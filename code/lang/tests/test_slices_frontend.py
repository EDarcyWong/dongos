"""Semantic and ABI contracts for slice descriptors and unsafe direct calls."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from lang.dongc import compile_file, compile_source
from lang.dongc.checker import Checker
from lang.dongc.frontend import Parser, lex
from lang.dongc.model import CompileError


def parsed(text):
    return Parser(lex(text)).parse()


def checked(text):
    module = parsed(text)
    Checker(module).check()
    return module


def program(body, returns="u64", declarations="", parameters=""):
    return f"module slices; {declarations} fn f({parameters}) {returns} {{ {body} }}"


class SliceFrontendTests(unittest.TestCase):
    def assert_error(self, text, code):
        with self.assertRaises(CompileError) as caught:
            checked(text)
        self.assertEqual(code, caught.exception.code, caught.exception.message)
        return caught.exception

    def test_descriptor_layout_and_nested_elements(self):
        module = checked(program("return sizeof([]u8)+alignof([]const u16);",
                                 declarations="struct Store {xs:[]u8, rows:[2][]const u16}"))
        types = module.type_system
        self.assertEqual((16, 8), (types.layout("[]u8").size, types.layout("[]u8").alignment))
        self.assertEqual(48, types.layout("Store").size)
        self.assertTrue(types.is_aggregate("[]u8"))
        self.assertEqual("[]const u16", types.element("[][]const u16"))
        self.assertEqual(24, module.functions[0].body[0].expr.constant)

    def test_array_slices_inherit_element_mutability(self):
        module = checked(program("var a:[3]u8=[1,2,3]; let s=a[..]; s[1]=9; return s[1] as u64;"))
        slice_expr = module.functions[0].body[1].expr
        self.assertEqual(("[]u8", 3, 1), (slice_expr.typ, slice_expr.array_length, slice_expr.element_size))
        access = module.functions[0].body[-1].expr.args[0]
        self.assertEqual((True, None, True), (access.bounds_check, access.array_length, access.writable))
        checked(program("let a:[3]u8=[1,2,3]; let s:[]const u8=a[1..]; return s[0] as u64;"))
        self.assert_error(program("let a:[2]u8=[1,2]; let s=a[..]; s[0]=9; return 0;"), "E0402")
        self.assert_error(program("let a:[2]u8=[1,2]; let s:[]u8=a[..]; return 0;"), "E0301")

    def test_const_descriptor_can_still_mutate_mutable_elements(self):
        checked(program("s[0]=7; return s[0] as u64;", parameters="s:[]u8"))
        self.assert_error(program("s[0]=7; return 0;", parameters="s:[]const u8"), "E0402")
        self.assert_error(program("s=t; return 0;", parameters="s:[]u8,t:[]u8"), "E0402")
        checked(program("var s:[]u8=a; s=b; s[0]=8; return s.len;", parameters="a:[]u8,b:[]u8"))

    def test_omitted_bounds_and_empty_ranges(self):
        for expression, length in [("a[..]", 4), ("a[1..]", 3), ("a[..2]", 2),
                                   ("a[2..2]", 0), ("a[4..]", 0)]:
            with self.subTest(expression=expression):
                module = checked(program(f"let a:[4]u8=[0;4]; let s={expression}; return s.len;"))
                self.assertEqual(length, module.functions[0].body[1].expr.known_length)
        checked(program("let s=a[lo..hi]; return s.len;", parameters="a:[]u8,lo:usize,hi:usize"))
        checked(program("let s=a[..hi]; return s.len;", parameters="a:[]u8,hi:usize"))
        checked(program("let s=a[lo..]; return s.len;", parameters="a:[]u8,lo:usize"))

    def test_constant_bounds_rejected_before_backend(self):
        for expression in ["a[3..2]", "a[..5]", "a[5..]", "a[5..6]", "a[-1..2]", "a[..-1]"]:
            with self.subTest(expression=expression):
                self.assert_error(program(f"let a:[4]u8=[0;4]; let s={expression}; return 0;"), "E0302")
        self.assert_error(program("let s=a[3..2]; return 0;", parameters="a:[]u8"), "E0302")
        self.assert_error(program("return a[0..2][2] as u64;", parameters="a:[]u8"), "E0302")
        self.assert_error(program("let a:[2]u8=[0;2]; return a[1..][1] as u64;"), "E0302")

    def test_range_bound_types_are_usize(self):
        self.assert_error(program("let s=a[n..]; return 0;", parameters="a:[]u8,n:u8"), "E0301")
        self.assert_error(program("let s=a[..true]; return 0;", parameters="a:[]u8"), "E0301")
        self.assert_error(program("let s=p[..1]; return 0;", parameters="p:*u8"), "E0301")

    def test_array_temporaries_cannot_supply_borrowed_storage(self):
        self.assert_error(program("let s=[1,2][..]; return s.len;"), "E0601")
        self.assert_error(program("let s=Box {data:[1,2]}.data[..]; return s.len;",
                                  declarations="struct Box {data:[2]u8}"), "E0601")
        checked(program('return "ab"[1..][..].len;'))

    def test_packed_fields_need_proven_element_alignment(self):
        for declaration in ["packed struct P {tag:u8,data:[2]u16}",
                            "packed struct P {data:[2]u16}"]:
            with self.subTest(declaration=declaration):
                self.assert_error(program("var p=P {data:[0;2]" + (",tag:0" if "tag" in declaration else "") +
                                          "}; let s=p.data[..]; return s.len;", declarations=declaration), "E0601")
        self.assert_error(program("var p:P=P {tag:0,data:[0;2]}; unsafe {let s=p.data[..];} return 0;",
                                  declarations="packed struct P {tag:u8,data:[2]u16}"), "E0601")
        checked(program("var p=P {tag:0,data:[0;2]}; let s=p.data[..]; return s.len;",
                        declarations="packed struct P {tag:u8,data:[2]u8}"))
        module = checked(program("var p=P {tag:0,data:[0;2]}; let s=p.data[..]; return s.len;",
                                 declarations="struct P {tag:u8,data:[2]u16}"))
        self.assertEqual(2, module.functions[0].body[1].expr.args[0].alignment)

    def test_packed_alignment_survives_nested_places_and_indexing(self):
        declarations = "packed struct P {tag:u8,data:[2][2]u32} struct Outer {p:P}"
        self.assert_error(program("var x=Outer {p:P {tag:0,data:[[0;2];2]}}; let s=x.p.data[i][..]; return s.len;",
                                  declarations=declarations, parameters="i:usize"), "E0601")
        checked(program("var a:[2][2]u32=[[0;2];2]; let s=a[i][..]; return s.len;", parameters="i:usize"))

    def test_slice_properties_preserve_receiver_evaluation(self):
        module = checked(program("return identity(s).len;", parameters="s:[]u8",
                                 declarations="fn identity(s:[]u8) []u8 {return s;}"))
        length = module.functions[-1].body[0].expr
        self.assertEqual(("field", "call", "u64", None), (length.kind, length.args[0].kind, length.typ, length.constant))
        module = checked(program("return s.ptr;", "*const u8", parameters="s:[]const u8"))
        self.assertEqual("*const u8", module.functions[0].body[0].expr.typ)
        self.assert_error(program("s.len=2; return 0;", parameters="s:[]u8"), "E0301")
        self.assert_error(program("s.ptr=null; return 0;", parameters="s:[]u8"), "E0301")
        self.assert_error(program("return *s.ptr as u64;", parameters="s:[]u8"), "E0501")

    def test_string_slices_are_utf8_bytes_and_const(self):
        module = checked(program('let s="中\\0\\xFF"; return s.len;'))
        string = module.functions[0].body[0].expr
        self.assertEqual(("[]const u8", "中".encode() + b"\x00\xff"), (string.typ, string.value))
        checked(program('return "";', "[]const u8"))
        self.assert_error(program('let s:[]u8="hi"; return 0;'), "E0301")
        self.assert_error(program('"hi"[0]=65; return 0;'), "E0402")
        self.assert_error(program('return "hi"[2] as u64;'), "E0302")
        self.assert_error(program('return "hi"[..3].len;'), "E0302")

    def test_raw_slice_constructor_is_explicitly_unsafe(self):
        self.assert_error(program("let s=slice_from_raw_parts(p,n); return s.len;", parameters="p:*u8,n:usize"), "E0501")
        module = checked(program("unsafe {return slice_from_raw_parts(p,n);}", "[]u8", parameters="p:*u8,n:usize"))
        constructor = module.functions[0].body[0].body[0].expr
        self.assertEqual(("raw_slice", "[]u8", 1), (constructor.kind, constructor.typ, constructor.element_size))
        checked(program("unsafe {return slice_from_raw_parts(p,0);}", "[]const u16", parameters="p:*const u16"))
        self.assert_error(program("unsafe {let s=slice_from_raw_parts(null,0);} return 0;"), "E0301")
        self.assert_error(program("unsafe {let s=slice_from_raw_parts(p);} return 0;", parameters="p:*u8"), "E0301")
        self.assert_error(program("unsafe {let s=slice_from_raw_parts(p,n);} return 0;", parameters="p:*u8,n:u8"), "E0301")

    def test_slice_const_coercions_and_casts(self):
        checked(program("return s;", "[]const u8", parameters="s:[]u8"))
        checked(program("return s as []const u8;", "[]const u8", parameters="s:[]u8"))
        self.assert_error(program("return s;", "[]u8", parameters="s:[]const u8"), "E0301")
        self.assert_error(program("return s as []u8;", "[]u8", parameters="s:[]const u8"), "E0501")
        checked(program("unsafe {return s as []u8;}", "[]u8", parameters="s:[]const u8"))
        self.assert_error(program("unsafe {return s as []u16;}", "[]u16", parameters="s:[]u8"), "E0301")
        self.assert_error(program("unsafe {return s as *u8;}", "*u8", parameters="s:[]u8"), "E0301")

    def test_slices_cross_internal_function_boundaries(self):
        checked(program("return pass(s,1,2,3,4,5,6,7);", "[]const u8", parameters="s:[]u8",
                        declarations="fn pass(s:[]const u8,a:u8,b:u16,c:u32,d:u64,e:i64,f:usize,g:u64) []const u8 {return s;}"))
        self.assert_error(program("return 0;", parameters="s:[2]u8"), "E0601")

    def test_unsafe_function_requires_lexical_call_block(self):
        declaration = "unsafe fn dangerous(p:*u8) u8 {unsafe {return *p;}}"
        self.assert_error(program("return dangerous(p) as u64;", declarations=declaration, parameters="p:*u8"), "E0501")
        checked(program("unsafe {return dangerous(p) as u64;}", declarations=declaration, parameters="p:*u8"))
        self.assert_error("module m; unsafe fn dangerous(p:*u8) u8 {return *p;}", "E0501")
        self.assert_error("module m; unsafe fn a() void {} unsafe fn b() void {a();}", "E0501")

    def test_extern_signatures_and_call_conventions(self):
        for abi in ("sysv64", "win64"):
            declaration = f'extern "{abi}" ("foreign") fn foreign_call(a:u8,b:u64,c:*u8,d:bool,e:u64,f:u64,g:u64) i64;'
            module = checked(program("unsafe {return foreign_call(1,2,p,true,5,6,7);}", "i64", declarations=declaration, parameters="p:*u8"))
            self.assertEqual((True, True, "foreign", abi), (module.functions[0].external, module.functions[0].unsafe, module.functions[0].symbol, module.functions[0].abi))
            self.assert_error(program("return foreign_call(1,2,p,true,5,6,7);", "i64", declarations=declaration, parameters="p:*u8"), "E0501")
        self.assert_error('module m; extern "sysv64" fn ext(s:[]u8) u64;', "E0601")
        self.assert_error('module m; extern "sysv64" fn ext() []u8;', "E0601")
        checked('module m; extern "win64" fn callback() void {}')

    def test_linker_symbol_conflicts_are_diagnosed(self):
        self.assert_error('module m; extern "sysv64" ("same") fn first() u64; extern "win64" ("same") fn second() u8;', "E0602")
        self.assert_error('module m; extern "sysv64" fn __dong_panic() void;', "E0602")
        self.assert_error('module m; export("same") fn first() void {} export("same") fn second() void {}', "E0602")

    def test_string_literal_symbols_are_reserved(self):
        for symbol in ("__dg_string_0", "__dg_string_19", "__dg_string_007"):
            with self.subTest(symbol=symbol):
                self.assert_error(f'module m; export("{symbol}") fn user() []const u8 {{return "x";}}', "E0602")
                self.assert_error(f'module m; extern "sysv64" ("{symbol}") fn user() void;', "E0602")
        # Other names in the namespace cannot be emitted as numeric literal labels.
        checked('module m; export("__dg_string_named") fn user() void {}')

    def test_imported_call_is_not_shadowed_by_unrelated_local_basename(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entry = root / "main.dg"
            entry.write_text('module main; import dep as d; fn f()u64{let value=0;return d.value();}', encoding="utf-8")
            (root / "dep.dg").write_text('module dep; pub fn value()u64{return 42;}', encoding="utf-8")
            result = compile_file(entry, roots=[root])
            self.assertIn("call $__dg_m" + b"dep".hex() + "_f" + b"value".hex(), result.assembly)
            # A plain local call must still respect a binding that hides the fn.
            entry.write_text('module main; import dep as d; fn value()u64{return 42;} fn f()u64{let value=0;return value();}', encoding="utf-8")
            with self.assertRaises(CompileError) as caught:
                compile_file(entry, roots=[root])
            self.assertEqual("E0601", caught.exception.code)
        with self.assertRaises(CompileError) as caught:
            compile_source('module m; fn value()u64{return 42;} fn f()u64{let value=0;return value();}')
        self.assertEqual("E0601", caught.exception.code)

    def test_dependency_symbols_use_owning_module_and_local_name(self):
        module = parsed("module entry; fn work() u64 {return 1;}")
        function = module.functions[0]
        function.module, function.local_name = "dependency", "work"
        function.token = replace(function.token, value="dependency.work")
        Checker(module).check()
        self.assertEqual("__dg_m" + b"dependency".hex() + "_f" + b"work".hex(), function.symbol)

    def test_cross_module_struct_fields_need_public_visibility(self):
        text = program("unsafe {return (*p).private_value;}", parameters="p:*const P",
                       declarations="pub struct P {pub visible:u64,private_value:u64}")
        module = parsed(text)
        module.structs[0].module = "dependency"
        with self.assertRaises(CompileError) as caught:
            Checker(module).check()
        self.assertEqual("E0201", caught.exception.code)
        module = parsed(text.replace("(*p).private_value", "(*p).visible"))
        module.structs[0].module = "dependency"
        Checker(module).check()
        module = parsed(program("let p=P {visible:1,private_value:2}; return p.visible;",
                                declarations="pub struct P {pub visible:u64,private_value:u64}"))
        module.structs[0].module = "dependency"
        with self.assertRaises(CompileError) as caught:
            Checker(module).check()
        self.assertEqual("E0201", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
