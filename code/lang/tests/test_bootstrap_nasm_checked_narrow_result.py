"""Actual Dong composed checked narrow result (CR28 guard then CR14 cast)."""
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
from lang.tests.test_dongc import tool,nasm_flags as _nasm_flags

def nasm_flags(nasm):
    flags=list(_nasm_flags(nasm))
    if '-w-reloc-rel-dword' not in flags:
        flags.append('-w-reloc-rel-dword')
    return flags

SOURCE=ROOT/'lang/bootstrap/nasm_checked_narrow_result.dg'
DOC=ROOT/'lang/bootstrap/nasm_checked_narrow_result.md'
GUARD=ROOT/'lang/bootstrap/nasm_narrow_range_guard.dg'
CAST=ROOT/'lang/bootstrap/nasm_integer_cast.dg'
def _dep(p):
    return p if p.is_file() else ROOT/'lang/bootstrap'/p.name
CR4=_dep(ROOT/'lang/bootstrap/decimal_integer.dg')
OK,INVALID,CAPACITY=0,1,2
NONE=(1<<64)-1
TOP=1<<63
WIDTHS=(8,16,32)
REGS64=[b'rax',b'rcx',b'rdx',b'rbx',b'rsp',b'rbp',b'rsi',b'rdi',
        b'r8',b'r9',b'r10',b'r11',b'r12',b'r13',b'r14',b'r15']
