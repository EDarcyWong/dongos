"""Actual isolated compiler ELF boot, file I/O and same-disk fixed point."""
from pathlib import Path
import argparse,hashlib,json,os,re,socket,struct,subprocess,sys,threading,time,uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests import run_services_qemu as p5
from tools import build as builder
from tools.make_fat32_disk import create
from tools.compiler_job import source_blob
ROOT=builder.ROOT

def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def source_names(rows):
    result={str(p).replace('\\','/'):v for p,v in rows.items()}
    if len(result)!=len(rows):raise ValueError('duplicate normalized source path')
    for name in result:
        if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('unsafe source path')
    return result

def frozen_changes(groups):
    return {group:[str(p) for p,digest in rows.items() if not p.is_file() or file_hash(p)!=digest]
            for group,rows in groups.items()}

def verify_frozen(groups):
    changed={k:v for k,v in frozen_changes(groups).items() if v}
    if changed:raise ValueError('frozen compiler inputs changed: '+json.dumps(changed))

def load_inputs(source_root,esp,fixture):
    """Bind the host fixture and the actual boot/observation files to one source."""
    source_root=Path(source_root).resolve();esp=Path(esp).resolve();fixture=Path(fixture).resolve();build=esp.parent
    receipt_path=fixture/'receipt.json';build_path=build/'build-inputs.json'
    receipt_bytes=receipt_path.read_bytes();build_bytes=build_path.read_bytes()
    receipt=json.loads(receipt_bytes);build_receipt=json.loads(build_bytes)
    blob=(fixture/'sources.bin').read_bytes();image=(fixture/'stage1.elf').read_bytes()
    if (receipt.get('source_stable') is not True or receipt.get('exact_fixedpoint') is not True
        or hashlib.sha256(blob).hexdigest()!=receipt['blob_sha256']
        or hashlib.sha256(image).hexdigest()!=receipt['elf_sha256'] or receipt.get('elf_bytes')!=len(image)):
        raise ValueError('host fixture changed or fixed point unproven')
    if (build_receipt.get('source_unchanged') is not True or build_receipt.get('compiler_job') is not True
        or build_receipt.get('runtime_level')!=5):raise ValueError('compiler profile build not stable')
    expected=source_names(build_receipt['source_sha256'])
    before={p:file_hash(source_root/p) for p in expected}
    if before!=expected:raise ValueError('current source does not match compiler profile build')
    canonical,sources=source_blob(source_root);sources=source_names(sources)
    if (blob!=canonical or source_names(receipt['sources'])!=sources
        or any(before.get(p)!=v for p,v in sources.items())):
        raise ValueError('host and guest compiler source revisions differ')
    # build.py records absolute paths for exactly the generated boot payloads.
    artifacts={Path(p).resolve():v for p,v in build_receipt['artifacts'].items()}
    required={build/'kernel.bin',build/'kernel.elf',esp/'DONGOS.IMG',esp/'EFI/BOOT/BOOTX64.EFI',esp/'SERVICES.BIN'}
    if not required.issubset(artifacts) or any(not p.is_relative_to(build) for p in artifacts):
        raise ValueError('compiler profile artifact manifest incomplete or outside build')
    if any(not p.is_file() or file_hash(p)!=digest for p,digest in artifacts.items()):
        raise ValueError('compiler profile artifact differs from build manifest')
    profile=[build/'dong_layout.json',*[build/'services'/n/'program.elf' for n in ('shell','fs','block')]]
    fixtures={receipt_path:hashlib.sha256(receipt_bytes).hexdigest(),fixture/'sources.bin':hashlib.sha256(blob).hexdigest(),
        fixture/'stage1.elf':hashlib.sha256(image).hexdigest()}
    if (fixture/'stage2.elf').exists():
        if (fixture/'stage2.elf').read_bytes()!=image:raise ValueError('host fixed point ELF differs')
        fixtures[fixture/'stage2.elf']=hashlib.sha256(image).hexdigest()
    harness=[ROOT/p for p in ('tests/run_compiler_job_qemu.py','tests/run_services_qemu.py',
        'tests/run_runtime_qemu.py','tests/run_acpi_qemu.py','tools/build.py','tools/compiler_job.py','tools/make_fat32_disk.py')]
    groups=dict(sources={source_root/p:v for p,v in before.items()},harness={p:file_hash(p) for p in harness},
        fixture=fixtures,profile=artifacts|{p:file_hash(p) for p in profile}|{build_path:hashlib.sha256(build_bytes).hexdigest()})
    verify_frozen(groups)
    return blob,image,before,groups

