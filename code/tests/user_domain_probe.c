#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct{U w[25];} Frame;
extern U ABI ud_required(void),ud_init(U,U),ud_lock(U,U),ud_unlock(U),ud_admit(U,U,U,U,U,U,U*),ud_select(U,U*),ud_begin(U),ud_complete(U),ud_drain(U),ud_release(U,U),ud_commit(U),ud_cancel(U),ud_park(U),ud_poll(U),ud_barrier_begin(U),ud_barrier_finish(U,U),ud_wait(U,U,U),ud_retire_begin(U,U),ud_retire_finish(U,U),ud_wake(U,U,U),ud_audit(void),ud_get(U,U);
static U checks,cpu,roots[16],switches,retains,flushes[16],kicks[16],clock_tick=1,flush_fault,kick_fault,switch_fault,if0=1,lock_wait_release,wait_sequence,legacy_fault,legacy_polls;
static U tlb_root[16][17],tlb_version[16][17],map_version[17];
static Frame frames[16] __attribute__((aligned(64)));
static unsigned char xstates[16][1024] __attribute__((aligned(64))),hardware[16][1024];
static U tokens[16];
static void fail(const char*s,unsigned line){fprintf(stderr,"user SMP oracle line %u: %s\n",line,s);exit(1);}
#define C(x)do{checks++;if(!(x))fail(#x,__LINE__);}while(0)
void ABI __dong_panic(void){fail("Dong panic",__LINE__);}
U ABI user_smp_arch_if0(void){return if0;}
U ABI user_smp_arch_cpu(void){return cpu;}
U ABI user_smp_arch_root(void){return roots[cpu];}
/* Hardware legacy-mailbox boundary, not part of the queue/ownership model. */
U ABI user_domain_legacy_poll(void){C(roots[cpu]==0x100000);legacy_polls++;return legacy_fault;}
U ABI user_smp_arch_try_lock(U*p){if(*p)return 0;*p=1;return 1;}
void ABI user_smp_arch_unlock(U*p){C(*p==1);*p=0;}
U ABI user_smp_arch_clock(void){return clock_tick++;}
void ABI user_smp_arch_copy(U dst,U src,U n){C(n==200||n==1024);memcpy((void*)(uintptr_t)dst,(void*)(uintptr_t)src,(size_t)n);}
void ABI user_smp_arch_save(U pointer){C(ud_get(4,cpu)==3&&roots[cpu]==0x100000&&pointer==ud_get(9,cpu));memcpy((void*)(uintptr_t)pointer,hardware[cpu],1024);}
U ABI user_smp_arch_flush(U target){C(target==cpu&&roots[cpu]==0x100000);U mode=ud_get(4,cpu);C(mode==1||mode==4||mode==5);
 flushes[cpu]++;if(flush_fault)return 1;memset(tlb_root[cpu],0,sizeof tlb_root[cpu]);memset(tlb_version[cpu],0,sizeof tlb_version[cpu]);return 0;}
U ABI user_smp_arch_kick(U target){C(target<3);kicks[target]++;return kick_fault;}
U ABI user_smp_arch_validate(U frame,U root){Frame*f=(Frame*)(uintptr_t)frame;
 return f->w[15]>=0x10000&&f->w[15]<0x8000000000&&f->w[17]>=0x10000&&f->w[17]<0x8000000000&&(f->w[16]&0x202)==0x202&&!(f->w[16]&~(U)0x10ed7)&&f->w[18]==root&&!f->w[19]&&!f->w[20]&&!f->w[24];}
U ABI user_smp_arch_switch(U root,U tag,U retain){C(tag>=1&&tag<=16&&ud_get(4,cpu)==6&&roots[cpu]==0x100000);
 if(retain){C(tlb_root[cpu][tag]==root&&tlb_version[cpu][tag]==map_version[tag]);retains++;}
 else{tlb_root[cpu][tag]=root;tlb_version[cpu][tag]=map_version[tag];}switches++;if(switch_fault)return 1;roots[cpu]=root;return 0;}
static void prepared(unsigned slot,U root,U value){memset(&frames[slot],0,sizeof frames[slot]);frames[slot].w[14]=value;frames[slot].w[15]=0x400000;frames[slot].w[16]=0x202;frames[slot].w[17]=0x7f000000;frames[slot].w[18]=root;memset(xstates[slot],(unsigned char)value,1024);map_version[slot+1]++;}
static void setup(void){size_t n=(size_t)ud_required();C(n<128*1024);void*p;
#ifdef _WIN32
 p=_aligned_malloc(n,4096);
#else
 p=aligned_alloc(4096,(n+4095)&~(size_t)4095);
#endif
 C(p);memset(p,0xa5,n);for(unsigned c=0;c<16;c++)roots[c]=0x100000;C(!ud_init((U)(uintptr_t)p,n));C(!ud_audit());}
