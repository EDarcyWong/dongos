"""Actual Dong scope-exit cleanup planning, against an independent Python ancestor-chain model."""
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

SOURCE=ROOT/'lang/bootstrap/cleanup_plan.dg'
OK,INVALID,CAPACITY=0,1,2
MAX=2**64-1
WRAPPER='''module probe.cleanup_export;
import bootstrap.cleanup_plan as c;
export("dong_cleanup_plan") pub unsafe fn plan(scopes:*const c.Scope,ns:usize,ids:*const usize,ni:usize,
 from_scope:usize,target_scope:usize,out:*usize,no:usize,used:*usize)u64{unsafe{
 return c.plan(slice_from_raw_parts(scopes,ns),slice_from_raw_parts(ids,ni),from_scope,target_scope,slice_from_raw_parts(out,no),used);
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
typedef struct {uint64_t parent,first,count;} Scope;
_Static_assert(sizeof(Scope)==24&&__builtin_offsetof(Scope,count)==16,"Scope layout");
extern uint64_t ABI dong_cleanup_plan(const Scope*,uint64_t,const uint64_t*,uint64_t,uint64_t,uint64_t,uint64_t*,uint64_t,uint64_t*);
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
/* Bad descriptors: INVALID with every arena byte unchanged. */
static unsigned invalid(void){
 static uint8_t arena[2048],saved[2048];const unsigned total=16;
 Scope*s=(Scope*)arena;uint64_t*ids=(uint64_t*)(arena+256);uint64_t*o=(uint64_t*)(arena+512);uint64_t*u=(uint64_t*)(arena+1536);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));s[0].parent=UINT64_MAX;s[0].first=0;s[0].count=1;s[1].parent=0;s[1].first=1;s[1].count=1;ids[0]=10;ids[1]=11;
  memcpy(saved,arena,sizeof(arena));uint64_t r=0;
  switch(i){
   case 0:r=dong_cleanup_plan(s,2,ids,2,1,UINT64_MAX,o,8,NULL);break;
   case 1:r=dong_cleanup_plan(s,2,ids,2,1,UINT64_MAX,o,8,(uint64_t*)(arena+1540));break;
   case 2:r=dong_cleanup_plan(s,2,ids,2,1,UINT64_MAX,o,8,(uint64_t*)s);break;
   case 3:r=dong_cleanup_plan(s,2,ids,2,1,UINT64_MAX,ids,8,u);break;
   case 4:r=dong_cleanup_plan(s,2,ids,2,1,UINT64_MAX,(uint64_t*)s+2,8,u);break;
   case 5:r=dong_cleanup_plan(s,2,ids,2,1,UINT64_MAX,o,8,o+7);break;
   case 6:r=dong_cleanup_plan((Scope*)(arena+4),2,ids,2,1,UINT64_MAX,o,8,u);break;
   case 7:r=dong_cleanup_plan(s,2,(uint64_t*)(arena+260),2,1,UINT64_MAX,o,8,u);break;
   case 8:r=dong_cleanup_plan(s,2,ids,2,1,UINT64_MAX,(uint64_t*)(arena+516),8,u);break;
   case 9:r=dong_cleanup_plan(NULL,2,ids,2,1,UINT64_MAX,o,8,u);break;
   case 10:r=dong_cleanup_plan(s,2,NULL,2,1,UINT64_MAX,o,8,u);break;
   case 11:r=dong_cleanup_plan(s,UINT64_MAX/24+1,ids,2,1,UINT64_MAX,o,8,u);break;
   case 12:r=dong_cleanup_plan((Scope*)(uintptr_t)(UINT64_MAX-23),2,ids,2,1,UINT64_MAX,o,8,u);break;
   case 13:r=dong_cleanup_plan(s,0,ids,2,0,UINT64_MAX,o,8,u);break;
   case 14:r=dong_cleanup_plan(s,2,ids,2,2,UINT64_MAX,o,8,u);break;
   default:r=dong_cleanup_plan(s,2,ids,2,1,UINT64_MAX,o,UINT64_MAX/8+1,u);break;
  }
  if(r!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)r);exit(93);}
 }
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[6];read_exact(h,sizeof(h));uint64_t ns=h[0],ni=h[1],from=h[2],target=h[3],no=h[4],ro=h[5];
  if(ns>100000||ni>300000||no>300000)exit(94);
  uint64_t sb=ns*24,ib=ni*8;uint8_t*in=malloc(sb+ib+96),*copy=malloc(sb+ib+1);uint64_t*out=malloc((no+8)*8);uint64_t meta[3];
  if(!in||!copy||!out)exit(95);
  memset(in,0xa5,sb+ib+96);read_exact(in+32,sb);read_exact(in+64+sb,ib);memcpy(copy,in+32,sb);memcpy(copy+sb,in+64+sb,ib);
  const Scope*s=ns?(const Scope*)(in+32):NULL;const uint64_t*ids=ni?(const uint64_t*)(in+64+sb):NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro){pages=((sb+ib)/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,sb+ib);ro_protect(page,pages);
   s=ns?(const Scope*)page:NULL;ids=ni?(const uint64_t*)(page+sb):NULL;}
  memset(out,0xa5,(no+8)*8);memset(meta,0xa5,sizeof(meta));uint64_t*used=meta+1;
  uint64_t r=dong_cleanup_plan(s,ns,ids,ni,from,target,no?out+4:NULL,no,used);
  uint64_t valid=(!sb||!memcmp(copy,s,sb))&&(!ib||!memcmp(copy+sb,ids,ib))&&(ro||(filled(in,32)&&filled(in+32+sb,32)&&filled(in+64+sb+ib,32)))&&
    filled(out,32)&&filled(out+4+no,32)&&filled(meta,8)&&filled(meta+2,8);
  if(r)valid=valid&&filled(out+4,no*8)&&filled(used,8);
  else valid=valid&&*used<=no&&filled(out+4+*used,(no-*used)*8);
  uint64_t response[3]={r,valid,r?0:*used};write_exact(response,24);write_exact(out+4,r?0:*used*8);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(out);
 }return 0;
}
'''


