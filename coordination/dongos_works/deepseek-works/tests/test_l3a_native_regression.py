"""L3A native-container regression: real Dong NASM text consumed by the native
assembler, validated as ELF64 and actually executed from its program headers.

The seed Python compiler only builds the compiler.  The emitted artifact is
assembled twice by the production native assembler (default and alternate host
mapping bases) and the same observations are compared with an independent
Python byte model and with the kernel's ELF validator.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

WORKS = Path(__file__).resolve().parents[2]
ROOT = WORKS
if not (ROOT / "lang").is_dir() and (WORKS / "project.json").is_file():
    source = Path(json.loads((WORKS / "project.json").read_text(encoding="utf-8"))["source_root"])
    ROOT = source if source.is_absolute() else (WORKS / source).resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import tool, nasm_flags

CANDIDATES = ("lower_program.dg", "nasm_program.dg", "native_assembler.dg")
CAND = WORKS / "deepseek-works/l3a/src/bootstrap"
if not CAND.is_dir(): CAND = ROOT / "lang/bootstrap"
BUILD = WORKS / "deepseek-works/build/L3A" if CAND != ROOT / "lang/bootstrap" else ROOT / "build/test/L3A"
SEARCH = (("", ROOT / "lang"), ("std", ROOT / "lang" / "std"), ("", ROOT / "kernel"))
WIN = os.name == "nt"
BASE = 0x400000
PAGE = 0x1000

WRAPPER = '''module probe.l3a_native;
import bootstrap.frontend as front;
import bootstrap.program_ir as ir;
import bootstrap.lower_program as lower;
import bootstrap.nasm_program as backend;
import bootstrap.native_assembler as assembler;
import exec.elf as elf;
export("native_lower") pub unsafe fn lower_raw(g:*const front.Graph,w:*const ir.Workspace,mode:u64,r:*ir.Result)u64{unsafe{return lower.lower(g,w,mode,r);}}
export("native_emit") pub unsafe fn emit_raw(p:*const ir.Program,w:*const backend.Workspace,out:*u8,capacity:usize,written:*usize)u64{unsafe{return backend.emit(p,w,slice_from_raw_parts(out,capacity),written);}}
export("native_assemble") pub unsafe fn assemble_raw(src:*const u8,n:usize,entry:*const u8,ne:usize,w:*const assembler.Workspace,out:*u8,capacity:usize,r:*assembler.Result)u64{unsafe{return assembler.assemble(slice_from_raw_parts(src,n),slice_from_raw_parts(entry,ne),w,slice_from_raw_parts(out,capacity),r);}}
export("kernel_validate") fn validate_raw(raw:*const u8,n:usize,plan:*elf.Plan)u64{unsafe{match elf.validate(slice_from_raw_parts(raw,n),0,plan){ok=>{return 0;},err(code)=>{return code;},}}}
'''

NATIVE = '''module native;
pub var canary_lo:u64 = 0x0102030405060708;
pub var a:u8 = 0x11;
pub var b:u8 = 0x22;
pub var c:u16 = 0x3344;
pub var d:u32 = 0x55667788;
pub var e:u64 = 0x99aabbccddeeff00;
pub var pair_hi:u64 = 0x1111222233334444;
pub struct Pair { pub tag:u8, pub word:u32, pub delta:i16 }
pub var pair:Pair = Pair{tag:0xaa,word:0x0badf00d,delta:-1234};
pub var zeroes:[8]u8 = [0;8];
pub var words:[3]u16 = [65535,0x1234,0];
pub var canary_hi:u64 = 0x8877665544332211;
pub var obs:[13]u64 = [0;13];
pub fn probe()*u64 {
 obs[0]=canary_lo;
 obs[1]=(a as u64)+((b as u64)<<8)+((c as u64)<<16)+(d as u64)+e;
 obs[2]=pair_hi;
 obs[3]=pair.delta as u64;
 obs[4]=(pair.tag as u64)+((pair.word as u64)*0x100);
 obs[5]=(words[0] as u64)+((words[1] as u64)<<16);
 obs[6]=(zeroes[0] as u64)+zeroes[7] as u64;
 obs[7]=canary_hi;
 a=0x5a; b=0x6b; c=0x7c8d; d=0x9e0fa1b2; e=0x0102030405060708;
 pair.tag=0x11; pair.word=0x22446688; pair.delta=-2;
 words[1]=0xbeef; zeroes[3]=9;
 obs[8]=(a as u64)+((b as u64)<<8)+((c as u64)<<16)+(d as u64)+e;
 obs[9]=(pair.tag as u64)+((pair.word as u64)*0x100);
 obs[10]=(words[1] as u64)+(zeroes[3] as u64);
 obs[11]=canary_lo;
 obs[12]=canary_hi;
 return &obs[0];
}
'''

DRIVER = r'''
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
typedef struct{Slice labels,table,text,data;} AsmWorkspace;
typedef struct{U status,line,detail,text,data,labels,written;} AsmResult;
#define ABI __attribute__((sysv_abi))
extern U ABI dong_frontend_check(const Options*,const Source*,U,const Limits*,void*,U,FrontResult*);
extern U ABI native_lower(const Graph*,const LowerWorkspace*,U,LowerResult*);
extern U ABI native_emit(const Program*,const EmitWorkspace*,void*,U,U*);
extern U ABI native_assemble(const void*,U,const void*,U,const AsmWorkspace*,void*,U,AsmResult*);
extern U ABI kernel_validate(const void*,U,void*);
void ABI __dong_panic(uint32_t k,uint32_t line,const void*p,U n){(void)p;(void)n;fprintf(stderr,"seed panic %llu line %llu\n",(unsigned long long)k,(unsigned long long)line);exit(93);}
typedef struct{unsigned char*base;U bytes;} Allocation;
static Allocation allocations[64];static U allocation_count=0;
static Slice alloc(U n,U width){U bytes=n*width;unsigned char*p=calloc(1,bytes+32);if(!p)exit(94);memset(p,0xa7,16);memset(p+16+bytes,0xa7,16);if(allocation_count<64)allocations[allocation_count++]=(Allocation){p,bytes};return(Slice){p+16,n};}
static void guards(void){for(U i=0;i<allocation_count;i++){Allocation a=allocations[i];for(U j=0;j<16;j++)if(a.base[j]!=0xa7||a.base[16+a.bytes+j]!=0xa7){fprintf(stderr,"guard failure\n");exit(95);}}}
static U hash(const void*p,U n){const unsigned char*b=p;U h=14695981039346656037ULL;for(U i=0;i<n;i++){h^=b[i];h*=1099511628211ULL;}return h;}
static U hash_lower(const LowerWorkspace*w){return hash(w->functions.p,w->functions.n*sizeof(Function))^hash(w->code.p,w->code.n*sizeof(Instruction))^hash(w->args.p,w->args.n*sizeof(Argument))^hash(w->node_slots.p,w->node_slots.n*8);}
static U hash_emit(const EmitWorkspace*w){return hash(w->text.p,w->text.n)^hash(w->piece.p,w->piece.n)^hash(w->kinds.p,w->kinds.n)^hash(w->locations.p,w->locations.n*16);}
static int unpublished(const LowerResult*r){return !r->program.g&&!r->program.functions.n&&!r->program.code.n&&!r->program.args.n&&!r->program.blocks;}
#define REQUIRE(x) do{if(!(x)){fprintf(stderr,"contract failure line %d\n",__LINE__);return 96;}guards();}while(0)
static U source_hash(Source*c,U n){U h=0;for(U i=0;i<n;i++)h^=hash(c[i].bytes.p,c[i].bytes.n);return h;}

static unsigned char* slurp(const char*path,U*size){FILE*f=fopen(path,"rb");if(!f)return NULL;fseek(f,0,SEEK_END);long n=ftell(f);rewind(f);unsigned char*b=alloc((U)n,1).p;if(fread(b,1,(size_t)n,f)!=(size_t)n){fclose(f);return NULL;}fclose(f);*size=(U)n;return b;}
static int raw(const char*asm_path,const char*entry,const char*elf_path){
 U size=0;unsigned char*src=slurp(asm_path,&size);if(!src)return 91;
 AsmWorkspace w;w.labels=alloc(8192,32);w.table=alloc(16384,8);w.text=alloc(16*1024*1024,1);w.data=alloc(16*1024*1024,1);
 Slice out=alloc(8*1024*1024,1);AsmResult r;memset(&r,0,sizeof(r));
 memset(out.p,0xa5,out.n);U rc=native_assemble(src,size,entry,strlen(entry),&w,out.p,out.n,&r);
 printf("RAW status=%llu line=%llu detail=%llu text=%llu data=%llu labels=%llu written=%llu\n",(unsigned long long)rc,(unsigned long long)r.line,(unsigned long long)r.detail,(unsigned long long)r.text,(unsigned long long)r.data,(unsigned long long)r.labels,(unsigned long long)r.written);
 if(rc!=0){return 0;}
 U exact=r.written;Slice snapshot=alloc(exact,1);memcpy(snapshot.p,out.p,exact);U hashfull=hash(out.p,out.n);
 AsmResult cap;memset(&cap,0,sizeof(cap));
 U cap_rc=native_assemble(src,size,entry,strlen(entry),&w,out.p,exact-1,&cap);
 printf("RAW-CAP status=%llu written=%llu unchanged=%d\n",(unsigned long long)cap_rc,(unsigned long long)cap.written,hash(out.p,out.n)==hashfull);
 AsmResult alias;memset(&alias,0,sizeof(alias));
 U alias_rc=native_assemble(src,size,entry,strlen(entry),&w,src,size,&alias);
 printf("RAW-ALIAS status=%llu\n",(unsigned long long)alias_rc);
 AsmResult miss;memset(&miss,0,sizeof(miss));
 U miss_rc=native_assemble(src,size,"absent_symbol_xyz",18,&w,out.p,out.n,&miss);
 printf("RAW-MISS status=%llu\n",(unsigned long long)miss_rc);
 FILE*f=fopen(elf_path,"wb");if(!f)return 92;if(fwrite(out.p,1,(size_t)exact,f)!=(size_t)exact)return 93;fclose(f);
 return 0;
}
static int validate_elf(const char*elf_path){U size=0;unsigned char*raw=slurp(elf_path,&size);if(!raw)return 91;unsigned char*plan=calloc(1,4096);if(!plan)return 92;U rc=kernel_validate(raw,size,plan);printf("VALIDATE %llu\n",(unsigned long long)rc);return 0;}
int main(int argc,char**argv){
 if(argc>=4&&!strcmp(argv[1],"raw")){return raw(argv[2],argv[3],argv[4]);}
 if(argc>=3&&!strcmp(argv[1],"validate")){return validate_elf(argv[2]);}
 if(argc<7){fprintf(stderr,"usage: pipeline source|list path asm mode elf entry | raw asm entry elf | validate elf\n");return 90;}
 static Source catalog[16];static char paths[16][256];U sources=0;
 if(strstr(argv[1],".list")){
  FILE*lf=fopen(argv[1],"rb");if(!lf)return 91;char line[1024];
  while(fgets(line,sizeof(line),lf)&&sources<16){char*eq=strchr(line,'=');if(!eq)continue;*eq=0;
   char*name=line;while(*name==' ')name++;char*file=eq+1;while(*file==' ')file++;
   char*end=file+strlen(file);while(end>file&&(end[-1]=='\n'||end[-1]=='\r'||end[-1]==' '))--end;*end=0;
   if(strlen(name)>=256){return 91;}
   strcpy(paths[sources],name);FILE*sf=fopen(file,"rb");if(!sf)return 91;
   fseek(sf,0,SEEK_END);long n=ftell(sf);rewind(sf);Slice b=alloc((U)n,1);if(fread(b.p,1,(size_t)n,sf)!=(size_t)n)return 92;fclose(sf);
   catalog[sources]=(Source){0,{paths[sources],strlen(paths[sources])},b};sources++;
  }fclose(lf);
 }else{
  FILE*rf=fopen(argv[1],"rb");if(!rf)return 91;fseek(rf,0,SEEK_END);long length=ftell(rf);rewind(rf);
  Slice source=alloc((U)length,1);if(fread(source.p,1,(size_t)length,rf)!=(size_t)length)return 92;fclose(rf);
  catalog[0]=(Source){0,{argv[2],strlen(argv[2])},source};sources=1;
 }
 U mode=(U)strtoull(argv[4],NULL,10);
 Options o={0,1,64};Limits l={8192,8192,65536,256,4096,4096,65536,4096,512,8192};
 Slice arena=alloc(64*1024*1024,1);FrontResult fr;memset(&fr,0,sizeof(fr));
 U rc=dong_frontend_check(&o,catalog,sources,&l,arena.p,arena.n,&fr);
 if(rc){fprintf(stderr,"frontend status=%llu stage=%llu code=%llu detail=%llu source=%llu offset=%llu\n",(unsigned long long)rc,(unsigned long long)fr.stage,(unsigned long long)fr.code,(unsigned long long)fr.detail,(unsigned long long)fr.source,(unsigned long long)fr.offset);return 10;}
 U arena_hash=hash(arena.p,arena.n),sources_hash=source_hash(catalog,sources);guards();
 LowerWorkspace lw={alloc(4096,sizeof(Function)),alloc(524288,sizeof(Instruction)),alloc(131072,sizeof(Argument)),alloc(262144,8)};
 LowerResult lr;memset(&lr,0,sizeof(lr));
 rc=native_lower(&fr.graph,&lw,mode,&lr);
 if(rc){REQUIRE(unpublished(&lr));fprintf(stderr,"lower status=%llu node=%llu detail=%llu\n",(unsigned long long)rc,(unsigned long long)lr.node,(unsigned long long)lr.detail);return 11;}
 LowerResult before=lr;U scratch_hash=hash_lower(&lw);
 REQUIRE(native_lower(&fr.graph,&lw,2,&lr)==1&&!memcmp(&lr,&before,sizeof(lr))&&scratch_hash==hash_lower(&lw));
 LowerWorkspace bad=lw;bad.code.p=arena.p;bad.code.n=1;
 REQUIRE(native_lower(&fr.graph,&bad,mode,&lr)==1&&!memcmp(&lr,&before,sizeof(lr))&&scratch_hash==hash_lower(&lw));
 bad=lw;bad.functions.p=lw.code.p;
 REQUIRE(native_lower(&fr.graph,&bad,mode,&lr)==1&&!memcmp(&lr,&before,sizeof(lr))&&scratch_hash==hash_lower(&lw));
 U exact_functions=lr.program.functions.n,exact_code=lr.program.code.n,exact_args=lr.program.args.n;
 for(U which=0;which<4;which++){if(which==2&&exact_args==0){continue;}bad=lw;if(which==0)bad.functions.n=exact_functions-1;if(which==1)bad.code.n=exact_code-1;if(which==2)bad.args.n=exact_args-1;if(which==3)bad.node_slots.n=fr.graph.nodes.n-1;
  REQUIRE(native_lower(&fr.graph,&bad,mode,&lr)==2&&unpublished(&lr));}
 lw.functions.n=exact_functions;lw.code.n=exact_code;lw.args.n=exact_args;lw.node_slots.n=fr.graph.nodes.n;
 REQUIRE(native_lower(&fr.graph,&lw,mode,&lr)==0);
 U code_hash=hash(lw.code.p,lw.code.n*sizeof(Instruction)),args_hash=hash(lw.args.p,lw.args.n*sizeof(Argument)),function_hash=hash(lw.functions.p,lw.functions.n*sizeof(Function));
 EmitWorkspace ew={alloc(32*1024*1024,1),alloc(8192,1),alloc(8192,1),alloc(8192,16)};Slice out=alloc(16*1024*1024,1);U written=0;
 memset(out.p,0xa9,out.n);
 rc=native_emit(&lr.program,&ew,out.p,out.n,&written);
 if(rc){fprintf(stderr,"emit status=%llu\n",(unsigned long long)rc);return 12;}
 U exact=written;Slice snapshot=alloc(exact,1);memcpy(snapshot.p,out.p,exact);memset(out.p,0xa9,out.n);U out_hash=hash(out.p,out.n);written=999;
 REQUIRE(native_emit(&lr.program,&ew,out.p,exact-1,&written)==2&&written==999&&out_hash==hash(out.p,out.n));
 U has_calls=0;for(U k=0;k<lr.program.code.n;k++){Instruction*x=(Instruction*)lr.program.code.p+k;if(x->operation==14&&x->b>0){has_calls=1;break;}}
 for(U which=0;which<4;which++){if(which==2&&!has_calls){continue;}if(which==3&&!has_calls){continue;}EmitWorkspace badw=ew;if(which==0)badw.text.n=exact-1;if(which==1)badw.piece.n=1023;if(which==2)badw.kinds.n=0;if(which==3)badw.locations.n=0;
  REQUIRE(native_emit(&lr.program,&badw,out.p,out.n,&written)==2&&written==999&&out_hash==hash(out.p,out.n));}
 U emit_hash=hash_emit(&ew);
 REQUIRE(native_emit(&lr.program,&ew,catalog[0].bytes.p,catalog[0].bytes.n,&written)==1&&written==999);
 REQUIRE(native_emit(&lr.program,&ew,ew.text.p,ew.text.n,&written)==1&&written==999);
 REQUIRE(native_emit(&lr.program,&ew,out.p,out.n,(U*)out.p)==1&&out_hash==hash(out.p,out.n));
 EmitWorkspace badw=ew;badw.piece=badw.text;
 REQUIRE(native_emit(&lr.program,&badw,out.p,out.n,&written)==1&&written==999&&out_hash==hash(out.p,out.n));
 REQUIRE(emit_hash==hash_emit(&ew));
 ew.text.n=exact;REQUIRE(native_emit(&lr.program,&ew,out.p,exact,&written)==0&&written==exact&&!memcmp(out.p,snapshot.p,exact));
 for(U i=exact;i<out.n;i++){if(((unsigned char*)out.p)[i]!=0xa9)return 97;}guards();
 REQUIRE(arena_hash==hash(arena.p,arena.n)&&sources_hash==source_hash(catalog,sources)&&code_hash==hash(lw.code.p,lw.code.n*sizeof(Instruction))&&args_hash==hash(lw.args.p,lw.args.n*sizeof(Argument))&&function_hash==hash(lw.functions.p,lw.functions.n*sizeof(Function)));
 FILE*wf=fopen(argv[3],"wb");if(!wf)return 13;if(fwrite(out.p,1,(size_t)written,wf)!=written)return 14;fclose(wf);

 U exact_asm=written;AsmWorkspace aw;aw.labels=alloc(8192,32);aw.table=alloc(16384,8);aw.text=alloc(16*1024*1024,1);aw.data=alloc(16*1024*1024,1);
 Slice image=alloc(8*1024*1024,1);AsmResult ar;memset(&ar,0,sizeof(ar));
 U arc=native_assemble(ew.text.p,exact_asm,argv[6],strlen(argv[6]),&aw,image.p,image.n,&ar);
 if(arc){fprintf(stderr,"assemble status=%llu line=%llu detail=%llu\n",(unsigned long long)arc,(unsigned long long)ar.line,(unsigned long long)ar.detail);return 15;}
 FILE*ef=fopen(argv[5],"wb");if(!ef)return 16;if(fwrite(image.p,1,(size_t)ar.written,ef)!=(size_t)ar.written)return 17;fclose(ef);
 printf("PIPE functions=%llu instructions=%llu asm=%llu text=%llu data=%llu labels=%llu elf=%llu\n",(unsigned long long)lr.program.functions.n,(unsigned long long)lr.program.code.n,(unsigned long long)exact_asm,(unsigned long long)ar.text,(unsigned long long)ar.data,(unsigned long long)ar.labels,(unsigned long long)ar.written);

}
'''

MAPPER = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#define ABI __attribute__((sysv_abi))
static void* map_at(uint64_t base,size_t size){return VirtualAlloc((void*)(uintptr_t)base,size,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);}
static int protect_text(void*p,size_t n){DWORD old;return VirtualProtect(p,n,PAGE_EXECUTE_READ,&old)!=0;}
#else
#include <sys/mman.h>
#define ABI
static void* map_at(uint64_t base,size_t size){return mmap((void*)(uintptr_t)base,size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);}
static int protect_text(void*p,size_t n){return mprotect(p,n,PROT_READ|PROT_EXEC)==0;}
#endif
typedef uint64_t U;
static unsigned char* image;
static U rd64(U o){U v=0;memcpy(&v,image+o,8);return v;}
static U rd16(U o){unsigned short v=0;memcpy(&v,image+o,2);return v;}
static int mapped_main(int argc,char**argv){
 if(argc<4){return 90;}
 FILE*f=fopen(argv[1],"rb");if(!f)return 91;
 fseek(f,0,SEEK_END);long n=ftell(f);rewind(f);image=malloc((size_t)n);
 if(fread(image,1,(size_t)n,f)!=(size_t)n)return 92;
 fclose(f);
 if(memcmp(image,"\x7f" "ELF\x02\x01",6)){return 93;}
 U base=(U)strtoull(argv[2],NULL,16),count=(U)strtoull(argv[3],NULL,10);
 U phoff=rd64(32),phnum=rd16(56),entry=rd64(24),elfbase=0x400000,text_end=0;
 unsigned char*map=(unsigned char*)map_at(base,0x200000);
 if(!map||map==(void*)-1){fprintf(stderr,"map failed %llu\n",(unsigned long long)base);return 94;}
 for(U i=0;i<phnum;i++){
  U o=phoff+i*56,off=rd64(o+8),vaddr=rd64(o+16),filesz=rd64(o+32),memsz=rd64(o+40),flags=rd64(o+4);
  unsigned char*dst=map+(vaddr-elfbase);memcpy(dst,image+off,(size_t)filesz);memset(dst+filesz,0,(size_t)(memsz-filesz));
  if((flags&1)&&!(flags&2)){text_end=filesz;}
 }
 if(text_end&&!protect_text(map,(size_t)text_end)){return 95;}
 typedef U (ABI *fnptr)(void);
 fnptr fn=(fnptr)(uintptr_t)(base+(entry-elfbase));
 U ptr=fn();
 printf("BASE %llx ENTRY %llx PTR %llx\n",(unsigned long long)base,(unsigned long long)(entry-elfbase),(unsigned long long)ptr);
 for(U i=0;i<count;i++){printf("OBS %llu %llu\n",(unsigned long long)i,(unsigned long long)((U*)(uintptr_t)ptr)[i]);}
 return 0;
}
#ifdef _WIN32
// The initial Windows thread reserves its stack at the ELF's fixed 4MiB
// base. Let the OS release that stack before the worker maps the exact ELF
// addresses; do not patch/rebase absolute static pointer initializers.
static int saved_argc;static char**saved_argv;
static DWORD WINAPI mapped_worker(void*parent){
 WaitForSingleObject((HANDLE)parent,INFINITE);CloseHandle((HANDLE)parent);
 ExitProcess((UINT)mapped_main(saved_argc,saved_argv));return 0;
}
int main(int argc,char**argv){
 saved_argc=argc;saved_argv=argv;HANDLE parent;
 if(!DuplicateHandle(GetCurrentProcess(),GetCurrentThread(),GetCurrentProcess(),&parent,SYNCHRONIZE,FALSE,0))return 97;
 HANDLE worker=CreateThread(NULL,0,mapped_worker,parent,0,NULL);
 if(!worker){CloseHandle(parent);return 98;}CloseHandle(worker);
 ExitThread(0);return 99;
}
#else
int main(int argc,char**argv){return mapped_main(argc,argv);}
#endif
'''

LAYOUT = {
    "canary_lo": 8, "a": 1, "b": 1, "c": 2, "d": 4, "e": 8, "pair_hi": 8,
    "pair": 12, "zeroes": 8, "words": 6, "canary_hi": 8, "obs": 104,
}
ALIGN = {"canary_lo": 8, "a": 1, "b": 1, "c": 2, "d": 4, "e": 8, "pair_hi": 8,
         "pair": 4, "zeroes": 1, "words": 2, "canary_hi": 8, "obs": 8}


def label(module, name):
    return "__dong_m" + module.encode().hex() + "_n" + name.encode().hex()


def imports(text):
    return re.findall(r"(?m)^\s*import\s+([A-Za-z_][\w.]*)\s+as\s+\w+\s*;", text)


def locate(module):
    rel = Path(*module.split(".")).with_suffix(".dg")
    for prefix, base in SEARCH:
        path = base / rel
        if path.is_file():
            return prefix, path
    raise RuntimeError("missing module " + module)


def stage_compiler(work, mutations=None):
    stage = work / ("stage-" + uuid.uuid4().hex[:8])
    (stage / "probe").mkdir(parents=True)
    seen, order, queue = {}, [], []
    for name in CANDIDATES:
        module = "bootstrap." + name[:-3]
        seen[module] = CAND / name
        order.append((module, CAND / name))
        queue.append(module)
    prefix, kernel_path = locate("exec.elf")
    seen["exec.elf"] = kernel_path
    order.append(("exec.elf", kernel_path))
    queue.append("exec.elf")
    while queue:
        module = queue.pop()
        for dep in imports(seen[module].read_text(encoding="utf-8")):
            if dep in seen:
                continue
            _, path = locate(dep)
            seen[dep] = path
            order.append((dep, path))
            queue.append(dep)
    provenance = {}
    for module, path in order:
        rel = Path(*module.split(".")).with_suffix(".dg")
        if path.parent == CAND:
            prefix = ""
            data = path.read_bytes()
            if mutations and path.name in mutations:
                text = data.decode("utf-8")
                old, new = mutations[path.name]
                if text.count(old) != 1:
                    raise AssertionError("mutation needle mismatch")
                data = text.replace(old, new).encode("utf-8")
        else:
            prefix = next(p for p, root in SEARCH if path == root / rel)
            data = path.read_bytes()
        dest = stage / (prefix / rel if prefix else rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        provenance[dest.relative_to(stage).as_posix()] = {"origin": str(path), "sha256": hashlib.sha256(data).hexdigest()}
    (stage / "probe" / "l3a_native.dg").write_text(WRAPPER)
    return stage, provenance


class L3ANativeRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not cls.nasm or not cls.cc:
            raise RuntimeError("NASM and a SysV-capable CC are required")
        cls.work = BUILD / ("native-" + uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        cls.records = []
        cls.inputs = {str(CAND / name): hashlib.sha256((CAND / name).read_bytes()).hexdigest() for name in CANDIDATES}
        stage, provenance = stage_compiler(cls.work)
        cls.stage, cls.provenance = stage, provenance
        for record in provenance.values():
            path=Path(record["origin"]);cls.inputs[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        cls.inputs[str(Path(__file__))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (stage / "driver.c").write_text(DRIVER)
        wrapper = stage / "probe" / "l3a_native.dg"
        compiled = compile_file(wrapper, roots=[stage, stage / "std"], mode="debug")
        for source in compiled.sources:
            if source in provenance:
                if hashlib.sha256((stage / source).read_bytes()).hexdigest() != provenance[source]["sha256"]:
                    raise AssertionError("staged module changed during seed compile")
        asm = stage / "wrapper.asm"
        asm.write_text(compiled.assembly)
        cls.command([cls.nasm, "-O0", "-f", "win64", *nasm_flags(cls.nasm), "-o", stage / "wrapper.obj", asm], "wrapper-win64")
        cls.command([cls.nasm, "-O0", "-f", "elf64", *nasm_flags(cls.nasm), "-o", stage / "wrapper.elf.o", asm], "wrapper-elf64")
        cls.driver = stage / "driver.exe"
        cls.command([cls.cc, "-std=c11", "-D_GNU_SOURCE", "-D__USE_MINGW_ANSI_STDIO=1", "-O2", "-Wall", "-Wextra",
                     "-Werror", stage / "driver.c", stage / "wrapper.obj", "-o", cls.driver], "driver-link")
        (stage / "mapper.c").write_text(MAPPER)
        mapper = stage / ("mapper.exe" if WIN else "mapper")
        base_flag = ["-Wl,--image-base=0x100000000"] if WIN else []
        cls.command([cls.cc, "-std=c11", "-D_GNU_SOURCE", "-D__USE_MINGW_ANSI_STDIO=1", "-O2", "-Wall", "-Wextra",
                     "-Werror", *base_flag, stage / "mapper.c", "-o", mapper], "mapper-link")
        cls.mapper = mapper
        cls.records.append({"wrapper_sources": list(compiled.sources), "provenance": provenance,
                            "wrapper_sha256": hashlib.sha256(compiled.assembly.encode()).hexdigest()})

    @classmethod
    def command(cls, args, name, expect=0):
        p = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=600)
        (cls.work / (name + ".log")).write_text(p.stdout + p.stderr)
        cls.records.append({"name": name, "command": [str(a) for a in args], "returncode": p.returncode,
                            "stdout": p.stdout, "stderr": p.stderr})
        if expect is not None and p.returncode != expect:
            raise AssertionError(f"{name}: {p.returncode}\n{p.stdout}\n{p.stderr}")
        return p

    def pipeline(self, source: str, entry: str, tag: str):
        directory = self.work / tag
        directory.mkdir(exist_ok=True)
        source_file = directory / "native.dg"
        source_file.write_text(source, encoding="utf-8")
        asm = directory / "module.asm"
        elf = directory / "module.elf"
        report = self.command([self.driver, source_file, "native.dg", asm, "0", elf, entry], tag + "-pipeline").stdout
        self.assertIn("PIPE ", report)
        self.assertIn("asm=", report)
        return directory, asm, elf, report

    def expected_observations(self):
        lo = 0x0102030405060708
        hi = 0x8877665544332211
        return [
            lo,
            0x11 + (0x22 << 8) + (0x3344 << 16) + 0x55667788 + 0x99aabbccddeeff00,
            0x1111222233334444,
            (-1234) & ((1 << 64) - 1),
            0xaa + 0x0badf00d * 0x100,
            0xffff + (0x1234 << 16),
            0,
            hi,
            (0x5a + (0x6b << 8) + (0x7c8d << 16) + 0x9e0fa1b2 + 0x0102030405060708) & ((1 << 64) - 1),
            0x11 + 0x22446688 * 0x100,
            0xbeef + 9,
            lo,
            hi,
        ]

    def expected_data(self):
        values = {
            "canary_lo": 0x0102030405060708,
            "a": 0x11,
            "b": 0x22,
            "c": 0x3344,
            "d": 0x55667788,
            "e": 0x99aabbccddeeff00,
            "pair_hi": 0x1111222233334444,
        }
        out = bytearray()
        for name in ("canary_lo", "a", "b", "c", "d", "e", "pair_hi"):
            while len(out) % ALIGN[name]:
                out.append(0)
            out += values[name].to_bytes(LAYOUT[name], "little")
        while len(out) % 4:
            out.append(0)
        out += bytes([0xaa, 0, 0, 0]) + (0x0badf00d).to_bytes(4, "little") + ((-1234) & 0xffff).to_bytes(2, "little") + b"\0\0"
        entries = [("zeroes", bytes(8)), ("words", bytes.fromhex("ffff34120000")), ("canary_hi", (0x8877665544332211).to_bytes(8, "little")), ("obs", bytes(104))]
        for name, data in entries:
            while len(out) % ALIGN[name]:
                out.append(0)
            out += data
        return bytes(out)

    def asm_data(self, text: str):
        data = bytearray()
        section = None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("section "):
                section = line.split()[1]
                continue
            if section != ".data" or not line or line.startswith("%"):
                continue
            if line.startswith("align "):
                alignment = int(line.split()[1])
                while len(data) % alignment:
                    data.append(0)
            elif line.startswith("times "):
                match = re.match(r"times (\d+) db (\d+)$", line)
                self.assertIsNotNone(match, line)
                data += bytes([int(match.group(2))]) * int(match.group(1))
            elif line.startswith("db "):
                data += bytes(int(part) for part in line[3:].split(","))
            elif line.startswith("global ") or line.endswith(":"):
                continue
            else:
                self.fail("unexpected .data line: " + line)
        return bytes(data)

    def parse_elf(self, image: bytes):
        self.assertEqual(image[:4], b"\x7fELF")
        self.assertEqual((image[4], image[5], image[6]), (2, 1, 1))
        e_type, e_machine = struct.unpack_from("<HH", image, 16)
        self.assertEqual((e_type, e_machine), (2, 62))
        entry, phoff = struct.unpack_from("<QQ", image, 24)
        _, phnum = struct.unpack_from("<HH", image, 54)
        self.assertEqual(phnum, 2)
        headers = [struct.unpack_from("<IIQQQQQQ", image, phoff + i * 56) for i in range(phnum)]
        return entry, headers

    def execute(self, elf: Path, base: str, count=13):
        p = self.command([self.mapper, elf, base, str(count)], f"execute-{base}")
        lines = [line for line in p.stdout.splitlines() if line.startswith("OBS ")]
        self.assertEqual(len(lines), count, p.stdout + p.stderr)
        return [int(line.split()[2]) for line in lines]

    def test_native_elf_layout_data_and_real_execution(self):
        directory, asm, elf, report = self.pipeline(NATIVE, label("native", "probe"), "native")
        text = asm.read_text(encoding="utf-8")
        self.assertIn("section .data", text)
        self.assertNotIn("section .bss", text)
        model = self.expected_data()
        self.assertEqual(self.asm_data(text), model)
        image = elf.read_bytes()
        entry, headers = self.parse_elf(image)
        text_header, data_header = headers
        self.assertEqual((text_header[1], text_header[2], text_header[3]), (5, 0, BASE))
        self.assertEqual(text_header[5], text_header[6])
        text_size = text_header[5] - PAGE
        self.assertGreater(text_size, 0)
        data_offset = (PAGE + text_size + PAGE - 1) & ~(PAGE - 1)
        self.assertEqual((data_header[1], data_header[2], data_header[3]), (6, data_offset, BASE + data_offset))
        self.assertEqual(data_header[5], data_header[6])
        self.assertEqual(data_header[5], len(model))
        self.assertEqual(image[data_offset:data_offset + data_header[5]], model)
        self.assertTrue(BASE + PAGE <= entry < BASE + text_header[5])
        self.assertEqual(self.command([self.driver, "validate", elf], "kernel-validate").stdout.strip(), "VALIDATE 0")
        expected = self.expected_observations()
        windows = ["400000", "10000000"]
        results = [self.execute(elf, base) for base in windows]
        self.assertEqual(results[0], expected)
        self.assertEqual(results[1], expected)
        self.records.append({"data_sha256": hashlib.sha256(model).hexdigest(),
                             "elf_sha256": hashlib.sha256(image).hexdigest(),
                             "entry_offset": entry - PAGE - BASE, "text_size": text_size,
                             "mapping_bases": windows, "observations": results[0]})

    def test_fixed_address_static_pointer_initializers_execute(self):
        source="""module native;
