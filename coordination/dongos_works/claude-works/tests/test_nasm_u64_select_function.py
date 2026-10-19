"""Actual Dong whole SysV select function (C49): exact text, ELF64/COFF assembly, real call/ret through two return blocks."""
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
from lang.tests.test_dongc import tool,nasm_flags as _nasm_flags


def nasm_flags(nasm):
    """Shared -Wall -Werror flags; NASM 3.x lists its warnings only under "-h -w", so the shared probe misses
    reloc-rel-dword and ordinary RIP-relative .text -> .rodata references would fail. Every other warning stays an error."""
    flags=list(_nasm_flags(nasm))
    if '-w-reloc-rel-dword' not in flags:
        flags.append('-w-reloc-rel-dword')
    return flags

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_u64_select_function.dg'
DOC=WORKS/'claude-works/src/bootstrap/nasm_u64_select_function.md'
# Integrated components and their whole read-only import closure (nothing else from lang is staged).
DEPENDENCIES=[ROOT/'lang/bootstrap'/(n+'.dg')for n in (
    'nasm_symbol',                                                   # CR3
    'nasm_function_frame','decimal_integer',                         # CR11, CR4
    'nasm_sysv_incoming_args','sysv_integer_args','nasm_memory_operand',   # C37, C8, CR8
    'nasm_integer_memory_load',                                      # CR12
    'nasm_compare_emit','branch_plan',                               # C22, CR6
    'nasm_branch_emit',                                              # CR10
    'nasm_block_emit',                                               # CR18
    'nasm_sysv_function_exit','nasm_sysv_return_values','sysv_return_plan')]   # C42, C39, C14
