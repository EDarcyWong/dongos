#define _GNU_SOURCE
#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define CHECK(X) do{if(!(X)){fprintf(stderr,"core.arena check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
struct Bytes {const uint8_t *ptr;uint64_t len;};
struct Arena {uint8_t *base;uint64_t capacity;uint64_t used;};
extern uint64_t DG arena_size(void),arena_base_off(void),arena_cap_off(void),arena_used_off(void);
extern uint8_t DG arena_init(struct Arena*,struct Bytes);
extern uint8_t DG arena_allocate(struct Arena*,uint64_t,uint64_t,uint64_t*);
extern uint8_t DG arena_rewind(struct Arena*,uint64_t);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    fprintf(stderr,"unexpected core.arena panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char *)file);exit(99);
}
/* naturally-aligned guarded fixtures (compiler enforces alignment) */
struct GArena { uint8_t front[8]; struct Arena a; uint8_t back[8]; };
struct GOut { uint8_t front[8]; uint64_t v; uint8_t back[8]; };
#define AG(g) do{for(int _g=0;_g<8;_g++)CHECK((g).front[_g]==0xa5 && (g).back[_g]==0xa5);}while(0)
#define OG(g) do{for(int _g=0;_g<8;_g++)CHECK((g).front[_g]==0xa5 && (g).back[_g]==0xa5);}while(0)
/* storage guard: sg front/back around the len-byte buffer */
#define SG(g,len) do{for(int _g=0;_g<8;_g++)CHECK((g)[_g]==0xa5 && (g)[8+(len)+_g]==0xa5);}while(0)
static int model_alloc(uint64_t base,uint64_t cap,uint64_t used,uint64_t size,uint64_t align,uint64_t *out,uint64_t *nused){
    if(used>cap)return 0;
    if(align==0)return 0;
    if((align&(align-1))!=0)return 0;
    if(base==0 && cap!=0)return 0;
    if(base>UINT64_MAX-cap)return 0;
    uint64_t cur=base+used;
    uint64_t mask=align-1;
    if(cur>UINT64_MAX-mask)return 0;
    uint64_t p=(cur+mask)&~mask;
    if(p>UINT64_MAX-size)return 0;
    uint64_t end=p+size;
    if(end>base+cap)return 0;
    *out=p;*nused=(p-base)+size;
    return 1;
}
static uint64_t rng(uint64_t *s){*s^=*s<<13;*s^=*s>>7;*s^=*s<<17;return *s;}

