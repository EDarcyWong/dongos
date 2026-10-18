"""Static object sections and 64-bit relocations checked in real ELF objects."""
from __future__ import annotations

from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from lang.dongc import CompileError, compile_source
from lang.dongc.emitter import Emitter
from lang.dongc.model import Expr, Function, Module, StaticObject, StaticRelocation, Stmt, Token
from lang.dongc.typesys import TypeSystem
from lang.tests.test_dongc import nasm_flags, tool


def elf_sections(data):
    header = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
    offset, stride, count, strings_index = header[6], header[11], header[12], header[13]
    headers = [struct.unpack_from("<IIQQQQIIQQ", data, offset + stride * index) for index in range(count)]
    strings_header = headers[strings_index]
    strings = data[strings_header[4]:strings_header[4] + strings_header[5]]
    result = {}
    for section in headers:
        name = strings[section[0]:].split(b"\0", 1)[0].decode("ascii")
        result[name] = (section, data[section[4]:section[4] + section[5]])
    return result


class GlobalCodegenTests(unittest.TestCase):
    def assemble(self, assembly):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("static object encoding checks require NASM")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asm, output = directory / "static.asm", directory / "static.o"
            asm.write_text(assembly, encoding="utf-8")
            result = subprocess.run([nasm, "-f", "elf64", *nasm_flags(nasm), "-o", str(output), str(asm)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return output.read_bytes()

    def emit_objects(self, objects, expression=None, path="statics.dg"):
        token = Token("identifier", "statics", 1, 1)
        functions = [] if expression is None else [Function(token, [], expression.typ,
            [Stmt(token, "return", expr=expression)], None, symbol="probe")]
        module = Module("statics", token, functions)
        module.type_system = TypeSystem(module)
        module.static_objects = objects
        return Emitter(module, path, "debug").compile().assembly

    def test_real_object_section_flags_alignment_and_full_width_relocations(self):
        assembly = self.emit_objects([
            StaticObject("target", "u64", b"\x2a" + bytes(7), 4096),
            StaticObject("constant_zero", "u64", bytes(8), 8),
            StaticObject("pointers", "[2]*u8", bytes(16), 8, True,
                         [StaticRelocation(0, "target", 4294967297), StaticRelocation(8, "target", -4294967297)]),
            StaticObject("zero", "[64]u8", bytes(64), 64, True),
        ])
        sections = elf_sections(self.assemble(assembly))
        rodata, data, bss = (sections[name][0] for name in (".rodata", ".data", ".bss"))
        # ELF SHF_WRITE=1, SHF_ALLOC=2, SHT_NOBITS=8; these are binary ABI facts.
        self.assertEqual(rodata[2] & 3, 2)
        self.assertEqual((data[2] & 3, bss[2] & 3), (3, 3))
        self.assertEqual((rodata[8], data[8], bss[8]), (4096, 8, 64))
        self.assertEqual((bss[1], bss[5]), (8, 64))
        relocations = []
        for header, contents in sections.values():
            if header[1] == 4:  # SHT_RELA
                relocations.extend(struct.unpack_from("<QQq", contents, offset)
                                   for offset in range(0, len(contents), header[9]))
        self.assertEqual([item[1] & 0xffffffff for item in relocations], [1, 1])  # R_X86_64_64
        self.assertEqual(sorted(item[2] for item in relocations), [-4294967297, 4294967297])

    def test_source_globals_and_const_references_assemble_without_local_realignment(self):
        compiled = compile_source(r"""module globalcode;
            align(4096) struct Page {value:u64}
            var page:Page=Page{value:0};
            var counter:u64=5;
            var zero:[3]u16=[0;3];
            const values:[2]u64=[10,20];
            const pointer:*const u64=&values[1];
            const text:[]const u8="董\0x";
            export("probe") fn probe()u64{
                counter+=1;zero[1]=7;page.value=42;
                unsafe{return counter+(zero[1] as u64)+*pointer+(text[0] as u64);}
            }
        """)
        sections = elf_sections(self.assemble(compiled.assembly))
        self.assertNotIn("and rsp", compiled.assembly)
        self.assertEqual(sections[".bss"][0][8], 4096)
        self.assertGreaterEqual(sections[".bss"][0][5], 4096)
        self.assertIn("董".encode("utf-8") + b"\0x", sections[".rodata"][1])
        self.assertIn("section .data", compiled.assembly)

    def test_static_data_budget_is_enforced_before_text_expansion(self):
        with self.assertRaises(CompileError) as caught:
            self.emit_objects([StaticObject("too_large", "[16777217]u8", bytes(16777217), 1)])
        self.assertEqual(caught.exception.code, "E0601")
        self.assertIn("16 MiB", caught.exception.message)

    def test_runtime_strings_and_panic_paths_share_the_static_budget(self):
        token = Token("string", "x", 1, 1)
        full = StaticObject("full", "[16777216]u8", bytes(16777216), 1)
        string = Expr(token, "string", b"x", typ="[]const u8")
        one = lambda: Expr(token, "integer", 1, typ="u64", constant=1)
        checked_division = Expr(token, "binary", "/", [one(), one()], typ="u64")
        for expression in (string, checked_division):
            with self.subTest(kind=expression.kind):
                with self.assertRaises(CompileError) as caught:
                    self.emit_objects([full], expression, path="x")
                self.assertEqual(caught.exception.code, "E0601")
                self.assertIn("16 MiB", caught.exception.message)

    def test_large_runtime_literal_is_rejected_before_byte_text_expansion(self):
        class ExpansionGuard(bytes):
            def __iter__(self):
                raise AssertionError("over-budget byte data was expanded before validation")
        data = ExpansionGuard(b"ab" * (8 * 1024 * 1024 + 1))
        string = Expr(Token("string", "large", 1, 1), "string", data, typ="[]const u8")
        with self.assertRaises(CompileError) as caught:
            self.emit_objects([], string)
        self.assertEqual(caught.exception.code, "E0601")

    def test_large_uniform_data_emission_stays_compact(self):
        assembly = self.emit_objects([StaticObject("large", "[16777216]u8", bytes(16777216), 1)])
        self.assertLess(len(assembly), 1000)
        self.assertIn("16777216", assembly)


if __name__ == "__main__":
    unittest.main()
