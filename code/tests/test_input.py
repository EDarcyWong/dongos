"""Actual native PS/2/VirtIO state-machine oracles, debug and release."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import time
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]


def command(args, directory, name, success=True):
    start = time.monotonic()
    result = subprocess.run([str(a) for a in args], cwd=ROOT, capture_output=True, text=True, timeout=60)
    (directory / (name + '.json')).write_text(json.dumps(dict(command=[str(a) for a in args],
        returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
        elapsed_seconds=time.monotonic() - start), indent=2), encoding='utf-8')
    if success and result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result


def native(probe, directory, mode, roots):
    nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
    if not nasm or not cc:
        raise unittest.SkipTest('native state oracle needs NASM and SysV-capable GCC')
    directory.mkdir(parents=True)
    compiled = compile_file(ROOT / ('tests/' + probe + '.dg'), roots=[ROOT / 'tests', *roots], mode=mode)
    (directory / 'layout.json').write_text(json.dumps(compiled.layout_manifest, indent=2), encoding='utf-8')
    asm, obj = directory / 'probe.asm', directory / 'probe.o'
    asm.write_text(compiled.assembly, encoding='utf-8')
    command([nasm, '-f', 'win64' if os.name == 'nt' else 'elf64', *nasm_flags(nasm), '-o', obj, asm], directory, 'assemble')
    binary = directory / ('probe.exe' if os.name == 'nt' else 'probe')
    flags = ['-mno-sse'] if os.name == 'nt' else ['-no-pie']
    command([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-D__USE_MINGW_ANSI_STDIO=1', *flags,
             ROOT / ('tests/' + probe + '.c'), obj, '-o', binary], directory, 'link')
    return command([binary], directory, 'native', success=False), compiled


class InputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/input' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [*sorted((ROOT / 'services/input').glob('*.dg')), ROOT / 'tests/input_probe.dg',
                      ROOT / 'tests/input_probe.c', Path(__file__)]
        cls.before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-before.json').write_text(json.dumps(cls.before, indent=2), encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-after.json').write_text(json.dumps(after, indent=2), encoding='utf-8')
        if after != cls.before:
            raise AssertionError('input source changed during native verification')

    def test_wire_sequences_packets_frames_and_full_state_guards(self):
        for mode in ('debug', 'release'):
            result, compiled = native('input_probe', self.directory / 'normal' / mode, mode, [ROOT / 'services'])
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn('all-guards=ok', result.stdout)
            types = {t['full_name']: t for t in compiled.layout_manifest['types']}
            self.assertEqual((32, 8), (types['input.events.Event']['size'], types['input.events.Event']['alignment']))

    def test_bad_mouse_sign_and_unblocked_loss_are_actually_rejected(self):
        controls = (
            ('mouse-sign', 'ps2.dg', 'if (head & 16) != 0 { x -= 256; }',
             'if (head & 16) != 0 { negative_hit(1); x -= 128; }', 1),
            ('drop-block', 'virtio_input.dg', 'if (*state).blocked != 0 { return; }',
             'if (*state).blocked != 0 { negative_hit(2); }', 2))
        for label, filename, needle, replacement, kind in controls:
            staging = self.directory / 'controls' / label / 'services'
            shutil.copytree(ROOT / 'services/input', staging / 'input')
            source = (staging / 'input' / filename).read_text(encoding='utf-8')
            self.assertEqual(1, source.count(needle))
            module = 'input.' + filename.removesuffix('.dg')
            source = source.replace(needle, replacement).replace('module ' + module + ';',
                'module ' + module + ';\nunsafe extern "sysv64" ("input_negative_hit") fn negative_hit(kind: u64) void;', 1)
            (staging / 'input' / filename).write_text(source, encoding='utf-8')
            for mode in ('debug', 'release'):
                result, _ = native('input_probe', staging.parent / mode, mode, [staging])
                self.assertNotEqual(0, result.returncode, 'broken input parser passed')
                self.assertEqual(1, result.stderr.count('INPUT_NEGATIVE_HIT ' + str(kind)))
                self.assertIn('input oracle line', result.stderr)


if __name__ == '__main__':
    unittest.main()
