"""Native catalog-to-checked-graph integration; no host frontend in runtime."""
from __future__ import annotations
import hashlib,json,os,shutil,struct,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

ROOT=Path(__file__).resolve().parents[2]
NONE=2**64-1
FILES=['frontend.dg','frontend_diagnostics.dg','modules.dg','names.dg','binding.dg',
       'semantic_types.dg','expression.dg','syntax.dg','lexer.dg','unicode.dg',
       'constant_arithmetic.dg','type_layout.dg','bigint.dg','bigint_div.dg',
       'bigint_bits.dg','source_position.dg','diagnostic_format.dg']
STD=['core/arena.dg','core/utf8.dg']
LIMITS=[512,512,4096,32,544,1056,18432,32768,1024,32768]
HARNESS=r'''
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#else
#include <sys/mman.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef struct{const void*p;uint64_t n;} Slice;
typedef struct{uint64_t root;Slice path,bytes;} Source;
typedef struct{uint64_t entry,roots,depth;} Options;
typedef struct{uint64_t v[10];} Limits;
typedef struct{Slice arena,sources,units,tokens,strings,nodes,edges,symbols,refs,types,fields,node_types,
 values,value_states,limbs,layouts,field_offsets,info;uint64_t entry;} Graph;
typedef struct{uint64_t status,exit_code,stage,code,detail,source,offset,used;Graph graph;} Result;
typedef struct{uint64_t source,skip,ts,tc,ss,sc,ns,nc,root;} Unit;
typedef struct{uint64_t v[7];} Token;
typedef struct{uint64_t v[8];} Node;
typedef struct{uint64_t kind,unit,target,detail;} Ref;
typedef struct{uint64_t unit,name,decl,kind,flags,target;} Symbol;
_Static_assert(sizeof(Options)==24&&sizeof(Limits)==80&&sizeof(Source)==40&&sizeof(Graph)==296&&sizeof(Result)==360,"frontend ABI");
extern uint64_t ABI dong_frontend_check(const Options*,const Source*,uint64_t,const Limits*,void*,uint64_t,Result*);
extern uint64_t ABI dong_frontend_diagnostic(const Source*,uint64_t,const Result*,void*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static void fail(const char*what){fprintf(stderr,"frontend assertion: %s\n",what);exit(96);}
static void rd(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void wr(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static int filled(const void*p,uint64_t n){const uint8_t*b=p;for(uint64_t i=0;i<n;i++)if(b[i]!=0xa5)return 0;return 1;}
static void*alloc(uint64_t n){uint8_t*p=malloc(n+32);if(!p)exit(95);memset(p,0xa5,n+32);return p+16;}
static void release(void*p){free((uint8_t*)p-16);}
static int guard(const void*p,uint64_t n){return filled((const uint8_t*)p-16,16)&&filled((const uint8_t*)p+n,16);}
static void*readonly_copy(const void*p,uint64_t n){
#ifdef _WIN32
 void*q=VirtualAlloc(NULL,n?n:1,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);DWORD old;
 if(!q)exit(95);if(n)memcpy(q,p,n);if(!VirtualProtect(q,n?n:1,PAGE_READONLY,&old))exit(98);
#else
 void*q=mmap(NULL,n?n:1,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 if(q==MAP_FAILED)exit(95);if(n)memcpy(q,p,n);if(mprotect(q,n?n:1,PROT_READ))exit(98);
#endif
 return q;
}
static void ro_free(const void*p,uint64_t n){
#ifdef _WIN32
 (void)n;if(!VirtualFree((void*)p,0,MEM_RELEASE))exit(98);
#else
 if(munmap((void*)p,n?n:1))exit(98);
#endif
}
static unsigned invalid(void){
 uint64_t memory[4096],saved[4096];uint8_t*b=(uint8_t*)memory;
 Options*o=(Options*)b;Limits*l=(Limits*)(b+32);Source*s=(Source*)(b+128);Result*r=(Result*)(b+256);
 uint8_t*storage=b+1024;
 const unsigned count=24;
 for(unsigned i=0;i<count;i++){
  memset(memory,0xa5,sizeof(memory));*o=(Options){0,1,32};*l=(Limits){{32,32,128,4,64,64,128,128,32,128}};
  *s=(Source){0,{(const uint8_t*)"a.dg",4},{(const uint8_t*)"module a;",9}};
  if(i==9)s->bytes=(Slice){NULL,1};
  if(i==10)s->path=(Slice){(void*)(uintptr_t)(UINT64_MAX-1),4};
  if(i==11)s->bytes=(Slice){storage+2000,1};
  if(i==12)s->path=(Slice){storage+2000,4};
  if(i==13)o->depth=0;
  if(i==14)o->depth=257;
  if(i==15)o->entry=1;
  if(i==16)s->root=1;
  if(i==17)s->path=(Slice){(const uint8_t*)"../a.dg",7};
  if(i==18)l->v[1]=UINT64_MAX;
  if(i==19)l->v[4]=UINT64_MAX;
  if(i==20)s->bytes=(Slice){b+600,32};
  if(i==21)s->path=(Slice){b+600,32};
  memcpy(saved,memory,sizeof(memory));uint64_t z;
  switch(i){
   case 0:z=dong_frontend_check(NULL,s,1,l,storage,2048,r);break;
   case 1:z=dong_frontend_check(o,NULL,1,l,storage,2048,r);break;
   case 2:z=dong_frontend_check(o,s,UINT64_MAX,l,storage,2048,r);break;
   case 3:z=dong_frontend_check(o,s,1,NULL,storage,2048,r);break;
   case 4:z=dong_frontend_check(o,s,1,l,storage,2048,NULL);break;
   case 5:z=dong_frontend_check((Options*)(b+1),s,1,l,storage,2048,r);break;
   case 6:z=dong_frontend_check(o,s,1,l,NULL,1,r);break;
   case 7:z=dong_frontend_check(o,s,1,l,(void*)(uintptr_t)(UINT64_MAX-7),16,r);break;
   case 8:z=dong_frontend_check(o,s,1,l,storage,2048,(Result*)(storage+1904));break;
   case 22:z=dong_frontend_check(o,s,1,l,b+16,2048,r);break;
   case 23:z=dong_frontend_check(o,s,1,l,storage,2048,(Result*)(uintptr_t)(UINT64_MAX-7));break;
   default:z=dong_frontend_check(o,s,1,l,storage,2048,r);break;
  }
  if(z!=1||memcmp(memory,saved,sizeof(memory)))fail("INVALID changed output or returned wrong status");
 }
 return count;
}
static int in_arena(Slice v,uint64_t width,Slice arena){
 if(v.n>UINT64_MAX/width)return 0;uint64_t p=(uintptr_t)v.p,a=(uintptr_t)arena.p,n=v.n*width;
 return p>=a&&p-a<=arena.n&&n<=arena.n-(p-a);
}
static void checked_graph(const Result*r,const Source*s,uint64_t sn){
 const Graph*g=&r->graph;const Slice*all=&g->arena;
 if(r->status||r->exit_code||g->entry||g->sources.p!=s||g->sources.n!=sn||!g->units.n)fail("published graph header");
 const uint64_t width[]={1,40,72,56,1,64,32,48,32,72,24,8,40,1,4,16,8,24};
 for(unsigned i=2;i<18;i++)if(!in_arena(all[i],width[i],g->arena))fail("published graph range");
 if(g->refs.n!=g->nodes.n||g->node_types.n!=g->nodes.n||g->info.n!=g->nodes.n
  ||g->values.n!=g->nodes.n||g->value_states.n!=g->nodes.n||g->layouts.n!=g->types.n
  ||g->field_offsets.n!=g->fields.n||g->types.n<9)fail("published graph counts");
 const Unit*u=g->units.p;const Token*t=g->tokens.p;const Node*n=g->nodes.p;const Ref*refs=g->refs.p;const Symbol*sy=g->symbols.p;
 for(uint64_t i=0;i<g->units.n;i++){
  if(u[i].source>=sn||u[i].ts>g->tokens.n||u[i].tc>g->tokens.n-u[i].ts||u[i].ns>g->nodes.n||u[i].nc>g->nodes.n-u[i].ns
   ||u[i].root>=u[i].nc||u[i].skip>s[u[i].source].bytes.n)fail("unit prefix");
  for(uint64_t j=0;j<u[i].tc;j++){Token z=t[u[i].ts+j];if(z.v[1]>z.v[2]||z.v[2]>s[u[i].source].bytes.n-u[i].skip)fail("token source");}
  for(uint64_t j=0;j<u[i].nc;j++){Node z=n[u[i].ns+j];if(z.v[1]>=u[i].tc)fail("node token");}
 }
 for(uint64_t i=0;i<g->symbols.n;i++)if(sy[i].unit>=g->units.n||sy[i].name>=u[sy[i].unit].tc||sy[i].decl>=u[sy[i].unit].nc)fail("symbol target");
 for(uint64_t i=0;i<g->refs.n;i++){
  Ref x=refs[i];if(x.kind==1&&(x.unit>=g->units.n||x.target>=u[x.unit].nc))fail("local ref");
  if(x.kind==2&&x.target>=g->symbols.n)fail("global ref");
 }
}
static void empty_graph(const Result*r){const Slice*p=&r->graph.arena;for(unsigned i=0;i<18;i++)if(p[i].p||p[i].n)fail("failure published graph");if(r->graph.entry!=UINT64_MAX)fail("failure entry");}
static void invalid_diagnostic(const Source*s,uint64_t sn,const Result*r){
 uint64_t raw[512],saved[512];uint8_t*out=(uint8_t*)raw;uint64_t*written=raw+500;
 for(unsigned i=0;i<8;i++){
  memset(raw,0xa5,sizeof(raw));memcpy(saved,raw,sizeof(raw));uint64_t z;
  switch(i){
   case 0:z=dong_frontend_diagnostic(s,sn,NULL,out,128,written);break;
   case 1:z=dong_frontend_diagnostic(s,sn,r,out,128,NULL);break;
   case 2:z=dong_frontend_diagnostic(s,sn,r,out,128,(uint64_t*)(out+1));break;
   case 3:z=dong_frontend_diagnostic(s,sn,r,out,128,(uint64_t*)(out+120));break;
   case 4:z=dong_frontend_diagnostic(s,sn,r,(void*)s[0].bytes.p,s[0].bytes.n,written);break;
   case 5:z=dong_frontend_diagnostic(s,sn,r,(void*)r,sizeof(*r),written);break;
   case 6:z=dong_frontend_diagnostic(NULL,1,r,out,128,written);break;
   default:z=dong_frontend_diagnostic(s,UINT64_MAX,r,out,128,written);break;
  }
  if(z!=1||memcmp(raw,saved,sizeof(raw)))fail("diagnostic INVALID");
 }
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t inv=invalid(),count;rd(&count,8);wr(&inv,8);
 while(count--){
  uint64_t h[17];rd(h,sizeof(h));Options o={h[0],h[1],h[2]};uint64_t sn=h[3];Limits l;memcpy(&l,h+4,sizeof(l));
  uint64_t cap=h[14],dcap=h[15],shift=h[16];if(sn>4096||cap>1024ULL*1024*1024||dcap>65536||shift>1)exit(94);
  Source*catalog=calloc(sn?sn:1,sizeof(Source));if(!catalog)exit(95);
  for(uint64_t i=0;i<sn;i++){
   uint64_t sh[3];rd(sh,sizeof(sh));if(sh[1]>65536||sh[2]>16000000)exit(94);
   uint8_t*p=malloc(sh[1]+1),*b=malloc(sh[2]+1);if(!p||!b)exit(95);rd(p,sh[1]);rd(b,sh[2]);
   catalog[i]=(Source){sh[0],{readonly_copy(p,sh[1]),sh[1]},{readonly_copy(b,sh[2]),sh[2]}};free(p);free(b);
  }
  const Source*s=readonly_copy(catalog,sn*sizeof(Source));const Options*op=readonly_copy(&o,sizeof(o));const Limits*lp=readonly_copy(&l,sizeof(l));
  uint8_t*back=alloc(cap+shift);uint8_t*storage=back+shift;Result*r=alloc(sizeof(Result));uint8_t*diagnostic=alloc(dcap);uint64_t written=UINT64_MAX;
  uint64_t returned=dong_frontend_check(op,s,sn,lp,storage,cap,r);Result first=*r;
  if(returned==1){if(!filled(r,sizeof(*r))||!filled(back,cap+shift))fail("invalid regular call");}
  else{
   if(returned!=r->status||r->used>cap)fail("status/arena count");
   if(!returned)checked_graph(r,s,sn);else empty_graph(r);
   if(!filled(storage+r->used,cap-r->used))fail("arena unused tail");
  }
  if(!guard(back,cap+shift)||!filled(back,shift)||!guard(r,sizeof(*r)))fail("frontend guards");
  uint8_t*saved=malloc(cap+shift+1);if(!saved)exit(95);memcpy(saved,back,cap+shift);
  // Reuse exactly the same storage for the next compilation. No stale state may
  // survive: caller discards the previous graph, then starts a new arena lifetime.
  memset(back,0xa5,cap+shift);memset(r,0xa5,sizeof(*r));
  uint64_t second=dong_frontend_check(op,s,sn,lp,storage,cap,r);
  if(second!=returned||memcmp(r,&first,sizeof(first))||memcmp(back,saved,cap+shift))fail("arena reuse changed result");
  free(saved);
  uint64_t dstatus=1;
  if(returned>1){
   const Result*ro=readonly_copy(r,sizeof(*r));invalid_diagnostic(s,sn,ro);
   dstatus=dong_frontend_diagnostic(s,sn,ro,diagnostic,dcap,&written);ro_free(ro,sizeof(*r));
   if(dstatus&&(!filled(diagnostic,dcap)||written!=UINT64_MAX))fail("diagnostic failure atomicity");
   if(!dstatus&&(written>dcap||!filled(diagnostic+written,dcap-written)))fail("diagnostic tail");
  }
  if(!guard(diagnostic,dcap)||!guard(back,cap+shift)||!guard(r,sizeof(*r)))fail("final guards");
  uint64_t row[31];row[0]=returned;memcpy(row+1,r,64);
  const Slice*gs=&r->graph.arena;for(unsigned i=0;i<18;i++)row[9+i]=gs[i].n;
  row[27]=r->graph.entry;row[28]=dstatus;row[29]=dstatus?0:written;row[30]=1;wr(row,sizeof(row));if(!dstatus)wr(diagnostic,written);
  ro_free(op,sizeof(o));ro_free(lp,sizeof(l));ro_free(s,sn*sizeof(Source));
  for(uint64_t i=0;i<sn;i++){ro_free(catalog[i].path.p,catalog[i].path.n);ro_free(catalog[i].bytes.p,catalog[i].bytes.n);}
  free(catalog);release(back);release(r);release(diagnostic);
 }
 return 0;
}
'''

