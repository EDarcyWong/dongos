"""Native runtime type/flow checking over real lexer/module/binding graphs."""
from __future__ import annotations
import hashlib,json,os,random,shutil,struct,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_source
from lang.dongc.model import CompileError
from lang.tests import test_bootstrap_semantic_types as decl
from lang.tests.test_dongc import tool,nasm_flags
ROOT=decl.ROOT
NONE=decl.NONE
WRAPPER=decl.WRAPPER.replace('w:*const semantic.Workspace,depth:usize,r:*semantic.Result)',
 'w:*const semantic.Workspace,rw:*const semantic.RuntimeWorkspace,depth:usize,r:*semantic.Result)')
WRAPPER=WRAPPER.replace('return semantic.analyze(', 'return semantic.analyze_program(').replace('slice_from_raw_parts(refs,rn),w,depth,r);','slice_from_raw_parts(refs,rn),w,rw,depth,r);')
HARNESS=decl.HARNESS.replace('typedef struct{Pool pools[24];} Workspace;',
 'typedef struct{Pool pools[24];} Workspace;\ntypedef struct{Pool pools[5];} RuntimeWorkspace;')
HARNESS=HARNESS.replace('const Ref*,uint64_t,const Workspace*,uint64_t,SResult*);','const Ref*,uint64_t,const Workspace*,const RuntimeWorkspace*,uint64_t,SResult*);')
HARNESS=HARNESS.replace(' Workspace w;for(int i=0;i<24;i++)',r'''
 const uint64_t fwidth[]={24,1,1,1,1},fcaps[]={nn,nn,((nn+7)/8)*512,((nn+7)/8)*256,256};RuntimeWorkspace flow;
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
 flow.pools[2].n=((nn+7)/8)*h[10]*2;flow.pools[3].n=((nn+7)/8)*h[10];flow.pools[4].n=h[10];
 if(h[11]==29){flow.pools[2].n=fcaps[2];flow.pools[3].n=fcaps[3];}
 if(h[11]>=24&&h[11]<29){unsigned pool=h[11]-24;flow.pools[pool].n=h[12]==UINT64_MAX?flow.pools[pool].n-1:h[12];}
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


def never_flow_cases():
    # Typed wrappers keep the intrinsic/aggregate contracts intact: a direct
    # die() operand is not an integer operand for a wrapping intrinsic.
    prefix='fn die()noreturn{loop{}}fn g(x:u64)u64{return x;}'
    items=[]
    for name in ('wrapping_add','wrapping_sub','wrapping_mul'):
        for args in ('g(die()),1','1,g(die())'):
            items.append((prefix+f'fn f()u64{{let b=true&&({name}({args})==0);}}',0))
    # Exercise all direct noreturn operand positions across contextual sites.
    # Expected integer types must not turn these into legal intrinsic operands.
    for args in ('die(),1','1,die()','die(),die()'):
        items.extend([
          (prefix+f'fn f()u64{{return wrapping_add({args});}}',3),
          (prefix+f'fn f()u64{{let x:u8=wrapping_sub({args});}}',3),
          (prefix+f'fn use(x:u64)void{{}}fn f()u64{{use(wrapping_mul({args}));}}',3),
        ])
    items.extend([
      (prefix+'fn f()u64{return wrapping_add(g(die()),1);}',0),
      (prefix+'fn h(x:u8)u8{return x;}fn f()u64{let x:u8=wrapping_sub(1,h(die()));}',0),
      (prefix+'fn use(x:u64)void{}fn f()u64{use(wrapping_mul(g(die()),g(die())));}',0),
      (prefix+'fn f()u8{return wrapping_add(g(die()),1);}',3),
      ('fn f()u8{return wrapping_add(~0,1);}',0),
      ('fn f()u8{return wrapping_mul(255,2);}',0),
      ('fn f()u8{return wrapping_add(wrapping_add(255,1),255);}',0),
      ('fn f()u8{return wrapping_add(1<<7,128);}',0),
      ('fn f()u8{return wrapping_add(~0,2)+1;}',0),
      ('fn f()u8{return wrapping_add(1<<8,1);}',5),
      ('fn f()u8{return wrapping_sub(-1,1);}',3),
      ('fn f()u8{return wrapping_add(256,1);}',3),
      (prefix+'fn f()u64{return wrapping_add(wrapping_sub(die(),1),1);}',3),
      (prefix+'fn f()u64{unsafe{let b=false||(slice_from_raw_parts(null as *u8,die()).len==0);}}',0),
      (prefix+'fn p(x:u64)*u8{return null;}fn f()u64{unsafe{let b=true&&(slice_from_raw_parts(p(die()),1).len==0);}}',0),
      (prefix+'struct S{x:u64,y:u64}fn f()u64{let b=true&&(S{x:die(),y:1}.y==0);}',0),
      (prefix+'struct S{x:u64,y:u64}fn f()u64{let b=false||(S{y:1,x:die()}.y==0);}',0),
      (prefix+'fn f()u64{let b=true&&([1 as u64,die()][0]==0);}',0),
      (prefix+'fn f()u64{let b=false||([g(die()),1][1]==0);}',0),
      (prefix+'fn f()u64{let b=true&&([g(die());2][0]==0);}',0),
      (prefix+'struct S{x:[2]u64}fn f()u64{let b=false||(S{x:[wrapping_mul(1,g(die()));2]}.x[0]==0);}',0),
      # A skipped or unknown RHS does not terminate the enclosing expression.
      (prefix+'fn f()u64{let b=false&&(wrapping_add(g(die()),1)==0);}',14),
      (prefix+'fn f(b:bool)u64{let x=b||(wrapping_sub(1,g(die()))==0);}',14),
      (prefix+'fn f()u64{unsafe{let b=true||(slice_from_raw_parts(null as *u8,die()).len==0);}}',14),
      (prefix+'struct S{x:u64}fn f()u64{let b=false&&(S{x:die()}.x==0);}',14),
      (prefix+'struct S{x:u64}fn f(b:bool)u64{let x=b&&(S{x:die()}.x==0);}',14),
      (prefix+'fn f()u64{let b=true||([1 as u64,die()][0]==0);}',14),
      (prefix+'fn f(b:bool)u64{let x=b&&([g(die());2][0]==0);}',14),
      (prefix+'fn f()u64{let b=false&&([g(die());2][0]==0);return 7;}',0),
      # Termination is a flow fact, not permission to erase a typed result.
      (prefix+'fn f()void{let x:bool=wrapping_add(g(die()),1);}',3),
      (prefix+'fn f()void{unsafe{let x:bool=slice_from_raw_parts(null as *u8,die());}}',3),
      (prefix+'struct S{x:u64}fn f()void{let x:bool=S{x:die()};}',3),
      (prefix+'fn f()void{let x:bool=[1 as u64,die()];}',3),
      (prefix+'fn f()void{let x:bool=[g(die());2];}',3),
      (prefix+'fn f()void{let x:bool=g(die());}',3),
      # All children and ordinary dead code still undergo type/read checks.
      (prefix+'fn f()u64{let b=true&&(wrapping_add(die(),1)==0);}',3),
      (prefix+'fn f()u64{let b=false&&(wrapping_add(g(die()),true)==0);}',3),
      (prefix+'fn f()u64{unsafe{let b=true&&(slice_from_raw_parts(null as *u8,true).len==0);}}',3),
      (prefix+'struct S{x:u64,y:u64}fn f()u64{let b=true&&(S{x:die(),y:true}.x==0);}',3),
      (prefix+'fn f()u64{let b=true&&([g(die()),true][0]==0);}',3),
      (prefix+'fn f()u64{let b=true&&([g(die());0][0]==0);}',5),
      (prefix+'fn f()u64{var x:u64;let b=true&&(wrapping_mul(g(die()),x)==0);}',11),
      (prefix+'struct S{x:u64,y:u64}fn f()u64{var x:u64;let b=true&&(S{x:die(),y:x}.x==0);}',11),
      (prefix+'fn f()u64{var x:u64;let b=true&&([g(die()),x][0]==0);}',11),
      (prefix+'fn f()u64{var x:u64;let b=false&&([g(die());2][0]==0);return x;}',11),
      (prefix+'fn f()u64{let b=true&&([g(die());2][0]==0);let x:bool=1;}',3),
      # Skipped cleanup expressions remain nonterminating; captures are still
      # checked at defer registration, even when a previous child terminates.
      (prefix+'struct S{x:u64}fn f()u64{defer {let b=false&&(S{x:die()}.x==0);}return 1;}',0),
      (prefix+'fn f()u64{var x:u64;defer {let b=true&&(wrapping_add(g(die()),x)==0);}return 1;}',11),
    ])
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
    @classmethod
    def build(cls,root,mode,label):
        # Production is assembled in both containers. Semantic mutations only
        # need the host container: their rejection is actual native execution,
        # not portability of an intentionally incorrect implementation.
        entry=cls.work/(label+'-entry');entry.mkdir()
        wrapper=entry/'probe.dg';wrapper.write_text(cls.wrapper,encoding='utf-8')
        asm=cls.work/(label+'.asm')
        asm.write_text(decl.compile_file(wrapper,roots=[entry,root],mode=mode).assembly,encoding='utf-8')
        native='win64' if os.name=='nt' else 'elf64'
        formats=('elf64','win64') if label in ('debug','release') else (native,)
        obj=cls.work/(label+'.o');exe=cls.work/(label+('.exe' if os.name=='nt' else ''))
        commands=[]
        for fmt in formats:
            target=obj if fmt==native else cls.work/(label+'.'+fmt+'.o')
            commands.append([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',target,asm])
        commands.append([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),cls.work/'probe.c',obj,'-o',exe])
        for i,command in enumerate(commands):
            run=subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=120)
            (cls.work/(label+f'-{i}.log')).write_text(run.stdout+run.stderr,encoding='utf-8')
            if run.returncode:raise AssertionError((label,run.returncode,run.stdout,run.stderr))
        return exe
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
        cls.snapshot=cls.work/'source';(cls.snapshot/'bootstrap').mkdir(parents=True)
        for p in cls.files:shutil.copyfile(ROOT/'lang/bootstrap'/p,cls.snapshot/'bootstrap'/p)
        cls.executables={m:cls.build(cls.snapshot,m,m) for m in ('debug','release')}
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
    def test_contextual_runtime_shift_width(self):
        items=[]
        for typ in ('u8','u16','u32','u64','i8','i16','i32','i64'):
            for op in ('<<','>>'):
                items.extend([
                  (f'fn f(mask:{typ},i:u64){typ}{{return mask&(1{op}i);}}',0),
                  (f'fn f(mask:{typ},i:u64){typ}{{return (1{op}i)&mask;}}',0),
                  (f'fn f(i:u64){typ}{{return 1{op}i;}}',0),
                ])
        items.extend([
          ('fn f(mask:u64,i:u64)bool{return (mask&(1<<i))!=0;}',0),
          ('fn f(i:u64)u64{return (1<<i)+(2<<i);}',0),
          ('fn f(i:u64)i64{let x=1<<i;return x;}',0),
          ('fn f(i:u64)u8{return (256<<i);}',3),
          ('fn f(i:u64)u8{return (1<<i)<<8;}',3),
          ('fn f(i:u8)u64{return 1<<i;}',3),
          ('fn f(i:u64)bool{return 1<<i;}',3),
        ])
        cases=self.cases(items)
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'contextual-shift-'+mode)
        self.records.append(dict(test='contextual-runtime-shift',cases=len(cases),modes=2,passed=True))

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
    def test_intrinsic_and_aggregate_never_flow(self):
        cases=self.cases(never_flow_cases())
        # A cleanup that never returns closes the function's normal path.
        source='module a;fn die()noreturn{loop{}}struct S{x:u64}fn f()u64{defer {let b=true&&(S{x:die()}.x==0);}}'
        compile_source(source);cases.append(decl.case(source,0))
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'never-flow-'+mode)
        self.records.append(dict(test='intrinsic-aggregate-never-flow',cases=len(cases),modes=2,host_acceptance_checked=True,passed=True))

    def test_never_flow_actual_rollbacks_are_rejected(self):
        source=(self.snapshot/'bootstrap/semantic_types.dg').read_text(encoding='utf-8')
        prefix='module a;fn die()noreturn{loop{}}fn g(x:u64)u64{return x;}'
        pair='(*rt_info(c,id)).flags=((*rt_info(c,first)).flags|(*rt_info(c,second)).flags)&NEVER;'
        variants=[
          ('never-wrapping',pair+'\n   let ga=', 'let ga=',
           [prefix+'fn f()u64{let b=true&&(wrapping_add(g(die()),1)==0);}']),
          ('never-raw-slice',pair+'\n   let t=', 'let t=',
           [prefix+'fn f()u64{unsafe{let b=true&&(slice_from_raw_parts(null as *u8,die()).len==0);}}']),
          ('never-array','(*rt_info(c,id)).flags=stopped;return rt_type(c,ARRAY,0,element,count,id);',
           'return rt_type(c,ARRAY,0,element,count,id);',
           [prefix+'fn f()u64{let b=true&&([1 as u64,die()][0]==0);}',
            prefix+'fn f()u64{let b=true&&([g(die());2][0]==0);}']),
          ('never-struct','(*rt_info(c,id)).flags=stopped;return typ;', 'return typ;',
           [prefix+'struct S{x:u64}fn f()u64{let b=true&&(S{x:die()}.x==0);}']),
          ('never-wrapping-context',
           'if a==NORETURN||b==NORETURN{return rt_fail(c,TYPE,id,17);}',
           'if a==NORETURN{a=rt_accept(c,first,target);}if b==NORETURN{b=rt_accept(c,second,target);}',
           [prefix+'fn f()u64{return wrapping_add(die(),1);}',
            prefix+'fn f()u64{return wrapping_add(1,die());}',
            prefix+'fn f()u64{return wrapping_add(die(),die());}']),
          ('never-typed-coercion','if source==NORETURN{(*info).typ=target;return target;}',
           'if source==NORETURN||((*info).flags&NEVER)!=0{(*info).typ=target;return target;}',
           [prefix+'struct S{x:u64}fn f()void{let x:bool=S{x:die()};}']),
        ]
        for name,old,new,sources in variants:
            self.assertEqual(source.count(old),1);root=self.work/('bad-'+name);(root/'bootstrap').mkdir(parents=True)
            cases=[]
            for body in sources:
                status=3 if name in ('never-typed-coercion','never-wrapping-context') else 0
                try:compile_source(body);host=True
                except CompileError:host=False
                self.assertEqual(host,status==0,body);cases.append(decl.case(body,status))
            for p in self.files:
                if p!='semantic_types.dg':shutil.copyfile(self.snapshot/'bootstrap'/p,root/'bootstrap'/p)
            (root/'bootstrap/semantic_types.dg').write_text(source.replace(old,new,1),encoding='utf-8')
            for mode in ('debug','release'):
                self.run_cases(self.executables[mode],cases,name+'-good-'+mode)
                exe=self.build(root,mode,name+'-'+mode)
                for i,case in enumerate(cases):
                    with self.assertRaisesRegex(AssertionError,'status'):self.run_cases(exe,[case],name+'-'+mode+'-'+str(i))
                self.records.append(dict(test='actual-bad-Dong',variant=name,mode=mode,cases=len(cases),rejected_by='status',passed=True))

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
        source=(self.snapshot/'bootstrap/semantic_types.dg').read_text(encoding='utf-8')
        variants=[
          ('try-context','if (*c).in_defer||rt_kind(c,(*c).returns)!=RESULT',
           'if (*c).in_defer',decl.case('module a;fn f(x:!u8)u8{return try x;}',15)),
          ('orelse-live','(*c).live=live&&tag!=1;',
           '(*c).live=live;',decl.case('module a;const O:?u64=1;fn f()noreturn{loop{let n=O orelse break;}}')),
        ]
        for name,old,new,case in variants:
            self.assertEqual(source.count(old),1);root=self.work/('bad-'+name);(root/'bootstrap').mkdir(parents=True)
            for p in self.files:
                if p!='semantic_types.dg':shutil.copyfile(self.snapshot/'bootstrap'/p,root/'bootstrap'/p)
            (root/'bootstrap/semantic_types.dg').write_text(source.replace(old,new,1),encoding='utf-8')
            for mode in ('debug','release'):
                self.run_cases(self.executables[mode],[case],name+'-good-'+mode)
                exe=self.build(root,mode,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'status'):self.run_cases(exe,[case],name+'-'+mode)
                self.records.append(dict(test='actual-bad-Dong',variant=name,mode=mode,rejected_by='status',passed=True))

    def test_memory_intrinsics_actual_wrong_permissions_are_rejected(self):
        source=(self.snapshot/'bootstrap/semantic_types.dg').read_text(encoding='utf-8')
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
                if p!='semantic_types.dg':shutil.copyfile(self.snapshot/'bootstrap'/p,root/'bootstrap'/p)
            (root/'bootstrap/semantic_types.dg').write_text(source.replace(old,new,1),encoding='utf-8')
            for mode in ('debug','release'):
                self.run_cases(self.executables[mode],[case],name+'-good-'+mode)
                exe=self.build(root,mode,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'status'):self.run_cases(exe,[case],name+'-'+mode)
                self.records.append(dict(test='actual-bad-Dong',variant=name,mode=mode,rejected_by='status',passed=True))

    def test_optional_result_match_payloads_and_flow(self):
        samples=[
          ('fn f(x:?u8)u8{match x{null=>{return 0;},some(v)=>{return v;}}}',0),
          ('fn f(x:?u8)u8{match x{some(v)=>{return v;},_=>{return 0;}}}',0),
          ('fn f(x:!u8)u64{match x{ok(v)=>{return v as u64;},err(e)=>{return e;}}}',0),
          ('fn f(x:!void)u64{match x{ok=>{return 0;},err(e)=>{return e;}}}',0),
          ('fn f(x:!u8)u8{match x{ok(v)=>{return v;},_=>{return 0;}}}',0),
          ('fn f(x:?u8)u8{var y:u8;match x{null=>{y=0;},some(v)=>{y=v;}}return y;}',0),
          ('fn f(x:!u8)u8{var y:u8;match x{ok(v)=>{y=v;},err(e)=>{y=0;}}return y;}',0),
          ('fn f(x:?u8,y:!u8)u8{match x{null=>{return 0;},some(v)=>{match y{ok(z)=>{return z;},err(e)=>{return v;}}}}}',0),
          ('fn f(x:?u8)void{match x{null=>{},some(v)=>{let n:u8=v;}}}',0),
          ('fn f(x:!void)void{match x{ok=>{},err(e)=>{let n:u64=e;}}}',0),
          ('fn f(x:?u8)u8{match x{null=>{return 0;}}}',15),
          ('fn f(x:!u8)u8{match x{ok(v)=>{return v;}}}',15),
          ('fn f(x:?u8)void{match x{null=>{},null=>{},some(v)=>{}}}',15),
          ('fn f(x:!u8)void{match x{err(e)=>{},err(f)=>{},ok(v)=>{}}}',15),
          ('fn f(x:?u8)void{match x{_=>{},null=>{}}}',15),
          ('fn f(x:!u8)void{match x{ok(v)=>{},err(e)=>{},_=>{}}}',15),
          ('fn f(x:?u8)void{match x{true=>{},_=>{}}}',3),
          ('fn f(x:!u8)void{match x{null=>{},_=>{}}}',3),
          ('fn f(x:!u8)void{match x{ok=>{},err(e)=>{}}}',3),
          ('fn f(x:!void)void{match x{ok(v)=>{},err(e)=>{}}}',3),
          ('fn f(x:?u8)void{match x{null=>{},some(v)=>{let y:bool=v;}}}',3),
          ('fn f(x:!u8)void{match x{ok(v)=>{},err(e)=>{let y:bool=e;}}}',3),
          ('fn f(x:?u8)u8{var y:u8;match x{null=>{},some(v)=>{y=v;}}return y;}',11),
          ('fn f(x:!u8)u8{var y:u8;match x{ok(v)=>{y=v;},err(e)=>{}}return y;}',11),
          ('const O:?u64=1;fn f()u64{var y:u64;match O{null=>{},some(v)=>{y=v;}}return y;}',0),
          ('const O:?u64=null;fn f()u64{var y:u64;match O{null=>{y=7;},some(v)=>{}}return y;}',0),
        ]
        cases=[]
        for body,status in samples:
            source='module a;'+body
            try:compile_source(source);accepted=True
            except CompileError:accepted=False
            self.assertEqual(accepted,status==0,body)
            cases.append(decl.case(source,status))
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'tagged-match-'+mode)
        self.records.append(dict(test='optional-result-match',cases=len(cases),modes=2,host_acceptance_checked=True,passed=True))

    def test_packed_flow_exact_capacity_and_byte_boundaries(self):
        # Every byte pattern, including the high bit, with varying global-node
        # offsets, imported modules, nested branch/loop slots and defer restore.
        cases=[]
        for mask in range(256):
            pad=''.join(f'let pad{i}:u64={i};' for i in range(mask%16))
            bindings=''.join(f'var x{i}:u64;' for i in range(8))
            yes=''.join(f'x{i}=1;' for i in range(8) if mask&(1<<i))
            other=((mask<<1)|(mask>>7))&255
            no=''.join(f'x{i}=2;' for i in range(8) if other&(1<<i))
            target=mask%8
            expected=0 if mask&other&(1<<target) else 11
            # Loop break snapshots and branch merge must produce the same
            # intersection; an unrelated initialized defer capture survives.
            flow=f'loop{{if b{{{yes}break;}}else{{{no}break;}}}}'
            body=f'fn f(b:bool)u64{{let anchor:u64=1;defer {{let z=anchor;}}{pad}{bindings}{flow}return x{target};}}'
            source='module a;import b;'+body
            files=[(0,'a.dg',source),(0,'b.dg','module b;pub fn seed()u64{return 1;}')]
            # Independent host acceptance, over the identical cross-source input.
            host=self.work/f'packed-host-{mask}';host.mkdir()
            for _,path,text in files:(host/path).write_text(text,encoding='utf-8')
            try:decl.compile_file(host/'a.dg',roots=[host]);accepted=True
            except CompileError:accepted=False
            self.assertEqual(accepted,expected==0,mask)
            cases.append(decl.case('',expected,files=files,semantic_depth=32))
            if mask<16:
                for pool in (26,27):cases.append(decl.case('',2,files=files,semantic_depth=32,pool=pool,cap=NONE))
        # With depth16, full allocated descriptors exceed even the old
        # byte-per-node contract. Larger callers remain accepted unchanged.
        cases.append(decl.case('module a;fn f(b:bool)u64{var x:u64;if b{x=1;}else{x=2;}return x;}',semantic_depth=16,pool=29))
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'packed-flow-'+mode)
        self.records.append(dict(test='packed-flow-all-byte-patterns-exact-and-one-short',cases=len(cases),modes=2,host_acceptance_checked=True,passed=True))

    def test_tagged_cleanup_support_and_workspace_limits_are_explicit(self):
        cases=[decl.case('module a;fn f()void{}',2,pool=i,cap=0) for i in range(24,29)]
        supported=['enum E{A,B}fn f(e:E)u64{match e{E.A=>{return 1;},E.B=>{return 2;}}}',
                   'fn die()noreturn{loop{}}fn f()u64{defer die();}',
                   'error Oops=1;fn f()void{}']
        for body in supported:compile_source('module a;'+body);cases.append(decl.case('module a;'+body,0))
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'limits-'+mode)
        self.records.append(dict(test='tagged-cleanup-support-and-capacity',cases=len(cases),invalid_preflights_per_case=20,modes=2,passed=True))
    def test_z_actual_bad_type_and_branch_intersection_are_rejected(self):
        source=(self.snapshot/'bootstrap/semantic_types.dg').read_text(encoding='utf-8')
        variants=[('coercion','return rt_fail(c,TYPE,id,target as u64);','(*info).typ=target;return target;',decl.case('module a;fn f(x:u64)bool{return x;}',3)),
          ('intersection','bits[slot*stride+byte]&=value;','bits[slot*stride+byte]|=value;',decl.case('module a;fn f(b:bool)u64{var x:u64;if b{x=1;}else{}return x;}',11)),
          ('packed-high-bit','while bit<8&&byte*8+bit<count','while bit<7&&byte*8+bit<count',
           decl.case('module a;fn f(b:bool)u64{'+''.join(f'var x{i}:u64;' for i in range(16))+
             'if b{'+''.join(f'x{i}=1;' for i in range(16))+'}else{'+''.join(f'x{i}=2;' for i in range(16))+
             '}return '+'+'.join(f'x{i}' for i in range(16))+';}')),
          ('slice-bounds','if have_length&&((have_lo&&lo>length)||(have_hi&&hi>length))','if false&&have_length&&((have_lo&&lo>length)||(have_hi&&hi>length))',decl.case('module a;fn f()[]const u8{return "abc"[0..4];}',3)),
          ('slice-readonly','var readonly=t.flags&1;','var readonly:u64=0;',decl.case('module a;fn f(s:[]const u8)[]u8{return s[..];}',3)),
          ('match-error-payload','mask=2;payload=3;','mask=2;payload=8;',decl.case('module a;fn f(x:!u8)void{match x{ok(v)=>{},err(e)=>{let y:bool=e;}}}',3)),
          ('match-exhaustive','if seen!=3{rt_fail(c,FLOW,id,2);return false;}','if false{rt_fail(c,FLOW,id,2);return false;}',decl.case('module a;fn f(x:?u8)void{match x{null=>{}}}',15))]
        for name,old,new,c in variants:
            self.assertEqual(source.count(old),1);root=self.work/('bad-'+name);(root/'bootstrap').mkdir(parents=True)
            for p in self.files:
                if p!='semantic_types.dg':shutil.copyfile(self.snapshot/'bootstrap'/p,root/'bootstrap'/p)
            (root/'bootstrap/semantic_types.dg').write_text(source.replace(old,new,1),encoding='utf-8')
            for mode in ('debug','release'):
                exe=self.build(root,mode,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'status'):self.run_cases(exe,[c],name+'-'+mode)
                self.records.append(dict(test='actual-bad-Dong',variant=name,mode=mode,rejected_by='status',passed=True))

if __name__=='__main__':unittest.main()
