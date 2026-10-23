"""Pure controls for lifecycle guest evidence; no guest or build is started."""
from pathlib import Path
import struct,tempfile,unittest
from unittest.mock import patch
from tests import run_process_lifecycle_qemu as runner


def catalog_fixture():
    raw=bytearray(10776);struct.pack_into('<3Q',raw,0,1,18,7)
    flags=[7,7,5,7,5,5,7]+[8]*6+[4]+[9]*4
    for index in range(32):
        base=24+128*index;struct.pack_into('<Q',raw,base,1)
        if index<18:
            name=runner.NAMES[index].encode();struct.pack_into('<8Q',raw,base,1,index,runner.DEPS[index],3 if index in (0,1,3,6) else 0,1000,flags[index],index+1,len(name));raw[base+64:base+64+len(name)]=name
    states=24+32*128;slots=states+32*64;incarnations=slots+256;configurations=incarnations+128;events=configurations+128
    order=[5,6,2,4,1,0,3]
    for index in range(32):
        struct.pack_into('<8Q',raw,states+index*64,1,index,0,0,0,0,0,0)
        struct.pack_into('<Q',raw,slots+index*8,runner.NONE)
        if index<16:struct.pack_into('<Q',raw,configurations+index*8,runner.NONE)
    for sequence,index in enumerate(order,1):
        token=256+index+1;struct.pack_into('<8Q',raw,states+index*64,1,index,token,1,2,0,sequence,0)
        struct.pack_into('<Q',raw,slots+index*8,index);struct.pack_into('<Q',raw,incarnations+index*8,1);struct.pack_into('<Q',raw,configurations+index*8,index)
    for index in range(64):struct.pack_into('<Q',raw,events+index*64,1)
    for sequence,index in enumerate(order,1):struct.pack_into('<8Q',raw,events+(sequence-1)*64,1,sequence,index,1,256+index+1,2,0,0)
    return raw,dict(states=states,slots=slots,incarnations=incarnations,configurations=configurations,events=events)


