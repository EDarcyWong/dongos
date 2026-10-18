"""The boot gate must reject crashes, timeouts, stale or partial success text."""

import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("run_qemu", Path(__file__).with_name("run_qemu.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class BootGateTests(unittest.TestCase):
    serial = runner.HELLO + b"\r\n" + runner.PASS + b"\r\n"

    def test_success(self):
        self.assertEqual(runner.check_result(33, self.serial, False), [])

    def test_crash_after_printing_success_is_failure(self):
        self.assertTrue(runner.check_result(1, self.serial, False))

    def test_timeout_with_success_text_is_failure(self):
        self.assertTrue(runner.check_result(33, self.serial, True))

    def test_missing_hello_is_failure(self):
        self.assertTrue(runner.check_result(33, runner.PASS + b"\r\n", False))

    def test_partial_or_embedded_marker_is_failure(self):
        self.assertTrue(runner.check_result(33, runner.HELLO + b"\r\nx" + runner.PASS + b"\r\n", False))

    def test_out_of_order_marker_is_failure(self):
        self.assertTrue(runner.check_result(33, runner.PASS + b"\r\n" + runner.HELLO + b"\r\n", False))

    def test_incomplete_final_line_is_failure(self):
        self.assertTrue(runner.check_result(33, self.serial.rstrip(b"\r\n"), False))

    def test_p1_complete_chain(self):
        serial = b"\r\n".join(runner.P1_MARKERS) + b"\r\n"
        self.assertEqual(runner.check_result(33, serial, False, "p1"), [])

    def test_p1_rejects_missing_ebs_proof(self):
        serial = b"\r\n".join(m for m in runner.P1_MARKERS if m != b"DONGOS_P1_EBS_OK") + b"\r\n"
        self.assertTrue(runner.check_result(33, serial, False, "p1"))

    def test_p1_requires_activation_proof_in_order(self):
        activation = b"DONGOS_P2_ACTIVATION_READY"
        serial = b"\r\n".join(runner.P1_MARKERS) + b"\r\n"
        variants = {
            "missing": serial.replace(activation + b"\r\n", b""),
            "duplicate": serial.replace(activation, activation + b"\r\n" + activation),
            "before_preflight": serial.replace(b"DONGOS_P2_PREFLIGHT_READY\r\n" + activation,
                                                activation + b"\r\nDONGOS_P2_PREFLIGHT_READY"),
            "after_mutation": serial.replace(activation + b"\r\nDONGOS_P2_MUTATION_READY",
                                              b"DONGOS_P2_MUTATION_READY\r\n" + activation),
        }
        for name, candidate in variants.items():
            with self.subTest(name=name):
                self.assertTrue(runner.check_result(33, candidate, False, "p1"))

    def test_p1_requires_mutation_lifecycle_proof_in_order(self):
        marker = b"DONGOS_P2_MUTATION_READY"
        serial = b"\r\n".join(runner.P1_MARKERS) + b"\r\n"
        for candidate in (serial.replace(marker + b"\r\n", b""),
                          serial.replace(marker, marker + b"\r\n" + marker),
                          serial.replace(b"DONGOS_P2_ACTIVATION_READY\r\n" + marker,
                                         marker + b"\r\nDONGOS_P2_ACTIVATION_READY"),
                          serial.replace(marker + b"\r\nDONGOS_P2_MEMORY_READY",
                                         b"DONGOS_P2_MEMORY_READY\r\n" + marker)):
            self.assertTrue(runner.check_result(33, candidate, False, "p1"))

    def test_rejected_image_must_not_reach_kernel(self):
        marker = runner.FAILURE_CASES["tamper"]
        self.assertTrue(runner.check_result(35, marker + b"\r\nDONGOS_P1_PASS\r\n", False, "p1", marker))

    def test_rejection_requires_start_and_exact_failure(self):
        marker = runner.FAILURE_CASES["tamper"]
        self.assertTrue(runner.check_result(35, marker + b"\r\n", False, "p1", marker))
        serial = runner.P1_MARKERS[0] + b"\r\n" + marker + b"\r\n"
        self.assertEqual(runner.check_result(35, serial, False, "p1", marker), [])
        self.assertTrue(runner.check_result(35, serial + b"DONGOS_OTHER_FAIL\r\n", False, "p1", marker))


if __name__ == "__main__":
    unittest.main()
