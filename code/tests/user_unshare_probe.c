#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI unshare_setup(uint64_t,uint64_t,uint64_t,uint64_t),unshare_kernel_setup(uint64_t,uint64_t,uint64_t);
extern uint64_t ABI unshare_run(uint64_t,uint64_t,uint64_t),unshare_get(uint64_t,uint64_t),unshare_leaf(uint64_t,uint64_t);
extern uint64_t ABI unshare_change(uint64_t),unshare_kernel_flags(uint64_t),unshare_snapshot(uint64_t,void*);
extern uint64_t ABI unshare_stale_receipt(void),unshare_fresh(void),unshare_stage_rejected(void),unshare_drop_alias(uint64_t);
extern uint64_t ABI unshare_resources_calls(void),unshare_allocate(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
extern uint64_t ABI unshare_journal_count(void),unshare_fill_tables(uint64_t),unshare_alias_collision(uint64_t);
extern void ABI unshare_resources_setup(uint64_t),unshare_corrupt_receipt(uint64_t),unshare_reusable(uint64_t);
static unsigned checks,flushes,reclaims,zero_receipts,watch,injection,injected,withdrawn;
static uint64_t alias,scratch,current_root,watched_id,watched_base,watched_pages;
static void die(const char*why){fprintf(stderr,"unshare ordering failed: %s\n",why);exit(1);}
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"unshare check line %u: %s\n",__LINE__,#x);return 1;}}while(0)
void ABI __dong_panic(void){die("Dong panic");}
uint64_t ABI user_current_root(void){return current_root;}
uint64_t ABI user_pcid_bind(uint64_t a,uint64_t b,uint64_t c){(void)a;(void)b;(void)c;die("unexpected bind");return 0;}
uint64_t ABI user_pcid_unbind(uint64_t a,uint64_t b){(void)a;(void)b;die("unexpected unbind");return 0;}
uint64_t ABI user_entropy64(void*a,void*b){(void)a;(void)b;die("unexpected entropy");return 0;}
void ABI runtime_copy_bytes(void*d,const void*s,uint64_t n){memcpy(d,s,(size_t)n);}
void ABI runtime_invalidate(uint64_t va){if(injection==3&&!injected&&va==alias){injected=1;if(unshare_drop_alias(alias+4096))die("late protect injection failed");}}
void ABI user_pcid_invalidate_root(uint64_t root){if(root!=0x100000&&root!=0x120000)die("wrong invalidated root");}
void ABI user_pcid_flush_all(void){
 ++flushes;
 if(!watch)return;
 for(uint64_t i=0;i<watched_pages;i++)if(unshare_leaf(watched_id,watched_base+i*4096))die("partial USER withdrawal before barrier");
 withdrawn=1;
 if(!injected&&(injection==1||injection==2)){injected=1;if(injection==1)unshare_corrupt_receipt(1);else if(unshare_drop_alias(alias+4096))die("late alias injection failed");}
}
void ABI unshare_reclaim_event(uint64_t pending,uint64_t count,uint64_t root){
 (void)root;
 if(!pending||!flushes)die("receipt reclaimed without pending/barrier");
 if(watch&&!withdrawn)die("reclaim before complete withdrawal");
 ++reclaims;if(!count)++zero_receipts;
}
static int setup(unsigned count,unsigned shared,unsigned ro){
 memset((void*)(uintptr_t)alias,0xa5,1024*4096);
 memset((void*)(uintptr_t)scratch,0,11*4096);memset((void*)(uintptr_t)(scratch+11*4096),0xcd,4096);
 current_root=0;watch=flushes=reclaims=zero_receipts=injection=injected=withdrawn=0;
 unshare_resources_setup(scratch);CHECK(!unshare_setup(alias,count,shared,ro));CHECK(!unshare_kernel_setup(alias,count,ro));return 0;
}
static void observe(unsigned id,uint64_t base,unsigned count){watch=1;watched_id=id;watched_base=base;watched_pages=count;withdrawn=0;}
static int zero(unsigned index){for(unsigned b=0;b<4096;b++)CHECK(!*((unsigned char*)(uintptr_t)alias+index*4096+b));return 0;}
static int marker(unsigned index){for(unsigned b=0;b<4096;b++)CHECK(*((unsigned char*)(uintptr_t)alias+index*4096+b)==0xa5);return 0;}
static int guard(void){for(unsigned b=0;b<4096;b++)CHECK(*((unsigned char*)(uintptr_t)scratch+11*4096+b)==0xcd);return 0;}
static int sharing(void){
 CHECK(!setup(4,1,0));observe(0,0x44000000,4);CHECK(!unshare_run(0,0x44000000,4));
 CHECK(reclaims==4&&zero_receipts==3&&unshare_resources_calls()==1);
 for(unsigned i=0;i<4;i++){CHECK(!unshare_leaf(0,0x44000000+i*4096));CHECK(unshare_leaf(1,0x45000000+i*4096));CHECK(!unshare_get(0,i)&&!unshare_get(6,i));CHECK(!marker(i));}
 CHECK(!unshare_kernel_flags(alias));observe(1,0x45000000,4);CHECK(!unshare_run(1,0x45000000,4));
 CHECK(reclaims==8&&unshare_resources_calls()==1&&unshare_kernel_flags(alias)==1);
 for(unsigned i=0;i<4;i++){CHECK(unshare_get(0,i)==1&&unshare_get(1,i)==1&&!unshare_get(6,i));CHECK(!zero(i));}
 memset((void*)(uintptr_t)alias,0xcc,4096);watch=0;CHECK(unshare_fresh()==0);CHECK(!zero(0));CHECK(!guard());
 CHECK(!setup(4,0,0));CHECK(!unshare_change(8));observe(0,0x44000000,4);CHECK(!unshare_run(0,0x44000000,4));
 CHECK(!unshare_get(0,0));CHECK(!marker(0));for(unsigned i=1;i<4;i++){CHECK(unshare_get(0,i)==1);CHECK(!zero(i));}
 observe(0,0x46000000,1);CHECK(!unshare_run(0,0x46000000,1));CHECK(unshare_get(0,0)==1);CHECK(!zero(0));
 CHECK(!setup(2,0,0));CHECK(!unshare_change(9));observe(0,0x44000000,2);CHECK(!unshare_run(0,0x44000000,2));
 CHECK(unshare_get(0,0)==1&&!unshare_get(0,1));CHECK(!zero(0));CHECK(!marker(1));
 CHECK(!setup(768,0,0));observe(0,0x44000000,768);CHECK(!unshare_run(0,0x44000000,768));
 CHECK(reclaims==768&&zero_receipts>760&&unshare_resources_calls()==1);for(unsigned i=0;i<768;i++){CHECK(unshare_get(0,i)==1&&!unshare_get(6,i));CHECK(!zero(i));}CHECK(!guard());return 0;
}
static int rejected(void){
 unsigned char before[140000],after[140000];
 for(unsigned variant=0;variant<16;variant++){
  CHECK(!setup(4,1,0));uint64_t id=0,base=0x44000000,count=4;
  if(variant<7)CHECK(!unshare_change(variant+1));
  if(variant==7){count=0;}if(variant==8){count=769;}if(variant==9){base++;}
  if(variant==10){base=0;}if(variant==11){base=UINT64_MAX-4095;}if(variant==12){id=16;}
  if(variant==13){current_root=0x100000;}if(variant==14){base=0x7ffffff000;}if(variant==15){count=UINT64_MAX;}
  uint64_t length=unshare_snapshot(0,before);CHECK(length<sizeof(before));
  CHECK(unshare_run(id,base,count)!=0);CHECK(unshare_snapshot(0,after)==length);CHECK(!memcmp(before,after,(size_t)length));
  CHECK(!unshare_get(2,0)&&!unshare_get(3,0)&&!unshare_resources_calls());
  for(unsigned i=0;i<4;i++){CHECK(unshare_get(0,i)==(variant==3&&i==1?2:0));CHECK(!marker(i));}
 }
 return 0;
}
static int failures(void){
 CHECK(!setup(4,0,1));observe(0,0x44000000,4);injection=1;CHECK(unshare_run(0,0x44000000,4)!=0);
 CHECK(unshare_get(2,0)&&unshare_get(3,0)&&!unshare_get(6,0)&&unshare_get(6,1));
 for(unsigned i=0;i<4;i++){CHECK(!unshare_get(0,i));CHECK(!marker(i));}
 CHECK(unshare_run(0,0x44000000,4)==0x04060001&&unshare_stage_rejected()==0x04060001&&unshare_fresh()==0x04060001);
 CHECK(!setup(4,0,1));observe(0,0x44000000,4);injection=2;CHECK(unshare_run(0,0x44000000,4)!=0);
 CHECK(unshare_get(2,0)&&unshare_get(3,0));for(unsigned i=0;i<4;i++){CHECK(unshare_get(0,i)!=1);CHECK(!marker(i));}
 CHECK(!setup(4,0,1));observe(0,0x44000000,4);injection=3;CHECK(unshare_run(0,0x44000000,4)!=0);
 CHECK(injected&&unshare_get(2,0)&&unshare_get(1,0)==1);for(unsigned i=0;i<4;i++){CHECK(unshare_get(0,i)!=1);CHECK(!marker(i));}
 CHECK(!setup(4,0,0));CHECK(!unshare_stale_receipt());CHECK(unshare_get(6,0));
 CHECK(unshare_run(0,0x44000000,4)!=0);CHECK(unshare_get(2,0)&&unshare_get(3,0)&&unshare_get(6,0));
 for(unsigned i=0;i<4;i++){CHECK(unshare_leaf(0,0x44000000+i*4096));CHECK(!unshare_get(0,i));CHECK(!marker(i));}CHECK(!reclaims);return 0;
}
static int allocation(void){
 CHECK(!setup(4,0,0));observe(0,0x44000000,4);CHECK(!unshare_run(0,0x44000000,4));watch=0;
 CHECK(!unshare_allocate(0,1,0x48000000,0x49000000,4));CHECK(unshare_journal_count()==4&&!unshare_get(2,0)&&!unshare_get(3,0));
 for(unsigned i=0;i<4;i++){uint64_t a=unshare_leaf(0,0x48000000+i*4096),b=unshare_leaf(1,0x49000000+i*4096);CHECK(a==b&&a==(0x200000+i*4096+3));CHECK(!unshare_get(0,i));CHECK(!zero(i));}
 observe(0,0x48000000,4);CHECK(!unshare_run(0,0x48000000,4));observe(1,0x49000000,4);CHECK(!unshare_run(1,0x49000000,4));
 for(unsigned i=0;i<4;i++){CHECK(unshare_get(0,i)==1);}CHECK(unshare_resources_calls()==1);CHECK(!guard());
 CHECK(!setup(4,0,0));CHECK(unshare_allocate(0,1,0x48000000,0x45000000,0)!=0); /* zero count rejected */
 CHECK(!unshare_resources_calls());CHECK(unshare_allocate(0,1,0x44000000,0x45000000,4)!=0);CHECK(!unshare_resources_calls());
 CHECK(!setup(4,0,0));observe(0,0x44000000,4);CHECK(!unshare_run(0,0x44000000,4));watch=0;CHECK(!unshare_fill_tables(1));
 CHECK(unshare_allocate(0,1,0x48000000,0x49000000,4)!=0);CHECK(!unshare_get(2,0)&&!unshare_get(3,0)&&unshare_journal_count()==1);
 for(unsigned i=0;i<4;i++){CHECK(!unshare_leaf(0,0x48000000+i*4096)&&!unshare_leaf(1,0x49000000+i*4096));CHECK(unshare_get(0,i)==1);CHECK(!zero(i));}
 CHECK(!setup(4,0,0));observe(0,0x44000000,4);CHECK(!unshare_run(0,0x44000000,4));watch=0;CHECK(!unshare_fill_tables(1));
 CHECK(unshare_allocate(0,1,0x48000000,UINT64_C(0x10001ff000),4)!=0);
 CHECK(!unshare_get(2,0)&&!unshare_get(3,0)&&unshare_journal_count()==2);
 for(unsigned i=0;i<4;i++){CHECK(!unshare_leaf(0,0x48000000+i*4096)&&!unshare_leaf(1,UINT64_C(0x10001ff000)+i*4096));CHECK(unshare_get(0,i)==1);CHECK(!zero(i));}
 /* New Frame journaled before supervisor alias collision, no returned index. */
 CHECK(!setup(4,0,0));CHECK(!unshare_alias_collision(4));CHECK(unshare_allocate(0,1,0x48000000,0x49000000,1)!=0);
 CHECK(unshare_journal_count()==1&&unshare_get(9,0)==5&&unshare_get(2,0)&&unshare_get(3,0));CHECK(!unshare_get(0,4));
 CHECK(unshare_stage_rejected()==0x04060001&&unshare_fresh()==0x04060001);return 0;
}
int main(void){
#ifdef _WIN32
 void*ram=_aligned_malloc(1024*4096,4096),*storage=_aligned_malloc(12*4096,4096);
#else
 void*ram=aligned_alloc(4096,1024*4096),*storage=aligned_alloc(4096,12*4096);
#endif
 CHECK(ram&&storage);alias=(uint64_t)(uintptr_t)ram;scratch=(uint64_t)(uintptr_t)storage;
 if(sharing()||rejected()||failures()||allocation())return 1;
 printf("user unshare checks passed %u; real linear receipts, shared last reference, allocation rollback\n",checks);return 0;
}
