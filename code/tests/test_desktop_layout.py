"""Independent DPI layout metrics, lifetime invariants and atomic failures."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
from tests.test_input import ROOT, command, native


class DesktopLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/desktop-layout/host' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [ROOT / p for p in ('services/desktop/layout.dg', 'services/desktop/windows.dg',
            'services/gfx/geometry.dg', 'services/gfx/errors.dg', 'services/input/events.dg',
            'tests/layout_probe.dg', 'tests/layout_probe.c', 'tests/test_desktop_layout.py')]
        cls.before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-before.json').write_text(json.dumps(cls.before, indent=2) + '\n', encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-after.json').write_text(json.dumps(after, indent=2) + '\n', encoding='utf-8')
        if after != cls.before:
            raise AssertionError('layout sources changed during verification')

    def test_native_all_scale_pairs_lifetimes_and_atomic_failures(self):
        for mode in ('debug', 'release'):
            value, compiled = native('layout_probe', self.directory / 'normal' / mode, mode, [ROOT / 'services'])
            self.assertEqual(0, value.returncode, value.stdout + value.stderr)
            self.assertIn('full-State=730', value.stdout)
            self.assertIn('five-scale-pairs=25 stride-guards=ok', value.stdout)
            types = {t['full_name']: t for t in compiled.layout_manifest['types']}
            self.assertEqual(3128, types['desktop.windows.State']['size'])
            self.assertEqual(144, types['desktop.windows.Slot']['size'])

    def test_elf_coff_and_16k_stack_bound(self):
        nasm = tool('nasm', 'NASM')
        if not nasm:
            self.skipTest('NASM unavailable')
        for mode in ('debug', 'release'):
            compiled = compile_file(ROOT / 'tests/layout_probe.dg', roots=[ROOT / 'tests', ROOT / 'services'], mode=mode)
            functions, current = {}, None
            for line in compiled.assembly.splitlines():
                match = re.match(r'^\$([A-Za-z_][A-Za-z0-9_]*):$', line)
                if match:
                    current = match.group(1)
                    functions[current] = dict(frame=16, calls=set())
                if current:
                    match = re.search(r'\bsub rsp, (\d+)', line)
                    if match:
                        functions[current]['frame'] += int(match.group(1))
                    match = re.search(r'\bcall \$([A-Za-z_][A-Za-z0-9_]*)\b', line)
                    if match:
                        functions[current]['calls'].add(match.group(1))
            def stack(name, path=()):
                self.assertNotIn(name, path)
                item = functions[name]
                return item['frame'] + max([stack(child, (*path, name)) for child in item['calls'] if child in functions] or [0])
            maximum = max(stack(name) for name in functions)
            self.assertLessEqual(maximum, 16384)
            directory = self.directory / 'formats' / mode
            directory.mkdir(parents=True)
            (directory / 'stack.json').write_text(json.dumps(dict(generated_direct_call_path_bytes=maximum,
                caller_stack_bytes=16384, caller_remaining_bytes=16384-maximum)) + '\n', encoding='utf-8')
            asm = directory / 'probe.asm'
            asm.write_text(compiled.assembly, encoding='utf-8')
            for fmt in ('elf64', 'win64'):
                command([nasm, '-f', fmt, *nasm_flags(nasm), '-o', directory / (fmt + '.o'), asm], directory, fmt)

    def test_partial_commit_before_late_serial_failure_rejected(self):
        source = (ROOT / 'services/desktop/layout.dg').read_text(encoding='utf-8')
        needle = 'if (*slot).serial==MAX { return error.SerialExhausted; }'
        self.assertEqual(1, source.count(needle))
        services = self.directory / 'control' / 'services'
        for name in ('desktop', 'gfx', 'input'):
            shutil.copytree(ROOT / 'services' / name, services / name)
        source = source.replace(needle, 'if (*slot).serial==MAX { if i==3 { negative_hit(1);*state=candidate; }return error.SerialExhausted; }').replace(
            'module desktop.layout;', 'module desktop.layout;\nunsafe extern "sysv64" ("layout_negative_hit") fn negative_hit(kind:u64) void;', 1)
        (services / 'desktop/layout.dg').write_text(source, encoding='utf-8')
        for mode in ('debug', 'release'):
            value, _ = native('layout_probe', services.parent / mode, mode, [services])
            self.assertEqual(1, value.returncode, value.stdout + value.stderr)
            self.assertEqual(1, value.stderr.count('LAYOUT_NEGATIVE_HIT 1'), value.stderr)
            self.assertIn('memcmp(&actual.state,&before,sizeof before)==0', value.stderr)
            self.assertNotIn('panic', value.stderr)


if __name__ == '__main__':
    unittest.main()
