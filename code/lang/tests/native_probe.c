/* The host harness supplies an independent SysV boundary and panic observer. */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DG __attribute__((sysv_abi))
#define DECL_U(name) extern uint64_t DG name(uint64_t, uint64_t)
#define DECL_I(name) extern int64_t DG name(int64_t, int64_t)
DECL_U(dg_add); DECL_U(dg_sub); DECL_U(dg_mul); DECL_U(dg_div); DECL_U(dg_mod);
DECL_U(dg_shl); DECL_U(dg_shr); DECL_U(dg_bits); DECL_U(dg_order);
DECL_I(dg_iadd); DECL_I(dg_isub); DECL_I(dg_imul); DECL_I(dg_idiv); DECL_I(dg_imod);
extern uint64_t DG dg_uneg(uint64_t);
extern int64_t DG dg_ineg(int64_t);
extern int64_t DG dg_sar(int64_t, uint64_t);
extern uint64_t DG dg_litshift(uint64_t);
extern uint8_t DG dg_and(uint8_t, uint64_t);
extern uint8_t DG dg_or(uint8_t, uint64_t);
extern uint8_t DG dg_not(uint8_t);
extern uint8_t DG dg_ult(uint64_t, uint64_t);
extern uint8_t DG dg_ilt(int64_t, int64_t);
extern uint8_t DG dg_equal(uint8_t, uint8_t);
extern uint64_t DG dg_factorial(uint64_t);
extern uint64_t DG dg_loop(uint64_t);
extern int64_t DG dg_zero(void);
extern uint64_t DG abi_probe(void);

static uint32_t expected_kind;
int panic_entry_alignment;

void DG __attribute__((noreturn)) panic_record(uint32_t kind, uint32_t line, const uint8_t *file, uint64_t len)
{
    if (kind != expected_kind || len != 15 || memcmp(file, "scalar_probe.dg", 15) || !line || panic_entry_alignment != 8) {
        fprintf(stderr, "invalid panic ABI: kind=%u line=%u len=%" PRIu64 " rsp%%16=%d\n", kind, line, len, panic_entry_alignment);
        exit(100);
    }
    printf("observed panic %u at line %u with aligned SysV arguments\n", kind, line);
    exit((int)(64 + kind));
}

#define CHECK(expr) do { if (!(expr)) { fprintf(stderr, "check failed at line %d: %s\n", __LINE__, #expr); return 1; } } while (0)
#define PANIC_CASE(name, kind, expression) if (!strcmp(argv[1], (name))) { \
    expected_kind = (kind); (void)(expression); \
    fprintf(stderr, "missing panic: %s\n", (name)); return 1; \
}

int main(int argc, char **argv)
{
    /* Each panic runs in its own process: Dong intentionally has no SEH or
       exception unwind metadata, so no host longjmp crosses generated frames. */
    if (argc > 1) {
        PANIC_CASE("divzero", 3, dg_div(1, 0));
        PANIC_CASE("modzero", 3, dg_mod(1, 0));
        PANIC_CASE("idivzero", 3, dg_idiv(1, 0));
        PANIC_CASE("andzero", 3, dg_and(1, 0));
        PANIC_CASE("divoverflow", 5, dg_idiv(INT64_MIN, -1));
        PANIC_CASE("modoverflow", 5, dg_imod(INT64_MIN, -1));
        PANIC_CASE("shift", 4, dg_shl(1, 64));
        PANIC_CASE("signedshift", 4, dg_sar(-1, UINT64_MAX));
#if DEBUG_MODE
        PANIC_CASE("add", 2, dg_add(UINT64_MAX, 1));
        PANIC_CASE("sub", 2, dg_sub(0, 1));
        PANIC_CASE("mul", 2, dg_mul(UINT64_MAX, 2));
        PANIC_CASE("uneg", 2, dg_uneg(1));
        PANIC_CASE("iadd", 2, dg_iadd(INT64_MAX, 1));
        PANIC_CASE("isub", 2, dg_isub(INT64_MIN, 1));
        PANIC_CASE("imul", 2, dg_imul(INT64_MAX, 2));
        PANIC_CASE("ineg", 2, dg_ineg(INT64_MIN));
        /* Overflow of the first argument must precede the second's divide. */
        PANIC_CASE("order", 2, dg_order(UINT64_MAX, 0));
#else
        PANIC_CASE("order", 3, dg_order(UINT64_MAX, 0));
#endif
        fprintf(stderr, "unknown panic case: %s\n", argv[1]);
        return 1;
    }
    CHECK(dg_add(20, 22) == 42);
    CHECK(dg_sub(20, 7) == 13);
    CHECK(dg_mul(9, 8) == 72);
    CHECK(dg_div(100, 7) == 14 && dg_mod(100, 7) == 2);
    CHECK(dg_iadd(-20, 22) == 2 && dg_isub(-20, 22) == -42);
    CHECK(dg_imul(-9, 8) == -72);
    CHECK(dg_idiv(-100, 7) == -14 && dg_imod(-100, 7) == -2);
    CHECK(dg_idiv(100, -7) == -14 && dg_imod(100, -7) == 2);
    CHECK(dg_ineg(-21) == 21 && dg_uneg(0) == 0);
    CHECK(dg_shl(UINT64_C(1), 63) == (UINT64_C(1)<<63));
    CHECK(dg_shr(UINT64_MAX, 63) == 1 && dg_sar(-2, 1) == -1);
    CHECK(dg_litshift(63) == (UINT64_C(1)<<63));
    CHECK(dg_bits(0xfeed, 0xbeef) == (~(UINT64_C(0xfeed)&UINT64_C(0xbeef))^((UINT64_C(0xfeed)|UINT64_C(0xbeef))>>1)));
    CHECK(dg_ult(UINT64_MAX, 0) == 0 && dg_ilt(-1, 0) == 1);
    CHECK(dg_equal(1, 1) == 1 && dg_equal(1, 0) == 0 && dg_not(1) == 0 && dg_not(0) == 1);
    CHECK(dg_and(0, 0) == 0 && dg_or(1, 0) == 1);
    CHECK(dg_and(1, 1) == 1 && dg_or(0, 1) == 1);
    CHECK(dg_factorial(10) == 3628800);
    CHECK(dg_loop(10) == 8 && dg_loop(0) == 0);
    CHECK(dg_zero() == INT64_MIN);
    CHECK(abi_probe() == 1);
#if !DEBUG_MODE
    CHECK(dg_add(UINT64_MAX, 1) == 0);
    CHECK(dg_sub(0, 1) == UINT64_MAX);
    CHECK(dg_mul(UINT64_MAX, 2) == UINT64_MAX-1);
    CHECK(dg_uneg(1) == UINT64_MAX);
    CHECK(dg_iadd(INT64_MAX, 1) == INT64_MIN);
    CHECK(dg_isub(INT64_MIN, 1) == INT64_MAX);
    CHECK(dg_imul(INT64_MAX, 2) == -2);
    CHECK(dg_ineg(INT64_MIN) == INT64_MIN);
#endif
    puts("native scalar and SysV probe passed");
    return 0;
}
