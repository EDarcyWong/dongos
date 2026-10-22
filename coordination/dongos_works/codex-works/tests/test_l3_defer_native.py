"""L3DEFER1 candidate: real Dong lowering, independent seed/C observations."""
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
import unittest

WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS
if not (ROOT/'lang').is_dir():
    root=Path(json.loads((WORKS/'project.json').read_text(encoding='utf-8'))['source_root'])
    ROOT=root if root.is_absolute() else (WORKS/root).resolve()
sys.path.insert(0,str(ROOT))
from lang.tests import test_l3a_globals as bridge
from lang.tests import test_l3_method_native as methods
from tools import g5_differential as g5

CAND=WORKS/'codex-works/l3-defer/src/bootstrap/lower_program.dg'
SOURCE='''module clean;
pub var trace:u64=0;pub var state:u64=0;
fn push(n:u64)void{trace=trace*10+n;state+=1;}
fn noise(x:u64)u64{push(9);return x*3+11;}
pub fn normal()u64{trace=0;if true{defer push(1);defer push(2);push(3);}return trace;}
pub fn local()void{trace=0;defer{var n:u64=6;n+=1;push(n);}return;}
pub fn late()void{trace=0;var n:u64=1;defer push(n);n=8;}
pub fn branch(yes:bool)u64{trace=0;if yes{defer push(1);push(2);}else{defer push(3);push(4);}push(5);return trace;}
pub fn early()u64{trace=0;state=41;defer push(1);if true{defer push(2);return state;}return 99;}
pub fn pair(s:[]u8)[]u8{trace=0;defer noise(47);return s;}
pub fn pointer(p:*u8)*u8{trace=0;defer push(8);return p;}
pub fn voided()void{trace=0;defer push(4);return;}
pub fn looped()u64{trace=0;defer push(9);var i:u64=0;while i<3{
 i+=1;defer push(i);if i==1{continue;}if i==2{break;}
}push(8);return trace;}
pub fn nested()u64{trace=0;defer push(1);loop{defer push(2);loop{defer push(3);break;}push(4);break;}return trace;}
pub fn unregistered()u64{trace=0;defer push(1);return 7;defer push(2);}
'''

def observer(body):
    declarations=['#include <stdint.h>','#include <stdio.h>',
        'typedef uint64_t U;typedef struct{void*p;U n;}Slice;',
        '#define ABI __attribute__((sysv_abi))',
        '#define CHECK(x) do{if(!(x)){fputs("defer-oracle\\n",stderr);return 17;}}while(0)']
    for name,ret,args in [('normal','U','void'),('local','void','void'),('late','void','void'),
        ('branch','U','_Bool'),('early','U','void'),('pair','Slice','Slice'),('pointer','void*','void*'),
        ('voided','void','void'),('looped','U','void'),('nested','U','void'),('unregistered','U','void')]:
        declarations.append('extern '+ret+' ABI f_'+name+'('+args+') __asm__("'+bridge.label('clean',name)+'");')
    for name in ('trace','state'):
        declarations.append('extern U '+name+' __asm__("'+bridge.label('clean',name)+'");')
    return '\n'.join(declarations)+'\nint main(void){'+body+'return 0;}'


class DeferNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved=bridge.CAND,bridge.BUILD,bridge.DRIVER,bridge.stage_compiler
        original=bridge.stage_compiler
        def stage(work,wrapper=bridge.WRAPPER,mutations=None,extra=('exec.elf',)):
            directory,provenance=original(work,wrapper,mutations=None,extra=extra)
            data=CAND.read_bytes()
            if mutations:
                if set(mutations)!={'lower_program.dg'}:raise AssertionError('only candidate lower mutation is allowed')
                old,new=mutations['lower_program.dg'];text=data.decode('utf-8')
                if text.count(old)!=1:raise AssertionError('mutation boundary not unique')
                data=text.replace(old,new).encode('utf-8')
            rel='bootstrap/lower_program.dg';(directory/rel).write_bytes(data)
            provenance[rel]=dict(origin=str(CAND),sha256=hashlib.sha256(data).hexdigest(),candidate=True)
            return directory,provenance
        bridge.CAND=ROOT/'lang/bootstrap'
        bridge.BUILD=WORKS/'codex-works/build/L3DEFER1'
        bridge.DRIVER=g5.diagnostic_driver().replace('if(rc){REQUIRE(unpublished(&lr));',
            'if(rc){REQUIRE(arena_hash==hash(arena.p,arena.n)&&sources_hash==source_hash(catalog,sources));REQUIRE(unpublished(&lr));')
        bridge.stage_compiler=stage
        try:bridge.L3AGlobalsTests.setUpClass()
        except BaseException:
            bridge.CAND,bridge.BUILD,bridge.DRIVER,bridge.stage_compiler=cls.saved
            raise
        cls.h=bridge.L3AGlobalsTests()
        cls.h.inputs[str(Path(__file__))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        cls.runner=g5.Runner(cls.h.work/'differential')
        cls.runner.g,cls.runner.nasm,cls.runner.cc=cls.h,cls.h.nasm,cls.h.cc

    @classmethod
    def tearDownClass(cls):
        try:
            cls.runner.assert_inputs()
            g5.write(cls.runner.work/'defer.json',dict(cases=cls.runner.cases,commands=cls.runner.records,
                production_integrated=False,L3_complete=False))
            cls.h.tearDownClass()
        finally:bridge.CAND,bridge.BUILD,bridge.DRIVER,bridge.stage_compiler=cls.saved

    differential=methods.NativeMethodTests.differential

    def test_lexical_reverse_registration_late_reads_and_cleanup_locals(self):
        self.differential('lexical',[('clean.dg',SOURCE)],observer(
            'CHECK(f_normal()==321&&trace==321);f_local();CHECK(trace==7);f_late();CHECK(trace==8);'
            'CHECK(f_branch(1)==215&&trace==215);CHECK(f_branch(0)==435&&trace==435);'))

    def test_return_scalar_void_pointer_and_pair_survive_cleanup(self):
        self.differential('returns',[('clean.dg',SOURCE)],observer(
            'CHECK(f_early()==41&&state==43&&trace==21);'
            'unsigned char bytes[5]={1,2,3,4,5};Slice p=f_pair((Slice){bytes+1,3});'
            'CHECK(p.p==bytes+1&&p.n==3&&trace==9&&bytes[0]==1&&bytes[4]==5);'
            'CHECK(f_pointer(bytes+2)==bytes+2&&trace==8);f_voided();CHECK(trace==4);'))

    def test_break_continue_and_nested_loop_exit_scope(self):
        self.differential('loops',[('clean.dg',SOURCE)],observer(
            'CHECK(f_looped()==128&&trace==1289);CHECK(f_nested()==342&&trace==3421);'))

    def test_defer_after_return_does_not_run(self):
        self.differential('unregistered',[('clean.dg',SOURCE)],observer(
            'CHECK(f_unregistered()==7&&trace==1);'))

    def test_method_and_sysv_paths_remain_executable(self):
        check=methods.NativeMethodTests()
        check.h,check.runner=self.h,self.runner
        check.test_selected_declaration_and_both_call_forms()
        check.test_receiver_once_before_nested_arguments_and_stack()
        check.test_pointer_alias_const_unsafe_narrow_void_recursive_and_slice_pair()
        check.test_bodyless_method_link_names_and_explicit_definition_alias()

    def test_real_dong_skipped_return_cleanup_is_rejected_by_value_oracle(self):
        old='(*s).locals=(*s).cursor;cleanups(s,NONE,depth+1);(*s).locals=locals;'
        bad='(*s).locals=(*s).cursor;(*s).locals=locals;'
        self.h.build_driver('bad-return',{'lower_program.dg':(old,bad)})
        # Use the same C/seed differential procedure but the negative marker
        # reflects the independent cleanup oracle, not a compilation failure.
        directory=self.runner.source_directory('bad-return',[('clean.dg',SOURCE)])
        obs=observer('CHECK(f_early()==41&&state==43&&trace==21);')
        for mode in ('debug','release'):
            self.runner.observe(self.runner.seed(directory,mode),obs,'bad-return-seed-'+mode)
            asm,result=self.runner.dong(directory,mode,'bad-return')
            self.assertEqual(result.returncode,0,result.stderr)
            target=self.runner.observe(asm,obs,'bad-return-dong-'+mode,expect=17)
            self.assertIn('defer-oracle',target['stderr'])
            self.runner.cases.append(dict(name='bad-return',mode=mode,status='negative-rejected',native=target))


if __name__=='__main__':unittest.main()
