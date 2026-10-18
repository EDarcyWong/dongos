"""Execute the real texture sampler against independent rational/pixel models."""
from pathlib import Path
import hashlib
import json
import os
import re
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
from tests.test_input import ROOT, command


class TransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/desktop-transform/host' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [ROOT / p for p in ('services/desktop/transform.dg', 'services/gfx/transform.asm',
            'services/gfx/accelerated.asm', 'services/gfx/raster.dg', 'services/gfx/geometry.dg', 'services/gfx/errors.dg',
            'tests/transform_probe.dg', 'tests/transform_probe.c', 'tests/transform_register_fixture.asm', 'tests/test_desktop_transform.py')]
        cls.before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-before.json').write_text(json.dumps(cls.before, indent=2) + '\n', encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-after.json').write_text(json.dumps(after, indent=2) + '\n', encoding='utf-8')
        if after != cls.before:
            raise AssertionError('transform inputs changed during verification')

    def native(self, mode, directory, sampler=None):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not nasm or not cc:
            self.skipTest('native texture oracle needs NASM and SysV GCC')
        directory.mkdir(parents=True)
        compiled = compile_file(ROOT / 'tests/transform_probe.dg', roots=[ROOT / 'tests', ROOT / 'services'], mode=mode)
        asm = directory / 'probe.asm'
        asm.write_text(compiled.assembly, encoding='utf-8')
        (directory / 'layout.json').write_text(json.dumps(compiled.layout_manifest, indent=2), encoding='utf-8')
        sources = [asm, sampler or ROOT / 'services/gfx/transform.asm', ROOT / 'tests/transform_register_fixture.asm', ROOT / 'services/gfx/accelerated.asm']
        objects = []
        for i, source in enumerate(sources):
            obj = directory / f'input-{i}.o'
            command([nasm, '-f', 'win64' if os.name == 'nt' else 'elf64', *nasm_flags(nasm), '-o', obj, source], directory, f'assemble-{i}')
            objects.append(obj)
        binary = directory / ('probe.exe' if os.name == 'nt' else 'probe')
        flags = ['-mno-sse'] if os.name == 'nt' else ['-no-pie', '-D_DEFAULT_SOURCE']
        command([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation',
            '-D__USE_MINGW_ANSI_STDIO=1', *flags, ROOT / 'tests/transform_probe.c', *objects, '-o', binary], directory, 'link')
        return command([binary], directory, 'native', success=False), compiled

    def test_actual_asm_exact_sampling_clips_opacity_and_guards(self):
        for mode in ('debug', 'release'):
            value, compiled = self.native(mode, self.directory / 'normal' / mode)
            self.assertEqual(0, value.returncode, value.stdout + value.stderr)
            self.assertIn('cases=1335 partitioned=1329 atomic-invalid=20', value.stdout)
            self.assertIn('actual-ASM guards+SysV=ok', value.stdout)
            types = {t['full_name']: t for t in compiled.layout_manifest['types']}
            self.assertEqual(104, types['desktop.transform.Command']['size'])

    def test_elf_coff_and_bounded_generated_stack(self):
        nasm = tool('nasm', 'NASM')
        if not nasm:
            self.skipTest('NASM unavailable')
        for mode in ('debug', 'release'):
            compiled = compile_file(ROOT / 'tests/transform_probe.dg', roots=[ROOT / 'tests', ROOT / 'services'], mode=mode)
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
            (directory / 'stack.json').write_text(json.dumps(dict(generated_direct_call_path_bytes=maximum, native_frame_bytes=48)) + '\n', encoding='utf-8')
            asm = directory / 'probe.asm'
            asm.write_text(compiled.assembly, encoding='utf-8')
            for fmt in ('elf64', 'win64'):
                for i, source in enumerate((asm, ROOT / 'services/gfx/transform.asm', ROOT / 'tests/transform_register_fixture.asm', ROOT / 'services/gfx/accelerated.asm')):
                    command([nasm, '-f', fmt, *nasm_flags(nasm), '-o', directory / f'{fmt}-{i}.o', source], directory, f'{fmt}-{i}')

    def test_wrong_sampling_negative_control_is_actually_executed(self):
        source = (ROOT / 'services/gfx/transform.asm').read_text(encoding='utf-8')
        # Corrupt the original SSE2 GATHER4 only. The permanently forced-zero
        # feature flag makes this a real fallback-path sampling control even
        # when the source also contains the independently tested AVX2 tails.
        needle = '%macro GATHER4 0\n    movzx edx,word [rsi]\n'
        self.assertEqual(1, source.count(needle))
        source = source.replace('global svc_transform_rows\n', 'global svc_transform_rows\nextern transform_negative_hits\n', 1)
        source = source.replace('svc_transform_rows:\n', 'svc_transform_rows:\n    inc qword [rel transform_negative_hits]\n', 1)
        source = source.replace(needle, needle+'    add edx,4\n', 1)
        control = self.directory / 'control'
        control.mkdir()
        sampler = control / 'wrong-sampler.asm'
        sampler.write_text(source, encoding='utf-8')
        for mode in ('debug', 'release'):
            value, _ = self.native(mode, control / mode, sampler)
            self.assertEqual(1, value.returncode, value.stdout + value.stderr)
            self.assertIn('TRANSFORM_NEGATIVE_HIT ', value.stderr)
            self.assertIn('memcmp(actual,expected,sizeof actual)==0', value.stderr)
            self.assertNotIn('panic', value.stderr)


if __name__ == '__main__':
    unittest.main()
