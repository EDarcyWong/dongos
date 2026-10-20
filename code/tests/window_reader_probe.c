#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef struct{uint64_t version,lease,owner,epoch,client,server,bytes,width,height,stride;} Lease;
extern uint64_t ABI reader_setup(uint64_t),reader_kernel_setup(uint64_t),reader_unshare_seed(void),reader_reopen(void),reader_destroy(void);
extern uint64_t ABI reader_initialize(uint64_t),reader_allocate(uint64_t,uint64_t,Lease*),reader_depart(uint64_t),reader_revoke(uint64_t,uint64_t);
extern uint64_t ABI reader_compositor_gone(void),reader_budget(void),reader_broker_failed(void),reader_describe(uint64_t,uint64_t,uint64_t,Lease*);
extern uint64_t ABI reader_leaf(uint64_t,uint64_t),reader_alias(uint64_t,uint64_t),reader_anonymous(uint64_t),reader_state(uint64_t),reader_failed(void),reader_fresh(void);
extern uint64_t ABI unshare_resources_calls(void);
extern void ABI unshare_resources_setup(uint64_t);
static unsigned checks,flushes,invalidations,unbinds;
static void die(const char*s){fprintf(stderr,"window reader boundary: %s\n",s);exit(1);}
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"window reader oracle failed line %u: %s\n",__LINE__,#x);return 1;}}while(0)
void ABI __dong_panic(void){die("Dong panic");}
uint64_t ABI user_current_root(void){return 0;}
uint64_t ABI user_pcid_bind(uint64_t a,uint64_t b,uint64_t c){(void)a;(void)b;(void)c;die("unexpected bind");return 0;}
uint64_t ABI user_pcid_unbind(uint64_t slot,uint64_t root){if(slot!=7||root!=0x1e0000||!flushes)die("unbind without root withdrawal barrier");++unbinds;return 1;}
uint64_t ABI user_entropy64(void*a,void*b){(void)a;(void)b;die("unexpected entropy");return 0;}
void ABI user_pcid_flush_all(void){++flushes;}
void ABI user_pcid_invalidate_root(uint64_t root){if(root!=0x100000&&root!=0x160000&&root!=0x1e0000)die("unknown user root");++invalidations;}
void ABI runtime_copy_bytes(void*d,const void*s,uint64_t n){memcpy(d,s,(size_t)n);}
void ABI runtime_invalidate(uint64_t va){(void)va;}
static int zero(const unsigned char*ram,unsigned index){for(unsigned b=0;b<4096;b++)CHECK(ram[index*4096+b]==0);return 0;}
static int mapped(uint64_t id,uint64_t va,unsigned first,unsigned count){for(unsigned i=0;i<count;i++)CHECK(reader_leaf(id,va+i*4096)==0x200000+(first+i)*4096+3);return 0;}
int main(void){
#ifdef _WIN32
 unsigned char*ram=_aligned_malloc(16*4096,4096),*scratch=_aligned_malloc(12*4096,4096);
#else
 unsigned char*ram=aligned_alloc(4096,16*4096),*scratch=aligned_alloc(4096,12*4096);
#endif
 CHECK(ram&&scratch);memset(ram,0xa5,16*4096);memset(scratch,0,11*4096);memset(scratch+11*4096,0xcd,4096);
 unshare_resources_setup((uint64_t)(uintptr_t)scratch);CHECK(!reader_setup((uint64_t)(uintptr_t)ram));CHECK(!reader_kernel_setup((uint64_t)(uintptr_t)ram));
 CHECK(!reader_unshare_seed());for(unsigned i=0;i<12;i++){CHECK(reader_state(i)==1);CHECK(!zero(ram,i));}
 CHECK(!reader_initialize(1));Lease a={0},b={0},sentinel,output;uint64_t ownerA=(UINT64_C(8)<<32)|1,ownerB=(UINT64_C(8)<<32)|2;
 uint64_t windowA=(UINT64_C(1)<<32)|0x101,windowB=(UINT64_C(1)<<32)|0x102;
 CHECK(!reader_allocate(ownerA,windowA,&a));CHECK(a.client==0x74000000&&a.server==0x78000000&&a.bytes==16384&&reader_budget()==16384);
 CHECK(!mapped(7,a.client,0,4)&&!mapped(3,a.server,0,4));uint64_t borrowed=reader_alias(7,a.client);CHECK(borrowed==(uint64_t)(uintptr_t)ram);*(uint64_t*)(uintptr_t)borrowed=0x1111;
 CHECK(!reader_depart(ownerA));CHECK(reader_budget()==16384);CHECK(!reader_leaf(7,a.client));CHECK(!mapped(3,a.server,0,4));
 CHECK(*(uint64_t*)(uintptr_t)reader_alias(3,a.server)==0x1111);for(unsigned i=0;i<4;i++)CHECK(reader_state(i)==0);
 memset(&sentinel,0x5a,sizeof(sentinel));output=sentinel;CHECK(reader_describe(ownerA,windowA,a.lease,&output)==0x07430002);CHECK(!memcmp(&output,&sentinel,sizeof(output)));
 CHECK(reader_initialize(2)!=0);CHECK(!reader_depart(ownerA));CHECK(reader_budget()==16384);CHECK(!reader_destroy()&&unbinds==1);CHECK(!mapped(3,a.server,0,4));
 CHECK(!reader_reopen());CHECK(!reader_allocate(ownerB,windowB,&b));CHECK(b.client==0x74400000&&b.server==0x78400000&&reader_budget()==32768);
 CHECK(!mapped(7,b.client,4,4)&&!mapped(3,b.server,4,4));CHECK(reader_leaf(3,a.server)!=reader_leaf(3,b.server));
 *(uint64_t*)(uintptr_t)reader_alias(7,b.client)=0x2222;CHECK(*(uint64_t*)(uintptr_t)reader_alias(3,a.server)==0x1111);
 // An unrelated new incarnation deliberately occupies the old client range.
 for(unsigned i=0;i<4;i++){CHECK(reader_anonymous(a.client+i*4096)==0x208000+i*4096);*(uint64_t*)(uintptr_t)reader_alias(7,a.client+i*4096)=0x3333+i;}
 CHECK(!reader_revoke(1,a.lease));CHECK(reader_budget()==16384&&!reader_broker_failed()&&!reader_failed());CHECK(!reader_leaf(3,a.server));
 CHECK(!mapped(7,a.client,8,4)&&!mapped(7,b.client,4,4)&&!mapped(3,b.server,4,4));
 for(unsigned i=0;i<4;i++){CHECK(reader_state(i)==1);CHECK(!zero(ram,i));CHECK(*(uint64_t*)(uintptr_t)reader_alias(7,a.client+i*4096)==0x3333+i);}
 unsigned before=flushes;CHECK(!reader_revoke(1,a.lease)&&before==flushes);CHECK(reader_revoke(2,a.lease)==0x07430002);
 CHECK(!reader_depart(ownerB));CHECK(reader_budget()==16384);CHECK(!reader_destroy()&&unbinds==2);CHECK(!mapped(3,b.server,4,4));
 CHECK(*(uint64_t*)(uintptr_t)reader_alias(3,b.server)==0x2222);CHECK(!reader_compositor_gone());CHECK(!reader_budget());
 for(unsigned i=0;i<8;i++){CHECK(reader_state(i)==1);CHECK(!zero(ram,i));}CHECK(!reader_leaf(3,b.server));
 CHECK(!reader_initialize(2));CHECK(reader_revoke(1,b.lease)==0x07430002);
 // destroy() may retain dirty reusable RAM; every later fresh() must zero it.
 for(unsigned i=0;i<12;i++){CHECK(reader_fresh()==i);CHECK(!zero(ram,i));}
 CHECK(unshare_resources_calls()==1&&flushes>10&&invalidations>4);for(unsigned i=0;i<4096;i++)CHECK(scratch[11*4096+i]==0xcd);
 printf("window reader real memory/paging checks passed %u; STATIC3 dynamic compositor128 and slot7, last-reader retention, same-slot reuse, zeroed reuse\n",checks);return 0;
}
