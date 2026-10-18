"""Actual Dong ULEB128/SLEB128 encoders, against an independent Python encoder/decoder."""
import hashlib
import json
import os
from pathlib import Path
import random
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

SOURCE=WORKS/'claude-works/src/bootstrap/leb128.dg'
OK,INVALID,CAPACITY=0,1,2
MAX=2**64-1
I64_MIN,I64_MAX=-2**63,2**63-1
UNSIGNED,SIGNED=0,1
PREFLIGHTS=18
WRAPPER='''module probe.leb128_export;
import bootstrap.leb128 as l;
export("dong_uleb128") pub unsafe fn uleb(value:u64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return l.unsigned(value,slice_from_raw_parts(out,no),written);
}}
export("dong_sleb128") pub unsafe fn sleb(value:i64,out:*u8,no:usize,written:*usize)u64{unsafe{
 return l.signed(value,slice_from_raw_parts(out,no),written);
}}
'''
HARNESS=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI dong_uleb128(uint64_t,uint8_t*,uint64_t,uint64_t*);
extern uint64_t ABI dong_sleb128(int64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n,uint8_t fill){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=fill)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static uint64_t call(uint64_t kind,uint64_t v,uint8_t*o,uint64_t n,uint64_t*w)
{return kind?dong_sleb128((int64_t)v,o,n,w):dong_uleb128(v,o,n,w);}
/* Bad descriptors, each for both encoders: INVALID with every arena byte unchanged.
   The value 1 fits every non-empty out, so only the descriptor can reject it. */
