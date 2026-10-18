"""ISA IRQ routing executes the production IOAPIC code with a strict register model."""
from __future__ import annotations
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
NAMES=('kernel/irq/platform.dg','kernel/irq/clock_calibration.dg','kernel/boot/device_policy.dg',
 'kernel/firmware/acpi.dg','kernel/firmware/acpi_errors.dg','tests/isa_irq_probe.dg','tests/isa_irq_probe.c',
 'tests/irq_platform_probe.dg','tests/irq_platform_probe.c','tests/test_isa_irq.py')
class IsaIrqTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=ROOT/'build/test/isa-irq/host'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
        cls.before={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in NAMES}
        (cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
    @classmethod
    def tearDownClass(cls):
        after={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in NAMES};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
        if after!=cls.before:raise AssertionError('ISA IRQ inputs changed during native verification')
    def command(self,args,d,name):
        r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(name+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
    def test_iso_route_mask_readback_eoi_and_errors(self):
        self.native()
    def test_actual_omitted_mask_and_destination_readbacks_are_rejected(self):
        for mutation in ('mask-readback','destination-readback'):self.native(mutation)
    def native(self,mutation=None):
        for mode in ('debug','release'):
            with self.subTest(mode=mode):
                d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir();kernel=ROOT/'kernel'
                if mutation:
                    kernel=d/'kernel'
                    for p in (ROOT/'kernel').rglob('*.dg'):
                        q=kernel/p.relative_to(ROOT/'kernel');q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes())
                    path=kernel/'irq/platform.dg';source=path.read_text()
                    needle={'mask-readback':'if (io_read(controller,register)&MASK)==0 {return error.HardwareReadback;}',
                        'destination-readback':'if (io_read(controller,register+1)&ROUTE_HIGH_MASK)!=high {return error.HardwareReadback;}'}[mutation]
                    self.assertEqual(1,source.count(needle));path.write_text(source.replace(needle,'if false {return error.HardwareReadback;}'))
                    (d/'mutation.json').write_text(json.dumps(dict(mutation=mutation,expected='strict independent MMIO model rejects actual omitted production readback'),indent=2)+'\n')
                c=compile_file(ROOT/'tests/isa_irq_probe.dg',roots=[ROOT/'tests',kernel,ROOT/'lang/std',ROOT/'lang/examples'],mode=mode)
                layouts={x['full_name']:x for x in c.layout_manifest['types']};self.assertEqual(80,layouts['irq.platform.IsaRoute']['size'])
                src=d/'probe.asm';src.write_text(c.assembly);obj=d/'probe.o';nasm=tool('nasm','NASM');cc=tool('gcc','CC');self.assertTrue(nasm);self.assertTrue(cc)
                r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',str(obj),str(src)],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe')
                r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',* (['-mno-sse'] if os.name=='nt' else ['-no-pie']),str(ROOT/'tests/isa_irq_probe.c'),str(obj),'-o',str(exe)],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                for scenario in ([0] if mutation else range(15)):
                    with self.subTest(scenario=scenario):
                        r=self.command([str(exe),str(scenario)],d,'scenario-'+str(scenario))
                        if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('IRQ_MODEL_ASSERT',r.stderr)
                        else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('scenario='+str(scenario)+' passed',r.stdout)
