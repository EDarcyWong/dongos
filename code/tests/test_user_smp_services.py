"""Actual services callbacks and dormant LARGE wiring; synthetic owned RAM only."""
import hashlib,json,os,re,subprocess,sys,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool
from tests.test_service_ipc_cancellation import block
from tests.test_service_gui_wiring import copy_graph
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT
def source_hashes():
 """Re-enumerate the complete source inputs, including copy_graph's search graph."""
 files={Path(__file__),ROOT/'lang/tests/test_dongc.py',ROOT/'tests/test_service_gui_wiring.py',
        ROOT/'tests/test_service_ipc_cancellation.py',ROOT/'tests/user_current_entry_probe.dg',
        ROOT/'tests/user_current_entry_probe.c'}
 for name in ('kernel','include','services','lang/dongc','lang/std','lang/examples'):
  files.update(p for p in (ROOT/name).rglob('*') if p.is_file() and p.suffix in ('.dg','.asm','.inc','.py'))
 return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None for p in sorted(files)}

PREFIX='''
import user.abi as abi;
import boot.trace as trace;import boot.trace_runtime as boot_trace;
import user.memory as memory;
import user.processes as procs;
import lib.process_abi as proc;
import user.window_broker as windows;
import user.device_host as device_host;
import sched.user_bridge as smp_bridge;
import sched.user_domain as smp_domain;
import sched.multicore as smp_queue;
import boot.service_memory as resources;
import mm.runtime_large as runtime_large;
pub error Protocol=0x050b_0002;
const ACTIVE:usize=16;const NONE:usize=16;
var CURRENT:usize=0;var SMP_ENABLED:bool=false;var SMP_TEST_SLOTS:u64=0;
var CATALOG:*procs.Catalog=null;
unsafe extern "sysv64" fn smp_service_catalog_storage()u64;
struct State{waiting:u64,started:u64}
var STATES:[16]State=[State{waiting:0,started:0};16];
align(64) struct XState{bytes:[1024]u8}
var XSTATES:[16]XState=[XState{bytes:[0;1024]};16];
struct Info{current:u64,syscalls:u64,errors:u64,last_error:u64,frames:u64,process_count:u64}
var INFO:Info=Info{current:0,syscalls:0,errors:0,last_error:0,frames:0,process_count:0};
var USER_FAULTS:u64=0;var USER_IRQS:u64=0;var USB_DEPARTED:u64=0;var GUI_DEPARTED:[16]u64=[0;16];var LAUNCH_FAILED:bool=false;
unsafe extern "sysv64" fn user_validate_frame(frame:*abi.Frame)u64;
unsafe extern "sysv64" fn smp_service_fixture_event(phase:u64,slot:u64,value:u64)u64;
unsafe fn wake_waiters()!void{return;}
unsafe fn wake_irqs()!void{return;}
// This fixture has no P5 DMA context. The dedicated P5 oracle covers its hooks.
unsafe fn fixture_skip_retire(id:usize)!void{return;}
unsafe fn revoke_loaded(id:usize,inc:u64)!void{unsafe{let result=smp_service_fixture_event(2,id as u64,inc);if result!=0{return error.Protocol;}(*(memory.processes()+id)).ready=0;}return;}
unsafe fn retire(id:usize,state:u64,status:u64)!void{unsafe{try retire_one(id,state,status);}return;}
unsafe fn perform(frame:*abi.Frame)!usize{unsafe{
 let observed=smp_service_fixture_event(1,CURRENT as u64,frame as u64);if observed!=0{return error.Protocol;}
 if (*frame).rax==0x99{return error.Protocol;}
 if (*frame).rax==0xff{try retire_one(CURRENT,proc.EXITED,73);return CURRENT;}
 (*frame).rax=0x7788;return CURRENT;
}}
'''
TAIL='''
unsafe fn catalog_start(cfg:usize,slot:usize)!void{unsafe{
 var snapshot=proc.EMPTY_SNAPSHOT;try procs.start(CATALOG,cfg,slot,0,&snapshot);try procs.mark_ready(CATALOG,slot,1);
}return;}
export("us_setup") fn setup(configuration:u64)u64{unsafe{
 CATALOG=smp_service_catalog_storage() as *procs.Catalog;match procs.initialize(CATALOG,1000000){ok=>{},err(e)=>{return e;},}
 match catalog_start(5,5){ok=>{},err(e)=>{return e;},}match catalog_start(6,6){ok=>{},err(e)=>{return e;},}
 match catalog_start(2,2){ok=>{},err(e)=>{return e;},}match catalog_start(1,1){ok=>{},err(e)=>{return e;},}
 match catalog_start(4,4){ok=>{},err(e)=>{return e;},}match catalog_start(3,3){ok=>{},err(e)=>{return e;},}
 match catalog_start(configuration as usize,7){ok=>{},err(e)=>{return e;},}
 let p=memory.processes()+7;(*p).ready=1;(*p).root=0x207000;(*p).frame=abi.EMPTY;(*p).frame.rip=0x400000;(*p).frame.rsp=0x70000000;(*p).frame.cr3=(*p).root;
 match enable_smp(){ok=>{return 0;},err(e)=>{return e;},}
}}
export("us_project") fn project()u64{return smp_project();}
export("us_select") fn select()u64{unsafe{
 var out:u64=0;match ud.select(D,0,&out){ok(found)=>{if !found{return 1;}},err(e)=>{return e;},}
 match ud.selected_kernel(D,0){ok=>{return 0;},err(e)=>{return e;},}
}}
export("us_op") fn op(value:u64)u64{unsafe{let f=&(*(memory.processes()+7)).frame;(*f).rax=value;return smp_service(7,257,f as u64);}}
export("us_fault") fn fault()u64{unsafe{return smp_service(7,7,(&(*(memory.processes()+7)).frame) as u64);}}
export("us_guard") fn guard(which:u64)u64{unsafe{
 let f=&(*(memory.processes()+7)).frame;
 if which==1{(*CATALOG).incarnation[7]+=1;let result=smp_service(7,257,f as u64);(*CATALOG).incarnation[7]-=1;return result;}
 if which==2{return smp_service(7,257,(&(*(memory.processes()+8)).frame) as u64);}
 if which==3{(*D).owner=1;let result=smp_service(7,257,f as u64);(*D).owner=0;return result;}return 1;
}}
export("us_irq") fn irq(vector:u64)u64{return smp_interrupt(vector);}
export("us_large_size") fn large_size()u64{return sizeof(LargeStorage) as u64;}
export("us_large_guard") fn large_guard(which:u64)u64{unsafe{
 if RUNTIME_LARGE==null||LARGE_STORAGE==null{return 1;}
 if which==1{LARGE_REQUESTED=true;}else if which==2{(*RUNTIME_LARGE).ready=1;}
 else if which==3{(*RUNTIME_LARGE).report.attempted=1;}else{return 1;}
 let result=large_try();LARGE_REQUESTED=false;(*RUNTIME_LARGE).ready=0;(*RUNTIME_LARGE).report.attempted=0;
 match result{ok=>{return 0;},err(e)=>{return e;},}
}}
export("us_large_registered") fn large_registered()u64{unsafe{
 match smp_domain.register_poll(D,large_poll){ok=>{return 0;},err(e)=>{return e;},}
}}
export("us_large_state") fn large_state(which:u64)u64{unsafe{
 if which==0{return LARGE_STORAGE as u64;}if which==1{return RUNTIME_LARGE as u64;}
 if which==2{return LARGE_TRIES;}if which==3{return LARGE_REQUESTED as u64;}
 if RUNTIME_LARGE==null{return 0xffff_ffff_ffff_ffff;}
 if which==4{return (*RUNTIME_LARGE).ready;}if which==5{return (*RUNTIME_LARGE).report.attempted;}
 if which==6{return (*RUNTIME_LARGE).report.complete;}return 0xffff_ffff_ffff_ffff;
}}
export("us_get") fn get(which:u64)u64{unsafe{
 if which==0{return CURRENT as u64;}if which==1{return (*(memory.processes()+7)).frame.rax;}if which==2{return INFO.syscalls;}
 if which==3{return USER_FAULTS;}if which==4{return USER_IRQS;}if which==5{return (*(memory.processes()+7)).ready;}
 if which==6{return (*(*D).engine).threads[7].affinity;}if which==7{return procs.current(CATALOG,7);}if which==8{return SMP_TEST_SLOTS;}return 0;
}}
'''
MEMORY='''module user.memory;import user.abi as abi;import mm.runtime_roots as runtime_roots;
pub struct Process{pub frame:abi.Frame,pub root:u64,pub ready:u64}
var P:[16]Process=[Process{frame:abi.EMPTY,root:0,ready:0};16];
pub var OBJECT_FAILED:bool=false;pub var STAGE_FAILED:bool=false;pub var UNSHARE_FAILED:bool=false;pub var RESOURCE_FAILED:bool=false;
pub fn processes()*Process{unsafe{return &P[0];}}pub fn frame_count()usize{return 17;}
pub fn generation(id:usize)u64{return 1;}
'''
# The actual production project is tested with LARGE deliberately unarmed.
# Neither a subset Context nor a successful transaction stand-in is permitted.
DORMANT='''
pub var RUNTIME_LARGE:*runtime_large.Context=null;
var LARGE_STORAGE:*LargeStorage=null;var LARGE_REQUESTED:bool=false;var LARGE_TRIES:u64=0;
unsafe fn large_try()!void{unsafe{
 LARGE_TRIES+=1;
 if RUNTIME_LARGE==null||LARGE_STORAGE==null||RUNTIME_LARGE!=&(*LARGE_STORAGE).context
  ||LARGE_REQUESTED||(*RUNTIME_LARGE).ready!=0||(*RUNTIME_LARGE).report.attempted!=0
  ||(*RUNTIME_LARGE).report.complete!=0{return error.Protocol;}
}return;}
'''
RESOURCES='''module boot.service_memory;
pub error InvalidState=0x0507_0001;
unsafe extern "sysv64" fn smp_service_fixture_allocate(pages:usize,alignment:usize,out:*Block)u64;
pub unsafe fn allocate(pages:usize,alignment:usize,out:*Block)!void{unsafe{
 if smp_service_fixture_allocate(pages,alignment,out)!=0{return error.InvalidState;}
}return;}
'''
WINDOWS='''module user.window_broker;pub var FAILED:bool=false;pub var EPOCH:u64=0;
pub unsafe fn owner_gone(owner:u64)!void{return;}pub unsafe fn compositor_gone(epoch:u64)!void{return;}
'''
DEVICE='''module user.device_host;pub var PCI_FAILED:bool=false;pub error Invalid=0x060b_0040;
unsafe extern "sysv64" fn smp_service_fixture_irq(vector:u64)u64;
pub unsafe fn interrupt(vector:u64)!u64{unsafe{let x=smp_service_fixture_irq(vector);}return 0;}
pub unsafe fn dma_stop(slot:usize,configuration:u64,owner:u64,incarnation:u64,root:u64,generation:u64,smp:u64,code:u64)void{return;}
'''
CMAIN=r'''
extern U ABI us_setup(U),us_project(void),us_select(void),us_op(U),us_fault(void),us_guard(U),us_irq(U),us_get(U);
extern U ABI us_large_size(void),us_large_guard(U),us_large_registered(void),us_large_state(U);
static U performed,withdrawn,interrupts;
typedef struct{U physical,virtual_address,pages;} ServiceBlock;
static unsigned char*large_owned;static U large_pages,large_allocations;
U ABI smp_service_fixture_allocate(U pages,U alignment,ServiceBlock*out){
 C(cpu==0&&d&&d->owner==0&&d->lock==1&&out);
 C(!large_allocations&&pages&&(pages<=128)&&alignment==1&&pages==(us_large_size()+4095)/4096);
 large_owned=arena((size_t)(pages+2)*4096);unsigned char*body=large_owned+4096;
 C(!((uintptr_t)body&4095));memset(body,0,(size_t)pages*4096);
 for(size_t i=0;i<(size_t)pages*4096;i++)C(body[i]==0);
 large_pages=pages;large_allocations=1;
 *out=(ServiceBlock){0x70000000,(U)(uintptr_t)body,pages};return 0;
}
static void large_boundary(void){
 C(large_allocations==1&&large_pages==(us_large_size()+4095)/4096);
 C(us_large_state(0)==(U)(uintptr_t)(large_owned+4096)&&us_large_state(1)==us_large_state(0));
 for(unsigned i=3;i<=6;i++)C(!us_large_state(i));
 for(size_t i=0;i<4096;i++)C(large_owned[i]==0xa5&&large_owned[(size_t)(large_pages+1)*4096+i]==0xa5);
}
static unsigned char catalog_storage[32768] __attribute__((aligned(64)));
U ABI smp_service_catalog_storage(void){return (U)(uintptr_t)catalog_storage;}
U ABI user_validate_frame(Frame*f){return (f->w[16]&0x202)==0x202&&f->w[18]&&f->w[15]>=0x10000&&f->w[17]>=0x10000;}
U ABI smp_service_fixture_event(U phase,U slot,U value){C(cpu==0&&d->lock==1&&d->owner==0);
 if(phase==1){C(slot==7&&us_get(0)==7&&value==d->processes[7].frame);performed++;}
 else if(phase==2){C(slot==7&&value==1&&!d->processes[7].token&&!d->cpus[0].token&&!d->barrier);for(unsigned i=0;i<3;i++)C(d->cpus[i].ack==d->completed&&d->completed>0);withdrawn++;}
 else if(phase==3){C(slot==0&&(value==0x51||value==0x5c||value==0x60)&&us_get(0)==16);interrupts++;}else{C(0);}
 return 0;
}
U ABI smp_service_fixture_irq(U vector){return smp_service_fixture_event(3,0,vector);}
int main(int argc,char**argv){C(argc==2);U gui=!strcmp(argv[1],"gui");setup();cpu=0;C(!ue_lock(0));C(!us_setup(gui?14:9)&&us_get(0)==16);large_boundary();
 C(us_large_registered()==0x06090002);C(!ue_poll(0)&&!d->failed);
 C(us_large_guard(1)==0x050b0002&&us_large_guard(2)==0x050b0002&&us_large_guard(3)==0x050b0002);large_boundary();C(us_large_state(2)==3);
 C(!us_project()&&!us_project()&&us_get(6)==7&&d->processes[7].token&&us_get(8)==(gui?0:128));C(us_large_state(2)==5);C(!us_select());
 U saved=us_get(1);C(us_guard(1)==0x060b0011&&us_get(1)==saved);C(us_guard(2)==0x060b0011&&us_get(1)==saved);C(us_guard(3)==0x060b0011&&us_get(1)==saved);
 C(!us_op(1)&&us_get(0)==16&&us_get(1)==0x7788&&performed==1&&us_get(2)==1);C(!us_op(0x99)&&us_get(0)==16&&us_get(1)==0x050b0002&&performed==2&&us_get(2)==2);
 C(!us_irq(0x51)&&!us_irq(0x5c)&&!us_irq(0x60)&&interrupts==3&&us_get(4)==3&&us_get(0)==16);
 if(!strcmp(argv[1],"exit")||gui){C(!us_op(0xff)&&us_get(0)==16&&performed==3&&withdrawn==1&&!us_get(5));}
 else{C(!strcmp(argv[1],"fault"));C(!us_fault()&&us_get(0)==16&&us_get(3)==1&&withdrawn==1&&!us_get(5));}
 C(us_get(7)==UINT64_MAX&&!d->processes[7].token&&!us_get(8)&&!ue_audit());large_boundary();C(!ue_unlock(0));
 printf("actual services SMP callback checks=%u scenario=%s real-Catalog scope generation frame-authority retire-before-withdraw IRQ-BSP dormant-LARGE owned-zero-RAM pages=%u storage-bytes=%u runtime_large_executed=false actual_qemu_executed=false\n",(unsigned)checks,argv[1],(unsigned)large_pages,(unsigned)us_large_size());return 0;}
'''
MUTATION_POLICY="\nU ABI user_bridge_service_policy(U slot,U event,U frame){(void)slot;(void)event;(void)frame;return 0;}\n"
class Tests(unittest.TestCase):
 def test_actual_service_callbacks_and_retirement_before_withdrawal(self):
  controls={
   'retire-without-remote-detach':('let stopped=smp_bridge.retire(id);','let stopped=fixture_skip_retire(id);'),
   'missing-test-role-mask':('if cfg>=7&&cfg<=11{SMP_TEST_SLOTS|=1<<slot as u64;}',''),
   'stale-test-role-mask':('SMP_TEST_SLOTS&=~(1<<id as u64);',''),
   'test-mask-includes-normal-GUI':('if cfg>=7&&cfg<=11{SMP_TEST_SLOTS|=1<<slot as u64;}','if cfg>=7{SMP_TEST_SLOTS|=1<<slot as u64;}'),
   'AHCI-MSI-rejected':('(vector!=0x51&&vector!=0x5c&&vector!=0x60)','(vector!=0x51&&vector!=0x5c)'),
   'CURRENT-leaks-after-service':('CURRENT=NONE;if failure!=0','if failure!=0'),
   'stale-incarnation-authority':('||(*p).incarnation!=(*CATALOG).incarnation[slot]',''),
   'foreign-Frame-pointer':('||pointer!=(&(*process(slot)).frame) as u64',''),
   'AP-owner-runs-perform':('if (*d).owner!=0||(*d).lock!=1||(*cpu).mode','if (*d).lock!=1||(*cpu).mode'),
   'duplicate-admission':('if (*p).token==0{\n                let cfg','if true{\n                let cfg'),
  }
  out=ROOT/'build/test/p6-cpl3-service-native'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
  before=source_hashes();tool_paths={'python':str(Path(sys.executable).resolve()),'nasm':None,'cc':None}
  evidence=[];commands=[];compilations=[];passed=False;failure=None;active={};tools_before={}
  def tool_hashes():
   return {role:dict(path=path,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest() if path and Path(path).is_file() else None) for role,path in tool_paths.items()}
  def run(args,d,label):
   args=list(map(str,args));record=dict(argv=args,cwd=str(ROOT),label=label,directory=d.relative_to(out).as_posix())
   raw=json.dumps(dict(argv=args,cwd=str(ROOT)),sort_keys=True,indent=2).encode()+b'\n'
   (d/(label+'.command.json')).write_bytes(raw);record['command_sha256']=hashlib.sha256(raw).hexdigest()
   stdout=stderr=b''
   try:
    r=subprocess.run(args,cwd=ROOT,capture_output=True,timeout=60)
    stdout,stderr=r.stdout,r.stderr;record['returncode']=r.returncode
   except (subprocess.TimeoutExpired,OSError) as exc:
    stdout=getattr(exc,'stdout',None) or b'';stderr=getattr(exc,'stderr',None) or b''
    if isinstance(stdout,str):stdout=stdout.encode()
    if isinstance(stderr,str):stderr=stderr.encode()
    record['failure']=dict(type=type(exc).__name__,message=str(exc))
    raise
   finally:
    (d/(label+'.stdout')).write_bytes(stdout);(d/(label+'.stderr')).write_bytes(stderr)
    record.update(stdout_sha256=hashlib.sha256(stdout).hexdigest(),stderr_sha256=hashlib.sha256(stderr).hexdigest(),stdout=stdout.decode(errors='replace'),stderr=stderr.decode(errors='replace'))
    (d/(label+'.json')).write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');commands.append(record)
   r.stdout=stdout.decode(errors='replace');r.stderr=stderr.decode(errors='replace');return r
  try:
   for role,name,override in (('nasm','nasm','NASM'),('cc','gcc','CC')):
    found=tool(name,override);self.assertTrue(found,'required native tool unavailable: '+role);tool_paths[role]=str(Path(found).resolve())
   tools_before=tool_hashes();nasm,cc=tool_paths['nasm'],tool_paths['cc']
   # Same warning discovery policy as test_dongc, with every probe archived.
   help_result=run([nasm,'-h'],out,'nasm-help');self.assertEqual(0,help_result.returncode,help_result.stderr);help_text=help_result.stdout
   if re.search(r'(?m)^\s*-h\s+-\S+',help_text):
    help_result=run([nasm,'-h','-w'],out,'nasm-warning-help');self.assertEqual(0,help_result.returncode,help_result.stderr);help_text+='\n'+help_result.stdout
   flags=['-Wall','-Werror']+['-w-'+name for name in ('reloc-rel-dword','reloc-abs-qword') if re.search(r'(?m)^\s*'+re.escape(name)+r'\s',help_text)]
   text=(BASE/'kernel/user/services.dg').read_text(encoding='utf-8')
   needles=('unsafe fn process(', 'unsafe fn managed(', 'unsafe fn retire_one(', 'pub unsafe fn enable_smp(', 'unsafe fn large_poll(', 'export("dong_user_smp_project")', 'export("dong_user_smp_service")', 'export("dong_user_smp_interrupt")')
   for needle in (*needles,'struct LargeTicket{','align(64) struct LargeStorage{'):self.assertEqual(1,text.count(needle),needle)
   actual='\n'.join(block(text,n) for n in needles)
   declarations='\n'.join(block(text,n) for n in ('struct LargeTicket{','align(64) struct LargeStorage{'))
   snapshot=block((ROOT/'kernel/user/memory.dg').read_text(encoding='utf-8'),'pub struct RootSnapshot{')
   resource_block=block((ROOT/'kernel/boot/service_memory.dg').read_text(encoding='utf-8'),'pub struct Block ')
   entry=(ROOT/'tests/user_current_entry_probe.dg').read_text(encoding='utf-8')+PREFIX+declarations+DORMANT+actual+TAIL
   c=(ROOT/'tests/user_current_entry_probe.c').read_text(encoding='utf-8')
   for needle in ('U ABI dong_user_smp_service(', 'U ABI dong_user_smp_project('):self.assertEqual(1,c.count(needle));c=c.replace(block(c,needle),'')
   c=c[:c.index('int main(void)')]+CMAIN+MUTATION_POLICY
   for mode in ('debug','release'):
    for variant in ('normal',*controls):
     active=dict(mode=mode,variant=variant,phase='stage');d=out/(mode+'-'+variant);stage=d/'kernel';s=entry
     if variant!='normal':old,new=controls[variant];self.assertEqual(1,s.count(old),variant);s=s.replace(old,new)
     overrides={'user_current_entry_probe':s,'user.memory':MEMORY+snapshot,'boot.service_memory':RESOURCES+resource_block,
       'user.window_broker':WINDOWS,'user.device_host':DEVICE,'boot.trace_runtime':'module boot.trace_runtime;pub unsafe fn event(a:u64,b:u64,c:u64,d:u64)void{return;}'}
     copy_graph(stage,['user_current_entry_probe'],overrides)
     staged={p.relative_to(stage).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.rglob('*.dg'))}
     active['phase']='compile';invocation=dict(mode=mode,variant=variant,entry=str(stage/'user_current_entry_probe.dg'),roots=[str(stage)],staged_source_sha256=staged,executed=False)
     compilations.append(invocation);(d/'compile.json').write_text(json.dumps(invocation,indent=2)+'\n',encoding='utf-8')
     try:
      invocation['executed']=True;compiled=compile_file(stage/'user_current_entry_probe.dg',roots=[stage],mode=mode)
      invocation['passed']=True
     except BaseException as exc:
      invocation.update(passed=False,failure=dict(type=type(exc).__name__,message=str(exc)));raise
     finally:(d/'compile.json').write_text(json.dumps(invocation,indent=2)+'\n',encoding='utf-8')
     (d/'probe.asm').write_text(compiled.assembly,encoding='utf-8');(d/'probe.c').write_text(c,encoding='utf-8')
     (d/'layout.json').write_text(json.dumps(compiled.layout_manifest,indent=2)+'\n',encoding='utf-8')
     layouts={t['full_name']:t for t in compiled.layout_manifest['types']}
     storage=layouts['user_current_entry_probe.LargeStorage'];context=layouts['mm.runtime_large.Context']
     self.assertEqual(0,storage['fields'][0]['offset']);self.assertEqual(24,layouts['boot.service_memory.Block']['size'])
     self.assertGreater(storage['size'],context['size']);self.assertLessEqual(storage['size'],128*4096)
     objects=[];active['phase']='assemble'
     for name,path in [('dong',d/'probe.asm'),('entry',BASE/'kernel/sched/user_entry.asm'),('legacy',BASE/'kernel/sched/user_legacy.asm')]:
      obj=d/(name+'.o');r=run([nasm,'-f','win64'if os.name=='nt'else'elf64',*flags,'-I',str(BASE/'include')+os.sep,path,'-o',obj],d,'assemble-'+name);self.assertEqual(0,r.returncode,r.stdout+r.stderr);objects.append(obj)
     active['phase']='link';exe=d/('probe.exe'if os.name=='nt'else'probe')
     r=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',*([]if os.name=='nt'else['-no-pie']),d/'probe.c',*objects,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stdout+r.stderr)
     for scenario in ('exit','fault','gui')if variant=='normal'else(('gui',)if variant=='test-mask-includes-normal-GUI'else('exit',)):
      active.update(phase='native',scenario=scenario);r=run([exe,scenario],d,scenario)
      case=dict(mode=mode,variant=variant,scenario=scenario,returncode=r.returncode,
       executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),object_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in objects})
      evidence.append(case);self.assertEqual(0 if variant=='normal'else 1,r.returncode,r.stdout+r.stderr)
      if variant!='normal':self.assertIn('user CPL3 current-source oracle line',r.stderr);self.assertNotIn('actual services SMP callback checks=',r.stdout)
      else:self.assertIn('dormant-LARGE owned-zero-RAM',r.stdout);self.assertIn('runtime_large_executed=false actual_qemu_executed=false',r.stdout)
   self.assertEqual(26,len(evidence));self.assertEqual(6,sum(e['variant']=='normal' for e in evidence))
   self.assertEqual(before,source_hashes());self.assertEqual(tools_before,tool_hashes());passed=True
  except BaseException as exc:
   failure=dict(type=type(exc).__name__,message=str(exc),active=active);raise
  finally:
   after=source_hashes();tools_after=tool_hashes()
   artifacts={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p!=out/'validation-summary.json'}
   (out/'validation-summary.json').write_text(json.dumps(dict(passed=passed and before==after and tools_before==tools_after,failure=failure,
     contract='current-service-dormant-large-v2',current_source=True,historical_replay=False,actual_services_fragments=True,real_catalog_domain_queue=True,
     source_before=before,source_after=after,sources_unchanged=before==after,tools_before=tools_before,tools_after=tools_after,tools_unchanged=tools_before==tools_after,
     artifact_sha256=artifacts,commands=commands,compilations=compilations,evidence=evidence,skipped=[],normal_expected=6,mutant_expected=20,
     synthetic_RAM_boundary=True,memory_hardware_and_perform_boundary_mocked=True,large_context_type='mm.runtime_large.Context',actual_large_poll_source=True,
     actual_large_poll_registration=passed and sum(e['variant']=='normal' for e in evidence)==6,
     runtime_large_executed=False,actual_ap_cpl3_executed=False,actual_qemu_executed=False,os_build_executed=False),indent=2)+'\n',encoding='utf-8')
   print('USER_SMP_SERVICE_EVIDENCE',out)
  self.assertTrue(passed and before==after and tools_before==tools_after,'late source/tool changes must fail the unittest and its receipt')
if __name__=='__main__':unittest.main(verbosity=2)
