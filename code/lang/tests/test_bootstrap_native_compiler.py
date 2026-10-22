"""Actual source -> Dong frontend -> typed IR -> Dong NASM -> native execution."""
from __future__ import annotations
import hashlib,json,os,shutil,signal,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
ROOT=Path(__file__).resolve().parents[2]
WRAPPER='''module probe.native_compiler;
import bootstrap.frontend as front;
import bootstrap.program_ir as ir;
import bootstrap.lower_program as lower;
import bootstrap.nasm_program as backend;
export("native_lower") pub unsafe fn lower_raw(g:*const front.Graph,w:*const ir.Workspace,mode:u64,r:*ir.Result)u64{unsafe{return lower.lower(g,w,mode,r);}}
export("native_emit") pub unsafe fn emit_raw(p:*const ir.Program,w:*const backend.Workspace,out:*u8,capacity:usize,written:*usize)u64{unsafe{return backend.emit(p,w,slice_from_raw_parts(out,capacity),written);}}
'''
DRIVER=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint64_t U;
typedef struct{void*p;U n;} Slice;
typedef struct{U root;Slice path,bytes;} Source;
typedef struct{Slice arena,sources,units,tokens,strings,nodes,edges,symbols,refs,types,fields,node_types,values,value_states,limbs,layouts,field_offsets,info;U entry;} Graph;
typedef struct{U status,exit_code,stage,code,detail,source,offset,used;Graph graph;} FrontResult;
typedef struct{U entry,roots,depth;} Options;
typedef struct{U tokens,nodes,strings,edges,types,fields,limbs,text,math_limbs,math_work;} Limits;
typedef struct{U operation,typ,destination,a,b,value,extra,unit,node;} Instruction;
typedef struct{U symbol,first,count,parameter_first,parameter_count,frame_bytes,returns,trap;} Function;
typedef struct{U typ,offset;} Argument;
typedef struct{Graph*g;Slice functions,code,args;U blocks,mode;} Program;
typedef struct{U status,unit,node,detail;Program program;} LowerResult;
typedef struct{Slice functions,code,args,node_slots;} LowerWorkspace;
typedef struct{Slice text,piece,kinds,locations;} EmitWorkspace;
extern U dong_frontend_check(const Options*,const Source*,U,const Limits*,void*,U,FrontResult*);
extern U native_lower(const Graph*,const LowerWorkspace*,U,LowerResult*);
extern U native_emit(const Program*,const EmitWorkspace*,void*,U,U*);
void __dong_panic(uint32_t k,uint32_t line,const void*p,U n){(void)p;(void)n;fprintf(stderr,"seed panic %llu line %llu\n",(unsigned long long)k,(unsigned long long)line);exit(93);}
typedef struct{unsigned char *base;U bytes;} Allocation;
static Allocation allocations[32];static U allocation_count=0;
static Slice alloc(U n,U width){U bytes=n*width;unsigned char*p=calloc(1,bytes+32);if(!p)exit(94);memset(p,0xa7,16);memset(p+16+bytes,0xa7,16);allocations[allocation_count++]=(Allocation){p,bytes};return(Slice){p+16,n};}
static void guards(void){for(U i=0;i<allocation_count;i++){Allocation a=allocations[i];for(U j=0;j<16;j++)if(a.base[j]!=0xa7||a.base[16+a.bytes+j]!=0xa7){fprintf(stderr,"guard failure\n");exit(95);}}}
static U hash(const void*p,U n){const unsigned char*b=p;U h=14695981039346656037ULL;for(U i=0;i<n;i++){h^=b[i];h*=1099511628211ULL;}return h;}
static U hash_lower(const LowerWorkspace*w){return hash(w->functions.p,w->functions.n*sizeof(Function))^hash(w->code.p,w->code.n*sizeof(Instruction))^hash(w->args.p,w->args.n*sizeof(Argument))^hash(w->node_slots.p,w->node_slots.n*8);}
static U hash_emit(const EmitWorkspace*w){return hash(w->text.p,w->text.n)^hash(w->piece.p,w->piece.n)^hash(w->kinds.p,w->kinds.n)^hash(w->locations.p,w->locations.n*16);}
static int unpublished(const LowerResult*r){return !r->program.g&&!r->program.functions.n&&!r->program.code.n&&!r->program.args.n&&!r->program.blocks;}
#define REQUIRE(x) do{if(!(x)){fprintf(stderr,"contract failure line %d\n",__LINE__);return 96;}guards();}while(0)
int main(int argc,char**argv){
 if(argc!=5){return 90;}FILE*f=fopen(argv[1],"rb");if(!f)return 91;fseek(f,0,SEEK_END);long length=ftell(f);rewind(f);
 Slice source=alloc((U)length,1);if(fread(source.p,1,(size_t)length,f)!=(size_t)length)return 92;fclose(f);
 Source catalog={0,{argv[2],strlen(argv[2])},source};Options o={0,1,64};Limits l={8192,8192,65536,256,4096,4096,65536,4096,512,8192};
 Slice arena=alloc(24*1024*1024,1);FrontResult fr;memset(&fr,0,sizeof(fr));
 U rc=dong_frontend_check(&o,&catalog,1,&l,arena.p,arena.n,&fr);
 if(rc){fprintf(stderr,"frontend status=%llu stage=%llu code=%llu detail=%llu offset=%llu\n",(unsigned long long)rc,(unsigned long long)fr.stage,(unsigned long long)fr.code,(unsigned long long)fr.detail,(unsigned long long)fr.offset);return 10;}
 U arena_hash=hash(arena.p,arena.n),source_hash=hash(source.p,source.n);guards();
 LowerWorkspace lw={alloc(512,sizeof(Function)),alloc(65536,sizeof(Instruction)),alloc(8192,sizeof(Argument)),alloc(8192,8)};LowerResult lr;memset(&lr,0,sizeof(lr));
 rc=native_lower(&fr.graph,&lw,(U)strtoull(argv[4],NULL,10),&lr);
 if(rc){REQUIRE(unpublished(&lr));fprintf(stderr,"lower status=%llu node=%llu detail=%llu\n",(unsigned long long)rc,(unsigned long long)lr.node,(unsigned long long)lr.detail);return 11;}
 U mode=(U)strtoull(argv[4],NULL,10);LowerResult before=lr;U scratch_hash=hash_lower(&lw);
 REQUIRE(native_lower(&fr.graph,&lw,2,&lr)==1&&!memcmp(&lr,&before,sizeof(lr))&&scratch_hash==hash_lower(&lw));
 LowerWorkspace bad=lw;bad.code.p=source.p;bad.code.n=1;
 REQUIRE(native_lower(&fr.graph,&bad,mode,&lr)==1&&!memcmp(&lr,&before,sizeof(lr))&&scratch_hash==hash_lower(&lw));
 bad=lw;bad.functions.p=lw.code.p;
 REQUIRE(native_lower(&fr.graph,&bad,mode,&lr)==1&&!memcmp(&lr,&before,sizeof(lr))&&scratch_hash==hash_lower(&lw));
 U exact_functions=lr.program.functions.n,exact_code=lr.program.code.n,exact_args=lr.program.args.n;
 for(U which=0;which<4;which++){bad=lw;
  if(which==2&&exact_args==0){
   LowerResult preserved=lr;U whole=hash_lower(&lw);bad.args.n=UINT64_MAX;
   REQUIRE(native_lower(&fr.graph,&bad,mode,&lr)==1&&!memcmp(&lr,&preserved,sizeof(lr))&&whole==hash_lower(&lw));continue;
  }
  if(which==0){bad.functions.n=exact_functions-1;}
  if(which==1){bad.code.n=exact_code-1;}
  if(which==2){bad.args.n=exact_args-1;}
  if(which==3){bad.node_slots.n=fr.graph.nodes.n-1;}
  REQUIRE(native_lower(&fr.graph,&bad,mode,&lr)==2&&unpublished(&lr));}
 lw.functions.n=exact_functions;lw.code.n=exact_code;lw.args.n=exact_args;lw.node_slots.n=fr.graph.nodes.n;
 REQUIRE(native_lower(&fr.graph,&lw,mode,&lr)==0);
 U code_hash=hash(lw.code.p,lw.code.n*sizeof(Instruction)),args_hash=hash(lw.args.p,lw.args.n*sizeof(Argument)),function_hash=hash(lw.functions.p,lw.functions.n*sizeof(Function));
 EmitWorkspace ew={alloc(4*1024*1024,1),alloc(1024,1),alloc(128,1),alloc(256,16)};Slice out=alloc(4*1024*1024,1);U written=0;
 rc=native_emit(&lr.program,&ew,out.p,out.n,&written);
 if(rc){fprintf(stderr,"emit status=%llu\n",(unsigned long long)rc);return 12;}
 U exact=written;Slice snapshot=alloc(exact,1);memcpy(snapshot.p,out.p,exact);memset(out.p,0xa9,out.n);U out_hash=hash(out.p,out.n);written=999;
 REQUIRE(native_emit(&lr.program,&ew,out.p,exact-1,&written)==2&&written==999&&out_hash==hash(out.p,out.n));
 if(exact_args==0){
  for(U spare=0;spare<2;spare++){
   EmitWorkspace unused=ew;if(spare==0){unused.kinds.n=0;}else{unused.locations.n=0;}
   REQUIRE(native_emit(&lr.program,&unused,out.p,out.n,&written)==0&&written==exact&&!memcmp(out.p,snapshot.p,exact));
   memset(out.p,0xa9,exact);REQUIRE(out_hash==hash(out.p,out.n));written=999;
  }
 }
 for(U which=0;which<4;which++){if(exact_args==0&&which>=2){continue;}EmitWorkspace badw=ew;if(which==0)badw.text.n=exact-1;if(which==1)badw.piece.n=1023;if(which==2)badw.kinds.n=0;if(which==3)badw.locations.n=0;
  REQUIRE(native_emit(&lr.program,&badw,out.p,out.n,&written)==2&&written==999&&out_hash==hash(out.p,out.n));}
 U emit_hash=hash_emit(&ew);
 REQUIRE(native_emit(&lr.program,&ew,source.p,source.n,&written)==1&&written==999);
 REQUIRE(native_emit(&lr.program,&ew,ew.text.p,ew.text.n,&written)==1&&written==999);
 REQUIRE(native_emit(&lr.program,&ew,out.p,out.n,(U*)out.p)==1&&out_hash==hash(out.p,out.n));
 EmitWorkspace badw=ew;badw.piece=badw.text;
 REQUIRE(native_emit(&lr.program,&badw,out.p,out.n,&written)==1&&written==999&&out_hash==hash(out.p,out.n));
 REQUIRE(emit_hash==hash_emit(&ew));
 ew.text.n=exact;REQUIRE(native_emit(&lr.program,&ew,out.p,exact,&written)==0&&written==exact&&!memcmp(out.p,snapshot.p,exact));
 for(U i=exact;i<out.n;i++){if(((unsigned char*)out.p)[i]!=0xa9)return 97;}guards();
 REQUIRE(arena_hash==hash(arena.p,arena.n)&&source_hash==hash(source.p,source.n)&&code_hash==hash(lw.code.p,lw.code.n*sizeof(Instruction))&&args_hash==hash(lw.args.p,lw.args.n*sizeof(Argument))&&function_hash==hash(lw.functions.p,lw.functions.n*sizeof(Function)));
 f=fopen(argv[3],"wb");if(!f)return 13;if(fwrite(out.p,1,(size_t)written,f)!=written)return 14;fclose(f);
 printf("{\"functions\":%llu,\"instructions\":%llu,\"arguments\":%llu,\"bytes\":%llu}\n",(unsigned long long)lr.program.functions.n,(unsigned long long)lr.program.code.n,(unsigned long long)lr.program.args.n,(unsigned long long)written);return 0;
}
'''
OBSERVER=r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t U;typedef struct{const unsigned char*p;U n;} Slice;
typedef struct{U kind,offset,expected,actual;} Result;
extern U compare_native(Slice,Slice,Result*) __asm__("__dong_m626f6f7473747261702e61727469666163745f636f6d70617265_n636f6d70617265");
static U seed=0x735498dc872359abULL;static U random64(void){seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;return seed;}
static Result reference(Slice a,Slice b){U n=a.n<b.n?a.n:b.n;Result r={0,n,256,256};
 for(U i=0;i<n;i++){if(a.p[i]!=b.p[i])return(Result){1,i,a.p[i],b.p[i]};}
 if(a.n!=b.n){r.kind=2;if(a.n<b.n)r.actual=b.p[n];else r.expected=a.p[n];}return r;}
int main(void){unsigned char a[66],b[66],sa[66],sb[66];U runs=0;
 for(U trial=0;trial<1000;trial++){
  for(U i=0;i<66;i++){a[i]=(unsigned char)random64();}memcpy(b,a,66);
  U an=random64()%65,bn=random64()%65;if(trial%3==0)bn=an;if(trial%4==0&&bn)b[1+random64()%bn]^=127;
  memcpy(sa,a,66);memcpy(sb,b,66);Slice x={a+1,an},y={b+1,bn};Result want=reference(x,y);
  struct{U left;Result result;U right;} out={0x7354,{9,9,9,9},0x6721};
  U code=compare_native(x,y,&out.result);
  if(code||memcmp(&out.result,&want,32)||out.left!=0x7354||out.right!=0x6721||memcmp(a,sa,66)||memcmp(b,sb,66)){fprintf(stderr,"value failure trial %llu\n",(unsigned long long)trial);return 2;}runs++;
 }
 Result before={15,16,17,18},r=before;Slice empty={NULL,0};
 if(compare_native(empty,empty,NULL)!=1)return 3;
 if(compare_native((Slice){NULL,1},empty,&r)!=1||memcmp(&r,&before,32))return 4;
 if(compare_native((Slice){(void*)UINT64_MAX,2},empty,&r)!=1||memcmp(&r,&before,32))return 5;
 if(compare_native((Slice){(void*)&r,1},empty,&r)!=1||memcmp(&r,&before,32))return 6;
 if(compare_native(empty,empty,&r)||r.kind||r.offset||r.expected!=256||r.actual!=256)return 7;
 printf("{\"vectors\":%llu,\"invalid\":4}\n",(unsigned long long)runs);return 0;
}
'''
AUDIT='''module audit;
pub fn cast8(x:i8)i64{return x as i64;}
fn pair(s:[]const u8)[]const u8{return s;}
fn sum(a:[]const u8,b:[]const u8)u64{return a.len*100+b.len;}
pub fn nested(a:[]const u8,b:[]const u8)u64{return sum(pair(a),pair(b));}
fn many(a:[]const u8,b:[]const u8,c:[]const u8,d:[]const u8,e:[]const u8,f:[]const u8,g:[]const u8,h:[]const u8,i:[]const u8,x:u64,y:u64)u64{return a.len+b.len+c.len+d.len+e.len+f.len+g.len+h.len+i.len+x+y;}
pub fn twenty(s:[]const u8)u64{return many(s,s,s,s,s,s,s,s,s,1,2);}
fn spare(a:u64,b:u64,c:u64,d:u64,e:u64,s:[]const u8,z:u64)u64{return a+b+c+d+e+s.len+z;}
pub fn whole_pair(s:[]const u8)u64{return spare(1,2,3,4,5,s,6);}
unsafe fn advance(p:**u64,n:*u64)*u64{unsafe{let old=*p;*p=old+1;*n+=1;return old;}}
pub unsafe fn once(p:**u64,n:*u64)u64{unsafe{*advance(p,n)=wrapping_add(5 as u64,2 as u64);return *n;}}
pub unsafe fn memory(p:*i8,q:*u16,index:usize)i64{unsafe{let value=p[index];q[index]=513;return value as i64;}}
pub fn overflow(x:u64)u64{return x+1;}
pub fn sub(x:u64,y:u64)u64{return x-y;}
pub fn signed_div(x:i8,y:i8)i8{return x/y;}
pub fn negu(x:u64)u64{return -x;}
pub fn negi(x:i64)i64{return -x;}
pub fn neg8(x:i8)i8{return -x;}
pub fn narrow_add(x:u8)u8{return x+1;}
pub fn shift(x:u64,n:usize)u64{return x<<n;}
pub fn readindex(s:[]const u64,i:usize)u64{return s[i];}
pub unsafe fn pointer(p:*u64,i:usize)*u64{unsafe{return p+i;}}
pub fn wrapped(x:u64)u64{return wrapping_add(x,1 as u64);}
pub fn shorted(a:bool,p:*u64)bool{unsafe{return a&&*p==1;}}
'''
# Symbols are derived only for independently calling the generated artifact.
def label(module,name):return '__dong_m'+module.encode().hex()+'_n'+name.encode().hex()
AUDIT_OBSERVER=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint64_t U;typedef struct{const void*p;U n;} Slice;
#define DECL(ret,name,args) extern ret name args __asm__("SYMBOL_" #name)
DECL(int64_t,cast8,(int8_t));DECL(U,nested,(Slice,Slice));DECL(U,twenty,(Slice));DECL(U,whole_pair,(Slice));DECL(U,once,(U**,U*));DECL(int64_t,memory,(int8_t*,uint16_t*,U));
DECL(U,overflow,(U));DECL(U,sub,(U,U));DECL(int8_t,signed_div,(int8_t,int8_t));DECL(U,negu,(U));DECL(int64_t,negi,(int64_t));DECL(int8_t,neg8,(int8_t));DECL(uint8_t,narrow_add,(uint8_t));DECL(U,shift,(U,U));DECL(U,readindex,(Slice,U));DECL(U*,pointer,(U*,U));DECL(U,wrapped,(U));DECL(_Bool,shorted,(_Bool,U*));
extern U abi_probe(void*,U,U,U);
#define CHECK(x) do{if(!(x)){fprintf(stderr,"audit value failure line %d\n",__LINE__);return 2;}}while(0)
int main(int argc,char**argv){
 const char*test=argc>1?argv[1]:"normal";int release=argc>2?atoi(argv[2]):0;unsigned char bytes[7]={0};U a[3]={1,2,3};
 if(!strcmp(test,"add")){CHECK(overflow(UINT64_MAX)==0);return 0;}
 if(!strcmp(test,"sub")){CHECK(sub(0,1)==UINT64_MAX);return 0;}
 if(!strcmp(test,"neg-one")){CHECK(negu(1)==UINT64_MAX);return 0;}
 if(!strcmp(test,"neg-max")){CHECK(negu(UINT64_MAX)==1);return 0;}
 if(!strcmp(test,"neg-min")){CHECK(negi(INT64_MIN)==INT64_MIN);return 0;}
 if(!strcmp(test,"neg8")){CHECK(neg8(INT8_MIN)==INT8_MIN);return 0;}
 if(!strcmp(test,"narrow")){CHECK(narrow_add(255)==0);return 0;}
 if(!strcmp(test,"bounds")){(void)readindex((Slice){a,3},3);return 3;}
 if(!strcmp(test,"shift")){(void)shift(1,64);return 3;}
 if(!strcmp(test,"divide")){(void)signed_div(-128,-1);return 3;}
 if(!strcmp(test,"divide-zero")){(void)signed_div(1,0);return 3;}
 CHECK(abi_probe((void*)cast8,(U)-128,0,(U)-128)&&abi_probe((void*)twenty,(U)bytes,5,48)&&abi_probe((void*)whole_pair,(U)bytes,5,26));
 CHECK(cast8(-128)==-128&&cast8(127)==127);CHECK(nested((Slice){bytes,3},(Slice){bytes,2})==302);CHECK(twenty((Slice){bytes,5})==48);CHECK(whole_pair((Slice){bytes,5})==26);
 U *p=a,n=0;CHECK(once(&p,&n)==1&&p==a+1&&n==1&&a[0]==7&&a[1]==2&&a[2]==3);
 int8_t signed_bytes[3]={66,-128,77};uint16_t shorts[3]={0xabcd,0,0x1234};CHECK(memory(signed_bytes,shorts,1)==-128&&shorts[0]==0xabcd&&shorts[1]==513&&shorts[2]==0x1234);
 CHECK(signed_div(-128,2)==-64&&signed_div(127,-2)==-63);CHECK(negu(0)==0&&negi(-1)==1&&neg8(-127)==127);CHECK(overflow(4)==5&&sub(4,2)==2&&narrow_add(254)==255&&shift(1,63)==(1ULL<<63));
 CHECK(readindex((Slice){a,3},2)==3&&wrapped(UINT64_MAX)==0&&!shorted(0,NULL));
 // Unsafe pointer arithmetic deliberately wraps like the seed in both modes.
 CHECK(pointer(a,UINT64_MAX/8+1)==a&&pointer(a,1)==a+1);
 printf("{\"audit\":true,\"release\":%d,\"abi_words\":20}\n",release);return 0;
}
'''
# Turn the explicit independent declarations into exact Dong mangled symbols.
import re
AUDIT_OBSERVER=re.sub(r'DECL\(([^,]+),(\w+),(\([^;]+)\);',lambda m:f'extern {m[1]} {m[2]} {m[3]} __asm__("{label("audit",m[2])}");',AUDIT_OBSERVER)
ABI_PROBE=r'''bits 64
section .text
global abi_probe
abi_probe:
 push rbp
 push rbx
 push r12
 push r13
 push r14
 push r15
 sub rsp,40
 mov [rsp],rdi
 mov [rsp+8],rsi
 mov [rsp+16],rdx
 mov [rsp+24],rcx
 mov [rsp+32],rsp
 mov ebp,0x12345678
 mov ebx,0x23456789
 mov r12d,0x3456789a
 mov r13d,0x456789ab
 mov r14d,0x56789abc
 mov r15d,0x6789abcd
 mov rax,[rsp]
 mov rdi,[rsp+8]
 mov rsi,[rsp+16]
 call rax
 cmp rax,[rsp+24]
 jne .bad
 cmp rsp,[rsp+32]
 jne .bad
 cmp rbp,0x12345678
 jne .bad
 cmp rbx,0x23456789
 jne .bad
 cmp r12,0x3456789a
 jne .bad
 cmp r13,0x456789ab
 jne .bad
 cmp r14,0x56789abc
 jne .bad
 cmp r15,0x6789abcd
 jne .bad
 mov eax,1
 jmp .done
