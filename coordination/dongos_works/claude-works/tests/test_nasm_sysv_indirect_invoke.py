"""Actual Dong SysV indirect call site from a frame slot (C34 setup + CR12 load + C27 call + C34 cleanup + C40 capture)."""
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

WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS
if not (ROOT/'lang').is_dir() and (WORKS/'project.json').is_file():
    source=Path(json.loads((WORKS/'project.json').read_text(encoding='utf-8'))['source_root'])
    ROOT=(WORKS/source).resolve() if not source.is_absolute() else source
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_sysv_indirect_invoke.dg'
DOC=WORKS/'claude-works/src/bootstrap/nasm_sysv_indirect_invoke.md'
# Integrated components and their whole read-only import closure (nothing else from lang is staged).
DEPENDENCIES=[ROOT/'lang/bootstrap'/(n+'.dg')for n in (
    'nasm_sysv_call_args','sysv_integer_args','nasm_memory_operand','decimal_integer',   # C34, C8, CR8, CR4
    'nasm_integer_memory_load','nasm_indirect_call',                                   # CR12, C27
    'nasm_sysv_capture_return','sysv_return_plan')]                                    # C40, C14
OK,INVALID,CAPACITY=0,1,2
U64=2**64-1
PREFLIGHTS=17
VOID,BOOL,U8,I8,U16,I16,U32,I32,UQ,IQ,PTR,PAIR=range(12)
ARGS=['rdi','rsi','rdx','rcx','r8','r9']
SENTINELS=[0x1212121212121212,0x1313131313131313,0x1414141414141414,0x1515151515151515]   # r12..r15
GUARDS=[0x4747474747474747,0x4848484848484848,0x4949494949494949]
DECOY=0x5a5a5a5a5a5a5a5a
WRAPPER='''module probe.indirect_export;
import bootstrap.nasm_sysv_indirect_invoke as v;
export("dong_indirect_emit") pub unsafe fn emit(k:*const u8,nk:usize,f:*const usize,nf:usize,target:usize,rk:u64,frame:usize,low:usize,high:usize,out:*u8,no:usize,written:*usize)u64{unsafe{
 return v.emit(slice_from_raw_parts(k,nk),slice_from_raw_parts(f,nf),target,rk,frame,low,high,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_indirect_emit(const uint8_t*,uint64_t,const uint64_t*,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,
                                       uint8_t*,uint64_t,uint64_t*);
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
#define FAKE(x) ((void*)(uintptr_t)(x))
/* Descriptor/alias preflights. Every other field is legal and full length before the snapshot: 16 scalar kinds,
   16 distinct slots 8..128, target slot 136, frame 256, a U64 return to [rbp - 144], out 2048 bytes. So each
   declared-tail alias is reachable on its own. Every failing preflight is reported, then exit 93. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[4096],saved[4096];const unsigned total=17;unsigned failed=0;
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  const uint8_t*k=arena;const uint64_t*f=(const uint64_t*)(arena+64);
  memset(arena,0,16);for(unsigned j=0;j<16;j++)((uint64_t*)(arena+64))[j]=8+8*j;
  memcpy(saved,arena,sizeof(arena));
  uint64_t nk=16,nf=16;uint8_t*o=arena+512;uint64_t ol=2048;uint64_t*w=(uint64_t*)(arena+3072);
  switch(i){
   case 0:w=NULL;break;                                                  /* written NULL */
   case 1:w=(uint64_t*)(arena+3073);break;                               /* written odd */
   case 2:w=FAKE(UINT64_MAX-7);o=NULL;ol=0;break;                        /* written end overflow, legal empty out */
   case 3:o=FAKE(UINT64_MAX-1023);break;                                 /* out end overflow */
   case 4:o=NULL;break;                                                  /* NULL non-empty out */
   case 5:k=NULL;break;                                                  /* NULL non-empty kinds */
   case 6:f=NULL;break;                                                  /* NULL non-empty offsets */
   case 7:k=FAKE(UINT64_MAX-7);break;                                    /* kinds end overflow */
   case 8:f=(const uint64_t*)(arena+68);break;                           /* offsets misaligned */
   case 9:nf=UINT64_MAX/8+1;break;                                       /* offsets length multiplication overflow */
   case 10:f=FAKE(UINT64_MAX-63);break;                                  /* offsets end overflow */
   case 11:w=(uint64_t*)(arena+8);break;                                 /* written in kinds' tail */
   case 12:w=(uint64_t*)(arena+184);break;                               /* written in offsets' tail */
   case 13:o=arena+8;ol=8;break;                                         /* out over kinds' last 8 bytes only */
   case 14:o=arena+184;ol=8;break;                                       /* out over offsets' last 8 bytes only */
   case 15:w=(uint64_t*)o;break;                                         /* written on out prefix */
   default:w=(uint64_t*)(o+2040);break;                                  /* written in out's unused tail */
  }
  uint64_t s=dong_indirect_emit(k,nk,f,nf,136,8,256,144,0,o,ol,w);
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
  uint64_t h[10];read_exact(h,sizeof(h));
  uint64_t nk=h[0],nf=h[1],target=h[2],rk=h[3],frame=h[4],low=h[5],high=h[6],cap=h[7],ro=h[8];(void)h[9];
  if(nk>64||nf>64||cap>4096)exit(94);
  uint8_t*in=malloc(1024),*copy=malloc(nk+nf*8+1),*out=malloc(cap+64);static _Alignas(8) uint64_t meta[3];
  if(!in||!copy||!out)exit(95);
  memset(in,0xa5,1024);read_exact(in+32,nk);read_exact(in+128,nf*8);
  const uint8_t*k=in+32;const uint64_t*f=(const uint64_t*)(in+128);
  uint8_t*page=NULL;uint64_t pages=4096*2,protected_ok=1;
  if(ro){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,in,1024);protected_ok=ro_protect(page,pages);
         k=page+32;f=(const uint64_t*)(page+128);}
  memcpy(copy,k,nk);memcpy(copy+nk,f,nf*8);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=dong_indirect_emit(nk?k:NULL,nk,nf?f:NULL,nf,target,rk,frame,low,high,cap?out+32:NULL,cap,written);
  uint64_t valid=protected_ok&&!memcmp(copy,k,nk)&&!memcmp(copy+nk,f,nf*8)&&
    filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(s)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={s,valid,s?0:*written};write_exact(response,24);write_exact(out+32,response[2]);
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
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
/* Commit the stack pages the 4 KiB stub frames will touch (no guard-page skipping). */
static __attribute__((noinline)) void commit_stack(void){volatile uint8_t pages[65536];for(unsigned i=0;i<sizeof(pages);i+=512)pages[i]=(uint8_t)i;}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 commit_stack();
 static uint64_t io[STATE+1];
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  memset(io,0,sizeof(io));read_exact(io,512*8);io[STATE]=0xa5a5a5a5a5a5a5a5ull;
  table[i](io);
  if(io[STATE]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  if(fwrite(io+512,8,STATE-512,stdout)!=STATE-512)exit(92);
 }return 0;
}
'''
# State layout (qwords): [0,512) frame image in; [512,1024) frame out; [1024,1027) guards above rbp;
# [1027,1033) callee rdi..r9; [1033,1049) callee stack words; 1049 callee entry rsp%16; 1050 callee marker;
# 1051 rsp before; 1052 rsp after; [1053,1057) r12..r15 after; 1057 target address; 1058 decoy address.
FRAME_OUT,GUARD_OUT,ARG_OUT,STACK_OUT,ENTRY_ALIGN,MARKER,RSP_BEFORE,RSP_AFTER,SAVED_OUT,FPTR,DPTR,STATE=\
    512,1024,1027,1033,1049,1050,1051,1052,1053,1057,1058,1059
