"""Independent cache stage, ABI, fault and host lifecycle gates; no real guest."""
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


runner = load("run_cache_qemu", "run_cache_qemu.py")
hard = load("cache_hardening_fixture", "test_hardening_qemu_result.py")
old = hard.old
SYMBOLS = dict(old.SYMBOLS, object_memory_report_size=192,
               object_memory_test_expected_rip=old.K + 0x1380,
               object_memory_test_mid_return=old.K + 0x1320,
               object_memory_test_inject_return=old.K + 0x1300)


def cache_lines(case="all-features", **changes):
    profile = "all-features" if case == "cache-unmap" else case
    values = dict(zip(runner.FIELDS, (0x800000, 0xffffb00000001000, 0x850000, 0x850000,
                                     48, 64, 64, 64, 0x02000007, 0x020d0001,
                                     0xffffb00000001440, 944, 943, 944, 12, 15, 12,
                                     2, 2, 6, 472576, 1023, 0x620 | hard.RAW[profile][2], 2)))
    values.update(changes)
    return [f"cache_{name}=0x{values[name]:016x}".encode() for name in runner.FIELDS]


def panic_lines():
    changes = {"rax": 0xffffb00000001000, "cr2": 0xffffb00000001000,
               "rip": SYMBOLS["object_memory_test_expected_rip"],
               "frame_symbol": SYMBOLS["object_memory_test_expected_rip"],
               "frame_00": SYMBOLS["object_memory_test_expected_rip"],
               "frame_01": SYMBOLS["object_memory_test_mid_return"],
               "frame_02": SYMBOLS["object_memory_test_inject_return"]}
    lines = []
    for line in old.activation_panic("tlb-unmap", SYMBOLS):
        name = line.split(b"=", 1)[0].decode().removeprefix("panic_")
        lines.append(f"panic_{name}=0x{changes[name]:016x}".encode() if name in changes else line)
    return lines


def capture(case="all-features", **changes):
    profile = "all-features" if case == "cache-unmap" else case
    base = hard.capture(profile)
    block = b"\r\n".join([*cache_lines(case, **changes), runner.READY]) + b"\r\n"
    serial = base.replace(runner.memory.MUTATION_READY + b"\r\n", runner.memory.MUTATION_READY + b"\r\n" + block)
    if case == "cache-unmap":
        serial = serial.replace(runner.memory.READY + b"\r\n" + runner.memory.PASS + b"\r\n",
                                b"\r\n".join([runner.INJECT, runner.memory.PANIC, *panic_lines()]) + b"\r\n")
    return serial


def layout_manifest():
    layout = hard.layout_manifest()
    layout["types"].append({"full_name": "boot.object_memory.Report", "size": 192, "alignment": 8,
                            "fields": [{"name": name, "offset": i * 8} for i, name in enumerate(runner.FIELDS)]})
    return layout


