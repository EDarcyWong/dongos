"""Actual Dong NASM division-guard emitter: exact text, dual-format assembly, and native routing (no division executed)."""
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

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_division_guard.dg'
DEPENDENCY=ROOT/'lang/bootstrap/decimal_integer.dg'      # integrated CR4, staged read-only
OK,INVALID,CAPACITY=0,1,2
M64=NONE=2**64-1
TOP=1<<63
WRAPPER='''module probe.guard_export;
import bootstrap.nasm_division_guard as g;
export("dong_guard_emit") pub unsafe fn emit(signed:bool,zero_target:u64,overflow_target:u64,success_target:u64,
 out:*u8,no:usize,written:*usize)u64{unsafe{
 return g.emit(signed,zero_target,overflow_target,success_target,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_guard_emit(uint8_t,uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
/* Each preflight keeps every other field valid so only the target check can reject it. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[1024],saved[1024];const unsigned total=13;
 uint8_t*o=arena+64;uint64_t*w=(uint64_t*)(arena+768);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_guard_emit(1,1,2,3,o,256,NULL);break;                                     /* written NULL */
   case 1:s=dong_guard_emit(1,1,2,3,o,256,(uint64_t*)(arena+769));break;                   /* written odd */
   case 2:s=dong_guard_emit(1,1,2,3,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;    /* written end overflow, empty out */
   case 3:s=dong_guard_emit(1,1,2,3,(uint8_t*)(uintptr_t)(UINT64_MAX-15),16,w);break;      /* out end overflow */
   case 4:s=dong_guard_emit(1,1,2,3,NULL,256,w);break;                                     /* NULL non-empty out */
   case 5:s=dong_guard_emit(1,1,2,3,o,256,(uint64_t*)o);break;                             /* written on out prefix */
   case 6:s=dong_guard_emit(1,1,2,3,o,512,(uint64_t*)(o+504));break;                       /* written in out's unused tail */
   case 7:s=dong_guard_emit(1,UINT64_MAX,2,3,NULL,0,w);break;                              /* NONE zero target, capacity 0 */
   case 8:s=dong_guard_emit(1,1,UINT64_MAX,3,o,256,w);break;                               /* NONE overflow target */
   case 9:s=dong_guard_emit(1,1,2,UINT64_MAX,o,256,w);break;                               /* NONE success target */
   case 10:s=dong_guard_emit(0,1,UINT64_MAX,3,NULL,0,w);break;                             /* unsigned still checks overflow target */
   case 11:s=dong_guard_emit(0,UINT64_MAX,2,3,o,256,w);break;
   default:s=dong_guard_emit(0,1,2,UINT64_MAX,o,1,w);break;
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
  uint64_t h[5];read_exact(h,sizeof(h));uint64_t cap=h[4];if(cap>4096)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=dong_guard_emit((uint8_t)h[0],h[1],h[2],h[3],cap?out+32:NULL,cap,written);
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
  /* [0] rdi dividend, [1] rsi divisor, [2..6] rcx rdx r8 r9 r10 sentinels, [7] block marker */
  uint64_t state[10];read_exact(state+1,56);state[8]=0x5a5a5a5a5a5a5a5aull;state[0]=state[9]=0xa5a5a5a5a5a5a5a5ull;
  table[i](state+1);
  if(state[0]!=0xa5a5a5a5a5a5a5a5ull||state[9]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  if(fwrite(state+1,8,8,stdout)!=8)exit(92);
 }return 0;
}
'''
REGS=['rdi','rsi','rcx','rdx','r8','r9','r10']


def expected_text(signed,z,o,s):
    if not signed:return ('test rsi, rsi\njz __dong_b%d\njmp __dong_b%d\n'%(z,s)).encode()
    return ('test rsi, rsi\njz __dong_b%d\ncmp rsi, -1\njne __dong_b%d\nmov rax, 0x8000000000000000\n'
            'cmp rdi, rax\nje __dong_b%d\njmp __dong_b%d\n'%(z,s,o,s)).encode()


def route(signed,a,b):
    """Independent classification of a division before it runs."""
    if b==0:return 'zero'
    if signed and b==M64 and a==TOP:return 'overflow'
    return 'success'


