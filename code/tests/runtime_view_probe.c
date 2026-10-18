/* Synthetic physical addresses are never host pointers. Every production call
 * passes through checked(), which snapshots the full input/output and guards. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define U(x) UINT64_C(x)
#define HHDM U(0xffff800000000000)
#define STACK U(0xffff900000001000)
#define LIMIT U(0x100000000)
#define E_VIEW U(0x02070001)
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"runtime view failed line %d, call %u: %s\n",__LINE__,calls,#x);exit(1); } } while (0)
struct Info {
    uint64_t magic,version,size,flags,raw,raw_size,descriptor_size,descriptor_version;
    uint64_t framebuffer,size_fb,width,height,stride,pixel_format,rsdp,kernel,kernel_size,root,stack,stack_size;
};
struct Display { uint64_t framebuffer,size,width,height,stride,pixel_format; };
struct View {
    struct Display display;
    uint64_t boot_info,raw_map,raw_size,descriptor_size,rsdp,rsdp_size;
    uint64_t pool,pool_physical,pool_pages,stack_bottom,stack_top,probe_bottom,probe_top,root;
};
struct Parameters { struct Info info; uint64_t physical,rsdp_size,pool,stack; };
struct Input { uint64_t before[2];struct Info info;uint64_t after[2]; };
struct Output { uint64_t before[2];uint8_t body[160];uint64_t after[2]; };
extern uint64_t DG rv_display(const struct Info*,struct Display*);
extern uint64_t DG rv_make(const struct Info*,uint64_t,uint64_t,uint64_t,uint64_t,struct View*);
extern uint64_t DG rv_display_size(void),rv_view_size(void),rv_view_align(void);
extern void DG rv_empty(struct View*);
static unsigned calls,successes,failures;
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length) {
    fprintf(stderr,"unexpected runtime view panic %u at %.*s:%u\n",kind,(int)length,file,line);exit(99);
}
static struct Parameters valid(void) {
    struct Parameters p={
        {U(0x544f4f42474e4f44),1,160,1,U(0x200000),80,40,1,
         U(0x10000000),640*480*4,640,480,640,1,U(0x300000),U(0x800000),U(0x200000),U(0xa00000),U(0x900000),65536},
        U(0x100000),36,U(0x400000),U(0x500000)
    };
    return p;
}
/* Independent expected field list. No pointer is created from a model PA. */
static struct View expected(const struct Parameters *p) {
    struct View v={
        {HHDM+p->info.framebuffer,p->info.size_fb,p->info.width,p->info.height,p->info.stride,p->info.pixel_format},
        HHDM+p->physical,HHDM+p->info.raw,p->info.raw_size,p->info.descriptor_size,
        HHDM+p->info.rsdp,p->rsdp_size,HHDM+p->pool,p->pool,128,
        STACK,STACK+65536,HHDM+p->stack,HHDM+p->stack+65536,p->pool
    };
    return v;
}
/* storage: 0 normal, 1 null source, 2 null destination, 3 actual alias,
 * 4 wrapped source span, 5 wrapped destination span. */
