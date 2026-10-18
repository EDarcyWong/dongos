"""CPUID capability decoding, fail-closed detection and independent host CPUID."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent
STD = ROOT / "lang" / "std"


class CpuCapabilitiesTests(unittest.TestCase):
    def compile_probe(self, mode):
        return compile_file(
            FIXTURES / "cpu_capabilities_probe.dg",
            roots=[FIXTURES, ROOT / "kernel", STD], mode=mode,
        )

    def assemble(self, nasm, source, target, object_format):
        result = subprocess.run(
            [nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(target), str(source)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_layout_module_graph_and_elf64_coff_in_both_modes(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("ELF64/COFF assembly requires NASM")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in ("debug", "release"):
                compiled = self.compile_probe(mode)
                self.assertEqual(
                    {"arch.x86_64", "cpu.capability_errors", "cpu.capabilities", "cpu_capabilities_probe"},
                    set(compiled.manifest()["modules"]),
                )
                layouts = {item["full_name"]: item for item in compiled.layout_manifest["types"]}
                capabilities = layouts["cpu.capabilities.Capabilities"]
                self.assertEqual((16, 8), (capabilities["size"], capabilities["alignment"]))
                self.assertEqual([0, 8], [field["offset"] for field in capabilities["fields"]])
                cpuid = layouts["arch.x86_64.CpuId"]
                self.assertEqual((16, 4), (cpuid["size"], cpuid["alignment"]))
                self.assertEqual([0, 4, 8, 12], [field["offset"] for field in cpuid["fields"]])
                assembly = directory / (mode + ".asm")
                assembly.write_text(compiled.assembly, encoding="utf-8")
                for object_format in ("elf64", "win64"):
                    with self.subTest(mode=mode, format=object_format):
                        self.assemble(nasm, assembly, directory / (mode + object_format + ".o"), object_format)
                        self.assemble(nasm, STD / "arch" / "x86_64.asm",
                                      directory / ("arch-" + mode + object_format + ".o"), object_format)

    def run_native(self, mock):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native capability probes require NASM and a SysV-capable GCC")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            object_format = "win64" if os.name == "nt" else "elf64"
            for mode in ("debug", "release"):
                with self.subTest(mode=mode, mock=mock):
                    assembly, obj = directory / (mode + ".asm"), directory / (mode + ".o")
                    assembly.write_text(self.compile_probe(mode).assembly, encoding="utf-8")
                    self.assemble(nasm, assembly, obj, object_format)
                    objects = [str(obj)]
                    if not mock:
                        arch_obj = directory / (mode + "-arch.o")
                        self.assemble(nasm, STD / "arch" / "x86_64.asm", arch_obj, object_format)
                        objects.append(str(arch_obj))
                    executable = directory / (mode + (".exe" if os.name == "nt" else ""))
                    flags = ["-DCPU_CAPABILITIES_MOCK_CPUID=1"] if mock else []
                    if os.name != "nt":
                        flags.append("-no-pie")
                    result = subprocess.run(
                        [cc, "-std=c11", "-O2", "-D__USE_MINGW_ANSI_STDIO=1", "-Wall", "-Wextra", "-Werror",
                         *flags, str(FIXTURES / "cpu_capabilities_probe.c"), *objects, "-o", str(executable)],
                        capture_output=True, text=True, timeout=30,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    expected = "CPU capability mock probe ok" if mock else "CPU capability independent CPUID probe ok"
                    self.assertIn(expected, result.stdout)

    def test_pure_decode_and_independent_actual_cpuid(self):
        self.run_native(mock=False)

    def test_detect_missing_leaves_invalid_width_and_exact_query_sequence(self):
        self.run_native(mock=True)


if __name__ == "__main__":
    unittest.main()
