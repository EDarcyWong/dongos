#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DG __attribute__((sysv_abi))
#define PAGE UINT64_C(4096)
#define KBASE UINT64_C(0xffffffff80000000)
#define STACK_BYTES UINT64_C(16384)
struct Span { uint64_t start, end; };
struct Layout {
    struct Span text, rodata, data, bss, gdt, tss, idt, df, nmi, exception_stack, workspace;
    uint64_t rsdp_size;
};
struct Box { uint8_t before[32]; struct Layout layout; uint8_t after[32]; };
extern uint64_t DG ist_valid(const struct Layout *);
extern uint64_t DG ist_is_guard(uint64_t, const struct Layout *);
extern uint64_t DG ist_layout_size(void), ist_layout_align(void);
static unsigned checks, layouts;
#define CHECK(X) do { if (!(X)) { fprintf(stderr, "IST layout failure layout=%u check=%u line=%d: %s\n", layouts, checks, __LINE__, #X); exit(1); } } while (0)
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind, uint32_t line, const uint8_t *file, uint64_t length) {
    fprintf(stderr, "unexpected Dong panic %u %.*s:%u\n", kind, (int)length, (const char *)file, line);
    exit(99);
}
static struct Box baseline(uint64_t base) {
    struct Box box;
    memset(&box, 0x6b, sizeof box);
    box.layout = (struct Layout){
        .text={base,base+0x4000}, .rodata={base+0x4000,base+0x6000},
        .data={base+0x6000,base+0x8000}, .bss={base+0x8000,base+0x40000},
        .gdt={base+0x6000,base+0x6028}, .tss={base+0x8000,base+0x8068},
        .idt={base+0x9000,base+0xa000}, .df={base+0xb000,base+0xf000},
        .nmi={base+0x11000,base+0x15000}, .exception_stack={base+0x17000,base+0x1b000},
        .workspace={base+0x30000,base+0x3f000}, .rsdp_size=36,
    };
    return box;
}
static struct Span *stack(struct Layout *l, unsigned index) {
    if (index == 0) return &l->df;
    if (index == 1) return &l->nmi;
    return &l->exception_stack;
}
static struct Span *live(struct Layout *l, unsigned index) {
    if (index == 0) return &l->gdt;
    if (index == 1) return &l->tss;
    if (index == 2) return &l->idt;
    return &l->workspace;
}
static void valid(struct Box *box, int expected) {
    struct Box saved = *box;
    checks++;
    CHECK(ist_valid(&box->layout) == (uint64_t)expected);
    CHECK(!memcmp(&saved, box, sizeof saved));
}
static void guard(struct Box *box, uint64_t address, int expected) {
    struct Box saved = *box;
    checks++;
    CHECK(ist_is_guard(address, &box->layout) == (uint64_t)expected);
    CHECK(!memcmp(&saved, box, sizeof saved));
}
static void invalid(struct Box *box) {
    layouts++;
    valid(box, 0);
    const uint64_t candidates[] = {0, UINT64_MAX, KBASE, KBASE+0xa000, KBASE+0xf000,
        KBASE+0x10000, KBASE+0x15000, KBASE+0x16000, KBASE+0x1b000};
    for (size_t i=0; i<sizeof candidates/sizeof candidates[0]; i++) guard(box, candidates[i], 0);
}
static void valid_skip_sets(void) {
    const unsigned permutations[6][3] = {{0,1,2},{0,2,1},{1,0,2},{1,2,0},{2,0,1},{2,1,0}};
    const uint64_t bases[] = {KBASE, UINT64_C(0x100000), UINT64_C(0xfffffffffffbf000)};
    for (size_t base=0; base<sizeof bases/sizeof bases[0]; base++)
    for (unsigned a=0; a<6; a++) for (unsigned b=a+1; b<6; b++) for (unsigned c=b+1; c<6; c++)
    for (unsigned order=0; order<6; order++) {
        struct Box box=baseline(bases[base]);
        const unsigned slots[3]={a,b,c};
        uint8_t skipped[56]={0};
        /* The independent model selects three disjoint six-page slots and
         * marks their first/last page. It never calls the Dong predicate. */
        for (unsigned i=0; i<3; i++) {
            unsigned slot=slots[permutations[order][i]];
            uint64_t bottom=box.layout.bss.start+(3+6*slot)*PAGE;
            *stack(&box.layout,i)=(struct Span){bottom,bottom+STACK_BYTES};
            skipped[2+6*slot]=1; skipped[7+6*slot]=1;
        }
        layouts++;
        valid(&box,1);
        unsigned holes=0, mapped=0;
        for (unsigned page=0; page<56; page++) {
            uint64_t address=box.layout.bss.start+page*PAGE;
            guard(&box,address,skipped[page]);
            guard(&box,address+1,0); guard(&box,address+PAGE-1,0);
            if (skipped[page]) holes++; else mapped++;
        }
        CHECK(holes==6 && mapped==50);
        for (unsigned i=0; i<3; i++) {
            struct Span s=*stack(&box.layout,i);
            CHECK(s.end-s.start==STACK_BYTES);
            for (unsigned page=0; page<4; page++) guard(&box,s.start+page*PAGE,0);
        }
        guard(&box,box.layout.bss.start-PAGE,0); guard(&box,box.layout.bss.end,0);
        guard(&box,0,0); guard(&box,UINT64_MAX,0);
    }
}
static void malformed_bss_and_stacks(void) {
    for (unsigned variant=0; variant<6; variant++) {
        struct Box box=baseline(KBASE);
        switch (variant) {
            case 0: box.layout.bss.start++; break;
            case 1: box.layout.bss.end--; break;
            case 2: box.layout.bss.end=box.layout.bss.start; break;
            case 3: box.layout.bss.end=box.layout.bss.start-PAGE; break;
            case 4: box.layout.bss.start=UINT64_MAX; break;
            default: box.layout.bss.end=0; break;
        }
        invalid(&box);
    }
    for (unsigned i=0; i<3; i++) for (unsigned variant=0; variant<13; variant++) {
        struct Box box=baseline(KBASE); struct Span *s=stack(&box.layout,i);
        switch (variant) {
            case 0: s->start++; s->end++; break;
            case 1: s->start--; s->end--; break;
            case 2: s->end-=PAGE; break;
            case 3: s->end+=PAGE; break;
            case 4: s->end=s->start; break;
            case 5: s->end=s->start-PAGE; break;
            case 6: s->start=box.layout.bss.start; s->end=s->start+STACK_BYTES; break;
            case 7: s->end=box.layout.bss.end; s->start=s->end-STACK_BYTES; break;
            case 8: s->start=box.layout.bss.start-PAGE; s->end=s->start+STACK_BYTES; break;
            case 9: s->end=box.layout.bss.end+PAGE; s->start=s->end-STACK_BYTES; break;
            case 10: s->start=0; s->end=STACK_BYTES; break;
            case 11: s->start=UINT64_MAX-STACK_BYTES; s->end=UINT64_MAX; break;
            default: s->start=UINT64_MAX-PAGE; s->end=PAGE; break;
        }
        invalid(&box);
    }
    for (unsigned a=0; a<3; a++) for (unsigned b=a+1; b<3; b++)
    for (unsigned variant=0; variant<3; variant++) {
        struct Box box=baseline(KBASE); struct Span first=*stack(&box.layout,a);
        struct Span *second=stack(&box.layout,b);
        uint64_t bottom=variant==0 ? first.start : variant==1 ? first.end : first.end+PAGE;
        *second=(struct Span){bottom,bottom+STACK_BYTES};
        invalid(&box); /* same stack, touching usable ranges, shared guard */
    }
}
static void live_resource_intersections(void) {
    const unsigned guard_pages[]={2,7,8,13,14,19};
    for (unsigned resource=0; resource<4; resource++) for (unsigned g=0; g<6; g++)
    for (unsigned variant=0; variant<5; variant++) {
        struct Box box=baseline(KBASE); uint64_t page=box.layout.bss.start+guard_pages[g]*PAGE;
        struct Span *s=live(&box.layout,resource);
        switch (variant) {
            case 0: *s=(struct Span){page,page+PAGE}; break;
            case 1: *s=(struct Span){page,page+1}; break;
            case 2: *s=(struct Span){page+PAGE-1,page+PAGE}; break;
            case 3: *s=(struct Span){page-1,page+1}; break;
            default: *s=(struct Span){page+PAGE-1,page+PAGE+1}; break;
        }
        invalid(&box);
    }
    for (unsigned resource=0; resource<4; resource++) for (unsigned variant=0; variant<2; variant++) {
        struct Box box=baseline(KBASE); struct Span *s=live(&box.layout,resource);
        s->end=variant ? s->start-1 : s->start;
        invalid(&box);
    }
    /* Half-open boundaries adjacent to the first/last guard stay valid. */
    for (unsigned resource=0; resource<4; resource++) for (unsigned side=0; side<2; side++) {
        struct Box box=baseline(KBASE);
        *live(&box.layout,resource)=side ? (struct Span){KBASE+0x1c000,KBASE+0x1c001}
                                      : (struct Span){KBASE+0x9fff,KBASE+0xa000};
        layouts++; valid(&box,1);
        guard(&box,KBASE+0xa000,1); guard(&box,KBASE+0x1b000,1);
    }
}
int main(void) {
    CHECK(ist_layout_size()==sizeof(struct Layout) && ist_layout_align()==_Alignof(struct Layout));
    CHECK(ist_valid(NULL)==0 && ist_is_guard(0,NULL)==0 && ist_is_guard(PAGE,NULL)==0);
    valid_skip_sets(); malformed_bss_and_stacks(); live_resource_intersections();
    printf("IST layout probe ok: %u layouts, %u immutable calls, six guards and 16KiB stacks\n",layouts,checks);
    return 0;
}
