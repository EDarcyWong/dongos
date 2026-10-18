#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif

#define DG __attribute__((sysv_abi))
#define PAGE UINT64_C(4096)
#define KERNEL UINT64_C(0xffffffff80000000)
#define STACK UINT64_C(0xffff900000001000)
#define INVALID UINT64_C(0x02090001)
#define BAD_TREE UINT64_C(0x02060005)
#define NX UINT64_C(0x8000000000000000)
static unsigned checks;
#define CHECK(X) do { checks++; if (!(X)) { fprintf(stderr,"activation check %u at %d: %s\n",checks,__LINE__,#X); exit(1); } } while(0)
struct State { uint64_t cr0, cr3, cr4, efer, rflags, pat; };
struct Plan { uint64_t cr0, efer, actions; };
struct Display { uint64_t base, bytes, width, height, stride, format; };
struct View {
    struct Display display;
    uint64_t boot_info, raw_map, raw_size, descriptor_size, rsdp, rsdp_size;
    uint64_t pool, pool_physical, pool_pages, stack_bottom, stack_top;
    uint64_t stack_probe_bottom, stack_probe_top, root_physical;
};
struct Report {
    uint64_t cr3, cr0, cr4, efer, pat, rflags, entry_rsp, entry_rbp;
    uint64_t rsp, rbp, nested_value, display_value, runtime_value, cache_steps;
};
_Static_assert(sizeof(struct Report)==112,"activation report ABI");
_Static_assert(_Alignof(struct Report)==8,"activation report alignment");
#define OFFSET(F,N) _Static_assert(offsetof(struct Report,F)==8*(N),"activation " #F " offset")
OFFSET(cr3,0); OFFSET(cr0,1); OFFSET(cr4,2); OFFSET(efer,3); OFFSET(pat,4); OFFSET(rflags,5);
OFFSET(entry_rsp,6); OFFSET(entry_rbp,7); OFFSET(rsp,8); OFFSET(rbp,9); OFFSET(nested_value,10);
OFFSET(display_value,11); OFFSET(runtime_value,12); OFFSET(cache_steps,13);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t bytes) {
    fprintf(stderr,"unexpected Dong panic %u %.*s:%u\n",kind,(int)bytes,(const char *)file,line);
    exit(99);
}

