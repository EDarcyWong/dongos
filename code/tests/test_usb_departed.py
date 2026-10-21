"""Current-source regression, not a replay of unavailable candidate snapshots.

Exact retirement/query source, real Catalog and capabilities; no hardware."""
from __future__ import annotations
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_service_ipc_cancellation import block
from tests.test_service_gui_wiring import copy_graph
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'kernel/user/services.dg'
def retirement_boundaries():
 # Only observation is modeled. The real catalog termination remains intact.
 return {
  # These USB query fixtures have no DMA context. Its observation is tested by P5.
  'usb_departed_dma': '''module usb_departed_dma;
pub fn generation(id:usize)u64{return 1;}
pub unsafe fn dma_stop(slot:usize,configuration:u64,owner:u64,incarnation:u64,root:u64,generation:u64,smp:u64,code:u64)void{return;}
''',
  'usb_departed_smp': 'module usb_departed_smp;pub error Unmodeled=0x09000002;pub unsafe fn retire(id:usize)!void{return error.Unmodeled;}',
  'usb_departed_trace': '''module usb_departed_trace;import boot.trace as trace;
pub var COUNT:u64=0;pub var SUBJECT:u64=0;pub var GENERATION:u64=0;pub var BAD:bool=false;
pub unsafe fn event(kind:u64,cfg:u64,generation:u64,detail:u64)void{unsafe{
 if kind!=trace.SERVICE_STOP||cfg>=32||generation==0||detail!=0{BAD=true;return;}
 COUNT+=1;SUBJECT=cfg;GENERATION=generation;
}return;}
''',
 }

class UsbDepartedTests(unittest.TestCase):
 def test_real_retirement_query_authority_and_mutants(self):
  paths=[SOURCE,ROOT/'kernel/boot/trace.dg',ROOT/'kernel/user/processes.dg',ROOT/'kernel/ipc/handles.dg',ROOT/'kernel/user/abi.dg',ROOT/'services/lib/process_abi.dg',ROOT/'tests/usb_departed_probe.dg.in',ROOT/'tests/usb_departed_probe.c',Path(__file__)]
  before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};source=SOURCE.read_text()
  fragments='\n'.join(block(source,'unsafe fn '+name+'(') for name in ('managed','authority','endpoint','retire_one'))
  fragments+='\nunsafe fn perform(frame:*abi.Frame)!usize{unsafe{let code=(*frame).rax;'+block(source,'if code==0x2e{')+'}return error.InvalidCall;}\n'
  fixture=(ROOT/'tests/usb_departed_probe.dg.in').read_text().replace('// EXACT_PRODUCTION_FUNCTIONS',fragments)
  windows='''module usb_departed_windows;pub var EPOCH:u64=0;pub error Bad=0x09000001;
unsafe extern "sysv64" fn ud_window_boundary(kind:u64,id:u64,inc:u64,logical:u64)u64;
pub unsafe fn compositor_gone(epoch:u64)!void{unsafe{if ud_window_boundary(2,epoch,0,0)!=0{return error.Bad;}}return;}
pub unsafe fn owner_gone(key:u64)!void{unsafe{if ud_window_boundary(3,key,0,0)!=0{return error.Bad;}}return;}
'''
  variants={
   'no-record':('USB_DEPARTED=incarnation;','USB_DEPARTED=0;'),
   'untagged-departure':('value=(0x5548_4450<<32)|USB_DEPARTED;','value=USB_DEPARTED;'),
   'invalid-departure-incarnation':('if USB_DEPARTED>0x0fff_ffff{return error.Protocol;}',''),
   'no-current':('CURRENT!=4||','false||'),
   'no-config':('procs.current(CATALOG,4)!=4','false'),
   'no-managed':('!managed(4)||','false||'),
   'early-clear':('if !GRAPHICS||CATALOG==null','USB_DEPARTED=0;if !GRAPHICS||CATALOG==null'),
   'no-coalesce':('incarnation>USB_DEPARTED','incarnation>0'),
   'premature-record':('let terminated=procs.terminate(CATALOG,id,state,status);',
     'if id==13&&cfg==13&&incarnation>USB_DEPARTED{USB_DEPARTED=incarnation;}\n    let terminated=procs.terminate(CATALOG,id,state,status);'),
  }
  out=ROOT/'build/test/p8-usb-departed'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);evidence=[]
  nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
  def command(args,d,name):
   r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(name+'.json')).write_text(json.dumps(dict(command=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
  for mode in ('debug','release'):
   for variant in ('normal',*variants):
    d=out/(mode+'-'+variant);d.mkdir();text=fixture
    if variant!='normal':
     if variant=='premature-record':
      record='    if id==13&&cfg==13&&incarnation>USB_DEPARTED{USB_DEPARTED=incarnation;}\n'
      self.assertEqual(1,text.count(record));text=text.replace(record,'',1)
     old,new=variants[variant];self.assertEqual(1,text.count(old));text=text.replace(old,new,1)
    copy_graph(d/'source',('usb_departed_fixture',),{**retirement_boundaries(),'usb_departed_fixture':text,'usb_departed_windows':windows})
    c=compile_file(d/'source/usb_departed_fixture.dg',roots=[d/'source'],mode=mode);asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o'
    r=command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
    exe=d/('probe.exe' if os.name=='nt' else 'probe');r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-strict-aliasing',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),ROOT/'tests/usb_departed_probe.c',obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
    scenarios=('retire','guards','coalesce','identity','preconditions','failed-retire','range') if variant=='normal' else ({'no-record':'retire','untagged-departure':'retire','invalid-departure-incarnation':'range','no-current':'guards','no-config':'guards','no-managed':'guards','early-clear':'guards','no-coalesce':'coalesce','premature-record':'failed-retire'}[variant],)
    for scenario in scenarios:
     r=command([exe,scenario],d,scenario);self.assertEqual(0 if variant=='normal' else 1,r.returncode,r.stdout+r.stderr)
     self.assertIn('USB departed native checks passed' if variant=='normal' else 'USB departed native failed line',r.stdout if variant=='normal' else r.stderr)
     evidence.append(dict(mode=mode,variant=variant,scenario=scenario,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr))
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};self.assertEqual(before,after)
  (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_sha256=after,sources_unchanged=True,exact_retire_and_query_fragments=True,real_catalog_and_capability_table=True,windows_revoke_boundaries_mocked=True,actual_guest_boots=0,evidence=evidence),indent=2)+'\n');print('USB_DEPARTED_EVIDENCE',out)
