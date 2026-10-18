"""Execute exact production IPC dispatch/retirement fragments with real core.

Only the authority and memory boundaries are mocked. Candidate corrections
stay in the private output tree; this never modifies production or boots VMs.
"""
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]


def block(source,needle):
    start=source.index(needle);opening=source.index('{',start);level=1;end=opening+1
    while level:
        if source[end]=='{':level+=1
        elif source[end]=='}':level-=1
        end+=1
    return source[start:end]


PREFIX='''module service_ipc_fixture;
import ipc.core as ipc;import ipc.handles as handles;import user.abi as abi;
import lib.process_abi as proc;import service_ipc_memory as memory;
import user.processes as procs;import ipc.cap_notify as capnotify;
pub error Protocol=0x050b_0002;pub error InvalidCall=0x050b_0001;
const COUNT:usize=16;const NONE:usize=16;var ACTIVE:usize=16;var CURRENT:usize=0;
struct State {waiting:u64,ticket:u64,reply_pointer:u64,receive_pointer:u64,table:handles.Table}
const EMPTY_STATE:State=State{waiting:0,ticket:0,reply_pointer:0,receive_pointer:0,table:handles.EMPTY_TABLE};
struct Process{frame:abi.Frame}var PROCESSES:[16]Process=[Process{frame:abi.EMPTY};16];
var STATES:[16]State=[EMPTY_STATE;16];var ALIVE:[16]bool=[true;16];
var ENDPOINTS:[16]ipc.Endpoint=[ipc.EMPTY_ENDPOINT;16];var CANCELED:[16]u64=[0;16];
struct Report{calls:u64,replies:u64}var INFO:Report=Report{calls:0,replies:0};
var BUFFER:[64]u8=[0;64];
unsafe fn process(id:usize)*Process{unsafe{return &PROCESSES[id];}}
unsafe fn managed(id:usize)bool{unsafe{return id<16&&ALIVE[id];}}
unsafe fn endpoint(token:u64,rights:u64)!usize{if token==0||token>16{return error.Protocol;}return (token-1) as usize;}
unsafe fn runnable()!usize{unsafe{var step:usize=1;while step<ACTIVE{
 let next=(CURRENT+step)%ACTIVE;if managed(next)&&STATES[next].waiting==0{return next;}step+=1;
 }if managed(CURRENT)&&STATES[CURRENT].waiting==0{return CURRENT;}}return error.Protocol;}
'''
SUFFIX='''
export("fixture_initialize") fn initialize()u64{unsafe{
 var i:usize=0;while i<16{STATES[i]=EMPTY_STATE;ALIVE[i]=true;CANCELED[i]=0;
 PROCESSES[i].frame=abi.EMPTY;ENDPOINTS[i]=ipc.EMPTY_ENDPOINT;
 match ipc.endpoint_init(&ENDPOINTS[i],i as u64+1,i as u64+1){ok=>{},err(e)=>{return e;},}i+=1;}
 INFO.calls=0;INFO.replies=0;CURRENT=0;}return 0;}
export("fixture_waiting") fn waiting(id:usize,value:u64)void{unsafe{STATES[id].waiting=value;}return;}
export("fixture_perform") fn execute(actor:usize,frame:*abi.Frame,next:*u64)u64{unsafe{
 CURRENT=actor;match perform(frame){ok(value)=>{*next=value as u64;return 0;},err(e)=>{return e;},}}}
export("fixture_get") fn get(which:u64,id:usize)u64{unsafe{
 if which==0{return STATES[id].waiting;}if which==1{return CANCELED[id];}
 if which==2{return ENDPOINTS[id].state;}if which==3{return ENDPOINTS[id].caller;}
 if which==4{return INFO.replies;}if which==5{return INFO.calls;}
 if which==6{return PROCESSES[id].frame.rax;}if which==7{return ENDPOINTS[id].live;}
 return ENDPOINTS[id].token;}}
'''
MEMORY='''module service_ipc_memory;
pub error Invalid=0x0406_0004;
pub unsafe fn check_range(id:usize,address:u64,length:usize,write:bool)!void{
 if id>=16||address==0||length!=64{return error.Invalid;}return;}
pub unsafe fn copy_in(id:usize,address:u64,output:[]u8)!void{unsafe{
 try check_range(id,address,output.len,false);var i:usize=0;while i<output.len{output[i]=*((address as *const u8)+i);i+=1;}}return;}
pub unsafe fn copy_out(id:usize,address:u64,input:[]const u8)!void{unsafe{
 try check_range(id,address,input.len,true);var i:usize=0;while i<input.len{*((address as *u8)+i)=input[i];i+=1;}}return;}
'''



def fixture_graph(stage,overrides):
    paths={}
    for base in ('kernel','services','lang/std'):
        for path in (ROOT/base).rglob('*.dg'):
            match=re.search(r'^module\s+([\w.]+);',path.read_text(encoding='utf-8'),re.M)
            if match:paths[match[1]]=path
    seen=set()
    def visit(name):
        if name in seen:return
        seen.add(name);body=overrides[name]if name in overrides else paths[name].read_text(encoding='utf-8')
        target=stage/(name.replace('.','/')+'.dg');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(body,encoding='utf-8')
        for imported in re.findall(r'\bimport\s+([\w.]+)\s+as\s+',body):visit(imported)
    visit('service_ipc_fixture')

