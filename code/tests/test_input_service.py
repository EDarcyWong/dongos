"""Actual CPL3 input service model: controller setup, IRQs, routing and recovery."""
from __future__ import annotations
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
NAMES=('services/drivers/input_service.dg','services/input/console.dg','services/input/ps2.dg',
 'services/input/events.dg','services/lib/sys.dg','services/lib/device.dg','services/lib/device_abi.dg',
 'services/drivers/tablet_service.dg','services/drivers/pci.dg','services/drivers/virtio_pci.dg',
 'services/drivers/virtio_blk.dg','services/drivers/virtio_tablet.dg','tests/input_service_probe.dg',
 'tests/input_service_probe.c','tests/test_input_service.py')
class InputServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=ROOT/'build/test/input-service/host'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
        cls.before={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in NAMES};(cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
    @classmethod
    def tearDownClass(cls):
        after={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in NAMES};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
        if after!=cls.before:raise AssertionError('input service source changed during native verification')
    def command(self,args,d,n):
        r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(n+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
    def test_real_input_service_irq_ack_resend_and_console(self):
        self.native()
    def test_actual_ack_without_drain_is_rejected(self):self.native(True)
    def test_actual_missing_post_ack_recheck_is_rejected(self):self.native('lost-edge')
    def test_actual_lost_backpressure_obligation_is_rejected(self):self.native('lost-obligation')
    def native(self,negative=False):
        for mode in ('debug','release'):
            with self.subTest(mode=mode):
                d=self.out/((str(negative)+'-' if negative else '')+mode);d.mkdir();services=ROOT/'services'
                if negative:
                    services=d/'services'
                    for p in (ROOT/'services').rglob('*.dg'):
                        q=services/p.relative_to(ROOT/'services');q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes())
                    p=services/'drivers/input_service.dg';source=p.read_text()
                    if negative=='lost-edge':
                        needle='if acknowledged{RECHECK=!(try drain(boot,queue,characters,modern));}'
                        replacement='if acknowledged{RECHECK=false;}'
                    elif negative=='lost-obligation':
                        needle='if acknowledged{RECHECK=!(try drain(boot,queue,characters,modern));}'
                        replacement='if acknowledged{let ignored=try drain(boot,queue,characters,modern);RECHECK=false;}'
                    else:
                        needle='if KEY_PENDING||MOUSE_PENDING||RECHECK{\n                    let drained=try drain(boot,queue,characters,modern);'
                        replacement='if KEY_PENDING||MOUSE_PENDING||RECHECK{\n                    let drained=true;'
                    self.assertEqual(1,source.count(needle));p.write_text(source.replace(needle,replacement))
                    (d/'mutation.json').write_text(json.dumps(dict(mutation=str(negative),expected='independent syscall model rejects lost bytes or unread hardware at ACK'),indent=2)+'\n')
                c=compile_file(ROOT/'tests/input_service_probe.dg',roots=[ROOT/'tests',services,ROOT/'lang/std'],mode=mode)
                src=d/'probe.asm';src.write_text(c.assembly);obj=d/'probe.o';nasm=tool('nasm','NASM');cc=tool('gcc','CC');self.assertTrue(nasm);self.assertTrue(cc)
                r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',str(obj),str(src)],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe');r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',* ([] if os.name=='nt' else ['-no-pie','-D_DEFAULT_SOURCE']),str(ROOT/'tests/input_service_probe.c'),str(obj),'-o',str(exe)],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                for scenario in ([6] if negative=='lost-edge' else [7] if negative=='lost-obligation' else [0] if negative else range(8)):
                    with self.subTest(scenario=scenario):
                        r=self.command([str(exe),str(scenario)],d,'scenario-'+str(scenario))
                        if negative:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('input service check failed line',r.stderr)
                        else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('scenario='+str(scenario)+' passed',r.stdout)
