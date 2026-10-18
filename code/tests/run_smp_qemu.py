#!/usr/bin/env python3
"""Serial real SMP/TLB and persistent CPL3 service gate, with physical oracles."""
from pathlib import Path
import argparse,hashlib,json,re,struct,sys,uuid
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import build as builder
from tools.make_fat32_disk import create
from tests import run_services_qemu as services
from tests import run_acpi_qemu as acpi

ROOT=builder.ROOT
FIELDS=('version cpu_count online ping_acks iterations gpr_checks xstate_checks stress_errors overlap_start overlap_end '
        'tlb_broadcasts tlb_sent tlb_acks tlb_invalidations tlb_full tlb_probes reclaimed tables_before tables_after low_pages '
        'context_pointer stress_pointer domain_pointer mailbox_pointer marker_a marker_b steps error_code').split()
BASE_PROJECT=services.project
BASE_VERIFY=services.verify
PROBE=0xffffc80012345000

def parse(serial,count=4):
    start=serial.index(b'DONGOS_P6_SMP_START\r\n')
    stop=serial.index(b'DONGOS_P6_SMP_READY\r\n')+len(b'DONGOS_P6_SMP_READY\r\n')
    pairs=re.findall(rb'^smp_([a-z_]+)=0x([0-9a-f]{16})\r$',serial[start:stop],re.MULTILINE)
    if [n.decode() for n,_ in pairs]!=FIELDS:raise ValueError('SMP report shape/order differs')
    data={n.decode():int(v,16) for n,v in pairs}
    exact=dict(version=1,cpu_count=count,online=count,ping_acks=count-1,iterations=count*2097152,
        gpr_checks=count*1536,xstate_checks=count*512,stress_errors=0,reclaimed=3,low_pages=count-1,
        tlb_probes=2,steps=31,error_code=0,marker_a=0x1122334455667788,marker_b=0x8877665544332211)
    if any(data[n]!=v for n,v in exact.items()):raise ValueError('actual SMP report failed')
    if data['overlap_start']>=data['overlap_end'] or data['tables_before']!=data['tables_after']:
        raise ValueError('no real parallel overlap or table retirement leak')
    if data['tlb_sent']!=data['tlb_acks'] or data['tlb_sent']!=data['tlb_broadcasts']*(count-1):
        raise ValueError('serial IPI acknowledgement mismatch')
    return data,serial[:start]+serial[stop:]

def project(serial,symbols):
    _,old=parse(serial)
    return BASE_PROJECT(old,symbols)

