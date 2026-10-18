#!/usr/bin/env python3
"""Inspect real bracketed clock calibration; reuse an existing build, never build.

Examples:
  python -m tests.run_clock_calibration_qemu --reuse-esp BUILD/esp
  python -m tests.run_clock_calibration_qemu --reuse-esp BUILD/esp --no-hpet
  python -m tests.run_clock_calibration_qemu --self-test
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import build as builder
from tools.elf_symbols import read_elf_symbols
from tools.make_fat32_disk import create
from tests import run_acpi_qemu as acpi, run_services_qemu as storage

ROOT=builder.ROOT
MAX=(1<<64)-1
ERR=0x03060000
REFERENCE_FIELDS=('mask','period_fs','hz')
SAMPLE_FIELDS=('r0_before','c0','t0','r0_after','r1_before','c1','t1','r1_after')
ESTIMATE_FIELDS=('reference_lower','reference_upper','ns_lower','ns_upper','tsc_lower_hz','tsc_upper_hz',
                 'lapic_lower_hz','lapic_upper_hz','tsc_hz','lapic_hz','uncertainty_ppm')
RESULT_FIELDS=('total','accepted','rejected','consistent','accepted_mask','selected_mask',
               'tsc_lower_hz','tsc_upper_hz','tsc_hz','lapic_lower_hz','lapic_upper_hz','lapic_hz',
               'median_tsc_hz','median_lapic_hz','tightest_index','reference_delta','uncertainty_ppm')
PLATFORM_FIELDS=('lapic_pa','lapic_va','lapic_id','lapic_version','ioapic_count','redirection_count',
                 'pic_master','pic_slave','reference_source','tsc_hz','lapic_hz','timer_mode','interval_ns',
                 'last_tsc','last_deadline','arm_count','stop_count','spurious_vector','timer_vector','cr4',
                 'rflags','ref_period_fs','ref_delta','steps')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def check(condition,message):
    if not condition:raise ValueError(message)
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
def ceildiv(n,d):return (n+d-1)//d
def median(values):
    values=sorted(values);n=len(values)
    return values[n//2] if n%2 else (values[n//2-1]+values[n//2])//2


class Rejected(ValueError):
    def __init__(self,number,reason):self.code=ERR+number;super().__init__(reason)


def validate_reference(reference):
    mask,period,hz=(reference[n] for n in REFERENCE_FIELDS)
    if mask not in ((1<<24)-1,(1<<32)-1,MAX):raise Rejected(2,'unsupported reference mask')
    if period:
        if hz or not 1000<=period<=100_000_000:raise Rejected(2,'invalid HPET period or mixed clock units')
        horizon=ceildiv(25_000_000*1_000_000,period)
    else:
        if not 1_000_000<=hz<=1_000_000_000:raise Rejected(2,'invalid exact reference rate')
        horizon=ceildiv(25_000_000*hz,1_000_000_000)
    if horizon>=mask//2+1:raise Rejected(4,'supported horizon reaches the ambiguous half-cycle')


def estimate(reference,sample):
    """Conservative quantized-clock interval arithmetic, using Python big ints."""
    validate_reference(reference)
    mask,period,hz=(reference[n] for n in REFERENCE_FIELDS)
    r0,c0,t0,r0a,r1,c1,t1,r1a=(sample[n] for n in SAMPLE_FIELDS)
    if any(not 0<=value<=MAX for value in sample.values()):raise Rejected(3,'sample outside unsigned range')
    if any(v>mask for v in (r0,r0a,r1,r1a)) or t1<=t0 or c0>(1<<32)-1 or not 0<c1<c0:
        raise Rejected(3,'counter reset, overflow, backwards TSC, or exhausted APIC timer')
    # Modular subtraction independently expresses the forward clock ordering.
    a,b,c=((value-r0)&mask for value in (r0a,r1,r1a))
    if c+1>=mask//2+1 or not a<=b<=c:raise Rejected(4,'reference endpoints wrap ambiguously or go backwards')
    if b-a<=1:raise Rejected(3,'reference endpoints have no positive interior')
    lower,upper=b-a-1,c+1
    scale,denominator=(period,1_000_000) if period else (1_000_000_000,hz)
    products=(lower*scale,upper*scale)
    if max(products)>MAX:raise Rejected(7,'reference multiplication exceeds production u64')
    ns_lower,ns_upper=products[0]//denominator,ceildiv(products[1],denominator)
    if not 5_000_000<=ns_lower<ns_upper<=25_000_000:raise Rejected(6,'reference duration outside 5–25 ms horizon')
    first,second=a+1,c-b+1
    if first*100>lower or second*100>lower or (first+second)*50>lower:
        raise Rejected(5,'reference endpoint uncertainty exceeds 1% per endpoint / 2% combined')
    dt,dc=t1-t0,c0-c1
    if dt<=1 or dc<=1 or dt==MAX:raise Rejected(3,'insufficient or overflowing measured counter span')
    numerators=((dt-1)*1_000_000_000,(dt+1)*1_000_000_000,(dc-1)*1_000_000_000,(dc+1)*1_000_000_000)
    if max(numerators)>MAX:raise Rejected(7,'rate multiplication exceeds production u64')
    tl,th=numerators[0]//ns_upper,ceildiv(numerators[1],ns_lower)
    ll,lh=numerators[2]//ns_upper,ceildiv(numerators[3],ns_lower)
    if not 1_000_000<=tl<=th<=16_000_000_000 or not 1000<=ll<=lh<=4_000_000_000:
        raise Rejected(6,'frequency bounds outside supported TSC/APIC rates')
    return dict(zip(ESTIMATE_FIELDS,(lower,upper,ns_lower,ns_upper,tl,th,ll,lh,(tl+th)//2,(ll+lh)//2,
                                     (upper-lower)*1_000_000//lower)))


def select(reference,samples):
    """Find maximum 2D frequency-plane coverage, independently of DG subsets."""
    validate_reference(reference)
    if not 3<=len(samples)<=7:raise Rejected(1,'sample count outside bounded policy')
    estimates=[];errors=[];qualified=[]
    for index,sample in enumerate(samples):
        try:value=estimate(reference,sample)
        except Rejected as exc:
            estimates.append(dict(error=exc.code,reason=str(exc)));errors.append(exc.code)
        else:
            estimates.append(value);errors.append(0);qualified.append(index)
    if len(qualified)<3:raise Rejected(8,'fewer than three bounded samples')
    # Any nonempty intersection has its maximum lower TSC/APIC coordinates at
    # input edges. Sweep their Cartesian grid and deduplicate maximal cover sets.
    clusters=set();best=0
    for x in qualified:
        for y in qualified:
            fx,fy=estimates[x]['tsc_lower_hz'],estimates[y]['lapic_lower_hz']
            covered=frozenset(i for i in qualified if estimates[i]['tsc_lower_hz']<=fx<=estimates[i]['tsc_upper_hz']
                              and estimates[i]['lapic_lower_hz']<=fy<=estimates[i]['lapic_upper_hz'])
            if len(covered)>best:best=len(covered);clusters={covered}
            elif len(covered)==best:clusters.add(covered)
    if best<3 or len(clusters)!=1:raise Rejected(9,'no unique largest simultaneous frequency consensus')
    selected=sorted(next(iter(clusters)));tight=min(selected,key=lambda i:(estimates[i]['uncertainty_ppm'],i))
    tl=max(estimates[i]['tsc_lower_hz'] for i in selected);th=min(estimates[i]['tsc_upper_hz'] for i in selected)
    ll=max(estimates[i]['lapic_lower_hz'] for i in selected);lh=min(estimates[i]['lapic_upper_hz'] for i in selected)
    mt=median([estimates[i]['tsc_hz'] for i in selected]);ml=median([estimates[i]['lapic_hz'] for i in selected])
    result=dict(zip(RESULT_FIELDS,(len(samples),len(qualified),len(samples)-len(qualified),best,
        sum(1<<i for i in qualified),sum(1<<i for i in selected),tl,th,min(th,max(tl,mt)),ll,lh,min(lh,max(ll,ml)),
        mt,ml,tight,(estimates[tight]['reference_lower']+estimates[tight]['reference_upper'])//2,estimates[tight]['uncertainty_ppm'])))
    result['errors']=errors+[0]*(7-len(samples))
    return result,estimates


def unpack_record(data,fields):
    check(len(data)==8*len(fields),'raw record length differs from fixed ABI')
    return dict(zip(fields,struct.unpack('<'+'Q'*len(fields),data)))


def verify_layout(path):
    document=json.loads(Path(path).read_text(encoding='utf-8'));types={x['full_name']:x for x in document['types']}
    for name,fields in (('Reference',REFERENCE_FIELDS),('Sample',SAMPLE_FIELDS),('Estimate',ESTIMATE_FIELDS),('Result',RESULT_FIELDS+('errors',))):
        item=types['irq.clock_calibration.'+name];size=192 if name=='Result' else len(fields)*8
        check(item['size']==size and item['alignment']==8,'clock '+name+' size/alignment changed')
        check([(x['name'],x['offset']) for x in item['fields']]==[(name,i*8) for i,name in enumerate(fields)],'clock '+name+' field offsets changed')
    item=types['irq.platform.Report']
    check(item['size']==192 and [(x['name'],x['offset']) for x in item['fields']]==[(name,i*8) for i,name in enumerate(PLATFORM_FIELDS)],'platform report 24-Qword ABI changed')


class ClockGuest:
    """Root-only real QEMU runner; its only guest operations are QMP/read-only dumps."""
    def __init__(self,esp,state,no_hpet,timeout,runtime_level):
        self.state=state;self.esp=esp;self.no_hpet=no_hpet;self.timeout=timeout;self.runtime_level=runtime_level
        self.process=self.qmp=self.uart=self.reader=self.stderr=None;self.raw=bytearray();self.chunks=[]
        self.evidence=dict(actual_qemu_executed=False,no_hpet=no_hpet)
    def start(self):
        disk=self.state/'disk.img';create(disk,64)
        up,qp=storage.free_port(),storage.free_port()
        command=builder.qemu_command(self.esp,self.state/'guest',test=True)
        i=command.index('isa-debug-exit,iobase=0xf4,iosize=0x04');del command[i-1:i+1]
        if self.no_hpet:command[command.index('-machine')+1]='q35,hpet=off'
        command[command.index('-serial')+1]=f'tcp:127.0.0.1:{up},server=on,wait=off'
        command+=['-cpu','max,+smep,+smap,+umip,-tsc-deadline','-S','-qmp',f'tcp:127.0.0.1:{qp},server=on,wait=off',
                  '-drive',f'if=none,id=data,format=raw,cache=writeback,file={disk.resolve().as_posix()}',
                  '-device','virtio-blk-pci,drive=data,disable-legacy=on','-device','virtio-tablet-pci']
        self.evidence['command']=command;self.stderr=(self.state/'stderr.log').open('wb')
        self.process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=self.stderr);self.evidence['actual_qemu_executed']=True
        self.qmp=acpi.QMP(qp,self.process);self.uart=socket.create_connection(('127.0.0.1',up));self.uart.settimeout(.2)
        def read_uart():
            with (self.state/'serial.log').open('wb') as stream:
                while self.process.poll() is None:
                    try:data=self.uart.recv(4096)
                    except socket.timeout:continue
                    except OSError:break
                    if not data:break
                    self.raw.extend(data);stream.write(data);stream.flush()
        self.reader=threading.Thread(target=read_uart,daemon=True);self.reader.start();self.qmp.request('cont')
        marker=b'DONGOS_P7_DESKTOP_READY\r\n' if self.runtime_level>=7 else b'DONGOS_P3_THREADS_READY\r\n'
        self.evidence['completion_marker']=marker.decode().strip()
        deadline=time.monotonic()+self.timeout
        while marker not in self.raw:
            check(self.process.poll() is None,'QEMU terminated before actual calibration/preemption completion')
            check(b'DONGOS_P1_KERNEL_FAIL' not in self.raw and b'PANIC' not in self.raw,'actual guest kernel failure')
            if time.monotonic()>=deadline:raise TimeoutError('actual completed runtime marker missing: '+repr(marker))
            time.sleep(.02)
        self.qmp.request('stop')
        check(bytes(self.raw).count(b'DONGOS_P3_IRQ_READY\r\n')==1,'IRQ-ready marker not unique')
        self.symbols=read_elf_symbols(self.esp.parent/'kernel.elf')
        memory={k.decode():int(v,16) for k,v in re.findall(rb'^memory_([a-z_]+)=0x([0-9a-f]{16})\r?$',self.raw,re.MULTILINE)}
        check('runtime_boot_info' in memory,'actual relocated BootInfo address absent')
        self.boot=struct.unpack('<20Q',self.physical(memory['runtime_boot_info']-acpi.HHDM,160,'actual BootInfo'))
        check(self.boot[15]>0 and self.boot[15]%4096==0,'kernel physical base invalid')
    def physical(self,pa,n,role):
        check(0<pa<1<<48 and 0<n<=1<<24 and pa+n<=1<<48,'unsafe read-only physical span')
        path=self.state/f'physical-{len(self.chunks):05d}.bin'
        self.qmp.request('pmemsave',dict(val=pa,size=n,filename=str(path.resolve())))
        data=path.read_bytes();check(len(data)==n,'truncated physical dump')
        self.chunks.append(dict(physical=pa,length=n,role=role,file=path.name,sha256=hashlib.sha256(data).hexdigest()))
        return data
    def kernel(self,va,n,role):
        check(self.symbols['__kernel_text_start']<=va<=self.symbols['__kernel_bss_end']-n,'clock read escaped retained kernel span')
        return self.physical(self.boot[15]+va-storage.KERNEL,n,role)
    def global_data(self,name,n):
        address=self.symbols[storage.symbol('irq.platform',name)]
        check(self.symbols['__kernel_bss_start']<=address<=self.symbols['__kernel_bss_end']-n,'clock global not retained in kernel BSS')
        return self.kernel(address,n,'irq.platform.'+name)
    def verify_code(self):
        image=(self.esp.parent/'kernel.elf').read_bytes();check(image[:4]==b'\x7fELF' and image[4:6]==b'\x02\x01','unsupported kernel ELF')
        offset=struct.unpack_from('<Q',image,32)[0];stride,count=struct.unpack_from('<HH',image,54);total=0
        for index in range(count):
            kind,flags,off,address,_,size,_,_=struct.unpack_from('<IIQQQQQQ',image,offset+index*stride)
            if kind==1 and flags&1 and size:
                check(off+size<=len(image),'truncated kernel executable segment')
                check(self.kernel(address,size,'actual linked executable kernel segment')==image[off:off+size],'actual executable kernel differs from hashed linked ELF')
                total+=size
        check(total>0,'no actual kernel executable bytes inspected');return total
    def capture_firmware(self):
        # Existing independent ACPI discovery validates RSDP/XSDT and every
        # child SDT checksum. Its reader additionally enforces the real UEFI
        # ACPI ownership map before any original firmware byte is inspected.
        entries=acpi.read_map(self.physical(self.boot[4],self.boot[5],'actual UEFI map'),self.boot[6])
        def read(pa,n):
            check(acpi.acpi_range(entries,pa,n),'firmware read escaped original ACPI ownership')
            return self.physical(pa,n,'original checked ACPI firmware')
        discovery=acpi.reference.discover_with_tables(read,self.boot[14])
        wanted=[item for item in discovery['tables'] if item['signature'] in ('FACP','SSDT')]
        dsdt=discovery['inventory']['dsdt']
        if dsdt:
            header=read(dsdt,36);length=struct.unpack_from('<I',header,4)[0]
            check(header[:4]==b'DSDT' and 36<=length<=1<<20,'original FADT DSDT pointer/length invalid')
            raw=read(dsdt,length);check(raw[:36]==header and sum(raw)%256==0,'original DSDT changed or checksum invalid')
            wanted.append(dict(physical=dsdt,length=length,signature='DSDT',sha256=hashlib.sha256(raw).hexdigest()))
        saved=[]
        for index,item in enumerate(wanted):
            raw=read(item['physical'],item['length'])
            check(hashlib.sha256(raw).hexdigest()==item['sha256'] and sum(raw)%256==0,'original firmware table changed after discovery')
            path=self.state/f"acpi-{index:02d}-{item['signature']}.bin";path.write_bytes(raw)
            saved.append(dict(**item,file=path.name,checksum_verified=True))
        write(self.state/'acpi-tables.json',dict(inventory=discovery['inventory'],checked_tables=discovery['tables'],saved=saved))
        return saved
    def capture(self):
        actual_code=self.verify_code()
        reference=unpack_record(self.global_data('CALIBRATION_REFERENCE',24),REFERENCE_FIELDS)
        sample_bytes=self.global_data('CALIBRATION_SAMPLES',7*64)
        samples=[unpack_record(sample_bytes[i*64:(i+1)*64],SAMPLE_FIELDS) for i in range(7)]
        result_bytes=self.global_data('CALIBRATION_RESULT',192)
        result=unpack_record(result_bytes[:136],RESULT_FIELDS);result['errors']=list(struct.unpack('<7Q',result_bytes[136:]))
        count=struct.unpack('<Q',self.global_data('CALIBRATION_COUNT',8))[0]
        ready=self.global_data('CALIBRATION_READY',1)
        platform=unpack_record(self.global_data('INFO',192),PLATFORM_FIELDS)
        reference_source=struct.unpack('<Q',self.global_data('REFERENCE',8))[0]
        check(count==7 and ready==b'\x01','actual seven-sample calibration did not publish successfully')
        check(platform['timer_mode']==2,'clock runner did not exercise actual LAPIC fallback calibration')
        check(reference_source in ((3,4) if self.no_hpet else (2,)),'actual reference differs from HPET/PM command line case')
        if self.no_hpet:check(reference['period_fs']==0 and reference['hz']==3579545,'PM reference lost exact rational units')
        else:check(reference['period_fs']==platform['ref_period_fs'] and reference['hz']==0,'HPET reference differs from actual advertised period')
        expected,estimates=select(reference,samples)
        for field in (*RESULT_FIELDS,'errors'):check(result[field]==expected[field],'actual selection differs from independent frequency-plane oracle: '+field)
        check(result['consistent']>=3 and result['accepted']+result['rejected']==7,'actual consensus does not meet minimum')
        check(platform['lapic_hz']==result['lapic_hz'] and platform['ref_delta']==result['reference_delta'],'selected APIC/ref counts not used by platform')
        if platform['reference_source']==1:
            check(1_000_000<=platform['tsc_hz']<=16_000_000_000,'CPUID-derived trusted TSC rate outside supported range')
            tsc_source='CPUID leaf 0x15 preserved; sample result independently checked'
        else:
            check(platform['reference_source']==reference_source and platform['tsc_hz']==result['tsc_hz'],'selected TSC rate not used by platform')
            tsc_source='actual bounded sample consensus'
        # Record what the old stale single-point formula would infer, without
        # substituting those values or a host rate into the production report.
        old_rates=[]
        for sample in samples:
            ticks=(sample['r1_before']-sample['r0_before'])&reference['mask']
            numerator,denominator=(ticks*reference['period_fs'],1_000_000) if reference['period_fs'] else (ticks*1_000_000_000,reference['hz'])
            ns=numerator//denominator
            old_rates.append((sample['t1']-sample['t0'])*1_000_000_000//ns if ns else None)
        serial_rates=re.findall(rb'^platform_tsc_hz=0x([0-9a-f]{16})\r?$',self.raw,re.MULTILINE)
        check(len(serial_rates)==1 and int(serial_rates[0],16)==platform['tsc_hz'],'serial TSC report detached from actual memory')
        firmware=self.capture_firmware()
        return dict(reference=reference,samples=samples,result=result,independent_estimates=estimates,
                    independent_result=expected,platform=platform,actual_reference_source=reference_source,
                    actual_kernel_rx_bytes_verified=actual_code,raw_records_sha256=hashlib.sha256(sample_bytes+result_bytes).hexdigest(),
                    old_stale_single_point_hz=old_rates,tsc_source=tsc_source,actual_count=count,calibration_ready=True,
                    checked_original_firmware_tables=firmware)
    def close(self):
        if self.qmp:
            try:self.qmp.request('quit')
            except Exception:pass
            self.qmp.close()
        if self.uart:self.uart.close()
        if self.process:
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
            self.evidence['qemu_shutdown_returncode']=self.process.returncode
        if self.reader:self.reader.join(timeout=2)
        if self.stderr:self.stderr.close()
        write(self.state/'physical-manifest.json',self.chunks)


def verify_build(esp):
    build=esp.parent;description=json.loads((build/'build-inputs.json').read_text(encoding='utf-8'))
    check(description['runtime_level']>=4 and description['graphics_case'] is None and description['smp_case'] is None
          and description['source_unchanged'],'existing build is not a completed normal runtime build')
    for name,expected in description['artifacts'].items():
        path=Path(name) if Path(name).is_absolute() else build/name
        check(sha(path)==expected,'actual completed build artifact changed: '+name)
    for name,expected in description['source_sha256'].items():check(sha(ROOT/name)==expected,'source differs from existing build: '+name)
    check('kernel/irq/clock_calibration.dg' in description['source_sha256'],'existing build predates bracketed clock policy')
    verify_layout(build/'dong_layout.json')
    return description


def self_test():
    """Exercise only Python arithmetic; no tools, build or guest process runs."""
    references=[dict(mask=mask,period_fs=period,hz=hz) for mask,period,hz in
                (((1<<24)-1,10_000_000,0),((1<<32)-1,30_000_000,0),(MAX,1000,0),((1<<24)-1,0,3579545),(MAX,0,3579545))]
    cases=0
    for reference in references:
        def sample(first,second,rate=3_410_000_000):
            origin=reference['mask']-100
            def ticks(ns):return ns*1_000_000//reference['period_fs'] if reference['period_fs'] else ns*reference['hz']//1_000_000_000
            a,b,c,d=first//3,first*2//3,10_000_000+second//3,10_000_000+second*2//3
            return dict(zip(SAMPLE_FIELDS,(origin,(1<<32)-1-a*62_500_000//1_000_000_000,1_000_000_000+b*rate//1_000_000_000,
                (origin+ticks(first))&reference['mask'],(origin+ticks(10_000_000))&reference['mask'],
                (1<<32)-1-c*62_500_000//1_000_000_000,1_000_000_000+d*rate//1_000_000_000,(origin+ticks(10_000_000+second))&reference['mask'])))
        samples=[sample(1_350_000,1000),sample(1_200_000,1000)]+[sample(1000+i*1000,2000+i*1000) for i in range(5)]
        result,values=select(reference,samples)
        check(result['accepted']==5 and result['selected_mask']==124 and result['errors'][:2]==[ERR+5,ERR+5],'self-test endpoint jitter not rejected')
        check(abs(result['tsc_hz']-3_410_000_000)<10_000_000,'self-test physical frequency not recovered')
        for item in values[2:]:check(item['tsc_lower_hz']<=3_410_000_000<=item['tsc_upper_hz'] and item['lapic_lower_hz']<=62_500_000<=item['lapic_upper_hz'],'self-test lost true rate bounds')
        tied=[sample(1000,1000,rate) for rate in [3_410_000_000]*3+[3_000_000_000]*3]
        try:select(reference,tied)
        except Rejected as exc:check(exc.code==ERR+9,'wrong tied-cluster rejection')
        else:raise AssertionError('self-test tied clusters accepted')
        cases+=1
    return dict(passed=True,actual_qemu_executed=False,full_build_executed=False,reference_cases=cases,
                endpoint_jitter_and_wrap=True,physical_rate_bounds=True,ambiguous_consensus_rejected=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp',type=Path,help='existing normal runtime4+ ESP; this runner never builds')
    parser.add_argument('--no-hpet',action='store_true',help='disable HPET and inspect the exact-frequency ACPI PM timer path')
    parser.add_argument('--timeout',type=float,default=90)
    parser.add_argument('--self-test',action='store_true',help='pure independent arithmetic only; never starts QEMU')
    args=parser.parse_args()
    if args.self_test:
        value=self_test();print(json.dumps(value,indent=2));return 0
    if not args.reuse_esp:parser.error('--reuse-esp is required unless --self-test is used; automatic builds are prohibited')
    check(1<=args.timeout<=300,'invalid bounded timeout')
    state=ROOT/'build/test/clock-calibration/qemu'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
    files=[Path(__file__),ROOT/'tests/run_acpi_qemu.py',ROOT/'tests/acpi_reference.py',ROOT/'tests/run_services_qemu.py',ROOT/'tools/build.py',ROOT/'tools/elf_symbols.py',ROOT/'tools/make_fat32_disk.py']
    before={str(p.relative_to(ROOT)):sha(p) for p in files};write(state/'source-before.json',before)
    result=dict(passed=False,actual_qemu_executed=False,full_build_executed=False,no_hpet=args.no_hpet,source_sha256=before)
    guest=None;description={};started=time.monotonic()
    try:
        esp=args.reuse_esp.resolve();description=verify_build(esp);result['build_inputs_verified']=True
        result['build_input_sha256']=sha(esp.parent/'build-inputs.json');result['build_source_sha256']=description['source_sha256']
        result['build_artifact_sha256']=description['artifacts'];result['layout_sha256']=sha(esp.parent/'dong_layout.json')
        guest=ClockGuest(esp,state,args.no_hpet,args.timeout,description['runtime_level']);guest.start();result.update(guest.evidence)
        result['clock']=guest.capture();result['passed']=True
    except Exception as exc:result['error']=f'{type(exc).__name__}: {exc}'
    finally:
        if guest:
            try:guest.close()
            except Exception as exc:result.update(passed=False,error=f'cleanup failed: {type(exc).__name__}: {exc}')
            result.update(guest.evidence)
        after={str(p.relative_to(ROOT)):sha(p) for p in files};write(state/'source-after.json',after)
        unchanged=before==after and all(sha(ROOT/name)==expected for name,expected in description.get('source_sha256',{}).items())
        result['source_unchanged']=unchanged;result['elapsed_seconds']=time.monotonic()-started
        if not unchanged:result.update(passed=False,error='source changed during real calibration verification')
        write(state/'result.json',result)
    print('Actual clock calibration','PASS' if result['passed'] else 'FAIL',state,result.get('error',''))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
