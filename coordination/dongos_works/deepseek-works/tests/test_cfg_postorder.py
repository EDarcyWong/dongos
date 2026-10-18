"""Actual Dong CFG iterative DFS post-order, against an independent Python DFS."""
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
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

SOURCE=WORKS/'deepseek-works/src/bootstrap/cfg_postorder.dg'
DOC=WORKS/'deepseek-works/src/bootstrap/cfg_postorder.md'
# Mainline Node provider, imported read-only through the ROOT/'lang' source root.
MAINLINE=ROOT/'lang/bootstrap/cfg_reachability.dg'
OK,INVALID,CAPACITY,WORKSPACE=0,1,2,3
NONE=2**64-1
WRAPPER='''module probe.cfg_postorder_export;
import bootstrap.cfg_reachability as cfg;
import bootstrap.cfg_postorder as p;
export("dong_cfg_postorder") pub unsafe fn order(nodes:*const cfg.Node,nn:usize,edges:*const usize,ne:usize,entry:usize,
 out:*usize,no:usize,marks:*u8,nm:usize,work:*p.Frame,nw:usize,used:*usize)u64{unsafe{
 return p.order(slice_from_raw_parts(nodes,nn),slice_from_raw_parts(edges,ne),entry,
  slice_from_raw_parts(out,no),slice_from_raw_parts(marks,nm),slice_from_raw_parts(work,nw),used);
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
typedef struct {uint64_t node,next;} Frame;
_Static_assert(sizeof(Node)==16&&__builtin_offsetof(Node,count)==8,"Node layout");
_Static_assert(sizeof(Frame)==16&&__builtin_offsetof(Frame,next)==8,"Frame layout");
extern uint64_t ABI dong_cfg_postorder(const Node*,uint64_t,const uint64_t*,uint64_t,uint64_t,
 uint64_t*,uint64_t,uint8_t*,uint64_t,Frame*,uint64_t,uint64_t*);
#define P dong_cfg_postorder
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
static uint8_t arena[8192] __attribute__((aligned(64))),saved[8192];
/* Undo one expected write so the rest of the arena can be compared byte for byte. */
static void restore(const void*p,uint64_t n){memcpy((uint8_t*)p,saved+((const uint8_t*)p-arena),n);}
/* The base fixture (2 nodes, 0->1, everything separate and aligned) is legal; each
   preflight breaks exactly one descriptor rule, so INVALID can only come from it. */
static unsigned checks(void){
 const unsigned total=41;const uint64_t X=UINT64_MAX;
 Node*n=(Node*)arena;uint64_t*e=(uint64_t*)(arena+256);uint64_t*o=(uint64_t*)(arena+1024);
 uint8_t*m=arena+2048;Frame*w=(Frame*)(arena+3072);uint64_t*u=(uint64_t*)(arena+4096);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));n[0].first=0;n[0].count=1;n[1].first=1;n[1].count=0;e[0]=1;
  if(i==18){Node ns[2]={{0,1},{1,0}};memcpy(arena+4,ns,sizeof(ns));}
  if(i==19){uint64_t t=1;memcpy(arena+260,&t,8);}
  memcpy(saved,arena,sizeof(arena));uint64_t r=0;
  switch(i){
   case 0:r=P(n,2,e,1,0,o,8,m,8,w,8,NULL);break;
   case 1:r=P(n,2,e,1,0,o,8,m,8,w,8,(uint64_t*)(arena+4100));break;
   case 2:r=P(n,2,e,1,0,o,8,m,8,w,8,(uint64_t*)n);break;
   case 3:r=P(n,2,e,1,0,o,8,m,8,w,8,e);break;
   case 4:r=P(n,2,e,1,0,o,8,m,8,w,8,o+7);break;
   case 5:r=P(n,2,e,1,0,o,8,m,8,w,8,(uint64_t*)m);break;
   case 6:r=P(n,2,e,1,0,o,8,m,8,w,8,&w[7].next);break;
   case 7:r=P(n,2,e,1,0,(uint64_t*)n,8,m,8,w,8,u);break;
   case 8:r=P(n,2,e,1,0,e,8,m,8,w,8,u);break;
   case 9:r=P(n,2,e,1,0,(uint64_t*)(arena+2040),8,m,8,w,8,u);break;
   case 10:r=P(n,2,e,1,0,(uint64_t*)w,8,m,8,w,8,u);break;
   case 11:r=P(n,2,e,1,0,o,8,(uint8_t*)n+16,8,w,8,u);break;
   case 12:r=P(n,2,e,1,0,o,8,(uint8_t*)e+7,8,w,8,u);break;
   case 13:r=P(n,2,e,1,0,o,8,(uint8_t*)w+127,8,w,8,u);break;
   case 14:r=P(n,2,e,1,0,o,8,(uint8_t*)o+63,8,w,8,u);break;
   case 15:r=P(n,2,e,1,0,o,8,m,8,(Frame*)n,8,u);break;
   case 16:r=P(n,2,e,1,0,o,8,m,8,(Frame*)(arena+136),8,u);break;
   case 17:r=P(n,2,e,1,0,o,8,m,8,(Frame*)(arena+3076),8,u);break;
   case 18:r=P((Node*)(arena+4),2,e,1,0,o,8,m,8,w,8,u);break;
   case 19:r=P(n,2,(uint64_t*)(arena+260),1,0,o,8,m,8,w,8,u);break;
   case 20:r=P(n,2,e,1,0,(uint64_t*)(arena+1028),8,m,8,w,8,u);break;
   case 21:r=P(NULL,2,e,1,0,o,8,m,8,w,8,u);break;
   case 22:r=P(n,2,NULL,1,0,o,8,m,8,w,8,u);break;
   case 23:r=P(n,2,e,1,0,NULL,8,m,8,w,8,u);break;
   case 24:r=P(n,2,e,1,0,o,8,NULL,8,w,8,u);break;
   case 25:r=P(n,2,e,1,0,o,8,m,8,NULL,8,u);break;
   case 26:r=P(n,X/16+1,e,1,0,o,8,m,8,w,8,u);break;
   case 27:r=P(n,2,e,X/8+1,0,o,8,m,8,w,8,u);break;
   case 28:r=P(n,2,e,1,0,o,X/8+1,m,8,w,8,u);break;
   case 29:r=P(n,2,e,1,0,o,8,m,8,w,X/16+1,u);break;
   /* Fake high addresses: aligned and alias-free, rejected only by the endpoint check. */
   case 30:r=P((Node*)(uintptr_t)(X-15),2,e,1,0,o,8,m,8,w,8,u);break;
   case 31:r=P(n,2,(uint64_t*)(uintptr_t)(X-7),1,0,o,8,m,8,w,8,u);break;
   case 32:r=P(n,2,e,1,0,(uint64_t*)(uintptr_t)(X-63),8,m,8,w,8,u);break;
   case 33:r=P(n,2,e,1,0,o,8,(uint8_t*)(uintptr_t)(X-6),8,w,8,u);break;
   case 34:r=P(n,2,e,1,0,o,8,m,8,(Frame*)(uintptr_t)(X-127),8,u);break;
   case 35:r=P(n,2,e,1,0,o,8,m,8,w,8,(uint64_t*)(uintptr_t)(X-7));break;
   case 36:r=P(n,2,e,1,0,o,8,(uint8_t*)(uintptr_t)1,X,w,8,u);break;
   case 37:r=P(n,0,e,1,0,o,8,m,8,w,8,u);break;
   case 38:r=P(n,2,e,1,2,o,8,m,8,w,8,u);break;
   case 39:r=P(n,2,e,1,X,o,8,m,8,w,8,u);break;
   default:r=P(n,2,e,1,0,o,1,m,1,w,1,NULL);break;   /* INVALID before CAPACITY/WORKSPACE */
  }
  if(r!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)r);exit(93);}
 }
 /* Legal aliasing: base fixture, nodes/edges overlapping (read-only), writables exactly adjacent. */
 for(unsigned i=0;i<3;i++){
  memset(arena,0xa5,sizeof(arena));n[0].first=0;n[0].count=1;n[1].first=1;n[1].count=0;e[0]=1;
  memcpy(saved,arena,sizeof(arena));
  const uint64_t*ee=e;uint64_t ne=1,no=8,nm=8,nw=8,want=2;uint64_t*oo=o,*uu=u;uint8_t*mm=m;Frame*ww=w;
  if(i==1){ee=(const uint64_t*)n;ne=4;want=1;}   /* edges are the words {0,1,1,0}: node 0 loops to itself */
  if(i==2){no=2;nm=2;nw=2;mm=arena+1040;ww=(Frame*)(arena+1048);uu=(uint64_t*)(arena+1080);}
  uint64_t r=P(n,2,ee,ne,0,oo,no,mm,nm,ww,nw,uu);
  int good=r==0&&*uu==want&&(want==1?(oo[0]==0&&mm[0]==2&&mm[1]==0):(oo[0]==1&&oo[1]==0&&mm[0]==2&&mm[1]==2));
  restore(oo,want*8);restore(mm,2);restore(ww,2*sizeof(Frame));restore(uu,8);
  if(!good||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"alias positive %u status %u\n",i,(unsigned)r);exit(97);}
 }
 return total+3;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t flag,count,preflights=0;read_exact(&flag,8);if(flag)preflights=checks();read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[7];read_exact(h,sizeof(h));uint64_t nn=h[0],ne=h[1],entry=h[2],no=h[3],nm=h[4],nw=h[5],ro=h[6];
  if(nn>200000||ne>400000||no>200016||nm>200016||nw>200016)exit(94);
  uint64_t nb=nn*16,eb=ne*8;
  uint8_t*in=malloc(nb+eb+96),*copy=malloc(nb+eb+1),*mb=malloc(nm+nn+64);uint64_t*ob=malloc((no+8)*8);
  Frame*wb=malloc((nw+4)*sizeof(Frame));uint64_t meta[3];
  if(!in||!copy||!mb||!ob||!wb)exit(95);
  memset(in,0xa5,nb+eb+96);read_exact(in+32,nb);read_exact(in+64+nb,eb);memcpy(copy,in+32,nb);memcpy(copy+nb,in+64+nb,eb);
  const Node*n=nn?(const Node*)(in+32):NULL;const uint64_t*e=ne?(const uint64_t*)(in+64+nb):NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro){pages=((nb+eb)/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,nb+eb);ro_protect(page,pages);
   n=(const Node*)page;e=(const uint64_t*)(page+nb);}
  memset(mb,0xa5,nm+nn+64);memset(ob,0xa5,(no+8)*8);memset(wb,0xa5,(nw+4)*sizeof(Frame));memset(meta,0xa5,sizeof(meta));
  uint64_t*out=ob+4,*used=meta+1;uint8_t*marks=mb+32;Frame*work=wb+2;
  uint64_t r=P(n,nn,e,ne,entry,out,no,marks,nm,work,nw,used);
  uint64_t valid=(!nb||!memcmp(copy,n,nb))&&(!eb||!memcmp(copy+nb,e,eb))&&(ro||(filled(in,32)&&filled(in+32+nb,32)&&filled(in+64+nb+eb,32)))&&
    filled(ob,32)&&filled(out+no,32)&&filled(mb,32)&&filled(marks+nm,32)&&filled(wb,32)&&filled(work+nw,32)&&filled(meta,8)&&filled(meta+2,8);
  uint64_t k=0;
  if(r)valid=valid&&filled(out,no*8)&&filled(marks,nm)&&filled(work,nw*sizeof(Frame))&&filled(used,8);
  else{
   k=*used;
   if(k>no||nm<nn||nw<nn){valid=0;k=0;}
   else{
    valid=valid&&filled(out+k,(no-k)*8)&&filled(marks+nn,nm-nn)&&filled(work+nn,(nw-nn)*sizeof(Frame));
    for(uint64_t i=0;i<nn;i++)valid=valid&&(marks[i]==0||marks[i]==2);
   }
  }
  uint64_t response[4]={r,valid,r?0:*used,k};write_exact(response,32);write_exact(out,k*8);write_exact(marks,r?0:nn);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(mb);free(ob);free(wb);
 }return 0;
}
'''


