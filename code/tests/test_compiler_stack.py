"""Execute the production compiler stack loader with real ELF and paging."""
import hashlib,json,os,re,shutil,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
FIXTURE='''
export("compiler_load") fn compiler_load(p:*const u8,n:usize,random:bool)u64{unsafe{
 if random{match stage_compiler_random(8,slice_from_raw_parts(p,n)){ok=>{return 0;},err(e)=>{return e;},}}
 match stage_compiler(8,slice_from_raw_parts(p,n),0x1000_0000,STACK_TOP){ok=>{return 0;},err(e)=>{return e;},}
}}
export("compiler_limit") fn compiler_limit(n:usize)void{unsafe{EXTENDED_LIMIT=n;}return;}
export("compiler_mapping") fn compiler_mapping(address:u64)u64{unsafe{
 var m=paging.Mapping{physical:0,flags:0};
 match paging.query(&SPACES[8],address,&m){ok=>{return m.flags;},err(e)=>{return 0;},}
}}
'''
MAIN=r'''
extern uint64_t ABI compiler_load(const void*,uint64_t,uint64_t),compiler_mapping(uint64_t);
extern void ABI compiler_limit(uint64_t);
static const uint64_t top=UINT64_C(0x7ffff00000);
static int profiles(void){
 CHECK(!setup(0));elf(1);CHECK(!stage_load(image,sizeof(image),0));CHECK(stage_get(0,0)==5);
 for(unsigned i=1;i<=4;i++)CHECK(compiler_mapping(top-i*4096)==3);
 CHECK(!compiler_mapping(top-5*4096)&&!compiler_mapping(top));
 aborting=1;CHECK(!stage_abort_test());aborting=0;CHECK(!empty(5));
 CHECK(!setup(0));elf(1);CHECK(!compiler_load(image,sizeof(image),0));CHECK(stage_get(0,0)==17);
 for(unsigned i=1;i<=16;i++)CHECK(compiler_mapping(top-i*4096)==3);
 CHECK(!compiler_mapping(top-17*4096)&&!compiler_mapping(top));CHECK(stage_get(13,8)==top-8);
 aborting=1;CHECK(!stage_abort_test());aborting=0;CHECK(!empty(17));
 CHECK(!compiler_load(image,sizeof(image),0));CHECK(stage_get(0,0)==17&&stage_resources_calls()==17);
 CHECK(!stage_commit_test());aborting=1;CHECK(!stage_destroy_test(8));aborting=0;
 CHECK(!stage_get(2,8));for(unsigned i=0;i<17;i++)CHECK(stage_get(1,i)==1);
 CHECK(!compiler_load(image,sizeof(image),0));CHECK(stage_get(0,0)==17);
 aborting=1;CHECK(!stage_abort_test());aborting=0;CHECK(!empty(17));return 0;
}
static int capacity_and_rollback(void){
 CHECK(!setup(0));elf(1);compiler_limit(16);CHECK(compiler_load(image,sizeof(image),0)!=0);
 CHECK(stage_resources_calls()==0&&stage_get(0,0)==0&&stage_get(5,0)==16);
 compiler_limit(17);CHECK(!compiler_load(image,sizeof(image),0));CHECK(stage_get(0,0)==17);
 aborting=1;CHECK(!stage_abort_test());aborting=0;CHECK(!empty(17));
 CHECK(!setup(10));elf(1);CHECK(compiler_load(image,sizeof(image),0)==0x05070002);
 CHECK(stage_get(0,0)==9);CHECK(!empty(9));stage_resources_fail(0);
 CHECK(!compiler_load(image,sizeof(image),0));CHECK(stage_get(0,0)==17);
 aborting=1;CHECK(!stage_abort_test());aborting=0;CHECK(!empty(17));return 0;
}
static int collisions_and_entropy(void){
 for(unsigned i=0;i<18;i++){
  CHECK(!setup(0));elf(2);put64(64+56+16,top-0x10000000-17*4096+i*4096);
  CHECK(compiler_load(image,sizeof(image),0)!=0);CHECK(!stage_resources_calls()&&!binds);CHECK(!empty(0));
 }
 // Adjacent pages outside each guard are permitted.
 for(unsigned i=0;i<2;i++){
  CHECK(!setup(0));elf(2);put64(64+56+16,top-0x10000000+(i?4096:-18*INT64_C(4096)));
  CHECK(!compiler_load(image,sizeof(image),0));CHECK(stage_get(0,0)==18);
  aborting=1;CHECK(!stage_abort_test());aborting=0;CHECK(!empty(18));
 }
 CHECK(!setup(0));elf(1);put16(16,2);CHECK(!compiler_load(image,sizeof(image),1));
 uint64_t random_top=top-UINT64_C(0x12345000);CHECK(stage_get(13,8)==random_top-8&&stage_get(12,8)==0x103c0);
 for(unsigned i=1;i<=16;i++)CHECK(compiler_mapping(random_top-i*4096)==3);
 CHECK(!compiler_mapping(random_top-17*4096)&&!compiler_mapping(random_top));
 aborting=1;CHECK(!stage_abort_test());aborting=0;CHECK(!empty(17));
 CHECK(!setup(0));entropy_fail=1;CHECK(compiler_load(image,sizeof(image),1)==0x04080001);
 CHECK(!stage_resources_calls()&&stage_get(5,0)==16);return 0;
}
int main(void){
#ifdef _WIN32
 void*memory=_aligned_malloc(256*4096,4096);
#else
 void*memory=aligned_alloc(4096,256*4096);
#endif
 CHECK(memory);alias=(uint64_t)(uintptr_t)memory;
 if(profiles()||capacity_and_rollback()||collisions_and_entropy())return 1;
 printf("compiler stack checks passed %u\n",checks);return 0;
}
'''
class Tests(unittest.TestCase):
 def test_real_loader_profiles_guards_capacity_and_rollback(self):
  names=('kernel/user/memory.dg','kernel/user/compiler_stack.dg','kernel/exec/elf.dg','kernel/mm/paging.dg',
   'tests/user_stage_fixture.dg','tests/user_stage_startup.dg','tests/user_stage_resources.dg','tests/user_stage_probe.c','tests/test_compiler_stack.py')
  before={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}
  out=ROOT/'build/test/compiler-stack'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
  nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);records=[]
  def command(argv,d,label):
   r=subprocess.run(list(map(str,argv)),capture_output=True,text=True,timeout=120)
   data=dict(command=list(map(str,argv)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
   (d/(label+'.json')).write_text(json.dumps(data,indent=2)+'\n');records.append(data);return r
  for mode in ('debug','release'):
   for variant in ('normal','old-four-pages','old-guard-window','old-capacity-precheck'):
    d=out/(mode+'-'+variant);shutil.copytree(ROOT/'kernel',d/'kernel')
    source=(ROOT/names[0]).read_text()
    changes={'old-four-pages':('var at = stack_top - stack_pages * 4096;','var at = stack_top - 4 * 4096;'),
     'old-guard-window':('stack_top - (stack_pages+1) * 4096','stack_top - 5 * 4096'),
     'old-capacity-precheck':('plan.page_count + stack_pages >','plan.page_count + 4 >')}
    if variant!='normal':
     a,b=changes[variant];self.assertEqual(source.count(a),1);source=source.replace(a,b)
    source=source.replace('pub const ALIASES: u64 = 0xffff_d000_0000_0000;','pub var ALIASES: u64 = 0;')
    path=d/'kernel/user/memory.dg';path.write_text(source+'\n'+(ROOT/names[4]).read_text()+FIXTURE)
    (d/'kernel/boot/memory_startup.dg').write_text((ROOT/'kernel/boot/memory_startup.dg').read_text()+'\n'+(ROOT/names[5]).read_text())
    (d/'kernel/boot/service_memory.dg').write_text((ROOT/names[6]).read_text())
    c=compile_file(path,roots=[d/'kernel',ROOT/'services',ROOT/'lang/std',ROOT/'lang/examples'],mode=mode)
    asm=d/'probe.asm';asm.write_text(c.assembly)
    mocked={'__dong_panic','user_current_root','user_pcid_flush_all','user_pcid_unbind','user_pcid_bind','user_entropy64','runtime_invalidate','runtime_copy_bytes','user_pcid_invalidate_root'}
    externs={m.group(1).lstrip('$') for m in re.finditer(r'^extern (\$?\w+)',c.assembly,re.M)}-mocked
    stub=d/'unused.asm';stub.write_text('bits 64\nsection .text\n'+''.join('global $'+x+'\n$'+x+': ud2\n' for x in sorted(externs)))
    objects=[]
    for label,file in (('probe',asm),('unused',stub)):
     for fmt in ('win64','elf64'):
      obj=d/(label+'-'+fmt+'.o')
      r=command([nasm,'-O0','-f',fmt,*nasm_flags(nasm),file,'-o',obj],d,label+'-'+fmt);self.assertEqual(r.returncode,0,r.stderr)
      if fmt==('win64' if os.name=='nt' else 'elf64'):objects.append(obj)
    probe=d/'probe.c';probe.write_text((ROOT/names[7]).read_text().split('static int sparse_retry')[0]+MAIN)
    exe=d/('probe.exe' if os.name=='nt' else 'probe')
    r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),probe,*objects,'-o',exe],d,'link');self.assertEqual(r.returncode,0,r.stderr)
    r=command([exe],d,'execute');self.assertEqual(r.returncode,0 if variant=='normal' else 1,r.stdout+r.stderr)
    if variant!='normal':self.assertIn('stage check failed',r.stderr)
  self.assertEqual(before,{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names})
  (out/'summary.json').write_text(json.dumps(dict(inputs=before,source_stable=True,records=records,real_loader_and_paging=True,hardware_mocked=True,guest_executed=False),indent=2)+'\n')
  print('COMPILER_STACK_EVIDENCE',out)
if __name__=='__main__':unittest.main()
