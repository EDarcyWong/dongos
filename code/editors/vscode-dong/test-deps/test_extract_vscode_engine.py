"""Offline recovery regression tests; only temporary copies are modified."""
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import shutil
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('extract_engine', HERE / 'extract_vscode_engine.py')
extractor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extractor)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / 'app'
        self.output = self.root / 'output'
        self.app.mkdir()
        self.output.mkdir()
        self.lock = json.loads((HERE / 'engine-lock.json').read_text())
        self.lock_bytes = (HERE / 'engine-lock.json').read_bytes()
        (self.output / 'engine-lock.json').write_bytes(self.lock_bytes)
        self.original_here = extractor.HERE
        extractor.HERE = self.output
        self.addCleanup(setattr, extractor, 'HERE', self.original_here)

    def make_app(self, corrupt=False, version=None):
        (self.app / 'package.json').write_text(json.dumps({'version': version or self.lock['vscode_version']}))
        tree = {'files': {}}
        payload = bytearray()
        for relative in self.lock['files']:
            parts = relative.split('/')[1:]
            data = (HERE / relative).read_bytes()
            if corrupt and relative.endswith('vscode-textmate/release/main.js'):
                data += b'\n'
            branch = tree
            for part in parts[:-1]:
                branch = branch['files'].setdefault(part, {'files': {}})
            if relative.endswith('.wasm'):
                branch['files'][parts[-1]] = {'size': len(data), 'unpacked': True}
                target = self.app / 'node_modules.asar.unpacked' / Path(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            else:
                branch['files'][parts[-1]] = {'size': len(data), 'offset': str(len(payload))}
                payload.extend(data)
        header = json.dumps(tree).encode()
        (self.app / 'node_modules.asar').write_bytes(struct.pack('<4I', 4, 8 + len(header), 0, len(header)) + header + payload)

    def test_exact_recovery_preserves_lock(self):
        self.make_app()
        extractor.extract(self.app)
        self.assertEqual(self.lock_bytes, (self.output / 'engine-lock.json').read_bytes())
        for relative in self.lock['files']:
            self.assertEqual((HERE / relative).read_bytes(), (self.output / relative).read_bytes())

    def test_mismatch_does_not_write_or_repin(self):
        self.make_app(corrupt=True)
        with self.assertRaisesRegex(ValueError, 'dependency hash mismatch'):
            extractor.extract(self.app)
        self.assertFalse((self.output / 'vendor').exists())
        self.assertEqual(self.lock_bytes, (self.output / 'engine-lock.json').read_bytes())

    def test_wrong_vscode_version_does_not_write(self):
        self.make_app(version='0.0.0')
        with self.assertRaisesRegex(ValueError, 'VS Code version'):
            extractor.extract(self.app)
        self.assertFalse((self.output / 'vendor').exists())

    def test_runner_rejects_tampered_runtime(self):
        self.make_app()
        extractor.extract(self.app)
        shutil.copyfile(HERE / 'run_textmate.cjs', self.output / 'run_textmate.cjs')
        target = self.output / 'vendor/vscode-oniguruma/release/onig.wasm'
        target.write_bytes(target.read_bytes() + b'corruption')
        result = subprocess.run(['node', str(self.output / 'run_textmate.cjs')],
                                input='{"groups": []}', text=True, capture_output=True, timeout=20)
        self.assertNotEqual(0, result.returncode)
        self.assertIn('dependency hash mismatch', result.stderr)
        self.assertEqual('', result.stdout)


if __name__ == '__main__':
    unittest.main()
