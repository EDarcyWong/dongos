"""Native SysV stack-switch probes plus ELF64/COFF assembly checks."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from lang.tests.test_dongc import tool,nasm_flags

ROOT=Path(__file__).resolve().parents[1]


class StackBridgeTests(unittest.TestCase):
    def test_elf64_coff_and_plain_bridge(self):
        nasm=tool("nasm","NASM")
        if not nasm:
            self.skipTest("stack bridge assembly requires NASM")
        with tempfile.TemporaryDirectory() as tmp:
            for fmt in ("elf64","win64"):
                for testing in (False,True):
                    with self.subTest(format=fmt,testing=testing):
                        cmd=[nasm,"-f",fmt,*nasm_flags(nasm)]
                        if testing:cmd+=["-DSTACK_BRIDGE_TEST=1"]
                        result=subprocess.run(cmd+["-o",str(Path(tmp)/(fmt+str(testing)+".o")),str(ROOT/"kernel/stack_bridge.asm")],capture_output=True,text=True,timeout=30)
                        self.assertEqual(0,result.returncode,result.stderr)

    def test_native_o0_o2_stack_alignment_flags_nested_and_failure(self):
        nasm,cc=tool("nasm","NASM"),tool("gcc","CC")
        if not nasm or not cc:
            self.skipTest("native stack bridge requires NASM and SysV-capable GCC")
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);obj=path/"bridge.o"
            result=subprocess.run([nasm,"-f","win64" if os.name=="nt" else "elf64",*nasm_flags(nasm),"-DSTACK_BRIDGE_TEST=1","-o",str(obj),str(ROOT/"kernel/stack_bridge.asm")],capture_output=True,text=True,timeout=30)
            self.assertEqual(0,result.returncode,result.stderr)
            for mode in ("O0","O2"):
                with self.subTest(mode=mode):
                    exe=path/(mode+(".exe" if os.name=="nt" else ""))
                    cmd=[cc,"-std=c11","-"+mode,"-fno-omit-frame-pointer","-D__USE_MINGW_ANSI_STDIO=1","-Wall","-Wextra","-Werror"]
                    if os.name!="nt":cmd+=["-no-pie"]
                    result=subprocess.run(cmd+[str(ROOT/"tests/stack_bridge_probe.c"),str(obj),"-o",str(exe)],capture_output=True,text=True,timeout=30)
                    self.assertEqual(0,result.returncode,result.stderr)
                    result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
                    self.assertEqual(0,result.returncode,result.stdout+result.stderr)
                    self.assertIn("stack bridge probe ok",result.stdout)


if __name__=="__main__":unittest.main()
