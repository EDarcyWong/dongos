"""Actual Dong NASM fixed-register 64-bit divide/remainder emit."""
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
from lang.tests.test_dongc import tool,nasm_flags

SOURCE=WORKS/'cursor-works/src/bootstrap/nasm_integer_divide.dg'
DOC=WORKS/'cursor-works/src/bootstrap/nasm_integer_divide.md'
OK,INVALID,CAPACITY=0,1,2
MASK64=(1<<64)-1
WRAPPER='''module probe.nasm_integer_divide_export;
import bootstrap.nasm_integer_divide as m;
export("dong_nasm_integer_divide_emit") pub unsafe fn emit(
 signed:bool,remainder:bool,out:*u8,no:usize,written:*usize)u64{unsafe{
 return m.emit(signed,remainder,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_nasm_integer_divide_emit(uint8_t,uint8_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
#define FAKE(x) ((uint8_t*)(uintptr_t)(x))
static unsigned invalid(void){
 /* Descriptor INVALID only (bools have no illegal enum). CAPACITY covered in seeded cases. */
 static uint8_t arena[4096],saved[4096];const unsigned total=9;
 uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));
  if(i==5)memcpy(o+80,"mov rax, rdi\n",13);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_nasm_integer_divide_emit(1,0,o,128,NULL);break;
   case 1:st=dong_nasm_integer_divide_emit(1,0,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_nasm_integer_divide_emit(1,0,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_nasm_integer_divide_emit(1,0,o,128,(uint64_t*)(o+120));break;
   case 4:st=dong_nasm_integer_divide_emit(1,0,NULL,128,w);break;
   case 5:st=dong_nasm_integer_divide_emit(1,0,o,160,(uint64_t*)(o+80));break;
   case 6:st=dong_nasm_integer_divide_emit(1,0,FAKE(UINT64_MAX-7),128,w);break;
   case 7:st=dong_nasm_integer_divide_emit(1,0,o,0,(uint64_t*)(uintptr_t)1);break;
   default:st=dong_nasm_integer_divide_emit(1,0,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
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
  uint64_t signedf=h[0],rem=h[1],cap=h[2],nout=h[3];
  if(cap>256)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_nasm_integer_divide_emit((uint8_t)signedf,(uint8_t)rem,o,cap,written);
  uint64_t valid=filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  free(out);
 }return 0;
}
'''


def expected(signed,remainder):
    head=b'mov rax, rdi\nmov rcx, rsi\n'
    mid=b'cqo\nidiv rcx\n' if signed else b'xor edx, edx\ndiv rcx\n'
    tail=b'mov rax, rdx\n' if remainder else b''
    return head+mid+tail


def need_total(signed,remainder):
    return len(expected(signed,remainder))


def py_div(a,b,signed,remainder):
    """Toward-zero quotient; remainder = a - q*b (Dong-style, not Python %)."""
    if signed:
        sa=a if a<(1<<63) else a-(1<<64)
        sb=b if b<(1<<63) else b-(1<<64)
        # Integer toward-zero (avoid float precision loss on large magnitudes).
        q=abs(sa)//abs(sb)
        if (sa<0)!=(sb<0):q=-q
        r=sa-q*sb
        return (r if remainder else q)&MASK64
    q=a//b
    r=a-q*b
    return (r if remainder else q)&MASK64


def item(signed,remainder,cap=None,status=None,nout=0):
    if nout and status is None:status=INVALID
    if status is None:
        need=need_total(signed,remainder)
        if cap is None:cap=need
        status=OK if need<=cap else CAPACITY
    if cap is None:cap=need_total(signed,remainder) if status==OK else 64
    text=expected(signed,remainder) if status==OK else None
    return dict(signed=int(bool(signed)),rem=int(bool(remainder)),cap=cap,nout=nout,
                status=status,text=text)


def pack_case(c):
    return struct.pack('<4Q',c['signed'],c['rem'],c['cap'],c.get('nout',0))


