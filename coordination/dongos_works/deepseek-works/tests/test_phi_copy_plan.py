"""Actual Dong phi edge-copy planning, against an independent Python dict model and real C9 scheduling."""
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

SOURCE=WORKS/'deepseek-works/src/bootstrap/phi_copy_plan.dg'
# Mainline C9, imported read-only through the explicit ROOT/'lang' source root. deepseek-works/src is never a
# root here: it holds its own historical parallel_moves.dg, which would be a duplicate module.
MOVES=ROOT/'lang/bootstrap/parallel_moves.dg'
OK,INVALID,CAPACITY=0,1,2
MAX=2**64-1
NOT_RUN=MAX
PREFLIGHTS,FIXED=20,2
WRAPPER='''module probe.phi_export;
import bootstrap.phi_copy_plan as p;
import bootstrap.parallel_moves as m;
export("dong_phi_copy_plan") pub unsafe fn plan(phis:*const p.Phi,np:usize,inputs:*const p.Input,ni:usize,predecessor:usize,
 block_count:usize,slot_count:usize,out:*m.Move,no:usize,used:*usize)u64{unsafe{
 return p.plan(slice_from_raw_parts(phis,np),slice_from_raw_parts(inputs,ni),predecessor,block_count,slot_count,
  slice_from_raw_parts(out,no),used);
}}
export("dong_parallel_moves") pub unsafe fn schedule(moves:*const m.Move,nm:usize,slot_count:usize,
 out:*m.Move,no:usize,work:*u8,nw:usize,used:*usize)u64{unsafe{
 return m.schedule(slice_from_raw_parts(moves,nm),slot_count,slice_from_raw_parts(out,no),slice_from_raw_parts(work,nw),used);
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
typedef struct {uint64_t dst,first,count;} Phi;
typedef struct {uint64_t pred,src;} Input;
typedef struct {uint64_t dst,src;} Move;
_Static_assert(sizeof(Phi)==24&&__builtin_offsetof(Phi,count)==16,"Phi layout");
_Static_assert(sizeof(Input)==16&&__builtin_offsetof(Input,src)==8,"Input layout");
_Static_assert(sizeof(Move)==16&&__builtin_offsetof(Move,src)==8,"Move layout");
extern uint64_t ABI dong_phi_copy_plan(const Phi*,uint64_t,const Input*,uint64_t,uint64_t,uint64_t,uint64_t,Move*,uint64_t,uint64_t*);
extern uint64_t ABI dong_parallel_moves(const Move*,uint64_t,uint64_t,Move*,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static void put(uint8_t*base,uint64_t at,const void*v,uint64_t n){memcpy(base+at,v,n);}
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
/* Bad descriptors: INVALID with every arena byte unchanged. Every fixture keeps the data valid (the final
   iteration runs the unmodified fixture and must succeed), and misaligned views point at valid data copies. */
static unsigned invalid(void){
 static uint8_t arena[2048],saved[2048],expect[2048];const unsigned total=20;
 Phi*p=(Phi*)arena;Input*in=(Input*)(arena+256);Move*o=(Move*)(arena+512);uint64_t*u=(uint64_t*)(arena+1536);
 for(unsigned i=0;i<=total;i++){
  memset(arena,0xa5,sizeof(arena));
  /* Two phis sharing input range [0,2); inputs[2..4) is an unreferenced tail. */
  Phi ps[2]={{0,0,2},{1,0,2}};Input is[4]={{0,1},{1,0},{0,0},{1,1}};
  put(arena,0,ps,48);put(arena,256,is,64);put(arena,132,ps,48);put(arena,324,is,64);memcpy(saved,arena,sizeof(arena));
  const Phi*pp=p;uint64_t np=2;const Input*ip=in;uint64_t ni=4;Move*op=o;uint64_t no=8;uint64_t*up=u;
  switch(i){
   case 0:up=NULL;break;
   case 1:up=(uint64_t*)(arena+1540);break;
   case 2:up=(uint64_t*)(arena+8);break;                 /* inside phis */
   case 3:up=(uint64_t*)(arena+256+56);break;            /* inside the unreferenced inputs tail */
   case 4:up=(uint64_t*)(arena+512+120);break;           /* inside out */
   case 5:op=(Move*)(arena+32);break;                    /* out over phis */
   case 6:op=(Move*)(arena+256+48);break;                /* out over the unreferenced inputs tail only */
   case 7:pp=(const Phi*)(arena+132);break;              /* misaligned copy of valid phis */
   case 8:ip=(const Input*)(arena+324);break;            /* misaligned copy of valid inputs */
   case 9:op=(Move*)(arena+516);break;
   case 10:pp=NULL;break;
   case 11:ip=NULL;break;
   case 12:op=NULL;break;
   case 13:np=UINT64_MAX/24+1;break;
   case 14:ni=UINT64_MAX/16+1;break;
   case 15:no=UINT64_MAX/16+1;break;
   case 16:pp=(const Phi*)(uintptr_t)(UINT64_MAX-23);break;
   case 17:ip=(const Input*)(uintptr_t)(UINT64_MAX-31);break;
   case 18:op=(Move*)(uintptr_t)(UINT64_MAX-15);break;
   case 19:up=(uint64_t*)(uintptr_t)(UINT64_MAX-7);break;
   default:break;
  }
  uint64_t s=dong_phi_copy_plan(pp,np,ip,ni,0,2,2,op,no,up);
  if(i==total){
   Move want[2]={{0,1},{1,1}};uint64_t two=2;memcpy(expect,saved,sizeof(expect));put(expect,512,want,32);put(expect,1536,&two,8);
   if(s||memcmp(expect,arena,sizeof(arena))){fprintf(stderr,"preflight baseline status %u\n",(unsigned)s);exit(93);}
  }else if(s!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)s);exit(93);}
 }
 return total;
}
/* Legal layouts at the edges of the alias rules. */
static unsigned fixed(void){
 static uint8_t arena[1024],expect[1024];
 /* phis and inputs read the same bytes: phi {0,0,1}; inputs {0,0},{1,7} (the second is an unreferenced tail). */
 memset(arena,0xa5,sizeof(arena));uint64_t words[4]={0,0,1,7};put(arena,0,words,32);memcpy(expect,arena,sizeof(arena));
 uint64_t s=dong_phi_copy_plan((const Phi*)arena,1,(const Input*)arena,2,0,2,2,(Move*)(arena+256),1,(uint64_t*)(arena+512));
 Move a={0,0};uint64_t one=1;put(expect,256,&a,16);put(expect,512,&one,8);
 if(s||memcmp(expect,arena,sizeof(arena))){fprintf(stderr,"shared read-only bytes status %u\n",(unsigned)s);exit(96);}
 /* out ends exactly where inputs begin and used starts exactly where inputs end; the match is not first. */
 memset(arena,0xa5,sizeof(arena));Phi ph={1,1,2};Input is[3]={{0,0},{1,0},{0,1}};put(arena,0,&ph,24);put(arena,256,is,48);
 memcpy(expect,arena,sizeof(arena));
 s=dong_phi_copy_plan((const Phi*)arena,1,(const Input*)(arena+256),3,0,2,2,(Move*)(arena+224),2,(uint64_t*)(arena+304));
 Move b={1,1};put(expect,224,&b,16);put(expect,304,&one,8);
 if(s||memcmp(expect,arena,sizeof(arena))){fprintf(stderr,"adjacent objects status %u\n",(unsigned)s);exit(96);}
 return 2;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t flag,count,head[2]={0,0};read_exact(&flag,8);if(flag){head[0]=invalid();head[1]=fixed();}read_exact(&count,8);write_exact(head,16);
 while(count--){
  uint64_t h[7];read_exact(h,sizeof(h));uint64_t np=h[0],ni=h[1],pred=h[2],bc=h[3],slots=h[4],no=h[5],ro=h[6];
  if(np>100000||ni>300000||no>300000)exit(94);
  uint64_t pb=np*24,ib=ni*16;uint8_t*in=malloc(pb+ib+96),*copy=malloc(pb+ib+1);Move*out=malloc((no+4)*16);uint64_t meta[3];
  if(!in||!copy||!out)exit(95);
  memset(in,0xa5,pb+ib+96);read_exact(in+32,pb);read_exact(in+64+pb,ib);memcpy(copy,in+32,pb);memcpy(copy+pb,in+64+pb,ib);
  const Phi*p=np?(const Phi*)(in+32):NULL;const Input*ip=ni?(const Input*)(in+64+pb):NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro){pages=((pb+ib)/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,pb+ib);ro_protect(page,pages);
   p=np?(const Phi*)page:NULL;ip=ni?(const Input*)(page+pb):NULL;}
  memset(out,0xa5,(no+4)*16);memset(meta,0xa5,sizeof(meta));uint64_t*used=meta+1;
  uint64_t s=dong_phi_copy_plan(p,np,ip,ni,pred,bc,slots,no?out+2:NULL,no,used);
  uint64_t valid=(!pb||!memcmp(copy,p,pb))&&(!ib||!memcmp(copy+pb,ip,ib))&&(ro||(filled(in,32)&&filled(in+32+pb,32)&&filled(in+64+pb+ib,32)))&&
    filled(out,32)&&filled(out+2+no,32)&&filled(meta,8)&&filled(meta+2,8);
  if(s)valid=valid&&filled(out+2,no*16)&&filled(used,8);
  else valid=valid&&*used<=no&&filled(out+2+*used,(no-*used)*16);
  uint64_t n=(!s&&valid)?*used:0,r2=UINT64_MAX,sv=1,sn=0;Move*seq=NULL;
  if(!s&&valid){
   /* Hand the plan straight to mainline C9 with exactly sufficient output (2n) and workspace (n). */
   uint64_t so=2*n;seq=malloc((so+4)*16);uint8_t*work=malloc(n+64);Move*plan=malloc(n*16+1);uint64_t sm[3];
   if(!seq||!work||!plan)exit(95);
   memcpy(plan,out+2,n*16);memset(seq,0xa5,(so+4)*16);memset(work,0xa5,n+64);memset(sm,0xa5,sizeof(sm));
   r2=dong_parallel_moves(n?out+2:NULL,n,slots,so?seq+2:NULL,so,n?work+32:NULL,n,sm+1);
   sv=(!n||!memcmp(plan,out+2,n*16))&&filled(seq,32)&&filled(seq+2+so,32)&&filled(work,32)&&filled(work+32+n,32)&&filled(sm,8)&&filled(sm+2,8);
   if(!r2){sn=sm[1];sv=sv&&sn<=so;if(sv)sv=filled(seq+2+sn,(so-sn)*16);else sn=0;}
   free(work);free(plan);
  }
  uint64_t response[6]={s,valid,n,r2,sv,sn};write_exact(response,48);write_exact(out+2,n*16);if(sn)write_exact(seq+2,sn*16);
  if(page)ro_free(page,pages);
  free(seq);free(in);free(copy);free(out);
 }return 0;
}
'''


