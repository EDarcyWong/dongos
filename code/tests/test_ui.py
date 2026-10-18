"""Native dynamic theme/widgets/AA rendering and invalid-frame atomicity."""
from pathlib import Path
import hashlib
import json
import shutil
import unittest
import uuid
from tests.test_input import ROOT, native


class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/ui' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [*sorted((ROOT / 'services/desktop').glob('*.dg')), ROOT / 'tests/ui_probe.dg', ROOT / 'tests/ui_probe.c', Path(__file__)]
        cls.before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-before.json').write_text(json.dumps(cls.before, indent=2), encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-after.json').write_text(json.dumps(after, indent=2), encoding='utf-8')
        if cls.before != after:
            raise AssertionError('UI sources changed during verification')

    def test_actual_dynamic_controls_unicode_and_full_pixel_oracle(self):
        for mode in ('debug', 'release'):
            result, compiled = native('ui_probe', self.directory / 'normal' / mode, mode, [ROOT / 'services'])
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn('full-byte-guards=ok', result.stdout)
            # Large app/model storage is caller-owned; no giant hidden local.
            import re
            frames = [int(n) for n in re.findall(r'sub rsp, (\d+)', compiled.assembly)]
            self.assertTrue(frames and max(frames) <= 4096, max(frames))

    def test_theme_range_and_late_geometry_controls_actually_rejected(self):
        controls = (
            ('theme-range', 'theme.dg', 'try validate(&value); *out = value;',
             'if value.scale_q8 < 256 || value.scale_q8 > 1024 { negative_hit(1); } *out = value;', 1),
            ('frame-preflight', 'render.dg', 'try check_frame(dst,font,value,style,damage);',
             'if (*value).count != 0 && (*value).controls[(*value).count-1].rect.right > (*value).bounds.right { negative_hit(2); }', 2))
        for label, filename, needle, replacement, kind in controls:
            staging = self.directory / 'controls' / label / 'services'
            for name in ('desktop', 'gfx', 'input'):
                shutil.copytree(ROOT / 'services' / name, staging / name)
            source = (staging / 'desktop' / filename).read_text(encoding='utf-8')
            self.assertEqual(1, source.count(needle))
            module = 'desktop.' + filename.removesuffix('.dg')
            source = source.replace(needle, replacement).replace('module ' + module + ';',
                'module ' + module + ';\nunsafe extern "sysv64" ("ui_negative_hit") fn negative_hit(kind: u64) void;', 1)
            (staging / 'desktop' / filename).write_text(source, encoding='utf-8')
            for mode in ('debug', 'release'):
                result, _ = native('ui_probe', staging.parent / mode, mode, [staging])
                self.assertNotEqual(0, result.returncode, 'broken UI accepted by oracle')
                self.assertEqual(1, result.stderr.count('UI_NEGATIVE_HIT ' + str(kind)))
                self.assertIn('ui oracle line', result.stderr)


if __name__ == '__main__':
    unittest.main()
