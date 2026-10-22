"""L3METHOD1: native method declaration / receiver-call semantics vs Python seed.

Compile the mainline bootstrap snapshot in debug/release and compare it with
the seed for the supported struct-pointer subset. Also exercise the existing
runtime regressions and the complete frontend/diagnostics entry point.
"""
from __future__ import annotations
import hashlib,json,os,re,shutil,struct,subprocess,sys,unittest,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from lang.dongc import compile_source
from lang.dongc.model import CompileError
from lang.tests import test_bootstrap_semantic_types as decl
from lang.tests import test_bootstrap_semantic_runtime as runtime
from lang.tests import test_bootstrap_frontend as frontend
from lang.tests.test_dongc import tool,nasm_flags

NONE=decl.NONE
TYPE,PRIVATE,UNSUPPORTED,UNSAFE,CAPACITY=3,10,8,13,2
FUNCTION=19

# Seed-aligned corpus: native status==0 iff seed accepts. Status codes match the
# runtime harness (TYPE/PRIVATE/UNSAFE), not Python E0xxx strings.
ALIGNED=[
 # mutable / const receivers + both call forms
 ('struct S{x:u64}fn(self:*S)get()u64{unsafe{return (*self).x;}}fn f()u64{var s=S{x:7};return get(&s);}',0),
 ('struct S{x:u64}fn(self:*S)get()u64{unsafe{return (*self).x;}}fn f()u64{var s=S{x:7};return (&s).get();}',0),
 ('struct S{x:u64}fn(self:*S)get()u64{unsafe{return (*self).x;}}fn f(p:*S)u64{return p.get();}',0),
 ('struct S{x:u64}fn(self:*const S)get()u64{unsafe{return (*self).x;}}fn f()u64{let s=S{x:7};return get(&s);}',0),
 ('struct S{x:u64}fn(self:*const S)get()u64{unsafe{return (*self).x;}}fn f()u64{let s=S{x:7};return (&s).get();}',0),
 # same-module alias receiver
 ('struct S{x:u64}type Alias=S;fn(self:*Alias)get()u64{unsafe{return (*self).x;}}fn f(p:*S)u64{return get(p);}',0),
 # free function / const / global short name wins over method candidates
 ('struct S{x:u64}fn get(p:*S)u64{return 1;}fn(self:*S)get()u64{return 2;}fn f(p:*S)u64{return get(p);}',0),
 ('struct S{x:u64}const get:u64=9;fn(self:*S)get()u64{return 2;}fn f()u64{return get;}',0),
 ('struct S{x:u64}fn get(x:bool)bool{return x;}fn(self:*S)get()u64{return 2;}fn f()bool{return get(true);}',0),
 # non-receiver arity / argument type / call return / method-body return
 ('struct S{x:u64}fn(self:*S)get(x:u64)u64{return x;}fn f(p:*S)u64{return p.get();}',TYPE),
 ('struct S{x:u64}fn(self:*S)get(x:u64)u64{return x;}fn f(p:*S)u64{return p.get(1,2);}',TYPE),
 ('struct S{x:u64}fn(self:*S)get(x:u64)u64{return x;}fn f()u64{return get();}',TYPE),
 ('struct S{x:u64}fn(self:*S)get(x:u64)u64{return x;}fn f(p:*S)u64{return get(p);}',TYPE),
 ('struct S{x:u64}fn(self:*S)get(x:u64)u64{return x;}fn f(p:*S)u64{return get(p,1,2);}',TYPE),
 ('struct S{x:u64}fn(self:*S)get(x:u64)u64{return x;}fn f(p:*S)u64{return p.get(true);}',TYPE),
 ('struct S{x:u64}fn(self:*S)get(x:u64)u64{return x;}fn f(p:*S)u64{return get(p,true);}',TYPE),
 ('struct S{x:u64}fn(self:*S)get(x:u64)u64{return x;}fn f(p:*S)bool{return p.get(1);}',TYPE),
 ('struct S{x:u64}fn(self:*S)get()u64{return true;}',TYPE),
 # pointer / slice signatures in method params and returns
 ('struct S{x:u64}fn(self:*S)get()*S{return self;}fn f(p:*S)*S{return p.get();}',0),
 ('struct S{x:u64}fn(self:*S)get(x:[]u64)[]u64{return x;}fn f(p:*S,x:[]u64)[]u64{return p.get(x);}',0),
 # same name, different receivers — both forms accept
 ('struct S{x:u64}struct T{x:u64}fn(self:*S)get(x:u64)u64{return x;}fn(self:*T)get(x:bool)bool{return x;}'
  'fn f(p:*S,q:*T)bool{return get(q,true)&&get(p,1)==1;}',0),
 ('struct S{x:u64}struct T{x:u64}fn(self:*S)get(x:u64)u64{return x;}fn(self:*T)get(x:bool)bool{return x;}'
  'fn f(p:*S,q:*T)bool{return q.get(true)&&p.get(1)==1;}',0),
 # declaration rejects
 ('struct S{x:u64}fn(self:S)get()void{}',TYPE),
 ('fn(self:*u64)get()void{}',TYPE),
 ('struct S{x:u64}fn(self:*S)x()void{}',TYPE),
 ('struct S{x:u64}fn(self:*S)get()void{}fn(self:*const S)get()void{}',TYPE),
 # call rejects: value receiver, const/mutable mismatch
 ('struct S{x:u64}fn(self:*S)get()void{}fn f()void{var s=S{x:0};s.get();}',TYPE),
 ('struct S{x:u64}fn(self:*const S)get()void{}fn f()void{var s=S{x:0};(&s).get();}',TYPE),
 ('struct S{x:u64}fn(self:*const S)get()void{}fn f()void{var s=S{x:0};get(&s);}',TYPE),
 # unsafe boundary
 ('struct S{x:u64}unsafe fn(self:*S)get()void{}fn f(p:*S)void{p.get();}',UNSAFE),
 ('struct S{x:u64}unsafe fn(self:*S)get()void{}fn f(p:*S)void{unsafe{p.get();}}',0),
]

