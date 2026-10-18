"""Actual Dong register/spill-slot assignment, against an independent occupancy-history model."""
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

SOURCE=WORKS/'claude-works/src/bootstrap/register_slots.dg'
OK,INVALID,CAPACITY=0,1,2
MAX=2**64-1
PREFLIGHTS=15
WRAPPER='''module probe.register_slots_export;
import bootstrap.register_slots as s;
export("dong_register_slots") pub unsafe fn assign(input:*const s.Interval,n:usize,register_count:usize,out:*s.Location,no:usize,result:*s.Result)u64{unsafe{
 return s.assign(slice_from_raw_parts(input,n),register_count,slice_from_raw_parts(out,no),result);
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
typedef struct {uint64_t start,end;} Interval;
typedef struct {uint64_t kind,index;} Location;
typedef struct {uint64_t used,spill_slots;} Result;
_Static_assert(sizeof(Interval)==16&&sizeof(Location)==16&&sizeof(Result)==16&&__builtin_offsetof(Interval,end)==8&&
  __builtin_offsetof(Location,index)==8&&__builtin_offsetof(Result,spill_slots)==8,"layout");
extern uint64_t ABI dong_register_slots(const Interval*,uint64_t,uint64_t,Location*,uint64_t,Result*);
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
/* Bad descriptors with valid data and register_count=2: INVALID, every arena byte unchanged.
   Each case is aligned and alias-free except for the one defect it tests. */
static unsigned invalid(void){
 static uint8_t arena[2048],saved[2048];const unsigned total=15;
 Interval*in=(Interval*)arena;Location*o=(Location*)(arena+256);Result*r=(Result*)(arena+1024);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));in[0].start=0;in[0].end=3;in[1].start=1;in[1].end=2;memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_register_slots(in,2,2,o,8,NULL);break;
   case 1:s=dong_register_slots(in,2,2,o,8,(Result*)(arena+1028));break;
   case 2:s=dong_register_slots(in,2,2,o,8,(Result*)(arena+16));break;
   case 3:s=dong_register_slots(in,2,2,(Location*)(arena+16),8,r);break;
   case 4:s=dong_register_slots(in,2,2,o,8,(Result*)(o+3));break;
   case 5:s=dong_register_slots(in,2,2,o,8,(Result*)((uint8_t*)(o+7)+8));break;
   case 6:s=dong_register_slots((const Interval*)(arena+4),2,2,o,8,r);break;
   case 7:s=dong_register_slots(in,2,2,(Location*)(arena+260),8,r);break;
   case 8:s=dong_register_slots(NULL,2,2,o,8,r);break;
   case 9:s=dong_register_slots(in,2,2,NULL,8,r);break;
   case 10:s=dong_register_slots(in,UINT64_MAX/16+1,2,o,8,r);break;
   case 11:s=dong_register_slots(in,2,2,o,UINT64_MAX/16+1,r);break;
   case 12:s=dong_register_slots((const Interval*)(uintptr_t)(UINT64_MAX-15),2,2,o,8,r);break;
   case 13:s=dong_register_slots(in,2,2,(Location*)(uintptr_t)(UINT64_MAX-15),2,r);break;
   default:s=dong_register_slots(in,2,2,o,8,(Result*)(uintptr_t)(UINT64_MAX-7));break;
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
  uint64_t h[4];read_exact(h,sizeof(h));uint64_t n=h[0],no=h[1],rc=h[2],ro=h[3];
  if(n>200000||no>400000)exit(94);
  uint64_t nb=n*16;uint8_t*in=malloc(nb+64),*copy=malloc(nb+1);Location*out=malloc((no+4)*16);uint64_t meta[6];
  if(!in||!copy||!out)exit(95);
  memset(in,0xa5,nb+64);read_exact(in+32,nb);memcpy(copy,in+32,nb);
  const Interval*src=n?(const Interval*)(in+32):NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro&&n){pages=(nb/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,nb);ro_protect(page,pages);src=(const Interval*)page;}
  memset(out,0xa5,(no+4)*16);memset(meta,0xa5,sizeof(meta));Result*r=(Result*)(meta+2);
  uint64_t s=dong_register_slots(src,n,rc,no?out+2:NULL,no,r);
  uint64_t valid=(!nb||!memcmp(copy,src,nb))&&(ro||(filled(in,32)&&filled(in+32+nb,32)))&&filled(out,32)&&filled(out+2+no,32)&&
    filled(meta,16)&&filled(meta+4,16);
  if(s)valid=valid&&filled(out+2,no*16)&&filled(r,16);
  else valid=valid&&r->used<=no&&filled(out+2+r->used,(no-r->used)*16);
  uint64_t emit=(!s&&r->used<=no)?r->used:0;
  uint64_t response[5]={s,valid,s?0:r->used,s?0:r->spill_slots,emit};write_exact(response,40);write_exact(out+2,emit*16);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(out);
 }return 0;
}
'''


