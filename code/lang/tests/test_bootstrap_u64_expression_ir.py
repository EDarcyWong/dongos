"""Actual Dong lexer -> expression.parse -> u64_expression_ir.lower -> integrated C48.emit -> assembly -> real call/ret (C51)."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[2]
WORKS=ROOT
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


SOURCE=ROOT/'lang/bootstrap/u64_expression_ir.dg'
DOC=ROOT/'lang/bootstrap/u64_expression_ir.md'
# Existing native frontend/integer baseline plus the integrated C48 emitter and its whole read-only import closure.
BASELINE=[ROOT/'lang/bootstrap'/(n+'.dg')for n in ('lexer','unicode','expression','bigint')]
C48=ROOT/'lang/bootstrap/nasm_u64_function.dg'
DEPENDENCIES=BASELINE+[C48]+[ROOT/'lang/bootstrap'/(n+'.dg')for n in (
    'nasm_symbol','decimal_integer','nasm_function_frame','nasm_sysv_incoming_args','sysv_integer_args','nasm_memory_operand',
    'nasm_integer_memory_load','nasm_integer_memory_store','nasm_integer_binary','nasm_sysv_function_exit',
    'nasm_sysv_return_values','sysv_return_plan')]
OK,INVALID,CAPACITY,UNSUPPORTED=0,1,2,3
U64=2**64-1
H,L=0x8000000000000000,0x7fffffffffffffff
NONE=U64
PREFLIGHTS=34
CONST,COPY,ADD,SUB,AND,OR,XOR,IMUL=range(8)
OPERATION={'+':ADD,'-':SUB,'*':IMUL,'&':AND,'|':OR,'^':XOR}
MNEMONIC={ADD:'add',SUB:'sub',AND:'and',OR:'or',XOR:'xor',IMUL:'imul'}
REGS=['rdi','rsi','rdx','rcx','r8','r9']
# lexer token kinds
T_EOF,T_IDENT,T_INT,T_FN,T_RETURN=0,1,2,266,281
T_LP,T_RP,T_COMMA,T_COLON,T_SEMI=1064,1065,1068,1082,1083
# expression node kinds
N_INTEGER,N_NAME,N_BINARY,N_UNARY=1,5,8,6
WRAPPER='''module probe.c51_export;
import bootstrap.lexer as lex;
import bootstrap.expression as ast;
import bootstrap.u64_expression_ir as u;
import bootstrap.nasm_u64_function as f;
export("dong_c51_lex") pub unsafe fn lex_raw(s:*const u8,n:usize,t:*lex.Token,cap:usize,st:*u8,sb:usize,out:*lex.Result)u64{unsafe{
 return lex.lex(slice_from_raw_parts(s,n),slice_from_raw_parts(t,cap),slice_from_raw_parts(st,sb),out);
}}
export("dong_c51_parse") pub unsafe fn parse_raw(s:*const u8,n:usize,t:*const lex.Token,c:usize,start:usize,nodes:*ast.Node,cap:usize,
 depth:usize,allow:bool,res:*ast.Result)u64{unsafe{
 return ast.parse(slice_from_raw_parts(s,n),slice_from_raw_parts(t,c),start,slice_from_raw_parts(nodes,cap),depth,allow,res);
}}
export("dong_c51_lower") pub unsafe fn lower_raw(s:*const u8,n:usize,t:*const lex.Token,nt:usize,nodes:*const ast.Node,nn:usize,root:usize,
 pt:*const usize,np:usize,out:*f.Instruction,cap:usize,res:*u.Result)u64{unsafe{
 return u.lower(slice_from_raw_parts(s,n),slice_from_raw_parts(t,nt),slice_from_raw_parts(nodes,nn),root,slice_from_raw_parts(pt,np),
  slice_from_raw_parts(out,cap),res);
}}
export("dong_c51_emit") pub unsafe fn emit_raw(m:*const u8,mn:usize,i:*const u8,inn:usize,p:usize,slots:usize,x:*const f.Instruction,xn:usize,
 rs:usize,out:*u8,no:usize,written:*usize)u64{unsafe{
 return f.emit(slice_from_raw_parts(m,mn),slice_from_raw_parts(i,inn),p,slots,slice_from_raw_parts(x,xn),rs,slice_from_raw_parts(out,no),written);
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
typedef struct{uint64_t kind,start,end,line,column,value_start,value_length;}Tok;
typedef struct{uint64_t count,used,code,start,line,column;}LexRes;
typedef struct{uint64_t kind,token,op,a,b,c,next,flags;}Nod;
typedef struct{uint64_t root,used,next,code,error;}PRes;
typedef struct{uint64_t ic,slots,rs;}LRes;
typedef struct{uint64_t op,dst,l,r,imm;}Ins;
extern uint64_t ABI dong_c51_lex(N,uint64_t,Tok*,uint64_t,uint8_t*,uint64_t,LexRes*);
extern uint64_t ABI dong_c51_parse(N,uint64_t,const Tok*,uint64_t,uint64_t,Nod*,uint64_t,uint64_t,uint8_t,PRes*);
extern uint64_t ABI dong_c51_lower(N,uint64_t,const Tok*,uint64_t,const Nod*,uint64_t,uint64_t,const uint64_t*,uint64_t,Ins*,uint64_t,LRes*);
extern uint64_t ABI dong_c51_emit(N,uint64_t,N,uint64_t,uint64_t,uint64_t,const Ins*,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
/* A guarded exact-size buffer: 32 guard bytes before and 64 after, all 0xa5. */
typedef struct{uint8_t*raw;uint8_t*p;uint64_t n;}Buf;
static Buf mk(uint64_t n){Buf b;b.n=n;b.raw=malloc(n+96);if(!b.raw||((uintptr_t)b.raw&15))exit(95);memset(b.raw,0xa5,n+96);b.p=b.raw+32;return b;}
static int gok(Buf b){return filled(b.raw,32)&&filled(b.p+b.n,64);}
static void rm(Buf b){free(b.raw);}
typedef struct{uint64_t status,valid,ic,slots,rs;uint8_t ir[24*40];}LowerOut;
/* One lower call on the given inputs with fresh guarded out/result buffers. valid = guards intact and atomicity held:
   on failure the whole out area and the whole result stay 0xa5; on success only the exact prefix/result are written. */
static void lower_run(LowerOut*o,N src,uint64_t slen,const Tok*tk,uint64_t ntok,const Nod*nd,uint64_t nn,uint64_t root,
 const uint64_t*pp,uint64_t np,uint64_t cap){
 Buf out=mk(cap*40),res=mk(24);
 o->status=dong_c51_lower(src,slen,tk,ntok,nd,nn,root,np?pp:NULL,np,cap?(Ins*)out.p:NULL,cap,(LRes*)res.p);
 uint64_t v=gok(out)&&gok(res);o->ic=o->slots=o->rs=0;memset(o->ir,0,sizeof(o->ir));
 if(o->status){v=v&&filled(out.p,cap*40)&&filled(res.p,24);}
 else{LRes*r=(LRes*)res.p;o->ic=r->ic;o->slots=r->slots;o->rs=r->rs;
  v=v&&r->ic<=cap&&r->ic<=24&&filled(out.p+r->ic*40,(cap-r->ic)*40);if(r->ic<=24&&r->ic<=cap)memcpy(o->ir,out.p,r->ic*40);}
 o->valid=v;rm(out);rm(res);
}
/* Copy the four lower inputs into one page-aligned region, 8-aligned each, and make the region read-only. */
typedef struct{uint8_t*page;uint64_t size;uint64_t protected_ok;N src;const Tok*tk;const Nod*nd;const uint64_t*pp;}Ro;
static Ro ro_make(N src,uint64_t slen,const Tok*tk,uint64_t ntok,const Nod*nd,uint64_t nn,const uint64_t*pp,uint64_t np){
 Ro r;r.size=4096*16;r.page=ro_alloc(r.size);if(!r.page)exit(95);uint64_t at=0;
 r.src=r.page+at;memcpy(r.page+at,src,slen);at=(at+slen+7)&~7ull;
 r.tk=(const Tok*)(r.page+at);memcpy(r.page+at,tk,ntok*sizeof(Tok));at+=ntok*sizeof(Tok);
 r.nd=(const Nod*)(r.page+at);memcpy(r.page+at,nd,nn*sizeof(Nod));at+=nn*sizeof(Nod);
 r.pp=(const uint64_t*)(r.page+at);memcpy(r.page+at,pp,np*8);at+=np*8;
 r.protected_ok=ro_protect(r.page,r.size);return r;
}
/* Descriptor/alias preflights on a real lexer+parser baseline ("a+1", params [a], out 4 instructions). Every other field
   is legal, so only the target check can reject it; each must return INVALID with the whole arena unchanged. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[16384],base[16384];const unsigned total=34;unsigned failed=0;
 memset(arena,0xa5,sizeof(arena));
 uint8_t*S=arena+64;memcpy(S,"a+1",3);Tok*T=(Tok*)(arena+256);Nod*Nd=(Nod*)(arena+512);uint64_t*P=(uint64_t*)(arena+768);
 uint8_t*O=arena+1024;LRes*R=(LRes*)(arena+1280);LexRes lr;PRes pr;uint8_t strings[64];
 if(dong_c51_lex(S,3,T,4,strings,sizeof(strings),&lr)||lr.count!=4)exit(97);
 if(dong_c51_parse(S,3,T,lr.count,0,Nd,3,16,0,&pr)||pr.root!=2||pr.used!=3)exit(98);
 P[0]=0;
 if(dong_c51_lower(S,3,T,4,Nd,3,2,P,1,(Ins*)O,4,R)!=0||R->ic!=2)exit(99);
 memset(O,0xa5,160);memset(R,0xa5,24);memcpy(base,arena,sizeof(arena));
 for(unsigned i=0;i<total;i++){
  memcpy(arena,base,sizeof(arena));
  N ps=S,pt2=NULL;(void)pt2;const Tok*pt=T;const Nod*pn=Nd;const uint64_t*pp=P;uint8_t*po=O;LRes*pr2=R;
  uint64_t ls=3,lt=4,ln=3,lp=1,lo=4,root=2;
  switch(i){
   case 0:pr2=NULL;break;                                            /* result NULL */
   case 1:pr2=(LRes*)(arena+1281);break;                             /* result odd */
   case 2:pr2=(LRes*)(uintptr_t)(UINT64_MAX-23);break;               /* result end overflow (aligned, exactly Result-sized) */
   case 3:po=(uint8_t*)(uintptr_t)(UINT64_MAX-39);break;             /* out end overflow */
   case 4:po=NULL;break;                                             /* NULL non-empty out */
   case 5:ps=NULL;break;case 6:ps=FAKE(UINT64_MAX-1);break;          /* source NULL / end overflow */
   case 7:pt=NULL;break;case 8:pt=(const Tok*)(arena+257);break;case 9:pt=FAKE(UINT64_MAX-55);break;   /* tokens */
   case 10:pn=NULL;break;case 11:pn=(const Nod*)(arena+513);break;case 12:pn=FAKE(UINT64_MAX-63);break; /* nodes */
   case 13:pp=NULL;break;case 14:pp=(const uint64_t*)(arena+769);break;case 15:pp=FAKE(UINT64_MAX-7);break; /* params */
   case 16:lt=0;break;case 17:lt=257;break;                          /* token count */
   case 18:ln=0;break;case 19:ln=25;break;                           /* node count */
   case 20:lp=7;break;case 21:ls=4097;break;case 22:root=3;break;    /* parameter count, source size, root */
   case 23:lo=UINT64_MAX/40+1;break;                                 /* out count * 40 overflows */
   case 24:pr2=(LRes*)O;break;                                       /* result on out prefix */
   case 25:pr2=(LRes*)(O+136);break;                                 /* result inside out's unused tail */
   case 26:pr2=(LRes*)S;break;case 27:pr2=(LRes*)T;break;            /* result on source / tokens */
   case 28:pr2=(LRes*)Nd;break;case 29:pr2=(LRes*)P;break;           /* result on nodes / params */
   case 30:po=arena+56;lo=1;break;                                   /* out over source's last byte */
   case 31:po=arena+456;lo=1;break;                                  /* out over tokens' last byte */
   case 32:po=arena+672;lo=1;break;                                  /* out over nodes' last byte */
   default:po=arena+736;lo=1;break;                                  /* out over params' last byte */
  }
  uint64_t s=dong_c51_lower(ps,ls,pt,lt,pn,ln,root,pp,lp,(Ins*)po,lo,pr2);
  int same=!memcmp(base,arena,sizeof(arena));
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
  uint64_t h[16];read_exact(h,sizeof(h));uint64_t cmd=h[0];
  if(cmd==2){                                  /* LEX: [2, srclen] + source -> [status, count] + tokens */
   uint64_t slen=h[1];if(slen>4096)exit(94);
   Buf S=mk(slen),T=mk(256*sizeof(Tok)),ST=mk(4096);read_exact(S.p,slen);LexRes lr;memset(&lr,0xa5,sizeof(lr));
   uint64_t st=dong_c51_lex(S.p,slen,(Tok*)T.p,256,ST.p,4096,&lr);
   uint64_t out[2]={st,st?0:lr.count};write_exact(out,16);write_exact(T.p,out[1]*sizeof(Tok));rm(S);rm(T);rm(ST);continue;
  }
  if(cmd==1){                                  /* RAW: caller-supplied tokens/nodes straight into lower */
   uint64_t slen=h[1],ntok=h[2],nn=h[3],root=h[4],np=h[5],cap=h[6],flags=h[7];uint64_t pt[7];memcpy(pt,h+8,56);
   if(slen>5000||ntok>400||nn>64||np>7||cap>64)exit(94);
   Buf S=mk(slen),T=mk(ntok*sizeof(Tok)),D=mk(nn*sizeof(Nod)),P=mk(np*8);
   read_exact(S.p,slen);read_exact(T.p,ntok*sizeof(Tok));read_exact(D.p,nn*sizeof(Nod));memcpy(P.p,pt,np*8);
   Buf S0=mk(slen),T0=mk(ntok*sizeof(Tok)),D0=mk(nn*sizeof(Nod)),P0=mk(np*8);
   memcpy(S0.p,S.p,slen);memcpy(T0.p,T.p,ntok*sizeof(Tok));memcpy(D0.p,D.p,nn*sizeof(Nod));memcpy(P0.p,P.p,np*8);
   LowerOut o;uint64_t protected_ok=1;
   if(flags&2){Ro r=ro_make(S.p,slen,(const Tok*)T.p,ntok,(const Nod*)D.p,nn,(const uint64_t*)P.p,np);protected_ok=r.protected_ok;
    lower_run(&o,r.src,slen,r.tk,ntok,r.nd,nn,root,r.pp,np,cap);ro_free(r.page,r.size);}
   else lower_run(&o,S.p,slen,(const Tok*)T.p,ntok,(const Nod*)D.p,nn,root,(const uint64_t*)P.p,np,cap);
   uint64_t same=!memcmp(S.p,S0.p,slen)&&!memcmp(T.p,T0.p,ntok*sizeof(Tok))&&!memcmp(D.p,D0.p,nn*sizeof(Nod))&&!memcmp(P.p,P0.p,np*8);
   same=same&&gok(S)&&gok(T)&&gok(D)&&gok(P);
   uint64_t out[6]={o.status,o.valid&&same,o.ic,o.slots,o.rs,protected_ok};write_exact(out,48);write_exact(o.ir,o.status?0:o.ic*40);
   rm(S);rm(T);rm(D);rm(P);rm(S0);rm(T0);rm(D0);rm(P0);continue;
  }
  /* PIPE: [0, srclen, start, np, ptok[6], cap, flags, mlen, ilen, 0] + source + module + item
     lex -> parse(start) -> lower(nodes[0..used)) -> emit; flags bit1: also lower from read-only copies. */
  uint64_t slen=h[1],start=h[2],np=h[3],cap=h[10],flags=h[11],ml=h[12],il=h[13];uint64_t ptok[6];memcpy(ptok,h+4,48);
  if(slen>4096||np>6||cap>64||ml>64||il>64)exit(94);
  Buf S=mk(slen),MB=mk(ml),IB=mk(il);read_exact(S.p,slen);read_exact(MB.p,ml);read_exact(IB.p,il);
  uint64_t o16[16];memset(o16,0,sizeof(o16));
  Buf T=mk(256*sizeof(Tok)),ST=mk(4096);LexRes lr;memset(&lr,0xa5,sizeof(lr));
  o16[0]=dong_c51_lex(S.p,slen,(Tok*)T.p,256,ST.p,4096,&lr);o16[1]=o16[0]?0:lr.count;
  Buf ND=mk(64*sizeof(Nod));PRes pr;memset(&pr,0xa5,sizeof(pr));uint64_t pused=0;
  if(!o16[0]){o16[2]=dong_c51_parse(S.p,slen,(const Tok*)T.p,lr.count,start,(Nod*)ND.p,64,64,0,&pr);o16[3]=pr.root;o16[4]=pr.used;o16[5]=pr.next;
   if(!o16[2])pused=pr.used;}
  uint64_t ptokcopy[6];memcpy(ptokcopy,ptok,48);
  LowerOut lo;memset(&lo,0,sizeof(lo));uint64_t lowered=0;
  Buf TK=mk(lr.count*sizeof(Tok)),NK=mk(pused*sizeof(Nod)),PK=mk(np*8);
  Buf IRB=mk(24*40),EO=mk(8192),WB=mk(8);uint64_t emit_status=9,emit_len=0,emit_valid=1,protected_ok=1,ro_same=1;
  if(!o16[0]&&!o16[2]){
   memcpy(TK.p,T.p,lr.count*sizeof(Tok));memcpy(NK.p,ND.p,pused*sizeof(Nod));memcpy(PK.p,ptokcopy,np*8);
   lower_run(&lo,S.p,slen,(const Tok*)TK.p,lr.count,(const Nod*)NK.p,pused,pr.root,(const uint64_t*)PK.p,np,cap);lowered=1;
   o16[6]=lo.status;o16[8]=lo.ic;o16[9]=lo.slots;o16[10]=lo.rs;
   uint64_t inputs_same=gok(TK)&&gok(NK)&&gok(PK)&&!memcmp(TK.p,T.p,lr.count*sizeof(Tok))&&!memcmp(NK.p,ND.p,pused*sizeof(Nod))&&!memcmp(PK.p,ptokcopy,np*8);
   o16[7]=lo.valid&&inputs_same;
   if(flags&2){LowerOut l2;Ro r=ro_make(S.p,slen,(const Tok*)TK.p,lr.count,(const Nod*)NK.p,pused,(const uint64_t*)PK.p,np);protected_ok=r.protected_ok;
    lower_run(&l2,r.src,slen,r.tk,lr.count,r.nd,pused,pr.root,r.pp,np,cap);ro_free(r.page,r.size);
    ro_same=l2.valid&&l2.status==lo.status&&l2.ic==lo.ic&&l2.slots==lo.slots&&l2.rs==lo.rs&&!memcmp(l2.ir,lo.ir,sizeof(lo.ir));}
   if(lo.status==0){
    memcpy(IRB.p,lo.ir,lo.ic*40);
    emit_status=dong_c51_emit(MB.p,ml,IB.p,il,np,lo.slots,lo.ic?(const Ins*)IRB.p:NULL,lo.ic,lo.rs,EO.p,8192,(uint64_t*)WB.p);
    emit_len=emit_status?0:*(uint64_t*)WB.p;
    emit_valid=gok(EO)&&gok(WB)&&(emit_status?filled(EO.p,8192):(emit_len<=8192&&filled(EO.p+emit_len,8192-emit_len)));
   }
  }
  o16[11]=emit_status;o16[12]=emit_len;o16[13]=emit_valid;o16[14]=protected_ok;o16[15]=ro_same;
  write_exact(o16,128);write_exact(T.p,o16[1]*sizeof(Tok));write_exact(ND.p,pused*sizeof(Nod));
  write_exact(lo.ir,(lowered&&!lo.status)?lo.ic*40:0);write_exact(EO.p,emit_len);
  rm(S);rm(MB);rm(IB);rm(T);rm(ST);rm(ND);rm(TK);rm(NK);rm(PK);rm(IRB);rm(EO);rm(WB);
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
PRECEDENCE={'|':4,'^':5,'&':6,'+':8,'-':8,'*':9}


def py_tokens(text):
    """Independent expression tokenizer: names, integer literals, + - * & | ^ and parentheses."""
    out=[];at=0
    while at<len(text):
        c=text[at]
        if c==' ':at+=1;continue
        m=re.compile(r'[A-Za-z_][A-Za-z_0-9]*|0[xX][0-9a-fA-F_]+|0[bB][01_]+|[0-9][0-9_]*|[-+*&|^()]').match(text,at)
        out.append(m.group(0));at=m.end()
    return out


def py_parse(tokens):
    """Independent precedence-climbing parser (all six operators are left-associative). Tree: ('n',name),('i',value),('b',op,l,r)."""
    pos=[0]
    def primary():
        t=tokens[pos[0]];pos[0]+=1
        if t=='(':
            e=expr(0);assert tokens[pos[0]]==')';pos[0]+=1;return e
        if re.match(r'[A-Za-z_]',t):return ('n',t)
        return ('i',int(t.replace('_',''),0))
    def expr(minimum):
        left=primary()
        while pos[0]<len(tokens) and tokens[pos[0]] in PRECEDENCE and PRECEDENCE[tokens[pos[0]]]>=minimum:
            op=tokens[pos[0]];pos[0]+=1;right=expr(PRECEDENCE[op]+1);left=('b',op,left,right)
        return left
    tree=expr(0);assert pos[0]==len(tokens);return tree


def py_ir(tree,params):
    """Expected C48 IR from the tree: post-order, NAME -> its parameter slot, fresh slot per INTEGER/BINARY from p."""
    program=[];state={'next':len(params)}
    def walk(t):
        if t[0]=='n':return params.index(t[1])
        if t[0]=='i':
            s=state['next'];state['next']+=1;program.append((CONST,s,0,0,t[1]));return s
        a=walk(t[2]);b=walk(t[3]);s=state['next'];state['next']+=1;program.append((OPERATION[t[1]],s,a,b,0));return s
    rs=walk(tree);return program,max(1,len(params)+len(program)),rs


def py_eval(tree,env):
    if tree[0]=='n':return env[tree[1]]
    if tree[0]=='i':return tree[1]
    a=py_eval(tree[2],env);b=py_eval(tree[3],env)
    return {'+':a+b,'-':a-b,'*':a*b,'&':a&b,'|':a|b,'^':a^b}[tree[1]]&U64


def symbol(module,item):
    """Independent CR3 expectation: __dong_m<hex module>_n<hex item>, two lowercase digits per byte."""
    return '__dong_m'+module.hex()+'_n'+item.hex()


def expected_text(module,item,p,slots,program,rs):
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
    return ''.join(l+'\n'for l in lines).encode()


def fixture_source(params,expr):
    return 'fn f(%s)u64{return %s;}'%(','.join(n+':u64'for n in params),expr)


def locate(tokens):
    """From the real lexer's token tuples (kind,start,end,...): signature parameter token indexes and the return expression start."""
    i=next(k for k,t in enumerate(tokens)if t[0]==T_FN);j=i+2
    assert tokens[j][0]==T_LP;j+=1;params=[]
    while tokens[j][0]!=T_RP:
        assert tokens[j][0]==T_IDENT;params.append(j)
        while tokens[j][0] not in (T_COMMA,T_RP):j+=1
        if tokens[j][0]==T_COMMA:j+=1
    r=next(k for k,t in enumerate(tokens)if t[0]==T_RETURN)
    return params,r+1


