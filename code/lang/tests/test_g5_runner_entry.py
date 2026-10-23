"""Check the real mainline CLI/source boundary; full matrix has its own gate."""
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from tools import g5_differential as runner

ROOT=Path(__file__).resolve().parents[2]

class MainlineRunnerEntryTests(unittest.TestCase):
    def test_actual_module_cli_and_source_root(self):
        self.assertEqual(runner.ROOT,ROOT)
        self.assertEqual(runner.DEFAULT_BUILD,ROOT/'build/test/G5-full')
        process=subprocess.run([sys.executable,'-m','tools.g5_differential','--help'],cwd=ROOT,capture_output=True,text=True,timeout=20)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr)
        self.assertIn('--output',process.stdout)
        self.assertIn('Known language gaps',process.stdout)

    def test_mainline_input_inventory_and_existing_output_protection(self):
        with tempfile.TemporaryDirectory()as temp:
            output=Path(temp)/'run'
            execution=runner.Runner(output)
            self.assertEqual(execution.assert_inputs(),execution.inputs)
            self.assertIn(str(ROOT/'lang/bootstrap/lower_program.dg'),execution.inputs)
            self.assertIn(str(ROOT/'tools/g5_differential.py'),execution.inputs)
            sentinel=output/'keep';sentinel.write_bytes(b'preserved')
            with self.assertRaises(FileExistsError):runner.Runner(output)
            self.assertEqual(sentinel.read_bytes(),b'preserved')

if __name__=='__main__':unittest.main()
