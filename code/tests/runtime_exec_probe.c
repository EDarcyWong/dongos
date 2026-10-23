#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
typedef uint64_t U;
#define OLD UINT64_C(0xffffa90000000000)
#define WA (OLD+8192)
#define XA (OLD+12288)
#define MASK UINT64_C(0x0000fffffffff000)
#define NX UINT64_C(0x8000000000000000)
#define CODE42 UINT64_C(0x0000c30000002ab8)
#define CODE43 UINT64_C(0x0000c30000002bb8)
#define CODE99 UINT64_C(0x0000c300000063b8)
#define ERR_INVALID UINT64_C(0x06140001)
#define ERR_FOREST UINT64_C(0x06140003)
#define ERR_AUTH UINT64_C(0x06140002)
#define ERR_TIMEOUT UINT64_C(0x06140005)
#define ERR_DOMAIN_TIMEOUT UINT64_C(0x06090005)
#define ERR_DOMAIN_HARDWARE UINT64_C(0x06090003)
#define ERR_STALE_WRITE UINT64_C(0x06140006)
#define ERR_FAULT UINT64_C(0x06140007)
typedef struct{U cpu,root,cr0,cr4,rflags;} Env;
typedef struct{U cpu,root,cr0,cr4,rflags,value,fault;} Sample;
typedef struct{U armed,consumed,cpu,sequence,root,virtual,rip,after;} Ticket;
typedef struct{U cpu,sequence,root,rip,cr2,error,cs,rflags,vector;} Fault;
typedef struct{U cpu,sequence,root,virtual,rip,after;} Binding;
typedef struct{U request,acknowledged,command,virtual,expected,count;Ticket ticket;Sample sample,called42,called43,denied42,denied43,serialized;U serialized_sequence;} Reader;
typedef struct{U version,attempted,complete,poison,error_code,phase,state,root,physical,online,root_count,
 barriers,sequence,action_sequence,command,expected,ack_mask,held,unmapped,receipts_consumed,
 tables_before,tables_after,aliases,readers_pointer,roots_pointer;} Report;
typedef struct{void *space;U identity,generation;} Root;
typedef struct{U mode,token,incarnation,slot,captured_token,captured_incarnation,captured,requested,acknowledged,
 capture,capture_xstate,returned,return_xstate,return_root;void *seen;} Cpu;
typedef struct{U ready,failed,lock,owner,online,sequence,barrier,expected,completed,kernel_root;void *engine;Cpu *cpus;void *processes;U arena,bytes;} Domain;
extern U DG re_size(U),re_init(void*,void*,void*,U),re_map(void*,U,U,U),re_buddy(void*,void*,U*,U*);
extern U DG re_bind(void*,Domain*,void*,void*,const Root*,U,U,U(DG*)(U),void(DG*)(Env*),void(DG*)(U,U,U,Ticket*,Sample*));
extern U DG re_install(void*,Domain*),re_run(void*),re_pointer(void*,U),re_fault(void*,U,const Fault*,U*);
extern U DG re_consume(Ticket*,const Fault*,const Binding*,U*);
/* The exported production domain poll is reached through this exact wrapper. */
extern U DG re_poll(Domain*,U);
typedef struct{unsigned char *all,*p;size_t n;} Guard;
static Guard allocations[32];static unsigned allocated;
static void *ctx,*spaces[3],*pools[3],*metas[3],*allocator;
static Domain *domain;static Cpu *cpus;static Root roots[2];static Report *report;static Reader *readers;
static U current,clock_value,frame,anchor,tag_bad,pge_bad,identity_bad,hold_ack=16,skip_flush=16,pcide=1,checks,flushes;
static U bad_tag_cpu=16,bad_pge_cpu=16;
static U cache_w[3],cache_x[3],serialized[3],calls[3],probes[3],warm[3],fault_replays;
static U actual_word;static unsigned char before_pool[32*4096];
static int reject(const char *why){fprintf(stderr,"RAW_EXEC_REJECT %s; returned normally\n",why);return 1;}
#define REQUIRE(x) do{++checks;if(!(x)){return reject(#x);}}while(0)
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const unsigned char *file,U n){
 fprintf(stderr,"unexpected Dong panic %u:%u %.*s\n",kind,line,(int)n,file);exit(99);
}
static void *guard(size_t n,size_t alignment){
 unsigned char *all=calloc(n+alignment+128,1);if(!all||allocated==32){exit(97);}
 uintptr_t p=((uintptr_t)all+64+alignment-1)&~(alignment-1);
 memset((void*)(p-64),0xa5,64);memset((void*)(p+n),0x5a,64);
 allocations[allocated++]=(Guard){all,(unsigned char*)p,n};return (void*)p;
}
static int guards(void){for(unsigned i=0;i<allocated;i++){for(unsigned j=0;j<64;j++){
 if(allocations[i].p[-64+(int)j]!=0xa5||allocations[i].p[allocations[i].n+j]!=0x5a){return 0;}}}return 1;}
