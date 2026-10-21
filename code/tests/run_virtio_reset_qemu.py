#!/usr/bin/env python3
"""Disposable modern VirtIO initialized-queue crash/reset/hold observation only.
No shell kill, guest memory/register writes, production backdoor or physical disk.
Run from the prepared source fixture against its completed normal runtime7 ESP.
"""
from pathlib import Path
import argparse, hashlib, json, re, shutil, socket, struct, subprocess, sys, threading, time, uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests import run_process_lifecycle_qemu as life
from tests import p5_virtio_reset_fixture as fixture
from tests import p5_recovery_context_guest as context
from tools.build_usb import verify_build
from tools.make_fat32_disk import create

settings, storage, nvme = life.settings, life.storage, life.nvme
builder, acpi = settings.builder, settings.acpi
check=settings.check

# Current immutable Catalog contract: GUI applications are AUTOSTART|ORDINARY.
# Do not normalize raw evidence to the older lifecycle runner's flags=8 expectation.
def decode_catalog(raw):
    settings.check(len(raw)==life.CATALOG_BYTES,'catalog must have the completed exact ABI size')
    ready,count,sequence=struct.unpack_from('<3Q',raw)
    settings.check((ready,count)==(1,18),'kernel catalog is not initialized with 18 admitted configurations')
    configs=[]
    for index in range(32):
        offset=24+index*128;fields=struct.unpack_from('<8Q',raw,offset)
        version,identifier,deps,retries,timeout,flags,image,length=fields
        name=raw[offset+64:offset+96];reserved=raw[offset+96:offset+128]
        settings.check(version==1 and reserved==bytes(32),'config version/reserved field differs')
        if index<18:
            expected_flags=7 if index in (0,1,3,6) else (5 if index<7 else (4 if index==13 else (9 if index>=14 else 8)))
            settings.check(identifier==index and deps==life.DEPS[index] and image==index+1
                           and flags==expected_flags and retries==(3 if index in (0,1,3,6) else 0)
                           and timeout>0 and 0<length<=32 and name[:length]==life.NAMES[index].encode()
                           and name[length:]==bytes(32-length),'admitted configuration or dependency DAG differs')
        else:
            settings.check(fields==(1,0,0,0,0,0,0,0) and name==bytes(32),'unused configuration is not empty')
        configs.append(dict(id=identifier,name=name[:length].decode('ascii'),dependencies=deps,
                            retries=retries,timeout=timeout,flags=flags,image=image))
    offset=24+32*128
    snapshots=[]
    for index in range(32):
        version,configuration,process,generation,state,status,event_sequence,argument=struct.unpack_from('<8Q',raw,offset+index*64)
        settings.check(version==1 and configuration==index and state<=5 and event_sequence<=sequence,
                       'snapshot version/configuration/state/sequence differs')
        snapshots.append(dict(configuration=configuration,process=process,generation=generation,state=state,
                              status=status,sequence=event_sequence,argument=argument))
    offset+=32*64
    slots=list(struct.unpack_from('<32Q',raw,offset));offset+=256
    incarnations=list(struct.unpack_from('<16Q',raw,offset));offset+=128
    configurations=list(struct.unpack_from('<16Q',raw,offset));offset+=128
    for index,snapshot in enumerate(snapshots):
        token=snapshot['process']
        if token:
            slot=slots[index]
            settings.check(index<18 and slot<16 and (slot==13 if index==13 else slot!=13) and configurations[slot]==index
                           and 0<incarnations[slot]<=0x0fffffff
                           and token==(incarnations[slot]<<8)|(slot+1)
                           and snapshot['generation']>0 and snapshot['state'] in (1,2),
                           'live token/slot/incarnation/configuration do not agree')
        else:
            settings.check(slots[index]==life.NONE and snapshot['state'] in (0,3,4,5),
                           'unowned configuration retains a slot or live state')
    for slot,configuration in enumerate(configurations):
        settings.check(configuration==life.NONE or (configuration<18 and slots[configuration]==slot
                       and snapshots[configuration]['process']!=0),'slot map is not the exact inverse of configurations')
    events=[]
    for index in range(64):
        version,seq,configuration,generation,process,state,status,flags=struct.unpack_from('<8Q',raw,offset+index*64)
        settings.check(version==1 and flags==0,'event version/flags differs')
        if seq:
            settings.check(max(1,sequence-63)<=seq<=sequence and (seq-1)%64==index
                           and configuration<18 and generation>0 and 0<(process>>8)<=0x0fffffff
                           and 1<=(process&255)<=16 and state in (2,3,4,5),
                           'event ring sequence/slot/configuration/state differs')
            events.append(dict(sequence=seq,configuration=configuration,generation=generation,
                               process=process,state=state,status=status))
    events.sort(key=lambda event:event['sequence'])
    settings.check([e['sequence'] for e in events]==list(range(max(1,sequence-63),sequence+1)),
                   'event ring has gaps or duplicate logical sequences')
    return dict(sequence=sequence,configs=configs,snapshots=snapshots,slots=slots,
                incarnations=incarnations,configurations=configurations,events=events,
                raw_sha256=hashlib.sha256(raw).hexdigest())