def compiler_context(registers,ready,root,expected_root,current):
    # RUNNING is published before dispatch switches CURRENT and returns via
    # SYSRET. A stopped kernel/controller is not a live compiler observation.
    if 'CPL=3' not in registers:return False
    match=re.search(r'CR3=([0-9a-fA-F]+)',registers)
    if match is None:raise ValueError('live compiler register report missing CR3')
    if int(match[1],16)!=root:return False
    if ready!=1 or root!=expected_root or current!=3:raise ValueError('live compiler is not current published slot3')
    return True

def seed_disk(path,blob,image):
    g=create(path,64);fat=bytearray(g['fat_sectors']*512)
    with path.open('r+b') as f:
        f.seek(32*512);fat[:]=f.read(len(fat));f.seek(g['data_start']*512);directory=bytearray(f.read(512))
        cluster=4
        for row,(name,data) in enumerate([(b'SOURCES BIN',blob),(b'SEED    ELF',image),(b'STAGE1  ELF',b''),(b'STAGE2  ELF',b'')],1):
            entry=memoryview(directory)[row*32:(row+1)*32];entry[:11]=name;entry[11]=0x20
            start=cluster if data else 0;struct.pack_into('<H',entry,20,start>>16);struct.pack_into('<H',entry,26,start&65535);struct.pack_into('<I',entry,28,len(data))
            for at in range(0,len(data),512):
                last=at+512>=len(data);struct.pack_into('<I',fat,cluster*4,0xfffffff if last else cluster+1)
                f.seek((g['data_start']+cluster-2)*512);f.write(data[at:at+512].ljust(512,b'\0'));cluster+=1
        for sector in [32,32+g['fat_sectors']]:f.seek(sector*512);f.write(fat)
        f.seek(g['data_start']*512);f.write(directory);f.flush();os.fsync(f.fileno())

def compiler_project(serial,symbols):
    start=serial.index(b'DONGOS_P5_SERVICES_START\r\n');stop=serial.index(b'DONGOS_P5_SERVICES_READY\r\n')+len(b'DONGOS_P5_SERVICES_READY\r\n')
    block=serial[start:stop];lines=re.findall(rb'^services_([a-z_]+)=0x([0-9a-f]{16})\r$',block,re.M)
    if [n.decode() for n,_ in lines]!=p5.FIELDS:raise ValueError('compiler service report shape/order differs')
    fields={n.decode():int(v,16) for n,v in lines}
    for name,value in dict(version=1,process_count=3,errors=0,last_error=0,last_pid=1,last_syscall=255,completed=1,steps=31,current=1).items():
        if fields[name]!=value:raise ValueError('compiler service completion failed: '+name)
    if fields['calls']!=fields['replies'] or fields['calls']==0 or fields['syscalls']<2*fields['calls'] or fields['frames']>16384 or fields['end_tsc']<=fields['start_tsc']:
        raise ValueError('compiler service work/budget differs')
    for marker in [b'DONGOS_P5_ELF_LOADED',b'DONGOS_BLK_READY',b'DONGOS_FS_READY',b'DONGOS_L3_RUN\r\n',b'DONGOS_L3_EXIT\r\n']:
        if block.count(marker)!=1:raise ValueError('missing/duplicate compiler marker '+repr(marker))
    if b'DONGOS_L3_FAILED' in block or block.count(b'DONGOS_L3_RESULT 0x0000000000000000 0x0000000000000003 0x0000000000000000 0x0000000000000000\r\n')!=1:
        raise ValueError('pure compiler failed')
    inputs=re.findall(rb'DONGOS_L3_INPUT (SEED|STAGE1)\.ELF\r\n',block)
    durable=re.findall(rb'DONGOS_L3_DURABLE (STAGE[12])\.ELF 0x([0-9a-f]{16})\r\n',block)
    if len(inputs)!=1 or len(durable)!=1 or durable[0][0]!=(b'STAGE1' if inputs[0]==b'SEED' else b'STAGE2') or not 4096<=int(durable[0][1],16)<=2097152:
        raise ValueError('compiler artifact completion differs')
    if block.count(b'DONGOS_L3_EXACT_FIXEDPOINT\r\n')!=int(inputs[0]==b'STAGE1'):raise ValueError('in-guest exact comparison missing')
    old,p3=p5.runtime.project_runtime(serial[:start]+serial[stop:]);platform,scheduler=p5.runtime.validate_fields(p3,'normal')
    firmware,prior=p5.acpi.parse_report(old,symbols,production=True)
    return fields,platform,scheduler,firmware,prior

