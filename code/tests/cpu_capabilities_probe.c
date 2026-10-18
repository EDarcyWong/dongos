#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef CPU_CAPABILITIES_MOCK_CPUID
#include <cpuid.h>
#endif

#define DG __attribute__((sysv_abi))
#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "CPU capability failure line=%d: %s\n", __LINE__, #condition); \
    exit(1); } } while (0)
#define E_MISSING UINT64_C(0x02040001)
#define E_BITS UINT64_C(0x02040002)
#define NX (UINT32_C(1) << 20)

struct Capabilities { uint64_t physical_bits; uint8_t nx; };
struct Guarded { uint8_t before[16]; struct Capabilities value; uint8_t after[16]; };
extern uint64_t DG caps_size(void), caps_align(void);
extern void DG caps_reset(struct Capabilities *);
extern uint64_t DG caps_decode(uint32_t, uint32_t, uint32_t, struct Capabilities *);
extern uint64_t DG caps_detect(struct Capabilities *);

void DG __attribute__((noreturn)) __dong_panic(
    uint32_t kind, uint32_t line, const uint8_t *file, uint64_t length
) {
    fprintf(stderr, "unexpected CPU capability panic kind=%u line=%u file=%.*s\n",
            kind, line, (int)length, (const char *)file);
    exit(99);
}

static struct Guarded fresh(void) {
    struct Guarded result;
    memset(&result, 0xa5, sizeof(result));
    return result;
}

static void guards(const struct Guarded *value) {
    for (size_t i = 0; i < 16; i++) {
        CHECK(value->before[i] == 0xa5);
        CHECK(value->after[i] == 0xa5);
    }
}

static void decode_case(uint32_t maximum, uint32_t features, uint32_t addresses,
                        uint64_t expected_error, uint64_t bits, uint8_t nx) {
    struct Guarded value = fresh(), before;
    memcpy(&before, &value, sizeof(value));
    CHECK(caps_decode(maximum, features, addresses, &value.value) == expected_error);
    guards(&value);
    if (expected_error) CHECK(!memcmp(&before, &value, sizeof(value)));
    else {
        CHECK(value.value.physical_bits == bits);
        CHECK(value.value.nx == nx);
    }
}

static void decode_boundaries(void) {
    struct Guarded empty = fresh();
    caps_reset(&empty.value);
    guards(&empty);
    CHECK(empty.value.physical_bits == 0 && empty.value.nx == 0);
    const uint32_t missing[] = {0, 1, UINT32_C(0x7fffffff), UINT32_C(0x80000000),
                                UINT32_C(0x80000001), UINT32_C(0x80000007)};
    for (size_t i = 0; i < sizeof(missing) / sizeof(missing[0]); i++) {
        decode_case(missing[i], NX, 48, E_MISSING, 0, 0);
        decode_case(missing[i], UINT32_MAX, 0, E_MISSING, 0, 0);
    }
    for (uint32_t bits = 0; bits <= 255; bits++) {
        uint64_t error = bits >= 32 && bits <= 52 ? 0 : E_BITS;
        /* Other EAX fields and feature bits must not replace the low byte/NX. */
        decode_case(UINT32_C(0x80000008), NX, bits, error, bits, 1);
        decode_case(UINT32_C(0x80000009), UINT32_MAX & ~NX,
                    UINT32_C(0xffffff00) | bits, error, bits, 0);
        decode_case(UINT32_MAX, UINT32_MAX,
                    UINT32_C(0x12345600) | bits, error, bits, 1);
    }
}

#ifdef CPU_CAPABILITIES_MOCK_CPUID
struct CpuId { uint32_t eax, ebx, ecx, edx; };
static uint32_t mock_maximum, mock_features, mock_addresses;
static unsigned calls;

void DG dg_arch_cpuid(uint32_t leaf, uint32_t subleaf, struct CpuId *out) {
    CHECK(subleaf == 0);
    CHECK(calls < 3);
    static const uint32_t expected[] = {
        UINT32_C(0x80000000), UINT32_C(0x80000001), UINT32_C(0x80000008)
    };
    CHECK(leaf == expected[calls]);
    calls++;
    *out = (struct CpuId){0, UINT32_MAX, UINT32_MAX, 0};
    if (leaf == UINT32_C(0x80000000)) out->eax = mock_maximum;
    if (leaf == UINT32_C(0x80000001)) out->edx = mock_features;
    if (leaf == UINT32_C(0x80000008)) out->eax = mock_addresses;
}

static void detect_case(uint32_t maximum, uint32_t features, uint32_t addresses,
                        uint64_t expected_error, unsigned expected_calls) {
    struct Guarded value = fresh(), before;
    memcpy(&before, &value, sizeof(value));
    mock_maximum = maximum; mock_features = features; mock_addresses = addresses;
    calls = 0;
    CHECK(caps_detect(&value.value) == expected_error);
    CHECK(calls == expected_calls);
    guards(&value);
    if (expected_error) CHECK(!memcmp(&before, &value, sizeof(value)));
    else {
        CHECK(value.value.physical_bits == (addresses & 255));
        CHECK(value.value.nx == !!(features & NX));
    }
}

static void detect_probe(void) {
    detect_case(0, NX, 48, E_MISSING, 1);
    detect_case(UINT32_C(0x80000007), NX, 48, E_MISSING, 1);
    detect_case(UINT32_C(0x80000008), NX, 0, E_BITS, 3);
    detect_case(UINT32_C(0x80000008), NX, 31, E_BITS, 3);
    detect_case(UINT32_C(0x80000008), NX, 53, E_BITS, 3);
    detect_case(UINT32_C(0x80000008), 0, 32, 0, 3);
    detect_case(UINT32_C(0x80000008), NX, 52, 0, 3);
    detect_case(UINT32_MAX, UINT32_MAX & ~NX, UINT32_C(0xffffff30), 0, 3);
    puts("CPU capability mock probe ok");
}
#else
static void detect_probe(void) {
    unsigned eax, ebx, ecx, edx;
    /* GCC's independent inline CPUID path does not call dg_arch_cpuid. */
    __cpuid_count(UINT32_C(0x80000000), 0, eax, ebx, ecx, edx);
    uint32_t maximum = eax;
    uint32_t features = 0, addresses = 0;
    uint64_t expected_error = E_MISSING;
    if (maximum >= UINT32_C(0x80000008)) {
        __cpuid_count(UINT32_C(0x80000001), 0, eax, ebx, ecx, edx);
        features = edx;
        __cpuid_count(UINT32_C(0x80000008), 0, eax, ebx, ecx, edx);
        addresses = eax;
        uint32_t bits = addresses & 255;
        expected_error = bits >= 32 && bits <= 52 ? 0 : E_BITS;
    }
    struct Guarded value = fresh(), before;
    memcpy(&before, &value, sizeof(value));
    CHECK(caps_detect(&value.value) == expected_error);
    guards(&value);
    if (expected_error) CHECK(!memcmp(&before, &value, sizeof(value)));
    else {
        CHECK(value.value.physical_bits == (addresses & 255));
        CHECK(value.value.nx == !!(features & NX));
    }
    printf("CPU capability independent CPUID probe ok: max=%08" PRIx32
           " physical_bits=%u nx=%u\n", maximum, addresses & 255, !!(features & NX));
}
#endif

int main(void) {
    CHECK(caps_size() == sizeof(struct Capabilities));
    CHECK(caps_align() == _Alignof(struct Capabilities));
    decode_boundaries();
    detect_probe();
    return 0;
}
