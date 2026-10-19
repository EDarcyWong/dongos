"""Actual Dong SysV function entry (CR11 prologue with no saved registers + C37 capture). Derived from the C37 test:
actual Dong SysV incoming-argument capture emitter (C8 + CR8 + CR4): exact text, assembly, native entry capture."""
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

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_sysv_function_entry.dg'
DOC=WORKS/'claude-works/src/bootstrap/nasm_sysv_function_entry.md'
# Integrated components and their whole read-only import closure (nothing else from lang is staged).
DEPENDENCIES=[ROOT/'lang/bootstrap'/(n+'.dg')for n in ('nasm_function_frame','decimal_integer',            # CR11, CR4
    'nasm_sysv_incoming_args','sysv_integer_args','nasm_memory_operand')]                                # C37, C8, CR8
OK,INVALID,CAPACITY=0,1,2
ARGS=['rdi','rsi','rdx','rcx','r8','r9']
PREFLIGHTS=19
PATTERN=0x6b6b6b6b6b6b6b6b
AREA=21                                  # outgoing qwords below the caller's frame: arguments then guard (168 bytes)
FLAGS_IN,FLAGS_MASK,FLAGS_WANT=0x8d7,0xcd5,0x8d5   # CF PF AF ZF SF OF set, DF clear
RAX_S,R10_S,R11_S=0x0a0a0a0a0a0a0a0a,0x1010101010101010,0x1111111111111111
CALLEE_SAVED=[0x1212121212121212,0x1313131313131313,0x1414141414141414,0x1515151515151515]
WRAPPER='''module probe.entry_export;
import bootstrap.nasm_sysv_function_entry as c;
import bootstrap.nasm_function_frame as ff;
export("dong_entry_emit") pub unsafe fn emit(kinds:*const u8,nk:usize,offsets:*const usize,no:usize,frame_bytes:usize,out:*u8,nout:usize,written:*usize)u64{unsafe{
 return c.emit(slice_from_raw_parts(kinds,nk),slice_from_raw_parts(offsets,no),frame_bytes,slice_from_raw_parts(out,nout),written);
}}
export("dong_cr11_epilogue") pub unsafe fn epilogue(frame_bytes:usize,mask:u64,out:*u8,nout:usize,written:*usize)u64{unsafe{
 return ff.epilogue(frame_bytes,mask,slice_from_raw_parts(out,nout),written);
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
extern uint64_t ABI dong_entry_emit(const uint8_t*,uint64_t,const uint64_t*,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
extern uint64_t ABI dong_cr11_epilogue(uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
/* Each preflight keeps every other field valid (2 scalars, slots 8/16, frame 16) so only the target check can reject it. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[2048],saved[2048];const unsigned total=19;unsigned failed=0;
 uint8_t*k=arena;uint64_t*f=(uint64_t*)(arena+64);uint8_t*o=arena+512;uint64_t*w=(uint64_t*)(arena+1600);
 for(unsigned i=0;i<total;i++){
  /* all 16 kinds are scalar and all 16 offsets distinct legal slots 8..128 before the snapshot, so the
     len=16 declared-tail alias cases 12/14/16 (frame 128) cannot be masked by a data INVALID */
  memset(arena,0xa5,sizeof(arena));for(unsigned j=0;j<16;j++){k[j]=0;f[j]=8+8*j;}
  memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_entry_emit(k,2,f,2,16,o,512,NULL);break;                              /* written NULL */
   case 1:s=dong_entry_emit(k,2,f,2,16,o,512,(uint64_t*)(arena+1601));break;           /* written odd */
   case 2:s=dong_entry_emit(k,2,f,2,16,NULL,0,FAKE(UINT64_MAX-7));break;               /* written end overflow, legal empty out */
   case 3:s=dong_entry_emit(k,2,f,2,16,FAKE(UINT64_MAX-15),32,w);break;                /* out end overflow */
   case 4:s=dong_entry_emit(k,2,f,2,16,NULL,16,w);break;                               /* NULL non-empty out */
   case 5:s=dong_entry_emit(NULL,2,f,2,16,o,512,w);break;                              /* NULL non-empty kinds */
   case 6:s=dong_entry_emit(FAKE(UINT64_MAX-1),4,f,2,16,o,512,w);break;                /* kinds end overflow */
   case 7:s=dong_entry_emit(k,2,NULL,2,16,o,512,w);break;                              /* NULL non-empty offsets */
   case 8:s=dong_entry_emit(k,2,(uint64_t*)(arena+68),2,16,o,512,w);break;             /* offsets misaligned */
   case 9:s=dong_entry_emit(k,2,f,UINT64_MAX/8+1,16,o,512,w);break;                    /* offsets multiplication overflow */
   case 10:s=dong_entry_emit(k,2,FAKE(UINT64_MAX-15),4,16,o,512,w);break;              /* offsets end overflow */
   case 11:s=dong_entry_emit(k,2,f,2,16,o,512,(uint64_t*)k);break;                     /* written on kinds' aligned prefix */
   case 12:s=dong_entry_emit(k,16,f,16,128,o,512,(uint64_t*)(k+8));break;              /* written in kinds' declared tail */
   case 13:s=dong_entry_emit(k,2,f,2,16,o,512,f);break;                                /* written on offsets prefix */
   case 14:s=dong_entry_emit(k,16,f,16,128,o,512,f+15);break;                          /* written in offsets' declared tail */
   case 15:s=dong_entry_emit(k,2,f,2,16,k,8,w);break;                                  /* out over kinds */
   case 16:s=dong_entry_emit(k,16,f,16,128,(uint8_t*)(f+14),16,w);break;               /* out over offsets' declared tail */
   case 17:s=dong_entry_emit(k,2,f,2,16,o,512,(uint64_t*)o);break;                     /* written on out prefix */
   default:s=dong_entry_emit(k,2,f,2,16,o,512,(uint64_t*)(o+504));break;               /* written in out's unused tail */
  }
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
  uint64_t h[6];read_exact(h,sizeof(h));uint64_t nk=h[0],nf=h[1],frame=h[2],cap=h[3],ro=h[4],op=h[5];
  if(nk>64||nf>64||cap>8192)exit(94);
  uint8_t*in=malloc(nk+nf*8+96),*copy=malloc(nk+nf*8+1),*out=malloc(cap+64);uint64_t meta[3];
  if(!in||!copy||!out)exit(95);
  memset(in,0xa5,nk+nf*8+96);read_exact(in+32,nk);read_exact(in+64+((nk+7)&~7ull),nf*8);
  const uint8_t*k=in+32;const uint64_t*f=(const uint64_t*)(in+64+((nk+7)&~7ull));
  memcpy(copy,k,nk);memcpy(copy+nk,f,nf*8);uint8_t*page=NULL;uint64_t pages=8192,protected_ok=1;
  if(ro){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,k,nk);memcpy(page+1024,f,nf*8);protected_ok=ro_protect(page,pages);k=page;f=(const uint64_t*)(page+1024);}
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));
  uint64_t s=op?dong_cr11_epilogue(frame,0,cap?out+32:NULL,cap,meta+1)
              :dong_entry_emit(nk?k:NULL,nk,nf?f:NULL,nf,frame,cap?out+32:NULL,cap,meta+1);
  uint64_t w=s?0:meta[1];
  uint64_t valid=protected_ok&&filled(meta,8)&&filled(meta+2,8)&&!memcmp(copy,k,nk)&&!memcmp(copy+nk,f,nf*8)&&filled(out,32)&&filled(out+32+cap,32);
  if(s)valid=valid&&filled(meta+1,8)&&filled(out+32,cap);else valid=valid&&w<=cap&&filled(out+32+w,cap-w);
  uint64_t response[3]={s,valid,w};write_exact(response,24);write_exact(out+32,w);
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
/* Commit the stack pages the 4 KiB callee frames and the prefilled region below them will touch. */
static __attribute__((noinline)) void commit_stack(void){volatile uint8_t pages[65536];for(unsigned i=0;i<sizeof(pages);i+=512)pages[i]=(uint8_t)i;}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 commit_stack();
 static uint64_t io[600];
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  memset(io,0,sizeof(io));read_exact(io,32*8);io[599]=0xa5a5a5a5a5a5a5a5ull;
  table[i](io);
  if(io[599]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  if(fwrite(io+32,8,567,stdout)!=567)exit(92);
 }return 0;
}
'''


