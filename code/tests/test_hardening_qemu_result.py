"""Independent hardening capture and runner gates; never launch a real guest."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load("run_hardening_qemu", "run_hardening_qemu.py")
old = load("hardening_capture_fixture", "test_memory_qemu_result.py")
SYMBOLS = old.SYMBOLS
RAW = {
    "all-features": (0x100080, 4, 0x300800),
    "no-smep": (0x100000, 4, 0x200800),
    "no-smap": (0x80, 4, 0x100800),
    "no-umip": (0x100080, 0, 0x300000),
    "no-features": (0, 0, 0),
}


def hardening_lines(case="all-features", **changes):
    ebx, ecx, supported = RAW[case]
    values = dict(zip(runner.FIELDS, (7, ebx, ecx, supported, 0x620, 0x620 | supported,
                                     2, 0x46, 0x80010011, 0x800000, 0xd00,
                                     0x0007040600070406, 7)))
    values.update(changes)
    return [f"hardening_{name}=0x{values[name]:016x}".encode() for name in runner.FIELDS]


def capture(case="all-features", **changes):
    block = b"\r\n".join([*hardening_lines(case, **changes), runner.READY])
    return old.capture().replace(runner.memory.ACTIVATION_READY + b"\r\n",
                                 runner.memory.ACTIVATION_READY + b"\r\n" + block + b"\r\n")


def layout_manifest():
    layout = old.layout_manifest()
    layout["types"].append({"full_name": "cpu.hardening.Report", "size": 104, "alignment": 8,
                            "fields": [{"name": name, "offset": index * 8}
                                       for index, name in enumerate(runner.FIELDS)]})
    return layout


class HardeningGateTests(unittest.TestCase):
    def check(self, serial=None, *, case="all-features", code=33, timeout=False, symbols=SYMBOLS):
        return runner.check_result(code, capture(case) if serial is None else serial, timeout, case, symbols)

    def test_all_independent_profiles_and_old_reports_pass(self):
        self.assertEqual(("all-features", "no-smep", "no-smap", "no-umip", "no-features"), runner.CASES)
        self.assertEqual(("max_basic", "leaf7_ebx", "leaf7_ecx", "supported", "cr4_before", "cr4_after",
                          "rflags_before", "rflags_after", "cr0", "cr3", "efer", "pat", "steps"), runner.FIELDS)
        self.assertEqual(0x300800, runner.MASK)
        for case in RAW:
            with self.subTest(case=case):
                self.assertEqual([], self.check(case=case))
                parsed = runner.parse_result(capture(case), case=case, symbols=SYMBOLS)
                self.assertTrue(parsed["passed"])
                self.assertEqual(RAW[case][2], parsed["hardening"]["supported"])
                self.assertEqual(38, len(parsed["memory"]["fields"]))
                self.assertEqual(14, len(parsed["memory"]["activation"]))
                self.assertEqual(18, len(parsed["memory"]["mutation"]))

    def test_every_field_is_required_unique_and_in_fixed_order(self):
        for line in hardening_lines():
            with self.subTest(line=line):
                self.assertTrue(self.check(capture().replace(line + b"\r\n", b"")))
                self.assertTrue(self.check(capture().replace(line, line + b"\r\n" + line)))
                self.assertTrue(self.check(capture().replace(line, line.replace(b"hardening_", b"hardening_unknown_"))))
        first, second = hardening_lines()[:2]
        swapped = capture().replace(first + b"\r\n" + second, second + b"\r\n" + first)
        self.assertTrue(self.check(swapped))

    def test_raw_cpuid_width_missing_leaf_and_unrelated_bits(self):
        for field in ("max_basic", "leaf7_ebx", "leaf7_ecx"):
            self.assertTrue(self.check(capture(**{field: 0x100000000})))
        self.assertEqual([], self.check(capture("no-features", max_basic=6), case="no-features"))
        for changes in ({"max_basic": 6, "leaf7_ebx": 1}, {"max_basic": 0, "leaf7_ecx": 1}):
            self.assertTrue(self.check(capture("no-features", **changes), case="no-features"))
        self.assertEqual([], self.check(capture(leaf7_ebx=0xffffffff, leaf7_ecx=0xffffffff)))
        for field, value in (("leaf7_ebx", 0x100000), ("leaf7_ecx", 0), ("supported", 0),
                             ("supported", 0x300801)):
            self.assertTrue(self.check(capture(**{field: value})))
        for case in RAW:
            for other in RAW:
                if case != other:
                    self.assertTrue(self.check(capture(case), case=other))

    def test_real_cr4_and_other_control_readback_are_mandatory(self):
        for changes in ({"cr4_after": 0x620}, {"cr4_after": 0x300621},
                        {"cr4_before": 0x621}, {"cr4_before": 0x100620},
                        {"cr0": 0x80000011}, {"cr3": 0x510000}, {"efer": 0x500},
                        {"pat": 0}, {"steps": 0}, {"steps": 15}):
            with self.subTest(changes=changes):
                self.assertTrue(self.check(capture(**changes)))
        self.assertTrue(self.check(capture("no-features", cr4_before=0x100620, cr4_after=0x100620),
                                   case="no-features"))

    def test_flags_require_fixed_bit_and_if_df_vm_ac_clear(self):
        for field in ("rflags_before", "rflags_after"):
            for flag in (0, 1 << 9, 1 << 10, 1 << 17, 1 << 18):
                value = 0 if flag == 0 else 2 | flag
                self.assertTrue(self.check(capture(**{field: value})))
        self.assertEqual([], self.check(capture(rflags_before=0x8d7, rflags_after=0x46)))

    def test_format_marker_and_stage_placement_fail_closed(self):
        line = hardening_lines()[0]
        for bad in (line.upper(), line + b" ", b"X" + line, line.replace(b"0x", b"0X"),
                    line.replace(b"0000000000000007", b"7"), b"hardening_max_basic=7"):
            self.assertTrue(self.check(capture().replace(line, bad)))
        for serial in (capture().replace(runner.READY, b""),
                       capture().replace(runner.READY, runner.READY + b"\r\n" + runner.READY),
                       capture().replace(runner.READY, b"prefix" + runner.READY),
                       capture().replace(hardening_lines()[3], b"unrelated line\r\n" + hardening_lines()[3]),
                       capture().replace(runner.READY, b"DONGOS_UNKNOWN\r\n" + runner.READY),
                       capture()[:-1]):
            self.assertTrue(self.check(serial))
        block = b"\r\n".join([*hardening_lines(), runner.READY]) + b"\r\n"
        stripped = capture().replace(block, b"")
        self.assertTrue(self.check(block + stripped))
        self.assertTrue(self.check(stripped + block))

    def test_existing_memory_semantics_exit_and_fault_rejection_are_retained(self):
        for prefix, name, value in (("mutation", "read_b", 0), ("activation", "cache_steps", 0),
                                    ("memory", "root_physical", 0)):
            self.assertTrue(self.check(old.replace_diagnostic(capture(), prefix, name, value)))
        for code in (None, 0, 35, 37):
            self.assertTrue(self.check(code=code))
        self.assertTrue(self.check(timeout=True))
        self.assertTrue(self.check(capture() + b"DONGOS_P2_PANIC\r\n"))
        self.assertTrue(self.check(old.capture("tlb-ro")))
        self.assertTrue(self.check(symbols={}))
        self.assertTrue(self.check(capture(), case="unknown"))


class HardeningLayoutTests(unittest.TestCase):
    def test_compiled_layout_and_original_layout_symbols_are_all_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.elf"
            path.write_bytes(old.symbol_elf())
            manifest_path = path.with_name("dong_layout.json")
            manifest_path.write_text(json.dumps(layout_manifest()))
            self.assertEqual(SYMBOLS, runner.read_validation_symbols(path))
            for change in ("missing", "size", "alignment", "name", "offset", "order", "duplicate"):
                layout = layout_manifest()
                report = layout["types"][-1]
                if change == "missing":
                    layout["types"].pop()
                elif change == "duplicate":
                    layout["types"].append(dict(report))
                elif change == "size":
                    report["size"] = 112
                elif change == "alignment":
                    report["alignment"] = 16
                elif change == "name":
                    report["fields"][-1]["name"] = "other"
                elif change == "offset":
                    report["fields"][-1]["offset"] = 88
                else:
                    report["fields"][:2] = reversed(report["fields"][:2])
                manifest_path.write_text(json.dumps(layout))
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "hardening Report"):
                    runner.read_validation_symbols(path)
            manifest_path.write_text(json.dumps(layout_manifest()))
            symbols = dict(SYMBOLS)
            del symbols["cpu_idt"]
            path.write_bytes(old.symbol_elf(symbols))
            with self.assertRaisesRegex(ValueError, "cpu_idt"):
                runner.read_validation_symbols(path)


class HardeningLifecycleTests(unittest.TestCase):
    def run_mock(self, root, *, case="all-features", mode="success", reuse=False):
        state = root / runner.STATE_DIR / case
        state.mkdir(parents=True)
        (state / "serial.log").write_bytes(b"STALE_SUCCESS")
        (state / "result.json").write_text('{"passed":true}')
        esp = root / runner.STATE_DIR / "normal/build/esp"
        esp.mkdir(parents=True)
        (esp.parent / "kernel.elf").write_bytes(old.symbol_elf())
        (esp.parent / "dong_layout.json").write_text(json.dumps(layout_manifest()))
        process = mock.Mock()
        process.returncode = 33
        process.poll.return_value = 33
        process.wait.return_value = 33
        if mode in ("timeout", "interrupt", "exception"):
            problem = (subprocess.TimeoutExpired("qemu", 1) if mode == "timeout" else
                       KeyboardInterrupt() if mode == "interrupt" else RuntimeError("host wait failure"))
            process.wait.side_effect = [problem, 33]
            process.poll.side_effect = [None, 33]

        def build_gate(**kwargs):
            self.assertEqual(b"", (state / "serial.log").read_bytes())
            self.assertFalse(json.loads((state / "result.json").read_text())["passed"])
            self.assertEqual({"test": True, "stage": "p1", "output": root / runner.STATE_DIR / "normal/build"}, kwargs)
            if mode == "build-error":
                raise RuntimeError("deliberate build failure")
            return esp

        def launch(*args, **kwargs):
            self.assertEqual(b"", (state / "serial.log").read_bytes())
            (state / "serial.log").write_bytes(capture(case))
            return process

        with mock.patch.object(runner, "ROOT", root), mock.patch.object(runner, "build", side_effect=build_gate) as builder, \
                mock.patch.object(runner, "qemu_command", return_value=["qemu", str(esp)]) as command, \
                mock.patch.object(runner.subprocess, "Popen", side_effect=launch) as popen:
            with redirect_stdout(io.StringIO()):
                result = runner.run_case(case, 1, normal_esp=esp if reuse else None)
        self.assertEqual(result, json.loads((state / "result.json").read_text()))
        return result, process, builder, command, popen

    def test_profiles_reuse_exact_esp_and_isolate_logs(self):
        for case in RAW:
            for reuse in (False, True):
                with self.subTest(case=case, reuse=reuse), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    result, _, builder, command, _ = self.run_mock(root, case=case, reuse=reuse)
                    self.assertTrue(result["passed"], result)
                    self.assertEqual(0 if reuse else 1, builder.call_count)
                    self.assertEqual(["-cpu", runner.PROFILES[case][0]], result["command"][-2:])
                    self.assertEqual(RAW[case][2], result["expected_mask"])
                    self.assertEqual(root / runner.STATE_DIR / case, command.call_args.args[1])

    def test_timeout_interrupt_exception_reap_and_fail_without_stale_success(self):
        for mode in ("timeout", "interrupt", "exception"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                result, process, _, _, _ = self.run_mock(Path(temporary), mode=mode)
                self.assertFalse(result["passed"])
                process.kill.assert_called_once()
                self.assertEqual(2, process.wait.call_count)
                self.assertEqual(mode == "timeout", result["timed_out"])
                self.assertEqual(mode == "interrupt", result["interrupted"])

    def test_build_failure_writes_failed_result_and_never_launches(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, _, _, _, popen = self.run_mock(Path(temporary), mode="build-error")
            self.assertFalse(result["passed"])
            self.assertIsNone(result["returncode"])
            popen.assert_not_called()

    def test_invalid_case_and_timeout_rejected_before_work(self):
        for timeout in (0, -1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                runner.run_case("all-features", timeout)
        with self.assertRaises(ValueError):
            runner.run_case("unknown", 1)
        with mock.patch.object(runner, "run_case") as run, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                runner.main(["--timeout", "nan"])
            run.assert_not_called()

    def test_cli_defaults_all_features_and_reuses_one_build_in_serial_order(self):
        for args, expected in (([], ["all-features"]), (["--all"], list(RAW))):
            with self.subTest(args=args), tempfile.TemporaryDirectory() as temporary:
                calls = []

                def run(case, timeout, *, normal_esp=None):
                    calls.append((case, normal_esp))
                    return {"case": case, "passed": True, "interrupted": False, "esp": "same-esp"}

                with mock.patch.object(runner, "ROOT", Path(temporary)), mock.patch.object(runner, "run_case", side_effect=run):
                    self.assertEqual(0, runner.main(args))
                self.assertEqual([(case, None if index == 0 else "same-esp") for index, case in enumerate(expected)], calls)
                self.assertTrue(json.loads((Path(temporary) / runner.STATE_DIR / "result.json").read_text())["passed"])

    def test_cli_host_exception_overwrites_aggregate_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / runner.STATE_DIR
            state.mkdir(parents=True)
            (state / "result.json").write_text('{"passed":true}')
            with mock.patch.object(runner, "ROOT", root), mock.patch.object(runner, "run_case", side_effect=RuntimeError("host failure")):
                self.assertEqual(1, runner.main(["--all"]))
            result = json.loads((state / "result.json").read_text())
            self.assertFalse(result["passed"])
            self.assertEqual("failed", result["status"])


if __name__ == "__main__":
    unittest.main()
