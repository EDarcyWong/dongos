"""Real native window policy, separate lifetime and hit-test expectations."""
from pathlib import Path
import hashlib
import json
import shutil
import unittest
import uuid
from tests.test_input import ROOT, native


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/desktop' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [*sorted((ROOT / 'services/desktop').glob('*.dg')), *sorted((ROOT / 'services/gfx').glob('*.dg')),
                      *sorted((ROOT / 'services/input').glob('*.dg')), ROOT / 'tests/desktop_probe.dg',
                      ROOT / 'tests/desktop_probe.c', ROOT / 'tests/test_input.py', Path(__file__)]
        cls.before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-before.json').write_text(json.dumps(cls.before, indent=2), encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-after.json').write_text(json.dumps(after, indent=2), encoding='utf-8')
        if after != cls.before:
            raise AssertionError('desktop dependencies changed during native verification')

    def test_real_lifetimes_drag_resize_and_independent_hit_focus_model(self):
        for mode in ('debug', 'release'):
            result, compiled = native('desktop_probe', self.directory / 'normal' / mode, mode, [ROOT / 'services'])
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn('independent_focus_steps=3000 guards-lifetimes=ok', result.stdout)
            types = {t['full_name']: t for t in compiled.layout_manifest['types']}
            self.assertEqual(144, types['desktop.windows.Slot']['size'])
            self.assertEqual(3128, types['desktop.windows.State']['size'])

    def test_stale_generation_and_live_retired_buffer_controls_rejected(self):
        controls = (
            ('stale-generation', 'if handle(state,i) != value ||',
             'if handle(state,i) != value { negative_hit(1); }\n        if false ||', 1),
            ('retired-buffer', 'if (*slot).retired_buffer != 0 { return error.Busy; }',
             'if (*slot).retired_buffer != 0 { negative_hit(2); }', 2))
        for label, needle, replacement, kind in controls:
            staging = self.directory / 'controls' / label / 'services'
            for module in ('desktop', 'input', 'gfx'):
                shutil.copytree(ROOT / 'services' / module, staging / module)
            source = (staging / 'desktop/windows.dg').read_text(encoding='utf-8')
            self.assertEqual(1, source.count(needle))
            source = source.replace(needle, replacement).replace('module desktop.windows;',
                'module desktop.windows;\nunsafe extern "sysv64" ("desktop_negative_hit") fn negative_hit(kind: u64) void;', 1)
            (staging / 'desktop/windows.dg').write_text(source, encoding='utf-8')
            for mode in ('debug', 'release'):
                result, _ = native('desktop_probe', staging.parent / mode, mode, [staging])
                self.assertNotEqual(0, result.returncode, 'broken lifetime policy passed')
                self.assertEqual(1, result.stderr.count('DESKTOP_NEGATIVE_HIT ' + str(kind)))
                self.assertIn('desktop oracle line', result.stderr)


if __name__ == '__main__':
    unittest.main()
