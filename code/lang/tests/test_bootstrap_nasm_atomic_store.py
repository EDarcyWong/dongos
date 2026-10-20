"""Actual Dong NASM SC atomic store emit via memory-XCHG (32/64)."""
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


SOURCE=ROOT/'lang/bootstrap/nasm_atomic_store.dg'
DOC=ROOT/'lang/bootstrap/nasm_atomic_store.md'
OK,INVALID,CAPACITY=0,1,2
NONE=(1<<64)-1
W32,W64=32,64
TEXT32=b'mov eax, esi\nxchg dword [rdi], eax\n'
TEXT64=b'mov rax, rsi\nxchg qword [rdi], rax\n'
WRAPPER='''module probe.nasm_atomic_store_export;
import bootstrap.nasm_atomic_store as m;
export("dong_atomic_store_emit") pub unsafe fn emit(
 width:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(width,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_atomic_store_emit(uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 _Alignas(16) static uint8_t arena[4096];
 _Alignas(16) static uint8_t saved[4096];
 const unsigned total=14;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  if(i==5)memcpy(o+80,"mov eax, esi\nxchg dword [rdi], eax\n",35);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_atomic_store_emit(32,o,128,NULL);break;
   case 1:st=dong_atomic_store_emit(32,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_atomic_store_emit(32,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_atomic_store_emit(32,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_atomic_store_emit(32,NULL,128,w);break;
   case 5:st=dong_atomic_store_emit(32,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_atomic_store_emit(32,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_atomic_store_emit(32,o,0,(uint64_t*)(uintptr_t)1);break;
   case 8:st=dong_atomic_store_emit(32,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=dong_atomic_store_emit(0,o,128,w);break;
   case 10:st=dong_atomic_store_emit(16,o,128,w);break;
   case 11:st=dong_atomic_store_emit(128,o,128,w);break;
   case 12:st=dong_atomic_store_emit(0,o,0,w);break;
   default:st=dong_atomic_store_emit(7,o,0,w);break;
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
  uint64_t h[3];read_exact(h,sizeof(h));
  uint64_t width=h[0],cap=h[1],nout=h[2];
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);_Alignas(8) uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_atomic_store_emit(width,o,cap,written);
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
  /* in: [0]cell_init [1]new [2]rcx [3]rdx [4]r8 [5]r9 [6]flags_in
     meta outs (separate from object): [7]flags [8]rax [9]rdi [10]rsi
     [11]rcx [12]rdx [13]r8 [14]r9
     object (never overwritten by meta): [16]lo_guard [17]cell [18]hi_guard
     then expected_rdi word */
  uint64_t state[24];read_exact(state,56);
  memset(state+7,0xa5,sizeof(state)-56);
  table[i](state);
  uint64_t expected_rdi=(uint64_t)(uintptr_t)&state[17];
  if(fwrite(state,8,19,stdout)!=19)exit(92);
  if(fwrite(&expected_rdi,8,1,stdout)!=1)exit(92);
 }return 0;
}
'''


def expected(width):
    return TEXT32 if width==W32 else TEXT64


def need_total(width):
    return len(expected(width))


