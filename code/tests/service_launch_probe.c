#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef struct{uint64_t version,cfg,token,generation,state,status,sequence,argument;} Snapshot;
typedef struct{uint64_t ready,count,sequence;unsigned char configs[32][128];Snapshot states[32];
 uint64_t slots[32],incarnations[16],configurations[16];unsigned char events[64][64];} Catalog;
_Static_assert(sizeof(Catalog)==10776,"catalog ABI");
extern uint64_t ABI launch_fixture_init(void),launch_fixture_call(uint64_t,uint64_t,uint64_t,uint64_t,Snapshot*),launch_fixture_get(uint64_t,uint64_t),launch_fixture_prepare(uint64_t),launch_fixture_lookup(uint64_t,uint64_t);
extern const Catalog* ABI launch_fixture_catalog(void);
extern const Snapshot* ABI launch_fixture_internal(void);
extern uint64_t ABI compat_cn_smoke(void),compat_owner(uint64_t),compat_abort_count(uint64_t),compat_unsupported(void);
static Catalog before;static Snapshot output,internal_before;
static unsigned tracing,mode,checks,trace[32],count,slot=7,cfg=7,preloaded;
static uint64_t argument=42;
static void failure(unsigned line,const char* what){fprintf(stderr,"launch oracle failed line %u: %s\n",line,what);exit(1);}
#define OBS(x) do{++checks;if(!(x))failure(__LINE__,#x);}while(0)
#define CHECK(x) OBS(x)
void ABI __dong_panic(void){failure(__LINE__,"unexpected Dong panic");}
static int untouched(void){const unsigned char*p=(const unsigned char*)&output;for(unsigned i=0;i<sizeof(output);i++)if(p[i]!=0xa5)return 0;return 1;}
static void catalog_unchanged(void){OBS(!memcmp(&before,launch_fixture_catalog(),sizeof(before)));}
static void started(void){
 const Catalog*c=launch_fixture_catalog();const Snapshot*s=&c->states[cfg];
 OBS(c->slots[cfg]==slot&&c->configurations[slot]==cfg&&c->incarnations[slot]==before.incarnations[slot]+1);
 OBS(s->token==((c->incarnations[slot]<<8)|(slot+1)));
 OBS(s->generation==before.states[cfg].generation+1&&s->state==1&&s->status==0&&s->argument==argument);
}
uint64_t ABI launch_adapter_event(uint64_t op,uint64_t target,uint64_t id,uint64_t generation,uint64_t arg){
 if(!tracing)return 0;
 OBS(count<32);trace[count++]=(unsigned)op;OBS(untouched());
 if(op==4||op==5)started();else catalog_unchanged();
 if(op==1){OBS(target==slot&&launch_fixture_get(15,0)==slot);OBS(count>=2&&trace[count-2]==7);
  return mode==4?1:mode==5?2:0;}
 if(op==2){OBS(target==slot&&generation==before.incarnations[slot]+1&&arg==argument);
  OBS(count>=2&&trace[count-2]==1);OBS(launch_fixture_get(0,slot)==1);return mode==1?1:0;}
 if(op==3){OBS(target==slot&&id==cfg&&generation==before.incarnations[slot]+1&&arg==argument);
  OBS(count>=2&&trace[count-2]==2);OBS(launch_fixture_get(0,slot)==3&&launch_fixture_get(7,slot)==1);
  if(mode==3){return 2;}return mode==2||mode==6?1:0;}
 if(op==4){OBS(target==slot&&id==cfg&&generation==before.states[cfg].generation+1&&arg==argument);
  if(!preloaded)OBS(count>=2&&trace[count-2]==3);else OBS(count==1);return 0;}
 if(op==5){OBS(target==slot&&launch_fixture_get(15,0)==slot);OBS(count>=2&&trace[count-2]==4);return mode==7?1:0;}
 if(op==6){OBS(target==slot);OBS(launch_fixture_get(0,slot)==0&&launch_fixture_get(7,slot)==0);
  OBS(launch_fixture_get(1,slot)==9&&launch_fixture_get(2,slot)==0&&launch_fixture_get(3,slot)==0&&launch_fixture_get(4,slot)==0);
  return mode==6?1:0;}
 OBS(op==7&&count==1);return mode==8?1:0;
}
static void checkpoint(void){memcpy(&before,launch_fixture_catalog(),sizeof(before));internal_before=*launch_fixture_internal();memset(&output,0xa5,sizeof(output));count=0;tracing=1;}
static void setup(unsigned selected,unsigned prepare){
 tracing=0;mode=selected;slot=prepare==4?8:7;cfg=prepare==6?3:7;preloaded=prepare==6;
 if(preloaded)slot=3;CHECK(!launch_fixture_init());CHECK(!launch_fixture_prepare(prepare));checkpoint();
}
static void trace_is(const unsigned* expected,unsigned n){CHECK(count==n);CHECK(!memcmp(trace,expected,n*sizeof(*expected)));}
static void unchanged_failed_output(void){catalog_unchanged();CHECK(untouched());CHECK(!memcmp(&internal_before,launch_fixture_internal(),sizeof(internal_before)));}
static void normal(void){
 setup(0,0);CHECK(!launch_fixture_call(0,7,0,argument,&output));started();CHECK(output.token==264&&output.state==1&&output.argument==argument);
 const unsigned expected[]={7,1,2,3,4,5};trace_is(expected,6);
 CHECK(launch_fixture_get(0,7)==3&&launch_fixture_get(1,7)==0&&launch_fixture_get(2,7)==0&&launch_fixture_get(4,7)==0);
 CHECK(launch_fixture_get(15,0)==16&&!launch_fixture_get(5,0)&&launch_fixture_get(6,0)==0);
 setup(0,4);CHECK(!launch_fixture_call(0,7,0,argument,&output));CHECK((output.token&255)==9);trace_is(expected,6);
 setup(0,6);CHECK(!launch_fixture_call(5,3,1,argument,&output));CHECK(output.token==516&&output.generation==2);
 const unsigned preload[]={4};trace_is(preload,1);CHECK(!launch_fixture_get(9,3)&&!launch_fixture_get(1,3)&&!launch_fixture_get(2,3)&&!launch_fixture_get(4,3));
}
static void cleanup_and_retry(void){
 for(unsigned failed=1;failed<=2;failed++){
  setup(failed,0);uint64_t error=failed==1?0x051a0002:0x051a0003;
  for(unsigned retry=0;retry<2;retry++){
   CHECK(launch_fixture_call(0,7,0,argument,&output)==error);unchanged_failed_output();
   const unsigned channel[]={7,1,2,6},identity[]={7,1,2,3,6};trace_is(failed==1?channel:identity,failed==1?4:5);
   CHECK(launch_fixture_get(0,7)==0&&launch_fixture_get(15,0)==16&&launch_fixture_get(10,7)==0);
   CHECK(launch_fixture_get(1,7)==9&&!launch_fixture_get(5,0)&&!launch_fixture_get(16,0)&&launch_fixture_get(6,0)==0);
   uint64_t old=launch_fixture_get(failed==1?12:13,7);CHECK(launch_fixture_lookup(7,old)==0x04010002);checkpoint();
  }
  mode=0;CHECK(!launch_fixture_call(0,7,0,argument,&output));CHECK(output.token==264&&output.generation==1);
  CHECK(launch_fixture_get(failed==1?12:13,7)>>8==3);
 }
}
static void failures(void){
 setup(3,0);CHECK(launch_fixture_call(0,7,0,argument,&output)==0x04010002);unchanged_failed_output();
 CHECK(launch_fixture_get(5,0)&&launch_fixture_get(6,0)==16&&launch_fixture_get(15,0)==7&&launch_fixture_get(0,7)==3);
 const unsigned corrupt[]={7,1,2,3};trace_is(corrupt,4);
 setup(4,0);CHECK(launch_fixture_call(0,7,0,argument,&output)==0x051a0001);unchanged_failed_output();
 CHECK(!launch_fixture_get(5,0)&&!launch_fixture_get(16,0)&&launch_fixture_get(6,0)==0&&launch_fixture_get(15,0)==16);
 setup(5,0);CHECK(launch_fixture_call(0,7,0,argument,&output)==0x051a0001);unchanged_failed_output();
 CHECK(launch_fixture_get(16,0)&&launch_fixture_get(6,0)==16);
 setup(6,0);CHECK(launch_fixture_call(0,7,0,argument,&output)==0x051a0004);unchanged_failed_output();
 CHECK(launch_fixture_get(5,0)&&launch_fixture_get(16,0)&&launch_fixture_get(6,0)==16&&launch_fixture_get(0,7)==0&&launch_fixture_get(15,0)==7);
 setup(7,0);CHECK(launch_fixture_call(0,7,0,argument,&output)==0x051a0005);started();CHECK(untouched());
 CHECK(launch_fixture_get(5,0)&&launch_fixture_get(6,0)==16&&launch_fixture_get(0,7)==3&&launch_fixture_get(15,0)==7);
 setup(8,0);CHECK(launch_fixture_call(0,7,0,argument,&output)==0x051a0007);unchanged_failed_output();
 const unsigned resource[]={7};trace_is(resource,1);CHECK(launch_fixture_get(15,0)==16);
}
static void prechecks(void){
 for(unsigned prepare=1;prepare<=3;prepare++){
  setup(0,prepare);uint64_t expected=prepare==1?0x05110004:0x050b0002;
  CHECK(launch_fixture_call(0,7,prepare==2?UINT64_MAX:0,argument,&output)==expected);unchanged_failed_output();CHECK(count==0);
 }
 setup(0,5);CHECK(launch_fixture_call(0,7,0,argument,&output)==0x050b0002);unchanged_failed_output();CHECK(count==0);
 setup(0,0);CHECK(launch_fixture_call(6,7,0,argument,&output)==0x05110001);unchanged_failed_output();CHECK(count==0);
 setup(0,0);CHECK(launch_fixture_call(0,7,1,argument,&output)==0x05110003);unchanged_failed_output();CHECK(count==0);
}
static void compat_boundary_checks(void){
 setup(2,0);CHECK(launch_fixture_call(0,7,0,argument,&output)==0x051a0003);
 CHECK(!compat_owner(7)&&compat_abort_count(7)==1);
 setup(6,0);CHECK(launch_fixture_call(0,7,0,argument,&output)==0x051a0004);
 CHECK(compat_owner(7)==((UINT64_C(8)<<32)|1)&&!compat_abort_count(7));
}
int main(void){CHECK(!compat_cn_smoke());normal();cleanup_and_retry();failures();prechecks();compat_boundary_checks();CHECK(!compat_unsupported());printf("service launch checks passed %u; real catalog, caps and production transaction fragments\n",checks);return 0;}
