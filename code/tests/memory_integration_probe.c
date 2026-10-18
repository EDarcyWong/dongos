/* P2 host integration: actual Dong modules, independently modeled ownership.
 * Every simulated PA is translated by a checked offset into an aligned arena.
 * This process never loads CR3, enables NX, or runs a privileged instruction. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define PAGE UINT64_C(4096)
#define NP 128u
#define TABLES 8u
#define POOL_ORDER 3u
#define FILL 0x6b
#define NX (UINT64_C(1) << 63)
#define ADDRESS UINT64_C(0x000ffffffffff000)
#define E_NOT_INIT UINT64_C(0x02000001)
#define E_INVALID UINT64_C(0x02000003)
#define E_UNAVAILABLE UINT64_C(0x02000005)
#define E_OOM UINT64_C(0x02000007)
#define E_FREE UINT64_C(0x02000008)
#define E_CAPACITY UINT64_C(0x01000001)
#define E_MAPPED UINT64_C(0x02030001)
#define E_HOLE UINT64_C(0x02030002)
#define HIGH UINT64_C(0xffff800000200000)
#define LOW UINT64_C(0x400000)

struct ReservedRange { uint64_t base, length; };
struct PageRange { uint64_t start_page, page_count; };
struct Mapping { uint64_t physical, flags; };
extern uint64_t DG mi_reserved_size(void), mi_reserved_align(void), mi_range_size(void), mi_range_align(void);
extern uint64_t DG mi_buddy_size(void), mi_buddy_align(void), mi_page_meta_size(void), mi_page_meta_align(void);
extern uint64_t DG mi_space_size(void), mi_space_align(void), mi_table_size(void), mi_table_align(void);
extern uint64_t DG mi_mapping_size(void), mi_mapping_align(void);
extern void DG mi_buddy_reset(void *), mi_paging_reset(void *);
extern uint64_t DG mi_normalize(const void *, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t,
    const struct ReservedRange *, uint64_t, void *, uint64_t, struct PageRange *, uint64_t, uint64_t *);
extern uint64_t DG mi_buddy_init(void *, uint64_t, uint64_t, void *, uint64_t);
extern uint64_t DG mi_buddy_add(void *, uint64_t, uint64_t), mi_buddy_alloc(void *, uint64_t, uint64_t *);
extern uint64_t DG mi_buddy_free(void *, uint64_t, uint64_t), mi_buddy_count(const void *, uint64_t *);
extern uint64_t DG mi_paging_init(void *, void *, uint64_t, uint64_t, void *, uint64_t, uint64_t, uint64_t);
extern uint64_t DG mi_paging_root(const void *, uint64_t *), mi_paging_used(const void *, uint64_t *);
extern uint64_t DG mi_paging_map(void *, uint64_t, uint64_t, uint64_t), mi_paging_unmap(void *, uint64_t);
extern uint64_t DG mi_paging_protect(void *, uint64_t, uint64_t), mi_paging_query(const void *, uint64_t, struct Mapping *);

static const char *phase = "startup";
static unsigned scenario, step;
static uint64_t seed;
#define CHECK(X) do { if (!(X)) { fprintf(stderr, "integration failure scenario=%u phase=%s step=%u seed=%llu line=%d: %s\n", scenario, phase, step, (unsigned long long)seed, __LINE__, #X); exit(1); } } while (0)
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind, uint32_t line, const uint8_t *file, uint64_t length) {
    fprintf(stderr, "unexpected Dong panic %u %.*s:%u\n", kind, (int)length, (const char *)file, line);
    exit(99);
}
static uint64_t random64(void) { seed ^= seed << 13; seed ^= seed >> 7; seed ^= seed << 17; return seed; }
struct Buffer { uint8_t *raw, *data; size_t size, guard; };
struct View { uint8_t *data; size_t size; };
static struct Buffer buffer(size_t size, size_t alignment) {
    struct Buffer b = {0};
    CHECK(alignment && !(alignment & (alignment - 1)));
    b.size = size; b.guard = alignment < 16 ? 16 : alignment;
    b.raw = malloc(size + 3 * b.guard + alignment); CHECK(b.raw);
    b.data = (uint8_t *)(((uintptr_t)(b.raw + b.guard) + alignment - 1) & ~(uintptr_t)(alignment - 1));
    memset(b.data - b.guard, 0xa5, b.guard); memset(b.data, FILL, size); memset(b.data + size, 0x5a, b.guard);
    return b;
}
static void guards(const struct Buffer *b) {
    for (size_t i = 0; i < b->guard; i++) {
        CHECK(b->data[-(ptrdiff_t)b->guard + (ptrdiff_t)i] == 0xa5);
        CHECK(b->data[b->size + i] == 0x5a);
    }
}
struct Descriptor { uint64_t start, pages, attr; uint32_t type; };
struct Record { uint64_t va, pa, flags; };
enum Owner { BLOCKED, FREE, POOL, FRAME };
struct Context {
    struct Buffer arena, buddy, space, reservations;
    struct View raw, bmeta, pmeta, scratch, output, pool;
    uint8_t *saved_arena, *saved_buddy, *saved_space, *saved_reservations;
    uint64_t base, pool_pa;
    size_t stride, descriptors, reserved_count, total, map_count;
    uint8_t eligible[NP], owner[NP];
    struct Descriptor desc[8];
    struct Record maps[32];
};
static uint8_t *at(struct Context *c, uint64_t pa, size_t length) {
    CHECK(pa >= c->base && pa - c->base <= c->arena.size);
    size_t offset = (size_t)(pa - c->base);
    CHECK(length <= c->arena.size - offset);
    return c->arena.data + offset;
}
static struct View view(struct Context *c, unsigned page, size_t offset, size_t size) {
    CHECK(offset + size <= PAGE);
    struct View v = {at(c, c->base + page * PAGE + offset, size), size}; return v;
}
static int inside(size_t offset, const struct View *v, const struct Context *c, size_t limit) {
    if (!v->data || !limit) return 0;
    size_t start = (size_t)(v->data - c->arena.data);
    return offset >= start && offset - start < limit;
}
enum Allow { NONE = 0, BUDDY = 1, PAGING = 2, NORMALIZE = 4, RESET_SPACE = 8 };
static void before(struct Context *c) {
    step++;
    memcpy(c->saved_arena, c->arena.data, c->arena.size);
    memcpy(c->saved_buddy, c->buddy.data, c->buddy.size);
    memcpy(c->saved_space, c->space.data, c->space.size);
    memcpy(c->saved_reservations, c->reservations.data, c->reservations.size);
}
/* Allow only the documented write spans. This checks the entire arena,
 * including all data/reserved pages, buffer guards and excess metadata tails. */