def live_job(qmp,state,serial,build,blob,image):
    """Return None during staging; otherwise prove the actual live user mappings."""
    symbols=p5.acpi.validation_symbols(build/'kernel.elf');chunks=[]
    def physical(pa,n,role):
        if not 0<pa<1<<48 or not 0<n<=1<<20 or n>(1<<48)-pa:raise ValueError('unsafe live dump')
        path=state/f'live-{len(chunks):03d}.bin';qmp.request('pmemsave',{'val':pa,'size':n,'filename':str(path.resolve())});data=path.read_bytes()
        if len(data)!=n:raise ValueError('short live dump')
        chunks.append(dict(physical=pa,length=n,role=role,file=path.name,sha256=hashlib.sha256(data).hexdigest()));return data
    prefix=serial[:serial.index(b'DONGOS_P5_SERVICES_START')]
    # A running boot has no final PASS yet. Use its exact completed-stage
    # locators for this snapshot; final verification validates the full actual
    # prior lifecycle and the same physical BootInfo after normal completion.
    def locator(name):
        rows=re.findall(rb'^memory_'+name.encode()+rb'=0x([0-9a-f]{16})\r$',prefix,re.M)
        if len(rows)!=1:raise ValueError('missing/duplicate live boot locator')
        return int(rows[0],16)
    if prefix.count(b'DONGOS_P2_MEMORY_READY\r\n')!=1 or prefix.count(b'DONGOS_P3_THREADS_READY\r\n')!=1:raise ValueError('live prior stages incomplete')
    boot_va=locator('runtime_boot_info');kernel_root=locator('root_physical')
    if not p5.acpi.HHDM<boot_va<p5.acpi.HHDM+(1<<48) or kernel_root%4096:raise ValueError('live boot locator range differs')
    boot=struct.unpack('<20Q',physical(boot_va-p5.acpi.HHDM,160,'BootInfo'))
    def global_data(module,name,n):
        va=symbols[p5.symbol(module,name)]
        if not symbols['__kernel_text_start']<=va<=symbols['__kernel_bss_end']-n:raise ValueError('live global escaped kernel')
        return physical(boot[15]+va-p5.KERNEL,n,module+'.'+name)
    if global_data('user.compiler_job','RUNNING',1)!=b'\1':return None
    count=struct.unpack('<Q',global_data('user.memory','FRAME_COUNT',8))[0]
    limit=struct.unpack('<Q',global_data('user.memory','EXTENDED_LIMIT',8))[0]
    extended=struct.unpack('<Q',global_data('user.memory','EXTENDED',8))[0]
    arena_pa,arena_bytes=struct.unpack_from('<2Q',global_data('boot.service_memory','PLAN',48),32)
    roots=struct.unpack('<16Q',global_data('user.memory','DYNAMIC_PHYSICAL',128))
    process=global_data('user.memory','PROCESSES',4*1288);ready,root=struct.unpack_from('<2Q',process,3*1288)
    registers=qmp.request('human-monitor-command',{'command-line':'info registers'});(state/'live-registers.txt').write_text(registers)
    if not compiler_context(registers,ready,root,roots[3],struct.unpack_from('<Q',global_data('user.services','CURRENT',8))[0]):return None
    cache={}
    def pte(r,va,pool_pages):
        current=r
        for shift in [39,30,21,12]:
            if current%4096 or not r<=current<r+pool_pages*4096:raise ValueError('live table escaped its exclusive pool')
            if current not in cache:cache[current]=physical(current,4096,'live page table')
            v=struct.unpack_from('<Q',cache[current],((va>>shift)&511)*8)[0]
            if not v&1:return v
            if r!=kernel_root and not v&4:raise ValueError('live USER ancestor absent')
            if shift==12:return v
            if v&128:raise ValueError('live large mapping')
            current=v&p5.MASK
    frames=p5.read_owned_frames(count,extended,limit,arena_pa,arena_bytes//4096,physical,lambda va:pte(kernel_root,va,128))
    owners={pa:(va,w) for pa,va,w in frames}
    top=0x7ffff00000-3*0x1000000
    for va in [top,top-17*4096,0x20000000-4096,0x23800000]:
        if pte(root,va,128)!=0:raise ValueError('compiler stack/arena guard mapped')
    def owned(va,flags):
        v=pte(root,va,128)
        if v&0x800000000000001f!=flags or v&p5.MASK not in owners:raise ValueError('live owned mapping/protection differs')
        return v&p5.MASK
    stacks={owned(va,0x8000000000000007) for va in range(top-16*4096,top,4096)}
    if len(stacks)!=16:raise ValueError('compiler stack contains aliases')
    meta={owned(0x70000000,0x8000000000000007)}
    pages=[owned(va,0x8000000000000007) for va in range(0x20000000,0x23800000,4096)]
    if len(set(pages))!=14336:raise ValueError('compiler workspace contains aliases')
    req=struct.unpack('<6Q',global_data('user.compiler_job','REQUEST',48));source,source_n=req[2:4]
    if source_n!=len(blob):raise ValueError('live source length differs')
    got=bytearray();sources=set();controller_root=struct.unpack_from('<Q',process,8)[0]
    at=0
    while at<len(blob):
        va=source+at;n=min(4096-(va&4095),len(blob)-at);pa=owned(va,0x8000000000000005)
        original=pte(controller_root,va,32)
        if original&p5.MASK!=pa or original&0x800000000000001f!=0x8000000000000007:raise ValueError('compiler source is not the blocked controller readonly loan')
        sources.add(pa)
        got+=physical(pa+(va&4095),n,'actual readonly compiler source');at+=n
    if bytes(got)!=blob:raise ValueError('live compiler did not read the frozen filesystem source')
    ph=struct.unpack_from('<Q',image,32)[0];stride,nph=struct.unpack_from('<HH',image,54)
    images=set();rx=set();rw=set();image_pages=0
    for i in range(nph):
        kind,flags,off,va,_,fs,ms,_=struct.unpack_from('<IIQQQQQQ',image,ph+i*stride)
        if kind!=1:continue
        for address in range(va&~4095,(va+ms+4095)&~4095,4096):
            pa=owned(address,5 if flags&1 else 0x8000000000000007)
            image_pages+=1;images.add(pa);(rx if flags&1 else rw).add(pa)
            alias,w=owners[pa]
            if flags&1 and (w!=0 or pte(kernel_root,alias,128)&~0x60!=pa|0x8000000000000001):raise ValueError('compiler code has writable kernel alias')
            first,last=max(address,va),min(address+4096,va+fs)
            if first<last and physical(pa+first-address,last-first,'actual compiler ELF')!=image[off+first-va:off+last-va]:raise ValueError('live compiler code/data differs from persisted ELF')
    if len(images)!=image_pages or rx&rw:raise ValueError('compiler ELF has physical page aliases or RX/RW overlap')
    sets=[set(pages),stacks,meta,sources,images]
    for i in range(len(sets)):
        for j in range(i):
            if sets[i]&sets[j]:raise ValueError('compiler arena/stack/meta/source/ELF physical regions overlap')
    layout={t['full_name']:t for t in json.loads((build/'dong_layout.json').read_text())['types']}
    state_layout=layout['user.services.State'];handle_layout=layout['ipc.handles.Table']
    if state_layout['size']!=1336 or handle_layout['size']!=1296:raise ValueError('compiler handle ABI differs')
    state_bytes=global_data('user.services','STATES',4*1336)
    empty_table=struct.pack('<162Q',0,0,*([1,0,0,0,0]*32))
    if state_bytes[3*1336:3*1336+1296]!=empty_table:raise ValueError('compiler has a hidden kernel handle')
    if struct.unpack_from('<Q',state_bytes,1320)[0]!=7:raise ValueError('source owner was not blocked')
    boot3=struct.unpack('<16Q',global_data('user.services','BOOTS',4*128)[3*128:])
    if boot3!=(1,0,0,0,0,0,0,65536,0,0,0,3,0,0,0,0):raise ValueError('compiler inherited boot authority')
    result=dict(managed_frames=count,limit=limit,arena_pages=14336,stack_pages=16,guards=4,source_sha256=hashlib.sha256(blob).hexdigest(),image_sha256=hashlib.sha256(image).hexdigest(),source_readonly=True,code_wx=True,no_capabilities=True)
    p5.write_json(state/'live-physical-manifest.json',chunks);p5.write_json(state/'live-result.json',result);return result

def final_job(qmp,state,serial,build,expected_bytes):
    symbols=p5.acpi.validation_symbols(build/'kernel.elf');chunks=[]
    def physical(pa,n,role):
        if not 0<pa<1<<48 or not 0<n<=1<<20 or n>(1<<48)-pa:raise ValueError('unsafe final dump')
        path=state/f'final-{len(chunks):03d}.bin';qmp.request('pmemsave',{'val':pa,'size':n,'filename':str(path.resolve())});data=path.read_bytes()
        if len(data)!=n:raise ValueError('short final dump')
        chunks.append(dict(physical=pa,length=n,role=role,file=path.name,sha256=hashlib.sha256(data).hexdigest()));return data
    _,_,_,_,prior=compiler_project(serial,symbols)
    boot=struct.unpack('<20Q',physical(prior['hardening']['memory']['fields']['runtime_boot_info']-p5.acpi.HHDM,160,'BootInfo'))
    def global_data(module,name,n):
        va=symbols[p5.symbol(module,name)]
        if not symbols['__kernel_text_start']<=va<=symbols['__kernel_bss_end']-n:raise ValueError('final global escaped kernel')
        return physical(boot[15]+va-p5.KERNEL,n,module+'.'+name)
    if global_data('user.compiler_job','RUNNING',1)!=b'\0' or global_data('user.compiler_job','FAILED',1)!=b'\0':raise ValueError('compiler job was not retired cleanly')
    if struct.unpack('<Q',global_data('user.services','ACTIVE',8))[0]!=3 or struct.unpack('<Q',global_data('user.compiler_job','RUNS',8))[0]!=1:raise ValueError('compiler slot activation was not restored')
    p=global_data('user.memory','PROCESSES',4*1288)
    if struct.unpack_from('<2Q',p,3*1288)!=(0,0):raise ValueError('compiler Process remained published')
    if global_data('user.memory','SPACES',4*64)[3*64:]!=bytes(64):raise ValueError('compiler Space remained published')
    root=struct.unpack_from('<Q',global_data('user.memory','DYNAMIC_PHYSICAL',128),3*8)[0]
    if physical(root,128*4096,'retired compiler tables')!=bytes(128*4096):raise ValueError('retired compiler translations remain')
    states=global_data('user.services','STATES',4*1336)
    if struct.unpack_from('<Q',states,1320)[0]!=0:raise ValueError('controller wait state was not restored')
    if global_data('user.compiler_job','REQUEST',48)!=bytes(48):raise ValueError('compiler source loan metadata retained')
    last=struct.unpack('<9Q',global_data('user.compiler_job','LAST',72))
    if last[:6]!=(0,3,0,0,expected_bytes,8388608):raise ValueError('retired compiler result differs')
    p5.write_json(state/'final-physical-manifest.json',chunks)
    return dict(slot_retired=True,tables_cleared=True,controller_resumed=True,source_loan_withdrawn=True)

def failure_snapshot(qmp,state,serial,build):
    """Capture linked globals physically, independent of the current user CR3."""
    (state/'failure-registers.txt').write_text(qmp.request('human-monitor-command',{'command-line':'info registers'}))
    symbols=p5.acpi.validation_symbols(build/'kernel.elf');chunks=[]
    def physical(pa,n,role,name):
        if not 0<pa<1<<48 or not 0<n<=1<<20 or n>(1<<48)-pa:raise ValueError('unsafe failure dump')
        path=state/name;qmp.request('pmemsave',{'val':pa,'size':n,'filename':str(path.resolve())});data=path.read_bytes()
        if len(data)!=n:raise ValueError('short failure dump')
        chunks.append(dict(physical=pa,length=n,role=role,file=path.name,sha256=hashlib.sha256(data).hexdigest()));return data
    try:
        rows=re.findall(rb'^memory_runtime_boot_info=0x([0-9a-f]{16})\r$',serial,re.M)
        if len(rows)!=1:raise ValueError('missing/duplicate failure BootInfo locator')
        boot_va=int(rows[0],16)
        if not p5.acpi.HHDM<boot_va<p5.acpi.HHDM+(1<<48):raise ValueError('unsafe failure BootInfo locator')
        boot=struct.unpack('<20Q',physical(boot_va-p5.acpi.HHDM,160,'BootInfo','failure-BootInfo.bin'))
        for module,name,n in [('user.services','INFO',160),('user.services','STATES',4*1336),
            ('user.services','CURRENT',8),('user.services','ACTIVE',8),('user.services','BOOTS',4*128),
            ('user.compiler_job','RUNNING',1),('user.compiler_job','FAILED',1),('user.compiler_job','RUNS',8),
            ('user.compiler_job','LAST',72),('user.compiler_job','REQUEST',48),
            ('user.memory','PROCESSES',4*1288),('user.memory','SPACES',4*64),
            ('user.memory','DYNAMIC_PHYSICAL',128),('user.memory','FRAME_COUNT',8),
            ('user.memory','EXTENDED',8),('user.memory','EXTENDED_LIMIT',8)]:
            va=symbols[p5.symbol(module,name)]
            if not symbols['__kernel_text_start']<=va<=symbols['__kernel_bss_end']-n:raise ValueError('failure global escaped kernel')
            physical(boot[15]+va-p5.KERNEL,n,module+'.'+name,'failure-'+module+'-'+name+'.bin')
    finally:
        p5.write_json(state/'failure-physical-manifest.json',chunks)


def boot(esp,disk,state,blob,image,timeout=3600):
    state.mkdir(parents=True);up,qp=p5.free_port(),p5.free_port();command=builder.qemu_command(esp,state,test=True)
    # The compiler profile is deliberately an exclusive BSP job. A single CPU
    # also avoids idle AP spin consuming host TCG time during long builds.
    command[command.index('-smp')+1]='1'
    i=command.index('isa-debug-exit,iobase=0xf4,iosize=0x04');del command[i-1:i+1]
    command[command.index('-serial')+1]=f'tcp:127.0.0.1:{up},server=on,wait=off'
    command+=['-cpu','max,+smep,+smap,+umip','-S','-qmp',f'tcp:127.0.0.1:{qp},server=on,wait=off','-drive',f'if=none,id=data,format=raw,cache=writeback,file={disk.resolve().as_posix()}','-device','virtio-blk-pci,drive=data,disable-legacy=on']
    result=dict(passed=False,actual_qemu_executed=False,errors=[],command=command);raw=bytearray();qmp=uart=process=None;started=time.monotonic();next_probe=0;live=None
    try:
        with (state/'stderr.log').open('wb') as stderr:
            process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=stderr);result['actual_qemu_executed']=True
            qmp=p5.acpi.QMP(qp,process);uart=socket.create_connection(('127.0.0.1',up));uart.settimeout(.2)
            def reader():
                with (state/'serial.log').open('wb') as f:
                    while process.poll() is None:
                        try:data=uart.recv(4096)
                        except socket.timeout:continue
                        except OSError:break
                        if not data:break
                        raw.extend(data);f.write(data);f.flush()
            threading.Thread(target=reader,daemon=True).start();qmp.request('cont')
            while time.monotonic()-started<timeout:
                data=bytes(raw)
                if b'DONGOS_P1_KERNEL_FAIL' in data or b'PANIC' in data or b'DONGOS_L3_FAILED' in data:raise ValueError('actual compiler guest failure')
                if live is None and b'DONGOS_L3_RUN\r\n' in data and time.monotonic()>next_probe:
                    qmp.request('stop');live=live_job(qmp,state,data,esp.parent,blob,image);qmp.request('cont');next_probe=time.monotonic()+1
                if b'DONGOS_P1_PASS\r\n' in data:
                    if live is None:raise ValueError('no independently captured live compiler execution')
                    qmp.request('stop');old_project=p5.project;p5.project=compiler_project
                    try:result['physical']=p5.verify(qmp,state,data,esp.parent)
                    finally:p5.project=old_project
                    result['retirement']=final_job(qmp,state,data,esp.parent,len(image))
                    result.update(passed=True,live=live);break
                if process.poll() is not None:raise ValueError('guest exited before normal completion')
                time.sleep(.02)
            else:raise TimeoutError('compiler did not complete')
    except Exception as e:
        result['errors'].append(f'{type(e).__name__}: {e}')
        if qmp:
            try:
                qmp.request('stop')
                failure_snapshot(qmp,state,bytes(raw),esp.parent)
            except Exception as diagnostic:result['errors'].append('diagnostic: '+str(diagnostic))
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
        result['elapsed_seconds']=time.monotonic()-started;p5.write_json(state/'result.json',result)
    print('PASS' if result['passed'] else 'FAIL','L3',state.name,result['errors'],flush=True);return result

