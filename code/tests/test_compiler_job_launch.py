"""Execute the exact launch descriptor/result checks; full kernel type check."""
from pathlib import Path
import hashlib,json,os,subprocess,unittest,uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct{U image,image_bytes,blob,blob_bytes,output,result;}Q;
typedef struct{U status,stage,code,detail,written,offset,front,retained,backend;}R;
extern U ABI request(const Q*,U),result(const R*,U);
static void ck(int b){if(!b)exit(90);}
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*p,U n){(void)k;(void)l;(void)p;(void)n;exit(91);}
int main(void){
 Q q={0x10000000,4096,0x11000000,447948,0x12000000,0x13000000};
 ck(request(&q,0x14000000)==1);
 for(U i=0;i<26;i++){Q b=q;U p=0x14000000;
  switch(i){case 0:b.image_bytes=4095;break;case 1:b.image_bytes=2097153;break;case 2:b.blob_bytes=15;break;case 3:b.blob_bytes=524289;break;
   case 4:b.image=0;break;case 5:b.blob=0;break;case 6:b.output=0;break;case 7:b.result=0;break;case 8:b.result++;break;
   case 9:b.image=UINT64_MAX-4095;break;case 10:b.blob=UINT64_MAX-15;break;case 11:b.output=0x8000000000-1048576;break;case 12:b.result=0x8000000000-8;break;
   case 13:b.blob=0x1000000-4096;break;case 14:b.blob=0x20000000-4096;break;
   case 15:b.output=p;break;case 16:b.output=b.image;break;case 17:b.output=b.blob;break;
   case 18:b.result=p;break;case 19:b.result=b.image;break;case 20:b.result=b.blob;break;case 21:b.result=b.output;break;
   case 22:p=0;break;case 23:p=0x8000000000-8;break;case 24:b.output=b.blob+b.blob_bytes-1;break;case 25:b.result=b.blob+b.blob_bytes-4;break;
  }ck(request(&b,p)==0);
 }
 R r={0,3,0,0,4096,8388608,58720256,49283072,49283072};ck(result(&r,0)==1);
 for(U s=1;s<4;s++){R b={s,2,3,4,0,0,0,0,0};ck(result(&b,s)==1);b.written=1;ck(result(&b,s)==0);}
 for(U i=0;i<14;i++){R b=r;U status=0;switch(i){case 0:status=1;break;case 1:b.status=4;status=4;break;case 2:b.stage=4;break;
  case 3:b.front++;break;case 4:b.retained++;break;case 5:b.backend++;break;case 6:b.stage=2;break;case 7:b.code=1;break;case 8:b.detail=1;break;
  case 9:b.written=4095;break;case 10:b.written=2097153;break;case 11:b.offset++;break;case 12:b.status=2;status=2;break;case 13:b.written=UINT64_MAX;break;}
  ck(result(&b,status)==0);
 }
 puts("PASS request 26 rejection cases; result 20 rejection cases");return 0;
}
'''
class LaunchTests(unittest.TestCase):
    def test_actual_syscall_gates(self):
        work=ROOT/'build/test/compiler-launch'/('gate-'+uuid.uuid4().hex[:12]);work.mkdir(parents=True)
        services=(ROOT/'kernel/user/services.dg').read_text()
        branch=services[services.index('        if COMPILER&&CURRENT==compiler_job.SLOT{'):services.index('        if code>=0x80&&code<=0x89{return try process_call(frame);}')]
        compiler_stub='''module user.compiler_job;pub const SLOT:usize=3;pub var RUNNING:bool=true;pub var FAILED:bool=false;pub var STARTS:u64=0;pub var FINISHES:u64=0;pub var ARG:u64=0;pub var MODE:u64=0;pub error Bad=99;
pub unsafe fn start(a:u64)!void{unsafe{STARTS+=1;ARG=a;if MODE==2{FAILED=true;}if MODE!=0{return error.Bad;}RUNNING=true;}return;}
pub unsafe fn finish(s:u64)!void{unsafe{FINISHES+=1;ARG=s;if MODE==6{return error.Bad;}RUNNING=false;}return;}
pub fn reset(mode:u64)void{unsafe{MODE=mode;RUNNING=mode!=4;FAILED=false;STARTS=0;FINISHES=0;ARG=0;}return;}'''
        prefix='''module gate;import user.abi as abi;import user.compiler_job as compiler_job;import user.memory as memory;
