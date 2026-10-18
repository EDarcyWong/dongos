"""Optional supervisor controls: independent C policy and real/mock CPUID ABI."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests"
STD = ROOT / "lang" / "std"


class CpuHardeningTests(unittest.TestCase):
    def compile_probe(self, mode):
        return compile_file(FIXTURES / "hardening_probe.dg",
                            roots=[FIXTURES, ROOT / "kernel", STD], mode=mode)

    def assemble(self, nasm, source, target, fmt):
        result = subprocess.run([nasm, "-f", fmt, *nasm_flags(nasm), "-o", str(target), str(source)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_layouts_module_graph_and_elf64_coff_both_modes(self):
        nasm = tool("nasm", "NASM")
        self.assertTrue(nasm, "configured NASM required")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in ("debug", "release"):
                compiled = self.compile_probe(mode)
                self.assertEqual({"hardening_probe", "cpu.hardening", "boot.preflight", "arch.x86_64"},
                                 set(compiled.manifest()["modules"]))
                layouts = {item["full_name"]: item for item in compiled.layout_manifest["types"]}
                for name, size in (("Features", 24), ("Plan", 16), ("Report", 104)):
                    layout = layouts["cpu.hardening." + name]
                    self.assertEqual((size, 8), (layout["size"], layout["alignment"]))
                    self.assertEqual(list(range(0, size, 8)), [field["offset"] for field in layout["fields"]])
                assembly = directory / (mode + ".asm")
                assembly.write_text(compiled.assembly, encoding="utf-8")
                for fmt in ("elf64", "win64"):
                    with self.subTest(mode=mode, format=fmt):
                        self.assemble(nasm, assembly, directory / (mode + fmt + ".o"), fmt)
                        self.assemble(nasm, STD / "arch/x86_64.asm", directory / ("arch" + mode + fmt + ".o"), fmt)

    def run_native(self, mock):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        self.assertTrue(nasm and cc, "configured NASM and SysV-capable GCC required")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fmt = "win64" if os.name == "nt" else "elf64"
            for mode in ("debug", "release"):
                with self.subTest(mode=mode, mock=mock):
                    assembly = directory / (mode + ".asm")
                    assembly.write_text(self.compile_probe(mode).assembly, encoding="utf-8")
                    obj = directory / (mode + ".o")
                    self.assemble(nasm, assembly, obj, fmt)
                    objects = [str(obj)]
                    if not mock:
                        arch = directory / (mode + "arch.o")
                        self.assemble(nasm, STD / "arch/x86_64.asm", arch, fmt)
                        objects.append(str(arch))
                    executable = directory / (mode + (".exe" if os.name == "nt" else ""))
                    flags = ["-DHARDENING_MOCK_CPUID=1"] if mock else []
                    if os.name != "nt":
                        flags.append("-no-pie")
                    # Exercise both Dong modes with the same C reference code.
                    # Bundled TDM GCC's -O0 mixed-ABI prologue pass can ICE on
                    # the guarded mock loop; -O2 matches the capability probe.
                    result = subprocess.run([cc, "-std=c11", "-O2",
                                             "-Wall", "-Wextra", "-Werror", *flags,
                                             str(FIXTURES / "hardening_probe.c"), *objects, "-o", str(executable)],
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("hardening native checks passed", result.stdout)
                    self.assertIn("hardening exact CPUID sequence passed" if mock else "hardening independent CPUID passed",
                                  result.stdout)

    def test_independent_c_policy_and_actual_cpuid(self):
        self.run_native(False)

    def test_missing_leaves_and_mock_cpuid_query_sequence(self):
        self.run_native(True)


if __name__ == "__main__":
    unittest.main()
