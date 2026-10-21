#!/usr/bin/env python3
"""Real fragmented-buddy OOM, no guest-memory writes; portable raw replay."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,struct,sys,time,uuid
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import build as builder
from tools.build_usb import verify_build
from tools.make_fat32_disk import create
from tests import p2_fragmented_fixture as fixture
from tests import run_p2_shared_large_qemu as shared
from tests import run_virtio_reset_qemu as transport
ROOT=builder.ROOT;NONE=(1<<64)-1;MASK=shared.MASK
def check(value,message):
    if not value:raise ValueError('P2 fragmented OOM: '+message)
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
def audit_buddy(allocator,metadata,hole):
    check(len(allocator)==128 and len(metadata)==16384,'complete buddy ABI')
    ready,base,count,pointer=struct.unpack_from('<4Q',allocator)
    check(ready==1 and base%0x400000==0 and count==1024 and pointer!=0 and hole==base+0x200000,'actual arena and second-half hole')
    nodes=[struct.unpack_from('<BB6xQ',metadata,i*16) for i in range(1024)]
    free=set();heads=set();max_order=0
    for order,head in enumerate(struct.unpack_from('<11Q',allocator,32)):
        check(order<9 or head==NONE,'no contiguous order9/order10 block')
        while head!=NONE:
            check(head<1024 and head not in heads and head%(1<<order)==0 and head+(1<<order)<=1024,'free range/cycle')
            check(nodes[head][:2]==(1,order),'free head state/order')
            block=set(range(head,head+(1<<order)))
            check(not free&block and all(nodes[i][0]==3 for i in block if i!=head),'free overlap/tails')
            free|=block;heads.add(head);max_order=max(max_order,order);head=nodes[head][2]
    check(heads=={i for i,n in enumerate(nodes) if n[0]==1},'orphan free head')
    check(len(free)==struct.unpack_from('<Q',allocator,120)[0]==879,'independent actual free total879')
    allocated=set()
    for first,order in ((0,7),(128,4),(512,0)):
        check(nodes[first]==(2,order,NONE),'actual pool/stack/hole allocation')
        block=set(range(first,first+(1<<order)));check(not allocated&block and not free&block,'allocation overlap')
        check(all(nodes[i][0]==3 for i in block if i!=first),'allocated tails');allocated|=block
    check(free|allocated==set(range(1024)) and {i for i,n in enumerate(nodes) if n[0]==2}=={0,128,512},'complete physical ownership')
    return dict(free=len(free),largest_order=max_order,hole=hole,allocated_pages=len(allocated))
def pool_hash(pool):
    h=14695981039346656037
    for x, in struct.iter_unpack('<Q',pool):h=((h^(x&~0x60))*1099511628211)&NONE
    return h
def audit_pool(pool,metadata,root,used):
    check(len(pool)==128*4096 and len(metadata)==128 and set(metadata)<={0,1},'actual bounded pool without quarantine')
    seen=set();leaves=0
    check(struct.unpack_from('<Q',pool,336*8)[0]==0,'shared large window was never published')
    for i,v in enumerate(metadata):
        if not v:check(pool[i*4096:(i+1)*4096]==bytes(4096),'free table remains zero')
    def walk(pa,level):
        nonlocal leaves
        check(pa%4096==0 and root<=pa<root+len(pool) and pa not in seen,'pool walk range/cycle')
        check(metadata[(pa-root)//4096]==1,'tree references free table');seen.add(pa)
        for e, in struct.iter_unpack('<Q',pool[pa-root:pa-root+4096]):
            if not e:continue
            check(e&1,'nonpresent table garbage')
            if level<3:check(e&~(MASK|0x20)==7,'no large/intermediate malformed entry');walk(e&MASK,level+1)
            else:check(not e&4,'supervisor kernel ownership');leaves+=1
    walk(root,0);check(len(seen)==sum(metadata)==used,'complete reachable unchanged pool')
    return dict(tables=len(seen),ordinary_pages=leaves,large_pages=0)
def verify_bytes(read,layout,symbols,boot,cpus,registers,serial):
    check(tuple(boot[:3])==(0x544f4f42474e4f44,1,160) and len(boot)==20 and 0<boot[15]<1<<32,'actual BootInfo')
    check(len(re.findall(rb'^smp_runtime_error=0x0000000002000007\r$',serial,re.M))==1 and
          b'DONGOS_P6_SMP_READY\r\n' in serial and b'DONGOS_P1_KERNEL_FAIL\r\n' in serial and b'DONGOS_P7_DESKTOP_READY' not in serial,'exact OOM UART, no desktop continuation')
    types={t['full_name']:t for t in layout['types']}
    for typ,size,offset in [('mm.phys_buddy.Allocator',128,24),('mm.paging.Space',64,32)]:
        check(types[typ]['size']==size and next(f['offset'] for f in types[typ]['fields'] if f['name']=='metadata')==offset,'fixture raw ABI '+typ)
    def kernel(module,name,n):
        va=symbols[transport.storage.symbol(module,name)];check(symbols['__kernel_data_start']<=va<=symbols['__kernel_bss_end']-n,'bounded kernel symbol '+name)
        return read(boot[15]+va-transport.storage.KERNEL,n,module+'.'+name)
    r=shared.decode_report(kernel('smp.large_memory','REPORT',504),layout)
    exact=dict(version=1,attempted=1,complete=0,phase=0,steps=0,physical=0,held=0,free_before=879,free_held=0,free_after=0,error_code=0x02000007,sealed=0,seal_error=0,count=cpus)
    check(all(r[k]==v for k,v in exact.items()),'failed before lease acquisition/bind/publication')
    check(r['window']==shared.WINDOW and r['root']>0 and r['root']%4096==0,'exact exercise root/window')
    check(all(r[k]==0 for k in ('tables_mapped','tables_split','tables_merged','tables_after','sample_first','sample_last','large_entry','split_entry','merged_entry','final_entry','invlpg','full_flush','retired_tables','reader_checks')),'no post-acquisition work claimed')
    work=kernel('boot.memory_startup','WORK',types['boot.memory_startup.Workspace']['size'])
    f=lambda n:shared.field(types,'boot.memory_startup.Workspace',work,n)
    allocator,metadata,space=f('allocator'),f('page_meta'),f('space')
    hole=struct.unpack('<Q',kernel('smp.large_memory','FRAGMENT_HOLE',8))[0]
    saved=kernel('smp.large_memory','FRAGMENT_BEFORE',16512)
    check(saved==allocator+metadata,'actual OOM entire allocator/metadata unchanged')
    check(kernel('smp.large_memory','FRAGMENT_SPACE_BEFORE',64)==space and kernel('smp.large_memory','FRAGMENT_TABLE_META_BEFORE',128)==f('table_meta'),'Space and full table metadata unchanged')
    work_va=symbols[transport.storage.symbol('boot.memory_startup','WORK')]
    check(struct.unpack_from('<Q',allocator,24)[0]==work_va+next(x['offset'] for x in types['boot.memory_startup.Workspace']['fields'] if x['name']=='page_meta'),'actual metadata pointer')
    buddy=audit_buddy(allocator,metadata,hole)
    check(struct.unpack_from('<Q',space,24)[0]==r['root'] and struct.unpack_from('<Q',space,16)[0]==128,'actual root pool descriptor')
    pool=read(r['root'],128*4096,'complete failed-alloc kernel table pool')
    before_hash=struct.unpack('<Q',kernel('smp.large_memory','FRAGMENT_POOL_HASH',8))[0]
    check(pool_hash(pool)==before_hash,'full pool unchanged except hardware A/D')
    tree=audit_pool(pool,f('table_meta'),r['root'],r['tables_before'])
    domain=struct.unpack('<14Q',kernel('smp.runtime','DOMAIN',112))
    check(domain[0:2]==(1,0) and domain[3]==cpus and domain[13]==0 and r['domain_pointer']==symbols[transport.storage.symbol('smp.runtime','DOMAIN')],'reader domain healthy')
    for key,index in [('epoch',6),('broadcasts',7),('sent',8),('acks',9),('invalid',10),('full',11),('probes',12)]:
        check(domain[index]==r[key+'_before'] and r[key+'_after']==0,'no reader-domain operation on OOM')
    contexts=read(boot[15]+domain[2]-transport.storage.KERNEL,cpus*256,'failed-alloc reader contexts')
    boxes=read(boot[15]+domain[4]-transport.storage.KERNEL,cpus*64,'failed-alloc reader mailboxes')
    for i in range(cpus):
        c=struct.unpack_from('<32Q',contexts,i*256);check(c[:6]==(domain[2]+i*256,i,i,4,1,r['root']) and c[25]==1,'online CPU retains original root/epoch')
        if i:
            b=struct.unpack_from('<8Q',boxes,i*64);check(b[0]==b[3]==domain[6] and b[5:]==(0x8877665544332211,0,0),'only earlier SMP proof was observed')
    owner=kernel('smp.large_memory','CONTEXT',types['mm.shared_paging.Context']['size'])
    for n in ('domain','root','count','bound','busy','sealed'):check(int.from_bytes(shared.field(types,'mm.shared_paging.Context',owner,n),'little')==0,'unbound owner '+n)
    inner=shared.field(types,'mm.shared_paging.Context',owner,'inner')
    check(shared.field(types,'mm.active_paging.Context',inner,'totals')==bytes(24),'no active transaction counters')
    bsp=re.split(r'CPU#\d+\s*',registers)[1:];check(len(bsp)==cpus,'actual CPU register dump count');bsp=bsp[0]
    rip=int(re.search(r'RIP=([0-9a-fA-F]+)',bsp)[1],16);halt=symbols['kernel_fail.halt']
    check('CPL=0' in bsp and 'HLT=1' in bsp and rip in (halt,halt+1) and int(re.search(r'CR3=([0-9a-fA-F]+)',bsp)[1],16)==r['root'],'linked expected fail-stop/root')
    return dict(report=r,buddy=buddy,tree=tree,entire_allocator_unchanged=True,pool_software_bits_unchanged=True,owner_unbound=True,reader_domain_unchanged=True)
def run(esp,cpus=4):
    esp=Path(esp).resolve();verify_build(esp);injected=fixture.verify(ROOT)
    state=ROOT/'build/test/p2-fragmented-qemu'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True);art=state/'artifacts';art.mkdir()
    for n in ('kernel.elf','dong_layout.json','build-inputs.json'):shutil.copy2(esp.parent/n,art/n)
    shutil.copy2(ROOT/'p2-fragmented-fixture.json',art/'fixture.json');shutil.copy2(Path(injected['source'])/fixture.TARGET,art/'production-large.dg');shutil.copy2(ROOT/fixture.TARGET,art/'fixture-large.dg')
    disk=state/'data.img';create(disk,64);before=fixture.hashes(ROOT);disk_before=fixture.digest(disk);g=None;start=time.monotonic()
    result=dict(passed=False,cpus=cpus,source_before=before,artifacts_sha256={p.name:fixture.digest(p) for p in art.iterdir()},no_guest_memory_or_register_writes=True)
    base=builder.qemu_command
    def command(*a,**kw):
        cmd=base(*a,**kw);cmd[cmd.index('-smp')+1]=str(cpus);return cmd
    try:
        with mock.patch.object(builder,'qemu_command',command):g=transport.ResetGuest(esp,disk,state/'guest',control=True)
        g.resume();deadline=time.monotonic()+100
        while b'DONGOS_P1_KERNEL_FAIL\r\n' not in g.raw:
            check(g.process.poll() is None and b'PANIC' not in g.raw and time.monotonic()<deadline,'expected OOM marker timeout/exit/panic');time.sleep(.02)
        while True:
            g.pause();registers=g.qmp.request('human-monitor-command',{'command-line':'info registers -a'})
            if 'HLT=1' in re.split(r'CPU#\d+\s*',registers)[1]:break
            check(time.monotonic()<deadline,'expected BSP halt timeout');g.resume();time.sleep(.02)
        check(len(g.qmp.request('query-cpus-fast'))==cpus,'actual CPU count');(state/'registers.txt').write_text(registers)
        read_start=len(g.chunks);observed=verify_bytes(g.physical,g.layout,g.symbols,g.boot,cpus,registers,bytes(g.raw))
        result.update(passed=True,observed=observed,read_range=[read_start,len(g.chunks)],boot=list(g.boot))
    except Exception as error:result['error']=f'{type(error).__name__}: {error}'
    finally:
        if g:
            try:g.close()
            except Exception as error:result.update(passed=False,cleanup_error=str(error))
            result['guest']=g.evidence;result['serial_sha256']=fixture.digest(state/'guest/serial.log');result['physical_manifest_sha256']=fixture.digest(state/'guest/physical-manifest.json')
        after=fixture.hashes(ROOT);result.update(source_after=after,source_unchanged=before==after,disk_before_sha256=disk_before,disk_after_sha256=fixture.digest(disk),elapsed_seconds=time.monotonic()-start)
        if before!=after or disk_before!=fixture.digest(disk):result.update(passed=False,integrity_error='source or disk changed')
        verify_build(esp);fixture.verify(ROOT);write(state/'result.json',result)
    if result['passed']:write(state/'replay-result.json',replay(state/'result.json'))
    print(json.dumps(dict(result=str(state/'result.json'),passed=result['passed'],error=result.get('error'))));return result
def replay(path):
    path=Path(path).resolve();state=path.parent;r=json.loads(path.read_text());check(r['passed'] is True,'completed result required')
    expected={'kernel.elf','dong_layout.json','build-inputs.json','fixture.json','production-large.dg','fixture-large.dg'}
    check(set(r['artifacts_sha256'])==expected,'exact artifact set')
    for n,sha in r['artifacts_sha256'].items():check(fixture.digest(state/'artifacts'/n)==sha,'archived artifact bytes')
    check(r['source_before']==r['source_after'] and r['source_unchanged'] is True and r['no_guest_memory_or_register_writes'] is True,'stable no-write observation')
    check(r['guest']['actual_qemu_executed'] is True and r['guest']['cleanup_completed'] is True and r['guest']['qemu_returncode']==0 and r['guest']['process_alive'] is False,'real guest and cleanup')
    injected=json.loads((state/'artifacts/fixture.json').read_text());p=injected['production_sha256'];f=injected['fixture_sha256']
    check(set(p)==set(f) and [n for n in p if p[n]!=f[n]]==[fixture.TARGET] and injected['changed']==[fixture.TARGET],'single-source injection')
    check(fixture.digest(state/'artifacts/production-large.dg')==p[fixture.TARGET] and fixture.digest(state/'artifacts/fixture-large.dg')==f[fixture.TARGET],'bound original and candidate bytes')
    check((state/'artifacts/fixture-large.dg').read_text()==fixture.inject((state/'artifacts/production-large.dg').read_text()),'exact audited real-buddy injection')
    current=dict(r['source_before']);check(current.pop('p2-fragmented-fixture.json')==r['artifacts_sha256']['fixture.json'] and current==f,'source snapshot bound to fixture')
    build=json.loads((state/'artifacts/build-inputs.json').read_text());check(build['runtime_level']==7 and build['test'] is False and build['source_unchanged'] is True,'normal release runtime7 build')
    check(all(f.get(n)==v for n,v in build['source_sha256'].items()),'build inputs bound to fixture')
    check([v for n,v in build['artifacts'].items() if n.replace('\\','/').rsplit('/',1)[-1]=='kernel.elf']==[r['artifacts_sha256']['kernel.elf']],'ELF bound to completed build')
    serial=(state/'guest/serial.log').read_bytes();check(hashlib.sha256(serial).hexdigest()==r['serial_sha256'],'serial bytes')
    manifest=json.loads((state/'guest/physical-manifest.json').read_text());check(fixture.digest(state/'guest/physical-manifest.json')==r['physical_manifest_sha256'],'physical manifest')
    for item in manifest:
        check(re.fullmatch(r'physical-[0-9]{5,}\.bin',item['file']) is not None,'safe physical archive filename')
        q=state/'guest'/item['file'];check(not q.is_symlink() and q.stat().st_size==item['length'] and fixture.digest(q)==item['sha256'],'all physical dump bytes')
    bs=[x for x in manifest if x['role']=='BootInfo'];markers=re.findall(rb'^memory_runtime_boot_info=0x([0-9a-f]{16})\r?$',serial,re.M)
    check(len(bs)==len(markers)==1 and bs[0]['physical']==int(markers[0],16)-transport.acpi.HHDM and bs[0]['length']==160,'unique UART BootInfo binding')
    check(list(struct.unpack('<20Q',(state/'guest'/bs[0]['file']).read_bytes()))==r['boot'],'raw BootInfo')
    start,end=r['read_range'];cursor=start
    def read(pa,n,role):
        nonlocal cursor
        check(cursor<end,'raw replay exhausted');item=manifest[cursor];cursor+=1
        check((item['physical'],item['length'],item['role'])==(pa,n,role),'ordered raw read address/role')
        return (state/'guest'/item['file']).read_bytes()
    symbols=transport.acpi.validation_symbols(state/'artifacts/kernel.elf');layout=json.loads((state/'artifacts/dong_layout.json').read_text())
    observed=verify_bytes(read,layout,symbols,r['boot'],r['cpus'],(state/'registers.txt').read_text(),serial)
    check(cursor==end and observed==r['observed'],'raw offline result differs')
    return dict(passed=True,raw_recomputed=True,reads=end-start,observed=observed)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reuse-esp',type=Path);p.add_argument('--cpus',type=int,choices=(1,4),default=4);p.add_argument('--replay',type=Path);a=p.parse_args()
    if a.replay:print(json.dumps(replay(a.replay)));return 0
    if not a.reuse_esp:p.error('--reuse-esp required')
    return 0 if run(a.reuse_esp,a.cpus)['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
