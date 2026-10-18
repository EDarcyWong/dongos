"""Actual Dong NASM byte-literal encoding, against independent Python formatting."""
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

SOURCE=WORKS/'cursor-works/src/bootstrap/nasm_bytes.dg'
OK,INVALID,CAPACITY=0,1,2
USIZE_MAX=2**64-1
WRAPPER='''module probe.nasm_bytes_export;
import bootstrap.nasm_bytes as n;
export("dong_nasm_encode") pub unsafe fn encode(source:*const u8,ns:usize,out:*u8,no:usize,written:*usize)u64{unsafe{
 return n.encode(slice_from_raw_parts(source,ns),slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_nasm_encode(const uint8_t*,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
/* Descriptor / length preflights: INVALID and every arena byte unchanged.
   Fake pointers are only used on paths that must reject before any read. */
static unsigned invalid(void){
 static uint8_t arena[4096],saved[4096];const unsigned total=18;
 uint8_t*s=arena+64,*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(s,"\x00\x0A\xFF",3);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_nasm_encode(s,3,o,64,NULL);break;
   case 1:st=dong_nasm_encode(s,3,o,64,(uint64_t*)(arena+2052));break;
   case 2:st=dong_nasm_encode(s,3,o,64,(uint64_t*)(o+8));break;
   case 3:st=dong_nasm_encode(s,3,o,64,(uint64_t*)s);break;
   /* source lies only in unused out tail (need for 3 bytes is 18); full out span still aliases */
   case 4:st=dong_nasm_encode(o+40,3,o,64,w);break;
   /* written naturally aligned inside the declared out tail (was o+60, which masked the alias) */
   case 5:st=dong_nasm_encode(s,3,o,64,(uint64_t*)(o+56));break;
   case 6:st=dong_nasm_encode(NULL,3,o,64,w);break;
   case 7:st=dong_nasm_encode(s,3,NULL,64,w);break;
   case 8:st=dong_nasm_encode(FAKE(UINT64_MAX),2,o,64,w);break;
   case 9:st=dong_nasm_encode(s,3,(uint8_t*)(uintptr_t)(UINT64_MAX-7),64,w);break;
   case 10:st=dong_nasm_encode(s,3,o,64,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   /* need-length overflow: high fake bases pass span and stay clear of real out/written
      (low bases with huge lengths cover the stack arena and hit alias checks first). */
   case 11:st=dong_nasm_encode(FAKE((UINT64_C(1)<<63)|0x1000),UINT64_MAX/5+1,o,64,w);break;
   case 12:st=dong_nasm_encode(FAKE((UINT64_C(1)<<63)|0x2000),UINT64_MAX/5,o,64,w);break;
   case 13:st=dong_nasm_encode(FAKE(UINT64_MAX-8),16,o,64,w);break;
   case 14:st=dong_nasm_encode(s,3,(uint8_t*)(uintptr_t)(UINT64_MAX-3),8,w);break;
   case 15:st=dong_nasm_encode(NULL,3,NULL,0,w);break;
   case 16:st=dong_nasm_encode(s,3,o,0,(uint64_t*)(uintptr_t)1);break;
   default:st=dong_nasm_encode(FAKE((UINT64_C(1)<<63)|0x3000),UINT64_MAX/5+1,o,0,w);break;
  }
  if(st!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)st);exit(93);}
 }
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  /* ns cap readonly nullsrc nullout */
  uint64_t h[5];read_exact(h,sizeof(h));uint64_t ns=h[0],cap=h[1],ro=h[2],nullsrc=h[3],nullout=h[4];
  if(ns>300000||cap>400000)exit(94);
  uint8_t*in=malloc(ns+64),*copy=malloc(ns+1),*out=malloc(cap+64);uint64_t meta[3];
  if(!in||!copy||!out)exit(95);
  memset(in,0xa5,ns+64);if(ns)read_exact(in+32,ns);memcpy(copy,in+32,ns);
  uint8_t*base=in+32,*page=NULL;uint64_t pages=0;
  if(ro&&ns){pages=(ns/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,ns);ro_protect(page,pages);base=page;}
  const uint8_t*src=nullsrc?NULL:((!ns)?NULL:base);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nullout?NULL:((!cap)?NULL:out+32);
  if(!cap&&!nullout)o=out+32;
  uint64_t st=dong_nasm_encode(src,ns,o,cap,written);
  uint64_t valid=!memcmp(copy,base,ns)&&(ro||!ns||(filled(in,32)&&filled(in+32+ns,32)))&&filled(out,32)&&filled(out+32+cap,32)&&
    filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(out);
 }return 0;
}
'''


