"""Actual Dong raw-LF line index, against Python bytes.split(b'\\n') starts and bisect lookup."""
import bisect
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

SOURCE=WORKS/'claude-works/src/bootstrap/line_index.dg'
OK,INVALID,CAPACITY=0,1,2
USIZE_MAX=2**64-1
BUILD,LOCATE=0,1
PREFLIGHTS=(13,8)
WRAPPER='''module probe.line_index_export;
import bootstrap.line_index as l;
export("dong_line_build") pub unsafe fn build(source:*const u8,ns:usize,starts:*usize,nc:usize,used:*usize)u64{unsafe{
 return l.build(slice_from_raw_parts(source,ns),slice_from_raw_parts(starts,nc),used);
}}
export("dong_line_locate") pub unsafe fn locate(starts:*const usize,n:usize,source_len:usize,offset:usize,result:*l.Position)u64{unsafe{
 return l.locate(slice_from_raw_parts(starts,n),source_len,offset,result);
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
typedef struct {uint64_t line,byte_column;} Position;
_Static_assert(sizeof(Position)==16&&__builtin_offsetof(Position,byte_column)==8,"Position layout");
extern uint64_t ABI dong_line_build(const uint8_t*,uint64_t,uint64_t*,uint64_t,uint64_t*);
extern uint64_t ABI dong_line_locate(const uint64_t*,uint64_t,uint64_t,uint64_t,Position*);
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
/* Bad build descriptors, one defect each: INVALID with every arena byte unchanged.
   Fake high addresses are only used where the span check must reject them. */
static unsigned invalid_build(void){
 static _Alignas(16) uint8_t arena[2048];static uint8_t saved[2048];const unsigned total=13;
 uint8_t*src=arena;uint64_t*st=(uint64_t*)(arena+256);uint64_t*u=(uint64_t*)(arena+1024);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(src,"a\nb\r\n\n",6);memcpy(saved,arena,sizeof(arena));uint64_t r=0;
  switch(i){
   case 0:r=dong_line_build(src,6,st,16,NULL);break;
   case 1:r=dong_line_build(src,6,st,16,(uint64_t*)(arena+1028));break;
   case 2:r=dong_line_build(src,6,st,16,(uint64_t*)arena);break;
   case 3:r=dong_line_build(src,64,(uint64_t*)(arena+32),16,u);break;
   case 4:r=dong_line_build(src,6,st,16,st+3);break;
   case 5:r=dong_line_build(src,6,(uint64_t*)(arena+260),16,u);break;
   case 6:r=dong_line_build(NULL,6,st,16,u);break;
   case 7:r=dong_line_build(src,6,NULL,16,u);break;
   case 8:r=dong_line_build(src,6,st,UINT64_MAX/8+1,u);break;
   case 9:r=dong_line_build(src,UINT64_MAX,st,16,u);break;
   case 10:r=dong_line_build((const uint8_t*)(uintptr_t)(UINT64_MAX-15),32,st,16,u);break;
   case 11:r=dong_line_build(src,6,(uint64_t*)(uintptr_t)(UINT64_MAX-15),4,u);break;
   default:r=dong_line_build(src,6,st,16,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
  }
  if(r!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"build preflight %u status %u\n",i,(unsigned)r);exit(93);}
 }
 return total;
}
static unsigned invalid_locate(void){
 static _Alignas(16) uint8_t arena[1024];static uint8_t saved[1024];const unsigned total=8;
 uint64_t*st=(uint64_t*)arena;Position*res=(Position*)(arena+512);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));st[0]=0;st[1]=2;st[2]=4;memcpy(saved,arena,sizeof(arena));uint64_t r=0;
  switch(i){
   case 0:r=dong_line_locate(st,3,6,3,NULL);break;
   case 1:r=dong_line_locate(st,3,6,3,(Position*)(arena+516));break;
   case 2:r=dong_line_locate(st,3,6,3,(Position*)(arena+8));break;
   case 3:r=dong_line_locate((const uint64_t*)(arena+4),3,6,3,res);break;
   case 4:r=dong_line_locate(NULL,3,6,3,res);break;
   case 5:r=dong_line_locate(st,UINT64_MAX/8+1,6,3,res);break;
   case 6:r=dong_line_locate((const uint64_t*)(uintptr_t)(UINT64_MAX-15),4,6,3,res);break;
   default:r=dong_line_locate(st,3,6,3,(Position*)(uintptr_t)(UINT64_MAX-15));break;
  }
  if(r!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"locate preflight %u status %u\n",i,(unsigned)r);exit(93);}
 }
 return total;
}
static void build_case(uint64_t n,uint64_t cap,uint64_t ro){
 if(n>1000000||cap>1000000)exit(94);
 uint8_t*in=malloc(n+64),*copy=malloc(n+1);uint64_t*out=malloc((cap+4)*8);uint64_t meta[3];
 if(!in||!copy||!out)exit(95);
 memset(in,0xa5,n+64);read_exact(in+32,n);memcpy(copy,in+32,n);
 const uint8_t*s=n?in+32:NULL;uint8_t*page=NULL;uint64_t pages=0;
 if(ro&&n){pages=(n/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,n);ro_protect(page,pages);s=page;}
 memset(out,0xa5,(cap+4)*8);memset(meta,0xa5,sizeof(meta));uint64_t*used=meta+1;
 uint64_t r=dong_line_build(s,n,cap?out+2:NULL,cap,used);
 uint64_t valid=(!n||!memcmp(copy,s,n))&&filled(in,32)&&filled(in+32+n,32)&&(!n||!memcmp(copy,in+32,n))&&
   filled(out,16)&&filled(out+2+cap,16)&&filled(meta,8)&&filled(meta+2,8);
 if(r)valid=valid&&filled(out+2,cap*8)&&filled(used,8);
 else valid=valid&&*used<=cap&&filled(out+2+*used,(cap-*used)*8);
 uint64_t response[3]={r,valid,r?0:*used};write_exact(response,24);
 if(!r&&valid)write_exact(out+2,*used*8);
 if(page)ro_free(page,pages);
 free(in);free(copy);free(out);
}
static void locate_case(uint64_t n,uint64_t slen,uint64_t off,uint64_t ro){
 if(n>1000000)exit(94);
 uint64_t ib=n*8;uint8_t*in=malloc(ib+64),*copy=malloc(ib+1);uint64_t res[4];
 if(!in||!copy)exit(95);
 memset(in,0xa5,ib+64);read_exact(in+32,ib);memcpy(copy,in+32,ib);
 const uint64_t*t=n?(const uint64_t*)(in+32):NULL;uint8_t*page=NULL;uint64_t pages=0;
 if(ro&&n){pages=(ib/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,ib);ro_protect(page,pages);t=(const uint64_t*)page;}
 memset(res,0xa5,sizeof(res));Position*p=(Position*)(res+1);
 uint64_t r=dong_line_locate(t,n,slen,off,p);
 uint64_t valid=(!ib||!memcmp(copy,t,ib))&&filled(in,32)&&filled(in+32+ib,32)&&(!ib||!memcmp(copy,in+32,ib))&&
   filled(res,8)&&filled(res+3,8);
 if(r)valid=valid&&filled(p,16);
 uint64_t response[4]={r,valid,r?0:p->line,r?0:p->byte_column};write_exact(response,32);
 if(page)ro_free(page,pages);
 free(in);free(copy);
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t pre[2],count;pre[0]=invalid_build();pre[1]=invalid_locate();read_exact(&count,8);write_exact(pre,16);
 while(count--){
  uint64_t h[5];read_exact(h,sizeof(h));
  if(h[0]==0)build_case(h[1],h[2],h[4]);
  else if(h[0]==1)locate_case(h[1],h[2],h[3],h[4]);
  else exit(96);
 }return 0;
}
'''


