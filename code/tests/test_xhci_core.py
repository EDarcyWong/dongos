"""Current-source regression, not a replay of unavailable candidate snapshots.

Tracked production xHCI TRB/rings against a DMA-byte hardware consumer."""
from __future__ import annotations
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
def source_root():
    production=ROOT/'services'
    return production
class XhciCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.services=source_root();cls.inputs=[cls.services/'usb/xhci_trb.dg',cls.services/'usb/xhci_ring.dg',cls.services/'usb/xhci_context.dg',ROOT/'tests/xhci_core_probe.dg',ROOT/'tests/xhci_core_probe.c',Path(__file__)]
        cls.out=ROOT/'build/test/p8-xhci-core/host'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
        cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
    @classmethod
    def tearDownClass(cls):
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
        if after!=cls.before:raise AssertionError('current xHCI inputs changed during native execution')
    def command(self,args,d,n):
        r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(n+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
    def native(self,mutation=None):
        for mode in ('debug','release'):
            with self.subTest(mode=mode,mutation=mutation):
                d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir();services=self.services
                if mutation:
                    services=d/'services';(services/'usb').mkdir(parents=True)
                    for name in ('xhci_ring.dg','xhci_trb.dg','xhci_context.dg'):(services/'usb'/name).write_bytes((self.services/'usb'/name).read_bytes())
                    p=services/'usb/xhci_ring.dg';source=p.read_text()
                    needle={'link-toggle':'((6<<10)|2|(*p).link_cycle) as u32','missing-publication-fence':'let first=barrier(ops,context,1);'}[mutation]
                    self.assertEqual(1,source.count(needle));source=source.replace(needle,'((6<<10)|(*p).link_cycle) as u32' if mutation=='link-toggle' else 'let first=omitted_fence();')
                    if mutation=='missing-publication-fence':source+='\nunsafe fn omitted_fence()!void {return;}\n'
                    p.write_text(source);(d/'mutation.json').write_text(json.dumps(dict(mutation=mutation,expected='same independent hardware consumer rejects actual changed current production source'),indent=2)+'\n')
                c=compile_file(ROOT/'tests/xhci_core_probe.dg',roots=[ROOT/'tests',services],mode=mode)
                layouts={x['full_name']:x for x in c.layout_manifest['types']}
                for name,size in {'usb.xhci_trb.Trb':16,'usb.xhci_trb.Event':64,'usb.xhci_ring.Producer':320,'usb.xhci_ring.Plan':320,'usb.xhci_ring.Consumer':88}.items():self.assertEqual(size,layouts[name]['size'])
                src=d/'probe.asm';src.write_text(c.assembly);obj=d/'probe.o';nasm=tool('nasm','NASM');cc=tool('gcc','CC');self.assertTrue(nasm);self.assertTrue(cc)
                r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',str(obj),str(src)],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe');r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',* (['-mno-sse'] if os.name=='nt' else ['-no-pie']),str(ROOT/'tests/xhci_core_probe.c'),str(obj),'-o',str(exe)],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                r=self.command([str(exe)],d,'native')
                if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('xHCI core check failed line',r.stderr)
                else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertRegex(r.stdout,r'checks passed [0-9]+; commands=[0-9]+; transfer_TRBs=[0-9]+; events=[0-9]+; ring_wraps=[0-9]+')
    def test_actual_trb_dma_rings_and_fault_retention(self):self.native()
    def test_actual_missing_link_toggle_and_fence_are_rejected(self):
        for mutation in ('link-toggle','missing-publication-fence'):self.native(mutation)