pub error Protocol=0x050b_0002;pub error InvalidCall=0x050b_0001;
var COMPILER:bool=false;var GRAPHICS:bool=false;var CATALOG:*u8=null;var CURRENT:usize=0;var ACTIVE:usize=3;var LAUNCH_FAILED:bool=false;
struct State{waiting:u64}const EMPTY_STATE:State=State{waiting:0};var STATES:[4]State=[EMPTY_STATE;4];
struct Process{frame:abi.Frame}var PROCESSES:[4]Process=[Process{frame:abi.EMPTY_FRAME};4];
unsafe fn process(id:usize)*Process{unsafe{return &PROCESSES[id];}}
unsafe fn perform(frame:*abi.Frame)!usize{unsafe{let code=(*frame).rax;
'''
        suffix='''return error.InvalidCall;}}
export("probe") unsafe fn probe(flags:u64,current:usize,code:u64,mask:u64,mode:u64,out:*u64)u64{unsafe{
 COMPILER=(flags&1)!=0;GRAPHICS=(flags&2)!=0;CATALOG=null;if (flags&4)!=0{CATALOG=(1 as u64) as *u8;}ACTIVE=3;if (flags&8)!=0{ACTIVE=4;}
 CURRENT=current;LAUNCH_FAILED=false;STATES=[EMPTY_STATE;4];compiler_job.reset(mode);memory.STAGE_FAILED=mode==3;
 var f=abi.EMPTY_FRAME;f.rax=code;f.rdi=1234;if code==255{f.rdi=0;}f.rsi=mask&1;f.rdx=mask&2;f.r10=mask&4;f.r8=mask&8;f.r9=mask&16;
 var status:u64=0;var next:usize=99;match perform(&f){ok(id)=>{next=id;},err(e)=>{status=e;},}
 *out=next as u64;*(out+1)=STATES[0].waiting;*(out+2)=ACTIVE as u64;*(out+3)=compiler_job.STARTS;*(out+4)=compiler_job.FINISHES;*(out+5)=compiler_job.ARG;*(out+6)=LAUNCH_FAILED as u64;return status;
}}
'''
        harness=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
typedef uint64_t U;
extern U __attribute__((sysv_abi)) probe(U,U,U,U,U,U*);
static void ck(int b){if(!b)exit(90);}
void __attribute__((sysv_abi,noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*p,U n){(void)k;(void)l;(void)p;(void)n;exit(91);}
int main(void){U o[7];ck(probe(1,0,0x8a,0,0,o)==0&&o[0]==3&&o[1]==7&&o[2]==4&&o[3]==1&&o[4]==0&&o[5]==1234&&o[6]==0);
 for(U i=0;i<5;i++)ck(probe(1,0,0x8a,1ULL<<i,0,o)==0x050b0002&&o[3]==0);
 for(U i=0;i<4;i++)ck(probe(1,i+1,0x8a,0,0,o)==0x050b0002&&o[3]==0);
 for(U f=0;f<16;f++)if(f!=1)ck(probe(f,0,0x8a,0,0,o)==0x050b0002&&o[3]==0);
 for(U mode=1;mode<=3;mode++){ck(probe(1,0,0x8a,0,mode,o)==0x050b0002&&o[3]==1&&o[1]==0&&o[2]==3);ck(o[6]==(mode!=1));}
 ck(probe(9,3,255,0,0,o)==0&&o[0]==0&&o[1]==0&&o[2]==3&&o[4]==1&&o[3]==0);
 ck(probe(9,3,255,0,4,o)==0x050b0002&&o[4]==0);
 ck(probe(9,3,255,0,6,o)==0x050b0002&&o[4]==1&&o[6]==1);
 U ops[]={1,2,3,0x22,0x70,0x78,0x8a,0xfe};for(U i=0;i<8;i++)ck(probe(9,3,ops[i],0,0,o)==0x050b0002&&o[3]==0&&o[4]==0);
 puts("PASS real syscall gate and transition branches");return 0;}
'''
        (work/'probe.c').write_text(harness);nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
        for mode in ['debug','release']:
            for variant in ['normal','bad-profile','bad-owner-wait']:
                p=work/(mode+'-'+variant);(p/'user').mkdir(parents=True)
                (p/'user/abi.dg').write_bytes((ROOT/'kernel/user/abi.dg').read_bytes())
                (p/'user/compiler_job.dg').write_text(compiler_stub)
                (p/'user/memory.dg').write_text('module user.memory;pub var STAGE_FAILED:bool=false;')
                body=branch
                if variant=='bad-profile':body=body.replace('!COMPILER||GRAPHICS','GRAPHICS',1)
                if variant=='bad-owner-wait':body=body.replace('STATES[0].waiting=7','STATES[0].waiting=0',1)
                (p/'gate.dg').write_text(prefix+body+suffix)
                result=compile_file(p/'gate.dg',roots=[p],mode=mode);(p/'gate.asm').write_text(result.assembly)
                fmt='win64' if os.name=='nt' else 'elf64'
                for f in [fmt,'elf64' if fmt=='win64' else 'win64']:
                    r=subprocess.run([nasm,'-O0','-f',f,*nasm_flags(nasm),'-o',str(p/(f+'.o')),str(p/'gate.asm')],capture_output=True,timeout=60);self.assertEqual(r.returncode,0,r.stderr)
                exe=p/('probe.exe' if os.name=='nt' else 'probe')
                r=subprocess.run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),str(work/'probe.c'),str(p/(fmt+'.o')),'-o',str(exe)],capture_output=True,timeout=60);self.assertEqual(r.returncode,0,r.stderr)
                r=subprocess.run([str(exe)],capture_output=True,timeout=30);(p/'execution.log').write_bytes(r.stdout+r.stderr);self.assertEqual(r.returncode,0 if variant=='normal' else 90,r.stderr)
    def test_exact_checks_and_kernel(self):
        work=ROOT/'build/test/compiler-launch'/('run-'+uuid.uuid4().hex[:12]);work.mkdir(parents=True)
        paths=[ROOT/'kernel/user/compiler_job.dg',ROOT/'kernel/user/services.dg',ROOT/'kernel/services_run.asm',ROOT/'services/compiler/controller.dg',ROOT/'tools/build.py']
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        source=paths[0].read_text().split('// LAUNCH_IMPLEMENTATION:')[0]
        source=source.replace('import user.memory as memory;','').replace('import user.abi as abi;','').replace('import boot.service_memory as resources;','').replace('memory.STACK_TOP','0x0000_007f_fff0_0000')
        (work/'probe.c').write_text(HARNESS)
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
        records=[]
        def run(cmd,label,expected=0):
            r=subprocess.run(list(map(str,cmd)),capture_output=True,timeout=300)
            (work/(label+'.stdout')).write_bytes(r.stdout);(work/(label+'.stderr')).write_bytes(r.stderr)
            self.assertEqual(r.returncode,expected,r.stderr.decode(errors='replace'));records.append({'command':list(map(str,cmd)),'returncode':r.returncode})
        for mode in ['debug','release']:
            for variant in ['normal','bad-source-alias','bad-output-offset']:
                snap=work/(mode+'-'+variant);(snap/'user').mkdir(parents=True)
                (snap/'exec').mkdir();(snap/'exec/elf.dg').write_text('module exec.elf;pub const USER_MIN:u64=0x10000;pub const USER_LIMIT:u64=0x8000000000;')
                s=source
                if variant=='bad-source-alias':s=s.replace('i<3','i<2',1)
                if variant=='bad-output-offset':s=s.replace('&&(*r).offset==8*M','',1)
                (snap/'user/compiler_job.dg').write_text(s)
                p=snap/'probe.dg';p.write_text('module probe;import user.compiler_job as j;export("request") unsafe fn req(q:*const j.Request,a:u64)bool{unsafe{return j.valid(q,a);}}export("result") unsafe fn res(r:*const j.Result,s:u64)bool{unsafe{return j.valid_result(r,s);}}')
                c=compile_file(p,roots=[snap],mode=mode)
                a=snap/'probe.asm';a.write_text(c.assembly);o=snap/'probe.o';tag=mode+'-'+variant
                fmt='win64' if os.name=='nt' else 'elf64'
                run([nasm,'-O0','-f',fmt,*nasm_flags(nasm),'-o',o,a],tag+'-asm')
                run([nasm,'-O0','-f','elf64' if fmt=='win64' else 'win64',*nasm_flags(nasm),'-o',snap/'other.o',a],tag+'-other')
                e=snap/('probe.exe' if os.name=='nt' else 'probe')
                run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),work/'probe.c',o,'-o',e],tag+'-link')
                run([e],tag+'-execute',0 if variant=='normal' else 90)
            compile_file(paths[1],roots=[ROOT/'kernel',ROOT/'services',ROOT/'lang/examples',ROOT/'lang/std'],mode=mode)
            compile_file(paths[3],roots=[ROOT/'services',ROOT/'lang',ROOT/'lang/std'],mode=mode)
        self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
        (work/'receipt.json').write_text(json.dumps({'source_stable':True,'sources':before,'commands':records},indent=2))

