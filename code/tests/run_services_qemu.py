#!/usr/bin/env python3
"""Real shell/FAT/VirtIO persistence across two boots, with physical checks."""
from pathlib import Path
import argparse,hashlib,json,re,socket,struct,subprocess,sys,threading,time,uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import build as builder
from tools.make_fat32_disk import create
from tools.elf_symbols import read_elf_symbols
from tests import run_runtime_qemu as runtime
from tests import run_acpi_qemu as acpi
from lang.dongc.modules import Resolver
ROOT=builder.ROOT
KERNEL=0xffffffff80000000
MASK=0x000ffffffffff000
FIELDS=('version process_count syscalls calls replies errors last_error last_pid last_syscall completed '
        'steps shell_root fs_root block_root frames bundle_physical arena_physical start_tsc end_tsc current').split()
PAYLOAD=b'DongOS persistent shell 2026-10-17'

def write_json(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def free_port():
    s=socket.socket();s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close();return port
def symbol(module,name):return '__dg_m'+module.encode().hex()+'_g'+name.encode().hex()

def project(serial,symbols):
    start=serial.index(b'DONGOS_P5_SERVICES_START\r\n')
    stop=serial.index(b'DONGOS_P5_SERVICES_READY\r\n')+len(b'DONGOS_P5_SERVICES_READY\r\n')
    fields={}
    block=serial[start:stop]
    lines=re.findall(rb'^services_([a-z_]+)=0x([0-9a-f]{16})\r$',block,re.MULTILINE)
    if [name.decode() for name,_ in lines]!=FIELDS:raise ValueError('service report shape/order differs')
    fields={name.decode():int(value,16) for name,value in lines}
    for name,value in dict(version=1,process_count=3,errors=0,last_error=0,last_pid=1,last_syscall=255,completed=1,steps=31,current=1).items():
        if fields[name]!=value:raise ValueError('service completion failed: '+name)
    if fields['calls']!=fields['replies'] or fields['calls']<3000 or fields['syscalls']<6000 or fields['end_tsc']<=fields['start_tsc']:
        raise ValueError('nested actual service work/timing differs')
    for marker in (b'DONGOS_P5_ELF_LOADED',b'DONGOS_BLK_READY',b'DONGOS_FS_READY',b'DONGOS_SHELL_READY',b'DONGOS_SHELL_EXIT'):
        if block.count(marker)!=1:raise ValueError('missing/duplicate service marker '+repr(marker))
    old,p3=runtime.project_runtime(serial[:start]+serial[stop:])
    platform,scheduler=runtime.validate_fields(p3,'normal')
    firmware,prior=acpi.parse_report(old,symbols)
    return fields,platform,scheduler,firmware,prior

def verify(qmp,state,serial,build):
    symbols=acpi.validation_symbols(build/'kernel.elf')
    report,platform,scheduler,firmware,prior=project(serial,symbols)
    registers=qmp.request('human-monitor-command',{'command-line':'info registers'})
    (state/'registers.txt').write_text(registers)
    rip=int(re.search(r'RIP=([0-9a-fA-F]+)',registers)[1],16)
    halt=symbols['memory_activation_entry.halt']
    if rip not in (halt,halt+1) or 'HLT=1' not in registers or 'CPL=0' not in registers:
        raise ValueError('actual normal linked CPL0 HLT required')
    chunks=[]
    def physical(pa,count,role):
        if not 0<pa<1<<48 or not 0<count<=1<<20 or pa+count>1<<48:raise ValueError('unsafe physical dump')
        path=state/f'physical-{len(chunks):03d}.bin'
        qmp.request('pmemsave',{'val':pa,'size':count,'filename':str(path.resolve())})
        data=path.read_bytes()
        if len(data)!=count:raise ValueError('incomplete physical dump')
        chunks.append(dict(physical=pa,length=count,role=role,file=path.name,sha256=hashlib.sha256(data).hexdigest()))
        return data
    old=prior['hardening']['memory']['fields']
    boot=struct.unpack('<20Q',physical(old['runtime_boot_info']-acpi.HHDM,160,'BootInfo'))
    entries=acpi.read_map(physical(boot[4],boot[5],'UEFI map'),boot[6])
    def firmware_read(pa,n):
        if not acpi.acpi_range(entries,pa,n):raise ValueError('firmware escaped ACPI ownership')
        return physical(pa,n,'firmware')
    expected=acpi.reference.discover(firmware_read,boot[14])
    if firmware!=acpi.expected_report(expected):raise ValueError('firmware serial differs from original tables')
    def kernel(va,n,role):
        if not symbols['__kernel_text_start']<=va<=symbols['__kernel_bss_end']-n:raise ValueError('escaped retained kernel')
        return physical(boot[15]+va-KERNEL,n,role)
    def global_data(module,name,n):return kernel(symbols[symbol(module,name)],n,module+'.'+name)
    inventory=struct.unpack('<Q',kernel(symbols['p3_acpi_inventory'],8,'inventory pointer'))[0]
    if kernel(inventory,2456,'copied ACPI')!=acpi.inventory_bytes(expected):raise ValueError('copied ACPI mismatch')
    if kernel(symbols['runtime_platform_report'],192,'platform')!=struct.pack('<24Q',*(platform[n] for n in runtime.PLATFORM)):
        raise ValueError('physical platform report differs')
    if kernel(symbols['sched_report'],240,'scheduler')!=struct.pack('<30Q',*(scheduler[n] for n in runtime.SCHED)):
        raise ValueError('physical scheduler report differs')
    lapic=qmp.request('human-monitor-command',{'command-line':'info lapic'})
    pic=qmp.request('human-monitor-command',{'command-line':'info pic'})
    runtime.validate_controllers(lapic,pic)
    (state/'lapic.txt').write_text(lapic);(state/'pic.txt').write_text(pic)
    if global_data('user.services','INFO',160)!=struct.pack('<20Q',*(report[n] for n in FIELDS)):
        raise ValueError('physical service report differs')
    original_root=int(re.search(r'CR3=([0-9a-fA-F]+)',registers)[1],16)
    if original_root!=old['root_physical']:raise ValueError('kernel root not restored')
    roots=[report[n+'_root'] for n in ('shell','fs','block')]
    table_base=boot[15]+symbols[symbol('user.memory','TABLES')]-KERNEL
    if roots!=[table_base+i*32*4096 for i in range(3)]:raise ValueError('private roots escaped exclusive pools')
    pages={}
    def page(pa):
        if pa not in pages:pages[pa]=physical(pa,4096,'page table')
        return pages[pa]
    def pte(root,va,user=True):
        current=root
        for shift in (39,30,21,12):
            pools=[(root,32)] if user else [(original_root,128)]
            if current%4096 or not any(lo<=current<lo+n*4096 for lo,n in pools):raise ValueError('page table ownership escaped')
            value=struct.unpack_from('<Q',page(current),((va>>shift)&511)*8)[0]
            if not value&1:return value
            if user and not value&4:raise ValueError('USER ancestor absent')
            if shift==12:return value
            if value&128:raise ValueError('unexpected large leaf')
            current=value&MASK
    layout=json.loads((build/'dong_layout.json').read_text())
    types={t['full_name']:t for t in layout['types']}
    process=types['user.memory.Process']
    if process['size']!=1288 or [(x['name'],x['offset']) for x in process['fields']]!=[('ready',0),('root',8),('frame',16),('plan',216)]:
        raise ValueError('process snapshot ABI differs')
    processes=global_data('user.memory','PROCESSES',3*1288)
    owned=global_data('user.memory','FRAMES',report['frames']*24)
    frames=[struct.unpack_from('<3Q',owned,i*24) for i in range(report['frames'])]
    if len({x[0] for x in frames})!=len(frames):raise ValueError('duplicate physical RAM owner')
    for index,(pa,va,writable) in enumerate(frames):
        if va!=0xffffd00000000000+index*4096 or writable not in (0,1) or not old['arena_base']<=pa<old['arena_base']+old['arena_pages']*4096:
            raise ValueError('RAM owner escaped original held arena')
        if pte(original_root,va,False)&~0x60!=pa|0x8000000000000001|(2 if writable else 0):
            raise ValueError('owned supervisor alias lost WB/NX/W^X')
    for index,name in enumerate(('shell','fs','block')):
        item=processes[index*1288:(index+1)*1288]
        ready,root=struct.unpack_from('<2Q',item)
        bias=struct.unpack_from('<Q',item,224)[0]
        if ready!=1 or root!=roots[index]:raise ValueError('process publication differs')
        image=(build/'services'/name/'program.elf').read_bytes()
        phoff=struct.unpack_from('<Q',image,32)[0];stride,count=struct.unpack_from('<HH',image,54)
        for i in range(count):
            kind,flags,off,va,_,filesz,memsz,_=struct.unpack_from('<IIQQQQQQ',image,phoff+i*stride)
            if kind!=1:continue
            for address in range(va&~4095,(va+memsz+4095)&~4095,4096):
                entry=pte(root,bias+address)
                if entry&0x800000000000001f!=(5|(2 if flags&2 else 0)|(0 if flags&1 else 1<<63)):
                    raise ValueError('actual user ELF protection differs')
                first,last=max(address,va),min(address+4096,va+filesz)
                if flags&1 and first<last:
                    if physical((entry&MASK)+first-address,last-first,'actual user code')!=image[off+first-va:off+last-va]:
                        raise ValueError('actual executable differs from linked ELF')
        top=0x0000007ffff00000-index*0x1000000
        if pte(root,top)!=0 or pte(root,top-5*4096)!=0:raise ValueError('user stack guard mapped')
        for address in range(top-4*4096,top,4096):
            if pte(root,address)&0x800000000000001f!=0x8000000000000007:raise ValueError('user stack policy differs')
        boot_entry=pte(root,0x70000000)
        if boot_entry&0x800000000000001f!=0x8000000000000005:raise ValueError('boot capability record writable/executable')
        record=struct.unpack('<16Q',physical(boot_entry&MASK,128,'user boot capabilities'))
        if record[0]!=1 or record[1]!=index+1 or record[11]!=3:raise ValueError('boot identity differs')
    for address,a,b in ((0x50000000,0,1),(0x51000000,1,2)):
        for i in range(16):
            x,y=pte(roots[a],address+i*4096),pte(roots[b],address+i*4096)
            if x&~0x60!=y&~0x60 or x&0x800000000000001f!=0x8000000000000007:
                raise ValueError('IPC bulk channel physical/protection mismatch')
    for name in ('user_kernel_guard_low','user_kernel_guard_high'):
        if pte(original_root,symbols[name],False)!=0:raise ValueError('syscall kernel stack guard mapped')
    bars=global_data('user.devices','BARS',144)
    actual_bars=[]
    for index in range(6):
        pa,n,token=struct.unpack_from('<3Q',bars,index*24)
        if not n:continue
        for offset in range(0,n,4096):
            if pte(roots[2],0x60000000+index*0x1000000+offset)&~0x60!=(pa+offset)|0x800000000000001f:
                raise ValueError('device grant lost exact UC/USER/RW/NX mapping')
        actual_bars.append(dict(index=index,physical=pa,length=n,token=token))
    if not any(b['physical']>=1<<32 for b in actual_bars):raise ValueError('expected actual high 64bit BAR was not exercised')
    token,dma,virtual,length=struct.unpack('<4Q',global_data('user.devices','DMA_LEASE',32))
    if token!=1 or virtual!=0x68000000 or length!=131072 or dma%131072:raise ValueError('DMA lease differs')
    for offset in range(0,length,4096):
        if pte(roots[2],virtual+offset)&~0x60!=(dma+offset)|0x8000000000000007:raise ValueError('DMA backing/protection mismatch')
    header=struct.unpack('<IIQ',physical(dma+256,16,'last actual block command'))
    if header!=(4,0,0) or physical(dma+272,1,'last actual block status')!=b'\0':raise ValueError('last device FLUSH did not complete')
    pci=qmp.request('human-monitor-command',{'command-line':'info pci'});(state/'pci.txt').write_text(pci)
    write_json(state/'physical-manifest.json',chunks)
    return dict(report=report,platform=platform,scheduler=scheduler,bars=actual_bars,dma=dma,
                private_roots_verified=True,code_bytes_verified=True,stack_guards_verified=8,
                channels_verified=2,actual_flush_verified=True,raw_physical_reads=len(chunks),prior_lifecycle_passed=True)

def boot_once(esp,disk,state,commands,timeout=60):
    state.mkdir(parents=True)
    uart_port,qmp_port=free_port(),free_port()
    command=builder.qemu_command(esp,state,test=True)
    i=command.index('isa-debug-exit,iobase=0xf4,iosize=0x04');del command[i-1:i+1]
    command[command.index('-serial')+1]=f'tcp:127.0.0.1:{uart_port},server=on,wait=off'
    command+=['-cpu','max,+smep,+smap,+umip','-S','-qmp',f'tcp:127.0.0.1:{qmp_port},server=on,wait=off',
        '-drive',f'if=none,id=data,format=raw,cache=writeback,file={disk.resolve().as_posix()}',
        '-device','virtio-blk-pci,drive=data,disable-legacy=on']
    result=dict(passed=False,actual_qemu_executed=False,errors=[],command=command)
    write_json(state/'result.json',result)
    raw=bytearray();qmp=None;uart=None;process=None;started=time.monotonic()
    try:
        with (state/'stderr.log').open('wb') as stderr:
            process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=stderr)
            result['actual_qemu_executed']=True
            qmp=acpi.QMP(qmp_port,process);uart=socket.create_connection(('127.0.0.1',uart_port));uart.settimeout(.2)
            def read_uart():
                with (state/'serial.log').open('wb') as stream:
                    while process.poll() is None:
                        try:data=uart.recv(4096)
                        except socket.timeout:continue
                        except OSError:break
                        if not data:break
                        raw.extend(data);stream.write(data);stream.flush()
            thread=threading.Thread(target=read_uart,daemon=True);thread.start();qmp.request('cont')
            sent=0;cursor=0;completed=False
            while time.monotonic()-started<timeout:
                data=bytes(raw)
                if b'DONGOS_P1_KERNEL_FAIL' in data or b'PANIC' in data:raise ValueError('actual guest failure')
                if b'DONGOS_SHELL_READY' in data and sent<len(commands):
                    prompt=data.find(b'> ',cursor)
                    if prompt>=0:
                        uart.sendall(commands[sent].encode()+b'\r');cursor=len(data);sent+=1
                if b'DONGOS_P1_PASS\r\n' in data:completed=True;break
                if process.poll() is not None:raise ValueError('guest terminated before normal HLT')
                time.sleep(.01)
            if not completed:raise TimeoutError('service shell did not complete all actual commands')
            qmp.request('stop')
            result['physical']=verify(qmp,state,bytes(raw),esp.parent)
            result.update(passed=True,commands=commands,serial_bytes=len(raw),termination='Host QMP quit after actual linked normal HLT and independent physical validation.')
    except Exception as exc:result['errors'].append(f'{type(exc).__name__}: {exc}')
    finally:
        if qmp:
            try:qmp.request('quit')
            except Exception:pass
            qmp.close()
        if uart:uart.close()
        if process:
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            result['qemu_shutdown_returncode']=process.returncode
        result['elapsed_seconds']=time.monotonic()-started
        write_json(state/'result.json',result)
    print(('PASS' if result['passed'] else 'FAIL'),'P5',state.name,result['errors'],flush=True)
    return result