static void checked(const struct Parameters *p,int make,uint64_t error,int storage) {
    struct Input in,before_in;struct Output out,before_out,want;
    memset(&in,0xa6,sizeof(in));in.info=p->info;before_in=in;
    memset(&out,0xb7,sizeof(out));before_out=out;want=out;
    const struct Info *source=&in.info;void *destination=out.body;
    if(storage==1)source=NULL;
    if(storage==2)destination=NULL;
    if(storage==3)destination=&in.info;
    if(storage==4)source=(const struct Info*)(uintptr_t)(UINT64_MAX-7);
    if(storage==5)destination=(void*)(uintptr_t)(UINT64_MAX-7);
    calls++;
    uint64_t got=make?rv_make(source,p->physical,p->rsdp_size,p->pool,p->stack,destination):rv_display(source,destination);
    CHECK(got==error);
    CHECK(!memcmp(&in,&before_in,sizeof(in)));
    if(error) { CHECK(!memcmp(&out,&before_out,sizeof(out)));failures++; }
    else {
        struct View v=expected(p);
        memcpy(want.body,&v,make?sizeof(v):sizeof(v.display));
        CHECK(!memcmp(&out,&want,sizeof(out)));successes++;
    }
}
static void both(const struct Parameters *p,uint64_t error) { checked(p,0,error,0);checked(p,1,error,0); }
static void base(struct Parameters *p,unsigned index,uint64_t value) {
    switch(index) {
        case 0:p->physical=value;break;case 1:p->info.raw=value;break;
        case 2:p->info.rsdp=value;break;case 3:p->info.framebuffer=value;break;
        case 4:p->pool=value;break;case 5:p->stack=value;break;
        default:CHECK(0);
    }
}
static uint64_t length(const struct Parameters *p,unsigned index) {
    const uint64_t n[]={160,p->info.raw_size,p->rsdp_size,p->info.size_fb,524288,65536};return n[index];
}
static uint64_t seed=U(0x4b8cf7a15e02839d);
static uint64_t rng(void) { seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;return seed; }
int main(void) {
    CHECK(sizeof(struct Info)==160&&sizeof(struct Display)==48&&sizeof(struct View)==160);
    CHECK(rv_display_size()==48&&rv_view_size()==160&&rv_view_align()==8);
    { struct Output o,snapshot;memset(&o,0xa9,sizeof(o));snapshot=o;
      rv_empty((struct View*)o.body);memset(snapshot.body,0,sizeof(snapshot.body));
      CHECK(!memcmp(&o,&snapshot,sizeof(o))); }
    struct Parameters p=valid();both(&p,0);
    for(int make=0;make<2;make++)for(int storage=1;storage<=5;storage++)checked(&p,make,E_VIEW,storage);
#define BAD_BOTH(field,value) do { p=valid();p.info.field=(value);both(&p,E_VIEW); } while(0)
    BAD_BOTH(magic,0);BAD_BOTH(version,2);BAD_BOTH(size,159);BAD_BOTH(size,161);BAD_BOTH(flags,2);
    BAD_BOTH(width,0);BAD_BOTH(width,8193);BAD_BOTH(height,0);BAD_BOTH(height,8193);
    BAD_BOTH(stride,0);BAD_BOTH(stride,639);BAD_BOTH(stride,16385);BAD_BOTH(pixel_format,2);
    BAD_BOTH(framebuffer,0);BAD_BOTH(framebuffer,LIMIT);BAD_BOTH(framebuffer,UINT64_MAX);
    BAD_BOTH(framebuffer,LIMIT-100);BAD_BOTH(size_fb,0);BAD_BOTH(size_fb,640*480*4-1);
    BAD_BOTH(size_fb,UINT64_MAX);BAD_BOTH(width,UINT64_MAX);BAD_BOTH(stride,UINT64_MAX);
    p=valid();p.info.width=1;p.info.height=1;p.info.stride=1;p.info.size_fb=4;p.info.pixel_format=0;both(&p,0);
    p=valid();p.info.width=8192;p.info.height=8192;p.info.stride=16384;p.info.size_fb=U(16384)*8192*4;both(&p,0);
    p=valid();p.info.framebuffer=LIMIT-p.info.size_fb;both(&p,0);
#define BAD_INFO(field,value) do { p=valid();p.info.field=(value);checked(&p,1,E_VIEW,0); } while(0)
#define BAD_PARAM(field,value) do { p=valid();p.field=(value);checked(&p,1,E_VIEW,0); } while(0)
    BAD_INFO(raw,0);BAD_INFO(raw,LIMIT);BAD_INFO(raw,UINT64_MAX);BAD_INFO(raw,LIMIT-79);
    BAD_INFO(raw_size,0);BAD_INFO(raw_size,65537);BAD_INFO(raw_size,79);BAD_INFO(raw_size,UINT64_MAX);
    BAD_INFO(descriptor_size,0);BAD_INFO(descriptor_size,39);BAD_INFO(descriptor_size,41);
    BAD_INFO(descriptor_size,UINT64_MAX);BAD_INFO(descriptor_version,0);BAD_INFO(descriptor_version,2);
    BAD_INFO(rsdp,0);BAD_INFO(rsdp,LIMIT);BAD_INFO(rsdp,UINT64_MAX);BAD_INFO(rsdp,LIMIT-35);
    BAD_PARAM(physical,0);BAD_PARAM(physical,LIMIT);BAD_PARAM(physical,UINT64_MAX);BAD_PARAM(physical,LIMIT-159);
    BAD_PARAM(rsdp_size,0);BAD_PARAM(rsdp_size,35);BAD_PARAM(rsdp_size,4097);BAD_PARAM(rsdp_size,UINT64_MAX);
    BAD_PARAM(pool,0);BAD_PARAM(pool,U(0x401000));BAD_PARAM(pool,LIMIT);BAD_PARAM(pool,UINT64_MAX);
    BAD_PARAM(stack,0);BAD_PARAM(stack,U(0x501000));BAD_PARAM(stack,LIMIT);BAD_PARAM(stack,UINT64_MAX);
    p=valid();p.info.raw_size=65536;p.info.descriptor_size=4096;p.rsdp_size=4096;checked(&p,1,0,0);
    p=valid();p.physical=LIMIT-160;checked(&p,1,0,0);
    p=valid();p.info.raw=LIMIT-80;checked(&p,1,0,0);
    p=valid();p.info.rsdp=LIMIT-36;checked(&p,1,0,0);
    p=valid();p.pool=LIMIT-524288;checked(&p,1,0,0);
    p=valid();p.stack=LIMIT-65536;checked(&p,1,0,0);
    /* Every pair overlaps in isolation; exact touching endpoints are legal. */
    for(unsigned i=0;i<6;i++)for(unsigned j=i+1;j<6;j++) {
        p=valid();base(&p,i,U(0x2000000));base(&p,j,U(0x2000000));checked(&p,1,E_VIEW,0);
        p=valid();uint64_t bytes=length(&p,i);base(&p,i,U(0x2000000)-bytes);base(&p,j,U(0x2000000));checked(&p,1,0,0);
    }
    /* display deliberately does not require a memory-map view or pool. */
    p=valid();p.info.raw=UINT64_MAX;p.info.descriptor_size=0;p.info.rsdp=0;p.physical=0;p.pool=0;p.stack=0;checked(&p,0,0,0);
    for(unsigned round=0;round<1000;round++) {
        p=valid();p.info.width=1+rng()%8192;p.info.height=1+rng()%8192;
        p.info.stride=p.info.width+rng()%(16385-p.info.width);p.info.pixel_format=rng()&1;
        p.info.size_fb=p.info.stride*p.info.height*4;
        p.info.framebuffer=U(0x10000000)+(rng()%4096)*4096;
        p.info.descriptor_size=40+8*(rng()%24);p.info.raw_size=p.info.descriptor_size*(1+rng()%16);
        p.rsdp_size=36+rng()%4061;p.pool=U(0x400000)+(rng()%16)*524288;p.stack=U(0x1000000)+(rng()%16)*65536;
        both(&p,0);
        switch(round%6) {
            case 0:p.info.size_fb--;both(&p,E_VIEW);break;
            case 1:p.info.raw_size++;checked(&p,1,E_VIEW,0);break;
            case 2:p.pool++;checked(&p,1,E_VIEW,0);break;
            case 3:p.stack++;checked(&p,1,E_VIEW,0);break;
            case 4:p.physical=p.info.raw;checked(&p,1,E_VIEW,0);break;
            default:p.info.rsdp=LIMIT-p.rsdp_size+1;checked(&p,1,E_VIEW,0);break;
        }
    }
    CHECK(successes>2000&&failures>1000);
    printf("runtime view probe ok: %u guarded calls, %u success, %u rejected\n",calls,successes,failures);
    return 0;
}
