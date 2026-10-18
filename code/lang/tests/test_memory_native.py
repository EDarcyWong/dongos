"""Independent C and hand-written assembly checks for the L1 memory backend."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import compile_source
from lang.tests.test_dongc import nasm_flags, tool


FIXTURES = Path(__file__).parent


def memory_source():
    source = (FIXTURES / "memory_probe.dg").read_text(encoding="utf-8")
    for sign in "ui":
        for width in (8, 16, 32, 64):
            typ = f"{sign}{width}"
            for name, operator in (("add", "+"), ("sub", "-"), ("mul", "*"), ("div", "/"), ("mod", "%")):
                source += f'\nexport("dg_{typ}_{name}") fn {typ}_{name}(a:{typ},b:{typ}){typ}{{return a{operator}b;}}'
            for name, operator in (("shl", "<<"), ("shr", ">>")):
                source += f'\nexport("dg_{typ}_{name}") fn {typ}_{name}(a:{typ},b:usize){typ}{{return a{operator}b;}}'
            source += f'\nexport("dg_{typ}_neg") fn {typ}_neg(a:{typ}){typ}{{return -a;}}'
            source += f'\nexport("dg_{typ}_lt") fn {typ}_lt(a:{typ},b:{typ})bool{{return a<b;}}'
            source += f'\nexport("dg_{typ}_cast") fn {typ}_cast(a:u64){typ}{{return a as {typ};}}'
            wide = "i64" if sign == "i" else "u64"
            source += f'\nexport("dg_{typ}_widen") fn {typ}_widen(a:{typ}){wide}{{return a as {wide};}}'
    return source


class MemoryNativeTests(unittest.TestCase):
    def test_large_pointer_object_assembly(self):
        # No giant local or allocation: the backend must still encode legal
        # offsets and copy counts of objects referred to by caller pointers.
        text = """module large;
            struct Huge { pad:[2147483648]u8,last:u8 }
            fn field(p:*const Huge)u8 {unsafe{return (*p).last;}}
            fn copy(p:*[4294967297]u8,q:*const [4294967297]u8)void {unsafe{*p=*q;}}
        """
        compiled = compile_source(text)
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("large pointer object encoding requires NASM")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asm, obj = directory / "large.asm", directory / "large.o"
            asm.write_text(compiled.assembly, encoding="utf-8")
            result = subprocess.run([nasm, "-f", "elf64", *nasm_flags(nasm), "-o", str(obj), str(asm)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)

    def test_python_layout_expectations(self):
        compiled = compile_source(memory_source(), "memory_probe.dg")
        layouts = {item["name"]: item for item in compiled.layout_manifest["types"]}
        # Hand-calculated values, independent of TypeSystem and C compilation.
        expected = {"Natural": (16, 4, [0, 4, 8, 10]), "Packed": (7, 1, [0, 1, 5]),
                    "Aligned": (16, 16, [0, 8])}
        for name, (size, alignment, offsets) in expected.items():
            with self.subTest(name=name):
                layout = layouts[name]
                self.assertEqual((size, alignment), (layout["size"], layout["alignment"]))
                self.assertEqual(offsets, [field["offset"] for field in layout["fields"]])
        self.assertEqual(["__dong_panic"], compiled.runtime_symbols)
        self.assertNotIn("extern memcpy", compiled.assembly)
        self.assertNotIn("[rsp-", compiled.assembly)

    def test_native_memory_widths_layout_and_panics(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native memory checks require NASM and a SysV-capable GCC host compiler")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    asm, obj, abi = directory / f"{mode}.asm", directory / f"{mode}.o", directory / "memory_abi.o"
                    exe = directory / (f"{mode}.exe" if os.name == "nt" else mode)
                    asm.write_text(compile_source(memory_source(), "memory_probe.dg", mode=mode).assembly, encoding="utf-8")
                    for inp, out in ((asm, obj), (FIXTURES / "memory_probe.asm", abi)):
                        result = subprocess.run([nasm, "-f", "win64" if os.name == "nt" else "elf64", *nasm_flags(nasm), "-o", str(out), str(inp)], capture_output=True, text=True)
                        self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror",
                                             "-DDEBUG_MODE=" + ("1" if mode == "debug" else "0"),
                                             str(FIXTURES / "memory_probe.c"), str(obj), str(abi), "-o", str(exe)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("native memory, narrow integer and layout probes passed", result.stdout)
                    cases = {"bounds": 1, "boundsmax": 1, "address_order": 1, "nested_bounds": 1}
                    for sign in "ui":
                        for width in (8, 16, 32, 64):
                            prefix = f"{sign}{width}_"
                            cases.update({prefix + name: kind for name, kind in (("zero", 3), ("modzero", 3), ("shift", 4), ("shiftmax", 4))})
                            if sign == "i":
                                cases.update({prefix + "divoverflow": 5, prefix + "modoverflow": 5})
                            if mode == "debug":
                                cases.update({prefix + name: 2 for name in ("add", "sub", "mul", "neg")})
                    for name, kind in cases.items():
                        with self.subTest(mode=mode, panic=name):
                            result = subprocess.run([str(exe), name], capture_output=True, text=True, timeout=10)
                            self.assertEqual(64 + kind, result.returncode, result.stdout + result.stderr)
                            self.assertIn(f"observed panic {kind}", result.stdout)


if __name__ == "__main__":
    unittest.main()
