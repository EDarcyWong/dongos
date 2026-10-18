"""Real SPSC publication, concurrent input, US key mapping and F12 focus policy."""
from __future__ import annotations
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
NAMES=('services/input/console.dg','services/input/events.dg','tests/console_probe.dg','tests/console_probe.c','tests/test_console.py')
class ConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=ROOT/'build/test/input-console/host'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
        cls.before={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in NAMES};(cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
    @classmethod
    def tearDownClass(cls):
        after={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in NAMES};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
        if after!=cls.before:raise AssertionError('console source changed during native verification')
    def command(self,args,d,n):
        r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(n+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
    def native(self,mutation=None):
        for mode in ('debug','release'):
            with self.subTest(mode=mode,mutation=mutation):
                d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir();services=ROOT/'services'
                if mutation:
                    services=d/'services';(services/'input').mkdir(parents=True)
                    for n in ('console.dg','events.dg'):(services/'input'/n).write_bytes((ROOT/'services/input'/n).read_bytes())
                    p=services/'input/console.dg';source=p.read_text();needle={'overflow':'if tail-head==CAPACITY','caps':'if shift!=caps'}[mutation];self.assertEqual(1,source.count(needle));p.write_text(source.replace(needle,'if false' if mutation=='overflow' else 'if shift||caps'))
                c=compile_file(ROOT/'tests/console_probe.dg',roots=[ROOT/'tests',services],mode=mode);layouts={x['full_name']:x for x in c.layout_manifest['types']};self.assertEqual(280,layouts['input.console.Queue']['size']);self.assertEqual([0,8,16,24],[x['offset'] for x in layouts['input.console.Queue']['fields']])
                src=d/'probe.asm';src.write_text(c.assembly);obj=d/'probe.o';nasm=tool('nasm','NASM');cc=tool('gcc','CC');self.assertTrue(nasm);self.assertTrue(cc)
                r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',str(obj),str(src)],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe');r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',* ([] if os.name=='nt' else ['-no-pie','-pthread']),str(ROOT/'tests/console_probe.c'),str(obj),'-o',str(exe)],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                r=self.command([str(exe)],d,'native')
                if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('console check failed line',r.stderr)
                else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('concurrent_bytes=100000; F12=ok',r.stdout)
    def test_concurrent_ring_and_keyboard_mapping(self):self.native()
    def test_actual_overwrite_and_caps_regressions_are_rejected(self):
        for mutation in ('overflow','caps'):self.native(mutation)
