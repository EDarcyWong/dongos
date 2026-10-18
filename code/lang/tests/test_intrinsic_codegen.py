"""Instruction width and side-effect lowering checks for the L1 intrinsics."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from lang.dongc import compile_source
from lang.tests.test_dongc import nasm_flags, tool

INTEGER_TYPES = [f"{sign}{width}" for sign in "ui" for width in (8, 16, 32, 64)]
WIDTH = {8: "byte", 16: "word", 32: "dword", 64: "qword"}
ACCUMULATOR = {8: "al", 16: "ax", 32: "eax", 64: "rax"}


def body(assembly, symbol):
    return assembly.split("$" + symbol + ":", 1)[1].split("\nalign 16\n", 1)[0]


def target_accesses(text):
    return [line.strip() for line in text.splitlines() if "[r11]" in line and not line.lstrip().startswith(";")]


class IntrinsicCodegenTests(unittest.TestCase):
    def assemble_both_formats(self, assembly):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("intrinsic instruction encoding checks require NASM")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asm = directory / "intrinsics.asm"
            asm.write_text(assembly, encoding="utf-8")
            for output_format in ("elf64", "win64"):
                result = subprocess.run([nasm, "-f", output_format, *nasm_flags(nasm), "-o", str(directory / (output_format + ".o")), str(asm)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrapping_uses_modular_operations_and_normalizes_every_width(self):
        source = "module intrinsic;"
        for typ in INTEGER_TYPES:
            for name in ("add", "sub", "mul"):
                source += f'export("{name}_{typ}") fn {name}_{typ}(a:{typ},b:{typ}){typ}{{return wrapping_{name}(a,b);}}'
        normalizations = {"u8": "movzx eax, al", "i8": "movsx rax, al", "u16": "movzx eax, ax",
                          "i16": "movsx rax, ax", "u32": "mov eax, eax", "i32": "movsxd rax, eax"}
        for mode in ("debug", "release"):
            compiled = compile_source(source, mode=mode)
            self.assertEqual(compiled.runtime_symbols, [])
            self.assertNotIn("__dong_panic", compiled.assembly)
            for typ in INTEGER_TYPES:
                for name, instruction in (("add", "add"), ("sub", "sub"), ("mul", "imul")):
                    with self.subTest(mode=mode, type=typ, operation=name):
                        generated = body(compiled.assembly, name + "_" + typ)
                        self.assertIn(instruction + " rax, r10", generated)
                        self.assertNotRegex(generated, r"\bj(?:o|c|a|b|l|g)e?\b")
                        if typ in normalizations:
                            self.assertIn(normalizations[typ], generated)
            self.assemble_both_formats(compiled.assembly)

    def test_volatile_and_unaligned_target_access_is_once_at_exact_width(self):
        source, expected = "module intrinsic;", {}
        for typ in INTEGER_TYPES:
            bits = int(typ[1:])
            width = WIDTH[bits]
            if bits == 64:
                read = "mov rax, qword [r11]"
            elif typ == "i32":
                read = "movsxd rax, dword [r11]"
            elif bits == 32:
                read = "mov eax, dword [r11]"
            else:
                read = f"{'movsx rax' if typ.startswith('i') else 'movzx eax'}, {width} [r11]"
            for intrinsic in ("volatile_load", "read_unaligned"):
                symbol = intrinsic + "_" + typ
                source += f'export("{symbol}") fn {symbol}(p:*const {typ}){typ}{{unsafe{{return {intrinsic}(p);}}}}'
                expected[symbol] = read
            for intrinsic in ("volatile_store", "write_unaligned"):
                symbol = intrinsic + "_" + typ
                source += f'export("{symbol}") fn {symbol}(p:*{typ},v:{typ})void{{unsafe{{{intrinsic}(p,v);}}}}'
                expected[symbol] = f"mov {width} [r11], {ACCUMULATOR[bits]}"
        for mode in ("debug", "release"):
            compiled = compile_source(source, mode=mode)
            self.assertEqual(compiled.runtime_symbols, [])
            for symbol, instruction in expected.items():
                with self.subTest(mode=mode, function=symbol):
                    self.assertEqual(target_accesses(body(compiled.assembly, symbol)), [instruction])
            self.assertNotRegex(compiled.assembly, r"\b(?:lock|mfence|lfence|sfence|xmm[0-9]+)\b")
            self.assemble_both_formats(compiled.assembly)

    def test_atomics_use_consistent_seq_cst_mapping_and_return_old_values(self):
        source, expected = "module intrinsic;", {}
        for typ, width, register in (("u32", "dword", "eax"), ("u64", "qword", "rax")):
            for intrinsic, parameters, arguments, returns in (
                ("atomic_load", "", "", typ),
                ("atomic_store", f",v:{typ}", ",v", "void"),
                ("atomic_compare_exchange", f",expected:{typ},desired:{typ}", ",expected,desired", typ),
                ("atomic_fetch_add", f",delta:{typ}", ",delta", typ),
            ):
                symbol = intrinsic + "_" + typ
                source += f'export("{symbol}") fn {symbol}(p:*{typ}{parameters}){returns}{{unsafe{{' + ("return " if returns != "void" else "") + f'{intrinsic}(p{arguments});}}}}'
            expected["atomic_load_" + typ] = f"mov {register}, {width} [r11]"
            expected["atomic_store_" + typ] = f"xchg {width} [r11], {register}"
            expected["atomic_compare_exchange_" + typ] = f"lock cmpxchg {width} [r11], {'r10d' if typ == 'u32' else 'r10'}"
            expected["atomic_fetch_add_" + typ] = f"lock xadd {width} [r11], {register}"
        for mode in ("debug", "release"):
            compiled = compile_source(source, mode=mode)
            self.assertEqual(compiled.runtime_symbols, [])
            for symbol, instruction in expected.items():
                with self.subTest(mode=mode, function=symbol):
                    generated = body(compiled.assembly, symbol)
                    self.assertEqual(target_accesses(generated), [instruction])
                    if symbol in ("atomic_compare_exchange_u32", "atomic_fetch_add_u32"):
                        self.assertIn("mov eax, eax", generated)
            self.assertNotRegex(compiled.assembly, r"\b(?:mfence|lfence|sfence|xmm[0-9]+)\b")
            self.assemble_both_formats(compiled.assembly)

    def test_intrinsic_arguments_finish_once_in_source_order_before_target_access(self):
        compiled = compile_source("""module intrinsic;
            var value:u32=0;
            export("argument_pointer") fn pointer()*u32{return &value;}
            export("argument_expected") fn expected()u32{return 7;}
            export("argument_desired") fn desired()u32{return 9;}
            export("ordered") fn ordered()u32{
                unsafe{return atomic_compare_exchange(pointer(),expected(),desired());}
            }
        """)
        generated = body(compiled.assembly, "ordered")
        calls = re.findall(r"call \$([A-Za-z_0-9]+)", generated)
        self.assertEqual(calls, ["argument_pointer", "argument_expected", "argument_desired"])
        self.assertGreater(generated.index("lock cmpxchg"), generated.index("call $argument_desired"))
        after_arguments = generated.split("; intrinsic atomic_compare_exchange", 1)[1]
        self.assertRegex(after_arguments, r"mov r11, qword \[rbp-[0-9]+\]")
        self.assertEqual(target_accesses(generated), ["lock cmpxchg dword [r11], r10d"])
        self.assemble_both_formats(compiled.assembly)

    def test_compiler_fence_adds_no_cpu_instruction_and_preserves_volatile_order(self):
        empty = compile_source('module intrinsic;export("probe") fn f()void{}')
        fenced = compile_source('module intrinsic;export("probe") fn f()void{unsafe{compiler_fence();}}')
        instructions = lambda text: re.findall(r"^    [a-z][^\n]*", text, re.MULTILINE)
        self.assertEqual(instructions(empty.assembly), instructions(fenced.assembly))
        self.assertIn("compiler barrier: compiler_fence", fenced.assembly)
        ordered = compile_source('module intrinsic;fn f(p:*u32)void{unsafe{volatile_store(p,1);compiler_fence();volatile_store(p,2);}}')
        first, second = [match.start() for match in re.finditer("; intrinsic volatile_store", ordered.assembly)]
        self.assertLess(first, ordered.assembly.index("compiler barrier: compiler_fence"))
        self.assertLess(ordered.assembly.index("compiler barrier: compiler_fence"), second)
        self.assertEqual(target_accesses(ordered.assembly), ["mov dword [r11], eax", "mov dword [r11], eax"])
        self.assemble_both_formats(ordered.assembly)


if __name__ == "__main__":
    unittest.main()
