#!/usr/bin/env python3
"""Real runtime DPI, durable preferences, reboot and damaged-slot QEMU gate."""
from pathlib import Path
import argparse, hashlib, json, re, shutil, socket, struct, subprocess, sys, threading, time, uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import build as builder
from tools.make_fat32_disk import create
from tools.elf_symbols import read_elf_symbols
from tools.kernel_storage_profile import verify_profile
from tests import run_acpi_qemu as acpi, run_services_qemu as storage
from tests import desktop_preferences_oracle as oracle

ROOT = builder.ROOT
DARK = (0xff151924, 0xff242b3b, 0xffedf1fa, 0xffa3acc2, 0xff4b80e8,
        0xff3c4860, 0x60000000, 0xff35558c, 0xffe56067)
LIGHT = (0xffe7edf6, 0xfff9fbff, 0xff172c48, 0xff465a75, 0xff1f65b8,
         0xffb7c8dd, 0x40000000, 0xffb2d2f4, 0xffae2b36)

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def check(condition, message):
    if not condition: raise ValueError(message)
def rect(state, i): return struct.unpack_from('<4q', state, i*144+40)
def theme_bytes(colors, scale): return struct.pack('<9I4x4Q', *colors, 7, 8, scale, 140)

def storage_profile(esp):
    """Read the exact profile from real input sources, never infer it from roots."""
    output = Path(esp).resolve().parent
    manifest = json.loads((output / 'build-inputs.json').read_text(encoding='utf-8'))
    # Explicit build helpers place their reviewed source copy beside image/.
    # Ordinary build.py uses this module's current repository source root.
    staged = output.parent / 'source'
    source_root = staged if output.name == 'image' and staged.is_dir() else ROOT
    count = verify_profile(output, manifest, source_root=source_root)
    return count, manifest['runtime_level']

