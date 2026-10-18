"""Actual async event multiplexer and recovery over independent DMA hardware."""
from __future__ import annotations
import hashlib,json,os,subprocess,unittest,uuid,shutil
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'build/test/p8-async-candidate/services/usb/xhci_transport.dg'
class XhciAsyncTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.out=ROOT/'build/test/p8-xhci-async'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
  cls.inputs=[SOURCE,*[ROOT/('services/usb/'+n+'.dg') for n in ('xhci_controller','xhci_trb','xhci_ring','xhci_context','transport','descriptor','enumerate','bot')],*[ROOT/('tests/'+n) for n in ('xhci_async_probe.dg','xhci_async_probe.c','xhci_controller_probe.dg','xhci_controller_probe.c','xhci_core_probe.dg','xhci_core_probe.c')],Path(__file__)]
  cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
 @classmethod
 def tearDownClass(cls):
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
  if after!=cls.before:raise AssertionError('USB transport/source models changed during verification')
 def command(self,args,d,name):
  r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(name+'.json')).write_text(json.dumps(dict(command=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
 def native(self,mutation=None):
  for mode in ('debug','release'):
   d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir();source=d/'services';shutil.copytree(ROOT/'services',source);shutil.copyfile(SOURCE,source/'usb/xhci_transport.dg')
   if mutation:
    s=SOURCE.read_text()
    old,new={
     'discard-hid':('if (*p).done!=0||(*r).epoch!=','if (*p).asynchronous==1 {return;}if (*p).done!=0||(*r).epoch!='),
     'no-reset':('try submit(s,&reset,end,&result);','result=slot;'),
     'no-set-dequeue':('try submit(s,&set,end,&result);','result=slot;'),
     'clear-before-completion':('try submit(s,&set,end,&result);','(*r).fault=0;(*r).pending=0;try submit(s,&set,end,&result);'),
     'idle-deadline':('try healthy(s);var i:u64=0;while i<budget','try ended(s,(*s).last_tsc+1000);var i:u64=0;while i<budget'),
     'accept-stale':('let count=(*r).count;match ring.complete(r,(*s).epoch,(*p).generation,e,','let count=(*r).count;var sanitized=*e;sanitized.parameter=(*r).physical+(*r).slots[0]*16;match ring.complete(r,(*s).epoch,(*p).generation,&sanitized,'),
    }[mutation];self.assertEqual(1,s.count(old));(source/'usb/xhci_transport.dg').write_text(s.replace(old,new))
   c=compile_file(ROOT/'tests/xhci_async_probe.dg',roots=[ROOT/'tests',source],mode=mode);layouts={i['full_name']:i for i in c.layout_manifest['types']};self.assertEqual(2120,layouts['usb.xhci_transport.State']['size']);self.assertEqual(1784,layouts['usb.enumerate.State']['size']);self.assertNotRegex(c.assembly.lower(),r'\b(?:invlpg|invpcid|rdmsr|wrmsr|hlt|cli|sti)\b');asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o';nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
   r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
   model=(ROOT/'tests/xhci_controller_probe.c').read_text();self.assertEqual(1,model.count('int main(int argc,char**argv)'));(d/'xhci_transport_controller_model.h').write_text(model.replace('int main(int argc,char**argv)','int xhci_controller_unused_main(int argc,char**argv)'))
   exe=d/('probe.exe' if os.name=='nt' else 'probe');r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-strict-aliasing','-I',ROOT/'tests','-I',d,*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),ROOT/'tests/xhci_async_probe.c',obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
   scenarios=('idle','command-mux','ep0-mux','bot','getlun-stall','bulk-stall','phase-recovery','bad-csw','stale-event','wrong-endpoint','hid-stall','recovery-timeout','recovery-pointer','bad-dequeue-readback','ownership','async-wrap','recover-before-complete','generation','disconnect','short-report','bulk-short')
   if mutation:scenarios=({'discard-hid':'command-mux','no-reset':'hid-stall','no-set-dequeue':'hid-stall','idle-deadline':'idle','accept-stale':'stale-event','clear-before-completion':'recovery-timeout'}[mutation],)
   for scenario in scenarios:
    r=self.command([exe,scenario],d,scenario)
    if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('xHCI transport check failed line',r.stderr)
    else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('xHCI async native checks passed',r.stdout)
 def test_actual_async_hid_ep0_bot_and_endpoint_recovery(self):self.native()
 def test_actual_corrupt_transport_sources_are_rejected(self):
  for mutation in ('discard-hid','no-reset','no-set-dequeue','idle-deadline','accept-stale','clear-before-completion'):self.native(mutation)