# (parameters, expression, argument values): every operation, 0/1/6 parameters, 0/max/high-bit values, wraparound,
# non-commutative SUB both ways, precedence, parentheses, repeated parameter reads, all literal forms, the 23-node maximum.
FIXTURES=[
    ([],'42',[]),
    ([],'0xFFFF_FFFF_FFFF_FFFF',[]),
    (['a'],'a',[0xfedcba9876543210]),
    (['a'],'a*a+a',[0x100000001]),
    (['a','b'],'a-b',[5,9]),
    (['a','b'],'b-a',[5,9]),
    (['a','b'],'a+b*3',[H,L]),
    (['a','b'],'(a+b)*3',[H,L]),
    (['a','b','c','d','e','f'],'a-b-c-d-e-f',[1,2,3,4,5,U64]),
    (['a','b','c','d','e','f'],'a+b-c*d&e|f^a',[0x1111,0x2222,0x3333,0xff00ff00ff00ff00,0x0f0f,0xaaaa5555aaaa5555]),
    (['a'],'a^0b1010_1010',[0xffff]),
    (['a'],'a&0x00FF_00FF_00FF_00FF|0x8000_0000_0000_0000',[U64]),
    (['a','b'],'a*b+0xDEADBEEFCAFEBABE',[0x123456789abcdef,0xfedcba987654321]),
    (['a'],'a+1_000_000_007*2',[U64-3]),
    ([],'0-1',[]),
    (['a','b','c'],'(a|b)^(c&0xF0F0)',[0x0f0f,0xf0f0f0f0,0xffffffff]),
    (['a','b'],'(((a+1)*2-3)^4)&0xFF|b',[7,H]),
    (['a','b','c','d','e','f'],'a+b*c-d^e&f|1+2*3-4^5&6',[10,20,30,40,50,60]),
    (['a'],'a+a*a-a',[U64]),
    ([],'0xdeadBEEF*0b1_1',[]),
]
NAMES=[(b'e',b'v%d'%k)for k in range(len(FIXTURES))]
NAMES[1]=(b'\xe4\xb8\xad',b'f'*64);NAMES[4]=(b'm'*64,b'\x00\xff');NAMES[0]=(b'W',b'x')
# UNSUPPORTED constructs (all parse with the real parser; lower must refuse them without writing).
UNSUPPORTED_EXPRESSIONS=['-a','!a','~a','&a','a/b','a%b','a<<1','a>>1','a<b','a==b','a&&b','a||b','f(a)','a as u64','true','null','a.b','a[0]',
                         '"s"','[a]','a orelse b','a+(-b)','a*(b/c)']