#ifndef DG_AUDIT
extern uint64_t DG activation_verify(const struct Report *,const struct State *,const struct Plan *,const struct View *);
extern void DG activation_empty(struct Report *);
struct Inputs {
    uint64_t lo;
    struct Report report;
    struct State before;
    struct Plan plan;
    struct View view;
    uint64_t hi;
};
static struct Inputs baseline(void) {
    struct Inputs a;
    memset(&a,0,sizeof a);
    a.lo=UINT64_C(0x123456789abcdef0); a.hi=UINT64_C(0xfedcba9876543210);
    a.before=(struct State){UINT64_C(0x80000011),0x200000,0x620,0x500,2,UINT64_C(0x0007040600070406)};
    a.plan=(struct Plan){UINT64_C(0x80010011),0xd00,7};
    a.view.root_physical=0x400000;
    a.view.stack_bottom=STACK; a.view.stack_top=STACK+65536;
    a.report=(struct Report){0x400000,UINT64_C(0x80010011),0x620,0xd00,
        UINT64_C(0x0007040600070406),2,STACK+65536,0,STACK+65528,STACK+65520,
        UINT64_C(0x414354495645),0x0055aa33,UINT64_C(0x52554e54494d45),31};
    return a;
}
static void verify(struct Inputs *a,int good) {
    struct Inputs saved=*a;
    CHECK(activation_verify(&a->report,&a->before,&a->plan,&a->view)==(good?0:INVALID));
    CHECK(!memcmp(a,&saved,sizeof saved));
}
static void pointer_failures(void) {
    struct Inputs a=baseline(),saved=a;
    const uintptr_t invalid[]={0,1,UINTPTR_MAX,UINTPTR_MAX-7};
    for(unsigned i=0;i<sizeof invalid/sizeof invalid[0];i++) {
        CHECK(activation_verify((const struct Report *)invalid[i],&a.before,&a.plan,&a.view)==INVALID);
        CHECK(activation_verify(&a.report,(const struct State *)invalid[i],&a.plan,&a.view)==INVALID);
        CHECK(activation_verify(&a.report,&a.before,(const struct Plan *)invalid[i],&a.view)==INVALID);
        CHECK(activation_verify(&a.report,&a.before,&a.plan,(const struct View *)invalid[i])==INVALID);
        CHECK(!memcmp(&a,&saved,sizeof a));
    }
}
static void control_failures(void) {
    for(unsigned nxe=0;nxe<2;nxe++) for(unsigned wp=0;wp<2;wp++) {
        struct Inputs a=baseline();
        a.before.efer|=(uint64_t)nxe<<11; a.before.cr0|=(uint64_t)wp<<16;
        a.plan.actions=4+!nxe+2*!wp;
        verify(&a,1);
    }
    /* A readback may vary ordinary status flags without losing the required
     * reserved bit or enabling IF/DF/VM. */
    struct Inputs a=baseline(); a.report.rflags=0x8d7; verify(&a,1);
    const uint64_t bad_flags[]={0,0x200|2,0x400|2,0x20000|2,0x40000|2};
    for(unsigned i=0;i<5;i++){a=baseline();a.report.rflags=bad_flags[i];verify(&a,0);}
    for(unsigned field=0;field<14;field++) {
        uint64_t words[14]; a=baseline();memcpy(words,&a.report,sizeof words);
        words[field]^=field==5?2:1;memcpy(&a.report,words,sizeof words);verify(&a,0);
    }
    const uint64_t roots[]={0,0x400001,UINT64_C(0x100000000),0x200000};
    for(unsigned i=0;i<4;i++){a=baseline();a.report.cr3=a.view.root_physical=roots[i];verify(&a,0);}
    for(unsigned field=0;field<3;field++) {
        uint64_t words[3];a=baseline();memcpy(words,&a.plan,sizeof words);
        words[field]^=1;memcpy(&a.plan,words,sizeof words);verify(&a,0);
    }
    const unsigned cr0_bad[]={0,31,29,30},cr4_bad[]={5,7,12,17,23};
    for(unsigned i=0;i<4;i++){a=baseline();a.before.cr0^=UINT64_C(1)<<cr0_bad[i];verify(&a,0);}
    for(unsigned i=0;i<5;i++){a=baseline();a.before.cr4^=UINT64_C(1)<<cr4_bad[i];a.report.cr4=a.before.cr4;verify(&a,0);}
    a=baseline();a.before.rflags=0x202;verify(&a,0);
    a=baseline();a.before.pat^=1;a.report.pat=a.before.pat;verify(&a,0);
    a=baseline();a.before.cr3|=1;verify(&a,0);
    for(unsigned value=0;value<64;value++){a=baseline();a.report.cache_steps=value;verify(&a,value==31);}
}
static void stack_boundaries(void) {
    struct Inputs a=baseline();
    const uint64_t good_rsp[]={STACK+8,STACK+24,STACK+65528};
    const uint64_t good_rbp[]={STACK,STACK+16,STACK+65520};
    for(unsigned i=0;i<3;i++) for(unsigned j=0;j<3;j++) {
        a=baseline();a.report.rsp=good_rsp[i];a.report.rbp=good_rbp[j];verify(&a,1);
    }
    const uint64_t bad_rsp[]={0,STACK-8,STACK,STACK+7,STACK+9,STACK+65535,STACK+65536,STACK+65544,UINT64_MAX};
    const uint64_t bad_rbp[]={0,STACK-16,STACK-1,STACK+1,STACK+65519,STACK+65521,STACK+65528,STACK+65536,UINT64_MAX-15};
    for(unsigned i=0;i<sizeof bad_rsp/sizeof bad_rsp[0];i++){a=baseline();a.report.rsp=bad_rsp[i];verify(&a,0);}
    for(unsigned i=0;i<sizeof bad_rbp/sizeof bad_rbp[0];i++){a=baseline();a.report.rbp=bad_rbp[i];verify(&a,0);}
    for(int delta=-8;delta<=8;delta+=8){a=baseline();a.report.entry_rsp+=(uint64_t)delta;verify(&a,delta==0);}
    a=baseline();a.report.entry_rbp=STACK+65520;verify(&a,0);
    a=baseline();a.view.stack_bottom=a.view.stack_top;verify(&a,0);
    a=baseline();a.view.stack_bottom=a.view.stack_top+16;verify(&a,0);
    /* Coherent bounds near UINT64_MAX exercise subtraction rather than an
     * overflowing rbp+16 computation. */
    a=baseline();a.view.stack_bottom=UINT64_MAX-65535;a.view.stack_top=UINT64_MAX-7;
    a.report.entry_rsp=a.view.stack_top;a.report.rsp=UINT64_MAX-15;a.report.rbp=UINT64_MAX-15;verify(&a,0);
    a=baseline();
    for(unsigned offset=0;offset<65536;offset++) {
        a.report.rsp=STACK+offset;verify(&a,(offset%16)==8);
    }
    a=baseline();
    for(unsigned offset=0;offset<65536;offset++) {
        a.report.rbp=STACK+offset;verify(&a,(offset%16)==0&&offset<=65520);
    }
}
int main(void) {
    struct Inputs a=baseline();verify(&a,1);
    struct { uint64_t lo; struct Report report; uint64_t hi; } zero;
    memset(&zero,0xa6,sizeof zero);uint64_t lo=zero.lo,hi=zero.hi;
    activation_empty(&zero.report);struct Report expected={0};
    CHECK(!memcmp(&zero.report,&expected,sizeof expected)&&zero.lo==lo&&zero.hi==hi);
    pointer_failures();control_failures();stack_boundaries();
    printf("activation native checks passed: %u\n",checks);return 0;
}
#else
struct Span { uint64_t start,end; };
struct Layout {
    struct Span text,rodata,data,bss,gdt,tss,idt,df,nmi,exception_stack,workspace;
    uint64_t rsdp_size;
};
extern uint64_t DG audit_init(void *,uint64_t,const struct Layout *,const struct View *,uint64_t);
extern uint64_t DG audit_map(uint64_t,uint64_t,uint64_t);
extern uint64_t DG audit_validate(uint64_t,uint64_t);
extern void DG audit_ready(uint64_t),audit_bad_count(void),audit_bad_ist(void);
static uint64_t *pool;
static const uint64_t pool_pa=0x400000,kernel_pa=0x2000000;
static uint64_t hhdm;
static uint64_t boot_info[20];
static struct Layout layout;
static struct View view;
static void raw_checks(int strict,int active) {
    unsigned char *saved=malloc(128*4096);CHECK(saved!=NULL);memcpy(saved,pool,128*4096);
    CHECK(audit_validate(pool_pa,0)==(strict?0:BAD_TREE));
    CHECK(audit_validate(pool_pa,1)==(active?0:BAD_TREE));
    CHECK(!memcmp(saved,pool,128*4096));free(saved);
}
static void add(uint64_t virtual,uint64_t physical,uint64_t flags) { CHECK(audit_map(virtual,physical,flags)==0); }
static void baseline(void) {
    memset(pool,0,128*4096);memset(boot_info,0,sizeof boot_info);
    /* BootInfo offset 136 is the bootstrap root, read independently by the
     * production allow-list; its other physical fields are not accessed. */
    boot_info[17]=0x180000;
    layout=(struct Layout){
        .text={KERNEL,KERNEL+0x4000},.rodata={KERNEL+0x4000,KERNEL+0x6000},
        .data={KERNEL+0x6000,KERNEL+0x8000},.bss={KERNEL+0x8000,KERNEL+0x40000},
        .gdt={KERNEL+0x6000,KERNEL+0x6028},.tss={KERNEL+0x8000,KERNEL+0x8068},
        .idt={KERNEL+0x9000,KERNEL+0xa000},.df={KERNEL+0xb000,KERNEL+0xf000},
        .nmi={KERNEL+0x11000,KERNEL+0x15000},.exception_stack={KERNEL+0x17000,KERNEL+0x1b000},
        .workspace={KERNEL+0x30000,KERNEL+0x3f000},.rsdp_size=36,
    };
    memset(&view,0,sizeof view);hhdm=(uint64_t)(uintptr_t)pool-pool_pa;
    view.boot_info=(uint64_t)(uintptr_t)boot_info;
    view.raw_map=hhdm+0x800000;view.raw_size=96;view.descriptor_size=48;
    view.rsdp=hhdm+0x900000;view.rsdp_size=36;
    view.pool=(uint64_t)(uintptr_t)pool;view.pool_physical=pool_pa;view.pool_pages=128;
    view.stack_bottom=STACK;view.stack_top=STACK+65536;
    view.stack_probe_bottom=hhdm+0xa00000;view.stack_probe_top=view.stack_probe_bottom+65536;
    view.root_physical=pool_pa;view.display.base=hhdm+0xb00000;view.display.bytes=4096;
    CHECK(audit_init(pool,pool_pa,&layout,&view,kernel_pa)==0);
    add(KERNEL,kernel_pa,4);add(KERNEL+0x4000,kernel_pa+0x4000,0);
    add(KERNEL+0x6000,kernel_pa+0x6000,1);add(KERNEL+0x8000,kernel_pa+0x8000,1);
    add(STACK,0xa00000,1);add(view.raw_map,0x800000,1);add(view.rsdp,0x900000,0);
    add(view.pool,pool_pa,1);add(view.stack_probe_bottom,0xa00000,1);
    add(view.display.base,0xb00000,1|8);add(hhdm+0x180000,0x180000,1);
    raw_checks(1,1);
}
static uint64_t *entry(uint64_t virtual,unsigned depth) {
    uint64_t physical=pool_pa;
    for(unsigned level=0;level<=depth;level++) {
        CHECK(physical>=pool_pa&&physical-pool_pa<128*4096&&!(physical&4095));
        uint64_t *current=pool+(physical-pool_pa)/8;
        uint64_t *item=&current[(virtual>>(39-9*level))&511];
        if(level==depth)return item;
        CHECK((*item&7)==7);physical=*item&UINT64_C(0x000ffffffffff000);
    }
    abort();
}
static void permission_masks(void) {
    for(unsigned level=0;level<4;level++) {
        baseline();uint64_t *item=entry(STACK,level),original=*item;
        for(unsigned bit=0;bit<64;bit++) {
            *item=original^(UINT64_C(1)<<bit);
            raw_checks(0,bit==5||(level==3&&bit==6));*item=original;
        }
        *item=original|0x60;raw_checks(0,level==3);*item=original;
    }
    /* Accumulating A throughout the tree and D on every mapped leaf is the
     * only allowed difference after activation, even for read-only leaves. */
    baseline();
    const uint64_t leaves[]={KERNEL,KERNEL+0x4000,KERNEL+0x6000,KERNEL+0x8000,STACK,
        view.raw_map,view.rsdp,view.pool,view.stack_probe_bottom,view.display.base,hhdm+0x180000};
    for(unsigned i=0;i<sizeof leaves/sizeof leaves[0];i++) {
        for(unsigned level=0;level<3;level++)*entry(leaves[i],level)|=0x20;
        *entry(leaves[i],3)|=0x60;
    }
    raw_checks(0,1);
}
static void malformed_trees(void) {
    const uint64_t garbage[]={0x20,0x40,0x60};
    for(unsigned level=0;level<4;level++) for(unsigned i=0;i<3;i++) {
        baseline();uint64_t *item=entry(STACK,level);
        /* Choose an unused neighboring slot at the selected level. */
        uint64_t *table=(uint64_t *)((uintptr_t)item&~(uintptr_t)4095);
        unsigned slot=(unsigned)(item-table),free_slot=(slot+1)%512;
        while(table[free_slot])free_slot=(free_slot+1)%512;
        table[free_slot]=garbage[i];raw_checks(0,0);
    }
    baseline();uint64_t *link=entry(STACK,0);*link=pool_pa|7;raw_checks(0,0);
    baseline();link=entry(STACK,0);uint64_t duplicate=*link;
    unsigned slot=0;while(pool[slot])slot++;pool[slot]=duplicate;raw_checks(0,0);
    baseline();*entry(STACK,3)=0;raw_checks(0,0);
    baseline();audit_bad_count();raw_checks(0,0);
    baseline();audit_ready(0);raw_checks(0,0);
    baseline();audit_bad_ist();raw_checks(0,0);
    baseline();CHECK(audit_validate(pool_pa+PAGE,1)==BAD_TREE);
    CHECK(audit_validate(0,1)==BAD_TREE);CHECK(audit_validate(pool_pa|1,1)==BAD_TREE);
}
static void extra_mappings(void) {
    const uint64_t guards[]={0,STACK-PAGE,STACK+65536,KERNEL+0xa000,KERNEL+0xf000,
        KERNEL+0x10000,KERNEL+0x15000,KERNEL+0x16000,KERNEL+0x1b000,KERNEL+0x40000};
    for(unsigned i=0;i<sizeof guards/sizeof guards[0];i++) {
        baseline();uint64_t pa=guards[i]>=KERNEL?kernel_pa+guards[i]-KERNEL:0xc00000;
        add(guards[i],pa,1);raw_checks(0,0);
    }
    baseline();add(hhdm+kernel_pa,kernel_pa,1);raw_checks(0,0);
    baseline();add(hhdm+0xc00000,0xc00000,1);raw_checks(0,0);
    baseline();add(0x700000,0x700000,1);raw_checks(0,0);
}
int main(void) {
#ifdef _WIN32
    pool=_aligned_malloc(128*4096,4096);
#else
    pool=aligned_alloc(4096,128*4096);
#endif
    CHECK(pool!=NULL);permission_masks();malformed_trees();extra_mappings();
#ifdef _WIN32
    _aligned_free(pool);
#else
    free(pool);
#endif
    printf("activation raw audit checks passed: %u\n",checks);return 0;
}
#endif
