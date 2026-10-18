"""Actual Dong constant evaluation over native Dong lexer/parser ASTs, against Python integers."""
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import unittest
import uuid

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'lang/bootstrap/constant_arithmetic.dg'
DEPENDENCIES=[ROOT/'lang/bootstrap'/name for name in
              ('lexer.dg','unicode.dg','expression.dg','bigint.dg','bigint_div.dg','bigint_bits.dg')]
OK,INVALID,CAPACITY,WORKSPACE,DIVZERO,TYPE,SHIFT,UNSUPPORTED,DEPTH=range(9)
NONE=2**64-1
# Temporary export wrapper; the module itself exports nothing.
WRAPPER='''module probe.const_export;
import bootstrap.lexer as lex;
import bootstrap.expression as ex;
import bootstrap.constant_arithmetic as k;
export("dong_const_eval") pub unsafe fn eval(source:*const u8,length:usize,tokens:*const lex.Token,count:usize,
 nodes:*const ex.Node,used:usize,root:usize,out:*u32,capacity:usize,work:*u32,workspace:usize,max_depth:usize,result:*k.Value)u64{unsafe{
 return k.evaluate(slice_from_raw_parts(source,length),slice_from_raw_parts(tokens,count),slice_from_raw_parts(nodes,used),root,
  slice_from_raw_parts(out,capacity),slice_from_raw_parts(work,workspace),max_depth,result);
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
typedef struct {uint64_t kind,start,end,line,column,value_start,value_length;} Token;
typedef struct {uint64_t kind,token,op,a,b,c,next,flags;} Node;
typedef struct {uint64_t count,used,error_code,error_start,error_line,error_column;} LexResult;
typedef struct {uint64_t root,used,next,error_code,error_token;} ParseResult;
typedef struct {uint64_t kind;uint8_t negative,padding[7];uint64_t used;} Value;
_Static_assert(sizeof(Token)==56&&sizeof(Node)==64,"AST layout");
_Static_assert(sizeof(Value)==24&&__builtin_offsetof(Value,negative)==8&&__builtin_offsetof(Value,used)==16,"Value layout");
extern uint64_t ABI dong_bootstrap_lex(const uint8_t*,uint64_t,Token*,uint64_t,uint8_t*,uint64_t,LexResult*);
extern uint64_t ABI dong_bootstrap_expression(const uint8_t*,uint64_t,const Token*,uint64_t,uint64_t,Node*,uint64_t,uint64_t,uint8_t,ParseResult*);
extern uint64_t ABI dong_const_eval(const uint8_t*,uint64_t,const Token*,uint64_t,const Node*,uint64_t,uint64_t,uint32_t*,uint64_t,uint32_t*,uint64_t,uint64_t,Value*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static void*readonly_alloc(uint64_t n){
#ifdef _WIN32
 return VirtualAlloc(NULL,n,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*p=mmap(NULL,n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return p==MAP_FAILED?NULL:p;
#endif
}
static void readonly_protect(void*p,uint64_t n){
#ifdef _WIN32
 DWORD old;if(!VirtualProtect(p,n,PAGE_READONLY,&old))exit(98);
#else
 if(mprotect(p,n,PROT_READ))exit(98);
#endif
}
static void readonly_free(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;VirtualFree(p,0,MEM_RELEASE);
#else
 munmap(p,n);
#endif
}
/* Build one parsed AST of "1+2" and reject bad descriptors with every byte unchanged. */
static unsigned invalid(void){
 static uint8_t arena[16384];static uint8_t saved[16384];const unsigned total=22;
 uint8_t*src=arena;Token*tok=(Token*)(arena+64);Node*nodes=(Node*)(arena+1024);
 uint32_t*out=(uint32_t*)(arena+4096);uint32_t*work=(uint32_t*)(arena+8192);Value*v=(Value*)(arena+12288);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(src,"1+2",3);
  LexResult lr;ParseResult pr;uint8_t strings[8];
  if(dong_bootstrap_lex(src,3,tok,8,strings,8,&lr)||dong_bootstrap_expression(src,3,tok,lr.count,0,nodes,16,64,1,&pr))exit(99);
  memcpy(saved,arena,sizeof(arena));uint64_t s=0,c=lr.count,u=pr.used,r=pr.root;
  switch(i){
   case 0:s=dong_const_eval(NULL,3,tok,c,nodes,u,r,out,8,work,64,16,v);break;
   case 1:s=dong_const_eval(src,3,(Token*)((uint8_t*)tok+4),c,nodes,u,r,out,8,work,64,16,v);break;
   case 2:s=dong_const_eval(src,3,tok,c,(Node*)((uint8_t*)nodes+4),u,r,out,8,work,64,16,v);break;
   case 3:s=dong_const_eval(src,3,tok,c,nodes,u,r,(uint32_t*)((uint8_t*)out+2),8,work,64,16,v);break;
   case 4:s=dong_const_eval(src,3,tok,c,nodes,u,r,out,8,(uint32_t*)((uint8_t*)work+1),64,16,v);break;
   case 5:s=dong_const_eval(src,3,tok,c,nodes,u,r,out,8,work,64,16,NULL);break;
   case 6:s=dong_const_eval(src,3,tok,c,nodes,u,r,out,8,work,64,16,(Value*)((uint8_t*)v+4));break;
   case 7:s=dong_const_eval(src,3,tok,c,nodes,u,r,out,8,out+4,64,16,v);break;
   case 8:s=dong_const_eval(src,3,tok,c,nodes,u,r,(uint32_t*)src,8,work,64,16,v);break;
   case 9:s=dong_const_eval(src,3,tok,c,nodes,u,r,(uint32_t*)tok,8,work,64,16,v);break;
   case 10:s=dong_const_eval(src,3,tok,c,nodes,u,r,out,8,(uint32_t*)nodes,64,16,v);break;
   case 11:s=dong_const_eval(src,3,tok,c,nodes,u,r,out,8,work,64,16,(Value*)work);break;
   case 12:s=dong_const_eval(src,3,tok,c,nodes,u,u,out,8,work,64,16,v);break;
   case 13:s=dong_const_eval(src,3,tok,c,nodes,u,r,out,8,work,64,0,v);break;
   case 14:s=dong_const_eval(src,3,tok,c,nodes,u,r,out,8,work,64,257,v);break;
   case 15:s=dong_const_eval(src,3,tok,UINT64_MAX,nodes,u,r,out,8,work,64,16,v);break;
   case 16:s=dong_const_eval(src,3,tok,c,nodes,UINT64_MAX/8,r,out,8,work,64,16,v);break;
   case 17:s=dong_const_eval((void*)(uintptr_t)(UINT64_MAX-1),3,tok,c,nodes,u,r,out,8,work,64,16,v);break;
   case 18:s=dong_const_eval(src,3,tok,c,nodes,u,r,out,UINT64_MAX/4+1,work,64,16,v);break;
   case 19:s=dong_const_eval(src,3,tok,c,nodes,u,r,out,8,work,64,16,(Value*)src);break;
   case 20:s=dong_const_eval(src,3,tok,c,nodes,u,r,out,8,(uint32_t*)((uint8_t*)tok+40),64,16,v);break;
   default:s=dong_const_eval(src,3,tok,c,nodes,u,NONE_ROOT,out,8,work,64,16,v);break;
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
  uint64_t h[8];read_exact(h,sizeof(h));uint64_t n=h[0],cap=h[1],wc=h[2],depth=h[3],root=h[4],np=h[5],ro=h[6];
  if(n>1000000||cap>200000||wc>400000||np>16)exit(94);
  uint64_t tcap=n+2,ncap=n+2;
  uint8_t*src=malloc(n+64);Token*tok=malloc(tcap*sizeof(Token));uint8_t*strings=malloc(n+1);Node*nodes=malloc(ncap*sizeof(Node));
  uint32_t*out=malloc((cap+8)*4),*work=malloc((wc+8)*4);uint64_t patch[48];
  if(!src||!tok||!strings||!nodes||!out||!work)exit(95);
  memset(src,0xa5,n+64);read_exact(src+32,n);read_exact(patch,np*24);
  LexResult lr;ParseResult pr;memset(&pr,0,sizeof(pr));
  uint64_t ls=dong_bootstrap_lex(src+32,n,tok,tcap,strings,n+1,&lr),ps=99;
  uint64_t response[8]={ls,99,99,0,0,0,0,0};
  if(!ls){
   ps=dong_bootstrap_expression(src+32,n,tok,lr.count,0,nodes,ncap,256,1,&pr);response[1]=ps;
   if(!ps&&pr.next+1!=lr.count)response[1]=ps=98; /* whole source must be one expression */
  }
  if(!ls&&!ps){
   for(uint64_t i=0;i<np;i++){uint64_t*f=(uint64_t*)&nodes[patch[3*i]];f[patch[3*i+1]]=patch[3*i+2];}
   if(root==UINT64_MAX)root=pr.root;else if(root==UINT64_MAX-1)root=pr.used;
   uint64_t tb=lr.count*sizeof(Token),nb=pr.used*sizeof(Node);
   const uint8_t*s=src+32;const Token*t=tok;const Node*d=nodes;uint8_t*page=NULL;uint64_t pages=0;
   uint8_t*copy=malloc(n+tb+nb+1);if(!copy)exit(95);memcpy(copy,src+32,n);memcpy(copy+n,tok,tb);memcpy(copy+n+tb,nodes,nb);
   if(ro){pages=((tb+nb+n+64)/4096+1)*4096;page=readonly_alloc(pages);if(!page)exit(95);
    memcpy(page,tok,tb);memcpy(page+tb,nodes,nb);memcpy(page+tb+nb,src+32,n);readonly_protect(page,pages);
    t=(const Token*)page;d=(const Node*)(page+tb);s=page+tb+nb;}
   memset(out,0xa5,(cap+8)*4);memset(work,0xa5,(wc+8)*4);
   uint64_t meta[7];memset(meta,0xa5,sizeof(meta));Value*v=(Value*)(meta+2);
   uint64_t status=dong_const_eval(s,n,t,lr.count,d,pr.used,root,out+4,cap,work+4,wc,depth,v);
   uint64_t valid=filled(src,32)&&filled(src+32+n,32)&&!memcmp(copy,s,n)&&!memcmp(copy+n,t,tb)&&!memcmp(copy+n+tb,d,nb)&&
     filled(out,16)&&filled(out+4+cap,16)&&filled(work,16)&&filled(work+4+wc,16)&&filled(meta,16)&&filled(meta+5,16);
   if(status)valid=valid&&filled(out+4,cap*4)&&filled(v,24);
   if(status==1||status==5||status==7||status==8)valid=valid&&filled(work+4,wc*4);
   if(!status)valid=valid&&v->used<=cap&&v->negative<=1&&(v->kind==1||v->kind==2)&&filled(out+4+v->used,(cap-v->used)*4)&&
     (v->used?out[4+v->used-1]!=0:!v->negative)&&(v->kind==1||(!v->negative&&v->used<=1&&(!v->used||out[4]==1)));
   response[2]=status;response[3]=status?0:v->kind;response[4]=status?0:v->negative;response[5]=status?0:v->used;
   response[6]=valid;response[7]=pr.used;
   if(page){readonly_free(page,pages);}free(copy);
  }
  write_exact(response,sizeof(response));write_exact(out+4,(!ls&&!ps)?cap*4:0);
  free(src);free(tok);free(strings);free(nodes);free(out);free(work);
 }return 0;
}
'''.replace('NONE_ROOT','UINT64_MAX')


