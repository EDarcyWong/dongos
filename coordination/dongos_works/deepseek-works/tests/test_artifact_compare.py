"""Actual Dong byte-exact artifact comparison, against an independent Python model."""
import hashlib
import json
import os
import shutil
from pathlib import Path
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

SOURCE=WORKS/'deepseek-works/src/bootstrap/artifact_compare.dg'
OK,INVALID=0,1
PREFLIGHTS=11
WRAPPER='''module probe.artifact_export;
import bootstrap.artifact_compare as u;
export("dong_artifact_compare") pub unsafe fn compare(ep:*const u8,en:usize,ap:*const u8,an:usize,out:*u.Result)u64{unsafe{
 return u.compare(slice_from_raw_parts(ep,en),slice_from_raw_parts(ap,an),out);
}}
'''
HARNESS=r'''
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
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
typedef struct {uint64_t kind,offset,expected,actual;} Result;
extern uint64_t ABI dong_artifact_compare(const uint8_t*,uint64_t,const uint8_t*,uint64_t,Result*);
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
 (void)n;if(!VirtualFree(p,0,MEM_RELEASE))exit(98);
#else
 if(munmap(p,n))exit(98);
#endif
}
typedef struct {uint8_t*base;const uint8_t*p;uint8_t*copy;uint64_t n;int ro;uint8_t*page;uint64_t pages;} View;
static void make_view(View*v,const uint8_t*data,uint64_t n,int ro){
 v->base=NULL;v->page=NULL;v->pages=0;v->ro=ro;v->n=n;v->p=NULL;v->copy=NULL;
 if(!n)return;
 v->copy=malloc(n);if(!v->copy)exit(95);memcpy(v->copy,data,n);
 if(ro){
  v->pages=(n/4096+2)*4096;v->page=ro_alloc(v->pages);if(!v->page)exit(95);
  memcpy(v->page,v->copy,n);ro_protect(v->page,v->pages);v->p=v->page;
 }else{
  v->base=malloc(n+64);if(!v->base)exit(95);
  memset(v->base,0xa5,n+64);memcpy(v->base+32,data,n);v->p=v->base+32;
 }
}
static int verify_view(const View*v){
 if(!v->n)return 1;
 if(memcmp(v->p,v->copy,v->n))return 0;
 if(!v->ro&&(!filled(v->base,32)||!filled(v->base+32+v->n,32)))return 0;
 return 1;
}
static void free_view(View*v){
 if(v->page)ro_free(v->page,v->pages);
 free(v->base);free(v->copy);
 v->base=v->page=v->copy=NULL;
}
static unsigned invalid(void){
 static uint8_t arena[512] __attribute__((aligned(64))),saved[512];
 const unsigned total=11;
 const uint8_t*ep=arena+64;const uint64_t elen=96;
 const uint8_t*ap=arena+192;const uint64_t alen=96;
 Result*out=(Result*)(arena+320);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));arena[64]=0x00;arena[192]=0x00;
  memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  const uint8_t*pe=ep,*pa=ap;uint64_t en=elen,an=alen;Result*o=out;
  switch(i){
   case 0:o=NULL;break;
   case 1:o=(Result*)(arena+321);break;
   case 2:o=(Result*)(uintptr_t)(UINT64_MAX-31);break;
   case 3:pe=NULL;break;
   case 4:pa=NULL;break;
   case 5:pe=(const uint8_t*)(uintptr_t)(UINT64_MAX-1);en=8;break;
   case 6:pa=(const uint8_t*)(uintptr_t)(UINT64_MAX-1);an=8;break;
   case 7:o=(Result*)(arena+64);break;
   case 8:o=(Result*)(arena+64+96-8);break;
   case 9:o=(Result*)(arena+192);break;
   default:o=(Result*)(arena+192+96-8);break;
  }
  s=dong_artifact_compare(pe,en,pa,an,o);
  if(s!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)s);exit(93);}
 }
 memset(arena,0xa5,sizeof(arena));arena[64]=0x00;arena[192]=0x00;
 uint64_t s=dong_artifact_compare(ep,elen,ap,alen,(Result*)(arena+320));
 if(s!=0){fprintf(stderr,"baseline status %u\n",(unsigned)s);exit(93);}
 Result*o=(Result*)(arena+320);
 if(o->kind!=0||o->offset!=96||o->expected!=256||o->actual!=256){fprintf(stderr,"baseline fields\n");exit(93);}
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t flag,count,preflights=0;read_exact(&flag,8);if(flag)preflights=invalid();read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t mode,delta,le,roe,la,roa;
  read_exact(&mode,8);read_exact(&delta,8);read_exact(&le,8);read_exact(&roe,8);
  read_exact(&la,8);read_exact(&roa,8);
  if(le>1000000||la>1000000)exit(94);
  uint8_t*de=NULL,*da=NULL,*master=NULL;uint64_t ml=0;
  if(mode==0||mode==3||mode==4){
   de=malloc(le?le:1);da=malloc(la?la:1);if(!de||!da)exit(95);
   read_exact(de,le);read_exact(da,la);
  }else if(mode==1){
   if(la!=le)exit(94);
   de=malloc(le?le:1);if(!de)exit(95);read_exact(de,le);da=de;
  }else{
   ml=(delta+la>le)?delta+la:le;
   master=malloc(ml?ml:1);if(!master)exit(95);read_exact(master,ml);
  }
  View ve,va;uint8_t*dummy=NULL;
  if(mode==0||mode==3||mode==4){make_view(&ve,de,le,(int)roe);make_view(&va,da,la,(int)roa);}
  else if(mode==1){make_view(&ve,de,le,(int)roe);memset(&va,0,sizeof(va));}
  else{make_view(&ve,master,ml,(int)roe);memset(&va,0,sizeof(va));}
  const uint8_t*pe=ve.p,*pa;
  if(mode==0||mode==3||mode==4)pa=va.p;else if(mode==1)pa=ve.p;else pa=ve.p+delta;
  uint64_t en=le,an=la;
  if(mode==3)pe=NULL;
  if(mode==4)pa=NULL;
  _Alignas(8) uint8_t fx[48];memset(fx,0xa5,48);
  uint64_t s=dong_artifact_compare(pe,en,pa,an,(Result*)(fx+8));
  int ok=verify_view(&ve)&&verify_view(&va)&&filled(fx,8)&&filled(fx+40,8);
  if(s)ok=ok&&filled(fx,48);
  Result*r=(Result*)(fx+8);
  uint64_t resp[6]={s,(uint64_t)ok,r->kind,r->offset,r->expected,r->actual};
  write_exact(resp,48);
  free_view(&ve);if(mode==0||mode==3||mode==4)free_view(&va);
  free(de);if(mode!=1)free(da);free(master);(void)dummy;
 }return 0;
}
'''


