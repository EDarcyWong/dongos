#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif
#define SYSV __attribute__((sysv_abi))
extern uint64_t SYSV dma_kernel_setup(uint64_t,uint64_t);
extern uint64_t SYSV dma_setup(uint64_t,uint64_t,uint64_t),dma_release(uint64_t),dma_destroy(uint64_t);
extern uint64_t SYSV dma_pinned(uint64_t),dma_base(uint64_t),dma_pages(uint64_t),dma_state(uint64_t),dma_ready(uint64_t);
extern void SYSV dma_set_ready(uint64_t,uint64_t);
static uint64_t current_root;
static unsigned checks;
static void die(const char*why){fprintf(stderr,"dma release failed %s\n",why);exit(1);}
uint64_t SYSV user_current_root(void){return current_root;}
void SYSV user_pcid_flush_all(void){}
uint64_t SYSV user_pcid_unbind(uint64_t id,uint64_t root){(void)id;(void)root;return 1;}
void SYSV runtime_invalidate(uint64_t va){(void)va;}
void SYSV user_pcid_invalidate_root(uint64_t root){(void)root;}
void SYSV runtime_copy_bytes(void*d,const void*s,uint64_t bytes){memcpy(d,s,(size_t)bytes);}
void SYSV __dong_panic(void){die("Dong panic");}
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"dma release check failed line %u\n",__LINE__);return 1;}}while(0)
int main(void){
 void*page;
#ifdef _WIN32
 page=_aligned_malloc(4*4096,4096);
#else
 page=aligned_alloc(4096,4*4096);
#endif
 CHECK(page!=NULL);uint64_t alias=(uint64_t)(uintptr_t)page;
 CHECK(dma_kernel_setup(alias,4)==0);
 CHECK(dma_setup(alias,UINT64_C(0x68000000),4)==0);
 memset(page,0xa5,4*4096);
 CHECK(dma_pinned(2)==1&&dma_base(2)==UINT64_C(0x68000000)&&dma_pages(2)==4);
 current_root=UINT64_C(0x300000);
 CHECK(dma_release(2)==UINT64_C(0x04060001));
 CHECK(dma_pinned(2)==1&&dma_base(2)==UINT64_C(0x68000000)&&dma_pages(2)==4);
 current_root=0;
 dma_set_ready(2,0);
 CHECK(dma_release(2)==UINT64_C(0x04060001));
 CHECK(dma_pinned(2)==1&&dma_base(2)==UINT64_C(0x68000000));
 dma_set_ready(2,1);
 CHECK(dma_release(16)==UINT64_C(0x04060001));
 CHECK(dma_release(0)==UINT64_C(0x04060001));
 uint64_t released=dma_release(2);
 CHECK(released==0);
 CHECK(dma_pinned(2)==0&&dma_base(2)==0&&dma_pages(2)==0);
 CHECK(dma_ready(2)==1);
 for(unsigned i=0;i<4;i++)CHECK(dma_state(i)==1);
 for(unsigned i=0;i<4*4096;i++)CHECK(((unsigned char*)page)[i]==0);
 CHECK(dma_release(2)==UINT64_C(0x04060001));
 CHECK(dma_destroy(2)==0&&dma_ready(2)==0);
#ifdef _WIN32
 _aligned_free(page);
#else
 free(page);
#endif
 printf("dma release checks passed %u; pinned range released and zeroed\n",checks);return 0;
}
