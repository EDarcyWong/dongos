"""Capability generations and real guarded IPC state transitions."""
from __future__ import annotations
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
INPUTS=[ROOT/p for p in ("kernel/ipc/handles.dg","kernel/ipc/core.dg","tests/ipc_probe.dg","tests/ipc_probe.c","tests/test_ipc.py")]
class IpcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence=ROOT/"build/test/p4-ipc/host"/("run-"+uuid.uuid4().hex[:12]);cls.evidence.mkdir(parents=True)
        cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in INPUTS}
        (cls.evidence/"source-before.json").write_text(json.dumps(cls.before,indent=2)+"\n")
    @classmethod
    def tearDownClass(cls):
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in INPUTS}
        (cls.evidence/"source-after.json").write_text(json.dumps(after,indent=2)+"\n")
        if after!=cls.before:raise AssertionError("IPC sources changed during host verification")
    def compile(self,mode,kernel=None):return compile_file(ROOT/"tests/ipc_probe.dg",roots=[ROOT/"tests",kernel or ROOT/"kernel",ROOT/"lang/std"],mode=mode)
    def command(self,argv,d,name):
        r=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=45)
        (d/(name+".json")).write_text(json.dumps(dict(command=argv,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+"\n")
        return r
    def assemble(self,src,out,fmt,d,name):
        n=tool("nasm","NASM");self.assertTrue(n,"configured NASM required")
        r=self.command([n,"-f",fmt,*nasm_flags(n),"-o",str(out),str(src)],d,name);self.assertEqual(0,r.returncode,r.stderr)
    def test_layouts_and_both_formats(self):
        expected={"ipc.handles.Table":1296,"ipc.handles.Entry":40,"ipc.handles.View":24,"ipc.core.Endpoint":552,
            "ipc.core.Message":80,"ipc.core.Notification":24,"ipc.core.MemoryObject":48,"ipc.core.Region":24}
        for mode in ("debug","release"):
            c=self.compile(mode);layouts={x["full_name"]:x for x in c.layout_manifest["types"]}
            for name,size in expected.items():self.assertEqual((size,8),(layouts[name]["size"],layouts[name]["alignment"]))
            d=self.evidence/("formats-"+mode);d.mkdir();src=d/"probe.asm";src.write_text(c.assembly)
            for fmt in ("elf64","win64"):self.assemble(src,d/(fmt+".o"),fmt,d,fmt)
    def native(self,negative=False):
        cc=tool("gcc","CC");self.assertTrue(cc,"configured SysV GCC required")
        for mode in ("debug","release"):
            d=self.evidence/(("bad-tail-" if negative else "")+mode);d.mkdir();kernel=None
            if negative:
                kernel=d/"kernel";(kernel/"ipc").mkdir(parents=True)
                for name in ("handles.dg","core.dg"):(kernel/"ipc"/name).write_bytes((ROOT/"kernel/ipc"/name).read_bytes())
                target=kernel/"ipc/core.dg";source=target.read_text();needle="        (*out).length = bytes.len as u64;"
                self.assertEqual(1,source.count(needle));target.write_text(source.replace(needle,needle+"\n        (*out).bytes[63] = 0x5a;"))
                (d/"mutation.json").write_text(json.dumps(dict(kind="actual-short-message-tail-write",expected="independent exact message bytes reject"),indent=2)+"\n")
            src=d/"probe.asm";src.write_text(self.compile(mode,kernel).assembly);obj=d/"probe.o"
            self.assemble(src,obj,"win64" if os.name=="nt" else "elf64",d,"assemble")
            exe=d/("probe.exe" if os.name=="nt" else "probe");flags=[] if os.name=="nt" else ["-no-pie"]
            r=self.command([cc,"-std=c11","-O2","-Wall","-Wextra","-Werror",*flags,str(ROOT/"tests/ipc_probe.c"),str(obj),"-o",str(exe)],d,"link")
            self.assertEqual(0,r.returncode,r.stderr);r=self.command([str(exe)],d,"native")
            if negative:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn("IPC check failed line",r.stderr)
            else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertRegex(r.stdout,r"IPC native checks passed [0-9]+")
    def test_native_independent_handles_and_guarded_lifecycle(self):self.native()
    def test_actual_short_message_tail_corruption_is_rejected(self):self.native(negative=True)