class CacheGateTests(unittest.TestCase):
    def check(self, serial=None, *, case="all-features", code=None, timeout=False, symbols=SYMBOLS):
        return runner.check_result((37 if case == "cache-unmap" else 33) if code is None else code,
                                   capture(case) if serial is None else serial, timeout, case, symbols)

    def test_independent_contract_all_profiles_and_real_fault_pass(self):
        self.assertEqual(("all-features", "no-features", "cache-unmap"), runner.CASES)
        self.assertEqual(("root", "virtual", "physical", "reused_physical", "object_size", "alignment",
                          "capacity", "allocated", "oom_error", "busy_error", "reused_object", "free_before",
                          "free_held", "free_after", "tables_before", "tables_peak", "tables_after",
                          "invlpg_count", "reload_count", "retired_tables", "checksum", "steps", "cr4", "rflags"),
                         runner.FIELDS)
        self.assertEqual(Path("build/test/cache-lifecycle/qemu"), runner.STATE_DIR)
        self.assertEqual(472576, runner.CHECKSUM)
        self.assertEqual(0xffffb00000001000, runner.VIRTUAL)
        for case in runner.CASES:
            with self.subTest(case=case):
                self.assertEqual([], self.check(case=case))
                parsed = runner.parse_result(capture(case), case=case, symbols=SYMBOLS)
                self.assertTrue(parsed["passed"])
                self.assertEqual(38, len(parsed["hardening"]["memory"]["fields"]))
                self.assertEqual(18, len(parsed["hardening"]["memory"]["mutation"]))
                self.assertEqual(case == "cache-unmap", bool(parsed["panic"]))

    def test_each_field_required_unique_known_ordered_and_semantic(self):
        for name, line in zip(runner.FIELDS, cache_lines()):
            with self.subTest(field=name):
                self.assertTrue(self.check(capture().replace(line + b"\r\n", b"")))
                self.assertTrue(self.check(capture().replace(line, line + b"\r\n" + line)))
                self.assertTrue(self.check(capture().replace(line, line.replace(b"cache_", b"cache_other_"))))
                value = int(line.split(b"0x")[1], 16)
                self.assertTrue(self.check(capture(**{name: 0 if name == "rflags" else value ^ 1})))
        a, b = cache_lines()[:2]
        self.assertTrue(self.check(capture().replace(a + b"\r\n" + b, b + b"\r\n" + a)))

    def test_format_stage_marker_interruption_and_exclusive_placement(self):
        line = cache_lines()[0]
        for bad in (line.upper(), b"X" + line, line + b" ", line.replace(b"0x", b"0X"), b"cache_root=0x1"):
            self.assertTrue(self.check(capture().replace(line, bad)))
        for serial in (capture()[:-1], capture().replace(runner.READY, b""),
                       capture().replace(runner.READY, b"X" + runner.READY),
                       capture().replace(runner.READY, runner.READY + b"\r\n" + runner.READY),
                       capture().replace(cache_lines()[3], b"interrupted\r\n" + cache_lines()[3]),
                       capture().replace(runner.READY, runner.READY + b"\r\nnoise"),
                       capture() + b"trailing noise\r\n",
                       capture().replace(runner.memory.MUTATION_READY, b"DONGOS_UNKNOWN\r\n" + runner.memory.MUTATION_READY)):
            self.assertTrue(self.check(serial))
        block = b"\r\n".join([*cache_lines(), runner.READY]) + b"\r\n"
        moved = capture().replace(block, b"").replace(runner.memory.ACTIVATION_READY + b"\r\n",
                                                    runner.memory.ACTIVATION_READY + b"\r\n" + block)
        self.assertTrue(self.check(moved))

    def test_page_ownership_reuse_accounting_and_preserved_controls(self):
        for physical in (0, 0x850001, 0x7ff000, 0xc00000, 0x800000, 0x840000):
            self.assertTrue(self.check(capture(physical=physical, reused_physical=physical)))
        self.assertTrue(self.check(capture(reused_physical=0x851000)))
        self.assertTrue(self.check(capture("no-features")))
        self.assertTrue(self.check(capture(), case="no-features"))
        for flags in (0, 0x202, 0x402, 0x20002, 0x40002):
            self.assertTrue(self.check(capture(rflags=flags)))
        self.assertEqual([], self.check(capture(rflags=0x8d7)))
        self.assertTrue(self.check(symbols={k: v for k, v in SYMBOLS.items() if k != runner.REPORT_SIZE}))

    def test_old_memory_hardening_and_mutation_semantics_remain_required(self):
        for before, after in ((b"memory_free_pages=0x00000000000003b0", b"memory_free_pages=0x00000000000003b1"),
                              (b"hardening_cr4_after=0x0000000000300e20", b"hardening_cr4_after=0x0000000000000620"),
                              (b"mutation_invlpg_count=0x0000000000000005", b"mutation_invlpg_count=0x0000000000000004")):
            self.assertIn(before, capture())
            self.assertTrue(self.check(capture().replace(before, after)))

    def test_old_memory_gate_only_projects_complete_optional_normal_structure(self):
        # Dedicated cache semantics reject this while the original memory gate
        # deliberately checks only the new optional stage's strict structure.
        serial = capture(object_size=1)
        self.assertTrue(runner.memory.parse_memory_result(serial, symbols=SYMBOLS)["passed"])
        self.assertTrue(self.check(serial))
        for line in cache_lines():
            self.assertFalse(runner.memory.parse_memory_result(capture().replace(line + b"\r\n", b""), symbols=SYMBOLS)["passed"])
        first, second = cache_lines()[:2]
        for serial in (capture().replace(first, first + b"\r\n" + first),
                       capture().replace(first, b"X" + first),
                       capture().replace(first, first.upper()),
                       capture().replace(first + b"\r\n" + second, second + b"\r\n" + first),
                       capture().replace(second, b"noise\r\n" + second),
                       capture().replace(runner.READY, runner.READY + b"\r\n" + runner.READY)):
            self.assertFalse(runner.memory.parse_memory_result(serial, symbols=SYMBOLS)["passed"])
        self.assertFalse(runner.memory.parse_memory_result(capture("cache-unmap"), case="tlb-unmap", symbols=SYMBOLS)["passed"])
        self.assertTrue(runner.memory.parse_memory_result(old.capture(), symbols=SYMBOLS)["passed"])

    def test_fault_seed_context_frames_flags_and_target_are_independent(self):
        serial = capture("cache-unmap")
        parsed = runner.parse_result(serial, case="cache-unmap", symbols=SYMBOLS)
        for name, value in parsed["panic"].items():
            if name == "stack":
                replacement = b"panic_stack=OTHER"
                old_line = b"panic_stack=EXCEPTION"
            else:
                old_line = f"panic_{name}=0x{value:016x}".encode()
                changed = value & ~2 if name == "rflags" else value ^ 1
                replacement = f"panic_{name}=0x{changed:016x}".encode()
            with self.subTest(field=name):
                self.assertTrue(self.check(serial.replace(old_line, replacement), case="cache-unmap"))
                self.assertTrue(self.check(serial.replace(old_line + b"\r\n", b""), case="cache-unmap"))
        for name, value in (("context", old.K + 0x23000 - 176), ("rflags", 0x40402),
                            ("rflags", 0x602), ("rsp", runner.memory.STACK_BOTTOM - 8)):
            old_value = parsed["panic"][name]
            self.assertTrue(self.check(serial.replace(f"panic_{name}=0x{old_value:016x}".encode(),
                                                      f"panic_{name}=0x{value:016x}".encode()), case="cache-unmap"))
        for symbol in runner.FAULT_SYMBOLS:
            self.assertTrue(self.check(case="cache-unmap", symbols={k: v for k, v in SYMBOLS.items() if k != symbol}))
        for data in (serial.replace(runner.INJECT, b""), serial + b"noise\r\n",
                     serial.replace(runner.memory.PANIC, runner.memory.PANIC + b"\r\nnoise")):
            self.assertTrue(self.check(data, case="cache-unmap"))

    def test_exit_timeout_unknown_case_and_normal_fault_separation(self):
        self.assertTrue(self.check(code=37))
        self.assertTrue(runner.check_result(33, capture("cache-unmap"), False, "cache-unmap", SYMBOLS))
        self.assertTrue(self.check(timeout=True))
        self.assertTrue(self.check(capture("cache-unmap")))
        self.assertTrue(self.check(capture(), case="cache-unmap"))
        self.assertFalse(runner.parse_result(capture(), case="unknown", symbols=SYMBOLS)["passed"])

    def test_exact_new_report_abi_and_fault_symbols(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.elf"
            path.write_bytes(old.symbol_elf(SYMBOLS))
            manifest_path = path.with_name("dong_layout.json")
            manifest_path.write_text(json.dumps(layout_manifest()))
            self.assertEqual(192, runner.read_validation_symbols(path, case="cache-unmap")[runner.REPORT_SIZE])
            for change in ("missing", "duplicate", "size", "alignment", "name", "offset", "order"):
                layout = layout_manifest()
                report = layout["types"][-1]
                if change == "missing":
                    layout["types"].pop()
                elif change == "duplicate":
                    layout["types"].append(dict(report))
                elif change in ("size", "alignment"):
                    report[change] += 8
                elif change in ("name", "offset"):
                    report["fields"][-1][change] = "wrong" if change == "name" else 0
                else:
                    report["fields"][:2] = reversed(report["fields"][:2])
                manifest_path.write_text(json.dumps(layout))
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "object-memory Report"):
                    runner.read_validation_symbols(path)
            manifest_path.write_text(json.dumps(layout_manifest()))
            missing = dict(SYMBOLS)
            del missing["object_memory_test_expected_rip"]
            path.write_bytes(old.symbol_elf(missing))
            with self.assertRaisesRegex(ValueError, "cache fault ELF"):
                runner.read_validation_symbols(path, case="cache-unmap")


