"""Live PTE publication, synchronous invalidation and delayed table recycling."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent


class ActivePagingTests(unittest.TestCase):
    def compile(self, mode):
        return compile_file(FIXTURES / 'active_paging_probe.dg',
                            roots=[FIXTURES, ROOT / 'kernel', ROOT / 'lang/std'], mode=mode)

    def test_live_layout_atomic_publication_and_both_formats(self):
        compiled = self.compile('debug')
        layouts = {item['full_name']: item for item in compiled.layout_manifest['types']}
        stats = layouts['mm.active_paging.Stats']
        self.assertEqual((24, 8), (stats['size'], stats['alignment']))
        self.assertEqual([0, 8, 16], [item['offset'] for item in stats['fields']])
        self.assertEqual(4096, layouts['mm.paging.Table']['alignment'])
        self.assertNotRegex(compiled.assembly.lower(), r'\b(?:xmm|ymm|zmm)[0-9]+\b')
        nasm = tool('nasm', 'NASM')
        if not nasm:
            self.skipTest('live paging encoding requires NASM')
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in ('debug', 'release'):
                assembly = self.compile(mode).assembly
                # These are the actual language atomic intrinsics, not wrappers
                # that a native fixture could silently replace with no-ops.
                self.assertIn('lock cmpxchg qword [r11], r10', assembly)
                self.assertIn('xchg qword [r11], rax', assembly)
                source = directory / (mode + '.asm')
                source.write_text(assembly, encoding='utf-8')
                for format_ in ('elf64', 'win64'):
                    with self.subTest(mode=mode, format=format_):
                        result = subprocess.run([nasm, '-f', format_, *nasm_flags(nasm),
                                                 '-o', str(directory / (mode + format_ + '.o')),
                                                 str(source)], capture_output=True, text=True, timeout=30)
                        self.assertEqual(0, result.returncode, result.stderr)

    def test_native_raw_ordering_quarantine_reuse_ad_and_failures(self):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not nasm or not cc:
            self.skipTest('live paging native checks require NASM and GCC')
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in ('debug', 'release'):
                with self.subTest(mode=mode):
                    source, obj = directory / (mode + '.asm'), directory / (mode + '.o')
                    executable = directory / (mode + ('.exe' if os.name == 'nt' else ''))
                    source.write_text(self.compile(mode).assembly, encoding='utf-8')
                    result = subprocess.run([nasm, '-f', 'win64' if os.name == 'nt' else 'elf64',
                                             *nasm_flags(nasm), '-o', str(obj), str(source)],
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, result.returncode, result.stderr)
                    # TDM GCC 9 otherwise ICEs while saving Win64 XMM registers
                    # around mixed SysV calls. This integer-only oracle does not
                    # need SIMD; generated Dong code is separately checked above.
                    flags = ['-mno-sse'] if os.name == 'nt' else ['-no-pie', '-pthread']
                    result = subprocess.run([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                                             *flags, str(FIXTURES / 'active_paging_probe.c'), str(obj),
                                             '-o', str(executable)], capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=45)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn('live paging ordering/quarantine/reuse/atomicity checks passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
