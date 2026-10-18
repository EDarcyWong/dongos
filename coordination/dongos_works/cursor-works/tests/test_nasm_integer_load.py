"""Actual Dong NASM fixed-width integer load, reusing integrated CR4 decimal_integer."""
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

SOURCE=WORKS/'cursor-works/src/bootstrap/nasm_integer_load.dg'
DOC=WORKS/'cursor-works/src/bootstrap/nasm_integer_load.md'
OK,INVALID,CAPACITY=0,1,2
REGS=[b'rax',b'rcx',b'rdx',b'rbx',b'rsp',b'rbp',b'rsi',b'rdi',
      b'r8',b'r9',b'r10',b'r11',b'r12',b'r13',b'r14',b'r15']
# Caller-saved targets safe to execute (not rsp/rbp/callee-saved).
SAFE_REGS={0,1,2,8,9,10,11}
WRAPPER='''module probe.nasm_integer_load_export;
import bootstrap.nasm_integer_load as m;
export("dong_nasm_integer_load_emit") pub unsafe fn emit(
 register:u64,raw:u64,width:usize,signed:bool,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(register,raw,width,signed,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_nasm_integer_load_emit(uint64_t,uint64_t,uint64_t,uint8_t,uint8_t*,uint64_t,uint64_t*);
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
  if(i==5)memcpy(o+80,"mov rax, 0\n",11);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_nasm_integer_load_emit(0,0,8,0,o,64,NULL);break;
   case 1:st=dong_nasm_integer_load_emit(0,0,8,0,o,64,(uint64_t*)(arena+2052));break;
   case 2:st=dong_nasm_integer_load_emit(0,0,8,0,o,64,(uint64_t*)(o+8));break;
   case 3:st=dong_nasm_integer_load_emit(0,0,8,0,o,64,(uint64_t*)(o+56));break;
   case 4:st=dong_nasm_integer_load_emit(0,0,8,0,NULL,64,w);break;
   case 5:st=dong_nasm_integer_load_emit(0,0,8,0,o,128,(uint64_t*)(o+80));break;
   case 6:st=dong_nasm_integer_load_emit(16,0,8,0,o,64,w);break;
   case 7:st=dong_nasm_integer_load_emit(0,0,7,0,o,64,w);break;
   case 8:st=dong_nasm_integer_load_emit(0,256,8,0,o,64,w);break;
   case 9:st=dong_nasm_integer_load_emit(0,0,8,0,FAKE(UINT64_MAX-7),64,w);break;
   case 10:st=dong_nasm_integer_load_emit(0,0,8,0,o,0,(uint64_t*)(uintptr_t)1);break;
   case 11:st=dong_nasm_integer_load_emit(16,0,8,0,o,0,w);break;
   case 12:st=dong_nasm_integer_load_emit(0,256,8,0,o,0,w);break;
   default:st=dong_nasm_integer_load_emit(0,0,63,0,o,64,w);break;
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
  uint64_t h[6];read_exact(h,sizeof(h));
  uint64_t reg=h[0],raw=h[1],width=h[2],signedf=h[3],cap=h[4],nout=h[5];
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_nasm_integer_load_emit(reg,raw,width,(uint8_t)signedf,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''


def width_ok(width):
    return width in (8,16,32,64)


def python_value(raw,width,signed):
    if signed:
        sign=1<<(width-1)
        if raw&sign:return raw-(1<<width)
        return raw
    return raw


def decimal_text(raw,width,signed):
    return str(python_value(raw,width,signed)).encode('ascii')


def bits64(raw,width,signed):
    if not signed:return raw&((1<<64)-1)
    return python_value(raw,width,True)&((1<<64)-1)


def expected(reg,raw,width,signed):
    return b'mov '+REGS[reg]+b', '+decimal_text(raw,width,signed)+b'\n'


def need_total(reg,raw,width,signed):
    return len(expected(reg,raw,width,signed))


def item(reg,raw,width,signed,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        if reg>15 or not width_ok(width):status=INVALID
        elif width!=64 and raw>=(1<<width):status=INVALID
        else:
            need=need_total(reg,raw,width,signed)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:cap=need_total(reg,raw,width,signed) if status==OK else 32
    text=expected(reg,raw,width,signed) if status==OK else None
    return dict(reg=reg,raw=raw,width=width,signed=int(bool(signed)),cap=cap,nout=nout,
                status=status,text=text)


class NasmIntegerLoadTests(unittest.TestCase):
    PREFLIGHTS=14

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_integer_load requires NASM/GCC')
        cls.work=WORKS/'cursor-works/build/CR9'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_integer_load.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__),ROOT/'lang/bootstrap/decimal_integer.dg']}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_integer_load_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_integer_load_export.dg',roots=roots,mode=mode)
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
            payload.extend(struct.pack('<6Q',c['reg'],c['raw'],c['width'],c['signed'],c['cap'],c.get('nout',0)))
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
        rng=random.Random(0x0C89009)
        cases=[]
        boundaries=[
            (0,0,8,False),(0,0xff,8,False),(0,0x80,8,True),(0,0x7f,8,True),
            (1,0,16,False),(1,0xffff,16,False),(1,0x8000,16,True),
            (2,0,32,False),(2,(1<<32)-1,32,False),(2,1<<31,32,True),
            (8,0,64,False),(8,(1<<64)-1,64,False),(8,1<<63,64,True),(9,0,64,True),
        ]
        for reg,raw,w,s in boundaries:
            need=need_total(reg,raw,w,s)
            cases+=[item(reg,raw,w,s),item(reg,raw,w,s,cap=need+2),item(reg,raw,w,s,cap=max(0,need-1))]
        for reg in range(16):
            cases.append(item(reg,42,64,False))
        for reg in (16,99):
            cases.append(item(reg,0,8,False,cap=64,status=INVALID))
        for w in (0,7,9,15,24,63,128):
            cases.append(item(0,0,w,False,cap=64,status=INVALID))
        cases+=[item(0,256,8,False,cap=64,status=INVALID),
                item(0,1<<16,16,False,cap=64,status=INVALID),
                item(0,1<<32,32,True,cap=64,status=INVALID),
                item(0,0,8,False,nout=1,cap=64,status=INVALID)]
        for i in range(30):
            reg=rng.randrange(16);w=rng.choice([8,16,32,64]);s=bool(rng.getrandbits(1))
            raw=rng.randrange(1<<w) if w<64 else rng.getrandbits(64)
            cases+=[item(reg,raw,w,s),item(reg,raw,w,s,cap=max(0,need_total(reg,raw,w,s)-1))]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_dong_assemble_and_native_load(self):
        samples=[]
        for reg in range(16):
            for raw,w,s in ((0,8,False),(0xff,8,True),(0x80,8,True),(7,16,False),
                            (0x8000,16,True),(1,32,False),(1<<31,32,True),
                            (0,64,False),(1<<63,64,True),((1<<64)-1,64,False)):
                if w!=64 and raw>=(1<<w):continue
                samples.append((reg,raw,w,s))
        cases=[item(*t)for t in samples]
        results=self.run_both(cases,'load')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0;probed=0
        for mode,outs in results.items():
            for index,(tup,out) in enumerate(zip(samples,outs)):
                reg,raw,w,s=tup
                self.assertIsNotNone(out,(mode,index))
                body=b'bits 64\nsection .text\n'+out+b'ret\n'
                for fmt in ('elf64','win64'):
                    asm=asm_dir/f'{mode}-{index:03d}-{fmt}.asm'
                    obj=asm_dir/f'{mode}-{index:03d}-{fmt}.o'
                    asm.write_bytes(body)
                    r=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                     capture_output=True,timeout=30)
                    self.assertEqual(r.returncode,0,(mode,index,fmt,r.stderr,out))
                    assembled+=1
                if reg in SAFE_REGS:
                    got=self._probe_mov(mode,index,reg,out)
                    self.assertEqual(got,bits64(raw,w,s),(mode,index,reg,raw,w,s,out))
                    probed+=1
        self.records.append(dict(test='dong-assemble-native-load',samples=len(samples),
                                 assembled=assembled,probed=probed,modes=2,formats=2,passed=True))

    def _probe_mov(self,mode,index,reg,text:bytes)->int:
        rname=REGS[reg].decode()
        body=(f'bits 64\nsection .text\nglobal probe_mov\nprobe_mov:\n'
              f'{text.decode()}'
              f' mov rax, {rname}\n ret\n')
        d=self.work/'mov-probe';d.mkdir(exist_ok=True)
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
            'uint64_t __attribute__((sysv_abi)) probe_mov(void);\n'
            'int main(void){uint64_t v=probe_mov();'
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
        (src/'nasm_integer_load.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'wrapper'/'probe'/'nasm_integer_load_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',ROOT/'lang',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-unsigned-as-signed',
             'let sd=dec.encode(raw,width,signed,dsl,&dw);',
             'let sd=dec.encode(raw,width,false,dsl,&dw);',
             [item(0,0x80,8,True)],'written|output'),
            ('bad-early-written',
             'if total>out.len{return CAPACITY;}',
             '*written=total;if total>out.len{return CAPACITY;}',
             [item(0,0,8,False,cap=5)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
