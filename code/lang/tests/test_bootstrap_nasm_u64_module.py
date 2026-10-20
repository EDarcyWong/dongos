"""Actual Dong multi-function NASM module (C52): exact text, ELF64/COFF assembly of the same text, link + real calls to every export."""
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


SOURCE=ROOT/'lang/bootstrap/nasm_u64_module.dg'
DOC=ROOT/'lang/bootstrap/nasm_u64_module.md'
C48=ROOT/'lang/bootstrap/nasm_u64_function.dg'
# Integrated C48 and its whole read-only import closure (CR3 is nasm_symbol); nothing else from lang is staged.
DEPENDENCIES=[C48]+[ROOT/'lang/bootstrap'/(n+'.dg')for n in (
    'nasm_symbol','decimal_integer','nasm_function_frame','nasm_sysv_incoming_args','sysv_integer_args','nasm_memory_operand',
    'nasm_integer_memory_load','nasm_integer_memory_store','nasm_integer_binary','nasm_sysv_function_exit',
    'nasm_sysv_return_values','sysv_return_plan')]
OK,INVALID,CAPACITY,WORKSPACE=0,1,2,3
U64=2**64-1
H,L=0x8000000000000000,0x7fffffffffffffff
PREFLIGHTS=36
CONST,COPY,ADD,SUB,AND,OR,XOR,IMUL=range(8)
MNEMONIC={ADD:'add',SUB:'sub',AND:'and',OR:'or',XOR:'xor',IMUL:'imul'}
REGS=['rdi','rsi','rdx','rcx','r8','r9']
HEADER='bits 64\nsection .text\n'
PER=274+6591
WRAPPER='''module probe.c52_export;
import bootstrap.nasm_u64_module as m;
export("dong_c52_emit") pub unsafe fn emit(functions:*const m.Function,n:usize,work:*u8,wn:usize,out:*u8,on:usize,written:*usize)u64{unsafe{
 return m.emit(slice_from_raw_parts(functions,n),slice_from_raw_parts(work,wn),slice_from_raw_parts(out,on),written);
}}
'''
HARNESS=r'''
#ifndef _WIN32
#define _GNU_SOURCE
#endif
#include <stdint.h>
#include <errno.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#else
#include <sys/mman.h>
#include <signal.h>
#include <unistd.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef const uint8_t*N;
typedef struct{uint64_t op,dst,l,r,imm;}Ins;
typedef struct{N m;uint64_t mn;N i;uint64_t in;uint64_t p;uint64_t slots;const Ins*x;uint64_t xn;uint64_t rs;}Fn;
extern uint64_t ABI dong_c52_emit(const Fn*,uint64_t,uint8_t*,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
#define FAKE(x) ((const void*)(uintptr_t)(x))
/* Read observation: every name/IR body lives alone in its own page that is armed so that the first read is
   recorded and then allowed. Windows: PAGE_GUARD (the system clears the flag on the first access; a vectored handler lets
   the access complete; afterwards VirtualQuery says whether the flag is gone). Linux: PROT_NONE + a SIGSEGV handler.
   After the first access the page is READONLY, never writable. An unrelated/repeated fault or a failed protection call
   terminates with an error, which Python rejects; a crash/timeout cannot count as a successful observation. */
static uint8_t*g_base;static uint64_t g_pages,g_page_size;
static uint64_t guard_page_size(void){
#ifdef _WIN32
 SYSTEM_INFO info;GetSystemInfo(&info);return info.dwPageSize;
#else
 long n=sysconf(_SC_PAGESIZE);if(n<4096)exit(95);return (uint64_t)n;
#endif
}
#ifdef _WIN32
static LONG WINAPI guard_veh(PEXCEPTION_POINTERS p){
 EXCEPTION_RECORD*r=p->ExceptionRecord;uintptr_t a=r->NumberParameters>=2?r->ExceptionInformation[1]:0,base=(uintptr_t)g_base;
 return r->ExceptionCode==STATUS_GUARD_PAGE_VIOLATION&&a>=base&&a-base<g_pages*g_page_size?
  EXCEPTION_CONTINUE_EXECUTION:EXCEPTION_CONTINUE_SEARCH;
}
#else
static volatile sig_atomic_t g_touched[64];
static void guard_segv(int sig,siginfo_t*si,void*ctx){
 (void)ctx;int saved_errno=errno;uintptr_t a=(uintptr_t)si->si_addr,base=(uintptr_t)g_base;
 if(sig==SIGSEGV&&si->si_code==SEGV_ACCERR&&a>=base&&a-base<g_pages*g_page_size){
  uint64_t k=(a-base)/g_page_size;if(g_touched[k])_exit(98);g_touched[k]=1;
  if(mprotect(g_base+k*g_page_size,g_page_size,PROT_READ))_exit(98);
  errno=saved_errno;return;
 }
 _exit(98);
}
#endif
typedef struct{uint8_t*raw;uint8_t*p;uint64_t n;}Buf;
static Buf mk(uint64_t n){Buf b;b.n=n;b.raw=malloc(n+96);if(!b.raw||((uintptr_t)b.raw&15))exit(95);memset(b.raw,0xa5,n+96);b.p=b.raw+32;return b;}
static int gok(Buf b){return filled(b.raw,32)&&filled(b.p+b.n,64);}
static void rm(Buf b){free(b.raw);}
static void build_fn(Fn*f,const uint8_t*base,const uint64_t*d){
 f->m=d[1]?base+d[0]:NULL;f->mn=d[1];f->i=d[3]?base+d[2]:NULL;f->in=d[3];f->p=d[4];f->slots=d[5];
 f->x=d[7]?(const Ins*)(base+d[6]):NULL;f->xn=d[7];f->rs=d[8];
}
/* Descriptor/alias preflights on a one-function baseline (64-byte module and item names, one ADD). Every other field is
   legal, so only the target check can reject it; each must return INVALID with the whole arena unchanged. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[32768],base[32768],before[32768];const unsigned total=36;unsigned failed=0;
 memset(arena,0xa5,sizeof(arena));
 Fn*F=(Fn*)(arena+64);uint8_t*M=arena+256,*I=arena+384;Ins*X=(Ins*)(arena+512);
 uint8_t*W=arena+2048,*O=arena+10240;uint64_t*WR=(uint64_t*)(arena+18432);uint8_t*W2=arena+20480;
 memset(M,'m',64);memset(I,'f',64);X[0].op=2;X[0].dst=1;X[0].l=0;X[0].r=0;X[0].imm=0;
 F->m=M;F->mn=64;F->i=I;F->in=64;F->p=1;F->slots=2;F->x=X;F->xn=1;F->rs=1;
 if(dong_c52_emit(F,1,W,8192,O,8192,WR)!=0||*WR<30)exit(99);
 memset(W,0xa5,8192);memset(O,0xa5,8192);memset(WR,0xa5,8);memcpy(base,arena,sizeof(arena));
 for(unsigned i=0;i<total;i++){
  memcpy(arena,base,sizeof(arena));
  const Fn*pf=F;uint64_t nf=1;uint8_t*pw=W;uint64_t wn=8192;uint8_t*po=O;uint64_t on=8192;uint64_t*pwr=WR;
  switch(i){
   case 0:pwr=NULL;break;                                             /* written NULL */
   case 1:pwr=(uint64_t*)(arena+18433);break;                         /* written odd */
   case 2:pwr=(uint64_t*)(uintptr_t)(UINT64_MAX-7);po=NULL;on=0;break;/* written end overflow, legal empty out */
   case 3:pf=NULL;break;                                              /* functions NULL */
   case 4:pf=(const Fn*)(arena+65);break;                             /* functions odd */
   case 5:pf=FAKE(UINT64_MAX-71);break;                               /* functions end overflow */
   case 6:nf=0;break;case 7:nf=9;break;case 8:nf=UINT64_MAX/72+1;break;   /* count 0, 9, multiplication overflow */
   case 9:pw=NULL;break;case 10:pw=(uint8_t*)(uintptr_t)(UINT64_MAX-4095);break;   /* work NULL / end overflow */
   case 11:po=NULL;break;case 12:po=(uint8_t*)(uintptr_t)(UINT64_MAX-4095);break;  /* out NULL / end overflow */
   case 13:pwr=(uint64_t*)(W+64);break;                               /* written inside work */
   case 14:pwr=(uint64_t*)(O+8184);break;                             /* written in out's unused tail */
   case 15:po=arena+10048;break;                                      /* work overlaps out */
   case 16:pwr=(uint64_t*)(arena+72);break;                           /* functions array overlaps written */
   case 17:pw=arena+124;break;                                        /* functions array overlaps work */
   case 18:po=arena+124;pw=W2;break;                                  /* functions array overlaps out */
   case 19:F->m=NULL;break;                                           /* module NULL */
   case 20:F->m=FAKE(UINT64_MAX-31);break;                            /* module end overflow */
   case 21:F->i=NULL;break;case 22:F->i=FAKE(UINT64_MAX-31);break;    /* item NULL / end overflow */
   case 23:F->x=NULL;break;case 24:F->x=(const Ins*)(arena+513);break;case 25:F->x=FAKE(UINT64_MAX-39);break;   /* IR */
   case 26:F->xn=UINT64_MAX/40+1;break;                               /* IR count * 40 overflows */
   case 27:pwr=(uint64_t*)(M+56);break;case 28:pwr=(uint64_t*)(I+56);break;case 29:pwr=(uint64_t*)(arena+544);break;   /* written over names / IR */
   case 30:pw=M+63;break;case 31:pw=I+63;break;case 32:pw=arena+551;break;                                              /* work over names / IR last byte */
   case 33:po=M+63;pw=W2;break;case 34:po=I+63;pw=W2;break;case 35:po=arena+551;pw=W2;break;                            /* out over names / IR last byte */
  }
  memcpy(before,arena,sizeof(arena));                              /* the arena exactly as handed to the emitter */
  uint64_t s=dong_c52_emit(pf,nf,pw,wn,po,on,pwr);
  int same=!memcmp(before,arena,sizeof(arena));
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
  /* [nfun, pool_len, work_len, out_len, flags, 0 ...] + nfun*9 descriptors + pool. flags bit1: pool and table on a read-only page. */
  uint64_t h[16];read_exact(h,sizeof(h));
  if(h[0]==0xC52){                    /* GUARD: [0xC52, nfun, work_len, out_len, 0...] + nfun*9 {m_len,i_len,p,slots,x_count,rs,..} + bodies */
   uint64_t gn=h[1],gw=h[2],go=h[3];if(gn>8||gw>70000||go>70000)exit(94);
   uint64_t gd[8*9];read_exact(gd,gn*72);uint64_t pages=gn*3,ps=guard_page_size();
   uint8_t*G=ro_alloc(pages*ps);if(!G)exit(95);memset(G,0xa5,pages*ps);
   for(uint64_t k=0;k<gn;k++){
    if(gd[9*k]>4096||gd[9*k+1]>4096||gd[9*k+4]*40>4096)exit(94);
    read_exact(G+(3*k)*ps,gd[9*k]);read_exact(G+(3*k+1)*ps,gd[9*k+1]);read_exact(G+(3*k+2)*ps,gd[9*k+4]*40);
   }
   Buf GF=mk(gn*72),GF0=mk(gn*72),G0=mk(pages*ps),GW=mk(gw),GO=mk(go),GR=mk(8);Fn*ft=(Fn*)GF.p;
   for(uint64_t k=0;k<gn;k++){
    ft[k].m=gd[9*k]?G+(3*k)*ps:NULL;ft[k].mn=gd[9*k];ft[k].i=gd[9*k+1]?G+(3*k+1)*ps:NULL;ft[k].in=gd[9*k+1];
    ft[k].p=gd[9*k+2];ft[k].slots=gd[9*k+3];ft[k].x=gd[9*k+4]?(const Ins*)(G+(3*k+2)*ps):NULL;ft[k].xn=gd[9*k+4];ft[k].rs=gd[9*k+5];
   }
   uint8_t touched[64];memset(touched,0,sizeof(touched));
   memcpy(GF0.p,GF.p,gn*72);memcpy(G0.p,G,pages*ps);g_base=G;g_pages=pages;g_page_size=ps;
#ifdef _WIN32
   PVOID handler=AddVectoredExceptionHandler(1,guard_veh);if(!handler)exit(95);
   for(uint64_t i=0;i<pages;i++){DWORD old;if(!VirtualProtect(G+i*ps,ps,PAGE_READONLY|PAGE_GUARD,&old))exit(95);}
#else
   struct sigaction sa,old_sa;memset(&sa,0,sizeof(sa));sa.sa_sigaction=guard_segv;sa.sa_flags=SA_SIGINFO;
   if(sigemptyset(&sa.sa_mask)||sigaction(SIGSEGV,&sa,&old_sa))exit(95);
   for(uint64_t i=0;i<64;i++)g_touched[i]=0;
   for(uint64_t i=0;i<pages;i++){if(mprotect(G+i*ps,ps,PROT_NONE))exit(95);}
#endif
   uint64_t gs=dong_c52_emit(gn?ft:NULL,gn,gw?GW.p:NULL,gw,go?GO.p:NULL,go,(uint64_t*)GR.p);
#ifdef _WIN32
   for(uint64_t i=0;i<pages;i++){
    MEMORY_BASIC_INFORMATION mbi;if(VirtualQuery(G+i*ps,&mbi,sizeof(mbi))!=sizeof(mbi))exit(95);
    touched[i]=(mbi.Protect&PAGE_GUARD)?0:1;
   }
#else
   for(uint64_t i=0;i<pages;i++)touched[i]=g_touched[i];
#endif
   /* Freeze observations before reading snapshots; unarm all pages before restoring the previous handler. */
   if(!ro_protect(G,pages*ps))exit(95);
#ifdef _WIN32
   if(!RemoveVectoredExceptionHandler(handler))exit(95);
#else
   if(sigaction(SIGSEGV,&old_sa,NULL))exit(95);
#endif
   uint64_t gv=gok(GF)&&gok(GW)&&gok(GO)&&gok(GR)&&filled(GW.p,gw)&&filled(GO.p,go)&&filled(GR.p,8)
    &&!memcmp(GF.p,GF0.p,gn*72)&&!memcmp(G,G0.p,pages*ps);
   uint64_t gdirty=0;for(uint64_t i=0;i<gw;i++)if(GW.p[i]!=0xa5)gdirty=i+1;
   uint64_t gout[8]={gs,pages,gdirty,gv,0,0,0,0};write_exact(gout,64);write_exact(touched,pages);
   ro_free(G,pages*ps);rm(GF);rm(GF0);rm(G0);rm(GW);rm(GO);rm(GR);continue;
  }
  uint64_t nf=h[0],pool=h[1],wl=h[2],ol=h[3],flags=h[4];
  if(nf>12||pool>30000||wl>70000||ol>70000){fprintf(stderr,"bounds nf=%u pool=%u work=%u out=%u\n",(unsigned)nf,(unsigned)pool,(unsigned)wl,(unsigned)ol);exit(94);}
  uint64_t d[12*9];read_exact(d,nf*72);
  Buf P=mk(pool),P0=mk(pool),FT=mk(nf*72),FT0=mk(nf*72);read_exact(P.p,pool);memcpy(P0.p,P.p,pool);
  Buf W=mk(wl),O=mk(ol),WR=mk(8);uint64_t protected_ok=1;const Fn*table;uint8_t*page=NULL;uint64_t psize=4096*16;
  if(flags&2){
   page=ro_alloc(psize);if(!page)exit(95);memcpy(page,P.p,pool);uint64_t at=(pool+7)&~7ull;Fn*t=(Fn*)(page+at);
   for(uint64_t i=0;i<nf;i++){build_fn(t+i,page,d+9*i);}
   protected_ok=ro_protect(page,psize);table=nf?t:NULL;
   memcpy(FT0.p,t,nf*72);
  }else{
   for(uint64_t i=0;i<nf;i++){build_fn((Fn*)FT.p+i,P.p,d+9*i);}
   memcpy(FT0.p,FT.p,nf*72);table=nf?(const Fn*)FT.p:NULL;
  }
  uint64_t s=dong_c52_emit(table,nf,wl?W.p:NULL,wl,ol?O.p:NULL,ol,(uint64_t*)WR.p);
  uint64_t written=*(uint64_t*)WR.p;uint64_t v=gok(P)&&gok(FT)&&gok(W)&&gok(O)&&gok(WR)&&!memcmp(P.p,P0.p,pool);
  if(!(flags&2))v=v&&!memcmp(FT.p,FT0.p,nf*72);
  if(s){v=v&&filled(O.p,ol)&&filled(WR.p,8);written=0;}
  else v=v&&written<=ol&&filled(O.p+written,ol-written);
  uint64_t dirty=0;for(uint64_t i=0;i<wl;i++)if(W.p[i]!=0xa5)dirty=i+1;
  uint64_t out[8]={s,v,written,dirty,protected_ok,0,0,0};write_exact(out,64);write_exact(O.p,written);write_exact(W.p,dirty);
  if(page)ro_free(page,psize);
  rm(P);rm(P0);rm(FT);rm(FT0);rm(W);rm(O);rm(WR);
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
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 static uint64_t io[STATE+2];
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  memset(io,0,sizeof(io));io[0]=io[STATE+1]=0xa5a5a5a5a5a5a5a5ull;
  table[i](io+1);
  if(io[0]!=0xa5a5a5a5a5a5a5a5ull||io[STATE+1]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  if(fwrite(io+1,8,STATE,stdout)!=STATE)exit(92);
 }return 0;
}
'''
# State layout (qwords): 0 rax after; 1 rsp before call; 2 rsp after; 3 rbx before (the planted value); 4 rbx after;
# 5 rbp after; 6..9 r12..r15 after; 10 caller stack canary after (read through the saved host anchor); 11 rsp%16 before the call.
RAX,RSP_BEFORE,RSP_AFTER,RBX_BEFORE,RBX_AFTER,RBP_AFTER,R12_AFTER,CANARY_AFTER,ALIGN,STATE=0,1,2,3,4,5,6,10,11,12
# Known values planted in every callee-saved register (rbx included: it is under test, never the observation pointer).
CALLER={'rbx':0x0bbb0bbb0bbb0bbb,'rbp':0x0b0b0b0b0b0b0b0b,'r12':0x1212121212121212,'r13':0x1313131313131313,'r14':0x1414141414141414,'r15':0x1515151515151515}
CANARY=0x5ca1ab1e0ddba11c
JUNK=0xdead00000000be00


