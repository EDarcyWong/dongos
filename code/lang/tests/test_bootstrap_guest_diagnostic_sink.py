"""Real native frontend -> existing renderer -> bounded transport."""
import hashlib,json,os,subprocess,sys,unittest,uuid,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
WORKS=ROOT
sys.path.insert(0,str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
SOURCE=ROOT/'lang/bootstrap/guest_diagnostic_sink.dg'
WRAPPER='''module probe.sink_export;
import bootstrap.guest_diagnostic_sink as d;
import bootstrap.frontend as f;
import bootstrap.modules as m;
export("sink_emit") unsafe fn emit(s:*const m.Source,n:usize,fr:*const f.Result,out:*u8,cap:usize,context:u64,write:d.Write,r:*d.Result)u64{unsafe{
 return d.emit(slice_from_raw_parts(s,n),fr,slice_from_raw_parts(out,cap),context,write,r);
}}
'''
HARNESS=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct{const void*p;U n;} Slice;
typedef struct{U root;Slice path,bytes;} Source;
typedef struct{U status,stage,code,length,sent;} Result;
typedef U (ABI *Write)(U,const void*,U,U*);
extern U ABI sink_emit(const Source*,U,const void*,void*,U,U,Write,Result*);
extern U ABI dong_frontend_check(const U*,const Source*,U,const U*,void*,U,void*);
extern U ABI dong_frontend_diagnostic(const Source*,U,const void*,void*,U,U*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,U n){(void)k;(void)l;(void)f;(void)n;exit(87);}
static void check(int b,const char*s){if(!b){fprintf(stderr,"sink assertion: %s\n",s);exit(90);}}
static unsigned char received[4096],baseline[4096],scratch[4096];
static U calls,sent,chunk,fail_at,over_at,zero_at;
static U ABI wr(U context,const void*p,U n,U*moved){
 check(context==77&&n>0&&n<=sizeof received-sent,"callback ABI");calls++;
 if(calls==fail_at)return 0xbeef;
 if(calls==over_at){*moved=n+1;return 0;}
 if(calls==zero_at){*moved=0;return 0;}
 U m=n<chunk?n:chunk;memcpy(received+sent,p,m);sent+=m;*moved=m;return 0;
}
static void one(const char*text,U expect_front,U action){
 static _Alignas(16) unsigned char arena[16*1024*1024];U fr[45]={0},saved[45];
 Source source={0,{"a.dg",4},{text,strlen(text)}};U opts[3]={0,1,64};
 U limits[10]={512,512,4096,32,544,1056,18432,32768,1024,32768};
 check(dong_frontend_check(opts,&source,1,limits,arena,sizeof arena,fr)==expect_front,"real frontend status");memcpy(saved,fr,sizeof fr);
 U n=0;if(expect_front)check(dong_frontend_diagnostic(&source,1,fr,baseline,sizeof baseline,&n)==0&&n>0,"baseline renderer");
 calls=sent=0;chunk=5;fail_at=over_at=zero_at=UINT64_MAX;memset(scratch,0xa5,sizeof scratch);memset(received,0xa5,sizeof received);
 Result r={99,98,97,96,95};U cap=sizeof scratch;
 if(action==1)cap=n-1;else if(action==2)zero_at=2;else if(action==3)fail_at=2;else if(action==4)over_at=2;else if(action==5)cap=n;
 U got=sink_emit(&source,1,fr,scratch,cap,77,wr,&r);
 check(!memcmp(saved,fr,sizeof fr),"frontend immutable");
 if(action==1){check(got==2&&r.code==2&&r.stage==1&&calls==0&&r.sent==0,"render failure");return;}
 if(!expect_front){check(got==0&&r.sent==0&&r.length==0&&calls==0,"normal source silent");return;}
 if(action==2)check(got==5&&r.stage==2&&r.sent==5&&calls==2,"no progress");
 else if(action==3)check(got==3&&r.code==0xbeef&&r.sent==5&&calls==2,"transport failure");
 else if(action==4)check(got==4&&r.sent==5&&calls==2,"overlong response");
 else check(got==0&&r.sent==n&&r.length==n&&sent==n,"complete prefix");
 check(r.sent==sent&&!memcmp(received,baseline,sent),"confirmed prefix");
 for(U i=n;i<sizeof scratch;i++)check(scratch[i]==0xa5,"scratch tail");
}
static void invalid(void){
 U fr[45]={0},saved[45];Result r={99,98,97,96,95},oldr=r;Source source={0,{"a.dg",4},{"module a;",9}};memcpy(saved,fr,sizeof fr);calls=0;
 check(sink_emit(&source,1,fr,(void*)fr,sizeof fr,77,wr,&r)==1&&calls==0&&!memcmp(fr,saved,sizeof fr)&&!memcmp(&r,&oldr,sizeof r),"alias preflight");
 check(sink_emit(&source,1,fr,scratch,sizeof scratch,77,wr,(Result*)(scratch+64))==1&&calls==0,"result tail alias");
 check(sink_emit(&source,1,NULL,scratch,sizeof scratch,77,wr,&r)==1&&calls==0,"null preflight");
}
int main(void){
 one("module a;fn f()u64{return 1;}",0,0);
 one("module a;fn f()u64{return unknown;}",3,0);
 one("module a;\n\xff",3,0);
 one("module a;fn f()u64{return true;}",3,0);
 one("module a;fn \xe4\xb8\xad\xe6\x96\x87()u64{return unknown;}",3,5);
 for(U action=1;action<=4;action++)one("module a;fn f()u64{return unknown;}",3,action);
 invalid();puts("sink checks passed");return 0;
}
'''
class GuestDiagnosticSinkTests(unittest.TestCase):
 def test_native_frontend_and_transport(self):
  nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
  work=ROOT/'build/test/guest-integration/CR46'/('run-'+uuid.uuid4().hex[:12]);work.mkdir(parents=True)
  snap=work/'source';shutil.copytree(ROOT/'lang/bootstrap',snap/'bootstrap');shutil.copytree(ROOT/'lang/std/core',snap/'core')
  production=SOURCE.read_text(encoding='utf-8');(work/'probe').mkdir();wrapper=work/'probe/sink_export.dg';wrapper.write_text(WRAPPER,encoding='utf-8');(work/'probe.c').write_text(HARNESS,encoding='utf-8')
  before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,SOURCE.with_suffix('.md'),Path(__file__))};records=[]
  variants=[('good',production),('bad-short-write',production.replace('  sent+=moved;','  sent+=remaining;')),
    ('bad-render-result',production.replace('return finish(r,RENDER,1,rendered,0,0);','return finish(r,OK,1,rendered,0,0);'))]
  for mode in ('debug','release'):
   for label,source in variants:
    (snap/'bootstrap/guest_diagnostic_sink.dg').write_text(source,encoding='utf-8')
    compiled=compile_file(wrapper,roots=[work,snap],mode=mode);name=mode+'-'+label
    asm=work/(name+'.asm');asm.write_text(compiled.assembly,encoding='utf-8');obj=work/(name+'.o');exe=work/(name+('.exe' if os.name=='nt' else ''))
    native='win64' if os.name=='nt' else 'elf64';commands=[]
    for fmt in ('elf64','win64'):
     target=obj if fmt==native else work/(name+'.'+fmt+'.o');commands.append([nasm,'-O0','-f',fmt,*nasm_flags(nasm),'-o',target,asm])
    commands.append([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',work/'probe.c',obj,'-o',exe])
    for i,cmd in enumerate(commands+[[exe]]):
     r=subprocess.run(list(map(str,cmd)),capture_output=True,timeout=180);(work/f'{name}-{i}.stdout').write_bytes(r.stdout);(work/f'{name}-{i}.stderr').write_bytes(r.stderr)
     expected=90 if label!='good' and i==len(commands) else 0
     self.assertEqual(r.returncode,expected,r.stderr.decode(errors='replace'))
     if expected:self.assertIn(b'sink assertion:',r.stderr)
     records.append(dict(command=list(map(str,cmd)),returncode=r.returncode,expected=expected))
  self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,SOURCE.with_suffix('.md'),Path(__file__))})
  artifacts={str(p.relative_to(work)):hashlib.sha256(p.read_bytes()).hexdigest() for p in work.rglob('*') if p.is_file()}
  (work/'summary.json').write_text(json.dumps(dict(inputs=before,records=records,artifacts=artifacts,source_stable=True,guest_executed=False),indent=2)+'\n')
if __name__=='__main__':unittest.main()
