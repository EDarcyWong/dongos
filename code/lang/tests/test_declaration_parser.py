"""Syntax contracts for transparent aliases and typed compile-time constants."""
from __future__ import annotations

import unittest

from lang.dongc.frontend import Parser, lex
from lang.dongc.model import AliasDecl, CompileError, ConstDecl, Expr, Module, Token


def parse(source: str):
    return Parser(lex("module declarations; " + source, path="declarations.dg")).parse()


class DeclarationParserTests(unittest.TestCase):
    def test_alias_target_shapes_and_visibility(self):
        module = parse("""
            type Word = u16;
            pub type View = []const Word;
            type External = dependency.Record;
            type Buffer = [4]*const External;
            type Empty = void;
        """)
        self.assertEqual([(alias.token.value, alias.target, alias.public) for alias in module.aliases],
                         [("Word", "u16", False), ("View", "[]const Word", True),
                          ("External", "dependency.Record", False), ("Buffer", "[4]*const External", False),
                          ("Empty", "void", False)])
        for alias in module.aliases:
            self.assertIsInstance(alias, AliasDecl)
            self.assertEqual((alias.module, alias.local_name, alias.token.path),
                             ("declarations", alias.token.value, "declarations.dg"))

    def test_void_alias_can_name_a_return_type_but_void_is_not_direct_local_storage(self):
        module = parse("type Done = void; fn finish() Done {}")
        self.assertEqual(module.aliases[0].target, "void")
        self.assertEqual(module.functions[0].returns, "Done")
        with self.assertRaises(CompileError) as caught:
            parse("fn f() void { var value: void; }")
        self.assertEqual(caught.exception.code, "E0302")

    def test_constant_initializers_retain_names_types_and_layout_expressions(self):
        module = parse("""
            pub const COUNT: usize = 4;
            const ENABLED: bool = true;
            const NEXT: u16 = (COUNT + 2) as u16;
            const BYTES: usize = sizeof(Item) + alignof(Item) + offsetof(Item, value);
            const IMPORTED: u64 = limits.MAX;
        """)
        self.assertEqual([constant.typ for constant in module.constants], ["u64", "bool", "u16", "u64", "u64"])
        count, enabled, next_, bytes_, imported = module.constants
        self.assertTrue(count.public)
        self.assertFalse(enabled.public)
        self.assertEqual((count.expr.kind, count.expr.value), ("integer", 4))
        self.assertEqual((enabled.expr.kind, enabled.expr.value), ("boolean", True))
        self.assertEqual((next_.expr.kind, next_.expr.value), ("cast", "u16"))
        self.assertEqual(next_.expr.args[0].args[0].value, "COUNT")
        self.assertEqual(bytes_.expr.kind, "binary")
        self.assertEqual(bytes_.expr.args[1].value, ("offsetof", "Item", "value"))
        self.assertEqual((imported.expr.kind, imported.expr.value, imported.expr.args[0].value),
                         ("field", "MAX", "limits"))
        for constant in module.constants:
            self.assertIsInstance(constant, ConstDecl)
            self.assertEqual((constant.module, constant.local_name, constant.token.path),
                             ("declarations", constant.token.value, "declarations.dg"))

    def test_dynamic_type_lengths_have_module_owned_expression_entries(self):
        module = parse("""
            type Block = [COUNT + 1]u8;
            struct S { one: [sizeof(Block)]u8, many: [COUNT][limits.N]u16 }
            fn f(a: *[COUNT]Block) void { let b: [COUNT]u8 = [0; COUNT]; }
        """)
        self.assertEqual(module.aliases[0].target, "[@0]u8")
        self.assertEqual([typ for _, typ in module.structs[0].fields], ["[@1]u8", "[@2][@3]u16"])
        self.assertEqual(module.functions[0].params[0][1], "*[@4]Block")
        self.assertEqual(module.functions[0].body[0].value[1], "[@5]u8")
        self.assertEqual(list(module.type_lengths), ["@0", "@1", "@2", "@3", "@4", "@5"])
        self.assertEqual((module.type_lengths["@0"].kind, module.type_lengths["@0"].value), ("binary", "+"))
        self.assertEqual(module.type_lengths["@1"].value, ("sizeof", "Block", None))
        self.assertEqual(module.type_lengths["@3"].kind, "field")
        repeated = module.functions[0].body[0].expr
        self.assertEqual(repeated.kind, "array")
        self.assertIsInstance(repeated.value, Expr)
        self.assertEqual((repeated.value.kind, repeated.value.value), ("name", "COUNT"))

    def test_numeric_counts_and_alignment_preserve_legacy_immediate_values(self):
        module = parse("""
            type Fixed = [(2 + 3) * 2]u8;
            align(1 << 4) struct S { data: [4]u64 }
            fn f() void { let a = [0; 2 * 3]; }
        """)
        self.assertEqual(module.aliases[0].target, "[10]u8")
        self.assertEqual(module.structs[0].alignment, 16)
        self.assertEqual(module.functions[0].body[0].expr.value, 6)
        self.assertEqual(module.type_lengths, {})

    def test_deferred_alignment_repeat_and_nested_layout_counts(self):
        module = parse("""
            align(PAGE_SIZE) struct S { bytes: [sizeof([COUNT]u16)]u8 }
            fn f() void { let a = [0; sizeof(S) as usize]; }
        """)
        alignment = module.structs[0].alignment
        self.assertIsInstance(alignment, Expr)
        self.assertEqual((alignment.kind, alignment.value), ("name", "PAGE_SIZE"))
        self.assertEqual(module.structs[0].fields[0][1], "[@1]u8")
        self.assertEqual(module.type_lengths["@0"].value, "COUNT")
        self.assertEqual(module.type_lengths["@1"].value, ("sizeof", "[@0]u16", None))
        count = module.functions[0].body[0].expr.value
        self.assertEqual((count.kind, count.value, count.args[0].value), ("cast", "u64", ("sizeof", "S", None)))

    def test_non_scalar_initializers_are_preserved_for_semantic_checking(self):
        module = parse("""
            const TEXT: []const u8 = "hello";
            const VALUES: [2]u8 = [1, 2];
            const ADDRESS: *u8 = &target;
            const RESULT: u64 = compute();
        """)
        self.assertEqual([constant.expr.kind for constant in module.constants], ["string", "array", "unary", "call"])

    def test_declaration_syntax_errors_and_modifiers_are_rejected(self):
        for source in ["const N = 1;", "const N: u64;", "type A u64;", "type A = u64",
                       'export("A") type A = u64;', 'extern "sysv64" const N: u64 = 1;',
                       "unsafe type A = u64;", "packed type A = u64;", "align(N) const X: u64 = 0;"]:
            with self.subTest(source=source), self.assertRaises(CompileError):
                parse(source)

    def test_local_constants_globals_and_unsupported_alias_forms_stay_explicit(self):
        for source in ["let N: u64 = 1;",
                       "fn f() void { type Word = u64; }"]:
            with self.subTest(source=source), self.assertRaises(CompileError) as caught:
                parse(source)
            self.assertEqual(caught.exception.code, "E0601")

    def test_invalid_numeric_counts_still_fail_during_parsing(self):
        for source in ["type A = [0]u8;", "type A = [-1]u8;", "type A = [1 / 0]u8;",
                       "type A = [9223372036854775808]u8;", "fn f() void { let a = [0; 0]; }"]:
            with self.subTest(source=source), self.assertRaises(CompileError) as caught:
                parse(source)
            self.assertEqual(caught.exception.code, "E0302")

    def test_module_positional_constructor_retains_existing_fields(self):
        token = Token("identifier", "legacy", 1, 1)
        module = Module("legacy", token, [], [], [])
        self.assertEqual((module.aliases, module.constants, module.type_lengths), ([], [], {}))


if __name__ == "__main__":
    unittest.main()
