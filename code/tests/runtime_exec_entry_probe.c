#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
typedef uint64_t U;
#define ROOT UINT64_C(0x04000000)
#define MAGIC UINT64_C(0x55534552534d5036)
#define WA UINT64_C(0xffffa90000002000)
#define CODE42 UINT64_C(0x0000c30000002ab8)
#define CODE43 UINT64_C(0x0000c30000002bb8)
#define CODE99 UINT64_C(0x0000c300000063b8)
#define PROBE UINT64_C(0x11110000)
#define AFTER UINT64_C(0x11110008)
#define GENERATION UINT64_C(91)
typedef struct {
 U cr2,r15,r14,r13,r12,r11,r10,r9,r8,rdi,rsi,rbp,rdx,rcx,rbx,rax;
 U vector,error,rip,cs,rflags,rsp,ss;
} Raw;
typedef struct {U cpu,root,cr0,cr4,rflags,header;} Snapshot;
typedef struct {U armed,consumed,cpu,sequence,root,virtual,rip,after;} Ticket;
typedef struct {U cpu,root,cr0,cr4,rflags,value,fault;} Sample;
typedef struct {
 U request,acknowledged,command,virtual,expected,count;Ticket ticket;
 Sample sample,called42,called43,denied42,denied43,serialized;U serialized_sequence;
} Reader;
typedef struct {
 U version,attempted,complete,poison,error_code,phase,state,root,physical,online,root_count;
 U barriers,sequence,action_sequence,command,expected,ack_mask,held,unmapped,receipts_consumed;
 U tables_before,tables_after,aliases,readers_pointer,roots_pointer;
} Report;
typedef struct {void *space;U identity,generation;} Root;
typedef struct {
 U mode,token,incarnation,slot,captured_token,captured_incarnation,captured,requested,acknowledged;
 U capture,capture_xstate,returned,return_xstate,return_root;void *seen;
} Cpu;
typedef struct {
 U ready,failed,lock,owner,online,sequence,barrier,expected,completed,kernel_root;
 void *engine;Cpu *cpus;void *processes;U arena,bytes;
} Domain;
typedef struct {
 U kernel_stack,user_stack,continuation,root_frame,original_cr3,syscalls,busy,result;
 U smp;Domain *domain;U logical_id,contexts,context_count,pcid_enabled;
 U gdt,tss,idt,stack_bottom,df_top,nmi_top,exception_top,kernel_xstate;
 U capture,returned,return_xstate,ready,last_error,event,raw_frame,deadline_ticks,tsc_hz,timer_hz;
} Header;
typedef struct __attribute__((aligned(64))) {
 U version,commit,cpu,payload,header,root,generation,frame,stack_bottom,stack_top;
 U context,domain,reader,request,acknowledged,action_sequence,command,virtual,expected,after;
 Raw raw;Ticket ticket_before,ticket_after;U reserved[5];
} RawTrace;
/* Only the independently described prefix is accessed as a C structure. */
typedef struct {
 Report report;Domain *domain;void *space,*allocator;U cookie,check,hardware,action;
 U deadline,ready,busy,payload,probe_rip,probe_after,anchor_a,anchor_b,anchor_pt;Root roots[16];
} Prefix;
typedef U (DG *Callback)(Header*,U,const Raw*,U);
extern U DG ree_size(U),ree_layout(U,U,U),ree_pointer(void*,U),ree_callback(void);
extern void DG ree_prepare(void*,Domain*,U,U);
extern U DG ree_bind(void*,Domain*,Header**,U,U,Callback,const Snapshot*);
extern U DG ree_dispatch(Header*,U,const Raw*,U);
extern U DG ree_trace_bind(void*,RawTrace*,U,U,U,Header**,U),ree_pool(void*,void*,void*,U,U);
extern void DG ree_trace_prepare(void*,void*,void*);
extern U DG user_smp_exec_register(Callback,U,U,U,const U*,U);
extern U DG user_smp_exec_registration(U);
extern U DG user_smp_exec_apply(Header*,U,Raw*,U,U);
_Static_assert(sizeof(Raw)==184,"independent raw ABI");
_Static_assert(sizeof(Header)==256,"independent GS header ABI");
_Static_assert(sizeof(Snapshot)==48,"independent trusted snapshot ABI");
_Static_assert(offsetof(Raw,rip)==144,"saved RIP ABI");
_Static_assert(offsetof(Raw,rsp)==168,"hardware saved RSP ABI");
_Static_assert(sizeof(RawTrace)==512&&_Alignof(RawTrace)==64,"independent trace ABI");
_Static_assert(offsetof(RawTrace,raw)==160&&offsetof(RawTrace,ticket_before)==344,"pre-ASM trace ABI");
_Static_assert(offsetof(RawTrace,ticket_after)==408&&offsetof(RawTrace,reserved)==472,"ticket trace ABI");
_Static_assert(offsetof(Header,exception_top)==160,"native stack switch Header ABI");

/* SysV on both ELF and COFF. This calls the pure native gate on the owned
 * exception arena; it executes neither the hardware entry nor IRET. The saved
 * host RSP lives above the callee's call frame and r12 is restored exactly. */
static U DG __attribute__((naked,noinline)) trace_stack_apply(
 Header *h __attribute__((unused)),U root __attribute__((unused)),Raw *raw __attribute__((unused)),
 U generation __attribute__((unused)),U swapped __attribute__((unused))){
 __asm__ volatile("push %r12\n\tmov %rsp,%r12\n\tmov 160(%rdi),%rsp\n\tsub $16,%rsp\n\t"
                  "mov %r12,(%rsp)\n\tcall user_smp_exec_apply\n\tmov (%rsp),%rsp\n\tpop %r12\n\tret");
}

