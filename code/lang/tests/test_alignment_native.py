"""Independent native checks for realigned local and temporary stack objects."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import compile_source
from lang.tests.test_dongc import nasm_flags, tool


FIXTURES = Path(__file__).parent


class AlignmentNativeTests(unittest.TestCase):
    def test_independent_layout_expectations(self):
        result = compile_source((FIXTURES / "alignment_probe.dg").read_text(encoding="utf-8"), "alignment_probe.dg")
        layouts = {entry["name"]: entry for entry in result.layout_manifest["types"]}
        for alignment in (32, 64, 256, 1024):
            with self.subTest(alignment=alignment):
                entry = layouts[f"A{alignment}"]
                self.assertEqual((alignment, alignment), (entry["size"], entry["alignment"]))
        self.assertEqual((192, 64), (layouts["Outer"]["size"], layouts["Outer"]["alignment"]))
        self.assertEqual([0, 64], [field["offset"] for field in layouts["Outer"]["fields"]])
        self.assertNotRegex(result.assembly.lower(), r"\b(?:xmm|ymm|zmm)[0-9]+\b")
        self.assertNotIn("[rsp-", result.assembly)
        self.assertEqual(["__dong_panic"], result.runtime_symbols)

    def test_native_alignment_temporaries_calls_and_panics(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("aligned stack verification requires NASM and SysV-capable GCC")
        source = (FIXTURES / "alignment_probe.dg").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    asm, obj, observer = directory / f"{mode}.asm", directory / f"{mode}.o", directory / "observer.o"
                    exe = directory / (f"{mode}.exe" if os.name == "nt" else mode)
                    asm.write_text(compile_source(source, "alignment_probe.dg", mode=mode).assembly, encoding="utf-8")
                    for inp, out in ((asm, obj), (FIXTURES / "alignment_probe.asm", observer)):
                        result = subprocess.run([nasm, "-f", "win64" if os.name == "nt" else "elf64", *nasm_flags(nasm), "-o", str(out), str(inp)], capture_output=True, text=True)
                        self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror", str(FIXTURES / "alignment_probe.c"), str(obj), str(observer), "-o", str(exe)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("native aligned locals, temporaries and ABI probes passed", result.stdout)
                    cases = {"bounds": 1, "early_bounds": 1}
                    if mode == "debug":
                        cases["overflow"] = 2
                    for case, kind in cases.items():
                        with self.subTest(mode=mode, panic=case):
                            result = subprocess.run([str(exe), case], capture_output=True, text=True, timeout=10)
                            self.assertEqual(64 + kind, result.returncode, result.stdout + result.stderr)
                            self.assertIn(f"observed aligned panic {kind}", result.stdout)


if __name__ == "__main__":
    unittest.main()
