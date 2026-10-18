"""UEFI ACPI range policy and persistent inventory, independent native oracle."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest
import uuid

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent
FIELDS = ("rsdp", "xsdt", "madt", "fadt", "hpet", "mcfg", "table_count", "cpu_count", "ioapic_count",
          "iso_count", "nmi_count", "mcfg_count", "lapic_address", "madt_flags", "fadt_flags", "boot_arch",
          "pm_timer_block", "pm_timer_length", "pm_timer_32bit", "hpet_gas_info", "hpet_address",
          "pm_timer_gas_info", "pm_timer_address", "steps")


def stack_chain(assembly):
    starts = list(re.finditer(r"^\$([^\s:]+):\s*$", assembly, re.MULTILINE))
    bodies = {match[1]: assembly[match.end():starts[index + 1].start() if index + 1 < len(starts) else len(assembly)]
              for index, match in enumerate(starts)}
    frames, edges = {}, {}
    reader = "__dg_m" + b"boot.acpi_startup".hex() + "_f" + b"uefi_reader".hex()
    parser_prefix = "__dg_m" + b"firmware.acpi".hex() + "_f"
    for name, body in bodies.items():
        if not re.match(r"\s*push rbp", body):
            continue
        prologue = "\n".join(body.splitlines()[:12])
        allocation = re.search(r"sub rsp, ([0-9]+)", prologue)
        frames[name] = (int(allocation[1]) if allocation else 0) + 16  # saved RBP + return address
        edges[name] = re.findall(r"^\s+call \$([^\s]+)", body, re.MULTILINE)
        if name.startswith(parser_prefix) and re.search(r"^\s+call r[0-9]+", body, re.MULTILINE):
            edges[name].append(reader)  # the real boot Reader supplied to discover

    def longest(name, active):
        if name not in frames:
            return 0, []
        if name in active:
            raise AssertionError("ACPI early-call chain must not recurse")
        child = max((longest(target, active | {name}) for target in edges[name]), default=(0, []))
        return frames[name] + child[0], [name, *child[1]]

    root = "__dg_m" + b"boot.acpi_startup".hex() + "_f" + b"prepare".hex()
    discover = parser_prefix + b"discover".hex()
    if not {root, reader, discover, "as_prepare"} <= frames.keys():
        raise AssertionError("missing known ACPI call-chain functions")
    if not any(reader in targets for name, targets in edges.items() if name.startswith(parser_prefix)):
        raise AssertionError("real ACPI Reader callback edge was not identified")
    total, chain = longest("as_prepare", set())
    return {"bytes": total, "chain": chain, "frames": {name: frames[name] for name in chain}}


class AcpiStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = ROOT / "build/test/acpi-startup/host" / ("run-" + uuid.uuid4().hex[:12])
        cls.evidence.mkdir(parents=True)
        cls.inputs = [Path(__file__), FIXTURES / "acpi_startup_probe.dg", FIXTURES / "acpi_startup_probe.c",
                      ROOT / "kernel/boot/acpi_startup.dg", ROOT / "kernel/firmware/acpi.dg",
                      ROOT / "kernel/firmware/acpi_errors.dg", ROOT / "lang/examples/boot/abi.dg"]
        cls.before = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.inputs}
        (cls.evidence / "source-before.json").write_text(json.dumps(cls.before, indent=2) + "\n")

    @classmethod
    def tearDownClass(cls):
        after = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.inputs}
        (cls.evidence / "source-after.json").write_text(json.dumps(after, indent=2) + "\n")
        if cls.before != after:
            raise AssertionError("ACPI startup inputs changed during this test execution")

    def compile(self, mode, *, kernel=None):
        return compile_file(FIXTURES / "acpi_startup_probe.dg",
                            roots=[FIXTURES, kernel or ROOT / "kernel", ROOT / "lang/examples", ROOT / "lang/std"], mode=mode)

    def command(self, argv, directory, name, *, timeout=30):
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        (directory / (name + ".json")).write_text(json.dumps({"command": argv, "returncode": result.returncode,
                                                              "stdout": result.stdout, "stderr": result.stderr}, indent=2) + "\n")
        return result

    def native(self, mode, directory, *, kernel=None):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        self.assertTrue(nasm and cc, "configured NASM and SysV-capable GCC are required")
        directory.mkdir(parents=True)
        assembly = directory / "probe.asm"
        assembly.write_text(self.compile(mode, kernel=kernel).assembly, encoding="utf-8")
        obj = directory / "probe.o"
        result = self.command([nasm, "-f", "win64" if os.name == "nt" else "elf64", *nasm_flags(nasm),
                               "-o", str(obj), str(assembly)], directory, "assemble")
        self.assertEqual(0, result.returncode, result.stderr)
        executable = directory / ("probe.exe" if os.name == "nt" else "probe")
        command = [cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror"]
        if os.name != "nt":
            command.append("-no-pie")
        result = self.command([*command, str(FIXTURES / "acpi_startup_probe.c"), str(obj), "-o", str(executable)], directory, "link")
        self.assertEqual(0, result.returncode, result.stderr)
        return self.command([str(executable)], directory, "native")

    def test_exact_report_inventory_layout_and_both_object_formats(self):
        nasm = tool("nasm", "NASM")
        self.assertTrue(nasm, "configured NASM is required")
        for mode in ("debug", "release"):
            compiled = self.compile(mode)
            stack = stack_chain(compiled.assembly)
            self.assertLessEqual(stack["bytes"], 4096, stack)
            layouts = {item["full_name"]: item for item in compiled.layout_manifest["types"]}
            report, inventory = layouts["boot.acpi_startup.Report"], layouts["firmware.acpi.Inventory"]
            self.assertEqual((192, 8), (report["size"], report["alignment"]))
            self.assertEqual(list(FIELDS), [field["name"] for field in report["fields"]])
            self.assertEqual(list(range(0, 192, 8)), [field["offset"] for field in report["fields"]])
            self.assertEqual((2456, 8), (inventory["size"], inventory["alignment"]))
            self.assertNotRegex(compiled.assembly.lower(), r"\b(?:xmm|ymm|zmm)[0-9]+\b")
            directory = self.evidence / "formats" / mode
            directory.mkdir(parents=True)
            assembly = directory / "probe.asm"
            assembly.write_text(compiled.assembly, encoding="utf-8")
            (directory / "layout.json").write_text(json.dumps(compiled.layout_manifest, indent=2) + "\n")
            (directory / "stack-chain.json").write_text(json.dumps(stack, indent=2) + "\n")
            for fmt in ("elf64", "win64"):
                result = self.command([nasm, "-f", fmt, *nasm_flags(nasm), "-o", str(directory / (fmt + ".o")),
                                       str(assembly)], directory, fmt)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_native_interval_model_failures_copy_and_callback_reentry(self):
        for mode in ("debug", "release"):
            result = self.native(mode, self.evidence / "native" / mode)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("ACPI UEFI independent coverage model passed", result.stdout)
            self.assertIn("ACPI startup persistent-copy/failure/reentry model passed", result.stdout)

    def test_wrong_type_reader_is_rejected_by_the_independent_native_model(self):
        source = (ROOT / "kernel/boot/acpi_startup.dg").read_text(encoding="utf-8")
        before = "(kind != 9 && kind != 10)"
        self.assertEqual(1, source.count(before))
        directory = self.evidence / "control-wrong-type"
        kernel = directory / "kernel"
        shutil.copytree(ROOT / "kernel", kernel)
        (kernel / "boot/acpi_startup.dg").write_text(source.replace(before, "false", 1), encoding="utf-8")
        for mode in ("debug", "release"):
            result = self.native(mode, directory / mode, kernel=kernel)
            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertIn("ACPI startup failure", result.stderr)
            self.assertNotIn("panic", result.stderr)


if __name__ == "__main__":
    unittest.main()