static unsigned invalid(void){
 static uint64_t store[64];static uint8_t saved[512];uint8_t*a=(uint8_t*)store;const unsigned per=9;
 for(unsigned k=0;k<2;k++)for(unsigned i=0;i<per;i++){
  memset(a,0xa5,512);memcpy(saved,a,512);uint64_t r=0;
  uint8_t*o=a+256;uint64_t*w=store+8;                  /* w=[64,72) lies below o=[256,..) */
  switch(i){
   case 0:r=call(k,1,o,16,NULL);break;
   case 1:r=call(k,1,o,16,(uint64_t*)(a+68));break;    /* misaligned only */
   case 2:r=call(k,1,o,16,(uint64_t*)(o+8));break;     /* written inside out */
   case 3:r=call(k,1,a+12,4,(uint64_t*)(a+8));break;   /* partial overlap */
   case 4:r=call(k,1,NULL,4,w);break;
   case 5:r=call(k,1,(uint8_t*)(uintptr_t)(UINT64_MAX-3),8,w);break;  /* out end wraps; no alias */
   case 6:r=call(k,1,o,UINT64_MAX,w);break;                            /* out end wraps; w below */
   case 7:r=call(k,1,o,16,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break; /* aligned, end wraps */
   default:r=call(k,k?(uint64_t)INT64_MIN:UINT64_MAX,o,0,NULL);break;  /* INVALID before CAPACITY */
  }
  if(r!=1||memcmp(saved,a,512)){fprintf(stderr,"invalid preflight %u/%u status %u\n",k,i,(unsigned)r);exit(93);}
 }
 return 2*per;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[5];read_exact(h,sizeof(h));
  uint64_t kind=h[0],value=h[1],cap=h[2],null_empty=h[4];uint8_t fill=(uint8_t)h[3];
  if(cap>4096)exit(94);
  uint8_t*buf=malloc(cap+64);if(!buf)exit(95);
  memset(buf,fill,cap+64);uint8_t*out=buf+32;uint64_t meta[3];memset(meta,fill,sizeof(meta));uint64_t*w=meta+1;
  uint64_t r=call(kind,value,(cap||!null_empty)?out:NULL,cap,w);
  uint64_t n=r?0:*w;
  uint64_t valid=filled(buf,32,fill)&&filled(out+cap,32,fill)&&filled(meta,8,fill)&&filled(meta+2,8,fill);
  if(r)valid=valid&&filled(out,cap,fill)&&filled(w,8,fill);
  else valid=valid&&n>=1&&n<=10&&n<=cap&&filled(out+n,cap-n,fill);
  if(!valid)n=0;
  uint64_t response[3]={r,valid,n};write_exact(response,24);write_exact(out,n);
  free(buf);
 }return 0;
}
'''


def uleb(value):
    assert 0<=value<=MAX
    out=[]
    while True:
        b=value&0x7f;value>>=7
        if not value:out.append(b);return out
        out.append(b|0x80)


def sleb(value):
    assert I64_MIN<=value<=I64_MAX
    out=[]
    while True:
        b=value&0x7f;value>>=7                     # Python >> on int is arithmetic
        if (value==0 and not b&0x40) or (value==-1 and b&0x40):out.append(b);return out
        out.append(b|0x80)


def decode(data,signed):
    value=shift=0
    for i,b in enumerate(data):
        value|=(b&0x7f)<<shift;shift+=7
        if not b&0x80:
            if i!=len(data)-1:raise ValueError('bytes after the final byte')
            if signed and b&0x40:value-=1<<shift
            return value
    raise ValueError('unterminated')


def shortest(value,signed):
    """Closed-form minimum length, independent of either encoder loop."""
    n=1
    if signed:
        while not -(1<<(7*n-1))<=value<(1<<(7*n-1)):n+=1
    else:
        while value>=1<<(7*n):n+=1
    return n


def check_encoding(data,value,signed):
    """Decodes to value, continuation bits exactly on non-final bytes, minimum length, at most 10 bytes."""
    data=list(data)
    assert decode(data,signed)==value,(data,value)
    assert all(b&0x80 for b in data[:-1]) and not data[-1]&0x80,data
    assert len(data)==shortest(value,signed)<=10,(data,value)
    if len(data)>1:                                # dropping the last group must change the value
        assert decode(data[:-2]+[data[-2]&0x7f],signed)!=value,data


def case(kind,value,cap=None,fill=0xa5,null=0,status=None):
    signed=kind==SIGNED;enc=sleb(value)if signed else uleb(value);check_encoding(enc,value,signed)
    cap=len(enc)if cap is None else cap
    expected=(OK,enc)if cap>=len(enc)else(CAPACITY,None)
    if status is not None:assert expected[0]==status,(status,expected,kind,value,cap)
    return dict(kind=kind,value=value,cap=cap,fill=fill,null=null,expected=expected)


KNOWN=[(UNSIGNED,0,'00'),(UNSIGNED,1,'01'),(UNSIGNED,63,'3f'),(UNSIGNED,64,'40'),(UNSIGNED,65,'41'),(UNSIGNED,127,'7f'),
       (UNSIGNED,128,'8001'),(UNSIGNED,300,'ac02'),(UNSIGNED,16383,'ff7f'),(UNSIGNED,16384,'808001'),(UNSIGNED,624485,'e58e26'),
       (UNSIGNED,MAX,'ff'*9+'01'),(UNSIGNED,2**63,'80'*9+'01'),
       (SIGNED,0,'00'),(SIGNED,1,'01'),(SIGNED,-1,'7f'),(SIGNED,63,'3f'),(SIGNED,64,'c000'),(SIGNED,65,'c100'),
       (SIGNED,-63,'41'),(SIGNED,-64,'40'),(SIGNED,-65,'bf7f'),(SIGNED,127,'ff00'),(SIGNED,128,'8001'),(SIGNED,-128,'807f'),
       (SIGNED,-129,'ff7e'),(SIGNED,-123456,'c0bb78'),(SIGNED,I64_MAX,'ff'*9+'00'),(SIGNED,I64_MIN,'80'*9+'7f')]


def boundary_values():
    values=[]
    for k in range(1,11):
        top=1<<(7*k)
        values+=[(UNSIGNED,v)for v in (top-1,top,top+1,top>>1,(top>>1)-1)if v<=MAX]
        half=1<<(7*k-1)
        values+=[(SIGNED,v)for v in (half-1,half,half+1,-half,-half-1,-half+1)if I64_MIN<=v<=I64_MAX]
    values+=[(UNSIGNED,v)for v in (0,1,63,64,65,127,128,MAX,MAX-1,2**63,2**63-1)]
    values+=[(SIGNED,v)for v in (0,1,-1,63,64,65,-63,-64,-65,127,128,-127,-128,I64_MIN,I64_MAX,I64_MIN+1,I64_MAX-1)]
    return values


class Leb128Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native leb128 requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C13'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/leb128_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([WORKS/'claude-works/src',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/leb128_export.dg',roots=roots,mode=mode)
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
        files={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in cls.work.rglob('*')if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,artifact_sha256=files,
            records=cls.records,integrated=False,OS_VM_built=False),indent=2)+'\n')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:payload.extend(struct.pack('<5Q',c['kind'],c['value']&MAX,c['cap'],c['fill'],c['null']))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,PREFLIGHTS)
        offset=8
        for index,c in enumerate(cases):
            status,guard,n=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['expected'][0],(label,index,'status'))
            if not status:
                data=list(run.stdout[offset:offset+n]);offset+=n
                self.assertEqual((n,bytes(data).hex()),(len(c['expected'][1]),bytes(c['expected'][1]).hex()),(label,index,'bytes'))
                check_encoding(data,c['value'],c['kind']==SIGNED)   # native output decoded independently
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def test_known_vectors_boundaries_and_capacity(self):
        for kind,value,text in KNOWN:
            self.assertEqual(bytes(sleb(value)if kind else uleb(value)).hex(),text,(kind,value))
            check_encoding(bytes.fromhex(text),value,kind==SIGNED)
        fills=[0xa5,0x00,0xff,0x5a,0x80,0x7f,0x01,0xc0]
        cases=[case(kind,value,fill=fills[i%len(fills)])for i,(kind,value,_) in enumerate(KNOWN)]
        for i,(kind,value) in enumerate(boundary_values()):
            n=len(sleb(value)if kind else uleb(value));fill=fills[i%len(fills)]
            cases+=[case(kind,value,fill=fill,status=OK),case(kind,value,cap=n+3,fill=fill,status=OK),
                    case(kind,value,cap=10,fill=fill,status=OK),case(kind,value,cap=16,fill=fill^0xff,status=OK),
                    case(kind,value,cap=0,fill=fill,status=CAPACITY),case(kind,value,cap=0,fill=fill,null=1,status=CAPACITY)]
            if n>1:cases.append(case(kind,value,cap=n-1,fill=fill,status=CAPACITY))
        self.run_both(cases,'bounds')
        self.records.append(dict(test='known-boundaries-capacity',cases=len(cases),known_vectors=len(KNOWN),
            invalid_preflights_per_native=PREFLIGHTS,modes=2,passed=True))

    def test_seeded_random_values_against_python(self):
        rng=random.Random(0xC13A);cases=[]
        for i in range(600):
            kind=rng.randrange(2);bits=rng.randint(0,64 if kind==UNSIGNED else 63);value=rng.getrandbits(bits)
            if kind==SIGNED and rng.randrange(2):value=max(I64_MIN,-value-rng.randrange(2))
            n=len(sleb(value)if kind else uleb(value))
            cap=rng.choice([n,n,n-1,0,n+rng.randint(1,6),10])
            cases.append(case(kind,value,cap=cap,fill=rng.randrange(256),null=int(cap==0 and rng.randrange(2)==1)))
        self.assertGreaterEqual(sum(c['expected'][0]==OK for c in cases),100)
        self.run_both(cases,'random')
        self.records.append(dict(test='seeded-random',cases=len(cases),seed='0xC13A',modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/leb128.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/leb128_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            # Ends as soon as the remainder is 0/-1, ignoring bit 6: 64 becomes 40 (decodes as -64).
            ('bad-early-sign-end','while !((v==0&&(low&0x40)==0)||(v==-1&&(low&0x40)!=0))','while !(v==0||v==-1)',
             [case(SIGNED,64,status=OK),case(SIGNED,-65,status=OK)],'bytes'),
            # Continuation bit also set on the final unsigned byte.
            ('bad-continuation-bit','out[i]=(b|0x80)as u8;}else{out[i]=b as u8;}','out[i]=(b|0x80)as u8;}else{out[i]=(b|0x80)as u8;}',
             [case(UNSIGNED,1,status=OK)],'bytes'),
            # Writes the first group before the capacity check; 300 needs 2 bytes, only 1 given.
            ('bad-write-before-capacity','let n=ulen(value);if out.len<n{return CAPACITY;}',
             'let n=ulen(value);if out.len!=0{out[0]=(value|0x80)as u8;}if out.len<n{return CAPACITY;}',
             [case(UNSIGNED,300,cap=1,fill=0xa5,status=CAPACITY)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control cases first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