# ---------------------------------------------------------------- independent Python models
def symbol(module,item):
    """Independent CR3 expectation: __dong_m<hex module>_n<hex item>, two lowercase digits per byte."""
    return '__dong_m'+module.hex()+'_n'+item.hex()


def body_text(module,item,p,slots,program,rs):
    """Independent whole-function text model of the integrated C48 emitter."""
    frame=(8*slots+15)//16*16;off=lambda s:8*(s+1)
    lines=[symbol(module,item)+':','push rbp','mov rbp, rsp','sub rsp, %d'%frame]
    lines+=['mov qword [rbp - %d], %s'%(off(i),REGS[i])for i in range(p)]
    for op,d,l,r,imm in program:
        if op==CONST:lines.append('mov rax, %d'%imm)
        elif op==COPY:lines.append('mov rax, qword [rbp - %d]'%off(l))
        else:lines+=['mov rax, qword [rbp - %d]'%off(l),'mov rcx, qword [rbp - %d]'%off(r),'%s rax, rcx'%MNEMONIC[op]]
        lines.append('mov qword [rbp - %d], rax'%off(d))
    lines+=['mov rax, qword [rbp - %d]'%off(rs),'add rsp, %d'%frame,'pop rbp','ret']
    return ''.join(l+'\n'for l in lines)