def reference(scopes,ids,frm,target,no):
    """Independent model: validate the forest, then walk ancestors. Returns (status, sequence)."""
    n=len(scopes)
    if n==0 or frm>=n:return INVALID,None
    for i,(parent,first,count) in enumerate(scopes):
        if first+count>len(ids):return INVALID,None
        if (i==0)!=(parent==MAX):return INVALID,None
        if i and parent>=n:return INVALID,None
    for i in range(n):
        seen=set();at=i
        while at!=0:
            if at in seen:return INVALID,None
            seen.add(at);at=scopes[at][0]
    chain=[frm]
    while chain[-1]!=0:chain.append(scopes[chain[-1]][0])
    if target==MAX:layers=chain
    elif target in chain:layers=chain[:chain.index(target)]
    else:return INVALID,None
    sequence=[]
    for scope in layers:
        _,first,count=scopes[scope];sequence+=list(reversed(ids[first:first+count]))
    if no<len(sequence):return CAPACITY,None
    return OK,sequence


def case(scopes,ids,frm,target,no=None,readonly=0,status=None):
    if no is None:
        st,seq=reference(scopes,ids,frm,target,MAX);no=len(seq)if seq is not None else 4
    expected=reference(scopes,ids,frm,target,no)
    if status is not None:assert expected[0]==status,(status,expected,scopes,frm,target)
    return dict(scopes=scopes,ids=ids,frm=frm,target=target,no=no,readonly=readonly,expected=expected)


def random_tree(rng,n):
    scopes,ids=[],[]
    for i in range(n):
        parent=MAX if i==0 else rng.randrange(i) if rng.random()<0.7 else rng.randrange(n)
        k=rng.choice([0,0,1,2,3,5]);first=len(ids)
        ids+=[rng.choice([rng.randrange(8),rng.randrange(MAX+1)])for _ in range(k)]   # repeated opaque ids allowed
        scopes.append((parent,first,k))
    return scopes,ids


def ancestors(scopes,frm):
    chain=[frm]
    while chain[-1]!=0:chain.append(scopes[chain[-1]][0])
    return chain


class CleanupPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native cleanup planning requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/C12'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/cleanup_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/cleanup_export.dg',roots=roots,mode=mode)
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
            payload.extend(struct.pack('<6Q',len(c['scopes']),len(c['ids']),c['frm'],c['target'],c['no'],c['readonly']))
            for p,f,k in c['scopes']:payload.extend(struct.pack('<3Q',p,f,k))
            payload.extend(struct.pack('<%dQ'%len(c['ids']),*c['ids']))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,16)
        offset=8
        for index,c in enumerate(cases):
            status,guard,used=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['expected'][0],(label,index,'status'))
            if not status:
                got=list(struct.unpack_from('<%dQ'%used,run.stdout,offset));offset+=8*used
                self.assertEqual(got,c['expected'][1],(label,index,'sequence',c['frm'],c['target']))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def test_random_scope_trees_against_ancestor_model(self):
        rng=random.Random(0xC12C);cases=[];statuses={}
        for i in range(400):
            scopes,ids=random_tree(rng,rng.randint(1,30));frm=rng.randrange(len(scopes))
            if reference(scopes,ids,frm,MAX,MAX)[0]==OK:
                chain=ancestors(scopes,frm);target=rng.choice(chain+[MAX,MAX])
            else:target=MAX
            c=case(scopes,ids,frm,target,readonly=int(i%40==0));cases.append(c)
            statuses[c['expected'][0]]=statuses.get(c['expected'][0],0)+1
        deep=[(MAX,0,1)]+[(i,i+1,1)for i in range(3000)];cases.append(case(deep,list(range(3001)),3000,MAX,readonly=1))
        self.run_both(cases,'random')
        self.assertGreater(statuses.get(OK,0),150,statuses);self.assertGreater(statuses.get(INVALID,0),50,statuses)
        self.records.append(dict(test='random-trees',cases=len(cases),seed='0xC12C',statuses=statuses,modes=2,passed=True))

    def test_paths_targets_cycles_and_capacity(self):
        # fn body 0 {defer a,b}  loop 1 {defer c}  block 2 {defer d,e}  inner 3 {}   sibling 4 under 0 {defer f}
        scopes=[(MAX,0,2),(0,2,1),(1,3,2),(2,5,0),(0,5,1)];ids=[100,101,200,300,301,400]
        cases=[case(scopes,ids,3,MAX,status=OK),                  # return from inner: 301,300,200,101,100
               case(scopes,ids,3,1,status=OK),                    # break out of the loop body: 301,300
               case(scopes,ids,3,2,status=OK),                    # continue-like exit to block 2: nothing (inner empty)
               case(scopes,ids,2,1,status=OK),case(scopes,ids,3,3,status=OK),case(scopes,ids,0,MAX,status=OK),
               case(scopes,ids,0,0,status=OK),case(scopes,ids,4,0,status=OK),case(scopes,ids,4,MAX,status=OK),
               case([(MAX,0,3)],[7,7,7],0,MAX,status=OK),case([(MAX,0,0)],[],0,MAX,status=OK),case([(MAX,0,0)],[],0,MAX,no=0,status=OK)]
        self.assertEqual(reference(scopes,ids,3,MAX,9)[1],[301,300,200,101,100])
        self.assertEqual(reference(scopes,ids,3,1,9)[1],[301,300])
        # Invalid targets and shapes.
        cases+=[case(scopes,ids,3,4,status=INVALID),case(scopes,ids,1,2,status=INVALID),case(scopes,ids,3,5,status=INVALID),
                case(scopes,ids,3,MAX-1,status=INVALID),case(scopes,ids,5,MAX,status=INVALID),case([],[],0,MAX,status=INVALID),
                case([(0,0,0)],[],0,MAX,status=INVALID),case([(MAX,0,0),(MAX,0,0)],[],1,MAX,status=INVALID),
                case([(MAX,0,0),(2,0,0)],[],1,MAX,status=INVALID),case([(MAX,0,1)],[],0,MAX,status=INVALID),
                case([(MAX,1,1)],[5],0,MAX,status=INVALID),case([(MAX,0,0),(0,MAX,2)],[1,2],1,MAX,status=INVALID),
                case([(MAX,0,0),(1,0,0)],[],0,MAX,status=INVALID),                                  # unreachable self-loop
                case([(MAX,0,0),(0,0,0),(3,0,0),(2,0,0)],[],1,MAX,status=INVALID),                  # unreachable 2-cycle
                case([(MAX,0,0),(0,0,0),(3,0,0),(4,0,0),(2,0,0)],[],0,0,status=INVALID),            # unreachable 3-cycle
                case([(MAX,0,1),(0,1,1),(1,2,9)],[1,2,3],2,MAX,no=0,status=INVALID)]                # INVALID before CAPACITY
        for frm,target in ((3,MAX),(3,1),(4,MAX)):
            need=len(reference(scopes,ids,frm,target,MAX)[1])
            cases+=[case(scopes,ids,frm,target,no=need-1,status=CAPACITY),case(scopes,ids,frm,target,no=0,status=CAPACITY),
                    case(scopes,ids,frm,target,no=need+6,status=OK)]
        self.run_both(cases,'paths')
        self.records.append(dict(test='paths-targets-cycles-capacity',cases=len(cases),invalid_preflights_per_native=16,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/cleanup_plan.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/cleanup_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        scopes=[(MAX,0,2),(0,2,1),(1,3,2),(2,5,0),(0,5,1)];ids=[100,101,200,300,301,400]
        controls=[
            # Outer scopes emitted before inner ones: the output is filled from the end.
            ('bad-outer-first','var k:usize=0;at=from_scope;\n while at!=target_scope{\n  let s=scopes[at];var j=s.count;\n  while j!=0{j-=1;out[k]=cleanup_ids[s.first+j];k+=1;}',
             'var k:usize=need;at=from_scope;\n while at!=target_scope{\n  let s=scopes[at];var j=s.count;\n  k-=s.count;var p=k;while j!=0{j-=1;out[p]=cleanup_ids[s.first+j];p+=1;}',
             [case(scopes,ids,3,MAX)],'sequence'),
            # The target scope's own cleanups are included.
            ('bad-include-target','  at=s.parent;\n }\n *used=need;',
             '  at=s.parent;\n }\n if target_scope!=ROOT_PARENT{let t=scopes[target_scope];var q:usize=0;while q<t.count&&k<out.len{out[k]=cleanup_ids[t.first+q];k+=1;q+=1;}}\n *used=k;',
             [case(scopes,ids,3,1,no=8)],'sequence'),
            # Registration order kept instead of reversed within a scope.
            ('bad-not-reversed','while j!=0{j-=1;out[k]=cleanup_ids[s.first+j];k+=1;}','var q:usize=0;while q<s.count{out[k]=cleanup_ids[s.first+q];k+=1;q+=1;}',
             [case(scopes,ids,2,MAX)],'sequence'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
