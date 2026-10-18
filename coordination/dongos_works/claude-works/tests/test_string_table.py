"""Actual Dong deduplicated NUL-terminated string table, against an independent Python dict build."""
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

SOURCE=WORKS/'claude-works/src/bootstrap/string_table.dg'
OK,INVALID,CAPACITY=0,1,2
MAX=2**64-1
WRAPPER='''module probe.strtab_export;
import bootstrap.string_table as s;
export("dong_string_table") pub unsafe fn build(names:*const s.Name,nn:usize,bytes:*const u8,nb:usize,
 offsets:*usize,no:usize,table:*u8,nt:usize,result:*s.Result)u64{unsafe{
 return s.build(slice_from_raw_parts(names,nn),slice_from_raw_parts(bytes,nb),slice_from_raw_parts(offsets,no),
  slice_from_raw_parts(table,nt),result);
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
typedef struct {uint64_t first,count;} Name;
typedef struct {uint64_t used,bytes;} Result;
_Static_assert(sizeof(Name)==16&&sizeof(Result)==16&&__builtin_offsetof(Result,bytes)==8,"layout");
extern uint64_t ABI dong_string_table(const Name*,uint64_t,const uint8_t*,uint64_t,uint64_t*,uint64_t,uint8_t*,uint64_t,Result*);
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
/* Bad descriptors: INVALID with every arena byte unchanged. Fake addresses only where
   rejection must happen first, and each case has no earlier alias/alignment fault. */
static unsigned invalid(void){
 static uint8_t arena[2048],saved[2048];const unsigned total=18;
 Name*n=(Name*)arena;uint8_t*b=arena+128;uint64_t*o=(uint64_t*)(arena+512);uint8_t*t=arena+1024;Result*r=(Result*)(arena+1536);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(b,"abc",3);n[0].first=0;n[0].count=3;n[1].first=1;n[1].count=2;
  memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_string_table(n,2,b,3,o,8,t,64,NULL);break;
   case 1:s=dong_string_table(n,2,b,3,o,8,t,64,(Result*)(arena+1540));break;
   case 2:s=dong_string_table(n,2,b,3,o,8,t,64,(Result*)n);break;
   case 3:s=dong_string_table(n,2,b,3,o,8,t,64,(Result*)(arena+128));break;      /* result over bytes */
   case 4:s=dong_string_table(n,2,b,3,(uint64_t*)n,8,t,64,r);break;
   case 5:s=dong_string_table(n,2,b,3,o,8,b+1,8,r);break;                         /* table over bytes */
   case 6:s=dong_string_table(n,2,b,3,o,8,(uint8_t*)o+8,8,r);break;               /* table over offsets */
   case 7:s=dong_string_table(n,2,b,3,o,8,t,64,(Result*)(t+16));break;            /* result over table */
   case 8:s=dong_string_table(n,2,b,3,o,8,t,64,(Result*)(o+2));break;             /* result over offsets */
   case 9:s=dong_string_table((Name*)(arena+4),2,b,3,o,8,t,64,r);break;
   case 10:s=dong_string_table(n,2,b,3,(uint64_t*)(arena+516),8,t,64,r);break;
   case 11:s=dong_string_table(NULL,2,b,3,o,8,t,64,r);break;
   case 12:s=dong_string_table(n,2,NULL,3,o,8,t,64,r);break;
   case 13:s=dong_string_table(n,2,b,3,o,8,NULL,64,r);break;
   case 14:s=dong_string_table(n,UINT64_MAX/16+1,b,3,o,8,t,64,r);break;
   case 15:s=dong_string_table(n,2,(const uint8_t*)(uintptr_t)(UINT64_MAX-1),3,o,8,t,64,r);break;
   case 16:s=dong_string_table(n,2,b,3,o,8,(uint8_t*)(uintptr_t)(UINT64_MAX-7),9,r);break;
   default:s=dong_string_table(n,2,b,3,o,UINT64_MAX/8+1,t,64,r);break;
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
  uint64_t h[5];read_exact(h,sizeof(h));uint64_t nn=h[0],nb=h[1],no=h[2],nt=h[3],ro=h[4];
  if(nn>100000||nb>1000000||no>100000||nt>2000000)exit(94);
  uint64_t xb=nn*16;uint8_t*in=malloc(xb+nb+96),*copy=malloc(xb+nb+1),*table=malloc(nt+64);uint64_t*off=malloc((no+8)*8);uint64_t meta[6];
  if(!in||!copy||!table||!off)exit(95);
  memset(in,0xa5,xb+nb+96);read_exact(in+32,xb);read_exact(in+64+xb,nb);memcpy(copy,in+32,xb);memcpy(copy+xb,in+64+xb,nb);
  const Name*n=nn?(const Name*)(in+32):NULL;const uint8_t*b=nb?in+64+xb:NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro){pages=((xb+nb)/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,xb+nb);ro_protect(page,pages);
   n=nn?(const Name*)page:NULL;b=nb?page+xb:NULL;}
  memset(table,0xa5,nt+64);memset(off,0xa5,(no+8)*8);memset(meta,0xa5,sizeof(meta));Result*r=(Result*)(meta+2);
  uint64_t s=dong_string_table(n,nn,b,nb,no?off+4:NULL,no,nt?table+32:NULL,nt,r);
  uint64_t valid=(!xb||!memcmp(copy,n,xb))&&(!nb||!memcmp(copy+xb,b,nb))&&(ro||(filled(in,32)&&filled(in+32+xb,32)&&filled(in+64+xb+nb,32)))&&
    filled(table,32)&&filled(table+32+nt,32)&&filled(off,32)&&filled(off+4+no,32)&&filled(meta,16)&&filled(meta+4,16);
  if(s)valid=valid&&filled(table+32,nt)&&filled(off+4,no*8)&&filled(r,16);
  else valid=valid&&r->used==nn&&r->bytes<=nt&&filled(table+32+r->bytes,nt-r->bytes)&&filled(off+4+nn,(no-nn)*8);
  uint64_t response[4]={s,valid,s?0:r->used,s?0:r->bytes};write_exact(response,32);
  if(!s){write_exact(off+4,nn*8);write_exact(table+32,r->bytes);}
  if(page)ro_free(page,pages);
  free(in);free(copy);free(table);free(off);
 }return 0;
}
'''


