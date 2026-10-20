"""Production FAT32 grow/allocate with real native callbacks and I/O budgets.

Private entry points are exposed only by appending test exports to a verbatim
temporary production module. No allocation algorithm is duplicated in the probe.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / p for p in (
    "services/fs/fat32.dg", "services/fs/errors.dg", "services/fs/path.dg", "services/fs/lfn.dg",
    "tests/fat32_allocation_exports.dg.inc", "tests/fat32_allocation_probe.c", "tests/test_fat32_allocation.py")]


class Fat32AllocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = ROOT / "build/test/p5-fat32-allocation/host" / ("run-" + uuid.uuid4().hex[:12])
        cls.evidence.mkdir(parents=True)
        cls.before = cls.hashes()
        (cls.evidence / "source-before.json").write_text(json.dumps(cls.before, indent=2) + "\n")
        cls.executables = {}

    @classmethod
    def hashes(cls):
        return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES}

    @classmethod
    def tearDownClass(cls):
        after = cls.hashes()
        (cls.evidence / "source-after.json").write_text(json.dumps(after, indent=2) + "\n")
        if after != cls.before:
            raise AssertionError("allocation sources changed during native validation")

    def command(self, command, directory, label):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=120)
        (directory / (label + ".json")).write_text(json.dumps(dict(command=command,
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2) + "\n")
        return result

    def executable(self, mode, mutation=None):
        key = (mode, mutation)
        if key in self.executables:
            return self.executables[key]
        directory = self.evidence / ((mutation or "native") + "-" + mode)
        services = directory / "services"
        (services / "fs").mkdir(parents=True)
        for name in ("errors.dg", "path.dg", "lfn.dg"):
            shutil.copyfile(ROOT / "services/fs" / name, services / "fs" / name)
        source = (ROOT / "services/fs/fat32.dg").read_text()
        if mutation == "entry-scan":
            start = source.index("unsafe fn find_free(")
            end = source.index("unsafe fn allocate_from(", start)
            source = source[:start] + """unsafe fn find_free(v:*const Volume,w:*Scratch,start:u64)!u64{unsafe{
    var cluster=start;while cluster<(*v).clusters+2{
        if (try fat_get(v,w,cluster))==0{return cluster;}cluster+=1;
    }
}return error.errors.NoSpace;}
""" + source[end:]
        elif mutation == "restart-at-two":
            needle = "let cluster=try allocate_from(v,w,next_free);next_free=cluster+1;"
            self.assertEqual(1, source.count(needle))
            # Keep cursor syntax valid but restore the actual quadratic behavior.
            source = source.replace(needle, "let cluster=try allocate_from(v,w,2);next_free=cluster+1;")
        elif mutation is not None:
            raise AssertionError(mutation)
        target = services / "fs/fat32.dg"
        target.write_text(source + "\n" + (ROOT / "tests/fat32_allocation_exports.dg.inc").read_text())
        if mutation:
            (directory / "mutation.json").write_text(json.dumps(dict(kind=mutation,
                expected="real grow callback read budget rejects the changed production body"), indent=2) + "\n")
        compiled = compile_file(target, roots=[services], mode=mode)
        layouts = {item["full_name"]: item for item in compiled.layout_manifest["types"]}
        self.assertEqual(120, layouts["fs.fat32.Volume"]["size"])
        self.assertEqual(39656, layouts["fs.fat32.Scratch"]["size"])
        assembly = directory / "probe.asm"
        assembly.write_text(compiled.assembly)
        obj = directory / "probe.o"
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        self.assertTrue(nasm and cc, "configured NASM/GCC required")
        result = self.command([nasm, "-f", "win64" if os.name == "nt" else "elf64",
            *nasm_flags(nasm), "-o", str(obj), str(assembly)], directory, "assemble")
        self.assertEqual(0, result.returncode, result.stderr)
        executable = directory / ("probe.exe" if os.name == "nt" else "probe")
        result = self.command([cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-DFAT32_SCRATCH_BYTES=" + str(layouts["fs.fat32.Scratch"]["size"]),
            *([] if os.name == "nt" else ["-no-pie"]), str(ROOT / "tests/fat32_allocation_probe.c"),
            str(obj), "-o", str(executable)], directory, "link")
        self.assertEqual(0, result.returncode, result.stderr)
        self.executables[key] = executable
        return executable

    def test_production_growth_fragmentation_boundaries_and_faults(self):
        for mode in ("debug", "release"):
            executable = self.executable(mode)
            for scenario in ("large", "fragmented", "boundaries", "failures"):
                with self.subTest(mode=mode, scenario=scenario):
                    result = self.command([str(executable), scenario], executable.parent, scenario)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("allocation native checks passed", result.stdout)

    def test_actual_entry_reads_and_restarted_cursor_exceed_budget(self):
        for mode in ("debug", "release"):
            for mutation in ("entry-scan", "restart-at-two"):
                with self.subTest(mode=mode, mutation=mutation):
                    executable = self.executable(mode, mutation)
                    result = self.command([str(executable), "large"], executable.parent, "budget-rejection")
                    self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                    self.assertIn("read budget rejected production body: reads=24001", result.stderr)
                    self.assertNotIn("unexpected panic", result.stderr)


if __name__ == "__main__":
    unittest.main()
