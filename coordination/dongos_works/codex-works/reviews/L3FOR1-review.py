"""Independent deterministic range/array/slice/match observations."""
import hashlib,json,os,random,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]/'code';sys.path.insert(0,str(ROOT))
from lang.tests.test_dongc import tool,nasm_flags
run=Path(sys.argv[1]).resolve()
out=Path(__file__).resolve().parents[1]/'build/L3FOR1-review'/run.name;out.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();records=[]
def command(args,expected=0):
 p=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=600)
 records.append(dict(command=list(map(str,args)),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
 (out/'processes.json').write_text(json.dumps(records,indent=2))
 assert p.returncode==expected,(args,p.returncode,p.stdout,p.stderr)
 return p
def label(item):return '__dong_m'+b'review'.hex()+'_n'+item.encode().hex()
summary=json.loads((run/'summary.json').read_text());assert summary['source_stable']
for origin,before in summary['inputs_before'].items():assert sha(origin)==before,origin
drivers={}
for tag in ('good','bad-increment'):
 stage=next((run/tag).glob('stage-*'))
 provenance=next(r['provenance'] for r in summary['records'] if r.get('tag')==tag)
 for rel,p in provenance.items():
  assert sha(stage/rel)==p['sha256'],(tag,rel)
  if tag=='good':assert sha(p['origin'])==p['sha256'],p['origin']
 drivers[tag]=stage/'driver.exe'
source='''module review;
pub var calls:u64=0;
fn bound(x:u64)u64{calls+=1;return x;}
fn choose(x:u64)bool{calls+=1;return x>100;}
pub fn f(a:u64,b:u64)u64{calls=0;var n:u64=0;for x in bound(a)..bound(b){if x==3{continue;}n+=x;}
 match choose(n){true=>{return n+10;},_=>{return n+20;},}
}
pub fn array(a:u64,b:u64)u64{var n:u64=0;for x in [a,b]{for y in [2 as u64,4,6]{n+=x*y;}}return n;}
pub fn values(s:[]u64)u64{var n:u64=0;for x in s{n+=x;}return n;}
'''
src=out/'review.dg';src.write_text(source);source_hash=sha(src)
rng=random.Random(2026102203);vectors=[(rng.randrange(20),rng.randrange(25)) for _ in range(64)]
checks=''.join('CHECK(one(%d,%d)==0);'%p for p in vectors)
observer='''#include <stdint.h>
#include <stdio.h>
typedef uint64_t U;typedef struct{void*p;U n;}Slice;
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do{if(!(x)){fputs("independent-for-value\\n",stderr);return 17;}}while(0)
extern U ABI f(U,U) __asm__("'''+label('f')+'''");
extern U ABI array(U,U) __asm__("'''+label('array')+'''");
extern U ABI values(Slice) __asm__("'''+label('values')+'''");
extern U calls __asm__("'''+label('calls')+'''");
static int one(U a,U b){U expected=0;for(U x=a;x<b;x++){if(x!=3){expected+=x;}}
 CHECK(f(a,b)==expected+(expected>100?10:20));CHECK(calls==3);
 CHECK(array(a,b)==12*(a+b));U items[7]={a,b,3,5,7,11,13},n=b%8,sum=0;
 for(U i=0;i<n;i++){sum+=items[i];}CHECK(values((Slice){items,n})==sum);return 0;
}
int main(void){'''+checks+'''puts("independent-64-vectors-ok");return 0;}
'''
c=out/'observer.c';c.write_text(observer);nasm,cc=tool('nasm','NASM'),tool('gcc','CC');results=[]
for tag,driver in drivers.items():
 for mode in (0,1):
  asm=out/(tag+'-'+str(mode)+'.asm');command([driver,src,'review.dg',asm,mode])
  obj=asm.with_suffix('.obj' if os.name=='nt' else '.o')
  command([nasm,'-O0','-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj])
  exe=asm.with_suffix('.exe')
  command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),c,obj,'-o',exe])
  p=command([exe],0 if tag=='good' else 17)
  if tag!='good':assert 'independent-for-value' in p.stderr
  results.append(dict(tag=tag,mode=mode,expected_rejection=tag!='good',returncode=p.returncode,
   driver_sha256=sha(driver),assembly_sha256=sha(asm),object_sha256=sha(obj),exe_sha256=sha(exe)))
assert sha(src)==source_hash
(out/'summary.json').write_text(json.dumps(dict(closure_verified=True,seed_fallback=False,
 positive_vectors=128,positive_observations=512,real_dong_negatives_rejected=2,vectors=vectors,results=results),indent=2))
print(out/'summary.json')
