#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct{U w[23];} Frame;
typedef struct{U token,source,target,notify;} Move;
extern U ABI ps_required(void),ps_init(U,U,U),ps_config(U,U,U),ps_admit(U,U,U,U,U*),ps_start(void),ps_wake(U),ps_affinity(U,U),ps_priority(U,U),ps_preempt(U,U),ps_rebalance(U,U,Move*),ps_get(U,U),ps_audit(void);
extern U ABI parallel_dispatch(U,U,U),parallel_request(U,U),parallel_idle_arm(U);
static U checks,kicks,saves,restores,arms,stops,eois,locks,unlocks,registered[16],tokens[64],timer_active[16],cpu_kicks[16];
static unsigned char expected[64][1024],hardware[16][1024],initial[1024] __attribute__((aligned(64)));
static unsigned char *arena,*stacks,*idle,*scheduler;
static U active_cpu,old_token,phase,serial,event_active,if0=1,on_scheduler=1,wrong_root,timer_fault,kick_fault;
static U retirements,exit_requested[16];
static void fail(const char*s,unsigned line){fprintf(stderr,"parallel adapter oracle line %u: %s\n",line,s);exit(1);}
#define C(x) do{checks++;if(!(x))fail(#x,__LINE__);}while(0)
static void*alloc(size_t n){
#ifdef _WIN32
 return _aligned_malloc(n,4096);
#else
 return aligned_alloc(4096,(n+4095)&~(size_t)4095);
#endif
}
static U id(U token){C((token&255)>0&&(token&255)<=64);return (token&255)-1;}
void ABI __dong_panic(void){fail("Dong panic",__LINE__);}
U ABI parallel_arch_if0(void){return if0;}
void ABI parallel_arch_lock(U*p){C(if0&&!*p);*p=1;locks++;if(event_active)C(phase==(old_token?1:0));}
void ABI parallel_arch_unlock(U*p){C(*p==1);*p=0;unlocks++;if(event_active)phase=2;}
U ABI parallel_arch_on_scheduler(U low,U top){C(low==(U)(uintptr_t)(scheduler+active_cpu*16384)&&top==low+16384);return on_scheduler;}
U ABI parallel_arch_root(void){return wrong_root?0x200000:0x100000;}
/* Retire notification is observed before the old token/frame are cleared. */
void ABI parallel_live_retire(U cpu,U slot,U frame){
 C(event_active&&cpu==active_cpu&&exit_requested[cpu]&&phase==1&&locks==unlocks+1);
 C(old_token&&slot==id(old_token)&&ps_get(3,cpu)==old_token&&ps_get(4,slot)==old_token);
 C(ps_get(5,slot)==3&&frame==ps_get(6,slot));retirements++;
}
static U request_exit(U cpu){U result=parallel_request(cpu,2);if(!result){C(!exit_requested[cpu]);exit_requested[cpu]=1;}return result;}

void ABI parallel_arch_save(U pointer){C(event_active&&on_scheduler&&phase==0&&old_token&&pointer==ps_get(8,id(old_token)));C(ps_get(5,id(old_token))==2);
 memcpy((void*)(uintptr_t)pointer,hardware[active_cpu],1024);memcpy(expected[id(old_token)],hardware[active_cpu],1024);saves++;phase=1;}
void ABI parallel_arch_restore(U pointer){U token=ps_get(3,active_cpu);C(event_active&&phase==5&&token&&pointer==ps_get(8,id(token)));
 C(!memcmp((void*)(uintptr_t)pointer,expected[id(token)],1024));memcpy(hardware[active_cpu],(void*)(uintptr_t)pointer,1024);restores++;phase=6;}
void ABI parallel_arch_copy(U dst,U src,U n){C(n==1024&&src==(U)(uintptr_t)initial);memcpy((void*)(uintptr_t)dst,(void*)(uintptr_t)src,(size_t)n);}
void ABI parallel_arch_register(U cpu,U top){C(cpu>=1&&cpu<=3&&top==(U)(uintptr_t)(scheduler+(cpu+1)*16384));registered[cpu]=top;}
U ABI parallel_arch_install(U root,U tss,U top){C(event_active&&phase==2&&root==0x100000&&tss==0x100000+active_cpu*4096);
 U token=ps_get(3,active_cpu);C(top==(token?ps_get(9,id(token)):ps_get(10,active_cpu)));phase=3;return 0;}
