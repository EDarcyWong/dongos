"""Actual Dong NASM scaled-index operand encoder: exact text, dual-format assembly, and native LEA evaluation."""
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

SOURCE=ROOT/'lang/bootstrap/nasm_indexed_operand.dg'
DEPENDENCY=ROOT/'lang/bootstrap/decimal_integer.dg'      # integrated CR4, staged read-only
OK,INVALID,CAPACITY=0,1,2
M64=2**64-1
I32_MIN,I32_MAX=-2**31,2**31-1
NAMES=['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi']+['r%d'%i for i in range(8,16)]
SAFE=[0,1,2,6,8,9,10,11]          # caller-saved registers the native stubs may load/clobber (rdi holds the state pointer)
DEST=11                           # the independent LEA writes r11, which is never a base/index in native vectors
ARITH_FLAGS=0x8d5
WRAPPER='''module probe.indexed_export;
import bootstrap.nasm_indexed_operand as n;
export("dong_indexed_encode") pub unsafe fn encode(base:u64,index:u64,scale:u64,displacement:i64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return n.encode(base,index,scale,displacement,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_indexed_encode(uint64_t,uint64_t,uint64_t,int64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
/* Each preflight keeps every other field valid so only the target check can reject it. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[512],saved[512];const unsigned total=16;
 uint8_t*o=arena+64;uint64_t*w=(uint64_t*)(arena+256);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_indexed_encode(0,1,4,8,o,64,NULL);break;                                    /* written NULL */
   case 1:s=dong_indexed_encode(0,1,4,8,o,64,(uint64_t*)(arena+257));break;                  /* written odd */
   case 2:s=dong_indexed_encode(0,1,4,8,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;  /* written end overflow, empty out */
   case 3:s=dong_indexed_encode(0,1,4,8,(uint8_t*)(uintptr_t)(UINT64_MAX-3),8,w);break;      /* out end overflow */
   case 4:s=dong_indexed_encode(0,1,4,8,NULL,64,w);break;                                    /* NULL non-empty out */
   case 5:s=dong_indexed_encode(0,1,4,8,o,64,(uint64_t*)o);break;                            /* written on out prefix */
   case 6:s=dong_indexed_encode(0,1,4,8,o,96,(uint64_t*)(o+88));break;                       /* written in out's unused tail */
   case 7:s=dong_indexed_encode(16,1,4,8,NULL,0,w);break;                                    /* bad base, capacity 0 */
   case 8:s=dong_indexed_encode(0,16,4,8,o,64,w);break;                                      /* bad index */
   case 9:s=dong_indexed_encode(0,4,4,8,NULL,0,w);break;                                     /* RSP as index, capacity 0 */
   case 10:s=dong_indexed_encode(0,1,3,8,o,64,w);break;                                      /* bad scale */
   case 11:s=dong_indexed_encode(0,1,0,8,NULL,0,w);break;                                    /* scale 0, capacity 0 */
   case 12:s=dong_indexed_encode(0,1,16,8,o,64,w);break;                                     /* scale 16 */
   case 13:s=dong_indexed_encode(0,1,4,(int64_t)2147483648LL,o,64,w);break;                  /* disp i32 max + 1 */
   case 14:s=dong_indexed_encode(0,1,4,-(int64_t)2147483649LL,NULL,0,w);break;               /* disp i32 min - 1, capacity 0 */
   default:s=dong_indexed_encode(0,1,4,INT64_MIN,o,64,w);break;
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
  uint64_t s=dong_indexed_encode(h[0],h[1],h[2],(int64_t)h[3],cap?out+32:NULL,cap,written);
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
  uint64_t state[12];read_exact(state+1,64);state[9]=state[10]=0;state[0]=state[11]=0xa5a5a5a5a5a5a5a5ull;
  table[i](state+1);
  if(state[0]!=0xa5a5a5a5a5a5a5a5ull||state[11]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  if(fwrite(state+1,8,10,stdout)!=10)exit(92);
 }return 0;
}
'''


def expected_text(b,i,s,d):
    tail='' if d==0 else (' + %d'%d if d>0 else ' - %d'%-d)
    return ('[%s + %s*%d%s]'%(NAMES[b],NAMES[i],s,tail)).encode()


