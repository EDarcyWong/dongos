"""Actual Dong NASM unsigned array/slice bounds-guard emit (cmp/jae)."""
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


SOURCE=ROOT/'lang/bootstrap/nasm_bounds_guard.dg'
DOC=ROOT/'lang/bootstrap/nasm_bounds_guard.md'
CR4=WORKS/'cursor-works/src/bootstrap/decimal_integer.dg'
if not CR4.is_file():
    CR4=ROOT/'lang/bootstrap/decimal_integer.dg'
OK,INVALID,CAPACITY=0,1,2
NONE=(1<<64)-1
TOP=1<<63
REGS64=[b'rax',b'rcx',b'rdx',b'rbx',b'rsp',b'rbp',b'rsi',b'rdi',
        b'r8',b'r9',b'r10',b'r11',b'r12',b'r13',b'r14',b'r15']
# Safe SysV caller-saved for native execution (no rsp/rbp/callee-saved).
SAFE={0,1,2,6,7,8,9,10,11}
FALL=111
TRAP=222
WRAPPER='''module probe.nasm_bounds_guard_export;
import bootstrap.nasm_bounds_guard as m;
export("dong_bounds_emit") pub unsafe fn emit(
 index:u64,length:u64,trap_block:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(index,length,trap_block,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_bounds_emit(uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 _Alignas(16) static uint8_t arena[4096];
 _Alignas(16) static uint8_t saved[4096];
 const unsigned total=15;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  if(i==5)memcpy(o+80,"cmp rax, rcx\njae __dong_b0\n",24);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_bounds_emit(0,1,0,o,128,NULL);break;
   case 1:st=dong_bounds_emit(0,1,0,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_bounds_emit(0,1,0,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_bounds_emit(0,1,0,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_bounds_emit(0,1,0,NULL,128,w);break;
   case 5:st=dong_bounds_emit(0,1,0,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_bounds_emit(0,1,0,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_bounds_emit(0,1,0,o,0,(uint64_t*)(uintptr_t)1);break;
   case 8:st=dong_bounds_emit(0,1,0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=dong_bounds_emit(16,1,0,o,128,w);break;
   case 10:st=dong_bounds_emit(0,16,0,o,128,w);break;
   case 11:st=dong_bounds_emit(0,1,UINT64_MAX,o,128,w);break;
   case 12:st=dong_bounds_emit(16,1,0,o,0,w);break;
   case 13:st=dong_bounds_emit(0,1,UINT64_MAX,o,0,w);break;
   default:st=dong_bounds_emit(0,16,0,o,0,w);break;
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
  uint64_t index=h[0],length=h[1],trap=h[2],cap=h[3],nout=h[4];
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);_Alignas(8) uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_bounds_emit(index,length,trap,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''


def expected(index,length,trap):
    return (b'cmp '+REGS64[index]+b', '+REGS64[length]+b'\njae __dong_b'
            +str(trap).encode('ascii')+b'\n')


def need_total(index,length,trap):
    return len(expected(index,length,trap))


def py_route(index_val,length_val):
    """Unsigned oracle: index >= length → trap, else fallthrough."""
    return 'trap' if (index_val&NONE)>=(length_val&NONE) else 'fall'


def item(index,length,trap,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        if index>15 or length>15 or trap==NONE:status=INVALID
        else:
            need=need_total(index,length,trap)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(index,length,trap) if status==OK else 64
    text=expected(index,length,trap) if status==OK else None
    return dict(index=index,length=length,trap=trap,cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<5Q',c['index'],c['length'],c['trap'],c['cap'],c.get('nout',0))


# (index_reg, length_reg, index_val, length_val, trap_block) — <=24 native vectors.
NATIVE_VECTORS=[
    (7,6,0,0,10),          # index0 == len0 → trap
    (7,6,0,5,11),          # index0 < len → fall
    (7,6,4,5,12),          # len-1 → fall
    (7,6,5,5,13),          # == → trap
    (7,6,6,5,14),          # len+1 → trap
    (7,6,TOP,NONE,15),     # 2^63 < MAX → fall (unsigned)
    (7,6,NONE,NONE,16),    # MAX==MAX → trap
    (7,6,NONE,0,17),       # MAX >= 0 → trap
    (7,6,TOP,TOP,18),      # equal high → trap
    (7,6,TOP-1,TOP,19),    # below 2^63 → fall
    (7,6,TOP,TOP-1,20),    # 2^63 > 2^63-1 → trap
    (7,6,1,0,21),          # len0 non-zero index → trap
    (8,9,0,1,22),          # r8/r9 fall
    (8,9,1,1,23),          # r8/r9 trap
    (10,11,42,100,24),     # r10/r11 fall
    (10,11,100,100,25),    # r10/r11 trap
    (0,1,3,4,26),          # rax/rcx fall
    (0,1,4,4,27),          # rax/rcx trap
    (2,8,0,1,28),          # rdx/r8 fall
    (1,2,NONE,TOP,29),     # MAX >= 2^63 → trap
    (0,0,7,7,30),          # same reg always equal → trap
    (8,8,0,0,31),          # same reg zero → trap
    (7,6,1,1,0),           # trap_block 0
    (7,6,0,1,NONE-1),      # trap_block MAX-1
]


class NasmBoundsGuardTests(unittest.TestCase):
    PREFLIGHTS=15

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_bounds_guard requires NASM/GCC')
        cls.work=WORKS/'build/test/bootstrap-nasm-bounds-guard'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_bounds_guard.dg')
        shutil.copy2(CR4,cls.src_root/'bootstrap'/'decimal_integer.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__),CR4]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_bounds_guard_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_bounds_guard_export.dg',roots=roots,mode=mode)
        asm=cls.work/(name+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
        native='win64'if os.name=='nt'else'elf64'
        obj=cls.work/(name+'.o');exe=cls.work/(name+('.exe'if os.name=='nt'else''))
        for fmt in ('elf64','win64'):
            output=obj if fmt==native else cls.work/(name+'.'+fmt+'.o')
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
        # Rotate all 16 registers as index/length pairs (not full cartesian).
        for i in range(16):
            length=(i*3+1)&15
            for trap in (0,1,42,TOP,NONE-1):
                need=need_total(i,length,trap)
                cases+=[item(i,length,trap),
                        item(i,length,trap,cap=need+3),
                        item(i,length,trap,cap=max(0,need-1))]
            # same-register form
            cases+=[item(i,i,7)]
        # Exact max-length capacity (46) and need-1 (45) for same-reg + 20-digit trap.
        max_need=need_total(15,15,NONE-1)
        self.assertEqual(max_need,46)
        cases+=[item(15,15,NONE-1),
                item(15,15,NONE-1,cap=max_need),
                item(15,15,NONE-1,cap=max_need-1),
                item(16,0,0,cap=64,status=INVALID),
                item(0,16,0,cap=64,status=INVALID),
                item(0,1,NONE,cap=64,status=INVALID),
                item(0,1,0,nout=1,cap=64,status=INVALID),
                item(16,0,0,nout=0,cap=0,status=INVALID),
                item(0,16,0,nout=0,cap=0,status=INVALID),
                item(0,1,NONE,nout=0,cap=0,status=INVALID),
                item(0,1,0,cap=0,status=CAPACITY)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_dong_assemble_and_native_bounds(self):
        self.assertLessEqual(len(NATIVE_VECTORS),24)
        # Text/assemble: rotating pairs across all 16 regs + same-reg + boundary traps.
        samples=[]
        for i in range(16):
            samples.append((i,(i+5)&15,i+100))
            samples.append((i,i,200+i))
        samples+=[(0,1,0),(7,6,NONE-1),(8,9,TOP)]
        cases=[item(a,b,t)for a,b,t in samples]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,((a,b,t),out) in enumerate(zip(samples,outs)):
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
        ncases=[item(a,b,t)for a,b,_,__,t in NATIVE_VECTORS]
        nresults=self.run_both(ncases,'native-vecs')
        probed=0
        for mode,outs in nresults.items():
            for index,(vec,out) in enumerate(zip(NATIVE_VECTORS,outs)):
                ireg,lreg,ival,lval,trap=vec
                self.assertTrue(ireg in SAFE and lreg in SAFE,(mode,index,ireg,lreg))
                marker,captured=self._probe(mode,index,ireg,lreg,ival,lval,trap,out)
                want=TRAP if py_route(ival,lval)=='trap' else FALL
                self.assertEqual(marker,want,(mode,index,vec,py_route(ival,lval),out,marker))
                self._assert_preserved(mode,index,ireg,lreg,ival,lval,captured)
                probed+=1
        self.records.append(dict(test='dong-assemble-native-bounds',assemble_samples=len(samples),
                                 assembled=assembled,native_vectors=len(NATIVE_VECTORS),probed=probed,
                                 register_preserve=True,modes=2,formats=2,passed=True))

    def _expected_regs(self,ireg,lreg,ival,lval,observe):
        expected={}
        for r in observe:
            if r==ireg:expected[r]=ival&NONE
            elif r==lreg:expected[r]=lval&NONE
            else:expected[r]=0x1111111111111100+r
        return expected

    def _assert_preserved(self,mode,index,ireg,lreg,ival,lval,captured):
        expected=self._expected_regs(ireg,lreg,ival,lval,sorted(captured))
        for r,want in expected.items():
            self.assertEqual(captured[r],want,
                             (mode,index,'reg%d preserved'%r,REGS64[r].decode(),
                              hex(captured[r]),hex(want)))

    def _probe(self,mode,index,ireg,lreg,ival,lval,trap,text:bytes):
        """Native path marker + capture of inputs and other controlled SAFE GPRs.

        Marker is written to an independent state slot after register capture, so an
        RAX input is never overwritten before observation. State pointer lives in a
        non-input spill register chosen from SAFE.
        """
        used={ireg,lreg}
        spill=next(r for r in (11,10,9,8,2,1,6,7,0) if r not in used)
        observe=sorted(SAFE-{spill})
        expected=self._expected_regs(ireg,lreg,ival,lval,observe)
        spill_name=REGS64[spill].decode()
        lines=['bits 64','section .text','global probe_bounds','probe_bounds:',
               f' mov {spill_name}, rdi']
        for r in observe:
            if r not in (ireg,lreg):
                lines.append(f' mov {REGS64[r].decode()}, 0x{expected[r]:x}')
        if ireg==lreg:
            lines.append(f' mov {REGS64[ireg].decode()}, 0x{ival&NONE:x}')
        else:
            lines.append(f' mov {REGS64[ireg].decode()}, 0x{ival&NONE:x}')
            lines.append(f' mov {REGS64[lreg].decode()}, 0x{lval&NONE:x}')
        lines+=text.decode('ascii').rstrip('\n').split('\n')

        def capture(marker):
            block=[]
            for i,r in enumerate(observe):
                block.append(f' mov [{spill_name}+{i*8}], {REGS64[r].decode()}')
            block+=[f' mov rax, {marker}',
                    f' mov [{spill_name}+{len(observe)*8}], rax',
                    ' ret']
            return block

        lines+=capture(FALL)
        lines+=[f'__dong_b{trap}:']+capture(TRAP)
        body='\n'.join(lines)+'\n'
        d=self.work/'bounds-probe';d.mkdir(exist_ok=True)
        asm=d/f'{mode}-{index:03d}.asm';obj=d/f'{mode}-{index:03d}.o'
        exe=d/f"{mode}-{index:03d}{'.exe'if os.name=='nt'else''}"
        asm.write_text(body,encoding='utf-8')
        native='win64'if os.name=='nt'else'elf64'
        r=subprocess.run([str(self.nasm),'-f',native,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                         capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,(r.stderr,body))
        nwords=len(observe)+1
        csrc=d/f'{mode}-{index:03d}.c'
        csrc.write_text(
            '#include <stdint.h>\n#include <stdio.h>\n#include <stdalign.h>\n'
            '#ifdef _WIN32\n#include <io.h>\n#include <fcntl.h>\n#endif\n'
            'void __attribute__((sysv_abi)) probe_bounds(uint64_t *state);\n'
            'int main(void){\n'
            '#ifdef _WIN32\n'
            '_setmode(_fileno(stdout),_O_BINARY);\n'
            '#endif\n'
            f'alignas(16) uint64_t state[{nwords}];\n'
            f'for(int i=0;i<{nwords};i++)state[i]=0;\n'
            'probe_bounds(state);\n'
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
        (src/'nasm_bounds_guard.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        shutil.copy2(CR4,src/'decimal_integer.dg')
        (root/'wrapper'/'probe'/'nasm_bounds_guard_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        # jae → ja: index==len must trap for good, fallthrough for bad.
        jae_old=' at=copy(buffer,at,"jae __dong_b");'
        jae_new=' at=copy(buffer,at,"ja __dong_b");'
        # After CMP, clobber rdi without touching flags; route stays fallthrough.
        clobber_old=' at=copy(buffer,at+2,register(length));buffer[at]=10;at+=1;\n at=copy(buffer,at,"jae __dong_b");'
        clobber_new=(' at=copy(buffer,at+2,register(length));buffer[at]=10;at+=1;\n'
                     ' at=copy(buffer,at,"mov rdi, 0\\n");\n'
                     ' at=copy(buffer,at,"jae __dong_b");')
        early_old=' if at>out.len{return CAPACITY;}'
        early_new=' *written=at;if at>out.len{return CAPACITY;}'
        short=item(0,1,0,cap=5)
        equal=item(7,6,40)  # text only; native uses index==len values
        # Cap must fit the longer clobber text (extra "mov rdi, 0\n").
        fall_hold=item(7,6,41,cap=need_total(7,6,41)+16)
        controls=[
            ('bad-jae-as-ja',jae_old,jae_new,'native-route'),
            ('bad-clobber-rdi',clobber_old,clobber_new,'native-hold'),
            ('bad-early-written',early_old,early_new,'atomic'),
        ]
        for name,old,new,kind in controls:
            if kind=='atomic':
                self.run_both([short],name+'-good')
            elif kind=='native-hold':
                # Good emitter: index=3 < length=5 → FALL and rdi stays 3.
                good_text=expected(7,6,41)
                for mode in self.executables:
                    marker,captured=self._probe(mode,800,7,6,3,5,41,good_text)
                    self.assertEqual(marker,FALL,(name,mode,'good-route',marker))
                    self._assert_preserved(mode,800,7,6,3,5,captured)
            else:
                self.run_both([equal],name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                if kind=='atomic':
                    with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                        self.run_cases(exe,[short],name+'-'+mode)
                elif kind=='native-hold':
                    c=fall_hold
                    payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(c))
                    run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stderr)
                    st,g,w=struct.unpack_from('<3Q',run.stdout,8)
                    text=run.stdout[32:32+c['cap']][:w]
                    self.assertEqual(st,0);self.assertEqual(g,1)
                    self.assertNotEqual(text,c['text'],(name,mode,text))
                    self.assertIn(b'mov rdi, 0',text,(name,mode,text))
                    marker,captured=self._probe(mode,900+hash(name)%100,7,6,3,5,41,text)
                    # Route still fallthrough; rdi clobber is what the hold assert rejects.
                    self.assertEqual(marker,FALL,(name,mode,'bad-route-still-fall',marker))
                    with self.assertRaisesRegex(AssertionError,r'reg7 preserved'):
                        self._assert_preserved(mode,900,7,6,3,5,captured)
                else:
                    # Emit with rdi/rsi and trap 40; run index==len=5 → good traps, bad falls.
                    c=item(7,6,40)
                    payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(c))
                    run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stderr)
                    st,g,w=struct.unpack_from('<3Q',run.stdout,8)
                    text=run.stdout[32:32+c['cap']][:w]
                    self.assertEqual(st,0);self.assertEqual(g,1)
                    self.assertNotEqual(text,c['text'],(name,mode,text))
                    marker,captured=self._probe(mode,900+hash(name)%100,7,6,5,5,40,text)
                    # Good would return TRAP; bad ja falls through → FALL.
                    self.assertEqual(marker,FALL,(name,mode,marker))
                    self.assertNotEqual(marker,TRAP,(name,mode,marker))
                    self._assert_preserved(mode,900,7,6,5,5,captured)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=kind))


if __name__=='__main__':unittest.main()