def item(width,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        if width not in (W32,W64):status=INVALID
        else:
            need=need_total(width)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(width) if status==OK else 64
    text=expected(width) if status==OK else None
    return dict(width=width,cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<3Q',c['width'],c['cap'],c.get('nout',0))


# (width, old, new) — both widths together <=16 per mode (not 16 each).
def make_vectors(width):
    mask=(1<<width)-1
    return [
        (width,0,0),
        (width,0,mask),
        (width,mask,0),
        (width,mask,mask),
        (width,0x1111222233334444&NONE,0xAAAABBBBCCCCDDDD&NONE),  # hi/lo pattern
        (width,0x00000000FFFFFFFF,0xFFFFFFFF00000000&NONE),  # RSI high32 nonzero
        (width,0xDEADBEEF,0xDEADBEEF),  # equal
        (width,1,2),  # different
    ]


VECTORS32=make_vectors(W32)
VECTORS64=make_vectors(W64)
assert len(VECTORS32)+len(VECTORS64)<=16
# Adjacent upper-32 guard inside the 8-byte cell for dword stores.
HIGH_GUARD=0xA5A5A5A5
# Full adjacent qword guards around the target object (both widths).
SIDE_GUARD=0xA5A5A5A5A5A5A5A5
# Non-trivial arith flags seed: CF=1 (plus IF / reserved bit1).
FLAGS_IN=0x203
ARITH_FLAGS=0x8D5


class NasmAtomicStoreTests(unittest.TestCase):
    PREFLIGHTS=14

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_atomic_store requires NASM/GCC')
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.work=WORKS/'build/test/bootstrap-nasm-atomic-store'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_atomic_store.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_atomic_store_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_atomic_store_export.dg',roots=roots,mode=mode)
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
        for width in (W32,W64):
            need=need_total(width)
            self.assertEqual(need,35)
            cases+=[item(width),
                    item(width,cap=need),
                    item(width,cap=need+3),
                    item(width,cap=need-1),
                    item(width,cap=0,status=CAPACITY)]
        cases+=[item(0,cap=64,status=INVALID),
                item(16,cap=64,status=INVALID),
                item(8,cap=64,status=INVALID),
                item(128,cap=64,status=INVALID),
                item(NONE,cap=64,status=INVALID),
                item(W32,nout=1,cap=64,status=INVALID),
                item(0,nout=0,cap=0,status=INVALID),
                item(7,nout=0,cap=0,status=INVALID),
                item(128,nout=0,cap=0,status=INVALID)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_dong_assemble_encoding_and_native_store(self):
        samples=[W32,W64]
        cases=[item(w)for w in samples]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,(width,out) in enumerate(zip(samples,outs)):
                self.assertIsNotNone(out,(mode,index))
                body=b'bits 64\nsection .text\nglobal t\nt:\n'+out+b'ret\n'
                for fmt in ('elf64','win64'):
                    asm=asm_dir/f'{mode}-{width}-{fmt}.asm'
                    obj=asm_dir/f'{mode}-{width}-{fmt}.o'
                    asm.write_bytes(body)
                    r=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                     capture_output=True,timeout=30)
                    self.assertEqual(r.returncode,0,(mode,width,fmt,r.stderr,out))
                    assembled+=1
                self._assert_xchg_encoding(mode,width,out)
        # Native vectors
        for width,vectors in ((W32,VECTORS32),(W64,VECTORS64)):
            texts={mode:self.run_both([item(width)],f'native-text-{width}')[mode][0]
                   for mode in self.executables}
            for mode in self.executables:
                self._native_batch(mode,width,texts[mode],vectors)
        total=len(VECTORS32)+len(VECTORS64)
        self.assertLessEqual(total,16,(total,'vectors per mode'))
        self.records.append(dict(test='dong-assemble-encoding-native',assemble_samples=len(samples),
                                 assembled=assembled,vectors32=len(VECTORS32),vectors64=len(VECTORS64),
                                 vectors_total=total,encoding_checked=True,modes=2,formats=2,passed=True))

    def _assert_xchg_encoding(self,mode,width,text:bytes):
        """Assemble emitted text alone and confirm memory-XCHG width bytes, no LOCK."""
        body=b'bits 64\nsection .text\nglobal t\nt:\n'+text+b'ret\n'
        d=self.work/'encode';d.mkdir(exist_ok=True)
        asm=d/f'{mode}-{width}.asm';obj=d/f'{mode}-{width}.bin'
        asm.write_bytes(body)
        # Flat binary via nasm -f bin for exact instruction bytes.
        r=subprocess.run([str(self.nasm),'-f','bin','-o',str(obj),str(asm)],
                         capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,(r.stderr,body))
        raw=obj.read_bytes()
        # Exact encodings (no LOCK): mov + memory-XCHG + ret.
        # Note 89 F0 87 07 contains the byte run F0 87 07 — that is NOT a LOCK prefix.
        if width==W32:
            self.assertEqual(raw,b'\x89\xf0\x87\x07\xc3',
                             (mode,width,'dword mov/xchg encoding',raw.hex()))
        else:
            self.assertEqual(raw,b'\x48\x89\xf0\x48\x87\x07\xc3',
                             (mode,width,'qword mov/xchg encoding',raw.hex()))
        ndisasm=shutil.which('ndisasm')
        if ndisasm:
            dump=subprocess.run([ndisasm,'-b','64',str(obj)],capture_output=True,text=True,timeout=30)
            (d/f'{mode}-{width}.ndisasm').write_text(dump.stdout,encoding='utf-8')
            low=dump.stdout.lower()
            self.assertIn('xchg',low,(mode,width,dump.stdout))
            self.assertNotIn('lock',low,(mode,width,dump.stdout))

    def _native_batch(self,mode,width,text:bytes,vectors):
        stub=['bits 64','section .text']
        for k,(w,old,new) in enumerate(vectors):
            self.assertEqual(w,width)
            # Object at [16]=lo,[17]=cell,[18]=hi; meta outs at [7..14] never alias object.
            stub+=[
                'global v%d'%k,'v%d:'%k,
                'mov r11, rdi',
                'mov rax, 0xa5a5a5a5a5a5a5a5',
                'mov [r11+128], rax',
                'mov [r11+144], rax',
                'mov rax, [r11+0]',
                'mov [r11+136], rax',
                'lea rdi, [r11+136]',
                'mov rsi, [r11+8]',
                'mov rcx, [r11+16]','mov rdx, [r11+24]',
                'mov r8, [r11+32]','mov r9, [r11+40]',
                'push qword [r11+48]','popfq',
            ]
            stub+=text.decode('ascii').rstrip('\n').split('\n')
            stub+=[
                'pushfq','pop qword [r11+56]',
                'mov [r11+64], rax',
                'mov [r11+72], rdi','mov [r11+80], rsi',
                'mov [r11+88], rcx','mov [r11+96], rdx',
                'mov [r11+104], r8','mov [r11+112], r9',
                'ret',
            ]
        label=f'{mode}-w{width}-native'
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),
                          '-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],
                         label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(vectors))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(vectors))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',
                      self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],
                     label+'-native-link')
        rcx_s,rdx_s,r8_s,r9_s=0x2222222222222222,0x3333333333333333,0x4444444444444444,0x5555555555555555
        payload=bytearray()
        mask=(1<<width)-1
        for w,old,new in vectors:
            cell_init=((HIGH_GUARD<<32)|(old&mask)) if width==W32 else (old&NONE)
            payload.extend(struct.pack('<7Q',cell_init,new&NONE,rcx_s,rdx_s,r8_s,r9_s,FLAGS_IN))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        stride=20*8  # 19 state words + expected_rdi
        for k,(w,old,new) in enumerate(vectors):
            words=list(struct.unpack_from('<20Q',run.stdout,stride*k))
            # words[0..6] input leftovers; [7]=flags [8]=rax [9]=rdi [10]=rsi
            # [11]=rcx [12]=rdx [13]=r8 [14]=r9; [16]=lo [17]=cell [18]=hi; [19]=expected_rdi
            flags_out=words[7]
            rax_out,rdi_out,rsi_out=words[8],words[9],words[10]
            rcx_out,rdx_out,r8_out,r9_out=words[11],words[12],words[13],words[14]
            lo_guard,cell,hi_guard=words[16],words[17],words[18]
            expected_rdi=words[19]
            want_mem=new&mask
            want_rax=old&mask
            self.assertEqual(rdi_out,expected_rdi,(label,k,'rdi equals target',hex(rdi_out),hex(expected_rdi)))
            self.assertEqual(lo_guard,SIDE_GUARD,(label,k,'lo guard',hex(lo_guard)))
            self.assertEqual(hi_guard,SIDE_GUARD,(label,k,'hi guard',hex(hi_guard)))
            self.assertEqual(cell&mask,want_mem,(label,k,'mem',vectors[k],hex(cell)))
            if width==W32:
                self.assertEqual((cell>>32)&0xFFFFFFFF,HIGH_GUARD,
                                 (label,k,'adjacent high dword guard',hex(cell)))
            self.assertEqual(rax_out&mask,want_rax,(label,k,'rax old',vectors[k],hex(rax_out)))
            if width==W32:
                self.assertEqual(rax_out>>32,0,(label,k,'rax zero-extend',hex(rax_out)))
            self.assertEqual(rsi_out,new&NONE,(label,k,'rsi preserved',hex(rsi_out)))
            self.assertEqual(rcx_out,rcx_s,(label,k,'rcx preserved'))
            self.assertEqual(rdx_out,rdx_s,(label,k,'rdx preserved'))
            self.assertEqual(r8_out,r8_s,(label,k,'r8 preserved'))
            self.assertEqual(r9_out,r9_s,(label,k,'r9 preserved'))
            self.assertEqual(flags_out&ARITH_FLAGS,FLAGS_IN&ARITH_FLAGS,
                             (label,k,'arith flags',hex(flags_out),hex(FLAGS_IN)))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,(name,source.count(old)))
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_atomic_store.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'wrapper'/'probe'/'nasm_atomic_store_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def _emit_text_from_exe(self,exe,width):
        c=item(width,cap=64)
        payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(c))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        self.assertEqual(run.returncode,0,run.stderr)
        st,g,w=struct.unpack_from('<3Q',run.stdout,8)
        text=run.stdout[32:32+64][:w]
        self.assertEqual(st,0);self.assertEqual(g,1)
        return text

    def test_actual_compiled_wrong_sources_are_rejected(self):
        mov32_old=' at=copy(buffer,0,"mov eax, esi\\n");'
        mov32_new=' at=copy(buffer,0,"mov eax, 0\\n");'
        mov64_old=' at=copy(buffer,0,"mov rax, rsi\\n");'
        mov64_new=' at=copy(buffer,0,"mov rax, 0\\n");'
        xchg64_old=' at=copy(buffer,at,"xchg qword [rdi], rax\\n");'
        xchg64_rdi=' at=copy(buffer,at,"xchg qword [rdi], rax\\n");\n  at=copy(buffer,at,"mov rdi, 0\\n");'
        xchg64_guard=' at=copy(buffer,at,"xchg qword [rdi], rax\\n");\n  at=copy(buffer,at,"mov qword [rdi + 8], 0\\n");'
        xchg64_clc=' at=copy(buffer,at,"xchg qword [rdi], rax\\n");\n  at=copy(buffer,at,"clc\\n");'
        early_old=' if at>out.len{return CAPACITY;}'
        early_new=' *written=at;if at>out.len{return CAPACITY;}'
        short=item(W32,cap=5)
        # Same native fixture for good/bad sides of mov-zero and selective clobber cases.
        MOV_VEC=[(W32,0x11,0x99)]
        MOV64_VEC=[(W64,0x11,0x99)]
        controls=[
            ('bad-mov32-zero',mov32_old,mov32_new,'mem',W32,MOV_VEC),
            ('bad-mov64-zero',mov64_old,mov64_new,'mem',W64,MOV64_VEC),
            ('bad-clobber-rdi',xchg64_old,xchg64_rdi,'rdi equals target',W64,MOV64_VEC),
            ('bad-clobber-hi-guard',xchg64_old,xchg64_guard,'hi guard',W64,MOV64_VEC),
            ('bad-clc',xchg64_old,xchg64_clc,'arith flags',W64,MOV64_VEC),
            ('bad-early-written',early_old,early_new,'atomic',W32,None),
        ]
        for name,old,new,kind,width,vec in controls:
            if kind=='atomic':
                self.run_both([short],name+'-good')
            else:
                # Good side: actual formal Dong text, identical inputs to the bad side.
                for mode,exe in self.executables.items():
                    good_text=self._emit_text_from_exe(exe,width)
                    self.assertEqual(good_text,expected(width),(name,mode,'good text'))
                    self._native_batch(mode+'-good-'+name,width,good_text,vec)
            for mode,exe in self.bad_build(name,old,new).items():
                if kind=='atomic':
                    with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                        self.run_cases(exe,[short],name+'-'+mode)
                else:
                    text=self._emit_text_from_exe(exe,width)
                    self.assertNotEqual(text,expected(width),(name,mode,text))
                    with self.assertRaisesRegex(AssertionError,kind):
                        self._native_batch(mode+'-'+name,width,text,vec)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=kind))


if __name__=='__main__':unittest.main()