def check_disk(path,*,raw_name=b'PROBE   TXT',payload=PAYLOAD):
    with path.open('rb') as disk:
        boot=disk.read(512);bps=struct.unpack_from('<H',boot,11)[0];spc=boot[13]
        reserved=struct.unpack_from('<H',boot,14)[0];nfats=boot[16];fat_size=struct.unpack_from('<I',boot,36)[0]
        root=struct.unpack_from('<I',boot,44)[0];data_start=reserved+nfats*fat_size
        if bps!=512 or spc!=1 or nfats!=2:raise ValueError('independent disk geometry differs')
        disk.seek(reserved*512);fat=disk.read(fat_size*512)
        if disk.read(fat_size*512)!=fat or struct.unpack_from('<I',fat,4)[0]&0xc000000!=0xc000000:
            raise ValueError('persistent FAT mirrors/clean bit differ')
        def chain(cluster):
            seen=set();out=bytearray()
            while cluster<0xffffff8:
                if cluster<2 or cluster in seen or cluster*4>=len(fat):raise ValueError('persistent cluster chain invalid')
                seen.add(cluster);disk.seek((data_start+cluster-2)*512);out.extend(disk.read(512))
                cluster=struct.unpack_from('<I',fat,cluster*4)[0]&0xfffffff
            return bytes(out)
        directory=chain(root);entry=None
        for offset in range(0,len(directory),32):
            candidate=directory[offset:offset+32]
            if candidate[0]==0:break
            if candidate[:11]==raw_name:entry=candidate;break
        if entry is None:raise ValueError('shell-created file absent from actual disk')
        cluster=(struct.unpack_from('<H',entry,20)[0]<<16)|struct.unpack_from('<H',entry,26)[0]
        size=struct.unpack_from('<I',entry,28)[0];content=chain(cluster)[:size]
        if content!=payload:raise ValueError('persistent file bytes differ')
        return dict(name=raw_name[:8].decode().rstrip()+'.'+raw_name[8:].decode().rstrip(),size=size,sha256=hashlib.sha256(content).hexdigest(),both_fats_equal=True,clean=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--reuse-esp',type=Path);args=parser.parse_args()
    state=ROOT/'build/test/p5-storage/qemu'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
    paths=set()
    resolver_roots=[ROOT/'kernel',ROOT/'services',ROOT/'lang/examples',ROOT/'lang/std']
    for source in ('kernel/services_probe.dg','services/shell/main.dg','services/fs/service.dg','services/drivers/block_service.dg'):
        paths.update(Path(p) for p in Resolver(resolver_roots).load(ROOT/source).source_files)
    paths.update(ROOT.glob('kernel/*.asm'));paths.update(ROOT.glob('kernel/*/*.asm'));paths.update(ROOT.glob('include/*.inc'))
    paths.update(ROOT/p for p in ('boot/efi_main.asm','boot/image.asm','boot/service_bundle.asm','tools/build.py','tools/user_services.py','tools/service_bundle.py',
        'services/lib/service.ld','services/lib/syscalls.asm','lang/std/arch/x86_64.asm','kernel/linker.ld','tests/run_services_qemu.py'))
    hashes=lambda:{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    before=hashes();write_json(state/'source-before.json',before)
    esp=args.reuse_esp.resolve() if args.reuse_esp else builder.build(test=True,runtime_level=5,output=state/'build')
    disk=state/'disk.img';create(disk,64)
    results=[]
    first=boot_once(esp,disk,state/'write',['write PROBE.TXT '+PAYLOAD.decode(),'cat PROBE.TXT','ls','sync','exit'])
    results.append(first)
    persistent=None
    if first['passed']:
        persistent=check_disk(disk)
        results.append(boot_once(esp,disk,state/'reboot',['cat PROBE.TXT','ls','exit']))
        if results[-1]['passed']:
            check_disk(disk)
            serial=(state/'reboot/serial.log').read_bytes()
            if b'cat PROBE.TXT\r\n'+PAYLOAD+b'\r\n' not in serial:results[-1]['errors'].append('second boot shell did not print actual persisted bytes');results[-1]['passed']=False
    after=hashes();write_json(state/'source-after.json',after)
    passed=len(results)==2 and before==after and all(r['passed'] for r in results)
    write_json(state/'result.json',dict(passed=passed,source_unchanged=before==after,results=results,persistent=persistent))
    print('P5 actual persistence','PASS' if passed else 'FAIL',state)
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
