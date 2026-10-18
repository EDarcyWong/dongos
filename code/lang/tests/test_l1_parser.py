"""The complete v1 statement and tagged-value syntax has a stable AST."""
from __future__ import annotations

from pathlib import Path
import unittest

from lang.dongc.frontend import Parser, lex
from lang.dongc.model import CompileError, function_signature


def parsed(declarations):
    return Parser(lex("module syntax; " + declarations)).parse()


class L1ParserTests(unittest.TestCase):
    def test_methods_keep_receiver_as_first_abi_parameter(self):
        module = parsed("struct Page{x:u64}pub unsafe fn(page:*Page)clear(value:u8)void{unsafe{(*page).x=value as u64;}}")
        function = module.functions[0]
        self.assertEqual(("clear", True, True), (function.local_name, function.public, function.unsafe))
        self.assertEqual(("page", "*Page"), (function.receiver[0].value, function.receiver[1]))
        self.assertEqual([("page", "*Page"), ("value", "u8")], [(token.value, typ) for token, typ in function.params])

    def test_optional_result_void_and_noreturn_type_forms(self):
        module = parsed("type A=?u8;type B=!*const u8;type C=!void;type F=unsafe fn(?u8,!u16)!void;fn stop()noreturn{loop{}}")
        self.assertEqual(["?u8", "!*const u8", "!void", "unsafe fn(?u8,!u16)!void"], [item.target for item in module.aliases])
        self.assertEqual("noreturn", module.functions[0].returns)
        signature = function_signature(module.aliases[-1].target)
        self.assertEqual((("?u8", "!u16"), "!void"), (signature.params, signature.returns))

    def test_enum_variants_and_explicit_error_numbers(self):
        module = parsed("pub enum Event{Timer,Key(u8),Shutdown,}enum Plain{A,B}pub error Missing=1;error Invalid=2+1;")
        self.assertEqual([("Timer", None), ("Key", "u8"), ("Shutdown", None)], [(token.value, typ) for token, typ in module.enums[0].variants])
        self.assertTrue(module.enums[0].public)
        self.assertEqual([("Missing", 1, True), ("Invalid", 3, False)], [(item.local_name, item.code, item.public) for item in module.errors])

    def test_enum_payload_arity_and_explicit_tags_are_rejected(self):
        for source in ("enum E{A(u8,u16)}", "enum E{A=3}"):
            with self.subTest(source=source), self.assertRaises(CompileError) as caught:
                parsed(source)
            self.assertEqual("E0601", caught.exception.code)

    def test_loop_and_both_for_forms_preserve_once_evaluated_sources(self):
        module = parsed("fn f()void{loop{break;}for i in lower()..upper(){continue;}for byte in values()[1..]{consume(byte);}}")
        loop, ranged, sequence = module.functions[0].body
        self.assertEqual(("loop", "break"), (loop.kind, loop.body[0].kind))
        self.assertEqual(("for", "i", "range"), (ranged.kind, ranged.value.value, ranged.expr.kind))
        self.assertEqual(["call", "call"], [arg.kind for arg in ranged.expr.args])
        self.assertEqual(("byte", "slice", "call"), (sequence.value.value, sequence.expr.kind, sequence.expr.args[0].kind))

    def test_defer_call_and_block_are_explicit_statement_lists(self):
        module = parsed("fn f()void{defer release();defer{unsafe{*p=3;}finish();}return;}")
        first, second, _ = module.functions[0].body
        self.assertEqual(("defer", ["call"]), (first.kind, [item.kind for item in first.body]))
        self.assertEqual(("defer", ["unsafe", "call"]), (second.kind, [item.kind for item in second.body]))
        with self.assertRaises(CompileError):
            parsed("fn f()void{defer x=3;}")

    def test_local_const_uses_binding_ast_and_requires_initializer(self):
        module = parsed("fn f()void{const COUNT:usize=3;const OTHER=COUNT+1;var a:[COUNT]u8=[0;COUNT];}")
        first, second, _ = module.functions[0].body
        self.assertEqual(("binding", "const", "u64"), (first.kind, first.token.kind, first.value[1]))
        self.assertEqual(("const", None), (second.token.kind, second.value[1]))
        with self.assertRaises(CompileError):
            parsed("fn f()void{const N:u8;}")

    def test_enum_match_patterns_keep_variant_paths_and_payload_bindings(self):
        module = parsed("fn f(event:Event)void{match event{Event.Timer=>{},Event.Key(code)=>{use(code);},mod.Event.Shutdown=>{},}}")
        match = module.functions[0].body[0]
        self.assertEqual("match", match.kind)
        self.assertEqual(["Event.Timer", "Event.Key", "mod.Event.Shutdown"], [arm.pattern.value for arm in match.value])
        self.assertEqual("code", match.value[1].pattern.binding.value)
        self.assertEqual("call", match.value[1].body[0].kind)

    def test_bool_optional_and_result_patterns_share_arm_shape(self):
        module = parsed("fn f()void{match yes{true=>{},false=>{},}match opt{null=>{},some(value)=>{},}match result{ok(value)=>{},err(code)=>{},}match empty{ok=>{},_=>{},}}")
        patterns = [[arm.pattern.kind for arm in item.value] for item in module.functions[0].body]
        self.assertEqual([["bool", "bool"], ["null", "some"], ["ok", "err"], ["ok", "wildcard"]], patterns)

    def test_match_guards_and_non_block_arms_are_not_in_v1(self):
        with self.assertRaises(CompileError) as caught:
            parsed("fn f()void{match x{some(v) if v>0=>{},_=>{},}}")
        self.assertEqual("E0601", caught.exception.code)
        with self.assertRaises(CompileError):
            parsed("fn f()void{match x{true=>release(),false=>{},}}")

    def test_try_binds_tighter_than_cast_and_binary_operators(self):
        module = parsed("fn f()!u64{return (try allocate()) as u64+1;}")
        expression = module.functions[0].body[0].expr
        self.assertEqual(("binary", "+", "cast", "try", "call"),
                         (expression.kind, expression.value, expression.args[0].kind, expression.args[0].args[0].kind, expression.args[0].args[0].args[0].kind))
        module = parsed("fn f()!void{try initialize();return;}")
        self.assertEqual(("call", "try"), (module.functions[0].body[0].kind, module.functions[0].body[0].expr.kind))

    def test_orelse_is_lowest_precedence_right_associative_and_short_circuit_ast(self):
        module = parsed("fn f()u64{return a orelse b orelse x+y*2;}")
        expression = module.functions[0].body[0].expr
        self.assertEqual(("orelse", "name", "orelse"), (expression.kind, expression.args[0].kind, expression.args[1].kind))
        self.assertEqual("binary", expression.args[1].args[1].kind)
        self.assertEqual("*", expression.args[1].args[1].args[1].value)

    def test_orelse_control_transfers_are_value_ast_nodes(self):
        module = parsed("fn f()!u8{let x=a orelse return error.mem.Missing;loop{let y=b orelse break;let z=c orelse continue;}return x;}")
        binding = module.functions[0].body[0]
        exit_ = binding.expr.args[1]
        self.assertEqual(("exit", "return", "error", "mem.Missing"), (exit_.kind, exit_.value, exit_.args[0].kind, exit_.args[0].value))
        loop = module.functions[0].body[1]
        self.assertEqual(["break", "continue"], [item.expr.args[1].value for item in loop.body])
        for control in ("break", "continue"):
            with self.subTest(control=control), self.assertRaises(CompileError) as caught:
                parsed(f"fn f()void{{loop{{let x=value orelse {control}+1;}}}}")
            self.assertEqual("E0601", caught.exception.code)

    def test_parenthesized_literals_are_accepted_in_control_conditions(self):
        module = parsed("fn f()void{match (Event.Key(3)){Event.Key(x)=>{},_=>{},}for item in (Holder{values:[1,2]}).values{use(item);}}")
        self.assertEqual(["match", "for"], [item.kind for item in module.functions[0].body])

    def test_optional_type_prefix_is_not_a_value_constructor(self):
        with self.assertRaises(CompileError) as caught:
            parsed("fn f()void{let value=?u64;}")
        self.assertEqual("E0101", caught.exception.code)
        self.assertNotIn("not implemented", str(caught.exception))

    def test_root_full_l1_native_fixtures_parse(self):
        directory = Path(__file__).parent
        for name in ("l1_defs.dg", "l1_probe.dg"):
            path = directory / name
            if not path.exists():
                continue
            with self.subTest(name=name):
                Parser(lex(path.read_text(encoding="utf-8"), path=name)).parse()


if __name__ == "__main__":
    unittest.main()
