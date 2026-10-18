#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef uint64_t U;
typedef struct {U w[25];} Frame;
typedef struct {U mode,token,inc,slot,cap_token,cap_inc,captured,requested,ack,capture,cap_xstate,returned,return_xstate,root,seen;} Cpu;
typedef struct {U token,inc,root,frame,xstate,retiring,retirement;} Process;
typedef struct {U ready,failed,lock,owner,online,sequence,barrier,expected,completed,kernel_root;void*engine;Cpu*cpus;Process*processes;U arena,bytes;} Domain;
typedef struct {U v[32];} Header;
typedef struct {U bottom,top,df_bottom,df_top,nmi_bottom,nmi_top,exception_bottom,exception_top;} Stacks;
extern U ABI ue_required(void),ue_init(U,U),ue_plan(U,U,U,const Stacks*,Header**),ue_bridge(U,U*),ue_lock(U),ue_unlock(U),ue_admit(U,U,U,U,U,U,U*),ue_project_one(U,U),ue_audit(void);
extern Domain* ABI ue_domain(void);
extern U ABI ue_poll(U),ue_cancel(U);
extern U ABI dong_user_smp_event(U,U,U),dong_user_smp_idle(U,U),dong_user_smp_return(U);
extern U ABI user_smp_prepare_tables(Header*);
extern void ABI user_smp_interrupt_frame(Frame*,const U*,U,U);
extern const U user_smp_entry_table[256];
extern U ABI user_smp_legacy_observe(Header*,U*,U,U,U);
U smp_tlb_mailboxes[16*8] __attribute__((aligned(64)));
static U checks,cpu,roots[16],clock_tick=1,flushes[16],kicks[16],timer[16],service_calls,restore_calls,mapping_failure,guard_failure,waiting[16],saved_xstate_calls;
static Header* headers[16];static U header_values[16];
static Frame frames[16] __attribute__((aligned(64)));
static unsigned char xstates[16][1024] __attribute__((aligned(64))),hardware[16][1024];
static U contexts[16*32] __attribute__((aligned(64)));
static Domain*d;
static void fail(const char*s,unsigned line){fprintf(stderr,"user CPL3 candidate oracle line %u: %s\n",line,s);exit(1);}
#define C(x) do{checks++;if(!(x))fail(#x,__LINE__);}while(0)
void ABI __dong_panic(void){fail("Dong panic",__LINE__);}
static void* arena(size_t n){void*p;
#ifdef _WIN32
 p=_aligned_malloc((n+4095)&~(size_t)4095,4096);
#else
 p=aligned_alloc(4096,(n+4095)&~(size_t)4095);
#endif
 C(p);memset(p,0xa5,n);return p;}
