"""Independent value/ABI observer for a completed native method verification.

Pass the test's run directory. Reuses only compiler executables whose exact
staged closure is checked; it builds new target sources and independent C.
"""
import hashlib,json,os,random,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]/'code'
sys.path.insert(0,str(ROOT))
from lang.tests.test_dongc import tool,nasm_flags

run=Path(sys.argv[1]).resolve()
out=Path(__file__).resolve().parents[1]/'build/L3METHODLOW1-review'/run.name
out.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
records=[]
def command(args,expected=0):
 p=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=600)
 records.append(dict(command=list(map(str,args)),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
 (out/'processes.json').write_text(json.dumps(records,indent=2))
 assert p.returncode==expected,(args,p.returncode,p.stdout,p.stderr)
 return p
def label(item,nominal=None):
 return '__dong_m'+b'review'.hex()+'_n'+item.encode().hex()+('_t'+nominal.encode().hex() if nominal else '')

summary=json.loads((run/'summary.json').read_text())
assert summary['source_stable']
for origin,before in summary['inputs_before'].items():assert sha(origin)==before,origin
drivers={}
for tag in ('good','bad-head'):
 stage=next((run/tag).glob('stage-*'))
 provenance=next(r['provenance'] for r in summary['records'] if r.get('tag')==tag)
 for rel,p in provenance.items():
  assert sha(stage/rel)==p['sha256'],(tag,rel)
  if tag=='good':assert sha(p['origin'])==p['sha256'],p['origin']
 drivers[tag]=stage/'driver.exe'

source='''module review;
struct A{x:u64}struct B{x:u64}
fn(self:*A)sum(n:u64)u64{unsafe{return (*self).x+n;}}
fn(self:*B)sum(n:u64)u64{unsafe{return (*self).x+3*n;}}
pub fn f(x:u64,n:u64)u64{var a=A{x:x};var b=B{x:x+1};return (&a).sum(n)+sum(&b,n);}
'''
src=out/'review.dg';src.write_text(source);source_hash=sha(src)
rng=random.Random(2026102201)
vectors=[(rng.randrange(100000),rng.randrange(1,1000)) for _ in range(64)]
checks=''.join('CHECK(f(%d,%d)==%d);CHECK(a(&x,%d)==%d);CHECK(b(&x,%d)==%d);'%(x,n,2*x+1+4*n,n,73+n,n,73+3*n) for x,n in vectors)
observer='''#include <stdint.h>
#include <stdio.h>
typedef uint64_t U;
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do{if(!(x)){fputs("independent-method-value\\n",stderr);return 17;}}while(0)
extern U ABI f(U,U) __asm__("'''+label('f')+'''");
extern U ABI a(U*,U) __asm__("'''+label('sum','A')+'''");
extern U ABI b(U*,U) __asm__("'''+label('sum','B')+'''");
int main(void){U x=73;'''+checks+'''puts("independent-192-observations-ok");return 0;}
'''
c=out/'observer.c';c.write_text(observer)
nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
results=[]
for tag,driver in drivers.items():
 for mode in (0,1):
  asm=out/(tag+'-'+str(mode)+'.asm')
  command([driver,src,'review.dg',asm,mode])
  obj=asm.with_suffix('.obj' if os.name=='nt' else '.o')
  command([nasm,'-O0','-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj])
  exe=asm.with_suffix('.exe')
  command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),c,obj,'-o',exe])
  p=command([exe],0 if tag=='good' else 17)
  if tag!='good':assert 'independent-method-value' in p.stderr
  results.append(dict(tag=tag,mode=mode,expected_rejection=tag!='good',returncode=p.returncode,
   driver_sha256=sha(driver),assembly_sha256=sha(asm),object_sha256=sha(obj),exe_sha256=sha(exe)))
assert sha(src)==source_hash
(out/'summary.json').write_text(json.dumps(dict(closure_verified=True,seed_fallback=False,
 positive_observations=384,real_dong_negatives_rejected=2,vectors=vectors,results=results),indent=2))
print(out/'summary.json')
