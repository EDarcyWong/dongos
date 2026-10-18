"""Actual Dong NASM variable-shift (CL) emitter: exact text, dual-format assembly, and native execution."""
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

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_variable_shift.dg'
OK,INVALID,CAPACITY=0,1,2
M64=2**64-1
NAMES=['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi']+['r%d'%i for i in range(8,16)]
MNEMONICS=['shl','shr','sar']
SAFE=[0,1,2,6,8,9,10,11]          # caller-saved registers the native stubs may load/clobber (rdi holds the state pointer)
RCX=1
WRAPPER='''module probe.shift_export;
import bootstrap.nasm_variable_shift as v;
export("dong_shift_emit") pub unsafe fn emit(operation:u64,destination:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return v.emit(operation,destination,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_shift_emit(uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
/* Each preflight keeps every other field valid so only the target check can reject it. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[512],saved[512];const unsigned total=11;
 uint8_t*o=arena+64;uint64_t*w=(uint64_t*)(arena+256);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_shift_emit(0,0,o,32,NULL);break;                                    /* written NULL */
   case 1:s=dong_shift_emit(0,0,o,32,(uint64_t*)(arena+257));break;                  /* written odd */
   case 2:s=dong_shift_emit(0,0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;  /* written end overflow, empty out */
   case 3:s=dong_shift_emit(0,0,(uint8_t*)(uintptr_t)(UINT64_MAX-3),8,w);break;      /* out end overflow */
   case 4:s=dong_shift_emit(0,0,NULL,32,w);break;                                    /* NULL non-empty out */
   case 5:s=dong_shift_emit(0,0,o,32,(uint64_t*)o);break;                            /* written on out prefix */
   case 6:s=dong_shift_emit(0,0,o,64,(uint64_t*)(o+56));break;                       /* written in out's unused tail */
   case 7:s=dong_shift_emit(3,0,NULL,0,w);break;                                     /* bad operation, capacity 0 */
   case 8:s=dong_shift_emit(UINT64_MAX,0,o,32,w);break;
   case 9:s=dong_shift_emit(0,16,NULL,0,w);break;                                    /* bad destination, capacity 0 */
   default:s=dong_shift_emit(2,UINT64_MAX,o,1,w);break;
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
  uint64_t h[3];read_exact(h,sizeof(h));uint64_t cap=h[2];if(cap>4096)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=dong_shift_emit(h[0],h[1],cap?out+32:NULL,cap,written);
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


def expected_line(op,d):
    return ('%s %s, cl\n'%(MNEMONICS[op],NAMES[d])).encode()


def semantics(op,value,count):
    """Independent arbitrary-precision reference: effective count is count&63, result is the low 64 bits."""
    k=count&63
    if op==0:return (value<<k)&M64
    if op==1:return value>>k
    signed=value-(1<<64)if value>>63 else value
    return (signed>>k)&M64


TOP,ONES=1<<63,M64
# (operation, destination, value, rcx count); for dest==RCX the value is the count's own bit pattern. 24 per mode.
VECTORS=[(0,0,1,0),(0,2,1,1),(0,6,ONES,31),(0,8,0x8000000000000001,32),(0,9,1,63),(0,10,3,64),(0,11,ONES,65),(0,1,0x41,0x41),
         (1,0,TOP,0),(1,2,TOP,1),(1,6,ONES,32),(1,8,ONES,63),(1,9,TOP,64),(1,10,TOP,65),(1,1,M64,M64),
         (2,0,TOP,1),(2,2,TOP,63),(2,6,ONES,31),(2,8,0x7fffffffffffffff,62),(2,9,TOP|0x100,64),(2,10,TOP,65),(2,11,0,M64),
         (2,1,TOP|0x3f,TOP|0x3f),(2,0,0x8000000000001234,M64)]


class NasmVariableShiftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C26'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
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
        (root/'bootstrap/nasm_variable_shift.dg').write_text(text,encoding='utf-8')
        (root/'probe/shift_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/shift_export.dg',roots=[root],mode=mode)
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
        """cases: (op,dest,cap,expected_status). Guards are asserted per call before results are used."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for op,d,cap,_ in cases:payload.extend(struct.pack('<3Q',op,d,cap))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],11)
        offset=8;texts=[]
        for index,(op,d,cap,status) in enumerate(cases):
            got,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(got,status,(label,index,'status'))
            texts.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return texts

    def native_run(self,lines,vectors,label):
        """Assemble the emitted lines into SysV stubs, run them, and compare every safe register (full 64 bits)."""
        stub=['bits 64','section .text']
        for i,line in enumerate(lines):
            stub+=['global v%d'%i,'v%d:'%i]+['mov %s, [rdi+%d]'%(NAMES[r],8*k)for k,r in enumerate(SAFE)]
            stub.append(line.decode('ascii').rstrip('\n'))
            stub+=['mov [rdi+%d], %s'%(8*k,NAMES[r])for k,r in enumerate(SAFE)]+['ret']
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        self.command([self.nasm,'-f',self.native,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.o'),self.work/(label+'.stubs.asm')],label+'-stubs')
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%i for i in range(len(lines))))
        main=main.replace('%TABLE%',','.join('v%d'%i for i in range(len(lines))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.o'),'-o',exe],label+'-native-link')
        payload=bytearray();expected=[]
        for op,d,value,count in vectors:
            state=[0x1111111111111111*(j+1)for j in range(8)]
            state[SAFE.index(RCX)]=count;state[SAFE.index(d)]=value     # dest==RCX: value and count share one bit pattern
            if d==RCX:self.assertEqual(value,count)
            payload.extend(struct.pack('<8Q',*state))
            want=list(state);want[SAFE.index(d)]=semantics(op,value,count);expected.append(want)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        for k,want in enumerate(expected):
            got=list(struct.unpack_from('<8Q',run.stdout,64*k))
            self.assertEqual(got,want,(label,k,'native',vectors[k]))

    def vector_texts(self,exe,vectors,label):
        return self.emit(exe,[(op,d,32,OK)for op,d,_,_ in vectors],label)

    def test_exact_text_and_capacity_for_all_registers(self):
        cases=[]
        for op in range(3):
            for d in range(16):
                n=len(expected_line(op,d));cases+=[(op,d,n,OK),(op,d,n+9,OK),(op,d,n-1,CAPACITY)]
        cases+=[(0,0,0,CAPACITY),(3,0,64,INVALID),(0,16,64,INVALID),(2**64-1,17,0,INVALID)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for (op,d,cap,status),text in zip(cases,texts):
                if status==OK:self.assertEqual(text,expected_line(op,d),(mode,op,d))
        self.records.append(dict(test='exact-text-capacity',cases=len(cases),preflights_per_native=11,modes=2,passed=True))

    def test_all_sixteen_registers_assemble_in_both_formats(self):
        cases=[(op,d,32,OK)for op in range(3)for d in range(16)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'asm-'+mode)
            source=self.work/('all-registers-'+mode+'.asm')
            source.write_bytes(b'bits 64\nsection .text\n'+b''.join(texts))
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('all-registers-%s.%s.o'%(mode,fmt)),source],'all-registers-%s-%s'%(mode,fmt))
        self.records.append(dict(test='all-registers-assemble',lines=len(cases),formats=['elf64','win64'],modes=2,passed=True))

    def test_native_execution_masks_count_to_six_bits(self):
        for mode,exe in self.executables.items():
            self.native_run(self.vector_texts(exe,VECTORS,'vectors-'+mode),VECTORS,'native-'+mode)
        self.records.append(dict(test='native-variable-shift',vectors_per_mode=len(VECTORS),registers=[NAMES[r]for r in SAFE],modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        old='return "sar ";';new='return "shr ";';self.assertEqual(source.count(old),1)
        vectors=[v for v in VECTORS if v[0]==2 and v[2]>>63]          # SAR on negative values
        for mode,exe in self.executables.items():
            self.native_run(self.vector_texts(exe,vectors,'bad-sar-good-'+mode),vectors,'bad-sar-good-'+mode)
        for mode,exe in self.build_all('bad-sar-as-shr',source.replace(old,new,1)).items():
            texts=self.vector_texts(exe,vectors,'bad-sar-'+mode)
            with self.assertRaisesRegex(AssertionError,'native'):self.native_run(texts,vectors,'bad-sar-'+mode)
        self.records.append(dict(test='bad-sar-as-shr',compiled=True,native_executed=True,modes=2,rejected_by='native negative SAR result'))
        old='if at>out.len{return CAPACITY;}';self.assertEqual(source.count(old),1)
        new='if at>out.len{*written=at;return CAPACITY;}'
        case=[(2,8,4,CAPACITY)]
        for mode,exe in self.executables.items():self.emit(exe,case,'bad-early-written-good-'+mode)
        for mode,exe in self.build_all('bad-early-written',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,case,'bad-early-written-'+mode)
        self.records.append(dict(test='bad-early-written',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))


if __name__=='__main__':unittest.main()
