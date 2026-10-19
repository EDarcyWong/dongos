"""Actual Dong NASM 8/16/32-bit debug narrow arithmetic range-guard emit."""
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

SOURCE=ROOT/'lang/bootstrap/nasm_narrow_range_guard.dg'
DOC=ROOT/'lang/bootstrap/nasm_narrow_range_guard.md'
CR4=WORKS/'cursor-works/src/bootstrap/decimal_integer.dg'
if not CR4.is_file():
    CR4=ROOT/'lang/bootstrap/decimal_integer.dg'
OK,INVALID,CAPACITY=0,1,2
NONE=(1<<64)-1
TOP=1<<63
WIDTHS=(8,16,32)
REGS64=[b'rax',b'rcx',b'rdx',b'rbx',b'rsp',b'rbp',b'rsi',b'rdi',
        b'r8',b'r9',b'r10',b'r11',b'r12',b'r13',b'r14',b'r15']
# RAX holds the value; R11 is intentionally clobbered by the guard.
SAFE={0,1,2,6,7,8,9,10}
FALL=111
TRAP=222
WRAPPER='''module probe.nasm_narrow_range_guard_export;
import bootstrap.nasm_narrow_range_guard as m;
export("dong_narrow_range_guard_emit") pub unsafe fn emit(
 width:u64,signed:bool,trap_block:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(width,signed,trap_block,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_narrow_range_guard_emit(uint64_t,uint8_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
   case 0:st=dong_narrow_range_guard_emit(8,1,0,o,128,NULL);break;
   case 1:st=dong_narrow_range_guard_emit(8,1,0,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_narrow_range_guard_emit(8,1,0,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_narrow_range_guard_emit(8,1,0,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_narrow_range_guard_emit(8,1,0,NULL,128,w);break;
   case 5:st=dong_narrow_range_guard_emit(8,1,0,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_narrow_range_guard_emit(8,1,0,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_narrow_range_guard_emit(8,1,0,o,0,(uint64_t*)(uintptr_t)1);break;
   case 8:st=dong_narrow_range_guard_emit(8,1,0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=dong_narrow_range_guard_emit(0,1,0,o,128,w);break;
   case 10:st=dong_narrow_range_guard_emit(64,1,0,o,128,w);break;
   case 11:st=dong_narrow_range_guard_emit(7,1,0,o,128,w);break;
   case 12:st=dong_narrow_range_guard_emit(8,1,UINT64_MAX,o,128,w);break;
   case 13:st=dong_narrow_range_guard_emit(0,1,0,o,0,w);break;
   case 14:st=dong_narrow_range_guard_emit(64,0,0,o,0,w);break;
   case 15:st=dong_narrow_range_guard_emit(128,1,0,o,0,w);break;
   default:st=dong_narrow_range_guard_emit(8,1,UINT64_MAX,o,0,w);break;
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
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);_Alignas(8) uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_narrow_range_guard_emit(width,(uint8_t)signed_f,trap,o,cap,written);
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
    """Independent CR4-shaped decimal; do not truncate to narrow width first."""
    if not signed:
        return str(raw&NONE).encode('ascii')
    return str(i64(raw)).encode('ascii')


def expected(width,signed,trap):
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


def need_total(width,signed,trap):
    return len(expected(width,signed,trap))


def py_route(value,width,signed):
    """Independent full-64-bit range check; never truncate to low width bits first."""
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


class NasmNarrowRangeGuardTests(unittest.TestCase):
    PREFLIGHTS=17

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_narrow_range_guard requires NASM/GCC')
        cls.work=WORKS/'build/test/bootstrap-nasm-narrow-range-guard'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_narrow_range_guard.dg')
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
        (wrapper/'probe/nasm_narrow_range_guard_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_narrow_range_guard_export.dg',roots=roots,mode=mode)
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
        for width in WIDTHS:
            for signed in (True,False):
                for trap in (0,1,42,TOP,NONE-1):
                    need=need_total(width,signed,trap)
                    cases+=[item(width,signed,trap),
                            item(width,signed,trap,cap=need+3),
                            item(width,signed,trap,cap=max(0,need-1))]
        max_need=need_total(32,True,NONE-1)
        self.assertEqual(max_need,131)
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
                                 preflights=self.PREFLIGHTS,max_need=max_need,passed=True))

    def test_dong_assemble_and_native_range_guard(self):
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
        self.records.append(dict(test='dong-assemble-native-range-guard',assemble_samples=len(samples),
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
        """Path marker + RAX original value and non-R11 SAFE GPR hold.

        Spill is callee-saved RBX: the guard clobbers R11, so R11 cannot hold
        the state pointer across the emitted sequence.
        """
        spill=3  # rbx — not clobbered; not in SAFE observe set
        observe=sorted(SAFE)
        expected=self._expected_regs(value,observe)
        spill_name=REGS64[spill].decode()
        lines=['bits 64','section .text','global probe_narrow_range','probe_narrow_range:',
               f' push {spill_name}',
               f' mov {spill_name}, rdi']
        for r in observe:
            if r!=0:
                lines.append(f' mov {REGS64[r].decode()}, 0x{expected[r]:x}')
        lines.append(f' mov rax, 0x{value&NONE:x}')
        lines+=text.decode('ascii').rstrip('\n').split('\n')

        def capture(marker):
            block=[]
            for i,r in enumerate(observe):
                block.append(f' mov [{spill_name}+{i*8}], {REGS64[r].decode()}')
            block+=[f' mov rax, {marker}',
                    f' mov [{spill_name}+{len(observe)*8}], rax',
                    f' pop {spill_name}',
                    ' ret']
            return block

        lines+=capture(FALL)
        lines+=[f'__dong_b{trap}:']+capture(TRAP)
        body='\n'.join(lines)+'\n'
        d=self.work/'range-guard-probe';d.mkdir(exist_ok=True)
        asm=d/f'{mode}-{index:03d}.asm';obj=d/f'{mode}-{index:03d}.o'
        exe=d/f"{mode}-{index:03d}{'.exe'if os.name=='nt'else''}"
        asm.write_text(body,encoding='utf-8')
        r=subprocess.run([str(self.nasm),'-f',self.native,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                         capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,(r.stderr,body))
        nwords=len(observe)+1
        csrc=d/f'{mode}-{index:03d}.c'
        csrc.write_text(
            '#include <stdint.h>\n#include <stdio.h>\n#include <stdalign.h>\n'
            '#ifdef _WIN32\n#include <io.h>\n#include <fcntl.h>\n#endif\n'
            'void __attribute__((sysv_abi)) probe_narrow_range(uint64_t *state);\n'
            'int main(void){\n'
            '#ifdef _WIN32\n'
            '_setmode(_fileno(stdout),_O_BINARY);\n'
            '#endif\n'
            f'alignas(16) uint64_t state[{nwords}];\n'
            f'for(int i=0;i<{nwords};i++)state[i]=0;\n'
            'probe_narrow_range(state);\n'
            f'fwrite(state,8,{nwords},stdout);\n'
            'return 0;\n}\n',encoding='utf-8')
        r=subprocess.run([str(self.cc),'-std=c11','-O2','-Wall','-Wextra','-Werror',
                          str(csrc),str(obj),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        run=subprocess.run([str(exe)],capture_output=True,timeout=30)
        self.assertEqual(run.returncode,0,(run.returncode,run.stderr,run.stdout))
        self.assertEqual(len(run.stdout),8*nwords)
        words=list(struct.unpack(f'<{nwords}Q',run.stdout))
        captured={r:words[i] for i,r in enumerate(observe)}
        marker=words[len(observe)]
        return marker,captured

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,(name,source.count(old)))
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_narrow_range_guard.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        shutil.copy2(CR4,src/'decimal_integer.dg')
        (root/'wrapper'/'probe'/'nasm_narrow_range_guard_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        # 1) Drop signed lower-bound check: min-1 alone wrongly falls.
        drop_lo_old=(' at=copy(buffer,0,"mov r11, ");\n'
                     '  at=copy(buffer,at,slice_from_raw_parts(&mindig[0],mincount));buffer[at]=10;at+=1;\n'
                     '  at=copy(buffer,at,"cmp rax, r11\\n");\n'
                     '  at=copy(buffer,at,"jl __dong_b");\n'
                     '  at=copy(buffer,at,slice_from_raw_parts(&tdig[0],tcount));buffer[at]=10;at+=1;\n'
                     '  at=copy(buffer,at,"mov r11, ");')
        drop_lo_new=' at=copy(buffer,0,"mov r11, ");'
        # 2) unsigned JA → JG: u64 max looks negative, wrongly falls.
        ja_old=' at=copy(buffer,at,"ja __dong_b");'
        ja_new=' at=copy(buffer,at,"jg __dong_b");'
        # 3) capacity early write.
        early_old=' if at>out.len{return CAPACITY;}'
        early_new=' *written=at;if at>out.len{return CAPACITY;}'
        short=item(8,True,0,cap=5)
        # min-1 for i8: -129
        signed_min_m1=( -129)&NONE
        controls=[
            ('bad-drop-signed-lo',drop_lo_old,drop_lo_new,'native-drop-lo'),
            ('bad-ja-as-jg',ja_old,ja_new,'native-ja-jg'),
            ('bad-early-written',early_old,early_new,'atomic'),
        ]
        for name,old,new,kind in controls:
            if kind=='atomic':
                self.run_both([short],name+'-good')
            elif kind=='native-drop-lo':
                good=item(8,True,90)
                for mode in self.executables:
                    marker,captured=self._probe(mode,700,signed_min_m1,8,True,90,good['text'])
                    self.assertEqual(marker,TRAP,(name,mode,'good-must-trap',marker))
                    self._assert_preserved(mode,700,signed_min_m1,captured)
            else:
                good=item(32,False,91)
                for mode in self.executables:
                    marker,captured=self._probe(mode,710,NONE,32,False,91,good['text'])
                    self.assertEqual(marker,TRAP,(name,mode,'good-u64max-trap',marker))
                    self._assert_preserved(mode,710,NONE,captured)
            for mode,exe in self.bad_build(name,old,new).items():
                if kind=='atomic':
                    with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                        self.run_cases(exe,[short],name+'-'+mode)
                elif kind=='native-drop-lo':
                    c=item(8,True,90)
                    payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(c))
                    run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stderr)
                    st,g,w=struct.unpack_from('<3Q',run.stdout,8)
                    text=run.stdout[32:32+c['cap']][:w]
                    self.assertEqual(st,0);self.assertEqual(g,1)
                    self.assertNotEqual(text,c['text'],(name,mode,text))
                    self.assertNotIn(b'jl __dong_b',text,(name,mode,text))
                    marker,captured=self._probe(mode,800,signed_min_m1,8,True,90,text)
                    self.assertEqual(marker,FALL,(name,mode,'min-1 wrongly falls',marker))
                    self._assert_preserved(mode,800,signed_min_m1,captured)
                else:
                    c=item(32,False,91)
                    payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(c))
                    run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stderr)
                    st,g,w=struct.unpack_from('<3Q',run.stdout,8)
                    text=run.stdout[32:32+c['cap']][:w]
                    self.assertEqual(st,0);self.assertEqual(g,1)
                    self.assertNotEqual(text,c['text'],(name,mode,text))
                    self.assertIn(b'jg __dong_b',text,(name,mode,text))
                    marker,captured=self._probe(mode,900,NONE,32,False,91,text)
                    self.assertEqual(marker,FALL,(name,mode,'u64max wrongly falls via jg',marker))
                    self._assert_preserved(mode,900,NONE,captured)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=kind))


if __name__=='__main__':unittest.main()
