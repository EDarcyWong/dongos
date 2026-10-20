"""Coherent retained128-page BSP pool, actual raw PTE audit and independent oracles."""
# Tests the tracked current implementation, not a replay of unavailable candidate sources.
from pathlib import Path
import hashlib,json,os,re,shutil,subprocess,unittest,uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
from tests.test_activation import AUDIT_PREFIX,AUDIT_SUFFIX
ROOT=Path(__file__).resolve().parents[1]
BASE_REVISION=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
CURRENT=ROOT/'kernel'
class KernelPool128Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.out=ROOT/'build/test/kernel-pool128-native'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
  cls.inputs=[*CURRENT.rglob('*.dg'),*[ROOT/('tests/'+n) for n in ('kernel_pool128_probe.dg','arena_fit_probe.c','runtime_view_probe.c','activation_probe.c','test_activation.py')],Path(__file__)]
  cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
 @classmethod
 def tearDownClass(cls):
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n');assert after==cls.before
  results={}
  for file in cls.out.glob('*/native.json'):
   data=json.loads(file.read_text());results[file.parent.name]={key:data[key] for key in ('returncode','stdout','stderr')}
  normal={kind+'-'+mode for kind in ('arena','runtime','audit') for mode in ('debug','release')}
  passed=len(results)==16 and all((v['returncode']==0 if name in normal else v['returncode']!=0) for name,v in results.items())
  (cls.out/'validation-summary.json').write_text(json.dumps(dict(passed=passed,source_binding='tracked-current-source',historical_candidate_replay=False,base_revision=BASE_REVISION,source_sha256=after,sources_unchanged=after==cls.before,actual_ap_or_vm_executed=False,evidence=results),indent=2)+'\n')
  print('KERNEL_POOL128_EVIDENCE',cls.out)
 def command(self,args,d,name):
  r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(name+'.json')).write_text(json.dumps({'command':list(map(str,args)),'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n');return r
 def stage(self,d,mutation=None):
  kernel=d/'kernel';shutil.copytree(ROOT/'kernel',kernel)
  if mutation:
   file,old,new={
    'arena-eight':('arena_fit','stack_blocks >= policy.POOL_PAGES / 16 + 1','stack_blocks >= policy.POOL_PAGES / 16'),
    'runtime64':('runtime_view','pool_pages: policy.POOL_PAGES as u64,','pool_pages: 64,'),
    'audit-bound64':('memory_startup','physical - pool >= (POOL_PAGES as u64) * PAGE','physical - pool >= 64 * PAGE'),
    'audit-seen64':('memory_startup','var seen: [POOL_PAGES]u8 = [0;POOL_PAGES];','var seen: [64]u8 = [0;64];'),
    'audit-leaf64':('memory_startup','(*view).pool,(POOL_PAGES as u64) * PAGE','(*view).pool,64 * PAGE'),
   }[mutation];target=kernel/('boot/'+file+'.dg');s=target.read_text();self.assertEqual(1,s.count(old));target.write_text(s.replace(old,new))
  return kernel
 def compile_native(self,source,model,d,kernel,mode):
  c=compile_file(source,roots=[d,ROOT/'tests',kernel,ROOT/'lang/std',ROOT/'lang/examples'],mode=mode);asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o';nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
  for fmt in ('elf64','win64'):
   target=obj if fmt==('win64' if os.name=='nt' else 'elf64') else d/(fmt+'.o');r=self.command([nasm,'-f',fmt,*nasm_flags(nasm),asm,'-o',target],d,'assemble-'+fmt);self.assertEqual(0,r.returncode,r.stderr)
  exe=d/('probe.exe' if os.name=='nt' else 'probe');r=self.command([cc,*(['-DDG_AUDIT=1'] if source.name=='activation_audit_probe.dg' else []),'-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-strict-aliasing',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),model,obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr);return exe,c
 def arena_model(self,d):
  s=(ROOT/'tests/arena_fit_probe.c').read_text();s=s.replace('pool+64','pool+128').replace('pool+=64','pool+=128').replace('complete(map,pool,64)','complete(map,pool,128)').replace('(rng()%16)*64','(rng()%8)*128').replace('available+pool,1,64','available+pool,1,128')
  s=s.replace('{{0,64}}','{{0,128}}').replace('{{0,64},{80,15}}','{{0,128},{144,15}}').replace('{{0,64},{80,16}}','{{0,128},{144,16}}').replace('{{16,80}}','{{16,144}}').replace('{{0,64},{81,16}}','{{0,128},{145,16}}').replace('{{0,80}}','{{0,144}}').replace('{{944,80}}','{{880,144}}').replace('{{0,64},{80,7},{96,8}}','{{0,128},{144,7},{160,8}}')
  s=s.replace('int main(void) {','extern uint64_t DG pool_buddy(uint64_t*);extern void DG pool_policy(uint64_t*);\nint main(void) {\n uint64_t cfg[3],b[3];pool_policy(cfg);CHECK(cfg[0]==7&&cfg[1]==128&&cfg[2]==524288);CHECK(pool_buddy(b)==0&&b[0]%524288==0&&b[1]%65536==0&&b[2]==880&&!(b[0]<b[1]+65536&&b[1]<b[0]+524288));')
  target=d/'model.c';target.write_text(s);return target
 def runtime_model(self,d):
  s=(ROOT/'tests/runtime_view_probe.c').read_text().replace('p->pool,p->pool,64,','p->pool,p->pool,128,').replace('262144','524288');target=d/'model.c';target.write_text(s);return target
 def audit_source(self,d,kernel):
  source=(kernel/'boot/memory_startup.dg').read_text();prefix=AUDIT_PREFIX
  if 'const POOL_PAGES:' not in prefix:prefix=prefix.replace('module activation_audit_probe;','module activation_audit_probe;\nimport boot.memory_policy as policy;\nconst POOL_PAGES:usize=policy.POOL_PAGES;')
  prefix=prefix.replace('table_meta: [64]u8','table_meta: [128]u8').replace('table_meta: [0;64]','table_meta: [0;128]')
  suffix=AUDIT_SUFFIX.replace('slice_from_raw_parts(pool,64)','slice_from_raw_parts(pool,128)')+"""
export("audit_used") fn used()u64 {unsafe {match paging.used_tables(&WORK.space){ok(v)=>{return v as u64;},err(e)=>{return 0;},}}}
export("audit_grow_bss") fn grow(end:u64)void {unsafe{WORK.layout.bss.end=end;}return;}
export("audit_guard") fn guard(seen:*u8,out:*u64)u64 {unsafe{var leaves:usize=0;var tables:usize=0;match audit_table(WORK.runtime.root_physical,0,0,seen,&leaves,&tables,false){ok=>{out[0]=leaves as u64;out[1]=tables as u64;return 0;},err(e)=>{return e;},}}}
"""
  target=d/'activation_audit_probe.dg';target.write_text(prefix+source[source.index('fn in_pages('):]+suffix);return target
 def audit_model(self,d):
  s=(ROOT/'tests/activation_probe.c').read_text().replace('64*4096','128*4096').replace('view.pool_pages=64','view.pool_pages=128')
  extra="""
extern uint64_t DG audit_used(void),audit_guard(uint8_t*,uint64_t*);extern void DG audit_grow_bss(uint64_t);
static void high_index(void){
 baseline();puts("entering high-index128 audit");fflush(stdout);add(view.pool+127*PAGE,pool_pa+127*PAGE,1);raw_checks(1,1);audit_grow_bss(KERNEL+0x10000000);uint64_t last=0;
 for(uint64_t i=1;audit_used()<128;i++){CHECK(i<128);last=KERNEL+i*0x200000;add(last,kernel_pa+i*0x200000,1);}CHECK(audit_used()==128);raw_checks(1,1);
 struct{uint8_t pre[16],seen[128],post[16];}guard;memset(&guard,0x6a,sizeof guard);memset(guard.seen,0,128);uint64_t counts[2];CHECK(audit_guard(guard.seen,counts)==0&&counts[1]==128);for(unsigned i=0;i<16;i++)CHECK(guard.pre[i]==0x6a&&guard.post[i]==0x6a);for(unsigned i=0;i<128;i++)CHECK(guard.seen[i]==1);
 uint64_t*leaf=entry(last,3),old=*leaf;*leaf|=4;raw_checks(0,0);*leaf=old;uint64_t*parent=entry(last,2),saved=*parent;*parent=pool_pa+128*PAGE|7;raw_checks(0,0);*parent=saved;
 uint64_t*pd=(uint64_t*)((uintptr_t)parent&~(uintptr_t)4095);unsigned slot=(unsigned)(parent-pd),free_slot=(slot+1)%512;while(pd[free_slot])free_slot=(free_slot+1)%512;pd[free_slot]=saved;raw_checks(0,0);pd[free_slot]=0;raw_checks(1,1);
}
"""
  needle='int main(void) {\n#ifdef _WIN32';self.assertEqual(1,s.count(needle));s=s.replace(needle,extra+'\n'+needle).replace('permission_masks();malformed_trees();extra_mappings();','permission_masks();malformed_trees();extra_mappings();high_index();').replace('pool_pa+128*PAGE|7','(pool_pa+128*PAGE)|7');target=d/'model.c';target.write_text(s);return target
 def run_probe(self,kind,mutation=None):
  for mode in ('debug','release'):
   d=self.out/((mutation or kind)+'-'+mode);d.mkdir();kernel=self.stage(d,mutation)
   if kind=='arena':source=ROOT/'tests/kernel_pool128_probe.dg';model=self.arena_model(d)
   elif kind=='runtime':source=ROOT/'tests/runtime_view_probe.dg';model=self.runtime_model(d)
   else:source=self.audit_source(d,kernel);model=self.audit_model(d)
   exe,c=self.compile_native(source,model,d,kernel,mode);r=self.command([exe],d,'native')
   if mutation:self.assertNotEqual(0,r.returncode,r.stdout+r.stderr)
   else:self.assertEqual(0,r.returncode,r.stdout+r.stderr)
 def test_actual_arena_buddy_runtime_and_raw_high_index(self):
  for kind in ('arena','runtime','audit'):self.run_probe(kind)
 def test_actual_old_bounds_and_seen_and_arena_are_rejected(self):
  for mutation,kind in (('arena-eight','arena'),('runtime64','runtime'),('audit-bound64','audit'),('audit-seen64','audit'),('audit-leaf64','audit')):self.run_probe(kind,mutation)