U ABI user_entry_mapped(U a,U n,U writable){C(a&&n&&writable==1);return !mapping_failure;}
U ABI user_entry_guard(U a){C(!(a&4095));return !guard_failure;}
U ABI user_smp_arch_if0(void){return 1;}
U ABI user_domain_legacy_poll(void){return 0;}
U ABI user_smp_arch_cpu(void){return cpu;}
U ABI user_smp_arch_root(void){return roots[cpu];}
U ABI user_smp_arch_try_lock(U*p){if(*p)return 0;*p=1;return 1;}
void ABI user_smp_arch_unlock(U*p){C(*p==1);*p=0;}
void ABI user_smp_arch_pause(void){U saved=cpu;for(unsigned i=0;i<3;i++){if(i!=saved&&d->cpus[i].ack<d->cpus[i].requested){cpu=i;if(d->cpus[i].mode==6){C(!ue_cancel(i));}C(d->cpus[i].mode==1||d->cpus[i].mode==4);C(ue_poll(i)==1);}}cpu=saved;}
U ABI user_smp_arch_clock(void){return clock_tick++;}
void ABI user_smp_arch_copy(U dst,U src,U bytes){C(bytes==200||bytes==1024);memcpy((void*)(uintptr_t)dst,(void*)(uintptr_t)src,(size_t)bytes);}
void ABI user_smp_arch_save(U pointer){C(d->cpus[cpu].mode==3&&roots[cpu]==0x100000);memcpy((void*)(uintptr_t)pointer,hardware[cpu],1024);saved_xstate_calls++;}
U ABI user_smp_arch_flush(U target){C(target==cpu&&roots[cpu]==0x100000);flushes[cpu]++;return 0;}
U ABI user_smp_arch_kick(U target){C(target<3);kicks[target]++;return 0;}
U ABI user_smp_arch_switch(U root,U tag,U retain){C(d->cpus[cpu].mode==6&&roots[cpu]==0x100000&&tag&&tag<=16&&retain<=1);roots[cpu]=root;return 0;}
U ABI user_smp_arch_validate(U frame,U root){Frame*f=(Frame*)(uintptr_t)frame;return f->w[15]>=0x10000&&f->w[17]>=0x10000&&(f->w[16]&0x202)==0x202&&!(f->w[16]&~(U)0x10ed7)&&f->w[18]==root&&!f->w[19]&&!f->w[20]&&!f->w[24];}
U ABI user_bridge_cpu(void){return cpu;}
U ABI user_bridge_clock(void){return clock_tick++;}
void ABI user_bridge_copy(U a,U b,U n){user_smp_arch_copy(a,b,n);}
void ABI user_bridge_restore(U pointer){C(pointer==headers[cpu]->v[21]);C(d->cpus[cpu].captured==1&&d->cpus[cpu].mode==4);restore_calls++;memset(hardware[cpu],0,1024);}
U ABI user_bridge_kick(U target){return user_smp_arch_kick(target);}
U ABI user_bridge_eoi(U who,U vector){C(who==cpu&&(vector==0x40||vector==0xf4||vector==0xff));return 0;}
U ABI user_bridge_timer(U who,U need){C(who==cpu&&need<2);timer[cpu]=need;return 0;}
U ABI user_bridge_service(U slot,U event,U frame){C(cpu==0&&d->owner==0&&d->lock==1&&d->cpus[0].mode==5);for(unsigned c=0;c<3;c++)C(flushes[c]>=2*service_calls+1);C(slot<16&&d->processes[slot].frame==frame);Frame*f=(Frame*)(uintptr_t)frame;
 C(event==257||event==7);C(f->w[14]==0x73||f->w[14]==0x66);C(xstates[slot][0]==0x7b);f->w[14]=0x1122334455667788ULL;waiting[slot]=(event==7);service_calls++;return 0;}
