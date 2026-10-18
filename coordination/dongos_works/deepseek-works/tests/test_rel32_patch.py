"""Actual Dong rel32 patching, against a Python model using byte-coverage sets and struct.pack('<i')."""
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

SOURCE=WORKS/'deepseek-works/src/bootstrap/rel32_patch.dg'
OK,INVALID,CAPACITY=0,1,2
USIZE_MAX=2**64-1
PREFLIGHTS=19
WRAPPER='''module probe.rel32_export;
import bootstrap.rel32_patch as r;
export("dong_rel32_apply") pub unsafe fn apply(code:*u8,nc:usize,patches:*const r.Patch,np:usize,applied:*usize)u64{unsafe{
 return r.apply(slice_from_raw_parts(code,nc),slice_from_raw_parts(patches,np),applied);
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
typedef struct {uint64_t at,target;} Patch;
_Static_assert(sizeof(Patch)==16&&__builtin_offsetof(Patch,target)==8,"Patch layout");
extern uint64_t ABI dong_rel32_apply(uint8_t*,uint64_t,const Patch*,uint64_t,uint64_t*);
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
/* Numerically valid high code range, never dereferenced: only must-reject displacements use it. */
#define FAKE_ADDR 0x4000000000000000ull
#define FAKE_LEN 0x100000010ull
#define FAKE ((uint8_t*)(uintptr_t)FAKE_ADDR)
/* Bad descriptors and i32 overflow: INVALID with every arena byte unchanged. */
static unsigned invalid(void){
 static uint8_t arena[2048],saved[2048];const unsigned total=17;
 uint8_t*code=arena;Patch*p=(Patch*)(arena+256);uint64_t*a=(uint64_t*)(arena+1536);
 uint64_t lo=(uint64_t)(uintptr_t)arena;
 if(lo<FAKE_ADDR+FAKE_LEN&&FAKE_ADDR<lo+sizeof(arena))exit(96);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));p[0].at=0;p[0].target=8;p[1].at=8;p[1].target=0;
  switch(i){
   case 13:p[0].at=0;p[0].target=0x80000004ull;break;                         /* +2^31 */
   case 14:p[0].at=0x7ffffffdull;p[0].target=0;break;                         /* -(2^31+1) */
   case 15:p[0].at=0;p[0].target=0x80000003ull;p[1].at=0x80000000ull;p[1].target=3;break; /* +2^31-1 then -(2^31+1) */
   case 16:p[0].at=0x100000000ull;p[0].target=0;break;                        /* at+4<=len, -(2^32+4) */
   default:break;
  }
  memcpy(saved,arena,sizeof(arena));uint64_t r=0;
  switch(i){
   case 0:r=dong_rel32_apply(code,64,p,2,NULL);break;
   case 1:r=dong_rel32_apply(code,64,p,2,(uint64_t*)(arena+1540));break;
   case 2:r=dong_rel32_apply(code,64,p,2,(uint64_t*)(arena+8));break;
   case 3:r=dong_rel32_apply(code,64,p,2,(uint64_t*)(p+1));break;
   case 4:r=dong_rel32_apply(code,300,p,2,a);break;
   case 5:r=dong_rel32_apply(arena+1500,64,p,2,a);break;
   case 6:r=dong_rel32_apply(code,64,(Patch*)(arena+260),2,a);break;
   case 7:r=dong_rel32_apply(NULL,64,p,2,a);break;
   case 8:r=dong_rel32_apply(code,64,NULL,2,a);break;
   case 9:r=dong_rel32_apply(code,64,p,UINT64_MAX/16+1,a);break;
   case 10:r=dong_rel32_apply((uint8_t*)(uintptr_t)(UINT64_MAX-15),64,p,2,a);break;
   case 11:r=dong_rel32_apply(code,64,(Patch*)(uintptr_t)(UINT64_MAX-15),2,a);break;
   case 12:r=dong_rel32_apply(code,64,p,2,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 15:r=dong_rel32_apply(FAKE,FAKE_LEN,p,2,a);break;
   default:r=dong_rel32_apply(FAKE,FAKE_LEN,p,1,a);break;
  }
  if(r!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)r);exit(93);}
 }
 /* The same fake descriptor with real, aligned, non-aliasing metadata passes every descriptor
    check: with no patches it succeeds, so the rejections above come from the displacement. */
 for(unsigned i=0;i<2;i++){
  memset(arena,0xa5,sizeof(arena));p[0].at=0;p[0].target=0x80000004ull;memcpy(saved,arena,sizeof(arena));memset(saved+1536,0,8);
  uint64_t r=dong_rel32_apply(FAKE,FAKE_LEN,i?NULL:p,0,a);
  if(r!=0||*a!=0||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"fake ok %u status %u\n",i,(unsigned)r);exit(97);}
 }
 return total+2;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t flag,count,preflights=0;read_exact(&flag,8);if(flag)preflights=invalid();
 read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[3];read_exact(h,sizeof(h));uint64_t nc=h[0],np=h[1],ro=h[2];
  if(nc>1000000||np>100000)exit(94);
  uint64_t pb=np*16;uint8_t*cb=malloc(nc+64),*orig=malloc(nc+1),*pin=malloc(pb+64),*pcopy=malloc(pb+1);uint64_t meta[3];
  if(!cb||!orig||!pin||!pcopy)exit(95);
  memset(cb,0xa5,nc+64);read_exact(cb+32,nc);memcpy(orig,cb+32,nc);
  memset(pin,0xa5,pb+64);read_exact(pin+32,pb);memcpy(pcopy,pin+32,pb);
  const Patch*pp=np?(const Patch*)(pin+32):NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro&&np){pages=(pb/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,pcopy,pb);ro_protect(page,pages);pp=(const Patch*)page;}
  memset(meta,0xa5,sizeof(meta));uint64_t*applied=meta+1;
  uint64_t r=dong_rel32_apply(nc?cb+32:NULL,nc,pp,np,applied);
  uint64_t valid=(!pb||!memcmp(pcopy,pp,pb))&&filled(pin,32)&&filled(pin+32+pb,32)&&
    filled(cb,32)&&filled(cb+32+nc,32)&&filled(meta,8)&&filled(meta+2,8);
  if(r)valid=valid&&!memcmp(orig,cb+32,nc)&&filled(applied,8);
  else valid=valid&&*applied==np;
  uint64_t response[3]={r,valid,r?0:*applied};write_exact(response,24);write_exact(cb+32,nc);
  if(page)ro_free(page,pages);
  free(cb);free(orig);free(pin);free(pcopy);
 }return 0;
}
'''


