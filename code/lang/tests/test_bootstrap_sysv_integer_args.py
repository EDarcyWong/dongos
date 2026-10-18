"""Actual Dong SysV INTEGER argument planning, against an independent Python state model."""
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

SOURCE=ROOT/'lang/bootstrap/sysv_integer_args.dg'
OK,INVALID,CAPACITY=0,1,2
WRAPPER='''module probe.sysv_export;
import bootstrap.sysv_integer_args as s;
export("dong_sysv_plan") pub unsafe fn plan(kinds:*const u8,nk:usize,out:*s.Location,no:usize,result:*s.Result)u64{unsafe{
 return s.plan(slice_from_raw_parts(kinds,nk),slice_from_raw_parts(out,no),result);
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
typedef struct {uint64_t kind,index;} Location;
typedef struct {uint64_t used,stack_bytes;} Result;
_Static_assert(sizeof(Location)==16&&sizeof(Result)==16&&__builtin_offsetof(Result,stack_bytes)==8,"layout");
extern uint64_t ABI dong_sysv_plan(const uint8_t*,uint64_t,Location*,uint64_t,Result*);
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
/* Bad descriptors: INVALID with every arena byte unchanged. */
static unsigned invalid(void){
 static uint8_t arena[2048],saved[2048];const unsigned total=12;
 uint8_t*k=arena;Location*o=(Location*)(arena+256);Result*r=(Result*)(arena+1024);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));k[0]=0;k[1]=1;memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_sysv_plan(k,2,o,8,NULL);break;
   case 1:s=dong_sysv_plan(k,2,o,8,(Result*)(arena+1028));break;
   case 2:s=dong_sysv_plan(k,2,o,8,(Result*)k);break;
   case 3:s=dong_sysv_plan(k,2,(Location*)k,8,r);break;
   case 4:s=dong_sysv_plan(k,2,o,8,(Result*)(o+3));break;
   case 5:s=dong_sysv_plan(k,2,(Location*)(arena+260),8,r);break;
   case 6:s=dong_sysv_plan(NULL,2,o,8,r);break;
   case 7:s=dong_sysv_plan(k,2,NULL,8,r);break;
   case 8:s=dong_sysv_plan(k,2,o,UINT64_MAX/16+1,r);break;
   case 9:s=dong_sysv_plan((const uint8_t*)(uintptr_t)(UINT64_MAX-1),4,o,8,r);break;
   case 10:s=dong_sysv_plan(k,2,(Location*)(uintptr_t)(UINT64_MAX-15),2,r);break;
   default:s=dong_sysv_plan(k,2,o,8,(Result*)(uintptr_t)(UINT64_MAX-7));break;
  }
  if(s!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)s);exit(93);}
 }
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[3];read_exact(h,sizeof(h));uint64_t nk=h[0],no=h[1],ro=h[2];
  if(nk>1000000||no>2000000)exit(94);
  uint8_t*in=malloc(nk+64),*copy=malloc(nk+1);Location*out=malloc((no+4)*16);uint64_t meta[6];
  if(!in||!copy||!out)exit(95);
  memset(in,0xa5,nk+64);read_exact(in+32,nk);memcpy(copy,in+32,nk);
  const uint8_t*k=nk?in+32:NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro&&nk){pages=(nk/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,nk);ro_protect(page,pages);k=page;}
  memset(out,0xa5,(no+4)*16);memset(meta,0xa5,sizeof(meta));Result*r=(Result*)(meta+2);
  uint64_t s=dong_sysv_plan(k,nk,no?out+2:NULL,no,r);
  uint64_t valid=(!nk||!memcmp(copy,k,nk))&&(ro||(filled(in,32)&&filled(in+32+nk,32)))&&filled(out,32)&&filled(out+2+no,32)&&
    filled(meta,16)&&filled(meta+4,16);
  if(s)valid=valid&&filled(out+2,no*16)&&filled(r,16);
  else valid=valid&&r->used<=no&&filled(out+2+r->used,(no-r->used)*16);
  uint64_t response[4]={s,valid,s?0:r->used,s?0:r->stack_bytes};write_exact(response,32);write_exact(out+2,s?0:r->used*16);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(out);
 }return 0;
}
'''


