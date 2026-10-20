"""Actual isolated services callbacks, real catalog/domain/queue, RAM boundary mock."""
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
from tests.test_service_ipc_cancellation import block
from tests.test_service_gui_wiring import copy_graph
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT
def current_files():
 """Tracked graph identity, not unavailable candidate provenance."""
 names=subprocess.check_output(['git','ls-files','-z','kernel','include','services','lang/dongc','lang/std'],cwd=ROOT).decode().split('\0')
 return [ROOT/name for name in names if name and (ROOT/name).is_file()]

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
export("us_get") fn get(which:u64)u64{unsafe{
 if which==0{return CURRENT as u64;}if which==1{return (*(memory.processes()+7)).frame.rax;}if which==2{return INFO.syscalls;}
 if which==3{return USER_FAULTS;}if which==4{return USER_IRQS;}if which==5{return (*(memory.processes()+7)).ready;}
 if which==6{return (*(*D).engine).threads[7].affinity;}if which==7{return procs.current(CATALOG,7);}if which==8{return SMP_TEST_SLOTS;}return 0;
}}
'''
MEMORY='''module user.memory;import user.abi as abi;
pub struct Process{pub frame:abi.Frame,pub root:u64,pub ready:u64}
var P:[16]Process=[Process{frame:abi.EMPTY,root:0,ready:0};16];
pub var OBJECT_FAILED:bool=false;pub var STAGE_FAILED:bool=false;pub var UNSHARE_FAILED:bool=false;pub var RESOURCE_FAILED:bool=false;
pub fn processes()*Process{unsafe{return &P[0];}}pub fn frame_count()usize{return 17;}
'''
WINDOWS='''module user.window_broker;pub var FAILED:bool=false;pub var EPOCH:u64=0;
pub unsafe fn owner_gone(owner:u64)!void{return;}pub unsafe fn compositor_gone(epoch:u64)!void{return;}
'''
DEVICE='''module user.device_host;pub var PCI_FAILED:bool=false;pub error Invalid=0x060b_0040;
unsafe extern "sysv64" fn smp_service_fixture_irq(vector:u64)u64;
pub unsafe fn interrupt(vector:u64)!u64{unsafe{let x=smp_service_fixture_irq(vector);}return 0;}
'''
CMAIN=r'''
extern U ABI us_setup(U),us_project(void),us_select(void),us_op(U),us_fault(void),us_guard(U),us_irq(U),us_get(U);
static U performed,withdrawn,interrupts;
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
int main(int argc,char**argv){C(argc==2);U gui=!strcmp(argv[1],"gui");setup();cpu=0;C(!ue_lock(0));C(!us_setup(gui?14:9)&&us_get(0)==16);C(!us_project()&&!us_project()&&us_get(6)==7&&d->processes[7].token&&us_get(8)==(gui?0:128));C(!us_select());
 U saved=us_get(1);C(us_guard(1)==0x060b0011&&us_get(1)==saved);C(us_guard(2)==0x060b0011&&us_get(1)==saved);C(us_guard(3)==0x060b0011&&us_get(1)==saved);
 C(!us_op(1)&&us_get(0)==16&&us_get(1)==0x7788&&performed==1&&us_get(2)==1);C(!us_op(0x99)&&us_get(0)==16&&us_get(1)==0x050b0002&&performed==2&&us_get(2)==2);
 C(!us_irq(0x51)&&!us_irq(0x5c)&&!us_irq(0x60)&&interrupts==3&&us_get(4)==3&&us_get(0)==16);
 if(!strcmp(argv[1],"exit")||gui){C(!us_op(0xff)&&us_get(0)==16&&performed==3&&withdrawn==1&&!us_get(5));}
 else{C(!strcmp(argv[1],"fault"));C(!us_fault()&&us_get(0)==16&&us_get(3)==1&&withdrawn==1&&!us_get(5));}
 C(us_get(7)==UINT64_MAX&&!d->processes[7].token&&!us_get(8)&&!ue_audit());C(!ue_unlock(0));printf("actual services SMP callback checks=%u scenario=%s real-Catalog scope generation frame-authority retire-before-withdraw IRQ-BSP\n",(unsigned)checks,argv[1]);return 0;}
