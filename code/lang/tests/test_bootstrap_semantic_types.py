"""Native declaration-type/C3/C4 integration over actual loaded Dong graphs."""
from __future__ import annotations
import hashlib,json,random,shutil,struct,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_source,compile_file
from lang.dongc.model import CompileError
from lang.dongc.frontend import Parser,lex
from lang.dongc.typesys import TypeSystem
from lang.tests import test_bootstrap_modules as graph,test_bootstrap_names as namespace,test_bootstrap_binding as binder
from lang.tests.test_dongc import tool
ROOT=Path(__file__).resolve().parents[2]
NONE=2**64-1
WRAPPER=binder.WRAPPER.replace('module probe;','module probe;\nimport bootstrap.semantic_types as semantic;',1)+'''
export("semantic_check") unsafe fn sem(s:*const modules.Source,sn:usize,u:*const modules.Unit,un:usize,
 t:*const lex.Token,tn:usize,n:*const ast.Node,nn:usize,e:*const modules.Edge,en:usize,sy:*const names.Symbol,yn:usize,
 refs:*const binding.Ref,rn:usize,w:*const semantic.Workspace,depth:usize,r:*semantic.Result)u64{unsafe{
 return semantic.analyze(slice_from_raw_parts(s,sn),slice_from_raw_parts(u,un),slice_from_raw_parts(t,tn),
 slice_from_raw_parts(n,nn),slice_from_raw_parts(e,en),slice_from_raw_parts(sy,yn),slice_from_raw_parts(refs,rn),w,depth,r);
}}
'''
HELPERS=binder.HELPERS.split('static void binding(')[0]+r'''
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/mman.h>
#endif
static void*readonly_copy(const void*p,uint64_t n){
#ifdef _WIN32
 void*q=VirtualAlloc(NULL,n?n:1,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);DWORD previous;
 if(!q){exit(96);}memcpy(q,p,n);if(!VirtualProtect(q,n?n:1,PAGE_READONLY,&previous)){exit(96);}
#else
 void*q=mmap(NULL,n?n:1,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 if(q==MAP_FAILED){exit(96);}memcpy(q,p,n);if(mprotect(q,n?n:1,PROT_READ)){exit(96);}
#endif
 return q;
}
static void readonly_free(const void*p,uint64_t n){
#ifdef _WIN32
 (void)n;VirtualFree((void*)p,0,MEM_RELEASE);
#else
 munmap((void*)p,n?n:1);
#endif
}
typedef struct{uint64_t kind,flags,element,count,first,length,unit,node,alignment;} SType;
typedef struct{uint64_t typ,unit,node;} SField;
typedef struct{uint64_t kind,typ,negative,first,used;} Value;
typedef struct{uint64_t code,types,fields,limbs,unchecked,unit,token,detail;} SResult;
typedef struct{void*p;uint64_t n;} Pool;
typedef struct{Pool pools[24];} Workspace;
extern uint64_t ABI semantic_check(const Source*,uint64_t,const Unit*,uint64_t,const Token*,uint64_t,const Node*,uint64_t,
 const Edge*,uint64_t,const Symbol*,uint64_t,const Ref*,uint64_t,const Workspace*,uint64_t,SResult*);
_Static_assert(sizeof(SType)==72&&sizeof(SField)==24&&sizeof(Value)==40&&sizeof(SResult)==64&&sizeof(Workspace)==384,"semantic ABI");
static void semantic(const Source*s,uint64_t sn,const Unit*u,const Token*t,const Node*n,const Edge*e,const Result*r,const uint64_t*h){
 uint64_t un=r->count,tn=r->tu,nn=r->nu,en=r->eu;
 Symbol*sy=alloc(nn*48),*sw=alloc(nn*48);NamesResult nr;
 if(names_collect(s,sn,u,un,t,tn,n,nn,e,en,sy,nn,sw,nn,&nr)){fprintf(stderr,"namespace failed\n");exit(96);}
 Ref*refs=alloc(nn*32),*rw=alloc(nn*32);Local*locals=alloc(nn*40);NamesResult br;
 if(binding_check(s,sn,u,un,t,tn,n,nn,e,en,sy,nr.count,refs,nn,rw,nn,locals,nn,256,&br)){fprintf(stderr,"binding failed\n");exit(96);}
 const uint64_t width[]={72,24,8,40,1,1,4,1,56,64,4,4,8,8,56,8,16,8,16,8,1,16,8,1};
 uint64_t nt=nn+32,nf=nn*2+32;
 uint64_t caps[]={nt,nf,nn,nn,nn,nn,nn*32+2048,32768,8,8,1024,32768,nt,nt,nt,nf,nt,nf,nt,nf,nt,nt,nf,nt};
 Workspace w;for(int i=0;i<24;i++)w.pools[i]=(Pool){alloc(caps[i]*width[i]),caps[i]};
 uint64_t rm[12];memset(rm,0xa5,sizeof(rm));SResult*out=(SResult*)(rm+2);
 uint64_t sizes[]={un*72,tn*56,nn*64,en*32,nr.count*48,nn*32};const void*inputs[]={u,t,n,e,sy,refs};uint8_t*copies[6];
 for(int i=0;i<6;i++){copies[i]=malloc(sizes[i]+1);memcpy(copies[i],inputs[i],sizes[i]);}
 #define S(W,D,R) semantic_check(s,sn,u,un,t,tn,n,nn,e,en,sy,nr.count,refs,nn,W,D,R)
 for(unsigned i=0;i<11;i++){
  Workspace bad=w;uint64_t code;
  switch(i){
   case 0:code=S(NULL,256,out);break;
   case 1:code=S(&w,256,NULL);break;
   case 2:bad.pools[0].p=NULL;code=S(&bad,256,out);break;
   case 3:bad.pools[0].n=UINT64_MAX;code=S(&bad,256,out);break;
   case 4:bad.pools[0].p=(uint8_t*)bad.pools[0].p+1;code=S(&bad,256,out);break;
   case 5:bad.pools[0].p=(void*)n;bad.pools[0].n=1;code=S(&bad,256,out);break;
   case 6:bad.pools[0].p=bad.pools[1].p;bad.pools[0].n=1;code=S(&bad,256,out);break;
   case 7:code=S(&w,0,out);break;
   case 8:code=S(&w,257,out);break;
   case 9:bad.pools[7].p=(void*)s[0].bytes.p;bad.pools[7].n=1;code=S(&bad,256,out);break;
   default:code=S(&w,256,(SResult*)&w);break;
  }
  if(code!=1||!filled(rm,sizeof(rm))){fprintf(stderr,"semantic invalid %u\n",i);exit(96);}
  for(int j=0;j<24;j++)if(!filled(w.pools[j].p,caps[j]*width[j])){fprintf(stderr,"invalid scratch %u/%u\n",i,j);exit(96);}
 }
 if(h[11]!=UINT64_MAX){if(h[11]>=24||h[12]>caps[h[11]])exit(96);w.pools[h[11]].n=h[12];}
 Workspace saved=w;Source*source_copy=malloc(sn*40+1);memcpy(source_copy,s,sn*40);
 for(uint64_t i=0;i<sn;i++){source_copy[i].path.p=readonly_copy(s[i].path.p,s[i].path.n);source_copy[i].bytes.p=readonly_copy(s[i].bytes.p,s[i].bytes.n);}
 const Source*source_ro=readonly_copy(source_copy,sn*40);const void*ro[6];for(int i=0;i<6;i++)ro[i]=readonly_copy(inputs[i],sizes[i]);
 const Workspace*workspace_ro=readonly_copy(&w,sizeof(w));
 uint64_t code=semantic_check(source_ro,sn,ro[0],un,ro[1],tn,ro[2],nn,ro[3],en,ro[4],nr.count,ro[5],nn,workspace_ro,h[10],out);
 uint64_t good=code==out->code&&!memcmp(&w,&saved,sizeof(w))&&filled(rm,16)&&filled(rm+10,16);
 for(int i=0;i<24;i++)good=good&&guard(w.pools[i].p,caps[i]*width[i]);
 for(int i=0;i<6;i++){good=good&&!memcmp(inputs[i],copies[i],sizes[i]);free(copies[i]);}
 if(code)good=good&&out->types==0&&out->fields==0&&out->limbs==0;
 wr(&code,8);wr(out,64);wr(&good,8);
 if(!code){wr(&nr.count,8);for(uint64_t i=0;i<nr.count;i++){
  Symbol syi=sy[i];uint64_t global=u[syi.unit].ns+syi.decl,typ=((uint64_t*)w.pools[2].p)[global];
  uint64_t size=0,align=0,fc=0;if(typ<out->types){size=((uint64_t*)w.pools[21].p)[2*typ];align=((uint64_t*)w.pools[21].p)[2*typ+1];SType st=((SType*)w.pools[0].p)[typ];if(st.kind==17||st.kind==18)fc=st.length;}
  Value v={0};if(((uint8_t*)w.pools[4].p)[global]==2)v=((Value*)w.pools[3].p)[global];
  uint64_t row[]={u[syi.unit].source,t[u[syi.unit].ts+syi.name].data[1],syi.kind,typ,size,align,v.kind,v.typ,v.negative,v.used,fc};wr(row,sizeof(row));
  if(v.used)wr((uint32_t*)w.pools[6].p+v.first,v.used*4);
  if(fc){SType st=((SType*)w.pools[0].p)[typ];wr((uint64_t*)w.pools[22].p+st.first,fc*8);}
 }}
 readonly_free(workspace_ro,sizeof(w));for(int i=0;i<6;i++){readonly_free(ro[i],sizes[i]);}
 for(uint64_t i=0;i<sn;i++){readonly_free(source_copy[i].path.p,source_copy[i].path.n);readonly_free(source_copy[i].bytes.p,source_copy[i].bytes.n);}
 readonly_free(source_ro,sn*40);free(source_copy);
 for(int i=0;i<24;i++){release(w.pools[i].p);}release(sy);release(sw);release(refs);release(rw);release(locals);
 #undef S
}
'''
HARNESS=graph.HARNESS.replace('int main(void){',HELPERS+'\nint main(void){',1)
HARNESS=HARNESS.replace('uint64_t h[10];rd(h,sizeof(h))','uint64_t h[14];rd(h,sizeof(h))',1)
HARNESS=HARNESS.replace('  uint64_t ok=guard(s,','  if(code){fprintf(stderr,"loader failed %u\\n",(unsigned)code);exit(97);}\n  semantic(s,sn,u,t,n,e,r,h);\n  uint64_t ok=guard(s,',1)
HARNESS=HARNESS.replace('wr(&code,8);wr(r,72);wr(&ok,8);if(!code){wr(u,r->count*72);wr(e,r->eu*32);}','wr(&ok,8);',1)

