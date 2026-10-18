"""Actual Dong aligned, deduplicated raw constant pool, against an independent Python dict layout."""
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

SOURCE=ROOT/'lang/bootstrap/data_pool_layout.dg'
OK,INVALID,CAPACITY=0,1,2
MAX=2**64-1
ALIGNMENTS=(1,2,4,8,16)
PREFLIGHTS=22
WRAPPER='''module probe.pool_export;
import bootstrap.data_pool_layout as d;
export("dong_data_pool_layout") pub unsafe fn build(blobs:*const d.Blob,nn:usize,raw:*const u8,nb:usize,
 offsets:*usize,no:usize,image:*u8,ni:usize,result:*d.Result)u64{unsafe{
 return d.build(slice_from_raw_parts(blobs,nn),slice_from_raw_parts(raw,nb),slice_from_raw_parts(offsets,no),
  slice_from_raw_parts(image,ni),result);
}}
'''
# Test-only bridge: a private copy where the checked layout helpers are made pub, nothing else changes.
BRIDGE_WRAPPER='''module probe.pool_bridge;
import bootstrap.data_pool_layout as d;
export("dong_pool_fits") pub unsafe fn fits(c:usize,a:usize,n:usize)u64{unsafe{if d.fits(c,a,n){return 1;}return 0;}}
export("dong_pool_start") pub unsafe fn start(c:usize,a:usize)usize{unsafe{return d.start(c,a);}}
'''
COMMON=r'''
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
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static void binary_io(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
}
'''
HARNESS=COMMON+r'''
typedef struct {uint64_t first,count,alignment;} Blob;
typedef struct {uint64_t used,bytes;} Result;
_Static_assert(sizeof(Blob)==24&&__builtin_offsetof(Blob,alignment)==16&&sizeof(Result)==16&&__builtin_offsetof(Result,bytes)==8,"layout");
extern uint64_t ABI dong_data_pool_layout(const Blob*,uint64_t,const uint8_t*,uint64_t,uint64_t*,uint64_t,uint8_t*,uint64_t,Result*);
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
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
/* Bad descriptors: INVALID with every arena byte unchanged. The two blobs and raw "abc" are
   valid data (layout needs 2 offsets, 6 image bytes), so only the targeted descriptor fault can
   reject; fake addresses only where the numeric span check must reject before any access. */
static unsigned invalid(void){
 static uint8_t arena[2048],saved[2048];const unsigned total=21;
 Blob*n=(Blob*)arena;uint8_t*b=arena+128;uint64_t*o=(uint64_t*)(arena+512);uint8_t*t=arena+1024;Result*r=(Result*)(arena+1536);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(b,"abc",3);
  n[0].first=0;n[0].count=3;n[0].alignment=1;n[1].first=1;n[1].count=2;n[1].alignment=4;
  if(i==11){Blob legal[2]={{0,3,1},{1,2,4}};memcpy(arena+4,legal,sizeof(legal));}
  memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_data_pool_layout(n,2,b,3,o,8,t,64,NULL);break;
   case 1:s=dong_data_pool_layout(n,2,b,3,o,8,t,64,(Result*)(arena+1540));break;
   case 2:s=dong_data_pool_layout(n,2,b,3,o,8,t,64,(Result*)n);break;                /* result over blobs */
   case 3:s=dong_data_pool_layout(n,2,b,3,o,8,t,64,(Result*)(arena+128));break;      /* result over raw */
   case 4:s=dong_data_pool_layout(n,2,b,3,(uint64_t*)n,8,t,64,r);break;              /* offsets over blobs */
   case 5:s=dong_data_pool_layout(n,2,b,3,(uint64_t*)b,8,t,64,r);break;              /* offsets over raw */
   case 6:s=dong_data_pool_layout(n,2,b,3,o,8,(uint8_t*)n+8,8,r);break;              /* image over blobs */
   case 7:s=dong_data_pool_layout(n,2,b,3,o,8,b+1,8,r);break;                         /* image over raw */
   case 8:s=dong_data_pool_layout(n,2,b,3,o,8,(uint8_t*)o+8,8,r);break;              /* image over offsets */
   case 9:s=dong_data_pool_layout(n,2,b,3,o,8,t,64,(Result*)(t+16));break;           /* result over image */
   case 10:s=dong_data_pool_layout(n,2,b,3,o,8,t,64,(Result*)(o+2));break;           /* result over offsets */
   case 11:s=dong_data_pool_layout((Blob*)(arena+4),2,b,3,o,8,t,64,r);break;
   case 12:s=dong_data_pool_layout(n,2,b,3,(uint64_t*)(arena+516),8,t,64,r);break;
   case 13:s=dong_data_pool_layout(NULL,2,b,3,o,8,t,64,r);break;
   case 14:s=dong_data_pool_layout(n,2,NULL,3,o,8,t,64,r);break;
   case 15:s=dong_data_pool_layout(n,2,b,3,NULL,8,t,64,r);break;
   case 16:s=dong_data_pool_layout(n,2,b,3,o,8,NULL,64,r);break;
   case 17:s=dong_data_pool_layout(n,UINT64_MAX/24+1,b,3,o,8,t,64,r);break;
   case 18:s=dong_data_pool_layout(n,2,(const uint8_t*)(uintptr_t)(UINT64_MAX-1),3,o,8,t,64,r);break;
   case 19:s=dong_data_pool_layout(n,2,b,3,o,8,(uint8_t*)(uintptr_t)(UINT64_MAX-7),9,r);break;
   default:s=dong_data_pool_layout(n,2,b,3,o,UINT64_MAX/8+1,t,64,r);break;
  }
  if(s!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)s);exit(93);}
 }
 return total;
}
/* Read-only inputs may alias: raw is the blob array itself. */
static unsigned aliased(void){
 static uint64_t blk[6],copy[6],off[4],img[4];Result res;
 Blob*n=(Blob*)blk;memset(off,0xa5,sizeof(off));memset(img,0xa5,sizeof(img));memset(&res,0xa5,sizeof(res));
 n[0].first=0;n[0].count=8;n[0].alignment=8;n[1].first=8;n[1].count=8;n[1].alignment=1;memcpy(copy,blk,sizeof(blk));
 uint64_t s=dong_data_pool_layout(n,2,(const uint8_t*)blk,48,off,2,(uint8_t*)img,16,&res);
 if(s||res.used!=2||res.bytes!=16||off[0]!=0||off[1]!=8||!filled(off+2,16)||memcmp(img,blk,16)||!filled(img+2,16)||memcmp(copy,blk,sizeof(blk)))
 {fprintf(stderr,"aliased read-only inputs status %u\n",(unsigned)s);exit(96);}
 return 1;
}
int main(void){
 binary_io();
 uint64_t preflights=invalid()+aliased(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[5];read_exact(h,sizeof(h));uint64_t nn=h[0],nb=h[1],no=h[2],ni=h[3],ro=h[4];
  if(nn>100000||nb>1000000||no>100000||ni>2000000)exit(94);
  uint64_t xb=nn*24;uint8_t*in=malloc(xb+nb+96),*copy=malloc(xb+nb+1),*image=malloc(ni+64);uint64_t*off=malloc((no+8)*8);uint64_t meta[6];
  if(!in||!copy||!image||!off)exit(95);
  memset(in,0xa5,xb+nb+96);read_exact(in+32,xb);read_exact(in+64+xb,nb);memcpy(copy,in+32,xb);memcpy(copy+xb,in+64+xb,nb);
  const Blob*n=nn?(const Blob*)(in+32):NULL;const uint8_t*b=nb?in+64+xb:NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro){pages=((xb+nb)/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,xb+nb);ro_protect(page,pages);
   n=nn?(const Blob*)page:NULL;b=nb?page+xb:NULL;}
  memset(image,0xa5,ni+64);memset(off,0xa5,(no+8)*8);memset(meta,0xa5,sizeof(meta));Result*r=(Result*)(meta+2);
  uint64_t s=dong_data_pool_layout(n,nn,b,nb,no?off+4:NULL,no,ni?image+32:NULL,ni,r);
  uint64_t valid=(!xb||!memcmp(copy,n,xb))&&(!nb||!memcmp(copy+xb,b,nb))&&(ro||(filled(in,32)&&filled(in+32+xb,32)&&filled(in+64+xb+nb,32)))&&
    filled(image,32)&&filled(image+32+ni,32)&&filled(off,32)&&filled(off+4+no,32)&&filled(meta,16)&&filled(meta+4,16);
  if(s)valid=valid&&filled(image+32,ni)&&filled(off+4,no*8)&&filled(r,16);
  else valid=valid&&r->used==nn&&no>=nn&&r->bytes<=ni&&filled(image+32+r->bytes,ni-r->bytes)&&filled(off+4+nn,(no-nn)*8);
  uint64_t response[4]={s,valid,s?0:r->used,s?0:r->bytes};write_exact(response,32);
  if(!s&&valid){write_exact(off+4,nn*8);write_exact(image+32,r->bytes);}
  if(page)ro_free(page,pages);
  free(in);free(copy);free(image);free(off);
 }return 0;
}
'''
BRIDGE=COMMON+r'''
extern uint64_t ABI dong_pool_fits(uint64_t,uint64_t,uint64_t);
extern uint64_t ABI dong_pool_start(uint64_t,uint64_t);
int main(void){
 binary_io();uint64_t count;read_exact(&count,8);
 while(count--){
  uint64_t q[3];read_exact(q,sizeof(q));uint64_t f=dong_pool_fits(q[0],q[1],q[2]);
  uint64_t response[2]={f,f?dong_pool_start(q[0],q[1]):0};write_exact(response,16);
 }return 0;
}
'''


