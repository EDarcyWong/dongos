"""Real yield/runnable/IRQ_WAIT paths; owned user RAM and hardware are adapters."""
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
from tests.test_service_ipc_cancellation import block
from tests.test_service_gui_wiring import copy_graph
from tests import test_user_smp_services as old
from tests import test_user_smp_poll_fast as policy
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT;ARCH=ROOT
TAIL='''
var CAP:u64=0;
unsafe fn started(cfg:usize)!void{unsafe{var s=proc.EMPTY_SNAPSHOT;try procs.start(CATALOG,cfg,cfg,0,&s);try procs.mark_ready(CATALOG,cfg,1);}return;}
unsafe fn setup_inner(which:u64)!void{unsafe{
 CATALOG=smp_service_catalog_storage() as *procs.Catalog;try procs.initialize(CATALOG,1000000);
 try started(5);try started(6);try started(2);try started(4);
 var slot:usize=4;while slot<7{let p=process(slot);(*p).ready=1;(*p).root=0x200000+slot as u64*4096;(*p).frame=abi.EMPTY;(*p).frame.rip=0x400000;(*p).frame.rsp=0x70000000;(*p).frame.cr3=(*p).root;(*p).frame.rax=0xa5;slot+=1;}
 try handles.init(&STATES[4].table);let object=try device_host.fixture(4);CAP=try handles.install(&STATES[4].table,handles.INTERRUPT,object,handles.WAIT);
 try enable_smp();if smp_project()!=0{return error.Protocol;}
 slot=4;while slot<6{var out:u64=0;if !(try ud.select(D,0,&out)){return error.Protocol;}try ud.selected_kernel(D,0);if (*(*D).cpus).slot!=slot as u64{return error.Protocol;}try ud.release(D,0,smp_queue.BLOCKED);slot+=1;}
 var out:u64=0;if !(try ud.select(D,0,&out)){return error.Protocol;}try ud.selected_kernel(D,0);if (*(*D).cpus).slot!=6{return error.Protocol;}
 STATES[4].waiting=5;IRQ_TOKEN[4]=CAP;IRQ_AFTER[4]=1;IRQ_POINTER[4]=0x70004000;
 STATES[5].waiting=3;WAIT_AFTER[5]=(*CATALOG).sequence;WAIT_POINTER[5]=0x70005000;
 if which==0{IRQ_AFTER[4]=0;try started(1);}
 if which==2{WAIT_DEADLINE[5]=1;IRQ_DEADLINE[4]=1;}
 if which==3{IRQ_AFTER[4]=0;try started(1);}
 return;
}}
export("pw_setup") fn setup(which:u64)u64{unsafe{match setup_inner(which){ok=>{return 0;},err(e)=>{return e;},}}}
export("pw_yield") fn yielding()u64{unsafe{CURRENT=6;let f=&(*process(6)).frame;(*f).rax=3;match perform(f){ok(value)=>{CURRENT=NONE;return value as u64;},err(e)=>{CURRENT=NONE;return e;},}}}
export("pw_irq") fn irq(after:u64)u64{unsafe{CURRENT=4;let f=&(*process(4)).frame;(*f).rax=dev.IRQ_WAIT;(*f).rdi=CAP;(*f).rsi=after;(*f).rdx=0x70004000;(*f).r10=0;(*f).r8=0;(*f).r9=0;
 match perform(f){ok(value)=>{CURRENT=NONE;return value as u64;},err(e)=>{CURRENT=NONE;return e;},}
}}
export("pw_get") fn get(slot:usize,which:u64)u64{unsafe{if which==0{return STATES[slot].waiting;}if which==1{return (*process(slot)).frame.rax;}if which==2{return (*(*D).engine).threads[slot].state;}if which==3{return CAP;}return 0;}}
export("pw_project") fn project()u64{return smp_project();}
'''
CMAIN=r'''
extern U ABI pw_setup(U),pw_yield(void),pw_irq(U),pw_get(U,U),pw_project(void);
static unsigned char catalog_storage[32768] __attribute__((aligned(64)));
static unsigned char outputs[16][64];static U copies[16],copy_failure;
U ABI smp_service_catalog_storage(void){return (U)(uintptr_t)catalog_storage;}
U ABI smp_service_fixture_event(U a,U b,U c){(void)a;(void)b;(void)c;return 0;}
U ABI user_validate_frame(Frame*f){return user_smp_arch_validate((U)(uintptr_t)f,f->w[18]);}
U ABI user_bridge_service_policy(U a,U b,U c){(void)a;(void)b;(void)c;return 0;}
U ABI services_pcid_metric(U a){(void)a;return 0;}U ABI services_smp_pcid_metric(U a){(void)a;return 0;}
U ABI pw_check(U slot,U va,U size,U write){C(slot==4&&va==0x70004000&&size==64&&write==1);return 1;}
U ABI pw_copy(U slot,U va,U ptr,U size){C(cpu==0&&d->lock==1&&d->owner==0&&slot>=4&&slot<=5&&va==0x70000000+slot*4096&&size==64);
 C(pw_get(slot,2)==3);for(unsigned i=0;i<3;i++)C(d->cpus[i].slot!=slot&&d->cpus[i].token!=d->processes[slot].token);
 if(copy_failure){return 0;}memcpy(outputs[slot],(void*)(uintptr_t)ptr,64);copies[slot]++;return 1;}
U ABI arch_read_tsc(void){return clock_tick++;}
int main(int argc,char**argv){C(argc==2);U which=strtoull(argv[1],0,10);setup();cpu=0;C(!ue_lock(0));memset(outputs,0xa5,sizeof outputs);C(!pw_setup(which));
 C(pw_get(4,2)==3&&pw_get(5,2)==3&&d->cpus[0].slot==6&&d->cpus[0].mode==5);
 for(unsigned i=1;i<3;i++)C(d->cpus[i].token==0&&d->cpus[i].mode==1);
 U epoch=d->completed;copy_failure=(which==3);U result=pw_yield();
 if(which==0){C(result==4&&pw_get(4,0)==0&&pw_get(5,0)==0&&pw_get(4,1)==0&&pw_get(5,1)==0&&copies[4]==1&&copies[5]==1);
   U*v=(U*)outputs[4];C(v[0]==1&&v[1]==pw_get(4,3)&&v[6]==1);v=(U*)outputs[5];C(v[0]==1&&v[2]==1&&v[5]==2);}
 if(which==1){C(result==6&&pw_get(4,0)==5&&pw_get(5,0)==3&&pw_get(4,1)==0xa5&&pw_get(5,1)==0xa5&&!copies[4]&&!copies[5]);}
 if(which==2){C(result==4&&pw_get(4,0)==0&&pw_get(5,0)==0&&pw_get(4,1)==0x05120007&&pw_get(5,1)==0x05110007&&!copies[4]&&!copies[5]);}
 if(which==3){C(result==0x1111&&pw_get(4,0)==5&&pw_get(5,0)==3&&pw_get(4,1)==0xa5&&pw_get(5,1)==0xa5&&!copies[4]&&!copies[5]);}
 C(d->completed==epoch&&pw_get(4,2)==3&&pw_get(5,2)==3);copy_failure=0;C(!pw_project());
 if(which==0||which==2)C(pw_get(4,2)==1&&pw_get(5,2)==1);
 if(which==1)C(pw_get(4,2)==3&&pw_get(5,2)==3);
 if(which==3)C(pw_get(4,2)==1&&pw_get(5,2)==1);
 C(!ue_audit());
 /* Execute exact NONBLOCK IRQ_WAIT branch after the wake fixture. Target is
    still blocked until the projection above; user RAM remains a boundary. */
 if(which==1){U old=read64(outputs[4]);C(pw_irq(1)==0x05120006&&read64(outputs[4])==old&&copies[4]==0);C(pw_irq(0)==4&&copies[4]==1);}
 printf("poll fast actual yield/wakes checks=%u scenario=%u domain-BLOCKED/no-remote-owner, event/IRQ/timeout/output-failure, projection-after-wake\n",(unsigned)checks,(unsigned)which);return 0;}
'''
class Tests(unittest.TestCase):
 def test_actual_yield_waiters_irq_and_blocked_projection(self):
  text=(BASE/'kernel/user/services.dg').read_text();prefix=old.PREFIX
  prefix=prefix.replace('import user.device_host as device_host;','import user.device_host as device_host;import ipc.handles as handles;import lib.device_abi as dev;import arch.x86_64 as arch;')
  prefix=prefix.replace('struct State{waiting:u64,started:u64}','struct State{table:handles.Table,waiting:u64,started:u64}').replace('State{waiting:0,started:0}','State{table:handles.EMPTY_TABLE,waiting:0,started:0}')
  for name in ('unsafe fn wake_waiters(', 'unsafe fn wake_irqs(', 'unsafe fn perform('):prefix=prefix.replace(block(prefix,name),'')
  prefix=prefix.replace('try retire_one(id,state,status);','')
  globals='var WAIT_AFTER:[16]u64=[0;16];var WAIT_POINTER:[16]u64=[0;16];var WAIT_DEADLINE:[16]u64=[0;16];var EVENT:proc.Event=proc.EMPTY_EVENT;var IRQ_TOKEN:[16]u64=[0;16];var IRQ_AFTER:[16]u64=[0;16];var IRQ_POINTER:[16]u64=[0;16];var IRQ_DEADLINE:[16]u64=[0;16];'
  actual='\n'.join(block(text,n)for n in ('unsafe fn process(','unsafe fn managed(','unsafe fn owner_key(','unsafe fn authority(','unsafe fn wake_waiters(','unsafe fn wake_irqs(','unsafe fn runnable(','pub unsafe fn enable_smp(','export("dong_user_smp_project")'))
  perform='unsafe fn perform(frame:*abi.Frame)!usize{unsafe{let code=(*frame).rax;'+block(text,'if code==3 {')+block(block(text,'unsafe fn device_call('),'if code==dev.IRQ_WAIT{')+'}return error.Protocol;}'
  source=(ROOT/'tests/user_current_entry_probe.dg').read_text()+prefix+globals+actual+perform+TAIL
  memory=old.MEMORY+'''pub error Invalid=0x1111;
unsafe extern "sysv64" fn pw_check(slot:u64,va:u64,size:u64,write:u64)u64;unsafe extern "sysv64" fn pw_copy(slot:u64,va:u64,ptr:u64,size:u64)u64;
pub unsafe fn check_range(slot:usize,va:u64,size:usize,write:bool)!void{unsafe{if pw_check(slot as u64,va,size as u64,write as u64)!=1{return error.Invalid;}}return;}
pub unsafe fn copy_out(slot:usize,va:u64,source:[]const u8)!void{unsafe{if pw_copy(slot as u64,va,source.ptr as u64,source.len as u64)!=1{return error.Invalid;}}return;}
'''
  host=policy.HOST+block((BASE/'kernel/user/device_host.dg').read_text(),'pub unsafe fn poll_irq(')
  arch='module arch.x86_64;unsafe extern "sysv64" fn arch_read_tsc()u64;pub unsafe fn read_tsc()u64{unsafe{return arch_read_tsc();}}'
  c=(ROOT/'tests/user_current_entry_probe.c').read_text().replace(block((ROOT/'tests/user_current_entry_probe.c').read_text(),'U ABI dong_user_smp_project('),'');c=c[:c.index('int main(void)')]+CMAIN
  controls={'yield-does-not-wake':('try wake_waiters();try wake_irqs();',''), 'IRQ-wakes-do-not-publish':('STATES[id].waiting=0;(*process(id)).frame.rax=0;',''), 'event-wake-omits-output':('if found{try memory.copy_out(id,WAIT_POINTER[id],slice_from_raw_parts((&EVENT) as *const u8,sizeof(proc.Event)));}',''), 'wakes-ignore-output-failure':('try memory.copy_out(id,WAIT_POINTER[id],slice_from_raw_parts((&EVENT) as *const u8,sizeof(proc.Event)));','let ignored=memory.copy_out(id,WAIT_POINTER[id],slice_from_raw_parts((&EVENT) as *const u8,sizeof(proc.Event)));')}
  candidate={}
  files=[BASE/'kernel/user/services.dg',BASE/'kernel/user/device_host.dg',Path(__file__)];before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files}
  out=ROOT/'build/test/p6-poll-wakes-native'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);nasm,cc=tool('nasm','NASM'),tool('gcc','CC');evidence={}
  for mode in ('debug','release'):
   for variant in ('normal',*controls):
    d=out/(mode+'-'+variant);stage=d/'kernel';s=source
    if variant!='normal':a,b=controls[variant];self.assertEqual(1,s.count(a));s=s.replace(a,b)
    copy_graph(stage,['user_current_entry_probe'],{**candidate,'user_current_entry_probe':s,'user.memory':memory,'boot.trace_runtime':'module boot.trace_runtime;pub unsafe fn event(a:u64,b:u64,c:u64,d:u64)void{return;}','user.window_broker':old.WINDOWS,'user.device_host':host,'arch.x86_64':arch})
    result=compile_file(stage/'user_current_entry_probe.dg',roots=[stage],mode=mode);(d/'probe.asm').write_text(result.assembly);(d/'probe.c').write_text(c)
    def run(args,label):
     r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=60);(d/(label+'.json')).write_text(json.dumps(dict(command=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
    objects=[]
    for name,p in [('dong',d/'probe.asm'),('entry',ARCH/'kernel/sched/user_entry.asm'),('legacy',ARCH/'kernel/sched/user_legacy.asm')]:
     obj=d/(name+'.o');r=run([nasm,'-f','win64'if os.name=='nt'else'elf64',*nasm_flags(nasm),'-I',str(ARCH/'include')+os.sep,'-I',str(ROOT/'include')+os.sep,p,'-o',obj],'asm-'+name);self.assertEqual(0,r.returncode,r.stderr);objects.append(obj)
    exe=d/('probe.exe'if os.name=='nt'else'probe');r=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',*([]if os.name=='nt'else['-no-pie']),d/'probe.c',*objects,'-o',exe],'link');self.assertEqual(0,r.returncode,r.stderr)
    for scenario in (0,1,2,3)if variant=='normal'else((3,)if variant=='wakes-ignore-output-failure'else(0,)):
     r=run([exe,str(scenario)],str(scenario));self.assertEqual(0 if variant=='normal'else 1,r.returncode,r.stdout+r.stderr)
     if variant!='normal':self.assertIn('user CPL3 current-source oracle line',r.stderr)
     evidence[mode+'-'+variant+'-'+str(scenario)]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};self.assertEqual(before,after)
  (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),contract="tracked-current-cpl3-v1",actual_yield_runnable_waiters_irq_wait_and_projection=True,real_catalog_domain_queue_handles_irq_ledger=True,owned_user_ram_and_hardware_adapted=True,no_os_build_or_vm=True,source_sha256=after,sources_unchanged=True,evidence=evidence),indent=2)+'\n');print('POLL_WAKES_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
