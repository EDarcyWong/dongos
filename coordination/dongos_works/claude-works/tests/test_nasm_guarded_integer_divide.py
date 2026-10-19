"""Actual Dong composed guarded integer divide: C31 guard + CR18 label + CR19 kernel."""
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

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_guarded_integer_divide.dg'
DOC=WORKS/'claude-works/src/bootstrap/nasm_guarded_integer_divide.md'
DEPS=[
    ROOT/'lang/bootstrap/nasm_division_guard.dg',
    ROOT/'lang/bootstrap/nasm_block_emit.dg',
    ROOT/'lang/bootstrap/nasm_integer_divide.dg',
    ROOT/'lang/bootstrap/decimal_integer.dg',
]
OK,INVALID,CAPACITY=0,1,2
NONE=M64=(1<<64)-1
TOP=1<<63
SMAX=TOP-1
NAMES=['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi','r8','r9','r10','r11','r12','r13','r14','r15']
OBSERVED=[r for r in range(16) if r!=4]   # every GPR except rsp (rsp is compared before/after separately)
RAX,RCX,RDX,RBX,RSI,RDI=0,1,2,3,6,7
SUCCESS_MARK=111
ZERO_MARK=222
OVERFLOW_MARK=333
WRAPPER='''module probe.nasm_guarded_integer_divide_export;
import bootstrap.nasm_guarded_integer_divide as m;
export("dong_guarded_integer_divide_emit") pub unsafe fn emit(
 signed:bool,remainder:bool,zero_target:u64,overflow_target:u64,success_block:u64,
 out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(signed,remainder,zero_target,overflow_target,success_block,
  slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_guarded_integer_divide_emit(uint8_t,uint8_t,uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 _Alignas(16) static uint8_t arena[8192];
 _Alignas(16) static uint8_t saved[8192];
 const unsigned total=14;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+4096);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  if(i==5)memcpy(o+200,"test rsi, rsi\n",14);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_guarded_integer_divide_emit(1,0,1,2,3,o,512,NULL);break;
   case 1:st=dong_guarded_integer_divide_emit(1,0,1,2,3,o,512,(uint64_t*)(arena+4097));break;
   case 2:st=dong_guarded_integer_divide_emit(1,0,1,2,3,o,512,(uint64_t*)(o+8));break;
   case 3:st=dong_guarded_integer_divide_emit(1,0,1,2,3,o,512,(uint64_t*)(o+504));break;
   case 4:st=dong_guarded_integer_divide_emit(1,0,1,2,3,NULL,512,w);break;
   case 5:st=dong_guarded_integer_divide_emit(1,0,1,2,3,o,600,(uint64_t*)(o+200));break;
   case 6:st=dong_guarded_integer_divide_emit(1,0,1,2,3,FAKE(UINT64_MAX-7),512,w);break;
   case 7:st=dong_guarded_integer_divide_emit(1,0,1,2,3,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 8:st=dong_guarded_integer_divide_emit(1,0,UINT64_MAX,2,3,o,512,w);break;
   case 9:st=dong_guarded_integer_divide_emit(1,0,1,UINT64_MAX,3,o,512,w);break;
   case 10:st=dong_guarded_integer_divide_emit(1,0,1,2,UINT64_MAX,o,512,w);break;
   case 11:st=dong_guarded_integer_divide_emit(1,0,1,1,3,o,512,w);break;
   case 12:st=dong_guarded_integer_divide_emit(1,0,1,2,1,o,0,w);break;
   default:st=dong_guarded_integer_divide_emit(0,0,5,5,6,o,0,w);break;
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
  uint64_t h[7];read_exact(h,sizeof(h));
  uint64_t sg=h[0],rem=h[1],z=h[2],o=h[3],s=h[4],cap=h[5],nout=h[6];
  if(cap>1024)exit(94);
  uint8_t*out=malloc(cap+64);_Alignas(8) uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*op=nout?NULL:out+32;
  uint64_t st=dong_guarded_integer_divide_emit((uint8_t)sg,(uint8_t)rem,z,o,s,op,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''


def expected_guard(signed,z,o,s):
    if not signed:
        return ('test rsi, rsi\njz __dong_b%d\njmp __dong_b%d\n'%(z,s)).encode()
    return ('test rsi, rsi\njz __dong_b%d\ncmp rsi, -1\njne __dong_b%d\n'
            'mov rax, 0x8000000000000000\ncmp rdi, rax\nje __dong_b%d\njmp __dong_b%d\n'
            %(z,s,o,s)).encode()


def expected_div(signed,remainder):
    head=b'mov rax, rdi\nmov rcx, rsi\n'
    mid=b'cqo\nidiv rcx\n' if signed else b'xor edx, edx\ndiv rcx\n'
    tail=b'mov rax, rdx\n' if remainder else b''
    return head+mid+tail


def expected(signed,remainder,z,o,s):
    return expected_guard(signed,z,o,s)+('__dong_b%d:\n'%s).encode()+expected_div(signed,remainder)


def need_total(signed,remainder,z,o,s):
    return len(expected(signed,remainder,z,o,s))


def labels_ok(z,o,s):
    return z!=NONE and o!=NONE and s!=NONE and z!=o and z!=s and o!=s


def route(signed,a,b):
    if b==0:return 'zero'
    if signed and b==M64 and a==TOP:return 'overflow'
    return 'success'


def py_div(a,b,signed,remainder):
    if signed:
        sa=a if a<TOP else a-(1<<64)
        sb=b if b<TOP else b-(1<<64)
        q=abs(sa)//abs(sb)
        if (sa<0)!=(sb<0):q=-q
        r=sa-q*sb
        return (r if remainder else q)&M64
    q=a//b
    r=a-q*b
    return (r if remainder else q)&M64


def item(signed,remainder,z,o,s,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        if not labels_ok(z,o,s):status=INVALID
        else:
            need=need_total(signed,remainder,z,o,s)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_total(signed,remainder,z,o,s) if status==OK else 256
    text=expected(signed,remainder,z,o,s) if status==OK else None
    return dict(sg=int(bool(signed)),rem=int(bool(remainder)),z=z,o=o,s=s,
                cap=cap,nout=nout,status=status,text=text)


def pack_case(c):
    return struct.pack('<7Q',c['sg'],c['rem'],c['z'],c['o'],c['s'],c['cap'],c.get('nout',0))


# (signed, rem, a, b, z, o, s) — <=24; distinct labels; cover success + both exception edges.
NATIVE_VECTORS=[
    (1,0,7,2,10,11,12),            # signed quot +/−
    (1,1,7,2,13,14,15),            # signed rem
    (1,0,(-7)&M64,3,16,17,18),     # neg/pos toward-zero
    (1,1,7,(-3)&M64,19,20,21),
    (1,0,TOP,1,22,23,24),          # MIN/1 success
    (1,1,TOP,3,25,26,27),
    (1,0,SMAX,M64,28,29,30),       # pos / -1
    (1,0,7,0,31,32,33),            # zero divisor
    (1,0,TOP,M64,34,35,36),        # MIN/-1 overflow
    (1,0,TOP,0,37,38,39),          # zero with MIN dividend
    (0,0,M64,1,40,41,42),          # unsigned max
    (0,1,M64,2,43,44,45),
    (0,0,TOP,TOP,46,47,48),
    (0,1,100,7,49,50,51),
    (0,0,7,0,52,53,54),            # unsigned zero
    (0,0,0,1,55,56,57),
    (1,0,9,3,58,59,2**40),         # large success label
    (1,1,(-9)&M64,4,60,61,62),
    (0,0,1,M64,63,64,65),
    (1,0,TOP|1,M64,66,67,68),      # not overflow (not exact MIN/-1)
    (1,0,5,TOP,69,70,71),
    (0,1,0,M64,72,73,74),
    (1,1,TOP,1,75,76,NONE-1),      # large success
    (0,0,123456789,98765,80,81,82),
]
assert len(NATIVE_VECTORS)<=24
assert all(labels_ok(z,o,s) for *_,z,o,s in NATIVE_VECTORS)


class NasmGuardedIntegerDivideTests(unittest.TestCase):
    PREFLIGHTS=14

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest('native nasm_guarded_integer_divide requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C47'/('run-'+uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src'
        (cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_guarded_integer_divide.dg')
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
        (wrapper/'probe/nasm_guarded_integer_divide_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_guarded_integer_divide_export.dg',roots=roots,mode=mode)
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
        for sg in (0,1):
            for rem in (0,1):
                for z,o,s in ((1,2,3),(0,10,99),(100,1000,10**19),(M64-1,TOP,7)):
                    need=need_total(sg,rem,z,o,s)
                    cases+=[item(sg,rem,z,o,s),
                            item(sg,rem,z,o,s,cap=need+9),
                            item(sg,rem,z,o,s,cap=max(0,need-1))]
        max_need=need_total(1,1,M64-1,M64-2,M64-3)
        self.assertLessEqual(max_need,287)
        cases+=[item(1,1,M64-1,M64-2,M64-3),
                item(1,1,M64-1,M64-2,M64-3,cap=max_need),
                item(1,1,M64-1,M64-2,M64-3,cap=max_need-1),
                item(1,0,NONE,2,3,cap=256,status=INVALID),
                item(1,0,1,NONE,3,cap=256,status=INVALID),
                item(1,0,1,2,NONE,cap=256,status=INVALID),
                item(1,0,1,1,3,cap=256,status=INVALID),
                item(1,0,1,2,1,cap=256,status=INVALID),
                item(0,0,5,6,5,cap=256,status=INVALID),
                item(1,0,1,2,3,nout=1,cap=256,status=INVALID),
                item(1,0,NONE,2,3,nout=0,cap=0,status=INVALID),
                item(1,0,1,1,3,nout=0,cap=0,status=INVALID),
                item(1,0,1,2,3,cap=0,status=CAPACITY)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,max_need=max_need,passed=True))

    def test_dong_assemble_and_native_guarded_divide(self):
        samples=[(sg,rem,z,o,s)
                 for sg in (0,1) for rem in (0,1)
                 for z,o,s in ((1,2,3),(10,20,30),(100,200,300),(M64-3,M64-2,M64-1))]
        cases=[item(sg,rem,z,o,s) for sg,rem,z,o,s in samples]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,((sg,rem,z,o,s),out) in enumerate(zip(samples,outs)):
                self.assertIsNotNone(out,(mode,index))
                body=(b'bits 64\nsection .text\n'+out+
                      b'mov rax, 1\n ret\n'+
                      ('__dong_b%d:\n mov rax, 2\n ret\n'%z).encode()+
                      ('__dong_b%d:\n mov rax, 3\n ret\n'%o).encode())
                for fmt in ('elf64','win64'):
                    asm=asm_dir/f'{mode}-{index:03d}-{fmt}.asm'
                    obj=asm_dir/f'{mode}-{index:03d}-{fmt}.o'
                    asm.write_bytes(body)
                    runc=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                        capture_output=True,timeout=30)
                    self.assertEqual(runc.returncode,0,(mode,index,fmt,runc.stderr,out))
                    assembled+=1
        ncases=[item(sg,rem,z,o,s) for sg,rem,_,_,z,o,s in NATIVE_VECTORS]
        nresults=self.run_both(ncases,'native-vecs')
        probed=0
        for mode,outs in nresults.items():
            for index,(vec,out) in enumerate(zip(NATIVE_VECTORS,outs)):
                sg,rem,a,b,z,o,s=vec
                marker,rax,preserved=self._probe(mode,index,a,b,z,o,s,out)
                kind=route(sg,a,b)
                if kind=='zero':
                    self.assertEqual(marker,ZERO_MARK,(mode,index,vec,marker))
                elif kind=='overflow':
                    self.assertEqual(marker,OVERFLOW_MARK,(mode,index,vec,marker))
                else:
                    self.assertEqual(marker,SUCCESS_MARK,(mode,index,vec,marker))
                    self.assertEqual(rax,py_div(a,b,sg,rem),(mode,index,vec,rax))
                self.assert_preserved(mode,index,marker,a,b,preserved)
                probed+=1
        self.records.append(dict(test='dong-assemble-native-guarded-divide',assemble_samples=len(samples),
                                 assembled=assembled,native_vectors=len(NATIVE_VECTORS),probed=probed,
                                 modes=2,formats=2,passed=True))

    @staticmethod
    def initial_regs(a,b):
        """Distinct values for all 15 observed GPRs; RDI is the dividend and RSI the divisor."""
        regs={r:(0x1111111111111100+r*0x0101010101010001)&M64 for r in OBSERVED}
        regs[RDI]=a&M64;regs[RSI]=b&M64
        return regs

    def _probe(self,mode,index,a,b,z,o,s,text:bytes):
        """Run the fragment natively with soft exception stubs (never #DE) and capture all 15 GPRs except rsp.
        The bridge saves the host callee-saved registers and keeps the state pointer in a stack slot, so every
        observed register (rbx/rbp/r12..r15 included) holds a test value while the fragment runs. Each exit
        pushes the 15 registers first, copies them to the state area with the route marker and rsp, restores
        the host ABI and returns normally. Returns (marker, rax, {register number: captured value})."""
        initial=self.initial_regs(a,b)
        n=len(OBSERVED)                                        # 15
        lines=['bits 64','section .text','global probe_guarded_div','probe_guarded_div:',
               ' push rbx',' push rbp',' push r12',' push r13',' push r14',' push r15',
               ' push rdi',                                    # state pointer slot
               f' mov [rdi+{8*(n+1)}], rsp']                   # rsp before the fragment
        for r in OBSERVED:lines.append(f' mov {NAMES[r]}, 0x{initial[r]:x}')
        lines+=text.decode('ascii').rstrip('\n').split('\n')

        def capture(marker):
            block=[f' push {NAMES[r]}' for r in OBSERVED]                    # [rsp+8*(n-1-i)] holds OBSERVED[i]
            block+=[f' mov rax, [rsp+{8*n}]']                                # state pointer
            for i in range(n):block+=[f' mov rbx, [rsp+{8*(n-1-i)}]',f' mov [rax+{8*i}], rbx']
            block+=[f' lea rbx, [rsp+{8*n}]',f' mov [rax+{8*(n+2)}], rbx']   # rsp after the fragment
            block+=[f' mov qword [rax+{8*n}], {marker}']
            block+=[f' add rsp, {8*(n+1)}',' pop r15',' pop r14',' pop r13',' pop r12',' pop rbp',' pop rbx',' ret']
            return block

        lines+=capture(SUCCESS_MARK)                                         # fallthrough after the divide
        lines+=[f'__dong_b{z}:']+capture(ZERO_MARK)                         # safe stubs: nothing divides here
        lines+=[f'__dong_b{o}:']+capture(OVERFLOW_MARK)
        body='\n'.join(lines)+'\n'
        d=self.work/'guarded-div-probe';d.mkdir(exist_ok=True)
        asm=d/f'{mode}-{index:03d}.asm'
        obj=d/f'{mode}-{index:03d}.o'
        exe=d/f"{mode}-{index:03d}{'.exe'if os.name=='nt'else''}"
        asm.write_text(body,encoding='utf-8')
        native='win64'if os.name=='nt'else'elf64'
        for fmt in ('elf64','win64'):
            target=obj if fmt==native else d/f'{mode}-{index:03d}.{fmt}.o'
            r=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(target),str(asm)],
                             capture_output=True,timeout=30)
            self.assertEqual(r.returncode,0,(r.stderr,body))
        nwords=n+3
        csrc=d/f'{mode}-{index:03d}.c'
        csrc.write_text(
            '#include <stdint.h>\n#include <stdio.h>\n#include <stdalign.h>\n'
            '#ifdef _WIN32\n#include <io.h>\n#include <fcntl.h>\n#endif\n'
            'void __attribute__((sysv_abi)) probe_guarded_div(uint64_t *state);\n'
            'int main(void){\n'
            '#ifdef _WIN32\n'
            '_setmode(_fileno(stdout),_O_BINARY);\n'
            '#endif\n'
            f'alignas(16) static uint64_t state[{nwords+1}];\n'
            f'for(int i=0;i<{nwords};i++)state[i]=0;\n'
            f'state[{nwords}]=0xa5a5a5a5a5a5a5a5ull;\n'
            'probe_guarded_div(state);\n'
            f'if(state[{nwords}]!=0xa5a5a5a5a5a5a5a5ull)return 96;\n'
            f'fwrite(state,8,{nwords},stdout);\n'
            'return 0;\n}\n',encoding='utf-8')
        r=subprocess.run([str(self.cc),'-std=c11','-O2','-Wall','-Wextra','-Werror',
                          str(csrc),str(obj),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        run=subprocess.run([str(exe)],capture_output=True,timeout=30)
        self.assertEqual(run.returncode,0,(run.returncode,run.stderr,body))
        self.assertEqual(len(run.stdout),8*nwords)
        words=list(struct.unpack(f'<{nwords}Q',run.stdout))
        captured={r:words[i] for i,r in enumerate(OBSERVED)}
        self.assertEqual(words[n+2],words[n+1],(mode,index,'native rsp preserved by the fragment'))
        return words[n],captured[RAX],captured

    def assert_preserved(self,mode,index,marker,a,b,captured):
        """Success may change RAX/RCX/RDX (divide kernel); exception routes may change only RAX (C31 scratch)."""
        initial=self.initial_regs(a,b)
        changeable={RAX,RCX,RDX}if marker==SUCCESS_MARK else {RAX}
        for r in OBSERVED:
            if r not in changeable:
                self.assertEqual(captured[r],initial[r],(mode,index,'native register preserved',NAMES[r],hex(captured[r])))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8')
        self.assertEqual(source.count(old),1,(name,source.count(old)))
        root=self.work/name
        src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_guarded_integer_divide.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        for dep in DEPS:
            shutil.copy2(dep,src/dep.name)
        (root/'wrapper'/'probe'/'nasm_guarded_integer_divide_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        # Flip remainder boolean → numeric reject on success path.
        rem_old=' let ds=divm.emit(signed,remainder,slice_from_raw_parts(&dbuf[0],DIV),&dlen);'
        rem_new=' let ds=divm.emit(signed,!remainder,slice_from_raw_parts(&dbuf[0],DIV),&dlen);'
        # Swap zero/overflow targets: still safe stubs, wrong route (no #DE).
        swap_old=(' let gs=guardm.emit(signed,zero_target,overflow_target,success_block,'
                  'slice_from_raw_parts(&gbuf[0],GUARD),&glen);')
        swap_new=(' let gs=guardm.emit(signed,overflow_target,zero_target,success_block,'
                  'slice_from_raw_parts(&gbuf[0],GUARD),&glen);')
        # Append "mov rbx, 61453" after the published text: rbx must be preserved on every path.
        clobber_old=' var k:usize=0;while k<dlen{out[mid+k]=dbuf[k];k+=1;}\n *written=total;return OK;'
        clobber_new=(' var k:usize=0;while k<dlen{out[mid+k]=dbuf[k];k+=1;}\n'
                     ' let extra="mov rbx, 61453\\n";var e:usize=0;while e<extra.len&&total+e<out.len{out[total+e]=extra[e];e+=1;}\n'
                     ' *written=total+e;return OK;')
        early_old=' if total>out.len{return CAPACITY;}'
        early_new=' *written=total;if total>out.len{return CAPACITY;}'
        # (name, old, new, (signed, rem, a, b, z, o, s), good marker, bad marker, rejection regex)
        semantic=[
            ('bad-flip-remainder',rem_old,rem_new,(1,0,7,2,10,11,12),SUCCESS_MARK,SUCCESS_MARK,'quotient'),
            ('bad-swap-exception',swap_old,swap_new,(1,0,7,0,10,11,12),ZERO_MARK,OVERFLOW_MARK,'route'),
            ('bad-clobber-rbx',clobber_old,clobber_new,(1,0,7,2,10,11,12),SUCCESS_MARK,SUCCESS_MARK,"'rbx'"),
        ]
        for index,(name,old,new,vec,good_marker,bad_marker,reason) in enumerate(semantic):
            sg,rem,a,b,z,o,s=vec
            # Good side: actual Dong output of the formal debug/release executables for the same input.
            good=self.run_both([item(sg,rem,z,o,s)],name+'-good')
            for mode,outs in good.items():
                gmark,grax,gcap=self._probe(mode,800+2*index,a,b,z,o,s,outs[0])
                self.assertEqual(gmark,good_marker,(name,mode,'good route'))
                if gmark==SUCCESS_MARK:self.assertEqual(grax,py_div(a,b,sg,rem),(name,mode,'good value'))
                self.assert_preserved(mode,800+2*index,gmark,a,b,gcap)
            for mode,exe in self.bad_build(name,old,new).items():
                c=item(sg,rem,z,o,s,cap=need_total(sg,rem,z,o,s)+64,status=OK)
                payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(c))
                run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                self.assertEqual(run.returncode,0,run.stderr)
                st,g,w=struct.unpack_from('<3Q',run.stdout,8)
                self.assertEqual((st,g),(0,1),(name,mode))
                text=run.stdout[32:32+c['cap']][:w]                          # the bad emitter's actual output
                marker,rax,captured=self._probe(mode,801+2*index,a,b,z,o,s,text)   # normal execution, normal return
                self.assertEqual(marker,bad_marker,(name,mode,'bad route'))
                if reason=='quotient':
                    self.assertEqual(rax,py_div(a,b,sg,1),(name,mode,'bad body computed the remainder'))
                    self.assertNotEqual(rax,py_div(a,b,sg,rem),(name,mode,'rejected by the value'))
                elif reason=='route':
                    self.assertNotEqual(marker,good_marker,(name,mode,'rejected by the route'))
                else:
                    self.assertEqual(rax,py_div(a,b,sg,rem),(name,mode,'quotient itself is right'))
                    with self.assertRaisesRegex(AssertionError,reason):
                        self.assert_preserved(mode,801+2*index,marker,a,b,captured)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,
                                     good_side='actual Dong output of the formal executables',rejected_by=reason))
        short=item(1,0,1,2,3,cap=5)
        self.run_both([short],'bad-early-written-good')
        for mode,exe in self.bad_build('bad-early-written',early_old,early_new).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                self.run_cases(exe,[short],'bad-early-written-'+mode)
        self.records.append(dict(test='bad-early-written',compiled=True,native_executed=True,modes=2,rejected_by='atomic'))


if __name__=='__main__':unittest.main()
