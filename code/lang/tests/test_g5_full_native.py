"""Cumulative G5 gate: source-built compiler, independent CPU oracles, no skips."""
from __future__ import annotations
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS if (WORKS/'lang').is_dir() else WORKS.parents[1]/'code'
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(Path(__file__).resolve().parent))
HERE=WORKS/'codex-works/g5-full' if Path(__file__).resolve().parent.name=='tests' and 'codex-works' in Path(__file__).parts else ROOT/'lang/tests/g5'
RUNNER=HERE/'g5_differential.py' if HERE.name=='g5-full' else ROOT/'tools/g5_differential.py'
spec=importlib.util.spec_from_file_location('g5_full_runner',RUNNER)
full=importlib.util.module_from_spec(spec);spec.loader.exec_module(full)
from lang.tests import test_g5_tagged_native as tagged
from lang.tests import test_g5_exec_native as execution
from lang.tests import test_g5_alignment_native as alignment
from lang.tests import test_g5_panic_native as panic
from lang.tests import test_l3_method_native as methods
from lang.tests import test_l3_defer_native as defers
from lang.tests import test_l3_for_native as loops
from lang.tests import test_intrinsic_runtime as intrinsics

class FullLanguageNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved_panic_flags=panic.nasm_flags;panic.nasm_flags=full.nasm_flags
        cls.runner=full.Runner()
        cls.runner.boot();cls.h=cls.runner.g
        cls.cases=[];cls.succeeded=set()
        cls.requirements=json.loads((HERE/'requirements.json').read_text())
        for module in (tagged,execution,alignment,panic,methods,defers,loops,intrinsics):
            path=Path(module.__file__);cls.runner.inputs[str(path)]=full.sha(path)
        for path in (Path(__file__),HERE/'requirements.json',ROOT/'lang/spec.md'):
            cls.runner.inputs[str(path)]=full.sha(path)
    def run(self,result=None):
        result=result or self.defaultTestResult()
        fields=('errors','failures','skipped','expectedFailures','unexpectedSuccesses')
        before=tuple(len(getattr(result,k)) for k in fields)
        super().run(result)
        if before==tuple(len(getattr(result,k)) for k in fields):
            type(self).succeeded.add(self._testMethodName)
        return result
    @classmethod
    def tearDownClass(cls):
        required={name for item in cls.requirements['requirements'] for name in item['tests']}
        rows=[dict(id=item['id'],tests=item['tests'],passed=all(name in cls.succeeded for name in item['tests']))
              for item in cls.requirements['requirements']]
        missing=sorted(required-cls.succeeded)
        result=cls.runner.finish()
        panic.nasm_flags=cls.saved_panic_flags
        result.update(scope_complete=not missing and not result['known_gap'] and result['native_container']['passed'],
                      remaining=missing,requirements=rows,successful_tests=sorted(cls.succeeded),
                      extended_runtime_and_diagnostics=cls.cases,
                      failure=missing,skip=[])
        full.write(cls.runner.work/'full-coverage.json',result)
        if missing:raise AssertionError('G5 incomplete tests: '+', '.join(missing))
        cls.assert_complete(result)
    @staticmethod
    def assert_complete(result):
        full.require(result['scope_complete'] and result['source_stable'] and not result['remaining']
            and not result['known_gap'] and not result['failure'] and not result['skip'],'G5 gate incomplete')
    def differential(self,name,sources,observer,tag='good',expected=0):
        name=hashlib.sha256(self._testMethodName.encode()).hexdigest()[:8]+'-'+name
        if isinstance(sources,str):
            return tagged.TaggedNativeTests.differential(self,name,sources,observer,tag,expected)
        return methods.NativeMethodTests.differential(self,name,sources,observer,tag,expected)
    def observe(self,asm,a,b,name):
        result=panic.PanicNativeTests.observe(self,asm,a,b,name)
        binding=self.runner.bindings.get(str(asm))
        if binding:
            self.assertEqual(binding['emitted_sha256'],full.sha(asm))
            self.assertEqual(binding['native_compile_returncode'],0)
            result.update(binding)
        return result
    def test_a_scalar_aggregate_global_module_and_runtime_matrix(self):
        self.runner.supported()
    def test_b_all_previously_missing_language_paths_execute(self):
        self.runner.known_gaps()
        self.assertEqual(self.runner.gaps,[])
    def test_c_module_privacy_diagnostics(self):
        self.runner.diagnostics()
    def test_d_native_elf_with_real_target_runtime_and_static_pointers(self):
        self.runner.native_container()
    def test_e_memory_all_widths_side_effect_order_and_four_thread_atomic_contention(self):
        source=intrinsics.dong_source()
        directory=self.runner.source_directory('intrinsic-full',[('intrinsic_runtime.dg',source)])
        c=directory/'observer.c';c.write_text(intrinsics.c_source())
        stub=directory/'observer.asm';stub.write_text(intrinsics.OBSERVER)
        stub_obj=stub.with_suffix('.obj')
        self.runner.command([self.h.nasm,'-O0','-f','win64',*full.nasm_flags(self.h.nasm),stub,'-o',stub_obj],'intrinsic-observer')
        for mode in ('debug','release'):
            seed=self.runner.seed(directory,mode)
            native,p=self.runner.dong(directory,mode)
            self.assertEqual(p.returncode,0,p.stderr)
            records=[]
            for label,asm in [('seed',seed),('dong',native)]:
                for fmt,suffix in [('elf64','.o'),('win64','.obj')]:
                    self.runner.command([self.h.nasm,'-O0','-f',fmt,*full.nasm_flags(self.h.nasm),asm,'-o',asm.with_suffix(suffix)],'intrinsic-'+label+'-'+fmt+'-'+mode)
                exe=directory/(label+'-'+mode+'.exe')
                self.runner.command([self.h.cc,'-std=c11','-O0','-fno-omit-frame-pointer','-Wall','-Wextra','-Werror',c,asm.with_suffix('.obj'),stub_obj,'-o',exe],'intrinsic-'+label+'-link-'+mode)
                process=self.runner.command([exe],'intrinsic-'+label+'-execute-'+mode)
                self.assertIn('contended atomic intrinsic probes passed',process.stdout)
                record=dict(path='actual-native-execution',returncode=process.returncode,stdout=process.stdout,assembly_sha256=full.sha(asm),exe_sha256=full.sha(exe))
                if label=='dong':record.update(self.runner.bindings[str(asm)])
                records.append(record)
            self.assertEqual(records[0]['stdout'],records[1]['stdout'])
            self.runner.cases.append(dict(name='all-width-memory-and-contention',mode=mode,status='supported-pass',seed=records[0],native=records[1]))
    def test_f_noreturn_cleanup_and_conditional_cleanup_flow(self):
        source='''module tagged;
extern "sysv64" fn stop(n:u64)noreturn;
pub var trace:u64=0;fn push(n:u64)void{trace=trace*10+n;}
pub fn cleanup()u64{defer{unsafe{stop(trace);}}defer push(2);push(1);}
pub fn conditional(b:bool)u64{defer{if b{unsafe{stop(trace);}}}return 19;}
'''
        obs=tagged.observer([('cleanup','U','void'),('conditional','U','_Bool')],
            'CHECK(f_conditional(0)==19);f_cleanup();CHECK(0);')
        helper='void __attribute__((sysv_abi,noreturn)) stop(U n){if(n!=12){fputs("wrong-cleanup-trace\\n",stderr);exit(17);}puts("NORETURN trace=12");exit(86);}\n'
        obs=obs.replace('#include <stdio.h>','#include <stdio.h>\n#include <stdlib.h>')
        obs=obs.replace('int main(void){',helper+'int main(void){')
        directory=self.runner.source_directory('noreturn-cleanup',[('tagged.dg',source)])
        for mode in ('debug','release'):
            seed=self.runner.observe(self.runner.seed(directory,mode),obs,'noreturn-seed-'+mode,expect=86)
            asm,p=self.runner.dong(directory,mode)
            self.assertEqual(p.returncode,0,p.stderr)
            native=self.runner.observe(asm,obs,'noreturn-dong-'+mode,expect=86)
            self.assertEqual(seed['stdout'],'NORETURN trace=12\n')
            self.assertEqual(seed['stdout'],native['stdout'])
            self.cases.append(dict(name='noreturn-cleanup',mode=mode,seed=seed,native=native))
    def test_z_actual_semantic_mutants_and_native_failure_fallback_reject(self):
        self.runner.negative_controls()
    def test_g_default_unsafe_survives_combined_frontend_and_function_types(self):
        cases=[
            ('free','extern "sysv64" fn host()u64;pub fn f()u64{return host();}',False,'E0501'),
            ('method','pub struct S{pub x:u64}extern "sysv64" fn(self:*S)get()u64;pub fn f(p:*S)u64{return p.get();}',False,'E0501'),
            ('pointer-type','extern "sysv64" fn host()u64;pub fn f()void{let p:fn()u64=host;}',False,'E0301'),
            ('free-safe','extern "sysv64" fn host()u64;pub fn f()u64{unsafe{return host();}}',True,None),
            ('bodyful','extern "sysv64" fn host()u64{return 7;}pub fn f()u64{return host();}',True,None),
        ]
        from lang.dongc.model import CompileError
        for name,body,accepted,code in cases:
            directory=self.runner.source_directory('unsafe-'+name,[('tagged.dg','module tagged;'+body)])
            for mode in ('debug','release'):
                if accepted:self.runner.seed(directory,mode)
                else:
                    with self.assertRaises(CompileError) as caught:self.runner.seed(directory,mode)
                    self.assertEqual(caught.exception.code,code)
                asm,p=self.runner.dong(directory,mode)
                self.assertEqual(p.returncode,0 if accepted else 10,p.stderr)
                if not accepted:
                    self.assertIn(code+':',p.stderr);self.assertEqual(asm.read_bytes(),b'unchanged')
                self.cases.append(dict(name='default-unsafe-'+name,mode=mode,accepted=accepted,native=p.stderr))
    def test_z_wrong_panic_category_mutation_is_rejected(self):
        # Keep this mutant fixture free of globals/local addresses/tagged values:
        # the combined bad compiler's other independent mutations cannot fire.
        self.h.build_driver('bad-kind',{'nasm_program.dg':('immediate(s,7,kind);','immediate(s,7,kind^1);')})
        source='module tagged;\nexport("observe_trace")fn trace()u64{return 0;}\nexport("run_case")pub fn f(a:u64,b:u64)u64{\n /*site*/return a/b;\n}\n'
        line=source[:source.index('/*site*/')].count('\n')+1
        directory=self.runner.source_directory('bad-kind',[('tagged.dg',source)])
        for mode in ('debug','release'):
            records=[]
            for tag in ('seed','good','bad-kind'):
                if tag=='seed':asm=self.runner.seed(directory,mode)
                else:
                    asm,p=self.runner.dong(directory,mode,tag)
                    self.assertEqual(p.returncode,0,p.stderr)
                record=self.observe(asm,7,0,'bad-kind-'+tag+'-'+mode)
                self.assertEqual(record['returncode'],85,record)
                self.assertEqual(record['stdout'],'PANIC kind='+('2' if tag=='bad-kind' else '3')+' line='+str(line)+' file=tagged.dg trace=0\n')
                records.append(record)
            self.cases.append(dict(name='bad-kind',mode=mode,status='negative-rejected',records=records))
    def test_h_tagged_pointer_function_bool_and_imported_error_payloads(self):
        source='''module tagged;import dep as dep;
type Callback=fn(u64)u64;fn plus(n:u64)u64{return n+1;}
pub fn get(b:bool)?Callback{if b{return plus;}return null;}
pub fn call(x:?Callback)u64{let f=x orelse return 77;unsafe{return f(9);}}
pub fn boolean(b:bool)?bool{return b;}
pub fn pointer(p:*u64)?*u64{return p;}
pub fn result_pointer(p:*u64)!*u64{return p;}
pub fn bad()!u64{return error.dep.Bad;}
'''
        obs=tagged.observer([('get','Pair','_Bool'),('call','U','Pair'),('boolean','Pair','_Bool'),
            ('pointer','Pair','U*'),('result_pointer','Pair','U*'),('bad','Pair','void')],
            'Pair f=f_get(1),n=f_get(0),a=f_boolean(0),b=f_boolean(1),p=f_pointer(0),r=f_result_pointer(0),e=f_bad();'
            'CHECK(f.tag==1&&f.value!=0&&n.tag==0&&n.value==0&&f_call(f)==10&&f_call(n)==77);'
            'CHECK(a.tag==1&&a.value==0&&b.tag==1&&b.value==1&&p.tag==1&&p.value==0&&r.tag==0&&r.value==0);'
            'CHECK(e.tag==4294967295ULL&&e.value==0);')
        self.differential('payload-kinds',[('tagged.dg',source),('dep.dg','module dep;pub error Bad=4294967295;')],obs)
    def test_i_static_objects_larger_than_frame_budget(self):
        source='''module tagged;
pub const table:[667]u64=[7;667];pub var data:[1024]u64=[3;1024];
pub var selected:*const u64=&table[666];
pub fn read(i:usize)u64{return table[i];}
pub fn change(i:usize)u64{data[i]=11;return data[i];}
pub fn pointer()u64{unsafe{return *selected;}}
'''
        self.differential('large-static',source,tagged.observer([('read','U','U'),('change','U','U'),('pointer','U','void')],
            'CHECK(f_read(0)==7&&f_read(666)==7&&f_change(1023)==11&&f_pointer()==7);'))
    def test_j_imported_constant_enum_preserves_tag_and_payload(self):
        source='''module tagged;import dep as dep;
pub var copied:dep.E=dep.original;
pub var plain:dep.E=dep.empty;
pub fn f()u64{match copied{dep.E.A=>{return 0;},dep.E.B(v)=>{return v;},}}
pub fn a()u64{match plain{dep.E.A=>{return 7;},dep.E.B(v)=>{return v;},}}
'''
        dep='module dep;pub enum E{A,B(u64)}pub const original:E=E.B(19);pub const empty:E=E.A;'
        self.differential('import-enum',[('tagged.dg',source),('dep.dg',dep)],
            tagged.observer([('f','U','void'),('a','U','void')],'CHECK(f_f()==19&&f_a()==7);'))
    def test_k_const_pointer_conversion_before_tagged_wrap(self):
        source='''module tagged;
pub fn optional(p:*u64)?*const u64{return p;}
pub fn result(p:*u64)!*const u64{return p;}
'''
        self.differential('wrap-const-pointer',source,
            tagged.observer([('optional','Pair','U*'),('result','Pair','U*')],
                'U value=37;Pair a=f_optional(&value),b=f_result(&value);'
                'CHECK(a.tag==1&&a.value==(U)(uintptr_t)&value&&b.tag==0&&b.value==(U)(uintptr_t)&value);'
                'a=f_optional(0);b=f_result(0);CHECK(a.tag==1&&a.value==0&&b.tag==0&&b.value==0);'))
    def test_l_known_error_try_is_a_terminating_path(self):
        source='''module tagged;error Bad=1;
pub fn f()!u64{const x:!u64=error.Bad;let value=try x;}
'''
        self.differential('known-error-try',source,
            tagged.observer([('f','Pair','void')],'Pair x=f_f();CHECK(x.tag==1&&x.value==0);'))
    def test_m_huge_local_capacity_rejects_without_output(self):
        source='module tagged;pub fn f(x:u64)void{var a:[1152921504606846975]u64;}'
        directory=self.runner.source_directory('huge-local',[('tagged.dg',source)])
        from lang.dongc.model import CompileError
        for mode in ('debug','release'):
            with self.assertRaises(CompileError) as caught:self.runner.seed(directory,mode)
            self.assertEqual(caught.exception.code,'E0601')
            asm,p=self.runner.dong(directory,mode)
            self.assertEqual(p.returncode,11,p.stderr)
            self.assertIn('lower status=4',p.stderr)
            self.assertEqual(asm.read_bytes(),b'unchanged')

