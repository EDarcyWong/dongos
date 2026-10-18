#!/usr/bin/env python3
"""Boot real desktop, inject PS/2 drag/typing, inspect private RAM and GOP."""
from pathlib import Path
import argparse,hashlib,json,re,socket,struct,subprocess,sys,threading,time,uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import build as builder
from tools.make_fat32_disk import create
from tools.elf_symbols import read_elf_symbols
from tests import run_acpi_qemu as acpi
from tests import run_services_qemu as storage
ROOT=builder.ROOT
DISPLAY_VERSION=3
FONT_BASE=0x72000000
FONT_APERTURE_BYTES=8*1024*1024
FONT_PAGE_COUNT=FONT_APERTURE_BYTES//4096
FONT_PTE_FLAGS=0x8000000000000005
# Independent expected defaults, not colors inferred from the guest image or
# its composition cache. Runtime settings have a separate acceptance runner.
DEFAULT_PALETTE=(0xff151924,0xff242b3b,0xffedf1fa,0xffa3acc2,0xff4b80e8,
                 0xff3c4860,0x60000000,0xff35558c,0xffe56067)

def validate_font_aperture(root,virtual,font_bytes,pte):
    """Validate all actual PTEs; pte(root, va) also checks USER ancestry."""
    if virtual!=FONT_BASE or not 48<=font_bytes<=FONT_APERTURE_BYTES:
        raise ValueError('font descriptor escaped its fixed 8MiB aperture')
    payload_pages=(font_bytes+4095)//4096
    entries=[pte(root,virtual+i*4096) for i in range(FONT_PAGE_COUNT)]
    physical=entries[0]&storage.MASK
    if not physical or physical+payload_pages*4096>1<<48:
        raise ValueError('font physical payload range invalid')
    for i,entry in enumerate(entries):
        target=physical+min(i,payload_pages-1)*4096
        if entry&~0x60!=target|FONT_PTE_FLAGS:
            raise ValueError('font aperture page lost exact RO/NX/WB mapping at '+str(i))
    if pte(root,virtual-4096)!=0 or pte(root,virtual+FONT_APERTURE_BYTES)!=0:
        raise ValueError('font aperture guard mapped')
    return dict(root=root,virtual=virtual,bytes=FONT_APERTURE_BYTES,page_count=FONT_PAGE_COUNT,
                font_bytes=font_bytes,payload_pages=payload_pages,
                repeated_tail_pages=FONT_PAGE_COUNT-payload_pages,physical=physical,
                last_payload_physical=physical+(payload_pages-1)*4096,
                pte_flags=FONT_PTE_FLAGS,raw_ptes=entries,
                pte_sha256=hashlib.sha256(struct.pack('<2048Q',*entries)).hexdigest())

