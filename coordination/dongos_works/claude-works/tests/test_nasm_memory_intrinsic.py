"""Actual Dong NASM byte copy/zero emitter: exact text, dual-format assembly, and native rep movsb/stosb execution."""
import hashlib
import json
import os
from pathlib import Path
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

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_memory_intrinsic.dg'
OK,INVALID,CAPACITY=0,1,2
COPY,ZERO=0,1
ARITH_FLAGS=0x8d5
DF=0x400
GUARD=32
WRAPPER='''module probe.mem_export;
import bootstrap.nasm_memory_intrinsic as m;
export("dong_mem_emit") pub unsafe fn emit(operation:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(operation,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_mem_emit(uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
/* Each preflight keeps every other field valid so only the target check can reject it. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[512],saved[512];const unsigned total=10;
 uint8_t*o=arena+64;uint64_t*w=(uint64_t*)(arena+256);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_mem_emit(0,o,32,NULL);break;                                    /* written NULL */
   case 1:s=dong_mem_emit(1,o,32,(uint64_t*)(arena+257));break;                  /* written odd */
   case 2:s=dong_mem_emit(0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;  /* written end overflow, empty out */
   case 3:s=dong_mem_emit(1,(uint8_t*)(uintptr_t)(UINT64_MAX-3),8,w);break;      /* out end overflow */
   case 4:s=dong_mem_emit(0,NULL,32,w);break;                                    /* NULL non-empty out */
   case 5:s=dong_mem_emit(1,o,32,(uint64_t*)o);break;                            /* written on out prefix */
   case 6:s=dong_mem_emit(0,o,64,(uint64_t*)(o+56));break;                       /* written in out's unused tail */
   case 7:s=dong_mem_emit(2,NULL,0,w);break;                                     /* bad operation, capacity 0 */
   case 8:s=dong_mem_emit(UINT64_MAX,o,32,w);break;
   default:s=dong_mem_emit(3,o,1,w);break;
  }
  if(s!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)s);exit(93);}
 }
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[2];read_exact(h,sizeof(h));uint64_t cap=h[1];if(cap>4096)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=dong_mem_emit(h[0],cap?out+32:NULL,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(s)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={s,valid,s?0:*written};write_exact(response,24);write_exact(out+32,s?0:*written);
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
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#else
#include <sys/mman.h>
#endif
#define ABI __attribute__((sysv_abi))
#define GUARD 32
typedef void ABI (*stub)(uint64_t*);
%DECLS%
static const stub table[]={%TABLE%};
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
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
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  /* input: count, rax, sentinels for rdx r8 r9 r10, then count source bytes */
  uint64_t h[6];read_exact(h,sizeof(h));uint64_t n=h[0];if(n>4096)exit(94);
  uint8_t*src_bytes=malloc(n+1);read_exact(src_bytes,n);
  uint8_t*dst_area=malloc(n+2*GUARD);memset(dst_area,0xa5,n+2*GUARD);       /* destination prefilled non-zero */
  uint8_t*page=NULL;uint64_t pages=(n/4096+2)*4096;uint64_t protected_ok=1;
  const uint8_t*src=NULL;uint8_t*dst=NULL;
  if(n){page=ro_alloc(pages);if(!page)exit(95);memset(page,0x3c,pages);memcpy(page+GUARD,src_bytes,n);
   protected_ok=ro_protect(page,pages);src=page+GUARD;dst=dst_area+GUARD;}
  /* state: [0] rax [1] rcx [2] rdx [3] rsi [4] rdi [5] r8 [6] r9 [7] r10 [8] flags before [9] flags after */
  uint64_t state[12]={0xa5a5a5a5a5a5a5a5ull,h[1],n,h[2],(uint64_t)(uintptr_t)src,(uint64_t)(uintptr_t)dst,h[3],h[4],h[5],0,0,0xa5a5a5a5a5a5a5a5ull};
  table[i](state+1);
  if(state[0]!=0xa5a5a5a5a5a5a5a5ull||state[11]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  uint64_t intact=n?!memcmp(page+GUARD,src_bytes,n):1;
  for(uint64_t k=0;n&&k<GUARD;k++)intact=intact&&page[k]==0x3c&&page[GUARD+n+k]==0x3c;
  uint64_t response[14];memcpy(response,state+1,80);
  response[10]=(uint64_t)(uintptr_t)src;response[11]=(uint64_t)(uintptr_t)dst;response[12]=intact;response[13]=protected_ok;
  if(fwrite(response,8,14,stdout)!=14)exit(92);
  if(fwrite(dst_area,1,n+2*GUARD,stdout)!=n+2*GUARD)exit(92);
  if(page)ro_free(page,pages);
  free(src_bytes);free(dst_area);
 }return 0;
}
'''
TEXT={COPY:b'rep movsb\n',ZERO:b'xor eax, eax\nrep stosb\n'}
SENT=[0x2222222222222222,0x3333333333333333,0x4444444444444444,0x5555555555555555]   # rdx r8 r9 r10
RAX_INIT=0x7777777777777777       # AL=0x77, never present in the source patterns
COUNTS=[0,1,7,8,15,16,31,64,65,0,1,7,8,15,16,31,64,65]


