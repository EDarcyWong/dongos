"""Actual Dong zero-argument scope cleanup call emitter (C12 + CR4): exact text, assembly, native call log."""
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

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_scope_cleanup.dg'
DEPENDENCIES=[ROOT/'lang/bootstrap'/n for n in ('cleanup_plan.dg','decimal_integer.dg')]  # C12, CR4
OK,INVALID,CAPACITY=0,1,2
U64=2**64-1
ROOTP=U64
PREFLIGHTS=21
SENTINELS=[0x1212121212121212,0x1313131313131313,0x1414141414141414,0x1515151515151515,0x0b0b0b0b0b0b0b0b]  # r12..r15, rbp
WRAPPER='''module probe.cleanup_export;
import bootstrap.cleanup_plan as clean;
import bootstrap.nasm_scope_cleanup as c;
export("dong_cleanup_emit") pub unsafe fn emit(scopes:*const clean.Scope,ns:usize,ids:*const usize,ni:usize,from_scope:usize,target_scope:usize,out:*u8,nout:usize,written:*usize)u64{unsafe{
 return c.emit(slice_from_raw_parts(scopes,ns),slice_from_raw_parts(ids,ni),from_scope,target_scope,slice_from_raw_parts(out,nout),written);
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
typedef struct {uint64_t parent,first,count;} Scope;
_Static_assert(sizeof(Scope)==24&&__builtin_offsetof(Scope,count)==16,"Scope layout");
extern uint64_t ABI dong_cleanup_emit(const Scope*,uint64_t,const uint64_t*,uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
#define R UINT64_MAX
/* Each preflight keeps every other field valid (root + child scope, ids {3,4}, from 1 to ROOT) so only the target check can reject it. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[4096],saved[4096];const unsigned total=21;
 Scope*sc=(Scope*)arena;uint64_t*id=(uint64_t*)(arena+512);uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+3584);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));sc[0]=(Scope){R,0,1};sc[1]=(Scope){0,1,1};id[0]=3;id[1]=4;memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_cleanup_emit(sc,2,id,2,1,R,o,2048,NULL);break;                              /* written NULL */
   case 1:s=dong_cleanup_emit(sc,2,id,2,1,R,o,2048,(uint64_t*)(arena+3585));break;           /* written odd */
   case 2:s=dong_cleanup_emit(sc,2,id,2,1,R,NULL,0,FAKE(UINT64_MAX-7));break;                /* written end overflow, legal empty out */
   case 3:s=dong_cleanup_emit(sc,2,id,2,1,R,FAKE(UINT64_MAX-15),32,w);break;                 /* out end overflow */
   case 4:s=dong_cleanup_emit(sc,2,id,2,1,R,NULL,16,w);break;                                /* NULL non-empty out */
   case 5:s=dong_cleanup_emit(NULL,2,id,2,1,R,o,2048,w);break;                               /* NULL non-empty scopes */
   case 6:s=dong_cleanup_emit((Scope*)(arena+4),2,id,2,1,R,o,2048,w);break;                  /* scopes misaligned */
   case 7:s=dong_cleanup_emit(sc,UINT64_MAX/24+1,id,2,1,R,o,2048,w);break;                   /* scopes multiplication overflow */
   case 8:s=dong_cleanup_emit(FAKE(UINT64_MAX-31),2,id,2,1,R,o,2048,w);break;                /* scopes end overflow */
   case 9:s=dong_cleanup_emit(sc,2,NULL,2,1,R,o,2048,w);break;                               /* NULL non-empty ids */
   case 10:s=dong_cleanup_emit(sc,2,(uint64_t*)(arena+516),2,1,R,o,2048,w);break;            /* ids misaligned */
   case 11:s=dong_cleanup_emit(sc,2,id,UINT64_MAX/8+1,1,R,o,2048,w);break;                   /* ids multiplication overflow */
   case 12:s=dong_cleanup_emit(sc,2,FAKE(UINT64_MAX-7),2,1,R,o,2048,w);break;                /* ids end overflow */
   case 13:s=dong_cleanup_emit(sc,2,id,2,1,R,o,2048,(uint64_t*)sc);break;                    /* written on scopes prefix */
   case 14:s=dong_cleanup_emit(sc,8,id,2,1,R,o,2048,(uint64_t*)(arena+184));break;           /* written in scopes' declared tail */
   case 15:s=dong_cleanup_emit(sc,2,id,2,1,R,o,2048,id);break;                               /* written on ids prefix */
   case 16:s=dong_cleanup_emit(sc,2,id,16,1,R,o,2048,id+15);break;                           /* written in ids' declared tail */
   case 17:s=dong_cleanup_emit(sc,2,id,2,1,R,arena+40,16,w);break;                           /* out over scopes */
   case 18:s=dong_cleanup_emit(sc,2,id,16,1,R,arena+600,32,w);break;                         /* out over ids' declared tail */
   case 19:s=dong_cleanup_emit(sc,2,id,2,1,R,o,2048,(uint64_t*)o);break;                     /* written on out prefix */
   default:s=dong_cleanup_emit(sc,2,id,2,1,R,o,2048,(uint64_t*)(o+2040));break;              /* written in out's unused tail */
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
  uint64_t h[6];read_exact(h,sizeof(h));uint64_t ns=h[0],ni=h[1],from=h[2],target=h[3],cap=h[4],ro=h[5];
  if(ns>64||ni>64||cap>8192)exit(94);
  uint64_t bytes=ns*24+ni*8;uint8_t*in=malloc(bytes+64),*copy=malloc(bytes+1),*out=malloc(cap+64);uint64_t meta[3];
  if(!in||!copy||!out)exit(95);
  read_exact(in,bytes);memcpy(copy,in,bytes);
  const Scope*sc=(const Scope*)in;const uint64_t*id=(const uint64_t*)(in+ns*24);uint8_t*page=NULL;uint64_t pages=4096,protected_ok=1;
  if(ro){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,in,bytes);protected_ok=ro_protect(page,pages);sc=(const Scope*)page;id=(const uint64_t*)(page+ns*24);}
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));
  uint64_t s=dong_cleanup_emit(ns?sc:NULL,ns,ni?id:NULL,ni,from,target,cap?out+32:NULL,cap,meta+1);
  uint64_t w=s?0:meta[1];
  uint64_t valid=protected_ok&&filled(meta,8)&&filled(meta+2,8)&&!memcmp(copy,sc,ns*24)&&!memcmp(copy+ns*24,id,ni*8)&&filled(out,32)&&filled(out+32+cap,32);
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
extern uint64_t cleanup_log[1+2*32];
%DECLS%
static const stub table[]={%TABLE%};
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 for(unsigned k=0;k<sizeof(table)/sizeof(table[0]);k++){
  uint64_t io[24];memset(io,0xa5,sizeof(io));read_exact(io,16);io[23]=0x5a5a5a5a5a5a5a5aull;
  memset(cleanup_log,0,sizeof(cleanup_log));
  table[k](io);
  if(io[23]!=0x5a5a5a5a5a5a5a5aull)exit(96);
  if(fwrite(io,8,12,stdout)!=12||fwrite(cleanup_log,8,1+2*32,stdout)!=1+2*32)exit(92);
 }return 0;
}
'''


