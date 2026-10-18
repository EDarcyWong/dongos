"""Real current DG sampler oracle, forced SSE2 and independently gated AVX2."""
from pathlib import Path
import hashlib
import json
import os
import re
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
from tests.test_input import command

FEATURE_RENAMES = ['-D_start=feature_test_start', '-D__dong_panic=feature_test_panic',
    '-Dsvc_avx2=feature_test_avx2', '-Dsvc_gather_fast=feature_test_gather_fast',
    '-Dsvc_graphics_features=feature_test_graphics_features']

class TransformAvx2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/desktop-transform-avx2/host' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [ROOT / name for name in ('services/desktop/transform.dg', 'services/gfx/transform.asm', 'services/lib/syscalls.asm',
            'services/gfx/accelerated.asm', 'services/gfx/raster.dg', 'services/gfx/geometry.dg', 'services/gfx/errors.dg',
            'tests/transform_probe.dg', 'tests/transform_probe.c', 'tests/transform_register_fixture.asm',
            'tests/transform_avx2_probe.c', 'tests/transform_host_features.asm', 'tests/test_desktop_transform_avx2.py')]
        cls.before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        cls.results, cls.binaries = {}, {}

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        if cls.before != after:
            raise AssertionError('candidate or formal oracle changed during native verification')
        (cls.directory / 'validation-summary.json').write_text(json.dumps(dict(source_sha256=after,
            sources_unchanged=True, formal_native_suite=True, actual_qemu_executed=False,
            evidence=cls.results), indent=2) + '\n', encoding='utf-8')

    def build(self, mode, label='normal', sampler=None, features=None):
        key = (mode, label)
        if key in self.binaries:
            return self.binaries[key]
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not nasm or not cc:
            self.skipTest('real native sampler oracle requires NASM/GCC')
        directory = self.directory / label / mode
        directory.mkdir(parents=True)
        compiled = compile_file(ROOT / 'tests/transform_probe.dg', roots=[ROOT / 'tests', ROOT / 'services'], mode=mode)
        types = {t['full_name']: t for t in compiled.layout_manifest['types']}
        self.assertEqual(104, types['desktop.transform.Command']['size'])
        assembly = directory / 'probe.asm'
        assembly.write_text(compiled.assembly, encoding='utf-8')
        sources = (assembly, sampler or ROOT / 'services/gfx/transform.asm', ROOT / 'tests/transform_register_fixture.asm',
                   ROOT / 'services/gfx/accelerated.asm', ROOT / 'tests/transform_host_features.asm',
                   features or ROOT / 'services/lib/syscalls.asm')
        objects = []
        for i, source in enumerate(sources):
            obj = directory / f'input-{i}.o'
            command([nasm, '-DTRANSFORM_PROBE=1', '-f', 'win64' if os.name == 'nt' else 'elf64',
                     *nasm_flags(nasm), *(FEATURE_RENAMES if i == 5 else []), '-o', obj, source], directory, f'assemble-{i}')
            objects.append(obj)
        binary = directory / ('probe.exe' if os.name == 'nt' else 'probe')
        flags = ['-mno-sse'] if os.name == 'nt' else ['-no-pie', '-D_DEFAULT_SOURCE']
        command([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation',
                 '-D__USE_MINGW_ANSI_STDIO=1', *flags, ROOT / 'tests/transform_avx2_probe.c', *objects, '-o', binary], directory, 'link')
        self.binaries[key] = binary, directory, compiled
        return self.binaries[key]

    def run_branch(self, mode, flag, label='normal', sampler=None, gather=None):
        binary, directory, compiled = self.build(mode, label, sampler)
        args = [binary, str(flag)] + ([str(gather)] if gather is not None else [])
        result = command(args, directory, 'native-flags-' + str(flag) + '-' + str(gather), success=False)
        return result, compiled

    def test_forced_zero_uses_only_real_sse2_oracle(self):
        modes = {}
        for mode in ('debug', 'release'):
            branches = {}
            for avx, gather in ((0, 0), (0, 1), (1, 0), (2, 1), (1, 2)):
                value, _ = self.run_branch(mode, avx, gather=gather)
                self.assertEqual(0, value.returncode, value.stdout + value.stderr)
                self.assertIn('cases=1335 partitioned=1329 atomic-invalid=20', value.stdout)
                self.assertIn(f'forced-flag={avx} gather-flag={gather}', value.stdout)
                self.assertRegex(value.stdout, r'sse2=[1-9][0-9]* gather8=0 opaque8=0 partial8=0 tail4=0 scalar=0')
                branches[f'{avx},{gather}'] = value.stdout.strip()
            modes[mode] = branches
        self.results['forced_sse2'] = modes

    def test_gated_one_really_executes_gather_opacity_opaque_tails_and_vzeroupper(self):
        modes = {}
        for mode in ('debug', 'release'):
            value, _ = self.run_branch(mode, 1)
            if value.returncode == 77:
                self.results['gated_avx2'] = dict(status='unsupported', actual_avx2_tested=False, output=value.stdout.strip())
                self.skipTest('host CPUID/XCR0 does not support AVX2; no AVX2 pass claimed')
            self.assertEqual(0, value.returncode, value.stdout + value.stderr)
            self.assertIn('cases=1335 partitioned=1329 atomic-invalid=20', value.stdout)
            self.assertIn('host-gate=1 forced-flag=1 gather-flag=1 sse2=0', value.stdout)
            for field in ('gather8', 'opaque8', 'partial8', 'tail4', 'scalar'):
                self.assertRegex(value.stdout, field + r'=[1-9][0-9]*')
            self.assertIn('guarded-map-source-destination=ok vzeroupper=observed', value.stdout)
            modes[mode] = value.stdout.strip()
        self.results['gated_avx2'] = dict(status='passed', actual_avx2_tested=True, modes=modes)

    def test_formats_and_generated_stack_bound(self):
        nasm = tool('nasm', 'NASM')
        if not nasm:
            self.skipTest('NASM unavailable')
        results = {}
        for mode in ('debug', 'release'):
            compiled = compile_file(ROOT / 'tests/transform_probe.dg', roots=[ROOT / 'tests', ROOT / 'services'], mode=mode)
            directory = self.directory / 'formats' / mode
            directory.mkdir(parents=True)
            assembly = directory / 'probe.asm'
            assembly.write_text(compiled.assembly, encoding='utf-8')
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
                return item['frame'] + max([stack(c, (*path, name)) for c in item['calls'] if c in functions] or [0])
            maximum = max(map(stack, functions)) + 56  # six pushes + native return
            self.assertLessEqual(maximum, 4096)
            sources = (assembly, ROOT / 'services/gfx/transform.asm', ROOT / 'tests/transform_register_fixture.asm',
                       ROOT / 'services/gfx/accelerated.asm', ROOT / 'tests/transform_host_features.asm', ROOT / 'services/lib/syscalls.asm')
            for fmt in ('elf64', 'win64'):
                for i, source in enumerate(sources):
                    command([nasm, '-DTRANSFORM_PROBE=1', '-f', fmt, *nasm_flags(nasm),
                        *(FEATURE_RENAMES if i == 5 else []),
                        '-o', directory / f'{fmt}-{i}.o', source], directory, f'{fmt}-{i}')
            results[mode] = dict(generated_plus_native_stack_bytes=maximum, formats=['elf64', 'win64'])
        self.results['formats_and_stack'] = results

    def test_actual_wrong_gather_is_executed_and_rejected_by_existing_pixel_oracle(self):
        source = (ROOT / 'services/gfx/transform.asm').read_text(encoding='utf-8')
        needle = '    vpmovzxwd ymm12,oword [rsi]\n'
        self.assertEqual(1, source.count(needle))
        source = source.replace('extern svc_avx2\n', 'extern svc_avx2\nextern transform_negative_hits\n', 1)
        source = source.replace(needle, needle + '    inc qword [rel transform_negative_hits]\n    vpaddd ymm12,ymm12,[rel bad_offset]\n', 1)
        source = source.replace('transform_255: times 8 dw 255', 'bad_offset: times 8 dd 4\ntransform_255: times 8 dw 255', 1)
        control = self.directory / 'bad-gather'
        control.mkdir()
        sampler = control / 'sampler.asm'
        sampler.write_text(source, encoding='utf-8')
        modes = {}
        for mode in ('debug', 'release'):
            sse, _ = self.run_branch(mode, 0, 'bad-gather', sampler)
            self.assertEqual(0, sse.returncode, sse.stdout + sse.stderr)
            value, _ = self.run_branch(mode, 1, 'bad-gather', sampler)
            if value.returncode == 77:
                self.results['bad_gather'] = dict(status='unsupported', actual_avx2_tested=False)
                self.skipTest('host cannot execute AVX2 bad-gather control')
            self.assertEqual(1, value.returncode, value.stdout + value.stderr)
            self.assertIn('TRANSFORM_NEGATIVE_HIT ', value.stderr)
            self.assertIn('memcmp(actual,expected,sizeof actual)==0', value.stderr)
            self.assertNotIn('panic', value.stderr)
            modes[mode] = dict(exit=1, stderr=value.stderr.strip(), forced_sse2_still_passed=True)
        self.results['bad_gather'] = dict(status='rejected', modes=modes)

    def test_actual_vendor_policy_exact_tcg_and_real_corrupt_predicate(self):
        source = (ROOT / 'services/lib/syscalls.asm').read_text(encoding='utf-8')
        needle = '    cmp esi,0x43544743\n'
        self.assertEqual(1, source.count(needle))
        source = source.replace('global svc_gather_vendor_fast\n', 'global svc_gather_vendor_fast\nextern vendor_negative_hits\n', 1)
        source = source.replace('svc_gather_vendor_fast:\n', 'svc_gather_vendor_fast:\n    inc qword [rel vendor_negative_hits]\n', 1)
        source = source.replace(needle, '    cmp esi,0x43544742\n', 1)
        control = self.directory / 'bad-vendor'
        control.mkdir()
        bad = control / 'syscalls.asm'
        bad.write_text(source, encoding='utf-8')
        modes = {}
        for mode in ('debug', 'release'):
            binary, directory, _ = self.build(mode)
            good = command([binary, '--vendor'], directory, 'vendor', success=False)
            self.assertEqual(0, good.returncode, good.stdout + good.stderr)
            self.assertIn('vendor oracle passed: cases=3082 exact-TCG-only=ok KVM+VMware+other=enabled', good.stdout)
            binary, directory, _ = self.build(mode, 'bad-vendor', features=bad)
            wrong = command([binary, '--vendor'], directory, 'vendor-negative', success=False)
            self.assertEqual(1, wrong.returncode, wrong.stdout + wrong.stderr)
            self.assertIn('VENDOR_NEGATIVE_HIT 1', wrong.stderr)
            self.assertIn('actual==expected', wrong.stderr)
            modes[mode] = dict(actual_formal_predicate=good.stdout.strip(), bad_vendor_exit=wrong.returncode,
                               bad_vendor_stderr=wrong.stderr.strip())
        self.results['one_time_vendor_policy'] = dict(passed=True, actual_formal_syscalls_asm=True, modes=modes)


if __name__ == '__main__':
    unittest.main()
