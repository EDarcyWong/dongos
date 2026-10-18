"""Function types and code addresses across lazy static/module declarations."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from lang.dongc import CompileError, compile_file
from lang.dongc.checker import Checker
from lang.dongc.frontend import Parser, lex
from lang.dongc.modules import prepare_single
from lang.dongc.model import function_signature


def checked(source):
    source = "module declarations; " + source
    module = prepare_single(Parser(lex(source)).parse(), source, "declarations.dg")
    Checker(module).check()
    return module


class FunctionDeclarationTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(CompileError) as caught:
            checked(source)
        self.assertEqual(caught.exception.code, code, caught.exception.message)

    def test_static_function_addresses_resolve_forward_signatures_and_aliases(self):
        module = checked('''
            const READ:Read=fetch;
            type Read=fn(*const Value)Number;
            type Number=u64;
            struct Value{number:Number}
            fn fetch(value:*const Value)Number {unsafe{return (*value).number;}}
            fn use(value:*const Value)Number {unsafe{return READ(value);}}
        ''')
        read = module.constants[0]
        self.assertEqual(function_signature(read.typ).params, ("*const Value",))
        self.assertEqual(read.initializer.data, bytes(8))
        self.assertEqual([(item.offset, item.symbol, item.addend) for item in read.initializer.relocations],
                         [(0, module.functions[0].symbol, 0)])

    def test_nested_static_function_values_keep_typed_relocations(self):
        module = checked('''
            type Op=fn(u64)u64;
            struct Table{tag:u8,entries:[2]Op}
            const TABLE:Table=Table{tag:7,entries:[increment,decrement]};
            var CURRENT:Op=TABLE.entries[1];
            fn increment(n:u64)u64{return n+1;}
            fn decrement(n:u64)u64{return n-1;}
        ''')
        table = module.constants[0].initializer
        self.assertEqual(len(table.data), 24)
        self.assertEqual([item.offset for item in table.relocations], [8, 16])
        current = module.globals[0].initializer
        self.assertEqual([(item.offset, item.symbol) for item in current.relocations],
                         [(0, module.functions[1].symbol)])

    def test_recursive_struct_through_function_signature_has_finite_layout(self):
        module = checked('''
            struct Node{next:*Node,visit:fn(*Node)u64}
            fn visit(node:*Node)u64{return 3;}
            var ROOT:Node=Node{next:&ROOT,visit:visit};
        ''')
        self.assertEqual(module.type_system.layout("Node").size, 16)
        self.assertEqual([item.offset for item in module.globals[0].initializer.relocations], [0, 8])

    def test_unused_signatures_and_layout_requests_validate_targets(self):
        for declaration in ('type F=fn(*Missing)void;', 'type F=fn()Missing;',
                            'struct V{callback:fn(*Missing)void}',
                            'const N:usize=sizeof(fn(Missing)void);',
                            'fn unused(handler:fn(*Missing)void)void{}'):
            with self.subTest(declaration=declaration):
                self.assert_error(declaration, "E0301")

    def test_alias_cycles_in_function_signatures_are_rejected(self):
        for declaration in ('type A=fn(A)void;', 'type A=fn()A;',
                            'type A=fn(B)void;type B=fn(A)void;'):
            with self.subTest(declaration=declaration):
                self.assert_error(declaration, "E0302")

    def test_function_constants_cannot_be_called_or_compared_at_compile_time(self):
        prefix = 'type F=fn()u64;fn a()u64{return 1;}const CALL:F=a;'
        self.assert_error(prefix + 'const N:u64=CALL();', "E0601")
        self.assert_error(prefix + 'const SAME:bool=CALL==a;', "E0601")
        self.assert_error(prefix + 'const N:usize=CALL as usize;', "E0301")
        self.assert_error(prefix + 'const P:F=null;', "E0301")

    def test_imported_functions_and_function_objects_are_distinct_callees(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "defs.dg").write_text('''module defs;
                pub type Op=fn(u64)u64;
                pub fn apply(n:u64)u64{return n+1;}
                pub const DEFAULT:Op=apply;
                pub var CURRENT:Op=apply;
                pub struct Table{pub callback:Op}
                pub var TABLE:Table=Table{callback:apply};
                ''', encoding="utf-8")
            entry = root / "main.dg"
            entry.write_text('''module main;import defs as d;
                const OWN:d.Op=d.apply;
                fn invoke(n:u64)u64{unsafe{return d.apply(n)+d.DEFAULT(n)+d.CURRENT(n)+d.TABLE.callback(n)+OWN(n);}}
                ''', encoding="utf-8")
            compiled = compile_file(entry, roots=[root])
            self.assertEqual(compiled.modules, ["defs", "main"])

    def test_public_function_types_cannot_expose_private_nested_types(self):
        for declaration in ('pub type F=fn(*Hidden)void;', 'pub type F=fn() *Hidden;',
                            'pub struct Public{pub callback:fn(fn(*Hidden)void)void}',
                            'pub fn f(cb:fn(*Hidden)void)void{}'):
            with self.subTest(declaration=declaration):
                self.assert_error('struct Hidden{number:u64}' + declaration, "E0201")

    def test_unexported_import_function_address_is_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "defs.dg").write_text('module defs;fn hidden()u64{return 1;}', encoding="utf-8")
            entry = root / "main.dg"
            entry.write_text('module main;import defs as d;const F:fn()u64=d.hidden;', encoding="utf-8")
            with self.assertRaises(CompileError) as caught:
                compile_file(entry, roots=[root])
            self.assertEqual(caught.exception.code, "E0201")


if __name__ == "__main__":
    unittest.main()
