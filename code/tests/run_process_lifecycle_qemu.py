#!/usr/bin/env python3
"""Actual admitted-process lifecycle/ASLR/PCID gate, using a completed ESP.

Root alone runs actual guests. This runner never builds, writes guest memory,
changes guest registers, or edits a running disk. APP.ELF is an explicitly
recorded host input in a fresh ordinary FAT fixture before either boot.
"""
from pathlib import Path
import argparse,hashlib,json,re,struct,sys,time,uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.build_usb import verify_build
from tools.make_fat32_disk import create,SEED
from tools.elf_symbols import read_elf_symbols
from tests import run_fat_paths_qemu as fat
from tests import fat_paths_oracle as disk_oracle

ROOT,settings,storage,nvme=fat.ROOT,fat.settings,fat.storage,fat.nvme
NAMES=('shell','fs','block','compositor','input','init','devmgr','echo','fault','waiter','ipc-peer','fs-reader','file-app','xhci','terminal','files','editor','settings')
DEPS=(2,4,64,18,64,0,32,2,2,2,2,2,2,64,10,10,10,10)
CONFIG_BYTES,SNAPSHOT_BYTES,EVENT_BYTES,CATALOG_BYTES,PROCESS_BYTES=128,64,64,10776,1288
NONE=(1<<64)-1
MAX_EXEC_IMAGE=2*1024*1024
NF=1<<63


