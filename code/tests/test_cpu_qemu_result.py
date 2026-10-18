"""CPU fault acceptance must reject partial diagnostics and every false pass."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import build as builder

spec = importlib.util.spec_from_file_location("run_cpu_qemu", Path(__file__).with_name("run_cpu_qemu.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

SYMBOLS = {
    "cpu_df_stack_bottom": 0xffffffff80020000, "cpu_df_stack_top": 0xffffffff80024000,
    "cpu_exception_stack_bottom": 0xffffffff80030000, "cpu_exception_stack_top": 0xffffffff80034000,
    "cpu_test_expected_rip": 0xffffffff80001234,
    "cpu_test_mid_return": 0xffffffff80001120, "cpu_test_inject_return": 0xffffffff80001100,
}


def good_capture(case="ud2"):
    fields = dict(runner.SEED_REGISTERS)
    fields.update(context=SYMBOLS["cpu_exception_stack_top"] - 184,
                  rbp=0x100ff00, rsp=0x100ff00, vector=runner.CASE_VECTORS[case],
                  error=0, rip=SYMBOLS["cpu_test_expected_rip"], cs=8, ss=0x10,
                  rflags=0x402, cr2=0, frame_symbol=SYMBOLS["cpu_test_expected_rip"])
    if case in {"gp", "double-fault"}:
        fields["rax"] = 0x28
    if case == "gp":
        fields["error"] = 0x28
    if case == "pf":
        fields["rax"] = fields["cr2"] = runner.UNMAPPED_ADDRESS
    if case == "bad-stack":
        fields["rsp"] = runner.UNMAPPED_ADDRESS
    if case == "bad-frame":
        fields["rbp"] = runner.UNMAPPED_ADDRESS
    if case == "double-fault":
        fields["context"] = SYMBOLS["cpu_df_stack_top"] - 184
        fields["rip"] = fields["frame_symbol"] = 0xffffffff80005678
    if case == "divide":
        fields.update(rax=1, rcx=0, rdx=0)
    frames = [fields["rip"]] if case == "bad-frame" else [fields["rip"], SYMBOLS["cpu_test_mid_return"], SYMBOLS["cpu_test_inject_return"]]
    markers = runner.PREFIX_MARKERS + [f"DONGOS_P2_INJECT:{case}".encode(), runner.PANIC_MARKER]
    lines = list(markers)
    lines.append(f"panic_context=0x{fields.pop('context'):016x}".encode())
    lines.append(b"panic_stack=" + (b"DF" if case == "double-fault" else b"EXCEPTION"))
    lines += [f"panic_{name}=0x{value:016x}".encode() for name, value in fields.items()]
    lines += [f"panic_frame_{i:02d}=0x{value:016x}".encode() for i, value in enumerate(frames)]
    lines.append(f"panic_frame_count=0x{len(frames):016x}".encode())
    return b"\r\n".join(lines) + b"\r\n"


def replace_field(serial, name, value):
    prefix = f"panic_{name}=".encode()
    return b"\r\n".join(f"panic_{name}=0x{value:016x}".encode() if line.startswith(prefix) else line
                           for line in serial.split(b"\r\n"))


def symbol_elf(symbols=SYMBOLS):
    """Small independent ELF fixture with a real SHT_SYMTAB and string table."""
    strings = bytearray(b"\0")
    entries = [bytes(24)]
    for name, value in symbols.items():
        offset = len(strings)
        strings += name.encode() + b"\0"
        entries.append(struct.pack("<IBBHQQ", offset, 0x10, 0, 1, value, 0))
    symtab = b"".join(entries)
    table_offset = 64
    symbols_offset = table_offset + 3 * 64
    strings_offset = symbols_offset + len(symtab)
    header = bytearray(64)
    header[:16] = b"\x7fELF\x02\x01\x01" + bytes(9)
    struct.pack_into("<HHIQQQIHHHHHH", header, 16, 2, 62, 1, 0, 0, table_offset, 0, 64, 0, 0, 64, 3, 0)
    sections = bytes(64) + struct.pack("<IIQQQQIIQQ", 0, 2, 0, 0, symbols_offset, len(symtab), 2, 0, 8, 24)
    sections += struct.pack("<IIQQQQIIQQ", 0, 3, 0, 0, strings_offset, len(strings), 0, 0, 1, 0)
    return bytes(header) + sections + symtab + strings


class CpuGateTests(unittest.TestCase):
    def check(self, serial=None, *, case="ud2", code=37, timeout=False, symbols=SYMBOLS):
        return runner.check_result(code, good_capture(case) if serial is None else serial, timeout, case, symbols)

    def test_all_eight_valid_captures_and_df_abort_rip(self):
        for case in runner.CPU_TEST_CASES:
            with self.subTest(case=case):
                self.assertEqual([], self.check(case=case))

    def test_crash_normal_exit_missing_process_and_timeout_never_pass(self):
        for code in (None, 0, 1, 33, 35, -9):
            with self.subTest(code=code):
                self.assertTrue(self.check(code=code))
        self.assertTrue(self.check(timeout=True))

    def test_partial_missing_embedded_duplicate_and_reordered_markers(self):
        serial = good_capture()
        variants = [serial[:-1], serial.replace(b"DONGOS_P1_EBS_OK\r\n", b""),
                    serial.replace(b"DONGOS_P2_PANIC", b"xDONGOS_P2_PANIC"),
                    serial + runner.PANIC_MARKER + b"\r\n",
                    serial.replace(b"DONGOS_P1_START", b"DONGOS_P1_READY", 1)]
        for value in variants:
            with self.subTest(serial=value[:100]):
                self.assertTrue(self.check(value))

    def test_later_success_failure_reentry_and_other_injection_are_rejected(self):
        for extra in (b"DONGOS_P1_PASS", b"DONGOS_L1_PROBE_OK: 42", b"DONGOS_P2_PANIC_REENTERED",
                      b"DONGOS_OTHER_FAIL", b"DONGOS_UNEXPECTED_SUCCESS", b"DONGOS_P2_INJECT:gp"):
            with self.subTest(extra=extra):
                self.assertTrue(self.check(good_capture() + extra + b"\r\n"))

    def test_fields_are_complete_unique_known_and_after_the_marker(self):
        serial = good_capture()
        line = b"panic_vector=0x0000000000000006\r\n"
        for value in (serial.replace(line, b""), serial + line,
                      serial.replace(line, b"panic_vector=0x6\r\n"),
                      serial.replace(line, b"panic_vector=0x000000000000000g\r\n"),
                      serial + b"panic_extra=0x0000000000000000\r\n", line + serial,
                      serial + b"panic_stack=EXCEPTION\r\n"):
            with self.subTest(value=value[-100:]):
                self.assertTrue(self.check(value))

    def test_vector_error_rip_cr2_and_segments(self):
        for name, value in (("vector", 13), ("error", 1), ("rip", 0), ("cs", 0x38), ("ss", 0), ("frame_symbol", 0)):
            with self.subTest(name=name):
                self.assertTrue(self.check(replace_field(good_capture(), name, value)))
        self.assertTrue(self.check(replace_field(good_capture("gp"), "error", 0), case="gp"))
        self.assertTrue(self.check(replace_field(good_capture("pf"), "cr2", 0), case="pf"))

    def test_each_seeded_gpr_and_case_overrides_are_observed(self):
        for name in runner.SEED_REGISTERS:
            with self.subTest(name=name):
                self.assertTrue(self.check(replace_field(good_capture(), name, 0)))
        for case, name in (("gp", "rax"), ("pf", "rax"), ("divide", "rax"), ("divide", "rcx"), ("divide", "rdx")):
            with self.subTest(case=case, name=name):
                self.assertTrue(self.check(replace_field(good_capture(case), name, 9), case=case))

    def test_saved_flags_and_interrupted_stack_frame(self):
        for flags in (0x602, 2, 0x400):
            self.assertTrue(self.check(replace_field(good_capture(), "rflags", flags)))
        for name, value in (("rbp", 0), ("rbp", 0x100ff08), ("rsp", 0), ("rsp", 0x100fe00)):
            self.assertTrue(self.check(replace_field(good_capture(), name, value)))
        self.assertTrue(self.check(replace_field(good_capture("bad-stack"), "rsp", 0x100ff00), case="bad-stack"))
        self.assertTrue(self.check(replace_field(good_capture("bad-frame"), "rbp", 0x100ff00), case="bad-frame"))

    def test_context_must_fit_the_correct_ist_in_full(self):
        serial = good_capture()
        for context in (0, SYMBOLS["cpu_exception_stack_bottom"] - 8,
                        SYMBOLS["cpu_exception_stack_top"] - 8,
                        SYMBOLS["cpu_df_stack_top"] - 184,
                        SYMBOLS["cpu_exception_stack_top"] - 183):
            self.assertTrue(self.check(replace_field(serial, "context", context)))
        self.assertTrue(self.check(serial.replace(b"panic_stack=EXCEPTION", b"panic_stack=DF")))
        self.assertTrue(self.check(serial.replace(b"panic_stack=EXCEPTION", b"panic_stack=UNKNOWN")))
        self.assertTrue(self.check(symbols={}))

    def test_frame_count_indices_order_and_linked_returns(self):
        serial = good_capture()
        for value in (0, 2, 17):
            self.assertTrue(self.check(replace_field(serial, "frame_count", value)))
        for name in ("frame_00", "frame_01", "frame_02"):
            self.assertTrue(self.check(replace_field(serial, name, 0)))
        self.assertTrue(self.check(serial + b"panic_frame_01=0xffffffff80001120\r\n"))
        self.assertTrue(self.check(serial.replace(b"panic_frame_01=", b"panic_frame_03=")))
        self.assertTrue(self.check(serial.replace(b"panic_frame_01=", b"panic_frame_16=")))
        first, second = b"panic_frame_01=0xffffffff80001120", b"panic_frame_02=0xffffffff80001100"
        self.assertTrue(self.check(serial.replace(first + b"\r\n" + second, second + b"\r\n" + first)))
        bad = good_capture("bad-frame")
        bad = replace_field(bad, "frame_count", 2) + b"panic_frame_01=0xffffffff80001120\r\n"
        self.assertTrue(self.check(bad, case="bad-frame"))

    def test_sht_symtab_reader_rejects_bad_or_missing_elf_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.elf"
            path.write_bytes(symbol_elf())
            self.assertEqual(SYMBOLS, runner.read_elf_symbols(path))
            for data in (b"", symbol_elf()[:-1], b"NOPE" + symbol_elf()[4:], symbol_elf({})):
                with self.subTest(size=len(data)):
                    path.write_bytes(data)
                    with self.assertRaises(ValueError):
                        runner.read_elf_symbols(path)


class CpuRunnerTests(unittest.TestCase):
    def test_build_rejects_non_test_p0_and_unknown_before_tools(self):
        with mock.patch.object(builder, "find_tool", side_effect=AssertionError("must validate before tools")):
            for options in ({"cpu_case": "ud2"}, {"test": True, "stage": "p0", "cpu_case": "ud2"},
                            {"test": True, "stage": "p1", "cpu_case": "unknown"}):
                with self.subTest(options=options), self.assertRaises(builder.ToolError):
                    builder.build(**options)

    def run_mock(self, temporary, *, mode="success"):
        root = Path(temporary)
        state = root / "build/test/cpu/ud2"
        state.mkdir(parents=True, exist_ok=True)
        (state / "serial.log").write_bytes(b"STALE_SUCCESS")
        (state / "result.json").write_text('{"passed":true}')
        esp = state / "build/esp"
        esp.mkdir(parents=True)
        (esp.parent / "kernel.elf").write_bytes(symbol_elf())
        process = mock.Mock()
        process.returncode = 37
        process.wait.return_value = 37
        process.poll.return_value = 37

        def launch(*args, **kwargs):
            self.assertEqual((state / "serial.log").read_bytes(), b"")
            self.assertFalse(json.loads((state / "result.json").read_text())["passed"])
            (state / "serial.log").write_bytes(good_capture())
            return process

        if mode in {"timeout", "interrupt", "exception"}:
            process.poll.side_effect = [None, 37, 37]
            problem = subprocess.TimeoutExpired("qemu", 1) if mode == "timeout" else KeyboardInterrupt() if mode == "interrupt" else RuntimeError("host failure")
            process.wait.side_effect = [problem, 37]
        with mock.patch.object(runner, "ROOT", root), mock.patch.object(runner, "build", return_value=esp) as rebuild, \
                mock.patch.object(runner, "qemu_command", return_value=["qemu", "test"]) as command, \
                mock.patch.object(runner.subprocess, "Popen", side_effect=launch), mock.patch("sys.stdout", new=io.StringIO()):
            result = runner.run_case("ud2", 1)
        rebuild.assert_called_once_with(test=True, stage="p1", cpu_case="ud2")
        command.assert_called_once_with(esp, state, test=True)
        self.assertEqual(result, json.loads((state / "result.json").read_text()))
        self.assertEqual(result["command"], ["qemu", "test"])
        return result, process

    def test_fresh_rebuild_clears_stale_results_and_records_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, process = self.run_mock(temporary)
        self.assertTrue(result["passed"])
        process.kill.assert_not_called()

    def test_timeout_interrupt_and_host_exception_kill_and_reap(self):
        for mode in ("timeout", "interrupt", "exception"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                result, process = self.run_mock(temporary, mode=mode)
                self.assertFalse(result["passed"])
                process.kill.assert_called_once()
                self.assertGreaterEqual(process.wait.call_count, 2)
                self.assertEqual(result["timed_out"], mode == "timeout")
                self.assertEqual(result["interrupted"], mode == "interrupt")

    def test_build_failure_is_a_recorded_failure_without_qemu(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(runner, "ROOT", Path(temporary)), \
                mock.patch.object(runner, "build", side_effect=RuntimeError("failed build")), \
                mock.patch.object(runner.subprocess, "Popen") as process, mock.patch("sys.stdout", new=io.StringIO()):
            result = runner.run_case("ud2", 1)
        self.assertFalse(result["passed"])
        self.assertIn("failed build", result["errors"][0])
        process.assert_not_called()

    def test_all_cases_are_serial_and_aggregate_never_keeps_a_stale_pass(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(runner, "ROOT", Path(temporary)):
            calls = []
            def one(case, timeout):
                self.assertEqual(timeout, 2)
                calls.append(case)
                return {"case": case, "passed": case != "gp"}
            with mock.patch.object(runner, "run_case", side_effect=one):
                self.assertEqual(1, runner.main(["--all", "--timeout", "2"]))
            result = json.loads((Path(temporary) / "build/test/cpu/result.json").read_text())
        self.assertEqual(calls, list(runner.CPU_TEST_CASES))
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["results"]), 8)

    def test_timeout_must_be_finite_and_positive(self):
        with mock.patch("sys.stderr", new=io.StringIO()):
            for value in ("0", "-1", "nan", "inf"):
                with self.subTest(value=value), self.assertRaises(SystemExit):
                    runner.main(["--timeout", value])


if __name__ == "__main__":
    unittest.main()
