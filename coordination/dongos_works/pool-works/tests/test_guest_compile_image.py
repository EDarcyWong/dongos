"""Actual Dong guest compile_image adapter: frontend Graph → emit → assemble → ELF.

Production module is compiled debug/release with a thin export wrapper, linked to a
native C harness that builds a live frontend.Graph, calls compile_image, validates
the ELF with the kernel planner, and on this host maps the image to call the entry
as a SysV function (never as OS _start). Failures keep Result/out atomic; at least
two real bad-Dong copies are compiled and rejected by named assertions.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest
import uuid

WORKS = Path(__file__).resolve().parents[2]
ROOT = WORKS
if not (ROOT / 'lang').is_dir() and (WORKS / 'project.json').is_file():
    source = Path(json.loads((WORKS / 'project.json').read_text(encoding='utf-8'))['source_root'])
    ROOT = (WORKS / source).resolve() if not source.is_absolute() else source
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lang.dongc import compile_file
from lang.tests.test_dongc import tool, nasm_flags

SOURCE = WORKS / 'pool-works/lang/bootstrap/guest_compile_image.dg'
OK, INVALID, CAPACITY, UNSUPPORTED = 0, 1, 2, 3
SYMBOL = 4
WORKSPACE, LOWER, EMIT, ASSEMBLE = 0, 1, 2, 3
MAX = 2 ** 64 - 1
PREFLIGHTS = 18
RESULT_FIELDS = ('status', 'stage', 'code', 'unit', 'node', 'detail', 'used', 'text', 'written')

# module a / item f → CR3 mangling used by nasm_program.
ENTRY_F = '__dong_m' + b'a'.hex() + '_n' + b'f'.hex()

# Locals + branch/loop + cross-function call (matches CLI emit-asm coverage shape).
SAMPLE = (
    'module a;'
    'fn helper(x:u64)u64{return x*2;}'
    'pub fn f(x:u64)u64{'
    'var n:u64=0;var i:u64=0;'
    'while i<x{if i==3{i+=1;continue;}n+=helper(i);i+=1;}'
    'return n;}'
)
SAMPLE_PATH = 'a.dg'
# Independent host expectation for f(n).
def expected_f(n: int) -> int:
    total = 0
    for i in range(n):
        if i != 3:
            total += 2 * i
    return total


UNSUPPORTED_SRC = 'module a;var state:u64=7;fn f()u64{return state;}'

WRAPPER = '''module probe.guest_compile_image_export;
import bootstrap.guest_compile_image as m;
import bootstrap.frontend as front;
import bootstrap.compiler_driver as driver;
import bootstrap.native_assembler as nasm;
import exec.elf as elf;
export("dong_guest_compile_image") pub unsafe fn compile_image(
 g:*const front.Graph,limits:*const driver.Limits,mode:u64,
 storage:*u8,sn:usize,text:*u8,tn:usize,entry:*const u8,en:usize,
 w:*const nasm.Workspace,out:*u8,on:usize,r:*m.Result)u64{unsafe{
 return m.compile_image(g,limits,mode,slice_from_raw_parts(storage,sn),slice_from_raw_parts(text,tn),
  slice_from_raw_parts(entry,en),w,slice_from_raw_parts(out,on),r);
}}
export("kernel_validate") fn validate(raw:*const u8,n:usize,out:*elf.Plan)u64{unsafe{
 match elf.validate(slice_from_raw_parts(raw,n),0,out){ok=>{return 0;},err(code)=>{return code;},}
}}
'''

HARNESS = r'''
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
#include <unistd.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef struct{const void*p;uint64_t n;} Slice;
typedef struct{uint64_t root;Slice path,bytes;} Source;
typedef struct{uint64_t entry,roots,depth;} Options;
typedef struct{uint64_t v[10];} FrontLimits;
typedef struct{Slice arena,sources,units,tokens,strings,nodes,edges,symbols,refs,types,fields,node_types,
 values,value_states,limbs,layouts,field_offsets,info;uint64_t entry;} Graph;
typedef struct{uint64_t status,exit_code,stage,code,detail,source,offset,used;Graph graph;} FrontResult;
typedef struct{uint64_t functions,instructions,arguments,text,piece,parameters,locations;} EmitLimits;
typedef struct{Slice labels,table,text,data;} Workspace;
typedef struct{uint64_t status,stage,code,unit,node,detail,used,text,written;} ImageResult;
typedef struct{uint64_t virtual_addr,file_offset,file_size,memory_size,map_start,map_size,flags,alignment;} Seg;
typedef struct{uint64_t entry,load_bias,segment_count,page_count,relocation_count,rela_offset;Seg segments[16];} Plan;
_Static_assert(sizeof(Options)==24&&sizeof(FrontLimits)==80&&sizeof(Source)==40&&sizeof(Graph)==296&&sizeof(FrontResult)==360,"frontend ABI");
_Static_assert(sizeof(EmitLimits)==56&&sizeof(Workspace)==64&&sizeof(ImageResult)==72&&sizeof(Plan)==1072,"image ABI");
extern uint64_t ABI dong_frontend_check(const Options*,const Source*,uint64_t,const FrontLimits*,void*,uint64_t,FrontResult*);
extern uint64_t ABI dong_guest_compile_image(const Graph*,const EmitLimits*,uint64_t,void*,uint64_t,void*,uint64_t,
 const void*,uint64_t,const Workspace*,void*,uint64_t,ImageResult*);
extern uint64_t ABI kernel_validate(const void*,uint64_t,void*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static void rd(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void wr(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static int filled(const void*p,uint64_t n){const uint8_t*b=p;for(uint64_t i=0;i<n;i++)if(b[i]!=0xa5)return 0;return 1;}
static void*page_alloc(uint64_t n){
#ifdef _WIN32
 return VirtualAlloc(NULL,(SIZE_T)(n?n:1),MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*p=mmap(NULL,n?n:1,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return p==MAP_FAILED?NULL:p;
#endif
}
static void page_free(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;if(p&&!VirtualFree(p,0,MEM_RELEASE))exit(98);
#else
 if(p&&munmap(p,n?n:1))exit(98);
#endif
}
static void*readonly_copy(const void*p,uint64_t n){
 void*q=page_alloc(n);if(!q)exit(95);if(n)memcpy(q,p,n);
#ifdef _WIN32
 DWORD old;if(!VirtualProtect(q,n?n:1,PAGE_READONLY,&old))exit(98);
#else
 if(mprotect(q,n?n:1,PROT_READ))exit(98);
#endif
 return q;
}
static void*alloc_guard(uint64_t n){uint8_t*p=malloc(n+64);if(!p)exit(95);memset(p,0xa5,n+64);return p+32;}
static void free_guard(void*p){free((uint8_t*)p-32);}
static int guard(const void*p,uint64_t n){return filled((const uint8_t*)p-32,32)&&filled((const uint8_t*)p+n,32);}
/* Map a validated static ELF at its planned VAs and call entry as SysV, never as _start. */
static uint64_t call_entry(const uint8_t*image,uint64_t written,const Plan*plan,uint64_t arg,uint64_t*out_value){
 if(!plan->segment_count||!plan->entry)return 1;
 uint64_t lo=UINT64_MAX,hi=0;
 for(uint64_t i=0;i<plan->segment_count;i++){
  const Seg*s=&plan->segments[i];
  if(s->map_start<lo)lo=s->map_start;
  if(s->map_start+s->map_size>hi)hi=s->map_start+s->map_size;
 }
 if(hi<=lo)return 2;
 uint64_t span=hi-lo;
#ifdef _WIN32
 void*base=VirtualAlloc((void*)(uintptr_t)lo,(SIZE_T)span,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*base=mmap((void*)(uintptr_t)lo,span,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0);
 if(base==MAP_FAILED)base=NULL;
#endif
 if(!base||(uint64_t)(uintptr_t)base!=lo){if(base){
#ifdef _WIN32
  VirtualFree(base,0,MEM_RELEASE);
#else
  munmap(base,span);
#endif
 }return 3;}
 for(uint64_t i=0;i<plan->segment_count;i++){
  const Seg*s=&plan->segments[i];
  if(s->file_offset+s->file_size>written){
#ifdef _WIN32
   VirtualFree(base,0,MEM_RELEASE);
#else
   munmap(base,span);
#endif
   return 4;}
  memset((void*)(uintptr_t)s->virtual_addr,0,(size_t)s->memory_size);
  if(s->file_size)memcpy((void*)(uintptr_t)s->virtual_addr,image+s->file_offset,(size_t)s->file_size);
 }
 for(uint64_t i=0;i<plan->segment_count;i++){
  const Seg*s=&plan->segments[i];
  uint32_t prot;
#ifdef _WIN32
  DWORD old;
  if(s->flags&1)prot=PAGE_EXECUTE_READ;else prot=PAGE_READWRITE;
  if(!VirtualProtect((void*)(uintptr_t)s->map_start,(SIZE_T)s->map_size,prot,&old)){
   VirtualFree(base,0,MEM_RELEASE);return 5;}
#else
  int p=PROT_READ;if(s->flags&1)p|=PROT_EXEC;if(s->flags&2)p|=PROT_WRITE;
  if(mprotect((void*)(uintptr_t)s->map_start,(size_t)s->map_size,p)){munmap(base,span);return 5;}
#endif
 }
 typedef uint64_t ABI (*Fn)(uint64_t);
 *out_value=((Fn)(uintptr_t)plan->entry)(arg);
#ifdef _WIN32
 VirtualFree(base,0,MEM_RELEASE);
#else
 munmap(base,span);
#endif
 return 0;
}
static unsigned invalid_preflights(void){
 static _Alignas(16) unsigned char arena[65536],saved[65536];
 unsigned count=0;
 for(unsigned scenario=0;scenario<PREFLIGHT_COUNT;scenario++){
  memset(arena,0xa5,sizeof arena);
  Graph*g=(Graph*)(arena+256);
  EmitLimits*limits=(EmitLimits*)(arena+1024);
  Workspace*w=(Workspace*)(arena+2048);
  ImageResult*r=(ImageResult*)(arena+4096);
  uint8_t*storage=arena+8192;uint64_t sn=256;
  uint8_t*text=arena+12288;uint64_t tn=256;
  uint8_t*entry=arena+16384;uint64_t en=6;memcpy(entry,"abcdef",6);
  uint8_t*out=arena+20480;uint64_t on=512;
  uint8_t*labels=arena+28672;uint8_t*table=arena+32768;uint8_t*wt=arena+36864;uint8_t*wd=arena+40960;
  memset(g,0,sizeof(*g));*limits=(EmitLimits){8,256,64,1024,128,32,32};
  *w=(Workspace){{labels,4},{table,16},{wt,256},{wd,256}};
  Graph*gp=g;EmitLimits*lp=limits;Workspace*wp=w;ImageResult*rp=r;
  uint8_t*sp=storage;uint8_t*tp=text;uint8_t*ep=entry;uint8_t*op=out;
  switch(scenario){
   case 0:gp=NULL;break;case 1:lp=NULL;break;case 2:wp=NULL;break;case 3:rp=NULL;break;
   case 4:gp=(Graph*)(arena+257);break;case 5:lp=(EmitLimits*)(arena+1025);break;
   case 6:wp=(Workspace*)(arena+2049);break;case 7:rp=(ImageResult*)(arena+4097);break;
   case 8:gp=(Graph*)(uintptr_t)(UINT64_MAX-7);break;
   case 9:lp=(EmitLimits*)(uintptr_t)(UINT64_MAX-7);break;
   case 10:op=sp;break;case 11:tp=op;break;case 12:rp=(ImageResult*)op;break;
   case 13:w->labels.p=op;break;case 14:w->table.n=UINT64_MAX/8+1;break;
   case 15:w->labels.n=UINT64_MAX/32+1;break;case 16:sp=ep;sn=en?en:1;break;
   default:op=(uint8_t*)(uintptr_t)(UINT64_MAX-7);on=16;break;
  }
  memcpy(saved,arena,sizeof arena);
  uint64_t rc=dong_guest_compile_image(gp,lp,0,sp,sn,tp,tn,ep,en,wp,op,on,rp);
  if(rc!=1||memcmp(saved,arena,sizeof arena)){fprintf(stderr,"preflight %u rc=%llu\n",scenario,(unsigned long long)rc);exit(94);}
  count++;
 }
 return count;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t flag,cases;rd(&flag,8);uint64_t preflights=flag?invalid_preflights():0;rd(&cases,8);wr(&preflights,8);
 FrontLimits fl={{2048,2048,4096,64,2080,4096,65536,65536,2048,65536}};
 Options options={0,1,32};
 while(cases--){
  uint64_t hdr[12];rd(hdr,sizeof hdr);
  uint64_t sl=hdr[0],pl=hdr[1],el=hdr[2],mode=hdr[3];
  EmitLimits limits={hdr[4],hdr[5],hdr[6],hdr[7],hdr[8],hdr[9],hdr[10]};
  uint64_t kind=hdr[11];
  if(sl>1<<20||pl>4096||el>4096)exit(94);
  uint8_t*src=malloc(sl+1);uint8_t*path=malloc(pl+1);uint8_t*entry=malloc(el+1);
  if(!src||!path||!entry)exit(95);
  rd(src,sl);rd(path,pl);rd(entry,el);
  const uint64_t front_cap=16ull<<20,store_cap=4ull<<20,text_cap=1ull<<20,out_cap=1ull<<20;
  uint8_t*front_storage=alloc_guard(front_cap);
  FrontResult fr;memset(&fr,0xa5,sizeof fr);
  Source cat={0,{readonly_copy(path,pl),pl},{readonly_copy(src,sl),sl}};
  const Source*sc=readonly_copy(&cat,sizeof cat);
  const Options*op=readonly_copy(&options,sizeof options);
  const FrontLimits*flp=readonly_copy(&fl,sizeof fl);
  uint64_t front_rc=dong_frontend_check(op,sc,1,flp,front_storage,front_cap,&fr);
  uint8_t*storage=alloc_guard(store_cap);uint8_t*text=alloc_guard(text_cap);
  uint8_t*labels=alloc_guard(128*32);uint8_t*table=alloc_guard(512*8);
  uint8_t*wtext=alloc_guard(1<<20);uint8_t*wdata=alloc_guard(1<<20);uint8_t*out=alloc_guard(out_cap);
  ImageResult result;memset(&result,0xa5,sizeof result);
  Workspace w={{labels,128},{table,512},{wtext,1<<20},{wdata,1<<20}};
  uint64_t sn=store_cap,tn=text_cap,on=out_cap;
  if(kind==1){limits.text=64;limits.piece=16;limits.parameters=4;limits.locations=4;} /* emit capacity */
  if(kind==2){on=64;} /* assemble/out capacity */
  if(kind==3){/* keep defaults; wrong entry supplied by Python */}
  if(kind==4){sn=1024;} /* tiny storage → workspace capacity */
  uint8_t out_before[64];memcpy(out_before,out,on<64?on:64);
  uint64_t image_rc=1;uint64_t guards=1;uint64_t validation=0;uint64_t call_rc=0;uint64_t call_value=0;
  Plan plan;memset(&plan,0,sizeof plan);
  if(front_rc==0){
   image_rc=dong_guest_compile_image(&fr.graph,&limits,mode,storage,sn,text,tn,entry,el,&w,out,on,&result);
   if(!guard(storage,sn)||!guard(text,tn)||!guard(out,on)||!guard(labels,128*32)||!guard(table,512*8)
      ||!guard(wtext,1<<20)||!guard(wdata,1<<20))guards=0;
   if(image_rc==0){
    validation=kernel_validate(out,result.written,&plan);
    if(!validation){
     call_rc=call_entry(out,result.written,&plan,7,&call_value);
    }
   }else if(image_rc!=1){
    /* Non-INVALID failure must leave unused ELF capacity as canary. */
    uint64_t keep=result.written?result.written:0;
    if(!filled(out+keep,on-keep))guards=0;
    if(on>=64&&memcmp(out,out_before,64)&&result.written==0){
     /* allow workspace/text mutation; ELF prefix must stay canary when written=0 */
     if(!filled(out,on))guards=0;
    }
   }
  }else{
   image_rc=0xffff;guards=guard(front_storage,front_cap);
  }
  uint64_t head[8]={front_rc,image_rc,guards,validation,call_rc,call_value,result.written,0};
  wr(head,sizeof head);wr(&result,sizeof result);
  if(image_rc==0&&result.written)wr(out,result.written);
  free(src);free(path);free(entry);
  free_guard(front_storage);free_guard(storage);free_guard(text);free_guard(labels);free_guard(table);
  free_guard(wtext);free_guard(wdata);free_guard(out);
  page_free((void*)sc,sizeof *sc);page_free((void*)op,sizeof *op);page_free((void*)flp,sizeof *flp);
  page_free((void*)cat.path.p,pl);page_free((void*)cat.bytes.p,sl);
 }
 return 0;
}
'''.replace('PREFLIGHT_COUNT', str(PREFLIGHTS))

DEFAULT_LIMITS = (128, 16384, 4096, 1024 * 1024, 1024, 128, 256)


def pack_case(source: str, path: str, entry: str, mode: int, limits=DEFAULT_LIMITS, kind: int = 0) -> bytes:
    sb, pb, eb = source.encode(), path.encode(), entry.encode()
    return struct.pack('<12Q', len(sb), len(pb), len(eb), mode, *limits, kind) + sb + pb + eb


class GuestCompileImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest('native guest compile image gate requires NASM/GCC')
        cls.work = WORKS / 'pool-works/build/GUEST4' / ('run-' + uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        (cls.work / 'probe.c').write_text(HARNESS, encoding='utf-8')
        cls.records = []
        cls.inputs = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in [SOURCE, SOURCE.with_suffix('.md'), Path(__file__)]}
        cls.snapshot = cls.work / 'snapshot'
        for directory in ('bootstrap', 'std'):
            shutil.copytree(ROOT / 'lang' / directory, cls.snapshot / 'lang' / directory)
        (cls.snapshot / 'lang/bootstrap/guest_compile_image.dg').write_bytes(SOURCE.read_bytes())
        (cls.snapshot / 'exec').mkdir(parents=True)
        shutil.copy2(ROOT / 'kernel/exec/elf.dg', cls.snapshot / 'exec/elf.dg')
        cls.wrapper = cls.work / 'wrapper'
        (cls.wrapper / 'probe').mkdir(parents=True)
        (cls.wrapper / 'probe/guest_compile_image_export.dg').write_text(WRAPPER, encoding='utf-8')
        cls.roots = [cls.wrapper, cls.snapshot / 'lang', cls.snapshot / 'lang/std', cls.snapshot]
        cls.executables = {mode: cls.build(mode, mode) for mode in ('debug', 'release')}

    @classmethod
    def command(cls, cmd, name):
        r = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, timeout=600)
        (cls.work / (name + '.log')).write_text(r.stdout + r.stderr, encoding='utf-8')
        if r.returncode:
            raise AssertionError((name, r.returncode, r.stdout, r.stderr))

    @classmethod
    def build(cls, mode, name, roots=None):
        roots = roots or cls.roots
        compiled = compile_file(cls.wrapper / 'probe/guest_compile_image_export.dg', roots=roots, mode=mode)
        asm = cls.work / (name + '.asm')
        asm.write_text(compiled.assembly, encoding='utf-8')
        native = 'win64' if os.name == 'nt' else 'elf64'
        obj = cls.work / (name + '.o')
        exe = cls.work / (name + ('.exe' if os.name == 'nt' else ''))
        for fmt in ('elf64', 'win64'):
            output = obj if fmt == native else cls.work / (name + '.' + fmt + '.o')
            cls.command([cls.nasm, '-f', fmt, *nasm_flags(cls.nasm), '-o', output, asm], name + '-' + fmt)
        cls.command([cls.cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                     cls.work / 'probe.c', obj, '-o', exe], name + '-link')
        return exe

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls, 'work'):
            return
        assert cls.inputs == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                              [SOURCE, SOURCE.with_suffix('.md'), Path(__file__)]}, 'inputs changed'
        files = {p.relative_to(cls.work).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in cls.work.rglob('*') if p.is_file()}
        (cls.work / 'summary.json').write_text(json.dumps(dict(
            source_sha256=cls.inputs, artifact_sha256=files, records=cls.records,
            groups=len(cls.records), integrated=False, OS_VM_built=False,
            entry_symbol=ENTRY_F, sample_sha256=hashlib.sha256(SAMPLE.encode()).hexdigest()), indent=2) + '\n')

    def run_cases(self, exe, cases, label, preflight=True):
        payload = bytearray(struct.pack('<2Q', int(preflight), len(cases)))
        for c in cases:
            payload.extend(c['payload'])
        (self.work / (label + '.input')).write_bytes(payload)
        run = subprocess.run([str(exe)], input=bytes(payload), capture_output=True, timeout=600)
        (self.work / (label + '.output')).write_bytes(run.stdout)
        (self.work / (label + '.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode, 0, (label, run.stderr.decode(errors='replace')[:2000]))
        preflights, = struct.unpack_from('<Q', run.stdout, 0)
        self.assertEqual(preflights, PREFLIGHTS if preflight else 0, label)
        offset = 8
        results = []
        for index, c in enumerate(cases):
            front_rc, image_rc, guards, validation, call_rc, call_value, written, _ = struct.unpack_from(
                '<8Q', run.stdout, offset)
            raw_result = run.stdout[offset + 64:offset + 136]
            offset += 136
            image = b''
            if image_rc == 0 and written:
                image = run.stdout[offset:offset + written]
                offset += written
            where = (label, index, c.get('name', index))
            self.assertEqual(guards, 1, where + ('guard/atomicity',))
            self.assertEqual(front_rc, c['front'], where + ('frontend',))
            if c['front'] != 0:
                results.append(dict(front=front_rc))
                continue
            self.assertEqual(image_rc, c['status'], where + ('status', image_rc, struct.unpack('<9Q', raw_result)))
            got = dict(zip(RESULT_FIELDS, struct.unpack('<9Q', raw_result)))
            if c['status'] == INVALID:
                self.assertEqual(raw_result, b'\xa5' * 72, where + ('guard/atomicity',))
            else:
                for key, value in c.get('result', {}).items():
                    self.assertEqual(got[key], value, where + (key, got))
                if c['status'] == OK:
                    self.assertEqual(got['written'], written, where)
                    self.assertEqual(got['stage'], ASSEMBLE, where)
                    self.assertEqual(validation, 0, where + ('elf-validate', validation))
                    self.assertTrue(image.startswith(b'\x7fELF'), where)
                    self.assertEqual(call_rc, 0, where + ('call-entry', call_rc))
                    self.assertEqual(call_value, c['call'], where + ('return-value',))
                else:
                    self.assertEqual(written, 0, where)
                    self.assertEqual(got['written'], 0, where)
                    if 'stage' in c.get('result', {}):
                        self.assertEqual(got['stage'], c['result']['stage'], where)
            results.append(dict(front=front_rc, status=image_rc, result=got if c['status'] != INVALID else None,
                                validation=validation, call_rc=call_rc, call_value=call_value,
                                image_sha256=hashlib.sha256(image).hexdigest() if image else None))
        self.assertEqual(offset, len(run.stdout), label)
        return results

    def run_both(self, cases, label, preflight=True):
        out = {}
        for mode, exe in self.executables.items():
            out[mode] = self.run_cases(exe, cases, label + '-' + mode, preflight)
        return out

    def case(self, name, source, entry=ENTRY_F, mode=0, limits=DEFAULT_LIMITS, kind=0,
             status=OK, front=0, result=None, call=None):
        if call is None and status == OK:
            call = expected_f(7)
        return dict(name=name, payload=pack_case(source, SAMPLE_PATH, entry, mode, limits, kind),
                    status=status, front=front, result=result or {}, call=call)

    def test_success_debug_release_and_validate(self):
        cases = [
            self.case('sample-debug', SAMPLE, mode=0),
            self.case('sample-release', SAMPLE, mode=1),
        ]
        results = self.run_both(cases, 'success')
        # Same emit mode must be bit-identical across seed debug/release builds.
        self.assertEqual(results['debug'][0]['image_sha256'], results['release'][0]['image_sha256'])
        self.assertEqual(results['debug'][1]['image_sha256'], results['release'][1]['image_sha256'])
        for mode in results:
            self.assertGreater(results[mode][0]['result']['text'], 0)
            self.assertGreater(results[mode][0]['result']['written'], 64)
        self.records.append(dict(test='success-validate-call', cases=len(cases), modes=2, passed=True,
                                 entry=ENTRY_F, call=expected_f(7)))

    def test_emit_failures_leave_elf_untouched(self):
        cases = [
            # Module-level state is rejected by lower_program (not nasm emit).
            self.case('unsupported-global', UNSUPPORTED_SRC, status=UNSUPPORTED,
                      result=dict(status=UNSUPPORTED, stage=LOWER, text=0, written=0)),
            # Shrunk emit text/piece limits still allocate the arena, then emit hits CAPACITY.
            self.case('emit-capacity', SAMPLE, kind=1, status=CAPACITY,
                      result=dict(status=CAPACITY, stage=EMIT, text=0, written=0)),
            self.case('tiny-storage', SAMPLE, kind=4, status=CAPACITY,
                      result=dict(status=CAPACITY, stage=WORKSPACE, text=0, written=0)),
        ]
        self.run_both(cases, 'emit-fail')
        self.records.append(dict(test='emit-failures-atomic', cases=len(cases), modes=2, passed=True))

    def test_assemble_failures_keep_text_length(self):
        cases = [
            self.case('missing-entry', SAMPLE, entry='not_a_label', status=SYMBOL,
                      result=dict(status=SYMBOL, stage=ASSEMBLE, written=0)),
            self.case('out-capacity', SAMPLE, kind=2, status=CAPACITY,
                      result=dict(status=CAPACITY, stage=ASSEMBLE, written=0)),
        ]
        rows = self.run_both(cases, 'assemble-fail')
        for mode in rows:
            for row in rows[mode]:
                self.assertGreater(row['result']['text'], 0)
        self.records.append(dict(test='assemble-failures-keep-text', cases=len(cases), modes=2, passed=True))

    def test_mode_matrix_small(self):
        # Two more success vectors under the 24-case budget (structural invalids are separate).
        cases = [
            self.case('f0-debug', SAMPLE, mode=0, call=expected_f(7)),
            self.case('f0-release', SAMPLE, mode=1, call=expected_f(7)),
        ]
        self.run_both(cases, 'modes', preflight=False)
        self.records.append(dict(test='mode-matrix', cases=len(cases), modes=2, passed=True))

    def bad_build(self, name, old, new):
        source = SOURCE.read_text(encoding='utf-8')
        self.assertEqual(source.count(old), 1, name)
        root = self.work / name
        for directory in ('bootstrap', 'std'):
            shutil.copytree(ROOT / 'lang' / directory, root / 'lang' / directory)
        (root / 'lang/bootstrap/guest_compile_image.dg').write_text(source.replace(old, new, 1), encoding='utf-8')
        (root / 'exec').mkdir(parents=True)
        shutil.copy2(ROOT / 'kernel/exec/elf.dg', root / 'exec/elf.dg')
        roots = [self.wrapper, root / 'lang', root / 'lang/std', root]
        return {mode: self.build(mode, name + '-' + mode, roots=roots) for mode in ('debug', 'release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        good = [self.case('baseline', SAMPLE)]
        self.run_both(good, 'bad-baseline', preflight=False)
        controls = [
            # Skip the assembler entirely and forge a successful ELF publish.
            ('bad-skip-assemble',
             ' let assembled=nasm.assemble(source,entry,w,out,&ar);\n'
             ' if assembled==INVALID{\n'
             '  // Should be unreachable after our preflight; keep caller Result/out untouched.\n'
             '  return INVALID;\n'
             ' }\n'
             ' if assembled!=OK{\n'
             '  return publish(r,ar.status,ASSEMBLE,ar.status,MAX as usize,MAX as usize,ar.detail,er.used,er.written,0);\n'
             ' }\n'
             ' return publish(r,OK,ASSEMBLE,0,MAX as usize,MAX as usize,0,er.used,er.written,ar.written);\n',
             ' var i:usize=0;while i<16&&i<out.len{out[i]=0xcc;i+=1;}\n'
             ' return publish(r,OK,ASSEMBLE,0,MAX as usize,MAX as usize,0,er.used,er.written,16);\n',
             good, 'elf-validate|call-entry|return-value|status'),
            # Treat unsupported emit as success without assembling.
            ('bad-unsupported-as-ok',
             ' if emit!=OK{\n'
             '  // Emit failed: never call the assembler; keep ELF capacity untouched.\n'
             '  return publish(r,er.status,er.stage,er.code,er.unit,er.node,er.detail,er.used,0,0);\n'
             ' }\n',
             ' if emit!=OK{\n'
             '  return publish(r,OK,ASSEMBLE,0,MAX as usize,MAX as usize,0,er.used,0,0);\n'
             ' }\n',
             [self.case('unsupported-global', UNSUPPORTED_SRC, status=UNSUPPORTED,
                        result=dict(status=UNSUPPORTED, stage=LOWER, text=0, written=0))],
             'status'),
        ]
        for name, old, new, cases, reason in controls:
            for mode, exe in self.bad_build(name, old, new).items():
                with self.assertRaisesRegex(AssertionError, reason):
                    self.run_cases(exe, cases, name + '-' + mode, preflight=False)
            self.records.append(dict(test=name, compiled=True, native_executed=True, modes=2,
                                     rejected_by=reason))


if __name__ == '__main__':
    unittest.main()
