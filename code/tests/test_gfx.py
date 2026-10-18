"""Freestanding Dong graphics; actual native whole-buffer C pixel models."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]


class GraphicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/gfx' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [*sorted((ROOT / 'services/gfx').glob('*.dg')),
                      ROOT / 'tests/gfx_probe.dg', ROOT / 'tests/gfx_probe.c', Path(__file__)]
        cls.before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-before.json').write_text(json.dumps(cls.before, indent=2))
        cls.compiled = {}

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-after.json').write_text(json.dumps(after, indent=2))
        if after != cls.before:
            raise AssertionError('graphics sources changed during native verification')

    def compiled_mode(self, mode):
        if mode not in self.compiled:
            self.compiled[mode] = compile_file(ROOT / 'tests/gfx_probe.dg', roots=[ROOT / 'tests', ROOT / 'services'], mode=mode)
        return self.compiled[mode]

    def command(self, args, directory, name, *, success=True):
        start = time.monotonic()
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=60)
        (directory / (name + '.json')).write_text(json.dumps(dict(command=[str(a) for a in args],
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
            elapsed_seconds=round(time.monotonic() - start, 6)), indent=2), encoding='utf-8')
        if success:
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return result

    def test_public_layout_and_both_assembly_formats(self):
        nasm = tool('nasm', 'NASM')
        if not nasm:
            self.skipTest('graphics format oracle requires NASM')
        for mode in ('debug', 'release'):
            compiled = self.compiled_mode(mode)
            types = {t['full_name']: t for t in compiled.layout_manifest['types']}
            for name, size in (('gfx.geometry.Rect', 32), ('gfx.geometry.Damage', 560),
                               ('gfx.raster.Surface', 40), ('gfx.compositor.Window', 80),
                               ('gfx.atlas.Atlas', 72), ('gfx.atlas.Glyph', 64)):
                self.assertEqual((size, 8), (types[name]['size'], types[name]['alignment']))
            self.assertNotRegex(compiled.assembly.lower(), r'\b(?:xmm|ymm|zmm)[0-9]+\b')
            directory = self.directory / 'formats' / mode
            directory.mkdir(parents=True)
            asm = directory / 'probe.asm'
            asm.write_text(compiled.assembly, encoding='utf-8')
            (directory / 'layout.json').write_text(json.dumps(compiled.layout_manifest, indent=2))
            for fmt in ('elf64', 'win64'):
                self.command([nasm, '-f', fmt, *nasm_flags(nasm), '-o', str(directory / (fmt + '.o')), str(asm)], directory, fmt)

    def test_native_independent_pixels_guards_text_and_failure_snapshots(self):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not nasm or not cc:
            self.skipTest('graphics native oracle requires NASM and SysV-capable GCC')
        for mode in ('debug', 'release'):
            directory = self.directory / 'native' / mode
            directory.mkdir(parents=True)
            asm, obj = directory / 'probe.asm', directory / 'probe.o'
            asm.write_text(self.compiled_mode(mode).assembly, encoding='utf-8')
            self.command([nasm, '-f', 'win64' if os.name == 'nt' else 'elf64', *nasm_flags(nasm), '-o', str(obj), str(asm)], directory, 'assemble')
            binary = directory / ('probe.exe' if os.name == 'nt' else 'probe')
            flags = ['-mno-sse'] if os.name == 'nt' else ['-no-pie']
            self.command([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-D__USE_MINGW_ANSI_STDIO=1', *flags,
                          str(ROOT / 'tests/gfx_probe.c'), str(obj), '-o', str(binary)], directory, 'link')
            result = self.command([str(binary)], directory, 'native')
            self.assertRegex(result.stdout, r'fills=1000 blits=1000 masks=1000 compositions=100 .*rejected=\d+ full-buffer-guards=ok')

    def test_original_pixel_stride_and_text_atomicity_controls_are_rejected(self):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not nasm or not cc:
            self.skipTest('graphics negative oracle requires NASM and SysV-capable GCC')
        controls = (
            ('stride', 'raster.dg', '(*dst).pixels[y * (*dst).stride + x] = color;',
             'negative_hit(1); (*dst).pixels[y * (*dst).width + x] = color;', 1),
            ('text-atomicity', 'atlas.dg', 'try walk(dst,atlas,text,x,baseline,color,false,&measured);',
             'if text.len == 3 && text[1] == 0xc0 { negative_hit(2); }', 2))
        for label, filename, needle, replacement, kind in controls:
            staging = self.directory / 'controls' / label / 'services'
            shutil.copytree(ROOT / 'services/gfx', staging / 'gfx')
            source = (staging / 'gfx' / filename).read_text(encoding='utf-8')
            self.assertEqual(1, source.count(needle))
            module = 'gfx.' + filename.removesuffix('.dg')
            source = source.replace(needle, replacement).replace('module ' + module + ';',
                'module ' + module + ';\nunsafe extern "sysv64" ("gfx_negative_hit") fn negative_hit(kind: u64) void;', 1)
            (staging / 'gfx' / filename).write_text(source, encoding='utf-8')
            for mode in ('debug', 'release'):
                directory = staging.parent / mode
                directory.mkdir()
                compiled = compile_file(ROOT / 'tests/gfx_probe.dg', roots=[ROOT / 'tests', staging], mode=mode)
                asm, obj = directory / 'probe.asm', directory / 'probe.o'
                asm.write_text(compiled.assembly, encoding='utf-8')
                self.command([nasm, '-f', 'win64' if os.name == 'nt' else 'elf64', *nasm_flags(nasm), '-o', str(obj), str(asm)], directory, 'assemble')
                binary = directory / ('probe.exe' if os.name == 'nt' else 'probe')
                flags = ['-mno-sse'] if os.name == 'nt' else ['-no-pie']
                self.command([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-D__USE_MINGW_ANSI_STDIO=1', *flags,
                              str(ROOT / 'tests/gfx_probe.c'), str(obj), '-o', str(binary)], directory, 'link')
                result = self.command([str(binary)], directory, 'native', success=False)
                self.assertNotEqual(0, result.returncode, 'actual broken renderer passed the pixel oracle')
                self.assertEqual(1, result.stderr.count('GFX_NEGATIVE_HIT ' + str(kind)))
                self.assertIn('memcmp', result.stderr)


if __name__ == '__main__':
    unittest.main()
