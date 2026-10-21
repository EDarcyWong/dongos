#!/usr/bin/env python3
"""Observe the production BSP large-page lifecycle on a completed normal root.

Never writes guest memory/registers. --replay uses archived physical bytes only.
The lifetime finishes before AP startup; this does not test SMP large pages.
"""
from pathlib import Path
import argparse, hashlib, json, re, shutil, struct, subprocess, sys, time, uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import build as builder
from tools.elf_symbols import read_elf_symbols
from tests import run_acpi_qemu as acpi, run_services_qemu as storage

ROOT=builder.ROOT
WINDOW=0xffffa80000000000
MASK=0x000ffffffffff000
FIELDS=('version attempted complete phase steps root window physical pages order '
        'free_before free_held free_after tables_before tables_mapped tables_split tables_merged tables_after '
        'sample_first sample_last split_value replacement_value restored_value merge_value merge_error '
        'invlpg full_flush retired_tables held cr0 cr3 cr4 efer rflags pat error_code '
        'large_entry split_entry merged_entry').split()

def check(value,message):
    if not value: raise ValueError('P2 active large: '+message)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def source_hashes():
    return {p.relative_to(ROOT).as_posix():sha(p)
            for folder in ('kernel','services','boot','include','lang','tools','assets','tests')
            for p in sorted((ROOT/folder).rglob('*'))
            if p.is_file() and not any(n in ('build','__pycache__') for n in p.relative_to(ROOT).parts)
            and p.suffix!='.pyc'}

def report_layout(layout):
    check(type(layout.get('schema')) is int and layout['schema']==1
          and layout.get('target')=='x86_64-dongos-elf' and layout.get('spec_version')=='0.1','layout header')
    candidates=[t for t in layout['types'] if t.get('full_name')=='boot.large_memory.Report']
    check(len(candidates)==1,'unique report layout required')
    item=candidates[0]
    expected=[dict(name=n,type='u64',offset=i*8,size=8) for i,n in enumerate(FIELDS)]
    check(item.get('name')=='Report' and item.get('size')==312 and type(item['size']) is int
          and type(item.get('alignment')) is int and item.get('alignment')==8
          and item.get('kind')=='struct' and item.get('fields')==expected,'exact 39-field ABI')
    check(all(type(f['offset']) is int and type(f['size']) is int for f in item['fields']),'integer ABI offsets')
    return item

def decode_report(raw,layout):
    report_layout(layout);check(isinstance(raw,bytes) and len(raw)==312,'exact report bytes required')
    return dict(zip(FIELDS,struct.unpack('<39Q',raw)))

