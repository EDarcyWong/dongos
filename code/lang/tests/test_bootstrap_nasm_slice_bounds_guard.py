"""Actual Dong NASM slice lo/hi/len joint unsigned bounds-guard emit."""
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


SOURCE=ROOT/'lang/bootstrap/nasm_slice_bounds_guard.dg'
DOC=ROOT/'lang/bootstrap/nasm_slice_bounds_guard.md'
CR4=WORKS/'cursor-works/src/bootstrap/decimal_integer.dg'
if not CR4.is_file():
    CR4=ROOT/'lang/bootstrap/decimal_integer.dg'
OK,INVALID,CAPACITY=0,1,2
NONE=(1<<64)-1
TOP=1<<63
REGS64=[b'rax',b'rcx',b'rdx',b'rbx',b'rsp',b'rbp',b'rsi',b'rdi',
        b'r8',b'r9',b'r10',b'r11',b'r12',b'r13',b'r14',b'r15']
# Fixed: RDI=lo(7), RSI=hi(6), RDX=len(2). Observe these + other SAFE GPRs.
SAFE={0,1,2,6,7,8,9,10,11}
FALL=111
TRAP=222
WRAPPER='''module probe.nasm_slice_bounds_guard_export;
import bootstrap.nasm_slice_bounds_guard as m;
export("dong_slice_bounds_guard_emit") pub unsafe fn emit(
 trap_block:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(trap_block,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_slice_bounds_guard_emit(uint64_t,uint8_t*,uint64_t,uint64_t*);
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
  if(i==5)memcpy(o+80,"cmp rsi, rdx\n",13);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_slice_bounds_guard_emit(0,o,128,NULL);break;
   case 1:st=dong_slice_bounds_guard_emit(0,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_slice_bounds_guard_emit(0,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_slice_bounds_guard_emit(0,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_slice_bounds_guard_emit(0,NULL,128,w);break;
   case 5:st=dong_slice_bounds_guard_emit(0,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_slice_bounds_guard_emit(0,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_slice_bounds_guard_emit(0,o,0,(uint64_t*)(uintptr_t)1);break;
   case 8:st=dong_slice_bounds_guard_emit(0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=dong_slice_bounds_guard_emit(UINT64_MAX,o,128,w);break;
   case 10:st=dong_slice_bounds_guard_emit(UINT64_MAX,o,0,w);break;
   default:st=dong_slice_bounds_guard_emit(UINT64_MAX,NULL,0,w);break;
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
  uint64_t trap=h[0],cap=h[1],nout=h[2];
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);_Alignas(8) uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_slice_bounds_guard_emit(trap,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''


def expected(trap):
    t=str(trap).encode('ascii')
    return (b'cmp rsi, rdx\n'
            b'ja __dong_b'+t+b'\n'
            b'cmp rdi, rsi\n'
            b'ja __dong_b'+t+b'\n')


def need_total(trap):
    return len(expected(trap))


def py_route(lo,hi,length):
    """Independent full-64-bit unsigned: fall iff lo<=hi<=len."""
    lo&=NONE;hi&=NONE;length&=NONE
    return 'fall' if lo<=hi<=length else 'trap'


def which_edge(lo,hi,length):
    """Which JA fires first (for independent path coverage)."""
    lo&=NONE;hi&=NONE;length&=NONE
    if hi>length:return 'hi_gt_len'
    if lo>hi:return 'lo_gt_hi'
    return 'ok'


def item(trap,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        if trap==NONE:status=INVALID
        else:
            need=need_total(trap)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(trap) if status==OK else 64
    text=expected(trap) if status==OK else None
    return dict(trap=trap,cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<3Q',c['trap'],c['cap'],c.get('nout',0))


# (lo, hi, len, trap) — 16 vectors covering both failure edges independently.
NATIVE_VECTORS=[
    (0,0,0,10),                 # all-zero empty
    (1,5,10,11),                # nonempty valid
    (0,0,10,12),                # empty at start
    (5,5,10,13),                # empty at end
    (3,10,10,14),               # hi==len
    (0,10,10,15),               # hi==len from 0
    (1,11,10,16),               # hi>len, lo<=hi → edge1
    (5,3,10,17),                # lo>hi, hi<=len → edge2
    (8,5,3,18),                 # both bad (first edge wins)
    (5,8,3,19),                 # hi>len, lo<=hi → edge1
    (TOP-1,TOP,NONE,20),        # high-bit fall
    (TOP,TOP-1,NONE,21),        # lo>hi, hi<=len → edge2
    (0,NONE,NONE-1,22),         # hi>len → edge1
    (NONE,NONE,NONE,23),        # max equal fall
    (1,1,0,24),                 # hi>len → edge1
    (2,2,2,25),                 # equal nonempty fall
]
assert len(NATIVE_VECTORS)<=16
assert any(which_edge(lo,hi,ln)=='hi_gt_len' for lo,hi,ln,_ in NATIVE_VECTORS)
assert any(which_edge(lo,hi,ln)=='lo_gt_hi' for lo,hi,ln,_ in NATIVE_VECTORS)


class NasmSliceBoundsGuardTests(unittest.TestCase):
    PREFLIGHTS=12

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_slice_bounds_guard requires NASM/GCC')
        cls.work=WORKS/'build/test/bootstrap-nasm-slice-bounds-guard'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_slice_bounds_guard.dg')
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
        (wrapper/'probe/nasm_slice_bounds_guard_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_slice_bounds_guard_export.dg',roots=roots,mode=mode)
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
        for trap in (0,1,42,TOP,NONE-1):
            need=need_total(trap)
            cases+=[item(trap),item(trap,cap=need+3),item(trap,cap=max(0,need-1))]
        max_need=need_total(NONE-1)
        self.assertEqual(max_need,90)
        cases+=[item(NONE-1),
                item(NONE-1,cap=max_need),
                item(NONE-1,cap=max_need-1),
                item(NONE,cap=64,status=INVALID),
                item(0,nout=1,cap=64,status=INVALID),
                item(NONE,nout=0,cap=0,status=INVALID),
                item(0,cap=0,status=CAPACITY)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,max_need=max_need,passed=True))

    def test_dong_assemble_and_native_slice_bounds(self):
        samples=[0,1,42,100,TOP,NONE-1]
        cases=[item(t)for t in samples]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,(t,out) in enumerate(zip(samples,outs)):
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
        ncases=[item(t)for *_,t in NATIVE_VECTORS]
        nresults=self.run_both(ncases,'native-vecs')
        probed=0
        edges_seen=set()
        for mode,outs in nresults.items():
            for index,(vec,out) in enumerate(zip(NATIVE_VECTORS,outs)):
                lo,hi,ln,trap=vec
                marker,captured=self._probe(mode,index,lo,hi,ln,trap,out)
                want=TRAP if py_route(lo,hi,ln)=='trap' else FALL
                self.assertEqual(marker,want,(mode,index,vec,py_route(lo,hi,ln),which_edge(lo,hi,ln),out,marker))
                self._assert_preserved(mode,index,lo,hi,ln,captured)
                edges_seen.add(which_edge(lo,hi,ln))
                probed+=1
        self.assertIn('hi_gt_len',edges_seen)
        self.assertIn('lo_gt_hi',edges_seen)
        self.assertIn('ok',edges_seen)
        self.records.append(dict(test='dong-assemble-native-slice-bounds',assemble_samples=len(samples),
                                 assembled=assembled,native_vectors=len(NATIVE_VECTORS),probed=probed,
                                 edges=sorted(edges_seen),register_preserve=True,modes=2,formats=2,passed=True))

    def _expected_regs(self,lo,hi,ln,observe):
        expected={}
        for r in observe:
            if r==7:expected[r]=lo&NONE
            elif r==6:expected[r]=hi&NONE
            elif r==2:expected[r]=ln&NONE
            else:expected[r]=0x1111111111111100+r
        return expected

    def _assert_preserved(self,mode,index,lo,hi,ln,captured):
        expected=self._expected_regs(lo,hi,ln,sorted(captured))
        for r,want in expected.items():
            self.assertEqual(captured[r],want,
                             (mode,index,'reg%d preserved'%r,REGS64[r].decode(),
                              hex(captured[r]),hex(want)))

    def _probe(self,mode,index,lo,hi,ln,trap,text:bytes):
        """Path marker + all SAFE GPR hold (only flags may change)."""
        spill=3  # rbx callee-saved spill for state pointer
        observe=sorted(SAFE)
        expected=self._expected_regs(lo,hi,ln,observe)
        spill_name=REGS64[spill].decode()
        lines=['bits 64','section .text','global probe_slice_bounds','probe_slice_bounds:',
               f' push {spill_name}',
               f' mov {spill_name}, rdi']
        for r in observe:
            lines.append(f' mov {REGS64[r].decode()}, 0x{expected[r]:x}')
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
        d=self.work/'slice-bounds-probe';d.mkdir(exist_ok=True)
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
            'void __attribute__((sysv_abi)) probe_slice_bounds(uint64_t *state);\n'
            'int main(void){\n'
            '#ifdef _WIN32\n'
            '_setmode(_fileno(stdout),_O_BINARY);\n'
            '#endif\n'
            f'alignas(16) uint64_t state[{nwords}];\n'
            f'for(int i=0;i<{nwords};i++)state[i]=0;\n'
            'probe_slice_bounds(state);\n'
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
        (src/'nasm_slice_bounds_guard.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        shutil.copy2(CR4,src/'decimal_integer.dg')
        (root/'wrapper'/'probe'/'nasm_slice_bounds_guard_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        # Bad1: first JA → JAE; legal hi==len wrongly traps.
        ja1_old=(' at=copy(buffer,0,"cmp rsi, rdx\\n");\n'
                 ' at=copy(buffer,at,"ja __dong_b");')
        ja1_new=(' at=copy(buffer,0,"cmp rsi, rdx\\n");\n'
                 ' at=copy(buffer,at,"jae __dong_b");')
        # Bad2: remove second JA; lo>hi but hi<=len wrongly falls.
        ja2_old=(' at=copy(buffer,at,"cmp rdi, rsi\\n");\n'
                 ' at=copy(buffer,at,"ja __dong_b");\n'
                 ' at=copy(buffer,at,slice_from_raw_parts(&digits[0],count));buffer[at]=10;at+=1;')
        ja2_new=' at=copy(buffer,at,"cmp rdi, rsi\\n");'
        early_old=' if at>out.len{return CAPACITY;}'
        early_new=' *written=at;if at>out.len{return CAPACITY;}'
        short=item(0,cap=5)
        controls=[
            ('bad-first-ja-as-jae',ja1_old,ja1_new,'native-jae'),
            ('bad-drop-second-ja',ja2_old,ja2_new,'native-drop2'),
            ('bad-early-written',early_old,early_new,'atomic'),
        ]
        for name,old,new,kind in controls:
            if kind=='atomic':
                self.run_both([short],name+'-good')
            elif kind=='native-jae':
                # hi==len must fall for good.
                good=item(90)
                for mode in self.executables:
                    marker,captured=self._probe(mode,700,3,10,10,90,good['text'])
                    self.assertEqual(marker,FALL,(name,mode,'good-hi-eq-len',marker))
                    self._assert_preserved(mode,700,3,10,10,captured)
            else:
                # lo>hi, hi<=len must trap for good.
                good=item(91)
                for mode in self.executables:
                    marker,captured=self._probe(mode,710,5,3,10,91,good['text'])
                    self.assertEqual(marker,TRAP,(name,mode,'good-lo-gt-hi',marker))
                    self._assert_preserved(mode,710,5,3,10,captured)
            for mode,exe in self.bad_build(name,old,new).items():
                if kind=='atomic':
                    with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                        self.run_cases(exe,[short],name+'-'+mode)
                elif kind=='native-jae':
                    # jae is 1 byte longer than ja; give headroom so emit succeeds.
                    c=item(90,cap=need_total(90)+16)
                    payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(c))
                    run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stderr)
                    st,g,w=struct.unpack_from('<3Q',run.stdout,8)
                    text=run.stdout[32:32+c['cap']][:w]
                    self.assertEqual(st,0);self.assertEqual(g,1)
                    self.assertNotEqual(text,expected(90),(name,mode,text))
                    self.assertIn(b'jae __dong_b',text,(name,mode,text))
                    marker,captured=self._probe(mode,800,3,10,10,90,text)
                    self.assertEqual(marker,TRAP,(name,mode,'hi==len wrongly traps',marker))
                    self._assert_preserved(mode,800,3,10,10,captured)
                else:
                    c=item(91)
                    payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(c))
                    run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stderr)
                    st,g,w=struct.unpack_from('<3Q',run.stdout,8)
                    text=run.stdout[32:32+c['cap']][:w]
                    self.assertEqual(st,0);self.assertEqual(g,1)
                    self.assertNotEqual(text,c['text'],(name,mode,text))
                    # Only one ja left (first); second ja removed.
                    self.assertEqual(text.count(b'ja __dong_b'),1,(name,mode,text))
                    marker,captured=self._probe(mode,900,5,3,10,91,text)
                    self.assertEqual(marker,FALL,(name,mode,'lo>hi wrongly falls',marker))
                    self._assert_preserved(mode,900,5,3,10,captured)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=kind))


if __name__=='__main__':unittest.main()
