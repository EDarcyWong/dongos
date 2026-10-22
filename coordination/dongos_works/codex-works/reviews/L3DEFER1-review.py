"""Independent scope/return observer for L3DEFER1's frozen native artifacts."""
import hashlib,json,os,random,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]/'code'
sys.path.insert(0,str(ROOT))
from lang.tests.test_dongc import tool,nasm_flags
run=Path(sys.argv[1]).resolve()
out=Path(__file__).resolve().parents[1]/'build/L3DEFER1-review'/run.name
out.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
records=[]
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
for tag in ('good','bad-return'):
 stage=next((run/tag).glob('stage-*'))
 provenance=next(r['provenance'] for r in summary['records'] if r.get('tag')==tag)
 for rel,p in provenance.items():
  assert sha(stage/rel)==p['sha256'],(tag,rel)
  if tag=='good':assert sha(p['origin'])==p['sha256'],p['origin']
 drivers[tag]=stage/'driver.exe'
source='''module review;
pub var trace:u64=0;
fn step(n:u64)void{trace=trace*17+n;}
pub fn f(n:u64)u64{trace=0;defer step(13);var sum:u64=0;var i:u64=0;
 while i<n{i+=1;defer step(i);if i==2{continue;}if i==4{break;}sum+=i;}return sum;
}
pub fn pair(s:[]u8,n:u64)[]u8{trace=0;defer step(7);
 if n>3{defer step(8);return s[1..n];}return s[0..n];
}
'''
src=out/'review.dg';src.write_text(source);source_hash=sha(src)
rng=random.Random(2026102202);vectors=[rng.randrange(7) for _ in range(128)]
checks=''.join('CHECK(one(%d)==0);'%n for n in vectors)
observer='''#include <stdint.h>
#include <stdio.h>
typedef uint64_t U;typedef struct{void*p;U n;}Slice;
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do{if(!(x)){fputs("independent-defer-value\\n",stderr);return 17;}}while(0)
extern U ABI f(U) __asm__("'''+label('f')+'''");
extern Slice ABI pair(Slice,U) __asm__("'''+label('pair')+'''");
extern U trace __asm__("'''+label('trace')+'''");
static int one(U n){U sum=0,t=0;
 for(U i=1;i<=n;i++){t=t*17+i;if(i==4){break;}if(i!=2){sum+=i;}}
 CHECK(f(n)==sum);CHECK(trace==t*17+13);
 unsigned char bytes[16]={0};Slice p=pair((Slice){bytes,16},n);
 CHECK(p.p==bytes+(n>3));CHECK(p.n==n-(n>3));CHECK(trace==(n>3?143:7));
 return 0;
}
int main(void){'''+checks+'''puts("independent-128-vectors-ok");return 0;}
'''
c=out/'observer.c';c.write_text(observer)
nasm,cc=tool('nasm','NASM'),tool('gcc','CC');results=[]
for tag,driver in drivers.items():
 for mode in (0,1):
  asm=out/(tag+'-'+str(mode)+'.asm');command([driver,src,'review.dg',asm,mode])
  obj=asm.with_suffix('.obj' if os.name=='nt' else '.o')
  command([nasm,'-O0','-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj])
  exe=asm.with_suffix('.exe')
  command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),c,obj,'-o',exe])
  p=command([exe],0 if tag=='good' else 17)
  if tag!='good':assert 'independent-defer-value' in p.stderr
  results.append(dict(tag=tag,mode=mode,expected_rejection=tag!='good',returncode=p.returncode,
   driver_sha256=sha(driver),assembly_sha256=sha(asm),object_sha256=sha(obj),exe_sha256=sha(exe)))
assert sha(src)==source_hash
(out/'summary.json').write_text(json.dumps(dict(closure_verified=True,seed_fallback=False,
 positive_vectors=256,positive_observations=1280,real_dong_negatives_rejected=2,vectors=vectors,results=results),indent=2))
print(out/'summary.json')