static U competition(U cpu){
 U token=ps_get(3,cpu);if(!token)return 0;U priority=ps_get(17,id(token));
 for(U t=0;t<64;t++)if(ps_get(5,t)==1&&(ps_get(18,t)&(1<<cpu))&&ps_get(17,t)<=priority)return 1;
 return 0;
}
U ABI parallel_arch_timer(U lapic,U mode,U value){
 C(lapic==0xfec00000);if(event_active)C(phase==3);
 if(!mode){C(!value);C(!event_active||!competition(active_cpu));stops++;timer_active[active_cpu]=0;}
 else{C(value>0&&mode==(active_cpu==2?2:1));C(event_active&&competition(active_cpu));arms++;timer_active[active_cpu]=1;}
 if(event_active){phase=4;}return timer_fault;
}
U ABI parallel_arch_clock(void){return 1000000000+serial*1000;}
void ABI parallel_arch_eoi(U lapic){C(event_active&&(phase==3||phase==4)&&lapic==0xfec00000);C(timer_active[active_cpu]==competition(active_cpu));eois++;phase=5;}
U ABI parallel_arch_kick(U lapic,U apic){C(if0&&lapic==0xfec00000&&apic>=17&&apic<=19);kicks++;cpu_kicks[apic-16]++;return kick_fault;}
static U stack(unsigned n){return (U)(uintptr_t)(stacks+n*16384);}
static void setup(void){
 size_t bytes=(size_t)ps_required();C(bytes<128*1024);arena=alloc(bytes);stacks=alloc(64*16384);idle=alloc(16*16384);scheduler=alloc(16*16384);C(arena&&stacks&&idle&&scheduler);
 memset(arena,0,bytes);memset(initial,0x5a,1024);for(unsigned i=0;i<64;i++)memcpy(expected[i],initial,1024);
 C(!ps_init((U)(uintptr_t)arena,bytes,(U)(uintptr_t)initial));C(ps_init((U)(uintptr_t)arena,bytes,(U)(uintptr_t)initial)!=0);
 for(U c=1;c<=3;c++){C(!ps_config(c,(U)(uintptr_t)(idle+c*16384),(U)(uintptr_t)(scheduler+c*16384)));C(registered[c]==(U)(uintptr_t)(scheduler+(c+1)*16384));}
 C(ps_config(0,(U)(uintptr_t)idle,(U)(uintptr_t)scheduler)!=0);C(ps_config(1,(U)(uintptr_t)idle,(U)(uintptr_t)scheduler)!=0);
}
static void admit(unsigned n,U priority,U affinity){U token=0xa5;C(!ps_admit(n,priority,affinity,stack(n),&token));C(token&&token==ps_get(4,n));tokens[n]=token;memcpy(expected[n],initial,1024);
 Frame*f=(Frame*)(uintptr_t)ps_get(6,n);C(f->w[4]==0x80000100+n*16&&f->w[9]==n+100&&f->w[18]==0x80000010&&f->w[19]==8&&f->w[20]==0x202&&f->w[21]==stack(n)+16384-8&&f->w[22]==16);}
