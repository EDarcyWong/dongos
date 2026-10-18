/* Independent reference enumerates every concrete disjoint pool/stack pair. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define PAGES 1024u
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"arena fit failed at %d: %s\n",__LINE__,#x);exit(1); } } while (0)
struct Range { uint64_t start,count; };
extern uint64_t DG arena_fits(const struct Range*,uint64_t);
extern uint64_t DG arena_range_size(void),arena_range_align(void);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length) {
    fprintf(stderr,"unexpected arena fit panic %u at %.*s:%u\n",kind,(int)length,file,line);exit(99);
}
static uint64_t seed=UINT64_C(0xc52aa17e5b04f139);
static uint64_t rng(void) { seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;return seed; }
static unsigned checks,yes,no;
static void checked(const struct Range *input,size_t n,int expected) {
    size_t bytes=(n+2)*sizeof(struct Range);
    struct Range *storage=malloc(bytes);uint8_t *snapshot=malloc(bytes);CHECK(storage&&snapshot);
    memset(storage,0xA6,bytes);if(n)memcpy(storage+1,input,n*sizeof(struct Range));memcpy(snapshot,storage,bytes);
    uint64_t got=arena_fits(storage+1,n);
    CHECK(got==(uint64_t)expected);CHECK(!memcmp(storage,snapshot,bytes));
    checks++;yes+=expected!=0;no+=expected==0;free(storage);free(snapshot);
}
static int complete(const uint8_t *map,unsigned first,unsigned count) {
    for(unsigned p=first;p<first+count;p++)if(!map[p])return 0;
    return 1;
}
static int reference(const uint8_t *map) {
    for(unsigned pool=0;pool+128<=PAGES;pool+=128) {
        if(!complete(map,pool,128))continue;
        for(unsigned stack=0;stack+16<=PAGES;stack+=16) {
            if(stack<pool+128 && pool<stack+16)continue;
            if(complete(map,stack,16))return 1;
        }
    }
    return 0;
}
int main(void) {
    CHECK(arena_range_size()==sizeof(struct Range)&&arena_range_align()==_Alignof(struct Range));
    checked(NULL,0,0);
    { const struct Range r[]={{0,128}};checked(r,1,0); }
    { const struct Range r[]={{0,128},{144,15}};checked(r,2,0); }
    { const struct Range r[]={{0,128},{144,16}};checked(r,2,1); }
    { const struct Range r[]={{16,144}};checked(r,1,0); } /* 80 free, no aligned pool */
    { const struct Range r[]={{0,128},{145,16}};checked(r,2,0); } /* no whole stack block */
    { const struct Range r[]={{0,144}};checked(r,1,1); }
    { const struct Range r[]={{880,144}};checked(r,1,1); } /* last legal arena page */
    { const struct Range r[]={{0,1024}};checked(r,1,1); }
    { const struct Range r[]={{0,128},{144,7},{160,8}};checked(r,3,0); } /* 15 fragmented pages */
    struct Range *ranges=malloc(PAGES*sizeof(struct Range));CHECK(ranges);
    uint8_t available[PAGES];
    for(unsigned round=0;round<6000;round++) {
        memset(available,0,sizeof(available));
        if(round%4==0) {
            for(unsigned p=0;p<PAGES;p++)available[p]=(rng()%4)!=0;
        } else if(round%4==1) {
            unsigned p=0;
            while(p<PAGES) {
                unsigned count=1+(unsigned)(rng()%128);int value=(rng()&1)!=0;
                if(count>PAGES-p)count=PAGES-p;
                for(unsigned j=0;j<count;j++)available[p+j]=(uint8_t)value;
                p+=count;
            }
        } else if(round%4==2) {
            unsigned pool=(unsigned)(rng()%8)*128;
            memset(available+pool,1,128);
            if(rng()&1) {
                unsigned stack=(unsigned)(rng()%64)*16;
                memset(available+stack,1,16);
            }
        } else {
            memset(available,1,sizeof(available));
            for(unsigned p=0;p<PAGES;p++)if(rng()%16==0)available[p]=0;
        }
        size_t n=0;
        for(unsigned p=0;p<PAGES;) {
            if(!available[p]){p++;continue;}
            unsigned first=p;while(p<PAGES&&available[p])p++;
            ranges[n++]=(struct Range){first,p-first};
        }
        checked(ranges,n,reference(available));
    }
    CHECK(yes>500&&no>500);free(ranges);
    printf("arena fit probe ok: %u maps, %u fit, %u rejected\n",checks,yes,no);
    return 0;
}
