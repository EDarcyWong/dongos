"""Module graph and constant initialization contracts for the remaining L1."""
from pathlib import Path
import tempfile
import unittest
from lang.dongc import CompileError,compile_file,compile_source
from lang.dongc.frontend import Parser,lex
from lang.dongc.modules import prepare_single
from lang.dongc.checker import Checker


class L1ModuleTests(unittest.TestCase):
    def files(self,files):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,source in files.items():
                path=root/(name.replace('.','/')+'.dg');path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('module '+name+';'+source,encoding='utf-8')
            return compile_file(root/'main.dg',roots=[root])

    def invalid(self,files,code):
        with self.assertRaises(CompileError) as caught:self.files(files)
        self.assertEqual(caught.exception.code,code,caught.exception.message)
        return caught.exception

    def test_imported_public_nominal_types_methods_and_static_pairs(self):
        result=self.files({'main':'''import dep as d;fn f()!u64{
            var e:d.Event=d.DEFAULT;let p:*d.Event=&e;let n=p.number();
            match e{d.Event.Value(value)=>{return n+value as u64;},_=>{return error.d.Failed;},}
        }''','dep':'''pub enum Event{Empty,Value(u8)}pub error Failed=17;
            pub const DEFAULT:Event=Event.Value(9);
            pub fn(self:*Event)number()u64{return 7;}
        '''})
        self.assertIn('__dg_m646570_t4576656e74_f6e756d626572',result.assembly)
        self.assertIn('main',result.modules);self.assertIn('dep',result.modules)

    def test_method_owner_aliases_visibility_and_receiver_identity(self):
        self.files({'main':'import dep as d;fn f()u64{var s=d.S{x:7};return (&s).get()+d.get(&s);}',
                    'dep':'pub struct S{pub x:u64}type Alias=S;pub fn(self:*Alias)get()u64{unsafe{return (*self).x;}}'})
        for files,code in [
            ({'main':'import dep as d;fn(self:*d.S)get()void{}','dep':'pub struct S{x:u64}'},'E0201'),
            ({'main':'import dep as d;type Alias=d.S;fn(self:*Alias)get()void{}','dep':'pub struct S{x:u64}'},'E0201'),
            ({'main':'import dep as d;fn f(p:*d.S)void{p.get();}','dep':'pub struct S{x:u64}fn(self:*S)get()void{}'},'E0201'),
            ({'main':'import dep as d;fn f(p:*d.S)void{p.get();}','dep':'pub struct S{x:u64}pub fn(self:*const S)get()void{}'},'E0301'),
            ({'main':'import dep as d;fn f(p:*d.S)void{p.get();}','dep':'pub struct S{x:u64}pub unsafe fn(self:*S)get()void{}'},'E0501'),
        ]:
            with self.subTest(files=files):self.invalid(files,code)

    def test_private_enum_and_error_cannot_cross_module(self):
        for files in [
            {'main':'import dep as d;fn f()d.E{return d.E.A;}','dep':'enum E{A}'},
            {'main':'import dep as d;fn f()!u8{return error.d.Hidden;}','dep':'error Hidden=9;'},
            {'main':'import dep;','dep':'enum Hidden{A}pub fn f(p:*Hidden)void{}'},
            {'main':'import dep;','dep':'enum Hidden{A}pub type Alias=?*Hidden;'},
            {'main':'import dep;','dep':'enum Hidden{A}pub enum Public{Call(fn(*Hidden)void)}'},
        ]:
            with self.subTest(files=files):self.invalid(files,'E0201')

    def test_error_codes_are_unique_program_wide_and_import_paths_deduplicate(self):
        self.files({'main':'import a;import b;fn f()!u8{return error.a.E;}',
                    'a':'import shared;pub error E=17;','b':'import shared;',
                    'shared':'pub error Once=19;'})
        error=self.invalid({'main':'import a;import b;','a':'error A=19;','b':'error B=19;'},'E0602')
        self.assertEqual(error.token.path,'b.dg')
        for value in ['0','4294967296','-1']:
            with self.subTest(value=value):self.invalid({'main':'error E='+value+';'},'E0302')
        self.files({'main':'const BASE:u32=16;error E=BASE+1;fn f()!u8{return error.E;}'})

    def test_enum_alias_constructor_patterns_and_nested_qualified_value_fields(self):
        self.files({'main':'import dep as d;fn f()u64{let e=d.Alias.B(7);match e{d.Alias.A=>{return 0;},d.Alias.B(n)=>{return n as u64+d.object.value;},}}',
                    'dep':'pub enum E{A,B(u8)}pub type Alias=E;pub struct S{pub value:u64}pub const object:S=S{value:3};'})

    def test_top_level_namespace_collisions_include_enums_and_errors(self):
        for source in ['enum X{A}error X=7;','const X:u8=1;enum X{A}',
                       'type X=u8;error X=7;','fn X()void{}enum X{A}',
                       'struct X{x:u8}error X=7;']:
            with self.subTest(source=source):self.invalid({'main':source},'E0201')

    def test_static_pair_bytes_zero_unused_high_bits_and_payload_relocations(self):
        source='''module main;enum E{Empty,Small(i8),Call(fn()u64)}error Bad=17;
            fn target()u64{return 7;}const NEG:?i16=-123;const NONE:?i16=null;
            const BAD:!u8=error.Bad;const SMALL:E=E.Small(-1);const FN:E=E.Call(target);
        '''
        module=prepare_single(Parser(lex(source,path='main.dg')).parse(),source,'main.dg');Checker(module).check()
        objects={item.local_name:item.initializer for item in module.constants}
        self.assertEqual(objects['NEG'].data,(1).to_bytes(8,'little')+(0xff85).to_bytes(8,'little'))
        self.assertEqual(objects['NONE'].data,bytes(16))
        self.assertEqual(objects['BAD'].data,(17).to_bytes(8,'little')+bytes(8))
        self.assertEqual(objects['SMALL'].data,(1).to_bytes(8,'little')+(255).to_bytes(8,'little'))
        self.assertEqual(objects['FN'].relocations[0].offset,8)
        self.assertEqual(objects['FN'].relocations[0].symbol,module.functions[0].symbol)

    def test_unused_invalid_enum_is_reported_at_dependency(self):
        error=self.invalid({'main':'import dep;','dep':'enum Bad{Value(?u8)}'},'E0302')
        self.assertEqual(error.token.path,'dep.dg')


if __name__=='__main__':unittest.main()
