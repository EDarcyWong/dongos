"""Real Dong slice construction -> checked element access, with independent C oracle.

A successful view's returned pointer AND length feed indexed access. Failed views
are translated to {0, 1} without invoking access. This is test-only ABI wiring,
not a new production compiler lowering pass or a replacement for either emitter.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid

from lang.tests import test_bootstrap_nasm_slice_view_function as view
from lang.tests import test_bootstrap_nasm_indexed_memory_function as memory

ROOT = Path(__file__).resolve().parents[2]
MAX = (1 << 64) - 1
VALUE = 0xFEDCBA9876543210


def case(width=8, signed=False, operation=0, base=0, length=8, lo=1, hi=3, index=0):
    # base: 0 = real guarded allocation, 1 = NULL, 2 = forged endpoint (never accessed).
    return (width, int(signed), operation, base, length, lo, hi, index, VALUE)


def cases():
    result = [case(w, s, index=int(s)) for w in (8, 16, 32, 64)
              for s in ((False, True) if w != 64 else (False,))]
    result += [case(w, operation=1, index=1) for w in (8, 16, 32, 64)]
    result += [case(w, operation=1, index=2) for w in (8, 16, 32, 64)]
    result += [case(w, operation=1, lo=4, hi=4) for w in (8, 64)]
    result += [case(base=1, length=0, lo=0, hi=0)]
    result += [case(lo=3, hi=2), case(hi=9), case(base=1, length=1, lo=0, hi=1),
               case(64, length=1 << 61, lo=0, hi=0),
               case(64, base=2, length=1, lo=0, hi=0)]
    result += [case(32, True, index=2)]
    return result


CASES = cases()
ORACLE = r'''
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
%DECLARATIONS%
typedef struct { uint64_t width, sign, operation, base, length, lo, hi, index, value; } Case;
static const Case cases[] = {%CASES%};
static void (ABI *const calls[])(uint64_t *, uint8_t *) = {%CALLS%};
static const uint64_t preserved[] = {%PRESERVED%};
int main(void) {
    unsigned view_failures = 0, pair_failures = 0, memory_failures = 0;
    unsigned call_failures = 0, abi_failures = 0, errors = 0, accesses = 0, successes = 0;
    for (unsigned k = 0; k < sizeof(cases) / sizeof(cases[0]); ++k) {
        const Case *c = &cases[k];
        _Alignas(16) uint8_t actual[320], expected[320];
        for (unsigned j = 0; j < sizeof(actual); ++j) actual[j] = 0x80u | ((j * 37u) & 0x7fu);
        memcpy(expected, actual, sizeof(actual));
        uint64_t o[24] = {0}, stride = c->width / 8;
        uint64_t base = c->base == 1 ? 0 : c->base == 2 ? UINT64_MAX - 7 : (uintptr_t)(actual + 32);
        int valid = c->lo <= c->hi && c->hi <= c->length && (base || !c->length);
        valid = valid && c->length <= UINT64_MAX / stride;
        if (valid) valid = c->length * stride <= UINT64_MAX - base;
        uint64_t ptr = valid ? base + c->lo * stride : 0;
        uint64_t count = valid ? c->hi - c->lo : UINT64_MAX;
        uint64_t value = 0, status = 1;
        if (valid && c->index < count) {
            size_t offset = 32 + (c->lo + c->index) * stride;
            status = 0;
            if (c->operation) {
                for (unsigned b = 0; b < stride; ++b) expected[offset + b] = (uint8_t)(c->value >> (8 * b));
            }
            for (unsigned b = 0; b < stride; ++b) value |= (uint64_t)expected[offset + b] << (8 * b);
            if (c->sign && c->width < 64 && (value & (UINT64_C(1) << (c->width - 1))))
                value |= UINT64_MAX << c->width;
        }
        calls[k](o, actual + 32);
        int badabi = o[4] != o[5] || o[4] != o[6] || o[7] || o[23]
                     || o[8] != %CANARY% || o[9] != %CANARY%;
        for (unsigned r = 0; r < 6; ++r)
            if (o[11 + r] != preserved[r] || o[17 + r] != preserved[r]) badabi = 1;
        view_failures += o[0] != ptr || o[1] != count;
        pair_failures += o[2] != value || o[3] != status;
        memory_failures += memcmp(actual, expected, sizeof(actual)) != 0;
        call_failures += o[10] != (uint64_t)valid;
        abi_failures += badabi;
        errors += !valid;
        accesses += valid;
        successes += status == 0;
    }
    printf("{\"cases\":%zu,\"view_errors\":%u,\"access_calls\":%u,\"successes\":%u,"
           "\"view_failures\":%u,\"pair_failures\":%u,\"memory_failures\":%u,"
           "\"call_failures\":%u,\"abi_failures\":%u}\n",
           sizeof(cases) / sizeof(cases[0]), errors, accesses, successes,
           view_failures, pair_failures, memory_failures, call_failures, abi_failures);
    return abi_failures ? 11 : view_failures || pair_failures || memory_failures || call_failures ? 10 : 0;
}
'''


def c_u64(value):
    return "UINT64_C(0x%x)" % value


class SliceMemoryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = []
        cls.before = cls.digests()
        cls.addClassCleanup(cls.cleanup_fixtures)
        for base in (view.FunctionTests, memory.NasmIndexedMemoryFunctionTests):
            fixture = type("Composition" + base.__name__, (base,), {})
            cls.fixtures.append(fixture)
            fixture.setUpClass()
        cls.view, cls.memory = (fixture() for fixture in cls.fixtures)
        cls.work = ROOT / "build/test/bootstrap-slice-memory" / ("run-" + uuid.uuid4().hex[:12])
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
        paths = {view.SOURCE, view.DOC, memory.SOURCE, memory.DOC,
                 Path(view.__file__), Path(memory.__file__), Path(__file__),
                 *view.DEPENDENCIES, *memory.DEPENDENCIES, *(ROOT / "lang/dongc").glob("*.py")}
        return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls, "work"):
            return
        after = cls.digests()
        result = {"inputs_before": cls.before, "inputs_after": after, "stable": cls.before == after,
                  "records": cls.records, "native_format": cls.view.native,
                  "selfhost_complete": False, "OS_VM_built": False,
                  "artifacts": {str(p.relative_to(cls.work)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in cls.work.rglob("*") if p.is_file()}}
        (cls.work / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        if cls.before != after:
            raise AssertionError("compiler, component or integration source changed during verification")

    def generated_functions(self, mode, vectors, variant, executable):
        vs, ms = [], []
        for k, c in enumerate(vectors):
            width, signed, operation = c[:3]
            vs.append(dict(names=[b"composition", ("view%d" % k).encode()], q=[width // 8, 2*k], args=[]))
            ms.append((b"composition", ("access%d" % k).encode(), operation, width, bool(signed), 2*k+1))
        label = "composition-" + mode + "-" + variant
        vt = self.view.generate(executable, vs, label, exact=variant != "bad-view-length")
        mt = self.memory.generate(self.memory.executables[mode], ms, label)
        return b"".join(vt + mt).decode("ascii")

    def bridge(self, vectors, variant):
        # All observations are reached through an independent static pointer;
        # capture both calls' state before restoring the host stack/registers.
        lines = ["bits 64", "section .data", "align 8", "observation: dq 0",
                 "host_anchor: dq 0", "source_base: dq 0", "section .text"]
        for k, c in enumerate(vectors):
            _, _, _, base, length, lo, hi, index, value = c
            lines += ["global compose%d" % k, "compose%d:" % k]
            lines += ["push " + r for r in view.CALLER]
            lines += ["sub rsp, 8", "mov [rel observation], rdi", "mov [rel source_base], rsi",
                      "mov [rel host_anchor], rsp", "mov r10, rdi", "mov [r10+32], rsp",
                      "mov rax, rsp", "and rax, 15", "mov [r10+56], rax",
                      "mov rax, 0x%x" % view.CANARY, "mov [rsp], rax"]
            lines += ["mov %s, 0x%x" % pair for pair in view.CALLER.items()]
            lines += ["mov rdi, [rel source_base]" if base == 0 else "mov rdi, 0x%x" % (0 if base == 1 else MAX-7),
                      "mov rsi, 0x%x" % length, "mov rdx, 0x%x" % lo, "mov rcx, 0x%x" % hi,
                      "call " + view.symbol(b"composition", ("view%d" % k).encode()),
                      "mov r10, [rel observation]", "mov [r10], rax", "mov [r10+8], rdx",
                      "mov [r10+40], rsp"]
            lines += ["mov [r10+%d], %s" % (88 + 8*j, r) for j, r in enumerate(view.CALLER)]
            lines += ["mov r11, [rel host_anchor]", "mov r11, [r11]", "mov [r10+64], r11",
                      "cmp rdx, -1", "je .view_failure", "mov rdi, rax", "mov rsi, rdx",
                      "mov rdx, 0x%x" % index, "mov rcx, 0x%x" % value,
                      "inc qword [r10+80]", "mov r11, rsp", "and r11, 15", "mov [r10+184], r11",
                      "call " + view.symbol(b"composition", ("access%d" % k).encode()),
                      "jmp .done", ".view_failure:", "xor eax, eax",
                      "mov edx, %d" % (0 if variant == "bad-error-status" else 1), ".done:",
                      "mov r10, [rel observation]", "mov [r10+16], rax", "mov [r10+24], rdx",
                      "mov [r10+48], rsp"]
            lines += ["mov [r10+%d], %s" % (136 + 8*j, r) for j, r in enumerate(view.CALLER)]
            lines += ["mov r11, [rel host_anchor]", "mov r11, [r11]", "mov [r10+72], r11",
                      "mov rsp, [rel host_anchor]", "add rsp, 8"]
            lines += ["pop " + r for r in reversed(view.CALLER)] + ["ret"]
        return "\n".join(lines) + "\n"

    def oracle_source(self, vectors):
        return (ORACLE.replace("%DECLARATIONS%", "\n".join(
                    "extern void ABI compose%d(uint64_t *, uint8_t *);" % k for k in range(len(vectors))))
                .replace("%CASES%", ",\n".join("{" + ",".join(map(c_u64, c)) + "}" for c in vectors))
                .replace("%CALLS%", ",".join("compose%d" % k for k in range(len(vectors))))
                .replace("%PRESERVED%", ",".join(map(c_u64, view.CALLER.values())))
                .replace("%CANARY%", c_u64(view.CANARY)))

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
            self.command([self.view.nasm, "-f", fmt, *view.nasm_flags(self.view.nasm),
                          "-o", self.work / (label + "." + fmt + ".o"), asm], label + "-" + fmt)
        exe = self.work / (label + (".exe" if os.name == "nt" else ""))
        self.command([self.view.cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                      oracle, self.work / (label + "." + self.view.native + ".o"), "-o", exe], label + "-link")
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
        (self.work / (label + ".stdout")).write_text(run.stdout)
        (self.work / (label + ".stderr")).write_text(run.stderr)
        self.assertEqual(run.returncode, 0 if variant == "good" else 10, (label, run.stderr))
        record = json.loads(run.stdout)
        self.assertEqual(record, expected, label)
        self.records.append(dict(mode=mode, variant=variant, normal_exit=True, observations=record))

    def test_real_subview_access_and_safe_negative_controls(self):
        self.assertEqual(len(CASES), 24)
        zeros = dict(view_failures=0, pair_failures=0, memory_failures=0, call_failures=0, abi_failures=0)
        source = view.SOURCE.read_text(encoding="utf-8")
        old = "bin.emit(1,0,1,slice_from_raw_parts(&buffer[at],16),&n)"
        self.assertEqual(source.count(old), 1)
        # Mutation exists only in an isolated copy, and is executed only against
        # four safe backing arrays. Bad length allows writes inside the parent
        # allocation but outside the intended subview: no crash is the oracle.
        mutants = self.view.build_all("composition-bad-view-length", source.replace(old, old.replace("(1,", "(0,", 1)))
        for mode in ("debug", "release"):
            with self.subTest(mode=mode):
                self.run_chain(mode, CASES, "good", self.view.executables[mode],
                               dict(zeros, cases=24, view_errors=5, access_calls=19, successes=11))
                self.run_chain(mode, CASES[11:15], "bad-view-length", mutants[mode],
                               dict(zeros, cases=4, view_errors=0, access_calls=4, successes=0,
                                    view_failures=4, pair_failures=4, memory_failures=4))
                self.run_chain(mode, CASES[18:23], "bad-error-status", self.view.executables[mode],
                               dict(zeros, cases=5, view_errors=5, access_calls=0, successes=0, pair_failures=5))


if __name__ == "__main__":
    unittest.main()