SMAX=TOP-1
# (signed, dividend, divisor, zero target, overflow target, success target); 24 per mode, labels unique per vector.
VECTORS=[(1,7,2,10,11,12),(1,7,0,13,14,15),(1,TOP,M64,16,17,18),(1,TOP,1,19,20,21),(1,SMAX,M64,22,23,24),
         (1,M64,M64,25,26,27),(1,0,M64,28,29,30),(1,TOP,0,31,32,33),(1,TOP|1,M64,34,35,36),(1,5,TOP,37,38,39),
         (1,TOP,M64,0,40,41),(1,3,0,M64-1,42,43),(1,TOP,M64,44,2**63+5,45),(1,9,3,46,47,2**40),
         (0,7,2,50,51,52),(0,7,0,53,54,55),(0,TOP,M64,56,57,58),(0,M64,M64,59,60,61),(0,M64,1,62,63,64),
         (0,0,0,65,66,67),(0,TOP,TOP,68,69,70),(0,1,M64,71,72,73),
         (1,4,0,74,75,74),(1,TOP,M64,76,77,76)]          # identical zero/success targets are allowed


class NasmDivisionGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C31'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
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
        """Stage only this component and the integrated CR4 module, then build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_division_guard.dg').write_text(text,encoding='utf-8')
        shutil.copyfile(DEPENDENCY,root/'bootstrap/decimal_integer.dg')
        (root/'probe/guard_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/guard_export.dg',roots=[root],mode=mode)
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
        """cases: (signed,zero,overflow,success,cap,expected_status). Guards are asserted per call before results are used."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for sg,z,o,s,cap,_ in cases:payload.extend(struct.pack('<5Q',sg,z,o,s,cap))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],13)
        offset=8;texts=[]
        for index,case in enumerate(cases):
            got,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(got,case[5],(label,index,'status'))
            texts.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return texts

    def native_run(self,texts,vectors,label):
        """The emitted guard routes into independently defined blocks that record their label number; no division runs."""
        stub=['bits 64','section .text'];defined=set()
        for k,(text,(sg,a,b,z,o,s)) in enumerate(zip(texts,vectors)):
            stub+=['global v%d'%k,'v%d:'%k,'mov r11, rdi']+['mov %s, [r11+%d]'%(r,8*j)for j,r in enumerate(REGS)]
            stub+=text.decode('ascii').rstrip('\n').split('\n')
            stub+=['ud2']                                                    # the guard must always branch away
            for target in (z,o,s):
                if target in defined:continue
                defined.add(target)
                stub+=['__dong_b%d:'%target]+['mov [r11+%d], %s'%(8*j,r)for j,r in enumerate(REGS)]
                stub+=['mov rax, %d'%target,'mov [r11+56], rax','ret']
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(texts))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(texts))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],label+'-native-link')
        payload=bytearray();inputs=[]
        for sg,a,b,z,o,s in vectors:
            state=[a,b]+[0x2222222222222222*(j+1)for j in range(5)];inputs.append(state)
            payload.extend(struct.pack('<7Q',*state))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        for k,(sg,a,b,z,o,s) in enumerate(vectors):
            got=list(struct.unpack_from('<8Q',run.stdout,64*k))
            want={'zero':z,'overflow':o,'success':s}[route(sg,a,b)]
            self.assertEqual(got[7],want,(label,k,'native route',route(sg,a,b),vectors[k]))
            self.assertEqual(got[:7],inputs[k],(label,k,'native preserved registers'))

    def test_exact_text_and_capacity(self):
        cases=[]
        for sg in (0,1):
            for z,o,s in ((0,0,0),(1,2,3),(9,10,99),(100,1000,10**19),(M64-1,2**63,7),(12345678901234567890,M64-1,0)):
                n=len(expected_text(sg,z,o,s))
                cases+=[(sg,z,o,s,n,OK),(sg,z,o,s,n+9,OK),(sg,z,o,s,n-1,CAPACITY)]
        cases+=[(1,1,2,3,0,CAPACITY),(0,1,2,3,0,CAPACITY),(1,NONE,2,3,256,INVALID),(1,1,NONE,3,256,INVALID),(1,1,2,NONE,256,INVALID),
                (0,1,NONE,3,256,INVALID),(0,NONE,NONE,NONE,0,INVALID)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for (sg,z,o,s,cap,status),text in zip(cases,texts):
                if status==OK:self.assertEqual(text,expected_text(sg,z,o,s),(mode,sg,z,o,s))
        self.records.append(dict(test='exact-text-capacity',cases=len(cases),preflights_per_native=13,modes=2,passed=True))

    def longest_cases(self):
        """R1: every target a legal 20-digit label (same and distinct). Signed text is 197 bytes, unsigned 79."""
        cases=[]
        for sg in (1,0):
            for z,o,s in ((M64-1,M64-1,M64-1),(M64-1,M64-2,M64-3),(10**19,M64-1,12345678901234567890)):
                n=len(expected_text(sg,z,o,s))
                cases+=[(sg,z,o,s,n,OK),(sg,z,o,s,n+9,OK),(sg,z,o,s,n-1,CAPACITY),(sg,z,o,s,0,CAPACITY)]
        return cases

    def test_longest_twenty_digit_labels(self):
        cases=self.longest_cases()
        self.assertEqual(len(expected_text(1,M64-1,M64-1,M64-1)),197)
        self.assertEqual(len(expected_text(0,M64-1,M64-1,M64-1)),79)
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'longest-'+mode)
            for (sg,z,o,s,cap,status),text in zip(cases,texts):
                if status==OK:self.assertEqual(text,expected_text(sg,z,o,s),(mode,sg,z,o,s))
        self.records.append(dict(test='longest-twenty-digit-labels',cases=len(cases),signed_max_bytes=197,modes=2,passed=True))

    def test_guard_text_assembles_in_both_formats(self):
        cases=[(sg,z,o,s,256,OK)for sg in (0,1)for z,o,s in ((0,1,2),(3,4,5),(M64-1,2**63,9),(M64-1,M64-1,M64-1),(M64-1,M64-2,M64-3))]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'asm-'+mode)
            labels=sorted({t for _,z,o,s,_,_ in cases for t in (z,o,s)})
            source=self.work/('guards-'+mode+'.asm')
            source.write_bytes(b'bits 64\nsection .text\n'+b''.join(texts)+b''.join(b'__dong_b%d:\nret\n'%l for l in labels))
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('guards-%s.%s.o'%(mode,fmt)),source],'guards-%s-%s'%(mode,fmt))
        self.records.append(dict(test='guards-assemble',sequences=len(cases),formats=['elf64','win64'],modes=2,passed=True))

    def vector_texts(self,exe,vectors,label):
        return self.emit(exe,[(sg,z,o,s,256,OK)for sg,a,b,z,o,s in vectors],label)

    def test_native_routing(self):
        routes=[route(sg,a,b)for sg,a,b,_,_,_ in VECTORS]
        self.assertEqual(set(routes),{'zero','overflow','success'})
        for mode,exe in self.executables.items():
            self.native_run(self.vector_texts(exe,VECTORS,'vectors-'+mode),VECTORS,'native-'+mode)
        self.records.append(dict(test='native-routing',vectors_per_mode=len(VECTORS),routes={r:routes.count(r)for r in set(routes)},
                                 division_executed=False,modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        old='at=jump(buffer,at,"je ",overflow);';new='at=jump(buffer,at,"jne ",overflow);';self.assertEqual(source.count(old),1)
        vectors=[v for v in VECTORS if v[0]==1 and v[2]==M64]                # signed divisor -1: MIN and non-MIN dividends
        for mode,exe in self.executables.items():
            self.native_run(self.vector_texts(exe,vectors,'bad-min-good-'+mode),vectors,'bad-min-good-'+mode)
        for mode,exe in self.build_all('bad-inverted-min',source.replace(old,new,1)).items():
            texts=self.vector_texts(exe,vectors,'bad-min-'+mode)
            with self.assertRaisesRegex(AssertionError,'native route'):self.native_run(texts,vectors,'bad-min-'+mode)
        self.records.append(dict(test='bad-inverted-min',compiled=True,native_executed=True,modes=2,rejected_by='native route'))
        old='if at>out.len{return CAPACITY;}';self.assertEqual(source.count(old),1)
        new='var j:usize=0;while j<at&&j<out.len{out[j]=buffer[j];j+=1;}if at>out.len{return CAPACITY;}'
        case=[(1,1,2,3,20,CAPACITY)]
        for mode,exe in self.executables.items():self.emit(exe,case,'bad-early-out-good-'+mode)
        for mode,exe in self.build_all('bad-early-out',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,case,'bad-early-out-'+mode)
        self.records.append(dict(test='bad-early-out',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))
        # R1: the original 192-byte scratch bound must make the new longest-label check fail (it panics on legal input).
        old='var text:[224]u8=[0;224];let buffer=slice_from_raw_parts(&text[0],224);';self.assertEqual(source.count(old),1)
        new='var text:[192]u8=[0;192];let buffer=slice_from_raw_parts(&text[0],192);'
        cases=self.longest_cases()
        for mode,exe in self.executables.items():self.emit(exe,cases,'bad-192-good-'+mode)
        for mode,exe in self.build_all('bad-192-bound',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'unexpected panic'):self.emit(exe,cases,'bad-192-'+mode)
        self.records.append(dict(test='bad-192-bound',compiled=True,native_executed=True,modes=2,rejected_by='longest-label check (native panic exit)'))


if __name__=='__main__':unittest.main()
