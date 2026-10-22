"""Frozen mainline gate: all permanent method/defer/for cases, one good build.

Only compiler build objects are shared. Each permanent test receives a fresh
differential directory and input manifest, preserving all independent oracles.
The three real Dong mutation builds remain separate.
"""
import hashlib,json,sys,unittest
from pathlib import Path
WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS
if not (ROOT/'lang').is_dir():
    root=Path(json.loads((WORKS/'project.json').read_text(encoding='utf-8'))['source_root'])
    ROOT=root if root.is_absolute() else (WORKS/root).resolve()
sys.path.insert(0,str(ROOT))
from lang.tests import test_l3_method_native as methods
from lang.tests import test_l3_defer_native as defer
from lang.tests import test_l3_for_native as iterate
from lang.tests import test_l3_sysv_native as sysv
from lang.tests import test_l3_escaped_symbols as escaped
from lang.tests import test_dongc as seed_tools
from tools import g5_differential as g5

CORE=[('method',methods,methods.NativeMethodTests),('defer',defer,defer.DeferNativeTests),('for',iterate,iterate.ForNativeTests)]
CASE_LABELS={tag[0]+hashlib.sha256((tag+'.'+name).encode()).hexdigest()[:7]:tag+'.'+name
    for tag,_,case_type in CORE for name in unittest.defaultTestLoader.getTestCaseNames(case_type)}
assert len(CASE_LABELS)==sum(len(unittest.defaultTestLoader.getTestCaseNames(c)) for _,_,c in CORE)

class ControlIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        methods.NativeMethodTests.setUpClass.__func__(cls)
        cls.runners=[];cls.executed=[]
        for path in [Path(__file__),*(Path(m.__file__) for _,m,_ in CORE),Path(sysv.__file__),
            Path(escaped.__file__),Path(seed_tools.__file__),Path(g5.__file__)]:
            cls.h.inputs[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    @classmethod
    def tearDownClass(cls):
        try:
            for runner in cls.runners:runner.assert_inputs()
            g5.write(cls.h.work/'control-integration.json',dict(
                permanent_tests=cls.executed,counts={tag:len(unittest.defaultTestLoader.getTestCaseNames(c)) for tag,_,c in CORE},
                case_directories=CASE_LABELS,
                shared_good_driver=str(cls.h.drivers['good']),
                real_dong_mutants=sorted(k for k in cls.h.drivers if k!='good'),
                cases=[c for r in cls.runners for c in r.cases],
                gaps=[c for r in cls.runners for c in r.gaps],
                commands=[c for r in cls.runners for c in r.records],L3_complete=False))
        finally:methods.NativeMethodTests.tearDownClass.__func__(cls)

def make_test(tag,case_type,name):
    def test(self):
        case=case_type(name);case.h=self.h
        label=tag+'.'+name;case_id=tag[0]+hashlib.sha256(label.encode()).hexdigest()[:7]
        self.assertEqual(CASE_LABELS[case_id],label)
        case.runner=g5.Runner(self.h.work/'c'/case_id)
        case.runner.g,case.runner.nasm,case.runner.cc=self.h,self.h.nasm,self.h.cc
        self.runners.append(case.runner)
        getattr(case,name)()
        case.runner.assert_inputs()
        self.executed.append(tag+'.'+name)
    return test

for tag,module,case_type in CORE:
    for name in unittest.defaultTestLoader.getTestCaseNames(case_type):
        setattr(ControlIntegrationTests,'test_'+tag+'__'+name,make_test(tag,case_type,name))
del tag,module,case_type,name

if __name__=='__main__':unittest.main()