def audit_buddy(allocator,metadata,lease,expected_free,retained=()):
    check(len(allocator)==128 and len(metadata)==1024*16,'actual bounded buddy ABI')
    initialized,base,count,pointer=struct.unpack_from('<B7xQQQ',allocator)
    check(initialized==1 and count==1024 and base%0x400000==0 and pointer>0,'actual buddy arena')
    heads=struct.unpack_from('<11Q',allocator,32);total=struct.unpack_from('<Q',allocator,120)[0]
    nodes=[struct.unpack_from('<BB6xQ',metadata,i*16) for i in range(1024)]
    check(all(node[0] in (0,1,2,3) for node in nodes),'invalid buddy metadata state')
    free=set();visited=set()
    for order,head in enumerate(heads):
        while head!=(1<<64)-1:
            check(head<1024 and head not in visited and head%(1<<order)==0
                  and head+(1<<order)<=1024,'buddy free-list range/cycle/alignment')
            state,actual_order,next_head=nodes[head]
            check(state==1 and actual_order==order,'buddy free head state/order')
            block=set(range(head,head+(1<<order)))
            check(not free.intersection(block) and all(nodes[i][0]==3 for i in block if i!=head),
                  'buddy overlapping free blocks or allocated/reserved tail')
            visited.add(head);free.update(block);head=next_head
    check(visited=={i for i,node in enumerate(nodes) if node[0]==1},'unreachable buddy free head')
    check(len(free)==total==expected_free,'buddy free-list count differs from actual ledger')
    for address,pages in retained:
        check(address>=base and (address-base)%4096==0 and pages>0 and address+pages*4096<=base+count*4096,
              'retained startup resource outside buddy arena')
        check(not free.intersection(range((address-base)//4096,(address-base)//4096+pages)),
              'still-owned startup resource incorrectly marked free')
    check(lease>=base and (lease-base)%0x200000==0,'exact original buddy lease alignment')
    first=(lease-base)//4096
    check(set(range(first,first+512))<=free,'original order9 lease was not fully returned')
    return len(free)

def audit_pool(pool,metadata,root,expected_leaves,allowed):
    check(len(pool)==128*4096 and len(metadata)==128 and set(metadata)<={0,1},'bounded final table pool')
    for index,used in enumerate(metadata):
        if not used:check(pool[index*4096:(index+1)*4096]==bytes(4096),'reclaimed table was not zeroed')
    seen=set();leaves=0
    def walk(pa,level,prefix):
        nonlocal leaves
        check(pa%4096==0 and root<=pa<root+len(pool) and pa not in seen,'invalid/cyclic table')
        index=(pa-root)//4096;check(metadata[index]==1,'tree references free/quarantined table');seen.add(pa)
        for slot,entry in enumerate(struct.unpack_from('<512Q',pool,pa-root)):
            if not entry:continue
            check(entry&1,'nonpresent garbage entry');va=prefix|(slot<<(39-level*9))
            if level<3:
                check(entry&~(MASK|0x20)==7,'final tree must restore ordinary 4KiB parent')
                walk(entry&MASK,level+1,va)
            else:
                if va&(1<<47):va|=0xffff000000000000
                check(allowed(va,entry),'final leaf outside exact physical/permission/cache allowlist');leaves+=1
    walk(root,0,0)
    check(len(seen)==sum(metadata) and leaves==expected_leaves,'unreachable table or final leaf count')
    return len(seen)

def validate_report(r):
    check(set(r)==set(FIELDS) and all(type(v) is int and 0<=v<1<<64 for v in r.values()),'complete u64 report')
    check((r['version'],r['attempted'],r['complete'],r['phase'],r['steps'],r['held'],r['error_code'])
          ==(1,1,1,10,1023,0,0),'lifecycle incomplete, unsupported, or still held')
    check(r['root']==r['cr3'] and r['root']>0 and r['root']%4096==0,'exact active root')
    check(r['window']==WINDOW and r['physical']>0 and r['physical']%0x200000==0
          and (r['pages'],r['order'])==(512,9),'exact owned order9 span')
    check(r['free_before']==r['free_after'] and r['free_held']+512==r['free_before'],'buddy ownership balance')
    base=r['tables_before']
    check(base>0 and (r['tables_mapped'],r['tables_split'],r['tables_merged'],r['tables_after'])
          ==(base+2,base+3,base+2,base),'page table lifetime balance')
    tag=lambda i:0x1122334400000000|i
    check((r['sample_first'],r['sample_last'],r['split_value'],r['replacement_value'],r['restored_value'],r['merge_value'])
          ==(tag(0),tag(511),tag(5),tag(6),tag(5),tag(5)),'hardware translation/readback values')
    check(r['merge_error']==0x02030007 and (r['invlpg'],r['full_flush'],r['retired_tables'])==(2,516,4),
          'rejected merge or complete invalidation/reclamation sequence')
    check(r['cr0']&0x80010001==0x80010001 and not r['cr0']&0x60000000
          and r['efer']&0xd00==0xd00 and r['cr4']&32 and not r['cr4']&0x00821080
          and not r['rflags']&0x60600 and r['rflags']&2,'actual hardened BSP controls')
    check(r['pat']&255==6 and (r['pat']>>24)&255==0,'unchanged WB/UC PAT policy')
    check(all(r[n]&~0x60==r['physical']|0x8000000000000083 for n in ('large_entry','merged_entry')),
          'actual 2MiB WB/RW/NX leaf encoding')
    check(r['split_entry']&~(MASK|0x20)==7 and r['split_entry']&MASK>r['root']
          and r['split_entry']&MASK<r['root']+128*4096,'actual split child in retained table pool')
    return r

def verify_inputs(esp):
    record=json.loads((esp.parent/'build-inputs.json').read_text(encoding='utf-8'))
    check(record.get('test') is False and record.get('runtime_level')==0
          and record.get('source_unchanged') is True,'completed ordinary P2 build required')
    for name,value in record['source_sha256'].items():check(sha(ROOT/name)==value,'build source changed: '+name)
    for name,value in record['artifacts'].items():
        p=Path(name);check(sha(p if p.is_absolute() else esp.parent/p)==value,'build artifact changed: '+name)
    from lang.dongc import compile_file
    canonical=compile_file(ROOT/'kernel/memory_probe.dg',roots=[ROOT/'lang/examples',ROOT/'kernel',ROOT/'lang/std'],mode=record['kernel_mode'])
    check(canonical.layout_manifest==json.loads((esp.parent/'dong_layout.json').read_text(encoding='utf-8')),
          'completed layout differs from compiler output for exact built sources')
    return record

def verify_bytes(read,layout,symbols,serial,registers):
    _,prior=acpi.parse_report(serial,symbols,production=True)
    old=prior['hardening']['memory']['fields']
    boot=struct.unpack('<20Q',read(old['runtime_boot_info']-acpi.HHDM,160,'BootInfo'))
    check(boot[:3]==(0x544f4f42474e4f44,1,160),'BootInfo ABI')
    physical=boot[15]
    def kernel(va,size,role):
        check(symbols['__kernel_data_start']<=va and va+size<=symbols['__kernel_bss_end'],'bounded retained data/BSS record')
        return read(physical+va-acpi.KERNEL,size,role)
    report=validate_report(decode_report(kernel(symbols[storage.symbol('boot.large_memory','REPORT')],312,'large report'),layout))
    types={t['full_name']:t for t in layout['types']}
    work_type=types['boot.memory_startup.Workspace']
    work=kernel(symbols[storage.symbol('boot.memory_startup','WORK')],work_type['size'],'startup workspace')
    def field(typ,raw,name):
        matches=[f for f in types[typ]['fields'] if f['name']==name];check(len(matches)==1,'unique ledger field')
        f=matches[0];return raw[f['offset']:f['offset']+f['size']]
    def number(typ,raw,name):
        value=field(typ,raw,name);check(len(value) in (1,8),'scalar ledger field');return int.from_bytes(value,'little')
    alloc=field('boot.memory_startup.Workspace',work,'allocator')
    space=field('boot.memory_startup.Workspace',work,'space')
    table_meta=field('boot.memory_startup.Workspace',work,'table_meta')
    buddy_meta=field('boot.memory_startup.Workspace',work,'page_meta')
    check(number('mm.phys_buddy.Allocator',alloc,'metadata')
          ==symbols[storage.symbol('boot.memory_startup','WORK')]+next(f['offset'] for f in work_type['fields'] if f['name']=='page_meta'),
          'buddy metadata pointer differs from actual retained workspace')
    audit_buddy(alloc,buddy_meta,report['physical'],report['free_after'],((report['root'],128),(old['stack_physical'],16)))
    arena=number('mm.phys_buddy.Allocator',alloc,'base')
    check(arena<=report['physical'] and report['physical']+0x200000<=arena+1024*4096,'lease outside actual owned arena')
    check(number('mm.paging.Space',space,'used_total')==report['tables_after']
          and number('mm.paging.Space',space,'pool_physical')==report['root']
          and number('mm.paging.Space',space,'pool_count')==128,'actual page table ledger disagrees')
    check(len(table_meta)==128 and set(table_meta)<={0,1} and sum(table_meta)==report['tables_after'],
          'pending/quarantined or mismatched table metadata')
    pool=read(report['root'],128*4096,'complete kernel table pool')
    resource_layout=field('boot.memory_startup.Workspace',work,'layout')
    spans={name:struct.unpack('<2Q',field('boot.memory_resources.Layout',resource_layout,name))
           for name in ('text','rodata','data','bss','df','nmi','exception_stack')}
    for name in ('text','rodata','data','bss'):
        check(spans[name]==(symbols['__kernel_'+name+'_start'],symbols['__kernel_'+name+'_end']),
              'startup section manifest differs from actual ELF')
    view=field('boot.memory_startup.Workspace',work,'runtime')
    v=lambda n:number('boot.runtime_view.View',view,n)
    display=field('boot.runtime_view.View',view,'display')
    d=lambda n:number('boot.runtime_view.Display',display,n)
    manifest=field('boot.memory_startup.Workspace',work,'manifest')
    check(struct.unpack_from('<Q',manifest,8*24+8)[0]==physical,'kernel resource physical identity')
    def inside(va,base,size):return size>0 and base&~4095<=va<(base+size+4095)&~4095
    def allowed(va,entry):
        entry&=~0x60
        if spans['text'][0]<=va<spans['bss'][1]:
            if any(va in (start-4096,end) for start,end in (spans[n] for n in ('df','nmi','exception_stack'))):return False
            flags=1 if va>=spans['rodata'][1] else 0 if va>=spans['text'][1] else 4
            expected=physical+va-acpi.KERNEL|1|(2 if flags&1 else 0)|(0 if flags&4 else 1<<63)
            return entry==expected
        if inside(va,v('stack_bottom'),65536):return entry==(v('stack_probe_bottom')-acpi.HHDM+va-v('stack_bottom')|0x8000000000000003)
        flags=1
        found=any(inside(va,base,size) for base,size in ((v('boot_info'),160),(v('raw_map'),v('raw_size')),
            (v('pool'),128*4096),(v('stack_probe_bottom'),65536))) or va==acpi.HHDM+boot[17]
        if inside(va,v('rsdp'),v('rsdp_size')):found=True;flags=0
        if inside(va,d('framebuffer_base'),d('framebuffer_size')):found=True;flags=9
        if not found or not acpi.HHDM<=va<acpi.HHDM+(1<<32):return False
        return entry==(va-acpi.HHDM|1|(2 if flags&1 else 0)|1<<63|(0x18 if flags&8 else 0))
    tables=audit_pool(pool,table_meta,report['root'],number('boot.memory_startup.Workspace',work,'expected_pages'),allowed)
    pa=report['root']
    for level in range(4):
        slot=(WINDOW>>(39-level*9))&511;entry=struct.unpack_from('<Q',pool,pa-report['root']+slot*8)[0]
        if entry==0:break
        check(level<3,'large exercise window still mapped');pa=entry&MASK
    controls={n:int(v,16) for n,v in re.findall(r'\b(CR0|CR3|CR4|EFER)=([0-9a-fA-F]+)',registers)}
    check(controls=={n.upper():report[n] for n in ('cr0','cr3','cr4','efer')},'independent hardware controls differ')
    halt=symbols['memory_activation_entry.halt']
    check('HLT=1' in registers and 'CPL=0' in registers
          and int(re.search(r'RIP=([0-9a-fA-F]+)',registers)[1],16) in (halt,halt+1),'linked normal CPL0 halt')
    return dict(report=report,actual_buddy_free=report['free_after'],actual_tables=tables,
                final_pool_sha256=hashlib.sha256(pool).hexdigest(),scope='BSP WB/NX startup lifecycle; final 4KiB tree restored')

def run(esp,cpus=4,timeout=90):
    esp=Path(esp).resolve();build=verify_inputs(esp)
    state=ROOT/'build/test/p2-active-large'/('run-'+uuid.uuid4().hex);state.mkdir(parents=True)
    artifacts=state/'artifacts';artifacts.mkdir()
    for name in ('kernel.elf','dong_layout.json','build-inputs.json'):shutil.copy2(esp.parent/name,artifacts/name)
    artifacts_sha={p.name:sha(p) for p in artifacts.iterdir()}
    serial=state/'serial.log';serial.write_bytes(b'');chunks=[];process=qmp=None
    source_before=source_hashes()
    result=dict(passed=False,actual_qemu_executed=False,cpus=cpus,build_source_sha256=build['source_sha256'],source_before=source_before,
                layout_source_verified=True,completed_layout_sha256=sha(esp.parent/'dong_layout.json'),
                artifacts_sha256=artifacts_sha,no_guest_memory_or_register_writes=True)
    def read(pa,size,role):
        check(type(pa) is int and type(size) is int and 0<pa<1<<32 and 0<size<=1<<20 and pa+size<=1<<32,'bounded physical read')
        path=state/f'physical-{len(chunks):04d}.bin'
        qmp.request('pmemsave',dict(val=pa,size=size,filename=str(path.resolve())))
        raw=path.read_bytes();check(len(raw)==size,'short physical read')
        chunks.append(dict(physical=pa,length=size,role=role,file=path.name,sha256=sha(path)));return raw
    try:
        symbols=acpi.validation_symbols(artifacts/'kernel.elf');port=storage.free_port()
        command=builder.qemu_command(esp,state/'firmware',test=True)
        i=command.index('isa-debug-exit,iobase=0xf4,iosize=0x04');del command[i-1:i+1]
        command[command.index('-smp')+1]=str(cpus)
        command+=['-vga','std','-cpu','max,+smep,+smap,+umip','-S','-qmp',f'tcp:127.0.0.1:{port},server=on,wait=off']
        command[command.index('-serial')+1]='file:'+serial.resolve().as_posix()
        result['command']=command
        with (state/'stderr.log').open('wb') as stderr:
            process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=stderr);result['actual_qemu_executed']=True
            qmp=acpi.QMP(port,process);qmp.request('cont');deadline=time.monotonic()+timeout
            while True:
                raw=serial.read_bytes()
                check(b'FAIL' not in raw and b'PANIC' not in raw,'actual guest failure')
                if b'DONGOS_P1_PASS\r\n' in raw:
                    registers=qmp.request('human-monitor-command',{'command-line':'info registers'})
                    if 'HLT=1' in registers:break
                check(process.poll() is None and time.monotonic()<deadline,'normal startup timeout/exit');time.sleep(.05)
            qmp.request('stop');registers=qmp.request('human-monitor-command',{'command-line':'info registers'})
            check(len(qmp.request('query-cpus-fast'))==cpus,'actual QEMU CPU count')
            (state/'registers.txt').write_text(registers,encoding='utf-8')
            result['observed']=verify_bytes(read,json.loads((artifacts/'dong_layout.json').read_text(encoding='utf-8')),symbols,raw,registers)
            verify_inputs(esp);result.update(passed=True)
    except Exception as error:
        result['error']=f'{type(error).__name__}: {error}'
        if qmp and process and process.poll() is None:
            try:
                qmp.request('stop');failed_serial=serial.read_bytes()
                markers=re.findall(rb'^memory_runtime_boot_info=0x([0-9a-f]{16})\r?$',failed_serial,re.M)
                if len(markers)==1:
                    boot=struct.unpack('<20Q',read(int(markers[0],16)-acpi.HHDM,160,'failure BootInfo'))
                    address=symbols[storage.symbol('boot.large_memory','REPORT')]
                    check(symbols['__kernel_data_start']<=address<symbols['__kernel_bss_end']-312,'bounded failure report')
                    result['failure_report']=decode_report(read(boot[15]+address-acpi.KERNEL,312,'failure large report'),
                        json.loads((artifacts/'dong_layout.json').read_text(encoding='utf-8')))
            except Exception as capture:result['failure_capture_error']=str(capture)
    finally:
        if qmp:
            try:qmp.request('quit')
            except Exception as error:result.update(passed=False,cleanup_error=str(error))
            qmp.close()
        if process:
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5);result.update(passed=False,cleanup_error='forced QEMU stop')
            result.update(qemu_returncode=process.returncode,process_alive=process.poll() is None,
                          cleanup_completed=process.returncode==0)
            if process.returncode!=0:result['passed']=False
        source_after=source_hashes();result.update(source_after=source_after,source_unchanged=source_before==source_after)
        if source_before!=source_after:result.update(passed=False,integrity_error='source changed during guest run')
        write(state/'physical-manifest.json',chunks)
        result['evidence_sha256']={n:sha(state/n) for n in ('serial.log','registers.txt','physical-manifest.json') if (state/n).exists()}
        write(state/'result.json',result)
    return state/'result.json',result

