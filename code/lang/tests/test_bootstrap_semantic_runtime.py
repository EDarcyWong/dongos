"""Native runtime type/flow checking over real lexer/module/binding graphs."""
from __future__ import annotations
import hashlib,json,random,shutil,struct,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_source
from lang.dongc.model import CompileError
from lang.tests import test_bootstrap_semantic_types as decl
from lang.tests.test_dongc import tool
ROOT=decl.ROOT
NONE=decl.NONE
WRAPPER=decl.WRAPPER.replace('w:*const semantic.Workspace,depth:usize,r:*semantic.Result)',
 'w:*const semantic.Workspace,rw:*const semantic.RuntimeWorkspace,depth:usize,r:*semantic.Result)')
WRAPPER=WRAPPER.replace('return semantic.analyze(', 'return semantic.analyze_program(').replace('slice_from_raw_parts(refs,rn),w,depth,r);','slice_from_raw_parts(refs,rn),w,rw,depth,r);')
HARNESS=decl.HARNESS.replace('typedef struct{Pool pools[24];} Workspace;',
 'typedef struct{Pool pools[24];} Workspace;\ntypedef struct{Pool pools[5];} RuntimeWorkspace;')
HARNESS=HARNESS.replace('const Ref*,uint64_t,const Workspace*,uint64_t,SResult*);','const Ref*,uint64_t,const Workspace*,const RuntimeWorkspace*,uint64_t,SResult*);')
HARNESS=HARNESS.replace(' Workspace w;for(int i=0;i<24;i++)',r'''
 const uint64_t fwidth[]={24,1,1,1,1},fcaps[]={nn,nn,nn*512,nn*256,256};RuntimeWorkspace flow;
 for(int i=0;i<5;i++){flow.pools[i]=(Pool){alloc(fcaps[i]*fwidth[i]),fcaps[i]};}
 Workspace w;for(int i=0;i<24;i++)''')
HARNESS=HARNESS.replace('refs,nn,W,D,R)', 'refs,nn,W,&flow,D,R)')
HARNESS=HARNESS.replace(' if(h[11]!=UINT64_MAX){if(h[11]>=24||h[12]>caps[h[11]])exit(96);w.pools[h[11]].n=h[12];}',r'''
 for(unsigned i=0;i<9;i++){
  RuntimeWorkspace bad=flow;uint64_t code;
  switch(i){
   case 0:code=semantic_check(s,sn,u,un,t,tn,n,nn,e,en,sy,nr.count,refs,nn,&w,NULL,256,out);break;
   case 1:bad.pools[0].p=NULL;code=semantic_check(s,sn,u,un,t,tn,n,nn,e,en,sy,nr.count,refs,nn,&w,&bad,256,out);break;
   case 2:bad.pools[0].n=UINT64_MAX;code=semantic_check(s,sn,u,un,t,tn,n,nn,e,en,sy,nr.count,refs,nn,&w,&bad,256,out);break;
   case 3:bad.pools[0].p=(uint8_t*)bad.pools[0].p+1;code=semantic_check(s,sn,u,un,t,tn,n,nn,e,en,sy,nr.count,refs,nn,&w,&bad,256,out);break;
   case 4:bad.pools[0].p=w.pools[0].p;bad.pools[0].n=1;code=semantic_check(s,sn,u,un,t,tn,n,nn,e,en,sy,nr.count,refs,nn,&w,&bad,256,out);break;
   case 5:bad.pools[1]=bad.pools[2];code=semantic_check(s,sn,u,un,t,tn,n,nn,e,en,sy,nr.count,refs,nn,&w,&bad,256,out);break;
   case 6:bad.pools[1].p=(void*)s[0].bytes.p;bad.pools[1].n=1;code=semantic_check(s,sn,u,un,t,tn,n,nn,e,en,sy,nr.count,refs,nn,&w,&bad,256,out);break;
   case 7:code=semantic_check(s,sn,u,un,t,tn,n,nn,e,en,sy,nr.count,refs,nn,&w,&bad,256,(SResult*)&bad);break;
   default:code=semantic_check(s,sn,u,un,t,tn,n,nn,e,en,sy,nr.count,refs,nn,&w,(RuntimeWorkspace*)w.pools[0].p,256,out);break;
  }
  if(code!=1||!filled(rm,sizeof(rm))){fprintf(stderr,"runtime invalid %u\n",i);exit(96);}
  for(int j=0;j<24;j++){if(!filled(w.pools[j].p,caps[j]*width[j]))exit(96);}
  for(int j=0;j<5;j++){if(!filled(flow.pools[j].p,fcaps[j]*fwidth[j]))exit(96);}
 }
 if(h[11]<24){if(h[12]>caps[h[11]])exit(96);w.pools[h[11]].n=h[12];}
 if(h[11]>=24&&h[11]<29){flow.pools[h[11]-24].n=h[12];}
''')
# Invalid 9 uses a real descriptor inside original scratch, with valid fields,
# so descriptor-alias rejection is reached before original scratch can change.
HARNESS=HARNESS.replace('default:code=semantic_check(s,sn,u,un,t,tn,n,nn,e,en,sy,nr.count,refs,nn,&w,(RuntimeWorkspace*)w.pools[0].p,256,out);break;',
 'default:bad.pools[0].p=(void*)u;bad.pools[0].n=1;code=semantic_check(s,sn,u,un,t,tn,n,nn,e,en,sy,nr.count,refs,nn,&w,&bad,256,out);break;')