def split_starts(src):
    """Line starts from bytes.split: each LF-terminated piece contributes len+1."""
    starts=[0]
    for piece in src.split(b'\n')[:-1]:starts.append(starts[-1]+len(piece)+1)
    return starts


def direct_position(src,offset):
    """Second, scan-free model: count LFs before offset and the distance from the last one."""
    return src.count(b'\n',0,offset)+1,offset-(src.rfind(b'\n',0,offset)+1)+1


def build(src,cap=None,readonly=0,status=None):
    starts=split_starts(src);cap=len(starts)if cap is None else cap
    st=OK if cap>=len(starts)else CAPACITY
    if status is not None:assert st==status,(status,st,src,cap)
    return dict(kind=BUILD,source=bytes(src),cap=cap,readonly=readonly,status=st,starts=starts if st==OK else None)


def locate(starts,source_len,offset,readonly=0,status=None,expect=None):
    ok=(len(starts)>0 and starts[0]==0 and all(a<b for a,b in zip(starts,starts[1:]))
        and starts[-1]<=source_len and offset<=source_len)
    pos=None
    if ok:
        i=bisect.bisect_right(starts,offset)-1;col=offset-starts[i]+1
        if col>USIZE_MAX:ok=False
        else:pos=(i+1,col)
    st=OK if ok else INVALID
    if status is not None:assert st==status,(status,st,starts,source_len,offset)
    if expect is not None:assert pos==expect,(expect,pos,starts,source_len,offset)
    return dict(kind=LOCATE,starts=list(starts),source_len=source_len,offset=offset,readonly=readonly,status=st,pos=pos)


