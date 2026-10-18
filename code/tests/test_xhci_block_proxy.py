"""Actual block2 request boundary, real BOT/xHCI source, independent DMA model."""
from __future__ import annotations
import hashlib,json,os,subprocess,unittest,uuid,shutil
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'build/test/p8-rpc-candidate/services/usb/block_proxy.dg'
ADAPTER=ROOT/'build/test/p8-async-candidate/services/usb/xhci_transport.dg'
class XhciBlockProxyTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.out=ROOT/'build/test/p8-xhci-block-proxy'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
  cls.inputs=[SOURCE,ADAPTER,*[ROOT/('services/usb/'+n+'.dg') for n in ('xhci_controller','xhci_trb','xhci_ring','xhci_context','transport','descriptor','enumerate','bot')],*[ROOT/('tests/'+n) for n in ('xhci_block_proxy_probe.dg','xhci_block_proxy_probe.c','xhci_async_probe.dg','xhci_async_probe.c','xhci_controller_probe.dg','xhci_controller_probe.c','xhci_core_probe.dg','xhci_core_probe.c')],Path(__file__)]
  cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
 @classmethod
 def tearDownClass(cls):
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
  if after!=cls.before:raise AssertionError('USB transport/source models changed during verification')
 def command(self,args,d,name):
  r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(name+'.json')).write_text(json.dumps(dict(command=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
 def native(self,mutation=None):
  for mode in ('debug','release'):
   d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir();source=d/'services';shutil.copytree(ROOT/'services',source);shutil.copyfile(ADAPTER,source/'usb/xhci_transport.dg');shutil.copyfile(SOURCE,source/'usb/block_proxy.dg')
   if mutation:
    s=SOURCE.read_text()
    old,new={
     'peer':('if peer!=3||','if false||'),
     'epoch':('(epochs>>32)!=(*s).epoch||','false||'),
     'skip-write-copy':('if !inward {while i<bytes','if false {while i<bytes'),
     'skip-flush':('try bot.synchronize((*s).storage);','let omitted:u64=0;'),
     'early-read-copy':('try bot.read_write((*s).storage,lba+done,chunk,&data,inward);','if inward {i=0;while i<bytes {*(shared+i as usize)=*(data.pointer+i as usize);i+=1;}}try bot.read_write((*s).storage,lba+done,chunk,&data,inward);'),
    }[mutation];self.assertEqual(1,s.count(old));(source/'usb/block_proxy.dg').write_text(s.replace(old,new))
   c=compile_file(ROOT/'tests/xhci_block_proxy_probe.dg',roots=[ROOT/'tests',source],mode=mode);layouts={i['full_name']:i for i in c.layout_manifest['types']};self.assertEqual(2120,layouts['usb.xhci_transport.State']['size']);self.assertEqual(1784,layouts['usb.enumerate.State']['size']);self.assertNotRegex(c.assembly.lower(),r'\b(?:invlpg|invpcid|rdmsr|wrmsr|hlt|cli|sti)\b');asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o';nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
   r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
   model=(ROOT/'tests/xhci_controller_probe.c').read_text();self.assertEqual(1,model.count('int main(int argc,char**argv)'));(d/'xhci_transport_controller_model.h').write_text(model.replace('int main(int argc,char**argv)','int xhci_controller_unused_main(int argc,char**argv)'))
   model=(ROOT/'tests/xhci_async_probe.c').read_text();self.assertEqual(1,model.count('int main(int argc,char**argv)'));model=model.replace('int main(int argc,char**argv)','int xhci_async_unused_main(int argc,char**argv)').replace('disk[8192],durable[8192]','disk[131072],durable[131072]').replace('xbeput(p,15);','xbeput(p,255);').replace('x->bot_lba<16','x->bot_lba<256').replace('x->bot_lba+x->bot_count<=16','x->bot_lba+x->bot_count<=256')
   old='if(x->stall_once){x->stall_once=0;xcontext_state(x,2,endpoint,2)';self.assertEqual(1,model.count(old));model=model.replace(old,'if(!strcmp(x->scenario,"partial-read")&&x->bot_lba==24&&!x->wire_stall)x->stall_once=1;'+old)
   (d/'xhci_block_proxy_async_model.h').write_text(model)
   exe=d/('probe.exe' if os.name=='nt' else 'probe');r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-strict-aliasing','-I',ROOT/'tests','-I',d,*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),ROOT/'tests/xhci_block_proxy_probe.c',obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
   scenarios=('normal','peer','epochs','bounds','short-read','partial-read','alias')
   if mutation:scenarios=({'peer':'peer','epoch':'epochs','skip-write-copy':'normal','skip-flush':'normal','early-read-copy':'short-read'}[mutation],)
   for scenario in scenarios:
    r=self.command([exe,scenario],d,scenario)
    if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('xHCI transport check failed line',r.stderr)
    else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('xHCI block proxy native checks passed',r.stdout)
 def test_actual_block_requests_and_private_dma(self):self.native()
 def test_actual_corrupt_transport_sources_are_rejected(self):
  for mutation in ('peer','epoch','skip-write-copy','skip-flush','early-read-copy'):self.native(mutation)
