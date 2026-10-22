"""Mainline for/bool match: actual native for/bool-match lowering and execution."""
from __future__ import annotations
import hashlib
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
from lang.tests import test_l3a_globals as bridge
from lang.tests import test_l3_method_native as methods
from tools import g5_differential as g5
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

COMPOSED='''module control;
pub var trace:u64=0;
fn push(n:u64)void{trace=trace*10+n;}
pub fn loops(n:u64)u64{trace=0;defer push(9);var sum:u64=0;
 for i in 1..n{defer push(i);if i==2{continue;}match i==4{true=>{break;},false=>{sum+=i;},}}return sum;
}
pub fn pair(s:[]u8)[]u8{trace=0;defer{for z in [1 as u64,2,3]{push(z);}}return s[1..3];}
pub fn early(s:[]u8)[]u8{trace=0;defer push(8);
 for i in [1 as u64,2,3]{defer push(i);match i==2{true=>{return s;},_=>{},}}return s[0..0];
}
'''

ELF_ENTRY='''module entry;
pub var total:u64=0;
fn add(n:u64)void{total+=n;}
fn compute()u64{total=0;defer add(3);for i in 1..4{defer add(i);match i==2{true=>{continue;},_=>{},}}return total;}
pub fn f()u64{let x=compute();return 10*x+total;}
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
        cls.saved=bridge.CAND,bridge.BUILD,bridge.DRIVER
        bridge.CAND=ROOT/'lang/bootstrap'
        bridge.BUILD=ROOT/'build/test/l3-for-native'
        bridge.DRIVER=g5.diagnostic_driver().replace('if(rc){REQUIRE(unpublished(&lr));',
            'if(rc){REQUIRE(arena_hash==hash(arena.p,arena.n)&&sources_hash==source_hash(catalog,sources));REQUIRE(unpublished(&lr));')
        try:bridge.L3AGlobalsTests.setUpClass()
        except BaseException:
            bridge.CAND,bridge.BUILD,bridge.DRIVER=cls.saved
            raise
        cls.h=bridge.L3AGlobalsTests()
        cls.h.inputs[str(Path(__file__))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        cls.runner=g5.Runner(cls.h.work/'differential')
        cls.runner.g,cls.runner.nasm,cls.runner.cc=cls.h,cls.h.nasm,cls.h.cc
    @classmethod
    def tearDownClass(cls):
        try:
            cls.runner.assert_inputs()
            g5.write(cls.runner.work/'for.json',dict(cases=cls.runner.cases,commands=cls.runner.records,
                mainline=True,L3_complete=False))
            cls.h.tearDownClass()
        finally:bridge.CAND,bridge.BUILD,bridge.DRIVER=cls.saved
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

    def test_for_match_defer_cleanup_composition_and_pair_return(self):
        obs='''#include <stdint.h>
#include <stdio.h>
typedef uint64_t U;typedef struct{void*p;U n;}Slice;
#define ABI __attribute__((sysv_abi))
#define CHECK(x) do{if(!(x)){fputs("control-oracle\\n",stderr);return 17;}}while(0)
'''
        for name,ret,args in [('loops','U','U'),('pair','Slice','Slice'),('early','Slice','Slice')]:
            obs+='extern '+ret+' ABI '+name+'('+args+') __asm__("'+bridge.label('control',name)+'");\n'
        obs+='extern U trace __asm__("'+bridge.label('control','trace')+'");\n'
        obs+='''int main(void){for(U n=0;n<9;n++){U sum=0,t=0;
 for(U i=1;i<n;i++){t=t*10+i;if(i==4){break;}if(i!=2){sum+=i;}}
 CHECK(loops(n)==sum&&trace==t*10+9);}
 unsigned char bytes[5]={1,2,3,4,5};Slice p=pair((Slice){bytes,5});
 CHECK(p.p==bytes+1&&p.n==2&&trace==123);p=early((Slice){bytes+1,3});
 CHECK(p.p==bytes+1&&p.n==3&&trace==128&&bytes[0]==1&&bytes[4]==5);return 0;}
'''
        self.differential('composition',[('control.dg',COMPOSED)],obs)

    def test_native_elf_consumes_actual_lowered_control_flow(self):
        from lang.tests import test_l3_escaped_symbols as escaped
        escaped.EscapedSymbolTests.setUpClass();check=escaped.EscapedSymbolTests()
        try:
            for mode in (0,1):
                _,asm=self.h.generate('good',[('entry.dg',ELF_ENTRY)],'control-native-elf-'+str(mode),mode)
                text=asm.read_text();kind='release' if mode else 'debug';entry=bridge.label('entry','f')
                status,image,result=check.assemble(kind,text,entry=entry)
                self.assertEqual(status,0,(result.line,result.detail));self.assertEqual(image[:4],b'\x7fELF')
                self.assertEqual(check.execute(image),69)
                exact,repeat,_=check.assemble(kind,text,entry=entry,capacity=len(image))
                self.assertEqual(exact,0);self.assertEqual(image,repeat)
                short,unused,_=check.assemble(kind,text,entry=entry,capacity=len(image)-1)
                self.assertEqual(short,2);self.assertEqual(unused,b'')
                target=asm.with_suffix('.native.elf');target.write_bytes(image)
                self.h.records.append(dict(name='native-control-elf',mode=mode,returned=69,
                    source_assembly_sha256=hashlib.sha256(asm.read_bytes()).hexdigest(),
                    native_elf_sha256=hashlib.sha256(image).hexdigest(),path=str(target)))
        finally:escaped.EscapedSymbolTests.tearDownClass()

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
