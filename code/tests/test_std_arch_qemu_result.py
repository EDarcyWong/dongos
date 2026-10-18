"""Host parsing checks for the arch.x86_64 ring-0 QEMU probe results."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

import tests.run_std_arch_qemu as runner
from tests.run_std_arch_qemu import MARKERS, EXIT_CODE, check_result


def good_serial() -> bytes:
    return b"".join(marker + b"\n" for marker in MARKERS)


class StdArchQemuResultTests(unittest.TestCase):
    def test_success_serial_passes(self):
        self.assertEqual([], check_result(EXIT_CODE, good_serial(), False))

    def test_missing_marker(self):
        errors = check_result(EXIT_CODE, b"".join(m + b"\n" for m in MARKERS[1:]), False)
        self.assertTrue(any("missing marker" in e for e in errors))

    def test_duplicate_marker(self):
        serial = MARKERS[0] + b"\n" + good_serial()
        errors = check_result(EXIT_CODE, serial, False)
        self.assertTrue(any("duplicate marker" in e for e in errors))

    def test_out_of_order_marker(self):
        serial = MARKERS[1] + b"\n" + MARKERS[0] + b"\n" + b"".join(m + b"\n" for m in MARKERS[2:])
        errors = check_result(EXIT_CODE, serial, False)
        self.assertTrue(any("out of order" in e for e in errors))

    def test_wrong_exit_code(self):
        errors = check_result(35, good_serial(), False)
        self.assertTrue(any("exit code" in e for e in errors))

    def test_timeout_reported(self):
        errors = check_result(EXIT_CODE, good_serial(), True)
        self.assertTrue(any("timed out" in e for e in errors))

    def test_fail_marker_detected(self):
        serial = good_serial() + b"DONGOS_STD_ARCH_FAIL:X\n"
        errors = check_result(EXIT_CODE, serial, False)
        self.assertTrue(any("failure" in e for e in errors))

    def test_trailing_truncated_fail_without_newline(self):
        serial = good_serial() + b"DONGOS_STD_ARCH_FAIL:TRUNCATED"
        errors = check_result(EXIT_CODE, serial, False)
        self.assertTrue(any("without a newline" in e for e in errors))

    def test_unknown_stage_marker(self):
        serial = good_serial() + b"DONGOS_STD_ARCH_EXTRA_PASS\n"
        errors = check_result(EXIT_CODE, serial, False)
        self.assertTrue(any("unknown stage" in e for e in errors))

    def test_build_failure_clears_stale_success(self):
        with mock.patch.object(runner, "build_probe", side_effect=RuntimeError("simulated build failure")):
            result = runner.run_probe("debug", timeout=1.0)
        self.assertFalse(result["passed"])
        self.assertTrue(result["errors"])
        state = runner.output_dir("debug")
        saved = json.loads((state / "result.json").read_text(encoding="utf-8"))
        self.assertFalse(saved["passed"])

    def test_timeout_kills_process(self):
        with mock.patch.object(runner, "build_probe", return_value=Path(".")), \
                mock.patch.object(runner, "qemu_command", return_value=[sys.executable, "-c", "import time; time.sleep(60)"]):
            result = runner.run_probe("debug", timeout=1.0)
        self.assertFalse(result["passed"])
        self.assertTrue(result["timed_out"])
        self.assertTrue(any("timed out" in e for e in result["errors"]))

    def test_interrupt_recovers_and_kills_process(self):
        class FakeProc:
            def __init__(self):
                self.waits = 0
                self.killed = False
            def wait(self, timeout=None):
                self.waits += 1
                if self.waits == 1:
                    raise KeyboardInterrupt
                return 1
            def kill(self):
                self.killed = True
        fake = FakeProc()
        with mock.patch.object(runner, "build_probe", return_value=Path(".")), \
                mock.patch.object(runner, "qemu_command", return_value=["true"]), \
                mock.patch.object(runner.subprocess, "Popen", return_value=fake):
            result = runner.run_probe("debug", timeout=5.0)
        self.assertFalse(result["passed"])
        self.assertTrue(fake.killed)
        self.assertTrue(any("KeyboardInterrupt" in e for e in result["errors"]))

    def test_start_failure_records_error(self):
        with mock.patch.object(runner, "build_probe", return_value=Path(".")), \
                mock.patch.object(runner, "qemu_command", return_value=["definitely-not-a-real-binary-xyz"]):
            result = runner.run_probe("debug", timeout=5.0)
        self.assertFalse(result["passed"])
        self.assertTrue(any("FileNotFoundError" in e for e in result["errors"]))

    def test_negative_runner_timeout_recovers(self):
        class FakeProc:
            def __init__(self):
                self.waits = []
                self.killed = False
            def wait(self, timeout=None):
                self.waits.append(timeout)
                if len(self.waits) == 1:
                    raise runner.subprocess.TimeoutExpired("qemu", timeout)
                return 7
            def kill(self):
                self.killed = True
        fake = FakeProc()
        with mock.patch.object(runner, "build_probe", return_value=Path(".")), \
                mock.patch.object(runner, "qemu_command", return_value=["true"]), \
                mock.patch.object(runner.subprocess, "Popen", return_value=fake):
            result = runner.run_negative_control(Path("bad.asm"), "neg-timeout", timeout=1.0)
        self.assertFalse(result["passed"])
        self.assertTrue(result["timed_out"])
        self.assertTrue(fake.killed)
        self.assertEqual([1.0, None], fake.waits)
        self.assertEqual(7, result["returncode"])
        saved = json.loads((runner.output_dir("negative-neg-timeout") / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result, saved)

    def test_negative_runner_interrupt_recovers(self):
        class FakeProc:
            def __init__(self):
                self.waits = []
                self.killed = False
            def wait(self, timeout=None):
                self.waits.append(timeout)
                if len(self.waits) == 1:
                    raise KeyboardInterrupt
                return 7
            def kill(self):
                self.killed = True
        fake = FakeProc()
        with mock.patch.object(runner, "build_probe", return_value=Path(".")), \
                mock.patch.object(runner, "qemu_command", return_value=["true"]), \
                mock.patch.object(runner.subprocess, "Popen", return_value=fake):
            result = runner.run_negative_control(Path("bad.asm"), "neg-interrupt", timeout=5.0)
        self.assertFalse(result["passed"])
        self.assertTrue(fake.killed)
        self.assertEqual([5.0, None], fake.waits)
        self.assertTrue(any("KeyboardInterrupt" in e for e in result["errors"]))
        saved = json.loads((runner.output_dir("negative-neg-interrupt") / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result, saved)

    def test_negative_runner_clears_stale_success(self):
        state = runner.output_dir("negative-neg-stale")
        state.mkdir(parents=True, exist_ok=True)
        (state / "result.json").write_text(json.dumps({"passed": True, "stale": True}), encoding="utf-8")
        (state / "serial.log").write_text("DONGOS_STD_ARCH_PASS\n", encoding="utf-8")

        def build_and_observe(*args, **kwargs):
            # at build entry the stale success must already be replaced by building/failed state
            saved = json.loads((state / "result.json").read_text(encoding="utf-8"))
            self.assertEqual({"passed": False, "status": "building"}, saved)
            self.assertEqual(b"", (state / "serial.log").read_bytes())
            raise RuntimeError("boom")

        with mock.patch.object(runner, "build_probe", side_effect=build_and_observe):
            result = runner.run_negative_control(Path("bad.asm"), "neg-stale", timeout=1.0)
        self.assertFalse(result["passed"])
        # the entry AssertionError must not masquerade as the expected build failure
        self.assertEqual(["RuntimeError: boom"], result["errors"])
        self.assertEqual(b"", (state / "serial.log").read_bytes())
        saved = json.loads((state / "result.json").read_text(encoding="utf-8"))
        self.assertFalse(saved["passed"])

    def test_panic_marker(self):
        serial = good_serial() + b"DONGOS_STD_ARCH_PANIC:3\n"
        errors = check_result(EXIT_CODE, serial, False)
        self.assertTrue(any("panic" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
