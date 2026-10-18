"""Top-level mutable object syntax remains distinct from local bindings."""
from __future__ import annotations

import unittest

from lang.dongc.frontend import Parser, lex
from lang.dongc.model import CompileError, GlobalDecl, Module, Token


def parse(body):
    return Parser(lex("module globals;" + body, "globals.dg")).parse()


class GlobalParserTests(unittest.TestCase):
    def test_global_objects_have_types_initializers_visibility_and_owner(self):
        module = parse("pub var counter:u64=7;var bytes:[3]u8=[1,2,3];var pointer:*u64=&counter;")
        self.assertEqual(len(module.globals), 3)
        counter, values, pointer = module.globals
        self.assertTrue(all(isinstance(item, GlobalDecl) and item.mutable for item in module.globals))
        self.assertEqual((counter.token.value, counter.typ, counter.public, counter.module, counter.local_name),
                         ("counter", "u64", True, "globals", "counter"))
        self.assertEqual(counter.expr.kind, "integer")
        self.assertEqual((values.typ, values.expr.kind, values.public), ("[3]u8", "array", False))
        self.assertEqual((pointer.typ, pointer.expr.kind, pointer.expr.value), ("*u64", "unary", "&"))
        self.assertEqual(counter.token.path, "globals.dg")
        self.assertIsNone(counter.initializer)

    def test_global_var_requires_both_type_and_initializer(self):
        for declaration in ("var value=1;", "var value:u64;", "pub var value:u64;"):
            with self.subTest(declaration=declaration), self.assertRaises(CompileError) as caught:
                parse(declaration)
            self.assertEqual(caught.exception.code, "E0301")

    def test_other_modifiers_keep_their_original_declaration_scope(self):
        for modifier in ('export("object")', 'extern "sysv64"', "unsafe", "packed", "align(64)"):
            with self.subTest(modifier=modifier), self.assertRaises(CompileError) as caught:
                parse(modifier + " var value:u64=1;")
            self.assertEqual(caught.exception.code, "E0101")
        with self.assertRaises(CompileError) as caught:
            parse("let value:u64=1;")
        self.assertEqual(caught.exception.code, "E0601")

    def test_const_initializers_retain_aggregate_string_and_address_syntax(self):
        module = parse("""
            struct Record{value:u64}
            const record:Record=Record{value:42};
            const text:[]const u8="abc";
            const address:*const u64=&record.value;
        """)
        self.assertEqual([declaration.expr.kind for declaration in module.constants], ["struct", "string", "unary"])
        self.assertEqual(module.constants[2].expr.args[0].kind, "field")
        self.assertTrue(all(declaration.initializer is None for declaration in module.constants))

    def test_local_var_and_old_module_positional_arguments_are_unchanged(self):
        module = parse("var top:u64=1;fn f()void{var value:u64;let copy=top;}")
        self.assertEqual([statement.kind for statement in module.functions[0].body], ["binding", "binding"])
        legacy = Module("legacy", Token("identifier", "legacy", 1, 1), [], [], [], [], [], {})
        self.assertEqual(legacy.globals, [])
        self.assertEqual(legacy.static_objects, [])


if __name__ == "__main__":
    unittest.main()
