"""Actual Dong static ELF64 image emitter: independent struct model, real kernel exec.elf.validate, bounds and atomicity."""
import hashlib
import json
import os
from pathlib import Path
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

SOURCE=WORKS/'claude-works/src/bootstrap/elf64_image.dg'
DOC=WORKS/'claude-works/src/bootstrap/elf64_image.md'
KERNEL_ELF=ROOT/'kernel/exec/elf.dg'                   # read-only reference parser (module exec.elf, no imports)
OK,INVALID,CAPACITY=0,1,2
U64=2**64-1
LIMIT=0x100_0000
BASE=0x40_0000
PREFLIGHTS=15
BAD_PERMISSIONS,BAD_ENTRY=0x0403_0006,0x0403_0009        # exec.elf error codes
SMALL=65536                                              # outputs up to this size are returned and compared in full
WRAPPER='''module probe.elf_export;
import bootstrap.elf64_image as img;
import exec.elf as elf;
export("dong_elf_emit") pub unsafe fn emit(code:*const u8,nc:usize,data:*const u8,nd:usize,bss:usize,entry:usize,out:*u8,no:usize,written:*usize)u64{unsafe{
 return img.emit(slice_from_raw_parts(code,nc),slice_from_raw_parts(data,nd),bss,entry,slice_from_raw_parts(out,no),written);
}}
export("kernel_elf_validate") fn validate(raw: *const u8, length: usize, bias: u64, out: *elf.Plan) u64 {
    unsafe { match elf.validate(slice_from_raw_parts(raw,length),bias,out) { ok => { return 0; }, err(code) => { return code; }, } }
}
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
extern uint64_t ABI dong_elf_emit(const uint8_t*,uint64_t,const uint8_t*,uint64_t,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
extern uint64_t ABI kernel_elf_validate(const uint8_t*,uint64_t,uint64_t,void*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static int zero(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i])return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
/* Deterministic input bytes, regenerated independently by the Python model. */
static uint8_t pattern(uint64_t i,uint64_t seed){return (uint8_t)(i*131u+seed*29u+(i>>9));}
static void fill(uint8_t*p,uint64_t n,uint64_t seed){for(uint64_t i=0;i<n;i++)p[i]=pattern(i,seed);}
static int intact(const uint8_t*p,uint64_t n,uint64_t seed){for(uint64_t i=0;i<n;i++)if(p[i]!=pattern(i,seed))return 0;return 1;}
static uint8_t*ro_alloc(uint64_t n){
#ifdef _WIN32
 return VirtualAlloc(NULL,n,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*p=mmap(NULL,n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return p==MAP_FAILED?NULL:p;
#endif
}
static int ro_protect(void*p,uint64_t n){
#ifdef _WIN32
 DWORD old;return VirtualProtect(p,n,PAGE_READONLY,&old)!=0;
#else
 return mprotect(p,n,PROT_READ)==0;
#endif
}
static void ro_free(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;VirtualFree(p,0,MEM_RELEASE);
#else
 munmap(p,n);
#endif
}
#define FAKE(x) ((void*)(uintptr_t)(x))
/* Descriptor/alias preflights. Every other field is legal (64-byte code, 64-byte data, no bss, entry 0, out 16 KiB,
   enough for the 8256-byte image) so only the target check can reject it. Every failure is reported, then exit 93. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[40960],saved[40960];const unsigned total=15;unsigned failed=0;
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memset(arena,'c',64);memset(arena+128,'d',64);memcpy(saved,arena,sizeof(arena));
  const uint8_t*c=arena,*d=arena+128;uint8_t*o=arena+4096;uint64_t ol=16384;uint64_t*w=(uint64_t*)(arena+24576);
  switch(i){
   case 0:w=NULL;break;                                                  /* written NULL */
   case 1:w=(uint64_t*)(arena+24577);break;                              /* written odd */
   case 2:w=FAKE(UINT64_MAX-7);o=NULL;ol=0;break;                        /* written end overflow, legal empty out */
   case 3:o=FAKE(UINT64_MAX-4095);break;                                 /* out end overflow */
   case 4:o=NULL;break;                                                  /* NULL non-empty out */
   case 5:c=NULL;break;                                                  /* NULL non-empty code */
   case 6:d=NULL;break;                                                  /* NULL non-empty data */
   case 7:c=FAKE(UINT64_MAX-31);break;                                   /* code end overflow */
   case 8:d=FAKE(UINT64_MAX-31);break;                                   /* data end overflow */
   case 9:w=(uint64_t*)(arena+56);break;                                 /* written in code's tail */
   case 10:w=(uint64_t*)(arena+184);break;                               /* written in data's tail */
   case 11:o=arena+56;ol=8;break;                                        /* out over code's last 8 bytes only */
   case 12:o=arena+184;ol=8;break;                                       /* out over data's last 8 bytes only */
   case 13:w=(uint64_t*)o;break;                                         /* written on out prefix */
   default:w=(uint64_t*)(o+16376);break;                                 /* written in out's unused tail */
  }
  uint64_t s=dong_elf_emit(c,64,d,64,0,0,o,ol,w);
  int same=!memcmp(saved,arena,sizeof(arena));
  if(s!=1||!same){fprintf(stderr,"invalid preflight %u status %u unchanged %d\n",i,(unsigned)s,same);failed++;}
 }
 if(failed)exit(93);
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 static _Alignas(16) uint64_t plan[134+2];   /* exec.elf.Plan is 1072 bytes */
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[8];read_exact(h,sizeof(h));
  uint64_t nc=h[0],nd=h[1],bss=h[2],entry=h[3],cap=h[4],ro=h[5],share=h[6],seed=h[7];
  if(nc>0x1000001||nd>0x1000001||cap>0x1000100||(share&&nd>nc)||(ro&&nc+nd>8192))exit(94);
  uint8_t*cbuf=malloc(nc+64),*dbuf=share?NULL:malloc(nd+64),*out=malloc(cap+64);static _Alignas(8) uint64_t meta[3];
  if(!cbuf||(!share&&!dbuf)||!out)exit(95);
  memset(cbuf,0xa5,nc+64);fill(cbuf+32,nc,seed);
  const uint8_t*code=cbuf+32,*data;uint64_t dseed=seed;
  if(share)data=code;else{memset(dbuf,0xa5,nd+64);fill(dbuf+32,nd,seed+1);data=dbuf+32;dseed=seed+1;}
  uint8_t*page=NULL;uint64_t pages=4096*4,protected_ok=1;
  if(ro){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,code,nc);memcpy(page+8192,data,nd);
         protected_ok=ro_protect(page,pages);code=page;data=page+8192;}
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=dong_elf_emit(nc?code:NULL,nc,nd?data:NULL,nd,bss,entry,cap?out+32:NULL,cap,written);
  uint64_t w=s?0:*written;
  uint64_t valid=protected_ok&&intact(code,nc,seed)&&intact(data,nd,dseed)&&filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(!share)valid=valid&&filled(cbuf,32)&&filled(cbuf+32+nc,32)&&filled(dbuf,32)&&filled(dbuf+32+nd,32);
  if(s)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&w<=cap&&filled(out+32+w,cap-w);
  /* Regions of a successful image (the header page is checked field by field in Python). */
  uint64_t regions=0,vstatus=UINT64_MAX;memset(plan,0,sizeof(plan));
  if(!s&&w>=4096+nc){
   uint64_t code_end=4096+nc,data_offset=(code_end+4095)&~4095ull;
   regions=!memcmp(out+32+4096,code,nc);
   if(nd||bss)regions=regions&&w==data_offset+nd&&zero(out+32+code_end,data_offset-code_end)&&!memcmp(out+32+data_offset,data,nd);
   else regions=regions&&w==code_end;
  }
  if(!s)vstatus=kernel_elf_validate(out+32,w,0,plan);
  uint64_t nret=s?0:(w<=65536?w:4096);
  uint64_t response[6]={s,valid,w,vstatus,regions,nret};write_exact(response,48);write_exact(plan,22*8);write_exact(out+32,nret);
  if(page)ro_free(page,pages);
  free(cbuf);free(dbuf);free(out);
 }return 0;
}
'''