typedef struct {unsigned char *allocation,*p,*base,*before;size_t n;} Guard;
static Guard guards_list[256];static unsigned guard_count,online_count=2;
static void *context;static Prefix *prefix;static Report *report;static Reader *readers;static Root *roots;
static Domain *domain;static Cpu *cpus;static Header **headers,*header[16],*unknown_header;
static Snapshot *snapshot;static U *slots;static unsigned char *stacks[16][4];static Raw *frames[16];
static RawTrace *trace_records;static unsigned char *trace_storage;
static void *trace_spaces[3],*trace_tables[3],*trace_meta[3],*trace_allocator;
#define TRACE_BYTES UINT64_C(65536)
static U checks,callback_calls,nested_calls,continuation_mode;static const char *where="setup";
static U root_arg,generation_arg,gs_arg;static Header *header_arg;static Raw *raw_arg;
static int reject(const char *why){
 fprintf(stderr,"runtime EXEC entry oracle case=%s check=%s; no guest executed\n",where,why);return 1;
}
#define REQUIRE(x) do { ++checks;if(!(x)){return reject(#x);} } while(0)
static void *guard(size_t n,size_t alignment){
 unsigned char *allocation=calloc(n+alignment+128,1);
 if(!allocation||guard_count==256){exit(97);}
 uintptr_t p=((uintptr_t)allocation+64+alignment-1)&~(uintptr_t)(alignment-1);
 memset((void*)(p-64),0xa5,64);memset((void*)(p+n),0x5a,64);
 Guard *g=&guards_list[guard_count++];*g=(Guard){allocation,(unsigned char*)p,malloc(n),malloc(n),n};
 if(!g->base||!g->before){exit(97);}return (void*)p;
}
static int intact(void){
 for(unsigned i=0;i<guard_count;i++){Guard *g=&guards_list[i];for(unsigned j=0;j<64;j++){
  if(g->p[-64+(int)j]!=0xa5||g->p[g->n+j]!=0x5a){return 0;}
 }}return 1;
}
static void remember_base(void){for(unsigned i=0;i<guard_count;i++){memcpy(guards_list[i].base,guards_list[i].p,guards_list[i].n);}}
static void restore_base(void){for(unsigned i=0;i<guard_count;i++){memcpy(guards_list[i].p,guards_list[i].base,guards_list[i].n);}}
static void remember_before(void){for(unsigned i=0;i<guard_count;i++){memcpy(guards_list[i].before,guards_list[i].p,guards_list[i].n);}}
static int unchanged(void){
 for(unsigned i=0;i<guard_count;i++){if(memcmp(guards_list[i].before,guards_list[i].p,guards_list[i].n)){return 0;}}
 return intact();
}
static int exception_scratch(unsigned cpu){
 /* Only this exact allocated stack interior is scratch. Its canaries and all
  * persistent Raw/ticket/trace/Context bytes remain independently checked. */
 REQUIRE(intact());
 for(unsigned i=0;i<guard_count;i++){
  Guard *g=&guards_list[i];if(g->p==stacks[cpu][3]){
   REQUIRE(g->n==16384&&header[cpu]->exception_top==(U)(uintptr_t)g->p+g->n);
   memcpy(g->before,g->p,g->n);return 0;
  }
 }return reject("exception scratch arena not owned");
}
static void expect_word(const void *address,U value){
 uintptr_t a=(uintptr_t)address;
 for(unsigned i=0;i<guard_count;i++){Guard *g=&guards_list[i];uintptr_t b=(uintptr_t)g->p;
  if(a>=b&&a-b<=g->n-sizeof(value)){memcpy(g->before+(a-b),&value,sizeof(value));return;}
 }exit(96);
}
static void flip_word(void *object,size_t offset,U bits){
 U value;memcpy(&value,(unsigned char*)object+offset,sizeof(value));value^=bits;
 memcpy((unsigned char*)object+offset,&value,sizeof(value));
}
static void cleanup(void){
 for(unsigned i=0;i<guard_count;i++){free(guards_list[i].base);free(guards_list[i].before);free(guards_list[i].allocation);}
}
static U DG rogue(Header *h,U root,const Raw *raw,U generation){
 (void)h;(void)root;(void)raw;(void)generation;callback_calls++;return AFTER;
}
static U DG continuation_oracle(Header *h,U root,const Raw *raw,U generation){
 (void)h;(void)root;(void)raw;(void)generation;callback_calls++;
 return continuation_mode==0?0:continuation_mode==1?AFTER+8:AFTER;
}
static Callback actual_callback(void){return (Callback)(uintptr_t)ree_callback();}
U DG runtime_exec_probe_label(U which){return which==0?PROBE:which==1?AFTER:0;}
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const unsigned char *file,U n){
 fprintf(stderr,"unexpected Dong panic %u:%u %.*s\n",kind,line,(int)n,file);exit(99);
}
/* Host tests link the complete production entry object. None of these hardware
 * or legacy-entry boundaries may be executed, even accidentally. */
static void forbidden(const char *name){fprintf(stderr,"privileged/legacy host boundary called: %s\n",name);abort();}
U DG dong_user_smp_event(void){forbidden("dong_user_smp_event");return 0;}
U DG dong_user_smp_return(void){forbidden("dong_user_smp_return");return 0;}
U DG dong_user_smp_idle(void){forbidden("dong_user_smp_idle");return 0;}
void DG sched_xstate_save(U p){(void)p;forbidden("sched_xstate_save");}
void DG sched_xstate_restore(U p){(void)p;forbidden("sched_xstate_restore");}
U DG user_smp_arch_enable_pcid(void){forbidden("user_smp_arch_enable_pcid");return 0;}
U DG user_smp_arch_if0(void){forbidden("user_smp_arch_if0");return 0;}
U DG user_smp_arch_cpu(void){forbidden("user_smp_arch_cpu");return 0;}
U DG user_smp_arch_root(void){forbidden("user_smp_arch_root");return 0;}
U DG user_smp_arch_try_lock(U *p){(void)p;forbidden("user_smp_arch_try_lock");return 0;}
void DG user_smp_arch_unlock(U *p){(void)p;forbidden("user_smp_arch_unlock");}
void DG user_smp_arch_pause(void){forbidden("user_smp_arch_pause");}
U DG user_smp_arch_clock(void){forbidden("user_smp_arch_clock");return 0;}
void DG user_smp_arch_copy(U d,U s,U n){(void)d;(void)s;(void)n;forbidden("user_smp_arch_copy");}
void DG user_smp_arch_save(U p){(void)p;forbidden("user_smp_arch_save");}
U DG user_smp_arch_flush(U cpu){(void)cpu;forbidden("user_smp_arch_flush");return 1;}
U DG user_smp_arch_kick(U cpu){(void)cpu;forbidden("user_smp_arch_kick");return 1;}
U DG user_smp_arch_switch(U r,U t,U k){(void)r;(void)t;(void)k;forbidden("user_smp_arch_switch");return 1;}
U DG user_smp_arch_validate(U f,U r){(void)f;(void)r;forbidden("user_smp_arch_validate");return 0;}
U DG user_domain_legacy_poll(void){forbidden("user_domain_legacy_poll");return 1;}

