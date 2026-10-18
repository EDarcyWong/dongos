#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DG __attribute__((sysv_abi))
#define COUNT 19u
#define PAGE UINT64_C(4096)
#define KBASE UINT64_C(0xffffffff80000000)
#define FOUR_G UINT64_C(0x100000000)
#define FILL 0x6b
#define E_INFO UINT64_C(0x02050001)
#define E_PHYSICAL UINT64_C(0x02050002)
#define E_MAP UINT64_C(0x02050003)
#define E_OWNER UINT64_C(0x02050004)
#define E_LAYOUT UINT64_C(0x02050005)
#define E_OUTPUT UINT64_C(0x02050006)
static unsigned case_number;
#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "boot resource failure case=%u line=%d: %s\n", case_number, __LINE__, #condition); \
    exit(1); } } while (0)

struct BootInfo {
    uint64_t magic, version, size, flags;
    uint64_t memory_map, memory_map_size, descriptor_size, descriptor_version;
    uint64_t framebuffer_base, framebuffer_size, width, height, stride, pixel_format;
    uint64_t rsdp, kernel_physical, kernel_size, pml4_physical, stack_physical, stack_size;
};
struct Span { uint64_t start, end; };
struct Layout {
    struct Span text, rodata, data, bss, gdt, tss, idt, df, nmi, exception_stack, workspace;
    uint64_t rsdp_size;
};
struct Resource { uint64_t kind, base, length; };
extern uint64_t DG br_info_size(void), br_info_align(void), br_span_size(void), br_span_align(void);
extern uint64_t DG br_layout_size(void), br_layout_align(void), br_resource_size(void), br_resource_align(void);
extern uint64_t DG br_count(void);
extern uint64_t DG br_collect(const struct BootInfo *, uint64_t, const uint8_t *, uint64_t,
                             const struct Layout *, struct Resource *, uint64_t, uint64_t *);

void DG __attribute__((noreturn)) __dong_panic(
    uint32_t kind, uint32_t line, const uint8_t *file, uint64_t length
) {
    fprintf(stderr, "unexpected boot resource panic kind=%u line=%u file=%.*s\n",
            kind, line, (int)length, (const char *)file);
    exit(99);
}

struct Buffer { uint8_t *allocation, *data; size_t size; };
struct Context {
    struct Buffer buffer[5]; /* BootInfo, Layout, raw map, output, returned count */
    uint64_t info_physical, raw_length, capacity;
    struct Span owners[5];
};
static struct BootInfo *info(struct Context *c) { return (struct BootInfo *)c->buffer[0].data; }
static struct Layout *layout(struct Context *c) { return (struct Layout *)c->buffer[1].data; }
static struct Span get_span(const struct Layout *l, unsigned index) {
    switch (index) {
        case 0: return l->text; case 1: return l->rodata; case 2: return l->data;
        case 3: return l->bss; case 4: return l->gdt; case 5: return l->tss;
        case 6: return l->idt; case 7: return l->df; case 8: return l->nmi;
        case 9: return l->exception_stack; default: CHECK(index == 10); return l->workspace;
    }
}
static void set_span(struct Layout *l, unsigned index, struct Span span) {
    switch (index) {
        case 0: l->text=span; break; case 1: l->rodata=span; break;
        case 2: l->data=span; break; case 3: l->bss=span; break;
        case 4: l->gdt=span; break; case 5: l->tss=span; break;
        case 6: l->idt=span; break; case 7: l->df=span; break;
        case 8: l->nmi=span; break; case 9: l->exception_stack=span; break;
        default: CHECK(index == 10); l->workspace=span; break;
    }
}
static struct Buffer buffer(size_t size) {
    struct Buffer result;
    result.allocation=malloc(size+32); CHECK(result.allocation != NULL);
    result.data=result.allocation+16; result.size=size;
    memset(result.allocation,0xa5,16); memset(result.data,FILL,size);
    memset(result.data+size,0x5a,16);
    return result;
}
static void guards(const struct Context *c) {
    for (unsigned b=0;b<5;b++) for (size_t i=0;i<16;i++) {
        CHECK(c->buffer[b].allocation[i] == 0xa5);
        CHECK(c->buffer[b].data[c->buffer[b].size+i] == 0x5a);
    }
}
static void write_descriptor(struct Context *c, unsigned index, uint32_t type,
                             uint64_t start, uint64_t pages) {
    size_t offset=(size_t)info(c)->descriptor_size*index;
    CHECK(offset+40 <= c->buffer[2].size);
    uint8_t *p=c->buffer[2].data+offset;
    uint64_t zero=0;
    memcpy(p,&type,4); memcpy(p+8,&start,8); memcpy(p+16,&zero,8);
    memcpy(p+24,&pages,8); memcpy(p+32,&zero,8);
}
static void descriptor_u64(struct Context *c, unsigned index, unsigned field, uint64_t value) {
    memcpy(c->buffer[2].data+info(c)->descriptor_size*index+field,&value,8);
}
static void descriptor_type(struct Context *c, unsigned index, uint32_t value) {
    memcpy(c->buffer[2].data+info(c)->descriptor_size*index,&value,4);
}

