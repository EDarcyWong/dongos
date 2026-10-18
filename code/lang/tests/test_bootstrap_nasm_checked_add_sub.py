"""Actual Dong NASM checked add/sub emitter: exact text, dual-format assembly, and native trap/fallthrough execution."""
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

SOURCE=ROOT/'lang/bootstrap/nasm_checked_add_sub.dg'
DEPENDENCY=ROOT/'lang/bootstrap/decimal_integer.dg'      # integrated CR4, staged read-only
OK,INVALID,CAPACITY=0,1,2
M64=NONE=2**64-1
NAMES=['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi']+['r%d'%i for i in range(8,16)]
SAFE=[0,1,2,6,8,9,10,11]          # caller-saved registers the native stubs may load/clobber (rdi holds the state pointer)
WRAPPER='''module probe.checked_export;
import bootstrap.nasm_checked_add_sub as c;
export("dong_checked_emit") pub unsafe fn emit(operation:u64,signed:bool,destination:u64,source:u64,trap_block:u64,
 out:*u8,no:usize,written:*usize)u64{unsafe{
 return c.emit(operation,signed,destination,source,trap_block,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_checked_emit(uint64_t,uint8_t,uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
/* Each preflight keeps every other field valid so only the target check can reject it. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[512],saved[512];const unsigned total=13;
 uint8_t*o=arena+64;uint64_t*w=(uint64_t*)(arena+256);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_checked_emit(0,1,0,1,7,o,64,NULL);break;                                    /* written NULL */
   case 1:s=dong_checked_emit(0,1,0,1,7,o,64,(uint64_t*)(arena+257));break;                  /* written odd */
   case 2:s=dong_checked_emit(0,1,0,1,7,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;  /* written end overflow, empty out */
   case 3:s=dong_checked_emit(0,1,0,1,7,(uint8_t*)(uintptr_t)(UINT64_MAX-3),8,w);break;      /* out end overflow */
   case 4:s=dong_checked_emit(0,1,0,1,7,NULL,64,w);break;                                    /* NULL non-empty out */
   case 5:s=dong_checked_emit(0,1,0,1,7,o,64,(uint64_t*)o);break;                            /* written on out prefix */
   case 6:s=dong_checked_emit(0,1,0,1,7,o,96,(uint64_t*)(o+88));break;                       /* written in out's unused tail */
   case 7:s=dong_checked_emit(2,1,0,1,7,NULL,0,w);break;                                     /* bad operation, capacity 0 */
   case 8:s=dong_checked_emit(0,1,16,1,7,o,64,w);break;                                      /* bad destination */
   case 9:s=dong_checked_emit(0,0,0,16,7,NULL,0,w);break;                                    /* bad source, capacity 0 */
   case 10:s=dong_checked_emit(0,1,0,1,UINT64_MAX,NULL,0,w);break;                           /* NONE trap block, capacity 0 */
   case 11:s=dong_checked_emit(1,0,0,1,UINT64_MAX,o,64,w);break;                             /* NONE trap block */
   default:s=dong_checked_emit(UINT64_MAX,1,UINT64_MAX,UINT64_MAX,UINT64_MAX,o,1,w);break;
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
  uint64_t h[6];read_exact(h,sizeof(h));uint64_t cap=h[5];if(cap>4096)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=dong_checked_emit(h[0],(uint8_t)h[1],h[2],h[3],h[4],cap?out+32:NULL,cap,written);
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
  uint64_t state[11];read_exact(state+1,64);state[9]=0x5a5a5a5a5a5a5a5aull;   /* path marker: set by fallthrough or trap */
  state[0]=state[10]=0xa5a5a5a5a5a5a5a5ull;
  table[i](state+1);
  if(state[0]!=0xa5a5a5a5a5a5a5a5ull||state[10]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  if(fwrite(state+1,8,9,stdout)!=9)exit(92);
 }return 0;
}
'''


def expected_text(op,signed,d,s,block):
    return ('%s %s, %s\n%s __dong_b%d\n'%(['add','sub'][op],NAMES[d],NAMES[s],'jo'if signed else'jc',block)).encode()


