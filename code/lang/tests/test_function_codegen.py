"""Function-value calls and full Win64 bridge encoding and frame budgets."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from lang.dongc import CompileError, compile_source
from lang.tests.test_dongc import nasm_flags, tool


def function_body(assembly, symbol):
    return assembly.split("$" + symbol + ":", 1)[1].split("\nalign 16\n", 1)[0]


class FunctionCodegenTests(unittest.TestCase):
    def assemble_both_formats(self, assembly):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("function pointer and bridge encoding checks require NASM")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asm = directory / "functions.asm"
            asm.write_text(assembly, encoding="utf-8")
            for output_format in ("elf64", "win64"):
                result = subprocess.run([nasm, "-f", output_format, *nasm_flags(nasm), "-o", str(directory / (output_format + ".o")), str(asm)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_callee_is_evaluated_and_saved_before_each_argument(self):
        source = """module pointers;
            type Binary=fn(u64,u64)u64;
            fn first(a:u64,b:u64)u64{return a+b;}
            fn second(a:u64,b:u64)u64{return a*b;}
            var selected:Binary=first;
            export("fetch") fn fetch()Binary{return selected;}
            export("argument1") fn argument1()u64{selected=second;return 2;}
            export("argument2") fn argument2()u64{return 3;}
            export("invoke") fn invoke()u64{unsafe{return fetch()(argument1(),argument2());}}
        """
        for mode in ("debug", "release"):
            compiled = compile_source(source, mode=mode)
            generated = function_body(compiled.assembly, "invoke")
            self.assertEqual(re.findall(r"call (\$[A-Za-z_0-9]+|r11)", generated),
                             ["$fetch", "$argument1", "$argument2", "r11"])
            snapshot = re.search(r"call \$fetch\n    mov qword (\[rbp-[0-9]+\]), rax", generated)
            self.assertIsNotNone(snapshot)
            self.assertIn("mov r11, qword " + snapshot[1] + "\n    call r11", generated)
            self.assertGreater(generated.index("call $argument1"), snapshot.end())
            self.assemble_both_formats(compiled.assembly)

    def test_static_only_and_runtime_external_function_values_declare_externs(self):
        source = """module pointers;
            extern "sysv64" fn external(value:u64)u64;
            extern "sysv64" fn unused()void;
            const callback:unsafe fn(u64)u64=external;
            export("address") fn address()unsafe fn(u64)u64{return external;}
        """
        compiled = compile_source(source)
        self.assertEqual(compiled.assembly.count("extern $external"), 1)
        self.assertIn("dq $external", compiled.assembly)
        self.assertIn("lea rax, [rel $external]", compiled.assembly)
        self.assertNotIn("extern $unused", compiled.assembly)
        self.assertNotIn("call $external", compiled.assembly)
        self.assemble_both_formats(compiled.assembly)
        static_only = compile_source('module pointers;extern "sysv64" fn external()void;const f:unsafe fn()void=external;')
        self.assertIn("extern $external", static_only.assembly)
        self.assertIn("dq $external", static_only.assembly)
        self.assemble_both_formats(static_only.assembly)

    def test_win64_bridge_preserves_full_nonvolatile_set_and_marshals_stack(self):
        source = """module pointers;
            export("callback") extern "win64" fn callback(a:u64,b:u64,c:u64,d:u64,e:u64,f:u64,g:u64,h:u64)u64{
                return a+b+c+d+e+f+g+h;
            }
            export("direct") fn direct()u64{unsafe{return callback(1,2,3,4,5,6,7,8);}}
        """
        compiled = compile_source(source)
        wrapper = function_body(compiled.assembly, "callback")
        internal = "__dg_bridge_" + b"callback".hex()
        body = function_body(compiled.assembly, internal)
        self.assertIn("call $" + internal, wrapper)
        self.assertIn("mov qword [rbp-8], rdi", wrapper)
        self.assertIn("mov qword [rbp-16], rsi", wrapper)
        self.assertIn("mov rdi, qword [rbp-8]", wrapper)
        self.assertIn("mov rsi, qword [rbp-16]", wrapper)
        for register in range(6, 16):
            self.assertRegex(wrapper, rf"movdqu \[rbp-[0-9]+\], xmm{register}\b")
            self.assertRegex(wrapper, rf"movdqu xmm{register}, \[rbp-[0-9]+\]")
        self.assertEqual(wrapper.count("movdqu"), 20)
        self.assertNotIn("xmm", body)
        for instruction in ("mov rdi, rcx", "mov rsi, rdx", "mov rdx, r8", "mov rcx, r9",
                            "mov r8, qword [rbp+48]", "mov r9, qword [rbp+56]",
                            "mov rax, qword [rbp+64]", "mov rax, qword [rbp+72]"):
            self.assertIn(instruction, wrapper)
        self.assertIn("mov qword [rsp+0], rax", wrapper)
        self.assertIn("mov qword [rsp+8], rax", wrapper)
        after_call = wrapper.split("call $" + internal, 1)[1]
        self.assertNotRegex(after_call, r"\b(?:rax|eax|ax|al)\b")
        direct = function_body(compiled.assembly, "direct")
        self.assertIn("sub rsp, 64", direct)
        self.assertIn("mov qword [rsp+32], rax", direct)
        self.assertIn("mov qword [rsp+56], rax", direct)
        self.assertIn("call $callback", direct)
        self.assemble_both_formats(compiled.assembly)

    def test_indirect_sysv_slice_rollback_and_win64_field_call(self):
        source = """module pointers;
            type SliceCall=fn(u64,u64,u64,u64,u64,[]u64,u64)[]u64;
            type WinCall=extern "win64" fn(u64,u64,u64,u64,u64)u64;
            struct Table{function:WinCall}
            export("slice_call") fn slice_call(f:SliceCall,s:[]u64)[]u64{
                unsafe{return f(1,2,3,4,5,s,6);}
            }
            export("field_call") fn field_call(t:*const Table)u64{unsafe{return (*t).function(1,2,3,4,5);}}
        """
        compiled = compile_source(source)
        sysv = function_body(compiled.assembly, "slice_call")
        win64 = function_body(compiled.assembly, "field_call")
        self.assertIn("sub rsp, 16", sysv)
        self.assertIn("mov qword [rsp+8], rax", sysv)
        self.assertRegex(sysv, r"mov r9, qword \[rbp-[0-9]+\]")
        self.assertIn("mov rdx, qword [rax+8]", sysv)
        self.assertIn("call r11", sysv)
        self.assertIn("sub rsp, 48", win64)
        self.assertIn("mov qword [rsp+32], rax", win64)
        self.assertIn("call r11", win64)
        self.assemble_both_formats(compiled.assembly)

    def test_bridge_and_body_share_one_4096_byte_budget(self):
        params = ",".join(f"p{i}:u64" for i in range(8))
        cases = [
            ("", "", 3888),
            ("", params, 3808),
            ("align(64) struct A{byte:u8}", "", 3760),
        ]
        for prefix, parameters, limit in cases:
            for extra in (0, 16):
                with self.subTest(prefix=prefix, parameters=parameters, extra=extra):
                    local = "var aligned:A;" if prefix else ""
                    source = f'module budget;{prefix}extern "win64" fn callback({parameters})void{{{local}var reserve:[{limit + extra}]u8;}}'
                    if extra:
                        with self.assertRaises(CompileError) as caught:
                            compile_source(source)
                        self.assertEqual(caught.exception.code, "E0601")
                        self.assertIn("4112", caught.exception.message)
                    else:
                        self.assemble_both_formats(compile_source(source).assembly)

    def test_body_outgoing_shadow_also_counts_with_the_bridge(self):
        for reserve, valid in ((3856, True), (3872, False)):
            source = f'module budget;extern "win64" fn target()void;extern "win64" fn callback()void{{var reserve:[{reserve}]u8;unsafe{{target();}}}}'
            with self.subTest(reserve=reserve):
                if valid:
                    self.assemble_both_formats(compile_source(source).assembly)
                else:
                    with self.assertRaises(CompileError) as caught:
                        compile_source(source)
                    self.assertEqual(caught.exception.code, "E0601")
                    self.assertIn("4112", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