static void lock(unsigned who){cpu=who;C(!ud_lock(cpu,clock_tick+10000));C(ud_get(1,0)==cpu&&ud_get(2,0)==1&&ud_get(4,cpu)==5);}
static void admit(unsigned slot,U inc,U root,U value){prepared(slot,root,value);U token=0xa5;
 C(!ud_admit(cpu,slot,inc,root,(U)(uintptr_t)&frames[slot],(U)(uintptr_t)xstates[slot],&token));C(token&&token==ud_get(15,slot));tokens[slot]=token;}
static U select_user(void){U out=0xa5;C(ud_select(cpu,&out)==1&&out==ud_get(10,cpu));C(ud_get(4,cpu)==6);C(!ud_unlock(cpu));C(ud_commit(cpu)==1&&ud_get(4,cpu)==2);return ud_get(7,cpu);}
static void enter(unsigned who,U value){cpu=who;C(ud_get(4,cpu)==2);U slot=ud_get(7,cpu);C(slot<16);C(!ud_begin(cpu));
 Frame*f=(Frame*)(uintptr_t)ud_get(8,cpu);memcpy(f,&frames[slot],sizeof *f);f->w[14]=value;memset(hardware[cpu],(unsigned char)value,1024);roots[cpu]=0x100000;
 C(!ud_complete(cpu)&&ud_get(14,cpu)==1&&ud_get(4,cpu)==4);}
