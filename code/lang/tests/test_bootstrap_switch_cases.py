"""Actual Dong switch-case ordering, against Python sorted() and set-based duplicate detection."""
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

ROOT=Path(__file__).resolve().parents[2]
WORKS=ROOT

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

SOURCE=ROOT/'lang/bootstrap/switch_cases.dg'
OK,INVALID,CAPACITY,WORKSPACE=0,1,2,3
I64_MIN,I64_MAX,USIZE_MAX=-2**63,2**63-1,2**64-1
WRAPPER='''module probe.cases_export;
import bootstrap.switch_cases as s;
export("dong_switch_order") pub unsafe fn order(input:*const s.Case,ni:usize,out:*s.Case,no:usize,work:*s.Case,nw:usize,used:*usize)u64{unsafe{
 return s.order(slice_from_raw_parts(input,ni),slice_from_raw_parts(out,no),slice_from_raw_parts(work,nw),used);
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
#else
#include <sys/mman.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef struct {int64_t value;uint64_t label;} Case;
_Static_assert(sizeof(Case)==16&&__builtin_offsetof(Case,label)==8,"Case layout");
extern uint64_t ABI dong_switch_order(const Case*,uint64_t,Case*,uint64_t,Case*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static uint8_t*ro_alloc(uint64_t n){
#ifdef _WIN32
 return VirtualAlloc(NULL,n,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*p=mmap(NULL,n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return p==MAP_FAILED?NULL:p;
#endif
}
static void ro_protect(void*p,uint64_t n){
#ifdef _WIN32
 DWORD old;if(!VirtualProtect(p,n,PAGE_READONLY,&old))exit(98);
#else
 if(mprotect(p,n,PROT_READ))exit(98);
#endif
}
static void ro_free(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;VirtualFree(p,0,MEM_RELEASE);
#else
 munmap(p,n);
#endif
}
/* Bad descriptors: INVALID with every arena byte (work included) unchanged. */
static unsigned invalid(void){
 static uint8_t arena[2048],saved[2048];const unsigned total=15;
 Case*in=(Case*)arena;Case*o=(Case*)(arena+256);Case*w=(Case*)(arena+768);uint64_t*u=(uint64_t*)(arena+1536);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));in[0].value=2;in[0].label=0;in[1].value=1;in[1].label=1;memcpy(saved,arena,sizeof(arena));uint64_t r=0;
  switch(i){
   case 0:r=dong_switch_order(in,2,o,8,w,8,NULL);break;
   case 1:r=dong_switch_order(in,2,o,8,w,8,(uint64_t*)(arena+1540));break;
   case 2:r=dong_switch_order(in,2,o,8,w,8,(uint64_t*)in);break;
   case 3:r=dong_switch_order(in,2,in,8,w,8,u);break;
   case 4:r=dong_switch_order(in,2,o,8,in+1,8,u);break;
   case 5:r=dong_switch_order(in,2,o,8,o+4,8,u);break;
   case 6:r=dong_switch_order(in,2,o,8,w,8,(uint64_t*)w+3);break;
   case 7:r=dong_switch_order((Case*)(arena+4),2,o,8,w,8,u);break;
   case 8:r=dong_switch_order(in,2,(Case*)(arena+260),8,w,8,u);break;
   case 9:r=dong_switch_order(in,2,o,8,(Case*)(arena+772),8,u);break;
   case 10:r=dong_switch_order(NULL,2,o,8,w,8,u);break;
   case 11:r=dong_switch_order(in,2,NULL,8,w,8,u);break;
   case 12:r=dong_switch_order(in,UINT64_MAX/16+1,o,8,w,8,u);break;
   case 13:r=dong_switch_order((Case*)(uintptr_t)(UINT64_MAX-15),2,o,8,w,8,u);break;
   default:r=dong_switch_order(in,2,o,8,(Case*)(uintptr_t)(UINT64_MAX-15),8,u);break;
  }
  if(r!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)r);exit(93);}
 }
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[4];read_exact(h,sizeof(h));uint64_t ni=h[0],no=h[1],nw=h[2],ro=h[3];
  if(ni>300000||no>300000||nw>300000)exit(94);
  uint64_t ib=ni*16;uint8_t*in=malloc(ib+64),*copy=malloc(ib+1);Case*out=malloc((no+4)*16),*work=malloc((nw+4)*16);uint64_t meta[3];
  if(!in||!copy||!out||!work)exit(95);
  memset(in,0xa5,ib+64);read_exact(in+32,ib);memcpy(copy,in+32,ib);
  const Case*c=ni?(const Case*)(in+32):NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro&&ni){pages=(ib/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,ib);ro_protect(page,pages);c=(const Case*)page;}
  memset(out,0xa5,(no+4)*16);memset(work,0xa5,(nw+4)*16);memset(meta,0xa5,sizeof(meta));uint64_t*used=meta+1;
  uint64_t r=dong_switch_order(c,ni,no?out+2:NULL,no,nw?work+2:NULL,nw,used);
  uint64_t valid=(!ib||!memcmp(copy,c,ib))&&(ro||(filled(in,32)&&filled(in+32+ib,32)))&&filled(out,32)&&filled(out+2+no,32)&&
    filled(work,32)&&filled(work+2+nw,32)&&filled(meta,8)&&filled(meta+2,8);
  if(r)valid=valid&&filled(out+2,no*16)&&filled(used,8);
  else valid=valid&&*used==ni&&filled(out+2+ni,(no-ni)*16);
  uint64_t response[3]={r,valid,r?0:*used};write_exact(response,24);write_exact(out+2,r?0:ni*16);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(out);free(work);
 }return 0;
}
'''