def need_len(n):
    if n==0:return 0
    return 5*n+3*((n+15)//16)


def expected(data):
    """Independent reference: group by 16 and format uppercase hex db lines."""
    if not data:return b''
    parts=[]
    for i in range(0,len(data),16):
        chunk=data[i:i+16]
        parts.append(b'db '+b','.join(b'0x%02X'%b for b in chunk)+b'\n')
    return b''.join(parts)


def item(data,cap=None,status=None,readonly=0,nullsrc=0,nullout=0):
    text=expected(data)
    need=need_len(len(data))
    if nullsrc and len(data):status=INVALID
    if nullout and cap:status=INVALID if status is None else status
    if status is None:
        if cap is None:cap=need
        status=OK if need<=cap else CAPACITY
    if cap is None:cap=need if status==OK else 16
    return dict(data=data,cap=cap,readonly=readonly,nullsrc=nullsrc,nullout=nullout,
                status=status,text=text if status==OK else None,need=need)


class NasmBytesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_bytes requires NASM/GCC')
        cls.work=WORKS/'cursor-works/build/test/cursor-cr1'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={str(p.relative_to(WORKS)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,Path(__file__),WORKS/'cursor-works/src/bootstrap/nasm_bytes.md']}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_bytes_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([WORKS/'cursor-works/src',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_bytes_export.dg',roots=roots,mode=mode)
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
        files={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for p in cls.work.rglob('*')if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,artifact_sha256=files,
            records=cls.records,L3_selfhost_complete=False,OS_VM_built=False),indent=2)+'\n',encoding='utf-8')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:
            payload.extend(struct.pack('<5Q',len(c['data']),c['cap'],c['readonly'],c['nullsrc'],c['nullout']))
            payload.extend(c['data'])
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=180)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,18)
        offset=8
        outs=[]
        for index,c in enumerate(cases):
            status,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            out=run.stdout[offset:offset+c['cap']];offset+=c['cap']
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status',c['data'][:32]))
            if not status:
                self.assertEqual(written,len(c['text']),(label,index,'written'))
                self.assertEqual(out[:written],c['text'],(label,index,'output'))
            outs.append(out[:written] if not status else None)
        self.assertEqual(offset,len(run.stdout))
        return outs

    def run_both(self,cases,label):
        results={}
        for mode,exe in self.executables.items():results[mode]=self.run_cases(exe,cases,label+'-'+mode)
        return results

    def test_seeded_binary_exact_short_and_extra_capacity(self):
        rng=random.Random(0x0C81B17E)
        cases=[]
        specials=[
            b'',b'\x00',b'\xff',b'\x00\x0a\xff',bytes(range(256)),
            b'"\'\\\n\r\t',b'\xc0\x80',b'\xed\xa0\x80',b'\xff\xfe',
            bytes(16),bytes(17),bytes(15),bytes(31),bytes(32),bytes(33),
            b'\x00'*16,b'\xff'*16,b'\x00'*17,b'\xff'*33,
            bytes([i%256 for i in range(2048)]),
        ]
        for data in specials:
            need=need_len(len(data))
            cases+=[item(data),item(data,cap=need+11),item(data,cap=max(0,need-1)),
                    item(data,cap=0),item(data,cap=0,nullout=1)]
        for i in range(1000):
            n=rng.randint(0,2048)
            data=bytes(rng.randrange(256)for _ in range(n))
            if i%50==0:data=bytes(range(256))+(data[:max(0,n-256)])
            if i%77==0:data=bytes([0,10,13,34,39,92,7,255][:n])+data[8:n]
            need=need_len(len(data));ro=int(i%80==0 and n>0)
            cases+=[item(data,readonly=ro),item(data,cap=need+5),item(data,cap=max(0,need-1))]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='seeded-exact-short-extra',fixed_specials=len(specials),
                                 random_inputs=1000,cases=len(cases),seed='0x0C81B17E',modes=2,passed=True))

    def test_line_boundaries_empty_and_priority(self):
        cases=[]
        for n in (0,1,15,16,17,31,32,33):
            data=bytes([(i*17+3)&0xff for i in range(n)])
            need=need_len(n)
            cases+=[item(data),item(data,cap=need+1),item(data,cap=max(0,need-1))]
        cases+=[
            item(b'',cap=0),item(b'',cap=8),item(b'',cap=0,nullout=1),
            item(b'\x00\x0a\xff'),item(bytes(range(256)),readonly=1),
            item(b'abc',nullsrc=1,cap=0,status=INVALID),  # INVALID beats CAPACITY
            item(b'abc',cap=1,nullsrc=1,status=INVALID),
            item(b'xy',cap=0,nullout=0),  # CAPACITY empty-ish out with len 0
        ]
        # Verify Python formula on a few sizes including multi-line.
        for n in (0,1,16,17,32,100):
            self.assertEqual(len(expected(b'A'*n)),need_len(n),n)
        self.run_both(cases,'bounds')
        self.records.append(dict(test='line-boundaries-empty-priority',cases=len(cases),
                                 invalid_preflights_per_native=18,modes=2,passed=True))

    def test_dong_output_nasm_bin_roundtrip(self):
        rng=random.Random(0x0C81B17F)
        samples=[b'',b'\x00\x0a\xff',bytes(range(256)),bytes(16),bytes(17),bytes(33),
                 b'"\\\'\n',b'\xff'*64,bytes([i%256 for i in range(100)]),
                 bytes([0]*15)+b'\xff',bytes(range(32))]
        while len(samples)<120:
            n=rng.choice([0,1,15,16,17,31,32,33,64,100,200,512])
            samples.append(bytes(rng.randrange(256)for _ in range(n)))
        cases=[item(s)for s in samples]
        results=self.run_both(cases,'roundtrip')
        round_dir=self.work/'nasm-bin';round_dir.mkdir(exist_ok=True)
        checked=0;nasm_calls=0;empty_nasm_calls=0
        for mode,outs in results.items():
            for index,(data,out) in enumerate(zip(samples,outs)):
                # Round-trip must use actual Dong output, never the Python expectation.
                # Empty Dong output still writes an empty .asm and invokes real NASM -f bin.
                self.assertIsNotNone(out,(mode,index))
                asm_path=round_dir/f'{mode}-{index:03d}.asm'
                bin_path=round_dir/f'{mode}-{index:03d}.bin'
                asm_path.write_bytes(out)
                r=subprocess.run([str(self.nasm),'-f','bin','-o',str(bin_path),str(asm_path)],
                                 capture_output=True,timeout=30)
                self.assertEqual(r.returncode,0,(mode,index,r.stderr))
                nasm_calls+=1
                if out==b'':empty_nasm_calls+=1
                recovered=bin_path.read_bytes()
                self.assertEqual(recovered,data,(mode,index,'nasm-bin-roundtrip'))
                checked+=1
        self.assertEqual(nasm_calls,checked)
        self.assertGreater(empty_nasm_calls,0)
        self.records.append(dict(test='dong-nasm-bin-roundtrip',inputs=len(samples),
                                 checks=checked,nasm_bin_calls=nasm_calls,
                                 empty_nasm_bin_calls=empty_nasm_calls,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_bytes.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/nasm_bytes_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-hex-case',
             'return (55+v)as u8;',
             'return (87+v)as u8;',
             [item(bytes([0xab,0xcd,0xef]))],'output'),
            ('bad-line-split',
             'const WIDTH:usize=16;',
             'const WIDTH:usize=15;',
             [item(bytes(range(16)),cap=200)],'written|output'),
            ('bad-early-written',
             'if total>out.len{return CAPACITY;}',
             '*written=total;if total>out.len{return CAPACITY;}',
             [item(b'\x00\x0a\xff',cap=5)],'guard/atomicity'),
            ('bad-early-out',
             'if total>out.len{return CAPACITY;}',
             'if total>out.len{if out.len!=0{out[0]=100;}return CAPACITY;}',
             [item(b'\x00\x0a\xff',cap=5)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
