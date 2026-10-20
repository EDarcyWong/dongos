"""Actual Dong commit state machine + files client, observed IPC boundary."""
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
ROOT=Path(__file__).resolve().parents[2]
WRAPPER='''module probe;
import lib.compiler_artifact as c;
import lib.files as f;
import bootstrap.guest_artifact_commit as a;
export("store") unsafe fn store(s:*f.Session,t:u64,p:*const u8,n:usize,st:*a.State,e:*u64)u64{
 unsafe{return c.store(s,t,slice_from_raw_parts(p,n),st,e);}
}
'''
HARNESS=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct{U endpoint,channel,root,rights,request[8],response[8];}Session;
typedef struct{U status,stage,code,written,total,attempts,stalls,flushes;}State;
extern U ABI store(Session*,U,const void*,U,State*,U*);
static unsigned char backing[73728],src[2097152],saved[2097152],disk[2097152];
static unsigned char*channel;
static U size,chunk,offset,writes,flushes,fail_at,oversize,zero,flush_fail,bad_version,error_value;
static void check(int ok,const char*s){if(!ok){fprintf(stderr,"FAIL %s\n",s);exit(90);}}
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*p,U n){(void)k;(void)l;(void)p;(void)n;check(0,"panic");abort();}
U ABI svc_receive(U a,void*b,U*c){(void)a;(void)b;(void)c;abort();}
U ABI svc_reply_wait(U a,U b,const void*c,void*d,U*e){(void)a;(void)b;(void)c;(void)d;(void)e;abort();}
void ABI svc_fence(void){}
U ABI svc_call(U number,U endpoint,U request,U response,U a,U b,U c){
 (void)a;(void)b;(void)c;check(number==0x22&&endpoint==77,"only authorized file IPC");
 U*q=(U*)(uintptr_t)request,*r=(U*)(uintptr_t)response;
 check(q[1]==0x100000101ULL&&q[4]==0&&q[5]==0&&q[6]==3&&q[7]==0,"borrowed token/request fields");
 memset(r,0,64);r[5]=3;
 if(q[0]==0x207){
  ++writes;U count=size-offset;if(count>61440)count=61440;
  check(q[2]==offset&&q[3]==count&&count>0,"write range");
  check(!memcmp(channel+4096,src+offset,count),"write bytes");
  if(writes==fail_at){r[0]=error_value;return 0;}
  if(writes==bad_version){r[5]=2;return 0;}
  if(writes==oversize){r[1]=count+1;return 0;}
  U n=count;if(n>chunk)n=chunk;if(zero)n=0;
  memcpy(disk+offset,channel+4096,n);offset+=n;r[1]=n;return 0;
 }
 check(q[0]==0x20d&&q[2]==0&&q[3]==0,"H_SYNC only after writes");
 check(offset==size,"flush requires complete artifact");++flushes;
 if(flush_fail)r[0]=error_value;return 0;
}
static void run(U n,U step,U failure,U over,U stall,U ff,U ver,U expected,U confirmed,U io,U expected_flush){
 size=n;chunk=step;offset=writes=flushes=0;fail_at=failure;oversize=over;zero=stall;flush_fail=ff;bad_version=ver;
 memset(disk,0xa5,sizeof disk);Session s={0};s.endpoint=77;s.channel=(U)(uintptr_t)channel;
 State st={99,98,97,96,95,94,93,92};U error=123;
 U status=store(&s,0x100000101ULL,src,n,&st,&error);
 check(status==expected&&st.status==(expected==3?3:4)&&st.written==confirmed&&st.total==n&&error==io,"result");
 check(flushes==expected_flush&&st.flushes==flushes&&st.attempts==writes,"call counters");
 check(!memcmp(src,saved,sizeof src),"immutable artifact");
 check(!memcmp(disk,src,confirmed),"confirmed disk prefix");
 for(U i=confirmed;i<sizeof disk;i++)check(disk[i]==0xa5,"unwritten suffix");
 if(stall)check(writes==8&&st.stalls==8&&st.stage==1&&st.code==1,"bounded stalls");
 if(expected==3)check(st.written==st.total&&st.stage==0&&st.code==0,"durability gate");
}
static void invalid(void){
 for(unsigned i=0;i<15;i++){
  Session s={0};s.endpoint=77;s.channel=(U)(uintptr_t)channel;State st={99,98,97,96,95,94,93,92};U err=123;
  Session*sp=&s;State*tp=&st;U*ep=&err;const void*p=src;U n=64,t=0x100000101ULL;
  switch(i){
   case 0:sp=NULL;break;case 1:t=0;break;case 2:s.channel++;break;case 3:s.endpoint=0;break;
   case 4:p=channel+4096;break;case 5:p=&s;break;case 6:p=&st;break;case 7:p=&err;break;
   case 8:tp=(State*)(channel+4096);break;case 9:tp=(State*)src;break;case 10:ep=(U*)&s;break;
   case 11:ep=(U*)&st;break;case 12:n=2097153;break;case 13:p=NULL;break;case 14:ep=(U*)(uintptr_t)(UINT64_MAX-3);break;
  }
  Session old=s;State oldst=st;U olderr=err;writes=flushes=0;
  check(store(sp,t,p,n,tp,ep)==1&&!writes&&!flushes,"preflight before IPC");
  check(!memcmp(&s,&old,sizeof s)&&!memcmp(&st,&oldst,sizeof st)&&err==olderr&&!memcmp(src,saved,sizeof src),"invalid atomicity");
 }
}
int main(void){
 channel=(unsigned char*)(((uintptr_t)backing+4095)&~(uintptr_t)4095);
 for(U i=0;i<sizeof src;i++)src[i]=(unsigned char)(i*17+3);memcpy(saved,src,sizeof src);
 invalid();error_value=0xdead;
 run(0,1,0,0,0,0,0,3,0,0,1);
 run(17,3,0,0,0,0,0,3,17,0,1);
 run(2097152,61440,0,0,0,0,0,3,2097152,0,1);
 run(17,3,2,0,0,0,0,2,3,0xdead,0);
 run(17,17,0,0,0,1,0,2,17,0xdead,1);
 run(17,17,0,1,0,0,0,2,0,0x05130002,0);
 run(131072,61440,0,1,0,0,0,2,0,0x05130002,0);
 run(17,17,0,0,1,0,0,2,0,0,0);
 run(17,17,0,0,0,0,1,2,0,0x05080003,0);
 error_value=UINT64_MAX;run(17,17,1,0,0,0,0,2,0,UINT64_MAX,0);
 puts("guest file commit checks passed");return 0;
}
'''
class Tests(unittest.TestCase):
 def test_actual_write_sync_client_and_commit(self):
  out=ROOT/'build/test/guest-files-commit'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
  names=('services/lib/compiler_artifact.dg','services/lib/files.dg','services/lib/sys.dg','services/lib/abi.dg',
   'services/fs/protocol.dg','services/fs/handles.dg','lang/bootstrap/guest_artifact_commit.dg','lang/tests/test_guest_files_commit.py')
  before={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names};snapshot=out/'source'
  for n in names[:-1]:
   p=Path(n);target=snapshot/Path(*p.parts[1:]);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/n).read_bytes())
  wrapper=out/'probe.dg';wrapper.write_text(WRAPPER);harness=out/'probe.c';harness.write_text(HARNESS)
  nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);records=[]
  source=(snapshot/'lib/compiler_artifact.dg').read_text()
  for mode in ('debug','release'):
   for variant in ('normal','skip-real-sync','accept-oversize'):
    altered=source
    if variant=='skip-real-sync':altered=altered.replace('let status=files.sync((*c).session,(*c).token);','let status=0 as u64;')
    if variant=='accept-oversize':altered=altered.replace('if moved>count{','if false{')
    (snapshot/'lib/compiler_artifact.dg').write_text(altered)
    compiled=compile_file(wrapper,roots=[snapshot,out],mode=mode);name=mode+'-'+variant
    asm=out/(name+'.asm');asm.write_text(compiled.assembly);obj=out/(name+'.o');exe=out/(name+('.exe' if os.name=='nt' else ''))
    commands=[]
    for fmt in ('elf64','win64'):
     target=obj if fmt==('win64' if os.name=='nt' else 'elf64') else out/(name+'.'+fmt+'.o')
     commands.append([nasm,'-O0','-f',fmt,*nasm_flags(nasm),'-o',target,asm])
    commands.append([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',harness,obj,'-o',exe])
    for i,argv in enumerate(commands+[[exe]]):
     r=subprocess.run(list(map(str,argv)),capture_output=True,timeout=120)
     (out/f'{name}-{i}.stdout').write_bytes(r.stdout);(out/f'{name}-{i}.stderr').write_bytes(r.stderr)
     expected=90 if i==len(commands) and variant!='normal' else 0
     self.assertEqual(r.returncode,expected,r.stderr.decode(errors='replace'))
     if expected:self.assertIn(b'FAIL ',r.stderr)
     records.append(dict(command=list(map(str,argv)),returncode=r.returncode,expected=expected))
  self.assertEqual(before,{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names})
  (out/'summary.json').write_text(json.dumps(dict(inputs=before,records=records,source_stable=True,guest_executed=False),indent=2)+'\n')
if __name__=='__main__':unittest.main()
