"""Execute the actual filesystem service body with native syscall/block stubs.

The private staging suffix only exports existing service functions/globals;
request validation, routing, record packing and APPEND execute original code.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool, nasm_flags
from tools.make_fat32_disk import create, SEED
from tests.fat32_disk_oracle import RawFat
from tests.test_fat32 import stack_bound

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / p for p in ("services/fs/service.dg", "services/fs/protocol.dg",
    "services/fs/fat32.dg", "services/fs/mount_cache.dg", "services/fs/errors.dg", "services/fs/path.dg", "services/fs/lfn.dg", "services/fs/handles.dg",
    "services/lib/abi.dg", "services/lib/sys.dg", "tests/fs_service_probe.dg.in",
    "tests/fs_service_probe.c", "tests/test_fs_service.py", "tests/fat32_disk_oracle.py")]


class FsServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = ROOT / "build/test/p5-fs-service/host" / ("run-" + uuid.uuid4().hex[:12])
        cls.evidence.mkdir(parents=True)
        cls.before = cls.hashes()
        (cls.evidence / "source-before.json").write_text(json.dumps(cls.before, indent=2) + "\n")
        cls.results = []

    @classmethod
    def hashes(cls):
        return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES}

    @classmethod
    def tearDownClass(cls):
        after = cls.hashes()
        stable = after == cls.before
        (cls.evidence / "source-after.json").write_text(json.dumps(after, indent=2) + "\n")
        (cls.evidence / "validation-summary.json").write_text(json.dumps(dict(
            source_unchanged=stable, actual_service_body=True, actual_block_device=False,
            actual_peer_kernel=False, results=cls.results), indent=2) + "\n")
        if not stable:
            raise AssertionError("filesystem service input changed during native run")

    def command(self, argv, directory, label):
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120)
        (directory / (label + ".json")).write_text(json.dumps(dict(command=argv,
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2) + "\n")
        return result

    def run_native(self, mode, bad=False):
        directory = self.evidence / (("bad-reserved-" if bad else "native-") + mode)
        (directory / "services/fs").mkdir(parents=True)
        original = (ROOT / "services/fs/service.dg").read_bytes()
        source = original.decode()
        if bad:
            needle = "REQUEST.words[7]!=0"
            self.assertEqual(3, source.count(needle))
            source = source.replace(needle, "false", 1)
        suffix = (ROOT / "tests/fs_service_probe.dg.in").read_text()
        staged = directory / "services/fs/service.dg"
        staged.write_bytes((source + suffix).encode())
        # The normal staging body is byte-identical; only exports are appended.
        if not bad:
            self.assertEqual(original, staged.read_bytes()[:len(original)])
        (directory / "staging.json").write_text(json.dumps(dict(
            actual_service_sha256=hashlib.sha256(original).hexdigest(),
            service_body_unchanged=not bad, added_exports_only=not bad,
            mutation="ignore reserved request word 7" if bad else None), indent=2) + "\n")
        for path in SOURCES:
            if path.is_relative_to(ROOT / "services") and path.name != "service.dg":
                target = directory / "services" / path.relative_to(ROOT / "services")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        compiled = compile_file(staged, roots=[directory / "services"], mode=mode)
        assembly = directory / "probe.asm"
        assembly.write_text(compiled.assembly)
        frame = max(map(int, re.findall(r"sub rsp, ([0-9]+)", compiled.assembly)))
        bound = stack_bound(compiled.assembly)
        self.assertLessEqual(frame, 8192)
        self.assertLessEqual(bound, 12288)
        (directory / "stack.json").write_text(json.dumps(dict(max_frame=frame,
            direct_call_chain=bound, syscall_stub_native_only=True), indent=2) + "\n")
        nasm, gcc = tool("nasm", "NASM"), tool("gcc", "CC")
        self.assertTrue(nasm and gcc)
        for fmt in ("elf64", "win64"):
            result = self.command([nasm, "-f", fmt, *nasm_flags(nasm), "-o",
                str(directory / (fmt + ".o")), str(assembly)], directory, "assemble-" + fmt)
            self.assertEqual(0, result.returncode, result.stderr)
        obj = directory / (("win64" if os.name == "nt" else "elf64") + ".o")
        executable = directory / ("probe.exe" if os.name == "nt" else "probe")
        flags = [] if os.name == "nt" else ["-no-pie", "-D_GNU_SOURCE"]
        result = self.command([gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-D__USE_MINGW_ANSI_STDIO=1", "-finput-charset=UTF-8", "-fexec-charset=UTF-8", *flags,
            str(ROOT / "tests/fs_service_probe.c"), str(obj), "-o", str(executable)], directory, "link")
        self.assertEqual(0, result.returncode, result.stderr)
        image = directory / "disk.img"
        create(image)
        result = self.command([str(executable), str(image)], directory, "native")
        if bad:
            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertIn("FS service check failed line", result.stderr)
            self.assertNotIn("unexpected panic", result.stderr)
        else:
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("FS service native checks passed", result.stdout)
            with RawFat(image) as disk:
                entries = disk.audit()
                self.assertEqual(0, disk.invalid_lfn)
                self.assertEqual(SEED, entries["/README.TXT"]["content"])
                self.assertEqual(b"first second", entries["/append 测试.txt"]["content"])
        self.results.append(dict(mode=mode, negative_control_caught=bad,
            returncode=result.returncode, stdout=result.stdout))

    def test_actual_service_guards_routes_records_and_single_rpc_append(self):
        for mode in ("debug", "release"):
            self.run_native(mode)

    def test_actual_missing_reserved_guard_is_caught(self):
        for mode in ("debug", "release"):
            self.run_native(mode, bad=True)


if __name__ == "__main__":
    unittest.main()
