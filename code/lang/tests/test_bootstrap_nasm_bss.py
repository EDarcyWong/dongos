"""Actual Dong NASM BSS emit, reusing integrated CR4 decimal_integer."""
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

ROOT=Path(__file__).resolve().parents[2]
WORKS=ROOT

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

SOURCE=ROOT/'lang/bootstrap/nasm_bss.dg'
DOC=ROOT/'lang/bootstrap/nasm_bss.md'
OK,INVALID,CAPACITY=0,1,2
PREFIX=b'__dong_'
WRAPPER='''module probe.nasm_bss_export;
import bootstrap.nasm_bss as b;
export("dong_nasm_bss_emit") pub unsafe fn emit(
 label:*const u8,nl:usize,byte_count:usize,alignment:usize,out:*u8,no:usize,written:*usize)u64{unsafe{
 return b.emit(slice_from_raw_parts(label,nl),byte_count,alignment,slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_nasm_bss_emit(const uint8_t*,uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
 uint8_t*lab=arena+64,*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);
 const char*oklab="__dong_x";
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(lab,oklab,8);
  /* case5: legal label in unused out tail before snapshot (alias coverage). */
  if(i==5)memcpy(o+80,oklab,8);
  memcpy(saved,arena,sizeof(arena));uint64_t st=0;
  switch(i){
   case 0:st=dong_nasm_bss_emit(lab,8,16,8,o,128,NULL);break;
   case 1:st=dong_nasm_bss_emit(lab,8,16,8,o,128,(uint64_t*)(arena+2052));break;
   case 2:st=dong_nasm_bss_emit(lab,8,16,8,o,128,(uint64_t*)(o+8));break;
   case 3:st=dong_nasm_bss_emit(lab,8,16,8,o,128,(uint64_t*)lab);break;
   case 4:st=dong_nasm_bss_emit(lab,8,16,8,o,128,(uint64_t*)(o+56));break;
   case 5:st=dong_nasm_bss_emit(o+80,8,16,8,o,128,w);break;
   case 6:st=dong_nasm_bss_emit(NULL,8,16,8,o,128,w);break;
   case 7:st=dong_nasm_bss_emit(lab,8,16,8,NULL,128,w);break;
   case 8:st=dong_nasm_bss_emit(lab,7,16,8,o,128,w);break;
   case 9:st=dong_nasm_bss_emit((const uint8_t*)"__dong_!",8,16,8,o,128,w);break;
   case 10:st=dong_nasm_bss_emit(lab,8,16,3,o,128,w);break; /* not power of two */
   case 11:st=dong_nasm_bss_emit(lab,8,16,8192,o,128,w);break;
   case 12:st=dong_nasm_bss_emit(lab,8,16,0,o,128,w);break;
   case 13:st=dong_nasm_bss_emit(FAKE(UINT64_MAX),8,16,8,o,128,w);break;
   case 14:st=dong_nasm_bss_emit(lab,8,16,8,o,0,(uint64_t*)(uintptr_t)1);break;
   default:st=dong_nasm_bss_emit(lab,8,16,8,(uint8_t*)(uintptr_t)(UINT64_MAX-7),128,w);break;
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
  uint64_t h[6];read_exact(h,sizeof(h));
  uint64_t nl=h[0],byte_count=h[1],alignment=h[2],cap=h[3],rol=h[4],nout=h[5];
  if(nl>300||cap>400000)exit(94);
  uint8_t*lab=malloc(nl+64),*labc=malloc(nl+1),*out=malloc(cap+64);uint64_t meta[3];
  if(!lab||!labc||!out)exit(95);
  memset(lab,0xa5,nl+64);if(nl)read_exact(lab+32,nl);memcpy(labc,lab+32,nl);
  uint8_t*lbase=lab+32,*lpage=NULL;uint64_t lpages=0;
  if(rol&&nl){lpages=(nl/4096+2)*4096;lpage=ro_alloc(lpages);if(!lpage)exit(95);memcpy(lpage,labc,nl);ro_protect(lpage,lpages);lbase=lpage;}
  const uint8_t*lp=(!nl)?NULL:lbase;
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint8_t*o=nout?NULL:out+32;
  uint64_t st=dong_nasm_bss_emit(lp,nl,byte_count,alignment,o,cap,written);
  uint64_t valid=!memcmp(labc,lbase,nl)&&(rol||!nl||(filled(lab,32)&&filled(lab+32+nl,32)))&&
    filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={st,valid,st?0:*written};write_exact(response,24);write_exact(out+32,cap);
  if(lpage)ro_free(lpage,lpages);
  free(lab);free(labc);free(out);
 }return 0;
}
'''


