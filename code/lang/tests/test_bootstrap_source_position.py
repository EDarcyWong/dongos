"""Actual Dong UTF-8 source position locator, against Python's strict UTF-8 decoder and bytes slicing."""
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
SOURCE=ROOT/'lang/bootstrap/source_position.dg'
UTF8_MODULE=ROOT/'lang/std/core/utf8.dg'
OK,INVALID,UTF8,BOUNDARY=0,1,2,3
WRAPPER='''module probe.position_export;
import bootstrap.source_position as s;
export("dong_source_locate") pub unsafe fn locate(source:*const u8,length:usize,offset:usize,out:*s.Position)u64{unsafe{
 return s.locate(slice_from_raw_parts(source,length),offset,out);
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
typedef struct {uint64_t line,column,line_start,line_end;} Position;
_Static_assert(sizeof(Position)==32&&__builtin_offsetof(Position,column)==8&&__builtin_offsetof(Position,line_start)==16
 &&__builtin_offsetof(Position,line_end)==24,"Position layout");
extern uint64_t ABI dong_source_locate(const uint8_t*,uint64_t,uint64_t,Position*);
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
/* Bad descriptors / offsets: INVALID with every arena byte unchanged; fake pointers never read. */
static unsigned invalid(void){
 static uint8_t arena[1024],saved[1024];const unsigned total=12;
 uint8_t*s=arena;Position*o=(Position*)(arena+512);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(s,"ab\n\xe4\xb8\xad",6);memcpy(saved,arena,sizeof(arena));uint64_t r=0;
  switch(i){
   case 0:r=dong_source_locate(s,6,0,NULL);break;
   case 1:r=dong_source_locate(s,6,0,(Position*)(arena+516));break;
   case 2:r=dong_source_locate(s,6,0,(Position*)s);break;
   case 3:r=dong_source_locate(s,64,0,(Position*)(arena+40));break;        /* out overlaps source tail */
   case 4:r=dong_source_locate(NULL,6,0,o);break;
   case 5:r=dong_source_locate(FAKE(UINT64_MAX-3),8,0,o);break;
   case 6:r=dong_source_locate(s,6,0,(Position*)(uintptr_t)(UINT64_MAX-15));break;
   case 7:r=dong_source_locate(s,6,7,o);break;
   case 8:r=dong_source_locate(s,6,UINT64_MAX,o);break;
   case 9:r=dong_source_locate(FAKE(4096),100,101,o);break;              /* offset checked before reading */
   case 10:r=dong_source_locate(NULL,0,1,o);break;
   default:r=dong_source_locate(FAKE(4096),UINT64_MAX-4096,0,(Position*)(uintptr_t)8192);break; /* aliasing fake out */
  }
  if(r!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)r);exit(93);}
 }
 /* NULL empty source is accepted: 1/1/0/0. */
 memset(arena,0xa5,sizeof(arena));
 if(dong_source_locate(NULL,0,0,o)||o->line!=1||o->column!=1||o->line_start||o->line_end){fprintf(stderr,"null empty\n");exit(96);}
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[3];read_exact(h,sizeof(h));uint64_t n=h[0],offset=h[1],ro=h[2];
  if(n>4000000)exit(94);
  uint8_t*in=malloc(n+64),*copy=malloc(n+1);uint64_t meta[8];if(!in||!copy)exit(95);
  memset(in,0xa5,n+64);read_exact(in+32,n);memcpy(copy,in+32,n);
  const uint8_t*src=n?in+32:NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro&&n){pages=(n/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,n);ro_protect(page,pages);src=page;}
  memset(meta,0xa5,sizeof(meta));Position*out=(Position*)(meta+2);
  uint64_t r=dong_source_locate(src,n,offset,out);
  uint64_t valid=(!n||!memcmp(copy,src,n))&&(ro||(filled(in,32)&&filled(in+32+n,32)))&&filled(meta,16)&&filled(meta+6,16);
  if(r)valid=valid&&filled(out,32);
  uint64_t response[6]={r,valid,r?0:out->line,r?0:out->column,r?0:out->line_start,r?0:out->line_end};
  write_exact(response,sizeof(response));
  if(page)ro_free(page,pages);
  free(in);free(copy);
 }return 0;
}
'''


def reference(src,offset):
    """Independent reference: Python strict UTF-8 decoding plus bytes slicing."""
    if offset>len(src):return INVALID,None
    try:text=src.decode('utf-8',errors='strict')
    except UnicodeDecodeError:return UTF8,None
    starts=set();at=0
    for ch in text:starts.add(at);at+=len(ch.encode('utf-8'))
    starts.add(len(src))
    if offset not in starts:return BOUNDARY,None
    prefix=src[:offset].decode('utf-8');last=prefix.rfind('\n')
    line=prefix.count('\n')+1;column=len(prefix[last+1:])+1
    line_start=len(prefix[:last+1].encode('utf-8'));end=src.find(b'\n',offset)
    return OK,(line,column,line_start,len(src)if end<0 else end)


def case(src,offset,readonly=0):
    status,position=reference(src,offset)
    return dict(src=src,offset=offset,readonly=readonly,status=status,position=position)


