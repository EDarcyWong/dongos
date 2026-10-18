"""Actual Dong NASM base+displacement operand, reusing integrated CR4 decimal_integer."""
import hashlib
import json
import os
from pathlib import Path
import random
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

SOURCE=WORKS/'cursor-works/src/bootstrap/nasm_memory_operand.dg'
DOC=WORKS/'cursor-works/src/bootstrap/nasm_memory_operand.md'
OK,INVALID,CAPACITY=0,1,2
I32_MIN,I32_MAX=-2147483648,2147483647
REGS=[b'rax',b'rcx',b'rdx',b'rbx',b'rsp',b'rbp',b'rsi',b'rdi',
      b'r8',b'r9',b'r10',b'r11',b'r12',b'r13',b'r14',b'r15']
# Caller-saved / non-stack bases safe for lea math probes (not rsp/rbp/callee-saved).
SAFE_BASES={0,1,2,6,7,8,9,10,11}
WRAPPER='''module probe.nasm_memory_operand_export;
import bootstrap.nasm_memory_operand as m;
export("dong_nasm_memory_operand_encode") pub unsafe fn encode(
 base:u64,displacement:i64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.encode(base,displacement,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_nasm_memory_operand_encode(uint64_t,int64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 static uint8_t arena[4096],saved[4096];const unsigned total=14;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  /* case5: seed legal-looking bytes in unused out tail before snapshot (alias). */
  /* case5: seed unused out tail before snapshot so alias reject is not masked. */
  if(i==5)memcpy(o+80,"[rax]",5);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_nasm_memory_operand_encode(0,0,o,64,NULL);break;
   case 1:st=dong_nasm_memory_operand_encode(0,0,o,64,(uint64_t*)(arena+2052));break;
   case 2:st=dong_nasm_memory_operand_encode(0,0,o,64,(uint64_t*)(o+8));break;
   case 3:st=dong_nasm_memory_operand_encode(0,0,o,64,(uint64_t*)(o+56));break;
   case 4:st=dong_nasm_memory_operand_encode(0,0,NULL,64,w);break;
   case 5:st=dong_nasm_memory_operand_encode(0,0,o,128,(uint64_t*)(o+80));break;
   case 6:st=dong_nasm_memory_operand_encode(16,0,o,64,w);break;
   case 7:st=dong_nasm_memory_operand_encode(99,0,o,64,w);break;
   case 8:st=dong_nasm_memory_operand_encode(0,(int64_t)2147483648LL,o,64,w);break;
   case 9:st=dong_nasm_memory_operand_encode(0,(int64_t)-2147483649LL,o,64,w);break;
   case 10:st=dong_nasm_memory_operand_encode(0,0,FAKE(UINT64_MAX-7),64,w);break;
   case 11:st=dong_nasm_memory_operand_encode(0,0,o,0,(uint64_t*)(uintptr_t)1);break;
   case 12:st=dong_nasm_memory_operand_encode(16,0,o,0,w);break; /* INVALID before CAPACITY */
   default:st=dong_nasm_memory_operand_encode(0,(int64_t)2147483648LL,o,0,w);break;
  }
  if(st!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)st);exit(93);}
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
  uint64_t base=h[0];int64_t disp;(void)memcpy(&disp,&h[1],8);
  uint64_t cap=h[2],nout=h[3];
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_nasm_memory_operand_encode(base,disp,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''


def as_u64_i64(disp:int)->int:
    return disp&((1<<64)-1)


def mag_text(disp:int)->bytes:
    if disp>=0:return str(disp).encode()
    return str(-disp).encode()  # Python int: -I32_MIN == 2147483648


def expected(base:int,disp:int)->bytes:
    reg=REGS[base]
    if disp==0:return b'['+reg+b']'
    if disp>0:return b'['+reg+b' + '+str(disp).encode()+b']'
    return b'['+reg+b' - '+mag_text(disp)+b']'


def need_total(base,disp):
    return len(expected(base,disp))


def item(base,disp,cap=None,status=None,nout=0):
    if nout and cap and status is None:status=INVALID
    if status is None:
        if base>15 or disp<I32_MIN or disp>I32_MAX:status=INVALID
        else:
            need=need_total(base,disp)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:cap=need_total(base,disp) if status==OK else 32
    text=expected(base,disp) if status==OK else None
    return dict(base=base,disp=disp,cap=cap,nout=nout,status=status,text=text)


class NasmMemoryOperandTests(unittest.TestCase):
    PREFLIGHTS=14

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_memory_operand requires NASM/GCC')
        cls.work=WORKS/'cursor-works/build/CR8'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_memory_operand.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__),ROOT/'lang/bootstrap/decimal_integer.dg']}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_memory_operand_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_memory_operand_export.dg',roots=roots,mode=mode)
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
        for c in cases:
            payload.extend(struct.pack('<4Q',c['base'],as_u64_i64(c['disp']),c['cap'],c['nout']))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=180)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,self.PREFLIGHTS)
        offset=8;outs=[]
        for index,c in enumerate(cases):
            status,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            out=run.stdout[offset:offset+c['cap']];offset+=c['cap']
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status',c['base'],c['disp']))
            if not status:
                self.assertEqual(written,len(c['text']),(label,index,'written'))
                self.assertEqual(out[:written],c['text'],(label,index,'output'))
            outs.append(out[:written] if not status else None)
        self.assertEqual(offset,len(run.stdout))
        return outs

    def run_both(self,cases,label):
        return {mode:self.run_cases(exe,cases,label+'-'+mode)for mode,exe in self.executables.items()}

    def test_format_boundaries_and_capacity(self):
        rng=random.Random(0x0C88008)
        disps=[0,1,-1,8,-8,I32_MIN,I32_MAX,42,-42,100,-100]
        cases=[]
        for base in range(16):
            for d in disps:
                need=need_total(base,d)
                cases+=[item(base,d),item(base,d,cap=need+3),item(base,d,cap=max(0,need-1))]
        for base in (16,17,99,(1<<64)-1):
            cases.append(item(base,0,cap=64,status=INVALID))
        for d in (I32_MAX+1,I32_MIN-1,(1<<40),-(1<<40)):
            cases.append(item(0,d,cap=64,status=INVALID))
        for i in range(40):
            base=rng.randrange(16);d=rng.randint(I32_MIN,I32_MAX)
            cases+=[item(base,d),item(base,d,cap=max(0,need_total(base,d)-1))]
        cases+=[item(0,0,nout=1,cap=64,status=INVALID),
                item(16,0,cap=0,status=INVALID)]
        self.assertEqual(expected(5,-8),b'[rbp - 8]')
        self.assertEqual(expected(0,0),b'[rax]')
        self.assertEqual(expected(8,1),b'[r8 + 1]')
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_dong_lea_assemble_and_native_math(self):
        samples=[]
        for base in range(16):
            for d in (0,1,-1,8,-8,I32_MIN,I32_MAX,123,-456):
                samples.append((base,d))
        cases=[item(b,d)for b,d in samples]
        results=self.run_both(cases,'lea')
        asm_dir=self.work/'lea';asm_dir.mkdir(exist_ok=True)
        assembled=0;probed=0
        for mode,outs in results.items():
            for index,((base,disp),out) in enumerate(zip(samples,outs)):
                self.assertIsNotNone(out,(mode,index))
                body=b'bits 64\nsection .text\nlea rax, '+out+b'\n'
                for fmt in ('elf64','win64'):
                    asm=asm_dir/f'{mode}-{index:03d}-{fmt}.asm'
                    obj=asm_dir/f'{mode}-{index:03d}-{fmt}.o'
                    asm.write_bytes(body)
                    r=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                     capture_output=True,timeout=30)
                    self.assertEqual(r.returncode,0,(mode,index,fmt,r.stderr,out))
                    assembled+=1
                if base in SAFE_BASES:
                    got=self._probe_lea(mode,index,base,disp,out)
                    expect=(0x1234_0000_abcd+disp)&((1<<64)-1)
                    self.assertEqual(got,expect,(mode,index,base,disp,out))
                    probed+=1
        self.records.append(dict(test='dong-lea-assemble-native-math',samples=len(samples),
                                 assembled=assembled,probed=probed,modes=2,formats=2,passed=True))

    def _probe_lea(self,mode,index,base,disp,operand:bytes)->int:
        reg=REGS[base].decode()
        # SysV: rdi = base value; set base reg from rdi; lea rax, [..]; ret
        body=(f'bits 64\nsection .text\nglobal probe_lea\nprobe_lea:\n'
              f' mov {reg}, rdi\n lea rax, {operand.decode()}\n ret\n')
        d=self.work/'lea-probe';d.mkdir(exist_ok=True)
        asm=d/f'{mode}-{index:03d}.asm';obj=d/f'{mode}-{index:03d}.o'
        exe=d/f"{mode}-{index:03d}{'.exe'if os.name=='nt'else''}"
        asm.write_text(body,encoding='utf-8')
        native='win64'if os.name=='nt'else'elf64'
        r=subprocess.run([str(self.nasm),'-f',native,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                         capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,(r.stderr,body))
        csrc=d/f'{mode}-{index:03d}.c'
        csrc.write_text(
            '#include <stdint.h>\n#include <stdio.h>\n#include <inttypes.h>\n'
            'uint64_t __attribute__((sysv_abi)) probe_lea(uint64_t);\n'
            'int main(void){uint64_t v=probe_lea(0x12340000abcdULL);'
            'printf("%" PRIu64 "\\n",v);return 0;}\n',encoding='utf-8')
        r=subprocess.run([str(self.cc),'-std=c11','-O2','-Wall','-Wextra','-Werror',
                          str(csrc),str(obj),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
        self.assertEqual(run.returncode,0,run.stderr)
        return int(run.stdout.strip())

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_memory_operand.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'wrapper'/'probe'/'nasm_memory_operand_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',ROOT/'lang',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-sign',
             'if displacement<0{out[at+1]=45;}else{out[at+1]=43;}',
             'if displacement<0{out[at+1]=43;}else{out[at+1]=43;}',
             [item(5,-8)],'output'),
            ('bad-early-capacity',
             'let total=nl+2;\n  if total>out.len{return CAPACITY;}',
             'let total=nl+2;\n  out[0]=91;if total>out.len{return CAPACITY;}',
             [item(0,0,cap=1)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
