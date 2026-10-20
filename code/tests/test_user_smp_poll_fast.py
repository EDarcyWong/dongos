"""Exact new policy/const IRQ preview, real Catalog/domain/caps/IRQ/MSI."""
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
from tests.test_service_ipc_cancellation import block
from tests.test_service_gui_wiring import copy_graph
from tests import test_user_smp_services as old
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT;ARCH=ROOT
HOST='''module user.device_host;import user.device_manager as ledger;import drivers.pci_msi as msi;import lib.device_abi as abi;
pub var PCI_FAILED:bool=false;var T:ledger.Table=ledger.EMPTY;pub var TABLE:*ledger.Table=null;pub var IRQ:abi.Irq=abi.EMPTY_IRQ;pub var MSI:msi.State=msi.EMPTY;
pub unsafe fn interrupt(vector:u64)!u64{return 0;}
pub unsafe fn fixture(slot:usize)!u64{unsafe{
 let owner=((slot as u64+1)<<32)|1;TABLE=&T;try ledger.initialize(TABLE);
 if slot==2{MSI.stage=1;MSI.serial=1;MSI.owner=owner;MSI.incarnation=1;MSI.sequence=1;MSI.pending=1;return msi.token(&MSI);}
 var raw=abi.EMPTY_DEVICE;raw.kind=abi.I8042;var view=abi.EMPTY_DEVICE;try ledger.register(TABLE,&raw,&view);
 var binding=abi.EMPTY_BINDING;try ledger.bind(TABLE,view.token,&raw,abi.PS2,&binding);
 var out=abi.EMPTY_IRQ;try ledger.irq_bind(TABLE,owner,1,1,1,&out);let token=out.token;let delivered=try ledger.irq_signal(TABLE,0x51,&out);return token;
}}
pub unsafe fn alter_owner(slot:usize,wrong:bool)void{unsafe{let owner=((slot as u64+1)<<32)|1;if slot==2{MSI.owner=owner+(wrong as u64);}else{T.interrupts[0].owner=owner+(wrong as u64);}}return;}
pub fn region(which:u64)u64{unsafe{if which==0{return &T as u64;}if which==1{return &MSI as u64;}return &IRQ as u64;}}
pub fn bytes(which:u64)u64{if which==0{return sizeof(ledger.Table) as u64;}if which==1{return sizeof(msi.State) as u64;}return sizeof(abi.Irq) as u64;}
'''
TAIL='''
var TARGET:usize=0;var CAP:u64=0;var SIGNAL_CAP:u64=0;
unsafe fn start_catalog(cfg:usize)!void{unsafe{var s=proc.EMPTY_SNAPSHOT;try procs.start(CATALOG,cfg,cfg,0,&s);try procs.mark_ready(CATALOG,cfg,1);}return;}
unsafe fn setup_inner(slot:usize)!void{unsafe{
 TARGET=slot;CATALOG=smp_service_catalog_storage() as *procs.Catalog;try procs.initialize(CATALOG,1000000);
 try start_catalog(5);try start_catalog(6);try start_catalog(2);try start_catalog(4);
 let p=process(slot);(*p).ready=1;(*p).root=0x200000+slot as u64*4096;(*p).frame=abi.EMPTY;(*p).frame.rip=0x400000;(*p).frame.rsp=0x70000000;(*p).frame.cr3=(*p).root;
 try handles.init(&STATES[slot].table);let object=try device_host.fixture(slot);
 CAP=try handles.install(&STATES[slot].table,handles.INTERRUPT,object,handles.WAIT);SIGNAL_CAP=try handles.install(&STATES[slot].table,handles.INTERRUPT,object,handles.SIGNAL);
 try enable_smp();if smp_project()!=0{return error.Protocol;}
 var out:u64=0;if !(try ud.select(D,0,&out)){return error.Protocol;}try ud.selected_kernel(D,0);
}return;}
export("pf_setup") fn setup(slot:usize)u64{unsafe{match setup_inner(slot){ok=>{return 0;},err(e)=>{return e;},}}}
export("pf_policy") fn policy(op:u64,which:u64)u64{unsafe{
 let f=&(*process(TARGET)).frame;(*f).rax=op;(*f).rdi=CAP;(*f).rsi=0;(*f).rdx=0x70001000;(*f).r10=0;(*f).r8=0;(*f).r9=0;(*f).rflags=0x202;
 if op==3||op==0x73{(*f).rdi=0;(*f).rdx=0;}
 if which==1{(*f).r10=1;}if which==2{(*f).r8=1;}if which==3{(*f).r9=1;}if which==5{(*f).rdi=SIGNAL_CAP;}
 if which==6{(*f).rsi=2;}if which==8{(*f).rsi=1;}if which==9{(*f).rdi=1;}if which==10{(*f).rflags=0;}
 if which==7{device_host.alter_owner(TARGET,true);}
 let result=smp_service_policy(TARGET,257,f as u64);if which==7{device_host.alter_owner(TARGET,false);}return result;
}}
export("pf_region") fn region(which:u64)u64{return device_host.region(which);}
export("pf_bytes") fn bytes(which:u64)u64{return device_host.bytes(which);}
'''
CMAIN=r'''
extern U ABI pf_setup(U),pf_policy(U,U),pf_region(U),pf_bytes(U);
static unsigned char catalog_storage[32768] __attribute__((aligned(64)));static U valid_output=1;
U ABI smp_service_catalog_storage(void){return (U)(uintptr_t)catalog_storage;}
U ABI smp_service_fixture_event(U a,U b,U c){(void)a;(void)b;(void)c;return 0;}
U ABI user_validate_frame(Frame*f){return user_smp_arch_validate((U)(uintptr_t)f,f->w[18]);}
U ABI pf_output(U slot,U va,U size,U write){C((slot==2||slot==4)&&va==0x70001000&&size==64&&write==1);return valid_output;}
U ABI user_bridge_service_policy(U a,U b,U c){(void)a;(void)b;(void)c;return 0;}
U ABI services_pcid_metric(U a){(void)a;return 0;}U ABI services_smp_pcid_metric(U a){(void)a;return 0;}
static U digest(void){U h=0xcbf29ce484222325ULL;for(U i=0;i<3;i++){unsigned char*p=(void*)(uintptr_t)pf_region(i);U n=pf_bytes(i);for(U j=0;j<n;j++)h=(h^p[j])*0x100000001b3ULL;}return h;}
int main(int argc,char**argv){C(argc==2);U slot=!strcmp(argv[1],"msi")?2:4;setup();cpu=0;C(!ue_lock(0));C(!pf_setup(slot));U old=digest();
 C(pf_policy(3,0)==1&&pf_policy(3,9)==0);C(pf_policy(0x93,0)==1&&digest()==old);C(pf_policy(0x93,8)==1&&digest()==old);
 for(U i=1;i<=7;i++){if(i==4)valid_output=0;C(pf_policy(0x93,i)==0);valid_output=1;C(digest()==old);}
 C(pf_policy(0x93,10)==0);C(pf_policy(0x94,0)==0);C(pf_policy(0x92,0)==0);C(pf_policy(0xb6,0)==0);C(pf_policy(0xb0,0)==0);C(pf_policy(0x97,0)==0);
 for(U i=0;i<1000;i++){C(pf_policy(i&1?3:0x93,0)==1);}C(digest()==old);C(!ue_audit());
 printf("poll fast actual policy checks=%u scenario=%s real-ledger/MSI owner/caps/range/const-output,1000classifiedsafe\n",(unsigned)checks,argv[1]);return 0;}
'''
class Tests(unittest.TestCase):
 def test_real_policy_const_backends_and_bad_controls(self):
  source=(BASE/'kernel/user/services.dg').read_text();actual='\n'.join(block(source,n)for n in ('unsafe fn process(', 'unsafe fn managed(', 'pub unsafe fn enable_smp(', 'export("dong_user_smp_project")','export("dong_user_smp_service_policy")'))
  prefix=old.PREFIX.replace('import user.device_host as device_host;','import user.device_host as device_host;import user.devices as devices;import ipc.handles as handles;import lib.device_abi as dev;')
  prefix=prefix.replace('struct State{waiting:u64,started:u64}','struct State{table:handles.Table,waiting:u64,started:u64}').replace('State{waiting:0,started:0}','State{table:handles.EMPTY_TABLE,waiting:0,started:0}').replace('var LAUNCH_FAILED:bool=false;','var LAUNCH_FAILED:bool=false;var GRAPHICS:bool=true;').replace('try retire_one(id,state,status);','').replace('try retire_one(CURRENT,proc.EXITED,73);','')
  entry=(ROOT/'tests/user_current_entry_probe.dg').read_text()+prefix+actual+TAIL
  memory=old.MEMORY+'''unsafe extern "sysv64" fn pf_output(slot:u64,va:u64,size:u64,write:u64)u64;
pub unsafe fn check_range(slot:usize,va:u64,size:usize,write:bool)!void{unsafe{if pf_output(slot as u64,va,size as u64,write as u64)!=1{return error.Invalid;}}return;}pub error Invalid=0x1111;'''
  devices='''module user.devices;pub const CONFIGURATION_OBJECT:u64=0x1234;pub unsafe fn configuration_read_stable(physical:u64)bool{return true;}'''
  host=HOST+block((BASE/'kernel/user/device_host.dg').read_text(),'pub unsafe fn irq_poll_readonly(')
  c=(ROOT/'tests/user_current_entry_probe.c').read_text();c=c.replace(block(c,'U ABI dong_user_smp_project('),'');c=c[:c.index('int main(void)')]+CMAIN
  controls={
   'yield-args-ignored':('policy','(*frame).rdi!=0||','', 'if (*frame).rax==3{'),
   'yield-not-fast':('policy','return 1;','return 0;','if (*frame).rax==3{'),
   'BLOCK-IRQ-fast':('policy','(*frame).r10!=dev.NONBLOCK||','','if (*frame).rax==dev.IRQ_WAIT{'),
   'deadline-IRQ-fast':('policy','(*frame).r8!=0||','','if (*frame).rax==dev.IRQ_WAIT{'),
   'nonzero-unused-IRQ-fast':('policy','||(*frame).r9!=0','','if (*frame).rax==dev.IRQ_WAIT{'),
   'SIGNAL-without-WAIT-fast':('policy','handles.INTERRUPT,handles.WAIT','handles.INTERRUPT,0','if (*frame).rax==dev.IRQ_WAIT{'),
   'whole-output-check-removed':('policy','match memory.check_range(slot,(*frame).rdx,sizeof(dev.Irq),true){ok=>{},err(e)=>{return 0;},}','','if (*frame).rax==dev.IRQ_WAIT{'),
   'wrong-owner-or-stale-fast':('host','return e==0x0512_0006;','return e==0x0512_0006||e==0x0512_0004;',None),
   'preview-publishes-global-IRQ':('host','&snapshot','&IRQ',None),
   'legacy-preview-ACKs':('host','ok=>{return true;},err(e)=>{return e==0x0512_0006;},}\n}}','ok=>{let bad=ledger.irq_ack(TABLE,token,owner,snapshot.sequence);return true;},err(e)=>{return e==0x0512_0006;},}\n}}',None),
   'MSI-preview-ACKs':('host','ok=>{return true;},err(e)=>{return e==0x0512_0006;},}}','ok=>{let bad=msi.acknowledge(&MSI,token,owner,snapshot.sequence);return true;},err(e)=>{return e==0x0512_0006;},}}',None),
  }
  out=ROOT/'build/test/p6-poll-fast-native'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);evidence={};nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
  candidate={}
  files=[BASE/'kernel/user/services.dg',BASE/'kernel/user/device_host.dg',Path(__file__),ROOT/'tests/user_current_entry_probe.c',ROOT/'tests/user_current_entry_probe.dg'];before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files}
  for mode in ('debug','release'):
   for variant in ('normal',*controls):
    d=out/(mode+'-'+variant);stage=d/'kernel';s=entry;h=host
    if variant!='normal':
     kind,a,b,scope=controls[variant]
     if kind=='policy':sub=block(s,scope);self.assertEqual(1,sub.count(a));s=s.replace(sub,sub.replace(a,b))
     else:self.assertGreaterEqual(h.count(a),1);h=h.replace(a,b)
    copy_graph(stage,['user_current_entry_probe'],{**candidate,'user_current_entry_probe':s,'user.memory':memory,'user.devices':devices,'boot.trace_runtime':'module boot.trace_runtime;pub unsafe fn event(a:u64,b:u64,c:u64,d:u64)void{return;}','user.window_broker':old.WINDOWS,'user.device_host':h})
    compiled=compile_file(stage/'user_current_entry_probe.dg',roots=[stage],mode=mode);(d/'probe.asm').write_text(compiled.assembly);(d/'probe.c').write_text(c)
    def run(args,label):
     r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=60);(d/(label+'.json')).write_text(json.dumps(dict(command=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
    objects=[]
    for name,p in [('dong',d/'probe.asm'),('entry',ARCH/'kernel/sched/user_entry.asm'),('legacy',ARCH/'kernel/sched/user_legacy.asm')]:
     obj=d/(name+'.o');r=run([nasm,'-f','win64'if os.name=='nt'else'elf64',*nasm_flags(nasm),'-I',str(ARCH/'include')+os.sep,'-I',str(ROOT/'include')+os.sep,p,'-o',obj],'asm-'+name);self.assertEqual(0,r.returncode,r.stderr);objects.append(obj)
    exe=d/('probe.exe'if os.name=='nt'else'probe');r=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',*([]if os.name=='nt'else['-no-pie']),d/'probe.c',*objects,'-o',exe],'link');self.assertEqual(0,r.returncode,r.stderr)
    for scenario in(('legacy','msi')if variant=='normal'else(('msi',)if variant=='MSI-preview-ACKs'else('legacy',))):
     r=run([exe,scenario],scenario);self.assertEqual(0 if variant=='normal'else 1,r.returncode,r.stdout+r.stderr)
     if variant!='normal':self.assertIn('user CPL3 current-source oracle line',r.stderr)
     evidence[mode+'-'+variant+'-'+scenario]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};self.assertEqual(before,after)
  (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),contract="tracked-current-cpl3-v1",actual_policy_and_preview=True,real_catalog_domain_queue_handles_legacy_irq_and_msi=True,hardware_and_owned_ram_boundary_mocked=True,no_os_build_or_vm=True,source_sha256=after,sources_unchanged=True,evidence=evidence),indent=2)+'\n');print('POLL_FAST_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)