MODULE_OK=[
 ([(0,'a.dg','module a;import b as d;fn f()u64{var s=d.S{x:7};return (&s).get()+d.get(&s);}'),
   (0,'b.dg','module b;pub struct S{pub x:u64}type Alias=S;pub fn(self:*Alias)get()u64{unsafe{return (*self).x;}}')],0),
]
MODULE_BAD=[
 ([(0,'a.dg','module a;import dep as d;fn(self:*d.S)get()void{}'),(0,'dep.dg','module dep;pub struct S{x:u64}')],PRIVATE),
 ([(0,'a.dg','module a;import dep as d;type Alias=d.S;fn(self:*Alias)get()void{}'),(0,'dep.dg','module dep;pub struct S{x:u64}')],PRIVATE),
 ([(0,'a.dg','module a;import dep as d;fn f(p:*d.S)void{p.get();}'),(0,'dep.dg','module dep;pub struct S{x:u64}fn(self:*S)get()void{}')],PRIVATE),
 ([(0,'a.dg','module a;import dep as d;fn f(p:*d.S)void{d.get(p);}'),(0,'dep.dg','module dep;pub struct S{x:u64}fn(self:*S)get()void{}')],PRIVATE),
 ([(0,'a.dg','module a;import dep as d;fn f(p:*d.S)void{p.get();}'),(0,'dep.dg','module dep;pub struct S{x:u64}pub fn(self:*const S)get()void{}')],TYPE),
 ([(0,'a.dg','module a;import dep as d;fn f(p:*d.S)void{p.get();}'),(0,'dep.dg','module dep;pub struct S{x:u64}pub unsafe fn(self:*S)get()void{}')],UNSAFE),
]

# Native-only: struct pointer required; seed still accepts enum receivers.
NATIVE_STRICT=[
 ('enum E{A,B}fn(self:*const E)read()bool{unsafe{return *self==E.A;}}fn f()bool{let e=E.A;return (&e).read();}',TYPE),
]

# Successful calls whose selected callee Info must be a real FUNCTION type with
# Type.unit/node locating the chosen declaration (not the candidate-group head).
INFO_CASES=[
 ('free-baseline','module a;fn get(x:u64)u64{return x;}fn f()u64{return get(1);}',1),
 ('receiver','module a;struct S{x:u64}fn(self:*S)get(x:u64)u64{return x;}fn f(p:*S)u64{return p.get(1);}',1),
 ('functional','module a;struct S{x:u64}fn(self:*S)get(x:u64)u64{return x;}fn f(p:*S)u64{return get(p,1);}',1),
 ('same-name-functional','module a;struct S{x:u64}struct T{x:u64}'
  'fn(self:*S)get(x:u64)u64{return x;}fn(self:*T)get(x:bool)bool{return x;}'
  'fn f(p:*S,q:*T)bool{return get(q,true)&&get(p,1)==1;}',2),
 ('same-name-receiver','module a;struct S{x:u64}struct T{x:u64}'
  'fn(self:*S)get(x:u64)u64{return x;}fn(self:*T)get(x:bool)bool{return x;}'
  'fn f(p:*S,q:*T)bool{return q.get(true)&&p.get(1)==1;}',2),
]

