#!/usr/bin/env python3
"""Read-only runtime7 shared-root large-page observation and raw offline replay."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,struct,sys,time,uuid
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import build as builder
from tools.build_usb import verify_build
from tools.make_fat32_disk import create
from tests import run_p2_active_large_qemu as prior
from tests import run_virtio_reset_qemu as control

ROOT=builder.ROOT;WINDOW=prior.WINDOW;MASK=prior.MASK
EXTRA=('domain_pointer count epoch_before epoch_after broadcasts_before broadcasts_after sent_before sent_after '
       'acks_before acks_after invalid_before invalid_after full_before full_after probes_before probes_after '
       'reader_value reader_checks sealed seal_error final_entry cleanup_tables domain_pending domain_failures').split()
FIELDS=prior.FIELDS+EXTRA
def check(value,message):
    if not value:raise ValueError('P2 shared large: '+message)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def decode_report(raw,layout):
    ts=[t for t in layout['types'] if t.get('full_name')=='smp.large_memory.Report']
    check(len(ts)==1,'report layout unique')
    expected=[dict(name=n,type='u64',offset=i*8,size=8) for i,n in enumerate(FIELDS)]
    check(ts[0]['size']==504 and ts[0]['alignment']==8 and ts[0]['fields']==expected,'exact shared report ABI')
    check(type(raw) is bytes and len(raw)==504,'exact shared report bytes')
    return dict(zip(FIELDS,struct.unpack('<63Q',raw)))
def validate_report(r):
    check(set(r)==set(FIELDS) and all(type(v) is int and 0<=v<1<<64 for v in r.values()),'complete u64 report')
    check(tuple(r[n] for n in ('version','attempted','complete','phase','steps','held','error_code','sealed','seal_error'))
          ==(1,1,1,11,2047,1,0,1,0x060e0002),'complete persistent sealed owner')
    check(r['count'] in (1,4) and r['domain_pointer']>0,'actual reader domain')
    check(r['window']==WINDOW and r['root']==r['cr3'] and r['root']>0 and r['root']%4096==0,'actual shared root/window')
    check(r['physical']>0 and r['physical']%0x200000==0 and (r['pages'],r['order'])==(512,9),'owned aligned order9 lease')
    check(r['free_after']==r['free_held']==r['free_before']-512,'persistent buddy lease remains held')
    b=r['tables_before'];check(b>0 and tuple(r[n] for n in ('tables_mapped','tables_split','tables_merged','cleanup_tables','tables_after'))
        ==(b+2,b+3,b+2,b,b+2),'temporary reclaim and persistent table accounting')
    tag=lambda n:0x1122334400000000|n
    check(tuple(r[n] for n in ('sample_first','sample_last','split_value','replacement_value','restored_value','merge_value','reader_value'))
          ==(tag(0),tag(511),tag(5),tag(6),tag(5),tag(5),tag(5)),'actual BSP/AP translations')
    check((r['invlpg'],r['full_flush'],r['retired_tables'],r['merge_error'])==(2,517,4,0x02030007),'flush/reclaim/rejected merge')
    diffs={n:r[n+'_after']-r[n+'_before'] for n in ('epoch','broadcasts','sent','acks','invalid','full','probes')}
    check(diffs==dict(epoch=524,broadcasts=524,sent=524*(r['count']-1),acks=524*(r['count']-1),invalid=2,full=517,probes=5),
          'all online reader acknowledgements before reclamation')
    check((r['domain_pending'],r['domain_failures'],r['reader_checks'])==(0,0,5*(r['count']-1)),'reader epoch completed')
    check(all(r[n]&~0x60==r['physical']|0x8000000000000083 for n in ('large_entry','merged_entry','final_entry')),'persistent WB/RW/NX PDE')
    check(r['split_entry']&~(MASK|0x20)==7 and r['root']<r['split_entry']&MASK<r['root']+128*4096,'split parent owned by pool')
    check(r['cr0']&0x80010001==0x80010001 and not r['cr0']&0x60000000 and r['efer']&0xd00==0xd00
          and r['cr4']&32 and not r['cr4']&0x00821080 and not r['rflags']&0x60600 and r['rflags']&2,'actual pre-scheduler controls')
    check(r['pat']&255==6 and (r['pat']>>24)&255==0,'unchanged WB/UC PAT')
    return r
def field(types,typ,raw,name):
    fs=[f for f in types[typ]['fields'] if f['name']==name];check(len(fs)==1,'unique ledger field '+name);f=fs[0]
    check(len(raw)==types[typ]['size'],'complete ledger object '+typ)
    return raw[f['offset']:f['offset']+f['size']]
def audit_buddy(allocator,metadata,r):
    check(len(allocator)==128 and len(metadata)==16384,'actual buddy ABI')
    initialized,base,count,pointer=struct.unpack_from('<B7xQQQ',allocator)
    check(initialized==1 and count==1024 and base%0x400000==0 and pointer>0,'actual bounded buddy arena')
    nodes=[struct.unpack_from('<BB6xQ',metadata,i*16) for i in range(1024)]
    check(all(n[0] in (0,1,2,3) for n in nodes),'buddy state enum')
    free=set();heads=set()
    for order,head in enumerate(struct.unpack_from('<11Q',allocator,32)):
        while head!=(1<<64)-1:
            check(head<1024 and head not in heads and head%(1<<order)==0 and head+(1<<order)<=1024,'buddy free list range/cycle')
            state,actual,next_head=nodes[head];check(state==1 and actual==order,'buddy head order/state')
            block=set(range(head,head+(1<<order)));check(not free&block and all(nodes[i][0]==3 for i in block if i!=head),'overlapping buddy blocks')
            heads.add(head);free|=block;head=next_head
    check(heads=={i for i,n in enumerate(nodes) if n[0]==1} and len(free)==struct.unpack_from('<Q',allocator,120)[0]==r['free_after'],'actual free ledger')
    check(base<=r['physical']<=base+0x200000,'held lease in arena');i=(r['physical']-base)//4096
    check(nodes[i]==(2,9,(1<<64)-1) and all(n[0]==3 for n in nodes[i+1:i+512]) and not free&set(range(i,i+512)),'order9 exact allocated head/tails')
    return len(free)
def audit_pool(pool,metadata,space,types,r):
    check(len(pool)==128*4096 and len(metadata)==128 and set(metadata)<={0,1},'bounded nonquarantined table pool')
    root=r['root'];seen=set();large=[];leaves=0
    for i,v in enumerate(metadata):
        if not v:check(pool[i*4096:(i+1)*4096]==bytes(4096),'free table must be zero')
    def walk(pa,level,prefix):
        nonlocal leaves
        check(pa%4096==0 and root<=pa<root+len(pool) and pa not in seen,'pool range/cycle/shared child')
        check(metadata[(pa-root)//4096]==1,'published tree references free table');seen.add(pa)
        for slot,e in enumerate(struct.unpack_from('<512Q',pool,pa-root)):
            if not e:continue
            check(e&1,'nonpresent garbage in table');va=prefix|(slot<<(39-level*9))
            if va&(1<<47):va|=0xffff000000000000
            if level==2 and e&128:
                check(va==WINDOW and e&~0x60==r['physical']|0x8000000000000083,'unexpected large mapping/cache/permission')
                large.append((va,e));leaves+=512
            elif level<3:
                check(e&~(MASK|0x20)==7,'ordinary parent flags');walk(e&MASK,level+1,va)
            else:
                check(not r['physical']<=e&MASK<r['physical']+0x200000,'conflicting lease alias')
                check(not e&4,'kernel leaf supervisor ownership');leaves+=1
    walk(root,0,0)
    used=int.from_bytes(field(types,'mm.paging.Space',space,'used_total'),'little')
    check(len(large)==1 and len(seen)==sum(metadata)==used and used>=r['tables_after'],'complete pool reachability and actual ledger')
    return dict(tables=len(seen),ordinary_pages=leaves-512,large_pages=1,lease_aliases=1)
def verify_bytes(read,layout,symbols,boot,cpus,negative=False):
    check(len(boot)==20 and tuple(boot[:3])==(0x544f4f42474e4f44,1,160) and 0<boot[15]<1<<32,'actual BootInfo identity')
    types={t['full_name']:t for t in layout['types']}
    def kernel(module,name,typ):
        va=symbols[control.storage.symbol(module,name)];n=types[typ]['size']
        check(symbols['__kernel_data_start']<=va<=symbols['__kernel_bss_end']-n,'bounded kernel report')
        return read(boot[15]+va-control.storage.KERNEL,n,module+'.'+name)
    r=decode_report(kernel('smp.large_memory','REPORT','smp.large_memory.Report'),layout)
    domain=struct.unpack('<14Q',kernel('smp.runtime','DOMAIN','smp.tlb.Domain'))
    check(r['count']==cpus and domain[0]==1 and domain[3]==cpus and r['domain_pointer']==symbols[control.storage.symbol('smp.runtime','DOMAIN')],'live root reader identity')
    check(domain[2]==symbols[control.storage.symbol('smp.runtime','CPUS')],'reader context pointer')
    ctx=read(boot[15]+domain[2]-control.storage.KERNEL,cpus*256,'shared root reader contexts')
    boxes=read(boot[15]+domain[4]-control.storage.KERNEL,cpus*64,'shared root reader mailboxes')
    for i in range(cpus):
        c=struct.unpack_from('<32Q',ctx,i*256)
        check(c[:6]==(domain[2]+i*256,i,i,4,1,r['root']) and c[25]==1 and not c[7]&0x20080,'real online context/root/epoch')
        if i:
            b=struct.unpack_from('<8Q',boxes,i*64)
            check(b[0]==b[3]==domain[6] and b[6:]==(0,0),'AP sequence acknowledgement/fault')
            check(b[5]==0x1122334400000005,'actual retained AP observed value')
            if negative:check(b[1:3]==(WINDOW+5*4096,2) and b[4]==0x1122334400000006,'precise stale AP probe target')
    if negative:
        check((r['attempted'],r['complete'],r['phase'],r['held'],r['error_code'])==(1,0,3,1,0x06030006),'real omitted-shootdown failed on AP stale mapping')
        check(domain[1]==1 and domain[13]==1 and r['replacement_value']==0x1122334400000006,'BSP updated but AP mismatch fail-stop')
        pool=read(r['root'],128*4096,'failed shared kernel table pool');pa=r['root']
        for shift in (39,30,21):
            check(r['root']<=pa<r['root']+len(pool) and pa%4096==0,'failed root walk range')
            e=struct.unpack_from('<Q',pool,pa-r['root']+((WINDOW>>shift)&511)*8)[0]
            check(e&~(MASK|0x20)==7,'failed path must retain split ordinary parents');pa=e&MASK
        check(r['root']<=pa<r['root']+len(pool),'failed split PT owned by pool')
        leaf=struct.unpack_from('<Q',pool,pa-r['root']+5*8)[0]
        check(leaf&~0x60==r['physical']+6*4096|0x8000000000000003,'actual new PTE contrasts with AP cached old value')
        return dict(report=r,negative=True,precise_stale_ap_translation=True)
    validate_report(r)
    check(domain[1]==0 and domain[13]==0 and domain[6]==domain[7] and domain[8]==domain[9]==domain[7]*(cpus-1)
          and domain[12]==r['probes_after'] and domain[7]>=r['broadcasts_after'],'actual live completed barriers')
    work=kernel('boot.memory_startup','WORK','boot.memory_startup.Workspace')
    f=lambda n:field(types,'boot.memory_startup.Workspace',work,n)
    allocator=f('allocator');metadata=f('page_meta');space=f('space')
    work_va=symbols[control.storage.symbol('boot.memory_startup','WORK')]
    metadata_at=next(f['offset'] for f in types['boot.memory_startup.Workspace']['fields'] if f['name']=='page_meta')
    check(int.from_bytes(field(types,'mm.phys_buddy.Allocator',allocator,'metadata'),'little')==work_va+metadata_at,'actual retained buddy metadata pointer')
    check(int.from_bytes(field(types,'mm.paging.Space',space,'pool_physical'),'little')==r['root'],'actual root pool pointer')
    check(int.from_bytes(field(types,'mm.paging.Space',space,'pool_count'),'little')==128,'actual root pool capacity')
    actual_free=audit_buddy(allocator,metadata,r)
    pool=read(r['root'],128*4096,'complete shared kernel table pool');tree=audit_pool(pool,f('table_meta'),space,types,r)
    owned=read(r['physical'],0x200000,'complete held order9 block')
    for i in range(512):
        check(struct.unpack_from('<Q',owned,i*4096)[0]==0x1122334400000000|i and
              struct.unpack_from('<Q',owned,i*4096+4088)[0]==0x8877665500000000|i,'all512 physical page boundary words')
    owner=kernel('smp.large_memory','CONTEXT','mm.shared_paging.Context')
    fs={f['name']:f for f in types['mm.shared_paging.Context']['fields']}
    num=lambda n:int.from_bytes(owner[fs[n]['offset']:fs[n]['offset']+fs[n]['size']],'little')
    check((num('domain'),num('root'),num('count'),num('bound'),num('busy'),num('sealed'))==(r['domain_pointer'],r['root'],cpus,1,0,1),'actual sealed persistent owner')
    return dict(report=r,actual_buddy_free=actual_free,tree=tree,owned_sha256=hashlib.sha256(owned).hexdigest(),pool_sha256=hashlib.sha256(pool).hexdigest())
def run(esp,cpus=4,negative=False):
    esp=Path(esp).resolve();verify_build(esp)
    state=ROOT/'build/test/p2-shared-large'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
    art=state/'artifacts';art.mkdir()
    for name in ('kernel.elf','dong_layout.json','build-inputs.json'):shutil.copy2(esp.parent/name,art/name)
    disk=state/'data.img';create(disk,64);disk_before=sha(disk);before=prior.source_hashes();g=None;start=time.monotonic()
    result=dict(passed=False,cpus=cpus,negative=negative,source_before=before,artifacts_sha256={p.name:sha(p) for p in art.iterdir()},no_guest_memory_or_register_writes=True)
    base=builder.qemu_command
    def command(*a,**kw):
        cmd=base(*a,**kw);cmd[cmd.index('-smp')+1]=str(cpus);return cmd
    try:
        with mock.patch.object(builder,'qemu_command',command):g=control.ResetGuest(esp,disk,state/'guest',control=True)
        g.resume()
        if negative:g.wait(b'smp_runtime_error=',timeout=90)
        elif cpus==4:g.wait(b'DONGOS_P7_DESKTOP_READY',timeout=120)
        else:
            # One CPU has no parallel user-domain service assignment. Require
            # the completed P2 owner, then observe subsequent normal startup.
            deadline=time.monotonic()+90
            while True:
                time.sleep(.03);g.pause();r=g.global_record('smp.large_memory','REPORT','smp.large_memory.Report')
                if r['complete']==1:break
                check(not r['error_code'] and time.monotonic()<deadline,'one-CPU shared startup failure/timeout');g.resume()
        g.pause();check(len(g.qmp.request('query-cpus-fast'))==cpus,'actual QEMU CPU count')
        registers=g.qmp.request('human-monitor-command',{'command-line':'info registers -a'});(state/'registers.txt').write_text(registers)
        read_start=len(g.chunks);observed=verify_bytes(g.physical,g.layout,g.symbols,g.boot,cpus,negative)
        result.update(observed=observed,read_range=[read_start,len(g.chunks)],boot=list(g.boot),desktop_ready=cpus==4 and not negative,actual_cpu_count=cpus)
        if cpus==4 and not negative:
            first=g.snapshot();control.validate(first,control=True);g.resume();time.sleep(.2);second=g.snapshot();control.validate(second,control=True)
            control.context.validate_observations(first,second,control=True);result['p5_control_regression']=True;result['p5_snapshots']=[first,second]
        result['passed']=True
    except Exception as error:result['error']=f'{type(error).__name__}: {error}'
    finally:
        if g:
            try:g.close()
            except Exception as error:result.update(passed=False,cleanup_error=str(error))
            result['guest']=g.evidence
            result['serial_sha256']=sha(state/'guest/serial.log');result['physical_manifest_sha256']=sha(state/'guest/physical-manifest.json')
        after=prior.source_hashes();result.update(source_after=after,source_unchanged=before==after,disk_before_sha256=disk_before,disk_after_sha256=sha(disk),elapsed_seconds=time.monotonic()-start)
        if before!=after or disk_before!=sha(disk):result.update(passed=False,integrity_error='source or read-only disk changed')
        verify_build(esp);write(state/'result.json',result)
    if result['passed']:write(state/'replay-result.json',replay(state/'result.json'))
    print(json.dumps(dict(result=str(state/'result.json'),passed=result['passed'],error=result.get('error'))));return result
def replay(path):
    path=Path(path).resolve();state=path.parent;result=json.loads(path.read_text());check(result['passed'] is True,'completed result required')
    for name,value in result['artifacts_sha256'].items():check(name in ('kernel.elf','dong_layout.json','build-inputs.json') and sha(state/'artifacts'/name)==value,'archived artifact identity')
    check(result['source_before']==result['source_after'] and result['source_unchanged'] is True
          and result['no_guest_memory_or_register_writes'] is True and result['actual_cpu_count']==result['cpus'],'stable observation identity')
    check(result['guest']['actual_qemu_executed'] is True and result['guest']['cleanup_completed'] is True
          and result['guest']['qemu_returncode']==0 and result['guest']['process_alive'] is False,'actual guest and cleanup')
    build=json.loads((state/'artifacts/build-inputs.json').read_text())
    check(build['runtime_level']==7 and build['test'] is False and build['source_unchanged'] is True,'normal release runtime7 build')
    check(all(result['source_before'].get(k)==v for k,v in build['source_sha256'].items()),'run sources differ from completed build')
    kernel_hashes=[v for k,v in build['artifacts'].items() if k.replace('\\','/').rsplit('/',1)[-1]=='kernel.elf']
    check(kernel_hashes==[result['artifacts_sha256']['kernel.elf']],'ELF not bound to actual build')
    layout=json.loads((state/'artifacts/dong_layout.json').read_text());symbols=control.acpi.validation_symbols(state/'artifacts/kernel.elf')
    manifest=json.loads((state/'guest/physical-manifest.json').read_text());start,end=result['read_range'];cursor=start
    check(sha(state/'guest/physical-manifest.json')==result['physical_manifest_sha256'] and sha(state/'guest/serial.log')==result['serial_sha256'],'serial/physical manifest identity')
    boot_items=[i for i in manifest if i['role']=='BootInfo'];markers=re.findall(rb'^memory_runtime_boot_info=0x([0-9a-f]{16})\r?$',(state/'guest/serial.log').read_bytes(),re.M)
    check(len(boot_items)==len(markers)==1,'unique actual BootInfo/UART')
    b=boot_items[0];check(b['physical']==int(markers[0],16)-control.acpi.HHDM and b['length']==160,'BootInfo physical address')
    check(list(struct.unpack('<20Q',(state/'guest'/b['file']).read_bytes()))==result['boot'],'BootInfo raw bytes differ')
    # Verify all physical chunks, including P5 control snapshots, before use.
    for item in manifest:
        check(re.fullmatch(r'physical-[0-9]{5,}\.bin',item['file']) is not None,'physical archive filename')
        p=state/'guest'/item['file'];check(not p.is_symlink() and p.stat().st_size==item['length'] and sha(p)==item['sha256'],'physical archive bytes')
    def read(pa,n,role):
        nonlocal cursor
        check(cursor<end,'replay exhausted');item=manifest[cursor];cursor+=1
        check((item['physical'],item['length'],item['role'])==(pa,n,role),'bound raw read order/address/role')
        return (state/'guest'/item['file']).read_bytes()
    actual=verify_bytes(read,layout,symbols,result['boot'],result['cpus'],result['negative'])
    check(cursor==end and actual==result['observed'],'offline raw result differs')
    return dict(passed=True,raw_recomputed=True,reads=end-start,observed=actual)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reuse-esp',type=Path);p.add_argument('--cpus',type=int,choices=(1,4),default=4);p.add_argument('--negative',action='store_true');p.add_argument('--replay',type=Path);a=p.parse_args()
    if a.replay:print(json.dumps(replay(a.replay)));return 0
    p.error('--reuse-esp required') if not a.reuse_esp else None
    return 0 if run(a.reuse_esp,a.cpus,a.negative)['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