def decode_catalog(raw):
    settings.check(len(raw)==CATALOG_BYTES,'catalog must have the completed exact ABI size')
    ready,count,sequence=struct.unpack_from('<3Q',raw)
    settings.check((ready,count)==(1,18),'kernel catalog is not initialized with 18 admitted configurations')
    configs=[]
    for index in range(32):
        offset=24+index*128;fields=struct.unpack_from('<8Q',raw,offset)
        version,identifier,deps,retries,timeout,flags,image,length=fields
        name=raw[offset+64:offset+96];reserved=raw[offset+96:offset+128]
        settings.check(version==1 and reserved==bytes(32),'config version/reserved field differs')
        if index<18:
            expected_flags=7 if index in (0,1,3,6) else (5 if index<7 else (4 if index==13 else 8))
            settings.check(identifier==index and deps==DEPS[index] and image==index+1
                           and flags==expected_flags and retries==(3 if index in (0,1,3,6) else 0)
                           and timeout>0 and 0<length<=32 and name[:length]==NAMES[index].encode()
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
            settings.check(slots[index]==NONE and snapshot['state'] in (0,3,4,5),
                           'unowned configuration retains a slot or live state')
    for slot,configuration in enumerate(configurations):
        settings.check(configuration==NONE or (configuration<18 and slots[configuration]==slot
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


def check_boot_dag(catalog):
    settings.check(catalog['sequence']<=64,'boot DAG history has already been overwritten')
    ready=set()
    for event in catalog['events']:
        identifier=event['configuration']
        if event['state']==2:
            settings.check(all(dependency in ready for dependency in range(18) if DEPS[identifier]&(1<<dependency)),
                           'READY was published before a real prerequisite READY')
            ready.add(identifier)
        else:ready.discard(identifier)
    settings.check(all(i in ready and catalog['snapshots'][i]['state']==2 for i in range(7)),
                   'all seven essential service processes must be READY')
    return dict(ready_order=[e['configuration'] for e in catalog['events'] if e['state']==2],
                actual_dependency_ready_order_verified=True)


def parse_record(body,label,name=None):
    prefix=re.escape(label+((' '+name) if name else ''))
    matches=re.findall(rb'^'+prefix.encode()+rb' token=([0-9]+) generation=([0-9]+) state=([0-9]+) status=([0-9]+)\r?$',body,re.M)
    settings.check(len(matches)==1,'one fresh literal '+label+' process record is required')
    token,generation,state,status=map(int,matches[0]);settings.check(0<token<=NONE and generation<=NONE and state<=5 and status<=NONE,'process response field exceeds its contract')
    return dict(token=token,generation=generation,state=state,status=status)


def parse_ps(body):
    matches=re.findall(rb'^PROCESS ([a-z-]+) id=([0-9]+) token=([0-9]+) generation=([0-9]+) state=([0-9]+) status=([0-9]+)\r?$',body,re.M)
    settings.check(len(matches)==18,'ps did not return the complete 18 configuration records')
    records=[]
    for index,(name,identifier,token,generation,state,status) in enumerate(matches):
        settings.check(name.decode()==NAMES[index] and int(identifier)==index,'ps ordering/configuration names differ')
        settings.check(int(token)<=NONE and int(generation)<=NONE and int(state)<=5 and int(status)<=NONE,
                       'ps field exceeds the process ABI')
        records.append(dict(name=name.decode(),id=index,token=int(token),generation=int(generation),state=int(state),status=int(status)))
    return records


def rejected_elfs():
    def image(kind,addresses):
        count=len(addresses);raw=bytearray((count+1)*4096)
        raw[:16]=b'\x7fELF\x02\x01\x01'+bytes(9)
        struct.pack_into('<HHIQQQIHHHHHH',raw,16,kind,62,1,addresses[0],64,0,0,64,56,count,0,0,0)
        for index,address in enumerate(addresses):
            offset=(index+1)*4096;data=b'\x0f\x0b' if index==0 else b'X'
            struct.pack_into('<IIQQQQQQ',raw,64+index*56,1,5 if index==0 else 6,
                             offset,address,0,len(data),4096,4096)
            raw[offset:offset+len(data)]=data
        return bytes(raw)
    return {'/SPARSE.ELF':image(3,[0x10000+i*0x40000000 for i in range(16)]),
            '/CLASH.ELF':image(2,[0x70000000])}


def input_files(payload):return {'/README.TXT':SEED,'/APP.ELF':payload,**rejected_elfs()}


def seed_executable(path,payload):
    """Populate recorded ordinary ELF fixtures before any VM has started."""
    settings.check(payload[:4]==b'\x7fELF' and 0<len(payload)<=MAX_EXEC_IMAGE,'seed must be a completed admitted ELF within the bounded EXEC limit')
    geometry=create(path,64);cursor=4
    with path.open('r+b') as stream:
        stream.seek(geometry['data_start']*512);root=bytearray(stream.read(512))
        settings.check(root[32]==0,'seed fixture root slot is occupied')
        for slot,(name,data) in enumerate(list(input_files(payload).items())[1:],1):
            stem,suffix=name[1:].split('.');at=slot*32;clusters=(len(data)+511)//512
            root[at:at+11]=stem.encode().ljust(8,b' ')+suffix.encode().ljust(3,b' ');root[at+11]=0x20
            struct.pack_into('<H',root,at+26,cursor);struct.pack_into('<I',root,at+28,len(data))
            for copy in range(2):
                base=(geometry['reserved']+copy*geometry['fat_sectors'])*512
                for index in range(clusters):
                    stream.seek(base+(cursor+index)*4);stream.write(struct.pack('<I',0x0fffffff if index==clusters-1 else cursor+index+1))
            stream.seek((geometry['data_start']+cursor-2)*512);stream.write(data)
            stream.write(bytes(clusters*512-len(data)));cursor+=clusters
        stream.seek(geometry['data_start']*512);stream.write(root)
        stream.flush()
    raw=disk_oracle.inspect(path,files=input_files(payload),exact_namespace=True)
    return dict(geometry=geometry,payload_sha256=hashlib.sha256(payload).hexdigest(),raw=raw,
                host_seeded_input_file='/APP.ELF',host_seed_before_guest_start=True)


def parse_registers(text):
    pairs=re.findall(r'\b(CR[034])=([0-9a-fA-F]+)\b',text)
    values={name:int(value,16) for name,value in pairs}
    settings.check(len(pairs)==3 and set(values)=={'CR0','CR3','CR4'},'read-only BSP register dump omitted/duplicated CR0/CR3/CR4')
    return values


class ProcessGuest(fat.FatGuest):
    def capture_failure(self):
        self.pause();report={}
        self.qmp.request('human-monitor-command',{'command-line':'cpu 0'})
        report['registers']=self.qmp.request('human-monitor-command',{'command-line':'info registers'})
        for label,module,name,n in (('processes','user.memory','PROCESSES',16*1288),
                ('current','user.services','CURRENT',8),('faults','user.services','USER_FAULTS',8),
                ('irqs','user.services','USER_IRQS',8)):
            raw=self.kernel(self.ksym(module,name),n,'failure '+label)
            report[label]=list(struct.unpack('<'+'Q'*(n//8),raw))
        for name,n in (('user_active_frame',200),('user_context_cpu',64),('user_context_last_error',8)):
            raw=self.kernel(self.symbols[name],n,'failure '+name)
            report[name]=list(struct.unpack('<'+'Q'*(n//8),raw))
        raw=self.kernel(self.symbols['cpu_exception_stack_top']-184,184,'failure hardware exception context')
        report['exception']=list(struct.unpack('<23Q',raw))
        storage.write_json(self.state/'failure.json',report)
        return report
    def settle(self):
        # Lifecycle checks do not depend on compositor internal window layout.
        self.resume();time.sleep(.08);self.pause()

    def refresh_processes(self):
        self.processes=self.kernel(self.ksym('user.memory','PROCESSES'),16*PROCESS_BYTES,'all sixteen process ABI records')
        self.roots=[struct.unpack_from('<Q',self.processes,i*PROCESS_BYTES+8)[0] for i in range(16)]
        return self.processes

    def verify_elf(self):
        self.refresh_processes();records=[]
        for pid,name in enumerate(NAMES[:7]):
            settings.check(struct.unpack_from('<Q',self.processes,pid*PROCESS_BYTES)[0]==1,'essential image was not loaded')
            records.append(self.verify_process(pid,name))
        self.evidence.update(actual_processes=7,essential_elfs=records,all_elf_code_bytes_verified=True,user_stack_guards_verified=14)

    def verify_process(self,pid,name):
        self.refresh_processes();root=self.roots[pid];offset=pid*PROCESS_BYTES
        settings.check(root>0 and root%4096==0,'live process root is invalid')
        if pid<4 and self.pool_limits[pid]==32:
            base=self.boot[15]+self.ksym('user.memory','TABLES')-storage.KERNEL
            settings.check(root==base+pid*32*4096,'fixed static pool moved')
        else:
            physicals=struct.unpack('<16Q',self.kernel(self.ksym('user.memory','DYNAMIC_PHYSICAL'),128,'trusted dynamic table pool records'))
            settings.check(root==physicals[pid] and root!=0,'dynamic root differs from its held arena pool')
        bias=struct.unpack_from('<Q',self.processes,offset+224)[0]
        settings.check(0x10000000<=bias<=0x1fff0000 and bias%65536==0,'load bias is outside the admitted 12-bit randomized window')
        data=(self.esp.parent/'services'/name/'program.elf').read_bytes()
        headers,stride,count=struct.unpack_from('<Q',data,32)[0],*struct.unpack_from('<HH',data,54)
        executable=0
        for index in range(count):
            kind,flags,file_offset,address,_,size,memory,_=struct.unpack_from('<IIQQQQQQ',data,headers+index*stride)
            if kind!=1:continue
            for page in range(address&~4095,(address+memory+4095)&~4095,4096):
                entry=self.pte(root,bias+page)
                settings.check(entry&0x800000000000001f==(5|(2 if flags&2 else 0)|(0 if flags&1 else NF)),
                               'actual code/data USER/RW/NX permissions differ')
                first,last=max(page,address),min(page+4096,address+size)
                if flags&1 and first<last:
                    actual=self.physical((entry&storage.MASK)+first-page,last-first,'actual executable '+name)
                    settings.check(actual==data[file_offset+first-address:file_offset+last-address],'executed ELF code differs from completed artifact');executable+=last-first
        rsp=struct.unpack_from('<Q',self.processes,offset+16+17*8)[0]
        top=(rsp&~4095)+4096
        for _ in range(4):
            if not self.pte(root,top)&1:break
            top+=4096
        settings.check(0x7fbff01000<=top<=0x7ffff00000 and not self.pte(root,top)&1
                       and not self.pte(root,top-5*4096)&1,'randomized stack does not have exact double guards')
        for page in range(top-4*4096,top,4096):
            settings.check(self.pte(root,page)&0x800000000000001f==NF|7,'randomized stack page lost private RW/NX')
        return dict(pid=pid,image=name,root=root,bias=bias,stack_top=top,executable_bytes=executable,
                    code_sha256=hashlib.sha256(data).hexdigest(),private_pool_kind='static' if pid<4 and self.pool_limits[pid]==32 else 'arena',private_pool_pages=self.pool_limits[pid])

    def canary(self,image,expected):
        module='apps.'+image['image'].replace('-','_')
        symbols=read_elf_symbols(self.esp.parent/'services'/image['image']/'program.elf')
        virtual=image['bias']+symbols[storage.symbol(module,'CANARY')]
        raw=self.user(image['pid'],virtual,8,'actual fresh owned BSS '+module+'.CANARY')
        observed=struct.unpack('<Q',raw)[0]
        settings.check(observed==expected,'actual initialized BSS canary differs from this incarnation argument')
        return dict(virtual=virtual,physical=self.pte(image['root'],virtual)&storage.MASK,
                    expected=expected,observed=observed,module=module,
                    zero_before_write_checked_by_actual_program=True)

    def fixed_probe(self,image,expected):
        settings.check(image['image']=='waiter' and image['pid']>=7,'fixed reuse probe requires an ordinary waiter image')
        catalog=self.catalog();incarnation=catalog['incarnations'][image['pid']]
        source=0x53200000+(image['pid']-7)*8192+((incarnation-1)&1)*4096
        target=0x44000000;target_entry=self.pte(image['root'],target);source_entry=self.pte(self.roots[1],source)
        settings.check(target_entry&0x800000000000001f in (NF|5,NF|7) and not target_entry&256
                       and source_entry&0x800000000000001f==NF|7
                       and (target_entry&storage.MASK)==(source_entry&storage.MASK),
                       'fixed USER probe is not the selected FS-held owned WB/NX page')
        symbols=read_elf_symbols(self.esp.parent/'services/waiter/program.elf')
        actual=struct.unpack('<Q',self.user(image['pid'],image['bias']+symbols[storage.symbol('apps.waiter','PROBE_VALUE')],8,'actual CPU-loaded fixed-VA PROBE_VALUE'))[0]
        physical=target_entry&storage.MASK;raw=struct.unpack('<Q',self.physical(physical,8,'FS-held probe source word'))[0]
        settings.check(actual==raw==expected,'actual fixed-VA load did not observe this incarnation page argument')
        return dict(virtual=target,physical=physical,source_virtual=source,incarnation=incarnation,
                    expected=expected,raw_source_word=raw,cpu_loaded_value=actual,
                    actual_cpu_load_before_ready_verified=True)

    def virtual_kernel(self,address,length,role):
        base,pages=self.trusted_kernel_pool();out=bytearray()
        while length:
            table=self.evidence['trusted_kernel_page_table_pool']['root_physical']
            for shift in (39,30,21,12):
                settings.check(base<=table<base+pages*4096 and table%4096==0,'kernel virtual read escaped trusted table pool')
                entry=struct.unpack_from('<Q',self.physical(table,4096,role+' table'),((address>>shift)&511)*8)[0]
                settings.check(entry&1,'missing trusted kernel mapping')
                if shift==12 or (shift in (30,21) and entry&128):
                    physical=(entry&storage.MASK&~((1<<shift)-1))+(address&((1<<shift)-1));break
                table=entry&storage.MASK
            count=min(length,4096-(address&4095));out.extend(self.physical(physical,count,role));address+=count;length-=count
        return bytes(out)

    def catalog(self):
        pointer=self.kval('user.services','CATALOG')
        settings.check(pointer>=0xffff800000000000 and pointer%8==0,'CATALOG is not a trusted aligned kernel pointer')
        return decode_catalog(self.virtual_kernel(pointer,CATALOG_BYTES,'actual kernel-owned lifecycle catalog'))

    def wait_state(self,configuration,state,timeout=15):
        deadline=time.monotonic()+timeout
        while True:
            self.pause();catalog=self.catalog()
            if catalog['snapshots'][configuration]['state']==state:return catalog
            settings.check(time.monotonic()<deadline,'configuration failed to reach real state')
            self.resume();time.sleep(.02)

    def pcid_snapshot(self):
        self.pause()
        def asm_global(name,n):return self.kernel(self.symbols[name],n,'actual '+name)
        enabled=struct.unpack('<Q',asm_global('user_pcid_enabled',8))[0]
        switches=struct.unpack('<Q',asm_global('user_pcid_switches',8))[0]
        retained=struct.unpack('<Q',asm_global('user_pcid_retained',8))[0]
        raw=asm_global('user_pcid_bindings',16*24);bindings=[dict(zip(('root','generation','loaded'),struct.unpack_from('<3Q',raw,i*24))) for i in range(16)]
        self.qmp.request('human-monitor-command',{'command-line':'cpu 0'})
        dump=self.qmp.request('human-monitor-command',{'command-line':'info registers'})
        registers=parse_registers(dump)
        settings.check(enabled in (0,1) and bool(registers['CR4']&(1<<17))==bool(enabled),'PCIDE register/software gate disagree')
        settings.check(not registers['CR4']&(1<<7),'PGE must remain disabled')
        if not enabled:
            settings.check(registers['CR3']%4096==0 and retained==0 and all(b['loaded']==0 for b in bindings),'PCID fallback retained a tagged/noflush context')
        else:
            tag=registers['CR3']&4095
            settings.check(tag<=16 and (tag==0 or bindings[tag-1]['root']==registers['CR3']&~4095),'actual CR3 tag/root binding differs')
        return dict(enabled=bool(enabled),registers=registers,switches=switches,retained=retained,bindings=bindings)

    def keyboard_shell(self):
        self.pause();before=self.kval('user.services','USER_IRQS')
        initial=struct.unpack('<3Q',self.user(4,0x54100000,24,'console ring before physical keyboard input'))
        start=len(self.raw);self.resume()
        def key(name):
            self.qmp.request('send-key',{'keys':[{'type':'qcode','data':name}],'hold-time':10})
            time.sleep(.06)
        def fresh_marker(marker):
            deadline=time.monotonic()+15
            while marker not in bytes(self.raw[start:]):
                settings.check(self.process.poll() is None and b'PANIC' not in self.raw,'physical keyboard guest failed')
                settings.check(time.monotonic()<deadline,'missing fresh keyboard mode marker')
                time.sleep(.01)
        key('f12');fresh_marker(b'DONGOS_INPUT_CONSOLE_ON\r\n')
        command_start=len(self.raw)
        for code in ('p','w','d','ret'):key(code)
        deadline=time.monotonic()+15;response=None
        while response is None:
            response=fat.fresh_response(bytes(self.raw[command_start:]),'pwd',exact=b'/\r\n')
            settings.check(time.monotonic()<deadline,'i8042 characters did not reach the real shell')
            if response is None:time.sleep(.01)
        key('f12');fresh_marker(b'DONGOS_INPUT_CONSOLE_OFF\r\n');self.pause()
        after=self.kval('user.services','USER_IRQS')
        final=struct.unpack('<3Q',self.user(4,0x54100000,24,'console ring after physical keyboard input'))
        settings.check(after>before and final[0]==final[1] and final[0]-initial[0]==4
                       and final[2]==initial[2]==0,'actual keyboard IRQ/SPSC consumption differs')
        table=self.kval('user.device_host','TABLE')
        raw=self.virtual_kernel(table,4560,'actual device and IRQ authority ledger')
        ready,count=struct.unpack_from('<2Q',raw);settings.check(ready==1 and 0<count<=32,'actual device inventory invalid')
        irq=struct.unpack_from('<12Q',raw,16+4096+256)
        settings.check(irq[0]==1 and irq[2]==1 and irq[4]==0x51 and irq[6]>0
                       and irq[7]==0 and irq[8]==(5<<32)|1 and irq[10]==1,
                       'keyboard IRQ was not acknowledged by its bound input incarnation')
        return dict(actual_qmp_keyboard_only=True,no_uart_command_injected=True,command='pwd',
                    response=response,irq_before=before,irq_after=after,ring_before=initial,
                    ring_after=final,keyboard_irq=irq)


def run_commands(guest,require_pcid=False):
    commands=[];records=[]
    def call(command,**kwargs):
        response=guest.shell(command,**kwargs);commands.append(response);return bytes.fromhex(response['response_hex'])
    initial=guest.catalog();dag=check_boot_dag(initial);pcid_before=guest.pcid_snapshot()
    keyboard=guest.keyboard_shell()
    table=parse_ps(call('ps'))
    settings.check(all(table[i]['state']==2 for i in range(7)),'ps essential services do not agree with READY catalog')
    for index,record in enumerate(table):
        snapshot=initial['snapshots'][index]
        settings.check((record['token'],record['generation'],record['state'],record['status'])
                       ==(snapshot['process'],snapshot['generation'],snapshot['state'],snapshot['status']),
                       'ps record differs from trusted kernel catalog')
    rejected=[]
    for path in ('/SPARSE.ELF','/CLASH.ELF'):
        held=[]
        for attempt in range(10):
            before=guest.catalog();response=call('exec '+path,expect_error=True);after=guest.catalog()
            expected_error=0x02000007 if path=='/SPARSE.ELF' else 0x02030001
            settings.check(response==('ERROR 0x%016x\r\n'%expected_error).encode(),
                           'fixture was not rejected at the intended late resource boundary')
            settings.check(before['raw_sha256']==after['raw_sha256'],'rejected staged ELF published process state')
            held.append(guest.kval('user.memory','FRAME_COUNT'))
        settings.check(len(set(held[1:]))==1,'failed staged ELF repeatedly leaked owned frames')
        rejected.append(dict(path=path,attempts=10,frame_counts=held,last_response_hex=response.hex(),
                             catalog_unchanged=True,valid_elf_rejected_at_resource_boundary=True))
    for argument in (17,1001,0,997):
        launched=parse_record(call('run echo '+str(argument)),'RUN OK','echo')
        ended=parse_record(call('wait '+str(launched['token'])),'WAIT OK')
        settings.check(ended['token']==launched['token'] and ended['generation']==launched['generation']
                       and (ended['state'],ended['status'])==(3,argument),'actual admitted echo exit/argument differs')
        records.append(dict(kind='echo-exit',spawn=launched,exit=ended))
    waiter=parse_record(call('run waiter 781624'),'RUN OK','waiter');current=guest.wait_state(9,2)
    slot=current['slots'][9];first=guest.verify_process(slot,'waiter');first['canary']=guest.canary(first,781624);first['probe']=guest.fixed_probe(first,781624)
    call('kill '+str(waiter['token']))
    waiter2=parse_record(call('run waiter 991833'),'RUN OK','waiter');current=guest.wait_state(9,2)
    settings.check(current['slots'][9]==slot and waiter2['token']!=waiter['token'] and waiter2['generation']>waiter['generation'],
                   'slot reincarnation revived a stale process token')
    second=guest.verify_process(slot,'waiter');second['canary']=guest.canary(second,991833);second['probe']=guest.fixed_probe(second,991833)
    settings.check(first['root']==second['root'] and first['probe']['physical']!=second['probe']['physical']
                   and struct.unpack('<Q',guest.physical(first['probe']['physical'],8,'held old fixed-VA page retains old argument'))[0]==781624,
                   'warm fixed-VA root reuse did not replace the PA while retaining the old page/value')
    before=guest.catalog();call('kill '+str(waiter['token']),expect_error=True);after=guest.catalog()
    settings.check(before['raw_sha256']==after['raw_sha256'] and after['snapshots'][9]['process']==waiter2['token'],
                   'old token killed or mutated its new slot incarnation')
    peer=parse_record(call('run ipc-peer 0'),'RUN OK','ipc-peer');current=guest.wait_state(10,2)
    peer_slot=current['slots'][10];settings.check(peer_slot>=8,'second ordinary process did not use the dynamic pool')
    peer_image=guest.verify_process(peer_slot,'ipc-peer');peer_image['canary']=guest.canary(peer_image,0)
    peer_log_start=len(guest.raw)
    caller=parse_record(call('run echo 999'),'RUN OK','echo')
    caller_exit=parse_record(call('wait '+str(caller['token'])),'WAIT OK')
    settings.check((caller_exit['state'],caller_exit['status'])==(3,0)
                   and b'DONGOS_APP_PEER_GONE\r\n' in bytes(guest.raw[peer_log_start:]),
                   'blocked real IPC caller did not observe peer-fault cancellation')
    peer_exit=parse_record(call('wait '+str(peer['token'])),'WAIT OK')
    settings.check((peer_exit['state'],peer_exit['status'])==(4,6),'IPC peer did not die from the actual requested UD2')
    settings.check(guest.canary(second,991833)['observed']==991833,'other process fault corrupted existing waiter BSS')
    call('kill '+str(waiter2['token']))
    fault=parse_record(call('run fault'),'RUN OK','fault');ended=parse_record(call('wait '+str(fault['token'])),'WAIT OK')
    settings.check(ended['state']==4 and ended['status'] in (6,13,14),'actual CPL3 fault was not isolated and recorded')
    call('pwd',exact=b'/\r\n')
    for name in ('fs-reader',):
        rights_log_start=len(guest.raw)
        launched=parse_record(call('run '+name),'RUN OK',name);ended=parse_record(call('wait '+str(launched['token'])),'WAIT OK')
        settings.check((ended['state'],ended['status'])==(3,0)
                       and b'DONGOS_APP_FS_RIGHTS_PASS\r\n' in bytes(guest.raw[rights_log_start:]),
                       'ordinary negative-control program did not pass actual file authority checks')
    launched=parse_record(call('exec /APP.ELF 3791'),'EXEC OK','/APP.ELF')
    loaded=guest.wait_state(12,2);executed_image=guest.verify_process(loaded['slots'][12],'waiter');executed_image['canary']=guest.canary(executed_image,3791);executed_image['probe']=guest.fixed_probe(executed_image,3791)
    call('kill '+str(launched['token']))
    ended=parse_record(call('wait '+str(launched['token'])),'WAIT OK')
    settings.check((ended['state'],ended['status'])==(5,0),'actual disk-loaded ELF termination differs')
    before=guest.catalog();call('exec /README.TXT',expect_error=True);after=guest.catalog()
    settings.check(before['raw_sha256']==after['raw_sha256'],'invalid ELF changed process catalog')
    before=guest.catalog();call('kill '+str(table[2]['token']),expect_error=True);after=guest.catalog()
    settings.check(before['raw_sha256']==after['raw_sha256'] and after['snapshots'][2]['state']==2,'shell killed essential device service')
    survivor=parse_record(call('run waiter 51977'),'RUN OK','waiter');before=guest.wait_state(9,2)
    input_root=guest.roots[4]
    queue_pa=guest.pte(input_root,0x54000000)&storage.MASK
    descriptor_pa=guest.pte(input_root,0x70001000)&storage.MASK
    call('restart compositor',expected=b'RESTART OK compositor\r\n')
    recovered=guest.wait_state(3,2,timeout=90)
    settings.check(recovered['snapshots'][3]['generation']==before['snapshots'][3]['generation']+1
                   and recovered['snapshots'][9]['process']==survivor['token'],
                   'compositor recovery changed another process or did not publish a new generation')
    new_compositor=guest.verify_process(3,'compositor')
    settings.check(guest.pte(guest.roots[3],0x54000000)&storage.MASK==queue_pa
                   and guest.pte(guest.roots[3],0x70001000)&storage.MASK==descriptor_pa,
                   'compositor recovery did not retain the live input queue/RO descriptor')
    restart_start=len(guest.raw);guest.resume();guest.uart.sendall(b'restart fs\r')
    deadline=time.monotonic()+120
    markers=(b'RESTART REQUEST fs\r\n',b'DONGOS_FS_READY\r\n',b'DONGOS_SHELL_READY\r\n',b'DONGOS_P7_DESKTOP_READY\r\n')
    while not all(marker in bytes(guest.raw[restart_start:]) for marker in markers):
        settings.check(guest.process.poll() is None and b'PANIC' not in guest.raw,'service recovery guest failed')
        settings.check(time.monotonic()<deadline,'FS recovery did not re-create dependent services')
        time.sleep(.02)
    guest.pause();restarted=guest.catalog();guest.refresh_processes()
    for identifier in (0,1,3):
        settings.check(restarted['snapshots'][identifier]['state']==2
                       and restarted['snapshots'][identifier]['generation']==recovered['snapshots'][identifier]['generation']+1,
                       'filesystem recovery did not restore the dependent service at a new generation')
        guest.verify_process(identifier,NAMES[identifier])
    settings.check(restarted['snapshots'][9]['state']==5 and restarted['snapshots'][9]['status']==0x05110006
                   and restarted['snapshots'][9]['process']==0,'manual ordinary dependent survived filesystem retirement')
    for identifier in (2,4,5,6):
        settings.check(restarted['snapshots'][identifier]['process']==recovered['snapshots'][identifier]['process'],
                       'filesystem recovery restarted a DMA driver or unrelated manager')
    call('cat /README.TXT',exact=SEED+b'\r\n')
    call('kill '+str(survivor['token']),expect_error=True)
    rights_start=len(guest.raw);rights=parse_record(call('run fs-reader'),'RUN OK','fs-reader')
    rights_exit=parse_record(call('wait '+str(rights['token'])),'WAIT OK')
    settings.check((rights_exit['state'],rights_exit['status'])==(3,0)
                   and b'DONGOS_APP_FS_RIGHTS_PASS\r\n' in bytes(guest.raw[rights_start:]),
                   'new filesystem epoch lost file authorization after recovery')
    pcid_after=guest.pcid_snapshot()
    settings.check(pcid_after['switches']>pcid_before['switches'],'no actual context switch was observed')
    if require_pcid:
        settings.check(pcid_before['enabled'] and pcid_after['enabled']
                       and pcid_after['retained']>pcid_before['retained'],'this run requires actual PCIDE/no-flush execution')
    call('sync',expected=b'SYNC OK\r\n')
    return dict(commands=commands,dag=dag,keyboard=keyboard,rejected_stages=rejected,records=records,first_waiter=first,reloaded_waiter=second,
                dynamic_peer=peer_image,pcid_before=pcid_before,pcid_after=pcid_after,
                disk_loaded_image=executed_image,
                actual_peer_gone=dict(caller=caller,caller_exit=caller_exit,peer=peer,peer_exit=peer_exit,
                                      fresh_kernel_error_observed_by_caller_program=True),
                actual_disk_exec_verified=True,stale_slot_token_rejected=True,actual_fault_isolated=True,
                actual_fixed_va_different_pa_reuse=True,old_probe_page_held_with_old_argument=True,
                actual_service_recovery=dict(compositor=new_compositor,filesystem_catalog=restarted,
                                            persistent_input_queue=queue_pa,persistent_descriptor=descriptor_pa,
                                            manual_dependent_retired=True,dma_drivers_unchanged=True),
                pcid_hardware_executed=pcid_after['enabled'],strict_pcid_fallback=not pcid_after['enabled'])


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--reuse-esp',type=Path,required=True)
    parser.add_argument('--require-pcid',action='store_true',help='fail if the actual BSP lacks PCIDE/retained tagged contexts')
    args=parser.parse_args();esp=args.reuse_esp.resolve();state=ROOT/'build/test/process-lifecycle/qemu'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
    result=dict(passed=False,boots=[],actual_qemu_boots=0,full_os_build_executed=False,no_guest_memory_or_register_writes=True,
                host_seeded_input_file='APP.ELF',host_seed_before_guest_start=True,require_pcid=args.require_pcid)
    inputs={name:settings.sha(ROOT/name) for name in ('tests/run_process_lifecycle_qemu.py','tests/run_fat_paths_qemu.py',
        'tests/run_nvme_qemu.py','tests/run_desktop_settings_qemu.py','tests/run_services_qemu.py','tests/fat_paths_oracle.py','tools/make_fat32_disk.py')}
    guest=None;metadata={}
    try:
        metadata=verify_build(esp);result['build_inputs_sha256']=settings.sha(esp.parent/'build-inputs.json')
        layout=nvme.check_kernel_memory_layout(esp);payload=(esp.parent/'services/waiter/program.elf').read_bytes();disk=state/'data.img'
        result['seed']=seed_executable(disk,payload);first_hash=None
        for boot in range(2):
            guest=ProcessGuest(esp,disk,state/('boot-'+str(boot+1)),layout)
            record=run_commands(guest,args.require_pcid);record['block']=guest.block_snapshot();record['evidence']=guest.evidence
            guest.close();guest=None;result['boots'].append(record)
            raw=disk_oracle.inspect(disk,files=input_files(payload),exact_namespace=True)
            storage.write_json(state/('disk-after-boot-'+str(boot+1)+'.json'),raw)
            if boot==0:first_hash=raw['image_sha256']
            else:settings.check(raw['image_sha256']==first_hash,'same input disk changed across read-only exec/reboot')
        result.update(passed=True,actual_process_lifecycle=True,same_disk_reboot_verified=True,
                      physical_aslr_layouts=[b['first_waiter'] for b in result['boots']])
    except Exception as error:
        result['error']=f'{type(error).__name__}: {error}'
        if guest is not None:
            try:guest.capture_failure();result['failure_state_captured']=True
            except Exception as capture:result['failure_capture_error']=str(capture)
    finally:
        if guest is not None:
            try:guest.close()
            except Exception as error:result.update(passed=False,cleanup_error=str(error))
        records=[json.loads(path.read_text()) for path in state.glob('boot-*/guest.json')]
        result['actual_qemu_boots']=sum(r.get('actual_qemu_executed') is True for r in records)
        result['all_started_guests_stopped']=all(not r.get('actual_qemu_executed') or r.get('qemu_stopped') for r in records)
        if result['passed'] and (result['actual_qemu_boots']!=2 or not result['all_started_guests_stopped']):result.update(passed=False,error='two stopped actual guests are required')
        result['runner_inputs_unchanged']=all(settings.sha(ROOT/name)==digest for name,digest in inputs.items())
        if not result['runner_inputs_unchanged']:result.update(passed=False,error='runner inputs changed')
        if metadata:
            try:verify_build(esp);settings.check(settings.sha(esp.parent/'build-inputs.json')==result['build_inputs_sha256'],'build identity changed')
            except Exception as error:result.update(passed=False,build_unchanged_error=str(error))
        storage.write_json(state/'result.json',result)
    print('Process lifecycle actual', 'PASS' if result['passed'] else 'FAIL',state,result.get('error',''),flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
