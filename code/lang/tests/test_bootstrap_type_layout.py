"""Actual Dong type layout engine, against an independent Python reference and the host typesys."""
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
from lang.dongc.frontend import Parser,lex
from lang.dongc.typesys import TypeSystem
from lang.tests.test_dongc import tool,nasm_flags

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'lang/bootstrap/type_layout.dg'
HOST=ROOT/'lang/dongc/typesys.py'
OK,INVALID,CAPACITY,CYCLE,OVERFLOW,ALIGNMENT,DEPTH=range(7)
U8,U16,U32,U64,BOOL,POINTER,FUNCTION,SLICE,OPTIONAL,RESULT,ARRAY,STRUCT,ENUM=range(1,14)
NONE=2**64-1
MAX_SIZE=2**63-1
WRAPPER='''module probe.layout_export;
import bootstrap.type_layout as k;
export("dong_type_layout") pub unsafe fn layout(types:*const k.Type,nt:usize,fields:*const k.Field,nf:usize,
 layouts:*k.Layout,nl:usize,offsets:*usize,no:usize,work:*k.Layout,nw:usize,work_offsets:*usize,nx:usize,
 states:*u8,ns:usize,max_depth:usize)u64{unsafe{
 return k.calculate(slice_from_raw_parts(types,nt),slice_from_raw_parts(fields,nf),slice_from_raw_parts(layouts,nl),
  slice_from_raw_parts(offsets,no),slice_from_raw_parts(work,nw),slice_from_raw_parts(work_offsets,nx),
  slice_from_raw_parts(states,ns),max_depth);
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
typedef struct {uint64_t kind,element,count,first,length,alignment;uint8_t packed,padding[7];} Type;
typedef struct {uint64_t size,alignment;} Layout;
_Static_assert(sizeof(Type)==56&&__builtin_offsetof(Type,packed)==48&&sizeof(Layout)==16,"layout ABI");
extern uint64_t ABI dong_type_layout(const Type*,uint64_t,const uint64_t*,uint64_t,Layout*,uint64_t,uint64_t*,uint64_t,
 Layout*,uint64_t,uint64_t*,uint64_t,uint8_t*,uint64_t,uint64_t);
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
/* Bad descriptors: INVALID with every byte of the arena unchanged. */
static unsigned invalid(void){
 static uint8_t arena[8192],saved[8192];const unsigned total=24;
 Type*t=(Type*)arena;uint64_t*f=(uint64_t*)(arena+512);Layout*l=(Layout*)(arena+1024);uint64_t*o=(uint64_t*)(arena+2048);
 Layout*w=(Layout*)(arena+3072);uint64_t*x=(uint64_t*)(arena+4096);uint8_t*s=arena+5120;
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memset(t,0,2*sizeof(Type));
  t[0].kind=12;t[0].element=UINT64_MAX;t[0].first=0;t[0].length=1;t[1].kind=4;t[1].element=UINT64_MAX;f[0]=1;
  memcpy(saved,arena,sizeof(arena));uint64_t r=0;
  switch(i){
   case 0:r=dong_type_layout(NULL,2,f,1,l,8,o,8,w,8,x,8,s,8,16);break;
   case 1:r=dong_type_layout((Type*)(arena+4),2,f,1,l,8,o,8,w,8,x,8,s,8,16);break;
   case 2:r=dong_type_layout(t,2,(uint64_t*)(arena+516),1,l,8,o,8,w,8,x,8,s,8,16);break;
   case 3:r=dong_type_layout(t,2,f,1,(Layout*)(arena+1028),8,o,8,w,8,x,8,s,8,16);break;
   case 4:r=dong_type_layout(t,2,f,1,l,8,(uint64_t*)(arena+2052),8,w,8,x,8,s,8,16);break;
   case 5:r=dong_type_layout(t,2,f,1,l,8,o,8,(Layout*)(arena+3076),8,x,8,s,8,16);break;
   case 6:r=dong_type_layout(t,2,f,1,l,8,o,8,w,8,(uint64_t*)(arena+4100),8,s,8,16);break;
   case 7:r=dong_type_layout(t,2,f,1,(Layout*)t,8,o,8,w,8,x,8,s,8,16);break;
   case 8:r=dong_type_layout(t,2,f,1,l,8,f,8,w,8,x,8,s,8,16);break;
   case 9:r=dong_type_layout(t,2,f,1,l,8,o,8,w,8,x,8,arena+8,8,16);break;
   case 10:r=dong_type_layout(t,2,f,1,l,8,o,8,l,8,x,8,s,8,16);break;
   case 11:r=dong_type_layout(t,2,f,1,l,8,o,8,w,8,o+4,8,s,8,16);break;
   case 12:r=dong_type_layout(t,2,f,1,l,8,o,8,w,8,x,8,(uint8_t*)w+120,8,16);break;
   case 13:r=dong_type_layout(t,2,f,1,l,8,o,8,w,8,x,8,s,8,0);break;
   case 14:r=dong_type_layout(t,2,f,1,l,8,o,8,w,8,x,8,s,8,257);break;
   case 15:r=dong_type_layout(t,UINT64_MAX,f,1,l,8,o,8,w,8,x,8,s,8,16);break;
   case 16:r=dong_type_layout(t,2,f,UINT64_MAX/4,l,8,o,8,w,8,x,8,s,8,16);break;
   case 17:r=dong_type_layout(t,2,f,1,l,UINT64_MAX/8,o,8,w,8,x,8,s,8,16);break;
   case 18:r=dong_type_layout((void*)(uintptr_t)(UINT64_MAX-63),2,f,1,l,8,o,8,w,8,x,8,s,8,16);break;
   case 19:r=dong_type_layout(t,2,f,1,l,8,o,8,w,8,x,8,(uint8_t*)(uintptr_t)(UINT64_MAX-3),8,16);break;
   case 20:r=dong_type_layout(t,2,NULL,1,l,8,o,8,w,8,x,8,s,8,16);break;
   case 21:r=dong_type_layout(t,2,f,1,l,8,o,8,w,8,x,8,(uint8_t*)f,8,16);break;
   case 22:r=dong_type_layout(t,2,f,1,l,8,o,8,w,8,(uint64_t*)l+2,8,s,8,16);break;
   default:r=dong_type_layout(t,2,f,1,l,8,o,8,w,UINT64_MAX/16+1,x,8,s,8,16);break;
  }
  if(r!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)r);exit(93);}
 }
 /* NULL empty views are accepted. */
 if(dong_type_layout(NULL,0,NULL,0,NULL,0,NULL,0,NULL,0,NULL,0,NULL,0,1)){fprintf(stderr,"empty views\n");exit(96);}
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[10];read_exact(h,sizeof(h));
  uint64_t nt=h[0],nf=h[1],nl=h[2],no=h[3],nw=h[4],nx=h[5],ns=h[6],depth=h[7],ro=h[8];
  if(nt>100000||nf>100000||nl>100000||no>100000||nw>100000||nx>100000||ns>100000)exit(94);
  uint64_t tb=nt*sizeof(Type),fb=nf*8;
  uint8_t*in=malloc(tb+fb+64);Layout*l=malloc((nl+2)*16);uint64_t*o=malloc((no+4)*8);Layout*w=malloc((nw+2)*16);
  uint64_t*x=malloc((nx+4)*8);uint8_t*s=malloc(ns+32);uint8_t*copy=malloc(tb+fb+1);
  if(!in||!l||!o||!w||!x||!s||!copy)exit(95);
  memset(in,0xa5,tb+fb+64);read_exact(in+16,tb);read_exact(in+16+tb+16,fb);
  memcpy(copy,in+16,tb);memcpy(copy+tb,in+32+tb,fb);
  const Type*t=(const Type*)(in+16);const uint64_t*f=(const uint64_t*)(in+32+tb);uint8_t*page=NULL;uint64_t pages=0;
  if(ro){pages=((tb+fb)/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,tb);memcpy(page+tb,copy+tb,fb);
   ro_protect(page,pages);t=(const Type*)page;f=(const uint64_t*)(page+tb);}
  memset(l,0xa5,(nl+2)*16);memset(o,0xa5,(no+4)*8);memset(w,0xa5,(nw+2)*16);memset(x,0xa5,(nx+4)*8);memset(s,0xa5,ns+32);
  uint64_t r=dong_type_layout(t,nt,f,nf,l+1,nl,o+2,no,w+1,nw,x+2,nx,s+16,ns,depth);
  uint64_t valid=!memcmp(copy,t,tb)&&!memcmp(copy+tb,f,fb)&&(ro||(filled(in,16)&&filled(in+16+tb,16)&&filled(in+32+tb+fb,32)))&&
    filled(l,16)&&filled(l+1+nl,16)&&filled(o,16)&&filled(o+2+no,16)&&filled(w,16)&&filled(w+1+nw,16)&&
    filled(x,16)&&filled(x+2+nx,16)&&filled(s,16)&&filled(s+16+ns,16);
  if(r)valid=valid&&filled(l+1,nl*16)&&filled(o+2,no*8);
  if(r==1)valid=valid&&filled(w+1,nw*16)&&filled(x+2,nx*8)&&filled(s+16,ns);
  if(!r)valid=valid&&nt<=nl&&nf<=no&&filled(l+1+nt,(nl-nt)*16)&&filled(o+2+nf,(no-nf)*8);
  uint64_t response[2]={r,valid};write_exact(response,16);
  if(!r){write_exact(l+1,nt*16);write_exact(o+2,nf*8);}
  if(page)ro_free(page,pages);
  free(in);free(l);free(o);free(w);free(x);free(s);free(copy);
 }return 0;
}
'''


