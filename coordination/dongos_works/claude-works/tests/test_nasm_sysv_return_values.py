"""Actual Dong SysV return-value load emitter (C14 plan + CR8 operands): exact text, assembly, native frame loads."""
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

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_sysv_return_values.dg'
DOC=WORKS/'claude-works/src/bootstrap/nasm_sysv_return_values.md'
DEPENDENCIES=[ROOT/'lang/bootstrap'/n for n in ('sysv_return_plan.dg','nasm_memory_operand.dg','decimal_integer.dg')]  # C14, CR8, CR4 (CR8's import)
OK,INVALID,CAPACITY=0,1,2
U64=2**64-1
PREFLIGHTS=7
VOID,BOOL,U8,I8,U16,I16,U32,I32,UQ,IQ,PTR,PAIR=range(12)
# Registers the stub sets to sentinels and reads back after the emitted text (rbx holds the state pointer).
REGS=['rax','rcx','rdx','rsi','rdi','r8','r9','r10','r11','r12','r13','r14','r15']
SENTINEL={r:0x0101010101010101*(k+1)^0x8000000000000000 for k,r in enumerate(REGS)}
GUARDS=[0x4747474747474747,0x4848484848484848]
ARITH_FLAGS=0x8d5
WRAPPER='''module probe.retval_export;
import bootstrap.nasm_sysv_return_values as r;
export("dong_ret_emit") pub unsafe fn emit(kind:u64,frame:usize,low:usize,high:usize,out:*u8,no:usize,written:*usize)u64{unsafe{
 return r.emit(kind,frame,low,high,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_ret_emit(uint64_t,uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((void*)(uintptr_t)(x))
/* Descriptor/alias preflights. Every other field is legal (U64 load from [rbp - 8], frame 16, out 64 bytes)
   so only the target check can reject it. Every failing preflight is reported, then exit 93. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[1024],saved[1024];const unsigned total=7;unsigned failed=0;
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(saved,arena,sizeof(arena));
  uint8_t*o=arena+256;uint64_t ol=64;uint64_t*w=(uint64_t*)(arena+768);
  if(i==0)w=NULL;                                                   /* written NULL */
  else if(i==1)w=(uint64_t*)(arena+769);                            /* written odd */
  else if(i==2){w=FAKE(UINT64_MAX-7);o=NULL;ol=0;}                  /* written end overflow, legal empty out */
  else if(i==3)o=FAKE(UINT64_MAX-15);                               /* out end overflow (length 64) */
  else if(i==4)o=NULL;                                              /* NULL non-empty out */
  else if(i==5)w=(uint64_t*)o;                                      /* written on out prefix */
  else w=(uint64_t*)(o+56);                                         /* written in out's unused tail */
  uint64_t s=dong_ret_emit(8,16,8,0,o,ol,w);
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
  uint64_t h[5];read_exact(h,sizeof(h));uint64_t kind=h[0],frame=h[1],low=h[2],high=h[3],cap=h[4];
  if(cap>4096)exit(94);
  uint8_t*out=malloc(cap+64);static _Alignas(8) uint64_t meta[3];if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=dong_ret_emit(kind,frame,low,high,cap?out+32:NULL,cap,written);
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
# State layout (qwords): [0,512) frame image in; [512,1024) frame out; [1024,1026) guards above rbp;
# [1026,1039) REGS after; 1039 rbp after; 1040 rsp after; 1041 rbp before; 1042 rsp before;
# 1043 flags before; 1044 flags after; 1045 rbx after; 1046 rbx before.
FRAME_OUT,GUARD_OUT,REGS_OUT,RBP_AFTER,RSP_AFTER,RBP_BEFORE,RSP_BEFORE,FLAGS_BEFORE,FLAGS_AFTER,RBX_AFTER,RBX_BEFORE,STATE=\
    512,1024,1026,1039,1040,1041,1042,1043,1044,1045,1046,1047
WIDTH={BOOL:8,U8:8,I8:8,U16:16,I16:16,U32:32,I32:32,UQ:64,IQ:64,PTR:64}
SIGNED={I8,I16,I32}
PREFIX={BOOL:'movzx rax, byte ',U8:'movzx rax, byte ',I8:'movsx rax, byte ',U16:'movzx rax, word ',I16:'movsx rax, word ',
        U32:'mov eax, dword ',I32:'movsxd rax, dword ',UQ:'mov rax, qword ',IQ:'mov rax, qword ',PTR:'mov rax, qword '}


def expected_text(kind,low,high):
    """Independent text model (not the C14 planner)."""
    if kind==VOID:return b''
    if kind==PAIR:return ('mov rax, qword [rbp - %d]\nmov rdx, qword [rbp - %d]\n'%(low,high)).encode()
    return ('%s[rbp - %d]\n'%(PREFIX[kind],low)).encode()


def extend(kind,slot):
    """Independent arbitrary-precision bit model of the unified internal representation in RAX."""
    if kind in (UQ,IQ,PTR,PAIR):return slot&U64
    w=WIDTH[kind];v=slot&((1<<w)-1)
    if kind in SIGNED and v>>(w-1):v-=1<<w
    return v&U64


def index(offset):return (4096-offset)//8                # [rbp-4096+8j] holds image[j]


# (kind, frame_bytes, low, high, {offset: slot value}); narrow slots carry high-bit garbage.
G=0xdeadbeefcafe0000
VECTORS=[(VOID,0,0,0,{}),
         (BOOL,16,8,0,{8:G|0x00}),(BOOL,16,8,0,{8:G|0x01}),(U8,16,8,0,{8:G|0xff}),
         (I8,16,8,0,{8:G|0x80}),(I8,16,8,0,{8:G|0x7f}),(U16,32,16,0,{16:0xdead0000beef0000|0xffff}),
         (I16,32,24,0,{24:0x1234567890ab8000}),(I16,32,8,0,{8:0xffffffffffff7fff}),(U32,16,8,0,{8:0x12345678ffffffff}),
         (I32,16,8,0,{8:0xabcdef0180000000}),(I32,16,16,0,{16:0x000000007fffffff}),(UQ,16,8,0,{8:U64}),
         (IQ,16,8,0,{8:0x8000000000000000}),(PTR,64,40,0,{40:0x00007ffe12345678}),
         (PAIR,16,8,16,{8:0x1111222233334444,16:0x5555666677778888}),
         (PAIR,4080,4080,8,{4080:0xfedcba9876543210,8:0x0123456789abcdef}),
         (UQ,4080,4080,0,{4080:0x8877665544332211}),(I8,4080,4080,0,{4080:0x00000000000000ff}),
         (I32,4080,8,0,{8:0x12345678ffffffff})]


def image_for(k,slots):
    image=[0x6b6b000000000000+0x10000*k+j for j in range(512)]        # guard pattern in every non-slot word
    for o,v in slots.items():image[index(o)]=v
    return image


class NasmSysvReturnValuesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C39'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,DOC,*DEPENDENCIES,Path(__file__)]}
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.executables=cls.build_all('good',SOURCE.read_text(encoding='utf-8'))

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build_all(cls,name,text):
        """Stage only this component and the integrated C14/CR8/CR4 modules, then build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_sysv_return_values.dg').write_text(text,encoding='utf-8')
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        (root/'probe/retval_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/retval_export.dg',roots=[root],mode=mode)
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
        """cases: (kind, frame, low, high, cap, status). Returns the emitted text (None on failure); guards checked per call."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for kind,frame,low,high,cap,_ in cases:payload.extend(struct.pack('<5Q',kind,frame,low,high,cap))
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
        return self.run_cases(exe,[(k,f,lo,hi,64,OK)for k,f,lo,hi,_ in vectors],label)

    def native_run(self,texts,vectors,label):
        """Each stub builds a real rbp frame from the image, runs the actual Dong text, and records registers/frame/flags."""
        stub=['bits 64','section .text']
        for k,text in enumerate(texts):
            stub+=['global v%d'%k,'v%d:'%k,'push rbx','push rbp','push r12','push r13','push r14','push r15','mov rbx, rdi',
                   'sub rsp, 16']+['mov rax, 0x%x'%g+'\nmov [rsp+%d], rax'%(8*j)for j,g in enumerate(GUARDS)]
            stub+=['mov rbp, rsp','sub rsp, 4096','cld','lea rsi, [rbx]','lea rdi, [rbp-4096]','mov rcx, 512','rep movsq']
            stub+=['mov [rbx+%d], rbp'%(8*RBP_BEFORE),'mov [rbx+%d], rsp'%(8*RSP_BEFORE),'mov [rbx+%d], rbx'%(8*RBX_BEFORE)]
            stub+=['mov %s, 0x%x'%(r,SENTINEL[r])for r in REGS]
            stub+=['push 0x%x'%(0x8d7 if k%2==0 else 0x202),'popfq','pushfq','pop qword [rbx+%d]'%(8*FLAGS_BEFORE)]
            stub+=text.decode('ascii').rstrip('\n').split('\n')if text else []
            stub+=['pushfq','pop qword [rbx+%d]'%(8*FLAGS_AFTER)]
            stub+=['mov [rbx+%d], %s'%(8*(REGS_OUT+j),r)for j,r in enumerate(REGS)]
            stub+=['mov [rbx+%d], rbp'%(8*RBP_AFTER),'mov [rbx+%d], rsp'%(8*RSP_AFTER),'mov [rbx+%d], rbx'%(8*RBX_AFTER)]
            stub+=['cld','lea rsi, [rbp-4096]','lea rdi, [rbx+%d]'%(8*FRAME_OUT),'mov rcx, 514','rep movsq',  # frame + 2 guards
                   'mov rsp, rbp','add rsp, 16','pop r15','pop r14','pop r13','pop r12','pop rbp','pop rbx','ret']
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','#define STATE %d\n'%STATE+'\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(texts))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(texts))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],label+'-native-link')
        images=[image_for(k,v[4])for k,v in enumerate(vectors)]
        payload=b''.join(struct.pack('<512Q',*im)for im in images)
        run=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        n=STATE-512;self.assertEqual(len(run.stdout),8*n*len(vectors))
        for k,(kind,frame,low,high,slots) in enumerate(vectors):
            got=list(struct.unpack_from('<%dQ'%n,run.stdout,8*n*k));at=lambda i:got[i-512]
            image=images[k];regs=dict(zip(REGS,[at(REGS_OUT+j)for j in range(len(REGS))]))
            want_rax=SENTINEL['rax']if kind==VOID else extend(kind,image[index(low)])
            want_rdx=image[index(high)]if kind==PAIR else SENTINEL['rdx']
            self.assertEqual(regs['rax'],want_rax,(label,k,'native rax',kind))
            self.assertEqual(regs['rdx'],want_rdx,(label,k,'native rdx',kind))
            for r in REGS[1:]:
                if r!='rdx':self.assertEqual(regs[r],SENTINEL[r],(label,k,'native register preserved',r))
            self.assertEqual(got[:512],image,(label,k,'native frame slots and guards'))
            self.assertEqual([at(GUARD_OUT),at(GUARD_OUT+1)],GUARDS,(label,k,'native guards above rbp'))
            self.assertEqual((at(RBP_AFTER),at(RSP_AFTER),at(RBX_AFTER)),(at(RBP_BEFORE),at(RSP_BEFORE),at(RBX_BEFORE)),(label,k,'native rbp/rsp/rbx preserved'))
            self.assertEqual(at(FLAGS_AFTER)&ARITH_FLAGS,at(FLAGS_BEFORE)&ARITH_FLAGS,(label,k,'native flags preserved'))

    def test_exact_text_capacity_and_invalid(self):
        cases=[]
        for kind,frame,low,high,_ in VECTORS:
            n=len(expected_text(kind,low,high))
            cases+=[(kind,frame,low,high,n,OK),(kind,frame,low,high,n+7,OK)]
            if n:cases+=[(kind,frame,low,high,n-1,CAPACITY),(kind,frame,low,high,0,CAPACITY)]
        longest=(PAIR,4080,4080,4072);n=len(expected_text(*longest[:1],*longest[2:]))
        self.assertEqual(n,56);cases+=[(*longest,56,OK),(*longest,55,CAPACITY)]
        self.assertEqual(len(expected_text(I32,4080,0)),31);cases+=[(I32,4080,4080,0,31,OK),(I32,4080,4080,0,30,CAPACITY)]
        cases+=[(VOID,0,0,0,0,OK),(VOID,4080,0,0,16,OK)]                  # VOID: empty text, NULL out with capacity 0
        bad=[(12,16,8,0),(U64,16,8,0),(VOID,8,0,0),(UQ,8,8,0),(UQ,4096,8,0),(UQ,2**64-16,8,0),(UQ,24,8,0),
             (VOID,16,8,0),(VOID,16,0,8),(UQ,16,8,8),(UQ,16,0,0),(UQ,16,12,0),(UQ,16,24,0),(UQ,16,U64-7,0),
             (BOOL,4080,4088,0),(PAIR,16,8,8),(PAIR,16,8,0),(PAIR,16,0,8),(PAIR,16,8,24),(PAIR,16,4,8)]
        for kind,frame,low,high in bad:cases+=[(kind,frame,low,high,64,INVALID),(kind,frame,low,high,0,INVALID)]
        for mode,exe in self.executables.items():
            for c,text in zip(cases,self.run_cases(exe,cases,'text-'+mode)):
                if c[-1]==OK:self.assertEqual(text,expected_text(c[0],c[2],c[3]),(mode,c))
        self.records.append(dict(test='exact-text-capacity-invalid',cases=len(cases),preflights_per_native=PREFLIGHTS,longest_bytes=56,modes=2,passed=True))

    def test_native_return_values(self):
        self.assertLessEqual(len(VECTORS),24)
        self.assertEqual({v[0]for v in VECTORS},set(range(12)))                         # all 12 kinds
        self.assertTrue(any(v[0]==PAIR and v[4][v[2]]!=v[4][v[3]]for v in VECTORS))     # PAIR words differ
        self.assertTrue({8,4080}<={o for v in VECTORS for o in v[4]})
        for mode,exe in self.executables.items():
            self.native_run(self.texts(exe,VECTORS,'vectors-'+mode),VECTORS,'native-'+mode)
        self.records.append(dict(test='native-return-values',vectors_per_mode=len(VECTORS),modes=2,formats=['elf64','win64'],passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        signed=[v for v in VECTORS if v[0]in SIGNED and extend(v[0],v[4][v[2]])>>63]       # negative narrow values
        pairs=[v for v in VECTORS if v[0]==PAIR]
        for name,old,new,vectors,reason in [
            ('bad-sign-as-zero','if extension==rp.SIGN{','if false{',signed,'native rax'),
            ('bad-pair-swap','!load(text,&at,"mov rax, qword ",low_offset)||!load(text,&at,"mov rdx, qword ",high_offset)',
             '!load(text,&at,"mov rax, qword ",high_offset)||!load(text,&at,"mov rdx, qword ",low_offset)',pairs,'native r[ad]x')]:
            self.assertEqual(source.count(old),1,name);self.assertGreaterEqual(len(vectors),2,name)
            for mode,exe in self.executables.items():                                       # same inputs pass first
                self.native_run(self.texts(exe,vectors,name+'-good-'+mode),vectors,name+'-good-'+mode)
            for mode,exe in self.build_all(name,source.replace(old,new,1)).items():
                texts=self.texts(exe,vectors,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,reason):self.native_run(texts,vectors,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,linked=True,native_executed=True,modes=2,rejected_by=reason))
        old='if at>out.len{return CAPACITY;}';new='if at>out.len{*written=at;return CAPACITY;}'
        self.assertEqual(source.count(old),1);case=[(PAIR,16,8,16,20,CAPACITY)]
        for mode,exe in self.executables.items():self.run_cases(exe,case,'bad-early-written-good-'+mode)
        for mode,exe in self.build_all('bad-early-written',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.run_cases(exe,case,'bad-early-written-'+mode)
        self.records.append(dict(test='bad-early-written',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))

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