def oracle(kinds):
    """Independent SysV INTEGER placement: ([(argument register index, word)], [word in stack order], stack_bytes)."""
    free=list(range(6));regs,stack=[],[];word=0
    for k in kinds:
        need=1 if k==0 else 2
        if len(free)>=need:
            for _ in range(need):regs.append((free.pop(0),word));word+=1
        else:
            for _ in range(need):stack.append(word);word+=1
    return regs,stack,-(-8*len(stack)//16)*16


def expected_prologue(frame):return ('push rbp\nmov rbp, rsp\n'+('sub rsp, %d\n'%frame if frame else '')).encode()


def expected_epilogue(frame):return (('add rsp, %d\n'%frame if frame else '')+'pop rbp\nret\n').encode()


def expected_text(kinds,offsets,frame):
    """Independent text model: CR11 prologue with no saved registers, then the C37 capture."""
    regs,stack,_=oracle(kinds);lines=[]
    for reg,word in regs:lines.append('mov qword [rbp - %d], %s'%(offsets[word],ARGS[reg]))
    for slot,word in enumerate(stack):
        lines+=['mov rax, qword [rbp + %d]'%(16+8*slot),'mov qword [rbp - %d], rax'%offsets[word]]
    return expected_prologue(frame)+''.join(l+'\n'for l in lines).encode()


def words(kinds):return sum(1 if k==0 else 2 for k in kinds)


def value(k,w):return (0x8000000000000000|((k+1)<<40)|(w*0x01010101)|0x5000)&(2**64-1)


# (kinds, destination offsets, frame_bytes)
VECTORS=[([],[],0),([0],[8],16),([0]*6,[48,8,40,16,32,24],48),([0]*7,[8*i for i in (3,7,1,5,2,6,4)],64),
         ([0]*8,[128-8*i for i in range(8)],128),([0]*16,[4080,8,2000,3000,16,4072,1000,512,24,32,40,48,56,64,72,80],4080),
         ([0]*5+[1,0],[8,16,24,32,40,56,48,64],64),([0]*6+[1],[64,56,48,40,32,24,16,8],64),([1]*8,[4080-8*i for i in range(16)],4080),
         ([0],[4080],4080),([0,1,0,1,0,0],[16,24,32,40,48,56,64,8],96)]
SAME=7                                 # vector index whose source words repeat one bit pattern


class NasmSysvFunctionEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C44'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
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
        """Stage only this component and its integrated read-only closure, then build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_sysv_function_entry.dg').write_text(text,encoding='utf-8')
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        (root/'probe/entry_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/entry_export.dg',roots=[root],mode=mode)
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
        """cases: (kinds, offsets, frame, cap, readonly, status[, op]); op 1 = CR11 epilogue(frame, 0). Returns text or None."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:
            kinds,offsets,frame,cap,ro=c[:5];op=c[6]if len(c)>6 else 0
            payload.extend(struct.pack('<6Q',len(kinds),len(offsets),frame,cap,ro,op));payload.extend(bytes(kinds))
            payload.extend(struct.pack('<%dQ'%len(offsets),*offsets))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],PREFLIGHTS)
        offset=8;results=[]
        for index,c in enumerate(cases):
            got,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(got,c[5],(label,index,'status',c[2:4]))
            results.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return results

    def native_run(self,texts,vectors,label,epilogues):
        """Hand-written caller sets six registers and [rsp+8j] stack words, calls a callee whose entry is the actual Dong
        output (CR11 prologue + C37 capture) and whose exit is the actual CR11 epilogue(frame, 0)."""
        asm=['bits 64','section .text']
        for k,(text,(kinds,offsets,frame)) in enumerate(zip(texts,vectors)):
            fill=frame//8+8                                        # [rsp_c-64, rbp) where rsp_c = R-16-frame
            asm+=['global v%d'%k,'v%d:'%k,'push rbx','push rbp','push r12','push r13','push r14','push r15','mov rbx, rdi',
                  'sub rsp, %d'%(8*AREA),'cld','mov rax, 0x%x'%PATTERN,'mov rdi, rsp','mov rcx, %d'%AREA,'rep stosq',  # outgoing area
                  'lea rdi, [rsp-%d]'%(16+frame+64),'mov rcx, %d'%fill,'rep stosq']                               # callee frame below
            asm+=['mov rax, [rbx+%d]'%(8*(6+j))+'\nmov [rsp+%d], rax'%(8*j)for j in range(10)]
            asm+=['mov %s, [rbx+%d]'%(r,8*j)for j,r in enumerate(ARGS)]
            asm+=['mov rax, 0x%x'%RAX_S,'mov r10, 0x%x'%R10_S,'mov r11, 0x%x'%R11_S,'mov rbp, 0x%x'%PATTERN]
            asm+=['mov r%d, 0x%x'%(12+j,v)for j,v in enumerate(CALLEE_SAVED)]
            asm+=['mov [rbx+%d], rsp'%(8*49),'push 0x%x'%FLAGS_IN,'popfq','call c%d'%k,'mov [rbx+%d], rsp'%(8*48)]
            asm+=['mov [rbx+%d], rbp'%(8*590),'lea rsi, [rsp]','lea rdi, [rbx+%d]'%(8*50),'mov rcx, %d'%AREA,'rep movsq',
                  'add rsp, %d'%(8*AREA),'pop r15','pop r14','pop r13','pop r12','pop rbp','pop rbx','ret']
            asm+=['c%d:'%k]+text.decode('ascii').rstrip('\n').split('\n')               # actual Dong entry: prologue + capture
            asm+=['mov [rbx+%d], %s'%(8*(32+j),r)for j,r in enumerate(ARGS)]
            asm+=['mov [rbx+%d], rax'%(8*38),'mov [rbx+%d], r10'%(8*39),'mov [rbx+%d], r11'%(8*40)]
            asm+=['mov [rbx+%d], r%d'%(8*(41+j),12+j)for j in range(4)]
            asm+=['pushfq','pop rax','mov [rbx+%d], rax'%(8*45),'mov [rbx+%d], rbp'%(8*46),'mov [rbx+%d], rsp'%(8*47)]
            asm+=['lea rsi, [rsp-64]','lea rdi, [rbx+%d]'%(8*72),'mov rcx, 7','rep movsq']           # low guard (rsp-8 held RFLAGS)
            asm+=['lea rsi, [rsp]','lea rdi, [rbx+%d]'%(8*79),'mov rcx, %d'%(frame//8),'rep movsq']   # frame [rsp, rbp)
            asm+=epilogues[k].decode('ascii').rstrip('\n').split('\n')               # actual CR11 epilogue(frame, 0)
        source=self.work/(label+'.stubs.asm');source.write_text('\n'.join(asm)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.'+fmt+'.o'),source],label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(texts))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(texts))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],label+'-native-link')
        payload=bytearray();plans=[]
        for k,(kinds,offsets,frame) in enumerate(vectors):
            regs,stack,_=oracle(kinds);vals=[value(k,w)if k!=SAME else 0x9e3779b97f4a7c15 for w in range(words(kinds))]
            io=[0]*32
            for reg,w in regs:io[reg]=vals[w]
            for slot,w in enumerate(stack):io[6+slot]=vals[w]
            plans.append((io,vals));payload.extend(struct.pack('<32Q',*io))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        for k,(kinds,offsets,frame) in enumerate(vectors):
            got=struct.unpack_from('<567Q',run.stdout,567*8*k);io,vals=plans[k];at=lambda i:got[i-32]
            regs,stack,_=oracle(kinds)
            image=[at(79+j)for j in range(frame//8)]                # image[j] is [rbp-frame+8j]
            want=[PATTERN]*(frame//8)
            for w,o in enumerate(offsets):want[(frame-o)//8]=vals[w]
            for w,o in enumerate(offsets):self.assertEqual(image[(frame-o)//8],vals[w],(label,k,'native captured slot',o))
            self.assertEqual(image,want,(label,k,'native untargeted frame words'))
            self.assertEqual([at(72+j)for j in range(7)],[PATTERN]*7,(label,k,'native guard below frame'))
            self.assertEqual([at(32+j)for j in range(6)],io[:6],(label,k,'native argument registers preserved'))
            if not stack:self.assertEqual(at(38),RAX_S,(label,k,'native rax kept without stack words'))
            self.assertEqual([at(39),at(40)],[R10_S,R11_S],(label,k,'native other GPRs kept'))
            self.assertEqual([at(41+j)for j in range(4)],CALLEE_SAVED,(label,k,'native callee-saved preserved'))
            if frame==0:self.assertEqual(at(45)&FLAGS_MASK,FLAGS_WANT,(label,k,'native flags preserved'))   # 'sub rsp' changes flags
            self.assertEqual(at(46)-at(47),frame,(label,k,'native rbp/rsp frame'))
            self.assertEqual(at(48),at(49),(label,k,'native stack balance'))
            self.assertEqual(at(590),PATTERN,(label,k,'native caller rbp restored'))
            area=[at(50+j)for j in range(AREA)];want_area=[PATTERN]*AREA
            for slot in range(len(stack)):want_area[slot]=io[6+slot]
            for j in range(10):
                if j>=len(stack):want_area[j]=io[6+j]                # caller wrote all 10 argument words
            self.assertEqual(area,want_area,(label,k,'native incoming stack arguments untouched'))

    def test_exact_text_capacity_and_invalid(self):
        cases=[]
        for k,(kinds,offsets,frame) in enumerate(VECTORS):
            n=len(expected_text(kinds,offsets,frame))
            cases+=[(kinds,offsets,frame,n,int(k%3==0),OK),(kinds,offsets,frame,n+9,0,OK)]
            cases+=[(kinds,offsets,frame,n-1,0,CAPACITY),(kinds,offsets,frame,0,0,CAPACITY)]
        longest=([0]*16,[4080-8*i for i in range(16)],4080);n=len(expected_text(*longest))
        cases+=[(*longest,n,1,OK),(*longest,n-1,0,CAPACITY),(*longest,0,0,CAPACITY),
                ([],[],4080,36,1,OK),([],[],4080,35,0,CAPACITY),([],[],0,22,0,OK),([],[],0,0,0,CAPACITY)]   # prologue only
        cases+=[([],[],8,0,0,INVALID),([0],[8],4096,64,0,INVALID),([0],[8],24,64,0,INVALID),([0],[8],2**64-16,64,0,INVALID),
                ([2],[8],16,64,1,INVALID),([0]*17,[8*(i+1)for i in range(17)],4080,0,0,INVALID),([1]*9,[8*(i+1)for i in range(18)],4080,64,0,INVALID),
                ([0,0],[8],16,64,0,INVALID),([0],[8,16],16,64,1,INVALID),([0],[0],16,64,0,INVALID),([0],[4],16,0,0,INVALID),
                ([0],[24],16,64,0,INVALID),([0,0,0],[8,16,8],16,64,1,INVALID),([0]*7,[8,16,24,32,40,48,16],64,0,0,INVALID),
                ([0],[2**64-8],4080,64,0,INVALID),
                ([2],[8],16,0,0,INVALID),([0,0xff],[8,16],16,0,1,INVALID)]   # illegal kind with capacity 0: INVALID before CAPACITY
        for mode,exe in self.executables.items():
            results=self.run_cases(exe,cases,'text-'+mode)
            for c,text in zip(cases,results):
                if c[-1]==OK:self.assertEqual(text,expected_text(c[0],c[1],c[2]),(mode,c[0],c[2]))
        self.assertLessEqual(n,36+880)
        self.records.append(dict(test='exact-text-capacity-invalid',cases=len(cases),preflights_per_native=PREFLIGHTS,
                                 longest_bytes=n,modes=2,passed=True))

    def texts(self,exe,vectors,label):
        return self.run_cases(exe,[(*v,2048,0,OK)for v in vectors],label)

    def epilogues(self,exe,vectors,label):
        """Actual CR11 epilogue(frame, 0) text from the same executable, checked against the independent model."""
        out=self.run_cases(exe,[([],[],v[2],64,0,OK,1)for v in vectors],label)
        for v,text in zip(vectors,out):self.assertEqual(text,expected_epilogue(v[2]))
        return out

    def test_text_assembles_in_both_formats(self):
        for mode,exe in self.executables.items():
            source=self.work/('incoming-'+mode+'.asm');source.write_bytes(b'bits 64\nsection .text\n'+b''.join(self.texts(exe,VECTORS,'asm-'+mode)))
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('incoming-%s.%s.o'%(mode,fmt)),source],'incoming-%s-%s'%(mode,fmt))
        self.records.append(dict(test='incoming-assemble',formats=['elf64','win64'],modes=2,passed=True))

    def test_native_entry_capture(self):
        for mode,exe in self.executables.items():
            self.native_run(self.texts(exe,VECTORS,'vectors-'+mode),VECTORS,'native-'+mode,self.epilogues(exe,VECTORS,'epilogue-'+mode))
        self.records.append(dict(test='native-entry-capture',vectors_per_mode=len(VECTORS),modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        call='if inc.emit(kinds,destination_offsets,frame_bytes,'
        swap=('var sw:[16]usize=[0;16];var q:usize=0;while q<destination_offsets.len&&q<16{sw[q]=destination_offsets[q];q+=1;}\n'
              ' if destination_offsets.len>=2{let t=sw[0];sw[0]=sw[1];sw[1]=t;}\n'
              ' if inc.emit(kinds,slice_from_raw_parts(&sw[0],destination_offsets.len),frame_bytes,')
        self.assertEqual(source.count(call),1)
        vectors=[v for v in VECTORS if words(v[0])>=2][:4]                    # two legal, distinct slots swapped
        for mode,exe in self.executables.items():
            self.native_run(self.texts(exe,vectors,'bad-slot-swap-good-'+mode),vectors,'bad-slot-swap-good-'+mode,
                            self.epilogues(exe,vectors,'bad-slot-swap-epi-'+mode))
        for mode,exe in self.build_all('bad-slot-swap',source.replace(call,swap,1)).items():
            texts=self.texts(exe,vectors,'bad-slot-swap-'+mode)
            with self.assertRaisesRegex(AssertionError,'native captured slot'):
                self.native_run(texts,vectors,'bad-slot-swap-'+mode,self.epilogues(exe,vectors,'bad-slot-swap-epi2-'+mode))
        self.records.append(dict(test='bad-slot-swap',compiled=True,native_executed=True,modes=2,rejected_by='native captured slot'))
        old='if at>on{return CAPACITY;}'
        new='if at>on{var j:usize=0;while j<at&&j<on{out[j]=buffer[j];j+=1;}return CAPACITY;}'
        self.assertEqual(source.count(old),1)
        v=VECTORS[4];case=[(*v,len(expected_prologue(v[2])),0,CAPACITY)]        # capacity fits only the prologue
        for mode,exe in self.executables.items():self.run_cases(exe,case,'bad-early-prologue-good-'+mode)
        for mode,exe in self.build_all('bad-early-prologue',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.run_cases(exe,case,'bad-early-prologue-'+mode)
        self.records.append(dict(test='bad-early-prologue',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))

    def test_selective_tail_alias_checks_are_each_reachable(self):
        """Preflight sensitivity: three real Dong sources each truncate one input/written/out alias check to a prefix."""
        source=SOURCE.read_text(encoding='utf-8')
        for mode,exe in self.executables.items():self.run_cases(exe,[],'alias-good-'+mode)   # same harness passes all 19
        for name,old,new,target in [
            ('bad-kinds-written-prefix','overlap(kp,kn,wp,8)','overlap(kp,2,wp,8)',12),
            ('bad-offsets-written-prefix','overlap(dp,dn,wp,8)','overlap(dp,16,wp,8)',14),
            ('bad-offsets-out-prefix','overlap(dp,dn,op,on)','overlap(dp,16,op,on)',16)]:
            self.assertEqual(source.count(old),1,name)
            for mode,exe in self.build_all(name,source.replace(old,new,1)).items():
                run=subprocess.run([str(exe)],input=struct.pack('<Q',0),capture_output=True,timeout=60)
                err=run.stderr.decode('ascii','replace');(self.work/(name+'-'+mode+'.stderr')).write_text(err,encoding='ascii')
                self.assertEqual(run.returncode,93,(name,mode,err))                          # normal exit from the preflight check
                failed=[int(line.split()[2])for line in err.splitlines()if line.startswith('invalid preflight ')]
                self.assertEqual(failed,[target],(name,mode,err))                            # exactly the target alias case
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by='preflight %d'%target))


if __name__=='__main__':unittest.main()
