"""Modern virtio-blk native PCI/DMA/durable-backend protocol model."""
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
from lang.tests.test_dongc import nasm_flags,tool

ROOT=Path(__file__).resolve().parents[1]
class VirtioBlkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=ROOT/"build/test/p5-virtio/host"/("run-"+uuid.uuid4().hex[:12]);cls.directory.mkdir(parents=True)
        cls.inputs=[ROOT/name for name in ("services/drivers/pci.dg","services/drivers/virtio_pci.dg","services/drivers/virtio_blk.dg","tests/virtio_blk_probe.dg","tests/virtio_blk_probe.c","tests/test_virtio_blk.py")]
        cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory/"source-before.json").write_text(json.dumps(cls.before,indent=2)+"\n")

    @classmethod
    def tearDownClass(cls):
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory/"source-after.json").write_text(json.dumps(after,indent=2)+"\n")
        if after!=cls.before:raise AssertionError("formal VirtIO sources changed during run")

    def command(self,args,directory,name):
        started=time.monotonic();value=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=40)
        (directory/(name+".json")).write_text(json.dumps(dict(command=[str(v) for v in args],returncode=value.returncode,stdout=value.stdout,stderr=value.stderr,seconds=round(time.monotonic()-started,6)),indent=2)+"\n")
        return value

    def compile(self,mode,services=None):
        return compile_file(ROOT/"tests/virtio_blk_probe.dg",roots=[ROOT/"tests",services or ROOT/"services"],mode=mode)

    def native(self,mode,directory,services=None):
        nasm,cc=tool("nasm","NASM"),tool("gcc","CC")
        if not nasm or not cc:self.skipTest("VirtIO native model requires NASM and SysV GCC")
        directory.mkdir(parents=True);asm=directory/"probe.asm";obj=directory/"probe.o";asm.write_text(self.compile(mode,services).assembly)
        value=self.command([nasm,"-f","win64" if os.name=="nt" else "elf64",*nasm_flags(nasm),"-o",str(obj),str(asm)],directory,"assemble");self.assertEqual(0,value.returncode,value.stderr)
        exe=directory/("probe.exe" if os.name=="nt" else "probe")
        value=self.command([cc,"-std=c11","-O2","-Wall","-Wextra","-Werror","-D__USE_MINGW_ANSI_STDIO=1",*(["-mno-sse"] if os.name=="nt" else ["-no-pie"]),str(ROOT/"tests/virtio_blk_probe.c"),str(obj),"-o",str(exe)],directory,"link");self.assertEqual(0,value.returncode,value.stderr)
        return exe

    def test_native_pci_dma_read_write_flush_and_fault_ownership(self):
        for mode in ("debug","release"):
            directory=self.directory/"native"/mode;exe=self.native(mode,directory)
            for scenario in range(13):
                with self.subTest(mode=mode,scenario=scenario):
                    value=self.command([str(exe),str(scenario)],directory,"scenario-"+str(scenario));self.assertEqual(0,value.returncode,value.stdout+value.stderr)
                    self.assertIn("passed",value.stdout) if scenario in (0,8,10,11,12) else self.assertIn("safely retained DMA",value.stdout)

    def test_layout_stack_and_elf_coff(self):
        nasm=tool("nasm","NASM")
        if not nasm:self.skipTest("NASM unavailable")
        for mode in ("debug","release"):
            compiled=self.compile(mode);types={t["full_name"]:t for t in compiled.layout_manifest["types"]}
            for name,size in (("drivers.virtio_blk.State",288),("drivers.virtio_blk.Ops",40),("drivers.virtio_blk.Lease",32),("drivers.virtio_pci.Transport",136),("drivers.pci.Function",88)):
                self.assertEqual(size,types[name]["size"])
            self.assertNotRegex(compiled.assembly.lower(),r"\b(?:xmm|ymm|zmm)[0-9]+\b")
            functions={};current=None
            for line in compiled.assembly.splitlines():
                match=re.match(r"^\$([A-Za-z_][A-Za-z0-9_]*):$",line)
                if match:current=match.group(1);functions[current]={"frame":16,"calls":set()}
                if current:
                    match=re.search(r"\bsub rsp, (\d+)",line)
                    if match:functions[current]["frame"]+=int(match.group(1))
                    match=re.search(r"\bcall \$([A-Za-z_][A-Za-z0-9_]*)\b",line)
                    if match:functions[current]["calls"].add(match.group(1))
            def stack(name,path=()):
                self.assertNotIn(name,path);f=functions[name]
                return f["frame"]+max([stack(child,(*path,name)) for child in f["calls"] if child in functions] or [0])
            maximum=max(stack(name) for name in functions);self.assertLessEqual(maximum,4096)
            directory=self.directory/"formats"/mode;directory.mkdir(parents=True)
            (directory/"stack.json").write_text(json.dumps({"generated_direct_call_path_bytes":maximum,"external_callback_stack_is_caller_contract":True})+"\n")
            asm=directory/"probe.asm";asm.write_text(compiled.assembly)
            for fmt in ("elf64","win64"):
                value=self.command([nasm,"-f",fmt,*nasm_flags(nasm),"-o",str(directory/(fmt+".o")),str(asm)],directory,fmt);self.assertEqual(0,value.returncode,value.stderr)

    def test_wrong_completion_and_premature_dma_release_are_rejected(self):
        original=(ROOT/"services/drivers/virtio_blk.dg").read_text()
        controls={
            "wrong_used_id":("if id != 0 || length != expected || result > 2", "if id != 0 { negative_hit(1); }\n                if length != expected || result > 2",1,"result=="),
            "release_before_reset":("unsafe fn cleanup(state: *State) !void {\n    unsafe {\n        try reset(state);", "unsafe fn cleanup(state: *State) !void {\n    unsafe {\n        negative_hit(2);",7,"status==0&&qenable==0"),
        }
        for kind,(needle,replacement,scenario,assertion) in controls.items():
            self.assertEqual(1,original.count(needle));services=self.directory/"controls"/kind/"services";shutil.copytree(ROOT/"services",services)
            source=original.replace(needle,replacement).replace("module drivers.virtio_blk;",'module drivers.virtio_blk;\nunsafe extern "sysv64" ("vb_negative_hit") fn negative_hit(kind:u64) void;',1)
            (services/"drivers/virtio_blk.dg").write_text(source)
            for mode in ("debug","release"):
                directory=services.parent/mode;exe=self.native(mode,directory,services)
                value=self.command([str(exe),str(scenario)],directory,"negative")
                self.assertNotEqual(0,value.returncode);self.assertEqual(1,value.stderr.count("VBLK_NEGATIVE_HIT"),value.stderr);self.assertIn(assertion,value.stderr)

if __name__=="__main__":unittest.main()
