#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define SYSV __attribute__((sysv_abi))
#define INVALID 0x050c0002ULL
#define DENIED 0x050c0003ULL
#define NOSPACE 0x050c0004ULL
#define ARG 0x050c0001ULL
#define MAXGEN 0xffffffULL
typedef struct {uint64_t generation,live,owner,rights,kind,length,sector,offset;uint8_t alias[11],path[1024];} Entry;
typedef struct {uint64_t ready,epoch,used;Entry entries[32];} Table;
typedef struct {uint64_t before[4];Table value;uint64_t after[4];} Guarded;
extern uint64_t SYSV fsh_init(Table*,uint64_t),fsh_install(Table*,uint64_t,uint64_t,uint64_t,const uint8_t*,uint64_t,uint64_t,uint64_t,const uint8_t*,uint64_t*),fsh_lookup(Table*,uint64_t,uint64_t,uint64_t,uint64_t*),fsh_close(Table*,uint64_t,uint64_t),fsh_dup(Table*,uint64_t,uint64_t,uint64_t,uint64_t*);
extern void SYSV fsh_owner(Table*,uint64_t),fsh_namespace(Table*);
static Guarded g;static Table model,snapshot;static uint64_t checks,seed=0x9e3779b97f4a7c15ULL,negative_hits;
static const uint8_t alias[11]="IDENTITYTXT",path[]="/directory/file.txt";
#define CHECK(x) do {checks++;if(!(x)){fprintf(stderr,"FSH_MODEL_ASSERT line %u checks=%llu marked=%llu\n",__LINE__,(unsigned long long)checks,(unsigned long long)negative_hits);return 1;}}while(0)
void SYSV __dong_panic(uint64_t code,const char*p,uint64_t n){(void)p;(void)n;fprintf(stderr,"unexpected panic %llu\n",(unsigned long long)code);exit(9);}
void SYSV fsh_negative_hit(uint64_t kind){negative_hits++;fprintf(stderr,"FSH_NEGATIVE_HIT %llu\n",(unsigned long long)kind);}
static uint64_t random64(void){seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;return seed;}
static uint64_t token(unsigned slot){return (model.epoch<<32)|(model.entries[slot].generation<<8)|(slot+1);}
static uint64_t index_of(uint64_t owner,uint64_t t,uint64_t required,unsigned*out){
 unsigned slot=(unsigned)(t&255);if(!owner||!slot||slot>32||!((t>>8)&MAXGEN)||(t>>32)!=model.epoch)return INVALID;
 Entry*e=&model.entries[slot-1];if(!e->live||e->generation!=((t>>8)&MAXGEN))return INVALID;
 if(e->owner!=owner||(required&~e->rights)){return DENIED;}*out=slot-1;return 0;
}
static void revoke(unsigned slot){Entry*e=&model.entries[slot];e->live=0;e->owner=0;e->rights=0;e->generation++;model.used--;}
static int same(void){
 CHECK(g.value.ready==model.ready&&g.value.epoch==model.epoch&&g.value.used==model.used);
 for(unsigned i=0;i<32;i++){Entry*a=&g.value.entries[i],*b=&model.entries[i];CHECK(a->generation==b->generation&&a->live==b->live);if(b->live){CHECK(a->owner==b->owner&&a->rights==b->rights&&a->kind==b->kind&&a->length==b->length&&a->sector==b->sector&&a->offset==b->offset);CHECK(!memcmp(a->alias,b->alias,11)&&!memcmp(a->path,b->path,b->length));}}
 for(unsigned i=0;i<4;i++){CHECK(g.before[i]==0x123456789abcdef0ULL&&g.after[i]==0xfedcba9876543210ULL);}return 0;
}
static void install_model(unsigned slot,uint64_t owner,uint64_t kind,uint64_t rights){Entry*e=&model.entries[slot];e->live=1;e->owner=owner;e->kind=kind;e->rights=rights;e->length=sizeof path-1;e->sector=123;e->offset=96;memcpy(e->alias,alias,11);memcpy(e->path,path,sizeof path-1);model.used++;}
static unsigned empty_slot(void){for(unsigned i=0;i<32;i++)if(!model.entries[i].live&&model.entries[i].generation<MAXGEN)return i;return 32;}
int main(void){
 CHECK(sizeof(Entry)==1104&&sizeof(Table)==35352);memset(&g,0,sizeof g);for(unsigned i=0;i<4;i++){g.before[i]=0x123456789abcdef0ULL;g.after[i]=0xfedcba9876543210ULL;}
 CHECK(!fsh_init(&g.value,37));model.ready=1;model.epoch=37;for(unsigned i=0;i<32;i++)model.entries[i].generation=1;CHECK(!same());snapshot=g.value;CHECK(fsh_init(&g.value,38)==ARG&&!memcmp(&snapshot,&g.value,sizeof snapshot));
 uint64_t historical[4096]={0};unsigned history=0;
 for(unsigned step=0;step<20000;step++){
  uint64_t action=random64()%8,owner=(random64()%3)+1,out=0xa55a55a55a55a55aULL,expected=0,actual=0;unsigned slot=(unsigned)(random64()%32),found=0;uint64_t t=token(slot),rights=random64()&1023;
  if(step%5==0&&history){t=historical[random64()%history];}snapshot=g.value;
  if(action==0){unsigned vacant=empty_slot();uint64_t kind=random64()%3+1;if(!rights)rights=1;actual=fsh_install(&g.value,owner,kind,rights,path,sizeof path-1,123,96,alias,&out);if(vacant==32)expected=NOSPACE;else{uint64_t minted=token(vacant);install_model(vacant,owner,kind,rights);CHECK(out==minted);historical[history++%4096]=out;if(history>=4096)history=4096;}}
  else if(action==1||action==2){expected=index_of(owner,t,action==1?rights:0,&found);actual=action==1?fsh_lookup(&g.value,owner,t,rights,&out):fsh_close(&g.value,owner,t);if(!expected&&action==1)CHECK(out==found);if(!expected&&action==2)revoke(found);}
  else if(action==3){expected=index_of(owner,t,128,&found);if(!expected&&(!rights||(rights&~model.entries[found].rights)))expected=DENIED;unsigned vacant=empty_slot();if(!expected&&vacant==32)expected=NOSPACE;actual=fsh_dup(&g.value,owner,t,rights,&out);if(!expected){Entry original=model.entries[found];uint64_t minted=token(vacant);model.entries[vacant]=original;model.entries[vacant].generation=(minted>>8)&MAXGEN;model.entries[vacant].rights=rights;model.used++;CHECK(out==minted);}}
  else if(action==4){fsh_owner(&g.value,owner);for(unsigned i=0;i<32;i++)if(model.entries[i].live&&model.entries[i].owner==owner)revoke(i);}
  else if(action==5){fsh_namespace(&g.value);for(unsigned i=0;i<32;i++)if(model.entries[i].live&&model.entries[i].kind!=3)revoke(i);}
  else if(action==6){expected=INVALID;actual=fsh_lookup(&g.value,owner,t^(1ULL<<32),0,&out);}
  else{expected=ARG;actual=fsh_install(&g.value,0,1,1,path,sizeof path-1,123,96,alias,&out);}
  CHECK(actual==expected);if(expected){CHECK(!memcmp(&snapshot,&g.value,sizeof snapshot));CHECK(out==0xa55a55a55a55a55aULL);}CHECK(!same());
 }
 // An attacker with the exact token still needs the authenticated owner.
 fsh_owner(&g.value,1);for(unsigned i=0;i<32;i++)if(model.entries[i].live&&model.entries[i].owner==1)revoke(i);
 unsigned vacant=empty_slot();CHECK(vacant<32);uint64_t mine=0,got=0;CHECK(!fsh_install(&g.value,1,1,3,path,sizeof path-1,123,96,alias,&mine));install_model(vacant,1,1,3);CHECK(fsh_lookup(&g.value,2,mine,1,&got)==DENIED);CHECK(fsh_lookup(&g.value,1,mine,4,&got)==DENIED);CHECK(fsh_lookup(&g.value,1,mine^(1ULL<<32),0,&got)==INVALID);CHECK(!same());
 // Generation exhaustion retires all slots, preserving the table and output.
 for(unsigned i=0;i<32;i++){g.value.entries[i].live=0;g.value.entries[i].generation=MAXGEN;}g.value.used=0;snapshot=g.value;got=0x55;CHECK(fsh_install(&g.value,1,1,1,path,sizeof path-1,123,96,alias,&got)==NOSPACE&&got==0x55&&!memcmp(&snapshot,&g.value,sizeof snapshot));
 printf("FS handles independent model passed checks=%llu steps=20000 guardbytes=ok\n",(unsigned long long)checks);return 0;
}
