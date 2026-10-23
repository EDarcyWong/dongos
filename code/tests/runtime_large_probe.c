#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
typedef uint64_t U;
#define OLD UINT64_C(0xffffa80000000000)
#define NEW (OLD+UINT64_C(0x200000))
#define PA UINT64_C(0x10000000)
#define TAG UINT64_C(0x1122334400000000)
#define MASK UINT64_C(0x0000fffffffff000)
typedef struct {U cpu,if0,root,cr4;} Env;
typedef struct {U cpu,root,cr4,value;} Sample;
typedef struct {void *space;U identity,generation;} Root;
typedef struct {U mode,token,incarnation,slot,captured_token,captured_incarnation,captured,requested,acknowledged,capture,capture_xstate,returned,return_xstate,return_root;void *seen;} Cpu;
typedef struct {U ready,failed,lock,owner,online,sequence,barrier,expected,completed,kernel_root;void *engine;Cpu *cpus;void *processes;U arena,bytes;} Domain;
typedef struct {unsigned char *all,*p;size_t n;} Guard;
extern U DG rl_size(U),rl_init(void*,void*,void*,U),rl_map(void*,U,U,U,U),rl_buddy(void*,void*,U*);
extern U DG rl_bind(void*,Domain*,void*,void*,const Root*,U,U,U(DG*)(U),void(DG*)(Env*),void(DG*)(U,Sample*),void(DG*)(U),U(DG*)(U,U));
extern U DG rl_hook(void*,Domain*),rl_run(void*),rl_step(void*,U),rl_readers(void*,U,U),rl_poll(Domain*,U),rl_get(void*,U,U);
static Guard blocks[20];static unsigned nb;
static void *ctx,*spaces[3],*pools[3],*meta[3],*allocator,*bmeta;
static Domain *domain;static Cpu *cpus;static Root roots[2];
static U current,clock_value,window_active,checks,flushes,loads,hold_ack=16,authority_bad,tag_bad;
static U cr4_value=UINT64_C(0x20000);static int occupied;
static U tag_bad_cpu=16,pge_bad_cpu=16;
static U cache_valid[3],cache_value[3],cache_physical[3],raw_seen[8],retirement_checks;
static unsigned char *payload,*original;
static int fail(const char *why,int line){fprintf(stderr,"runtime large raw oracle line %d: %s; returned normally\n",line,why);return 1;}
#define REQUIRE(x) do{++checks;if(!(x)){return fail(#x,__LINE__);}}while(0)
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const unsigned char *file,U n){
 fprintf(stderr,"unexpected Dong panic %u %u %.*s\n",kind,line,(int)n,file);exit(99);
}
static void *guard(size_t n,size_t alignment){
 unsigned char *all=calloc(n+alignment+128,1);if(!all){exit(97);}
 uintptr_t p=((uintptr_t)all+64+alignment-1)&~(alignment-1);memset((void*)(p-64),0xa7,64);memset((void*)(p+n),0x7a,64);
 blocks[nb++]=(Guard){all,(unsigned char*)p,n};return (void*)p;
}
static int guards(void){for(unsigned i=0;i<nb;i++){for(unsigned j=0;j<64;j++){if(blocks[i].p[-64+(int)j]!=0xa7||blocks[i].p[blocks[i].n+j]!=0x7a){return 0;}}}return 1;}
static U physical_table(U p){
 for(unsigned i=0;i<3;i++){U base=UINT64_C(0x4000000)+i*UINT64_C(0x100000);if(p>=base&&p<base+32*4096&&!(p&4095)){return (U)(uintptr_t)pools[i]+p-base;}}
 return 0;
}
static U translation(U va,U *leaf,U *leaf_bytes){
 U physical=UINT64_C(0x4000000);
 for(unsigned level=0;level<4;level++){
  U table=physical_table(physical);if(!table){return 0;}
  unsigned shift=39-9*level;U e=((U*)(uintptr_t)table)[(va>>shift)&511];if(!(e&1)){return 0;}
  if(level==3||(level==2&&(e&128))){U bytes=level==2?UINT64_C(0x200000):4096;
   if(leaf){*leaf=e;}if(leaf_bytes){*leaf_bytes=bytes;}return (e&MASK&~(bytes-1))+(va&(bytes-1));}
  if(e&128){return 0;}physical=e&MASK;
 }
 return 0;
}
static U value_at(U physical){if(physical<PA||physical>PA+UINT64_C(0x200000)-8){exit(96);}U value;memcpy(&value,payload+physical-PA,8);return value;}
static U raw_root(void){return domain->kernel_root|tag_bad|(current==tag_bad_cpu?17:0);}
static U raw_cr4(void){return cr4_value|(current==pge_bad_cpu?128:0);}
static void DG hardware(Env *e){*e=(Env){current,1,raw_root(),raw_cr4()};}
static void DG load_alias(U va,Sample *s){
 U physical=0;if(va==NEW+5*4096&&cache_valid[current]){physical=cache_physical[current];}
 else{physical=translation(va,0,0);if(!physical){exit(95);}if(va==NEW+5*4096){cache_physical[current]=physical;cache_value[current]=value_at(physical);cache_valid[current]=1;}}
 U value=(va==NEW+5*4096)?cache_value[current]:value_at(physical);
 *s=(Sample){current,raw_root(),raw_cr4(),value};++loads;
}
static U DG digest(U va,U bytes){U h=UINT64_C(0x4c41524745313601);if(va!=OLD||bytes!=UINT64_C(0x200000)){exit(94);}
 for(U i=0;i<bytes;i+=8){h^=value_at(translation(va+i,0,0));h=(h<<7)|(h>>57);}return h;
}
static void DG window(U active){window_active=active;}
static U DG authority(U cookie){
 U *report=(U*)(uintptr_t)rl_get(ctx,0,0);Root *actual=(Root*)(uintptr_t)report[27];
 if(cookie!=0x16||authority_bad||report[11]!=2){return 1;}
 for(unsigned i=0;i<2;i++){if(actual[i].space!=roots[i].space||actual[i].identity!=roots[i].identity||actual[i].generation!=roots[i].generation){return 1;}}
 return 0;
}
static U *leaf_pointer(U va){U physical=UINT64_C(0x4000000);
 for(unsigned level=0;level<4;level++){U table=physical_table(physical);if(!table){return 0;}U *entry=(U*)(uintptr_t)table+((va>>(39-9*level))&511);
  if(level==3){return entry;}if(!(*entry&1)||(*entry&128)){return 0;}physical=*entry&MASK;
 }return 0;
}
U DG user_smp_arch_if0(void){return 1;}U DG user_smp_arch_cpu(void){return current;}
/* Production accessor normalizes CR3; the separate real owner environment
   must reject a nonzero AP kernel tag before earning even a no-reader ACK. */
