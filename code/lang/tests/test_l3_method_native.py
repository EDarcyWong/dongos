"""Methods through the actual Dong frontend/lower/NASM compiler and host CPU.

The seed only bootstraps that compiler and supplies a separate differential
baseline. The C observer checks values, pointer identities and guarded memory;
it never manufactures Graph/IR or rewrites emitted instructions.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from lang.tests import test_l3a_globals as bridge
from tools import g5_differential as g5

ROOT = Path(__file__).resolve().parents[2]

SELECTED = '''module selected;
struct S{x:u64}struct T{x:u64}
fn(self:*S)get(n:u64)u64{unsafe{return (*self).x+n;}}
fn(self:*T)get(n:u64)u64{unsafe{return (*self).x+10*n;}}
pub fn f()u64{var s=S{x:3};var t=T{x:5};
 return get(&s,2)+get(&t,7)+(&s).get(4)+(&t).get(8);
}
'''

COLLISIONS = '''module collisions;
struct S{x:u64}struct T{x:u64}
fn get(p:*S)u64{unsafe{return (*p).x+1000;}}
fn(self:*S)get()u64{unsafe{return (*self).x+10;}}
fn(self:*T)get()u64{unsafe{return (*self).x+100;}}
pub fn f()u64{var s=S{x:3};var t=T{x:5};return get(&s)+(&s).get()+(&t).get();}
'''

ORDER = '''module ordered;
pub struct S{x:u64}
pub var object:S=S{x:7};pub var trace:u64=0;pub var calls:u64=0;
fn receiver()*S{trace=trace*10+1;calls+=1;return &object;}
fn argument(n:u64)u64{trace=trace*10+n;return n;}
fn(self:*S)combine(a:u64,b:u64,c:u64,d:u64,e:u64,f:u64,g:u64)u64{
 unsafe{return (*self).x+a+2*b+3*c+4*d+5*e+6*f+7*g;}
}
pub fn f()u64{trace=0;calls=0;
 let a=receiver().combine(argument(2),argument(3),argument(4),argument(5),argument(6),argument(7),argument(8));
 if trace!=12345678||calls!=1{return 9001;}
 trace=0;calls=0;
 let b=combine(receiver(),argument(2),argument(3),argument(4),argument(5),argument(6),argument(7),argument(8));
 if trace!=12345678||calls!=1{return 9002;}
 return a+b;
}
'''

SHAPES = '''module shapes;
pub struct Box{pub guard:u8,pub value:i8,pub tail:u16}
type Alias=Box;
fn(self:*Alias)set(x:i8)void{unsafe{(*self).value=x;}}
fn(self:*Alias)small(x:i16)i8{unsafe{return ((*self).value as i16+x)as i8;}}
fn(self:*Alias)identity()*Box{return self;}
fn(self:*const Box)read()i8{unsafe{return (*self).value;}}
fn(self:*Alias)pair(a:u64,b:u64,c:u64,d:u64,bytes:[]u8,n:u64)[]u8{return bytes;}
unsafe fn(self:*Alias)unsafe_value()i8{unsafe{return (*self).value;}}
fn(self:*Alias)recurse(n:u64)u64{if n==0{return 1;}return n*self.recurse(n-1);}
pub unsafe fn run(p:*Box,bytes:[]u8)[]u8{unsafe{
 p.set(-7);if p.small(2)!=-5||p.identity()!=p||p.unsafe_value()!=-7||p.recurse(6)!=720{return bytes[0..0];}
 return pair(p,1,2,3,4,bytes,9);
}}
pub fn readonly()i8{let b=Box{guard:1,value:-101,tail:9};return (&b).read();}
'''

FOREIGN = '''module foreign;
struct A{x:u64}struct B{x:u64}
extern "sysv64"("host_a") fn(self:*A)get(n:u64)u64;
extern "sysv64"("host_b") fn(self:*B)get(n:u64)u64;
extern "sysv64" fn(self:*A)plain(n:u64)u64;
extern "sysv64"("method_alias") fn(self:*A)defined(n:u64)u64{unsafe{return (*self).x+n;}}
pub fn f()u64{var a=A{x:3};var b=B{x:5};unsafe{
 return (&a).get(1)+get(&b,2)+(&a).plain(4)+(&a).defined(6);
}}
'''

CROSS = [
    ('main.dg', '''module main;import dep as d;
struct S{x:u64}fn(self:*S)get()u64{unsafe{return (*self).x+1;}}
pub fn f()u64{var s=S{x:3};var t=d.S{x:5};return (&s).get()+(&t).get()+d.get(&t);}
'''),
    ('dep.dg', '''module dep;pub struct S{pub x:u64}type Alias=S;
pub fn(self:*Alias)get()u64{unsafe{return (*self).x+10;}}
'''),
]


def scalar_observer(module, value):
    return ('#include <stdint.h>\n#include <stdio.h>\n'
            'extern uint64_t __attribute__((sysv_abi)) f(void) __asm__("'
            + bridge.label(module, 'f') + '");\n'
            'int main(void){uint64_t x=f();if(x!=' + str(value)
            + '){fprintf(stderr,"wrong-method-value %llu\\n",(unsigned long long)x);return 17;}return 0;}')


class NativeMethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = bridge.CAND, bridge.BUILD, bridge.DRIVER
        bridge.CAND = ROOT / 'lang/bootstrap'
        bridge.BUILD = ROOT / 'build/test/l3-method-native'
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
            g5.write(cls.runner.work / 'methods.json', dict(cases=cls.runner.cases, gaps=cls.runner.gaps,
                runtime=cls.runner.runtime, commands=cls.runner.records, L3_complete=False))
            cls.h.tearDownClass()
        finally:
            bridge.CAND, bridge.BUILD, bridge.DRIVER = cls.saved

    def differential(self, name, sources, observer, tag='good', expected=0):
        directory = self.runner.source_directory(name, sources)
        texts = []
        for mode in ('debug', 'release'):
            seed = self.runner.observe(self.runner.seed(directory, mode), observer, name + '-seed-' + mode)
            asm, result = self.runner.dong(directory, mode, tag)
            self.assertEqual(result.returncode, 0, result.stderr)
            target = self.runner.observe(asm, observer, name + '-dong-' + mode, expect=expected)
            if expected == 0:
                self.assertEqual((seed['stdout'], seed['returncode']), (target['stdout'], target['returncode']))
            else:
                self.assertIn('wrong-method-value', target['stderr'])
            self.runner.cases.append(dict(name=name, mode=mode, seed=seed, native=target,
                status='negative-rejected' if expected else 'supported-pass'))
            texts.append(asm.read_text())
        return texts

    def test_selected_declaration_and_both_call_forms(self):
        texts = self.differential('selected', [('selected.dg', SELECTED)], scalar_observer('selected', 172))
        for text in texts:
            for nominal in ('S', 'T'):
                symbol = bridge.label('selected', 'get') + '_t' + nominal.encode().hex()
                self.assertEqual(text.count(symbol + ':'), 1)
                self.assertIn('call ' + symbol + '\n', text)

    def test_free_function_and_same_name_methods_do_not_collide(self):
        texts = self.differential('collisions', [('collisions.dg', COLLISIONS)], scalar_observer('collisions', 1121))
        for text in texts:
            free = bridge.label('collisions', 'get')
            self.assertEqual(text.count(free + ':'), 1)
            self.assertIn(free + '_t53:', text)
            self.assertIn(free + '_t54:', text)

    def test_receiver_once_before_nested_arguments_and_stack(self):
        # Each call is 7 + (2 + 6 + 12 + 20 + 30 + 42 + 56) == 175.
        self.differential('ordered', [('ordered.dg', ORDER)], scalar_observer('ordered', 350))

    def test_pointer_alias_const_unsafe_narrow_void_recursive_and_slice_pair(self):
        obs = '''#include <stdint.h>
#include <string.h>
typedef struct{void*p;uint64_t n;}Slice;
extern Slice __attribute__((sysv_abi)) run(void*,Slice) __asm__("''' + bridge.label('shapes', 'run') + '''");
extern int8_t __attribute__((sysv_abi)) readonly(void) __asm__("''' + bridge.label('shapes', 'readonly') + '''");
int main(void){unsigned char guarded[8]={0x11,0x22,0x5a,0x10,0xef,0xbe,0x33,0x44};
 unsigned char bytes[4]={1,2,3,4};Slice p=run(guarded+2,(Slice){bytes,4});
 const unsigned char expected[8]={0x11,0x22,0x5a,0xf9,0xef,0xbe,0x33,0x44};
 if(p.p!=bytes||p.n!=4||memcmp(guarded,expected,8)||readonly()!=-101){return 17;}return 0;}
'''
        self.differential('shapes', [('shapes.dg', SHAPES)], obs)

    def test_cross_module_public_method_and_nominal_alias(self):
        texts = self.differential('cross', CROSS, scalar_observer('main', 34))
        for text in texts:
            self.assertIn(bridge.label('main', 'get') + '_t53:', text)
            self.assertIn(bridge.label('dep', 'get') + '_t53:', text)

    def test_bodyless_method_link_names_and_explicit_definition_alias(self):
        obs = scalar_observer('foreign', 270)
        obs = obs.replace('int main(void)', '''
uint64_t __attribute__((sysv_abi)) host_a(uint64_t*p,uint64_t n){return *p+10*n;}
uint64_t __attribute__((sysv_abi)) host_b(uint64_t*p,uint64_t n){return *p+100*n;}
uint64_t __attribute__((sysv_abi)) plain(uint64_t*p,uint64_t n){return *p+10*n;}
int main(void)''')
        # 13 + 205 + 43 + 9 == 270; the C link observes each distinct symbol.
        texts = self.differential('foreign', [('foreign.dg', FOREIGN)], obs)
        for text in texts:
            for name in ('host_a', 'host_b', 'plain'):
                self.assertIn('extern $' + name + '\n', text)
                self.assertNotIn('$' + name + ':', text)
            self.assertIn('global $method_alias\n$method_alias:', text)

    def test_frontend_rejections_preserve_output_and_sources(self):
        from lang.tests import test_bootstrap_method_semantics as semantic
        cases = [([(0, 'a.dg', 'module a;' + src)], status) for src, status in semantic.ALIGNED if status]
        cases += semantic.MODULE_BAD
        for i, (sources, status) in enumerate(cases):
            directory = self.runner.source_directory('rejected-' + str(i), [(p, s) for _, p, s in sources])
            for mode in ('debug', 'release'):
                asm, result = self.runner.dong(directory, mode)
                self.assertEqual(result.returncode, 10, result.stderr)
                self.assertRegex(result.stderr, 'frontend status=3 stage=4 code=' + str(status) + r'\b')
                self.assertEqual(asm.read_bytes(), b'unchanged')

    def test_g5_closed_paths_require_native_execution(self):
        first = len(self.runner.cases)
        self.runner.known_gaps()
        self.assertEqual({(c['name'], c['mode']) for c in self.runner.cases[first:]},
            {(n, m) for n in ('method', 'defer', 'extern-sysv', 'for-range', 'for-array', 'for-slice', 'bool-match') for m in ('debug', 'release')})
        self.assertEqual({(c['name'], c['mode']) for c in self.runner.gaps},
            {(n, m) for n in ('enum', 'error', 'try', 'orelse', 'extern-win64') for m in ('debug', 'release')})

    def test_existing_native_scalar_aggregate_global_and_sysv_regressions(self):
        # Run the unchanged SysV observations through these freshly built
        # compiler objects, including actual host extern definitions and links.
        from lang.tests import test_l3_sysv_native as sysv
        check = sysv.NativeSysVTests()
        check.h, check.runner = self.h, self.runner
        check.test_explicit_definitions_aliases_narrow_stack_and_pointer()
        check.test_external_imports_execute_real_host_functions()
        check.test_same_source_name_distinct_module_link_names()
        check.test_win64_and_foreign_pair_rejections_keep_output()
        from lang.tests import test_bootstrap_native_compiler as audit
        from lang.tests.test_dongc import nasm_flags
        self.runner.abi = self.runner.work / 'abi.asm'
        self.runner.abi.write_text(audit.ABI_PROBE)
        self.runner.abi_obj = self.runner.abi.with_suffix('.obj')
        self.runner.command([self.h.nasm, '-f', 'win64', *nasm_flags(self.h.nasm),
            self.runner.abi, '-o', self.runner.abi_obj], 'abi-object')
        self.runner.supported()

    def test_real_dong_candidate_head_mutant_fails_independent_value_oracle(self):
        old = 'target=method_target(s,n.a,id);if (*s).status!=0{return NONE;}'
        bad = 'if r.kind!=binding.METHOD_CANDIDATE{target=method_target(s,n.a,id);}if (*s).status!=0{return NONE;}'
        self.h.build_driver('bad-head', {'lower_program.dg': (old, bad)})
        self.differential('bad-head', [('selected.dg', SELECTED)], scalar_observer('selected', 172), 'bad-head', 17)


if __name__ == '__main__':
    unittest.main()