def reference(phis,inputs,pred,bc,slots,no):
    """Independent model: a dict pred->src per phi. Returns (status, moves)."""
    if bc==0 or pred>=bc or slots==0 or slots==MAX:return INVALID,None
    seen=set();chosen=[]
    for dst,first,count in phis:
        if dst>=slots or dst in seen:return INVALID,None
        seen.add(dst)
        if count and first+count>len(inputs):return INVALID,None
        table={}
        for p,s in inputs[first:first+count]:
            if p>=bc or s>=slots or p in table:return INVALID,None
            table[p]=s
        if pred not in table:return INVALID,None
        chosen.append((dst,table[pred]))
    if no<len(phis):return CAPACITY,None
    return OK,chosen


def check_sequence(test,moves,slots,sequence,label):
    """Run C9's sequence on unique symbolic old values and compare with the parallel phi copy."""
    state={}
    def get(x):return state.get(x,('old',x)if x<slots else('undefined-temp',))
    for d,s in sequence:
        test.assertTrue(d<=slots and s<=slots,(label,'location id'))
        state[d]=get(s)
    want={d:('old',s)for d,s in moves}
    touched={x for m in moves for x in m}|{d for d,_ in sequence if d<slots}
    test.assertEqual({i:get(i)for i in touched},{i:want.get(i,('old',i))for i in touched},(label,'semantics'))