def decode_tokens(data,count):
    return [struct.unpack_from('<7Q',data,56*i)for i in range(count)]


def decode_nodes(data,count):
    return [list(struct.unpack_from('<8Q',data,64*i))for i in range(count)]


def encode_tokens(tokens):
    return b''.join(struct.pack('<7Q',*t)for t in tokens)


def encode_nodes(nodes):
    return b''.join(struct.pack('<8Q',*n)for n in nodes)


class U64ExpressionIrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=ROOT/'build/bootstrap_u64_expression_ir'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.records=[]
        cls.inputs=cls.digests()
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.executables=cls.build_all('good',SOURCE.read_text(encoding='utf-8'),C48.read_text(encoding='utf-8'))
        cls.lexed={}

    @staticmethod
    def digests():
        return {p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,DOC,*DEPENDENCIES,Path(__file__)]}

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=240)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build_all(cls,name,ir_text,c48_text):
        """Stage the production module, the lexer/expression/bigint baseline and the C48 closure read-only (C48 optionally a
        bad copy), then build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        (root/'bootstrap/nasm_u64_function.dg').write_text(c48_text,encoding='utf-8')
        (root/'bootstrap/u64_expression_ir.dg').write_text(ir_text,encoding='utf-8')
        (root/'probe/c51_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/c51_export.dg',roots=[root],mode=mode)
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

    # ---------------------------------------------------------------- harness protocol
    def run_harness(self,exe,commands,label):
        """commands: list of (header16, payload bytes). Returns the raw stdout after the preflight count."""
        payload=bytearray(struct.pack('<Q',len(commands)))
        for header,body in commands:payload.extend(struct.pack('<16Q',*header));payload.extend(body)
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],PREFLIGHTS)
        return run.stdout,8

    def lex_all(self,exe,sources,label):
        data,at=self.run_harness(exe,[([2,len(s)]+[0]*14,s)for s in sources],label);out=[]
        for s in sources:
            status,count=struct.unpack_from('<2Q',data,at);at+=16
            tokens=decode_tokens(data[at:],count);at+=56*count
            self.assertEqual(status,0,('lex',s));out.append(tokens)
        self.assertEqual(at,len(data));return out

    def pipe_header(self,source,start,ptoks,cap,flags,module,item):
        pt=list(ptoks)+[0]*(6-len(ptoks))
        return [0,len(source),start,len(ptoks)]+pt+[cap,flags,len(module),len(item),0,0]

    def pipe_all(self,exe,cases,label):
        """cases: (source, start, parameter token indexes, cap, flags, module, item). Returns one dict per case."""
        cmds=[(self.pipe_header(*c),c[0]+c[5]+c[6])for c in cases]
        data,at=self.run_harness(exe,cmds,label);out=[]
        for c in cases:
            h=struct.unpack_from('<16Q',data,at);at+=128
            r=dict(lex=h[0],tokens=h[1],parse=h[2],root=h[3],used=h[4],next=h[5],lower=h[6],lower_valid=h[7],ic=h[8],slots=h[9],rs=h[10],
                   emit=h[11],emit_len=h[12],emit_valid=h[13],protected=h[14],ro_same=h[15])
            r['token_list']=decode_tokens(data[at:],h[1]);at+=56*h[1]
            r['node_list']=decode_nodes(data[at:],h[4]if h[2]==0 else 0);at+=64*(h[4]if h[2]==0 else 0)
            n=h[8]if(h[6]==0 and h[11]!=9)else 0
            r['ir']=[struct.unpack_from('<5Q',data,at+40*i)for i in range(n)];at+=40*n
            r['text']=data[at:at+h[12]];at+=h[12];out.append(r)
        self.assertEqual(at,len(data));return out

    def raw_all(self,exe,cases,label):
        """cases: (source, tokens, nodes, root, parameter tokens, cap, flags). Returns one dict per case."""
        cmds=[]
        for s,t,d,root,pt,cap,flags in cases:
            cmds.append(([1,len(s),len(t),len(d),root,len(pt),cap,flags]+list(pt)+[0]*(7-len(pt))+[0],s+encode_tokens(t)+encode_nodes(d)))
        data,at=self.run_harness(exe,cmds,label);out=[]
        for _ in cases:
            status,valid,ic,slots,rs,protected=struct.unpack_from('<6Q',data,at);at+=48
            n=ic if status==0 else 0
            out.append(dict(status=status,valid=valid,ic=ic,slots=slots,rs=rs,protected=protected,
                            ir=[struct.unpack_from('<5Q',data,at+40*i)for i in range(n)]));at+=40*n
        self.assertEqual(at,len(data));return out

    # ---------------------------------------------------------------- fixtures through the real pipeline
    def fixture_cases(self,exe,label,fixtures=None,names=None,cap=24,flags=0):
        fixtures=FIXTURES if fixtures is None else fixtures;names=NAMES if names is None else names
        sources=[fixture_source(p,e).encode()for p,e,_ in fixtures]
        tokens=self.lex_all(exe,sources,label+'-lex')
        cases=[]
        for (p,e,a),s,t,(m,it) in zip(fixtures,sources,tokens,names):
            params,start=locate(t);self.assertEqual([s[t[i][1]:t[i][2]].decode()for i in params],p)
            cases.append((s,start,params,cap,flags,m,it))
        return cases

    def expected(self,params,expr):
        tree=py_parse(py_tokens(expr));program,slots,rs=py_ir(tree,params);return tree,program,slots,rs

    def check_good(self,fixtures,results,label,names=None):
        names=NAMES if names is None else names
        for k,((p,e,a),r,(m,it)) in enumerate(zip(fixtures,results,names)):
            tree,program,slots,rs=self.expected(p,e)
            self.assertEqual((r['lex'],r['parse'],r['lower'],r['emit']),(0,0,OK,OK),(label,k,e,r))
            self.assertEqual(r['lower_valid'],1,(label,k,'lower guards/atomicity'))
            self.assertEqual(r['ir'],program,(label,k,e,'IR'))
            self.assertEqual((r['ic'],r['slots'],r['rs']),(len(program),slots,rs),(label,k,e,'result'))
            self.assertEqual(r['text'],expected_text(m,it,len(p),slots,program,rs),(label,k,e,'text'))
            self.assertEqual(r['emit_valid'],1,(label,k,'emit guards'))
        return results

    # ---------------------------------------------------------------- native bridge
    def native_run(self,texts,vectors,label):
        """All generated functions go in one file. Each hand-written SysV stub saves the host's callee-saved registers, then
        stores the observation-area address and a host stack anchor in independent static memory (no register under test
        holds either). It plants known values in every callee-saved register (rbx included), the arguments (junk in unused
        argument registers) and a stack canary, and really calls the generated function. After the return it first parks
        RAX in static memory, reloads the observation address from static memory, records RAX, RSP and every callee-saved
        register exactly as returned, reads the canary through the saved anchor, then restores RSP from the anchor and the
        host's registers from its own pushes before returning. All assertions run afterwards in Python.
        vectors: (module, item, parameter count, argument values, expected value)."""
        stub=['bits 64','section .data','align 8','observation: dq 0','host_anchor: dq 0','parked_rax: dq 0','section .text']
        for k,(m,it,p,args,_) in enumerate(vectors):
            stub+=['global v%d'%k,'v%d:'%k,'push rbx','push rbp','push r12','push r13','push r14','push r15','sub rsp, 8']
            stub+=['mov [rel observation], rdi','mov [rel host_anchor], rsp','mov r11, rdi']
            stub+=['mov rax, 0x%x'%CANARY,'mov [rsp], rax','mov [r11+%d], rsp'%(8*RSP_BEFORE),
                   'mov rax, rsp','and rax, 15','mov [r11+%d], rax'%(8*ALIGN),'mov rax, 0x%x'%CALLER['rbx'],'mov [r11+%d], rax'%(8*RBX_BEFORE)]
            stub+=['mov %s, 0x%x'%(r,v)for r,v in CALLER.items()]
            stub+=['mov %s, 0x%x'%(REGS[i],args[i]if i<p else JUNK|i)for i in range(6)]+['mov rax, 0x%x'%JUNK,'call '+symbol(m,it)]
            stub+=['mov [rel parked_rax], rax','mov rax, [rel observation]',
                   'mov [rax+%d], rsp'%(8*RSP_AFTER),'mov [rax+%d], rbx'%(8*RBX_AFTER),'mov [rax+%d], rbp'%(8*RBP_AFTER)]
            stub+=['mov [rax+%d], r%d'%(8*(R12_AFTER+j),12+j)for j in range(4)]
            stub+=['mov rcx, [rel parked_rax]','mov [rax+%d], rcx'%(8*RAX),
                   'mov rcx, [rel host_anchor]','mov rcx, [rcx]','mov [rax+%d], rcx'%(8*CANARY_AFTER)]
            stub+=['mov rsp, [rel host_anchor]','add rsp, 8','pop r15','pop r14','pop r13','pop r12','pop rbp','pop rbx','ret']
        for text in texts:stub+=text.decode('ascii').rstrip('\n').split('\n')
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','#define STATE %d\n'%STATE+'\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(vectors))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(vectors))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],label+'-native-link')
        run=subprocess.run([str(exe)],capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        self.assertEqual(len(run.stdout),8*STATE*len(vectors))
        for k,(m,it,p,args,want) in enumerate(vectors):
            got=struct.unpack_from('<%dQ'%STATE,run.stdout,8*STATE*k)
            self.assertEqual(got[ALIGN],0,(label,k,'caller rsp aligned before call'))
            self.assertEqual(got[RAX],want,(label,k,'native rax',it))
            self.assertEqual(got[RSP_AFTER],got[RSP_BEFORE],(label,k,'native rsp balanced across call/ret'))
            self.assertEqual(got[RBX_BEFORE],CALLER['rbx'],(label,k,'planted rbx recorded'))
            self.assertEqual(got[RBX_AFTER],CALLER['rbx'],(label,k,'native rbx preserved'))
            self.assertEqual((got[RBP_AFTER],*got[R12_AFTER:R12_AFTER+4]),tuple(v for r,v in CALLER.items()if r!='rbx'),(label,k,'native rbp/r12..r15 preserved'))
            self.assertEqual(got[CANARY_AFTER],CANARY,(label,k,'caller stack canary'))

    def native_vectors(self,results):
        out=[]
        for (p,e,a),r,(m,it) in zip(FIXTURES,results,NAMES):
            env=dict(zip(p,a));out.append((m,it,len(p),a,py_eval(py_parse(py_tokens(e)),env)))
        return out

    # ---------------------------------------------------------------- tests
    def test_real_pipeline_exact_ir_text_and_capacity(self):
        self.assertLessEqual(len(FIXTURES),24)
        for mode,exe in self.executables.items():
            cases=self.fixture_cases(exe,'pipe-'+mode,flags=2)
            results=self.pipe_all(exe,cases,'pipe-'+mode)
            self.check_good(FIXTURES,results,mode)
            for r in results:
                self.assertEqual((r['protected'],r['ro_same']),(1,1),(mode,'read-only copies'))
            # the parser's own workspace contract, observed separately: a syntax error fails in parse, lower never runs
            bad=self.pipe_all(exe,[(b'fn f(a:u64)u64{return a+;}',cases[2][1],[cases[2][2][0]],24,0,b'm',b'f')],'parse-fail-'+mode)[0]
            self.assertNotEqual(bad['parse'],0);self.assertEqual((bad['lower'],bad['emit']),(0,9),'lower must not run after a parse failure')
            # exact capacity / short / zero / spare tail, with the out area and Result guarded
            sub=[(k,f)for k,f in enumerate(FIXTURES)]
            capacity_cases=[];expect=[]
            for k,f in sub:
                ic=len(self.expected(f[0],f[1])[1]);c=cases[k]
                for cap,status in ((ic,OK),(ic+5,OK),(ic-1,CAPACITY),(0,CAPACITY)):
                    if cap<0 or (status==CAPACITY and ic==0):continue
                    capacity_cases.append((c[0],c[1],c[2],cap,0,c[5],c[6]));expect.append((k,cap,status))
            res=self.pipe_all(exe,capacity_cases,'capacity-'+mode)
            for (k,cap,status),r in zip(expect,res):
                self.assertEqual(r['lower'],status,(mode,k,cap));self.assertEqual(r['lower_valid'],1,(mode,k,cap,'guards/atomicity'))
                if status==OK:
                    program=self.expected(FIXTURES[k][0],FIXTURES[k][1])[1];self.assertEqual(r['ir'],program,(mode,k,cap))
                else:self.assertEqual((r['emit'],r['ic']),(9,0),(mode,k,cap,'nothing emitted after CAPACITY'))
            # the maximum tree really is 23 nodes
            big=FIXTURES[17];self.assertEqual(results[17]['used'],23);self.assertEqual(len(self.expected(big[0],big[1])[1]),17)
            self.assertEqual(results[17]['slots'],23)
        self.records.append(dict(test='real-pipeline-ir-text-capacity',fixtures=len(FIXTURES),capacity_cases=len(capacity_cases),modes=2,preflights_per_native=PREFLIGHTS,passed=True))

    def test_native_call_ret_of_lowered_functions(self):
        vectors_per_mode=len(FIXTURES);self.assertLessEqual(vectors_per_mode,24)
        for mode,exe in self.executables.items():
            results=self.check_good(FIXTURES,self.pipe_all(exe,self.fixture_cases(exe,'native-'+mode),'native-pipe-'+mode),mode)
            self.native_run([r['text']for r in results],self.native_vectors(results),'native-'+mode)
        self.records.append(dict(test='native-call-ret',vectors_per_mode=vectors_per_mode,modes=2,formats=['elf64','win64'],passed=True))

    def test_unsupported_and_invalid_inputs_through_the_real_parser(self):
        for mode,exe in self.executables.items():
            fixtures=[(['a','b'],e,[0,0])for e in UNSUPPORTED_EXPRESSIONS]
            sources=[fixture_source(p,e).encode()for p,e,_ in fixtures]
            tokens=self.lex_all(exe,sources,'unsupported-lex-'+mode);cases=[]
            for (p,e,_),s,t in zip(fixtures,sources,tokens):
                params,start=locate(t);cases.append((s,start,params,24,2,b'm',b'f'))
            for e,r in zip(UNSUPPORTED_EXPRESSIONS,self.pipe_all(exe,cases,'unsupported-'+mode)):
                self.assertEqual((r['parse'],r['lower']),(0,UNSUPPORTED),(mode,e,r));self.assertEqual((r['lower_valid'],r['ro_same'],r['emit']),(1,1,9),(mode,e))
            # INVALID: unknown name, duplicate parameter, bad literals, bad parameter tokens, too many nodes
            def src(p,e):return fixture_source(p,e).encode()
            invalid=[(['a'],'a+z',None),(['a','a'],'a+a','dup'),(['a'],'a+18446744073709551616',None),(['a'],'a+0x1_0000_0000_0000_0000',None),
                     (['a'],'a+'+'1'*257,None),(['a'],'a+0x1_FFFF_FFFF_FFFF_FFFF',None),(['a'],'0b'+'1'*65+'+a',None),
                     (['a'],'+'.join(['a']*14).replace('+','+1*'),None)]
            ss=[src(p,e)for p,e,_ in invalid];toks=self.lex_all(exe,ss,'invalid-lex-'+mode);cases=[]
            for (p,e,kind),s,t in zip(invalid,ss,toks):
                params,start=locate(t);cases.append((s,start,params,24,2,b'm',b'f'))
            for (p,e,kind),r in zip(invalid,self.pipe_all(exe,cases,'invalid-'+mode)):
                self.assertEqual((r['parse'],r['lower']),(0,INVALID),(mode,e));self.assertEqual((r['lower_valid'],r['ro_same'],r['emit']),(1,1,9),(mode,e))
            # parameter token problems with real tokens: not an identifier, index == token count, far out of range
            s=src(['a','b'],'a-b');t=self.lex_all(exe,[s],'ptok-lex-'+mode)[0];params,start=locate(t)
            colon=next(i for i,x in enumerate(t)if x[0]==T_COLON)
            cases=[(s,start,[params[0],colon],24,0,b'm',b'f'),(s,start,[params[0],params[1]],24,0,b'm',b'f'),
                   (s,start,[params[0],len(t)],24,0,b'm',b'f'),(s,start,[params[0],999],24,0,b'm',b'f'),
                   (s,start,[params[0],len(t)-1],24,0,b'm',b'f')]            # the last one is the EOF token: empty spelling
            got=self.pipe_all(exe,cases,'ptok-'+mode)
            self.assertEqual([r['lower']for r in got],[INVALID,OK,INVALID,INVALID,INVALID],mode)
            for r in got:self.assertEqual(r['lower_valid'],1)
        self.records.append(dict(test='unsupported-invalid-real-parser',unsupported=len(UNSUPPORTED_EXPRESSIONS),invalid=len(invalid),modes=2,passed=True))

    def test_hand_mutated_trees_tokens_and_descriptors(self):
        """Real lexer/parser output for 'a-b*3+c', then field-by-field corruption fed straight into lower: INVALID/UNSUPPORTED,
        nothing written, inputs unchanged. Never executes any machine code."""
        for mode,exe in self.executables.items():
            s=fixture_source(['a','b','c'],'a-b*3+c').encode()
            t=self.lex_all(exe,[s],'mut-lex-'+mode)[0];params,start=locate(t)
            base=self.pipe_all(exe,[(s,start,params,24,0,b'm',b'f')],'mut-base-'+mode)[0];self.assertEqual(base['lower'],OK)
            tokens=base['token_list'];nodes=[list(n)for n in base['node_list']];root=base['root'];nn=len(nodes)
            def find(kind,skip=0):return [i for i,n in enumerate(nodes)if n[0]==kind][skip]
            binary=find(N_BINARY);integer=find(N_INTEGER);name=find(N_NAME);ident_tok=params[0]
            int_tok=next(i for i,x in enumerate(tokens)if x[0]==T_INT)
            plus=nodes[root][1]
            def mutate(fn,toks=None,src=None,roots=None,ptoks=None,cap=24):
                nd=[list(n)for n in nodes];tk=[list(x)for x in tokens];sc=bytearray(s)
                fn(nd,tk,sc);return (bytes(sc),[tuple(x)for x in tk],[tuple(x)for x in nd],root if roots is None else roots,params if ptoks is None else ptoks,cap,0)
            def set_node(i,j,v):
                def f(nd,tk,sc):nd[i][j]=v
                return f
            def set_tok(i,j,v):
                def f(nd,tk,sc):tk[i][j]=v
                return f
            ntok=len(tokens)
            invalid=[
                ('node token out of range',mutate(set_node(name,1,ntok))),
                ('node token huge',mutate(set_node(name,1,NONE))),
                ('child a out of range',mutate(set_node(binary,3,nn))),
                ('child b out of range',mutate(set_node(root,4,NONE))),
                ('cycle (child is itself)',mutate(set_node(root,3,root))),
                ('shared child',mutate(lambda nd,tk,sc:nd[root].__setitem__(4,nd[root][3]))),
                ('unreachable extra node',mutate(lambda nd,tk,sc:nd.append(list(nd[integer])))),
                ('leaf next set',mutate(set_node(name,6,0))),
                ('flags 2',mutate(set_node(integer,7,2))),
                ('integer op',mutate(set_node(integer,2,1))),
                ('integer child a',mutate(set_node(integer,3,0))),
                ('name child b',mutate(set_node(name,4,0))),
                ('binary c',mutate(set_node(binary,5,0))),
                ('name on an integer token',mutate(set_node(name,1,int_tok))),
                ('integer on an identifier token',mutate(set_node(integer,1,ident_tok))),
                ('binary op differs from token kind',mutate(set_node(root,2,1069 if plus and tokens[nodes[root][1]][0]==1067 else 1067))),
                ('binary spelling differs',mutate(lambda nd,tk,sc:sc.__setitem__(tokens[nodes[root][1]][1],ord('x')))),
                ('literal spelling not a number',mutate(lambda nd,tk,sc:sc.__setitem__(tokens[int_tok][1],ord('g')))),
                ('last token not EOF',mutate(set_tok(ntok-1,0,T_IDENT))),
                ('EOF in the middle',mutate(set_tok(0,0,T_EOF))),
                ('token start > end',mutate(set_tok(2,1,tokens[2][2]+1))),
                ('token end > source',mutate(set_tok(2,2,len(s)+1))),
                ('token overlap',mutate(set_tok(3,1,tokens[2][2]-1))),
                ('root == nodes.len',mutate(lambda nd,tk,sc:None,roots=nn)),
                ('root huge',mutate(lambda nd,tk,sc:None,roots=NONE)),
                ('parameter token out of range',mutate(lambda nd,tk,sc:None,ptoks=[params[0],ntok])),
                ('duplicate parameter token',mutate(lambda nd,tk,sc:None,ptoks=[params[0],params[0]])),
                ('25 nodes',mutate(lambda nd,tk,sc:nd.extend([list(nd[integer])]*(25-len(nd))))),
                ('257 tokens',mutate(lambda nd,tk,sc:tk.extend([list(tk[-1])]*(257-len(tk))))),
                ('7 parameters',mutate(lambda nd,tk,sc:None,ptoks=params+[params[0]]*4)),
                ('source 4097 bytes',(s+b' '*(4097-len(s)),[tuple(x)for x in tokens],[tuple(x)for x in nodes],root,params,24,0)),
            ]
            unsupported=[
                ('unary node',mutate(set_node(integer,0,N_UNARY))),
                ('division operator',mutate(set_node(root,2,1071))),
                ('unsupported wins over a later shape error',mutate(lambda nd,tk,sc:(nd[integer].__setitem__(0,N_UNARY),nd[binary].__setitem__(6,0)))),
                ('unsupported wins over an unknown parameter',mutate(lambda nd,tk,sc:nd[integer].__setitem__(0,N_UNARY),ptoks=[params[0]])),
            ]
            labeled=invalid+unsupported
            got=self.raw_all(exe,[c for _,c in labeled],'mutated-'+mode)
            for (label,_),r in zip(invalid,got):self.assertEqual((r['status'],r['valid']),(INVALID,1),(mode,label,r))
            for (label,_),r in zip(unsupported,got[len(invalid):]):self.assertEqual((r['status'],r['valid']),(UNSUPPORTED,1),(mode,label,r))
            # a well-formed RAW input succeeds, also from read-only memory, and matches the independent IR
            good=mutate(lambda nd,tk,sc:None);ro=good[:6]+(2,)
            for c in (good,ro):
                r=self.raw_all(exe,[c],'mutated-good-'+mode)[0];program,slots,rs=py_ir(py_parse(py_tokens('a-b*3+c')),['a','b','c'])[0:3]
                self.assertEqual((r['status'],r['valid'],r['protected'],r['ir'],r['slots'],r['rs']),(OK,1,1,program,slots,rs))
            # read-only protection must succeed on the failing inputs too
            r=self.raw_all(exe,[invalid[0][1][:6]+(2,)],'mutated-ro-'+mode)[0];self.assertEqual((r['status'],r['protected'],r['valid']),(INVALID,1,1))
        self.records.append(dict(test='hand-mutated-inputs',invalid=len(invalid),unsupported=len(unsupported),modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8');c48=C48.read_text(encoding='utf-8')
        emit_line='out[written]=f.Instruction{operation:operation(n.op),destination:next,left:slot_of[n.a],right:slot_of[n.b],immediate:0};'
        unknown='if !found{return INVALID;}'
        capacity='if out.len<count{return CAPACITY;}'
        for x in (emit_line,unknown,capacity):self.assertEqual(source.count(x),1,x)
        # 1. SUB sources swapped inside lower: everything builds and runs normally; the returned value is wrong.
        swapped=source.replace(emit_line,'var l=slot_of[n.a];var r=slot_of[n.b];if n.op==1069{l=slot_of[n.b];r=slot_of[n.a];}\n    '
            'out[written]=f.Instruction{operation:operation(n.op),destination:next,left:l,right:r,immediate:0};',1)
        subs=[k for k,(p,e,a)in enumerate(FIXTURES)if '-' in e and len(p)>=1 and any(x[0]==SUB and x[2]!=x[3]for x in self.expected(p,e)[1])]
        self.assertGreaterEqual(len(subs),4)
        sub_fixtures=[FIXTURES[k]for k in subs];sub_names=[NAMES[k]for k in subs]
        sub_vectors=[v for k,v in enumerate(self.native_vectors([None]*len(FIXTURES)))if k in subs]
        for mode,exe in self.executables.items():
            res=self.check_good(sub_fixtures,self.pipe_all(exe,self.fixture_cases(exe,'bad-sub-good-'+mode,sub_fixtures,sub_names),'bad-sub-good-'+mode),mode,sub_names)
            self.native_run([r['text']for r in res],sub_vectors,'bad-sub-good-'+mode)
        for mode,exe in self.build_all('bad-sub-swapped',swapped,c48).items():
            res=self.pipe_all(exe,self.fixture_cases(exe,'bad-sub-lex-'+mode,sub_fixtures,sub_names),'bad-sub-'+mode)
            for r in res:self.assertEqual((r['lower'],r['emit']),(OK,OK))
            with self.assertRaisesRegex(AssertionError,'native rax'):self.native_run([r['text']for r in res],sub_vectors,'bad-sub-'+mode)
        self.records.append(dict(test='bad-sub-swapped',vectors=len(subs),compiled=True,linked=True,native_executed=True,modes=2,rejected_by='native rax'))
        # 2. Unknown NAME silently mapped to parameter slot 0: only fixtures with a safe parameter slot, rejected by status.
        mapped=source.replace(unknown,'if !found{slot_of[i]=0;}',1)
        names_bad=[(['a'],'a+z'),(['a','b'],'a-q*b'),(['a','b','c'],'zz|a')]
        def unknown_cases(exe,label):
            fx=[(p,e,[])for p,e in names_bad];ss=[fixture_source(p,e).encode()for p,e in names_bad];toks=self.lex_all(exe,ss,label+'-lex');cs=[]
            for (p,e),s,t in zip(names_bad,ss,toks):
                params,start=locate(t);cs.append((s,start,params,24,0,b'm',b'f'))
            return cs
        for mode,exe in self.executables.items():
            for r in self.pipe_all(exe,unknown_cases(exe,'bad-name-good-'+mode),'bad-name-good-'+mode):self.assertEqual((r['lower'],r['lower_valid']),(INVALID,1))
        for mode,exe in self.build_all('bad-unknown-name-mapped',mapped,c48).items():
            for i,c in enumerate(unknown_cases(exe,'bad-name-lex-'+mode)):
                r=self.pipe_all(exe,[c],'bad-name-%s-%d'%(mode,i))[0]
                with self.assertRaisesRegex(AssertionError,'1 != 0|0 != 1'):self.assertEqual(r['lower'],INVALID)
        self.records.append(dict(test='bad-unknown-name-mapped',compiled=True,native_executed=True,modes=2,rejected_by='status (OK instead of INVALID)'))
        # 3. Capacity shortfall that writes into out / Result first: rejected by the atomicity guards.
        early_ir=source.replace(capacity,'if out.len<count{if out.len!=0{out[0]=f.Instruction{operation:f.CONST,destination:0,left:0,right:0,immediate:1};}return CAPACITY;}',1)
        early_result=source.replace(capacity,'if out.len<count{*result=Result{instruction_count:count,slot_count:1,return_slot:0};return CAPACITY;}',1)
        k=next(i for i,(p,e,a)in enumerate(FIXTURES)if len(self.expected(p,e)[1])>=2)
        def short_case(exe,label):
            c=self.fixture_cases(exe,label,[FIXTURES[k]],[NAMES[k]]);ic=len(self.expected(FIXTURES[k][0],FIXTURES[k][1])[1])
            return [(c[0][0],c[0][1],c[0][2],ic-1,0,c[0][5],c[0][6])]
        for mode,exe in self.executables.items():
            r=self.pipe_all(exe,short_case(exe,'bad-early-good-'+mode),'bad-early-good-'+mode)[0];self.assertEqual((r['lower'],r['lower_valid']),(CAPACITY,1))
        for name,text in (('bad-early-ir',early_ir),('bad-early-result',early_result)):
            for mode,exe in self.build_all(name,text,c48).items():
                r=self.pipe_all(exe,short_case(exe,name+'-lex-'+mode),name+'-'+mode)[0];self.assertEqual(r['lower'],CAPACITY)
                self.assertEqual(r['lower_valid'],0,(name,mode,'atomicity guard must catch the early write'))
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by='lower atomicity guards'))
        # 4. Callee-saved RBX not preserved by the emitted function (bad copy of the integrated C48: add rbx, 8 before ret).
        exit_piece='if ex.emit(U64_KIND,frame,0,8*(return_slot+1),0,slice_from_raw_parts(&buffer[0],CHUNK),&n)!=ex.OK{return false;}\n  at=n;'
        self.assertEqual(c48.count(exit_piece),1)
        tail=b'pop rbp\nadd rbx, 8\nret\n'
        clobber=c48.replace(exit_piece,exit_piece+'at-=4;put(buffer,&at,"add rbx, 8\\nret\\n");',1)
        for mode,exe in self.executables.items():
            res=self.check_good(FIXTURES,self.pipe_all(exe,self.fixture_cases(exe,'bad-rbx-good-'+mode),'bad-rbx-good-'+mode),mode)
            self.native_run([r['text']for r in res],self.native_vectors(res),'bad-rbx-good-'+mode)
        for mode,exe in self.build_all('bad-rbx-clobbered',source,clobber).items():
            res=self.pipe_all(exe,self.fixture_cases(exe,'bad-rbx-lex-'+mode),'bad-rbx-'+mode)
            for r in res:self.assertEqual((r['lower'],r['emit']),(OK,OK));self.assertTrue(r['text'].endswith(tail))
            with self.assertRaisesRegex(AssertionError,'native rbx preserved'):self.native_run([r['text']for r in res],self.native_vectors(res),'bad-rbx-'+mode)
        self.records.append(dict(test='bad-rbx-clobbered',vectors=len(FIXTURES),compiled=True,linked=True,native_executed=True,modes=2,
                                 rejected_by='native rbx preserved (rax and rsp assertions passed first)'))

    def test_alias_preflights_are_reachable(self):
        """Preflight sensitivity: a real Dong without the alias checks fails exactly preflights 24..33."""
        source=SOURCE.read_text(encoding='utf-8')
        start=source.index(' // Inputs may overlap each other;');end=source.index(' if root>=nodes.len{return INVALID;}')
        old=source[start:end];self.assertIn('overlap(op,on,pp,pn)',old);self.assertEqual(source.count(old),1)
        for mode,exe in self.executables.items():self.run_harness(exe,[],'alias-good-'+mode)
        for mode,exe in self.build_all('bad-no-alias',source.replace(old,'',1),C48.read_text(encoding='utf-8')).items():
            run=subprocess.run([str(exe)],input=struct.pack('<Q',0),capture_output=True,timeout=60)
            err=run.stderr.decode('ascii','replace');(self.work/('bad-no-alias-'+mode+'.stderr')).write_text(err,encoding='ascii')
            self.assertEqual(run.returncode,93,(mode,err))
            failed=[int(line.split()[2])for line in err.splitlines()if line.startswith('invalid preflight ')]
            self.assertEqual(failed,list(range(24,34)),(mode,err))
        self.records.append(dict(test='bad-no-alias',compiled=True,native_executed=True,modes=2,rejected_by='preflights 24..33'))


if __name__=='__main__':unittest.main()