def limbs(n):
    n=abs(int(n));out=[]
    while n:out.append(n&0xffffffff);n>>=32
    return out


def used(x):return len(limbs(x))


# ---- Independent Python reference over a Python-side tree (rendered to Dong source) ----
# ('int',value,text) ('bool',b) ('un',op,child) ('bin',op,l,r) ('raw',text)
INT_OPS=['+','-','*','/','%','&','|','^','<<','>>']
CMP_OPS=['==','!=','<','<=','>','>=']


def render(n):
    tag=n[0]
    if tag=='int':return n[2]
    if tag=='bool':return 'true'if n[1]else'false'
    if tag=='raw':return n[1]
    if tag=='un':return n[1]+'('+render(n[2])+')'
    return '('+render(n[2])+' '+n[1]+' '+render(n[3])+')'


def literal(value,rng=None):
    text=str(value)
    if rng:
        style=rng.randrange(4)
        if style==1:text=hex(value)
        elif style==2:text=bin(value)
        elif style==3 and len(text)>3:text=text[0]+'_'+text[1:]
    return ('int',value,text)


class Failure(Exception):
    def __init__(self,status):self.status=status


def typing(n):
    tag=n[0]
    if tag=='int':return 'i'
    if tag=='bool':return 'b'
    if tag=='raw':raise Failure(UNSUPPORTED)
    if tag=='un':
        inner=typing(n[2])
        if (n[1]=='!')!=(inner=='b'):raise Failure(TYPE)
        return inner
    left,right=typing(n[2]),typing(n[3]);op=n[1]
    if op in('&&','||'):
        if left!='b'or right!='b':raise Failure(TYPE)
        return 'b'
    if op in('==','!='):
        if left!=right:raise Failure(TYPE)
        return 'b'
    if left!='i'or right!='i':raise Failure(TYPE)
    return 'b'if op in CMP_OPS else 'i'