def oracle(scopes,ids,start,target):
    """Independent model: innermost to outermost scope until target (root included for ROOT), each in reverse registration."""
    order=[];at=start
    while at!=target:
        parent,first,count=scopes[at];order+=list(reversed(ids[first:first+count]));at=parent
    return order


def expected_text(order):
    if not order:return b''
    lines=['sub rsp, 16','mov qword [rsp], rax','mov qword [rsp + 8], rdx']+['call __dong_cleanup%d'%i for i in order]
    lines+=['mov rax, qword [rsp]','mov rdx, qword [rsp + 8]','add rsp, 16']
    return ''.join(l+'\n'for l in lines).encode()


TREE=[(ROOTP,0,2),(0,2,3),(1,5,1),(2,6,2),(0,8,0)]
TREE_IDS=[10,11,12,13,12,14,15,U64-2]
LONG_SCOPES=[(ROOTP,0,8),(0,8,8)]
LONG_IDS=[U64-2-i for i in range(16)]
OVERLAP=[(ROOTP,0,4),(0,2,4)]
OVERLAP_IDS=[20,21,22,23,24,25]
# (scopes, ids, from, target): self exit, function return through the root, continue/break style ancestors, sibling, 16 long calls
VECTORS=[(TREE,TREE_IDS,3,3),(TREE,TREE_IDS,3,ROOTP),(TREE,TREE_IDS,3,2),(TREE,TREE_IDS,3,1),(TREE,TREE_IDS,1,0),
         (TREE,TREE_IDS,4,ROOTP),(LONG_SCOPES,LONG_IDS,1,ROOTP),(OVERLAP,OVERLAP_IDS,1,ROOTP),([(ROOTP,0,3)],[7,7,7],0,ROOTP),
         ([(ROOTP,0,1),(0,1,1)],[0,U64-2],1,0)]


class NasmScopeCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C36'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
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
        """Stage only this component and the integrated C12/CR4 modules, then build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_scope_cleanup.dg').write_text(text,encoding='utf-8')
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        (root/'probe/cleanup_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/cleanup_export.dg',roots=[root],mode=mode)
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
        """cases: (scopes, ids, from, target, cap, readonly, status). Returns the emitted text (None on failure) per case."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for scopes,ids,start,target,cap,ro,_ in cases:
            payload.extend(struct.pack('<6Q',len(scopes),len(ids),start,target,cap,ro))
            for s in scopes:payload.extend(struct.pack('<3Q',*s))
            payload.extend(struct.pack('<%dQ'%len(ids),*ids))
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
            self.assertEqual(got,c[-1],(label,index,'status',c[2:5]))
            results.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return results

    def native_run(self,texts,vectors,label):
        """Stubs run each text with high-bit RAX/RDX and callee-saved sentinels; helpers log (ID, rsp&15) and clobber caller-saved."""
        ids=sorted({i for _,v,_,_ in vectors for i in v})
        asm=['bits 64','default rel','section .bss','global cleanup_log','cleanup_log: resq 65','section .text']
        for i in ids:
            asm+=['__dong_cleanup%d:'%i,'lea r11, [cleanup_log]','mov r10, [r11]','cmp r10, 32','jae .full','shl r10, 4',
                  'mov rax, %d'%i,'mov [r11+r10+8], rax','mov rax, rsp','and rax, 15','mov [r11+r10+16], rax','inc qword [r11]','.full:']
            asm+=['mov %s, 0x%x'%(r,0x7700000000000000+j*0x1111+i%251)for j,r in enumerate(['rax','rcx','rdx','rsi','rdi','r8','r9','r10','r11'])]
            asm+=['ret']
        for k,text in enumerate(texts):
            asm+=['global v%d'%k,'v%d:'%k,'push rbx','push rbp','push r12','push r13','push r14','push r15','sub rsp, 8','mov rbx, rdi']   # rsp%16==0 at the cleanup text
            asm+=['mov %s, 0x%x'%(r,v)for r,v in zip(['r12','r13','r14','r15','rbp'],SENTINELS)]
            asm+=['mov rax, [rbx]','mov rdx, [rbx+8]','mov [rbx+32], rsp']
            asm+=text.decode('ascii').rstrip('\n').split('\n')if text else []
            asm+=['mov [rbx+16], rax','mov [rbx+24], rdx','mov [rbx+40], rsp']+['mov [rbx+%d], %s'%(48+8*j,r)for j,r in enumerate(['r12','r13','r14','r15','rbp'])]
            asm+=['mov [rbx+88], rbx','add rsp, 8','pop r15','pop r14','pop r13','pop r12','pop rbp','pop rbx','ret']
        source=self.work/(label+'.stubs.asm');source.write_text('\n'.join(asm)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.'+fmt+'.o'),source],label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(texts))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(texts))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],label+'-native-link')
        payload=bytearray();inputs=[]
        for k in range(len(texts)):
            rax,rdx=0x8000000000000000|(0xa1b2c3d4<<16)|k,0xf000000000000000|(0x5e6f7081<<8)|k
            inputs.append((rax,rdx));payload.extend(struct.pack('<2Q',rax,rdx))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        size=(12+65)*8;self.assertEqual(len(run.stdout),size*len(texts))
        for k,(scopes,ids_,start,target) in enumerate(vectors):
            io=struct.unpack_from('<12Q',run.stdout,size*k);log=struct.unpack_from('<65Q',run.stdout,size*k+96)
            want=oracle(scopes,ids_,start,target);n=log[0]
            self.assertEqual([log[1+2*j]for j in range(n)],want,(label,k,'native cleanup log order'))
            self.assertEqual([log[2+2*j]for j in range(n)],[8]*n,(label,k,'native callee entry alignment'))
            self.assertEqual(io[2:4],inputs[k],(label,k,'native return value restored'))
            self.assertEqual(io[4],io[5],(label,k,'native rsp restored'))
            self.assertEqual(list(io[6:11]),SENTINELS,(label,k,'native callee-saved preserved'))

    def test_exact_text_capacity_and_invalid(self):
        cases=[]
        for k,(scopes,ids,start,target) in enumerate(VECTORS):
            text=expected_text(oracle(scopes,ids,start,target));n=len(text)
            cases+=[(scopes,ids,start,target,n,int(k%2==0),OK),(scopes,ids,start,target,n+7,0,OK)]
            if n:cases+=[(scopes,ids,start,target,n-1,0,CAPACITY),(scopes,ids,start,target,0,0,CAPACITY)]
        self.assertEqual(len(expected_text(oracle(LONG_SCOPES,LONG_IDS,1,ROOTP))),756)
        sum17=[(ROOTP,0,9),(0,8,8)]
        cases+=[(sum17,LONG_IDS,1,ROOTP,4096,1,INVALID),(sum17,LONG_IDS,0,0,0,0,INVALID),           # count sum 17 (even with an empty path)
                (TREE,TREE_IDS+[U64],3,3,4096,1,INVALID),(TREE,TREE_IDS+[U64],3,ROOTP,0,0,INVALID),   # unused ID u64::MAX
                ([(ROOTP,0,1),(0,1,1),(3,0,0),(2,0,0)],[1,2],1,ROOTP,4096,1,INVALID),             # unreachable parent cycle
                ([],[],0,ROOTP,64,0,INVALID),([(ROOTP,0,0)]+[(0,0,0)]*8,[],0,ROOTP,64,0,INVALID),   # 0 and 9 scopes
                ([(ROOTP,0,1)],list(range(17)),0,ROOTP,4096,0,INVALID),                          # 17 ids
                (TREE,TREE_IDS,3,4,4096,1,INVALID),(TREE,TREE_IDS,1,3,4096,0,INVALID),           # target sibling / descendant
                (TREE,TREE_IDS,5,ROOTP,4096,0,INVALID),([(ROOTP,1,2)],[1,2],0,ROOTP,4096,0,INVALID),  # from out of range, range out of bounds
                ([(0,0,1)],[1],0,ROOTP,4096,0,INVALID),([(ROOTP,0,U64)],[1],0,ROOTP,0,0,INVALID)]  # bad root parent, huge count
        for mode,exe in self.executables.items():
            results=self.run_cases(exe,cases,'text-'+mode)
            for c,text in zip(cases,results):
                if c[-1]==OK:self.assertEqual(text,expected_text(oracle(*c[:4])),(mode,c[2:5]))
        self.records.append(dict(test='exact-text-capacity-invalid',cases=len(cases),preflights_per_native=PREFLIGHTS,
                                 longest_bytes=756,modes=2,passed=True))

    def texts(self,exe,vectors,label):
        return self.run_cases(exe,[(*v,2048,0,OK)for v in vectors],label)

    def test_text_assembles_in_both_formats(self):
        for mode,exe in self.executables.items():
            texts=self.texts(exe,VECTORS,'asm-'+mode)
            externs=''.join('extern __dong_cleanup%d\n'%i for i in sorted({i for _,v,_,_ in VECTORS for i in v}))
            source=self.work/('cleanup-'+mode+'.asm');source.write_bytes(b'bits 64\n'+externs.encode()+b'section .text\n'+b''.join(texts))
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('cleanup-%s.%s.o'%(mode,fmt)),source],'cleanup-%s-%s'%(mode,fmt))
        self.records.append(dict(test='cleanup-assemble',formats=['elf64','win64'],modes=2,passed=True))

    def test_native_cleanup_calls(self):
        for mode,exe in self.executables.items():
            self.native_run(self.texts(exe,VECTORS,'vectors-'+mode),VECTORS,'native-'+mode)
        self.records.append(dict(test='native-cleanup-calls',vectors_per_mode=len(VECTORS),modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8');vectors=[VECTORS[1],VECTORS[3]]
        for mode,exe in self.executables.items():
            self.native_run(self.texts(exe,vectors,'bad-good-'+mode),vectors,'bad-good-'+mode)
        for name,old,new,reason in [
            ('bad-reversed','if !call(text,&at,order[i] as u64)','if !call(text,&at,order[used-1-i] as u64)','native cleanup log order'),
            ('bad-no-restore','mov rax, qword [rsp]\\nmov rdx','mov rdx','native return value restored')]:
            self.assertEqual(source.count(old),1,name)
            for mode,exe in self.build_all(name,source.replace(old,new,1)).items():
                texts=self.texts(exe,vectors,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,reason):self.native_run(texts,vectors,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))
        old='if at>out.len{return CAPACITY;}\n i=0;while i<at{out[i]=buffer[i];i+=1;}'
        new='i=0;while i<at&&i<out.len{out[i]=buffer[i];i+=1;}\n if at>out.len{return CAPACITY;}'
        self.assertEqual(source.count(old),1);case=[(*VECTORS[1],30,0,CAPACITY)]
        for mode,exe in self.executables.items():self.run_cases(exe,case,'bad-early-out-good-'+mode)
        for mode,exe in self.build_all('bad-early-out',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.run_cases(exe,case,'bad-early-out-'+mode)
        self.records.append(dict(test='bad-early-out',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))


if __name__=='__main__':unittest.main()