.bad:
 xor eax,eax
.done:
 add rsp,40
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbx
 pop rbp
 ret
section .note.GNU-stack noalloc noexec nowrite progbits
'''
class NativeCompilerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
  if not cls.nasm or not cls.cc:raise RuntimeError('NASM and GCC are required')
  cls.work=ROOT/'build/test/bootstrap-native-compiler'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
  cls.records=[];cls.drivers={};cls.closure_inputs={}
  cls.inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*sorted((ROOT/'lang/bootstrap').glob('*.dg')),*sorted((ROOT/'lang/dongc').glob('*.py')),Path(__file__)]}
  (cls.work/'probe').mkdir();(cls.work/'probe/native_compiler.dg').write_text(WRAPPER);(cls.work/'driver.c').write_text(DRIVER);(cls.work/'observer.c').write_text(OBSERVER);(cls.work/'audit.dg').write_text(AUDIT);(cls.work/'audit.c').write_text(AUDIT_OBSERVER);(cls.work/'abi.asm').write_text(ABI_PROBE)
  cls.command([cls.nasm,'-f','elf64',*nasm_flags(cls.nasm),'-o',cls.work/'abi.o',cls.work/'abi.asm'],'abi-assemble')
 @classmethod
 def command(cls,args,name):
  p=subprocess.run([str(x) for x in args],cwd=ROOT,text=True,capture_output=True,timeout=180)
  (cls.work/(name+'.log')).write_text(p.stdout+p.stderr)
  cls.records.append({'name':name,'command':[str(x) for x in args],'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
  if p.returncode:raise AssertionError(f'{name}: {p.returncode}\n{p.stdout}\n{p.stderr}')
  return p.stdout
 @classmethod
 def build(cls,mode,root=None,label=None):
  label=label or mode
  asm=cls.work/(label+'.asm');obj=asm.with_suffix('.o');exe=cls.work/(label+'.exe')
  roots=[cls.work,root or ROOT/'lang',ROOT/'lang/std']
  before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for r in roots for p in r.rglob('*.dg')}
  compiled=compile_file(cls.work/'probe/native_compiler.dg',roots=roots,mode=mode)
  closure={}
  for source in compiled.sources:
   path=next(r/source for r in roots if (r/source).is_file());key=str(path);digest=hashlib.sha256(path.read_bytes()).hexdigest()
   if digest!=before[key]:raise AssertionError('compiler source changed during build: '+key)
   if key in cls.closure_inputs and cls.closure_inputs[key]!=digest:raise AssertionError('compiler source changed between builds: '+key)
   cls.closure_inputs[key]=digest;closure[key]=digest
  cls.records.append({'name':label+'-source-provenance','closure':closure,'assembly_sha256':hashlib.sha256(compiled.assembly.encode()).hexdigest()})
  asm.write_text(compiled.assembly)
  for fmt,suffix in [('elf64','.o'),('win64','.obj')]:cls.command([cls.nasm,'-O0','-f',fmt,*nasm_flags(cls.nasm),'-o',asm.with_suffix(suffix),asm],label+'-'+fmt)
  cls.command([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-no-pie',cls.work/'driver.c',obj,'-o',exe],label+'-link')
  return exe
 @classmethod
 def driver(cls,mode):
  if mode not in cls.drivers:cls.drivers[mode]=cls.build(mode)
  return cls.drivers[mode]
 def test_unchanged_artifact_compare_source(self):
  for mode in ('debug','release'):
   exe=self.driver(mode);asm=self.work/(mode+'-artifact.asm')
   report=json.loads(self.command([exe,ROOT/'lang/bootstrap/artifact_compare.dg','bootstrap/artifact_compare.dg',asm,int(mode=='release')],mode+'-compile-artifact'))
   self.assertEqual(report['functions'],4)
   obj=asm.with_suffix('.o');self.command([self.nasm,'-f','elf64',*nasm_flags(self.nasm),'-o',obj,asm],mode+'-artifact-assemble')
   observed=self.work/(mode+'-observed.exe');self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-no-pie',self.work/'observer.c',obj,'-o',observed],mode+'-observer-link')
   result=json.loads(self.command([observed],mode+'-observe'));self.assertEqual(result['vectors'],1000)
 def generated(self,mode,source,path,name,observer,driver=None):
  asm=self.work/(name+'.asm');report=json.loads(self.command([driver or self.driver(mode),source,path,asm,int(mode=='release')],name+'-compile'))
  for fmt,suffix in [('elf64','.o'),('win64','.obj')]:self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',asm.with_suffix(suffix),asm],name+'-'+fmt)
  exe=self.work/(name+'.exe');self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-no-pie',observer,asm.with_suffix('.o'),*([self.work/'abi.o'] if observer.name=='audit.c' else []),'-o',exe],name+'-link')
  return exe,report
 def test_source_operations_abi_and_traps(self):
  for mode in ('debug','release'):
   exe,report=self.generated(mode,self.work/'audit.dg','audit.dg',mode+'-audit',self.work/'audit.c')
   result=json.loads(self.command([exe,'normal',int(mode=='release')],mode+'-audit-values'));self.assertEqual(result['abi_words'],20)
   for case in ('add','sub','neg-one','neg-max','neg-min','neg8','narrow','bounds','shift','divide','divide-zero'):
    p=subprocess.run([str(exe),case,str(int(mode=='release'))],capture_output=True,text=True,timeout=10)
    expected=-signal.SIGILL if mode=='debug' or case in ('bounds','shift','divide','divide-zero') else 0
    self.records.append({'name':mode+'-'+case,'returncode':p.returncode,'expected':expected,'stderr':p.stderr})
    self.assertEqual(p.returncode,expected,(mode,case,p.stdout,p.stderr))
 def test_aggregate_strings_static_slices(self):
  source=self.work/'aggregate.dg';source.write_text(r'''module aggregate;