def main():
    a=argparse.ArgumentParser();a.add_argument('--esp',type=Path,required=True);a.add_argument('--fixture',type=Path,required=True);a.add_argument('--source-root',type=Path,default=ROOT);args=a.parse_args()
    state=ROOT/'build/test/l3-guest'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
    results=[];errors=[];before={};groups={};checks=[];blob=image=b'';passed=False
    try:
        blob,image,before,groups=load_inputs(args.source_root,args.esp,args.fixture)
        verify_frozen(groups);checks.append('before seed')
        disk=state/'disk.img';seed_disk(disk,blob,image);results.append(boot(args.esp.resolve(),disk,state/'seed',blob,image))
        verify_frozen(groups);checks.append('after seed')
        if results[0]['passed']:
            p5.check_disk(disk,raw_name=b'SOURCES BIN',payload=blob)
            p5.check_disk(disk,raw_name=b'STAGE1  ELF',payload=image)
            verify_frozen(groups);checks.append('before reboot')
            results.append(boot(args.esp.resolve(),disk,state/'reboot',blob,image))
            verify_frozen(groups);checks.append('after reboot')
            if results[-1]['passed']:
                p5.check_disk(disk,raw_name=b'SOURCES BIN',payload=blob)
                p5.check_disk(disk,raw_name=b'STAGE2  ELF',payload=image)
        passed=len(results)==2 and all(r['passed'] and r.get('actual_qemu_executed') for r in results)
    except Exception as e:
        errors.append(f'{type(e).__name__}: {e}')
    changed=frozen_changes(groups);stable={k:not v for k,v in changed.items()}
    if not groups or any(changed.values()):passed=False
    p5.write_json(state/'receipt.json',dict(passed=passed,actual_qemu_executed=any(r.get('actual_qemu_executed') for r in results),
        exact_host_guest_elf=passed,source_unchanged=stable.get('sources',False),harness_unchanged=stable.get('harness',False),
        harness={str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p):v for p,v in groups.get('harness',{}).items()},
        fixture_unchanged=stable.get('fixture',False),profile_unchanged=stable.get('profile',False),
        frozen_inputs={k:{str(p):v for p,v in rows.items()} for k,rows in groups.items()},changed_inputs=changed,input_checks=checks,
        errors=errors,source_root=str(args.source_root.resolve()),sources=before,results=results,
        blob_sha256=hashlib.sha256(blob).hexdigest(),elf_sha256=hashlib.sha256(image).hexdigest()))
    print('L3 actual guest','PASS' if passed else 'FAIL',state);return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