def children(nodes,edges,v):
    first,count=nodes[v];return edges[first:first+count]


def postorder_iterative(nodes,edges,entry):
    """Stack of Python iterators; a target is marked the moment it is discovered."""
    seen={entry};post=[];stack=[(entry,iter(children(nodes,edges,entry)))]
    while stack:
        v,it=stack[-1]
        for t in it:
            if t not in seen:
                seen.add(t);stack.append((t,iter(children(nodes,edges,t))));break
        else:
            stack.pop();post.append(v)
    return post


def postorder_recursive(nodes,edges,entry):
    seen=set();post=[]
    def visit(v):
        seen.add(v)
        for t in children(nodes,edges,v):
            if t not in seen:visit(t)
        post.append(v)
    visit(entry);return post


def preorder(nodes,edges,entry):
    seen=set();pre=[]
    def visit(v):
        seen.add(v);pre.append(v)
        for t in children(nodes,edges,v):
            if t not in seen:visit(t)
    visit(entry);return pre


def reference(nodes,edges,entry,no,nm,nw):
    """Whole-graph validation, then DFS. Returns (status, post-order, marks)."""
    n=len(nodes)
    if n==0 or entry>=n:return INVALID,None,None
    for first,count in nodes:
        if first>len(edges) or count>len(edges)-first:return INVALID,None,None
        if any(t>=n for t in edges[first:first+count]):return INVALID,None,None
    if no<n:return CAPACITY,None,None
    if nm<n or nw<n:return WORKSPACE,None,None
    post=postorder_iterative(nodes,edges,entry)
    if n<=300:assert post==postorder_recursive(nodes,edges,entry),(nodes,edges,entry)
    reached=set(post);assert len(reached)==len(post)
    return OK,post,bytes(2 if i in reached else 0 for i in range(n))