static struct Context baseline(uint64_t stride, int split) {
    struct Context c;
    c.buffer[0]=buffer(sizeof(struct BootInfo)); c.buffer[1]=buffer(sizeof(struct Layout));
    c.buffer[2]=buffer(65537); c.buffer[3]=buffer((COUNT+4)*sizeof(struct Resource));
    c.buffer[4]=buffer(sizeof(uint64_t));
    c.info_physical=UINT64_C(0x1001200); c.capacity=COUNT+4;
    c.raw_length=stride*(split?5:2);
    *info(&c)=(struct BootInfo){
        .magic=UINT64_C(0x544f4f42474e4f44),.version=1,.size=160,.flags=1,
        .memory_map=UINT64_C(0x1010000),.memory_map_size=c.raw_length,
        .descriptor_size=stride,.descriptor_version=1,
        .framebuffer_base=UINT64_C(0xe0000000),.framebuffer_size=8192+55,
        .rsdp=UINT64_C(0xf0000),.kernel_physical=UINT64_C(0x600000),.kernel_size=UINT64_C(0x40000),
        .pml4_physical=UINT64_C(0x1040000),.stack_physical=UINT64_C(0x1020000),.stack_size=65536,
    };
    *layout(&c)=(struct Layout){
        .text={KBASE,KBASE+0x10000}, .rodata={KBASE+0x10000,KBASE+0x18000},
        .data={KBASE+0x18000,KBASE+0x20000}, .bss={KBASE+0x20000,KBASE+0x40000},
        .gdt={KBASE+0x18000,KBASE+0x18028}, .tss={KBASE+0x20000,KBASE+0x20068},
        .idt={KBASE+0x21000,KBASE+0x22000}, .df={KBASE+0x22000,KBASE+0x26000},
        .nmi={KBASE+0x26000,KBASE+0x2a000}, .exception_stack={KBASE+0x2a000,KBASE+0x2e000},
        .workspace={KBASE+0x2e000,KBASE+0x3f000}, .rsdp_size=36,
    };
    c.owners[0]=(struct Span){UINT64_C(0x400000),UINT64_C(0xc00000)};
    write_descriptor(&c,0,1,c.owners[0].start,(c.owners[0].end-c.owners[0].start)/PAGE);
    if (split) {
        const struct Span separate[]={{UINT64_C(0x1001000),UINT64_C(0x1002000)},
            {UINT64_C(0x1010000),UINT64_C(0x1020000)}, {UINT64_C(0x1020000),UINT64_C(0x1030000)},
            {UINT64_C(0x1040000),UINT64_C(0x1048000)}};
        for (unsigned i=1;i<5;i++) {
            c.owners[i]=separate[i-1];
            write_descriptor(&c,i,2,c.owners[i].start,(c.owners[i].end-c.owners[i].start)/PAGE);
        }
    } else {
        for (unsigned i=1;i<5;i++) c.owners[i]=(struct Span){UINT64_C(0x1000000),UINT64_C(0x1400000)};
        write_descriptor(&c,1,2,c.owners[1].start,(c.owners[1].end-c.owners[1].start)/PAGE);
    }
    return c;
}
static void destroy(struct Context *c) {
    for (unsigned i=0;i<5;i++) free(c->buffer[i].allocation);
}
static void invoke(struct Context *c, uint64_t expected_error) {
    case_number++;
    uint8_t *before[5];
    guards(c);
    for (unsigned i=0;i<5;i++) {
        before[i]=malloc(c->buffer[i].size); CHECK(before[i] != NULL);
        memcpy(before[i],c->buffer[i].data,c->buffer[i].size);
    }
    uint64_t error=br_collect(info(c),c->info_physical,c->buffer[2].data,c->raw_length,
        layout(c),(struct Resource *)c->buffer[3].data,c->capacity,(uint64_t *)c->buffer[4].data);
    CHECK(error == expected_error);
    guards(c);
    for (unsigned i=0;i<5;i++) {
        if (expected_error || i<3) CHECK(!memcmp(before[i],c->buffer[i].data,c->buffer[i].size));
    }
    if (!expected_error) {
        CHECK(*(uint64_t *)c->buffer[4].data == COUNT);
        const struct Resource *actual=(const struct Resource *)c->buffer[3].data;
        const struct Resource zero={0,0,PAGE};
        CHECK(!memcmp(&actual[0],&zero,sizeof(zero)));
        for (unsigned i=1;i<6;i++) {
            CHECK(actual[i].kind == i);
            CHECK(actual[i].base == c->owners[i-1].start);
            CHECK(actual[i].length == c->owners[i-1].end-c->owners[i-1].start);
        }
        CHECK(actual[6].kind == 6 && actual[6].base == info(c)->framebuffer_base && actual[6].length == info(c)->framebuffer_size);
        CHECK(actual[7].kind == 7 && actual[7].base == info(c)->rsdp && actual[7].length == layout(c)->rsdp_size);
        for (unsigned i=0;i<11;i++) {
            struct Span span=get_span(layout(c),i);
            CHECK(actual[8+i].kind == 8+i);
            CHECK(actual[8+i].base == info(c)->kernel_physical+(span.start-KBASE));
            CHECK(actual[8+i].length == span.end-span.start);
        }
        CHECK(!memcmp(c->buffer[3].data+COUNT*sizeof(struct Resource),
                      before[3]+COUNT*sizeof(struct Resource),c->buffer[3].size-COUNT*sizeof(struct Resource)));
    }
    for (unsigned i=0;i<5;i++) free(before[i]);
}
static void positive_cases(void) {
    for (unsigned split=0;split<2;split++) for (uint64_t stride=40;stride<=64;stride+=8) {
        struct Context c=baseline(stride,(int)split); invoke(&c,0); destroy(&c);
    }
    struct Context c=baseline(48,0);
    /* The sole conventional zero-page descriptor exercises the one-page
     * validation scratch without affecting loader-owned resources. */
    write_descriptor(&c,2,7,0,1); c.raw_length+=48; info(&c)->memory_map_size=c.raw_length;
    invoke(&c,0); destroy(&c);
    c=baseline(40,0); info(&c)->kernel_size=UINT64_C(0x3f080); info(&c)->flags=UINT64_MAX;
    layout(&c)->rsdp_size=4096; invoke(&c,0); destroy(&c);
    c=baseline(40,0); info(&c)->kernel_physical=FOUR_G-UINT64_C(0x200000);
    c.owners[0]=(struct Span){info(&c)->kernel_physical,FOUR_G};
    write_descriptor(&c,0,1,c.owners[0].start,512); invoke(&c,0); destroy(&c);
    c=baseline(40,0); info(&c)->framebuffer_base=FOUR_G-PAGE; info(&c)->framebuffer_size=PAGE;
    info(&c)->rsdp=FOUR_G-PAGE; layout(&c)->rsdp_size=PAGE; invoke(&c,0); destroy(&c);
    c=baseline(56,1);
    uint8_t temporary[56]; memcpy(temporary,c.buffer[2].data,56);
    memcpy(c.buffer[2].data,c.buffer[2].data+4*56,56); memcpy(c.buffer[2].data+4*56,temporary,56);
    invoke(&c,0); destroy(&c); /* descriptor ordering does not choose resources */
}
static void header_and_map_failures(void) {
    for (unsigned which=0;which<26;which++) {
        struct Context c=baseline(40,0); uint64_t expected=E_MAP;
        switch (which) {
            case 0: info(&c)->magic^=1; expected=E_INFO; break;
            case 1: info(&c)->version=2; expected=E_INFO; break;
            case 2: info(&c)->size=159; expected=E_INFO; break;
            case 3: info(&c)->size=161; expected=E_INFO; break;
            case 4: info(&c)->flags=0; expected=E_INFO; break;
            case 5: info(&c)->flags=2; expected=E_INFO; break;
            case 6: c.raw_length=0; info(&c)->memory_map_size=0; break;
            case 7: c.raw_length=65537; info(&c)->memory_map_size=c.raw_length; break;
            case 8: info(&c)->memory_map_size++; break;
            case 9: info(&c)->descriptor_size=0; break;
            case 10: info(&c)->descriptor_size=39; break;
            case 11: info(&c)->descriptor_size=41; break;
            case 12: info(&c)->descriptor_size=UINT64_MAX; break;
            case 13: info(&c)->descriptor_size=UINT64_C(1)<<63; break;
            case 14: info(&c)->descriptor_version=0; break;
            case 15: info(&c)->descriptor_version=2; break;
            case 16: descriptor_u64(&c,0,8,UINT64_C(0x400001)); break;
            case 17: descriptor_u64(&c,0,24,0); break;
            case 18: descriptor_u64(&c,0,8,UINT64_MAX-UINT64_C(4095)); descriptor_u64(&c,0,24,2); break;
            case 19: descriptor_u64(&c,1,8,UINT64_C(0x401000)); break;
            case 20: c.raw_length--; info(&c)->memory_map_size=c.raw_length; break;
            case 21: write_descriptor(&c,2,0,UINT64_C(0x3000001),1); c.raw_length+=40; info(&c)->memory_map_size=c.raw_length; break;
            case 22: descriptor_type(&c,0,2); expected=E_OWNER; break;
            case 23: descriptor_type(&c,1,3); expected=E_OWNER; break;
            case 24: descriptor_u64(&c,0,8,info(&c)->kernel_physical); descriptor_u64(&c,0,24,64); expected=E_OWNER; break;
            default: info(&c)->descriptor_version=UINT64_MAX; break;
        }
        invoke(&c,expected); destroy(&c);
    }
    for (unsigned owner=1;owner<5;owner++) {
        struct Context c=baseline(48,1); descriptor_type(&c,owner,3);
        invoke(&c,E_OWNER); destroy(&c);
    }
}
static void physical_failures(void) {
    for (unsigned which=0;which<33;which++) {
        struct Context c=baseline(40,0); uint64_t expected=E_PHYSICAL;
        switch (which) {
            case 0: c.info_physical=0; break;
            case 1: c.info_physical=FOUR_G; break;
            case 2: c.info_physical=UINT64_MAX; break;
            case 3: info(&c)->kernel_physical=0; break;
            case 4: info(&c)->kernel_physical++; break;
            case 5: info(&c)->kernel_physical=FOUR_G; break;
            case 6: info(&c)->kernel_size=0; break;
            case 7: info(&c)->kernel_size=UINT64_C(0x200001); break;
            case 8: info(&c)->memory_map=0; break;
            case 9: info(&c)->memory_map=FOUR_G; break;
            case 10: info(&c)->memory_map=FOUR_G-1; break;
            case 11: info(&c)->stack_physical=0; break;
            case 12: info(&c)->stack_physical++; break;
            case 13: info(&c)->stack_physical=FOUR_G-PAGE; break;
            case 14: info(&c)->stack_size=0; break;
            case 15: info(&c)->stack_size=65535; break;
            case 16: info(&c)->pml4_physical=0; break;
            case 17: info(&c)->pml4_physical++; break;
            case 18: info(&c)->pml4_physical=FOUR_G; break;
            case 19: info(&c)->framebuffer_base=0; break;
            case 20: info(&c)->framebuffer_size=0; break;
            case 21: info(&c)->framebuffer_base=FOUR_G; break;
            case 22: info(&c)->framebuffer_size=UINT64_MAX; break;
            case 23: info(&c)->rsdp=0; break;
            case 24: info(&c)->rsdp=FOUR_G; break;
            case 25: info(&c)->rsdp=UINT64_MAX; break;
            case 26: info(&c)->memory_map=c.info_physical+1; break;
            case 27: info(&c)->pml4_physical=info(&c)->stack_physical+PAGE; break;
            case 28: c.info_physical=info(&c)->pml4_physical; break;
            case 29: c.info_physical=UINT64_C(0x1400000)-80; expected=E_OWNER; break;
            case 30: info(&c)->memory_map=UINT64_C(0x1400000)-40; expected=E_OWNER; break;
            case 31: info(&c)->stack_physical=UINT64_C(0x1400000)-32768; expected=E_OWNER; break;
            default: info(&c)->pml4_physical=UINT64_C(0x1400000); expected=E_OWNER; break;
        }
        invoke(&c,expected); destroy(&c);
    }
    struct Context c=baseline(40,0);
    info(&c)->kernel_physical=FOUR_G-UINT64_C(0x200000);
    write_descriptor(&c,0,1,info(&c)->kernel_physical,1024);
    invoke(&c,E_PHYSICAL); destroy(&c); /* owner envelope, not actual window, crosses 4G */
    c=baseline(40,0); descriptor_u64(&c,1,24,UINT64_C(1)<<20);
    invoke(&c,E_PHYSICAL); destroy(&c);
}
static void layout_and_capacity_failures(void) {
    for (unsigned index=0;index<11;index++) for (unsigned variant=0;variant<4;variant++) {
        struct Context c=baseline(40,0); struct Span span=get_span(layout(&c),index);
        if (variant==0) span.start=KBASE-1;
        if (variant==1) span.end=span.start;
        if (variant==2) span.end=span.start-1;
        if (variant==3) span.end=layout(&c)->bss.end+PAGE;
        set_span(layout(&c),index,span); invoke(&c,E_LAYOUT); destroy(&c);
    }
    for (unsigned which=0;which<7;which++) {
        struct Context c=baseline(40,0);
        switch (which) {
            case 0: layout(&c)->text.start+=PAGE; break;
            case 1: layout(&c)->rodata.start+=PAGE; break;
            case 2: layout(&c)->rodata.start++; layout(&c)->text.end++; break;
            case 3: layout(&c)->bss.end=UINT64_MAX; break;
            case 4: layout(&c)->rsdp_size=35; break;
            case 5: layout(&c)->rsdp_size=4097; break;
            default: info(&c)->kernel_size=1; break;
        }
        invoke(&c,E_LAYOUT); destroy(&c);
    }
    for (unsigned capacity=0;capacity<COUNT;capacity++) {
        struct Context c=baseline(48,1); c.capacity=capacity;
        invoke(&c,E_OUTPUT); destroy(&c);
    }
    struct Context c=baseline(64,0); c.capacity=COUNT; invoke(&c,0); destroy(&c);
}
int main(void) {
    CHECK(br_info_size()==sizeof(struct BootInfo) && br_info_align()==_Alignof(struct BootInfo));
    CHECK(br_span_size()==sizeof(struct Span) && br_span_align()==_Alignof(struct Span));
    CHECK(br_layout_size()==sizeof(struct Layout) && br_layout_align()==_Alignof(struct Layout));
    CHECK(br_resource_size()==sizeof(struct Resource) && br_resource_align()==_Alignof(struct Resource));
    CHECK(br_count()==COUNT);
    positive_cases(); header_and_map_failures(); physical_failures(); layout_and_capacity_failures();
    printf("boot resource probe ok: %u guarded full-snapshot cases\n",case_number);
    return 0;
}
