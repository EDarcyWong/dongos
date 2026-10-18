"""Actual 16K fresh/own_frame and three retirement paths, real raw page tables."""
from __future__ import annotations
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_service_gui_wiring import modules
ROOT=Path(__file__).resolve().parents[1]
STARTUP='''module boot.memory_startup;import mm.paging as paging;import mm.phys_buddy as buddy;
var SPACE:paging.Space=paging.EMPTY_SPACE;var POOL:[128]paging.Table=[paging.Table{entries:[0;512]};128];var META:[128]u8=[0;128];
var ALLOC:buddy.Allocator=buddy.EMPTY_ALLOCATOR;pub struct View{pub pool:u64}var VIEW:View=View{pool:0};
pub fn space_pointer()*paging.Space{unsafe{return &SPACE;}}pub fn allocator_pointer()*buddy.Allocator{unsafe{return &ALLOC;}}
pub fn runtime_pointer()*View{unsafe{return &VIEW;}}
export("cursor_kernel_setup") fn setup()u64{unsafe{SPACE=paging.EMPTY_SPACE;VIEW.pool=&POOL[0] as u64;
 match paging.init(&SPACE,POOL[..],0x10000000,META[..],48,true){ok=>{return 0;},err(e)=>{return e;},}
}}
'''
RESOURCES='''module boot.service_memory;pub struct Block{pub physical:u64,pub virtual:u64,pub pages:usize}
pub error Invalid=0x09000001;var NEXT:u64=0x200000;var SCRATCH:u64=0;
export("cursor_resources_setup") fn setup(pointer:u64)void{unsafe{NEXT=0x200000;SCRATCH=pointer;}return;}
pub unsafe fn reserve(pages:usize,alignment:usize,out:*Block)!void{unsafe{
 if pages!=1||alignment!=1{return error.Invalid;}*out=Block{physical:NEXT,virtual:0,pages:1};NEXT+=4096;
}return;}
pub unsafe fn allocate(pages:usize,alignment:usize,out:*Block)!void{unsafe{
 if pages!=11||alignment!=1||SCRATCH==0{return error.Invalid;}*out=Block{physical:0x20000000,virtual:SCRATCH,pages:pages};
}return;}
'''
DEVICES='''module boot.device_memory;pub unsafe extern "sysv64" fn runtime_invalidate(address:u64)void;
pub unsafe fn runtime_flush_root()void{return;}
'''
def copy_graph(stage,overrides):
 paths=modules();seen=set()
 def visit(name):
  if name in seen:return
  seen.add(name);text=overrides[name] if name in overrides else paths[name].read_text(encoding='utf-8')
  path=stage/(name.replace('.','/')+'.dg');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
  for imported in re.findall(r'\bimport\s+([\w.]+)\s+as\s+',text):visit(imported)
 visit('user.memory')
class UserReuseCursorTests(unittest.TestCase):
 def test_actual_fresh_linear_scan_retirement_rewind_and_held(self):
  paths=[ROOT/p for p in ('kernel/user/memory.dg','kernel/mm/paging.dg','kernel/mm/phys_buddy.dg','tests/user_reuse_cursor_fixture.dg','tests/user_reuse_cursor_probe.c','tests/test_user_reuse_cursor.py')]
  before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};source=paths[0].read_text()
  variants={
   'old-zero-start':('var reusable:usize=REUSE_FROM;','var reusable:usize=0;','linear-new',None),
   'no-selected-advance':('REUSE_FROM=reusable+1;','','linear-reuse',None),
   'no-scan-end-advance':('REUSE_FROM=FRAME_COUNT;','','linear-new',None),
   'no-stage-rewind':('if index<REUSE_FROM{REUSE_FROM=index;}','','stage','unsafe fn abort_candidate('),
   'no-unshare-rewind':('if index<REUSE_FROM{REUSE_FROM=index;}','','unshare','unsafe fn unshare_recycle('),
   'no-destroy-rewind':('if index<REUSE_FROM{REUSE_FROM=index;}','','destroy','pub unsafe fn destroy('),
   'reuse-held':('if *recycled(reusable)==1 {','if *recycled(reusable)!=0 {','held',None),
   'abort-held':('*recycled(index)==2||referenced_frame(index)','false||referenced_frame(index)','stage',None),
   'ignore-failstop':('if UNSHARE_FAILED{return error.InvalidState;}','','held',None),
  }
  out=ROOT/'build/test/user-reuse-cursor'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);evidence=[]
  nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
  def command(args,d,name):
   r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(name+'.json')).write_text(json.dumps(dict(command=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
  for mode in ('debug','release'):
   for variant in ('normal',*variants):
    d=out/(mode+'-'+variant);d.mkdir();text=source
    if variant!='normal':
     old,new,scenario,scope=variants[variant]
     if scope:
      from tests.test_service_ipc_cancellation import block
      body=block(text,scope);self.assertEqual(1,body.count(old));text=text.replace(body,body.replace(old,new))
     else:self.assertEqual(1,text.count(old));text=text.replace(old,new)
    self.assertEqual(1,text.count('while reusable<FRAME_COUNT {'));text=text.replace('while reusable<FRAME_COUNT {','while reusable<FRAME_COUNT {TEST_SCAN_COUNT+=1;cursor_scan_event(TEST_SCAN_COUNT);')
    text=text.replace('pub const ALIASES: u64 = 0xffff_d000_0000_0000;','pub var ALIASES: u64 = 0;')+'\n'+paths[3].read_text()
    copy_graph(d/'source',{'user.memory':text,'boot.memory_startup':STARTUP,'boot.service_memory':RESOURCES,'boot.device_memory':DEVICES})
    c=compile_file(d/'source/user/memory.dg',roots=[d/'source'],mode=mode);asm=d/'probe.asm';asm.write_text(c.assembly)
    mocked={'__dong_panic','user_current_root','user_pcid_flush_all','user_pcid_unbind','runtime_invalidate','runtime_copy_bytes','user_pcid_invalidate_root','cursor_scan_event'}
    externs={m.group(1).lstrip('$') for m in re.finditer(r'^extern (\$?\w+)',c.assembly,re.M)}-mocked
    stub=d/'unused.asm';stub.write_text('bits 64\nsection .text\n'+''.join('global $'+x+'\n$'+x+': ud2\n' for x in sorted(externs)));objects=[]
    for label,file in (('probe',asm),('unused',stub)):
     obj=d/(label+'.o');objects.append(obj);r=command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),file,'-o',obj],d,'assemble-'+label);self.assertEqual(0,r.returncode,r.stderr)
    exe=d/('probe.exe' if os.name=='nt' else 'probe');r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-strict-aliasing',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),paths[4],*objects,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
    scenarios=('linear-new','linear-reuse','stage','unshare','destroy','held') if variant=='normal' else (variants[variant][2],)
    for scenario in scenarios:
     r=command([exe,scenario],d,scenario);self.assertEqual(0 if variant=='normal' else 1,r.returncode,r.stdout+r.stderr)
     self.assertIn('reuse cursor native checks passed' if variant=='normal' else 'reuse cursor native failed line',r.stdout if variant=='normal' else r.stderr)
     evidence.append(dict(mode=mode,variant=variant,scenario=scenario,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr))
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};self.assertEqual(before,after)
  (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_sha256=after,sources_unchanged=True,real_fresh_own_frame_and_three_retire_paths=True,real_paging=True,scan_counter_only_instrumentation=True,hardware_alias_arena_boundaries_mocked=True,actual_guest_boots=0,evidence=evidence),indent=2)+'\n');print('USER_REUSE_CURSOR_EVIDENCE',out)