def module_text(functions):
    """Independent module model: fixed header, then 'global <symbol>' immediately followed by that function's own body."""
    out=HEADER
    for f in functions:
        out+='global %s\n'%symbol(f['m'],f['i'])+body_text(f['m'],f['i'],f['p'],f['slots'],f['prog'],f['rs'])
    return out.encode()


def interpret(f,args):
    """Independent u64 interpreter of the IR."""
    s=[None]*f['slots']
    for i in range(f['p']):s[i]=args[i]
    for op,d,l,r,imm in f['prog']:
        if op==CONST:v=imm
        elif op==COPY:v=s[l]
        else:
            a,b=s[l],s[r]
            v={ADD:a+b,SUB:a-b,AND:a&b,OR:a|b,XOR:a^b,IMUL:a*b}[op]&U64
        s[d]=v
    return s[f['rs']]


def fn(m,i,p,slots,prog,rs):
    return dict(m=m,i=i,p=p,slots=slots,prog=prog,rs=rs)


# Four modules (1, 2, 2 and 8 functions; 13 native vectors per mode). Every (module,item) pair is unique across all of them.
MOD_A=[fn(b'm',b'f',1,2,[(ADD,1,0,0,0)],1)]                                                    # [21] -> 42
MOD_B=[fn(b'lib',b'add',2,3,[(ADD,2,0,1,0)],2),fn(b'lib',b'sub',2,3,[(SUB,2,0,1,0)],2)]        # same module, different item
MOD_C=[fn(b'm1',b'run',1,1,[],0),                                                               # same item, different module; empty IR returns a parameter
       fn(b'm2',b'run',2,2,[(IMUL,0,0,1,0)],0)]                                                 # two parameters, return slot 0 (the bad-return-slot fixture)