'''
MUTATION_POLICY="\nU ABI user_bridge_service_policy(U slot,U event,U frame){(void)slot;(void)event;(void)frame;return 0;}\n"
class Tests(unittest.TestCase):
 def test_actual_service_callbacks_and_retirement_before_withdrawal(self):
  source=BASE/'kernel/user/services.dg';text=source.read_text(encoding='utf-8')
  actual='\n'.join(block(text,n)for n in ('unsafe fn process(', 'unsafe fn managed(', 'unsafe fn retire_one(', 'pub unsafe fn enable_smp(', 'export("dong_user_smp_project")', 'export("dong_user_smp_service")', 'export("dong_user_smp_interrupt")'))
  entry=(ROOT/'tests/user_current_entry_probe.dg').read_text()+PREFIX+actual+TAIL
  c=(ROOT/'tests/user_current_entry_probe.c').read_text()
  for needle in ('U ABI dong_user_smp_service(', 'U ABI dong_user_smp_project('):c=c.replace(block(c,needle),'')
  c=c[:c.index('int main(void)')]+CMAIN+MUTATION_POLICY
  controls={
   'retire-without-remote-detach':('try smp_bridge.retire(id);',''),
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
  files=[source,ROOT/'kernel/user/processes.dg',ROOT/'services/lib/process_abi.dg',ROOT/'tests/user_current_entry_probe.dg',ROOT/'tests/user_current_entry_probe.c',Path(__file__),*sorted((BASE/'kernel/sched').glob('*.*'))]
  before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};out=ROOT/'build/test/p6-cpl3-service-native'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);nasm,cc=tool('nasm','NASM'),tool('gcc','CC');evidence={}
  def run(args,d,label):
   args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60);(d/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
  candidate={}
  for mode in ('debug','release'):
   for variant in ('normal',*controls):
    d=out/(mode+'-'+variant);stage=d/'kernel';s=entry
    if variant!='normal':old,new=controls[variant];self.assertEqual(1,s.count(old));s=s.replace(old,new)
    overrides={**candidate,'user_current_entry_probe':s,'user.memory':MEMORY,'user.window_broker':WINDOWS,'user.device_host':DEVICE,'boot.trace_runtime':'module boot.trace_runtime;pub unsafe fn event(a:u64,b:u64,c:u64,d:u64)void{return;}'}
    copy_graph(stage,['user_current_entry_probe'],overrides);compiled=compile_file(stage/'user_current_entry_probe.dg',roots=[stage],mode=mode);(d/'probe.asm').write_text(compiled.assembly);(d/'probe.c').write_text(c)
    objects=[]
    for name,path in [('dong',d/'probe.asm'),('entry',BASE/'kernel/sched/user_entry.asm'),('legacy',BASE/'kernel/sched/user_legacy.asm')]:
     obj=d/(name+'.o');r=run([nasm,'-f','win64'if os.name=='nt'else'elf64',*nasm_flags(nasm),'-I',str(BASE/'include')+os.sep,'-I',str(ROOT/'include')+os.sep,path,'-o',obj],d,'assemble-'+name);self.assertEqual(0,r.returncode,r.stderr);objects.append(obj)
    exe=d/('probe.exe'if os.name=='nt'else'probe');r=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',*([]if os.name=='nt'else['-no-pie']),d/'probe.c',*objects,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
    for scenario in ('exit','fault','gui')if variant=='normal'else(('gui',)if variant=='test-mask-includes-normal-GUI'else('exit',)):
     r=run([exe,scenario],d,scenario);self.assertEqual(0 if variant=='normal'else 1,r.returncode,r.stdout+r.stderr)
     if variant!='normal':self.assertIn('user CPL3 current-source oracle line',r.stderr)
     evidence[mode+'-'+variant+'-'+scenario]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};self.assertEqual(before,after);(out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),contract="tracked-current-cpl3-v1",current_source=True,historical_replay=False,actual_services_fragments=True,real_catalog_domain_queue=True,memory_hardware_and_perform_boundary_mocked=True,actual_ap_cpl3_executed=False,source_sha256=after,sources_unchanged=True,evidence=evidence),indent=2)+'\n');print('USER_SMP_SERVICE_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
