/* Actual DG paging/forest/Domain and real atomic ASM gate; only CPU/MSR/cache
   boundaries are explicitly mocked. No privileged instruction is executed. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
typedef uint64_t U;
#define NX (UINT64_C(1)<<63)
#define MASK UINT64_C(0x0000fffffffff000)
#define CLOSED (UINT64_C(1)<<63)
#define PA UINT64_C(0x10000000)
#define KROOT UINT64_C(0x4000000)
#define HHDM UINT64_C(0xffff800000000000)
#define UV1 UINT64_C(0x40000000)
#define UV2 UINT64_C(0x50000000)
#define BYTES UINT64_C(12288)
#define PAT UINT64_C(0x0000000100000006)
#define ERR_AUTH UINT64_C(0x06150002)
#define ERR_FOREST UINT64_C(0x06150003)
#define ERR_HW UINT64_C(0x06150004)
#define ERR_CAP UINT64_C(0x06150007)
#define ERR_STORE UINT64_C(0x06150008)
typedef struct {U mode,token,incarnation,slot,captured_token,captured_incarnation,captured,requested,acknowledged,capture,capture_xstate,returned,return_xstate,return_root;void*seen;} Cpu;
typedef struct {U token,incarnation,root,frame,xstate,retiring,retirement;} Process;
typedef struct {U ready,failed,lock,owner,online,sequence,barrier,expected,completed,kernel_root;void*engine;Cpu*cpus;Process*processes;U arena,bytes;} Domain;
typedef struct {void*space;U identity,generation;} Root;
typedef struct {U root,identity,generation,virtual_address,physical,bytes,flags,leaf_bytes;} Alias;
typedef struct {U word,epoch,drained,opened;} Gate;
typedef struct {U cpu,if0,root,cr0,cr4,pat,bits,cap,default_type,request,barrier,action,operations,apic,variable[32],fixed[11];} Reading;
typedef struct {U request,acknowledged,reads,maintenances;Reading baseline,latest;} Reader;
typedef struct {void*space;U virtual_address,physical,flags,retired[8];} Page;
typedef struct {U version,attempted,complete,poison,error_code,phase,round,target,root,online,physical,bytes,linear,revoked,reclaimed,remapped,barriers,first,second,request,action,held,gate_token,committed;} Report;
typedef struct {void*pointer;size_t length;} Slice;
typedef U(DG*Check)(U,const Root*,size_t,const Alias*,size_t);
typedef U(DG*Hardware)(U,U,U,Reading*);
typedef struct {Domain*domain;void*kernel;const void*info;Slice roots,ledger,pages;void*work;Gate*gate;U*ledger_epoch;Check check;Hardware hardware;U cookie,ticks;} Config;
extern U DG rc_size(U),rc_init(void*,void*,void*,U),rc_map(void*,U,U,U),rc_domain(U,U,Domain**);
extern U DG rc_bind(void*,const Config*),rc_hook(void*,Domain*),rc_run(void*),rc_poll(Domain*,U),rc_get(void*,U);
extern U DG runtime_cache_gate_enter(Gate*),runtime_cache_gate_leave(Gate*),runtime_cache_gate_close(Gate*,U),runtime_cache_gate_drain(Gate*,U),runtime_cache_gate_open(Gate*,U);
typedef struct {unsigned char*allocation,*p;size_t n;} Guard;
static Guard blocks[32];static size_t block_count;
static void*context,*spaces[3],*pools[3];static unsigned char*metadata[3];
static Domain*domain;static Config*config;static Root*roots;static Alias*ledger;static Page*pages;static Gate*gate;static U*epoch,*boot;
static Alias publication[3];
static U current,clock_value,checks,flushes,first_ack[3],maintained[3],second_ack[3],raw_samples;
static U stop_cpu=16,bad_identity,bad_hardware,bad_pat,bad_maint,bad_mtrr,bad_tag,bad_range;
static const char*raw_failure;static Report*report;
static int failure(const char*why,int line){fprintf(stderr,"runtime cache raw oracle line %d: %s; returned normally\n",line,why);return 1;}
#define REQUIRE(x) do{checks++;if(!(x)){return failure(#x,__LINE__);}}while(0)
DG void __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const void*file,U bytes){(void)file;(void)bytes;fprintf(stderr,"unexpected Dong panic %u/%u\n",kind,line);exit(99);}
static void*guard(size_t n,size_t alignment){
 unsigned char*allocation=calloc(n+alignment+128,1);if(!allocation){exit(98);}
 uintptr_t p=((uintptr_t)allocation+64+alignment-1)&~(alignment-1);
 memset((void*)(p-64),0xa5,64);memset((void*)(p+n),0x5a,64);
 if(block_count==32){exit(97);}blocks[block_count++]=(Guard){allocation,(void*)p,n};return (void*)p;
}
static int guards(void){for(size_t i=0;i<block_count;i++){for(size_t j=0;j<64;j++){if(blocks[i].p[-64+(ptrdiff_t)j]!=0xa5||blocks[i].p[blocks[i].n+j]!=0x5a){return 0;}}}return 1;}
static U*physical_table(U physical){
 for(size_t i=0;i<3;i++){U base=KROOT+i*UINT64_C(0x100000);if(physical>=base&&physical-base<32*4096&&!(physical&4095)){return (U*)((unsigned char*)pools[i]+physical-base);}}
 return NULL;
}
/* Independent raw PA and effective permission decoder across the actual full
   retained forest. It never calls a Dong query to decide what was mapped. */
