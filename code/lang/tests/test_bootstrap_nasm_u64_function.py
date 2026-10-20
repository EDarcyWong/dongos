"""Actual Dong whole SysV function from a restricted straight-line u64 IR (C48): exact text, ELF64/COFF assembly, real call/ret."""
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
WORKS=ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags




SOURCE=ROOT/'lang/bootstrap/nasm_u64_function.dg'
DOC=ROOT/'lang/bootstrap/nasm_u64_function.md'
# Integrated components and their whole read-only import closure (nothing else from lang is staged).
DEPENDENCIES=[ROOT/'lang/bootstrap'/(n+'.dg')for n in (
    'nasm_symbol','decimal_integer',                                        # CR3, CR4
    'nasm_function_frame',                                                  # CR11
    'nasm_sysv_incoming_args','sysv_integer_args','nasm_memory_operand',    # C37, C8, CR8
    'nasm_integer_memory_load','nasm_integer_memory_store',                 # CR12, CR13
    'nasm_integer_binary',                                                  # C23
    'nasm_sysv_function_exit','nasm_sysv_return_values','sysv_return_plan')]   # C42, C39, C14
OK,INVALID,CAPACITY=0,1,2
U64=2**64-1
H,L=0x8000000000000000,0x7fffffffffffffff
PREFLIGHTS=24
CONST,COPY,ADD,SUB,AND,OR,XOR,IMUL=range(8)
MNEMONIC={ADD:'add',SUB:'sub',AND:'and',OR:'or',XOR:'xor',IMUL:'imul'}
REGS=['rdi','rsi','rdx','rcx','r8','r9']
WRAPPER='''module probe.u64fn_export;
import bootstrap.nasm_u64_function as f;
export("dong_u64fn_emit") pub unsafe fn emit(m:*const u8,mn:usize,i:*const u8,inn:usize,parameters:usize,slots:usize,
 x:*const f.Instruction,xn:usize,return_slot:usize,out:*u8,no:usize,written:*usize)u64{unsafe{
 return f.emit(slice_from_raw_parts(m,mn),slice_from_raw_parts(i,inn),parameters,slots,slice_from_raw_parts(x,xn),return_slot,
  slice_from_raw_parts(out,no),written);
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
typedef struct{uint64_t operation,destination,left,right,immediate;}Ins;
extern uint64_t ABI dong_u64fn_emit(N,uint64_t,N,uint64_t,uint64_t,uint64_t,const Ins*,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
/* Descriptor/alias preflights. Every other field is legal (two distinct 4-byte names, two all-zero CONST instructions,
   0 parameters, 1 slot, return slot 0, out 4096 bytes, aligned written) so only the target check can reject it. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[8192],saved[8192];const unsigned total=24;unsigned failed=0;
 uint8_t*m=arena+64,*it=arena+192,*o=arena+1024;Ins*x=(Ins*)(arena+320);uint64_t*w=(uint64_t*)(arena+6144);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memset(m,'a',64);memset(it,'b',64);memset(x,0,2*sizeof(Ins));memcpy(saved,arena,sizeof(arena));
  N pm=m,pi=it;uint64_t lm=4,li=4,lx=1,lo=4096;const Ins*px=x;uint8_t*po=o;uint64_t*pw=w;
  switch(i){
   case 0:pw=NULL;break;                                                  /* written NULL */
   case 1:pw=(uint64_t*)(arena+6145);break;                               /* written odd */
   case 2:pw=(uint64_t*)(uintptr_t)(UINT64_MAX-7);po=NULL;lo=0;break;     /* written end overflow, legal empty out */
   case 3:po=(uint8_t*)(uintptr_t)(UINT64_MAX-2047);break;                /* out end overflow */
   case 4:po=NULL;break;                                                  /* NULL non-empty out */
   case 5:pm=NULL;break;case 6:pi=NULL;break;                             /* NULL non-empty names */
   case 7:pm=FAKE(UINT64_MAX-3);lm=8;break;case 8:pi=FAKE(UINT64_MAX-1);break;   /* name end overflows */
   case 9:px=NULL;break;                                                  /* NULL non-empty instructions */
   case 10:px=(const Ins*)(arena+324);break;                              /* misaligned instructions */
   case 11:px=(const Ins*)(uintptr_t)(UINT64_MAX-63);lx=2;break;          /* instructions end overflow */
   case 12:lx=UINT64_MAX/40+1;break;                                      /* count * 40 overflows */
   case 13:pw=(uint64_t*)o;break;                                         /* written on out prefix */
   case 14:pw=(uint64_t*)(o+4088);break;                                  /* written in out's unused tail */
   case 15:lm=64;pw=(uint64_t*)m;break;case 16:lm=64;pw=(uint64_t*)(m+56);break;   /* written on/in whole names */
   case 17:li=64;pw=(uint64_t*)it;break;case 18:li=64;pw=(uint64_t*)(it+56);break;
   case 19:lx=2;pw=(uint64_t*)x;break;case 20:lx=2;pw=(uint64_t*)x+9;break;      /* written on/in whole instruction array */
   case 21:lm=64;po=m+63;lo=8;break;case 22:li=64;po=it+63;lo=8;break;           /* out over each name's last byte */
   default:lx=2;po=(uint8_t*)x+79;lo=8;break;                             /* out over the array's last byte */
  }
  uint64_t s=dong_u64fn_emit(pm,lm,pi,li,0,1,px,lx,0,po,lo,pw);
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
  /* pool, module (off,len), item (off,len), instructions (off,count), flags, parameters, slots, return slot, capacity */
  uint64_t h[12];read_exact(h,sizeof(h));uint64_t pool=h[0],flags=h[7],cap=h[11];
  if(pool>8192||cap>16384)exit(94);
  uint8_t*in=malloc(pool+96),*copy=malloc(pool+1),*out=malloc(cap+64);static _Alignas(8) uint64_t meta[3];
  if(!in||!copy||!out||((uintptr_t)in&15))exit(95);
  memset(in,0xa5,pool+96);read_exact(in+32,pool);memcpy(copy,in+32,pool);
  uint8_t*base=in+32,*page=NULL;uint64_t pages=4096*4,protected_ok=1;
  if(flags&2){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,pool);protected_ok=ro_protect(page,pages);base=page;}
  const Ins*x=(flags&1)?NULL:(const Ins*)(base+h[5]);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=dong_u64fn_emit(base+h[1],h[2],base+h[3],h[4],h[8],h[9],x,h[6],h[10],cap?out+32:NULL,cap,written);
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


def symbol(module,item):
    """Independent CR3 expectation: __dong_m<hex module>_n<hex item>, two lowercase digits per byte."""
    return '__dong_m'+module.hex()+'_n'+item.hex()


def frame_of(slots):
    return (8*slots+15)//16*16


def expected_text(module,item,p,slots,program,rs):
    """Independent whole-function text model."""
    frame=frame_of(slots);off=lambda s:8*(s+1)
    lines=[symbol(module,item)+':','push rbp','mov rbp, rsp','sub rsp, %d'%frame]
    lines+=['mov qword [rbp - %d], %s'%(off(i),REGS[i])for i in range(p)]
    for op,d,l,r,imm in program:
        if op==CONST:lines.append('mov rax, %d'%imm)
        elif op==COPY:lines.append('mov rax, qword [rbp - %d]'%off(l))
        else:lines+=['mov rax, qword [rbp - %d]'%off(l),'mov rcx, qword [rbp - %d]'%off(r),'%s rax, rcx'%MNEMONIC[op]]
        lines.append('mov qword [rbp - %d], rax'%off(d))
    lines+=['mov rax, qword [rbp - %d]'%off(rs),'add rsp, %d'%frame,'pop rbp','ret']
    return ''.join(l+'\n'for l in lines).encode()


def interpret(p,slots,program,rs,args):
    """Independent u64 interpreter of the IR."""
    s=[None]*slots
    for i in range(p):s[i]=args[i]
    for op,d,l,r,imm in program:
        if op==CONST:v=imm
        elif op==COPY:v=s[l]
        else:
            a,b=s[l],s[r]
            v={ADD:a+b,SUB:a-b,AND:a&b,OR:a|b,XOR:a^b,IMUL:a*b}[op]&U64
        s[d]=v
    return s[rs]


def ins(op,d,l=0,r=0,imm=0):return (op,d,l,r,imm)


def big_program():
    """64 instructions over 32 slots touching every operation; returns into slot 31."""
    prog=[ins(CONST,2,imm=0x9e3779b97f4a7c15),ins(CONST,3,imm=U64)]
    k=4;ops=[ADD,SUB,AND,OR,XOR,IMUL,COPY]
    while len(prog)<63:
        op=ops[len(prog)%len(ops)];d=k%32 if k<32 else 4+(k*7)%28;a=(k*5)%min(k,32);b=(k*3+1)%min(k,32)
        prog.append(ins(op,d,a)if op==COPY else ins(op,d,a,b));k+=1
    prog.append(ins(ADD,31,0,1))
    return prog


# (module, item, parameters, slots, program, return slot, arguments)
VECTORS=[
    (b'W',b'x',0,1,[ins(CONST,0,imm=0x123456789abcdef0)],0,[]),                                    # 0 params, 1 slot, 1-byte names
    (b'v',b'id1',1,1,[],0,[0xfedcba9876543210]),                                                     # empty program returns the parameter
    (b'v',b'last6',6,6,[],5,[1,2,3,4,5,U64]),                                                        # 6 params, return the last
    (b'v',b'first6',6,6,[],0,[H,2,3,4,5,6]),
    (b'M'*64,bytes(range(64)),6,8,[ins(ADD,6,0,1),ins(SUB,7,6,2),ins(AND,6,7,3),ins(OR,7,6,4),ins(XOR,6,7,5),ins(IMUL,7,6,0)],7,
     [0x1111,0x2222,0x3333,0xff00ff00ff00ff00,0x0f0f,0xaaaa5555aaaa5555]),                           # every binary op, 64-byte names
    (b'v',b'wrap',2,3,[ins(ADD,2,0,1),ins(IMUL,2,2,1)],2,[U64,2]),                                    # add/mul wraparound
    (b'v',b'mulwrap',2,2,[ins(IMUL,0,0,1),ins(ADD,0,0,1)],0,[H|3,L]),
    (b'v',b'same',1,1,[ins(ADD,0,0,0),ins(IMUL,0,0,0),ins(XOR,0,0,0)],0,[0x123456789]),                 # left=right=destination
    (b'v',b'oldsub',2,2,[ins(SUB,0,1,0)],0,[5,3]),                                                   # destination read as right before write
    (b'v',b'oldsub2',2,2,[ins(SUB,1,1,0),ins(SUB,0,0,1)],0,[9,100]),
    (b'v',b'copies',3,4,[ins(COPY,3,2),ins(COPY,0,3),ins(COPY,2,1)],0,[1,2,3]),                       # copy chain, return first slot
    (b'v',b'consts',0,32,[ins(CONST,31,imm=U64),ins(CONST,0,imm=0),ins(XOR,31,31,0)],31,[]),           # 32 slots, return last slot
    (b'v',b'sub',2,3,[ins(SUB,2,0,1)],2,[5,9]),                                                       # non-commutative, wraps
    (b'v',b'subrev',2,3,[ins(SUB,2,1,0),ins(SUB,2,2,0)],2,[L,H]),
    (b'v',b'overwrite',6,8,[ins(CONST,0,imm=7),ins(ADD,5,5,0),ins(COPY,7,5),ins(OR,1,1,7)],1,[1,2,3,4,5,6]),   # parameter slots overwritten
    (b'v',b'big',2,32,big_program(),31,[0x0123456789abcdef,0xfedcba9876543210]),                     # 64 instructions, 32 slots
]


def layout(module,item,program):
    """Pool bytes: names with gaps, then the 40-byte instruction records at an 8-aligned offset."""
    pool=bytearray(module+b'\xa5'*(8-len(module)%8+8));io=len(pool);pool+=item+b'\xa5'*(8-len(item)%8+8)
    xo=len(pool);pool+=b''.join(struct.pack('<5Q',*x)for x in program)+b'\xa5'*8
    return bytes(pool),[(0,len(module)),(io,len(item)),(xo,len(program))]


class NasmU64FunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=ROOT/'build/bootstrap_nasm_u64_function'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
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
        (root/'bootstrap/nasm_u64_function.dg').write_text(text,encoding='utf-8')
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        (root/'probe/u64fn_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/u64fn_export.dg',roots=[root],mode=mode)
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

    @staticmethod
    def case(module,item,p,slots,program,rs,cap,status,flags=0):
        pool,spans=layout(module,item,program)
        if not program and flags&4:flags|=1                                       # empty program passed as NULL
        return (pool,spans,flags&3,p,slots,rs,cap,status)

    def emit(self,exe,cases,label):
        """cases: (pool, spans[3], flags, p, slots, rs, cap, status); flags bit0 = NULL instructions, bit1 = read-only page."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for pool,spans,flags,p,slots,rs,cap,_ in cases:
            payload.extend(struct.pack('<12Q',len(pool),*[v for s in spans for v in s],flags,p,slots,rs,cap));payload.extend(pool)
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
            self.assertEqual(guard,1,(label,index,'guard/atomicity',case[3:]))
            self.assertEqual(got,case[7],(label,index,'status',case[3:]))
            texts.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return texts

    def generate(self,exe,vectors,label):
        texts=self.emit(exe,[self.case(*v[:6],16384,OK,4)for v in vectors],label)
        for v,text in zip(vectors,texts):self.assertEqual(text,expected_text(*v[:6]),(label,v[:2]))
        return texts

    def native_run(self,texts,vectors,label):
        """All generated functions go in one file. Each hand-written SysV stub saves the host's callee-saved registers, then
        stores the observation-area address and a host stack anchor in independent static memory (no register under test
        holds either). It plants known values in every callee-saved register (rbx included), the arguments (junk in unused
        argument registers) and a stack canary, and really calls the generated function. After the return it first parks
        RAX in static memory, reloads the observation address from static memory, records RAX, RSP and every callee-saved
        register exactly as returned, reads the canary through the saved anchor, then restores RSP from the anchor and the
        host's registers from its own pushes before returning. All assertions run afterwards in Python."""
        stub=['bits 64','section .data','align 8','observation: dq 0','host_anchor: dq 0','parked_rax: dq 0','section .text']
        for k,(m,it,p,slots,program,rs,args) in enumerate(vectors):
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
        for k,(m,it,p,slots,program,rs,args) in enumerate(vectors):
            got=struct.unpack_from('<%dQ'%STATE,run.stdout,8*STATE*k)
            self.assertEqual(got[ALIGN],0,(label,k,'caller rsp aligned before call'))
            self.assertEqual(got[RAX],interpret(p,slots,program,rs,args),(label,k,'native rax',it))
            self.assertEqual(got[RSP_AFTER],got[RSP_BEFORE],(label,k,'native rsp balanced across call/ret'))
            self.assertEqual(got[RBX_BEFORE],CALLER['rbx'],(label,k,'planted rbx recorded'))
            self.assertEqual(got[RBX_AFTER],CALLER['rbx'],(label,k,'native rbx preserved'))
            self.assertEqual((got[RBP_AFTER],*got[R12_AFTER:R12_AFTER+4]),tuple(v for r,v in CALLER.items()if r!='rbx'),(label,k,'native rbp/r12..r15 preserved'))
            self.assertEqual(got[CANARY_AFTER],CANARY,(label,k,'caller stack canary'))

    def test_exact_text_capacity_invalid_and_read_only_inputs(self):
        cases=[]
        for k,v in enumerate(VECTORS):
            size=len(expected_text(*v[:6]))
            cases+=[self.case(*v[:6],size,OK,4|(2 if k%3==0 else 0)),self.case(*v[:6],size+9,OK),
                    self.case(*v[:6],size-1,CAPACITY,2 if k%2 else 0),self.case(*v[:6],0,CAPACITY)]
        # Longest possible text: 64-byte names, 6 parameters, 32 slots, 64 binary ops on the deepest slots, 20-digit CONST.
        longest=[ins(CONST,31,imm=U64),ins(CONST,30,imm=U64-1)]+[ins(IMUL,31,31,30 if j%2 else 31)for j in range(61)]+[ins(SUB,30,31,31)]
        big=(b'\xff'*64,b'\x00'*64,6,32,longest,31);size=len(expected_text(*big))
        self.assertLessEqual(size,268+35+156+64*95+52)
        cases+=[self.case(*big,size,OK,2),self.case(*big,size-1,CAPACITY),self.case(*big,size+100,OK)]
        # Overlapping names (item inside module), also read-only.
        pool=b'modulename'+b'\xa5'*6+struct.pack('<5Q',CONST,0,0,0,42)+b'\xa5'*8
        cases+=[(pool,[(0,6),(2,4),(16,1)],0,0,1,0,4096,OK),(pool,[(0,10),(0,10),(16,1)],2,0,1,0,4096,OK)]
        legal=dict(m=b'mod',it=b'fn',p=2,slots=4,prog=[ins(ADD,2,0,1)],rs=2)
        def bad(**kw):
            v=dict(legal);v.update(kw);return (v['m'],v['it'],v['p'],v['slots'],v['prog'],v['rs'])
        bads=[bad(m=b''),bad(it=b''),bad(m=b'm'*65),bad(it=b'f'*65),bad(p=7,slots=8),bad(slots=0,p=0,prog=[],rs=0),bad(slots=33),
              bad(p=3,slots=2,prog=[],rs=0),bad(prog=[ins(ADD,2,0,1)]*65),bad(rs=4),bad(rs=U64),
              bad(prog=[ins(8,2,0,1)]),bad(prog=[ins(U64,2)]),bad(prog=[ins(CONST,2,l=1)]),bad(prog=[ins(CONST,2,r=1)]),
              bad(prog=[ins(COPY,2,0,r=1)]),bad(prog=[ins(COPY,2,0,imm=1)]),bad(prog=[ins(COPY,2,4)]),bad(prog=[ins(ADD,2,0,1,imm=1)]),
              bad(prog=[ins(ADD,2,4,1)]),bad(prog=[ins(ADD,2,0,4)]),bad(prog=[ins(ADD,4,0,1)]),bad(prog=[ins(CONST,U64)]),
              bad(prog=[ins(COPY,2,3)]),bad(prog=[ins(XOR,2,0,3)]),bad(prog=[ins(ADD,3,3,0)],rs=3),         # read uninitialized
              bad(prog=[ins(CONST,3,imm=1)],rs=2),bad(prog=[],rs=2)]                                        # return slot never written
        for b in bads:cases+=[self.case(*b,4096,INVALID),self.case(*b,0,INVALID,2)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for c,text in zip(cases,texts):
                if c[7]==OK:
                    pool,spans=c[0],c[1];m=pool[spans[0][0]:sum(spans[0])];it=pool[spans[1][0]:sum(spans[1])]
                    prog=[struct.unpack_from('<5Q',pool,spans[2][0]+40*j)for j in range(spans[2][1])]
                    self.assertEqual(text,expected_text(m,it,c[3],c[4],prog,c[5]),(mode,c[3:6]))
                    self.assertTrue(all(b==10 or 32<=b<127 for b in text)and b'\n\n'not in text,(mode,'ASCII/LF'))
                    for word in (b'section',b'global',b'bits',b'extern'):self.assertNotIn(word,text,(mode,word))
        self.records.append(dict(test='exact-text-capacity-invalid-readonly',cases=len(cases),preflights_per_native=PREFLIGHTS,longest_bytes=size,modes=2,passed=True))

    def test_native_call_ret(self):
        self.assertLessEqual(len(VECTORS),24)
        self.assertTrue({0,1,6}<={v[2]for v in VECTORS}and{1,32}<={v[3]for v in VECTORS}and{0,64}<={len(v[4])for v in VECTORS})
        self.assertEqual({x[0]for v in VECTORS for x in v[4]},set(range(8)))
        self.assertTrue(any(v[5]==0 for v in VECTORS)and any(v[5]==v[3]-1 for v in VECTORS))
        self.assertTrue(any(x[0]>=ADD and x[2]==x[3]for v in VECTORS for x in v[4]))                # left = right
        self.assertTrue(any(x[0]>=ADD and x[1]in(x[2],x[3])for v in VECTORS for x in v[4]))          # reads old destination
        self.assertEqual(len({symbol(*v[:2])for v in VECTORS}),len(VECTORS))
        for mode,exe in self.executables.items():
            self.native_run(self.generate(exe,VECTORS,'vectors-'+mode),VECTORS,'native-'+mode)
        self.records.append(dict(test='native-call-ret',vectors_per_mode=len(VECTORS),functions_per_file=len(VECTORS),modes=2,formats=['elf64','win64'],passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        loads='if !load_slot(buffer,&at,RAX,x.left)||!load_slot(buffer,&at,RCX,x.right){return false;}'
        early='  if x.destination>=slot_count{return INVALID;}\n'
        capacity='if total>on{return CAPACITY;}'
        for s in (loads,early,capacity):self.assertEqual(source.count(s),1,s)
        # 1. SUB loads swapped: builds, links and runs normally; the returned value is wrong.
        swapped=source.replace(loads,'if !load_slot(buffer,&at,RAX,first(x.operation,x.left,x.right))'
            '||!load_slot(buffer,&at,RCX,second(x.operation,x.left,x.right)){return false;}',1).replace(
            'unsafe fn piece(','fn first(op:u64,l:usize,r:usize)usize{if op==SUB{return r;}return l;}\n'
            'fn second(op:u64,l:usize,r:usize)usize{if op==SUB{return l;}return r;}\nunsafe fn piece(',1)
        subs=[v for v in VECTORS if any(x[0]==SUB and x[2]!=x[3]for x in v[4])]
        self.assertGreaterEqual(len(subs),3)
        for mode,exe in self.executables.items():
            self.native_run(self.generate(exe,subs,'bad-sub-good-'+mode),subs,'bad-sub-good-'+mode)
        for mode,exe in self.build_all('bad-sub-swapped',swapped).items():
            texts=self.emit(exe,[self.case(*v[:6],16384,OK,4)for v in subs],'bad-sub-'+mode)
            with self.assertRaisesRegex(AssertionError,'native rax'):self.native_run(texts,subs,'bad-sub-'+mode)
        self.records.append(dict(test='bad-sub-swapped',vectors=len(subs),compiled=True,linked=True,native_executed=True,modes=2,rejected_by='native rax'))
        # 1b. Callee-saved RBX not preserved: the exit piece gets "add rbx, 8" right before its ret. It builds, links and
        # returns normally with the right RAX and a balanced RSP; only the recorded RBX value rejects it.
        exit_piece='if ex.emit(U64_KIND,frame,0,8*(return_slot+1),0,slice_from_raw_parts(&buffer[0],CHUNK),&n)!=ex.OK{return false;}\n  at=n;'
        self.assertEqual(source.count(exit_piece),1)
        clobber=source.replace(exit_piece,exit_piece+'at-=4;put(buffer,&at,"add rbx, 8\\nret\\n");',1)
        for mode,exe in self.executables.items():
            self.native_run(self.generate(exe,VECTORS,'bad-rbx-good-'+mode),VECTORS,'bad-rbx-good-'+mode)
        for mode,exe in self.build_all('bad-rbx-clobbered',clobber).items():
            texts=self.emit(exe,[self.case(*v[:6],16384,OK,4)for v in VECTORS],'bad-rbx-'+mode)
            self.assertTrue(all(t.endswith(b'pop rbp\nadd rbx, 8\nret\n')for t in texts),(mode,'injected before ret'))
            with self.assertRaisesRegex(AssertionError,'native rbx preserved'):self.native_run(texts,VECTORS,'bad-rbx-'+mode)
        self.records.append(dict(test='bad-rbx-clobbered',vectors=len(VECTORS),compiled=True,linked=True,native_executed=True,modes=2,
                                 rejected_by='native rbx preserved (rax and rsp assertions passed first)'))
        # 2. Destination marked initialized before the reads: an IR reading its own uninitialized destination is accepted.
        marked=source.replace(early,early+'  ready[x.destination]=1;\n',1)
        uninit=[self.case(b'v',b'u',2,4,[ins(ADD,3,3,0)],3,4096,INVALID),self.case(b'v',b'u',1,2,[ins(COPY,1,1)],1,4096,INVALID),
                self.case(b'v',b'u',0,2,[ins(CONST,0,imm=1),ins(XOR,1,0,1)],1,4096,INVALID)]
        for mode,exe in self.executables.items():self.emit(exe,uninit,'bad-early-mark-good-'+mode)
        for mode,exe in self.build_all('bad-early-mark',marked).items():
            for i,c in enumerate(uninit):
                with self.assertRaisesRegex(AssertionError,'status'):self.emit(exe,[c],'bad-early-mark-%s-%d'%(mode,i))
        self.records.append(dict(test='bad-early-mark',compiled=True,emitter_only=True,machine_code_executed=False,modes=2,rejected_by='status (OK instead of INVALID)'))
        # 3. Capacity failure that first publishes the function header (piece 0) into out.
        new='if total>on{if piece(0,module_name,item_name,parameter_count,frame,instructions,return_slot,scratch,&n){i=0;while i<n&&i<on{out[i]=buffer[i];i+=1;}}return CAPACITY;}'
        v=VECTORS[4];size=len(expected_text(*v[:6]));case=[self.case(*v[:6],size-1,CAPACITY)]
        for mode,exe in self.executables.items():self.emit(exe,case,'bad-early-header-good-'+mode)
        for mode,exe in self.build_all('bad-early-header',source.replace(capacity,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,case,'bad-early-header-'+mode)
        self.records.append(dict(test='bad-early-header',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))

    def test_input_alias_preflights_are_reachable(self):
        """Preflight sensitivity: a real Dong without the name/instruction alias checks fails exactly preflights 15..23."""
        source=SOURCE.read_text(encoding='utf-8')
        old=' if overlap(wp,8,mp,mn)||overlap(wp,8,ip,inn)||overlap(wp,8,xp,xn)||overlap(op,on,mp,mn)||overlap(op,on,ip,inn)||overlap(op,on,xp,xn){return INVALID;}\n'
        self.assertEqual(source.count(old),1)
        for mode,exe in self.executables.items():self.emit(exe,[],'alias-good-'+mode)
        for mode,exe in self.build_all('bad-no-input-alias',source.replace(old,'',1)).items():
            run=subprocess.run([str(exe)],input=struct.pack('<Q',0),capture_output=True,timeout=60)
            err=run.stderr.decode('ascii','replace');(self.work/('bad-no-input-alias-'+mode+'.stderr')).write_text(err,encoding='ascii')
            self.assertEqual(run.returncode,93,(mode,err))
            failed=[int(line.split()[2])for line in err.splitlines()if line.startswith('invalid preflight ')]
            self.assertEqual(failed,list(range(15,24)),(mode,err))
        self.records.append(dict(test='bad-no-input-alias',compiled=True,native_executed=True,modes=2,rejected_by='preflights 15..23'))


if __name__=='__main__':unittest.main()
