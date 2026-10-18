"""Candidate xHCI controller executes reset, MMIO setup and DMA NoOps."""
from __future__ import annotations
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
NAMES=('xhci_trb.dg','xhci_ring.dg','xhci_context.dg','xhci_controller.dg')

def source_root():
    override=os.environ.get('DONGOS_XHCI_CONTROLLER_ROOT')
    if override:return Path(override)
    production=ROOT/'services'
    return production if (production/'usb/xhci_controller.dg').exists() else ROOT/'build/test/p8-xhci-candidate/services'

class XhciControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.services=source_root()
        cls.inputs=[*(cls.services/'usb'/name for name in NAMES),ROOT/'tests/xhci_core_probe.dg',ROOT/'tests/xhci_core_probe.c',ROOT/'tests/xhci_controller_probe.dg',ROOT/'tests/xhci_controller_probe.c',Path(__file__)]
        cls.out=ROOT/'build/test/p8-xhci-controller/host'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
        cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
    @classmethod
    def tearDownClass(cls):
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
        if after!=cls.before:raise AssertionError('candidate controller inputs changed during execution')
    def command(self,args,d,n):
        r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        (d/(n+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
    def native(self,mutation=None):
        for mode in ('debug','release'):
            with self.subTest(mode=mode,mutation=mutation):
                d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir();services=self.services
                if mutation:
                    services=d/'services';(services/'usb').mkdir(parents=True)
                    for name in NAMES:(services/'usb'/name).write_bytes((self.services/'usb'/name).read_bytes())
                    name='xhci_ring.dg' if mutation=='completion-pointer' else 'xhci_controller.dg'
                    p=services/'usb'/name;source=p.read_text()
                    needle,replacement={
                        'missing-halt':('try wait(s,op+4,1,1);',''),
                        'missing-reset':('try wait(s,op,2,0);',''),
                        'wrong-erst':('try write64(s,runtime+0x30,(*s).setup.physical+ERST_OFFSET);','try write64(s,runtime+0x28,(*s).setup.physical+ERST_OFFSET);'),
                        'late-bme':('    if (*(*s).ops).enable_bme((*s).context)!=0 {return error.IoFailure;}(*s).enabled=1;\n    // ERSTBA submission may fetch the table immediately, even while halted.\n    // Enable only the kernel-admitted private lease before exposing this pointer.\n    try write64(s,runtime+0x30,(*s).setup.physical+ERST_OFFSET);','    try write64(s,runtime+0x30,(*s).setup.physical+ERST_OFFSET);\n    if (*(*s).ops).enable_bme((*s).context)!=0 {return error.IoFailure;}(*s).enabled=1;'),
                        'completion-pointer':('if e.parameter==(*r).physical+(*r).slots[i]*16 {found=i;}','if i==0 {found=i;}'),
                    }[mutation]
                    self.assertEqual(1,source.count(needle));p.write_text(source.replace(needle,replacement))
                    (d/'mutation.json').write_text(json.dumps(dict(mutation=mutation,needle=needle,replacement=replacement,expected='independent MMIO and DMA hardware model rejects actual changed candidate source'),indent=2)+'\n')
                c=compile_file(ROOT/'tests/xhci_controller_probe.dg',roots=[ROOT/'tests',services],mode=mode)
                layouts={x['full_name']:x for x in c.layout_manifest['types']}
                for name,size in {'usb.xhci_controller.Ops':40,'usb.xhci_controller.Setup':112,'usb.xhci_controller.Caps':328,'usb.xhci_controller.State':1280}.items():self.assertEqual(size,layouts[name]['size'])
                src=d/'probe.asm';src.write_text(c.assembly);obj=d/'probe.o';nasm=tool('nasm','NASM');cc=tool('gcc','CC');self.assertTrue(nasm);self.assertTrue(cc)
                r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',str(obj),str(src)],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe')
                r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),str(ROOT/'tests/xhci_controller_probe.c'),str(obj),'-o',str(exe)],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                for scenario in ([9] if mutation=='completion-pointer' else [0] if mutation else range(30)):
                    r=self.command([str(exe),str(scenario)],d,'native-'+str(scenario))
                    if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('xHCI controller check failed line',r.stderr)
                    else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('xHCI controller native scenario='+str(scenario)+' passed;',r.stdout)
    def test_actual_controller_mmio_start_and_faults(self):self.native()
    def test_actual_missing_wait_wrong_register_and_pointer_are_rejected(self):
        for mutation in ('missing-halt','missing-reset','wrong-erst','late-bme','completion-pointer'):self.native(mutation)
