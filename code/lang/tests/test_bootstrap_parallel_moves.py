"""Actual Dong parallel-move sequentialization, checked by symbolic execution in Python."""
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

SOURCE=ROOT/'lang/bootstrap/parallel_moves.dg'
OK,INVALID,CAPACITY,WORKSPACE=0,1,2,3
MAX=2**64-1
WRAPPER='''module probe.moves_export;
import bootstrap.parallel_moves as p;
export("dong_parallel_moves") pub unsafe fn schedule(moves:*const p.Move,nm:usize,slot_count:usize,
 out:*p.Move,no:usize,work:*u8,nw:usize,used:*usize)u64{unsafe{
 return p.schedule(slice_from_raw_parts(moves,nm),slot_count,slice_from_raw_parts(out,no),slice_from_raw_parts(work,nw),used);
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
typedef struct {uint64_t dst,src;} Move;
_Static_assert(sizeof(Move)==16&&__builtin_offsetof(Move,src)==8,"Move layout");
extern uint64_t ABI dong_parallel_moves(const Move*,uint64_t,uint64_t,Move*,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
/* Bad descriptors: INVALID with every arena byte (work included) unchanged. */
static unsigned invalid(void){
 static uint8_t arena[2048],saved[2048];const unsigned total=16;
 Move*m=(Move*)arena;Move*o=(Move*)(arena+256);uint8_t*w=arena+1024;uint64_t*u=(uint64_t*)(arena+1536);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));m[0].dst=0;m[0].src=1;m[1].dst=1;m[1].src=0;memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_parallel_moves(m,2,2,o,8,w,8,NULL);break;
   case 1:s=dong_parallel_moves(m,2,2,o,8,w,8,(uint64_t*)(arena+1540));break;
   case 2:s=dong_parallel_moves(m,2,2,o,8,w,8,(uint64_t*)m);break;
   case 3:s=dong_parallel_moves(m,2,2,m,8,w,8,u);break;
   case 4:s=dong_parallel_moves(m,2,2,o,8,(uint8_t*)m+8,8,u);break;
   case 5:s=dong_parallel_moves(m,2,2,o,8,(uint8_t*)o,8,u);break;
   case 6:s=dong_parallel_moves(m,2,2,o,8,w,8,(uint64_t*)o);break;
   case 7:s=dong_parallel_moves((Move*)(arena+8+4),2,2,o,8,w,8,u);break;
   case 8:s=dong_parallel_moves(m,2,2,(Move*)(arena+260),8,w,8,u);break;
   case 9:s=dong_parallel_moves(NULL,2,2,o,8,w,8,u);break;
   case 10:s=dong_parallel_moves(m,2,2,NULL,8,w,8,u);break;
   case 11:s=dong_parallel_moves(m,UINT64_MAX/8,2,o,8,w,8,u);break;
   case 12:s=dong_parallel_moves((Move*)(uintptr_t)(UINT64_MAX-15),2,2,o,8,w,8,u);break;
   case 13:s=dong_parallel_moves(m,2,2,o,8,(uint8_t*)(uintptr_t)(UINT64_MAX-3),8,u);break;
   case 14:s=dong_parallel_moves(m,2,0,o,8,w,8,u);break;
   default:s=dong_parallel_moves(m,2,UINT64_MAX,o,8,w,8,u);break;
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
  uint64_t h[5];read_exact(h,sizeof(h));uint64_t nm=h[0],slots=h[1],no=h[2],nw=h[3],ro=h[4];
  if(nm>100000||no>300000||nw>300000)exit(94);
  uint64_t mb=nm*16;uint8_t*in=malloc(mb+64),*copy=malloc(mb+1),*work=malloc(nw+64);Move*out=malloc((no+4)*16);uint64_t meta[3];
  if(!in||!copy||!work||!out)exit(95);
  memset(in,0xa5,mb+64);read_exact(in+32,mb);memcpy(copy,in+32,mb);
  const Move*m=nm?(const Move*)(in+32):NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro&&nm){pages=(mb/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,mb);ro_protect(page,pages);m=(const Move*)page;}
  memset(out,0xa5,(no+4)*16);memset(work,0xa5,nw+64);memset(meta,0xa5,sizeof(meta));uint64_t*used=meta+1;
  uint64_t s=dong_parallel_moves(m,nm,slots,no?out+2:NULL,no,nw?work+32:NULL,nw,used);
  uint64_t valid=(!mb||!memcmp(copy,m,mb))&&(ro||(filled(in,32)&&filled(in+32+mb,32)))&&filled(out,32)&&filled(out+2+no,32)&&
    filled(work,32)&&filled(work+32+nw,32)&&filled(meta,8)&&filled(meta+2,8);
  if(s)valid=valid&&filled(out+2,no*16)&&filled(used,8);
  else valid=valid&&*used<=no&&*used<=2*nm&&filled(out+2+*used,(no-*used)*16);
  uint64_t response[3]={s,valid,s?0:*used};write_exact(response,24);write_exact(out+2,s?0:*used*16);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(work);free(out);
 }return 0;
}
'''


