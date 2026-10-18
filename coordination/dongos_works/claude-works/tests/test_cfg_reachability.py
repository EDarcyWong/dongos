"""Actual Dong CFG validation/reachability, against an independent Python BFS."""
from collections import deque
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

SOURCE=WORKS/'claude-works/src/bootstrap/cfg_reachability.dg'
OK,INVALID,CAPACITY,WORKSPACE=0,1,2,3
NONE=2**64-1
WRAPPER='''module probe.cfg_export;
import bootstrap.cfg_reachability as g;
export("dong_cfg_reachable") pub unsafe fn reachable(nodes:*const g.Node,nn:usize,edges:*const usize,ne:usize,entry:usize,
 out:*u8,no:usize,work:*usize,nw:usize,used:*usize)u64{unsafe{
 return g.reachable(slice_from_raw_parts(nodes,nn),slice_from_raw_parts(edges,ne),entry,
  slice_from_raw_parts(out,no),slice_from_raw_parts(work,nw),used);
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
typedef struct {uint64_t first,count;} Node;
_Static_assert(sizeof(Node)==16&&__builtin_offsetof(Node,count)==8,"Node layout");
extern uint64_t ABI dong_cfg_reachable(const Node*,uint64_t,const uint64_t*,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*,uint64_t,uint64_t*);
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
 static uint8_t arena[4096],saved[4096];const unsigned total=20;
 Node*n=(Node*)arena;uint64_t*e=(uint64_t*)(arena+256);uint8_t*o=arena+1024;uint64_t*w=(uint64_t*)(arena+2048);uint64_t*u=(uint64_t*)(arena+3072);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));n[0].first=0;n[0].count=1;n[1].first=1;n[1].count=0;e[0]=1;
  memcpy(saved,arena,sizeof(arena));uint64_t r=0;
  switch(i){
   case 0:r=dong_cfg_reachable(n,2,e,1,0,o,8,w,8,NULL);break;
   case 1:r=dong_cfg_reachable(n,2,e,1,0,o,8,w,8,(uint64_t*)(arena+3076));break;
   case 2:r=dong_cfg_reachable(n,2,e,1,0,o,8,w,8,(uint64_t*)n);break;
   case 3:r=dong_cfg_reachable(n,2,e,1,0,(uint8_t*)e,8,w,8,u);break;
   case 4:r=dong_cfg_reachable(n,2,e,1,0,o,8,(uint64_t*)n,8,u);break;
   case 5:r=dong_cfg_reachable(n,2,e,1,0,o,8,(uint64_t*)o,8,u);break;
   case 6:r=dong_cfg_reachable(n,2,e,1,0,o,8,(uint64_t*)(arena+2052),8,u);break;
   case 7:r=dong_cfg_reachable((Node*)(arena+4),2,e,1,0,o,8,w,8,u);break;
   case 8:r=dong_cfg_reachable(n,2,(uint64_t*)(arena+260),1,0,o,8,w,8,u);break;
   case 9:r=dong_cfg_reachable(NULL,2,e,1,0,o,8,w,8,u);break;
   case 10:r=dong_cfg_reachable(n,2,NULL,1,0,o,8,w,8,u);break;
   case 11:r=dong_cfg_reachable(n,UINT64_MAX/8,e,1,0,o,8,w,8,u);break;
   case 12:r=dong_cfg_reachable((Node*)(uintptr_t)(UINT64_MAX-15),2,e,1,0,o,8,w,8,u);break;
   case 13:r=dong_cfg_reachable(n,2,e,1,0,(uint8_t*)(uintptr_t)(UINT64_MAX-3),8,w,8,u);break;
   case 14:r=dong_cfg_reachable(n,0,e,1,0,o,8,w,8,u);break;
   case 15:r=dong_cfg_reachable(n,2,e,1,2,o,8,w,8,u);break;
   case 16:r=dong_cfg_reachable(n,2,e,1,UINT64_MAX,o,8,w,8,u);break;
   case 17:r=dong_cfg_reachable(n,2,e,1,0,o,8,w,8,w+3);break;
   case 18:r=dong_cfg_reachable(n,2,e,1,0,o,8,w,UINT64_MAX/8+1,u);break;
   default:r=dong_cfg_reachable(n,2,e,1,0,o+4,8,w,8,(uint64_t*)(o+8));break;
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
  uint64_t h[6];read_exact(h,sizeof(h));uint64_t nn=h[0],ne=h[1],entry=h[2],no=h[3],nw=h[4],ro=h[5];
  if(nn>200000||ne>400000||no>200000||nw>200000)exit(94);
  uint64_t nb=nn*16,eb=ne*8;uint8_t*in=malloc(nb+eb+96),*copy=malloc(nb+eb+1),*out=malloc(no+64);uint64_t*work=malloc((nw+8)*8);uint64_t meta[3];
  if(!in||!copy||!out||!work)exit(95);
  memset(in,0xa5,nb+eb+96);read_exact(in+32,nb);read_exact(in+64+nb,eb);memcpy(copy,in+32,nb);memcpy(copy+nb,in+64+nb,eb);
  const Node*n=nn?(const Node*)(in+32):NULL;const uint64_t*e=ne?(const uint64_t*)(in+64+nb):NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro){pages=((nb+eb)/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,nb+eb);ro_protect(page,pages);
   n=(const Node*)page;e=(const uint64_t*)(page+nb);}
  memset(out,0xa5,no+64);memset(work,0xa5,(nw+8)*8);memset(meta,0xa5,sizeof(meta));uint64_t*used=meta+1;
  uint64_t r=dong_cfg_reachable(n,nn,e,ne,entry,out+32,no,work+4,nw,used);
  uint64_t valid=(!nb||!memcmp(copy,n,nb))&&(!eb||!memcmp(copy+nb,e,eb))&&(ro||(filled(in,32)&&filled(in+32+nb,32)&&filled(in+64+nb+eb,32)))&&
    filled(out,32)&&filled(out+32+no,32)&&filled(work,32)&&filled(work+4+nw,32)&&filled(meta,8)&&filled(meta+2,8);
  if(r)valid=valid&&filled(out+32,no)&&filled(used,8);
  else{valid=valid&&no>=nn&&filled(out+32+nn,no-nn);for(uint64_t i=0;i<nn;i++)valid=valid&&out[32+i]<=1;}
  uint64_t response[3]={r,valid,r?0:*used};write_exact(response,24);write_exact(out+32,r?0:nn);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(out);free(work);
 }return 0;
}
'''