def semantics(op,signed,a,b):
    """Independent arbitrary-precision result and overflow decision: (wrapped value, trapped)."""
    if signed:
        sa,sb=(a-(1<<64)if a>>63 else a),(b-(1<<64)if b>>63 else b)
        exact=sa+sb if op==0 else sa-sb
        return exact&M64,not(-2**63<=exact<=2**63-1)
    exact=a+b if op==0 else a-b
    return exact&M64,not(0<=exact<=M64)


TOP,ONES,SMAX=1<<63,M64,(1<<63)-1
# (operation, signed, dest, source, a, b, trap block); 24 per mode, distinct block labels.
VECTORS=[(0,1,0,1,SMAX,1,100),(0,1,8,9,SMAX,0,101),(1,1,1,2,TOP,1,102),(1,1,9,8,TOP,0,103),
         (0,1,2,6,ONES,ONES,104),(0,1,10,11,TOP,TOP,105),(1,1,6,10,5,7,106),(1,1,11,0,0,TOP,107),
         (0,1,0,0,0x4000000000000000,0x4000000000000000,108),(1,1,8,8,TOP,TOP,109),
         (0,0,0,1,ONES,1,110),(0,0,8,9,ONES,0,111),(1,0,1,2,0,1,112),(1,0,9,8,1,1,113),
         (0,0,2,6,TOP,TOP,114),(0,0,10,11,TOP,SMAX,115),(1,0,6,10,5,7,116),(1,0,11,0,TOP,1,117),
         (0,0,0,0,TOP,TOP,118),(1,0,8,8,ONES,ONES,119),(0,0,1,1,SMAX,SMAX,120),
         (0,1,9,10,123456789,987654321,0),(1,0,2,11,10,3,2**64-2),(1,1,10,1,1,TOP,12345678901234567890)]


class NasmCheckedAddSubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/C24'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
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
        (root/'bootstrap/nasm_checked_add_sub.dg').write_text(text,encoding='utf-8')
        shutil.copyfile(DEPENDENCY,root/'bootstrap/decimal_integer.dg')
        (root/'probe/checked_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/checked_export.dg',roots=[root],mode=mode)
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
        """cases: (op,signed,dest,source,block,cap,expected_status). Guards are asserted per call before results are used."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for op,sg,d,s,blk,cap,_ in cases:payload.extend(struct.pack('<6Q',op,sg,d,s,blk,cap))
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
            self.assertEqual(got,case[6],(label,index,'status'))
            texts.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return texts

    def native_run(self,texts,vectors,label):
        """Wire each emitted pair into a stub with a real fallthrough path and a real trap block, then run it."""
        save=lambda:['mov [rdi+%d], %s'%(8*k,NAMES[r])for k,r in enumerate(SAFE)]
        stub=['bits 64','section .text']
        for i,(text,vector) in enumerate(zip(texts,vectors)):
            stub+=['global v%d'%i,'v%d:'%i]+['mov %s, [rdi+%d]'%(NAMES[r],8*k)for k,r in enumerate(SAFE)]
            stub+=text.decode('ascii').rstrip('\n').split('\n')
            stub+=save()+['mov qword [rdi+64], 0','ret']                    # fallthrough: no overflow
            stub+=['__dong_b%d:'%vector[6]]+save()+['mov qword [rdi+64], 1','ret']   # upstream-owned trap block
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        self.command([self.nasm,'-f',self.native,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.o'),self.work/(label+'.stubs.asm')],label+'-stubs')
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%i for i in range(len(texts))))
        main=main.replace('%TABLE%',','.join('v%d'%i for i in range(len(texts))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.o'),'-o',exe],label+'-native-link')
        payload=bytearray();expected=[]
        for op,sg,d,s,a,b,_ in vectors:
            state=[0x1111111111111111*(j+1)for j in range(8)]
            state[SAFE.index(s)]=b;state[SAFE.index(d)]=a
            if d==s:b=a
            payload.extend(struct.pack('<8Q',*state))
            value,trapped=semantics(op,sg,a,b)
            want=list(state);want[SAFE.index(d)]=value;expected.append((want,int(trapped)))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        for k,(want,trapped) in enumerate(expected):
            got=list(struct.unpack_from('<9Q',run.stdout,72*k))
            self.assertEqual(got[8],trapped,(label,k,'native trap path',vectors[k]))
            self.assertEqual(got[:8],want,(label,k,'native value',vectors[k]))

    def vector_texts(self,exe,vectors,label):
        return self.emit(exe,[(op,sg,d,s,blk,64,OK)for op,sg,d,s,_,_,blk in vectors],label)

    def test_exact_text_and_capacity_for_all_registers(self):
        cases=[]
        for op in (0,1):
            for sg in (0,1):
                for d in range(16):
                    for shift,block in ((0,0),(1,9),(7,10),(13,2**64-2)):
                        s=(d+shift)%16;n=len(expected_text(op,sg,d,s,block))
                        cases+=[(op,sg,d,s,block,n,OK),(op,sg,d,s,block,n+9,OK),(op,sg,d,s,block,n-1,CAPACITY)]
        cases+=[(0,1,0,0,7,0,CAPACITY),(2,1,0,0,7,64,INVALID),(0,0,16,0,7,64,INVALID),(0,0,0,16,7,64,INVALID),
                (0,1,0,1,NONE,64,INVALID),(1,0,1,2,NONE,0,INVALID)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for case,text in zip(cases,texts):
                if case[6]==OK:self.assertEqual(text,expected_text(*case[:5]),(mode,case))
        self.records.append(dict(test='exact-text-capacity',cases=len(cases),preflights_per_native=13,modes=2,passed=True))

    def test_all_sixteen_registers_assemble_in_both_formats(self):
        cases=[(op,sg,d,(d+shift)%16,d*16+shift,64,OK)for op in (0,1)for sg in (0,1)for d in range(16)for shift in (0,1,7,13)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'asm-'+mode)
            labels=sorted({c[4]for c in cases})
            source=self.work/('all-registers-'+mode+'.asm')
            source.write_bytes(b'bits 64\nsection .text\n'+b''.join(texts)+b''.join(b'__dong_b%d:\nret\n'%l for l in labels))
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('all-registers-%s.%s.o'%(mode,fmt)),source],'all-registers-%s-%s'%(mode,fmt))
        self.records.append(dict(test='all-registers-assemble',pairs=len(cases),formats=['elf64','win64'],modes=2,passed=True))

    def test_native_trap_and_fallthrough_paths(self):
        trapped=sum(semantics(op,sg,a,a if d==s else b)[1]for op,sg,d,s,a,b,_ in VECTORS)
        self.assertTrue(8<=trapped<=16,trapped)
        for mode,exe in self.executables.items():
            self.native_run(self.vector_texts(exe,VECTORS,'vectors-'+mode),VECTORS,'native-'+mode)
        self.records.append(dict(test='native-trap-fallthrough',vectors_per_mode=len(VECTORS),trapping=trapped,registers=[NAMES[r]for r in SAFE],modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        native_controls=[
            # Signed overflow tested with the carry flag.
            ('bad-signed-predicate','if signed{at=copy(buffer,at,"jo __dong_b");}','if signed{at=copy(buffer,at,"jc __dong_b");}',[v for v in VECTORS if v[1]==1]),
            # Unsigned carry/borrow branch inverted.
            ('bad-unsigned-inverted','else{at=copy(buffer,at,"jc __dong_b");}','else{at=copy(buffer,at,"jnc __dong_b");}',[v for v in VECTORS if v[1]==0]),
        ]
        for name,old,new,vectors in native_controls:
            self.assertEqual(source.count(old),1,name)
            for mode,exe in self.executables.items():          # the same fixture passes on the real source first
                self.native_run(self.vector_texts(exe,vectors,name+'-good-'+mode),vectors,name+'-good-'+mode)
            for mode,exe in self.build_all(name,source.replace(old,new,1)).items():
                texts=self.vector_texts(exe,vectors,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'native trap path'):self.native_run(texts,vectors,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by='native trap path'))
        old='if at>out.len{return CAPACITY;}';self.assertEqual(source.count(old),1)
        new='var j:usize=0;while j<at&&j<out.len{out[j]=buffer[j];j+=1;}if at>out.len{return CAPACITY;}'
        case=[(0,1,0,1,77,12,CAPACITY)]
        for mode,exe in self.executables.items():self.emit(exe,case,'bad-early-out-good-'+mode)
        for mode,exe in self.build_all('bad-early-out',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,case,'bad-early-out-'+mode)
        self.records.append(dict(test='bad-early-out',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))


if __name__=='__main__':unittest.main()
