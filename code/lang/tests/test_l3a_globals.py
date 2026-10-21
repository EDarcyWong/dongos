"""L3A: mutable globals through the real native frontend -> lower -> NASM pipeline.

One candidate module set is staged next to its read-only import closure; the seed
Python compiler only builds the compiler under test.  Every observation below is
made by assembling the production NASM text with NASM and executing the emitted
machine code through an explicit SysV bridge, plus independent Python oracles.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
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

WRAPPER = '''module probe.l3a_pipeline;
import bootstrap.frontend as front;
import bootstrap.program_ir as ir;
import bootstrap.lower_program as lower;
import bootstrap.nasm_program as backend;
export("native_lower") pub unsafe fn lower_raw(g:*const front.Graph,w:*const ir.Workspace,mode:u64,r:*ir.Result)u64{unsafe{return lower.lower(g,w,mode,r);}}
export("native_emit") pub unsafe fn emit_raw(p:*const ir.Program,w:*const backend.Workspace,out:*u8,capacity:usize,written:*usize)u64{unsafe{return backend.emit(p,w,slice_from_raw_parts(out,capacity),written);}}
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
#define ABI __attribute__((sysv_abi))
extern U ABI dong_frontend_check(const Options*,const Source*,U,const Limits*,void*,U,FrontResult*);
extern U ABI native_lower(const Graph*,const LowerWorkspace*,U,LowerResult*);
extern U ABI native_emit(const Program*,const EmitWorkspace*,void*,U,U*);
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
int main(int argc,char**argv){
 if(argc<5){fprintf(stderr,"usage: source|list path asm-out mode\n");return 90;}
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
 printf("{\"sources\":%llu,\"functions\":%llu,\"instructions\":%llu,\"arguments\":%llu,\"blocks\":%llu,\"bytes\":%llu}\n",(unsigned long long)sources,(unsigned long long)lr.program.functions.n,(unsigned long long)lr.program.code.n,(unsigned long long)lr.program.args.n,(unsigned long long)lr.program.blocks,(unsigned long long)written);return 0;
}
'''

SCALARS = '''module scalars;
pub var canary_head:u64 = 0x0123456789abcdef;
pub var narrow_a:u8 = 0x11;
pub var narrow_b:u8 = 0x22;
pub var narrow_c:u16 = 0x0102;
pub var narrow_d:u32 = 0x01020304;
pub var narrow_e:u64 = 0x0102030405060708;
pub var hi_u8:u8 = 0xff;
pub var hi_u16:u16 = 0xabcd;
pub var hi_u32:u32 = 0xdeadbeef;
pub var max_u64:u64 = 18446744073709551615;
pub var neg_i8:i8 = -128;
pub var neg_i16:i16 = -32768;
pub var neg_i32:i32 = -2147483648;
pub var neg_i64:i64 = -9223372036854775808;
pub var flag:bool = true;
pub var ptr:*u8 = null;
pub var canary_tail:u64 = 0xfedcba9876543210;
pub fn read_cluster()u64 { return (narrow_a as u64)+(narrow_b as u64)+(narrow_c as u64)+(narrow_d as u64)+narrow_e; }
pub fn read_hi_u8()u8 { return hi_u8; }
pub fn read_hi_u16()u16 { return hi_u16; }
pub fn read_hi_u32()u32 { return hi_u32; }
pub fn read_signed()i64 { return (neg_i8 as i64)+(neg_i16 as i64)+(neg_i32 as i64); }
pub fn read_neg64()i64 { return neg_i64; }
pub fn read_max()u64 { return max_u64; }
pub fn read_flag()bool { return flag; }
pub fn bump()u64 { narrow_a+=1; narrow_c+=1; narrow_e+=1; return narrow_a as u64; }
pub fn write_cluster()void { narrow_a=0x5a; narrow_b=0x6b; narrow_c=0x7c8d; narrow_d=0x9e0fa1b2; narrow_e=0x0102030405060708; }
pub fn write_neg()void { neg_i8=-1; neg_i16=-2; neg_i32=-3; neg_i64=-4; }
pub fn clear_flag()void { flag=false; }
pub fn set_ptr()void { ptr=&narrow_b; }
pub fn read_ptr_value()u8 { unsafe { return *ptr; } }
'''

LAYOUT = '''module layout;
pub struct Vec3 { pub x:u16, pub y:u32, pub z:u8 }
pub struct Nested { pub tag:u8, pub inner:Vec3, pub tail:u16 }
pub var head:u64 = 0x1111222233334444;
pub var v:Vec3 = Vec3{x:0x1234,y:0x55667788,z:0x9a};
pub var n:Nested = Nested{tag:0x5a,inner:Vec3{x:1,y:2,z:3},tail:0xbeef};
pub var bytes:[6]u8 = [0,1,2,255,4,5];
pub var zeros:[12]u8 = [0;12];
pub var words:[3]u16 = [65535,0,4660];
pub var tail:u64 = 0xaaaabbbbccccdddd;
pub const BASE:[4]u16 = [9,8,7,6];
pub fn read_v()u64 { return (v.x as u64)+(v.y as u64)+(v.z as u64); }
pub fn read_n()u64 { return (n.tag as u64)+(n.inner.x as u64)+(n.inner.y as u64)+(n.inner.z as u64)+(n.tail as u64); }
pub fn read_byte(i:usize)u8 { return bytes[i]; }
pub fn write_byte(i:usize,value:u8)void { bytes[i]=value; }
pub fn read_const(i:usize)u16 { return BASE[i]; }
pub fn const_addr(i:usize)*const u16 { return &BASE[i]; }
pub fn write_fields()void { v.z=0x77; n.tail=0x1234; n.inner.y=0xaabbccdd; }
pub fn read_zero(i:usize)u8 { return zeros[i]; }
pub fn read_word(i:usize)u16 { return words[i]; }
'''

DEP = '''module dep;
pub var shared:u64 = 11;
var secret:u64 = 22;
pub fn read_a()u64 { return shared+secret; }
pub fn bump_a()u64 { shared+=1; return shared; }
pub fn add(value:u64)u64 { return shared+value; }
'''

MAIN = '''module main;
import dep as x;
pub var shared:u64 = 33;
pub fn read_b()u64 { return shared + x.shared; }
pub fn cross()u64 { return x.read_a() + x.bump_a(); }
pub fn with_arg()u64 { return x.add(7); }
'''

PRIVATE_BAD = '''module privbad;
import dep as x;
pub fn leak()u64 { return x.secret; }
'''

EXTERN_BAD = 'module extbad;\nextern "sysv64" fn foreign(value:u64)u64;\npub fn call_foreign()u64 { unsafe { return foreign(1); } }\n'


def label(module: str, name: str) -> str:
    return "__dong_m" + module.encode().hex() + "_n" + name.encode().hex()


def imports(text: str):
    return re.findall(r"(?m)^\s*import\s+([A-Za-z_][\w.]*)\s+as\s+\w+\s*;", text)


def locate(module: str):
    rel = Path(*module.split(".")).with_suffix(".dg")
    for prefix, base in SEARCH:
        path = base / rel
        if path.is_file():
            return prefix, path
    raise RuntimeError("missing module " + module)


def closure(extra=("exec.elf",)):
    seen, order = {}, []
    for name in CANDIDATES:
        module = "bootstrap." + name[:-3]
        seen[module] = CAND / name
        order.append((module, CAND / name))
    queue = [m for m, _ in order]
    for module in extra:
        if module in seen:
            continue
        prefix, path = locate(module)
        seen[module] = path
        order.append((module, path))
        queue.append(module)
    while queue:
        module = queue.pop()
        for dep in imports(seen[module].read_text(encoding="utf-8")):
            if dep in seen:
                continue
            prefix, path = locate(dep)
            seen[dep] = path
            order.append((dep, path))
            queue.append(dep)
    return order


def stage_compiler(work: Path, wrapper: str = WRAPPER, mutations=None, extra=("exec.elf",)):
    stage = work / ("stage-" + uuid.uuid4().hex[:8])
    (stage / "probe").mkdir(parents=True)
    provenance = {}
    for module, path in closure(extra):
        rel = Path(*module.split(".")).with_suffix(".dg")
        if path.parent == CAND:
            prefix = ""
            data = path.read_bytes()
            if mutations and path.name in mutations:
                text = data.decode("utf-8")
                old, new = mutations[path.name]
                if text.count(old) != 1:
                    raise AssertionError(f"mutation needle count {text.count(old)} for {path.name}")
                data = text.replace(old, new).encode("utf-8")
        else:
            prefix = next(p for p, root in SEARCH if path == root / rel)
            data = path.read_bytes()
        dest = stage / (prefix / rel if prefix else rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        provenance[dest.relative_to(stage).as_posix()] = {
            "origin": str(path), "sha256": hashlib.sha256(data).hexdigest(),
            "candidate": path.parent == CAND,
        }
    (stage / "probe" / "l3a_pipeline.dg").write_text(wrapper)
    return stage, provenance


class L3AGlobalsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not cls.nasm or not cls.cc:
            raise RuntimeError("NASM and a SysV-capable CC are required for L3A")
        cls.work = BUILD / ("run-" + uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        cls.records = []
        cls.provenance = {}
        cls.inputs = {str(Path(__file__)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        for name in CANDIDATES:
            cls.inputs[str(CAND / name)] = hashlib.sha256((CAND / name).read_bytes()).hexdigest()
        cls.drivers = {}
        cls.build_driver("good")
        cls.binaries = {}

    @classmethod
    def build_driver(cls, tag, mutations=None):
        if tag in cls.drivers:
            return cls.drivers[tag]
        stage, provenance = stage_compiler(cls.work / tag, mutations=mutations)
        cls.provenance[tag] = provenance
        for record in provenance.values():
            path=Path(record["origin"]);cls.inputs[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        (stage / "driver.c").write_text(DRIVER)
        wrapper = stage / "probe" / "l3a_pipeline.dg"
        compiled = compile_file(wrapper, roots=[stage, stage / "std"], mode="debug")
        for source in compiled.sources:
            if source in provenance:
                staged = stage / source
                if hashlib.sha256(staged.read_bytes()).hexdigest() != provenance[source]["sha256"]:
                    raise AssertionError("staged module changed during seed compile: " + source)
        asm = stage / "wrapper.asm"
        asm.write_text(compiled.assembly)
        obj = stage / "wrapper.obj"
        cls.command([cls.nasm, "-O0", "-f", "win64", *nasm_flags(cls.nasm), "-o", obj, asm], tag + "-wrapper-win64")
        cls.command([cls.nasm, "-O0", "-f", "elf64", *nasm_flags(cls.nasm), "-o", stage / "wrapper.elf.o", asm], tag + "-wrapper-elf64")
        driver = stage / "driver.exe"
        cls.command([cls.cc, "-std=c11", "-D_GNU_SOURCE", "-D__USE_MINGW_ANSI_STDIO=1", "-O2", "-Wall", "-Wextra",
                     "-Werror", *([] if WIN else ["-no-pie"]), stage / "driver.c", (obj if WIN else stage / "wrapper.elf.o"), "-o", driver], tag + "-driver-link")
        cls.drivers[tag] = driver
        cls.records.append({"tag": tag, "provenance": provenance,
                            "wrapper_sources": list(compiled.sources),
                            "wrapper_sha256": hashlib.sha256(compiled.assembly.encode()).hexdigest()})
        return driver

    @classmethod
    def command(cls, args, name, expect=0):
        p = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=600)
        (cls.work / (name + ".log")).write_text(p.stdout + p.stderr)
        cls.records.append({"name": name, "command": [str(a) for a in args], "returncode": p.returncode,
                            "stdout": p.stdout, "stderr": p.stderr})
        if expect is not None and p.returncode != expect:
            raise AssertionError(f"{name}: {p.returncode}\n{p.stdout}\n{p.stderr}")
        return p

    @classmethod
    def generate(cls, tag, sources, name, mode=0):
        """Run the production pipeline and return the emitted NASM path."""
        driver = cls.drivers[tag]
        directory = cls.work / (tag + "-" + name)
        directory.mkdir(exist_ok=True)
        if len(sources) == 1:
            source = directory / sources[0][0]
            source.write_text(sources[0][1], encoding="utf-8")
            asm = directory / "module.asm"
            cls.command([driver, source, sources[0][0], asm, str(mode)], name + "-compile")
        else:
            listing = directory / "sources.list"
            lines = []
            for path, text in sources:
                source = directory / path
                source.write_text(text, encoding="utf-8")
                lines.append(f"{path}={source}")
            listing.write_text("\n".join(lines) + "\n", encoding="ascii")
            asm = directory / "module.asm"
            cls.command([driver, listing, "multi", asm, str(mode)], name + "-compile")
        return directory, asm

    @classmethod
    def assemble(cls, asm: Path, name):
        obj = asm.with_suffix(".obj")
        cls.command([cls.nasm, "-O0", "-f", "win64", *nasm_flags(cls.nasm), "-o", obj, asm], name + "-win64")
        cls.command([cls.nasm, "-O0", "-f", "elf64", *nasm_flags(cls.nasm), "-o", asm.with_suffix(".elf.o"), asm], name + "-elf64")
        return obj if WIN else asm.with_suffix(".elf.o")

    @classmethod
    def observe(cls, obj: Path, name, body: str, declarations: str):
        source = obj.parent / (name + ".c")
        source.write_text(
            "#include <stdint.h>\n#include <stdio.h>\n#include <string.h>\n"
            "typedef uint64_t U;\n#define ABI __attribute__((sysv_abi))\n"
            + declarations + "\nint main(void){\n" + body + "\n}\n", encoding="utf-8")
        exe = obj.parent / (name + ".exe")
        cls.command([cls.cc, "-std=c11", "-D_GNU_SOURCE", "-D__USE_MINGW_ANSI_STDIO=1", "-O2", "-Wall",
                     "-Wextra", "-Werror", *([] if WIN else ["-no-pie"]), source, obj, "-o", exe], name + "-link")
        return cls.command([exe], name + "-run")

    def test_scalars_read_write_and_canaries(self):
        for mode in (0, 1):
            directory, asm = self.generate("good", [("scalars.dg", SCALARS)], f"scalars-m{mode}", mode)
            obj = self.assemble(asm, f"scalars-m{mode}")
            dec = []
            for name, ret, args in (("read_cluster", "U", "()"), ("read_hi_u8", "unsigned char", "()"),
                                    ("read_hi_u16", "unsigned short", "()"), ("read_hi_u32", "unsigned int", "()"),
                                    ("read_signed", "long long", "()"), ("read_neg64", "long long", "()"),
                                    ("read_max", "U", "()"), ("read_flag", "_Bool", "()"),
                                    ("bump", "U", "()"), ("write_cluster", "void", "()"),
                                    ("write_neg", "void", "()"), ("clear_flag", "void", "()"),
                                    ("set_ptr", "void", "()"), ("read_ptr_value", "unsigned char", "()")):
                dec.append(f'extern {ret} ABI f_{name}{args} __asm__("{label("scalars", name)}");')
            dec.append(f'extern unsigned char g_narrow_a __asm__("{label("scalars","narrow_a")}");')
            dec.append(f'extern unsigned char g_narrow_b __asm__("{label("scalars","narrow_b")}");')
            dec.append(f'extern unsigned short g_narrow_c __asm__("{label("scalars","narrow_c")}");')
            dec.append(f'extern unsigned int g_narrow_d __asm__("{label("scalars","narrow_d")}");')
            dec.append(f'extern U g_narrow_e __asm__("{label("scalars","narrow_e")}");')
            dec.append(f'extern U g_head __asm__("{label("scalars","canary_head")}");')
            dec.append(f'extern U g_tail __asm__("{label("scalars","canary_tail")}");')
            dec.append(f'extern signed char g_neg_i8 __asm__("{label("scalars","neg_i8")}");')
            dec.append(f'extern short g_neg_i16 __asm__("{label("scalars","neg_i16")}");')
            dec.append(f'extern int g_neg_i32 __asm__("{label("scalars","neg_i32")}");')
            dec.append(f'extern long long g_neg_i64 __asm__("{label("scalars","neg_i64")}");')
            dec.append(f'extern U g_max __asm__("{label("scalars","max_u64")}");')
            dec.append(f'extern unsigned char g_flag __asm__("{label("scalars","flag")}");')
            body = f'''
 if(g_head!=0x0123456789abcdefULL||g_tail!=0xfedcba9876543210ULL) return 1;
 if(f_read_cluster()!=0x11+0x22+0x0102+0x01020304ULL+0x0102030405060708ULL) return 2;
 if(f_read_hi_u8()!=0xff||f_read_hi_u16()!=0xabcd||f_read_hi_u32()!=0xdeadbeefU) return 3;
 if(f_read_signed()!=(long long)(-128-32768-2147483648LL)) return 4;
 if(f_read_neg64()!=INT64_MIN||f_read_max()!=UINT64_MAX) return 5;
 if(!f_read_flag()||g_flag!=1) return 6;
 if(f_bump()!=0x12||g_narrow_a!=0x12||g_narrow_c!=0x0103||g_narrow_e!=0x0102030405060709ULL) return 7;
 if(g_narrow_b!=0x22||g_narrow_d!=0x01020304U) return 8;
 f_write_cluster();
 if(g_narrow_a!=0x5a||g_narrow_b!=0x6b||g_narrow_c!=0x7c8d||g_narrow_d!=0x9e0fa1b2U||g_narrow_e!=0x0102030405060708ULL) return 9;
 if(f_read_cluster()!=0x5a+0x6b+0x7c8d+0x9e0fa1b2ULL+0x0102030405060708ULL) return 10;
 if(g_head!=0x0123456789abcdefULL||g_tail!=0xfedcba9876543210ULL) return 11;
 f_write_neg();
 if(g_neg_i8!=-1||g_neg_i16!=-2||g_neg_i32!=-3||g_neg_i64!=-4) return 12;
 if(f_read_signed()!=-6||f_read_neg64()!=-4) return 13;
 f_clear_flag(); if(f_read_flag()||g_flag!=0) return 14;
 f_set_ptr(); if(f_read_ptr_value()!=0x6b) return 15;
 printf("scalars=%d ok\\n",{mode});return 0;'''
            self.observe(obj, f"scalars-observer-m{mode}", body, "\n".join(dec))

    def test_aggregate_layout_and_static_address(self):
        for mode in (0, 1):
            directory, asm = self.generate("good", [("layout.dg", LAYOUT)], f"layout-m{mode}", mode)
            obj = self.assemble(asm, f"layout-m{mode}")
            dec = []
            for name, ret, args in (("read_v", "U", "()"), ("read_n", "U", "()"),
                                    ("read_byte", "unsigned char", "(U)"), ("write_byte", "void", "(U,unsigned char)"),
                                    ("read_const", "unsigned short", "(U)"), ("const_addr", "const unsigned short*", "(U)"),
                                    ("write_fields", "void", "()"), ("read_zero", "unsigned char", "(U)"),
                                    ("read_word", "unsigned short", "(U)")):
                dec.append(f'extern {ret} ABI f_{name}{args} __asm__("{label("layout", name)}");')
            dec.append(f'extern unsigned char g_head[] __asm__("{label("layout","head")}");')
            dec.append(f'extern unsigned char g_v[] __asm__("{label("layout","v")}");')
            dec.append(f'extern unsigned char g_n[] __asm__("{label("layout","n")}");')
            dec.append(f'extern unsigned char g_bytes[] __asm__("{label("layout","bytes")}");')
            dec.append(f'extern unsigned char g_tail[] __asm__("{label("layout","tail")}");')
            body = '''
 if(g_head[0]!=0x44||g_head[7]!=0x11) return 1;
 const unsigned char want_v[12]={0x34,0x12,0,0,0x88,0x77,0x66,0x55,0x9a,0,0,0};
 for(int i=0;i<12;i++) if(g_v[i]!=want_v[i]) {fprintf(stderr,"v[%d]=%02x\\n",i,g_v[i]);return 2;}
 const unsigned char want_n[20]={0x5a,0,0,0,1,0,0,0,2,0,0,0,3,0,0,0,0xef,0xbe,0,0};
 for(int i=0;i<20;i++) if(g_n[i]!=want_n[i]) {fprintf(stderr,"n[%d]=%02x\\n",i,g_n[i]);return 3;}
 if(f_read_v()!=0x1234+0x55667788ULL+0x9a) return 4;
 if(f_read_n()!=0x5a+1+2+3+0xbeef) return 5;
 if(f_read_byte(0)!=0||f_read_byte(3)!=255||f_read_byte(5)!=5) return 6;
 f_write_byte(2,77); if(g_bytes[2]!=77||f_read_byte(2)!=77) return 7;
 if(g_bytes[0]!=0||g_bytes[1]!=1||g_bytes[4]!=4||g_bytes[5]!=5) return 8;
 if(f_read_const(0)!=9||f_read_const(3)!=6) return 9;
 const unsigned short* a=f_const_addr(2); if(a!=f_const_addr(2)||*a!=7) return 10;
 if(f_read_zero(0)!=0||f_read_zero(11)!=0) return 11;
 if(f_read_word(0)!=65535||f_read_word(1)!=0||f_read_word(2)!=4660) return 12;
 f_write_fields();
 if(f_read_v()!=(0x1234+0x55667788ULL+0x77)) return 13;
 if(f_read_n()!=0x5a+1+0xaabbccddULL+3+0x1234) return 14;
 if(g_v[8]!=0x77||g_n[16]!=0x34||g_n[17]!=0x12) return 15;
 if(g_tail[0]!=0xdd||g_tail[7]!=0xaa) return 16;
 printf("layout=@MODE@ ok\\n");return 0;'''.replace("@MODE@", str(mode))
            self.observe(obj, f"layout-observer-m{mode}", body, "\n".join(dec))

    def test_static_pointer_initializers_real_dong_both_modes(self):
        source='module native;\npub const fixed:[3]u16=[0x11,0x2233,0x4455];\npub var values:[4]u16=[3,5,7,11];\npub struct Bag{pub tag:u8,pub word:u32}\npub var bag:Bag=Bag{tag:0xaa,word:0x12345678};\npub var p:*u16=&values[2];\npub var q:*u32=&bag.word;\npub var r:*const u16=&fixed[1];\npub var obs:[8]u64=[0;8];\npub fn probe()*u64{unsafe{\n obs[0]=*p as u64;obs[1]=*q as u64;obs[2]=*r as u64;\n *p=0xbeef;*q=0xaabbccdd;\n obs[3]=values[2] as u64;obs[4]=bag.word as u64;obs[5]=*r as u64;\n if p==&values[2]{obs[6]=4;}else{obs[6]=999;}if q==&bag.word{obs[7]=4;}else{obs[7]=999;}\n }return &obs[0];}\n'
        declarations='extern U* ABI probe(void) __asm__("'+label('native','probe')+'");'
        body='const U expected[8]={7,0x12345678,0x2233,0xbeef,0xaabbccdd,0x2233,4,4}; U*p=probe();for(unsigned i=0;i<8;i++)if(p[i]!=expected[i])return 1;return 0;'
        for mode in (0,1):
            _,asm=self.generate('good',[('native.dg',source)],'static-ptr-'+str(mode),mode)
            obj=self.assemble(asm,'static-ptr-'+str(mode))
            self.observe(obj,'static-ptr-observe-'+str(mode),body,declarations)

    def test_two_modules_same_item_pub_private_and_cross_function(self):
        for mode in (0, 1):
            directory, asm = self.generate("good", [("main.dg", MAIN), ("dep.dg", DEP)], f"multi-m{mode}", mode)
            obj = self.assemble(asm, f"multi-m{mode}")
            dec = [f'extern U ABI f_read_b(void) __asm__("{label("main","read_b")}");',
                   f'extern U ABI f_cross(void) __asm__("{label("main","cross")}");',
                   f'extern U ABI f_with_arg(void) __asm__("{label("main","with_arg")}");',
                   f'extern U ABI f_read_a(void) __asm__("{label("dep","read_a")}");',
                   f'extern U ABI f_bump_a(void) __asm__("{label("dep","bump_a")}");',
                   f'extern U g_main_shared __asm__("{label("main","shared")}");',
                   f'extern U g_dep_shared __asm__("{label("dep","shared")}");']
            body = '''
 if(f_read_b()!=44) return 1;
 if(f_cross()!=33+12) return 2;
 if(g_dep_shared!=12||g_main_shared!=33||f_read_a()!=34) return 3;
 if(f_read_b()!=45) return 4;
 if(f_with_arg()!=19) return 5;
 printf("multi=@MODE@ ok\\n");return 0;'''.replace("@MODE@", str(mode))
            self.observe(obj, f"multi-observer-m{mode}", body, "\n".join(dec))
        private_source = self.work / "privbad.dg"
        private_source.write_text(PRIVATE_BAD, encoding="utf-8")
        dep_source = self.work / "dep.dg"
        dep_source.write_text(DEP, encoding="utf-8")
        listing = self.work / "priv.list"
        listing.write_text(f"privbad.dg={private_source}\ndep.dg={dep_source}\n", encoding="ascii")
        out = self.work / "priv.asm"
        out.write_bytes(b"unchanged")
        p = self.command([self.drivers["good"], listing, "multi", out, "0"], "private-reject", expect=None)
        self.assertEqual(p.returncode, 10, p.stderr)
        self.assertIn("frontend status=", p.stderr)
        self.assertEqual(out.read_bytes(), b"unchanged")

    def test_mainline_global_case_is_positive_and_extern_stays_rejected(self):
        directory = self.work / "mainline"
        directory.mkdir(exist_ok=True)
        positive = directory / "global_ok.dg"
        positive.write_text("module globalok;\nvar value:u64=1;\npub fn read()u64{return value;}\n", encoding="utf-8")
        asm = directory / "global.asm"
        self.command([self.drivers["good"], positive, "globalok.dg", asm, "0"], "mainline-global-positive")
        obj = self.assemble(asm, "mainline-global")
        dec = [f'extern U ABI f_read(void) __asm__("{label("globalok","read")}");']
        self.observe(obj, "mainline-global-observer", 'if(f_read()!=1) return 1;\nprintf("global positive ok\\n");\nreturn 0;', "\n".join(dec))
        negative = directory / "extern.dg"
        negative.write_text(EXTERN_BAD, encoding="utf-8")
        out = directory / "extern.asm"
        out.write_bytes(b"unchanged")
        p = self.command([self.drivers["good"], negative, "extbad.dg", out, "0"], "extern-reject", expect=None)
        self.assertEqual(p.returncode, 11, p.stderr)
        self.assertIn("lower status=3", p.stderr)
        self.assertEqual(out.read_bytes(), b"unchanged")

    def test_three_real_bad_dong_bodies_execute_and_are_rejected(self):
        # Good side first: the same inputs must build, link and pass.
        self.test_scalars_read_write_and_canaries()
        # 1. wrong global address: GLOBAL static addresses gain +8.
        address_old = 'if op==ir.STATIC_ADDRESS{put(s,"lea rax, [rel ");symbol(s,(*x).value);put(s,"]\\n");return slotstore(s,0,(*x).destination);}'
        address_new = 'if op==ir.STATIC_ADDRESS{put(s,"lea rax, [rel ");symbol(s,(*x).value);if (*g).symbols[(*x).value].kind==names.GLOBAL{put(s,"+8");}put(s,"]\\n");return slotstore(s,0,(*x).destination);}'
        self.build_driver("bad-address", {"nasm_program.dg": (address_old, address_new)})
        directory, asm = self.generate("bad-address", [("scalars.dg", SCALARS)], "bad-address", 0)
        obj = self.assemble(asm, "bad-address")
        dec = [f'extern U ABI f_read_max(void) __asm__("{label("scalars","read_max")}");']
        body = 'U got=f_read_max(); if(got!=UINT64_MAX){fprintf(stderr,"bad global address observed %llu\\n",(unsigned long long)got);return 0;} return 9;'
        # The bad body must succeed at build/link and return normally; exact value assertion rejects it.
        self.observe(obj, "bad-address-observer", body, "\n".join(dec))
        # 2. wrong narrow store width: every scalar STORE writes 64 bits.
        store_old = 'else{store(s,0,11,0,ir.width(g,t));}return (*s).status==0;'
        store_new = 'else{store(s,0,11,0,64);}return (*s).status==0;'
        self.build_driver("bad-narrow", {"nasm_program.dg": (store_old, store_new)})
        directory, asm = self.generate("bad-narrow", [("scalars.dg", SCALARS)], "bad-narrow", 0)
        obj = self.assemble(asm, "bad-narrow")
        dec = [f'extern U ABI f_bump(void) __asm__("{label("scalars","bump")}");',
               f'extern unsigned char g_b __asm__("{label("scalars","narrow_b")}");',
               f'extern unsigned char g_a __asm__("{label("scalars","narrow_a")}");']
        body = '''if(f_bump()!=0x12) return 8;
 if(g_a==0x12&&g_b!=0x22){
  fprintf(stderr,"adjacent byte changed to %u\\n",g_b);
  return 0;
 }
 return 9;'''
        self.observe(obj, "bad-narrow-observer", body, "\n".join(dec))
        # 3. capacity failure publishes output early: the driver's atomicity contract must reject it.
        publish_old = 'if s.status!=0{return s.status;}if out.len<s.at{return CAPACITY;}'
        publish_new = 'if s.status!=0{return s.status;}if out.len<s.at{if out.len!=0{out[0]=(*w).text[0];}return CAPACITY;}'
        self.build_driver("bad-publish", {"nasm_program.dg": (publish_old, publish_new)})
        directory = self.work / "bad-publish"
        directory.mkdir(exist_ok=True)
        source = directory / "scalars.dg"
        source.write_text(SCALARS, encoding="utf-8")
        out = directory / "module.asm"
        p = self.command([self.drivers["bad-publish"], source, "scalars.dg", out, "0"], "bad-publish-run", expect=None)
        self.assertEqual(p.returncode, 96, p.stderr)
        self.assertIn("contract failure", p.stderr)
        self.assertFalse(out.exists())

    @classmethod
    def tearDownClass(cls):
        after = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in cls.inputs}
        stable = after == cls.inputs
        provenance_after = {}
        for tag, records in cls.provenance.items():
            for rel, record in records.items():
                staged = cls.work / tag / rel
                provenance_after[tag + "/" + rel] = hashlib.sha256(staged.read_bytes()).hexdigest() if staged.exists() else None
        (cls.work / "summary.json").write_text(json.dumps({
            "records": cls.records, "inputs_before": cls.inputs, "inputs_after": after,
            "source_stable": stable, "staged_after": provenance_after,
            "L3A_complete": False, "global_scope": "scalar/aggregate/zero/null and checked static storage pointer initializers",
            "static_address_frontend": "L3PTR7 separate checked-static-place scope; arbitrary unsafe casts/dynamic initializers remain rejected",
        }, indent=2) + "\n")
        if not stable:
            raise AssertionError("candidate or read-only input changed during the test run")


if __name__ == "__main__":
    unittest.main()