class CacheLifecycleTests(unittest.TestCase):
    def run_mock(self, root, *, case="all-features", mode="success", reuse=False):
        state = root / runner.STATE_DIR / case
        state.mkdir(parents=True)
        (state / "serial.log").write_bytes(b"STALE_SUCCESS")
        (state / "result.json").write_text('{"passed":true}')
        build_dir = state / "build" if case == "cache-unmap" else root / runner.STATE_DIR / "normal/build"
        esp = build_dir / "esp"
        esp.mkdir(parents=True)
        (build_dir / "kernel.elf").write_bytes(old.symbol_elf(SYMBOLS))
        (build_dir / "dong_layout.json").write_text(json.dumps(layout_manifest()))
        process = mock.Mock()
        code = 37 if case == "cache-unmap" else 33
        process.returncode = code
        process.poll.return_value = code
        process.wait.return_value = code
        if mode in ("timeout", "interrupt", "exception"):
            problem = subprocess.TimeoutExpired("qemu", 1) if mode == "timeout" else KeyboardInterrupt() if mode == "interrupt" else RuntimeError("host failure")
            process.wait.side_effect = [problem, code]
            process.poll.side_effect = [None, code]

        def build_gate(**kwargs):
            self.assertEqual(b"", (state / "serial.log").read_bytes())
            self.assertFalse(json.loads((state / "result.json").read_text())["passed"])
            expected = {"test": True, "stage": "p1", "output": build_dir}
            if case == "cache-unmap":
                expected["memory_case"] = case
            self.assertEqual(expected, kwargs)
            if mode == "build-error":
                raise RuntimeError("build failed")
            return esp

        def launch(*args, **kwargs):
            self.assertEqual(b"", (state / "serial.log").read_bytes())
            (state / "serial.log").write_bytes(capture(case))
            return process

        with mock.patch.object(runner, "ROOT", root), mock.patch.object(runner, "build", side_effect=build_gate) as builder, \
                mock.patch.object(runner, "qemu_command", return_value=["qemu", str(esp)]) as command, \
                mock.patch.object(runner.subprocess, "Popen", side_effect=launch) as popen, redirect_stdout(io.StringIO()):
            result = runner.run_case(case, 1, normal_esp=esp if reuse else None)
        self.assertEqual(result, json.loads((state / "result.json").read_text()))
        return result, process, builder, command, popen

    def test_profiles_reuse_normal_image_but_fault_always_builds_own_image(self):
        for case in runner.CASES:
            for reuse in (False, True):
                with self.subTest(case=case, reuse=reuse), tempfile.TemporaryDirectory() as temporary:
                    result, _, builder, command, _ = self.run_mock(Path(temporary), case=case, reuse=reuse)
                    self.assertTrue(result["passed"], result)
                    self.assertEqual(0 if reuse and case != "cache-unmap" else 1, builder.call_count)
                    profile = "all-features" if case == "cache-unmap" else case
                    self.assertEqual(["-cpu", runner.PROFILES[profile][0]], result["command"][-2:])
                    self.assertEqual(Path(temporary) / runner.STATE_DIR / case, command.call_args.args[1])

    def test_timeout_interrupt_exception_reap_and_discard_stale_success(self):
        for mode in ("timeout", "interrupt", "exception"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                result, process, _, _, _ = self.run_mock(Path(temporary), mode=mode)
                self.assertFalse(result["passed"])
                process.kill.assert_called_once()
                self.assertEqual(2, process.wait.call_count)
                self.assertEqual(mode == "timeout", result["timed_out"])
                self.assertEqual(mode == "interrupt", result["interrupted"])

    def test_build_failure_never_launches_and_persists_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, _, _, _, popen = self.run_mock(Path(temporary), mode="build-error")
            self.assertFalse(result["passed"])
            self.assertIsNone(result["returncode"])
            popen.assert_not_called()

    def test_unknown_case_or_invalid_timeout_has_no_side_effect(self):
        for timeout in (0, -1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                runner.run_case("all-features", timeout)
        with self.assertRaises(ValueError):
            runner.run_case("unknown", 1)
        with mock.patch.object(runner, "run_case") as run, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                runner.main(["--timeout", "nan"])
            run.assert_not_called()

    def test_cli_serial_order_reuse_and_aggregate_failure(self):
        for args, expected in (([], ["all-features"]), (["--all"], list(runner.CASES))):
            with self.subTest(args=args), tempfile.TemporaryDirectory() as temporary:
                calls = []

                def run(case, timeout, *, normal_esp=None):
                    calls.append((case, normal_esp))
                    return {"case": case, "passed": True, "interrupted": False, "esp": "same-esp"}

                with mock.patch.object(runner, "ROOT", Path(temporary)), mock.patch.object(runner, "run_case", side_effect=run):
                    self.assertEqual(0, runner.main(args))
                self.assertEqual([(case, None if i == 0 else "same-esp") for i, case in enumerate(expected)], calls)
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(runner, "ROOT", Path(temporary)), \
                mock.patch.object(runner, "run_case", side_effect=RuntimeError("host failed")):
            self.assertEqual(1, runner.main(["--all"]))
            result = json.loads((Path(temporary) / runner.STATE_DIR / "result.json").read_text())
            self.assertFalse(result["passed"])
            self.assertEqual("failed", result["status"])


if __name__ == "__main__":
    unittest.main()