def truncdiv(a,b):
    q=abs(a)//abs(b)
    return -q if (a<0)!=(b<0) else q


class Machine:
    """Value semantics are plain Python integers; only the scratch reservation rules
    documented in constant_arithmetic.md are mirrored, to predict WORKSPACE exactly."""
    def __init__(self,wc):self.wc=wc;self.peak=0
    def room(self,start,n):
        self.peak=max(self.peak,start+n)
        if start+n>self.wc:raise Failure(WORKSPACE)
    def boolean(self,base,truth):
        if truth:self.room(base,1)
        return bool(truth)
    def ev(self,n,base):
        tag=n[0]
        if tag=='int':
            cap=len(n[2])//8+1;self.room(base,2*cap);return n[1]
        if tag=='bool':return self.boolean(base,n[1])
        if tag=='un':
            v=self.ev(n[2],base)
            if n[1]=='-':return -v
            if n[1]=='!':return self.boolean(base,not v)
            at=base+used(v);self.room(at,2*(used(v)+1));return ~v
        op=n[1];a=self.ev(n[2],base)
        if op=='&&':return a and self.ev(n[3],base)
        if op=='||':return a or self.ev(n[3],base)
        rb=base+used(a);b=self.ev(n[3],rb);at=rb+used(b);la,lb=used(a),used(b)
        if op in CMP_OPS:
            return self.boolean(base,{'==':a==b,'!=':a!=b,'<':a<b,'<=':a<=b,'>':a>b,'>=':a>=b}[op])
        if op in('/','%'):
            if b==0:raise Failure(DIVZERO)
            self.room(at,la+2*la+2);q=truncdiv(a,b);return q if op=='/'else a-q*b
        if op in('<<','>>'):
            if b<0 or lb>2:raise Failure(SHIFT)
            if op=='<<':
                cap=la+b//32+1 if la else 0;self.room(at,2*cap);return a<<b if a else 0
            self.room(at,la+la+1);return a>>b
        w=max(la,lb)+1
        if op=='*':self.room(at,2*(la+lb));return a*b
        self.room(at,2*w)
        return {'+':a+b,'-':a-b,'&':a&b,'|':a|b,'^':a^b}[op]


