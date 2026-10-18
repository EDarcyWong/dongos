"""Actual Dong NASM wrapping-binary emitter: exact text, dual-format assembly, and native execution."""
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

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_integer_binary.dg'
OK,INVALID,CAPACITY=0,1,2
M64=2**64-1
NAMES=['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi']+['r%d'%i for i in range(8,16)]
MNEMONICS=['add','sub','and','or','xor','imul']
SAFE=[0,1,2,6,8,9,10,11]          # caller-saved registers the native stubs may load/clobber (rdi holds the state pointer)
WRAPPER='''module probe.binary_export;
import bootstrap.nasm_integer_binary as b;
export("dong_binary_emit") pub unsafe fn emit(operation:u64,destination:u64,source:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return b.emit(operation,destination,source,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_binary_emit(uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
   case 0:s=dong_binary_emit(0,0,1,o,32,NULL);break;                                   /* written NULL */
   case 1:s=dong_binary_emit(0,0,1,o,32,(uint64_t*)(arena+257));break;                 /* written odd */
   case 2:s=dong_binary_emit(0,0,1,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break; /* written end overflow, empty out */
   case 3:s=dong_binary_emit(0,0,1,(uint8_t*)(uintptr_t)(UINT64_MAX-3),8,w);break;     /* out end overflow */
   case 4:s=dong_binary_emit(0,0,1,NULL,32,w);break;                                   /* NULL non-empty out */
   case 5:s=dong_binary_emit(0,0,1,o,32,(uint64_t*)o);break;                           /* written on out prefix */
   case 6:s=dong_binary_emit(0,0,1,o,64,(uint64_t*)(o+56));break;                      /* written in out's unused tail */
   case 7:s=dong_binary_emit(6,0,1,NULL,0,w);break;                                    /* bad operation, capacity 0 */
   case 8:s=dong_binary_emit(UINT64_MAX,0,1,o,32,w);break;
   case 9:s=dong_binary_emit(0,16,1,NULL,0,w);break;                                   /* bad destination, capacity 0 */
   case 10:s=dong_binary_emit(0,0,16,o,32,w);break;                                    /* bad source */
   default:s=dong_binary_emit(5,UINT64_MAX,UINT64_MAX,o,1,w);break;
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
  uint64_t s=dong_binary_emit(h[0],h[1],h[2],cap?out+32:NULL,cap,written);
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


def expected_line(op,d,s):
    return ('%s %s, %s\n'%(MNEMONICS[op],NAMES[d],NAMES[s])).encode()


def semantics(op,a,b):
    """Independent low-64-bit reference."""
    return [(a+b),(a-b),(a&b),(a|b),(a^b),(a*b)][op]&M64


# At most 24 native vectors: every operation, dest==source, 0/1/all-ones/top bit and high multiplication.
TOP,ONES=1<<63,M64
VECTORS=[(0,0,1,ONES,1),(0,8,9,TOP,TOP),(0,2,2,TOP|5,TOP|5),(0,10,11,0x7fffffffffffffff,1),
         (1,1,2,0,1),(1,9,8,TOP,1),(1,6,6,12345,12345),(1,11,0,1,ONES),
         (2,2,6,0xf0f0f0f0f0f0f0f0,0x0ff00ff00ff00ff0),(2,8,8,ONES,ONES),(2,0,10,TOP,TOP|1),(2,11,9,0,ONES),
         (3,6,0,0,0),(3,9,10,TOP,1),(3,1,1,0x1234,0x1234),(3,10,2,0xaaaa,0x5555),
         (4,8,1,ONES,ONES),(4,0,0,TOP|7,TOP|7),(4,10,6,TOP,1),(4,2,11,0x123456789abcdef0,ONES),
         (5,0,1,0xffffffff00000001,0x100000001),(5,9,9,TOP|3,TOP|3),(5,2,8,ONES,ONES),(5,11,10,0x7fffffffffffffff,3)]


class NasmIntegerBinaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C23'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
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
        (root/'bootstrap/nasm_integer_binary.dg').write_text(text,encoding='utf-8')
        (root/'probe/binary_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/binary_export.dg',roots=[root],mode=mode)
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
        """cases: (op,d,s,cap,expected_status). Returns emitted texts (None on failure); guards asserted per call."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for op,d,s,cap,_ in cases:payload.extend(struct.pack('<4Q',op,d,s,cap))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],12)
        offset=8;texts=[]
        for index,(op,d,s,cap,status) in enumerate(cases):
            got,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            text=run.stdout[offset:offset+written];offset+=written
            # Storage verdict first, before this or the next result is used.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(got,status,(label,index,'status'))
            texts.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return texts

    def native_run(self,lines,vectors,label):
        """Assemble the emitted lines into SysV stubs, run them, and compare every safe register."""
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
        for k,(op,d,s,a,b) in enumerate(vectors):
            state=[0x1111111111111111*(j+1)for j in range(8)]               # distinct sentinels
            state[SAFE.index(s)]=b;state[SAFE.index(d)]=a                    # dest==source: dest value wins
            if d==s:b=a
            payload.extend(struct.pack('<8Q',*state))
            want=list(state);want[SAFE.index(d)]=semantics(op,a,b);expected.append(want)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        for k,want in enumerate(expected):
            got=list(struct.unpack_from('<8Q',run.stdout,64*k))
            self.assertEqual(got,want,(label,k,'native',vectors[k]))
        return len(vectors)

    def test_exact_text_and_capacity_for_all_registers(self):
        cases=[]
        for op in range(6):
            for d in range(16):
                for shift in (0,1,5,11):
                    s=(d+shift)%16;n=len(expected_line(op,d,s))
                    cases+=[(op,d,s,n,OK),(op,d,s,n+9,OK),(op,d,s,n-1,CAPACITY)]
        cases+=[(0,0,0,0,CAPACITY),(6,0,0,64,INVALID),(0,16,0,64,INVALID),(0,0,16,64,INVALID),(7,17,17,0,INVALID)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for (op,d,s,cap,status),text in zip(cases,texts):
                if status==OK:self.assertEqual(text,expected_line(op,d,s),(mode,op,d,s))
        self.records.append(dict(test='exact-text-capacity',cases=len(cases),preflights_per_native=12,modes=2,passed=True))

    def test_all_sixteen_registers_assemble_in_both_formats(self):
        cases=[(op,d,(d+shift)%16,32,OK)for op in range(6)for d in range(16)for shift in (0,1,5,11)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'asm-'+mode)
            source=self.work/('all-registers-'+mode+'.asm')
            source.write_bytes(b'bits 64\nsection .text\n'+b''.join(texts))
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('all-registers-%s.%s.o'%(mode,fmt)),source],'all-registers-%s-%s'%(mode,fmt))
        self.records.append(dict(test='all-registers-assemble',lines=len(cases),formats=['elf64','win64'],modes=2,passed=True))

    def test_native_execution_matches_low_64_bits(self):
        for mode,exe in self.executables.items():
            texts=self.emit(exe,[(op,d,s,32,OK)for op,d,s,_,_ in VECTORS],'vectors-'+mode)
            self.native_run(texts,VECTORS,'native-'+mode)
        self.records.append(dict(test='native-semantics',vectors_per_mode=len(VECTORS),registers=[NAMES[r]for r in SAFE],modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        native_controls=[
            # sub emitted with swapped operands: writes the source register and computes source-dest.
            ('bad-sub-direction','at=copy(buffer,at+1,register(destination));buffer[at]=44;buffer[at+1]=32;\n at=copy(buffer,at+2,register(source));',
             'var first=destination;var second=source;if operation==SUB{first=source;second=destination;}\n at=copy(buffer,at+1,register(first));buffer[at]=44;buffer[at+1]=32;\n at=copy(buffer,at+2,register(second));',
             [v for v in VECTORS if v[0]==1 and v[1]!=v[2]]),
            ('bad-imul-as-add','return "imul";','return "add";',[v for v in VECTORS if v[0]==5]),
        ]
        for name,old,new,vectors in native_controls:
            self.assertEqual(source.count(old),1,name)
            for mode,exe in self.executables.items():          # the same fixture passes on the real source first
                self.native_run(self.emit(exe,[(op,d,s,32,OK)for op,d,s,_,_ in vectors],name+'-good-'+mode),vectors,name+'-good-'+mode)
            for mode,exe in self.build_all(name,source.replace(old,new,1)).items():
                texts=self.emit(exe,[(op,d,s,32,OK)for op,d,s,_,_ in vectors],name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'native'):self.native_run(texts,vectors,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by='native register result'))
        # Capacity failure that writes the output first: rejected by the full-buffer guard check.
        old='if at>out.len{return CAPACITY;}';self.assertEqual(source.count(old),1)
        new='var j:usize=0;while j<at&&j<out.len{out[j]=buffer[j];j+=1;}if at>out.len{return CAPACITY;}'
        case=[(0,0,1,4,CAPACITY)]
        for mode,exe in self.executables.items():self.emit(exe,case,'bad-early-out-good-'+mode)
        for mode,exe in self.build_all('bad-early-out',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,case,'bad-early-out-'+mode)
        self.records.append(dict(test='bad-early-out',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))


if __name__=='__main__':unittest.main()