OK,INVALID,CAPACITY=0,1,2
U64=2**64-1
NONE=U64
PREFLIGHTS=17
EQ,NE,ULT,ULE,UGT,UGE,SLT,SLE,SGT,SGE=range(10)
SETCC=['sete','setne','setb','setbe','seta','setae','setl','setle','setg','setge']
WRAPPER='''module probe.select_export;
import bootstrap.nasm_u64_select_function as s;
export("dong_select_emit") pub unsafe fn emit(module_name:*const u8,nm:usize,item_name:*const u8,ni:usize,condition:u64,yes_block:u64,no_block:u64,
 out:*u8,no:usize,written:*usize)u64{unsafe{
 return s.emit(slice_from_raw_parts(module_name,nm),slice_from_raw_parts(item_name,ni),condition,yes_block,no_block,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_select_emit(const uint8_t*,uint64_t,const uint8_t*,uint64_t,uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
#define FAKE(x) ((const uint8_t*)(uintptr_t)(x))
/* Descriptor/alias preflights. Every other field is legal (names 4 bytes unless stated, EQ, blocks 1/2, out 1024 bytes,
   aligned written) so only the target check can reject it. Every failing preflight is reported, then exit 93. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[4096],saved[4096];const unsigned total=17;unsigned failed=0;
 uint8_t*m=arena+64,*it=arena+192,*o=arena+1024;uint64_t*w=(uint64_t*)(arena+3072);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_select_emit(m,4,it,4,0,1,2,o,1024,NULL);break;                                    /* written NULL */
   case 1:s=dong_select_emit(m,4,it,4,0,1,2,o,1024,(uint64_t*)(arena+3073));break;                 /* written odd */
   case 2:s=dong_select_emit(m,4,it,4,0,1,2,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;    /* written end overflow, empty out */
   case 3:s=dong_select_emit(m,4,it,4,0,1,2,(uint8_t*)(uintptr_t)(UINT64_MAX-511),1024,w);break;   /* out end overflow */
   case 4:s=dong_select_emit(m,4,it,4,0,1,2,NULL,1024,w);break;                                    /* NULL non-empty out */
   case 5:s=dong_select_emit(NULL,4,it,4,0,1,2,o,1024,w);break;                                    /* NULL non-empty module */
   case 6:s=dong_select_emit(m,4,NULL,4,0,1,2,o,1024,w);break;                                     /* NULL non-empty item */
   case 7:s=dong_select_emit(FAKE(UINT64_MAX-3),8,it,4,0,1,2,o,1024,w);break;                      /* module end overflow */
   case 8:s=dong_select_emit(m,4,FAKE(UINT64_MAX-1),4,0,1,2,o,1024,w);break;                       /* item end overflow */
   case 9:s=dong_select_emit(m,4,it,4,0,1,2,o,1024,(uint64_t*)o);break;                            /* written on out prefix */
   case 10:s=dong_select_emit(m,4,it,4,0,1,2,o,1024,(uint64_t*)(o+1016));break;                    /* written in out's unused tail */
   case 11:s=dong_select_emit(m,64,it,4,0,1,2,o,1024,(uint64_t*)m);break;                          /* written on module prefix */
   case 12:s=dong_select_emit(m,64,it,4,0,1,2,o,1024,(uint64_t*)(m+56));break;                     /* written in module's tail */
   case 13:s=dong_select_emit(m,4,it,64,0,1,2,o,1024,(uint64_t*)it);break;                         /* written on item prefix */
   case 14:s=dong_select_emit(m,4,it,64,0,1,2,o,1024,(uint64_t*)(it+56));break;                    /* written in item's tail */
   case 15:s=dong_select_emit(m,64,it,4,0,1,2,m+63,8,w);break;                                     /* out overlaps module's last byte */
   default:s=dong_select_emit(m,4,it,64,0,1,2,it+63,8,w);break;                                    /* out overlaps item's last byte */
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
  uint64_t h[8];read_exact(h,sizeof(h));uint64_t nm=h[0],ni=h[1],cond=h[2],yes=h[3],no=h[4],cap=h[5],share=h[6],ro=h[7];
  if(nm>200||ni>200||cap>4096)exit(94);
  uint8_t*in=malloc(nm+ni+96),*copy=malloc(nm+ni+1),*out=malloc(cap+64);static _Alignas(8) uint64_t meta[3];
  if(!in||!copy||!out)exit(95);
  memset(in,0xa5,nm+ni+96);read_exact(in+32,nm);read_exact(in+64+nm,ni);memcpy(copy,in+32,nm);memcpy(copy+nm,in+64+nm,ni);
  const uint8_t*m=in+32,*it=in+64+nm;uint8_t*page=NULL;uint64_t pages=4096*2,protected_ok=1;
  if(share){it=m+share-1;}
  if(ro){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,nm+ni);protected_ok=ro_protect(page,pages);
   m=page;it=share?page+share-1:page+nm;}
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=dong_select_emit(nm?m:NULL,nm,ni?it:NULL,ni,cond,yes,no,cap?out+32:NULL,cap,written);
  uint64_t valid=protected_ok&&!memcmp(copy,m,nm)&&(share||!memcmp(copy+nm,it,ni))&&(ro||(filled(in,32)&&filled(in+32+nm,32)&&filled(in+64+nm+ni,32)))&&
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
# State layout (qwords): 0 rax after; 1 rsp before call; 2 rsp after; 3 rbx before; 4 rbx after; 5 rbp after;
# 6..9 r12..r15 after; 10 caller stack canary after; 11 rsp%16 just before the call.
RAX,RSP_BEFORE,RSP_AFTER,RBX_BEFORE,RBX_AFTER,RBP_AFTER,R12_AFTER,CANARY_AFTER,ALIGN,STATE=0,1,2,3,4,5,6,10,11,12
# Known values planted in every callee-saved register (rbx included: it is under test, never the observation pointer).
CALLER={'rbx':0x0bbb0bbb0bbb0bbb,'rbp':0x0b0b0b0b0b0b0b0b,'r12':0x1212121212121212,'r13':0x1313131313131313,'r14':0x1414141414141414,'r15':0x1515151515151515}
CANARY=0x5ca1ab1e0ddba11c
JUNK_RAX=0x0a0a0a0a0a0a0a0a


def symbol(module,item):
    """Independent CR3 expectation: __dong_m<hex module>_n<hex item>, two lowercase digits per byte."""
    return '__dong_m'+module.hex()+'_n'+item.hex()


def expected_text(module,item,cond,yes,no):
    """Independent whole-function text model."""
    lines=[symbol(module,item)+':','push rbp','mov rbp, rsp','sub rsp, 32',
           'mov qword [rbp - 8], rdi','mov qword [rbp - 16], rsi','mov qword [rbp - 24], rdx','mov qword [rbp - 32], rcx',
           'mov rax, qword [rbp - 8]','mov rcx, qword [rbp - 16]',
           'cmp rax, rcx',SETCC[cond]+' al','movzx rax, al','test rax, rax','je __dong_b%d'%no,
           '__dong_b%d:'%yes,'mov rax, qword [rbp - 24]','add rsp, 32','pop rbp','ret',
           '__dong_b%d:'%no,'mov rax, qword [rbp - 32]','add rsp, 32','pop rbp','ret']
    return ''.join(l+'\n'for l in lines).encode()


def signed(v):
    return v-(1<<64)if v>>63 else v


def holds(cond,a,b):
    """Independent comparison model on raw 64-bit patterns (signed conditions read them as i64)."""
    sa,sb=signed(a),signed(b)
    return [a==b,a!=b,a<b,a<=b,a>b,a>=b,sa<sb,sa<=sb,sa>sb,sa>=sb][cond]


H,L=0x8000000000000000,0x7fffffffffffffff
# (condition, lhs, rhs): every condition true and false, equality, 0/UINT64_MAX/sign boundaries,
# and pairs where the signed and unsigned readings disagree.
COMPARISONS=[(EQ,5,5),(EQ,0,U64),(NE,0,U64),(NE,U64,U64),
             (ULT,0,U64),(ULT,U64,0),(ULE,7,7),(ULE,H,L),
             (UGT,H,L),(UGT,3,3),(UGE,U64,U64),(UGE,0,1),
             (SLT,H,L),(SLT,0,U64),(SLE,H,H),(SLE,1,0),
             (SGT,0,U64),(SGT,L,L),(SGE,L,H),(SGE,U64,0)]


def vectors():
    """(module, item, cond, yes_block, no_block, lhs, rhs, yes_value, no_value); block IDs are unique across the file."""
    out=[]
    for k,(c,a,b) in enumerate(COMPARISONS):
        yes,no=(0,U64-1)if k==0 else ((U64-2,1)if k==1 else (1000+2*k,1001+2*k))
        if k==2:yes,no=no,yes                                            # yes block ID larger than no block ID
        module=b'm' if k%2 else b'sel/'+bytes([65+k])
        item=bytes([97+k]) if k!=3 else b'f'*64
        out.append((module,item,c,yes,no,a,b,0x59e5000000000000|(k<<8)|1,0xc0de000000000000|(k<<8)|2))
    return out


VECTORS=vectors()


class NasmU64SelectFunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C49'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
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
        (root/'bootstrap/nasm_u64_select_function.dg').write_text(text,encoding='utf-8')
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        (root/'probe/select_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/select_export.dg',roots=[root],mode=mode)
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

    def emit(self,exe,cases,label):
        """cases: (module,item,cond,yes,no,cap,share,readonly,status). Guards are asserted per call before results are used."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for m,it,c,y,n,cap,share,ro,_ in cases:
            payload.extend(struct.pack('<8Q',len(m),len(it),c,y,n,cap,share,ro));payload.extend(m+it)
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],PREFLIGHTS)
        offset=8;texts=[]
        for index,case in enumerate(cases):
            got,guard,written,protected=struct.unpack_from('<4Q',run.stdout,offset);offset+=32
            text=run.stdout[offset:offset+written];offset+=written
            if case[7]:self.assertEqual(protected,1,(label,index,'read-only protection call failed'))
            self.assertEqual(guard,1,(label,index,'guard/atomicity',case[2:]))
            self.assertEqual(got,case[8],(label,index,'status',case[2:]))
            texts.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return texts

    def generate(self,exe,vectors,label):
        texts=self.emit(exe,[(m,it,c,y,n,1024,0,0,OK)for m,it,c,y,n,*_ in vectors],label)
        for v,text in zip(vectors,texts):self.assertEqual(text,expected_text(*v[:5]),(label,v[:5]))
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
        for k,(m,it,c,y,n,a,b,yv,nv) in enumerate(vectors):
            stub+=['global v%d'%k,'v%d:'%k,'push rbx','push rbp','push r12','push r13','push r14','push r15','sub rsp, 8']
            stub+=['mov [rel observation], rdi','mov [rel host_anchor], rsp','mov r11, rdi']
            stub+=['mov %s, 0x%x'%(r,v)for r,v in CALLER.items()]
            stub+=['mov rax, 0x%x'%CANARY,'mov [rsp], rax','mov [r11+%d], rsp'%(8*RSP_BEFORE),
                   'mov rax, rsp','and rax, 15','mov [r11+%d], rax'%(8*ALIGN),'mov rax, 0x%x'%CALLER['rbx'],'mov [r11+%d], rax'%(8*RBX_BEFORE)]
            stub+=['mov rdi, 0x%x'%a,'mov rsi, 0x%x'%b,'mov rdx, 0x%x'%yv,'mov rcx, 0x%x'%nv,'mov rax, 0x%x'%JUNK_RAX,'call '+symbol(m,it)]
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
        for k,(m,it,c,y,n,a,b,yv,nv) in enumerate(vectors):
            got=struct.unpack_from('<%dQ'%STATE,run.stdout,8*STATE*k)
            self.assertEqual(got[ALIGN],0,(label,k,'caller rsp aligned before call'))
            self.assertEqual(got[RAX],yv if holds(c,a,b)else nv,(label,k,'native rax',SETCC[c],hex(a),hex(b)))
            self.assertEqual(got[RSP_AFTER],got[RSP_BEFORE],(label,k,'native rsp balanced across call/ret'))
            self.assertEqual(got[RBX_BEFORE],CALLER['rbx'],(label,k,'planted rbx recorded'))
            self.assertEqual(got[RBX_AFTER],CALLER['rbx'],(label,k,'native rbx preserved'))
            self.assertEqual((got[RBP_AFTER],*got[R12_AFTER:R12_AFTER+4]),tuple(v for r,v in CALLER.items()if r!='rbx'),(label,k,'native rbp/r12..r15 preserved'))
            self.assertEqual(got[CANARY_AFTER],CANARY,(label,k,'caller stack canary'))

    def test_exact_text_capacity_invalid_and_read_only_inputs(self):
        cases=[]
        for k,(m,it,c,y,n,*_) in enumerate(VECTORS):
            size=len(expected_text(m,it,c,y,n))
            cases+=[(m,it,c,y,n,size,0,k%3==0,OK),(m,it,c,y,n,size+9,0,0,OK),(m,it,c,y,n,size-1,0,k%2,CAPACITY),(m,it,c,y,n,0,0,0,CAPACITY)]
        big=(b'\xff'*64,b'\x00'*64,SGE,U64-1,10**19);size=len(expected_text(*big))     # longest: 64/64 names, two 20-digit blocks
        self.assertEqual(size,266+2+34+103+25+26+36+14+32+30+50+30+50)
        cases+=[(*big,size,0,1,OK),(*big,size-1,0,0,CAPACITY),(*big,size+100,0,0,OK)]
        # Overlapping names (item inside module), also read-only.
        cases+=[(b'abcd',b'cd',NE,4,5,1024,3,0,OK),(b'abcd',b'abcd',ULT,6,7,1024,1,1,OK),(b'q'*64,b'q'*64,EQ,8,9,1024,1,1,OK)]
        legal=(b'm',b'f',EQ,1,2)
        def bad(**kw):
            v=dict(zip(('m','it','c','y','n'),legal));v.update(kw);return (v['m'],v['it'],v['c'],v['y'],v['n'])
        for b in [bad(m=b''),bad(it=b''),bad(m=b'm'*65),bad(it=b'f'*65),bad(c=10),bad(c=U64),
                  bad(y=NONE),bad(n=NONE),bad(y=NONE,n=NONE),bad(y=7,n=7),bad(y=0,n=0)]:
            cases+=[(*b,1024,0,0,INVALID),(*b,0,0,1,INVALID)]                                # INVALID before CAPACITY
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for (m,it,c,y,n,cap,share,ro,status),text in zip(cases,texts):
                if status==OK:
                    item=m[share-1:share-1+len(it)]if share else it
                    self.assertEqual(text,expected_text(m,item,c,y,n),(mode,m,it,c,y,n))
                    self.assertTrue(all(b==10 or 32<=b<127 for b in text)and b'\n\n'not in text,(mode,'ASCII/LF'))
                    for word in (b'section',b'global',b'bits',b'extern'):self.assertNotIn(word,text,(mode,word))
        self.records.append(dict(test='exact-text-capacity-invalid-readonly',cases=len(cases),preflights_per_native=PREFLIGHTS,longest_bytes=size,modes=2,passed=True))

    def test_native_call_ret_through_both_blocks(self):
        self.assertLessEqual(len(VECTORS),24)
        self.assertEqual({v[2]for v in VECTORS},set(range(10)))
        for c in range(10):self.assertEqual({holds(c,v[5],v[6])for v in VECTORS if v[2]==c},{True,False},SETCC[c])
        self.assertTrue(any(v[5]==v[6]for v in VECTORS))
        self.assertTrue(any(holds(v[2],v[5],v[6])!=holds(v[2]-4 if v[2]>=6 else v[2]+4,v[5],v[6])for v in VECTORS if v[2]>=2))
        ids=[b for v in VECTORS for b in v[3:5]];self.assertEqual(len(ids),len(set(ids)));self.assertIn(U64-1,ids)
        self.assertEqual(len({symbol(v[0],v[1])for v in VECTORS}),len(VECTORS))
        self.assertTrue(all(v[7]>>56 and v[8]>>63 and v[7]!=v[8]for v in VECTORS))
        for mode,exe in self.executables.items():
            self.native_run(self.generate(exe,VECTORS,'vectors-'+mode),VECTORS,'native-'+mode)
        self.records.append(dict(test='native-call-ret',vectors_per_mode=len(VECTORS),functions_per_file=len(VECTORS),modes=2,formats=['elf64','win64'],passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        yes_exit='ex.emit(U64_KIND,FRAME,0,24,0,';no_exit='ex.emit(U64_KIND,FRAME,0,32,0,';branch='br.emit(bp.NE,'
        for s in (yes_exit,no_exit,branch):self.assertEqual(source.count(s),1,s)
        swapped=source.replace(yes_exit,'@YES@').replace(no_exit,yes_exit).replace('@YES@',no_exit)
        for name,text in [('bad-return-slots-swapped',swapped),('bad-branch-ne-as-eq',source.replace(branch,'br.emit(bp.EQ,',1))]:
            for mode,exe in self.executables.items():                                       # same inputs pass first
                self.native_run(self.generate(exe,VECTORS,name+'-good-'+mode),VECTORS,name+'-good-'+mode)
            for mode,exe in self.build_all(name,text).items():
                texts=self.emit(exe,[(m,it,c,y,n,1024,0,0,OK)for m,it,c,y,n,*_ in VECTORS],name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'native rax'):self.native_run(texts,VECTORS,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,linked=True,native_executed=True,modes=2,rejected_by='native rax'))
        # Callee-saved RBX not preserved on BOTH exits: "add rbx, 8" right before each ret. It builds, links and returns
        # normally on both the yes and the no route with the right RAX and a balanced RSP; only the recorded RBX rejects it.
        yes_line=' if ex.emit(U64_KIND,FRAME,0,24,0,slice_from_raw_parts(&buffer[at],EXIT),&n)!=ex.OK{return INVALID;}\n at+=n;\n'
        no_line=' if ex.emit(U64_KIND,FRAME,0,32,0,slice_from_raw_parts(&buffer[at],EXIT),&n)!=ex.OK{return INVALID;}\n at+=n;\n'
        for s in (yes_line,no_line):self.assertEqual(source.count(s),1,s)
        inject='at-=4;put(text,&at,"add rbx, 8\\nret\\n");\n'
        tail=b'pop rbp\nadd rbx, 8\nret\n'
        clobber=source.replace(yes_line,yes_line+inject,1).replace(no_line,no_line+inject,1)
        for mode,exe in self.executables.items():
            self.native_run(self.generate(exe,VECTORS,'bad-rbx-good-'+mode),VECTORS,'bad-rbx-good-'+mode)
        for mode,exe in self.build_all('bad-rbx-clobbered',clobber).items():
            texts=self.emit(exe,[(m,it,c,y,n,1024,0,0,OK)for m,it,c,y,n,*_ in VECTORS],'bad-rbx-'+mode)
            self.assertTrue(all(t.count(tail)==2 and t.endswith(tail)for t in texts),(mode,'injected before both rets'))
            with self.assertRaisesRegex(AssertionError,'native rbx preserved'):self.native_run(texts,VECTORS,'bad-rbx-'+mode)
        self.records.append(dict(test='bad-rbx-clobbered',vectors=len(VECTORS),exits=2,compiled=True,linked=True,native_executed=True,modes=2,
                                 rejected_by='native rbx preserved (rax and rsp assertions passed first)'))
        old='if at>on{return CAPACITY;}';self.assertEqual(source.count(old),1)
        new='if at>on{var k:usize=0;while k<on{out[k]=buffer[k];k+=1;}return CAPACITY;}'    # publishes the function header early
        m,it,c,y,n,*_=VECTORS[0];size=len(expected_text(m,it,c,y,n));case=[(m,it,c,y,n,size-1,0,0,CAPACITY)]
        for mode,exe in self.executables.items():self.emit(exe,case,'bad-early-header-good-'+mode)
        for mode,exe in self.build_all('bad-early-header',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,case,'bad-early-header-'+mode)
        self.records.append(dict(test='bad-early-header',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))

    def test_name_alias_preflights_are_reachable(self):
        """Preflight sensitivity: a real Dong without the name alias line fails exactly preflights 11..16."""
        source=SOURCE.read_text(encoding='utf-8')
        old='if overlap(wp,8,mp,mn)||overlap(wp,8,ip,inn)||overlap(op,on,mp,mn)||overlap(op,on,ip,inn){return INVALID;}'
        self.assertEqual(source.count(old),1)
        for mode,exe in self.executables.items():self.emit(exe,[],'alias-good-'+mode)
        for mode,exe in self.build_all('bad-no-name-alias',source.replace(old,'',1)).items():
            run=subprocess.run([str(exe)],input=struct.pack('<Q',0),capture_output=True,timeout=60)
            err=run.stderr.decode('ascii','replace');(self.work/('bad-no-name-alias-'+mode+'.stderr')).write_text(err,encoding='ascii')
            self.assertEqual(run.returncode,93,(mode,err))
            failed=[int(line.split()[2])for line in err.splitlines()if line.startswith('invalid preflight ')]
            self.assertEqual(failed,[11,12,13,14,15,16],(mode,err))
        self.records.append(dict(test='bad-no-name-alias',compiled=True,native_executed=True,modes=2,rejected_by='preflights 11..16'))


if __name__=='__main__':unittest.main()
