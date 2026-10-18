"""Independent BootInfo-v1 resource envelope and physical-layout validation."""
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


class BootResourcesTests(unittest.TestCase):
    def compile_probe(self, mode):
        return compile_file(
            FIXTURES / "boot_resources_probe.dg",
            roots=[FIXTURES, ROOT / "kernel", ROOT / "lang" / "examples", ROOT / "lang" / "std"],
            mode=mode,
        )

    def assemble(self, nasm, assembly, obj, object_format):
        result = subprocess.run(
            [nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(obj), str(assembly)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_abi_public_layouts_and_both_object_formats(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("both object formats require NASM")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in ("debug", "release"):
                compiled = self.compile_probe(mode)
                self.assertTrue(
                    {"boot.abi", "boot.memory_resources", "boot.resource_errors", "mm.memory_map"}
                    .issubset(set(compiled.manifest()["modules"]))
                )
                layouts = {item["full_name"]: item for item in compiled.layout_manifest["types"]}
                for name, size, offsets in (
                    ("boot.abi.BootInfo", 160, list(range(0, 160, 8))),
                    ("boot.memory_resources.Span", 16, [0, 8]),
                    ("boot.memory_resources.Layout", 184, list(range(0, 176, 16)) + [176]),
                    ("boot.memory_resources.Resource", 24, [0, 8, 16]),
                ):
                    layout = layouts[name]
                    self.assertEqual((size, 8), (layout["size"], layout["alignment"]))
                    self.assertEqual(offsets, [field["offset"] for field in layout["fields"]])
                assembly = directory / (mode + ".asm")
                assembly.write_text(compiled.assembly, encoding="utf-8")
                for object_format in ("elf64", "win64"):
                    with self.subTest(mode=mode, format=object_format):
                        self.assemble(nasm, assembly, directory / (mode + object_format + ".o"), object_format)

    def test_native_resources_envelopes_layout_and_full_failure_snapshots(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native boot-resource tests require NASM and a SysV-capable GCC")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    assembly, obj = directory / (mode + ".asm"), directory / (mode + ".o")
                    executable = directory / (mode + (".exe" if os.name == "nt" else ""))
                    assembly.write_text(self.compile_probe(mode).assembly, encoding="utf-8")
                    self.assemble(nasm, assembly, obj, "win64" if os.name == "nt" else "elf64")
                    flags = [] if os.name == "nt" else ["-no-pie"]
                    result = subprocess.run(
                        [cc, "-std=c11", "-O2", "-D__USE_MINGW_ANSI_STDIO=1", "-Wall", "-Wextra", "-Werror",
                         *flags, str(FIXTURES / "boot_resources_probe.c"), str(obj), "-o", str(executable)],
                        capture_output=True, text=True, timeout=30,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("boot resource probe ok:", result.stdout)


if __name__ == "__main__":
    unittest.main()
