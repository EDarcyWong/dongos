"""Independent for/match/defer composition using frozen mainline executables."""
import hashlib,json,os,random,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]/'code';sys.path.insert(0,str(ROOT))
from lang.tests.test_dongc import tool,nasm_flags
run=Path(sys.argv[1]).resolve();out=Path(__file__).resolve().parents[1]/'build/L3CONTROL-mainline-review'/run.name
out.mkdir(parents=True,exist_ok=True);sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();records=[]
def command(args,expected=0):
 p=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=600)
 records.append(dict(command=list(map(str,args)),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
 (out/'processes.json').write_text(json.dumps(records,indent=2));assert p.returncode==expected,(args,p.returncode,p.stdout,p.stderr)
 return p
def label(item):return '__dong_m'+b'control'.hex()+'_n'+item.encode().hex()
SOURCE='''module control;
pub var trace:u64=0;
fn push(n:u64)void{trace=trace*10+n;}
pub fn loops(n:u64)u64{trace=0;defer push(9);var sum:u64=0;
 for i in 1..n{defer push(i);if i==2{continue;}match i==4{true=>{break;},false=>{sum+=i;},}}return sum;
}
pub fn pair(s:[]u8)[]u8{trace=0;defer{for z in [1 as u64,2,3]{push(z);}}return s[1..3];}
pub fn early(s:[]u8)[]u8{trace=0;defer push(8);
 for i in [1 as u64,2,3]{defer push(i);match i==2{true=>{return s;},_=>{},}}return s[0..0];
}
'''

if len(sys.argv)>2 and sys.argv[2]=='--seed-only':
 from lang.dongc import compile_file
 p=out/'control.dg';p.write_text(SOURCE)
 result=compile_file(p,roots=[out,ROOT/'lang/std']);print('combined source seed accepted',len(result.assembly));raise SystemExit
summary=json.loads((run/'summary.json').read_text());assert summary['source_stable']
for origin,before in summary['inputs_before'].items():assert sha(origin)==before,origin
drivers={}
for tag in ('good','bad-return','bad-increment'):
 stage=next((run/tag).glob('stage-*'));provenance=next(r['provenance'] for r in summary['records'] if r.get('tag')==tag)
 for rel,p in provenance.items():
  assert sha(stage/rel)==p['sha256'],(tag,rel)
  if tag=='good':assert sha(p['origin'])==p['sha256'],p['origin']
 drivers[tag]=stage/'driver.exe'
src=out/'control.dg';src.write_text(SOURCE);source_hash=sha(src)
rng=random.Random(2026102204);vectors=[rng.randrange(9) for _ in range(128)]
checks=''.join('CHECK(one(%d)==0);'%n for n in vectors)
observer='''#include <stdint.h>
#include <stdio.h>
typedef uint64_t U;typedef struct{void*p;U n;}Slice;
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do{if(!(x)){fputs("independent-control-value\\n",stderr);return 17;}}while(0)
extern U ABI loops(U) __asm__("'''+label('loops')+'''");
extern Slice ABI pair(Slice) __asm__("'''+label('pair')+'''");
extern Slice ABI early(Slice) __asm__("'''+label('early')+'''");
extern U trace __asm__("'''+label('trace')+'''");
static int one(U n){U sum=0,t=0;for(U i=1;i<n;i++){t=t*10+i;if(i==4){break;}if(i!=2){sum+=i;}}
 CHECK(loops(n)==sum);CHECK(trace==t*10+9);unsigned char bytes[5]={1,2,3,4,5};
 Slice p=pair((Slice){bytes,5});CHECK(p.p==bytes+1&&p.n==2&&trace==123);
 p=early((Slice){bytes+1,3});CHECK(p.p==bytes+1&&p.n==3&&trace==128);
 CHECK(bytes[0]==1&&bytes[4]==5);return 0;}
int main(void){'''+checks+'''puts("independent-control-128-vectors-ok");return 0;}
'''
c=out/'observer.c';c.write_text(observer);nasm,cc=tool('nasm','NASM'),tool('gcc','CC');results=[]
for tag,driver in drivers.items():
 for mode in (0,1):
  asm=out/(tag+'-'+str(mode)+'.asm');command([driver,src,'control.dg',asm,mode]);obj=asm.with_suffix('.obj' if os.name=='nt' else '.o')
  command([nasm,'-O0','-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj]);exe=asm.with_suffix('.exe')
  command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),c,obj,'-o',exe])
  p=command([exe],0 if tag=='good' else 17)
  if tag!='good':assert 'independent-control-value' in p.stderr
  results.append(dict(tag=tag,mode=mode,expected_rejection=tag!='good',returncode=p.returncode,
   driver_sha256=sha(driver),assembly_sha256=sha(asm),object_sha256=sha(obj),exe_sha256=sha(exe)))
assert sha(src)==source_hash
(out/'summary.json').write_text(json.dumps(dict(closure_verified=True,seed_fallback=False,
 positive_vectors=256,real_dong_negatives_rejected=4,vectors=vectors,results=results),indent=2));print(out/'summary.json')
