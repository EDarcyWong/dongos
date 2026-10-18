"""Independent semantic contracts for the remaining L1 language features."""
from __future__ import annotations
import unittest
from lang.dongc import CompileError,compile_source


class L1SemanticsTests(unittest.TestCase):
    def valid(self,source):
        return compile_source('module l1;'+source)

    def invalid(self,source,code):
        with self.assertRaises(CompileError) as caught:
            self.valid(source)
        self.assertEqual(caught.exception.code,code,str(caught.exception))

    def test_noreturn_control_flow_and_bottom_arguments(self):
        for source in [
            'fn stop()noreturn{loop{}}',
            'fn stop()noreturn{loop{if false{break;}}}',
            'fn f()u64{loop{if false{break;}return 7;}}',
            'fn stop()noreturn{loop{}}fn use(x:u64)void{}fn f()u64{use(stop());}',
            'fn stop()noreturn{loop{}}fn f()u64{let x:u64=stop();return x;}',
            'fn stop()noreturn{loop{}}fn f()u64{if stop(){return 1;}}',
            'type Stop=fn()noreturn;fn f(p:Stop)noreturn{unsafe{p();}}',
            'fn f()noreturn{while false{break;}loop{}}',
            'fn stop()noreturn{loop{}}fn f()u64{while stop(){}}',
            'fn stop()noreturn{loop{}}fn f()u64{for i in 0..stop(){}}',
            'fn stop()noreturn{loop{}}fn f()u64{let x=stop()+1;}',
            'const O:?u64=null;fn stop()noreturn{loop{}}fn f()u64{let x=O orelse stop();}',
            'fn stop()noreturn{loop{}}fn f()u64{let x=true&&stop();}',
            'const O:?u64=null;fn stop()noreturn{loop{}}fn use(a:u64,b:u64)void{}fn f()noreturn{loop{use(stop(),O orelse break);}}',
            'const O:?bool=null;fn f()noreturn{loop{let x=false&&(O orelse break);}}',
            'const O:?u64=null;fn stop()noreturn{loop{}}fn f()noreturn{loop{for i in stop()..(O orelse break){}}}',
        ]:
            with self.subTest(source=source):self.valid(source)
        for source in ['fn stop()noreturn{loop{}}fn f()u64{let n=false&&stop();}',
                       'fn stop()noreturn{loop{}}fn f()u64{if false&&stop(){return 1;}}',
                       'fn stop()noreturn{loop{}}fn f()u64{let n=true||stop();}',
                       'fn stop()noreturn{loop{}}fn f(b:bool)u64{let n=b&&stop();}',
                       'fn f()noreturn{}','fn f()noreturn{if false{return; }loop{}}','fn f()u64{loop{break;}}']:
            with self.subTest(source=source):self.invalid(source,'E0402')

    def test_loops_definite_initialization_and_immutable_iteration(self):
        self.valid('fn f(b:bool)u64{var x:u64;loop{if b{x=1;break;}x=2;break;}return x;}')
        self.valid('fn f()u64{var x:u64;while true{x=7;break;}return x;}')
        for source,code in [
            ('fn f()u64{var x:u64;for i in 0..3{x=i;}return x;}','E0401'),
            ('fn f(b:bool)u64{var x:u64;loop{if b{break;}x=7;break;}return x;}','E0401'),
            ('fn f()void{for i in 0..3{i=2;}}','E0402'),
            ('fn f()void{for i in 0..3{let x:u64=i;}let y=i;}','E0201'),
            ('fn f(x:u8)void{for i in x..3{}}','E0301'),
            ('fn f()void{for i in true{}}','E0301'),
        ]:
            with self.subTest(source=source):self.invalid(source,code)

    def test_defer_registration_initialization_and_context_restrictions(self):
        self.valid('fn use(x:u64)void{}fn f()void{var x:u64=1;defer use(x);x=2;}')
        self.valid('fn stop()noreturn{loop{}}fn f()void{defer stop();}')
        self.valid('fn stop()noreturn{loop{}}fn f()noreturn{defer stop();}')
        self.valid('fn stop()noreturn{loop{}}fn f()noreturn{loop{defer stop();break;}}')
        self.valid('fn f()void{defer{var x:u64;x=1;}}')
        for source,code in [
            ('fn f()void{var x:u64;defer{x=1;}}','E0401'),
            ('fn use(x:u64)void{}fn f()void{var x:u64;defer use(x);x=1;}','E0401'),
            ('fn f()void{defer{return;}}','E0501'),
            ('fn f()void{loop{defer{break;}}}','E0501'),
            ('fn f()void{loop{defer{continue;}}}','E0501'),
            ('fn use()void{}fn f()void{defer{defer use();}}','E0501'),
            ('error E=1;fn g()!void{return;}fn f()!void{defer{try g();}return;}','E0501'),
        ]:
            with self.subTest(source=source):self.invalid(source,code)

    def test_local_constants_width_shape_scope_and_shadow(self):
        self.valid('const N:usize=9;fn f()u64{const N:usize=3;const V:u8=255;const Z=wrapping_add(V,1);var a:[N]u64=[7;N];{const N=2;var b:[N]u64=[1;N];}return a.len+(Z as u64);}')
        self.valid('fn f()u64{const N=2;{let N:u64=7;}var a:[N]u8=[1;N];return a.len;}')
        self.valid('enum E{A,B(u8)}fn f()u8{const X:E=E.B(7);match X{E.B(n)=>{return n;},_=>{return 0;},}}')
        for source,code in [
            ('fn f()void{const X:u8=256;}','E0302'),
            ('fn f()void{let n:u64=3;const X=n;}','E0601'),
            ('fn f()void{const N=3;{let N:u64=2;var a:[N]u8;}}','E0601'),
            ('fn f()void{const N=3;N=4;}','E0402'),
            ('fn f()void{const N=3;const N=4;}','E0201'),
            ('fn f(N:u64)void{const N=3;}','E0201'),
            ('fn f()void{{const N=3;}var a:[N]u8;}','E0201'),
        ]:
            with self.subTest(source=source):self.invalid(source,code)

    def test_enum_constructors_comparisons_and_payload_types(self):
        self.valid('enum E{A,B}fn f(x:E)bool{return x==E.A;}')
        self.valid('type Byte=u8;enum E{A(Byte),B(*[sizeof(E)]u8)}')
        self.valid('type F=fn()void;const N:usize=sizeof(E);enum E{A(F),B(*[N]u8)}')
        self.valid('enum E{A,B(i8),C(fn()u64)}fn value()u64{return 3;}const X:E=E.C(value);fn f()E{return E.B(-128);}')
        for source,code in [
            ('enum E{A,B(u8)}fn f()E{return E.B;}','E0301'),
            ('enum E{A,B}fn f()E{return E.A(1);}','E0301'),
            ('enum E{A,B(u8)}fn f()E{return E.B(256);}','E0302'),
            ('enum E{A}fn f()E{return E.Z;}','E0201'),
            ('enum E{A}fn f()E{return 0 as E;}','E0301'),
            ('enum E{A,B(u8)}fn f(x:E)bool{return x==x;}','E0301'),
            ('enum E{A}enum F{A}fn f(x:E,y:F)bool{return x==y;}','E0301'),
            ('enum E{A(?u8)}','E0302'),
            ('enum E{A(E)}','E0302'),
        ]:
            with self.subTest(source=source):self.invalid(source,code)

    def test_match_exhaustiveness_duplicate_and_binding_scope(self):
        self.valid('fn f(x:bool)u64{var n:u64;match x{true=>{n=1;},false=>{n=2;},}return n;}')
        for source,code in [
            ('enum E{A,B}fn f(e:E)void{match e{E.A=>{},}}','E0403'),
            ('fn f(b:bool)void{match b{true=>{},true=>{},false=>{},}}','E0403'),
            ('fn f(b:bool)void{match b{_=>{},false=>{},}}','E0403'),
            ('fn f(b:bool)void{match b{true=>{},false=>{},_=>{},}}','E0403'),
            ('enum E{A,B(u8)}fn f(e:E)void{match e{E.A=>{},E.B=>{},}}','E0301'),
            ('enum E{A}fn f(e:E)void{match e{E.A(n)=>{},}}','E0301'),
            ('fn f(x:?u8)void{match x{null=>{},some(n)=>{n=1;},}}','E0402'),
            ('fn f(x:?u8)u8{match x{null=>{return 0;},some(n)=>{},}return n;}','E0201'),
            ('fn f(x:u64)void{match x{_=>{},}}','E0301'),
        ]:
            with self.subTest(source=source):self.invalid(source,code)

    def test_optional_results_try_orelse_and_void(self):
        self.valid('error E=17;fn g(b:bool)!u8{if b{return error.E;}return 7;}fn f()!u64{let n=try g(false);return n as u64;}')
        self.valid('fn f(x:?u8)u64{let n=x orelse return 9;return n as u64;}')
        self.valid('fn f(x:!void)u64{match x{ok=>{return 1;},err(code)=>{return code;},}}')
        self.valid('fn f()!void{return;}fn g()!void{try f();return;}')
        self.valid('fn f()void{const X:?u8=7;const Y:u8=X orelse 9;var a:[Y]u8;}')
        for source,code in [
            ('fn f()u8{return try 7;}','E0501'),
            ('fn f()!u8{return try 7;}','E0301'),
            ('fn g()!u8{return 7;}fn f()void{g();}','E0301'),
            ('fn f()void{let x=try 7;}','E0501'),
            ('fn f(x:?u8)u8{return x;}','E0301'),
            ('fn f()u8{return 7 orelse 9;}','E0301'),
            ('fn f()void{let x:?u8=null;let y=x orelse break;}','E0101'),
            ('fn f()!void{return 7;}','E0301'),
            ('fn f()!void{let x:void=try f();return;}','E0302'),
            ('fn f()void{var x:?[]u8;}','E0302'),
            ('fn f()void{var x:??u8;}','E0302'),
            ('fn g()!u8{return 7;}const X:u8=try g();','E0501'),
        ]:
            with self.subTest(source=source):self.invalid(source,code)

    def test_methods_require_exact_explicit_pointer_receiver(self):
        self.valid('struct S{x:u64}fn(self:*S)get()u64{unsafe{return (*self).x;}}fn f()u64{var s=S{x:7};return get(&s);}')
        self.valid('struct S{x:u64}fn(self:*S)get()u64{unsafe{return (*self).x;}}fn f()u64{var s=S{x:7};return (&s).get();}')
        self.valid('enum E{A,B}fn(self:*const E)read()bool{unsafe{return *self==E.A;}}fn f()bool{let e=E.A;return (&e).read();}')
        for source,code in [
            ('struct S{x:u64}fn(self:S)get()void{}','E0301'),
            ('fn(self:*u64)get()void{}','E0201'),
            ('struct S{x:u64}fn(self:*S)x()void{}','E0201'),
            ('struct S{x:u64}fn(self:*S)get()void{}fn(self:*const S)get()void{}','E0201'),
            ('struct S{x:u64}fn(self:*S)get()void{}fn f()void{var s=S{x:0};s.get();}','E0201'),
            ('struct S{x:u64}fn(self:*const S)get()void{}fn f()void{var s=S{x:0};(&s).get();}','E0301'),
            ('struct S{x:u64}fn(self:*const S)get()void{}fn f()void{var s=S{x:0};get(&s);}','E0301'),
        ]:
            with self.subTest(source=source):self.invalid(source,code)


if __name__=='__main__':unittest.main()
