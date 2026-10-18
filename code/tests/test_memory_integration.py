"""Host integration of memory-map normalization, buddy pages and offline paging."""
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
MODES = ("debug", "release")
SEEDS = (None, "0x0fedcba987654321", "0xc001d00d5eed1234")


class MemoryIntegrationTests(unittest.TestCase):
    def compile_probe(self, mode, entry=None):
        entry = entry or FIXTURES / "memory_integration_probe.dg"
        return compile_file(
            entry,
            roots=[entry.parent, ROOT / "kernel", ROOT / "lang" / "std"],
            mode=mode,
        )

    def build_native(self, directory, mode, nasm, cc, entry=None):
        assembly = directory / (mode + ".asm")
        obj = directory / (mode + ".o")
        executable = directory / (mode + (".exe" if os.name == "nt" else ""))
        assembly.write_text(self.compile_probe(mode, entry).assembly, encoding="utf-8")
        result = subprocess.run(
            [nasm, "-f", "win64" if os.name == "nt" else "elf64",
             *nasm_flags(nasm), "-o", str(obj), str(assembly)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        platform_flags = [] if os.name == "nt" else ["-no-pie"]
        result = subprocess.run(
            [cc, "-std=c11", "-O2", "-D__USE_MINGW_ANSI_STDIO=1",
             "-Wall", "-Wextra", "-Werror", *platform_flags,
             str(FIXTURES / "memory_integration_probe.c"), str(obj),
             "-o", str(executable)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return executable

    def test_module_graph_layouts_and_both_object_formats(self):
        nasm = tool("nasm", "NASM")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in MODES:
                with self.subTest(mode=mode):
                    compiled = self.compile_probe(mode)
                    modules = set(compiled.manifest()["modules"])
                    self.assertTrue(
                        {
                            "core.errors", "mm.errors", "mm.memory_map",
                            "mm.phys_buddy", "mm.paging", "mm.paging_errors",
                            "memory_integration_probe",
                        }.issubset(modules),
                        modules,
                    )
                    layouts = {
                        item["full_name"]: item
                        for item in compiled.layout_manifest["types"]
                    }
                    for name, fields in (
                        ("mm.memory_map.ReservedRange", ["base", "length"]),
                        ("mm.memory_map.PageRange", ["start_page", "page_count"]),
                        ("mm.paging.Mapping", ["physical", "flags"]),
                    ):
                        layout = layouts[name]
                        self.assertEqual((16, 8), (layout["size"], layout["alignment"]))
                        self.assertEqual(fields, [field["name"] for field in layout["fields"]])
                        self.assertEqual([0, 8], [field["offset"] for field in layout["fields"]])
                    table = layouts["mm.paging.Table"]
                    self.assertEqual((4096, 4096), (table["size"], table["alignment"]))
                    self.assertEqual([0], [field["offset"] for field in table["fields"]])
                    for name in ("mm.phys_buddy.Allocator", "mm.phys_buddy.PageMeta", "mm.paging.Space"):
                        self.assertIn(name, layouts)
                    self.assertNotRegex(compiled.assembly.lower(), r"\b(?:xmm|ymm|zmm)[0-9]+\b")
                    if nasm:
                        assembly = directory / (mode + ".asm")
                        assembly.write_text(compiled.assembly, encoding="utf-8")
                        for object_format in ("elf64", "win64"):
                            with self.subTest(mode=mode, format=object_format):
                                result = subprocess.run(
                                    [nasm, "-f", object_format, *nasm_flags(nasm), "-o",
                                     str(directory / (mode + "-" + object_format + ".o")),
                                     str(assembly)],
                                    capture_output=True, text=True, timeout=30,
                                )
                                self.assertEqual(0, result.returncode, result.stderr)
            if not nasm:
                self.skipTest("ELF64/COFF integration assembly requires NASM; layouts were checked")

    def test_native_normalize_publish_allocate_map_and_reclaim(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native integration requires NASM and a SysV-capable GCC host compiler")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in MODES:
                executable = self.build_native(directory, mode, nasm, cc)
                for seed in SEEDS:
                    with self.subTest(mode=mode, seed=seed or "default"):
                        args = [str(executable)] + ([] if seed is None else [seed])
                        result = subprocess.run(
                            args, capture_output=True, text=True, timeout=45,
                        )
                        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                        self.assertIn("memory integration probe ok", result.stdout)

    def test_corrupt_handoffs_are_rejected_by_independent_harness(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native negative controls require NASM and a SysV-capable GCC host compiler")
        original = (FIXTURES / "memory_integration_probe.dg").read_text(encoding="utf-8")
        mutations = (
            (
                "normalized_range_includes_kernel",
                "ok(value) => { *used = value; return 0; },",
                "ok(value) => { (*output).start_page = 0; *used = value; return 0; },",
            ),
            (
                "allocated_physical_address_truncated_to_u32",
                "match buddy.alloc(state, order) {\n"
                "            ok(value) => { *out = value; return 0; },",
                "match buddy.alloc(state, order) {\n"
                "            ok(value) => { *out = value as u32 as u64; return 0; },",
            ),
            (
                "table_pool_physical_base_shifted_one_page",
                "state, slice_from_raw_parts(pool, table_count), physical,",
                "state, slice_from_raw_parts(pool, table_count), physical + 4096,",
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            for name, before, after in mutations:
                self.assertEqual(1, original.count(before), name)
                directory = Path(temporary) / name
                directory.mkdir()
                entry = directory / "memory_integration_probe.dg"
                entry.write_text(original.replace(before, after, 1), encoding="utf-8")
                for mode in MODES:
                    with self.subTest(mutation=name, mode=mode):
                        # Build failures are test failures, never accepted as a
                        # negative-control rejection of a completed handoff.
                        executable = self.build_native(directory, mode, nasm, cc, entry)
                        result = subprocess.run(
                            [str(executable)], capture_output=True, text=True, timeout=45,
                        )
                        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
                        self.assertIn("integration failure", result.stderr)
                        self.assertNotIn("memory integration probe ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
