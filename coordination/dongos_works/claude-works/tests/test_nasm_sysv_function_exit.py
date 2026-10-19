"""Actual Dong SysV function exit (C39 return load + CR11 epilogue): exact text, assembly, real CR11-framed call/ret."""
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

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_sysv_function_exit.dg'
DOC=WORKS/'claude-works/src/bootstrap/nasm_sysv_function_exit.md'
# Integrated components and their whole read-only import closure (nothing else from lang is staged).
DEPENDENCIES=[ROOT/'lang/bootstrap'/(n+'.dg')for n in (
    'nasm_sysv_return_values','sysv_return_plan','nasm_memory_operand','decimal_integer',   # C39, C14, CR8, CR4
    'nasm_function_frame')]                                                                # CR11 (imports CR4)
OK,INVALID,CAPACITY=0,1,2
U64=2**64-1
PREFLIGHTS=7
VOID,BOOL,U8,I8,U16,I16,U32,I32,UQ,IQ,PTR,PAIR=range(12)
SAVED=['rbx','r12','r13','r14','r15']                    # mask bit order
WRAPPER='''module probe.exit_export;
import bootstrap.nasm_sysv_function_exit as x;
import bootstrap.nasm_function_frame as ff;
export("dong_exit_emit") pub unsafe fn emit(kind:u64,frame:usize,mask:u64,low:usize,high:usize,out:*u8,no:usize,written:*usize)u64{unsafe{
 return x.emit(kind,frame,mask,low,high,slice_from_raw_parts(out,no),written);
}}
export("dong_cr11_prologue") pub unsafe fn prologue(frame:usize,mask:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return ff.prologue(frame,mask,slice_from_raw_parts(out,no),written);
}}
'''
HARNESS=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI dong_exit_emit(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
extern uint64_t ABI dong_cr11_prologue(uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((void*)(uintptr_t)(x))
/* Descriptor/alias preflights. Every other field is legal (I8 from [rbp - 16], frame 16, mask rbx, out 128 bytes)
   so only the target check can reject it. Every failing preflight is reported, then exit 93. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[1024],saved[1024];const unsigned total=7;unsigned failed=0;
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(saved,arena,sizeof(arena));
  uint8_t*o=arena+256;uint64_t ol=128;uint64_t*w=(uint64_t*)(arena+768);
  if(i==0)w=NULL;                                                   /* written NULL */
  else if(i==1)w=(uint64_t*)(arena+769);                            /* written odd */
  else if(i==2){w=FAKE(UINT64_MAX-7);o=NULL;ol=0;}                  /* written end overflow, legal empty out */
  else if(i==3)o=FAKE(UINT64_MAX-63);                               /* out end overflow (length 128) */
  else if(i==4)o=NULL;                                              /* NULL non-empty out */
  else if(i==5)w=(uint64_t*)o;                                      /* written on out prefix */
  else w=(uint64_t*)(o+120);                                        /* written in out's unused tail */
  uint64_t s=dong_exit_emit(3,16,1,16,0,o,ol,w);
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
  uint64_t h[7];read_exact(h,sizeof(h));uint64_t op=h[0],kind=h[1],frame=h[2],mask=h[3],low=h[4],high=h[5],cap=h[6];
  if(cap>4096)exit(94);
  uint8_t*out=malloc(cap+64);static _Alignas(8) uint64_t meta[3];if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=op?dong_cr11_prologue(frame,mask,cap?out+32:NULL,cap,written)
               :dong_exit_emit(kind,frame,mask,low,high,cap?out+32:NULL,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(s)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={s,valid,s?0:*written};write_exact(response,24);write_exact(out+32,response[2]);
  free(out);
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
/* Commit the stack pages the 4 KiB callee frames will touch (no guard-page skipping). */
static __attribute__((noinline)) void commit_stack(void){volatile uint8_t pages[65536];for(unsigned i=0;i<sizeof(pages);i+=512)pages[i]=(uint8_t)i;}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 commit_stack();
 static uint64_t io[STATE+1];
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  memset(io,0,sizeof(io));io[STATE]=0xa5a5a5a5a5a5a5a5ull;
  table[i](io);
  if(io[STATE]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  if(fwrite(io,8,STATE,stdout)!=STATE)exit(92);
 }return 0;
}
'''
# State layout (qwords): [0,512) callee frame [rsp, rbp) snapshot taken just before the exit text;
# 512 callee entry rsp%16; 513 rsp before call; 514 rsp after; 515 rax; 516 rdx; 517 rbx before; 518 rbx after;
# 519 rbp after; [520,524) r12..r15 after.
SNAP,ENTRY_ALIGN,RSP_BEFORE,RSP_AFTER,RAX,RDX,RBX_BEFORE,RBX_AFTER,RBP_AFTER,R12_AFTER,STATE=0,512,513,514,515,516,517,518,519,520,524
CALLER={'rbp':0x0b0b0b0b0b0b0b0b,'r12':0x1212121212121212,'r13':0x1313131313131313,'r14':0x1414141414141414,'r15':0x1515151515151515}
CLOBBER=0xc10bbe7ec10bbe00                                # what the callee puts in each saved register before exiting
JUNK_RAX,JUNK_RDX=0x0a0a0a0a0a0a0a0a,0x0d0d0d0d0d0d0d0d
LOCAL_FILL=0x6b6b6b6b00000000
WIDTH={BOOL:8,U8:8,I8:8,U16:16,I16:16,U32:32,I32:32,UQ:64,IQ:64,PTR:64,PAIR:64}
SIGNED={I8,I16,I32}
PREFIX={BOOL:'movzx rax, byte ',U8:'movzx rax, byte ',I8:'movsx rax, byte ',U16:'movzx rax, word ',I16:'movsx rax, word ',
        U32:'mov eax, dword ',I32:'movsxd rax, dword ',UQ:'mov rax, qword ',IQ:'mov rax, qword ',PTR:'mov rax, qword '}


def layout(frame,mask):
    """Independent CR11 frame model: (saved register count, padding, extent below rbp, adjust)."""
    n=bin(mask&31).count('1');pad=8 if n%2 else 0
    return n,pad,8*n+frame+pad,frame+pad


def expected_text(kind,frame,mask,low,high):
    """Independent text model: C39 load then the CR11 epilogue."""
    n,pad,extent,adjust=layout(frame,mask);lines=[]
    if kind==PAIR:lines+=['mov rax, qword [rbp - %d]'%low,'mov rdx, qword [rbp - %d]'%high]
    elif kind!=VOID:lines.append('%s[rbp - %d]'%(PREFIX[kind],low))
    if adjust:lines.append('add rsp, %d'%adjust)
    lines+=['pop '+SAVED[b]for b in reversed(range(5))if mask>>b&1]+['pop rbp','ret']
    return ''.join(l+'\n'for l in lines).encode()


def expected_prologue(frame,mask):
    n,pad,extent,adjust=layout(frame,mask)
    lines=['push rbp','mov rbp, rsp']+['push '+SAVED[b]for b in range(5)if mask>>b&1]+(['sub rsp, %d'%adjust]if adjust else[])
    return ''.join(l+'\n'for l in lines).encode()


def extend(kind,value):
    """Independent arbitrary-precision bit model of the unified 64-bit internal representation."""
    w=WIDTH[kind];v=value&((1<<w)-1)
    if kind in SIGNED and v>>(w-1):v-=1<<w
    return v&U64


G=0xdeadbeefcafe0000                                      # high-bit garbage in every narrow slot
# (kind, frame_bytes, saved_mask, low, high, low slot value, high slot value)
VECTORS=[(VOID,0,0,0,0,0,0),
         (VOID,16,0b11111,0,0,0,0),
         (BOOL,16,0b00001,16,0,G|0x01,0),                  # n=1 (odd, pad 8), slot just above the saved area
         (BOOL,16,0b00010,16,0,G|0x00,0),
         (U8,32,0b00010,40,0,G|0xff,0),                    # slot at the local bottom (8n+frame)
         (I8,16,0b00011,24,0,G|0x80,0),                    # n=2 (even, no pad), adjacent to the saved area
         (I8,16,0,16,0,G|0xff,0),
         (U16,16,0,8,0,0xdead0000beefffff,0),
         (I16,32,0b00111,56,0,0x1234567890ab8000,0),       # n=3, bottom of the locals
         (U32,16,0b01111,40,0,0xabcdef0180000000,0),       # n=4
         (I32,32,0b11111,48,0,0x7777777780000000,0),       # all five saved
         (UQ,4080,0,4080,0,U64,0),                         # maximum extent, local bottom
         (IQ,4048,0b10101,32,0,0x8000000000000000,0),      # n=3: extent 24+4048+8 = 4080, slot adjacent to saved area
         (PTR,16,0b00100,16,0,0x00007ffe12345678,0),
         (PAIR,32,0b00011,24,48,0x1111222233334444,0x5555666677778888),
         (PAIR,4032,0b11111,4072,48,0xfedcba9876543210,0x0123456789abcdef)]   # extent 4080, bottom and adjacent slots


class NasmSysvFunctionExitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C42'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
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
        (root/'bootstrap/nasm_sysv_function_exit.dg').write_text(text,encoding='utf-8')
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        (root/'probe/exit_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/exit_export.dg',roots=[root],mode=mode)
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
        """cases: (op, kind, frame, mask, low, high, cap, status); op 0 = this emitter, 1 = CR11 prologue."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:payload.extend(struct.pack('<7Q',*c[:7]))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],PREFLIGHTS)
        offset=8;results=[]
        for i,c in enumerate(cases):
            got,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,i,'guard/atomicity',c))
            self.assertEqual(got,c[-1],(label,i,'status',c))
            results.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return results

    def texts(self,exe,vectors,label):
        """Actual Dong output for each vector: (CR11 prologue, this function exit)."""
        cases=[]
        for kind,frame,mask,low,high,_,_ in vectors:cases+=[(1,0,frame,mask,0,0,256,OK),(0,kind,frame,mask,low,high,256,OK)]
        out=self.run_cases(exe,cases,label)
        return [(out[2*k],out[2*k+1])for k in range(len(vectors))]

    def native_run(self,texts,vectors,label):
        """Caller stub -> real call into a callee whose entry is the actual CR11 prologue and whose exit is the actual
        Dong function-exit text (with its ret). The frame is snapshotted before the exit; nothing reads it after ret."""
        stub=['bits 64','section .text']
        for k,((pro,exit_),(kind,frame,mask,low,high,lv,hv)) in enumerate(zip(texts,vectors)):
            n,pad,extent,adjust=layout(frame,mask)
            stub+=['global v%d'%k,'v%d:'%k,'push rbx','push rbp','push r12','push r13','push r14','push r15','mov rbx, rdi','sub rsp, 8']
            stub+=['mov %s, 0x%x'%(r,v)for r,v in CALLER.items()]
            stub+=['mov [rbx+%d], rbx'%(8*RBX_BEFORE),'mov [rbx+%d], rsp'%(8*RSP_BEFORE),'mov rdi, rbx','call f%d'%k]
            stub+=['mov [rbx+%d], rsp'%(8*RSP_AFTER),'mov [rbx+%d], rax'%(8*RAX),'mov [rbx+%d], rdx'%(8*RDX),
                   'mov [rbx+%d], rbx'%(8*RBX_AFTER),'mov [rbx+%d], rbp'%(8*RBP_AFTER)]
            stub+=['mov [rbx+%d], r%d'%(8*(R12_AFTER+j),12+j)for j in range(4)]
            stub+=['add rsp, 8','pop r15','pop r14','pop r13','pop r12','pop rbp','pop rbx','ret']
            # callee: entry alignment, actual CR11 prologue, fill locals, write return slots, clobber saved registers,
            # snapshot [rsp, rbp), junk RAX/RDX, then the actual Dong exit text (which ends in CR11's ret).
            stub+=['f%d:'%k,'mov rax, rsp','and rax, 15','mov [rdi+%d], rax'%(8*ENTRY_ALIGN),'mov r11, rdi']
            stub+=pro.decode('ascii').rstrip('\n').split('\n')
            if adjust:stub+=['cld','mov rdi, rsp','mov rcx, %d'%(adjust//8),'mov rax, 0x%x'%LOCAL_FILL,'rep stosq']
            if low:stub+=['mov rax, 0x%x'%lv,'mov [rbp-%d], rax'%low]
            if high:stub+=['mov rax, 0x%x'%hv,'mov [rbp-%d], rax'%high]
            stub+=['mov %s, 0x%x'%(SAVED[b],CLOBBER+b)for b in range(5)if mask>>b&1]
            if extent:stub+=['cld','mov rsi, rsp','lea rdi, [r11+%d]'%(8*SNAP),'mov rcx, %d'%(extent//8),'rep movsq']
            stub+=['mov rax, 0x%x'%JUNK_RAX,'mov rdx, 0x%x'%JUNK_RDX]
            stub+=exit_.decode('ascii').rstrip('\n').split('\n')
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','#define STATE %d\n'%STATE+'\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(texts))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(texts))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],label+'-native-link')
        run=subprocess.run([str(exe)],capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        self.assertEqual(len(run.stdout),8*STATE*len(vectors))
        for k,(kind,frame,mask,low,high,lv,hv) in enumerate(vectors):
            got=struct.unpack_from('<%dQ'%STATE,run.stdout,8*STATE*k);n,pad,extent,adjust=layout(frame,mask)
            want_rax=JUNK_RAX if kind==VOID else (lv if kind==PAIR else extend(kind,lv))
            want_rdx=hv if kind==PAIR else JUNK_RDX
            self.assertEqual(got[RAX],want_rax,(label,k,'native rax',kind))
            self.assertEqual(got[RDX],want_rdx,(label,k,'native rdx',kind))
            self.assertEqual(got[ENTRY_ALIGN],8,(label,k,'native callee entry alignment'))
            self.assertEqual(got[RSP_AFTER],got[RSP_BEFORE],(label,k,'native rsp balanced across call/ret'))
            self.assertEqual(got[RBX_AFTER],got[RBX_BEFORE],(label,k,'native rbx restored'))
            self.assertEqual((got[RBP_AFTER],*got[R12_AFTER:R12_AFTER+4]),tuple(CALLER.values()),(label,k,'native rbp/r12..r15 restored'))
            # Frame snapshot (lowest address first): locals/padding fill, return slots, then the pushed caller values.
            snap=list(got[SNAP:SNAP+extent//8]);want=[LOCAL_FILL]*(adjust//8)
            pushed=[('rbx',got[RBX_BEFORE])]+[(r,CALLER[r])for r in SAVED[1:]]
            want+=[v for b,(r,v) in reversed(list(enumerate(pushed)))if mask>>b&1]
            if low:want[(extent-low)//8]=lv
            if high:want[(extent-high)//8]=hv
            self.assertEqual(snap,want,(label,k,'native frame snapshot (locals, slots, saved area)'))

    def test_exact_text_capacity_and_invalid(self):
        cases=[]
        for kind,frame,mask,low,high,_,_ in VECTORS:
            n=len(expected_text(kind,frame,mask,low,high))
            cases+=[(0,kind,frame,mask,low,high,n,OK),(0,kind,frame,mask,low,high,n+5,OK),
                    (0,kind,frame,mask,low,high,n-1,CAPACITY),(0,kind,frame,mask,low,high,0,CAPACITY)]
        longest=(PAIR,4032,0b11111,4072,4064);n=len(expected_text(*longest))
        self.assertLessEqual(n,122);cases+=[(0,*longest,n,OK),(0,*longest,n-1,CAPACITY)]
        cases+=[(0,VOID,0,0,0,0,12,OK),(0,VOID,0,0,0,0,11,CAPACITY)]                                           # VOID still emits "pop rbp\nret\n"
        base=dict(kind=I8,frame=32,mask=0b00001,low=16,high=0)                    # n=1: saved 8, locals (8,40], pad 8
        def change(**kw):v=dict(base);v.update(kw);return (v['kind'],v['frame'],v['mask'],v['low'],v['high'])
        bad=[change(frame=8),change(frame=4112),change(frame=2**64-16),change(mask=32),change(mask=U64),
             change(frame=4080,mask=0b00001,low=16),change(frame=4096,mask=0,low=16),          # extent 4096 > 4080
             change(kind=12),change(kind=U64),change(low=8),change(low=0),change(low=4),change(low=20),
             change(low=48),change(low=56),change(high=24),change(kind=VOID),change(kind=VOID,low=0,high=24),
             change(kind=PAIR,high=16),change(kind=PAIR,high=0),change(kind=PAIR,high=8),change(kind=PAIR,high=48)]
        for b in bad:cases+=[(0,*b,256,INVALID),(0,*b,0,INVALID)]
        for frame,mask in [(0,0),(16,1),(32,0b11),(4032,0b11111),(4080,0)]:
            p=len(expected_prologue(frame,mask));cases.append((1,0,frame,mask,0,0,p,OK))
        for mode,exe in self.executables.items():
            for c,text in zip(cases,self.run_cases(exe,cases,'text-'+mode)):
                if c[-1]==OK:
                    want=expected_prologue(c[2],c[3])if c[0]else expected_text(*c[1:6])
                    self.assertEqual(text,want,(mode,c))
        self.records.append(dict(test='exact-text-capacity-invalid',cases=len(cases),preflights_per_native=PREFLIGHTS,longest_bytes=n,modes=2,passed=True))

    def test_native_function_exit(self):
        self.assertLessEqual(len(VECTORS),24)
        self.assertEqual({v[0]for v in VECTORS},set(range(12)))
        masks={v[2]for v in VECTORS};self.assertTrue({0,0b11111}<=masks)
        self.assertTrue(any(bin(m).count('1')==1 for m in masks)and any(bin(m).count('1')in(2,3,4)for m in masks))
        self.assertTrue({0,8}<={layout(v[1],v[2])[1]for v in VECTORS})                         # even and odd padding
        self.assertIn(4080,{layout(v[1],v[2])[2]for v in VECTORS})                             # maximum extent
        self.assertTrue(any(v[3]==8*layout(v[1],v[2])[0]+8 for v in VECTORS if v[3]))           # slot touching the saved area
        self.assertTrue(any(v[3]==8*layout(v[1],v[2])[0]+v[1]for v in VECTORS if v[3]))         # slot at the local bottom
        for mode,exe in self.executables.items():
            self.native_run(self.texts(exe,VECTORS,'vectors-'+mode),VECTORS,'native-'+mode)
        self.records.append(dict(test='native-function-exit',vectors_per_mode=len(VECTORS),modes=2,formats=['elf64','win64'],passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        call='rv.emit(kind,extent,low_offset,high_offset,'
        self.assertEqual(source.count(call),1);self.assertEqual(source.count('pub unsafe fn emit('),1)
        pairs=[v for v in VECTORS if v[0]==PAIR]
        signed=[v for v in VECTORS if v[0]==I8 and extend(I8,v[5])>>63]
        for name,text,vectors,reason in [
            ('bad-pair-delegate-swap',source.replace(call,'rv.emit(kind,extent,high_offset,low_offset,',1),pairs,'native r[ad]x'),
            ('bad-i8-delegated-as-u8',source.replace(call,'rv.emit(widen_kind(kind),extent,low_offset,high_offset,',1)
             .replace('pub unsafe fn emit(','fn widen_kind(k:u64)u64{if k==3{return 2;}return k;}\npub unsafe fn emit(',1),signed,'native rax')]:
            self.assertGreaterEqual(len(vectors),2,name)
            for mode,exe in self.executables.items():                                       # same inputs pass first
                self.native_run(self.texts(exe,vectors,name+'-good-'+mode),vectors,name+'-good-'+mode)
            for mode,exe in self.build_all(name,text).items():
                texts=self.texts(exe,vectors,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,reason):self.native_run(texts,vectors,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,linked=True,native_executed=True,modes=2,rejected_by=reason))
        old='if at>out.len{return CAPACITY;}';new='if at>out.len{*written=at;return CAPACITY;}'
        self.assertEqual(source.count(old),1);case=[(0,*VECTORS[-1][:5],20,CAPACITY)]
        for mode,exe in self.executables.items():self.run_cases(exe,case,'bad-early-written-good-'+mode)
        for mode,exe in self.build_all('bad-early-written',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.run_cases(exe,case,'bad-early-written-'+mode)
        self.records.append(dict(test='bad-early-written',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))

    def test_local_window_is_this_modules_check(self):
        """A real Dong without the local-area window: C39 alone accepts slots in the saved area or bottom padding."""
        source=SOURCE.read_text(encoding='utf-8')
        old='if !local(low_offset,saved,frame_bytes)||!local(high_offset,saved,frame_bytes){return INVALID;}'
        self.assertEqual(source.count(old),1)
        cases=[(0,I8,32,0b00001,8,0,256,INVALID),(0,I8,32,0b00001,48,0,256,INVALID),          # saved area, bottom padding
               (0,PAIR,32,0b00001,16,8,256,INVALID),(0,UQ,32,0b11111,40,0,256,INVALID)]
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'window-good-'+mode)
        for mode,exe in self.build_all('bad-no-local-window',source.replace(old,'',1)).items():
            for i,c in enumerate(cases):
                with self.assertRaisesRegex(AssertionError,'status'):self.run_cases(exe,[c],'bad-no-local-window-%s-%d'%(mode,i))
        self.records.append(dict(test='bad-no-local-window',compiled=True,native_executed=True,modes=2,rejected_by='status (OK instead of INVALID)'))

    def test_alias_preflight_is_reachable(self):
        """Preflight sensitivity: a real Dong without the written/out overlap check fails exactly cases 5 and 6."""
        source=SOURCE.read_text(encoding='utf-8')
        old='if overlap(wp,8,op,out.len){return INVALID;}';self.assertEqual(source.count(old),1)
        for mode,exe in self.executables.items():self.run_cases(exe,[],'alias-good-'+mode)
        for mode,exe in self.build_all('bad-no-alias',source.replace(old,'',1)).items():
            run=subprocess.run([str(exe)],input=struct.pack('<Q',0),capture_output=True,timeout=60)
            err=run.stderr.decode('ascii','replace');(self.work/('bad-no-alias-'+mode+'.stderr')).write_text(err,encoding='ascii')
            self.assertEqual(run.returncode,93,(mode,err))
            failed=[int(line.split()[2])for line in err.splitlines()if line.startswith('invalid preflight ')]
            self.assertEqual(failed,[5,6],(mode,err))
        self.records.append(dict(test='bad-no-alias',compiled=True,native_executed=True,modes=2,rejected_by='preflight 5/6'))


if __name__=='__main__':unittest.main()