def locate_in(src,offset,readonly=0):
    c=locate(split_starts(src),len(src),offset,readonly)
    assert c['pos']==direct_position(src,offset),(src,offset,c['pos'])
    return c


class LineIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native line index requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C17'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/line_index_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([WORKS/'claude-works/src',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/line_index_export.dg',roots=roots,mode=mode)
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
            if c['kind']==BUILD:
                payload.extend(struct.pack('<5Q',BUILD,len(c['source']),c['cap'],0,c['readonly']));payload.extend(c['source'])
            else:
                payload.extend(struct.pack('<5Q',LOCATE,len(c['starts']),c['source_len'],c['offset'],c['readonly']))
                payload.extend(struct.pack('<%dQ'%len(c['starts']),*c['starts']))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<2Q',run.stdout,0),PREFLIGHTS)
        offset=16
        for index,c in enumerate(cases):
            if c['kind']==BUILD:
                status,guard,used=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
                # Each call's storage verdict is checked before its result is looked at.
                self.assertEqual(guard,1,(label,index,'guard/atomicity'))
                self.assertEqual(status,c['status'],(label,index,'status'))
                if not status:
                    got=list(struct.unpack_from('<%dQ'%used,run.stdout,offset));offset+=8*used
                    self.assertEqual(used,len(c['starts']),(label,index,'used'))
                    self.assertEqual(got,c['starts'],(label,index,'starts'))
            else:
                status,guard,line,column=struct.unpack_from('<4Q',run.stdout,offset);offset+=32
                self.assertEqual(guard,1,(label,index,'guard/atomicity'))
                self.assertEqual(status,c['status'],(label,index,'status'))
                if not status:self.assertEqual((line,column),c['pos'],(label,index,'position'))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def test_random_sources_against_split_and_bisect(self):
        rng=random.Random(0xC17C17);cases=[]
        tokens=[b'a',b'Z',b' ',b'\n',b'\n\n',b'\r\n',b'\r',b'\x00',b'\xa5',
                'é'.encode(),'あ'.encode(),'😀'.encode()]
        for i in range(300):
            src=b''.join(rng.choice(tokens)for _ in range(rng.randint(0,30)))
            n=len(split_starts(src));ro=int(i%40==0)
            cases.append(build(src,readonly=ro))
            if i%3==0:cases.append(build(src,cap=n+rng.randint(1,4)))
            if i%4==0:cases.append(build(src,cap=n-1,status=CAPACITY));cases.append(build(src,cap=0,status=CAPACITY))
            offsets={0,len(src),rng.randint(0,len(src)),rng.randint(0,len(src))}|set(split_starts(src))
            for off in sorted(offsets):cases.append(locate_in(src,off,readonly=ro))
            starts=split_starts(src)
            cases.append(locate(starts,len(src),len(src)+1+rng.randint(0,3),status=INVALID))
            extra=len(src)+rng.randint(1,5)                                  # index need not reach source_len
            cases.append(locate(starts,extra,rng.randint(0,extra),status=OK))
            if len(starts)>1:                                                # corrupted indexes
                bad=list(starts);j=rng.randrange(1,len(bad));bad[j]=bad[j-1]
                cases.append(locate(bad,len(src),rng.randint(0,len(src)),status=INVALID))
                cases.append(locate(starts[::-1],len(src),0,status=INVALID))
            cases.append(locate([1]+starts[1:],len(src),len(src),status=INVALID))
        big=bytes(rng.choice(b'ab\r\n\x00\xa5')for _ in range(100000));bs=split_starts(big)
        cases.append(build(big,readonly=1));cases.append(build(big,cap=len(bs)-1,status=CAPACITY))
        for off in (0,1,len(big)//2,bs[len(bs)//2],len(big)-1,len(big)):cases.append(locate_in(big,off,readonly=1))
        self.run_both(cases,'random')
        self.assertGreater(sum(c['status']==OK for c in cases),1000);self.assertGreater(sum(c['status']==INVALID for c in cases),500)
        self.assertGreater(sum(c['status']==CAPACITY for c in cases),100)
        self.records.append(dict(test='random-split-bisect',cases=len(cases),sources=300,seed='0xC17C17',modes=2,passed=True))

    def test_boundaries_crlf_utf8_eof_and_bad_indexes(self):
        utf='aé\nあ😀\r\n'.encode()
        cases=[build(b''),build(b'',cap=0,status=CAPACITY),build(b'',cap=3),build(b'\n'),build(b'\n',cap=1,status=CAPACITY),
               build(b'\n\n\n'),build(b'abc'),build(b'abc\n'),build(b'a\r\nb\r\n'),build(b'\r\r\r'),build(b'\x00\n\x00'),
               build(utf),build(b'\n'*64,readonly=1),build(b'x'*5000,readonly=1),build(b'\xa5\n\xa5')]
        assert split_starts(b'')==[0] and split_starts(b'a\n')==[0,2] and split_starts(b'a\r\nb\r\n')==[0,3,6]
        assert split_starts(utf)==[0,4,13] and split_starts(b'\n\n')==[0,1,2]
        cases+=[locate([0],0,0,expect=(1,1)),locate([0],0,1,status=INVALID),
                locate([0,2],2,2,expect=(2,1)),locate([0,2],2,1,expect=(1,2)),locate([0,2],2,0,expect=(1,1)),
                locate([0,1,2,3],3,3,expect=(4,1)),locate([0,1,2,3],3,2,expect=(3,1)),
                locate([0,3,6],6,2,expect=(1,3)),locate([0,3,6],6,3,expect=(2,1)),locate([0,3],4,4,expect=(2,2)),
                locate([0,4,13],13,8,expect=(2,5)),locate([0,4,13],13,12,expect=(2,9)),locate([0,4,13],13,13,expect=(3,1)),
                locate([0,10,20],30,15,expect=(2,6)),locate([0,10,20],30,30,expect=(3,11)),locate([0,10,20],30,19,expect=(2,10)),
                locate([0,10,20],30,20,readonly=1,expect=(3,1)),locate(list(range(0,4096,7)),5000,4095,readonly=1,expect=(586,1)),
                locate([0],USIZE_MAX-1,USIZE_MAX-1,expect=(1,USIZE_MAX)),
                locate([0],USIZE_MAX,USIZE_MAX,status=INVALID),                 # byte column +1 overflows
                locate([0,USIZE_MAX-1],USIZE_MAX,USIZE_MAX,expect=(2,2)),locate([0,USIZE_MAX],USIZE_MAX,USIZE_MAX,expect=(2,1)),
                locate([0,USIZE_MAX],USIZE_MAX,USIZE_MAX-1,expect=(1,USIZE_MAX)),locate([0,1],USIZE_MAX,USIZE_MAX,expect=(2,USIZE_MAX))]
        cases+=[locate([],0,0,status=INVALID),locate([],5,0,status=INVALID),locate([1],5,1,status=INVALID),
                locate([0,0],5,0,status=INVALID),locate([0,2,2],5,3,status=INVALID),locate([0,3,2],5,1,status=INVALID),
                locate([0,5],4,0,status=INVALID),locate([0,2],4,5,status=INVALID),locate([0,USIZE_MAX],USIZE_MAX-1,0,status=INVALID),
                locate([0,2],USIZE_MAX,USIZE_MAX,status=OK),locate([USIZE_MAX],USIZE_MAX,0,status=INVALID),
                locate([0,1,2,3,3],10,9,readonly=1,status=INVALID)]
        self.run_both(cases,'bounds')
        self.records.append(dict(test='boundaries-crlf-utf8-eof',cases=len(cases),invalid_preflights_per_native=sum(PREFLIGHTS),modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/line_index.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/line_index_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-missing-tail-line','fn breaks(source:[]const u8,i:usize)bool{return source[i]==10;}',
             'fn breaks(source:[]const u8,i:usize)bool{return source[i]==10&&i+1<source.len;}',
             [build(b'ab\n')],"'used'"),
            ('bad-equal-offset-prev-line','if starts[mid]<=offset{lo=mid;}','if starts[mid]<offset{lo=mid;}',
             [locate([0,3],3,3,expect=(2,1))],"'position'"),
            ('bad-overflow-writes-result','if delta==MAX{return INVALID;}',
             'if delta==MAX{*result=Position{line:0,byte_column:0};return INVALID;}',
             [locate([0],USIZE_MAX,USIZE_MAX,status=INVALID)],"'guard/atomicity'"),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
