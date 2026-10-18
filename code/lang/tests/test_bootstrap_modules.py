"""Native module graph over explicit-root source catalogs; real host resolver oracle."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tempfile
import unittest
import uuid
from lang.dongc import compile_file
from lang.dongc.frontend import lex
from lang.dongc.modules import Resolver
from lang.tests.test_dongc import tool,nasm_flags

ROOT=Path(__file__).resolve().parents[2]
NONE=2**64-1
HARNESS=r'''
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef struct{const uint8_t*p;uint64_t n;} Bytes;
typedef struct{uint64_t root;Bytes path,bytes;} Source;
typedef struct{uint64_t source,skip,ts,tc,ss,sc,ns,nc,root;} Unit;
typedef struct{uint64_t from,to,import_node,alias;} Edge;
typedef struct{uint64_t count,tu,su,nu,eu,code,source,start,detail;} Result;
typedef struct{uint64_t data[7];} Token;
typedef struct{uint64_t data[8];} Node;
_Static_assert(sizeof(Source)==40&&sizeof(Unit)==72&&sizeof(Edge)==32&&sizeof(Result)==72,"Dong layout");
extern uint64_t ABI dong_bootstrap_modules(uint64_t,uint64_t,const Source*,uint64_t,Unit*,uint64_t,Token*,uint64_t,
 uint8_t*,uint64_t,Node*,uint64_t,Edge*,uint64_t,uint8_t*,uint64_t,uint64_t,Result*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n){fprintf(stderr,"panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*b=p;for(uint64_t i=0;i<n;i++)if(b[i]!=0xa5)return 0;return 1;}
static void rd(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void wr(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static void*alloc(uint64_t n){uint8_t*p=malloc(n+32);if(!p)exit(95);memset(p,0xa5,n+32);return p+16;}
static int guard(const void*p,uint64_t n){return filled((const uint8_t*)p-16,16)&&filled((const uint8_t*)p+n,16);}
static void release(void*p){free((uint8_t*)p-16);}
static void invalid(void){
 uint64_t memory[512],saved[512];Source*s=(Source*)memory;Unit*u=(Unit*)(memory+16);Token*t=(Token*)(memory+64);
 Node*n=(Node*)(memory+192);Edge*e=(Edge*)(memory+340);uint8_t*b=(uint8_t*)(memory+380),*st=(uint8_t*)(memory+390);Result*r=(Result*)(memory+400);
 for(unsigned i=0;i<12;i++){
  memset(memory,0xa5,sizeof(memory));s[0]=(Source){0,{(const uint8_t*)"a.dg",4},{(const uint8_t*)"module a;",9}};
  if(i==6){s[0].bytes=(Bytes){NULL,1};}
  if(i==7){s[0].path=(Bytes){(const uint8_t*)"../a.dg",7};}
  if(i==8){s[0].root=1;}
  memcpy(saved,memory,sizeof(memory));uint64_t code;
  switch(i){
   case 0:code=dong_bootstrap_modules(0,1,s,1,u,2,t,16,b,32,n,16,e,2,st,8,64,NULL);break;
   case 1:code=dong_bootstrap_modules(0,1,NULL,1,u,2,t,16,b,32,n,16,e,2,st,8,64,r);break;
   case 2:code=dong_bootstrap_modules(0,1,s,UINT64_MAX,u,2,t,16,b,32,n,16,e,2,st,8,64,r);break;
   case 3:code=dong_bootstrap_modules(0,1,s,1,u,UINT64_MAX,t,16,b,32,n,16,e,2,st,8,64,r);break;
   case 4:code=dong_bootstrap_modules(0,1,s,1,u,2,(Token*)u,16,b,32,n,16,e,2,st,8,64,r);break;
   case 5:code=dong_bootstrap_modules(0,1,s,1,u,2,t,16,b,32,n,16,e,2,(uint8_t*)n,8,64,r);break;
   case 9:code=dong_bootstrap_modules(0,1,s,1,(Unit*)((uint8_t*)u+1),2,t,16,b,32,n,16,e,2,st,8,64,r);break;
   case 10:code=dong_bootstrap_modules(1,1,s,1,u,2,t,16,b,32,n,16,e,2,st,8,64,r);break;
   case 11:code=dong_bootstrap_modules(0,1,s,1,u,2,t,16,b,32,n,16,e,2,st,8,0,r);break;
   default:code=dong_bootstrap_modules(0,1,s,1,u,2,t,16,b,32,n,16,e,2,st,8,64,r);break;
  }if(code!=1||memcmp(memory,saved,sizeof(memory))){fprintf(stderr,"invalid preflight %u\n",i);exit(93);}
 }
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 invalid();uint64_t count;rd(&count,8);
 while(count--){uint64_t h[10];rd(h,sizeof(h));uint64_t roots=h[0],entry=h[1],sn=h[2],uc=h[3],tc=h[4],sc=h[5],nc=h[6],ec=h[7],stc=h[8];
  if(sn>1000||uc>1000||tc>300000||sc>300000||nc>500000||ec>10000||stc>1000)exit(94);
  Source*s=alloc(sn*40);uint8_t**copies=calloc(sn?sn:1,sizeof(*copies));if(!copies)exit(95);
  for(uint64_t i=0;i<sn;i++){uint64_t x[3];rd(x,sizeof(x));if(x[1]>10000||x[2]>1000000)exit(94);
   s[i].root=x[0];uint8_t*p=alloc(x[1]),*b=alloc(x[2]);rd(p,x[1]);rd(b,x[2]);s[i].path=(Bytes){p,x[1]};s[i].bytes=(Bytes){b,x[2]};
   copies[i]=malloc(x[1]+x[2]+1);if(!copies[i])exit(95);memcpy(copies[i],p,x[1]);memcpy(copies[i]+x[1],b,x[2]);
  }Source*copy=malloc(sn*40+1);memcpy(copy,s,sn*40);
  Unit*u=alloc(uc*72);Token*t=alloc(tc*56);uint8_t*b=alloc(sc);Node*n=alloc(nc*64);Edge*e=alloc(ec*32);uint8_t*st=alloc(stc);
  uint64_t rm[13];memset(rm,0xa5,sizeof(rm));Result*r=(Result*)(rm+2);
  uint64_t code=dong_bootstrap_modules(entry,roots,s,sn,u,uc,t,tc,b,sc,n,nc,e,ec,st,stc,h[9],r);
  uint64_t ok=guard(s,sn*40)&&!memcmp(copy,s,sn*40)&&guard(u,uc*72)&&guard(t,tc*56)&&guard(b,sc)&&guard(n,nc*64)&&guard(e,ec*32)&&guard(st,stc)&&filled(rm,16)&&filled(rm+11,16);
  for(uint64_t i=0;i<sn;i++)ok=ok&&guard(s[i].path.p,s[i].path.n)&&guard(s[i].bytes.p,s[i].bytes.n)&&!memcmp(copies[i],s[i].path.p,s[i].path.n)&&!memcmp(copies[i]+s[i].path.n,s[i].bytes.p,s[i].bytes.n);
  if(code==1)ok=ok&&filled(r,72)&&filled(u,uc*72)&&filled(t,tc*56)&&filled(b,sc)&&filled(n,nc*64)&&filled(e,ec*32)&&filled(st,stc);
  else{ok=ok&&code==r->code&&r->count<=uc&&r->tu<=tc&&r->su<=sc&&r->nu<=nc&&r->eu<=ec;
   if(code)ok=ok&&r->count==0;
   else{ok=ok&&filled(u+r->count,(uc-r->count)*72)&&filled(t+r->tu,(tc-r->tu)*56)&&filled(b+r->su,sc-r->su)&&filled(n+r->nu,(nc-r->nu)*64)&&filled(e+r->eu,(ec-r->eu)*32)&&filled(st+sn,stc-sn);
    for(uint64_t i=0;i<r->count;i++)ok=ok&&u[i].source<sn&&u[i].root<u[i].nc&&n[u[i].ns+u[i].root].data[0]==96;
   }
  }wr(&code,8);wr(r,72);wr(&ok,8);if(!code){wr(u,r->count*72);wr(e,r->eu*32);}
  for(uint64_t i=0;i<sn;i++){release((void*)s[i].path.p);release((void*)s[i].bytes.p);free(copies[i]);}
  free(copies);free(copy);release(s);release(u);release(t);release(b);release(n);release(e);release(st);
 }return 0;
}
'''

def catalog(files,roots=1,entry=0,**budgets):
    # files: (logical root, canonical relative path, raw bytes or str)
    items=[(r,p.encode(),s.encode() if isinstance(s,str) else s) for r,p,s in files]
    size=sum(len(s) for _,_,s in items)
    values=dict(units=len(items)+1,tokens=size+32,strings=size+32,nodes=size*2+64,edges=len(items)*4+8,states=len(items)+4,depth=256)
    values.update(budgets)
    return dict(files=items,roots=roots,entry=entry,**values)

class BootstrapModulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native module loading requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-modules'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.records=[]
        names=['modules.dg','syntax.dg','expression.dg','lexer.dg','unicode.dg']
        cls.inputs={f'lang/bootstrap/{n}':hashlib.sha256((ROOT/'lang/bootstrap'/n).read_bytes()).hexdigest() for n in names}
        cls.inputs[Path(__file__).relative_to(ROOT).as_posix()]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        cls.executables={m:cls.build(ROOT/'lang',m,m) for m in ('debug','release')}

    @classmethod
    def command(cls,args,label):
        r=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=120)
        (cls.work/(label+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((label,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,root,mode,label):
        result=compile_file(root/'bootstrap/modules.dg',roots=[root],mode=mode)
        asm=cls.work/(label+'.asm');asm.write_text(result.assembly,encoding='utf-8');obj=cls.work/(label+'.o')
        for fmt in ('elf64','win64'):
            target=obj if fmt==('win64' if os.name=='nt' else 'elf64') else cls.work/(label+'.'+fmt+'.o')
            cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',target,asm],label+'-'+fmt)
        exe=cls.work/(label+('.exe' if os.name=='nt' else ''))
        cls.command([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),cls.work/'probe.c',obj,'-o',exe],label+'-link')
        return exe

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        artifacts={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.work.rglob('*') if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,artifact_sha256=artifacts,records=cls.records,OS_VM_built=False,L3_selfhost_complete=False),indent=2)+'\n',encoding='utf-8')

    def reference(self,c):
        with tempfile.TemporaryDirectory(dir=self.work) as temporary:
            base=Path(temporary);paths=[]
            for i,(r,p,b) in enumerate(c['files']):
                root=base/str(r);root.mkdir(exist_ok=True)
                path=root/p.decode();path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b);paths.append(path.resolve())
            roots=[base/str(i) for i in range(c['roots'])]
            resolver=Resolver(roots);first=resolver.read(paths[c['entry']],str(paths[c['entry']]))
            if roots:self.assertEqual(resolver.locate(first.name,first.token),paths[c['entry']])
            resolver.visit(first,paths[c['entry']]);names=list(resolver.units)
            indexes=[paths.index(resolver.paths[name].resolve()) for name in names]
            edges=[]
            for name,unit in resolver.units.items():
                for imported in unit.imports:edges.append((indexes[names.index(name)],indexes[names.index(imported.path)],imported.alias))
            return indexes,sorted(edges)

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c,status in cases:
            payload.extend(struct.pack('<10Q',c['roots'],c['entry'],len(c['files']),*[c[k] for k in ('units','tokens','strings','nodes','edges','states','depth')]))
            for r,p,s in c['files']:payload.extend(struct.pack('<3Q',r,len(p),len(s)));payload.extend(p);payload.extend(s)
        (self.work/(label+'.input')).write_bytes(payload)
        r=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(r.stdout);(self.work/(label+'.stderr')).write_bytes(r.stderr)
        self.assertEqual(r.returncode,0,r.stderr);at=0
        for i,(c,expected) in enumerate(cases):
            status,*fields=struct.unpack_from('<11Q',r.stdout,at);at+=88
            count,tu,su,nu,eu,code,source,start,detail,guard=fields
            self.assertEqual(guard,1,(label,i,'guard/atomicity'))
            self.assertEqual(status,expected,(label,i,'status',source,start,detail))
            if status:continue
            units=[struct.unpack_from('<9Q',r.stdout,at+j*72) for j in range(count)];at+=count*72
            edges=[struct.unpack_from('<4Q',r.stdout,at+j*32) for j in range(eu)];at+=eu*32
            expected_units,expected_edges=self.reference(c)
            self.assertEqual([u[0] for u in units],expected_units,(label,i,'units'))
            actual_edges=[]
            for a,b,imp,alias in edges:
                raw=c['files'][units[a][0]][2].decode('utf-8-sig')
                actual_edges.append((units[a][0],units[b][0],lex(raw)[alias].value))
            self.assertEqual(sorted(actual_edges),expected_edges,(label,i,'edges'))
            self.assertEqual(sum(u[3] for u in units),tu);self.assertEqual(sum(u[5] for u in units),su);self.assertEqual(sum(u[7] for u in units),nu)
        self.assertEqual(at,len(r.stdout))

    def test_import_graphs_against_existing_filesystem_resolver(self):
        cases=[(catalog([(0,'a.dg','module a;import b;import c;'),(0,'b.dg','module b;import d;'),(0,'c.dg','module c;import d as shared;'),(0,'d.dg','module d;')]),0),
               (catalog([(0,'目录/a.dg',b'\xef\xbb\xbfmodule \xe7\x9b\xae\xe5\xbd\x95.a;import \xe7\x9b\xae\xe5\xbd\x95.b;'),(1,'目录/b.dg','module 目录.b;')],roots=2),0),
               (catalog([(NONE,'entry.dg','module different.name;')],roots=0),0)]
        rng=random.Random(0x106D06)
        for n in range(2,28):
            files=[]
            for i in range(n):
                dependencies=[j for j in range(i+1,n) if rng.randrange(5)==0]
                files.append((i%2,f'm{i}.dg',f'module m{i};'+''.join(f'import m{j} as x{j};' for j in dependencies)))
            cases.append((catalog(files,roots=2),0))
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'graphs-'+mode)
        self.records.append(dict(test='filesystem-resolver-graph',cases=len(cases),modes=2,passed=True))

    def test_rejections_and_pool_boundaries(self):
        cases=[(catalog([(0,'a.dg','module a;import missing;')]),2),
               (catalog([(0,'a.dg','module a;'),(1,'a.dg','module a;')],roots=2),3),
               (catalog([(0,'a.dg','module wrong;')]),4),
               (catalog([(0,'a.dg','module a;import b;'),(0,'b.dg','module b;import a;')]),5),
               (catalog([(0,'a.dg','module a;import b as x;import c as x;'),(0,'b.dg','module b;'),(0,'c.dg','module c;')]),10),
               (catalog([(NONE,'a.dg','module a;import b;')],roots=0),9),
               (catalog([(0,'a.dg',b'\xff')]),7),(catalog([(0,'a.dg','module a;fn')]),8),
               (catalog([(0,'../a.dg','module a;')]),1)]
        simple=[(0,'a.dg','module a;')]
        for key in ('units','tokens','nodes','states'):cases.append((catalog(simple,**{key:0}),6))
        cases.append((catalog([(0,'a.dg','module a;const s:[]const u8="x";')],strings=0),6))
        cases.append((catalog([(0,'a.dg','module a;import b;'),(0,'b.dg','module b;')],edges=0),6))
        cases.append((catalog([(0,'a.dg','module a;import b;'),(0,'b.dg','module b;')],depth=1),11))
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'bounds-'+mode)
        self.records.append(dict(test='root-import-cycle-capacity',cases=len(cases),modes=2,invalid_preflights_per_process=12,passed=True))

    def test_actual_bad_ambiguity_and_cycle_checks_are_rejected(self):
        source=(ROOT/'lang/bootstrap/modules.dg').read_text(encoding='utf-8')
        variants=[('ambiguity','if found!=NONE{return reject(s,AMBIGUOUS,(*unit).source_index,(*s).tokens[(*unit).token_start+token].start,0);}',
                   'if found!=NONE{return found;}',catalog([(0,'a.dg','module a;'),(1,'a.dg','module a;')],roots=2),3),
                  ('cycle','if (*s).states[index]==1{return reject(s,CYCLE,index,0,0);}',
                   'if (*s).states[index]==9{return reject(s,CYCLE,index,0,0);}',catalog([(0,'a.dg','module a;import a;')]),5)]
        for name,old,new,c,expected in variants:
            self.assertEqual(source.count(old),1)
            root=self.work/('bad-'+name);(root/'bootstrap').mkdir(parents=True)
            for file in ('expression.dg','syntax.dg','lexer.dg','unicode.dg'):shutil.copyfile(ROOT/'lang/bootstrap'/file,root/'bootstrap'/file)
            (root/'bootstrap/modules.dg').write_text(source.replace(old,new,1),encoding='utf-8')
            for mode in ('debug','release'):
                exe=self.build(root,mode,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'status'):self.run_cases(exe,[(c,expected)],'bad-'+name+'-'+mode)
                self.records.append(dict(test='actual-bad-Dong',variant=name,mode=mode,rejected_by='status',passed=True))


if __name__=='__main__':unittest.main()
