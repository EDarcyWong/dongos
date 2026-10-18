"""Independent permission captures, ELF opcodes and host lifecycle; no QEMU."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest import mock


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load("run_permission_qemu", "run_permission_qemu.py")
fixture = load("permission_cache_fixture", "test_cache_qemu_result.py")
hard, old = fixture.hard, fixture.old
K = old.K
SYMBOLS = dict(fixture.SYMBOLS, __kernel_bss_end=K + 0x33000,
               permission_code_page=K + 0x1000, permission_data_page=K + 0x27000,
               permission_stack_page=K + 0x28000, permission_pdpt=K + 0x29000,
               permission_pd=K + 0x2a000, permission_pt=K + 0x2b000,
               permission_shadow_gdt=K + 0x5000, permission_shadow_gdt_end=K + 0x5038,
               permission_report=K + 0x2c000,
               permission_report_end=K + 0x2c000 + 296,
               permission_test_mid_return=K + 0x700, permission_test_inject_return=K + 0x600,
               permission_user_call_stub=K + 0x1000, permission_test_expected_rip=K + 0x800,
               permission_user_sgdt=K + 0x1040,
               permission_user_sidt=K + 0x1043, permission_user_sldt=K + 0x1047,
               permission_user_smsw=K + 0x104b, permission_user_str=K + 0x104f,
               permission_user_exit_hlt=K + 0x1090,
               permission_report_size=296, permission_opcodes_verified=1)
SYMBOLS.update({"permission_report_" + name: SYMBOLS["permission_report"] + index * 8
                for index, name in enumerate(runner.FIELDS)})


def prior_capture(profile):
    resources = old.resources()
    next(item for item in resources if item["kind"] == 11)["length"] = SYMBOLS["__kernel_bss_end"] - SYMBOLS["__kernel_bss_start"]
    serial = old.capture(manifest=resources, values={"mapped_pages": 402})
    hard_block = b"\r\n".join([*hard.hardening_lines(profile), runner.hardening.READY]) + b"\r\n"
    serial = serial.replace(runner.memory.ACTIVATION_READY + b"\r\n", runner.memory.ACTIVATION_READY + b"\r\n" + hard_block)
    cache_block = b"\r\n".join([*fixture.cache_lines(cr4=0x620 | hard.RAW[profile][2]), runner.cache.READY]) + b"\r\n"
    return serial.replace(runner.memory.MUTATION_READY + b"\r\n", runner.memory.MUTATION_READY + b"\r\n" + cache_block)


def permission_values(case="smep", **changes):
    values = dict.fromkeys(runner.FIELDS, 0)
    values.update(case_id=runner.CASES.index(case) + 1, cr0=0x80010011, cr3=0x800000,
                  cr4=0x620 | hard.RAW[runner.PROFILE[case]][2], efer=0xd00, pat=0x0007040600070406,
                  rflags=2, code_va=0x40000000, data_va=0x40001000, stack_top=0x40003000,
                  probe_rip=runner.expected_rip(case, SYMBOLS), gdt_base=K + 0x5000,
                  gdt_limit=55, idt_base=SYMBOLS["cpu_idt"], idt_limit=4095, ldtr=0, tr=0x18,
                  msw=0x11, steps=15 if case in ("smap-read", "smap-write") else 7)
    if case.startswith("smap-"):
        values.update(ac_flags=0x40002 if case != "smap-off" else 2,
                      ac_read=0x1122334455667788, ac_write=0x55aa33cc77ee9900)
    for kind, symbol in runner.BACKING.items():
        values[kind + "_pa"] = 0x200000 + SYMBOLS[symbol] - K
        for level, table in zip(("pml4", "pdpt", "pd"), runner.TABLES):
            values[kind + "_" + level] = (0x200000 + SYMBOLS[table] - K) | 7
        flags = (5 | ((1 << 63) if case == "nx-control" else 0)) if kind == "code" else (1 << 63) | 7
        values[kind + "_pte"] = values[kind + "_pa"] | flags
    values.update(changes)
    return values


def permission_lines(case="smep", **changes):
    values = permission_values(case, **changes)
    return [f"permission_{name}=0x{values[name]:016x}".encode() for name in runner.FIELDS]


def panic_values(case):
    user = case.startswith("umip-")
    rip = runner.expected_rip(case, SYMBOLS)
    values = dict(runner.memory.SEED_REGISTERS, context=K + 0x23000 - 184, stack="EXCEPTION",
                  rbp=0 if user else 0xffff900000010f00, vector=13 if user else 14,
                  error=0 if user else 1 if case == "smap-read" else 3 if case == "smap-write" else 0x11,
                  rip=rip, cs=0x2b if user else 8, ss=0x33 if user else 0x10,
                  rflags=2 if user else 0x402, rsp=0x40003000 if user else 0xffff900000010f00,
                  cr2=0 if user else 0x40001000 if case.startswith("smap-") else rip, frame_symbol=rip)
    if user:
        values["rdi"] = 0x40001000
        if case == "umip-off":
            values.update(rax=K + 0x5000, rbx=SYMBOLS["cpu_idt"], rcx=55, rdx=4095,
                          rsi=0, rdi=0x11, r8=0x18, r9=2)
    elif case in ("smep", "nx-control"):
        values.update(rax=rip, rsp=values["rbp"] - 8)
    else:
        values["rax"] = 0x40001000
    values.update(frame_00=rip, frame_count=1 if user else 3)
    if not user:
        values.update(frame_01=K + 0x700, frame_02=K + 0x600)
    return values


def panic_lines(case):
    values = panic_values(case)
    names = [*runner.memory.PANIC_FIELDS, *[f"frame_{i:02d}" for i in range(values["frame_count"])], "frame_count"]
    return [(f"panic_{name}={values[name]}" if name == "stack" else f"panic_{name}=0x{values[name]:016x}").encode()
            for name in names]


def capture(case="smep", **changes):
    block = [*permission_lines(case, **changes), runner.READY, runner.INJECT]
    block += [runner.PASS] if case in runner.SUCCESS else [runner.memory.PANIC, *panic_lines(case)]
    return prior_capture(runner.PROFILE[case]).replace(runner.memory.READY + b"\r\n" + runner.memory.PASS + b"\r\n",
                                                     b"\r\n".join(block) + b"\r\n")


def replace(serial, prefix, name, value):
    return old.replace_diagnostic(serial, prefix, name, value)


def permission_elf(symbols=SYMBOLS, *, case="smep", corrupted=None):
    # Add a real PT_LOAD image to the independent symbol-table fixture. The
    # permission reader must obtain opcode bytes from ELF, not a source file.
    data = bytearray(old.symbol_elf({name: value for name, value in symbols.items()
                                    if name not in (runner.REPORT_SIZE, runner.OPCODES_VERIFIED)}))
    image = bytearray(0x33000)
    for name, opcode in {**runner.OPCODES, **runner.opcode_contract(case)}.items():
        if name in symbols:
            offset = symbols[name] - K
            image[offset:offset + len(opcode)] = opcode
    if corrupted is not None:
        image[symbols[corrupted] - K] = 0x90
    phoff = len(data)
    struct.pack_into("<Q", data, 32, phoff)
    struct.pack_into("<HH", data, 54, 56, 1)
    data += struct.pack("<IIQQQQQQ", 1, 7, phoff + 56, K, K, len(image), len(image), 4096)
    return bytes(data + image)


class PermissionGateTests(unittest.TestCase):
    def check(self, serial=None, *, case="smep", code=None, timeout=False, symbols=SYMBOLS):
        return runner.check_result((41 if case in runner.SUCCESS else 37) if code is None else code,
                                   capture(case) if serial is None else serial, timeout, case, symbols)

    def test_twelve_cases_profiles_contexts_and_prior_reports(self):
        self.assertEqual(("smep", "smep-off", "nx-control", "smap-read", "smap-write", "smap-off",
                          "umip-sgdt", "umip-sidt", "umip-sldt", "umip-smsw", "umip-str", "umip-off"), runner.CASES)
        self.assertEqual(37, len(runner.FIELDS))
        self.assertEqual(("case_id", "cr0", "cr3", "cr4", "efer", "pat", "rflags", "ac_flags", "ac_read", "ac_write",
                          "code_va", "data_va", "stack_top", "probe_rip", "code_pa", "data_pa", "stack_pa",
                          "code_pml4", "code_pdpt", "code_pd", "code_pte", "data_pml4", "data_pdpt", "data_pd", "data_pte",
                          "stack_pml4", "stack_pdpt", "stack_pd", "stack_pte", "gdt_base", "gdt_limit", "idt_base",
                          "idt_limit", "ldtr", "tr", "msw", "steps"), runner.FIELDS)
        self.assertEqual(Path("build/test/permissions/qemu"), runner.STATE_DIR)
        for case in runner.CASES:
            with self.subTest(case=case):
                self.assertEqual([], self.check(case=case))
                result = runner.parse_result(capture(case), case=case, symbols=SYMBOLS)
                self.assertTrue(result["passed"])
                self.assertEqual(24, len(result["cache"]["cache"]))
                self.assertEqual(38, len(result["cache"]["hardening"]["memory"]["fields"]))
                self.assertEqual(case not in runner.SUCCESS, bool(result["panic"]))

    def test_each_report_field_required_known_unique_and_in_fixed_order(self):
        serial = capture()
        for line in permission_lines():
            with self.subTest(line=line):
                self.assertTrue(self.check(serial.replace(line + b"\r\n", b"")))
                self.assertTrue(self.check(serial.replace(line, line + b"\r\n" + line)))
                self.assertTrue(self.check(serial.replace(line, line.replace(b"permission_", b"permission_other_"))))
        first, second = permission_lines()[:2]
        self.assertTrue(self.check(serial.replace(first + b"\r\n" + second, second + b"\r\n" + first)))

    def test_format_markers_exclusive_stage_and_unexpected_tail(self):
        first = permission_lines()[0]
        for bad in (first.upper(), first + b" ", b"X" + first, b"permission_case_id=0x1", first.replace(b"0x", b"0X")):
            self.assertTrue(self.check(capture().replace(first, bad)))
        for serial in (capture()[:-1], capture().replace(runner.READY, b"X" + runner.READY),
                       capture().replace(runner.READY, runner.READY + b"\r\n" + runner.READY),
                       capture().replace(runner.INJECT, b""), capture().replace(runner.INJECT, runner.PASS),
                       capture().replace(first, b"noise\r\n" + first), capture() + b"noise\r\n",
                       capture().replace(runner.memory.PANIC, runner.memory.PANIC + b"\r\nnoise"),
                       capture().replace(runner.cache.READY, b"DONGOS_UNKNOWN\r\n" + runner.cache.READY)):
            self.assertTrue(self.check(serial))
        serial = capture("smep-off")
        self.assertTrue(self.check(serial + b"noise\r\n", case="smep-off"))
        block = b"\r\n".join(permission_lines()) + b"\r\n"
        moved = capture().replace(block, b"").replace(runner.memory.ACTIVATION_READY + b"\r\n",
                                                      runner.memory.ACTIVATION_READY + b"\r\n" + block)
        self.assertTrue(self.check(moved))

    def test_actual_user_chain_requires_each_level_and_rx_nx_contrast(self):
        values = permission_values()
        for kind in ("code", "data", "stack"):
            for level in ("pml4", "pdpt", "pd", "pte"):
                name = kind + "_" + level
                for mask in (1, 2, 4, 1 << 63, 0x1000):
                    # Code leaf is intentionally read-only; making it writable
                    # must fail as well as clearing a required ancestor write bit.
                    self.assertTrue(self.check(capture(**{name: values[name] ^ mask})), name)
        self.assertEqual([], self.check(capture(**{name: value | (0x60 if name.endswith("_pte") else 0x20)
                                                  for name, value in values.items()
                                                  if name.endswith(("_pml4", "_pdpt", "_pd", "_pte"))})))
        self.assertTrue(self.check(capture(code_pd=values["code_pd"] | 0x40)))
        for name in ("code_pa", "data_pa", "stack_pa", "code_va", "data_va", "stack_top", "probe_rip"):
            self.assertTrue(self.check(capture(**{name: values[name] + 4096})))
        self.assertTrue(self.check(capture("nx-control", code_pte=permission_values()["code_pte"]), case="nx-control"))
        self.assertTrue(self.check(capture("smep-off", code_pte=values["code_pte"] | (1 << 63)), case="smep-off"))

    def test_profile_controls_descriptor_references_and_ac_actual_evidence(self):
        for name in ("case_id", "cr0", "cr3", "cr4", "efer", "pat", "gdt_base", "gdt_limit", "idt_base", "idt_limit",
                     "tr", "msw", "steps"):
            self.assertTrue(self.check(capture(**{name: permission_values()[name] ^ 1})), name)
        self.assertTrue(self.check(capture(rflags=0x202)))
        self.assertTrue(self.check(capture(ac_read=runner.TOKEN)))
        self.assertTrue(self.check(capture(ldtr=0x10000)))
        self.assertTrue(self.check(replace(capture(), "memory", "physical_bits", (1 << 64) - 1)))
        for case in ("smap-read", "smap-write"):
            for name, value in (("ac_flags", 2), ("ac_flags", 0x40202), ("ac_read", 0), ("ac_write", 0), ("steps", 7)):
                self.assertTrue(self.check(capture(case, **{name: value}), case=case))
        self.assertTrue(self.check(capture("smep-off")))
        self.assertTrue(self.check(capture(), case="smep-off"))
        for key in (runner.REPORT_SIZE, runner.OPCODES_VERIFIED, runner.PROBE["smep"], "permission_report_case_id"):
            self.assertTrue(self.check(symbols={name: value for name, value in SYMBOLS.items() if name != key}))

    def test_original_memory_mutation_cache_and_hardening_are_still_required(self):
        for prefix, name, value in (("memory", "free_pages", 0), ("activation", "cr0", 0),
                                    ("hardening", "supported", 0), ("mutation", "invlpg_count", 0),
                                    ("cache", "free_after", 0)):
            self.assertTrue(self.check(replace(capture(), prefix, name, value)))

    def test_kernel_context_fault_error_original_registers_and_trusted_frames(self):
        for case in ("smep", "nx-control", "smap-read", "smap-write"):
            serial = capture(case)
            values = panic_values(case)
            for name in ("context", "rax", "rbx", "rdi", "vector", "error", "rip", "cs", "ss", "rsp", "rbp", "cr2",
                         "frame_symbol", "frame_00", "frame_01", "frame_02", "frame_count"):
                with self.subTest(case=case, field=name):
                    self.assertTrue(self.check(replace(serial, "panic", name, values[name] ^ 1), case=case))
            self.assertTrue(self.check(replace(serial, "panic", "rflags", 0x40402), case=case))
            self.assertTrue(self.check(serial.replace(b"panic_stack=EXCEPTION", b"panic_stack=OTHER"), case=case))

    def test_cpl3_umip_fault_must_be_selected_opcode_not_bad_entry_or_fake_kernel_fault(self):
        for case in runner.CASES[6:]:
            serial, values = capture(case), panic_values(case)
            for name in ("rip", "cs", "ss", "rsp", "rbp", "cr2", "vector", "error", "context", "frame_count"):
                self.assertTrue(self.check(replace(serial, "panic", name, values[name] ^ 1), case=case), (case, name))
            self.assertTrue(self.check(replace(serial, "panic", "rflags", 0x402), case=case))
            self.assertTrue(self.check(replace(serial, "panic", "rip", 0x40001000), case=case))
        for name in ("rax", "rbx", "rcx", "rdx", "rsi", "rdi", "r8", "r9"):
            self.assertTrue(self.check(replace(capture("umip-off"), "panic", name,
                                               0xa5a5a5a5a5a5a5a5), case="umip-off"), name)
        self.assertTrue(self.check(replace(capture("umip-off"), "panic", "rip", runner.expected_rip("umip-sgdt", SYMBOLS)),
                                   case="umip-off"))
        baseline = replace(capture("umip-off", ldtr=0x28), "panic", "rsi", 0x28)
        self.assertEqual([], self.check(baseline, case="umip-off"))
        no_frame = capture("umip-off").replace(f"panic_frame_00=0x{panic_values('umip-off')['frame_00']:016x}\r\n".encode(), b"")
        self.assertTrue(self.check(replace(no_frame, "panic", "frame_count", 0), case="umip-off"))

    def test_exit_timeout_unknown_case_and_normal_terminal_panic_separation(self):
        for case in runner.CASES:
            self.assertTrue(self.check(case=case, code=33))
            self.assertTrue(self.check(case=case, code=37 if case in runner.SUCCESS else 41))
            self.assertTrue(self.check(case=case, timeout=True))
        self.assertFalse(runner.parse_result(capture(), case="unknown", symbols=SYMBOLS)["passed"])
        self.assertTrue(self.check(capture().replace(runner.memory.PANIC, runner.PASS), case="smep"))

    def test_cache_optional_profile_is_explicit_validated_and_default_unchanged(self):
        self.assertTrue(runner.cache.parse_result(fixture.capture(), symbols=fixture.SYMBOLS)["passed"])
        self.assertFalse(runner.cache.parse_result(prior_capture("no-smep"), symbols=SYMBOLS)["passed"])
        self.assertTrue(runner.cache.parse_result(prior_capture("no-smep"), symbols=SYMBOLS, hardening_case="no-smep")["passed"])
        self.assertFalse(runner.cache.parse_result(prior_capture("no-smep"), symbols=SYMBOLS, hardening_case="unknown")["passed"])

    def test_exact_elf_field_aliases_backing_and_real_opcode_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            elf = Path(temporary) / "kernel.elf"
            elf.with_name("dong_layout.json").write_text(json.dumps(fixture.layout_manifest()))
            for case in runner.CASES:
                elf.write_bytes(permission_elf(case=case))
                self.assertEqual(296, runner.read_validation_symbols(elf, case=case)[runner.REPORT_SIZE])
            for name in ("permission_report_end", "permission_report_steps", "permission_code_page", "permission_pdpt"):
                symbols = dict(SYMBOLS)
                symbols[name] += 8
                elf.write_bytes(permission_elf(symbols))
                with self.subTest(symbol=name), self.assertRaises(ValueError):
                    runner.read_validation_symbols(elf)
            for name in runner.OPCODES:
                elf.write_bytes(permission_elf(corrupted=name))
                case = "umip-off"
                with self.subTest(opcode=name), self.assertRaisesRegex(ValueError, "opcode"):
                    runner.read_validation_symbols(elf, case=case)
            for case in ("smap-read", "smap-write"):
                elf.write_bytes(permission_elf(case=case, corrupted="permission_test_expected_rip"))
                with self.assertRaisesRegex(ValueError, "opcode"):
                    runner.read_validation_symbols(elf, case=case)
            symbols = dict(SYMBOLS, permission_user_sidt=K + 0x1200)
            elf.write_bytes(permission_elf(symbols, case="umip-off"))
            with self.assertRaisesRegex(ValueError, "consecutive"):
                runner.read_validation_symbols(elf, case="umip-off")


class PermissionLifecycleTests(unittest.TestCase):
    def run_mock(self, root, case="smep", mode="success"):
        state = root / runner.STATE_DIR / case
        build_dir, esp = state / "build", state / "build/esp"
        esp.mkdir(parents=True)
        (state / "serial.log").write_bytes(b"STALE_SUCCESS")
        (state / "result.json").write_text('{"passed":true}')
        (build_dir / "kernel.elf").write_bytes(permission_elf(case=case))
        (build_dir / "dong_layout.json").write_text(json.dumps(fixture.layout_manifest()))
        process = mock.Mock()
        code = 41 if case in runner.SUCCESS else 37
        process.returncode = process.poll.return_value = process.wait.return_value = code
        if mode in ("timeout", "interrupt", "exception"):
            error = subprocess.TimeoutExpired("qemu", 1) if mode == "timeout" else KeyboardInterrupt() if mode == "interrupt" else RuntimeError("host failure")
            process.wait.side_effect = [error, code]
            process.poll.side_effect = [None, code]

        def builder(**kwargs):
            self.assertEqual({"test": True, "stage": "p1", "output": build_dir, "permission_case": case}, kwargs)
            self.assertEqual(b"", (state / "serial.log").read_bytes())
            self.assertFalse(json.loads((state / "result.json").read_text())["passed"])
            if mode == "build-error":
                raise RuntimeError("deliberate builder failure")
            return esp

        def launch(*args, **kwargs):
            self.assertEqual(b"", (state / "serial.log").read_bytes())
            (state / "serial.log").write_bytes(capture(case))
            return process

        with (mock.patch.object(runner, "ROOT", root), mock.patch.object(runner, "build", side_effect=builder) as build,
              mock.patch.object(runner, "qemu_command", return_value=["qemu", str(esp)]) as command,
              mock.patch.object(runner.subprocess, "Popen", side_effect=launch) as popen, redirect_stdout(io.StringIO())):
            result = runner.run_case(case, 1)
        self.assertEqual(result, json.loads((state / "result.json").read_text()))
        return result, process, build, command, popen

    def test_each_case_has_separate_build_state_expected_cpu_and_logs(self):
        for case in runner.CASES:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                result, _, builder, command, _ = self.run_mock(Path(temporary), case)
                self.assertTrue(result["passed"], result)
                builder.assert_called_once()
                self.assertEqual(["-cpu", runner.hardening.PROFILES[runner.PROFILE[case]][0]], result["command"][-2:])
                self.assertEqual(Path(temporary) / runner.STATE_DIR / case, command.call_args.args[1])

    def test_timeout_interrupt_exception_reap_and_stale_success_discard(self):
        for mode in ("timeout", "interrupt", "exception"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                result, process, _, _, _ = self.run_mock(Path(temporary), mode=mode)
                self.assertFalse(result["passed"])
                process.kill.assert_called_once()
                self.assertEqual(2, process.wait.call_count)
                self.assertEqual(mode == "timeout", result["timed_out"])
                self.assertEqual(mode == "interrupt", result["interrupted"])
        with tempfile.TemporaryDirectory() as temporary:
            result, _, _, _, popen = self.run_mock(Path(temporary), mode="build-error")
            self.assertFalse(result["passed"])
            self.assertIsNone(result["returncode"])
            popen.assert_not_called()

    def test_cli_all_serial_order_failures_and_invalid_input(self):
        for args, expected in (([], ["smep"]), (["--all"], list(runner.CASES))):
            with tempfile.TemporaryDirectory() as temporary, mock.patch.object(runner, "ROOT", Path(temporary)), \
                    mock.patch.object(runner, "run_case", return_value={"passed": True, "interrupted": False}) as run:
                self.assertEqual(0, runner.main(args))
                self.assertEqual([mock.call(case, 60.0) for case in expected], run.call_args_list)
        for timeout in (0, -1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                runner.run_case("smep", timeout)
        with self.assertRaises(ValueError):
            runner.run_case("unknown", 1)
        with mock.patch.object(runner, "run_case") as run, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                runner.main(["--timeout", "nan"])
            run.assert_not_called()
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(runner, "ROOT", Path(temporary)), \
                mock.patch.object(runner, "run_case", side_effect=RuntimeError("host failed")):
            self.assertEqual(1, runner.main(["--all"]))
            self.assertFalse(json.loads((Path(temporary) / runner.STATE_DIR / "result.json").read_text())["passed"])


if __name__ == "__main__":
    unittest.main()
