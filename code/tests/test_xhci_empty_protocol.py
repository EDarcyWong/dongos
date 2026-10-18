"""Actual xHCI precheck with captured QEMU BAR; empty ranges grant no ports."""
import hashlib,json,os,shutil,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_input import command
from tests.test_fat32 import stack_bound
ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT/'build/test/p8-zero-protocol-candidate/services/usb/xhci_controller.dg'
SUFFIX='\nexport("xhp_check") unsafe fn probe_precheck(ops:*const Ops,context:u64,s:*const Setup,out:*Caps)u64{unsafe{match precheck(ops,context,s,out){ok=>{return 0;},err(e)=>{return e;},}}}\n'
class XhciEmptyProtocolTests(unittest.TestCase):
 def test_captured_bar_empty_ranges_and_real_bad_implementations(self):
  paths=[CANDIDATE,ROOT/'services/usb/xhci_trb.dg',ROOT/'services/usb/xhci_ring.dg',ROOT/'tests/xhci_empty_protocol_probe.c',Path(__file__)]
  before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};out=ROOT/'build/test/xhci-empty-protocol'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);evidence=[]
  variants={
   'rejects-empty':('if start==0||start>c.ports+1','if start==0||ports==0||start>c.ports+1',0),
   'grants-empty-port':('var i=start-1;while i<start-1+ports','if ports==0{c.protocols[(start-1) as usize]=major;}var i=start-1;while i<start-1+ports',0),
   'ignores-empty-major':('(major!=2&&major!=3)','(ports!=0&&(major!=2&&major!=3))',4),
   'ignores-empty-name':('if (try read_raw(ops,context,s,offset+4))!=0x2042_5355','if (header>>24)==2&&(try read_raw(ops,context,s,offset+4))!=0x2042_5355',5),
   'ignores-empty-slot':('||(slot&~31)!=0||(slot&31)!=0','||(ports!=0&&((slot&~31)!=0||(slot&31)!=0))',7),
   'empty-breaks-chain':('var i=start-1;while i<start-1+ports','if ports==0{break;}var i=start-1;while i<start-1+ports',13),
   'allows-beyond-port-boundary':('ports>c.ports+1-start','false',19),
  }
  for mode in ('debug','release'):
   for variant in ('normal',*variants):
    d=out/(variant+'-'+mode);stage=d/'source';(stage/'usb').mkdir(parents=True)
    for name in ('xhci_trb.dg','xhci_ring.dg','xhci_controller.dg'):
     p=CANDIDATE if name=='xhci_controller.dg' else ROOT/'services/usb'/name;(stage/'usb'/name).write_bytes(p.read_bytes())
    p=stage/'usb/xhci_controller.dg';s=p.read_text()
    if variant!='normal':old,new,scenario=variants[variant];self.assertEqual(1,s.count(old));s=s.replace(old,new,1)
    p.write_text(s+SUFFIX);r=compile_file(p,roots=[stage],mode=mode);asm=d/'probe.asm';asm.write_text(r.assembly);bound=stack_bound(r.assembly);self.assertLessEqual(bound,12288);nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
    for fmt in ('elf64','win64'):command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',d/(fmt+'.o'),asm],d,'assemble-'+fmt)
    exe=d/('probe.exe' if os.name=='nt' else 'probe');command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),ROOT/'tests/xhci_empty_protocol_probe.c',d/('win64.o' if os.name=='nt' else 'elf64.o'),'-o',exe],d,'link')
    for scenario in range(20) if variant=='normal' else (variants[variant][2],):
     result=command([exe,str(scenario)],d,'native-'+str(scenario),success=False);self.assertEqual(0 if variant=='normal' else 1,result.returncode,result.stdout+result.stderr);self.assertIn('XHCI_EMPTY_PROTOCOL_NATIVE_PASS' if variant=='normal' else 'XHCI_EMPTY_PROTOCOL_ASSERT',result.stdout+result.stderr);evidence.append(dict(mode=mode,variant=variant,scenario=scenario,stack=bound,stdout=result.stdout,stderr=result.stderr))
  self.assertEqual(before,{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths});(out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_unchanged=True,source_sha256=before,actual_precheck=True,bar_fixture='build/test/p8-xhci/qemu/run-822f626b7974/failure-capabilities.json',mmio_callbacks_only=True,vm_started=False,evidence=evidence),indent=2)+'\n');print('XHCI_EMPTY_PROTOCOL_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