def replay(path):
    state=Path(path).resolve().parent;result=json.loads((state/'result.json').read_text(encoding='utf-8'))
    check(result.get('passed') is True and result.get('source_unchanged') is True,'successful stable archive required')
    check(result.get('actual_qemu_executed') is True and result.get('no_guest_memory_or_register_writes') is True
          and result.get('cleanup_completed') is True and result.get('process_alive') is False
          and type(result.get('qemu_returncode')) is int and result['qemu_returncode']==0,'actual guest/cleanup facts required')
    command=result.get('command',[])
    check(type(command) is list and all(type(item) is str for item in command),'complete command string list')
    for option in ('-smp','-accel'):
        check(command.count(option)==1 and command.index(option)+1<len(command),'complete unique command option '+option)
    check(type(result.get('cpus')) is int and result['cpus'] in (1,4) and command.count('-smp')==1
          and command[command.index('-smp')+1]==str(result['cpus']) and command.count('-accel')==1
          and command[command.index('-accel')+1]=='tcg','actual configured CPU/TCG facts')
    for name,value in result['artifacts_sha256'].items():
        check(name in ('kernel.elf','dong_layout.json','build-inputs.json') and sha(state/'artifacts'/name)==value,'archived artifact hash')
    check(set(result['artifacts_sha256'])=={'kernel.elf','dong_layout.json','build-inputs.json'},'complete archived artifacts')
    check(result.get('layout_source_verified') is True and result.get('completed_layout_sha256')
          ==result['artifacts_sha256']['dong_layout.json'],'canonical build/archive layout identity')
    build=json.loads((state/'artifacts/build-inputs.json').read_text(encoding='utf-8'))
    check(build['source_sha256']==result['build_source_sha256'] and build['test'] is False
          and build['runtime_level']==0 and build['source_unchanged'] is True,'archive build source identity')
    check(result.get('source_before')==result.get('source_after') and result.get('source_before')
          and all(result['source_before'].get(n)==v for n,v in build['source_sha256'].items()),'source before/after/build mismatch')
    kernel_hashes=[v for n,v in build['artifacts'].items() if n.replace('\\','/').rsplit('/',1)[-1]=='kernel.elf']
    check(kernel_hashes==[result['artifacts_sha256']['kernel.elf']],'build/archive kernel ELF identity')
    layout_hashes=[v for n,v in build['artifacts'].items() if n.replace('\\','/').rsplit('/',1)[-1]=='dong_layout.json']
    check(layout_hashes==[result['artifacts_sha256']['dong_layout.json']],'build/archive canonical layout identity')
    check(set(result.get('evidence_sha256',{}))=={'serial.log','registers.txt','physical-manifest.json'}
          and all(sha(state/n)==v for n,v in result['evidence_sha256'].items()),'archive serial/register/physical manifest SHA')
    chunks=json.loads((state/'physical-manifest.json').read_text(encoding='utf-8'));cursor=0
    def read(pa,size,role):
        nonlocal cursor
        check(cursor<len(chunks),'offline physical read exceeds archive');item=chunks[cursor];cursor+=1
        check((pa,size,role)==(item['physical'],item['length'],item['role']),'offline read order/address/role')
        check(re.fullmatch(r'physical-[0-9]{4,}\.bin',item['file']) is not None,'offline dump path')
        raw=(state/item['file']).read_bytes();check(len(raw)==size and hashlib.sha256(raw).hexdigest()==item['sha256'],'offline short/hash')
        return raw
    decoded=verify_bytes(read,json.loads((state/'artifacts/dong_layout.json').read_text(encoding='utf-8')),
                         acpi.validation_symbols(state/'artifacts/kernel.elf'),(state/'serial.log').read_bytes(),
                         (state/'registers.txt').read_text(encoding='utf-8'))
    check(cursor==len(chunks) and decoded==result['observed'],'offline decoded evidence mismatch')
    return dict(passed=True,actual_qemu_executed=result['actual_qemu_executed'],observed=decoded)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp',type=Path);parser.add_argument('--cpus',type=int,choices=(1,4),default=4)
    parser.add_argument('--replay',type=Path);args=parser.parse_args()
    if args.replay:print(json.dumps(replay(args.replay),indent=2));return 0
    if not args.reuse_esp:parser.error('--reuse-esp is required')
    path,result=run(args.reuse_esp,args.cpus);print(path);return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
