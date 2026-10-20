"""Actual Dong whole SysV forwarding function (C50): exact text, ELF64/COFF assembly, real call chain bridge -> wrapper -> callee."""
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

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags as _nasm_flags


def nasm_flags(nasm):
    """Shared -Wall -Werror flags; NASM 3.x lists its warnings only under "-h -w", so the shared probe misses
    reloc-rel-dword and ordinary RIP-relative .text -> .rodata references would fail. Every other warning stays an error."""
    flags=list(_nasm_flags(nasm))
    if '-w-reloc-rel-dword' not in flags:
        flags.append('-w-reloc-rel-dword')
    return flags


SOURCE=ROOT/'lang/bootstrap/nasm_u64_forward_function.dg'
DOC=ROOT/'lang/bootstrap/nasm_u64_forward_function.md'
# Integrated components and their whole read-only import closure (nothing else from lang is staged).
DEPENDENCIES=[ROOT/'lang/bootstrap'/(n+'.dg')for n in (
    'nasm_symbol',                                                          # CR3
    'nasm_function_frame','decimal_integer',                                # CR11, CR4
    'nasm_sysv_incoming_args','sysv_integer_args','nasm_memory_operand',    # C37, C8, CR8
    'nasm_sysv_direct_invoke','nasm_sysv_call_args','nasm_direct_call',     # C41, C34, C25
    'nasm_sysv_capture_return','sysv_return_plan',                          # C40, C14
    'nasm_sysv_function_exit','nasm_sysv_return_values')]                   # C42, C39
