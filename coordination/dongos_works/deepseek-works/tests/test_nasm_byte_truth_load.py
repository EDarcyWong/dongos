"""Actual Dong composed byte truth load (CR12 load + double CR16 zero-compare)."""
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

SOURCE=WORKS/'deepseek-works/src/bootstrap/nasm_byte_truth_load.dg'
DOC=WORKS/'deepseek-works/src/bootstrap/nasm_byte_truth_load.md'
LOAD=WORKS/'cursor-works/src/bootstrap/nasm_integer_memory_load.dg'
UNARY=WORKS/'cursor-works/src/bootstrap/nasm_integer_unary.dg'
MEMOP=WORKS/'cursor-works/src/bootstrap/nasm_memory_operand.dg'
def _dep(p):
    return p if p.is_file() else ROOT/'lang/bootstrap'/p.name
CR4=_dep(WORKS/'cursor-works/src/bootstrap/decimal_integer.dg')
OK,INVALID,CAPACITY=0,1,2
TOP=1<<63
NONE=(1<<64)-1
I32_MIN=-(1<<31)
I32_MAX=(1<<31)-1
REGS64=[b'rax',b'rcx',b'rdx',b'rbx',b'rsp',b'rbp',b'rsi',b'rdi',
        b'r8',b'r9',b'r10',b'r11',b'r12',b'r13',b'r14',b'r15']
