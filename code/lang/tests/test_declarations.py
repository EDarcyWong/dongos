"""Transparent types and compile-time values share the ordinary scalar rules."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from lang.dongc import CompileError, compile_file, compile_source
from lang.dongc.checker import Checker
from lang.dongc.frontend import Parser, lex
from lang.dongc.modules import prepare_single


def checked(source):
    module = prepare_single(Parser(lex(source, path="values.dg")).parse(), source, "values.dg")
    Checker(module).check()
    return module


class DeclarationTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(CompileError) as caught:
            compile_source("module values; " + source)
        self.assertEqual(code, caught.exception.code, caught.exception.message)
        return caught.exception

    def value(self, declaration, expression="VALUE", returns="u64"):
        module = checked(f"module values; {declaration} fn f(){returns}{{return {expression};}}")
        return module.functions[0].body[0].expr

    def test_transparent_aliases_cover_object_type_forms(self):
        module = checked("""module values; type Byte=u8;type Ref=*Byte;type View=[]const Byte;
            type Data=[COUNT]Byte;type Record=Packet;const COUNT:usize=3;
            struct Packet{data:Data,view:View,ptr:Ref}
            fn f(p:*Record) Byte {unsafe{return (*p).data[0];}}""")
        self.assertEqual(["*Packet"], [typ for _, typ in module.functions[0].params])
        self.assertEqual("u8", module.functions[0].returns)
        self.assertEqual(["[3]u8", "[]const u8", "*u8"],
                         [field[1] for field in module.structs[0].fields])
        self.assertEqual(32, module.type_system.layout("Packet").size)

    def test_alias_is_not_a_distinct_assignment_or_call_type(self):
        compile_source("""module values;type Count=u16;type Data=[3]Count;type View=[]Count;
            fn pass(s:View)[]u16{return s;}
            fn f()Count{var a:Data=[4;3];let b:[3]u16=a;let s=pass(a[..]);s[0]=5;return b[0]+s[0];}""")
        self.assert_error("type Small=u8;fn f(x:Small)u16{return x;}", "E0301")

    def test_alias_struct_literals_and_layout_builtins(self):
        module = checked("""module values;type Record=Pair;struct Pair{x:u8,y:u64}
            fn f()u64{let p=Record{x:1,y:4};return p.y+sizeof(Record)+offsetof(Record,y);}""")
        self.assertEqual("Pair", module.functions[0].variables[0].typ)
        self.assertEqual(16, module.type_system.layout("Pair").size)

    def test_void_alias_only_has_a_return_role(self):
        compile_source("module values;type Done=void;fn f()Done{}")
        self.assert_error("type Done=void;fn f()void{var bad:Done;}", "E0302")
        self.assert_error("type Done=void;type Bad=*Done;", "E0302")
        self.assert_error("type Done=void;type Bad=[]Done;", "E0302")

    def test_all_integer_constant_widths_and_limits(self):
        for width in (8, 16, 32, 64):
            for sign in "iu":
                typ = f"{sign}{width}"
                low = -(1 << (width - 1)) if sign == "i" else 0
                high = (1 << (width - (sign == "i"))) - 1
                for value in (low, high):
                    with self.subTest(typ=typ, value=value):
                        expression = self.value(f"const VALUE:{typ}={value};", returns=typ)
                        self.assertEqual((typ, value), (expression.typ, expression.constant))
                for value in (low - 1, high + 1):
                    self.assert_error(f"const VALUE:{typ}={value};", "E0302")

    def test_typed_constants_preserve_width_and_cast_truncation(self):
        self.assertEqual(44, self.value("const VALUE:u8=(300 as u16) as u8;", returns="u8").constant)
        self.assertEqual(-1, self.value("const VALUE:i8=255 as i8;", returns="i8").constant)
        self.assert_error("const SMALL:u8=255;const BAD:u8=SMALL+1;", "E0302")
        self.assert_error("const SMALL:u8=1;const BIG:u64=SMALL;", "E0301")
        self.assert_error("const SMALL:u8=1;fn f(x:u64)u64{return x+SMALL;}", "E0301")
        self.assertEqual(255, self.value("const VALUE:u8=256-1;", returns="u8").constant)

    def test_constant_shifts_and_complements_use_context(self):
        for expression, expected in [("(128<<1)+1", 1), ("~0", 255), ("(~0)-1", 254),
                                     ("(1<<7)>>7", 1), ("(300-45)<<1", 254)]:
            with self.subTest(expression=expression):
                self.assertEqual(expected, self.value(f"const VALUE:u8={expression};", returns="u8").constant)
        for expression in ("1<<8", "(1<<8)-256", "1/(128<<1)"):
            self.assert_error(f"const BAD:u8={expression};", "E0302")
        self.assert_error("const SMALL:u8=128;const BAD:u8=SMALL<<8;", "E0302")

    def test_bool_constants_fold_and_drive_return_analysis(self):
        expression = self.value("const VALUE:bool=(1<2)&&!false;", returns="bool")
        self.assertEqual(("bool", True), (expression.typ, expression.constant))
        compile_source("module values;const YES:bool=true;fn f()u64{if YES{return 1;}}")
        self.assert_error("const BAD:bool=1;", "E0301")
        self.assert_error("const BAD:u8=true;", "E0301")

    def test_forward_constants_aliases_and_layout_dependencies(self):
        module = checked("""module values;
            const SIZE:usize=sizeof(Record);type Record=Packet;type Bytes=[COUNT]u16;
            align(ALIGNMENT) struct Packet{tag:u8,data:Bytes}
            const COUNT:usize=3;const ALIGNMENT:usize=alignof(u64);
            const CHECKSUM:usize=SIZE+alignof(Record)+offsetof(Record,data);
            fn f()usize{return CHECKSUM;}""")
        self.assertEqual(18, module.functions[0].body[0].expr.constant)
        self.assertEqual((8, 8), (module.type_system.layout("Packet").size, module.type_system.layout("Packet").alignment))

    def test_array_lengths_repeat_and_align_accept_layout_expressions(self):
        module = checked("""module values;const COUNT:usize=3;type Values=[COUNT+1]u16;
            align(alignof(u64)) struct Packet{values:Values}
            fn f()u64{let a:[sizeof([COUNT]u16)]u8=[0;sizeof([COUNT]u16)];
                let b:Values=[1;COUNT+1];return a.len+b.len;}""")
        self.assertEqual(["[6]u8", "[4]u16"], [variable.typ for variable in module.functions[0].variables])
        self.assertEqual(6, module.functions[0].body[0].expr.value)

    def test_invalid_named_shape_values_are_diagnosed(self):
        for source, code in [
            ("const N:usize=0;type A=[N]u8;", "E0302"),
            ("const N:i64=-1;type A=[N]u8;", "E0302"),
            ("const N:bool=true;type A=[N]u8;", "E0301"),
            ("const N:usize=3;align(N)struct S{x:u8}", "E0302"),
            ("const N:usize=8192;align(N)struct S{x:u8}", "E0302"),
            ("const N:usize=0;fn f()void{let a=[0;N];}", "E0302"),
            ("const N:usize=18446744073709551615;type A=[N]u8;", "E0302"),
        ]:
            with self.subTest(source=source):
                self.assert_error(source, code)

    def test_cycles_include_alias_constant_and_layout_paths(self):
        for source in [
            "type A=B;type B=A;", "type A=*A;", "const A:u64=B;const B:u64=A;",
            "const N:usize=sizeof(P);struct P{data:[N]u8}",
            "align(N)struct P{x:u8}const N:usize=alignof(P);",
            "type A=[sizeof(A)]u8;", "type A=P;struct P{a:A}",
            "type A=[N]u8;const N:usize=sizeof(A);",
        ]:
            with self.subTest(source=source):
                self.assert_error(source, "E0302")

    def test_pointer_and_slice_recursive_structs_remain_finite(self):
        compile_source("module values;type Link=*Node;type Children=[]Node;struct Node{next:Link,children:Children,data:[sizeof(Link)]u8}")

    def test_indirection_breaks_layout_dependencies_before_target_dimensions(self):
        for source in [
            "const N:usize=sizeof(Node);struct Node{next:*[N]Node}",
            "const N:usize=sizeof(*[8]Node);struct Node{bytes:[N]u8}",
            "type Link=*[N]Node;const N:usize=sizeof(Node);struct Node{next:Link}",
            "const N:usize=sizeof(Node);struct Node{children:[][N]Node}",
        ]:
            with self.subTest(source=source):
                expression = self.value(source, "N")
                self.assertEqual(16 if "children" in source else 8, expression.constant)
        self.assert_error("struct S{next:*[N]Missing}const N:usize=sizeof(S);", "E0301")
        self.assert_error("struct S{next:*[N]u8}const N:usize=0;", "E0302")
        self.assert_error("type Done=void;const N:usize=sizeof(*Done);", "E0302")
        self.assert_error("const N:usize=sizeof(*Missing);", "E0301")
        self.assert_error("type Done=void;const N:usize=sizeof([]Done);", "E0302")

    def test_layout_builtins_defer_indirect_target_layout_expressions(self):
        for prefix, expected in (("*", 8), ("[]", 16)):
            for alias in (False, True):
                with self.subTest(prefix=prefix, alias=alias):
                    declaration = f"type A={prefix}[sizeof(S)]S;" if alias else ""
                    target = "A" if alias else f"{prefix}[sizeof(S)]S"
                    source = declaration + f"const N:usize=sizeof({target});struct S{{data:[N]u8}}"
                    self.assertEqual(expected, self.value(source, "N").constant)
        for target, code in (("Missing", "E0301"), ("Done", "E0302")):
            for prefix in ("*", "[]"):
                with self.subTest(target=target, prefix=prefix):
                    self.assert_error(f"type Done=void;const N:usize=sizeof({prefix}[sizeof(S)]{target});struct S{{data:[N]u8}}", code)
        for prefix in ("*", "[]"):
            self.assert_error(f"const N:usize=sizeof({prefix}[COUNT]S);const COUNT:usize=0;struct S{{data:[N]u8}}", "E0302")

    def test_unused_declarations_are_validated(self):
        self.assert_error("type Unused=Missing;", "E0301")
        self.assert_error("const UNUSED:u8=256;", "E0302")
        self.assert_error("type Unused=[N]u8;const N:usize=0;", "E0302")

    def test_global_constants_have_readonly_storage(self):
        self.assert_error("const N:u64=3;fn f()void{N=4;}", "E0402")
        self.assert_error("const N:u64=3;fn f()void{N+=1;}", "E0402")
        compile_source("module values;const N:u64=3;fn f()*const u64{return &N;}")

    def test_unsupported_global_constant_values_are_explicit(self):
        for source in [
            "fn f()u64{return 1;}const N:u64=f();", "let global:u64=1;",
        ]:
            with self.subTest(source=source):
                self.assert_error(source, "E0601")

    def test_static_aggregate_string_and_address_initializers(self):
        compile_source('''module values;
            const TEXT:[]const u8="hello";
            const DATA:[2]u8=[1,2];
            struct P{x:u8} const RECORD:P=P{x:1};
            const PTR:*u8=null;
            const N:u64=1; const ADDRESS:*const u64=&N;
            const FIRST:u8="x"[0]; var global:u64=1;
        ''')

    def test_local_shadow_uses_old_scope_in_initializer(self):
        module = checked("""module values;const N:u64=3;fn f()u64{
            var N=N+1;N+=1;{let N:u64=9;}return N;}""")
        expression = module.functions[0].body[0].expr
        self.assertEqual(4, expression.constant)
        self.assertEqual("name", module.functions[0].body[-1].expr.kind)
        compile_source("module values;const N:u64=3;fn f(N:u64)u64{return N;}")

    def test_local_value_shadow_cannot_be_used_as_compile_time_shape(self):
        for body in ["let a:[N]u8=[0;3];", "let a=[0;N];", "let n=sizeof([N]u8);",
                     "let a:[N+1]u8=[0;4];", "let a:[sizeof([N]u8)]u8=[0;3];",
                     "let a:[sizeof(*[N]u8)]u8=[0;8];", "let a=[0;sizeof([N]u8)];"]:
            with self.subTest(body=body):
                self.assert_error(f"const N:usize=3;fn f(N:usize)void{{{body}}}", "E0601")
        # The alias was defined in global scope, so a local name cannot alter it.
        compile_source("module values;const N:usize=3;type A=[N]u8;fn f(N:usize)void{let a:A=[0;3];}")

    def test_all_top_level_declarations_share_a_namespace(self):
        for source in ["type A=u8;const A:u8=0;", "type A=u8;struct A{x:u8}",
                       "const A:u8=0;fn A()void{}", "struct A{x:u8}fn A()void{}",
                       "type u8=u16;", "type usize=u64;", "const A:u8=1;const A:u8=2;"]:
            with self.subTest(source=source):
                self.assert_error(source, "E0201")

    def files(self, root, sources):
        for name, source in sources.items():
            (root / f"{name}.dg").write_text(source, encoding="utf-8")
        return root / "main.dg"

    def test_public_aliases_constants_and_layout_across_modules(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entry = self.files(root, {
                "main": "module main;import defs as d;type Local=d.PacketAlias;fn f()u64{let p=Local{data:[7;d.COUNT]};return p.data.len+d.CHECKSUM;}",
                "defs": "module defs;type Byte=u8;pub const COUNT:usize=3;pub type Bytes=[COUNT]Byte;pub struct Packet{pub data:Bytes}pub type PacketAlias=Packet;pub const CHECKSUM:usize=sizeof(PacketAlias);",
            })
            result = compile_file(entry, roots=[root])
            self.assertEqual(3, result.layout_manifest["types"][0]["size"])
            self.assertEqual("[3]u8", result.layout_manifest["types"][0]["fields"][0]["type"])

    def test_private_aliases_constants_and_public_type_leaks(self):
        cases = [
            ("type Secret=u8;", "type A=d.Secret;", ""),
            ("const SECRET:u64=1;", "", "return d.SECRET;"),
            ("struct Secret{x:u8}pub type Leak=*Secret;", "", "return 0;"),
            ("struct Secret{x:u8}type Indirect=Secret;pub type Leak=[]Indirect;", "", "return 0;"),
        ]
        for declarations, aliases, body in cases:
            with self.subTest(declarations=declarations), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                entry = self.files(root, {"main": f"module main;import defs as d;{aliases}fn f()u64{{{body or 'return 0;'}}}", "defs": "module defs;" + declarations})
                with self.assertRaises(CompileError) as caught:
                    compile_file(entry, roots=[root])
                self.assertEqual("E0201", caught.exception.code, caught.exception.message)

    def test_import_aliases_share_top_level_declaration_namespace(self):
        for declaration in ("const d:u8=0;", "type d=u8;", "struct d{x:u8}", "fn d()void{}"):
            with self.subTest(declaration=declaration), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                entry = self.files(root, {"main": "module main;import defs as d;" + declaration, "defs": "module defs;"})
                with self.assertRaises(CompileError) as caught:
                    compile_file(entry, roots=[root])
                self.assertEqual("E0201", caught.exception.code)

    def test_imported_const_is_immutable_and_import_alias_can_be_shadowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entry = self.files(root, {"main": "module main;import defs as d;fn f()void{d.COUNT=4;}", "defs": "module defs;pub const COUNT:usize=3;"})
            with self.assertRaises(CompileError) as caught:
                compile_file(entry, roots=[root])
            self.assertEqual("E0402", caught.exception.code)
            entry.write_text("module main;import defs as d;struct Holder{COUNT:u64}fn f()u64{let d=Holder{COUNT:9};return d.COUNT;}", encoding="utf-8")
            compile_file(entry, roots=[root])

    def test_dependency_diagnostic_keeps_its_source_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entry = self.files(root, {"main": "module main;import defs as d;", "defs": "module defs;\nconst BAD:u8=256;"})
            with self.assertRaises(CompileError) as caught:
                compile_file(entry, roots=[root])
            text = caught.exception.format("main.dg", "module main;")
            self.assertIn("defs.dg:2:", text)
            self.assertIn("const BAD:u8=256;", text)


if __name__ == "__main__":
    unittest.main()
