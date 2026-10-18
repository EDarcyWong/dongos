"""Safe native validation/capture/copy ABI; privileged entry is root QEMU only."""
from __future__ import annotations
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
FILES=[ROOT/p for p in ("kernel/user/context.asm","kernel/user/abi.dg","include/user_context.inc","tests/user_context_probe.dg","tests/user_context_probe.asm","tests/user_context_probe.c","tests/test_user_context.py")]
class UserContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence=ROOT/"build/test/p4-user/host"/("run-"+uuid.uuid4().hex[:12]);cls.evidence.mkdir(parents=True)
        cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in FILES}
        (cls.evidence/"source-before.json").write_text(json.dumps(cls.before,indent=2)+"\n")
    @classmethod
    def tearDownClass(cls):
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in FILES}
        (cls.evidence/"source-after.json").write_text(json.dumps(after,indent=2)+"\n")
        if after!=cls.before:raise AssertionError("user boundary sources changed during host checks")
    def command(self,argv,d,name):
        r=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=45)
        (d/(name+".json")).write_text(json.dumps(dict(command=argv,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+"\n")
        return r
    def assemble(self,src,out,fmt,d,name):
        n=tool("nasm","NASM");self.assertTrue(n,"configured NASM required")
        r=self.command([n,"-f",fmt,*nasm_flags(n),"-I"+str(ROOT/"include")+os.sep,"-o",str(out),str(src)],d,name)
        self.assertEqual(0,r.returncode,r.stderr)
    def test_both_formats_and_exact_syscall_sequence(self):
        d=self.evidence/"formats";d.mkdir()
        for fmt in ("elf64","win64"):
            self.assemble(ROOT/"kernel/user/context.asm",d/(fmt+".o"),fmt,d,fmt)
            self.assemble(ROOT/"tests/user_context_probe.asm",d/("probe-"+fmt+".o"),fmt,d,"probe-"+fmt)
        text=(ROOT/"kernel/user/context.asm").read_text()
        instructions="\n".join(line.split(";",1)[0] for line in text.splitlines())
        self.assertRegex(instructions,r"user_syscall_entry:\s+swapgs\s+lfence\s+mov \[gs:UserCpu.user_stack\], rsp\s+mov rsp, \[gs:UserCpu.kernel_stack\]")
        self.assertNotRegex(text.lower(),r"\b(?:xmm|ymm|zmm)[0-9]+\b")
        self.assertIn("0x0020000800000000",text)
    def test_dong_frame_matches_all_assembly_and_c_offsets(self):
        fields="r15 r14 r13 r12 r11 r10 r9 r8 rdi rsi rbp rdx rcx rbx rax rip rflags rsp cr3 fs_base gs_base status syscalls exit_code reserved".split()
        for mode in ("debug","release"):
            c=compile_file(ROOT/"tests/user_context_probe.dg",roots=[ROOT/"tests",ROOT/"kernel"],mode=mode)
            layout=next(t for t in c.layout_manifest["types"] if t["full_name"]=="user.abi.Frame")
            self.assertEqual((200,8),(layout["size"],layout["alignment"]))
            self.assertEqual(fields,[f["name"] for f in layout["fields"]])
            self.assertEqual(list(range(0,200,8)),[f["offset"] for f in layout["fields"]])
            d=self.evidence/("dong-"+mode);d.mkdir();src=d/"probe.asm";src.write_text(c.assembly)
            for fmt in ("elf64","win64"):self.assemble(src,d/(fmt+".o"),fmt,d,fmt)
    def native(self,negative=False,interrupt_negative=False):
        d=self.evidence/("bad-interrupt-mask" if interrupt_negative else "bad-top" if negative else "native");d.mkdir()
        src=ROOT/"kernel/user/context.asm"
        if negative:
            text=src.read_text();needle="    cmp rdx, rcx\n    jae .bad";self.assertEqual(2,text.count(needle))
            src=d/"bad-context.asm";src.write_text(text.replace(needle,"    cmp rdx, rcx\n    nop ; negative: allow invalid high user address",1))
            (d/"mutation.json").write_text(json.dumps(dict(kind="missing-user-rip-upper-bound",expected="actual native invalid address accepted and rejected by oracle"),indent=2)+"\n")
        if interrupt_negative:
            text=src.read_text();needle="mov r8d, USER_INTERRUPT_RFLAGS_ALLOWED";self.assertEqual(1,text.count(needle))
            src=d/"bad-context.asm";src.write_text(text.replace(needle,"mov r8d, USER_RFLAGS_ALLOWED"))
            (d/"mutation.json").write_text(json.dumps(dict(kind="reject-legitimate-interrupted-df-rf",expected="actual IRQ validator rejects captured backward-copy flags"),indent=2)+"\n")
        fmt="win64" if os.name=="nt" else "elf64";objs=[]
        for name,path in (("context",src),("probe",ROOT/"tests/user_context_probe.asm")):
            obj=d/(name+".o");self.assemble(path,obj,fmt,d,"assemble-"+name);objs.append(str(obj))
        cc=tool("gcc","CC");self.assertTrue(cc,"configured GCC required")
        exe=d/("probe.exe" if os.name=="nt" else "probe");flags=[] if os.name=="nt" else ["-no-pie"]
        r=self.command([cc,"-std=c11","-O2","-Wall","-Wextra","-Werror",*flags,str(ROOT/"tests/user_context_probe.c"),*objs,"-o",str(exe)],d,"link")
        self.assertEqual(0,r.returncode,r.stderr);r=self.command([str(exe)],d,"native")
        if negative or interrupt_negative:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn("user context check failed line",r.stderr)
        else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertRegex(r.stdout,r"user context native checks passed [0-9]+")
    def test_native_frame_registers_and_exact_copy_guards(self):self.native()
    def test_invalid_high_return_control_is_rejected(self):self.native(True)
    def test_interrupt_direction_and_resume_flags_are_preserved(self):self.native(interrupt_negative=True)