def validate(s, control=False):
    check(s['identity']==0x10421af4 and s['lease']['pages']==32,'wrong controller/whole lease')
    check(s['lease']['physical']>0 and s['lease']['physical']%131072==0
          and s['lease']['state']==2 and s['lease']['mapped']==32
          and s['lease']['attempted']==32 and s['lease']['root']==s['root'] and s['root']>0
          and s['lease']['generation']==s['memory_generation'] and s['memory_generation']>0
          and s['pinned']==1 and s['memory_ready']==1,'DMA no longer completely held')
    check(s['domain_ready']==1 and s['domain_failed']==0 and s['bridge_failed']==0
          and s['online']==15 and len(s['cpus'])==4,'runtime7 four-CPU domain is not healthy')
    if control:
        check(s['reset_state']==0 and s['reset_owner']==0 and s['reset_token']==0
              and s['snapshot']['state']==2 and s['snapshot']['process']!=0
              and s['status']==15 and s['quarantined']==0 and s['command']&0x406==0x406,
              'control did not remain normally initialized and DMA enabled')
        context.validate_context(s,control=True)
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
    context.validate_context(s,control=False)

class ResetGuest(life.ProcessGuest):
    """Reuse read-only decoders, but not normal-desktop-ready constructor."""
    def __init__(self,esp,disk,state,control=False):
        self.esp,self.disk,self.state=esp,disk,state;state.mkdir()
        self.control=control
        self.raw=bytearray();self.chunks=[];self.tables={};self.stopped=False
        self.process=self.qmp=self.uart=None
        self.evidence=dict(actual_qemu_executed=False,no_guest_memory_or_register_writes=True,cleanup_completed=False)
        self.kernel_memory_layout=nvme.check_kernel_memory_layout(esp)
        self.layout=json.loads((esp.parent/'dong_layout.json').read_text())
        for name in (context.CONTEXT_TYPE,context.DEVICE_TYPE,context.LEASE_TYPE,'lib.device_abi.Binding'):context.checked_layout(self.layout,name)
        self.types={t['full_name']:t for t in self.layout['types']}
        self.block_symbols=life.read_elf_symbols(esp.parent/'services/block/program.elf')
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
    def complete_record(self,typ,address,index=0):
        size=context.checked_layout(self.layout,typ)['size']
        return context.decode_record(self.virtual_kernel(address+index*size,size,typ),self.layout,typ)
    def catalog(self):
        pointer=self.kval('user.services','CATALOG')
        check(pointer>=0xffff800000000000 and pointer%8==0,'Catalog is not a trusted aligned kernel pointer')
        return decode_catalog(self.virtual_kernel(pointer,life.CATALOG_BYTES,'actual kernel-owned lifecycle catalog'))
    def snapshot(self):
        self.pause();dump_start=len(self.chunks);catalog=self.catalog()
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
        expected_fault_rip=None if self.control else plan['load_bias']+self.block_symbols['svc_user_ud2']
        self.roots=[0,0,p['root']]
        self.pool_limits=list(struct.unpack('<16Q',self.kernel(self.ksym('user.memory','POOL_LIMITS'),128,'table pool limits')))
        instruction=None if self.control else self.user(2,expected_fault_rip,2,'actual linked fault instruction').hex()
        for cpu in cpus:cpu['block_seen']=self.record('sched.user_domain.Seen',cpu['seen'],2)
        engine_fields={f['name']:f['offset'] for f in self.types['sched.multicore.Engine']['fields']}
        queue_thread=self.record('sched.multicore.Thread',domain['engine']+engine_fields['threads'],2)
        owner=self.kval('user.device_host','PCI_OWNERS')
        check(owner==((3<<32)|catalog['incarnations'][2]),'owner differs from real Catalog incarnation')
        dma_context=self.complete_record(context.CONTEXT_TYPE,self.ksym('user.device_host','DMA_CONTEXTS'),2)
        table=self.kval('user.device_host','TABLE')
        check(table>=acpi.HHDM and table%8==0,'device ledger is not a trusted aligned kernel pointer')
        table_type=self.types['user.device_manager.Table'];table_fields={f['name']:f for f in table_type['fields']}
        table_header=self.record('user.device_manager.Table',table)
        token=self.kval('user.device_host','PCI_TOKENS');index=(token&255)-1
        check(table_header['initialized']==1 and 0<=index<table_header['count']<=32,'actual ledger table/token is invalid')
        ledger_device=self.complete_record(context.DEVICE_TYPE,table+table_fields['devices']['offset'],index)
        binding=self.complete_record('lib.device_abi.Binding',table+table_fields['bindings']['offset'],0)
        region_base=self.kval('user.devices','REGION_BASE');offset=ecam-region_base
        check(region_base>0 and offset>=0,'selected device lies outside trusted ECAM base')
        hardware=dict(version=1,token=0,next_cursor=0,kind=1,ecam=ecam,segment=0,bus=offset>>20,
                      device=(offset>>15)&31,function=(offset>>12)&7,vendor=identity&65535,device_id=identity>>16,
                      class_code=struct.unpack_from('<I',config,8)[0]>>8,header=(struct.unpack_from('<I',config,12)[0]>>16)&255,
                      flags=0,generation=0,reserved=0)
        result=dict(context=dma_context,catalog=catalog,binding=binding,ledger_device=ledger_device,pci_identity=hardware,
            selected_ecam=ecam,region_base=region_base,
            memory_generation=struct.unpack('<Q',self.kernel(self.ksym('user.memory','GENERATIONS')+16,8,'block memory generation'))[0],fault_rip=frame['rip'],expected_fault_rip=expected_fault_rip,fault_instruction=instruction,
            pending=self.record('sched.user_bridge.Pending',bridge['pending'],2),identity=identity,command=command,status=status,lease=lease,root=p['root'],memory_ready=p['ready'],
            pinned=self.kernel(self.ksym('user.memory','PINNED')+2,1,'block PINNED')[0],
            quarantined=self.kernel(self.ksym('user.devices','BLOCK_QUARANTINED'),1,'quarantine')[0],
            owner=owner,device_token=token,
            reset_state=self.kval('user.devices','BLOCK_RESET_STATE'),
            reset_owner=self.kval('user.device_host','BLOCK_RESET_OWNER'),reset_token=self.kval('user.device_host','BLOCK_RESET_TOKEN'),
            snapshot=catalog['snapshots'][2],catalog_slot=catalog['slots'][2],configuration=catalog['configurations'][2],
            bridge_failed=bridge['failed'],domain_ready=domain['ready'],domain_failed=domain['failed'],completed=domain['completed'],online=domain['online'],
            queue_thread=queue_thread,domain_process=self.record('sched.user_domain.Process',domain['processes'],2),cpus=cpus)
        result['dump_range']=[dump_start,len(self.chunks)]
        return result
    def close(self):
        try:settings.Guest.close(self)
        finally:
            if self.process is not None and self.process.poll() is None:
                self.process.kill();self.process.wait(timeout=5)
            self.evidence['qemu_stopped']=self.process is None or self.process.poll() is not None
            self.evidence['qemu_returncode']=None if self.process is None else self.process.returncode
            self.evidence['process_alive']=self.process is not None and self.process.poll() is None
            storage.write_json(self.state/'guest.json',self.evidence)
        check(self.evidence['qemu_stopped'],'own QEMU process did not stop')
        check(self.evidence['qemu_returncode'] in (None,0),'own QEMU did not exit cleanly')
        self.evidence['cleanup_completed']=True
        storage.write_json(self.state/'guest.json',self.evidence)