def validate_default_background(background,width,height,stride,scale_q8):
    """Check non-text panel/taskbar interiors against fixed palette colors."""
    scale=lambda n:(n*scale_q8+128)//256
    points=((5,5,DEFAULT_PALETTE[1]),(0,height//2,DEFAULT_PALETTE[0]),
            (scale(175),height-scale(45),DEFAULT_PALETTE[1]))
    for x,y,expected in points:
        if not (0<=x<width and 0<=y<height) or struct.unpack_from('<I',background,(y*stride+x)*4)[0]!=expected:
            raise ValueError('actual background/panel/taskbar differs from default palette at '+str((x,y)))
    return [dict(x=x,y=y,argb=color) for x,y,color in points]

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--reuse-esp',type=Path);parser.add_argument('--controls',action='store_true');parser.add_argument('--tablet',action='store_true');parser.add_argument('--scale',type=int,choices=(100,125,150,175,200),default=100);args=parser.parse_args()
    state=ROOT/'build/test/p7-desktop/qemu'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
    result=dict(passed=False,actual_qemu_executed=False,p7_60fps_accepted=False,runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    runner_before=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    build_sources={}
    process=None;qmp=None;uart=None;raw=bytearray()
    try:
        esp=args.reuse_esp.resolve() if args.reuse_esp else builder.build(runtime_level=7,desktop_scale=args.scale,output=state/'build')
        metadata=esp.parent/'build-inputs.json'
        if metadata.exists():
            description=json.loads(metadata.read_text())
            if description['runtime_level']!=7 or description['graphics_case'] is not None or not description['source_unchanged']:
                raise ValueError('normal desktop build identity differs')
            for path,expected in description['artifacts'].items():
                artifact=Path(path) if Path(path).is_absolute() else esp.parent/path
                if hashlib.sha256(artifact.read_bytes()).hexdigest()!=expected:raise ValueError('built artifact hash changed')
            build_sources=description['source_sha256']
            if any(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=expected for path,expected in build_sources.items()):
                raise ValueError('source differs from the actual completed build')
            result['build_inputs_verified']=True
        disk=state/'disk.img';create(disk,64)
        up,qp=storage.free_port(),storage.free_port()
        command=builder.qemu_command(esp,state/'guest',test=True)
        i=command.index('isa-debug-exit,iobase=0xf4,iosize=0x04');del command[i-1:i+1]
        command[command.index('-serial')+1]=f'tcp:127.0.0.1:{up},server=on,wait=off'
        command+=['-cpu','max,+smep,+smap,+umip','-S','-qmp',f'tcp:127.0.0.1:{qp},server=on,wait=off',
            '-drive',f'if=none,id=data,format=raw,cache=writeback,file={disk.resolve().as_posix()}',
            '-device','virtio-blk-pci,drive=data,disable-legacy=on']
        if args.tablet:command+=['-device','virtio-tablet-pci']
        result['command']=command
        with (state/'stderr.log').open('wb') as stderr:
            process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=stderr);result['actual_qemu_executed']=True
            qmp=acpi.QMP(qp,process);uart=socket.create_connection(('127.0.0.1',up));uart.settimeout(.2)
            def reader():
                with (state/'serial.log').open('wb') as stream:
                    while process.poll() is None:
                        try:b=uart.recv(4096)
                        except socket.timeout:continue
                        except OSError:break
                        if not b:break
                        raw.extend(b);stream.write(b);stream.flush()
            thread=threading.Thread(target=reader,daemon=True);thread.start();qmp.request('cont')
            started=time.monotonic()
            def wait(marker,timeout=90):
                deadline=time.monotonic()+timeout
                while marker not in raw:
                    if b'DONGOS_P1_KERNEL_FAIL' in raw or b'PANIC' in raw or process.poll() is not None:raise ValueError('actual desktop guest failed')
                    if time.monotonic()>deadline:raise TimeoutError('missing '+repr(marker))
                    time.sleep(.02)
            wait(b'DONGOS_P7_DESKTOP_READY');wait(b'DONGOS_INPUT_PS2_READY');wait(b'DONGOS_P7_AVX_CONTEXT_READY')
            result['firmware_inclusive_first_frame_seconds']=time.monotonic()-started
            if args.tablet:wait(b'DONGOS_INPUT_VIRTIO_TABLET_READY')
            time.sleep(.5)
            symbols=acpi.validation_symbols(esp.parent/'kernel.elf')
            memory={k.decode():int(v,16) for k,v in re.findall(rb'^memory_([a-z_]+)=0x([0-9a-f]{16})\r?$',raw,re.MULTILINE)}
            chunks=[]
            def physical(pa,n,role):
                if not 0<pa<1<<48 or not 0<n<=1<<24:raise ValueError('unsafe desktop read')
                path=state/f'physical-{len(chunks):03d}.bin';qmp.request('pmemsave',dict(val=pa,size=n,filename=str(path.resolve())))
                data=path.read_bytes()
                if len(data)!=n:raise ValueError('incomplete desktop read')
                chunks.append(dict(physical=pa,length=n,role=role,file=path.name,sha256=hashlib.sha256(data).hexdigest()));return data
            qmp.request('stop')
            boot=struct.unpack('<20Q',physical(memory['runtime_boot_info']-acpi.HHDM,160,'BootInfo'))
            def kernel(va,n,role):return physical(boot[15]+va-storage.KERNEL,n,role)
            processes=kernel(symbols[storage.symbol('user.memory','PROCESSES')],5*1288,'five private processes')
            roots=[struct.unpack_from('<Q',processes,i*1288+8)[0] for i in range(5)]
            if any(struct.unpack_from('<Q',processes,i*1288)[0]!=1 for i in range(5)) or len(set(roots))!=5:raise ValueError('five isolated loaded processes absent')
            table_base=boot[15]+symbols[storage.symbol('user.memory','TABLES')]-storage.KERNEL
            dynamic=struct.unpack('<16Q',kernel(symbols[storage.symbol('user.memory','DYNAMIC_PHYSICAL')],128,'held arena table pools'))
            pool_symbol=storage.symbol('user.memory','POOL_LIMITS')
            pool_limits=([32]*16 if pool_symbol not in symbols else list(struct.unpack('<16Q',kernel(symbols[pool_symbol],128,'trusted private pool limits'))))
            expected=[32]*16
            if pool_symbol in symbols:expected[3]=128
            if pool_limits!=expected:raise ValueError('unexpected private pool role/capacity')
            for pid,root in enumerate(roots):
                wanted=table_base+pid*32*4096 if pid<4 and pool_limits[pid]==32 else dynamic[pid]
                if root!=wanted or not root or root%4096:raise ValueError('private root escaped own pool')
            table_images={}
            def pte(root,va,kernel_root=False):
                current=root
                for shift in (39,30,21,12):
                    if not root<=current<root+(128 if kernel_root else pool_limits[roots.index(root)])*4096:raise ValueError('page table escaped its exclusive pool')
                    if current not in table_images:table_images[current]=physical(current,4096,'page table')
                    page=table_images[current];entry=struct.unpack_from('<Q',page,((va>>shift)&511)*8)[0]
                    if not entry&1:return entry
                    if not kernel_root and not entry&4:raise ValueError('USER ancestor missing')
                    if shift==12:return entry
                    if entry&128:raise ValueError('unexpected large user page')
                    current=entry&storage.MASK
            def user(pid,va,n,role):
                data=bytearray()
                while n:
                    entry=pte(roots[pid],va);step=min(n,4096-(va&4095))
                    if not entry&1:raise ValueError('missing desktop user mapping')
                    data.extend(physical((entry&storage.MASK)+(va&4095),step,role));va+=step;n-=step
                return bytes(data)
            descriptor=struct.unpack('<16Q',user(3,0x70001000,128,'immutable display descriptor'))
            version,width,height,stride,fmt,fb,nbytes,back,font,fontbytes,hz,queue,background_cache,window_cache,scale_q8,font_pixels=descriptor
            if version!=DISPLAY_VERSION or scale_q8!=args.scale*256//100 or font_pixels!=args.scale*16//100 or (width,height,stride,fmt)!=(boot[10],boot[11],boot[12],boot[13]) or nbytes!=stride*height*4:raise ValueError('descriptor differs from actual firmware GOP')
            if pte(roots[3],0x70001000)&0x800000000000001f!=0x8000000000000005:raise ValueError('display descriptor is writable/executable')
            if pte(roots[3],fb&~4095)&~0x60!=(boot[8]&~4095)|0x800000000000001f:raise ValueError('GOP not exact UC/USER/RW/NX')
            if pte(roots[3],back)&0x800000000000001f!=0x8000000000000007:raise ValueError('back buffer not WB/RW/NX')
            if pte(roots[3],font)&0x800000000000001f!=0x8000000000000005:raise ValueError('font not RO/NX')
            if pte(roots[4],fb&~4095)&storage.MASK==pte(roots[3],fb&~4095)&storage.MASK:raise ValueError('input driver can access framebuffer')
            for pid in (0,1,2):
                if pte(roots[pid],fb&~4095)!=0 or pte(roots[pid],queue)!=0:raise ValueError('storage process received desktop grants')
            if pte(roots[3],queue)&~0x60!=pte(roots[4],queue)&~0x60:raise ValueError('input transport not shared between actual roots')
            for first,length in ((back,nbytes),(background_cache,nbytes),(window_cache,8*1024*1024)):
                for address in range(first,first+length,4096):
                    if pte(roots[3],address)&0x800000000000001f!=0x8000000000000007:raise ValueError('RAM cache page lost WB/USER/RW/NX')
            for offset in range(0,(nbytes+4095)&~4095,4096):
                if pte(roots[3],(fb&~4095)+offset)&~0x60!=((boot[8]&~4095)+offset)|0x800000000000001f:
                    raise ValueError('GOP page cache policy/range differs')
            font_evidence=validate_font_aperture(roots[3],font,fontbytes,pte)
            font_physical=font_evidence['physical']
            asset_path=Path(f'assets/fonts/dong-cjk-sc-{font_pixels}.dgfont')
            asset=(ROOT/asset_path).read_bytes()
            if fontbytes!=len(asset) or hashlib.sha256(physical(font_physical,fontbytes,'actual read-only atlas')).digest()!=hashlib.sha256(asset).digest():
                raise ValueError('actual glyph atlas differs from licensed resource')
            last_page=physical(font_evidence['last_payload_physical'],4096,'font repeated last page and zero padding')
            valid_last=fontbytes-(font_evidence['payload_pages']-1)*4096
            if last_page[:valid_last]!=asset[-valid_last:] or any(last_page[valid_last:]):
                raise ValueError('font last page exposes bytes outside its validated payload')
            font_evidence.update(asset=str(asset_path.as_posix()),asset_sha256=hashlib.sha256(asset).hexdigest(),
                                 zero_padding_bytes=4096-valid_last)
            storage.write_json(state/'font-aperture.json',font_evidence)
            result.update(display_version=DISPLAY_VERSION,font_aperture_pages_verified=FONT_PAGE_COUNT,
                          font_payload_pages_verified=font_evidence['payload_pages'],
                          font_repeated_tail_pages_verified=font_evidence['repeated_tail_pages'])
            extended=struct.unpack('<Q',kernel(symbols[storage.symbol('user.memory','EXTENDED')],8,'extended frame metadata pointer'))[0]
            held=struct.unpack('<Q',kernel(symbols[storage.symbol('user.memory','FRAME_COUNT')],8,'held RAM count'))[0]
            if not 4096<held<=8192:raise ValueError('desktop did not use the bounded expanded RAM allocator')
            kernel_root=memory['root_physical'];metadata_physical=pte(kernel_root,extended,True)&storage.MASK
            owners=physical(metadata_physical,held*24,'actual expanded RAM ownership records')
            for i in range(held):
                pa,va,writable=struct.unpack_from('<3Q',owners,i*24)
                if va!=0xffffd00000000000+i*4096 or writable not in (0,1):raise ValueError('expanded owner record invalid')
                if pte(kernel_root,va,True)&~0x60!=pa|0x8000000000000001|(2 if writable else 0):raise ValueError('expanded supervisor alias lost WB/NX/W^X')
            for pid,name in enumerate(('shell','fs','block','compositor','input')):
                bias_i=struct.unpack_from('<Q',processes,pid*1288+224)[0]
                executable=(esp.parent/'services'/name/'program.elf').read_bytes()
                ph=struct.unpack_from('<Q',executable,32)[0];stride_ph,nph=struct.unpack_from('<HH',executable,54)
                for item in range(nph):
                    kind,flags,off,address,_,size,mem,_=struct.unpack_from('<IIQQQQQQ',executable,ph+item*stride_ph)
                    if kind!=1:continue
                    for page_va in range(address&~4095,(address+mem+4095)&~4095,4096):
                        entry=pte(roots[pid],bias_i+page_va)
                        if entry&0x800000000000001f!=(5|(2 if flags&2 else 0)|(0 if flags&1 else 1<<63)):raise ValueError('desktop ELF protection differs')
                        first,last=max(page_va,address),min(page_va+4096,address+size)
                        if flags&1 and first<last and physical((entry&storage.MASK)+first-page_va,last-first,'actual executable '+name)!=executable[off+first-address:off+last-address]:
                            raise ValueError('desktop executable bytes differ')
                top=0x7ffff00000-pid*0x1000000
                if pte(roots[pid],top)!=0 or pte(roots[pid],top-5*4096)!=0:raise ValueError('desktop user stack guard mapped')
            result.update(all_cache_pages_verified=True,all_elf_code_bytes_verified=True,owned_ram_pages_verified=held,user_stack_guards_verified=10)
            elfsyms=read_elf_symbols(esp.parent/'services/compositor/program.elf')
            bias=struct.unpack_from('<Q',processes,3*1288+224)[0]
            palette=struct.unpack('<9I',user(3,bias+elfsyms[storage.symbol('desktop.service','STYLE')],36,'actual default compositor palette'))
            if palette!=DEFAULT_PALETTE:raise ValueError('compositor default palette differs')
            result['default_palette_argb']=list(palette)
            window_va=bias+elfsyms[storage.symbol('desktop.service','WINDOWS')]
            def snapshot(name):
                windows=user(3,window_va,3128,'actual compositor window state '+name)
                image=state/(name+'.ppm');qmp.request('screendump',dict(filename=str(image.resolve())))
                from PIL import Image
                Image.open(image).save(state/(name+'.png'))
                return windows
            before=snapshot('desktop-before')
            def field(name,count=1):
                return struct.unpack('<'+str(count)+'Q',user(3,bias+elfsyms[storage.symbol('desktop.service',name)],count*8,'animation '+name))
            if field('ALPHA',4)!=(256,)*4 or field('PRESENTED_ALPHA',4)!=(256,)*4:raise ValueError('startup animation did not settle in actual presented frames')
            frames=field('ANIMATION_FRAMES')[0];samples=field('ANIMATION_SAMPLES',64)
            if frames<2 or not any(0<v<256 for v in samples):raise ValueError('startup easing skipped all intermediate actual frames')
            result['startup_animation']=dict(frames=frames,alpha_samples=list(samples[:min(frames,64)]),final_alpha=list(field('PRESENTED_ALPHA',4)))
            for i in range(4):
                l,t,r,b=struct.unpack_from('<4q',before,i*144+40)
                if not (0<=l<r<=width and 0<=t<b<=height) or (r-l+(24*scale_q8+128)//256)*(b-t+(24*scale_q8+128)//256)>524288:
                    raise ValueError('DPI layout or cache bound invalid')
            # Window state lives in the independent service ELF; policy ABI is
            # 16 slots of 144 bytes, then z order and focus/grab metadata.
            def rect(raw,index):return struct.unpack_from('<4q',raw,index*144+40)
            oldrect=rect(before,2);result['editor_rect_before']=oldrect
            qmp.request('cont')
            scale=lambda n:(n*scale_q8+128)//256
            pointer=[width//2,height//2]
            def move(dx,dy):
                # Real PS/2 reports have bounded deltas and sample rate. Wait
                # for each modest injection instead of queueing one 840px jump.
                steps=max(1,(max(abs(dx),abs(dy))+63)//64)
                for step in range(steps):
                    x=dx*(step+1)//steps-dx*step//steps;y=dy*(step+1)//steps-dy*step//steps
                    pointer[0]+=x;pointer[1]+=y
                    if args.tablet:
                        coords=[(pointer[0]*32767+width-2)//(width-1),(pointer[1]*32767+height-2)//(height-1)]
                        qmp.request('input-send-event',dict(events=[dict(type='abs',data=dict(axis=axis,value=v)) for axis,v in zip(('x','y'),coords)]))
                    else:qmp.request('input-send-event',dict(events=[dict(type='rel',data=dict(axis='x',value=x)),dict(type='rel',data=dict(axis='y',value=y))]))
                    time.sleep(.06)
            if args.tablet:
                for xx,yy in ((0,0),(width-1,height-1),(width//2,height//2)):
                    values=[(xx*32767+width-2)//(width-1),(yy*32767+height-2)//(height-1)]
                    qmp.request('input-send-event',dict(events=[dict(type='abs',data=dict(axis=axis,value=v)) for axis,v in zip(('x','y'),values)]))
                    time.sleep(.08);qmp.request('stop')
                    position=struct.unpack('<2q',user(3,window_va+2464,16,'actual absolute screen endpoint'))
                    if position!=(xx,yy):raise ValueError('real VirtIO absolute endpoints not calibrated exactly')
                    qmp.request('cont')
                pointer[:]=[width//2,height//2];result['tablet_exact_endpoints_verified']=True
            def button(down):qmp.request('input-send-event',dict(events=[dict(type='btn',data=dict(down=down,button='left'))]))
            move(oldrect[0]+scale(80)-width//2,oldrect[1]+scale(28)-height//2);time.sleep(.25);button(True);time.sleep(.15)
            for _ in range(10):move(10,-6);time.sleep(.08)
            button(False);time.sleep(.5)
            qmp.request('stop');after=snapshot('desktop-dragged');newrect=rect(after,2)
            if newrect!=tuple(v+d for v,d in zip(oldrect,(100,-60,100,-60))):raise ValueError('actual PS/2 drag did not move the compositor window')
            result['editor_rect_after']=newrect
            qmp.request('cont');move(0,scale(80));time.sleep(.15);button(True);time.sleep(.1);button(False)
            for key in ('a','b','c'):
                qmp.request('send-key',dict(keys=[dict(type='qcode',data=key)],**{'hold-time':30}));time.sleep(.15)
            time.sleep(2);qmp.request('stop');snapshot('desktop-typed')
            text=user(3,bias+elfsyms[storage.symbol('desktop.service','TEXT')],3,'actual editor typed bytes')
            size=struct.unpack('<Q',user(3,bias+elfsyms[storage.symbol('desktop.service','TEXT_SIZE')],8,'actual editor length'))[0]
            if text!=b'abc' or size!=3:raise ValueError('real PS/2 keyboard input did not reach editor')
            qmp.request('cont')
            qmp.request('send-key',dict(keys=[dict(type='qcode',data='ctrl'),dict(type='qcode',data='s')],**{'hold-time':50}))
            wait(b'DONGOS_EDITOR_SAVED',15);time.sleep(.1);qmp.request('stop')
            saved=storage.check_disk(disk,raw_name=b'NOTE    TXT',payload=b'abc')
            result['editor_disk']=saved
            snapshot('desktop-saved')
            mask=struct.unpack('<Q',kernel(symbols['sched_xstate_mask'],8,'actual YMM save mask'))[0]
            if mask!=7:raise ValueError('YMM save/restore mask absent')
            # Actual PS/2 drag at a host-paced 60-Hz request rate. Record
            # throughput and guest durations honestly; this gate never turns
            # a slow renderer or host scheduling delay into a 60fps pass.
            qmp.request('cont');move(0,-scale(80));time.sleep(.3);button(True);time.sleep(.2)
            qmp.request('stop')
            start_count=struct.unpack('<Q',kernel(symbols[storage.symbol('user.desktop','FRAMES')],8,'benchmark initial actual presentations'))[0]
            qmp.request('cont');clock=time.perf_counter();host_late=0
            for step in range(120):
                deadline=clock+(step+1)/60
                remaining=deadline-time.perf_counter()
                if remaining>0:time.sleep(remaining)
                elif -remaining>1/60:host_late+=1
                pointer[0]+=1
                if args.tablet:
                    value=(pointer[0]*32767+width-2)//(width-1)
                    qmp.request('input-send-event',dict(events=[dict(type='abs',data=dict(axis='x',value=value))]))
                else:qmp.request('input-send-event',dict(events=[dict(type='rel',data=dict(axis='x',value=1))]))
            elapsed=time.perf_counter()-clock;time.sleep(.1);qmp.request('stop')
            end_count=struct.unpack('<Q',kernel(symbols[storage.symbol('user.desktop','FRAMES')],8,'benchmark final actual presentations'))[0]
            frame_count=struct.unpack('<Q',user(3,bias+elfsyms[storage.symbol('desktop.service','FRAME_COUNT')],8,'compositor presentation count'))[0]
            durations=struct.unpack('<256Q',user(3,bias+elfsyms[storage.symbol('desktop.service','FRAME_TIMES')],2048,'actual composition and presentation TSC durations'))
            completed_times=struct.unpack('<256Q',user(3,bias+elfsyms[storage.symbol('desktop.service','FRAME_COMPLETED')],2048,'actual completed frame TSC history before mouse release'))
            if frame_count!=end_count:raise ValueError('compositor and trusted presentation counts differ')
            samples=[durations[i%256]/hz for i in range(max(start_count,end_count-256),end_count)]
            completed=[completed_times[i%256] for i in range(max(start_count,end_count-256),end_count)]
            if len(completed)<2 or any(a>=b for a,b in zip(completed,completed[1:])):raise ValueError('actual completion timestamps absent or unordered')
            completion_seconds=(completed[-1]-completed[0])/hz
            actual_fps=(len(completed)-1)/completion_seconds
            trusted_last=struct.unpack('<Q',kernel(symbols[storage.symbol('user.desktop','LAST')],8,'trusted final actual presentation timestamp'))[0]
            if not trusted_last<=completed[-1]<=trusted_last+hz//10:raise ValueError('completed timestamp detached from trusted presentation')
            result['drag_performance']=dict(requested_hz=60,host_seconds=elapsed,host_late_requests=host_late,
                actual_presentations=end_count-start_count,actual_fps=actual_fps,guest_frame_seconds=samples,
                maximum_frame_seconds=max(samples,default=0),xsave_mask=mask,guest_completion_tsc=completed,
                completed_frame_intervals=len(completed)-1,guest_completion_seconds=completion_seconds,
                mouse_release_excluded=True)
            result['p7_60fps_accepted']=result.get('build_inputs_verified',False) and width==1920 and height==1080 and host_late==0 and actual_fps>=59.5 and bool(samples) and max(samples)<=1/60
            cpus=kernel(symbols[storage.symbol('smp.runtime','CPUS')],4096,'live four CPU contexts')
            domain=struct.unpack('<14Q',kernel(symbols[storage.symbol('smp.runtime','DOMAIN')],112,'live acknowledged TLB domain'))
            boxes=kernel(symbols['smp_tlb_mailboxes'],1024,'live actual AP mailbox acknowledgements')
            if domain[0:2]!=(1,0) or domain[3]!=4 or domain[6]!=domain[7] or domain[8]!=domain[9] or domain[8]!=domain[7]*3 or domain[13]!=0:
                raise ValueError('desktop did not retain a safe four CPU TLB domain')
            registers=qmp.request('human-monitor-command',{'command-line':'info registers -a'})
            (state/'all-cpu-registers.txt').write_text(registers)
            hardware=re.split(r'CPU#\d+\s*',registers)[1:]
            if len(hardware)!=4:raise ValueError('desktop did not retain four actual vCPUs')
            for i in (1,2,3):
                cpu=struct.unpack_from('<32Q',cpus,i*256);box=struct.unpack_from('<8Q',boxes,i*64)
                if cpu[1:6]!=(i,i,4,1,kernel_root) or cpu[10]!=7 or cpu[25]!=1 or cpu[30]!=domain[7]+1 or cpu[31]!=0:
                    raise ValueError('AP online/xstate/IPI context differs during desktop')
                if box[0]!=domain[6] or box[3]!=domain[6] or box[5:]!=(0x8877665544332211,0,0):raise ValueError('AP live mailbox failed')
                r=hardware[i]
                if int(re.search(r'CR3=([0-9a-fA-F]+)',r)[1],16)!=kernel_root or int(re.search(r'RIP=([0-9a-fA-F]+)',r)[1],16)!=symbols['smp_ap_idle']+2 or 'HLT=1' not in r or 'CPL=0' not in r:
                    raise ValueError('AP actual hardware stopped following the shared kernel root')
            result['live_smp_tlb_verified']=True
            # Full-cache RAM snapshot plus an independent scalar pixel oracle.
            # Includes AA/shadow boundaries and overlapping/occluded windows.
            def ram(va,length):
                addresses=[pte(roots[3],v)&storage.MASK for v in range(va,va+length,4096)]
                lo=min(addresses);hi=max(addresses)+4096
                block=physical(lo,hi-lo,'actual RAM composition cache')
                return b''.join(block[p-lo:p-lo+4096] for p in addresses)[:length]
            bg=ram(background_cache,nbytes);textures=ram(window_cache,8*1024*1024)
            result['default_background_exact_pixels']=validate_default_background(bg,width,height,stride,scale_q8)
            scene=snapshot('composition-oracle');from PIL import Image
            actual=Image.open(state/'composition-oracle.png').convert('RGB')
            order=struct.unpack_from('<16Q',scene,2304);count=struct.unpack_from('<Q',scene,2432)[0]
            pos=struct.unpack_from('<2q',scene,2464);alphas=field('PRESENTED_ALPHA',4)
            points={(x,y) for y in range(3,height,37) for x in range(5,width,43)}
            for index in range(4):
                l,t,r,b=rect(scene,index)
                for x in (l-scale(12),l-1,l,l+1,l+scale(8),r-scale(8)-1,r-1,r,r+scale(9)):
                    for y in (t-scale(12),t-1,t,t+1,t+scale(8),b-scale(8)-1,b-1,b,b+scale(10)):
                        if 0<=x<width and 0<=y<height:points.add((x,y))
            for dy in (0,scale(4),scale(16)):
                for dx in (0,dy//2):
                    x,y=pos[0]+dx,pos[1]+dy
                    if 0<=x<width and 0<=y<height:points.add((x,y))
            for x,y in points:
                color=struct.unpack_from('<I',bg,(y*stride+x)*4)[0]
                for handle in order[:count]:
                    index=(handle&255)-1;l,t,r,b=rect(scene,index);margin=scale(12)
                    if alphas[index] and l-margin<=x<r+margin and t-margin<=y<b+margin:
                        off=index*0x200000+((y-t+margin)*(r-l+2*margin)+x-l+margin)*4
                        src=struct.unpack_from('<I',textures,off)[0];a=src>>24
                        color=sum(min(255,((src>>sh)&255)+(((color>>sh)&255)*(255-a)+127)//255)<<sh for sh in (0,8,16,24))
                dx,dy=x-pos[0],y-pos[1]
                if 0<=dy<scale(17) and 0<=dx<=dy//2:color=DEFAULT_PALETTE[2]
                expected=((color>>16)&255,(color>>8)&255,color&255)
                if actual.getpixel((x,y))!=expected:raise ValueError('actual GOP differs from independent cache/occlusion pixel oracle at '+str((x,y)))
            result['composition_exact_gop_pixels']=len(points)
            if args.tablet:
                selected=struct.unpack('<Q',kernel(symbols[storage.symbol('user.devices','INPUT_SELECTED')],8,'actual input PCI function'))[0]
                block_selected=struct.unpack('<Q',kernel(symbols[storage.symbol('user.devices','SELECTED')],8,'actual block PCI function'))[0]
                if not selected or selected==block_selected:raise ValueError('input and block share PCI authority')
                bars=struct.unpack('<18Q',kernel(symbols[storage.symbol('user.devices','INPUT_BARS')],144,'actual input BAR grants'))
                block_bars=struct.unpack('<18Q',kernel(symbols[storage.symbol('user.devices','BARS')],144,'actual block BAR grants'))
                bar_pages=0
                for index in range(6):
                    pa,size,handle=bars[index*3:index*3+3]
                    if not size:continue
                    if not handle:raise ValueError('input BAR has no caller-bound handle')
                    for j in range(6):
                        other,length,_=block_bars[j*3:j*3+3]
                        if length and pa<other+length and other<pa+size:raise ValueError('input/block BAR overlap')
                    for offset in range(0,size,4096):
                        entry=pte(roots[4],0x60000000+index*0x1000000+offset)
                        if entry&~0x60!=(pa+offset)|0x800000000000001f:raise ValueError('input BAR lost exact UC/USER/RW/NX grant')
                        bar_pages+=1
                lease=struct.unpack('<4Q',kernel(symbols[storage.symbol('user.devices','INPUT_LEASE')],32,'actual exclusive input DMA lease'))
                if lease[0]!=2 or lease[2:]!=(0x68000000,16384):raise ValueError('input DMA lease differs')
                for off in range(0,16384,4096):
                    if pte(roots[4],lease[2]+off)&~0x60!=(lease[1]+off)|0x8000000000000007 or pte(roots[3],lease[2]+off)!=0:
                        raise ValueError('input DMA RAM isolation/WB lost')
                wire=physical(lease[1],16384,'actual device-written/recycled input split rings')
                for index in range(64):
                    if struct.unpack_from('<QIHH',wire,index*16)!=(lease[1]+4096+index*8,8,2,0):raise ValueError('actual input descriptor escaped its write-only event buffer')
                input_bias=struct.unpack_from('<Q',processes,4*1288+224)[0]
                input_symbols=read_elf_symbols(esp.parent/'services/input/program.elf')
                state_va=input_bias+input_symbols[storage.symbol('drivers.tablet_service','STATE')]
                ready,fault,used,available,notify,completed=struct.unpack('<6Q',user(4,state_va+176,48,'actual tablet transport counters'))
                if ready!=1 or fault or completed<8 or used!=completed%65536 or available!=(64+completed)%65536:
                    raise ValueError('actual device completions not retired/recycled')
                if struct.unpack_from('<H',wire,1026)[0]!=available or struct.unpack_from('<H',wire,2050)[0]!=used or struct.unpack_from('<H',wire,9218)[0]!=0:
                    raise ValueError('actual DMA ring indices differ from input state')
                result['tablet_dma']=dict(exact_bar_pages=bar_pages,wire_completions=completed,used_index=used,available_index=available,lease_physical=lease[1],retained_bytes=lease[3],isolated_from_block=True)
            qmp.request('cont');button(False);time.sleep(.3);qmp.request('stop')
            if args.controls:
                current=snapshot('before-controls');r=rect(current,2);px,py=struct.unpack_from('<2q',current,2464)
                qmp.request('cont');move(r[2]-scale(16)-px,r[1]+scale(12)-py);time.sleep(.3);button(True);time.sleep(.1);button(False);time.sleep(1)
                qmp.request('stop');hidden=snapshot('window-hidden')
                if struct.unpack_from('<Q',hidden,2*144+136)[0]&1:raise ValueError('actual title close did not hide the editor')
                deadline=time.monotonic()+5
                while field('PRESENTED_ALPHA',4)[2]!=0 or field('FRAME_BUSY')[0]!=0:
                    if time.monotonic()>deadline:raise ValueError('hide animation failed to become transparent')
                    qmp.request('cont');time.sleep(.03);qmp.request('stop')
                hidden=snapshot('window-hidden')
                px,py=struct.unpack_from('<2q',hidden,2464)
                qmp.request('cont');move(scale(435)-px,height-scale(40)-py);time.sleep(.3);button(True)
                # Stop only between completed frames. QMP reads real user state
                # and actual GOP pixels, never an image rendered by this host.
                middle=None;middle_alpha=0
                progress={name:bias+elfsyms[storage.symbol('desktop.service',name)] for name in ('FRAME_BUSY','ALPHA','PRESENTED_ALPHA')}
                low=min(progress.values());high=max(progress['FRAME_BUSY']+8,progress['ALPHA']+32,progress['PRESENTED_ALPHA']+32)
                def live_progress():
                    data=user(3,low,high-low,'live animation publication')
                    busy=struct.unpack_from('<Q',data,progress['FRAME_BUSY']-low)[0]
                    alpha=struct.unpack_from('<Q',data,progress['ALPHA']-low+16)[0]
                    published=struct.unpack_from('<Q',data,progress['PRESENTED_ALPHA']-low+16)[0]
                    return busy,alpha,published
                deadline=time.monotonic()+2
                while time.monotonic()<deadline:
                    busy,alpha,published=live_progress()
                    if busy==0 and alpha==published and 0<published<256:
                        qmp.request('stop')
                        busy,alpha,published=live_progress()
                        if busy==0 and alpha==published and 0<published<256:
                            snapshot('animation-middle');middle=state/'animation-middle.png';middle_alpha=published
                            middle_body=field('PRESENTED_RECTS',16)[8:12]
                            middle_texture=ram(window_cache+2*0x200000,0x200000)
                            break
                        qmp.request('cont')
                    time.sleep(.001)
                if middle is None:raise ValueError('no intermediate completed window animation captured')
                qmp.request('cont');button(False);time.sleep(.5)
                qmp.request('stop');restored=snapshot('window-restored')
                if not struct.unpack_from('<Q',restored,2*144+136)[0]&1 or struct.unpack_from('<Q',restored,2440)[0]!=259:
                    raise ValueError('actual taskbar did not restore/focus the editor')
                deadline=time.monotonic()+5
                while field('PRESENTED_ALPHA',4)[2]!=256 or field('FRAME_BUSY')[0]!=0:
                    if time.monotonic()>deadline:raise ValueError('restore animation failed to reach opaque endpoint')
                    qmp.request('cont');time.sleep(.03);qmp.request('stop')
                restored=snapshot('window-restored')
                from PIL import Image
                hidden_pixels=Image.open(state/'window-hidden.png').convert('RGB')
                middle_pixels=Image.open(middle).convert('RGB');opaque_pixels=Image.open(state/'window-restored.png').convert('RGB')
                # The intermediate frame scales the actual final-size cache.
                # Compare its independently sampled premultiplied texels over
                # the exact hidden scene, including text/AA/shadow boundaries.
                rr=rect(restored,2);verified=0;geom_verified=0
                margin=scale(12);sw=rr[2]-rr[0]+2*margin;sh=rr[3]-rr[1]+2*margin
                l,t,r,b=middle_body
                mx=margin*(r-l)//(rr[2]-rr[0]);my=margin*(b-t)//(rr[3]-rr[1])
                full=(l-mx,t-my,r+mx,b+my)
                for yy in range(max(0,full[1]),min(height,full[3]),7):
                    for xx in range(max(0,full[0]),min(width,full[2]),11):
                        sx=(xx-full[0])*sw//(full[2]-full[0]);sy=(yy-full[1])*sh//(full[3]-full[1])
                        packed=struct.unpack_from('<I',middle_texture,(sy*sw+sx)*4)[0]
                        src=((packed>>16)&255,(packed>>8)&255,packed&255)
                        dst=hidden_pixels.getpixel((xx,yy));actual=middle_pixels.getpixel((xx,yy))
                        scaled_a=((packed>>24)*middle_alpha+128)//256
                        expected=tuple(min(255,(c*middle_alpha+128)//256+(d*(255-scaled_a)+127)//255) for c,d in zip(src,dst))
                        if actual!=expected:raise ValueError('intermediate actual GOP zoom/alpha pixel differs from independent cache oracle')
                        if actual!=src and actual!=dst:verified+=1
                        if middle_body!=rr:geom_verified+=1
                if verified<8:raise ValueError('animation did not change enough actual GOP pixels')
                result.update(title_hide_verified=True,taskbar_restore_verified=True,animation_verified=True,
                    animation_middle_alpha=middle_alpha,animation_exact_gop_pixels=verified,animation_geometry_pixels=geom_verified,animation_final_alpha=256)
            count=struct.unpack('<Q',kernel(symbols[storage.symbol('user.desktop','FRAMES')],8,'kernel observed actual presentations'))[0]
            if count<5:raise ValueError('no repeated actual presentation')
            storage.write_json(state/'physical-manifest.json',chunks)
            result.update(passed=True,resolution=[width,height],actual_processes=5,presentations=count,pointer_transport='virtio-tablet' if args.tablet else 'ps2',pointer_drag_verified=True,scale_percent=args.scale,font_pixels=font_pixels,
                ps2_typing_verified=True,isolated_display_input_grants=True,font_readonly_verified=True,back_buffer_wb_verified=True,
                screenshot=str(state/('window-restored.png' if args.controls else 'desktop-saved.png')),physical_reads=len(chunks),editor_text=text.decode(),editor_real_flush_verified=True)
    except Exception as exc:result.update(error=f'{type(exc).__name__}: {exc}',p7_60fps_accepted=False)
    finally:
        if qmp:
            try:qmp.request('quit')
            except Exception:pass
            qmp.close()
        if uart:uart.close()
        if process:
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        unchanged=runner_before==hashlib.sha256(Path(__file__).read_bytes()).hexdigest() and all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected for path,expected in build_sources.items())
        result['source_unchanged']=unchanged
        if not unchanged:result.update(passed=False,p7_60fps_accepted=False,error='source changed during actual verification')
        storage.write_json(state/'result.json',result)
    print('P7 actual desktop','PASS' if result['passed'] else 'FAIL',state,result.get('error',''))
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