def verify(qmp,state,serial,build):
    original=BASE_VERIFY(qmp,state,serial,build)
    data,_=parse(serial)
    symbols=acpi.validation_symbols(build/'kernel.elf')
    manifest=[]
    def physical(pa,n,role):
        if not 0<pa<1<<48 or not 0<n<=1<<20:raise ValueError('unsafe SMP physical read')
        path=state/f'smp-physical-{len(manifest):03d}.bin'
        qmp.request('pmemsave',dict(val=pa,size=n,filename=str(path.resolve())))
        raw=path.read_bytes()
        if len(raw)!=n:raise ValueError('incomplete SMP dump')
        manifest.append(dict(physical=pa,length=n,role=role,file=path.name,sha256=hashlib.sha256(raw).hexdigest()))
        return raw
    _,_,_,_,prior=project(serial,symbols)
    old=prior['hardening']['memory']['fields']
    boot=struct.unpack('<20Q',physical(old['runtime_boot_info']-acpi.HHDM,160,'BootInfo'))
    root=old['root_physical']
    def kernel(va,n,role):
        if not symbols['__kernel_text_start']<=va<=symbols['__kernel_bss_end']-n:raise ValueError('SMP pointer escaped kernel')
        return physical(boot[15]+va-services.KERNEL,n,role)
    def glob(module,name,n):return kernel(symbols[services.symbol(module,name)],n,module+'.'+name)
    pages={}
    def pte(va):
        current=root
        for shift in (39,30,21,12):
            if current%4096 or not root<=current<root+128*4096:raise ValueError('SMP page table escaped exclusive pool')
            if current not in pages:pages[current]=physical(current,4096,'kernel page table')
            entry=struct.unpack_from('<Q',pages[current],((va>>shift)&511)*8)[0]
            if not entry&1:return entry
            if shift==12:
                if entry&4:raise ValueError('AP supervisor leaf is user accessible')
                return entry
            if entry&128:raise ValueError('unexpected AP large mapping')
            current=entry&services.MASK
    def virtual(va,n,role):
        result=bytearray()
        while n:
            entry=pte(va)
            if not entry&1:raise ValueError('missing actual AP mapping')
            step=min(n,4096-(va&4095));result.extend(physical((entry&services.MASK)+(va&4095),step,role))
            va+=step;n-=step
        return bytes(result)
    if glob('smp.runtime','INFO',224)!=struct.pack('<28Q',*(data[n] for n in FIELDS)):
        raise ValueError('SMP physical report differs from serial')
    contexts=glob('smp.runtime','CPUS',4096)
    domain=struct.unpack('<14Q',glob('smp.runtime','DOMAIN',112))
    boxes=kernel(data['mailbox_pointer'],1024,'TLB mailboxes')
    stress=kernel(data['stress_pointer'],1024,'actual per CPU stress')
    lows=struct.unpack('<16Q',glob('smp.runtime','LOW',128))
    if domain[0:2]!=(1,0) or domain[2:5]!=(data['context_pointer'],4,data['mailbox_pointer']) or domain[13]!=0:
        raise ValueError('live TLB domain not safely quiescent')
    if domain[6]!=domain[7] or domain[8]!=domain[9] or domain[8]!=domain[7]*3 or sum(domain[10:13])!=domain[7] or domain[12]!=2:
        raise ValueError('live TLB accounting inconsistent')
    if domain[7]<data['tlb_broadcasts']:raise ValueError('live TLB domain regressed')
    registers=qmp.request('human-monitor-command',{'command-line':'info registers -a'})
    (state/'all-cpu-registers.txt').write_text(registers)
    cpus=re.split(r'CPU#\d+\s*',registers)[1:]
    if len(cpus)!=4:raise ValueError('four actual QEMU CPUs required')
    ranges=[];guard_count=0;starts=[];ends=[]
    for i in range(4):
        c=struct.unpack_from('<32Q',contexts,i*256)
        s=struct.unpack_from('<8Q',stress,i*64)
        if c[:6]!=(data['context_pointer']+i*256,i,i,4,1,root) or c[25]!=1 or c[31]!=0:
            raise ValueError('actual CPU identity/state/root differs')
        if s[:6]!=(1,2097152,(data['marker_a']+i+2097152*(i+1))&((1<<64)-1),1536,512,0) or not s[6]<s[7]:
            raise ValueError('per CPU actual compute/check counters failed')
        starts.append(s[6]);ends.append(s[7])
        if i==0:continue
        r=cpus[i]
        values={n:int(re.search(n+r'=([0-9a-fA-F]+)',r)[1],16) for n in ('RIP','CR0','CR3','CR4','EFER')}
        if values!={'RIP':symbols['smp_ap_idle']+2,'CR0':c[6],'CR3':c[5],'CR4':c[7],'EFER':c[8]} or 'CPL=0' not in r or 'HLT=1' not in r:
            raise ValueError('AP actual hardware state differs from online context')
        for pattern,expected in ((r'GS =\w+ ([0-9a-fA-F]+)',c[0]),(r'GDT=\s+([0-9a-fA-F]+)',c[13]),(r'IDT=\s+([0-9a-fA-F]+)',c[15]),(r'TR =\w+ ([0-9a-fA-F]+)',c[14])):
            if int(re.search(pattern,r)[1],16)!=expected:raise ValueError('AP actual GS/GDT/IDT/TSS differs')
        if c[26:30]!=(1,1,0,0) or c[30]!=domain[7]+1:raise ValueError('AP real ping/TLB IPI count differs')
        b=struct.unpack_from('<8Q',boxes,i*64)
        if b[0]!=domain[6] or b[3]!=domain[6] or b[5:]!=(data['marker_b'],0,0):raise ValueError('AP final TLB mailbox differs')
        for bottom,top in ((c[11],c[12]),(c[16],c[17]),(c[18],c[19]),(c[20],c[21])):
            if top-bottom!=16384 or bottom%4096 or pte(bottom-4096)!=0 or pte(top)!=0:raise ValueError('AP stack guard absent')
            guard_count+=2;ranges.append((bottom,top))
            for va in range(bottom,top,4096):
                if pte(va)&0x800000000000001f!=0x8000000000000003:raise ValueError('AP stack not WB/RW/NX supervisor')
        tss=virtual(c[14],104,'AP actual TSS')
        if struct.unpack_from('<Q',tss,4)[0]!=c[12] or [struct.unpack_from('<Q',tss,36+n*8)[0] for n in range(3)]!=[c[17],c[19],c[21]] or struct.unpack_from('<H',tss,102)[0]!=104:
            raise ValueError('AP private TSS stack contract differs')
        idt=virtual(c[15],4096,'AP actual IDT')
        for vector,target in ((0xf1,'smp_ping_entry'),(0xf2,'smp_tlb_entry')):
            gate=idt[vector*16:vector*16+16]
            address=struct.unpack_from('<H',gate)[0]|struct.unpack_from('<H',gate,6)[0]<<16|struct.unpack_from('<I',gate,8)[0]<<32
            if address!=symbols[target] or gate[5]!=0x8e:raise ValueError('AP real IPI IDT gate differs')
        if not 0<lows[i]<0xa0000 or pte(lows[i])!=0 or pte(0xffffc00000200000+i*4096)!=0:raise ValueError('SIPI aliases not retired')
        trampoline=physical(lows[i],4096,'executed SIPI trampoline')
        offset=lambda name:symbols[name]-symbols['smp_trampoline_start']
        if struct.unpack_from('<I',trampoline,offset('smp_trampoline_stage'))[0]!=2 or struct.unpack_from('<Q',trampoline,offset('smp_trampoline_context'))[0]!=c[0] or struct.unpack_from('<I',trampoline,offset('smp_trampoline_cr3'))[0]!=root:
            raise ValueError('executed SIPI patch/state differs')
    if max(starts)!=data['overlap_start'] or min(ends)!=data['overlap_end']:raise ValueError('serial overlap fabricated')
    if any(a<d and c<b for n,(a,b) in enumerate(ranges) for c,d in ranges[n+1:]):raise ValueError('AP stack ranges overlap')
    if pte(PROBE)!=0 or guard_count!=24:raise ValueError('retired probe or AP guards differ')
    mtrr=struct.unpack('<48Q',kernel(symbols['smp_mtrr_snapshot'],384,'BSP synchronized MTRR snapshot'))
    if mtrr[0]!=1 or mtrr[3]!=mtrr[1]&255 or mtrr[3]>16 or not 32<=mtrr[47]<=52:raise ValueError('MTRR snapshot invalid')
    services.write_json(state/'smp-physical-manifest.json',manifest)
    original['smp']=dict(report=data,live_domain=list(domain),actual_cpus_verified=4,ap_stack_guards_verified=guard_count,
        physical_reads=len(manifest),private_gdt_tss_idt_verified=True,real_ipi_and_tlb_probe_verified=True)
    return original

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--reuse-esp',type=Path);args=parser.parse_args()
    state=ROOT/'build/test/p6-smp/qemu'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
    paths=sorted(p for tree in ('kernel','services','include','boot','tools','tests','lang/dongc','lang/std') for p in (ROOT/tree).rglob('*') if p.suffix in ('.dg','.asm','.inc','.ld','.py','.c'))
    hashes=lambda:{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    before=hashes();services.write_json(state/'source-before.json',before)
    esp=args.reuse_esp.resolve() if args.reuse_esp else builder.build(test=True,runtime_level=6,output=state/'build')
    disk=state/'disk.img';create(disk,64)
    with mock.patch.object(services,'project',project),mock.patch.object(services,'verify',verify):
        results=[services.boot_once(esp,disk,state/'write',['write PROBE.TXT '+services.PAYLOAD.decode(),'cat PROBE.TXT','sync','exit'])]
        if results[0]['passed']:
            services.check_disk(disk)
            results.append(services.boot_once(esp,disk,state/'reboot',['cat PROBE.TXT','ls','exit']))
    after=hashes();services.write_json(state/'source-after.json',after)
    passed=len(results)==2 and before==after and all(r['passed'] for r in results)
    services.write_json(state/'result.json',dict(passed=passed,source_unchanged=before==after,results=results))
    print('P6 SMP+services','PASS' if passed else 'FAIL',state)
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
