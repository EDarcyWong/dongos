"""Production GUI/IPC/lifecycle fragments, real catalog/caps/IPC/broker."""
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_service_ipc_cancellation import block
ROOT=Path(__file__).resolve().parents[1]
def modules():
    result={}
    for base in ('kernel','services','lang/std','lang/examples'):
        for path in (ROOT/base).rglob('*.dg'):
            text=path.read_text(encoding="utf-8");match=re.search(r'^module\s+([\w.]+);',text,re.M)
            if match:result[match[1]]=path
    return result
def copy_graph(stage,names,overrides):
    paths=modules();seen=set()
    def visit(name):
        if name in seen:return
        seen.add(name);text=overrides[name] if name in overrides else paths[name].read_text(encoding="utf-8")
        path=stage/(name.replace('.','/')+'.dg');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
        for imported in re.findall(r'\bimport\s+([\w.]+)\s+as\s+',text):visit(imported)
    for name in names:visit(name)
class Tests(unittest.TestCase):
    def test_exact_dispatch_scope_output_and_teardown(self):
        names=('kernel/user/services.dg','kernel/user/processes.dg','kernel/user/window_broker.dg','kernel/ipc/core.dg','kernel/ipc/handles.dg','services/lib/process_abi.dg','services/lib/window_broker_abi.dg','services/lib/window_abi.dg','tests/service_gui_fixture.dg','tests/service_gui_memory.dg','tests/service_gui_probe.c','tests/test_service_gui_wiring.py')
        before={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
        source=(ROOT/names[0]).read_text(encoding="utf-8")
        functions=('process','authority','endpoint','managed','manager','close_table','owner_key','gui_role','accepted_caller','window_server','window_call','revoke_loaded','retire_one','discard_preloaded','retire','image_name','probe_pages','channels','abort_launch','launch','install_identity','BOOTs_common','BOOTs_region','BOOTs_manager','pending_call_enqueue','pending_call_finish','pending_call_pump','pending_calls_departed','accept','cap_departed')
        fragments='\n'.join(block(source,'unsafe fn '+name+'(') for name in functions)
        selected=[block(source,'if code==0x25{'),block(source,'if code==0x2d{'),block(source,'if code==0x67{')]
        perform='''unsafe fn perform(frame:*abi.Frame)!usize{unsafe{let code=(*frame).rax;
if code>=window.ALLOCATE&&code<=window.PEER{return try window_call(frame);}
'''+ '\n'.join(selected)+ '\n}return error.InvalidCall;}\n'
        fixture=(ROOT/names[8]).read_text(encoding="utf-8").replace('// PRODUCTION_FUNCTIONS',source[source.index('// One trusted request snapshot'):source.index('var WAIT_AFTER:')]+'\n'+fragments+'\n'+perform).replace('// PRODUCTION_FATAL',block(source,'if LAUNCH_FAILED||memory.STAGE_FAILED||memory.UNSHARE_FAILED'))
        catalog=(ROOT/names[1]).read_text(encoding="utf-8")
        for function in ('start','terminate'):
            needle='pub unsafe fn '+function+'(';self.assertEqual(1,catalog.count(needle));catalog=catalog.replace(needle,'unsafe fn actual_'+function+'(')
        catalog+='''
pub unsafe fn start(c:*Catalog,id:usize,slot:usize,argument:u64,out:*abi.Snapshot)!void{unsafe{try actual_start(c,id,slot,argument,out);let event=gui_catalog_event(33,slot as u64,id as u64);}return;}
pub unsafe fn terminate(c:*Catalog,slot:usize,state:u64,status:u64)!void{unsafe{try actual_terminate(c,slot,state,status);let event=gui_catalog_event(3,slot as u64,state);}return;}
unsafe extern "sysv64" fn gui_catalog_event(kind:u64,a:u64,b:u64)u64;
'''
        hardware={
          'user.memory':(ROOT/names[9]).read_text(encoding="utf-8"),
          'user.processes':catalog,
          'boot.power_startup':'module boot.power_startup;pub const POWER_OBJECT:u64=0x08000001;',
          'arch.x86_64':'module arch.x86_64;pub unsafe fn read_tsc()u64{return 1000;}',
          'user.devices':'''module user.devices;pub const CONFIGURATION_OBJECT:u64=10;pub const DMA_OBJECT:u64=20;pub const CONSOLE_OBJECT:u64=30;
pub fn region_base()u64{return 0;}pub fn region_first()u64{return 0;}pub fn region_last()u64{return 0;}
pub unsafe fn quarantine(id:usize)!void{return;}
pub unsafe extern "sysv64" fn gui_event(kind:u64,a:u64,b:u64,c:u64,d:u64)u64;
pub unsafe fn xhci_enable(id:usize,owner:u64,incarnation:u64)!void{unsafe{if gui_event(41,id as u64,owner,incarnation,0)!=0{return error.Invalid;}}return;}
pub error Invalid=0x0f430001;''',
          'user.device_host':'''module user.device_host;pub var XHCI_OWNER:u64=0;pub error Denied=0x0f440001;
unsafe extern "sysv64" fn gui_event(kind:u64,a:u64,b:u64,c:u64,d:u64)u64;
pub unsafe fn revoke_owner(owner:u64)!void{unsafe{let event=gui_event(42,owner,0,0,0);}return;}
pub unsafe fn xhci_attach(id:usize,owner:u64,generation:u64)!void{unsafe{if XHCI_OWNER!=0{return error.Denied;}
if gui_event(40,id as u64,owner,generation,0)!=0{return error.Denied;}XHCI_OWNER=owner;}return;}''',
          'user.desktop':'''module user.desktop;import lib.window_broker_abi as window;
pub const INPUT_QUEUE:u64=0x54000000;pub unsafe fn recreate(id:usize)!void{return;}
pub unsafe fn map_client_font(id:usize)!void{return;}
unsafe extern "sysv64" fn gui_event(kind:u64,a:u64,b:u64,c:u64,d:u64)u64;
pub unsafe fn client_font(id:usize,owner:u64,epoch:u64,pixels:u64,out:*window.Font)!void{unsafe{
if gui_event(23,id as u64,owner,epoch,pixels)!=0{return error.Invalid;}
*out=window.Font{version:1,owner:owner,epoch:epoch,client_address:0x72000000,server_address:0x72000000,bytes:4096,pixels:pixels,scale:256,glyphs:42};}return;}
pub error Invalid=0x0f420001;''',
          'boot.service_memory':'''module boot.service_memory;import exec.bundle as bundle;pub struct Block{pub physical:u64,pub virtual:u64,pub pages:usize}
var IMAGE:[1]u8=[0x7f];pub unsafe fn find(name:[]const u8,out:*bundle.Contents)!void{unsafe{*out=bundle.Contents{pointer:&IMAGE[0],length:1};}return;}
pub unsafe fn allocate(pages:usize,alignment:usize,out:*Block)!void{return error.Invalid;}pub error Invalid=0x0f010001;''',
        }
        hardware['user.shared_objects']='module user.shared_objects;\nimport ipc.shared_core as core;import ipc.handles as handles;\npub unsafe extern "sysv64" fn fixture_boundary_fail(code:u64)void;\npub fn tagged(identity:u64)bool{return core.tagged(identity);}\n// No generic backing is installed in this legacy IPC/GUI fixture. Never\n// accept a dynamic reference and never quietly implement its commit hooks.\npub unsafe fn check_ref(identity:u64,increase:bool)!void{return error.handles.Denied;}\npub unsafe fn retain(identity:u64)void{unsafe{fixture_boundary_fail(0x7fff01);}return;}\npub unsafe fn drop(identity:u64)void{unsafe{fixture_boundary_fail(0x7fff02);}return;}\n\nimport user.memory as memory;import lib.shared_abi as abi;\npub fn bound_owner(id:usize)u64{unsafe{if id>=16{return 0;}return memory.SHARED.owners[id];}}\npub unsafe fn bind_owner(id:usize,owner:u64)!void{unsafe{try core.bind_owner(&memory.SHARED,id,owner);}return;}\npub unsafe fn owner_gone(id:usize,owner:u64)!void{unsafe{\n if !core.owner_valid(id,owner)||memory.SHARED.owners[id]!=owner||(*(memory.processes()+id)).ready!=0{return error.abi.Stale;}\n var m:usize=0;while m<4{if memory.SHARED.maps[id][m].state!=0{return error.abi.Held;}m+=1;}\n memory.SHARED.owners[id]=0;\n}return;}\n'
        hardware['sched.user_bridge']='module sched.user_bridge;import user.shared_objects as shared;\npub unsafe fn retire(id:usize)!void{unsafe{shared.fixture_boundary_fail(0x7fff03);}return error.Invalid;}\npub error Invalid=0x7fff0003;\n'
        hardware['boot.trace_runtime']='module boot.trace_runtime;import boot.trace as trace;import user.shared_objects as shared;\nvar KINDS:[80]u64=[0;80];var SUBJECTS:[80]u64=[0;80];var GENERATIONS:[80]u64=[0;80];var DETAILS:[80]u64=[0;80];var USED:usize=0;\n// Host fixture records trusted hook arguments. It makes no TSC/boot-time claim.\npub unsafe fn event(kind:u64,configuration:u64,generation:u64,detail:u64)void{unsafe{\n if USED>=80||configuration>=32||generation==0||(kind!=trace.SERVICE_START&&kind!=trace.SERVICE_STOP){shared.fixture_boundary_fail(0x7fff04);return;}\n KINDS[USED]=kind;SUBJECTS[USED]=configuration;GENERATIONS[USED]=generation;DETAILS[USED]=detail;USED+=1;\n}return;}\n'
        hardware['user.device_host']=hardware['user.device_host'].replace('pub var XHCI_OWNER:u64=0;','pub var XHCI_OWNER:u64=0;pub var PCI_FAILED:bool=false;')
        for name in ('user.devices','user.device_host','user.desktop'):
            text=hardware[name].replace('module '+name+';','module '+name+';import user.memory as memory;')
            text=re.sub(r'(?:pub )?unsafe extern "sysv64" fn gui_event\([^;]+;', '', text)
            hardware[name]=text.replace('gui_event(','memory.gui_event(')
        mutations={
          'missing-overlap-check':('if (*frame).rsi<(*frame).rdx+8&&(*frame).rdx<(*frame).rsi+64{return error.Protocol;}','if false{return error.Protocol;}'),
          'allocate-before-output-precheck':('try memory.check_range(CURRENT,(*frame).r9,sizeof(window.Lease),true);',''),
          'physical-gui-role':('let cfg=procs.current(CATALOG,id);if cfg<14||cfg>17{return 0;}','let cfg=id as u64;if cfg<14||cfg>17{return 0;}'),
          'stale-incarnation-role':('||state.process!=((incarnation<<8)|(id as u64+1))','||false'),
          'destroy-before-alias-withdrawal':('    // Withdraw every shared alias while both roots still exist.','    try revoke_loaded(id,incarnation);\n    // Withdraw every shared alias while both roots still exist.'),
          'ordinary-takes-reserved13':('while slot<COUNT&&(slot==13||(*process(slot)).ready!=0','while slot<COUNT&&((*process(slot)).ready!=0'),
          'early-xhci-attach':None,
          'ignore-unshare-fatal':('if LAUNCH_FAILED||memory.STAGE_FAILED||memory.UNSHARE_FAILED||memory.RESOURCE_FAILED||memory.OBJECT_FAILED||device_host.PCI_FAILED||windows.FAILED{','if false{'),
        }
        scenarios=('nonblock','windows','roles','teardown','teardown-fail','teardown-server-fail','launch')
        out=ROOT/'build/test/service-gui-wiring'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);evidence={}
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
        def command(args,d,label):
            args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
            (d/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
        for mode in ('debug','release'):
            for variant in ('normal',*mutations):
                d=out/(mode+'-'+variant);stage=d/'source';text=fixture
                if variant=='early-xhci-attach':
                    line='if id==13{try device_host.xhci_attach(id,((id as u64+1)<<32)|generation,generation);}'
                    self.assertEqual(1,text.count(line));text=text.replace(line,'');text=text.replace('    let boot_page=try memory.anonymous(id,BOOT_ADDRESS);','    '+line+'\n    let boot_page=try memory.anonymous(id,BOOT_ADDRESS);')
                elif variant!='normal':old,new=mutations[variant];self.assertEqual(1,text.count(old));text=text.replace(old,new)
                overrides=dict(hardware);overrides['service_gui_fixture']=text;copy_graph(stage,['service_gui_fixture'],overrides)
                compiled=compile_file(stage/'service_gui_fixture.dg',roots=[stage],mode=mode)
                asm=d/'probe.asm';asm.write_text(compiled.assembly);obj=d/'probe.o';r=command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe');r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),ROOT/names[10],obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                runs=scenarios if variant=='normal' else ({'missing-overlap-check':'nonblock','allocate-before-output-precheck':'windows','physical-gui-role':'windows','stale-incarnation-role':'windows','destroy-before-alias-withdrawal':'teardown','ordinary-takes-reserved13':'launch','early-xhci-attach':'launch','ignore-unshare-fatal':'teardown-fail'}[variant],)
                for scenario in runs:
                    r=command([exe,scenario],d,scenario);self.assertEqual(0 if variant=='normal' else 1,r.returncode,r.stdout+r.stderr)
                    evidence[mode+'-'+variant+'-'+scenario]={key:getattr(r,key) for key in ('returncode','stdout','stderr')}
        after={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names};self.assertEqual(before,after)
        (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,sources_unchanged=True,source_sha256=after,production_fragments_executed=True,real_catalog_caps_ipc_broker=True,memory_and_hardware_boundaries_mocked=True,hardware_io=False,evidence=evidence),indent=2)+'\n')
        print('SERVICE_GUI_WIRING_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
