"""Actual Dong bounded shortest SLEB128 i64 decode, against an independent Python model."""
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
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

SOURCE=ROOT/'lang/bootstrap/sleb128_decode.dg'
OK,INVALID,TRUNCATED,OVERFLOW,NONCANONICAL=0,1,2,3,4
MAX=2**64-1
I64_MIN=-2**63;I64_MAX=2**63-1
PREFLIGHTS=13
WRAPPER='''module probe.sleb_export;
import bootstrap.sleb128_decode as s;
export("dong_sleb128_decode") pub unsafe fn decode(input:*const u8,n:usize,value:*i64,consumed:*usize)u64{unsafe{
 return s.decode(slice_from_raw_parts(input,n),value,consumed);
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
extern uint64_t ABI dong_sleb128_decode(const uint8_t*,uint64_t,int64_t*,uint64_t*);
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
static unsigned invalid(void){
 static uint8_t arena[320] __attribute__((aligned(64))),saved[320];const unsigned total=13;
 const uint8_t*ip=arena+64;const uint64_t ilen=96;
 int64_t*val=(int64_t*)(arena+200);uint64_t*con=(uint64_t*)(arena+216);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));arena[64]=0x00;
  memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  const uint8_t*p=ip;uint64_t n=ilen;int64_t*v=val;uint64_t*c=con;
  switch(i){
   case 0:v=NULL;break;
   case 1:c=NULL;break;
   case 2:v=(int64_t*)(arena+201);break;
   case 3:c=(uint64_t*)(arena+217);break;
   case 4:v=(int64_t*)(arena+64);break;
   case 5:c=(uint64_t*)(arena+64);break;
   case 6:v=(int64_t*)(arena+200);c=(uint64_t*)(arena+200);break;
   case 7:p=NULL;break;
   case 8:p=(const uint8_t*)(uintptr_t)(UINT64_MAX-1);break;
   case 9:v=(int64_t*)(uintptr_t)(UINT64_MAX-7);break;
   case 10:c=(uint64_t*)(uintptr_t)(UINT64_MAX-7);break;
   case 11:v=(int64_t*)(arena+128);break;
   default:c=(uint64_t*)(arena+128);break;
  }
  s=dong_sleb128_decode(p,n,v,c);
  if(s!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)s);exit(93);}
 }
 memset(arena,0xa5,sizeof(arena));arena[64]=0x00;
 uint64_t s=dong_sleb128_decode(ip,ilen,val,con);
 if(s!=0||*val!=0||*con!=1){fprintf(stderr,"baseline status %u\n",(unsigned)s);exit(93);}
 return total;
}
static void alias_case(unsigned kind){
 if(kind>3)exit(94);
 static uint8_t arena[320] __attribute__((aligned(64))),saved[320];
 memset(arena,0xa5,sizeof(arena));arena[64]=0x00;
 const uint8_t*ip=arena+64;const uint64_t ilen=96;
 int64_t*val=(int64_t*)(arena+200);uint64_t*con=(uint64_t*)(arena+216);
 switch(kind){
  case 0:val=(int64_t*)(arena+64);break;
  case 1:con=(uint64_t*)(arena+64);break;
  case 2:val=(int64_t*)(arena+128);break;
  case 3:con=(uint64_t*)(arena+128);break;
 }
 memcpy(saved,arena,sizeof(arena));
 uint64_t s=dong_sleb128_decode(ip,ilen,val,con);
 uint64_t response[2]={s,memcmp(saved,arena,sizeof(arena))==0};
 write_exact(response,sizeof(response));
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t amode;read_exact(&amode,8);
 if(amode!=0){alias_case((unsigned)(amode-1));return 0;}
 uint64_t flag,count,preflights=0;read_exact(&flag,8);if(flag)preflights=invalid();read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[2];read_exact(h,sizeof(h));uint64_t n=h[0],ro=h[1];
  if(n>1000000)exit(94);
  uint8_t*ib=malloc(n+64),*copy=malloc(n+1);uint64_t meta[4];
  if(!ib||!copy)exit(95);
  memset(ib,0xa5,n+64);read_exact(ib+32,n);memcpy(copy,ib+32,n);
  const uint8_t*p=n?(const uint8_t*)(ib+32):NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro&&n){pages=(n/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,n);ro_protect(page,pages);p=(const uint8_t*)page;}
  memset(meta,0xa5,sizeof(meta));int64_t*val=(int64_t*)(meta+1);uint64_t*con=meta+2;
  uint64_t s=dong_sleb128_decode(p,n,val,con);
  uint64_t valid=(!n||!memcmp(copy,p,n))&&(ro||(filled(ib,32)&&filled(ib+32+n,32)))&&filled(meta,8)&&filled(meta+3,8);
  if(s)valid=valid&&filled(meta+1,16);
  uint64_t response[4]={s,valid,s?0:(uint64_t)*val,s?0:*con};write_exact(response,32);
  if(page)ro_free(page,pages);
  free(ib);free(copy);
 }return 0;
}
'''


