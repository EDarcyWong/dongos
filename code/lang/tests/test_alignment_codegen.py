"""Encoding and frame-selection checks for local alignments above 16 bytes."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import CompileError, compile_source
from lang.tests.test_dongc import nasm_flags, tool


class AlignmentCodegenTests(unittest.TestCase):
    def assemble(self, assembly):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("alignment encoding checks require NASM")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source, output = directory / "aligned.asm", directory / "aligned.o"
            source.write_text(assembly, encoding="utf-8")
            result = subprocess.run([nasm, "-f", "elf64", *nasm_flags(nasm), "-o", str(output), str(source)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_temporary_alignment_selects_frame_after_body(self):
        text = """module aligned;
            align(64) struct A {value:u64}
            export("ordinary") fn ordinary()u64{return 7;}
            export("temporary") fn temporary()u64{return A{value:42}.value;}
            export("after") fn after()u64{return 9;}
        """
        compiled = compile_source(text)
        ordinary, temporary, after = [compiled.assembly.split("$" + name + ":", 1)[1].split("align 16", 1)[0]
                                      for name in ("ordinary", "temporary", "after")]
        for body in (ordinary, after):
            self.assertNotIn("r12", body)
            self.assertNotIn("and rsp", body)
        self.assertIn("and rsp, -64", temporary)
        self.assertIn("mov r12, rsp", temporary)
        self.assertIn("mov r12, qword [rbp-8]", temporary)
        self.assertNotIn("__DG_FRAME_BASE__", compiled.assembly)
        self.assemble(compiled.assembly)

    def test_realigned_frames_keep_incoming_stack_anchor_and_slice_return(self):
        text = """module aligned;
            align(256) struct A {value:u64}
            extern "win64" fn observe(p:*const A,n:u64,a:u64,b:u64,c:u64)u64;
            export("probe") fn probe(a:u64,b:u64,c:u64,d:u64,e:u64,view:[]u64,z:u64)[]u64{
                let aligned=A{value:a+b+c+d+e+z};
                unsafe{let count=observe(&aligned,view.len,1,2,3);if count==0{return view;}}
                return view[1..];
            }
        """
        compiled = compile_source(text)
        self.assertIn("and rsp, -256", compiled.assembly)
        self.assertIn("qword [rbp+16]", compiled.assembly)
        self.assertIn("qword [rbp+24]", compiled.assembly)
        self.assertIn("mov rdx, qword [rax+8]", compiled.assembly)
        self.assertIn("mov r12, qword [rbp-8]", compiled.assembly)
        self.assertNotIn("[rsp-", compiled.assembly)
        self.assertNotRegex(compiled.assembly, r"\b(?:xmm|ymm|zmm)[0-9]+\b")
        self.assemble(compiled.assembly)

    def test_page_aligned_objects_are_legal_through_pointers(self):
        text = """module aligned;
            align(4096) struct Page {value:u64}
            export("read") fn read(p:*const Page)u64{unsafe{return (*p).value;}}
            export("copy") fn copy(p:*Page,q:*const Page)void{unsafe{*p=*q;}}
            export("copy_two") fn copy_two(p:*[2]Page,q:*const [2]Page)void{unsafe{*p=*q;}}
        """
        compiled = compile_source(text)
        page = compiled.layout_manifest["types"][0]
        self.assertEqual((page["size"], page["alignment"]), (4096, 4096))
        self.assertNotIn("and rsp", compiled.assembly)
        self.assertNotIn("push r12", compiled.assembly)
        self.assertIn("mov rcx, 8192", compiled.assembly)
        self.assemble(compiled.assembly)

    def test_layout_limit_does_not_relax_actual_frame_budget(self):
        for alignment in (2048, 4096):
            with self.subTest(alignment=alignment):
                text = f"module aligned;align({alignment}) struct A{{value:u8}}fn f()void{{var object:A;}}"
                with self.assertRaises(CompileError) as caught:
                    compile_source(text)
                self.assertEqual(caught.exception.code, "E0601")
                self.assertIn("frame", caught.exception.message)
                self.assertIn("4096", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
