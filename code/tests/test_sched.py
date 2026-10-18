"""Bounded priority/wait queues and exact production eager xstate helpers."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]
INPUTS = [ROOT / x for x in ("kernel/sched/core.dg", "kernel/sched/runtime.dg", "kernel/sched/sync.dg",
    "kernel/sched/context.asm", "include/sched.inc", "tests/sched_probe.dg", "tests/sched_probe.c",
    "tests/sched_context_probe.asm", "tests/test_sched.py")]

class SchedulerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = ROOT / "build/test/p3-sched/host" / ("run-" + uuid.uuid4().hex[:12])
        cls.evidence.mkdir(parents=True)
        cls.before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in INPUTS}
        (cls.evidence / "source-before.json").write_text(json.dumps(cls.before, indent=2) + "\n")
    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in INPUTS}
        (cls.evidence / "source-after.json").write_text(json.dumps(after, indent=2) + "\n")
        if after != cls.before:
            raise AssertionError("scheduler source changed during host run")
    def command(self, argv, directory, name):
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=45)
        (directory / (name + ".json")).write_text(json.dumps(dict(command=argv, returncode=result.returncode,
            stdout=result.stdout, stderr=result.stderr), indent=2) + "\n")
        return result
    def compile(self, mode):
        return compile_file(ROOT / "tests/sched_probe.dg", roots=[ROOT / "tests", ROOT / "kernel", ROOT / "lang/std"], mode=mode)
    def assemble(self, source, output, fmt, directory, name):
        n = tool("nasm", "NASM")
        self.assertTrue(n, "configured NASM required")
        result = self.command([n, "-f", fmt, *nasm_flags(n), "-I" + str(ROOT / "include") + os.sep,
            "-o", str(output), str(source)], directory, name)
        self.assertEqual(0, result.returncode, result.stderr)
    def test_layout_and_both_object_formats(self):
        for mode in ("debug", "release"):
            c = self.compile(mode)
            types = {t["full_name"]: t for t in c.layout_manifest["types"]}
            for name, size in (("Engine",448),("Thread",48),("WaitQueue",24)):
                layout = types["sched.core." + name]
                self.assertEqual((size,8),(layout["size"],layout["alignment"]))
            self.assertNotRegex(c.assembly.lower(), r"\b(?:xmm|ymm|zmm)[0-9]+\b")
            # Asynchronous interrupts may occupy all bytes below RSP. The
            # compiler explicitly allocates locals; there is no red-zone use.
            self.assertNotRegex(c.assembly, r"\[rsp\s*-\s*[0-9]")
            directory = self.evidence / ("formats-" + mode);directory.mkdir()
            asm = directory / "probe.asm";asm.write_text(c.assembly)
            for fmt in ("elf64","win64"):
                self.assemble(asm,directory / (fmt + ".o"),fmt,directory,"dong-"+fmt)
                self.assemble(ROOT / "kernel/sched/context.asm",directory / ("context-"+fmt+".o"),fmt,directory,"context-"+fmt)
    def test_native_policy_wait_and_production_xstate(self):
        self.native(negative=False)
    def test_missing_fx_restore_is_observed_by_native_checks(self):
        self.native(negative=True)
    def native(self, *, negative):
        cc = tool("gcc","CC");self.assertTrue(cc,"configured SysV-capable GCC required")
        for mode in ("debug","release"):
            directory = self.evidence / (("missing-restore-" if negative else "")+mode);directory.mkdir()
            asm = directory / "probe.asm";asm.write_text(self.compile(mode).assembly)
            context=ROOT / "kernel/sched/context.asm"
            if negative:
                original=context.read_text()
                self.assertEqual(1,original.count("    fxrstor64 [rdi]"))
                context=directory / "bad-context.asm"
                context.write_text(original.replace("    fxrstor64 [rdi]","    nop ; negative control: deliberately omit actual FX restore"))
                (directory / "mutation.json").write_text(json.dumps(dict(kind="missing-fx-restore",
                    source_sha256=hashlib.sha256(original.encode()).hexdigest(),expected="actual native xstate mismatch"),indent=2)+"\n")
            fmt = "win64" if os.name == "nt" else "elf64"
            objects=[]
            for name,source in (("dong",asm),("context",context),("xstate",ROOT / "tests/sched_context_probe.asm")):
                obj=directory / (name+".o");self.assemble(source,obj,fmt,directory,"assemble-"+name);objects.append(str(obj))
            exe=directory / ("probe.exe" if os.name=="nt" else "probe")
            flags=[] if os.name=="nt" else ["-no-pie"]
            linked=self.command([cc,"-std=c11","-O2","-Wall","-Wextra","-Werror",*flags,
                str(ROOT / "tests/sched_probe.c"),*objects,"-o",str(exe)],directory,"link")
            self.assertEqual(0,linked.returncode,linked.stderr)
            result=self.command([str(exe)],directory,"native")
            if negative:
                self.assertEqual(1,result.returncode,result.stdout+result.stderr)
                self.assertIn("sched check failed line",result.stderr)
                self.assertNotIn("unexpected Dong panic",result.stderr)
            else:
                self.assertEqual(0,result.returncode,result.stdout+result.stderr)
                self.assertRegex(result.stdout,r"scheduler native checks passed [0-9]+ xsave_host=[02]")
