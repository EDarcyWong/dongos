"""Actual Dong NASM fixed-register 64-bit checked multiply emit."""
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
    flags=list(_nasm_flags(nasm))
    if '-w-reloc-rel-dword' not in flags:
        flags.append('-w-reloc-rel-dword')
    return flags

SOURCE=WORKS/'cursor-works/src/bootstrap/nasm_checked_multiply.dg'
DOC=WORKS/'cursor-works/src/bootstrap/nasm_checked_multiply.md'
CR4=WORKS/'cursor-works/src/bootstrap/decimal_integer.dg'
if not CR4.is_file():
    CR4=ROOT/'lang/bootstrap/decimal_integer.dg'
OK,INVALID,CAPACITY=0,1,2
NONE=(1<<64)-1
TOP=1<<63
SMAX=TOP-1
FALL=111
TRAP=222
WRAPPER='''module probe.nasm_checked_multiply_export;
import bootstrap.nasm_checked_multiply as m;
export("dong_checked_mul_emit") pub unsafe fn emit(
 signed:bool,trap_block:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(signed,trap_block,slice_from_raw_parts(out,no),written);
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
#endif
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI dong_checked_mul_emit(uint8_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 _Alignas(16) static uint8_t arena[4096];
 _Alignas(16) static uint8_t saved[4096];
 const unsigned total=12;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  if(i==5)memcpy(o+80,"mov rax, rdi\n",13);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_checked_mul_emit(1,0,o,128,NULL);break;
   case 1:st=dong_checked_mul_emit(1,0,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_checked_mul_emit(1,0,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_checked_mul_emit(1,0,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_checked_mul_emit(1,0,NULL,128,w);break;
   case 5:st=dong_checked_mul_emit(1,0,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_checked_mul_emit(1,0,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_checked_mul_emit(1,0,o,0,(uint64_t*)(uintptr_t)1);break;
   case 8:st=dong_checked_mul_emit(1,0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=dong_checked_mul_emit(1,UINT64_MAX,o,128,w);break;
   case 10:st=dong_checked_mul_emit(0,UINT64_MAX,o,128,w);break;
   default:st=dong_checked_mul_emit(1,UINT64_MAX,o,0,w);break;
  }
  if(st!=1||memcmp(saved,arena,sizeof(arena))){
   fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)st);exit(93);
  }
 }
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[4];read_exact(h,sizeof(h));
  uint64_t signed_f=h[0],trap=h[1],cap=h[2],nout=h[3];
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);_Alignas(8) uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_checked_mul_emit((uint8_t)signed_f,trap,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
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
  /* [0]a [1]b [2]rdx_in [3]rcx [4]r8 [5]r9 — then out overwrites with results */
  uint64_t state[10];read_exact(state,48);
  state[6]=state[7]=state[8]=state[9]=0xa5a5a5a5a5a5a5a5ull;
  table[i](state);
  if(fwrite(state,8,8,stdout)!=8)exit(92);
 }return 0;
}
'''


def i64(v):
    v&=NONE
    return v- (1<<64) if v>=TOP else v


def py_mul(signed,a,b):
    a&=NONE;b&=NONE
    if signed:
        prod=i64(a)*i64(b)
        overflow=prod< -(1<<63) or prod>=(1<<63)
        low=prod&(NONE)
        return overflow,low,None
    prod=a*b
    overflow=prod>=(1<<64)
    return overflow,prod&NONE,(prod>>64)&NONE


def expected(signed,trap):
    if signed:
        return b'mov rax, rdi\nimul rax, rsi\njo __dong_b'+str(trap).encode()+b'\n'
    return b'mov rax, rdi\nmul rsi\njc __dong_b'+str(trap).encode()+b'\n'


def need_total(signed,trap):
    return len(expected(signed,trap))


