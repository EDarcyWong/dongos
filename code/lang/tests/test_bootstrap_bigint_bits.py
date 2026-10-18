"""Actual Dong bignum bitwise/shift operations, independently compared with Python integers."""
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import unittest
import uuid

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'lang/bootstrap/bigint_bits.dg'
BASELINE=ROOT/'lang/bootstrap/bigint.dg'
AND,OR,XOR=1,2,3
BITWISE,INVERT,LEFT,RIGHT=1,2,3,4
OK,INVALID,CAPACITY,WORKSPACE=0,1,2,3
USIZE_MAX=2**64-1
# Temporary export wrapper; the module itself exports nothing.
WRAPPER='''module probe.bits_export;
import bootstrap.bigint as big;
import bootstrap.bigint_bits as k;
export("dong_big_bitwise") pub unsafe fn bitwise(operation:u64,negative_a:bool,a:*const u32,na:usize,
 negative_b:bool,b:*const u32,nb:usize,out:*u32,capacity:usize,work:*u32,workspace:usize,result:*big.Result)u64{unsafe{
 return k.bitwise(operation,negative_a,slice_from_raw_parts(a,na),negative_b,slice_from_raw_parts(b,nb),
  slice_from_raw_parts(out,capacity),slice_from_raw_parts(work,workspace),result);
}}
export("dong_big_invert") pub unsafe fn invert(negative:bool,a:*const u32,na:usize,
 out:*u32,capacity:usize,work:*u32,workspace:usize,result:*big.Result)u64{unsafe{
 return k.invert(negative,slice_from_raw_parts(a,na),slice_from_raw_parts(out,capacity),slice_from_raw_parts(work,workspace),result);
}}
export("dong_big_shift") pub unsafe fn shift(left:bool,negative:bool,a:*const u32,na:usize,amount:usize,
 out:*u32,capacity:usize,work:*u32,workspace:usize,result:*big.Result)u64{unsafe{
 return k.shift(left,negative,slice_from_raw_parts(a,na),amount,slice_from_raw_parts(out,capacity),slice_from_raw_parts(work,workspace),result);
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
typedef struct {uint8_t negative,padding[7];uint64_t used;} Big;
_Static_assert(sizeof(Big)==16,"Dong bignum metadata");
_Static_assert(__builtin_offsetof(Big,used)==8,"Dong bignum used offset");
extern uint64_t ABI dong_big_bitwise(uint64_t,uint8_t,const uint32_t*,uint64_t,uint8_t,const uint32_t*,uint64_t,uint32_t*,uint64_t,uint32_t*,uint64_t,Big*);
extern uint64_t ABI dong_big_invert(uint8_t,const uint32_t*,uint64_t,uint32_t*,uint64_t,uint32_t*,uint64_t,Big*);
extern uint64_t ABI dong_big_shift(uint8_t,uint8_t,const uint32_t*,uint64_t,uint64_t,uint32_t*,uint64_t,uint32_t*,uint64_t,Big*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
/* Descriptor rejection for all three entry points: INVALID with the whole arena unchanged. */
static unsigned invalid(void){
 uint64_t data[96],saved[96];
 uint32_t*a=(uint32_t*)data,*b=(uint32_t*)(data+4),*out=(uint32_t*)(data+16),*work=(uint32_t*)(data+40);
 Big *result=(Big*)(data+80),*odd=(Big*)((uint8_t*)result+4);uint32_t*mis=(uint32_t*)((uint8_t*)out+1);
 void*far=(void*)(uintptr_t)(UINT64_MAX-3);const unsigned total=33;
 for(unsigned i=0;i<total;i++){
  memset(data,0xa5,sizeof(data));a[0]=7;b[0]=3;
  memcpy(saved,data,sizeof(data));uint64_t s=0;
  switch(i){
   case 0:s=dong_big_bitwise(0,0,a,1,0,b,1,out,8,work,16,result);break;
   case 1:s=dong_big_bitwise(4,0,a,1,0,b,1,out,8,work,16,result);break;
   case 2:s=dong_big_bitwise(UINT64_MAX,0,a,1,0,b,1,out,8,work,16,result);break;
   case 3:s=dong_big_bitwise(1,0,NULL,1,0,b,1,out,8,work,16,result);break;
   case 4:s=dong_big_bitwise(1,0,a,1,0,NULL,1,out,8,work,16,result);break;
   case 5:s=dong_big_bitwise(1,0,a,UINT64_MAX,0,b,1,out,8,work,16,result);break;
   case 6:s=dong_big_bitwise(1,0,a,1,0,b,1,out,8,out,8,result);break;
   case 7:s=dong_big_bitwise(1,0,a,1,0,b,1,out,8,work,16,NULL);break;
   case 8:s=dong_big_bitwise(1,0,a,1,0,b,1,mis,4,work,16,result);break;
   case 9:s=dong_big_bitwise(1,0,a,1,0,b,1,out,8,work,16,odd);break;
   case 10:s=dong_big_bitwise(1,0,a,1,0,b,1,out,8,work,16,(Big*)work);break;
   case 11:s=dong_big_bitwise(1,0,a,1,0,b,1,a,4,work,16,result);break;
   case 12:s=dong_big_bitwise(1,0,a,1,0,b,1,out,8,b,4,result);break;
   case 13:s=dong_big_bitwise(1,0,a,1,0,b,1,out+44,8,work,16,result);break;
   case 14:s=dong_big_bitwise(1,0,far,2,0,b,1,out,8,work,16,result);break;
   case 15:s=dong_big_bitwise(1,0,(uint32_t*)((uint8_t*)a+2),1,0,b,1,out,8,work,16,result);break;
   case 16:s=dong_big_invert(0,NULL,1,out,8,work,16,result);break;
   case 17:s=dong_big_invert(0,a,1,a,4,work,16,result);break;
   case 18:s=dong_big_invert(0,a,1,out,8,a,4,result);break;
   case 19:s=dong_big_invert(0,a,1,out,8,work,16,NULL);break;
   case 20:s=dong_big_invert(0,a,1,out,8,(uint32_t*)((uint8_t*)work+2),8,result);break;
   case 21:s=dong_big_invert(0,far,2,out,8,work,16,result);break;
   case 22:s=dong_big_invert(0,a,1,out,8,work,UINT64_MAX/4+1,result);break;
   case 23:s=dong_big_shift(1,0,NULL,1,1,out,8,work,16,result);break;
   case 24:s=dong_big_shift(1,0,a,1,UINT64_MAX,a,4,work,16,result);break;  /* INVALID before WORKSPACE */
   case 25:s=dong_big_shift(0,0,a,1,1,out,8,a,4,result);break;
   case 26:s=dong_big_shift(0,0,a,1,1,out,8,work,16,(Big*)out);break;
   case 27:s=dong_big_shift(1,0,a,1,1,mis,4,work,16,result);break;
   case 28:s=dong_big_shift(0,0,a,1,1,out,8,work,16,odd);break;
   case 29:s=dong_big_shift(1,0,far,2,1,out,8,work,16,result);break;
   case 30:s=dong_big_shift(1,0,a,UINT64_MAX,1,out,8,work,16,result);break;
   case 31:s=dong_big_shift(0,0,a,1,1,out,8,out,8,result);break;
   default:s=dong_big_invert(0,a,1,out,8,work,16,(Big*)((uint8_t*)a));break;
  }
  if(s!=1||memcmp(saved,data,sizeof(data))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)s);exit(93);}
 }
 /* Accepted descriptors: identical inputs and NULL empty views. */
 memset(data,0xa5,sizeof(data));a[0]=9;
 if(dong_big_bitwise(3,0,a,1,0,a,1,out,8,work,16,result)||result->used!=0||result->negative||!filled(out,32))
  {fprintf(stderr,"overlapping inputs\n");exit(96);}
 memset(data,0xa5,sizeof(data));
 if(dong_big_shift(1,0,NULL,0,UINT64_MAX,NULL,0,NULL,0,result)||result->used!=0||result->negative)
  {fprintf(stderr,"null empty shift\n");exit(96);}
 memset(data,0xa5,sizeof(data));
 if(dong_big_invert(0,NULL,0,out,1,work,1,result)||result->used!=1||!result->negative||out[0]!=1)
  {fprintf(stderr,"null empty invert\n");exit(96);}
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[9];read_exact(h,sizeof(h));uint64_t na=h[4],nb=h[5],cap=h[6],wc=h[7];
  if(na>100000||nb>100000||cap>100000||wc>300000)exit(94);
  uint32_t *a=malloc((na+8)*4),*b=malloc((nb+8)*4),*out=malloc((cap+8)*4),*work=malloc((wc+8)*4);
  if(!a||!b||!out||!work)exit(95);
  memset(a,0xa5,(na+8)*4);memset(b,0xa5,(nb+8)*4);memset(out,0xa5,(cap+8)*4);memset(work,0xa5,(wc+8)*4);
  read_exact(a+4,na*4);read_exact(b+4,nb*4);
  uint32_t *copya=malloc((na+1)*4),*copyb=malloc((nb+1)*4);if(!copya||!copyb)exit(95);
  memcpy(copya,a+4,na*4);memcpy(copyb,b+4,nb*4);
  uint64_t meta[6];memset(meta,0xa5,sizeof(meta));Big *result=(Big*)(meta+2);uint64_t status;
  switch(h[0]){
   case 1:status=dong_big_bitwise(h[1],(uint8_t)h[2],a+4,na,(uint8_t)h[3],b+4,nb,out+4,cap,work+4,wc,result);break;
   case 2:status=dong_big_invert((uint8_t)h[2],a+4,na,out+4,cap,work+4,wc,result);break;
   case 3:status=dong_big_shift(1,(uint8_t)h[2],a+4,na,h[8],out+4,cap,work+4,wc,result);break;
   case 4:status=dong_big_shift(0,(uint8_t)h[2],a+4,na,h[8],out+4,cap,work+4,wc,result);break;
   default:exit(97);
  }
  uint64_t valid=filled(a,16)&&filled(a+4+na,16)&&filled(b,16)&&filled(b+4+nb,16)&&
    filled(out,16)&&filled(out+4+cap,16)&&filled(work,16)&&filled(work+4+wc,16)&&
    filled(meta,16)&&filled(meta+4,16)&&!memcmp(copya,a+4,na*4)&&!memcmp(copyb,b+4,nb*4);
  if(status)valid=valid&&filled(out+4,cap*4)&&filled(result,16);
  if(status==1)valid=valid&&filled(work+4,wc*4);
  if(!status)valid=valid&&result->used<=cap&&result->negative<=1&&filled(out+4+result->used,(cap-result->used)*4)&&
     (result->used?out[4+result->used-1]!=0:!result->negative);
  uint64_t response[4]={status,status?0:result->negative,status?0:result->used,valid};
  write_exact(response,sizeof(response));write_exact(out+4,cap*4);
  free(a);free(b);free(out);free(work);free(copya);free(copyb);
 }return 0;
}
'''


