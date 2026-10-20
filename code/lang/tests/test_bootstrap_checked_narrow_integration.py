"""Actual checked64 Dong function -> narrow arithmetic, with independent C math.

CR41 normalizes both inputs before its ADD/SUB: this chain is deliberately NOT a
checked wide-to-narrow conversion. A failed wide operation must skip stage two.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid

from lang.tests import test_bootstrap_nasm_checked_u64_function as wide
from lang.tests import test_bootstrap_nasm_narrow_arithmetic_function as narrow

ROOT = Path(__file__).resolve().parents[2]
MAX = (1 << 64) - 1
TOP = 1 << 63


def cases():
    # wide_op, wide_signed, a, b, narrow_op, width, signed, checked, rhs
    result = []
    for width in (8, 16, 32):
        half = 1 << (width - 1)
        result += [
            (0, 1, half-2, 1, 0, width, 1, 1, 1),
            (0, 1, half-2, 1, 0, width, 1, 0, 1),
            (2, 0, half, 2, 1, width, 0, 1, 1),
            (2, 0, half, 2, 1, width, 0, 0, 1),
            (3, 1, (-half) & MAX, 99, 1, width, 1, 1, 1),
            (1, 1, MAX, 1, 0, width, 1, 1, 0xA5A5A5A500000003),
        ]
    result += [(op, signed, a, b, 0, width, 0, 1, 7)
               for op, signed, a, b, width in (
                   (0, 0, MAX, 1, 8), (1, 0, 0, 1, 16), (2, 0, TOP, 2, 32),
                   (0, 1, TOP-1, 1, 8), (2, 1, TOP, MAX, 16), (3, 1, TOP, 42, 32))]
    return result


CASES = cases()
ORACLE = r'''
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#define ABI __attribute__((sysv_abi))
%DECLARATIONS%
typedef struct { uint64_t op, sign, a, b, narrow_op, width, narrow_sign, checked, rhs; } Case;
static const Case cases[] = {%CASES%};
static void (ABI *const calls[])(uint64_t *) = {%CALLS%};
static const uint64_t preserved[] = {%PRESERVED%};
/* Decode without implementation-defined unsigned-to-signed conversion. int128
   represents every exact signed64 product and every unsigned64 sum/difference.
   Unsigned64 multiplication is separately computed in unsigned int128. */
static __int128 integer(uint64_t bits, unsigned width, int sign) {
    uint64_t mask = width == 64 ? UINT64_MAX : (UINT64_C(1) << width) - 1;
    __int128 value = bits & mask;
    if (sign && (bits & (UINT64_C(1) << (width - 1)))) value -= (__int128)1 << width;
    return value;
}
int main(void) {
    unsigned wide_failures = 0, pair_failures = 0, call_failures = 0, abi_failures = 0;
    unsigned wide_errors = 0, narrow_errors = 0, narrow_calls = 0, successes = 0;
    for (unsigned k = 0; k < sizeof(cases) / sizeof(cases[0]); ++k) {
        const Case *c = &cases[k];
        __int128 a = integer(c->a, 64, c->sign), b = integer(c->b, 64, c->sign);
        __int128 lo = c->sign ? -((__int128)1 << 63) : 0;
        __int128 hi = c->sign ? ((__int128)1 << 63) - 1 : (__int128)UINT64_MAX;
        __int128 math = c->op == 0 ? a + b : c->op == 1 ? a - b : c->op == 3 ? -a : 0;
        int overflow;
        uint64_t wvalue, wstatus;
        if (c->op == 2 && !c->sign) {
            unsigned __int128 product = (unsigned __int128)c->a * c->b;
            overflow = product > UINT64_MAX;
            wvalue = overflow ? 0 : (uint64_t)product;
        } else {
            if (c->op == 2) math = a * b;
            overflow = math < lo || math > hi;
            wvalue = overflow ? 0 : (uint64_t)math;
        }
        wstatus = overflow != 0;
        uint64_t value = 0, status = 1;
        wide_errors += overflow != 0;
        if (!overflow) {
            ++narrow_calls;
            a = integer(wvalue, c->width, c->narrow_sign);
            b = integer(c->rhs, c->width, c->narrow_sign);
            math = c->narrow_op ? a - b : a + b;
            lo = c->narrow_sign ? -((__int128)1 << (c->width - 1)) : 0;
            hi = c->narrow_sign ? ((__int128)1 << (c->width - 1)) - 1 : ((__int128)1 << c->width) - 1;
            int failure = c->checked && (math < lo || math > hi);
            narrow_errors += failure;
            if (!failure) {
                value = (uint64_t)integer((uint64_t)math, c->width, c->narrow_sign);
                status = 0;
            }
        }
        uint64_t o[24] = {0};
        calls[k](o);
        int badabi = o[4] != o[5] || o[4] != o[6] || o[7] || o[23]
                     || o[8] != %CANARY% || o[9] != %CANARY%;
        for (unsigned r = 0; r < 6; ++r)
            if (o[11+r] != preserved[r] || o[17+r] != preserved[r]) badabi = 1;
        wide_failures += o[0] != wvalue || o[1] != wstatus;
        pair_failures += o[2] != value || o[3] != status;
        call_failures += o[10] != (uint64_t)!overflow;
        abi_failures += badabi;
        successes += status == 0;
    }
    printf("{\"cases\":%zu,\"wide_errors\":%u,\"narrow_errors\":%u,\"narrow_calls\":%u,\"successes\":%u,"
           "\"wide_failures\":%u,\"pair_failures\":%u,\"call_failures\":%u,\"abi_failures\":%u}\n",
           sizeof(cases) / sizeof(cases[0]), wide_errors, narrow_errors, narrow_calls, successes,
           wide_failures, pair_failures, call_failures, abi_failures);
    return abi_failures ? 11 : wide_failures || pair_failures || call_failures ? 10 : 0;
}
'''


def c_u64(value):
    return "UINT64_C(0x%x)" % value


class CheckedNarrowIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = []
        cls.before = cls.digests()
        cls.addClassCleanup(cls.cleanup_fixtures)
        for base in (wide.NasmCheckedU64FunctionTests, narrow.FunctionTests):
            fixture = type("Composition" + base.__name__, (base,), {})
            cls.fixtures.append(fixture)
            fixture.setUpClass()
        cls.wide, cls.narrow = (fixture() for fixture in cls.fixtures)
        cls.work = ROOT / "build/test/bootstrap-checked-narrow" / ("run-" + uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        cls.records = []

    @classmethod
    def cleanup_fixtures(cls):
        errors = []
        for fixture in reversed(cls.fixtures):
            try:
                fixture.tearDownClass()
            except Exception as error:
                errors.append(error)
        if errors:
            raise errors[0]

    @staticmethod
    def digests():
        paths = {wide.SOURCE, wide.DOC, narrow.SOURCE, narrow.DOC,
                 Path(wide.__file__), Path(narrow.__file__), Path(__file__),
                 *wide.DEPENDENCIES, *narrow.DEPENDENCIES, *(ROOT / "lang/dongc").glob("*.py")}
        return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls, "work"):
            return
        after = cls.digests()
        result = {"inputs_before": cls.before, "inputs_after": after, "stable": cls.before == after,
                  "records": cls.records, "native_format": cls.wide.native,
                  "selfhost_complete": False, "OS_VM_built": False,
                  "artifacts": {str(p.relative_to(cls.work)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in cls.work.rglob("*") if p.is_file()}}
        (cls.work / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        if cls.before != after:
            raise AssertionError("compiler, component or integration source changed during verification")

    def generated_functions(self, mode, vectors, variant, executable):
        ws, ns = [], []
        for k, c in enumerate(vectors):
            op, signed, a, b, nop, width, nsign, checked, rhs = c
            ws.append((b"composition", ("wide%d" % k).encode(), op, bool(signed), 2*k, a, b))
            ns.append(dict(names=[b"composition", ("narrow%d" % k).encode()],
                           q=[nop, width, nsign, checked, 2*k+1], args=[]))
        label = "composition-" + mode + "-" + variant
        wt = self.wide.generate(self.wide.executables[mode], ws, label)
        nt = self.narrow.generate(executable, ns, label, exact=variant != "bad-narrow-check")
        return b"".join(wt + nt).decode("ascii")

    def bridge(self, vectors, variant):
        lines = ["bits 64", "section .data", "align 8", "observation: dq 0", "host_anchor: dq 0", "section .text"]
        for k, c in enumerate(vectors):
            a, b, rhs = c[2], c[3], c[8]
            lines += ["global compose%d" % k, "compose%d:" % k]
            lines += ["push " + r for r in wide.CALLER]
            lines += ["sub rsp, 8", "mov [rel observation], rdi", "mov [rel host_anchor], rsp",
                      "mov r10, rdi", "mov [r10+32], rsp", "mov rax, rsp", "and rax, 15",
                      "mov [r10+56], rax", "mov rax, 0x%x" % wide.CANARY, "mov [rsp], rax"]
            lines += ["mov %s, 0x%x" % pair for pair in wide.CALLER.items()]
            lines += ["mov rdi, 0x%x" % a, "mov rsi, 0x%x" % b,
                      "call " + wide.symbol(b"composition", ("wide%d" % k).encode()),
                      "mov r10, [rel observation]", "mov [r10], rax", "mov [r10+8], rdx", "mov [r10+40], rsp"]
            lines += ["mov [r10+%d], %s" % (88+8*j, r) for j, r in enumerate(wide.CALLER)]
            lines += ["mov r11, [rel host_anchor]", "mov r11, [r11]", "mov [r10+64], r11"]
            if variant != "bad-propagation":
                lines += ["test rdx, rdx", "jnz .done"]
            lines += ["mov rdi, rax", "mov rsi, 0x%x" % rhs, "inc qword [r10+80]",
                      "mov r11, rsp", "and r11, 15", "mov [r10+184], r11",
                      "call " + wide.symbol(b"composition", ("narrow%d" % k).encode()), ".done:",
                      "mov r10, [rel observation]", "mov [r10+16], rax", "mov [r10+24], rdx", "mov [r10+48], rsp"]
            lines += ["mov [r10+%d], %s" % (136+8*j, r) for j, r in enumerate(wide.CALLER)]
            lines += ["mov r11, [rel host_anchor]", "mov r11, [r11]", "mov [r10+72], r11",
                      "mov rsp, [rel host_anchor]", "add rsp, 8"]
            lines += ["pop " + r for r in reversed(wide.CALLER)] + ["ret"]
        return "\n".join(lines) + "\n"

    def oracle_source(self, vectors):
        return (ORACLE.replace("%DECLARATIONS%", "\n".join(
                    "extern void ABI compose%d(uint64_t *);" % k for k in range(len(vectors))))
                .replace("%CASES%", ",\n".join("{" + ",".join(map(c_u64, c)) + "}" for c in vectors))
                .replace("%CALLS%", ",".join("compose%d" % k for k in range(len(vectors))))
                .replace("%PRESERVED%", ",".join(map(c_u64, wide.CALLER.values())))
                .replace("%CANARY%", c_u64(wide.CANARY)))

    def command(self, command, label):
        run = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=180)
        (self.work / (label + ".log")).write_text(run.stdout + run.stderr)
        self.assertEqual(run.returncode, 0, (label, run.stdout, run.stderr))

    def run_chain(self, mode, vectors, variant, executable, expected):
        label = mode + "-" + variant
        asm, oracle = self.work / (label + ".asm"), self.work / (label + ".c")
        asm.write_text(self.bridge(vectors, variant) + self.generated_functions(mode, vectors, variant, executable), encoding="ascii")
        oracle.write_text(self.oracle_source(vectors), encoding="ascii")
        for fmt in ("elf64", "win64"):
            self.command([self.wide.nasm, "-f", fmt, *wide.nasm_flags(self.wide.nasm),
                          "-o", self.work / (label + "." + fmt + ".o"), asm], label + "-" + fmt)
        exe = self.work / (label + (".exe" if os.name == "nt" else ""))
        self.command([self.wide.cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                      oracle, self.work / (label + "." + self.wide.native + ".o"), "-o", exe], label + "-link")
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
        (self.work / (label + ".stdout")).write_text(run.stdout)
        (self.work / (label + ".stderr")).write_text(run.stderr)
        self.assertEqual(run.returncode, 0 if variant == "good" else 10, (label, run.stderr))
        record = json.loads(run.stdout)
        self.assertEqual(record, expected, label)
        self.records.append(dict(mode=mode, variant=variant, normal_exit=True, observations=record))

    def test_real_checked_to_narrow_and_error_propagation(self):
        self.assertEqual(len(CASES), 24)
        zeros = dict(wide_failures=0, pair_failures=0, call_failures=0, abi_failures=0)
        source = narrow.SOURCE.read_text(encoding="utf-8")
        old = "narrow.emit((*c).width,(*c).signed,(*c).error_block,buffer,&n)"
        new = "cast.emit(0,0,(*c).width,(*c).signed,buffer,&n)"
        self.assertEqual(source.count(old), 1)
        mutants = self.narrow.build_all("composition-bad-narrow-check", source.replace(old, new))
        overflow = [CASES[6*w + i] for w in range(3) for i in (0, 2, 4)]
        for mode in ("debug", "release"):
            with self.subTest(mode=mode):
                self.run_chain(mode, CASES, "good", self.narrow.executables[mode],
                               dict(zeros, cases=24, wide_errors=6, narrow_errors=9, narrow_calls=18, successes=9))
                self.run_chain(mode, overflow, "bad-narrow-check", mutants[mode],
                               dict(zeros, cases=9, wide_errors=0, narrow_errors=9, narrow_calls=9, successes=0, pair_failures=9))
                self.run_chain(mode, CASES[18:], "bad-propagation", self.narrow.executables[mode],
                               dict(zeros, cases=6, wide_errors=6, narrow_errors=0, narrow_calls=0, successes=0,
                                    pair_failures=6, call_failures=6))


if __name__ == "__main__":
    unittest.main()