static U *table(U physical){for(unsigned i=0;i<3;i++){U base=UINT64_C(0x4000000)+i*UINT64_C(0x100000);
 if(physical>=base&&physical<base+32*4096&&!(physical&4095)){return (U*)((unsigned char*)pools[i]+physical-base);}}return 0;}
/* Independent raw walk, not a call to DG query or the owner's alias report. */
static U pte(U root,U va){U pa=root;for(unsigned level=0;level<4;level++){
 U *t=table(pa);if(!t){return 0;}U e=t[(va>>(39-level*9))&511];if(!(e&1)){return 0;}
 if(level==3){return e;}if(e&128){return 0;}pa=e&MASK;}return 0;}
static U value(U physical){if(physical==frame){return actual_word;}if(physical==anchor){return CODE43;}exit(96);}
static void DG hardware(Env *e){*e=(Env){current,domain->kernel_root|tag_bad|(current==bad_tag_cpu?17:0),
 UINT64_C(0x80010001),32|(pcide<<17)|pge_bad|(current==bad_pge_cpu?128:0),2};}
U DG runtime_exec_probe_label(U which){return which==0?UINT64_C(0x11110000):which==1?UINT64_C(0x11110008):0;}
static U DG identity(U cookie){Root *copied=(Root*)(uintptr_t)re_pointer(ctx,2);
 if(cookie!=0x19||identity_bad||report->root_count!=2){return 1;}
 for(unsigned i=0;i<2;i++){if(copied[i].space!=roots[i].space||copied[i].identity!=roots[i].identity
  ||copied[i].generation!=roots[i].generation){return 1;}}return 0;}
static void DG action(U command,U va,U expected,Ticket *ticket,Sample *sample){
 Env e;hardware(&e);*sample=(Sample){e.cpu,e.root,e.cr0,e.cr4,e.rflags,0,0};
 U w=pte(domain->kernel_root,WA),x=pte(domain->kernel_root,XA),entry=va?pte(domain->kernel_root,va):0;
 if((w&2)&&(x&1)&&!(x&NX)){sample->fault=9;return;}
 if(command==1){serialized[current]++;return;}
 if(command==2){if(!entry){sample->fault=9;return;}sample->value=value(entry&MASK);return;}
 if(command==3){if(!(entry&1)||(entry&NX)||(w&2)){sample->fault=9;return;}
  cache_x[current]=1;calls[current]++;U code=value(entry&MASK);sample->value=code==CODE42?42:code==CODE43?43:99;return;}
 if(command==5||command==6){if(!entry||(!(entry&2)&&!cache_w[current])){sample->fault=9;return;}
  cache_w[current]=1;actual_word=expected;sample->value=actual_word;if(command==5){warm[current]++;}return;}
 if(command==4){probes[current]++;
  if(report->phase!=5||report->state!=2||((x&1)&&!(x&NX))){sample->fault=9;return;}
  if(cache_w[current]||(entry&2)){actual_word=expected;sample->value=actual_word;return;}
  Fault observed={current,readers[current].request,domain->kernel_root|tag_bad,
   runtime_exec_probe_label(0),WA,3,8,2,14};U after=0;
  if(re_fault(ctx,current,&observed,&after)||after!=runtime_exec_probe_label(1)){sample->fault=9;return;}
  Ticket saved=*ticket;U untouched=0xdead;
  if(re_fault(ctx,current,&observed,&untouched)!=ERR_FAULT||untouched!=0xdead||memcmp(ticket,&saved,sizeof(saved))){sample->fault=9;return;}
  fault_replays++;sample->fault=1;sample->value=actual_word;return;
 }
 sample->fault=9;
}
U DG user_smp_arch_if0(void){return 1;}U DG user_smp_arch_cpu(void){return current;}
/* Production's Domain helper strips low CR3 bits; the owner must check raw hardware. */
U DG user_smp_arch_root(void){return domain->kernel_root;}
U DG user_smp_arch_try_lock(U *p){if(*p){return 0;}*p=1;return 1;}
void DG user_smp_arch_unlock(U *p){*p=0;}void DG user_smp_arch_pause(void){}
U DG user_smp_arch_clock(void){clock_value+=1000;return clock_value;}
void DG user_smp_arch_copy(U d,U s,U n){memcpy((void*)(uintptr_t)d,(void*)(uintptr_t)s,(size_t)n);}
void DG user_smp_arch_save(U p){(void)p;}U DG user_smp_arch_switch(U r,U t,U k){(void)r;(void)t;(void)k;return 0;}
U DG user_smp_arch_validate(U f,U r){(void)f;(void)r;return 1;}U DG user_domain_legacy_poll(void){return 0;}
U DG user_smp_arch_flush(U cpu){if(cpu!=current){return 1;}
 if(cpu!=skip_flush||report->phase!=4){cache_w[cpu]=cache_x[cpu]=0;}
 flushes++;return 0;}