class NasmIntegerDivideTests(unittest.TestCase):
    PREFLIGHTS=9

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_integer_divide requires NASM/GCC')
        cls.work=WORKS/'cursor-works/build/CR19'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_integer_divide.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_integer_divide_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_integer_divide_export.dg',roots=roots,mode=mode)
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
        for signed in (True,False):
            for rem in (True,False):
                need=need_total(signed,rem)
                cases+=[item(signed,rem),
                        item(signed,rem,cap=need+3),
                        item(signed,rem,cap=max(0,need-1))]
        cases+=[item(True,False,nout=1,cap=64,status=INVALID)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_dong_assemble_and_native_divide(self):
        modes=[(True,False),(True,True),(False,False),(False,True)]
        cases=[item(s,r)for s,r in modes]
        results=self.run_both(cases,'asm-all')
        asm_dir=self.work/'asm';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,((s,r),out) in enumerate(zip(modes,outs)):
                self.assertIsNotNone(out,(mode,index))
                body=b'bits 64\nsection .text\n'+out+b'ret\n'
                for fmt in ('elf64','win64'):
                    asm=asm_dir/f'{mode}-{index:03d}-{fmt}.asm'
                    obj=asm_dir/f'{mode}-{index:03d}-{fmt}.o'
                    asm.write_bytes(body)
                    rr=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                      capture_output=True,timeout=30)
                    self.assertEqual(rr.returncode,0,(mode,index,fmt,rr.stderr,out))
                    assembled+=1
        # Safe pairs: non-zero divisor; signed not i64min/-1.
        native=[
            (True,False,-7&MASK64,3),
            (True,True,-7&MASK64,3),
            (True,False,7,3),
            (True,True,7,-3&MASK64),
            (False,False,100,7),
            (False,True,100,7),
            (False,False,MASK64,2),
            (True,False,-(1<<62)&MASK64,3),
            (True,True,1,1),
            (False,False,0,5),
            (True,False,-1&MASK64,2),
            (False,True,(1<<63)-1,9),
        ]
        ncases=[item(s,r)for s,r,_a,_b in native]
        nresults=self.run_both(ncases,'native-vecs')
        probed=0
        for mode,outs in nresults.items():
            for index,((s,r,a,b),out) in enumerate(zip(native,outs)):
                got=self._probe(mode,index,out,a,b)
                expect=py_div(a,b,s,r)
                self.assertEqual(got,expect,(mode,index,s,r,hex(a),hex(b),out,hex(got),hex(expect)))
                probed+=1
        self.records.append(dict(test='dong-assemble-native-divide',assemble_modes=len(modes),
                                 assembled=assembled,native_vectors=len(native),probed=probed,
                                 modes=2,formats=2,passed=True))

    def _probe(self,mode,index,text:bytes,dividend:int,divisor:int)->int:
        body=(
            'bits 64\nsection .text\nglobal probe_div\n'
            'probe_div:\n'
            +text.decode()+
            ' ret\n'
        )
        d=self.work/'div-probe';d.mkdir(exist_ok=True)
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
            'uint64_t __attribute__((sysv_abi)) probe_div(uint64_t,uint64_t);\n'
            f'int main(void){{printf("%" PRIu64 "\\n",probe_div(0x{dividend&MASK64:x}ULL,0x{divisor&MASK64:x}ULL));'
            'return 0;}\n',encoding='utf-8')
        r=subprocess.run([str(self.cc),'-std=c11','-O2','-Wall','-Wextra','-Werror',
                          str(csrc),str(obj),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
        self.assertEqual(run.returncode,0,(run.returncode,run.stderr,run.stdout))
        return int(run.stdout.strip())

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,(name,source.count(old)))
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_integer_divide.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'wrapper'/'probe'/'nasm_integer_divide_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        early_old=' if total>out.len{return CAPACITY;}'
        early_new=' *written=total;if total>out.len{return CAPACITY;}'
        short=item(True,False,cap=20)
        signed_case=item(True,False)
        # Same-length: idiv rdx instead of idiv rcx → wrong divisor (safe for -7/3).
        idiv_old=' out[at+4]=105;out[at+5]=100;out[at+6]=105;out[at+7]=118;out[at+8]=32;\n out[at+9]=114;out[at+10]=99;out[at+11]=120;out[at+12]=10;'
        idiv_new=' out[at+4]=105;out[at+5]=100;out[at+6]=105;out[at+7]=118;out[at+8]=32;\n out[at+9]=114;out[at+10]=100;out[at+11]=120;out[at+12]=10;'
        controls=[
            ('bad-idiv-rdx',idiv_old,idiv_new,'native',signed_case),
            ('bad-early-written',early_old,early_new,'atomic',short),
        ]
        for name,old,new,kind,case in controls:
            self.run_both([case],name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                if kind=='atomic':
                    with self.assertRaisesRegex(AssertionError,'guard/atomicity'):
                        self.run_cases(exe,[case],name+'-'+mode)
                else:
                    payload=bytearray(struct.pack('<Q',1));payload.extend(pack_case(case))
                    run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stderr)
                    st,g,w=struct.unpack_from('<3Q',run.stdout,8)
                    text=run.stdout[32:32+case['cap']][:w]
                    self.assertEqual(st,0);self.assertEqual(g,1)
                    self.assertNotEqual(text,case['text'],(name,mode,text))
                    a,b=(-7)&MASK64,3
                    got=self._probe(mode,hash(name)%100,text,a,b)
                    self.assertNotEqual(got,py_div(a,b,True,False),(name,mode,hex(got),text))
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=kind))


if __name__=='__main__':unittest.main()