OK,INVALID,CAPACITY=0,1,2
U64=2**64-1
H,L=0x8000000000000000,0x7fffffffffffffff
PREFLIGHTS=34
REGS=['rdi','rsi','rdx','rcx','r8','r9']
WRAPPER='''module probe.forward_export;
import bootstrap.nasm_u64_forward_function as f;
export("dong_forward_emit") pub unsafe fn emit(m:*const u8,mn:usize,i:*const u8,inn:usize,cm:*const u8,cmn:usize,ci:*const u8,cin:usize,
 incoming:usize,map:*const usize,an:usize,out:*u8,no:usize,written:*usize)u64{unsafe{
 return f.emit(slice_from_raw_parts(m,mn),slice_from_raw_parts(i,inn),slice_from_raw_parts(cm,cmn),slice_from_raw_parts(ci,cin),
  incoming,slice_from_raw_parts(map,an),slice_from_raw_parts(out,no),written);
}}
'''
HARNESS=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#else
#include <sys/mman.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef const uint8_t*N;
extern uint64_t ABI dong_forward_emit(N,uint64_t,N,uint64_t,N,uint64_t,N,uint64_t,uint64_t,const uint64_t*,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static uint8_t*ro_alloc(uint64_t n){
#ifdef _WIN32
 return VirtualAlloc(NULL,n,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*p=mmap(NULL,n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return p==MAP_FAILED?NULL:p;
#endif
}
static int ro_protect(void*p,uint64_t n){
#ifdef _WIN32
 DWORD old;return VirtualProtect(p,n,PAGE_READONLY,&old)!=0;
#else
 return mprotect(p,n,PROT_READ)==0;
#endif
}
static void ro_free(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;VirtualFree(p,0,MEM_RELEASE);
#else
 munmap(p,n);
#endif
}
#define FAKE(x) ((N)(uintptr_t)(x))
/* Descriptor/alias preflights. Every other field is legal (four distinct names, map [0,0] or six zeros, two incoming,
   out 2048 bytes, aligned written) so only the target check can reject it. Failures are reported, then exit 93. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[4096],saved[4096];const unsigned total=34;unsigned failed=0;
 uint8_t*m=arena+64,*it=arena+192,*cm=arena+320,*ci=arena+448,*o=arena+1024;
 uint64_t*map=(uint64_t*)(arena+576),*w=(uint64_t*)(arena+3584);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memset(m,'a',64);memset(it,'b',64);memset(cm,'c',64);memset(ci,'d',64);memset(map,0,48);
  memcpy(saved,arena,sizeof(arena));
  N pm=m,pi=it,pcm=cm,pci=ci;uint64_t lm=4,li=4,lcm=4,lci=4,ln=2,lo=2048;const uint64_t*pmap=map;uint8_t*po=o;uint64_t*pw=w;
  switch(i){
   case 0:pw=NULL;break;                                         /* written NULL */
   case 1:pw=(uint64_t*)(arena+3585);break;                      /* written odd */
   case 2:pw=(uint64_t*)(uintptr_t)(UINT64_MAX-7);po=NULL;lo=0;break;   /* written end overflow, legal empty out */
   case 3:po=(uint8_t*)(uintptr_t)(UINT64_MAX-1023);break;       /* out end overflow */
   case 4:po=NULL;break;                                         /* NULL non-empty out */
   case 5:pm=NULL;break;case 6:pi=NULL;break;case 7:pcm=NULL;break;case 8:pci=NULL;break;   /* NULL non-empty names */
   case 9:pm=FAKE(UINT64_MAX-3);lm=8;break;                      /* name end overflows */
   case 10:pi=FAKE(UINT64_MAX-1);break;
   case 11:pcm=FAKE(UINT64_MAX-2);break;
   case 12:pci=FAKE(UINT64_MAX);break;
   case 13:pmap=NULL;break;                                      /* NULL non-empty map */
   case 14:pmap=(const uint64_t*)(arena+580);break;              /* misaligned map */
   case 15:pmap=(const uint64_t*)(uintptr_t)(UINT64_MAX-15);ln=4;break;  /* map end overflow */
   case 16:ln=(uint64_t)1<<61;break;                             /* map length * 8 overflows */
   case 17:pw=(uint64_t*)o;break;                                /* written on out prefix */
   case 18:pw=(uint64_t*)(o+2040);break;                         /* written in out's unused tail */
   case 19:lm=64;pw=(uint64_t*)m;break;case 20:lm=64;pw=(uint64_t*)(m+56);break;      /* written on/in each whole name */
   case 21:li=64;pw=(uint64_t*)it;break;case 22:li=64;pw=(uint64_t*)(it+56);break;
   case 23:lcm=64;pw=(uint64_t*)cm;break;case 24:lcm=64;pw=(uint64_t*)(cm+56);break;
   case 25:lci=64;pw=(uint64_t*)ci;break;case 26:lci=64;pw=(uint64_t*)(ci+56);break;
   case 27:ln=6;pw=map;break;case 28:ln=6;pw=map+5;break;        /* written on/in the whole map */
   case 29:lm=64;po=m+63;lo=8;break;case 30:li=64;po=it+63;lo=8;break;                 /* out over each name's last byte */
   case 31:lcm=64;po=cm+63;lo=8;break;case 32:lci=64;po=ci+63;lo=8;break;
   default:ln=6;po=(uint8_t*)map+47;lo=8;break;                  /* out over the map's last byte */
  }
  uint64_t s=dong_forward_emit(pm,lm,pi,li,pcm,lcm,pci,lci,2,pmap,ln,po,lo,pw);
  int same=!memcmp(saved,arena,sizeof(arena));
  if(s!=1||!same){fprintf(stderr,"invalid preflight %u status %u unchanged %d\n",i,(unsigned)s,same);failed++;}
 }
 if(failed)exit(93);
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  /* pool, (offset,length) for module/item/callee module/callee item/map (map length in entries), flags, incoming, capacity */
  uint64_t h[14];read_exact(h,sizeof(h));uint64_t pool=h[0],flags=h[11],incoming=h[12],cap=h[13];
  if(pool>1024||cap>8192)exit(94);
  uint8_t*in=malloc(pool+96),*copy=malloc(pool+1),*out=malloc(cap+64);static _Alignas(8) uint64_t meta[3];
  if(!in||!copy||!out||((uintptr_t)in&15))exit(95);
  memset(in,0xa5,pool+96);read_exact(in+32,pool);memcpy(copy,in+32,pool);
  uint8_t*base=in+32,*page=NULL;uint64_t pages=4096*2,protected_ok=1;
  if(flags&2){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,pool);protected_ok=ro_protect(page,pages);base=page;}
  const uint64_t*map=(flags&1)?NULL:(const uint64_t*)(base+h[9]);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=dong_forward_emit(base+h[1],h[2],base+h[3],h[4],base+h[5],h[6],base+h[7],h[8],incoming,map,h[10],cap?out+32:NULL,cap,written);
  uint64_t valid=protected_ok&&!memcmp(copy,base,pool)&&((flags&2)||(filled(in,32)&&filled(in+32+pool,32)))&&
    filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(s)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[4]={s,valid,s?0:*written,protected_ok};write_exact(response,32);write_exact(out+32,response[2]);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(out);
 }return 0;
}
'''
NATIVE_MAIN=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef void ABI (*stub)(uint64_t*);
%DECLS%
static const stub table[]={%TABLE%};
extern uint64_t callee_align,callee_id,callee_arity,callee_calls,callee_args[6];
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 static uint64_t io[STATE+2];
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  memset(io,0,sizeof(io));io[0]=io[STATE+1]=0xa5a5a5a5a5a5a5a5ull;
  callee_align=callee_id=callee_arity=UINT64_MAX;callee_calls=0;memset(callee_args,0xee,sizeof(callee_args));
  table[i](io+1);
  if(io[0]!=0xa5a5a5a5a5a5a5a5ull||io[STATE+1]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  static uint64_t record[10];record[0]=callee_calls;record[1]=callee_id;record[2]=callee_align;record[3]=callee_arity;
  memcpy(record+4,callee_args,sizeof(callee_args));
  if(fwrite(io+1,8,STATE,stdout)!=STATE||fwrite(record,8,10,stdout)!=10)exit(92);
 }return 0;
}
'''
CALLEE=r'''
#include <stdint.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
/* Independent callee: every assembly alias records its entry rsp%16, its vector id and its arity, then jumps here. */
uint64_t ABI callee_target(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
uint64_t callee_align,callee_id,callee_arity,callee_calls,callee_args[6];
uint64_t ABI callee_target(uint64_t a0,uint64_t a1,uint64_t a2,uint64_t a3,uint64_t a4,uint64_t a5){
 uint64_t a[6]={a0,a1,a2,a3,a4,a5};callee_calls++;memcpy(callee_args,a,sizeof(a));
 uint64_t h=0xc0ffee0000000000ull|callee_arity;
 for(uint64_t j=0;j<callee_arity&&j<6;j++)h=(h*0x100000001b3ull)^(a[j]+(j+1)*0x9e3779b97f4a7c15ull);
  return h|0x8000000000000000ull;
}
'''
# State layout (qwords): 0 rax after; 1 rsp before call; 2 rsp after; 3 rbx before; 4 rbx after; 5 rbp after;
# 6..9 r12..r15 after; 10 caller stack canary after; 11 rsp%16 just before the call.
RAX,RSP_BEFORE,RSP_AFTER,RBX_BEFORE,RBX_AFTER,RBP_AFTER,R12_AFTER,CANARY_AFTER,ALIGN,STATE=0,1,2,3,4,5,6,10,11,12
# Known values planted in every callee-saved register (rbx included: it is under test, never the observation pointer).
CALLER={'rbx':0x0bbb0bbb0bbb0bbb,'rbp':0x0b0b0b0b0b0b0b0b,'r12':0x1212121212121212,'r13':0x1313131313131313,'r14':0x1414141414141414,'r15':0x1515151515151515}
CANARY=0x5ca1ab1e0ddba11c
JUNK=0xdead00000000be00


