"""Integer wrapping and unsafe memory intrinsics keep ordinary type rules."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from lang.dongc import CompileError, compile_file
from lang.dongc.checker import Checker
from lang.dongc.frontend import Parser, lex
from lang.dongc.modules import prepare_single


def checked(source):
    source = "module intrinsics; " + source
    module = prepare_single(Parser(lex(source)).parse(), source, "intrinsics.dg")
    Checker(module).check()
    return module


class IntrinsicSemanticTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(CompileError) as caught:
            checked(source)
        self.assertEqual(code, caught.exception.code, caught.exception.message)
        return caught.exception

    def test_wrapping_constant_results_for_all_integer_widths(self):
        for width in (8, 16, 32, 64):
            for sign in "iu":
                typ = f"{sign}{width}"
                low = -(1 << (width - 1)) if sign == "i" else 0
                high = (1 << (width - (sign == "i"))) - 1
                cases = [(f"wrapping_add({high},1)", low), (f"wrapping_sub({low},1)", high),
                         (f"wrapping_mul({high},2)", -2 if sign == "i" else high - 1)]
                for expression, result in cases:
                    with self.subTest(typ=typ, expression=expression):
                        module = checked(f"const VALUE:{typ}={expression};fn f(){typ}{{return VALUE;}}")
                        self.assertEqual(result, module.functions[0].body[0].expr.constant)

    def test_wrapping_literals_follow_the_outer_integer_context(self):
        for expression, value in [("wrapping_add(255,1)+1", 1),
                                  ("wrapping_mul(wrapping_add(255,1),17)", 0),
                                  ("wrapping_sub(0,1)&15", 15),
                                  ("wrapping_add(1,2)<<1", 6)]:
            with self.subTest(expression=expression):
                module = checked(f"fn f()u8{{return {expression};}}")
                self.assertEqual(value, module.functions[0].body[0].expr.constant)
        module = checked("fn f()i64{let n=wrapping_add(9223372036854775807,1);return n;}")
        self.assertEqual(-9223372036854775808, module.functions[0].body[0].expr.constant)

    def test_wrapping_typed_argument_sets_width_and_preserves_result_type(self):
        module = checked("fn f(x:u8)u8{return wrapping_add(1,x);}")
        intrinsic = module.functions[0].body[0].expr
        self.assertEqual(("intrinsic", "wrapping_add", "u8", "u8"),
                         (intrinsic.kind, intrinsic.value, intrinsic.typ, intrinsic.intrinsic_type))
        self.assertEqual(["u8", "u8"], [arg.typ for arg in intrinsic.args])
        self.assert_error("fn f(x:u8)u64{return wrapping_add(x,1);}", "E0301")
        self.assert_error("fn f(x:u8,y:u16)u8{return wrapping_add(x,y);}", "E0301")
        self.assert_error("fn f()u8{return wrapping_add(256,1);}", "E0302")

    def test_discarded_wrapping_defaults_to_i64(self):
        module = checked("fn f()void{wrapping_add(9223372036854775807,1);}")
        expression = module.functions[0].body[0].expr
        self.assertEqual(("i64", "i64", -9223372036854775808),
                         (expression.typ, expression.intrinsic_type, expression.constant))
        self.assert_error("fn f()void{wrapping_add(18446744073709551615,1);}", "E0302")

    def test_wrapping_is_available_in_shapes_and_static_aggregate_projection(self):
        module = checked("const DATA:[2]u8=[255,7];const COUNT:usize=wrapping_add(2,1);type Bytes=[COUNT]u8;const VALUE:u8=wrapping_add(DATA[0],1);var BUFFER:Bytes=[0;COUNT];")
        constants = {item.local_name: item for item in module.constants}
        self.assertEqual(b"\0", constants["VALUE"].initializer.data)
        self.assertEqual("[3]u8", module.globals[0].typ)

    def test_untyped_shape_wrapping_uses_default_width_before_range_checks(self):
        for expression in ("wrapping_add(wrapping_mul(9223372036854775807,2),3)",
                           "wrapping_add(9223372036854775807,1)+9223372036854775809",
                           "wrapping_add(-1,2)"):
            with self.subTest(expression=expression):
                module = checked(f"type Bytes=[{expression}]u8;align({expression})struct Aligned{{x:u8}}var DATA:Bytes=[0;{expression}];")
                self.assertEqual("[1]u8", module.globals[0].typ)
                self.assertEqual(1, module.type_system.layout("Aligned").alignment)
        module = checked("type Bytes=[wrapping_add(sizeof(u64),18446744073709551615)]u8;var DATA:Bytes=[0;7];")
        self.assertEqual("[7]u8", module.globals[0].typ)
        self.assert_error("type Bytes=[wrapping_add(-2,1)]u8;", "E0302")
        self.assert_error("type Bytes=[wrapping_sub(0,18446744073709551615)]u8;", "E0302")
        # Without wrapping, a pure arithmetic intermediate remains unbounded.
        checked("type Bytes=[(18446744073709551616+1)-18446744073709551616]u8;var DATA:Bytes=[0;1];")

    def test_wrapping_requires_exactly_two_integer_arguments(self):
        for expression in ("wrapping_add()", "wrapping_sub(1)", "wrapping_mul(1,2,3)",
                           "wrapping_add(true,false)", "wrapping_add(null,null)",
                           "wrapping_add([1],[2])"):
            with self.subTest(expression=expression):
                self.assert_error(f"fn f()void{{let n={expression};}}", "E0301")

    def test_memory_loads_and_stores_cover_all_signed_and_unsigned_widths(self):
        for typ in sorted({f"{sign}{width}" for sign in "iu" for width in (8, 16, 32, 64)}):
            for load, store in (("volatile_load", "volatile_store"), ("read_unaligned", "write_unaligned")):
                with self.subTest(typ=typ, load=load):
                    module = checked(f"fn f(p:*{typ},q:*const {typ},value:{typ}){typ}{{unsafe{{{store}(p,value);return {load}(q);}}}}")
                    statements = module.functions[0].body[0].body
                    self.assertEqual(("void", typ), (statements[0].expr.typ, statements[0].expr.intrinsic_type))
                    self.assertEqual((typ, typ), (statements[1].expr.typ, statements[1].expr.intrinsic_type))

    def test_all_memory_and_fence_intrinsics_require_lexical_unsafe(self):
        calls = ["volatile_load(p)", "volatile_store(p,1)", "read_unaligned(p)", "write_unaligned(p,1)",
                 "atomic_load(p)", "atomic_store(p,1)", "atomic_compare_exchange(p,1,2)",
                 "atomic_fetch_add(p,1)", "compiler_fence()"]
        for call in calls:
            with self.subTest(call=call):
                self.assert_error(f"fn f(p:*u32)void{{{call};}}", "E0501")
        self.assert_error("unsafe fn f(p:*u32)u32{return atomic_load(p);}", "E0501")
        self.assert_error("fn f(p:*u32)u32{unsafe{let n=atomic_load(p);}return atomic_load(p);}", "E0501")

    def test_write_intrinsics_require_mutable_pointer_targets(self):
        for call in ("volatile_store(p,1)", "write_unaligned(p,1)", "atomic_store(p,1)",
                     "atomic_compare_exchange(p,1,2)", "atomic_fetch_add(p,1)"):
            with self.subTest(call=call):
                self.assert_error(f"fn f(p:*const u32)void{{unsafe{{{call};}}}}", "E0402")
        checked("fn f(p:*const u32)u32{unsafe{return atomic_load(p);}}")

    def test_memory_intrinsics_reject_noninteger_or_nontyped_pointer_arguments(self):
        for parameter in ("p:bool", "p:[]u8", "p:*bool", "p:*[2]u8", "p:**u8"):
            with self.subTest(parameter=parameter):
                self.assert_error(f"fn f({parameter})void{{unsafe{{volatile_load(p);}}}}", "E0301")
        self.assert_error("fn f()void{unsafe{volatile_load(null);}}", "E0301")
        self.assert_error("struct P{x:u64}fn f(p:*P)void{unsafe{read_unaligned(p);}}", "E0301")

    def test_memory_store_value_types_are_exact(self):
        for call in ("volatile_store(p,value)", "write_unaligned(p,value)", "atomic_store(p,value)",
                     "atomic_fetch_add(p,value)", "atomic_compare_exchange(p,value,1)",
                     "atomic_compare_exchange(p,1,value)"):
            with self.subTest(call=call):
                self.assert_error(f"fn f(p:*u32,value:u64)void{{unsafe{{{call};}}}}", "E0301")
        checked("fn f(p:*u8)void{unsafe{volatile_store(p,255);}}")
        self.assert_error("fn f(p:*u8)void{unsafe{volatile_store(p,256);}}", "E0302")

    def test_atomic_types_are_only_u32_and_u64(self):
        for typ in ("u32", "u64"):
            module = checked(f"fn f(p:*{typ},value:{typ}){typ}{{unsafe{{atomic_store(p,value);atomic_fetch_add(p,value);return atomic_compare_exchange(p,value,7);}}}}")
            result = module.functions[0].body[0].body[-1].expr
            self.assertEqual((typ, typ, 3), (result.typ, result.intrinsic_type, len(result.args)))
        for typ in ("i8", "i16", "i32", "i64", "u8", "u16"):
            with self.subTest(typ=typ):
                self.assert_error(f"fn f(p:*{typ})void{{unsafe{{atomic_load(p);}}}}", "E0301")

    def test_memory_intrinsic_arities_are_checked(self):
        for call in ("volatile_load()", "read_unaligned(p,1)", "volatile_store(p)",
                     "write_unaligned(p,1,2)", "atomic_load(p,1)", "atomic_store()",
                     "atomic_compare_exchange(p,1)", "atomic_fetch_add(p)", "compiler_fence(p)"):
            with self.subTest(call=call):
                self.assert_error(f"fn f(p:*u32)void{{unsafe{{{call};}}}}", "E0301")

    def test_void_memory_results_follow_ordinary_storable_and_return_rules(self):
        checked("fn f(p:*u32)void{unsafe{atomic_store(p,1);compiler_fence();}}")
        self.assert_error("fn f(p:*u32)void{unsafe{let n=atomic_store(p,1);}}", "E0301")
        self.assert_error("fn f(p:*u32)u32{unsafe{return atomic_store(p,1);}}", "E0301")
        self.assert_error("fn f()void{unsafe{let n=compiler_fence();}}", "E0301")

    def test_memory_and_fence_intrinsics_are_not_constant_expressions(self):
        for source in ("const N:u32=atomic_load(null);", "var N:u32=volatile_load(null);",
                       "const N:u32=read_unaligned(null);", "const N:u32=compiler_fence();"):
            with self.subTest(source=source):
                self.assert_error(source, "E0601")

    def test_functions_override_builtin_spellings_in_runtime_calls(self):
        module = checked("fn wrapping_add(x:u8)u8{return x;}fn volatile_load(x:u8)u8{return x;}fn f()u8{return wrapping_add(volatile_load(7));}")
        result = module.functions[-1].body[0].expr
        self.assertEqual("call", result.kind)
        self.assertEqual("call", result.args[0].kind)
        self.assert_error("fn wrapping_add(a:u64,b:u64)u64{return a+b;}const N:u64=wrapping_add(1,2);", "E0601")

    def test_local_and_global_values_shadow_intrinsic_names(self):
        self.assert_error("fn f()void{let wrapping_add=7;wrapping_add(1,2);}", "E0601")
        self.assert_error("fn f(atomic_load:u32,p:*u32)void{unsafe{atomic_load(p);}}", "E0601")
        self.assert_error("const wrapping_add:u8=7;const N:u8=wrapping_add(1,2);", "E0601")
        self.assert_error("var volatile_load:u8=7;fn f()void{unsafe{volatile_load(1);}}", "E0601")
        module = checked("fn f()i64{let wrapping_add=wrapping_add(1,2);return wrapping_add;}")
        self.assertEqual(3, module.functions[0].body[0].expr.constant)

    def test_types_and_import_namespaces_also_shadow_intrinsic_names(self):
        for name, call in (("wrapping_add", "wrapping_add(1,2)"),
                           ("volatile_load", "volatile_load(p)"), ("compiler_fence", "compiler_fence()")):
            for declaration in (f"type {name}=u8;", f"struct {name}{{x:u8}}"):
                with self.subTest(declaration=declaration):
                    self.assert_error(declaration + f"fn f(p:*u32)void{{unsafe{{{call};}}}}", "E0601")
        self.assert_error("type wrapping_add=u8;const N:u64=wrapping_add(1,2);", "E0601")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "defs.dg").write_text("module defs;", encoding="utf-8")
            entry = root / "main.dg"
            for body in ("fn f()u64{return wrapping_add(1,2);}", "const N:u64=wrapping_add(1,2);"):
                entry.write_text("module main;import defs as wrapping_add;" + body, encoding="utf-8")
                with self.assertRaises(CompileError) as caught:
                    compile_file(entry, roots=[root])
                self.assertEqual("E0601", caught.exception.code)

    def test_imported_same_name_function_stays_a_function(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "defs.dg").write_text("module defs;pub fn wrapping_add(x:u8)u8{return x;}", encoding="utf-8")
            entry = root / "main.dg"
            entry.write_text("module main;import defs as d;fn f()u8{return d.wrapping_add(7);}", encoding="utf-8")
            compile_file(entry, roots=[root])
            entry.write_text("module main;import defs as d;const N:u8=d.wrapping_add(7);", encoding="utf-8")
            with self.assertRaises(CompileError) as caught:
                compile_file(entry, roots=[root])
            self.assertEqual("E0601", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