# Reuse the independent, already-reviewed oracles against this final compiler,
# not their original candidate compilers or their old pass receipts.
for cls in (tagged.TaggedNativeTests,execution.ExecutionNativeTests,alignment.AlignmentNativeTests,panic.PanicNativeTests):
    for name,value in vars(cls).items():
        if name.startswith('test_'):
            if name=='test_z_wrong_panic_category_mutation_is_rejected':continue
            assert not hasattr(FullLanguageNativeTests,name),name
            setattr(FullLanguageNativeTests,name,value)
for cls,names in [
    (methods.NativeMethodTests,('test_selected_declaration_and_both_call_forms','test_free_function_and_same_name_methods_do_not_collide',
      'test_receiver_once_before_nested_arguments_and_stack','test_pointer_alias_const_unsafe_narrow_void_recursive_and_slice_pair',
      'test_cross_module_public_method_and_nominal_alias','test_bodyless_method_link_names_and_explicit_definition_alias')),
    (defers.DeferNativeTests,('test_lexical_reverse_registration_late_reads_and_cleanup_locals',
      'test_return_scalar_void_pointer_and_pair_survive_cleanup','test_break_continue_and_nested_loop_exit_scope','test_defer_after_return_does_not_run')),
    (loops.ForNativeTests if hasattr(loops,'ForNativeTests') else loops.ForMatchNativeTests,(
      'test_range_snapshot_order_zero_reverse_and_u64_edge','test_array_and_slice_view_observe_original_storage',
      'test_array_temporary_lifetime_and_aggregate_element_snapshot','test_nested_break_continue_targets',
      'test_bool_match_once_exhaustive_and_wildcard_returns','test_for_match_defer_cleanup_composition_and_pair_return')),
]:
    for name in names:setattr(FullLanguageNativeTests,name,getattr(cls,name))
del cls,names,name,value

if __name__=='__main__':unittest.main()
