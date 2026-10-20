"""Host-only rejection controls for G6 input binding and live sampling.

No emulator or native compiler is launched. Synthetic QMP bytes exercise the
real observation ordering; temporary source modules use the real blob builder.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch,Mock
import hashlib,json,struct,sys,unittest
from tests import run_compiler_job_qemu as runner


class GuestRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary=TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.real_load_inputs=runner.load_inputs
        self.root=Path(self.temporary.name);self.source=self.root/'source'
        (self.source/'lang/bootstrap').mkdir(parents=True);(self.source/'lang/std').mkdir()
        self.module=self.source/'lang/bootstrap/compiler_job.dg'
        self.module.write_text('module bootstrap.compiler_job;pub fn run()u64{return 0;}\n',encoding='utf-8')
        self.fixture=self.root/'fixture';self.fixture.mkdir()
        blob,sources=runner.source_blob(self.source)
        self.image=b'\x7fELF'+bytes(4092)  # Data only; no guest is executed here.
        (self.fixture/'sources.bin').write_bytes(blob)
        for name in ('stage1.elf','stage2.elf'):(self.fixture/name).write_bytes(self.image)
        self.receipt=dict(source_stable=True,exact_fixedpoint=True,sources=sources,
            blob_sha256=hashlib.sha256(blob).hexdigest(),elf_sha256=hashlib.sha256(self.image).hexdigest(),elf_bytes=len(self.image))
        self.build=self.root/'build';self.esp=self.build/'esp';(self.esp/'EFI/BOOT').mkdir(parents=True)
        artifacts=[self.build/'kernel.bin',self.build/'kernel.elf',self.esp/'DONGOS.IMG',
            self.esp/'EFI/BOOT/BOOTX64.EFI',self.esp/'SERVICES.BIN']
        for p in artifacts:p.write_bytes(p.name.encode())
        (self.build/'dong_layout.json').write_text('{"types":[]}',encoding='utf-8')
        for name in ('shell','fs','block'):
            p=self.build/'services'/name/'program.elf';p.parent.mkdir(parents=True);p.write_bytes(name.encode())
        self.profile=dict(compiler_job=True,runtime_level=5,source_unchanged=True,
            source_sha256=runner.source_names(sources),artifacts={str(p.resolve()):runner.file_hash(p) for p in artifacts})
        self.save_receipts()

    def save_receipts(self):
        (self.fixture/'receipt.json').write_text(json.dumps(self.receipt),encoding='utf-8')
        (self.build/'build-inputs.json').write_text(json.dumps(self.profile),encoding='utf-8')

    def load(self):return runner.load_inputs(self.source,self.esp,self.fixture)

    def test_real_blob_and_build_manifest_are_accepted(self):
        blob,image,sources,groups=self.load()
        self.assertEqual(blob,runner.source_blob(self.source)[0]);self.assertEqual(image,self.image)
        self.assertEqual(sources,self.profile['source_sha256']);runner.verify_frozen(groups)

    def test_self_consistent_blob_digest_cannot_hide_different_source(self):
        p=self.fixture/'sources.bin';p.write_bytes(p.read_bytes()+b'changed')
        self.receipt['blob_sha256']=runner.file_hash(p);self.save_receipts()
        with self.assertRaisesRegex(ValueError,'source revisions differ'):self.load()

    def test_missing_source_entry_cannot_turn_binding_into_subset_check(self):
        self.receipt['sources']={};self.save_receipts()
        with self.assertRaisesRegex(ValueError,'source revisions differ'):self.load()

    def test_changed_source_and_unproven_fixedpoint_are_rejected(self):
        self.module.write_text(self.module.read_text()+'// changed\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'current source'):self.load()
        self.receipt['exact_fixedpoint']=False;self.save_receipts()
        with self.assertRaisesRegex(ValueError,'fixed point unproven'):self.load()

    def test_missing_or_modified_boot_artifact_is_rejected(self):
        name=str((self.esp/'SERVICES.BIN').resolve());digest=self.profile['artifacts'].pop(name);self.save_receipts()
        with self.assertRaisesRegex(ValueError,'manifest incomplete'):self.load()
        self.profile['artifacts'][name]=digest;self.save_receipts();Path(name).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'differs from build manifest'):self.load()

    def test_each_frozen_input_group_detects_later_changes(self):
        for category in ('sources','harness','fixture','profile'):
            with self.subTest(category=category):
                *_,groups=self.load()
                # Never mutate the checkout's harness; use a private byte copy
                # of an actual entry when checking that group.
                if category=='harness':
                    original=next(iter(groups[category]));p=self.root/'harness.py';p.write_bytes(original.read_bytes())
                    groups[category]={p:runner.file_hash(p)}
                else:p=next(iter(groups[category]))
                old=p.read_bytes();p.write_bytes(old+b'changed')
                try:
                    with self.assertRaisesRegex(ValueError,category):runner.verify_frozen(groups)
                finally:p.write_bytes(old)

    def test_startup_observation_retries_but_real_wrong_identity_fails(self):
        base=runner.p5.KERNEL;kernel_pa=0x200000;boot_pa=0x100000;root=0x300000
        symbols={'__kernel_text_start':base,'__kernel_bss_end':base+0x10000}
        boot=[0]*20;boot[15]=kernel_pa
        memory={(boot_pa,160):struct.pack('<20Q',*boot)}
        values=[('user.compiler_job','RUNNING',b'\1'),('user.memory','FRAME_COUNT',struct.pack('<Q',1)),
            ('user.memory','EXTENDED_LIMIT',struct.pack('<Q',16384)),('user.memory','EXTENDED',struct.pack('<Q',0)),
            ('boot.service_memory','PLAN',bytes(32)+struct.pack('<2Q',0x400000,128*1024*1024)),
            ('user.memory','DYNAMIC_PHYSICAL',struct.pack('<16Q',0,0,0,root,*([0]*12)))]
        process=bytearray(4*1288);struct.pack_into('<2Q',process,3*1288,1,root)
        values += [('user.memory','PROCESSES',bytes(process)),('user.services','CURRENT',struct.pack('<Q',0))]
        for i,(module,name,data) in enumerate(values):
            offset=0x1000+i*0x2000;symbols[runner.p5.symbol(module,name)]=base+offset
            memory[(kernel_pa+offset,len(data))]=data
        symbols['__kernel_bss_end']=base+0x20000
        serial=(f'memory_runtime_boot_info=0x{runner.p5.acpi.HHDM+boot_pa:016x}\r\n'
            'memory_root_physical=0x0000000000500000\r\n'
            'DONGOS_P2_MEMORY_READY\r\nDONGOS_P3_THREADS_READY\r\nDONGOS_P5_SERVICES_START\r\n').encode()
        state=self.root/'observation';state.mkdir();registers='CPL=0 CR3=0000000000500000'
        def qmp(command,arguments=None):
            if command=='human-monitor-command':return registers
            self.assertEqual(command,'pmemsave')
            Path(arguments['filename']).write_bytes(memory[(arguments['val'],arguments['size'])])
        transport=Mock();transport.request.side_effect=qmp
        with patch.object(runner.p5.acpi,'validation_symbols',return_value=symbols),patch.object(runner.p5,'read_owned_frames') as frames:
            self.assertIsNone(runner.live_job(transport,state,serial,self.build,b'',b''));frames.assert_not_called()
            registers=f'CPL=3 CR3={root:016x}'
            with self.assertRaisesRegex(ValueError,'not current published slot3'):
                runner.live_job(transport,state,serial,self.build,b'',b'')
            frames.assert_not_called()

    def test_live_identity_checks_remain_strict_inside_compiler(self):
        self.assertTrue(runner.compiler_context('CPL=3 CR3=00300000',1,0x300000,0x300000,3))
        self.assertFalse(runner.compiler_context('CPL=3 CR3=00400000',1,0x300000,0x300000,0))
        for ready,expected,current in ((0,0x300000,3),(1,0x400000,3),(1,0x300000,0)):
            with self.assertRaisesRegex(ValueError,'not current published slot3'):
                runner.compiler_context('CPL=3 CR3=00300000',ready,0x300000,expected,current)

    def test_input_change_after_seed_prevents_second_boot(self):
        def seed(*args,**kwargs):
            (self.fixture/'stage1.elf').write_bytes(b'changed after seed')
            return dict(passed=True,actual_qemu_executed=True)
        argv=['runner','--esp',str(self.esp),'--fixture',str(self.fixture),'--source-root',str(self.source)]
        with patch.object(runner,'ROOT',self.source),patch.object(runner,'load_inputs',wraps=self.load_inputs_for_main), \
             patch.object(runner,'seed_disk'),patch.object(runner,'boot',side_effect=seed) as boot, \
             patch.object(runner.p5,'check_disk'),patch.object(sys,'argv',argv):
            self.assertEqual(runner.main(),1);self.assertEqual(boot.call_count,1)
        receipt=json.loads(next((self.source/'build/test/l3-guest').glob('*/receipt.json')).read_text())
        self.assertFalse(receipt['passed']);self.assertFalse(receipt['fixture_unchanged'])
        self.assertIn('fixture',' '.join(receipt['errors']));self.assertNotIn('before reboot',receipt['input_checks'])

    def test_bad_fixture_never_starts_emulator_and_retains_failure_receipt(self):
        self.receipt['sources']={};self.save_receipts()
        argv=['runner','--esp',str(self.esp),'--fixture',str(self.fixture),'--source-root',str(self.source)]
        with patch.object(runner,'ROOT',self.source),patch.object(runner,'boot') as boot,patch.object(sys,'argv',argv):
            self.assertEqual(runner.main(),1);boot.assert_not_called()
        receipt=json.loads(next((self.source/'build/test/l3-guest').glob('*/receipt.json')).read_text())
        self.assertFalse(receipt['passed']);self.assertFalse(receipt['actual_qemu_executed'])
        self.assertTrue(receipt['errors'])

    def failure_transport(self,state,*,bad_global=False):
        base=runner.p5.KERNEL;boot_pa=0x100000;kernel_pa=0x200000
        class Symbols(dict):
            def __missing__(self,name):
                value=base+0x1000+len(self)*0x2000
                self[name]=base-1 if bad_global else value
                return self[name]
        symbols=Symbols(__kernel_text_start=base,__kernel_bss_end=base+0x100000)
        boot=[0]*20;boot[15]=kernel_pa;calls=[]
        def request(command,arguments):
            if command=='human-monitor-command':return 'CPL=3 CR3=000000007d995000 RIP=000000001200f7c3'
            # QMP memsave rejects unsigned high-half virtual addresses. Physical
            # captures must also work while a block-service user CR3 is current.
            self.assertEqual(command,'pmemsave');pa=arguments['val'];size=arguments['size']
            self.assertIs(type(pa),int);self.assertTrue(0<pa<1<<48)
            raw=struct.pack('<20Q',*boot) if pa==boot_pa else bytes([pa//4096%256])*size
            Path(arguments['filename']).write_bytes(raw);calls.append((pa,size))
        serial=f'memory_runtime_boot_info=0x{runner.p5.acpi.HHDM+boot_pa:016x}\r\n'.encode()
        return Mock(request=Mock(side_effect=request)),symbols,serial,calls

    def test_failure_snapshot_uses_physical_addresses_under_user_cr3(self):
        state=self.root/'failure';state.mkdir();qmp,symbols,serial,calls=self.failure_transport(state)
        with patch.object(runner.p5.acpi,'validation_symbols',return_value=symbols):
            runner.failure_snapshot(qmp,state,serial,self.build)
        manifest=json.loads((state/'failure-physical-manifest.json').read_text())
        self.assertEqual(len(calls),17);self.assertEqual(len(manifest),17)
        self.assertEqual(manifest[0]['role'],'BootInfo')
        self.assertIn('CPL=3',(state/'failure-registers.txt').read_text())
        for row in manifest:
            raw=(state/row['file']).read_bytes()
            self.assertEqual(len(raw),row['length']);self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])

    def test_failure_snapshot_rejects_unsafe_global_and_retains_partial_evidence(self):
        state=self.root/'failure-bad';state.mkdir();qmp,symbols,serial,calls=self.failure_transport(state,bad_global=True)
        with patch.object(runner.p5.acpi,'validation_symbols',return_value=symbols):
            with self.assertRaisesRegex(ValueError,'global escaped kernel'):
                runner.failure_snapshot(qmp,state,serial,self.build)
        self.assertEqual(calls,[(0x100000,160)])
        self.assertEqual(len(json.loads((state/'failure-physical-manifest.json').read_text())),1)

    def test_failure_snapshot_without_boot_locator_still_retains_registers(self):
        state=self.root/'failure-early';state.mkdir();qmp,symbols,_,calls=self.failure_transport(state)
        with patch.object(runner.p5.acpi,'validation_symbols',return_value=symbols):
            with self.assertRaisesRegex(ValueError,'BootInfo locator'):
                runner.failure_snapshot(qmp,state,b'',self.build)
        self.assertEqual(calls,[]);self.assertTrue((state/'failure-registers.txt').is_file())
        self.assertEqual(json.loads((state/'failure-physical-manifest.json').read_text()),[])

    def load_inputs_for_main(self,*args):
        # Keep actual checkout harness hashes while main writes only in temp.
        with patch.object(runner,'ROOT',Path(__file__).resolve().parents[1]):return self.real_load_inputs(*args)


if __name__=='__main__':unittest.main()