def model(code,patches):
    """Status and resulting bytes; failure returns the original buffer."""
    n=len(code);covered=set()
    for at,target in patches:
        if at+4>n or target>n:return INVALID,bytes(code)
        if not -2**31<=target-(at+4)<2**31:return INVALID,bytes(code)
    for at,_ in patches:
        field=set(range(at,at+4))
        if field&covered:return INVALID,bytes(code)
        covered|=field
    out=bytearray(code)
    for at,target in patches:out[at:at+4]=struct.pack('<i',target-(at+4))
    return OK,bytes(out)


def case(code,patches,readonly=0,status=None):
    code=bytes(code);st,result=model(code,patches)
    if status is not None:assert st==status,(status,st,len(code),patches)
    return dict(code=code,patches=list(patches),readonly=readonly,status=st,result=result)


class Rel32PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native rel32 patching requires NASM/GCC')
        cls.work=WORKS/'deepseek-works/build/D14'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/rel32_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([WORKS/'deepseek-works/src',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/rel32_export.dg',roots=roots,mode=mode)
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
            payload.extend(struct.pack('<3Q',len(c['code']),len(c['patches']),c['readonly']))
            payload.extend(c['code'])
            for at,target in c['patches']:payload.extend(struct.pack('<2Q',at,target))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,PREFLIGHTS if preflight else 0)
        offset=8
        for index,c in enumerate(cases):
            status,guard,applied=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            got=run.stdout[offset:offset+len(c['code'])];offset+=len(c['code'])
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status'))
            if not status:self.assertEqual(applied,len(c['patches']),(label,index,'applied'))
            self.assertEqual(got,c['result'],(label,index,'bytes'))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label,preflight=True):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode,preflight)

    def test_random_patch_sets_against_model(self):
        rng=random.Random(0xC16C);cases=[]
        for i in range(600):
            n=rng.randint(0,80);code=bytes(rng.randrange(256)for _ in range(n))
            patches=[];taken=set()
            for _ in range(rng.randint(0,12)):
                if n<4:break
                at=rng.randint(0,n-4)
                if taken&set(range(at,at+4)):continue
                taken|=set(range(at,at+4));patches.append((at,rng.randint(0,n)))
            rng.shuffle(patches)
            kind=i%6
            if kind==1 and patches:                                     # exact duplicate at (any target)
                at,_=rng.choice(patches);patches.insert(rng.randint(0,len(patches)),(at,rng.randint(0,n)))
            elif kind==2 and patches:                                   # partial overlap by 1..3 bytes, either side
                at,_=rng.choice(patches);other=at+rng.choice([-3,-2,-1,1,2,3])
                if 0<=other<=n-4:patches.insert(rng.randint(0,len(patches)),(other,rng.randint(0,n)))
            elif kind==3:                                               # one bad item anywhere
                bad=rng.choice([(max(n-3,0),0),(n+rng.randint(0,5),0),(0,n+1),(0,USIZE_MAX),(USIZE_MAX,0),(USIZE_MAX-3,n),(USIZE_MAX-2,0)])
                patches.insert(rng.randint(0,len(patches)),bad)
            cases.append(case(code,patches,readonly=int(i%25==0)))
        # A larger buffer: 2000 non-overlapping fields in shuffled order, read-only patch array.
        n=65536;code=bytes(rng.randrange(256)for _ in range(n));ats=rng.sample(range(0,n//4-2),2000)
        big=[(4*a,rng.randint(0,n))for a in ats]
        cases.append(case(code,big,readonly=1,status=OK))
        cases.append(case(code,big+[(big[1234][0]+2,0)],status=INVALID))
        self.run_both(cases,'random')
        self.assertGreater(sum(c['status']==OK for c in cases),250);self.assertGreater(sum(c['status']==INVALID for c in cases),150)
        self.records.append(dict(test='random-model',cases=len(cases),seed='0xC16C',modes=2,
            ok=sum(c['status']==OK for c in cases),invalid=sum(c['status']==INVALID for c in cases),passed=True))

    def test_directions_bounds_and_overlaps(self):
        z=lambda n:bytes(range(n))   # distinct non-zero-ish bytes so untouched bytes are visible
        cases=[case(b'',[],status=OK),case(z(3),[],status=OK),case(z(3),[(0,0)],status=INVALID),
               case(z(4),[(0,4)],status=OK),                                  # zero displacement
               case(z(4),[(0,0)],status=OK),                                  # -4
               case(z(16),[(0,16)],status=OK),case(z(16),[(12,0)],status=OK),   # forward to end label, backward to 0
               case(z(16),[(5,9)],status=OK),case(z(16),[(5,8)],status=OK),case(z(16),[(5,10)],status=OK),
               case(z(16),[(12,16),(0,16),(4,0),(8,8)],status=OK),             # four touching fields, shuffled
               case(z(32),[(20,3),(0,31),(9,9),(4,32),(28,0)],status=OK),
               case(z(16),[(12,17)],status=INVALID),case(z(16),[(13,0)],status=INVALID),case(z(16),[(16,16)],status=INVALID),
               case(z(16),[(0,USIZE_MAX)],status=INVALID),case(z(16),[(USIZE_MAX,0)],status=INVALID),
               case(z(16),[(USIZE_MAX-3,0)],status=INVALID),case(z(16),[(USIZE_MAX-2,0)],status=INVALID),
               case(z(16),[(2**63,0)],status=INVALID),
               case(z(16),[(4,0),(4,0)],status=INVALID),case(z(16),[(4,0),(4,9)],status=INVALID),
               case(z(16),[(4,0),(5,0)],status=INVALID),case(z(16),[(7,0),(4,0)],status=INVALID),
               case(z(16),[(4,0),(1,0)],status=INVALID),case(z(16),[(6,0),(8,0)],status=INVALID),
               case(z(16),[(10,0),(0,4),(12,16)],status=INVALID),             # overlap between non-adjacent items
               case(z(32),[(0,1),(4,2),(8,3),(12,4),(16,5),(20,6),(24,7),(28,32),(26,0)],status=INVALID),  # last pair only
               case(z(32),[(0,1),(4,2),(8,3),(12,4),(16,5),(20,6),(24,7),(28,33)],status=INVALID),  # later bad item
               case(z(32),[(28,33),(0,1),(4,2)],status=INVALID),
               case(b'\xa5'*16,[(0,16)],status=OK),case(b'\xa5'*16,[(4,0)],status=OK)]
        for n in (4,5,7,8,64):
            cases+=[case(z(n),[(n-4,n)],status=OK),case(z(n),[(n-4,0)],status=OK),case(z(n),[(n-4,n+1)],status=INVALID),
                    case(z(n),[(n-3,n)],status=INVALID),case(z(n),[(0,n)],readonly=1,status=OK)]
        self.run_both(cases,'bounds')
        self.records.append(dict(test='directions-bounds-overlaps',cases=len(cases),preflights_per_native=PREFLIGHTS,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/rel32_patch.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/rel32_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        loop='while i<n{if !fits(cl,patches[i].at,patches[i].target){return INVALID;}i+=1;}'
        controls=[
            ('bad-base-at',' let end=at+4;\n',' let end=at;\n',
             [case(bytes(16),[(0,16)],status=OK)],'bytes'),
            ('bad-early-write',loop,loop.replace('i+=1;}','put(code,patches[i].at,rel(patches[i].at,patches[i].target));i+=1;}'),
             [case(bytes(16),[(0,8),(8,17)],status=INVALID)],'guard/atomicity'),
            ('bad-adjacent-only','var j=i+1;while j<n{','var j=i+1;while j<n&&j<i+2{',
             [case(bytes(16),[(10,0),(0,4),(12,16)],status=INVALID)],'status'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first. Fake-address preflights are skipped
            # here: a wrong source could dereference them, and a crash does not count as rejection.
            self.run_both(cases,name+'-good',preflight=False)
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode,preflight=False)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