def case(nodes,edges,entry,no=None,nm=None,nw=None,readonly=0,status=None,post=None):
    n=len(nodes);no=n if no is None else no;nm=n if nm is None else nm;nw=n if nw is None else nw
    expected=reference(nodes,edges,entry,no,nm,nw)
    if status is not None:assert expected[0]==status,(status,expected,nodes,edges,entry)
    if post is not None:assert expected[1]==post,(post,expected,nodes,edges,entry)
    return dict(nodes=nodes,edges=edges,entry=entry,no=no,nm=nm,nw=nw,readonly=readonly,expected=expected)


def random_graph(rng,n,density=2.0,tail=0):
    nodes,edges=[],[]
    for _ in range(n):
        k=min(int(rng.expovariate(1/density)),12);nodes.append((len(edges),k))
        edges+=[rng.randrange(n)for _ in range(k)]
    edges+=[rng.randrange(1<<64)for _ in range(tail)]   # unreferenced tail: arbitrary values are never read
    return nodes,edges


def shuffled(rng,nodes,edges):
    """Same multiset of successors per node, different input edge order."""
    edges=list(edges)
    for first,count in nodes:
        part=edges[first:first+count];rng.shuffle(part);edges[first:first+count]=part
    return edges


class CfgPostorderTests(unittest.TestCase):
    PREFLIGHTS=44

    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native CFG post-order requires NASM/GCC')
        cls.work=WORKS/'deepseek-works/build/D17'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        # Private source root holds only the module under test; cfg_reachability comes from ROOT/'lang'.
        cls.src_root=cls.work/'src';(cls.src_root/'bootstrap').mkdir(parents=True)
        shutil.copy2(SOURCE,cls.src_root/'bootstrap'/'cfg_postorder.dg')
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        def key(p):
            try:return p.resolve().relative_to(WORKS).as_posix()
            except ValueError:return p.resolve().as_posix()
        cls.inputs={key(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,DOC,Path(__file__),MAINLINE]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/cfg_postorder_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([cls.src_root,ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/cfg_postorder_export.dg',roots=roots,mode=mode)
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
            records=cls.records,integrated=False,OS_VM_built=False),indent=2)+'\n',encoding='utf-8')

    def run_cases(self,exe,cases,label,preflight=True):
        payload=bytearray(struct.pack('<2Q',int(preflight),len(cases)))
        for c in cases:
            payload.extend(struct.pack('<7Q',len(c['nodes']),len(c['edges']),c['entry'],c['no'],c['nm'],c['nw'],c['readonly']))
            for f,k in c['nodes']:payload.extend(struct.pack('<2Q',f,k))
            payload.extend(struct.pack('<%dQ'%len(c['edges']),*c['edges']))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=180)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,self.PREFLIGHTS if preflight else 0)
        offset=8
        for index,c in enumerate(cases):
            status,guard,used,emitted=struct.unpack_from('<4Q',run.stdout,offset);offset+=32
            order=list(struct.unpack_from('<%dQ'%emitted,run.stdout,offset));offset+=8*emitted
            n=len(c['nodes']);marks=run.stdout[offset:offset+n]if not status else None;offset+=0 if status else n
            # Each call's storage verdict is checked before its result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['expected'][0],(label,index,'status-code'))
            if not status:
                self.assertEqual(used,len(c['expected'][1]),(label,index,'used-count'))
                self.assertEqual(order,c['expected'][1],(label,index,'post-order'))
                self.assertEqual(marks,c['expected'][2],(label,index,'marks-state'))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label,preflight=True):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode,preflight)

    def test_seeded_graphs_and_edge_orders_against_python_dfs(self):
        cases=[];statuses={};differs_pre=0;differs_order=0;seeds=range(0xC1900,0xC1980)
        for s in seeds:
            rng=random.Random(s)
            for j in range(3):
                n=rng.randint(1,40);nodes,edges=random_graph(rng,n,rng.choice([0.7,1.5,3.0]),tail=rng.choice([0,0,4]))
                entry=rng.randrange(n);c=case(nodes,edges,entry,readonly=int(s%16==0 and j==0))
                other=shuffled(rng,nodes,edges);d=case(nodes,other,entry)
                cases+=[c,case(nodes,edges,entry,no=n+3,nm=n+5,nw=n+2),d]
                statuses[c['expected'][0]]=statuses.get(c['expected'][0],0)+1
                differs_pre+=c['expected'][1]!=preorder(nodes,edges,entry)
                differs_order+=c['expected'][1]!=d['expected'][1]
        # Larger random graph and a 100000-deep chain with a back edge to entry at every level.
        big_nodes,big_edges=random_graph(random.Random(0xC19B16),5000,2.0,tail=7)
        cases.append(case(big_nodes,big_edges,0,readonly=1))
        depth=100000;deep_nodes=[(2*i,2)for i in range(depth-1)]+[(2*(depth-1),1)]
        deep_edges=[x for i in range(depth-1)for x in (i+1,0)]+[0]
        cases.append(case(deep_nodes,deep_edges,0,readonly=1,post=list(range(depth-1,-1,-1))))
        self.run_both(cases,'seeded')
        self.assertEqual(statuses,{OK:3*len(seeds)})
        self.assertGreater(differs_pre,100);self.assertGreater(differs_order,20)
        self.records.append(dict(test='seeded-dfs',seeds='0xC1900..0xC197F',cases=len(cases),
            postorder_differs_from_preorder=differs_pre,edge_order_changes_result=differs_order,deep_chain=depth,modes=2,passed=True))

    def test_cycles_duplicates_orders_unreachable_invalid_and_workspace(self):
        cases=[
            case([(0,0)],[],0,post=[0]),
            case([(0,1)],[0],0,post=[0]),                                               # self loop
            case([(0,3),(3,0)],[1,1,1],0,post=[1,0]),                                   # duplicate edges
            case([(0,2),(2,1),(3,1),(4,0)],[1,2,3,3],0,post=[3,1,2,0]),                 # diamond; preorder 0,1,3,2
            case([(0,2),(2,1),(3,1),(4,0)],[2,1,3,3],0,post=[3,2,1,0]),                 # same diamond, reversed edge order
            case([(0,1),(1,1),(2,2),(4,0)],[1,2,0,3],0,post=[3,2,1,0]),                 # back edge 2->0 to on-stack entry
            case([(0,1),(1,2),(3,1)],[1,0,2,1],0,post=[2,1,0]),                         # two back edges into the stack
            case([(0,2),(2,0),(2,1)],[1,2,1],0,post=[1,2,0]),                           # cross edge to emitted node
            case([(0,3),(3,1),(4,0),(4,0)],[1,2,3,2],0,post=[2,1,3,0]),
            case([(0,0),(0,2),(2,2)],[2,0,0,0],1,post=[0,2,1]),                         # entry != 0, repeated cross edges
            case([(0,1),(1,0),(1,1),(2,1)],[1,3,2],0,post=[1,0]),                       # unreachable cycle 2<->3
            case([(0,1),(1,0),(1,1),(2,1)],[1,3,2],2,post=[3,2]),
            case([(0,1),(1,0),(1,1),(2,1)],[1,3,2],1,post=[1]),
            case([(1,1),(2,1)],[NONE,1,0],0,post=[1,0]),                                 # unreferenced head
            case([(0,1),(3,1)],[1,NONE,NONE,0],0,post=[1,0]),                           # unreferenced hole
            case([(0,2),(0,2)],[1,0],0,post=[1,0]),                                     # shared edge ranges
            case([(0,1),(1,0)],[1],0,post=[1,0]),                                       # first==edges.len, count 0
            case([(0,1),(1,1),(2,1)],[1,2,0],0,readonly=1,post=[2,1,0]),
            case([(0,0),(0,0),(0,0)],[],2,no=5,nm=9,nw=4,post=[2]),
        ]
        # Invalid nodes/edges anywhere, reachable or not, and INVALID before CAPACITY/WORKSPACE.
        cases+=[case([(0,1),(1,1),(2,1)],[1,0,3],0,status=INVALID),                    # node 2 unreachable, bad target
                case([(0,1),(1,1),(5,1)],[1,0,2],0,status=INVALID),                    # node 2 first past edges
                case([(0,1),(1,1),(2,2)],[1,0,2],0,status=INVALID),                    # node 2 count past edges
                case([(0,1),(2,0)],[1],0,status=INVALID),                              # count 0 but first past edges
                case([(0,1),(NONE,2)],[0],0,status=INVALID),case([(0,1),(1,NONE)],[0,0],0,status=INVALID),
                case([(0,1)],[NONE],0,status=INVALID),case([(0,1)],[1],0,status=INVALID),
                case([(0,1)],[0],1,status=INVALID),case([],[],0,status=INVALID),case([(0,0)],[],NONE,status=INVALID),
                case([(0,1),(1,0)],[5],0,no=0,nm=0,nw=0,status=INVALID)]
        # Fixed thresholds: out/marks/work are measured against nodes.len, not the reachable count.
        for n in (1,2,5,33):
            nodes=[(i,1)for i in range(n)];edges=[(i+1)%n for i in range(n)]
            cases+=[case(nodes,edges,0,status=OK),case(nodes,edges,0,no=n-1,status=CAPACITY),
                    case(nodes,edges,0,nm=n-1,status=WORKSPACE),case(nodes,edges,0,nw=n-1,status=WORKSPACE),
                    case(nodes,edges,0,nm=n-1,nw=n-1,status=WORKSPACE),case(nodes,edges,0,no=n-1,nm=0,nw=0,status=CAPACITY),
                    case(nodes,edges,0,no=n+9,nm=n+7,nw=n+5,status=OK)]
        cases+=[case([(0,0),(0,0),(0,0)],[],0,no=1,status=CAPACITY),case([(0,0),(0,0),(0,0)],[],0,nm=1,status=WORKSPACE),
                case([(0,0),(0,0),(0,0)],[],0,nw=1,status=WORKSPACE)]
        # Seeded graphs made INVALID only through an unreachable node.
        rng=random.Random(0xC19BAD);bad=0
        for i in range(60):
            n=rng.randint(2,30);nodes,edges=random_graph(rng,n,1.0);entry=rng.randrange(n)
            good=case(nodes,edges,entry,status=OK);reached=set(good['expected'][1])
            victims=[v for v in range(n)if v not in reached and nodes[v][1]]
            if victims and i%2:
                v=rng.choice(victims);edges=list(edges);edges[nodes[v][0]+rng.randrange(nodes[v][1])]=n+rng.randrange(5)
            elif i%3==0:
                nodes=nodes+[(len(edges)+1+rng.randrange(3),0)]            # new unreachable node, first past edges
            else:
                nodes=nodes+[(len(edges),1)];edges=edges+[n+1+rng.randrange(4)] # new unreachable node, bad target
            cases+=[good,case(nodes,edges,entry,no=0,status=INVALID)];bad+=1
        self.run_both(cases,'bounds')
        self.records.append(dict(test='cycles-invalid-workspace',cases=len(cases),unreachable_bad=bad,
            native_preflights=self.PREFLIGHTS,modes=2,passed=True))

    def bad_build(self,name,edits):
        source=SOURCE.read_text(encoding='utf-8')
        for old,new in edits:
            self.assertEqual(source.count(old),1,(name,old));source=source.replace(old,new,1)
        root=self.work/name;(root/'src/bootstrap').mkdir(parents=True);(root/'wrapper/probe').mkdir(parents=True)
        (root/'src/bootstrap/cfg_postorder.dg').write_text(source,encoding='utf-8')
        (root/'wrapper/probe/cfg_postorder_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root/'src',ROOT/'lang',root/'wrapper'],root/'wrapper',mode,name+'-'+mode)
                for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        diamond=case([(0,2),(2,1),(3,1),(4,0)],[1,2,3,3],0,post=[3,1,2,0])
        controls=[
            # Emits each node when it is discovered (preorder) instead of after its children.
            ('bad-pre-emit',[('var top:usize=1;var count:usize=0;','var top:usize=1;out[0]=entry;var count:usize=1;'),
                             ('if marks[t]==0{marks[t]=1;','if marks[t]==0{marks[t]=1;out[count]=t;count+=1;'),
                             ('marks[v]=2;out[count]=v;count+=1;top-=1;','marks[v]=2;top-=1;')],
             [diamond,case([(0,3),(3,1),(4,0),(4,0)],[1,2,3,2],0,post=[2,1,3,0])],"'post-order'"),
            # Re-enters an on-stack node through a back edge (pushes a fresh frame for it), so it is emitted twice.
            ('bad-reenter-stack',[('if marks[t]==0{marks[t]=1;work[top].node=t;work[top].next=nodes[t].first;top+=1;}',
                                   'if marks[t]!=2{work[top].node=t;work[top].next=nodes[t].first;'
                                   'if marks[t]==1{work[top].next=nodes[t].first+nodes[t].count;}marks[t]=1;top+=1;}')],
             [case([(0,2),(2,1),(3,0)],[1,2,0],0,no=8,nm=8,nw=8,post=[1,2,0])],"'used-count'"),
            # Validates only node 0, so a bad edge in an unreachable node slips through.
            ('bad-reachable-only',[('while k<nodes.len{','while k<1{')],
             [case([(0,1),(1,1),(2,1)],[1,0,7],0,status=INVALID)],"'status-code'"),
            # Clears marks before the workspace check.
            ('bad-early-marks',[('if marks.len<n||work.len<n{return WORKSPACE;}',
                                 'var z:usize=0;while z<marks.len{marks[z]=0;z+=1;}if marks.len<n||work.len<n{return WORKSPACE;}')],
             [case([(0,1),(1,1),(2,1)],[1,2,0],0,nw=2,status=WORKSPACE)],"'guard/atomicity'"),
        ]
        for name,edits,cases,reason in controls:
            # The real source passes the exact control cases first (preflight skipped: a wrong
            # source could corrupt the alias-positive fixtures, and that exit must not count).
            self.run_both(cases,name+'-good',preflight=False)
            for mode,exe in self.bad_build(name,edits).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode,preflight=False)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason.strip("'")))


if __name__=='__main__':unittest.main()
