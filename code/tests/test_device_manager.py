"""Kernel device/IRQ authority and production CPL3 manager against independent models."""
from __future__ import annotations
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
NAMES=('kernel/user/device_manager.dg','services/lib/device_abi.dg','services/lib/device.dg',
 'services/drivers/device_policy.dg','services/drivers/device_manager.dg','services/lib/process_abi.dg',
 'services/lib/process.dg','services/lib/sys.dg','services/lib/abi.dg',
 'tests/device_manager_probe.dg','tests/device_manager_probe.c','tests/test_device_manager.py')
class DeviceManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=ROOT/'build/test/device-manager/host'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
        cls.before={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in NAMES}
        (cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
    @classmethod
    def tearDownClass(cls):
        after={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in NAMES}
        (cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
        if after!=cls.before:raise AssertionError('device manager inputs changed during native verification')
    def command(self,args,d,name):
        r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        (d/(name+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
    def native(self,mutation=None):
        for mode in ('debug','release'):
            with self.subTest(mode=mode,mutation=mutation):
                d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir();services=ROOT/'services';kernel=ROOT/'kernel'
                if mutation:
                    services=d/'services';kernel=d/'kernel'
                    for n in NAMES:
                        if n.startswith(('services/','kernel/')):
                            p=d/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/n).read_bytes())
                    if mutation=='accepted-replaced-device':
                        path=services/'drivers/device_policy.dg';src=path.read_text();needle='return (*a).version==(*b).version&&(*a).kind==(*b).kind&&(*a).ecam==(*b).ecam&&(*a).segment==(*b).segment'
                        self.assertEqual(1,src.count(needle));src=src.replace(needle,'return true||(*a).version==(*b).version&&(*a).kind==(*b).kind&&(*a).ecam==(*b).ecam&&(*a).segment==(*b).segment')
                    elif mutation in ('skipped-recovery-retirement','reused-recovery-token'):
                        path=kernel/'user/device_manager.dg';src=path.read_text()
                        needle,replacement={
                            'skipped-recovery-retirement':('if (*ops).retire(context,token,generation)!=0','if false'),
                            'reused-recovery-token':('fresh.token=(generation<<8)|slot','fresh.token=token'),
                        }[mutation]
                        self.assertEqual(1,src.count(needle));src=src.replace(needle,replacement)
                    else:
                        path=kernel/'user/device_manager.dg';src=path.read_text();needle='sequence==0||sequence!=view.sequence||view.flags!=(abi.MASKED|abi.PENDING)'
                        self.assertEqual(1,src.count(needle));src=src.replace(needle,'sequence==0||view.flags!=(abi.MASKED|abi.PENDING)')
                    path.write_text(src);(d/'mutation.json').write_text(json.dumps(dict(mutation=mutation,expected='independent native model rejects actual changed Dong source'),indent=2)+'\n')
                c=compile_file(ROOT/'tests/device_manager_probe.dg',roots=[ROOT/'tests',kernel,services,ROOT/'lang/std'],mode=mode)
                layouts={x['full_name']:x for x in c.layout_manifest['types']}
                for n,size in {'lib.device_abi.Device':128,'lib.device_abi.Binding':64,'lib.device_abi.Irq':64,'user.device_manager.Table':4560}.items():self.assertEqual(size,layouts[n]['size'])
                src=d/'probe.asm';src.write_text(c.assembly);obj=d/'probe.o';nasm=tool('nasm','NASM');cc=tool('gcc','CC');self.assertTrue(nasm);self.assertTrue(cc)
                r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',str(obj),str(src)],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe')
                r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',* ([] if os.name=='nt' else ['-no-pie']),str(ROOT/'tests/device_manager_probe.c'),str(obj),'-o',str(exe)],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                r=self.command([str(exe)],d,'native')
                if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('device manager check failed line',r.stderr)
                else:
                    self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertRegex(r.stdout,r'checks passed [0-9]+; irq_rounds=1024; launcher_bindings=3; launcher_revocations=1')
                    r=self.command([str(exe),'catalog-failure'],d,'catalog-failure');self.assertEqual(0,r.returncode,r.stdout+r.stderr)
                    self.assertRegex(r.stdout,r'checks passed [0-9]+; irq_rounds=1024; launcher_bindings=3; launcher_revocations=3')
    def test_independent_authority_irq_and_actual_launcher(self):self.native()
    def test_actual_replaced_identity_and_stale_ack_are_rejected(self):
        for mutation in ('accepted-replaced-device','accepted-stale-ack'):self.native(mutation)

    def test_recovery_frontend_both_modes(self):
        # This is only a compiler/ABI check, not native or hardware execution.
        for mode in ('debug','release'):
            c=compile_file(ROOT/'tests/device_manager_probe.dg',roots=[ROOT/'tests',ROOT/'kernel',ROOT/'services',ROOT/'lang/std'],mode=mode)
            layouts={x['full_name']:x for x in c.layout_manifest['types']}
            self.assertEqual(4560,layouts['user.device_manager.Table']['size'])
            self.assertEqual(32,layouts['user.device_manager.RecoveryOps']['size'])
            self.assertIn('dm_recover',c.assembly)
    def test_actual_recovery_mutations_are_rejected(self):
        for mutation in ('skipped-recovery-retirement','reused-recovery-token'):self.native(mutation)
