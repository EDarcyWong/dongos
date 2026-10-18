#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI preload_setup(uint64_t),preload_retire(uint64_t),preload_launch(uint64_t),preload_ready(uint64_t),preload_get(uint64_t,uint64_t),preload_old_handle(uint64_t);
extern uint64_t ABI compat_cn_smoke(void),compat_owner(uint64_t),compat_abort_count(uint64_t),compat_unsupported(void);
static unsigned checks;
void ABI __dong_panic(void){fputs("preload oracle unexpected panic\n",stderr);exit(1);}
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"preload oracle failed line %u: %s\n",__LINE__,#x);exit(1);}}while(0)
static void fs_failure(unsigned ready){
 CHECK(!preload_setup(ready));uint64_t before=preload_get(4,0);CHECK(preload_get(0,0)&&preload_get(0,3));
 CHECK(!preload_retire(1));CHECK(preload_get(4,0)==before+1);
 for(unsigned id=0;id<4;id++)if(id!=2){
  CHECK(!preload_get(0,id)&&!preload_get(1,id)&&!preload_get(2,id)&&!preload_get(12,id));CHECK(preload_get(13,id)==1);
  if(id!=1){CHECK(preload_get(5,id)==0&&preload_get(6,id)==0&&preload_get(7,id)==0&&preload_get(8,id)==0);CHECK(!preload_get(3,id));}
 }
 CHECK(preload_get(3,1)==1&&preload_get(1,2)&&preload_get(1,4)&&preload_get(11,0));
 CHECK(!preload_launch(1));CHECK(!preload_ready(1));CHECK(preload_get(5,1)==2&&preload_get(6,1)==2);
 CHECK(preload_get(10,0)!=1);CHECK(!preload_launch(0));CHECK(!preload_launch(3));
 CHECK(preload_get(9,0)==preload_get(10,0)&&preload_get(9,3)==preload_get(10,0));
 CHECK(preload_get(5,0)==1&&preload_get(5,3)==1&&preload_get(6,0)==1&&preload_get(6,3)==1);
}
static void unrelated_unready_preload(void){
 CHECK(!preload_setup(2));CHECK(preload_get(0,0)&&preload_get(8,1)==1);
 CHECK(!preload_retire(4));CHECK(preload_get(0,0)&&preload_get(1,0)&&preload_get(13,0)==0);
 CHECK(preload_get(7,1)!=0&&preload_get(8,1)==1);CHECK(!preload_get(0,3)&&!preload_get(1,3)&&preload_get(13,3)==1);
 CHECK(!preload_get(3,3)&&preload_get(3,4)==1&&!preload_get(11,0));CHECK(preload_get(1,4)&&preload_get(14,4)==1);
}
static void manager_failure(void){
 CHECK(!preload_setup(3));uint64_t before=preload_get(4,0);CHECK(!preload_retire(6));CHECK(preload_get(4,0)==before+1);
 for(unsigned id=0;id<5;id++){
  CHECK(!preload_get(0,id)&&!preload_get(1,id)&&!preload_get(2,id)&&preload_get(13,id)==1);
  CHECK(!preload_get(3,id)&&!preload_get(5,id)&&!preload_get(6,id)&&!preload_get(7,id));
 }
 CHECK(!preload_get(11,0));
 /* Once running drivers own DMA, the old roots/leases stay held instead of
    pretending a one-shot manager rebind can safely recycle them. */
 CHECK(!preload_setup(4));before=preload_get(4,0);CHECK(!preload_retire(6));CHECK(preload_get(4,0)==before+6);
 for(unsigned id=0;id<5;id++)CHECK(!preload_get(7,id)&&preload_get(8,id)>=3&&!preload_get(2,id));
 CHECK(preload_get(1,2)&&preload_get(1,4)&&preload_get(14,2)==1&&preload_get(14,4)==1);
 CHECK(!preload_get(13,2)&&!preload_get(13,4)&&!preload_get(11,0));
}
int main(void){CHECK(!compat_cn_smoke());fs_failure(0);fs_failure(1);unrelated_unready_preload();manager_failure();CHECK(!compat_unsupported());printf("preload dependency checks passed %u; real retirement/catalog/caps, mapped-root adapter\n",checks);return 0;}
