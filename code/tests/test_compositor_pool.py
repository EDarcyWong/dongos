"""Per-owner compositor pool, true ELF/paging/retirement plus independent VA oracle."""
from __future__ import annotations
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_service_ipc_cancellation import block
from tests.test_user_reuse_cursor import copy_graph,STARTUP,DEVICES
ROOT=Path(__file__).resolve().parents[1]
MEMORY_ROOT=Path(os.environ.get('DONGOS_COMPOSITOR_MEMORY_ROOT',str(ROOT))).resolve()
SOURCE=MEMORY_ROOT/'kernel/user/memory.dg'
def source_name(path):
 try:return str(path.relative_to(ROOT))
 except ValueError:return str(path)
RESOURCES='''module boot.service_memory;pub struct Block{pub physical:u64,pub virtual:u64,pub pages:usize}
pub error Invalid=0x09000001;var NEXT:u64=0x200000;
unsafe extern "sysv64" fn cpp_allocate(pages:u64,alignment:u64,out:*Block)u64;
pub unsafe fn allocate(pages:usize,alignment:usize,out:*Block)!void{unsafe{if cpp_allocate(pages as u64,alignment as u64,out)!=0{return error.Invalid;}}return;}
pub unsafe fn reserve(pages:usize,alignment:usize,out:*Block)!void{unsafe{if pages!=1||alignment!=1{return error.Invalid;}*out=Block{physical:NEXT,virtual:0,pages:1};NEXT+=4096;}return;}
'''
class CompositorPoolTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.out=ROOT/'build/test/compositor-pool128-native'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
  cls.paths=[SOURCE,*[ROOT/p for p in ('kernel/mm/paging.dg','kernel/user/entropy.dg','kernel/user/window_broker.dg','services/lib/window_broker_abi.dg','tests/compositor_pool_fixture.dg','tests/compositor_pool_probe.c','tests/test_compositor_pool.py','tests/test_user_reuse_cursor.py')]]
  cls.before={source_name(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths};(cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
 @classmethod
 def tearDownClass(cls):
  after={source_name(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
  if after!=cls.before:raise AssertionError('compositor pool input changed during verification')
 def command(self,args,d,name):
  r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=120);(d/(name+'.json')).write_text(json.dumps(dict(command=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
 def native(self,variant='normal'):
  variants={
   'no-desktop-limit':('POOL_LIMITS[3]=COMPOSITOR_POOL_PAGES;','POOL_LIMITS[3]=POOL_PAGES;','budget',None),
   'wrong-static-storage':('return DYNAMIC_TABLES[id]+index;','return &TABLES[0][index];','lifecycle',None),
   'wrong-static-root':('var pool_physical=DYNAMIC_PHYSICAL[id];','var pool_physical=KERNEL_PHYSICAL;','budget',None),
   'short-reference-scan':('while table<pool_pages(id) {','while table<POOL_PAGES {','lifecycle','unsafe fn referenced('),
   'short-destroy-collection':('while table<pool_pages(id) {','while table<POOL_PAGES {','lifecycle','pub unsafe fn destroy('),
   'short-destroy-clear':('while table<pool_pages(id) {','while table<POOL_PAGES {','lifecycle','pub unsafe fn destroy('),
   'short-abort-clear':('while table<pool_pages(id){','while table<POOL_PAGES{','abort','unsafe fn abort_candidate('),
  }
  for mode in ('debug','release'):
   d=self.out/(mode+'-'+variant);d.mkdir();text=SOURCE.read_text()
   if variant!='normal':
    if variant=='short-reference-scan' and 'var FRAME_BUCKETS:' in text:
     variants[variant]=('while table<pool_pages(id){','while table<POOL_PAGES{','lifecycle','unsafe fn reference_batch_inner(')
    old,new,scenario,scope=variants[variant]
    if scope:
     body=block(text,scope);count=body.count(old)
     if variant.startswith('short-destroy'):
      self.assertEqual(2,count);pos=body.index(old) if variant.endswith('collection') else body.rindex(old);changed=body[:pos]+body[pos:].replace(old,new,1)
     else:self.assertEqual(1,count);changed=body.replace(old,new)
     text=text.replace(body,changed)
    else:self.assertEqual(1,text.count(old));text=text.replace(old,new)
   text=text.replace('pub const ALIASES: u64 = 0xffff_d000_0000_0000;','pub var ALIASES: u64 = 0;')+'\n'+(ROOT/'tests/compositor_pool_fixture.dg').read_text()
   paging=(ROOT/'kernel/mm/paging.dg').read_text(encoding='utf-8')+'\npub unsafe fn cp_used(s:*const Space)u64{unsafe{return (*s).used_total as u64;}}\npub unsafe fn cp_count(s:*const Space)u64{unsafe{return (*s).pool_count as u64;}}\n'
   copy_graph(d/'source',{'user.memory':text,'boot.memory_startup':STARTUP.replace('cursor_kernel_setup','cp_kernel_setup'),'boot.service_memory':RESOURCES,'boot.device_memory':DEVICES,'mm.paging':paging})
   c=compile_file(d/'source/user/memory.dg',roots=[d/'source'],mode=mode);asm=d/'probe.asm';asm.write_text(c.assembly)
   mocked={'__dong_panic','user_current_root','user_pcid_bind','user_pcid_flush_all','user_pcid_unbind','runtime_invalidate','runtime_copy_bytes','user_pcid_invalidate_root','cpp_allocate'}
   externs={m.group(1).lstrip('$') for m in re.finditer(r'^extern (\$?\w+)',c.assembly,re.M)}-mocked
   stub=d/'unused.asm';stub.write_text('bits 64\nsection .text\n'+''.join('global $'+x+'\n$'+x+': ud2\n' for x in sorted(externs)));objects=[];nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
   for label,file in (('probe',asm),('unused',stub)):
    obj=d/(label+'.o');objects.append(obj);r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),file,'-o',obj],d,'assemble-'+label);self.assertEqual(0,r.returncode,r.stderr)
   metadata_pages=128 if 'var FRAME_BUCKETS:' in text else 109
   exe=d/('probe.exe' if os.name=='nt' else 'probe');r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-strict-aliasing','-DDONGOS_FRAME_METADATA_PAGES='+str(metadata_pages),*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),ROOT/'tests/compositor_pool_probe.c',*objects,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
   scenarios=('legacy','budget','lifecycle','abort','allocation-failure') if variant=='normal' else (variants[variant][2],)
   for scenario in scenarios:
    r=self.command([exe,scenario],d,scenario);self.assertEqual(0 if variant=='normal' else 1,r.returncode,r.stdout+r.stderr)
    self.assertIn('compositor pool native checks passed' if variant=='normal' else 'compositor pool native failed line',r.stdout if variant=='normal' else r.stderr)
 def test_actual_pool_budget_raw_high_pte_and_lifecycle(self):self.native()
 def test_real_bad_pool_sources_are_rejected(self):
  for variant in ('no-desktop-limit','wrong-static-storage','wrong-static-root','short-reference-scan','short-destroy-collection','short-destroy-clear','short-abort-clear'):self.native(variant)
