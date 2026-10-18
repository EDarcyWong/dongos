"""Independent C model checks for core.arena."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[2]
STD = ROOT / "lang" / "std"


def wrapper_source():
    return """module probe;
import core.arena as arena;
export("arena_size") fn size()usize{return sizeof(arena.Arena);}
export("arena_base_off") fn base_off()usize{return offsetof(arena.Arena,base);}
export("arena_cap_off") fn cap_off()usize{return offsetof(arena.Arena,capacity);}
export("arena_used_off") fn used_off()usize{return offsetof(arena.Arena,used);}
export("arena_init") fn init(a:*arena.Arena, storage:[]u8)bool{unsafe{return arena.init(a,storage);}}
export("arena_allocate") fn allocate(a:*arena.Arena, size:usize, alignment:usize, out:*usize)bool{unsafe{return arena.allocate(a,size,alignment,out);}}
export("arena_rewind") fn rewind(a:*arena.Arena, mark:usize)bool{unsafe{return arena.rewind(a,mark);}}
"""


C_SOURCE = (Path(__file__).parent / "std_arena_probe.c").read_text(encoding="utf-8")


class StdArenaTests(unittest.TestCase):
    def test_module_compiles_and_assembles(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("assembly checks require NASM")
        compiled = compile_file(STD / "core" / "arena.dg", roots=[STD])
        self.assertEqual(["core.arena"], compiled.manifest()["modules"])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asm = directory / "arena.asm"
            asm.write_text(compiled.assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(directory / (object_format + ".o")), str(asm)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)

    def test_native_arena(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native core.arena checks require NASM and a SysV-capable GCC host compiler")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            c_path = directory / "probe.c"
            c_path.write_text(C_SOURCE, encoding="utf-8")
            object_format = "win64" if os.name == "nt" else "elf64"
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    asm, obj = directory / (mode + ".asm"), directory / (mode + ".o")
                    exe = directory / (mode + (".exe" if os.name == "nt" else ""))
                    with tempfile.TemporaryDirectory() as roots:
                        entry = Path(roots) / "probe.dg"
                        entry.write_text(wrapper_source(), encoding="utf-8")
                        compiled = compile_file(entry, roots=[Path(roots), STD], mode=mode)
                    asm.write_text(compiled.assembly, encoding="utf-8")
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(obj), str(asm)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror", str(c_path), str(obj), "-o", str(exe)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("native core.arena probes passed", result.stdout)


    def _bad_module(self, mutation):
        source = (STD / "core" / "arena.dg").read_text(encoding="utf-8")
        mutated = mutation(source)
        self.assertNotEqual(source, mutated, "mutation must change the module")
        return mutated

    def _run_probe(self, module_source, mode, directory, label):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        root = directory / ("root-" + label + "-" + mode)
        (root / "core").mkdir(parents=True)
        (root / "core" / "arena.dg").write_text(module_source, encoding="utf-8")
        entry = root / "probe.dg"
        entry.write_text(wrapper_source(), encoding="utf-8")
        compiled = compile_file(entry, roots=[root], mode=mode)
        asm, obj = directory / ("bad-" + mode + ".asm"), directory / ("bad-" + mode + ".o")
        exe = directory / ("bad-" + mode + (".exe" if os.name == "nt" else ""))
        asm.write_text(compiled.assembly, encoding="utf-8")
        object_format = "win64" if os.name == "nt" else "elf64"
        r = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(obj), str(asm)], capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stderr)
        r = subprocess.run([cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror", str(directory / "probe.c"), str(obj), "-o", str(exe)], capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stderr)
        return subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)

    def test_negative_controls(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("negative controls require NASM and a C compiler")

        def bad_align_offsets(src):
            return src.replace(
                "        let p: usize = (current + mask) & ~mask;",
                "        let p: usize = base_addr + ((used + mask) & ~mask);")

        def bad_early_out(src):
            return src.replace(
                "pub unsafe fn allocate(arena: *Arena, size: usize, alignment: usize, out: *usize) bool {\n    unsafe {",
                "pub unsafe fn allocate(arena: *Arena, size: usize, alignment: usize, out: *usize) bool {\n    unsafe {\n        (*out) = 0;")

        cases = [
            ("bad-align-offsets", bad_align_offsets),
            ("bad-early-out-write", bad_early_out),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "probe.c").write_text(C_SOURCE, encoding="utf-8")
            for label, mutation in cases:
                module = self._bad_module(mutation)
                for mode in ("debug", "release"):
                    with self.subTest(control=label, mode=mode):
                        result = self._run_probe(module, mode, directory, label)
                        self.assertEqual(1, result.returncode, "control must be rejected: " + label + "\n" + result.stdout + result.stderr)
                        self.assertIn("check failed", result.stderr)
                        self.assertNotIn("panic", result.stderr)


if __name__ == "__main__":
    unittest.main()
