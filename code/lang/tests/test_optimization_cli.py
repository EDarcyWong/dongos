"""The optimization/debug switches retain CLI input and publication contracts."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from lang.dongc import compile_source


class OptimizationCLITests(unittest.TestCase):
    def invoke(self, args):
        return subprocess.run([sys.executable, "-m", "lang.dongc", *map(str, args)],
                              capture_output=True, text=True, encoding="utf-8")

    def test_ir_reports_real_ssa_and_full_function_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source, asm, manifest, ir = [directory / n for n in ("source.dg", "source.asm", "manifest.json", "ir.json")]
            source.write_text('module test; export("scalar") fn scalar(n:u64)u64{return n+3;} '
                              'fn memory(p:*u64)u64{unsafe{return volatile_load(p);}}', encoding="utf-8")
            result = self.invoke(["--mode", "release", "-O1", "--emit-asm", asm, "--emit-manifest", manifest,
                                  "--emit-ir", ir, source])
            self.assertEqual(result.returncode, 0, result.stderr)
            info = json.loads(ir.read_text(encoding="utf-8"))
            self.assertEqual([r["backend"] for r in info["functions"]], ["ssa", "l1"])
            self.assertEqual(info, json.loads(manifest.read_text())["optimization"])
            self.assertIn("blocks", info["functions"][0]["after"])

    def test_new_artifact_cannot_alias_a_source_or_another_output(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.dg"
            text = "module test; fn f()u64{return 4;}"
            path.write_text(text)
            for args in (["-O1", "--emit-ir", path],
                         ["-O1", "--emit-ir", path.with_suffix('.json'), "--emit-asm", path.with_suffix('.json')]):
                run = self.invoke([*args, path])
                self.assertEqual(run.returncode, 2, run.stderr)
                self.assertEqual(path.read_text(), text)

    def test_opt_in_ir_and_check_output_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.dg"
            path.write_text("module test; fn f()void{}")
            output = path.with_suffix('.json')
            for args in (["--emit-ir", output], ["--check", "-O1", "--emit-ir", output]):
                run = self.invoke([*args, path])
                self.assertEqual(run.returncode, 2, run.stderr)
                self.assertFalse(output.exists())

    def test_source_debugging_and_debug_mode_retain_checks(self):
        text = "module test; fn f(x:u64)u64{return x+1;}"
        for mode, debug in (("debug", False), ("release", True)):
            result = compile_source(text, mode=mode, debug_info=debug, optimize=1)
            self.assertEqual(result.optimization["functions"][0]["backend"], "l1")
            if mode == "debug":
                self.assertIn("__dong_panic", result.runtime_symbols)
            if debug:
                self.assertIn(".debug_info", result.assembly)


if __name__ == "__main__":
    unittest.main()