class Tests(unittest.TestCase):
    def test_dispatch_cancellation_and_nested_wait_native(self):
        names=('kernel/user/services.dg','kernel/ipc/core.dg','kernel/ipc/handles.dg','kernel/user/abi.dg',
               'tests/service_ipc_cancellation_probe.c','tests/test_service_ipc_cancellation.py')
        before={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
        out=ROOT/'build/test/service-ipc-cancellation'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
        source=(ROOT/names[0]).read_text();cases=[block(source,'if code=='+code+' {') for code in ('0x22','0x23','0x24 || code==0x26')]
        detach=block(source,'var ep:usize=0;while ep<ACTIVE{');accept=block(source,'unsafe fn accept(id:usize)!void')
        prefix=PREFIX+'var SMP_ENABLED:bool=false;var CATALOG:*procs.Catalog=null;\nvar CAP_OFFERS:[16]capnotify.Delivery=[capnotify.EMPTY_DELIVERY;16];\n'+source[source.index('// One trusted request snapshot'):source.index('var WAIT_AFTER:')]+'\n'+'\n'.join(block(source,'unsafe fn '+name+'(')for name in ('owner_key','pending_call_enqueue','pending_call_finish','pending_call_pump','pending_calls_departed'))+'\n'
        raw=prefix+accept+'\nunsafe fn perform(frame:*abi.Frame)!usize{unsafe{let code=(*frame).rax;\n'+'\n'.join(cases)+'\n}return error.InvalidCall;}\n'
        raw+='unsafe fn retire_impl(id:usize)!void{unsafe{ALIVE[id]=false;STATES[id].waiting=9;'+detach+'}return;}\n'
        raw+='export("fixture_retire") fn retire(id:usize)u64{unsafe{match retire_impl(id){ok=>{return 0;},err(e)=>{return e;},}}}\n'+SUFFIX
        changes={
          'blocked-owner':('return owner;','if STATES[owner].waiting==0{return owner;}return try runnable();'),
          'pending-tombstone':('CANCELED[ep]=ENDPOINTS[ep].token;INFO.replies+=1;',
            'if ENDPOINTS[ep].state==ipc.ACCEPTED{if CANCELED[ep]!=0{return error.Protocol;}CANCELED[ep]=ENDPOINTS[ep].token;}INFO.replies+=1;'),
          'receive-abandon':('STATES[CURRENT].receive_pointer=(*frame).rsi;',
            'CANCELED[id]=0;STATES[CURRENT].receive_pointer=(*frame).rsi;'),
        }
        # Record an honest result for the frozen production fragments, whether
        # the parent has or has not landed its independent repair yet.
        fixed=raw;missing=[]
        for label,(old,new) in changes.items():
            if label=='blocked-owner' and new in fixed:continue
            if label=='pending-tombstone' and 'ENDPOINTS[ep].state==ipc.ACCEPTED' in detach:continue
            if label=='receive-abandon' and 'CANCELED[id]=0;' in cases[1]:continue
            self.assertEqual(1,fixed.count(old),label);fixed=fixed.replace(old,new);missing.append(label)
        variants={'production':raw,'candidate':fixed}
        for label,(old,new) in changes.items():
            if new in fixed:variants['omit-'+label]=fixed.replace(new,old)
        evidence={}
        def command(argv,d,label):
            argv=list(map(str,argv));result=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=60)
            (d/(label+'.json')).write_text(json.dumps(dict(argv=argv,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr),indent=2)+'\n')
            return result
        for mode in ('debug','release'):
            for variant,text in variants.items():
                d=out/(mode+'-'+variant);d.mkdir();(d/'service_ipc_fixture.dg').write_text(text);(d/'service_ipc_memory.dg').write_text(MEMORY)
                fixture_graph(d/'source',{'service_ipc_fixture':text,'service_ipc_memory':MEMORY,'user.shared_objects':'module user.shared_objects;\nimport ipc.shared_core as core;import ipc.handles as handles;\npub unsafe extern "sysv64" fn fixture_boundary_fail(code:u64)void;\npub fn tagged(identity:u64)bool{return core.tagged(identity);}\n// No generic backing is installed in this legacy IPC/GUI fixture. Never\n// accept a dynamic reference and never quietly implement its commit hooks.\npub unsafe fn check_ref(identity:u64,increase:bool)!void{return error.handles.Denied;}\npub unsafe fn retain(identity:u64)void{unsafe{fixture_boundary_fail(0x7fff01);}return;}\npub unsafe fn drop(identity:u64)void{unsafe{fixture_boundary_fail(0x7fff02);}return;}\n'})
                compilation=compile_file(d/'source/service_ipc_fixture.dg',roots=[d/'source'],mode=mode)
                asm=d/'probe.asm';asm.write_text(compilation.assembly);obj=d/'probe.o';fmt='win64' if os.name=='nt' else 'elf64'
                result=command([nasm,'-f',fmt,*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,result.returncode,result.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe')
                result=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),ROOT/names[4],obj,'-o',exe],d,'link');self.assertEqual(0,result.returncode,result.stderr)
                result=command([exe],d,'execute');expected=0 if variant=='candidate' or (variant=='production' and not missing) else 1
                self.assertEqual(expected,result.returncode,result.stdout+result.stderr)
                evidence[mode+'-'+variant]=dict(expected_returncode=expected,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
        after={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names};self.assertEqual(before,after)
        (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_sha256=after,sources_unchanged=True,
          frozen_production_missing_repairs=missing,production_fragments_executed=True,real_ipc_core_executed=True,
          authority_and_memory_boundary_mocked=True,actual_vmware_boots=0,actual_qemu_boots=0,evidence=evidence),indent=2)+'\n')
        print('SERVICE_IPC_CANCELLATION_EVIDENCE',out)


if __name__=='__main__':unittest.main(verbosity=2)