def label_ok(label:bytes)->bool:
    if not (8<=len(label)<=128):return False
    if not label.startswith(PREFIX):return False
    if len(label)==len(PREFIX):return False
    for c in label[len(PREFIX):]:
        if not (65<=c<=90 or 97<=c<=122 or 48<=c<=57 or c==95):return False
    return True


def align_ok(a:int)->bool:
    return a!=0 and a<=4096 and (a&(a-1))==0


def expected(label:bytes,byte_count:int,alignment:int)->bytes:
    return b'align '+str(alignment).encode()+b', resb 1\n'+label+b': resb '+str(byte_count).encode()+b'\n'


def need_total(label:bytes,byte_count:int,alignment:int)->int:
    return len(expected(label,byte_count,alignment))


def item(label,byte_count,alignment,cap=None,status=None,rol=0,nout=0):
    text=expected(label,byte_count,alignment)
    need=len(text)
    if nout and cap and status is None:status=INVALID
    if status is None:
        if not label_ok(label) or not align_ok(alignment):status=INVALID
        else:
            if cap is None:cap=need
            status=OK if need<=cap else CAPACITY
    if cap is None:cap=need if status==OK else 32
    return dict(label=label,byte_count=byte_count,alignment=alignment,cap=cap,rol=rol,nout=nout,
                status=status,text=text if status==OK else None,need=need)


def elf64_sym_value_and_bss_size(path:Path,name:bytes):
    data=path.read_bytes()
    if data[:4]!=b'\x7fELF':raise AssertionError('not elf')
    e_shoff,=struct.unpack_from('<Q',data,40)
    e_shentsize,e_shnum,e_shstrndx=struct.unpack_from('<HHH',data,58)
    def shdr(i):
        off=e_shoff+i*e_shentsize
        return struct.unpack_from('<IIQQQQIIQQ',data,off)
    # name,type,flags,addr,offset,size,link,info,addralign,entsize
    shstr=shdr(e_shstrndx)
    shstrtab=data[shstr[4]:shstr[4]+shstr[5]]
    sections={}
    for i in range(e_shnum):
        h=shdr(i)
        n=shstrtab[h[0]:].split(b'\x00',1)[0]
        sections[n]=h
    bss=sections.get(b'.bss')
    if not bss:raise AssertionError('no .bss')
    # find symtab
    for n,h in sections.items():
        if h[1]!=2:continue  # SHT_SYMTAB
        link=h[6];strtab=sections[list(sections.keys())[link]] if False else None
        # link is section index
        str_h=shdr(link)
        strings=data[str_h[4]:str_h[4]+str_h[5]]
        entsize=h[9] or 24
        for off in range(h[4],h[4]+h[5],entsize):
            st_name,st_info,st_other,st_shndx,st_value,st_size=struct.unpack_from('<IBBHQQ',data,off)
            sname=strings[st_name:].split(b'\x00',1)[0]
            if sname==name:
                return st_value,bss[5]
    raise AssertionError(('symbol missing',name))