class ProcessLifecycleControls(unittest.TestCase):
    def test_current_gui_autostart_flags_are_exact_not_historical_ordinary_only(self):
        raw,_=catalog_fixture();current=runner.decode_catalog(raw)
        self.assertEqual([9]*4,[c['flags'] for c in current['configs'][14:18]])
        for cfg in range(14,18):
            bad=bytearray(raw);struct.pack_into('<Q',bad,24+cfg*128+40,8)
            with self.subTest(cfg=cfg),self.assertRaises(ValueError):runner.decode_catalog(bad)

    def test_verify_process_reuses_bound_profile_before_reading_elf(self):
        from tests.test_private_pool_oracle import PoolOracleTests
        factory=PoolOracleTests();self.addCleanup(factory.doCleanups)
        class ReachedElf(RuntimeError):pass
        original=Path.read_bytes
        for level in (4,5,6,7):
            guest=factory.guest(True,level)
            def refresh():
                guest.processes=guest._data[guest.ksym('user.memory','PROCESSES')]
                guest.roots=[struct.unpack_from('<Q',guest.processes,i*1288+8)[0] for i in range(16)]
            guest.refresh_processes=refresh;target=guest.esp.parent/'services/fs/program.elf'
            def read(path):
                if path==target:raise ReachedElf('actual ELF checking remains required')
                return original(path)
            with patch.object(Path,'read_bytes',read),self.assertRaises(ReachedElf):runner.ProcessGuest.verify_process(guest,1,'fs')
            self.assertEqual(level!=7,guest.uses_static_pool(1))
        guest=factory.guest(True,7);guest.roots[1]=guest._dynamic[1]=0x230000
        guest._pointers[1]=guest.ksym('user.memory','TABLES')+32*4096;guest.fixture_rebuild()
        def refresh_bad():
            guest.processes=guest._data[guest.ksym('user.memory','PROCESSES')]
            guest.roots=[struct.unpack_from('<Q',guest.processes,i*1288+8)[0] for i in range(16)]
        guest.refresh_processes=refresh_bad
        with self.assertRaises(ValueError):runner.ProcessGuest.verify_process(guest,1,'fs')

    def test_complete_catalog_and_actual_ready_dependencies(self):
        raw,_=catalog_fixture();catalog=runner.decode_catalog(raw);result=runner.check_boot_dag(catalog)
        self.assertEqual([5,6,2,4,1,0,3],result['ready_order']);self.assertEqual(7,catalog['sequence'])
    def test_token_slot_incarnation_and_event_forgery_rejected(self):
        for field,delta in (('states',16),('slots',0),('incarnations',0),('configurations',0),('events',8)):
            raw,offsets=catalog_fixture();struct.pack_into('<Q',raw,offsets[field]+delta,999)
            with self.subTest(field=field),self.assertRaises(ValueError):runner.decode_catalog(raw)
        raw,_=catalog_fixture();raw[24+96]=1
        with self.assertRaises(ValueError):runner.decode_catalog(raw)
        with self.assertRaises(ValueError):runner.decode_catalog(raw[:-1])
    def test_extended_catalog_and_reserved_usb_slot_are_enforced(self):
        raw,_=catalog_fixture();struct.pack_into('<Q',raw,8,13)
        with self.assertRaises(ValueError):runner.decode_catalog(raw)
        raw,offsets=catalog_fixture()
        # A consistent inverse map is still invalid when an ordinary GUI
        # claims the independently reserved USB controller physical slot.
        struct.pack_into('<8Q',raw,offsets['states']+14*64,1,14,270,1,2,0,7,0)
        struct.pack_into('<Q',raw,offsets['slots']+14*8,13)
        struct.pack_into('<Q',raw,offsets['incarnations']+13*8,1)
        struct.pack_into('<Q',raw,offsets['configurations']+13*8,14)
        with self.assertRaises(ValueError):runner.decode_catalog(raw)
        raw,_=catalog_fixture();struct.pack_into('<Q',raw,24+17*128+16,2)
        with self.assertRaises(ValueError):runner.decode_catalog(raw)
    def test_ready_label_cannot_replace_dependency_event_order(self):
        raw,offsets=catalog_fixture();first=raw[offsets['events']:offsets['events']+64];second=raw[offsets['events']+64:offsets['events']+128]
        raw[offsets['events']:offsets['events']+64]=second;raw[offsets['events']+64:offsets['events']+128]=first
        struct.pack_into('<Q',raw,offsets['events']+8,1);struct.pack_into('<Q',raw,offsets['events']+72,2)
        catalog=runner.decode_catalog(raw)
        with self.assertRaises(ValueError):runner.check_boot_dag(catalog)
    def test_process_records_require_one_literal_fresh_status(self):
        line=b'RUN OK echo token=264 generation=3 state=1 status=0\r\n'
        self.assertEqual(264,runner.parse_record(line,'RUN OK','echo')['token'])
        for bad in (b'run echo\r\n',line+line,line.replace(b'token=264',b'token=0'),line.replace(b'state=1',b'state=6')):
            with self.assertRaises(ValueError):runner.parse_record(bad,'RUN OK','echo')
    def test_ps_is_complete_ordered_catalog(self):
        body=b''.join(('PROCESS '+name+' id='+str(index)+' token='+str(257+index if index<7 else 0)+' generation='+str(index<7 and 1 or 0)+' state='+str(index<7 and 2 or 0)+' status=0\r\n').encode() for index,name in enumerate(runner.NAMES))
        self.assertEqual(18,len(runner.parse_ps(body)))
        for bad in (body[:-65],body+body.splitlines()[0]+b'\r\n',body.replace(b'id=0',b'id=1',1)):
            with self.assertRaises(ValueError):runner.parse_ps(bad)
    def test_register_dump_must_be_unique_and_complete(self):
        self.assertEqual(0x1000,runner.parse_registers('CR0=80010033 CR2=0 CR3=0000000000001000 CR4=0000000000000020')['CR3'])
        for bad in ('CR0=1 CR4=2','CR0=1 CR3=2 CR3=3 CR4=4'):
            with self.assertRaises(ValueError):runner.parse_registers(bad)
    def test_host_seed_is_explicit_and_raw_fat_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'data.img';payload=b'\x7fELF'+bytes(range(256))*5
            seeded=runner.seed_executable(path,payload)
            self.assertEqual('/APP.ELF',seeded['host_seeded_input_file']);self.assertTrue(seeded['host_seed_before_guest_start'])
            self.assertEqual(len(payload),seeded['raw']['entries']['/APP.ELF']['size'])
    def test_no_invalid_executable_seed_or_oversize(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'bad.img'
            for payload in (b'',b'not an ELF',b'\x7fELF'+bytes(runner.MAX_EXEC_IMAGE-3)):
                with self.assertRaises(ValueError):runner.seed_executable(path,payload)
            self.assertFalse(path.exists())
    def test_exec_seed_crosses_old_limit_and_accepts_exact_new_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            for length in (262145,runner.MAX_EXEC_IMAGE):
                payload=b'\x7fELF'+bytes(length-4)
                result=runner.seed_executable(Path(temp)/('app-%d.img'%length),payload)
                self.assertEqual(length,result['raw']['entries']['/APP.ELF']['size'])
    def test_fixed_va_probe_requires_cpu_value_and_selected_distinct_pa(self):
        image=dict(image='waiter',pid=7,root=0x900000,bias=0x10000000)
        class Guest:
            roots=[0x100000+i*0x20000 for i in range(16)]
            esp=Path('completed/esp')
            cpu=991833
            physical_word=991833
            child_pa=0x320000
            source_pa=0x320000
            child_flags=runner.NF|5
            source_flags=runner.NF|7
            def catalog(self):return dict(incarnations=[0]*7+[2]+[0]*8)
            def pte(self,root,virtual):
                if root==image['root'] and virtual==0x44000000:return self.child_pa|self.child_flags
                if root==self.roots[1] and virtual==0x53201000:return self.source_pa|self.source_flags
                raise AssertionError('wrong fixed-VA/source selection')
            def user(self,pid,virtual,size,role):
                if (pid,virtual,size)!=(7,0x10001234,8):raise AssertionError('not actual PROBE_VALUE global')
                return struct.pack('<Q',self.cpu)
            def physical(self,address,size,role):
                if (address,size)!=(self.child_pa,8):raise AssertionError('wrong physical probe word')
                return struct.pack('<Q',self.physical_word)
        with patch.object(runner,'read_elf_symbols',return_value={runner.storage.symbol('apps.waiter','PROBE_VALUE'):0x1234}):
            guest=Guest();valid=runner.ProcessGuest.fixed_probe(guest,image,991833)
            self.assertEqual((0x53201000,0x320000,991833),(valid['source_virtual'],valid['physical'],valid['cpu_loaded_value']))
            for name,value in (('cpu',781624),('physical_word',781624),('child_pa',0x321000),('child_flags',5),('source_flags',runner.NF|0x1f)):
                guest=Guest();setattr(guest,name,value)
                with self.subTest(field=name),self.assertRaises(ValueError):runner.ProcessGuest.fixed_probe(guest,image,991833)
