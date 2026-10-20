#!/usr/bin/env python3
"""Disposable modern VirtIO initialized-queue crash/reset/hold observation only.
No shell kill, guest memory/register writes, production backdoor or physical disk.
Run from the prepared source fixture against its completed normal runtime7 ESP.
"""
from pathlib import Path
import argparse, hashlib, json, re, socket, struct, subprocess, sys, threading, time, uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests import run_process_lifecycle_qemu as life
from tests import p5_virtio_reset_fixture as fixture
from tools.build_usb import verify_build
from tools.make_fat32_disk import create

settings, storage, nvme = life.settings, life.storage, life.nvme
builder, acpi = settings.builder, settings.acpi
check=settings.check

def validate(s, control=False):
    check(s['identity']==0x10421af4 and s['lease']['pages']==32,'wrong controller/whole lease')
    check(s['lease']['physical']>0 and s['lease']['physical']%131072==0
          and s['lease']['state']==2 and s['lease']['mapped']==32
          and s['lease']['attempted']==32 and s['lease']['root']==s['root'] and s['root']>0
          and s['pinned']==1 and s['memory_ready']==1,'DMA no longer completely held')
    if control:
        check(s['reset_state']==0 and s['reset_owner']==0 and s['reset_token']==0
              and s['snapshot']['state']==2 and s['snapshot']['process']!=0
              and s['status']==15,'control did not remain normally initialized')
        return
    check(s['fault_rip']==s['expected_fault_rip'] and s['fault_instruction']=='0f0b','fault not at linked UD2 fixture')
    check(s['pending']['token']==0 and s['pending']['incarnation']==0 and s['pending']['event']==0 and s['pending']['affinity']==0,'deferred old owner remains')
    check(s['reset_state']==2 and s['reset_owner']==s['owner'] and s['owner']!=0
          and s['reset_token']==s['device_token'] and s['device_token']!=0,'missing exact reset receipt')
    check(s['snapshot']['state']==4 and s['snapshot']['status']==6
          and s['snapshot']['process']==0 and s['catalog_slot']==life.NONE
          and s['configuration']==life.NONE,'actual block #UD termination not established')
    check(s['status']==0 and s['command']&0x406==0x402 and s['quarantined']==1,'controller reset/isolation missing')
    check(s['domain_ready']==1 and s['domain_failed']==0 and s['bridge_failed']==0
          and all(s['domain_process'][k]==0 for k in ('token','root','frame','xstate','retiring','retirement'))
          and s['queue_thread']['state']==0 and s['queue_thread']['frame']==0
          and s['completed']>0,'scheduler retirement absent')
    check(s['online']==15 and len(s['cpus'])==4,'online CPU evidence incomplete')
    for cpu in s['cpus']:
        check(cpu['token']==0 or cpu['token']&255!=3,'old owner still selected on CPU')
        check(not(cpu['captured']!=0 and cpu['captured_token']&255==3),'active old capture remains')
        check(not(cpu['mode'] in (2,6) and cpu['return_root']==s['root']),'active old return root remains')
        check(cpu['block_seen']['valid']==0,'old block translation tag remains valid')
        check(cpu['acknowledged']>=s['completed'],'online CPU lacks completed barrier acknowledgement')

