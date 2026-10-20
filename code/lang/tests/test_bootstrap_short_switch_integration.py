"""Real short-circuit function -> observable thunks -> real i64 switch function.

The thunks only supply selectors and record calls/results; all truth conversion,
short-circuit control flow, switch dispatch and return values are emitted by Dong.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid

from lang.tests import test_bootstrap_nasm_short_circuit_function as short
from lang.tests import test_bootstrap_nasm_i64_switch_function as switch

ROOT = Path(__file__).resolve().parents[2]
MAX = (1 << 64) - 1
TOP = 1 << 63
# Deliberately unsorted, including equal low32 bits and high-bit-only truth.
ARMS = ((-TOP, 0), (TOP-1, 0x100), (-1, MAX), (0, 0),
        (0x100000001, TOP), (-0x100000001, 0x10000))
DEFAULT = 0x100000000
CASES = [(op, selector, 0 if k % 2 == 0 else TOP-1)
         for op in (0, 1) for k, (selector, _) in enumerate(ARMS)]
CASES += [(op, 99, rhs) for op in (0, 1) for rhs in (0, 99)]
ORACLE = r'''
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#define ABI __attribute__((sysv_abi))
%DECLARATIONS%
typedef struct { uint64_t operation, left, right; } Case;
static const Case cases[] = {%CASES%};
static void (ABI *const calls[])(uint64_t *) = {%CALLS%};
static const uint64_t selectors[] = {%SELECTORS%};
static const uint64_t values[] = {%VALUES%};
static const uint64_t preserved[] = {%PRESERVED%};
static uint64_t dispatch(uint64_t selector) {
    for (unsigned j = 0; j < sizeof(selectors) / sizeof(selectors[0]); ++j)
        if (selector == selectors[j]) return values[j];
    return %DEFAULT%;
}
int main(void) {
    unsigned bool_failures = 0, trace_failures = 0, value_failures = 0, abi_failures = 0;
    unsigned right_calls = 0, true_results = 0;
    for (unsigned k = 0; k < sizeof(cases) / sizeof(cases[0]); ++k) {
        const Case *c = &cases[k];
        uint64_t left = dispatch(c->left), right = dispatch(c->right);
        int eval = c->operation ? left == 0 : left != 0;
        uint64_t want = (eval ? right : left) != 0;
        uint64_t o[48] = {0};
        calls[k](o);
        int badabi = o[1] != o[2] || o[3] || o[4] != %CANARY%;
        for (unsigned r = 0; r < 6; ++r) if (o[10+r] != preserved[r]) badabi = 1;
        for (unsigned side = 0; side < 2; ++side) {
            unsigned base = 16 + 16 * side;
            if (side == 0 || o[5] == 2) {
                if (o[base] != o[base+1] || o[base+2] || o[base+3] != %CANARY%) badabi = 1;
                for (unsigned r = 0; r < 6; ++r)
                    if (o[base+4+r] != o[base+10+r]) badabi = 1;
            } else {
                for (unsigned j = 0; j < 16; ++j) if (o[base+j]) badabi = 1;
            }
        }
        bool_failures += o[0] != want;
        trace_failures += o[5] != (uint64_t)(1+eval) || o[6] != 1 || o[7] != (uint64_t)(eval ? 2 : 0);
        value_failures += o[8] != left || o[9] != (eval ? right : 0);
        abi_failures += badabi;
        right_calls += eval;
        true_results += want != 0;
    }
    printf("{\"cases\":%zu,\"right_calls\":%u,\"true_results\":%u,\"bool_failures\":%u,"
           "\"trace_failures\":%u,\"value_failures\":%u,\"abi_failures\":%u}\n",
           sizeof(cases) / sizeof(cases[0]), right_calls, true_results,
           bool_failures, trace_failures, value_failures, abi_failures);
    return abi_failures ? 11 : bool_failures || trace_failures || value_failures ? 10 : 0;
}
'''


def c_u64(value):
    return "UINT64_C(0x%x)" % (value & MAX)


class ShortSwitchIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = []
        cls.before = cls.digests()
        cls.addClassCleanup(cls.cleanup_fixtures)
        for base in (short.FunctionTests, switch.NasmI64SwitchFunctionTests):
            fixture = type("Composition" + base.__name__, (base,), {})
            cls.fixtures.append(fixture)
            fixture.setUpClass()
        cls.short, cls.switch = (fixture() for fixture in cls.fixtures)
        cls.work = ROOT / "build/test/bootstrap-short-switch" / ("run-" + uuid.uuid4().hex[:12])
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
        paths = {short.SOURCE, short.DOC, switch.SOURCE, switch.DOC,
                 Path(short.__file__), Path(switch.__file__), Path(__file__),
                 *short.DEPENDENCIES, *switch.DEPENDENCIES, *(ROOT / "lang/dongc").glob("*.py")}
        return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls, "work"):
            return
        after = cls.digests()
        result = {"inputs_before": cls.before, "inputs_after": after, "stable": cls.before == after,
                  "records": cls.records, "native_format": cls.short.native,
                  "selfhost_complete": False, "OS_VM_built": False,
                  "artifacts": {str(p.relative_to(cls.work)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in cls.work.rglob("*") if p.is_file()}}
        (cls.work / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        if cls.before != after:
            raise AssertionError("compiler, component or integration source changed during verification")

    def generated_functions(self, mode, vectors, variant, short_exe, switch_exe):
        ss = []
        for k, (op, _, _) in enumerate(vectors):
            names = [b"composition", ("short%d" % k).encode(), b"thunk", ("left%d" % k).encode(),
                     b"thunk", ("right%d" % k).encode()]
            ss.append(dict(names=names, q=[op, 1000+2*k, 1001+2*k], args=[]))
        fn = (b"composition", b"dispatch", tuple((s, 100+j, value) for j, (s, value) in enumerate(ARMS)), 106, DEFAULT)
        label = "composition-" + mode + "-" + variant
        st = self.short.generate(short_exe, ss, label, exact=variant not in ("bad-short-circuit", "bad-call-order"))
        wt = self.switch.generate(switch_exe, [fn], label, exact=variant != "bad-switch-association")
        return b"".join(st + wt).decode("ascii")

    def bridge(self, vectors):
        lines = ["bits 64", "section .data", "align 8", "observation: dq 0",
                 "host_anchor: dq 0", "thunk_anchor: dq 0", "section .text"]
        for k, (_, left, right) in enumerate(vectors):
            lines += ["global compose%d" % k, "compose%d:" % k]
            lines += ["push " + r for r in short.CALLER]
            lines += ["sub rsp, 8", "mov [rel observation], rdi", "mov [rel host_anchor], rsp",
                      "mov r10, rdi", "mov [r10+8], rsp", "mov rax, rsp", "and rax, 15",
                      "mov [r10+24], rax", "mov rax, 0x%x" % short.CANARY, "mov [rsp], rax"]
            lines += ["mov %s, 0x%x" % pair for pair in short.CALLER.items()]
            lines += ["call " + short.symbol(b"composition", ("short%d" % k).encode()),
                      "mov r10, [rel observation]", "mov [r10], rax", "mov [r10+16], rsp"]
            lines += ["mov [r10+%d], %s" % (80+8*j, r) for j, r in enumerate(short.CALLER)]
            lines += ["mov r11, [rel host_anchor]", "mov r11, [r11]", "mov [r10+32], r11",
                      "mov rsp, [rel host_anchor]", "add rsp, 8"]
            lines += ["pop " + r for r in reversed(short.CALLER)] + ["ret"]
            for side, selector in enumerate((left, right)):
                base = 8 * (16 + 16*side)
                item = (("left" if side == 0 else "right") + str(k)).encode()
                lines += [short.symbol(b"thunk", item)+":", "sub rsp, 8", "mov [rel thunk_anchor], rsp",
                          "mov r10, [rel observation]", "mov r11, [r10+40]", "inc qword [r10+40]",
                          "and r11, 1", "mov qword [r10+r11*8+48], %d" % (side+1),
                          "mov [r10+%d], rsp" % base, "mov r11, rsp", "and r11, 15",
                          "mov [r10+%d], r11" % (base+16), "mov r11, 0x%x" % short.CANARY,
                          "mov [rsp], r11"]
                lines += ["mov [r10+%d], %s" % (base+32+8*j, r) for j, r in enumerate(short.CALLER)]
                lines += ["mov rdi, 0x%x" % (selector & MAX),
                          "call " + short.symbol(b"composition", b"dispatch"),
                          "mov r10, [rel observation]", "mov [r10+%d], rax" % (64+8*side),
                          "mov [r10+%d], rsp" % (base+8)]
                lines += ["mov [r10+%d], %s" % (base+80+8*j, r) for j, r in enumerate(short.CALLER)]
                lines += ["mov r11, [rel thunk_anchor]", "mov r11, [r11]", "mov [r10+%d], r11" % (base+24)]
                # Restore only after observing actual switch state, so a broken
                # callee cannot hide corruption or break the surrounding host.
                lines += ["mov %s, [r10+%d]" % (r, base+32+8*j) for j, r in enumerate(short.CALLER)]
                lines += ["mov rsp, [rel thunk_anchor]", "add rsp, 8"]
                lines += ["mov %s, %d" % (r, 31+j) for j, r in enumerate(("rdi", "rsi", "rcx", "rdx", "r8", "r9", "r10", "r11"))]
                lines += ["stc", "ret"]
        return "\n".join(lines) + "\n"

    def oracle_source(self, vectors):
        return (ORACLE.replace("%DECLARATIONS%", "\n".join(
                    "extern void ABI compose%d(uint64_t *);" % k for k in range(len(vectors))))
                .replace("%CASES%", ",\n".join("{" + ",".join(map(c_u64, c)) + "}" for c in vectors))
                .replace("%CALLS%", ",".join("compose%d" % k for k in range(len(vectors))))
                .replace("%SELECTORS%", ",".join(c_u64(s) for s, _ in ARMS))
                .replace("%VALUES%", ",".join(c_u64(v) for _, v in ARMS))
                .replace("%DEFAULT%", c_u64(DEFAULT))
                .replace("%PRESERVED%", ",".join(map(c_u64, short.CALLER.values())))
                .replace("%CANARY%", c_u64(short.CANARY)))

    def command(self, command, label):
        run = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=180)
        (self.work / (label + ".log")).write_text(run.stdout + run.stderr)
        self.assertEqual(run.returncode, 0, (label, run.stdout, run.stderr))

    def run_chain(self, mode, vectors, variant, short_exe, switch_exe, expected):
        label = mode + "-" + variant
        asm, oracle = self.work / (label + ".asm"), self.work / (label + ".c")
        asm.write_text(self.bridge(vectors) + self.generated_functions(mode, vectors, variant, short_exe, switch_exe), encoding="ascii")
        oracle.write_text(self.oracle_source(vectors), encoding="ascii")
        for fmt in ("elf64", "win64"):
            self.command([self.short.nasm, "-f", fmt, *short.nasm_flags(self.short.nasm),
                          "-o", self.work / (label + "." + fmt + ".o"), asm], label + "-" + fmt)
        exe = self.work / (label + (".exe" if os.name == "nt" else ""))
        self.command([self.short.cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                      oracle, self.work / (label + "." + self.short.native + ".o"), "-o", exe], label + "-link")
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
        (self.work / (label + ".stdout")).write_text(run.stdout)
        (self.work / (label + ".stderr")).write_text(run.stderr)
        self.assertEqual(run.returncode, 0 if variant == "good" else 10, (label, run.stderr))
        record = json.loads(run.stdout)
        self.assertEqual(record, expected, label)
        self.records.append(dict(mode=mode, variant=variant, normal_exit=True, observations=record))

    def test_real_short_circuit_switch_results_and_controls(self):
        self.assertEqual(len(CASES), 16)
        zeros = dict(bool_failures=0, trace_failures=0, value_failures=0, abi_failures=0)
        source = short.SOURCE.read_text(encoding="utf-8")
        old = "if (*c).operation==1{condition=0;}"
        self.assertEqual(source.count(old), 1)
        short_mutants = self.short.build_all("composition-bad-short-circuit", source.replace(old, "if (*c).operation==0{condition=0;}"))
        left = "inv.emit((*c).left_module,(*c).left_item"
        right = "inv.emit((*c).right_module,(*c).right_item"
        self.assertEqual(source.count(left), 1)
        self.assertEqual(source.count(right), 1)
        swapped = source.replace(left, "SWAPPED_CALL_TARGET").replace(right, left).replace("SWAPPED_CALL_TARGET", right)
        order_mutants = self.short.build_all("composition-bad-call-order", swapped)
        source = switch.SOURCE.read_text(encoding="utf-8")
        old = "return_block(arms[i].block,arms[i].result,"
        self.assertEqual(source.count(old), 1)
        switch_mutants = self.switch.build_all("composition-bad-switch-association", source.replace(old, "return_block(arms[i].block,arms[(i+1)%arms.len].result,", 1))
        for mode in ("debug", "release"):
            with self.subTest(mode=mode):
                self.run_chain(mode, CASES, "good", self.short.executables[mode], self.switch.executables[mode],
                               dict(zeros, cases=16, right_calls=8, true_results=10))
                self.run_chain(mode, CASES, "bad-short-circuit", short_mutants[mode], self.switch.executables[mode],
                               dict(zeros, cases=16, right_calls=8, true_results=10,
                                    bool_failures=8, trace_failures=16, value_failures=8))
                self.run_chain(mode, [CASES[i] for i in (1, 5, 13)], "bad-call-order", order_mutants[mode], self.switch.executables[mode],
                               dict(zeros, cases=3, right_calls=3, true_results=3, trace_failures=3))
                self.run_chain(mode, CASES[6:12], "bad-switch-association", self.short.executables[mode], switch_mutants[mode],
                               dict(zeros, cases=6, right_calls=2, true_results=5,
                                    bool_failures=1, trace_failures=4, value_failures=6))


if __name__ == "__main__":
    unittest.main()
