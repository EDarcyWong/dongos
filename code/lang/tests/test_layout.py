"""Independent layout/AST tests: the target layout is shared by checking and NASM."""
from __future__ import annotations

import unittest

from lang.dongc.frontend import Parser, lex
from lang.dongc.model import CompileError, bounds, bits, is_signed
from lang.dongc.typesys import TypeSystem


def parse(source):
    return Parser(lex("module layout_test; " + source)).parse()


class LayoutTests(unittest.TestCase):
    def test_integer_and_bool_layouts(self):
        types = TypeSystem(parse(""))
        for width in (8, 16, 32, 64):
            for sign in "iu":
                name = f"{sign}{width}"
                with self.subTest(name=name):
                    self.assertEqual((types.layout(name).size, types.layout(name).alignment), (width // 8,) * 2)
                    self.assertEqual(bits(name), width)
                    self.assertEqual(is_signed(name), sign == "i")
                    self.assertEqual(bounds(name), (-(1 << (width - 1)), (1 << (width - 1)) - 1)
                                     if sign == "i" else (0, (1 << width) - 1))
        self.assertEqual((types.layout("bool").size, types.layout("bool").alignment), (1, 1))
        self.assertEqual(bounds("usize"), bounds("u64"))

    def test_natural_packed_nested_and_overaligned_layout(self):
        types = TypeSystem(parse("""
            struct Natural { tag: u8, value: u64, tail: u16 }
            packed struct Packed { tag: u8, value: u64, tail: u16 }
            align(4096) struct Page { values: [512]u64 }
            struct Nested { prefix: u8, items: [2]Natural, last: u8 }
        """))
        natural = types.layout("Natural")
        self.assertEqual((natural.size, natural.alignment), (24, 8))
        self.assertEqual({name: field.offset for name, field in natural.fields.items()},
                         {"tag": 0, "value": 8, "tail": 16})
        packed = types.layout("Packed")
        self.assertEqual((packed.size, packed.alignment), (11, 1))
        self.assertEqual(packed.fields["value"].offset, 1)
        self.assertEqual(packed.fields["tail"].offset, 9)
        self.assertEqual((types.layout("Page").size, types.layout("Page").alignment), (4096, 4096))
        nested = types.layout("Nested")
        self.assertEqual((nested.size, nested.alignment), (64, 8))
        self.assertEqual(nested.fields["items"].offset, 8)
        self.assertEqual(nested.fields["last"].offset, 56)

    def test_pointers_break_recursive_layout(self):
        types = TypeSystem(parse("""
            struct Left { next: *const Right, children: *[2]Left }
            struct Right { next: *Left }
        """))
        self.assertEqual(types.layout("Left").size, 16)
        self.assertEqual(types.layout("Right").size, 8)
        self.assertEqual(types.layout("[2]Left").size, 32)
        self.assertTrue(types.is_pointer("*const Right"))
        self.assertTrue(types.readonly("*const Right"))
        self.assertEqual(types.pointee("*const Right"), "Right")
        self.assertEqual(types.element("[2]Left"), "Left")
        self.assertEqual(types.array_length("[2]Left"), 2)

    def test_manifest_contains_offsets_and_field_sizes(self):
        types = TypeSystem(parse("struct S { flag: u8, values: [2]u16 }"))
        manifest = types.manifest()
        self.assertEqual(manifest["schema"], 1)
        self.assertEqual(manifest["module"], "layout_test")
        self.assertEqual(manifest["target"], "x86_64-dongos-elf")
        self.assertEqual(manifest["spec_version"], "0.1")
        self.assertEqual(manifest["types"], [{
            "name": "S", "full_name": "layout_test.S", "kind": "struct", "size": 6, "alignment": 2,
            "fields": [{"name": "flag", "type": "u8", "offset": 0, "size": 1},
                       {"name": "values", "type": "[2]u16", "offset": 2, "size": 4}],
        }])

    def test_invalid_layouts_are_diagnosed(self):
        cases = [
            "struct S {}", "struct S { x: u8, x: u64 }",
            "struct S { x: Missing }", "struct S { x: *Missing }",
            "struct S { x: S }", "struct S { x: [2]S }",
            "struct A { b: B } struct B { a: A }",
            "align(0) struct S { x: u8 }", "align(3) struct S { x: u8 }",
            "align(8192) struct S { x: u8 }", "align(1) struct S { x: u64 }",
            "packed align(8) struct S { x: u8 }",
            "struct S { x: [9223372036854775807]u64 }",
            "struct S { x: [0]u64 }", "struct S { x: *void }",
            "struct S { x: u8 } struct S { y: u16 }", "struct i64 { x: u8 }",
        ]
        for case in cases:
            with self.subTest(source=case), self.assertRaises(CompileError):
                TypeSystem(parse(case))


class AggregateParserTests(unittest.TestCase):
    def test_type_syntax_and_literal_protocol(self):
        module = parse("""
            pub struct Pair { a: u8, b: i16 }
            fn inspect(p: *const Pair, data: [2 + 2]u8) usize {
                var pair: Pair = Pair { b: -2, a: 1 };
                let bytes = [3; 2 * 2];
                let values = [1, 2,];
                unsafe { (*p).b = pair.b as i16; data[1] += 2; }
                return sizeof(Pair) + alignof(Pair) + offsetof(Pair, b);
            }
        """)
        function = module.functions[0]
        self.assertEqual([typ for _, typ in function.params], ["*const Pair", "[4]u8"])
        self.assertEqual(function.returns, "u64")
        constructor = function.body[0].expr
        self.assertEqual((constructor.kind, constructor.value), ("struct", ("Pair", ["b", "a"])))
        repeated = function.body[1].expr
        self.assertEqual((repeated.kind, repeated.value, len(repeated.args)), ("array", 4, 1))
        self.assertEqual((function.body[2].expr.kind, len(function.body[2].expr.args)), ("array", 2))
        unsafe = function.body[3]
        self.assertEqual(unsafe.kind, "unsafe")
        assignment = unsafe.body[0]
        self.assertEqual(assignment.value[0].kind, "field")
        self.assertEqual(assignment.value[0].args[0].value, "*")
        self.assertEqual(assignment.expr.kind, "cast")
        self.assertEqual(unsafe.body[1].value[0].kind, "index")

    def test_address_null_and_cast_precedence(self):
        function = parse("fn f() void { var x: i8 = 1; let p = &x; let q: *i8 = null; let n = -x as u64 * 2; }").functions[0]
        self.assertEqual(function.body[1].expr.value, "&")
        self.assertEqual(function.body[2].expr.kind, "null")
        product = function.body[3].expr
        self.assertEqual(product.value, "*")
        self.assertEqual(product.args[0].kind, "cast")
        self.assertEqual(product.args[0].args[0].value, "-")

    def test_empty_control_blocks_do_not_become_structure_literals(self):
        statements = parse("fn f(flag: bool) void { if flag {} while flag {} }").functions[0].body
        self.assertEqual([stmt.kind for stmt in statements], ["if", "while"])
        self.assertEqual([stmt.expr.kind for stmt in statements], ["name", "name"])

    def test_l1_control_and_enum_features_parse(self):
        cases = [
            "fn f() void { defer f(); }", "fn f() !u64 {}",
            "enum Event { Timer }",
            "fn f()void{for i in 0..2 {}}",
        ]
        for case in cases:
            with self.subTest(source=case):
                parse(case)


if __name__ == "__main__":
    unittest.main()
