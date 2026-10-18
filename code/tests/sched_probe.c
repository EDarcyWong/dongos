#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define SYSV __attribute__((sysv_abi))
typedef struct { uint64_t state,priority,ticks,switches,frame,next; } Thread;
typedef struct { uint64_t current,ticks,switches,quantum,remaining,depth,pending,count; Thread t[8]; } Engine;
typedef struct { uint64_t head,tail,generation; } Wait;
extern uint64_t SYSV sp_engine_size(void),sp_thread_size(void),sp_wait_size(void);
extern uint64_t SYSV sp_init(Engine*,uint64_t),sp_add(Engine*,uint64_t,uint64_t,uint64_t),sp_tick(Engine*,uint64_t);
extern uint64_t SYSV sp_wait(Engine*,Wait*,uint64_t),sp_wake(Engine*,Wait*),sp_disable(Engine*),sp_enable(Engine*);
extern uint64_t SYSV dong_sched_init(Engine*,uint64_t,uint64_t),dong_sched_tick(Engine*,uint64_t);
extern uint64_t SYSV sched_probe_xstate(uint64_t);
static unsigned checks;
#define CHECK(x) do { ++checks; if(!(x)) { fprintf(stderr,"sched check failed line %u\n",__LINE__); return 1; } } while(0)
void SYSV __dong_panic(uint64_t code,const char*message,uint64_t length) { (void)message;(void)length;fprintf(stderr,"unexpected Dong panic %x\n",(unsigned)code);exit(9); }
uint64_t SYSV platform_timer_rearm(void) { return 0; }
void SYSV apic_eoi(void) {}
/* Host link-only placeholders. None of the privileged IRQ path is executed. */
char __kernel_text_start[1],__kernel_text_end[1];
static uint64_t rng=0x91d786cd493b0285ULL;
static uint64_t random64(void) { rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng; }
/* Independent queue-free reference: a cyclic priority search plus accounting. */
static uint64_t reference_tick(Engine*e,uint64_t frame) {
  uint64_t current=e->current, pick=current, best=32, n;
  for(n=1;n<=8;n++) { uint64_t j=(current+n)&7;
    if((e->t[j].state==1||e->t[j].state==2)&&e->t[j].priority<best) { pick=j;best=e->t[j].priority; }
  }
  e->t[current].frame=frame;e->ticks++;e->t[current].ticks++;
  if(e->remaining)e->remaining--;
  if(e->depth) { e->pending=1;if(!e->remaining)e->remaining=1;return current; }
  if(e->t[current].state==2&&e->remaining&&best>=e->t[current].priority&&!e->pending)return current;
  if(e->t[current].state==2)e->t[current].state=1;
  e->current=pick;e->t[pick].state=2;e->remaining=e->quantum;e->pending=0;
  if(pick!=current){e->switches++;e->t[pick].switches++;}
  return pick;
}
static int policy(void) {
  Engine e,ref,before;Wait q,qbefore;
  CHECK(sp_engine_size()==sizeof e&&sp_thread_size()==sizeof(Thread)&&sp_wait_size()==sizeof q);
  memset(&e,0x6b,sizeof e);before=e;CHECK(sp_init(&e,0)==0x03040001&&!memcmp(&e,&before,sizeof e));
  CHECK(sp_init(&e,2)==0);CHECK(e.current==8&&e.count==0);
  CHECK(sp_add(&e,0,2,0x1000)==0);CHECK(sp_add(&e,1,2,0x2000)==0);CHECK(sp_add(&e,2,2,0x3000)==0);
  before=e;CHECK(sp_add(&e,1,2,0x4000)==0x03040002&&!memcmp(&e,&before,sizeof e));
  CHECK(sp_add(&e,8,1,0x4000)==0x03040001&&!memcmp(&e,&before,sizeof e));
  CHECK(sp_add(&e,3,32,0x4000)==0x03040001&&!memcmp(&e,&before,sizeof e));
  CHECK(sp_add(&e,3,1,0x4001)==0x03040001&&!memcmp(&e,&before,sizeof e));
  ref=e;
  for(unsigned i=0;i<4096;i++) {
    if(i%37==0) { CHECK(sp_disable(&e)==0);ref.depth++; }
    if(i%37==11&&e.depth) {CHECK(sp_enable(&e)==0);ref.depth--;}
    if(i%23==0) {unsigned j=(unsigned)(random64()%3); e.t[j].priority=ref.t[j].priority=random64()%4;}
    uint64_t frame=0x10000+(uint64_t)i*256,expected=reference_tick(&ref,frame);
    CHECK(sp_tick(&e,frame)==expected);CHECK(!memcmp(&e,&ref,sizeof e));
  }
  while(e.depth)CHECK(sp_enable(&e)==0);
  before=e;CHECK(sp_enable(&e)==0x03040002&&!memcmp(&e,&before,sizeof e));
  before=e;CHECK(sp_tick(&e,3)==0x03040001&&!memcmp(&e,&before,sizeof e));
  e.ticks=UINT64_MAX;before=e;CHECK(sp_tick(&e,0x1000)==0x03040004&&!memcmp(&e,&before,sizeof e));
  CHECK(sp_init(&e,1)==0);CHECK(sp_add(&e,0,0,0x1000)==0);CHECK(sp_add(&e,1,2,0x2000)==0);CHECK(sp_add(&e,2,2,0x3000)==0);
  q=(Wait){8,8,0};CHECK(sp_wait(&e,&q,0)==0);CHECK(e.t[0].state==3&&q.head==0&&q.tail==0);
  CHECK(sp_tick(&e,0x5000)==1);CHECK(sp_wait(&e,&q,0)==0);CHECK(q.head==0&&q.tail==1&&e.t[0].next==1);
  CHECK(sp_tick(&e,0x6000)==2);before=e;qbefore=q;
  CHECK(sp_wait(&e,&q,0)==0x03040003&&!memcmp(&e,&before,sizeof e)&&!memcmp(&q,&qbefore,sizeof q));
  CHECK(sp_wake(&e,&q)==0);CHECK(q.head==1&&q.tail==1&&q.generation==1&&e.t[0].state==1);
  CHECK(sp_tick(&e,0x7000)==0);before=e;qbefore=q;
  CHECK(sp_wait(&e,&q,0)==0x03040002&&!memcmp(&e,&before,sizeof e)&&!memcmp(&q,&qbefore,sizeof q));
  CHECK(sp_wake(&e,&q)==1);CHECK(q.head==8&&q.tail==8&&q.generation==2);
  CHECK(sp_wake(&e,&q)==8&&q.generation==3);
  q.head=1;q.tail=1;e.t[1].state=3;e.t[1].next=1;before=e;qbefore=q;
  CHECK(sp_wake(&e,&q)==0x03040002&&!memcmp(&e,&before,sizeof e)&&!memcmp(&q,&qbefore,sizeof q));
  CHECK(sp_init(&e,2)==0);CHECK(sp_add(&e,0,0,0x1000)==0);q=(Wait){8,8,0};before=e;
  CHECK(sp_wait(&e,&q,0)==0x03040003&&!memcmp(&e,&before,sizeof e));
  CHECK(dong_sched_init(&e,0x2000,0x3000)==0);
  for(unsigned i=0;i<129;i++)CHECK(dong_sched_tick(&e,0x10000+(uint64_t)i*256)<3);
  CHECK(e.current==0&&e.ticks==129&&e.t[1].ticks==64&&e.t[2].ticks==64&&e.switches==65);
  return 0;
}
int main(void) {
  if(policy())return 1;
  CHECK(sched_probe_xstate(1)==0);
  /* The probe gates XGETBV/XSAVE on actual host CPUID and OSXSAVE. A return of
     two is a recorded hardware unavailability, not a skipped unittest. */
  uint64_t actual=sched_probe_xstate(2);CHECK(actual==0||actual==2);
  printf("scheduler native checks passed %u xsave_host=%u\n",checks,(unsigned)actual);
  return 0;
}
