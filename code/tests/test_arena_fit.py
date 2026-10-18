"""Pure arena feasibility matches independently enumerated pool/stack pairs."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=Path(__file__).parent


def compile_probe(mode):
    return compile_file(FIXTURES/"arena_fit_probe.dg",roots=[FIXTURES,ROOT/"kernel",ROOT/"lang/std"],mode=mode)


class ArenaFitTests(unittest.TestCase):
    def test_both_modes_layouts_and_elf64_coff(self):
        nasm=tool("nasm","NASM")
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            for mode in ("debug","release"):
                compiled=compile_probe(mode)
                layout=next(t for t in compiled.layout_manifest["types"] if t["full_name"]=="mm.memory_map.PageRange")
                self.assertEqual((16,8),(layout["size"],layout["alignment"]))
                self.assertEqual([0,8],[f["offset"] for f in layout["fields"]])
                if not nasm:continue
                asm=path/(mode+".asm");asm.write_text(compiled.assembly,encoding="utf-8")
                for fmt in ("elf64","win64"):
                    with self.subTest(mode=mode,format=fmt):
                        result=subprocess.run([nasm,"-f",fmt,*nasm_flags(nasm),"-o",str(path/(mode+fmt+".o")),str(asm)],capture_output=True,text=True,timeout=30)
                        self.assertEqual(0,result.returncode,result.stderr)
            if not nasm:self.skipTest("ELF/COFF assembly requires NASM; layouts checked")

    def test_native_independent_pair_enumeration(self):
        nasm,cc=tool("nasm","NASM"),tool("gcc","CC")
        if not nasm or not cc:self.skipTest("native arena fit requires NASM and SysV-capable GCC")
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            for mode in ("debug","release"):
                with self.subTest(mode=mode):
                    asm=path/(mode+".asm");asm.write_text(compile_probe(mode).assembly,encoding="utf-8")
                    obj=path/(mode+".o");exe=path/(mode+(".exe" if os.name=="nt" else ""))
                    result=subprocess.run([nasm,"-f","win64" if os.name=="nt" else "elf64",*nasm_flags(nasm),"-o",str(obj),str(asm)],capture_output=True,text=True,timeout=30)
                    self.assertEqual(0,result.returncode,result.stderr)
                    cmd=[cc,"-std=c11","-O0" if mode=="debug" else "-O2","-fno-omit-frame-pointer","-D__USE_MINGW_ANSI_STDIO=1","-Wall","-Wextra","-Werror"]
                    if os.name!="nt":cmd+=["-no-pie"]
                    result=subprocess.run(cmd+[str(FIXTURES/"arena_fit_probe.c"),str(obj),"-o",str(exe)],capture_output=True,text=True,timeout=30)
                    self.assertEqual(0,result.returncode,result.stderr)
                    result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
                    self.assertEqual(0,result.returncode,result.stdout+result.stderr)
                    self.assertIn("arena fit probe ok: 6010 maps",result.stdout)


if __name__=="__main__":unittest.main()