# Diagnostic harness: dump call-site callee Info typ + selected Type kind/unit/node.
_INFO_MARKER=' wr(&code,8);wr(out,64);wr(&good,8);'
_INFO_DIAG=r'''
 if(!code){for(uint64_t j=0;j<un;j++){for(uint64_t k=0;k<u[j].nc;k++){
  uint64_t g=u[j].ns+k;const Node*call=n+g;if(call->data[0]!=10)continue;
  uint64_t cg=u[j].ns+call->data[3];const uint64_t*ci=(uint64_t*)flow.pools[0].p+3*cg;
  const uint64_t*ri=(uint64_t*)flow.pools[0].p+3*g;
  uint64_t ct=ci[0],kind=UINT64_MAX,tunit=UINT64_MAX,tnode=UINT64_MAX;
  if(ct!=UINT64_MAX&&ct<out->types){SType st=((SType*)w.pools[0].p)[ct];kind=st.kind;tunit=st.unit;tnode=st.node;}
  fprintf(stderr,"CALL unit=%llu node=%llu ref=%llu target=%llu callee_type=%llu result_type=%llu type_kind=%llu type_unit=%llu type_node=%llu\n",
   (unsigned long long)j,(unsigned long long)k,(unsigned long long)refs[cg].kind,
   (unsigned long long)refs[cg].target,(unsigned long long)ct,(unsigned long long)ri[0],
   (unsigned long long)kind,(unsigned long long)tunit,(unsigned long long)tnode);
 }}}
'''


