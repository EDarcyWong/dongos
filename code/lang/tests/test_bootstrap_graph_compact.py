"""Opt-in consuming graph compaction: native relocation, rejection, and emit parity."""
from __future__ import annotations
import hashlib,json,os,shutil,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
from lang.tests.test_bootstrap_frontend import HARNESS as FRONT_HARNESS
ROOT=Path(__file__).resolve().parents[2]
WRAPPER='''module probe;
import bootstrap.graph_compact as compact;
import bootstrap.compiler_driver as driver;
import bootstrap.frontend as front;
export("compact_graph") pub unsafe fn run(g:*front.Graph,r:*compact.Result)u64{unsafe{return compact.compact(g,r);}}
'''
HARNESS=FRONT_HARNESS.split('static unsigned invalid(void)')[0]+r'''
typedef struct{uint64_t old,retained,reclaimed;} CompactResult;
typedef struct{uint64_t v[7];} DriverLimits;
typedef struct{uint64_t status,stage,code,unit,node,detail,used,written;} DriverResult;
extern uint64_t ABI compact_graph(Graph*,CompactResult*);
extern uint64_t ABI dong_native_emit(const Graph*,const DriverLimits*,uint64_t,void*,uint64_t,void*,uint64_t,DriverResult*);
static uint64_t hash(const void*p,uint64_t n){const unsigned char*b=p;uint64_t h=14695981039346656037ULL;for(uint64_t i=0;i<n;i++){h^=b[i];h*=1099511628211ULL;}return h;}
#define CHECK(x) do{if(!(x)){fprintf(stderr,"compact assertion line %d\n",__LINE__);exit(96);}}while(0)
static const uint64_t widths[16]={72,56,1,64,32,48,32,72,24,8,40,1,4,16,8,24};
static const uint64_t alignments[16]={8,8,1,8,8,8,8,8,8,8,8,1,4,8,8,8};
static unsigned invalid(void){
 uint64_t raw[2048],saved[2048];unsigned count=0;
 for(unsigned k=0;k<39;k++){
  memset(raw,0xa5,sizeof(raw));unsigned char*b=(unsigned char*)raw;
  Graph*g=(Graph*)b;CompactResult*r=(CompactResult*)(b+320);Source*s=(Source*)(b+400);
  memset(g,0,sizeof(*g));g->arena=(Slice){b+1024,8192};g->sources=(Slice){s,1};*s=(Source){0,{b+600,8},{b+640,64}};
  Slice*pool=&g->units;for(unsigned i=0;i<16;i++)pool[i]=(Slice){b+1024+i*128,1};
  Graph*gp=g;CompactResult*rp=r;
  switch(k){
   case 0:gp=NULL;break;case 1:rp=NULL;break;
   case 2:gp=(Graph*)(b+1);break;case 3:rp=(CompactResult*)(b+321);break;
   case 4:gp=(Graph*)(UINT64_MAX-7);break;case 5:rp=(CompactResult*)(UINT64_MAX-7);break;
   case 6:rp=(CompactResult*)g;break;case 7:g->arena=(Slice){NULL,1};break;
   case 8:g->arena=(Slice){(void*)(UINT64_MAX-7),16};break;
   case 9:g->arena=(Slice){b,8192};break;case 10:rp=(CompactResult*)(b+2048);break;
   case 11:g->sources=(Slice){NULL,1};break;case 12:g->sources.n=UINT64_MAX;break;
   case 13:g->sources.p=b+401;break;case 14:g->sources.p=(void*)(UINT64_MAX-7);break;
   case 15:g->sources.p=b+2048;break;case 16:g->sources.p=g;break;case 17:g->sources.p=r;break;
   case 18:s->path=(Slice){NULL,1};break;case 19:s->bytes=(Slice){(void*)(UINT64_MAX-1),8};break;
   case 20:s->path=(Slice){b+2048,1};break;case 21:s->bytes=(Slice){b+2048,1};break;
   case 22:s->path=(Slice){g,1};break;case 23:s->bytes=(Slice){r,1};break;
   case 24:pool[15].n=UINT64_MAX;break;case 25:pool[15].p=NULL;break;
   case 26:pool[15].p=(void*)(UINT64_MAX-7);break;case 27:pool[15].p=b+1025;break;
   case 28:pool[15].p=b+1024;break;case 29:pool[15].p=b+1016;break;
   case 30:pool[15].p=b+9216;break;case 31:pool[15]=(Slice){b+9208,1};break;
   case 32:pool[1].p=pool[0].p;break;case 33:pool[0].n=2;break;
   case 34:s->bytes=(Slice){g,1};break;case 35:s->path=(Slice){r,1};break;
   case 36:pool[12].p=(char*)pool[12].p+2;break;
   case 37:pool[0].p=(void*)8;break;
   case 38:g->arena.n=1;break;
  }
  memcpy(saved,raw,sizeof(raw));CHECK(compact_graph(gp,rp)==1);CHECK(!memcmp(raw,saved,sizeof(raw)));count++;
 }
 return count;
}
int main(int argc,char**argv){
 CHECK(argc==2);unsigned inv=invalid();
 char text[]="module a; struct Pair{a:u64,b:u64} const K:u64=7; pub fn choose(x:u64)u64{if x>2{return x+K;}return 3;} pub fn size()usize{return sizeof(Pair);}";
 const char path[]="a.dg";Source cat={0,{path,sizeof(path)-1},{text,sizeof(text)-1}};
 const Source*s=readonly_copy(&cat,sizeof(cat));Options options={0,1,32};Limits limits={{2048,2048,4096,64,2080,4096,65536,65536,2048,65536}};
 const uint64_t cap=16*1024*1024;unsigned char*storage=alloc(cap);Result fr;
 CHECK(!dong_frontend_check(&options,s,1,&limits,storage,cap,&fr));Graph*g=&fr.graph;
 uint64_t hashes[16],counts[16];Slice*p=&g->units;for(unsigned i=0;i<16;i++){counts[i]=p[i].n;hashes[i]=hash(p[i].p,p[i].n*widths[i]);}
 uint64_t sh=hash(text,sizeof(text)),ph=hash(path,sizeof(path)),ch=hash(s,sizeof(*s)),old=g->arena.n;
 DriverLimits dl={{128,16384,4096,1024*1024,1024,128,256}};uint64_t dc=4*1024*1024,oc=1024*1024;
 void*work=alloc(dc);void*out=alloc(oc);void*before=alloc(oc);DriverResult dr;
 uint64_t mode=strtoull(argv[1],NULL,10);CHECK(!dong_native_emit(g,&dl,mode,work,dc,before,oc,&dr));uint64_t emitted=dr.written;
 CompactResult cr;memset(&cr,0xa5,sizeof(cr));CHECK(!compact_graph(g,&cr));
 CHECK(cr.old==old&&cr.retained==g->arena.n&&cr.reclaimed==old-cr.retained&&cr.reclaimed>0);
 uintptr_t cursor=(uintptr_t)g->arena.p;for(unsigned i=0;i<16;i++){
  cursor=(cursor+alignments[i]-1)&~(alignments[i]-1);CHECK((uintptr_t)p[i].p==cursor&&p[i].n==counts[i]);
  CHECK(hash(p[i].p,p[i].n*widths[i])==hashes[i]);cursor+=p[i].n*widths[i];
 }CHECK(cursor-(uintptr_t)g->arena.p==cr.retained);
 CHECK(hash(text,sizeof(text))==sh&&hash(path,sizeof(path))==ph&&hash(s,sizeof(*s))==ch);
 // Reuse all released storage immediately, proving emission has no stale scratch aliases.
 memset(storage+cr.retained,0xcc,cap-cr.retained);
 CHECK(!dong_native_emit(g,&dl,mode,work,dc,out,oc,&dr));CHECK(dr.written==emitted&&!memcmp(out,before,emitted));
 Graph saved=*g;uint64_t compact_hash=hash(storage,cap),retained=cr.retained;
 CHECK(!compact_graph(g,&cr));CHECK(cr.old==retained&&cr.retained==retained&&cr.reclaimed==0);
 CHECK(!memcmp(g,&saved,sizeof(saved))&&hash(storage,cap)==compact_hash);
 CHECK(guard(storage,cap)&&guard(work,dc)&&guard(out,oc)&&guard(before,oc));
 printf("{\"invalid\":%u,\"pools\":16,\"old_bytes\":%llu,\"retained_bytes\":%llu,\"assembly_bytes\":%llu,\"idempotent\":true}\n",inv,(unsigned long long)old,(unsigned long long)retained,(unsigned long long)emitted);
 ro_free(s,sizeof(*s));release(storage);release(work);release(out);release(before);return 0;
}
'''

class BootstrapGraphCompactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-graph-compact'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.snapshot=cls.work/'snapshot'
        for directory in ('bootstrap','std'):
            shutil.copytree(ROOT/'lang'/directory,cls.snapshot/'lang'/directory)
        (cls.snapshot/'probe.dg').write_text(WRAPPER)
        (cls.work/'probe.c').write_text(HARNESS)
        cls.hashes={str(p.relative_to(cls.snapshot)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.snapshot.rglob('*.dg')}
        cls.records=[]
    def test_native_compaction_debug_release(self):
        for mode in ('debug','release'):
            with self.subTest(mode=mode):
                asm=self.work/(mode+'.asm');obj=self.work/(mode+'.o');exe=self.work/(mode+('.exe' if os.name=='nt' else ''))
                asm.write_text(compile_file(self.snapshot/'probe.dg',roots=[self.snapshot,self.snapshot/'lang',self.snapshot/'lang/std'],mode=mode).assembly)
                commands=[[self.nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(self.nasm),'-o',obj,asm],
                          [self.cc,'-std=c11','-O2',*([] if os.name=='nt' else ['-no-pie']),self.work/'probe.c',obj,'-o',exe]]
                for i,command in enumerate(commands):
                    result=subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=180)
                    (self.work/f'{mode}-{i}.log').write_text(result.stdout+result.stderr)
                    self.assertEqual(result.returncode,0,result.stderr)
                for emitted_mode in (0,1):
                    result=subprocess.run([str(exe),str(emitted_mode)],capture_output=True,text=True,timeout=180)
                    (self.work/f'{mode}-{emitted_mode}.run.log').write_text(result.stdout+result.stderr)
                    self.assertEqual(result.returncode,0,result.stderr)
                    row=json.loads(result.stdout);self.assertEqual(row['invalid'],39);self.assertEqual(row['pools'],16)
                    self.records.append(dict(seed_mode=mode,emitted_mode=emitted_mode,**row))
    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,'work'):
            (cls.work/'summary.json').write_text(json.dumps(dict(sources=cls.hashes,records=cls.records,guest_fit_established=False),indent=2)+'\n')
