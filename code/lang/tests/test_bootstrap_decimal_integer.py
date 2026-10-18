"""Actual Dong fixed-width integer → canonical decimal ASCII."""
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

ROOT=Path(__file__).resolve().parents[2]
WORKS=ROOT

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

SOURCE=ROOT/'lang/bootstrap/decimal_integer.dg'
DOC=ROOT/'lang/bootstrap/decimal_integer.md'
OK,INVALID,CAPACITY=0,1,2
WRAPPER='''module probe.decimal_integer_export;
import bootstrap.decimal_integer as d;
export("dong_decimal_integer_encode") pub unsafe fn encode(
 raw:u64,width:usize,signed:bool,out:*u8,no:usize,written:*usize)u64{unsafe{
 return d.encode(raw,width,signed,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_decimal_integer_encode(uint64_t,uint64_t,uint8_t,uint8_t*,uint64_t,uint64_t*);
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
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_decimal_integer_encode(0,8,0,o,32,NULL);break;
   case 1:st=dong_decimal_integer_encode(0,8,0,o,32,(uint64_t*)(arena+2052));break;
   case 2:st=dong_decimal_integer_encode(0,8,0,o,32,(uint64_t*)(o+8));break;
   case 3:st=dong_decimal_integer_encode(0,8,0,o,32,(uint64_t*)(o+24));break; /* aligned out-tail alias */
   case 4:st=dong_decimal_integer_encode(0,8,0,NULL,32,w);break;
   case 5:st=dong_decimal_integer_encode(0,8,0,FAKE(UINT64_MAX-7),32,w);break;
   case 6:st=dong_decimal_integer_encode(0,8,0,FAKE((UINT64_C(1)<<63)|0x1000),UINT64_MAX/2,w);break;
   case 7:st=dong_decimal_integer_encode(0,7,0,o,32,w);break;
   case 8:st=dong_decimal_integer_encode(0,0,0,o,32,w);break;
   case 9:st=dong_decimal_integer_encode(0,63,0,o,32,w);break;
   case 10:st=dong_decimal_integer_encode(256,8,0,o,0,w);break; /* INVALID before CAPACITY */
   case 11:st=dong_decimal_integer_encode(65536,16,0,o,0,w);break;
   case 12:st=dong_decimal_integer_encode(0,8,0,o,0,(uint64_t*)(uintptr_t)1);break;
   default:st=dong_decimal_integer_encode((UINT64_C(1)<<32),32,1,o,0,w);break;
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
  uint64_t raw=h[0],width=h[1],signedf=h[2],cap=h[3];
  if(cap>64)exit(94);
  uint8_t*out=malloc(cap+64);uint64_t meta[3];
  if(!out)exit(95);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=out+32;
  uint64_t st=dong_decimal_integer_encode(raw,width,(uint8_t)signedf,o,cap,written);
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
    """Independent arbitrary-precision interpretation of fixed-width bits."""
    if signed:
        sign=1<<(width-1)
        if raw&sign:
            return raw-(1<<width)
        return raw
    return raw


def python_text(raw,width,signed):
    return str(python_value(raw,width,signed)).encode('ascii')


def bits64_expected(raw,width,signed):
    """Low 64 bits of two's complement; sign-extend narrow signed values."""
    if not signed:
        return raw&((1<<64)-1)
    val=python_value(raw,width,True)
    return val&((1<<64)-1)


def need_len(raw,width,signed):
    return len(python_text(raw,width,signed))


def item(raw,width,signed,cap=None,status=None):
    if status is None:
        if not width_ok(width):
            status=INVALID
        elif width!=64 and raw>=(1<<width):
            status=INVALID
        else:
            need=need_len(raw,width,signed)
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:
        cap=need_len(raw,width,signed) if status==OK else 32
    text=python_text(raw,width,signed) if status==OK else None
    return dict(raw=raw,width=width,signed=int(bool(signed)),cap=cap,status=status,text=text)


class DecimalIntegerTests(unittest.TestCase):
    PREFLIGHTS=14

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native decimal_integer requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/CR4'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'decimal_integer.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,DOC,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/decimal_integer_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/decimal_integer_export.dg',roots=roots,mode=mode)
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
            payload.extend(struct.pack('<4Q',c['raw'],c['width'],c['signed'],c['cap']))
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
            self.assertEqual(status,c['status'],(label,index,'status',c['raw'],c['width'],c['signed']))
            if not status:
                self.assertEqual(written,len(c['text']),(label,index,'written'))
                self.assertEqual(out[:written],c['text'],(label,index,'output'))
            outs.append(out[:written] if not status else None)
        self.assertEqual(offset,len(run.stdout))
        return outs

    def run_both(self,cases,label):
        return {mode:self.run_cases(exe,cases,label+'-'+mode)for mode,exe in self.executables.items()}

    def corner_raws(self,width):
        mask=(1<<width)-1
        sign=1<<(width-1)
        return [
            (0,False),(0,True),
            (sign-1,True),          # max positive signed
            (sign,True),            # min negative
            (mask,True),            # -1 signed
            (mask,False),           # unsigned max
            (1,True),(1,False),
            (sign-1,False),
        ]

    def test_widths_capacity_illegal_and_invalid_before_capacity(self):
        cases=[]
        for width in (8,16,32,64):
            for raw,signed in self.corner_raws(width):
                need=need_len(raw,width,signed)
                cases+=[
                    item(raw,width,signed),
                    item(raw,width,signed,cap=need),
                    item(raw,width,signed,cap=need+4),
                    item(raw,width,signed,cap=max(0,need-1)),
                    item(raw,width,signed,cap=0),
                ]
        # documented examples
        cases+=[
            item(255,8,True),
            item(128,8,True),
            item(256,8,False,cap=0,status=INVALID),
            item(256,8,True,cap=0,status=INVALID),
            item(0x8000_0000_0000_0000,64,True),
        ]
        # illegal widths
        for w in (0,1,7,9,15,24,31,33,48,63,65,128):
            cases+=[item(0,w,False,cap=8,status=INVALID),item(0,w,True,cap=0,status=INVALID)]
        # illegal raw for narrow widths (INVALID before CAPACITY)
        for width,bad in ((8,256),(8,1000),(16,65536),(16,0x1_0000),(32,1<<32),(32,(1<<32)+9)):
            cases+=[item(bad,width,False,cap=0,status=INVALID),item(bad,width,True,cap=64,status=INVALID)]
        rng=random.Random(0x0C84001)
        for _ in range(80):
            width=rng.choice([8,16,32,64])
            limit=1<<width
            raw=rng.randrange(0,limit)
            signed=bool(rng.getrandbits(1))
            need=need_len(raw,width,signed)
            cases+=[item(raw,width,signed),item(raw,width,signed,cap=need+1),
                    item(raw,width,signed,cap=max(0,need-1))]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='widths-capacity-illegal',cases=len(cases),
                                 random=80,modes=2,preflights=self.PREFLIGHTS,passed=True))

    def test_dong_decimal_as_nasm_dq_bin(self):
        """Dong decimal text as NASM dq operand; bin equals Python two's-complement low 64."""
        samples=[]
        for width in (8,16,32,64):
            for raw,signed in self.corner_raws(width):
                samples.append((raw,width,signed))
        samples+=[
            (255,8,True),(128,8,True),(127,8,True),(0,8,False),
            (0x7fff,16,True),(0x8000,16,True),(0xffff,16,True),
            (0x7fffffff,32,True),(0x80000000,32,True),(0xffffffff,32,False),
            (0x7fffffffffffffff,64,True),(0x8000000000000000,64,True),
            ((1<<64)-1,64,False),((1<<64)-1,64,True),
        ]
        cases=[item(r,w,s)for r,w,s in samples]
        results=self.run_both(cases,'dq-roundtrip')
        dq_dir=self.work/'nasm-dq';dq_dir.mkdir(exist_ok=True)
        checked=0;nasm_calls=0
        for mode,outs in results.items():
            for index,((raw,width,signed),text) in enumerate(zip(samples,outs)):
                self.assertIsNotNone(text,(mode,index))
                asm_path=dq_dir/f'{mode}-{index:03d}.asm'
                bin_path=dq_dir/f'{mode}-{index:03d}.bin'
                # actual Dong output is the dq operand
                asm_path.write_bytes(b'bits 64\ndq '+text+b'\n')
                r=subprocess.run([str(self.nasm),'-f','bin','-o',str(bin_path),str(asm_path)],
                                 capture_output=True,timeout=30)
                self.assertEqual(r.returncode,0,(mode,index,r.stderr,text))
                nasm_calls+=1
                got=bin_path.read_bytes()
                exp=struct.pack('<Q',bits64_expected(raw,width,signed))
                self.assertEqual(got,exp,(mode,index,'dq-bin',text,raw,width,signed))
                checked+=1
        self.assertEqual(nasm_calls,checked)
        self.records.append(dict(test='dong-nasm-dq-bin',inputs=len(samples),checks=checked,
                                 nasm_bin_calls=nasm_calls,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'decimal_integer.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'wrapper'/'probe'/'decimal_integer_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-missing-minus',
             'if negative{out[0]=45;at=1;}',
             'if negative{at=0;}',
             [item(128,8,True)],'output'),
            ('bad-i64-min-wrong-wrap',
             'if width==64{magnitude=wrapping_sub(0,raw);}',
             'if width==64{magnitude=wrapping_sub(1,raw);}',
             [item(0x8000_0000_0000_0000,64,True)],'output'),
            ('bad-early-written',
             'if total>out.len{return CAPACITY;}',
             '*written=total;if total>out.len{return CAPACITY;}',
             [item(128,8,True,cap=3)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
