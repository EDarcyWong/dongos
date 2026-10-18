"""Actual Dong bignum division/remainder, independently compared with Python integers."""
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
SOURCE=ROOT/'lang/bootstrap/bigint_div.dg'
BASELINE=ROOT/'lang/bootstrap/bigint.dg'
DIV,REM,DIVZERO=1,2,5
OK,INVALID,CAPACITY,WORKSPACE=0,1,2,3
# Temporary export wrapper; the module itself keeps calculate as its only public function.
WRAPPER='''module probe.div_export;
import bootstrap.bigint as big;
import bootstrap.bigint_div as d;
export("dong_big_div") pub unsafe fn raw(operation:u64,negative_a:bool,a:*const u32,na:usize,
 negative_b:bool,b:*const u32,nb:usize,out:*u32,capacity:usize,work:*u32,workspace:usize,result:*big.Result)u64{unsafe{
 return d.calculate(operation,negative_a,slice_from_raw_parts(a,na),negative_b,slice_from_raw_parts(b,nb),
  slice_from_raw_parts(out,capacity),slice_from_raw_parts(work,workspace),result);
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
extern uint64_t ABI dong_big_div(uint64_t,uint8_t,const uint32_t*,uint64_t,uint8_t,const uint32_t*,uint64_t,uint32_t*,uint64_t,uint32_t*,uint64_t,Big*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
/* Descriptor rejection: every case must return INVALID with the whole arena unchanged. */
static unsigned invalid(void){
 uint64_t data[96],saved[96];
 uint32_t*a=(uint32_t*)data,*b=(uint32_t*)(data+4),*out=(uint32_t*)(data+16),*work=(uint32_t*)(data+40);
 Big *result=(Big*)(data+80);const unsigned total=21;
 for(unsigned i=0;i<total;i++){
  memset(data,0xa5,sizeof(data));a[0]=7;a[1]=0;a[2]=0;b[0]=3;
  memcpy(saved,data,sizeof(data));uint64_t status=0;
  switch(i){
   case 0:status=dong_big_div(0,0,a,1,0,b,1,out,8,work,16,result);break;
   case 1:status=dong_big_div(3,0,a,1,0,b,1,out,8,work,16,result);break;
   case 2:status=dong_big_div(UINT64_MAX,0,a,1,0,b,1,out,8,work,16,result);break;
   case 3:status=dong_big_div(1,0,NULL,1,0,b,1,out,8,work,16,result);break;
   case 4:status=dong_big_div(1,0,a,1,0,NULL,1,out,8,work,16,result);break;
   case 5:status=dong_big_div(1,0,a,UINT64_MAX,0,b,1,out,8,work,16,result);break;
   case 6:status=dong_big_div(1,0,a,1,0,b,1,out,8,out,8,result);break;
   case 7:status=dong_big_div(1,0,a,1,0,b,1,out,8,work,16,NULL);break;
   case 8:status=dong_big_div(1,0,a,1,0,b,1,(uint32_t*)((uint8_t*)out+1),4,work,16,result);break;
   case 9:status=dong_big_div(1,0,a,1,0,b,1,out,8,(uint32_t*)((uint8_t*)work+2),8,result);break;
   case 10:status=dong_big_div(1,0,(uint32_t*)((uint8_t*)a+1),1,0,b,1,out,8,work,16,result);break;
   case 11:status=dong_big_div(1,0,a,1,0,b,1,out,8,work,16,(Big*)((uint8_t*)result+4));break;
   case 12:status=dong_big_div(1,0,a,1,0,b,1,out,8,work,16,(Big*)out);break;
   case 13:status=dong_big_div(1,0,a,1,0,b,1,out,8,work,16,(Big*)work);break;
   case 14:status=dong_big_div(1,0,a,1,0,b,1,a,4,work,16,result);break;
   case 15:status=dong_big_div(1,0,a,1,0,b,1,out,8,b,4,result);break;
   case 16:status=dong_big_div(1,0,a,1,0,b,1,out+44,8,work,16,result);break; /* out tail overlaps work */
   case 17:status=dong_big_div(1,0,(void*)(uintptr_t)(UINT64_MAX-3),2,0,b,1,out,8,work,16,result);break;
   case 18:status=dong_big_div(2,0,a,1,0,b,1,out,8,work,UINT64_MAX/4+1,result);break;
   case 19:status=dong_big_div(3,0,a,1,0,b,0,out,8,work,16,result);break; /* INVALID before DIVZERO */
   default:status=dong_big_div(1,0,a,2,0,b,0,out,8,work,16,result);break;  /* high zero before DIVZERO */
  }
  if(status!=1||memcmp(saved,data,sizeof(data))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)status);exit(93);}
 }
 /* Accepted aliasing/empty descriptors: identical inputs and NULL empty slices. */
 memset(data,0xa5,sizeof(data));a[0]=9;memset(result,0xa5,sizeof(Big));
 if(dong_big_div(1,1,a,1,0,a,1,out,8,work,16,result)||result->used!=1||!result->negative||out[0]!=1||!filled(out+1,28))
  {fprintf(stderr,"overlapping inputs\n");exit(96);}
 memset(data,0xa5,sizeof(data));
 if(dong_big_div(2,0,NULL,0,0,b,1,NULL,0,NULL,0,result)||result->used!=0||result->negative)
  {fprintf(stderr,"null empty views\n");exit(96);}
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[7];read_exact(h,sizeof(h));uint64_t na=h[3],nb=h[4],cap=h[5],wc=h[6];
  if(na>100000||nb>100000||cap>100000||wc>300000)exit(94);
  uint32_t *a=malloc((na+8)*4),*b=malloc((nb+8)*4),*out=malloc((cap+8)*4),*work=malloc((wc+8)*4);
  if(!a||!b||!out||!work)exit(95);
  memset(a,0xa5,(na+8)*4);memset(b,0xa5,(nb+8)*4);memset(out,0xa5,(cap+8)*4);memset(work,0xa5,(wc+8)*4);
  read_exact(a+4,na*4);read_exact(b+4,nb*4);
  uint32_t *copya=malloc((na+1)*4),*copyb=malloc((nb+1)*4);if(!copya||!copyb)exit(95);
  memcpy(copya,a+4,na*4);memcpy(copyb,b+4,nb*4);
  uint64_t meta[6];memset(meta,0xa5,sizeof(meta));Big *result=(Big*)(meta+2);
  uint64_t status=dong_big_div(h[0],(uint8_t)h[1],a+4,na,(uint8_t)h[2],b+4,nb,out+4,cap,work+4,wc,result);
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


def truncated(a,b):
    """Independent reference: quotient toward zero, remainder takes the dividend sign."""
    q=abs(a)//abs(b)
    if (a<0)!=(b<0):q=-q
    return q,a-q*b


def required(op,a,b):
    """Documented exact scratch limbs (bigint_div.md) for canonical a, b!=0."""
    m,n=len(limbs(a)),len(limbs(b))
    if m==0:return 0
    if abs(a)<abs(b):return m if op==REM else 0
    if abs(a)==abs(b):return 1 if op==DIV else 0
    return m if n==1 else 2*m+2


def case(op,a,b,cap=None,wc=None,status=None):
    q,r=truncated(a,b);expected=q if op==DIV else r
    if cap is None:cap=len(limbs(expected))
    if wc is None:wc=required(op,a,b)
    if status is None:status=OK
    return (op,int(a<0),limbs(a),int(b<0),limbs(b),cap,wc,expected if status==OK else None,status)


class BootstrapBigintDivTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native bignum division requires NASM/GCC')
        cls.work=ROOT/'build/test/claude-c1'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in
                    [SOURCE,BASELINE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/div_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/div_export.dg',roots=roots,mode=mode)
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
            records=cls.records,operations=['div','rem'],L3_selfhost_complete=False,OS_VM_built=False),indent=2)+'\n')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for op,sa,a,sb,b,cap,wc,_,_ in cases:
            payload.extend(struct.pack('<7Q',op,sa,sb,len(a),len(b),cap,wc))
            payload.extend(struct.pack('<'+'I'*(len(a)+len(b)),*a,*b))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,21)
        offset=8
        for index,(_,_,_,_,_,cap,_,expected,status)in enumerate(cases):
            actual,negative,used,guard=struct.unpack_from('<4Q',run.stdout,offset);offset+=32
            words=struct.unpack_from('<'+'I'*cap,run.stdout,offset);offset+=cap*4
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(actual,status,(label,index,'status'))
            if not actual:
                value=sum(w<<(32*i)for i,w in enumerate(words[:used]))*(-1 if negative else 1)
                self.assertEqual(value,expected,(label,index,'value'))
        self.assertEqual(offset,len(run.stdout))
        return len(cases)

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    @staticmethod
    def values():
        rng=random.Random(0xC1D1F)
        fixed=[1,2,3,7,10,2**31-1,2**31,2**32-1,2**32,2**32+1,2**63-1,2**63,2**64-1,2**64,2**64+1,
               2**96-1,2**96,2**128-1,2**32*7+5]
        for k in (31,32,33,63,64,65,95,96,127,128,160,4095,4096):fixed+= [2**k-1,2**k,2**k+1]
        fixed+=[2**(32*k)-1 for k in (2,3,5,8,128)]                 # all-ones limbs
        fixed+=[2**(32*k)+1 for k in (2,4,9,127)]                   # long interior zero limbs
        fixed+=[rng.getrandbits(4096)|1<<4095 for _ in range(3)]    # full 4096-bit
        return rng,fixed

    def test_signed_division_against_independent_reference(self):
        rng,fixed=self.values();cases=[]
        small=[0,1,2,3,7,2**32-1,2**32,2**64-1,2**64+1,2**4096-1]
        for x in small:
            for y in small[1:]:
                for sx in (1,-1):
                    for sy in (1,-1):
                        for op in (DIV,REM):cases.append(case(op,sx*x,sy*y))
        for x in fixed:
            for y in rng.sample(fixed,12)+[x,x-1 if x>1 else 1,x+1]:
                sx,sy=rng.choice((1,-1)),rng.choice((1,-1))
                for op in (DIV,REM):cases.append(case(op,sx*x,sy*y))
        # Knuth D correction paths (Hacker's Delight vectors scaled to 32-bit limbs).
        def join(ws):return sum(w<<(32*i)for i,w in enumerate(ws))
        knuth=[([0,0,0x80000000,0x7fffffff],[1,0,0x80000000]),([3,0,0x80000000],[1,0,0x20000000]),
               ([0,0,0x80000000],[0xffffffff,0x40000000]),([0,0xfffe,0x8000],[0xffff,0x8000]),
               ([0xffffffff,0xffffffff,0xffffffff,0x7fffffff],[0xffffffff,0x80000000]),
               ([0,0,0,0x80000000],[1,0,0x80000000]),([0x89ab,0x4567,0x123],[0,1]),
               ([0,0,0xfffffffe,0xffffffff],[0xffffffff,0xffffffff])]
        for u,v in knuth:
            for op in (DIV,REM):
                for s in ((1,1),(-1,1),(1,-1),(-1,-1)):cases.append(case(op,s[0]*join(u),s[1]*join(v)))
        # Random: at least 500 seeded pairs, quotient/remainder near multiples, mixed widths.
        widths=[1,7,31,32,33,63,64,65,96,127,128,200,512,1024,2048,4096]
        for i in range(700):
            wb=rng.choice(widths);b=rng.getrandbits(wb)|1<<(wb-1)
            if i%4==0:a=b*rng.getrandbits(rng.choice(widths))+rng.choice((0,1,b-1))   # near multiples
            elif i%4==1:a=rng.getrandbits(rng.choice(widths))                         # independent, may be < b
            elif i%4==2:b=2**(32*rng.randint(1,8))-rng.randint(1,3);a=rng.getrandbits(4096)
            else:a=rng.getrandbits(4096);b=rng.getrandbits(rng.randint(33,4096))|1
            sa,sb=rng.choice((1,-1)),rng.choice((1,-1))
            for op in (DIV,REM):cases.append(case(op,sa*a,sb*b))
        self.run_both(cases,'division')
        self.records.append(dict(test='signed-division',cases=len(cases),random_pairs=700,modes=2,passed=True))

    def test_zero_divisor_noncanonical_and_capacity_boundaries(self):
        rng,fixed=self.values();cases=[]
        for a in (0,1,-1,2**64,-2**4096+1):
            for op in (DIV,REM):
                cases.append((op,int(a<0),limbs(a),0,[],4,300,None,DIVZERO))
                cases.append((op,int(a<0),limbs(a),1,[],4,300,None,INVALID))   # negative zero divisor
        for op in (DIV,REM):
            cases+=[(op,1,[],0,[5],2,10,None,INVALID),(op,0,[5,0],0,[3],2,10,None,INVALID),
                    (op,0,[5],0,[3,0],2,10,None,INVALID),(op,1,[0],0,[3],2,10,None,INVALID),
                    (op,0,[5,0],0,[],2,10,None,INVALID),(op,0,[],1,[],0,0,None,INVALID),
                    (op,0,[],0,[],0,0,None,DIVZERO),(op,0,[],0,[3],0,0,0,OK),(op,1,[3],0,[3],1,1,
                     -1 if op==DIV else 0,OK)]
            cases+=[(0,0,[5],0,[3],2,10,None,INVALID),(4,0,[5],0,[3],2,10,None,INVALID)]
        pairs=[(7,3),(-7,3),(7,-3),(-7,-3),(3,7),(-3,7),(2**64,2**64),(-2**64,2**64),(2**64+5,2**32-1),
               (2**4096-1,2**32+1),(2**4096-1,-(2**2048+12345)),(2**128,2**64-1),(-2**4095,2**4095-1)]
        for _ in range(100):
            b=rng.getrandbits(rng.choice([32,64,96,512,2048]))|1;pairs.append((rng.getrandbits(4096)*rng.choice((1,-1)),b))
        exact=0
        for a,b in pairs:
            for op in (DIV,REM):
                q,r=truncated(a,b);need=len(limbs(q if op==DIV else r));wc=required(op,a,b)
                cases.append(case(op,a,b));cases.append(case(op,a,b,cap=need+3,wc=wc+5));exact+=1
                if need:cases.append(case(op,a,b,cap=need-1,status=CAPACITY))
                if wc:cases.append(case(op,a,b,wc=wc-1,status=WORKSPACE))
                if wc and need:cases.append(case(op,a,b,cap=need-1,wc=wc-1,status=WORKSPACE))   # WORKSPACE before CAPACITY
        self.run_both(cases,'bounds')
        self.records.append(dict(test='divzero-invalid-capacity-workspace',cases=len(cases),exact_pairs=exact,
                                 invalid_preflights_per_native=21,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        shutil.copyfile(BASELINE,root/'bootstrap/bigint.dg')
        (root/'bootstrap/bigint_div.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/div_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-rem-sign','return publish(negative_a,trimmed(work,b.len),out,work,result);',
             'return publish(negative_a!=negative_b,trimmed(work,b.len),out,work,result);',
             [case(REM,-(2**100+7),-(2**64+3))],'value'),
            ('bad-floor-div','if operation==DIV{return publish(negative_a!=negative_b,trimmed(work,m),out,work,result);}',
             'if operation==DIV{if negative_a!=negative_b&&r!=0{work[0]+=1;}return publish(negative_a!=negative_b,trimmed(work,m),out,work,result);}',
             [case(DIV,-7,2)],'value'),
            ('bad-addback','qhat-=1;var c:u64=0;','var c:u64=0;',
             [case(DIV,0x7fffffff_80000000_00000000_00000000,0x80000000_00000000_00000001)],'value'),
            ('bad-early-output','if used>out.len{return big.CAPACITY;}var i:usize=0;while i<used{out[i]=work[i];i+=1;}',
             'var i:usize=0;while i<used&&i<out.len{out[i]=work[i];i+=1;}if used>out.len{return big.CAPACITY;}',
             [case(DIV,2**200+1,3,cap=1,status=CAPACITY)],'guard/atomicity'),
            ('bad-early-result','if work.len<required(operation,a.len,b.len,relation){return big.WORKSPACE;}',
             'if work.len<required(operation,a.len,b.len,relation){*result=big.Result{negative:false,used:0};return big.WORKSPACE;}',
             [case(REM,2**300,2**100+1,wc=1,status=WORKSPACE)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
