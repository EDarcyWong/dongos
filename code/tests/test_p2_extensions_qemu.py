"""Boot the P2 extension probe under QEMU in both modes; wrong mm sources must fail.

Wraps tests/run_p2_extensions_qemu.py: the good build must exit 33 with every
step marker (2 MiB leaf, split with a hardware-visible 4 KiB replacement,
merge + reclaim, cross-alias W^X ending in a real call of new code, PAT entry 4
WC with MTRR/effective type and migration order). Each mutant must exit 35.
"""
from __future__ import annotations
import unittest

from tools.build import ToolError, find_firmware, find_tool
from tests import run_p2_extensions_qemu as runner


class P2ExtensionsQemuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            for name, variable in (("nasm", "NASM"), ("lld-link", "LLD_LINK"), ("qemu-system-x86_64", "QEMU")):
                find_tool(name, variable)
            find_firmware(find_tool("qemu-system-x86_64", "QEMU"))
        except ToolError as error:
            raise unittest.SkipTest(f"P2 extension QEMU probe needs its toolchain: {error}")

    def test_probe_passes_in_both_modes(self):
        for mode in ("debug", "release"):
            with self.subTest(mode=mode):
                record = runner.run("good", runner.ROOT / "kernel", mode, 180.0)
                self.assertEqual(record["exit_code"], runner.PASS_EXIT, record["serial_tail"])
                self.assertTrue(all(record["markers"].values()), record["markers"])
                self.assertTrue(record["passed"])

    def test_wrong_mm_sources_fail_the_probe(self):
        for name in sorted(runner.MUTANTS):
            for mode in ("debug", "release"):
                with self.subTest(mutant=name, mode=mode):
                    record = runner.run(name, runner.mutant_root(name), mode, 180.0)
                    self.assertEqual(record["exit_code"], runner.FAIL_EXIT, record["serial_tail"])
                    self.assertFalse(record["passed"])


if __name__ == "__main__":
    unittest.main()