def T(kind,element=NONE,count=0,first=0,length=0,alignment=0,packed=0):
    return [kind,element,count,first,length,alignment,packed]


# ---- Independent Python reference (typesys rules, written from the task text) ----
SCALAR={U8:(1,1),U16:(2,2),U32:(4,4),U64:(8,8),BOOL:(1,1),POINTER:(8,8),FUNCTION:(8,8),
        SLICE:(16,8),OPTIONAL:(16,8),RESULT:(16,8)}


class Stop(Exception):
    def __init__(self,status):self.status=status


def metadata_ok(types,fields):
    n=len(types);owners=[]
    for kind,element,count,first,length,alignment,packed in types:
        if not 1<=kind<=13 or packed not in(0,1):return False
        if kind!=STRUCT and (alignment or packed):return False
        if kind!=ARRAY and count:return False
        if kind in(STRUCT,ENUM):
            if length==0 or first+length>len(fields) or element!=NONE:return False
            for f in range(first,first+length):
                if not(fields[f]<n or (kind==ENUM and fields[f]==NONE)):return False
            owners.append(set(range(first,first+length)))
        else:
            if first or length:return False
            if kind in(POINTER,SLICE,OPTIONAL,ARRAY):
                if element>=n:return False
            elif kind==RESULT:
                if element>=n and element!=NONE:return False
            elif element!=NONE:return False
            if kind==ARRAY and count==0:return False
    seen=set()
    for o in owners:
        if seen&o:return False
        seen|=o
    return True


