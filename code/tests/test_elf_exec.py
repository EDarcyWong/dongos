"""Native static ELF planning and RELATIVE relocation failure controls."""
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

class ElfExecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / "build/test/p4-exec/host" / ("run-" + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [ROOT / name for name in ("kernel/exec/elf.dg", "tests/elf_exec_probe.dg", "tests/elf_exec_probe.c", "tests/test_elf_exec.py")]
        cls.before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / "source-before.json").write_text(json.dumps(cls.before, indent=2) + "\n")

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / "source-after.json").write_text(json.dumps(after, indent=2) + "\n")
        if after != cls.before:
            raise AssertionError("ELF formal inputs changed during run")

    def command(self, args, directory, name):
        start = time.monotonic()
        value = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=40)
        (directory / (name+".json")).write_text(json.dumps(dict(command=[str(v) for v in args],returncode=value.returncode,
            stdout=value.stdout,stderr=value.stderr,elapsed_seconds=round(time.monotonic()-start,6)),indent=2)+"\n")
        return value

    def compile(self, mode, kernel=None):
        return compile_file(ROOT / "tests/elf_exec_probe.dg", roots=[ROOT / "tests", kernel or ROOT / "kernel"], mode=mode)

    def tools(self, native=False):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or native and not cc:
            self.skipTest("ELF oracle requires NASM and SysV GCC")
        return nasm, cc

    def native(self, compiled, directory, nasm, cc):
        directory.mkdir(parents=True)
        asm, obj = directory / "probe.asm", directory / "probe.o"
        asm.write_text(compiled.assembly)
        result = self.command([nasm,"-f","win64" if os.name=="nt" else "elf64",*nasm_flags(nasm),"-o",str(obj),str(asm)],directory,"assemble")
        self.assertEqual(0,result.returncode,result.stderr)
        exe = directory / ("probe.exe" if os.name=="nt" else "probe")
        result = self.command([cc,"-std=c11","-O2","-Wall","-Wextra","-Werror","-D__USE_MINGW_ANSI_STDIO=1",
            *( ["-mno-sse"] if os.name=="nt" else ["-no-pie"] ),str(ROOT / "tests/elf_exec_probe.c"),str(obj),"-o",str(exe)],directory,"link")
        self.assertEqual(0,result.returncode,result.stderr)
        return self.command([str(exe)],directory,"native")

    def test_layout_bounded_stack_and_formats(self):
        nasm,_ = self.tools()
        for mode in ("debug","release"):
            compiled = self.compile(mode)
            types = {item["full_name"]:item for item in compiled.layout_manifest["types"]}
            self.assertEqual(1072,types["exec.elf.Plan"]["size"])
            self.assertEqual(64,types["exec.elf.Segment"]["size"])
            self.assertEqual(16,types["exec.elf.Reloc"]["size"])
            self.assertNotRegex(compiled.assembly.lower(),r"\b(?:xmm|ymm|zmm)[0-9]+\b")
            functions={}; current=None
            for line in compiled.assembly.splitlines():
                match=re.match(r"^\$(__dg_[A-Za-z0-9_]+):$",line)
                if match: current=match.group(1); functions[current]={"frame":16,"calls":set()}
                if current:
                    frame=re.search(r"\bsub rsp, (\d+)",line)
                    if frame: functions[current]["frame"]+=int(frame.group(1))
                    call=re.search(r"\bcall \$(__dg_[A-Za-z0-9_]+)\b",line)
                    if call: functions[current]["calls"].add(call.group(1))
            def stack(name,path=()):
                self.assertNotIn(name,path)
                value=functions[name]
                return value["frame"]+max([stack(child,(*path,name)) for child in value["calls"] if child in functions] or [0])
            maximum=max(stack(name) for name in functions)
            self.assertLessEqual(maximum,4096)
            directory=self.directory/"formats"/mode;directory.mkdir(parents=True)
            (directory/"stack.json").write_text(json.dumps({"max_direct_call_path_bytes":maximum})+"\n")
            asm=directory/"probe.asm";asm.write_text(compiled.assembly)
            for fmt in ("elf64","win64"):
                result=self.command([nasm,"-f",fmt,*nasm_flags(nasm),"-o",str(directory/(fmt+".o")),str(asm)],directory,fmt)
                self.assertEqual(0,result.returncode,result.stderr)

    def test_native_independent_load_relocation_and_rejection_snapshots(self):
        nasm,cc=self.tools(native=True)
        for mode in ("debug","release"):
            result=self.native(self.compile(mode),self.directory/"native"/mode,nasm,cc)
            self.assertEqual(0,result.returncode,result.stdout+result.stderr)
            self.assertRegex(result.stdout,r"elf independent fixture passed checks=\d+ success=\d+ rejected=\d+ full-output-unchanged=\d+")

    def test_wrong_relocation_permission_and_premature_output_are_rejected(self):
        nasm,cc=self.tools(native=True)
        source=(ROOT/"kernel/exec/elf.dg").read_text()
        controls={
            "relocation_to_rx":("if !writable { return error.BadPermissions; }","if !writable { negative_hit(1); }","ELF_NEGATIVE_HIT 1","error==expected"),
            "failed_publish":("if !entry_found || !phdr_found { return error.BadEntry; }","if !entry_found || !phdr_found { negative_hit(2); *out = value; return error.BadEntry; }","ELF_NEGATIVE_HIT 2","memcmp(&before,&guarded.value,sizeof before)==0"),
        }
        for kind,(needle,replacement,hit,assertion) in controls.items():
            self.assertEqual(1,source.count(needle))
            kernel=self.directory/"controls"/kind/"kernel";(kernel/"exec").mkdir(parents=True)
            injected=source.replace(needle,replacement).replace("module exec.elf;",'module exec.elf;\nunsafe extern "sysv64" ("elf_negative_hit") fn negative_hit(kind:u64) void;',1)
            (kernel/"exec/elf.dg").write_text(injected)
            for mode in ("debug","release"):
                result=self.native(self.compile(mode,kernel),kernel.parent/mode,nasm,cc)
                self.assertNotEqual(0,result.returncode)
                self.assertEqual(1,result.stderr.count(hit),result.stderr)
                self.assertIn(assertion,result.stderr)

if __name__=="__main__": unittest.main()
