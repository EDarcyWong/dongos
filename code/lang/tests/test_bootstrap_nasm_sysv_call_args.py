"""Actual Dong SysV call-argument setup/cleanup emitter (C8 + CR8 + CR4): exact text, assembly, native calls."""
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

SOURCE=ROOT/'lang/bootstrap/nasm_sysv_call_args.dg'
DEPENDENCIES=[ROOT/'lang/bootstrap'/n for n in ('sysv_integer_args.dg','nasm_memory_operand.dg','decimal_integer.dg')]  # C8, CR8, CR4
OK,INVALID,CAPACITY=0,1,2
ARGS=['rdi','rsi','rdx','rcx','r8','r9']
PAD=0x5a5a5a5a5a5a5a5a
SENTINELS=[0x1212121212121212,0x1313131313131313,0x1414141414141414,0x1515151515151515]
RAX_SENTINEL,R10_SENTINEL,R11_SENTINEL=0x0a0a0a0a0a0a0a0a,0x1010101010101010,0x1111111111111111
WRAPPER='''module probe.callargs_export;
import bootstrap.nasm_sysv_call_args as c;
export("dong_args_setup") pub unsafe fn setup(kinds:*const u8,nk:usize,offsets:*const usize,no:usize,out:*u8,nout:usize,result:*c.Result)u64{unsafe{
 return c.setup(slice_from_raw_parts(kinds,nk),slice_from_raw_parts(offsets,no),slice_from_raw_parts(out,nout),result);
}}
export("dong_args_cleanup") pub unsafe fn cleanup(stack_bytes:usize,out:*u8,nout:usize,written:*usize)u64{unsafe{
 return c.cleanup(stack_bytes,slice_from_raw_parts(out,nout),written);
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
typedef struct {uint64_t written,stack_bytes;} Result;
_Static_assert(sizeof(Result)==16&&__builtin_offsetof(Result,stack_bytes)==8,"Result layout");
extern uint64_t ABI dong_args_setup(const uint8_t*,uint64_t,const uint64_t*,uint64_t,uint8_t*,uint64_t,Result*);
extern uint64_t ABI dong_args_cleanup(uint64_t,uint8_t*,uint64_t,uint64_t*);
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
/* Each preflight keeps every other field valid so only the target check can reject it. Before the snapshot all
   16 kinds are scalar and all 16 offsets are legal (8..128), so the len=16 alias cases 11/13/15 have word count
   equal to offset count and cannot be masked by a data INVALID. Every failing preflight is reported, then exit 93. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[2048],saved[2048];const unsigned total=28;unsigned failed=0;
 uint8_t*k=arena;uint64_t*f=(uint64_t*)(arena+64);uint8_t*o=arena+512;Result*r=(Result*)(arena+1536);uint64_t*w=(uint64_t*)(arena+1600);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));for(unsigned j=0;j<16;j++){k[j]=0;f[j]=8+8*j;}
  memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_args_setup(k,2,f,2,o,512,NULL);break;                                   /* result NULL */
   case 1:s=dong_args_setup(k,2,f,2,o,512,(Result*)(arena+1540));break;                  /* result misaligned */
   case 2:s=dong_args_setup(k,2,f,2,o,512,FAKE(UINT64_MAX-15));break;                    /* result end overflow */
   case 3:s=dong_args_setup(NULL,2,f,2,o,512,r);break;                                   /* NULL non-empty kinds */
   case 4:s=dong_args_setup(FAKE(UINT64_MAX-1),4,f,2,o,512,r);break;                     /* kinds end overflow */
   case 5:s=dong_args_setup(k,2,NULL,2,o,512,r);break;                                   /* NULL non-empty offsets */
   case 6:s=dong_args_setup(k,2,(uint64_t*)(arena+68),2,o,512,r);break;                  /* offsets misaligned */
   case 7:s=dong_args_setup(k,2,f,UINT64_MAX/8+1,o,512,r);break;                         /* offsets length overflow */
   case 8:s=dong_args_setup(k,2,FAKE(UINT64_MAX-15),4,o,512,r);break;                    /* offsets end overflow */
   case 9:s=dong_args_setup(k,2,f,2,NULL,512,r);break;                                   /* NULL non-empty out */
   case 10:s=dong_args_setup(k,2,f,2,FAKE(UINT64_MAX-15),32,r);break;                    /* out end overflow */
   case 11:s=dong_args_setup(k,16,f,16,o,512,(Result*)k);break;                          /* result on kinds aligned prefix */
   case 12:s=dong_args_setup(k,2,f,2,o,512,(Result*)f);break;                            /* result on offsets prefix */
   case 13:s=dong_args_setup(k,16,f,16,o,512,(Result*)(f+14));break;                     /* result in offsets' declared tail */
   case 14:s=dong_args_setup(k,2,f,2,k,8,r);break;                                       /* out over kinds */
   case 15:s=dong_args_setup(k,16,f,16,(uint8_t*)(f+15),16,r);break;                     /* out over offsets tail */
   case 16:s=dong_args_setup(k,2,f,2,o,512,(Result*)(o+496));break;                      /* result in out's unused tail */
   case 17:s=dong_args_setup(k,2,f,2,o,512,(Result*)o);break;                            /* result on out prefix */
   case 26:s=dong_args_setup(k,2,f,2,o,512,(Result*)(arena+56));break;                   /* only result's second word on offsets[0] */
   case 27:s=dong_args_setup(k,2,f,2,o,512,(Result*)(arena+504));break;                  /* only result's second word on out[0] */
   case 18:s=dong_args_cleanup(16,o,64,NULL);break;                                      /* cleanup: written NULL */
   case 19:s=dong_args_cleanup(16,o,64,(uint64_t*)(arena+1601));break;                   /* written odd */
   case 20:s=dong_args_cleanup(16,NULL,0,FAKE(UINT64_MAX-7));break;                      /* written end overflow, empty out */
   case 21:s=dong_args_cleanup(16,FAKE(UINT64_MAX-3),8,w);break;                         /* out end overflow */
   case 22:s=dong_args_cleanup(16,o,64,(uint64_t*)(o+56));break;                         /* written in out tail */
   case 23:s=dong_args_cleanup(8,NULL,0,w);break;                                        /* not a multiple of 16, capacity 0 */
   case 24:s=dong_args_cleanup(144,o,64,w);break;                                        /* above 128 */
   default:s=dong_args_cleanup(UINT64_MAX,o,64,w);break;
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
  uint64_t h[6];read_exact(h,sizeof(h));uint64_t op=h[0],nk=h[1],nf=h[2],cap=h[3],ro=h[4],bytes=h[5];
  if(nk>64||nf>64||cap>8192)exit(94);
  uint8_t*in=malloc(nk+nf*8+96),*copy=malloc(nk+nf*8+1),*out=malloc(cap+64);uint64_t meta[6];
  if(!in||!copy||!out)exit(95);
  memset(in,0xa5,nk+nf*8+96);read_exact(in+32,nk);read_exact(in+64+((nk+7)&~7ull),nf*8);
  const uint8_t*k=in+32;const uint64_t*f=(const uint64_t*)(in+64+((nk+7)&~7ull));
  memcpy(copy,k,nk);memcpy(copy+nk,f,nf*8);uint8_t*page=NULL;uint64_t pages=4096*2,protected_ok=1;
  if(ro){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,k,nk);memcpy(page+1024,f,nf*8);protected_ok=ro_protect(page,pages);k=page;f=(const uint64_t*)(page+1024);}
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));
  uint64_t s,valid,w;
  if(op==0){
   Result*r=(Result*)(meta+2);
   s=dong_args_setup(nk?k:NULL,nk,nf?f:NULL,nf,cap?out+32:NULL,cap,r);
   valid=filled(meta,16)&&filled(meta+4,16);w=s?0:r->written;bytes=s?0:r->stack_bytes;
   if(s)valid=valid&&filled(r,16);
  }else{
   uint64_t*written=meta+1;
   s=dong_args_cleanup(bytes,cap?out+32:NULL,cap,written);
   valid=filled(meta,8)&&filled(meta+2,8);w=s?0:*written;bytes=0;
   if(s)valid=valid&&filled(written,8);
  }
  valid=valid&&protected_ok&&!memcmp(copy,k,nk)&&!memcmp(copy+nk,f,nf*8)&&filled(out,32)&&filled(out+32+cap,32);
  if(s)valid=valid&&filled(out+32,cap);else valid=valid&&w<=cap&&filled(out+32+w,cap-w);
  uint64_t response[4]={s,valid,w,bytes};write_exact(response,32);write_exact(out+32,w);
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
 static uint64_t io[1056];
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  memset(io,0,sizeof(io));read_exact(io,512*8);io[1055]=0xa5a5a5a5a5a5a5a5ull;
  table[i](io);
  if(io[1055]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  if(fwrite(io+512,8,540,stdout)!=540)exit(92);
 }return 0;
}
'''