def reference(nodes,edges,entry,no=None,nw=None):
    """Independent Python BFS after whole-graph validation. Returns (status, used, marks)."""
    n=len(nodes);no=n if no is None else no;nw=n if nw is None else nw
    if n==0 or entry>=n:return INVALID,None,None
    for first,count in nodes:
        if first>len(edges) or first+count>len(edges):return INVALID,None,None
        if any(t>=n for t in edges[first:first+count]):return INVALID,None,None
    if no<n:return CAPACITY,None,None
    if nw<n:return WORKSPACE,None,None
    seen={entry};queue=deque([entry])
    while queue:
        first,count=nodes[queue.popleft()]
        for t in edges[first:first+count]:
            if t not in seen:seen.add(t);queue.append(t)
    return OK,len(seen),bytes(1 if i in seen else 0 for i in range(n))


def case(nodes,edges,entry,no=None,nw=None,readonly=0,status=None):
    n=len(nodes);no=n if no is None else no;nw=n if nw is None else nw
    expected=reference(nodes,edges,entry,no,nw)
    if status is not None:assert expected[0]==status,(status,expected,nodes,edges,entry)
    return dict(nodes=nodes,edges=edges,entry=entry,no=no,nw=nw,readonly=readonly,expected=expected)


def random_graph(rng,n,density=2.0,tail=0):
    nodes,edges=[],[]
    for _ in range(n):
        k=min(int(rng.expovariate(1/density)),12);nodes.append((len(edges),k))
        edges+=[rng.randrange(n)for _ in range(k)]
    edges+=[rng.randrange(1<<64)for _ in range(tail)]   # unreferenced tail: arbitrary values are never read
    return nodes,edges


class CfgReachabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native CFG reachability requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C7'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/cfg_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([WORKS/'claude-works/src',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/cfg_export.dg',roots=roots,mode=mode)
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
            payload.extend(struct.pack('<6Q',len(c['nodes']),len(c['edges']),c['entry'],c['no'],c['nw'],c['readonly']))
            for f,k in c['nodes']:payload.extend(struct.pack('<2Q',f,k))
            payload.extend(struct.pack('<%dQ'%len(c['edges']),*c['edges']))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,20)
        offset=8
        for index,c in enumerate(cases):
            status,guard,used=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['expected'][0],(label,index,'status'))
            if not status:
                marks=run.stdout[offset:offset+len(c['nodes'])];offset+=len(c['nodes'])
                self.assertEqual(used,c['expected'][1],(label,index,'used'))
                self.assertEqual(marks,c['expected'][2],(label,index,'reachable'))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def test_random_graphs_against_python_bfs(self):
        rng=random.Random(0xC7C7);cases=[];statuses={}
        for i in range(400):
            n=rng.randint(1,60);nodes,edges=random_graph(rng,n,rng.choice([0.5,1.5,3.0]),tail=rng.choice([0,0,3]))
            entry=rng.randrange(n);c=case(nodes,edges,entry,readonly=int(i%40==0))
            cases+=[c,case(nodes,edges,entry,no=n+5,nw=n+3)]
            statuses[c['expected'][0]]=statuses.get(c['expected'][0],0)+1
        big_nodes,big_edges=random_graph(random.Random(7),5000,2.0)
        cases.append(case(big_nodes,big_edges,0,readonly=1))
        self.run_both(cases,'random')
        self.assertEqual(statuses,{OK:400})
        self.records.append(dict(test='random-bfs',cases=len(cases),seed='0xC7C7',modes=2,passed=True))

    def test_cycles_disconnected_invalid_unreachable_and_capacity(self):
        cases=[]
        # Self loops, duplicate edges, cycles, disconnected components.
        cases+=[case([(0,0)],[],0,status=OK),case([(0,1)],[0],0,status=OK),case([(0,3)],[0,0,0],0,status=OK),
                case([(0,1),(1,1),(2,1)],[1,2,0],1,status=OK),case([(0,1),(1,1),(2,0),(2,1)],[1,0,2],0,status=OK),
                case([(0,2),(2,0),(2,1),(3,0)],[1,1,0],0,status=OK),case([(0,0),(0,0),(0,0)],[],2,status=OK),
                case([(0,1),(1,1),(2,1),(3,1)],[1,0,3,2],0,status=OK),case([(0,1),(1,1),(2,1),(3,1)],[1,0,3,2],3,status=OK),
                case([(1,1),(2,1)],[9,1,0],0,status=OK)]                                  # edges[0] is never referenced
        # Invalid but unreachable nodes/edges must still be rejected.
        cases+=[case([(0,1),(1,1),(2,1)],[1,0,3],0,status=INVALID),                    # node 2 unreachable, bad target
                case([(0,1),(1,1),(5,1)],[1,0,2],0,status=INVALID),                    # node 2 first past edges
                case([(0,1),(1,1),(2,2)],[1,0,2],0,status=INVALID),                    # node 2 count past edges
                case([(0,1),(NONE,2)],[0],0,status=INVALID),case([(0,1),(1,NONE)],[0,0],0,status=INVALID),
                case([(0,1)],[NONE],0,status=INVALID),case([(0,1)],[1],0,status=INVALID),
                case([(0,1)],[0],1,status=INVALID),case([],[],0,status=INVALID),case([(0,0)],[],NONE,status=INVALID),
                case([(0,1),(1,0)],[5],0,no=0,nw=0,status=INVALID)]                    # INVALID before CAPACITY
        # Capacity and workspace boundaries.
        for n in (1,2,7,33):
            nodes=[(i,1)for i in range(n)];edges=[(i+1)%n for i in range(n)]
            cases+=[case(nodes,edges,0,status=OK),case(nodes,edges,0,no=n-1,status=CAPACITY),case(nodes,edges,0,nw=n-1,status=WORKSPACE),
                    case(nodes,edges,0,no=n-1,nw=n-1,status=CAPACITY),case(nodes,edges,0,no=n+9,nw=n+9,status=OK)]
        cases.append(case([(0,1),(1,1),(2,1)],[1,2,0],0,no=0,nw=0,status=CAPACITY))
        rng=random.Random(0xC7BAD)
        for _ in range(60):
            n=rng.randint(2,30);nodes,edges=random_graph(rng,n,2.0)
            if edges:edges[rng.randrange(len(edges))]=n+rng.randrange(5)
            cases.append(case(nodes,edges,rng.randrange(n)))
        self.run_both(cases,'bounds')
        self.records.append(dict(test='cycles-invalid-capacity',cases=len(cases),invalid_preflights_per_native=20,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/cfg_reachability.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/cfg_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            # Only validates nodes up to the entry: an unreachable bad edge slips through.
            ('bad-unreachable-check',' var i:usize=0;\n while i<nodes.len{\n  let node=nodes[i];',' var i:usize=0;\n while i<1{\n  let node=nodes[i];',
             [case([(0,1),(1,1),(2,1)],[1,0,7],0,status=INVALID)],'status'),
            # Follows only forward edges, treating back edges as already handled cycles.
            ('bad-skip-cycle','if out[target]==0{','if out[target]==0&&target>work[top]{',
             [case([(0,1),(1,0),(1,1),(2,1)],[2,1,3],0,status=OK)],'used|reachable'),
            # Clears out before the capacity check.
            ('bad-early-out','if out.len<nodes.len{return CAPACITY;}','var z:usize=0;while z<out.len{out[z]=0;z+=1;}if out.len<nodes.len{return CAPACITY;}',
             [case([(0,1),(1,1),(2,1)],[1,2,0],0,no=2,status=CAPACITY)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