def symbol(module,item):
    """Independent CR3 expectation: __dong_m<hex module>_n<hex item>, two lowercase digits per byte."""
    return '__dong_m'+module.hex()+'_n'+item.hex()


def frame_of(n):
    return (8*(n+1)+15)//16*16


def expected_text(module,item,callee_module,callee_item,n,mapping):
    """Independent whole-function text model."""
    frame,result=frame_of(n),8*(n+1)
    lines=[symbol(module,item)+':','push rbp','mov rbp, rsp','sub rsp, %d'%frame]
    lines+=['mov qword [rbp - %d], %s'%(8*(i+1),REGS[i])for i in range(n)]
    lines+=['mov %s, qword [rbp - %d]'%(REGS[j],8*(a+1))for j,a in enumerate(mapping)]
    lines+=['call '+symbol(callee_module,callee_item),'mov qword [rbp - %d], rax'%result]
    lines+=['mov rax, qword [rbp - %d]'%result,'add rsp, %d'%frame,'pop rbp','ret']
    return ''.join(l+'\n'for l in lines).encode()


def callee_hash(args):
    """Independent model of the callee's position-weighted hash (wrapping u64, top bit forced)."""
    h=0xc0ffee0000000000|len(args)
    for j,x in enumerate(args):h=((h*0x100000001b3)&U64)^((x+(j+1)*0x9e3779b97f4a7c15)&U64)
    return h|H