# Only RAX and flags may change; every other GPR is captured and compared.
SAFE=set(range(16))-{4}
FALL=111
BAD_BASES={4,5}
WRAPPER='''module probe.nasm_byte_truth_load_export;
import bootstrap.nasm_byte_truth_load as m;
export("dong_byte_truth_load_emit") pub unsafe fn emit(
 base:u64,displacement:i64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(base,displacement,slice_from_raw_parts(out,no),written);
}}
'''
BAD_DROP='''module bootstrap.nasm_byte_truth_load_bad_drop;
import bootstrap.nasm_integer_memory_load as loadm;
import bootstrap.nasm_integer_unary as unarym;
pub const OK:u64=0;pub const INVALID:u64=1;pub const CAPACITY:u64=2;
const MAX:u64=0xffff_ffff_ffff_ffff;
const I32_MIN:i64=-2147483648;
const I32_MAX:i64=2147483647;
fn span(p:u64,n:u64)bool{return n==0||(p!=0&&n<=MAX-p);}
fn overlap(a:u64,n:u64,b:u64,m:u64)bool{return n!=0&&m!=0&&a<b+m&&b<a+n;}
fn copy(out:[]u8,at:usize,text:[]const u8)usize{
 var i:usize=0;while i<text.len{out[at+i]=text[i];i+=1;}return at+text.len;
}
pub unsafe fn emit(base:u64,displacement:i64,out:[]u8,written:*usize)u64{unsafe{
 let wp=written as u64;let op=out.ptr as u64;
 if written==null||(wp&7)!=0||!span(wp,8){return INVALID;}
 if !span(op,out.len){return INVALID;}
 if overlap(wp,8,op,out.len){return INVALID;}
 if base>15||base==4||base==5{return INVALID;}
 if displacement<I32_MIN||displacement>I32_MAX{return INVALID;}
 var lbuf:[128]u8=[0;128];var llen:usize=0;
 let ls=loadm.emit(0,base,displacement,8,false,slice_from_raw_parts(&lbuf[0],128),&llen);
 if ls!=loadm.OK{return INVALID;}
 var ubuf:[64]u8=[0;64];var ulen:usize=0;
 let us=unarym.emit(2,0,slice_from_raw_parts(&ubuf[0],64),&ulen);
 if us!=unarym.OK{return INVALID;}
 if llen>MAX-ulen{return INVALID;}let total=llen+ulen;
 if total>out.len{return CAPACITY;}
 // BAD: the second zero-compare is deleted, so the truth value is inverted.
 var at=copy(out,0,slice_from_raw_parts(&lbuf[0],llen));
 at=copy(out,at,slice_from_raw_parts(&ubuf[0],ulen));
 *written=total;return OK;
}}
'''
BAD_EARLY='''module bootstrap.nasm_byte_truth_load_bad_early;
import bootstrap.nasm_integer_memory_load as loadm;
import bootstrap.nasm_integer_unary as unarym;
pub const OK:u64=0;pub const INVALID:u64=1;pub const CAPACITY:u64=2;
const MAX:u64=0xffff_ffff_ffff_ffff;
const I32_MIN:i64=-2147483648;
const I32_MAX:i64=2147483647;
fn span(p:u64,n:u64)bool{return n==0||(p!=0&&n<=MAX-p);}
fn overlap(a:u64,n:u64,b:u64,m:u64)bool{return n!=0&&m!=0&&a<b+m&&b<a+n;}
fn copy(out:[]u8,at:usize,text:[]const u8)usize{
 var i:usize=0;while i<text.len{out[at+i]=text[i];i+=1;}return at+text.len;
}
pub unsafe fn emit(base:u64,displacement:i64,out:[]u8,written:*usize)u64{unsafe{
 let wp=written as u64;let op=out.ptr as u64;
 if written==null||(wp&7)!=0||!span(wp,8){return INVALID;}
 if !span(op,out.len){return INVALID;}
 if overlap(wp,8,op,out.len){return INVALID;}
 if base>15||base==4||base==5{return INVALID;}
 if displacement<I32_MIN||displacement>I32_MAX{return INVALID;}
 // BAD: the load segment is published straight into the user out (and
 // written) before the combined bound with both unary segments is proved.
 var llen:usize=0;
 let ls=loadm.emit(0,base,displacement,8,false,out,&llen);
 if ls!=loadm.OK{return ls;}
 *written=llen;
 var ubuf:[64]u8=[0;64];var ulen:usize=0;
 let us=unarym.emit(2,0,slice_from_raw_parts(&ubuf[0],64),&ulen);
 if us!=unarym.OK{return INVALID;}
 if llen>MAX-ulen{return INVALID;}let a1=llen+ulen;
 if ulen>MAX-a1{return INVALID;}let total=a1+ulen;
 if total>out.len{return CAPACITY;}
 var at=copy(out,llen,slice_from_raw_parts(&ubuf[0],ulen));
 at=copy(out,at,slice_from_raw_parts(&ubuf[0],ulen));
 *written=total;return OK;
}}
'''
WRAPPER_BAD='''module probe.{name}_export;
import bootstrap.{module} as m;
export("dong_{name}_emit") pub unsafe fn emit(
 base:u64,displacement:i64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(base,displacement,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_byte_truth_load_emit(uint64_t,int64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 _Alignas(16) static uint8_t arena[4096];
 _Alignas(16) static uint8_t saved[4096];
 const unsigned total=13;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  if(i==5)memcpy(o+80,"movzx rax, byte [rdi]\n",22);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_byte_truth_load_emit(6,0,o,128,NULL);break;
   case 1:st=dong_byte_truth_load_emit(6,0,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_byte_truth_load_emit(6,0,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_byte_truth_load_emit(6,0,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_byte_truth_load_emit(6,0,NULL,128,w);break;
   case 5:st=dong_byte_truth_load_emit(6,0,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_byte_truth_load_emit(6,0,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_byte_truth_load_emit(16,0,o,128,w);break;
   case 8:st=dong_byte_truth_load_emit(4,0,o,128,w);break;
   case 9:st=dong_byte_truth_load_emit(5,0,o,128,w);break;
   case 10:st=dong_byte_truth_load_emit(6,2147483648LL,o,128,w);break;
   case 11:st=dong_byte_truth_load_emit(6,-2147483649LL,o,128,w);break;
   default:st=dong_byte_truth_load_emit(6,0,o,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
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
  uint64_t base=h[0];int64_t disp=(int64_t)h[1];uint64_t cap=h[2],nout=h[3];
  if(cap>320)exit(94);
  uint8_t*out=malloc(cap+64);_Alignas(8) uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_byte_truth_load_emit(base,disp,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''
PROBE_C=r'''#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdalign.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#else
#include <sys/mman.h>
#endif
void __attribute__((sysv_abi)) probe_byte_truth(uint64_t *state, uint8_t *base);
int main(void){
#ifdef _WIN32
_setmode(_fileno(stdout),_O_BINARY);
uint8_t*buf=VirtualAlloc(NULL,16384,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
uint8_t*buf=mmap(NULL,16384,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
if(buf==MAP_FAILED)return 94;
#endif
if(!buf)return 94;
memset(buf,0xa5,16384);uint8_t *target=buf+8192;*target=(uint8_t){byte};
uint8_t saved[16384];memcpy(saved,buf,16384);
#ifdef _WIN32
DWORD old;if(!VirtualProtect(buf,16384,PAGE_READONLY,&old))return 95;
#else
if(mprotect(buf,16384,PROT_READ))return 95;
#endif
alignas(16) uint64_t state[21]={0};
uint8_t *base_addr=target-({disp});
state[18]=(uint64_t)(uintptr_t)base_addr;
state[19]=(uint64_t)*target;
probe_byte_truth(state,base_addr);
state[20]=(uint64_t)*target;
if(memcmp(saved,buf,16384))return 96;
fwrite(state,8,21,stdout);
#ifdef _WIN32
if(!VirtualFree(buf,0,MEM_RELEASE))return 97;
#else
if(munmap(buf,16384))return 97;
#endif
return 0;
}
'''


def operand(base,disp):
    r=REGS64[base]
    if disp==0:
        return b'['+r+b']'
    sign=b'+' if disp>0 else b'-'
    return b'['+r+b' '+sign+b' '+str(abs(disp)).encode()+b']'


def load_text(base,disp):
    """Independent CR12/CR8-shaped model: zero-extended byte load to RAX."""
    return b'movzx rax, byte '+operand(base,disp)+b'\n'


UNARY_TEXT=b'test rax, rax\nsete al\nmovzx rax, al\n'


def expected(base,disp):
    """Load + TWO zero-compares; the double compare is the nonzero truth."""
    return load_text(base,disp)+UNARY_TEXT+UNARY_TEXT


def need_load(base,disp):
    return len(load_text(base,disp))


def need_total(base,disp):
    return len(expected(base,disp))


def truth(byte):
    return 1 if byte!=0 else 0


def item(base,disp,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        if base>15 or base in BAD_BASES or disp<I32_MIN or disp>I32_MAX:status=INVALID
        else:
            need=need_total(base,disp)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(base,disp) if status==OK else 64
    text=expected(base,disp) if status==OK else None
    return dict(base=base,disp=disp,cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<QqQQ',c['base'],c['disp'],c['cap'],c.get('nout',0))


# (base, disp, byte) — exactly 16 native vectors: bytes 0/1/127/128/255,
# bases rax/rdi/r11/r15, zero/positive/negative displacement.
NATIVE_VECTORS=[
    (6,0,0),(6,0,1),(6,0,127),(6,0,128),(6,0,255),
    (0,0,1),(0,0,255),(11,0,1),(15,0,255),
    (6,8,128),(6,-8,1),(0,0,0),(11,0,0),(15,0,0),
    (6,4096,255),(0,-4096,127),
]
assert len(NATIVE_VECTORS)==16


class NasmByteTruthLoadTests(unittest.TestCase):
    PREFLIGHTS=13

    @classmethod
    def setUpClass(cls):
        src=SOURCE.read_text(encoding='utf-8')
        # Structural proof: the load precedes TWO mandatory zero-compare
        # calls, locals are the declared 128/64 buffers, and publish happens
        # once at the very end.
        li=src.index('loadm.emit');ui=src.index('unarym.emit')
        assert li<ui,'load segment must be assembled before the unary segments'
        assert src.count('unarym.emit')==2,'double zero-compare is mandatory'
        assert '[128]u8' in src and '[64]u8' in src
        assert src.count('*written=')==1 and src.rstrip().endswith('}}')
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_byte_truth_load requires NASM/GCC')
        # Proved bounds from the independent model: load <= 35, one unary
        # segment exactly 36; combined <= 107, covered by locals 128/64.
        cls.max_load=max(need_load(b,d) for b in range(16) if b not in BAD_BASES
                         for d in (0,1,-1,I32_MAX,I32_MIN))
        cls.max_unary=len(UNARY_TEXT)
        if cls.max_load!=35 or cls.max_unary!=36 or cls.max_load+2*cls.max_unary>107:
            raise AssertionError((cls.max_load,cls.max_unary))
        cls.work=WORKS/'deepseek-works/build/D22'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        for src_file,name in [(SOURCE,'nasm_byte_truth_load.dg'),(LOAD,'nasm_integer_memory_load.dg'),
                              (UNARY,'nasm_integer_unary.dg'),(MEMOP,'nasm_memory_operand.dg'),
                              (CR4,'decimal_integer.dg')]:
            shutil.copy2(src_file,cls.src_root/'bootstrap'/name)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.native='win64'if os.name=='nt'else'elf64'
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__),LOAD,UNARY,MEMOP,CR4]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_byte_truth_load_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],
                wrapper/'probe/nasm_byte_truth_load_export.dg',mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name,symbol='dong_byte_truth_load_emit',probe_c=None):
        compiled=compile_file(wrapper,roots=roots,mode=mode)
        asm=cls.work/(name+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
        obj=cls.work/(name+'.o');exe=cls.work/(name+('.exe'if os.name=='nt'else''))
        for fmt in ('elf64','win64'):
            output=obj if fmt==cls.native else cls.work/(name+'.'+fmt+'.o')
            cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',output,asm],name+'-'+fmt)
        pc=probe_c if probe_c is not None else cls.work/'probe.c'
        if probe_c is None:
            pc=cls.work/(name+'-probe.c')
            pc.write_text(HARNESS.replace('dong_byte_truth_load_emit',symbol),encoding='utf-8')
        cls.command([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',pc,obj,'-o',exe],name+'-link')
        return exe

    @classmethod
    def bad_build(cls,name,bad_text,module,symbol):
        root=cls.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/(module+'.dg')).write_text(bad_text,encoding='utf-8')
        for p in cls.src_root.glob('bootstrap/*.dg'):
            if p.name!=module+'.dg':shutil.copy2(p,src/p.name)
        short_name=module.replace('nasm_byte_truth_load_bad_','')
        wrapper=root/'wrapper'/'probe'/(short_name+'_export.dg')
        wrapper.write_text(WRAPPER_BAD.replace('{name}',short_name)
                                  .replace('{module}',module),encoding='utf-8')
        return {mode:cls.build([root/'src',root/'wrapper'],wrapper,mode,name+'-'+mode,symbol=symbol)
                for mode in ('debug','release')}

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
        samples=[(6,0),(0,0),(11,0),(15,0),(6,8),(6,-8),(6,I32_MAX),(15,I32_MIN),(11,1),(0,-1)]
        for base,disp in samples:
            need=need_total(base,disp)
            lneed=need_load(base,disp)
            cases+=[item(base,disp),
                    item(base,disp,cap=need+3),
                    item(base,disp,cap=max(0,need-1)),
                    # Capacity landing after the load but before the complete
                    # text (load only, load+one unary): full text won't fit.
                    item(base,disp,cap=lneed,status=CAPACITY),
                    item(base,disp,cap=min(need-1,lneed+1),status=CAPACITY)]
        max_need=need_total(15,I32_MIN)
        self.assertEqual(max_need,107)
        cases+=[item(16,0,cap=64,status=INVALID),
                item(4,0,cap=64,status=INVALID),
                item(5,0,cap=64,status=INVALID),
                item(6,I32_MAX+1,cap=64,status=INVALID),
                item(6,I32_MIN-1,cap=64,status=INVALID),
                item(6,0,nout=1,cap=64,status=INVALID),
                item(16,0,nout=0,cap=0,status=INVALID),
                item(6,0,cap=0,status=CAPACITY),
                item(6,0,nout=0,cap=0,status=CAPACITY)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,max_need=max_need,
                                 max_load=self.max_load,max_unary=self.max_unary,passed=True))

    def test_dong_assemble_and_native_byte_truth(self):
        # i32 extreme displacements: legal text and assembly only, never
        # executed against inaccessible addresses.
        extreme=[item(6,I32_MAX),item(15,I32_MIN)]
        eresults=self.run_both(extreme,'extreme-text')
        asm_dir=self.work/'extreme-asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in eresults.items():
            for index,((base,disp),out) in enumerate(zip([(6,I32_MAX),(15,I32_MIN)],outs)):
                self.assertIsNotNone(out,(mode,index))
                body=b'bits 64\nsection .text\nglobal extreme_probe\nextreme_probe:\n'+out+b' ret\n'
                for fmt in ('elf64','win64'):
                    asm=asm_dir/f'{mode}-{index:03d}-{fmt}.asm'
                    obj=asm_dir/f'{mode}-{index:03d}-{fmt}.o'
                    asm.write_bytes(body)
                    runc=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                        capture_output=True,timeout=30)
                    self.assertEqual(runc.returncode,0,(mode,index,fmt,runc.stderr,out))
                    assembled+=1
        cases=[item(b,d)for b,d,_ in NATIVE_VECTORS]
        results=self.run_both(cases,'native-vecs')
        probed=0
        for mode,outs in results.items():
            for index,(vec,out) in enumerate(zip(NATIVE_VECTORS,outs)):
                base,disp,byte=vec
                captured=self._probe(mode,index,base,disp,byte,out)
                self.assertEqual(captured[0],truth(byte),(mode,index,vec,'truth RAX',
                                                         captured[0],truth(byte)))
                probed+=1
        self.records.append(dict(test='dong-assemble-native-byte-truth',extreme_assembled=assembled,
                                 native_vectors=len(NATIVE_VECTORS),probed=probed,
                                 register_preserve=True,source_readonly=True,modes=2,formats=2,passed=True))

    def _expected_regs(self,base,base_addr,observe):
        expected={}
        for r in observe:
            if r==0:continue
            expected[r]=base_addr if r==base else (0x1111111111111100+r)
        return expected

    def _assert_preserved(self,mode,index,base,base_addr,captured):
        expected=self._expected_regs(base,base_addr,sorted(captured))
        for r,want in expected.items():
            self.assertEqual(captured[r],want,
                             (mode,index,'reg%d preserved'%r,REGS64[r].decode(),
                              hex(captured[r]),hex(want)))

    def _probe(self,mode,index,base,disp,byte,text:bytes):
        """Capture every non-RSP GPR before scratch use, plus before/after RSP.
        The source mapping is read-only, including surrounding guard bytes.
        Host callee-saved registers are restored before returning to C.
        """
        observe=sorted(SAFE)
        n=len(observe)
        lines=['bits 64','section .text','global probe_byte_truth','probe_byte_truth:',
               ' push rbx',' push rbp',' push r12',' push r13',' push r14',' push r15',
               ' push rdi',' push rsi',
               ' mov [rdi+128], rsp']
        for r in observe:
            lines.append(f' mov {REGS64[r].decode()}, 0x{0x1111111111111100+r:x}')
        lines.append(f' mov {REGS64[base].decode()}, [rsp]')
        lines+=text.decode('ascii').rstrip('\n').split('\n')
        lines += [f' push {REGS64[r].decode()}' for r in observe]
        lines.append(f' mov rcx, [rsp+{8*n+8}]')
        for i in range(n):
            lines += [f' mov rax, [rsp+{8*(n-1-i)}]',f' mov [rcx+{8*i}], rax']
        lines += [f' lea rax, [rsp+{8*n}]',' mov [rcx+120], rax',
                  ' mov qword [rcx+136], 111',
                  f' add rsp, {8*n+16}',
                  ' pop r15',' pop r14',' pop r13',' pop r12',' pop rbp',' pop rbx',' ret']
        body='\n'.join(lines)+'\n'
        d=self.work/'byte-truth-probe';d.mkdir(exist_ok=True)
        asm=d/f'{mode}-{index:03d}.asm';obj=d/f'{mode}-{index:03d}.o'
        exe=d/f"{mode}-{index:03d}{'.exe'if os.name=='nt'else''}"
        asm.write_text(body,encoding='utf-8')
        r=subprocess.run([str(self.nasm),'-f',self.native,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                         capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,(r.stderr,body))
        csrc=d/f'{mode}-{index:03d}.c'
        csrc.write_text(PROBE_C.replace('{byte}',str(byte)).replace('{disp}',str(disp)),encoding='utf-8')
        r=subprocess.run([str(self.cc),'-std=c11','-O2','-Wall','-Wextra','-Werror',
                          str(csrc),str(obj),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        run=subprocess.run([str(exe)],capture_output=True,timeout=30)
        self.assertEqual(run.returncode,0,(run.returncode,run.stderr,run.stdout))
        nwords=21
        self.assertEqual(len(run.stdout),8*nwords)
        words=list(struct.unpack(f'<{nwords}Q',run.stdout))
        base_addr=words[18]
        self.assertEqual(words[19],words[20],(mode,index,'source byte read-only',
                                              words[19],words[20]))
        self.assertEqual(words[15],words[16],(mode,index,'rsp recovered',
                                                      hex(words[15]),hex(words[16])))
        self.assertEqual(words[17],FALL,(mode,index,'marker'))
        captured={r:words[i] for i,r in enumerate(observe)}
        self._assert_preserved(mode,index,base,base_addr,captured)
        return captured

    def _emit_text(self,exe,c,label):
        payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(c))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        self.assertEqual(run.returncode,0,run.stderr)
        st,g,w=struct.unpack_from('<3Q',run.stdout,8)
        self.assertEqual(st,0,(label,st));self.assertEqual(g,1)
        return run.stdout[32:32+c['cap']][:w]

    def test_actual_compiled_dropped_compare_is_rejected(self):
        """Real bad Dong with the second zero-compare deleted: completes
        build/link, returns normally, but the truth value is inverted; the
        same-input good body passes first, then the bad body is rejected by
        the truth RAX value. Both boundaries, both modes."""
        bad=self.bad_build('bad-drop',BAD_DROP,'nasm_byte_truth_load_bad_drop','dong_drop_emit')
        for byte,want in [(255,1),(0,0)]:
            c=item(6,0)
            for mode in self.executables:
                good=self._emit_text(self.executables[mode],c,f'good-drop-{mode}')
                self.assertEqual(good,expected(6,0),(mode,good))
                captured=self._probe(mode,700,6,0,byte,good)
                self.assertEqual(captured[0],want,(mode,byte,'good truth',captured[0]))
                self.assertEqual(captured[0],truth(byte),(mode,byte,'good truth'))
                evil=self._emit_text(bad[mode],c,f'bad-drop-{mode}')
                self.assertNotEqual(evil,good,(mode,'bad text differs'))
                self.assertEqual(evil,load_text(6,0)+UNARY_TEXT,(mode,'one compare only'))
                captured=self._probe(mode,710,6,0,byte,evil)
                wrong=1-want
                self.assertEqual(captured[0],wrong,(mode,byte,'inverted truth observed',
                                                    captured[0],wrong))
                self.assertNotEqual(captured[0],want,(mode,byte,'truth value rejects bad body'))
        self.records.append(dict(test='bad-dropped-compare',compiled=True,native_executed=True,modes=2,
                                 boundaries=[255,0],rejected_by='truth-rax-value',passed=True))

    def test_actual_compiled_r11_clobber_is_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        old='*written=total;return OK;'
        new=('let extra="mov r11, 61453\\n";var e:usize=0;'
             'while e<extra.len{out[total+e]=extra[e];e+=1;}'
             '*written=total+extra.len;return OK;')
        self.assertEqual(source.count(old),1)
        bad=source.replace('module bootstrap.nasm_byte_truth_load;',
                           'module bootstrap.nasm_byte_truth_load_bad_r11;').replace(old,new)
        executables=self.bad_build('bad-r11',bad,'nasm_byte_truth_load_bad_r11','dong_r11_emit')
        for mode,exe in executables.items():
            c=item(11,0,cap=128)
            good=self._emit_text(self.executables[mode],c,'r11-good-'+mode)
            self.assertEqual(self._probe(mode,920,11,0,255,good)[0],1)
            evil=self._emit_text(exe,c,'r11-bad-'+mode)
            self.assertEqual(evil,good+b'mov r11, 61453\n')
            with self.assertRaisesRegex(AssertionError,'r11'):
                self._probe(mode,921,11,0,255,evil)
        self.records.append(dict(test='bad-r11',compiled=True,native_executed=True,
                                 modes=2,rejected_by='captured-r11-value'))

    def test_actual_compiled_early_publish_is_rejected(self):
        """Real bad Dong: publishes the load segment into the user out and
        written before the combined bound with both unary segments is proved;
        the full-output atomicity assertion rejects it while the good body
        keeps out/written intact on the same fixture."""
        base,disp=6,0
        lneed=need_load(base,disp)
        short=item(base,disp,cap=lneed,status=CAPACITY)
        self.run_both([short],'early-good')
        bad=self.bad_build('bad-early',BAD_EARLY,'nasm_byte_truth_load_bad_early','dong_early_emit')
        for mode,exe in bad.items():
            payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(short))
            run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
            self.assertEqual(run.returncode,0,run.stderr)
            st,g,w=struct.unpack_from('<3Q',run.stdout,8)
            out=run.stdout[32:32+short['cap']]
            self.assertEqual(st,CAPACITY,(mode,st))
            self.assertEqual(w,0,(mode,'masked written'))
            self.assertEqual(out,load_text(base,disp),(mode,'early out publish observed'))
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                self.run_cases(exe,[short],'early-bad-'+mode)
        self.records.append(dict(test='bad-early-publish',compiled=True,native_executed=True,modes=2,
                                 rejected_by='complete-out-written-atomicity',passed=True))


if __name__=='__main__':unittest.main()
