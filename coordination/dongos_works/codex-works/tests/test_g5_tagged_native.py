"""Actual candidate Dong compiler, separate seed compiler and C CPU oracles."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import unittest

WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS.parents[1]/'code'
sys.path.insert(0,str(ROOT))
from lang.tests import test_l3a_globals as bridge
from tools import g5_differential as g5

SOURCE='''module tagged;
error Bad=7;error Worse=0x1234;
pub var trace:u64=0;
fn mark(n:u64)void{trace=trace*10+n;}
pub fn absent()?u64{return null;}
pub fn present(n:u64)?u64{return n;}
pub fn small(n:i8)?i8{return n;}
pub fn success(n:u64)!u64{return n;}
pub fn failed()!u64{return error.Bad;}
pub fn voided(b:bool)!void{if b{return error.Worse;}return;}
pub fn fallback(b:bool)u64{trace=0;let x:?u64=null;if b{return present(9) orelse 31;}return x orelse alternate();}
fn alternate()u64{mark(8);return 31;}
pub fn propagate(b:bool)!u64{trace=0;defer mark(1);let a=try success(11);if b{defer mark(2);let x=try failed();return x;}return a+1;}
pub fn narrow(n:i8)i8{return small(n) orelse -3;}
pub fn match_optional(x:?u64)u64{match x{null=>{return 19;},some(n)=>{return n+1;},}}
pub fn match_result(x:!u64)u64{match x{ok(n)=>{return n+2;},err(e)=>{return e+3;},}}
pub fn exit_fallback(x:?u64)u64{defer mark(3);let n=x orelse return 71;return n;}
pub fn void_try(b:bool)!void{defer mark(4);try voided(b);return;}
'''

ENUMS='''module tagged;
pub enum E{A,B(i8),C(u64),D}
pub enum Flag{Off,On}
pub fn make(n:u64)E{if n==0{return E.A;}if n==1{return E.B(-7);}return E.C(n);}
pub fn read(e:E)u64{match e{E.A=>{return 11;},E.B(n)=>{return (n+10)as u64;},E.C(n)=>{return n+20;},E.D=>{return 44;},}}
pub fn pass(e:E)E{return e;}
pub fn flag(x:Flag)u64{match x{Flag.Off=>{return 0;},Flag.On=>{return 1;},}}
pub fn f()u64{return read(make(0))+read(make(1))+read(make(5))+flag(Flag.On);}
'''

def observer(decls,body):
    prefix='#include <stdint.h>\n#include <stdio.h>\n#include <string.h>\ntypedef uint64_t U;typedef struct{U tag,value;}Pair;\n#define ABI __attribute__((sysv_abi))\n#define CHECK(x) do{if(!(x)){fprintf(stderr,"tagged-oracle line %d\\n",__LINE__);return 17;}}while(0)\n'
    for name,ret,args in decls:
        prefix+='extern '+ret+' ABI f_'+name+'('+args+') __asm__("'+bridge.label('tagged',name)+'");\n'
    prefix+='extern U trace __asm__("'+bridge.label('tagged','trace')+'");\n' if 'trace' in body else ''
    return prefix+'int main(void){'+body+'return 0;}'

class TaggedNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved=bridge.CAND,bridge.CANDIDATES,bridge.BUILD,bridge.DRIVER
        bridge.CAND=WORKS/'codex-works/g5-tag/src/bootstrap'
        bridge.CANDIDATES=('semantic_types.dg','program_ir.dg','lower_program.dg','nasm_program.dg')
        bridge.BUILD=ROOT/'build/test/g5-tag'
        bridge.DRIVER=g5.diagnostic_driver()
        try:bridge.L3AGlobalsTests.setUpClass()
        except BaseException:
            bridge.CAND,bridge.CANDIDATES,bridge.BUILD,bridge.DRIVER=cls.saved
            raise
        cls.h=bridge.L3AGlobalsTests()
        cls.h.inputs[str(Path(__file__))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
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
            g5.write(cls.runner.work/'tagged.json',dict(cases=cls.runner.cases,diagnostics=cls.runner.diagnostic_cases,commands=cls.runner.records,scope_complete=False))
            cls.h.tearDownClass()
        finally:bridge.CAND,bridge.CANDIDATES,bridge.BUILD,bridge.DRIVER=cls.saved
    def differential(self,name,source,obs,tag='good',expected=0):
        directory=self.runner.source_directory(name,[('tagged.dg',source)])
        for mode in ('debug','release'):
            seed=self.runner.observe(self.runner.seed(directory,mode),obs,name+'-seed-'+mode)
            asm,result=self.runner.dong(directory,mode,tag)
            self.assertEqual(result.returncode,0,result.stderr)
            native=self.runner.observe(asm,obs,name+'-dong-'+mode,expect=expected)
            if expected:self.assertIn('tagged-oracle',native['stderr'])
            else:self.assertEqual((seed['stdout'],seed['returncode']),(native['stdout'],native['returncode']))
            self.runner.cases.append(dict(name=name,mode=mode,seed=seed,native=native,status='negative-rejected' if expected else 'supported-pass'))
    def test_optional_result_abi_bytes_and_narrow_payload(self):
        self.differential('pairs',SOURCE,observer([
            ('absent','Pair','void'),('present','Pair','U'),('small','Pair','int8_t'),
            ('success','Pair','U'),('failed','Pair','void'),('voided','Pair','_Bool'),('narrow','int8_t','int8_t')],
            'Pair a=f_absent(),b=f_present(0x123456789abcdef0ULL),c=f_small(-7),d=f_success(99),e=f_failed(),v=f_voided(0),w=f_voided(1);'
            'CHECK(a.tag==0&&a.value==0&&b.tag==1&&b.value==0x123456789abcdef0ULL);'
            'CHECK(c.tag==1&&c.value==249&&d.tag==0&&d.value==99&&e.tag==7&&e.value==0);'
            'CHECK(v.tag==0&&v.value==0&&w.tag==0x1234&&w.value==0&&f_narrow(-101)==-101);'))
    def test_try_defer_orelse_short_circuit_and_exit(self):
        self.differential('flow',SOURCE,observer([
            ('fallback','U','_Bool'),('propagate','Pair','_Bool'),('exit_fallback','U','Pair'),('void_try','Pair','_Bool')],
            'CHECK(f_fallback(1)==9&&trace==0);CHECK(f_fallback(0)==31&&trace==8);'
            'Pair a=f_propagate(0);CHECK(a.tag==0&&a.value==12&&trace==1);'
            'Pair b=f_propagate(1);CHECK(b.tag==7&&b.value==0&&trace==21);'
            'trace=0;CHECK(f_exit_fallback((Pair){0,0})==71&&trace==3);'
            'trace=0;CHECK(f_exit_fallback((Pair){1,55})==55&&trace==3);'
            'trace=0;Pair c=f_void_try(1);CHECK(c.tag==0x1234&&c.value==0&&trace==4);'))
    def test_match_optional_and_error_payload(self):
        self.differential('match',SOURCE,observer([
            ('match_optional','U','Pair'),('match_result','U','Pair')],
            'CHECK(f_match_optional((Pair){0,0})==19&&f_match_optional((Pair){1,80})==81);'
            'CHECK(f_match_result((Pair){0,90})==92&&f_match_result((Pair){1234,0})==1237);'))
    def test_enum_nominal_tag_payload_and_scalar(self):
        self.differential('enum',ENUMS,observer([('f','U','void'),('pass','Pair','Pair'),('read','U','Pair')],
            'CHECK(f_f()==40);Pair p=f_pass((Pair){2,0xfedcba9876543210ULL});'
            'CHECK(p.tag==2&&p.value==0xfedcba9876543210ULL&&f_read((Pair){3,0})==44);'))
    def test_static_tagged_aggregate_padding_and_array_elements(self):
        source='''module tagged;error Bad=17;
pub struct Holder{pub before:u8,pub opt:?i8,pub res:!u16,pub last:u8}
pub var h:Holder=Holder{before:0xa7,opt:-7,res:511,last:0x5a};
pub enum E{A,B(i8)}pub var a:?i8=-7;pub const b:!u64=99;
pub var c:!u64=error.Bad;pub const e:E=E.B(-7);
pub fn f()u64{let values:[2]?u64=[7,null];let n=values[0] orelse 0;let m=values[1] orelse 19;
 match a{null=>{return 0;},some(x)=>{match e{E.A=>{return 0;},E.B(v)=>{if x!=v{return 0;}}}}}
 match b{ok(x)=>{match c{ok(v)=>{return 0;},err(code)=>{return x+code+n+m;},}},err(x)=>{return 0;},}}
'''
        obs=observer([('f','U','void')],
            'CHECK(f_f()==142);unsigned char expected[48]={0};expected[0]=0xa7;expected[8]=1;'
            'expected[16]=249;expected[32]=255;expected[33]=1;expected[40]=0x5a;CHECK(!memcmp(h,expected,48));')
        obs=obs.replace('int main(void){','extern unsigned char h[] __asm__("'+bridge.label('tagged','h')+'");\nint main(void){')
        self.differential('statics',source,obs)
    def test_pair_rolls_wholly_to_stack_without_consuming_last_scalar_register(self):
        source='''module tagged;
pub fn combine(a:u64,b:u64,c:u64,d:u64,e:u64,p:?u64,z:u64)?u64{
 if a+2*b+3*c+4*d+5*e+6*z!=97{return null;}return p;}
pub fn f()u64{let p:?u64=77;let q=combine(1,2,3,4,5,p,7);return q orelse 0;}
'''
        self.differential('pair-stack',source,observer([('combine','Pair','U,U,U,U,U,Pair,U'),('f','U','void')],
            'CHECK(f_f()==77);Pair p=f_combine(1,2,3,4,5,(Pair){1,0x8877665544332211ULL},7);'
            'CHECK(p.tag==1&&p.value==0x8877665544332211ULL);'))
    def test_known_match_subject_excludes_dead_arms_from_initialization_merge(self):
        source='''module tagged;enum E{A,B,C}
pub fn known_enum()u64{var out:u64;match E.C{E.A=>{},E.B=>{},E.C=>{out=7;},}return out;}
pub fn known_optional()u64{var out:u64;const x:?u64=7;match x{some(n)=>{out=n;},_=>{}}return out;}
pub fn known_bool()u64{var out:u64;match true{true=>{out=7;},_=>{}}return out;}
error Bad=11;pub fn known_error()u64{var out:u64;const e:!u64=error.Bad;
 match e{ok(n)=>{},err(code)=>{out=code;},}return out;}
'''
        self.differential('known-match',source,observer([
            ('known_enum','U','void'),('known_optional','U','void'),('known_bool','U','void'),('known_error','U','void')],
            'CHECK(f_known_enum()==7&&f_known_optional()==7&&f_known_bool()==7&&f_known_error()==11);'))
    def test_invalid_tagged_sources_reject_before_publishing(self):
        cases={
            'error-zero':('error Bad=0;fn f()u64{return 1;}','E0302'),
            'error-large':('error Bad=4294967296;fn f()u64{return 1;}','E0302'),
            'error-duplicate':('error A=7;error B=7;fn f()u64{return 1;}','E0602'),
            'enum-missing':('enum E{A,B(u64)}fn f(e:E)u64{match e{E.A=>{return 0;},}}','E0403'),
            'enum-duplicate':('enum E{A,B(u64)}fn f(e:E)u64{match e{E.A=>{return 0;},E.A=>{return 1;},E.B(n)=>{return n;},}}','E0403'),
            'enum-other':('enum E{A}enum F{A}fn f(e:E)u64{match e{F.A=>{return 0;},}}','E0301'),
            'enum-payload':('enum E{A,B(u64)}fn f()E{return E.B;}','E0301'),
            'enum-extra':('enum E{A}fn f()E{return E.A(1);}','E0301'),
            'enum-bind':('enum E{A,B(u64)}fn f(e:E)u64{match e{E.A=>{return 1;},E.B=>{return 0;},}}','E0301'),
            'optional-wrong':('fn f(x:?u64)u64{return x orelse false;}','E0301'),
            'result-discard':('fn g()!u64{return 7;}fn f()void{g();}','E0301'),
            'defer-try':('fn g()!u64{return 7;}fn f()!u64{defer{let n=try g();}return 8;}','E0501'),
            'error-optional':('error Bad=7;fn f()?u64{return error.Bad;}','E0301'),
            'error-inferred':('error Bad=7;fn f()!u64{let e=error.Bad;return e;}','E0301'),
        }
        from lang.dongc.model import CompileError
        import re
        for name,(source,code) in cases.items():
            directory=self.runner.source_directory(name,[('tagged.dg','module tagged;'+source)])
            for mode in ('debug','release'):
                with self.assertRaises(CompileError) as caught:self.runner.seed(directory,mode)
                self.assertEqual(caught.exception.code,code)
                asm,p=self.runner.dong(directory,mode)
                self.assertEqual(p.returncode,10,p.stderr)
                self.assertEqual(asm.read_bytes(),b'unchanged')
                location=re.search(r'source=(\d+) offset=(\d+)',p.stderr)
                self.assertIsNotNone(location,p.stderr)
                self.assertEqual(int(location[1]),0)
                self.assertLess(int(location[2]),len(('module tagged;'+source).encode()))
                self.runner.diagnostic_cases.append(dict(name=name,mode=mode,seed_code=code,native=p.stderr,output_unchanged=True))
    def test_real_dong_wrong_optional_tag_is_rejected_after_normal_execution(self):
        self.h.build_driver('bad-tag',{'nasm_program.dg':(
            'else{immediate(s,0,(*x).value);}', 'else{immediate(s,0,(*x).value^1);}')})
        self.differential('bad-tag','module tagged;pub fn absent()?u64{return null;}',
            observer([('absent','Pair','void')],'Pair p=f_absent();CHECK(p.tag==0&&p.value==0);'),tag='bad-tag',expected=17)

if __name__=='__main__':unittest.main()
