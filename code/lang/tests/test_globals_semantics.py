"""Static values, symbolic addresses and mutable places obey separate rules."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from lang.dongc import CompileError, compile_file, compile_source
from lang.dongc.checker import Checker
from lang.dongc.frontend import Parser, lex
from lang.dongc.modules import prepare_single


def checked(source):
    source = "module values; " + source
    module = prepare_single(Parser(lex(source)).parse(), source, "values.dg")
    Checker(module).check()
    return module


class GlobalsSemanticTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(CompileError) as caught:
            compile_source("module values; " + source)
        self.assertEqual(code, caught.exception.code, caught.exception.message)
        return caught.exception

    def declarations(self, module):
        return {item.local_name: item for item in module.constants + module.globals}

    def test_scalar_constants_fold_and_have_readonly_addressable_storage(self):
        module = checked("const N:u64=18446744073709551615;const P:*const u64=&N;fn f()u64{return N;}")
        values = self.declarations(module)
        self.assertEqual(bytes([255]) * 8, values["N"].initializer.data)
        relocation = values["P"].initializer.relocations[0]
        self.assertEqual((0, values["N"].symbol, 0), (relocation.offset, relocation.symbol, relocation.addend))
        self.assertEqual(18446744073709551615, module.functions[0].body[0].expr.constant)
        self.assertTrue(all(not item.mutable for item in module.static_objects))

    def test_mutable_zero_and_initialized_scalar_storage(self):
        module = checked("var ZERO:u64=0;var VALUE:u16=4660;var FLAG:bool=true;fn f()void{ZERO=3;VALUE+=1;}")
        values = self.declarations(module)
        self.assertEqual(bytes(8), values["ZERO"].initializer.data)
        self.assertEqual(b"\x34\x12", values["VALUE"].initializer.data)
        self.assertEqual(b"\x01", values["FLAG"].initializer.data)
        self.assertTrue(all(item.mutable for item in module.static_objects))

    def test_struct_padding_is_zero_and_initializer_field_order_is_irrelevant(self):
        module = checked("struct P{tag:u8,value:u64}const DATA:P=P{value:9,tag:7};")
        data = self.declarations(module)["DATA"].initializer.data
        self.assertEqual(b"\x07" + bytes(7) + b"\x09" + bytes(7), data)

    def test_packed_nested_symbolic_relocations_keep_byte_offsets(self):
        module = checked("var V:u64=8;packed struct P{tag:u8,pointer:*u64}struct Outer{rows:[2]P}const DATA:Outer=Outer{rows:[P{tag:1,pointer:&V};2]};")
        values = self.declarations(module)
        data = values["DATA"].initializer
        self.assertEqual((18, [1, 10]), (len(data.data), [item.offset for item in data.relocations]))
        self.assertTrue(all(item.symbol == values["V"].symbol and item.addend == 0 for item in data.relocations))
        self.assertEqual((1, 1), (data.data[0], data.data[9]))

    def test_self_and_cross_address_cycles_do_not_read_initializers(self):
        module = checked("struct Node{next:*const Node,value:u64}const SELF:Node=Node{next:&SELF,value:1};var A:Node=Node{next:&B,value:2};var B:Node=Node{next:&A,value:3};")
        values = self.declarations(module)
        for origin, target in (("SELF", "SELF"), ("A", "B"), ("B", "A")):
            self.assertEqual(values[target].symbol, values[origin].initializer.relocations[0].symbol)

    def test_value_dependency_cycles_still_fail(self):
        self.assert_error("const A:u64=B;const B:u64=A;", "E0302")
        self.assert_error("struct P{x:u64}const A:P=B;const B:P=A;", "E0302")
        self.assert_error("const A:[2]u8=B;const B:[2]u8=A;", "E0302")

    def test_aggregate_constants_support_typed_compile_time_projections(self):
        module = checked("struct P{data:[3]u16,flag:bool}const DATA:P=P{data:[5,6,7],flag:true};const LAST:u16=DATA.data[2];const COUNT:usize=DATA.data.len;const FLAG:bool=DATA.flag;type Bytes=[COUNT]u8;var BUFFER:Bytes=[0;COUNT];")
        values = self.declarations(module)
        self.assertEqual(b"\x07\0", values["LAST"].initializer.data)
        self.assertEqual((3).to_bytes(8, "little"), values["COUNT"].initializer.data)
        self.assertEqual(b"\1", values["FLAG"].initializer.data)
        self.assertEqual(bytes(3), values["BUFFER"].initializer.data)
        self.assert_error("const DATA:[2]u8=[1,2];const VALUE:u64=DATA[0];", "E0301")

    def test_string_backing_has_exact_utf8_and_embedded_zero_length(self):
        module = checked('const TEXT:[]const u8="董\\0A";const EMPTY:[]const u8="";const FIRST:u8=TEXT[0];const LENGTH:usize=TEXT.len;')
        values = self.declarations(module)
        objects = {item.symbol: item for item in module.static_objects}
        backing = objects[values["TEXT"].initializer.relocations[0].symbol]
        self.assertEqual("董".encode() + b"\0A", backing.data)
        self.assertEqual(5, int.from_bytes(values["LENGTH"].initializer.data, "little"))
        self.assertEqual(b"\xe8", values["FIRST"].initializer.data)
        empty = objects[values["EMPTY"].initializer.relocations[0].symbol]
        self.assertEqual(b"", empty.data)

    def test_global_array_views_are_symbolic_and_allow_empty_one_past(self):
        module = checked("var DATA:[3]u64=[10,20,30];const VIEW:[]u64=DATA[1..];const END:[]u64=DATA[3..3];const P:*u64=&VIEW[0];")
        values = self.declarations(module)
        for name, offset, length in (("VIEW", 8, 2), ("END", 24, 0)):
            data = values[name].initializer
            self.assertEqual((values["DATA"].symbol, offset), (data.relocations[0].symbol, data.relocations[0].addend))
            self.assertEqual(length, int.from_bytes(data.data[8:], "little"))
        self.assertEqual(8, values["P"].initializer.relocations[0].addend)
        self.assert_error("var DATA:[3]u64=[10,20,30];const VIEW:[]u64=DATA[1..];const BAD:u64=VIEW[0];", "E0601")

    def test_constant_array_and_subviews_remain_readonly(self):
        compile_source("module values;const DATA:[3]u8=[1,2,3];const VIEW:[]const u8=DATA[1..];fn f()u8{var copy=DATA;copy[0]=7;return copy[0];}")
        for body in ("DATA[0]=7;", "let s=DATA[..];s[0]=7;", "VIEW[0]=7;"):
            self.assert_error("const DATA:[3]u8=[1,2,3];const VIEW:[]const u8=DATA[..];fn f()void{" + body + "}", "E0402")
        self.assert_error("const DATA:[3]u8=[1,2,3];const VIEW:[]u8=DATA[..];", "E0301")

    def test_address_bounds_include_slice_and_maximum_index(self):
        for source in [
            "const DATA:[2]u8=[1,2];const P:*const u8=&DATA[2];",
            'const DATA:[]const u8="";const P:*const u8=&DATA[0];',
            'const DATA:[]const u8="abc";const P:*const u8=&DATA[3];',
            'const DATA:[]const u8="abc";const P:*const u8=&DATA[18446744073709551615];',
            'const DATA:[]const u8="abc";const BAD:u8=DATA[3];',
            "var DATA:[2]u8=[1,2];const VIEW:[]u8=DATA[..];const P:*u8=&VIEW[2];",
        ]:
            with self.subTest(source=source):
                self.assert_error(source, "E0302")

    def test_mutable_values_are_never_constant_inputs(self):
        for source in [
            "var V:u64=1;const N:u64=V;", "var V:u64=1;var N:u64=V;",
            "var V:u64=1;const B:bool=false&&(V==1);",
            "var V:u64=1;const B:bool=true||(V==1);",
            "var V:[2]u8=[1,2];const N:u8=V[0];",
            "struct P{x:u8}var V:P=P{x:1};const N:u8=V.x;",
            'var V:[]const u8="abc";const N:usize=V.len;',
            "var V:usize=2;type A=[V]u8;",
        ]:
            with self.subTest(source=source):
                self.assert_error(source, "E0601")

    def test_type_only_array_length_does_not_read_mutable_elements(self):
        module = checked("var V:[2]u8=[1,2];const N:usize=V.len;const P:*u8=&V[1];")
        self.assertEqual(2, int.from_bytes(self.declarations(module)["N"].initializer.data, "little"))

    def test_const_addresses_can_project_fields_and_nested_arrays(self):
        module = checked("packed struct P{tag:u8,value:u64}const DATA:P=P{tag:1,value:2};const ADDRESS:*const u64=&DATA.value;var MATRIX:[2][3]u16=[[1,2,3],[4,5,6]];const ELEMENT:*u16=&MATRIX[1][2];")
        values = self.declarations(module)
        self.assertEqual(1, values["ADDRESS"].initializer.relocations[0].addend)
        self.assertEqual(10, values["ELEMENT"].initializer.relocations[0].addend)

    def test_address_operations_are_rejected_during_constant_evaluation(self):
        for initializer, typ in (("(&V) as usize", "usize"), ("(&V)==(&V)", "bool"),
                                 ("(&V)<(&V)", "bool"), ("(&V)+1", "*u64"),
                                 ("1 as *u64", "*u64")):
            with self.subTest(initializer=initializer):
                self.assert_error(f"var V:u64=1;const BAD:{typ}={initializer};", "E0601")
        compile_source("module values;var V:u64=1;fn f()usize{unsafe{return (&V) as usize;}}")

    def test_deep_scalar_casts_do_not_recheck_exponentially(self):
        expression = "7"
        for _ in range(30):
            expression = f"({expression} as u64)"
        checked(f"const VALUE:u64={expression};")

    def test_unused_global_types_are_fully_validated(self):
        for prefix in ("var", "const"):
            for typ, code in (("*Missing", "E0301"), ("*Done", "E0302"),
                              ("*[2]Missing", "E0301"), ("*[9223372036854775807]u64", "E0302")):
                with self.subTest(prefix=prefix, typ=typ):
                    self.assert_error(f"type Done=void;{prefix} P:{typ}=null;", code)
        compile_source("module values;var P:*[2147483648]u8=null;")

    def test_static_budget_is_checked_before_large_materialization(self):
        for prefix in ("var", "const"):
            self.assert_error(f"{prefix} HUGE:[16777217]u8=[0;16777217];", "E0601")
        self.assert_error("var A:[10485760]u8=[0;10485760];var B:[10485760]u8=[0;10485760];", "E0601")

    def test_full_budget_zero_repeat_has_compact_bss_output(self):
        result = compile_source("module values;var BUFFER:[16777216]u8=[0;16777216];")
        self.assertIn("resb 16777216", result.assembly)
        self.assertLess(len(result.assembly), 4096)

    def test_static_symbols_conflict_with_function_exports_and_reserved_strings(self):
        symbol = "__dg_m" + b"values".hex() + "_g" + b"V".hex()
        self.assert_error(f'var V:u64=1;export("{symbol}")fn f()void{{}}', "E0602")
        self.assert_error('export("__dg_static_string_0")fn f()void{}', "E0602")
        self.assert_error('extern "sysv64"("__dg_static_string_0")fn f()void;', "E0602")

    def test_local_shadow_and_old_scope_initializer_are_preserved(self):
        module = checked("var V:u64=1;const N:u64=3;fn f()u64{var V=V;let N=N+1;V+=N;return V;}")
        self.assertEqual("global", module.functions[0].body[0].expr.kind)
        self.assertEqual(4, module.functions[0].body[1].expr.constant)
        self.assertEqual("name", module.functions[0].body[-1].expr.kind)

    def test_address_of_function_syntax_and_runtime_initializers_are_rejected(self):
        self.assert_error("fn f()u64{return 1;}var V:u64=f();", "E0601")
        self.assert_error("fn f()u64{return 1;}const P:*u8=&f;", "E0301")
        self.assert_error("var V:u64;", "E0301")

    def test_cross_module_global_fields_and_visibility(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "defs.dg").write_text("module defs;pub struct P{pub data:[2]u8,secret:u8}pub var V:P=P{data:[1,2],secret:3};pub const DATA:[2]u8=[4,5];const HIDDEN:u8=7;", encoding="utf-8")
            entry = root / "main.dg"
            entry.write_text("module main;import defs as d;const N:u8=d.DATA[1];fn f()u8{d.V.data[0]=9;return d.V.data[1];}", encoding="utf-8")
            compile_file(entry, roots=[root])
            for body in ("return d.HIDDEN;", "return d.V.secret;"):
                entry.write_text("module main;import defs as d;fn f()u8{" + body + "}", encoding="utf-8")
                with self.assertRaises(CompileError) as caught:
                    compile_file(entry, roots=[root])
                self.assertEqual("E0201", caught.exception.code)
            (root / "defs.dg").write_text("module defs;struct Private{x:u8}pub var BAD:Private=Private{x:1};", encoding="utf-8")
            entry.write_text("module main;import defs as d;", encoding="utf-8")
            with self.assertRaises(CompileError) as caught:
                compile_file(entry, roots=[root])
            self.assertEqual("E0201", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