static U idle_frame(U cpu){Frame*f=(Frame*)(idle+(cpu+1)*16384-192);memset(f,0,sizeof *f);f->w[18]=0x80000020;f->w[19]=8;f->w[20]=0x202;f->w[21]=(U)(uintptr_t)(idle+(cpu+1)*16384-8);f->w[22]=16;return (U)(uintptr_t)f;}
static U dispatch(U cpu,U expect_failure){
 active_cpu=cpu;old_token=ps_get(3,cpu);phase=0;event_active=1;serial++;
 U old_frame=old_token?ps_get(6,id(old_token)):idle_frame(cpu);
 if(old_token){for(unsigned i=0;i<1024;i++)hardware[cpu][i]=(unsigned char)(serial+i*17+old_token);}
 U before_restore=restores,before_saves=saves,before_retire=retirements;U result=parallel_dispatch(cpu,old_frame,2);
 if(expect_failure){C(!result&&ps_get(0,0));event_active=0;return 0;}
 C(retirements==before_retire+exit_requested[cpu]);exit_requested[cpu]=0;
 C(result&&!ps_get(0,0));U now=ps_get(3,cpu);C(saves==before_saves+(old_token?1:0));C(restores==before_restore+(now?1:0));
 C(phase==(now?6:5));if(now){C(result==ps_get(6,id(now))&&ps_get(5,id(now))==2&&(ps_get(18,id(now))&(1<<cpu)));}
 else {C(result==idle_frame(cpu));}
 event_active=0;C(!ps_audit());return now;
}
static int normal(void){
 setup();U out=0xa5;U seq=ps_get(2,0);if0=0;C(ps_admit(0,1,14,stack(0),&out)!=0&&out==0xa5&&ps_get(2,0)==seq);if0=1;
 C(ps_admit(0,32,14,stack(0),&out)!=0&&out==0xa5);C(ps_admit(0,1,1,stack(0),&out)!=0&&out==0xa5);
 admit(0,8,2);admit(1,8,2);admit(2,31,14);admit(3,0,8);admit(4,16,14);
 C(ps_admit(5,1,14,stack(0),&out)!=0&&out==0xa5);C(!ps_start()&&kicks==3);C(ps_start()!=0);
 C(dispatch(1,0)==tokens[0]);C(dispatch(1,0)==tokens[1]);C(dispatch(2,0)==tokens[4]);C(dispatch(3,0)==tokens[3]);
 C(!ps_priority(tokens[0],0));C(!ps_preempt(1,1));C(parallel_request(1,1)!=0);
 ((Frame*)(uintptr_t)ps_get(6,1))->w[20]=0x10602;C(dispatch(1,0)==tokens[1]&&ps_get(13,1)==1);C(!ps_preempt(1,0));C(dispatch(1,0)==tokens[0]);
 C(!parallel_request(1,1));C(dispatch(1,0)==tokens[1]&&ps_get(5,0)==3);U wake_kicks=kicks;C(!ps_wake(tokens[0])&&kicks==wake_kicks+1);C(dispatch(1,0)==tokens[0]);
 U stale=tokens[0];C(!request_exit(1));C(dispatch(1,0)==tokens[1]);C(ps_get(4,0)==0&&ps_get(5,0)==0);seq=ps_get(2,0);C(ps_wake(stale)!=0&&ps_get(2,0)==seq);
 admit(0,8,2);C(tokens[0]!=stale&&ps_wake(stale)!=0);C(!parallel_request(1,1));C(dispatch(1,0)==tokens[0]);C(!parallel_request(1,1));C(dispatch(1,0)==tokens[2]);
 C(!parallel_request(2,1));C(dispatch(2,0)==0);C(!ps_affinity(tokens[0],14));C(!ps_wake(tokens[0]));C(ps_get(7,0)==2&&dispatch(2,0)==tokens[0]);
 seq=ps_get(2,0);C(ps_affinity(tokens[0],2)!=0&&ps_get(2,0)==seq&&ps_get(7,0)==2);
 for(unsigned i=5;i<8;i++){admit(i,31,2);C(!ps_affinity(tokens[i],14));}Move move={0};C(ps_rebalance(1,3,&move)==1&&move.source==1&&move.target==3&&ps_get(7,id(move.token))==3);
 for(unsigned i=8;i<40;i++)admit(i,i-8,14);
 for(unsigned round=0;round<1000;round++)for(U cpu=1;cpu<=3;cpu++){
  U prior=ps_get(3,cpu),best=32;for(U i=0;i<64;i++)if(ps_get(5,i)==1&&ps_get(7,i)==cpu&&ps_get(17,i)<best)best=ps_get(17,i);
  if(prior&&ps_get(17,id(prior))<best){best=ps_get(17,id(prior));}U next=dispatch(cpu,0);if(best<32)C(next&&ps_get(17,id(next))==best);
 }
 C(locks==unlocks&&saves>3000&&restores>3000&&arms>0&&stops>0&&arms+stops<=eois&&kicks>10);return 0;
}
static int failure(const char*name){
 setup();admit(0,8,2);admit(1,8,2);if(!strcmp(name,"kick-fail")){kick_fault=1;C(ps_start()==0x06070003&&ps_get(0,0));return 0;}
 C(!ps_start());C(dispatch(1,0)==tokens[0]);U seq=ps_get(2,0);
 if(!strcmp(name,"stack-fail"))on_scheduler=0;
 else if(!strcmp(name,"root-fail"))wrong_root=1;
 else if(!strcmp(name,"timer-fail"))timer_fault=1;
 else if(!strcmp(name,"stop-fail")){timer_fault=1;C(!parallel_request(1,1));}
 else if(!strcmp(name,"frame-fail"))((Frame*)(uintptr_t)ps_get(6,0))->w[19]=0x33;
 else C(0);
 dispatch(1,1);if(!strcmp(name,"stack-fail")||!strcmp(name,"root-fail"))C(ps_get(2,0)==seq);
 seq=ps_get(2,0);C(ps_wake(tokens[0])==0x06070004&&ps_get(2,0)==seq);return 0;
}
static int tickless(void){
 setup();C(!ps_start()&&kicks==3);C(!arms&&!stops);
 C(!dispatch(1,0)&&!arms&&stops==1&&!timer_active[1]);
 U old_stops=stops;active_cpu=1;C(parallel_idle_arm(1)==1&&!arms&&stops==old_stops);
 C(!dispatch(2,0)&&!dispatch(3,0)&&!arms&&stops==3);
 U prior_kicks=kicks;admit(0,8,2);admit(1,8,2);C(kicks==prior_kicks+2);
 C(dispatch(1,0)==tokens[0]&&timer_active[1]&&arms==1);
 C(dispatch(1,0)==tokens[1]&&timer_active[1]&&arms==2);
 C(!parallel_request(1,1));C(dispatch(1,0)==tokens[0]&&!timer_active[1]&&stops==4);
 C(!parallel_request(1,1));C(!dispatch(1,0)&&!timer_active[1]&&stops==4);
 C(!ps_wake(tokens[0])&&kicks==prior_kicks+3);C(dispatch(1,0)==tokens[0]&&!timer_active[1]);
 C(!ps_wake(tokens[1])&&kicks==prior_kicks+4);C(dispatch(1,0)==tokens[1]&&timer_active[1]&&arms==3);
 C(!request_exit(1));C(dispatch(1,0)==tokens[0]&&!timer_active[1]&&stops==5);
 C(!request_exit(1));C(!dispatch(1,0)&&!timer_active[1]&&ps_get(1,0)==0&&stops==5);
 active_cpu=1;C(parallel_idle_arm(1)==1&&!timer_active[1]&&stops==5);
 prior_kicks=kicks;admit(0,8,2);C(kicks==prior_kicks+1);C(dispatch(1,0)==tokens[0]&&!timer_active[1]);
 admit(1,8,2);U c2=cpu_kicks[2],c3=cpu_kicks[3];C(!ps_affinity(tokens[1],14));C(cpu_kicks[2]==c2+1&&cpu_kicks[3]==c3+1);
 C(dispatch(2,0)==tokens[1]&&!timer_active[2]);
 C(!parallel_request(1,1));C(!dispatch(1,0)&&!timer_active[1]);
 C(!parallel_request(2,1));C(!dispatch(2,0)&&!timer_active[2]);
 c2=cpu_kicks[2];c3=cpu_kicks[3];C(!ps_wake(tokens[1]));C(cpu_kicks[2]==c2+1&&cpu_kicks[3]==c3+1);
 C(dispatch(3,0)==tokens[1]&&!timer_active[3]);
 C(!request_exit(3));C(!dispatch(3,0)&&!timer_active[3]);C(!ps_wake(tokens[0]));C(dispatch(1,0)==tokens[0]);
 C(!request_exit(1));C(!dispatch(1,0)&&!ps_get(1,0));C(!ps_audit()&&locks==unlocks);return 0;
}
int main(int argc,char**argv){C(argc==2);if(!strcmp(argv[1],"normal"))normal();else if(!strcmp(argv[1],"tickless"))tickless();else failure(argv[1]);
 printf("parallel tickless native checks passed %u; scenario=%s real-runqueue timer-stop idle-IPI wake private-stack-xstate\n",(unsigned)checks,argv[1]);return 0;}
