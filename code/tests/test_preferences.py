"""Canonical dual-slot theme records, damage rejection and native controls."""
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


class PreferencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/preferences/host' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [ROOT / p for p in ('services/desktop/preferences.dg', 'services/desktop/theme.dg',
            'tests/preferences_probe.dg', 'tests/preferences_probe.c', 'tests/test_preferences.py')]
        cls.before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-before.json').write_text(json.dumps(cls.before, indent=2) + '\n', encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-after.json').write_text(json.dumps(after, indent=2) + '\n', encoding='utf-8')
        if after != cls.before:
            raise AssertionError('preferences sources changed during verification')

    def test_native_canonical_damage_fallback_and_atomic_rejection(self):
        for mode in ('debug', 'release'):
            value, compiled = native('preferences_probe', self.directory / 'normal' / mode, mode, [ROOT / 'services'])
            self.assertEqual(0, value.returncode, value.stdout + value.stderr)
            self.assertIn('corrupt-bits=1024 fallback=2048', value.stdout)
            self.assertIn('checksum=independent both-slots-and-guards=ok', value.stdout)
            types = {t['full_name']: t for t in compiled.layout_manifest['types']}
            self.assertEqual(72, types['desktop.theme.Theme']['size'])
            self.assertEqual(80, types['desktop.preferences.Record']['size'])

    def test_elf_coff_and_generated_stack(self):
        nasm = tool('nasm', 'NASM')
        if not nasm:
            self.skipTest('NASM unavailable')
        for mode in ('debug', 'release'):
            compiled = compile_file(ROOT / 'tests/preferences_probe.dg', roots=[ROOT / 'tests', ROOT / 'services'], mode=mode)
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

    def test_checksum_bypass_bad_native_actually_rejected(self):
        source = (ROOT / 'services/desktop/preferences.dg').read_text(encoding='utf-8')
        needle = 'if read_unaligned((p+104) as *const u64)!=checksum(bytes) { return error.InvalidChecksum; }'
        self.assertEqual(1, source.count(needle))
        services = self.directory / 'control' / 'services'
        (services / 'desktop').mkdir(parents=True)
        shutil.copy2(ROOT / 'services/desktop/theme.dg', services / 'desktop/theme.dg')
        source = source.replace(needle, 'if read_unaligned((p+104) as *const u64)!=checksum(bytes) { negative_hit(1); }').replace(
            'module desktop.preferences;', 'module desktop.preferences;\nunsafe extern "sysv64" ("preferences_negative_hit") fn negative_hit(kind:u64) void;', 1)
        (services / 'desktop/preferences.dg').write_text(source, encoding='utf-8')
        for mode in ('debug', 'release'):
            value, _ = native('preferences_probe', services.parent / mode, mode, [services])
            self.assertEqual(1, value.returncode, value.stdout + value.stderr)
            self.assertEqual(1, value.stderr.count('PREFERENCES_NEGATIVE_HIT 1'), value.stderr)
            self.assertIn('prefs_decode(p,length,&out.value)!=0', value.stderr)
            self.assertNotIn('panic', value.stderr)


if __name__ == '__main__':
    unittest.main()