int main(void){
    CHECK(arena_size()==24);
    CHECK(arena_base_off()==0 && arena_cap_off()==8 && arena_used_off()==16);
    CHECK(sizeof(struct Arena)==24 && offsetof(struct Arena,base)==0 && offsetof(struct Arena,capacity)==8 && offsetof(struct Arena,used)==16);

    /* init: valid / empty / null-with-len / overflow, immediate observation */
    {
        uint8_t sg[8+32+8]; uint8_t *storage=sg+8;
        memset(sg,0xa5,sizeof(sg)); memset(storage,0x5a,32);
        uint8_t snap[32]; memcpy(snap,storage,32);
        struct GArena ga; memset(&ga,0xa5,sizeof(ga)); struct Arena *a=&ga.a;
        CHECK(arena_init(a,(struct Bytes){storage,32}));
        CHECK(a->base==storage && a->capacity==32 && a->used==0);
        AG(ga); SG(sg,32); CHECK(!memcmp(storage,snap,32));
        memset(&ga,0xa5,sizeof(ga));
        CHECK(arena_init(a,(struct Bytes){NULL,0}));
        CHECK(a->base==NULL && a->capacity==0 && a->used==0);
        AG(ga);
        /* null-with-len: object fully unchanged incl. guards */
        { struct GArena gb; memset(&gb,0xa5,sizeof(gb)); struct Arena *b=&gb.a; memset(b,0x33,sizeof(*b));
          struct Arena bs=*b;
          CHECK(!arena_init(b,(struct Bytes){NULL,16}));
          CHECK(!memcmp(b,&bs,sizeof(bs))); AG(gb); }
        /* base+capacity overflow: object fully unchanged */
        { struct GArena gc; memset(&gc,0xa5,sizeof(gc)); struct Arena *c=&gc.a; memset(c,0x44,sizeof(*c));
          struct Arena cs=*c;
          CHECK(!arena_init(c,(struct Bytes){storage,(uint64_t)0-UINT64_C(1)-((uint64_t)(uintptr_t)storage)+2}));
          CHECK(!memcmp(c,&cs,sizeof(cs))); AG(gc); SG(sg,32); CHECK(!memcmp(storage,snap,32)); }
        SG(sg,32); CHECK(!memcmp(storage,snap,32));
    }

    /* allocate: mixed + random + deterministic + invalid + exact/one-less */
    {
        uint8_t sg[8+256+8]; uint8_t *storage=sg+8;
        memset(sg,0xa5,sizeof(sg)); memset(storage,0x5a,256);
        uint8_t snap[256]; memcpy(snap,storage,256);
        struct GArena ga; memset(&ga,0xa5,sizeof(ga)); struct Arena *a=&ga.a;
        struct GOut go; memset(&go,0xa5,sizeof(go)); uint64_t *out=&go.v;
        CHECK(arena_init(a,(struct Bytes){storage,256}));
        AG(ga); OG(go); SG(sg,256); CHECK(!memcmp(storage,snap,256));
        uint64_t seed=UINT64_C(0x9e3779b97f4a7c15);
        for(int k=0;k<300;k++){
            uint64_t size=rng(&seed)%(300+1);
            uint64_t align=(uint64_t)1<<(rng(&seed)%13);
            memset(&go,0xa5,sizeof(go)); *out=UINT64_C(0xdeadbeefcafebabe);
            struct Arena before=*a; uint64_t mo=0,mn=0;
            int ok=model_alloc((uint64_t)(uintptr_t)a->base,a->capacity,a->used,size,align,&mo,&mn);
            uint8_t rr=arena_allocate(a,size,align,out);
            CHECK(rr==(uint8_t)ok);
            if(ok){CHECK(*out==mo);CHECK(a->used==mn);CHECK(a->base==before.base);CHECK(a->capacity==before.capacity);}
            else {CHECK(*out==UINT64_C(0xdeadbeefcafebabe));CHECK(!memcmp(a,&before,sizeof(before)));}
            AG(ga); OG(go); CHECK(!memcmp(storage,snap,256)); SG(sg,256);
            if((k%37)==0){CHECK(arena_rewind(a,0)); CHECK(a->used==0); CHECK(a->base==storage); CHECK(a->capacity==256); AG(ga); OG(go); CHECK(!memcmp(storage,snap,256)); SG(sg,256);}
        }
        CHECK(arena_rewind(a,0)); CHECK(a->used==0); CHECK(a->base==storage); CHECK(a->capacity==256); AG(ga); SG(sg,256); CHECK(!memcmp(storage,snap,256));
        uint64_t sizes[]={0,1,2,3,7,8,15,16,17,31,32,63,64,100,255,256};
        uint64_t aligns[]={1,2,4,8,16,32,64,128,256,1024,65536,(uint64_t)1<<32};
        for(size_t si=0;si<sizeof(sizes)/sizeof(sizes[0]);si++){
            for(size_t ai=0;ai<sizeof(aligns)/sizeof(aligns[0]);ai++){
                memset(&go,0xa5,sizeof(go)); *out=UINT64_C(0xdeadbeefcafebabe);
                struct Arena before=*a;
                uint64_t mo=0,mn=0;
                int ok=model_alloc((uint64_t)(uintptr_t)a->base,a->capacity,a->used,sizes[si],aligns[ai],&mo,&mn);
                uint8_t r=arena_allocate(a,sizes[si],aligns[ai],out);
                CHECK(r==(uint8_t)ok);
                if(ok){CHECK(*out==mo);CHECK(a->used==mn);CHECK(a->base==before.base);CHECK(a->capacity==before.capacity);}
                else {CHECK(*out==UINT64_C(0xdeadbeefcafebabe));CHECK(!memcmp(a,&before,sizeof(before)));}
                AG(ga); OG(go); CHECK(!memcmp(storage,snap,256)); SG(sg,256);
            }
        }
        /* invalid alignment: full atomicity incl. out unchanged */
        { struct Arena before=*a;
          memset(&go,0xa5,sizeof(go)); *out=77; CHECK(!arena_allocate(a,1,0,out)); CHECK(*out==77); CHECK(!memcmp(a,&before,sizeof(before))); AG(ga); OG(go); SG(sg,256); CHECK(!memcmp(storage,snap,256));
          memset(&go,0xa5,sizeof(go)); *out=77; CHECK(!arena_allocate(a,1,3,out)); CHECK(*out==77); CHECK(!memcmp(a,&before,sizeof(before))); AG(ga); OG(go); SG(sg,256); CHECK(!memcmp(storage,snap,256));
          memset(&go,0xa5,sizeof(go)); *out=77; CHECK(!arena_allocate(a,1,6,out)); CHECK(*out==77); CHECK(!memcmp(a,&before,sizeof(before))); AG(ga); OG(go); SG(sg,256); CHECK(!memcmp(storage,snap,256)); }
        CHECK(arena_rewind(a,0)); CHECK(a->used==0); CHECK(a->base==storage); CHECK(a->capacity==256); AG(ga); SG(sg,256); CHECK(!memcmp(storage,snap,256));
        { memset(&go,0xa5,sizeof(go)); *out=0;
          CHECK(arena_allocate(a,256,1,out)); CHECK(*out==(uint64_t)(uintptr_t)storage && a->used==256); AG(ga); OG(go); SG(sg,256); CHECK(!memcmp(storage,snap,256));
          CHECK(arena_rewind(a,0)); CHECK(a->used==0); CHECK(a->base==storage); CHECK(a->capacity==256); AG(ga); SG(sg,256); CHECK(!memcmp(storage,snap,256));
          { struct Arena before=*a; memset(&go,0xa5,sizeof(go)); *out=11;
            CHECK(!arena_allocate(a,257,1,out)); CHECK(*out==11); CHECK(!memcmp(a,&before,sizeof(before))); AG(ga); OG(go); SG(sg,256); CHECK(!memcmp(storage,snap,256)); } }
        /* unaligned base: assert non-aligned, guards follow real base */
        { uint8_t ub[8+64+8+16]; uint8_t *ust=ub+8;
          while((uintptr_t)ust % 16 == 0) ust++;
          CHECK((uintptr_t)ust % 16 != 0);
          memset(ub,0xa5,sizeof(ub)); memset(ust,0x5a,64);
          uint8_t usnap[64]; memcpy(usnap,ust,64);
          struct GArena gua; memset(&gua,0xa5,sizeof(gua)); struct Arena *ua=&gua.a;
          CHECK(arena_init(ua,(struct Bytes){ust,64}));
          AG(gua); CHECK(!memcmp(ust,usnap,64));
          for(int g=0;g<8;g++)CHECK(ust[g-8]==0xa5 && ust[64+g]==0xa5);
          memset(&go,0xa5,sizeof(go)); *out=0; uint64_t mo=0,mn=0;
          int ok=model_alloc((uint64_t)(uintptr_t)ust,64,0,8,16,&mo,&mn);
          CHECK(ok); CHECK(arena_allocate(ua,8,16,out)); CHECK(*out==mo && ua->used==mn);
          CHECK(*out%16==0);
          AG(gua); OG(go); CHECK(!memcmp(ust,usnap,64));
          for(int g=0;g<8;g++)CHECK(ust[g-8]==0xa5 && ust[64+g]==0xa5);
        }
        CHECK(!memcmp(storage,snap,256));
    }

    /* extreme virtual base and used>capacity: reject numerically */
    {
        struct GArena ga; memset(&ga,0xa5,sizeof(ga)); struct Arena *a=&ga.a;
        memset(a,0x22,sizeof(*a));
        a->base=(uint8_t*)(uintptr_t)0xfffffffffffffff0ULL; a->capacity=0x20; a->used=0x10;
        struct Arena before=*a;
        struct GOut go; memset(&go,0xa5,sizeof(go)); uint64_t *out=&go.v;
        memset(&go,0xa5,sizeof(go)); *out=99; CHECK(!arena_allocate(a,0x10,16,out)); CHECK(*out==99); CHECK(!memcmp(a,&before,sizeof(*a))); AG(ga); OG(go);
        memset(&go,0xa5,sizeof(go)); *out=99; CHECK(!arena_allocate(a,0x20,1,out)); CHECK(*out==99); CHECK(!memcmp(a,&before,sizeof(*a))); AG(ga); OG(go);
        memset(&go,0xa5,sizeof(go)); *out=99; CHECK(!arena_allocate(a,1,(uint64_t)1<<63,out)); CHECK(*out==99); CHECK(!memcmp(a,&before,sizeof(*a))); AG(ga); OG(go);
        { struct Arena snap=*a; memset(&go,0xa5,sizeof(go)); *out=99; CHECK(!arena_allocate(a,0,1,out)); CHECK(*out==99); CHECK(!memcmp(a,&snap,sizeof(*a))); AG(ga); OG(go); }
        struct GArena ge; memset(&ge,0xa5,sizeof(ge)); struct Arena *ev=&ge.a;
        memset(ev,0x22,sizeof(*ev));
        ev->base=(uint8_t*)(uintptr_t)0xfffffffffffff000ULL; ev->capacity=0x800; ev->used=0;
        memset(&go,0xa5,sizeof(go)); *out=99; uint64_t mo=0,mn=0;
        int ok=model_alloc((uint64_t)(uintptr_t)ev->base,ev->capacity,ev->used,0,16,&mo,&mn);
        CHECK(ok); CHECK(arena_allocate(ev,0,16,out)); CHECK(*out==mo && ev->used==mn); AG(ge); OG(go);
        ev->used=ev->capacity+1;
        { struct Arena snap=*ev; memset(&go,0xa5,sizeof(go)); *out=99; CHECK(!arena_allocate(ev,0,1,out)); CHECK(*out==99); CHECK(!memcmp(ev,&snap,sizeof(*ev))); AG(ge); OG(go); }
    }

    /* rewind: immediate observation + preserved fields */
    {
        uint8_t sg[8+64+8]; uint8_t *storage=sg+8;
        memset(sg,0xa5,sizeof(sg)); memset(storage,0x5a,64);
        uint8_t snap[64]; memcpy(snap,storage,64);
        struct GArena ga; memset(&ga,0xa5,sizeof(ga)); struct Arena *a=&ga.a;
        struct GOut go; memset(&go,0xa5,sizeof(go)); uint64_t *out=&go.v;
        CHECK(arena_init(a,(struct Bytes){storage,64}));
        AG(ga); CHECK(!memcmp(storage,snap,64)); SG(sg,64);
        memset(&go,0xa5,sizeof(go)); *out=0;
        CHECK(arena_allocate(a,10,8,out)); uint64_t m1=a->used; AG(ga); OG(go); SG(sg,64); CHECK(!memcmp(storage,snap,64));
        CHECK(arena_allocate(a,20,8,out)); uint64_t m2=a->used; AG(ga); OG(go); SG(sg,64); CHECK(!memcmp(storage,snap,64));
        CHECK(arena_rewind(a,m1)); CHECK(a->used==m1); CHECK(a->base==storage); CHECK(a->capacity==64); AG(ga); CHECK(!memcmp(storage,snap,64)); SG(sg,64);
        { struct Arena before=*a; CHECK(!arena_rewind(a,m2)); CHECK(!memcmp(a,&before,sizeof(before))); AG(ga); CHECK(!memcmp(storage,snap,64)); SG(sg,64); }
        { struct Arena before=*a; CHECK(!arena_rewind(a,a->capacity+1)); CHECK(!memcmp(a,&before,sizeof(before))); AG(ga); CHECK(!memcmp(storage,snap,64)); SG(sg,64); }
        CHECK(arena_rewind(a,0)); CHECK(a->used==0); CHECK(a->base==storage); CHECK(a->capacity==64); AG(ga); CHECK(!memcmp(storage,snap,64)); SG(sg,64);
        uint64_t o1=0,o2=0;
        memset(&go,0xa5,sizeof(go)); *out=0; CHECK(arena_allocate(a,10,8,out)); o1=*out; AG(ga); OG(go); SG(sg,64); CHECK(!memcmp(storage,snap,64));
        CHECK(arena_rewind(a,0)); CHECK(a->used==0); CHECK(a->base==storage); CHECK(a->capacity==64); AG(ga); SG(sg,64); CHECK(!memcmp(storage,snap,64));
        memset(&go,0xa5,sizeof(go)); *out=0; CHECK(arena_allocate(a,10,8,out)); o2=*out; AG(ga); OG(go); SG(sg,64); CHECK(!memcmp(storage,snap,64));
        CHECK(o1==o2);
        CHECK(!memcmp(storage,snap,64)); SG(sg,64);
    }

    /* fixed-seed 1200-step model sequence */
    {
        uint8_t sg[8+512+8]; uint8_t *storage=sg+8;
        memset(sg,0xa5,sizeof(sg)); memset(storage,0x77,512);
        uint8_t snap[512]; memcpy(snap,storage,512);
        struct GArena ga; memset(&ga,0xa5,sizeof(ga)); struct Arena *aa=&ga.a;
        struct GOut go; memset(&go,0xa5,sizeof(go)); uint64_t *out=&go.v;
        CHECK(arena_init(aa,(struct Bytes){storage,512}));
        AG(ga); OG(go); CHECK(!memcmp(storage,snap,512)); SG(sg,512);
        uint64_t seed=UINT64_C(0x123456789abcdef0);
        uint64_t marks[64]; int nm=0;
        for(int step=0;step<1200;step++){
            uint64_t op=rng(&seed)%3;
            if(op==0){
                uint64_t size=rng(&seed)%(512+1);
                uint64_t align=(uint64_t)1<<(rng(&seed)%13);
                memset(&go,0xa5,sizeof(go)); *out=UINT64_C(0xabcdef0123456789);
                struct Arena before=*aa; uint64_t mo=0,mn=0;
                int ok=model_alloc((uint64_t)(uintptr_t)aa->base,aa->capacity,aa->used,size,align,&mo,&mn);
                uint8_t r=arena_allocate(aa,size,align,out);
                CHECK(r==(uint8_t)ok);
                if(ok){CHECK(*out==mo);CHECK(aa->used==mn);CHECK(aa->base==before.base);CHECK(aa->capacity==before.capacity);if(nm<64)marks[nm++]=aa->used;}
                else {CHECK(*out==UINT64_C(0xabcdef0123456789));CHECK(!memcmp(aa,&before,sizeof(before)));}
            }else if(op==1 && nm>0){
                int idx=(int)(rng(&seed)%(uint64_t)nm);
                uint64_t mark=marks[idx];
                CHECK(arena_rewind(aa,mark)); CHECK(aa->used==mark); CHECK(aa->base==storage); CHECK(aa->capacity==512);
                nm=0;
            }
            AG(ga); OG(go); CHECK(!memcmp(storage,snap,512)); SG(sg,512);
        }
    }

    puts("native core.arena probes passed");return 0;
}