def limbs(n):
    n=abs(n);out=[]
    while n:out.append(n&0xffffffff);n>>=32
    return out


def expect(kind,op,a,b,amount):
    """Independent reference: Python's unbounded two's complement integers."""
    if kind==BITWISE:return {AND:a&b,OR:a|b,XOR:a^b}[op]
    if kind==INVERT:return ~a
    if kind==RIGHT:return a>>amount
    if a==0:return 0
    return a<<amount


def required(kind,a,b,amount):
    """Documented exact scratch limbs (bigint_bits.md)."""
    la,lb=len(limbs(a)),len(limbs(b))
    if kind==BITWISE:return max(la,lb)+1
    if kind==INVERT:return la+1
    if la==0:return 0
    q=amount//32
    if kind==LEFT:return la+q+1
    if q>=la:return 1 if a<0 else 0
    return la-q+(1 if a<0 else 0)


def case(kind,a,b=0,op=0,amount=0,cap=None,wc=None,status=OK):
    expected=expect(kind,op,a,b,amount)if kind!=LEFT or a==0 or amount<2**20 else None
    if cap is None:cap=len(limbs(expected))
    if status!=OK:expected=None
    if wc is None:wc=required(kind,a,b,amount)
    return (kind,op,int(a<0),limbs(a),int(b<0),limbs(b),cap,wc,amount,expected,status)