def reference(e,a):
    n=min(len(e),len(a))
    for i in range(n):
        if e[i]!=a[i]:return (1,i,e[i],a[i])
    if len(e)==len(a):return (0,len(e),256,256)
    if len(e)<len(a):return (2,n,256,a[n])
    return (2,n,e[n],256)


def case(e,a,mode=0,delta=0,ro_e=0,ro_a=0):
    """Build one request case; e/a may be None to model a NULL pointer with nonzero length."""
    if e is None or a is None:
        assert (e is None)!=(a is None)
        kept=bytes(a if e is None else e)
        assert kept
        m=3 if e is None else 4
        filler=bytes(len(kept))
        payload=filler+kept if e is None else kept+filler
        return dict(e=e,a=a,mode=m,delta=0,ro_e=ro_e,ro_a=ro_a,
                    status=INVALID,payload=payload,en=len(kept),an=len(kept))
    e=bytes(e);a=bytes(a)
    if mode==0:payload=e+a
    elif mode==1:
        assert len(e)==len(a),('same-pointer needs equal lengths',)
        payload=e
    else:
        le,la=len(e),len(a);ml=max(le,delta+la)
        M=bytearray(b'\xa5'*ml)
        for i,b in enumerate(e):
            assert M[i] in (0xa5,b),(mode,'master conflict',i)
            M[i]=b
        for i,b in enumerate(a):
            assert M[delta+i] in (0xa5,b),(mode,'master conflict',delta+i)
            M[delta+i]=b
        payload=bytes(M)
    return dict(e=e,a=a,mode=mode,delta=delta,ro_e=ro_e,ro_a=ro_a,status=OK,payload=payload)


def pack_case(c):
    return struct.pack('<6Q',c['mode'],c['delta'],c.get('en',len(c['e'] or b'')),
                       c['ro_e'],c.get('an',len(c['a'] or b'')),c['ro_a'])+c['payload']


class ArtifactCompareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native artifact compare requires NASM/GCC')
        cls.work=WORKS/'deepseek-works/build/D23'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.input_paths=[SOURCE,SOURCE.with_suffix('.md'),Path(__file__)]
        cls.inputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in cls.input_paths}
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copyfile(SOURCE,cls.src_root/'bootstrap/artifact_compare.dg')
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/artifact_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/artifact_export.dg',roots=roots,mode=mode)
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
        assert cls.inputs=={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in cls.input_paths},'inputs changed'
        files={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in cls.work.rglob('*')if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,artifact_sha256=files,
            records=cls.records,integrated=False,OS_VM_built=False),indent=2)+'\n')

    def run_cases(self,exe,cases,label,preflight=True):
        payload=bytearray(struct.pack('<2Q',int(preflight),len(cases)))
        for c in cases:payload.extend(pack_case(c))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,PREFLIGHTS if preflight else 0)
        offset=8
        for index,c in enumerate(cases):
            status,valid,kind,off,eb,ab=struct.unpack_from('<6Q',run.stdout,offset);offset+=48
            self.assertEqual(valid,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status'))
            if status==OK:
                want=reference(c['e'],c['a'])
                self.assertEqual((kind,off,eb,ab),want,(label,index,'kind-offset-bytes'))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label,preflight=True):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode,preflight)

    def test_identical_alias_overlap(self):
        data16=bytes(range(16))+bytes([0xf0,0x0f,0x55,0xaa,0x01,0x80,0x7f,0xff])
        cases=[
            case(b'',b''),
            case(data16,data16,mode=1),
            case(b'ABCD',b'CDEF',mode=2,delta=2),
            case(data16,data16),
            case(b'\x00\x11\x22',b'\xff\x11\x22'),
            case(b'\xaa\xbb\xcc\xdd',b'\xaa\x77\xcc\xdd'),
            case(b'\x01\x02\x03\x04\x05\x06\x07\x08',b'\x01\x02\x03\x04\x05\x06\x07\x09'),
            case(b'\xff\x00',b'\x00\x00'),
            case(b'abc',b'abcd'),
            case(b'abcd',b'abc'),
            case(b'',b'Z'),
            case(b'Z',b''),
            case(b'\x01\x02\x03',b'\x01\x04'),
            case(b'AAAAA',b'AAABB',mode=2,delta=2),
            case(b'AAA',b'AAAAA\xbb',mode=2,delta=2),
        ]
        self.run_both(cases,'identity')
        self.records.append(dict(test='identical-alias-overlap',cases=len(cases),modes=2,passed=True))

    def test_boundaries_4096_4097(self):
        b4096=bytes((i*31+7)&0xff for i in range(4096))
        b4097=b4096+b'\x5a'
        last=b4096[:-1]+bytes([b4096[-1]^0xff])
        cases=[
            case(b4096,b4096,ro_e=1,ro_a=1),
            case(b4096,last,ro_e=1,ro_a=1),
            case(b4097,b4097,ro_e=1),
            case(b4097,b4096+b'\xa5',ro_a=1),
            case(b'\x00\xff\x80',b'\x00\xff\x7f'),
        ]
        self.run_both(cases,'boundaries')
        self.records.append(dict(test='boundaries-4096-4097',cases=len(cases),modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/artifact_compare.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/artifact_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            # Comparison loop misses the last byte of the common prefix: equal-length
            # inputs differing only in the final byte are wrongly reported identical.
            ('bad-skip-last-common-byte','while i<n{','while i+1<n{',
             [case(b'ABCDEFGH',b'ABCDEFGX')],'kind-offset-bytes'),
            # out.kind is modified before validation fails: with out legal and one
            # input NULL non-empty (no dereference fixture) the bad body still
            # returns INVALID but the published Result/guard region is no longer
            # intact, rejected by the full-fixture atomicity check.
            ('bad-early-out-kind-write','if !valid(expected,actual,out){return INVALID;}',
             '(*out).kind=9;if !valid(expected,actual,out){return INVALID;}',
             [case(None,b'\x01\x02\x03\x04')],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            self.run_both(cases,name+'-good',preflight=False)
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode,preflight=False)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))
        alias_old='if overlap(op,32,ep,expected.len)||overlap(op,32,ap,actual.len){return false;}'
        alias_new='if overlap(op,32,ep,1)||overlap(op,32,ap,1){return false;}'
        name='bad-input-tail-alias'
        self.run_both([],name+'-good',preflight=True)
        for mode,exe in self.bad_build(name,alias_old,alias_new).items():
            run=subprocess.run([str(exe)],input=struct.pack('<2Q',1,0),capture_output=True,timeout=30)
            self.assertEqual(run.returncode,93)
            self.assertEqual(run.stderr.replace(b'\r\n',b'\n'),b'invalid preflight 8 status 0\n')
        self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,
                                 rejected_by='expected-input-tail-preflight-8'))



if __name__=='__main__':unittest.main()
