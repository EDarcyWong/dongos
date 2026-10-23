"""Actual legacy contracts against one newly source-built mainline compiler.

The full 51-case and closure gates are separate coordinator checks. This gate
adds old API/ELF oracles without reusing any earlier run's compiler cache.
"""
from pathlib import Path
import hashlib
import sys
import unittest
WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS if (WORKS/'lang').is_dir() else WORKS.parents[1]/'code'
sys.path.insert(0,str(ROOT))
from tools import g5_differential as g5
from lang.tests import test_bootstrap_semantic_runtime as semantic
from lang.tests import test_bootstrap_guest_compile_image as guest
from lang.tests import test_g5_runner_entry as entry
from lang.tests import test_l3_method_native as methods
from lang.tests import test_l3_sysv_native as sysv
from lang.tests import test_l3a_mainline_compatibility as compatibility
from lang.tests import test_l3_for_native as loops
from lang.tests import test_l3a_native_regression as native

class MainlineNativeRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner=g5.Runner();cls.runner.boot();cls.h=cls.runner.g
        for module in (semantic,guest,entry,methods,sysv,compatibility,loops,native):
            p=Path(module.__file__);cls.runner.inputs[str(p)]=g5.sha(p)
        cls.runner.inputs[str(Path(__file__))]=g5.sha(Path(__file__))
        cls.runner.native_container()
        cls.n=native.L3ANativeRegressionTests()
    @classmethod
    def tearDownClass(cls):
        try:native.L3ANativeRegressionTests.tearDownClass()
        finally:cls.runner.finish()
    def method(self,name):
        check=methods.NativeMethodTests();check.h,check.runner=self.h,self.runner
        getattr(check,name)()
    def test_method_complete_g5_paths(self):
        self.method('test_g5_closed_paths_require_native_execution')
    def test_method_scalar_aggregate_global_and_both_abis(self):
        self.method('test_existing_native_scalar_aggregate_global_and_sysv_regressions')
    def test_sysv_and_win64_g5_transitions(self):
        # A separate source/receipt namespace shares only this cold compiler.
        # The method-path oracle above already created the same gap fixtures.
        runner=g5.Runner(self.runner.work/'sysv-transition')
        runner.g,runner.nasm,runner.cc=self.h,self.h.nasm,self.h.cc
        check=sysv.NativeSysVTests();check.h,check.runner=self.h,runner
        try:check.test_g5_sysv_and_win64_fixtures_execute()
        finally:runner.assert_inputs()
    def test_global_and_external_real_calls(self):
        self.h.test_mainline_global_and_external_calls_execute()
    def test_original_external_declaration(self):
        check=compatibility.MainlineCompatibilityTests();check.g=self.h
        check.test_original_extern_declaration_links_and_executes_in_both_modes()
    def test_native_elf_exact_data_and_two_addresses(self):
        self.n.test_native_elf_layout_data_and_real_execution()
    def test_native_elf_static_pointers(self):
        self.n.test_fixed_address_static_pointer_initializers_execute()
    def test_control_flow_elf_exact_short_and_execution(self):
        check=loops.ForNativeTests();check.h,check.runner=self.h,self.runner
        check.test_native_elf_consumes_actual_lowered_control_flow()

def load_tests(loader,tests,pattern):
    suite=unittest.TestSuite()
    suite.addTest(semantic.BootstrapSemanticRuntimeTests('test_intrinsic_and_aggregate_never_flow'))
    suite.addTest(semantic.BootstrapSemanticRuntimeTests('test_tagged_cleanup_support_and_workspace_limits_are_explicit'))
    suite.addTests(loader.loadTestsFromTestCase(guest.GuestCompileImageTests))
    suite.addTests(loader.loadTestsFromTestCase(entry.MainlineRunnerEntryTests))
    suite.addTests(loader.loadTestsFromTestCase(MainlineNativeRegressionTests))
    return suite

if __name__=='__main__':unittest.main()
