"""Actual Dong single-line diagnostic formatting, against independent Python bytes concatenation."""
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
SOURCE=ROOT/'lang/bootstrap/diagnostic_format.dg'
OK,INVALID,CAPACITY=0,1,2
USIZE_MAX=2**64-1
# Temporary export wrapper; the module itself exports nothing.
WRAPPER='''module probe.diagnostic_export;
import bootstrap.diagnostic_format as d;
export("dong_diagnostic_render") pub unsafe fn render(path:*const u8,np:usize,line:usize,column:usize,
 code:*const u8,nc:usize,message:*const u8,nm:usize,out:*u8,no:usize,written:*usize)u64{unsafe{
 return d.render(slice_from_raw_parts(path,np),line,column,slice_from_raw_parts(code,nc),
  slice_from_raw_parts(message,nm),slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_diagnostic_render(const uint8_t*,uint64_t,uint64_t,uint64_t,const uint8_t*,uint64_t,
 const uint8_t*,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
#define FAKE(x) ((const uint8_t*)(uintptr_t)(x))
/* Bad descriptors / impossible lengths: INVALID with every arena byte unchanged.
   Fake pointers are only passed where rejection must happen before any read. */
static unsigned invalid(void){
 static uint8_t arena[4096],saved[4096];const unsigned total=24;
 uint8_t*p=arena,*c=arena+64,*m=arena+128,*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(p,"a.dg",4);memcpy(c,"E0001",5);memcpy(m,"msg",3);
  memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_diagnostic_render(p,4,1,1,c,5,m,3,o,64,NULL);break;
   case 1:s=dong_diagnostic_render(p,4,1,1,c,5,m,3,o,64,(uint64_t*)(arena+2052));break;
   case 2:s=dong_diagnostic_render(p,4,1,1,c,5,m,3,o,64,(uint64_t*)(o+8));break;
   case 3:s=dong_diagnostic_render(p,4,1,1,c,5,m,3,o,64,(uint64_t*)p);break;
   case 4:s=dong_diagnostic_render(p,4,1,1,c,5,m,3,o,64,(uint64_t*)c);break;
   case 5:s=dong_diagnostic_render(p,4,1,1,c,5,m,3,o,64,(uint64_t*)m);break;
   case 6:s=dong_diagnostic_render(p,4,1,1,c,5,m,3,p,64,w);break;
   case 7:s=dong_diagnostic_render(p,4,1,1,c,5,m,3,c+2,8,w);break;
   case 8:s=dong_diagnostic_render(p,4,1,1,c,5,m,3,m-60,64,w);break;
   case 9:s=dong_diagnostic_render(NULL,4,1,1,c,5,m,3,o,64,w);break;
   case 10:s=dong_diagnostic_render(p,4,1,1,NULL,5,m,3,o,64,w);break;
   case 11:s=dong_diagnostic_render(p,4,1,1,c,5,NULL,3,o,64,w);break;
   case 12:s=dong_diagnostic_render(p,4,1,1,c,5,m,3,NULL,64,w);break;
   case 13:s=dong_diagnostic_render(FAKE(UINT64_MAX),2,1,1,c,5,m,3,o,64,w);break;
   case 14:s=dong_diagnostic_render(p,4,1,1,c,5,FAKE(UINT64_MAX-1),3,o,64,w);break;
   case 15:s=dong_diagnostic_render(p,4,1,1,c,5,m,3,(uint8_t*)(uintptr_t)(UINT64_MAX-7),64,w);break;
   case 16:s=dong_diagnostic_render(p,4,1,1,c,5,m,3,o,64,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   /* Valid spans whose total length overflows: rejected before the fake message is read. */
   case 17:s=dong_diagnostic_render(p,4,1,1,c,5,FAKE(1),UINT64_MAX-1,o,64,w);break;
   case 18:s=dong_diagnostic_render(FAKE(1),UINT64_MAX-50,USIZE_MAX_,USIZE_MAX_,c,5,m,3,o,64,w);break;
   case 19:s=dong_diagnostic_render(FAKE(8),UINT64_MAX-60,1,1,c,5,FAKE(8),20,o,64,w);break;
   /* Value errors that must be found without touching fake content. */
   case 20:s=dong_diagnostic_render(FAKE(8),100,0,1,c,5,m,3,o,64,w);break;
   case 21:s=dong_diagnostic_render(FAKE(8),100,1,0,c,5,m,3,o,64,w);break;
   case 22:s=dong_diagnostic_render(FAKE(8),100,1,1,FAKE(4096),4,m,3,o,64,w);break;
   default:s=dong_diagnostic_render(p,0,1,1,c,5,FAKE(8),100,o,64,w);break;
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
  /* np nc nm line column cap readonly share nullout */
  uint64_t h[9];read_exact(h,sizeof(h));uint64_t np=h[0],nc=h[1],nm=h[2],cap=h[6-1],ro=h[6],share=h[7],nullout=h[8];
  if(np>200000||nc>64||nm>200000||cap>500000)exit(94);
  uint64_t n=np+nc+nm;uint8_t*in=malloc(n+64),*copy=malloc(n+1),*out=malloc(cap+64);uint64_t meta[3];
  if(!in||!copy||!out)exit(95);
  memset(in,0xa5,n+64);read_exact(in+32,n);memcpy(copy,in+32,n);
  uint8_t*base=in+32,*page=NULL;uint64_t pages=0;
  if(ro){pages=(n/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,n);ro_protect(page,pages);base=page;}
  /* share=1: message is the same bytes as path; share=2: path/code/message overlap one buffer
     (code = first nc bytes, path = whole buffer, message = tail). */
  const uint8_t*p=base,*c=base+np,*m=base+np+nc;uint64_t mp=np,mc=nc,mm=nm;
  if(share==1){m=p;mm=np;}
  if(share==2){c=base;p=base;mp=n;m=base+nc;mm=n-nc;}
  if(!np&&share==0)p=NULL;
  if(!nm&&share==0)m=NULL;
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nullout?NULL:out+32;
  uint64_t s=dong_diagnostic_render(p,mp,h[3],h[4],c,mc,m,mm,o,cap,written);
  uint64_t valid=!memcmp(copy,base,n)&&(ro||(filled(in,32)&&filled(in+32+n,32)))&&filled(out,32)&&filled(out+32+cap,32)&&
    filled(meta,8)&&filled(meta+2,8);
  if(s)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={s,valid,s?0:*written};write_exact(response,24);write_exact(out+32,cap);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(out);
 }return 0;
}
'''.replace('USIZE_MAX_','UINT64_MAX')