static U mapping(size_t space,U va,U*flags){
 U physical=KROOT+space*UINT64_C(0x100000);int wr=1,us=1,nx=0;
 for(unsigned level=0;level<4;level++){
  U*table=physical_table(physical);if(!table){raw_failure="foreign raw table";return 0;}
  U e=table[(va>>(39-9*level))&511];if(!e){return 0;}
  if(!(e&1)||(e&128&&level!=3)){raw_failure="malformed/large GOP leaf";return 0;}
  wr=wr&&!!(e&2);us=us&&!!(e&4);nx=nx||!!(e&NX);
  if(level==3){if(e&~(MASK|NX|255)){raw_failure="reserved GOP bits";return 0;}
   U cache=e&152;if(cache!=0&&cache!=24&&cache!=128){raw_failure="invalid cache selector";return 0;}
   if(flags){*flags=(wr?1:0)|(us?2:0)|(!nx?4:0)|(cache==24?8:0)|(cache==128?16:0);}
   return (e&MASK)+(va&4095);
  }
  if(e&~(MASK|NX|39)){raw_failure="reserved parent bits";return 0;}physical=e&MASK;
 }
 return 0;
}
static U pending(void){U count=0;for(size_t r=0;r<3;r++){for(size_t i=0;i<32;i++){count+=metadata[r][i]==2;}}return count;}
static int all_aliases(int absent,U selector){
 const U va[3]={HHDM+PA,UV1,UV2};
 for(size_t r=0;r<3;r++){for(U page=0;page<3;page++){
  U flags=0,physical=mapping(r,va[r]+page*4096,&flags);raw_samples++;
  if(absent){if(physical){raw_failure=r?"USER-alias-not-revoked":"kernel-alias-not-revoked";return 0;}}
  else if(physical!=PA+page*4096||flags!=((r==0?1:r==1?3:2)|selector)){
   raw_failure="PA/USER/WRITE/NX/cache-restore";return 0;
  }
 }}
 /* Borrowed HHDM entries and the permanent non-GOP table-pool anchor survive. */
 U flags=0;if(mapping(0,HHDM+KROOT,&flags)!=KROOT||flags!=1){raw_failure="lost-HHDM-anchor";return 0;}
 for(size_t r=1;r<3;r++){for(size_t slot=1;slot<512;slot++){
  U a=((U*)pools[r])[slot],b=((U*)pools[0])[slot];
  if(((a^b)&~UINT64_C(32))||(b==0&&a)){raw_failure="borrowed-shared-entry-changed";return 0;}
 }}return raw_failure==NULL;
}
static U DG identity(U cookie,const Root*actual,size_t count,const Alias*allowed,size_t aliases){
 if(cookie!=0x20||bad_identity||count!=2||aliases!=3){return 1;}
 for(size_t i=0;i<2;i++){if(actual[i].space!=spaces[i+1]||actual[i].identity!=(i?9:3)||actual[i].generation!=(i?103:71)){return 1;}}
 for(size_t i=0;i<3;i++){if(memcmp(allowed+i,publication+i,sizeof(Alias))){return 1;}}
 if(domain->processes[3].token!=264||domain->processes[3].incarnation!=7011
    ||domain->processes[9].token!=522||domain->processes[9].incarnation!=10319){return 1;}
 return 0;
}
static U DG hardware(U action,U request,U barrier,Reading*out){
 memset(out,0,sizeof(*out));out->cpu=current;out->if0=1;out->root=KROOT|bad_tag;
 out->cr0=UINT64_C(0x80010033);out->cr4=UINT64_C(0x20020)|bad_hardware;
 out->pat=bad_pat?UINT64_C(0x0000000600000006):PAT;out->bits=48;out->cap=2;
 out->default_type=UINT64_C(0x806);out->apic=current*2+2;
 out->request=request;out->barrier=barrier;out->action=action;
 if(bad_mtrr&&current==2){out->variable[0]=6;}
 if(bad_range){out->variable[0]=PA;out->variable[1]=MASK|2048;}
 if(request){
  if(!(gate->word&CLOSED)||!gate->drained){raw_failure="early-open-gate";return 1;}
  if(action==2){
   if(first_ack[report->round]!=7||domain->completed!=report->first){raw_failure="reclaim-without-first-ACK";return 1;}
   if(!all_aliases(1,0)){return 1;}
   if(pending()){raw_failure="retired-not-reclaimed-after-ACK";return 1;}
   for(size_t i=0;i<9;i++){for(size_t j=0;j<8;j++){if(pages[i].retired[j]){raw_failure="linear-receipt-not-consumed";return 1;}}}
   maintained[report->round]|=UINT64_C(1)<<current;
   out->operations=bad_maint&&current==2?0:3;
  }
 }
 return 0;
}
U DG user_smp_arch_if0(void){return 1;}U DG user_smp_arch_cpu(void){return current;}
U DG user_smp_arch_root(void){return KROOT|bad_tag;}
U DG user_smp_arch_try_lock(U*p){if(*p){return 0;}*p=1;return 1;}
void DG user_smp_arch_unlock(U*p){*p=0;}void DG user_smp_arch_pause(void){}
U DG user_smp_arch_clock(void){clock_value+=1000;return clock_value;}
void DG user_smp_arch_copy(U dst,U src,U n){memcpy((void*)(uintptr_t)dst,(void*)(uintptr_t)src,(size_t)n);}
void DG user_smp_arch_save(U pointer){(void)pointer;}
U DG user_smp_arch_switch(U root,U tag,U retain){(void)root;(void)tag;(void)retain;return 0;}
U DG user_smp_arch_validate(U frame,U root){(void)frame;(void)root;return 1;}
U DG user_domain_legacy_poll(void){return 0;}
U DG user_smp_arch_flush(U cpu){
 if(cpu!=current||!(gate->word&CLOSED)||gate->drained!=report->gate_token){raw_failure="flush-without-drawing-drain";return 1;}
 if(report->phase==2){if(!all_aliases(0,16)){return 1;}}
 else if(report->phase==4){
  if(!all_aliases(1,0)){return 1;}U retired=0;
  for(size_t i=0;i<9;i++){if(pages[i].retired[0]!=1){raw_failure="missing-linear-retirement";return 1;}retired+=pages[i].retired[6];}
  if(!retired||retired!=pending()){raw_failure="reclaim-before-ACK";return 1;}
  first_ack[report->round]|=UINT64_C(1)<<cpu;
 }else if(report->phase==8){
  if(maintained[report->round]!=7){raw_failure="missing-per-CPU-cache-maintenance";return 1;}
  if(!all_aliases(0,report->target)){return 1;}second_ack[report->round]|=UINT64_C(1)<<cpu;
 }else{raw_failure="unexpected-flush-phase";return 1;}
 flushes++;return 0;
}
U DG user_smp_arch_kick(U cpu){
 if(cpu>=3){return 1;}if(cpu==stop_cpu){return 0;}U old=current;current=cpu;
 U status=rc_poll(domain,cpu);current=old;return status?1:0;
}
static int atomic_gate(void){
 Gate g={0};REQUIRE(runtime_cache_gate_enter(&g)==1&&g.word==1);
 REQUIRE(runtime_cache_gate_close(&g,1)==1&&(g.word&CLOSED));
 REQUIRE(runtime_cache_gate_enter(&g)==0&&runtime_cache_gate_drain(&g,1)==0);
 REQUIRE(runtime_cache_gate_open(&g,1)==0&&runtime_cache_gate_close(&g,1)==0);
 REQUIRE(runtime_cache_gate_leave(&g)==1&&g.word==CLOSED);
 REQUIRE(runtime_cache_gate_drain(&g,1)==1&&runtime_cache_gate_drain(&g,1)==0);
 REQUIRE(runtime_cache_gate_open(&g,2)==0&&runtime_cache_gate_open(&g,1)==1);
 REQUIRE(runtime_cache_gate_open(&g,1)==0&&runtime_cache_gate_leave(&g)==0);
 REQUIRE(runtime_cache_gate_enter(&g)==1&&runtime_cache_gate_leave(&g)==1);
 g.word=UINT32_MAX;REQUIRE(runtime_cache_gate_enter(&g)==0&&g.word==UINT32_MAX);
 g.word=0;REQUIRE(runtime_cache_gate_close(&g,1)==0&&g.word==0);
 REQUIRE(runtime_cache_gate_close(&g,2)==1&&runtime_cache_gate_enter(&g)==0);
 REQUIRE(g.word==CLOSED);return 0;
}
static int setup(void){
 REQUIRE(rc_size(2)==sizeof(Page)&&rc_size(3)==sizeof(Config)&&rc_size(5)==sizeof(Reading)
         &&rc_size(6)==64&&rc_size(7)==sizeof(Reader)&&rc_size(8)==sizeof(Report));
 context=guard((size_t)rc_size(0),64);report=(Report*)(uintptr_t)rc_get(context,0);
 for(size_t i=0;i<3;i++){spaces[i]=guard(64,64);pools[i]=guard(32*4096,4096);metadata[i]=guard(32,64);
  REQUIRE(!rc_init(spaces[i],pools[i],metadata[i],KROOT+i*UINT64_C(0x100000)));}
 REQUIRE(!rc_map(spaces[0],HHDM+KROOT,KROOT,1));
 for(U i=0;i<3;i++){
  REQUIRE(!rc_map(spaces[0],HHDM+PA+i*4096,PA+i*4096,17));
  REQUIRE(!rc_map(spaces[1],UV1+i*4096,PA+i*4096,19));
  REQUIRE(!rc_map(spaces[2],UV2+i*4096,PA+i*4096,18));
 }
 roots=guard(2*sizeof(Root),64);ledger=guard(3*sizeof(Alias),64);
 for(size_t i=0;i<2;i++){memcpy((U*)pools[i+1]+1,(U*)pools[0]+1,511*8);roots[i]=(Root){spaces[i+1],i?9:3,i?103:71};}
 ledger[0]=(Alias){KROOT,UINT64_MAX,0,HHDM+PA,PA,BYTES,17,4096};
 ledger[1]=(Alias){KROOT+0x100000,3,71,UV1,PA,BYTES,19,4096};
 ledger[2]=(Alias){KROOT+0x200000,9,103,UV2,PA,BYTES,18,4096};
 memcpy(publication,ledger,sizeof publication);
 size_t n=(size_t)rc_size(4);void*arena=guard(n,64);REQUIRE(!rc_domain((U)(uintptr_t)arena,n,&domain));
 domain->lock=1;domain->owner=0;domain->cpus[0].mode=5;
 domain->processes[3]=(Process){264,7011,KROOT+0x100000,0,0,0,0};
 domain->processes[9]=(Process){522,10319,KROOT+0x200000,0,0,0,0};
 gate=guard(sizeof(Gate),64);epoch=guard(8,8);*epoch=11;boot=guard(160,8);
 boot[0]=UINT64_C(0x544f4f42474e4f44);boot[1]=1;boot[2]=160;boot[8]=PA+123;boot[9]=8192+19;
 pages=guard(16*sizeof(Page),64);config=guard(sizeof(Config),64);
 *config=(Config){domain,spaces[0],boot,{roots,2},{ledger,3},{pages,16},guard((size_t)rc_size(1),64),gate,epoch,identity,hardware,0x20,100000};
 return 0;
}
/* Work is consumed scratch; all source/context/linear receipt and publication
   bytes remain unchanged after every rejected preflight. */
