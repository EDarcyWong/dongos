"""L3FOR1 candidate: actual native for/bool-match lowering and execution."""
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
CAND=WORKS/'codex-works/l3-for/src/bootstrap/lower_program.dg'
SOURCE='''module iterate;
pub var trace:u64=0;pub var data:[3]u64=[1,2,3];
struct Item{x:u64,y:u64}
fn lo()u64{trace=trace*10+1;return 1;}
fn hi()u64{trace=trace*10+2;return 4;}
fn id(x:u64)u64{return x;}
fn source()[]u64{trace+=1;return data[..];}
fn decide(x:u64)bool{trace+=1;return x==7;}
pub fn ranged()u64{trace=0;var n:u64=0;for i in lo()..hi(){n+=id(i);}return n;}
pub fn edge(a:u64,b:u64)u64{var n:u64=0;for i in a..b{n=wrapping_add(n,i);}return n;}
pub fn array()u64{var a:[3]u64=[1,2,3];var n:u64=0;for x in a{if x==1{a[2]=9;}n+=x;}return n;}
pub fn slice()u64{trace=0;data[2]=3;var n:u64=0;for x in source(){if x==1{data[2]=9;}n+=x;}return n;}
pub fn literal()u64{var n:u64=0;for x in [1 as u64,2,3]{n+=id(x);}return n;}
pub fn nested_literal()u64{var n:u64=0;for x in [1 as u64,2]{for y in [3 as u64,4]{n+=id(x*y);}}return n;}
pub fn aggregate()u64{var a:[2]Item=[Item{x:1,y:2},Item{x:3,y:4}];var n:u64=0;for x in a{a[0].x=99;n+=x.x+x.y;}return n;}
pub fn empty()u64{var n:u64=9;for x in data[3..3]{n+=x;}return n;}
pub fn flow(limit:u64)u64{var n:u64=0;for i in 0..limit{if i==1{continue;}for j in 0..limit{if j==3{break;}n=wrapping_add(n,10*i+j);}if i==3{break;}}return n;}
pub fn matched(x:u64)u64{trace=0;var n:u64=0;match decide(x){true=>{let y:u64=1;n=y;},false=>{let z:u64=2;n=z;},}return n+100*trace;}
pub fn wildcard(p:bool)u64{match p{true=>{return 7;},_=>{return 9;},}}
pub fn all(p:bool)u64{match p{_=>{return 11;},}}
'''

def observer(body):
    dec=['#include <stdint.h>','#include <stdio.h>','typedef uint64_t U;',
        '#define ABI __attribute__((sysv_abi))',
        '#define CHECK(x) do{if(!(x)){fputs("for-oracle\\n",stderr);return 17;}}while(0)']
    for name,ret,args in [('ranged','U','void'),('edge','U','U,U'),('array','U','void'),('slice','U','void'),
        ('literal','U','void'),('nested_literal','U','void'),('aggregate','U','void'),('empty','U','void'),
        ('flow','U','U'),('matched','U','U'),('wildcard','U','_Bool'),('all','U','_Bool')]:
        dec.append('extern '+ret+' ABI f_'+name+'('+args+') __asm__("'+bridge.label('iterate',name)+'");')
    dec.append('extern U trace __asm__("'+bridge.label('iterate','trace')+'");')
    return '\n'.join(dec)+'\nint main(void){'+body+'return 0;}'

