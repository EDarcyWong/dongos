"""Native directory/LFN integration, independently constructed and read FAT32.

Real Dong code is linked against file callbacks.  The Python disk reader is an
independent oracle; it never calls the Dong path/LFN implementation.
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
from lang.tests.test_dongc import nasm_flags, tool
from tests.fat32_disk_oracle import (RawFat, fixture, DIRECTORY, ROOT_LONG,
    NESTED, EDGE, PAYLOAD, NESTED_PAYLOAD, EDGE_PAYLOAD, CHILD_PAYLOAD)
from tests.test_fat32 import stack_bound
from tools.make_fat32_disk import create, SEED

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / p for p in (
    "services/fs/fat32.dg", "services/fs/errors.dg", "services/fs/path.dg", "services/fs/lfn.dg",
    "tests/fat32_paths_probe.dg", "tests/fat32_paths_probe.c", "tests/fat32_disk_oracle.py",
    "tests/test_fat32_paths.py", "tools/make_fat32_disk.py")]


class Fat32PathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = ROOT / "build/test/p5-fat32-paths/host" / ("run-" + uuid.uuid4().hex[:12])
        cls.evidence.mkdir(parents=True)
        cls.before = cls.hashes()
        (cls.evidence / "source-before.json").write_text(json.dumps(cls.before, indent=2) + "\n")
        cls.executables = {}
        cls.results = []

    @classmethod
    def hashes(cls):
        return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES}

    @classmethod
    def tearDownClass(cls):
        after = cls.hashes()
        (cls.evidence / "source-after.json").write_text(json.dumps(after, indent=2) + "\n")
        stable = after == cls.before
        (cls.evidence / "validation-summary.json").write_text(json.dumps(dict(
            source_unchanged=stable, results=cls.results,
            independent_oracle="raw FAT allocation tree, strict Python UTF-16 decoder",
            actual_hardware=False, arbitrary_power_loss_atomicity=False), indent=2) + "\n")
        if not stable:
            raise AssertionError("directory/LFN sources changed during native validation")

    def command(self, command, directory, label, timeout=120):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
        (directory / (label + ".json")).write_text(json.dumps(dict(command=command,
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2) + "\n")
        return result

    def executable(self, mode, bad=False):
        key = (mode, bad)
        if key in self.executables:
            return self.executables[key]
        directory = self.evidence / (("bad-lfn-checksum-" if bad else "native-") + mode)
        directory.mkdir()
        services = ROOT / "services"
        if bad:
            services = directory / "services"
            (services / "fs").mkdir(parents=True)
            for name in ("fat32.dg", "errors.dg", "path.dg", "lfn.dg"):
                shutil.copyfile(ROOT / "services/fs" / name, services / "fs" / name)
            target = services / "fs/lfn.dg"
            source = target.read_text()
            needle = "if entries[base+13]!=sum {return error.Corrupt;}"
            self.assertEqual(1, source.count(needle))
            target.write_text(source.replace(needle, "if false {return error.Corrupt;}"))
            (directory / "mutation.json").write_text(json.dumps(dict(
                kind="actually ignore on-disk LFN checksum",
                expected="bad checksum fixture is incorrectly writable and native RO assertion catches it"), indent=2) + "\n")
        compiled = compile_file(ROOT / "tests/fat32_paths_probe.dg",
                                roots=[ROOT / "tests", services], mode=mode)
        layouts = {item["full_name"]: item for item in compiled.layout_manifest["types"]}
        self.assertEqual(120, layouts["fs.fat32.Volume"]["size"])
        self.assertEqual(1112, layouts["fs.fat32.PathEntry"]["size"])
        bound = stack_bound(compiled.assembly)
        frame = max(map(int, re.findall(r"sub rsp, ([0-9]+)", compiled.assembly)))
        self.assertLessEqual(frame, 8192)
        self.assertLessEqual(bound, 12288)  # 16KiB service stack reserves >=4KiB callback/bridge.
        (directory / "layout-stack.json").write_text(json.dumps(dict(
            types={k:v["size"] for k,v in layouts.items() if k.startswith("fs.fat32.")},
            max_frame=frame, direct_call_chain=bound, service_stack=16384,
            bridge_callback_budget=16384-bound), indent=2) + "\n")
        source = directory / "probe.asm"
        source.write_text(compiled.assembly)
        nasm, gcc = tool("nasm", "NASM"), tool("gcc", "CC")
        self.assertTrue(nasm and gcc, "configured native NASM/GCC required")
        for fmt in ("elf64", "win64"):
            result = self.command([nasm, "-f", fmt, *nasm_flags(nasm), "-o",
                str(directory / (fmt + ".o")), str(source)], directory, "assemble-" + fmt)
            self.assertEqual(0, result.returncode, result.stderr)
        object_file = directory / (("win64" if os.name == "nt" else "elf64") + ".o")
        executable = directory / ("probe.exe" if os.name == "nt" else "probe")
        flags = [] if os.name == "nt" else ["-no-pie"]
        result = self.command([gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-D__USE_MINGW_ANSI_STDIO=1", "-finput-charset=UTF-8", "-fexec-charset=UTF-8", *flags,
            str(ROOT / "tests/fat32_paths_probe.c"), str(object_file), "-o", str(executable)], directory, "link")
        self.assertEqual(0, result.returncode, result.stderr)
        self.executables[key] = executable
        return executable

    def scenario(self, mode, case, *, bad=False):
        executable = self.executable(mode, bad)
        directory = self.evidence / (mode + "-" + case + ("-bad" if bad else ""))
        directory.mkdir()
        image = directory / "disk.img"
        if case in ("lifecycle", "write-failure", "flush-failure"):
            create(image)
        else:
            fixture(image, "valid" if case in ("read-failure", "late-read-failure") else case)
        before = hashlib.sha256(image.read_bytes()).hexdigest()
        result = self.command([str(executable), str(image), case,
                               str(directory / "byte-journal.bin")], directory, "native")
        if bad:
            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertIn("FAT paths check failed line", result.stderr)
            self.assertNotIn("unexpected panic", result.stderr)
        else:
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("FAT paths checks passed", result.stdout)
        after = hashlib.sha256(image.read_bytes()).hexdigest()
        if case not in ("lifecycle", "write-failure", "flush-failure"):
            self.assertEqual(before, after, "read/audit or rejected operation wrote the image")
        self.results.append(dict(mode=mode, case=case, bad_implementation_caught=bad,
                                 returncode=result.returncode, image_before=before, image_after=after))
        return image, directory

    def test_independent_fragmented_fixture_and_original_component_walk(self):
        for mode in ("debug", "release"):
            image, directory = self.scenario(mode, "valid")
            with RawFat(image) as disk:
                entries = disk.audit()
                self.assertEqual(0, disk.invalid_lfn)
                self.assertEqual(SEED, entries["/README.TXT"]["content"])
                self.assertEqual(PAYLOAD, entries["/" + ROOT_LONG]["content"])
                self.assertEqual(NESTED_PAYLOAD, entries["/" + DIRECTORY + "/" + NESTED]["content"])
                self.assertEqual(EDGE_PAYLOAD, entries["/" + DIRECTORY + "/" + EDGE]["content"])
                self.assertEqual(CHILD_PAYLOAD, entries["/" + DIRECTORY + "/ChildFolder/SPARSE.BIN"]["content"])
                self.assertEqual([7, 13, 8], entries["/" + ROOT_LONG]["chain"])
                (directory / "independent-tree.json").write_text(json.dumps(dict(
                    owners=disk.owners, entries={k:{a:b for a,b in v.items() if a!="content"}
                                               for k,v in entries.items()}), indent=2) + "\n")

    def test_writes_truncate_delete_alias_namespace_and_clean_remount(self):
        for mode in ("debug", "release"):
            image, directory = self.scenario(mode, "lifecycle")
            with RawFat(image) as disk:
                entries = disk.audit()
                self.assertEqual(0, disk.invalid_lfn, "deleted long-name groups left orphan live slots")
                name = "/PROJECTS/图形 桌面/多语言 report 😀.txt"
                expected = bytearray(1800)
                expected[:300] = bytes((i * 23 + 41) & 255 for i in range(300))
                expected[1600:1629] = bytes((i * 9 + 3) & 255 for i in range(29))
                self.assertEqual(expected, entries[name]["content"])
                self.assertIn("/PROJECTS/图形 桌面/" + "q" * 255, entries)
                alpha = entries["/PROJECTS/图形 桌面/Project documentation alpha.txt"]
                beta = entries["/PROJECTS/图形 桌面/Project documentation beta.txt"]
                self.assertNotEqual(alpha["raw_alias"], beta["raw_alias"])
                self.assertFalse(any("remove " in key for key in entries))
                (directory / "independent-tree.json").write_text(json.dumps(dict(
                    owners=disk.owners, entries={k:{a:b for a,b in v.items() if a!="content"}
                                               for k,v in entries.items()}), indent=2) + "\n")

    def test_tree_corruption_and_malformed_lfn_fallback_read_only(self):
        for mode in ("debug", "release"):
            for case in ("dot-self", "dot-parent", "cross-link", "ancestor", "dir-cycle", "unreachable"):
                image, _ = self.scenario(mode, case)
                with self.assertRaises(AssertionError), RawFat(image) as disk:
                    disk.audit()
            for case in ("lfn-checksum", "lfn-ordinal", "lfn-surrogate"):
                image, _ = self.scenario(mode, case)
                with RawFat(image) as disk:
                    entries = disk.audit()
                    self.assertGreater(disk.invalid_lfn, 0)
                    self.assertEqual(PAYLOAD, entries["/CROSSC~1.TXT"]["content"])
            self.scenario(mode, "dirty")

    def test_io_failures_preserve_results_and_poison_writes(self):
        for mode in ("debug", "release"):
            for case in ("read-failure", "late-read-failure", "write-failure", "flush-failure"):
                self.scenario(mode, case)

    def test_actual_missing_lfn_checksum_validation_is_caught(self):
        for mode in ("debug", "release"):
            self.scenario(mode, "lfn-checksum", bad=True)

    def test_every_mutation_sector_write_and_flush_failure_boundary(self):
        # Both codegen modes run all ordinary contracts above. This extended
        # prefix matrix runs release code at every actual callback boundary;
        # it is fail-stop recovery validation, not torn-sector/journal proof.
        executable = self.executable("release")
        rows = []
        for operation in ("create", "mkdir", "remove", "truncate"):
            for boundary in ("write", "flush"):
                for point in range(1, 128):
                    case = f"fault-{operation}-{boundary}-{point}"
                    directory = self.evidence / case
                    directory.mkdir()
                    image = directory / "disk.img"
                    create(image)
                    result = self.command([str(executable), str(image), case,
                        str(directory / "byte-journal.bin")], directory, "native")
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    match = re.search(r"FAULT operation=(\w+) boundary=(\w+) point=(\d+) writes=(\d+) flushes=(\d+) injected=([01]) recovery=(\d+) readonly=([01])", result.stdout)
                    self.assertIsNotNone(match, result.stdout)
                    injected, recovery = int(match[6]), int(match[7])
                    row = dict(operation=operation, boundary=boundary, point=point,
                        writes=int(match[4]), flushes=int(match[5]), injected=bool(injected),
                        recovery_error=recovery, readonly=bool(int(match[8])))
                    if recovery == 0:
                        with RawFat(image, require_clean=False) as disk:
                            entries = disk.audit(allow_unreachable=not disk.clean)
                            self.assertFalse(any("GHOST" in p for p in entries),
                                "publishing an LFN prefix exposed bytes beyond the old 00 terminator")
                            row.update(independent_live_tree_valid=True, clean=disk.clean,
                                       unreachable=len(disk.unreachable), invalid_lfn=disk.invalid_lfn)
                    else:
                        self.assertEqual(0x05040005, recovery)
                        row["independent_live_tree_valid"] = None
                    rows.append(row)
                    (self.evidence / "failure-boundary-matrix.json").write_text(json.dumps(rows, indent=2) + "\n")
                    if not injected:
                        self.assertGreater(point, 1)
                        break
                else:
                    self.fail("mutation exceeds bounded 127-point fault matrix")
        self.results.append(dict(case="all-release-mutation-boundaries", boundaries=rows))


if __name__ == "__main__":
    unittest.main()