def case(source,status=0,expected=None,files=None,**limits):
    c=graph.catalog(files or [(0,'a.dg',source)])
    c.update(semantic_depth=256,pool=NONE,cap=0);c.update(limits)
    return c,status,expected or {}

class BootstrapSemanticTypesTests(unittest.TestCase):
    wrapper=WRAPPER
    build=classmethod(namespace.BootstrapNamesTests.build.__func__)
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native semantics requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-semantic-types'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8')
        cls.files=['semantic_types.dg','binding.dg','modules.dg','names.dg','expression.dg','syntax.dg','lexer.dg','unicode.dg',
                   'constant_arithmetic.dg','type_layout.dg','bigint.dg','bigint_div.dg','bigint_bits.dg']
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
        for c,status,expected in cases:
            payload.extend(struct.pack('<14Q',c['roots'],c['entry'],len(c['files']),*[c[k] for k in ('units','tokens','strings','nodes','edges','states','depth')],c['semantic_depth'],c['pool'],c['cap'],0))
            for r,p,b in c['files']:payload.extend(struct.pack('<3Q',r,len(p),len(b)));payload.extend(p);payload.extend(b)
        (self.work/(label+'.input')).write_bytes(payload)
        result=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(result.stdout);(self.work/(label+'.stderr')).write_bytes(result.stderr)
        self.assertEqual(result.returncode,0,result.stderr);at=0
        for c,status,expected in cases:
            returned,code,nt,nf,nl,unchecked,u,t,detail,good=struct.unpack_from('<10Q',result.stdout,at);at+=80
            self.assertEqual(good,1,'guards/immutable input/publication');self.assertEqual(returned,code)
            self.assertEqual(code,status,('status',u,t,detail,c['files']))
            actual={}
            if not code:
                sycount,=struct.unpack_from('<Q',result.stdout,at);at+=8
                for _ in range(sycount):
                    source,start,kind,typ,size,align,vkind,vtyp,negative,used,fc=struct.unpack_from('<11Q',result.stdout,at);at+=88
                    words=struct.unpack_from('<'+'I'*used,result.stdout,at);at+=used*4
                    offsets=struct.unpack_from('<'+'Q'*fc,result.stdout,at);at+=fc*8
                    name=c['files'][source][2][start:].split(b':')[0].split(b'{')[0].split(b'=')[0].split(b'(')[0].split()[0].decode()
                    value=sum(x<<(32*i) for i,x in enumerate(words))*(-1 if negative else 1)
                    actual[(source,name)]=(size,align,offsets,value if vkind else None)
                for name,value in expected.items():
                    key=name if isinstance(name,tuple) else (0,name)
                    self.assertEqual(actual.get(key),value,('value/layout',key,c['files']))
            intact,=struct.unpack_from('<Q',result.stdout,at);at+=8;self.assertEqual(intact,1,'graph integrity')
        self.assertEqual(at,len(result.stdout))
    def test_constants_layout_dependencies_and_aliases(self):
        cases=[case('module a;const X:u64=2+3*4;',expected={'X':(8,8,(),14)}),
            case('module a;struct S{x:u8,y:u64}const X:usize=sizeof(S);const Y:usize=offsetof(S,y);',expected={'S':(16,8,(0,8),None),'X':(8,8,(),16),'Y':(8,8,(),8)}),
            case('module a;const N:usize=2+3;type A=[N]u16;struct S{a:A,b:u8}const X:usize=sizeof(S);',expected={'A':(10,2,(),None),'S':(12,2,(0,10),None),'X':(8,8,(),12)}),
            case('module a;struct S{next:*S,n:u8}type P=?*S;',expected={'S':(16,8,(0,8),None),'P':(16,8,(),None)}),
            case('module a;packed struct S{x:u8,y:u64}type A=[sizeof(S)]u8;',expected={'S':(9,1,(0,1),None),'A':(9,1,(),None)}),
            case('module a;enum E{A,B(u64)}type R=!void;',expected={'E':(16,8,(0,0),None),'R':(16,8,(),None)}),
            case('',files=[(0,'a.dg','module a;import b;const X:usize=sizeof(b.S)+b.N;'),(0,'b.dg','module b;pub struct S{pub x:u64}pub const N:usize=3;')],expected={'X':(8,8,(),11)})]
        rng=random.Random(0x18C3C4)
        for _ in range(80):
            a,b,c=[rng.randrange(1,10000) for _ in range(3)]
            source=f'module a;const A:i64={a};const B:i64=-{b};const X:i64=(A*B+{c})/7;'
            # Python truncation toward zero, independent of native C3 bridge.
            value=-(abs(-a*b+c)//7) if -a*b+c<0 else (-a*b+c)//7
            compile_source(source)
            cases.append(case(source,expected={'X':(8,8,(),value)}))
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'constants-'+mode)
        self.records.append(dict(test='actual-graph-C3-C4',cases=len(cases),modes=2,passed=True))
    def test_invalid_types_cycles_constants_and_budgets(self):
        cases=[case('module a;'+s,z) for s,z in [
            ('type A=B;type B=A;',4),('struct S{x:S}',4),('type A=*A;',4),
            ('type V=void;type P=*V;',3),('type V=void;type S=[]V;',3),('type O=?[]u8;',3),('type R=!noreturn;',3),
            ('type V=void;struct S{x:V}',3),('enum E{A([]u8)}',3),('const N:usize=0;type A=[N]u8;',5),
            ('const N:i64=-1;type A=[N]u8;',5),('type A=[0x7fff_ffff_ffff_ffff]u64;',6),
            ('align(3) struct S{x:u8}',6),('const X:u8=256;',3),('const X:u8=(1 as u8)+255;',3),
            ('const X:u8=(1<<8)-256;',5),('const X:i64=(-9223372036854775808)/(-1);',3),
            ('const X:u64=1/0;',5),('const X:bool=false&&(1/0==0);',5),
            ('const A:u64=B;const B:u64=A;',4),('const X:bool=1;',3),
            ('struct S{x:u64}fn f(x:S)void{}',3),('type V=void;type F=fn(V)void;',3)]]
        for _,status,_ in cases:
            self.assertNotEqual(status,0)
        for pool in (0,1,2,3,4,5,6,7,8,9,10,11,12,14,15,16,21,22,23):
            cases.append(case('module a;struct S{x:u64}const X:u64=1+2;',2,pool=pool,cap=0))
        cases.append(case('module a;const X:u64=1+2;',7,semantic_depth=1))
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'errors-'+mode)
        self.records.append(dict(test='types-cycles-budgets',cases=len(cases),invalid_preflights_per_case=11,modes=2,passed=True))
    def test_typed_constants_and_host_type_layout_oracle(self):
        cases=[]
        for typ,expr,value in [('u8','~0',255),('i8','~0',-1),('u8','255<<1',254),('i8','(-2 as i8)>>1',-1),
                ('u8','(-1) as u8',255),('i8','255 as i8',-1),('u16','true as u16',1),
                ('bool','true&&false',0),('bool','false||true',1),('bool','3<4',1),('bool','(4==4)&&!false',1),
                ('i64','(-17)/5',-3),('i64','(-17)%5',-2),('u64','(1<<63)+1',2**63+1),
                ('u64','0xffff_ffff_ffff_ffff',2**64-1),('u64','(0x'+('f'*200)+')-(0x'+('f'*199)+'e)',1)]:
            source=f'module a;const X:{typ}={expr};';compile_source(source)
            size={'u8':1,'i8':1,'u16':2,'bool':1}.get(typ,8)
            cases.append(case(source,expected={'X':(size,size,(),value)}))
        rng=random.Random(0xC418A)
        for i in range(80):
            size=rng.randrange(1,100);field=rng.choice(['u8','u16','u32','u64','?i8','!void','[]u8','*u16'])
            modifier=rng.choice(['','packed ','align(16) '])
            source=f'module a;const N:usize={size};{modifier}struct S{{a:u8,b:[N]{field},c:u32}}'
            system=TypeSystem(Parser(lex(source.replace('[N]',f'[{size}]'))).parse());expected=system.layout('S')
            cases.append(case(source,expected={'S':(expected.size,expected.alignment,tuple(x.offset for x in expected.fields.values()),None)}))
        good=['type F=fn(?u8,!void)[]u8;', 'enum E{A}type F=extern "win64" fn(E)E;',
              'fn f(x:[]u8)[]u8{return x;}', 'enum E{A,B(u64)}type F=fn(E)E;',
              'struct S{x:u8}type A=[sizeof(S)]u8;align(sizeof(A)*16) struct T{x:A}',
              'fn f()void{const N:usize=3;let a:[N]u8=[1,2,3];}',
              'align(sizeof(*S)) struct S{x:u8}', 'struct S{x:[sizeof(*S)]u8}',
              'struct S{x:[sizeof([]S)]u8}']
        for body in good:compile_source('module a;'+body);cases.append(case('module a;'+body))
        bad=['type F=extern "win64" fn(?u8)void;', 'extern "sysv64" fn f(x:[]u8)void;',
             'enum E{A(u8)}type F=extern "win64" fn(E)void;',
             'type A=[sizeof(S)]u8;struct S{x:A}', 'struct S{x:[sizeof(S)]u8}']
        for body in bad:
            source='module a;'+body
            with self.assertRaises(CompileError):compile_source(source)
            cases.append(case(source,4 if 'sizeof' in body else 3))
        files=[(0,'a.dg','module a;import b;const X:usize=offsetof(b.S,x);'),(0,'b.dg','module b;pub struct S{x:u8}')]
        cases.append(case('',10,files=files))
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'typed-layout-'+mode)
        self.records.append(dict(test='typed-values-host-layout-and-ABI',cases=len(cases),host_layouts=80,modes=2,passed=True))
    def test_actual_bad_C3_bridge_and_C4_offsets_are_rejected(self):
        source=(ROOT/'lang/bootstrap/semantic_types.dg').read_text(encoding='utf-8')
        variants=[('arithmetic','operation(s,op,left,right,&count)','operation(s,1067,left,right,&count)',case('module a;const X:u64=5*6;',expected={'X':(8,8,(),30)})),
                  ('offset','(*w).field_offsets[t.first+f]=(*w).layout_offsets[lt.first+f]','(*w).field_offsets[t.first+f]=0',case('module a;struct S{x:u8,y:u64}',expected={'S':(16,8,(0,8),None)}))]
        for name,old,new,c in variants:
            self.assertEqual(source.count(old),1);root=self.work/('bad-'+name);(root/'bootstrap').mkdir(parents=True)
            for p in self.files:
                if p!='semantic_types.dg':shutil.copyfile(ROOT/'lang/bootstrap'/p,root/'bootstrap'/p)
            (root/'bootstrap/semantic_types.dg').write_text(source.replace(old,new,1),encoding='utf-8')
            for mode in ('debug','release'):
                exe=self.build(root,mode,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'value/layout'):self.run_cases(exe,[c],name+'-'+mode)
                self.records.append(dict(test='actual-bad-Dong',variant=name,mode=mode,rejected_by='value/layout',passed=True))

if __name__=='__main__':unittest.main()
