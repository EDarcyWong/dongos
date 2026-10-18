"""Independent C and assembly verification of slice values and scalar externs."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import CompileError, compile_source
from lang.dongc.compiler import compile_file
from lang.tests.test_dongc import nasm_flags, tool

FIXTURES = Path(__file__).parent


def fixtures():
    source = (FIXTURES / "slices_probe.dg").read_text(encoding="utf-8")
    declarations, checks, calls = [], [], []
    total = 0
    for position in range(9):
        prefixes = [f"a{i}:u64" for i in range(position)]
        parameters = prefixes + ["s:[]u64", "z:u64"]
        value = "+".join([f"a{i}" for i in range(position)] + ["s.len*100", "s[0]", "z*1000"])
        source += f'\nexport("dg_slice_position{position}") fn position{position}({",".join(parameters)})u64{{return {value};}}'
        args = [str(i + 1) for i in range(position)] + ["s", "9"]
        calls.append(f"position{position}({','.join(args)})")
        expected = 9411 + position * (position + 1) // 2
        total += expected
        declarations.append(f"extern uint64_t DG dg_slice_position{position}({','.join(['uint64_t'] * position + ['struct Slice', 'uint64_t'])});")
        checks.append(f"CHECK(dg_slice_position{position}({','.join(args)})=={expected});")
    source += '\nexport("dg_slice_positions") fn positions()u64{var values:[4]u64=[11,22,33,44];let s=values[..];return ' + "+".join(calls) + ";}"
    source += '\nfn scalars(a:u64,b:u64,c:u64,d:u64,e:u64,f:u64,g:u64,h:u64)u64{return a+b*2+c*3+d*4+e*5+f*6+g*7+h*8;}'
    source += '\nexport("dg_slice_scalars") fn scalar_test()u64{return scalars(1,2,3,4,5,6,7,8);}'
    c = (FIXTURES / "slices_probe.c").read_text(encoding="utf-8")
    c = c.replace("POSITION_DECLARATIONS", "\n".join(declarations)).replace("POSITION_CHECKS", "\n    ".join(checks)).replace("POSITION_TOTAL", str(total))
    return source, c


class SliceNativeTests(unittest.TestCase):
    def test_assembly_and_manifest(self):
        source, _ = fixtures()
        compiled = compile_source(source, "slices_probe.dg")
        self.assertEqual(["__dong_panic"], compiled.runtime_symbols)
        self.assertNotIn("extern $slices_unused", compiled.assembly)
        self.assertNotIn("$slices_unused:", compiled.assembly)
        self.assertNotIn("slices_unused", compiled.exports)
        self.assertIn("extern $slices_asm_win", compiled.assembly)
        self.assertIn("extern $slices_asm_sysv", compiled.assembly)
        self.assertNotIn("[rsp-", compiled.assembly)
        self.assertNotRegex(compiled.assembly.lower(), r"\b(?:xmm|ymm|zmm)[0-9]+\b")
        self.assertIn("slices_probe.dg", compiled.manifest()["sources"])

    def test_manifest_includes_module_with_only_structures(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            entry, shapes = directory / "entry.dg", directory / "shapes.dg"
            entry.write_text("module entry;import shapes;fn result()u64{return 0;}", encoding="utf-8")
            shapes.write_text("module shapes;pub struct Record{pub value:u64}", encoding="utf-8")
            compiled = compile_file(entry, roots=[directory])
            self.assertEqual(["entry", "shapes"], compiled.manifest()["modules"])
            self.assertEqual(["entry.dg", "shapes.dg"], compiled.manifest()["sources"])

    def test_outgoing_stack_counts_toward_frame_limit(self):
        text = 'module f; extern "win64" fn helper()u64; fn test()u64{' + ' '.join(f'let a{i}:u64=0;' for i in range(507)) + 'unsafe{return helper();}}'
        with self.assertRaises(CompileError) as error:
            compile_source(text)
        self.assertEqual("E0601", error.exception.code)

    def test_native_slices_and_both_external_abis(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native slice checks require NASM and a SysV-capable GCC host compiler")
        source, c = fixtures()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            c_path = directory / "slices.c"
            c_path.write_text(c, encoding="utf-8")
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    asm, obj, observer = directory / f"{mode}.asm", directory / f"{mode}.o", directory / "observer.o"
                    exe = directory / (f"{mode}.exe" if os.name == "nt" else mode)
                    asm.write_text(compile_source(source, "slices_probe.dg", mode=mode).assembly, encoding="utf-8")
                    for inp, out in ((asm, obj), (FIXTURES / "slices_probe.asm", observer)):
                        result = subprocess.run([nasm, "-f", "win64" if os.name == "nt" else "elf64", *nasm_flags(nasm), "-o", str(out), str(inp)], capture_output=True, text=True)
                        self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror", str(c_path), str(obj), str(observer), "-o", str(exe)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("native slices, SysV aggregate and external ABI probes passed", result.stdout)
                    for case in ("index", "indexmax", "reversed", "high", "lowmax", "highmax", "array_high", "array_reversed", "snapshot_bounds", "field_bounds", "empty_index"):
                        with self.subTest(mode=mode, panic=case):
                            result = subprocess.run([str(exe), case], capture_output=True, text=True, timeout=10)
                            self.assertEqual(65, result.returncode, result.stdout + result.stderr)
                            self.assertIn("observed slice bounds panic", result.stdout)


if __name__ == "__main__":
    unittest.main()