def pattern(n,seed):
    """Source bytes that never equal 0x77 (the AL sentinel) and are not all zero."""
    return bytes(((seed*31+k*13)%200)+1 if ((seed*31+k*13)%200)+1!=0x77 else 0x78 for k in range(n))


class NasmMemoryIntrinsicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C32'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.executables=cls.build_all('good',SOURCE.read_text(encoding='utf-8'))

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build_all(cls,name,text):
        """Stage only this component (no whole lang root) and build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_memory_intrinsic.dg').write_text(text,encoding='utf-8')
        (root/'probe/mem_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/mem_export.dg',roots=[root],mode=mode)
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

    def emit(self,exe,cases,label):
        """cases: (operation,cap,expected_status). Guards are asserted per call before results are used."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for op,cap,_ in cases:payload.extend(struct.pack('<2Q',op,cap))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],10)
        offset=8;texts=[]
        for index,(op,cap,status) in enumerate(cases):
            got,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(got,status,(label,index,'status'))
            texts.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return texts

    def native_run(self,texts,vectors,label):
        """vectors: (operation, count). The stub clears DF, loads the fixed registers, runs the emitted text and records state."""
        regs=['rax','rcx','rdx','rsi','rdi','r8','r9','r10']
        stub=['bits 64','section .text']
        for k,text in enumerate(texts):
            stub+=['global v%d'%k,'v%d:'%k,'mov r11, rdi','cld']+['mov %s, [r11+%d]'%(r,8*j)for j,r in enumerate(regs)]
            stub+=['pushfq','pop qword [r11+64]']+text.decode('ascii').rstrip('\n').split('\n')+['pushfq','pop qword [r11+72]']
            stub+=['mov [r11+%d], %s'%(8*j,r)for j,r in enumerate(regs)]+['ret']
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(texts))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(texts))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],label+'-native-link')
        payload=bytearray();sources=[]
        for k,(op,n) in enumerate(vectors):
            data=pattern(n,k);sources.append(data)
            payload.extend(struct.pack('<6Q',n,RAX_INIT,*SENT));payload.extend(data)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        offset=0
        for k,(op,n) in enumerate(vectors):
            r=list(struct.unpack_from('<14Q',run.stdout,offset));offset+=112
            area=run.stdout[offset:offset+n+2*GUARD];offset+=n+2*GUARD
            rax,rcx,rdx,rsi,rdi,r8,r9,r10,before,after,src,dst,intact,protected_ok=r
            self.assertEqual(protected_ok,1,(label,k,'read-only protection'))
            self.assertEqual(intact,1,(label,k,'native source and guards intact'))
            want=bytes([0xa5])*GUARD+(sources[k]if op==COPY else bytes(n))+bytes([0xa5])*GUARD
            self.assertEqual(area,want,(label,k,'native bytes',op,n))
            if n==0:self.assertEqual((src,dst),(0,0),(label,k,'count 0 uses NULL pointers'))
            self.assertEqual((rcx,rdi),(0,dst+n),(label,k,'native rcx/rdi'))
            self.assertEqual(rsi,src+n if op==COPY else src,(label,k,'native rsi'))
            self.assertEqual(rax,RAX_INIT if op==COPY else 0,(label,k,'native rax'))
            self.assertEqual([rdx,r8,r9,r10],SENT,(label,k,'native other registers'))
            self.assertEqual(after&DF,0,(label,k,'DF clear'))
            if op==COPY:self.assertEqual(before&ARITH_FLAGS,after&ARITH_FLAGS,(label,k,'native flags preserved'))
        self.assertEqual(offset,len(run.stdout))

    def test_exact_text_and_capacity(self):
        cases=[]
        for op in (COPY,ZERO):
            n=len(TEXT[op]);cases+=[(op,n,OK),(op,n+9,OK),(op,n-1,CAPACITY),(op,0,CAPACITY)]
        cases+=[(2,64,INVALID),(2,0,INVALID),(2**64-1,64,INVALID)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for (op,cap,status),text in zip(cases,texts):
                if status==OK:self.assertEqual(text,TEXT[op],(mode,op))
        self.records.append(dict(test='exact-text-capacity',cases=len(cases),preflights_per_native=10,modes=2,passed=True))

    def test_text_assembles_in_both_formats(self):
        for mode,exe in self.executables.items():
            texts=self.emit(exe,[(COPY,32,OK),(ZERO,32,OK)],'asm-'+mode)
            source=self.work/('intrinsics-'+mode+'.asm');source.write_bytes(b'bits 64\nsection .text\n'+b''.join(texts))
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('intrinsics-%s.%s.o'%(mode,fmt)),source],'intrinsics-%s-%s'%(mode,fmt))
        self.records.append(dict(test='intrinsics-assemble',formats=['elf64','win64'],modes=2,passed=True))

    def vectors(self):
        return [(COPY if k<9 else ZERO,n)for k,n in enumerate(COUNTS)]

    def test_native_copy_and_zero(self):
        vectors=self.vectors()
        for mode,exe in self.executables.items():
            texts=self.emit(exe,[(op,32,OK)for op,_ in vectors],'vectors-'+mode)
            self.native_run(texts,vectors,'native-'+mode)
        self.records.append(dict(test='native-copy-zero',vectors_per_mode=len(vectors),counts=COUNTS,modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        old='if operation==COPY{at=copy(buffer,0,"rep movsb\\n");}';new='if operation==COPY{at=copy(buffer,0,"rep stosb\\n");}'
        self.assertEqual(source.count(old),1)
        vectors=[(COPY,n)for n in (1,7,16,65)]
        for mode,exe in self.executables.items():
            self.native_run(self.emit(exe,[(op,32,OK)for op,_ in vectors],'bad-copy-good-'+mode),vectors,'bad-copy-good-'+mode)
        for mode,exe in self.build_all('bad-copy-as-stosb',source.replace(old,new,1)).items():
            texts=self.emit(exe,[(op,32,OK)for op,_ in vectors],'bad-copy-'+mode)
            with self.assertRaisesRegex(AssertionError,'native bytes'):self.native_run(texts,vectors,'bad-copy-'+mode)
        self.records.append(dict(test='bad-copy-as-stosb',compiled=True,native_executed=True,modes=2,rejected_by='native bytes'))
        old='if at>out.len{return CAPACITY;}';self.assertEqual(source.count(old),1)
        new='var j:usize=0;while j<at&&j<out.len{out[j]=buffer[j];j+=1;}if at>out.len{return CAPACITY;}'
        case=[(ZERO,10,CAPACITY)]
        for mode,exe in self.executables.items():self.emit(exe,case,'bad-early-out-good-'+mode)
        for mode,exe in self.build_all('bad-early-out',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,case,'bad-early-out-'+mode)
        self.records.append(dict(test='bad-early-out',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))


if __name__=='__main__':unittest.main()