def coff_sym_value_and_bss_size(path:Path,name:bytes):
    data=path.read_bytes()
    _machine,numsec,_ts,symtab,nsyms,opthdr,_chars=struct.unpack_from('<HHIIIHH',data,0)
    sec_off=20+opthdr
    bss_idx=None;bss_size=None
    for i in range(numsec):
        off=sec_off+i*40
        sname=data[off:off+8].split(b'\x00',1)[0]
        vsize,_vaddr,rawsize,_rp,_rel,_ln,_nr,_nl,_flags=struct.unpack_from('<IIIIIIHHI',data,off+8)
        if sname.startswith(b'.bss'):
            # COFF objects often leave VirtualSize=0; SizeOfRawData holds BSS length.
            bss_idx=i+1;bss_size=vsize or rawsize;break
    if bss_idx is None:raise AssertionError('no coff bss')
    str_off=symtab+nsyms*18
    strings=data[str_off:] if str_off<len(data) else b''
    i=0
    while i<nsyms:
        off=symtab+i*18
        raw=data[off:off+8]
        if raw[:4]==b'\x00\x00\x00\x00':
            idx,=struct.unpack_from('<I',raw,4)
            sname=strings[idx:].split(b'\x00',1)[0]
        else:
            sname=raw.split(b'\x00',1)[0]
        value,secnum,_stype,_sclass,aux=struct.unpack_from('<IHHBB',data,off+8)
        if sname==name and secnum==bss_idx:
            return value,bss_size
        i+=1+aux
    raise AssertionError(('coff symbol missing',name))



def dependency_root(work):
    target=work/'dependencies/bootstrap';target.mkdir(parents=True,exist_ok=True)
    for name in ('decimal_integer',):
        (target/(name+'.dg')).write_bytes((ROOT/'lang/bootstrap'/(name+'.dg')).read_bytes())
    return target.parent

