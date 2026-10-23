/* Independent host oracle. Actual Dong sidecar+Domain execute on real threads.
 * TLS CPU/root/IF0 and atomic lock/clock/flush stand in for hardware only. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <malloc.h>
#else
#include <pthread.h>
#include <sched.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct {U mode,token,inc,slot,cap_token,cap_inc,captured,requested,ack,capture,cap_xstate,returned,return_xstate,root,seen;} Cpu;
typedef struct {U ready,failed,lock,owner,online,sequence,barrier,expected,completed,kernel_root;void*engine;Cpu*cpus;void*processes;U arena,bytes;} Domain;
typedef struct __attribute__((aligned(64))) {U ready;Domain*domain;U next,serving,owner,wait[16];} State;
_Static_assert(sizeof(Domain)==120&&sizeof(Cpu)==120,"unchanged Domain/Cpu ABI");
_Static_assert(sizeof(State)==192&&offsetof(State,next)==16&&offsetof(State,wait)==40,"independent FIFO ABI");
extern U ABI bk_required(void),bk_init(U,U,U),bk_bind(U),bk_acquire(U,U,U),bk_unlock(U,U);
extern U ABI bk_original_acquire(U,U),bk_original_unlock(U),bk_poll(U),bk_register_hook(void),bk_hooks(U),bk_barrier(void),bk_wait(U,U),bk_audit(void),bk_park(U),bk_returning(U,U,U);
extern Domain* ABI bk_domain(U);
extern const State* ABI bk_state(void);
extern void ABI bk_fault(U,U);
static _Thread_local U cpu,root=0x100000,if0=1,hardware_allowed=1,expect_sidecar_unlock,allow_pause_block;
static U checks,tick=1,hardware_calls,attempts[16],flushes[16],pauses[16],legacy[16],kicks[16];
static U active,order_count,order[16],pause_block,pause_entered,pause_release,clock_watch;
static Domain*d;static const State*s;
static const U LONG_LIMIT=UINT64_C(0x1000000000000000);
static U load(const U*p){return __atomic_load_n(p,__ATOMIC_SEQ_CST);}
static void store(U*p,U v){__atomic_store_n(p,v,__ATOMIC_SEQ_CST);}
static U add(U*p,U v){return __atomic_fetch_add(p,v,__ATOMIC_SEQ_CST);}
static void fail(const char*expr,unsigned line){fprintf(stderr,"BKL native oracle line %u: %s\n",line,expr);exit(1);}
#define C(x) do{add(&checks,1);if(!(x))fail(#x,__LINE__);}while(0)
static void yield_thread(void){
#ifdef _WIN32
 Sleep(0);
#else
 sched_yield();
#endif
}
static void hw(void){C(hardware_allowed);add(&hardware_calls,1);}
void ABI __dong_panic(void){fprintf(stderr,"USER_BKL_DONG_PANIC unexpected runtime panic\n");exit(97);}
U ABI user_smp_arch_if0(void){hw();return if0;}
U ABI user_smp_arch_cpu(void){hw();return cpu;}
U ABI user_smp_arch_root(void){hw();return root;}
U ABI user_domain_legacy_poll(void){hw();C(cpu<3&&root==0x100000);add(&legacy[cpu],1);return 0;}
U ABI user_smp_arch_try_lock(U*p){hw();C(cpu<3&&p==&d->lock);add(&attempts[cpu],1);U expected=0;return __atomic_compare_exchange_n(p,&expected,1,0,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST);}
void ABI user_smp_arch_unlock(U*p){hw();C(cpu<3&&p==&d->lock&&load(p)==1);
 if(expect_sidecar_unlock){C(load(&s->owner)==cpu&&load(&s->wait[cpu])>0&&load(&s->wait[cpu])!=UINT64_MAX);C(load(&s->serving)==load(&s->wait[cpu])-1);}
 store(p,0);
}
U ABI user_smp_arch_clock(void){hw();U n=add(&tick,1),watch=load(&clock_watch);C(!watch||n<watch);return n;}
void ABI user_smp_arch_pause(void){hw();C(cpu<3);add(&pauses[cpu],1);
 if(allow_pause_block&&load(&pause_block)==cpu+1){store(&pause_entered,1);while(!load(&pause_release))yield_thread();}
 yield_thread();
}
U ABI user_smp_arch_flush(U target){hw();C(target==cpu&&cpu<3&&root==0x100000);add(&flushes[cpu],1);return 0;}
U ABI user_smp_arch_kick(U target){hw();C(target<3);add(&kicks[target],1);return 0;}
void ABI user_smp_arch_copy(U dst,U src,U n){hw();C(dst&&src&&(n==200||n==1024));memcpy((void*)(uintptr_t)dst,(void*)(uintptr_t)src,(size_t)n);}
void ABI user_smp_arch_save(U dst){hw();C(0);(void)dst;}
U ABI user_smp_arch_switch(U a,U b,U c){hw();C(0);(void)a;(void)b;(void)c;return 1;}
U ABI user_smp_arch_validate(U a,U b){hw();C(0);(void)a;(void)b;return 0;}
static void* aligned_arena(size_t n){void*p;
#ifdef _WIN32
 p=_aligned_malloc((n+4095)&~(size_t)4095,4096);
#else
 p=aligned_alloc(4096,(n+4095)&~(size_t)4095);
#endif
 C(p);memset(p,0xa5,n);return p;}
static void initialize(void){U n=bk_required();C(n==63040);C(!bk_init((U)(uintptr_t)aligned_arena((size_t)n),(U)(uintptr_t)aligned_arena((size_t)n),n));d=bk_domain(0);s=bk_state();C(d&&s&&load(&s->ready)==0);}
static void bind_old_gs(void){U before=load(&hardware_calls);hardware_allowed=0;C(!bk_bind(0));hardware_allowed=1;
 C(load(&hardware_calls)==before&&load(&s->ready)==1&&s->domain==d&&!load(&s->next)&&!load(&s->serving)&&load(&s->owner)==16);
 for(unsigned i=0;i<16;i++)C(!load(&s->wait[i]));
}
static void unlock(void){expect_sidecar_unlock=1;C(!bk_unlock(cpu,0));expect_sidecar_unlock=0;}
static void acquired(U ticket){C(load(&s->owner)==cpu&&load(&s->serving)==ticket&&load(&s->wait[cpu])==ticket+1);C(load(&d->lock)==1&&load(&d->owner)==cpu&&load(&d->cpus[cpu].mode)==5);C(add(&active,1)==0);U pos=add(&order_count,1);C(pos<16);store(&order[pos],ticket);}
static void leaving(void){C(add(&active,UINT64_MAX)==1);}
static void until(const U*p,U value){for(unsigned i=0;i<2000000;i++){if(load(p)==value)return;yield_thread();}C(0);}
typedef struct{U cpu,ticket,result,expected,limit;} Worker;
static void worker_body(Worker*w){cpu=w->cpu;root=0x100000;if0=1;hardware_allowed=1;allow_pause_block=1;
 w->result=bk_acquire(cpu,w->limit,0);C(w->result==w->expected);
 if(!w->result){acquired(w->ticket);leaving();unlock();}
}
#ifdef _WIN32
typedef HANDLE Thread;
static DWORD WINAPI worker_entry(LPVOID p){worker_body((Worker*)p);return 0;}
static Thread start(Worker*w){HANDLE t=CreateThread(NULL,0,worker_entry,w,0,NULL);C(t!=NULL);return t;}
static void join(Thread t){C(WaitForSingleObject(t,30000)==WAIT_OBJECT_0);C(CloseHandle(t));}
#else
typedef pthread_t Thread;
static void*worker_entry(void*p){worker_body((Worker*)p);return NULL;}
static Thread start(Worker*w){pthread_t t;C(!pthread_create(&t,NULL,worker_entry,w));return t;}
static void join(Thread t){C(!pthread_join(t,NULL));}
#endif
static void fair(void){
 C(!bk_acquire(0,LONG_LIMIT,0));acquired(0);C(!bk_register_hook());
 Worker a={1,1,UINT64_MAX,0,LONG_LIMIT},b={2,2,UINT64_MAX,0,LONG_LIMIT};
 Thread ta=start(&a);until(&s->wait[1],2);Thread tb=start(&b);until(&s->wait[2],3);C(load(&s->next)==3);
 U sequence=bk_barrier();C(sequence==1);C(!bk_wait(sequence,load(&tick)+100000));
 C(load(&d->completed)==1&&!load(&d->barrier));for(unsigned i=0;i<3;i++)C(load(&d->cpus[i].ack)==sequence&&load(&flushes[i])==1);
 C(bk_hooks(0)>0);leaving();unlock();
 C(!bk_acquire(0,LONG_LIMIT,0));acquired(3);leaving();unlock();join(ta);join(tb);
 C(load(&order_count)==4);for(U i=0;i<4;i++)C(load(&order[i])==i);
 C(bk_hooks(1)>0&&bk_hooks(2)>0&&load(&legacy[1])>0&&load(&legacy[2])>0&&load(&pauses[1])>0&&load(&pauses[2])>0);
 C(load(&attempts[0])==2&&load(&attempts[1])==1&&load(&attempts[2])==1);
 C(load(&s->next)==4&&load(&s->serving)==4&&load(&s->owner)==16&&!load(&d->lock)&&load(&d->owner)==16&&!load(&active)&&!bk_audit());
}
static void bootstrap(void){C(!bk_original_acquire(0,LONG_LIMIT));Worker a={1,0,UINT64_MAX,0,LONG_LIMIT};Thread t=start(&a);
 until(&s->wait[1],1);for(unsigned i=0;i<2000000&&!load(&attempts[1]);i++)yield_thread();C(load(&attempts[1])>0);
 C(load(&s->owner)==16&&load(&s->serving)==0&&load(&d->owner)==0&&load(&d->lock)==1);C(!bk_original_unlock(0));join(t);
 C(!a.result&&load(&s->next)==1&&load(&s->serving)==1&&load(&s->owner)==16&&!load(&d->lock));
}
static void cycles(void){for(unsigned i=0;i<8;i++){C(!bk_acquire(0,LONG_LIMIT,0));C(load(&s->serving)==i&&load(&s->wait[0])==i+1);unlock();C(load(&d->cpus[0].mode)==4);C(!bk_park(0));C(load(&d->cpus[0].mode)==1);}
 C(load(&s->next)==8&&load(&s->serving)==8&&load(&s->owner)==16);}
static void returning(void){static U frame[25] __attribute__((aligned(64)));static unsigned char xstate[1024] __attribute__((aligned(64)));
 frame[15]=0x400000;frame[16]=0x202;frame[17]=0x70000000;frame[18]=0x200000;
 C(!bk_acquire(0,LONG_LIMIT,0));C(!bk_returning(0,(U)(uintptr_t)frame,(U)(uintptr_t)xstate));C(load(&d->cpus[0].mode)==6);unlock();C(load(&d->cpus[0].mode)==6&&!load(&d->lock)&&load(&s->serving)==1);}
static void queued_expired(void){C(!bk_acquire(0,LONG_LIMIT,0));store(&pause_block,2);
 Worker w={1,1,UINT64_MAX,0x06230004,1000};Thread t=start(&w);until(&pause_entered,1);C(load(&s->wait[1])==2);store(&tick,2000);unlock();C(!load(&d->lock)&&load(&s->serving)==1);store(&pause_release,1);join(t);
 C(w.result==0x06230004&&load(&s->wait[1])==2&&load(&s->serving)==1&&load(&s->owner)==16&&!load(&d->lock)&&!load(&d->failed));
}
static void duplicate_waiter(void){C(!bk_acquire(0,LONG_LIMIT,0));store(&pause_block,2);
 Worker w={1,1,UINT64_MAX,0x06090004,LONG_LIMIT};Thread t=start(&w);until(&pause_entered,1);
 cpu=1;C(bk_acquire(1,load(&tick)+8,0)==0x06230002&&load(&s->next)==2&&load(&s->wait[1])==2);
 cpu=0;store(&d->failed,1);store(&pause_release,1);join(t);C(w.result==0x06090004&&load(&s->owner)==0&&!load(&s->serving)&&load(&s->wait[1])==2&&load(&d->lock)==1);
}
static void snapshot(const char*path){FILE*f=fopen(path,"wb");C(f);C(fwrite(s,1,sizeof *s,f)==sizeof *s);C(fwrite(d,1,sizeof *d,f)==sizeof *d);C(fwrite(d->cpus,1,16*sizeof(Cpu),f)==16*sizeof(Cpu));C(!fclose(f));}
int main(int argc,char**argv){C(argc==3);initialize();
 if(!strcmp(argv[1],"bind")){hardware_allowed=0;store(&d->barrier,1);C(bk_bind(0)==0x06230001&&!load(&s->ready));store(&d->barrier,0);hardware_allowed=1;bind_old_gs();C(bk_bind(0)==0x06230001&&bk_bind(1)==0x06230001);}
 else{bind_old_gs();
  if(!strcmp(argv[1],"fair"))fair();
  else if(!strcmp(argv[1],"bootstrap"))bootstrap();
  else if(!strcmp(argv[1],"cycles"))cycles();
  else if(!strcmp(argv[1],"returning"))returning();
  else if(!strcmp(argv[1],"queued-expired-free"))queued_expired();
  else if(!strcmp(argv[1],"duplicate-waiter"))duplicate_waiter();
  else if(!strcmp(argv[1],"foreign")){C(bk_acquire(0,LONG_LIMIT,1)==0x06230001&&!load(&s->next)&&!load(&s->wait[0])&&!load(&d->lock));}
  else if(!strcmp(argv[1],"wrong-cpu")){C(bk_acquire(1,LONG_LIMIT,0)==0x06090001&&!load(&s->next)&&!load(&s->wait[1])&&!load(&d->lock));}
  else if(!strcmp(argv[1],"if0")){if0=0;C(bk_acquire(0,LONG_LIMIT,0)==0x06090002&&!load(&s->next)&&!load(&s->wait[0])&&!load(&d->lock));if0=1;}
  else if(!strcmp(argv[1],"root")){root=0x200000;C(bk_acquire(0,LONG_LIMIT,0)==0x06090002&&load(&s->next)==1&&load(&s->wait[0])==1&&!load(&s->serving)&&load(&s->owner)==16&&!load(&d->lock));root=0x100000;}
  else if(!strcmp(argv[1],"duplicate")){C(!bk_acquire(0,LONG_LIMIT,0));C(bk_acquire(0,LONG_LIMIT,0)==0x06230002&&load(&s->next)==1&&load(&s->wait[0])==1&&load(&s->owner)==0&&load(&d->owner)==0&&load(&d->lock)==1);}
  else if(!strcmp(argv[1],"queued-timeout")){C(!bk_acquire(0,LONG_LIMIT,0));cpu=1;U limit=load(&tick)+8;store(&clock_watch,limit+64);C(bk_acquire(1,limit,0)==0x06230004);store(&clock_watch,0);C(load(&s->next)==2&&!load(&s->serving)&&load(&s->owner)==0&&load(&s->wait[1])==2&&load(&d->owner)==0&&load(&d->lock)==1&&!load(&d->failed));}
  else if(!strcmp(argv[1],"head-timeout")){C(!bk_original_acquire(0,LONG_LIMIT));cpu=1;C(bk_acquire(1,load(&tick)+8,0)==0x06090005);C(load(&s->next)==1&&!load(&s->serving)&&load(&s->owner)==16&&load(&s->wait[1])==1&&load(&d->owner)==0&&load(&d->lock)==1&&load(&d->failed)==1);}
  else if(!strcmp(argv[1],"unlock-failed")||!strcmp(argv[1],"already-failed")){C(!bk_acquire(0,LONG_LIMIT,0));State before=*s;
   U code=0x06090002;if(!strcmp(argv[1],"unlock-failed"))store(&d->barrier,7);else{store(&d->failed,1);code=0x06090004;}
   C(bk_unlock(0,0)==code&&!memcmp(&before,s,sizeof before)&&load(&d->owner)==0&&load(&d->lock)==1);}
  else if(!strcmp(argv[1],"overflow")||!strcmp(argv[1],"overflow-max")){U n=!strcmp(argv[1],"overflow")?UINT64_MAX-1:UINT64_MAX;bk_fault(0,n);bk_fault(1,n);C(bk_acquire(0,LONG_LIMIT,0)==0x06230003&&load(&s->next)==n&&load(&s->serving)==n&&load(&s->wait[0])==UINT64_MAX&&load(&s->owner)==16&&!load(&d->lock));}
  else{C(!strcmp(argv[1],"last-ticket"));bk_fault(0,UINT64_MAX-2);bk_fault(1,UINT64_MAX-2);C(!bk_acquire(0,LONG_LIMIT,0));C(load(&s->wait[0])==UINT64_MAX-1);unlock();C(load(&s->next)==UINT64_MAX-1&&load(&s->serving)==UINT64_MAX-1);C(bk_acquire(0,LONG_LIMIT,0)==0x06230003&&load(&s->wait[0])==UINT64_MAX&&!load(&d->lock));}
 }
 snapshot(argv[2]);C(load(&checks)<=UINT32_MAX);
 printf("USER_BKL_NATIVE_PASS scenario=%s checks=%u synthetic_hardware=true actual_ap_cpl3_executed=false actual_qemu_executed=false next=0x%08x%08x serving=0x%08x%08x owner=%u order-count=%u\n",argv[1],(unsigned)load(&checks),(unsigned)(load(&s->next)>>32),(unsigned)load(&s->next),(unsigned)(load(&s->serving)>>32),(unsigned)load(&s->serving),(unsigned)load(&s->owner),(unsigned)load(&order_count));return 0;
}
