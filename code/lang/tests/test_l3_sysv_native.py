"""Execute real Dong-generated SysV definitions and external object links.

The seed only bootstraps the compiler executable. The shared L3A bridge also
checks exact/short capacities, aliases, guards and immutable graph/source/IR.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from lang.tests import test_l3a_globals as bridge
from tools import g5_differential as g5

ROOT = Path(__file__).resolve().parents[2]

DEFINITIONS = '''module defs;
pub extern "sysv64" fn sum(a:u64,b:u64,c:u64,d:u64,e:u64,f:u64,g:u64,h:u64)u64{
 return a+2*b+3*c+4*d+5*e+6*f+7*g+8*h;
}
pub extern "sysv64"("sysv_narrow") fn narrow(a:i8,b:u16,c:i32) i64{
 return (a as i64)+(b as i64)+(c as i64);
}
export("rax") pub extern "sysv64" fn keyword(x:u64)u64{return x+17;}
pub extern "sysv64"("sysv_touch") unsafe fn touch(p:*u8,n:u8)u8{unsafe{*p=n;return *p;}}
pub fn local()u64{return sum(1,2,3,4,5,6,7,8);}
'''

IMPORTS = '''module imports;
extern "sysv64" fn host_eight(a:u64,b:u64,c:u64,d:u64,e:u64,f:u64,g:u64,h:u64)u64;
extern "sysv64"("host_narrow") fn renamed(a:i8,b:u16,c:i32)i8;
export("host_touch") extern "sysv64" fn touch(p:*u8,n:u8)u8;
pub fn run()u64{unsafe{return host_eight(1,2,3,4,5,6,7,8);}}
pub fn small()i8{unsafe{return renamed(-7,60000,-123456);}}
pub unsafe fn write(p:*u8)u8{unsafe{return touch(p,0xa5);}}
'''


class NativeSysVTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = bridge.CAND, bridge.BUILD, bridge.DRIVER
        bridge.CAND = ROOT / 'lang/bootstrap'
        bridge.BUILD = ROOT / 'build/test/l3-sysv'
        bridge.DRIVER = g5.diagnostic_driver().replace(
            'if(rc){REQUIRE(unpublished(&lr));',
            'if(rc){REQUIRE(arena_hash==hash(arena.p,arena.n)&&sources_hash==source_hash(catalog,sources));REQUIRE(unpublished(&lr));')
        try:
            bridge.L3AGlobalsTests.setUpClass()
        except BaseException:
            bridge.CAND, bridge.BUILD, bridge.DRIVER = cls.saved
            raise
        cls.h = bridge.L3AGlobalsTests()
        cls.h.inputs[str(Path(__file__))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        cls.runner = g5.Runner(cls.h.work / 'differential')
        cls.runner.g, cls.runner.nasm, cls.runner.cc = cls.h, cls.h.nasm, cls.h.cc

    @classmethod
    def tearDownClass(cls):
        try:
            cls.runner.assert_inputs()
            cls.h.tearDownClass()
        finally:
            bridge.CAND, bridge.BUILD, bridge.DRIVER = cls.saved

    def emit(self, name, sources, mode, tag='good'):
        directory, asm = self.h.generate(tag, sources, name + '-' + str(mode), mode)
        return directory, asm

    def test_explicit_definitions_aliases_narrow_stack_and_pointer(self):
        for mode in (0, 1):
            directory, asm = self.emit('definitions', [('defs.dg', DEFINITIONS)], mode)
            obj = self.h.assemble(asm, 'definitions-' + str(mode))
            text = asm.read_text()
            self.assertIn('global $sysv_narrow\n$sysv_narrow:', text)
            self.assertIn('global $rax\n$rax:', text)
            declarations = '\n'.join([
                f'extern U ABI sum(U,U,U,U,U,U,U,U) __asm__("{bridge.label("defs", "sum")}");',
                f'extern U ABI local(void) __asm__("{bridge.label("defs", "local")}");',
                'extern int64_t ABI narrow(int8_t,uint16_t,int32_t) __asm__("sysv_narrow");',
                'extern U ABI keyword(U) __asm__("rax");',
                'extern uint8_t ABI touch(uint8_t*,uint8_t) __asm__("sysv_touch");',
            ])
            body = '''
 uint8_t bytes[3]={0x11,0x22,0x33};
 if(sum(1,2,3,4,5,6,7,8)!=204||local()!=204)return 1;
 if(narrow(-7,60000,-123456)!=-63463||keyword(5)!=22)return 2;
 if(touch(bytes+1,0xa5)!=0xa5||bytes[0]!=0x11||bytes[1]!=0xa5||bytes[2]!=0x33)return 3;
 puts("sysv-definitions-ok");return 0;'''
            self.h.observe(obj, 'definitions-observer-' + str(mode), body, declarations)

    def test_external_imports_execute_real_host_functions(self):
        for mode in (0, 1):
            directory, asm = self.emit('imports', [('imports.dg', IMPORTS)], mode)
            obj = self.h.assemble(asm, 'imports-' + str(mode))
            text = asm.read_text()
            for name in ('host_eight', 'host_narrow', 'host_touch'):
                self.assertIn('extern $' + name + '\n', text)
                self.assertNotIn('$' + name + ':', text)
            declarations = '''
 U ABI host_eight(U a,U b,U c,U d,U e,U f,U g,U h){return a+2*b+3*c+4*d+5*e+6*f+7*g+8*h;}
 int8_t ABI host_narrow(int8_t a,uint16_t b,int32_t c){return a==-7&&b==60000&&c==-123456?-101:99;}
 uint8_t ABI host_touch(uint8_t*p,uint8_t n){*p=n;return n;}
''' + '\n'.join([
                f'extern U ABI run(void) __asm__("{bridge.label("imports", "run")}");',
                f'extern int8_t ABI small(void) __asm__("{bridge.label("imports", "small")}");',
                f'extern uint8_t ABI write_byte(uint8_t*) __asm__("{bridge.label("imports", "write")}");',
            ])
            body = '''uint8_t a[3]={1,2,3};if(run()!=204||small()!=-101)return 1;
 if(write_byte(a+1)!=0xa5||a[0]!=1||a[1]!=0xa5||a[2]!=3)return 2;
 puts("sysv-imports-ok");return 0;'''
            self.h.observe(obj, 'imports-observer-' + str(mode), body, declarations)

    def test_same_source_name_distinct_module_link_names(self):
        sources = [
            ('main.dg', 'module main;import dep as dep;extern "sysv64"("host_left") fn same()u64;pub fn f()u64{unsafe{return same()+dep.f();}}'),
            ('dep.dg', 'module dep;extern "sysv64"("host_right") fn same()u64;pub fn f()u64{unsafe{return same();}}'),
        ]
        for mode in (0, 1):
            _, asm = self.emit('cross-module', sources, mode)
            obj = self.h.assemble(asm, 'cross-module-' + str(mode))
            dec = 'U ABI host_left(void){return 17;}U ABI host_right(void){return 31;}\n'
            dec += f'extern U ABI f(void) __asm__("{bridge.label("main", "f")}");'
            self.h.observe(obj, 'cross-observer-' + str(mode), 'return f()!=48;', dec)

    def test_native_container_consumes_actual_emitted_aliases(self):
        from lang.tests import test_l3_escaped_symbols as escaped
        escaped.EscapedSymbolTests.setUpClass()
        check = escaped.EscapedSymbolTests()
        try:
            for mode in (0, 1):
                source = DEFINITIONS + 'export("__dong_panic")fn panic(k:u32,line:u32,p:*const u8,n:usize)noreturn{loop{}}\n'
                _, asm = self.emit('native-alias-container', [('defs.dg', source)], mode)
                self.assertIn('global $__dong_panic\n', asm.read_text())
                self.assertNotIn('extern $__dong_panic\n', asm.read_text())
                status, image, result = check.assemble('release' if mode else 'debug', asm.read_text(), entry=bridge.label('defs', 'local'))
                self.assertEqual(status, 0, (result.line, result.detail))
                self.assertEqual(check.execute(image), 204)
        finally:
            escaped.EscapedSymbolTests.tearDownClass()

    def test_win64_definitions_and_declarations_execute(self):
        cases = [
            ('win-definition', 'bad', 'module bad;pub extern "win64" fn f()u64{return 7;}',
             'extern U __attribute__((ms_abi)) f(void) __asm__("' + bridge.label('bad', 'f') + '");',
             'return f()!=7;', None),
            ('win-declaration', 'bad', 'module bad;extern "win64" fn x()u64;pub fn f()u64{unsafe{return x();}}',
             'U __attribute__((ms_abi)) x(void){return 11;}\n'
             'extern U ABI f(void) __asm__("' + bridge.label('bad', 'f') + '");',
             'return f()!=11;', 'x'),
            ('legacy-win-declaration', 'unsupported',
             'module unsupported;extern "win64" fn f()u64;pub fn invoke()u64{unsafe{return f();}}',
             'U __attribute__((ms_abi)) f(void){return 13;}\n'
             'extern U ABI invoke(void) __asm__("' + bridge.label('unsupported', 'invoke') + '");',
             'return invoke()!=13;', 'f'),
        ]
        for mode in (0, 1):
            for name, module, source, declarations, body, external in cases:
                with self.subTest(mode=mode, name=name):
                    _, asm = self.emit(name, [(module + '.dg', source)], mode)
                    if external:
                        self.assertIn('extern $' + external + '\n', asm.read_text())
                        self.assertNotIn('$' + external + ':', asm.read_text())
                    obj = self.h.assemble(asm, name + '-' + str(mode))
                    self.h.observe(obj, name + '-observer-' + str(mode), body, declarations)

    def test_foreign_pair_and_invalid_link_names_keep_output(self):
        cases = [
            ('foreign-pair', 'module bad;extern "sysv64" fn x(s:[]u8)u64;pub fn f()u64{return 7;}', 10),
            ('bad-linker', 'module bad;extern "sysv64"("bad-name") fn x()u64;pub fn f()u64{return 7;}', 10),
        ]
        for mode in (0, 1):
            for name, source, status in cases:
                with self.subTest(mode=mode, name=name):
                    directory = self.h.work / (name + '-' + str(mode))
                    directory.mkdir()
                    src, out = directory / 'bad.dg', directory / 'module.asm'
                    src.write_text(source)
                    out.write_bytes(b'preserved-output')
                    p = self.h.command([self.h.drivers['good'], src, 'bad.dg', out, mode], name + '-reject-' + str(mode), status)
                    self.assertEqual(out.read_bytes(), b'preserved-output')
                    self.assertEqual(src.read_text(), source)
                    self.assertIn('status=', p.stderr)

    def test_mutated_dong_link_target_rejected_by_value_oracle(self):
        old = 'return put(s,"$")&&put(s,names.text((*g).sources,(*g).units,(*g).tokens,sy.unit,sy.name_token));'
        self.h.build_driver('bad-link', {'nasm_program.dg': (old, 'return put(s,"$host_decoy");')})
        source = 'module negative;extern "sysv64" fn host_value()u64;pub fn f()u64{unsafe{return host_value();}}'
        for mode in (0, 1):
            _, asm = self.emit('bad-link-target', [('negative.dg', source)], mode, 'bad-link')
            obj = self.h.assemble(asm, 'bad-link-' + str(mode))
            observer = obj.parent / 'negative.c'
            observer.write_text('#include <stdint.h>\n#include <stdio.h>\n'
                'uint64_t __attribute__((sysv_abi)) host_value(void){return 7;}\n'
                'uint64_t __attribute__((sysv_abi)) host_decoy(void){return 8;}\n'
                f'extern uint64_t __attribute__((sysv_abi)) f(void) __asm__("{bridge.label("negative", "f")}");\n'
                'int main(void){if(f()!=7){fputs("wrong-external-target\\n",stderr);return 17;}return 0;}')
            exe = observer.with_suffix('.exe')
            self.h.command([self.h.cc, '-O2', observer, obj, '-o', exe], 'bad-link-observer-' + str(mode))
            p = self.h.command([exe], 'bad-link-value-' + str(mode), 17)
            self.assertIn('wrong-external-target', p.stderr)

    def test_g5_sysv_and_win64_fixtures_execute(self):
        first = len(self.runner.cases)
        with patch.dict(g5.GAPS, {k: v for k, v in g5.GAPS.items() if k.startswith('extern-')}, clear=True):
            self.runner.known_gaps()
        self.assertEqual([(c['name'], c['mode']) for c in self.runner.cases[first:]],
                         [(name, mode) for name in ('extern-sysv', 'extern-win64') for mode in ('debug', 'release')])
        self.assertEqual(self.runner.gaps, [])
        for case in self.runner.cases[first:]:
            g5.validate_path(case)
        g5.write(self.runner.work / 'sysv-coverage.json', dict(supported=self.runner.cases, gaps=self.runner.gaps, commands=self.runner.records))


if __name__ == '__main__':
    unittest.main()