def case(phis,inputs,pred,bc,slots,no=None,readonly=0,status=None):
    no=len(phis)if no is None else no
    expected=reference(phis,inputs,pred,bc,slots,no)
    if status is not None:assert expected[0]==status,(status,expected,phis,inputs,pred)
    return dict(phis=phis,inputs=inputs,pred=pred,bc=bc,slots=slots,no=no,readonly=readonly,expected=expected)


def random_case(rng,readonly):
    bc=rng.randint(1,6);slots=rng.randint(1,10);pred=rng.randrange(bc);n=rng.randint(0,min(slots,6))
    junk=lambda:(rng.choice([rng.randrange(8),rng.randrange(MAX+1)]),rng.choice([rng.randrange(12),rng.randrange(MAX+1)]))
    inputs=[junk()for _ in range(rng.randint(0,2))]          # unreferenced head
    phis=[];ranges=[]
    for dst in rng.sample(range(slots),n):
        if ranges and rng.random()<0.25:first,count=rng.choice(ranges)   # shared read-only range
        else:
            preds=rng.sample(range(bc),rng.randint(1,bc))
            if pred not in preds and rng.random()<0.85:preds[rng.randrange(len(preds))]=pred
            first=len(inputs);count=len(preds);ranges.append((first,count))
            inputs+=[(p,rng.randrange(slots))for p in preds]
        phis.append((dst,first,count))
    inputs+=[junk()for _ in range(rng.randint(0,2))]         # unreferenced tail
    kind=rng.choice(['none']*5+['dup-dst','dup-pred','bad-src','bad-pred','retarget','range','params'])
    referenced=[(i,f+k)for i,(d,f,c)in enumerate(phis)for k in range(c)]
    if kind=='dup-dst' and n>=2:
        i,j=rng.sample(range(n),2);phis[j]=(phis[i][0],)+phis[j][1:]
    elif kind=='dup-pred':
        multi=[(f,c)for d,f,c in phis if c>=2]
        if multi:f,c=rng.choice(multi);a,b=rng.sample(range(c),2);inputs[f+b]=(inputs[f+a][0],inputs[f+b][1])
    elif kind in('bad-src','bad-pred','retarget')and referenced:
        _,at=rng.choice(referenced);p,s=inputs[at]
        if kind=='bad-src':inputs[at]=(p,rng.choice([slots,slots+1,MAX]))
        elif kind=='bad-pred':inputs[at]=(rng.choice([bc,bc+3,MAX]),s)
        else:inputs[at]=(rng.randrange(bc),s)                   # may drop or duplicate the chosen predecessor
    elif kind=='range' and n:
        i=rng.randrange(n);d,f,c=phis[i];phis[i]=(d,rng.choice([len(inputs)-c+1,len(inputs)+1,MAX,MAX-c+1]),max(c,1))
    elif kind=='params':
        choice=rng.randrange(4)
        if choice==0:bc=0
        elif choice==1:pred=bc
        elif choice==2:slots=0
        else:slots=MAX
    no=rng.choice([n,n,n,n+3,max(n-1,0),0])
    return case(phis,inputs,pred,bc,slots,no=no,readonly=readonly)


class PhiCopyPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native phi copy planning requires NASM/GCC')
        cls.work=WORKS/'deepseek-works/build/D18'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,MOVES,Path(__file__)]}
        root=cls.private_root('good',SOURCE.read_text(encoding='utf-8'))
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build(root,mode,mode)

    @classmethod
    def private_root(cls,name,source):
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/phi_copy_plan.dg').write_text(source,encoding='utf-8')
        (root/'probe/phi_export.dg').write_text(WRAPPER,encoding='utf-8')
        return root

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,root,mode,name):
        compiled=compile_file(root/'probe/phi_export.dg',roots=[root,ROOT/'lang'],mode=mode)
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
            payload.extend(struct.pack('<7Q',len(c['phis']),len(c['inputs']),c['pred'],c['bc'],c['slots'],c['no'],c['readonly']))
            for d,f,k in c['phis']:payload.extend(struct.pack('<3Q',d,f,k))
            for p,s in c['inputs']:payload.extend(struct.pack('<2Q',p,s))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<2Q',run.stdout,0),(PREFLIGHTS if preflight else 0,FIXED if preflight else 0))
        offset=16;results=[]
        for index,c in enumerate(cases):
            status,guard,used,scheduled,sguard,sused=struct.unpack_from('<6Q',run.stdout,offset);offset+=48
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['expected'][0],(label,index,'status'))
            got=sequence=None
            if status==OK:
                flat=struct.unpack_from('<%dQ'%(2*used),run.stdout,offset);offset+=16*used
                got=[(flat[2*i],flat[2*i+1])for i in range(used)]
                self.assertEqual(got,c['expected'][1],(label,index,'phi-moves'))
                self.assertEqual(scheduled,OK,(label,index,'schedule-status'))
                self.assertEqual(sguard,1,(label,index,'schedule-guard'))
                flat=struct.unpack_from('<%dQ'%(2*sused),run.stdout,offset);offset+=16*sused
                sequence=[(flat[2*i],flat[2*i+1])for i in range(sused)]
                check_sequence(self,got,c['slots'],sequence,(label,index))
            else:
                self.assertEqual((used,scheduled,sused),(0,NOT_RUN,0),(label,index,'no-schedule'))
            results.append((status,got,sequence))
        self.assertEqual(offset,len(run.stdout))
        return results

    def run_both(self,cases,label,preflight=True):
        results=[self.run_cases(exe,cases,label+'-'+mode,preflight)for mode,exe in self.executables.items()]
        self.assertEqual(results[0],results[1],(label,'debug/release determinism'))
        return results[0]

    def test_random_phis_against_dict_model(self):
        rng=random.Random(0xC20C);cases=[];statuses={}
        for i in range(600):
            c=random_case(rng,readonly=int(i%40==0));cases.append(c)
            statuses[c['expected'][0]]=statuses.get(c['expected'][0],0)+1
        # 300-phi rotation through three predecessors, read-only, chosen input in the middle of each range.
        phis=[(i,3*i,3)for i in range(300)];inputs=[]
        for i in range(300):inputs+=[(0,i),(2,(i+1)%300),(1,(i+7)%300)]
        cases.append(case(phis,inputs,2,3,300,readonly=1,status=OK))
        self.run_both(cases,'random')
        self.assertGreater(statuses.get(OK,0),100,statuses);self.assertGreater(statuses.get(INVALID,0),100,statuses)
        self.assertGreater(statuses.get(CAPACITY,0),20,statuses)
        self.records.append(dict(test='random-dict-model',cases=len(cases),seed='0xC20C',statuses=statuses,
                                 c9_scheduled_and_symbolically_checked=True,modes=2,passed=True))

    def test_edges_selection_validation_and_capacity(self):
        T=[(MAX,MAX),(MAX-1,0)]                                     # unreferenced tail garbage
        cases=[
            case([],[],0,1,1,status=OK),case([],[],0,1,1,no=0,status=OK),case([],T,4,5,MAX-1,no=3,status=OK),
            # Chosen input is not the first; per-phi input order differs.
            case([(0,0,3)],[(2,7),(0,5),(1,6)],0,3,8,status=OK),
            case([(0,0,2),(1,2,2)],[(1,4),(0,5),(0,6),(1,7)],1,2,8,status=OK),
            # Shared read-only range, self copy included, tail ignored.
            case([(0,0,2),(1,0,2),(2,0,2)],[(0,1),(1,2)]+T,0,2,3,status=OK),
            case([(3,0,2)],[(1,0),(0,3)],0,2,4,status=OK),             # self copy 3<-3
            case([(0,0,2),(1,2,2)],[(0,1),(1,0),(1,1),(0,0)],0,2,2,status=OK),   # swap needing C9's temporary
            case([(0,0,1),(1,1,1),(2,2,1)],[(0,1),(0,2),(0,0)],0,1,3,status=OK), # three-cycle
            case([(MAX-2,0,2)],[(MAX-3,MAX-3),(0,MAX-2)],MAX-3,MAX-2,MAX-1,status=OK),
            # Missing chosen predecessor, empty phi.
            case([(0,0,2)],[(1,0),(2,0)],0,3,1,status=INVALID),case([(0,0,0)],[(0,0)],0,1,1,status=INVALID),
            case([(0,5,0)],[],0,1,1,status=INVALID),
            # Illegal inputs that are not selected.
            case([(0,0,2)],[(0,1),(5,0)],0,2,3,status=INVALID),case([(0,0,2)],[(0,1),(1,9)],0,2,3,status=INVALID),
            case([(0,0,2)],[(0,1),(MAX,0)],0,2,3,status=INVALID),
            case([(0,0,3)],[(0,1),(1,0),(1,2)],0,2,3,status=INVALID),     # duplicate unselected pred
            case([(0,0,2),(1,2,1)],[(0,1),(1,2),(0,0)],0,2,3,status=OK),
            case([(0,0,2),(1,2,2)],[(0,1),(1,2),(0,0),(1,7)],0,2,3,status=INVALID),  # second phi's unselected src
            # Duplicate selected pred, duplicate dst, dst/src out of range.
            case([(0,0,2)],[(0,1),(0,1)],0,1,2,status=INVALID),
            case([(0,0,1),(0,0,1)],[(0,1)],0,1,2,status=INVALID),
            case([(1,0,1),(2,0,1),(1,0,1)],[(0,0)],0,1,3,status=INVALID),
            case([(2,0,1)],[(0,1)],0,1,2,status=INVALID),case([(0,0,1)],[(0,2)],0,1,2,status=INVALID),
            # Ranges.
            case([(0,1,2)],[(0,0),(0,0)],0,1,1,status=INVALID),case([(0,MAX,1)],[(0,0)],0,1,1,status=INVALID),
            case([(0,1,MAX)],[(0,0),(0,0)],0,1,1,status=INVALID),case([(0,2,1)],[(0,0),(0,0)],0,1,1,status=INVALID),
            # Parameters, even with no phis.
            case([],[],0,0,1,status=INVALID),case([],[],1,1,1,status=INVALID),case([],[],MAX,MAX,1,status=INVALID),
            case([],[],0,1,0,status=INVALID),case([],[],0,1,MAX,status=INVALID),
            case([(0,0,1)],[(0,0)],0,1,MAX,status=INVALID),
            # INVALID before CAPACITY; CAPACITY exact and zero; generous capacity leaves the tail.
            case([(0,0,2),(1,2,2)],[(0,1),(1,2),(0,0),(1,7)],0,2,3,no=0,status=INVALID),
            case([(0,0,2),(0,0,2)],[(0,1),(1,0)],0,2,2,no=0,status=INVALID),
            case([(0,0,2),(1,2,2)],[(0,1),(1,0),(1,1),(0,0)],0,2,2,no=1,status=CAPACITY),
            case([(0,0,2),(1,2,2)],[(0,1),(1,0),(1,1),(0,0)],0,2,2,no=0,status=CAPACITY),
            case([(0,0,2),(1,2,2)],[(0,1),(1,0),(1,1),(0,0)],0,2,2,no=9,status=OK),
            case([(0,0,2),(1,0,2),(2,0,2)],[(0,1),(1,2)],1,2,3,no=2,readonly=1,status=CAPACITY),
            case([(0,0,2),(1,0,2),(2,0,2)],[(0,1),(1,2)],1,2,3,readonly=1,status=OK),
        ]
        self.assertEqual(reference([(0,0,3)],[(2,7),(0,5),(1,6)],0,3,8,1),(OK,[(0,5)]))
        self.assertEqual(reference([(3,0,2)],[(1,0),(0,3)],0,2,4,1),(OK,[(3,3)]))
        results=self.run_both(cases,'edges')
        # The swap really went through the temporary id slot_count=2.
        self.assertEqual(results[7][2],[(2,0),(0,1),(1,2)])
        self.records.append(dict(test='edges-selection-validation-capacity',cases=len(cases),
                                 invalid_preflights_per_native=PREFLIGHTS,alias_success_fixtures=FIXED,modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            # Takes each phi's first input regardless of its pred.
            ('bad-first-input','while inputs[p.first+j].pred!=predecessor{j+=1;}','j=0;',
             [case([(0,0,2)],[(1,5),(0,2)],0,2,6,status=OK)],"'phi-moves'"),
            # Only the chosen predecessor's input is range-checked.
            ('bad-unselected-unchecked','if a.pred>=block_count||a.src>=slot_count{return false;}',
             'if a.pred==predecessor&&a.src>=slot_count{return false;}',
             [case([(0,0,2)],[(0,1),(1,9)],0,2,3,status=INVALID),case([(0,0,2)],[(0,1),(5,0)],0,2,3,status=INVALID)],"'status'"),
            # Repeated preds inside a phi are not rejected.
            ('bad-no-duplicate-pred','var k=j+1;while k<p.count{if inputs[p.first+k].pred==a.pred{return false;}k+=1;}','',
             [case([(0,0,3)],[(0,1),(1,0),(1,2)],0,2,3,status=INVALID)],"'status'"),
            # Writes out before reporting CAPACITY.
            ('bad-early-write','if out.len<n{return CAPACITY;}','if out.len<n{if out.len!=0{out[0]=moves.Move{dst:0,src:0};}return CAPACITY;}',
             [case([(0,0,1),(1,0,1)],[(0,1)],0,1,2,no=1,status=CAPACITY)],"'guard/atomicity'"),
        ]
        source=SOURCE.read_text(encoding='utf-8')
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first (preflight skipped: a wrong
            # source could corrupt the alias-positive fixtures, and that exit must not count).
            self.run_both(cases,name+'-good',preflight=False)
            self.assertEqual(source.count(old),1,name)
            root=self.private_root(name,source.replace(old,new,1))
            for mode in ('debug','release'):
                exe=self.build(root,mode,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode,preflight=False)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
