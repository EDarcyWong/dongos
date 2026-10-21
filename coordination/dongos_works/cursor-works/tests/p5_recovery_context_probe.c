#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(_WIN32)
#define ABI __attribute__((sysv_abi))
#else
#define ABI
#endif
typedef uint64_t U;
typedef struct {U version,token,next_cursor,kind,ecam,segment,bus,device,function,vendor,device_id,class_code,header,flags,generation,reserved;} Device;
typedef struct {U physical,virtual,pages,root,generation,attempted,mapped,state;} Lease;
typedef struct {
 U present,slot,configuration,owner,incarnation,device_token,device_generation;
 Device identity;
 U root,memory_generation,request_bytes,request_alignment,snapshot_status,snapshot_error;
 Lease lease;
 U acquire_done,acquire_error,context_error,stop_state,stop_error,smp_retire,route_state,route_error;
 U isolation,isolation_error,reset,reset_error,generation_after,revoke_error,held,drain;
} Context;
_Static_assert(sizeof(Context)==424,"independent context ABI");
_Static_assert(sizeof(Lease)==64,"independent lease ABI");
extern ABI void p5_reset(U),p5_host_reset(U),p5_set(U,U),p5_host_change(U,U),p5_lease(const Lease*,U);
extern ABI U p5_query(U,Context*),p5_call(U,U),p5_retire(void),p5_revoke(U),p5_manager_revoke(void);
extern ABI U p5_begin(U,U,U,U,U,U);
extern ABI void p5_finish(U,U,U,U,U),p5_stop(U,U,U,U,U,U,U,U);
#define FAIL UINT64_C(0x052b0001)
#define BUSY UINT64_C(0x05120003)
#define DENIED UINT64_C(0x05120002)
#define STALE UINT64_C(0x05120004)
#define ABSENT UINT64_C(0x05120006)
#define NOLEASE UINT64_C(0x04060001)
static U checks,scenario,slot,owner,failed_stage,acquire_error,copy_error,snapshot_error,reset_result;
static U count[32],trace[256],trace_count,reentry,inside;
static Lease receipt;
#define CK(x) do{checks++;if(!(x)){fprintf(stderr,"P5 context check failed scenario %u line %d: %s\n",(unsigned)scenario,__LINE__,#x);exit(1);}}while(0)
static Context get(void){Context c;memset(&c,0,sizeof c);CK(p5_query(slot,&c)==0);return c;}
static void absent(void){Context c,poison;memset(&c,0xa5,sizeof c);poison=c;CK(p5_query(slot,&c)==ABSENT&&!memcmp(&c,&poison,sizeof c));}
ABI U p5_event(U stage,U a,U b,U c){
 CK(stage<32);count[stage]++;
 if(stage!=10&&trace_count<256)trace[trace_count++]=stage;
 if(stage==10){
  if(a==0x80008000)return 0x10421af4;
  if(a==0x80008008)return 0x01000000;
  if(a==0x8000800c)return 0;
  return 0xffffffff;
 }
 if(stage==2){
  CK(a==slot&&b>0&&c>0);
  Context current;U status=p5_query(slot,&current);
  if(status==0){CK(current.present==1&&current.acquire_done==0&&current.snapshot_status==0);CK(current.owner==owner&&current.root==0x9000&&current.memory_generation==11);}
  if(reentry&&!inside){inside=1;CK(p5_call(131072,4096)==BUSY);inside=0;}
  p5_lease(&receipt,snapshot_error);
  return acquire_error;
 }
 if(stage==4){Context current;if(p5_query(slot,&current)==0)CK(current.acquire_done==1&&current.snapshot_status!=0);return copy_error;}
 if(stage==7)return failed_stage==7?FAIL:reset_result;
 if(stage==5||stage==11)CK(a==owner||a!=0);
 if(stage==6)CK(a==slot);
 if(stage==8)CK(a==0x702&&b==7);
 return stage==failed_stage?FAIL:0;
}
ABI void __dong_panic(void){fprintf(stderr,"unexpected native panic\n");exit(2);}
static void reset(U active){
 scenario++;slot=active;owner=((slot+1)<<32)|5;failed_stage=UINT64_MAX;acquire_error=copy_error=snapshot_error=0;
 reset_result=1;reentry=inside=0;memset(count,0,sizeof count);trace_count=0;
 receipt=(Lease){0x200000,0x68000000,32,0x9000,11,32,32,2};
 p5_reset(slot);p5_host_reset(slot);absent();
}
static void identity(const Context *c){
 CK(c->present==1&&c->slot==slot&&c->configuration==slot&&c->owner==owner&&c->incarnation==5);
 CK(c->device_token==0x702&&c->device_generation==7&&c->memory_generation==11&&c->root==0x9000);
 Device d={1,0x702,0,1,0x80008000,0,0,1,0,0x1af4,0x1042,0x10000,0,2,7,0};
 CK(!memcmp(&c->identity,&d,sizeof d));
 CK(c->request_bytes==131072&&c->request_alignment==4096&&c->held==1&&c->drain==0);
}
static void snapshot(const Context *c){
 identity(c);CK(c->snapshot_status==2);CK(c->snapshot_error==0&&c->acquire_done==1&&c->acquire_error==acquire_error);
 CK(!memcmp(&c->lease,&receipt,sizeof receipt)&&c->context_error==0);
 CK(count[2]==1&&count[3]==2);
}
static void check_trace(const U *want,size_t n){
 CK(trace_count==n);for(size_t i=0;i<n;i++)CK(trace[i]==want[i]);
}
static void lease_cases(void){
 /* The first failing allocation is the actual services err branch mutant target. */
 reset(2);acquire_error=FAIL;receipt.attempted=3;receipt.mapped=2;receipt.state=1;
 CK(p5_call(131072,4096)==FAIL);Context c=get();snapshot(&c);CK(!count[4]);
 const U err_trace[]={0,1,3,2,3};check_trace(err_trace,sizeof err_trace/sizeof *err_trace);
 for(U physical=0;physical<2;physical++){
  reset(2);acquire_error=FAIL;receipt.physical=physical?0x200000:0;receipt.attempted=physical?1:0;receipt.mapped=0;receipt.state=1;
  CK(p5_call(131072,4096)==FAIL);c=get();snapshot(&c);CK(c.lease.pages==32&&c.lease.state==1);
 }
 reset(2);CK(p5_call(131072,4096)==0);c=get();snapshot(&c);CK(count[4]==1);
 Context before=c;U calls=count[2];
 CK(p5_call(131072,4096)==BUSY);c=get();CK(count[2]==calls&&!memcmp(&c,&before,sizeof c));
 p5_set(30,6);p5_set(2,0xa000);p5_set(3,12);p5_host_change(24,((slot+1)<<32)|6);
 CK(p5_call(131072,4096)==BUSY);c=get();CK(count[2]==calls&&!memcmp(&c,&before,sizeof c));
 reset(2);copy_error=FAIL;CK(p5_call(131072,4096)==FAIL);c=get();snapshot(&c);CK(c.lease.state==2);
 const U copy_trace[]={0,1,3,2,3,4};check_trace(copy_trace,sizeof copy_trace/sizeof *copy_trace);
 reset(2);snapshot_error=NOLEASE;acquire_error=FAIL;CK(p5_call(131072,4096)==FAIL);c=get();identity(&c);
 CK(c.snapshot_status==1&&c.snapshot_error==NOLEASE&&c.acquire_error==FAIL&&c.acquire_done==1);
 Lease empty={0};CK(!memcmp(&c.lease,&empty,sizeof empty));
 reset(2);reentry=1;CK(p5_call(131072,4096)==0);c=get();snapshot(&c);CK(count[2]==1);
 for(U stage=0;stage<=1;stage++){reset(2);failed_stage=stage;CK(p5_call(131072,4096)==FAIL);absent();CK(!count[2]);}
 reset(2);snapshot_error=NOLEASE;acquire_error=DENIED;CK(p5_call(1,1)==DENIED);c=get();CK(c.request_bytes==1&&c.request_alignment==1&&c.snapshot_status==1);
 CK(p5_call(131072,4096)==BUSY&&count[2]==1);
 /* Explicitly stale source-memory snapshots never masquerade as valid identity. */
 for(U field=0;field<4;field++){
  reset(2);if(field==0)receipt.root=0xa000;if(field==1)receipt.generation=12;if(field==2)receipt.pages=0;if(field==3)receipt.state=9;
  CK(p5_call(131072,4096)==0);c=get();CK(c.snapshot_status==2&&c.context_error==STALE&&c.held==1&&c.drain==0);
 }
 reset(2);p5_lease(&receipt,0);CK(p5_call(131072,4096)==BUSY);absent();CK(!count[2]);
}
static void mismatch_cases(void){
 /* Each trusted Catalog/Process and independent generation input changes alone. */
 for(U field=0;field<5;field++){
  reset(2);p5_set(field,field==0?6:field==1?4:0);
  CK(p5_call(131072,4096)!=0);absent();CK(!count[2]);
 }
 for(U field=31;field<=36;field++){
  reset(2);p5_set(field,field==32?1:0);CK(p5_call(131072,4096)!=0);absent();CK(!count[2]);
 }
 for(U field=0;field<6;field++){
  reset(2);U x[6]={2,2,owner,5,0x9000,11};x[field]=field==0?4:field==1?4:field==2?owner+1:field==3?6:field==4?0xa000:12;
  CK(p5_begin(x[0],x[1],x[2],x[3],x[4],x[5])!=0);absent();CK(!count[2]);
 }
 const U fields[]={0,1,3,4,5,6,7,8,9,10,11,12,13,14,17,18,19,20,22,24,25,27};
 const U changes[]={2,0x802,2,0x80010000,1,1,2,1,0x1234,0x9999,0x20000,128,4,8,0x802,2,4,8,4,UINT64_C(0x300000006),0x802,1};
 for(size_t i=0;i<sizeof fields/sizeof *fields;i++){
  reset(2);p5_host_change(fields[i],changes[i]);CK(p5_call(131072,4096)!=0);absent();CK(!count[2]);
 }
 /* Unbound/new-controller and absent Catalog paths preserve existing behavior. */
 reset(2);p5_host_change(24,0);CK(p5_call(131072,4096)==0);absent();CK(count[2]==1&&count[3]==0);
 reset(2);p5_host_change(26,0);CK(p5_call(131072,4096)==0);absent();CK(count[2]==1);
 reset(2);p5_set(5,0);CK(p5_call(131072,4096)==0);absent();CK(count[2]==1);
 reset(2);CK(p5_call(131072,4096)==0);Context before=get();
 /* finish and retirement cannot adopt any different original identity. */
 for(U which=0;which<3;which++){
  p5_finish(2,owner+(which==0),0x9000+(which==1?4096:0),11+(which==2),FAIL);
  Context c=get();CK(!memcmp(&before,&c,sizeof c));
 }
 for(U which=0;which<6;which++){
  U x[6]={2,2,owner,5,0x9000,11};x[which]+=1;p5_stop(x[0],x[1],x[2],x[3],x[4],x[5],1,0);
  Context c=get();CK(c.owner==before.owner&&c.root==before.root&&c.memory_generation==before.memory_generation&&c.stop_state==0&&c.held==1&&c.drain==0);
 }
}
static void retirement_cases(void){
 for(U active=2;active<=13;active+=(active==2?2:9)){
  reset(active);CK(p5_call(131072,4096)==0);CK(p5_retire()==0);Context c=get();snapshot(&c);
  CK(c.stop_state==1&&c.smp_retire==1&&c.route_state==1&&c.isolation==1&&c.generation_after==8&&c.revoke_error==0);
  CK(c.reset==(active==2?2:0)&&c.reset_error==0&&c.drain==0&&c.held==1);
  CK(count[12]==1&&count[13]==1&&count[5]==1&&count[6]==1&&count[8]==1&&count[11]==1);
  CK(count[7]==(active==2?1:0));
 }
 for(U stage=5;stage<=13;stage++){
  if(stage==9||stage==10||stage==11)continue;
  reset(2);CK(p5_call(131072,4096)==0);failed_stage=stage;CK(p5_retire()==FAIL);Context c=get();snapshot(&c);
  CK(c.held==1&&c.drain==0&&c.generation_after==0);
  if(stage==12){CK(c.smp_retire==2&&c.stop_state==0&&c.stop_error==FAIL&&!count[13]&&!count[5]);}
  if(stage==13){CK(c.stop_state==1&&c.smp_retire==1&&c.stop_error==FAIL&&!count[5]);}
  if(stage==5){CK(c.route_state==2&&c.route_error==FAIL&&!count[6]);}
  if(stage==6){CK(c.isolation==2&&c.isolation_error==FAIL&&!count[7]);}
  if(stage==7){CK(c.reset==3&&c.reset_error==FAIL&&!count[8]);}
  if(stage==8){CK(c.reset==2&&c.revoke_error==FAIL);}
 }
 reset(2);reset_result=0;CK(p5_call(131072,4096)==0&&p5_retire()==0);Context c=get();CK(c.reset==1&&c.drain==0&&c.held==1);
 reset(2);p5_set(6,0);CK(p5_call(131072,4096)==0&&p5_retire()==0);c=get();CK(c.smp_retire==0&&c.stop_state==1&&!count[12]);
 reset(2);CK(p5_call(131072,4096)==0);p5_set(2,0xa000);CK(p5_retire()==0);c=get();CK(c.context_error==STALE&&count[6]==1&&c.root==0x9000&&c.held==1);
 reset(2);CK(p5_call(131072,4096)==0);CK(p5_revoke(owner+1)==0);c=get();CK(c.route_state==0&&c.isolation==0&&c.generation_after==0);
 reset(2);CK(p5_call(131072,4096)==0);p5_host_change(14,9);CK(p5_revoke(owner)==0);c=get();
 CK(count[6]==1&&c.context_error==STALE&&c.device_generation==7&&c.generation_after==0&&c.held==1&&c.drain==0);
 reset(2);CK(p5_call(131072,4096)==0);CK(p5_manager_revoke()==2);c=get();
 CK(c.stop_state==0&&c.smp_retire==0&&c.reset==0&&c.isolation==1&&c.generation_after==8&&c.drain==0&&c.held==1);
 failed_stage=6;CK(p5_retire()==FAIL);c=get();CK(c.isolation==2&&c.isolation_error==FAIL&&c.generation_after==8&&c.drain==0);
}
int main(void){
 lease_cases();mismatch_cases();retirement_cases();
 printf("P5 context native checks passed %u scenarios %u; real 0x63, retire_one, revoke_owner and manager revoke; drain UNKNOWN\n",(unsigned)checks,(unsigned)scenario);
 return 0;
}
