"""Independent executable checks for the rest of the L1 compiler contract."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool


FIXTURES = Path(__file__).parent


class RemainingL1NativeTests(unittest.TestCase):
    def assemble(self, nasm, source, target, object_format):
        result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(target), str(source)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_layouts_and_both_object_formats(self):
        compiled = compile_file(FIXTURES / "l1_probe.dg", roots=[FIXTURES])
        layouts = {item["full_name"]: item for item in compiled.layout_manifest["types"]}
        self.assertEqual((layouts["l1_defs.Flag"]["size"], layouts["l1_defs.Flag"]["alignment"]), (8,8))
        self.assertEqual((layouts["l1_defs.Event"]["size"], layouts["l1_defs.Event"]["alignment"]), (16,8))
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("object validation requires NASM")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "l1.asm"
            source.write_text(compiled.assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    self.assemble(nasm, source, directory / (object_format + ".o"), object_format)

    def test_native_remaining_features_debug_release_and_noreturn(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native L1 execution requires NASM and GCC")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    source, obj = directory / (mode + ".asm"), directory / (mode + ".o")
                    abi = directory / "abi.o"
                    executable = directory / (mode + (".exe" if os.name == "nt" else ""))
                    compiled = compile_file(FIXTURES / "l1_probe.dg", roots=[FIXTURES], mode=mode)
                    source.write_text(compiled.assembly, encoding="utf-8")
                    object_format = "win64" if os.name == "nt" else "elf64"
                    self.assemble(nasm, source, obj, object_format)
                    self.assemble(nasm, FIXTURES / "l1_probe.asm", abi, object_format)
                    command = [cc, "-std=c11", "-O0", "-Wall", "-Wextra", "-Werror", str(FIXTURES / "l1_probe.c"), str(obj), str(abi), "-o", str(executable)]
                    result = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("remaining L1 flow, cleanup, tagged values, methods and pair ABI passed", result.stdout)
                    result = subprocess.run([str(executable), "noreturn"], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
                    result = subprocess.run([str(executable), "panic"], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 91, result.stdout + result.stderr)
                    self.assertIn("L1 panic kind=1 trace=1", result.stderr)


if __name__ == "__main__":
    unittest.main()
