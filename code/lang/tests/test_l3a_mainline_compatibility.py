"""Run the formerly rejected GLOBAL/.data fixtures through the actual Dong path.

The older broad probes retain their Linux execution requirements. This focused
gate uses the existing SysV Windows bridge and never counts a skip as success.
"""
import hashlib
import json
from pathlib import Path
import unittest
from lang.tests import test_l3a_globals as globals_bridge
from lang.tests import test_l3a_native_regression as native_bridge


class MainlineCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = [Path(__file__), Path(__file__).with_name('test_bootstrap_native_compiler.py'),
                     Path(__file__).with_name('test_bootstrap_native_assembler.py')]
        cls.before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
        globals_bridge.L3AGlobalsTests.setUpClass()
        cls.g = globals_bridge.L3AGlobalsTests()
        native_bridge.L3ANativeRegressionTests.setUpClass()
        cls.n = native_bridge.L3ANativeRegressionTests()

    def test_original_global_fixture_executes_in_both_modes(self):
        source = 'module unsupported; var x:u64=1; pub fn f()u64{return x;}'
        declarations = 'extern U ABI f(void) __asm__("'+globals_bridge.label('unsupported', 'f')+'");'
        for mode in (0, 1):
            _, asm = self.g.generate('good', [('unsupported.dg', source)], 'old-global-'+str(mode), mode)
            obj = self.g.assemble(asm, 'old-global-'+str(mode))
            self.g.observe(obj, 'old-global-'+str(mode), 'if(f()!=1||f()!=1){return 2;}\nreturn 0;', declarations)

    def test_extern_still_fails_closed_in_both_modes(self):
        source = self.g.work/'old-extern.dg'
        source.write_text('module unsupported; extern "sysv64" fn f()u64;')
        for mode in (0, 1):
            output = self.g.work/('old-extern-'+str(mode)+'.asm')
            output.write_bytes(b'unchanged')
            p = self.g.command([self.g.drivers['good'], source, 'unsupported.dg', output, mode],
                               'old-extern-'+str(mode), expect=None)
            self.assertEqual(p.returncode, 11, p.stdout+p.stderr)
            self.assertIn('lower status=3', p.stderr)
            self.assertEqual(output.read_bytes(), b'unchanged')

    def test_data_bytes_execute_and_bad_sections_remain_rejected(self):
        # This executes a real writable data update from the exact 0x400000
        # native ELF mapping; the mapper does not rebase pointers or edit code.
        for mode in (0, 1):
            source = self.n.work/('data-'+str(mode)+'.dg')
            source.write_text('module native; pub var x:u64=1; pub fn f()u64{x+=41;return x;}')
            asm, elf = source.with_suffix('.asm'), source.with_suffix('.elf')
            self.n.command([self.n.driver, source, 'native.dg', asm, mode, elf,
                            native_bridge.label('native', 'f')], 'data-pipeline-'+str(mode))
            image = elf.read_bytes()
            _, headers = self.n.parse_elf(image)
            data = headers[1]
            self.assertEqual(image[data[2]:data[2]+8], (1).to_bytes(8, 'little'))
            run = self.n.command([self.n.mapper, elf, '400000', '0'], 'data-execute-'+str(mode))
            self.assertRegex(run.stdout, r'PTR 2a(?:\r?\n|$)')
        self.n.test_assembler_rejects_data_section_abuse_and_preserves_outputs()

    @classmethod
    def tearDownClass(cls):
        globals_bridge.L3AGlobalsTests.tearDownClass()
        native_bridge.L3ANativeRegressionTests.tearDownClass()
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
        (cls.n.work/'mainline-compatibility.json').write_text(json.dumps(dict(
            source_before=cls.before, source_after=after, source_stable=after==cls.before,
            older_linux_suite_executed=False, scope='GLOBAL/.data compatibility gate'), indent=2)+'\n')
        if cls.before != after:
            raise AssertionError('mainline compatibility inputs changed')


if __name__ == '__main__':
    unittest.main()