def case(cases,no=None,nw=None,readonly=0,status=None):
    n=len(cases);no=n if no is None else no;nw=n if nw is None else nw
    if no<n:st=CAPACITY
    elif nw<n:st=WORKSPACE
    elif len({v for v,_ in cases})!=n:st=INVALID
    else:st=OK
    if status is not None:assert st==status,(status,st,cases)
    return dict(cases=cases,no=no,nw=nw,readonly=readonly,status=st,sorted=sorted(cases)if st==OK else None)


class SwitchCasesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native switch ordering requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/C11'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/cases_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/cases_export.dg',roots=roots,mode=mode)
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
        for c in cases:
            payload.extend(struct.pack('<4Q',len(c['cases']),c['no'],c['nw'],c['readonly']))
            for v,l in c['cases']:payload.extend(struct.pack('<qQ',v,l))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,15)
        offset=8
        for index,c in enumerate(cases):
            status,guard,used=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status'))
            if not status:
                n=len(c['cases']);got=[struct.unpack_from('<qQ',run.stdout,offset+16*i)for i in range(n)];offset+=16*n
                self.assertEqual(used,n,(label,index,'used'))
                self.assertEqual([v for v,_ in got],[v for v,_ in c['sorted']],(label,index,'order'))
                self.assertEqual(got,c['sorted'],(label,index,'pairing'))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def test_random_cases_against_sorted_and_set(self):
        rng=random.Random(0xC11C);cases=[]
        pools=[lambda:rng.randint(-20,20),lambda:rng.randint(I64_MIN,I64_MAX),lambda:rng.choice([I64_MIN,I64_MAX,-1,0,1,I64_MIN+1,I64_MAX-1])]
        for i in range(500):
            n=rng.randint(0,40);pick=rng.choice(pools)
            values=[pick()for _ in range(n)]
            if i%2:values=list(dict.fromkeys(values))                        # half without duplicates
            items=[(v,rng.randrange(USIZE_MAX+1))for v in values]
            cases.append(case(items,readonly=int(i%50==0)))
            if i%5==0:cases.append(case(items,no=len(items)+4,nw=len(items)+2))
        big=rng.sample(range(-10**12,10**12),100000);cases.append(case([(v,i)for i,v in enumerate(big)],readonly=1))
        self.run_both(cases,'random')
        self.assertGreater(sum(c['status']==OK for c in cases),250);self.assertGreater(sum(c['status']==INVALID for c in cases),100)
        self.records.append(dict(test='random-sorted-set',cases=len(cases),seed='0xC11C',modes=2,passed=True))

    def test_extremes_duplicates_labels_and_capacity(self):
        cases=[case([],status=OK),case([],no=0,nw=0,status=OK),case([(5,7)],status=OK),
               case([(I64_MAX,0),(I64_MIN,1),(0,2),(-1,3),(1,4)],status=OK),
               case([(i,i+30)for i in range(30,-30,-1)],status=OK),                       # reverse order
               case([(-1,USIZE_MAX),(0,USIZE_MAX),(1,USIZE_MAX)],status=OK),                 # identical labels are fine
               case([(I64_MIN,9),(I64_MIN+1,8),(I64_MAX-1,7),(I64_MAX,6)][::-1],status=OK),
               case([(2**62,0),(-2**62,1),(2**63-1,2),(-2**63,3)],status=OK)]
        cases+=[case([(3,1),(3,1)],status=INVALID),case([(3,1),(3,2)],status=INVALID),case([(1,0),(2,0),(3,0),(1,9)],status=INVALID),
                case([(I64_MIN,0),(5,1),(I64_MIN,2)],status=INVALID),case([(I64_MAX,0),(0,1),(-1,2),(I64_MAX,3)],status=INVALID),
                case([(0,0),(-0,1)],status=INVALID),case([(i%7,i)for i in range(20)],status=INVALID)]
        for items in ([(1,0)],[(2,0),(1,1)],[(i,i)for i in range(9)],[(1,0),(1,1)]):
            n=len(items);cases+=[case(items,no=n-1),case(items,nw=n-1),case(items,no=n-1,nw=n-1),case(items,no=0,nw=0)]
        self.run_both(cases,'bounds')
        self.records.append(dict(test='extremes-duplicates-capacity',cases=len(cases),invalid_preflights_per_native=15,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/switch_cases.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/cases_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-unsigned-order','fn less(a:i64,b:i64)bool{return a<b;}','fn less(a:i64,b:i64)bool{return (a as u64)<(b as u64);}',
             [case([(1,0),(-1,1),(0,2)])],'order'),
            ('bad-adjacent-input-dup','i=1;while i<n{if work[i].value==work[i-1].value{return INVALID;}i+=1;}',
             'i=1;while i<n{if input[i].value==input[i-1].value{return INVALID;}i+=1;}',
             [case([(4,0),(9,1),(4,2)],status=INVALID)],'status'),
            ('bad-label-pairing','i=0;while i<n{out[i]=work[i];i+=1;}','i=0;while i<n{out[i]=Case{value:work[i].value,label:input[i].label};i+=1;}',
             [case([(3,30),(1,10),(2,20)])],'pairing'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