class ResetGuest(life.ProcessGuest):
    """Reuse read-only decoders, but not normal-desktop-ready constructor."""
    def __init__(self,esp,disk,state):
        self.esp,self.disk,self.state=esp,disk,state;state.mkdir()
        self.raw=bytearray();self.chunks=[];self.tables={};self.stopped=False
        self.process=self.qmp=self.uart=None
        self.evidence=dict(actual_qemu_executed=False,no_guest_memory_or_register_writes=True)
        self.kernel_memory_layout=nvme.check_kernel_memory_layout(esp)
        self.types={t['full_name']:t for t in json.loads((esp.parent/'dong_layout.json').read_text())['types']}
        up,qp=storage.free_port(),storage.free_port()
        command=builder.qemu_command(esp,state/'guest',test=True)
        i=command.index('isa-debug-exit,iobase=0xf4,iosize=0x04');del command[i-1:i+1]
        command[command.index('-serial')+1]=f'tcp:127.0.0.1:{up},server=on,wait=off'
        command += ['-cpu','max,+smep,+smap,+umip','-S','-qmp',f'tcp:127.0.0.1:{qp},server=on,wait=off',
                    '-drive',f'if=none,id=data,format=raw,cache=writeback,file={disk.resolve().as_posix().replace(chr(44),chr(44)*2)}',
                    '-device','virtio-blk-pci,drive=data,disable-legacy=on','-device','virtio-tablet-pci']
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
                        try:data=self.uart.recv(4096)
                        except socket.timeout:continue
                        except OSError:break
                        if not data:break
                        self.raw.extend(data);stream.write(data);stream.flush()
            self.reader=threading.Thread(target=reader,daemon=True);self.reader.start()
            self.qmp.request('cont')
            deadline=time.monotonic()+90
            while not re.search(rb'^memory_runtime_boot_info=0x[0-9a-f]{16}\r?$',bytes(self.raw),re.M):
                check(self.process.poll() is None and time.monotonic()<deadline,'BootInfo UART timeout/exit')
                time.sleep(.02)
            self.pause();self.symbols=acpi.validation_symbols(esp.parent/'kernel.elf')
            matches=re.findall(rb'^memory_runtime_boot_info=0x([0-9a-f]{16})\r?$',bytes(self.raw),re.M)
            check(len(matches)==1,'missing unique complete BootInfo address')
            self.boot=struct.unpack('<20Q',self.physical(int(matches[0],16)-acpi.HHDM,160,'BootInfo'))
        except BaseException:self.close();raise
    def record(self,name,address,index=0):
        t=self.types[name];raw=self.virtual_kernel(address+index*t['size'],t['size'],name)
        return {f['name']:int.from_bytes(raw[f['offset']:f['offset']+f['size']],'little')
                for f in t['fields'] if f['size']<=8}
    def global_record(self,module,name,typ,index=0):
        return self.record(typ,self.ksym(module,name),index)
    def snapshot(self):
        self.pause();catalog=self.catalog()
        lease=self.global_record('user.memory','DMA_LEASES','user.memory.DmaLease',2)
        p=self.global_record('user.memory','PROCESSES','user.memory.Process',2)
        ecam=self.kval('user.devices','SELECTED')
        check(ecam>0 and ecam%4096==0,'selected ECAM unavailable')
        config=self.physical(ecam,256,'selected PCI configuration')
        identity,command=struct.unpack_from('<IH',config)
        pos=config[52];seen=set();common=None
        while pos:
            check(64<=pos<=252 and pos%4==0 and pos not in seen and len(seen)<48,'malformed capability list')
            seen.add(pos);kind,nxt=config[pos],config[pos+1]
            if kind==9 and pos<=240 and config[pos+3]==1:
                check(config[pos+2]>=16,'short common capability')
                bar=config[pos+4];check(bar<6,'invalid common BAR')
                offset,length=struct.unpack_from('<II',config,pos+8)
                grant=self.global_record('user.devices','BARS','drivers.virtio_pci.Bar',bar)
                check(length>=56 and offset<=grant['length'] and length<=grant['length']-offset,'common outside trusted BAR')
                common=grant['physical']+offset;break
            pos=nxt
        check(common is not None,'modern common configuration missing')
        status=self.physical(common+20,1,'device_status')[0]
        bridge=self.record('sched.user_bridge.Bridge',self.kval('sched.user_bridge','ACTIVE'))
        domain=self.record('sched.user_domain.Domain',bridge['domain'])
        cpus=[self.record('sched.user_domain.Cpu',domain['cpus'],i) for i in range(16) if domain['online']&(1<<i)]
        pt=self.types['user.memory.Process'];fields={f['name']:f['offset'] for f in pt['fields']}
        process_at=self.ksym('user.memory','PROCESSES')+2*pt['size']
        frame=self.record('user.abi.Frame',process_at+fields['frame'])
        plan=self.record('exec.elf.Plan',process_at+fields['plan'])
        elf_symbols=life.read_elf_symbols(self.esp.parent/'services/block/program.elf')
        expected_fault_rip=plan['load_bias']+elf_symbols['svc_user_ud2']
        self.roots=[0,0,p['root']]
        self.pool_limits=list(struct.unpack('<16Q',self.kernel(self.ksym('user.memory','POOL_LIMITS'),128,'table pool limits')))
        instruction=self.user(2,expected_fault_rip,2,'actual linked fault instruction').hex()
        for cpu in cpus:cpu['block_seen']=self.record('sched.user_domain.Seen',cpu['seen'],2)
        engine_fields={f['name']:f['offset'] for f in self.types['sched.multicore.Engine']['fields']}
        queue_thread=self.record('sched.multicore.Thread',domain['engine']+engine_fields['threads'],2)
        owner=self.kval('user.device_host','PCI_OWNERS')
        check(owner==((3<<32)|catalog['incarnations'][2]),'owner differs from real Catalog incarnation')
        return dict(fault_rip=frame['rip'],expected_fault_rip=expected_fault_rip,fault_instruction=instruction,
            pending=self.record('sched.user_bridge.Pending',bridge['pending'],2),identity=identity,command=command,status=status,lease=lease,root=p['root'],memory_ready=p['ready'],
            pinned=self.kernel(self.ksym('user.memory','PINNED')+2,1,'block PINNED')[0],
            quarantined=self.kernel(self.ksym('user.devices','BLOCK_QUARANTINED'),1,'quarantine')[0],
            owner=owner,device_token=self.kval('user.device_host','PCI_TOKENS'),
            reset_state=self.kval('user.devices','BLOCK_RESET_STATE'),
            reset_owner=self.kval('user.device_host','BLOCK_RESET_OWNER'),reset_token=self.kval('user.device_host','BLOCK_RESET_TOKEN'),
            snapshot=catalog['snapshots'][2],catalog_slot=catalog['slots'][2],configuration=catalog['configurations'][2],
            bridge_failed=bridge['failed'],domain_ready=domain['ready'],domain_failed=domain['failed'],completed=domain['completed'],online=domain['online'],
            queue_thread=queue_thread,domain_process=self.record('sched.user_domain.Process',domain['processes'],2),cpus=cpus)
    def close(self):
        try:settings.Guest.close(self)
        finally:
            if self.process is not None and self.process.poll() is None:
                self.process.kill();self.process.wait(timeout=5)
            self.evidence['qemu_stopped']=self.process is None or self.process.poll() is not None
            storage.write_json(self.state/'guest.json',self.evidence)
        check(self.evidence['qemu_stopped'],'own QEMU process did not stop')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp',type=Path,required=True)
    parser.add_argument('--control',action='store_true',help='normal unmodified initialized-device control')
    args=parser.parse_args();esp=args.reuse_esp.resolve();root=Path(__file__).resolve().parents[1]
    if not args.control:fixture.verify(root)
    elif (root/'p5-reset-fixture.json').exists() or 'svc_user_ud2' in (root/fixture.TARGET).read_text():raise ValueError('control must use unmodified source root')
    verify_build(esp)
    state=root/'build/test/p5-reset-guest'/('run-'+uuid.uuid4().hex)
    check(not any(p.is_symlink() for p in state.parents),'symlink state ancestor')
    state.mkdir(parents=True)
    disk=state/'data.img';check(not disk.exists() and not disk.is_symlink(),'disk path already exists')
    create(disk,64);before=fixture.digest(disk);guest=None
    result=dict(passed=False,scope='initialized-queue-crash-reset-hold-only',control=args.control,
                outstanding_io_proven=False,dma_reuse_proven=False,restart_proven=False,
                build_manifest_sha256=fixture.digest(esp.parent/'build-inputs.json'),
                kernel_elf_sha256=fixture.digest(esp.parent/'kernel.elf'),
                block_elf_sha256=fixture.digest(esp.parent/'services/block/program.elf'),
                fixture_manifest_sha256=None if args.control else fixture.digest(root/'p5-reset-fixture.json'))
    try:
        guest=ResetGuest(esp,disk,state/'guest');deadline=time.monotonic()+90;last=None
        while time.monotonic()<deadline:
            try:
                guest.pause()
                check(guest.kval('user.services','CATALOG')!=0 and guest.kval('sched.user_bridge','ACTIVE')!=0,'scheduler/catalog not initialized yet')
                if not args.control and guest.kval('user.devices','BLOCK_RESET_STATE')!=2:
                    raise ValueError('trusted reset not yet completed')
                s=guest.snapshot();validate(s,args.control);last=None;break
            except (ValueError,KeyError,struct.error) as error:last=str(error)
            guest.resume();time.sleep(.1)
        else:raise TimeoutError('reset evidence not reached: '+str(last))
        guest.resume();time.sleep(.2);second=guest.snapshot();validate(second,args.control)
        check(second['lease']==s['lease'] and second['root']==s['root'],'held lease changed after observation')
        result.update(snapshots=[s,second],passed=True)
    except Exception as error:result['error']=f'{type(error).__name__}: {error}'
    finally:
        if guest is not None:
            try:guest.close();result['guest']=guest.evidence
            except Exception as error:result.update(passed=False,cleanup_error=str(error))
        try:
            check(fixture.digest(disk)==before,'read-only fixture disk changed')
            verify_build(esp)
            if not args.control:fixture.verify(root)
        except Exception as error:result.update(passed=False,integrity_error=str(error))
        storage.write_json(state/'result.json',result)
    print(state/'result.json');return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