PIECES=['a','Z','0',' ','中','文','é','é','́','😀','🚀','﻿','\t','\r','\r\n','\n','\0',' ',' ','\U0010ffff','߿','ࠀ']
BAD=[b'\xc0\x80',b'\xc1\xbf',b'\xe0\x80\x80',b'\xe0\x9f\xbf',b'\xf0\x80\x80\x80',b'\xf0\x8f\xbf\xbf',b'\xed\xa0\x80',b'\xed\xbf\xbf',
     b'\xf4\x90\x80\x80',b'\xf5\x80\x80\x80',b'\xff',b'\xfe',b'\x80',b'\xbf',b'\xe4\xb8',b'\xf0\x9f\x98',b'\xc3',b'\xe4',
     b'\xc3\x28',b'\xe4\x28\xad',b'\xf0\x9f\x28\x80']


def unicode_source(rng,limit=64):
    out=b''
    while True:
        piece=rng.choice(PIECES).encode('utf-8')
        if len(out)+len(piece)>limit or rng.random()<0.04:return out
        out+=piece


class BootstrapSourcePositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native source position requires NASM/GCC')
        cls.work=ROOT/'build/test/claude-c6'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,UTF8_MODULE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/position_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([ROOT/'lang',ROOT/'lang/std',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/position_export.dg',roots=roots,mode=mode)
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
        for c in cases:payload.extend(struct.pack('<3Q',len(c['src']),c['offset'],c['readonly']));payload.extend(c['src'])
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=300)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,12)
        offset=8
        for index,c in enumerate(cases):
            status,guard,*position=struct.unpack_from('<6Q',run.stdout,offset);offset+=48
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status',c['src'][:40],c['offset']))
            if not status:self.assertEqual(tuple(position),c['position'],(label,index,'position',c['src'][:40],c['offset']))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def test_every_offset_of_random_unicode_sources(self):
        rng=random.Random(0xC6505);cases=[];sources=0;statuses={}
        fixed=[b'',b'\n',b'\n\n',b'a',b'a\n',b'\r\n',b'a\r\nb',b'\t\tx',b'\0\0\n\0','﻿abc'.encode(),'中文\n😀'.encode(),
               'é\n'.encode(),b'x\n\n\ny']
        for i in range(1100):
            src=fixed[i]if i<len(fixed)else unicode_source(rng)
            sources+=1
            for offset in range(len(src)+2):
                c=case(src,offset,readonly=int(i%100==0));cases.append(c);statuses[c['status']]=statuses.get(c['status'],0)+1
        self.run_both(cases,'unicode')
        self.assertGreater(statuses.get(BOUNDARY,0),1000,statuses)
        self.records.append(dict(test='every-offset-unicode',sources=sources,cases=len(cases),seed='0xC6505',statuses=statuses,modes=2,passed=True))

    def test_invalid_utf8_before_after_target_and_long_lines(self):
        rng=random.Random(0xC6BAD);cases=[]
        for bad in BAD:
            for _ in range(6):
                head,tail=unicode_source(rng,24),unicode_source(rng,24);src=head+bad+tail
                self.assertEqual(reference(src,0)[0],UTF8,src)
                for offset in sorted({0,len(head),len(head)+1,len(head)+len(bad),len(src),len(src)+1}):
                    cases.append(case(src,min(offset,len(src)+1)))
            cases+=[case(bad,0),case(b'ok\n'+bad,3),case(bad+b'ok',len(bad)+2)]
        # Strict boundaries of the accepted range.
        for good in ['\u007f','\u0080','߿','ࠀ','퟿','','￿','\U00010000','\U0010ffff']:
            src=good.encode('utf-8');cases+=[case(src,o)for o in range(len(src)+1)]
        # Long lines / many lines, offsets spread over the whole source.
        long_line=('数据😀a\t'*20000).encode()+b'\n'+b'tail'
        many=b''.join(('line %d 中\r\n'%i).encode()for i in range(5000))
        for src in (long_line,many,b'\n'*30000,('é'*50000).encode()):
            for offset in sorted({0,1,2,len(src)//3,len(src)//2,len(src)-1,len(src),len(src)+1}|{rng.randrange(len(src)+1)for _ in range(12)}):
                cases.append(case(src,offset,readonly=int(offset==0)))
        self.run_both(cases,'bounds')
        self.records.append(dict(test='invalid-utf8-long-lines',cases=len(cases),bad_sequences=len(BAD),invalid_preflights_per_native=12,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir();(root/'core').mkdir()
        shutil.copyfile(UTF8_MODULE,root/'core/utf8.dg')
        (root/'bootstrap/source_position.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/position_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-byte-columns','}else{column+=1;}','}else{column+=d.width;}',[case('中a'.encode(),4)],'position'),
            ('bad-line-end','var end=byte_offset;while end<source.len&&source[end]!=10{end+=1;}',
             'var end=byte_offset;while end<source.len&&source[end]!=10{end+=1;}if end<source.len{end+=1;}',[case(b'ab\ncd',1)],'position'),
            ('bad-early-out','if !utf8.validate(source){return UTF8;}',
             '*out=Position{line:0,column:0,line_start:0,line_end:0};if !utf8.validate(source){return UTF8;}',
             [case(b'ok\xff',0)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