MOD_D=[fn(b'\xe4\xb8\xad\xe6\x96\x87',b'\xff\xfe',6,8,[(ADD,6,0,1,0),(SUB,7,6,2,0),(AND,6,7,3,0),(OR,7,6,4,0),(XOR,6,7,5,0),(IMUL,7,6,0,0)],7),
       fn(b'M'*64,b'N'*64,0,1,[(CONST,0,0,0,H)],0),                                              # 1-byte-class limits: 64-byte names, 0 parameters
       fn(b'd',b'e1',3,4,[(COPY,3,2,0,0)],3),
       fn(b'd',b'e2',2,2,[(SUB,0,1,0,0)],0),
       fn(b'd',b'e4',0,32,[(CONST,31,0,0,U64),(CONST,0,0,0,1),(XOR,31,31,0,0)],31),             # 32 slots, return the last
       fn(b'd2',b'e1',2,3,[(ADD,2,0,1,0),(IMUL,2,2,1,0)],2),
       fn(b'd',b'e5',6,6,[],5),                                                                   # 6 parameters, empty IR returns the last
       fn(b'd',b'e6',2,3,[(SUB,2,1,0,0),(SUB,2,2,0,0)],2)]
ARGS={(b'm',b'f'):[21],(b'lib',b'add'):[U64,2],(b'lib',b'sub'):[5,9],(b'm1',b'run'):[H],(b'm2',b'run'):[H|3,L],
      (b'\xe4\xb8\xad\xe6\x96\x87',b'\xff\xfe'):[0x1111,0x2222,0x3333,0xff00ff00ff00ff00,0x0f0f,0xaaaa5555aaaa5555],
      (b'M'*64,b'N'*64):[],(b'd',b'e1'):[1,2,3],(b'd',b'e2'):[5,3],(b'd',b'e4'):[],(b'd2',b'e1'):[U64,2],
      (b'd',b'e5'):[1,2,3,4,5,U64],(b'd',b'e6'):[L,H]}
MODULES=[MOD_A,MOD_B,MOD_C,MOD_D]


def layout(functions):
    """Pool bytes and per-function descriptors (m_off,m_len,i_off,i_len,p,slots,x_off,x_count,rs) with gaps; IR 8-aligned."""
    pool=bytearray();descs=[]
    def place(data,align=8):
        while len(pool)%align:pool.append(0xa5)
        off=len(pool);pool.extend(data);pool.extend(b'\xa5'*8);return off
    for f in functions:
        mo=place(f['m'],1);io=place(f['i'],1)
        xo=place(b''.join(struct.pack('<5Q',*x)for x in f['prog']))
        descs.append([mo,len(f['m']),io,len(f['i']),f['p'],f['slots'],xo,len(f['prog']),f['rs']])
    return bytes(pool),descs


