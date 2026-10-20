#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#define SYSV __attribute__((sysv_abi))
#define INVALID UINT64_C(0x05110001)
#define STALE UINT64_C(0x05110003)
#define EXHAUSTED UINT64_C(0x05110004)
#define DEPENDENCY UINT64_C(0x05110006)
#define NONE UINT64_MAX
typedef struct {uint64_t version,id,dependencies,restart_limit,timeout_ticks,flags,image,name_length;uint8_t name[32];uint64_t reserved[4];} Config;
typedef struct {uint64_t version,configuration,process,generation,state,status,sequence,argument;} Snapshot;
typedef struct {uint64_t version,sequence,configuration,generation,process,state,status,flags;} Event;
typedef struct {uint64_t ready;size_t count;uint64_t sequence;Config configs[32];Snapshot states[32];uint64_t slot[32],incarnation[16],configuration[16];Event events[64];} Catalog;
extern uint64_t SYSV catalog_initialize(Catalog*,uint64_t),catalog_allowed(const Catalog*,uint64_t,uint64_t,uint64_t),catalog_dependencies(const Catalog*,uint64_t);
extern uint64_t SYSV catalog_start(Catalog*,uint64_t,uint64_t,uint64_t,Snapshot*),catalog_ready(Catalog*,uint64_t,uint64_t),catalog_terminate(Catalog*,uint64_t,uint64_t,uint64_t);
extern uint64_t SYSV catalog_event(const Catalog*,uint64_t,uint64_t,Event*,uint64_t*),catalog_current(const Catalog*,uint64_t);
static unsigned checks;
void SYSV __dong_panic(void){fputs("unexpected process catalog Dong panic\n",stderr);exit(92);}
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"catalog oracle failed line %u\n",__LINE__);exit(1);}}while(0)
static const char*const names[18]={"shell","fs","block","compositor","input","init","devmgr","echo","fault","waiter","ipc-peer","fs-reader","file-app","xhci","terminal","files","editor","settings"};
/* Current desktop applications are AUTOSTART | ORDINARY, independently pinned. */
static const uint64_t deps[18]={2,4,64,18,64,0,32,2,2,2,2,2,2,64,10,10,10,10},flags[18]={7,7,5,7,5,5,7,8,8,8,8,8,8,4,9,9,9,9},retries[18]={3,3,0,3,0,0,3,0,0,0,0,0,0,0,0,0,0,0};
static Catalog model;
static void reference_initialize(uint64_t hz){
 memset(&model,0,sizeof model);model.ready=1;model.count=18;
 for(unsigned i=0;i<32;i++){model.configs[i].version=1;model.states[i].version=1;model.states[i].configuration=i;model.slot[i]=NONE;if(i<16)model.configuration[i]=NONE;}
 for(unsigned i=0;i<64;i++)model.events[i].version=1;
 for(unsigned i=0;i<18;i++){
  Config*p=&model.configs[i];p->id=i;p->dependencies=deps[i];p->restart_limit=retries[i];p->timeout_ticks=hz*10;p->flags=flags[i];p->image=i+1;p->name_length=strlen(names[i]);memcpy(p->name,names[i],p->name_length);
 }
}
static void equal(const Catalog*c){CHECK(!memcmp(c,&model,sizeof model));}
static void start(Catalog*c,unsigned id,unsigned slot,uint64_t arg){
 struct {uint64_t lo;Snapshot value;uint64_t hi;} out={0x182d,{0},0xabc3};
 CHECK(!catalog_start(c,id,slot,arg,&out.value));
 uint64_t generation=model.states[id].generation+1,incarnation=++model.incarnation[slot],token=incarnation*256+slot+1;
 model.states[id]=(Snapshot){1,id,token,generation,1,0,model.sequence,arg};model.slot[id]=slot;model.configuration[slot]=id;
 CHECK(!memcmp(&out.value,&model.states[id],sizeof out.value)&&out.lo==0x182d&&out.hi==0xabc3);equal(c);
}
static void publish(unsigned id,uint64_t state,uint64_t status){
 uint64_t seq=++model.sequence;Snapshot*s=&model.states[id];
 model.events[(seq-1)%64]=(Event){1,seq,id,s->generation,s->process,state,status,0};s->sequence=seq;s->state=state;s->status=status;
}
static void ready(Catalog*c,unsigned slot){unsigned id=(unsigned)model.configuration[slot];CHECK(!catalog_ready(c,slot,model.incarnation[slot]));publish(id,2,0);equal(c);}
static void terminate(Catalog*c,unsigned slot,unsigned state,uint64_t status){
 unsigned id=(unsigned)model.configuration[slot];CHECK(!catalog_terminate(c,slot,state,status));publish(id,state,status);model.states[id].process=0;model.slot[id]=NONE;model.configuration[slot]=NONE;equal(c);
}
static unsigned permitted(unsigned actor,unsigned config,unsigned write){
 unsigned ordinary=!!(flags[config]&8);
 if(actor==5||(actor==0&&(!write||ordinary))||(actor==6&&(!write||config==2||config==4||config==13))||(actor==3&&(!write||(config>=14&&config<=17))))return 1;
 return actor<16&&model.configuration[actor]==14&&model.slot[14]==actor&&model.incarnation[actor]&&
 (model.states[14].state==1||model.states[14].state==2)&&model.states[14].process==(model.incarnation[actor]*256+actor+1)&&(!write||ordinary);
}
static void event(Catalog*c,unsigned actor,uint64_t after){
 struct{uint64_t lo;Event item;uint64_t hi;} out,before;memset(&out,0xa5,sizeof out);before=out;uint64_t found=77;
 CHECK(!catalog_event(c,actor,after,&out.item,&found));
 uint64_t expected=0;
 for(uint64_t seq=after;seq<model.sequence;){++seq;Event*e=&model.events[(seq-1)%64];if(permitted(actor,(unsigned)e->configuration,1)){expected=seq;break;}}
 CHECK(found==!!expected);
 if(expected)CHECK(!memcmp(&out.item,&model.events[(expected-1)%64],sizeof(Event))&&out.lo==before.lo&&out.hi==before.hi);
 else {CHECK(!memcmp(&out,&before,sizeof out));}
 equal(c);
}
static void rejected_start(Catalog*c,unsigned id,unsigned slot,uint64_t code){
 Snapshot out,before;memset(&out,0xa5,sizeof out);before=out;Catalog prior=*c;
 CHECK(catalog_start(c,id,slot,999,&out)==code);CHECK(!memcmp(c,&prior,sizeof prior)&&!memcmp(&out,&before,sizeof out));
}
static void rejected_ready(Catalog*c,unsigned slot,uint64_t generation,uint64_t code){Catalog prior=*c;CHECK(catalog_ready(c,slot,generation)==code);CHECK(!memcmp(c,&prior,sizeof prior));}
int main(void){
 Catalog prior;struct {uint64_t lo;Catalog value;uint64_t hi;} guarded={0xabc231, {0},0x719dc8};
#define c guarded.value
 memset(&c,0,sizeof c);prior=c;
 CHECK(sizeof(Config)==128&&sizeof(Snapshot)==64&&sizeof(Event)==64&&sizeof(Catalog)==10776);
 CHECK(catalog_initialize(NULL,1)==INVALID&&catalog_initialize(&c,0)==INVALID&&!memcmp(&c,&prior,sizeof c));
 CHECK(catalog_initialize(&c,UINT64_MAX/10+1)==INVALID&&!memcmp(&c,&prior,sizeof c));
 CHECK(!catalog_initialize(&c,123456));reference_initialize(123456);equal(&c);prior=c;
 CHECK(catalog_initialize(&c,1)==INVALID&&!memcmp(&c,&prior,sizeof c));
 for(unsigned actor=0;actor<20;actor++)for(unsigned id=0;id<18;id++)for(unsigned write=0;write<2;write++)CHECK(catalog_allowed(&c,actor,id,write)==(permitted(actor,id,write)?0:INVALID));
 CHECK(catalog_allowed(&c,5,18,0)==INVALID&&catalog_allowed(NULL,5,0,0)==INVALID);
 for(unsigned id=0;id<18;id++)CHECK(catalog_dependencies(&c,id)==(id==5?0:DEPENDENCY));
 rejected_start(&c,7,7,DEPENDENCY);rejected_start(&c,18,7,INVALID);
 CHECK(catalog_current(&c,16)==NONE&&catalog_current(NULL,0)==NONE);
 start(&c,5,5,11);rejected_start(&c,5,8,STALE);rejected_ready(&c,5,0,STALE);rejected_ready(&c,5,2,STALE);ready(&c,5);
 prior=c;CHECK(!catalog_ready(&c,5,1)&&!memcmp(&c,&prior,sizeof c));
 start(&c,6,6,22);ready(&c,6);start(&c,2,2,33);start(&c,4,4,44);ready(&c,2);ready(&c,4);
 start(&c,1,1,55);ready(&c,1);start(&c,0,0,66);ready(&c,0);start(&c,3,3,77);ready(&c,3);
 /* Configuration ids 16 and 17 are not physical process slots. */
 start(&c,13,13,0);ready(&c,13);terminate(&c,13,5,0);
 start(&c,14,8,0);ready(&c,8);
 for(unsigned actor=0;actor<20;actor++)for(unsigned id=0;id<18;id++)for(unsigned write=0;write<2;write++)CHECK(catalog_allowed(&c,actor,id,write)==(permitted(actor,id,write)?0:INVALID));
 CHECK(catalog_allowed(&c,8,1,1)==INVALID&&catalog_allowed(&c,8,1,0)==0);
 CHECK(catalog_allowed(&c,3,13,1)==INVALID&&catalog_allowed(&c,3,2,1)==INVALID);
 CHECK(catalog_allowed(&c,14,16,1)==INVALID); /* vacant slot 14 is not terminal */
 start(&c,16,9,0x1616);ready(&c,9);terminate(&c,9,3,16);
 start(&c,17,9,0x1717);ready(&c,9);terminate(&c,9,3,17);
 for(unsigned actor=0;actor<16;actor++)event(&c,actor,c.sequence-4);
 terminate(&c,8,5,0);CHECK(catalog_allowed(&c,8,16,1)==INVALID);
 start(&c,12,8,0);ready(&c,8);CHECK(catalog_allowed(&c,8,16,1)==INVALID);terminate(&c,8,3,0);
 start(&c,14,14,0);ready(&c,14);CHECK(catalog_allowed(&c,14,16,1)==0);
 prior=c;c.incarnation[14]++;CHECK(catalog_allowed(&c,14,16,1)==INVALID);c=prior;
 c.states[14].state=3;CHECK(catalog_allowed(&c,14,16,1)==INVALID);c=prior;
 c.slot[14]=15;CHECK(catalog_allowed(&c,14,16,1)==INVALID);c=prior;
 terminate(&c,14,5,0);CHECK(catalog_allowed(&c,14,16,1)==INVALID);
 rejected_start(&c,16,16,STALE);rejected_start(&c,17,31,STALE);
 start(&c,7,7,UINT64_MAX);uint64_t echo_token=c.states[7].process;ready(&c,7);terminate(&c,7,3,123);
 CHECK(c.events[(c.sequence-1)%64].process==echo_token&&c.states[7].process==0);
 start(&c,8,7,34);CHECK(c.states[8].process!=echo_token&&c.states[8].generation==1);rejected_ready(&c,7,1,STALE);ready(&c,7);terminate(&c,7,4,0xd);
 start(&c,7,7,19);CHECK(c.states[7].generation==2&&c.states[7].process!=echo_token);terminate(&c,7,5,9999);
 prior=c;CHECK(catalog_terminate(&c,7,2,0)==INVALID&&!memcmp(&c,&prior,sizeof c));
 CHECK(catalog_terminate(&c,7,6,0)==INVALID&&!memcmp(&c,&prior,sizeof c));
 CHECK(catalog_terminate(&c,16,3,0)==INVALID&&!memcmp(&c,&prior,sizeof c));
 CHECK(catalog_terminate(&c,15,3,0)==STALE&&!memcmp(&c,&prior,sizeof c));
 for(unsigned actor=0;actor<10;actor++)for(uint64_t after=0;after<=c.sequence;after++)event(&c,actor,after);
 for(unsigned round=0;round<150;round++){start(&c,9,7,round);ready(&c,7);terminate(&c,7,3,round*2);}
 Event out,before;memset(&out,0xa5,sizeof out);before=out;uint64_t found=77;prior=c;
 CHECK(catalog_event(&c,5,c.sequence-65,&out,&found)==STALE&&!memcmp(&c,&prior,sizeof c)&&!memcmp(&out,&before,sizeof out)&&found==77);
 CHECK(catalog_event(&c,5,c.sequence+1,&out,&found)==INVALID&&!memcmp(&out,&before,sizeof out)&&found==77);
 CHECK(catalog_event(&c,5,c.sequence,NULL,&found)==INVALID&&found==77);
 for(unsigned actor=0;actor<10;actor++)for(uint64_t after=c.sequence-64;after<=c.sequence;after++)event(&c,actor,after);
 c.states[9].generation=UINT64_MAX;rejected_start(&c,9,7,STALE);c=model;
 c.incarnation[7]=0x0fffffff;rejected_start(&c,9,7,STALE);c=model;
 c.incarnation[7]=0x0ffffffe;model.incarnation[7]=0x0ffffffe;start(&c,9,7,1);CHECK(c.states[9].process==UINT64_C(0x0fffffff08));terminate(&c,7,3,0);rejected_start(&c,9,7,STALE);
 c=model;c.sequence=UINT64_MAX;prior=c;found=77;out=before;
 CHECK(catalog_start(&c,10,8,0,NULL)==EXHAUSTED&&!memcmp(&c,&prior,sizeof c));
 CHECK(!catalog_event(&c,5,UINT64_MAX,&out,&found)&&found==0&&!memcmp(&out,&before,sizeof out)&&!memcmp(&c,&prior,sizeof c));
 /* The final event is valid but hidden from shell. Skipping it must not wrap/panic. */
 c.events[62]=(Event){1,UINT64_MAX,5,1,0x106,2,0,0};prior=c;found=77;
 CHECK(!catalog_event(&c,0,UINT64_MAX-1,&out,&found)&&found==0&&!memcmp(&out,&before,sizeof out)&&!memcmp(&c,&prior,sizeof c));
 /* Exhaustion cannot mutate a STARTING process or publish a partial event. */
 c=model;model.incarnation[7]=0;model.slot[9]=NONE;model.states[9].process=0;c=model;start(&c,9,7,4);c.sequence=UINT64_MAX;prior=c;
 CHECK(catalog_ready(&c,7,c.incarnation[7])==EXHAUSTED&&!memcmp(&c,&prior,sizeof c));
 CHECK(catalog_terminate(&c,7,3,123)==EXHAUSTED&&!memcmp(&c,&prior,sizeof c));
 CHECK(guarded.lo==0xabc231&&guarded.hi==0x719dc8);
 printf("process catalog independent checks passed %u; golden 18-config DAG/config32-slot16, byte-exact state/event ring, slot reincarnation and scope\n",checks);return 0;
}
