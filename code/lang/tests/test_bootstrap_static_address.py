"""Native static relocations: real typed graphs, no runtime global reads."""
import hashlib,json,shutil,unittest
from pathlib import Path
from lang.tests import test_bootstrap_semantic_runtime as rt
from lang.tests import test_bootstrap_semantic_types as decl

class BootstrapStaticAddressTests(unittest.TestCase):
    wrapper=rt.WRAPPER
    build=classmethod(rt.BootstrapSemanticRuntimeTests.build.__func__)
    run_cases=decl.BootstrapSemanticTypesTests.run_cases
    @classmethod
    def setUpClass(cls):
        if not rt.tool('nasm','NASM') or not rt.tool('gcc','CC'):raise RuntimeError('native tools required; no skip')
        rt.BootstrapSemanticRuntimeTests.setUpClass.__func__(cls)
        if not cls.nasm or not cls.cc:raise RuntimeError('native tools required; no skip')
        cls.extra={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),rt.ROOT/'docs/bootstrap-static-address.md']}
    @classmethod
    def tearDownClass(cls):
        decl.BootstrapSemanticTypesTests.tearDownClass.__func__(cls)
        after={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in cls.extra}
        production={p:hashlib.sha256((rt.ROOT/'lang/bootstrap'/p).read_bytes()).hexdigest() for p in cls.files}
        if after!=cls.extra or production!=cls.inputs:raise AssertionError('static-address inputs changed')
        (cls.work/'static-address-summary.json').write_text(json.dumps(dict(inputs=cls.inputs,extra_inputs=cls.extra,source_stable=True,records=cls.records),indent=2)+'\n')
    @staticmethod
    def samples():
        prefix='module a;var bytes:[4]u8=[1,2,3,4];'
        good=[prefix+'var p:*u8=&bytes[0];',prefix+'const I:usize=1;var p:*u8=&bytes[I+1];',
              'module a;var x:u64=7;var p:*u64=&x;',
              'module a;const x:u64=7;var p:*const u64=&x;',
              'module a;struct S{x:u8,y:[3]u64}var s:S=S{x:1,y:[7,8,9]};var p:*u64=&s.y[2];',
              prefix+'struct P{x:*u8}var x:P=P{x:&bytes[2]};',
              prefix+'var p:[2]*u8=[&bytes[0],&bytes[3]];',
              prefix+'var p:*const u8=&bytes[1];',
              'module a;var p:*u64=&x;var x:u64=7;']
        bad=[(prefix+'var i:usize=1;var p:*u8=&bytes[i];',5),
             (prefix+'fn index()usize{return 1;}var p:*u8=&bytes[index()];',5),
             (prefix+'var p:*u8=&bytes[4];',3),
             ('module a;const x:u64=7;var p:*u64=&x;',3),
             ('module a;var x:u64=7;var p:*u8=&x;',3),
             ('module a;var p:*u8=null;var q:*u8=p;',5),
             ('module a;var p:*u8=null;var q:*u8=&*p;',13),
             ('module a;var x:u64=7;fn get()*u64{return &x;}var p:*u64=get();',5)]
        return [decl.case(s) for s in good]+[decl.case(s,code) for s,code in bad]
    def test_static_places_and_dynamic_rejections(self):
        cases=self.samples()
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'static-places-'+mode)
        self.records.append(dict(test='static-places',cases=len(cases),modes=2,passed=True))
    def test_cross_module_visibility_and_const(self):
        cases=[]
        for readonly,public,expected in [(False,True,0),(True,True,0)]:
            typ='*const u64' if readonly else '*u64'
            declkind='pub const' if readonly else ('pub var' if public else 'var')
            files=[(0,'a.dg',f'module a;import b;var p:{typ}=&b.x;'),(0,'b.dg',f'module b;{declkind} x:u64=7;')]
            cases.append(decl.case('',expected,files=files))
        for mode,exe in self.executables.items():
            self.run_cases(exe,cases,'static-modules-'+mode)
            private=decl.case('',files=[(0,'a.dg','module a;import b;var p:*u64=&b.x;'),(0,'b.dg','module b;var x:u64=7;')])
            with self.assertRaisesRegex(AssertionError,'binding failed'):self.run_cases(exe,[private],'static-private-'+mode)
        self.records.append(dict(test='static-cross-module',cases=3,modes=2,passed=True))
    def test_real_wrong_static_predicates_are_rejected(self):
        source=(self.snapshot/'bootstrap/semantic_types.dg').read_text(encoding='utf-8')
        needle='if n.kind==ast.UNARY&&n.op==1062{return rt_static_place(c,n.a,depth+1);}'
        self.assertEqual(source.count(needle),1)
        samples=[('deny-all',needle.replace('rt_static_place(c,n.a,depth+1)','false'),self.samples()[0]),
                 ('accept-runtime-index',needle.replace('rt_static_place(c,n.a,depth+1)','true'),self.samples()[9])]
        for name,replacement,case in samples:
            root=self.work/('bad-static-'+name);(root/'bootstrap').mkdir(parents=True)
            for f in self.files:shutil.copy2(self.snapshot/'bootstrap'/f,root/'bootstrap'/f)
            (root/'bootstrap/semantic_types.dg').write_text(source.replace(needle,replacement),encoding='utf-8')
            for mode in ('debug','release'):
                self.run_cases(self.executables[mode],[case],name+'-good-'+mode)
                exe=self.build(root,mode,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'status'):self.run_cases(exe,[case],name+'-'+mode)
                self.records.append(dict(test='real-wrong-Dong-static',variant=name,mode=mode,native_returned=True,rejected_by='semantic status',passed=True))

if __name__=='__main__':unittest.main()