def s64(u):
    return u-2**64 if u>=2**63 else u


def reference(data):
    """Decode a signed base-128 integer without native-width truncation.

    Python retains up to 70 bits; numerical range and independent re-encoding
    decide overflow/minimality. No special tenth-payload or adjacent-bit rule.
    """
    prefix=bytearray()
    for byte in data[:10]:
        prefix.append(byte)
        if byte&0x80:
            continue
        value=sum((part&0x7f)*128**i for i,part in enumerate(prefix))
        if byte&0x40:
            value-=128**len(prefix)
        if not I64_MIN<=value<=I64_MAX:
            return OVERFLOW,None,None
        if sleb_encode(value)!=bytes(prefix):
            return NONCANONICAL,None,None
        return OK,value,len(prefix)
    return (OVERFLOW if len(data)>=10 else TRUNCATED),None,None


def sleb_encode(value):
    out=bytearray()
    while True:
        byte=value&0x7f;value>>=7;sign=byte&0x40
        if (value==0 and not sign) or (value==-1 and sign):
            out.append(byte);return bytes(out)
        out.append(byte|0x80)


def case(data,status=None,value=None,consumed=None,readonly=0):
    data=bytes(data)
    st,val,con=reference(data)
    if status is not None:assert st==status,(status,st,data)
    if value is not None:assert val==value,(value,val,data)
    if consumed is not None:assert con==consumed,(consumed,con,data)
    return dict(data=data,readonly=readonly,status=st,value=val,consumed=con)


