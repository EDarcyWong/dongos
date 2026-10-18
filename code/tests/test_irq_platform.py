"""Bounded xAPIC register/clock model with native deadline-order control."""
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

class IrqPlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / "build/test/p3-irq/host" / ("run-" + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        names = ("kernel/irq/platform.dg", "kernel/irq/clock_calibration.dg", "kernel/irq/hardware.asm", "kernel/boot/device_policy.dg",
                 "kernel/firmware/acpi.dg", "kernel/firmware/acpi_errors.dg", "tests/irq_platform_probe.dg",
                 "tests/irq_platform_probe.c", "tests/test_irq_platform.py")
        cls.inputs = [ROOT / name for name in names]
        cls.before = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.inputs}
        cls.evidence = {}
        (cls.directory / "source-before.json").write_text(json.dumps(cls.before, indent=2) + "\n")

    @classmethod
    def tearDownClass(cls):
        after = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.inputs}
        (cls.directory / "source-after.json").write_text(json.dumps(after, indent=2) + "\n")
        if after != cls.before:
            raise AssertionError("formal IRQ inputs changed during the run")
        (cls.directory / "validation-summary.json").write_text(json.dumps(dict(source_sha256=after,
            sources_unchanged=True, actual_guest_executed=False, evidence=cls.evidence), indent=2) + "\n", encoding="utf-8")

    def command(self, args, directory, name):
        started = time.monotonic()
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=40)
        (directory / (name + ".json")).write_text(json.dumps(dict(command=[str(v) for v in args],
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
            elapsed_seconds=round(time.monotonic() - started, 6)), indent=2) + "\n", encoding="utf-8")
        return result

    def compile(self, mode, kernel=None):
        return compile_file(ROOT / "tests/irq_platform_probe.dg", roots=[ROOT / "tests", kernel or ROOT / "kernel",
                            ROOT / "lang/std", ROOT / "lang/examples"], mode=mode)

    def tools(self, native=False):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or native and not cc:
            self.skipTest("IRQ native model requires NASM and SysV-capable GCC")
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
                               str(ROOT / "tests/irq_platform_probe.c"), str(obj), "-o", str(binary)], directory, "link")
        self.assertEqual(0, linked.returncode, linked.stdout + linked.stderr)
        return binary

    def test_public_layout_and_both_object_formats(self):
        nasm, _ = self.tools()
        for mode in ("debug", "release"):
            compiled = self.compile(mode)
            types = {item["full_name"]: item for item in compiled.layout_manifest["types"]}
            self.assertEqual((192,8), (types["irq.platform.Report"]["size"], types["irq.platform.Report"]["alignment"]))
            self.assertEqual(88, types["boot.device_policy.Views"]["size"])
            self.assertEqual(448, types["irq.platform.Diagnostic"]["size"])
            self.assertEqual(16, types["irq.platform.DiagnosticCpu"]["size"])
            self.assertEqual(list(range(0,192,8)), [field["offset"] for field in types["irq.platform.Report"]["fields"]])
            self.assertNotRegex(compiled.assembly.lower(), r"\b(?:xmm|ymm|zmm)[0-9]+\b")
            maximum_local = max(map(int, re.findall(r"\bsub rsp, (\d+)", compiled.assembly)))
            self.assertLessEqual(maximum_local, 4096)
            directory = self.directory / "formats" / mode
            directory.mkdir(parents=True)
            asm = directory / "probe.asm"
            asm.write_text(compiled.assembly, encoding="utf-8")
            for fmt in ("elf64", "win64"):
                for name, source in (("probe",asm), ("hardware",ROOT / "kernel/irq/hardware.asm")):
                    result = self.command([nasm, "-f", fmt, *nasm_flags(nasm), "-o", str(directory / (name+"-"+fmt+".o")), str(source)], directory, name+"-"+fmt)
                    self.assertEqual(0, result.returncode, result.stderr)
            self.evidence.setdefault("formats_and_layout", {})[mode] = dict(report_bytes=192, diagnostic_bytes=448,
                maximum_local_reservation_bytes=maximum_local, formats=["elf64", "win64"])

    def test_native_deadline_hpet_pm_wrap_and_fail_closed_models(self):
        nasm, cc = self.tools(native=True)
        for mode in ("debug", "release"):
            directory = self.directory / "native" / mode
            binary = self.native(self.compile(mode), directory, nasm, cc)
            outputs = {}
            for scenario in range(37):
                with self.subTest(mode=mode, scenario=scenario):
                    result = self.command([str(binary), str(scenario)], directory, "scenario-"+str(scenario))
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("model passed scenario="+str(scenario), result.stdout)
                    outputs[str(scenario)] = result.stdout.strip()
            self.evidence.setdefault("independent_register_model", {})[mode] = outputs

    def test_actual_missing_deadline_ordering_is_rejected(self):
        nasm, cc = self.tools(native=True)
        original = (ROOT / "kernel/irq/platform.dg").read_text(encoding="utf-8")
        needle = "arch.mfence(); arch.write_msr(0x6e0,now + cycles);"
        self.assertEqual(1, original.count(needle))
        kernel = self.directory / "control" / "kernel"
        shutil.copytree(ROOT / "kernel", kernel)
        injected = original.replace(needle, "negative_hit(1); arch.write_msr(0x6e0,now + cycles);", 1).replace("module irq.platform;",
            'module irq.platform;\nunsafe extern "sysv64" ("irq_negative_hit") fn negative_hit(kind: u64) void;', 1)
        (kernel / "irq/platform.dg").write_text(injected, encoding="utf-8")
        for mode in ("debug", "release"):
            directory = kernel.parent / mode
            binary = self.native(self.compile(mode,kernel), directory, nasm, cc)
            result = self.command([str(binary), "0"], directory, "negative")
            self.assertNotEqual(0, result.returncode, "actual missing fence incorrectly passed")
            self.assertEqual(1, result.stderr.count("IRQ_NEGATIVE_HIT 1"), result.stderr)
            self.assertIn("fence_seq>lvt_seq", result.stderr)

    def test_actual_omitted_identity_readback_is_rejected(self):
        nasm, cc = self.tools(native=True)
        original = (ROOT / "kernel/irq/platform.dg").read_text(encoding="utf-8")
        needle = "let verified=io_read(index,0);"
        self.assertEqual(1, original.count(needle))
        kernel = self.directory / "no-id-readback" / "kernel"
        shutil.copytree(ROOT / "kernel", kernel)
        injected = original.replace(needle, "negative_hit(2); let verified=planned_ids[index];", 1).replace(
            "module irq.platform;", 'module irq.platform;\nunsafe extern "sysv64" ("irq_negative_hit") fn negative_hit(kind:u64)void;', 1)
        (kernel / "irq/platform.dg").write_text(injected, encoding="utf-8")
        modes = {}
        for mode in ("debug", "release"):
            directory = kernel.parent / mode
            binary = self.native(self.compile(mode,kernel), directory, nasm, cc)
            result = self.command([str(binary), "17"], directory, "negative")
            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertEqual(1, result.stderr.count("IRQ_NEGATIVE_HIT 2"), result.stderr)
            self.assertIn("id_readbacks[i]==1", result.stderr)
            self.assertNotIn("panic", result.stderr)
            modes[mode] = dict(exit=1, actual_marker=2, assertion="id_readbacks[i]==1")
        self.evidence["actual_missing_id_readback_rejected"] = modes

if __name__ == "__main__":
    unittest.main()
