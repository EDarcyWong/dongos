#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif
#define ABI __attribute__((sysv_abi))
extern void ABI stage_setup(uint64_t),stage_resources_reset(uint64_t),stage_resources_fail(uint64_t),stage_pin_test(uint64_t);
extern uint64_t ABI stage_load(const void*,uint64_t,uint64_t),stage_commit_test(void),stage_abort_test(void),stage_destroy_test(uint64_t),stage_extra(uint64_t),stage_own_orphan(void),stage_share_test(void);
extern uint64_t ABI stage_get(uint64_t,uint64_t),stage_kernel_setup(void),stage_kernel_flags(uint64_t),stage_drop_alias(uint64_t),stage_resources_calls(void),stage_alias_collision(uint64_t);
static unsigned checks,flushes,binds,unbinds,aborting,failed_unbind,entropy_fail,entropy_calls;
static uint64_t generation,alias;
static unsigned char image[1024];
static void die(const char* why){fprintf(stderr,"stage ordering failed %s\n",why);exit(1);}
void ABI __dong_panic(void){die("unexpected Dong panic");}
uint64_t ABI user_current_root(void){return 0;}
void ABI user_pcid_flush_all(void){if(aborting&&(stage_get(2,8)||stage_get(3,8)))die("USER root not withdrawn before tag barrier");++flushes;}
uint64_t ABI user_pcid_bind(uint64_t id,uint64_t root,uint64_t gen){if(id!=8||root!=0x300000||gen<=generation)die("wrong root or reused generation");generation=gen;++binds;return 1;}
uint64_t ABI user_pcid_unbind(uint64_t id,uint64_t root){
 if(!flushes||stage_get(2,id)||stage_get(3,id)||root!=(id==8?0x300000:0x320000))die("unbind before complete withdrawal");
 ++unbinds;return !failed_unbind;
}
void ABI runtime_invalidate(uint64_t va){(void)va;}
void ABI user_pcid_invalidate_root(uint64_t root){(void)root;}
void ABI runtime_copy_bytes(void*d,const void*s,uint64_t n){memcpy(d,s,(size_t)n);}
uint64_t ABI user_entropy64(uint64_t*out,uint64_t*kind){if(entropy_fail)return 0;*out=entropy_calls++%2?0x12345:0;*kind=1;return 1;}
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"stage check failed line %u: %s\n",__LINE__,#x);return 1;}}while(0)
static void put16(unsigned n,uint16_t value){memcpy(image+n,&value,2);}
static void put32(unsigned n,uint32_t value){memcpy(image+n,&value,4);}
static void put64(unsigned n,uint64_t value){memcpy(image+n,&value,8);}
static void elf(unsigned count){
 memset(image,0,sizeof(image));memcpy(image,"\177ELF",4);image[4]=2;image[5]=1;image[6]=1;
 put16(16,3);put16(18,62);put32(20,1);put64(24,0x103c0);put64(32,64);put16(52,64);put16(54,56);put16(56,(uint16_t)count);
 for(unsigned i=0;i<count;i++){unsigned at=64+i*56;put32(at,1);put32(at+4,i?6:5);
  put64(at+8,0);put64(at+16,0x10000+(uint64_t)i*0x40000000);put64(at+32,i?0:sizeof(image));put64(at+40,4096);put64(at+48,4096);}
}
static int setup(uint64_t fail){
 flushes=binds=unbinds=aborting=failed_unbind=entropy_fail=entropy_calls=0;generation=0;
 memset((void*)(uintptr_t)alias,0xa5,256*4096);stage_setup(alias);stage_resources_reset(fail);CHECK(stage_kernel_setup()==0);return 0;
}
static int empty(unsigned count){
 CHECK(stage_get(2,8)==0&&stage_get(3,8)==0&&stage_get(4,0)==0&&stage_get(5,0)==16&&stage_get(6,0)==0);
 for(unsigned i=0;i<count;i++){
  CHECK(stage_get(1,i)==1&&stage_get(7,i)==1&&stage_kernel_flags(alias+i*4096)==1);
  for(unsigned j=0;j<4096;j++)CHECK(*((unsigned char*)(uintptr_t)alias+i*4096+j)==0);
 }return 0;
}
static int sparse_retry(void){
 CHECK(!setup(0));elf(16);
 for(unsigned attempt=0;attempt<10;attempt++){
  CHECK(stage_load(image,sizeof(image),0)!=0);CHECK(stage_get(0,0)==16);CHECK(stage_resources_calls()==16);CHECK(!binds&&!unbinds);CHECK(!empty(16));
 }
 elf(1);CHECK(!stage_load(image,sizeof(image),0));CHECK(stage_get(2,8)==1&&stage_get(4,0)==5&&stage_get(9,8)==1);CHECK(!stage_commit_test());
 aborting=1;CHECK(!stage_destroy_test(8));aborting=0;CHECK(!stage_load(image,sizeof(image),0));CHECK(stage_get(9,8)==2);CHECK(!stage_commit_test());return 0;
}
static int late_failure(void){
 CHECK(!setup(0));elf(1);CHECK(!stage_load(image,sizeof(image),1));CHECK(stage_get(0,0)==5);
 CHECK(stage_extra(1)!=0);CHECK(stage_get(0,0)==6&&stage_get(4,0)==6);aborting=1;CHECK(!stage_abort_test());aborting=0;CHECK(unbinds==1);CHECK(!empty(6));
 CHECK(!stage_load(image,sizeof(image),0));CHECK(stage_get(9,8)==2);CHECK(!stage_commit_test());
 CHECK(!setup(3));CHECK(stage_load(image,sizeof(image),0)==0x05070002);CHECK(stage_get(0,0)==2);CHECK(!empty(2));
 stage_resources_fail(0);CHECK(!stage_load(image,sizeof(image),0));CHECK(stage_get(0,0)==5);CHECK(!stage_commit_test());
 CHECK(!setup(0));entropy_fail=1;CHECK(stage_load(image,sizeof(image),1)==0x04080001);CHECK(stage_get(0,0)==0&&stage_get(5,0)==16);return 0;
}
static int static_stack(void){
 CHECK(!setup(0));elf(1);put16(16,2);CHECK(!stage_load(image,sizeof(image),1));
 CHECK(stage_get(12,8)==0x103c0);CHECK(stage_get(13,8)==UINT64_C(0x7ffff00000)-UINT64_C(0x12345000)-8);
 CHECK(entropy_calls==2);aborting=1;CHECK(!stage_abort_test());aborting=0;CHECK(!empty(5));return 0;
}
static int survivors(void){
 CHECK(!setup(0));elf(1);CHECK(!stage_load(image,sizeof(image),0));uint64_t shared=stage_extra(0);CHECK(shared==5);
 *(uint64_t*)(uintptr_t)(alias+shared*4096)=0xabc987;CHECK(!stage_share_test());
 uint64_t pin=stage_own_orphan();CHECK(pin==6);stage_pin_test(pin);*(uint64_t*)(uintptr_t)(alias+pin*4096)=0x777555;
 aborting=1;CHECK(!stage_abort_test());aborting=0;CHECK(stage_get(1,shared)==0&&stage_get(1,pin)==2);
 CHECK(*(uint64_t*)(uintptr_t)(alias+shared*4096)==0xabc987);CHECK(*(uint64_t*)(uintptr_t)(alias+pin*4096)==0x777555);
 CHECK(stage_get(2,9)==1);CHECK(!stage_destroy_test(9));CHECK(stage_get(1,shared)==1&&stage_get(1,pin)==2);return 0;
}
static int held_failures(void){
 CHECK(!setup(0));elf(1);CHECK(!stage_load(image,sizeof(image),0));failed_unbind=1;aborting=1;CHECK(stage_abort_test()==0x04060001);aborting=0;
 CHECK(stage_get(6,0)==1&&stage_get(2,8)==0&&stage_get(3,8)==0);
 for(unsigned i=0;i<5;i++)CHECK(stage_get(1,i)==0);
 CHECK(stage_load(image,sizeof(image),0)==0x04060001);CHECK(stage_commit_test()==0x04060001);
 CHECK(!setup(0));CHECK(!stage_load(image,sizeof(image),0));CHECK(!stage_drop_alias(alias+4*4096));
 aborting=1;CHECK(stage_abort_test()!=0);aborting=0;CHECK(stage_get(6,0)==1);
 for(unsigned i=0;i<5;i++)CHECK(stage_get(1,i)==0);
 CHECK(!setup(0));CHECK(!stage_alias_collision(alias));CHECK(stage_load(image,sizeof(image),0)==0x04060005);
 CHECK(stage_get(6,0)==1&&stage_get(0,0)==1&&stage_get(4,0)==1&&stage_get(1,0)==0&&stage_resources_calls()==1);
 CHECK(stage_get(2,8)==0&&stage_get(3,8)==0&&binds==0&&unbinds==0);
 for(unsigned i=0;i<4096;i++)CHECK(*((unsigned char*)(uintptr_t)alias+i)==0xa5);
 CHECK(stage_load(image,sizeof(image),0)==0x04060001);
 return 0;
}
int main(void){
#ifdef _WIN32
 void*memory=_aligned_malloc(256*4096,4096);
#else
 void*memory=aligned_alloc(4096,256*4096);
#endif
 CHECK(memory!=NULL);alias=(uint64_t)(uintptr_t)memory;
 if(sparse_retry()||late_failure()||static_stack()||survivors()||held_failures())return 1;
 printf("user stage checks passed %u; sparse ELF, real paging, transaction rollback\n",checks);return 0;
}
