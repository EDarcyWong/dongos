"""Actual Dong bounded shortest ULEB128 u64 decode, against an independent Python model."""
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

SOURCE=ROOT/'lang/bootstrap/uleb128_decode.dg'
OK,INVALID,TRUNCATED,OVERFLOW,NONCANONICAL=0,1,2,3,4
MAX=2**64-1
PREFLIGHTS=13
WRAPPER='''module probe.uleb_export;
import bootstrap.uleb128_decode as u;
export("dong_uleb128_decode") pub unsafe fn decode(input:*const u8,n:usize,value:*u64,consumed:*usize)u64{unsafe{
 return u.decode(slice_from_raw_parts(input,n),value,consumed);
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
extern uint64_t ABI dong_uleb128_decode(const uint8_t*,uint64_t,uint64_t*,uint64_t*);
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
static unsigned invalid(void){
 static uint8_t arena[320] __attribute__((aligned(64))),saved[320];const unsigned total=13;
 const uint8_t*ip=arena+64;const uint64_t ilen=96;
 uint64_t*val=(uint64_t*)(arena+200);uint64_t*con=(uint64_t*)(arena+216);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));arena[64]=0x00;
  memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  const uint8_t*p=ip;uint64_t n=ilen;uint64_t*v=val;uint64_t*c=con;
  switch(i){
   case 0:v=NULL;break;
   case 1:c=NULL;break;
   case 2:v=(uint64_t*)(arena+201);break;
   case 3:c=(uint64_t*)(arena+217);break;
   case 4:v=(uint64_t*)(arena+64);break;
   case 5:c=(uint64_t*)(arena+64);break;
   case 6:v=(uint64_t*)(arena+200);c=(uint64_t*)(arena+200);break;
   case 7:p=NULL;break;
   case 8:p=(const uint8_t*)(uintptr_t)(UINT64_MAX-1);break;
   case 9:v=(uint64_t*)(uintptr_t)(UINT64_MAX-7);break;
   case 10:c=(uint64_t*)(uintptr_t)(UINT64_MAX-7);break;
   case 11:v=(uint64_t*)(arena+128);break;
   default:c=(uint64_t*)(arena+128);break;
  }
  s=dong_uleb128_decode(p,n,v,c);
  if(s!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)s);exit(93);}
 }
 memset(arena,0xa5,sizeof(arena));arena[64]=0x00;
 uint64_t s=dong_uleb128_decode(ip,ilen,val,con);
 if(s!=0||*val!=0||*con!=1){fprintf(stderr,"baseline status %u\n",(unsigned)s);exit(93);}
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t flag,count,preflights=0;read_exact(&flag,8);if(flag)preflights=invalid();read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[2];read_exact(h,sizeof(h));uint64_t n=h[0],ro=h[1];
  if(n>1000000)exit(94);
  uint8_t*ib=malloc(n+64),*copy=malloc(n+1);uint64_t meta[4];
  if(!ib||!copy)exit(95);
  memset(ib,0xa5,n+64);read_exact(ib+32,n);memcpy(copy,ib+32,n);
  const uint8_t*p=n?(const uint8_t*)(ib+32):NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro&&n){pages=(n/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,n);ro_protect(page,pages);p=(const uint8_t*)page;}
  memset(meta,0xa5,sizeof(meta));uint64_t*val=meta+1,*con=meta+2;
  uint64_t s=dong_uleb128_decode(p,n,val,con);
  uint64_t valid=(!n||!memcmp(copy,p,n))&&(ro||(filled(ib,32)&&filled(ib+32+n,32)))&&filled(meta,8)&&filled(meta+3,8);
  if(s)valid=valid&&filled(meta+1,16);
  uint64_t response[4]={s,valid,s?0:*val,s?0:*con};write_exact(response,32);
  if(page)ro_free(page,pages);
  free(ib);free(copy);
 }return 0;
}
'''


def reference(data):
    val=0;shift=0
    for i,b in enumerate(data):
        payload=b&0x7f;cont=b&0x80
        if i==9:
            if cont or payload>1:return OVERFLOW,None,None
            if payload==0:return NONCANONICAL,None,None
            val|=payload<<63;return OK,val,10
        if cont:
            val|=payload<<shift;shift+=7
        else:
            if i!=0 and payload==0:return NONCANONICAL,None,None
            val|=payload<<shift;return OK,val,i+1
    return TRUNCATED,None,None


def uleb_encode(value):
    out=bytearray()
    while True:
        b=value&0x7f;value>>=7
        if value:out.append(b|0x80)
        else:out.append(b);return bytes(out)


def case(data,status=None,value=None,consumed=None,readonly=0):
    data=bytes(data)
    st,val,con=reference(data)
    if status is not None:assert st==status,(status,st,data)
    if value is not None:assert val==value,(value,val,data)
    if consumed is not None:assert con==consumed,(consumed,con,data)
    return dict(data=data,readonly=readonly,status=st,value=val,consumed=con)