#define O(t,f) offsetof(t,f)
static int layout(void){
 static const size_t raw[]={O(Raw,cr2),O(Raw,r15),O(Raw,r14),O(Raw,r13),O(Raw,r12),O(Raw,r11),O(Raw,r10),O(Raw,r9),O(Raw,r8),O(Raw,rdi),O(Raw,rsi),O(Raw,rbp),O(Raw,rdx),O(Raw,rcx),O(Raw,rbx),O(Raw,rax),O(Raw,vector),O(Raw,error),O(Raw,rip),O(Raw,cs),O(Raw,rflags),O(Raw,rsp),O(Raw,ss)};
 static const size_t hdr[]={O(Header,kernel_stack),O(Header,user_stack),O(Header,continuation),O(Header,root_frame),O(Header,original_cr3),O(Header,syscalls),O(Header,busy),O(Header,result),O(Header,smp),O(Header,domain),O(Header,logical_id),O(Header,contexts),O(Header,context_count),O(Header,pcid_enabled),O(Header,gdt),O(Header,tss),O(Header,idt),O(Header,stack_bottom),O(Header,df_top),O(Header,nmi_top),O(Header,exception_top),O(Header,kernel_xstate),O(Header,capture),O(Header,returned),O(Header,return_xstate),O(Header,ready),O(Header,last_error),O(Header,event),O(Header,raw_frame),O(Header,deadline_ticks),O(Header,tsc_hz),O(Header,timer_hz)};
 static const size_t snap[]={O(Snapshot,cpu),O(Snapshot,root),O(Snapshot,cr0),O(Snapshot,cr4),O(Snapshot,rflags),O(Snapshot,header)};
 static const size_t pre[]={O(Prefix,report),O(Prefix,domain),O(Prefix,space),O(Prefix,allocator),O(Prefix,cookie),O(Prefix,check),O(Prefix,hardware),O(Prefix,action),O(Prefix,deadline),O(Prefix,ready),O(Prefix,busy),O(Prefix,payload),O(Prefix,probe_rip),O(Prefix,probe_after),O(Prefix,anchor_a),O(Prefix,anchor_b),O(Prefix,anchor_pt),O(Prefix,roots)};
 static const size_t reader[]={O(Reader,request),O(Reader,acknowledged),O(Reader,command),O(Reader,virtual),O(Reader,expected),O(Reader,count),O(Reader,ticket),O(Reader,sample),O(Reader,called42),O(Reader,called43),O(Reader,denied42),O(Reader,denied43),O(Reader,serialized),O(Reader,serialized_sequence)};
 static const size_t root[]={O(Root,space),O(Root,identity),O(Root,generation)};
 static const size_t rep[]={O(Report,version),O(Report,attempted),O(Report,complete),O(Report,poison),O(Report,error_code),O(Report,phase),O(Report,state),O(Report,root),O(Report,physical),O(Report,online),O(Report,root_count),O(Report,barriers),O(Report,sequence),O(Report,action_sequence),O(Report,command),O(Report,expected),O(Report,ack_mask),O(Report,held),O(Report,unmapped),O(Report,receipts_consumed),O(Report,tables_before),O(Report,tables_after),O(Report,aliases),O(Report,readers_pointer),O(Report,roots_pointer)};
 static const size_t cpu[]={O(Cpu,mode),O(Cpu,token),O(Cpu,incarnation),O(Cpu,slot),O(Cpu,captured_token),O(Cpu,captured_incarnation),O(Cpu,captured),O(Cpu,requested),O(Cpu,acknowledged),O(Cpu,capture),O(Cpu,capture_xstate),O(Cpu,returned),O(Cpu,return_xstate),O(Cpu,return_root),O(Cpu,seen)};
 static const size_t dom[]={O(Domain,ready),O(Domain,failed),O(Domain,lock),O(Domain,owner),O(Domain,online),O(Domain,sequence),O(Domain,barrier),O(Domain,expected),O(Domain,completed),O(Domain,kernel_root),O(Domain,engine),O(Domain,cpus),O(Domain,processes),O(Domain,arena),O(Domain,bytes)};
 static const size_t ticket[]={O(Ticket,armed),O(Ticket,consumed),O(Ticket,cpu),O(Ticket,sequence),O(Ticket,root),O(Ticket,virtual),O(Ticket,rip),O(Ticket,after)};
 const size_t *sets[]={raw,hdr,snap,pre,reader,root,rep,cpu,dom,ticket};
 const size_t counts[]={23,32,6,18,14,3,25,15,15,8};
 const U addresses[]={(U)(uintptr_t)frames[0],(U)(uintptr_t)header[0],(U)(uintptr_t)snapshot,(U)(uintptr_t)context,(U)(uintptr_t)readers,(U)(uintptr_t)roots,(U)(uintptr_t)report,(U)(uintptr_t)cpus,(U)(uintptr_t)domain,(U)(uintptr_t)&readers[0].ticket};
 const size_t sizes[]={sizeof(Raw),sizeof(Header),sizeof(Snapshot),0,sizeof(Reader),sizeof(Root),sizeof(Report),sizeof(Cpu),sizeof(Domain),sizeof(Ticket)};
 for(unsigned i=0;i<10;i++){
  if(i!=3){REQUIRE(ree_size(i)==sizes[i]);}
  for(size_t j=0;j<counts[i];j++){REQUIRE(ree_layout(addresses[i],i,j)==sets[i][j]);}
 }
 REQUIRE(ree_size(3)>=sizeof(Prefix)+16*sizeof(Reader)&&(ree_size(3)&63)==0);
 REQUIRE(ree_layout((U)(uintptr_t)context,3,18)==(U)((unsigned char*)readers-(unsigned char*)context));
 REQUIRE((unsigned char*)readers>=(unsigned char*)context+sizeof(Prefix));
 REQUIRE((unsigned char*)(readers+16)<=(unsigned char*)context+ree_size(3));
 REQUIRE(roots==prefix->roots&&report==&prefix->report);
 return 0;
}
static void arguments(unsigned cpu){
 header_arg=header[cpu];raw_arg=frames[cpu];root_arg=ROOT;generation_arg=GENERATION;gs_arg=0;
}
static void raw_frame(unsigned cpu,U ss){
 Raw *f=frames[cpu];
 for(unsigned i=0;i<23;i++){
  U value=UINT64_C(0x6000000000000000)+((U)i<<32)+cpu;
  memcpy((unsigned char*)f+i*sizeof(value),&value,sizeof(value));
 }
 f->cr2=WA;f->vector=14;f->error=3;f->rip=PROBE;f->cs=8;
 f->rflags=UINT64_C(0x10402);f->rsp=(U)(uintptr_t)f+sizeof(*f)+512;f->ss=ss;
}
static int setup(unsigned count){
 online_count=count;
 REQUIRE(ree_size(0)==sizeof(Raw)&&ree_size(1)==sizeof(Header)&&ree_size(2)==sizeof(Snapshot));
 context=guard((size_t)ree_size(3),64);prefix=context;
 domain=guard(sizeof(*domain),64);cpus=guard(16*sizeof(*cpus),64);
 headers=guard(16*sizeof(*headers),64);snapshot=guard(sizeof(*snapshot),64);
 slots=guard(16*4*sizeof(*slots),64);
 unsigned char *contexts=guard(16*256,64),*captures=guard(count*2048,64);
 domain->ready=1;domain->lock=1;domain->owner=0;domain->online=(UINT64_C(1)<<count)-1;
 domain->kernel_root=ROOT;domain->cpus=cpus;domain->arena=(U)(uintptr_t)domain;domain->bytes=sizeof(*domain);
 for(unsigned i=0;i<count;i++){
  cpus[i].mode=i?4:5;cpus[i].slot=16;cpus[i].capture=(U)(uintptr_t)(captures+i*2048);
  cpus[i].returned=cpus[i].capture+256;cpus[i].capture_xstate=cpus[i].capture+512;cpus[i].return_xstate=cpus[i].capture+1024;
  header[i]=guard(8192,64);headers[i]=header[i];
  for(unsigned j=0;j<4;j++){stacks[i][j]=guard(16384,4096);}
  Header *h=header[i];U address=(U)(uintptr_t)h;
  h->kernel_stack=(U)(uintptr_t)stacks[i][0]+16384;h->stack_bottom=(U)(uintptr_t)stacks[i][0];
  h->continuation=address;h->root_frame=cpus[i].returned;h->original_cr3=ROOT;h->busy=1;h->result=MAGIC;
  h->smp=(U)(uintptr_t)(contexts+i*256);h->domain=domain;h->logical_id=i;
  h->contexts=(U)(uintptr_t)contexts;h->context_count=count;h->pcid_enabled=1;
  h->gdt=address+256;h->tss=address+320;h->idt=address+512;h->kernel_xstate=address+4608;
  h->df_top=(U)(uintptr_t)stacks[i][1]+16384;h->nmi_top=(U)(uintptr_t)stacks[i][2]+16384;
  h->exception_top=(U)(uintptr_t)stacks[i][3]+16384;h->capture=cpus[i].capture;
  h->returned=cpus[i].returned;h->return_xstate=cpus[i].return_xstate;h->ready=2;
  h->deadline_ticks=1000000;h->tsc_hz=1000000000;h->timer_hz=1000000;
  frames[i]=(Raw*)(void*)(stacks[i][0]+8192);raw_frame(i,i?16:0);
  slots[i*4]=address;slots[i*4+1]=h->stack_bottom;slots[i*4+2]=h->kernel_stack;slots[i*4+3]=h->exception_top;
 }
 unknown_header=guard(8192,64);memcpy(unknown_header,header[0],sizeof(*unknown_header));
 *snapshot=(Snapshot){0,ROOT,UINT64_C(0x80010001),32|UINT64_C(1)<<17,2,(U)(uintptr_t)header[0]};
 ree_prepare(context,domain,PROBE,AFTER);
 report=(Report*)(uintptr_t)ree_pointer(context,0);readers=(Reader*)(uintptr_t)ree_pointer(context,1);roots=(Root*)(uintptr_t)ree_pointer(context,2);
 roots[0]=(Root){guard(64,64),7,101};roots[1]=(Root){guard(64,64),8,102};
 REQUIRE(!layout());REQUIRE(intact());remember_base();arguments(0);return 0;
}
static U bind_actual(Callback callback,U generation,U count,void *c,Domain *d,const Snapshot *s){
 return ree_bind(c,d,headers,count,generation,callback,s);
}
static int registration_empty(void){
 for(U i=0;i<6;i++){REQUIRE(user_smp_exec_registration(i)==0);}
 for(U i=16;i<80;i++){REQUIRE(user_smp_exec_registration(i)==0);}
 for(U i=80;i<96;i++){REQUIRE(user_smp_exec_registration(i)==0);}
 return 0;
}
static int reject_apply(void){
 remember_before();U result=user_smp_exec_apply(header_arg,root_arg,raw_arg,generation_arg,gs_arg);
 REQUIRE(result==0);REQUIRE(unchanged());REQUIRE(callback_calls==0);
 REQUIRE(user_smp_exec_registration(80)==0&&user_smp_exec_registration(81)==0);return 0;
}
static const char *bad_bind_cases[]={
 "snapshot-cpu","snapshot-tag","snapshot-pge","snapshot-no-pae","snapshot-no-wp","snapshot-cache-disabled","snapshot-if","snapshot-header",
 "ready","busy","attempted","poison","version","root","online","root-count","context-domain","probe","after",
 "domain-ready","domain-failed","domain-lock","domain-owner","domain-online","domain-root","domain-mode","domain-barrier",
 "header-ready","header-magic","header-domain","header-root","header-id","header-gdt","header-tss","header-idt","header-xstate",
 "header-contexts","header-smp","header-count","header-capture","header-returned","header-return-xstate","kernel-align","kernel-short",
 "df-align","nmi-align","exception-align","exception-overlap","stack-overlap-context","stack-overlap-header","stack-overlap-domain","stack-overlap-cpus",
 "offline-header","null-header","duplicate-header","shared-contexts","count","generation","null-callback","rogue-callback","null-context","unaligned-context","null-domain","null-snapshot"
};
static int bad_bind(unsigned kind){
 restore_base();where=bad_bind_cases[kind];Callback callback=actual_callback();U generation=GENERATION,count=16;
 void *c=context;Domain *d=domain;const Snapshot *s=snapshot;
 #define CASE(n) (!strcmp(where,(n)))
 if(CASE("snapshot-cpu")){snapshot->cpu=1;}else if(CASE("snapshot-tag")){snapshot->root|=17;}
 else if(CASE("snapshot-pge")){snapshot->cr4|=128;}else if(CASE("snapshot-no-pae")){snapshot->cr4&=~UINT64_C(32);}
 else if(CASE("snapshot-no-wp")){snapshot->cr0&=~UINT64_C(65536);}else if(CASE("snapshot-cache-disabled")){snapshot->cr0|=UINT64_C(1)<<30;}
 else if(CASE("snapshot-if")){snapshot->rflags|=512;}else if(CASE("snapshot-header")){snapshot->header=(U)(uintptr_t)header[1];}
 else if(CASE("ready")){prefix->ready=0;}else if(CASE("busy")){prefix->busy=1;}
 else if(CASE("attempted")){report->attempted=1;}else if(CASE("poison")){report->poison=1;}
 else if(CASE("version")){report->version=2;}else if(CASE("root")){report->root|=17;}
 else if(CASE("online")){report->online=1;}else if(CASE("root-count")){report->root_count=17;}
 else if(CASE("context-domain")){prefix->domain=NULL;}else if(CASE("probe")){prefix->probe_rip=0;}
 else if(CASE("after")){prefix->probe_after=PROBE;}
 else if(CASE("domain-ready")){domain->ready=0;}else if(CASE("domain-failed")){domain->failed=1;}
 else if(CASE("domain-lock")){domain->lock=0;}else if(CASE("domain-owner")){domain->owner=1;}
 else if(CASE("domain-online")){domain->online=2;report->online=2;}else if(CASE("domain-root")){domain->kernel_root|=17;}
 else if(CASE("domain-mode")){cpus[0].mode=4;}else if(CASE("domain-barrier")){domain->barrier=1;}
 else if(CASE("header-ready")){header[0]->ready=1;}else if(CASE("header-magic")){header[0]->result=0;}
 else if(CASE("header-domain")){header[0]->domain=NULL;}else if(CASE("header-root")){header[0]->original_cr3|=17;}
 else if(CASE("header-id")){header[1]->logical_id=0;}else if(CASE("header-gdt")){header[0]->gdt+=8;}
 else if(CASE("header-tss")){header[0]->tss+=8;}else if(CASE("header-idt")){header[0]->idt+=8;}
 else if(CASE("header-xstate")){header[0]->kernel_xstate+=64;}else if(CASE("header-contexts")){header[0]->contexts+=8;}
 else if(CASE("header-smp")){header[1]->smp+=256;}else if(CASE("header-count")){header[0]->context_count=0;}
 else if(CASE("header-capture")){header[0]->capture+=8;}else if(CASE("header-returned")){header[0]->returned+=8;}
 else if(CASE("header-return-xstate")){header[0]->return_xstate+=64;}else if(CASE("kernel-align")){header[0]->kernel_stack+=8;}
 else if(CASE("kernel-short")){header[0]->stack_bottom=header[0]->kernel_stack-4096;}
 else if(CASE("df-align")){header[0]->df_top+=8;}else if(CASE("nmi-align")){header[0]->nmi_top+=8;}
 else if(CASE("exception-align")){header[0]->exception_top+=8;}else if(CASE("exception-overlap")){header[0]->exception_top=header[0]->kernel_stack;}
 else if(CASE("stack-overlap-context")){header[0]->stack_bottom=(U)(uintptr_t)context&~UINT64_C(4095);header[0]->kernel_stack=header[0]->stack_bottom+16384;}
 else if(CASE("stack-overlap-header")){header[0]->stack_bottom=(U)(uintptr_t)header[0]&~UINT64_C(4095);header[0]->kernel_stack=header[0]->stack_bottom+16384;}
 else if(CASE("stack-overlap-domain")){header[0]->stack_bottom=(U)(uintptr_t)domain&~UINT64_C(4095);header[0]->kernel_stack=header[0]->stack_bottom+16384;}
 else if(CASE("stack-overlap-cpus")){header[0]->stack_bottom=(U)(uintptr_t)cpus&~UINT64_C(4095);header[0]->kernel_stack=header[0]->stack_bottom+16384;}
 else if(CASE("offline-header")){headers[2]=unknown_header;}else if(CASE("null-header")){headers[1]=NULL;}
 else if(CASE("duplicate-header")){headers[1]=headers[0];}else if(CASE("shared-contexts")){header[1]->contexts+=256;header[1]->smp+=256;}
 else if(CASE("count")){count=15;}else if(CASE("generation")){generation=0;}
 else if(CASE("null-callback")){callback=NULL;}else if(CASE("rogue-callback")){callback=rogue;}
 else if(CASE("null-context")){c=NULL;}else if(CASE("unaligned-context")){c=(unsigned char*)context+8;}
 else if(CASE("null-domain")){d=NULL;}else if(CASE("null-snapshot")){s=NULL;}
 else{return reject("bad bind case not implemented");}
 #undef CASE
 remember_before();REQUIRE(bind_actual(callback,generation,count,c,d,s)!=0);REQUIRE(unchanged());
 REQUIRE(callback_calls==0);REQUIRE(!registration_empty());return 0;
}
static int bad_binds(const char *single){
 for(unsigned i=0;i<sizeof(bad_bind_cases)/sizeof(bad_bind_cases[0]);i++){
  if(!single||!strcmp(single,bad_bind_cases[i])){if(bad_bind(i)){return 1;}if(single){return 0;}}
 }
 if(single){return reject("unknown bad-bind case");}restore_base();return 0;
}
static void active(void){
 prefix->busy=1;prefix->payload=CODE42;report->attempted=1;report->command=4;
 report->phase=5;report->state=2;report->action_sequence=37;
 for(unsigned i=0;i<online_count;i++){
  Reader *r=&readers[i];r->request=37;r->acknowledged=36;r->command=4;r->virtual=WA;r->expected=CODE99;
  r->ticket=(Ticket){1,0,i,37,ROOT,WA,PROBE,AFTER};raw_frame(i,i?16:0);
 }
 arguments(0);
}
static int registered(void){
 REQUIRE(user_smp_exec_registration(0)!=0);
 REQUIRE(user_smp_exec_registration(1)==ree_callback()&&user_smp_exec_registration(2)==PROBE);
 REQUIRE(user_smp_exec_registration(3)==AFTER&&user_smp_exec_registration(4)==GENERATION&&user_smp_exec_registration(5)==3);
 for(U i=0;i<64;i++){REQUIRE(user_smp_exec_registration(16+i)==slots[i]);}
 for(U i=80;i<96;i++){REQUIRE(user_smp_exec_registration(i)==0);}return 0;
}
static int success(unsigned cpu,U ss){
 restore_base();arguments(cpu);where=cpu?"success-ap":"success-bsp";raw_frame(cpu,ss);
 if(cpu){
  /* Ordinary entry bookkeeping may evolve after registration. */
  header[cpu]->user_stack=0x70000;header[cpu]->syscalls=19;header[cpu]->busy=0;
  header[cpu]->last_error=41;header[cpu]->event=14;header[cpu]->raw_frame=(U)(uintptr_t)raw_arg;
  raw_arg->rsp=header[cpu]->kernel_stack;
 }
 remember_before();U result=user_smp_exec_apply(header_arg,root_arg,raw_arg,generation_arg,gs_arg);
 REQUIRE(result==AFTER);
 /* The oracle modifies its expected byte images, never the production buffers. */
 expect_word(&raw_arg->rip,AFTER);expect_word(&readers[cpu].ticket.armed,0);expect_word(&readers[cpu].ticket.consumed,1);
 REQUIRE(unchanged());REQUIRE(raw_arg->ss==ss&&readers[cpu].acknowledged==36);
 REQUIRE(user_smp_exec_registration(80+cpu)==0);
 where="consumed-replay";remember_before();
 REQUIRE(user_smp_exec_apply(header_arg,root_arg,raw_arg,generation_arg,gs_arg)==0);REQUIRE(unchanged());
 raw_arg->rip=PROBE;remember_before();REQUIRE(user_smp_exec_apply(header_arg,root_arg,raw_arg,generation_arg,gs_arg)==0);
 REQUIRE(unchanged());return 0;
}
static int success_at_stack_margin(void){
 restore_base();arguments(0);where="success-stack-margin";
 Raw value=*frames[0];raw_arg=(Raw*)(void*)(stacks[0][0]+16);memcpy(raw_arg,&value,sizeof(value));
 raw_arg->rsp=(U)(uintptr_t)raw_arg+sizeof(*raw_arg);
 remember_before();REQUIRE(user_smp_exec_apply(header_arg,root_arg,raw_arg,generation_arg,gs_arg)==AFTER);
 expect_word(&raw_arg->rip,AFTER);expect_word(&readers[0].ticket.armed,0);expect_word(&readers[0].ticket.consumed,1);
 REQUIRE(unchanged());REQUIRE(readers[0].acknowledged==36&&user_smp_exec_registration(80)==0);return 0;
}
static int rejections(void){
 /* Each trial starts from an armed, otherwise valid ticket. The complete
  * Context, both stack/header arenas, Domain and all guards are compared. */
 for(unsigned field=0;field<8;field++){
  restore_base();arguments(0);where="ticket-field";flip_word(&readers[0].ticket,field*sizeof(U),1);
  if(reject_apply()){return 1;}
 }
 const size_t fault_fields[]={O(Raw,cr2),O(Raw,vector),O(Raw,error),O(Raw,rip),O(Raw,cs)};
 for(unsigned i=0;i<sizeof(fault_fields)/sizeof(fault_fields[0]);i++){
  restore_base();arguments(0);where="raw-fault-field";
  flip_word(raw_arg,fault_fields[i],1);if(reject_apply()){return 1;}
 }
 restore_base();arguments(0);where="raw-if";raw_arg->rflags|=512;if(reject_apply()){return 1;}
 U *fields[]={&prefix->ready,&prefix->busy,&report->attempted,&report->version,&report->root,&report->online,&report->root_count,&report->physical,
  &prefix->probe_rip,&prefix->probe_after,&report->command,&report->action_sequence,&report->phase,&report->state,
  &readers[0].request,&readers[0].command,&readers[0].virtual,&readers[0].expected};
 for(unsigned i=0;i<sizeof(fields)/sizeof(fields[0]);i++){
  restore_base();arguments(0);where="context-reader-binding";*fields[i]^=1;if(reject_apply()){return 1;}
 }
 U *zero_fields[]={&report->poison,&report->complete,&report->error_code,&domain->failed,&domain->barrier};
 for(unsigned i=0;i<sizeof(zero_fields)/sizeof(zero_fields[0]);i++){
  restore_base();arguments(0);where="healthy-state";*zero_fields[i]=1;if(reject_apply()){return 1;}
 }
 restore_base();arguments(0);where="ack-already-published";readers[0].acknowledged=37;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="payload";prefix->payload=CODE99;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="context-domain";prefix->domain=NULL;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="context-space";prefix->space=unknown_header;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="context-allocator";prefix->allocator=unknown_header;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="domain-cpus";domain->cpus=cpus+1;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="domain-engine";domain->engine=unknown_header;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="domain-processes";domain->processes=unknown_header;if(reject_apply()){return 1;}
 U *domain_fields[]={&domain->ready,&domain->lock,&domain->owner,&domain->online,&domain->kernel_root,&domain->arena,&domain->bytes};
 for(unsigned i=0;i<sizeof(domain_fields)/sizeof(domain_fields[0]);i++){
  restore_base();arguments(0);where="domain-binding";*domain_fields[i]^=1;if(reject_apply()){return 1;}
 }
 const U invalid_modes[]={0,1,2,3,6,7};
 for(unsigned cpu=0;cpu<2;cpu++){for(unsigned i=0;i<sizeof(invalid_modes)/sizeof(invalid_modes[0]);i++){
  /* CPU0 must remain LOCKED under BKL; CPU1 accepts only IDLE/KERNEL/LOCKED. */
  if(cpu==1&&invalid_modes[i]==1){continue;}
  restore_base();arguments(cpu);where="cpu-mode";cpus[cpu].mode=invalid_modes[i];if(reject_apply()){return 1;}
 }}
 restore_base();arguments(0);where="bsp-must-own-lock";cpus[0].mode=4;if(reject_apply()){return 1;}
 const size_t fixed_fields[]={O(Header,kernel_stack),O(Header,continuation),O(Header,root_frame),O(Header,original_cr3),O(Header,result),O(Header,smp),O(Header,logical_id),
  O(Header,contexts),O(Header,context_count),O(Header,pcid_enabled),O(Header,gdt),O(Header,tss),O(Header,idt),O(Header,stack_bottom),O(Header,df_top),
  O(Header,nmi_top),O(Header,exception_top),O(Header,kernel_xstate),O(Header,capture),O(Header,returned),O(Header,return_xstate),O(Header,ready),
  O(Header,deadline_ticks),O(Header,tsc_hz),O(Header,timer_hz)};
 for(unsigned cpu=0;cpu<2;cpu++){for(unsigned i=0;i<sizeof(fixed_fields)/sizeof(fixed_fields[0]);i++){
  restore_base();arguments(cpu);where="header-fixed-field";
  flip_word(header[cpu],fixed_fields[i],8);if(reject_apply()){return 1;}
 }}
 restore_base();arguments(0);where="header-domain";header[0]->domain=NULL;if(reject_apply()){return 1;}
 for(unsigned slot=0;slot<16;slot++){for(unsigned field=0;field<3;field++){
  restore_base();arguments(0);where="root-snapshot-field";
  flip_word(&roots[slot],field*sizeof(U),1);if(reject_apply()){return 1;}
 }}
 restore_base();arguments(0);where="raw-root-tag";root_arg|=17;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="raw-root";root_arg+=4096;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="generation";generation_arg++;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="gs-swapped";gs_arg=1;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="gs-invalid";gs_arg=2;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="unknown-header";header_arg=unknown_header;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="wrong-cpu-frame";header_arg=header[1];if(reject_apply()){return 1;}
 restore_base();arguments(0);where="null-header";header_arg=NULL;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="null-frame";raw_arg=NULL;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="unaligned-frame";raw_arg=(Raw*)((unsigned char*)frames[0]+1);if(reject_apply()){return 1;}
 restore_base();arguments(0);where="frame-outside-stack";raw_arg=frames[1];if(reject_apply()){return 1;}
 restore_base();arguments(0);where="frame-header-alias";raw_arg=(Raw*)header[0];if(reject_apply()){return 1;}
 restore_base();arguments(0);where="frame-context-alias";raw_arg=(Raw*)context;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="frame-domain-alias";raw_arg=(Raw*)domain;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="frame-cpus-alias";raw_arg=(Raw*)cpus;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="rsp-before-frame";raw_arg->rsp=(U)(uintptr_t)raw_arg+sizeof(Raw)-8;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="rsp-past-stack";raw_arg->rsp=header[0]->kernel_stack+8;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="rsp-below-stack";raw_arg->rsp=header[0]->stack_bottom-8;if(reject_apply()){return 1;}
 restore_base();arguments(0);where="frame-past-stack";raw_arg=(Raw*)(uintptr_t)(header[0]->kernel_stack-128);if(reject_apply()){return 1;}
 for(unsigned offset=0;offset<16;offset+=8){
  restore_base();arguments(0);where="insufficient-claim-stack-margin";
  Raw value=*frames[0];raw_arg=(Raw*)(void*)(stacks[0][0]+offset);memcpy(raw_arg,&value,sizeof(value));
  raw_arg->rsp=(U)(uintptr_t)raw_arg+sizeof(*raw_arg)+512;if(reject_apply()){return 1;}
 }
 restore_base();arguments(0);where="unclaimed-direct-dispatch";remember_before();
 REQUIRE(ree_dispatch(header_arg,root_arg,raw_arg,generation_arg)==0);REQUIRE(unchanged());
 return 0;
}
static U DG nested(Header *h,U root,const Raw *raw,U generation){
 if(++nested_calls!=1){exit(95);}Raw before=*raw;
 U value=user_smp_exec_apply(h,root,(Raw*)(uintptr_t)raw,generation,0);
 if(value||memcmp(&before,raw,sizeof(before))||user_smp_exec_registration(80+h->logical_id)!=1){exit(95);}
 return AFTER;
}
static int nested_test(void){
 where="nested-claim";REQUIRE(!registration_empty());remember_before();
 REQUIRE(user_smp_exec_register(nested,PROBE,AFTER,GENERATION,slots,3)==0);REQUIRE(unchanged());
 remember_before();REQUIRE(user_smp_exec_apply(header[0],ROOT,frames[0],GENERATION,0)==AFTER);
 expect_word(&frames[0]->rip,AFTER);REQUIRE(unchanged());
 REQUIRE(nested_calls==1&&user_smp_exec_registration(80)==0);return 0;
}
static int after_gate_test(void){
 where="fixed-after-gate";REQUIRE(!registration_empty());remember_before();
 REQUIRE(user_smp_exec_register(continuation_oracle,PROBE,AFTER,GENERATION,slots,3)==0);REQUIRE(unchanged());
 for(continuation_mode=0;continuation_mode<2;continuation_mode++){
  remember_before();REQUIRE(user_smp_exec_apply(header[0],ROOT,frames[0],GENERATION,0)==0);
  REQUIRE(unchanged());REQUIRE(user_smp_exec_registration(80)==0);
 }
 remember_before();REQUIRE(user_smp_exec_apply(header[0],ROOT,frames[0],GENERATION,0)==AFTER);
 expect_word(&frames[0]->rip,AFTER);REQUIRE(unchanged());REQUIRE(user_smp_exec_registration(80)==0);
 REQUIRE(callback_calls==3);return 0;
}
static int trace_setup(void){
 REQUIRE(ree_size(10)==sizeof(RawTrace)&&ree_size(11)>=64&&ree_size(12)>=64);
 trace_storage=guard((size_t)TRACE_BYTES,4096);trace_records=(RawTrace*)(void*)(trace_storage+32768);
 trace_allocator=guard((size_t)ree_size(12),64);
 for(unsigned i=0;i<3;i++){
  trace_spaces[i]=guard((size_t)ree_size(11),64);trace_tables[i]=guard(4096,4096);trace_meta[i]=guard(64,64);
  REQUIRE(ree_pool(trace_spaces[i],trace_tables[i],trace_meta[i],1,i==0?ROOT:ROOT+i*UINT64_C(0x100000))==0);
 }
 ree_trace_prepare(context,trace_spaces[0],trace_allocator);
 roots[0].space=trace_spaces[1];roots[1].space=trace_spaces[2];
 const size_t offsets[]={O(RawTrace,version),O(RawTrace,commit),O(RawTrace,cpu),O(RawTrace,payload),
  O(RawTrace,header),O(RawTrace,root),O(RawTrace,generation),O(RawTrace,frame),O(RawTrace,stack_bottom),O(RawTrace,stack_top),
  O(RawTrace,context),O(RawTrace,domain),O(RawTrace,reader),O(RawTrace,request),O(RawTrace,acknowledged),
  O(RawTrace,action_sequence),O(RawTrace,command),O(RawTrace,virtual),O(RawTrace,expected),O(RawTrace,after),
  O(RawTrace,raw),O(RawTrace,ticket_before),O(RawTrace,ticket_after),O(RawTrace,reserved)};
 for(unsigned i=0;i<24;i++){REQUIRE(ree_layout((U)(uintptr_t)trace_records,10,i)==offsets[i]);}
 remember_base();return 0;
}
static U trace_bind(void *c,RawTrace *records,U count,U base,U bytes){return ree_trace_bind(c,records,count,base,bytes,headers,16);}
static int trace_bind_ok(void){
 remember_before();REQUIRE(trace_bind(context,trace_records,32,(U)(uintptr_t)trace_storage,TRACE_BYTES)==0);REQUIRE(unchanged());
 remember_before();REQUIRE(trace_bind(context,trace_records,32,(U)(uintptr_t)trace_storage,TRACE_BYTES)!=0);REQUIRE(unchanged());
 return 0;
}
static int trace_bind_rejections(void){
 static const char *names[]={"null-context","context-align","ready","busy","version","attempted","complete","poison","error",
  "null-records","record-align","count-short","count-long","storage-zero","storage-align","storage-short","storage-overflow",
  "records-before-storage","records-past-storage","nonempty-first","nonempty-last","null-space","invalid-space","null-allocator",
  "storage-context","storage-domain","storage-cpus","storage-arena","storage-allocator","kernel-space","kernel-table","kernel-meta",
  "private-space","private-table","private-meta","root-count","null-private-space",
  "null-headers","header-count","offline-header","online-null-header","online-header-shape","storage-header"};
 for(unsigned kind=0;kind<sizeof(names)/sizeof(names[0]);kind++){
  restore_base();where=names[kind];void *c=context;RawTrace *records=trace_records;U count=32;
  Header **header_set=headers;U header_count=16;
  U base=(U)(uintptr_t)trace_storage,bytes=TRACE_BYTES,target=0,length=0;
  #define TCASE(n) (!strcmp(where,(n)))
  if(TCASE("null-context")){c=NULL;}else if(TCASE("context-align")){c=(unsigned char*)context+8;}
  else if(TCASE("ready")){prefix->ready=0;}else if(TCASE("busy")){prefix->busy=1;}
  else if(TCASE("version")){report->version=0;}else if(TCASE("attempted")){report->attempted=1;}
  else if(TCASE("complete")){report->complete=1;}else if(TCASE("poison")){report->poison=1;}else if(TCASE("error")){report->error_code=1;}
  else if(TCASE("null-records")){records=NULL;}else if(TCASE("record-align")){records=(RawTrace*)(void*)((unsigned char*)records+8);}
  else if(TCASE("count-short")){count=31;}else if(TCASE("count-long")){count=33;}
  else if(TCASE("storage-zero")){base=0;}else if(TCASE("storage-align")){base+=8;}
  else if(TCASE("storage-short")){bytes=16383;}else if(TCASE("storage-overflow")){bytes=UINT64_MAX-base+1;}
  else if(TCASE("records-before-storage")){base=(U)(uintptr_t)records+64;}
  else if(TCASE("records-past-storage")){base=(U)(uintptr_t)records;bytes=16384-64;}
  else if(TCASE("nonempty-first")){trace_records[0].version=1;}else if(TCASE("nonempty-last")){trace_records[31].reserved[4]=1;}
  else if(TCASE("null-space")){prefix->space=NULL;}else if(TCASE("invalid-space")){prefix->space=unknown_header;}
  else if(TCASE("null-allocator")){prefix->allocator=NULL;}
  else if(TCASE("storage-context")){target=(U)(uintptr_t)context;length=ree_size(3);}
  else if(TCASE("storage-domain")){target=(U)(uintptr_t)domain;length=sizeof(*domain);}
  else if(TCASE("storage-cpus")){target=(U)(uintptr_t)cpus;length=16*sizeof(*cpus);}
  else if(TCASE("storage-arena")){domain->arena=(U)(uintptr_t)trace_storage;domain->bytes=64;}
  else if(TCASE("storage-allocator")){target=(U)(uintptr_t)trace_allocator;length=ree_size(12);}
  else if(TCASE("kernel-space")){target=(U)(uintptr_t)trace_spaces[0];length=ree_size(11);}
  else if(TCASE("kernel-table")){target=(U)(uintptr_t)trace_tables[0];length=4096;}
  else if(TCASE("kernel-meta")){target=(U)(uintptr_t)trace_meta[0];length=1;}
  else if(TCASE("private-space")){target=(U)(uintptr_t)trace_spaces[2];length=ree_size(11);}
  else if(TCASE("private-table")){target=(U)(uintptr_t)trace_tables[2];length=4096;}
  else if(TCASE("private-meta")){target=(U)(uintptr_t)trace_meta[2];length=1;}
  else if(TCASE("root-count")){report->root_count=17;}else if(TCASE("null-private-space")){roots[1].space=NULL;}
  else if(TCASE("null-headers")){header_set=NULL;}else if(TCASE("header-count")){header_count=15;}
  else if(TCASE("offline-header")){domain->online=3;report->online=3;}
  else if(TCASE("online-null-header")){headers[0]=NULL;}else if(TCASE("online-header-shape")){header[0]->gdt+=8;}
  else if(TCASE("storage-header")){target=(U)(uintptr_t)header[0];length=8192;}
  else{return reject("unimplemented trace bind control");}
  #undef TCASE
  if(target){U end=base+bytes,other=target+length;if(target<base){base=target&~UINT64_C(63);}if(other>end){end=other;}bytes=end-base;}
  remember_before();REQUIRE(ree_trace_bind(c,records,count,base,bytes,header_set,header_count)!=0);REQUIRE(unchanged());REQUIRE(!registration_empty());
 }
 restore_base();where="trace-bind-after-all-rejections";REQUIRE(!trace_bind_ok());return 0;
}
static int trace_entry_rejection(const char *kind){
 where=kind;
 if(!strcmp(kind,"late")){
  remember_before();REQUIRE(bind_actual(actual_callback(),GENERATION,16,context,domain,snapshot)==0);REQUIRE(unchanged());
  remember_before();REQUIRE(trace_bind(context,trace_records,32,(U)(uintptr_t)trace_storage,TRACE_BYTES)!=0);REQUIRE(unchanged());return 0;
 }
 void *candidate=context;
 Header *original_header=header[0];
 if(!strcmp(kind,"context")){
  candidate=guard((size_t)ree_size(3),64);memcpy(candidate,context,(size_t)ree_size(3));
 }else if(!strcmp(kind,"header")){
  memcpy(trace_storage,header[0],8192);header[0]=(Header*)(void*)trace_storage;headers[0]=header[0];
  U address=(U)(uintptr_t)header[0];header[0]->continuation=address;
  header[0]->gdt=address+256;header[0]->tss=address+320;header[0]->idt=address+512;header[0]->kernel_xstate=address+4608;
  snapshot->header=address;
 }else if(!strcmp(kind,"kernel")){
  header[0]->stack_bottom=(U)(uintptr_t)trace_storage;header[0]->kernel_stack=header[0]->stack_bottom+16384;
 }else if(!strcmp(kind,"df")){header[0]->df_top=(U)(uintptr_t)trace_storage+16384;}
 else if(!strcmp(kind,"nmi")){header[0]->nmi_top=(U)(uintptr_t)trace_storage+16384;}
 else if(!strcmp(kind,"exception")){header[0]->exception_top=(U)(uintptr_t)trace_storage+16384;}
 else{return reject("unknown trace entry overlap");}
 if(!strcmp(kind,"context")){
  REQUIRE(!trace_bind_ok());remember_before();
  REQUIRE(bind_actual(actual_callback(),GENERATION,16,candidate,domain,snapshot)!=0);REQUIRE(unchanged());REQUIRE(!registration_empty());return 0;
 }
 /* The first admission itself must reject before publishing trace globals.
  * Correcting the exact same caller-owned buffers must then remain possible. */
 remember_before();REQUIRE(trace_bind(context,trace_records,32,(U)(uintptr_t)trace_storage,TRACE_BYTES)!=0);
 REQUIRE(unchanged());REQUIRE(!registration_empty());restore_base();header[0]=original_header;
 REQUIRE(!trace_bind_ok());remember_before();
 REQUIRE(bind_actual(actual_callback(),GENERATION,16,context,domain,snapshot)==0);REQUIRE(unchanged());return 0;
}
static void trace_arm(unsigned cpu,U payload,U sequence){
 prefix->payload=payload;report->action_sequence=sequence;Reader *r=&readers[cpu];
 r->request=sequence;r->acknowledged=sequence-1;r->command=4;r->virtual=WA;r->expected=CODE99;
 r->ticket=(Ticket){1,0,cpu,sequence,ROOT,WA,PROBE,AFTER};raw_frame(cpu,cpu?16:0);arguments(cpu);
}
static int trace_success(unsigned cpu,U payload){
 trace_arm(cpu,payload,payload==CODE42?37:38);RawTrace expected;memset(&expected,0,sizeof(expected));
 expected.version=1;expected.commit=1;expected.cpu=cpu;expected.payload=payload;expected.header=(U)(uintptr_t)header[cpu];
 expected.root=ROOT;expected.generation=GENERATION;expected.frame=(U)(uintptr_t)raw_arg;
 expected.stack_bottom=header[cpu]->stack_bottom;expected.stack_top=header[cpu]->kernel_stack;
 expected.context=(U)(uintptr_t)context;expected.domain=(U)(uintptr_t)domain;expected.reader=(U)(uintptr_t)&readers[cpu];
 expected.request=readers[cpu].request;expected.acknowledged=readers[cpu].acknowledged;
 expected.action_sequence=report->action_sequence;expected.command=4;expected.virtual=WA;expected.expected=CODE99;expected.after=AFTER;
 expected.raw=*raw_arg;expected.ticket_before=readers[cpu].ticket;expected.ticket_after=expected.ticket_before;
 expected.ticket_after.armed=0;expected.ticket_after.consumed=1;
 RawTrace *record=&trace_records[cpu*2+(payload==CODE43)];where="trace-independent-64q-oracle";remember_before();
 U applied=trace_stack_apply(header_arg,root_arg,raw_arg,generation_arg,gs_arg);
 REQUIRE(intact());REQUIRE(applied==AFTER);REQUIRE(!exception_scratch(cpu));
 for(unsigned i=0;i<64;i++){U value;memcpy(&value,(unsigned char*)&expected+i*8,8);expect_word((unsigned char*)record+i*8,value);}
 expect_word(&raw_arg->rip,AFTER);expect_word(&readers[cpu].ticket.armed,0);expect_word(&readers[cpu].ticket.consumed,1);
 REQUIRE(unchanged());REQUIRE(record->raw.rip==PROBE&&record->after==AFTER&&raw_arg->rip==AFTER);
 REQUIRE(readers[cpu].acknowledged==expected.acknowledged&&user_smp_exec_registration(80+cpu)==0);
 where="trace-consumed-replay";remember_before();REQUIRE(user_smp_exec_apply(header_arg,root_arg,raw_arg,generation_arg,gs_arg)==0);REQUIRE(unchanged());
 trace_arm(cpu,payload,39);where="trace-full-slot-rearmed-third-attempt";remember_before();
 REQUIRE(user_smp_exec_apply(header_arg,root_arg,raw_arg,generation_arg,gs_arg)==0);REQUIRE(unchanged());return 0;
}
static int trace_test(void){
 where="trace-entry-bind";REQUIRE(!trace_bind_ok());remember_before();
 REQUIRE(bind_actual(actual_callback(),GENERATION,16,context,domain,snapshot)==0);REQUIRE(unchanged());
 REQUIRE(user_smp_exec_registration(5)==domain->online);active();remember_base();
 for(unsigned payload=0;payload<2;payload++){for(unsigned word=0;word<64;word++){
  restore_base();trace_arm(0,payload?CODE43:CODE42,37);where="trace-any-nonzero-qword-refuses-consumption";
  U value=UINT64_C(0xa501000000000000)|word;memcpy((unsigned char*)&trace_records[payload]+word*8,&value,8);
  remember_before();REQUIRE(user_smp_exec_apply(header_arg,root_arg,raw_arg,generation_arg,gs_arg)==0);REQUIRE(unchanged());
 }}
 for(unsigned cpu=0;cpu<online_count;cpu++){
  for(unsigned field=0;field<8;field++){
   restore_base();trace_arm(cpu,CODE42,37);where="trace-ticket-field-mismatch";flip_word(&readers[cpu].ticket,field*8,1);
   remember_before();REQUIRE(user_smp_exec_apply(header_arg,root_arg,raw_arg,generation_arg,gs_arg)==0);REQUIRE(unchanged());
  }
  restore_base();trace_arm(cpu,CODE42,37);generation_arg++;where="trace-generation-mismatch";
  remember_before();REQUIRE(user_smp_exec_apply(header_arg,root_arg,raw_arg,generation_arg,gs_arg)==0);REQUIRE(unchanged());
  const size_t raw_fields[]={O(Raw,cr2),O(Raw,vector),O(Raw,error),O(Raw,rip),O(Raw,cs)};
  for(unsigned field=0;field<sizeof(raw_fields)/sizeof(raw_fields[0]);field++){
   restore_base();trace_arm(cpu,CODE42,37);where="trace-per-cpu-raw-field";flip_word(raw_arg,raw_fields[field],1);
   remember_before();REQUIRE(user_smp_exec_apply(header_arg,root_arg,raw_arg,generation_arg,gs_arg)==0);REQUIRE(unchanged());
  }
  for(unsigned kind=0;kind<8;kind++){
   restore_base();trace_arm(cpu,CODE42,37);where="trace-per-cpu-header-root-IF-range-payload";
   if(kind==0){header_arg=header[(cpu+1)%online_count];}else if(kind==1){root_arg|=17;}
   else if(kind==2){root_arg+=4096;}else if(kind==3){raw_arg->rflags|=512;}
   else if(kind==4){raw_arg->rsp=(U)(uintptr_t)raw_arg+sizeof(Raw)-8;}
   else if(kind==5){prefix->payload=CODE99;}else if(kind==6){readers[cpu].acknowledged=37;}
   else{raw_arg=(Raw*)(void*)&trace_records[cpu*2];}
   remember_before();REQUIRE(user_smp_exec_apply(header_arg,root_arg,raw_arg,generation_arg,gs_arg)==0);REQUIRE(unchanged());
  }
 }
 restore_base();
 for(unsigned cpu=0;cpu<online_count;cpu++){if(trace_success(cpu,CODE42)||trace_success(cpu,CODE43)){return 1;}}
 for(unsigned cpu=online_count;cpu<16;cpu++){for(unsigned payload=0;payload<2;payload++){
  unsigned char zero[512]={0};REQUIRE(!memcmp(&trace_records[cpu*2+payload],zero,512));
 }}
 if(online_count<16){where="trace-offline-header";remember_before();REQUIRE(user_smp_exec_apply(unknown_header,ROOT,frames[0],GENERATION,0)==0);REQUIRE(unchanged());}
 return 0;
}
int main(int argc,char **argv){
 const char *scenario=argc>1?argv[1]:"all";int tracing=!strncmp(scenario,"trace",5);
 if(setup(tracing&&strcmp(scenario,"trace-offline")?16:2)){return 1;}
 if(tracing){
  if(trace_setup()){return 1;}
  if(!strcmp(scenario,"trace")||!strcmp(scenario,"trace-offline")){if(trace_test()){return 1;}}
  else if(!strcmp(scenario,"trace-binds")){if(trace_bind_rejections()){return 1;}}
  else if(!strncmp(scenario,"trace-entry-",12)){if(trace_entry_rejection(scenario+12)){return 1;}}
  else{return reject("unknown trace scenario");}
 }else if(!strcmp(scenario,"missing")){
  where="missing-registration";REQUIRE(!registration_empty());if(reject_apply()){return 1;}
 }else if(!strcmp(scenario,"nested")){
  if(nested_test()){return 1;}
 }else if(!strcmp(scenario,"after-gate")){
  if(after_gate_test()){return 1;}
 }else if(!strncmp(scenario,"bad-bind-",9)){
  if(bad_binds(scenario+9)){return 1;}
 }else if(!strcmp(scenario,"all")){
  if(bad_binds(NULL)){return 1;}
  where="trusted-bind";remember_before();
  REQUIRE(bind_actual(actual_callback(),GENERATION,16,context,domain,snapshot)==0);REQUIRE(unchanged());
  REQUIRE(!registered());remember_before();
  REQUIRE(bind_actual(actual_callback(),GENERATION,16,context,domain,snapshot)!=0);REQUIRE(unchanged());
  REQUIRE(user_smp_exec_register(rogue,PROBE,AFTER,GENERATION,slots,3)!=0);REQUIRE(unchanged());REQUIRE(!registered());
  active();remember_base();
  if(rejections()||success(0,0)||success(1,16)||success(0,16)||success_at_stack_margin()){return 1;}
 }else{return reject("unknown scenario");}
 REQUIRE(intact());REQUIRE(callback_calls==(!strcmp(scenario,"after-gate")?3:0));
 printf("runtime EXEC entry checks=%llu scenario=%s; real DG bridge + production ASM apply; 23-qword/64-qword oracle and guards; trace success uses host-selected exception arena; privileged entry assembled only; no guest executed\n",
  (unsigned long long)checks,scenario);cleanup();return 0;
}