def archive_inputs(esp,state,root,control=False):
    """Keep the exact ABI/ELFs with the physical evidence for standalone replay."""
    artifacts=state/'artifacts';artifacts.mkdir()
    inputs={}
    paths=[('dong_layout.json',esp.parent/'dong_layout.json'),('kernel.elf',esp.parent/'kernel.elf'),
           ('block.elf',esp.parent/'services/block/program.elf'),('build-inputs.json',esp.parent/'build-inputs.json')]
    if not control:paths.append(('p5-reset-fixture.json',root/'p5-reset-fixture.json'))
    for name,path in paths:
        before=fixture.digest(path);shutil.copyfile(path,artifacts/name)
        check(fixture.digest(artifacts/name)==fixture.digest(path)==before,'artifact changed while archiving: '+name)
        inputs[name]=dict(source=str(path),sha256=before)
    storage.write_json(state/'archived-inputs.json',dict(artifacts=inputs,source_sha256=fixture.hashes(root)))
    return inputs


def _archived(base,relative):
    path=(base/relative).resolve()
    check(path.is_relative_to(base.resolve()) and not (base/relative).is_symlink(),'unsafe archived evidence path')
    return path


class ReplayGuest(ResetGuest):
    """The same decoder, supplied by exact ordered read-only physical dumps."""
    def __init__(self,state,metadata,manifest,start,control):
        self.state=state;self.control=control;self.stopped=True;self.tables={};self.evidence={}
        self.raw=bytearray((state/'guest/serial.log').read_bytes())
        self.layout=json.loads((state/'artifacts/dong_layout.json').read_text())
        self.types={t['full_name']:t for t in self.layout['types']}
        for name in (context.CONTEXT_TYPE,context.DEVICE_TYPE,context.LEASE_TYPE,'lib.device_abi.Binding'):context.checked_layout(self.layout,name)
        self.symbols=acpi.validation_symbols(state/'artifacts/kernel.elf')
        check(self.symbols==json.loads((state/'symbols.json').read_text()),'archived ELF symbols differ')
        self.block_symbols=life.read_elf_symbols(state/'artifacts/block.elf')
        self.kernel_memory_layout=metadata['kernel_memory_layout']
        workspace=self.types['boot.memory_startup.Workspace'];view=self.types['boot.runtime_view.View']
        check(self.kernel_memory_layout==dict(layout_file_sha256=fixture.digest(state/'artifacts/dong_layout.json'),
              workspace_size=workspace['size'],runtime_offset=next(f['offset'] for f in workspace['fields'] if f['name']=='runtime'),
              view_size=view['size'],view_fields={f['name']:f['offset'] for f in view['fields']}),
              'archived runtime View layout metadata differs')
        markers=re.findall(rb'^memory_runtime_boot_info=0x([0-9a-f]{16})\r?$',bytes(self.raw),re.M)
        boot_chunks=[(i,item) for i,item in enumerate(manifest) if item['role']=='BootInfo']
        check(len(markers)==len(boot_chunks)==1,'missing unique archived BootInfo/UART')
        index,item=boot_chunks[0]
        check(item['physical']==int(markers[0],16)-acpi.HHDM and item['length']==160,'archived BootInfo physical address mismatch')
        self.manifest=manifest;self.chunks=list(manifest[:index]);self.cursor=index
        self.boot=struct.unpack('<20Q',self.physical(item['physical'],160,'BootInfo'))
        self.chunks=list(manifest[:start]);self.cursor=start
    def pause(self):self.stopped=True;self.tables={}
    def physical(self,pa,n,role):
        check(self.cursor<len(self.manifest),'offline read exceeds physical manifest')
        item=self.manifest[self.cursor]
        check((item['physical'],item['length'],item['role'])==(pa,n,role),'offline physical read order/address/role mismatch')
        check(re.fullmatch(r'physical-[0-9]{5,}\.bin',item['file']) is not None,'unexpected physical dump filename')
        raw=_archived(self.state/'guest',item['file']).read_bytes()
        check(len(raw)==n and hashlib.sha256(raw).hexdigest()==item['sha256'],'archived physical dump short/hash mismatch')
        self.chunks.append(item);self.cursor+=1
        return raw