def pattern(n,seed):return bytes((i*131+seed*29+(i>>9))&255 for i in range(n))


def layout(nc,nd,bss,entry):
    """Independent layout model: (code_end, data_offset or None, file_size, phnum, entry address)."""
    code_end=4096+nc
    if nd or bss:
        data_offset=(code_end+4095)//4096*4096
        return code_end,data_offset,data_offset+nd,2,BASE+4096+entry
    return code_end,None,code_end,1,BASE+4096+entry


def expected_header(nc,nd,bss,entry):
    """Independent byte model of the whole 4096-byte header page."""
    code_end,data_offset,file_size,phnum,entry_address=layout(nc,nd,bss,entry)
    ident=b'\x7fELF'+bytes([2,1,1,0])+bytes(8)
    header=ident+struct.pack('<HHIQQQIHHHHHH',2,62,1,entry_address,64,0,0,64,56,phnum,0,0,0)
    header+=struct.pack('<IIQQQQQQ',1,5,0,BASE,BASE,code_end,code_end,4096)
    if phnum==2:header+=struct.pack('<IIQQQQQQ',1,6,data_offset,BASE+data_offset,BASE+data_offset,nd,nd+bss,4096)
    assert len(header)==64+56*phnum
    return header+bytes(4096-len(header))


def expected_image(nc,nd,bss,entry,seed,share):
    code_end,data_offset,file_size,_,_=layout(nc,nd,bss,entry)
    code=pattern(nc,seed);data=code[:nd]if share else pattern(nd,seed+1)
    image=expected_header(nc,nd,bss,entry)+code
    if data_offset is not None:image+=bytes(data_offset-code_end)+data
    assert len(image)==file_size
    return image