U ABI user_bridge_project(void){C(cpu==0&&d->owner==0&&d->lock==1);for(unsigned i=0;i<16;i++)C(!ue_project_one(i,waiting[i]));return 0;}
U ABI user_bridge_interrupt(U vector){C(cpu==0&&d->owner==0&&d->lock==1&&(vector==0x51||vector==0x5c||vector==0x60));return 0;}
/* Linked privileged paths remain unexecuted in this native oracle. */
U ABI user_smp_arch_enable_pcid(void){C(0);return 0;}
void ABI sched_xstate_save(U pointer){(void)pointer;C(0);}
void ABI sched_xstate_restore(U pointer){(void)pointer;C(0);}
U ABI dong_user_smp_service(U a,U b,U c){(void)a;(void)b;(void)c;C(0);return 0;}
U ABI dong_user_smp_project(void){C(0);return 0;}
static U read64(const unsigned char*p){U v;memcpy(&v,p,8);return v;}
static void tables(Header*h,const Stacks*s){const unsigned char*g=(void*)(uintptr_t)h->v[14],*t=(void*)(uintptr_t)h->v[15],*idt=(void*)(uintptr_t)h->v[16];
 C(read64(g)==0&&read64(g+8)==0x00af9b000000ffffULL&&read64(g+16)==0x00cf93000000ffffULL);C(read64(g+40)==0x00cff3000000ffffULL&&read64(g+48)==0x00affb000000ffffULL);C(g[29]==0x89&&g[24]==103&&g[25]==0&&g[30]==0&&read64(g+32)>>32==0);
 U base=(U)g[26]|((U)g[27]<<8)|((U)g[28]<<16)|((U)g[31]<<24)|((U)(uint32_t)read64(g+32)<<32);C(base==(U)(uintptr_t)t);
 C(read64(t+4)==s->top&&read64(t+36)==s->df_top&&read64(t+44)==s->nmi_top&&read64(t+52)==s->exception_top&&t[102]==104&&t[103]==0);
 for(unsigned i=0;i<256;i++){const unsigned char*p=idt+i*16;U addr=(U)p[0]|((U)p[1]<<8)|((U)p[6]<<16)|((U)p[7]<<24)|((U)(uint32_t)read64(p+8)<<32);C(addr==user_smp_entry_table[i]);C(p[2]==8&&p[3]==0&&p[4]==(i==8?1:i==2?2:0)&&p[5]==0x8e&&(read64(p+8)>>32)==0);}
}
static Stacks stack_for(unsigned id){U a=0xffffd40001000000ULL+(U)id*0x100000;return(Stacks){a,a+16384,a+0x10000,a+0x14000,a+0x20000,a+0x24000,a+0x30000,a+0x34000};}
static void setup(void){U n=ue_required();C(n==63040);C(!ue_init((U)(uintptr_t)arena((size_t)n),n));d=ue_domain();for(unsigned i=0;i<16;i++)roots[i]=0x100000;
 for(unsigned i=0;i<3;i++){void*a=arena(8192);Header*out=(Header*)(uintptr_t)0x55;Stacks s=stack_for(i);C(!ue_plan((U)(uintptr_t)a,i,(U)(uintptr_t)contexts,&s,&out));C(out==a&&out->v[25]==1&&out->v[10]==i&&out->v[8]==(U)(uintptr_t)&contexts[i*32]);tables(out,&s);headers[i]=out;header_values[i]=(U)(uintptr_t)out;out->v[25]=2;}
 C(!ue_bridge((U)(uintptr_t)arena(4096),header_values));
}
static void plan_controls(void){void*a=arena(8192);unsigned char before[8192];memcpy(before,a,8192);Header*out=(Header*)(uintptr_t)0x55;Stacks s=stack_for(4);
 mapping_failure=1;C(ue_plan((U)(uintptr_t)a,0,(U)(uintptr_t)contexts,&s,&out)!=0&&out==(Header*)(uintptr_t)0x55&&!memcmp(before,a,8192));mapping_failure=0;
 guard_failure=1;C(ue_plan((U)(uintptr_t)a,0,(U)(uintptr_t)contexts,&s,&out)!=0&&out==(Header*)(uintptr_t)0x55&&!memcmp(before,a,8192));guard_failure=0;
 s.nmi_bottom=s.bottom;s.nmi_top=s.top;C(ue_plan((U)(uintptr_t)a,0,(U)(uintptr_t)contexts,&s,&out)!=0&&!memcmp(before,a,8192));s=stack_for(4);
 C(ue_plan(d->arena,0,(U)(uintptr_t)contexts,&s,&out)!=0&&out==(Header*)(uintptr_t)0x55);
}
static void conversion(void){U raw[23];for(unsigned i=0;i<23;i++)raw[i]=0x1000000+i;Frame f;memset(&f,0xa5,sizeof f);raw[20]=0x10e16;user_smp_interrupt_frame(&f,raw,0x223000,73);
 for(unsigned i=0;i<15;i++)C(f.w[i]==raw[i+1]);C(f.w[15]==raw[18]&&f.w[16]==0x10e16&&f.w[17]==raw[21]&&f.w[18]==0x223000&&f.w[22]==73);C(!f.w[19]&&!f.w[20]&&!f.w[21]&&!f.w[23]&&!f.w[24]);
}
static void legacy(void){U*ctx=&contexts[32];ctx[0]=(U)(uintptr_t)ctx;ctx[1]=1;ctx[3]=4;ctx[26]=7;ctx[27]=3;U box[8]={9,0,1,8,0,0,0,0};
 C(!user_smp_legacy_observe(headers[1],box,0xf1,0,0)&&ctx[27]==7&&ctx[30]==1);C(headers[1]->v[26]==0);
 C(user_smp_legacy_observe(headers[1],box,0xf2,0,0)==1&&box[3]==8&&ctx[30]==1);
 C(!user_smp_legacy_observe(headers[1],box,0xf2,1,0)&&box[3]==9&&ctx[30]==2);
 box[0]=10;box[2]=2;C(!user_smp_legacy_observe(headers[1],box,0xf2,1,0xabcdef)&&box[3]==10&&box[5]==0xabcdef&&ctx[30]==3);
 ctx[3]=5;ctx[28]=11;ctx[29]=2;C(user_smp_legacy_observe(headers[1],box,0xf0,1,0)==1&&ctx[29]==2&&ctx[3]==5&&ctx[31]==0x06020003);ctx[3]=4;
}
static void admit(unsigned slot,U affinity){memset(&frames[slot],0,sizeof frames[slot]);frames[slot].w[15]=0x400000;frames[slot].w[16]=0x202;frames[slot].w[17]=0x70000000;frames[slot].w[18]=0x200000+slot*4096;U token=0;C(!ue_admit(slot,1,frames[slot].w[18],(U)(uintptr_t)&frames[slot],(U)(uintptr_t)xstates[slot],affinity,&token)&&token);}
static void start(unsigned who,unsigned slot){cpu=who;U f=dong_user_smp_idle(cpu,257);C(f==d->cpus[cpu].returned&&d->cpus[cpu].slot==slot);C(dong_user_smp_return(cpu)==1&&d->cpus[cpu].mode==2);memcpy(hardware[cpu],(void*)(uintptr_t)d->cpus[cpu].return_xstate,1024);}
static U event(unsigned who,U code,U vector){cpu=who;unsigned slot=(unsigned)d->cpus[cpu].slot;Frame f=frames[slot];f.w[14]=code;memset(hardware[cpu],0x7b,1024);roots[cpu]=0x100000;return dong_user_smp_event(cpu,(U)(uintptr_t)&f,vector);}
static void bridge_controls(void){cpu=0;C(!ue_lock(0));admit(0,2);C(!ue_unlock(0));start(1,0);C(timer[1]==0);
 C(!event(1,0x73,256)&&service_calls==0&&d->cpus[1].mode==1&&restore_calls==1&&saved_xstate_calls==1);C(xstates[0][0]==0x7b&&frames[0].w[14]==0x73);
 cpu=0;C(!dong_user_smp_idle(0,257)&&service_calls==1&&d->cpus[0].mode==1);C(frames[0].w[14]==0x1122334455667788ULL&&kicks[0]&&kicks[1]);start(1,0);C(timer[1]==0);
 U next=event(1,0x66,0x40);C(next==d->cpus[1].returned&&service_calls==1&&timer[1]==0);C(dong_user_smp_return(1)==1);
 cpu=0;C(!ue_lock(0));admit(1,2);C(!ue_unlock(0));next=event(1,0x66,0x40);C(next==d->cpus[1].returned&&d->cpus[1].slot==1&&timer[1]==1);C(dong_user_smp_return(1)==1);
 C(event(1,0x66,6)==d->cpus[1].returned&&service_calls==1&&d->cpus[1].slot==0);cpu=0;C(!dong_user_smp_idle(0,257)&&service_calls==2&&waiting[1]);C(!ue_audit()&&!d->failed);for(unsigned c=0;c<3;c++)C(flushes[c]==4);
 C(!dong_user_smp_idle(0,0x60)&&!d->failed); /* device broker owns exactly one EOI */
 /* Foreign CPU cannot use another header/capture ticket to mutate state. */
 cpu=2;U old=d->processes[0].frame;C(dong_user_smp_idle(1,257)==UINT64_MAX&&d->failed&&d->processes[0].frame==old);
}
int main(void){setup();plan_controls();conversion();legacy();bridge_controls();printf("CPL3 candidate native checks=%u perCPU-GDT-TSS-IDT frame-DF-RF deferred-BSP actual-queue xstate private-capture legacy-GS-pointee-alltag-before-ACK\n",(unsigned)checks);return 0;}
