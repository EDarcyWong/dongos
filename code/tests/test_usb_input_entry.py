"""Current-source regression, not a replay of unavailable candidate snapshots.

Actual current input main plus nonblocking ticket-authenticated HID pump."""
import hashlib,json,os,shutil,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_input import command
from tests.test_fat32 import stack_bound
ROOT=Path(__file__).resolve().parents[1]
SOURCE_ROOT=ROOT/'services'
SUFFIX='''
export("input_errors") fn probe_errors()u64{unsafe{return INPUT_ERRORS;}}
export("input_interrupts") fn probe_interrupts()u64{unsafe{return INTERRUPTS as u64;}}
export("input_console_pop") fn probe_pop(q:*console.Queue,out:*u8,present:*u64)u64{unsafe{match console.pop(q,out){ok(value)=>{*present=value as u64;return 0;},err(e)=>{return e;},}}}
export("usb_test_pump") fn probe_pump()u64{unsafe{
 match usb_pump(sys.boot()){ok=>{},err(e)=>{return e;},}
 match flush(0x54000000 as u64 as *events.Queue,0x54100000 as u64 as *console.Queue,true){ok(present)=>{return 0;},err(e)=>{return e;},}
}}
export("usb_test_ps2") fn probe_ps2(byte:u64)u64{unsafe{
 match keyboard(0x54000000 as u64 as *events.Queue,0x54100000 as u64 as *console.Queue,true,byte as u8){ok=>{},err(e)=>{return e;},}
 match collect(&KEY_EVENTS){ok(present)=>{},err(e)=>{return e;},}
 match flush(0x54000000 as u64 as *events.Queue,0x54100000 as u64 as *console.Queue,true){ok(present)=>{return 0;},err(e)=>{return e;},}
}}
export("usb_test_epoch") fn probe_epoch()u64{unsafe{return USB_RPC.self_epoch;}}
export("usb_test_last") fn probe_last(source:usize)u64{unsafe{return USB_RPC.sequence[source-1];}}
export("usb_test_departed") fn probe_departed()u64{unsafe{
 match usb_departures(sys.boot()){ok=>{},err(e)=>{return e;},}
 match flush(0x54000000 as u64 as *events.Queue,0x54100000 as u64 as *console.Queue,true){ok(present)=>{return 0;},err(e)=>{return e;},}
}}
'''
class UsbInputEntryTests(unittest.TestCase):
 def test_real_main_irq_routing_and_accepted_rpc(self):
  paths=list(SOURCE_ROOT.rglob('*.dg'))+[ROOT/'tests/input_service_probe.c',ROOT/'tests/usb_input_entry_probe.c',Path(__file__)]
  before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};out=ROOT/'build/test/usb-input-entry'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);results=[]
  variants=[('normal',None,None),('ignores-kernel-peer','let peer=sys.peer((*boot).endpoint,USB_TICKET);','let ignored=sys.peer((*boot).endpoint,USB_TICKET);let peer:u64=14;'),('ignores-input-incarnation','let session=sys.svc_call(0x2a,(*boot).endpoint,USB_TICKET,0,0,0,0);','let observed=sys.svc_call(0x2a,(*boot).endpoint,USB_TICKET,0,0,0,0);let session=(USB_RPC.self_epoch<<32)|(observed&0xffff_ffff);')]
  for name,old,new in variants:
   for mode in ('debug','release'):
    d=out/(name+'-'+mode);stage=d/'source';shutil.copytree(ROOT/'services',stage,ignore=shutil.ignore_patterns('*.asm','*.ld'))
    p=stage/'drivers/input_service.dg';source=p.read_text(encoding='utf-8')
    if old:self.assertEqual(1,source.count(old));source=source.replace(old,new,1)
    p.write_text(source+SUFFIX,encoding='utf-8');compiled=compile_file(p,roots=[stage],mode=mode);bound=stack_bound(compiled.assembly);self.assertLessEqual(bound,12288);asm=d/'probe.asm';asm.write_text(compiled.assembly,encoding='utf-8')
    nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
    for fmt in ('elf64','win64'):command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',d/(fmt+'.o'),asm],d,'assemble-'+fmt)
    exe=d/('probe.exe' if os.name=='nt' else 'probe');command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',*(['-mno-sse'] if os.name=='nt' else ['-no-pie','-D_DEFAULT_SOURCE']),ROOT/'tests/usb_input_entry_probe.c',d/('win64.o' if os.name=='nt' else 'elf64.o'),'-o',exe],d,'link')
    result=command([exe],d,'native',success=False);self.assertEqual(0 if old is None else 1,result.returncode,result.stdout+result.stderr);self.assertIn('USB_INPUT_ENTRY_NATIVE_PASS' if old is None else 'input service check failed',result.stdout+result.stderr);results.append(dict(variant=name,mode=mode,stack=bound,stdout=result.stdout,stderr=result.stderr))
    if old is None:
     for scenario in range(1,6):
      result=command([exe,str(scenario)],d,'legacy-'+str(scenario),success=False);self.assertEqual(0,result.returncode,result.stdout+result.stderr);self.assertIn('scenario='+str(scenario)+' passed',result.stdout);results.append(dict(variant='legacy-'+str(scenario),mode=mode,stack=bound,stdout=result.stdout,stderr=result.stderr))
  self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths});(out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_unchanged=True,source_sha256=before,actual_input_main_and_pump=True,hardware_io=False,results=results),indent=2)+'\n',encoding='utf-8');print('USB_INPUT_ENTRY_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
