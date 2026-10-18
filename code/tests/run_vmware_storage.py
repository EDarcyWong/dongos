#!/usr/bin/env python3
"""Private dual-SATA VMware UART/storage verification. Default is preparation only.

Reuse a completed runtime7 ESP and its verified ordinary GPT image. --execute
controls only a new private VM; it requires an otherwise idle VMware host.
No build, Tools installation, host setting change or physical disk access.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys
import threading
import time
import uuid

HERE=Path(__file__).absolute().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
from tests import vmware_support as base
from tools.make_fat32_disk import create,SEED
from tests.vmware_uart_pipe import WindowsPipe,validate_name,RETIRED
BASE=Path(base.__file__).absolute()

check,ordinary,sha,write_json=base.check,base.ordinary,base.sha,base.write_json
RUNS=ROOT/'build/test/vmware/storage'
RAW_NAME=b'VMWPROBETXT'
FILE_NAME='VMWPROBE.TXT'
LIMIT=32*1024*1024


def vmx_fields(text):
    result={}
    for line in text.splitlines():
        match=re.fullmatch(r'([A-Za-z0-9_.:]+) = "([^"\r\n]*)"',line)
        check(match is not None and match[1] not in result,'invalid or duplicate VMX setting')
        result[match[1]]=match[2]
    return result


def pipe_name(run_id):
    check(re.fullmatch('[0-9a-f]{16}',run_id) is not None,'invalid private run ID')
    value='\\\\.\\pipe\\DongOS-storage-'+run_id;validate_name(value);return value


def configuration(run_id):
    fields=vmx_fields(base.configuration(run_id,'sata'))
    fields.update({'displayName':'DongOS storage '+run_id,
      'sata0:0.fileName':'data.vmdk','sata0:1.present':'TRUE',
      'sata0:1.fileName':'boot.vmdk','sata0:1.deviceType':'disk',
      'sata0:1.mode':'persistent','sata0:1.startConnected':'TRUE',
      'serial0.fileType':'pipe','serial0.fileName':pipe_name(run_id),
      'serial0.pipe.endPoint':'server','serial0.tryNoRxLoss':'TRUE'})
    # Only the GPT disk has EFI boot files; the data superfloppy has no loader.
    # Firmware discovery of SATA 0:1 is established by actual UART boot markers.
    return ''.join(f'{key} = "{value}"\n' for key,value in fields.items())


def descriptor(size,run_id,role):
    check(role in ('data','boot'),'invalid private disk role')
    return base.descriptor(size,run_id[:8]).replace('"boot-flat.vmdk"',f'"{role}-flat.vmdk"')


def fat_oracle(path,payload=None):
    """Independent bounded raw FAT32 reader, never imports the writer geometry."""
    path=ordinary(path)
    check(path.stat().st_size==64*1024*1024,'data disk is not the private 64MiB profile')
    with path.open('rb') as disk:
        def read(offset,n):
            check(0<=offset<=path.stat().st_size-n and 0<n<=2*1024*1024,'raw FAT read escaped data disk')
            disk.seek(offset);raw=disk.read(n);check(len(raw)==n,'short raw FAT read');return raw
        boot=read(0,512);check(boot[510:]==b'\x55\xaa','bad data BPB signature')
        bps=struct.unpack_from('<H',boot,11)[0];spc=boot[13];reserved=struct.unpack_from('<H',boot,14)[0]
        fats=boot[16];total=struct.unpack_from('<I',boot,32)[0];size=struct.unpack_from('<I',boot,36)[0]
        root=struct.unpack_from('<I',boot,44)[0];info,backup=struct.unpack_from('<HH',boot,48)
        check((bps,spc,reserved,fats,total)==(512,1,32,2,131072),'unexpected independent FAT geometry')
        check(1<=size<=4096 and 0<info<reserved and 0<backup<reserved and backup+info<reserved,'invalid FAT table/backup fields')
        start=reserved+fats*size;clusters=total-start
        check(65525<=clusters and (clusters+2)*4<=size*512 and 2<=root<clusters+2,'not valid FAT32 cluster geometry')
        check(read(backup*512,512)==boot,'backup BPB differs')
        fsinfo=read(info*512,512)
        check(read((backup+info)*512,512)==fsinfo,'FSInfo backup differs')
        check(struct.unpack_from('<I',fsinfo,0)[0]==0x41615252 and struct.unpack_from('<I',fsinfo,484)[0]==0x61417272
              and struct.unpack_from('<I',fsinfo,508)[0]==0xaa550000,'invalid FSInfo signatures')
        fat=read(reserved*512,size*512);check(read((reserved+size)*512,size*512)==fat,'data FAT mirrors differ')
        check(struct.unpack_from('<I',fat,0)[0]&0xfffffff==0xffffff8,'invalid FAT reserved entry')
        check(struct.unpack_from('<I',fat,4)[0]&0xc000000==0xc000000,'data volume not clean/no-error after sync')
        def chain(cluster):
            seen=set();raw=bytearray()
            while True:
                check(2<=cluster<clusters+2 and cluster not in seen and len(seen)<4096,'invalid/cyclic/oversized data chain')
                seen.add(cluster);raw.extend(read((start+cluster-2)*512,512))
                cluster=struct.unpack_from('<I',fat,cluster*4)[0]&0xfffffff
                if cluster>=0xffffff8:return bytes(raw),seen
                check(cluster<0xffffff0,'reserved/bad cluster in data chain')
        directory,owned=chain(root);entries={}
        for offset in range(0,len(directory),32):
            entry=directory[offset:offset+32]
            if entry[0]==0:break
            if entry[0]==0xe5 or entry[11]&0xf==0xf or entry[11]&8:continue
            check(entry[:11] not in entries,'duplicate raw short name')
            entries[entry[:11]]=entry
        observed={}
        wanted={b'README  TXT':SEED}
        if payload is not None:wanted[RAW_NAME]=payload
        for name,expected in wanted.items():
            check(name in entries,'expected file absent from independent FAT directory: '+repr(name))
            entry=entries[name];check(not entry[11]&0x10,'expected file is a directory')
            length=struct.unpack_from('<I',entry,28)[0];check(length==len(expected),'persisted file length differs')
            first=struct.unpack_from('<H',entry,20)[0]<<16|struct.unpack_from('<H',entry,26)[0]
            data,chain_owned=chain(first)
            check(not owned&chain_owned,'cross-linked independent data chain');owned|=chain_owned
            check(data[:length]==expected,'persisted file bytes differ')
            observed[name.decode('ascii')]={'length':length,'sha256':hashlib.sha256(expected).hexdigest()}
        if payload is None:check(RAW_NAME not in entries,'fresh data disk unexpectedly contains probe file')
        return dict(both_fats_equal=True,clean=True,files=observed,sha256=sha(path),data_start=start,
                    cluster_count=clusters,independent_raw_reader=True)


def phase(state,result,name,**details):
    item=dict(phase=name,utc=base.utc(),monotonic=time.monotonic(),**details)
    result.setdefault('phases',[]).append(item);result['phase']=name
    write_json(state/'phases.json',result['phases'])
    print('VMware storage:',name,flush=True)


def own(state,owner,*,start=False,data_sha=None,first=False):
    ordinary(state,directory=True)
    check(state.parent==RUNS and state.name=='run-'+owner['run_id'],'private VM escaped storage run root')
    check(json.loads(ordinary(state/'owner.json').read_text(encoding='utf-8'))==owner,'VM ownership record changed')
    vmx=ordinary(state/'dongos.vmx');check(str(vmx)==owner['vmx'] and vmx.stat().st_nlink==1,'VMX identity/links differ')
    paths=[ordinary(state/name) for name in ('data-flat.vmdk','boot-flat.vmdk')]
    check(all(p.stat().st_nlink==1 for p in paths) and not os.path.samestat(paths[0].stat(),paths[1].stat()),'disk files alias another file')
    if start:
        check(sha(vmx)==owner['control_sha256']['dongos.vmx'],'VMX changed before own start')
        for name,digest in owner['control_sha256'].items():
            path=ordinary(state/name)
            check(path.stat().st_nlink==1 and sha(path)==digest,'VM control file changed/aliased: '+name)
        check(sha(paths[1])==owner['boot_sha256'],'private boot disk changed')
        check(sha(paths[0])==data_sha,'private data disk changed before boot')
        if first:check(not (state/'dongos.nvram').exists(),'first boot must use fresh NVRAM')
        elif (state/'dongos.nvram').exists():
            check(ordinary(state/'dongos.nvram').stat().st_nlink==1,'private NVRAM aliases another file')


def stop_own(state,owner,commands):
    own(state,owner);result={}
    try:result['before']=commands.running()
    except Exception as exc:result['initial_list_error']=f'{type(exc).__name__}: {exc}'
    try:result['stop_returncode']=commands.run(['-T','ws','stop',owner['vmx'],'hard'])[0]
    except Exception as exc:result['stop_error']=f'{type(exc).__name__}: {exc}'
    result['after']=commands.running()
    result['stopped_verified']=os.path.normcase(owner['vmx']) not in result['after']
    check(result['stopped_verified'],'own VM remains running after stop')
    return result


class Tee:
    def __init__(self,name,output,deadline,live=False,factory=WindowsPipe,clock=time.monotonic):
        validate_name(name);self.name=name;self.output=output;self.deadline=deadline;self.live=live
        self.factory=factory;self.clock=clock;self.stop=threading.Event();self.connected=threading.Event()
        self.lock=threading.Lock();self.raw=bytearray();self.error=None;self.pipe=None;self.events=[]
        self.rx=(output/'uart-rx.bin').open('xb',buffering=0);self.tx=(output/'uart-tx.bin').open('xb',buffering=0)
        self.event_file=(output/'uart-events.jsonl').open('x',encoding='utf-8')
        self.thread=threading.Thread(target=self._worker,daemon=True)

    def event(self,direction,data,offset):
        record=dict(direction=direction,bytes=len(data),offset=offset,monotonic=self.clock(),sha256=hashlib.sha256(data).hexdigest())
        self.events.append(record);self.event_file.write(json.dumps(record)+'\n');self.event_file.flush()

    def _worker(self):
        try:
            self.pipe=self.factory(self.name);self.pipe.connect(self.deadline,self.stop,self.clock);self.connected.set()
            while not self.stop.is_set():
                data=self.pipe.receive()
                if data:
                    with self.lock:
                        check(len(self.raw)+len(data)<=LIMIT,'UART RX exceeds 32MiB')
                        offset=len(self.raw);self.raw.extend(data);self.rx.write(data);self.event('rx',data,offset)
                    if self.live:sys.stdout.buffer.write(data);sys.stdout.buffer.flush()
        except BaseException as exc:
            if not self.stop.is_set():self.error=f'{type(exc).__name__}: {exc}'

    def start(self):self.thread.start()
    def snapshot(self):
        with self.lock:return bytes(self.raw)

    def send(self,data,delay):
        check(self.connected.is_set() and self.pipe is not None,'UART client is not connected')
        for value in data:
            check(self.clock()<self.deadline,'UART command deadline expired')
            byte=bytes((value,));check(self.pipe.write(byte,self.deadline,self.clock)==1,'short UART byte write')
            with self.lock:
                offset=self.tx.tell();self.tx.write(byte);self.event('tx',byte,offset)
            time.sleep(min(delay,max(0,self.deadline-self.clock())))

    def close(self):
        self.stop.set();self.thread.join(2)
        check(not self.thread.is_alive(),'UART reader failed to stop; refusing disk acceptance')
        if self.pipe:self.pipe.close()
        self.rx.close();self.tx.close();self.event_file.close()


def fatal(raw):
    return (base.serial_observations(raw)['guest_failure_observed'] or b'ERROR 0x' in raw
            or b'DONGOS_INIT_RETRY_EXHAUSTED\r\n' in raw)


def wait_for(session,predicate,*,clock=time.monotonic,sleep=time.sleep):
    while clock()<session.deadline:
        raw=session.snapshot()
        check(not fatal(raw),'guest failure observed in actual UART')
        if predicate(raw):return raw
        check(session.error is None,'UART reader failed: '+str(session.error))
        sleep(min(.025,max(0,session.deadline-clock())))
    raise TimeoutError('UART phase deadline expired')


def shell_ready(raw,require_clients=False):
    marker=b'DONGOS_SHELL_READY\r\n';position=raw.find(marker)
    # runtime7 starts the shell and compositor independently. Send no command
    # until the final desktop announcement, which could split UART echo bytes.
    desktop=b'DONGOS_P7_DESKTOP_READY\r\n';at=raw.find(desktop)
    ready=(position>=0 and raw.find(b'\r\n> ',position+len(marker))>=0 and at>=0)
    if require_clients:
        ready=ready and raw.find(b'DONGOS_P7_CLIENTS_READY\r\n',at+len(desktop))>=0
    return ready


def exchange(session,command,expected,delay,*,clock=time.monotonic,sleep=time.sleep):
    check(re.fullmatch(rb'[\x20-\x7e]{1,240}',command) is not None,'unsafe shell probe command')
    start=len(session.snapshot());session.send(command+b'\r',delay)
    raw=wait_for(session,lambda value:value.find(b'\r\n> ',start)>=0,clock=clock,sleep=sleep)
    end=raw.index(b'\r\n> ',start)+len(b'\r\n> ');segment=raw[start:end]
    check(command+b'\r\n' in segment,'fresh UART command echo differs')
    check(expected in segment,'fresh UART command result differs')
    return dict(command=command.decode('ascii'),rx_start=start,rx_end=end,
                rx_sha256=hashlib.sha256(segment).hexdigest(),expected_observed=True)


def boot(state,owner,commands,index,payload,timeout,delay,result,after_commands=None):
    folder=state/f'boot-{index}';folder.mkdir();deadline=time.monotonic()+timeout
    session=Tee(owner['pipe'],folder,deadline,result.get('live',False));record=dict(index=index,passed=False,start_attempted=False,simulated=result.get('simulated',False))
    result.setdefault('boots',[]).append(record);session.start()
    try:
        phase(state,result,f'boot{index}_start_attempt')
        record['start_attempted']=True
        code,_,_=commands.run(['-T','ws','start',owner['vmx'],'nogui'])
        record['start_returncode']=code;check(code==0,'vmrun start failed')
        running=commands.running();record['own_vm_observed_running']=os.path.normcase(owner['vmx']) in running
        check(record['own_vm_observed_running'],'successful start absent from running list')
        phase(state,result,f'boot{index}_wait_shell')
        require_clients=result.get('require_client_ready',False)
        raw=wait_for(session,lambda value:shell_ready(value,require_clients));record['pipe_connected']=session.connected.is_set()
        record['required_gui_clients_ready_observed']=require_clients
        for marker in (b'DONGOS_AHCI_READY',b'DONGOS_BLK_READY',b'DONGOS_FS_READY'):
            check(raw.splitlines().count(marker)==1,'missing/duplicate actual AHCI/block/FS marker: '+marker.decode())
        phase(state,result,f'boot{index}_shell_uart_commands')
        sequence=[]
        if index==1:sequence.append((b'write '+FILE_NAME.encode()+b' '+payload,b'WRITE OK\r\n'))
        sequence += [(b'cat '+FILE_NAME.encode(),payload+b'\r\n'),(b'ls',FILE_NAME.encode()+b' '+str(len(payload)).encode()+b'\r\n'),(b'sync',b'SYNC OK\r\n')]
        record['commands']=[exchange(session,cmd,expected,delay) for cmd,expected in sequence]
        if after_commands is not None:after_commands(session,record)
        record['passed']=True
    finally:
        if record['start_attempted']:
            phase(state,result,f'boot{index}_stop_own')
            try:record['cleanup']=stop_own(state,owner,commands)
            except Exception as exc:record.update(passed=False,cleanup_error=f'{type(exc).__name__}: {exc}')
        try:session.close()
        except Exception as exc:record.update(passed=False,pipe_cleanup_error=f'{type(exc).__name__}: {exc}')
        raw=session.snapshot();record['serial']=base.serial_observations(raw)
        record['pipe_connected']=session.connected.is_set()
        record['uart_rx_sha256']=hashlib.sha256(raw).hexdigest()
        if (folder/'uart-tx.bin').exists():
            record['uart_tx_bytes']=(folder/'uart-tx.bin').stat().st_size
            record['uart_tx_sha256']=sha(folder/'uart-tx.bin')
        record['kernel_entries_observed']=raw.splitlines().count(b'DONGOS_P1_KERNEL_HIGH_OK')
        if not record['serial']['bootstrap_markers_observed_in_order'] or fatal(raw):record['passed']=False
        write_json(folder/'result.json',record)
    check(record['passed'] and record.get('cleanup',{}).get('stopped_verified'),'boot/UART/own cleanup did not complete')
    return record


def prepare(state,run_id,args,result):
    phase(state,result,'verify_completed_build_and_gpt')
    source=ordinary(args.image);check(source.suffix.lower()=='.img','boot source must be ordinary .img')
    esp=ordinary(args.reuse_esp,directory=True);metadata,digest=base.verify_build(esp)
    expected={name:dict(length=item['length'],sha256=item['sha256']) for name,item in base.usb._source(esp).items() if item['kind']=='file'}
    observed=base.usb.inspect_image(source,expected);write_json(state/'source-image-before.json',observed)
    result.update(source_image=str(source),source_esp=str(esp),source_image_sha256=observed['image_sha256'],build_inputs_sha256=digest)
    write_json(state/'build-inputs.json',metadata)
    phase(state,result,'create_private_dual_disks')
    base.copy_verified_image(source,state/'boot-flat.vmdk',observed['image_sha256'])
    check(not (state/'data-flat.vmdk').exists(),'data disk already exists');geometry=create(state/'data-flat.vmdk',64)
    initial=fat_oracle(state/'data-flat.vmdk');write_json(state/'data-before.json',initial)
    controls={'dongos.vmx':configuration(run_id),'data.vmdk':descriptor(64*1024*1024,run_id,'data'),
              'boot.vmdk':descriptor(observed['image_bytes'],run_id,'boot')}
    for name,text in controls.items():
        with (state/name).open('x',encoding='utf-8',newline='\n') as stream:stream.write(text)
    owner=dict(run_id=run_id,vmx=str(state/'dongos.vmx'),pipe=pipe_name(run_id),
      boot_sha256=observed['image_sha256'],control_sha256={name:sha(state/name) for name in controls},created_utc=base.utc())
    write_json(state/'owner.json',owner);own(state,owner,start=True,data_sha=initial['sha256'],first=True)
    result.update(prepared_verified=True,data_geometry=geometry,data_initial_sha256=initial['sha256'],
                  pipe=owner['pipe'],disk_roles={'sata0:0':'private data FAT32 superfloppy','sata0:1':'private verified GPT boot copy'},
                  planned_start=[str(args.vmrun),'-T','ws','start',owner['vmx'],'nogui'],
                  planned_stop=[str(args.vmrun),'-T','ws','stop',owner['vmx'],'hard'])
    phase(state,result,'prepared_no_vm_started')
    return owner,controls,initial,expected


def probe(args,*,boot_runner=None,extra_inputs=()):
    if not RUNS.exists():RUNS.mkdir(parents=True)
    ordinary(RUNS,directory=True);run_id=uuid.uuid4().hex[:16];state=RUNS/('run-'+run_id);state.mkdir()
    result=dict(passed=False,prepared_verified=False,execute_requested=args.execute,actual_vmware_start_attempts=0,
      actual_vmware_boots=0,evidence_directory=str(state),live=args.live,
      require_client_ready=getattr(args,'require_client_ready',False),
      p5_complete_accepted=False,p7_pixels_or_memory_accepted=False,p7_fps_accepted=False,kvm_accepted=False,bare_metal_accepted=False)
    dependencies=[Path(__file__),HERE/'vmware_uart_pipe.py',BASE,ROOT/'tools/make_usb_image.py',ROOT/'tools/make_fat32_disk.py']
    dependencies.extend(extra_inputs)
    fingerprints={str(p):sha(ordinary(p)) for p in dependencies};result['runner_inputs']=fingerprints
    owner=commands=None;expected=None
    try:
        owner,controls,initial,expected=prepare(state,run_id,args,result)
        payload=('DongOS VMware persistence '+run_id).encode('ascii');result['payload']=payload.decode('ascii')
        if not args.execute:
            result.update(passed=True,outcome='prepared_only_no_vm_started')
        else:
            check(os.name=='nt','actual VMware pipe execution requires Windows')
            vmrun=ordinary(args.vmrun);result['vmrun_sha256']=sha(vmrun)
            commands=base.Commands(state,vmrun,Path(owner['vmx']))
            _,help_text,help_error=commands.run([])
            check('Usage: vmrun' in help_text+help_error and 'nogui' in help_text+help_error,'installed vmrun help differs')
            check(not commands.running(),'another VM is running; this probe requires an idle VMware host')
            data_hash=initial['sha256']
            for index in (1,2):
                own(state,owner,start=True,data_sha=data_hash,first=index==1)
                check(sha(vmrun)==result['vmrun_sha256'],'vmrun executable changed')
                (boot if boot_runner is None else boot_runner)(state,owner,commands,index,payload,args.timeout,args.char_delay,result)
                phase(state,result,f'boot{index}_independent_fat_after_verified_stop')
                check(sha(state/'boot-flat.vmdk')==owner['boot_sha256'],'guest modified boot disk instead of private data disk')
                disk=fat_oracle(state/'data-flat.vmdk',payload);write_json(state/f'data-after-boot-{index}.json',disk)
                check((disk['sha256']!=data_hash) if index==1 else (disk['sha256']==data_hash),
                      'write boot did not change data disk, or read-only second boot changed it')
                data_hash=disk['sha256']
                if index==1:
                    # VMware may change CID/VMX generated metadata. Archive it,
                    # then restore our exact safe control allowlist while stopped.
                    for name,text in controls.items():
                        check(ordinary(state/name).stat().st_nlink==1,'VM-generated control file aliases another file')
                        (state/'boot-1'/('vmware-'+name)).write_bytes((state/name).read_bytes())
                        (state/name).write_text(text,encoding='utf-8',newline='\n')
            result.update(passed=True,outcome='two_boot_uart_and_independent_fat_passed',storage_persistence_observed=True)
    except Exception as exc:
        result.update(passed=False,outcome='probe_error',error=f'{type(exc).__name__}: {exc}')
    finally:
        if commands is not None:
            result['actual_vmware_start_attempts']=sum(record['argv'][3:4]==['start'] for record in commands.records)
            result['actual_vmware_boots']=sum(bool(item.get('own_vm_observed_running') or item.get('kernel_entries_observed')) for item in result.get('boots',[]))
            result['kernel_entries_observed']=sum(item.get('kernel_entries_observed',0) for item in result.get('boots',[]))
            result['actual_uart_connections']=sum(bool(item.get('pipe_connected')) for item in result.get('boots',[]))
            try:
                running=commands.running();result['running_vms_after']=running
                if owner is not None and os.path.normcase(owner['vmx']) in running:result['final_cleanup']=stop_own(state,owner,commands)
                result['own_vm_stopped_verified']=owner is not None and os.path.normcase(owner['vmx']) not in commands.running()
                check(result['own_vm_stopped_verified'],'own VM cleanup cannot be confirmed')
            except Exception as exc:
                result.update(passed=False,cleanup_error=f'{type(exc).__name__}: {exc}',own_vm_may_require_cleanup=owner['vmx'] if owner else None)
                if owner is not None and result['actual_vmware_start_attempts']:
                    try:result['fallback_cleanup']=stop_own(state,owner,commands)
                    except Exception as retry:result['fallback_cleanup_error']=f'{type(retry).__name__}: {retry}'
        try:
            check(all(sha(path)==digest for path,digest in fingerprints.items()),'runner dependency changed')
            result['runner_inputs_unchanged']=True
            if expected is not None:
                after=base.usb.inspect_image(args.image,expected);write_json(state/'source-image-after.json',after)
                check(after['image_sha256']==result['source_image_sha256'],'original GPT image changed')
                _,digest=base.verify_build(args.reuse_esp);check(digest==result['build_inputs_sha256'],'build fingerprints changed')
                result['original_image_and_build_unchanged']=True
        except Exception as exc:result.update(passed=False,identity_error=f'{type(exc).__name__}: {exc}')
        result['retired_overlapped_operations']=len(RETIRED)
        if RETIRED:result.update(passed=False,uart_cancellation_incomplete=True)
        result['finished_utc']=base.utc();write_json(state/'result.json',result)
    print('VMware storage',result.get('outcome'),state,result.get('error',''),flush=True)
    return 0 if result['passed'] else 1


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path);parser.add_argument('--reuse-esp','--esp',dest='reuse_esp',type=Path)
    parser.add_argument('--vmrun',type=Path,default=base.DEFAULT_VMRUN)
    parser.add_argument('--timeout',type=float,default=120);parser.add_argument('--char-delay',type=float,default=.003)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--live',action='store_true')
    parser.add_argument('--require-client-ready',action='store_true',help='new independent-GUI builds: wait for all four clients and first presentations before UART input')
    parser.add_argument('--selftest',action='store_true')
    args=parser.parse_args(argv)
    if args.selftest:
        check(not args.execute,'selftest cannot execute VMs')
        from tests import test_vmware_storage
        return test_vmware_storage.run()
    if args.image is None or args.reuse_esp is None:parser.error('--image and --reuse-esp are required; no auto-build exists')
    if not 5<=args.timeout<=300 or not .001<=args.char_delay<=.05:parser.error('timeout/char-delay out of bounded range')
    return probe(args)


if __name__=='__main__':raise SystemExit(main())