def fingerprint(root):
    paths=[root/'lang/bootstrap'/p for p in FILES]+[root/'lang/std'/p for p in STD]
    paths += [ROOT/'lang/tests/test_bootstrap_frontend.py',ROOT/'lang/bootstrap/frontend.md',ROOT/'lang/bootstrap/frontend_diagnostics.md']
    paths += sorted((ROOT/'lang/dongc').glob('*.py'))
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

def case(body='',*,files=None,roots=1,entry=0,depth=32,limits=None,capacity=2_000_000,diagnostic=2048,shift=0):
    files=files or [(0,'a.dg','module a;'+body)]
    return dict(files=[(r,p.encode() if isinstance(p,str) else p,b.encode() if isinstance(b,str) else b) for r,p,b in files],
                roots=roots,entry=entry,depth=depth,limits=list(limits or LIMITS),capacity=capacity,diagnostic=diagnostic,shift=shift)

def budget(c):
    """Independent explicit byte-size model; allocator addresses are 16-aligned."""
    t,n,s,e,nt,nf,limbs,text,eo,ew=c['limits'];sn=len(c['files']);d=c['depth']
    specs=[(sn,72,8),(t,56,8),(s,1,1),(n,64,8),(e,32,8),(sn,1,1),
      (n,48,8),(n,48,8),(n,32,8),(n,32,8),(n,40,8),
      (nt,72,8),(nf,24,8),(n,8,8),(n,40,8),(n,1,1),(n,1,1),(limbs,4,4),(text,1,1),
      (8,56,8),(8,64,8),(eo,4,4),(ew,4,4),(nt,8,8),(nt,8,8),(nt,56,8),(nf,8,8),
      (nt,16,8),(nf,8,8),(nt,16,8),(nf,8,8),(nt,1,1),(nt,16,8),(nf,8,8),(nt,1,1),
      (n,24,8),(n,1,1),(2*((n+7)//8)*d,1,1),(((n+7)//8)*d,1,1),(d,1,1)]
    at=c['shift']
    for count,width,align in specs:at=(at+align-1)//align*align+count*width
    return at-c['shift']

class BootstrapFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native frontend requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-frontend'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.before=fingerprint(ROOT);cls.records=[]
        cls.snapshot=cls.work/'snapshot';(cls.snapshot/'lang/bootstrap').mkdir(parents=True)
        (cls.snapshot/'lang/std/core').mkdir(parents=True)
        for p in FILES:shutil.copyfile(ROOT/'lang/bootstrap'/p,cls.snapshot/'lang/bootstrap'/p)
        for p in STD:shutil.copyfile(ROOT/'lang/std'/p,cls.snapshot/'lang/std'/p)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8')
        cls.executables={m:cls.build(cls.snapshot,m,m) for m in ('debug','release')}
    @classmethod
    def build(cls,root,mode,label):
        asm=cls.work/(label+'.asm')
        assembly=compile_file(root/'lang/bootstrap/frontend_diagnostics.dg',roots=[root/'lang',root/'lang/std'],mode=mode).assembly
        asm.write_text(assembly,encoding='utf-8')
        obj=cls.work/(label+'.o');exe=cls.work/(label+('.exe' if os.name=='nt' else ''))
        native='win64' if os.name=='nt' else 'elf64'
        commands=[]
        formats=(native,) if 'skip-semantics' in label or 'wrong-source' in label else ('elf64','win64')
        for fmt in formats:
            out=obj if fmt==native else cls.work/(label+'.'+fmt+'.o')
            commands.append([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',out,asm])
        commands.append([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
                         *([] if os.name=='nt' else ['-no-pie']),cls.work/'probe.c',obj,'-o',exe])
        for i,command in enumerate(commands):
            r=subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=180)
            (cls.work/f'{label}-{i}.log').write_text(r.stdout+r.stderr)
            if r.returncode:raise AssertionError((label,r.returncode,r.stdout,r.stderr))
        return exe
    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        after=fingerprint(ROOT)
        artifacts={str(p.relative_to(cls.work)):hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in cls.work.rglob('*') if p.is_file() and p.name!='summary.json'}
        (cls.work/'summary.json').write_text(json.dumps(dict(before=cls.before,after=after,source_stable=cls.before==after,
          records=cls.records,artifacts=artifacts,full_compiler=False,L3_selfhost_complete=False,OS_VM_built=False),indent=2)+'\n')
    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:
            payload.extend(struct.pack('<17Q',c['entry'],c['roots'],c['depth'],len(c['files']),*c['limits'],c['capacity'],c['diagnostic'],c['shift']))
            for root,path,raw in c['files']:
                payload.extend(struct.pack('<3Q',root,len(path),len(raw)));payload.extend(path);payload.extend(raw)
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=180)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr.decode(errors='replace'))
        self.assertEqual(struct.unpack_from('<Q',run.stdout)[0],24)
        rows=[];at=8
        for c in cases:
            row=struct.unpack_from('<31Q',run.stdout,at);at+=31*8
            text=run.stdout[at:at+row[29]];at+=row[29]
            self.assertEqual(row[30],1)
            rows.append((row,text))
        self.assertEqual(at,len(run.stdout))
        self.records.append(dict(label=label,cases=len(cases),executed=True,readonly=True,guards=True,repeated=True))
        return rows
    def test_native_pipeline_and_diagnostics(self):
        cases=[
          case('pub fn f(x:u64)u64{return x+1;}'),
          case(files=[(0,'a.dg','module a;import b;fn f()u64{return b.value();}'),(1,'b.dg','module b;pub fn value()u64{return 7;}')],roots=2),
          case(files=[(0,'a.dg','\ufeffmodule a;\r\nfn 中文()u64{\n return unknown;\n}')]),
          case(files=[(0,'a.dg',b'\xef\xbb\xbfmodule a;\n// \xe4\xb8\xad\n\xff')]),
          case('fn f()u64{return ;}'),
          case('fn f()u64{return 1;}fn f()u64{return 2;}'),
          case('fn f()u64{return missing;}'),
          case('fn f()u64{return true;}'),
          case('fn f()u64{var x:u64;return x;}'),
          case('fn f(p:*u64)u64{return *p;}'),
          case('fn f()u64{let x:u64=1;x=2;return x;}'),
          case('import missing;'),
          case('fn f()u64{'),
          case('fn f()u64{let x:u64=1;}'),
          case('fn f(x:bool)u64{match x{true=>{return 1;},}}'),
          case('fn f(x:u64)u64{return try x;}'),
          case(files=[(0,'a.dg','module a;import b;fn f()u64{return b.value();}'),(0,'b.dg','module b;fn value()u64{return 7;}')]),
          case('fn f()u64{return 1;}',shift=1),
          case(files=[(0,'a.dg','module a;import b;'),(0,'b.dg','module b;'),(1,'b.dg','module b;')],roots=2),
          case(files=[(0,'a.dg','module a;import b;'),(0,'b.dg','module b;import a;')]),
          case(files=[(0,b'a\x1b.dg','module a;')]),
          case(files=[(0,b'\xff.dg','module a;')]),
          case(files=[(0,'m'+str(i)+'.dg',('module m'+str(i)+';import m'+str(i+1)+';') if i<16 else b'\xff') for i in range(17)],depth=16),
          case('fn f()u64{return "中文".len;}'),
          case(files=[(0,'a.dg','module a;import b as x;import c as x;'),(0,'b.dg','module b;'),(0,'c.dg','module c;')]),
          case('fn f()u64{\n return (((((((1)))))));\n}',depth=4),
          case(files=[(0,'a.dg',b'module a;\n@\xff')]),
        ]
        expected=[(0,0,None),(0,0,None),(3,3,'E0201'),(3,1,'E0001'),(3,4,'E0301'),
          (3,2,'E0201'),(3,3,'E0201'),(3,4,'E0301'),(3,4,'E0401'),(3,4,'E0501'),
          (3,4,'E0402'),(3,1,'E0202'),(3,1,'E0101'),(3,4,'E0402'),(3,4,'E0403'),
          (3,4,'E0501'),(3,3,'E0201'),(0,0,None),(3,1,'E0202'),(3,1,'E0202'),
          (3,1,'E0202'),(3,1,'E0202'),(4,1,'E0601'),(0,0,None),(3,1,'E0201'),
          (4,1,'E0601'),(3,1,'E0001')]
        for mode,exe in self.executables.items():
            rows=self.run_cases(exe,cases,mode+'-pipeline')
            for (row,text),(status,stage,code) in zip(rows,expected):
                self.assertEqual((row[0],row[3]),(status,stage),(row,text))
                if code:self.assertIn((': '+code+': ').encode(),text);self.assertEqual(row[28],0)
                else:self.assertGreater(row[11],0)
            self.assertEqual(rows[2][1],b'a.dg:3:9: E0201: unknown name\n')
            self.assertEqual(rows[3][1],b'a.dg:3:1: E0001: source is not valid UTF-8\n')
            self.assertTrue(rows[20][1].startswith(b'<input>:'))
            self.assertTrue(rows[21][1].startswith(b'<input>:'))
            self.assertEqual(rows[22][1],b'm16.dg:1:1: E0601: module or syntax depth limit exceeded\n')
            self.assertEqual(rows[23][0][13],6)
            self.assertEqual(rows[25][1],b'a.dg:2:9: E0601: module or syntax depth limit exceeded\n')
            self.assertEqual(rows[26][1],b'a.dg:2:2: E0001: source is not valid UTF-8\n')
            for c,(row,text) in zip(cases,rows):self.assertEqual(row[8],budget(c))
    def test_capacity_atomicity_and_lifetimes(self):
        good=case('fn f()u64{return 1;}');exact=budget(good)
        cases=[dict(good,capacity=exact),dict(good,capacity=exact-1),dict(good,capacity=0)]
        for idx,value,body in [(0,1,'fn f()u64{return 7;}'),(1,1,'fn f()u64{return 7;}'),
          (4,8,'fn f()u64{return 7;}'),(5,0,'fn f(x:u64)u64{return x;}'),
          (6,0,'const X:u64=7;'),(8,0,'const X:u64=1+2;'),(9,0,'const X:u64=1+2;')]:
            c=case(body);c['limits'][idx]=value;cases.append(c)
        edge=case(files=[(0,'a.dg','module a;import b;'),(0,'b.dg','module b;')]);edge['limits'][3]=0;cases.append(edge)
        bad=case('fn f()u64{return unknown;}')
        diagnostic=b'a.dg:1:27: E0201: unknown name\n'
        cases.extend([dict(bad,diagnostic=len(diagnostic)),dict(bad,diagnostic=len(diagnostic)-1),dict(bad,diagnostic=0)])
        for mode,exe in self.executables.items():
            rows=self.run_cases(exe,cases,mode+'-capacity')
            self.assertEqual(rows[0][0][0],0)
            self.assertEqual(rows[1][0][0],2);self.assertEqual(rows[2][0][0],2)
            for row,text in rows[1:3]:self.assertEqual(row[2],2);self.assertEqual(row[11],0)
            for row,text in rows[3:-3]:self.assertEqual((row[0],row[2]),(2,2),(row,text))
            self.assertEqual(rows[-3][1],diagnostic)
            self.assertEqual(rows[-2][0][28],2);self.assertEqual(rows[-1][0][28],2)
    def test_actual_bootstrap_closure(self):
        # The actual semantic checker dependency closure, not a synthetic tiny module.
        root=self.snapshot/'lang'
        from lang.dongc.modules import Resolver
        for entry_name in ('semantic_types','frontend_diagnostics'):
            resolver=Resolver([root,root/'std']);resolver.load(root/'bootstrap'/(entry_name+'.dg'))
            files=[]
            for name,path in sorted(resolver.paths.items()):
                files.append((1 if path.is_relative_to(root/'std') else 0,name.replace('.','/')+'.dg',path.read_bytes()))
            entry_index=next(i for i,(_,p,_) in enumerate(files) if p=='bootstrap/'+entry_name+'.dg')
            # Current closures need explicit, measured budgets. Native success
            # checks compiler source but does not emit or self-build its binary.
            c=case(files=files,roots=2,entry=entry_index,depth=128,limits=[110000,100000,100000,1000,100032,200032,3202048,32768,1024,32768],capacity=180_000_000)
            for mode,exe in self.executables.items():
                row,text=self.run_cases(exe,[c],mode+'-'+entry_name+'-closure')[0]
                self.assertEqual(row[0],0,(row,text))
                self.assertEqual(row[11],len(files));self.assertGreater(row[14],50000)
                self.records.append(dict(label=mode+'-'+entry_name+'-closure-result',modules=len(files),source_bytes=sum(len(f[2]) for f in files),
                  status=row[0],stage=row[3],code=row[4],diagnostic=text.decode(),arena_bytes=row[8],nodes=row[14],tokens=row[12]))
    def test_real_dong_negative_controls(self):
        cases=[case('fn f()u64{return true;}'),case(files=[(0,'a.dg','module a;import b;fn padding(x:u64)u64{return x;}'),(0,'b.dg','module b;\nfn f()u64{return missing;}')])]
        for mode,exe in self.executables.items():
            good=self.run_cases(exe,cases,mode+'-negative-good')
            self.assertEqual(good[0][0][0],3);self.assertTrue(good[1][1].startswith(b'b.dg:2:'))
            for name,old,new,index in [
              ('skip-semantics','semantic.analyze_program(sources,units,tokens,nodes,edges,symbols,refs,&w.semantic,&w.runtime,','semantic.analyze(sources,units,tokens,nodes,edges,symbols,refs,&w.semantic,',0),
              ('wrong-source','source=u.source_index;','source=0;',1)]:
                dest=self.work/(mode+'-'+name+'-source');shutil.copytree(self.snapshot,dest)
                path=dest/'lang/bootstrap/frontend.dg';text=path.read_text();self.assertEqual(text.count(old),1)
                path.write_text(text.replace(old,new))
                badexe=self.build(dest,mode,mode+'-'+name)
                bad=self.run_cases(badexe,[cases[index]],mode+'-'+name+'-execution')[0]
                if index==0:self.assertNotEqual(bad[0][0],good[index][0][0])
                else:self.assertTrue(bad[1].startswith(b'a.dg:'));self.assertNotEqual(bad[1],good[index][1])
                self.records.append(dict(label=mode+'-'+name,mutation_built=True,mutation_executed=True,
                                         rejected_by='status' if index==0 else 'diagnostic source'))