class NasmU64ModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-nasm-u64-module'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.records=[]
        cls.inputs=cls.digests()
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.nm=shutil.which('nm')
        cls.executables=cls.build_all('good',SOURCE.read_text(encoding='utf-8'),C48.read_text(encoding='utf-8'))

    @staticmethod
    def digests():
        return {p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,DOC,*DEPENDENCIES,Path(__file__)]}

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=240)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))
        return r.stdout

    @classmethod
    def build_all(cls,name,module_text_,c48_text):
        """Stage only this component and the integrated C48 closure (C48 optionally a bad copy), then build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        (root/'bootstrap/nasm_u64_function.dg').write_text(c48_text,encoding='utf-8')
        (root/'bootstrap/nasm_u64_module.dg').write_text(module_text_,encoding='utf-8')
        (root/'probe/c52_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/c52_export.dg',roots=[root],mode=mode)
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
            stable=after==cls.inputs,artifact_sha256=files,records=cls.records,integrated=False,OS_VM_built=False,
            nm=cls.nm),indent=2)+'\n')
        if after!=cls.inputs:raise AssertionError(('input/dependency SHA256 changed during the run',cls.inputs,after))

    # ---------------------------------------------------------------- harness protocol
    def emit_all(self,exe,cases,label):
        """cases: (pool, descriptors, work_len, out_len, flags). Returns dicts: status, valid, written, dirty, protected, text, work."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for pool,descs,wl,ol,flags in cases:
            payload.extend(struct.pack('<16Q',len(descs),len(pool),wl,ol,flags,*[0]*11))
            for d in descs:payload.extend(struct.pack('<9Q',*d))
            payload.extend(pool)
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=300)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],PREFLIGHTS)
        at=8;out=[]
        for _ in cases:
            status,valid,written,dirty,protected=struct.unpack_from('<5Q',run.stdout,at);at+=64
            text=run.stdout[at:at+written];at+=written;work=run.stdout[at:at+dirty];at+=dirty
            out.append(dict(status=status,valid=valid,written=written,dirty=dirty,protected=protected,text=text,work=work))
        self.assertEqual(at,len(run.stdout));return out

    def case(self,functions,work=None,out=None,flags=0,mutate=None):
        pool,descs=layout(functions)
        if mutate:pool,descs=mutate(pool,descs)
        try:text=module_text(functions)if functions else b''
        except (KeyError,IndexError):text=b''                                      # deliberately malformed IR/parameters
        budget=22+len(descs)*PER
        return (pool,descs,budget if work is None else work,len(text)if out is None else out,flags)

    def check(self,label,got,status,functions,work=None,out=None):
        """Status, guards and the work/out/written contract for one call."""
        self.assertEqual(got['status'],status,(label,got['status']))
        self.assertEqual(got['valid'],1,(label,'guards / atomicity'))
        text=module_text(functions)
        if status==OK:
            self.assertEqual(got['text'],text,(label,'module text'))
            self.assertEqual(got['written'],len(text));self.assertEqual(got['work'],text,(label,'work holds exactly the module prefix'))
        elif status==CAPACITY:
            self.assertEqual(got['written'],0);self.assertEqual(got['work'],text,(label,'work keeps the generated module on CAPACITY'))
        else:
            self.assertEqual((got['written'],got['dirty']),(0,0),(label,'INVALID/WORKSPACE leave work untouched'))

    # ---------------------------------------------------------------- native link + calls
    def native_run(self,modules,texts,label):
        """The module texts produced by the Dong emitter go to NASM unchanged (ELF64 and COFF), and the native-format objects
        are linked with a hand-written SysV bridge. Each stub saves the host's callee-saved registers, then stores the
        observation-area address and a host stack anchor in independent static memory (no register under test holds either),
        plants known values in every callee-saved register (rbx included), the arguments and a stack canary, and really calls
        the exported symbol. After the return it parks RAX, reloads the observation address from static memory, records RAX,
        RSP and every callee-saved register exactly as returned, reads the canary through the anchor, restores RSP from the
        anchor and the host's registers from its own pushes. All assertions run afterwards in Python."""
        vectors=[f for m in modules for f in m];names=[(f['m'],f['i'])for f in vectors]
        self.assertEqual(len(set(names)),len(names));self.assertLessEqual(len(vectors),24)
        objects=[];exports=[]
        for k,text in enumerate(texts):
            asm=self.work/('%s-module%d.asm'%(label,k));asm.write_bytes(text)
            for fmt in ('elf64','win64'):
                obj=self.work/('%s-module%d.%s.o'%(label,k,fmt))
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',obj,asm],'%s-module%d-%s'%(label,k,fmt))
                if self.nm:
                    listing=self.command([self.nm,'-g',obj],'%s-module%d-%s-nm'%(label,k,fmt))
                    found={l.split()[-1]for l in listing.splitlines()if l.split()[-2:-1]==['T']}
                    self.assertEqual(found,{symbol(f['m'],f['i'])for f in modules[k]},(label,k,fmt,'exported symbol set'))
                    exports.append((label,k,fmt,sorted(found)))
            objects.append(self.work/('%s-module%d.%s.o'%(label,k,self.native)))
        stub=['bits 64']+['extern '+symbol(*n)for n in names]+['section .data','align 8','observation: dq 0','host_anchor: dq 0','parked_rax: dq 0','section .text']
        for k,f in enumerate(vectors):
            args=ARGS[(f['m'],f['i'])];p=f['p']
            stub+=['global v%d'%k,'v%d:'%k,'push rbx','push rbp','push r12','push r13','push r14','push r15','sub rsp, 8']
            stub+=['mov [rel observation], rdi','mov [rel host_anchor], rsp','mov r11, rdi']
            stub+=['mov rax, 0x%x'%CANARY,'mov [rsp], rax','mov [r11+%d], rsp'%(8*RSP_BEFORE),
                   'mov rax, rsp','and rax, 15','mov [r11+%d], rax'%(8*ALIGN),'mov rax, 0x%x'%CALLER['rbx'],'mov [r11+%d], rax'%(8*RBX_BEFORE)]
            stub+=['mov %s, 0x%x'%(r,v)for r,v in CALLER.items()]
            stub+=['mov %s, 0x%x'%(REGS[i],args[i]if i<p else JUNK|i)for i in range(6)]+['mov rax, 0x%x'%JUNK,'call '+symbol(f['m'],f['i'])]
            stub+=['mov [rel parked_rax], rax','mov rax, [rel observation]',
                   'mov [rax+%d], rsp'%(8*RSP_AFTER),'mov [rax+%d], rbx'%(8*RBX_AFTER),'mov [rax+%d], rbp'%(8*RBP_AFTER)]
            stub+=['mov [rax+%d], r%d'%(8*(R12_AFTER+j),12+j)for j in range(4)]
            stub+=['mov rcx, [rel parked_rax]','mov [rax+%d], rcx'%(8*RAX),
                   'mov rcx, [rel host_anchor]','mov rcx, [rcx]','mov [rax+%d], rcx'%(8*CANARY_AFTER)]
            stub+=['mov rsp, [rel host_anchor]','add rsp, 8','pop r15','pop r14','pop r13','pop r12','pop rbp','pop rbx','ret']
        bridge=self.work/(label+'.bridge.asm');bridge.write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.bridge.'+fmt+'.o'),bridge],label+'-bridge-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','#define STATE %d\n'%STATE+'\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(vectors))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(vectors))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.bridge.'+self.native+'.o'),*objects,'-o',exe],label+'-native-link')
        run=subprocess.run([str(exe)],capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        self.assertEqual(len(run.stdout),8*STATE*len(vectors))
        for k,f in enumerate(vectors):
            got=struct.unpack_from('<%dQ'%STATE,run.stdout,8*STATE*k)
            self.assertEqual(got[ALIGN],0,(label,k,'caller rsp aligned before call'))
            self.assertEqual(got[RAX],interpret(f,ARGS[(f['m'],f['i'])]),(label,k,'native rax',f['i']))
            self.assertEqual(got[RSP_AFTER],got[RSP_BEFORE],(label,k,'native rsp balanced across call/ret'))
            self.assertEqual(got[RBX_BEFORE],CALLER['rbx'],(label,k,'planted rbx recorded'))
            self.assertEqual(got[RBX_AFTER],CALLER['rbx'],(label,k,'native rbx preserved'))
            self.assertEqual((got[RBP_AFTER],*got[R12_AFTER:R12_AFTER+4]),tuple(v for r,v in CALLER.items()if r!='rbx'),(label,k,'native rbp/r12..r15 preserved'))
            self.assertEqual(got[CANARY_AFTER],CANARY,(label,k,'caller stack canary'))
        return exports

    def good_texts(self,exe,label,flags=0):
        got=self.emit_all(exe,[self.case(m,flags=flags)for m in MODULES],label)
        for k,(m,g)in enumerate(zip(MODULES,got)):
            self.check((label,k),g,OK,m);self.assertEqual(g['protected'],1)
        return [g['text']for g in got]

    # ---------------------------------------------------------------- tests
    def test_exact_text_priorities_and_work_out_contract(self):
        for mode,exe in self.executables.items():
            cases=[];meta=[]
            for k,m in enumerate(MODULES):
                text=module_text(m);B=22+len(m)*PER
                for label,work,out,status in (('exact',B,len(text),OK),('spare tail',B+100,len(text)+9,OK),('out short 1',B,len(text)-1,CAPACITY),
                                              ('out zero',B,0,CAPACITY),('work short 1',B-1,len(text),WORKSPACE),('work zero',0,len(text),WORKSPACE),
                                              ('work and out short',B-1,0,WORKSPACE)):
                    cases.append(self.case(m,work=work,out=out,flags=2 if (k+len(label))%3==0 else 0));meta.append((k,label,status,m))
            for (k,label,status,m),g in zip(meta,self.emit_all(exe,cases,'text-'+mode)):self.check((mode,k,label),g,status,m)
            self.good_texts(exe,'readonly-'+mode,flags=2)          # all four modules from a read-only page; the protection call must succeed
            # INVALID beats WORKSPACE beats CAPACITY; the invalid function is the LAST one, after legal ones
            bad=[dict(f)for f in MOD_D];bad[-1]=fn(b'd',b'bad',2,4,[(ADD,3,3,0,0)],3)                       # reads an uninitialized slot
            priority=[self.case(bad,work=0,out=0),self.case(bad,work=22,out=1),self.case(MOD_B,work=22+2*PER-1,out=0),self.case(MOD_B,out=1)]
            got=self.emit_all(exe,priority,'priority-'+mode)
            for g,st in zip(got,(INVALID,INVALID,WORKSPACE,CAPACITY)):self.assertEqual((g['status'],g['valid']),(st,1),(mode,'priority'))
            self.assertEqual([g['dirty']for g in got[:3]],[0,0,0],'INVALID/WORKSPACE never touch work')
        self.records.append(dict(test='exact-text-priorities-work-out',modules=len(MODULES),cases_per_mode=len(cases)+4,modes=2,preflights_per_native=PREFLIGHTS,passed=True))

    def test_overlapping_duplicate_and_invalid_inputs(self):
        for mode,exe in self.executables.items():
            ok=[];bad=[]
            # inputs may overlap each other: both functions share one name buffer and one IR array; module == item bytes
            def shared(pool,descs):
                a,b=descs;b[0],b[1],b[2],b[3],b[6],b[7]=a[2],a[3],a[0],a[1],a[6],a[7];return pool,[a,b]
            two=[fn(b'ab',b'cd',2,3,[(ADD,2,0,1,0)],2),fn(b'cd',b'ab',2,3,[(ADD,2,0,1,0)],2)]
            ok.append((self.case(two,mutate=shared),two))
            # item name located inside the module name's bytes, and read-only
            def inside(pool,descs):
                d=descs[0];d[2],d[3]=d[0]+1,2;return pool,descs
            inner=[fn(b'wxyz',b'xy',1,2,[(ADD,1,0,0,0)],1)];ok.append((self.case(inner,mutate=inside,flags=2),inner))
            # only one name equal is legal
            same_item=[fn(b'a',b'x',0,1,[(CONST,0,0,0,1)],0),fn(b'b',b'x',0,1,[(CONST,0,0,0,2)],0)]
            same_module=[fn(b'a',b'x',0,1,[(CONST,0,0,0,1)],0),fn(b'a',b'y',0,1,[(CONST,0,0,0,2)],0)]
            ok+=[(self.case(same_item),same_item),(self.case(same_module),same_module)]
            # duplicates: independent copies, and the very same pointers
            dup=[fn(b'a',b'x',0,1,[(CONST,0,0,0,1)],0),fn(b'a',b'x',0,1,[(CONST,0,0,0,2)],0)]
            def pointers(pool,descs):
                a,b=descs;b[0],b[1],b[2],b[3]=a[0],a[1],a[2],a[3];return pool,[a,b]
            bad+=[self.case(dup),self.case(dup,mutate=pointers),self.case(dup,work=0,out=0)]
            three_dup=[fn(b'a',b'x',0,1,[(CONST,0,0,0,1)],0),fn(b'b',b'y',0,1,[(CONST,0,0,0,2)],0),fn(b'a',b'x',0,1,[(CONST,0,0,0,3)],0)]
            bad.append(self.case(three_dup))
            # C48-level IR/parameter/name errors in every position, always INVALID (even with tiny work/out)
            legal=lambda k:fn(b'm',b'f%d'%k,2,3,[(ADD,2,0,1,0)],2)
            faults=[('uninitialized read',fn(b'z',b'z',2,4,[(ADD,3,3,0,0)],3)),('return slot never written',fn(b'z',b'z',2,4,[(ADD,2,0,1,0)],3)),
                    ('unknown operation',fn(b'z',b'z',2,3,[(9,2,0,1,0)],2)),('7 parameters',fn(b'z',b'z',7,8,[],0)),('0 slots',fn(b'z',b'z',0,0,[],0)),
                    ('33 slots',fn(b'z',b'z',0,33,[(CONST,0,0,0,1)],0)),('empty module name',fn(b'',b'z',1,1,[],0)),('65-byte item',fn(b'z',b'i'*65,1,1,[],0)),
                    ('unused field set',fn(b'z',b'z',1,2,[(CONST,1,5,0,1)],1)),('65 instructions',fn(b'z',b'z',1,2,[(ADD,1,0,0,0)]*65,1))]
            for label,faulty in faults:
                for position in (0,1,2):
                    functions=[legal(0),legal(1),legal(2)];functions[position]=faulty
                    bad.append(self.case(functions,work=22+3*PER if position else 0,out=0 if position==1 else None))
            # count limits: 9 functions and 0 functions
            nine=[fn(b'm',b'n%d'%k,0,1,[(CONST,0,0,0,k)],0)for k in range(9)];bad.append(self.case(nine));bad.append(self.case([]))
            eight=[fn(b'm',b'n%d'%k,0,1,[(CONST,0,0,0,k)],0)for k in range(8)];ok.append((self.case(eight),eight))
            got=self.emit_all(exe,[c for c,_ in ok]+bad,'overlap-'+mode)
            for (c,functions),g in zip(ok,got):self.check((mode,'legal overlap/near-duplicate'),g,OK,functions);self.assertEqual(g['protected'],1)
            for g in got[len(ok):]:self.assertEqual((g['status'],g['valid'],g['written'],g['dirty']),(INVALID,1,0,0),(mode,'invalid input'))
        self.records.append(dict(test='overlapping-duplicate-invalid',ok_cases=len(ok),invalid_cases=len(bad),modes=2,passed=True))

    def test_assembled_linked_and_called_for_every_export(self):
        self.assertLessEqual(sum(len(m)for m in MODULES),24)
        report=[]
        for mode,exe in self.executables.items():
            report+=self.native_run(MODULES,self.good_texts(exe,'native-good-'+mode),'native-'+mode)
        self.records.append(dict(test='native-module-link-and-call',modules=len(MODULES),vectors_per_mode=sum(len(m)for m in MODULES),modes=2,
                                 formats=['elf64','win64'],nm_checked=bool(self.nm),exports=len(report),passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8');c48=C48.read_text(encoding='utf-8')
        generate='f.emit(functions[i].module_name,functions[i].item_name,functions[i].parameter_count,functions[i].slot_count,\n   functions[i].instructions,functions[i].return_slot,slice_from_raw_parts(&work[at],BODY),&n)'
        self.assertEqual(source.count(generate),1)
        dup_start=source.index(' // Duplicate (module,item) byte pairs.');dup_end=source.index(' // The existing C48 contract is the IR check')
        duplicate_block=source[dup_start:dup_end];self.assertEqual(source.count(duplicate_block),1)
        capacity=' if at>out.len{return CAPACITY;}';workspace=' if work.len<HEADER+functions.len*PER{return WORKSPACE;}'
        for x in (capacity,workspace):self.assertEqual(source.count(x),1,x)
        # 1. Return slot silently changed to another initialized parameter slot (only >= 2 parameters, slot 0, different values).
        wrong=source.replace(generate,'f.emit(functions[i].module_name,functions[i].item_name,functions[i].parameter_count,functions[i].slot_count,\n   functions[i].instructions,'
            'swapped_slot(functions[i].parameter_count,functions[i].return_slot),slice_from_raw_parts(&work[at],BODY),&n)',1)
        wrong=wrong.replace('unsafe fn put(','fn swapped_slot(p:usize,rs:usize)usize{if p>=2&&rs==0{return 1;}return rs;}\nunsafe fn put(',1)
        self.assertNotEqual(interpret(MOD_C[1],ARGS[(b'm2',b'run')]),ARGS[(b'm2',b'run')][1])                    # the swapped slot has a different value
        for mode,exe in self.executables.items():
            texts=self.good_texts(exe,'bad-slot-good-'+mode)
            self.native_run(MODULES,texts,'bad-slot-good-'+mode)
        for mode,exe in self.build_all('bad-return-slot',wrong,c48).items():
            got=self.emit_all(exe,[self.case(m,out=len(module_text(m))+256)for m in MODULES],'bad-slot-'+mode)
            for g in got:self.assertEqual((g['status'],g['valid']),(OK,1))
            with self.assertRaisesRegex(AssertionError,'native rax'):self.native_run(MODULES,[g['text']for g in got],'bad-slot-'+mode)
        self.records.append(dict(test='bad-return-slot-swapped',compiled=True,linked=True,native_executed=True,modes=2,rejected_by='native rax'))
        # 2. Duplicate check removed: rejected by status only; the conflicting module is never assembled or executed.
        no_dup=source.replace(duplicate_block,'',1)
        dup=[fn(b'a',b'x',0,1,[(CONST,0,0,0,1)],0),fn(b'a',b'x',0,1,[(CONST,0,0,0,2)],0)]
        for mode,exe in self.executables.items():
            g=self.emit_all(exe,[self.case(dup)],'bad-dup-good-'+mode)[0];self.assertEqual((g['status'],g['valid'],g['dirty']),(INVALID,1,0))
        for mode,exe in self.build_all('bad-no-duplicate-check',no_dup,c48).items():
            g=self.emit_all(exe,[self.case(dup)],'bad-dup-'+mode)[0]
            self.assertNotEqual(g['status'],INVALID,(mode,'the bad module accepts a duplicate'))
        self.records.append(dict(test='bad-no-duplicate-check',compiled=True,native_executed=True,modes=2,rejected_by='status (not INVALID)'))
        # 3. out too small: the work header is published into out first. Rejected by the out/written atomicity guards.
        early=source.replace(capacity,' if at>out.len{var k:usize=0;while k<out.len&&k<22{out[k]=work[k];k+=1;}return CAPACITY;}',1)
        short=self.case(MOD_B,out=len(module_text(MOD_B))-1)
        for mode,exe in self.executables.items():
            g=self.emit_all(exe,[short],'bad-early-good-'+mode)[0];self.assertEqual((g['status'],g['valid']),(CAPACITY,1))
        for mode,exe in self.build_all('bad-early-header',early,c48).items():
            g=self.emit_all(exe,[short],'bad-early-'+mode)[0];self.assertEqual(g['status'],CAPACITY)
            self.assertEqual(g['valid'],0,(mode,'atomicity guard must catch the early out write'))
        self.records.append(dict(test='bad-early-header-in-out',compiled=True,native_executed=True,modes=2,rejected_by='out/written atomicity guard'))
        # 4. Work written before the WORKSPACE check: rejected because work must stay untouched on WORKSPACE.
        early_work=source.replace(workspace,' if work.len<HEADER+functions.len*PER{if work.len!=0{work[0]=98;}return WORKSPACE;}',1)
        starved=self.case(MOD_B,work=22+2*PER-1)
        for mode,exe in self.executables.items():
            g=self.emit_all(exe,[starved],'bad-work-good-'+mode)[0];self.assertEqual((g['status'],g['dirty']),(WORKSPACE,0))
        for mode,exe in self.build_all('bad-early-work-write',early_work,c48).items():
            g=self.emit_all(exe,[starved],'bad-work-'+mode)[0];self.assertEqual(g['status'],WORKSPACE);self.assertEqual(g['dirty'],1)
        self.records.append(dict(test='bad-early-work-write',compiled=True,native_executed=True,modes=2,rejected_by='work dirty byte on WORKSPACE'))
        # 5. Callee-saved RBX not preserved by every emitted function (bad copy of the integrated C48: add rbx, 8 before ret).
        exit_piece='if ex.emit(U64_KIND,frame,0,8*(return_slot+1),0,slice_from_raw_parts(&buffer[0],CHUNK),&n)!=ex.OK{return false;}\n  at=n;'
        self.assertEqual(c48.count(exit_piece),1)
        clobber=c48.replace(exit_piece,exit_piece+'at-=4;put(buffer,&at,"add rbx, 8\\nret\\n");',1)
        tail=b'pop rbp\nadd rbx, 8\nret\n'
        for mode,exe in self.executables.items():self.native_run(MODULES,self.good_texts(exe,'bad-rbx-good-'+mode),'bad-rbx-good-'+mode)
        for mode,exe in self.build_all('bad-rbx-clobbered',source,clobber).items():
            got=self.emit_all(exe,[self.case(m,out=len(module_text(m))+512)for m in MODULES],'bad-rbx-'+mode)
            for m,g in zip(MODULES,got):
                self.assertEqual((g['status'],g['valid']),(OK,1));self.assertEqual(g['text'].count(tail),len(m))
            with self.assertRaisesRegex(AssertionError,'native rbx preserved'):self.native_run(MODULES,[g['text']for g in got],'bad-rbx-'+mode)
        self.records.append(dict(test='bad-rbx-clobbered',vectors=sum(len(m)for m in MODULES),compiled=True,linked=True,native_executed=True,modes=2,
                                 rejected_by='native rbx preserved (rax and rsp assertions passed first)'))

    def guard_all(self,exe,cases,label):
        """cases: (functions, work_len, out_len). Every module name, item name and IR array sits alone in its own armed page;
        returns per case (status, work dirty length, touched flags in [module, item, IR] x function order, unchanged)."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for functions,wl,ol in cases:
            payload.extend(struct.pack('<16Q',0xC52,len(functions),wl,ol,*[0]*12))
            for f in functions:payload.extend(struct.pack('<9Q',len(f['m']),len(f['i']),f['p'],f['slots'],len(f['prog']),f['rs'],0,0,0))
            for f in functions:payload.extend(f['m']+f['i']+b''.join(struct.pack('<5Q',*x)for x in f['prog']))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=300)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],PREFLIGHTS)
        at=8;out=[]
        for functions,_,_ in cases:
            status,pages,dirty,valid=struct.unpack_from('<4Q',run.stdout,at);at+=64
            self.assertEqual(pages,3*len(functions));out.append((status,dirty,list(run.stdout[at:at+pages]),valid));at+=pages
        self.assertEqual(at,len(run.stdout));return out

    @staticmethod
    def guard_fixtures():
        """(label, functions, expected status, reads allowed, forbidden reads in the pre-R1 implementation)."""
        prog=[(ADD,1,0,0,0)]
        def f(m,i,body=prog):return dict(m=m,i=i,p=1,slots=2,prog=body,rs=1)
        a,b,c,d,e,g=(bytes([x])*64 for x in b'ABCDEG')
        fixtures=[
            ('control: legal 64-byte single function reads its bodies',[f(a,b)],WORKSPACE,True,False),
            ('control: every body in three functions is observed',[f(a,b),f(c,d),f(e,g)],WORKSPACE,True,False),
            ('control: empty IR page stays unread',[fn(a,b,1,1,[],0)],WORKSPACE,True,False),
            ('single function, 65-byte module',[f(b'A'*65,b)],INVALID,False,False),
            ('single function, 65-byte item',[f(a,b'B'*65)],INVALID,False,False),
            ('two functions, both with 65-byte modules',[f(b'A'*65,b),f(b'C'*65,d)],INVALID,False,True),
            ('two functions, both with 65-byte items',[f(a,b'B'*65),f(a,b'D'*65)],INVALID,False,True),
            ('empty item in the LAST function, legal function before it',[f(a,b),f(c,b'')],INVALID,False,True),
            ('empty module in the MIDDLE function of three',[f(a,b),f(b'',d),f(e,g)],INVALID,False,True),
            ('65 instructions in the FIRST function',[f(a,b,prog*65),f(c,d)],INVALID,False,True),
            ('65 instructions in the LAST function',[f(a,b),f(c,d,prog*65)],INVALID,False,True),
            ('66-byte item in the LAST of three functions',[f(a,b),f(c,d),f(e,b'G'*66)],INVALID,False,True),
        ]
        # Every position and both name roles; all other descriptors/bodies are valid and remain accessible if read.
        for role in ('m','i'):
            for count in (0,65):
                for position in range(3):
                    functions=[f(a,b),f(a,d),f(a,g)]
                    functions[position][role]=b'Z'*count
                    fixtures.append(('%s count %d at position %d'%(role,count,position),functions,INVALID,False,True))
        return fixtures

    def test_nested_prechecks_read_no_body_bytes(self):
        """Every function's name lengths (1..64) and IR count (<= 64) are checked before any name or IR byte is read by the
        duplicate scan or by C48. Observed safely: each body is alone in an armed page (PAGE_GUARD / PROT_NONE + handler)."""
        source=SOURCE.read_text(encoding='utf-8');fixtures=self.guard_fixtures()
        cases=[(fs,22+len(fs)*PER-1,10)for _,fs,_,_,_ in fixtures]
        observations=[]
        for mode,exe in self.executables.items():
            got=self.guard_all(exe,cases,'guard-'+mode)
            for (label,fs,status,reads,_),(st,dirty,touched,valid) in zip(fixtures,got):
                self.assertEqual(st,status,(mode,label));self.assertEqual(dirty,0,(mode,label,'work untouched'))
                self.assertEqual(valid,1,(mode,label,'full work/out/written/table/body/guard atomicity'))
                if reads:
                    expected=[int(bool(x))for f in fs for x in (f['m'],f['i'],f['prog'])]
                    self.assertEqual(touched,expected,(mode,label,'positive control: each nonempty body must be observed'))
                else:self.assertEqual(sum(touched),0,(mode,label,'no module/item/IR byte may be read before the INVALID answer',touched))
                observations.append(dict(variant='good',mode=mode,case=label,status=st,touched=touched,unchanged=valid))
        # Sensitivity: the previous implementation (no count prechecks) really reads bodies in the multi-function cases.
        marker=' if mn==0||mn>f.NAME_LIMIT as u64||inn==0||inn>f.NAME_LIMIT as u64||functions[i].instructions.len>f.MAX_INSTRUCTIONS{return INVALID;}\n'
        self.assertEqual(source.count(marker),1)
        for mode,exe in self.build_all('bad-no-count-precheck',source.replace(marker,'',1),C48.read_text(encoding='utf-8')).items():
            got=self.guard_all(exe,cases,'bad-guard-'+mode)
            for (label,fs,status,reads,old_reads),(st,dirty,touched,valid) in zip(fixtures,got):
                self.assertEqual((st,dirty,valid),(status,0,1),(mode,label,'old implementation returns normally and remains atomic'))
                if old_reads:
                    self.assertGreater(sum(touched),0,(mode,label,'the old implementation reads before rejecting'))
                elif reads:
                    self.assertEqual(touched,[int(bool(x))for f in fs for x in (f['m'],f['i'],f['prog'])],(mode,label))
                else:self.assertEqual(sum(touched),0,(mode,label))
                observations.append(dict(variant='bad-no-count-precheck',mode=mode,case=label,status=st,touched=touched,unchanged=valid))
        self.records.append(dict(test='nested-prechecks-read-no-body-bytes',cases=len(fixtures),modes=2,
                                 observation='PAGE_GUARD per body page (Linux: PROT_NONE + checked SIGSEGV handler)',
                                 observations=observations,passed=True))

    def test_alias_preflights_are_reachable(self):
        """Preflight sensitivity: a real Dong without the alias checks fails exactly the alias preflights 13..18 and 27..35."""
        source=SOURCE.read_text(encoding='utf-8')
        top_start=source.index(' // written, work and out are pairwise disjoint');top_end=source.index(' // Nested descriptors of every function')
        top=source[top_start:top_end]
        nested_old=source[source.index('  if overlap(wp,8,mp,mn)'):source.index('  i+=1;\n }\n // Duplicate')]
        self.assertEqual(source.count(top),1);self.assertEqual(source.count(nested_old),1)
        for mode,exe in self.executables.items():self.emit_all(exe,[],'alias-good-'+mode)
        for mode,exe in self.build_all('bad-no-alias',source.replace(top,'',1).replace(nested_old,'',1),C48.read_text(encoding='utf-8')).items():
            run=subprocess.run([str(exe)],input=struct.pack('<Q',0),capture_output=True,timeout=120)
            err=run.stderr.decode('ascii','replace');(self.work/('bad-no-alias-'+mode+'.stderr')).write_text(err,encoding='ascii')
            self.assertEqual(run.returncode,93,(mode,err))
            failed=[int(line.split()[2])for line in err.splitlines()if line.startswith('invalid preflight ')]
            self.assertEqual(failed,list(range(13,19))+list(range(27,36)),(mode,err))
        self.records.append(dict(test='bad-no-alias',compiled=True,native_executed=True,modes=2,rejected_by='preflights 13..18, 27..35'))


if __name__=='__main__':unittest.main()
