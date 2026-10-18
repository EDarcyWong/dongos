"""ACPI PA-reader parser: independent native fixtures and finite failure controls."""
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

class AcpiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / "build/test/acpi/host" / ("run-" + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [ROOT / name for name in ("kernel/firmware/acpi.dg", "kernel/firmware/acpi_errors.dg",
                                              "tests/acpi_probe.dg", "tests/acpi_probe.c", "tests/test_acpi.py")]
        cls.before = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.inputs}
        (cls.directory / "source-before.json").write_text(json.dumps(cls.before, indent=2) + "\n")

    @classmethod
    def tearDownClass(cls):
        after = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.inputs}
        (cls.directory / "source-after.json").write_text(json.dumps(after, indent=2) + "\n")
        if after != cls.before:
            raise AssertionError("formal ACPI inputs changed during the run")

    def command(self, args, directory, name):
        started = time.monotonic()
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=40)
        (directory / (name + ".json")).write_text(json.dumps(dict(command=[str(v) for v in args],
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
            elapsed_seconds=round(time.monotonic() - started, 6)), indent=2) + "\n", encoding="utf-8")
        return result

    def compile(self, mode, kernel=None):
        return compile_file(ROOT / "tests/acpi_probe.dg", roots=[ROOT / "tests", kernel or ROOT / "kernel", ROOT / "lang/std"], mode=mode)

    def tools(self, native=False):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or native and not cc:
            self.skipTest("ACPI native oracle requires NASM and SysV-capable GCC")
        return nasm, cc

    def native(self, compiled, directory, nasm, cc):
        directory.mkdir(parents=True)
        asm, obj = directory / "probe.asm", directory / "probe.o"
        asm.write_text(compiled.assembly, encoding="utf-8")
        assembled = self.command([nasm, "-f", "win64" if os.name == "nt" else "elf64", *nasm_flags(nasm), "-o", str(obj), str(asm)], directory, "assemble")
        self.assertEqual(0, assembled.returncode, assembled.stderr)
        binary = directory / ("probe.exe" if os.name == "nt" else "probe")
        flags = ["-mno-sse"] if os.name == "nt" else ["-no-pie"]
        linked = self.command([cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-D__USE_MINGW_ANSI_STDIO=1", *flags,
                               str(ROOT / "tests/acpi_probe.c"), str(obj), "-o", str(binary)], directory, "link")
        self.assertEqual(0, linked.returncode, linked.stdout + linked.stderr)
        return self.command([str(binary)], directory, "native")

    def test_public_layout_formats_and_bounded_stack(self):
        nasm, _ = self.tools()
        for mode in ("debug", "release"):
            compiled = self.compile(mode)
            types = {item["full_name"]: item for item in compiled.layout_manifest["types"]}
            self.assertEqual((2456, 8), (types["firmware.acpi.Inventory"]["size"], types["firmware.acpi.Inventory"]["alignment"]))
            self.assertLess(types["firmware.acpi.Inventory"]["size"], 3000)
            self.assertEqual(40, types["firmware.acpi.Gas"]["size"])
            self.assertEqual([i * 8 for i in range(28)], [item["offset"] for item in types["firmware.acpi.Inventory"]["fields"][:28]])
            self.assertTrue({"firmware.acpi", "firmware.acpi_errors", "acpi_probe"}.issubset(compiled.manifest()["modules"]))
            self.assertNotRegex(compiled.assembly.lower(), r"\b(?:xmm|ymm|zmm)[0-9]+\b")
            directory = self.directory / "formats" / mode
            directory.mkdir(parents=True)
            asm = directory / "probe.asm"
            asm.write_text(compiled.assembly, encoding="utf-8")
            # A deliberately conservative bound: discover's frame plus the sum
            # of all helper frames exceeds every actual acyclic call path.
            # Compute the tighter actual direct-call graph from emitted code.
            functions = {}
            function = None
            for line in compiled.assembly.splitlines():
                match = re.match(r"^\$(__dg_[A-Za-z0-9_]+):$", line)
                if match:
                    function = match.group(1)
                    functions[function] = {"frame": 16, "calls": set()}
                if function is not None:
                    frame = re.search(r"\bsub rsp, (\d+)", line)
                    if frame:
                        functions[function]["frame"] += int(frame.group(1))
                    call = re.search(r"\bcall \$(__dg_[A-Za-z0-9_]+)\b", line)
                    if call:
                        functions[function]["calls"].add(call.group(1))
            discover = [name for name in functions if name.endswith("_f" + "discover".encode().hex())]
            self.assertEqual(1, len(discover), list(functions))
            def stack(name, path=()):
                self.assertNotIn(name, path, "unexpected parser recursion")
                value = functions[name]
                return value["frame"] + max([stack(child, (*path, name)) for child in value["calls"] if child in functions] or [0])
            maximum = stack(discover[0])
            self.assertLessEqual(maximum, 4096, maximum)
            (directory / "stack.json").write_text(json.dumps({"parser_call_path_upper_bound": maximum,
                "external_reader_frame_is_caller_contract": True, "functions": {k: {"frame": v["frame"], "calls": sorted(v["calls"])} for k, v in functions.items()}}, indent=2) + "\n")
            for fmt in ("elf64", "win64"):
                result = self.command([nasm, "-f", fmt, *nasm_flags(nasm), "-o", str(directory / (fmt + ".o")), str(asm)], directory, fmt)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_native_independent_inventory_and_failure_snapshots(self):
        nasm, cc = self.tools(native=True)
        for mode in ("debug", "release"):
            result = self.native(self.compile(mode), self.directory / "native" / mode, nasm, cc)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertRegex(result.stdout, r"acpi independent fixture passed: checks=\d+ success=\d+ rejected=\d+ full-output-unchanged=\d+")

    def test_original_unknown_checksum_and_failure_output_controls_are_rejected(self):
        nasm, cc = self.tools(native=True)
        original = (ROOT / "kernel/firmware/acpi.dg").read_text(encoding="utf-8")
        # Only temporary copies: one bypasses an unknown table's real checksum;
        # another writes output before the final required-table rejection.
        controls = {
            "unknown_checksum_bypass": ("try checksum(raw,length);", "if u32_at(raw,0) != 0x5453_4554 { try checksum(raw,length); } else if length == 40 && u8_at(raw,36) == 0x5d { negative_hit(1); }"),
            "premature_output": ("if value.madt == 0 || value.fadt == 0", "*out = value;\n        if value.madt == 0 || value.fadt == 0 { negative_hit(2); }\n        if value.madt == 0 || value.fadt == 0"),
        }
        for kind, (needle, replacement) in controls.items():
            self.assertEqual(1, original.count(needle))
            kernel = self.directory / "controls" / kind / "kernel"
            (kernel / "firmware").mkdir(parents=True)
            injected = original.replace(needle, replacement, 1).replace("module firmware.acpi;",
                'module firmware.acpi;\nunsafe extern "sysv64" ("acpi_negative_hit") fn negative_hit(kind: u64) void;', 1)
            (kernel / "firmware/acpi.dg").write_text(injected, encoding="utf-8")
            shutil.copyfile(ROOT / "kernel/firmware/acpi_errors.dg", kernel / "firmware/acpi_errors.dg")
            for mode in ("debug", "release"):
                result = self.native(self.compile(mode, kernel), kernel.parent / mode, nasm, cc)
                self.assertNotEqual(0, result.returncode, "actual wrong parser incorrectly passed independent fixture")
                if kind == "unknown_checksum_bypass":
                    self.assertEqual(1, result.stderr.count("ACPI_NEGATIVE_HIT kind=1"))
                    self.assertIn("error==expected_error", result.stderr)
                    self.assertIn("got 0x0 expected 0x3010005", result.stderr)
                else:
                    self.assertEqual(1, result.stderr.count("ACPI_NEGATIVE_HIT kind=2"))
                    self.assertIn("memcmp(out,&before,sizeof *out)==0", result.stderr)

if __name__ == "__main__":
    unittest.main()
