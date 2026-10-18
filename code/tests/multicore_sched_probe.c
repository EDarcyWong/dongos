#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define SYSV __attribute__((sysv_abi))
#define NONE UINT64_C(64)
#define INVALID UINT64_C(0x06060001)
#define STATE UINT64_C(0x06060002)
#define BUSY UINT64_C(0x06060003)
#define OVERFLOW UINT64_C(0x06060004)
#define STALE UINT64_C(0x06060006)
#define MAXGEN UINT64_C(0x00ffffffffffffff)
typedef struct{uint64_t state,priority,affinity,cpu,next,previous,generation,frame;} Thread;
typedef struct{uint64_t current,ready_count,bitmap,cursor,dispatches,heads[32],tails[32];} Cpu;
typedef struct{uint64_t ready,online,sequence,count;Cpu cpus[16];Thread threads[64];} Engine;
typedef struct{uint64_t token,frame,source_cpu,target_cpu,priority;} Dispatch;
typedef struct{uint64_t token,source_cpu,target_cpu,notify;} Move;
extern uint64_t SYSV multi_init(Engine*,uint64_t),multi_audit(const Engine*),multi_admit(Engine*,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t*);
extern uint64_t SYSV multi_acquire(Engine*,uint64_t,Dispatch*,uint64_t*),multi_release(Engine*,uint64_t,uint64_t,uint64_t,uint64_t),multi_wake(Engine*,uint64_t);
extern uint64_t SYSV multi_affinity(Engine*,uint64_t,uint64_t),multi_priority(Engine*,uint64_t,uint64_t),multi_remove(Engine*,uint64_t),multi_balance(Engine*,uint64_t,uint64_t,Move*,uint64_t*);
static unsigned checks;static uint64_t random_state=UINT64_C(0xd73a1289eb6304af);
void SYSV __dong_panic(void){fputs("unexpected multicore Dong panic\n",stderr);exit(92);}
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"multicore oracle failed line %u\n",__LINE__);exit(1);}}while(0)
static uint64_t random64(void){random_state^=random_state<<13;random_state^=random_state>>7;random_state^=random_state<<17;return random_state;}
typedef struct{uint64_t state,priority,affinity,cpu,generation,frame,order;} ModelThread;
static struct{uint64_t online,sequence,count,order,current[16],cursor[16],dispatches[16];ModelThread t[64];} m;
static Engine actual,expected,saved;
static uint64_t handle(unsigned id){return m.t[id].generation*256+id+1;}
static unsigned enabled(unsigned cpu){return cpu<16&&(m.online&(UINT64_C(1)<<cpu));}
static uint64_t load(unsigned cpu){uint64_t n=m.current[cpu]!=NONE;for(unsigned id=0;id<64;id++)n+=m.t[id].state==1&&m.t[id].cpu==cpu;return n;}
static unsigned least(uint64_t mask){unsigned best=16;uint64_t amount=65;for(unsigned cpu=0;cpu<16;cpu++)if(mask&(UINT64_C(1)<<cpu)){uint64_t n=load(cpu);if(n<amount){best=cpu;amount=n;}}return best;}
static void queue(unsigned id,unsigned cpu){m.t[id].state=1;m.t[id].cpu=cpu;m.t[id].order=++m.order;}
static void compare(void){
 memset(&expected,0,sizeof expected);expected.ready=1;expected.online=m.online;expected.sequence=m.sequence;expected.count=m.count;
 for(unsigned cpu=0;cpu<16;cpu++){
  Cpu*q=&expected.cpus[cpu];q->current=m.current[cpu];q->cursor=m.cursor[cpu];q->dispatches=m.dispatches[cpu];
  for(unsigned p=0;p<32;p++)q->heads[p]=q->tails[p]=NONE;
 }
 unsigned ordered[64],count=0;
 for(unsigned id=0;id<64;id++){
  ModelThread*t=&m.t[id];expected.threads[id]=(Thread){t->state,t->priority,t->affinity,t->cpu,NONE,NONE,t->generation,t->frame};
  if(t->state==1){unsigned at=count++;while(at&&m.t[ordered[at-1]].order>t->order){ordered[at]=ordered[at-1];--at;}ordered[at]=id;}
 }
 for(unsigned index=0;index<count;index++){
  unsigned id=ordered[index];Thread*t=&expected.threads[id];Cpu*q=&expected.cpus[t->cpu];uint64_t tail=q->tails[t->priority];
  t->previous=tail;if(tail==NONE)q->heads[t->priority]=id;else expected.threads[tail].next=id;
  q->tails[t->priority]=id;++q->ready_count;q->bitmap|=UINT64_C(1)<<t->priority;
 }
 CHECK(!memcmp(&expected,&actual,sizeof actual));CHECK(!multi_audit(&actual));
}
static void initialize(uint64_t mask){
 memset(&actual,0,sizeof actual);memset(&m,0,sizeof m);m.online=mask;
 for(unsigned c=0;c<16;c++){m.current[c]=NONE;m.cursor[c]=(c+1)%16;}
 for(unsigned id=0;id<64;id++)m.t[id].cpu=16;
 CHECK(!multi_init(&actual,mask));compare();
}
static void admit(unsigned id,unsigned p,uint64_t mask,uint64_t frame){
 uint64_t before=0x12bcba,value=before;uint64_t status=multi_admit(&actual,id,p,mask,frame,&value);
 uint64_t code=(id>=64||p>=32||!frame||(frame&7)||!mask||(mask&~m.online))?INVALID:(m.t[id].state?STATE:0);
 CHECK(status==code);
 if(!code){unsigned cpu=least(mask);ModelThread*t=&m.t[id];uint64_t generation=t->generation+1;*t=(ModelThread){1,p,mask,cpu,generation,frame,0};queue(id,cpu);++m.count;++m.sequence;CHECK(value==handle(id));}
 else CHECK(value==before);compare();
}
static unsigned first(unsigned cpu,unsigned p,uint64_t affinity,unsigned newest){
 unsigned best=64;uint64_t order=newest?0:UINT64_MAX;
 for(unsigned id=0;id<64;id++)if(m.t[id].state==1&&m.t[id].cpu==cpu&&m.t[id].priority==p&&(!affinity||(m.t[id].affinity&affinity))){
  if((newest&&m.t[id].order>order)||(!newest&&m.t[id].order<order)){best=id;order=m.t[id].order;}
 }return best;
}
static void acquire(unsigned cpu){
 Dispatch out,before;memset(&out,0xa5,sizeof out);before=out;uint64_t found=77;
 uint64_t result=multi_acquire(&actual,cpu,&out,&found);unsigned selected=64,source=cpu;
 uint64_t code=!enabled(cpu)?INVALID:(m.current[cpu]!=NONE?BUSY:0);CHECK(result==code);
 if(code){CHECK(found==77&&!memcmp(&out,&before,sizeof out));compare();return;}
 for(unsigned p=0;p<32&&selected==64;p++)selected=first(cpu,p,0,0);
 if(selected==64)for(unsigned p=0;p<32&&selected==64;p++)for(unsigned offset=0;offset<16&&selected==64;offset++){
  unsigned donor=(unsigned)(m.cursor[cpu]+offset)%16;if(donor==cpu||!enabled(donor))continue;
  selected=first(donor,p,UINT64_C(1)<<cpu,0);if(selected!=64)source=donor;
 }
 CHECK(found==(selected!=64));
 if(selected==64){CHECK(!memcmp(&out,&before,sizeof out));compare();return;}
 ModelThread*t=&m.t[selected];Dispatch want={handle(selected),t->frame,source,cpu,t->priority};CHECK(!memcmp(&out,&want,sizeof out));
 t->state=2;t->cpu=cpu;m.current[cpu]=selected;++m.dispatches[cpu];m.cursor[cpu]=(source+1)%16;++m.sequence;compare();
}
static void release(unsigned cpu,unsigned id,unsigned state,uint64_t frame){
 uint64_t value=handle(id),status=multi_release(&actual,cpu,value,state,frame),code=0;
 if((state!=1&&state!=3)||!frame||(frame&7)||!enabled(cpu))code=INVALID;
 else if(!m.t[id].state)code=STALE;
 else if(m.t[id].state!=2||m.t[id].cpu!=cpu||m.current[cpu]!=id)code=STATE;
 CHECK(status==code);
 if(!code){m.current[cpu]=NONE;m.t[id].state=state;m.t[id].frame=frame;if(state==1)queue(id,cpu);++m.sequence;}compare();
}
static void wake(unsigned id){uint64_t status=multi_wake(&actual,handle(id)),code=!m.t[id].state?STALE:(m.t[id].state!=3?STATE:0);CHECK(status==code);if(!code){queue(id,least(m.t[id].affinity));++m.sequence;}compare();}
static void affinity(unsigned id,uint64_t mask){
 uint64_t status=multi_affinity(&actual,handle(id),mask),code=0;ModelThread*t=&m.t[id];
 if(!mask||(mask&~m.online))code=INVALID;else if(!t->state)code=STALE;
 else if(t->affinity!=mask&&t->state==2&&!(mask&(UINT64_C(1)<<t->cpu)))code=BUSY;
 CHECK(status==code);
 if(!code&&t->affinity!=mask){if(!(mask&(UINT64_C(1)<<t->cpu))){unsigned cpu=least(mask);if(t->state==1)queue(id,cpu);else t->cpu=cpu;}t->affinity=mask;++m.sequence;}compare();
}
static void priority(unsigned id,unsigned p){uint64_t status=multi_priority(&actual,handle(id),p),code=p>=32?INVALID:(!m.t[id].state?STALE:0);CHECK(status==code);if(!code&&m.t[id].priority!=p){m.t[id].priority=p;if(m.t[id].state==1)queue(id,(unsigned)m.t[id].cpu);++m.sequence;}compare();}
static void remove_thread(unsigned id){uint64_t status=multi_remove(&actual,handle(id)),code=!m.t[id].state?STALE:(m.t[id].state==2?BUSY:0);CHECK(status==code);if(!code){uint64_t generation=m.t[id].generation;memset(&m.t[id],0,sizeof m.t[id]);m.t[id].generation=generation;m.t[id].cpu=16;--m.count;++m.sequence;}compare();}
static void balance(unsigned source,unsigned target){
 Move out,before;memset(&out,0xa5,sizeof out);before=out;uint64_t found=77;
 uint64_t status=multi_balance(&actual,source,target,&out,&found),code=source==target||!enabled(source)||!enabled(target)?INVALID:0;CHECK(status==code);
 if(code){CHECK(found==77&&!memcmp(&out,&before,sizeof out));compare();return;}
 unsigned selected=64;
 if(load(source)>load(target)+1)for(unsigned p=32;p&&selected==64;){--p;selected=first(source,p,UINT64_C(1)<<target,1);}
 CHECK(found==(selected!=64));
 if(selected==64){CHECK(!memcmp(&out,&before,sizeof out));compare();return;}
 uint64_t current=m.current[target],notify=current==NONE||m.t[selected].priority<m.t[current].priority;
 Move want={handle(selected),source,target,notify};CHECK(!memcmp(&out,&want,sizeof out));queue(selected,target);++m.sequence;compare();
}
static void failed_acquire_unchanged(void){Dispatch out,before;memset(&out,0xa5,sizeof out);before=out;uint64_t found=77;saved=actual;CHECK(multi_acquire(&actual,1,&out,&found)!=0);CHECK(found==77&&!memcmp(&out,&before,sizeof out)&&!memcmp(&saved,&actual,sizeof actual));}
int main(void){
 CHECK(sizeof(Thread)==64&&sizeof(Cpu)==552&&sizeof(Engine)==12960&&sizeof(Dispatch)==40&&sizeof(Move)==32);
 memset(&actual,0,sizeof actual);saved=actual;CHECK(multi_init(NULL,1)==INVALID&&multi_init(&actual,0)==INVALID&&multi_init(&actual,0x10000)==INVALID&&!memcmp(&saved,&actual,sizeof actual));
 initialize(3);saved=actual;CHECK(multi_init(&actual,3)==STATE&&!memcmp(&saved,&actual,sizeof actual));
 admit(0,0,1,8);admit(1,1,1,16);affinity(1,3);acquire(1);CHECK(m.current[1]==1); /* skip pinned higher-priority donor */
 initialize(3);
 admit(0,31,1,8);admit(1,0,1,16);affinity(1,3);acquire(1);CHECK(m.t[1].state==2&&m.t[1].cpu==1);affinity(1,1);release(1,1,3,24);affinity(1,1);wake(1);balance(0,1);remove_thread(0);remove_thread(1);
 uint64_t stale=handle(1);admit(1,4,3,32);CHECK(handle(1)!=stale);saved=actual;CHECK(multi_wake(&actual,stale)==STALE&&!memcmp(&saved,&actual,sizeof actual));
 initialize(1);for(unsigned id=0;id<3;id++)admit(id,5,1,(id+1)*8);
 acquire(0);CHECK(m.current[0]==0);release(0,0,1,80);acquire(0);CHECK(m.current[0]==1);release(0,1,3,88);acquire(0);CHECK(m.current[0]==2);release(0,2,1,96);priority(0,0);acquire(0);CHECK(m.current[0]==0);
 initialize(0x8001);for(unsigned id=0;id<64;id++)admit(id,id%32,0x8001,(id+1)*8);acquire(15);release(15,(unsigned)m.current[15],1,800);balance(0,15);balance(15,0);
 initialize(0xffff);for(unsigned id=0;id<64;id++)admit(id,id%32,0xffff,(id+1)*8);
 for(unsigned cpu=0;cpu<16;cpu++)acquire(cpu);
 for(unsigned cpu=0;cpu<16;cpu++)release(cpu,(unsigned)m.current[cpu],cpu%2?1:3,0x8000+cpu*8);
 for(unsigned cpu=0;cpu<16;cpu++)acquire(cpu);
 initialize(15);
 for(unsigned step=0;step<30000;step++){
  unsigned id=(unsigned)(random64()%64),cpu=(unsigned)(random64()%5),p=(unsigned)(random64()%34),op=(unsigned)(random64()%9);
  uint64_t mask=random64()%16,frame=((random64()%0x100000)+1)*8;
  switch(op){
   case 0:admit(id,p,mask,frame);break;case 1:acquire(cpu);break;
   case 2:if(cpu<4&&m.current[cpu]!=NONE)id=(unsigned)m.current[cpu];release(cpu,id,random64()%2?1:3,frame);break;
   case 3:wake(id);break;case 4:affinity(id,mask);break;case 5:priority(id,p);break;case 6:remove_thread(id);break;
   default:balance(cpu,(unsigned)(random64()%5));break;
  }
 }
 /* Every malformed structure fails before dequeue and preserves all bytes. */
 initialize(3);admit(0,4,1,8);admit(1,4,1,16);affinity(0,3);Engine good=actual;
 for(unsigned corrupt=0;corrupt<12;corrupt++){
  actual=good;
  switch(corrupt){
   case 0:actual.cpus[0].heads[4]=65;break;case 1:actual.threads[0].next=0;break;
   case 2:actual.threads[1].previous=NONE;break;case 3:actual.cpus[0].ready_count=3;break;
   case 4:actual.cpus[0].bitmap=0;break;case 5:actual.threads[0].affinity=2;break;
   case 6:actual.threads[0].priority=32;break;case 7:actual.threads[0].frame=9;break;
   case 8:actual.threads[0].generation=MAXGEN+1;break;case 9:actual.online=0;break;
   case 10:actual.count=0;break;default:actual.cpus[1].current=0;break;
  }failed_acquire_unchanged();
 }
 actual=good;actual.sequence=UINT64_MAX;saved=actual;uint64_t result=0x123;
 CHECK(multi_admit(&actual,2,4,3,24,&result)==OVERFLOW&&result==0x123&&!memcmp(&saved,&actual,sizeof actual));
 actual=good;actual.cpus[1].dispatches=UINT64_MAX;failed_acquire_unchanged();
 initialize(1);actual.threads[0].generation=MAXGEN;saved=actual;CHECK(multi_admit(&actual,0,0,1,8,&result)==OVERFLOW&&!memcmp(&saved,&actual,sizeof actual));
 printf("multicore runqueue independent checks passed %u; 30000 transitions, sixteen CPUs, affinity/FIFO/steal/generations; hardware not executed\n",checks);return 0;
}
