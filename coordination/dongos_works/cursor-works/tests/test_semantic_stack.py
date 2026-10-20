from concurrent.futures import ThreadPoolExecutor
from threading import Event
"""Compare native semantic behavior and measured dynamic stack reservations."""
import hashlib,json,os,re,shutil,struct,subprocess,sys,unittest,uuid
from pathlib import Path
WORKS=Path(__file__).resolve().parents[2];ROOT=WORKS
if not (ROOT/'lang').is_dir() and (WORKS/'project.json').is_file():
 source=Path(json.loads((WORKS/'project.json').read_text(encoding='utf-8'))['source_root']);ROOT=(WORKS/source).resolve() if not source.is_absolute() else source
sys.path.insert(0,str(ROOT))
from lang.dongc import compile_file
from lang.dongc.modules import Resolver
from lang.tests.test_dongc import tool,nasm_flags
SOURCE=WORKS/'cursor-works/lang/bootstrap/semantic_types.dg'
HARNESS=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct{void*p;U n;} S;
typedef struct{U root;S path,bytes;} Source;
typedef struct{S pools[18];U entry;} Graph;
typedef struct{U status,exit_code,stage,code,detail,source,offset,used;Graph graph;} R;
typedef struct{U status,stage,code,unit,node,detail,used,written;} ER;
extern U dg_stack_low;
extern U ABI dong_frontend_check(const U*,const Source*,U,const U*,void*,U,R*);
extern U ABI dong_native_emit(const Graph*,const U*,U,void*,U,void*,U,ER*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,U n){(void)f;(void)n;fprintf(stderr,"PANIC %u/%u",k,l);exit(87);}
static void fail(const char*s){fputs(s,stderr);exit(90);}
static U limits[10]={131072,65536,4194304,8192,16384,32768,1048576,4096,256,4096};
static void run(Source*s,U n,U entry,U depth,const char*output,U emit_mode){
 U capacity=(n>1?512ULL:64ULL)*1024*1024;
 U closure_limits[10]={250000,150000,4194304,8192,150032,300032,4802048,4096,256,4096};
 unsigned char*a=malloc(capacity+32);if(!a)exit(95);memset(a,0xa5,capacity+32);
 U opts[3]={entry,2,depth};R r={0};U start;dg_stack_low=UINT64_MAX;
 __asm__ volatile("mov %%rsp,%0":"=r"(start));
 U status=dong_frontend_check(opts,s,n,n>1?closure_limits:limits,a+16,capacity,&r);
 U peak=start-dg_stack_low;
 for(U i=0;i<16;i++)if(a[i]!=0xa5||a[16+capacity+i]!=0xa5)fail("arena canary");
 printf("{\"status\":%llu,\"stage\":%llu,\"code\":%llu,\"detail\":%llu,\"peak\":%llu}\n",(unsigned long long)status,(unsigned long long)r.stage,(unsigned long long)r.code,(unsigned long long)r.detail,(unsigned long long)peak);
 if(output&&status==0){
  void*b=malloc(256*1024*1024),*text=malloc(128*1024*1024);U el[7]={4096,262144,131072,128*1024*1024,2048,512,1024};ER er={0};
  if(!b||!text)exit(95);
  if(dong_native_emit(&r.graph,el,emit_mode,b,256*1024*1024,text,128*1024*1024,&er)!=0){fprintf(stderr,"emit %llu/%llu/%llu/%llu/%llu",(unsigned long long)er.status,(unsigned long long)er.stage,(unsigned long long)er.unit,(unsigned long long)er.node,(unsigned long long)er.detail);exit(91);}
  FILE*f=fopen(output,"wb");if(!f||fwrite(text,1,er.written,f)!=er.written||fclose(f))exit(92);free(text);free(b);
 }
 free(a);
}
static U word(FILE*f){U v;if(fread(&v,1,8,f)!=8)exit(93);return v;}
int main(int argc,char**argv){
 if(argc>4)limits[4]=10;
 if(argc>1){FILE*f=fopen(argv[1],"rb");if(!f)exit(93);U n=word(f),entry=word(f);if(n>256)exit(94);Source*s=calloc(n,sizeof *s);
  for(U i=0;i<n;i++){s[i].root=word(f);s[i].path.n=word(f);s[i].bytes.n=word(f);s[i].path.p=malloc(s[i].path.n+1);s[i].bytes.p=malloc(s[i].bytes.n+1);
   if(!s[i].path.p||!s[i].bytes.p)exit(95);
   if(fread(s[i].path.p,1,s[i].path.n,f)!=s[i].path.n||fread(s[i].bytes.p,1,s[i].bytes.n,f)!=s[i].bytes.n)exit(93);
  }fclose(f);run(s,n,entry,128,argc>2&&argv[2][0]?argv[2]:NULL,argc>3?strtoull(argv[3],NULL,10):0);for(U i=0;i<n;i++){free(s[i].path.p);free(s[i].bytes.p);}free(s);return 0;
 }
 const char*cases[]={
 "module a;fn f(x:u64)u64{return ((((((((((((((((x+1)+1)+1)+1)+1)+1)+1)+1)+1)+1)+1)+1)+1)+1)+1)+1);}",
 "module a;fn f()u64{var x:u64;return x;}",
 "module a;fn f()u64{return true;}",
 "module a;fn f(x:bool)u64{match x{true=>{return 1;},false=>{return 2;},}}",
 "module a;fn f()u64{var x:u64=1;defer{x+=1;}return x;}",
 "module a;fn f()u64{return try 1;}",
 "module a;unsafe fn f(p:*const u64)u64{return (p as *const u64)[0];}",
 "module a;fn f(x:u64)u64{return ((x+1)*(x+2))+(x+3);}",
 "module a;fn f(x:u64)u64{return ((((((((((((((((x+1)+1)+1)+1)+1)+1)+1)+1)+1)+1)+1)+1)+1)+1)+1)+1);}"};
 for(U i=0;i<sizeof cases/sizeof *cases;i++){Source s={0,{"a.dg",4},{(void*)cases[i],strlen(cases[i])}};run(&s,1,0,i==8?4:128,NULL,0);}return 0;
}
'''
SCENARIOS=[('constant-fold', 'fn f()u8{return (1+2)*3;}', 0), ('overflow', 'fn f()u8{return 255+1;}', 3), ('try', 'fn f(x:!u8)!u8{return try x;}', 0), ('try-defer', 'fn f(x:!u8)!u8{defer{let y=try x;}return 0;}', 15), ('orelse', 'fn f(x:?u8)u8{return x orelse 1;}', 0), ('orelse-read', 'fn f(x:?u8)u8{var y:u8;return x orelse y;}', 11), ('cast', 'fn f(x:u8)u64{return x as u64;}', 0), ('cast-never', 'fn die()noreturn{loop{}}fn g(x:u64)u64{return x;}fn f()u64{return g(die()) as u64;}', 0), ('array-never', 'fn die()noreturn{loop{}}fn g(x:u64)u64{return x;}fn f()u64{let b=true&&([1 as u64,die()][0]==0);}', 0), ('repeat-never', 'fn die()noreturn{loop{}}fn g(x:u64)u64{return x;}fn f()u64{let b=true&&([g(die());2][0]==0);}', 0), ('struct-never', 'fn die()noreturn{loop{}}fn g(x:u64)u64{return x;}struct S{x:u64,y:u64}fn f()u64{let b=true&&(S{x:die(),y:1}.y==0);}', 0), ('shortcircuit', 'fn die()noreturn{loop{}}fn g(x:u64)u64{return x;}struct S{x:u64}fn f()u64{let b=false&&(S{x:die()}.x==0);}', 14), ('dead-type-check', 'fn die()noreturn{loop{}}fn g(x:u64)u64{return x;}struct S{x:u64,y:u64}fn f()u64{let b=true&&(S{x:die(),y:true}.x==0);}', 3), ('dead-read-check', 'fn die()noreturn{loop{}}fn g(x:u64)u64{return x;}struct S{x:u64,y:u64}fn f()u64{var x:u64;let b=true&&(S{x:die(),y:x}.x==0);}', 11), ('context-mismatch', 'fn die()noreturn{loop{}}fn g(x:u64)u64{return x;}fn f()void{let x:bool=g(die());}', 3), ('defer', 'fn die()noreturn{loop{}}fn g(x:u64)u64{return x;}struct S{x:u64}fn f()u64{defer{let b=false&&(S{x:die()}.x==0);}return 1;}', 0), ('slice', 'fn f(x:[]const u8)[]const u8{return x[0..1];}', 0), ('nested-call', 'fn g(x:u64)u64{return x;}fn f(x:u64)u64{return g(g(g(x+1)));}', 0), ('match', 'fn f(x:bool)u64{match x{true=>{return 1;},false=>{return 2;},}}', 0), ('semantic-depth', 'fn f(x:u64)u64{return x+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1;}', 7)]

def instrument(text):
 serial=0
 def add(m):
  nonlocal serial
  serial+=1
  return m[0]+f'\n    pushfq\n    push r11\n    lea r11, [rsp+16]\n    cmp r11, [rel $dg_stack_low]\n    jae .L_stack_sample_{serial}\n    mov [rel $dg_stack_low], r11\n.L_stack_sample_{serial}:\n    pop r11\n    popfq'
 text=re.sub(r'^[ \t]*sub rsp, [0-9]+$',add,text,flags=re.M)
 return text+'\nsection .bss\nalign 8\nglobal $dg_stack_low\n$dg_stack_low: resq 1\n'
def frames(text):
 out={}
 for m in re.finditer(r'^\$__dg_m([0-9a-f]+)_f([0-9a-f]+):\n(.*?)(?=^\$|\Z)',text,re.M|re.S):
  if bytes.fromhex(m[1]).decode()=='bootstrap.semantic_types':
   n=re.search(r'sub rsp, ([0-9]+)',m[3][:400]);out[bytes.fromhex(m[2]).decode()]=int(n[1]) if n else 0
 return out
class SemanticStackTests(unittest.TestCase):
 def test_seed_and_native_stack(self):
  nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
  work=WORKS/'cursor-works/build/CR47'/('run-'+uuid.uuid4().hex[:12]);work.mkdir(parents=True)
  (work/'probe.c').write_text(HARNESS,encoding='utf-8');records=[];results={}
  base=ROOT/'lang/bootstrap/semantic_types.dg';before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,base,Path(__file__))}
  def command(cmd,label):
   r=subprocess.run(list(map(str,cmd)),capture_output=True,timeout=300);(work/(label+'.stdout')).write_bytes(r.stdout);(work/(label+'.stderr')).write_bytes(r.stderr)
   self.assertEqual(r.returncode,0,r.stderr.decode(errors='replace'));records.append(dict(command=list(map(str,cmd)),returncode=r.returncode));return r.stdout
  def link(text,name):
   asm=work/(name+'.asm');asm.write_text(instrument(text),encoding='utf-8');obj=work/(name+'.o');exe=work/(name+('.exe' if os.name=='nt' else ''))
   command([nasm,'-O0','-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',obj,asm],name+'-asm')
   command([nasm,'-O0','-f','elf64' if os.name=='nt' else 'win64',*nasm_flags(nasm),'-o',work/(name+'-other.o'),asm],name+'-asm-other')
   command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',work/'probe.c',obj,'-o',exe],name+'-link');return exe
  baseline_ready=Event()
  def variant(label):
   snap=work/label;shutil.copytree(ROOT/'lang/bootstrap',snap/'bootstrap');shutil.copytree(ROOT/'lang/std/core',snap/'core');(snap/'host').mkdir();shutil.copyfile(ROOT/'lang/host/native_entry.dg',snap/'host/native_entry.dg')
   shutil.copyfile(SOURCE if label=='candidate' else base,snap/'bootstrap/semantic_types.dg')
   resolver=Resolver([snap]);entry=snap/'host/native_entry.dg';resolver.load(entry)
   paths=list(resolver.paths.values());payload=bytearray(struct.pack('<2Q',len(paths),paths.index(entry.resolve())))
   for p in paths:
    relative=p.relative_to(snap).as_posix().encode();b=p.read_bytes();payload+=struct.pack('<3Q',0,len(relative),len(b))+relative+b
   corpus=work/(label+'.input');corpus.write_bytes(payload)
   if label=='baseline':baseline_ready.set()
   for mode in ('debug','release'):
    name=label+'-'+mode;compiled=compile_file(entry,roots=[snap],mode=mode);exe=link(compiled.assembly,name)
    rows=[json.loads(x) for x in command([exe],name+'-cases').splitlines()];closure_asm=work/(name+'-native.asm')
    closure=json.loads(command([exe,corpus,closure_asm,str(int(mode=='release'))],name+'-closure'))
    self.assertEqual(closure['status'],0,closure)
    # Native output is assembled/linked and executes the same source cases.
    native=link(closure_asm.read_text(encoding='utf-8'),name+'-native')
    native_rows=[json.loads(x) for x in command([native],name+'-native-cases').splitlines()]
    native_closure=json.loads(command([native,corpus],name+'-native-closure'));self.assertEqual(native_closure['status'],0,native_closure)
    explicit={};common={}
    for kind,target in (('seed',exe),('native',native)):
     checks=[]
     for title,text,expected in SCENARIOS:
      path=b'a.dg';body=('module a;'+text).encode();ip=work/(name+'-'+kind+'-'+title+'.input');ip.write_bytes(struct.pack('<5Q',1,0,0,len(path),len(body))+path+body)
      row=json.loads(command([target,ip],name+'-'+kind+'-'+title))
      if expected:self.assertEqual((row['stage'],row['code']),(4,expected),(title,row))
      else:self.assertEqual(row['status'],0,(title,row))
      if expected==7:self.assertEqual(row['status'],4,row)
      checks.append(row)
     path=b'a.dg';body=b'module a;struct S{x:u64}fn f(x:[2]u64)u64{return x[0];}';ip=work/(name+'-'+kind+'-capacity.input');ip.write_bytes(struct.pack('<5Q',1,0,0,len(path),len(body))+path+body)
     capacity=json.loads(command([target,ip,'','0','capacity'],name+'-'+kind+'-capacity'))
     self.assertEqual((capacity['status'],capacity['stage'],capacity['code'],capacity['detail']),(2,4,2,2),capacity)
     explicit[kind]=dict(semantic=checks,capacity=capacity)
     self.assertTrue(baseline_ready.wait(60),'baseline snapshot ready')
     same=work/(name+'-'+kind+'-same.asm');same_row=json.loads(command([target,work/'baseline.input',same,str(int(mode=='release'))],name+'-'+kind+'-same'))
     self.assertEqual(same_row['status'],0,same_row);common[kind]=hashlib.sha256(same.read_bytes()).hexdigest()
    results[name]=dict(rows=rows,closure=closure,frames=frames(compiled.assembly),native_rows=native_rows,native_closure=native_closure,explicit=explicit,common_assembly=common)
  with ThreadPoolExecutor(max_workers=2) as pool:
   list(pool.map(variant,('baseline','candidate')))
  for mode in ('debug','release'):
   a,b=results['baseline-'+mode],results['candidate-'+mode]
   for phase in ('rows','native_rows'):
    self.assertEqual([{k:v for k,v in x.items() if k!='peak'} for x in a[phase]], [{k:v for k,v in x.items() if k!='peak'} for x in b[phase]])
    self.assertLess(b[phase][0]['peak'],a[phase][0]['peak'],'old large-frame implementation fails this real dynamic stack assertion')
   self.assertLess(b['frames']['rt_expr'],a['frames']['rt_expr'])
   self.assertLess(b['closure']['peak'],a['closure']['peak'])
   self.assertLess(b['native_closure']['peak'],a['native_closure']['peak'])
   self.assertEqual(len(set([*a['common_assembly'].values(),*b['common_assembly'].values()])),1)
   for kind in ('seed','native'):
    for key in ('semantic',):
     trim=lambda seq:[{k:v for k,v in x.items() if k!='peak'} for x in seq]
     self.assertEqual(trim(a['explicit'][kind][key]),trim(b['explicit'][kind][key]))
  self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,base,Path(__file__))})
  artifacts={str(p.relative_to(work)):hashlib.sha256(p.read_bytes()).hexdigest() for p in work.rglob('*') if p.is_file()}
  (work/'summary.json').write_text(json.dumps(dict(inputs=before,records=records,results=results,artifacts=artifacts,guest_executed=False,stack_limit_changed=False),indent=2)+'\n')
if __name__=='__main__':unittest.main()