HARNESS=HARNESS.replace('const Workspace*workspace_ro=readonly_copy(&w,sizeof(w));','const Workspace*workspace_ro=readonly_copy(&w,sizeof(w));\n const RuntimeWorkspace*flow_ro=readonly_copy(&flow,sizeof(flow));')
HARNESS=HARNESS.replace('ro[5],nn,workspace_ro,h[10],out)', 'ro[5],nn,workspace_ro,flow_ro,h[10],out)')
HARNESS=HARNESS.replace(' for(int i=0;i<24;i++)good=good&&guard',r'''
 good=good&&out->unchecked==0;
 for(int i=0;i<5;i++){good=good&&guard(flow.pools[i].p,fcaps[i]*fwidth[i])&&filled((uint8_t*)flow.pools[i].p+flow.pools[i].n*fwidth[i],(fcaps[i]-flow.pools[i].n)*fwidth[i]);}
 for(int i=0;i<24;i++)good=good&&guard''')
HARNESS=HARNESS.replace(' readonly_free(workspace_ro,sizeof(w));', ' readonly_free(flow_ro,sizeof(flow));for(int i=0;i<5;i++){release(flow.pools[i].p);}\n readonly_free(workspace_ro,sizeof(w));')

def memory_intrinsic_cases():
    items=[]
    for typ in ('u8','u16','u32','u64','i8','i16','i32','i64'):
        for name in ('volatile_load','read_unaligned'):
            items.append((f'fn f(p:*const {typ}){typ}{{unsafe{{return {name}(p);}}}}',0))
        for name in ('volatile_store','write_unaligned'):
            items.append((f'fn f(p:*{typ},x:{typ})void{{unsafe{{{name}(p,x);}}}}',0))
    for typ in ('u32','u64'):
        items.extend([
          (f'fn f(p:*const {typ}){typ}{{unsafe{{return atomic_load(p);}}}}',0),
          (f'fn f(p:*{typ},x:{typ})void{{unsafe{{atomic_store(p,x);}}}}',0),
          (f'fn f(p:*{typ},x:{typ}){typ}{{unsafe{{return atomic_fetch_add(p,x);}}}}',0),
          (f'fn f(p:*{typ},x:{typ},y:{typ}){typ}{{unsafe{{return atomic_compare_exchange(p,x,y);}}}}',0)])
    items.extend([
      ('fn f()void{unsafe{compiler_fence();}}',0),
      ('fn f(p:*u8)void{unsafe{volatile_store(p,255);write_unaligned(p,0);}}',0),
      ('fn f(p:*i8)void{unsafe{volatile_store(p,-128);write_unaligned(p,127);}}',0),
      ('fn volatile_load(x:u64)u64{return x;}fn f()u64{return volatile_load(3);}',0),
      ('fn f(volatile_load:fn(u64)u64)u64{unsafe{return volatile_load(3);}}',0),
      ('fn die()noreturn{loop{}}fn f(p:*u32)u64{unsafe{atomic_store(p,die());}}',0),
      ('fn f()void{compiler_fence();}',13),
      ('fn f(p:u64)u64{unsafe{return volatile_load(p);}}',3),
      ('fn f(p:*bool)bool{unsafe{return read_unaligned(p);}}',3),
      ('fn f(p:**u64)*u64{unsafe{return volatile_load(p);}}',3),
      ('fn f(p:*i32)i32{unsafe{return atomic_load(p);}}',3),
      ('fn f(p:*u8)u8{unsafe{return atomic_fetch_add(p,1);}}',3),
      ('fn f(p:*u64,x:u32)void{unsafe{volatile_store(p,x);}}',3),
      ('fn f(p:*u8)void{unsafe{volatile_store(p,256);}}',3),
      ('fn f(p:*u8)void{unsafe{write_unaligned(p,-1);}}',3),
      ('fn f(p:*u32)bool{unsafe{return atomic_compare_exchange(p,0,1);}}',3),
      ('fn f(p:*u32)u32{unsafe{return atomic_compare_exchange(p,true,1);}}',3),
      ('fn f()u64{unsafe{return compiler_fence();}}',3),
      ('fn f(p:*u32)void{unsafe{volatile_store(p,true);}}',3),
      ('fn die()noreturn{loop{}}fn f(p:*u32)u64{unsafe{return atomic_compare_exchange(p,die(),true);}}',3),
      ('fn f(p:*u32)u32{var x:u32;unsafe{return atomic_compare_exchange(p,x,1);}}',11),
    ])
    for name,call in [('volatile_load','volatile_load(p)'),('read_unaligned','read_unaligned(p)'),
                      ('atomic_load','atomic_load(p)'),('volatile_store','volatile_store(p,1)'),
                      ('write_unaligned','write_unaligned(p,1)'),('atomic_store','atomic_store(p,1)'),
                      ('atomic_compare_exchange','atomic_compare_exchange(p,0,1)'),
                      ('atomic_fetch_add','atomic_fetch_add(p,1)')]:
        items.append((f'fn f(p:*u32)void{{{call};}}',13))
    for call in ('volatile_load()','volatile_load(p,1)','read_unaligned()',
                 'volatile_store(p)','write_unaligned(p,1,2)','atomic_load(p,1)',
                 'atomic_store()','atomic_compare_exchange(p,0)',
                 'atomic_compare_exchange(p,0,1,2)','atomic_fetch_add(p)','compiler_fence(1)'):
        items.append((f'fn f(p:*u32)void{{unsafe{{{call};}}}}',3))
    for call in ('volatile_store(p,1)','write_unaligned(p,1)','atomic_store(p,1)',
                 'atomic_compare_exchange(p,0,1)','atomic_fetch_add(p,1)'):
        items.append((f'fn f(p:*const u32)void{{unsafe{{{call};}}}}',12))
    return items


