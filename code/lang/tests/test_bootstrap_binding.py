"""Native lexical/type-name binding, immutable graph and atomic publication."""
from __future__ import annotations
import hashlib,json,random,shutil,struct,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests import test_bootstrap_modules as graph, test_bootstrap_names as namespace
from lang.tests.test_dongc import tool
ROOT=Path(__file__).resolve().parents[2]
NONE=2**64-1
WRAPPER=namespace.WRAPPER+'''
import bootstrap.binding as binding;
export("binding_check") unsafe fn bind(s:*const modules.Source,sn:usize,u:*const modules.Unit,un:usize,
 t:*const lex.Token,tn:usize,n:*const ast.Node,nn:usize,e:*const modules.Edge,en:usize,sy:*const names.Symbol,yn:usize,
 out:*binding.Ref,oc:usize,work:*binding.Ref,wc:usize,locals:*binding.Local,lc:usize,depth:usize,r:*binding.Result)u64{unsafe{
 return binding.check(slice_from_raw_parts(s,sn),slice_from_raw_parts(u,un),slice_from_raw_parts(t,tn),
 slice_from_raw_parts(n,nn),slice_from_raw_parts(e,en),slice_from_raw_parts(sy,yn),slice_from_raw_parts(out,oc),
 slice_from_raw_parts(work,wc),slice_from_raw_parts(locals,lc),depth,r);
}}
'''
# Imports must precede declarations.
WRAPPER=WRAPPER.replace('import bootstrap.binding as binding;\n','').replace('module probe;','module probe;\nimport bootstrap.binding as binding;',1)
HELPERS=r'''
typedef struct{uint64_t unit,name,decl,kind,flags,target;} Symbol;
typedef struct{uint64_t code,count,unit,token,detail;} NamesResult;
typedef struct{uint64_t kind,unit,target,detail;} Ref;
typedef struct{uint64_t unit,token,decl,scope,form;} Local;
extern uint64_t ABI names_collect(const Source*,uint64_t,const Unit*,uint64_t,const Token*,uint64_t,
 const Node*,uint64_t,const Edge*,uint64_t,Symbol*,uint64_t,Symbol*,uint64_t,NamesResult*);
extern uint64_t ABI binding_check(const Source*,uint64_t,const Unit*,uint64_t,const Token*,uint64_t,
 const Node*,uint64_t,const Edge*,uint64_t,const Symbol*,uint64_t,Ref*,uint64_t,Ref*,uint64_t,Local*,uint64_t,uint64_t,NamesResult*);
_Static_assert(sizeof(Ref)==32&&sizeof(Local)==40&&sizeof(NamesResult)==40,"binding ABI");
static void binding(const Source*s,uint64_t sn,const Unit*u,const Token*t,const Node*n,const Edge*e,
 const Result*r,const uint64_t*h){
 uint64_t un=r->count,tn=r->tu,nn=r->nu,en=r->eu;
 Symbol*sy=alloc(nn*48),*sw=alloc(nn*48);NamesResult nr;
 if(names_collect(s,sn,u,un,t,tn,n,nn,e,en,sy,nn,sw,nn,&nr)){fprintf(stderr,"namespace status\n");exit(96);}
 uint64_t oc=h[12]==UINT64_MAX?nn+2:h[12],wc=h[13]==UINT64_MAX?nn+2:h[13],lc=h[11];
 Ref*out=alloc(oc*32),*work=alloc(wc*32);Local*locals=alloc(lc*40);uint64_t rm[9];memset(rm,0xa5,sizeof(rm));NamesResult*res=(NamesResult*)(rm+2);
 uint64_t sizes[]={un*72,tn*56,nn*64,en*32,nr.count*48};const void*inputs[]={u,t,n,e,sy};uint8_t*copies[5];
 for(int i=0;i<5;i++){copies[i]=malloc(sizes[i]+1);memcpy(copies[i],inputs[i],sizes[i]);}
 #define B(O,OC,W,WC,L,LC,D,R) binding_check(s,sn,u,un,t,tn,n,nn,e,en,sy,nr.count,O,OC,W,WC,L,LC,D,R)
 for(unsigned i=0;i<10;i++){
  uint64_t z;
  switch(i){
   case 0:z=B(out,oc,work,wc,locals,lc,256,NULL);break;
   case 1:z=B(NULL,1,work,wc,locals,lc,256,res);break;
   case 2:z=B(out,1,out,1,locals,lc,256,res);break;
   case 3:z=B((Ref*)u,1,work,wc,locals,lc,256,res);break;
   case 4:z=B((Ref*)((uint8_t*)out+1),1,work,wc,locals,lc,256,res);break;
   case 5:z=B(out,oc,work,UINT64_MAX,locals,lc,256,res);break;
   case 6:z=B(out,oc,work,wc,locals,lc,0,res);break;
   case 7:z=B(out,oc,work,wc,locals,lc,257,res);break;
   case 8:z=binding_check(NULL,1,u,un,t,tn,n,nn,e,en,sy,nr.count,out,oc,work,wc,locals,lc,256,res);break;
   default:z=B(out,oc,work,wc,(Local*)sy,1,256,res);break;
  }
  if(z!=1||!filled(out,oc*32)||!filled(work,wc*32)||!filled(locals,lc*40)||!filled(rm,sizeof(rm))){fprintf(stderr,"binding invalid %u\n",i);exit(96);}
 }
 uint64_t code=B(out,oc,work,wc,locals,lc,h[10],res);
 uint64_t good=code==res->code&&guard(out,oc*32)&&guard(work,wc*32)&&guard(locals,lc*40)&&filled(rm,16)&&filled(rm+7,16);
 for(int i=0;i<5;i++){good=good&&!memcmp(inputs[i],copies[i],sizes[i]);free(copies[i]);}
 if(code)good=good&&res->count==0&&filled(out,oc*32);
 else good=good&&res->count==nn&&filled(out+nn,(oc-nn)*32)&&filled(work+nn,(wc-nn)*32);
 wr(&code,8);wr(res,40);wr(&good,8);
 if(!code){
  uint64_t refs=0;for(uint64_t i=0;i<nn;i++)if(out[i].kind)refs++;wr(&refs,8);
  for(uint64_t j=0;j<un;j++){const Unit*v=u+j;for(uint64_t i=0;i<v->nc;i++){
   Ref x=out[v->ns+i];if(!x.kind)continue;
   uint64_t target_source=UINT64_MAX,target_start=UINT64_MAX;
   if(x.kind==1||x.kind==5||x.kind==6){target_source=u[x.unit].source;uint64_t k=n[u[x.unit].ns+x.target].data[1];target_start=t[u[x.unit].ts+k].data[1];}
   if(x.kind==2||x.kind==7){Symbol sym=sy[x.target];target_source=u[sym.unit].source;target_start=t[u[sym.unit].ts+sym.name].data[1];}
   uint64_t k=n[v->ns+i].data[1];uint64_t line[]={v->source,t[v->ts+k].data[1],n[v->ns+i].data[0],x.kind,target_source,target_start,x.detail,x.target};wr(line,sizeof(line));
  }}
 }
 release(sy);release(sw);release(out);release(work);release(locals);
 #undef B
}
'''
HARNESS=graph.HARNESS.replace('int main(void){',HELPERS+'\nint main(void){',1)
HARNESS=HARNESS.replace('uint64_t h[10];rd(h,sizeof(h))','uint64_t h[14];rd(h,sizeof(h))',1)
HARNESS=HARNESS.replace('  uint64_t ok=guard(s,','  if(code){fprintf(stderr,"loader failed %u\\n",(unsigned)code);exit(97);}\n  binding(s,sn,u,t,n,e,r,h);\n  uint64_t ok=guard(s,',1)
HARNESS=HARNESS.replace('wr(&code,8);wr(r,72);wr(&ok,8);if(!code){wr(u,r->count*72);wr(e,r->eu*32);}', 'wr(&ok,8);',1)

