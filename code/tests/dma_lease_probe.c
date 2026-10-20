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
typedef struct {U physical,virtual,pages,root,generation,attempted,mapped,state;} Lease;
_Static_assert(sizeof(Lease)==64,"Lease");
extern ABI void dma_reset(U,U,U),dma_guard(U);
extern ABI U dma_get_slot(U,Lease*);
extern ABI U dma_allocate(U,U,U*),dma_get(Lease*),dma_is_pinned(void);
static U checks,calls,fail_stage,fail_page,own_calls,map_calls,expected_pages,extended;
#define CK(x) do{checks++;if(!(x)){fprintf(stderr,"DMA lease check failed line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
ABI U dma_event(U stage,U a,U b,U c){
    calls++;Lease l;CK(dma_get(&l)==0&&dma_is_pinned()==1&&l.state==1);
    Lease other;CK(dma_get_slot(3,&other)==0&&other.physical==0x400000&&other.root==0xa000&&other.generation==9&&other.pages==1&&other.attempted==1&&other.mapped==1&&other.state==2);
    CK(l.pages==expected_pages&&l.root==0x9000&&l.generation==7&&l.virtual==0x68000000);
    if(stage==1){
        CK(a==expected_pages&&b==expected_pages&&c==extended&&l.physical==0&&!l.attempted&&!l.mapped);
        U untouched=99;CK(dma_allocate(1,0x68000000,&untouched)==0x04060003&&untouched==99);
    }else{
        CK(l.physical==0x200000);
        if(stage==2){own_calls++;CK(a==0x200000+(own_calls-1)*4096&&l.attempted==own_calls&&l.mapped==own_calls-1);}
        if(stage==3){map_calls++;CK(a==0x68000000+(map_calls-1)*4096&&b==0x200000+(map_calls-1)*4096&&c==6);CK(l.attempted==map_calls&&l.mapped==map_calls-1);}
        if(stage==4)CK(l.mapped==map_calls);
        if(stage==5)CK(a==0x9000&&l.mapped==expected_pages);
    }
    return stage==fail_stage&&(stage==1||(stage==2&&own_calls==fail_page)||(stage==3&&map_calls==fail_page));
}
ABI void __dong_panic(void){fprintf(stderr,"unexpected panic\n");exit(2);}
static void reset(U ext,U cap,U count){extended=ext;calls=own_calls=map_calls=0;fail_stage=fail_page=0;dma_reset(ext,cap,count);}
int main(void){
    for(U ext=0;ext<2;ext++)for(U requested=1;requested<=32;requested++){
        expected_pages=1;while(expected_pages<requested)expected_pages*=2;
        reset(ext,64,0);U out=99;Lease l;CK(dma_allocate(requested,0x68000000,&out)==0&&out==0x200000);
        CK(dma_get(&l)==0&&l.physical==out&&l.pages==expected_pages&&l.attempted==expected_pages&&l.mapped==expected_pages&&l.state==2);
        Lease before=l;U oldcalls=calls;out=99;CK(dma_allocate(requested,0x68000000,&out)==0x04060003&&out==99&&calls==oldcalls);
        CK(dma_get(&l)==0&&!memcmp(&l,&before,sizeof l));
    }
    for(U ext=0;ext<2;ext++)for(U stage=1;stage<=3;stage++)for(U page=1;page<=32;page++){
        reset(ext,64,0);expected_pages=32;fail_stage=stage;fail_page=page;U out=99;Lease l;
        CK(dma_allocate(17,0x68000000,&out)==0x052a0001&&out==99&&dma_is_pinned());
        CK(dma_get(&l)==0&&l.pages==32&&l.state==1&&l.physical==(stage==1?0:0x200000));
        CK(l.attempted==(stage==1?0:page)&&l.mapped==(stage==1?0:page-1));
        Lease before=l;U oldcalls=calls;CK(dma_allocate(1,0x68000000,&out)==0x04060003&&calls==oldcalls);
        CK(dma_get(&l)==0&&!memcmp(&before,&l,sizeof l));
    }
    const U invalid[]={0,33,UINT64_MAX};
    for(unsigned i=0;i<3;i++){reset(1,64,0);U out=99;CK(dma_allocate(invalid[i],0x68000000,&out)==0x04060003&&!calls&&!dma_is_pinned()&&out==99);}
    const U badva[]={0,0xffff,0x68000001,UINT64_C(0x8000000000),UINT64_MAX};
    for(unsigned i=0;i<5;i++){reset(1,64,0);U out=99;CK(dma_allocate(1,badva[i],&out)==0x04060003&&!calls&&!dma_is_pinned());}
    reset(1,64,0);U out=99;CK(dma_allocate(2,UINT64_C(0x7ffffff000),&out)==0x04060002&&!calls&&!dma_is_pinned());
    reset(1,31,0);CK(dma_allocate(17,0x68000000,&out)==0x04060002&&!calls&&!dma_is_pinned());
    reset(1,31,32);CK(dma_allocate(1,0x68000000,&out)==0x04060002&&!calls&&!dma_is_pinned());
    reset(1,64,32);expected_pages=32;CK(dma_allocate(17,0x68000000,&out)==0&&own_calls==32&&map_calls==32);
    reset(1,64,0);Lease snapshot,poison;memset(&snapshot,0xa5,sizeof snapshot);poison=snapshot;
    CK(dma_get(&snapshot)==0x04060001&&!memcmp(&snapshot,&poison,sizeof snapshot));
    CK(dma_get_slot(16,&snapshot)==0x04060001&&!memcmp(&snapshot,&poison,sizeof snapshot));
    CK(dma_get(NULL)==0x04060001&&!calls);
    for(U guard=1;guard<=4;guard++){reset(1,64,0);dma_guard(guard);out=99;CK(dma_allocate(1,0x68000000,&out)==0x04060003&&!calls&&out==99);}
    printf("DMA lease native checks passed %llu\n",(unsigned long long)checks);return 0;
}