def semantics(bv,iv,s,d):
    """Independent arbitrary-precision effective address modulo 2^64."""
    return (bv+iv*s+d)&M64


TOP,ONES=1<<63,M64
# (base, index, scale, disp, base value, index value); 24 per mode, never using r11 (the LEA destination).
VECTORS=[(0,1,1,0,100,7),(1,2,2,8,0x1000,3),(2,6,4,-4,0x2000,5),(6,8,8,I32_MAX,0,1),(8,9,1,I32_MIN,0,0),
         (9,10,4,16,0x7fff0000,0x10),(10,0,8,-1,1,1),(0,0,4,0,5,5),(2,2,8,12,ONES,1),(6,1,4,I32_MAX,ONES,ONES),
         (1,6,4,-2147483647,TOP,TOP),(8,8,2,3,TOP,TOP),(9,2,4,0,0x123456789,0x1000),(10,1,4,-100,0x5000,4),
         (0,8,4,32,0xfffffffffffffff0,4),(2,9,1,-8,8,0),(6,10,2,1,ONES,TOP),(1,0,8,0,0,0x2000000000000000),
         (8,6,4,255,0x10,ONES),(9,9,4,-1,1,TOP),(10,10,1,I32_MIN,0,0),(0,2,4,1,TOP|1,0x4000000000000000),
         (2,1,8,-77,123,456),(6,0,4,I32_MAX,0x80000000,0x40000000)]


class NasmIndexedOperandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-nasm-indexed-operand'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
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
        (root/'bootstrap/nasm_indexed_operand.dg').write_text(text,encoding='utf-8')
        shutil.copyfile(DEPENDENCY,root/'bootstrap/decimal_integer.dg')
        (root/'probe/indexed_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/indexed_export.dg',roots=[root],mode=mode)
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
        """cases: (base,index,scale,disp,cap,expected_status). Guards are asserted per call before results are used."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for b,i,s,d,cap,_ in cases:payload.extend(struct.pack('<3QqQ',b,i,s,d,cap))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],16)
        offset=8;texts=[]
        for index,case in enumerate(cases):
            got,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(got,case[5],(label,index,'status'))
            texts.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return texts

    def native_run(self,operands,vectors,label):
        """Evaluate each emitted operand with an independent 'lea r11, <operand>' (never dereferenced)."""
        stub=['bits 64','section .text']
        for k,operand in enumerate(operands):
            stub+=['global v%d'%k,'v%d:'%k]+['mov %s, [rdi+%d]'%(NAMES[r],8*j)for j,r in enumerate(SAFE)]
            stub+=['pushfq','pop qword [rdi+64]','lea r11, '+operand.decode('ascii'),'pushfq','pop qword [rdi+72]']
            stub+=['mov [rdi+%d], %s'%(8*j,NAMES[r])for j,r in enumerate(SAFE)]+['ret']
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        self.command([self.nasm,'-f',self.native,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.o'),self.work/(label+'.stubs.asm')],label+'-stubs')
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(operands))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(operands))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.o'),'-o',exe],label+'-native-link')
        payload=bytearray();expected=[]
        for b,i,s,d,bv,iv in vectors:
            state=[0x1111111111111111*(j+1)for j in range(8)]
            state[SAFE.index(i)]=iv;state[SAFE.index(b)]=bv
            if b==i:iv=bv                                                  # base==index share one register value
            payload.extend(struct.pack('<8Q',*state))
            want=list(state);want[SAFE.index(DEST)]=semantics(bv,iv,s,d);expected.append(want)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        for k,want in enumerate(expected):
            got=list(struct.unpack_from('<10Q',run.stdout,80*k))
            self.assertEqual(got[8]&ARITH_FLAGS,got[9]&ARITH_FLAGS,(label,k,'native flags preserved'))
            self.assertEqual(got[SAFE.index(DEST)],want[SAFE.index(DEST)],(label,k,'native lea address',vectors[k]))
            self.assertEqual(got[:8],want,(label,k,'native other registers'))

    def test_exact_text_and_capacity_for_all_registers(self):
        cases=[];displacements=[0,1,-1,I32_MAX,I32_MIN,4096,-4096]
        for b in range(16):
            for k,shift in enumerate((1,6,11)):
                i=(b+shift)%16
                if i==4:i=12                                          # RSP cannot index; R12 can
                s=(1,2,4,8)[(b+k)%4];d=displacements[(b*3+k)%len(displacements)];n=len(expected_text(b,i,s,d))
                cases+=[(b,i,s,d,n,OK),(b,i,s,d,n+9,OK),(b,i,s,d,n-1,CAPACITY)]
        for i in range(16):
            if i!=4:cases.append((0,i,8,-5,64,OK))                    # every legal index, including r12
        cases+=[(5,12,4,I32_MIN,64,OK),(4,12,1,I32_MAX,64,OK),(3,3,2,0,64,OK),(0,1,4,8,0,CAPACITY),
                (0,4,4,8,64,INVALID),(4,4,1,0,64,INVALID),(16,0,1,0,64,INVALID),(0,16,1,0,64,INVALID),
                (0,1,3,0,64,INVALID),(0,1,0,0,0,INVALID),(0,1,4,I32_MAX+1,64,INVALID),(0,1,4,I32_MIN-1,0,INVALID)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for (b,i,s,d,cap,status),text in zip(cases,texts):
                if status==OK:self.assertEqual(text,expected_text(b,i,s,d),(mode,b,i,s,d))
        self.records.append(dict(test='exact-text-capacity',cases=len(cases),preflights_per_native=16,modes=2,passed=True))

    def test_all_operands_assemble_in_both_formats(self):
        cases=[]
        for b in range(16):
            for k,shift in enumerate((1,6,11)):
                i=(b+shift)%16;i=12 if i==4 else i
                cases.append((b,i,(1,2,4,8)[(b+k)%4],(0,I32_MAX,I32_MIN)[k],64,OK))
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'asm-'+mode)
            source=self.work/('all-operands-'+mode+'.asm')
            source.write_bytes(b'bits 64\nsection .text\n'+b''.join(b'lea rax, '+t+b'\n'+b'mov rax, '+t+b'\n'for t in texts))
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('all-operands-%s.%s.o'%(mode,fmt)),source],'all-operands-%s-%s'%(mode,fmt))
        self.records.append(dict(test='all-operands-assemble',operands=len(cases),formats=['elf64','win64'],modes=2,passed=True))

    def vector_texts(self,exe,vectors,label):
        return self.emit(exe,[(b,i,s,d,64,OK)for b,i,s,d,_,_ in vectors],label)

    def test_native_lea_matches_effective_address(self):
        for mode,exe in self.executables.items():
            self.native_run(self.vector_texts(exe,VECTORS,'vectors-'+mode),VECTORS,'native-'+mode)
        self.records.append(dict(test='native-lea',vectors_per_mode=len(VECTORS),destination=NAMES[DEST],modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        old='let shown=scale;';new='var shown=scale;if shown==4{shown=2;}';self.assertEqual(source.count(old),1)
        vectors=[v for v in VECTORS if v[2]==4 and v[5]!=0]
        for mode,exe in self.executables.items():
            self.native_run(self.vector_texts(exe,vectors,'bad-scale-good-'+mode),vectors,'bad-scale-good-'+mode)
        for mode,exe in self.build_all('bad-scale4-as-2',source.replace(old,new,1)).items():
            texts=self.vector_texts(exe,vectors,'bad-scale-'+mode)
            with self.assertRaisesRegex(AssertionError,'native lea address'):self.native_run(texts,vectors,'bad-scale-'+mode)
        self.records.append(dict(test='bad-scale4-as-2',compiled=True,native_executed=True,modes=2,rejected_by='native lea address'))
        old='if at>out.len{return CAPACITY;}';self.assertEqual(source.count(old),1)
        new='var j:usize=0;while j<at&&j<out.len{out[j]=buffer[j];j+=1;}if at>out.len{return CAPACITY;}'
        case=[(0,1,4,-16,6,CAPACITY)]
        for mode,exe in self.executables.items():self.emit(exe,case,'bad-early-out-good-'+mode)
        for mode,exe in self.build_all('bad-early-out',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,case,'bad-early-out-'+mode)
        self.records.append(dict(test='bad-early-out',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))


if __name__=='__main__':unittest.main()
