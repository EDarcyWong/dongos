"""Actual Dong NASM comparison-to-bool emitter: exact text, dual-format assembly, and native execution."""
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

SOURCE=ROOT/'lang/bootstrap/nasm_compare_emit.dg'
DEPENDENCY=ROOT/'lang/bootstrap/branch_plan.dg'      # integrated CR6, staged read-only
OK,INVALID,CAPACITY=0,1,2
NAMES=['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi']+['r%d'%i for i in range(8,16)]
SETCC=['sete','setne','setb','setbe','seta','setae','setl','setle','setg','setge']
SAFE=[0,1,2,6,8,9,10,11]          # caller-saved registers the native stubs may load/clobber (rdi holds the state pointer)
WRAPPER='''module probe.compare_export;
import bootstrap.nasm_compare_emit as c;
export("dong_compare_emit") pub unsafe fn emit(condition:u64,left:u64,right:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return c.emit(condition,left,right,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_compare_emit(uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
/* Each preflight keeps every other field valid so only the target check can reject it. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[512],saved[512];const unsigned total=12;
 uint8_t*o=arena+64;uint64_t*w=(uint64_t*)(arena+256);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_compare_emit(0,0,1,o,64,NULL);break;                                    /* written NULL */
   case 1:s=dong_compare_emit(0,0,1,o,64,(uint64_t*)(arena+257));break;                  /* written odd */
   case 2:s=dong_compare_emit(0,0,1,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;  /* written end overflow, empty out */
   case 3:s=dong_compare_emit(0,0,1,(uint8_t*)(uintptr_t)(UINT64_MAX-3),8,w);break;      /* out end overflow */
   case 4:s=dong_compare_emit(0,0,1,NULL,64,w);break;                                    /* NULL non-empty out */
   case 5:s=dong_compare_emit(0,0,1,o,64,(uint64_t*)o);break;                            /* written on out prefix */
   case 6:s=dong_compare_emit(0,0,1,o,96,(uint64_t*)(o+88));break;                       /* written in out's unused tail */
   case 7:s=dong_compare_emit(10,0,1,NULL,0,w);break;                                    /* bad condition, capacity 0 */
   case 8:s=dong_compare_emit(UINT64_MAX,0,1,o,64,w);break;
   case 9:s=dong_compare_emit(0,16,1,NULL,0,w);break;                                    /* bad left, capacity 0 */
   case 10:s=dong_compare_emit(0,0,16,o,64,w);break;                                     /* bad right */
   default:s=dong_compare_emit(9,UINT64_MAX,UINT64_MAX,o,1,w);break;
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
  uint64_t h[4];read_exact(h,sizeof(h));uint64_t cap=h[3];if(cap>4096)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=dong_compare_emit(h[0],h[1],h[2],cap?out+32:NULL,cap,written);
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
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef void ABI (*stub)(uint64_t*);
%DECLS%
static const stub table[]={%TABLE%};
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  uint64_t state[10];read_exact(state+1,64);state[0]=state[9]=0xa5a5a5a5a5a5a5a5ull;
  table[i](state+1);
  if(state[0]!=0xa5a5a5a5a5a5a5a5ull||state[9]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  if(fwrite(state+1,8,8,stdout)!=8)exit(92);
 }return 0;
}
'''


def expected_text(c,l,r):
    return ('cmp %s, %s\n%s al\nmovzx rax, al\n'%(NAMES[l],NAMES[r],SETCC[c])).encode()


def semantics(c,a,b):
    """Independent arbitrary-precision predicate on two's-complement 64-bit values."""
    sa,sb=(a-(1<<64)if a>>63 else a),(b-(1<<64)if b>>63 else b)
    return int([a==b,a!=b,a<b,a<=b,a>b,a>=b,sa<sb,sa<=sb,sa>sb,sa>=sb][c])


TOP,ONES=1<<63,2**64-1
# (condition, left, right, a, b, rax_initial or None when RAX is an operand); 24 per mode.
VECTORS=[(0,1,2,5,5,ONES),(0,8,9,TOP,TOP-1,ONES),(1,1,2,5,5,ONES),(1,0,1,TOP,0,None),
         (2,1,2,TOP,1,ONES),(2,8,9,1,TOP,ONES),(3,1,2,ONES,ONES,ONES),(3,9,8,ONES,0,ONES),
         (4,1,2,TOP,1,ONES),(4,2,0,0,ONES,None),(5,1,2,0,0,ONES),(5,10,11,0,1,ONES),
         (6,1,2,TOP,1,ONES),(6,8,9,1,TOP,ONES),(7,1,2,ONES,ONES,ONES),(7,9,8,0,ONES,ONES),
         (8,1,2,TOP,1,ONES),(8,0,1,1,ONES,None),(9,1,2,TOP,TOP,ONES),(9,10,11,ONES,TOP,ONES),
         (6,0,0,TOP,TOP,None),(9,0,0,TOP,TOP,None),(2,11,10,0x7fffffffffffffff,TOP,0xffffffffffffff00),
         (8,6,1,0x7fffffffffffffff,TOP,0xdeadbeefcafe0000)]


class NasmCompareEmitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/C22'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,DEPENDENCY,Path(__file__)]}
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.executables=cls.build_all('good',SOURCE.read_text(encoding='utf-8'))

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build_all(cls,name,text):
        """Stage only this component and the integrated CR6 module, then build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_compare_emit.dg').write_text(text,encoding='utf-8')
        shutil.copyfile(DEPENDENCY,root/'bootstrap/branch_plan.dg')
        (root/'probe/compare_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/compare_export.dg',roots=[root],mode=mode)
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
        """cases: (condition,left,right,cap,expected_status). Guards are asserted per call before results are used."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c,l,r,cap,_ in cases:payload.extend(struct.pack('<4Q',c,l,r,cap))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],12)
        offset=8;texts=[]
        for index,(c,l,r,cap,status) in enumerate(cases):
            got,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(got,status,(label,index,'status'))
            texts.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return texts

    def native_run(self,texts,vectors,label):
        """Assemble the emitted text into SysV stubs, run them, and compare every safe register (full 64 bits)."""
        stub=['bits 64','section .text']
        for i,text in enumerate(texts):
            stub+=['global v%d'%i,'v%d:'%i]+['mov %s, [rdi+%d]'%(NAMES[r],8*k)for k,r in enumerate(SAFE)]
            stub+=text.decode('ascii').rstrip('\n').split('\n')
            stub+=['mov [rdi+%d], %s'%(8*k,NAMES[r])for k,r in enumerate(SAFE)]+['ret']
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        self.command([self.nasm,'-f',self.native,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.o'),self.work/(label+'.stubs.asm')],label+'-stubs')
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%i for i in range(len(texts))))
        main=main.replace('%TABLE%',','.join('v%d'%i for i in range(len(texts))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.o'),'-o',exe],label+'-native-link')
        payload=bytearray();expected=[]
        for c,l,r,a,b,rax in vectors:
            state=[0x1111111111111111*(j+1)for j in range(8)]               # distinct sentinels
            if rax is not None:state[0]=rax                                  # RAX high bits set before the compare
            state[SAFE.index(r)]=b;state[SAFE.index(l)]=a
            if l==r:b=a
            payload.extend(struct.pack('<8Q',*state))
            want=list(state);want[0]=semantics(c,a,b);expected.append(want)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        for k,want in enumerate(expected):
            got=list(struct.unpack_from('<8Q',run.stdout,64*k))
            self.assertEqual(got,want,(label,k,'native',vectors[k]))

    def vector_texts(self,exe,vectors,label):
        return self.emit(exe,[(c,l,r,64,OK)for c,l,r,_,_,_ in vectors],label)

    def test_exact_text_and_capacity_for_all_registers(self):
        cases=[]
        for c in range(10):
            for l in range(16):
                for shift in (0,3,9):
                    r=(l+shift)%16;n=len(expected_text(c,l,r))
                    cases+=[(c,l,r,n,OK),(c,l,r,n+9,OK),(c,l,r,n-1,CAPACITY)]
        cases+=[(0,0,0,0,CAPACITY),(10,0,0,64,INVALID),(0,16,0,64,INVALID),(0,0,16,64,INVALID),(2**64-1,17,17,0,INVALID)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for (c,l,r,cap,status),text in zip(cases,texts):
                if status==OK:self.assertEqual(text,expected_text(c,l,r),(mode,c,l,r))
        self.records.append(dict(test='exact-text-capacity',cases=len(cases),preflights_per_native=12,modes=2,passed=True))

    def test_all_sixteen_registers_assemble_in_both_formats(self):
        cases=[(c,l,(l+shift)%16,64,OK)for c in range(10)for l in range(16)for shift in (0,3,9)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'asm-'+mode)
            source=self.work/('all-registers-'+mode+'.asm')
            source.write_bytes(b'bits 64\nsection .text\n'+b''.join(texts))
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('all-registers-%s.%s.o'%(mode,fmt)),source],'all-registers-%s-%s'%(mode,fmt))
        self.records.append(dict(test='all-registers-assemble',sequences=len(cases),formats=['elf64','win64'],modes=2,passed=True))

    def test_native_execution_produces_canonical_bool(self):
        for mode,exe in self.executables.items():
            self.native_run(self.vector_texts(exe,VECTORS,'vectors-'+mode),VECTORS,'native-'+mode)
        self.records.append(dict(test='native-canonical-bool',vectors_per_mode=len(VECTORS),registers=[NAMES[r]for r in SAFE],modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        native_controls=[
            # Signed less-than emitted with the unsigned setcc.
            ('bad-signed-predicate','if condition==bp.SLT{return "setl";}','if condition==bp.SLT{return "setb";}',[v for v in VECTORS if v[0]==6]),
            # setcc without clearing RAX's upper 56 bits (still a valid, assembling instruction).
            ('bad-no-zero-extend','at=copy(buffer,at,"movzx rax, al\\n");','at=copy(buffer,at,"and al, 1\\n");',VECTORS[:8]),
        ]
        for name,old,new,vectors in native_controls:
            self.assertEqual(source.count(old),1,name)
            for mode,exe in self.executables.items():          # the same fixture passes on the real source first
                self.native_run(self.vector_texts(exe,vectors,name+'-good-'+mode),vectors,name+'-good-'+mode)
            for mode,exe in self.build_all(name,source.replace(old,new,1)).items():
                texts=self.vector_texts(exe,vectors,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'native'):self.native_run(texts,vectors,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by='native full 64-bit RAX'))
        old='if at>out.len{return CAPACITY;}';self.assertEqual(source.count(old),1)
        new='var j:usize=0;while j<at&&j<out.len{out[j]=buffer[j];j+=1;}if at>out.len{return CAPACITY;}'
        case=[(6,0,1,10,CAPACITY)]
        for mode,exe in self.executables.items():self.emit(exe,case,'bad-early-out-good-'+mode)
        for mode,exe in self.build_all('bad-early-out',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,case,'bad-early-out-'+mode)
        self.records.append(dict(test='bad-early-out',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))


if __name__=='__main__':unittest.main()
