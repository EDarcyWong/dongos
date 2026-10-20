"""Faulting-DMA release through the production user.memory path.

A private copy of kernel/user/memory.dg gets a test-only fixture appended; the
production release_dma/destroy code above it is unchanged. The probe maps four
owned frames, fills them with 0xA5, releases the pinned contiguous range after
the caller-side fault checks, and requires every page to be zeroed and reusable
before destroy can retire the process. Real wrong Dong sources must be rejected
by the same checks. No OS/VM is started.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('kernel/user/memory.dg', 'kernel/boot/memory_startup.dg',
         'tests/dma_release_fixture.dg', 'tests/dma_release_startup.dg',
         'tests/dma_release_probe.c', 'tests/test_dma_release.py')


class DmaReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest('native DMA release checks require NASM and GCC')
        cls.dir = Path(tempfile.mkdtemp(prefix='dma-release-'))
        cls.before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in NAMES}

    @classmethod
    def tearDownClass(cls):
        after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in NAMES}
        assert after == cls.before, 'DMA release inputs changed during the test'
        shutil.rmtree(cls.dir, ignore_errors=True)

    def command(self, args, d, name):
        r = subprocess.run(list(map(str, args)), cwd=ROOT, capture_output=True, text=True, timeout=120)
        (d / (name + '.json')).write_text(
            __import__('json').dumps(dict(command=list(map(str, args)), returncode=r.returncode,
                                          stdout=r.stdout, stderr=r.stderr), indent=2) + '\n')
        return r

    def build_and_run(self, label, mode, mutate=None):
        d = self.dir / (label + '-' + mode)
        d.mkdir()
        kernel = d / 'kernel'
        for original in (ROOT / 'kernel').rglob('*.dg'):
            target = kernel / original.relative_to(ROOT / 'kernel')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original.read_bytes())
        memory = kernel / 'user/memory.dg'
        source = memory.read_text(encoding='utf-8')
        if mutate:
            self.assertEqual(source.count(mutate[0]), 1, label)
            source = source.replace(mutate[0], mutate[1], 1)
        memory.write_text(source + '\n' + (ROOT / 'tests/dma_release_fixture.dg').read_text(encoding='utf-8'),
                          encoding='utf-8')
        startup = kernel / 'boot/memory_startup.dg'
        startup.write_text(startup.read_text(encoding='utf-8') + '\n'
                           + (ROOT / 'tests/dma_release_startup.dg').read_text(encoding='utf-8'),
                           encoding='utf-8')
        compiled = compile_file(memory, roots=[kernel, ROOT / 'services', ROOT / 'lang/std', ROOT / 'lang/examples'],
                                mode=mode)
        asm = d / 'probe.asm'
        asm.write_text(compiled.assembly, encoding='utf-8')
        mocked = {'__dong_panic', 'user_current_root', 'user_pcid_flush_all', 'user_pcid_unbind',
                  'runtime_invalidate', 'runtime_copy_bytes', 'user_pcid_invalidate_root'}
        externs = {m.group(1).lstrip('$') for m in re.finditer(r'^extern (\$?\w+)', compiled.assembly, re.M)} - mocked
        stub = d / 'unused.asm'
        stub.write_text('bits 64\nsection .text\n' + ''.join('global $' + x + '\n$' + x + ': ud2\n' for x in sorted(externs)))
        objects = []
        for name, source_path in (('probe', asm), ('unused', stub)):
            obj = d / (name + '.o')
            r = self.command([self.nasm, '-f', 'win64' if os.name == 'nt' else 'elf64', *nasm_flags(self.nasm),
                              '-o', obj, source_path], d, 'assemble-' + name)
            self.assertEqual(0, r.returncode, r.stderr)
            objects.append(obj)
        exe = d / ('probe.exe' if os.name == 'nt' else 'probe')
        r = self.command([self.cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                          *( [] if os.name == 'nt' else ['-no-pie']),
                          ROOT / 'tests/dma_release_probe.c', *objects, '-o', exe], d, 'link')
        self.assertEqual(0, r.returncode, r.stderr)
        r = self.command([exe], d, 'execute')
        return r

    def test_release_zeroes_and_recycles_before_destroy(self):
        for mode in ('debug', 'release'):
            with self.subTest(mode=mode):
                r = self.build_and_run('good', mode)
                self.assertEqual(0, r.returncode, r.stdout + r.stderr)
                self.assertIn('dma release checks passed', r.stdout)

    def test_wrong_release_implementations_are_rejected(self):
        mutants = [
            ('keeps-pin', ('PINNED[id]=false;', 'PINNED[id]=true;')),
            ('drops-range-before-withdraw', ('let base=PINNED_BASE[id];let pages=PINNED_PAGES[id];', 'let base:u64=0;let pages:usize=0;')),
        ]
        for name, mutation in mutants:
            for mode in ('debug', 'release'):
                with self.subTest(mutant=name, mode=mode):
                    r = self.build_and_run(name, mode, mutation)
                    self.assertEqual(1, r.returncode, r.stdout + r.stderr)
                    self.assertIn('dma release check failed line', r.stderr)


if __name__ == '__main__':
    unittest.main()
