"""Exact BSP policy and bridge path, real queue/Catalog/handles, native only."""
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
from tests.test_service_ipc_cancellation import block
from tests.test_service_gui_wiring import copy_graph
from tests import test_user_smp_services as old
from tests.test_user_smp_services import current_files
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT;ARCH=ROOT
TAIL='''
export("ro_setup") fn setup()u64{unsafe{
 CATALOG=smp_service_catalog_storage() as *procs.Catalog;try procs.initialize(CATALOG,1000000);
 var snapshot=proc.EMPTY_SNAPSHOT;try procs.start(CATALOG,5,5,0,&snapshot);try procs.mark_ready(CATALOG,5,1);
 try procs.start(CATALOG,6,6,0,&snapshot);try procs.mark_ready(CATALOG,6,1);
 try procs.start(CATALOG,2,2,0,&snapshot);try procs.mark_ready(CATALOG,2,1);
 let p=process(2);(*p).ready=1;(*p).root=0x202000;(*p).frame=abi.EMPTY;(*p).frame.rip=0x400000;(*p).frame.rsp=0x70000000;(*p).frame.cr3=(*p).root;
 try handles.init(&STATES[2].table);let cap=try handles.install(&STATES[2].table,handles.CONFIGURATION,devices.CONFIGURATION_OBJECT,handles.READ);
 (*p).frame.rdi=cap;(*p).frame.rsi=0xe0000000;(*p).frame.rdx=0x70001000;
 try enable_smp();let projected=smp_project();if projected!=0{return projected;}return 0;
}}
export("ro_frame") fn frame()u64{unsafe{return (&(*process(2)).frame) as u64;}}
export("ro_counts") fn counts()u64{unsafe{return bridge.counts(2) as u64;}}
export("ro_policy_guard") fn guard(which:u64)u64{unsafe{
 let f=&(*process(2)).frame;let p=(*D).processes+2;let c=(*D).cpus;
 if which==1{(*CATALOG).incarnation[2]+=1;let r=smp_service_policy(2,257,f as u64);(*CATALOG).incarnation[2]-=1;return r;}
 if which==2{(*process(3)).frame=*f;return smp_service_policy(2,257,(&(*process(3)).frame) as u64);}
 if which==3{(*D).owner=1;let r=smp_service_policy(2,257,f as u64);(*D).owner=0;return r;}
 if which==4{return smp_service_policy(2,7,f as u64);}
 if which==5{(*p).root+=4096;let r=smp_service_policy(2,257,f as u64);(*p).root-=4096;return r;}
 if which==6{let saved=CATALOG;CATALOG=null;let r=smp_service_policy(2,257,f as u64);CATALOG=saved;return r;}
 return smp_service_policy(2,257,f as u64);
}}
'''
CMAIN=r'''
extern U ABI ro_setup(void),ro_frame(void),ro_counts(void),ro_policy_guard(U);
extern U ABI dong_user_smp_service(U,U,U),dong_user_smp_service_policy(U,U,U),dong_user_smp_project(void);
static unsigned char catalog_storage[32768] __attribute__((aligned(64)));
static U stable=1,valid_output=1,expected_flushes,performed;
U ABI smp_service_catalog_storage(void){return (U)(uintptr_t)catalog_storage;}
U ABI user_validate_frame(Frame*f){return user_smp_arch_validate((U)(uintptr_t)f,f->w[18]);}
U ABI ro_stable(U physical){C(physical==0xe0000000);return stable;}
U ABI ro_output(U slot,U va,U size,U write){C(slot==2&&va==0x70001000&&size==4&&write==1);return valid_output;}
U ABI smp_service_fixture_event(U phase,U slot,U value){C(phase==1&&slot==2&&value==ro_frame());for(unsigned i=0;i<3;i++)C(flushes[i]==expected_flushes);performed++;return 0;}
U ABI smp_service_fixture_irq(U vector){(void)vector;return 0;}
U ABI user_bridge_service(U s,U e,U p){return dong_user_smp_service(s,e,p);}
U ABI user_bridge_service_policy(U s,U e,U p){return dong_user_smp_service_policy(s,e,p);}
U ABI user_bridge_project(void){return dong_user_smp_project();}
static void invoke(U operation,U skip){cpu=0;Frame f=*(Frame*)(uintptr_t)ro_frame();f.w[14]=operation;
 if(operation==0x73)for(unsigned i=0;i<6;i++)f.w[8+i]=0; /* R9..RDI */
 memset(hardware[0],0x7b,1024);roots[0]=0x100000;U old=flushes[0];expected_flushes=old+(skip?0:1);
 U next=dong_user_smp_event(0,(U)(uintptr_t)&f,256);C(next==d->cpus[0].returned&&!d->failed);for(unsigned i=0;i<3;i++)C(flushes[i]==old+(skip?0:2));C(dong_user_smp_return(0)==1);
}
int main(void){setup();cpu=0;C(!ue_lock(0));C(!ro_setup());C(!ue_unlock(0));start(0,2);
 invoke(0x60,1);stable=0;invoke(0x60,0);stable=1;valid_output=0;invoke(0x60,0);valid_output=1;
 invoke(0x61,0);invoke(0x73,1);invoke(0xb0,0);invoke(0xb6,0);invoke(0x999,0);
 U*v=(U*)(uintptr_t)ro_counts();C(performed==8&&v[0]==8&&v[1]==3&&v[2]==1&&v[3]==12&&v[4]==4&&v[5]==257&&v[6]==0x999);
 /* Classifier rejects wrong incarnation/frame/CPU/event before any skip. */
 cpu=0;roots[0]=0x100000;d->cpus[0].mode=4;C(!ue_lock(0));Frame*f=(Frame*)(uintptr_t)ro_frame();f->w[14]=0x73;for(unsigned i=8;i<14;i++)f->w[i]=0;
 C(ro_policy_guard(0)==1);for(unsigned i=1;i<=6;i++)C(ro_policy_guard(i)==0);
 printf("readonly native actual-policy+bridge checks=%u calls=%u skipped=%u full=%u\n",(unsigned)checks,(unsigned)v[0],(unsigned)v[4],(unsigned)v[3]);return 0;}
'''
class Tests(unittest.TestCase):
 def test_same_page_preflight_uses_actual_pte_flags(self):
  source=(BASE/'kernel/user/devices.dg').read_text();helper=block(source,'pub unsafe fn configuration_read_stable(').replace('startup.space_pointer()','&S')
  entry='''module ecam_readonly_probe;import mm.paging as paging;
pub error Denied=0x1111;const WINDOW:u64=0xffff_c000_0008_0000;
var REGION_BASE:u64=0xe0000000;var REGION_FIRST:u64=0;var REGION_LAST:u64=255;var CURRENT_PAGE:u64=0;
var S:paging.Space=paging.EMPTY_SPACE;var TABLES:[8]paging.Table=[paging.Table{entries:[0;512]};8];var META:[8]u8=[0;8];
'''+block(source,'unsafe fn configuration_address(')+helper+'''
unsafe fn setup(flags:u64,pa:u64,current:u64)!u64{unsafe{
 S=paging.EMPTY_SPACE;try paging.init(&S,TABLES[..],0x100000,META[..],48,true);
 try paging.map_live(&S,WINDOW,pa,flags&~paging.USER);CURRENT_PAGE=current;
 // Failure injection only: the real mapper correctly refuses a high USER
 // mapping. Forge that corrupt PTE after construction to test the preflight.
 if (flags&paging.USER)!=0{var table:usize=0;var shift:u64=39;while true{
  let index=((WINDOW>>shift)&511) as usize;let entry=TABLES[table].entries[index];TABLES[table].entries[index]=entry|4;
  if shift==12{break;}table=(((entry&0x000f_ffff_ffff_f000)-0x100000)/4096) as usize;shift-=9;
 }}
 if configuration_read_stable(0xe0000010){return 1;}return 0;
}}
export("ecam_test") fn test(flags:u64,pa:u64,current:u64)u64{unsafe{match setup(flags,pa,current){ok(v)=>{return v;},err(e)=>{return e;},}}}
'''
  c='''#include <stdint.h>\n#include <stdlib.h>\n#include <stdio.h>\n#define ABI __attribute__((sysv_abi))\ntypedef uint64_t U;extern U ABI ecam_test(U,U,U);void ABI __dong_panic(void){exit(2);}
#define T(f,p,c,e) do{U r=ecam_test(f,p,c);if(r!=e){printf("preflight line %u got %x expected %u\\n",__LINE__,(unsigned)r,(unsigned)e);return 1;}}while(0)
int main(void){
 T(9,0xe0000000,0xe0000000,1);
 T(9,0xe0001000,0xe0000000,0);
 T(9,0xe0000000,0xe0001000,0);
 T(9,0xe0000000,0,0);
 T(1,0xe0000000,0xe0000000,0);
 T(11,0xe0000000,0xe0000000,0);
 T(12,0xe0000000,0xe0000000,0);
 T(8,0xe0000000,0xe0000000,0);
 puts("actual ECAM stable-preflight PTE positive and WB/USER/EXEC/RO/PA/cold rejection");return 0;}'''
  out=ROOT/'build/test/p6-ecam-preflight-native'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);nasm,cc=tool('nasm','NASM'),tool('gcc','CC');evidence={}
  controls={'ignores-PTE-flags':('mapping.flags==(paging.WRITE|paging.UNCACHED)','true'),'ignores-actual-PA':('mapping.physical==CURRENT_PAGE&&','')}
  for mode in ('debug','release'):
   for variant in ('normal',*controls):
    d=out/(mode+'-'+variant);d.mkdir();s=entry
    if variant!='normal':a,b=controls[variant];self.assertEqual(1,s.count(a));s=s.replace(a,b)
    p=d/'ecam_readonly_probe.dg';p.write_text(s);(d/'probe.c').write_text(c);compiled=compile_file(p,roots=[d,ROOT/'kernel'],mode=mode);(d/'probe.asm').write_text(compiled.assembly)
    def run(args,label):
     r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=60);(d/(label+'.json')).write_text(json.dumps(dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
    obj=d/'probe.o';r=run([nasm,'-f','win64'if os.name=='nt'else'elf64',*nasm_flags(nasm),d/'probe.asm','-o',obj],'assemble');self.assertEqual(0,r.returncode,r.stderr)
    exe=d/('probe.exe'if os.name=='nt'else'probe');r=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([]if os.name=='nt'else['-no-pie']),d/'probe.c',obj,'-o',exe],'link');self.assertEqual(0,r.returncode,r.stderr)
    r=run([exe],'native');self.assertEqual(0 if variant=='normal'else 1,r.returncode,r.stdout+r.stderr);evidence[mode+'-'+variant]=dict(returncode=r.returncode,stdout=r.stdout)
  (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),contract="tracked-current-cpl3-v1",actual_helper_actual_paging=True,startup_space_pointer_boundary_adapted=True,actual_guest_executed=False,evidence=evidence),indent=2)+'\n');print('ECAM_PREFLIGHT_EVIDENCE',out)
 def test_actual_policy_bridge_and_real_bad_controls(self):
  files=current_files()+[Path(__file__),ROOT/'tests/user_current_entry_probe.dg',ROOT/'tests/user_current_entry_probe.c',ROOT/'kernel/user/processes.dg',ROOT/'kernel/ipc/handles.dg']
  before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files}
  text=(BASE/'kernel/user/services.dg').read_text();actual='\n'.join(block(text,n)for n in ('unsafe fn process(', 'unsafe fn managed(', 'pub unsafe fn enable_smp(', 'export("dong_user_smp_project")','export("dong_user_smp_service_policy")','export("dong_user_smp_service")'))
  prefix=old.PREFIX.replace('import user.device_host as device_host;','import user.device_host as device_host;import user.devices as devices;import ipc.handles as handles;import lib.device_abi as dev;')
  prefix=prefix.replace('struct State{waiting:u64,started:u64}','struct State{table:handles.Table,waiting:u64,started:u64}').replace('State{waiting:0,started:0}','State{table:handles.EMPTY_TABLE,waiting:0,started:0}')
  prefix=prefix.replace('var LAUNCH_FAILED:bool=false;','var LAUNCH_FAILED:bool=false;var GRAPHICS:bool=true;')
  prefix=prefix.replace('try retire_one(id,state,status);','').replace('try retire_one(CURRENT,proc.EXITED,73);','')
  entry=(ROOT/'tests/user_current_entry_probe.dg').read_text()+prefix+actual+TAIL
  # setup uses ! operations inside an ordinary exported result wrapper.
  entry=entry.replace('export("ro_setup") fn setup()u64{unsafe{','unsafe fn setup_inner()!u64{unsafe{')+'\nexport("ro_setup") fn setup()u64{unsafe{match setup_inner(){ok(v)=>{return v;},err(e)=>{return e;},}}}\n'
  memory=old.MEMORY+'''unsafe extern "sysv64" fn ro_output(slot:u64,va:u64,size:u64,write:u64)u64;
pub unsafe fn check_range(slot:usize,va:u64,size:usize,write:bool)!void{unsafe{if ro_output(slot as u64,va,size as u64,write as u64)!=1{return error.Invalid;}}return;}pub error Invalid=0x1111;
'''
  devices='''module user.devices;pub const CONFIGURATION_OBJECT:u64=0x1234;unsafe extern "sysv64" fn ro_stable(physical:u64)u64;pub unsafe fn configuration_read_stable(physical:u64)bool{unsafe{return ro_stable(physical)==1;}}'''
  c=(ROOT/'tests/user_current_entry_probe.c').read_text()
  for needle in ('U ABI user_bridge_service(', 'U ABI user_bridge_project(', 'U ABI dong_user_smp_service(', 'U ABI dong_user_smp_project('):c=c.replace(block(c,needle),'')
  c=c[:c.index('int main(void)')]+CMAIN
  controls={
   'clock-policy-full':('services','return 1;\n }\n if (*frame).rax!=0x60','return 0;\n }\n if (*frame).rax!=0x60'),
   'PCI-window-replacement-skips':('services','if !devices.configuration_read_stable((*frame).rsi){return 0;}',''),
   'invalid-output-skips':('services','match memory.check_range(slot,(*frame).rdx,4,true){ok=>{},err(e)=>{return 0;},}',''),
   'stale-incarnation-skips':('services','||(*p).incarnation!=(*CATALOG).incarnation[slot]',''),
   'foreign-frame-skips':('services','||pointer!=(&(*process(slot)).frame) as u64',''),
   'changed-root-skips':('services','||(*p).root!=(*process(slot)).root',''),
   'null-catalog-skips':('services','if CATALOG==null{return 0;}','if CATALOG==null{return 1;}'),
   'missing-mutation-before-barrier':('bridge','if policy==0{(*counter).full+=2;let before=try ud.barrier_begin(d,cpu);try ud.barrier_wait(d,cpu,before,try deadline(d,cpu));}','if policy==0{(*counter).full+=2;}'),
   'missing-mutation-after-barrier':('bridge','if policy==0{let after=try ud.barrier_begin(d,cpu);try ud.barrier_wait(d,cpu,after,try deadline(d,cpu));}',''),
  }
  out=ROOT/'build/test/p6-readonly-native'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);evidence={};nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
  candidate={}
  bridge=(BASE/'kernel/sched/user_bridge.dg').read_text();candidate['sched.user_bridge']=bridge
  for mode in ('debug','release'):
   for variant in ('normal',*controls):
    d=out/(mode+'-'+variant);stage=d/'kernel';s=entry;b=bridge
    if variant!='normal':
     kind,old_s,new_s=controls[variant]
     # Identity checks occur in both actual policy and actual callback; mutate
     # the policy occurrence only. The callback still independently rejects.
     if kind=='services':
      policy=block(s,'export("dong_user_smp_service_policy")');self.assertEqual(1,policy.count(old_s));s=s.replace(policy,policy.replace(old_s,new_s))
     else:self.assertEqual(1,b.count(old_s));b=b.replace(old_s,new_s)
    overrides={**candidate,'sched.user_bridge':b,'user_current_entry_probe':s,'user.memory':memory,'user.devices':devices,'boot.trace_runtime':'module boot.trace_runtime;pub unsafe fn event(a:u64,b:u64,c:u64,d:u64)void{return;}','user.window_broker':old.WINDOWS,'user.device_host':old.DEVICE+'pub unsafe fn irq_poll_readonly(token:u64,owner:u64,after:u64)bool{return false;}'}
    copy_graph(stage,['user_current_entry_probe'],overrides);compiled=compile_file(stage/'user_current_entry_probe.dg',roots=[stage],mode=mode);(d/'probe.asm').write_text(compiled.assembly);(d/'probe.c').write_text(c)
    objects=[]
    def run(args,label):
     r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=60);(d/(label+'.json')).write_text(json.dumps(dict(command=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
    for name,path in [('dong',d/'probe.asm'),('entry',ARCH/'kernel/sched/user_entry.asm'),('legacy',ARCH/'kernel/sched/user_legacy.asm')]:
     obj=d/(name+'.o');r=run([nasm,'-f','win64'if os.name=='nt'else'elf64',*nasm_flags(nasm),'-I',str(ARCH/'include')+os.sep,'-I',str(ROOT/'include')+os.sep,path,'-o',obj],'asm-'+name);self.assertEqual(0,r.returncode,r.stderr);objects.append(obj)
    exe=d/('probe.exe'if os.name=='nt'else'probe');r=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',*([]if os.name=='nt'else['-no-pie']),d/'probe.c',*objects,'-o',exe],'link');self.assertEqual(0,r.returncode,r.stderr)
    r=run([exe],'native');self.assertEqual(0 if variant=='normal'else 1,r.returncode,r.stdout+r.stderr)
    if variant!='normal':self.assertIn('user CPL3 current-source oracle line',r.stderr)
    evidence[mode+'-'+variant]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};self.assertEqual(before,after)
  (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),contract="tracked-current-cpl3-v1",source_sha256=after,sources_unchanged=True,real_catalog_handles_queue_domain_bridge=True,hardware_memory_and_perform_boundary_mocked=True,actual_guest_executed=False,evidence=evidence),indent=2)+'\n');print('READONLY_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