static void idle_poll(unsigned who,U expected){cpu=who;U old=flushes[cpu];C(ud_poll(cpu)==expected);C(flushes[cpu]==old+expected);}
static void finish(unsigned owner,U sequence){cpu=owner;C(ud_barrier_finish(cpu,sequence)==1&&ud_get(20,0)==sequence&&!ud_get(3,0));}
void ABI user_smp_arch_pause(void){
 if(lock_wait_release){C(cpu==1&&ud_get(13,1)==wait_sequence&&ud_get(1,0)==2);lock_wait_release=0;U save=cpu;cpu=2;C(ud_barrier_finish(cpu,wait_sequence)==1);C(!ud_retire_finish(cpu,0));C(!ud_unlock(cpu));cpu=save;}
}
static int normal(void){
 setup();cpu=2;C(ud_lock(0,100)!=0&&!ud_get(2,0));lock(0);admit(0,1,0x200000,0x11);admit(1,1,0x300000,0x22);C(select_user()==0);C(!retains&&switches==1);
 lock(1);C(select_user()==1);C(!retains&&switches==2);lock(2);U sentinel=0xa5;C(!ud_select(2,&sentinel)&&sentinel==0xa5);C(!ud_unlock(2));C(!ud_park(2)&&ud_get(4,2)==1);
 enter(0,0x44);lock(0);C(ud_drain(0)==1&&frames[0].w[14]==0x44);for(unsigned i=0;i<1024;i++)C(xstates[0][i]==0x44);
 U old_kick1=kicks[1],old_kick2=kicks[2];C(!ud_release(0,1));C(kicks[1]==old_kick1&&kicks[2]==old_kick2+1);C(select_user()==0&&retains==1);
 lock(2);U sequence=ud_retire_begin(2,0);C(sequence==1&&ud_get(17,0)==1);C(ud_unlock(2)!=0);C(ud_retire_finish(2,0)!=0);idle_poll(2,1);
 cpu=0;C(!ud_poll(0));C(!ud_begin(0));Frame*f=(Frame*)(uintptr_t)ud_get(8,0);memcpy(f,&frames[0],sizeof *f);f->w[14]=0x66;memset(hardware[0],0x66,1024);roots[0]=0x100000;
 C(!ud_poll(0));cpu=2;C(!ud_barrier_finish(2,sequence));cpu=0;C(!ud_complete(0));idle_poll(0,1);enter(1,0x77);idle_poll(1,1);finish(2,sequence);
 C(!ud_retire_finish(2,0)&&!ud_get(15,0)&&ud_get(16,0)==1&&ud_get(14,0)==1);U old=tokens[0];admit(0,2,0x400000,0xab);C(tokens[0]!=old);C(!ud_unlock(2));
 lock(0);C(!ud_drain(0)&&frames[0].w[14]==0xab);C(select_user()==0&&retains==1);C(tlb_root[0][1]==0x400000);
 lock(1);C(ud_drain(1)==1&&frames[1].w[14]==0x77);C(!ud_release(1,1));U out=0xa5;C(ud_select(1,&out)==1);C(!ud_unlock(1));C(ud_get(4,1)==6&&roots[1]==0x100000);
 lock(2);sequence=ud_retire_begin(2,1);C(sequence==2);cpu=1;C(!ud_poll(1));U old_switches=switches;C(!ud_commit(1)&&switches==old_switches);C(!ud_cancel(1));idle_poll(1,1);enter(0,0x88);idle_poll(0,1);idle_poll(2,1);finish(2,sequence);C(!ud_retire_finish(2,1));C(!ud_unlock(2));
 lock(0);C(ud_drain(0)==1&&frames[0].w[14]==0x88);C(!ud_release(0,1));C(select_user()==0);C(ud_get(19,0)==1);
 lock(2);sequence=ud_retire_begin(2,0);C(sequence==3);enter(0,0x99);idle_poll(0,1);idle_poll(2,1);
 cpu=1;C(ud_get(4,1)==4&&ud_get(13,1)==2);wait_sequence=sequence;lock_wait_release=1;C(!ud_lock(1,clock_tick+1000));C(!lock_wait_release&&ud_get(13,1)==sequence&&ud_get(1,0)==1&&!ud_get(19,0));C(!ud_drain(1));C(!ud_unlock(1));
 lock(0);C(!ud_drain(0));U no=0xa5;C(ud_admit(0,0,2,0x500000,(U)(uintptr_t)&frames[0],(U)(uintptr_t)xstates[0],&no)!=0&&no==0xa5);admit(0,3,0x500000,0xcd);C(select_user()==0);C(!ud_get(0,0)&&!ud_audit());
 C(flushes[0]==3&&flushes[1]==3&&flushes[2]==3);
 lock(2);sequence=ud_barrier_begin(2);C(sequence==4);enter(0,0xdd);idle_poll(0,1);idle_poll(1,1);idle_poll(2,1);finish(2,sequence);map_version[1]++;C(!ud_unlock(2));
 lock(0);C(ud_drain(0)==1);C(!ud_release(0,1));U old_retains=retains;C(select_user()==0&&retains==old_retains&&tlb_version[0][1]==map_version[1]);
 C(kicks[0]>3&&kicks[1]>3&&kicks[2]>3);return 0;
}
static int failure(const char*name){
 setup();lock(0);admit(0,1,0x200000,0x11);C(select_user()==0);enter(0,0x44);lock(0);C(ud_drain(0)==1);C(!ud_release(0,3));
 if(!strcmp(name,"legacy-fail")){U seq=ud_barrier_begin(0);C(seq==1);U before=legacy_polls;legacy_fault=1;C(ud_poll(0)==0x06090003&&ud_get(0,0)&&ud_get(13,0)==0&&legacy_polls==before+1);}
 else if(!strcmp(name,"flush-fail")){U seq=ud_barrier_begin(0);C(seq==1);flush_fault=1;C(ud_poll(0)==0x06090003&&ud_get(0,0)&&ud_get(13,0)==0);}
 else if(!strcmp(name,"timeout")){U seq=ud_barrier_begin(0);C(seq==1);C(ud_wait(0,seq,clock_tick+3)==0x06090005&&ud_get(0,0)&&ud_get(3,0)==seq&&ud_get(2,0)==1);}
 else if(!strcmp(name,"kick-fail")){kick_fault=1;C(ud_wake(0,0,1)==0x06090003&&ud_get(0,0));}
 else if(!strcmp(name,"switch-fail")){C(!ud_wake(0,0,1));U out=0;C(ud_select(0,&out)==1);C(!ud_unlock(0));switch_fault=1;C(ud_commit(0)==0x06090003&&ud_get(0,0));}
 else if(!strcmp(name,"invalid-return")){C(!ud_wake(0,0,1));frames[0].w[16]=2;U out=0;C(ud_select(0,&out)==1);C(!ud_unlock(0));C(ud_commit(0)==0x06090004&&ud_get(0,0));}
 else C(0);
 cpu=0;C(ud_lock(0,clock_tick+10)==0x06090004);return 0;
}
int main(int argc,char**argv){C(argc==2);if(!strcmp(argv[1],"normal"))normal();else failure(argv[1]);printf("user SMP native checks passed %u scenario=%s real-queue capture-ticket RETURNING retirement alltag IF0-lock-poll\n",(unsigned)checks,argv[1]);return 0;}
