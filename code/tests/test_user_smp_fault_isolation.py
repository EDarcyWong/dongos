"""Actual bridge/domain/service retirement, real ASM validators, no guest."""
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
from tests.test_service_ipc_cancellation import block
from tests.test_service_gui_wiring import copy_graph
from tests import test_user_smp_services as old
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'build/test/p6-user-fault-isolation-candidate';R3=ROOT/'build/test/combined-user-smp-positive-r3/source';ARCH=ROOT/'build/test/p6-cpl3-integration-candidate'
TAIL='''
export("fi_add") fn add()u64{unsafe{
 match catalog_start(10,8){ok=>{},err(e)=>{return e;},}let p=process(8);(*p).ready=1;(*p).root=0x208000;(*p).frame=abi.EMPTY;(*p).frame.rip=0x400000;(*p).frame.rsp=0x70000000;(*p).frame.cr3=(*p).root;
 let result=smp_project();if result!=0{return result;}
 match smp_queue.set_affinity((*D).engine,(*((*D).processes+7)).token,2){ok=>{},err(e)=>{return e;},}
 match smp_queue.set_affinity((*D).engine,(*((*D).processes+8)).token,4){ok=>{return 0;},err(e)=>{return e;},}
}}
export("fi_state") fn state(cfg:usize,which:u64)u64{unsafe{
 if which==0{return (*CATALOG).states[cfg].state;}if which==1{return (*CATALOG).states[cfg].status;}if which==2{return (*CATALOG).states[cfg].process;}return (*CATALOG).states[cfg].generation;
}}
export("fi_counts") fn counts(slot:usize,index:u64)u64{unsafe{
 if index>=7{return 0xffff_ffff_ffff_ffff;}let p=bridge.counts(slot);
 return *((p as u64+index*8) as *const u64);
}}
'''
CMAIN=r'''
extern U ABI us_setup(U),us_project(void),us_get(U),fi_add(void),fi_state(U,U),fi_counts(U,U);
static unsigned char catalog_storage[32768] __attribute__((aligned(64)));static U eois,performed,withdrawn,interrupts;
U ABI smp_service_catalog_storage(void){return (U)(uintptr_t)catalog_storage;}
U ABI services_pcid_metric(U x){(void)x;return 0;}U ABI services_smp_pcid_metric(U x){(void)x;return 0;}
U ABI user_bridge_service_policy(U a,U b,U c){(void)a;(void)b;(void)c;return 0;}
U ABI smp_service_fixture_irq(U vector){C(cpu==0&&(vector==0x51||vector==0x5c||vector==0x60));interrupts++;return 0;}
U ABI smp_service_fixture_event(U phase,U slot,U value){C(cpu==0&&d->lock==1&&d->owner==0);
 if(phase==1){C(slot==8&&value==d->processes[8].frame);performed++;}
 else if(phase==2){C(slot==7&&value==1&&eois==1&&!d->processes[7].token);for(unsigned i=0;i<3;i++)C(d->cpus[i].ack==d->completed&&d->completed>0&&d->cpus[i].token!=264);withdrawn++;}
 else{C(0);}return 0;}
U ABI fi_service(U slot,U event,U frame){C(cpu==0&&d->owner==0&&d->lock==1);return dong_user_smp_service(slot,event,frame);}
int main(int argc,char**argv){C(argc==2);U which=strtoull(argv[1],0,10);setup();cpu=0;C(!ue_lock(0));C(!us_setup(9)&&!fi_add());U token=d->processes[7].token,healthy=d->processes[8].token;
 memset((void*)(uintptr_t)d->processes[7].xstate,0x7b,1024);C(!ue_unlock(0));
 if(which==4){cpu=1;C(dong_user_smp_idle(1,257)==d->cpus[1].returned);((Frame*)(uintptr_t)d->cpus[1].returned)->w[17]=0;
  C(dong_user_smp_return(1)==UINT64_MAX&&d->failed&&fi_state(9,0)==2&&!withdrawn&&!eois);puts("private return-copy corruption remains held");return 0;}
 start(1,7);Frame f=*(Frame*)(uintptr_t)d->processes[7].frame;
 if(which==0){f.w[17]=0;}if(which==1){f.w[16]|=1<<18;}if(which==2){f.w[16]|=0x10400;}if(which==3){f.w[18]+=4096;}
 roots[1]=0x100000;memset(hardware[1],0x7b,1024);U next=dong_user_smp_event(1,(U)(uintptr_t)&f,0x40);
 if(which==3){C(next==UINT64_MAX&&d->failed&&fi_state(9,0)==2&&withdrawn==0&&eois==0);puts("trusted root mismatch remains held");return 0;}
 C(next!=UINT64_MAX&&eois==1&&!d->failed);
 if(which==2){C(next==d->cpus[1].returned&&dong_user_smp_return(1)==1&&d->cpus[1].mode==2&&fi_state(9,0)==2&&!withdrawn);puts("DF/RF hardware return remains allowed");return 0;}
 C(next==0&&d->cpus[1].token==0&&d->cpus[1].mode==1);cpu=0;C(dong_user_smp_idle(0,257)==0&&!d->failed);
 C(fi_state(9,0)==4&&fi_state(9,1)==0x04050001&&fi_state(9,2)==0&&fi_state(9,3)==1&&withdrawn==1&&!d->processes[7].token);
 C(fi_state(10,0)==2&&d->processes[8].token==healthy&&fi_state(10,2)==265&&us_get(3)==1&&performed==0);
 C(fi_counts(7,0)==1&&fi_counts(7,3)==2&&fi_counts(7,4)==0&&fi_counts(7,5)==258);
 C(token==264);for(unsigned i=0;i<3;i++){C(d->cpus[i].token!=token&&d->cpus[i].ack==d->completed);U*seen=(void*)(uintptr_t)d->cpus[i].seen;C(!seen[7*3+2]);}
 start(2,8);Frame good=*(Frame*)(uintptr_t)d->processes[8].frame;good.w[14]=1;roots[2]=0x100000;memset(hardware[2],0x7b,1024);
 C(dong_user_smp_event(2,(U)(uintptr_t)&good,256)==0);cpu=0;C(dong_user_smp_idle(0,257)==0&&!d->failed&&performed==1&&withdrawn==1&&fi_state(10,0)==2);
 start(2,8);C(((Frame*)(uintptr_t)d->cpus[2].returned)->w[14]==0x7788);C(!ue_audit());
 printf("user invalid-return isolation checks=%u scenario=%u EOI/deferred-BSP/real-Catalog-retire/alltag-ACK-before-withdraw/healthy-resume\n",(unsigned)checks,(unsigned)which);return 0;}
'''
class Tests(unittest.TestCase):
 def test_actual_bad_return_capture_deferred_retirement(self):
  text=(BASE/'kernel/user/services.dg').read_text();prefix=old.PREFIX.replace('import user.abi as abi;','import user.abi as abi;import boot.trace as trace;import boot.trace_runtime as boot_trace;')
  actual='\n'.join(block(text,n)for n in ('unsafe fn process(', 'unsafe fn managed(', 'unsafe fn retire_one(', 'pub unsafe fn enable_smp(', 'export("dong_user_smp_project")','export("dong_user_smp_service")','export("dong_user_smp_interrupt")'))
  source=(ROOT/'tests/user_entry_probe.dg').read_text().replace('bridge.initialize(storage,704,','bridge.initialize(storage,1536,')+prefix+actual+old.TAIL+TAIL
  memory=old.MEMORY+'pub var OBJECT_FAILED:bool=false;'
  device=old.DEVICE+'pub var PCI_FAILED:bool=false;'
  c=(ROOT/'tests/user_entry_probe.c').read_text()
  for needle in ('U ABI user_bridge_service(', 'U ABI user_bridge_project(', 'U ABI dong_user_smp_service(', 'U ABI dong_user_smp_project(', 'U ABI user_smp_arch_validate('):c=c.replace(block(c,needle),'')
  c=c.replace('static void fail(', 'extern U ABI user_smp_arch_validate(U,U),dong_user_smp_service(U,U,U),dong_user_smp_project(void);\nstatic void fail(')
  c=c.replace(block(c,'U ABI user_bridge_eoi('),'U ABI user_bridge_eoi(U who,U vector){C(who==cpu&&(vector==0x40||vector==0xf4||vector==0xff));eois++;return 0;}')
  c=c.replace('static U checks,cpu,','static U eois;\nstatic U checks,cpu,')
  c=c[:c.index('int main(void)')]+CMAIN.replace(',performed,withdrawn,interrupts;',',performed,withdrawn,interrupts;').replace('static U eois,performed','static U performed')
  c=c.replace('U ABI fi_service(', 'U ABI fi_service(')
  c=c.replace('static void plan_controls(', 'U ABI user_bridge_service(U a,U b,U c){return dong_user_smp_service(a,b,c);}\nU ABI user_bridge_project(void){return dong_user_smp_project();}\nstatic void plan_controls(')
  # Actual pure validator, extracted without modifying the raw production object.
  ctx=(R3/'kernel/user/context.asm').read_text();validator='bits 64\ndefault rel\n%include "user_context.inc"\nglobal user_validate_frame,user_validate_interrupt_frame,user_smp_arch_validate\n'+ctx[ctx.index('user_validate_frame:'):ctx.index('user_frame_size:')]
  raw=(R3/'kernel/sched/user_arch.asm').read_text();validator+=raw[raw.index('user_smp_arch_validate:'):raw.index('user_smp_arch_kick:')]
  bridge=(BASE/'kernel/sched/user_bridge.dg').read_text()
  domain=(BASE/'kernel/sched/user_domain.dg').read_text()
  controls={'old-global-held':('bridge',bridge,(R3/'kernel/sched/user_bridge.dg').read_text()),'missing-EOI':('bridge','else if user_bridge_eoi(cpu as u64,event)!=0{return error.Held;}',''),'invalid-Frame-discarded':('bridge','deferred=true;service_event=258;','deferred=false;service_event=258;'),'new-event-not-retired':('service','}else if event==258{','}else if event==259{'),'trusted-root-treated-user-fault':('bridge','if *(((*process).frame+144) as *const u64)!=(*process).root{return error.Held;}',''),'missing-final-return-validation':('domain','if user_smp_arch_validate((*c).returned,(*c).return_root)!=1{fail(d);return error.Held;}','')}
  candidate={}
  for tree in (R3/'kernel/sched',R3/'services'):
   for p in tree.rglob('*.dg'):
    s=p.read_text(encoding='utf-8');candidate[re.search(r'module\s+([\w.]+);',s)[1]]=s
  candidate['sched.user_domain']=(BASE/'kernel/sched/user_domain.dg').read_text()
  files=[BASE/'kernel/sched/user_bridge.dg',BASE/'kernel/sched/user_domain.dg',BASE/'kernel/user/services.dg',Path(__file__),R3/'kernel/user/context.asm',R3/'kernel/sched/user_arch.asm'];before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files}
  out=ROOT/'build/test/p6-user-fault-native'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);nasm,cc=tool('nasm','NASM'),tool('gcc','CC');evidence={}
  for mode in ('debug','release'):
   for variant in ('normal',*controls):
    d=out/(mode+'-'+variant);stage=d/'kernel';s=source;b=bridge;u=domain
    if variant!='normal':
     kind,a,z=controls[variant];target={'service':s,'bridge':b,'domain':u}[kind];self.assertEqual(1,target.count(a));target=target.replace(a,z)
     s=target if kind=='service'else s;b=target if kind=='bridge'else b;u=target if kind=='domain'else u
    overrides={**candidate,'sched.user_domain':u,'sched.user_bridge':b,'user_entry_probe':s,'user.memory':memory,'user.window_broker':old.WINDOWS,'user.device_host':device,'boot.trace':'module boot.trace;pub const SERVICE_STOP:u64=8;','boot.trace_runtime':'module boot.trace_runtime;pub unsafe fn event(a:u64,b:u64,c:u64,d:u64)void{return;}'}
    copy_graph(stage,['user_entry_probe'],overrides);result=compile_file(stage/'user_entry_probe.dg',roots=[stage],mode=mode);(d/'probe.asm').write_text(result.assembly);(d/'probe.c').write_text(c);(d/'validator.asm').write_text(validator)
    def run(args,label):
     r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=60);(d/(label+'.json')).write_text(json.dumps(dict(command=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
    objects=[]
    for name,p in [('dong',d/'probe.asm'),('entry',ARCH/'kernel/sched/user_entry.asm'),('legacy',ARCH/'kernel/sched/user_legacy.asm'),('validator',d/'validator.asm')]:
     obj=d/(name+'.o');r=run([nasm,'-f','win64'if os.name=='nt'else'elf64',*nasm_flags(nasm),'-I',str(ARCH/'include')+os.sep,'-I',str(ROOT/'include')+os.sep,p,'-o',obj],'asm-'+name);self.assertEqual(0,r.returncode,r.stderr);objects.append(obj)
    exe=d/('probe.exe'if os.name=='nt'else'probe');r=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',*([]if os.name=='nt'else['-no-pie']),d/'probe.c',*objects,'-o',exe],'link');self.assertEqual(0,r.returncode,r.stderr)
    for scenario in (0,1,2,3,4)if variant=='normal'else((3,)if variant=='trusted-root-treated-user-fault'else(4,)if variant=='missing-final-return-validation'else(0,)):
     r=run([exe,str(scenario)],str(scenario));self.assertEqual(0 if variant=='normal'else 1,r.returncode,r.stdout+r.stderr)
     if variant!='normal':self.assertIn('user CPL3 candidate oracle line',r.stderr)
     evidence[mode+'-'+variant+'-'+str(scenario)]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};self.assertEqual(before,after)
  (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,real_bridge_domain_queue_catalog_retirement=True,real_asm_frame_validators=True,hardware_xstate_flush_and_memory_boundaries_adapted=True,no_os_build_or_vm=True,source_sha256=after,sources_unchanged=True,evidence=evidence),indent=2)+'\n');print('USER_FAULT_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