static void after(struct Context *c, unsigned allow, size_t output_written) {
    guards(&c->arena); guards(&c->buddy); guards(&c->space); guards(&c->reservations);
    CHECK(!memcmp(c->saved_reservations, c->reservations.data, c->reservations.size));
    if (!(allow & BUDDY)) CHECK(!memcmp(c->saved_buddy, c->buddy.data, c->buddy.size));
    if (!(allow & (PAGING | RESET_SPACE))) CHECK(!memcmp(c->saved_space, c->space.data, c->space.size));
    const size_t bmeta_bytes = NP * (c->bmeta.size / (NP + 2));
    for (size_t i = 0; i < c->arena.size; i++) {
        if ((allow & BUDDY) && inside(i, &c->bmeta, c, bmeta_bytes)) continue;
        if ((allow & PAGING) && (inside(i, &c->pmeta, c, TABLES) || inside(i, &c->pool, c, c->pool.size))) continue;
        if ((allow & NORMALIZE) && (inside(i, &c->scratch, c, NP) || inside(i, &c->output, c, output_written * sizeof(struct PageRange)))) continue;
        CHECK(c->arena.data[i] == c->saved_arena[i]);
    }
}
static struct ReservedRange *reserved(struct Context *c) { return (struct ReservedRange *)c->reservations.data; }
static void reserve(struct Context *c, uint64_t base, uint64_t length) {
    CHECK(c->reserved_count < c->reservations.size / sizeof(struct ReservedRange));
    reserved(c)[c->reserved_count++] = (struct ReservedRange){base, length};
}
static uint64_t get64(const uint8_t *p) { uint64_t v; memcpy(&v, p, sizeof v); return v; }
static void put64(uint8_t *p, uint64_t v) { memcpy(p, &v, sizeof v); }
static void encode(struct Context *c) {
    for (size_t i = 0; i < c->descriptors; i++) {
        uint8_t *p = c->raw.data + i * c->stride;
        memset(p, 0x9c, c->stride);
        memcpy(p, &c->desc[i].type, 4); put64(p + 8, c->desc[i].start);
        put64(p + 24, c->desc[i].pages); put64(p + 32, c->desc[i].attr);
    }
}
static struct Context create(uint64_t base, size_t stride, int fragmented) {
    struct Context c = {0}; c.base = base; c.stride = stride;
    c.arena = buffer(NP * PAGE, PAGE);
    c.buddy = buffer((size_t)mi_buddy_size(), (size_t)mi_buddy_align());
    c.space = buffer((size_t)mi_space_size(), (size_t)mi_space_align());
    c.reservations = buffer(100 * sizeof(struct ReservedRange), 8);
    mi_buddy_reset(c.buddy.data); mi_paging_reset(c.space.data);
    CHECK(mi_page_meta_align() <= 64 && 64 % mi_page_meta_align() == 0);
    c.raw = view(&c, 5, 65, 7 * stride); /* deliberately unaligned UEFI bytes */
    c.bmeta = view(&c, 8, 64, (NP + 2) * (size_t)mi_page_meta_size());
    c.pmeta = view(&c, 9, 64, TABLES + 16);
    c.scratch = view(&c, 10, 64, NP + 16);
    c.output = view(&c, 11, 64, (NP + 2) * sizeof(struct PageRange));
    c.descriptors = 7;
    c.desc[0] = (struct Descriptor){base + 100 * PAGE, 32, 0, 7};
    c.desc[1] = (struct Descriptor){base + 80 * PAGE, 8, 0, 11}; /* MMIO/framebuffer */
    c.desc[2] = (struct Descriptor){base - 4 * PAGE, 68, 0, 7};
    c.desc[3] = (struct Descriptor){base + 96 * PAGE, 4, 0, 0x80}; /* unknown */
    c.desc[4] = (struct Descriptor){base + 64 * PAGE, 16, 0, 7};
    c.desc[5] = (struct Descriptor){base + 92 * PAGE, 4, NX, 7}; /* EFI_MEMORY_RUNTIME */
    c.desc[6] = (struct Descriptor){base + 256 * PAGE, 4, 0, 7};
    /* 88..91 has no descriptor. Resource sizes follow actual backing spans;
     * stack and previous bootstrap table pool reserve their complete frames. */
    reserve(&c, base, 4 * PAGE);                       /* text, rodata, data */
    reserve(&c, base + 4 * PAGE + 101, 73);             /* BootInfo */
    reserve(&c, base + 5 * PAGE + 65, c.raw.size);      /* raw map */
    reserve(&c, base + 6 * PAGE, 2 * PAGE);             /* stack */
    reserve(&c, base + 8 * PAGE + 64, c.bmeta.size);    /* buddy metadata */
    reserve(&c, base + 9 * PAGE + 64, c.pmeta.size);    /* paging metadata */
    reserve(&c, base + 10 * PAGE + 64, c.scratch.size); /* normalize scratch */
    reserve(&c, base + 11 * PAGE + 64, c.output.size);  /* normalized ranges */
    reserve(&c, base + 12 * PAGE, 4 * PAGE);            /* old boot tables */
    reserve(&c, base + 71 * PAGE - 1, 2);              /* two partial pages */
    reserve(&c, base + 80 * PAGE, 8 * PAGE);            /* explicit MMIO too */
    reserve(&c, base + 127 * PAGE + 23, 1);
    reserve(&c, base - 16, 32);                        /* clips/overlaps text */
    reserve(&c, UINT64_MAX, 0);                       /* empty is ignored */
    for (unsigned i = 0; i < 8; i++) {
        unsigned page = 32 + (unsigned)(random64() % 36);
        reserve(&c, base + page * PAGE + (random64() & 4095), 1 + (random64() & 511));
    }
    if (fragmented) for (unsigned i = 1; i < NP; i += 2) reserve(&c, base + i * PAGE, PAGE);
    for (size_t i = c.descriptors; i > 1; i--) {
        size_t j = (size_t)(random64() % i); struct Descriptor d = c.desc[i - 1]; c.desc[i - 1] = c.desc[j]; c.desc[j] = d;
    }
    encode(&c);
    /* Oracle: decide membership of each entire page by descriptor containment
     * and interval intersection, independently of normalize's scratch marks. */
    for (unsigned i = 0; i < NP; i++) {
        uint64_t lo = base + i * PAGE, hi = lo + PAGE; int available = 0;
        for (size_t d = 0; d < c.descriptors; d++) {
            const struct Descriptor *p = &c.desc[d];
            if (p->type == 7 && !(p->attr & NX) && lo >= p->start && hi <= p->start + p->pages * PAGE) available = 1;
        }
        for (size_t r = 0; r < c.reserved_count; r++) {
            const struct ReservedRange *p = &reserved(&c)[r];
            if (p->length && lo < p->base + p->length && p->base < hi) available = 0;
        }
        c.eligible[i] = (uint8_t)available; c.total += (size_t)available;
    }
    c.saved_arena = malloc(c.arena.size); c.saved_buddy = malloc(c.buddy.size);
    c.saved_space = malloc(c.space.size); c.saved_reservations = malloc(c.reservations.size);
    CHECK(c.saved_arena && c.saved_buddy && c.saved_space && c.saved_reservations);
    return c;
}
static size_t expected_free(const struct Context *c) {
    size_t n = 0; for (unsigned i = 0; i < NP; i++) n += c->owner[i] == FREE; return n;
}
static void count(struct Context *c) {
    uint64_t n = UINT64_MAX; before(c); CHECK(mi_buddy_count(c->buddy.data, &n) == 0); after(c, NONE, 0);
    CHECK(n == expected_free(c));
}
static size_t page_index(const struct Context *c, uint64_t pa) {
    CHECK(pa >= c->base && pa - c->base < NP * PAGE && !(pa & (PAGE - 1)));
    return (size_t)((pa - c->base) / PAGE);
}
static uint64_t allocate(struct Context *c, unsigned order, enum Owner owner, uint64_t error) {
    uint64_t pa = UINT64_MAX; before(c);
    CHECK(mi_buddy_alloc(c->buddy.data, order, &pa) == error); after(c, error ? NONE : BUDDY, 0);
    if (error) { CHECK(pa == UINT64_MAX); count(c); return pa; }
    size_t p = page_index(c, pa), pages = (size_t)1 << order;
    CHECK(p % pages == 0 && p + pages <= NP);
    for (size_t i = p; i < p + pages; i++) { CHECK(c->eligible[i] && c->owner[i] == FREE); c->owner[i] = (uint8_t)owner; }
    count(c); return pa;
}
static void release(struct Context *c, uint64_t pa, unsigned order, uint64_t error) {
    before(c); CHECK(mi_buddy_free(c->buddy.data, pa, order) == error); after(c, error ? NONE : BUDDY, 0);
    if (!error) {
        size_t p = page_index(c, pa), pages = (size_t)1 << order;
        for (size_t i = p; i < p + pages; i++) { CHECK(c->owner[i] == FRAME || c->owner[i] == POOL); c->owner[i] = FREE; }
    }
    count(c);
}
static void publish(struct Context *c) {
    phase = "normalize/publish";
    size_t expected_segments = 0;
    for (unsigned i = 0; i < NP; i++) if (c->eligible[i] && (!i || !c->eligible[i - 1])) expected_segments++;
    CHECK(expected_segments && c->total > TABLES);
    /* Failure does not publish or write any output. Scratch is caller workspace. */
    uint64_t used = UINT64_MAX; before(c);
    CHECK(mi_normalize(c->raw.data, c->raw.size, c->stride, 1, c->base, NP, reserved(c), c->reserved_count,
        c->scratch.data, c->scratch.size, (struct PageRange *)c->output.data, expected_segments - 1, &used) == E_CAPACITY);
    after(c, NORMALIZE, 0); CHECK(used == UINT64_MAX);
    /* Invalid descriptors outside the arena must also stop the pipeline. */
    uint64_t old_start = get64(c->raw.data + 8); put64(c->raw.data + 8, 1);
    before(c);
    CHECK(mi_normalize(c->raw.data, c->raw.size, c->stride, 1, c->base, NP, reserved(c), c->reserved_count,
        c->scratch.data, c->scratch.size, (struct PageRange *)c->output.data, NP, &used) == E_INVALID);
    after(c, NORMALIZE, 0); CHECK(used == UINT64_MAX); put64(c->raw.data + 8, old_start);
    before(c);
    CHECK(mi_normalize(c->raw.data, c->raw.size, c->stride, 1, c->base, NP, reserved(c), c->reserved_count,
        c->scratch.data, c->scratch.size, (struct PageRange *)c->output.data, expected_segments, &used) == 0);
    after(c, NORMALIZE, expected_segments); CHECK(used == expected_segments);
    struct PageRange *out = (struct PageRange *)c->output.data; size_t segment = 0;
    for (unsigned i = 0; i < NP;) {
        if (!c->eligible[i]) { i++; continue; }
        unsigned start = i; while (i < NP && c->eligible[i]) i++;
        CHECK(out[segment].start_page == start && out[segment].page_count == i - start); segment++;
    }
    before(c); CHECK(mi_buddy_init(c->buddy.data, c->base, NP, c->bmeta.data, NP + 2) == 0); after(c, BUDDY, 0); count(c);
    /* Reverse segment order: publishing must not depend on firmware ordering. */
    for (size_t i = (size_t)used; i > 0; i--) {
        struct PageRange range = out[i - 1]; before(c);
        CHECK(mi_buddy_add(c->buddy.data, range.start_page, range.page_count) == 0); after(c, BUDDY, 0);
        for (size_t j = 0; j < range.page_count; j++) {
            size_t p = (size_t)range.start_page + j; CHECK(c->eligible[p] && c->owner[p] == BLOCKED); c->owner[p] = FREE;
        }
        count(c);
    }
    CHECK(expected_free(c) == c->total);
    before(c); CHECK(mi_buddy_add(c->buddy.data, out[0].start_page, out[0].page_count) == E_UNAVAILABLE); after(c, NONE, 0); count(c);
    release(c, c->base, 0, E_FREE); /* static kernel is never published */
}
static int walk(struct Context *c, uint64_t va, struct Mapping *out) {
    uint64_t pa = c->pool_pa;
    for (unsigned level = 0; level < 4; level++) {
        CHECK(pa >= c->pool_pa && pa - c->pool_pa < c->pool.size && !(pa & (PAGE - 1)));
        uint64_t *table = (uint64_t *)at(c, pa, PAGE);
        size_t slot = (size_t)((va >> (39 - 9 * level)) & 511); uint64_t entry = table[slot];
        if (!(entry & 1)) { CHECK(entry == 0); return 0; }
        if (level < 3) { CHECK((entry & ~ADDRESS) == 7); pa = entry & ADDRESS; }
        else {
            CHECK(!(entry & ~(ADDRESS | NX | UINT64_C(7))));
            out->physical = (entry & ADDRESS) | (va & (PAGE - 1));
            out->flags = ((entry & 2) ? 1u : 0u) | ((entry & 4) ? 2u : 0u) | ((entry & NX) ? 0u : 4u);
            CHECK((out->flags & 5) != 5); return 1;
        }
    }
    CHECK(0); return 0;
}
static size_t visit(struct Context *c, size_t index, unsigned level, uint8_t *seen, size_t *leaves) {
    CHECK(index < TABLES && !seen[index] && c->pmeta.data[index] == 1); seen[index] = 1;
    uint64_t *table = (uint64_t *)(c->pool.data + index * PAGE); size_t tables = 1;
    for (unsigned i = 0; i < 512; i++) {
        uint64_t e = table[i]; if (!e) continue; CHECK(e & 1);
        if (level == 3) {
            size_t p = page_index(c, e & ADDRESS); CHECK(c->owner[p] == FRAME || p < 4 || p == 6 || p == 7); (*leaves)++;
        } else {
            CHECK((e & ~ADDRESS) == 7); uint64_t pa = e & ADDRESS;
            CHECK(pa >= c->pool_pa && pa - c->pool_pa < c->pool.size);
            tables += visit(c, (size_t)((pa - c->pool_pa) / PAGE), level + 1, seen, leaves);
        }
    }
    return tables;
}
static void verify_tree(struct Context *c) {
    uint8_t seen[TABLES] = {0}; size_t leaves = 0, tables = visit(c, 0, 0, seen, &leaves);
    CHECK(leaves == c->map_count);
    for (unsigned i = 0; i < TABLES; i++) CHECK(c->pmeta.data[i] == seen[i]);
    before(c); uint64_t root = UINT64_MAX, used = UINT64_MAX;
    CHECK(mi_paging_root(c->space.data, &root) == 0 && root == c->pool_pa);
    CHECK(mi_paging_used(c->space.data, &used) == 0 && used == tables);
    for (size_t i = 0; i < c->map_count; i++) {
        struct Mapping raw = {0}, query = {0}; const struct Record *r = &c->maps[i];
        CHECK(walk(c, r->va + 137, &raw)); CHECK(raw.physical == r->pa + 137 && raw.flags == r->flags);
        CHECK(mi_paging_query(c->space.data, r->va + 137, &query) == 0);
        CHECK(query.physical == raw.physical && query.flags == raw.flags);
        for (size_t j = 0; j < i; j++) if (c->maps[j].pa == r->pa) CHECK(!((r->flags | c->maps[j].flags) & 1) || !((r->flags | c->maps[j].flags) & 4));
    }
    const uint64_t holes[] = {0, HIGH + UINT64_C(0xff000), HIGH + UINT64_C(0x102000)};
    for (size_t i = 0; i < sizeof holes / sizeof holes[0]; i++) {
        struct Mapping raw = {0}, query = {UINT64_MAX, UINT64_MAX};
        CHECK(!walk(c, holes[i], &raw)); CHECK(mi_paging_query(c->space.data, holes[i], &query) == E_HOLE);
        CHECK(query.physical == UINT64_MAX && query.flags == UINT64_MAX);
    }
    after(c, NONE, 0); count(c);
}
static void tables_used(struct Context *c, uint64_t expected) {
    uint64_t used = UINT64_MAX; before(c);
    CHECK(mi_paging_used(c->space.data, &used) == 0 && used == expected);
    after(c, NONE, 0);
}
static void map(struct Context *c, uint64_t va, uint64_t pa, uint64_t flags, uint64_t error) {
    before(c); CHECK(mi_paging_map(c->space.data, va, pa, flags) == error); after(c, error ? NONE : PAGING, 0);
    if (!error) { CHECK(c->map_count < 32); c->maps[c->map_count++] = (struct Record){va, pa, flags}; }
    verify_tree(c);
}
static void unmap(struct Context *c, uint64_t va) {
    size_t i = 0; while (i < c->map_count && c->maps[i].va != va) i++; CHECK(i < c->map_count);
    before(c); CHECK(mi_paging_unmap(c->space.data, va) == 0); after(c, PAGING, 0);
    c->maps[i] = c->maps[--c->map_count]; verify_tree(c);
}
static void protect(struct Context *c, uint64_t va, uint64_t flags, uint64_t error) {
    before(c); CHECK(mi_paging_protect(c->space.data, va, flags) == error); after(c, error ? NONE : PAGING, 0);
    if (!error) { size_t i = 0; while (i < c->map_count && c->maps[i].va != va) i++; CHECK(i < c->map_count); c->maps[i].flags = flags; }
    verify_tree(c);
}
static void drain(struct Context *c) {
    phase = "allocation exhaustion";
    uint64_t live[NP]; size_t n = 0, available = expected_free(c);
    while (expected_free(c)) { CHECK(n < NP); live[n++] = allocate(c, 0, FRAME, 0); }
    CHECK(n == available); allocate(c, 0, FRAME, E_OOM);
    /* Every eligible page is either a held pool/live frame or in this drain. */
    for (unsigned i = 0; i < NP; i++) CHECK(c->eligible[i] ? (c->owner[i] == FRAME || c->owner[i] == POOL) : c->owner[i] == BLOCKED);
    for (size_t i = n; i > 1; i--) { size_t j = (size_t)(random64() % i); uint64_t p = live[i - 1]; live[i - 1] = live[j]; live[j] = p; }
    for (size_t i = 0; i < n; i++) release(c, live[i], 0, 0);
    CHECK(expected_free(c) == available);
}
static void destroy(struct Context *c) {
    guards(&c->arena); guards(&c->buddy); guards(&c->space); guards(&c->reservations);
    free(c->arena.raw); free(c->buddy.raw); free(c->space.raw); free(c->reservations.raw);
    free(c->saved_arena); free(c->saved_buddy); free(c->saved_space); free(c->saved_reservations);
}
static void run(uint64_t base, size_t stride, int fragmented) {
    scenario++; step = 0; struct Context c = create(base, stride, fragmented); publish(&c);
    if (fragmented) {
        phase = "fragmented pool refusal"; allocate(&c, POOL_ORDER, POOL, E_OOM);
        struct Mapping out = {UINT64_MAX, UINT64_MAX}; before(&c);
        CHECK(mi_paging_query(c.space.data, LOW, &out) == E_NOT_INIT); after(&c, NONE, 0);
        CHECK(out.physical == UINT64_MAX && out.flags == UINT64_MAX);
        drain(&c); CHECK(expected_free(&c) == c.total); destroy(&c); return;
    }
    phase = "pool ownership"; c.pool_pa = allocate(&c, POOL_ORDER, POOL, 0);
    c.pool = (struct View){at(&c, c.pool_pa, TABLES * PAGE), TABLES * PAGE};
    CHECK((uintptr_t)c.pool.data != c.pool_pa && !((uintptr_t)c.pool.data & (PAGE - 1)));
    /* Width failure cannot lose the allocated pool; retry with modeled 36-bit support. */
    if (base >= UINT64_C(0x100000000)) {
        before(&c); CHECK(mi_paging_init(c.space.data, c.pool.data, TABLES, c.pool_pa, c.pmeta.data, c.pmeta.size, 32, 1) == E_INVALID); after(&c, NONE, 0); count(&c);
    }
    before(&c); CHECK(mi_paging_init(c.space.data, c.pool.data, TABLES, c.pool_pa, c.pmeta.data, c.pmeta.size, 36, 1) == 0); after(&c, PAGING, 0);
    verify_tree(&c); release(&c, c.pool_pa + PAGE, 0, E_FREE);
    uint64_t a = allocate(&c, 0, FRAME, 0), b = allocate(&c, 0, FRAME, 0);
    memset(at(&c, a, PAGE), 0x3c, PAGE); memset(at(&c, b, PAGE), 0xc3, PAGE);
    phase = "kernel/user permissions";
    map(&c, HIGH, base, 4, 0); map(&c, HIGH + PAGE, base + PAGE, 4, 0); /* text RX */
    map(&c, HIGH + 2 * PAGE, base + 2 * PAGE, 0, 0); /* rodata R/NX */
    map(&c, HIGH + 3 * PAGE, base + 3 * PAGE, 1, 0); /* data RW/NX */
    map(&c, HIGH + UINT64_C(0x100000), base + 6 * PAGE, 1, 0);
    map(&c, HIGH + UINT64_C(0x101000), base + 7 * PAGE, 1, 0);
    map(&c, LOW, a, 3, 0); map(&c, LOW + PAGE, a, 3, 0); /* same-owned-frame alias */
    map(&c, LOW + 2 * PAGE, b, 3, 0);
    tables_used(&c, 7);
    protect(&c, HIGH, 0, 0); protect(&c, HIGH, 4, 0);
    protect(&c, HIGH + 3 * PAGE, 0, 0); protect(&c, HIGH + 3 * PAGE, 1, 0);
    protect(&c, HIGH, 5, E_INVALID);
    map(&c, LOW, b, 3, E_MAPPED);
    phase = "map failure caller rollback";
    uint64_t failed = allocate(&c, 0, FRAME, 0);
    map(&c, UINT64_C(0xffff900000000000), failed, 1, E_OOM); /* needs 3 tables, only 1 free */
    CHECK(c.owner[page_index(&c, failed)] == FRAME); release(&c, failed, 0, 0);
    /* Failed flags likewise cannot consume a frame or change the hierarchy. */
    map(&c, LOW + 3 * PAGE, b, 5, E_INVALID);
    drain(&c); verify_tree(&c);
    phase = "unmap and explicit frame release";
    unmap(&c, LOW); CHECK(c.owner[page_index(&c, a)] == FRAME);
    /* The other alias still translates; no buddy page is released by unmap. */
    unmap(&c, LOW + PAGE); release(&c, a, 0, 0);
    unmap(&c, LOW + 2 * PAGE); release(&c, b, 0, 0);
    while (c.map_count) unmap(&c, c.maps[c.map_count - 1].va);
    tables_used(&c, 1);
    CHECK(expected_free(&c) == c.total - TABLES); /* root-only still owns entire pool */
    before(&c); mi_paging_reset(c.space.data); after(&c, RESET_SPACE, 0);
    /* No Space references remain and no activation occurred: caller may now return pool. */
    release(&c, c.pool_pa, POOL_ORDER, 0); CHECK(expected_free(&c) == c.total);
    release(&c, c.pool_pa, POOL_ORDER, E_FREE);
    drain(&c); CHECK(expected_free(&c) == c.total);
    phase = "recoalesced pool allocation";
    uint64_t again = allocate(&c, POOL_ORDER, POOL, 0); release(&c, again, POOL_ORDER, 0);
    CHECK(expected_free(&c) == c.total); destroy(&c);
}
int main(int argc, char **argv) {
    seed = argc > 1 ? (uint64_t)strtoull(argv[1], NULL, 0) : UINT64_C(0x6d656d6f727932);
    if (!seed) seed = 1;
    CHECK(mi_reserved_size() == sizeof(struct ReservedRange) && mi_reserved_align() == _Alignof(struct ReservedRange));
    CHECK(mi_range_size() == sizeof(struct PageRange) && mi_range_align() == _Alignof(struct PageRange));
    CHECK(mi_mapping_size() == sizeof(struct Mapping) && mi_mapping_align() == _Alignof(struct Mapping));
    CHECK(mi_table_size() == PAGE && mi_table_align() == PAGE);
    run(UINT64_C(0x10000000), 40, 0);
    run(UINT64_C(0x100000000), 48, 0);
    run((UINT64_C(1) << 36) - NP * PAGE, 56, 0);
    run(UINT64_C(0x20000000), 56, 1);
    puts("memory integration probe ok: reservations, ownership, raw walks, rollback, reclaim");
    return 0;
}
