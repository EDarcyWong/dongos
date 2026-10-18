"""Actual Dong linear live-interval envelopes, against a Python per-value min/max dictionary."""
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

SOURCE=ROOT/'lang/bootstrap/linear_intervals.dg'
OK,INVALID,CAPACITY=0,1,2
MAX=2**64-1
NONE=MAX
PREFLIGHTS=17
WRAPPER='''module probe.intervals_export;
import bootstrap.linear_intervals as l;
export("dong_linear_intervals") pub unsafe fn build(events:*const l.Event,ne:usize,value_count:usize,out:*l.Interval,no:usize,used:*usize)u64{unsafe{
 return l.build(slice_from_raw_parts(events,ne),value_count,slice_from_raw_parts(out,no),used);
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
typedef struct {uint64_t value,position;} Event;
typedef struct {uint64_t first,last;} Interval;
_Static_assert(sizeof(Event)==16&&__builtin_offsetof(Event,position)==8,"Event layout");
_Static_assert(sizeof(Interval)==16&&__builtin_offsetof(Interval,last)==8,"Interval layout");
extern uint64_t ABI dong_linear_intervals(const Event*,uint64_t,uint64_t,Interval*,uint64_t,uint64_t*);
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
/* Each case has exactly one defect (descriptor, then data, then capacity); every arena byte stays unchanged. */
static unsigned preflight(void){
 static uint8_t arena[2048] __attribute__((aligned(16))),saved[2048];const unsigned total=17;
 Event*e=(Event*)arena;Interval*o=(Interval*)(arena+512);uint64_t*u=(uint64_t*)(arena+1536);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));e[0].value=0;e[0].position=3;e[1].value=1;e[1].position=5;memcpy(saved,arena,sizeof(arena));
  uint64_t r=0,want=i==16?2:1;
  switch(i){
   case 0:r=dong_linear_intervals(e,2,2,o,8,NULL);break;
   case 1:r=dong_linear_intervals(e,2,2,o,8,(uint64_t*)(arena+1540));break;
   case 2:r=dong_linear_intervals(e,2,2,o,8,(uint64_t*)(arena+8));break;           /* used inside events */
   case 3:r=dong_linear_intervals(e,2,2,o,8,(uint64_t*)(arena+512+120));break;     /* used inside out[7] */
   case 4:r=dong_linear_intervals(e,2,2,(Interval*)(arena+16),8,u);break;          /* out overlaps events */
   case 5:r=dong_linear_intervals((const Event*)(arena+4),2,2,o,8,u);break;
   case 6:r=dong_linear_intervals(e,2,2,(Interval*)(arena+516),8,u);break;
   case 7:r=dong_linear_intervals(NULL,2,2,o,8,u);break;
   case 8:r=dong_linear_intervals(e,2,2,NULL,8,u);break;
   case 9:r=dong_linear_intervals(e,UINT64_MAX/16+1,2,o,8,u);break;
   case 10:r=dong_linear_intervals((const Event*)(uintptr_t)(UINT64_MAX-15),2,2,o,8,u);break;
   case 11:r=dong_linear_intervals(e,2,2,o,UINT64_MAX/16+1,u);break;
   case 12:r=dong_linear_intervals(e,2,2,o,8,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 13:r=dong_linear_intervals(e,2,2,(Interval*)(uintptr_t)(UINT64_MAX-127),8,u);break;
   case 14:r=dong_linear_intervals(e,2,UINT64_MAX/16+1,o,8,u);break;               /* value_count bytes overflow, not CAPACITY */
   case 15:r=dong_linear_intervals(e,2,1,o,8,u);break;                            /* event value 1 >= value_count */
   default:r=dong_linear_intervals(e,2,2,o,1,u);break;                            /* CAPACITY */
  }
  if(r!=want||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"preflight %u status %u\n",i,(unsigned)r);exit(93);}
 }
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=preflight(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[4];read_exact(h,sizeof(h));uint64_t ne=h[0],vc=h[1],no=h[2],ro=h[3];
  if(ne>200000||no>200000)exit(94);
  uint64_t eb=ne*16;uint8_t*in=malloc(eb+64),*copy=malloc(eb+1);Interval*ob=malloc((no+8)*16);uint64_t meta[3];
  if(!in||!copy||!ob)exit(95);
  memset(in,0xa5,eb+64);read_exact(in+32,eb);memcpy(copy,in+32,eb);
  const Event*e=ne?(const Event*)(in+32):NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro&&ne){pages=(eb/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,eb);ro_protect(page,pages);e=(const Event*)page;}
  memset(ob,0xa5,(no+8)*16);memset(meta,0xa5,sizeof(meta));uint64_t*used=meta+1;
  uint64_t r=dong_linear_intervals(e,ne,vc,no?ob+4:NULL,no,used);
  uint64_t valid=(!eb||!memcmp(copy,e,eb))&&(ro||(filled(in,32)&&filled(in+32+eb,32)))&&filled(ob,64)&&filled(ob+4+no,64)&&
    filled(meta,8)&&filled(meta+2,8);
  if(r)valid=valid&&filled(ob+4,no*16)&&filled(used,8);
  else valid=valid&&vc<=no&&filled(ob+4+vc,(no-vc)*16);
  uint64_t response[3]={r,valid,r?0:*used};write_exact(response,24);write_exact(ob+4,r?0:vc*16);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(ob);
 }return 0;
}
'''


