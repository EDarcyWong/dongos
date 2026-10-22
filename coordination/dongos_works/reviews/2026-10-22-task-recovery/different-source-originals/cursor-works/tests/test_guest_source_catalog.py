"""Native authorized-source catalog: atomic batch publication and frontend use."""
import hashlib,json,os,subprocess,sys,unittest,uuid
from pathlib import Path
WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS
if not (ROOT/'lang').is_dir() and (WORKS/'project.json').is_file():
    source=Path(json.loads((WORKS/'project.json').read_text(encoding='utf-8'))['source_root'])
    ROOT=(WORKS/source).resolve() if not source.is_absolute() else source
sys.path.insert(0,str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
SOURCE=WORKS/'cursor-works/lang/bootstrap/guest_source_catalog.dg'
WRAPPER='''module probe.catalog_export;
import bootstrap.guest_source_catalog as c;
import bootstrap.guest_source_reader as r;
import bootstrap.frontend as frontend;
export("catalog_load") unsafe fn load(p:*const c.Input,n:usize,entry:usize,w:*const c.Workspace,read:r.ReadAt,result:*c.Result)u64{unsafe{
 return c.load(slice_from_raw_parts(p,n),entry,w,read,result);
}}
'''
HARNESS=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct{void*p;U n;} Slice;
typedef struct{U root;Slice path;U file,capacity;} Input;
typedef struct{U root;Slice path,bytes;} Source;
typedef struct{Slice scratch,staged,storage,sizes,sources;} Workspace;
typedef struct{U status,index,code,detail,used,count,entry;} Result;
typedef U (ABI *Read)(U,U,void*,U,U*);
extern U ABI catalog_load(const Input*,U,U,const Workspace*,Read,Result*);
extern U ABI dong_frontend_check(const U*,const Source*,U,const U*,void*,U,void*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,U n){(void)k;(void)l;(void)f;(void)n;fputs("unexpected panic",stderr);exit(87);}
static void check(int b,const char*s){if(!b){fprintf(stderr,"catalog assertion: %s\n",s);exit(90);}}
static const char*body[]={"module a;import b;fn f()u64{return b.value();}","module b;pub fn value()u64{return 7;}"};
static _Alignas(16) unsigned char raw[256],stage[1024],storage[1024];
static U sizes[5];static Source sources[5];static Result result;
static Input inputs[2];static Workspace w;
static U calls,offsets[2],fail_file,over_file,chunk;
static U ABI rd(U file,U off,void*p,U n,U*moved){
 check(file<2&&off==offsets[file]&&n>0,"callback trace");calls++;
 if(file==fail_file)return 0xbeef;
 if(file==over_file){*moved=n+1;return 0;}
 U len=strlen(body[file]);check(off<=len,"no reads after EOF");
 U take=len-off;if(take>n)take=n;if(take>chunk)take=chunk;
 memcpy(p,body[file]+off,take);*moved=take;offsets[file]+=take;return 0;
}
static int filled(const void*p,U n){const unsigned char*b=p;for(U i=0;i<n;i++)if(b[i]!=0xa5)return 0;return 1;}
static void setup(void){
 memset(raw,0xa5,sizeof raw);memset(stage,0xa5,sizeof stage);memset(storage,0xa5,sizeof storage);
 memset(sizes,0xa5,sizeof sizes);memset(sources,0xa5,sizeof sources);memset(&result,0xa5,sizeof result);
 inputs[0]=(Input){0,{(void*)"a.dg",4},0,128};inputs[1]=(Input){1,{(void*)"b.dg",4},1,128};
 w=(Workspace){{raw+16,129},{stage+16,264},{storage+16,264},{sizes+1,2},{sources+1,2}};
 calls=offsets[0]=offsets[1]=0;fail_file=over_file=UINT64_MAX;chunk=7;
}
static void unchanged(void){check(filled(storage,sizeof storage)&&filled(sources,sizeof sources),"failed batch publication");}
static void good(void){
 U status=catalog_load(inputs,2,0,&w,rd,&result);check(status==0&&result.status==0,"success");
 U used=8+strlen(body[0])+strlen(body[1]);check(result.used==used&&result.count==2&&result.entry==0,"counts");
 U at=0;for(U i=0;i<2;i++){
  Source*s=sources+1+i;check(s->root==inputs[i].root&&s->path.n==4&&s->bytes.n==strlen(body[i]),"source metadata");
  check(s->path.p==storage+16+at&&s->bytes.p==storage+16+at+4,"borrowed final addresses");
  check(!memcmp(s->path.p,inputs[i].path.p,4)&&!memcmp(s->bytes.p,body[i],s->bytes.n),"source contents");
  at+=4+s->bytes.n;
 }
 check(filled(storage,16)&&filled(storage+16+used,sizeof storage-16-used),"storage tails");
 check(filled(sources,sizeof(Source))&&filled(sources+3,2*sizeof(Source)),"Source tails");
 check(filled(sizes,8)&&filled(sizes+3,16),"sizes tails");
 check(filled(raw,16)&&filled(raw+145,sizeof raw-145)&&filled(stage,16)&&filled(stage+280,sizeof stage-280),"scratch canaries");
 memset(raw,0x33,sizeof raw);memset(stage,0x44,sizeof stage); /* released aliases cannot affect final sources */
#ifndef NO_FRONTEND
 U opts[3]={0,2,64},limits[10]={512,512,4096,32,544,1056,18432,32768,1024,32768};
 static _Alignas(16) unsigned char arena[16*1024*1024];U fr[45]={0};
 check(dong_frontend_check(opts,sources+1,2,limits,arena,sizeof arena,fr)==0&&fr[0]==0,"actual multi-module frontend");
#endif
}
static void failures(void){
 setup();fail_file=1;check(catalog_load(inputs,2,0,&w,rd,&result)==3&&result.index==1&&result.code==3&&result.detail==0xbeef,"second file I/O");unchanged();
 setup();inputs[1].capacity=strlen(body[1])-1;check(catalog_load(inputs,2,0,&w,rd,&result)==3&&result.index==1&&result.code==2,"file capacity");unchanged();
 setup();over_file=1;check(catalog_load(inputs,2,0,&w,rd,&result)==3&&result.code==4,"overlong callback");unchanged();
 setup();w.staged.n=263;check(catalog_load(inputs,2,0,&w,rd,&result)==2&&calls==0&&filled(&result,sizeof result),"batch capacity");unchanged();
}
static void invalids(void){
 for(unsigned i=0;i<12;i++){
  setup();U n=2,entry=0;const Workspace*wp=&w;Result*rp=&result;
  switch(i){
   case 0:inputs[0].root=2;break;
   case 1:inputs[0].path=(Slice){(void*)"../a.dg",7};break;
   case 2:inputs[0].path=(Slice){(void*)"a.txt",5};break;
   case 3:inputs[1].root=0;inputs[1].path=inputs[0].path;break;
   case 4:n=0;break;case 5:entry=2;break;
   case 6:w.storage.p=stage+17;break;
   case 7:w.sources.p=(void*)&w;break;
   case 8:rp=(Result*)(storage+24);break;
   case 9:inputs[0].path=(Slice){storage+16,4};memcpy(storage+16,"a.dg",4);break;
   case 10:w.sizes.n=UINT64_MAX;break;case 11:wp=NULL;break;
  }
  unsigned char saved[sizeof storage];memcpy(saved,storage,sizeof storage);
  U got=catalog_load(inputs,n,entry,wp,rd,rp);
  check(got==1&&calls==0,"invalid preflight");
  check(!memcmp(saved,storage,sizeof storage)&&filled(sources,sizeof sources)&&filled(&result,sizeof result),"invalid atomicity");
 }
}
int main(void){setup();good();setup();inputs[0].capacity=strlen(body[0]);inputs[1].capacity=strlen(body[1]);good();failures();invalids();puts("catalog checks passed");return 0;}
'''
class GuestSourceCatalogTests(unittest.TestCase):
 def test_native_batch_and_frontend(self):
  nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
  work=WORKS/'cursor-works/build/CR45'/('run-'+uuid.uuid4().hex[:12]);work.mkdir(parents=True)
  snap=work/'source';(snap/'bootstrap').mkdir(parents=True)
  # Freeze the whole native dependency root; mutations stay in this private copy.
  import shutil
  shutil.copytree(ROOT/'lang/bootstrap',snap/'bootstrap',dirs_exist_ok=True)
  shutil.copytree(ROOT/'lang/std/core',snap/'core')
  production=SOURCE.read_text(encoding='utf-8');(snap/'bootstrap/guest_source_catalog.dg').write_text(production,encoding='utf-8')
  (work/'probe').mkdir();wrapper=work/'probe/catalog_export.dg';wrapper.write_text(WRAPPER,encoding='utf-8')
  (work/'probe.c').write_text(HARNESS,encoding='utf-8')
  before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,SOURCE.with_suffix('.md'),Path(__file__))}
  records=[]
  for mode in ('debug','release'):
   # The good executable covers all rejection/borrow/canary paths.
   c=compile_file(wrapper,roots=[work,snap],mode=mode)
   asm=work/(mode+'.asm');asm.write_text(c.assembly,encoding='utf-8');obj=work/(mode+'.o');exe=work/(mode+('.exe' if os.name=='nt' else ''))
   native='win64' if os.name=='nt' else 'elf64'
   commands=[]
   for fmt in ('elf64','win64'):
    target=obj if fmt==native else work/(mode+'.'+fmt+'.o')
    commands.append([nasm,'-O0','-f',fmt,*nasm_flags(nasm),'-o',target,asm])
   commands += [[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',work/'probe.c',obj,'-o',exe],[exe]]
   for i,command in enumerate(commands):
    run=subprocess.run(list(map(str,command)),capture_output=True,timeout=180)
    (work/f'{mode}-{i}.stdout').write_bytes(run.stdout);(work/f'{mode}-{i}.stderr').write_bytes(run.stderr)
    self.assertEqual(run.returncode,0,run.stderr.decode(errors='replace'));records.append(dict(command=list(map(str,command)),returncode=run.returncode))
  self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,SOURCE.with_suffix('.md'),Path(__file__))})
  artifacts={str(p.relative_to(work)):hashlib.sha256(p.read_bytes()).hexdigest() for p in work.rglob('*') if p.is_file()}
  (work/'summary.json').write_text(json.dumps(dict(inputs=before,records=records,artifacts=artifacts,source_stable=True,guest_executed=False),indent=2)+'\n')
 def test_early_publication_mutant(self):
  nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
  work=WORKS/'cursor-works/build/CR45'/('negative-'+uuid.uuid4().hex[:12]);work.mkdir(parents=True)
  import shutil
  snap=work/'source';shutil.copytree(ROOT/'lang/bootstrap',snap/'bootstrap');shutil.copytree(ROOT/'lang/std/core',snap/'core')
  (work/'probe').mkdir();wrapper=work/'probe/catalog_export.dg'
  wrapper.write_text(WRAPPER.replace('import bootstrap.frontend as frontend;',''),encoding='utf-8')
  (work/'probe.c').write_text(HARNESS,encoding='utf-8')
  source=SOURCE.read_text(encoding='utf-8');old=' var offset:usize=0;i=0;'
  self.assertEqual(source.count(old),1)
  records=[]
  for label,text in [('good',source),('bad-early-publication',source.replace(old,' (*w).sources[0].root=99;\n'+old))]:
   (snap/'bootstrap/guest_source_catalog.dg').write_text(text,encoding='utf-8')
   for mode in ('debug','release'):
    name=label+'-'+mode;compiled=compile_file(wrapper,roots=[work,snap],mode=mode)
    asm=work/(name+'.asm');asm.write_text(compiled.assembly,encoding='utf-8');obj=work/(name+'.o');exe=work/(name+('.exe' if os.name=='nt' else ''))
    commands=[[nasm,'-O0','-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',obj,asm],
      [cc,'-DNO_FRONTEND','-std=c11','-O2','-Wall','-Wextra','-Werror',work/'probe.c',obj,'-o',exe],[exe]]
    for i,cmd in enumerate(commands):
     r=subprocess.run(list(map(str,cmd)),capture_output=True,timeout=180);(work/f'{name}-{i}.stderr').write_bytes(r.stderr)
     expected=90 if label!='good' and i==2 else 0
     self.assertEqual(r.returncode,expected,r.stderr.decode(errors='replace'))
     if expected:self.assertIn(b'failed batch publication',r.stderr)
     records.append(dict(command=list(map(str,cmd)),returncode=r.returncode,expected=expected))
  artifacts={str(p.relative_to(work)):hashlib.sha256(p.read_bytes()).hexdigest() for p in work.rglob('*') if p.is_file()}
  (work/'summary.json').write_text(json.dumps(dict(records=records,artifacts=artifacts,guest_executed=False),indent=2)+'\n')
if __name__=='__main__':unittest.main()
