"""Parser and target-layout contracts for slices, imports and external ABIs."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from lang.dongc.compiler import compile_file
from lang.dongc.frontend import Parser, lex
from lang.dongc.model import CompileError, Token
from lang.dongc.typesys import TypeSystem, element, is_slice, readonly


def parse(source: str, path: str | None = None):
    return Parser(lex("module slice_test; " + source, path)).parse()


class SliceLayoutTests(unittest.TestCase):
    def test_slice_layout_and_element_qualifiers(self):
        types = TypeSystem(parse("struct Item { value: u16 }"))
        for typ, child in [("[]u8", "u8"), ("[]const Item", "Item"),
                           ("[]*const Item", "*const Item"),
                           ("[]const []u8", "[]u8"), ("[][3]Item", "[3]Item")]:
            with self.subTest(type=typ):
                self.assertTrue(is_slice(typ))
                self.assertTrue(types.is_aggregate(typ))
                self.assertEqual(element(typ), child)
                self.assertEqual((types.layout(typ).size, types.layout(typ).alignment), (16, 8))
        self.assertTrue(readonly("[]const Item"))
        self.assertTrue(readonly("*const []Item"))
        self.assertFalse(readonly("[]*const Item"))
        self.assertFalse(readonly("[2]Item"))
        self.assertEqual(types.layout("[3][]const Item").size, 48)

    def test_slice_breaks_recursive_value_layout(self):
        types = TypeSystem(parse("""
            struct Node { tag: u8, children: []Node, parent: *const Node }
            struct Tree { roots: [2][]const Node }
        """))
        self.assertEqual((types.layout("Node").size, types.layout("Node").alignment), (32, 8))
        self.assertEqual(types.layout("Node").fields["children"].offset, 8)
        self.assertEqual(types.layout("Node").fields["parent"].offset, 24)
        self.assertEqual(types.layout("Tree").size, 32)

    def test_invalid_slice_elements_are_validated(self):
        for typ in ("[]void", "[]const void", "[]Missing", "[]*Missing", "[]*void",
                    "[][0]u8", "[][9223372036854775807]u64", "*[]Missing"):
            with self.subTest(type=typ), self.assertRaises(CompileError):
                TypeSystem(parse("")).layout(typ)

    def test_qualified_structure_manifest_preserves_owner(self):
        module = parse("pub struct Item { pub bytes: []const u8, value: u16 }")
        item = module.structs[0]
        item.token = replace(item.token, value="other.items.Item")
        item.module = "other.items"
        entry = TypeSystem(module).manifest()["types"][0]
        self.assertEqual((entry["name"], entry["full_name"]), ("Item", "other.items.Item"))
        self.assertEqual((entry["size"], entry["alignment"]), (24, 8))
        self.assertEqual(entry["fields"][0]["size"], 16)


class SliceParserTests(unittest.TestCase):
    def test_slice_type_nesting_and_qualified_names(self):
        fn = parse("fn f(a: []const item.Record, b: *[]u8, c: [2][]*const item.Record) [][]u8 { return a[..]; }").functions[0]
        self.assertEqual([typ for _, typ in fn.params],
                         ["[]const item.Record", "*[]u8", "[2][]*const item.Record"])
        self.assertEqual(fn.returns, "[][]u8")

    def test_slice_boundaries_retain_omitted_bounds(self):
        body = parse("fn f() void { let a = xs[..]; let b = xs[1..]; let c = xs[..2]; let d = xs[1..2]; let e = xs[1]; }").functions[0].body
        for statement, expected in zip(body[:4], [(None, None), (1, None), (None, 2), (1, 2)]):
            value = statement.expr
            self.assertEqual(value.kind, "slice")
            self.assertEqual(value.args[0].kind, "name")
            self.assertEqual(tuple(arg.value if arg is not None else None for arg in value.args[1:]), expected)
        self.assertEqual(body[4].expr.kind, "index")

    def test_strings_store_utf8_and_escaped_bytes(self):
        fn = parse(r'fn f() void { let a = "中文\n\xFF\0"; let b = ""; }').functions[0]
        self.assertEqual(fn.body[0].expr.kind, "string")
        self.assertEqual(fn.body[0].expr.value, "中文".encode("utf-8") + b"\n\xff\0")
        self.assertEqual(fn.body[1].expr.value, b"")

    def test_raw_slice_builtin_is_a_regular_call(self):
        stmt = parse("fn f() void { unsafe { let s = slice_from_raw_parts(ptr, count); } }").functions[0].body[0].body[0]
        self.assertEqual((stmt.expr.kind, stmt.expr.value), ("call", "slice_from_raw_parts"))
        self.assertEqual([arg.value for arg in stmt.expr.args], ["ptr", "count"])

    def test_imports_visibility_and_qualified_expressions(self):
        module = parse("""
            import core.mem;
            import core.text as text;
            pub struct Record { pub bytes: []const u8, private_field: u8 }
            pub unsafe fn f() void { text.inspect(mem.get()); let r = text.Record { bytes: "" }; }
        """, "entry.dong")
        self.assertEqual([(i.path, i.alias) for i in module.imports], [("core.mem", "mem"), ("core.text", "text")])
        item = module.structs[0]
        self.assertTrue(item.public)
        self.assertEqual((item.module, item.local_name, item.field_public), ("slice_test", "Record", {"bytes"}))
        fn = module.functions[0]
        self.assertTrue(fn.public)
        self.assertTrue(fn.unsafe)
        self.assertEqual((fn.module, fn.local_name, fn.source_path), ("slice_test", "f", "entry.dong"))
        self.assertEqual((fn.body[0].expr.value.kind, fn.body[0].expr.value.value), ("field", "inspect"))
        self.assertEqual(fn.body[1].expr.value, ("text.Record", ["bytes"]))

    def test_external_abis_link_names_and_unbounded_scalar_parameters(self):
        module = parse('''
            extern "sysv64" ("native_read") fn read(p: *u8, n: usize) i64;
            pub extern "win64" fn firmware(a: u64, b: u64, c: u64, d: u64, e: u64, f: u64, g: u64) u64;
            fn ordinary(a: u64, b: u64, c: u64, d: u64, e: u64, f: u64, g: u64) u64 { return g; }
        ''')
        read, firmware, ordinary = module.functions
        self.assertEqual((read.abi, read.export, read.external, read.unsafe, read.body),
                         ("sysv64", "native_read", True, True, []))
        self.assertEqual((firmware.abi, firmware.export, firmware.public, len(firmware.params)),
                         ("win64", "firmware", True, 7))
        self.assertEqual((ordinary.abi, ordinary.external, ordinary.unsafe, len(ordinary.params)),
                         ("sysv64", False, False, 7))

    def test_win64_definition_preserves_abi_and_body(self):
        function = parse('export("callback") extern "win64" fn callback() void {}').functions[0]
        self.assertEqual((function.abi, function.export, function.external, function.unsafe, function.body),
                         ("win64", "callback", False, False, []))

    def test_invalid_declaration_modifiers_and_slice_syntax(self):
        for source in ['extern "other" fn f() void;', 'fn f() void;', 'unsafe struct S { x: u8 }',
                       'extern "sysv64" struct S { x: u8 }', 'pub pub fn f() void {}',
                       'fn f(s: []void) void {}', 'fn f() void { let s = xs[]; }']:
            with self.subTest(source=source), self.assertRaises(CompileError):
                parse(source)


class SourceDiagnosticTests(unittest.TestCase):
    def test_lexer_paths_and_cross_module_error_source(self):
        tokens = lex('module child; fn f() void {}', "child.dong")
        self.assertTrue(all(token.path == "child.dong" for token in tokens))
        error = CompileError("E0201", Token("identifier", "x", 2, 3, "child.dong"),
                             "duplicate x", Token("identifier", "x", 7, 4, "first.dong"))
        error.sources = {"child.dong": "module child;\n  x", "first.dong": ""}
        self.assertEqual(error.format("entry.dong", "irrelevant"),
                         "child.dong:2:3: error[E0201]: duplicate x\n      x\n      ^\nfirst.dong:7:4: note: previous declaration")

    def test_deferred_reference_layout_error_keeps_imported_field_location(self):
        main = "module main; import dep;"
        for prefix in ("*", "[]", "*[]", "[]const "):
            with self.subTest(reference=prefix), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                dependency = "module dep;\nstruct S { values: " + prefix + "[9223372036854775807]u64 }"
                (directory / "main.dg").write_text(main, encoding="utf-8")
                (directory / "dep.dg").write_text(dependency, encoding="utf-8")
                with self.assertRaises(CompileError) as caught:
                    compile_file(directory / "main.dg", roots=[directory])
                error = caught.exception
                self.assertEqual(error.code, "E0302")
                self.assertEqual((error.token.path, error.token.line, error.token.column, error.token.value),
                                 ("dep.dg", 2, 12, "values"))
                diagnostic = error.format("main.dg", main)
                self.assertTrue(diagnostic.startswith("dep.dg:2:12: error[E0302]:"), diagnostic)
                self.assertIn(dependency.splitlines()[1], diagnostic)

    def test_legacy_format_uses_explicit_path_and_source(self):
        error = CompileError("E0101", Token("identifier", "x", 1, 2), "bad token")
        self.assertEqual(error.format("main.dong", " x"),
                         "main.dong:1:2: error[E0101]: bad token\n     x\n     ^")


if __name__ == "__main__":
    unittest.main()