class NasmBssTests(unittest.TestCase):
    PREFLIGHTS=16

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native nasm_bss requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/CR5'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'nasm_bss.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return str(p.resolve().relative_to(WORKS)).replace('\\','/')
            except ValueError:
                try:return str(p.resolve().relative_to(ROOT)).replace('\\','/')
                except ValueError:return str(p.resolve()).replace('\\','/')
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [SOURCE,DOC,Path(__file__),ROOT/'lang/bootstrap/decimal_integer.dg']}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/nasm_bss_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,dependency_root(cls.work),wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/nasm_bss_export.dg',roots=roots,mode=mode)
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
            payload.extend(struct.pack('<6Q',len(c['label']),c['byte_count'],c['alignment'],c['cap'],c['rol'],c['nout']))
            payload.extend(c['label'])
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
            self.assertEqual(status,c['status'],(label,index,'status',c['label'],c['byte_count'],c['alignment']))
            if not status:
                self.assertEqual(written,len(c['text']),(label,index,'written'))
                self.assertEqual(out[:written],c['text'],(label,index,'output'))
            outs.append(out[:written] if not status else None)
        self.assertEqual(offset,len(run.stdout))
        return outs

    def run_both(self,cases,label):
        return {mode:self.run_cases(exe,cases,label+'-'+mode)for mode,exe in self.executables.items()}

    def test_format_boundaries_and_capacity(self):
        rng=random.Random(0x0C85005)
        aligns=[1,2,4,8,16,32,64,128,256,512,1024,2048,4096]
        labels=[b'__dong_a',b'__dong_BSS1',b'__dong_'+b'z'*121]
        cases=[]
        for lab in labels:
            for align in (1,8,4096):
                for n in (0,1,7,8,16,100):
                    need=need_total(lab,n,align)
                    self.assertEqual(need,23+len(lab)+len(str(align))+len(str(n)))
                    cases+=[item(lab,n,align),item(lab,n,align,cap=need+5),item(lab,n,align,cap=max(0,need-1))]
        # illegal labels / alignments
        for lab in (b'__dong_',b'__dong_!',b'dong_abc',b'__Dong_a',b''):
            cases.append(item(lab,8,8,cap=64,status=INVALID))
        for align in (0,3,5,7,9,8192,4100):
            cases.append(item(b'__dong_x',8,align,cap=64,status=INVALID))
        # huge byte_count: format only, no giant host alloc
        huge=(1<<64)-1
        cases+=[item(b'__dong_max',huge,8),item(b'__dong_max',huge,8,cap=10,status=CAPACITY)]
        for i in range(40):
            lab=PREFIX+(''.join(rng.choice('abcXYZ012_')for _ in range(rng.randint(1,10)))).encode()
            n=rng.randint(0,512);align=rng.choice(aligns)
            cases+=[item(lab,n,align,rol=int(i%7==0)),item(lab,n,align,cap=max(0,need_total(lab,n,align)-1))]
        cases+=[item(b'__dong_ok',8,8,nout=1,cap=64,status=INVALID),
                item(b'__dong_!',8,8,cap=0,status=INVALID)]
        self.run_both(cases,'seeded')
        self.records.append(dict(test='format-boundaries-capacity',cases=len(cases),modes=2,
                                 preflights=self.PREFLIGHTS,passed=True))

    def test_dong_bss_object_symbol_and_size(self):
        samples=[
            (b'__dong_s0',0,8),(b'__dong_s1',1,1),(b'__dong_s8',8,8),
            (b'__dong_s16',16,16),(b'__dong_s7',7,4),(b'__dong_s64',64,32),
            (b'__dong_s4096',17,4096),
        ]
        cases=[item(lab,n,a)for lab,n,a in samples]
        results=self.run_both(cases,'bss-obj')
        obj_dir=self.work/'bss-obj';obj_dir.mkdir(exist_ok=True)
        checked=0
        for mode,outs in results.items():
            for index,((lab,n,align),out) in enumerate(zip(samples,outs)):
                self.assertIsNotNone(out,(mode,index))
                # Leading resb 1 then Dong text inside .bss
                body=b'section .bss\nresb 1\n'+out
                for fmt,reader in (('elf64',elf64_sym_value_and_bss_size),('win64',coff_sym_value_and_bss_size)):
                    asm=obj_dir/f'{mode}-{index:02d}-{fmt}.asm'
                    obj=obj_dir/f'{mode}-{index:02d}-{fmt}.o'
                    asm.write_bytes(body)
                    r=subprocess.run([str(self.nasm),'-f',fmt,*nasm_flags(self.nasm),'-o',str(obj),str(asm)],
                                     capture_output=True,timeout=30)
                    self.assertEqual(r.returncode,0,(mode,index,fmt,r.stderr))
                    value,bss_size=reader(obj,lab)
                    # After resb 1, the next aligned offset is exactly alignment.
                    self.assertEqual(value,align,(mode,index,fmt,'value',value,align))
                    self.assertEqual(bss_size,align+n,(mode,index,fmt,'bss_size',bss_size,align,n))
                    checked+=1
        self.records.append(dict(test='dong-bss-object-symbol-size',samples=len(samples),
                                 checks=checked,modes=2,formats=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;src=root/'src'/'bootstrap';src.mkdir(parents=True)
        (root/'wrapper'/'probe').mkdir(parents=True)
        (src/'nasm_bss.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'wrapper'/'probe'/'nasm_bss_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',dependency_root(self.work),root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-align-kw',
             'out[0]=97;out[1]=108;out[2]=105;out[3]=103;out[4]=110;out[5]=32;',
             'out[0]=97;out[1]=108;out[2]=105;out[3]=120;out[4]=110;out[5]=32;',
             [item(b'__dong_x',8,8)],'output'),
            ('bad-resb-fill',
             'out[at+7]=49;at+=8;',
             'out[at+7]=50;at+=8;',
             [item(b'__dong_x',8,8)],'output'),
            ('bad-early-capacity',
             'if total>out.len{return CAPACITY;}',
             'out[0]=97;if total>out.len{return CAPACITY;}',
             [item(b'__dong_x',8,8,cap=5)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