def tagged_flow_cases():
    items=[]
    for typ in ('u8','u16','u32','u64','i8','i16','i32','i64'):
        items.extend([
          (f'fn f(x:?{typ}){typ}{{return x orelse 1;}}',0),
          (f'fn f(x:!{typ})!{typ}{{return try x;}}',0),
          (f'fn f(x:{typ})?{typ}{{return x;}}',0),
          (f'fn f(x:{typ})!{typ}{{return x;}}',0),
          (f'fn f(x:?{typ}){typ}{{let n=x orelse return 1;return n;}}',0),
          (f'fn f(x:!{typ}){typ}{{return try x;}}',15),
          (f'fn f(x:{typ}){typ}{{return x orelse 1;}}',3),
        ])
    items.extend([
      ('fn f(x:?bool)bool{return x orelse false;}',0),
      ('fn f(x:!bool)!bool{return try x;}',0),
      ('fn f(x:?*u8)*u8{return x orelse null;}',0),
      ('fn f(x:!*u8)!*u8{return try x;}',0),
      ('fn f(x:?fn()u8,y:fn()u8)fn()u8{return x orelse y;}',0),
      ('fn f(x:!fn()u8)!fn()u8{return try x;}',0),
      ('type O=?u8;type R=!u8;fn f(x:O,y:R)!u8{return (try y)+(x orelse 0);}',0),
      ('fn g()!void{return;}fn f()!void{try g();return;}',0),
      ('fn g()!u8{return 1;}fn f()!u16{return (try g()) as u16;}',0),
      ('fn f(x:?u8)!void{let n=x orelse return;return;}',0),
      ('fn f(x:?u8)!u8{return x orelse return 1;}',0),
      ('fn f(x:?u8,y:?u8)u8{return x orelse y orelse 1;}',0),
      ('fn f(x:?u8)u64{var n:u64=0;loop{let y=x orelse break;n=y as u64;break;}return n;}',0),
      ('fn f(x:?u8)void{loop{let y=x orelse continue;break;}}',0),
      ('fn die()noreturn{loop{}}fn f(x:?u8)u8{return x orelse die();}',0),
      ('const O:?u64=1;fn f()noreturn{loop{let n=O orelse break;}}',0),
      ('fn f()noreturn{const O:?u64=1;loop{let n=O orelse break;}}',0),
      ('const O:?u64=null;fn die()noreturn{loop{}}fn f()u64{let n=O orelse die();}',0),
      ('const O:?u64=1;fn die()noreturn{loop{}}fn f()u64{return O orelse die();}',0),
      ('const O:?u64=null;fn f()u64{var x:u64;loop{let n=O orelse break;x=1;}return x;}',11),
      ('const O:?u64=1;fn f()noreturn{loop{let n=1+(O orelse break);}}',0),
      ('const O:?bool=true;fn f()noreturn{loop{let n=false&&(O orelse break);}}',0),
      ('const O:?bool=null;fn f()noreturn{loop{let n=false&&(O orelse break);}}',0),
      ('const O:?u64=null;fn die()noreturn{loop{}}fn use(a:u64,b:u64)void{}fn f()noreturn{loop{use(die(),O orelse break);}}',0),
      ('fn f(x:?u8)u8{defer {let n=x orelse 1;}return 0;}',0),
      ('fn f(x:?u8)u8{var y:u8;return x orelse y;}',11),
      ('fn f(x:?u8)u8{let y=x orelse return true;return y;}',3),
      ('fn f(x:?u8)void{let y=x orelse return 1;}',3),
      ('fn f(x:?u8)u8{let y=x orelse return;return y;}',3),
      ('fn f(x:?u8)noreturn{loop{let y=x orelse return;}}',14),
      ('fn f(x:!u8)!u8{defer {let y=try x;}return 0;}',15),
      ('fn f(x:?u8)!u8{return try x;}',3),
      ('fn f()!u8{return try 1;}',3),
      ('fn g()!u8{return 1;}fn f()void{g();}',3),
      ('fn g()!void{return;}fn f()void{g();}',3),
      ('fn f(x:?u8)u8{return x orelse 256;}',3),
      ('fn f(x:!u8)!u16{return try x;}',3),
      ('fn f(x:!void)!u8{let n=try x;return 1;}',3),
      ('fn f(x:?u8)u8{var y:u8;loop{let n=x orelse break;y=1;break;}return y;}',11),
    ])
    return items