U DG user_smp_arch_root(void){return domain->kernel_root;}
U DG user_smp_arch_try_lock(U *p){if(*p){return 0;}*p=1;return 1;}
void DG user_smp_arch_unlock(U *p){*p=0;}void DG user_smp_arch_pause(void){}
U DG user_smp_arch_clock(void){clock_value+=100000;return clock_value;}
void DG user_smp_arch_copy(U d,U s,U n){memcpy((void*)(uintptr_t)d,(const void*)(uintptr_t)s,(size_t)n);}
void DG user_smp_arch_save(U p){(void)p;}
U DG user_smp_arch_switch(U r,U t,U keep){(void)r;(void)t;(void)keep;return 0;}
U DG user_smp_arch_validate(U f,U r){(void)f;(void)r;return 1;}
U DG user_domain_legacy_poll(void){return 0;}
static U audit_post(void){
 U kind=rl_get(ctx,2,0);if(!kind||domain->sequence!=rl_get(ctx,3,0)){return 0;}
 U e=0,size=0,p=translation(NEW+5*4096,&e,&size);raw_seen[kind]++;
 if(kind==1||kind==6){if(p!=PA+5*4096||size!=UINT64_C(0x200000)){return 1;}}
 if(kind==2||kind==5){if(p!=PA+5*4096||size!=4096){return 1;}}
 if(kind==3||kind==4){if(p!=PA+6*4096||size!=4096){return 1;}}
 if(kind==7&&p){return 1;}
 if(p&&((e&UINT64_C(0x800000000000001f))!=UINT64_C(0x8000000000000003))){return 1;}
 if(kind==6||kind==7){unsigned pending=0;for(unsigned i=0;i<32;i++){pending+=((unsigned char*)meta[0])[i]==2;}
  if(pending!=1){return 1;}retirement_checks++;}
 return 0;
}
U DG user_smp_arch_flush(U cpu){if(cpu!=current||audit_post()){return 1;}cache_valid[cpu]=0;flushes++;return 0;}
U DG user_smp_arch_kick(U cpu){
 if(cpu>=3){return 1;}if(cpu==hold_ack){return 0;}
 U old=current;current=cpu;U code=rl_poll(domain,cpu);current=old;return code?1:0;
}
static int setup(void){
 REQUIRE(rl_size(1)==64&&rl_size(2)==sizeof(Domain)&&rl_size(3)==sizeof(Cpu));
 ctx=guard((size_t)rl_size(0),64);domain=guard(sizeof(*domain),64);cpus=guard(16*sizeof(*cpus),64);
 for(unsigned i=0;i<3;i++){
  spaces[i]=guard(64,64);pools[i]=guard(32*4096,4096);meta[i]=guard(32,64);
  REQUIRE(!rl_init(spaces[i],pools[i],meta[i],UINT64_C(0x4000000)+i*UINT64_C(0x100000)));
 }
 allocator=guard((size_t)rl_size(5),64);bmeta=guard(1024*(size_t)rl_size(6),64);U physical=0;
 REQUIRE(!rl_buddy(allocator,bmeta,&physical)&&physical==PA);
 REQUIRE(!rl_map(spaces[0],OLD,PA,1,1));
 for(unsigned i=1;i<3;i++){
  REQUIRE(!rl_map(spaces[i],UINT64_C(0x40000000)+(U)i*4096,UINT64_C(0x20000000)+(U)i*4096,3,0));
  memcpy((U*)pools[i]+1,(U*)pools[0]+1,511*8);roots[i-1]=(Root){spaces[i],i-1,101+i};
 }
 domain->ready=1;domain->lock=1;domain->online=7;domain->kernel_root=UINT64_C(0x4000000);domain->cpus=cpus;
 for(unsigned i=0;i<3;i++){cpus[i].mode=i?4:5;cpus[i].slot=16;cpus[i].seen=guard(384,64);}
 payload=guard(0x200000,64);original=malloc(0x200000);REQUIRE(original!=0);
 for(U i=0;i<512;i++){for(U j=0;j<4096;j+=8){U v=(TAG|i)^((j/8)<<32);memcpy(payload+i*4096+j,&v,8);}}
 memcpy(original,payload,0x200000);
 if(occupied){
  REQUIRE(!rl_map(spaces[0],NEW+4096,UINT64_C(0x22000000),1,0));
  unsigned char before[32*4096];memcpy(before,pools[0],sizeof(before));
  REQUIRE(rl_bind(ctx,domain,spaces[0],allocator,roots,2,PA,authority,hardware,load_alias,window,digest)!=0);
  REQUIRE(!memcmp(before,pools[0],sizeof(before)));return 0;
 }
 REQUIRE(!rl_bind(ctx,domain,spaces[0],allocator,roots,2,PA,authority,hardware,load_alias,window,digest));
 REQUIRE(!rl_hook(ctx,domain));return 0;
}
int main(int argc,char **argv){
 const char *scenario=argc>1?argv[1]:"all";occupied=!strcmp(scenario,"occupied-window");
 if(!strcmp(scenario,"all-untagged")){cr4_value=0;}
 if(setup()){return 1;}
 if(occupied){REQUIRE(guards());puts("runtime large raw oracle: hidden second-page mapping rejected; no privileged instructions executed");return 0;}
 if(!strcmp(scenario,"null-callbacks")){
  void *fresh=guard((size_t)rl_size(0),64);
  for(unsigned i=0;i<5;i++){
   REQUIRE(rl_bind(fresh,domain,spaces[0],allocator,roots,2,PA,i==0?0:authority,i==1?0:hardware,i==2?0:load_alias,i==3?0:window,i==4?0:digest)!=0);
   for(U at=0;at<rl_size(0);at++){REQUIRE(!((unsigned char*)fresh)[at]);}
  }
 }else if(!strcmp(scenario,"all")||!strcmp(scenario,"all-untagged")){
  U code=rl_run(ctx);if(code){return fail("lifecycle, stale reader, or ACK-before-reclaim",__LINE__);}
  REQUIRE(rl_get(ctx,8,0)==1&&rl_get(ctx,9,0)==0&&rl_get(ctx,7,0)==0&&rl_get(ctx,10,0)==127);
  REQUIRE(rl_get(ctx,4,0)==16&&rl_get(ctx,5,0)==2&&rl_get(ctx,6,0)==2);
  REQUIRE(rl_get(ctx,11,0)==rl_get(ctx,12,0)&&rl_get(ctx,13,0)==rl_get(ctx,14,0));
  REQUIRE(flushes==48&&retirement_checks==6&&window_active==0);
  for(unsigned i=0;i<3;i++){REQUIRE(rl_get(ctx,15,i)==4&&rl_get(ctx,16,i)==(TAG|6));}
  for(unsigned i=1;i<8;i++){REQUIRE(raw_seen[i]>=3);}
  REQUIRE(!translation(NEW,0,0)&&translation(OLD+5*4096,0,0)==PA+5*4096);
 }else{
  REQUIRE(!rl_step(ctx,1)&&!rl_step(ctx,2));
  unsigned char before[32*4096];memcpy(before,pools[0],sizeof(before));
  if(!strcmp(scenario,"authority")){authority_bad=1;}
  else if(!strcmp(scenario,"omitted-root")){((U*)(uintptr_t)rl_get(ctx,0,0))[11]=1;}
  else if(!strcmp(scenario,"generation")){Root *p=(Root*)(uintptr_t)((U*)(uintptr_t)rl_get(ctx,0,0))[27];p[1].generation++;}
  else if(!strcmp(scenario,"shared-slot")){((U*)pools[1])[1]=32;}
  else if(!strcmp(scenario,"wrong-cpu")){current=1;}
  else if(!strcmp(scenario,"kernel-tag")){tag_bad=17;}
  else if(!strcmp(scenario,"ap-kernel-tag")){tag_bad_cpu=1;}
  else if(!strcmp(scenario,"ap-pge")){pge_bad_cpu=1;}
  else if(!strcmp(scenario,"returning")){cpus[1].mode=6;}
  else if(!strcmp(scenario,"missing-ack")){hold_ack=1;}
  else if(!strcmp(scenario,"old-window")){((U*)payload)[5*512]^=1;}
  else if(!strcmp(scenario,"new-third-party")){*leaf_pointer(NEW+4096)=UINT64_C(0x8000000022000003);memcpy(before,pools[0],sizeof(before));}
  else if(!strcmp(scenario,"new-hole")){*leaf_pointer(NEW+4096)=0;memcpy(before,pools[0],sizeof(before));}
  else if(!strcmp(scenario,"new-permission")){*leaf_pointer(NEW+4096)&=~UINT64_C(2);memcpy(before,pools[0],sizeof(before));}
  else{return fail("unknown scenario",__LINE__);}
  U code=rl_step(ctx,3);REQUIRE(code&&rl_get(ctx,9,0)==1&&domain->failed==1);
  REQUIRE(!memcmp(before,pools[0],sizeof(before))&&translation(NEW+5*4096,0,0)==PA+5*4096);
 }
 if(strcmp(scenario,"old-window")){REQUIRE(!memcmp(original,payload,0x200000));}
 REQUIRE(guards());printf("runtime large raw oracle checks=%llu scenario=%s flushes=%llu loads=%llu; callbacks mocked, no privileged instructions executed\n",(unsigned long long)checks,scenario,(unsigned long long)flushes,(unsigned long long)loads);
 for(unsigned i=0;i<nb;i++){free(blocks[i].all);}free(original);return 0;
}
