"""Actual Dong NASM-internal symbol encoding, with real NASM assemble checks."""
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
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

SOURCE=WORKS/'cursor-works/src/bootstrap/nasm_symbol.dg'
DOC=WORKS/'cursor-works/src/bootstrap/nasm_symbol.md'
OK,INVALID,CAPACITY=0,1,2
WRAPPER='''module probe.nasm_symbol_export;
import bootstrap.nasm_symbol as n;
export("dong_nasm_symbol_encode") pub unsafe fn encode(
 m:*const u8,nm:usize,it:*const u8,ni:usize,out:*u8,no:usize,written:*usize)u64{unsafe{
 return n.encode(slice_from_raw_parts(m,nm),slice_from_raw_parts(it,ni),
  slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_nasm_symbol_encode(const uint8_t*,uint64_t,const uint8_t*,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
static unsigned invalid(void){
 static uint8_t arena[4096],saved[4096];const unsigned total=16;
 uint8_t*m=arena+64,*it=arena+128,*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(m,"ab",2);memcpy(it,"cd",2);
  if(i==5)memcpy(o+40,"xx",2);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_nasm_symbol_encode(m,2,it,2,o,64,NULL);break;
   case 1:st=dong_nasm_symbol_encode(m,2,it,2,o,64,(uint64_t*)(arena+2052));break;
   case 2:st=dong_nasm_symbol_encode(m,2,it,2,o,64,(uint64_t*)(o+8));break;
   case 3:st=dong_nasm_symbol_encode(m,2,it,2,o,64,(uint64_t*)m);break;
   case 4:st=dong_nasm_symbol_encode(m,2,it,2,o,64,(uint64_t*)it);break;
   case 5:st=dong_nasm_symbol_encode(o+40,2,it,2,o,64,w);break;
   case 6:st=dong_nasm_symbol_encode(m,2,it,2,o,64,(uint64_t*)(o+56));break;
   case 7:st=dong_nasm_symbol_encode(NULL,2,it,2,o,64,w);break;
   case 8:st=dong_nasm_symbol_encode(m,2,NULL,2,o,64,w);break;
   case 9:st=dong_nasm_symbol_encode(m,2,it,2,NULL,64,w);break;
   case 10:st=dong_nasm_symbol_encode(m,0,it,2,o,64,w);break;
   case 11:st=dong_nasm_symbol_encode(m,2,it,0,o,64,w);break;
   case 12:st=dong_nasm_symbol_encode(FAKE((UINT64_C(1)<<63)|0x1000),UINT64_MAX/2,it,1,o,64,w);break;
   case 13:st=dong_nasm_symbol_encode(m,2,FAKE((UINT64_C(1)<<63)|0x2000),UINT64_MAX/2,o,64,w);break;
   case 14:st=dong_nasm_symbol_encode(m,2,it,2,o,0,(uint64_t*)(uintptr_t)1);break;
   default:st=dong_nasm_symbol_encode(FAKE(UINT64_MAX),2,it,2,o,64,w);break;
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
  uint64_t h[7];read_exact(h,sizeof(h));
  uint64_t nm=h[0],ni=h[1],cap=h[2],rom=h[3],roi=h[4],nmull=h[5],niull=h[6];
  if(nm>4000||ni>4000||cap>20000)exit(94);
  uint8_t*m=malloc(nm+64),*mc=malloc(nm+1),*it=malloc(ni+64),*ic=malloc(ni+1),*out=malloc(cap+64);
  uint64_t meta[3];
  if(!m||!mc||!it||!ic||!out)exit(95);
  memset(m,0xa5,nm+64);memset(it,0xa5,ni+64);
  if(nm)read_exact(m+32,nm);
  if(ni)read_exact(it+32,ni);
  memcpy(mc,m+32,nm);memcpy(ic,it+32,ni);
  uint8_t*mb=m+32,*ib=it+32,*mp=NULL,*ip=NULL;uint64_t mpages=0,ipages=0;
  if(rom&&nm){mpages=(nm/4096+2)*4096;mp=ro_alloc(mpages);if(!mp)exit(95);memcpy(mp,mc,nm);ro_protect(mp,mpages);mb=mp;}
  if(roi&&ni){ipages=(ni/4096+2)*4096;ip=ro_alloc(ipages);if(!ip)exit(95);memcpy(ip,ic,ni);ro_protect(ip,ipages);ib=ip;}
  const uint8_t*mptr=nmull?NULL:((!nm)?NULL:mb);
  const uint8_t*iptr=niull?NULL:((!ni)?NULL:ib);
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=out+32;
  uint64_t st=dong_nasm_symbol_encode(mptr,nm,iptr,ni,o,cap,written);
  uint64_t valid=!memcmp(mc,mb,nm)&&!memcmp(ic,ib,ni)&&
    (rom||!nm||(filled(m,32)&&filled(m+32+nm,32)))&&
    (roi||!ni||(filled(it,32)&&filled(it+32+ni,32)))&&
    filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  if(mp)ro_free(mp,mpages);
  if(ip)ro_free(ip,ipages);
  free(m);free(mc);free(it);free(ic);free(out);
 }return 0;
}
'''


def need_len(nm,ni):
    return 10+2*(nm+ni)


def expected(mod,item):
    return b'__dong_m'+mod.hex().encode()+b'_n'+item.hex().encode()


