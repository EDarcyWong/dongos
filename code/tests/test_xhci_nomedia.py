"""Current-source regression, not a replay of unavailable candidate snapshots.

Actual xHCI entry NoMedia lifecycle, with only the syscall boundary mocked."""
from __future__ import annotations
import hashlib,json,os,shutil,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT
SOURCE=BASE/'services/drivers/xhci_service.dg'
ADAPTER=ROOT/'services/usb/xhci_transport.dg'
SEAM=r'''
// Test-only exports appended to the otherwise unchanged production entry.
// Hardware startup is outside this fixture; the real async DMA native covers it.
export("entry_nomedia_setup") unsafe fn test_nomedia_setup(boot:*const sys.Boot)u64 {unsafe {
    BOOT=boot;STATE.setup.epoch=7;TRANSPORT.held=1;TRANSPORT.ready=1;TRANSPORT.fault=0;
    PROXY=block_proxy.EMPTY;ATTEMPTED=2;HID_POSTED=2;
    var i:usize=0;while i<2 {let d=&ENUMERATIONS[i][0] as *enumerator.State;
        (*d).ready=1;(*d).held=1;(*d).slot=i as u64+1;
        (*d).configuration.bindings[0].kind=descriptor.KEYBOARD;
        if i==1 {(*d).configuration.bindings[0].kind=descriptor.MOUSE;}
        (*d).input.held=1;(*d).input.ready=1;(*d).input.pending=1;(*d).input.generation=1;i+=1;
    }
    match start_proxy() {ok=>{return 0;},err(e)=>{return e;},}
}}
export("entry_nomedia_serve") unsafe fn test_nomedia_serve()u64 {unsafe {
    match serve_block() {ok=>{return 0;},err(e)=>{return e;},}
}}
export("entry_hid_preserved") unsafe fn test_hid_preserved()u64 {unsafe {
    if ATTEMPTED!=2||HID_POSTED!=2||PROXY.ready!=0||PROXY.storage!=null||TRANSPORT.ready!=1||TRANSPORT.fault!=0 {return 0;}
    var i:usize=0;while i<2 {let d=&ENUMERATIONS[i][0] as *enumerator.State;
        let b=&BOT_STORAGE[i][0] as *bot.State;
        if (*d).ready!=1||(*d).held!=1||(*d).slot!=i as u64+1||(*d).input.held!=1||(*d).input.ready!=1
            ||(*d).input.pending!=1||(*d).input.generation!=1||(*b).held!=0 {return 0;}
        if i==0&&(*d).configuration.bindings[0].kind!=descriptor.KEYBOARD {return 0;}
        if i==1&&(*d).configuration.bindings[0].kind!=descriptor.MOUSE {return 0;}i+=1;
    }return 1;
}}
'''
class XhciNoMediaTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.out=ROOT/'build/test/p8-xhci-nomedia'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
  cls.inputs=[SOURCE,ADAPTER,BASE/'services/usb/block_proxy.dg',BASE/'services/lib/usb_hid_abi.dg',ROOT/'tests/xhci_nomedia_probe.c',Path(__file__)]
  cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
 @classmethod
 def tearDownClass(cls):
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
  if after!=cls.before:raise AssertionError('entry/source changed during verification')
 def command(self,args,d,name):
  r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(name+'.json')).write_text(json.dumps(dict(command=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
 def native(self,mutation=None):
  for mode in ('debug','release'):
   d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir();source=d/'services';shutil.copytree(ROOT/'services',source)
   shutil.copyfile(ADAPTER,source/'usb/xhci_transport.dg')
   for extra in ('usb/block_proxy.dg','lib/usb_hid_abi.dg'):shutil.copyfile(BASE/'services'/extra,source/extra)
   s=SOURCE.read_text()
   if mutation:
    old,new={
     'old-start-failure':('let logged=sys.log("DONGOS_XHCI_BLOCK_NO_MEDIA\\r\\n");return;','return error.Setup;'),
     'skip-receive':('var ticket:u64=0;let received=','if PROXY.ready!=1 {return;}var ticket:u64=0;let received='),
     'peer':('if peer!=3||','if false||'),
     'epoch':('(epochs>>32)!=STATE.setup.epoch||','false||'),
     'missing-backend':('}else if PROXY.ready!=1 {','}else if false {'),
    }[mutation];self.assertEqual(1,s.count(old));s=s.replace(old,new)
   entry=source/'drivers/xhci_service.dg';entry.write_text(s+SEAM)
   c=compile_file(entry,roots=[source,ROOT/'lang/std'],mode=mode);asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o';nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
   r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
   exe=d/('probe.exe' if os.name=='nt' else 'probe');r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-strict-aliasing',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),ROOT/'tests/xhci_nomedia_probe.c',obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
   scenarios=('hid-only','peer','epochs','idle') if not mutation else ({'old-start-failure':'hid-only','skip-receive':'hid-only','peer':'peer','epoch':'epochs','missing-backend':'hid-only'}[mutation],)
   for scenario in scenarios:
    r=self.command([exe,scenario],d,scenario)
    if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('entry NoMedia native failed line',r.stderr)
    else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('entry NoMedia native checks passed',r.stdout)
 def test_actual_entry_hid_only_and_authenticated_nomedia(self):self.native()
 def test_real_bad_entry_sources_are_rejected(self):
  for mutation in ('old-start-failure','skip-receive','peer','epoch','missing-backend'):self.native(mutation)
