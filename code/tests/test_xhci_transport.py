"""Current-source transport regression, not a replay of an unavailable snapshot.

Actual controller+enumerator against independent DMA hardware.
"""
from __future__ import annotations
import hashlib,json,os,shutil,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'services/usb/xhci_transport.dg'
class XhciTransportTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.out=ROOT/'build/test/p8-xhci-transport'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
  cls.inputs=[SOURCE,*[ROOT/('services/usb/'+n+'.dg') for n in ('xhci_controller','xhci_trb','xhci_ring','xhci_context','transport','descriptor','enumerate')],*[ROOT/('tests/'+n) for n in ('xhci_transport_probe.dg','xhci_transport_probe.c','xhci_controller_probe.dg','xhci_controller_probe.c','xhci_core_probe.dg','xhci_core_probe.c')],Path(__file__)]
  cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
 @classmethod
 def tearDownClass(cls):
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
  if after!=cls.before:raise AssertionError('USB transport/source models changed during verification')
 def command(self,args,d,name):
  r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(name+'.json')).write_text(json.dumps(dict(command=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
 def native(self,mutation=None):
  for mode in ('debug','release'):
   d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir();source=SOURCE.parents[1]
   if mutation:
    source=d/'services';shutil.copytree(ROOT/'services',source);s=SOURCE.read_text()
    old,new={
     'command-pointer':('match ring.complete(&(*c).command,(*s).epoch,(*s).command_generation,e,','var sanitized=*e;sanitized.parameter=(*c).command.physical+(*c).command.slots[0]*16;match ring.complete(&(*c).command,(*s).epoch,(*s).command_generation,&sanitized,'),
     'transfer-pointer':('match ring.complete(r,(*s).epoch,(*p).generation,e,','var sanitized=*e;sanitized.parameter=(*r).physical+(*r).slots[(*r).count-1]*16;match ring.complete(r,(*s).epoch,(*p).generation,&sanitized,'),
     'skip-erdp':('try write64(s,(*c).caps.runtime+0x38,pointer);','let omitted:u64=pointer;'),
     'short-before-status':('(*p).actual=(*p).bytes-completion.residual;(*p).shortened=1;return;','(*p).actual=(*p).bytes-completion.residual;(*p).shortened=1;try completed(s,p,0);return;'),
    }[mutation];self.assertEqual(1,s.count(old));(source/'usb/xhci_transport.dg').write_text(s.replace(old,new))
   c=compile_file(ROOT/'tests/xhci_transport_probe.dg',roots=[ROOT/'tests',source],mode=mode);layouts={i['full_name']:i for i in c.layout_manifest['types']};self.assertEqual(112,layouts['usb.xhci_transport.Pending']['size']);self.assertEqual(720+12*112+7*8,layouts['usb.xhci_transport.State']['size']);self.assertEqual(1784,layouts['usb.enumerate.State']['size']);self.assertNotRegex(c.assembly.lower(),r'\b(?:invlpg|invpcid|rdmsr|wrmsr|hlt|cli|sti)\b');asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o';nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
   r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
   model=(ROOT/'tests/xhci_controller_probe.c').read_text();self.assertEqual(1,model.count('int main(int argc,char**argv)'));(d/'xhci_transport_controller_model.h').write_text(model.replace('int main(int argc,char**argv)','int xhci_controller_unused_main(int argc,char**argv)'))
   exe=d/('probe.exe' if os.name=='nt' else 'probe');r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-strict-aliasing','-I',ROOT/'tests','-I',d,*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),ROOT/'tests/xhci_transport_probe.c',obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
   scenarios=('normal','high-speed','superspeed','reset-timeout','command-timeout','command-pointer','command-slot','transfer-pointer','short-data','missing-status','buffer-alias','ring-alias','wrap')
   if mutation:scenarios=({'command-pointer':'command-pointer','transfer-pointer':'transfer-pointer','skip-erdp':'normal','short-before-status':'missing-status'}[mutation],)
   for scenario in scenarios:
    r=self.command([exe,scenario],d,scenario)
    if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('xHCI transport check failed line',r.stderr)
    else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('xHCI transport native checks passed',r.stdout)
 def test_actual_controller_to_ep0_to_hid_endpoint(self):self.native()
 def test_actual_corrupt_transport_sources_are_rejected(self):
  for mutation in ('command-pointer','transfer-pointer','skip-erdp','short-before-status'):self.native(mutation)