struct Small{a:u8,b:u64,c:[3]u16}
const EMPTY:Small=Small{a:5,b:9,c:[11,22,33]};
const TABLE:[600]u64=[73;600];
const TEXT:[]const u8="a\n\x62";
const TEXT_ALIAS:[]const u8=TEXT;
fn identity(p:[]const u8)usize{return p.len;}
export("range_probe") pub fn range_probe(s:[]const u8,lo:usize,hi:usize)usize{let sub=s[lo..hi];return sub.len;}
export("null_probe") pub fn null_probe()*const u8{return null as *const u8;}
export("aggregate_probe") pub unsafe fn probe(out:*u64)u64{unsafe{
 var a=Small{c:[1,2,3],b:41,a:7};var b=a;b.b+=1;b.c[1]=19;
 let saved=EMPTY;var repeat:[4]Small=[saved;4];repeat[2].a=23;
 let text=TEXT_ALIAS;let sub=text[1..];let table=TABLE[598..600];
 *out=a.b+b.b+b.c[1]as u64+repeat[2].a as u64+table[1];
 return identity(sub)+sub[1]as u64+sizeof(Small)+repeat[0].c[2]as u64;
}}
''')
  observer=self.work/'aggregate.c';observer.write_text('''#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef struct{const char*p;uint64_t n;} Slice;
