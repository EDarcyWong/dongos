"""Actual Dong NASM conditional-move emitter: exact text, dual-format assembly, and native flags/registers checks."""
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

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_conditional_move.dg'
DEPENDENCY=ROOT/'lang/bootstrap/branch_plan.dg'      # integrated CR6, staged read-only
OK,INVALID,CAPACITY=0,1,2
NAMES=['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi']+['r%d'%i for i in range(8,16)]
CMOV=['cmove','cmovne','cmovb','cmovbe','cmova','cmovae','cmovl','cmovle','cmovg','cmovge']
SAFE=[0,1,2,6,8,9,10,11]          # caller-saved registers the native stubs may load/clobber (rdi holds the state pointer)
ARITH_FLAGS=0x8d5                 # CF PF AF ZF SF OF
WRAPPER='''module probe.cmov_export;
import bootstrap.nasm_conditional_move as c;
export("dong_cmov_emit") pub unsafe fn emit(condition:u64,destination:u64,source:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return c.emit(condition,destination,source,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_cmov_emit(uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
   case 0:s=dong_cmov_emit(0,0,1,o,32,NULL);break;                                    /* written NULL */
   case 1:s=dong_cmov_emit(0,0,1,o,32,(uint64_t*)(arena+257));break;                  /* written odd */
   case 2:s=dong_cmov_emit(0,0,1,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;  /* written end overflow, empty out */
   case 3:s=dong_cmov_emit(0,0,1,(uint8_t*)(uintptr_t)(UINT64_MAX-3),8,w);break;      /* out end overflow */
   case 4:s=dong_cmov_emit(0,0,1,NULL,32,w);break;                                    /* NULL non-empty out */
   case 5:s=dong_cmov_emit(0,0,1,o,32,(uint64_t*)o);break;                            /* written on out prefix */
   case 6:s=dong_cmov_emit(0,0,1,o,64,(uint64_t*)(o+56));break;                       /* written in out's unused tail */
   case 7:s=dong_cmov_emit(10,0,1,NULL,0,w);break;                                    /* bad condition, capacity 0 */
   case 8:s=dong_cmov_emit(UINT64_MAX,0,1,o,32,w);break;
   case 9:s=dong_cmov_emit(0,16,1,NULL,0,w);break;                                    /* bad destination, capacity 0 */
   case 10:s=dong_cmov_emit(0,0,16,o,32,w);break;                                     /* bad source */
   default:s=dong_cmov_emit(9,UINT64_MAX,UINT64_MAX,o,1,w);break;
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
  uint64_t s=dong_cmov_emit(h[0],h[1],h[2],cap?out+32:NULL,cap,written);
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
  /* [0..7] safe registers, [8] cmp left, [9] cmp right, [10] RFLAGS before, [11] RFLAGS after */
  uint64_t state[14];read_exact(state+1,80);state[11]=state[12]=0;state[0]=state[13]=0xa5a5a5a5a5a5a5a5ull;
  table[i](state+1);
  if(state[0]!=0xa5a5a5a5a5a5a5a5ull||state[13]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  if(fwrite(state+1,8,12,stdout)!=12)exit(92);
 }return 0;
}
'''


def expected_line(c,d,s):
    return ('%s %s, %s\n'%(CMOV[c],NAMES[d],NAMES[s])).encode()


def predicate(c,a,b):
    """Independent u64/i64 interpretation of the CR6 predicates for cmp a, b."""
    sa,sb=(a-(1<<64)if a>>63 else a),(b-(1<<64)if b>>63 else b)
    return [a==b,a!=b,a<b,a<=b,a>b,a>=b,sa<sb,sa<=sb,sa>sb,sa>=sb][c]


TOP,ONES=1<<63,2**64-1
SELECT=0x0123456789abcdef           # source value selected on true (not a bool)
# (condition, dest, source, cmp left, cmp right); every predicate true and false, dest==source, signed/unsigned splits.
VECTORS=[(0,0,1,5,5),(0,2,6,5,6),(1,8,9,5,6),(1,10,11,7,7),(2,0,2,1,TOP),(2,6,8,TOP,1),(3,9,10,4,4),(3,11,0,ONES,0),
         (4,1,2,TOP,1),(4,8,6,1,TOP),(5,10,9,0,0),(5,0,11,0,1),(6,2,1,TOP,1),(6,6,0,1,TOP),(7,8,10,ONES,ONES),
         (7,9,11,0,ONES),(8,10,8,1,TOP),(8,11,2,TOP,1),(9,0,6,ONES,TOP),(9,1,9,TOP,ONES),
         (6,8,8,TOP,1),(4,10,10,1,TOP),(2,11,6,ONES,0x7fffffffffffffff),(6,2,8,ONES,0x7fffffffffffffff)]


class NasmConditionalMoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C28'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
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
        (root/'bootstrap/nasm_conditional_move.dg').write_text(text,encoding='utf-8')
        shutil.copyfile(DEPENDENCY,root/'bootstrap/branch_plan.dg')
        (root/'probe/cmov_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/cmov_export.dg',roots=[root],mode=mode)
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
        """cases: (condition,dest,source,cap,expected_status). Guards are asserted per call before results are used."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c,d,s,cap,_ in cases:payload.extend(struct.pack('<4Q',c,d,s,cap))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],12)
        offset=8;texts=[]
        for index,(c,d,s,cap,status) in enumerate(cases):
            got,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(got,status,(label,index,'status'))
            texts.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return texts

    def native_run(self,lines,vectors,label):
        """cmp from memory sets flags, RFLAGS is captured with pushfq/pop to memory (flags-neutral), registers are
        loaded with mov (flags-neutral), the emitted cmov runs, then registers and RFLAGS are captured again."""
        stub=['bits 64','section .text']
        for i,line in enumerate(lines):
            stub+=['global v%d'%i,'v%d:'%i,'mov rax, [rdi+64]','cmp rax, [rdi+72]','pushfq','pop qword [rdi+80]']
            stub+=['mov %s, [rdi+%d]'%(NAMES[r],8*k)for k,r in enumerate(SAFE)]
            stub.append(line.decode('ascii').rstrip('\n'))
            stub+=['mov [rdi+%d], %s'%(8*k,NAMES[r])for k,r in enumerate(SAFE)]+['pushfq','pop qword [rdi+88]','ret']
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        self.command([self.nasm,'-f',self.native,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.o'),self.work/(label+'.stubs.asm')],label+'-stubs')
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%i for i in range(len(lines))))
        main=main.replace('%TABLE%',','.join('v%d'%i for i in range(len(lines))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.o'),'-o',exe],label+'-native-link')
        payload=bytearray();expected=[]
        for c,d,s,a,b in vectors:
            state=[0x1111111111111111*(j+1)for j in range(8)]
            state[SAFE.index(s)]=SELECT;state[SAFE.index(d)]=0xfeedfacecafebeef
            source_value=state[SAFE.index(s)]                               # dest==source: the shared register's value
            payload.extend(struct.pack('<10Q',*state,a,b))
            want=list(state)
            if predicate(c,a,b):want[SAFE.index(d)]=source_value
            expected.append(want)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        for k,want in enumerate(expected):
            got=list(struct.unpack_from('<12Q',run.stdout,96*k))
            self.assertEqual(got[8:10],list(vectors[k][3:5]),(label,k,'native cmp inputs'))
            self.assertEqual(got[10]&ARITH_FLAGS,got[11]&ARITH_FLAGS,(label,k,'native flags preserved'))
            self.assertEqual(got[:8],want,(label,k,'native destination',vectors[k]))

    def vector_texts(self,exe,vectors,label):
        return self.emit(exe,[(c,d,s,32,OK)for c,d,s,_,_ in vectors],label)

    def test_exact_text_and_capacity_for_all_registers(self):
        cases=[]
        for c in range(10):
            for d in range(16):
                for shift in (0,5,12):
                    s=(d+shift)%16;n=len(expected_line(c,d,s))
                    cases+=[(c,d,s,n,OK),(c,d,s,n+9,OK),(c,d,s,n-1,CAPACITY)]
        cases+=[(0,0,0,0,CAPACITY),(10,0,0,64,INVALID),(0,16,0,64,INVALID),(0,0,16,64,INVALID),(2**64-1,17,17,0,INVALID)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for (c,d,s,cap,status),text in zip(cases,texts):
                if status==OK:self.assertEqual(text,expected_line(c,d,s),(mode,c,d,s))
        self.records.append(dict(test='exact-text-capacity',cases=len(cases),preflights_per_native=12,modes=2,passed=True))

    def test_all_sixteen_registers_assemble_in_both_formats(self):
        cases=[(c,d,(d+shift)%16,32,OK)for c in range(10)for d in range(16)for shift in (0,5,12)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'asm-'+mode)
            source=self.work/('all-registers-'+mode+'.asm')
            source.write_bytes(b'bits 64\nsection .text\n'+b''.join(texts))
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('all-registers-%s.%s.o'%(mode,fmt)),source],'all-registers-%s-%s'%(mode,fmt))
        self.records.append(dict(test='all-registers-assemble',lines=len(cases),formats=['elf64','win64'],modes=2,passed=True))

    def test_native_conditional_move(self):
        truths=[predicate(c,a,b)for c,d,s,a,b in VECTORS]
        for c in range(10):self.assertEqual({predicate(v[0],v[3],v[4])for v in VECTORS[:20]if v[0]==c},{True,False},c)
        for mode,exe in self.executables.items():
            self.native_run(self.vector_texts(exe,VECTORS,'vectors-'+mode),VECTORS,'native-'+mode)
        self.records.append(dict(test='native-cmov',vectors_per_mode=len(VECTORS),true=sum(truths),false=len(truths)-sum(truths),
                                 registers=[NAMES[r]for r in SAFE],rflags_mask=hex(ARITH_FLAGS),modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        old='if condition==bp.SLT{return "cmovl ";}';new='if condition==bp.SLT{return "cmovb ";}';self.assertEqual(source.count(old),1)
        vectors=[v for v in VECTORS if v[0]==6]                             # signed/unsigned divergent inputs
        self.assertTrue(any(predicate(6,v[3],v[4])!=predicate(2,v[3],v[4])for v in vectors))
        for mode,exe in self.executables.items():
            self.native_run(self.vector_texts(exe,vectors,'bad-slt-good-'+mode),vectors,'bad-slt-good-'+mode)
        for mode,exe in self.build_all('bad-slt-as-ult',source.replace(old,new,1)).items():
            texts=self.vector_texts(exe,vectors,'bad-slt-'+mode)
            with self.assertRaisesRegex(AssertionError,'native destination'):self.native_run(texts,vectors,'bad-slt-'+mode)
        self.records.append(dict(test='bad-slt-as-ult',compiled=True,native_executed=True,modes=2,rejected_by='native destination'))
        old='if at>out.len{return CAPACITY;}';self.assertEqual(source.count(old),1)
        new='var j:usize=0;while j<at&&j<out.len{out[j]=buffer[j];j+=1;}if at>out.len{return CAPACITY;}'
        case=[(6,0,1,5,CAPACITY)]
        for mode,exe in self.executables.items():self.emit(exe,case,'bad-early-out-good-'+mode)
        for mode,exe in self.build_all('bad-early-out',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,case,'bad-early-out-'+mode)
        self.records.append(dict(test='bad-early-out',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))


if __name__=='__main__':unittest.main()