def parse(header):
    """Independent struct parse of the ELF header and program headers."""
    e=struct.unpack_from('<16sHHIQQQIHHHHHH',header,0)
    fields=dict(ident=e[0],type=e[1],machine=e[2],version=e[3],entry=e[4],phoff=e[5],shoff=e[6],flags=e[7],
                ehsize=e[8],phentsize=e[9],phnum=e[10],shentsize=e[11],shnum=e[12],shstrndx=e[13])
    fields['segments']=[dict(zip(('type','flags','offset','vaddr','paddr','filesz','memsz','align'),
                                 struct.unpack_from('<IIQQQQQQ',header,64+56*i)))for i in range(e[10])]
    return fields


def profile_reject(header,file_size):
    """Independent field validator for this profile; returns the reason an image is not acceptable, or None."""
    f=parse(header)
    for s in f['segments']:
        if s['type']!=1 or s['flags']not in(5,6):return 'permissions'                  # R+X text or R+W data only, never W+X
        if s['filesz']>s['memsz']or s['offset']+s['filesz']>file_size or s['vaddr']%4096!=s['offset']%4096:return 'range'
    text=[s for s in f['segments']if s['flags']&1]
    if not any(s['vaddr']<=f['entry']<s['vaddr']+s['filesz']for s in text):return 'entry'
    return None