class Sleb128DecodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native SLEB128 decode requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/D20'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/sleb_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/sleb_export.dg',roots=roots,mode=mode)
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
        payload=bytearray(struct.pack('<3Q',0,int(preflight),len(cases)))
        for c in cases:
            payload.extend(struct.pack('<2Q',len(c['data']),c['readonly']))
            payload.extend(c['data'])
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,PREFLIGHTS if preflight else 0)
        offset=8
        for index,c in enumerate(cases):
            status,guard,value,consumed=struct.unpack_from('<4Q',run.stdout,offset);offset+=32
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status'))
            if status==OK:
                self.assertEqual(s64(value),c['value'],(label,index,'value'))
                self.assertEqual(consumed,c['consumed'],(label,index,'consumed'))
            else:
                self.assertEqual((value,consumed),(0,0),(label,index,'outputs-unchanged'))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label,preflight=True):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode,preflight)

    def run_alias(self,exe,kind,label):
        payload=struct.pack('<Q',kind+1)
        run=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=120)
        name=f'alias-{kind}-{label}-{Path(exe).stem}'
        (self.work/(name+'.input')).write_bytes(payload)
        (self.work/(name+'.output')).write_bytes(run.stdout)
        (self.work/(name+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        return struct.unpack('<2Q',run.stdout)

    def test_fixed_vectors(self):
        cases=[
            case(b'\x00',OK,0,1),case(b'\x01',OK,1,1),case(b'\x3f',OK,63,1),
            case(b'\xc0\x00',OK,64,2),case(b'\x7f',OK,-1,1),case(b'\x40',OK,-64,1),
            case(b'\xbf\x7f',OK,-65,2),case(b'\x80\x7f',OK,-128,2),
            case(b'\xff\x00',OK,127,2),case(b'\x80\x01',OK,128,2),
            case(b'\xff'*9+b'\x00',OK,I64_MAX,10),
            case(b'\x80'*9+b'\x7f',OK,I64_MIN,10),
        ]
        cases+=[case(b'\x00'+b'\xde\xad',OK,0,1),case(b'\x7f'+b'\xde\xad',OK,-1,1)]
        self.run_both(cases,'fixed')
        self.records.append(dict(test='fixed-vectors',cases=len(cases),modes=2,passed=True))

    def test_noncanonical_truncated_overflow(self):
        cases=[
            case(b'',TRUNCATED),case(b'\x80',TRUNCATED),case(b'\xff',TRUNCATED),
            case(b'\x80'*9,TRUNCATED),case(b'\xff'*9,TRUNCATED),
            case(b'\x80\x00',NONCANONICAL),case(b'\xff\x7f',NONCANONICAL),
            case(b'\x80'*9+b'\x00',NONCANONICAL),case(b'\xff'*9+b'\x7f',NONCANONICAL),
            case(b'\x80'*9+b'\x01',OVERFLOW),case(b'\xff'*9+b'\x7e',OVERFLOW),
            case(b'\x80'*10,OVERFLOW),case(b'\xff'*10,OVERFLOW),
            case(b'\x80'*9+b'\x02',OVERFLOW),case(b'\xff'*9+b'\x02',OVERFLOW),
        ]
        self.run_both(cases,'errors')
        self.records.append(dict(test='noncanonical-truncated-overflow',cases=len(cases),modes=2,passed=True))

    def test_boundaries_roundtrip_and_random(self):
        values=[0,1,-1,I64_MAX,I64_MIN,I64_MAX-1,I64_MIN+1]
        for groups in range(1,10):
            edge=1<<(7*groups-1)
            values.extend([edge-1,edge,-edge,-edge-1])
        cases=[case(sleb_encode(v),OK,v,len(sleb_encode(v)))for v in values]
        rng=random.Random(0xD2000)
        for _ in range(200):
            v=rng.randrange(I64_MIN,I64_MAX+1)
            cases.append(case(sleb_encode(v),OK,v,len(sleb_encode(v)),readonly=int(len(cases)%40==0)))
        self.run_both(cases,'roundtrip')
        self.records.append(dict(test='boundaries-roundtrip-random',cases=len(cases),seed='0xD2000',modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/sleb128_decode.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/sleb_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-10th-overflow','if cont!=0||(payload!=0&&payload!=0x7f){return OVERFLOW;}','if cont!=0{return OVERFLOW;}',
             [case(b'\x80'*9+b'\x01',status=OVERFLOW)],'status'),
            ('bad-sign-extension','if (payload&0x40)!=0{result|=MAX<<(shift+7);}','',
             [case(b'\x7f',status=OK,value=-1,consumed=1)],'value'),
            ('bad-early-write','pub unsafe fn decode(input:[]const u8,value:*i64,consumed:*usize)u64{unsafe{',
             'pub unsafe fn decode(input:[]const u8,value:*i64,consumed:*usize)u64{unsafe{\n *value=0;',
             [case(b'\x80\x80',status=TRUNCATED)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            self.run_both(cases,name+'-good',preflight=False)
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode,preflight=False)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))
        # Alias-miss: each of the 4 paths (value/consumed x prefix/tail) is observed
        # independently. Each selective mutant removes exactly one input-output overlap
        # check; alias_case(kind) reports exact status and full snapshot integrity
        # for one fixture, with separate evidence for every good/bad execution.
        overlap_full='if overlap(ip,inn,vp,8)||overlap(ip,inn,cp,8)||overlap(vp,8,cp,8){return false;}'
        rm_value='if overlap(ip,inn,cp,8)||overlap(vp,8,cp,8){return false;}'
        rm_consumed='if overlap(ip,inn,vp,8)||overlap(vp,8,cp,8){return false;}'
        bad_value=self.bad_build('bad-value-overlap',overlap_full,rm_value)
        bad_consumed=self.bad_build('bad-consumed-overlap',overlap_full,rm_consumed)
        alias_paths=[('value-prefix',0,bad_value),('consumed-prefix',1,bad_consumed),
                     ('value-tail',2,bad_value),('consumed-tail',3,bad_consumed)]
        for path_name,kind,bad in alias_paths:
            for mode,exe in self.executables.items():
                self.assertEqual(self.run_alias(exe,kind,'good'),(INVALID,1),(path_name,mode,'good'))
            for mode,exe in bad.items():
                observation=self.run_alias(exe,kind,'bad')
                self.assertEqual(observation,(OK,0),(path_name,mode,'bad exact status + changed snapshot'))
                self.records.append(dict(test='alias-'+path_name,compiled=True,native_executed=True,
                                         mode=mode,good_observation=[INVALID,1],bad_observation=list(observation),
                                         rejected_by='status/atomicity'))


if __name__=='__main__':unittest.main()