def model(kinds):
    """Independent SysV INTEGER-class state model: (status, locations, stack_bytes)."""
    free=['rdi','rsi','rdx','rcx','r8','r9'];names={n:i for i,n in enumerate(free)}
    locations,stack=[],0
    for k in kinds:
        if k not in(0,1):return INVALID,None,None
        need=1 if k==0 else 2
        if len(free)>=need:
            for _ in range(need):locations.append((0,names[free.pop(0)]))
        else:
            for _ in range(need):locations.append((1,stack));stack+=8
    return OK,locations,-(-stack//16)*16


def case(kinds,no=None,readonly=0,status=None):
    st,locations,stack=model(kinds)
    if no is None:no=len(locations)if locations is not None else 4
    if st==OK and no<len(locations):st=CAPACITY
    if status is not None:assert st==status,(status,st,kinds)
    return dict(kinds=bytes(kinds),no=no,readonly=readonly,status=st,locations=locations,stack=stack)


class SysvIntegerArgsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native SysV planning requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/C8'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/sysv_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/sysv_export.dg',roots=roots,mode=mode)
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
            records=cls.records,full_sysv_abi=False,integrated=False,OS_VM_built=False),indent=2)+'\n')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:payload.extend(struct.pack('<3Q',len(c['kinds']),c['no'],c['readonly']));payload.extend(c['kinds'])
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,12)
        offset=8
        for index,c in enumerate(cases):
            status,guard,used,stack=struct.unpack_from('<4Q',run.stdout,offset);offset+=32
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status'))
            if not status:
                flat=struct.unpack_from('<%dQ'%(2*used),run.stdout,offset);offset+=16*used
                self.assertEqual([(flat[2*i],flat[2*i+1])for i in range(used)],c['locations'],(label,index,'locations',c['kinds']))
                self.assertEqual(stack,c['stack'],(label,index,'stack_bytes'))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def test_random_signatures_against_state_model(self):
        rng=random.Random(0xC8A6);cases=[]
        for i in range(400):
            kinds=[rng.choice([0,0,1])for _ in range(rng.randint(0,20))]
            cases+=[case(kinds,readonly=int(i%40==0)),case(kinds,no=len(model(kinds)[1])+3)]
        cases.append(case([rng.choice([0,1])for _ in range(100000)],readonly=1))
        self.run_both(cases,'random')
        self.records.append(dict(test='random-signatures',cases=len(cases),seed='0xC8A6',modes=2,passed=True))

    def test_register_fallback_stack_rounding_invalid_and_capacity(self):
        cases=[case([],status=OK),case([],no=0,status=OK),case([0]*6,status=OK),case([0]*7,status=OK),case([1]*3,status=OK),
               case([1]*4,status=OK),case([0]*5+[1]+[0],status=OK),             # pair falls back, rcx-free r9 still used
               case([0]*5+[1]+[0,0],status=OK),case([0]*5+[1,1,0],status=OK),case([0,1,1,0,1,0],status=OK),
               case([1,1,0,1],status=OK),case([0]*4+[1,0,1],status=OK),case([0]*6+[1],status=OK),case([0]*6+[0,1],status=OK),
               case([0]*6+[0,0,0],status=OK),case([1]*3+[0]*3,status=OK)]
        # The key fallback: 5 scalars, then a pair (stack, offsets 0/8), then a scalar in R9.
        st,locations,stack=model([0]*5+[1,0])
        self.assertEqual(locations,[(0,0),(0,1),(0,2),(0,3),(0,4),(1,0),(1,8),(0,5)]);self.assertEqual(stack,16)
        self.assertEqual(model([0]*6+[0])[2],16);self.assertEqual(model([0]*6+[0,0,0])[2],32)
        for bad in (2,3,7,0x80,0xff):
            cases+=[case([bad],status=INVALID),case([0]*9+[bad],status=INVALID),case([bad,0,1],no=0,status=INVALID)]
        for kinds in ([0],[1],[0]*7,[0]*5+[1,0],[1]*5):
            need=len(model(kinds)[1])
            cases+=[case(kinds,no=need-1,status=CAPACITY),case(kinds,no=0,status=CAPACITY),case(kinds,no=need+9,status=OK)]
        self.run_both(cases,'bounds')
        self.records.append(dict(test='fallback-rounding-invalid-capacity',cases=len(cases),invalid_preflights_per_native=12,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/sysv_integer_args.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/sysv_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            # A pair that falls back to the stack also burns the last lone register (both passes).
            ('bad-burn-register','else{out[at]=Location{kind:STACK,index:stack};out[at+1]=Location{kind:STACK,index:stack+8};stack+=16;}',
             'else{out[at]=Location{kind:STACK,index:stack};out[at+1]=Location{kind:STACK,index:stack+8};stack+=16;regs=REGISTERS;}',
             [case([0]*5+[1,0])],'locations'),
            ('bad-no-rounding','let stack_bytes=(stack+15)&~(15 as usize);','let stack_bytes=stack;',[case([0]*7)],'stack_bytes'),
            # Writes a location during validation, before a later bad kind is seen.
            ('bad-early-write','if regs<REGISTERS{regs+=1;}else{if stack>MAX-8{return INVALID;}stack+=8;}',
             'if out.len!=0{out[0]=Location{kind:REGISTER,index:0};}if regs<REGISTERS{regs+=1;}else{if stack>MAX-8{return INVALID;}stack+=8;}',
             [case([0,9],no=4,status=INVALID)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
