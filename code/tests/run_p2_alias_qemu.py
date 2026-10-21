"""Read-only actual pre-scheduler EXEC/GOP WC observation and raw replay."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,struct,sys,time,uuid
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import build as builder
from tools.build_usb import verify_build
from tools.make_fat32_disk import create
from tests import run_virtio_reset_qemu as control
from tests import run_p2_active_large_qemu as prior
from tests import run_p2_shared_large_qemu as shared
ROOT=builder.ROOT;MASK=0x000ffffffffff000;NX=1<<63;HHDM=0xffff800000000000
A=0xffffa90000000000;B=A+4096;CODE42=0xc30000002ab8;CODE43=0xc30000002bb8;CODE99=0xc300000063b8
FIELDS='version attempted complete phase error_code domain count root frame held free_before free_held window_a window_b exec_owner wc_owner boxes readers ranges receipts receipt_pages framebuffer framebuffer_pages exec42_mask exec43_mask write_denied_mask warm_write_mask exec_sealed wc_sealed wc_complete exec_phase wc_phase broadcasts_before broadcasts_after acks_before acks_after pat_before pat_after mtrr_checks commands'.split()
def check(ok,message):
    if not ok:raise ValueError('P2 alias: '+message)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def source_hashes(root=None):
    root=Path(root or ROOT).resolve();result={}
    for folder in ('kernel','services','boot','include','lang','tools','assets','tests'):
        for p in sorted((root/folder).rglob('*')):
            rel=p.relative_to(root)
            if not p.is_file() or '__pycache__' in rel.parts or p.suffix=='.pyc':continue
            if 'build' in rel.parts and rel.parts[:2]!=('kernel','build'):continue
            result[rel.as_posix()]=sha(p)
    return result

def prepare_mutant(source,destination,kind):
    source=Path(source).resolve();destination=Path(destination).resolve()
    check(kind in ('exec','pat'),'known unique hardware mutant')
    check(not destination.exists() and source!=destination and source not in destination.parents,'new isolated mutant destination')
    target='kernel/smp/bootstrap.asm' if kind=='exec' else 'kernel/smp/alias_memory.asm'
    check((source/target).is_file(),'complete audited source target')
    before=source_hashes(source)
    def ignore(directory,names):
        return [n for n in names if n in ('.git','__pycache__') or n.endswith('.pyc') or (n=='build' and Path(directory).resolve()!=source/'kernel')]
    for folder in ('kernel','services','boot','include','lang','tools','assets','tests'):
        if (source/folder).is_dir():shutil.copytree(source/folder,destination/folder,ignore=ignore)
    original_bytes=(source/target).read_bytes()
    original=original_bytes.decode('utf-8').replace('\r\n','\n')
    if kind=='exec':
        anchor='.full:\n    mov rax,cr3\n    mov cr3,rax\n    jmp .ack'
        replacement='.full:\n    ; Only after the new owner begins: retain the warmed AP writable alias.\n    call alias_boxes_table\n    cmp qword [rax],0\n    jne .ack\n    mov rax,cr3\n    mov cr3,rax\n    jmp .ack'
        check(original.count(anchor)==1 and original.count('extern alias_ap_command\n')==1,'single actual AP full-flush boundary')
        candidate=original.replace(anchor,replacement).replace('extern alias_ap_command\n','extern alias_ap_command,alias_boxes_table\n')
    else:
        anchor=' mov ecx,0x277\n wrmsr\n wbinvd'
        replacement=' mov ecx,0x277\n cmp qword [r13+SmpContext.logical_id],3\n je alias_mutant_pat_omitted\n wrmsr\nalias_mutant_pat_omitted:\n wbinvd'
        check(original.count(anchor)==1,'single actual PAT write boundary');candidate=original.replace(anchor,replacement)
    (destination/target).write_text(candidate,encoding='utf-8',newline='')
    after=source_hashes(destination);changed=[n for n in before if before[n]!=after.get(n)]
    check(set(before)==set(after) and changed==[target] and source_hashes(source)==before,'exact one-source hardware mutation, original unchanged')
    (destination/'p2-alias-original-source.txt').write_bytes(original_bytes)
    record=dict(kind=kind,target=target,changed=changed,production_sha256=before,fixture_sha256=after,original_sha256=hashlib.sha256(original_bytes).hexdigest(),mutant_sha256=hashlib.sha256(candidate.encode()).hexdigest(),no_production_backdoor=True)
    write(destination/'p2-alias-fixture.json',record);return record
def validate_report(r,cpus,negative=None):
    check(set(r)==set(FIELDS) and all(type(v)is int and 0<=v<1<<64 for v in r.values()),'exact report u64 fields')
    check(cpus in (1,4) and r['count']==cpus,'actual count')
    check((r['version'],r['attempted'],r['held'],r['window_a'],r['window_b'])==(1,1,1,A,B),'owned initialized window')
    check(r['root']>0 and r['root']%4096==0 and r['frame']>0 and r['frame']%4096==0,'actual root/frame alignment')
    check(r['free_held']+1==r['free_before'],'exact order0 lease')
    mask=(1<<cpus)-1
    check(r['warm_write_mask']==mask,'all readers actually warmed writable aliases')
    if negative=='exec':
        check(cpus==4 and r['complete']==0 and r['phase']==3 and r['error_code']==0x06120003,'precise stale writable failure')
        check(r['write_denied_mask']!=mask and r['write_denied_mask']&1 and r['exec_sealed']==0 and r['exec42_mask']==0,'BSP denied but stale AP write succeeded before first code execution')
    else:
        check(r['exec42_mask']==mask,'all readers actually executed42')
        check((r['write_denied_mask'],r['exec43_mask'],r['exec_sealed'])==(mask,mask,1),'write protection and second actual execution')
        if negative=='pat':check(cpus==4 and (r['complete'],r['phase'],r['wc_phase'],r['error_code'],r['wc_complete'],r['wc_sealed'])==(0,8,4,7,0,0),'precise actual PAT readback failure')
        else:
            check((r['complete'],r['phase'],r['error_code'],r['wc_complete'],r['wc_sealed'])==(1,9,0,1,1),'completed sealed normal consumers')
            check(r['framebuffer']>=0x100000 and r['framebuffer']%4096==0 and 0<r['framebuffer_pages']<=4096,'actual GOP aperture')
            check(r['pat_after']==(r['pat_before']&~(255<<32))|(1<<32),'only PAT4 changed to WC')
            check(r['mtrr_checks']==4*cpus,'all four hardware phases checked every MTRR readback')
    return r

def audit_pool(pool,metadata,base,frame,framebuffer,pages):
    check(type(pool)is bytes and len(pool)%4096==0 and len(pool)//4096==len(metadata) and 0<len(metadata)<=256,'complete pool/metadata')
    check(set(metadata)<={0,1},'no quarantined tables')
    for i,m in enumerate(metadata):
        if not m:check(pool[i*4096:(i+1)*4096]==bytes(4096),'free table zero')
    seen=set();leaves=[]
    def walk(pa,level,prefix):
        check(base<=pa<base+len(pool) and pa%4096==0 and pa not in seen,'unique in-pool parent, no cycles')
        index=(pa-base)//4096;check(metadata[index]==1,'parent references allocated table');seen.add(pa)
        for slot,e in enumerate(struct.unpack_from('<512Q',pool,pa-base)):
            if e==0:continue
            check(e&1,'present only entries');va=prefix|(slot<<(39-level*9))
            if level==0 and slot>=256:va|=0xffff000000000000
            if level<3 and not(level==2 and e&128):
                check(e&~(MASK|32)==7,'exact ordinary parent flags');walk(e&MASK,level+1,va);continue
            large=level==2 and bool(e&128);check(level==3 or large,'only4K/2M leaves')
            check(not(e&2 and not e&NX) and not e&4 and not e&256,'supervisor nonglobal W^X')
            if large:
                check(e&0x1fe000==0 and e&~(MASK|NX|0x10ff)==0,'valid large leaf')
                cache=e&0x1018;check(cache in (0,24,4096),'known large selector');pa=e&MASK&~0x1fffff;size=0x200000
            else:
                check(e&~(MASK|NX|255)==0,'known leaf bits');cache=e&152;check(cache in (0,24,128),'known4K selector');pa=e&MASK;size=4096
            leaves.append(dict(virtual=va,physical=pa,size=size,entry=e,cache=cache))
    walk(base,0,0)
    check(seen=={base+i*4096 for i,m in enumerate(metadata) if m},'all allocated tables reachable')
    aliases=[x for x in leaves if x['physical']<=frame<x['physical']+x['size']]
    check(len(aliases)==2 and {x['virtual'] for x in aliases}=={A,B} and all(x['size']==4096 and x['physical']==frame for x in aliases),'complete EXEC alias closure')
    by={x['virtual']:x['entry']&~96 for x in aliases}
    check(by=={A:frame|NX|1,B:frame|1},'actual final RO/NX and RX, no writable alias')
    fb=[x for x in leaves if pages and x['physical']<framebuffer+pages*4096 and framebuffer<x['physical']+x['size']]
    for x in fb:check(x['size']==4096 and x['virtual']==HHDM+x['physical'] and x['entry']&~(MASK|96)==NX|131,'every GOP alias exact supervisor WC/RW/NX')
    return dict(tables=len(seen),exec_aliases=aliases,framebuffer_aliases=fb)

class Raw:
    def __init__(self,read,layout,symbols,boot):
        self.read=read;self.types={x['full_name']:x for x in layout['types']};self.symbols=symbols;self.boot=boot
    def field(self,typ,raw,name):
        t=self.types[typ];check(len(raw)==t['size'],'complete typed '+typ);fs=[f for f in t['fields'] if f['name']==name];check(len(fs)==1,'unique field '+name);f=fs[0];return raw[f['offset']:f['offset']+f['size']]
    def number(self,typ,raw,name):
        b=self.field(typ,raw,name);check(len(b)in(1,8),'scalar field '+name);return int.from_bytes(b,'little')
    def kernel(self,module,name,typ,index=0):
        n=self.types[typ]['size'];va=self.symbols[control.storage.symbol(module,name)]+index*n;check(self.symbols['__kernel_data_start']<=va and va+n<=self.symbols['__kernel_bss_end'],'retained global span');return self.read(self.boot[15]+va-control.acpi.KERNEL,n,module+'.'+name+'['+str(index)+']')
    def virtual(self,va,n,role):
        check(va>=0xffff800000000000 and 0<n<=0x200000,'bounded trusted virtual read');out=bytearray()
        while n:
            pa=self.base
            for level,shift in enumerate((39,30,21,12)):
                check(self.base<=pa<self.base+len(self.pool) and pa%4096==0,'virtual walk trusted pool');e=struct.unpack_from('<Q',self.pool,pa-self.base+((va>>shift)&511)*8)[0];check(e&1,'mapped retained input')
                if level==3 or (level==2 and e&128):pa=(e&MASK&~((1<<shift)-1))+(va&((1<<shift)-1));break
                pa=e&MASK
            count=min(n,4096-(va&4095));out.extend(self.read(pa,count,role));va+=count;n-=count
        return bytes(out)
    def record(self,typ,raw):return {f['name']:int.from_bytes(raw[f['offset']:f['offset']+8],'little') for f in self.types[typ]['fields'] if f['size']==8}

def audit_compositor(raw,r):
    # Actual process2 must use the existing arena path under the explicit
    # two-static-pool build; this is independent of compiler text/layout claims.
    s2=raw.kernel('user.memory','SPACES','mm.paging.Space',2)
    check(raw.number('mm.paging.Space',s2,'initialized')==1 and raw.number('mm.paging.Space',s2,'pool_count')==32,'actual pid2 complete ordinary pool')
    def global_u64(name,index):
        va=raw.symbols[control.storage.symbol('user.memory',name)]+index*8
        return struct.unpack('<Q',raw.read(raw.boot[15]+va-control.acpi.KERNEL,8,'actual '+name+'['+str(index)+']'))[0]
    pointer=raw.number('mm.paging.Space',s2,'pool');physical=raw.number('mm.paging.Space',s2,'pool_physical')
    check(pointer==global_u64('DYNAMIC_TABLES',2) and physical==global_u64('DYNAMIC_PHYSICAL',2) and pointer>=0xffffd40000000000 and pointer<0xffffd80000000000,'pid2 exact held arena-backed table ownership')
    data=raw.kernel('user.memory','SPACES','mm.paging.Space',3);count=raw.number('mm.paging.Space',data,'pool_count');base=raw.number('mm.paging.Space',data,'pool_physical')
    check(count==128 and raw.number('mm.paging.Space',data,'initialized')==1,'actual compositor128-table pool')
    pool=raw.read(base,count*4096,'complete compositor private pool');meta=raw.virtual(raw.number('mm.paging.Space',data,'metadata'),count,'complete compositor private metadata')
    check(set(meta)<={0,1},'compositor no pending retirement')
    seen=set();aliases=[]
    def table(pa):
        if base<=pa<base+len(pool):check(pa%4096==0 and meta[(pa-base)//4096]==1,'actual user pool table');return pool,base
        check(raw.base<=pa<raw.base+len(raw.pool) and pa%4096==0,'shared kernel table bound');return raw.pool,raw.base
    def walk(pa,level,prefix):
        check(pa not in seen,'no shared/cyclic compositor parent');seen.add(pa);buf,origin=table(pa)
        for slot,e in enumerate(struct.unpack_from('<512Q',buf,pa-origin)):
            if not e:continue
            check(e&1,'present compositor tree');va=prefix|(slot<<(39-level*9))
            if level==0 and slot>=256:va|=0xffff000000000000
            if level<3 and not(level==2 and e&128):check(e&~(MASK|32)==7,'compositor ordinary parent');walk(e&MASK,level+1,va);continue
            large=level==2 and bool(e&128);check(level==3 or large,'bounded compositor leaves')
            size=0x200000 if large else 4096;physical=e&MASK&~(size-1)
            if physical<r['framebuffer']+r['framebuffer_pages']*4096 and r['framebuffer']<physical+size:
                check(not large,'GOP never large mapped');wanted=NX|131
                if va<0xffff800000000000:
                    check(va==0x60000000+physical-r['framebuffer'],'only exact compositor GOP window');wanted|=4
                else:check(va==HHDM+physical,'only exact shared kernel GOP window')
                check(e&~(MASK|96)==wanted,'all compositor/kernel GOP aliases identical WC type');aliases.append((va,physical))
    walk(base,0,0)
    check({base+i*4096 for i,m in enumerate(meta) if m}=={pa for pa in seen if base<=pa<base+len(pool)},'all allocated compositor tables reachable')
    user=[(v,p)for v,p in aliases if v<0xffff800000000000];kernel=[(v,p)for v,p in aliases if v>=0xffff800000000000]
    check(len(user)==len(kernel)==r['framebuffer_pages'],'full normal compositor and kernel GOP aliases')
    return dict(pid2_arena_pool_physical=physical,pid2_arena_pool_virtual=pointer,compositor_root=base,user_wc_pages=len(user),shared_wc_pages=len(kernel),full_compositor_tree=True)

def audit_mtrr(box,framebuffer,pages):
    """Decode captured hardware MSRs independently of the Dong range planner."""
    check(type(box)is bytes and len(box)==416,'exact raw hardware Box')
    words=struct.unpack('<52Q',box);cap,default,bits=words[13:16]
    check(32<=bits<=52 and cap&255<=16,'bounded actual physical bits/MTRR count')
    check(framebuffer>=0x100000 and pages>0,'fixed low MTRRs disjoint from whole GOP')
    mask=((1<<bits)-1)&~4095;ranges=[]
    kind=default&255 if default&0x800 else 0
    check(kind in (0,1,4,5,6),'actual default MTRR kind')
    for i in range(cap&255):
        base,limit=words[16+i*2:18+i*2]
        if default&0x800 and limit&0x800:
            length=((~limit)&mask)+4096;start=base&mask;t=base&255
            check(length>=4096 and length&(length-1)==0 and start%length==0 and t in (0,1,4,5,6),'actual decoded variable MTRR')
            ranges.append((start,length,t))
    resolved=[]
    for page in range(pages):
        physical=framebuffer+page*4096
        types={t for start,length,t in ranges if start<=physical<start+length}
        if not types:t=kind
        elif 0 in types:t=0
        elif len(types)==1:t=next(iter(types))
        elif types=={4,6}:t=4
        else:raise ValueError('P2 alias: undefined actual MTRR overlap')
        resolved.append(t)
    return dict(default=kind,ranges=ranges,pages=len(resolved),effective_mtrr_types=sorted(set(resolved)))

def verify_bytes(read,layout,symbols,boot,cpus,negative=None):
    raw=Raw(read,layout,symbols,boot);t=raw.types['smp.alias_memory.Report'];check(t['size']==len(FIELDS)*8 and [f['name'] for f in t['fields']]==FIELDS,'real report ABI')
    r=validate_report(raw.record('smp.alias_memory.Report',raw.kernel('smp.alias_memory','REPORT','smp.alias_memory.Report')),cpus,negative)
    work=raw.kernel('boot.memory_startup','WORK','boot.memory_startup.Workspace');space=raw.field('boot.memory_startup.Workspace',work,'space');meta=raw.field('boot.memory_startup.Workspace',work,'table_meta')
    base=raw.number('mm.paging.Space',space,'pool_physical');count=raw.number('mm.paging.Space',space,'pool_count');check(base==r['root'] and count==128,'real private pool identity')
    raw.base=base;raw.pool=read(base,count*4096,'complete alias shared kernel pool')
    tree=audit_pool(raw.pool,meta,base,r['frame'],r['framebuffer'],r['framebuffer_pages'])
    check(tree['tables']==raw.number('mm.paging.Space',space,'used_total'),'actual allocated table ledger')
    check(len(tree['framebuffer_aliases'])==(0 if negative=='pat' else r['framebuffer_pages']),'complete framebuffer revoke/remap count')
    code=struct.unpack('<Q',read(r['frame'],8,'actual owned executable physical bytes'))[0];check(code==(CODE99 if negative=='exec' else CODE43),'actual physical code modified only while writable or by stale mutant')
    exraw=raw.virtual(r['exec_owner'],raw.types['mm.exec_alias_owner.Context']['size'],'actual EXEC Context');ex=raw.record('mm.exec_alias_owner.Context',exraw)
    check(tuple(ex[k] for k in ('bound','poisoned','busy','held','sealed'))==(1,0,0,1,0 if negative=='exec' else 1),'actual held EXEC state')
    check(ex['root']==base and ex['visible']==(1<<cpus)-1,'EXEC all-reader publication')
    boxes=raw.virtual(r['boxes'],16*416,'all actual hardware mailboxes');check(raw.types['smp.alias_memory.Box']['size']==416,'real Box ABI')
    box_records=[raw.record('smp.alias_memory.Box',boxes[i*416:(i+1)*416]) for i in range(cpus)]
    for b in box_records:check(b['sequence']==b['ack'] and b['sequence']>0 and b['root']==base and b['epoch']>0 and b['cr0']&0x80010001==0x80010001 and not b['cr0']&0x60000000 and b['cr4']&32 and not b['cr4']&0x20080,'completed actual hardware mailbox/control readback')
    wcdata=None;mtrr=[]
    if negative!='exec':
        mtrr=[audit_mtrr(boxes[i*416:(i+1)*416],r['framebuffer'],r['framebuffer_pages']) for i in range(cpus)]
        check(all(item==mtrr[0] for item in mtrr),'all actual readers share decoded MTRR ranges and per-GOP-page resolution')
        wcraw=raw.virtual(r['wc_owner'],raw.types['mm.cache_alias_owner.Context']['size'],'actual WC Context');wcdata=raw.record('mm.cache_alias_owner.Context',wcraw)
        check(tuple(wcdata[k] for k in ('bound','poisoned','busy','held','complete','sealed'))==(1,1 if negative=='pat' else 0,0,1,0 if negative=='pat' else 1,0 if negative=='pat' else 1),'actual held WC state')
        check(wcdata['revoked']==wcdata['retired']==wcdata['reclaimed']==r['framebuffer_pages'],'all revoke/receipt/reclaim progress')
        check(wcdata['remapped']==(0 if negative=='pat' else r['framebuffer_pages']),'no remap after failed PAT readback')
        if negative=='pat':check(len({b['pat'] for b in box_records})==2 and wcdata['last_error']==7 and wcdata['phase']==4,'actual differing PAT and original failure')
        else:check(all(b['pat']==r['pat_after'] for b in box_records),'all actual PATs equal selected WC')
        receipts=raw.virtual(r['receipts'],r['framebuffer_pages']*raw.types['mm.paging.Retired']['size'],'all actual retirement receipts')
        for i in range(r['framebuffer_pages']):
            data=receipts[i*raw.types['mm.paging.Retired']['size']:(i+1)*raw.types['mm.paging.Retired']['size']];check(raw.number('mm.paging.Retired',data,'pending')==0,'no retirement reused before completed barrier')
    large=raw.record('smp.large_memory.Report',raw.kernel('smp.large_memory','REPORT','smp.large_memory.Report'));check(large['complete']==1 and large['held']==1 and large['sealed']==1,'prior large owner completed')
    alloc=raw.field('boot.memory_startup.Workspace',work,'allocator');buddy=raw.field('boot.memory_startup.Workspace',work,'page_meta');shared.audit_buddy(alloc,buddy,large)
    arena=raw.number('mm.phys_buddy.Allocator',alloc,'base');check(arena<=r['frame']<arena+1024*4096,'EXEC startup arena ownership');i=(r['frame']-arena)//4096;check(struct.unpack_from('<BB6xQ',buddy,i*16)==(2,0,(1<<64)-1),'exact held order0 frame head')
    check(large['free_before']==r['free_held'] and large['free_after']+512==r['free_held'],'new lease predates prior large baseline')
    graphics=audit_compositor(raw,r) if cpus==4 and negative is None else None
    return dict(report=r,tree=tree,physical_code=code,exec_context=ex,wc_context=wcdata,hardware_boxes=box_records,graphics=graphics,raw_complete=True)

def run(esp,cpus=4,negative=None):
    esp=Path(esp).resolve();verify_build(esp);state=ROOT/'build/test/p2-alias'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True);art=state/'artifacts';art.mkdir()
    for name in ('kernel.elf','dong_layout.json','build-inputs.json','kernel-optimization.json'):shutil.copy2(esp.parent/name,art/name)
    build_manifest=json.loads((esp.parent/'build-inputs.json').read_text());profile=build_manifest['kernel_storage_profile'];shutil.copy2(esp.parent/profile['source'],art/'kernel-storage-profile.dg')
    if negative:
        fixture=json.loads((ROOT/'p2-alias-fixture.json').read_text());check(fixture['kind']==negative,'bound mutant kind')
        shutil.copy2(ROOT/'p2-alias-fixture.json',art/'fixture.json');shutil.copy2(ROOT/'p2-alias-original-source.txt',art/'production-source.txt');shutil.copy2(ROOT/fixture['target'],art/'mutant-source.txt')
    disk=state/'data.img';create(disk,64);disk_before=sha(disk);before=source_hashes();g=None;started=time.monotonic()
    check(all(before.get(k)==v for k,v in build_manifest['source_sha256'].items()),'current sources match every compiled input before boot')
    result=dict(passed=False,cpus=cpus,negative=negative,source_before=before,artifacts_sha256={p.name:sha(p) for p in art.iterdir()},no_guest_memory_or_register_writes=True)
    base=builder.qemu_command
    def command(*a,**kw):
        cmd=base(*a,**kw);cmd[cmd.index('-smp')+1]=str(cpus);return cmd
    try:
        with mock.patch.object(builder,'qemu_command',command):g=control.ResetGuest(esp,disk,state/'guest',control=True)
        g.resume()
        if negative:g.wait(b'smp_runtime_error=',timeout=90)
        elif cpus==4:g.wait(b'DONGOS_P7_DESKTOP_READY',timeout=150)
        else:
            deadline=time.monotonic()+90
            while True:
                time.sleep(.03);g.pause();r=g.global_record('smp.alias_memory','REPORT','smp.alias_memory.Report')
                if r['complete']==1:break
                check(not r['error_code'] and time.monotonic()<deadline,'one CPU failure/timeout');g.resume()
        g.pause();check(len(g.qmp.request('query-cpus-fast'))==cpus,'actual hardware CPU count')
        (state/'registers.txt').write_text(g.qmp.request('human-monitor-command',{'command-line':'info registers -a'}))
        start=len(g.chunks);observed=verify_bytes(g.physical,g.layout,g.symbols,g.boot,cpus,negative);result.update(observed=observed,read_range=[start,len(g.chunks)],boot=list(g.boot),actual_cpu_count=cpus)
        if cpus==4 and not negative:
            first=g.snapshot();control.validate(first,control=True);g.resume();time.sleep(.2);second=g.snapshot();control.validate(second,control=True);control.context.validate_observations(first,second,control=True)
            result.update(p5_control_regression=True,p5_snapshots=[first,second],desktop_ready=True)
        result['passed']=True
    except Exception as e:result['error']=type(e).__name__+': '+str(e)
    finally:
        if g:
            # Save incomplete owner state too, including a precise phase/error.
            try:
                g.pause();result['last_owner_report']=g.global_record('smp.alias_memory','REPORT','smp.alias_memory.Report')
            except Exception as e:result['diagnostic_error']=str(e)
            try:g.close()
            except Exception as e:result.update(passed=False,cleanup_error=str(e))
            result['guest']=g.evidence;result['serial_sha256']=sha(state/'guest/serial.log');result['physical_manifest_sha256']=sha(state/'guest/physical-manifest.json')
        after=source_hashes();result.update(source_after=after,source_unchanged=before==after,disk_before_sha256=disk_before,disk_after_sha256=sha(disk),elapsed_seconds=time.monotonic()-started)
        if before!=after or disk_before!=sha(disk):result.update(passed=False,integrity_error='source or read-only disk changed')
        verify_build(esp);write(state/'result.json',result)
    if result['passed']:
        try:write(state/'replay-result.json',replay(state/'result.json'))
        except Exception as e:
            result.update(passed=False,replay_error=type(e).__name__+': '+str(e));write(state/'result.json',result)
    print(json.dumps(dict(result=str(state/'result.json'),passed=result['passed'],error=result.get('error'),owner=result.get('last_owner_report'))));return result

def replay(path):
    path=Path(path).resolve();state=path.parent;r=json.loads(path.read_text());check(r['passed']is True,'completed result');check(isinstance(r['source_before'],dict) and r['source_before'] and r['source_before']==r['source_after'] and r['source_unchanged']is True and r['no_guest_memory_or_register_writes']is True,'unchanged observation sources')
    expected_artifacts={'kernel.elf','dong_layout.json','build-inputs.json','kernel-optimization.json','kernel-storage-profile.dg'}
    if r['negative']:expected_artifacts|={'fixture.json','production-source.txt','mutant-source.txt'}
    check(set(r['artifacts_sha256'])==expected_artifacts,'complete archived build artifacts')
    for name,digest in r['artifacts_sha256'].items():check(sha(state/'artifacts'/name)==digest,'archived artifact SHA')
    build=json.loads((state/'artifacts/build-inputs.json').read_text())
    check(build['runtime_level']==7 and build['test']is False and build['source_unchanged']is True,'normal completed build')
    check(all(r['source_before'].get(k)==v for k,v in build['source_sha256'].items()),'all observed build sources match actual compiler inputs')
    check(build['kernel_storage_profile']['sha256']==r['artifacts_sha256']['kernel-storage-profile.dg'] and build['kernel_storage_profile']['static_user_pools']==2,'actual generated profile SHA/count')
    for name in ('kernel.elf','kernel-optimization.json'):
        hashes=[v for k,v in build['artifacts'].items() if Path(k).name==name];check(hashes==[r['artifacts_sha256'][name]],'artifact bound to actual build '+name)
    if r['negative']:
        fixture=json.loads((state/'artifacts/fixture.json').read_text());before,after=fixture['production_sha256'],fixture['fixture_sha256'];target=fixture['target']
        check(fixture['kind']==r['negative'] and fixture['changed']==[target] and set(before)==set(after) and [n for n in before if before[n]!=after[n]]==[target],'exact unique hardware semantic mutation')
        check(r['source_before']==after,'actual run bound to entire mutant snapshot')
        check(sha(state/'artifacts/production-source.txt')==before[target]==fixture['original_sha256'] and sha(state/'artifacts/mutant-source.txt')==after[target]==fixture['mutant_sha256'],'actual original and mutated production source bytes')
    check(r['guest']['actual_qemu_executed']is True and r['guest']['cleanup_completed']is True and r['guest']['qemu_returncode']==0 and r['guest']['process_alive']is False,'actual guest completed cleanup')
    manifest=json.loads((state/'guest/physical-manifest.json').read_text());check(sha(state/'guest/physical-manifest.json')==r['physical_manifest_sha256'] and sha(state/'guest/serial.log')==r['serial_sha256'],'raw manifest/UART SHA')
    for item in manifest:
        check(re.fullmatch(r'physical-[0-9]{5,}\.bin',item['file'])is not None,'bounded raw filename');p=state/'guest'/item['file'];check(not p.is_symlink() and p.stat().st_size==item['length'] and sha(p)==item['sha256'],'every physical byte SHA')
    layout=json.loads((state/'artifacts/dong_layout.json').read_text());symbols=control.acpi.validation_symbols(state/'artifacts/kernel.elf');start,end=r['read_range'];cursor=start
    def read(pa,n,role):
        nonlocal cursor
        check(cursor<end,'bounded replay reads');item=manifest[cursor];cursor+=1;check((item['physical'],item['length'],item['role'])==(pa,n,role),'exact raw read identity');return (state/'guest'/item['file']).read_bytes()
    observed=verify_bytes(read,layout,symbols,r['boot'],r['cpus'],r['negative']);check(cursor==end and observed==r['observed'],'independent complete raw replay result')
    return dict(passed=True,raw_recomputed=True,reads=end-start,observed=observed)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reuse-esp',type=Path);p.add_argument('--cpus',type=int,choices=(1,4),default=4);p.add_argument('--negative',choices=('exec','pat'));p.add_argument('--replay',type=Path);a=p.parse_args()
    if a.replay:print(json.dumps(replay(a.replay)));return 0
    p.error('--reuse-esp is required') if not a.reuse_esp else None
    return 0 if run(a.reuse_esp,a.cpus,a.negative)['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
