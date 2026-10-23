"""Dynamic native frames checked by actual addresses, calls and CPU execution."""
from __future__ import annotations
import hashlib
from pathlib import Path
import sys
import unittest
WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS if (WORKS/'lang').is_dir() else WORKS.parents[1]/'code'
sys.path.insert(0,str(ROOT))
from lang.tests import test_l3a_globals as bridge
from tools import g5_differential as g5
from lang.tests import test_g5_tagged_native as tagged

SOURCE='''module tagged;
align(64) struct A{x:u64,y:?u64}
align(1024) struct Big{value:u64}
fn sum(a:u64,b:u64,c:u64,d:u64,e:u64,f:u64,g:u64,h:u64)u64{return a+b+c+d+e+f+g+h;}
pub fn f(a:u64,b:u64,c:u64,d:u64,e:u64,f:u64,g:u64,h:u64)u64{
 var x:A=A{x:11,y:19};var y:A=x;y.x=13;
 unsafe{if ((&x as usize)&63)!=0||((&y as usize)&63)!=0{return 9001;}}
 return sum(a,b,c,d,e,f,g,h)+x.x+y.x+(y.y orelse 0);
}
pub fn big()u64{var x:Big=Big{value:17};unsafe{if ((&x as usize)&1023)!=0{return 9002;}}return x.value;}
pub extern "win64" fn callback(a:u64,b:u64,c:u64,d:u64,e:u64,f:u64,g:u64,h:u64)u64{
 var x:A=A{x:23,y:null};unsafe{if ((&x as usize)&63)!=0{return 9003;}}return sum(a,b,c,d,e,f,g,h)+x.x;
}
pub fn direct()u64{unsafe{return callback(1,2,3,4,5,6,7,8);}}
'''

class AlignmentNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved=bridge.CAND,bridge.CANDIDATES,bridge.BUILD,bridge.DRIVER
        bridge.CAND=ROOT/'lang/bootstrap'
        bridge.CANDIDATES=('semantic_types.dg','program_ir.dg','lower_program.dg','nasm_program.dg')
        bridge.BUILD=ROOT/'build/test/g5-alignment'
        bridge.DRIVER=g5.diagnostic_driver()
        try:bridge.L3AGlobalsTests.setUpClass()
        except BaseException:
            bridge.CAND,bridge.CANDIDATES,bridge.BUILD,bridge.DRIVER=cls.saved
            raise
        cls.h=bridge.L3AGlobalsTests()
        for p in (Path(__file__),Path(tagged.__file__)):
            cls.h.inputs[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        cls.source_before=dict(cls.h.inputs)
        cls.runner=g5.Runner(cls.h.work/'differential')
        cls.runner.g,cls.runner.nasm,cls.runner.cc=cls.h,cls.h.nasm,cls.h.cc
    @classmethod
    def tearDownClass(cls):
        try:
            cls.runner.assert_inputs()
            after={p:g5.sha(p) for p in cls.source_before}
            g5.write(cls.h.work/'frozen-inputs.json',dict(before=cls.source_before,after=after,source_stable=after==cls.source_before))
            g5.require(after==cls.source_before,'frozen candidate or dependency changed')
            g5.write(cls.runner.work/'alignment.json',dict(cases=cls.runner.cases,commands=cls.runner.records,scope_complete=False))
            cls.h.tearDownClass()
        finally:bridge.CAND,bridge.CANDIDATES,bridge.BUILD,bridge.DRIVER=cls.saved
    differential=tagged.TaggedNativeTests.differential
    def test_aligned_objects_copy_stack_parameters_and_nested_calls(self):
        self.differential('aligned',SOURCE,tagged.observer([('f','U','U,U,U,U,U,U,U,U'),('big','U','void')],
            'CHECK(f_f(1,2,3,4,5,6,7,8)==79&&f_big()==17);'))
    def test_win64_bridge_and_realigned_sysv_body_share_budget(self):
        obs=tagged.observer([('callback','U','U,U,U,U,U,U,U,U'),('direct','U','void')],
            'CHECK(f_callback(1,2,3,4,5,6,7,8)==59&&f_direct()==59);')
        obs=obs.replace('ABI f_callback','__attribute__((ms_abi)) f_callback')
        self.differential('win64-aligned',SOURCE,obs)
    def test_oversize_combined_frame_rejects_without_output(self):
        source='module tagged;align(2048) struct A{x:u8}pub fn f()usize{var x:A=A{x:7};unsafe{return (&x as usize)&2047;}}'
        directory=self.runner.source_directory('frame-limit',[('tagged.dg',source)])
        from lang.dongc.model import CompileError
        for mode in ('debug','release'):
            with self.assertRaises(CompileError) as caught:self.runner.seed(directory,mode)
            self.assertEqual(caught.exception.code,'E0601')
            asm,p=self.runner.dong(directory,mode)
            self.assertIn(p.returncode,(11,12),p.stderr)
            self.assertRegex(p.stderr,r'(lower|emit) status=4')
            self.assertEqual(asm.read_bytes(),b'unchanged')
    def test_real_wrong_local_address_is_rejected_after_normal_return(self):
        self.h.build_driver('bad-address',{'nasm_program.dg':(
            'addr.emit(0,(*s).frame_base,-((*x).a as i64)',
            'addr.emit(0,(*s).frame_base,-((*x).a as i64)+8')})
        source='module tagged;align(64)struct A{x:u64}pub fn f()usize{var x:A=A{x:7};unsafe{return (&x as usize)&63;}}'
        self.differential('bad-address',source,tagged.observer([('f','U','void')],'CHECK(f_f()==0);'),tag='bad-address',expected=17)

if __name__=='__main__':unittest.main()
