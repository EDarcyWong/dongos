"""Host controls mutate actual ABI bytes; they never launch or impersonate a guest."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from tests import p5_recovery_context_guest as context

# Independent ABI oracle: do not derive the expected offsets from the decoder.
DEVICE = ('version token next_cursor kind ecam segment bus device function vendor '
          'device_id class_code header flags generation reserved').split()
LEASE = 'physical virtual pages root generation attempted mapped state'.split()
BINDING = 'version device_token role configuration_id generation irq_mask flags reserved'.split()
CONTEXT = [('present','u64',8),('slot','u64',8),('configuration','u64',8),
           ('owner','u64',8),('incarnation','u64',8),('device_token','u64',8),
           ('device_generation','u64',8),('identity','lib.device_abi.Device',128)]
CONTEXT += [(name,'u64',8) for name in
            'root memory_generation request_bytes request_alignment snapshot_status snapshot_error'.split()]
CONTEXT += [('lease','user.memory.DmaLease',64)]
CONTEXT += [(name,'u64',8) for name in
            ('acquire_done acquire_error context_error stop_state stop_error smp_retire '
             'route_state route_error isolation isolation_error reset reset_error '
             'generation_after revoke_error held drain').split()]


def manifest():
    def record(name,fields):
        offset=0;result=[]
        for field,typ,size in fields:
            result.append(dict(name=field,type=typ,offset=offset,size=size));offset+=size
        return dict(name=name.rsplit('.',1)[-1],full_name=name,kind='struct',size=offset,alignment=8,fields=result)
    return dict(schema=1,target='x86_64-dongos-elf',spec_version='0.1',module='user.services',types=[
        record('lib.device_abi.Device',[(n,'u64',8) for n in DEVICE]),
        # The compiler emits its canonical u64 type for source-level usize.
        record('user.memory.DmaLease',[(n,'u64',8) for n in LEASE]),
        record('user.device_host.DmaContext',CONTEXT),
        record('lib.device_abi.Binding',[(n,'u64',8) for n in BINDING])])


def original_context(control=False):
    identity=dict(zip(DEVICE,[1,257,0,1,0xe0100000,0,1,0,0,0x1af4,0x1042,0x10000,0,3,1,0]))
    lease=dict(zip(LEASE,[0x200000,0x68000000,32,0x1000,7,32,32,2]))
    values=dict(present=1,slot=2,configuration=2,owner=(3<<32)|1,incarnation=1,
                device_token=257,device_generation=1,identity=identity,root=0x1000,
                memory_generation=7,request_bytes=69632,request_alignment=4096,
                snapshot_status=2,snapshot_error=0,lease=lease,acquire_done=1,
                acquire_error=0,context_error=0,stop_state=0 if control else 1,
                stop_error=0,smp_retire=0 if control else 1,route_state=0 if control else 1,
                route_error=0,isolation=0 if control else 1,isolation_error=0,
                reset=0 if control else 2,reset_error=0,generation_after=0 if control else 2,
                revoke_error=0,held=1,drain=0)
    return values


def encode(value):
    words=[]
    for name,typ,size in CONTEXT:
        if name=='identity':words.extend(value[name][field] for field in DEVICE)
        elif name=='lease':words.extend(value[name][field] for field in LEASE)
        else:words.append(value[name])
    return struct.pack('<53Q',*words)


def offset(path):
    parent,*child=path.split('.')
    at=0
    for name,typ,size in CONTEXT:
        if name==parent:
            if child:at+=8*(DEVICE if name=='identity' else LEASE).index(child[0])
            return at
        at+=size
    raise KeyError(path)


def mutated(raw,path,value):
    result=bytearray(raw);struct.pack_into('<Q',result,offset(path),value);return bytes(result)


def enrich(snapshot,control=False):
    """Provide the old controls with a decoded, complete byte-level receipt."""
    c=context.decode_context(encode(original_context(control)),manifest())
    snapshot['context']=c
    snapshot['lease']['virtual']=c['lease']['virtual']
    snapshot['selected_ecam']=c['identity']['ecam'];snapshot['region_base']=0xe0000000
    snapshot['catalog']=dict(ready=1,count=18,incarnations=[0,0,1]+[0]*13,
        snapshots=[{} for _ in range(18)],slots=[(1<<64)-1]*32,
        configurations=[(1<<64)-1]*16)
    snapshot['catalog']['snapshots'][2]=copy.deepcopy(snapshot['snapshot'])
    snapshot['catalog']['slots'][2]=snapshot['catalog_slot']
    snapshot['catalog']['configurations'][2]=snapshot['configuration']
    snapshot['binding']=dict(version=1,device_token=257,role=1,configuration_id=2,
        generation=1,irq_mask=0,flags=2 if control else 6,reserved=0)
    snapshot['ledger_device']=copy.deepcopy(c['identity'])
    if not control:snapshot['ledger_device'].update(flags=7,generation=2)
    snapshot['pci_identity']=copy.deepcopy(c['identity'])
    snapshot['pci_identity'].update(token=0,flags=0,generation=0)
    return snapshot


def observation(control=False):
    from tests.test_virtio_reset_guest import good
    value=good()
    if control:
        value.update(reset_state=0,reset_owner=0,reset_token=0,status=15,quarantined=0,command=0x406,
            snapshot=dict(state=2,status=0,process=259),catalog_slot=2,configuration=2)
        enrich(value,True)
    return value


def archive_boundary(base):
    """Minimal real-byte archive for the replay orchestration unit boundary.

    It omits ELF/page-table decoding and is never evidence of a guest run.
    Actual guest archives must pass ReplayGuest without this substitution.
    """
    guest=base/'guest';guest.mkdir();artifacts=base/'artifacts';artifacts.mkdir()
    (guest/'serial.log').write_bytes(b'host boundary only\n')
    raw=encode(original_context());entries=[]
    for i in range(2):
        name=f'physical-{i:05d}.bin';(guest/name).write_bytes(raw)
        entries.append(dict(physical=0x1000,length=len(raw),role='user.device_host.DmaContext',
                            file=name,sha256=hashlib.sha256(raw).hexdigest()))
    for name in ('dong_layout.json','kernel.elf','block.elf'):
        path=artifacts/name
        path.write_bytes(json.dumps(manifest()).encode() if name=='dong_layout.json' else b'host boundary; not a guest build\n')
    target='services/drivers/block_service.dg'
    sources={target:hashlib.sha256(b'host boundary injected source').hexdigest(),
             'kernel/keep.dg':hashlib.sha256(b'host boundary unchanged source').hexdigest()}
    pristine=dict(sources);pristine[target]=hashlib.sha256(b'host boundary pristine source').hexdigest()
    injection=dict(changed=[target],fixture_sha256=dict(sources),production_sha256=pristine)
    (artifacts/'p5-reset-fixture.json').write_text(json.dumps(injection))
    build=dict(runtime_level=7,test=False,graphics_case=None,source_unchanged=True,source_sha256=dict(sources),
               artifacts={'/host-boundary/kernel.elf':hashlib.sha256((artifacts/'kernel.elf').read_bytes()).hexdigest()})
    (artifacts/'build-inputs.json').write_text(json.dumps(build))
    inputs={name:dict(sha256=hashlib.sha256((artifacts/name).read_bytes()).hexdigest())
            for name in ('dong_layout.json','kernel.elf','block.elf','build-inputs.json','p5-reset-fixture.json')}
    sources['p5-reset-fixture.json']=inputs['p5-reset-fixture.json']['sha256']
    (base/'archived-inputs.json').write_text(json.dumps(dict(artifacts=inputs,source_sha256=sources)))
    snapshots=[observation(),observation()]
    for i,snapshot in enumerate(snapshots):snapshot['dump_range']=[i,i+1]
    result=dict(passed=True,control=False,snapshots=snapshots,source_before=dict(sources),source_after=dict(sources),
                kernel_elf_sha256=inputs['kernel.elf']['sha256'],block_elf_sha256=inputs['block.elf']['sha256'],
                build_manifest_sha256=inputs['build-inputs.json']['sha256'],layout_manifest_sha256=inputs['dong_layout.json']['sha256'],
                fixture_manifest_sha256=inputs['p5-reset-fixture.json']['sha256'])
    path=base/'result.json';path.write_text(json.dumps(result))
    metadata=dict(control=False,serial_sha256=hashlib.sha256((guest/'serial.log').read_bytes()).hexdigest())
    def save_entries():
        (guest/'physical-manifest.json').write_text(json.dumps(entries))
        metadata['physical_manifest_sha256']=hashlib.sha256((guest/'physical-manifest.json').read_bytes()).hexdigest()
        (base/'replay-metadata.json').write_text(json.dumps(metadata))
    save_entries()
    return path,entries,result,save_entries


def replay_boundary_class(runner):
    class RawContextReplay(runner.ReplayGuest):
        def __init__(self,state,metadata,manifest,start,control):
            self.state=state;self.control=control;self.manifest=manifest
            self.cursor=start;self.chunks=list(manifest[:start])
            self.layout=json.loads((state/'artifacts/dong_layout.json').read_text())
        def snapshot(self):
            start=self.cursor
            raw=self.physical(0x1000,424,'user.device_host.DmaContext')
            s=observation(self.control);s['context']=context.decode_context(raw,self.layout)
            s['dump_range']=[start,self.cursor]
            return s
    return RawContextReplay


class ContextGuestControls(unittest.TestCase):
    def test_actual_production_structs_match_compiler_canonical_manifest(self):
        # Frontend-only compilation closes the gap between a hand-written
        # oracle and actual compiler metadata. No assembler, linker or VM runs.
        from lang.dongc import compile_file
        root=Path(__file__).resolve().parents[1]
        def declaration(path,name):
            text=path.read_text();start=text.index('pub struct '+name)
            opening=text.index('{',start);depth=1;end=opening+1
            while depth:
                if text[end]=='{':depth+=1
                elif text[end]=='}':depth-=1
                end+=1
            return text[start:end]
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);(base/'user').mkdir();(base/'lib').mkdir()
            (base/'lib/device_abi.dg').write_bytes((root/'services/lib/device_abi.dg').read_bytes())
            (base/'user/memory.dg').write_text('module user.memory;\n'+declaration(root/'kernel/user/memory.dg','DmaLease'))
            (base/'user/device_host.dg').write_text('module user.device_host;\nimport lib.device_abi as abi;import user.memory as memory;\n'+declaration(root/'kernel/user/device_host.dg','DmaContext'))
            entry=base/'layout_fixture.dg'
            entry.write_text('module layout_fixture;import user.device_host as host;export("context_size") fn context_size()u64{return sizeof(host.DmaContext) as u64;}')
            actual=compile_file(entry,roots=[base],mode='release').layout_manifest
            expected={t['full_name']:t for t in manifest()['types']}
            for name,oracle in expected.items():
                self.assertEqual([t for t in actual['types'] if t['full_name']==name],[oracle])
            self.assertEqual(context.decode_context(encode(original_context()),actual),original_context())

    def test_offline_source_build_and_artifact_provenance_controls(self):
        from tests import run_virtio_reset_qemu as runner
        labels=['source-before','source-after','archive-source-empty','archive-source-replaced','invalid-source-sha','phase-int','pass-int',
                'kernel_elf_sha256','block_elf_sha256','build_manifest_sha256','layout_manifest_sha256',
                'fixture_manifest_sha256','build-runtime','build-test','build-unstable','build-graphics',
                'build-source','build-source-empty','build-kernel-artifact','fixture-changed',
                'fixture-production-extra-change']
        for label in labels:
            with self.subTest(label=label),tempfile.TemporaryDirectory() as temp:
                base=Path(temp);path,entries,result,save=archive_boundary(base)
                archived_path=base/'archived-inputs.json';archived=json.loads(archived_path.read_text())
                def update_artifact(name,value):
                    destination=base/'artifacts'/name;destination.write_text(json.dumps(value))
                    sha=hashlib.sha256(destination.read_bytes()).hexdigest();archived['artifacts'][name]['sha256']=sha
                    key={'build-inputs.json':'build_manifest_sha256','p5-reset-fixture.json':'fixture_manifest_sha256'}[name]
                    result[key]=sha
                    if name=='p5-reset-fixture.json':
                        archived['source_sha256'][name]=sha
                        result['source_before'][name]=result['source_after'][name]=sha
                if label.startswith('source-'):
                    result['source_'+label.split('-')[1]]['kernel/keep.dg']='0'*64
                elif label=='archive-source-empty':archived['source_sha256']={}
                elif label=='archive-source-replaced':archived['source_sha256']['kernel/keep.dg']='0'*64
                elif label=='invalid-source-sha':
                    archived['source_sha256']['kernel/keep.dg']='invalid-sha'
                    result['source_before']['kernel/keep.dg']=result['source_after']['kernel/keep.dg']='invalid-sha'
                elif label=='phase-int':result['control']=0
                elif label=='pass-int':result['passed']=1
                elif label.endswith('_sha256'):result[label]='0'*64
                elif label.startswith('build-'):
                    build=json.loads((base/'artifacts/build-inputs.json').read_text())
                    if label=='build-runtime':build['runtime_level']=6
                    elif label=='build-test':build['test']=True
                    elif label=='build-unstable':build['source_unchanged']=False
                    elif label=='build-graphics':build['graphics_case']='drop-ymm'
                    elif label=='build-source':build['source_sha256']['kernel/keep.dg']='0'*64
                    elif label=='build-source-empty':build['source_sha256']={}
                    elif label=='build-kernel-artifact':build['artifacts']['/host-boundary/kernel.elf']='0'*64
                    update_artifact('build-inputs.json',build)
                else:
                    injection=json.loads((base/'artifacts/p5-reset-fixture.json').read_text())
                    if label=='fixture-changed':injection['changed']=['kernel/keep.dg']
                    else:injection['production_sha256']['kernel/keep.dg']='0'*64
                    update_artifact('p5-reset-fixture.json',injection)
                archived_path.write_text(json.dumps(archived));path.write_text(json.dumps(result))
                with mock.patch.object(runner,'ReplayGuest',replay_boundary_class(runner)):
                    with self.assertRaises(ValueError):context.replay(path)

    def test_offline_physical_reader_checks_order_role_length_hash_and_path(self):
        from tests import run_virtio_reset_qemu as runner
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);path,entries,result,save=archive_boundary(base)
            def reader():
                guest=runner.ReplayGuest.__new__(runner.ReplayGuest)
                guest.state=base;guest.manifest=copy.deepcopy(entries);guest.chunks=[];guest.cursor=0
                return guest
            r=reader();self.assertEqual(r.physical(0x1000,424,'user.device_host.DmaContext'),encode(original_context()))
            self.assertEqual(r.cursor,1)
            for pa,length,role in ((0x2000,424,'user.device_host.DmaContext'),(0x1000,423,'user.device_host.DmaContext'),(0x1000,424,'other-role')):
                with self.subTest(read=(pa,length,role)),self.assertRaises(ValueError):reader().physical(pa,length,role)
            for filename in ('../escape.bin','/absolute.bin','physical-00000.bin/../escape.bin'):
                r=reader();r.manifest[0]['file']=filename
                with self.subTest(filename=filename),self.assertRaises(ValueError):r.physical(0x1000,424,'user.device_host.DmaContext')
            r=reader();r.cursor=2
            with self.assertRaises(ValueError):r.physical(0x1000,424,'user.device_host.DmaContext')
            dump=base/'guest'/entries[0]['file'];original=dump.read_bytes()
            for candidate in (original[:-1],mutated(original,'drain',1)):
                dump.write_bytes(candidate)
                with self.subTest(length=len(candidate)),self.assertRaises(ValueError):reader().physical(0x1000,424,'user.device_host.DmaContext')
            dump.write_bytes(original)
            r=reader();target=base/'guest'/entries[0]['file'];actual=Path.is_symlink
            with mock.patch.object(Path,'is_symlink',lambda p:p==target or actual(p)):
                with self.assertRaises(ValueError):r.physical(0x1000,424,'user.device_host.DmaContext')

    def test_offline_replay_boundary_uses_raw_bytes_and_observation_ranges(self):
        from tests import run_virtio_reset_qemu as runner
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);path,entries,result,save=archive_boundary(base)
            with mock.patch.object(runner,'ReplayGuest',replay_boundary_class(runner)):
                replayed=context.replay(path)
                self.assertEqual(replayed['observations'],result['snapshots'])
                self.assertFalse(replayed['dma_drain_proven'])
                self.assertFalse(replayed['actual_qemu_executed'])
                for ranges in (([1,0],[1,2]),([0,3],[1,2]),([0,1],[0,1]),([0,2],[1,2])):
                    changed=copy.deepcopy(result)
                    for snapshot,span in zip(changed['snapshots'],ranges):snapshot['dump_range']=span
                    path.write_text(json.dumps(changed))
                    with self.subTest(ranges=ranges),self.assertRaises(ValueError):context.replay(path)
                path.write_text(json.dumps(result))
                # Rehash both the actual altered receipt and its manifest, and
                # update the recorded decode. Rejection must be semantic, not
                # merely an obsolete digest or stale JSON comparison.
                raw=mutated(encode(original_context()),'drain',1)
                (base/'guest'/entries[1]['file']).write_bytes(raw)
                entries[1]['sha256']=hashlib.sha256(raw).hexdigest();save()
                changed=copy.deepcopy(result);changed['snapshots'][1]['context']=context.decode_context(raw,manifest())
                path.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError,'held/drain'):context.replay(path)

    def test_exact_nested_abi_bytes_decode(self):
        for control in (False,True):
            raw=encode(original_context(control))
            self.assertEqual(len(raw),424)
            self.assertEqual(context.decode_context(raw,manifest()),original_context(control))
            context.validate_context(observation(control),control)
            context.validate_observations(observation(control),observation(control),control)

    def test_exact_size_short_reads_and_trailing_bytes(self):
        raw=encode(original_context())
        for length in (0,1,55,56,183,184,231,232,295,296,423,425,432):
            candidate=raw[:length] if length<=424 else raw+bytes(length-424)
            with self.subTest(length=length),self.assertRaises(ValueError):context.decode_context(candidate,manifest())

    def test_layout_names_types_offsets_sizes_and_duplicates(self):
        raw=encode(original_context())
        def cases():
            for key,value in [('schema',2),('schema',True),('target','aarch64'),('spec_version','0.2')]:
                m=manifest();m[key]=value;yield key,m
            for index in range(3):
                for key,value in [('name','Wrong'),('size',0),('size',float(manifest()['types'][index]['size'])),('alignment',16),('alignment',8.0),('kind','enum'),('full_name','wrong.Type')]:
                    m=manifest();m['types'][index][key]=value;yield (index,key),m
                for key,value in [('name','duplicate'),('type','u32'),('offset',1),('size',4)]:
                    m=manifest();m['types'][index]['fields'][1][key]=value;yield (index,key,'field'),m
                m=manifest();m['types'][index]['fields'][1]['offset']=0;yield (index,'overlap'),m
                m=manifest();m['types'][index]['fields'][0]['offset']=0.0;yield (index,'float-offset'),m
                m=manifest();m['types'][index]['fields'][0]['size']=8.0;yield (index,'float-size'),m
                m=manifest();m['types'][index]['fields'].append(copy.deepcopy(m['types'][index]['fields'][0]));yield (index,'duplicate-field'),m
                m=manifest();m['types'][index]['fields'].pop();yield (index,'missing-field'),m
            m=manifest();m['types'].append(copy.deepcopy(m['types'][0]));yield 'duplicate-type',m
            m=manifest();m['types'][2]['fields'][7]['type']='user.memory.DmaLease';yield 'wrong-nested-type',m
            m=manifest();m['types'][2]['fields'][7]['size']=64;yield 'short-nested-identity',m
            m=manifest();m['types'][2]['fields'][14]['offset']=184;yield 'nested-lease-overlap',m
            for field in ('pages','attempted','mapped'):
                m=manifest();next(f for f in m['types'][1]['fields'] if f['name']==field)['type']='usize'
                yield ('noncanonical-usize',field),m
        for label,bad in cases():
            with self.subTest(label=label),self.assertRaises(ValueError):context.decode_context(raw,bad)

    def test_every_identity_lease_phase_and_error_raw_field(self):
        raw=encode(original_context())
        values=original_context()
        cases={name:(0 if value else 1) for name,value in values.items() if isinstance(value,int)}
        cases.update(root=0x2000,memory_generation=8,device_generation=2,device_token=513,
            request_bytes=131072,request_alignment=8192,owner=(3<<32)|2,incarnation=2)
        for name,value in values['identity'].items():cases['identity.'+name]=value+1
        for name,value in values['lease'].items():cases['lease.'+name]=value+1
        cases.update({'lease.physical':0,'lease.pages':17,'lease.attempted':17,'lease.mapped':17,'lease.state':1})
        for path,value in cases.items():
            candidate=mutated(raw,path,value)
            self.assertNotEqual(candidate,raw)
            s=observation();s['context']=context.decode_context(candidate,manifest())
            with self.subTest(path=path),self.assertRaises(ValueError):context.validate_context(s)
        # Partial allocator receipts are native-tested by P5CTX1, not asserted
        # to have happened in this initialized-queue guest experiment.
        for physical,attempted,mapped in ((0,0,0),(0x200000,1,0),(0x200000,17,16)):
            bad=mutated(mutated(mutated(mutated(raw,'lease.physical',physical),'lease.attempted',attempted),'lease.mapped',mapped),'lease.state',1)
            s=observation();s['context']=context.decode_context(bad,manifest())
            with self.subTest(partial=(physical,attempted,mapped)),self.assertRaises(ValueError):context.validate_context(s)

    def test_control_rejects_every_retirement_phase(self):
        raw=encode(original_context(True))
        for path,value in [('stop_state',1),('smp_retire',1),('route_state',1),('isolation',1),
                           ('reset',2),('generation_after',2),('held',0),('drain',1)]:
            s=observation(True);s['context']=context.decode_context(mutated(raw,path,value),manifest())
            with self.subTest(path=path),self.assertRaises(ValueError):context.validate_context(s,True)
        from tests import run_virtio_reset_qemu as runner
        for field,value in [('quarantined',1),('command',0x402),('status',0)]:
            s=observation(True);s[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):runner.validate(s,True)

    def test_actual_ledger_binding_and_hardware_raw_fields(self):
        for source,names,typ in [('ledger_device',DEVICE,'lib.device_abi.Device'),
                                 ('pci_identity',DEVICE,'lib.device_abi.Device'),
                                 ('binding',BINDING,'lib.device_abi.Binding')]:
            s=observation();raw=struct.pack('<'+'Q'*len(names),*(s[source][n] for n in names))
            self.assertEqual(context.decode_record(raw,manifest(),typ),s[source])
            for i,name in enumerate(names):
                candidate=bytearray(raw);struct.pack_into('<Q',candidate,8*i,s[source][name]+1)
                bad=observation();bad[source]=context.decode_record(bytes(candidate),manifest(),typ)
                with self.subTest(source=source,field=name),self.assertRaises(ValueError):context.validate_context(bad)

    def test_two_observations_cannot_replace_identity_root_generation_or_lease(self):
        for path,value in [('owner',(3<<32)|2),('incarnation',2),('device_token',513),
                           ('device_generation',2),('root',0x2000),('memory_generation',8),
                           ('identity.ecam',0xe0200000),('lease.physical',0x400000),
                           ('lease.virtual',0x68001000),('lease.pages',64),('lease.root',0x2000),
                           ('lease.generation',8),('lease.attempted',31),('lease.mapped',31)]:
            first=observation();second=observation()
            second['context']=context.decode_context(mutated(encode(original_context()),path,value),manifest())
            with self.subTest(path=path),self.assertRaises(ValueError):context.validate_observations(first,second)

    def test_individually_valid_raw_receipts_cannot_replace_the_first(self):
        for change in ('root','memory-generation','physical','owner','device-token','hardware-identity'):
            first=observation();second=observation();c=original_context()
            if change=='root':
                c['root']=c['lease']['root']=0x2000;second['root']=0x2000
            elif change=='memory-generation':
                c['memory_generation']=c['lease']['generation']=8;second['memory_generation']=8
            elif change=='physical':c['lease']['physical']=0x400000
            elif change=='owner':
                c['incarnation']=2;c['owner']=(3<<32)|2;second['owner']=second['reset_owner']=c['owner']
                second['catalog']['incarnations'][2]=2
            elif change=='device-token':
                c['device_token']=c['identity']['token']=513;c['device_generation']=c['identity']['generation']=2
                c['generation_after']=3;second['device_token']=second['reset_token']=513
                second['binding'].update(device_token=513,generation=2)
                second['ledger_device'].update(token=513,generation=3)
            else:
                c['identity'].update(ecam=0xe0200000,bus=2);second['selected_ecam']=0xe0200000
                second['ledger_device'].update(ecam=0xe0200000,bus=2)
                second['pci_identity'].update(ecam=0xe0200000,bus=2)
            second['context']=context.decode_context(encode(c),manifest())
            second['lease']=copy.deepcopy(second['context']['lease'])
            if change=='device-token':second['ledger_device'].update(token=513,generation=3)
            context.validate_context(first);context.validate_context(second)
            with self.subTest(change=change),self.assertRaises(ValueError):context.validate_observations(first,second)


if __name__=='__main__':unittest.main()
