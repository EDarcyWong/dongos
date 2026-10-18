"""Buddy-owned active page cache: independent native oracle and finite controls."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import unittest
import uuid

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent
KERNEL = ROOT / "kernel"
MODES = ("debug", "release")


class PageCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = ROOT / "build/test/cache-lifecycle/host" / ("run-" + uuid.uuid4().hex[:12])
        cls.evidence.mkdir(parents=True)
        cls.inputs = [FIXTURES / "page_cache_probe.dg", FIXTURES / "page_cache_probe.c",
                      Path(__file__), KERNEL / "mm/page_cache.dg", KERNEL / "mm/phys_buddy.dg",
                      KERNEL / "mm/fixed_cache.dg", KERNEL / "mm/active_paging.dg", KERNEL / "mm/paging.dg"]
        cls.hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in cls.inputs}
        for path in cls.inputs:
            target = cls.evidence / "source-snapshot" / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
        (cls.evidence / "source-before.json").write_text(json.dumps(cls.hashes, indent=2) + "\n")

    @classmethod
    def tearDownClass(cls):
        after = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in cls.inputs}
        (cls.evidence / "source-after.json").write_text(json.dumps(after, indent=2) + "\n")
        if after != cls.hashes:
            raise AssertionError("page cache native inputs changed during this execution")

    def require_tools(self, native=False):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or native and not cc:
            self.skipTest("page cache oracle requires NASM" + (" and a SysV-capable GCC" if native else ""))
        return nasm, cc

    def compile(self, mode, *, kernel=KERNEL, entry=None):
        entry = entry or FIXTURES / "page_cache_probe.dg"
        return compile_file(entry, roots=[entry.parent, kernel, ROOT / "lang/std"], mode=mode)

    def command(self, command, directory, name, *, timeout=30):
        started = time.monotonic()
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
        (directory / (name + ".json")).write_text(json.dumps({
            "command": [str(item) for item in command], "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr,
            "elapsed_seconds": round(time.monotonic() - started, 6),
        }, indent=2) + "\n", encoding="utf-8")
        return result

    def build_native(self, directory, mode, nasm, cc, *, kernel=KERNEL, entry=None):
        directory.mkdir(parents=True, exist_ok=True)
        compiled = self.compile(mode, kernel=kernel, entry=entry)
        asm, obj = directory / "probe.asm", directory / "probe.o"
        asm.write_text(compiled.assembly, encoding="utf-8")
        object_format = "win64" if os.name == "nt" else "elf64"
        result = self.command([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(obj), str(asm)], directory, "assemble")
        self.assertEqual(0, result.returncode, result.stderr)
        executable = directory / ("probe.exe" if os.name == "nt" else "probe")
        flags = ["-mno-sse"] if os.name == "nt" else ["-no-pie"]
        result = self.command([cc, "-std=c11", "-O2", "-D__USE_MINGW_ANSI_STDIO=1", "-Wall", "-Wextra", "-Werror",
                               *flags, str(FIXTURES / "page_cache_probe.c"), str(obj), "-o", str(executable)], directory, "link")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return executable

    def test_layout_module_graph_and_both_formats(self):
        nasm, _ = self.require_tools()
        for mode in MODES:
            compiled = self.compile(mode)
            modules = set(compiled.manifest()["modules"])
            self.assertTrue({"mm.page_cache", "mm.phys_buddy", "mm.fixed_cache", "mm.active_paging",
                             "mm.paging", "boot.preflight", "page_cache_probe"}.issubset(modules), modules)
            layouts = {item["full_name"]: item for item in compiled.layout_manifest["types"]}
            info = layouts["mm.page_cache.Info"]
            self.assertEqual((48, 8), (info["size"], info["alignment"]))
            self.assertEqual(["physical", "virtual", "capacity", "free_objects", "mapped", "ready"],
                             [item["name"] for item in info["fields"]])
            self.assertEqual(list(range(0, 48, 8)), [item["offset"] for item in info["fields"]])
            self.assertEqual(4096, layouts["mm.paging.Table"]["alignment"])
            self.assertIn("mm.page_cache.Owner", layouts)
            self.assertNotRegex(compiled.assembly.lower(), r"\b(?:xmm|ymm|zmm)[0-9]+\b")
            directory = self.evidence / "formats" / mode
            directory.mkdir(parents=True)
            asm = directory / "probe.asm"
            asm.write_text(compiled.assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                result = self.command([nasm, "-f", object_format, *nasm_flags(nasm), "-o",
                                       str(directory / (object_format + ".o")), str(asm)], directory, object_format)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_native_ownership_payload_ordering_failures_and_reuse(self):
        nasm, cc = self.require_tools(native=True)
        for mode in MODES:
            directory = self.evidence / "native" / mode
            executable = self.build_native(directory, mode, nasm, cc)
            result = self.command([str(executable)], directory, "native", timeout=30)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("page cache ownership/ordering/payload model passed", result.stdout)

    def test_cleanup_required_retains_mapped_lease_and_retry_recovers(self):
        nasm, cc = self.require_tools(native=True)
        original = (KERNEL / "mm/page_cache.dg").read_text(encoding="utf-8")
        init = re.search(r"try\s+fixed\.init\([^;]+;", original)
        unmap = re.search(r"try\s+active\.unmap\([^;]+;", original)
        self.assertIsNotNone(init)
        self.assertIsNotNone(unmap)
        injected = original[:init.start()] + "if cleanup_fault(1) != 0 { return error.errors.InvalidArgument; }\n        " + original[init.start():]
        unmap = re.search(r"try\s+active\.unmap\([^;]+;", injected)
        injected = injected[:unmap.start()] + "if cleanup_fault(2) != 0 { return error.active.InvalidControls; }\n            " + injected[unmap.start():]
        injected = injected.replace("module mm.page_cache;", "module mm.page_cache;\n"
                                    'unsafe extern "sysv64" ("pc_cleanup_fault") fn cleanup_fault(stage: u64) u64;\n', 1)
        directory = self.evidence / "cleanup-recovery"
        kernel_copy = directory / "kernel"
        shutil.copytree(KERNEL, kernel_copy)
        (kernel_copy / "mm/page_cache.dg").write_text(injected, encoding="utf-8")
        for mode in MODES:
            output = directory / mode
            executable = self.build_native(output, mode, nasm, cc, kernel=kernel_copy)
            result = self.command([str(executable), "--cleanup-recovery"], output, "native", timeout=30)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(1, result.stderr.count("PC_CLEANUP_HIT stage=1 count=1"))
            self.assertEqual(1, result.stderr.count("PC_CLEANUP_HIT stage=2 count=1"))
            self.assertIn("page cache cleanup failure/retry passed", result.stdout)

    def test_minimal_bad_payload_and_early_release_are_observed(self):
        nasm, cc = self.require_tools(native=True)
        original_probe = (FIXTURES / "page_cache_probe.dg").read_text(encoding="utf-8")
        payload_before = "ok(value) => { *output = value as usize as u64; return 0; },"
        self.assertEqual(1, original_probe.count(payload_before))
        payload_probe = original_probe.replace(
            'export("pc_owner_size")',
            'unsafe extern "sysv64" ("pc_negative_hit") fn negative_hit(kind: u64) void;\n\nexport("pc_owner_size")', 1,
        ).replace(payload_before,
                  "ok(value) => { negative_hit(1); *value = *value ^ 1; *output = value as usize as u64; return 0; },", 1)
        payload_dir = self.evidence / "controls" / "successful_alloc_bad_payload"
        payload_dir.mkdir(parents=True)
        payload_entry = payload_dir / "page_cache_probe.dg"
        payload_entry.write_text(payload_probe, encoding="utf-8")

        # Inject the adapter's actual physical release ahead of its actual
        # unmap, armed only for the bounded lifecycle's valid destroy. The
        # callback must reject it before the later ordinary release is reached.
        original_core = (KERNEL / "mm/page_cache.dg").read_text(encoding="utf-8")
        destroy_start = original_core.index("unsafe fn release_storage(")
        tail = original_core[destroy_start:]
        unmap = re.search(r"try\s+active\.unmap\([^;]+;", tail)
        release = re.search(r"try\s+buddy\.free\([^;]+;", tail)
        self.assertIsNotNone(unmap, "update the finite early-release control for the adapter's actual unmap")
        self.assertIsNotNone(release, "update the finite early-release control for the adapter's actual physical free")
        self.assertLess(unmap.start(), release.start())
        changed_tail = (tail[:unmap.start()] + "if negative_armed() != 0 { negative_hit(2); " + release.group() + " }\n            "
                        + tail[unmap.start():])
        early_core = original_core[:destroy_start] + changed_tail
        declaration = ('unsafe extern "sysv64" ("pc_negative_hit") fn negative_hit(kind: u64) void;\n'
                       'unsafe extern "sysv64" ("pc_negative_armed") fn negative_armed() u64;\n')
        early_core = early_core.replace("module mm.page_cache;", "module mm.page_cache;\n" + declaration, 1)
        early_dir = self.evidence / "controls" / "physical_release_before_flush"
        kernel_copy = early_dir / "kernel"
        shutil.copytree(KERNEL, kernel_copy)
        (kernel_copy / "mm/page_cache.dg").write_text(early_core, encoding="utf-8")
        for name, directory, kernel, entry, kind, expected in (
            ("successful_alloc_bad_payload", payload_dir, KERNEL, payload_entry, 1, "!memcmp(f->buffer[i].data,f->expected[i],4096)"),
            ("physical_release_before_flush", early_dir, kernel_copy, None, 2, "pages(f)==expected.free_pages"),
        ):
            for mode in MODES:
                with self.subTest(control=name, mode=mode):
                    output = directory / mode
                    executable = self.build_native(output, mode, nasm, cc, kernel=kernel, entry=entry)
                    result = self.command([str(executable)], output, "native", timeout=30)
                    self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn(f"PC_NEGATIVE_HIT=1 kind={kind}", result.stderr)
                    self.assertIn("page cache failure", result.stderr)
                    self.assertIn(expected, result.stderr)
                    self.assertNotIn("page cache ownership/ordering/payload model passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