class ForNativeTests(unittest.TestCase):
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
        bridge.CAND=ROOT/'lang/bootstrap';bridge.BUILD=WORKS/'codex-works/build/L3FOR1'
        bridge.DRIVER=g5.diagnostic_driver().replace('if(rc){REQUIRE(unpublished(&lr));',
            'if(rc){REQUIRE(arena_hash==hash(arena.p,arena.n)&&sources_hash==source_hash(catalog,sources));REQUIRE(unpublished(&lr));')
        bridge.stage_compiler=stage
        try:bridge.L3AGlobalsTests.setUpClass()
        except BaseException:
            bridge.CAND,bridge.BUILD,bridge.DRIVER,bridge.stage_compiler=cls.saved;raise
        cls.h=bridge.L3AGlobalsTests();cls.h.inputs[str(Path(__file__))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        cls.runner=g5.Runner(cls.h.work/'differential');cls.runner.g,cls.runner.nasm,cls.runner.cc=cls.h,cls.h.nasm,cls.h.cc
    @classmethod
    def tearDownClass(cls):
        try:
            cls.runner.assert_inputs()
            g5.write(cls.runner.work/'for.json',dict(cases=cls.runner.cases,commands=cls.runner.records,
                production_integrated=False,L3_complete=False))
            cls.h.tearDownClass()
        finally:bridge.CAND,bridge.BUILD,bridge.DRIVER,bridge.stage_compiler=cls.saved
    differential=methods.NativeMethodTests.differential

    def test_range_snapshot_order_zero_reverse_and_u64_edge(self):
        self.differential('range',[('iterate.dg',SOURCE)],observer(
            'CHECK(f_ranged()==6&&trace==12);CHECK(f_edge(0,0)==0&&f_edge(9,3)==0);'
            'CHECK(f_edge(UINT64_MAX-2,UINT64_MAX)==UINT64_MAX-4);'))
    def test_array_and_slice_view_observe_original_storage(self):
        self.differential('views',[('iterate.dg',SOURCE)],observer(
            'CHECK(f_array()==12);CHECK(f_slice()==12&&trace==1);CHECK(f_empty()==9);'))
    def test_array_temporary_lifetime_and_aggregate_element_snapshot(self):
        self.differential('temporaries',[('iterate.dg',SOURCE)],observer(
            'CHECK(f_literal()==6&&f_nested_literal()==21&&f_aggregate()==10);'))
    def test_nested_break_continue_targets(self):
        body='for(U limit=0;limit<8;limit++){U sum=0;for(U i=0;i<limit;i++){if(i==1){continue;}'
        body+='for(U j=0;j<limit;j++){if(j==3){break;}sum+=10*i+j;}if(i==3){break;}}CHECK(f_flow(limit)==sum);}'
        self.differential('flow',[('iterate.dg',SOURCE)],observer(body))
    def test_bool_match_once_exhaustive_and_wildcard_returns(self):
        self.differential('match',[('iterate.dg',SOURCE)],observer(
            'CHECK(f_matched(7)==101&&trace==1);CHECK(f_matched(8)==102&&trace==1);'
            'CHECK(f_wildcard(1)==7&&f_wildcard(0)==9&&f_all(1)==11&&f_all(0)==11);'))
    def test_existing_methods_and_sysv_remain_executable(self):
        check=methods.NativeMethodTests();check.h,check.runner=self.h,self.runner
        check.test_selected_declaration_and_both_call_forms();check.test_bodyless_method_link_names_and_explicit_definition_alias()
    def test_real_dong_wrong_increment_is_rejected_by_value_oracle(self):
        old='emit(s,ir.CONSTANT,3,one,0,0,1,0,id);'
        bad='emit(s,ir.CONSTANT,3,one,0,0,2,0,id);'
        self.h.build_driver('bad-increment',{'lower_program.dg':(old,bad)})
        directory=self.runner.source_directory('bad-increment',[('iterate.dg',SOURCE)])
        obs=observer('CHECK(f_ranged()==6&&trace==12);')
        for mode in ('debug','release'):
            self.runner.observe(self.runner.seed(directory,mode),obs,'bad-increment-seed-'+mode)
            asm,result=self.runner.dong(directory,mode,'bad-increment');self.assertEqual(result.returncode,0,result.stderr)
            target=self.runner.observe(asm,obs,'bad-increment-dong-'+mode,expect=17)
            self.assertIn('for-oracle',target['stderr'])
            self.runner.cases.append(dict(name='bad-increment',mode=mode,status='negative-rejected',native=target))

if __name__=='__main__':unittest.main()