def case(source,expected=0,refs=(),files=None,**limits):
    c=graph.catalog(files or [(0,'a.dg',source)])
    c.update(bind_depth=256,locals=100,out=NONE,work=NONE);c.update(limits)
    return c,expected,refs

class BootstrapBindingTests(unittest.TestCase):
    wrapper=WRAPPER
    build=classmethod(namespace.BootstrapNamesTests.build.__func__)
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native binding requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-binding'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8')
        cls.files=['binding.dg','modules.dg','names.dg','expression.dg','syntax.dg','lexer.dg','unicode.dg']
        cls.inputs={p:hashlib.sha256((ROOT/'lang/bootstrap'/p).read_bytes()).hexdigest() for p in cls.files};cls.records=[]
        cls.executables={m:cls.build(ROOT/'lang',m,m) for m in ('debug','release')}
    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        after={p:hashlib.sha256((ROOT/'lang/bootstrap'/p).read_bytes()).hexdigest() for p in cls.files}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,source_stable=cls.inputs==after,
            records=cls.records,complete_semantics=False,L3_selfhost_complete=False,OS_VM_built=False),indent=2)+'\n',encoding='utf-8')
    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c,status,refs in cases:
            payload.extend(struct.pack('<14Q',c['roots'],c['entry'],len(c['files']),*[c[k] for k in ('units','tokens','strings','nodes','edges','states','depth')],*[c[k] for k in ('bind_depth','locals','out','work')]))
            for root,p,b in c['files']:payload.extend(struct.pack('<3Q',root,len(p),len(b)));payload.extend(p);payload.extend(b)
        (self.work/(label+'.input')).write_bytes(payload)
        r=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(r.stdout);(self.work/(label+'.stderr')).write_bytes(r.stderr)
        self.assertEqual(r.returncode,0,r.stderr);at=0
        for c,status,expected in cases:
            z,code,count,unit,token,detail,guard=struct.unpack_from('<7Q',r.stdout,at);at+=56
            self.assertEqual(guard,1,'guard/atomicity');self.assertEqual(z,code);self.assertEqual(z,status,('status',unit,token,detail,c['files']))
            if not z:
                number,=struct.unpack_from('<Q',r.stdout,at);at+=8
                refs=[struct.unpack_from('<8Q',r.stdout,at+64*i) for i in range(number)];at+=64*number
                actual={(f,start,tag):(kind,tf,ts,extra) for f,start,tag,kind,tf,ts,extra,target in refs}
                for key,value in expected:self.assertEqual(actual.get(key),value,('binding',key))
            intact,=struct.unpack_from('<Q',r.stdout,at);at+=8;self.assertEqual(intact,1,'input integrity')
        self.assertEqual(at,len(r.stdout))
    def test_scope_targets_and_cross_module_types(self):
        cases=[];rng=random.Random(0x106B06)
        for _ in range(50):
            s='module a;fn f(x:u64)u64{var sum:u64=x;';refs=[]
            # Each expected edge is produced while independently emitting its use,
            # before either parser or binder runs. Nested scopes reuse x.
            outer=s.index('x:u64');refs.append(((0,s.rindex('x;'),5),(1,0,outer,261)))
            for j in range(rng.randrange(1,8)):
                s+='{let x:u64='+str(rng.randrange(1000))+';sum+=x;'
                decl=s.rindex('x:u64');use=s.rindex('x;');refs.append(((0,use,5),(1,0,decl,261)))
            s+='}'*s.count('{',s.index('var sum'))+'return sum;}'
            refs.append(((0,s.rindex('sum;'),5),(1,0,s.index('sum:u64'),262)))
            cases.append(case(s,refs=refs))
        a='module a;import b as lib;fn f(x:lib . S)lib . Word{return x.field;}';b='module b;pub struct S{pub field:u64}pub type Word=u64;'
        cases.append(case('',files=[(0,'a.dg',a),(0,'b.dg',b)]))
        cases.append(case('',files=[(0,'a.dg','module a;import b;fn f(p:*b.B)u64{return b.get(p);}'),
             (0,'b.dg','module b;struct A{x:u64}pub struct B{x:u64}fn(self:*A)get()u64{return 1;}pub fn(self:*B)get()u64{return 2;}')]))
        for s in ['module a;fn g()void{}fn f()void{for x in 0..3{let x:u64=1;g();}loop{break;}defer g();}',
                  'module a;enum E{A,B(u64)}fn f(e:E)u64{match e{E.A=>{return 0;},E.B(x)=>{return x;}}}',
                  'module a;fn f()u64{let x:?u64=some(1);return x orelse return 0;}',
                  'module a;const A:usize=16;align(A) struct S{x:u64}fn f(p:*S)u64{unsafe{return (*p).x;}}',
                  'module a;struct S{x:u64}fn(self:*S)get()u64{unsafe{return (*self).x;}}fn f(p:*S)u64{return get(p);}',
                  'module a;fn f()u64{var a=[1,2];for x in a{a[0]+=x;}return a[0];}']:
            cases.append(case(s))
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'scopes-'+mode)
        self.records.append(dict(test='scope-type-import-targets',cases=len(cases),modes=2,passed=True))
    def test_semantic_errors_depth_and_capacity(self):
        bodies=[('fn f()u64{return missing;}',3),('fn f(x:u64)void{let x:u64=1;}',6),
                ('fn f()void{let x:u64=x;}',3),('fn f()void{{let x:u64=1;}x();}',3),
                ('fn f()void{break;}',7),('fn f()void{continue;}',7),('fn f()void{defer {return;}}',7),
                ('fn f()void{defer {defer f();}}',7),('const T:u64=1;fn f(x:T)void{}',5),
                ('fn f(x:Missing)void{}',3),('fn f()void{for i in 0..1{}wrapping_add(i,1);}',3),
                ('struct S{x:u64}fn f()void{let x=S{x:1,x:2};}',6)]
        cases=[case('module a;'+s,status) for s,status in bodies]
        cases.append(case('',4,files=[(0,'a.dg','module a;import b;fn f(x:b.S)void{}'),(0,'b.dg','module b;struct S{x:u64}')]))
        simple='module a;fn f(x:u64)u64{return x;}'
        for key in ('locals','out','work'):cases.append(case(simple,2,**{key:0}))
        cases.append(case(simple,8,bind_depth=1))
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'errors-'+mode)
        self.records.append(dict(test='errors-capacity-depth',cases=len(cases),invalid_preflights_per_process=10,modes=2,passed=True))
    def test_actual_bootstrap_module_graphs(self):
        files=[(0,'bootstrap/'+p.name,p.read_bytes()) for p in sorted((ROOT/'lang/bootstrap').glob('*.dg'))
               if p.name not in {'source_position.dg'}]
        cases=[case('',files=files,entry=i) for i in range(len(files))]
        # entry is a module-loader budget, not a binder limit.
        for i,(c,status,refs) in enumerate(cases):c['entry']=i
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'real-bootstrap-'+mode)
        self.records.append(dict(test='actual-bootstrap-graphs',entry_modules=len(files),modes=2,passed=True))
    def test_actual_bad_nearest_scope_and_control_checks_are_rejected(self):
        source=(ROOT/'lang/bootstrap/binding.dg').read_text(encoding='utf-8')
        s='module a;fn f(x:u64)u64{{let x:u64=1;return x;}}'
        refs=[((0,s.rindex('x;'),5),(1,0,s.rindex('x:u64'),261))]
        variants=[('nearest','if equal(t,text(s,l.unit,l.token)){return i;}','if equal(t,text(s,l.unit,l.token)){return 0;}',case(s,refs=refs),'binding'),
                  ('loop','if op!=281&&(*s).loops==0{return reject(s,CONTROL,token,0);}','if false{return reject(s,CONTROL,token,0);}',case('module a;fn f()void{break;}',7),'status')]
        for name,old,new,c,assertion in variants:
            self.assertEqual(source.count(old),1);root=self.work/('bad-'+name);(root/'bootstrap').mkdir(parents=True)
            for p in self.files:
                if p!='binding.dg':shutil.copyfile(ROOT/'lang/bootstrap'/p,root/'bootstrap'/p)
            (root/'bootstrap/binding.dg').write_text(source.replace(old,new,1),encoding='utf-8')
            for mode in ('debug','release'):
                exe=self.build(root,mode,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,assertion):self.run_cases(exe,[c],name+'-'+mode)
                self.records.append(dict(test='actual-bad-Dong',variant=name,mode=mode,rejected_by=assertion,passed=True))

if __name__=='__main__':unittest.main()