class Guest:
    """Only QMP input and read-only physical inspection; never patches guest RAM."""
    def __init__(self, esp, disk, state, readonly=False, block_backend='virtio'):
        self.esp,self.disk,self.state = esp,disk,state
        state.mkdir(parents=True);self.raw=bytearray();self.chunks=[];self.tables={}
        self.process=self.qmp=self.uart=None;self.stopped=False
        self.evidence=dict(actual_qemu_executed=False, disk=str(disk), readonly=readonly)
        up,qp=storage.free_port(),storage.free_port()
        command=builder.qemu_command(esp,state/'guest',test=True)
        i=command.index('isa-debug-exit,iobase=0xf4,iosize=0x04');del command[i-1:i+1]
        command[command.index('-serial')+1]=f'tcp:127.0.0.1:{up},server=on,wait=off'
        command += ['-cpu','max,+smep,+smap,+umip','-S','-qmp',f'tcp:127.0.0.1:{qp},server=on,wait=off',
                    '-drive',f'if=none,id=data,format=raw,cache=writeback,file={disk.resolve().as_posix()}'+(',readonly=on' if readonly else ''),
                    '-device','virtio-blk-pci,drive=data,disable-legacy=on','-device','virtio-tablet-pci']
        if block_backend=='ahci':
            # Keep the data disk at SATA port0 and the EFI fallback volume at
            # port1. The driver chooses the first live direct-ATA port.
            from tests.run_ahci_qemu import ahci_command
            command=ahci_command(command)
        elif block_backend=='nvme':
            from tests.run_nvme_qemu import nvme_command
            command=nvme_command(command)
        else:check(block_backend=='virtio','unsupported block backend')
        self.evidence['command']=command
        self.stderr=(state/'stderr.log').open('wb')
        try:
            self.process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=self.stderr)
            self.evidence['actual_qemu_executed']=True
            self.qmp=acpi.QMP(qp,self.process)
            self.uart=socket.create_connection(('127.0.0.1',up));self.uart.settimeout(.2)
            def reader():
                with (state/'serial.log').open('wb') as stream:
                    while self.process.poll() is None:
                        try: data=self.uart.recv(4096)
                        except socket.timeout: continue
                        except OSError: break
                        if not data: break
                        self.raw.extend(data);stream.write(data);stream.flush()
            self.reader=threading.Thread(target=reader,daemon=True);self.reader.start()
            self.qmp.request('cont')
            for marker in (b'DONGOS_P7_DESKTOP_READY',b'DONGOS_INPUT_VIRTIO_TABLET_READY',b'DONGOS_P7_AVX_CONTEXT_READY'):self.wait(marker)
            self.pause()
            self.bootstrap_audit()
            self.settle()
        except Exception:
            self.close();raise
    def bootstrap_audit(self):
        """Default synchronous audit; specialized runners may audit a sealed image."""
        self.symbols=acpi.validation_symbols(self.esp.parent/'kernel.elf')
        memory={k.decode():int(v,16) for k,v in re.findall(rb'^memory_([a-z_]+)=0x([0-9a-f]{16})\r?$',self.raw,re.MULTILINE)}
        self.boot=struct.unpack('<20Q',self.physical(memory['runtime_boot_info']-acpi.HHDM,160,'BootInfo'))
        self.processes=self.kernel(self.ksym('user.memory','PROCESSES'),5*1288,'five private processes')
        self.roots=[struct.unpack_from('<Q',self.processes,i*1288+8)[0] for i in range(5)]
        self.validate_private_pools()
        check(all(struct.unpack_from('<Q',self.processes,i*1288)[0]==1 for i in range(5)),'missing service')
        self.bias=struct.unpack_from('<Q',self.processes,3*1288+224)[0]
        self.syms=read_elf_symbols(self.esp.parent/'services/compositor/program.elf')
        self.verify_elf()
    def wait(self,marker,timeout=90):
        deadline=time.monotonic()+timeout
        while marker not in self.raw:
            check(self.process.poll() is None and b'DONGOS_P1_KERNEL_FAIL' not in self.raw and b'PANIC' not in self.raw,'guest failed: '+self.raw[-2000:].decode(errors='replace'))
            if time.monotonic()>deadline:raise TimeoutError('missing '+repr(marker))
            time.sleep(.02)
    def pause(self):
        if not self.stopped:self.qmp.request('stop');self.stopped=True
        self.tables={}
    def resume(self):
        if self.stopped:self.qmp.request('cont');self.stopped=False
    def physical(self,pa,n,role):
        check(0<pa<1<<48 and 0<n<=1<<24,'unsafe physical read')
        path=self.state/f'physical-{len(self.chunks):05d}.bin'
        self.qmp.request('pmemsave',dict(val=pa,size=n,filename=str(path.resolve())))
        data=path.read_bytes();check(len(data)==n,'incomplete read')
        self.chunks.append(dict(physical=pa,length=n,role=role,file=path.name,sha256=hashlib.sha256(data).hexdigest()))
        return data
    def ksym(self,module,name):return self.symbols[storage.symbol(module,name)]
    def kernel(self,va,n,role):return self.physical(self.boot[15]+va-storage.KERNEL,n,role)
    def kval(self,module,name):return struct.unpack('<Q',self.kernel(self.ksym(module,name),8,module+'.'+name))[0]
    def validate_private_pools(self):
        # Limits come from trusted kernel records, never an application's PTEs.
        self.static_pools,self.storage_runtime=storage_profile(self.esp)
        symbol=storage.symbol('user.memory','POOL_LIMITS')
        check(self.storage_runtime<5 or symbol in self.symbols,'service kernel omitted private pool limits')
        self.pool_limits=([32]*16 if symbol not in self.symbols else
            list(struct.unpack('<16Q',self.kernel(self.symbols[symbol],128,'trusted per-process pool limits'))))
        expected=[32]*16
        if symbol in self.symbols:expected[3]=128
        check(self.pool_limits==expected,'unexpected private table capacity/role')
        base=self.boot[15]+self.ksym('user.memory','TABLES')-storage.KERNEL
        dynamic=struct.unpack('<16Q',self.kernel(self.ksym('user.memory','DYNAMIC_PHYSICAL'),128,'held arena table pools'))
        pointers=struct.unpack('<16Q',self.kernel(self.ksym('user.memory','DYNAMIC_TABLES'),128,'held arena table aliases'))
        spaces=self.kernel(self.ksym('user.memory','SPACES'),16*64,'all private Space descriptors')
        metadata=self.kernel(self.ksym('user.memory','META'),16*128,'all private table metadata')
        generations=struct.unpack('<16Q',self.kernel(self.ksym('user.memory','GENERATIONS'),128,'memory root generations'))
        processes=self.kernel(self.ksym('user.memory','PROCESSES'),16*1288,'complete memory Process identities')
        plan=self.kernel(self.ksym('boot.service_memory','PLAN'),48,'actual held service arena plan')
        arena,arena_bytes=struct.unpack_from('<2Q',plan,32)
        next_page=self.kval('boot.service_memory','NEXT_PAGE')
        check(0<arena<1<<32 and arena_bytes==128*1024*1024 and arena+arena_bytes<=1<<32
              and 0<next_page<=32768,'held service arena extent differs')
        roots=[struct.unpack_from('<Q',processes,pid*1288+8)[0] for pid in range(16)]
        check(0<len(self.roots)<=16 and self.roots==roots[:len(self.roots)],'process root snapshot changed')
        kernel_base,kernel_pages=self.trusted_kernel_pool()
        kernel_root=self.evidence['trusted_kernel_page_table_pool']['root_physical']
        kernel_raw=self.physical(kernel_base,kernel_pages*4096,'complete retained kernel table pool')
        ranges=[(kernel_base,kernel_base+kernel_pages*4096)];audits=[]
        # Local imports avoid the oracle -> lifecycle -> settings import cycle.
        from tests.p2_pcid_oracle import audit_pool
        from tests.run_fat_paths_qemu import effective_mapping
        def kernel_table(pa):
            check(kernel_base<=pa<=kernel_base+len(kernel_raw)-4096 and pa%4096==0,'table alias escaped kernel pool')
            return kernel_raw[pa-kernel_base:pa-kernel_base+4096]
        for pid,root in enumerate(roots):
            space=spaces[pid*64:(pid+1)*64]
            ready=struct.unpack_from('<Q',processes,pid*1288)[0]
            frame_root=struct.unpack_from('<Q',processes,pid*1288+160)[0]
            if root==0:
                check(ready==frame_root==0 and space==bytes(64),'empty process retained Space/root identity')
                continue
            wanted=base+pid*32*4096 if self.uses_static_pool(pid) else dynamic[pid]
            check(ready==1 and root==frame_root==wanted and root>0 and root%4096==0 and generations[pid]>0,'private root differs from its own held table pool/Frame/generation')
            end=root+self.pool_limits[pid]*4096
            check(end<=1<<48,'private pool physical extent overflows')
            check(all(not(root<stop and start<end) for start,stop in ranges),'private table pools overlap')
            ranges.append((root,end))
            pointer=self.ksym('user.memory','TABLES')+pid*32*4096 if self.uses_static_pool(pid) else pointers[pid]
            check(struct.unpack_from('<Q',space,8)[0]==pointer and pointer!=0
                  and struct.unpack_from('<Q',space,32)[0]==self.ksym('user.memory','META')+pid*128,'Space pool/metadata alias differs')
            if not self.uses_static_pool(pid):
                check(arena<=root and end<=arena+next_page*4096 and pointer==0xffffd40000000000+root-arena
                      and not(root<self.boot[15]+0x200000 and self.boot[15]<end),'dynamic pool is not held in the allocated service arena')
            else:check(self.boot[15]<=root and end<=self.boot[15]+0x200000,'static pool escaped the loader window')
            for offset in range(0,self.pool_limits[pid]*4096,4096):
                mapping=effective_mapping(kernel_root,pointer+offset,kernel_table,(kernel_base,kernel_pages),kernel_pages)
                check(mapping['present'],'table pool supervisor alias is absent')
                selector=0x118|(128 if mapping['leaf_bytes']==4096 else 4096)
                check(mapping['present'] and not mapping['effective_user'] and mapping['effective_writable'] and mapping['effective_nx']
                      and mapping['physical']==root+offset and not mapping['leaf_entry']&selector,'table pool supervisor WB alias differs')
            image=self.physical(root,self.pool_limits[pid]*4096,'complete private pool '+str(pid))
            audit=audit_pool(image,metadata[pid*128:(pid+1)*128],space,root,self.pool_limits[pid],kernel_raw,kernel_root-kernel_base)
            audit.update(slot=pid,generation=generations[pid],kind='static' if self.uses_static_pool(pid) else 'arena')
            audits.append(audit)
        self.evidence['trusted_private_pool_pages']=self.pool_limits
        self.evidence['trusted_static_user_pools']=self.static_pools
        self.evidence['trusted_private_pool_audits']=audits
        self.evidence['trusted_service_arena']=dict(physical=arena,bytes=arena_bytes,next_page=next_page)
    def uses_static_pool(self,pid):
        check(type(pid)is int and 0<=pid<16,'invalid private pool slot')
        return pid<self.static_pools and self.pool_limits[pid]==32
    def trusted_kernel_pool(self):
        # The actual linked layout and UART independently bind the retained
        # kernel View. No compiler or guest write is invoked by this reader.
        layout_path=self.esp.parent/'dong_layout.json'
        types={t['full_name']:t for t in json.loads(layout_path.read_text())['types']}
        work,view=types['boot.memory_startup.Workspace'],types['boot.runtime_view.View']
        fields={f['name']:f['offset'] for f in view['fields']}
        runtime=next(f for f in work['fields'] if f['name']=='runtime')
        check(view['size']==runtime['size']==160 and all(fields.get(n)==o for n,o in
              dict(pool=96,pool_physical=104,pool_pages=112,root_physical=152).items()),'kernel View ABI differs')
        self.kernel_memory_layout=dict(layout_file_sha256=sha(layout_path),workspace_size=work['size'],runtime_offset=runtime['offset'],view_size=160,view_fields=fields)
        from tests.run_nvme_qemu import NvmeGuest
        return NvmeGuest.trusted_kernel_pool(self)
    def private_pages(self,root):
        check(root in self.roots and root>0,'unknown private root')
        return self.pool_limits[self.roots.index(root)]
    def pte(self,root,va):
        current=root
        for shift in (39,30,21,12):
            check(root<=current<root+self.private_pages(root)*4096,'page table outside private pool')
            if current not in self.tables:self.tables[current]=self.physical(current,4096,'page table')
            entry=struct.unpack_from('<Q',self.tables[current],((va>>shift)&511)*8)[0]
            if not entry&1:return entry
            check(entry&4,'missing USER ancestor')
            if shift==12:return entry
            check(not entry&128,'unexpected large page');current=entry&storage.MASK
    def user(self,pid,va,n,role):
        data=bytearray()
        while n:
            entry=self.pte(self.roots[pid],va);check(entry&1,'missing user mapping')
            size=min(n,4096-(va&4095));data.extend(self.physical((entry&storage.MASK)+(va&4095),size,role));va+=size;n-=size
        return bytes(data)
    def field(self,name,n=8,module='desktop.service'):
        return self.user(3,self.bias+self.syms[storage.symbol(module,name)],n,module+'.'+name)
    def value(self,name,module='desktop.service'):return struct.unpack('<Q',self.field(name,module=module))[0]
    def descriptor(self):return struct.unpack('<16Q',self.user(3,0x70001000,128,'Display v3'))
    def windows(self):return self.field('WINDOWS',3128)
    def verify_elf(self):
        for pid,name in enumerate(('shell','fs','block','compositor','input')):
            bias=struct.unpack_from('<Q',self.processes,pid*1288+224)[0]
            data=(self.esp.parent/'services'/name/'program.elf').read_bytes()
            ph=struct.unpack_from('<Q',data,32)[0];stride,count=struct.unpack_from('<HH',data,54)
            for i in range(count):
                kind,flags,off,address,_,size,mem,_=struct.unpack_from('<IIQQQQQQ',data,ph+i*stride)
                if kind!=1:continue
                for va in range(address&~4095,(address+mem+4095)&~4095,4096):
                    entry=self.pte(self.roots[pid],bias+va)
                    check(entry&0x800000000000001f==(5|(2 if flags&2 else 0)|(0 if flags&1 else 1<<63)),'ELF page permission differs')
                    first,last=max(va,address),min(va+4096,address+size)
                    if flags&1 and first<last:
                        check(self.physical((entry&storage.MASK)+first-va,last-first,'executable '+name)==data[off+first-address:off+last-address],'actual ELF code differs')
            top=0x7ffff00000-pid*0x1000000
            check(self.pte(self.roots[pid],top)==0 and self.pte(self.roots[pid],top-5*4096)==0,'stack guard mapped')
        self.evidence.update(actual_processes=5,all_elf_code_bytes_verified=True,user_stack_guards_verified=10)
    def settle(self):
        self.resume();time.sleep(.35);self.pause();deadline=time.monotonic()+8
        while (self.value('FRAME_BUSY') or self.field('CACHES_DIRTY',1)!=b'\0'
               or self.field('BACKGROUND_DIRTY',1)!=b'\0' or self.value('CACHE_MASK')
               or self.field('ALPHA',32)!=self.field('PRESENTED_ALPHA',32)
               or self.value('MOTION_ACTIVE') or self.field('VISUAL_RECTS',128)!=self.field('PRESENTED_RECTS',128)
               or self.value('STYLE_REVISION')!=self.value('PRESENTED_STYLE_REVISION')):
            check(time.monotonic()<deadline,'render did not settle');self.resume();time.sleep(.06);self.pause()
    def key(self,*keys):
        self.resume();self.qmp.request('send-key',dict(keys=[dict(type='qcode',data=k) for k in keys],**{'hold-time':40}));self.settle()
    def move(self,x,y):
        d=self.descriptor();self.resume()
        coords=[(v*32767+extent-2)//(extent-1) for v,extent in ((x,d[1]),(y,d[2]))]
        self.qmp.request('input-send-event',dict(events=[dict(type='abs',data=dict(axis=a,value=v)) for a,v in zip(('x','y'),coords)]))
        self.settle()
    def button(self,down):
        self.resume();self.qmp.request('input-send-event',dict(events=[dict(type='btn',data=dict(button='left',down=down))]));self.settle()
    def focus(self,index):
        d=self.descriptor();q=d[14];self.move((195+index*100+40)*q//256,d[2]-30*q//256)
        self.button(True);self.button(False)
        check(struct.unpack_from('<Q',self.windows(),2440)[0]==257+index,'taskbar focus did not reach requested window')
    def verify_state(self,name,scale,colors,sequence=None,text=None):
        self.settle();d=self.descriptor();check(d[0]==3 and d[14:]==(scale,scale//16),'actual display scale differs')
        style=self.field('STYLE',72);check(style==theme_bytes(colors,scale),'actual whole Theme differs')
        atlas=struct.unpack('<9Q',self.field('FONT',72));check(atlas[0]==d[8] and atlas[1]==d[9] and atlas[3]==scale//16,'Atlas stale after remap')
        check(self.pte(self.roots[3],0x70001000)&0x800000000000001f==0x8000000000000005,'descriptor lost RO/NX/WB')
        check(self.pte(self.roots[4],0x70001000)&~0x60==self.pte(self.roots[3],0x70001000)&~0x60,'input descriptor differs')
        from tests.run_desktop_qemu import validate_font_aperture
        aperture=validate_font_aperture(self.roots[3],d[8],d[9],self.pte)
        actual=self.physical(self.pte(self.roots[3],d[8])&storage.MASK,d[9],'actual selected atlas')
        check(hashlib.sha256(actual).hexdigest()==sha(ROOT/f'assets/fonts/dong-cjk-sc-{scale//16}.dgfont'),'actual selected atlas bytes differ')
        for pid in (0,1,2,4):
            for off in (0,0x400000,0x7ff000):check(self.pte(self.roots[pid],d[8]+off)==0,'font aperture leaked to another service')
        win=self.windows()
        for i in range(4):
            l,t,r,b=rect(win,i);border=(24*scale+128)//256
            check(0<=l<r<=d[1] and 0<=t<b<=d[2] and (r-l+border)*(b-t+border)<=524288,'runtime layout/cache capacity exceeded')
        if text is not None:check(self.value('TEXT_SIZE')==len(text) and self.field('TEXT',len(text))==text,'editor contents changed during style update')
        seq=self.value('PREF_SEQUENCE','desktop.apps')
        if sequence is not None:check(seq==sequence,'loaded durable sequence differs')
        # Compare actual UC GOP against independently expected palette at plain
        # background, taskbar, cursor, and Settings body, not another RAM cache.
        coords=[(0,d[2]//2,colors[0]),(5,5,colors[1]),((175*scale+128)//256,d[2]-(45*scale+128)//256,colors[1])]
        px=lambda n:(n*scale+128)//256
        pointer=struct.unpack_from('<2q',win,2464)
        if 0<=pointer[0]<d[1] and 0<=pointer[1]<d[2]:coords.append((*pointer,colors[2]))
        if struct.unpack_from('<Q',win,2440)[0]==260:
            l,t,r,b=rect(win,3);coords.append((r-px(4),t+px(40),colors[1]))
        pixels=[]
        for x,y,color in coords:
            value=struct.unpack('<I',self.physical(self.boot[8]+(y*d[3]+x)*4,4,'actual GOP palette pixel'))[0]&0xffffff
            expected=color&0xffffff
            if d[4]==0:expected=((expected&255)<<16)|(expected&0xff00)|(expected>>16)
            check(value==expected,f'actual GOP palette differs at {(x,y)}: {value:06x}!={expected:06x}')
            pixels.append(dict(x=x,y=y,actual=value,expected=expected))
        ppm=self.state/(name+'.ppm');self.qmp.request('screendump',dict(filename=str(ppm.resolve())))
        from PIL import Image
        Image.open(ppm).save(self.state/(name+'.png'))
        item=dict(name=name,scale_q8=scale,font_pixels=scale//16,font_sha256=hashlib.sha256(actual).hexdigest(),
                  font_aperture=aperture,theme_hex=style.hex(),sequence=seq,slot=self.value('PREF_SLOT','desktop.apps'),
                  status=self.value('PREF_STATUS','desktop.apps'),gop_pixels=pixels,
                  font_switches=self.kval('user.desktop','FONT_SWITCHES'),owned_frames=self.kval('user.memory','FRAME_COUNT'),
                  windows_sha256=hashlib.sha256(win).hexdigest(),screenshot=name+'.png')
        self.evidence.setdefault('states',[]).append(item);return item
    def switch(self,key,scale,colors,text):
        old=self.windows();revision=self.value('STYLE_REVISION');frames=self.kval('user.memory','FRAME_COUNT')
        meta=self.kernel(self.ksym('user.memory','META'),5*32,'private page-table metadata before')
        switched=self.kval('user.desktop','FONT_SWITCHES');d=self.descriptor()
        domain=struct.unpack('<14Q',self.kernel(self.ksym('smp.runtime','DOMAIN'),112,'TLB domain before'))
        self.key(key);new=self.windows()
        check(self.value('STYLE_REVISION')==revision+1,'key did not apply one style transaction')
        check(old[2304:2448]==new[2304:2448],'DPI changed z order/focus/count')
        for i in range(4):
            check(old[i*144:i*144+40]==new[i*144:i*144+40] and old[i*144+136:i*144+144]==new[i*144+136:i*144+144],'DPI changed window ownership or visibility')
        check(struct.unpack_from('<2Q',new,2448)==(0,0),'DPI retained drag capture')
        after=struct.unpack('<14Q',self.kernel(self.ksym('smp.runtime','DOMAIN'),112,'TLB domain after'))
        delta=1 if d[14]!=scale else 0
        check(self.kval('user.desktop','FONT_SWITCHES')==switched+delta,'font switch count differs')
        check(self.kval('user.memory','FRAME_COUNT')==frames,'DPI allocated RAM')
        check(self.kernel(self.ksym('user.memory','META'),5*32,'private page-table metadata after')==meta,'DPI consumed page-table pool')
        # Domain: ready,pending,cpus,count,mailboxes,ops,epoch,broadcasts,
        # sent,acks,invalidations,full_flushes,probes,failures.
        check(after[0]==1 and after[1]==0 and after[3]==4 and after[-1]==0,'TLB transaction pending/failed')
        check(after[7]-domain[7]==delta and after[8]-domain[8]==3*delta and after[9]-domain[9]==3*delta and after[11]-domain[11]==delta,'DPI did not use one acknowledged four-CPU TLB transaction')
        return self.verify_state(f'style-{revision+1:02d}',scale,colors,text=text)
    def measure_drag(self):
        d=self.descriptor();check(d[14]==512,'runtime FPS gate requires switched 200%')
        r=rect(self.windows(),3);self.move(r[0]+160,r[1]+56);self.button(True)
        start=self.kval('user.desktop','FRAMES');initial=self.value('FRAME_COUNT')
        pointer=struct.unpack_from('<2q',self.windows(),2464)
        self.resume();clock=time.perf_counter();late=0
        for step in range(120):
            delay=clock+(step+1)/60-time.perf_counter()
            if delay>0:time.sleep(delay)
            elif -delay>1/60:late+=1
            x=pointer[0]-step-1;value=(x*32767+d[1]-2)//(d[1]-1)
            self.qmp.request('input-send-event',dict(events=[dict(type='abs',data=dict(axis='x',value=value))]))
        elapsed=time.perf_counter()-clock;time.sleep(.1);self.pause()
        count=self.kval('user.desktop','FRAMES')-start;end=self.value('FRAME_COUNT')
        check(count==120 and end-initial==120,'runtime drag did not present exactly120 input frames')
        completed=struct.unpack('<256Q',self.field('FRAME_COMPLETED',2048))
        durations=struct.unpack('<256Q',self.field('FRAME_TIMES',2048))
        times=[completed[i%256] for i in range(initial,end)]
        work=[durations[i%256] for i in range(initial,end)]
        check(all(a<b for a,b in zip(times,times[1:])),'nonmonotonic actual completion times')
        fps=119*d[10]/(times[-1]-times[0]);maximum=max(work)/d[10]
        perf=dict(scale_percent=200,presentations=count,completion_intervals=119,actual_fps=fps,
                  maximum_frame_seconds=maximum,host_elapsed_seconds=elapsed,host_late_requests=late,
                  tsc_hz=d[10],completion_tsc=times,composition_ticks=work,release_frame_excluded=True)
        self.evidence['runtime_drag_performance']=perf
        check(59<=fps<=61 and maximum<=1/60 and late==0,'runtime 200%60Hz gate failed')
        self.button(False);return perf
    def close(self):
        if self.qmp:
            try:self.qmp.request('quit')
            except Exception:pass
            self.qmp.close()
        if self.process:
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
        if self.uart:self.uart.close()
        if hasattr(self,'reader'):self.reader.join(timeout=2)
        if hasattr(self,'stderr'):self.stderr.close()
        storage.write_json(self.state/'physical-manifest.json',self.chunks)
        storage.write_json(self.state/'guest.json',self.evidence)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--reuse-esp',required=True,type=Path);args=parser.parse_args()
    esp=args.reuse_esp.resolve();state=ROOT/'build/test/p7-settings/qemu'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
    inputs={str(Path(__file__).resolve()):sha(__file__)}
    for name in ('tests/run_desktop_qemu.py','tests/desktop_preferences_oracle.py'):
        inputs[str(ROOT/name)]=sha(ROOT/name)
    result=dict(passed=False,runner_sha256=sha(__file__),runner_inputs=inputs,boots=[]);guest=None
    description=json.loads((esp.parent/'build-inputs.json').read_text());sources=description['source_sha256']
    def unchanged():return all(sha(p)==v for p,v in inputs.items()) and all(sha(ROOT/p)==v for p,v in sources.items())
    try:
        check(description['runtime_level']==7 and description['source_unchanged'] and unchanged(),'build/source identity differs')
        for p,v in description['artifacts'].items():check(sha(Path(p) if Path(p).is_absolute() else esp.parent/p)==v,'build artifact changed')
        disk=state/'saved.img';create(disk,64)
        def start(name,image,readonly=False):
            g=Guest(esp,image,state/name,readonly);result['boots'].append(str(g.state));return g
        guest=start('interactive',disk);guest.verify_state('default',256,DARK,0)
        check(b'DONGOS_P7_SETTINGS_DEFAULT' in guest.raw,'default marker missing')
        guest.focus(2)
        for k in ('a','b','c'):guest.key(k)
        guest.key('ctrl','s');guest.wait(b'DONGOS_EDITOR_SAVED',15)
        guest.focus(3)
        for q in (320,384,448,512,256):guest.switch('equal',q,DARK,b'abc')
        guest.switch('minus',512,DARK,b'abc')
        # At 200%, physical y+56 belongs to the title bar, beyond the old32px.
        r=rect(guest.windows(),3);guest.move(r[0]+160,r[1]+56);guest.button(True)
        guest.move(r[0]+140,r[1]+46);guest.button(False)
        check(rect(guest.windows(),3)==tuple(v+d for v,d in zip(r,(-20,-10,-20,-10))),'200% title hit testing did not scale')
        result['scaled_title_drag_verified']=True
        guest.switch('equal',256,DARK,b'abc');guest.switch('equal',320,DARK,b'abc');guest.switch('equal',384,DARK,b'abc')
        guest.switch('t',384,LIGHT,b'abc');guest.key('s');guest.wait(b'DONGOS_P7_SETTINGS_SAVED',15)
        guest.verify_state('saved-older-light150',384,LIGHT,1,b'abc')
        guest.switch('t',384,DARK,b'abc');guest.switch('equal',448,DARK,b'abc');guest.switch('equal',512,DARK,b'abc')
        guest.key('s');guest.verify_state('saved-newer-dark200',512,DARK,2,b'abc')
        guest.switch('t',512,LIGHT,b'abc');guest.switch('minus',448,LIGHT,b'abc');guest.key('r')
        guest.verify_state('r-restored-dark200',512,DARK,2,b'abc')
        result['runtime_drag_performance']=guest.measure_drag();guest.close();guest=None
        result['editor_disk']=storage.check_disk(disk,raw_name=b'NOTE    TXT',payload=b'abc')
        saved=oracle.inspect_disk(disk);storage.write_json(state/'saved-disk.json',saved)
        check([s['record']['sequence'] for s in saved['slots']]==[1,2] and saved['selection']['slot']==1,'actual durable records differ')
        check(bytes.fromhex(saved['slots'][0]['record_hex'])[32:104]==theme_bytes(LIGHT,384) and bytes.fromhex(saved['slots'][1]['record_hex'])[32:104]==theme_bytes(DARK,512),'disk theme bytes differ')
        digest=sha(disk)
        guest=start('same-disk-reboot',disk);guest.verify_state('restored',512,DARK,2)
        check(b'DONGOS_P7_SETTINGS_LOADED' in guest.raw,'reboot did not load persisted preference');guest.close();guest=None
        check(sha(disk)==digest,'startup rewrote the saved disk')
        bad=state/'newest-damaged.img';storage.write_json(state/'corrupt-newest.json',oracle.corrupt_cfg_byte(disk,1,destination=bad));before_bad=sha(bad)
        guest=start('damaged-newest-reboot',bad);guest.verify_state('older-restored',384,LIGHT,1)
        check(b'DONGOS_P7_SETTINGS_LOADED' in guest.raw,'valid older preference not loaded');guest.close();guest=None
        check(sha(bad)==before_bad,'fallback rewrote damaged configuration')
        both=state/'both-damaged.img';storage.write_json(state/'corrupt-older.json',oracle.corrupt_cfg_byte(bad,0,destination=both));before_both=sha(both)
        guest=start('both-damaged-reboot',both);guest.verify_state('defaults',256,DARK,0)
        check(b'DONGOS_P7_SETTINGS_DEFAULT' in guest.raw,'invalid pair did not use defaults');guest.close();guest=None
        check(sha(both)==before_both,'default startup rewrote bad records')
        guest=start('readonly-save-failure',disk,True);guest.verify_state('loaded',512,DARK,2);guest.focus(3)
        guest.switch('t',512,LIGHT,b'');guest.key('s');guest.wait(b'DONGOS_P7_SETTINGS_SAVE_FAILED',15)
        guest.verify_state('failed-save-keeps-appearance',512,LIGHT,2)
        check(guest.value('PREF_STATUS','desktop.apps')==2 and guest.value('PREF_SAVES','desktop.apps')==0,'failed write published success')
        guest.close();guest=None;check(sha(disk)==digest,'readonly failure changed saved disk')
        result.update(passed=True,actual_qemu_boots=5,all_five_runtime_scales=True,same_disk_reboot_verified=True,
                      newest_corruption_fallback_verified=True,both_corrupt_defaults_verified=True,
                      failed_save_retains_appearance=True,editor_content_preserved=True,raw_fat_and_record_oracle_verified=True)
    except Exception as exc:result['error']=f'{type(exc).__name__}: {exc}'
    finally:
        if guest:guest.close()
        result['source_unchanged']=unchanged()
        if not result['source_unchanged']:result.update(passed=False,error='source changed during verification')
        storage.write_json(state/'result.json',result)
    print('P7 settings', 'PASS' if result['passed'] else 'FAIL', state, result.get('error',''),flush=True)
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
