"""Actual Dong emitters -> forwarded arguments -> generated select -> SysV return.

The component fixtures compile the real Dong emitters, never Python templates of
the functions under test. A separate C oracle checks the composed call chain.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid

from lang.tests import test_bootstrap_nasm_u64_select_function as select
from lang.tests import test_bootstrap_nasm_u64_forward_function as forward


ROOT = Path(__file__).resolve().parents[2]
INVERSE = (1, 0, 5, 4, 3, 2, 9, 8, 7, 6)
REGISTERS = ("rdi", "rsi", "rdx", "rcx", "r8", "r9")


def cases():
    result = []
    for index, vector in enumerate(select.VECTORS):
        condition, lhs, rhs, yes, no = vector[2], *vector[5:]
        mapping = (5, 2, 4, 1) if index % 2 == 0 else (2, 5, 1, 4)
        arguments = [0xDEADBEEF00000000 + index * 16 + n for n in range(6)]
        for position, value in zip(mapping, (lhs, rhs, yes, no)):
            arguments[position] = value
        result.append((condition, mapping, tuple(arguments)))
    return result


CASES = cases()
ORACLE = r'''
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#define ABI __attribute__((sysv_abi))
%DECLARATIONS%
typedef struct {
    uint64_t condition, mapping[4], arguments[6];
} Case;
static const Case cases[] = {%CASES%};
static void (ABI *const calls[])(uint64_t *) = {%CALLS%};
static const uint64_t preserved[] = {%PRESERVED%};

static int holds(uint64_t condition, uint64_t lhs, uint64_t rhs) {
    uint64_t sl = lhs ^ UINT64_C(0x8000000000000000);
    uint64_t sr = rhs ^ UINT64_C(0x8000000000000000);
    switch (condition) {
    case 0: return lhs == rhs;
    case 1: return lhs != rhs;
    case 2: return lhs < rhs;
    case 3: return lhs <= rhs;
    case 4: return lhs > rhs;
    case 5: return lhs >= rhs;
    case 6: return sl < sr;
    case 7: return sl <= sr;
    case 8: return sl > sr;
    case 9: return sl >= sr;
    default: return -1;
    }
}

int main(void) {
    unsigned numeric_failures = 0, abi_failures = 0, yes_count = 0, no_count = 0;
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        const Case *c = &cases[i];
        uint64_t observation[11] = {0};
        uint64_t lhs = c->arguments[c->mapping[0]];
        uint64_t rhs = c->arguments[c->mapping[1]];
        int yes = holds(c->condition, lhs, rhs);
        uint64_t want = c->arguments[c->mapping[yes ? 2 : 3]];
        calls[i](observation);
        yes_count += yes != 0;
        no_count += yes == 0;
        if (observation[0] != want) {
            fprintf(stderr, "numeric mismatch %u: got=%" PRIu64 " want=%" PRIu64 "\n",
                    i, observation[0], want);
            ++numeric_failures;
        }
        if (observation[1] != observation[2] || observation[9] != %CANARY% || observation[10])
            ++abi_failures;
        for (unsigned r = 0; r < 6; ++r)
            if (observation[3 + r] != preserved[r]) ++abi_failures;
    }
    printf("{\"cases\":%zu,\"yes\":%u,\"no\":%u,\"numeric_failures\":%u,\"abi_failures\":%u}\n",
           sizeof(cases) / sizeof(cases[0]), yes_count, no_count, numeric_failures, abi_failures);
    return abi_failures ? 11 : numeric_failures ? 10 : 0;
}
'''


def c_u64(value):
    return "UINT64_C(0x%x)" % value


class SelectForwardIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = []
        cls.before = cls.digests()
        # Separate fixture classes keep the component suites' class state intact.
        # Cleanup is registered before setup, including partial setup failures.
        cls.addClassCleanup(cls.cleanup_fixtures)
        for base in (select.NasmU64SelectFunctionTests, forward.NasmU64ForwardFunctionTests):
            fixture = type("Composition" + base.__name__, (base,), {})
            cls.fixtures.append(fixture)
            fixture.setUpClass()
        cls.select, cls.forward = (fixture() for fixture in cls.fixtures)
        cls.work = ROOT / "build/test/bootstrap-select-forward" / ("run-" + uuid.uuid4().hex[:12])
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
        paths = {select.SOURCE, select.DOC, forward.SOURCE, forward.DOC,
                 Path(select.__file__), Path(forward.__file__), Path(__file__),
                 *select.DEPENDENCIES, *forward.DEPENDENCIES,
                 *(ROOT / "lang/dongc").glob("*.py")}
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(paths)}

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls, "work"):
            return
        after = cls.digests()
        result = {"inputs_before": cls.before, "inputs_after": after, "stable": cls.before == after,
                  "records": cls.records, "native_format": cls.select.native,
                  "selfhost_complete": False, "OS_VM_built": False,
                  "artifacts": {str(path.relative_to(cls.work)): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in cls.work.rglob("*") if path.is_file()}}
        (cls.work / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        if cls.before != after:
            raise AssertionError("compiler, component or integration source changed during verification")

    def generated_functions(self, mode, variant):
        select_cases, forward_cases = [], []
        for index, (condition, mapping, arguments) in enumerate(CASES):
            item = ("choose%d" % index).encode("ascii")
            wrapper = ("forward%d" % index).encode("ascii")
            selected = INVERSE[condition] if variant == "bad-condition" else condition
            mapped = list(mapping)
            if variant == "bad-forward-map":
                mapped[2], mapped[3] = mapped[3], mapped[2]
            select_cases.append((b"composition", item, selected, index * 2, index * 2 + 1,
                                 1024, 0, 1, select.OK))
            forward_cases.append(self.forward.case((b"composition", wrapper, b"composition", item),
                                                   mapped, 6, 1536, forward.OK, flags=2))
        label = "composition-" + mode + "-" + variant
        chosen = self.select.emit(self.select.executables[mode], select_cases, label)
        forwarded = self.forward.emit(self.forward.executables[mode], forward_cases, label)
        return b"".join(chosen + forwarded).decode("ascii")

    def bridge(self):
        # Capture the returned machine state before restoring from an independent
        # host stack anchor; no register under test locates its observation area.
        lines = ["bits 64", "section .data", "align 8", "observation: dq 0",
                 "host_anchor: dq 0", "parked_rax: dq 0", "section .text"]
        for index, (_, _, arguments) in enumerate(CASES):
            lines += ["global compose%d" % index, "compose%d:" % index]
            lines += ["push " + register for register in select.CALLER]
            lines += ["sub rsp, 8", "mov [rel observation], rdi", "mov [rel host_anchor], rsp",
                      "mov r11, rdi", "mov [r11 + 8], rsp", "mov rax, rsp", "and rax, 15",
                      "mov [r11 + 80], rax", "mov rax, 0x%x" % select.CANARY, "mov [rsp], rax"]
            lines += ["mov %s, 0x%x" % pair for pair in select.CALLER.items()]
            lines += ["mov %s, 0x%x" % pair for pair in zip(REGISTERS, arguments)]
            lines += ["call " + select.symbol(b"composition", ("forward%d" % index).encode()),
                      "mov [rel parked_rax], rax", "mov rax, [rel observation]", "mov [rax + 16], rsp"]
            lines += ["mov [rax + %d], %s" % (24 + position * 8, register)
                      for position, register in enumerate(select.CALLER)]
            lines += ["mov rcx, [rel parked_rax]", "mov [rax], rcx", "mov rcx, [rel host_anchor]",
                      "mov rcx, [rcx]", "mov [rax + 72], rcx", "mov rsp, [rel host_anchor]", "add rsp, 8"]
            lines += ["pop " + register for register in reversed(select.CALLER)] + ["ret"]
        return "\n".join(lines) + "\n"

    def oracle_source(self):
        rows = []
        for condition, mapping, arguments in CASES:
            rows.append("{%d,{%s},{%s}}" % (condition, ",".join(map(str, mapping)),
                                           ",".join(map(c_u64, arguments))))
        return (ORACLE.replace("%DECLARATIONS%", "\n".join(
                    "extern void ABI compose%d(uint64_t *);" % i for i in range(len(CASES))))
                .replace("%CASES%", ",\n".join(rows))
                .replace("%CALLS%", ",".join("compose%d" % i for i in range(len(CASES))))
                .replace("%PRESERVED%", ",".join(map(c_u64, select.CALLER.values())))
                .replace("%CANARY%", c_u64(select.CANARY)))

    def command(self, command, label):
        run = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=180)
        (self.work / (label + ".log")).write_text(run.stdout + run.stderr)
        self.assertEqual(run.returncode, 0, (label, run.stdout, run.stderr))

    def test_real_forward_to_select_and_wrong_wiring_controls(self):
        oracle = self.work / "oracle.c"
        oracle.write_text(self.oracle_source(), encoding="ascii")
        for mode in ("debug", "release"):
            for variant in ("good", "bad-forward-map", "bad-condition"):
                with self.subTest(mode=mode, variant=variant):
                    label = mode + "-" + variant
                    asm = self.work / (label + ".asm")
                    asm.write_text(self.bridge() + self.generated_functions(mode, variant), encoding="ascii")
                    for fmt in ("elf64", "win64"):
                        self.command([self.select.nasm, "-f", fmt, *select.nasm_flags(self.select.nasm),
                                      "-o", self.work / (label + "." + fmt + ".o"), asm], label + "-" + fmt)
                    exe = self.work / (label + (".exe" if os.name == "nt" else ""))
                    self.command([self.select.cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                  oracle, self.work / (label + "." + self.select.native + ".o"), "-o", exe], label + "-link")
                    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
                    (self.work / (label + ".stdout")).write_text(run.stdout)
                    (self.work / (label + ".stderr")).write_text(run.stderr)
                    self.assertEqual(run.returncode, 0 if variant == "good" else 10, (label, run.stderr))
                    record = json.loads(run.stdout)
                    self.assertEqual(record, {"cases": 20, "yes": 10, "no": 10,
                                              "numeric_failures": 0 if variant == "good" else 20,
                                              "abi_failures": 0})
                    self.records.append({"mode": mode, "variant": variant, **record})


if __name__ == "__main__":
    unittest.main()
