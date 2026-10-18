"""Semantic contracts for the fixed-layout memory subset, independent of NASM."""
from __future__ import annotations

import unittest

from lang.dongc.checker import Checker
from lang.dongc.frontend import Parser, lex
from lang.dongc.model import CompileError


def checked(text):
    module = Parser(lex(text)).parse()
    Checker(module).check()
    return module


def program(body, returns="u64", declarations="", parameters=""):
    return f"module memory; {declarations} fn f({parameters}) {returns} {{ {body} }}"


class MemoryFrontendTests(unittest.TestCase):
    def assert_error(self, text, code):
        with self.assertRaises(CompileError) as caught:
            checked(text)
        self.assertEqual(code, caught.exception.code, caught.exception.message)
        return caught.exception

    def test_all_integer_widths_and_boundaries(self):
        for width in (8, 16, 32, 64):
            for sign in "iu":
                typ = f"{sign}{width}"
                minimum = -(1 << (width - 1)) if sign == "i" else 0
                maximum = (1 << (width - (sign == "i"))) - 1
                for value in (minimum, maximum):
                    with self.subTest(typ=typ, value=value):
                        module = checked(program(f"return {value};", typ))
                        self.assertEqual(value, module.functions[0].body[0].expr.constant)
                for value in (minimum - 1, maximum + 1):
                    with self.subTest(typ=typ, invalid=value):
                        self.assert_error(program(f"return {value};", typ), "E0302")
                checked(program(f"var x:{typ}; x={minimum}; x+=1; return x;", typ))

    def test_integer_operations_use_operand_width(self):
        for typ, maximum in [("u8", 255), ("i8", 127), ("u16", 65535), ("i16", 32767), ("u32", 4294967295), ("i32", 2147483647)]:
            with self.subTest(typ=typ):
                self.assert_error(program(f"return ({maximum} as {typ})+1;", typ), "E0302")
        self.assert_error(program("return (-128 as i8)/(-1 as i8);", "i8"), "E0302")
        self.assert_error(program("return (-128 as i8)%(-1 as i8);", "i8"), "E0302")
        self.assert_error(program("return -(128 as u8);", "u8"), "E0302")
        self.assert_error(program("return x+y;", "u16", parameters="x:u8,y:u16"), "E0301")
        self.assert_error(program("return x==y;", "bool", parameters="x:i8,y:u8"), "E0301")

    def test_cast_truncation_and_signed_values(self):
        for expression, typ, result in [("300 as u8", "u8", 44), ("255 as i8", "i8", -1),
                                        ("-1 as u8", "u8", 255), ("(-1 as i8) as i64", "i64", -1),
                                        ("(255 as u8) as i16", "i16", 255), ("true as u32", "u32", 1),
                                        ("~0", "u8", 255), ("~(0 as u16)", "u16", 65535)]:
            with self.subTest(expression=expression):
                module = checked(program(f"return {expression};", typ))
                self.assertEqual(result, module.functions[0].body[0].expr.constant)
        for expression in ("1 as bool", "false as bool", "null as u64"):
            self.assert_error(program(f"let x={expression}; return 0;"), "E0301")

    def test_shift_width_count_and_result(self):
        for typ, width in [("u8", 8), ("i8", 8), ("u16", 16), ("u32", 32), ("i64", 64)]:
            with self.subTest(typ=typ):
                self.assert_error(program(f"return (1 as {typ})<<{width};", typ), "E0302")
                self.assert_error(program(f"return 1<<{width};", typ), "E0302")
                checked(program("return x<<n;", typ, parameters=f"x:{typ},n:usize"))
        self.assert_error(program("return x<<n;", "u8", parameters="x:u8,n:u8"), "E0301")
        self.assert_error(program("return x<<-1;", "u8", parameters="x:u8"), "E0302")
        module = checked(program("return (255 as u8)<<1;", "u8"))
        self.assertEqual(254, module.functions[0].body[0].expr.constant)
        module = checked(program("return (-128 as i8)>>7;", "i8"))
        self.assertEqual(-1, module.functions[0].body[0].expr.constant)

    def test_nested_width_sensitive_constants_keep_arbitrary_arithmetic(self):
        for expression in ["(1<<8)-256", "(1<<8)&0", "1+((1<<8)-257)"]:
            self.assert_error(program(f"return {expression};", "u8"), "E0302")
        for expression, result in [("256-1", 255), ("(300-45)<<1", 254),
                                   ("(128<<1)+1", 1), ("~0 & 15", 15),
                                   ("(~0)-1", 254), ("(1<<7)>>7", 1)]:
            module = checked(program(f"return {expression};", "u8"))
            self.assertEqual(result, module.functions[0].body[0].expr.constant, expression)
        self.assert_error(program("return 1/(128<<1);", "u8"), "E0302")

    def test_struct_layout_is_shared_with_accesses(self):
        declarations = """struct Pair { tag:u8, value:u64 }
            packed struct Packed { tag:u8, value:u64 }
            align(64) struct Aligned { pair:Pair, data:[2]u16 }"""
        module = checked(program("var p=Pair {value:7,tag:1}; p.value+=2; return p.value;", declarations=declarations))
        types = module.type_system
        pair, packed, aligned = (types.layout(name) for name in ("Pair", "Packed", "Aligned"))
        self.assertEqual((16, 8, 8), (pair.size, pair.alignment, pair.fields["value"].offset))
        self.assertEqual((9, 1, 1), (packed.size, packed.alignment, packed.fields["value"].offset))
        self.assertEqual((64, 64, 16), (aligned.size, aligned.alignment, aligned.fields["data"].offset))
        access = module.functions[0].body[-1].expr
        self.assertTrue(access.addressable)
        self.assertTrue(access.writable)
        self.assertEqual(8, access.field_offset)

    def test_layout_builtins_are_usize_constants(self):
        declarations = "struct P {a:u8,b:u64}"
        for expression, result in [("sizeof(P)", 16), ("alignof(P)", 8), ("offsetof(P,b)", 8), ("sizeof([3]u16)", 6)]:
            module = checked(program(f"return {expression};", declarations=declarations))
            expr = module.functions[0].body[0].expr
            self.assertEqual(("u64", result), (expr.typ, expr.constant))
        self.assert_error(program("return offsetof(P,missing);", declarations=declarations), "E0201")
        self.assert_error(program("return offsetof(u64,value);"), "E0201")

    def test_aggregate_initialization_and_copy(self):
        declarations = "struct P {xs:[2]u8,p:*const u8}"
        module = checked(program("var a:P=P {xs:[1,2],p:null}; var b:P; b=a; b.xs=[3;2]; return b.xs[0] as u64;", declarations=declarations))
        statements = module.functions[0].body
        self.assertTrue(statements[0].expr.aggregate)
        self.assertTrue(statements[2].expr.aggregate)
        self.assertEqual("[2]u8", statements[3].expr.typ)
        checked(program("var a:[2][2]u8=[[1,2],[3;2]]; var b=a; b[0]=[5,6]; return b[0][1] as u64;"))
        module = checked(program("let a=[1,2]; return a.len;"))
        length = module.functions[0].body[-1].expr
        self.assertEqual(2, length.array_length)
        self.assertIsNone(length.constant)  # Evaluation of the receiver is retained.

    def test_array_context_and_length_errors(self):
        checked(program("let x:u8=1; let a=[0,x]; return a[0] as u64;"))
        for body in ["let a:[2]u8=[1];", "let a:[2]u8=[256,1];", "let a=[null,null];", "let a=[true,1];"]:
            with self.subTest(body=body):
                self.assert_error(program(body + " return 0;"), "E0302" if "256" in body else "E0301")

    def test_array_bounds_and_index_types(self):
        module = checked(program("let a:[4]u16=[7;4]; return a[i] as u64;", parameters="i:usize"))
        access = module.functions[0].body[-1].expr.args[0]
        self.assertEqual((True, 4, 2), (access.bounds_check, access.array_length, access.element_size))
        self.assertFalse(access.writable)
        self.assert_error(program("let a=[1,2]; return a[2] as u64;"), "E0302")
        self.assert_error(program("let a=[1,2]; return a[-1] as u64;"), "E0302")
        self.assert_error(program("let a=[1,2]; return a[i] as u64;", parameters="i:u8"), "E0301")
        self.assert_error(program("var a=[1,2]; a.len=3; return 0;"), "E0301")

    def test_immutable_aggregate_places(self):
        declarations = "struct P {x:u8,a:[2]u8}"
        for body in ["let a=[1,2]; a[0]=3;", "let p=P {x:0,a:[0;2]}; p.x=1;", "let p=P {x:0,a:[0;2]}; p.a[0]=1;"]:
            self.assert_error(program(body + " return 0;", declarations=declarations), "E0402")
        checked(program("var p=P {x:0,a:[0;2]}; let q=&p; unsafe {(*q).a[0]=1;} return p.a[0] as u64;", declarations=declarations))

    def test_address_of_and_pointer_constness(self):
        module = checked(program("var a:u8=1; let b:u8=2; let p=&a; let q=&b; return 0;"))
        variables = module.functions[0].variables
        self.assertEqual(["u8", "u8", "*u8", "*const u8"], [var.typ for var in variables])
        checked(program("var x:u8=0; let p:*u8=&x; let q:*const u8=p; unsafe {*p=3;} return x as u64;"))
        self.assert_error(program("var x:u8=0; let p:*const u8=&x; unsafe {*p=3;} return 0;"), "E0402")
        self.assert_error(program("let p=&1; return 0;"), "E0301")
        self.assert_error(program("let p=null; return 0;"), "E0301")

    def test_unsafe_blocks_are_lexical(self):
        for body in ["return *p as u64;", "p[0]=1; return 0;", "let q=p+1; return 0;", "let q=p-1; return 0;", "let n=p as usize; return 0;"]:
            self.assert_error(program(body, parameters="p:*u8"), "E0501")
        checked(program("unsafe {p[0]=1; let q=p+1; return *q as u64;}", parameters="p:*u8"))
        self.assert_error(program("unsafe {let x=*p;} return *p as u64;", parameters="p:*u8"), "E0501")
        self.assert_error(program("unsafe {let x=*p;} return x as u64;", parameters="p:*u8"), "E0201")

    def test_pointer_casts_and_pointer_arithmetic(self):
        checked(program("let q=p as *const u8; return 0;", parameters="p:*u8"))
        for expression in ["p as *u8", "p as *const u16", "p as usize"]:
            self.assert_error(program(f"let q={expression}; return 0;", parameters="p:*const u8"), "E0501")
        checked(program("unsafe {let q=p as *u8; let n=q as usize; let r=n as *u16; r[0]=1;} return 0;", parameters="p:*const u8"))
        self.assert_error(program("unsafe {let p=n as *u8;} return 0;", parameters="n:i64"), "E0301")
        self.assert_error(program("unsafe {let p=p-n;} return 0;", parameters="p:*u8,n:i64"), "E0301")
        self.assert_error(program("unsafe {return p-q;}", parameters="p:*u8,q:*u8"), "E0301")
        self.assert_error(program("unsafe {let q=1+p;} return 0;", parameters="p:*u8"), "E0301")

    def test_pointer_equality_and_null(self):
        checked(program("return p==null;", "bool", parameters="p:*u8"))
        checked(program("return null!=p;", "bool", parameters="p:*u8"))
        checked(program("return p==q;", "bool", parameters="p:*u8,q:*const u8"))
        self.assert_error(program("return p<q;", "bool", parameters="p:*u8,q:*u8"), "E0301")
        self.assert_error(program("return p==q;", "bool", parameters="p:*u8,q:*u16"), "E0301")
        self.assert_error(program("return null==null;", "bool"), "E0301")

    def test_uninitialized_places_need_whole_assignment(self):
        declarations = "struct P {x:u64,a:[2]u8}"
        for body in ["var p:P; let q=&p;", "var p:P; p.x=1;", "var p:P; p.a[0]=1;", "var p:P; let q=p;", "var a:[2]u8; a[0]=1;", "var x:u64; x+=1;"]:
            self.assert_error(program(body + " return 0;", declarations=declarations), "E0401")
        checked(program("var p:P; p=P {x:1,a:[0;2]}; let q=&p; unsafe {return (*q).x;}", declarations=declarations))
        self.assert_error(program("var p:P; if flag {p=P {x:1,a:[0;2]};} return p.x;", declarations=declarations, parameters="flag:bool"), "E0401")

    def test_compound_assignment_preserves_target_and_rhs(self):
        module = checked(program("unsafe {p[i]+=2;} return 0;", parameters="p:*u16,i:usize"))
        statement = module.functions[0].body[0].body[0]
        target, operator = statement.value
        self.assertEqual(("index", "+=", "integer", "u16"), (target.kind, operator, statement.expr.kind, statement.expr.typ))
        self.assertTrue(target.writable)
        self.assertEqual((False, None, 2), (target.bounds_check, target.array_length, target.element_size))

    def test_struct_initializer_diagnostics(self):
        declarations = "struct P {a:u8,b:u64}"
        for literal, code in [("P {a:1}", "E0301"), ("P {a:1,b:2,a:3}", "E0201"), ("P {a:1,c:2,b:3}", "E0201"), ("P {a:true,b:0}", "E0301")]:
            self.assert_error(program(f"let p={literal}; return 0;", declarations=declarations), code)
        self.assert_error(program("return 0;", declarations="struct f {x:u8}"), "E0201")

    def test_aggregate_abi_is_explicitly_rejected(self):
        declarations = "struct P {x:u64}"
        self.assert_error(program("return 0;", declarations=declarations, parameters="p:P"), "E0601")
        self.assert_error(program("return P {x:0};", "P", declarations=declarations), "E0601")
        self.assert_error(program("return 0;", parameters="a:[1]u64"), "E0601")
        checked(program("unsafe {return (*p).x;}", declarations=declarations, parameters="p:*const P"))


if __name__ == "__main__":
    unittest.main()
