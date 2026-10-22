"""Read-only source-gap survey; compile-only success is never acceptance."""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]/'code';sys.path.insert(0,str(ROOT))
from lang.dongc import compile_file
from lang.tests import test_l3a_globals as bridge
driver=Path(sys.argv[1]).resolve();stage=driver.parent
OUT=Path(__file__).resolve().parents[1]/'build/L3-host-gap-audit'/stage.parent.parent.name
OUT.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
bridge.CAND=ROOT/'lang/bootstrap'
inputs={}
for module,origin in bridge.closure():
 rel=Path(*module.split('.')).with_suffix('.dg')
 prefix='' if origin.parent==bridge.CAND else next(p for p,root in bridge.SEARCH if origin==root/rel)
 if prefix:rel=Path(prefix)/rel
 actual=stage/rel
 assert actual.is_file(),(module,actual)
 assert sha(origin)==sha(actual),(module,origin)
 inputs[str(origin)]=sha(origin)
cases={
 'for-range':'pub fn f()u64{var n:u64=0;for i in 1..4{n+=i;}return n;}',
 'for-array':'pub fn f()u64{let a:[3]u64=[1,2,3];var n:u64=0;for x in a{n+=x;}return n;}',
 'for-slice':'pub fn f()u64{let a:[3]u64=[1,2,3];var n:u64=0;for x in a[0..3]{n+=x;}return n;}',
 'bool-match':'pub fn f(x:bool)u64{match x{true=>{return 7;},false=>{return 8;},}}',
 'function-pointer':'fn g(x:u64)u64{return x+1;}pub fn f()u64{let p:fn(u64)u64=g;unsafe{return p(7);}}',
 'volatile':'pub fn f()u64{var x:u64=7;unsafe{volatile_store(&x,9);return volatile_load(&x);}}',
 'unaligned':'pub fn f()u64{var x:u64=7;unsafe{write_unaligned(&x,9);return read_unaligned(&x);}}',
 'atomic':'pub fn f()u64{var x:u64=7;unsafe{atomic_store(&x,9);let a=atomic_load(&x);let b=atomic_compare_exchange(&x,9,11);return a+b+atomic_fetch_add(&x,1);}}',
 'fence':'pub fn f()u64{unsafe{compiler_fence();}return 7;}',
 'asm':'pub fn f()u64{unsafe{asm{pause}}return 7;}',
 'optional':'pub fn f()u64{let x:?u64=null;return x orelse 7;}',
 'enum':'enum E{A,B(u64)}pub fn f()u64{let x=E.B(7);match x{E.A=>{return 0;},E.B(n)=>{return n;},}}',
 'error':'error Bad=7;pub fn f()!u64{return error.Bad;}',
 'try':'fn g()!u64{return 7;}pub fn f()!u64{return try g();}',
 'defer':'pub var x:u64=0;fn add()void{x+=1;}pub fn f()u64{defer add();return 7;}',
 'win64':'pub extern "win64" fn f()u64{return 7;}',
}
records=[]
for name,text in cases.items():
 directory=OUT/name;directory.mkdir(exist_ok=True)
 source=directory/'probe.dg';source.write_text('module probe;'+text)
 try:compile_file(source,roots=[directory,ROOT/'lang/std'])
 except Exception as e:
  records.append(dict(name=name,seed_accepted=False,error=str(e)));print(name,'seed-rejected',str(e),flush=True);continue
 for mode in (0,1):
  asm=directory/(str(mode)+'.asm');asm.write_bytes(b'unchanged')
  p=subprocess.run([str(driver),str(source),'probe.dg',str(asm),str(mode)],capture_output=True,text=True,timeout=600)
  if p.returncode:assert p.returncode in (10,11,12) and asm.read_bytes()==b'unchanged',(name,p.returncode,p.stderr)
  else:assert asm.read_bytes()!=b'unchanged'
  records.append(dict(name=name,mode=mode,seed_accepted=True,returncode=p.returncode,
   status='compile-only-needs-execution' if not p.returncode else 'precise-gap',stdout=p.stdout,stderr=p.stderr,
   source_sha256=sha(source),output_preserved=bool(p.returncode)))
  assert all(sha(p)==h for p,h in inputs.items())
  (OUT/'summary.json').write_text(json.dumps(dict(compiler_sha256=sha(driver),closure_verified=True,
   scope_complete=False,inputs=inputs,cases=records),indent=2))
  print(name,mode,p.returncode,p.stderr.strip().replace('\n',' | '),flush=True)
print(OUT/'summary.json')
