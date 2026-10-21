"""Independent gate for the finite runner; never declares the whole G5 complete."""
import importlib.util
from pathlib import Path
import unittest
import tempfile

SPEC=importlib.util.spec_from_file_location('g5_differential',Path(__file__).parents[1]/'l3/g5_differential.py')
runner=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(runner)

class DifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.execution=runner.Runner();cls.result=cls.execution.run()

    def test_supported_matrix_actual_native_values_and_formats(self):
        result=self.result
        self.assertTrue(result['runner_scope_passed'])
        self.assertTrue(result['source_stable'])
        self.assertEqual(result['source_before'],result['source_after'])
        self.assertEqual({(r['name'],r['mode']) for r in result['supported_pass']},
                         {(n,m) for n in ('audit','globals','generated') for m in ('debug','release')})
        for case in result['supported_pass']:
            runner.validate_path(case)
            self.assertEqual(case['seed']['stdout'],case['native']['stdout'])
            self.assertEqual(case['native']['returncode'],0)
            self.assertEqual(case['native']['driver_sha256'],result['compiler']['sha256'])
            self.assertEqual(runner.sha(case['native']['assembly_path']),case['native']['assembly_sha256'])
            self.assertNotEqual(case['seed']['assembly_path'],case['native']['assembly_path'])
            completed=[c for c in result['commands'] if c['command'][0]==result['compiler']['path']
                       and len(c['command'])==5 and c['command'][3]==case['native']['assembly_path']]
            self.assertEqual(len(completed),1)
            self.assertEqual(completed[0]['returncode'],0)
        self.assertTrue(result['native_container']['passed'])
        self.assertEqual(len(result['runtime_checks']),22)
        for record in result['runtime_checks']:
            if record['guarded']:
                self.assertEqual(record['seed_returncode'],85)
                self.assertIn('PANIC ',record['seed_diagnostic'])
                self.assertIn(record['native_returncode'],(86,-4))
            else:
                self.assertEqual((record['seed_returncode'],record['native_returncode']),(0,0))
        self.assertEqual(len(result['diagnostic_pass']),2)
        for record in result['diagnostic_pass']:
            self.assertEqual(record['status'],'diagnostic-pass')
            self.assertTrue(record['seed']['category'].startswith('E'))
            self.assertIn('frontend status=',record['native'])
        commands=result['commands']
        self.assertTrue(any('-f' in c['command'] and 'elf64' in c['command'] for c in commands))
        self.assertTrue(any('-f' in c['command'] and 'win64' in c['command'] for c in commands))
        self.assertTrue(all(not c.get('timed_out') for c in commands))

    def test_known_gaps_do_not_count_as_supported_or_complete(self):
        self.assertIs(self.result['scope_complete'],False)
        self.assertEqual(set(self.result['remaining']),set(runner.GAPS))
        self.assertEqual(len(self.result['known_gap']),2*len(runner.GAPS))
        for gap in self.result['known_gap']:
            self.assertEqual(gap['status'],'known-gap')
            self.assertEqual(gap['seed']['returncode'],0)
            self.assertIn(gap['native']['returncode'],(10,11,12))
            self.assertTrue(gap['native']['output_unchanged'])
            self.assertGreater(gap['native']['status'],0)
            self.assertGreater(gap['native']['line'],0)
            self.assertGreater(gap['native']['column'],0)
            self.assertGreaterEqual(gap['native']['offset'],0)
        self.assertEqual(self.result['failure'],[])
        self.assertEqual(self.result['skip'],[])

    def test_actual_bad_dong_and_bad_runner_are_precisely_rejected(self):
        negatives=self.result['negative_controls']
        self.assertEqual(len(negatives),5)
        for n in negatives:
            if n['name']=='seed-fallback':
                self.assertEqual(n['status'],'rejected-provenance')
                self.assertIn('fallback forbidden',n['reason'])
            else:
                self.assertEqual(n['status'],'rejected-semantic')
                self.assertEqual(n['observed']['returncode'],2)
                self.assertIn(n['reason'],n['observed']['stderr'])

class TargetSourceInventoryTests(unittest.TestCase):
    def test_generated_target_mutation_is_rejected_before_either_pipeline(self):
        with tempfile.TemporaryDirectory()as temp:
            execution=runner.Runner(Path(temp)/'run')
            directory=execution.source_directory('input',[('main.dg','module main;pub fn f()u64{return 7;}')])
            source=directory/'main.dg';original=source.read_bytes()
            self.assertIn(str(source),execution.inputs)
            execution.assert_inputs()
            source.write_bytes(original.replace(b'7',b'8'))
            with self.assertRaisesRegex(AssertionError,'generated target source changed'):execution.assert_inputs()
            with self.assertRaisesRegex(AssertionError,'generated target source changed'):execution.seed(directory,'debug')
            with self.assertRaisesRegex(AssertionError,'generated target source changed'):execution.dong(directory,'debug')
            source.write_bytes(original)
            self.assertEqual(execution.assert_inputs(),execution.inputs)

if __name__=='__main__':unittest.main()
