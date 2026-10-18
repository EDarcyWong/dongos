"""Independent target checks for typed constants and transparent type aliases."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import CompileError, compile_file, compile_source
from lang.tests.test_dongc import nasm_flags, tool

FIXTURES = Path(__file__).parent
ENTRY = FIXTURES / "declarations_probe.dg"


class DeclarationsNativeTests(unittest.TestCase):
    def test_cross_module_declaration_layouts(self):
        compiled = compile_file(ENTRY, roots=[FIXTURES])
        layouts = {entry["full_name"]: entry for entry in compiled.layout_manifest["types"]}
        packet = layouts["declarations_defs.Packet"]
        cache = layouts["declarations_probe.Cache"]
        # Hand calculated, and checked separately by C in the native probe.
        self.assertEqual((packet["size"], packet["alignment"]), (16, 4))
        self.assertEqual([field["offset"] for field in packet["fields"]], [0, 4, 8])
        self.assertEqual((cache["size"], cache["alignment"]), (16, 16))
        self.assertEqual([field["offset"] for field in cache["fields"]], [0, 1])
        self.assertEqual(compiled.manifest()["modules"], ["declarations_defs", "declarations_probe"])
        self.assertEqual(compiled.manifest()["sources"], ["declarations_defs.dg", "declarations_probe.dg"])

    def test_constant_types_mutability_and_storage_are_checked(self):
        cases = [
            ("const A:u8=256;", "E0302"),
            ("const A:i8=128;", "E0302"),
            ("const A:u8=-1;", "E0302"),
            ("const A:u8=255;const B:u8=A+1;", "E0302"),
            ("const A:bool=1;", "E0301"),
            ("const A:u8=7;fn f()u16{return A;}", "E0301"),
            ("const A:u16=7;fn f()void{A=8;}", "E0402"),
            ("let A:u16=7;", "E0601"),
        ]
        for declaration, code in cases:
            for mode in ("debug", "release"):
                with self.subTest(declaration=declaration, mode=mode):
                    with self.assertRaises(CompileError) as caught:
                        compile_source("module declarations;" + declaration, mode=mode)
                    self.assertEqual(caught.exception.code, code, caught.exception.message)

    def test_native_typed_constants_alias_memory_and_layout_expressions(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("declaration probes require NASM and a SysV-capable GCC host compiler")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    asm, obj, observer = directory / f"{mode}.asm", directory / f"{mode}.o", directory / "observer.o"
                    exe = directory / (f"{mode}.exe" if os.name == "nt" else mode)
                    asm.write_text(compile_file(ENTRY, roots=[FIXTURES], mode=mode).assembly, encoding="utf-8")
                    for inp, out in ((asm, obj), (FIXTURES / "declarations_probe.asm", observer)):
                        result = subprocess.run([nasm, "-f", "win64" if os.name == "nt" else "elf64", *nasm_flags(nasm), "-o", str(out), str(inp)], capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror", str(FIXTURES / "declarations_probe.c"), str(obj), str(observer), "-o", str(exe)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("native typed constants, transparent aliases and declaration layouts passed", result.stdout)
                    result = subprocess.run([str(exe), "bounds"], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 65, result.stdout + result.stderr)
                    self.assertIn("observed alias slice bounds panic", result.stdout)


if __name__ == "__main__":
    unittest.main()