def expected(path,line,column,code,message):
    """Independent reference: plain bytes concatenation and Python's own integer formatting."""
    return path+b':'+str(line).encode()+b':'+str(column).encode()+b': '+code+b': '+message+b'\n'


def item(path,line,column,code,message,cap=None,status=None,readonly=0,share=0,nullout=0):
    p,c,m=path,code,message
    if share==1:m=p
    if share==2:p=c+m;c=c;m=m
    valid=(line>0 and column>0 and len(p)>0 and len(c)==5 and c[:1]==b'E' and all(48<=x<=57 for x in c[1:])
           and not any(x in(0,10,13)for x in p+m))
    text=expected(p,line,column,c,m)if valid else None
    if cap is None:cap=len(text)if text else 16
    if status is None:status=OK if valid and len(text)<=cap else (CAPACITY if valid else INVALID)
    return dict(path=path,code=code,message=message if share!=1 else b'',line=line,column=column,cap=cap,
                readonly=readonly,share=share,nullout=nullout,status=status,text=text if status==OK else None)


SAMPLES=['src/main.dg','lang/编译器/类型.dg','路径 with space/x.dg','émoji😀/a.dg','C:\\proj\\mod.dg','a','./x/../y.dg']
MESSAGES=['expected identifier','类型不匹配：期望 u64，实际 bool','emoji ✅🚀 ok','','tab\there','x'*300,'混合 mixed «quotes» "q" \'s\'']
NUMBERS=[1,9,10,99,100,999,1000,2**32-1,2**32,2**63-1,2**63,USIZE_MAX-1,USIZE_MAX]


class BootstrapDiagnosticFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native diagnostic formatting requires NASM/GCC')
        cls.work=ROOT/'build/test/claude-c5'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/diagnostic_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/diagnostic_export.dg',roots=roots,mode=mode)
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
            records=cls.records,L3_selfhost_complete=False,OS_VM_built=False),indent=2)+'\n')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:
            payload.extend(struct.pack('<9Q',len(c['path']),len(c['code']),len(c['message']),c['line'],c['column'],
                                       c['cap'],c['readonly'],c['share'],c['nullout']))
            payload.extend(c['path']+c['code']+c['message'])
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,24)
        offset=8
        for index,c in enumerate(cases):
            status,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            out=run.stdout[offset:offset+c['cap']];offset+=c['cap']
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status'))
            if not status:
                self.assertEqual(written,len(c['text']),(label,index,'written'))
                self.assertEqual(out[:written],c['text'],(label,index,'output'))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def test_random_diagnostics_exact_short_and_empty_output(self):
        rng=random.Random(0xC5D1A6);cases=[]
        alphabet='abcxyz019_/.-中文路径诊断错误😀🚀✅é «» \t'
        for i in range(1100):
            path=(rng.choice(SAMPLES)if i%3==0 else ''.join(rng.choice(alphabet)for _ in range(rng.randint(1,40)))).encode()
            message=(rng.choice(MESSAGES)if i%2 else ''.join(rng.choice(alphabet)for _ in range(rng.randint(0,80)))).encode()
            line=rng.choice(NUMBERS)if i%4==0 else rng.randint(1,10**rng.randint(1,19))
            column=rng.choice(NUMBERS)if i%5==0 else rng.randint(1,2**rng.randint(1,64)-1)
            code=('E%04d'%rng.randrange(10000)).encode();text=expected(path,line,column,code,message)
            ro=int(i%100==0)
            cases+=[item(path,line,column,code,message,readonly=ro),item(path,line,column,code,message,cap=len(text)+7),
                    item(path,line,column,code,message,cap=len(text)-1),item(path,line,column,code,message,cap=0),
                    item(path,line,column,code,message,cap=0,nullout=1)]
        self.run_both(cases,'random')
        self.records.append(dict(test='random-exact-short-empty',diagnostics=1100,cases=len(cases),seed='0xC5D1A6',modes=2,passed=True))

    def test_numbers_codes_content_and_sharing(self):
        cases=[]
        for line in NUMBERS:
            for column in NUMBERS:cases.append(item(b'f.dg',line,column,b'E1234',b'm'))
        for code in (b'E0000',b'E9999',b'E0042'):cases.append(item(b'p',1,1,code,b''))
        for code in (b'e1234',b'E123',b'E12345',b'E12a4',b'X1234',b'E 123',b'E-123',b'',b'E',b'EEEEE',b'E12/4',b'E12:4',
                     'E１２３４'.encode()[:5],b'\x00E123'):
            cases.append(item(b'p',1,1,code,b'm',status=INVALID))
        for bad in (b'\x00',b'\n',b'\r',b'a\nb',b'tail\r',b'x\x00y'):
            cases.append(item(b'p'+bad,1,1,b'E0001',b'm',status=INVALID))
            cases.append(item(b'p',1,1,b'E0001',b'm'+bad,status=INVALID))
            cases.append(item(b'p',1,1,b'E0001',bad,status=INVALID))
        cases+=[item(b'',1,1,b'E0001',b'm',status=INVALID),item(b'p',0,1,b'E0001',b'm',status=INVALID),
                item(b'p',1,0,b'E0001',b'm',status=INVALID),item(b'p',0,0,b'E0001',b'm',status=INVALID),
                item(b'p',0,1,b'E0001',b'm',cap=0,status=INVALID),            # INVALID beats CAPACITY
                item(b'p\n',1,1,b'E0001',b'm',cap=1,status=INVALID),
                item(b'',1,1,b'E0001',b'',cap=0,nullout=1,status=INVALID)]
        # Shared read-only inputs: message is path, and path/code/message carved from one buffer.
        cases+=[item('同一/路径.dg'.encode(),7,8,b'E0007',b'',share=1),item(b'abc',1,2,b'E0001',b'',share=1,readonly=1),
                item(b'',3,4,b'E2468',b' tail msg',share=2),item(b'',3,4,b'E2468',b'',share=2,readonly=1),
                item(b'',3,4,b'E2468',b'x',share=2,cap=10)]
        cases+=[item('中文/😀.dg'.encode(),2**63,USIZE_MAX,b'E0001','错误：😀'.encode(),readonly=1),
                item(b'big.dg',1,1,b'E0001',b'y'*150000),item(b'z'*100000,USIZE_MAX,1,b'E0001',b'q',cap=100000)]
        self.run_both(cases,'bounds')
        self.records.append(dict(test='numbers-codes-content-sharing',cases=len(cases),invalid_preflights_per_native=24,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/diagnostic_format.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/diagnostic_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-digit-order','while i!=0{i-=1;out[at+i]=(48+v%10)as u8;v/=10;}','i=0;while i<n{out[at+i]=(48+v%10)as u8;v/=10;i+=1;}',
             [item(b'p',12,3,b'E0001',b'm')],'output'),
            ('bad-separator','out[at]=58;at=decimal(out,at+1,column);out[at]=58;out[at+1]=32;',
             'out[at]=58;at=decimal(out,at+1,column);out[at]=58;out[at+1]=9;',
             [item(b'p',1,1,b'E0001',b'm')],'output'),
            ('bad-early-written','if total>out.len{return CAPACITY;}','*written=total;if total>out.len{return CAPACITY;}',
             [item(b'path.dg',10,20,b'E0001',b'msg',cap=5)],'guard/atomicity'),
            ('bad-early-out','if total>out.len{return CAPACITY;}','if total>out.len{if out.len!=0{out[0]=path[0];}return CAPACITY;}',
             [item(b'path.dg',10,20,b'E0001',b'msg',cap=5)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