# Independent lifecycle oracle, embedded so formal snapshots need no build files.
LIFECYCLE_FIXTURES={'exports.dg': 'export("job_reset") fn test_reset()void{unsafe{RUNNING=false;FAILED=false;RUNS=0;LAST=EMPTY_RESULT;REQUEST=EMPTY;IMAGE=null;}return;}\nexport("job_start") fn test_start()u64{unsafe{match start(0x14000000){ok=>{return 0;},err(e)=>{return e;},}}}\nexport("job_finish") fn test_finish(s:u64)u64{unsafe{match finish(s){ok=>{return 0;},err(e)=>{return e;},}}}\nexport("job_get") fn test_get(k:u64)u64{unsafe{\n if k==0{return RUNNING as u64;}if k==1{return FAILED as u64;}if k==2{return RUNS;}\n if k==3{return REQUEST.blob;}if k==4{return LAST.status;}return 0;\n}}\nexport("job_snapshot") fn test_snapshot(i:usize)u64{unsafe{if IMAGE==null{return 0;}return IMAGE[i]as u64;}}\n', 'memory.dg': 'module user.memory;\nimport user.abi as abi;\nimport exec.elf as elf;\nimport user.compiler_stack as profile;\npub const STACK_TOP:u64=0x7ffff00000;\npub error Injected=0x0513_10ff;\npub error Contract=0x0513_10fe;\npub struct Process{pub ready:u64,pub root:u64,pub frame:abi.Frame,pub plan:elf.Plan}\nconst E:Process=Process{ready:0,root:0,frame:abi.EMPTY_FRAME,plan:elf.EMPTY_PLAN};\nvar P:[16]Process=[E;16];\npub var FAIL:u64=0;\nvar Q:*const u8=null;var IMAGE:*const u8=null;var OUT:*u8=null;var RESULT:*u8=null;var META:*const u8=null;\nvar COUNTS:[32]u64=[0;32];\nexport("mock_setup") pub fn setup(q:*const u8,image:*const u8,out:*u8,result:*u8,meta:*const u8)void{unsafe{\n Q=q;IMAGE=image;OUT=out;RESULT=result;META=meta;FAIL=0;COUNTS=[0;32];P[0]=E;P[0].ready=1;P[3]=E;\n}return;}\nexport("mock_fail") fn fail(value:u64)void{unsafe{FAIL=value;}return;}\nexport("mock_get") fn get(k:usize)u64{unsafe{\n if k==14{return P[3].ready;}if k==20{return P[3].frame.rdi;}if k==21{return P[3].frame.rsi;}\n if k==22{return P[3].frame.rdx;}if k==23{return P[3].frame.rcx;}if k==24{return P[3].frame.r8;}if k==25{return P[3].frame.r9;}\n if k==29{return P[3].frame.r10;}return COUNTS[k];\n}}\npub fn processes()*Process{unsafe{return &P[0];}}\npub unsafe fn check_range(id:usize,address:u64,n:usize,write:bool)!void{unsafe{\n if id!=0{return error.Contract;}let c=COUNTS[7];COUNTS[7]+=1;if write{COUNTS[8]|=1<<c;}\n if (FAIL>=2&&FAIL<=5)&&c==FAIL-2{return error.Injected;}\n if c==0&&(address!=0x10000000||n!=4096||write){return error.Contract;}\n if c==1&&(address!=0x11000003||n!=5000||write){return error.Contract;}\n if c==2&&(address!=0x12000000||n!=2097152||!write){return error.Contract;}\n if c==3&&(address!=0x13000000||n!=72||!write){return error.Contract;}\n}return;}\npub unsafe fn copy_in(id:usize,address:u64,out:[]u8)!void{unsafe{\n var src:*const u8=null;\n if id==0&&address==0x14000000{COUNTS[10]+=1;if FAIL==1{return error.Injected;}if out.len!=48{return error.Contract;}src=Q;}\n else if id==0&&address==0x10000000{COUNTS[9]+=1;if FAIL==6{return error.Injected;}if out.len!=4096{return error.Contract;}src=IMAGE;}\n else if id==3&&address==0x70000000{if FAIL==12{return error.Injected;}if out.len!=72{return error.Contract;}src=META;}\n else if id==3&&address>=0x20800000&&address<=0x20a00000&&out.len as u64<=0x20a00000-address{\n  COUNTS[11]+=1;if FAIL==13&&COUNTS[11]==2{return error.Injected;}\n  var i:usize=0;while i<out.len{out[i]=(address+i as u64)as u8;i+=1;}return;\n }else{return error.Contract;}\n var i:usize=0;while i<out.len{out[i]=*(src+i);i+=1;}\n}return;}\npub unsafe fn copy_out(id:usize,address:u64,src:[]const u8)!void{unsafe{\n if id!=0{return error.Contract;}var dst:*u8=null;\n if address>=0x12000000&&address<=0x12200000&&src.len as u64<=0x12200000-address{\n  COUNTS[12]+=1;if FAIL==14{return error.Injected;}dst=OUT+(address-0x12000000)as usize;\n }else if address==0x13000000&&src.len==72{COUNTS[13]+=1;if FAIL==15{return error.Injected;}dst=RESULT;}\n else{return error.Contract;}\n var i:usize=0;while i<src.len{*(dst+i)=src[i];i+=1;}\n}return;}\npub unsafe fn stage_compiler(id:usize,image:[]const u8,bias:u64,top:u64)!void{unsafe{\n COUNTS[0]+=1;COUNTS[26]=top;COUNTS[27]=profile.pages(true);\n if id!=3||image.len!=4096||bias!=0||top!=STACK_TOP-3*0x1000000{return error.Contract;}\n if FAIL==7{COUNTS[4]+=1;return error.Injected;}\n P[3].ready=1;P[3].root=0x300000;COUNTS[15]=1;\n}return;}\npub unsafe fn share(source:usize,target:usize,va:u64,write:bool)!void{unsafe{\n COUNTS[1]+=1;if FAIL==8||FAIL==18{return error.Injected;}\n if source!=0||target!=3||write||va!=0x11000000+(COUNTS[1]-1)*4096{return error.Contract;}\n}return;}\npub unsafe fn anonymous(id:usize,va:u64)!u64{unsafe{\n COUNTS[2]+=1;if id!=3{return error.Contract;}\n if COUNTS[2]==1{if va!=0x70000000{return error.Contract;}if FAIL==9{return error.Injected;}}\n else{COUNTS[3]+=1;if va!=0x20000000+(COUNTS[3]-1)*4096{return error.Contract;}if FAIL==10&&COUNTS[3]==3{return error.Injected;}}\n return 0x500000;\n}}\npub unsafe fn stage_commit(id:usize)!void{unsafe{\n COUNTS[5]+=1;if id!=3||P[3].ready!=1||COUNTS[15]!=1{return error.Contract;}\n if FAIL==11{return error.Injected;}COUNTS[15]=0;\n}return;}\npub unsafe fn stage_abort(id:usize)!void{unsafe{\n COUNTS[4]+=1;if id!=3||P[3].ready!=1||COUNTS[15]!=1{return error.Contract;}\n if FAIL==18{return error.Injected;}P[3]=E;COUNTS[15]=0;\n}return;}\npub unsafe fn destroy(id:usize)!void{unsafe{\n COUNTS[6]+=1;if id!=3||P[3].ready!=1||COUNTS[15]!=0{return error.Contract;}\n if FAIL==16{return error.Injected;}P[3]=E;\n if FAIL==19{COUNTS[28]=1;return error.Injected;}\n}return;}\n', 'probe.c': '#include <stdint.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#define ABI __attribute__((sysv_abi))\ntypedef uint64_t U;\ntypedef struct{U image,image_bytes,blob,blob_bytes,output,result;} Q;\ntypedef struct{U status,stage,code,detail,written,offset,frontend,retained,backend;} R;\nextern void ABI mock_setup(const void*,const void*,void*,void*,const void*),mock_fail(U),resource_reset(void),job_reset(void);\nextern U ABI mock_get(U),resource_calls(void),job_start(void),job_finish(U),job_get(U),job_snapshot(U);\nstatic unsigned char image[4096],out[2097152];static Q q;static R core,response;static unsigned cases,checks;\nstatic void ck(int good,const char*why){++checks;if(!good){fprintf(stderr,"FAIL case=%u %s\\n",cases,why);exit(90);}}\nvoid ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t line,const void*p,U n){(void)p;(void)n;fprintf(stderr,"PANIC %u/%u\\n",k,line);exit(91);}\nstatic void u16(unsigned p,uint16_t v){memcpy(image+p,&v,2);}static void u32(unsigned p,uint32_t v){memcpy(image+p,&v,4);}static void u64(unsigned p,U v){memcpy(image+p,&v,8);}\nstatic void elf(void){memset(image,0,sizeof image);memcpy(image,"\\177ELF\\2\\1\\1",7);u16(16,2);u16(18,62);u32(20,1);u64(24,0x400200);u64(32,64);u16(52,64);u16(54,56);u16(56,1);u32(64,1);u32(68,5);u64(80,0x400000);u64(96,4096);u64(104,4096);u64(112,4096);}\nstatic void reset(void){++cases;elf();q=(Q){0x10000000,4096,0x11000003,5000,0x12000000,0x13000000};core=(R){0,3,0,0,8192,8388608,58720256,20000000,16000000};memset(out,0xa5,sizeof out);memset(&response,0xa5,sizeof response);job_reset();resource_reset();mock_setup(&q,image,out,&response,&core);}\nstatic int untouched(const void*p,U n){const unsigned char*b=p;while(n--)if(*b++!=0xa5)return 0;return 1;}\nstatic void launched(void){ck(job_start()==0,"valid request did not launch");ck(job_get(0)==1&&job_get(1)==0&&job_get(2)==1,"running publication differs");ck(mock_get(0)==1&&mock_get(1)==2&&mock_get(27)==16,"fixed stack entry / readonly loan contract differs");ck(mock_get(2)==14337&&mock_get(3)==14336&&mock_get(5)==1,"complete 56MiB arena / meta / commit differs");ck(mock_get(7)==4&&mock_get(8)==12,"controller range authority checks differ");ck(mock_get(9)==1&&mock_get(10)==1&&resource_calls()==1,"request/image snapshot counts differ");ck(mock_get(14)==1&&mock_get(15)==0,"stage not committed");ck(mock_get(20)==q.blob&&mock_get(21)==q.blob_bytes&&mock_get(22)==0x70000080&&mock_get(23)==0x20000000&&mock_get(24)==58720256&&mock_get(25)==0x70000000&&mock_get(29)==0x20000000,"pure core register ABI differs");ck(mock_get(26)==UINT64_C(0x7ffff00000)-3*UINT64_C(0x1000000),"fixed compiler stack top differs");ck(untouched(out,sizeof out)&&untouched(&response,sizeof response),"start published output early");}\nint main(void){\n reset();launched();image[0]=0;ck(job_snapshot(0)==0x7f,"ELF was not snapshotted privately");ck(job_finish(0)==0,"valid finish rejected");ck(!job_get(0)&&!job_get(1)&&job_get(2)==1&&job_get(3)==0,"successful finish did not clear job state");ck(mock_get(6)==1&&mock_get(14)==0,"successful finish did not destroy job");ck(!memcmp(&response,&core,sizeof core),"validated result not copied exactly");for(U i=0;i<core.written;i++)ck(out[i]==(i&255),"artifact bounded copy differs");ck(untouched(out+core.written,sizeof out-core.written),"artifact over-copy");\n // A fresh request after success reuses the private image allocation.\n elf();mock_setup(&q,image,out,&response,&core);ck(job_start()==0&&resource_calls()==1,"image snapshot cache allocation regression");ck(job_finish(0)==0&&mock_get(14)==0,"second synchronous job cleanup differs");\n reset();q.image_bytes=4095;ck(job_start()==0x05131001,"invalid descriptor accepted");ck(!resource_calls()&&!mock_get(0)&&!mock_get(7)&&!mock_get(9)&&!job_get(0),"invalid descriptor published/staged");\n reset();image[0]=0;ck(job_start()==0x04030002,"real ELF bad header not rejected");ck(!mock_get(0)&&mock_get(14)==0&&!job_get(0),"bad ELF staged");\n reset();u64(24,0x900200);u64(80,0x900000);ck(job_start()==0x05131001,"ELF outside fixed private image window accepted");ck(!mock_get(0)&&!job_get(0),"bad ELF window staged");\n reset();u64(104,8192);ck(job_start()==0x05131001,"ELF BSS expansion accepted");ck(!mock_get(0)&&!job_get(0),"ELF BSS staged");\n reset();u16(56,3);for(unsigned i=1;i<3;i++){unsigned p=64+56*i;u32(p,1);u32(p+4,6);u64(p+16,0x400000+i*0x100000);u64(p+32,4096);u64(p+40,4096);u64(p+48,4096);}ck(job_start()==0x05131001,"ELF excess segments accepted");ck(!mock_get(0)&&!job_get(0),"excess ELF segments staged");\n for(U failure=1;failure<=11;failure++){\n  reset();mock_fail(failure);ck(job_start()==0x051310ff,"injected launch boundary did not propagate error");ck(!job_get(0)&&!job_get(1)&&job_get(2)==0,"failed launch published running state");ck(mock_get(14)==0&&mock_get(15)==0,"stage abort did not withdraw failed candidate");ck(untouched(out,sizeof out)&&untouched(&response,sizeof response),"failed launch changed controller outputs");\n  if(failure>=8)ck(mock_get(4)==1,"late failure did not abort exactly once");\n }\n reset();mock_fail(17);ck(job_start()==0x051310ff&&!mock_get(0)&&!job_get(0),"private snapshot allocation failure published");\n reset();mock_fail(18);ck(job_start()==0x051310ff&&job_get(1)==1&&!job_get(0)&&mock_get(14)==1,"abort failure not held/fail closed");ck(job_start()==0x05131001,"held abort failure allowed retry");\n reset();launched();U copies=mock_get(9);ck(job_start()==0x05131001&&mock_get(9)==copies,"running job allowed overlapping start");\n reset();ck(job_finish(0)==0x05131001&&!mock_get(6),"finish without running accepted");\n reset();launched();core.offset++;ck(job_finish(0)==0x05131001&&job_get(0)&&job_get(1)&&mock_get(14)==1,"invalid returned result not held");ck(!mock_get(6)&&!mock_get(12)&&!mock_get(13)&&untouched(out,sizeof out)&&untouched(&response,sizeof response),"invalid returned result published artifact");\n reset();launched();core=(R){2,2,3,4,0,0,1,2,3};ck(job_finish(2)==0&&!job_get(0)&&mock_get(14)==0,"valid failure result cleanup rejected");ck(!mock_get(12)&&mock_get(13)==1&&!memcmp(&response,&core,sizeof core)&&untouched(out,sizeof out),"failure result published bytes");\n for(U failure=12;failure<=16;failure++){\n  reset();launched();mock_fail(failure);ck(job_finish(0)==0x051310ff,"injected return boundary did not propagate error");ck(job_get(0)&&mock_get(14)==1,"return/destroy failure did not hold process");\n  if(failure<16)ck(!mock_get(6),"copy failure destroyed before complete publication");\n }\n reset();launched();mock_fail(19);ck(job_finish(0)==0x051310ff,"partial-withdraw destroy failure did not propagate");ck(job_get(0)&&!mock_get(14)&&mock_get(28)==1,"partial-withdraw destroy failure did not hold job state");ck(job_start()==0x05131001,"partially withdrawn failed job allowed new start");\n reset();launched();core.written=2097152;ck(job_finish(0)==0&&mock_get(11)==512&&mock_get(12)==512,"maximum artifact did not copy in 512 bounded chunks");for(U i=0;i<sizeof out;i++)ck(out[i]==(i&255),"maximum artifact byte differs");ck(!memcmp(&response,&core,sizeof core)&&!job_get(0)&&!mock_get(14),"maximum artifact cleanup differs");\n printf("PASS full production start/finish: %u lifecycle cases, %u assertions; actual ELF validation, 56MiB allocation count, fixed compiler stack API, RO loan, rollback and held failures\\n",cases,checks);return 0;\n}\n', 'resources.dg': 'module boot.service_memory;\nimport user.memory as memory;\npub struct Block{pub physical:u64,pub virtual:u64,pub pages:usize}\nvar IMAGE:[2097152]u8=[0;2097152];var CALLS:u64=0;\nexport("resource_reset") fn reset()void{unsafe{CALLS=0;}return;}\nexport("resource_calls") fn calls()u64{unsafe{return CALLS;}}\npub unsafe fn allocate(pages:usize,alignment:usize,out:*Block)!void{unsafe{\n CALLS+=1;if memory.FAIL==17{return error.memory.Injected;}\n if pages!=512||alignment!=1{return error.memory.Contract;}\n *out=Block{physical:0x800000,virtual:&IMAGE[0]as u64,pages:pages};\n}return;}\n'}
LIFECYCLE_DRIVER='"""Compile unmodified production compiler_job.dg with explicit boundary mocks."""\nfrom concurrent.futures import ThreadPoolExecutor\nimport hashlib,json,os,shutil,subprocess,sys,uuid\nfrom pathlib import Path\nHERE=Path(__file__).resolve().parent;ROOT=Path(os.environ[\'DONGOS_TEST_ROOT\']);sys.path.insert(0,str(ROOT))\nif not __debug__:raise RuntimeError(\'lifecycle assertions must be enabled\')\nfrom lang.dongc import compile_file\nfrom lang.tests.test_dongc import tool,nasm_flags\nsource=ROOT/\'kernel/user/compiler_job.dg\'\ninputs=[source,ROOT/\'kernel/exec/elf.dg\',ROOT/\'kernel/user/abi.dg\',ROOT/\'kernel/user/compiler_stack.dg\',*sorted((HERE/\'fixtures\').glob(\'*\'))]\nbefore={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in inputs}\nWORK=HERE/(\'run-\'+uuid.uuid4().hex[:12]);WORK.mkdir()\nnasm=tool(\'nasm\',\'NASM\');cc=tool(\'gcc\',\'CC\');assert nasm and cc\ndef variant(mode,kind):\n d=WORK/(mode+\'-\'+kind)\n for directory in (\'user\',\'boot\',\'exec\'):(d/directory).mkdir(parents=True)\n text=source.read_text()\n if kind==\'skip-share-abort\':\n  old=\'if (*(memory.processes()+SLOT)).ready==1\';assert text.count(old)==1;text=text.replace(old,\'if false\')\n if kind==\'skip-destroy\':\n  old=\'try memory.destroy(SLOT);\';assert text.count(old)==1;text=text.replace(old,\'if false{try memory.destroy(SLOT);}\')\n (d/\'user/compiler_job.dg\').write_text(text+\'\\n\'+(HERE/\'fixtures/exports.dg\').read_text())\n for a,b in ((HERE/\'fixtures/memory.dg\',d/\'user/memory.dg\'),(HERE/\'fixtures/resources.dg\',d/\'boot/service_memory.dg\'),(ROOT/\'kernel/exec/elf.dg\',d/\'exec/elf.dg\'),(ROOT/\'kernel/user/abi.dg\',d/\'user/abi.dg\'),(ROOT/\'kernel/user/compiler_stack.dg\',d/\'user/compiler_stack.dg\')):shutil.copyfile(a,b)\n c=compile_file(d/\'user/compiler_job.dg\',roots=[d],mode=mode)\n asm=d/\'probe.asm\';asm.write_text(c.assembly);records=[]\n def command(cmd,label,expected=0,needle=None):\n  p=subprocess.run(list(map(str,cmd)),capture_output=True,timeout=180)\n  r={\'command\':list(map(str,cmd)),\'returncode\':p.returncode,\'expected\':expected,\'stdout\':p.stdout.decode(errors=\'replace\'),\'stderr\':p.stderr.decode(errors=\'replace\')}\n  records.append(r);(d/(label+\'.json\')).write_text(json.dumps(r,indent=2)+\'\\n\')\n  assert p.returncode==expected,r\n  if needle:assert needle in r[\'stderr\'],r\n for fmt in (\'win64\',\'elf64\'):command([nasm,\'-O0\',\'-f\',fmt,*nasm_flags(nasm),\'-o\',d/(fmt+\'.o\'),asm],\'assemble-\'+fmt)\n obj=d/(\'win64.o\'if os.name==\'nt\'else\'elf64.o\');exe=d/(\'probe.exe\'if os.name==\'nt\'else\'probe\')\n command([cc,\'-std=c11\',\'-O2\',\'-Wall\',\'-Wextra\',\'-Werror\',*([\'-no-pie\']if os.name!=\'nt\'else[]),HERE/\'fixtures/probe.c\',obj,\'-o\',exe],\'link\')\n needle={\'skip-share-abort\':\'stage abort did not withdraw failed candidate\',\'skip-destroy\':\'successful finish did not destroy job\'}.get(kind)\n command([exe],\'execute\',0 if kind==\'normal\'else 90,needle)\n r={\'mode\':mode,\'variant\':kind,\'records\':records,\'artifact_sha256\':{str(p.relative_to(d)):hashlib.sha256(p.read_bytes()).hexdigest()for p in d.rglob(\'*\')if p.is_file()}}\n (d/\'receipt.json\').write_text(json.dumps(r,indent=2)+\'\\n\');return r\ndef mode_work(mode):return [variant(mode,kind)for kind in (\'normal\',\'skip-share-abort\',\'skip-destroy\')]\nwith ThreadPoolExecutor(max_workers=2)as pool:rows=list(pool.map(mode_work,(\'debug\',\'release\')))\nassert before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in inputs}\nresult={\'source_sha256\':before,\'source_stable\':True,\'results\':rows,\'skip_count\':0,\'production_start_finish_executed\':True,\'memory_resources_mocked\':True,\'actual_elf_abi_sources\':True,\'guest_executed\':False}\n(WORK/\'receipt.json\').write_text(json.dumps(result,indent=2)+\'\\n\');(HERE/\'latest.json\').write_text(json.dumps({\'run\':str(WORK)},indent=2)+\'\\n\')\nprint(\'PASS independent full launch lifecycle\',WORK)\n'

