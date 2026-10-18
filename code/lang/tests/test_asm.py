"""Restricted instruction grammar, emitted machine code and host-safe execution."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import CompileError, compile_source
from lang.tests.test_dongc import nasm_flags, tool


INSTRUCTIONS = {"cli": b"\xfa", "sti": b"\xfb", "hlt": b"\xf4", "pause": b"\xf3\x90",
                "int3": b"\xcc", "lfence": b"\x0f\xae\xe8", "sfence": b"\x0f\xae\xf8",
                "mfence": b"\x0f\xae\xf0"}


class AsmTests(unittest.TestCase):
    def test_whitelist_assembles_to_actual_instructions(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("instruction encoding verification requires NASM")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for instruction, encoding in INSTRUCTIONS.items():
                with self.subTest(instruction=instruction):
                    compiled = compile_source("module test; fn f()void{unsafe{asm{" + instruction + "}}}")
                    self.assertEqual(compiled.runtime_symbols, [])
                    source = directory / "probe.asm"
                    source.write_text(compiled.assembly, encoding="utf-8")
                    for object_format in ("elf64", "win64"):
                        output = directory / (object_format + ".o")
                        result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm),
                                                 "-o", str(output), str(source)], capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertIn(encoding, output.read_bytes())

    def test_requires_explicit_unsafe_block_including_unsafe_function(self):
        for prefix in ("", "unsafe "):
            with self.subTest(prefix=prefix):
                with self.assertRaises(CompileError) as caught:
                    compile_source("module test; " + prefix + "fn f()void{asm{pause}}")
                self.assertEqual(caught.exception.code, "E0501")
        compile_source("module test; fn f()void{unsafe{{asm{pause}}}}")

    def test_rejects_text_operands_directives_and_multiple_instructions(self):
        invalid = ("", "nop", "ret", "push rax", "jmp target", "mov rax, 1", "pause pause",
                   "pause;", "pause\ncli", "pause: cli", '"pause"', "db 144", "bits 32",
                   "lock xadd", "PAUSE", "lfence rax", "{pause}")
        for instruction in invalid:
            with self.subTest(instruction=instruction):
                with self.assertRaises(CompileError) as caught:
                    compile_source("module test; fn f()void{unsafe{asm{" + instruction + "}}}")
                self.assertEqual(caught.exception.code, "E0601")
        compile_source("module test; fn f()void{unsafe{asm{/* comment */ pause // comment\n}}}")

    def test_instruction_blocks_are_statements_and_fall_through(self):
        invalid = ("fn f()u64{unsafe{let x=asm{pause};}return 1;}",
                   "fn f()u64{unsafe{asm{hlt}}}", "asm{pause}")
        for declaration in invalid:
            with self.subTest(declaration=declaration):
                with self.assertRaises(CompileError):
                    compile_source("module test; " + declaration)

    def test_host_safe_fences_and_pause_preserve_values_and_memory(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native asm execution requires NASM and GCC")
        source = '''module probe;
            export("result") fn result(p:*u64,n:u64)u64 {
                var i:u64=0;
                while i<n { unsafe { asm{pause} } i+=1; }
                unsafe {
                    *p=i;
                    asm{sfence}
                    asm{mfence}
                    asm{lfence}
                    if *p!=n {return 0;}
                    *p+=3;
                    return *p;
                }
            }'''
        harness = '''#include <stdint.h>
            #include <stdlib.h>
            extern uint64_t __attribute__((sysv_abi)) result(uint64_t*,uint64_t);
            void __attribute__((sysv_abi,noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t z)
                {(void)k;(void)l;(void)f;(void)z;abort();}
            int main(void){uint64_t x=99;return result(&x,7)==10 && x==10 ? 0:1;}
            '''
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            c_file = directory / "probe.c"
            c_file.write_text(harness, encoding="utf-8")
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    asm, obj = directory / "probe.asm", directory / "probe.o"
                    exe = directory / ("probe.exe" if os.name == "nt" else "probe")
                    asm.write_text(compile_source(source, mode=mode).assembly, encoding="utf-8")
                    result = subprocess.run([nasm, "-f", "win64" if os.name == "nt" else "elf64",
                                             *nasm_flags(nasm), "-o", str(obj), str(asm)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                             str(c_file), str(obj), "-o", str(exe)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