def operand_rbp(offset):return '[rbp - %d]'%offset
def operand_rsp(index):return '[rsp]' if index==0 else '[rsp + %d]'%index


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


def expected_text(kinds,offsets):
    regs,stack,bytes_=oracle(kinds);lines=[]
    if bytes_:lines.append('sub rsp, %d'%bytes_)
    for slot,word in enumerate(stack):
        lines+=['mov rax, qword '+operand_rbp(offsets[word]),'mov qword %s, rax'%operand_rsp(8*slot)]
    order=sorted(regs,key=lambda rw:rw[1])
    for reg,word in order:lines.append('mov %s, qword %s'%(reg,operand_rbp(offsets[word])))
    return ''.join(l+'\n'for l in lines).encode(),bytes_


def words(kinds):return sum(1 if k==0 else 2 for k in kinds)


def offsets_for(kinds,start=8,step=8):
    return [start+step*i for i in range(words(kinds))]


VECTORS=[([],[]),([0],[8]),([0]*6,offsets_for([0]*6)),([0]*7,offsets_for([0]*7,16)),([0]*8,offsets_for([0]*8,8,24)),
         ([0]*16,[4096-8*i for i in range(16)]),([0]*5+[1,0],offsets_for([0]*5+[1,0],32)),([0]*6+[1],offsets_for([0]*6+[1],8,16)),
         ([0,0,1,0],[8,8,4096,8,16]),([1,1,1,1,1,1,1,1],[4096]*16),([0]*7,[8]*7),([1,0,1,0,1,0,1,0,0,0,0,0],offsets_for([1,0]*4+[0]*4,40))]


class NasmSysvCallArgsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'build/test/bootstrap-nasm-sysv-call-args'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,*DEPENDENCIES,Path(__file__)]}
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.executables=cls.build_all('good',SOURCE.read_text(encoding='utf-8'))

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build_all(cls,name,text):
        """Stage only this component and the integrated C8/CR8/CR4 modules, then build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_sysv_call_args.dg').write_text(text,encoding='utf-8')
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        (root/'probe/callargs_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/callargs_export.dg',roots=[root],mode=mode)
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
        """cases: ('setup',kinds,offsets,cap,readonly,status) or ('cleanup',bytes,cap,status). Returns (text, stack_bytes)."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:
            if c[0]=='setup':
                _,kinds,offsets,cap,ro,_=c
                payload.extend(struct.pack('<6Q',0,len(kinds),len(offsets),cap,ro,0));payload.extend(bytes(kinds))
                payload.extend(struct.pack('<%dQ'%len(offsets),*offsets))
            else:
                _,b,cap,_=c;payload.extend(struct.pack('<6Q',1,0,0,cap,0,b))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],28)
        offset=8;results=[]
        for index,c in enumerate(cases):
            got,guard,written,bytes_=struct.unpack_from('<4Q',run.stdout,offset);offset+=32
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(got,c[-1],(label,index,'status',c[:3]))
            results.append((text if got==OK else None,bytes_))
        self.assertEqual(offset,len(run.stdout))
        return results

    def native_run(self,setups,cleanups,vectors,label):
        """Each stub builds a 4104-byte frame holding the source slots, runs setup, calls a capturing callee, runs cleanup."""
        stub=['bits 64','section .text']
        for k,(setup_text,cleanup_text) in enumerate(zip(setups,cleanups)):
            stub+=['global v%d'%k,'v%d:'%k,'push rbx','push r12','push r13','push r14','push r15','push rbp','mov rbp, rsp',
                   'sub rsp, 4104','mov rbx, rdi','cld',
                   'lea rsi, [rbx]','lea rdi, [rbp-4096]','mov rcx, 512','rep movsq',               # frame image in
                   'sub rsp, 192','mov rdi, rsp','mov rax, 0x%x'%PAD,'mov rcx, 24','rep stosq','add rsp, 192']  # outgoing area pattern
            stub+=['mov r%d, 0x%x'%(12+j,s)for j,s in enumerate(SENTINELS)]+['mov [rbx+%d], rsp'%(8*1043)]
            stub+=['mov rax, 0x%x'%RAX_SENTINEL,'mov r10, 0x%x'%R10_SENTINEL,'mov r11, 0x%x'%R11_SENTINEL]
            stub+=setup_text.decode('ascii').rstrip('\n').split('\n')if setup_text else []
            stub+=['call c%d'%k]
            stub+=cleanup_text.decode('ascii').rstrip('\n').split('\n')if cleanup_text else []
            stub+=['mov [rbx+%d], rsp'%(8*1044)]+['mov [rbx+%d], r%d'%(8*(1045+j),12+j)for j in range(4)]
            stub+=['lea rsi, [rbp-4096]','lea rdi, [rbx+%d]'%(8*512),'mov rcx, 512','rep movsq',          # frame image out
                   'mov rsp, rbp','pop rbp','pop r15','pop r14','pop r13','pop r12','pop rbx','ret']
            stub+=['c%d:'%k,'mov [rbx+%d], rax'%(8*1049),'mov [rbx+%d], r10'%(8*1050),'mov [rbx+%d], r11'%(8*1051)]
            stub+=['mov [rbx+%d], %s'%(8*(1024+j),r)for j,r in enumerate(ARGS)]
            for j in range(12):stub+=['mov rax, [rsp+%d]'%(8+8*j),'mov [rbx+%d], rax'%(8*(1030+j))]
            stub+=['mov rax, rsp','and rax, 15','mov [rbx+%d], rax'%(8*1042),'ret']
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(setups))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(setups))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],label+'-native-link')
        payload=bytearray();images=[]
        for k,(kinds,offsets) in enumerate(vectors):
            image=[0x6b6b000000000000+j for j in range(512)]                # [rbp-4096+8j], guard pattern everywhere
            for o in set(offsets):image[(4096-o)//8]=0x0100000000000000*(k+1)+o*0x10001
            images.append(image);payload.extend(struct.pack('<512Q',*image))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        for k,(kinds,offsets) in enumerate(vectors):
            got=list(struct.unpack_from('<540Q',run.stdout,540*8*k));image=images[k]
            value=lambda w:image[(4096-offsets[w])//8]
            regs,stack,bytes_=oracle(kinds)
            captured=dict(zip(ARGS,got[512:518]));stack_seen=got[518:530]
            for reg,w in regs:self.assertEqual(captured[reg],value(w),(label,k,'native register argument',reg))
            for slot,w in enumerate(stack):self.assertEqual(stack_seen[slot],value(w),(label,k,'native stack argument',slot))
            if bytes_>8*len(stack):self.assertEqual(stack_seen[len(stack)],PAD,(label,k,'native padding untouched'))
            self.assertEqual(got[530],8,(label,k,'native callee entry alignment'))
            self.assertEqual(got[531],got[532],(label,k,'native rsp restored after cleanup'))
            self.assertEqual(got[533:537],SENTINELS,(label,k,'native callee-saved preserved'))
            self.assertEqual(got[:512],image,(label,k,'native source slots and guards'))
            if not stack:self.assertEqual(got[537],RAX_SENTINEL,(label,k,'native rax kept without stack words'))
            self.assertEqual(got[538:540],[R10_SENTINEL,R11_SENTINEL],(label,k,'native other GPRs kept'))

    def texts_for(self,exe,vectors,label):
        setups=self.run_cases(exe,[('setup',k,o,2048,0,OK)for k,o in vectors],label+'-setup')
        cleanups=self.run_cases(exe,[('cleanup',b,64,OK)for _,b in setups],label+'-cleanup')
        return [t for t,_ in setups],[t for t,_ in cleanups],[b for _,b in setups]

    def test_exact_text_capacity_and_invalid(self):
        cases=[]
        for k,(kinds,offsets) in enumerate(VECTORS):
            text,_=expected_text(kinds,offsets);n=len(text)
            cases+=[('setup',kinds,offsets,n,int(k%3==0),OK),('setup',kinds,offsets,n+9,0,OK)]
            if n:cases+=[('setup',kinds,offsets,n-1,0,CAPACITY),('setup',kinds,offsets,0,0,CAPACITY)]
        longest=([0]*16,[4096]*16)
        cases+=[('setup',*longest,len(expected_text(*longest)[0]),1,OK),('setup',[],[],0,1,OK)]
        cases+=[('setup',[2],[8],64,0,INVALID),('setup',[0]*17,[8]*17,0,0,INVALID),('setup',[1]*9,[8]*18,64,0,INVALID),
                ('setup',[0,0],[8],64,0,INVALID),('setup',[0],[8,16],64,1,INVALID),('setup',[0],[0],64,0,INVALID),
                ('setup',[0],[4],0,0,INVALID),('setup',[0],[4097],64,0,INVALID),('setup',[0],[4104],64,0,INVALID),
                ('setup',[0],[2**64-8],64,0,INVALID),('setup',[0,1],[8,16,12],0,1,INVALID)]
        for b in (0,16,32,48,64,80,96,112,128):
            n=0 if b==0 else len(b'add rsp, %d\n'%b);cases+=[('cleanup',b,n,OK),('cleanup',b,n+5,OK)]
            if n:cases+=[('cleanup',b,n-1,CAPACITY),('cleanup',b,0,CAPACITY)]
        cases+=[('cleanup',8,64,INVALID),('cleanup',129,0,INVALID),('cleanup',144,64,INVALID),('cleanup',2**64-1,64,INVALID)]
        for mode,exe in self.executables.items():
            results=self.run_cases(exe,cases,'text-'+mode)
            for c,(text,bytes_) in zip(cases,results):
                if c[-1]!=OK:continue
                if c[0]=='setup':
                    want,want_bytes=expected_text(c[1],c[2]);self.assertEqual((text,bytes_),(want,want_bytes),(mode,c[1]))
                else:self.assertEqual(text,b''if c[1]==0 else b'add rsp, %d\n'%c[1],(mode,c[1]))
        self.assertLessEqual(len(expected_text(*longest)[0]),893)
        self.records.append(dict(test='exact-text-capacity-invalid',cases=len(cases),preflights_per_native=28,
                                 longest_setup_bytes=len(expected_text(*longest)[0]),modes=2,passed=True))

    def test_text_assembles_in_both_formats(self):
        for mode,exe in self.executables.items():
            setups,cleanups,_=self.texts_for(exe,VECTORS,'asm-'+mode)
            source=self.work/('callargs-'+mode+'.asm');source.write_bytes(b'bits 64\nsection .text\n'+b''.join(setups)+b''.join(cleanups))
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('callargs-%s.%s.o'%(mode,fmt)),source],'callargs-%s-%s'%(mode,fmt))
        self.records.append(dict(test='callargs-assemble',formats=['elf64','win64'],modes=2,passed=True))

    def test_native_calls_receive_the_arguments(self):
        for mode,exe in self.executables.items():
            setups,cleanups,_=self.texts_for(exe,VECTORS,'vectors-'+mode)
            self.native_run(setups,cleanups,VECTORS,'native-'+mode)
        self.records.append(dict(test='native-call-arguments',vectors_per_mode=len(VECTORS),modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        old='let di=locations[i].index;';new='var di=locations[i].index;if di==0{di=8;}';self.assertEqual(source.count(old),1)
        vectors=[VECTORS[3]]                                   # 7 scalars: one stack word in a 16-byte area (padding slot is allocated)
        for mode,exe in self.executables.items():
            self.native_run(*self.texts_for(exe,vectors,'bad-slot-good-'+mode)[:2],vectors,'bad-slot-good-'+mode)
        for mode,exe in self.build_all('bad-first-stack-slot',source.replace(old,new,1)).items():
            setups,cleanups,_=self.texts_for(exe,vectors,'bad-slot-'+mode)
            with self.assertRaisesRegex(AssertionError,'native stack argument'):self.native_run(setups,cleanups,vectors,'bad-slot-'+mode)
        self.records.append(dict(test='bad-first-stack-slot',compiled=True,native_executed=True,modes=2,rejected_by='native stack argument'))
        for name,old,new,case in [
            ('bad-early-setup','if at>out.len{return CAPACITY;}\n i=0;while i<at{out[i]=buffer[i];i+=1;}',
             'i=0;while i<at&&i<out.len{out[i]=buffer[i];i+=1;}\n if at>out.len{return CAPACITY;}',[('setup',[0]*7,offsets_for([0]*7),10,0,CAPACITY)]),
            ('bad-early-cleanup','if at>out.len{return CAPACITY;}\n var i:usize=0;while i<at{out[i]=buffer[i];i+=1;}',
             'if at>out.len{*written=at;return CAPACITY;}\n var i:usize=0;while i<at{out[i]=buffer[i];i+=1;}',[('cleanup',16,5,CAPACITY)])]:
            self.assertEqual(source.count(old),1,name)
            for mode,exe in self.executables.items():self.run_cases(exe,case,name+'-good-'+mode)
            for mode,exe in self.build_all(name,source.replace(old,new,1)).items():
                with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.run_cases(exe,case,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))

    def test_selective_alias_checks_are_each_reachable(self):
        """Preflight sensitivity: three real Dong sources each drop or truncate one input/Result/out alias check."""
        source=SOURCE.read_text(encoding='utf-8')
        for mode,exe in self.executables.items():self.run_cases(exe,[],'alias-good-'+mode)   # same harness passes all 28
        for name,old,new,target in [
            ('bad-no-kinds-result','||overlap(kp,kn,rp,rn)','',11),
            ('bad-offsets-result-prefix','overlap(sp,sn,rp,rn)','overlap(sp,16,rp,rn)',13),
            ('bad-offsets-out-prefix','overlap(sp,sn,op,on)','overlap(sp,16,op,on)',15)]:
            self.assertEqual(source.count(old),1,name)
            for mode,exe in self.build_all(name,source.replace(old,new,1)).items():
                run=subprocess.run([str(exe)],input=struct.pack('<Q',0),capture_output=True,timeout=60)
                err=run.stderr.decode('ascii','replace');(self.work/(name+'-'+mode+'.stderr')).write_text(err,encoding='ascii')
                self.assertEqual(run.returncode,93,(name,mode,err))                          # normal exit from the preflight check
                failed=[int(line.split()[2])for line in err.splitlines()if line.startswith('invalid preflight ')]
                self.assertEqual(failed,[target],(name,mode,err))                            # exactly the target alias case
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by='preflight %d'%target))


if __name__=='__main__':unittest.main()