def item(mod,it,cap=None,status=None,rom=0,roi=0,nmull=0,niull=0):
    text=expected(mod,it);need=need_len(len(mod),len(it))
    if nmull and len(mod):status=INVALID
    if niull and len(it):status=INVALID
    if status is None:
        if len(mod)==0 or len(it)==0:status=INVALID
        else:
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:cap=need if status==OK else 32
    return dict(mod=mod,item=it,cap=cap,rom=rom,roi=roi,nmull=nmull,niull=niull,
                status=status,text=text if status==OK else None,need=need)


class NasmSymbolTests(unittest.TestCase):
    PREFLIGHTS=16

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_symbol requires NASM/GCC')
        cls.work=WORKS/'cursor-works/build/CR3'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_symbol.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,DOC,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_symbol_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_symbol_export.dg',roots=roots,mode=mode)
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
            payload.extend(struct.pack('<7Q',len(c['mod']),len(c['item']),c['cap'],c['rom'],c['roi'],c['nmull'],c['niull']))
            payload.extend(c['mod']);payload.extend(c['item'])
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=180)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,self.PREFLIGHTS)
        offset=8;outs=[]
        for index,c in enumerate(cases):
            status,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            out=run.stdout[offset:offset+c['cap']];offset+=c['cap']
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status',c['mod'][:16],c['item'][:16]))
            if not status:
                self.assertEqual(written,len(c['text']),(label,index,'written'))
                self.assertEqual(out[:written],c['text'],(label,index,'output'))
            outs.append(out[:written] if not status else None)
        self.assertEqual(offset,len(run.stdout))
        return outs

    def run_both(self,cases,label):
        return {mode:self.run_cases(exe,cases,label+'-'+mode)for mode,exe in self.executables.items()}

    def test_seeded_boundaries_and_ambiguity(self):
        rng=random.Random(0x0C83001)
        pairs=[
            (b'a',b'b'),(b'mov',b'rax'),(b'_',b'__'),(b'\x00',b'\xff'),
            (b'\xe4\xb8\xad',b'x'),(b'a',b'bc'),(b'ab',b'c'),
            (b'hello',b'world'),(b'!',b'?'),(b'\xc0\x80',b'\xed\xa0\x80'),
        ]
        cases=[]
        for m,i in pairs:
            need=need_len(len(m),len(i))
            cases+=[item(m,i),item(m,i,cap=need+5),item(m,i,cap=max(0,need-1)),item(m,i,cap=0)]
        # ambiguity: encodings must differ
        self.assertNotEqual(expected(b'a',b'bc'),expected(b'ab',b'c'))
        cases+=[item(b'',b'x',status=INVALID),item(b'x',b'',status=INVALID),
                item(b'a',b'b',nmull=1,cap=0,status=INVALID)]
        for i in range(120):
            nm=rng.randint(1,24);ni=rng.randint(1,24)
            m=bytes(rng.randrange(256)for _ in range(nm))
            it=bytes(rng.randrange(256)for _ in range(ni))
            need=need_len(nm,ni)
            cases+=[item(m,it,rom=int(i%17==0),roi=int(i%19==0)),
                    item(m,it,cap=need+2),item(m,it,cap=max(0,need-1))]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='seeded-boundaries-ambiguity',cases=len(cases),
                                 random=120,modes=2,preflights=self.PREFLIGHTS,passed=True))

    def test_dong_symbols_assemble_elf64_and_coff(self):
        """Actual Dong symbols used as NASM labels with define+reference; both object formats."""
        samples=[(b'a',b'b'),(b'mov',b'rax'),(b'\x00\xff',b'_'),(b'mod',b'item'),
                 (b'\xe4\xb8\xad',b'fn'),(b'x',b'y'*8)]
        cases=[item(m,i)for m,i in samples]
        results=self.run_both(cases,'assemble')
        asm_dir=self.work/'nasm-sym';asm_dir.mkdir(exist_ok=True)
        assembled=0
        for mode,outs in results.items():
            for index,((m,i),sym) in enumerate(zip(samples,outs)):
                self.assertIsNotNone(sym)
                self.assertTrue(sym.startswith(b'__dong_m') and b'_n' in sym)
                name=sym.decode('ascii')
                text=f'bits 64\ndefault rel\nsection .text\nglobal {name}\n{name}:\n xor eax,eax\n ret\n'
                # also a local reference so the symbol is used
                text+=f'global use_{index}\nuse_{index}:\n jmp {name}\n'
                path=asm_dir/f'{mode}-{index}.asm';path.write_text(text,encoding='utf-8')
                for fmt in ('elf64','win64'):
                    obj=asm_dir/f'{mode}-{index}-{fmt}.o'
                    r=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(path)],
                                     capture_output=True,timeout=30)
                    self.assertEqual(r.returncode,0,(mode,index,fmt,r.stderr,name))
                    assembled+=1
        self.records.append(dict(test='dong-symbols-assemble',samples=len(samples),
                                 assembled=assembled,modes=2,formats=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_symbol.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'wrapper'/'probe'/'nasm_symbol_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',ROOT/'lang',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-separator',
             'out[at]=95;out[at+1]=110;at+=2;i=0;',
             'out[at]=95;out[at+1]=109;at+=2;i=0;',  # "_m" instead of "_n"
             [item(b'a',b'b')],'output'),
            ('bad-hex-case',
             'return (87+v)as u8;',
             'return (55+v)as u8;',  # uppercase A-F
             [item(bytes([0xab]),bytes([0xcd]))],'output'),
            ('bad-early-written',
             'if total>out.len{return CAPACITY;}',
             '*written=total;if total>out.len{return CAPACITY;}',
             [item(b'a',b'b',cap=5)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
