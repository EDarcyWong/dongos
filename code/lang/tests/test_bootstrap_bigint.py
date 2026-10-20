"""Actual Dong bignum arithmetic, independently compared with Python integers."""
import hashlib
import json
import os
from pathlib import Path
import random
import struct
import subprocess
import unittest
import uuid

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

ROOT=Path(__file__).resolve().parents[2]
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
extern uint64_t ABI dong_big_parse(const uint8_t*,uint64_t,uint32_t*,uint64_t,uint32_t*,uint64_t,Big*);
extern uint64_t ABI dong_big_calculate(uint64_t,uint8_t,const uint32_t*,uint64_t,uint8_t,const uint32_t*,uint64_t,uint32_t*,uint64_t,uint32_t*,uint64_t,Big*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static void invalid(void){
 uint64_t data[64],saved[64];uint32_t*a=(uint32_t*)data,*out=(uint32_t*)(data+8),*work=(uint32_t*)(data+24);
 Big *result=(Big*)(data+48);
 for(unsigned i=0;i<9;i++){
  memset(data,0xa5,sizeof(data));memcpy(saved,data,sizeof(data));uint64_t status=0;
  switch(i){
   case 0:status=dong_big_calculate(0,0,a,1,0,a,1,out,4,work,8,result);break;
   case 1:status=dong_big_calculate(1,0,NULL,1,0,a,1,out,4,work,8,result);break;
   case 2:status=dong_big_calculate(1,0,a,UINT64_MAX,0,a,1,out,4,work,8,result);break;
   case 3:status=dong_big_calculate(1,0,a,1,0,a,1,out,4,out,4,result);break;
   case 4:status=dong_big_calculate(1,0,a,1,0,a,1,out,4,work,8,NULL);break;
   case 5:status=dong_big_calculate(1,0,a,1,0,a,1,(uint32_t*)((uint8_t*)out+1),4,work,8,result);break;
   case 6:status=dong_big_calculate(1,0,a,1,0,a,1,out,4,work,8,(Big*)out);break;
   case 7:status=dong_big_parse(NULL,1,out,4,work,8,result);break;
   default:status=dong_big_calculate(1,0,(void*)(uintptr_t)(UINT64_MAX-3),2,0,a,1,out,4,work,8,result);break;
  }
  if(status!=1||memcmp(saved,data,sizeof(data))){fprintf(stderr,"invalid preflight %u\n",i);exit(93);}
 }
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 invalid();uint64_t count;read_exact(&count,8);
 while(count--){
  uint64_t h[8];read_exact(h,sizeof(h));uint64_t na=h[3],nb=h[4],cap=h[5],wc=h[6],nt=h[7];
  if(na>100000||nb>100000||cap>100000||wc>200000||nt>100000)exit(94);
  uint32_t *a=malloc((na+8)*4),*b=malloc((nb+8)*4),*out=malloc((cap+8)*4),*work=malloc((wc+8)*4);
  uint8_t *text=malloc(nt+1);if(!a||!b||!out||!work||!text)exit(95);
  memset(a,0xa5,(na+8)*4);memset(b,0xa5,(nb+8)*4);memset(out,0xa5,(cap+8)*4);memset(work,0xa5,(wc+8)*4);
  read_exact(a+4,na*4);read_exact(b+4,nb*4);read_exact(text,nt);
  uint32_t *copya=malloc((na+1)*4),*copyb=malloc((nb+1)*4);if(!copya||!copyb)exit(95);
  memcpy(copya,a+4,na*4);memcpy(copyb,b+4,nb*4);
  uint64_t meta[6];memset(meta,0xa5,sizeof(meta));Big *result=(Big*)(meta+2);
  uint64_t status=h[0]?dong_big_calculate(h[0],(uint8_t)h[1],a+4,na,(uint8_t)h[2],b+4,nb,out+4,cap,work+4,wc,result)
                       :dong_big_parse(text,nt,out+4,cap,work+4,wc,result);
  uint64_t valid=filled(a,16)&&filled(a+4+na,16)&&filled(b,16)&&filled(b+4+nb,16)&&
    filled(out,16)&&filled(out+4+cap,16)&&filled(work,16)&&filled(work+4+wc,16)&&
    filled(meta,16)&&filled(meta+4,16)&&!memcmp(copya,a+4,na*4)&&!memcmp(copyb,b+4,nb*4);
  if(status)valid=valid&&filled(out+4,cap*4)&&filled(result,16);
  else valid=valid&&result->used<=cap&&result->negative<=1&&filled(out+4+result->used,(cap-result->used)*4)&&
     (result->used?out[4+result->used-1]!=0:!result->negative);
  uint64_t response[4]={status,status?0:result->negative,status?0:result->used,valid};
  write_exact(response,sizeof(response));write_exact(out+4,cap*4);
  free(a);free(b);free(out);free(work);free(text);free(copya);free(copyb);
 }return 0;
}
'''


def limbs(n):
    n=abs(n);out=[]
    while n:out.append(n&0xffffffff);n>>=32
    return out


class BootstrapBigintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native bignum requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-bigint'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in
                    [ROOT/'lang/bootstrap/bigint.dg',Path(__file__)]}
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build(ROOT/'lang',mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=90)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,root,mode,name):
        compiled=compile_file(root/'bootstrap/bigint.dg',roots=[root],mode=mode)
        asm=cls.work/(name+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
        obj=cls.work/(name+'.o');exe=cls.work/(name+('.exe'if os.name=='nt'else'.bin'))
        for fmt in ('elf64','win64'):
            output=obj if fmt==('win64'if os.name=='nt'else'elf64')else cls.work/(name+'.'+fmt+'.o')
            cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',output,asm],name+'-'+fmt)
        cls.command([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',cls.work/'probe.c',obj,'-o',exe],name+'-link')
        return exe

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        files={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in cls.work.rglob('*')if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,artifact_sha256=files,
            records=cls.records,operations=['parse','compare','add','subtract','multiply'],
            L3_selfhost_complete=False,OS_VM_built=False),indent=2)+'\n')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for op,sa,a,sb,b,cap,wc,text,expected,status in cases:
            payload.extend(struct.pack('<8Q',op,sa,sb,len(a),len(b),cap,wc,len(text)))
            payload.extend(struct.pack('<'+'I'*(len(a)+len(b)),*a,*b));payload.extend(text)
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        offset=0
        for index,(_,_,_,_,_,cap,_,_,expected,status)in enumerate(cases):
            actual,negative,used,guard=struct.unpack_from('<4Q',run.stdout,offset);offset+=32
            words=struct.unpack_from('<'+'I'*cap,run.stdout,offset);offset+=cap*4
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(actual,status,(label,index,'status'))
            if not actual:
                value=sum(w<<(32*i)for i,w in enumerate(words[:used]))*(-1 if negative else 1)
                self.assertEqual(value,expected,(label,index,'value'))
        self.assertEqual(offset,len(run.stdout))

    def test_signed_arithmetic_through_4096_bits_against_python(self):
        rng=random.Random(0xB16D06);cases=[]
        values=[0,1,-1,2**32-1,-2**32,2**64-1,-2**64,2**1024-1,-2**1024]
        for _ in range(220):
            width=rng.choice([7,32,64,127,255,512,1024,4096]);values.append(rng.getrandbits(width)*rng.choice([-1,1]))
        for a in values:
            for b in (a,-a,rng.choice(values)):
                aa,bb=limbs(a),limbs(b);cap=len(aa)+len(bb)+3
                for op,expected in [(1,a+b),(2,a-b),(3,a*b),(4,(a>b)-(a<b))]:
                    cases.append((op,int(a<0),aa,int(b<0),bb,cap,cap,b'',expected,0))
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'arithmetic-'+mode)
        self.records.append(dict(test='signed-arithmetic',cases=len(cases),modes=2,passed=True))

    def test_literals_capacities_and_invalid_inputs_preserve_outputs(self):
        cases=[]
        for n in [0,1,2**32-1,2**32,2**64,2**1024-1,2**4096-1]:
            for text in (str(n),hex(n),bin(n)):
                text=text.encode();size=len(limbs(n));cases.append((0,0,[],0,[],size,size+1,text,n,0))
        cases.extend([(0,0,[],0,[],0,0,b'000_000',0,0),
                      (1,0,[],0,[],0,0,b'',0,0),(2,0,[],0,[],0,0,b'',0,0),
                      (3,0,[],0,[],0,0,b'',0,0)])
        for text in (b'',b'0x',b'0b',b'_1',b'1_',b'1__2',b'0x_1',b'0b2',b'12u64',b'-1',b'0Xff'):
            cases.append((0,0,[],0,[],4,8,text,None,4))
        cases.extend([(0,0,[],0,[],0,3,b'123',None,2),
                      (0,0,[],0,[],4,0,b'123',None,3),
                      (1,0,[0xffffffff],0,[1],0,3,b'',None,2),
                      (1,0,[1],0,[1],2,0,b'',None,3),
                      (3,0,[1],0,[1],2,1,b'',None,3),
                      (1,1,[],0,[],2,4,b'',None,1),
                      (1,0,[1,0],0,[1],3,5,b'',None,1)])
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'bounds-'+mode)
        self.records.append(dict(test='literal-capacity-atomicity',cases=len(cases),modes=2,invalid_preflights_per_native=9,passed=True))

    def test_actual_compiled_wrong_carry_is_rejected(self):
        source=(ROOT/'lang/bootstrap/bigint.dg').read_text()
        old='let value=x+y+carry;';self.assertEqual(source.count(old),1)
        root=self.work/'bad-carry';(root/'bootstrap').mkdir(parents=True)
        (root/'bootstrap/bigint.dg').write_text(source.replace(old,'let value=x+y;',1))
        exe=self.build(root,'release','bad-carry')
        case=(1,0,[0xffffffff,0xffffffff],0,[1],3,4,b'',2**64,0)
        with self.assertRaisesRegex(AssertionError,'value'):self.run_cases(exe,[case],'bad-carry-native')
        self.records.append(dict(test='real-bad-carry',compiled=True,native_executed=True,rejected_by='value'))


if __name__=='__main__':unittest.main()