extern uint64_t aggregate_probe(uint64_t*);
extern uint64_t range_probe(Slice,uint64_t,uint64_t);
extern const unsigned char*null_probe(void);
int main(int argc,char**argv){
 Slice text={"abc",3};
 if(argc>1&&!strcmp(argv[1],"reversed")){(void)range_probe(text,2,1);return 3;}
 if(argc>1&&!strcmp(argv[1],"past-end")){(void)range_probe(text,3,4);return 3;}
 if(range_probe(text,3,3)!=0||null_probe()!=NULL)return 2;
 uint64_t out=0;uint64_t r=aggregate_probe(&out);if(out!=198||r!=157){fprintf(stderr,"out=%llu r=%llu\\n",(unsigned long long)out,(unsigned long long)r);return 1;}return 0;}
''')
  for mode in ('debug','release'):
   exe,_=self.generated(mode,source,'aggregate.dg',mode+'-aggregate',observer)
   self.command([exe],mode+'-aggregate-values')
   for case in ('reversed','past-end'):
    p=subprocess.run([str(exe),case],capture_output=True,text=True,timeout=10)
    self.records.append({'name':mode+'-subslice-'+case,'returncode':p.returncode,'expected':-signal.SIGILL,'stderr':p.stderr})
    self.assertEqual(p.returncode,-signal.SIGILL,(mode,case,p.stdout,p.stderr))
 def test_global_storage_is_supported(self):
  source=self.work/'global-supported.dg';source.write_text('module unsupported; var x:u64=1; pub fn f()u64{return x;}')
  observer=self.work/'global-supported.c';observer.write_text('#include <stdint.h>\nextern uint64_t f(void) __asm__("'+label('unsupported','f')+'");\nint main(void){return f()!=1;}\n')
  for mode in ('debug','release'):
   exe,_=self.generated(mode,source,'unsupported.dg',mode+'-global-supported',observer)
   self.command([exe],mode+'-global-supported-observe')
 def test_unsupported_source_fails_closed(self):
  sources={
   'extern':'module unsupported; extern "win64" fn f()u64;',
  }
  for mode in ('debug','release'):
   for case,text in sources.items():
    source=self.work/('unsupported-'+case+'.dg');source.write_text(text);out=self.work/('unsupported-'+case+'.asm');out.write_bytes(b'unchanged')
    p=subprocess.run([str(self.driver(mode)),str(source),'unsupported.dg',str(out),str(int(mode=='release'))],capture_output=True,text=True,timeout=30)
    self.records.append({'name':mode+'-unsupported-'+case,'returncode':p.returncode,'stderr':p.stderr})
    self.assertEqual(p.returncode,11,p.stderr);self.assertIn('lower status=3',p.stderr);self.assertEqual(out.read_bytes(),b'unchanged')
 def test_real_dong_mutations_are_rejected(self):
  original=(ROOT/'lang/bootstrap/lower_program.dg').read_text();needle='(*(*s).g).field_offsets[t.first+i]';self.assertEqual(original.count(needle),1)
  root=self.work/'mutant';shutil.copytree(ROOT/'lang/bootstrap',root/'bootstrap')
  (root/'bootstrap/lower_program.dg').write_text(original.replace(needle,'0'))
  for mode in ('debug','release'):
   driver=self.build(mode,root,'mutant-'+mode)
   exe,_=self.generated(mode,ROOT/'lang/bootstrap/artifact_compare.dg','bootstrap/artifact_compare.dg','mutant-'+mode+'-artifact',self.work/'observer.c',driver)
   p=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
   self.records.append({'name':'mutant-'+mode+'-oracle','returncode':p.returncode,'stderr':p.stderr})
   self.assertEqual(p.returncode,2,p.stderr);self.assertIn('value failure trial',p.stderr)
 @classmethod
 def tearDownClass(cls):
  after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in cls.inputs}
  closure_after={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in cls.closure_inputs}
  stable=cls.closure_inputs==closure_after
  (cls.work/'summary.json').write_text(json.dumps({'records':cls.records,'closure_inputs':cls.closure_inputs,'closure_after':closure_after,'stable':stable,'inventory_before':cls.inputs,'inventory_after':after,'inventory_stable':cls.inputs==after,'L3_complete':False},indent=2)+'\n')
  if not stable:raise AssertionError('active compiler inputs changed during test run')