def huge_left(a,amount,cap=4,wc=16):
    """Nonzero left shift whose exact result cannot fit any supplied workspace."""
    return (LEFT,0,int(a<0),limbs(a),0,[],cap,wc,amount,None,WORKSPACE)


class BootstrapBigintBitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native bignum bit operations require NASM/GCC')
        cls.work=ROOT/'build/test/claude-c2'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in
                    [SOURCE,BASELINE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/bits_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/bits_export.dg',roots=roots,mode=mode)
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
            records=cls.records,operations=['and','or','xor','invert','shift-left','shift-right'],
            L3_selfhost_complete=False,OS_VM_built=False),indent=2)+'\n')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for kind,op,sa,a,sb,b,cap,wc,amount,_,_ in cases:
            payload.extend(struct.pack('<9Q',kind,op,sa,sb,len(a),len(b),cap,wc,amount))
            payload.extend(struct.pack('<'+'I'*(len(a)+len(b)),*a,*b))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,33)
        offset=8
        for index,case_ in enumerate(cases):
            cap,expected,status=case_[6],case_[9],case_[10]
            actual,negative,used,guard=struct.unpack_from('<4Q',run.stdout,offset);offset+=32
            words=struct.unpack_from('<'+'I'*cap,run.stdout,offset);offset+=cap*4
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(actual,status,(label,index,'status'))
            if not actual:
                value=sum(w<<(32*i)for i,w in enumerate(words[:used]))*(-1 if negative else 1)
                self.assertEqual(value,expected,(label,index,'value'))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    @staticmethod
    def values():
        rng=random.Random(0xC2B175)
        base=[0,1,2,3,4,5,7,2**31-1,2**31,2**32-1,2**32,2**32+1,2**63,2**64-1,2**64,2**64+1]
        for k in (33,63,65,95,96,127,128,4095,4096):base+=[2**k-1,2**k,2**k+1]
        base+=[2**(32*k)-1 for k in (2,3,7,128)]+[2**(32*k)+1 for k in (2,5,127)]
        base+=[rng.getrandbits(4096)|1<<4095 for _ in range(3)]
        return rng,sorted(set(base))+[-x for x in sorted(set(base))if x]

    def test_bitwise_and_invert_against_python(self):
        rng,values=self.values();cases=[]
        small=[0,1,-1,2,-2,3,-3,2**32-1,-2**32,2**32,-(2**32-1),2**64,-2**64,2**4096-1,-2**4096]
        for x in small:
            for y in small:
                for op in (AND,OR,XOR):cases.append(case(BITWISE,x,y,op))
        for x in values:
            cases.append(case(INVERT,x))
            for y in rng.sample(values,6):
                for op in (AND,OR,XOR):cases.append(case(BITWISE,x,y,op))
        widths=[1,7,31,32,33,63,64,65,96,128,200,512,1024,2048,4096]
        for _ in range(600):
            x=rng.getrandbits(rng.choice(widths))*rng.choice((1,-1));y=rng.getrandbits(rng.choice(widths))*rng.choice((1,-1))
            for op in (AND,OR,XOR):cases.append(case(BITWISE,x,y,op))
            cases.append(case(INVERT,x))
        self.run_both(cases,'bitwise')
        self.records.append(dict(test='bitwise-invert',cases=len(cases),random_pairs=600,modes=2,passed=True))

    def test_shifts_against_python(self):
        rng,values=self.values();cases=[]
        amounts=[0,1,2,31,32,33,63,64,65,95,96,127,128,1000,4095,4096,4097,5000]
        for x in values:
            for amount in amounts:cases+=[case(LEFT,x,amount=amount),case(RIGHT,x,amount=amount)]
            for amount in (2**32,2**40,2**63,USIZE_MAX-31,USIZE_MAX):
                cases.append(case(RIGHT,x,amount=amount))
                cases.append(case(LEFT,x,amount=amount)if x==0 else huge_left(x,amount))
        # Floor rounding with dropped bits zero/nonzero, and exactly-one-limb carries.
        for x,k in [(-4,1),(-3,1),(-1,1),(-1,100),(-2,1),(-5,2),(-8,3),(-9,3),(-(2**64-1),32),(-(2**64),32),
                    (-(2**64+1),32),(-(2**96-1),64),(-(2**4096-1),4095),(-(2**4096),4096),(-(2**4096),4095)]:
            cases.append(case(RIGHT,x,amount=k))
        for _ in range(600):
            x=rng.getrandbits(rng.choice([1,32,33,64,65,128,1000,4096]))*rng.choice((1,-1));amount=rng.randrange(0,5000)
            cases+=[case(LEFT,x,amount=amount),case(RIGHT,x,amount=amount)]
        self.run_both(cases,'shift')
        self.records.append(dict(test='shift-left-right',cases=len(cases),random_values=600,modes=2,passed=True))

    def test_invalid_capacity_and_workspace_boundaries(self):
        rng,values=self.values();cases=[]
        for kind,op in ((BITWISE,AND),(BITWISE,OR),(BITWISE,XOR),(INVERT,0),(LEFT,0),(RIGHT,0)):
            for sa,a in ((1,[]),(0,[5,0]),(1,[0])):
                cases.append((kind,op,sa,a,0,[3],4,20,1,None,INVALID))
            if kind==BITWISE:cases+=[(kind,op,0,[3],1,[],4,20,0,None,INVALID),(kind,op,0,[3],0,[1,0],4,20,0,None,INVALID)]
        for op in (0,4,5,USIZE_MAX):cases.append((BITWISE,op,0,[5],0,[3],4,20,0,None,INVALID))
        cases.append((LEFT,0,1,[0],0,[],4,20,USIZE_MAX,None,INVALID))   # INVALID before huge-shift WORKSPACE
        trials=[]
        for _ in range(60):
            x,y=rng.choice(values),rng.choice(values);op=rng.choice((AND,OR,XOR))
            trials+=[(BITWISE,x,y,op,0),(INVERT,x,0,0,0),(LEFT,x,0,0,rng.choice([0,1,31,32,33,64,65,700])),
                     (RIGHT,x,0,0,rng.choice([0,1,31,32,33,64,65,700,5000]))]
        trials+=[(BITWISE,0,0,AND,0),(BITWISE,-1,-1,AND,0),(BITWISE,-2**64,2**64-1,OR,0),(INVERT,0,0,0,0),
                 (INVERT,-1,0,0,0),(INVERT,2**64-1,0,0,0),(RIGHT,-1,0,0,5000),(RIGHT,-(2**64-1),0,0,32),(LEFT,2**64-1,0,0,32)]
        for kind,x,y,op,amount in trials:
            need=len(limbs(expect(kind,op,x,y,amount)));wc=required(kind,x,y,amount)
            cases.append(case(kind,x,y,op,amount));cases.append(case(kind,x,y,op,amount,cap=need+3,wc=wc+5))
            if need:cases.append(case(kind,x,y,op,amount,cap=need-1,status=CAPACITY))
            if wc:cases.append(case(kind,x,y,op,amount,wc=wc-1,status=WORKSPACE))
            if wc and need:cases.append(case(kind,x,y,op,amount,cap=need-1,wc=wc-1,status=WORKSPACE))
        cases+=[huge_left(1,2**40,cap=100000,wc=300000),huge_left(-1,USIZE_MAX,cap=0,wc=0)]
        self.run_both(cases,'bounds')
        self.records.append(dict(test='invalid-capacity-workspace',cases=len(cases),exact_trials=len(trials),
                                 invalid_preflights_per_native=33,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        shutil.copyfile(BASELINE,root/'bootstrap/bigint.dg')
        (root/'bootstrap/bigint_bits.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/bits_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-sign-extension','if negative_b{let t=(y^MASK)+cb;y=t&MASK;cb=t>>32;}','',
             [case(BITWISE,2**40+5,-3,AND)],'value'),
            ('bad-shift-rounding','var carry:u64=0;if dropped{carry=1;}','var carry:u64=0;',
             [case(RIGHT,-3,amount=1)],'value'),
            ('bad-early-output','if used>out.len{return big.CAPACITY;}var i:usize=0;while i<used{out[i]=work[i];i+=1;}',
             'var i:usize=0;while i<used&&i<out.len{out[i]=work[i];i+=1;}if used>out.len{return big.CAPACITY;}',
             [case(BITWISE,2**100-1,2**64+7,XOR,cap=1,status=CAPACITY)],'guard/atomicity'),
            ('bad-early-result','let width=n+q+1;if work.len<width{return big.WORKSPACE;}',
             'let width=n+q+1;if work.len<width{*result=big.Result{negative:false,used:0};return big.WORKSPACE;}',
             [huge_left(5,USIZE_MAX)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