def model(intervals,rc,no):
    """Independent reference: each register keeps its full occupancy history; a register is free for
    [s,e] only if every interval it ever held ended strictly before s. Returns (status, locations, spills)."""
    if not 1<=rc<=16:return INVALID,None,None
    for i,(s,e) in enumerate(intervals):
        if s>e or (i and intervals[i-1][0]>s):return INVALID,None,None
    if no<len(intervals):return CAPACITY,None,None
    history=[[]for _ in range(rc)];spills=0;locations=[]
    for s,e in intervals:
        free=[r for r in range(rc)if all(old_end<s for _,old_end in history[r])]
        if free:history[min(free)].append((s,e));locations.append((0,min(free)))
        else:locations.append((1,spills));spills+=1
    return OK,locations,spills


R=lambda i:(0,i)
S=lambda i:(1,i)


def case(intervals,rc,no=None,readonly=0,status=None,locations=None,spills=None):
    no=len(intervals)if no is None else no
    st,locs,sp=model(intervals,rc,no)
    if status is not None:assert st==status,(status,st,intervals,rc,no)
    # Hand-derived expectations pin the model itself.
    if locations is not None:assert (locs,sp)==(locations,spills),(locs,sp,locations,spills,intervals)
    return dict(intervals=intervals,rc=rc,no=no,readonly=readonly,status=st,locations=locs,spills=sp)


def generate(rng):
    n=rng.randint(0,24);rc=rng.choice([1,1,2,2,3,3,4,5,8,16])
    lo=MAX-40 if rng.random()<0.15 else 0
    intervals=[]
    for s in sorted(lo+rng.randint(0,30)for _ in range(n)):       # dense starts: many equal starts and touching ends
        x=rng.random()
        e=MAX if x<0.1 else s if x<0.3 else min(MAX,s+rng.randint(0,12))
        intervals.append((s,e))
    return intervals,rc


class RegisterSlotsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native register slots require NASM/GCC')
        cls.work=WORKS/'claude-works/build/C15'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/register_slots_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([WORKS/'claude-works/src',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/register_slots_export.dg',roots=roots,mode=mode)
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
            records=cls.records,optimal_allocation=False,integrated=False,OS_VM_built=False),indent=2)+'\n')

    def properties(self,intervals,rc,locations,spills,label):
        """Facts independent of the model's selection loop."""
        self.assertEqual([i for k,i in locations if k==1],list(range(spills)),(label,'spill numbering'))
        held=[[]for _ in range(rc)];top=[None]*rc                      # top[r]: max end held so far by register r
        for (s,e),(kind,index) in zip(intervals,locations):
            self.assertIn(kind,(0,1),(label,'kind'))
            busy=[top[r]is not None and top[r]>=s for r in range(rc)]
            if kind==0:
                self.assertLess(index,rc,(label,'register range'))
                self.assertFalse(busy[index],(label,'register still live'))
                self.assertTrue(all(busy[:index]),(label,'not lowest free register'))
                held[index].append((s,e));top[index]=e if top[index]is None else max(top[index],e)
            else:self.assertTrue(all(busy),(label,'spilled with a free register'))
        # Same register: strictly disjoint closed intervals. h is sorted by start, so consecutive
        # a.end<b.start makes ends increase too and implies pairwise disjointness.
        for h in held:
            for a,b in zip(h,h[1:]):self.assertLess(a[1],b[0],(label,'register overlap',a,b))

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:
            payload.extend(struct.pack('<4Q',len(c['intervals']),c['no'],c['rc'],c['readonly']))
            for s,e in c['intervals']:payload.extend(struct.pack('<2Q',s,e))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,PREFLIGHTS)
        offset=8
        for index,c in enumerate(cases):
            status,guard,used,spills,emit=struct.unpack_from('<5Q',run.stdout,offset);offset+=40
            flat=struct.unpack_from('<%dQ'%(2*emit),run.stdout,offset);offset+=16*emit
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['status'],(label,index,'status'))
            if not status:
                locations=[(flat[2*i],flat[2*i+1])for i in range(emit)]
                self.assertEqual(locations,c['locations'],(label,index,'locations',c['rc'],c['intervals']))
                self.assertEqual((used,spills),(len(c['intervals']),c['spills']),(label,index,'used/spill_slots'))
                self.properties(c['intervals'],c['rc'],locations,spills,(label,index))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def test_seeded_small_cases_against_history_model(self):
        cases=[]
        for seed in range(128):
            rng=random.Random(0xC1500+seed)
            for k in range(3):
                intervals,rc=generate(rng)
                cases+=[case(intervals,rc,readonly=int(k==0 and seed%16==0)),case(intervals,rc,no=len(intervals)+3)]
            intervals,rc=generate(rng)                                  # one mutated (usually INVALID) case per seed
            if intervals:
                i=rng.randrange(len(intervals));s,e=intervals[i]
                intervals[i]=((s,s-1)if s else(1,0))if rng.random()<0.5 else(max(0,s-31),e)   # start>end, or a start going back
            cases+=[case(intervals,rc),case(intervals,rc,no=0)]
        self.assertGreater(sum(c['status']==INVALID for c in cases),50)
        self.assertGreater(sum(c['status']==OK and c['spills']>0 for c in cases),100)
        rng=random.Random(0xC15B)
        big=[];s=0
        for _ in range(3000):
            s+=rng.choice([0,0,1,2]);big.append((s,MAX if rng.random()<0.01 else s+rng.randint(0,40)))
        cases.append(case(big,16,readonly=1));cases.append(case(big,3))
        self.run_both(cases,'seeded')
        self.records.append(dict(test='seeded-small-cases',cases=len(cases),seeds='0xC1500..0xC157F,0xC15B',modes=2,passed=True))

    def test_equal_starts_touching_max_empty_spill_invalid_capacity(self):
        cases=[case([],1,status=OK,locations=[],spills=0),case([],16,no=0,status=OK,locations=[],spills=0),
               case([],1,no=5,status=OK,locations=[],spills=0),
               # Equal starts.
               case([(3,3)]*5,2,locations=[R(0),R(1),S(0),S(1),S(2)],spills=3),
               case([(7,9)]*16,16,locations=[R(i)for i in range(16)],spills=0),
               case([(7,9)]*17,16,locations=[R(i)for i in range(16)]+[S(0)],spills=1),
               case([(3,9),(3,3)],2,locations=[R(0),R(1)],spills=0),
               # Touching endpoints: old end == new start is still live; old end < new start frees.
               case([(0,5),(5,9)],1,locations=[R(0),S(0)],spills=1),
               case([(0,5),(6,9)],1,locations=[R(0),R(0)],spills=0),
               case([(0,5),(5,5),(6,6)],2,locations=[R(0),R(1),R(0)],spills=0),
               case([(4,4),(4,4),(5,5)],1,locations=[R(0),S(0),R(0)],spills=1),
               # MAX endpoints never free and never overflow.
               case([(0,MAX),(MAX,MAX)],1,locations=[R(0),S(0)],spills=1),
               case([(MAX,MAX)]*3,2,locations=[R(0),R(1),S(0)],spills=1),
               case([(0,MAX-1),(MAX,MAX)],1,locations=[R(0),R(0)],spills=0),
               case([(MAX-1,MAX),(MAX,MAX)],1,locations=[R(0),S(0)],spills=1),
               case([(MAX,MAX)],16,locations=[R(0)],spills=0),
               case([(0,MAX)]+[(i,i)for i in range(1,11)],1,locations=[R(0)]+[S(i)for i in range(10)],spills=10),
               # Lowest free register, not the most recently freed or the highest.
               case([(0,1),(0,5),(0,2),(3,4),(4,4)],3,locations=[R(0),R(1),R(2),R(0),R(2)],spills=0),
               case([(0,9),(0,1),(0,9),(0,1),(2,2)],4,locations=[R(0),R(1),R(2),R(3),R(1)],spills=0),
               # No eviction and no spill-slot reuse, even after a spilled interval ends.
               case([(0,10),(1,1),(2,2),(11,11)],1,locations=[R(0),S(0),S(1),R(0)],spills=2),
               # Every register full: the rest all spill.
               case([(0,MAX)]*40,16,locations=[R(i)for i in range(16)]+[S(i)for i in range(24)],spills=24),
               case([(0,MAX)]*6,1,locations=[R(0)]+[S(i)for i in range(5)],spills=5)]
        for rc in (0,17,18,64,MAX):
            cases+=[case([],rc,status=INVALID),case([(0,0)],rc,status=INVALID),case([(0,0),(1,1)],rc,no=0,status=INVALID)]
        for bad in ([(5,4)],[(0,1),(MAX,MAX-1)],[(2,3),(1,5)],[(0,0),(1,1),(0,2)],[(MAX,MAX),(0,0)],[(1,1),(MAX,0)]):
            cases+=[case(bad,4,status=INVALID),case(bad,4,no=0,status=INVALID),case(bad,1,no=len(bad)+4,status=INVALID)]
        for intervals,rc in (([(0,0)],1),([(0,5),(5,9)],1),([(3,3)]*5,2),([(0,MAX)]*20,16)):
            n=len(intervals)
            cases+=[case(intervals,rc,no=n-1,status=CAPACITY),case(intervals,rc,no=0,status=CAPACITY),case(intervals,rc,no=n+9,status=OK)]
        cases.append(case([(0,3),(1,2)],2,readonly=1,status=OK,locations=[R(0),R(1)],spills=0))
        self.run_both(cases,'bounds')
        self.records.append(dict(test='equal-touching-max-empty-spill-invalid-capacity',cases=len(cases),
            invalid_preflights_per_native=PREFLIGHTS,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/register_slots.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/register_slots_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            # Frees a register when old end == new start (closed intervals still share that point).
            ('bad-release-touching','ends[r]<s.start','ends[r]<=s.start',
             [case([(0,5),(5,9)],1)],'locations'),
            # Picks the highest-numbered free register instead of the lowest.
            ('bad-highest-free','while r<register_count{if busy[r]==0||ends[r]<s.start{break;}r+=1;}',
             'var pick=register_count;while r<register_count{if busy[r]==0||ends[r]<s.start{pick=r;}r+=1;}r=pick;',
             [case([(0,9),(0,1),(0,9),(0,1),(2,2)],4)],'locations'),
            # Reuses spill slot 0 for every spill.
            ('bad-reuse-spill','out[i]=Location{kind:SPILL,index:spills};spills+=1;','out[i]=Location{kind:SPILL,index:0};spills=1;',
             [case([(0,10),(1,1),(2,2)],1)],'locations'),
            # Writes out during data validation, before a later bad interval is found.
            ('bad-early-write','if s.start>s.end||s.start<prev{return INVALID;}',
             'if i<out.len{out[i]=Location{kind:REGISTER,index:0};}if s.start>s.end||s.start<prev{return INVALID;}',
             [case([(0,1),(3,2)],1,no=4,status=INVALID)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