def reference(events,value_count,no):
    """Python dictionary of per-value min/max. Returns (status, intervals)."""
    for value,position in events:
        if value>=value_count or position==NONE:return INVALID,None
    if value_count*16>MAX:return INVALID,None
    if no<value_count:return CAPACITY,None
    seen={}
    for value,position in events:
        lo,hi=seen.get(value,(position,position))
        seen[value]=(min(lo,position),max(hi,position))
    return OK,[seen.get(v,(NONE,0))for v in range(value_count)]


def case(events,value_count,no=None,readonly=0,status=None):
    no=value_count if no is None else no
    expected=reference(events,value_count,no)
    if status is not None:assert expected[0]==status,(status,expected,events,value_count,no)
    return dict(events=events,value_count=value_count,no=no,readonly=readonly,expected=expected)


def position(rng):
    return rng.choice([rng.randrange(64),rng.randrange(1<<20),2**32-1+rng.randrange(3),2**63+rng.randrange(8),MAX-1-rng.randrange(4)])


class LinearIntervalsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native linear intervals require NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/C14'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/intervals_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/intervals_export.dg',roots=roots,mode=mode)
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

    def envelope(self,events,intervals,label):
        """Order-free facts: first/last are real positions of the value and enclose all of them."""
        groups={}
        for v,p in events:groups.setdefault(v,[]).append(p)
        for value,(first,last) in enumerate(intervals):
            positions=groups.get(value,[])
            if not positions:
                self.assertEqual((first,last),(NONE,0),(label,value,'envelope'));continue
            self.assertLessEqual(first,last,(label,value,'envelope'))
            self.assertIn(first,positions,(label,value,'envelope'));self.assertIn(last,positions,(label,value,'envelope'))
            self.assertTrue(all(first<=p<=last for p in positions),(label,value,'envelope'))

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:
            payload.extend(struct.pack('<4Q',len(c['events']),c['value_count'],c['no'],c['readonly']))
            for value,position in c['events']:payload.extend(struct.pack('<2Q',value,position))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,PREFLIGHTS)
        offset=8
        for index,c in enumerate(cases):
            status,guard,used=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['expected'][0],(label,index,'status'))
            if not status:
                n=c['value_count'];flat=struct.unpack_from('<%dQ'%(2*n),run.stdout,offset);offset+=16*n
                intervals=[(flat[2*i],flat[2*i+1])for i in range(n)]
                self.assertEqual(used,n,(label,index,'used'))
                self.assertEqual(intervals,c['expected'][1],(label,index,'intervals'))
                self.envelope(c['events'],intervals,(label,index))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def test_seeded_cases_against_dictionary(self):
        cases=[];seeds=range(0xC1400,0xC1400+128)
        for seed in seeds:
            rng=random.Random(seed)
            for k in range(4):
                vc=rng.randint(0,12);ne=rng.randint(0,30)
                events=[(rng.randrange(vc if vc else 3),position(rng))for _ in range(ne)]
                if events and rng.random()<0.4:events+=[rng.choice(events)for _ in range(rng.randint(1,4))]
                rng.shuffle(events)
                if events and rng.random()<0.2:                     # one bad event, often the last
                    at=len(events)-1 if rng.random()<0.6 else rng.randrange(len(events))
                    v,p=events[at];events[at]=(vc+rng.randrange(3),p)if rng.random()<0.5 else (v,NONE)
                no=rng.choice([vc,vc+3,max(vc-1,0)])
                cases.append(case(events,vc,no,readonly=int(k==0 and seed%8==0)))
        rng=random.Random(0xC14B)
        cases.append(case([(rng.randrange(4096),position(rng))for _ in range(60000)],4096,4098,readonly=1,status=OK))
        statuses={s:sum(c['expected'][0]==s for c in cases)for s in (OK,INVALID,CAPACITY)}
        self.assertTrue(all(statuses.values()),statuses)
        self.run_both(cases,'seeded')
        self.records.append(dict(test='seeded-dictionary',cases=len(cases),seeds='0xC1400..0xC147F,0xC14B',statuses=statuses,modes=2,passed=True))

    def test_boundaries_order_and_error_priority(self):
        H=MAX//16
        cases=[case([],0,status=OK),case([],0,5,status=OK),case([],3,status=OK),case([],3,2,status=CAPACITY),case([],1,0,status=CAPACITY),
               case([(0,0)],1,status=OK),case([(0,0)],2,status=OK),case([(0,MAX-1)],1,status=OK),case([(0,0),(0,MAX-1)],1,status=OK),
               case([(0,MAX-1),(0,0)],1,status=OK),case([(1,2**63),(1,2**32-1),(1,2**63+5)],2,status=OK),
               case([(1,7)]*10,2,status=OK),case([(0,9),(0,3),(0,6),(0,1),(0,8)],1,status=OK),case([(0,5),(0,2),(1,7)],2,status=OK),
               case([(2,4),(0,1)],3,status=OK),case([(2,4),(0,1)],3,10,status=OK),case([(4,4),(4,4)],6,status=OK),
               case([(0,MAX)],1,status=INVALID),case([(1,0)],1,status=INVALID),case([(MAX,0)],1,status=INVALID),case([(0,0)],0,status=INVALID),
               case([(0,1)]*5+[(0,MAX)],1,status=INVALID),case([(0,1),(2,2),(1,3),(3,1)],3,status=INVALID),
               case([(0,1),(2,2),(1,3),(3,1)],3,0,status=INVALID),case([(0,1),(4,1)],4,1,status=INVALID),case([(0,1),(1,MAX)],2,0,status=INVALID),
               case([],H+1,4,status=INVALID),case([],MAX,0,status=INVALID),case([(0,MAX)],H+1,2,status=INVALID),case([(H,5)],H,4,status=INVALID),
               case([],H,4,status=CAPACITY),case([(H-1,5),(0,MAX-1)],H,0,status=CAPACITY)]
        for events,vc in (([(0,3)],1),([(1,1),(0,2),(1,9)],3),([(i%5,i)for i in range(40)],8)):
            cases+=[case(events,vc,vc-1,status=CAPACITY),case(events,vc,0,status=CAPACITY),case(events,vc,vc+7,status=OK),case(events,vc,readonly=1,status=OK)]
        self.assertEqual(reference([(0,5),(0,2),(1,7)],2,2),(OK,[(2,5),(7,7)]))
        self.assertEqual(reference([(2,4),(0,1)],3,3),(OK,[(1,1),(NONE,0),(4,4)]))
        self.run_both(cases,'bounds')
        self.records.append(dict(test='boundaries-order-priority',cases=len(cases),preflights_per_native=PREFLIGHTS,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/linear_intervals.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/intervals_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            # last keeps only the final event visited, not the maximum.
            ('bad-last-only-final','if e.position>last{last=e.position;}','last=e.position;',
             [case([(0,5),(0,2),(1,7)],2,status=OK)],'intervals'),
            # Validation stops before the final event, whose position is NONE.
            ('bad-skip-final-event','while i<events.len{let e=events[i];if e.value>=value_count',
             'while i+1<events.len{let e=events[i];if e.value>=value_count',
             [case([(0,1),(1,MAX)],2,status=INVALID)],'status'),
            # Only values that occur are reset; absent value 1 keeps the caller's bytes.
            ('bad-uncleared-absent','i=0;while i<value_count{out[i]=Interval{first:NONE,last:0};i+=1;}',
             'i=0;while i<events.len{out[events[i].value]=Interval{first:NONE,last:0};i+=1;}',
             [case([(2,4),(0,1)],3,status=OK)],'intervals'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