VALUES=[U64,0,H,L,1,0x0123456789abcdef,0xfedcba9876543210,0x8000000000000001]
# (incoming_count, argument_map): 0/1/6 incoming, empty/1/6 maps, reverse, duplicates, drops, 6->1, 1->6.
SHAPES=[(0,[]),(1,[]),(1,[0]),(1,[0]*6),(6,[]),(6,[0,1,2,3,4,5]),(6,[5,4,3,2,1,0]),(6,[3]),(6,[2,2,5,5,0,0]),
        (6,[1,0]),(3,[2,0,1]),(2,[1,0,1,0,1]),(4,[3,3,3,3,3,3]),(5,[4,0,2]),(2,[0,1]),(6,[5])]


def vectors():
    """(module, item, callee_module, callee_item, n, map, incoming values); every symbol in the file is distinct."""
    out=[]
    for k,(n,mapping) in enumerate(SHAPES):
        if k==0:names=(b'W',b'x',b'C',b'y')                                         # 1-byte names
        elif k==5:names=(b'M'*64,bytes(range(64)),b'N'*64,bytes(range(64,128)))       # 64-byte names
        else:names=(b'wrap',bytes([0x41+k]),b'callee/'+bytes([0x41+k]),b'f\x00'+bytes([k]))
        out.append((*names,n,mapping,[VALUES[(k+i)%8]^(k<<4 if i%2 else 0)for i in range(n)]))
    return out


VECTORS=vectors()


def layout(names,mapping):
    """Pool bytes and (offset,length) of each name and of the map (8-aligned), with gaps so nothing overlaps."""
    pool=bytearray();spans=[]
    for name in names:
        spans.append((len(pool),len(name)));pool+=name+b'\xa5'*(8-len(name)%8+8)
    spans.append((len(pool),len(mapping)));pool+=b''.join(struct.pack('<Q',a)for a in mapping)+b'\xa5'*8
    return bytes(pool),spans