# RAX holds the value; R11 is intentionally clobbered by the guard.
# Only RAX and R11 (plus flags) may change, so every other GPR is captured
# and compared after the sequence: SAFE includes rbx/rbp/r12..r15 too.
SAFE={0,1,2,3,5,6,7,8,9,10,12,13,14,15}
FALL=111
TRAP=222
WRAPPER='''module probe.nasm_checked_narrow_result_export;
import bootstrap.nasm_checked_narrow_result as m;
export("dong_checked_narrow_result_emit") pub unsafe fn emit(
 width:u64,signed:bool,trap_block:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(width,signed,trap_block,slice_from_raw_parts(out,no),written);
}}
'''
BAD_INVERTED='''module bootstrap.nasm_checked_narrow_result_bad_inverted;
import bootstrap.nasm_narrow_range_guard as guardm;
import bootstrap.nasm_integer_cast as castm;
pub const OK:u64=0;pub const INVALID:u64=1;pub const CAPACITY:u64=2;
pub const NONE:u64=0xffff_ffff_ffff_ffff;
const MAX:u64=0xffff_ffff_ffff_ffff;
fn span(p:u64,n:u64)bool{return n==0||(p!=0&&n<=MAX-p);}
fn overlap(a:u64,n:u64,b:u64,m:u64)bool{return n!=0&&m!=0&&a<b+m&&b<a+n;}
fn width_ok(w:u64)bool{return w==8||w==16||w==32;}
pub unsafe fn emit(width:u64,signed:bool,trap_block:u64,out:[]u8,written:*usize)u64{unsafe{
 let wp=written as u64;let op=out.ptr as u64;
 if written==null||(wp&7)!=0||!span(wp,8){return INVALID;}
 if !span(op,out.len){return INVALID;}
 if overlap(wp,8,op,out.len){return INVALID;}
 if !width_ok(width)||trap_block==NONE{return INVALID;}
 // BAD: normalization (truncate) happens BEFORE the full-result range check.
 var cbuf:[32]u8=[0;32];var clen:usize=0;
 let cs=castm.emit(0,0,width,signed,slice_from_raw_parts(&cbuf[0],32),&clen);
 if cs!=castm.OK{return INVALID;}
 var gbuf:[256]u8=[0;256];var glen:usize=0;
 let gs=guardm.emit(width,signed,trap_block,slice_from_raw_parts(&gbuf[0],256),&glen);
 if gs!=guardm.OK{return INVALID;}
 if glen>MAX-clen{return INVALID;}
 let total=glen+clen;
 if total>out.len{return CAPACITY;}
 var i:usize=0;while i<clen{out[i]=cbuf[i];i+=1;}
 var j:usize=0;while j<glen{out[clen+j]=gbuf[j];j+=1;}
 *written=total;return OK;
}}
'''
BAD_EARLY='''module bootstrap.nasm_checked_narrow_result_bad_early;
import bootstrap.nasm_narrow_range_guard as guardm;
import bootstrap.nasm_integer_cast as castm;
pub const OK:u64=0;pub const INVALID:u64=1;pub const CAPACITY:u64=2;
pub const NONE:u64=0xffff_ffff_ffff_ffff;
const MAX:u64=0xffff_ffff_ffff_ffff;
fn span(p:u64,n:u64)bool{return n==0||(p!=0&&n<=MAX-p);}
fn overlap(a:u64,n:u64,b:u64,m:u64)bool{return n!=0&&m!=0&&a<b+m&&b<a+n;}
fn width_ok(w:u64)bool{return w==8||w==16||w==32;}
pub unsafe fn emit(width:u64,signed:bool,trap_block:u64,out:[]u8,written:*usize)u64{unsafe{
 let wp=written as u64;let op=out.ptr as u64;
 if written==null||(wp&7)!=0||!span(wp,8){return INVALID;}
 if !span(op,out.len){return INVALID;}
 if overlap(wp,8,op,out.len){return INVALID;}
 if !width_ok(width)||trap_block==NONE{return INVALID;}
 // BAD: guard segment is published straight into the user out (and written)
 // before the combined bound with the cast segment has been proved.
 var glen:usize=0;
 let gs=guardm.emit(width,signed,trap_block,out,&glen);
 if gs!=guardm.OK{return gs;}
 *written=glen;
 var cbuf:[32]u8=[0;32];var clen:usize=0;
 let cs=castm.emit(0,0,width,signed,slice_from_raw_parts(&cbuf[0],32),&clen);
 if cs!=castm.OK{return INVALID;}
 let total=glen+clen;
 if total>out.len{return CAPACITY;}
 var j:usize=0;while j<clen{out[glen+j]=cbuf[j];j+=1;}
 *written=total;return OK;
}}
'''
WRAPPER_BAD='''module probe.{name}_export;
import bootstrap.{module} as m;
export("dong_{name}_emit") pub unsafe fn emit(
 width:u64,signed:bool,trap_block:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(width,signed,trap_block,slice_from_raw_parts(out,no),written);
}}
'''
BAD_CLOBBER='''module bootstrap.nasm_checked_narrow_result_bad_clobber;
import bootstrap.nasm_narrow_range_guard as guardm;
import bootstrap.nasm_integer_cast as castm;
pub const OK:u64=0;pub const INVALID:u64=1;pub const CAPACITY:u64=2;
pub const NONE:u64=0xffff_ffff_ffff_ffff;
const MAX:u64=0xffff_ffff_ffff_ffff;
fn span(p:u64,n:u64)bool{return n==0||(p!=0&&n<=MAX-p);}
fn overlap(a:u64,n:u64,b:u64,m:u64)bool{return n!=0&&m!=0&&a<b+m&&b<a+n;}
fn width_ok(w:u64)bool{return w==8||w==16||w==32;}
pub unsafe fn emit(width:u64,signed:bool,trap_block:u64,out:[]u8,written:*usize)u64{unsafe{
 let wp=written as u64;let op=out.ptr as u64;
 if written==null||(wp&7)!=0||!span(wp,8){return INVALID;}
 if !span(op,out.len){return INVALID;}
 if overlap(wp,8,op,out.len){return INVALID;}
 if !width_ok(width)||trap_block==NONE{return INVALID;}
 var gbuf:[256]u8=[0;256];var glen:usize=0;
 let gs=guardm.emit(width,signed,trap_block,slice_from_raw_parts(&gbuf[0],256),&glen);
 if gs!=guardm.OK{return INVALID;}
 var cbuf:[32]u8=[0;32];var clen:usize=0;
 let cs=castm.emit(0,0,width,signed,slice_from_raw_parts(&cbuf[0],32),&clen);
 if cs!=castm.OK{return INVALID;}
 // BAD: appends a line that clobbers callee-saved RBX, which must be kept.
 // "mov rbx, 61453\\n" is 15 bytes of ASCII written below.
 if glen>MAX-clen{return INVALID;}
 if clen>MAX-15{return INVALID;}
 let total=glen+clen+15;
 if total>out.len{return CAPACITY;}
 var i:usize=0;while i<glen{out[i]=gbuf[i];i+=1;}
 var j:usize=0;while j<clen{out[glen+j]=cbuf[j];j+=1;}
 var at=glen+clen;
 out[at+0]=109;out[at+1]=111;out[at+2]=118;out[at+3]=32;out[at+4]=114;
 out[at+5]=98;out[at+6]=120;out[at+7]=44;out[at+8]=32;out[at+9]=54;
 out[at+10]=49;out[at+11]=52;out[at+12]=53;out[at+13]=51;out[at+14]=10;
 *written=total;return OK;
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
extern uint64_t ABI dong_checked_narrow_result_emit(uint64_t,uint8_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 _Alignas(16) static uint8_t arena[4096];
 _Alignas(16) static uint8_t saved[4096];
 const unsigned total=17;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  if(i==5)memcpy(o+80,"mov r11, 127\n",13);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_checked_narrow_result_emit(8,1,0,o,128,NULL);break;
   case 1:st=dong_checked_narrow_result_emit(8,1,0,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_checked_narrow_result_emit(8,1,0,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_checked_narrow_result_emit(8,1,0,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_checked_narrow_result_emit(8,1,0,NULL,128,w);break;
   case 5:st=dong_checked_narrow_result_emit(8,1,0,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_checked_narrow_result_emit(8,1,0,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_checked_narrow_result_emit(8,1,0,o,0,(uint64_t*)(uintptr_t)1);break;
   case 8:st=dong_checked_narrow_result_emit(8,1,0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=dong_checked_narrow_result_emit(0,1,0,o,128,w);break;
   case 10:st=dong_checked_narrow_result_emit(64,1,0,o,128,w);break;
   case 11:st=dong_checked_narrow_result_emit(7,1,0,o,128,w);break;
   case 12:st=dong_checked_narrow_result_emit(8,1,UINT64_MAX,o,128,w);break;
   case 13:st=dong_checked_narrow_result_emit(0,1,0,o,0,w);break;
   case 14:st=dong_checked_narrow_result_emit(64,0,0,o,0,w);break;
   case 15:st=dong_checked_narrow_result_emit(128,1,0,o,0,w);break;
   default:st=dong_checked_narrow_result_emit(8,1,UINT64_MAX,o,0,w);break;
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
  uint64_t h[5];read_exact(h,sizeof(h));
  uint64_t width=h[0],signed_f=h[1],trap=h[2],cap=h[3],nout=h[4];
  if(cap>320)exit(94);
  uint8_t*out=malloc(cap+64);_Alignas(8) uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_checked_narrow_result_emit(width,(uint8_t)signed_f,trap,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''


def i64(v):
    v&=NONE
    return v-(1<<64) if v>=TOP else v


def signed_bounds(width):
    if width==8:return -128,127
    if width==16:return -32768,32767
    return -2147483648,2147483647


def unsigned_max(width):
    return (1<<width)-1


def min_bits(width):
    mn,_=signed_bounds(width)
    return mn&(NONE)


def max_mag(width,signed):
    if signed:
        _,mx=signed_bounds(width)
        return mx
    return unsigned_max(width)


def dec_text(raw,signed):
    if not signed:
        return str(raw&NONE).encode('ascii')
    return str(i64(raw)).encode('ascii')


def guard_expected(width,signed,trap):
    """Independent CR28-shaped model of the guard segment."""
    t=str(trap).encode('ascii')
    if signed:
        mn=dec_text(min_bits(width),True)
        mx=dec_text(max_mag(width,True),False)
        return (b'mov r11, '+mn+b'\n'
                b'cmp rax, r11\n'
                b'jl __dong_b'+t+b'\n'
                b'mov r11, '+mx+b'\n'
                b'cmp rax, r11\n'
                b'jg __dong_b'+t+b'\n')
    mx=dec_text(max_mag(width,False),False)
    return (b'mov r11, '+mx+b'\n'
            b'cmp rax, r11\n'
            b'ja __dong_b'+t+b'\n')


def cast_expected(width,signed):
    """Independent CR14-shaped model for destination=0, source=0."""
    if width==8:return (b'movsx rax, al\n' if signed else b'movzx rax, al\n')
    if width==16:return (b'movsx rax, ax\n' if signed else b'movzx rax, ax\n')
    # CR14 kind 5 emits dest32/src32: "mov eax, eax" zero-extends into RAX.
    return (b'movsxd rax, eax\n' if signed else b'mov eax, eax\n')


def expected(width,signed,trap):
    return guard_expected(width,signed,trap)+cast_expected(width,signed)


def need_guard(width,signed,trap):
    return len(guard_expected(width,signed,trap))


def need_total(width,signed,trap):
    return len(expected(width,signed,trap))


def py_route(value,width,signed):
    """Independent full-64-bit range check; never truncate first."""
    value&=NONE
    if signed:
        iv=i64(value)
        mn,mx=signed_bounds(width)
        return 'trap' if iv<mn or iv>mx else 'fall'
    return 'trap' if value>unsigned_max(width) else 'fall'


def item(width,signed,trap,cap=None,status=None,nout=0):
    sg=1 if signed else 0
    if nout and status is None:status=INVALID
    if status is None:
        if width not in WIDTHS or trap==NONE:status=INVALID
        else:
            need=need_total(width,signed,trap)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(width,signed,trap) if status==OK else 64
    text=expected(width,signed,trap) if status==OK else None
    return dict(width=width,signed=sg,trap=trap,cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<5Q',c['width'],c['signed'],c['trap'],c['cap'],c.get('nout',0))


# (width, signed, value, trap) — exactly 24: 3 widths × 2 signs × 4 boundaries.
NATIVE_VECTORS=[]
for w in WIDTHS:
    mn,mx=signed_bounds(w)
    NATIVE_VECTORS+=[
        (w,True,(mn-1)&NONE,10+w),
        (w,True,mn&NONE,20+w),
        (w,True,mx&NONE,30+w),
        (w,True,(mx+1)&NONE,40+w),
    ]
    umx=unsigned_max(w)
    NATIVE_VECTORS+=[
        (w,False,0,50+w),
        (w,False,umx,60+w),
        (w,False,(umx+1)&NONE,70+w),
        (w,False,NONE,80+w),
    ]
assert len(NATIVE_VECTORS)==24


class NasmCheckedNarrowResultTests(unittest.TestCase):
    PREFLIGHTS=17

    @classmethod
    def setUpClass(cls):
        src=SOURCE.read_text(encoding='utf-8')
        # Structural order proof: guard is emitted before the cast, both into
        # the declared 256/32-byte locals, and publish happens once at the end.
        gi=src.index('guardm.emit');ci=src.index('castm.emit')
        assert gi<ci,'guard segment must be assembled before the cast segment'
        assert '[256]u8' in src and '[32]u8' in src
        assert src.count('*written=')==1 and src.rstrip().endswith('}}')
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_checked_narrow_result requires NASM/GCC')
        # Proved bounds from the independent model: guard <= 131, cast <= 16,
        # combined <= 147; the module's locals (256/32) cover both segments.
        cls.max_guard=max(need_guard(w,s,NONE-1) for w in WIDTHS for s in (True,False))
        cls.max_cast=max(len(cast_expected(w,s)) for w in WIDTHS for s in (True,False))
        if cls.max_guard!=131 or cls.max_cast!=16 or cls.max_guard+cls.max_cast>147:
            raise AssertionError((cls.max_guard,cls.max_cast))
        cls.work=WORKS/'build/test/bootstrap-nasm-checked-narrow-result'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_checked_narrow_result.dg')
        shutil.copy2(GUARD,cls.src_root/'bootstrap'/'nasm_narrow_range_guard.dg')
        shutil.copy2(CAST,cls.src_root/'bootstrap'/'nasm_integer_cast.dg')
        shutil.copy2(CR4,cls.src_root/'bootstrap'/'decimal_integer.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.native='win64'if os.name=='nt'else'elf64'
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__),GUARD,CAST,CR4]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_checked_narrow_result_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],
                wrapper/'probe/nasm_checked_narrow_result_export.dg',mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name,symbol='dong_checked_narrow_result_emit'):
        compiled=compile_file(wrapper,roots=roots,mode=mode)
        asm=cls.work/(name+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
        obj=cls.work/(name+'.o');exe=cls.work/(name+('.exe'if os.name=='nt'else''))
        for fmt in ('elf64','win64'):
            output=obj if fmt==cls.native else cls.work/(name+'.'+fmt+'.o')
            cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',output,asm],name+'-'+fmt)
        probe_c=cls.work/(name+'-probe.c')
        probe_c.write_text(HARNESS.replace('dong_checked_narrow_result_emit',symbol),encoding='utf-8')
        cls.command([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',probe_c,obj,'-o',exe],name+'-link')
        return exe

    @classmethod
    def bad_build(cls,name,bad_text,module):
        root=cls.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/(module+'.dg')).write_text(bad_text,encoding='utf-8')
        for p in cls.src_root.glob('bootstrap/*.dg'):
            shutil.copy2(p,src/p.name)
        short_name=module.replace('nasm_checked_narrow_result_','')
        wrapper=root/'wrapper'/'probe'/(short_name+'_export.dg')
        wrapper.write_text(
            WRAPPER_BAD.replace('{name}',short_name)
                       .replace('{module}',module),encoding='utf-8')
        return {mode:cls.build([root/'src',root/'wrapper'],wrapper,mode,name+'-'+mode,
                               symbol='dong_'+short_name+'_emit')
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
        for width in WIDTHS:
            for signed in (True,False):
                for trap in (0,1,42,TOP,NONE-1):
                    need=need_total(width,signed,trap)
                    gneed=need_guard(width,signed,trap)
                    cases+=[item(width,signed,trap),
                            item(width,signed,trap,cap=need+3),
                            item(width,signed,trap,cap=max(0,need-1)),
                            # Capacity landing strictly between the guard and
                            # cast segments: guard fits, the cast does not.
                            item(width,signed,trap,cap=gneed,status=CAPACITY),
                            item(width,signed,trap,cap=min(need-1,gneed+1),status=CAPACITY)]
        max_need=need_total(32,True,NONE-1)
        self.assertEqual(max_need,147)
        cases+=[item(32,True,NONE-1),
                item(32,True,NONE-1,cap=max_need),
                item(32,True,NONE-1,cap=max_need-1),
                item(0,True,0,cap=64,status=INVALID),
                item(64,True,0,cap=64,status=INVALID),
                item(7,False,0,cap=64,status=INVALID),
                item(128,True,0,cap=64,status=INVALID),
                item(8,True,NONE,cap=64,status=INVALID),
                item(8,True,0,nout=1,cap=64,status=INVALID),
                item(0,True,0,nout=0,cap=0,status=INVALID),
                item(64,False,0,nout=0,cap=0,status=INVALID),
                item(8,True,NONE,nout=0,cap=0,status=INVALID),
                item(8,True,0,cap=0,status=CAPACITY)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,max_need=max_need,
                                 max_guard=self.max_guard,max_cast=self.max_cast,passed=True))

    def test_dong_assemble_and_native_checked_narrow(self):
        samples=[(w,s,t)
                 for w in WIDTHS
                 for s in (True,False)
                 for t in (0,w,100+w,TOP,NONE-1)]
        cases=[item(w,s,t)for w,s,t in samples]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,((w,s,t),out) in enumerate(zip(samples,outs)):
                self.assertIsNotNone(out,(mode,index))
                body=(b'bits 64\nsection .text\n'+out+
                      b'mov rax, 1\n ret\n__dong_b'+str(t).encode()+b':\n mov rax, 2\n ret\n')
                for fmt in ('elf64','win64'):
                    asm=asm_dir/f'{mode}-{index:03d}-{fmt}.asm'
                    obj=asm_dir/f'{mode}-{index:03d}-{fmt}.o'
                    asm.write_bytes(body)
                    runc=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                        capture_output=True,timeout=30)
                    self.assertEqual(runc.returncode,0,(mode,index,fmt,runc.stderr,out))
                    assembled+=1
        ncases=[item(w,s,t)for w,s,_,t in NATIVE_VECTORS]
        nresults=self.run_both(ncases,'native-vecs')
        probed=0
        for mode,outs in nresults.items():
            for index,(vec,out) in enumerate(zip(NATIVE_VECTORS,outs)):
                width,signed,value,trap=vec
                marker,captured=self._probe(mode,index,value,width,signed,trap,out)
                want=TRAP if py_route(value,width,signed)=='trap' else FALL
                self.assertEqual(marker,want,(mode,index,vec,py_route(value,width,signed),out,marker))
                self._assert_preserved(mode,index,value,captured)
                probed+=1
        self.records.append(dict(test='dong-assemble-native-checked-narrow',assemble_samples=len(samples),
                                 assembled=assembled,native_vectors=len(NATIVE_VECTORS),probed=probed,
                                 register_preserve=True,modes=2,formats=2,passed=True))

    def _expected_regs(self,value,observe):
        expected={}
        for r in observe:
            expected[r]=(value&NONE) if r==0 else (0x1111111111111100+r)
        return expected

    def _assert_preserved(self,mode,index,value,captured):
        expected=self._expected_regs(value,sorted(captured))
        for r,want in expected.items():
            self.assertEqual(captured[r],want,
                             (mode,index,'reg%d preserved'%r,REGS64[r].decode(),
                              hex(captured[r]),hex(want)))

    def _probe(self,mode,index,value,width,signed,trap,text:bytes):
        """Path marker + captured full remaining GPR set and stack recovery.

        Safe bridge: the host callee-saved registers are saved first, magic
        values are placed in every captured GPR before the real emitted text
        runs, the sequence executes, then all captured values (RAX, the 13
        non-R11 GPRs, and two RSP observation slots) are copied into the
        state buffer, and only afterwards is the host ABI restored by popping
        the saved callee-saved registers. Nothing relies on a crash or on
        pushing a register over the sequence: every value is independently
        captured after the text and compared in Python.

        State layout (17 qwords): 0 RAX; 1..13 rcx,rdx,rbx,rbp,rsi,rdi,
        r8,r9,r10,r12,r13,r14,r15; 14 RSP after the text; 15 RSP baseline
        (pushed right before the text, so the text must leave RSP at exactly
        baseline-8); 16 path marker (FALL=111 / TRAP=222 via R11).
        """
        spill=3  # rbx is captured like any other GPR; state ptr lives on stack
        observe=sorted(SAFE)
        expected=self._expected_regs(value,observe)
        lines=['bits 64','section .text','global probe_checked_narrow','probe_checked_narrow:',
               ' push rbx',' push rbp',' push r12',' push r13',' push r14',' push r15',
               ' push rdi',' push rsp']
        for r in observe:
            if r!=0:
                lines.append(f' mov {REGS64[r].decode()}, 0x{expected[r]:x}')
        lines.append(f' mov rax, 0x{value&NONE:x}')
        lines+=text.decode('ascii').rstrip('\n').split('\n')
        lines+=[' mov r11, 111',' jmp capture']

        def capture():
            block=['__dong_b'+str(trap)+':',' mov r11, 222','capture:',
                   ' push rsp',' push rax',
                   ' push rcx',' push rdx',' push rbx',' push rbp',' push rsi',' push rdi',
                   ' push r8',' push r9',' push r10',' push r12',' push r13',' push r14',' push r15',
                   ' mov rcx, [rsp+128]']
            # capture stack: +0 r15,+8 r14,+16 r13,+24 r12,+32 r10,+40 r9,+48 r8,
            # +56 rdi,+64 rsi,+72 rbp,+80 rbx,+88 rdx,+96 rcx,+104 rax,
            # +112 rsp_after,+120 rsp_baseline,+128 state_ptr, then callee-saved originals
            pairs=[(104,0),(96,8),(88,16),(80,24),(72,32),(64,40),(56,48),
                   (48,56),(40,64),(32,72),(24,80),(16,88),(8,96),(0,104)]
            for src,dst in pairs:
                block.append(f' mov rax, [rsp+{src}]')
                block.append(f' mov [rcx+{dst}], rax')
            block+=[' mov rax, [rsp+112]',' mov [rcx+112], rax',
                    ' mov rax, [rsp+120]',' mov [rcx+120], rax',
                    ' mov [rcx+128], r11',
                    ' add rsp, 120',' add rsp, 16',
                    ' pop r15',' pop r14',' pop r13',' pop r12',' pop rbp',' pop rbx',' ret']
            return block

        lines+=capture()
        body='\n'.join(lines)+'\n'
        d=self.work/'checked-narrow-probe';d.mkdir(exist_ok=True)
        asm=d/f'{mode}-{index:03d}.asm';obj=d/f'{mode}-{index:03d}.o'
        exe=d/f"{mode}-{index:03d}{'.exe'if os.name=='nt'else''}"
        asm.write_text(body,encoding='utf-8')
        r=subprocess.run([str(self.nasm),'-f',self.native,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                         capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,(r.stderr,body))
        nwords=17
        csrc=d/f'{mode}-{index:03d}.c'
        csrc.write_text(
            '#include <stdint.h>\n#include <stdio.h>\n#include <stdalign.h>\n'
            '#ifdef _WIN32\n#include <io.h>\n#include <fcntl.h>\n#endif\n'
            'void __attribute__((sysv_abi)) probe_checked_narrow(uint64_t *state);\n'
            'int main(void){\n'
            '#ifdef _WIN32\n'
            '_setmode(_fileno(stdout),_O_BINARY);\n'
            '#endif\n'
            f'alignas(16) uint64_t state[{nwords}];\n'
            f'for(int i=0;i<{nwords};i++)state[i]=0;\n'
            'probe_checked_narrow(state);\n'
            f'fwrite(state,8,{nwords},stdout);\n'
            'return 0;\n}\n',encoding='utf-8')
        r=subprocess.run([str(self.cc),'-std=c11','-O2','-Wall','-Wextra','-Werror',
                          str(csrc),str(obj),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        run=subprocess.run([str(exe)],capture_output=True,timeout=30)
        self.assertEqual(run.returncode,0,(run.returncode,run.stderr,run.stdout))
        self.assertEqual(len(run.stdout),8*nwords)
        words=list(struct.unpack(f'<{nwords}Q',run.stdout))
        # Stack recovery: RSP after the text must equal baseline-8 exactly
        # (the only RSP change between the two observations is the baseline
        # push itself; the sequence must not move RSP).
        self.assertEqual(words[14],(words[15]-8)&NONE,(mode,index,'rsp recovered',
                                                    hex(words[14]),hex(words[15])))
        captured={r:words[i] for i,r in enumerate(observe)}
        marker=words[16]
        return marker,captured

    def _emit_text(self,exe,c,label):
        payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(c))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        self.assertEqual(run.returncode,0,run.stderr)
        st,g,w=struct.unpack_from('<3Q',run.stdout,8)
        self.assertEqual(st,0,(label,st));self.assertEqual(g,1)
        return run.stdout[32:32+c['cap']][:w]

    def test_actual_compiled_inverted_order_is_rejected(self):
        """Real bad Dong: cast-first order builds, links, runs natively, and
        wrongly falls through on i8 result 128 and u8 result 256; the good
        body traps on the same inputs. Both boundaries, both modes."""
        cases={'signed-i8-128':item(8,True,90),'unsigned-u8-256':item(8,False,91)}
        bad=self.bad_build('bad-inverted',BAD_INVERTED,'nasm_checked_narrow_result_bad_inverted')
        boundaries=[('signed-i8-128',8,True,128,0x80),
                    ('unsigned-u8-256',8,False,256,0x100)]
        for name,width,signed,value,raw in boundaries:
            c=cases[name]
            for mode in self.executables:
                # Good body first on the same input: must take the trap path.
                good=self._emit_text(self.executables[mode],c,f'good-{name}')
                self.assertEqual(good,expected(width,signed,c['trap']),(mode,name,good))
                marker,captured=self._probe(mode,700,value,width,signed,c['trap'],good)
                self.assertEqual(marker,TRAP,(name,mode,'good-must-trap',marker))
                self._assert_preserved(mode,700,value,captured)
                # Bad body: completes build/link, runs natively, wrongly falls.
                evil=self._emit_text(bad[mode],c,f'bad-{name}')
                self.assertNotEqual(evil,good,(name,mode,'bad text differs'))
                self.assertLess(evil.index(cast_expected(width,signed)),
                                evil.index(guard_expected(width,signed,c['trap'])[:8]),
                                (name,mode,'cast precedes guard in bad text'))
                marker,captured=self._probe(mode,800,value,width,signed,c['trap'],evil)
                self.assertEqual(marker,FALL,(name,mode,'min/mag overflow wrongly falls',marker))
                # Bad body preserves the non-R11 GPRs, but RAX now holds the
                # WRONG cast-first normalization instead of the full result.
                self._assert_preserved(mode,800,value,{k:v for k,v in captured.items() if k!=0})
                self.assertNotEqual(captured[0],value&NONE,(name,mode,'wrong normalized RAX'))
                want=(((value&((1<<width)-1))^(1<<(width-1)))-(1<<(width-1)))&NONE if signed else (value&((1<<width)-1))
                self.assertEqual(captured[0],want,(name,mode,hex(captured[0]),hex(want)))
        self.records.append(dict(test='bad-inverted-order',compiled=True,native_executed=True,modes=2,
                                 boundaries=[b[0] for b in boundaries],
                                 rejected_by='good-traps-bad-falls-wrong-rax',passed=True))

    def test_actual_compiled_early_publish_is_rejected(self):
        """Real bad Dong: publishes the guard segment into the user out and
        written before the combined capacity is proved; full-output atomicity
        assertion rejects it while the good body keeps out/written intact."""
        trap=42
        gneed=need_guard(8,True,trap)
        short=item(8,True,trap,cap=gneed,status=CAPACITY)
        # Same fixture: good body first — CAPACITY with out and written untouched.
        self.run_both([short],'early-good')
        bad=self.bad_build('bad-early',BAD_EARLY,'nasm_checked_narrow_result_bad_early')
        for mode,exe in bad.items():
            payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(short))
            run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
            self.assertEqual(run.returncode,0,run.stderr)
            st,g,w=struct.unpack_from('<3Q',run.stdout,8)
            out=run.stdout[32:32+short['cap']]
            self.assertEqual(st,CAPACITY,(mode,st))
            # Harness masks written on failure; the dirty out itself proves
            # the early publish happened.
            self.assertEqual(w,0,(mode,'masked written'))
            self.assertEqual(out,guard_expected(8,True,trap),(mode,'early out publish observed'))
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                self.run_cases(exe,[short],'early-bad-'+mode)
        self.records.append(dict(test='bad-early-publish',compiled=True,native_executed=True,modes=2,
                                 rejected_by='complete-out-written-atomicity',passed=True))

    def test_actual_compiled_clobber_is_rejected(self):
        """Real bad Dong that completes build/link and returns NORMALLY after
        clobbering callee-saved RBX; the preserved-register capture rejects it
        by value. No crash, no build failure. Both modes, good body first."""
        bad=self.bad_build('bad-clobber',BAD_CLOBBER,'nasm_checked_narrow_result_bad_clobber')
        c=item(8,True,90)
        c_bad=item(8,True,90,cap=need_total(8,True,90)+15)  # extra clobber line
        value=1  # in range for i8: the fall path must return normally
        for mode in self.executables:
            good=self._emit_text(self.executables[mode],c,f'good-clobber-{mode}')
            self.assertEqual(good,expected(8,True,c['trap']),(mode,good))
            marker,captured=self._probe(mode,900,value,8,True,c['trap'],good)
            self.assertEqual(marker,FALL,(mode,'good falls',marker))
            self.assertEqual(captured[3],0x1111111111111103,(mode,'good keeps rbx'))
            evil=self._emit_text(bad[mode],c_bad,f'bad-clobber-{mode}')
            self.assertNotEqual(evil,good,(mode,'bad text differs'))
            self.assertIn(b'mov rbx, 61453',evil,(mode,evil))
            marker,captured=self._probe(mode,910,value,8,True,c['trap'],evil)
            # Normal return on the fall path: rejection is purely by the
            # captured preserved-register value.
            self.assertEqual(marker,FALL,(mode,'bad returns normally',marker))
            self.assertNotEqual(captured[3],0x1111111111111103,
                                (mode,'rbx clobber observed in capture'))
            self.assertEqual(captured[3],61453,(mode,hex(captured[3])))
            with self.assertRaisesRegex(AssertionError,'preserved'):
                self._assert_preserved(mode,920,value,captured)
        self.records.append(dict(test='bad-clobber-preserved-reg',compiled=True,native_executed=True,
                                 modes=2,rejected_by='preserved-register-value',passed=True))


if __name__=='__main__':unittest.main()