def reference(blobs,data,no,nt):
    """Independent dict + arbitrary-precision layout. Returns (status, offsets, image)."""
    for first,count,alignment in blobs:
        if alignment not in ALIGNMENTS or first>len(data) or count>len(data)-first:return INVALID,None,None
    image=bytearray();seen={};offsets=[];cursor=0
    for first,count,alignment in blobs:
        key=(alignment,bytes(data[first:first+count]))
        if key not in seen:
            start=-(-cursor//alignment)*alignment
            if start+count>MAX:return INVALID,None,None
            seen[key]=start;image+=bytes(start-cursor)+key[1];cursor=start+count
        offsets.append(seen[key])
    if no<len(blobs) or nt<cursor:return CAPACITY,None,None
    return OK,offsets,bytes(image)


def check_layout(blobs,data,offsets,image):
    """Properties of an OK layout, checked apart from how reference() built it."""
    first_at={};covered=set()
    for (first,count,alignment),off in zip(blobs,offsets):
        content=bytes(data[first:first+count]);key=(alignment,content)
        assert off%alignment==0 and image[off:off+count]==content,(blobs,offsets)
        if key in first_at:assert first_at[key]==off,(key,offsets)
        else:
            assert not covered&set(range(off,off+count)),('placements overlap',key)
            assert all(o<=off for o in first_at.values()),('first-occurrence order',key)
            first_at[key]=off;covered|=set(range(off,off+count))
    assert all(image[i]==0 for i in range(len(image)) if i not in covered),'gaps are 00'


def case(blobs,data,no=None,nt=None,readonly=0,status=None):
    full=reference(blobs,data,MAX,MAX)
    if no is None:no=len(blobs)
    if nt is None:nt=len(full[2])if full[2] is not None else 8
    expected=reference(blobs,data,no,nt)
    if status is not None:assert expected[0]==status,(status,expected,blobs,data)
    if expected[0]==OK:check_layout(blobs,data,expected[1],expected[2])
    return dict(blobs=blobs,data=bytes(data),no=no,nt=nt,readonly=readonly,expected=expected)


def random_case(rng):
    pool=rng.choice([b'ab',b'\x00\xff',b'abc\xff\xe4\xb8\xad\x00',bytes(range(256)),b'xyxyxyxy',b'\x80\xc0\xfe'])
    data=bytes(rng.choice(pool)for _ in range(rng.randint(0,60)))
    blobs=[]
    for _ in range(rng.randint(0,25)):
        roll=rng.random()
        if blobs and roll<0.25:blobs.append(rng.choice(blobs));continue                         # repeat a descriptor
        if blobs and roll<0.4:f,k,a=rng.choice(blobs);blobs.append((f,k,rng.choice(ALIGNMENTS)));continue   # same bytes, maybe other alignment
        first=rng.randint(0,len(data));count=rng.randint(0,min(6,len(data)-first))
        blobs.append((first,count,rng.choice(ALIGNMENTS)))
    return blobs,data


class DataPoolLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native data pool layout requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/D16'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');(cls.work/'bridge.c').write_text(BRIDGE,encoding='utf-8')
        cls.executables={};cls.bridges={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        # The real module is compiled byte-for-byte from a private root holding only it and the wrapper.
        root=cls.private_root('real',SOURCE.read_bytes(),'pool_export',WRAPPER)
        bridged=SOURCE.read_text(encoding='utf-8')
        for name in ('fits','start'):
            assert bridged.count('\nfn %s('%name)==1,name;bridged=bridged.replace('\nfn %s('%name,'\npub fn %s('%name,1)
        bridge=cls.private_root('bridge',bridged.encode('utf-8'),'pool_bridge',BRIDGE_WRAPPER)
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([root],root/'probe/pool_export.dg','probe.c',mode,mode)
            cls.bridges[mode]=cls.build([bridge],bridge/'probe/pool_bridge.dg','bridge.c',mode,'bridge-'+mode)

    @classmethod
    def private_root(cls,name,source,module,wrapper):
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/data_pool_layout.dg').write_bytes(source)
        (root/'probe'/(module+'.dg')).write_text(wrapper,encoding='utf-8')
        return root

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,entry,harness,mode,name):
        compiled=compile_file(entry,roots=roots,mode=mode)
        asm=cls.work/(name+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
        native='win64'if os.name=='nt'else'elf64'
        obj=cls.work/(name+'.o');exe=cls.work/(name+('.exe'if os.name=='nt'else''))
        for fmt in ('elf64','win64'):
            output=obj if fmt==native else cls.work/(name+'.'+fmt+'.o')
            cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',output,asm],name+'-'+fmt)
        cls.command([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',cls.work/harness,obj,'-o',exe],name+'-link')
        return exe

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        files={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in cls.work.rglob('*')if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,artifact_sha256=files,
            records=cls.records,integrated=False,OS_VM_built=False),indent=2)+'\n')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:
            payload.extend(struct.pack('<5Q',len(c['blobs']),len(c['data']),c['no'],c['nt'],c['readonly']))
            for f,k,a in c['blobs']:payload.extend(struct.pack('<3Q',f,k,a))
            payload.extend(c['data'])
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,PREFLIGHTS)
        offset=8
        for index,c in enumerate(cases):
            status,guard,used,size=struct.unpack_from('<4Q',run.stdout,offset);offset+=32
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['expected'][0],(label,index,'status'))
            if not status:
                n=len(c['blobs']);expected_offsets,expected_image=c['expected'][1:]
                self.assertEqual(used,n,(label,index,'used'))
                self.assertEqual(size,len(expected_image),(label,index,'result bytes'))
                offsets=list(struct.unpack_from('<%dQ'%n,run.stdout,offset));offset+=8*n
                image=run.stdout[offset:offset+size];offset+=size
                self.assertEqual(offsets,expected_offsets,(label,index,'offsets'))
                self.assertEqual(image,expected_image,(label,index,'image bytes'))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def test_random_layouts_against_python_dict(self):
        rng=random.Random(0xC21D);cases=[]
        for i in range(400):
            blobs,data=random_case(rng);c=case(blobs,data,readonly=int(i%40==0));cases.append(c)
            if i%4==0:cases.append(case(blobs,data,no=len(blobs)+3,nt=c['nt']+9))
        words=[('w%d'%(i%700)).encode()+b'\xff\x00'for i in range(3000)];data=b''.join(words);blobs=[];at=0
        for i,w in enumerate(words):blobs.append((at,len(w),ALIGNMENTS[(i//700)%5]));at+=len(w)
        cases.append(case(blobs,data,readonly=1))
        self.run_both(cases,'random')
        self.assertTrue(all(c['expected'][0]==OK for c in cases))
        self.assertTrue(any(len(c['expected'][1])>len(set(c['expected'][1]))for c in cases))
        self.records.append(dict(test='random-dict',cases=len(cases),seed='0xC21D',modes=2,passed=True))

    def test_dedup_padding_invalid_and_capacity(self):
        d=b'\xde\xad\xbe\xef\xff\x00\x80abab\xc3'
        L=len(d)
        self.assertEqual(reference([(0,4,1),(0,4,4),(0,4,1),(0,4,4)],d,9,99)[1:],([0,4,0,4],d[:4]*2))
        self.assertEqual(reference([(0,1,1),(0,0,8)],d,9,99)[1:],([0,8],b'\xde'+bytes(7)))
        self.assertEqual(reference([(7,2,2),(0,3,1),(9,2,2)],d,9,99)[1:],([0,2,0],b'ab\xde\xad\xbe'))
        cases=[case([],b'',no=0,nt=0,status=OK),case([],b'x',no=3,nt=5,status=OK),          # empty: 0/0, NULL outputs
               case([(0,0,1)],b'',nt=0,status=OK),case([(L,0,16)],d,nt=0,status=OK),        # empty blob, first==raw.len
               case([(0,1,1),(0,0,8)],d,status=OK),                                         # empty blob still advances cursor
               case([(0,0,16),(3,0,16),(L,0,16)],d,status=OK),                              # equal empty keys share offset 0
               case([(0,1,1),(0,0,16),(5,0,16),(0,0,4)],d,status=OK),                       # empty keys per alignment
               case([(0,4,1),(0,4,4),(0,4,1),(0,4,4)],d,status=OK),                         # same bytes, other alignment: distinct
               case([(7,2,2),(0,3,1),(9,2,2)],d,status=OK),                                 # repeated substring shared
               case([(7,2,1),(8,2,1),(9,2,1)],d,status=OK),                                 # same length, other content
               case([(0,3,1),(0,2,1),(1,3,16)],d,status=OK),                                # prefix kept separate, gap of 00
               case([(4,3,8),(5,1,2),(0,L,16),(4,3,8)],d,status=OK),                        # 0xff/0x00/0x80 copied as-is
               case([(0,1,a)for a in (1,2,4,8,16,16,8,4,2,1)],d,status=OK),case([(0,L,1)],d,status=OK)]
        cases+=[case([(0,1,0)],d,status=INVALID),case([(0,1,3)],d,status=INVALID),case([(0,1,32)],d,status=INVALID),
                case([(0,0,MAX)],d,status=INVALID),case([(0,2,1),(1,2,4),(0,1,5)],d,status=INVALID),    # last item bad alignment
                case([(0,2,1),(L,1,1)],d,status=INVALID),case([(0,2,8),(1,2,8),(L+1,0,1)],d,status=INVALID),   # last item out of raw
                case([(L-1,2,1)],d,status=INVALID),case([(MAX,1,1)],d,status=INVALID),case([(1,MAX,1)],d,status=INVALID),
                case([(MAX,0,1)],d,status=INVALID),case([(0,1,1)],b'',status=INVALID),
                case([(0,2,1),(9,9,1)],d,no=0,nt=0,status=INVALID)]                                    # INVALID before CAPACITY
        for blobs in ([(0,3,1)],[(0,3,1),(3,3,4),(1,2,16)],[(0,1,1)]*4,[(0,1,1),(0,0,8)],[(0,2,2),(0,2,4)]):
            need=len(reference(blobs,d,MAX,MAX)[2])
            cases+=[case(blobs,d,nt=need-1,status=CAPACITY),case(blobs,d,no=len(blobs)-1,status=CAPACITY),
                    case(blobs,d,no=0,nt=0,status=CAPACITY),case(blobs,d,nt=need+5,no=len(blobs)+2,status=OK)]
        cases+=[case([(0,0,1),(0,0,2)],b'',no=1,nt=8,status=CAPACITY),
                case([(5,1,1),(5,1,16),(0,4,8)],d,readonly=1,status=OK),case([(1,3,4),(9,2,1)],d,readonly=1,nt=40,no=7,status=OK)]
        self.run_both(cases,'bounds')
        self.records.append(dict(test='dedup-padding-invalid-capacity',cases=len(cases),
            native_preflights_per_executable=PREFLIGHTS,modes=2,passed=True))

    def test_checked_layout_arithmetic_bridge(self):
        rng=random.Random(0xC21A)
        queries=[(0,1,0),(0,16,0),(MAX,1,0),(MAX,1,1),(MAX-1,1,1),(MAX-15,16,0),(MAX-15,16,15),(MAX-15,16,16),
                 (MAX-14,16,0),(MAX,2,0),(MAX-2,2,1),(MAX-2,2,2),(MAX-7,8,7),(MAX-7,8,8),(5,16,MAX-16),(5,16,MAX-15),
                 (1,2,MAX-2),(1,2,MAX-1),(0,1,MAX),(1,1,MAX),(MAX-3,4,3),(MAX-4,4,0)]
        for _ in range(200):
            c=rng.choice([rng.randrange(64),MAX-rng.randrange(64),rng.randrange(MAX+1)])
            n=rng.choice([rng.randrange(64),MAX-rng.randrange(64)-c%17,rng.randrange(MAX+1)])
            queries.append((c,rng.choice(ALIGNMENTS),max(n,0)))
        payload=struct.pack('<Q',len(queries))+b''.join(struct.pack('<3Q',*q)for q in queries)
        for mode,exe in self.bridges.items():
            run=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=120)
            (self.work/('bridge-'+mode+'.output')).write_bytes(run.stdout)
            self.assertEqual(run.returncode,0,(mode,run.stderr))
            self.assertEqual(len(run.stdout),16*len(queries))
            for index,(c,a,n) in enumerate(queries):
                start=-(-c//a)*a;fits=int(start+n<=MAX)
                self.assertEqual(struct.unpack_from('<2Q',run.stdout,16*index),(fits,start if fits else 0),(mode,c,a,n,'checked layout'))
        self.records.append(dict(test='checked-layout-bridge',queries=len(queries),seed='0xC21A',modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.private_root(name,source.replace(old,new,1).encode('utf-8'),'pool_export',WRAPPER)
        return {mode:self.build([root],root/'probe/pool_export.dg','probe.c',mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        d=b'abcdef\xff\x00'
        controls=[
            # Deduplicates by bytes only, ignoring alignment.
            ('bad-alignment-dedup',' if a.alignment!=b.alignment{return false;}\n','',
             [case([(0,2,1),(0,2,4)],d)],"'result bytes'|'offsets'"),
            # Rounds the cursor down instead of up (the overflow guard is unchanged).
            ('bad-round-down','fn start(cursor:usize,alignment:usize)usize{return cursor+pad(cursor,alignment);}',
             'fn start(cursor:usize,alignment:usize)usize{return cursor-(cursor&(alignment-1));}',
             [case([(0,1,1),(1,2,4)],d)],"'result bytes'|'offsets'"),
            # Skips the alignment gap without writing 00 (offsets and size stay right).
            ('bad-unzeroed-gap','   while at<s{image[at]=0;at+=1;}\n','   at=s;\n',
             [case([(0,1,1),(1,2,4)],d)],"'image bytes'"),
            # Writes image[0] before validation finds a bad alignment in the last blob.
            ('bad-early-write','if !valid(blobs,raw,offsets,image,result){return INVALID;}',
             'if !valid(blobs,raw,offsets,image,result){return INVALID;}if image.len!=0{image[0]=0;}',
             [case([(0,2,1),(2,3,3)],d,nt=16,status=INVALID)],"'guard/atomicity'"),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