def expected_status(moves,slots,no,nw):
    if slots==0 or slots==MAX:return INVALID
    if any(d>=slots or s>=slots for d,s in moves):return INVALID
    if len({d for d,_ in moves})!=len(moves):return INVALID
    if no<2*len(moves):return CAPACITY
    if nw<len(moves):return WORKSPACE
    return OK


def check_sequence(test,moves,slots,sequence,label):
    """Run the emitted sequence on unique symbolic old values and compare with parallel semantics."""
    state={}
    def get(x):return state.get(x,('old',x)if x<slots else('undefined-temp',))
    for d,s in sequence:
        test.assertTrue(d<=slots and s<=slots,(label,'location id'))
        state[d]=get(s)
    want={d:('old',s)for d,s in moves}
    touched={x for m in moves for x in m}|{d for d,_ in sequence if d<slots}
    test.assertEqual({i:get(i)for i in touched},{i:want.get(i,('old',i))for i in touched},(label,'semantics'))
    test.assertLessEqual(len(sequence),2*len(moves),(label,'used bound'))


def case(moves,slots,no=None,nw=None,readonly=0,status=None):
    no=2*len(moves)if no is None else no;nw=len(moves)if nw is None else nw
    st=expected_status(moves,slots,no,nw)
    if status is not None:assert st==status,(status,st,moves,slots)
    return dict(moves=moves,slots=slots,no=no,nw=nw,readonly=readonly,status=st)


def permutation_moves(rng,slots,k):
    """Random parallel copy: unique destinations, arbitrary (possibly shared) sources."""
    dsts=rng.sample(range(slots),k)
    return [(d,rng.randrange(slots))for d in dsts]


class ParallelMovesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native parallel moves require NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/C9'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/moves_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/moves_export.dg',roots=roots,mode=mode)
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
            payload.extend(struct.pack('<5Q',len(c['moves']),c['slots'],c['no'],c['nw'],c['readonly']))
            for d,s in c['moves']:payload.extend(struct.pack('<2Q',d,s))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,16)
        offset=8;sequences=[]
        for index,c in enumerate(cases):
            status,guard,used=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status'))
            sequence=None
            if not status:
                flat=struct.unpack_from('<%dQ'%(2*used),run.stdout,offset);offset+=16*used
                sequence=[(flat[2*i],flat[2*i+1])for i in range(used)]
                check_sequence(self,c['moves'],c['slots'],sequence,(label,index,c['moves']))
            sequences.append(sequence)
        self.assertEqual(offset,len(run.stdout))
        return sequences

    def run_both(self,cases,label):
        results=[self.run_cases(exe,cases,label+'-'+mode)for mode,exe in self.executables.items()]
        self.assertEqual(results[0],results[1],(label,'debug/release determinism'))
        return results[0]

    def test_random_parallel_copies_symbolically(self):
        rng=random.Random(0xC9C9);cases=[]
        for i in range(500):
            slots=rng.randint(1,24);k=rng.randint(0,slots)
            cases.append(case(permutation_moves(rng,slots,k),slots,readonly=int(i%50==0)))
            if i%5==0:cases.append(case(cases[-1]['moves'],slots,no=2*k+7,nw=k+3))
        perm=list(range(300));rng.shuffle(perm)
        cases.append(case([(d,s)for d,s in zip(range(300),perm)],300,readonly=1))
        self.run_both(cases,'random')
        self.records.append(dict(test='random-symbolic',cases=len(cases),seed='0xC9C9',modes=2,deterministic_across_modes=True,passed=True))

    def test_shapes_invalid_capacity_and_workspace(self):
        shapes={
            'empty':([],1),'self':([(0,0)],1),'selfs':([(0,0),(1,1),(2,2)],3),'chain':([(1,0),(2,1),(3,2)],4),
            'fanout':([(1,0),(2,0),(3,0)],4),'swap':([(0,1),(1,0)],2),'three-cycle':([(0,1),(1,2),(2,0)],3),
            'two-cycles':([(0,1),(1,0),(2,3),(3,2),(4,5),(5,6),(6,4)],7),'cycle-with-tree':([(0,1),(1,0),(2,0),(3,1)],4),
            'reversed-chain':([(0,1),(1,2),(2,3)],4),'rotation':([(i,(i+1)%9)for i in range(9)],9),
            'self-plus-swap':([(2,2),(0,1),(1,0)],3),'big-slot-ids':([(MAX-3,MAX-2),(MAX-2,MAX-3)],MAX-1)}
        cases=[case(m,s,status=OK)for m,s in shapes.values()]
        # A swap needs exactly 3 moves through the temporary.
        seq=self.run_cases(self.executables['release'],[case([(0,1),(1,0)],2)],'swap-shape')[0]
        self.assertEqual(seq,[(2,0),(0,1),(1,2)])
        for moves,slots in [([(0,2)],2),([(2,0)],2),([(0,0),(0,1)],2),([(1,0),(2,0),(1,2)],3),([(0,1)],0),([(0,1)],MAX),
                            ([(0,MAX)],MAX-1),([(0,0),(0,0)],1)]:
            cases.append(case(moves,slots,status=INVALID))
        cases.append(case([(0,1),(0,2)],3,no=0,nw=0,status=INVALID))           # INVALID before CAPACITY
        for moves,slots in [([(0,1),(1,0)],2),([(i,(i+1)%9)for i in range(9)],9),([(1,0)],2)]:
            n=len(moves)
            cases+=[case(moves,slots,no=2*n-1,status=CAPACITY),case(moves,slots,nw=n-1,status=WORKSPACE),
                    case(moves,slots,no=2*n-1,nw=0,status=CAPACITY),case(moves,slots,no=0,nw=0,status=CAPACITY)]
        cases.append(case([],5,no=0,nw=0,status=OK))
        self.run_both(cases,'shapes')
        self.records.append(dict(test='shapes-invalid-capacity',cases=len(cases),shapes=sorted(shapes),invalid_preflights_per_native=16,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/parallel_moves.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/moves_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            # Plain sequential assignment in input order: breaks a swap.
            ('bad-sequential','while i<n{if work[i]!=DONE&&!needed(moves,work,moves[i].dst){pick=i;break;}i+=1;}',
             'while i<n{if work[i]!=DONE{pick=i;break;}i+=1;}',[case([(0,1),(1,0)],2)],'semantics'),
            # Breaks the cycle but the redirected reader still copies from its overwritten original source.
            ('bad-no-redirect','var src=moves[pick].src;if work[pick]==(PENDING|TEMP){src=temp;}','var src=moves[pick].src;',
             [case([(0,1),(1,2),(2,0)],3)],'semantics'),
            ('bad-early-out','if work.len<n{return WORKSPACE;}','if out.len!=0{out[0]=Move{dst:0,src:0};}if work.len<n{return WORKSPACE;}',
             [case([(0,1),(1,0)],2,nw=1,status=WORKSPACE)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