def reference(n,cap=None,wc=None):
    """Returns (status, kind, value, exact_peak)."""
    try:kind=typing(n)
    except Failure as f:return f.status,None,None,0
    m=Machine(float('inf')if wc is None else wc)
    try:value=m.ev(n,0)
    except Failure as f:return f.status,None,None,m.peak
    value=int(value);need=used(value)
    if cap is not None and need>cap:return CAPACITY,None,None,m.peak
    return OK,kind,value,m.peak


def item(n,cap=None,wc=None,depth=256,status=None,patches=(),root=NONE,readonly=0,source=None):
    """One harness case. With status None, status/value come from the Python reference."""
    text=(source if source is not None else render(n)).encode()
    if status is None:
        _,_,value,peak=reference(n,wc=wc)
        if wc is None:wc=peak
        if cap is None:cap=used(value)if value is not None else 4
        status,kind,value,_=reference(n,cap,wc)
    else:
        kind=value=None
        if wc is None:wc=64
        if cap is None:cap=4
    return dict(text=text,cap=cap,wc=wc,depth=depth,root=root,patches=list(patches),readonly=readonly,
                status=status,kind=kind,value=value)


def generate(rng,kind,depth,big=False):
    if depth==0 or rng.random()<0.25:
        if kind=='b':return ('bool',rng.random()<0.5)
        bits=rng.choice([1,8,31,32,33,64,65,128,512,4096]if big else[1,8,31,32,33,64,65,100])
        return literal(rng.getrandbits(bits),rng)
    if kind=='b':
        r=rng.random()
        if r<0.3:return ('un','!',generate(rng,'b',depth-1,big))
        if r<0.6:return ('bin',rng.choice(['&&','||']),generate(rng,'b',depth-1,big),generate(rng,'b',depth-1,big))
        if r<0.7:return ('bin',rng.choice(['==','!=']),generate(rng,'b',depth-1,big),generate(rng,'b',depth-1,big))
        return ('bin',rng.choice(CMP_OPS),generate(rng,'i',depth-1,big),generate(rng,'i',depth-1,big))
    r=rng.random()
    if r<0.15:return ('un',rng.choice('-~'),generate(rng,'i',depth-1,big))
    op=rng.choice(INT_OPS)
    if op in('<<','>>'):
        amount=rng.choice([0,1,31,32,33,63,64,65,rng.randrange(0,300)])
        right=literal(amount,rng)if rng.random()<0.8 else ('un','-',literal(rng.randrange(1,5)))
        return ('bin',op,generate(rng,'i',depth-1,big),right)
    return ('bin',op,generate(rng,'i',depth-1,big),generate(rng,'i',depth-1,big))


class BootstrapConstantArithmeticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native constant evaluation requires NASM/GCC')
        cls.work=ROOT/'build/test/claude-c3'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in
                    [SOURCE,*DEPENDENCIES,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/const_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=180)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/const_export.dg',roots=roots,mode=mode)
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
            records=cls.records,L3_selfhost_complete=False,names_types_layout_supported=False,OS_VM_built=False),indent=2)+'\n')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:
            payload.extend(struct.pack('<8Q',len(c['text']),c['cap'],c['wc'],c['depth'],c['root'],len(c['patches']),c['readonly'],0))
            payload.extend(c['text'])
            for p in c['patches']:payload.extend(struct.pack('<3Q',*p))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=300)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,22)
        offset=8
        for index,c in enumerate(cases):
            ls,ps,status,kind,negative,count,guard,_=struct.unpack_from('<8Q',run.stdout,offset);offset+=64
            self.assertEqual((ls,ps),(0,0),(label,index,'native lexer/parser',c['text'][:80]))
            words=struct.unpack_from('<'+'I'*c['cap'],run.stdout,offset);offset+=c['cap']*4
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity',c['text'][:80]))
            self.assertEqual(status,c['status'],(label,index,'status',c['text'][:80]))
            if not status:
                value=sum(w<<(32*i)for i,w in enumerate(words[:count]))*(-1 if negative else 1)
                self.assertEqual(kind,1 if c['kind']=='i'else 2,(label,index,'kind'))
                self.assertEqual(value,int(c['value']),(label,index,'value',c['text'][:80]))
        self.assertEqual(offset,len(run.stdout))
        return len(cases)

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def test_random_trees_against_python(self):
        rng=random.Random(0xC3C0457);cases=[];statuses={}
        for i in range(700):
            n=generate(rng,rng.choice('iib'),rng.randint(1,6),big=i%3==0)
            c=item(n,readonly=int(i%50==0));cases.append(c);statuses[c['status']]=statuses.get(c['status'],0)+1
        self.run_both(cases,'random')
        self.assertGreater(statuses.get(OK,0),400,statuses)
        self.records.append(dict(test='random-trees',cases=len(cases),seed='0xC3C0457',statuses=statuses,modes=2,passed=True))

    def test_operations_signs_shifts_and_short_circuit(self):
        cases=[];B=2**4096-12345;S=[0,1,7,2**32-1,2**32,2**64+3,B]
        for x in S:
            for y in S:
                for sx in (1,-1):
                    for sy in (1,-1):
                        a=('un','-',literal(x))if sx<0 else literal(x);b=('un','-',literal(y))if sy<0 else literal(y)
                        for op in INT_OPS[:7]+CMP_OPS:cases.append(item(('bin',op,a,b)))
        for x in (0,1,3,4,2**64-1,2**64,B):
            for neg in (False,True):
                a=('un','-',literal(x))if neg else literal(x)
                cases+= [item(('un','~',a)),item(('un','-',a))]
                for k in (0,1,31,32,33,63,64,65,4095,4096,5000):
                    cases+=[item(('bin','<<',a,literal(k))),item(('bin','>>',a,literal(k)))]
                for k in (2**32,2**63,2**64-1):cases.append(item(('bin','>>',a,literal(k))))
                cases.append(item(('bin','<<',a,literal(2**64-1)),wc=4096))     # zero ok, nonzero WORKSPACE
                cases+=[item(('bin','<<',a,('un','-',literal(1)))),item(('bin','>>',a,literal(2**64))),
                        item(('bin','<<',a,literal(2**70)))]                      # SHIFT
        for src,expected in [('-4 >> 1',-2),('-3 >> 1',-2),('-1 >> 100',-1),('1 << 4096',2**4096),
                             ('7 / -2',-3),('-7 / 2',-3),('-7 % 2',-1),('7 % -2',1),('~0',-1),('~-1',0),
                             ('1 + 2 * 3',7),('(1 + 2) * 3',9),('1 << 2 + 1',8),('6 & 3 | 8',10),('5 ^ 3 & 1',4),
                             ('-2 * -3',6),('0x_FF'if False else '0xff + 0b101',260),('1_000 - 1',999)]:
            n=('raw',src);cases.append(dict(text=src.encode(),cap=used(expected)+1,wc=1024,depth=256,root=NONE,patches=[],
                                         readonly=0,status=OK,kind='i',value=expected))
        for src,value in [('true && false',0),('false || true',1),('!true',0),('!(1 < 2)',0),('true == !false',1),
                          ('false != false',0),('1 < 2 && 2 < 1 || 3 >= 3',1),('false && 1 / 0 == 0',0),
                          ('true || 1 << -1 == 0',1),('false && (1 << 99999999999) == 0',0)]:
            cases.append(dict(text=src.encode(),cap=1,wc=16,depth=256,root=NONE,patches=[],readonly=0,status=OK,kind='b',value=value))
        for src,status in [('true && 1 / 0 == 0',DIVZERO),('false || 1 >> -1 == 0',SHIFT),('1 % (2 - 2)',DIVZERO),
                           ('false && (1 + true) == 0',TYPE),('1 + true',TYPE),('!1',TYPE),('-true',TYPE),('~false',TYPE),
                           ('true < false',TYPE),('1 == true',TYPE),('1 && 2',TYPE),('true + 1',TYPE),('true << 1',TYPE)]:
            cases.append(item(None,source=src,status=status))
        self.run_both(cases,'operations')
        self.records.append(dict(test='operations-signs-shifts-short-circuit',cases=len(cases),modes=2,passed=True))

    def test_unsupported_capacity_workspace_depth_and_invalid_trees(self):
        cases=[]
        for src in ['x','1 + y','null','"s"','f(1)','a.b','a[1]','a[1..2]','(1 as u8)','sizeof(u8)','[1, 2]','[0; 4]',
                    'try f()','&x','*p','x orelse 1','S{a: 1}','-x','false && x','true || f()','error.E',
                    '1 + (2 as u64)','!f()','(x) == 1']:
            cases.append(item(None,source=src,status=UNSUPPORTED))
        cases.append(item(None,source='x + true',status=UNSUPPORTED))           # left-to-right: UNSUPPORTED first
        cases.append(item(None,source='(1 + true) + x',status=TYPE))
        rng=random.Random(0xC3CA9);exact=0
        for i in range(120):
            n=generate(rng,'i',rng.randint(1,5),big=i%2==0);status,_,value,peak=reference(n)
            if status!=OK:continue
            need=used(value);exact+=1
            cases+=[item(n),item(n,cap=need+3,wc=peak+5)]
            if need:cases+=[item(n,cap=need-1),item(n,cap=need-1,wc=peak-1)]
            if peak:cases.append(item(n,wc=peak-1))
        cases+=[item(literal(0),cap=0,wc=2),item(('bool',False),cap=0,wc=0),item(('bool',True),cap=0,wc=1),
                item(('bool',True),cap=1,wc=0)]
        # Depth: a left-associated chain has tree depth = terms; parenthesis-free so the parser stays shallow.
        chain=lambda k:' + '.join(['1']*k)
        for k,limit,status in [(2,2,OK),(3,2,DEPTH),(256,256,OK),(257,256,DEPTH),(400,256,DEPTH),(1,1,OK),(2,1,DEPTH)]:
            cases.append(dict(text=chain(k).encode(),cap=2,wc=64,depth=limit,root=NONE,patches=[],readonly=0,
                              status=status,kind='i',value=k))
        # Tampered parser output: indices, token kinds, op mismatch, sharing and cycles must be INVALID (or DEPTH).
        # "1 + 2" parses as nodes 0:INTEGER 1:INTEGER 2:BINARY(a=0,b=1).
        base=dict(text=b'1 + 2',cap=2,wc=64,depth=16,root=NONE,readonly=0,kind=None,value=None)
        for patches,status in [([(2,3,3)],INVALID),([(2,4,NONE)],INVALID),([(2,1,99)],INVALID),([(0,1,1)],INVALID),
                               ([(2,2,1066)],INVALID),([(2,2,1067),(2,1,2)],INVALID),([(2,4,0)],INVALID),
                               ([(2,3,2)],INVALID),([(2,0,8),(2,2,285)],INVALID),([(0,0,2)],INVALID),([(2,3,1),(2,4,0)],INVALID)]:
            cases.append(dict(base,patches=patches,status=status))
        cases.append(dict(base,patches=[(2,3,2)],depth=3,status=INVALID))       # self-cycle rejected by layout order
        cases.append(dict(base,root=NONE-1,patches=[],status=INVALID))         # root == nodes.len
        cases+=[dict(base,patches=[],status=OK,kind='i',value=3,readonly=1),
                item(None,source='1 / 0',status=DIVZERO,wc=64),
                dict(item(generate(random.Random(5),'i',5,big=True)),readonly=1)]
        self.run_both(cases,'bounds')
        self.records.append(dict(test='unsupported-capacity-workspace-depth-invalid',cases=len(cases),exact_trees=exact,
                                 invalid_preflights_per_native=22,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        (root/'bootstrap/constant_arithmetic.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/const_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            ('bad-sub-as-add','else if op==1069{s=big.calculate(big.SUB,','else if op==1069{s=big.calculate(big.ADD,',
             [item(('bin','-',literal(10),literal(3)))],'value'),
            ('bad-negative-compare','if na{return -r;}return r;','return r;',
             [item(('bin','<',('un','-',literal(5)),('un','-',literal(3))))],'value'),
            ('bad-eager-and','if (op==518&&a.used==0)||(op==519&&a.used!=0){*v=a;return OK;}','',
             [item(None,source='false && 1 / 0 == 0',status=OK)|dict(kind='b',value=0,cap=1,wc=16)],'status'),
            ('bad-early-publish','if v.used>out.len{return CAPACITY;}\n var i:usize=0;while i<v.used{out[i]=work[i];i+=1;}',
             ' var i:usize=0;while i<v.used&&i<out.len{out[i]=work[i];i+=1;}\n if v.used>out.len{return CAPACITY;}',
             [item(literal(2**200),cap=1)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
