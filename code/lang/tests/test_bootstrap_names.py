"""Native graph-to-namespace collection and visibility, before type checking."""
from __future__ import annotations
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
from lang.tests.test_dongc import tool, nasm_flags
from lang.tests.test_bootstrap_modules import HARNESS as MODULE_HARNESS, catalog

ROOT=Path(__file__).resolve().parents[2]
SENTINEL=0xa5a5a5a5a5a5a5a5
WRAPPER='''module probe;
import bootstrap.names as names;
import bootstrap.modules as modules;
import bootstrap.lexer as lex;
import bootstrap.expression as ast;
export("names_collect") unsafe fn collect(s:*const modules.Source,sn:usize,u:*const modules.Unit,un:usize,
 t:*const lex.Token,tn:usize,n:*const ast.Node,nn:usize,e:*const modules.Edge,en:usize,
 out:*names.Symbol,oc:usize,work:*names.Symbol,wc:usize,r:*names.Result)u64{unsafe{
 return names.collect(slice_from_raw_parts(s,sn),slice_from_raw_parts(u,un),slice_from_raw_parts(t,tn),
 slice_from_raw_parts(n,nn),slice_from_raw_parts(e,en),slice_from_raw_parts(out,oc),slice_from_raw_parts(work,wc),r);
}}
export("names_resolve") unsafe fn resolve(s:*const modules.Source,sn:usize,u:*const modules.Unit,un:usize,
 t:*const lex.Token,tn:usize,sy:*const names.Symbol,n:usize,owner:usize,p:*const u8,len:usize,out:*usize)u64{unsafe{
 return names.resolve(slice_from_raw_parts(s,sn),slice_from_raw_parts(u,un),slice_from_raw_parts(t,tn),
 slice_from_raw_parts(sy,n),owner,slice_from_raw_parts(p,len),out);
}}
'''
DECLARATIONS=r'''
typedef struct{uint64_t unit,name,decl,kind,flags,target;} Symbol;
typedef struct{uint64_t code,count,unit,token,detail;} NamesResult;
extern uint64_t ABI names_collect(const Source*,uint64_t,const Unit*,uint64_t,const Token*,uint64_t,
 const Node*,uint64_t,const Edge*,uint64_t,Symbol*,uint64_t,Symbol*,uint64_t,NamesResult*);
extern uint64_t ABI names_resolve(const Source*,uint64_t,const Unit*,uint64_t,const Token*,uint64_t,
 const Symbol*,uint64_t,uint64_t,const uint8_t*,uint64_t,uint64_t*);
static void semantic(const Source*s,uint64_t sn,const Unit*u,const Token*t,const Node*n,const Edge*e,
 const Result*r,uint64_t oc,uint64_t wc,uint64_t queries){
 Symbol*out=alloc(oc*48),*work=alloc(wc*48);uint64_t rm[9];memset(rm,0xa5,sizeof(rm));NamesResult*res=(NamesResult*)(rm+2);
 uint64_t un=r->count,tn=r->tu,nn=r->nu,en=r->eu;
 uint64_t sizes[]={un*72,tn*56,nn*64,en*32};const void*inputs[]={u,t,n,e};uint8_t*copies[4];
 for(int i=0;i<4;i++){copies[i]=malloc(sizes[i]+1);memcpy(copies[i],inputs[i],sizes[i]);}
 /* Invalid calls must leave every output byte untouched. */
 for(unsigned i=0;i<8;i++){
  uint64_t z;
  switch(i){
   case 0:z=names_collect(s,sn,u,un,t,tn,n,nn,e,en,out,oc,work,wc,NULL);break;
   case 1:z=names_collect(NULL,1,u,un,t,tn,n,nn,e,en,out,oc,work,wc,res);break;
   case 2:z=names_collect(s,UINT64_MAX,u,un,t,tn,n,nn,e,en,out,oc,work,wc,res);break;
   case 3:z=names_collect(s,sn,u,un,t,tn,n,nn,e,en,(Symbol*)u,1,work,wc,res);break;
   case 4:z=names_collect(s,sn,u,un,t,tn,n,nn,e,en,out,1,out,1,res);break;
   case 5:z=names_collect(s,sn,u,un,t,tn,n,nn,e,en,(Symbol*)((uint8_t*)out+1),1,work,wc,res);break;
   case 6:z=names_collect(s,sn,u,un,t,tn,n,nn,e,en,NULL,1,work,wc,res);break;
   default:z=names_collect(s,sn,u,un,t,tn,n,nn,e,en,out,oc,work,UINT64_MAX,res);break;
  }
  if(z!=1||!filled(out,oc*48)||!filled(work,wc*48)||!filled(rm,sizeof(rm))){fprintf(stderr,"names invalid %u\n",i);exit(96);}
 }
 uint64_t code=names_collect(s,sn,u,un,t,tn,n,nn,e,en,out,oc,work,wc,res);
 uint64_t ok=code==res->code&&guard(out,oc*48)&&guard(work,wc*48)&&filled(rm,16)&&filled(rm+7,16);
 for(int i=0;i<4;i++){ok=ok&&!memcmp(inputs[i],copies[i],sizes[i]);free(copies[i]);}
 if(code)ok=ok&&res->count==0&&filled(out,oc*48);
 else ok=ok&&res->count<=oc&&filled(out+res->count,(oc-res->count)*48);
 wr(&code,8);wr(res,40);wr(&ok,8);
 if(!code){
  for(uint64_t i=0;i<res->count;i++){Symbol x=out[i];const Unit*v=u+x.unit;const Token*k=t+v->ts+x.name;
   uint64_t begin=k->data[1],end=k->data[2],len=end-begin;
   wr(&x.unit,8);wr(&x.kind,8);wr(&x.flags,8);wr(&x.target,8);wr(&len,8);wr(s[v->source].bytes.p+v->skip+begin,len);
  }
 }
 while(queries--){uint64_t h[2];rd(h,16);if(h[1]>10000)exit(94);uint8_t*p=alloc(h[1]);rd(p,h[1]);
  uint8_t*saved=malloc(h[1]+1);memcpy(saved,p,h[1]);uint64_t om[5];memset(om,0xa5,sizeof(om));uint64_t*value=om+2;
  uint64_t z=code?99:names_resolve(s,sn,u,un,t,tn,out,res->count,h[0],p,h[1],value);
  uint64_t good=filled(om,16)&&filled(om+3,16)&&guard(p,h[1])&&!memcmp(saved,p,h[1]);
  if(z)good=good&&*value==UINT64_C(0xa5a5a5a5a5a5a5a5);
  else good=good&&*value<res->count;
  wr(&z,8);wr(value,8);wr(&good,8);free(saved);release(p);
 }
 release(out);release(work);
}
'''
# Reuse the real module loader's input integrity checks; add semantic results
# before the original checks so corruption of any loaded input is observable.
HARNESS=MODULE_HARNESS.replace('int main(void){',DECLARATIONS+'\nint main(void){',1)
HARNESS=HARNESS.replace('uint64_t h[10];rd(h,sizeof(h))','uint64_t h[14];rd(h,sizeof(h))',1)
HARNESS=HARNESS.replace('  uint64_t ok=guard(s,','  if(code){fprintf(stderr,"loader status %u\\n",(unsigned)code);exit(97);}\n  uint64_t save=h[13]==1?t[0].data[2]:n[u[0].root].data[3];\n  if(h[13]==1)t[0].data[2]=UINT64_MAX;\n  if(h[13]==2)n[u[0].root].data[3]=u[0].nc;\n  semantic(s,sn,u,t,n,e,r,h[10],h[11],h[12]);\n  if(h[13]==1)t[0].data[2]=save;\n  if(h[13]==2)n[u[0].root].data[3]=save;\n  uint64_t ok=guard(s,',1)
HARNESS=HARNESS.replace('wr(&code,8);wr(r,72);wr(&ok,8);if(!code){wr(u,r->count*72);wr(e,r->eu*32);}', 'wr(&ok,8);',1)

class BootstrapNamesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native names requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-names'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.records=[]
        cls.files=['modules.dg','names.dg','expression.dg','syntax.dg','lexer.dg','unicode.dg']
        cls.inputs={p:hashlib.sha256((ROOT/'lang/bootstrap'/p).read_bytes()).hexdigest() for p in cls.files}
        cls.executables={m:cls.build(ROOT/'lang',m,m) for m in ('debug','release')}

    @classmethod
    def build(cls,root,mode,label):
        entry_root=cls.work/(label+'-entry');entry_root.mkdir()
        wrapper=entry_root/'probe.dg';wrapper.write_text(getattr(cls,'wrapper',WRAPPER),encoding='utf-8')
        asm=cls.work/(label+'.asm');asm.write_text(compile_file(wrapper,roots=[entry_root,root],mode=mode).assembly,encoding='utf-8')
        obj=cls.work/(label+'.o');exe=cls.work/(label+('.exe' if os.name=='nt' else ''))
        commands=[]
        for fmt in ('elf64','win64'):
            target=obj if fmt==('win64' if os.name=='nt' else 'elf64') else cls.work/(label+'.'+fmt+'.o')
            commands.append([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',target,asm])
        commands.append([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),cls.work/'probe.c',obj,'-o',exe])
        for i,command in enumerate(commands):
            r=subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=120)
            (cls.work/(label+f'-{i}.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
            if r.returncode:raise AssertionError((label,r.returncode,r.stdout,r.stderr))
        return exe

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        after={p:hashlib.sha256((ROOT/'lang/bootstrap'/p).read_bytes()).hexdigest() for p in cls.files}
        result=dict(source_sha256=cls.inputs,source_stable=cls.inputs==after,records=cls.records,complete_semantics=False,L3_selfhost_complete=False)
        (cls.work/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c,expected,queries in cases:
            payload.extend(struct.pack('<14Q',c['roots'],c['entry'],len(c['files']),*[c[k] for k in ('units','tokens','strings','nodes','edges','states','depth')],c.get('symbols',1000),c.get('work',1000),len(queries),c.get('mutate',0)))
            for r,p,b in c['files']:payload.extend(struct.pack('<3Q',r,len(p),len(b)));payload.extend(p);payload.extend(b)
            for owner,name,status,value in queries:
                b=name.encode();payload.extend(struct.pack('<2Q',owner,len(b)));payload.extend(b)
        (self.work/(label+'.input')).write_bytes(payload)
        r=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(r.stdout);(self.work/(label+'.stderr')).write_bytes(r.stderr)
        self.assertEqual(r.returncode,0,r.stderr);at=0
        for c,expected,queries in cases:
            status,code,count,unit,token,detail,guard=struct.unpack_from('<7Q',r.stdout,at);at+=56
            self.assertEqual(guard,1,'collection integrity');self.assertEqual(status,code)
            wanted=expected if isinstance(expected,int) else 0
            self.assertEqual(status,wanted,('status',unit,token,detail))
            symbols=[]
            if not status:
                for _ in range(count):
                    u,k,f,target,n=struct.unpack_from('<5Q',r.stdout,at);at+=40
                    name=r.stdout[at:at+n].decode();at+=n;symbols.append((u,name,k,f,target))
                self.assertEqual(symbols,expected,'symbols')
            for owner,name,z,value in queries:
                actual,v,g=struct.unpack_from('<3Q',r.stdout,at);at+=24
                self.assertEqual(g,1,'lookup integrity');self.assertEqual(actual,z,('lookup',name))
                self.assertEqual(v,value if z==0 else SENTINEL,('lookup-value',name))
            intact,=struct.unpack_from('<Q',r.stdout,at);at+=8;self.assertEqual(intact,1,'loader inputs')
        self.assertEqual(at,len(r.stdout))

    def test_collection_import_visibility_and_generated_namespaces(self):
        a='module a;import b as lib;const local:u64=1;pub fn main()u64{return lib.open();}'
        b='module b;pub fn open()u64{return 1;}fn hidden()u64{return 2;}pub struct S{pub field:u64}pub type Word=u64;'
        expected=[(0,'lib',1,0,1),(0,'local',7,0,0),(0,'main',2,1,0),(1,'open',2,1,1),(1,'hidden',2,0,1),(1,'S',3,1,1),(1,'Word',6,1,1)]
        queries=[(0,'local',0,1),(0,'lib.open',0,3),(0,'lib.hidden',6,0),(0,'lib.S',0,5),(1,'hidden',0,4),(0,'missing',5,0),(0,'lib.no',5,0),(0,'local.x',5,0),(0,'lib.Word',0,6),(999,'local',1,0)]
        cases=[(catalog([(0,'a.dg',a),(0,'b.dg',b)]),expected,queries)]
        cases.append((catalog([(0,'a.dg','module a;struct S{x:u64}fn(self:*S)get()u64{return 1;}fn get()u64{return 2;}')]),
                      [(0,'S',3,0,0),(0,'get',9,0,0),(0,'get',2,0,0)],[(0,'get',0,2)]))
        rng=random.Random(0x106A06)
        for j in range(40):
            names=rng.sample(range(10000),rng.randrange(1,30));decls=[];expected=[]
            for number in names:
                public=rng.randrange(2);name=f'名{number}';decls.append(('pub ' if public else '')+f'const {name}:u64={number};')
                expected.append((0,name,7,public,0))
            cases.append((catalog([(0,'a.dg','module a;'+''.join(decls))]),expected,[(0,x[1],0,i) for i,x in enumerate(expected)]))
        for m,exe in self.executables.items():self.run_cases(exe,cases,'collect-'+m)
        self.records.append(dict(test='collection-and-visibility',cases=len(cases),modes=2,passed=True))

    def test_duplicates_atomicity_and_capacity(self):
        bad=['const x:u64=1;fn x()u64{return 0;}', 'struct S{x:u64,x:u32}',
             'enum E{X,X}', 'fn f(x:u64,x:u64)u64{return x;}', 'type u64=u32;']
        cases=[(catalog([(0,'a.dg','module a;'+s)]),2,[]) for s in bad]
        cases.append((catalog([(0,'a.dg','module a;import b as x;const x:u64=1;'),(0,'b.dg','module b;')]),2,[]))
        for key in ('symbols','work'):
            c=catalog([(0,'a.dg','module a;const x:u64=1;')]);c[key]=0;cases.append((c,4,[]))
        for mutate in (1,2):
            c=catalog([(0,'a.dg','module a;const x:u64=1;')]);c['mutate']=mutate;cases.append((c,3,[]))
        for m,exe in self.executables.items():self.run_cases(exe,cases,'duplicates-'+m)
        self.records.append(dict(test='duplicates-capacity-atomicity',cases=len(cases),invalid_preflights=8,modes=2,passed=True))

    def test_actual_bad_private_visibility_is_rejected(self):
        source=(ROOT/'lang/bootstrap/names.dg').read_text(encoding='utf-8')
        old='if s.flags!=1||s.kind==IMPORT{return PRIVATE;}'
        self.assertEqual(source.count(old),1)
        root=self.work/'bad-private';(root/'bootstrap').mkdir(parents=True)
        for p in self.files:
            if p!='names.dg':shutil.copyfile(ROOT/'lang/bootstrap'/p,root/'bootstrap'/p)
        (root/'bootstrap/names.dg').write_text(source.replace(old,'if false{return PRIVATE;}',1),encoding='utf-8')
        c=catalog([(0,'a.dg','module a;import b;'),(0,'b.dg','module b;const hidden:u64=1;')])
        expected=[(0,'b',1,0,1),(1,'hidden',7,0,1)]
        for m in ('debug','release'):
            exe=self.build(root,m,'bad-private-'+m)
            with self.assertRaisesRegex(AssertionError,'lookup'):self.run_cases(exe,[(c,expected,[(0,'b.hidden',6,0)])],'bad-'+m)
            self.records.append(dict(test='actual-bad-Dong',mode=m,rejected_by='lookup',passed=True))

if __name__=='__main__':unittest.main()
