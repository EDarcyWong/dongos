"""Native rational geometry oracle: actual generated code, both modes/formats."""
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


class DesktopTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/desktop-transition/host' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [ROOT / p for p in ('services/desktop/transition.dg', 'services/gfx/geometry.dg',
            'services/gfx/errors.dg', 'tests/transition_probe.dg', 'tests/transition_probe.c',
            'tests/test_desktop_transition.py', 'tests/test_input.py')]
        cls.inputs.extend(sorted((ROOT / 'lang/dongc').glob('*.py')))
        cls.before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-before.json').write_text(json.dumps(cls.before, indent=2) + '\n', encoding='utf-8')
        cls.evidence = {}

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-after.json').write_text(json.dumps(after, indent=2) + '\n', encoding='utf-8')
        if after != cls.before:
            raise AssertionError('transition sources changed during verification')
        (cls.directory / 'validation-summary.json').write_text(json.dumps(dict(
            sources_unchanged=True, source_sha256=after, evidence=cls.evidence), indent=2) + '\n', encoding='utf-8')

    def test_native_integer_model_scales_reversal_and_atomic_failures(self):
        modes = {}
        for mode in ('debug', 'release'):
            value, compiled = native('transition_probe', self.directory / 'normal' / mode, mode, [ROOT / 'services'])
            self.assertEqual(0, value.returncode, value.stdout + value.stderr)
            self.assertIn('five-scale-pairs=25 target-cache-budgets=100 all-guards=ok', value.stdout)
            types = {t['full_name']: t for t in compiled.layout_manifest['types']}
            self.assertEqual(80, types['desktop.transition.Track']['size'])
            self.assertEqual(32, types['gfx.geometry.Rect']['size'])
            modes[mode] = dict(returncode=value.returncode, output=value.stdout.strip())
        self.evidence['native_integer_model'] = modes

    def test_elf_coff_and_bounded_stack(self):
        nasm = tool('nasm', 'NASM')
        if not nasm:
            self.skipTest('NASM unavailable')
        modes = {}
        for mode in ('debug', 'release'):
            compiled = compile_file(ROOT / 'tests/transition_probe.dg', roots=[ROOT / 'tests', ROOT / 'services'], mode=mode)
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
            self.assertLessEqual(maximum, 4096)
            directory = self.directory / 'formats' / mode
            directory.mkdir(parents=True)
            asm = directory / 'probe.asm'
            asm.write_text(compiled.assembly, encoding='utf-8')
            for fmt in ('elf64', 'win64'):
                command([nasm, '-f', fmt, *nasm_flags(nasm), '-o', directory / (fmt + '.o'), asm], directory, fmt)
            modes[mode] = dict(generated_direct_call_path_bytes=maximum, formats=['elf64', 'win64'])
        self.evidence['object_formats_and_stack'] = modes

    def test_endpoint_activity_off_by_one_is_rejected(self):
        source = (ROOT / 'services/desktop/transition.dg').read_text(encoding='utf-8')
        needle = 'if elapsed<(*track).duration_ms {'
        self.assertEqual(1, source.count(needle))
        services = self.directory / 'control' / 'services'
        for name in ('desktop', 'gfx'):
            (services / name).mkdir(parents=True)
        shutil.copy2(ROOT / 'services/gfx/geometry.dg', services / 'gfx/geometry.dg')
        shutil.copy2(ROOT / 'services/gfx/errors.dg', services / 'gfx/errors.dg')
        source = source.replace(needle, 'if elapsed<=(*track).duration_ms { negative_hit(1);').replace(
            'module desktop.transition;', 'module desktop.transition;\nunsafe extern "sysv64" ("transition_negative_hit") fn negative_hit(kind:u64) void;', 1)
        (services / 'desktop/transition.dg').write_text(source, encoding='utf-8')
        modes = {}
        for mode in ('debug', 'release'):
            value, _ = native('transition_probe', services.parent / mode, mode, [services])
            self.assertEqual(1, value.returncode, value.stdout + value.stderr)
            self.assertEqual(1, value.stderr.count('TRANSITION_NEGATIVE_HIT 1'), value.stderr)
            self.assertIn('actual_active==expected_active', value.stderr)
            self.assertNotIn('panic', value.stderr)
            modes[mode] = dict(returncode=value.returncode, hit=1, assertion='actual_active==expected_active')
        self.evidence['actual_bad_implementation_rejected'] = modes


if __name__ == '__main__':
    unittest.main()