class Uleb128DecodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native ULEB128 decode requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/D19'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/uleb_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/uleb_export.dg',roots=roots,mode=mode)
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

    def run_cases(self,exe,cases,label,preflight=True):
        payload=bytearray(struct.pack('<2Q',int(preflight),len(cases)))
        for c in cases:
            payload.extend(struct.pack('<2Q',len(c['data']),c['readonly']))
            payload.extend(c['data'])
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,PREFLIGHTS if preflight else 0)
        offset=8
        for index,c in enumerate(cases):
            status,guard,value,consumed=struct.unpack_from('<4Q',run.stdout,offset);offset+=32
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status'))
            if status==OK:
                self.assertEqual(value,c['value'],(label,index,'value'))
                self.assertEqual(consumed,c['consumed'],(label,index,'consumed'))
            else:
                self.assertEqual((value,consumed),(0,0),(label,index,'outputs-unchanged'))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label,preflight=True):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode,preflight)

    def test_boundaries_and_roundtrip(self):
        values=[0,1,2,0x7f,0x80,0x81,0xff,0x3fff,0x4000,0x1fffff,0x200000,
                0xfffffff,0x10000000,0x7ffffffff,0x800000000,0x3ffffffffff,0x40000000000,
                0x1ffffffffffff,0x2000000000000,0xffffffffffffff,0x100000000000000,
                0x7fffffffffffffff,0x8000000000000000,0xfffffffffffffffe,MAX]
        cases=[]
        for v in values:
            enc=uleb_encode(v);cases.append(case(enc,status=OK,value=v,consumed=len(enc)))
        cases+=[case(b'\x00\x41\x42',status=OK,value=0,consumed=1),
                case(b'\x80\x01\xff',status=OK,value=128,consumed=2),
                case(uleb_encode(MAX)+b'\xde\xad',status=OK,value=MAX,consumed=10)]
        self.run_both(cases,'boundaries')
        self.records.append(dict(test='boundaries-roundtrip',cases=len(cases),modes=2,passed=True))

    def test_noncanonical_truncated_overflow(self):
        cases=[
            case(b'',status=TRUNCATED),case(b'\x80',status=TRUNCATED),
            case(b'\x80\x80',status=TRUNCATED),case(b'\x80'*9,status=TRUNCATED),
            case(b'\x80\x00',status=NONCANONICAL),case(b'\x80\x80\x00',status=NONCANONICAL),
            case(b'\xc0\x00',status=NONCANONICAL),
            case(b'\x80'*9+b'\x00',status=NONCANONICAL),
            case(b'\x80'*9+b'\x02',status=OVERFLOW),case(b'\x80'*10,status=OVERFLOW),
            case(b'\xff'*9+b'\x02',status=OVERFLOW),case(b'\xff'*10,status=OVERFLOW),
            case(b'\xff'*9+b'\x80',status=OVERFLOW),case(b'\x80'*9+b'\x7f',status=OVERFLOW),
            case(b'\x80'*9+b'\x81',status=OVERFLOW),
        ]
        self.run_both(cases,'errors')
        self.records.append(dict(test='noncanonical-truncated-overflow',cases=len(cases),modes=2,passed=True))

    def test_random_against_python(self):
        rng=random.Random(0xD1900);cases=[]
        for i in range(400):
            kind=i%5
            if kind<2:
                v=rng.randrange(0,MAX+1);data=uleb_encode(v)
                if kind==1:data+=bytes(rng.randrange(256)for _ in range(rng.randint(0,4)))
            elif kind==2:
                v=rng.randrange(0,1<<(7*rng.randint(1,8)));data=b'\x80'*rng.randint(1,3)+uleb_encode(v)
            elif kind==3:
                data=uleb_encode(rng.randrange(1,MAX+1))[:-1]
            else:
                data=b'\x80'*9+bytes([rng.choice([0x02,0x03,0x7f,0x80,0xff])])
            cases.append(case(data,readonly=int(i%40==0)))
        self.run_both(cases,'random')
        self.records.append(dict(test='random',cases=len(cases),seed='0xD1900',modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/uleb128_decode.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/uleb_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-10th-overflow','if cont!=0||payload>1{return OVERFLOW;}','if cont!=0{return OVERFLOW;}',
             [case(b'\x80'*9+b'\x02',status=OVERFLOW)],'status'),
            ('bad-early-write','pub unsafe fn decode(input:[]const u8,value:*u64,consumed:*usize)u64{unsafe{',
             'pub unsafe fn decode(input:[]const u8,value:*u64,consumed:*usize)u64{unsafe{\n *value=0;',
             [case(b'\x80\x80',status=TRUNCATED)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            self.run_both(cases,name+'-good',preflight=False)
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode,preflight=False)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))
        # Alias-miss control: removes only the input-output overlap checks (keeping
        # descriptor/alignment/output-mutual-separation), so the prefix and tail alias
        # fixtures in the descriptor preflight are wrongly accepted. Runs the full
        # preflight (preflight=True): the mutant exits 93 at the first alias case.
        alias_old='if overlap(ip,inn,vp,8)||overlap(ip,inn,cp,8)||overlap(vp,8,cp,8){return false;}'
        alias_new='if overlap(vp,8,cp,8){return false;}'
        name='bad-input-output-alias'
        self.run_both([],name+'-good',preflight=True)
        for mode,exe in self.bad_build(name,alias_old,alias_new).items():
            with self.assertRaisesRegex(AssertionError,'status'):self.run_cases(exe,[],name+'-'+mode,preflight=True)
        self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by='status'))


if __name__=='__main__':unittest.main()
