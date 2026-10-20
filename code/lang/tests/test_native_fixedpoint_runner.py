"""Fast orchestration tests; mocked tools are not native fixed-point evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from tools import bootstrap_native_compiler as runner


class NativeFixedPointRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        for name, content in {
            'lang/bootstrap/a.dg': 'module bootstrap.a;',
            'lang/std/core/a.dg': 'module core.a;',
            'lang/dongc/compiler.py': '# fake seed for orchestration tests only',
            'lang/host/native_entry.dg': 'module host.native_entry;',
            'lang/host/native_driver.c': 'int main(void){return 0;}',
            'tools/build_native_frontend.py': '# fake seed builder',
        }.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.work = Path(self.temp.name) / 'work'
        self.work.mkdir()
        self.calls = []

    def fake_tool(self, args, *, cwd, env, capture_output, timeout):
        self.calls.append((args, env))
        stdout = b''
        if '-h' in args:
            stdout = b'    reloc-rel-dword    relative relocations\n    reloc-abs-qword    absolute relocations\n'
        elif '--output' in args:
            Path(args[args.index('--output') + 1]).write_bytes(b'fake-seed')
            stdout = b'{"selfhost": false}'
        elif '--emit-asm' in args:
            target = Path(args[args.index('--emit-asm') + 1])
            target.write_bytes(b'fake-assembly\n')
            stdout = json.dumps(dict(status=0, backend_status=0, backend_run=1,
                                     assembly_bytes=target.stat().st_size)).encode()
        elif '--check' in args:
            invalid = Path(args[-1]).name == 'negative.dg'
            return subprocess.CompletedProcess(args, 1 if invalid else 0,
                                               json.dumps(dict(status=3 if invalid else 0)).encode(),
                                               b'E0301\n' if invalid else b'')
        elif 'compiler.asm' in args:
            (Path(cwd) / 'compiler.o').write_bytes(b'fake-object')
        elif 'compiler.o' in args:
            (Path(cwd) / 'compiler.exe').write_bytes(b'fake-executable')
        return subprocess.CompletedProcess(args, 0, stdout, b'')

    def invoke(self, fake=None):
        with patch.object(runner, 'ROOT', self.root), \
             patch.object(runner.shutil, 'which', return_value=sys.executable), \
             patch.object(runner.subprocess, 'run', side_effect=fake or self.fake_tool), \
             patch.object(runner.platform, 'machine', return_value='x86_64'):
            return runner.run(self.work, 'debug', 10, dict(runner.DEFAULT_BUDGETS))

    def test_snapshot_exact_contents_and_source_changes(self):
        before = runner.snapshot(self.root, self.work / 'source')
        self.assertEqual(before, runner.fingerprint(self.work / 'source'))
        (self.root / 'lang/bootstrap/a.dg').write_text('module bootstrap.changed;')
        self.assertNotEqual(before, runner.fingerprint(self.root))

    def test_snapshot_rejects_symlinks(self):
        original = self.root / 'lang/bootstrap/a.dg'
        target = self.root / 'real.dg'; target.write_text(original.read_text())
        original.unlink(); original.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'non-symlink'):
            runner.snapshot(self.root, self.work / 'source')

    def test_existing_output_directory_is_never_reused(self):
        (self.work / 'receipt.json').write_text('previous evidence')
        with self.assertRaises(FileExistsError):
            runner.prepare_work(self.work)
        self.assertEqual((self.work / 'receipt.json').read_text(), 'previous evidence')

    def test_orchestration_requires_all_artifacts_and_isolates_native_path(self):
        result = self.invoke()
        self.assertTrue(result['host_fixed_point'])
        self.assertFalse(result['guest_booted'])
        self.assertFalse(result['target_python_used'])
        self.assertEqual(result['equal'], dict(asm=True, o=True, exe=True))
        native = [(args, env) for args, env in self.calls if '--emit-asm' in args or '--check' in args]
        self.assertEqual(len(native), 4)
        self.assertTrue(all(env['PATH'] == '' for _, env in native))
        self.assertTrue(all('-O0' in args for args, _ in self.calls if 'compiler.asm' in args))
        self.assertTrue(all('-w-reloc-rel-dword' in args for args, _ in self.calls if 'compiler.asm' in args))
        self.assertEqual(sum('--output' in args for args, _ in self.calls), 1)

    def test_changed_assembly_fails_even_when_objects_match(self):
        def fake(args, **kwargs):
            result = self.fake_tool(args, **kwargs)
            if '--emit-asm' in args and 'stage2.asm' in args[args.index('--emit-asm') + 1]:
                target = Path(args[args.index('--emit-asm') + 1]); target.write_bytes(b'other-assembly')
                result.stdout = json.dumps(dict(status=0, backend_status=0, backend_run=1,
                                               assembly_bytes=target.stat().st_size)).encode()
            return result
        with self.assertRaisesRegex(RuntimeError, 'fixed point differs: asm'):
            self.invoke(fake)
        receipt = json.loads((self.work / 'receipt.json').read_text())
        self.assertEqual(receipt['status'], 'failed')
        self.assertFalse(receipt['host_fixed_point'])

    def test_native_failure_never_invokes_seed_fallback(self):
        def fake(args, **kwargs):
            if '--emit-asm' in args:
                self.calls.append((args, kwargs['env']))
                return subprocess.CompletedProcess(args, 1, b'{}', b'unsupported')
            return self.fake_tool(args, **kwargs)
        with self.assertRaisesRegex(RuntimeError, 'stage1-emit exited 1'):
            self.invoke(fake)
        self.assertEqual(sum('--output' in args for args, _ in self.calls), 1)
        self.assertFalse((self.work / 'stage1.exe').exists())
        self.assertFalse(json.loads((self.work / 'receipt.json').read_text())['host_fixed_point'])

    def test_snapshot_mutation_during_native_emission_is_rejected(self):
        def fake(args, **kwargs):
            result = self.fake_tool(args, **kwargs)
            if '--emit-asm' in args:
                (self.work / 'source/lang/bootstrap/a.dg').write_text('module changed;')
            return result
        with self.assertRaisesRegex(RuntimeError, 'frozen compiler inputs changed'):
            self.invoke(fake)
        self.assertFalse((self.work / 'stage1.o').exists())
        self.assertFalse(json.loads((self.work / 'receipt.json').read_text())['host_fixed_point'])

    def test_final_negative_control_must_be_source_error(self):
        def fake(args, **kwargs):
            result = self.fake_tool(args, **kwargs)
            if '--check' in args and Path(args[-1]).name == 'negative.dg':
                result.stdout = b'{"status":2}'
            return result
        with self.assertRaisesRegex(RuntimeError, 'unexpected semantic status'):
            self.invoke(fake)
        self.assertFalse(json.loads((self.work / 'receipt.json').read_text())['host_fixed_point'])

    def test_timeout_retains_failed_receipt(self):
        def fake(args, **kwargs):
            raise subprocess.TimeoutExpired(args, kwargs['timeout'], output=b'partial')
        with self.assertRaisesRegex(RuntimeError, 'exceeded 10 seconds'):
            self.invoke(fake)
        receipt = json.loads((self.work / 'receipt.json').read_text())
        self.assertFalse(receipt['host_fixed_point'])
        self.assertTrue(receipt['commands'][0]['timeout'])
        self.assertEqual((self.work / 'nasm-version.stdout').read_bytes(), b'partial')


if __name__ == '__main__':
    unittest.main()