U DG user_smp_arch_kick(U cpu){if(cpu>=3){return 1;}if(cpu==hold_ack){return 0;}
 U previous=current;current=cpu;U code=re_poll(domain,cpu);current=previous;return code?1:0;}
static int fault_controls(void){
 Binding binding={2,77,UINT64_C(0x4000000),WA,runtime_exec_probe_label(0),runtime_exec_probe_label(1)};
 Ticket ticket={1,0,2,77,binding.root,WA,binding.rip,binding.after};
 Fault fault={2,77,binding.root,binding.rip,WA,3,8,2,14};
 for(unsigned kind=0;kind<18;kind++){Ticket t=ticket,original=t;Fault f=fault;Binding b=binding;U out=0xface;
  if(kind==0){f.cpu++;}else if(kind==1){f.sequence++;}else if(kind==2){f.root|=17;}
  else if(kind==3){f.rip++;}else if(kind==4){f.cr2+=8;}else if(kind==5){f.error=7;}
  else if(kind==6){f.cs=0x33;}else if(kind==7){f.rflags|=512;}else if(kind==8){f.vector=13;}
  else if(kind==9){t.consumed=1;original=t;}else if(kind==10){t.after++;original=t;}else if(kind==11){b.root|=17;}
  else if(kind==12){t.armed=0;original=t;}else if(kind==13){t.cpu++;original=t;}
  else if(kind==14){t.sequence++;original=t;}else if(kind==15){t.virtual+=8;original=t;}
  else if(kind==16){t.rip++;original=t;}else{b.after++;}
  REQUIRE(re_consume(&t,&f,&b,&out)==ERR_FAULT&&out==0xface&&!memcmp(&t,&original,sizeof(t)));
 }
 U out=0;REQUIRE(!re_consume(&ticket,&fault,&binding,&out)&&out==binding.after&&ticket.armed==0&&ticket.consumed==1);
 Ticket consumed=ticket;out=0xdead;REQUIRE(re_consume(&ticket,&fault,&binding,&out)==ERR_FAULT&&out==0xdead&&!memcmp(&ticket,&consumed,sizeof(ticket)));
 return 0;
}
static int setup(void){
 REQUIRE(re_size(1)==64&&re_size(2)==sizeof(Domain)&&re_size(3)==sizeof(Cpu));
 REQUIRE(re_size(6)==sizeof(Reader)&&re_size(7)==sizeof(Report)&&re_size(8)==sizeof(Ticket)
  &&re_size(9)==sizeof(Fault)&&re_size(10)==sizeof(Binding));
 ctx=guard((size_t)re_size(0),64);domain=guard(sizeof(*domain),64);cpus=guard(16*sizeof(*cpus),64);
 report=(Report*)(uintptr_t)re_pointer(ctx,0);readers=(Reader*)(uintptr_t)re_pointer(ctx,1);
 for(unsigned i=0;i<3;i++){spaces[i]=guard(64,64);pools[i]=guard(32*4096,4096);metas[i]=guard(32,64);
  REQUIRE(!re_init(spaces[i],pools[i],metas[i],UINT64_C(0x4000000)+i*UINT64_C(0x100000)));}
 allocator=guard((size_t)re_size(4),64);void *bmeta=guard(64*(size_t)re_size(5),64);
 REQUIRE(!re_buddy(allocator,bmeta,&anchor,&frame)&&anchor&&frame&&anchor!=frame);
 REQUIRE(!re_map(spaces[0],OLD,anchor,0)&&!re_map(spaces[0],OLD+4096,anchor,4));
 for(unsigned i=1;i<3;i++){REQUIRE(!re_map(spaces[i],UINT64_C(0x40000000)+i*4096,UINT64_C(0x20000000)+i*4096,3));
  memcpy((U*)pools[i]+1,(U*)pools[0]+1,511*8);roots[i-1]=(Root){spaces[i],i-1,100+i};}
 domain->ready=1;domain->lock=1;domain->online=7;domain->kernel_root=UINT64_C(0x4000000);domain->cpus=cpus;
 for(unsigned i=0;i<3;i++){cpus[i].mode=i?4:5;cpus[i].slot=16;cpus[i].seen=guard(384,64);}
 REQUIRE(re_bind(ctx,domain,spaces[0],allocator,roots,2,frame,NULL,hardware,action)==ERR_INVALID);
 REQUIRE(re_bind(ctx,domain,spaces[0],allocator,roots,2,frame,identity,NULL,action)==ERR_INVALID);
 REQUIRE(re_bind(ctx,domain,spaces[0],allocator,roots,2,frame,identity,hardware,NULL)==ERR_INVALID);
 for(U i=0;i<re_size(0);i++){REQUIRE(((unsigned char*)ctx)[i]==0);}
 REQUIRE(!re_bind(ctx,domain,spaces[0],allocator,roots,2,frame,identity,hardware,action));
 REQUIRE(!re_install(ctx,domain));return 0;
}
int main(int argc,char **argv){
 const char *scenario=argc>1?argv[1]:"all";if(setup()||fault_controls()){return 1;}
 if(!strcmp(scenario,"fallback")){pcide=0;}
 if(!strcmp(scenario,"kernel-tag-fallback")){pcide=0;tag_bad=17;}
 if(!strcmp(scenario,"identity")){identity_bad=1;}
 else if(!strcmp(scenario,"omitted-root")){report->root_count=1;}
 else if(!strcmp(scenario,"generation")){Root *r=(Root*)(uintptr_t)re_pointer(ctx,2);r[1].generation++;}
 else if(!strcmp(scenario,"kernel-tag")){tag_bad=17;}
 else if(!strcmp(scenario,"pge")){pge_bad=128;}
 else if(!strcmp(scenario,"ap-kernel-tag")){bad_tag_cpu=2;}
 else if(!strcmp(scenario,"ap-kernel-tag-fallback")){pcide=0;bad_tag_cpu=2;}
 else if(!strcmp(scenario,"ap-pge")){bad_pge_cpu=2;}
 else if(!strcmp(scenario,"wrong-cpu")){current=1;}
 else if(!strcmp(scenario,"missing-ack")){hold_ack=2;}
 else if(!strcmp(scenario,"stale-write")){skip_flush=2;}
 else if(!strcmp(scenario,"hidden-user")){REQUIRE(!re_map(spaces[1],UINT64_C(0x50000000),frame,3));}
 else if(!strcmp(scenario,"hidden-kernel")){REQUIRE(!re_map(spaces[0],OLD+16384,frame,1));}
 else if(strcmp(scenario,"all")&&strcmp(scenario,"fallback")&&strcmp(scenario,"kernel-tag-fallback")){return reject("unknown scenario");}
 memcpy(before_pool,pools[0],sizeof(before_pool));U word_before=actual_word;
 U code=re_run(ctx);
 if(!strcmp(scenario,"all")||!strcmp(scenario,"fallback")){
  if(code){U w=pte(domain->kernel_root,WA),x=pte(domain->kernel_root,XA);
   if(code==ERR_FOREST&&report->phase==3&&report->state==2&&(w&2)&&!(x&NX)){return reject("unsafe-both-aliases");}
   if(code==ERR_FOREST&&report->phase==3&&report->state==2&&(w&2)&&(x&NX)){return reject("missing-revoke");}
   if(code==ERR_FOREST&&report->phase==3&&report->state==2&&!(w&2)&&(x&1)&&!(x&NX)){return reject("early-exec-grant");}
   if(code==ERR_AUTH&&domain->barrier&&cpus[0].acknowledged!=domain->sequence){return reject("incomplete-ack");}
   return reject("unexpected owner failure");
  }
  REQUIRE(report->complete==1&&!report->poison&&report->state==0&&report->held==1&&report->unmapped==1);
  REQUIRE(report->barriers==13&&flushes==39&&domain->sequence==13&&domain->completed==13);
  REQUIRE(report->receipts_consumed==2&&report->tables_before==report->tables_after&&report->aliases==0);
  REQUIRE(actual_word==CODE43&&!pte(domain->kernel_root,WA)&&!pte(domain->kernel_root,XA));
  REQUIRE(!memcmp(before_pool,pools[0],sizeof(before_pool))&&fault_replays==6);
  for(unsigned i=0;i<3;i++){
   REQUIRE(calls[i]==2&&probes[i]==2&&warm[i]==2&&serialized[i]==6&&cpus[i].acknowledged==13);
   REQUIRE(readers[i].called42.value==42&&readers[i].called43.value==43&&readers[i].denied42.fault==1&&readers[i].denied43.fault==1);
   REQUIRE(readers[i].denied42.value==CODE42&&readers[i].denied43.value==CODE43);
   REQUIRE(readers[i].sample.root==domain->kernel_root&&readers[i].sample.cpu==i&&!(readers[i].sample.cr4&128));
   REQUIRE(readers[i].serialized.root==domain->kernel_root&&readers[i].serialized.cpu==i&&readers[i].serialized_sequence>0);
  }
 }else if(!strcmp(scenario,"stale-write")){
  REQUIRE(code==ERR_STALE_WRITE&&report->poison==1&&domain->failed==1&&report->held==1);
  REQUIRE(report->phase==5&&report->state==2&&actual_word==CODE99&&!report->complete);
  U w=pte(domain->kernel_root,WA),x=pte(domain->kernel_root,XA);
  REQUIRE((w&1)&&!(w&2)&&(w&NX)&&(x&1)&&!(x&2)&&(x&NX));
  REQUIRE(readers[2].ticket.armed==1&&readers[2].ticket.consumed==0&&cache_w[2]==1);
 }else{
  U expected=(!strcmp(scenario,"hidden-user")||!strcmp(scenario,"hidden-kernel"))?ERR_FOREST:
   !strcmp(scenario,"missing-ack")?ERR_DOMAIN_TIMEOUT:
   (!strcmp(scenario,"ap-kernel-tag")||!strcmp(scenario,"ap-kernel-tag-fallback")||!strcmp(scenario,"ap-pge"))?ERR_DOMAIN_HARDWARE:ERR_AUTH;
  REQUIRE(code==expected&&report->poison==1&&domain->failed==1&&report->held==1&&!report->complete);
  REQUIRE(!memcmp(before_pool,pools[0],sizeof(before_pool))&&actual_word==word_before&&!pte(domain->kernel_root,XA));
 }
 REQUIRE(guards());printf("runtime exec raw checks=%llu scenario=%s barriers=%llu flushes=%llu; real DG/paging, hardware boundaries mocked; handler not wired; no guest executed\n",
  (unsigned long long)checks,scenario,(unsigned long long)report->barriers,(unsigned long long)flushes);
 for(unsigned i=0;i<allocated;i++){free(allocations[i].all);}return 0;
}
