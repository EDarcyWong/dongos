#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif
#define SYSV __attribute__((sysv_abi))
extern void SYSV reclaim_setup(uint64_t);
extern uint64_t SYSV reclaim_destroy(uint64_t),reclaim_state(uint64_t),reclaim_writable(uint64_t),reclaim_root_entry(uint64_t),reclaim_ready(uint64_t),reclaim_fresh(void),reclaim_kernel_setup(uint64_t),reclaim_kernel_flags(uint64_t);
extern uint64_t SYSV reclaim_alias_setup(void),reclaim_alias(uint64_t,uint64_t,uint64_t,uint64_t*);
extern void SYSV reclaim_set_writable(uint64_t,uint64_t);
extern uint64_t SYSV reclaim_share_at(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t),reclaim_share_same(uint64_t),reclaim_tables_snapshot(uint64_t,void*);
typedef struct{uint64_t physical,virtual_,writable;} Frame;
extern uint64_t SYSV reclaim_reference_calls(void);
extern void SYSV reclaim_large(Frame*,unsigned char*);
static Frame large_frames[6200];static unsigned char large_states[6200];
static uint64_t current_root;
static unsigned flushes,invalidations,unbinds,checks,failed_unbind;
static uint64_t alias;
static unsigned sharing,root_invalidations;
static uint64_t expected_target,expected_root;
static void die(const char*why){fprintf(stderr,"reclaim ordering failed %s\n",why);exit(1);}
uint64_t SYSV user_current_root(void){return current_root;}
void SYSV user_pcid_flush_all(void){
 if(reclaim_ready(0)&&reclaim_ready(1))die("nothing detached before barrier");
 if(!reclaim_ready(0)&&reclaim_root_entry(0))die("USER root still published at barrier");
 ++flushes;
}
uint64_t SYSV user_pcid_unbind(uint64_t id,uint64_t root){
 if(!flushes||reclaim_ready(id)||reclaim_root_entry(id)||root!=0x100000+id*0x20000)die("unbind before detach/barrier");
 ++unbinds;return !failed_unbind;
}
void SYSV runtime_invalidate(uint64_t va){
 if(sharing){if(va!=expected_target)die("wrong share target invalidation");}
 else if(!flushes||va!=alias)die("write alias before flush");
 ++invalidations;
}
void SYSV user_pcid_invalidate_root(uint64_t root){if(!sharing||root!=expected_root)die("wrong share target context invalidation");++root_invalidations;}
void SYSV runtime_copy_bytes(void*d,const void*s,uint64_t bytes){memcpy(d,s,(size_t)bytes);}
void SYSV __dong_panic(void){die("Dong panic");}
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"reclaim check failed line %u\n",__LINE__);return 1;}}while(0)
static void reset(void){
 flushes=invalidations=unbinds=failed_unbind=root_invalidations=sharing=0;current_root=0;
 memset((void*)(uintptr_t)alias,0xa5,16384);reclaim_setup(alias);
 if(reclaim_kernel_setup(alias))die("native page-table setup");
}
enum{SNAPSHOT=32*4096+32+64};
static unsigned char before_tables[2][SNAPSHOT],after_tables[2][SNAPSHOT];
static uint64_t target_leaf(uint64_t virtual){
 uint64_t root=0x120000,current=root;unsigned char raw[SNAPSHOT];
 if(reclaim_tables_snapshot(1,raw)!=SNAPSHOT)die("private table snapshot ABI");
 const unsigned shifts[]={39,30,21,12};
 for(unsigned i=0;i<4;i++){
  if(current<root||current>=root+32*4096||(current&4095))die("shared PTE outside target private pool");
  uint64_t value;memcpy(&value,raw+(current-root)+((virtual>>shifts[i])&511)*8,8);
  if(!(value&1))return 0;
  if(!(value&4))die("shared mapping not effectively USER");
  if(i==3)return value;
  if(value&128)die("unexpected shared large mapping");
  current=value&UINT64_C(0x000ffffffffff000);
 }
 die("missing shared leaf");return 0;
}
static void reject_share(unsigned source,unsigned target,uint64_t from,uint64_t to,unsigned write,uint64_t code){
 for(unsigned id=0;id<2;id++)if(reclaim_tables_snapshot(id,before_tables[id])!=SNAPSHOT)die("snapshot size");
 unsigned saved=invalidations,saved_root=root_invalidations;
 if(reclaim_share_at(source,target,from,to,write)!=code)die("incorrect share rejection status");
 for(unsigned id=0;id<2;id++){
  reclaim_tables_snapshot(id,after_tables[id]);
  if(memcmp(before_tables[id],after_tables[id],SNAPSHOT))die("rejected share mutated source/target table or metadata");
 }
 if(invalidations!=saved||root_invalidations!=saved_root)die("rejected share issued invalidation");
 ++checks;
}
int main(void){
 void*page;
#ifdef _WIN32
 page=_aligned_malloc(6200*4096,4096);
#else
 page=aligned_alloc(4096,6200*4096);
#endif
 CHECK(page!=NULL);alias=(uint64_t)(uintptr_t)page;reset();
 CHECK(!reclaim_alias_setup());uint64_t borrowed=0xabc314;
 CHECK(!reclaim_alias(0,0x10000000,0,&borrowed)&&borrowed==alias);
 CHECK(!reclaim_alias(0,0x10000fff,0,&borrowed)&&borrowed==alias+4095);
 CHECK(!reclaim_alias(0,0x10001abc,1,&borrowed)&&borrowed==alias+4096+0xabc);
 borrowed=0xabc314;CHECK(reclaim_alias(0,0x10000000,1,&borrowed)==0x04060004&&borrowed==0xabc314);
 reclaim_set_writable(1,0);CHECK(reclaim_alias(0,0x10001000,1,&borrowed)==0x04060004&&borrowed==0xabc314);reclaim_set_writable(1,1);
 CHECK(reclaim_alias(0,0x60000000,1,&borrowed)==0x04060005&&borrowed==0xabc314);
 CHECK(reclaim_alias(0,0x70001000,0,&borrowed)==0x04060005&&borrowed==0xabc314);
 CHECK(reclaim_alias(16,0x10000000,0,&borrowed)==0x04060003&&borrowed==0xabc314);
 CHECK(reclaim_alias(0,UINT64_MAX,0,&borrowed)==0x04060003&&borrowed==0xabc314);
 sharing=1;expected_target=0x44000000;expected_root=0x120000;
 CHECK(!reclaim_share_at(0,1,0x10001000,expected_target,1));
 CHECK(target_leaf(expected_target)==UINT64_C(0x8000000000201007)&&invalidations==1&&root_invalidations==1);
 expected_target=0x44001000;CHECK(!reclaim_share_at(0,1,0x10001000,expected_target,0));CHECK(target_leaf(expected_target)==UINT64_C(0x8000000000201005));
 expected_target=0x44002000;CHECK(!reclaim_share_at(0,1,0x10002000,expected_target,0));CHECK(target_leaf(expected_target)==UINT64_C(0x8000000000201005));
 reject_share(0,1,0x10001000,0x44000000,1,0x02030001); /* no replacement */
 reject_share(0,1,0x10000000,0x44003000,0,0x04060004); /* EXEC source */
 reject_share(0,1,0x10002000,0x44003000,1,0x04060004); /* read-only source */
 reject_share(0,1,0x60000000,0x44003000,0,0x04060004); /* MMIO */
 reject_share(0,1,0x60001000,0x44003000,0,0x04060004); /* owned PA with UC alias */
 reject_share(0,1,0x70001000,0x44003000,0,0x04060005); /* resource PA */
 reject_share(0,1,0x10003000,0x44003000,0,0x02030002); /* absent source */
 reject_share(0,16,0x10001000,0x44003000,0,0x04060003);
 reject_share(16,1,0x10001000,0x44003000,0,0x04060003);
 reject_share(3,1,0x10001000,0x44003000,0,0x04060003); /* dead source */
 reject_share(0,1,0x10001001,0x44003000,0,0x04060003);
 reject_share(0,1,0x10001000,0x44003001,0,0x04060003);
 reject_share(0,1,UINT64_MAX,0x44003000,0,0x04060003);
 reject_share(0,1,0x10001000,UINT64_MAX,0,0x04060003);
 reclaim_set_writable(1,0);reject_share(0,1,0x10001000,0x44003000,1,0x04060004);reclaim_set_writable(1,1);
 expected_target=0x10001000;CHECK(!reclaim_share_same(expected_target));CHECK(target_leaf(expected_target)==UINT64_C(0x8000000000201007));
 reset();
 CHECK(reclaim_destroy(16)==0x04060001&&flushes==0&&unbinds==0);
 CHECK(reclaim_destroy(2)==0x04060001&&reclaim_ready(2)==1&&flushes==0);
 current_root=0x100000;CHECK(reclaim_destroy(0)==0x04060001&&reclaim_ready(0)==1&&flushes==0);current_root=0;
 CHECK(reclaim_kernel_flags(alias)==0&&reclaim_writable(0)==0);
 CHECK(reclaim_destroy(0)==0&&reclaim_ready(0)==0&&reclaim_root_entry(0)==0);
 CHECK(flushes==2&&unbinds==1&&invalidations==1&&reclaim_kernel_flags(alias)==1);
 CHECK(reclaim_state(0)==1&&reclaim_writable(0)==1&&reclaim_state(1)==0&&reclaim_state(2)==2);
 CHECK(reclaim_state(3)==0&&reclaim_reference_calls()==2); /* unrelated held page is not a candidate */
 CHECK(reclaim_ready(1)==1&&reclaim_root_entry(1)!=0);
 CHECK(reclaim_destroy(1)==0&&reclaim_state(1)==0&&reclaim_state(2)==2);
 CHECK(reclaim_destroy(8)==0&&reclaim_state(1)==1&&reclaim_state(2)==2);
 CHECK(reclaim_state(3)==0&&reclaim_reference_calls()==4); /* last shared reference, independent of original owner */
 CHECK(reclaim_fresh()==0&&reclaim_state(0)==0);
 for(unsigned i=0;i<4096;i++)CHECK(((unsigned char*)page)[i]==0);
 for(unsigned i=4096;i<12288;i++)CHECK(((unsigned char*)page)[i]==0xa5);
 CHECK(reclaim_fresh()==1&&reclaim_state(1)==0);
 for(unsigned i=0;i<8192;i++)CHECK(((unsigned char*)page)[i]==0);
 reset();failed_unbind=1;CHECK(reclaim_destroy(0)==0x04060001&&reclaim_state(0)==0&&reclaim_writable(0)==0&&invalidations==0);
 CHECK(reclaim_state(1)==0&&reclaim_state(2)==2); /* uncertain retirement holds every page */
 reset();reclaim_large(large_frames,large_states);
 CHECK(reclaim_destroy(0)==0&&reclaim_reference_calls()==2&&reclaim_state(0)==1&&reclaim_state(1)==0&&reclaim_state(2)==2);
 for(unsigned i=3;i<6200;i++)CHECK(reclaim_state(i)==0);
#ifdef _WIN32
 _aligned_free(page);
#else
 free(page);
#endif
 printf("user reclaim checks passed %u; exact production destroy/fresh/share_at; hardware invalidation mocked; 6200frames reference-scans=2\n",checks);return 0;
}
