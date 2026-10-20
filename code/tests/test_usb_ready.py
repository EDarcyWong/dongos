"""Current-source regression, not a replay of unavailable candidate snapshots.

Exact current kernel readiness branch, actual Catalog/capabilities; no guest."""
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_service_ipc_cancellation import block
from tests.test_service_gui_wiring import copy_graph
from tests.test_usb_departed import retirement_boundaries
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'kernel/user/services.dg'
class UsbReadyTests(unittest.TestCase):
 def test_actual_query_checks_real_identity_ready_and_incarnation(self):
  paths=[SOURCE,ROOT/'kernel/boot/trace.dg',ROOT/'tests/test_usb_departed.py',ROOT/'kernel/user/processes.dg',ROOT/'kernel/ipc/handles.dg',ROOT/'tests/usb_departed_probe.dg.in',ROOT/'tests/usb_ready_probe.c',Path(__file__)]
  before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};source=SOURCE.read_text()
  fragments='\n'.join(block(source,'unsafe fn '+name+'(') for name in ('managed','authority','endpoint','retire_one'))
  fragments+='\nunsafe fn perform(frame:*abi.Frame)!usize{unsafe{let code=(*frame).rax;'+block(source,'if code==0x2f{')+'}return error.InvalidCall;}\n'
  fixture=(ROOT/'tests/usb_departed_probe.dg.in').read_text().replace('// EXACT_PRODUCTION_FUNCTIONS',fragments)
  fixture+='\nexport("ur_change") fn ready_change(kind:u64,value:u64)void{unsafe{if kind==0{PROCESSES[13].ready=value;}else if kind==1{MODEL.states[13].state=value;}else if kind==2{MODEL.incarnation[13]=value;}else if kind==3{MODEL.ready=value;}}}\n'
  windows='module usb_departed_windows;pub var EPOCH:u64=0;pub unsafe fn compositor_gone(epoch:u64)!void{return;}pub unsafe fn owner_gone(key:u64)!void{return;}'
  variants={
   'wrong-input-current':('CURRENT!=4||','false||'),
   'wrong-input-role':('procs.current(CATALOG,4)!=4','false'),
   'unmanaged-input':('!managed(4)||','false||'),
   'unmanaged-xhci':('if managed(13)&&','if true&&'),
   'wrong-xhci-role':('procs.current(CATALOG,13)==13','true'),
   'starting-as-ready':('(*CATALOG).states[13].state==proc.READY','true'),
   'ignores-last-unused':('||(*frame).r9!=0',''),
   'call-capability-accepted':('endpoint((*frame).rdi,handles.WAIT|handles.REPLY)','endpoint((*frame).rdi,handles.CALL)'),
   'fixed-incarnation':('value=(0x5548_5244<<32)|incarnation;','value=(0x5548_5244<<32)|1;'),
   'untagged-ready':('value=(0x5548_5244<<32)|incarnation;','value=incarnation;'),
   'accepts-invalid-incarnation':('incarnation==0||incarnation>0x0fff_ffff','false'),
  }
  out=ROOT/'build/test/usb-ready'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);evidence=[]
  nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
  def command(args,d,name):
   r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(name+'.json')).write_text(json.dumps(dict(command=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
  for mode in ('debug','release'):
   for variant in ('normal',*variants):
    d=out/(mode+'-'+variant);d.mkdir();text=fixture
    if variant!='normal':
     old,new=variants[variant];self.assertGreaterEqual(text.count(old),1);text=text.replace(old,new)
    copy_graph(d/'source',('usb_departed_fixture',),{**retirement_boundaries(),'usb_departed_fixture':text,'usb_departed_windows':windows})
    c=compile_file(d/'source/usb_departed_fixture.dg',roots=[d/'source'],mode=mode);asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o'
    r=command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
    exe=d/('probe.exe' if os.name=='nt' else 'probe');r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-strict-aliasing',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),ROOT/'tests/usb_ready_probe.c',obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
    scenarios=('ready','guards','driver','incarnation') if variant=='normal' else ({'wrong-input-current':'guards','wrong-input-role':'guards','unmanaged-input':'guards','unmanaged-xhci':'driver','wrong-xhci-role':'driver','starting-as-ready':'driver','ignores-last-unused':'guards','call-capability-accepted':'call-cap','fixed-incarnation':'incarnation','untagged-ready':'ready','accepts-invalid-incarnation':'incarnation'}[variant],)
    for scenario in scenarios:
     r=command([exe,scenario],d,scenario);self.assertEqual(0 if variant=='normal' else 1,r.returncode,r.stdout+r.stderr);self.assertIn('USB_READY_NATIVE_PASS' if variant=='normal' else 'USB_READY_ASSERT',r.stdout+r.stderr)
     evidence.append(dict(mode=mode,variant=variant,scenario=scenario,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr))
  self.assertEqual(before,{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
  (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_sha256=before,source_unchanged=True,actual_catalog_and_capabilities=True,exact_query_body=True,actual_guest_boots=0,evidence=evidence),indent=2)+'\n');print('USB_READY_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