def reference(names,data,no,nt):
    """Independent dict-based build. Returns (status, offsets, table)."""
    for first,count in names:
        if count==0 or first+count>len(data) or 0 in data[first:first+count]:return INVALID,None,None
    table=bytearray(b'\0');seen={};offsets=[]
    for first,count in names:
        key=bytes(data[first:first+count])
        if key not in seen:seen[key]=len(table);table+=key+b'\0'
        offsets.append(seen[key])
    if no<len(names) or nt<len(table):return CAPACITY,None,None
    return OK,offsets,bytes(table)


def case(names,data,no=None,nt=None,readonly=0,status=None):
    full=reference(names,data,MAX,MAX)
    if no is None:no=len(names)
    if nt is None:nt=len(full[2])if full[2] is not None else 8
    expected=reference(names,data,no,nt)
    if status is not None:assert expected[0]==status,(status,expected,names,data)
    return dict(names=names,data=bytes(data),no=no,nt=nt,readonly=readonly,expected=expected)


def random_case(rng):
    pool=rng.choice([b'ab',b'abc\xff\xe4\xb8\xad',bytes(range(1,256)),b'xyxyxyxy'])
    data=bytes(rng.choice(pool)for _ in range(rng.randint(1,60)))
    names=[]
    for _ in range(rng.randint(0,25)):
        if names and rng.random()<0.3:names.append(rng.choice(names));continue      # repeat an earlier descriptor
        first=rng.randrange(len(data));count=rng.randint(1,min(6,len(data)-first));names.append((first,count))
    return names,data


class StringTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native string table requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C18'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/strtab_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([WORKS/'claude-works/src',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/strtab_export.dg',roots=roots,mode=mode)
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

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:
            payload.extend(struct.pack('<5Q',len(c['names']),len(c['data']),c['no'],c['nt'],c['readonly']))
            for f,k in c['names']:payload.extend(struct.pack('<2Q',f,k))
            payload.extend(c['data'])
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,18)
        offset=8
        for index,c in enumerate(cases):
            status,guard,used,size=struct.unpack_from('<4Q',run.stdout,offset);offset+=32
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['expected'][0],(label,index,'status'))
            if not status:
                n=len(c['names']);offsets=list(struct.unpack_from('<%dQ'%n,run.stdout,offset));offset+=8*n
                table=run.stdout[offset:offset+size];offset+=size
                self.assertEqual(used,n,(label,index,'used'))
                self.assertEqual(table,c['expected'][2],(label,index,'table bytes'))
                self.assertEqual(offsets,c['expected'][1],(label,index,'offsets'))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def test_random_tables_against_python_dict(self):
        rng=random.Random(0xC18D);cases=[]
        for i in range(400):
            names,data=random_case(rng);c=case(names,data,readonly=int(i%40==0));cases.append(c)
            if i%4==0:cases.append(case(names,data,no=len(names)+3,nt=c['nt']+9))
        words=[('w%d'%(i%700)).encode()for i in range(3000)];data=b''.join(words);names=[];at=0
        for w in words:names.append((at,len(w)));at+=len(w)
        cases.append(case(names,data,readonly=1))
        self.run_both(cases,'random')
        self.assertTrue(all(c['expected'][0]==OK for c in cases))
        self.records.append(dict(test='random-dict',cases=len(cases),seed='0xC18D',modes=2,passed=True))

    def test_sharing_bytes_invalid_and_capacity(self):
        d=b'abcabcab\xe4\xb8\xad\xff\x01'
        cases=[case([],b'',status=OK),case([],b'',no=0,nt=1,status=OK),case([],b'x',nt=1,status=OK),
               case([(0,3),(3,3)],d,status=OK),                                   # different descriptors, same bytes: shared
               case([(0,3),(1,3),(2,3)],d,status=OK),                             # same length, different content: distinct
               case([(0,2),(0,3),(0,2)],d,status=OK),                             # prefix kept separate, repeat shared
               case([(8,3),(11,1),(12,1),(8,3)],d,status=OK),                      # non-ASCII and 0x01 bytes kept as-is
               case([(0,1)]*5,d,status=OK),case([(0,len(d))],d,status=OK)]
        self.assertEqual(reference([(0,3),(3,3)],d,9,99)[1:],([1,1],b'\0abc\0'))
        bad=b'ab\0cd'
        cases+=[case([(0,0)],d,status=INVALID),case([(0,2),(1,0)],d,status=INVALID),case([(0,3)],bad,status=INVALID),
                case([(0,2),(2,1)],bad,status=INVALID),case([(0,2),(3,2),(1,2)],bad,status=INVALID),     # last item contains NUL
                case([(len(d),1)],d,status=INVALID),case([(len(d)-1,2)],d,status=INVALID),case([(MAX,1)],d,status=INVALID),
                case([(1,MAX)],d,status=INVALID),case([(0,1)],b'',status=INVALID),
                case([(0,2),(9,9)],d,no=0,nt=0,status=INVALID)]                                         # INVALID before CAPACITY
        for names in ([(0,3)],[(0,3),(3,3),(1,2)],[(0,1)]*4):
            need=len(reference(names,d,MAX,MAX)[2])
            cases+=[case(names,d,nt=need-1,status=CAPACITY),case(names,d,no=len(names)-1,status=CAPACITY),
                    case(names,d,no=0,nt=0,status=CAPACITY),case(names,d,nt=need+5,no=len(names)+2,status=OK)]
        cases+=[case([],b'',nt=0,status=CAPACITY),case([(0,2),(3,2)],b'ab\0ab',readonly=1,status=OK)]
        self.run_both(cases,'bounds')
        self.records.append(dict(test='sharing-bytes-invalid-capacity',cases=len(cases),invalid_preflights_per_native=18,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/string_table.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/strtab_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        d=b'abcabdxy'
        controls=[
            # Deduplicates by length only.
            ('bad-length-dedup',' var k:usize=0;while k<n{if bytes[a+k]!=bytes[b+k]{return false;}k+=1;}return true;',
             ' return true;',[case([(0,3),(3,3)],d)],'table bytes|offsets'),
            # Repeated names get a fresh copy instead of the first offset (both passes agree on size).
            ('bad-duplicate-copy','fn earliest(names:[]const Name,bytes:[]const u8,i:usize)usize{\n var j:usize=0;while j<i{if same(names,bytes,j,i){return j;}j+=1;}return i;',
             'fn earliest(names:[]const Name,bytes:[]const u8,i:usize)usize{\n return i;',
             [case([(0,2),(0,2)],d,nt=16)],'table bytes|offsets'),
            # Publishes table[0] before validation finds a NUL in the last name.
            ('bad-early-prefix','if !valid(names,bytes,offsets,table,result){return INVALID;}',
             'if !valid(names,bytes,offsets,table,result){return INVALID;}if table.len!=0{table[0]=0;}',
             [case([(0,2),(2,3)],b'ab\0cd',nt=16,status=INVALID)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
