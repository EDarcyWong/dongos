"""Actual Dong composed checked variable shift: CR21 full-RCX guard then C26 CL shift."""
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

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_checked_variable_shift.dg'
DOC=WORKS/'claude-works/src/bootstrap/nasm_checked_variable_shift.md'
DEPS=[
    ROOT/'lang/bootstrap/nasm_shift_guard.dg',
    ROOT/'lang/bootstrap/nasm_variable_shift.dg',
    ROOT/'lang/bootstrap/decimal_integer.dg',
]
OK,INVALID,CAPACITY=0,1,2
NONE=(1<<64)-1
M64=NONE
TOP=1<<63
POW32=1<<32
ONES=M64
REGS64=[b'rax',b'rcx',b'rdx',b'rbx',b'rsp',b'rbp',b'rsi',b'rdi',
        b'r8',b'r9',b'r10',b'r11',b'r12',b'r13',b'r14',b'r15']
NAMES=[r.decode() for r in REGS64]
MNEMONICS=[b'shl',b'shr',b'sar']
# Every GPR except rsp is set before the fragment and captured after it (rbx/rbp/r12..r15 included).
OBSERVED=[r for r in range(16) if r!=4]
RCX=1
RBX=3
FALL,TRAP=111,222
WRAPPER='''module probe.nasm_checked_variable_shift_export;
import bootstrap.nasm_checked_variable_shift as m;
export("dong_checked_variable_shift_emit") pub unsafe fn emit(
 operation:u64,destination:u64,trap_block:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(operation,destination,trap_block,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_checked_variable_shift_emit(uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 _Alignas(16) static uint8_t arena[4096];
 _Alignas(16) static uint8_t saved[4096];
 const unsigned total=16;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  if(i==5)memcpy(o+80,"cmp rcx, 64\njae __dong_b0\nshl rax, cl\n",34);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_checked_variable_shift_emit(0,0,0,o,128,NULL);break;
   case 1:st=dong_checked_variable_shift_emit(0,0,0,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_checked_variable_shift_emit(0,0,0,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_checked_variable_shift_emit(0,0,0,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_checked_variable_shift_emit(0,0,0,NULL,128,w);break;
   case 5:st=dong_checked_variable_shift_emit(0,0,0,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_checked_variable_shift_emit(0,0,0,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_checked_variable_shift_emit(0,0,0,o,0,(uint64_t*)(uintptr_t)1);break;
   case 8:st=dong_checked_variable_shift_emit(0,0,0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 9:st=dong_checked_variable_shift_emit(3,0,0,o,128,w);break;
   case 10:st=dong_checked_variable_shift_emit(0,4,0,o,128,w);break;
   case 11:st=dong_checked_variable_shift_emit(0,5,0,o,128,w);break;
   case 12:st=dong_checked_variable_shift_emit(0,16,0,o,128,w);break;
   case 13:st=dong_checked_variable_shift_emit(0,0,UINT64_MAX,o,128,w);break;
   case 14:st=dong_checked_variable_shift_emit(3,0,0,o,0,w);break;
   default:st=dong_checked_variable_shift_emit(0,4,UINT64_MAX,o,0,w);break;
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
  uint64_t operation=h[0],destination=h[1],trap=h[2],cap=h[3],nout=h[4];
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);_Alignas(8) uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_checked_variable_shift_emit(operation,destination,trap,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''


def expected(op,dest,trap):
    guard=b'cmp rcx, 64\njae __dong_b'+str(trap).encode('ascii')+b'\n'
    shift=MNEMONICS[op]+b' '+REGS64[dest]+b', cl\n'
    return guard+shift


def need_total(op,dest,trap):
    return len(expected(op,dest,trap))


def dest_ok(d):
    return d<=15 and d not in (4,5)


def py_route(count_val):
    return 'trap' if (count_val&NONE)>=64 else 'fall'


def py_shift(op,value,count):
    k=count&63
    if op==0:return (value<<k)&M64
    if op==1:return value>>k
    signed=value-(1<<64) if value>>63 else value
    return (signed>>k)&M64


def item(op,dest,trap,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        if op>2 or not dest_ok(dest) or trap==NONE:status=INVALID
        else:
            need=need_total(op,dest,trap)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(op,dest,trap) if status==OK else 64
    text=expected(op,dest,trap) if status==OK else None
    return dict(op=op,dest=dest,trap=trap,cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<5Q',c['op'],c['dest'],c['trap'],c['cap'],c.get('nout',0))


# (op, dest, value, count, trap) — <=24 native vectors; limited combinations.
NATIVE_VECTORS=[
    (0,0,1,0,10),                 # SHL count 0 fall
    (0,2,1,1,11),                 # SHL count 1 fall
    (0,8,1,63,12),                # SHL count 63 fall
    (0,9,3,64,13),                # SHL count 64 trap
    (0,10,5,256,14),              # SHL count 256 trap
    (0,11,7,POW32,15),            # SHL count 2^32 trap
    (0,1,3,3,16),                 # dest=RCX fall (value=count=3)
    (0,1,0x41,0x41,17),           # dest=RCX trap (65)
    (1,0,TOP,0,20),               # SHR
    (1,3,ONES,1,21),              # dest=RBX (callee-saved)
    (1,8,ONES,63,22),
    (1,9,TOP,64,23),
    (1,10,0x100,256,24),
    (2,0,TOP,1,30),               # SAR negative
    (2,2,TOP,63,31),
    (2,8,TOP,64,32),
    (2,6,0x8000000000001234,1,33),
    (2,1,TOP|0x3f,TOP|0x3f,34),   # dest=RCX large count trap
    (0,8,ONES,POW32,TOP-1),       # extended reg + large trap label
    (1,11,0xabcdef0123456789,63,100),
    (2,12,TOP|1,1,200),           # dest=R12
    (0,15,0x5,3,300),             # dest=R15
    (1,7,ONES,POW32,400),         # dest=RDI, trap
    (2,10,TOP,256,500),
]
assert len(NATIVE_VECTORS)<=24


class NasmCheckedVariableShiftTests(unittest.TestCase):
    PREFLIGHTS=16

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest('native nasm_checked_variable_shift requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C46'/('run-'+uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src'
        (cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_checked_variable_shift.dg')
        for dep in DEPS:
            shutil.copy2(dep,cls.src_root/'bootstrap'/dep.name)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8')
        cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__),*DEPS]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_checked_variable_shift_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_checked_variable_shift_export.dg',roots=roots,mode=mode)
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
        (self.work/(label+'.output')).write_bytes(run.stdout)
        (self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr.decode('utf-8','replace') if run.stderr else '')
        preflights,=struct.unpack_from('<Q',run.stdout,0)
        self.assertEqual(preflights,self.PREFLIGHTS)
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
        return {mode:self.run_cases(exe,cases,label+'-'+mode) for mode,exe in self.executables.items()}

    def test_format_boundaries_and_capacity(self):
        cases=[]
        for op in (0,1,2):
            for dest in (0,1,2,3,6,7,8,15):
                for trap in (0,1,42,TOP,NONE-1):
                    need=need_total(op,dest,trap)
                    cases+=[item(op,dest,trap),
                            item(op,dest,trap,cap=need+3),
                            item(op,dest,trap,cap=max(0,need-1))]
        max_need=need_total(2,15,NONE-1)
        self.assertEqual(max_need,57)
        cases+=[item(2,15,NONE-1),
                item(2,15,NONE-1,cap=max_need),
                item(2,15,NONE-1,cap=max_need-1),
                item(3,0,0,cap=64,status=INVALID),
                item(0,4,0,cap=64,status=INVALID),
                item(0,5,0,cap=64,status=INVALID),
                item(0,16,0,cap=64,status=INVALID),
                item(0,0,NONE,cap=64,status=INVALID),
                item(0,0,0,nout=1,cap=64,status=INVALID),
                item(3,0,0,nout=0,cap=0,status=INVALID),
                item(0,4,0,nout=0,cap=0,status=INVALID),
                item(0,0,NONE,nout=0,cap=0,status=INVALID),
                item(0,0,0,cap=0,status=CAPACITY)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_dong_assemble_and_native_checked_shift(self):
        samples=[(op,dest,trap)
                 for op in (0,1,2)
                 for dest in (0,1,2,3,6,7,8,9,10,11,12,13,14,15)
                 for trap in (dest,100+dest,TOP)]
        samples+=[(0,0,0),(2,15,NONE-1),(1,8,TOP)]
        cases=[item(o,d,t) for o,d,t in samples]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,((o,d,t),out) in enumerate(zip(samples,outs)):
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
        ncases=[item(o,d,t) for o,d,_,__,t in NATIVE_VECTORS]
        nresults=self.run_both(ncases,'native-vecs')
        probed=0
        for mode,outs in nresults.items():
            for index,(vec,out) in enumerate(zip(NATIVE_VECTORS,outs)):
                op,dest,value,count,trap=vec
                marker,captured=self._probe(mode,index,op,dest,value,count,trap,out)   # out: actual Dong text
                want=TRAP if py_route(count)=='trap' else FALL
                self.assertEqual(marker,want,(mode,index,vec,py_route(count),out,marker))
                self._assert_regs(mode,index,op,dest,value,count,marker,captured)
                probed+=1
        self.records.append(dict(test='dong-assemble-native-checked-shift',assemble_samples=len(samples),
                                 assembled=assembled,native_vectors=len(NATIVE_VECTORS),probed=probed,
                                 register_preserve=True,modes=2,formats=2,passed=True))

    def _initial_regs(self,dest,value,count):
        """Distinct values for all 15 observed GPRs; RCX holds the count (or the value when it is the target)."""
        regs={r:(0x1111111111111100+r*0x0101010101010001)&NONE for r in OBSERVED}
        regs[RCX]=count&NONE
        regs[dest]=value&NONE
        return regs

    def _assert_regs(self,mode,index,op,dest,value,count,marker,captured):
        initial=self._initial_regs(dest,value,count)
        self.assertEqual(sorted(captured),OBSERVED,(mode,index,'observed set'))
        for r in OBSERVED:
            if marker==TRAP:
                want=initial[r]
            elif r==dest:
                src=initial[dest]
                cnt=initial[RCX]
                want=py_shift(op,src,cnt)
            elif r==RCX:
                want=initial[RCX]
            else:
                want=initial[r]
            self.assertEqual(captured[r],want,
                             (mode,index,'reg%d'%r,NAMES[r],hex(captured[r]),hex(want),marker))

    def _probe(self,mode,index,op,dest,value,count,trap,text:bytes):
        """Run the given fragment natively and capture all 15 GPRs except rsp, plus rsp itself.
        The bridge saves the host callee-saved registers and keeps the state pointer in a stack slot, so every
        observed register (rbx/rbp/r12..r15 included) can hold a test value while the fragment runs. On either
        exit the 15 registers are pushed first (no register is used before capture), then copied into the state
        area, and the host ABI is restored before a normal ret."""
        initial=self._initial_regs(dest,value,count)
        n=len(OBSERVED)                                         # 15
        lines=['bits 64','section .text','global probe_checked_shift','probe_checked_shift:',
               ' push rbx',' push rbp',' push r12',' push r13',' push r14',' push r15',
               ' push rdi',                                    # state pointer slot, at [rsp] here
               f' mov [rdi+{8*(n+1)}], rsp']                   # rsp before the fragment
        for r in OBSERVED:
            lines.append(f' mov {NAMES[r]}, 0x{initial[r]:x}')
        lines+=text.decode('ascii').rstrip('\n').split('\n')

        def capture(marker):
            block=[f' push {NAMES[r]}' for r in OBSERVED]                    # [rsp+8*(n-1-i)] holds OBSERVED[i]
            block+=[f' mov rax, [rsp+{8*n}]']                                # state pointer
            for i in range(n):block+=[f' mov rbx, [rsp+{8*(n-1-i)}]',f' mov [rax+{8*i}], rbx']
            block+=[f' lea rbx, [rsp+{8*n}]',f' mov [rax+{8*(n+2)}], rbx']   # rsp after the fragment
            block+=[f' mov qword [rax+{8*n}], {marker}']
            block+=[f' add rsp, {8*(n+1)}',' pop r15',' pop r14',' pop r13',' pop r12',' pop rbp',' pop rbx',' ret']
            return block

        lines+=capture(FALL)
        lines+=[f'__dong_b{trap}:']+capture(TRAP)
        body='\n'.join(lines)+'\n'
        d=self.work/'checked-shift-probe';d.mkdir(exist_ok=True)
        asm=d/f'{mode}-{index:03d}.asm'
        obj=d/f'{mode}-{index:03d}.o'
        exe=d/f"{mode}-{index:03d}{'.exe'if os.name=='nt'else''}"
        asm.write_text(body,encoding='utf-8')
        for fmt in ('elf64','win64'):
            out_obj=obj if fmt==('win64'if os.name=='nt'else'elf64') else d/f'{mode}-{index:03d}.{fmt}.o'
            r=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(out_obj),str(asm)],
                             capture_output=True,timeout=30)
            self.assertEqual(r.returncode,0,(r.stderr,body))
        nwords=n+3
        csrc=d/f'{mode}-{index:03d}.c'
        csrc.write_text(
            '#include <stdint.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <stdalign.h>\n'
            '#ifdef _WIN32\n#include <io.h>\n#include <fcntl.h>\n#endif\n'
            'void __attribute__((sysv_abi)) probe_checked_shift(uint64_t *state);\n'
            'int main(void){\n'
            '#ifdef _WIN32\n'
            '_setmode(_fileno(stdout),_O_BINARY);\n'
            '#endif\n'
            f'alignas(16) static uint64_t state[{nwords+1}];\n'
            f'for(int i=0;i<{nwords};i++)state[i]=0;\n'
            f'state[{nwords}]=0xa5a5a5a5a5a5a5a5ull;\n'
            'probe_checked_shift(state);\n'
            f'if(state[{nwords}]!=0xa5a5a5a5a5a5a5a5ull)return 96;\n'
            f'fwrite(state,8,{nwords},stdout);\n'
            'return 0;\n}\n',encoding='utf-8')
        r=subprocess.run([str(self.cc),'-std=c11','-O2','-Wall','-Wextra','-Werror',
                          str(csrc),str(obj),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        run=subprocess.run([str(exe)],capture_output=True,timeout=30)
        self.assertEqual(run.returncode,0,(run.returncode,run.stderr,run.stdout))
        self.assertEqual(len(run.stdout),8*nwords)
        words=list(struct.unpack(f'<{nwords}Q',run.stdout))
        captured={r:words[i] for i,r in enumerate(OBSERVED)}
        marker=words[n]
        self.assertEqual(words[n+2],words[n+1],(mode,index,'native rsp preserved by the fragment'))
        return marker,captured

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8')
        self.assertEqual(source.count(old),1,(name,source.count(old)))
        root=self.work/name
        src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_checked_variable_shift.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        for dep in DEPS:
            shutil.copy2(dep,src/dep.name)
        (root/'wrapper'/'probe'/'nasm_checked_variable_shift_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def actual_text(self,label,op,dest,trap):
        """Actual Dong output of the formal debug/release executables for one input (never a Python template)."""
        outs=self.run_both([item(op,dest,trap)],label)
        return {mode:o[0] for mode,o in outs.items()}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        # Bad: guard width 64 -> 32; count=63 wrongly traps (a normal branch, no hardware fault).
        width_old=' let gs=guardm.emit(1,64,trap_block,slice_from_raw_parts(&gbuf[0],GUARD),&glen);'
        width_new=' let gs=guardm.emit(1,32,trap_block,slice_from_raw_parts(&gbuf[0],GUARD),&glen);'
        # Bad: skip guard; count=64 wrongly falls through to the masked shift.
        skip_old=(' var gbuf:[64]u8=[0;64];var glen:usize=0;\n'
                  ' let gs=guardm.emit(1,64,trap_block,slice_from_raw_parts(&gbuf[0],GUARD),&glen);\n'
                  ' if gs!=guardm.OK{return INVALID;}\n'
                  ' if glen>GUARD{return INVALID;}\n')
        skip_new=(' var gbuf:[64]u8=[0;64];var glen:usize=0;\n')
        # Bad: shift a fixed register (rbx, callee-saved and supposed to be preserved) instead of the target.
        reg_old=' let ss=shiftm.emit(operation,destination,slice_from_raw_parts(&sbuf[0],SHIFT),&slen);'
        reg_new=' let ss=shiftm.emit(operation,3,slice_from_raw_parts(&sbuf[0],SHIFT),&slen);'
        early_old=' if total>out.len{return CAPACITY;}'
        early_new=' *written=total;if total>out.len{return CAPACITY;}'
        # (name, old, new, (op, dest, value, count, trap), good route, bad route, rejection regex)
        semantic=[
            ('bad-width-32',width_old,width_new,(0,8,1,63,50),FALL,TRAP,'route'),
            ('bad-skip-guard',skip_old,skip_new,(0,8,1,64,51),TRAP,FALL,'route'),
            ('bad-shift-rbx',reg_old,reg_new,(0,8,0x0123456789abcdef,4,52),FALL,FALL,"'rbx'"),
        ]
        for index,(name,old,new,vec,good_route,bad_route,reason) in enumerate(semantic):
            op,dest,value,count,trap=vec
            good=self.actual_text(name+'-good',op,dest,trap)             # formal executables, same input first
            for mode,text in good.items():
                marker,captured=self._probe(mode,800+2*index,op,dest,value,count,trap,text)
                self.assertEqual(marker,good_route,(name,mode,'good route'))
                self._assert_regs(mode,800+2*index,op,dest,value,count,marker,captured)
            for mode,exe in self.bad_build(name,old,new).items():
                c=item(op,dest,trap,cap=64,status=OK)
                payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(c))
                run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                self.assertEqual(run.returncode,0,run.stderr)
                st,g,w=struct.unpack_from('<3Q',run.stdout,8)
                self.assertEqual((st,g),(0,1),(name,mode))
                text=run.stdout[32:32+c['cap']][:w]                          # the bad emitter's actual output
                marker,captured=self._probe(mode,801+2*index,op,dest,value,count,trap,text)   # normal execution
                self.assertEqual(marker,bad_route,(name,mode,'bad route'))
                if reason=='route':
                    self.assertNotEqual(marker,good_route,(name,mode,'route rejects the bad body'))
                else:
                    initial=self._initial_regs(dest,value,count)
                    self.assertNotEqual(captured[RBX],initial[RBX],(name,mode,'rbx changed'))
                    with self.assertRaisesRegex(AssertionError,reason):
                        self._assert_regs(mode,801+2*index,op,dest,value,count,marker,captured)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,
                                     good_side='actual Dong output of the formal executables',
                                     rejected_by='route %s instead of %s'%(bad_route,good_route)if reason=='route'
                                     else 'captured rbx value'))
        short=item(0,0,0,cap=5)
        self.run_both([short],'bad-early-written-good')
        for mode,exe in self.bad_build('bad-early-written',early_old,early_new).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                self.run_cases(exe,[short],'bad-early-written-'+mode)
        self.records.append(dict(test='bad-early-written',compiled=True,native_executed=True,modes=2,rejected_by='atomic'))

if __name__=='__main__':unittest.main()