def item(signed,trap,cap=None,status=None,nout=0):
    sg=1 if signed else 0
    if nout and status is None:status=INVALID
    if status is None:
        if trap==NONE:status=INVALID
        else:
            need=need_total(signed,trap)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(signed,trap) if status==OK else 64
    text=expected(signed,trap) if status==OK else None
    return dict(signed=sg,trap=trap,cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<4Q',c['signed'],c['trap'],c['cap'],c.get('nout',0))


# (signed, a, b, trap) — combined native main vectors <=24 (R2).
SIGNED_VECTORS=[
    (1,0,0,10),(1,1,1,12),(1,NONE,NONE,13),                      # 0/1/-1
    (1,TOP,0,14),(1,TOP,1,15),(1,TOP,NONE,16),                   # MIN*0/1 OK; MIN*-1 overflow
    (1,SMAX,1,17),(1,SMAX,2,18),                                 # MAX*1 OK; MAX*2 overflow
    (1,TOP>>1,2,19),(1,(TOP>>1)+1,2,20),                         # adjacent overflow boundary
    (1,3,5,21),(1,SMAX,SMAX,25),                                 # safe product; MAX*MAX overflow
]
UNSIGNED_VECTORS=[
    (0,0,0,40),(0,1,1,42),(0,NONE,0,53),(0,NONE,1,43),           # 0/1/MAX
    (0,NONE,2,44),(0,TOP,1,46),(0,TOP,2,45),                     # adjacent unsigned overflow
    (0,1<<32,1<<32,48),(0,(1<<32)-1,(1<<32)-1,49),               # high-product cases
    (0,NONE,NONE,50),(0,3,5,52),(0,1<<63,2,58),                  # MAX*MAX; 2^63*2 overflow
]
assert len(SIGNED_VECTORS)+len(UNSIGNED_VECTORS)<=24
assert len(SIGNED_VECTORS)<=24 and len(UNSIGNED_VECTORS)<=24


class NasmCheckedMultiplyTests(unittest.TestCase):
    PREFLIGHTS=12

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_checked_multiply requires NASM/GCC')
        cls.work=WORKS/'cursor-works/build/CR22'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_checked_multiply.dg')
        shutil.copy2(CR4,cls.src_root/'bootstrap'/'decimal_integer.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.native='win64'if os.name=='nt'else'elf64'
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__),CR4]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_checked_multiply_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_checked_multiply_export.dg',roots=roots,mode=mode)
        asm=cls.work/(name+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
        obj=cls.work/(name+'.o');exe=cls.work/(name+('.exe'if os.name=='nt'else''))
        for fmt in ('elf64','win64'):
            output=obj if fmt==cls.native else cls.work/(name+'.'+fmt+'.o')
            cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',output,asm],name+'-'+fmt)
        cls.command([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',cls.work/'probe.c',obj,'-o',exe],name+'-link')
        return exe

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        files={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for p in cls.work.rglob('*')if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,artifact_sha256=files,
            records=cls.records,L3_selfhost_complete=False,OS_VM_built=False),indent=2)+'\n',encoding='utf-8')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:payload.extend(pack_case(c))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=180)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr.decode('utf-8','replace') if run.stderr else '')
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,self.PREFLIGHTS)
        offset=8;outs=[]
        for index,c in enumerate(cases):
            status,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            out=run.stdout[offset:offset+c['cap']];offset+=c['cap']
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status',c))
            if not status:
                self.assertEqual(written,len(c['text']),(label,index,'written'))
                self.assertEqual(out[:written],c['text'],(label,index,'output'))
            outs.append(out[:written] if not status else None)
        self.assertEqual(offset,len(run.stdout))
        return outs

    def run_both(self,cases,label):
        return {mode:self.run_cases(exe,cases,label+'-'+mode)for mode,exe in self.executables.items()}

    def test_format_boundaries_and_capacity(self):
        cases=[]
        for signed in (True,False):
            for trap in (0,1,42,TOP,NONE-1):
                need=need_total(signed,trap)
                cases+=[item(signed,trap),
                        item(signed,trap,cap=need+3),
                        item(signed,trap,cap=max(0,need-1)),
                        item(signed,trap,cap=need)]  # exact capacity
        cases+=[item(True,NONE,cap=64,status=INVALID),
                item(False,NONE,cap=64,status=INVALID),
                item(True,0,nout=1,cap=64,status=INVALID),
                item(True,NONE,nout=0,cap=0,status=INVALID),
                item(True,0,cap=0,status=CAPACITY)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_dong_assemble_and_native_multiply(self):
        samples=[(sg,t)for sg in (True,False)for t in (0,1,42,TOP,NONE-1,999)]
        cases=[item(sg,t)for sg,t in samples]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,((sg,t),out) in enumerate(zip(samples,outs)):
                self.assertIsNotNone(out,(mode,index))
                body=(b'bits 64\nsection .text\n'+out+
                      b'mov rax, 1\n ret\n__dong_b'+str(t).encode()+b':\n mov rax, 2\n ret\n')
                for fmt in ('elf64','win64'):
                    asm=asm_dir/f'{mode}-{index:03d}-{fmt}.asm'
                    obj=asm_dir/f'{mode}-{index:03d}-{fmt}.o'
                    asm.write_bytes(body)
                    r=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                     capture_output=True,timeout=30)
                    self.assertEqual(r.returncode,0,(mode,index,fmt,r.stderr,out))
                    assembled+=1
        vectors=SIGNED_VECTORS+UNSIGNED_VECTORS
        ncases=[item(bool(sg),t)for sg,_,_,t in vectors]
        nresults=self.run_both(ncases,'native-vecs')
        probed=0
        for mode,outs in nresults.items():
            self._native_batch(mode,outs,vectors)
            probed+=len(vectors)
        self.records.append(dict(test='dong-assemble-native-multiply',assemble_samples=len(samples),
                                 assembled=assembled,native_vectors=len(vectors),probed=probed,
                                 modes=2,formats=2,passed=True))

    def _native_batch(self,mode,texts,vectors):
        stub=['bits 64','section .text']
        defined=set()
        for k,(text,(sg,a,b,trap)) in enumerate(zip(texts,vectors)):
            stub+=[
                'global v%d'%k,'v%d:'%k,
                'mov r11, rdi',
                'mov rdi, [r11+0]','mov rsi, [r11+8]',
                'mov rdx, [r11+16]','mov rcx, [r11+24]',
                'mov r8, [r11+32]','mov r9, [r11+40]',
            ]
            stub+=text.decode('ascii').rstrip('\n').split('\n')
            stub+=[
                'mov [r11+48], rax','mov [r11+56], rdx',
                'mov [r11+0], rdi','mov [r11+8], rsi',
                'mov [r11+16], rcx','mov [r11+24], r8','mov [r11+32], r9',
                'mov rax, %d'%FALL,'mov [r11+40], rax','ret',
            ]
            if trap not in defined:
                defined.add(trap)
                stub+=[
                    '__dong_b%d:'%trap,
                    'mov [r11+48], rax','mov [r11+56], rdx',
                    'mov [r11+0], rdi','mov [r11+8], rsi',
                    'mov [r11+16], rcx','mov [r11+24], r8','mov [r11+32], r9',
                    'mov rax, %d'%TRAP,'mov [r11+40], rax','ret',
                ]
        label=mode+'-native'
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),
                          '-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],
                         label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(texts))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(texts))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',
                      self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],
                     label+'-native-link')
        rdx_sentinel=0x1111111111111111
        rcx_s,r8_s,r9_s=0x2222222222222222,0x3333333333333333,0x4444444444444444
        payload=bytearray()
        for sg,a,b,trap in vectors:
            payload.extend(struct.pack('<6Q',a&NONE,b&NONE,rdx_sentinel,rcx_s,r8_s,r9_s))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        for k,(sg,a,b,trap) in enumerate(vectors):
            got=list(struct.unpack_from('<8Q',run.stdout,64*k))
            # layout after stub: [0]rdi [1]rsi [2]rcx [3]r8 [4]r9 [5]marker [6]rax [7]rdx
            overflow,low,high=py_mul(bool(sg),a,b)
            want_marker=TRAP if overflow else FALL
            self.assertEqual(got[5],want_marker,(label,k,'route',vectors[k],overflow))
            self.assertEqual(got[6],low,(label,k,'rax low',vectors[k]))
            self.assertEqual(got[0],a&NONE,(label,k,'rdi preserved'))
            self.assertEqual(got[1],b&NONE,(label,k,'rsi preserved'))
            self.assertEqual(got[2],rcx_s,(label,k,'rcx preserved'))
            self.assertEqual(got[3],r8_s,(label,k,'r8 preserved'))
            self.assertEqual(got[4],r9_s,(label,k,'r9 preserved'))
            if sg:
                self.assertEqual(got[7],rdx_sentinel,(label,k,'signed rdx preserved'))
            else:
                self.assertEqual(got[7],high,(label,k,'unsigned rdx high'))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,(name,source.count(old)))
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_checked_multiply.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        shutil.copy2(CR4,src/'decimal_integer.dg')
        (root/'wrapper'/'probe'/'nasm_checked_multiply_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        jc_old=' at=copy(buffer,at,"jc __dong_b");'
        jc_new=' at=copy(buffer,at,"jnc __dong_b");'
        jo_old=' at=copy(buffer,at,"jo __dong_b");'
        jo_new=' at=copy(buffer,at,"jno __dong_b");'
        early_old=' if at>out.len{return CAPACITY;}'
        early_new=' *written=at;if at>out.len{return CAPACITY;}'
        short=item(True,0,cap=5)
        controls=[
            ('bad-jc-as-jnc',jc_old,jc_new,'native-u',False,NONE,2),       # unsigned overflow
            ('bad-jo-as-jno',jo_old,jo_new,'native-s',True,TOP,NONE),       # signed MIN*-1 overflow
            ('bad-early-written',early_old,early_new,'atomic',True,0,0),
        ]
        for name,old,new,kind,sg,a,b in controls:
            if kind=='atomic':
                self.run_both([short],name+'-good')
            else:
                self.run_both([item(sg,70)],name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                if kind=='atomic':
                    with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                        self.run_cases(exe,[short],name+'-'+mode)
                else:
                    # Inverted mnemonics are one byte longer; spare capacity; do not demand good text.
                    c=dict(signed=1 if sg else 0,trap=70,cap=64,nout=0,status=OK,text=None)
                    payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(c))
                    run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stderr)
                    st,g,w=struct.unpack_from('<3Q',run.stdout,8)
                    text=run.stdout[32:32+64][:w]
                    self.assertEqual(st,0);self.assertEqual(g,1)
                    self.assertNotEqual(text,expected(sg,70),(name,mode,text))
                    # Overflowing inputs: oracle expects TRAP; inverted branch falls through → rejected.
                    with self.assertRaisesRegex(AssertionError,r'route'):
                        self._native_batch(mode+'-'+name,[text],[(1 if sg else 0,a,b,70)])
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=kind))


if __name__=='__main__':unittest.main()