def expected_plan(nc,nd,bss,entry):
    """What exec.elf.validate must report for this layout, computed independently."""
    code_end,data_offset,_,phnum,entry_address=layout(nc,nd,bss,entry)
    pages=lambda start,size:((start+size+4095)//4096*4096-start//4096*4096)//4096
    segs=[(BASE,0,code_end,code_end,BASE,pages(BASE,code_end)*4096,5,4096)]
    if phnum==2:segs.append((BASE+data_offset,data_offset,nd,nd+bss,BASE+data_offset,pages(BASE+data_offset,nd+bss)*4096,6,4096))
    return entry_address,len(segs),sum(s[5]//4096 for s in segs),segs


# (code, data, bss, entry, share data with code)
VECTORS=[(1,0,0,0,0),(4095,0,0,4094,0),(4096,1,0,0,0),(4097,0,100,4096,0),(100,4096,4096,50,0),(4097,10,0,0,0),
         (8,3,5,7,0),(64,64,0,0,1),
         (LIMIT-4096,0,0,LIMIT-4097,0),                          # largest code: the file is exactly 16 MiB
         (4096,LIMIT-8192,LIMIT,0,0),                            # largest data next to the largest bss
         (4096,0,LIMIT,4095,0)]                                  # bss only, largest


class Elf64ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native ELF image test requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C45'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,DOC,KERNEL_ELF,Path(__file__)]}
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.executables=cls.build_all('good',SOURCE.read_text(encoding='utf-8'))

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        after={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,DOC,KERNEL_ELF,Path(__file__)]}
        files={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in cls.work.rglob('*')if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,source_sha256_after=after,artifact_sha256=files,
            records=cls.records,integrated=False,OS_VM_built=False),indent=2)+'\n')
        if after!=cls.inputs:raise AssertionError('inputs changed during the run')

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=180)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build_all(cls,name,text):
        """Stage only this component and the read-only kernel exec.elf parser, then build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir();(root/'kernel/exec').mkdir(parents=True)
        (root/'bootstrap/elf64_image.dg').write_text(text,encoding='utf-8')
        shutil.copyfile(KERNEL_ELF,root/'kernel/exec/elf.dg')
        (root/'probe/elf_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/elf_export.dg',roots=[root,root/'kernel'],mode=mode)
            asm=cls.work/(tag+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
            obj=cls.work/(tag+'.o');exe=cls.work/(tag+('.exe'if os.name=='nt'else''))
            for fmt in ('elf64','win64'):
                output=obj if fmt==cls.native else cls.work/(tag+'.'+fmt+'.o')
                cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',output,asm],tag+'-'+fmt)
            cls.command([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',cls.work/'probe.c',obj,'-o',exe],tag+'-link')
            result[mode]=exe
        return result

    def run_cases(self,exe,cases,label):
        """cases: (nc, nd, bss, entry, cap, ro, share, status). Returns per case (image bytes or header, kernel status, plan)."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for i,(nc,nd,bss,entry,cap,ro,share,_) in enumerate(cases):payload.extend(struct.pack('<8Q',nc,nd,bss,entry,cap,ro,share,i))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=600)
        (self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],PREFLIGHTS)
        offset=8;results=[]
        for i,c in enumerate(cases):
            s,valid,w,vstatus,regions,nret=struct.unpack_from('<6Q',run.stdout,offset);offset+=48
            plan=struct.unpack_from('<22Q',run.stdout,offset);offset+=176
            body=run.stdout[offset:offset+nret];offset+=nret
            self.assertEqual(valid,1,(label,i,'guard/atomicity',c))
            self.assertEqual(s,c[-1],(label,i,'status',c))
            results.append((w,body,vstatus,regions,plan,i)if s==OK else None)        # i is the pattern seed the harness used
        self.assertEqual(offset,len(run.stdout))
        return results

    def check_image(self,case,result,label):
        nc,nd,bss,entry,cap,ro,share,_=case
        w,body,vstatus,regions,plan,seed=result
        code_end,data_offset,file_size,phnum,entry_address=layout(nc,nd,bss,entry)
        self.assertEqual(w,file_size,(label,case,'file size'))
        self.assertEqual(regions,1,(label,case,'code/padding/data regions'))
        self.assertEqual(body[:4096],expected_header(nc,nd,bss,entry),(label,case,'header page'))
        if w<=SMALL:self.assertEqual(body,expected_image(nc,nd,bss,entry,seed,share),(label,case,'whole image'))
        f=parse(body)
        self.assertEqual((f['type'],f['machine'],f['entry'],f['phnum'],f['shoff'],f['shnum'],f['shentsize']),(2,62,entry_address,phnum,0,0,0))
        self.assertIsNone(profile_reject(body,w),(label,case,'independent profile'))
        self.assertEqual(vstatus,0,(label,case,'kernel exec.elf.validate'))
        want_entry,want_count,want_pages,want_segs=expected_plan(nc,nd,bss,entry)
        self.assertEqual((plan[0],plan[1],plan[2],plan[3],plan[4]),(want_entry,0,want_count,want_pages,0),(label,case,'kernel plan'))
        for j,seg in enumerate(want_segs):self.assertEqual(tuple(plan[6+8*j:14+8*j]),seg,(label,case,'kernel segment',j))

    def test_images_layout_kernel_and_capacity(self):
        cases=[]
        for nc,nd,bss,entry,share in VECTORS:
            n=layout(nc,nd,bss,entry)[2];ro=int(nc+nd<=8192 and not share)
            cases+=[(nc,nd,bss,entry,n,ro,share,OK),(nc,nd,bss,entry,n-1,0,share,CAPACITY),(nc,nd,bss,entry,0,0,share,CAPACITY)]
            if n<=SMALL:cases.append((nc,nd,bss,entry,n+100,0,share,OK))
        for mode,exe in self.executables.items():
            for c,r in zip(cases,self.run_cases(exe,cases,'images-'+mode)):
                if r:self.check_image(c,r,mode)
        self.assertLessEqual(len(VECTORS),24)
        self.records.append(dict(test='images-layout-kernel-capacity',vectors=len(VECTORS),cases=len(cases),modes=2,passed=True))

    def test_invalid_layouts_precede_capacity(self):
        bad=[(0,0,0,0),(1,0,0,1),(4096,0,0,4096),(64,0,0,U64),(LIMIT+1,0,0,0),(LIMIT-4095,0,0,0),
             (64,LIMIT+1,0,0),(64,0,LIMIT+1,0),(64,0,U64,0),(4096,LIMIT-8191,0,0)]
        cases=[]
        for nc,nd,bss,entry in bad:cases+=[(nc,nd,bss,entry,0,0,0,INVALID),(nc,nd,bss,entry,16384,0,0,INVALID)]
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'invalid-'+mode)
        self.records.append(dict(test='invalid-layouts',cases=len(cases),modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        vectors=[(nc,nd,bss,entry,share)for nc,nd,bss,entry,share in VECTORS if layout(nc,nd,bss,entry)[2]<=SMALL][:4]
        cases=[(nc,nd,bss,entry,layout(nc,nd,bss,entry)[2],0,share,OK)for nc,nd,bss,entry,share in vectors]
        for name,old,new,code,reason in [
            ('bad-entry-past-text','put(out,24,BASE+(TEXT_OFFSET+entry_offset) as u64,8);','put(out,24,BASE+code_end as u64,8);',BAD_ENTRY,'entry'),
            ('bad-text-rwx','segment(out,64,5,','segment(out,64,7,',BAD_PERMISSIONS,'permissions')]:
            self.assertEqual(source.count(old),1,name)
            for mode,exe in self.executables.items():                                       # same inputs pass first
                for c,r in zip(cases,self.run_cases(exe,cases,name+'-good-'+mode)):self.check_image(c,r,name+'-good-'+mode)
            for mode,exe in self.build_all(name,source.replace(old,new,1)).items():
                for c,r in zip(cases,self.run_cases(exe,cases,name+'-'+mode)):
                    w,body,vstatus,_,_,_=r                                                  # the bad emitter still returns OK
                    self.assertEqual(vstatus,code,(name,mode,c,'kernel exec.elf.validate'))
                    self.assertEqual(profile_reject(body,w),reason,(name,mode,c,'independent profile'))
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,
                                     rejected_by='kernel validate 0x%08x and independent profile (%s)'%(code,reason)))
        old='if file_size>on{return CAPACITY;}';new='if file_size>on{*written=file_size;return CAPACITY;}'
        self.assertEqual(source.count(old),1);case=[(4096,1,0,0,8192,0,0,CAPACITY)]
        for mode,exe in self.executables.items():self.run_cases(exe,case,'bad-early-written-good-'+mode)
        for mode,exe in self.build_all('bad-early-written',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.run_cases(exe,case,'bad-early-written-'+mode)
        self.records.append(dict(test='bad-early-written',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))

    def test_input_tail_aliases_are_reachable(self):
        """Preflight sensitivity: a real Dong checking code/data against out/written by their first byte only."""
        source=SOURCE.read_text(encoding='utf-8')
        line='if overlap(wp,8,cp,cn)||overlap(wp,8,dp,dn)||overlap(op,on,cp,cn)||overlap(op,on,dp,dn){return INVALID;}'
        self.assertEqual(source.count(line),1)
        bad=line.replace(',cn)',',1)').replace(',dn)',',1)')
        for mode,exe in self.executables.items():self.run_cases(exe,[],'tail-good-'+mode)   # same harness passes all 15
        for mode,exe in self.build_all('bad-input-first-byte',source.replace(line,bad,1)).items():
            run=subprocess.run([str(exe)],input=struct.pack('<Q',0),capture_output=True,timeout=60)
            err=run.stderr.decode('ascii','replace');(self.work/('bad-input-first-byte-'+mode+'.stderr')).write_text(err,encoding='ascii')
            self.assertEqual(run.returncode,93,(mode,err))
            failed=[int(line.split()[2])for line in err.splitlines()if line.startswith('invalid preflight ')]
            self.assertEqual(failed,[9,10,11,12],(mode,err))
        self.records.append(dict(test='bad-input-first-byte',compiled=True,native_executed=True,modes=2,rejected_by='preflight 9..12'))


if __name__=='__main__':unittest.main()