class NasmU64ForwardFunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-nasm-u64-forward-function'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.records=[]
        cls.inputs=cls.digests()
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.executables=cls.build_all('good',SOURCE.read_text(encoding='utf-8'))

    @staticmethod
    def digests():
        return {p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,DOC,*DEPENDENCIES,Path(__file__)]}

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=180)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build_all(cls,name,text):
        """Stage only this component and its integrated read-only closure, then build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_u64_forward_function.dg').write_text(text,encoding='utf-8')
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        (root/'probe/forward_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/forward_export.dg',roots=[root],mode=mode)
            asm=cls.work/(tag+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
            obj=cls.work/(tag+'.o');exe=cls.work/(tag+('.exe'if os.name=='nt'else''))
            for fmt in ('elf64','win64'):
                output=obj if fmt==cls.native else cls.work/(tag+'.'+fmt+'.o')
                cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',output,asm],tag+'-'+fmt)
            cls.command([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',cls.work/'probe.c',obj,'-o',exe],tag+'-link')
            result[mode]=exe
        return result

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        after=cls.digests()
        files={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in cls.work.rglob('*')if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,source_sha256_after=after,
            stable=after==cls.inputs,artifact_sha256=files,records=cls.records,integrated=False,OS_VM_built=False),indent=2)+'\n')
        if after!=cls.inputs:raise AssertionError(('input/dependency SHA256 changed during the run',cls.inputs,after))

    def emit(self,exe,cases,label):
        """cases: (pool, spans[5], flags, incoming, cap, status); flags bit0 = NULL map, bit1 = read-only page."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for pool,spans,flags,n,cap,_ in cases:
            payload.extend(struct.pack('<14Q',len(pool),*[v for s in spans for v in s],flags,n,cap));payload.extend(pool)
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],PREFLIGHTS)
        offset=8;texts=[]
        for index,case in enumerate(cases):
            got,guard,written,protected=struct.unpack_from('<4Q',run.stdout,offset);offset+=32
            text=run.stdout[offset:offset+written];offset+=written
            if case[2]&2:self.assertEqual(protected,1,(label,index,'read-only protection call failed'))
            self.assertEqual(guard,1,(label,index,'guard/atomicity',case[1:]))
            self.assertEqual(got,case[5],(label,index,'status',case[1:]))
            texts.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return texts

    @staticmethod
    def case(names,mapping,n,cap,status,flags=0):
        pool,spans=layout(names,mapping);return (pool,spans,flags,n,cap,status)

    @staticmethod
    def resolve(case):
        """The actual bytes each pointer sees (names may overlap each other or the map)."""
        pool,spans=case[0],case[1]
        names=[pool[o:o+n]for o,n in spans[:4]];o,m=spans[4]
        return names,[struct.unpack_from('<Q',pool,o+8*j)[0]for j in range(m)]

    def generate(self,exe,vectors,label):
        cases=[self.case(v[:4],v[5],v[4],4096,OK,1 if not v[5] else 0)for v in vectors]
        texts=self.emit(exe,cases,label)
        for v,text in zip(vectors,texts):self.assertEqual(text,expected_text(*v[:6]),(label,v[4:6]))
        return texts

    def native_run(self,texts,vectors,label):
        """All generated functions go in one file. Each hand-written SysV stub saves the host's callee-saved registers, then
        stores the observation-area address and a host stack anchor in independent static memory (no register under test
        holds either). It plants known values in every callee-saved register (rbx included), the arguments (junk in unused
        argument registers) and a stack canary, and really calls the generated function. After the return it first parks
        RAX in static memory, reloads the observation address from static memory, records RAX, RSP and every callee-saved
        register exactly as returned, reads the canary through the saved anchor, then restores RSP from the anchor and the
        host's registers from its own pushes before returning. All assertions run afterwards in Python."""
        stub=['bits 64','extern callee_target','extern callee_align','extern callee_id','extern callee_arity','section .data','align 8','observation: dq 0','host_anchor: dq 0','parked_rax: dq 0','section .text']
        for k,(m,it,cm,ci,n,mapping,vals) in enumerate(vectors):
            stub+=['global v%d'%k,'v%d:'%k,'push rbx','push rbp','push r12','push r13','push r14','push r15','sub rsp, 8']
            stub+=['mov [rel observation], rdi','mov [rel host_anchor], rsp','mov r11, rdi']
            stub+=['mov %s, 0x%x'%(r,v)for r,v in CALLER.items()]
            stub+=['mov rax, 0x%x'%CANARY,'mov [rsp], rax','mov [r11+%d], rsp'%(8*RSP_BEFORE),
                   'mov rax, rsp','and rax, 15','mov [r11+%d], rax'%(8*ALIGN),'mov rax, 0x%x'%CALLER['rbx'],'mov [r11+%d], rax'%(8*RBX_BEFORE)]
            stub+=['mov %s, 0x%x'%(REGS[i],vals[i]if i<n else JUNK|i)for i in range(6)]+['mov rax, 0x%x'%JUNK,'call '+symbol(m,it)]
            stub+=['mov [rel parked_rax], rax','mov rax, [rel observation]',
                   'mov [rax+%d], rsp'%(8*RSP_AFTER),'mov [rax+%d], rbx'%(8*RBX_AFTER),'mov [rax+%d], rbp'%(8*RBP_AFTER)]
            stub+=['mov [rax+%d], r%d'%(8*(R12_AFTER+j),12+j)for j in range(4)]
            stub+=['mov rcx, [rel parked_rax]','mov [rax+%d], rcx'%(8*RAX),
                   'mov rcx, [rel host_anchor]','mov rcx, [rcx]','mov [rax+%d], rcx'%(8*CANARY_AFTER)]
            stub+=['mov rsp, [rel host_anchor]','add rsp, 8','pop r15','pop r14','pop r13','pop r12','pop rbp','pop rbx','ret']
            stub+=[symbol(cm,ci)+':','mov r11, rsp','and r11, 15','mov [rel callee_align], r11','mov r11, %d'%k,'mov [rel callee_id], r11',
                   'mov r11, %d'%len(mapping),'mov [rel callee_arity], r11','jmp callee_target']
        for text in texts:stub+=text.decode('ascii').rstrip('\n').split('\n')
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','#define STATE %d\n'%STATE+'\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(vectors))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(vectors))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        (self.work/'callee.c').write_text(CALLEE,encoding='utf-8')
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/'callee.c',self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],label+'-native-link')
        run=subprocess.run([str(exe)],capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        size=8*(STATE+10);self.assertEqual(len(run.stdout),size*len(vectors))
        for k,(m,it,cm,ci,n,mapping,vals) in enumerate(vectors):
            got=struct.unpack_from('<%dQ'%(STATE+10),run.stdout,size*k);calls,ident,align,arity=got[STATE:STATE+4];args=list(got[STATE+4:STATE+10])
            want=[vals[a]for a in mapping]
            self.assertEqual(got[ALIGN],0,(label,k,'caller rsp aligned before call'))
            self.assertEqual((calls,ident,arity),(1,k,len(mapping)),(label,k,'native callee reached once'))
            self.assertEqual(align,8,(label,k,'native callee entry rsp%16'))
            self.assertEqual(args[:len(mapping)],want,(label,k,'native args',n,mapping))
            self.assertEqual(got[RAX],callee_hash(want),(label,k,'native rax',n,mapping))
            self.assertEqual(got[RSP_AFTER],got[RSP_BEFORE],(label,k,'native rsp balanced across call/ret'))
            self.assertEqual(got[RBX_BEFORE],CALLER['rbx'],(label,k,'planted rbx recorded'))
            self.assertEqual(got[RBX_AFTER],CALLER['rbx'],(label,k,'native rbx preserved'))
            self.assertEqual((got[RBP_AFTER],*got[R12_AFTER:R12_AFTER+4]),tuple(v for r,v in CALLER.items()if r!='rbx'),(label,k,'native rbp/r12..r15 preserved'))
            self.assertEqual(got[CANARY_AFTER],CANARY,(label,k,'caller stack canary'))

    def test_exact_text_capacity_invalid_and_read_only_inputs(self):
        cases=[]
        for k,v in enumerate(VECTORS):
            size=len(expected_text(*v[:6]));nul=1 if not v[5] else 0
            cases+=[self.case(v[:4],v[5],v[4],size,OK,nul|(2 if k%3==0 else 0)),self.case(v[:4],v[5],v[4],size+9,OK),
                    self.case(v[:4],v[5],v[4],size-1,CAPACITY,2 if k%2 else 0),self.case(v[:4],v[5],v[4],0,CAPACITY)]
        big=(b'\xff'*64,b'\x00'*64,b'\x80'*64,b'\x7f'*64);bigmap=[5,4,3,2,1,0];size=len(expected_text(*big,6,bigmap))
        self.assertLessEqual(size,1356)
        cases+=[self.case(big,bigmap,6,size,OK,2),self.case(big,bigmap,6,size-1,CAPACITY),self.case(big,bigmap,6,size+100,OK)]
        # Overlapping inputs: names inside one another and the map bytes shared with the callee item; also read-only.
        pool=struct.pack('<2Q',1,0)+b'modulename'+b'\xa5'*6
        cases+=[(pool,[(16,6),(18,4),(19,7),(0,9),(0,2)],0,2,4096,OK),(pool,[(16,6),(18,4),(19,7),(0,9),(0,2)],2,2,4096,OK),
                (pool,[(16,3),(16,10),(17,3),(16,10),(0,1)],2,3,4096,OK)]
        # Self call: identical bytes (separate copies and the very same pointers) are INVALID; one differing name is OK.
        cases+=[self.case((b'm',b'f',b'm',b'f'),[0],1,4096,INVALID),self.case((b'm',b'f',b'm',b'f'),[0],1,0,INVALID),
                (b'mf'+b'\xa5'*6,[(0,1),(1,1),(0,1),(1,1),(8,0)],1,0,4096,INVALID),
                self.case((b'm',b'f',b'm',b'g'),[0],1,4096,OK),self.case((b'm',b'f',b'n',b'f'),[0],1,4096,OK)]
        legal=dict(names=[b'mod',b'fn',b'callee',b'g'],mapping=[1,0],n=2)
        def bad(**kw):
            v={k:(list(x)if isinstance(x,list)else x)for k,x in legal.items()};v.update(kw);return v
        bads=[bad(names=[b'',b'fn',b'callee',b'g']),bad(names=[b'mod',b'',b'callee',b'g']),bad(names=[b'mod',b'fn',b'',b'g']),
              bad(names=[b'mod',b'fn',b'callee',b'']),bad(names=[b'm'*65,b'fn',b'callee',b'g']),bad(names=[b'mod',b'f'*65,b'callee',b'g']),
              bad(names=[b'mod',b'fn',b'c'*65,b'g']),bad(names=[b'mod',b'fn',b'callee',b'g'*65]),
              bad(n=7,mapping=[0]),bad(n=6,mapping=[0]*7),bad(mapping=[2]),bad(mapping=[0,U64]),bad(n=0,mapping=[0]),bad(n=U64,mapping=[])]
        for b in bads:cases+=[self.case(b['names'],b['mapping'],b['n'],4096,INVALID),self.case(b['names'],b['mapping'],b['n'],0,INVALID,2)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for c,text in zip(cases,texts):
                if c[5]==OK:
                    names,mapping=self.resolve(c)
                    self.assertEqual(text,expected_text(*names,c[3],mapping),(mode,c[1:5]))
                    self.assertTrue(all(b==10 or 32<=b<127 for b in text)and b'\n\n'not in text,(mode,'ASCII/LF'))
                    for word in (b'section',b'global',b'bits',b'extern'):self.assertNotIn(word,text,(mode,word))
        self.records.append(dict(test='exact-text-capacity-invalid-readonly',cases=len(cases),preflights_per_native=PREFLIGHTS,longest_bytes=size,modes=2,passed=True))

    def test_native_call_chain(self):
        self.assertLessEqual(len(VECTORS),24)
        shapes=[(v[4],v[5])for v in VECTORS]
        self.assertTrue({0,1,6}<={n for n,_ in shapes}and{0,1,6}<={len(m)for _,m in shapes})
        self.assertIn((6,[5,4,3,2,1,0]),shapes);self.assertIn((6,[3]),shapes);self.assertIn((1,[0]*6),shapes)
        self.assertTrue(any(len(set(m))<len(m)for _,m in shapes))                                  # duplicates
        self.assertTrue(any(n and set(range(n))-set(m)for n,m in shapes))                          # dropped arguments
        self.assertTrue({U64,0,H,L}<={x for v in VECTORS for x in v[6]})
        self.assertTrue(any(len(v[0])==1 for v in VECTORS)and any(len(v[0])==64 and len(v[3])==64 for v in VECTORS))
        syms=[symbol(*v[:2])for v in VECTORS]+[symbol(*v[2:4])for v in VECTORS];self.assertEqual(len(syms),len(set(syms)))
        self.assertTrue(all(callee_hash([v[6][a]for a in v[5]])>>63 for v in VECTORS))         # high bit set in every result
        for mode,exe in self.executables.items():
            self.native_run(self.generate(exe,VECTORS,'vectors-'+mode),VECTORS,'native-'+mode)
        self.records.append(dict(test='native-call-chain',vectors_per_mode=len(VECTORS),functions_per_file=len(VECTORS),modes=2,formats=['elf64','win64'],passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        fill='j=0;while j<argument_map.len{sources[j]=8*(argument_map[j]+1);j+=1;}'
        load='ex.emit(U64_KIND,frame,0,result,0,'
        for s in (fill,load):self.assertEqual(source.count(s),1,s)
        swap=fill+'\n if argument_map.len>=2{let t=sources[0];sources[0]=sources[1];sources[1]=t;}'          # legal-looking reorder
        swapped=[v for v in VECTORS if len(v[5])>=2 and v[5][0]!=v[5][1]]
        argslot=[v for v in VECTORS if v[4]>=1]                                                          # slot 8 is an argument
        for name,text,vectors,reason in [('bad-map-swapped',source.replace(fill,swap,1),swapped,'native args'),
                                         ('bad-return-reads-argument-slot',source.replace(load,'ex.emit(U64_KIND,frame,0,8,0,',1),argslot,'native rax')]:
            self.assertGreaterEqual(len(vectors),4,name)
            for mode,exe in self.executables.items():                                       # same inputs pass first
                self.native_run(self.generate(exe,vectors,name+'-good-'+mode),vectors,name+'-good-'+mode)
            for mode,exe in self.build_all(name,text).items():
                cases=[self.case(v[:4],v[5],v[4],4096,OK,1 if not v[5] else 0)for v in vectors]
                texts=self.emit(exe,cases,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,reason):self.native_run(texts,vectors,name+'-'+mode)
            self.records.append(dict(test=name,vectors=len(vectors),compiled=True,linked=True,native_executed=True,modes=2,rejected_by=reason))
        # Callee-saved RBX not preserved: "add rbx, 8" right before the wrapper's ret. The full real call chain still runs
        # (bridge -> wrapper -> callee alias -> C target, callee records intact); RAX, RSP, args are right, only RBX is wrong.
        exit_line=' if ex.emit(U64_KIND,frame,0,result,0,slice_from_raw_parts(&buffer[at],EXIT),&n)!=ex.OK{return INVALID;}\n at+=n;\n'
        self.assertEqual(source.count(exit_line),1)
        inject='at-=4;put(text,&at,"add rbx, 8\\nret\\n");\n'
        tail=b'pop rbp\nadd rbx, 8\nret\n'
        clobber=source.replace(exit_line,exit_line+inject,1)
        for mode,exe in self.executables.items():
            self.native_run(self.generate(exe,VECTORS,'bad-rbx-good-'+mode),VECTORS,'bad-rbx-good-'+mode)
        for mode,exe in self.build_all('bad-rbx-clobbered',clobber).items():
            cases=[self.case(v[:4],v[5],v[4],4096,OK,1 if not v[5] else 0)for v in VECTORS]
            texts=self.emit(exe,cases,'bad-rbx-'+mode)
            self.assertTrue(all(t.endswith(tail)for t in texts),(mode,'injected before ret'))
            with self.assertRaisesRegex(AssertionError,'native rbx preserved'):self.native_run(texts,VECTORS,'bad-rbx-'+mode)
        self.records.append(dict(test='bad-rbx-clobbered',vectors=len(VECTORS),compiled=True,linked=True,native_executed=True,modes=2,
                                 rejected_by='native rbx preserved (callee record, rax and rsp assertions passed first)'))
        old='if at>on{return CAPACITY;}';self.assertEqual(source.count(old),1)
        new='if at>on{var k:usize=0;while k<on{out[k]=buffer[k];k+=1;}return CAPACITY;}'    # publishes the function header early
        v=VECTORS[5];size=len(expected_text(*v[:6]));case=[self.case(v[:4],v[5],v[4],size-1,CAPACITY)]
        for mode,exe in self.executables.items():self.emit(exe,case,'bad-early-header-good-'+mode)
        for mode,exe in self.build_all('bad-early-header',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,case,'bad-early-header-'+mode)
        self.records.append(dict(test='bad-early-header',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))

    def test_input_alias_preflights_are_reachable(self):
        """Preflight sensitivity: a real Dong without the name/map alias checks fails exactly preflights 19..33."""
        source=SOURCE.read_text(encoding='utf-8')
        start=source.index(' if overlap(wp,8,mp,mn)');end=source.index('{return INVALID;}\n',start)+len('{return INVALID;}\n')
        old=source[start:end];self.assertIn('overlap(op,on,ap,an)',old);self.assertEqual(source.count(old),1)
        for mode,exe in self.executables.items():self.emit(exe,[],'alias-good-'+mode)
        for mode,exe in self.build_all('bad-no-input-alias',source.replace(old,'',1)).items():
            run=subprocess.run([str(exe)],input=struct.pack('<Q',0),capture_output=True,timeout=60)
            err=run.stderr.decode('ascii','replace');(self.work/('bad-no-input-alias-'+mode+'.stderr')).write_text(err,encoding='ascii')
            self.assertEqual(run.returncode,93,(mode,err))
            failed=[int(line.split()[2])for line in err.splitlines()if line.startswith('invalid preflight ')]
            self.assertEqual(failed,list(range(19,34)),(mode,err))
        self.records.append(dict(test='bad-no-input-alias',compiled=True,native_executed=True,modes=2,rejected_by='preflights 19..33'))


if __name__=='__main__':unittest.main()
