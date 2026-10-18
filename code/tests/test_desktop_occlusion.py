"""Real DG occlusion code versus independent spatial and floor-sampling models."""
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


class DesktopOcclusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/desktop-occlusion/host' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [ROOT / name for name in ('services/desktop/occlusion.dg', 'services/gfx/geometry.dg',
            'services/gfx/errors.dg', 'tests/occlusion_probe.dg', 'tests/occlusion_probe.c',
            'tests/test_desktop_occlusion.py', 'tests/test_input.py')]
        cls.inputs.extend(sorted((ROOT / 'lang/dongc').glob('*.py')))
        cls.before = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.inputs}
        cls.evidence = {}

    @classmethod
    def tearDownClass(cls):
        after = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.inputs}
        if after != cls.before:
            raise AssertionError('occlusion sources changed during native verification')
        (cls.directory / 'validation-summary.json').write_text(json.dumps(dict(source_sha256=after,
            sources_unchanged=True, actual_qemu_executed=False, evidence=cls.evidence), indent=2) + '\n', encoding='utf-8')

    def test_native_coverage_highest_preimage_ceil_atomic_alias_and_guards(self):
        modes = {}
        for mode in ('debug', 'release'):
            result, compiled = native('occlusion_probe', self.directory / 'normal' / mode, mode, [ROOT / 'services'])
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn('capacity81+full-i64+alias+guards=ok', result.stdout)
            types = {item['full_name']: item for item in compiled.layout_manifest['types']}
            self.assertEqual(40, types['desktop.occlusion.Part']['size'])
            self.assertEqual(3248, types['desktop.occlusion.Plan']['size'])
            modes[mode] = result.stdout.strip()
        self.evidence['independent_spatial_and_floor_model'] = modes

    def test_elf_coff_and_generated_stack_bound(self):
        nasm = tool('nasm', 'NASM')
        if not nasm:
            self.skipTest('NASM required')
        modes = {}
        for mode in ('debug', 'release'):
            compiled = compile_file(ROOT / 'tests/occlusion_probe.dg', roots=[ROOT / 'tests', ROOT / 'services'], mode=mode)
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
            maximum = max(map(stack, functions))
            single = max(item['frame'] for item in functions.values())
            self.assertLessEqual(single, 4096)
            self.assertLessEqual(maximum, 4096)
            directory = self.directory / 'formats' / mode
            directory.mkdir(parents=True)
            asm = directory / 'probe.asm'
            asm.write_text(compiled.assembly, encoding='utf-8')
            for fmt in ('elf64', 'win64'):
                command([nasm, '-f', fmt, *nasm_flags(nasm), '-o', directory / (fmt + '.o'), asm], directory, fmt)
            modes[mode] = dict(maximum_single_function_frame=single, generated_direct_call_path_bytes=maximum,
                               formats=['elf64', 'win64'], frames=functions)
            for item in modes[mode]['frames'].values():
                item['calls'] = sorted(item['calls'])
        self.evidence['formats_and_stack'] = modes

    def test_real_wrong_highest_and_floor_instead_of_ceil_are_rejected(self):
        original = (ROOT / 'services/desktop/occlusion.dg').read_text(encoding='utf-8')
        controls = (
            ('highest', 'owner=(i+1) as u8;', 'negative_hit(1);owner=i as u8;', 1, 'actual_first==expected_first'),
            ('rounding', 'return (position*target+source as i64-1)/(source as i64);',
             'unsafe { negative_hit(2); }return (position*target)/(source as i64);', 2,
             'memcmp(&interior.value,&expected,sizeof expected)==0'))
        evidence = {}
        for label, needle, replacement, kind, assertion in controls:
            self.assertEqual(1, original.count(needle))
            services = self.directory / 'controls' / label / 'services'
            for name in ('desktop', 'gfx'):
                (services / name).mkdir(parents=True)
            for name in ('geometry.dg', 'errors.dg'):
                shutil.copy2(ROOT / 'services/gfx' / name, services / 'gfx' / name)
            source = original.replace(needle, replacement).replace('module desktop.occlusion;',
                'module desktop.occlusion;\nunsafe extern "sysv64" ("occlusion_negative_hit") fn negative_hit(kind:u64)void;', 1)
            (services / 'desktop/occlusion.dg').write_text(source, encoding='utf-8')
            modes = {}
            for mode in ('debug', 'release'):
                result, _ = native('occlusion_probe', services.parent / mode, mode, [services])
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertEqual(1, result.stderr.count('OCCLUSION_NEGATIVE_HIT ' + str(kind)), result.stderr)
                self.assertIn(assertion, result.stderr)
                self.assertNotIn('panic', result.stderr)
                modes[mode] = dict(exit=1, marker=kind, actual_assertion=assertion, stderr=result.stderr.strip())
            evidence[label] = modes
        self.evidence['actual_bad_implementations_rejected'] = evidence


if __name__ == '__main__':
    unittest.main()