class LifecycleTests(unittest.TestCase):
    def test_production_start_finish(self):
        work=ROOT/'build/test/compiler-launch'/('lifecycle-'+uuid.uuid4().hex[:12]);(work/'fixtures').mkdir(parents=True)
        for name,text in LIFECYCLE_FIXTURES.items():(work/'fixtures'/name).write_text(text,encoding='utf-8')
        (work/'run.py').write_text(LIFECYCLE_DRIVER,encoding='utf-8')
        env=dict(os.environ,DONGOS_TEST_ROOT=str(ROOT))
        r=subprocess.run([os.sys.executable,str(work/'run.py')],env=env,capture_output=True,timeout=600)
        (work/'stdout.log').write_bytes(r.stdout);(work/'stderr.log').write_bytes(r.stderr)
        self.assertEqual(r.returncode,0,r.stderr.decode(errors='replace'))
        receipt=json.loads((Path(json.loads((work/'latest.json').read_text())['run'])/'receipt.json').read_text())
        self.assertTrue(receipt['source_stable'] and receipt['production_start_finish_executed'])
        self.assertEqual(receipt['skip_count'],0)
        self.assertEqual(len(receipt['results']),2)
        for rows in receipt['results']:
            self.assertEqual(len(rows),3)
            self.assertIn('30 lifecycle cases',rows[0]['records'][-1]['stdout'])
if __name__=='__main__':unittest.main()
