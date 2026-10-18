"""Real init launcher and bounded recovery policy, executed in both modes."""
from __future__ import annotations
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
INPUTS=[ROOT/p for p in ('services/lib/process_abi.dg','services/lib/process.dg','services/lib/sys.dg',
 'services/lib/abi.dg','services/init/policy.dg','services/init/main.dg',
 'tests/init_lifecycle_probe.dg','tests/init_lifecycle_probe.c','tests/test_init_lifecycle.py')]
class InitLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=ROOT/'build/test/init-lifecycle/host'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
        cls.before={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in INPUTS}
        (cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
    @classmethod
    def tearDownClass(cls):
        after={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in INPUTS}
        (cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
        if after!=cls.before:raise AssertionError('init inputs changed during verification')
    def command(self,args,d,name):
        r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        (d/(name+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n')
        return r
    def test_real_launcher_and_exhaustive_independent_graphs(self):
        self.native()
    def test_actual_dependency_and_generation_regressions_are_rejected(self):
        for mutation in ('lost-dependency-kill','accepted-stale-generation'):
            with self.subTest(mutation=mutation):self.native(mutation)
    def native(self,mutation=None):
        for mode in ('debug','release'):
            with self.subTest(mode=mode):
                d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir()
                roots=[ROOT/'tests',ROOT/'services',ROOT/'lang/std']
                if mutation:
                    replacement=d/'services/init';replacement.mkdir(parents=True)
                    (d/'services/lib').mkdir()
                    for relative in ('init/main.dg','lib/process.dg','lib/process_abi.dg','lib/sys.dg','lib/abi.dg'):
                        (d/'services'/relative).write_bytes((ROOT/'services'/relative).read_bytes())
                    source=(ROOT/'services/init/policy.dg').read_text()
                    needle={'lost-dependency-kill':'if (c.dependencies&~bits)!=0 {reason=0x0511_0006;}',
                        'accepted-stale-generation':'if value.generation!=n.generation||value.process!=n.process {return false;}'}[mutation]
                    self.assertEqual(1,source.count(needle))
                    source=source.replace(needle,'if false {return false;}' if mutation=='accepted-stale-generation' else 'if false {reason=0x0511_0006;}')
                    (replacement/'policy.dg').write_text(source);roots[1]=d/'services'
                    (d/'mutation.json').write_text(json.dumps(dict(mutation=mutation,expected='independent C model rejects actual changed Dong implementation'),indent=2)+'\n')
                c=compile_file(ROOT/'tests/init_lifecycle_probe.dg',roots=roots,mode=mode)
                layouts={x['full_name']:x for x in c.layout_manifest['types']}
                for name,size in {'lib.process_abi.Config':128,'lib.process_abi.Snapshot':64,'lib.process_abi.Event':64,'init.policy.Manager':2840,'init.policy.Action':40}.items():self.assertEqual(size,layouts[name]['size'])
                src=d/'probe.asm';src.write_text(c.assembly);obj=d/'probe.o';fmt='win64' if os.name=='nt' else 'elf64'
                nasm=tool('nasm','NASM');cc=tool('gcc','CC');self.assertTrue(nasm);self.assertTrue(cc)
                r=self.command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',str(obj),str(src)],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe')
                r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',* ([] if os.name=='nt' else ['-no-pie']),str(ROOT/'tests/init_lifecycle_probe.c'),str(obj),'-o',str(exe)],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                r=self.command([str(exe)],d,'native')
                if mutation:
                    self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('init lifecycle check failed line',r.stderr)
                else:
                    self.assertEqual(0,r.returncode,r.stdout+r.stderr)
                    self.assertRegex(r.stdout,r'checks passed [0-9]+; exhaustive_graphs=65536; actual_launcher_spawns=3; actual_launcher_kills=1')
