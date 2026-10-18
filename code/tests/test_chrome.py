"""Fast chrome must preserve original AA, blend, clipping and byte guards."""
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


class ChromeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/chrome/host' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [ROOT / p for p in ('services/desktop/chrome.dg', 'services/desktop/render.dg',
            'services/desktop/theme.dg', 'services/desktop/widgets.dg', 'services/desktop/windows.dg',
            'services/gfx/raster.dg', 'services/gfx/geometry.dg', 'services/gfx/atlas.dg',
            'services/gfx/errors.dg', 'services/input/events.dg',
            'tests/chrome_probe.dg', 'tests/chrome_probe.c', 'tests/test_chrome.py')]
        cls.before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-before.json').write_text(json.dumps(cls.before, indent=2) + '\n', encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-after.json').write_text(json.dumps(after, indent=2) + '\n', encoding='utf-8')
        if after != cls.before:
            raise AssertionError('chrome oracle sources changed during verification')

    def test_native_original_and_independent_pixel_oracles(self):
        for mode in ('debug', 'release'):
            value, compiled = native('chrome_probe', self.directory / 'normal' / mode, mode, [ROOT / 'services'])
            self.assertEqual(0, value.returncode, value.stdout + value.stderr)
            self.assertIn('comparisons=1088', value.stdout)
            self.assertIn('atomic-invalid=8 full-array=reference+C stride-and-guards=ok', value.stdout)
            types = {t['full_name']: t for t in compiled.layout_manifest['types']}
            self.assertEqual(40, types['gfx.raster.Surface']['size'])
            self.assertEqual(32, types['gfx.geometry.Rect']['size'])

    def test_elf_coff_and_generated_stack(self):
        nasm = tool('nasm', 'NASM')
        if not nasm:
            self.skipTest('NASM unavailable')
        for mode in ('debug', 'release'):
            compiled = compile_file(ROOT / 'tests/chrome_probe.dg', roots=[ROOT / 'tests', ROOT / 'services'], mode=mode)
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
            (directory / 'stack.json').write_text(json.dumps(dict(generated_direct_call_path_bytes=maximum)) + '\n', encoding='utf-8')
            asm = directory / 'probe.asm'
            asm.write_text(compiled.assembly, encoding='utf-8')
            for fmt in ('elf64', 'win64'):
                command([nasm, '-f', fmt, *nasm_flags(nasm), '-o', directory / (fmt + '.o'), asm], directory, fmt)

    def test_missing_corner_column_bad_native_actually_rejected(self):
        source = (ROOT / 'services/desktop/chrome.dg').read_text(encoding='utf-8')
        needle = 'let tr=geo.Rect { left:(*rect).right-r,top:(*rect).top,right:(*rect).right,bottom:(*rect).top+r };'
        self.assertEqual(1, source.count(needle))
        services = self.directory / 'control' / 'services'
        for name in ('desktop', 'gfx', 'input'):
            shutil.copytree(ROOT / 'services' / name, services / name)
        source = source.replace(needle,
            'negative_hit(1);let tr=geo.Rect { left:(*rect).right-r+1,top:(*rect).top,right:(*rect).right,bottom:(*rect).top+r };').replace(
                'module desktop.chrome;', 'module desktop.chrome;\nunsafe extern "sysv64" ("chrome_negative_hit") fn negative_hit(kind:u64) void;', 1)
        (services / 'desktop/chrome.dg').write_text(source, encoding='utf-8')
        for mode in ('debug', 'release'):
            value, _ = native('chrome_probe', services.parent / mode, mode, [services])
            self.assertEqual(1, value.returncode, value.stdout + value.stderr)
            self.assertEqual(1, value.stderr.count('CHROME_NEGATIVE_HIT 1'), value.stderr)
            self.assertIn('memcmp(actual,expected,sizeof actual)==0', value.stderr)
            self.assertNotIn('panic', value.stderr)


if __name__ == '__main__':
    unittest.main()
