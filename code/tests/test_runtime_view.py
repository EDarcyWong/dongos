"""Pure Runtime PA/VA views: fixed ABI, guarded publication and boundaries."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from lang.dongc import compile_file
from lang.tests.test_dongc import tool, nasm_flags

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent


def compile_probe(mode):
    return compile_file(FIXTURES / "runtime_view_probe.dg", roots=[FIXTURES, ROOT / "kernel", ROOT / "lang/std", ROOT / "lang/examples"], mode=mode)


class RuntimeViewTests(unittest.TestCase):
    def test_fixed_layout_both_modes_elf64_coff(self):
        nasm = tool("nasm", "NASM")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            for mode in ("debug", "release"):
                compiled = compile_probe(mode)
                types = {t["full_name"]: t for t in compiled.layout_manifest["types"]}
                display, view = types["boot.runtime_view.Display"], types["boot.runtime_view.View"]
                self.assertEqual((48, 8), (display["size"], display["alignment"]))
                self.assertEqual((160, 8), (view["size"], view["alignment"]))
                self.assertEqual([0, 8, 16, 24, 32, 40], [f["offset"] for f in display["fields"]])
                self.assertEqual([0, *range(48, 160, 8)], [f["offset"] for f in view["fields"]])
                self.assertEqual(["framebuffer_base", "framebuffer_size", "width", "height", "stride", "pixel_format"], [f["name"] for f in display["fields"]])
                self.assertEqual(["display", "boot_info", "raw_map", "raw_size", "descriptor_size", "rsdp", "rsdp_size", "pool", "pool_physical", "pool_pages", "stack_bottom", "stack_top", "stack_probe_bottom", "stack_probe_top", "root_physical"], [f["name"] for f in view["fields"]])
                if not nasm:
                    continue
                asm = path / (mode + ".asm")
                asm.write_text(compiled.assembly, encoding="utf-8")
                for fmt in ("elf64", "win64"):
                    with self.subTest(mode=mode, format=fmt):
                        result = subprocess.run([nasm, "-f", fmt, *nasm_flags(nasm), "-o", str(path / (mode + fmt + ".o")), str(asm)], capture_output=True, text=True, timeout=30)
                        self.assertEqual(0, result.returncode, result.stderr)
            if not nasm:
                self.skipTest("ELF/COFF assembly requires NASM; layouts checked")

    def test_native_guarded_views(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native Runtime view requires NASM and SysV-capable GCC")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    asm = path / (mode + ".asm")
                    asm.write_text(compile_probe(mode).assembly, encoding="utf-8")
                    obj = path / (mode + ".o")
                    exe = path / (mode + (".exe" if os.name == "nt" else ""))
                    result = subprocess.run([nasm, "-f", "win64" if os.name == "nt" else "elf64", *nasm_flags(nasm), "-o", str(obj), str(asm)], capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, result.returncode, result.stderr)
                    cmd = [cc, "-std=c11", "-O0" if mode == "debug" else "-O2", "-fno-omit-frame-pointer", "-D__USE_MINGW_ANSI_STDIO=1", "-Wall", "-Wextra", "-Werror"]
                    if os.name != "nt":
                        cmd += ["-no-pie"]
                    result = subprocess.run(cmd + [str(FIXTURES / "runtime_view_probe.c"), str(obj), "-o", str(exe)], capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("runtime view probe ok:", result.stdout)


if __name__ == "__main__":
    unittest.main()