class L3MethodSemanticsTests(unittest.TestCase):
 wrapper=runtime.WRAPPER
 build=classmethod(runtime.BootstrapSemanticRuntimeTests.build.__func__)
 run_cases=decl.BootstrapSemanticTypesTests.run_cases
 cases=runtime.BootstrapSemanticRuntimeTests.cases

 @classmethod
 def setUpClass(cls):
  cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
  if not cls.nasm or not cls.cc:raise unittest.SkipTest('native method semantics require NASM/GCC')
  cls.work=ROOT/'build/test/bootstrap-method-semantics'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
  (cls.work/'probe.c').write_text(runtime.HARNESS,encoding='utf-8')
  cls.files=['semantic_types.dg','binding.dg','modules.dg','names.dg','expression.dg','syntax.dg','lexer.dg','unicode.dg',
             'constant_arithmetic.dg','type_layout.dg','bigint.dg','bigint_div.dg','bigint_bits.dg']
  cls.observed_paths=[ROOT/'lang/bootstrap'/p for p in
                      ('semantic_types.dg','binding.dg','semantic_types.md','method-semantics.md',
                       'lower_program.dg','nasm_program.dg')]+[Path(__file__)]
  cls.mainline={p:hashlib.sha256((ROOT/'lang/bootstrap'/p).read_bytes()).hexdigest() for p in cls.files}
  cls.observed_sha={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.observed_paths}
  cls.records=[]
  cls.snapshot=cls.work/'source';(cls.snapshot/'bootstrap').mkdir(parents=True)
  for p in cls.files:shutil.copyfile(ROOT/'lang/bootstrap'/p,cls.snapshot/'bootstrap'/p)
  cls.executables={m:cls.build(cls.snapshot,m,m) for m in ('debug','release')}
  assert runtime.HARNESS.count(_INFO_MARKER)==1
  (cls.work/'probe-info.c').write_text(runtime.HARNESS.replace(_INFO_MARKER,_INFO_DIAG+_INFO_MARKER),encoding='utf-8')
  cls.info_executables={}
  for mode in ('debug','release'):
   exe=cls.work/(mode+'-info'+('.exe' if os.name=='nt' else ''))
   subprocess.run([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',
                   *([] if os.name=='nt' else ['-no-pie']),
                   str(cls.work/'probe-info.c'),str(cls.work/(mode+'.o')),'-o',str(exe)],
                  check=True,capture_output=True)
   cls.info_executables[mode]=exe

 @classmethod
 def tearDownClass(cls):
  if not hasattr(cls,'work'):return
  after_main={p:hashlib.sha256((ROOT/'lang/bootstrap'/p).read_bytes()).hexdigest() for p in cls.files}
  after_observed={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.observed_paths}
  (cls.work/'summary.json').write_text(json.dumps(dict(
   mainline_sha256=cls.mainline,mainline_stable=cls.mainline==after_main,
   observed_sha256=cls.observed_sha,source_stable=cls.observed_sha==after_observed,
   records=cls.records,method_frontend_only=True,lower_program_unchanged=True,
   L3_selfhost_complete=False,OS_VM_built=False),indent=2)+'\n',encoding='utf-8')

 def host_ok(self,source):
  try:compile_source(source);return True
  except CompileError:return False

 def aligned_cases(self,items):
  cases=[]
  for body,status in items:
   source='module a;'+body
   host=self.host_ok(source)
   self.assertEqual(host,status==0,('host acceptance',source,status))
   cases.append(decl.case(source,status))
  return cases

 def payload(self,source):
  c,_,_=decl.case(source)
  out=bytearray(struct.pack('<Q',1))
  out.extend(struct.pack('<14Q',c['roots'],c['entry'],len(c['files']),
                         *[c[k] for k in ('units','tokens','strings','nodes','edges','states','depth')],
                         c['semantic_depth'],c['pool'],c['cap'],0))
  for root,path,data in c['files']:
   out.extend(struct.pack('<3Q',root,len(path),len(data)));out.extend(path);out.extend(data)
  return out

 def test_aligned_struct_methods_match_seed(self):
  cases=self.aligned_cases(ALIGNED)
  for files,status in MODULE_OK:
   host=self.work/'mod-ok';shutil.rmtree(host,ignore_errors=True);host.mkdir()
   for _,path,text in files:(host/path).write_text(text,encoding='utf-8')
   try:decl.compile_file(host/'a.dg',roots=[host]);accepted=True
   except CompileError:accepted=False
   self.assertTrue(accepted);self.assertEqual(status,0)
   cases.append(decl.case('',files=files))
  for files,status in MODULE_BAD:
   host=self.work/('mod-bad-'+uuid.uuid4().hex[:8]);host.mkdir()
   for _,path,text in files:(host/path).write_text(text,encoding='utf-8')
   with self.assertRaises(CompileError):decl.compile_file(host/'a.dg',roots=[host])
   cases.append(decl.case('',status,files=files))
  for mode,exe in self.executables.items():self.run_cases(exe,cases,'aligned-'+mode)
  self.records.append(dict(test='aligned-struct-methods',cases=len(cases),modes=2,passed=True))

 def test_selected_method_callee_info_is_published(self):
  """Success Graph must publish selected FUNCTION Info on call.a; same-name
  overloads must resolve to distinct Type.unit/node declarations."""
  observed=[]
  for mode,exe in self.info_executables.items():
   for name,source,call_count in INFO_CASES:
    self.assertTrue(self.host_ok(source),(name,source))
    run=subprocess.run([str(exe)],input=self.payload(source),capture_output=True,timeout=120)
    self.assertEqual(run.returncode,0,(mode,name,run.stderr))
    returned,status,nt,nf,nl,unchecked,u,t,detail,good=struct.unpack_from('<10Q',run.stdout)
    self.assertEqual(returned,status);self.assertEqual(status,0);self.assertEqual(good,1)
    self.assertGreater(nt,0);self.assertEqual(unchecked,0)
    rows=[]
    for line in run.stderr.decode(errors='replace').splitlines():
     m=re.search(
      r'callee_type=(\d+) result_type=(\d+) type_kind=(\d+) type_unit=(\d+) type_node=(\d+)',line)
     if not m:continue
     ct,rt,kind,tunit,tnode=(int(x) for x in m.groups())
     self.assertNotEqual(ct,NONE,(mode,name,'callee Info missing',line))
     self.assertEqual(kind,FUNCTION,(mode,name,line))
     self.assertNotEqual(tunit,NONE);self.assertNotEqual(tnode,NONE)
     rows.append((ct,rt,tunit,tnode))
    self.assertEqual(len(rows),call_count,(mode,name,rows,run.stderr))
    if 'same-name' in name:
     self.assertEqual(len({(r[2],r[3]) for r in rows}),2,
                      (mode,name,'same-name must select distinct declarations',rows))
     self.assertEqual(len({r[0] for r in rows}),2,
                      (mode,name,'same-name must publish distinct FUNCTION types',rows))
    observed.append(dict(mode=mode,name=name,calls=rows,published_types=nt))
  self.records.append(dict(test='selected-method-callee-info',cases=len(INFO_CASES),
                           modes=2,observed=observed,passed=True))

 def test_native_rejects_enum_receivers_seed_allows(self):
  cases=[]
  for body,status in NATIVE_STRICT:
   source='module a;'+body
   self.assertTrue(self.host_ok(source),'seed still allows enum receivers')
   self.assertNotEqual(status,0)
   cases.append(decl.case(source,status))
  for mode,exe in self.executables.items():self.run_cases(exe,cases,'native-strict-'+mode)
  self.records.append(dict(test='native-stricter-enum-receiver',cases=len(cases),modes=2,passed=True))

 def test_capacity_one_short_and_workspace_limits(self):
  body='struct S{x:u64}fn(self:*S)get()u64{unsafe{return (*self).x;}}fn f(p:*S)u64{return get(p);}'
  source='module a;'+body
  self.assertTrue(self.host_ok(source))
  # Exact default RuntimeWorkspace capacities succeed and publish.
  cases=[decl.case(source)]
  # Each RuntimeWorkspace pool (harness ids 24..28) at capacity 0 rejects.
  cases.extend(decl.case(source,CAPACITY,pool=i,cap=0) for i in range(24,29))
  # One-short vs the exact depth-derived sizes used by analyze_program:
  # All five pools shrink by 1 after semantic_depth=32 sizing.
  for pool in range(24,29):
   cases.append(decl.case(source,CAPACITY,semantic_depth=32,pool=pool,cap=NONE))
  for mode,exe in self.executables.items():self.run_cases(exe,cases,'capacity-'+mode)
  self.records.append(dict(test='capacity-exact-and-one-short',cases=len(cases),modes=2,
                           exact_success=1,zero_capacity_pools=list(range(24,29)),
                           one_short_pools=list(range(24,29)),invalid_preflights_per_case=20,passed=True))

 def test_existing_runtime_regressions(self):
  # Reuse these freshly compiled mainline objects for the existing acceptance
  # oracles; the unrelated mutation suites retain their separate entry points.
  names=('test_runtime_values_calls_and_places','test_contextual_runtime_shift_width',
         'test_flow_initialization_reachability_and_cleanup','test_intrinsic_and_aggregate_never_flow',
         'test_slices_bounds_readonly_and_place_alignment','test_memory_intrinsics_types_arity_and_permissions',
         'test_tagged_unwrap_types_and_control_flow','test_optional_result_match_payloads_and_flow',
         'test_unsupported_and_workspace_limits_are_explicit')
  for name in names:
   with self.subTest(regression=name):
    getattr(runtime.BootstrapSemanticRuntimeTests,name)(self)

 def test_full_frontend_pipeline(self):
  # This recompiles the real frontend/arena/diagnostic closure from mainline,
  # independently of the lower-level semantic objects used by this class.
  frontend.BootstrapFrontendTests.setUpClass()
  h=frontend.BootstrapFrontendTests()
  try:
   h.test_native_pipeline_and_diagnostics()
   body='struct S{x:u64}fn(self:*S)get(x:u64)u64{return x;}'
   cases=[frontend.case(body+'fn f(p:*S)u64{return p.get(1);}'),
          frontend.case(body+'fn f(p:*S)u64{return get(p,1);}'),
          frontend.case(body+'fn f(p:*S)u64{return p.get(true);}'),
          frontend.case(files=[(0,'a.dg','module a;import b;fn f(p:*b.S)void{p.get();}'),
                               (0,'b.dg','module b;pub struct S{x:u64}fn(self:*S)get()void{}')])]
   for mode,exe in h.executables.items():
    rows=h.run_cases(exe,cases,'methods-'+mode)
    for index,(row,text) in enumerate(rows):
     self.assertEqual(row[0],0 if index<2 else 3,(mode,index,row,text))
     self.assertEqual(row[30],1)
     if index<2:
      self.assertGreater(row[18],0) # Graph.types
      self.assertEqual(row[26],row[14]) # Info covers the whole node pool
      self.assertEqual(row[8],frontend.budget(cases[index]))
     else:
      self.assertEqual(row[3],4) # semantic stage
      self.assertTrue(all(n==0 for n in row[9:27]),(mode,index,row))
  finally:
   frontend.BootstrapFrontendTests.tearDownClass()
  self.records.append(dict(test='full-frontend-method-integration',
                           work=str(h.work),existing_pipeline_cases=27,method_cases=4,modes=2,passed=True))

 def test_actual_bad_method_candidates_are_rejected(self):
  source=(self.snapshot/'bootstrap/semantic_types.dg').read_text(encoding='utf-8')
  variants=[
   # Drop struct-only receiver gate → enum method wrongly accepted.
   ('enum-receiver',
    'if pointee>=(*s).type_count||(*w).types[pointee].kind!=STRUCT{fail(s,TYPE,sy.unit,recv_node,63);return false;}',
    'if pointee>=(*s).type_count{fail(s,TYPE,sy.unit,recv_node,63);return false;}',
    decl.case('module a;enum E{A,B}fn(self:*const E)read()bool{unsafe{return *self==E.A;}}fn f()bool{let e=E.A;return (&e).read();}',TYPE)),
   # Skip field-name clash → method named like a field wrongly accepted.
   ('field-clash',
    'if equal(method_name,text(s,field.unit,node.token)){fail(s,TYPE,sy.unit,sy.declaration,65);return false;}',
    'if false&&equal(method_name,text(s,field.unit,node.token)){fail(s,TYPE,sy.unit,sy.declaration,65);return false;}',
    decl.case('module a;struct S{x:u64}fn(self:*S)x()void{}',TYPE)),
   # Skip duplicate (pointee,name) → *S/*const S same name wrongly accepted.
   ('duplicate-method',
    'fail(s,TYPE,sy.unit,sy.declaration,66);return false;',
    'if false{fail(s,TYPE,sy.unit,sy.declaration,66);return false;}',
    decl.case('module a;struct S{x:u64}fn(self:*S)get()void{}fn(self:*const S)get()void{}',TYPE)),
   # Skip cross-module visibility on functional selection.
   ('private-select',
    'let sy=(*s).symbols[matched];if sy.unit!=(*c).unit&&sy.flags!=1{return rt_fail(c,PRIVATE,id,0);}\n return (*w).node_types[gid(s,sy.unit,sy.declaration)];',
    'let sy=(*s).symbols[matched];\n return (*w).node_types[gid(s,sy.unit,sy.declaration)];',
    decl.case('',PRIVATE,files=[(0,'a.dg','module a;import dep as d;fn f(p:*d.S)void{d.get(p);}'),
                                 (0,'dep.dg','module dep;pub struct S{x:u64}fn(self:*S)get()void{}')])),
  ]
  for name,old,new,case in variants:
   self.assertEqual(source.count(old),1,(name,old))
   root=self.work/('bad-'+name);(root/'bootstrap').mkdir(parents=True)
   for p in self.files:
    if p!='semantic_types.dg':shutil.copyfile(self.snapshot/'bootstrap'/p,root/'bootstrap'/p)
   (root/'bootstrap/semantic_types.dg').write_text(source.replace(old,new,1),encoding='utf-8')
   for mode in ('debug','release'):
    # Honest candidate still rejects the negative.
    self.run_cases(self.executables[mode],[case],name+'-good-'+mode)
    exe=self.build(root,mode,name+'-'+mode)
    with self.assertRaisesRegex(AssertionError,'status'):self.run_cases(exe,[case],name+'-'+mode)
    self.records.append(dict(test='actual-bad-Dong',variant=name,mode=mode,rejected_by='status',passed=True))

 def test_inputs_and_modules_remain_stable(self):
  after_main={p:hashlib.sha256((ROOT/'lang/bootstrap'/p).read_bytes()).hexdigest() for p in self.files}
  after_observed={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.observed_paths}
  self.assertEqual(self.mainline,after_main)
  self.assertEqual(self.observed_sha,after_observed)
  self.records.append(dict(test='source-immutable',passed=True))


if __name__=='__main__':unittest.main()