static int preflight(U expected){
 unsigned char*before[32];for(size_t i=0;i<block_count;i++){before[i]=malloc(blocks[i].n);if(!before[i]){exit(96);}memcpy(before[i],blocks[i].p,blocks[i].n);}
 U code=rc_bind(context,config);if(code!=expected){return failure("preflight exact error code",__LINE__);}
 for(size_t i=0;i<block_count;i++){if(blocks[i].p!=config->work&&memcmp(before[i],blocks[i].p,blocks[i].n)){return failure("preflight failure atomicity",__LINE__);}free(before[i]);}
 return 0;
}
int main(int argc,char**argv){
 REQUIRE(argc==2);const char*scenario=argv[1];if(!strcmp(scenario,"gate")){return atomic_gate();}
 REQUIRE(!setup());
 if(!strcmp(scenario,"bad-pat")){bad_pat=1;U code=rc_bind(context,config);if(code!=ERR_HW){return failure("wrong-PAT-readback",__LINE__);}REQUIRE(!report->attempted&&gate->word==0);}
 else if(!strcmp(scenario,"bad-ledger")){ledger[2].flags=19;REQUIRE(!preflight(ERR_AUTH));}
 else if(!strcmp(scenario,"omitted-user")){config->roots.length=1;REQUIRE(!preflight(ERR_AUTH));}
 else if(!strcmp(scenario,"omitted-alias")){config->ledger.length=2;REQUIRE(!preflight(ERR_AUTH));}
 else if(!strcmp(scenario,"wrong-identity")){bad_identity=1;REQUIRE(!preflight(ERR_AUTH));}
 else if(!strcmp(scenario,"memory-generation")){roots[0].generation++;REQUIRE(!preflight(ERR_AUTH));}
 else if(!strcmp(scenario,"domain-incarnation")){domain->processes[3].incarnation++;REQUIRE(!preflight(ERR_AUTH));}
 else if(!strcmp(scenario,"PGE")){bad_hardware=128;REQUIRE(!preflight(ERR_HW));}
 else if(!strcmp(scenario,"tagged-kernel")){bad_tag=17;REQUIRE(!preflight(ERR_HW));}
 else if(!strcmp(scenario,"capacity")){config->pages.length=8;REQUIRE(!preflight(ERR_CAP));}
 else if(!strcmp(scenario,"source-overlap")){config->pages.pointer=pools[1];REQUIRE(!preflight(ERR_STORE));}
 else if(!strcmp(scenario,"returning")){domain->cpus[0].mode=6;REQUIRE(!preflight(ERR_AUTH));}
 else if(!strcmp(scenario,"active-barrier")){domain->barrier=1;REQUIRE(!preflight(ERR_AUTH));}
 else if(!strcmp(scenario,"hidden-USER")){REQUIRE(!rc_map(spaces[1],UV1+0x100000,PA,19));REQUIRE(!preflight(ERR_FOREST));}
 else if(!strcmp(scenario,"non-WB-MTRR")){bad_range=1;REQUIRE(!preflight(ERR_HW));}
 else{
  REQUIRE(!rc_bind(context,config));REQUIRE(!rc_hook(context,domain));
  if(!strcmp(scenario,"missing-ack")){stop_cpu=2;}
  else if(!strcmp(scenario,"bad-maintenance")){bad_maint=1;}
  else if(!strcmp(scenario,"mtrr-changed")){bad_mtrr=1;}
  else if(strcmp(scenario,"all")){return failure("unknown scenario",__LINE__);}
  U code=rc_run(context);
  if(raw_failure){return failure(raw_failure,__LINE__);}
  if(!strcmp(scenario,"all")){
   REQUIRE(!code&&report->complete==1&&report->poison==0&&report->committed==1&&report->held==1);
   REQUIRE(report->barriers==5&&report->linear==9&&report->revoked==18&&report->reclaimed==18&&report->remapped==18);
   REQUIRE(first_ack[1]==7&&first_ack[2]==7&&maintained[1]==7&&maintained[2]==7&&second_ack[1]==7&&second_ack[2]==7);
   REQUIRE(all_aliases(0,16)&&pending()==0&&gate->word==0&&gate->opened==1&&*epoch==12);
   Reader*r=(Reader*)(uintptr_t)rc_get(context,1);for(size_t i=0;i<3;i++){REQUIRE(r[i].reads==5&&r[i].maintenances==2&&r[i].request==r[i].acknowledged&&r[i].latest.pat==PAT);}
   REQUIRE(rc_run(context)!=0);
  }else{
   REQUIRE(code&&domain->failed==1&&report->poison==1&&report->complete==0&&report->held==1);
   REQUIRE((gate->word&CLOSED)&&gate->opened==0&&*epoch==11&&report->committed==0);
   REQUIRE(runtime_cache_gate_enter(gate)==0&&rc_run(context)!=0);
   if(!strcmp(scenario,"bad-maintenance")){REQUIRE(all_aliases(1,0)&&report->revoked==9&&report->reclaimed==9&&report->remapped==0);}
   else{REQUIRE(all_aliases(0,16)&&report->revoked==0&&pending()==0);}
  }
 }
 REQUIRE(guards());printf("runtime cache raw oracle checks=%llu scenario=%s flushes=%llu raw_samples=%llu; hardware callbacks mocked, privileged instructions not executed\n",(unsigned long long)checks,scenario,(unsigned long long)flushes,(unsigned long long)raw_samples);
 for(size_t i=0;i<block_count;i++){free(blocks[i].allocation);}return 0;
}
