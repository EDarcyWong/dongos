"""Precise non-null function values, indirect calls and callback signatures."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from lang.dongc import CompileError, compile_file
from lang.dongc.checker import Checker
from lang.dongc.frontend import Parser, lex
from lang.dongc.model import FunctionSignature, function_signature, function_type, is_function_type, make_function_type
from lang.dongc.modules import prepare_single


def checked(source):
    source = "module callbacks; " + source
    module = prepare_single(Parser(lex(source)).parse(), source, "callbacks.dg")
    Checker(module).check()
    return module


class FunctionSemanticTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(CompileError) as caught:
            checked(source)
        self.assertEqual(code, caught.exception.code, caught.exception.message)
        return caught.exception

    def test_signature_helpers_roundtrip_nested_function_parameters_and_returns(self):
        callback = make_function_type(("u64", "*u8"), "bool", "win64", True)
        outer = make_function_type((callback, "[]fn(u8)u16", "*[2]u64"), "fn()" + callback)
        self.assertEqual(FunctionSignature((callback, "[]fn(u8)u16", "*[2]u64"), "fn()" + callback), function_signature(outer))
        self.assertEqual(FunctionSignature(("u64", "*u8"), "bool", "win64", True), function_signature(callback))
        self.assertTrue(is_function_type(callback))
        self.assertFalse(is_function_type("*" + callback))
        self.assertIsNone(function_signature("u64"))

    def test_parameter_names_do_not_contribute_to_type_identity(self):
        module = checked("type A=fn(value:u64,buffer:*u8)bool;type B=extern \"sysv64\" fn(u64,*u8)bool;fn f(x:A)B{return x;}")
        function = module.functions[0]
        self.assertEqual("fn(u64,*u8)bool", function.params[0][1])
        self.assertEqual(function.params[0][1], function.returns)
        self.assert_error("type F=fn(x:u64,x:u8)u64;", "E0201")

    def test_function_pointer_layout_and_storage_are_one_word(self):
        module = checked("fn target(n:u8)u8{return n;}type F=fn(u8)u8;struct Holder{first:u8,callback:F,callbacks:[2]F}const TABLE:[2]F=[target;2];var SELECTED:F=target;")
        self.assertEqual((8, 8), (module.type_system.layout("fn(u8)u8").size, module.type_system.layout("fn(u8)u8").alignment))
        self.assertEqual((32, 8), (module.type_system.layout("Holder").size, module.type_system.layout("Holder").fields["callback"].offset))
        self.assertEqual(2, len(module.constants[0].initializer.relocations))
        self.assertEqual([0, 8], [item.offset for item in module.constants[0].initializer.relocations])
        self.assertEqual(module.functions[0].symbol, module.globals[0].initializer.relocations[0].symbol)

    def test_function_names_infer_precise_safe_and_unsafe_types(self):
        module = checked("fn plain(x:u64)u64{return x;}unsafe fn danger(x:u64)u64{return x;}extern \"win64\" fn foreign(x:u64)u64;fn f()void{let a=plain;let b=danger;let c=foreign;}")
        variables = module.functions[-1].variables
        self.assertEqual(["fn(u64)u64", "unsafe fn(u64)u64", 'unsafe extern "win64" fn(u64)u64'], [item.typ for item in variables])
        self.assertEqual("fn(u64)u64", function_type(module.functions[0]))

    def test_local_function_pointer_call_requires_unsafe_even_for_safe_type(self):
        declaration = "fn target(n:u64)u64{return n;}"
        self.assert_error(declaration + "fn f()u64{let p=target;return p(3);}", "E0501")
        module = checked(declaration + "fn f()u64{let p=target;unsafe{return p(3);}}")
        call = module.functions[-1].body[1].body[0].expr
        self.assertEqual(("call", "name", "u64", "sysv64"), (call.kind, call.value.kind, call.typ, call.call_abi))
        checked(declaration + "fn f()u64{return target(3);}")
        self.assert_error(declaration + "unsafe fn f()u64{let p=target;return p(3);}", "E0501")

    def test_callee_postfix_expressions_include_returned_field_and_index_values(self):
        checked("""type F=fn(u64)u64;struct Holder{f:F}fn target(n:u64)u64{return n;}
            fn factory()F{return target;}fn f()u64{let holder=Holder{f:target};let table:[2]F=[target;2];
            unsafe{return factory()(1)+holder.f(2)+table[1](3);}}""")
        self.assert_error("fn target(n:u64)u64{return n;}fn factory()fn(u64)u64{return target;}fn f()u64{return factory()(3);}", "E0501")

    def test_indirect_arguments_and_returns_are_checked_exactly(self):
        self.assert_error("fn f(p:fn(u8)u16)u16{unsafe{return p(256);}}", "E0302")
        self.assert_error("fn f(p:fn(u8)u16,n:u64)u16{unsafe{return p(n);}}", "E0301")
        self.assert_error("fn f(p:fn(u8)u16)u16{unsafe{return p();}}", "E0301")
        self.assert_error("fn f(p:fn(u8)u16)u8{unsafe{return p(1);}}", "E0301")
        checked("fn f(p:fn(u8)void)void{unsafe{p(1);}}")

    def test_safe_unsafe_and_abi_identity_never_convert_implicitly(self):
        for destination in ("unsafe fn(u64)u64", 'extern "win64" fn(u64)u64'):
            with self.subTest(destination=destination):
                self.assert_error(f"fn target(n:u64)u64{{return n;}}fn f()void{{let p:{destination}=target;}}", "E0301")
        self.assert_error("unsafe fn target(n:u64)u64{return n;}fn f()void{let p:fn(u64)u64=target;}", "E0301")
        self.assert_error('extern "win64" fn target(n:u64)u64;const P:extern "win64" fn(u64)u64=target;', "E0301")

    def test_function_pointers_are_non_null_and_cannot_be_pointer_or_integer_casts(self):
        self.assert_error("var P:fn()void=null;", "E0301")
        self.assert_error("fn f()void{let p:fn()void=null;}", "E0301")
        for expression in ("p as usize", "p as *u8", "(0 as usize) as fn()void", "raw as fn()void", "p as unsafe fn()void"):
            with self.subTest(expression=expression):
                self.assert_error(f"fn f(p:fn()void,raw:*u8)void{{unsafe{{let q={expression};}}}}", "E0301")

    def test_function_pointer_comparisons_only_allow_same_type_equality(self):
        checked("fn f(a:fn()void,b:fn()void)bool{return a==b || a!=b;}")
        for expression in ("a<b", "a+1", "a-1", "a==null", "a==b"):
            parameters = "a:fn()void,b:unsafe fn()void" if expression == "a==b" else "a:fn()void,b:fn()void"
            with self.subTest(expression=expression):
                self.assert_error(f"fn f({parameters})bool{{unsafe{{return {expression};}}}}", "E0301")

    def test_sysv_function_pointer_signatures_allow_slices_and_stack_parameters(self):
        checked("type F=fn(u64,u64,u64,u64,u64,[]u8,u64)[]const u8;fn f(p:F,s:[]u8)[]const u8{unsafe{return p(1,2,3,4,5,s,7);}}")
        self.assert_error("struct P{x:u64}type F=fn(P)void;", "E0601")
        self.assert_error("type F=fn([2]u8)void;", "E0601")
        self.assert_error("type F=fn()[2]u8;", "E0601")
        self.assert_error("struct Recursive{callback:fn()Recursive}", "E0601")

    def test_unused_nested_function_signatures_are_strictly_validated(self):
        for source, code in [("type F=fn(*Missing)void;", "E0301"),
                             ("type F=fn(void)void;", "E0302"),
                             ('type F=extern "win64" fn([]u8)void;', "E0601"),
                             ('type F=fn(extern "win64" fn()[]u8)void;', "E0601"),
                             ("type F=fn()fn(*Missing)void;", "E0301")]:
            with self.subTest(source=source):
                self.assert_error(source, code)

    def test_win64_definitions_are_scalar_callbacks_and_keep_lexical_unsafe(self):
        module = checked('extern "win64" fn callback(a:u8,b:*u8,c:fn()void)u64{unsafe{*b=a;}return 7;}')
        self.assertEqual(("win64", False, False), (module.functions[0].abi, module.functions[0].external, module.functions[0].unsafe))
        self.assert_error('extern "win64" fn callback(s:[]u8)void{}', "E0601")
        self.assert_error('extern "win64" fn callback()[]u8{let a:[2]u8=[1,2];return a[..];}', "E0601")
        self.assert_error('unsafe extern "win64" fn callback(p:*u8)u8{return *p;}', "E0501")

    def test_indirect_win64_call_carries_abi_and_safe_type_still_needs_unsafe(self):
        module = checked('fn f(p:extern "win64" fn(u64)u64)u64{unsafe{return p(7);}}')
        self.assertEqual("win64", module.functions[0].body[0].body[0].expr.call_abi)
        self.assert_error('fn f(p:extern "win64" fn()void)void{p();}', "E0501")

    def test_raw_pointer_to_function_pointer_storage_is_distinct(self):
        checked("fn target(n:u64)u64{return n;}fn f()u64{let p=target;let storage=&p;unsafe{return (*storage)(3);}}")
        self.assert_error("fn target()void{}fn f()void{let p=&target;}", "E0301")

    def test_reserved_bridge_symbols_cannot_be_exports_or_external_names(self):
        self.assert_error('export("__dg_bridge_any")fn f()void{}', "E0602")
        self.assert_error('extern "sysv64"("__dg_bridge_any")fn f()void;', "E0602")

    def test_non_function_values_cannot_be_called(self):
        self.assert_error("fn f()void{let value=3;value();}", "E0601")
        self.assert_error("struct P{x:u64}fn f()void{let p=P{x:1};p.x();}", "E0601")

    def test_function_pointer_signatures_respect_private_type_visibility(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entry = root / "main.dg"
            entry.write_text("module main;import defs as d;", encoding="utf-8")
            for declaration in ("pub type F=fn(*Hidden)void;", "pub fn f(p:fn(*Hidden)void)void{}",
                                "pub struct Holder{pub p:fn(*Hidden)void}"):
                with self.subTest(declaration=declaration):
                    (root / "defs.dg").write_text("module defs;struct Hidden{x:u8}" + declaration, encoding="utf-8")
                    with self.assertRaises(CompileError) as caught:
                        compile_file(entry, roots=[root])
                    self.assertEqual("E0201", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