class BootstrapSemanticRuntimeTests(unittest.TestCase):
    wrapper=WRAPPER
    build=decl.BootstrapSemanticTypesTests.__dict__['build']
    run_cases=decl.BootstrapSemanticTypesTests.run_cases
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native runtime checking requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-semantic-runtime'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8')
        cls.files=['semantic_types.dg','binding.dg','modules.dg','names.dg','expression.dg','syntax.dg','lexer.dg','unicode.dg',
                   'constant_arithmetic.dg','type_layout.dg','bigint.dg','bigint_div.dg','bigint_bits.dg']
        cls.inputs={p:hashlib.sha256((ROOT/'lang/bootstrap'/p).read_bytes()).hexdigest() for p in cls.files};cls.records=[]
        cls.executables={m:cls.build(ROOT/'lang',m,m) for m in ('debug','release')}
    tearDownClass=decl.BootstrapSemanticTypesTests.__dict__['tearDownClass']
    def cases(self,items):
        cases=[]
        for body,status in items:
            source='module a;'+body
            try:compile_source(source);host=True
            except CompileError:host=False
            self.assertEqual(host,status==0,('host acceptance',source,status))
            cases.append(decl.case(source,status))
        return cases
    def test_runtime_values_calls_and_places(self):
        items=[('fn add(a:u64,b:u64)u64{return a+b;}fn f()u64{return add(2,3);}',0),
          ('fn f(x:u8)u8{return x+1;}',0),('fn f(x:u64)bool{return x==1;}',0),
          ('fn f()i64{var x=1;x+=2;return x;}',0),('fn f(p:*u64)u64{unsafe{*p=3;return *p;}}',0),
          ('fn f(p:*const u64)u64{unsafe{return p[0];}}',0),
          ('struct S{x:u64,y:u8}fn f()u64{var s=S{x:1,y:2};s.x=4;return s.x;}',0),
          ('fn f()i64{var a=[1,2,3];a[1]=4;return a[1];}',0),
          ('fn f()u8{let a:[3]u8=[1;3];return a[2];}',0),
          ('fn f(s:[]u8)u8{s[0]=1;return s[0];}',0),('fn f(s:[]const u8)usize{return s.len;}',0),
          ('fn f(p:*u8,n:usize)[]u8{unsafe{return slice_from_raw_parts(p,n);}}',0),
          ('fn f(x:u64)u64{return wrapping_add(x,1);}',0),
          ('unsafe fn g()u64{return 1;}fn f()u64{unsafe{return g();}}',0),
          ('fn f(g:fn(u64)u64)u64{unsafe{return g(3);}}',0),
          ('fn f(x:u64)u8{return x as u8;}',0),('fn f(p:*u8)*const u8{return p;}',0),
          ('fn f(x:u64)bool{return x;}',3),('fn f(x:bool)u64{return x+1;}',3),
          ('fn g(x:u8)void{}fn f()void{g(256);}',3),('fn g(x:u64)void{}fn f()void{g();}',3),
          ('fn f()u64{let x:u64=1;x=2;return x;}',12),
          ('fn f(p:*const u64)void{unsafe{*p=1;}}',12),
          ('fn f(s:[]const u8)void{s[0]=1;}',12),
          ('fn f(p:*u64)u64{return *p;}',13),('fn f(p:*u8)*u8{return p+1;}',13),
          ('unsafe fn g()void{}fn f()void{g();}',13),('fn f(g:fn()void)void{g();}',13),
          ('fn f(x:u64)*u8{return x as *u8;}',13),
          ('fn f()i64{let a=[1,2];return a[2];}',3),('fn f(x:u8)u8{return x<<8;}',3),
          ('fn f(x:u64)u64{return x/0;}',3),('fn f()void{var x:u8=1;x/=0;}',3),
          ('fn g()u64{return 1;}fn f()void{return;let x:bool=g();}',3),
          ('fn f()u8{return "a"[1];}',3),('fn f()u8{return ""[0];}',3),
          ('fn f()u8{return "中"[2];}',0),
          ('fn f()i64{return wrapping_add(-9223372036854775808,0)/(-1);}',3),
          ('fn f()u64{return wrapping_add(1,2)+1;}',0),
          ('fn f()u8{return wrapping_add(255,1)+1;}',0),
          ('fn f(x:u64)u64{return wrapping_add(1,2)+x;}',0),
          ('fn f()u8{return wrapping_add(255,1)+256;}',3),
          ('fn f()i64{return -wrapping_add(1,2);}',0),
          ('fn f()u8{return ~wrapping_add(255,1);}',0),
          ('enum E{A,B}fn f(a:E,b:E)bool{return a==b;}',0),
          ('enum E{A(u8),B}fn f(a:E,b:E)bool{return a==b;}',3)]
        cases=self.cases(items)
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'runtime-'+mode)
        self.records.append(dict(test='runtime-host-acceptance',cases=len(cases),modes=2,passed=True))
    def test_flow_initialization_reachability_and_cleanup(self):
        items=[('fn f(b:bool)u64{var x:u64;if b{x=1;}else{x=2;}return x;}',0),
          ('fn f()u64{var x:u64;if true{x=1;}return x;}',0),
          ('fn f(b:bool)u64{var x:u64;if b{return 1;}else{x=2;}return x;}',0),
          ('fn f()u64{var x:u64;loop{x=1;break;}return x;}',0),
          ('fn f()u64{var x:u64;while true{x=1;break;}return x;}',0),
          ('fn f()u64{loop{continue;}}',0),('fn f(b:bool)u64{match b{true=>{return 1;},false=>{return 2;}}}',0),
          ('fn f()u64{var x:u64;match true{true=>{x=1;},false=>{}}return x;}',0),
          ('fn g(x:u64)void{}fn f()void{let x:u64=1;defer g(x);}',0),
          ('fn f()void{defer {var x:u64;x=1;}}',0),
          ('fn f()u64{var x:u64;if true{x=1;return x;}else{loop{break;}}}',0),
          ('fn f()u64{var x:u64;return x;}',11),('fn f(b:bool)u64{var x:u64;if b{x=1;}return x;}',11),
          ('fn f()u64{var x:u64;while false{x=1;}return x;}',11),
          ('fn f(b:bool)u64{var x:u64;while b{x=1;break;}return x;}',11),
          ('fn f(b:bool)u64{var x:u64;loop{if b{break;}x=1;break;}return x;}',11),
          ('struct S{x:u64}fn f()u64{var s:S;s.x=1;return s.x;}',11),
          ('fn f(b:bool)u64{if b{return 1;}}',14),('fn f()noreturn{return;}',14),
          ('fn f(b:bool)u64{match b{true=>{return 1;}}}',15),
          ('fn g(x:u64)void{}fn f()void{var x:u64;defer g(x);x=1;}',11),
          ('fn f()void{var x:u64;defer {x=1;}}',11),
          ('fn f(b:bool)u64{var x:u64;if false&&b{}else{x=1;}return x;}',0),
          ('fn f(b:bool)u64{var x:u64;if true||b{x=1;}return x;}',0),
          ('fn f()u64{var x:u64;if wrapping_add(1,2)==3{x=4;}return x;}',0)]
        rng=random.Random(0x18F10)
        for _ in range(80):
            yes,no=rng.choice([True,False]),rng.choice([True,False])
            body='fn f(b:bool)u64{var x:u64;if b{'+('x=1;' if yes else '')+'}else{'+('x=2;' if no else '')+'}return x;}'
            items.append((body,0 if yes and no else 11))
        cases=self.cases(items)
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'flow-'+mode)
        self.records.append(dict(test='flow-host-acceptance',cases=len(cases),modes=2,passed=True))
    def test_slices_bounds_readonly_and_place_alignment(self):
        items=[
          ('fn f(s:[]u8)[]u8{return s[0..1];}',0),
          ('fn f(s:[]u8)[]u8{return s[..];}',0),
          ('fn f(s:[]u8)[]u8{return s[1..];}',0),
          ('fn f(s:[]u8)[]u8{return s[..1];}',0),
          ('fn f(s:[]u8,l:usize,h:usize)[]u8{return s[l..h];}',0),
          ('fn f(s:[]u8)[]u8{return s[1..1];}',0),
          ('fn f(s:[]u8,l:usize)[]u8{return s[l..0];}',0),
          ('fn f(s:[]const u64)[]const u64{return s[0..0];}',0),
          ('fn f()[]const u8{return ""[..];}',0),
          ('fn f()u8{return "中"[1..3][1];}',0),
          ('fn f()u64{var a:[4]u64=[1;4];return a[1..][0];}',0),
          ('fn f()[]u8{var a:[4]u8=[1;4];return a[4..4];}',0),
          ('fn f()void{var a=[1,2];a[..][0]=3;}',0),
          ('fn f()[]const i64{let a=[1,2];return a[..];}',0),
          ('fn f()[]const i64{var a=[1,2];return a[..];}',0),
          ('struct S{a:[2]u64}fn f()u64{var s=S{a:[1;2]};return s.a[..][0];}',0),
          ('packed struct S{x:u8,a:[2]u8}fn f()u8{var s=S{x:0,a:[1;2]};return s.a[..][0];}',0),
          ('packed struct P{a:[2]u64}struct S{pad:u64,p:P}fn f()u64{var s=S{pad:0,p:P{a:[1;2]}};return s.p.a[..][0];}',0),
          ('fn f()u64{var a:[2][2]u64=[[1;2];2];return a[1][..][0];}',0),
          ('fn f(s:[]u8)[]u8{return s[2..1];}',3),
          ('fn f()[]const u8{return "abc"[0..4];}',3),
          ('fn f()[]const u8{return "abc"[4..];}',3),
          ('fn f(s:[]u8)[]u8{return s[-1..];}',3),
          ('fn f(s:[]u8)[]u8{return s[..true];}',3),
          ('fn f(s:[]u8,l:i64)[]u8{return s[l..];}',3),
          ('fn f(s:[]const u8)[]u8{return s[..];}',3),
          ('fn f()void{let a=[1,2];a[..][0]=3;}',12),
          ('fn f(s:[]u8)void{s[0..1][1]=2;}',3),
          ('fn f()u8{return "中"[1..3][2];}',3),
          ('fn f()[]const i64{return [1,2][..];}',3),
          ('fn f(x:u64)[]u8{return x[..];}',3),
          ('fn f(p:*u8)[]u8{unsafe{return p[0..1];}}',3),
          ('packed struct S{x:u8,a:[2]u64}fn f()u64{var s=S{x:0,a:[1;2]};return s.a[..][0];}',3),
          ('packed struct S{a:[2]u64}fn f()u64{var s=S{a:[1;2]};return s.a[..][0];}',3),
          ('fn f()u64{var a:[2]u64;return a[..][0];}',11),
          ('fn die()noreturn{loop{}}fn f(s:[]u8)u64{let view=s[die()..1];}',0),
          ('fn die()noreturn{loop{}}fn f(s:[]u8)u64{let view=s[0..die()];}',0),
        ]
        cases=self.cases(items)
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'slices-'+mode)
        self.records.append(dict(test='slice-host-acceptance',cases=len(cases),modes=2,passed=True))

    def test_memory_intrinsics_types_arity_and_permissions(self):
        cases=self.cases(memory_intrinsic_cases())
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'memory-intrinsics-'+mode)
        self.records.append(dict(test='memory-intrinsics-host-acceptance',cases=len(cases),modes=2,passed=True))

    def test_tagged_unwrap_types_and_control_flow(self):
        cases=self.cases(tagged_flow_cases())
        files=[(0,'a.dg','module a;import b;fn f()noreturn{loop{let n=b.PRESENT orelse break;}}'),
               (0,'b.dg','module b;pub const PRESENT:?u64=1;')]
        host=self.work/'tagged-host-modules';host.mkdir()
        for _,path,body in files:(host/path).write_text(body,encoding='utf-8')
        decl.compile_file(host/'a.dg',roots=[host])
        cases.append(decl.case('',files=files))
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'tagged-flow-'+mode)
        self.records.append(dict(test='tagged-flow-host-acceptance',cases=len(cases),modes=2,passed=True))

    def test_tagged_unwrap_actual_wrong_flow_is_rejected(self):
        source=(ROOT/'lang/bootstrap/semantic_types.dg').read_text(encoding='utf-8')
        variants=[
          ('try-context','if (*c).in_defer||rt_kind(c,(*c).returns)!=RESULT',
           'if (*c).in_defer',decl.case('module a;fn f(x:!u8)u8{return try x;}',15)),
          ('orelse-live','(*c).live=live&&tag!=1;',
           '(*c).live=live;',decl.case('module a;const O:?u64=1;fn f()noreturn{loop{let n=O orelse break;}}')),
        ]
        for name,old,new,case in variants:
            self.assertEqual(source.count(old),1);root=self.work/('bad-'+name);(root/'bootstrap').mkdir(parents=True)
            for p in self.files:
                if p!='semantic_types.dg':shutil.copyfile(ROOT/'lang/bootstrap'/p,root/'bootstrap'/p)
            (root/'bootstrap/semantic_types.dg').write_text(source.replace(old,new,1),encoding='utf-8')
            for mode in ('debug','release'):
                self.run_cases(self.executables[mode],[case],name+'-good-'+mode)
                exe=self.build(root,mode,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'status'):self.run_cases(exe,[case],name+'-'+mode)
                self.records.append(dict(test='actual-bad-Dong',variant=name,mode=mode,rejected_by='status',passed=True))

    def test_memory_intrinsics_actual_wrong_permissions_are_rejected(self):
        source=(ROOT/'lang/bootstrap/semantic_types.dg').read_text(encoding='utf-8')
        variants=[
          ('memory-unsafe','if !rt_unsafe(c,id){return NONE;}\n if operation==12',
           'if operation==12',decl.case('module a;fn f()void{compiler_fence();}',13)),
          ('memory-readonly','if writing&&(t.flags&1)!=0{return rt_fail(c,IMMUTABLE,id,75);}',
           'if false&&writing&&(t.flags&1)!=0{return rt_fail(c,IMMUTABLE,id,75);}',
           decl.case('module a;fn f(p:*const u32)void{unsafe{atomic_store(p,1);}}',12)),
        ]
        for name,old,new,case in variants:
            self.assertEqual(source.count(old),1);root=self.work/('bad-'+name);(root/'bootstrap').mkdir(parents=True)
            for p in self.files:
                if p!='semantic_types.dg':shutil.copyfile(ROOT/'lang/bootstrap'/p,root/'bootstrap'/p)
            (root/'bootstrap/semantic_types.dg').write_text(source.replace(old,new,1),encoding='utf-8')
            for mode in ('debug','release'):
                self.run_cases(self.executables[mode],[case],name+'-good-'+mode)
                exe=self.build(root,mode,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'status'):self.run_cases(exe,[case],name+'-'+mode)
                self.records.append(dict(test='actual-bad-Dong',variant=name,mode=mode,rejected_by='status',passed=True))

    def test_unsupported_and_workspace_limits_are_explicit(self):
        cases=[decl.case('module a;fn f()void{}',2,pool=i,cap=0) for i in range(24,29)]
        unsupported=['enum E{A,B}fn f(e:E)u64{match e{E.A=>{return 1;},E.B=>{return 2;}}}',
                     'fn die()noreturn{loop{}}fn f()u64{defer die();}',
                     'error Oops=1;fn f()void{}']
        for body in unsupported:compile_source('module a;'+body);cases.append(decl.case('module a;'+body,8))
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'limits-'+mode)
        self.records.append(dict(test='explicit-unsupported-and-capacity',cases=len(cases),invalid_preflights_per_case=20,modes=2,passed=True))
    def test_z_actual_bad_type_and_branch_intersection_are_rejected(self):
        source=(ROOT/'lang/bootstrap/semantic_types.dg').read_text(encoding='utf-8')
        variants=[('coercion','return rt_fail(c,TYPE,id,target as u64);','(*info).typ=target;return target;',decl.case('module a;fn f(x:u64)bool{return x;}',3)),
          ('intersection','(*w).snapshots[slot*count+i]&=value;','(*w).snapshots[slot*count+i]|=value;',decl.case('module a;fn f(b:bool)u64{var x:u64;if b{x=1;}else{}return x;}',11)),
          ('slice-bounds','if have_length&&((have_lo&&lo>length)||(have_hi&&hi>length))','if false&&have_length&&((have_lo&&lo>length)||(have_hi&&hi>length))',decl.case('module a;fn f()[]const u8{return "abc"[0..4];}',3)),
          ('slice-readonly','var readonly=t.flags&1;','var readonly:u64=0;',decl.case('module a;fn f(s:[]const u8)[]u8{return s[..];}',3))]
        for name,old,new,c in variants:
            self.assertEqual(source.count(old),1);root=self.work/('bad-'+name);(root/'bootstrap').mkdir(parents=True)
            for p in self.files:
                if p!='semantic_types.dg':shutil.copyfile(ROOT/'lang/bootstrap'/p,root/'bootstrap'/p)
            (root/'bootstrap/semantic_types.dg').write_text(source.replace(old,new,1),encoding='utf-8')
            for mode in ('debug','release'):
                exe=self.build(root,mode,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'status'):self.run_cases(exe,[c],name+'-'+mode)
                self.records.append(dict(test='actual-bad-Dong',variant=name,mode=mode,rejected_by='status',passed=True))

if __name__=='__main__':unittest.main()