def reference(types,fields,caps=None,depth=256):
    """Returns (status, layouts, offsets)."""
    n,m=len(types),len(fields)
    if not 1<=depth<=256 or not metadata_ok(types,fields):return INVALID,None,None
    nl,no,nw,nx,ns=caps if caps else (n,m,n,m,n)
    if nl<n or nw<n or ns<n or no<m or nx<m:return CAPACITY,None,None
    out=[None]*n;offsets=[0]*m;state=[0]*n
    def up(x,a):return -(-x//a)*a
    def go(i,d):
        if d>depth:raise Stop(DEPTH)
        if state[i]==2:return out[i]
        if state[i]==1:raise Stop(CYCLE)
        kind,element,count,first,length,alignment,packed=types[i]
        if kind in SCALAR:out[i]=SCALAR[kind]
        elif kind==ENUM:out[i]=(16 if any(fields[f]!=NONE for f in range(first,first+length))else 8,8)
        elif kind==ARRAY:
            state[i]=1;size,align=go(element,d+1)
            if count*size>MAX_SIZE:raise Stop(OVERFLOW)
            out[i]=(count*size,align)
        else:
            if alignment and (packed or alignment&(alignment-1) or alignment>4096):raise Stop(ALIGNMENT)
            state[i]=1;offset=0;align=1
            for f in range(first,first+length):
                size,a=go(fields[f],d+1);a=1 if packed else a
                offset=up(offset,a)
                if offset>MAX_SIZE:raise Stop(OVERFLOW)
                offsets[f]=offset;offset+=size
                if offset>MAX_SIZE:raise Stop(OVERFLOW)
                align=max(align,a)
            if alignment:
                if alignment<align:raise Stop(ALIGNMENT)
                align=alignment
            if up(offset,align)>MAX_SIZE:raise Stop(OVERFLOW)
            out[i]=(up(offset,align),align)
        state[i]=2;return out[i]
    try:
        for i in range(n):go(i,1)
    except Stop as s:return s.status,None,None
    return OK,out,offsets


def case(types,fields,caps=None,depth=256,readonly=0,status=None):
    n,m=len(types),len(fields);caps=caps or (n,m,n,m,n)
    expected=reference(types,fields,caps,depth)
    if status is not None:assert expected[0]==status,(status,expected[0],types,fields)
    return dict(types=types,fields=fields,caps=caps,depth=depth,readonly=readonly,expected=expected)


def random_graph(rng,size,host=False,cyclic=False):
    """Random descriptor graph. Value edges only point to lower indices unless cyclic."""
    types,fields=[],[]
    for i in range(size):
        lower=list(range(i))
        def pick(value=True,scalar=False):
            pool=lower if (value and not cyclic) else list(range(size))
            if scalar or not pool:return None
            return rng.choice(pool)
        r=rng.random()
        if i<3 or r<0.25:types.append(T(rng.choice([U8,U16,U32,U64,BOOL])));continue
        if r<0.35:
            # Indirect: any index, including itself or later ones. Host type strings cannot name an
            # anonymous recursive type, so host graphs only point at earlier types.
            if host and not lower:types.append(T(U8));continue
            target=rng.choice(lower)if host else rng.randrange(size)
            types.append(T(rng.choice([POINTER,SLICE]),target));continue
        if r<0.42:
            pool=[j for j in lower if types[j][0] in(U8,U16,U32,U64,BOOL,POINTER)]if host else list(range(size))
            if not pool:types.append(T(U32));continue
            types.append(T(rng.choice([OPTIONAL,RESULT]),rng.choice(pool)));continue
        if r<0.45 and not host:types.append(T(FUNCTION));continue
        if r<0.58:
            element=pick()
            if element is None:types.append(T(U8));continue
            types.append(T(ARRAY,element,rng.choice([1,2,3,5,16,100])));continue
        if r<0.68:
            first=len(fields);k=rng.randint(1,4)
            for _ in range(k):
                pool=[j for j in lower if types[j][0] in(U8,U16,U32,U64,BOOL,POINTER)]if host else list(range(size))
                fields.append(rng.choice(pool)if pool and rng.random()<0.6 else NONE)
            types.append(T(ENUM,first=first,length=k));continue
        first=len(fields);k=rng.randint(1,5)
        for _ in range(k):
            f=pick()
            fields.append(f if f is not None else 0)
        packed=int(rng.random()<0.2);alignment=0 if packed or rng.random()<0.92 else rng.choice([1,2,8,16,64,4096])
        types.append(T(STRUCT,first=first,length=k,alignment=alignment,packed=packed))
    return types,fields


def host_name(types,fields,i,names):
    kind,element,count,first,length,_,_=types[i]
    if kind in(U8,U16,U32,U64):return 'u'+str(8<<(kind-1))
    if kind==BOOL:return 'bool'
    if kind==POINTER:return '*'+host_name(types,fields,element,names)
    if kind==SLICE:return '[]'+host_name(types,fields,element,names)
    if kind==OPTIONAL:return '?'+host_name(types,fields,element,names)
    if kind==RESULT:return '!'+host_name(types,fields,element,names)
    if kind==ARRAY:return '[%d]'%count+host_name(types,fields,element,names)
    return names[i]


def host_layouts(types,fields):
    """Lay the same graph out with the host compiler's TypeSystem."""
    names={i:('S%d'if t[0]==STRUCT else'E%d')%i for i,t in enumerate(types)if t[0]in(STRUCT,ENUM)}
    decls=[]
    for i,t in enumerate(types):
        kind,_,_,first,length,alignment,packed=t
        if kind==STRUCT:
            body=','.join('f%d:%s'%(f,host_name(types,fields,fields[f],names))for f in range(first,first+length))
            prefix=('packed 'if packed else'')+('align(%d) '%alignment if alignment else'')
            decls.append('%sstruct S%d{%s}'%(prefix,i,body))
        elif kind==ENUM:
            body=','.join('V%d'%f+('(%s)'%host_name(types,fields,fields[f],names)if fields[f]!=NONE else'')for f in range(first,first+length))
            decls.append('enum E%d{%s}'%(i,body))
    system=TypeSystem(Parser(lex('module host_layout; '+' '.join(decls))).parse())
    result=[];offsets={}
    for i in range(len(types)):
        layout=system.layout(host_name(types,fields,i,names));result.append((layout.size,layout.alignment))
        if types[i][0]==STRUCT:
            for f in range(types[i][3],types[i][3]+types[i][4]):offsets[f]=layout.fields['f%d'%f].offset
    return result,offsets


class BootstrapTypeLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native type layout requires NASM/GCC')
        cls.work=ROOT/'build/test/claude-c4'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,HOST,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/layout_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([ROOT/'lang',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/layout_export.dg',roots=roots,mode=mode)
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
            records=cls.records,semantic_checker_complete=False,L3_selfhost_complete=False,OS_VM_built=False),indent=2)+'\n')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:
            payload.extend(struct.pack('<10Q',len(c['types']),len(c['fields']),*c['caps'],c['depth'],c['readonly'],0))
            for t in c['types']:payload.extend(struct.pack('<6QB7x',*t[:6],t[6]))
            payload.extend(struct.pack('<%dQ'%len(c['fields']),*c['fields']))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,24)
        offset=8;results=[]
        for index,c in enumerate(cases):
            status,guard=struct.unpack_from('<2Q',run.stdout,offset);offset+=16
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['expected'][0],(label,index,'status'))
            if not status:
                n,m=len(c['types']),len(c['fields'])
                flat=struct.unpack_from('<%dQ'%(2*n),run.stdout,offset);offset+=16*n
                layouts=[(flat[2*i],flat[2*i+1])for i in range(n)]
                offsets=list(struct.unpack_from('<%dQ'%m,run.stdout,offset));offset+=8*m
                self.assertEqual(layouts,[tuple(x)for x in c['expected'][1]],(label,index,'layout'))
                self.assertEqual(offsets,c['expected'][2],(label,index,'offsets'))
                results.append((layouts,offsets))
            else:results.append(None)
        self.assertEqual(offset,len(run.stdout))
        return results

    def run_both(self,cases,label):
        return {mode:self.run_cases(exe,cases,label+'-'+mode)for mode,exe in self.executables.items()}

    def test_fixed_layouts_match_host_typesys(self):
        # Natural / packed / over-aligned / nested, as in test_layout.py, plus scalars and pairs.
        types=[T(U8),T(U16),T(U32),T(U64),T(BOOL),T(POINTER,9),T(FUNCTION),T(SLICE,0),T(OPTIONAL,3),T(RESULT,NONE),
               T(STRUCT,first=0,length=3),T(STRUCT,first=3,length=3,packed=1),T(ARRAY,3,512),
               T(STRUCT,first=6,length=1,alignment=4096),T(ARRAY,10,2),T(STRUCT,first=7,length=3),
               T(ENUM,first=10,length=2),T(ENUM,first=12,length=2),T(RESULT,3)]
        fields=[0,3,1, 0,3,1, 12, 0,14,0, NONE,NONE, NONE,3]
        c=case(types,fields,status=OK)
        self.assertEqual(c['expected'][1][10],(24,8));self.assertEqual(c['expected'][1][11],(11,1))
        self.assertEqual(c['expected'][1][13],(4096,4096));self.assertEqual(c['expected'][1][15],(64,8))
        self.assertEqual(c['expected'][2][7:10],[0,8,56])
        results=self.run_both([c,dict(c,readonly=1)],'fixed')
        host_types=[t for t in types];host_types[5]=T(POINTER,0);host_types[6]=T(U64);host_types[9]=T(RESULT,3)
        hc=case(host_types,fields,status=OK);host,offs=host_layouts(host_types,fields)
        self.assertEqual(hc['expected'][1],host)
        for f,o in offs.items():self.assertEqual(hc['expected'][2][f],o)
        self.run_both([hc],'fixed-host')
        self.records.append(dict(test='fixed-host',cases=3,modes=2,host_typesys_compared=True,passed=all(results.values())))

    def test_random_graphs_against_reference_and_host(self):
        rng=random.Random(0xC4A7);cases=[];host_checked=0;statuses={}
        for i in range(600):
            host=i%2==0;types,fields=random_graph(rng,rng.randint(1,40),host=host)
            c=case(types,fields,readonly=int(i%60==0));cases.append(c)
            statuses[c['expected'][0]]=statuses.get(c['expected'][0],0)+1
            if host and c['expected'][0]==OK:
                layouts,offsets=host_layouts(types,fields)
                self.assertEqual(c['expected'][1],layouts,('host',i));host_checked+=1
                for f,o in offsets.items():self.assertEqual(c['expected'][2][f],o,('host offset',i,f))
        for i in range(120):
            types,fields=random_graph(rng,rng.randint(2,25),cyclic=True);cases.append(case(types,fields))
            statuses[cases[-1]['expected'][0]]=statuses.get(cases[-1]['expected'][0],0)+1
        self.run_both(cases,'random')
        self.assertGreater(statuses.get(OK,0),480,statuses);self.assertGreater(statuses.get(CYCLE,0),20,statuses)
        self.records.append(dict(test='random-graphs',cases=len(cases),seed='0xC4A7',statuses=statuses,
                                 host_typesys_compared=host_checked,modes=2,passed=True))

    def test_cycles_alignment_overflow_capacity_depth_and_metadata(self):
        cases=[];S=STRUCT
        # Direct value cycles vs indirect self-reference.
        cases+=[case([T(S,first=0,length=1)],[0],status=CYCLE),
                case([T(ARRAY,0,2)],[],status=CYCLE),
                case([T(S,first=0,length=1),T(ARRAY,0,3)],[1],status=CYCLE),
                case([T(S,first=0,length=2),T(POINTER,0),T(U8)],[1,2],status=OK),
                case([T(S,first=0,length=2),T(SLICE,0),T(OPTIONAL,0),T(RESULT,0)],[1,2],status=OK),
                case([T(S,first=0,length=1),T(S,first=1,length=1),T(POINTER,0)],[1,2],status=OK),
                case([T(ENUM,first=0,length=1)],[0],status=OK),            # enum payload does not embed itself
                case([T(S,first=0,length=1),T(ENUM,first=1,length=1)],[1,0],status=OK)]
        # Alignment rules.
        for alignment,packed,status in [(0,0,OK),(1,0,ALIGNMENT),(2,0,ALIGNMENT),(8,0,OK),(16,0,OK),(4096,0,OK),(8192,0,ALIGNMENT),
                                        (3,0,ALIGNMENT),(48,0,ALIGNMENT),(0,1,OK),(1,1,ALIGNMENT),(8,1,ALIGNMENT),(NONE,0,ALIGNMENT)]:
            cases.append(case([T(S,first=0,length=2,alignment=alignment,packed=packed),T(U64),T(U8)],[1,2],status=status))
        cases.append(case([T(S,first=0,length=1,alignment=1),T(U8)],[1],status=OK))
        # Overflow at MAX_SIZE.
        cases+=[case([T(U8),T(ARRAY,0,MAX_SIZE)],[],status=OK),case([T(U8),T(ARRAY,0,MAX_SIZE+1)],[],status=OVERFLOW),
                case([T(U16),T(ARRAY,0,MAX_SIZE//2)],[],status=OK),case([T(U16),T(ARRAY,0,MAX_SIZE//2+1)],[],status=OVERFLOW),
                case([T(U64),T(ARRAY,0,NONE)],[],status=OVERFLOW),
                case([T(U8),T(ARRAY,0,MAX_SIZE),T(S,first=0,length=2,packed=1)],[1,0],status=OVERFLOW),
                case([T(U8),T(ARRAY,0,MAX_SIZE-1),T(S,first=0,length=2,packed=1)],[1,0],status=OK),
                case([T(U8),T(ARRAY,0,MAX_SIZE-1),T(U16),T(S,first=0,length=2)],[1,2],status=OVERFLOW),
                case([T(U8),T(ARRAY,0,2**62),T(ARRAY,1,2)],[],status=OVERFLOW),
                case([T(U8),T(ARRAY,0,MAX_SIZE-7),T(S,first=0,length=1,alignment=16)],[1],status=OVERFLOW)]
        # Depth: a chain of arrays; each level is one value edge.
        chain=[T(ARRAY,i+1,1)for i in range(300)]+[T(U8)]
        for depth,status in [(256,DEPTH),(300,INVALID),(1,DEPTH)]:cases.append(case(chain,[],depth=depth,status=status))
        short=[T(ARRAY,i+1,1)for i in range(255)]+[T(U8)]
        shorter=[T(ARRAY,i+1,1)for i in range(254)]+[T(U8)]
        cases+=[case(short,[],depth=256,status=OK),case(shorter,[],depth=255,status=OK),case(short,[],depth=255,status=DEPTH),
                case([T(U8)],[],depth=1,status=OK),case([T(U8),T(ARRAY,0,1)],[],depth=1,status=DEPTH)]
        # Exact and short capacities for every output and scratch region.
        types=[T(S,first=0,length=2),T(U32),T(U8)];fields=[1,2,0]
        for caps,status in [((3,3,3,3,3),OK),((4,5,6,7,8),OK),((2,3,3,3,3),CAPACITY),((3,2,3,3,3),CAPACITY),((3,3,2,3,3),CAPACITY),
                            ((3,3,3,2,3),CAPACITY),((3,3,3,3,2),CAPACITY),((0,0,0,0,0),CAPACITY)]:
            cases.append(case(types,fields,caps=caps,status=status))
        cases.append(case([],[],caps=(0,0,0,0,0),status=OK));cases.append(case([],[5,6],status=OK))   # unowned fields -> 0
        # Metadata: every malformed descriptor is INVALID before scratch is touched.
        bad=[([T(0)],[]),([T(14)],[]),([T(U8,0)],[]),([T(U8,count=1)],[]),([T(U8,first=1)],[0]),([T(U8,length=1)],[0]),
             ([T(U8,alignment=8)],[]),([T(U8,packed=1)],[]),([T(U8,packed=2)],[]),([T(S,first=0,length=1,packed=2),T(U8)],[1]),
             ([T(POINTER)],[]),([T(POINTER,5)],[]),([T(SLICE,1)],[]),([T(OPTIONAL,NONE)],[]),([T(RESULT,7)],[]),
             ([T(FUNCTION,0)],[]),([T(ARRAY,0,0),T(U8)],[]),([T(U8),T(ARRAY,0,0)],[]),([T(ARRAY,NONE,1)],[]),
             ([T(S,first=0,length=0)],[]),([T(ENUM,first=0,length=0)],[]),([T(S,first=0,length=2),T(U8)],[1]),
             ([T(S,first=NONE,length=2),T(U8)],[1]),([T(S,first=0,length=1),T(U8)],[NONE]),([T(S,first=0,length=1),T(U8)],[9]),
             ([T(ENUM,first=0,length=1)],[3]),([T(S,first=0,length=1,element=1),T(U8)],[1]),([T(ENUM,first=0,length=1,count=1)],[NONE]),
             ([T(ENUM,first=0,length=1,alignment=8)],[NONE]),([T(S,first=0,length=2),T(S,first=1,length=1),T(U8)],[2,2]),
             ([T(S,first=0,length=1),T(ENUM,first=0,length=1),T(U8)],[2]),([T(U8)],[],0),([T(U8)],[],257)]
        for entry in bad:
            types,fields=entry[0],entry[1];depth=entry[2]if len(entry)>2 else 256
            cases.append(case(types,fields,depth=depth,status=INVALID))
        cases.append(case([T(S,first=0,length=1),T(S,first=0,length=1)],[0],status=INVALID))   # INVALID before CYCLE
        cases.append(case([T(ARRAY,1,0),T(U8)],[],caps=(1,0,2,0,2),status=INVALID))         # INVALID before CAPACITY
        cases.append(case([T(S,first=0,length=1)],[0],caps=(0,1,1,1,1),status=CAPACITY))    # CAPACITY before CYCLE
        cases.append(case(short,[],depth=256,readonly=1,status=OK))
        self.run_both(cases,'bounds')
        self.records.append(dict(test='cycles-alignment-overflow-capacity-depth-metadata',cases=len(cases),
                                 invalid_preflights_per_native=24,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/type_layout.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/layout_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        S=STRUCT
        controls=[
            ('bad-packed-alignment','var fa=child.alignment;if t.is_packed{fa=1;}','var fa=child.alignment;',
             [case([T(S,first=0,length=2,packed=1),T(U8),T(U64)],[1,2])],'layout'),
            ('bad-cycle-check','if state==DONE{return OK;}if state==OPEN{return CYCLE;}','if state!=0{return OK;}',
             [case([T(S,first=0,length=2),T(U8),T(ARRAY,0,2)],[1,2],status=CYCLE)],'status'),
            ('bad-early-publish','i=0;while i<types.len{let status=compute(&c,i,1);if status!=OK{return status;}i+=1;}\n i=0;while i<types.len{layouts[i]=work[i];i+=1;}',
             'i=0;while i<types.len{let status=compute(&c,i,1);layouts[i]=work[i];if status!=OK{return status;}i+=1;}\n i=0;while i<types.len{layouts[i]=work[i];i+=1;}',
             [case([T(U8),T(S,first=0,length=1),T(ARRAY,2,2)],[0],status=CYCLE)],'guard/atomicity'),
            ('bad-early-offset','i=0;while i<fields.len{work_offsets[i]=0;i+=1;}','i=0;while i<fields.len{work_offsets[i]=0;offsets[i]=0;i+=1;}',
             [case([T(S,first=0,length=1),T(ARRAY,0,2)],[1],status=CYCLE)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