def replay_evidence(result_path):
    """Validate archived bytes again; does not access the original source/ESP."""
    result_path=Path(result_path).resolve();state=result_path.parent
    result=json.loads(result_path.read_text());metadata=json.loads((state/'replay-metadata.json').read_text())
    archived=json.loads((state/'archived-inputs.json').read_text())
    check(result.get('passed') is True and result.get('control') is metadata.get('control'),'result phase/pass metadata differs')
    check(type(result['control']) is bool,'phase must be an exact boolean')
    expected_artifacts={'dong_layout.json','kernel.elf','block.elf','build-inputs.json'}
    if not result['control']:expected_artifacts.add('p5-reset-fixture.json')
    for name,item in archived['artifacts'].items():
        check(name in expected_artifacts
              and fixture.digest(_archived(state,'artifacts/'+name))==item['sha256'],'archived artifact hash mismatch')
    check(set(archived['artifacts'])==expected_artifacts,'missing archived build inputs')
    sources=archived['source_sha256']
    check(isinstance(sources,dict) and sources and result.get('source_before')==result.get('source_after')==sources,
          'source before/after/archive identity differs')
    check(all(isinstance(name,str) and isinstance(sha,str) and re.fullmatch('[0-9a-f]{64}',sha) is not None
              for name,sha in sources.items()),'source identity contains a non-SHA256 value')
    for result_key,name in [('kernel_elf_sha256','kernel.elf'),('block_elf_sha256','block.elf'),
                            ('build_manifest_sha256','build-inputs.json'),('layout_manifest_sha256','dong_layout.json')]:
        check(result.get(result_key)==archived['artifacts'][name]['sha256'],'result/archive artifact identity differs: '+name)
    build=json.loads((state/'artifacts/build-inputs.json').read_text())
    check(build.get('runtime_level')==7 and type(build.get('runtime_level')) is int and build.get('test') is False
          and build.get('graphics_case') is None and build.get('source_unchanged') is True
          and isinstance(build.get('source_sha256'),dict) and build['source_sha256'],
          'archived build is not a stable normal runtime7 build')
    check(all(sources.get(name)==sha for name,sha in build['source_sha256'].items()),'build sources differ from run source identities')
    kernel_hashes=[sha for name,sha in build.get('artifacts',{}).items() if name.replace('\\','/').rsplit('/',1)[-1]=='kernel.elf']
    check(kernel_hashes==[archived['artifacts']['kernel.elf']['sha256']],'build artifact differs from archived kernel ELF')
    if not result['control']:
        injection=json.loads((state/'artifacts/p5-reset-fixture.json').read_text())
        without_manifest=dict(sources);manifest_sha=without_manifest.pop('p5-reset-fixture.json',None)
        check(manifest_sha==result.get('fixture_manifest_sha256')==archived['artifacts']['p5-reset-fixture.json']['sha256']
              and injection.get('changed')==[fixture.TARGET] and injection.get('fixture_sha256')==without_manifest,
              'archived exact UD2 fixture source identity differs')
        pristine=injection.get('production_sha256',{})
        check(pristine and set(pristine)==set(without_manifest)
              and [name for name in pristine if pristine[name]!=without_manifest[name]]==[fixture.TARGET],
              'fault fixture changes more than the exact block entry source')
    else:check(result.get('fixture_manifest_sha256') is None,'normal control claims a fault fixture')
    check(fixture.digest(state/'guest/serial.log')==metadata['serial_sha256'],'archived serial changed')
    manifest=json.loads((state/'guest/physical-manifest.json').read_text())
    check(fixture.digest(state/'guest/physical-manifest.json')==metadata['physical_manifest_sha256'],'physical manifest changed')
    observations=result.get('snapshots');check(isinstance(observations,list) and len(observations)==2,'two archived observations required')
    decoded=[];previous=0
    for saved in observations:
        start,end=saved['dump_range']
        check(type(start) is int and type(end) is int and previous<=start<end<=len(manifest),'invalid/overlapping observation dump range')
        guest=ReplayGuest(state,metadata,manifest,start,result['control'])
        actual=guest.snapshot();check(guest.cursor==end and actual==saved,'raw offline observation differs from recorded decoded snapshot')
        validate(actual,result['control']);decoded.append(actual);previous=end
    context.validate_observations(*decoded,control=result['control'])
    return dict(passed=True,control=result['control'],observations=decoded,
                actual_qemu_executed=result.get('guest',{}).get('actual_qemu_executed') is True,
                scope='initialized-queue-context-reset-hold-only',outstanding_io_proven=False,
                dma_drain_proven=False,dma_reuse_proven=False,restart_proven=False,
                observation_semantics='two stable final-phase observations; no per-step timestamps')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp',type=Path)
    parser.add_argument('--replay',type=Path,help='offline revalidate an archived result.json; never starts QEMU')
    parser.add_argument('--control',action='store_true',help='normal unmodified initialized-device control')
    args=parser.parse_args()
    if args.replay:
        if args.reuse_esp:parser.error('--replay cannot be combined with --reuse-esp')
        replayed=replay_evidence(args.replay);print(json.dumps(replayed,indent=2));return 0
    if not args.reuse_esp:parser.error('--reuse-esp is required for an actual guest run')
    esp=args.reuse_esp.resolve();root=Path(__file__).resolve().parents[1]
    if not args.control:fixture.verify(root)
    elif (root/'p5-reset-fixture.json').exists() or 'svc_user_ud2' in (root/fixture.TARGET).read_text():raise ValueError('control must use unmodified source root')
    verify_build(esp)
    state=root/'build/test/p5-reset-guest'/('run-'+uuid.uuid4().hex)
    check(not any(p.is_symlink() for p in state.parents),'symlink state ancestor')
    state.mkdir(parents=True)
    archived_inputs=archive_inputs(esp,state,root,args.control)
    disk=state/'data.img';check(not disk.exists() and not disk.is_symlink(),'disk path already exists')
    create(disk,64);before=fixture.digest(disk);guest=None
    source_before=fixture.hashes(root)
    result=dict(passed=False,scope='initialized-queue-context-reset-hold-only',control=args.control,
                outstanding_io_proven=False,dma_drain_proven=False,dma_reuse_proven=False,restart_proven=False,
                observation_semantics='two stable final-phase observations; no per-step timestamps',
                build_manifest_sha256=fixture.digest(esp.parent/'build-inputs.json'),
                layout_manifest_sha256=fixture.digest(esp.parent/'dong_layout.json'),
                kernel_elf_sha256=fixture.digest(esp.parent/'kernel.elf'),
                block_elf_sha256=fixture.digest(esp.parent/'services/block/program.elf'),
                fixture_manifest_sha256=None if args.control else fixture.digest(root/'p5-reset-fixture.json'))
    try:
        guest=ResetGuest(esp,disk,state/'guest',control=args.control);deadline=time.monotonic()+90;polls=[]
        storage.write_json(state/'symbols.json',guest.symbols)
        while time.monotonic()<deadline:
            guest.pause()
            check(guest.process.poll() is None and b'DONGOS_P1_KERNEL_FAIL' not in guest.raw and b'PANIC' not in guest.raw,'guest exited/panicked while awaiting receipt')
            catalog_pointer=guest.kval('user.services','CATALOG');bridge_pointer=guest.kval('sched.user_bridge','ACTIVE')
            ready=False;phase={}
            if catalog_pointer and bridge_pointer:
                initialized=struct.unpack('<Q',guest.virtual_kernel(catalog_pointer,8,'Catalog initialization poll'))[0]
                if initialized==1:
                    catalog=guest.catalog()
                    phase['block_state']=catalog['snapshots'][2]['state']
                    if args.control:ready=phase['block_state']==2
                    else:
                        phase['reset_state']=guest.kval('user.devices','BLOCK_RESET_STATE')
                        phase['current']=guest.kval('user.services','CURRENT')
                        # reset_state publishes inside the old retirement
                        # callback. Wait for that callback to return before
                        # judging its final receipt, without polling ctx's
                        # expected values and hiding a malformed receipt.
                        ready=phase['block_state']==4 and phase['reset_state']==2 and phase['current']!=2
            polls.append(dict(catalog_pointer=catalog_pointer,bridge_pointer=bridge_pointer,ready=ready,phase=phase))
            if ready:
                # Once the trusted phase is reached, malformed evidence fails
                # immediately. Never hide a real bad receipt as a poll timeout.
                s=guest.snapshot();validate(s,args.control);break
            guest.resume();time.sleep(.1)
        else:raise TimeoutError('reset/context phase not reached: '+repr(polls[-3:]))
        guest.resume();time.sleep(.2);second=guest.snapshot();validate(second,args.control)
        check(second['lease']==s['lease'] and second['root']==s['root'],'held lease changed after observation')
        context.validate_observations(s,second,args.control)
        result.update(snapshots=[s,second],polls=polls,passed=True)
    except Exception as error:result['error']=f'{type(error).__name__}: {error}'
    finally:
        if guest is not None:
            try:guest.close();result['guest']=guest.evidence
            except Exception as error:result.update(passed=False,cleanup_error=str(error),guest=guest.evidence)
            if hasattr(guest,'symbols'):
                storage.write_json(state/'replay-metadata.json',dict(control=args.control,kernel_memory_layout=guest.kernel_memory_layout,
                    serial_sha256=fixture.digest(state/'guest/serial.log'),
                    physical_manifest_sha256=fixture.digest(state/'guest/physical-manifest.json')))
        try:
            check(fixture.digest(disk)==before,'read-only fixture disk changed')
            verify_build(esp)
            if not args.control:fixture.verify(root)
            for name,item in archived_inputs.items():check(fixture.digest(Path(item['source']))==item['sha256'],'artifact changed during run: '+name)
            source_after=fixture.hashes(root);check(source_before==source_after,'source changed during guest run')
            result.update(source_before=source_before,source_after=source_after,disk_before_sha256=before,disk_after_sha256=fixture.digest(disk))
        except Exception as error:result.update(passed=False,integrity_error=str(error))
        storage.write_json(state/'result.json',result)
    print(state/'result.json');return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
