// Independent catalog, graph, lifecycle and actual service_main syscall model.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(_WIN32)
#define ABI __attribute__((sysv_abi))
#else
#define ABI
#endif
typedef uint64_t U;
typedef struct { U version,id,deps,retries,timeout,flags,image,name_len; unsigned char name[32];U reserved[4];} Config;
typedef struct {U version,id,process,generation,state,status,sequence,argument;} Snapshot;
typedef struct {U version,sequence,id,generation,process,state,status,flags;} Event;
typedef struct {U generation,process,phase,attempts,deadline,status;} Node;
typedef struct {U initialized,count,now;Config configs[32];Node nodes[32];} Manager;
typedef struct {U kind,id,generation,process,reason;} Action;
typedef struct {U words[16];} Boot;
_Static_assert(sizeof(Config)==128,"config");_Static_assert(sizeof(Snapshot)==64,"snapshot");
_Static_assert(sizeof(Event)==64,"event");_Static_assert(sizeof(Manager)==5656,"manager");
extern ABI U il_validate(const Config*,U),il_initialize(const Config*,U,Manager*),il_next(Manager*,U,Action*,U*);
extern ABI U il_spawned(Manager*,U,const Snapshot*,U),il_failed(Manager*,U,U),il_adopt(Manager*,const Snapshot*,U);
extern ABI U il_killed(Manager*,U,U),il_observe(Manager*,const Event*,U*),il_deadline(const Manager*,U*),il_exhausted(const Manager*,U*);
extern ABI U service_main(void);
static U checks;
#define CK(c) do {++checks;if(!(c)){fprintf(stderr,"init lifecycle check failed line %d: %s\n",__LINE__,#c);exit(1);}} while(0)
static const U INVALID=0x05110001,CYCLE=0x05110002,STALE=0x05110003,BLOCKED=0x05110005,DEPENDENCY=0x05110006,TIMEOUT=0x05110007;
static Config config(U i,U deps) {Config c={0};c.version=1;c.id=i;c.deps=deps;c.retries=2;c.timeout=100;c.flags=1|2|4;c.image=i+1;c.name_len=3;c.name[0]='s';c.name[1]='0'+(unsigned char)(i/10);c.name[2]='0'+(unsigned char)(i%10);return c;}
static int acyclic(const Config*c,unsigned count){unsigned removed=0;for(unsigned pass=0;pass<count;pass++){int advanced=0;for(unsigned i=0;i<count;i++)if(!(removed&(1u<<i))&&!(c[i].deps&~(U)removed)){removed|=1u<<i;advanced=1;}if(removed==((1u<<count)-1))return 1;if(!advanced)return 0;}return 0;}
static void graphs(void){
 Config c[32];for(unsigned i=0;i<32;i++)c[i]=config(i,0);
 for(unsigned raw=0;raw<65536;raw++){int self=0;for(unsigned i=0;i<4;i++){c[i].deps=(raw>>(i*4))&15;if(c[i].deps&(1u<<i))self=1;}U want=self?INVALID:(acyclic(c,4)?0:CYCLE);CK(il_validate(c,4)==want);}
 for(unsigned i=0;i<32;i++)c[i]=config(i,i?UINT64_C(1)<<(i-1):0);
 CK(il_validate(c,32)==0);c[0].deps=UINT64_C(1)<<31;CK(il_validate(c,32)==CYCLE);
 CK(il_validate(NULL,32)==INVALID);CK(il_validate(c,0)==INVALID);CK(il_validate(c,33)==INVALID);
 Manager m={0};Action action={0};U found=0;for(unsigned i=0;i<32;i++)c[i]=config(i,0);
 CK(il_initialize(c,32,&m)==0);
 for(U i=0;i<32;i++){Snapshot state={1,i,0x100+i,1,2,0,0,0};CK(il_adopt(&m,&state,1)==0);}
 Event high={1,1,31,1,0x11f,3,17,0};CK(il_observe(&m,&high,&found)==0&&found==1);
 CK(il_next(&m,2,&action,&found)==0&&found==1&&action.id==31&&action.kind==1);
}
static void rejects(void){Config c[2]={config(0,0),config(1,1)};Config old=c[0];Manager m={0},before=m;for(unsigned bit=0;bit<64;bit++){c[0]=old;c[0].flags|=UINT64_C(1)<<bit;U got=il_validate(c,2);CK(got==(bit<4?0:INVALID));}c[0]=old;c[0].reserved[3]=1;CK(il_initialize(c,2,&m)==INVALID);CK(!memcmp(&m,&before,sizeof m));c[0]=old;c[0].name[3]=1;CK(il_validate(c,2)==INVALID);c[0]=old;c[0].name_len=33;CK(il_validate(c,2)==INVALID);c[0]=old;c[0].retries=9;CK(il_validate(c,2)==INVALID);c[0]=old;c[0].timeout=0;CK(il_validate(c,2)==INVALID);c[0]=old;c[0].flags=2|4;CK(il_validate(c,2)==DEPENDENCY);c[0]=old;c[0].name[0]='/';CK(il_validate(c,2)==INVALID);c[0]=old;memcpy(c[1].name,c[0].name,32);CK(il_validate(c,2)==INVALID);}
static Snapshot spawned_snapshot(U id,U generation,U process){Snapshot s={1,id,process,generation,1,0,0,0};return s;}
static Event event(U seq,U id,U generation,U process,U state,U status){Event e={1,seq,id,generation,process,state,status,0};return e;}
static void lifecycle(void){Config c[3]={config(0,0),config(1,1),config(2,2)};Manager m={0};Action a={0};U b=123,d=0;CK(il_initialize(c,3,&m)==0);CK(il_next(&m,10,&a,&b)==0&&b==1&&a.kind==1&&a.id==0&&a.generation==0);Snapshot s=spawned_snapshot(0,1,0x1234);CK(il_spawned(&m,0,&s,10)==0);CK(il_deadline(&m,&d)==0&&d==110);memset(&a,0xa5,sizeof a);Action poison=a;CK(il_next(&m,11,&a,&b)==0&&b==0&&!memcmp(&a,&poison,sizeof a));Event e=event(1,0,1,0x1234,2,0);CK(il_observe(&m,&e,&b)==0&&b==1);for(U i=1;i<3;i++){CK(il_next(&m,12+i,&a,&b)==0&&b==1&&a.id==i);s=spawned_snapshot(i,1,0x1234+i);CK(il_spawned(&m,i,&s,12+i)==0);e=event(i+1,i,1,0x1234+i,2,0);CK(il_observe(&m,&e,&b)==0&&b==1);}Manager before=m;e=event(7,0,99,0x1234,4,14);CK(il_observe(&m,&e,&b)==0&&b==0&&!memcmp(&m,&before,sizeof m));e=event(8,0,1,0x1234,4,14);CK(il_observe(&m,&e,&b)==0&&b==1);CK(il_next(&m,20,&a,&b)==0&&b==1&&a.kind==2&&a.id==1&&a.reason==DEPENDENCY);CK(il_killed(&m,1,1)==0);CK(il_next(&m,20,&a,&b)==0&&b==1&&a.kind==2&&a.id==2);CK(il_killed(&m,2,1)==0);for(U i=1;i<3;i++){e=event(8+i,i,1,0x1234+i,5,DEPENDENCY);CK(il_observe(&m,&e,&b)==0&&b==1);}CK(il_next(&m,21,&a,&b)==0&&b==1&&a.id==0&&a.generation==1);s=spawned_snapshot(0,2,0x2000);CK(il_spawned(&m,0,&s,21)==0);before=m;e=event(30,0,1,0x1234,2,0);CK(il_observe(&m,&e,&b)==0&&b==0&&!memcmp(&m,&before,sizeof m));CK(il_next(&m,121,&a,&b)==0&&b==1&&a.kind==2&&a.reason==TIMEOUT);CK(il_killed(&m,0,1)==STALE);CK(il_killed(&m,0,2)==0);e=event(31,0,2,0x2000,5,TIMEOUT);CK(il_observe(&m,&e,&b)==0&&b==1);CK(il_failed(&m,0,INVALID)==0);CK(il_exhausted(&m,&b)==0&&b==1);CK(il_next(&m,122,&a,&b)==0&&b==0);before=m;CK(il_next(&m,120,&a,&b)==INVALID&&!memcmp(&m,&before,sizeof m));}
static void adoption(void){Config c=config(0,0);Manager m={0};U b;CK(il_initialize(&c,1,&m)==0);Snapshot s={1,0,44,7,2,0,9,0};CK(il_adopt(&m,&s,20)==0);CK(m.nodes[0].phase==2&&m.nodes[0].generation==7&&m.nodes[0].process==44);Manager before=m;CK(il_adopt(&m,&s,20)==INVALID&&!memcmp(&m,&before,sizeof m));Event e=event(10,0,7,44,3,0);CK(il_observe(&m,&e,&b)==0&&b==1);Action a;CK(il_next(&m,21,&a,&b)==0&&b==1&&a.generation==7);s=spawned_snapshot(0,8,45);CK(il_spawned(&m,0,&s,21)==0);e=event(11,0,7,44,4,9);before=m;CK(il_observe(&m,&e,&b)==0&&b==0&&!memcmp(&m,&before,sizeof m));}
// The launcher test executes the production service_main and user wrappers.
// Only svc_call is substituted, emulating the kernel-admitted capability ABI.
static int main_mode;static Boot boot;static Config catalog[18];static Snapshot snapshots[18];static Event queue[16];static unsigned qhead,qtail,spawns,kills,marked,logs,config_reads;static U ticks_now,sequence;
static void enqueue(U state,U generation,U process,U status){CK(qtail<16);queue[qtail++]=event(++sequence,17,generation,process,state,status);}
ABI U svc_call(U number,U a,U b,U c,U d,U e,U f){CK(main_mode);if(number==2)return (U)(uintptr_t)&boot;if(number==0x73)return ++ticks_now;if(number==0x70){CK(b&&b<=4096);logs++;return 0;}if(number==0x84){CK(a==0x101&&b==1&&!c&&!d&&!e&&!f);marked++;return 0;}CK(a==0x999);if(number==0x80){CK(b<18&&c&&d&&!e&&!f);config_reads++;memcpy((void*)(uintptr_t)c,&catalog[b],128);memcpy((void*)(uintptr_t)d,&snapshots[b],64);return 0;}if(number==0x81){CK(b==17&&c==spawns&&!d&&e&&!f);spawns++;Snapshot s=spawned_snapshot(17,spawns,0x200+spawns);*(Snapshot*)(uintptr_t)e=s;if(spawns==1){enqueue(2,1,s.process,0);enqueue(4,1,s.process,14);}else if(spawns==2){enqueue(2,2,s.process,0);enqueue(4,1,0x201,13);enqueue(3,2,s.process,0);}else{CK(spawns==3);/* Deliberately never READY: kernel timeout wakes init. */}return 0;}if(number==0x83){CK(b==0x203&&c==TIMEOUT&&!d&&!e&&!f);kills++;enqueue(5,3,b,c);return 0;}if(number==0x82){CK(c&&d<=1&&!f);if(qhead<qtail){CK(queue[qhead].sequence>b);*(Event*)(uintptr_t)c=queue[qhead++];return 0;}if(d==0)return BLOCKED;if(spawns==3&&!kills){CK(e>ticks_now);ticks_now=e;return TIMEOUT;}CK(spawns==3&&kills==1&&marked==1&&logs>=2);return 0x051100ff;}CK(0);return INVALID;}
static void launcher(void){main_mode=1;memset(&boot,0,sizeof boot);boot.words[0]=1;boot.words[1]=6;boot.words[2]=0x101;boot.words[12]=0x999;boot.words[13]=18;boot.words[14]=1;boot.words[15]=1000000000;for(U i=0;i<18;i++){catalog[i]=config(i,i==17?3:0);if(i>=2&&i<17){catalog[i].flags=8;catalog[i].retries=0;}snapshots[i]=(Snapshot){1,i,0,0,0,0,0,0};}snapshots[0]=(Snapshot){1,0,0x111,1,2,0,0,0};snapshots[1]=(Snapshot){1,1,0x112,1,2,0,0,0};U result=service_main();CK(result==0x051100ff);CK(spawns==3&&kills==1&&qhead==qtail&&config_reads==18);main_mode=0;}
ABI void __dong_panic(void){fprintf(stderr,"unexpected Dong panic\n");exit(2);}
int main(void){graphs();rejects();lifecycle();adoption();launcher();printf("init lifecycle native checks passed %lu; exhaustive_graphs=65536; actual_launcher_spawns=%u; actual_launcher_kills=%u; launcher_config_count=18; high_configuration=31\n",(unsigned long)checks,spawns,kills);return 0;}
