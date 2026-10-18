"""Isolated NVMe SQE/PRP/identify bytes and CQ lifetime oracle, no devices."""
from pathlib import Path
import hashlib
import json
import os
import re
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / 'tests'
SERVICES = ROOT / 'services'
OUTPUT = ROOT / 'build/test/nvme-core'
sys.path.insert(0, str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
from tests.test_input import command


class NvmeCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = OUTPUT / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [SERVICES / 'drivers/nvme_core.dg', TESTS / 'nvme_probe.dg',
                      TESTS / 'nvme_probe.c', Path(__file__),
                      *sorted((ROOT / 'lang/dongc').glob('*.py'))]
        cls.before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        cls.results = {}

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        if after != cls.before:
            raise AssertionError('NVMe formal sources, probes or compiler changed during verification')
        print('NVME_CORE_EVIDENCE=' + str(cls.directory))
        (cls.directory / 'validation-summary.json').write_text(json.dumps(dict(
            passed=len(cls.results) == 3, sources_unchanged=True, source_sha256=after,
            actual_device_executed=False, actual_guest_executed=False,
            queue_memory_reclaimed=False, actual_pcie_or_mmio_executed=False,
            evidence=cls.results), indent=2) + '\n', encoding='utf-8')

    def compile(self, mode, source=None):
        return compile_file(TESTS / 'nvme_probe.dg', mode=mode,
                            roots=[TESTS, source or SERVICES])

    def native(self, mode, label, source=None):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'NVMe byte/queue oracle requires NASM and GCC')
        directory = self.directory / label / mode
        directory.mkdir(parents=True)
        compiled = self.compile(mode, source)
        asm = directory / 'probe.asm'
        asm.write_text(compiled.assembly, encoding='utf-8')
        obj = directory / 'probe.o'
        command([nasm, '-f', 'win64' if os.name == 'nt' else 'elf64', *nasm_flags(nasm), '-o', obj, asm], directory, 'assemble')
        binary = directory / ('probe.exe' if os.name == 'nt' else 'probe')
        flags = ['-mno-sse'] if os.name == 'nt' else ['-no-pie']
        command([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-D__USE_MINGW_ANSI_STDIO=1',
                 *flags, TESTS / 'nvme_probe.c', obj, '-o', binary], directory, 'link')
        return command([binary], directory, 'native', success=False), compiled

    def test_independent_full_bytes_identify_prp_and_queue_model(self):
        modes = {}
        for mode in ('debug', 'release'):
            result, compiled = self.native(mode, 'normal')
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn('data-offsets=1024 counts=128 held=permanent hardware-executed=false', result.stdout)
            sizes = {item['full_name']: item['size'] for item in compiled.layout_manifest['types']}
            self.assertEqual(256, sizes['drivers.nvme_core.Plan'])
            self.assertEqual(168, sizes['drivers.nvme_core.Queue'])
            self.assertEqual(48, sizes['drivers.nvme_core.Completion'])
            modes[mode] = dict(returncode=0, output=result.stdout.strip())
        self.results['independent_native_model'] = modes

    def test_elf_coff_pure_code_and_direct_call_stack(self):
        nasm = tool('nasm', 'NASM')
        self.assertTrue(nasm, 'NASM required')
        modes = {}
        for mode in ('debug', 'release'):
            compiled = self.compile(mode)
            self.assertNotRegex(compiled.assembly.lower(), r'\b(?:cpuid|invlpg|rdmsr|wrmsr|cr[0348]|xmm[0-9]+|ymm[0-9]+)\b')
            self.assertNotRegex(compiled.assembly, r'(?m)^section \.(?:bss|data)\b')
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
            (directory / 'layout.json').write_text(json.dumps(compiled.layout_manifest, indent=2) + '\n', encoding='utf-8')
            for fmt in ('elf64', 'win64'):
                command([nasm, '-f', fmt, *nasm_flags(nasm), '-o', directory / (fmt + '.o'), asm], directory, fmt)
            modes[mode] = dict(direct_generated_call_path_bytes=maximum, formats=['elf64', 'win64'], pure_code=True)
        self.results['object_formats_and_stack'] = modes

    def test_actual_bad_protocol_and_admission_controls_are_rejected(self):
        original = (SERVICES / 'drivers/nvme_core.dg').read_text(encoding='utf-8')
        controls = [
            ('nlb', 'put32(p,48,r.sectors-1);', 'put32(p,48,r.sectors);negative_hit(1);', 1),
            ('phase', 'if (status&1)!=(*queue).phase {(*queue).last_ms=now;return false;}',
             'if (status&1)!=(*queue).phase {negative_hit(2);}', 2),
            ('zero-nn', 'let maximum_nsid=u32_at(raw,516);',
             'let maximum_nsid=u32_at(raw,516);if maximum_nsid==0 {negative_hit(3);}', 3),
            ('thin-ns', 'let formats=raw[25] as u64;let format=raw[26] as u64;',
             'let formats=raw[25] as u64;let format=raw[26] as u64;if (raw[24]&1)!=0 {negative_hit(4);}', 4),
        ]
        evidence = {}
        for label, needle, replacement, marker in controls:
            self.assertEqual(1, original.count(needle))
            source = self.directory / 'controls' / label / 'src'
            (source / 'drivers').mkdir(parents=True)
            changed = original.replace(needle, replacement)
            if label == 'zero-nn':
                self.assertEqual(1, changed.count('maximum_nsid==0 || maximum_nsid==0xffff_ffff'))
                changed = changed.replace('maximum_nsid==0 || maximum_nsid==0xffff_ffff', 'maximum_nsid==0xffff_ffff')
            if label == 'thin-ns':
                self.assertEqual(1, changed.count('(raw[24]&0xcb)!=0'))
                changed = changed.replace('(raw[24]&0xcb)!=0', '(raw[24]&0xca)!=0')
            changed = changed.replace('module drivers.nvme_core;',
                'module drivers.nvme_core;\nunsafe extern "sysv64" ("nvme_negative_hit") fn negative_hit(kind:u64)void;', 1)
            (source / 'drivers/nvme_core.dg').write_text(changed, encoding='utf-8')
            modes = {}
            for mode in ('debug', 'release'):
                result, _ = self.native(mode, label, source)
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertEqual(1, result.stderr.count('NVME_NEGATIVE_HIT ' + str(marker)), result.stderr)
                self.assertIn('NVME_MODEL_ASSERT', result.stderr)
                self.assertNotIn('panic', result.stderr.lower())
                modes[mode] = dict(returncode=1, actual_marked_mutation_executed=True, stderr=result.stderr.strip())
            evidence[label] = modes
        self.results['actual_bad_implementations'] = evidence


if __name__ == '__main__':
    unittest.main()
