from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from lang.dongc.__main__ import atomic_write, atomic_write_many
from lang.tests.test_dongc import ROOT, tool


class LayoutCliTests(unittest.TestCase):
    def run_cli(self, *arguments):
        return subprocess.run([sys.executable, "-m", "lang.dongc", *map(str, arguments)],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def test_layout_only_output_and_failure_preserves_previous_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source, layout = directory / "test.dg", directory / "layout.json"
            source.write_text("module test; struct Record { tag:u8, value:u64 }", encoding="utf-8")
            result = self.run_cli("--emit-layout", layout, source)
            self.assertEqual(result.returncode, 0, result.stderr)
            before = layout.read_bytes()
            record = json.loads(before)["types"][0]
            self.assertEqual((record["size"], record["alignment"]), (16, 8))
            self.assertEqual(record["fields"][1]["offset"], 8)
            source.write_text("module test; struct Record { bad:Record }", encoding="utf-8")
            self.assertEqual(self.run_cli("--emit-layout", layout, source).returncode, 1)
            self.assertEqual(layout.read_bytes(), before)
            self.assertEqual(self.run_cli("--check", "--emit-layout", layout, source).returncode, 2)

    def test_outputs_cannot_overwrite_source_or_each_other(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "test.dg"
            text = "module test; fn result()u64{return 1;}"
            source.write_text(text, encoding="utf-8")
            self.assertEqual(self.run_cli("--emit-layout", source, source).returncode, 2)
            output = Path(temp) / "output"
            self.assertEqual(self.run_cli("--emit-asm", output, "--emit-layout", output, source).returncode, 2)
            self.assertEqual(source.read_text(encoding="utf-8"), text)

    def test_later_directory_output_preserves_the_complete_previous_set(self):
        for previous in (None, b"previous successful assembly\n"):
            with self.subTest(previous=previous), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                source, assembly, layout = directory / "test.dg", directory / "test.asm", directory / "layout.json"
                source.write_text("module test; fn result()u64{return 1;}", encoding="utf-8")
                if previous is not None:
                    assembly.write_bytes(previous)
                layout.mkdir()
                result = self.run_cli("--emit-asm", assembly, "--emit-layout", layout, source)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("output target is not a regular file", result.stderr)
                self.assertTrue(layout.is_dir())
                if previous is None:
                    self.assertFalse(assembly.exists())
                else:
                    self.assertEqual(assembly.read_bytes(), previous)
                self.assertEqual(list(directory.glob("*.tmp")), [])

    def test_later_commit_failure_rolls_back_existing_or_new_first_output(self):
        for previous in (None, b"previous successful assembly\n"):
            with self.subTest(previous=previous), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                assembly, layout = directory / "test.asm", directory / "layout.json"
                if previous is not None:
                    assembly.write_bytes(previous)
                layout.write_bytes(b"previous successful layout\n")
                replace = os.replace
                commits = 0

                def fail_second_commit(staged, target):
                    nonlocal commits
                    commits += 1
                    if commits == 2:
                        raise OSError("simulated second artifact commit failure")
                    return replace(staged, target)

                with patch("lang.dongc.__main__.os.replace", side_effect=fail_second_commit):
                    with self.assertRaisesRegex(OSError, "second artifact commit failure"):
                        atomic_write_many([(assembly, "new assembly\n"), (layout, "new layout\n")])
                if previous is None:
                    self.assertFalse(assembly.exists())
                else:
                    self.assertEqual(assembly.read_bytes(), previous)
                self.assertEqual(layout.read_bytes(), b"previous successful layout\n")
                self.assertEqual(list(directory.glob("*.tmp")), [])

    def test_complete_output_set_and_single_output_wrapper_succeed(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            assembly, layout = directory / "test.asm", directory / "nested" / "layout.json"
            atomic_write(assembly, "previous\n")
            atomic_write_many([(assembly, "new assembly\n"), (layout, "新布局\n")])
            self.assertEqual(assembly.read_bytes(), b"new assembly\n")
            self.assertEqual(layout.read_bytes(), "新布局\n".encode("utf-8"))
            self.assertEqual(list(directory.rglob("*.tmp")), [])

    def test_nasm_observes_the_same_layout(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("NASM is unavailable")
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source, layout = directory / "test.dg", directory / "layout.json"
            source.write_text("module test; struct rax { tag:u8, value:u64 }", encoding="utf-8")
            result = self.run_cli("--emit-layout", layout, source)
            self.assertEqual(result.returncode, 0, result.stderr)
            include = directory / "record.inc"
            result = subprocess.run([sys.executable, "tools/gen_offsets.py", str(layout), str(include), "--type", "test.rax"],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            asm, binary = directory / "probe.asm", directory / "probe.bin"
            asm.write_text('%include "record.inc"\ndq rax_size, rax.tag, rax.value\n', encoding="ascii")
            subprocess.run([nasm, "-f", "bin", "-I", str(directory) + "/", "-o", str(binary), str(asm)], check=True)
            self.assertEqual(struct.unpack("<QQQ", binary.read_bytes()), (16, 0, 8))