pub const fixed:[3]u16=[0x11,0x2233,0x4455];
pub var values:[4]u16=[3,5,7,11];
pub struct Bag{pub tag:u8,pub word:u32}
pub var bag:Bag=Bag{tag:0xaa,word:0x12345678};
pub var p:*u16=&values[2];
pub var q:*u32=&bag.word;
pub var r:*const u16=&fixed[1];
pub var obs:[8]u64=[0;8];
pub fn probe()*u64{unsafe{
 obs[0]=*p as u64;obs[1]=*q as u64;obs[2]=*r as u64;
 *p=0xbeef;*q=0xaabbccdd;
 obs[3]=values[2] as u64;obs[4]=bag.word as u64;obs[5]=*r as u64;
 if p==&values[2]{obs[6]=4;}else{obs[6]=999;}if q==&bag.word{obs[7]=4;}else{obs[7]=999;}
 }return &obs[0];}
"""
        _,asm,elf,_=self.pipeline(source,label('native','probe'),'static-pointers')
        text=asm.read_text(encoding='utf-8')
        for name,offset in [('values',4),('bag',4),('fixed',2)]:
            self.assertIn('dq '+label('native',name)+'+'+str(offset),text)
        self.assertEqual(self.command([self.driver,'validate',elf],'pointer-kernel-validate').stdout.strip(),'VALIDATE 0')
        self.assertEqual(self.execute(elf,'400000',8),[7,0x12345678,0x2233,0xbeef,0xaabbccdd,0x2233,4,4])
        self.records.append(dict(test='fixed-ELF-static-pointers',base=BASE,absolute_pointer_rebasing=False,passed=True))

    def test_text_alignment_is_nop_and_executes_through_padding(self):
        source=self.work/'text-align.asmtext'
        source.write_text('bits 64\ndefault rel\nsection .text\nglobal _start\n_start:\nmov rax, 41\nalign 16\nadd rax, 1\nret\nsection .data\nunused: db 0\n')
        elf=self.work/'text-align.elf'
        self.command([self.driver,'raw',source,'_start',elf],'text-align-assemble')
        image=elf.read_bytes();entry,headers=self.parse_elf(image)
        text=image[PAGE:headers[0][5]]
        # mov rax,imm64 is exactly ten bytes in this assembler; alignment
        # must leave six executable NOPs before the next instruction.
        self.assertEqual(text[10:16],b'\x90'*6)
        # The independent mapper below asks for no observation dereferences;
        # it prints the function return in PTR, so 42 remains a plain value.
        run=self.command([self.mapper,elf,'400000','0'],'text-align-execute')
        self.assertRegex(run.stdout,r'PTR 2a(?:\r?\n|$)')
        self.records.append(dict(test='text-align-executable-NOP',entry=entry,returned=42,passed=True))

    def test_assembler_rejects_data_section_abuse_and_preserves_outputs(self):
        prefix = "bits 64\ndefault rel\nsection .text\nglobal _start\n_start:\nret\n"
        cases = {
            "bss": prefix + "section .bss\nx: db 0\n",
            "data_instruction": prefix + "section .data\nmov rax, 1\n",
            "unknown_symbol": prefix + "section .data\nx: dq absent_label\n",
            "duplicate": prefix + "section .data\nx: db 1\nx: db 2\n",
            "bad_relocation": prefix + "section .data\nx: dq 1, 2\ny: dq x, missing\n",
            "times_in_text": prefix + "times 4 db 0\n",
        }
        for name, body in cases.items():
            source = self.work / (name + ".asmtext")
            source.write_text(body, encoding="utf-8")
            out = self.work / (name + ".elf")
            p = self.command([self.driver, "raw", source, "_start", out], "raw-" + name, expect=0)
            self.assertIn("RAW status=", p.stdout)
            status = int(re.search(r"RAW status=(\d+)", p.stdout).group(1))
            self.assertNotEqual(status, 0, (name, p.stdout))
            self.assertFalse(out.exists(), name)
        valid = self.work / "valid.asmtext"
        valid.write_text(prefix + "section .data\nalign 8\nword: dq 0x1122334455667788\n", encoding="utf-8")
        out = self.work / "valid.elf"
        p = self.command([self.driver, "raw", valid, "_start", out], "raw-valid", expect=0)
        self.assertIn("RAW status=0", p.stdout)
        self.assertIn("RAW-CAP status=2", p.stdout)
        self.assertIn("unchanged=1", p.stdout)
        self.assertIn("RAW-ALIAS status=1", p.stdout)
        self.assertIn("RAW-MISS status=", p.stdout)
        self.assertNotIn("RAW-MISS status=0", p.stdout)
        image = out.read_bytes()
        self.assertEqual(image[:4], b"\x7fELF")
        self.assertTrue(out.exists())

    @classmethod
    def tearDownClass(cls):
        after = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in cls.inputs}
        stable = after == cls.inputs
        provenance_after = {}
        for rel, record in cls.provenance.items():
            staged = cls.stage / rel
            provenance_after[rel] = hashlib.sha256(staged.read_bytes()).hexdigest() if staged.exists() else None
        (cls.work / "summary.json").write_text(json.dumps({
            "records": cls.records, "inputs_before": cls.inputs, "inputs_after": after,
            "source_stable": stable, "staged_after": provenance_after, "L3A_complete": False,
            "windows_mapping_note": "Fixed 0x400000 execution frees the initial Windows thread stack by ExitThread before mapping from a worker. Static absolute pointers are never rebased. Alternate-base execution is restricted to pointer-free fixture.",
        }, indent=2) + "\n")
        if not stable:
            raise AssertionError("candidate or read-only input changed during the test run")


if __name__ == "__main__":
    unittest.main()