WIDTH={BOOL:8,U8:8,I8:8,U16:16,I16:16,U32:32,I32:32,UQ:64,IQ:64,PTR:64,PAIR:64}
SIGNED={I8,I16,I32}
WIDEN={BOOL:'movzx r10, al',U8:'movzx r10, al',I8:'movsx r10, al',U16:'movzx r10, ax',I16:'movsx r10, ax',
       U32:'mov r10d, eax',I32:'movsxd r10, eax'}


def operand_rbp(offset):return '[rbp - %d]'%offset
def operand_rsp(index):return '[rsp]' if index==0 else '[rsp + %d]'%index
def words(kinds):return sum(1 if k==0 else 2 for k in kinds)


def oracle(kinds):
    """Independent SysV INTEGER placement: (register words [(reg, word)], stack words [word], stack_bytes)."""
    free=list(ARGS);regs,stack=[],[];word=0
    for k in kinds:
        need=1 if k==0 else 2
        if len(free)>=need:
            for _ in range(need):regs.append((free.pop(0),word));word+=1
        else:
            for _ in range(need):stack.append(word);word+=1
    return regs,stack,-(-8*len(stack)//16)*16


def expected_text(kinds,offsets,target,rk,low,high):
    """Independent text model: setup, target load, call r11, cleanup, capture."""
    regs,stack,bytes_=oracle(kinds);lines=[]
    if bytes_:lines.append('sub rsp, %d'%bytes_)
    for s,word in enumerate(stack):lines+=['mov rax, qword '+operand_rbp(offsets[word]),'mov qword %s, rax'%operand_rsp(8*s)]
    for reg,word in sorted(regs,key=lambda rw:rw[1]):lines.append('mov %s, qword %s'%(reg,operand_rbp(offsets[word])))
    lines+=['mov r11, qword '+operand_rbp(target),'call r11']
    if bytes_:lines.append('add rsp, %d'%bytes_)
    if rk==PAIR:lines+=['mov qword [rbp - %d], rax'%low,'mov qword [rbp - %d], rdx'%high]
    elif rk in WIDEN:lines+=[WIDEN[rk],'mov qword [rbp - %d], r10'%low]
    elif rk!=VOID:lines.append('mov qword [rbp - %d], rax'%low)
    return ''.join(l+'\n'for l in lines).encode()


def extend(kind,value):
    """Independent arbitrary-precision bit model of the unified 64-bit internal representation."""
    w=WIDTH[kind];v=value&((1<<w)-1)
    if kind in SIGNED and v>>(w-1):v-=1<<w
    return v&U64


def index(offset):return (4096-offset)//8                # [rbp-4096+8j] holds image[j]


def seq(n,start=8,step=8):return [start+step*i for i in range(n)]


G=0xdeadbeefcafe0000
# (kinds, offsets, target, frame, return kind, low, high, callee rax, callee rdx); the decoy pointer is at target+8.
VECTORS=[([],[],8,16,VOID,0,0,0x1111,0x2222),
         ([],[],16,16,I32,8,0,0x77777777_80000001,0x2222),
         ([0]*6,seq(6),56,64,UQ,64,0,0x0123456789abcdef,0x2222),
         ([0]*7,seq(7),64,128,PAIR,80,88,0x1111222233334444,0x5555666677778888),
         ([0]*8,seq(8),72,128,I8,8,0,G|0x80,0x2222),                                  # return slot == argument slot
         ([0]*16,[4080-8*i for i in range(16)],8,4080,PAIR,4080,16,0xfedcba9876543210,0x0f0e0d0c0b0a0908),
         ([0]*5+[1,0],seq(8,16),96,128,U16,8,0,0xdead0000beefffff,0x2222),             # pair on stack, last scalar in r9
         ([1]*8,seq(16,8,16),8,256,PTR,256,0,0x00007ffe12345678,0x2222),
         ([0,0,0],[8,16,24],16,32,UQ,32,0,0x8877665544332211,0x2222),                  # target slot == argument slot
         ([0,0],[8,16],24,32,U32,24,0,0xabcdef0180000000,0x2222),                      # target slot == return slot
         ([0,0,0],[8,16,24],16,32,I16,16,0,0x1234567890ab8000,0x2222),                 # target == argument == return slot
         ([0,1,0,1,1],seq(8,40),16,128,U8,24,0,G|0xff,0x2222)]


def image_for(k,vector):
    kinds,offsets=vector[:2]
    image=[0x6b6b000000000000+0x10000*k+j for j in range(512)]     # guard pattern in every word
    for o in set(offsets):image[index(o)]=0x0100000000000000*(k+1)+o*0x10001
    return image


class NasmSysvIndirectInvokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C43'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,DOC,*DEPENDENCIES,Path(__file__)]}
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.executables=cls.build_all('good',SOURCE.read_text(encoding='utf-8'))

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=180)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build_all(cls,name,text):
        """Stage only this component and its integrated read-only closure, then build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_sysv_indirect_invoke.dg').write_text(text,encoding='utf-8')
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        (root/'probe/indirect_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/indirect_export.dg',roots=[root],mode=mode)
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
        files={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in cls.work.rglob('*')if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,artifact_sha256=files,
            records=cls.records,integrated=False,OS_VM_built=False),indent=2)+'\n')

    def run_cases(self,exe,cases,label):
        """cases: (kinds, offsets, target, frame, rk, low, high, cap, readonly, status). Returns text or None."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for kinds,offsets,target,frame,rk,low,high,cap,ro,_ in cases:
            payload.extend(struct.pack('<10Q',len(kinds),len(offsets),target,rk,frame,low,high,cap,ro,0))
            payload.extend(bytes(kinds));payload.extend(struct.pack('<%dQ'%len(offsets),*offsets))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],PREFLIGHTS)
        offset=8;results=[]
        for i,c in enumerate(cases):
            got,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,i,'guard/atomicity',c[:7]))
            self.assertEqual(got,c[-1],(label,i,'status',c[:7]))
            results.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return results

    def texts(self,exe,vectors,label):
        return self.run_cases(exe,[(*v[:7],2048,0,OK)for v in vectors],label)

    def native_run(self,texts,vectors,label):
        """Per vector: a caller stub stores the callee's (and a decoy's) code address into frame slots at run time,
        runs the actual Dong call-site text against a real rbp frame, and the hand-written SysV callee records its
        arguments/alignment and returns RAX/RDX."""
        objects=[]
        for k,(text,v) in enumerate(zip(texts,vectors)):
            kinds,offsets,target,frame,rk,low,high,rax,rdx=v
            regs,stack,_=oracle(kinds)
            stub=['bits 64','default rel','section .text','global v%d'%k,'v%d:'%k,'push rbx','push rbp','push r12','push r13','push r14','push r15',
                  'mov rbx, rdi','sub rsp, 24']+['mov rax, 0x%x\nmov [rsp+%d], rax'%(g,8*j)for j,g in enumerate(GUARDS)]
            stub+=['mov rbp, rsp','sub rsp, 4096','cld','lea rsi, [rbx]','lea rdi, [rbp-4096]','mov rcx, 512','rep movsq']
            stub+=['lea rax, [rel f%d]'%k,'mov [rbp-%d], rax'%target,'mov [rbx+%d], rax'%(8*FPTR),          # function pointer slot
                   'lea rax, [rel d%d]'%k,'mov [rbp-%d], rax'%(target+8),'mov [rbx+%d], rax'%(8*DPTR)]      # another legal pointer
            stub+=['mov r%d, 0x%x'%(12+j,s)for j,s in enumerate(SENTINELS)]+['mov [rbx+%d], rsp'%(8*RSP_BEFORE)]
            stub+=text.decode('ascii').rstrip('\n').split('\n')                       # actual Dong output
            stub+=['mov [rbx+%d], rsp'%(8*RSP_AFTER)]+['mov [rbx+%d], r%d'%(8*(SAVED_OUT+j),12+j)for j in range(4)]
            stub+=['cld','lea rsi, [rbp-4096]','lea rdi, [rbx+%d]'%(8*FRAME_OUT),'mov rcx, 515','rep movsq',   # frame + 3 guards
                   'mov rsp, rbp','add rsp, 24','pop r15','pop r14','pop r13','pop r12','pop rbp','pop rbx','ret']
            def callee(name,marker,ra,rd,record):
                body=[name+':']
                if record:
                    body+=['mov [rbx+%d], %s'%(8*(ARG_OUT+j),r)for j,r in enumerate(ARGS)]
                    for j in range(len(stack)):body+=['mov rax, [rsp+%d]'%(8+8*j),'mov [rbx+%d], rax'%(8*(STACK_OUT+j))]
                    body+=['mov rax, rsp','and rax, 15','mov [rbx+%d], rax'%(8*ENTRY_ALIGN)]
                body+=['mov qword [rbx+%d], %d'%(8*MARKER,marker)]
                body+=['mov %s, 0x%x'%(r,0x3c3c3c3c3c3c3c00+j)for j,r in enumerate(['rcx','rsi','rdi','r8','r9','r10','r11'])]  # clobber caller-saved
                body+=['mov rax, 0x%x'%ra,'mov rdx, 0x%x'%rd,'ret']
                return body
            stub+=callee('f%d'%k,1,rax,rdx,True)+callee('d%d'%k,2,rax^DECOY,rdx^DECOY,False)
            asm=self.work/('%s.v%d.asm'%(label,k));asm.write_text('\n'.join(stub)+'\n',encoding='ascii')
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('%s.v%d.%s.o'%(label,k,fmt)),asm],'%s-v%d-%s'%(label,k,fmt))
            objects.append(self.work/('%s.v%d.%s.o'%(label,k,self.native)))
        main=NATIVE_MAIN.replace('%DECLS%','#define STATE %d\n'%STATE+'\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(texts))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(texts))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),*objects,'-o',exe],label+'-native-link')
        images=[image_for(k,v)for k,v in enumerate(vectors)]
        run=subprocess.run([str(exe)],input=b''.join(struct.pack('<512Q',*im)for im in images),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        n=STATE-512;self.assertEqual(len(run.stdout),8*n*len(vectors))
        for k,v in enumerate(vectors):
            kinds,offsets,target,frame,rk,low,high,rax,rdx=v
            got=list(struct.unpack_from('<%dQ'%n,run.stdout,8*n*k));at=lambda i:got[i-512]
            before=list(images[k]);before[index(target)]=at(FPTR);before[index(target+8)]=at(DPTR)   # runtime pointer slots
            want=list(before)
            if rk==PAIR:want[index(low)]=rax;want[index(high)]=rdx
            elif rk!=VOID:want[index(low)]=extend(rk,rax)
            if rk!=VOID:self.assertEqual(got[index(low)],want[index(low)],(label,k,'native return slot','low'))
            if rk==PAIR:self.assertEqual(got[index(high)],want[index(high)],(label,k,'native return slot','high'))
            self.assertEqual(at(MARKER),1,(label,k,'native call target'))
            self.assertNotEqual(at(FPTR),at(DPTR))
            value=lambda w:before[index(offsets[w])]
            regs,stack,_=oracle(kinds)
            for reg,w in regs:self.assertEqual(at(ARG_OUT+ARGS.index(reg)),value(w),(label,k,'native register argument',reg))
            for s,w in enumerate(stack):self.assertEqual(at(STACK_OUT+s),value(w),(label,k,'native stack argument',s))
            self.assertEqual(at(ENTRY_ALIGN),8,(label,k,'native callee entry alignment'))
            self.assertEqual(got[:512],want,(label,k,'native frame (sources, pointer slots, return slots, guards)'))
            self.assertEqual([at(GUARD_OUT+j)for j in range(3)],GUARDS,(label,k,'native guards above rbp'))
            self.assertEqual(at(RSP_AFTER),at(RSP_BEFORE),(label,k,'native rsp restored'))
            self.assertEqual([at(SAVED_OUT+j)for j in range(4)],SENTINELS,(label,k,'native callee-saved preserved'))

    def test_exact_text_capacity_and_invalid(self):
        cases=[]
        for v in VECTORS:
            n=len(expected_text(*v[:3],v[4],v[5],v[6]))
            cases+=[(*v[:7],n,0,OK),(*v[:7],n+9,0,OK),(*v[:7],n-1,0,CAPACITY),(*v[:7],0,0,CAPACITY)]
        longest=([0]*16,[4080-8*i for i in range(16)],4080,4080,PAIR,4072,4064)
        n=len(expected_text(*longest[:3],*longest[4:]));self.assertLessEqual(n,1200)
        cases+=[(*longest,n,1,OK),(*longest,n-1,0,CAPACITY),(*longest,0,1,CAPACITY)]
        base=([0,0],[8,16],24,32,UQ,32,0)                                         # each bad case changes one field only
        def change(**kw):
            names=['kinds','offsets','target','frame','rk','low','high'];v=dict(zip(names,base));v.update(kw)
            return tuple(v[x]for x in names)
        bad=[change(kinds=[2],offsets=[8]),change(kinds=[0]*17,offsets=seq(17),frame=4080),change(kinds=[1]*9,offsets=seq(18),frame=4080),
             change(offsets=[8]),change(offsets=[8,16,24]),change(offsets=[0,8]),change(offsets=[8,12]),change(offsets=[8,48]),
             change(offsets=[8,2**64-8]),change(target=0),change(target=4),change(target=20),change(target=40),change(target=2**64-8),
             change(frame=8,offsets=[8,8],target=8,low=8),change(frame=4096),change(frame=2**64-16),
             change(rk=12),change(rk=U64),change(low=0),change(low=40),change(high=8),change(rk=PAIR,high=32),change(rk=VOID),
             change(rk=VOID,low=0,high=8)]
        for b in bad:cases+=[(*b,2048,0,INVALID),(*b,0,1,INVALID)]
        for mode,exe in self.executables.items():
            for c,text in zip(cases,self.run_cases(exe,cases,'text-'+mode)):
                if c[-1]==OK:self.assertEqual(text,expected_text(*c[:3],c[4],c[5],c[6]),(mode,c[:7]))
        self.records.append(dict(test='exact-text-capacity-invalid',cases=len(cases),preflights_per_native=PREFLIGHTS,longest_bytes=n,modes=2,passed=True))

    def test_native_indirect_calls(self):
        self.assertLessEqual(len(VECTORS),24)
        self.assertTrue({0,6,7,8,16}<={words(v[0])for v in VECTORS})
        kinds={v[4]for v in VECTORS};self.assertTrue({VOID,PAIR}<=kinds and kinds&SIGNED and kinds&set(WIDEN))
        self.assertTrue(any(v[2]in v[1]for v in VECTORS))                                  # target slot == argument slot
        self.assertTrue(any(v[4]!=VOID and v[2]==v[5]for v in VECTORS))                    # target slot == return slot
        self.assertTrue(any(v[2]in v[1]and v[2]==v[5]for v in VECTORS))                    # all three the same slot
        self.assertTrue(any(v[4]!=VOID and v[5]in v[1]for v in VECTORS))                   # return slot == argument slot
        for mode,exe in self.executables.items():
            self.native_run(self.texts(exe,VECTORS,'vectors-'+mode),VECTORS,'native-'+mode)
        self.records.append(dict(test='native-indirect-calls',vectors_per_mode=len(VECTORS),modes=2,formats=['elf64','win64'],passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        target=[v for v in VECTORS if v[4]!=VOID][:4]
        pairs=[v for v in VECTORS if v[4]==PAIR]
        for name,old,new,vectors in [
            ('bad-other-pointer-slot','ld.emit(R11,RBP,-(target_offset as i64),','ld.emit(R11,RBP,-(target_offset as i64)-8,',target),
            ('bad-pair-capture-swap','cap.emit(return_kind,frame_bytes,low_offset,high_offset,','cap.emit(return_kind,frame_bytes,high_offset,low_offset,',pairs)]:
            self.assertEqual(source.count(old),1,name);self.assertGreaterEqual(len(vectors),2,name)
            for mode,exe in self.executables.items():                                       # same inputs pass first
                self.native_run(self.texts(exe,vectors,name+'-good-'+mode),vectors,name+'-good-'+mode)
            for mode,exe in self.build_all(name,source.replace(old,new,1)).items():
                texts=self.texts(exe,vectors,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'native return slot'):self.native_run(texts,vectors,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,linked=True,native_executed=True,modes=2,rejected_by='native return slot'))
        old='if at>on{return CAPACITY;}';new='if at>on{*written=at;return CAPACITY;}'
        self.assertEqual(source.count(old),1);case=[(*VECTORS[3][:7],40,0,CAPACITY)]
        for mode,exe in self.executables.items():self.run_cases(exe,case,'bad-early-written-good-'+mode)
        for mode,exe in self.build_all('bad-early-written',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.run_cases(exe,case,'bad-early-written-'+mode)
        self.records.append(dict(test='bad-early-written',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))

    def test_input_tail_aliases_are_reachable(self):
        """Preflight sensitivity: a real Dong checking each input against out/written by its first byte only."""
        source=SOURCE.read_text(encoding='utf-8')
        line='if overlap(wp,8,kp,kn)||overlap(wp,8,sp,sn)||overlap(op,on,kp,kn)||overlap(op,on,sp,sn){return INVALID;}'
        self.assertEqual(source.count(line),1)
        bad=line.replace(',kn)',',1)').replace(',sn)',',1)')
        for mode,exe in self.executables.items():self.run_cases(exe,[],'tail-good-'+mode)   # same harness passes all 17
        for mode,exe in self.build_all('bad-input-first-byte',source.replace(line,bad,1)).items():
            run=subprocess.run([str(exe)],input=struct.pack('<Q',0),capture_output=True,timeout=60)
            err=run.stderr.decode('ascii','replace');(self.work/('bad-input-first-byte-'+mode+'.stderr')).write_text(err,encoding='ascii')
            self.assertEqual(run.returncode,93,(mode,err))
            failed=[int(line.split()[2])for line in err.splitlines()if line.startswith('invalid preflight ')]
            self.assertEqual(failed,[11,12,13,14],(mode,err))                                # exactly the four tail cases
        self.records.append(dict(test='bad-input-first-byte',compiled=True,native_executed=True,modes=2,rejected_by='preflight 11..14'))


if __name__=='__main__':unittest.main()
