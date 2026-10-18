"""Native independent VirtIO tablet MMIO, split-ring DMA and input oracle."""
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


class VirtioTabletTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/virtio-tablet/host' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [*sorted((ROOT / 'services/drivers').glob('*.dg')),
                      *sorted((ROOT / 'services/input').glob('*.dg')),
                      ROOT / 'tests/tablet_probe.dg', ROOT / 'tests/tablet_probe.c', Path(__file__)]
        cls.before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-before.json').write_text(json.dumps(cls.before, indent=2) + '\n', encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-after.json').write_text(json.dumps(after, indent=2) + '\n', encoding='utf-8')
        if after != cls.before:
            raise AssertionError('tablet/dependency sources changed during verification')

    def executable(self, mode, directory, services=None):
        # The shared native helper also performs one initial run; this probe
        # requires a scenario, so compile with the same recorded tool chain.
        import os
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not nasm or not cc:
            self.skipTest('tablet oracle requires NASM and SysV GCC')
        directory.mkdir(parents=True)
        compiled = compile_file(ROOT / 'tests/tablet_probe.dg',
                                roots=[ROOT / 'tests', services or ROOT / 'services'], mode=mode)
        (directory / 'layout.json').write_text(json.dumps(compiled.layout_manifest, indent=2), encoding='utf-8')
        asm, obj = directory / 'probe.asm', directory / 'probe.o'
        asm.write_text(compiled.assembly, encoding='utf-8')
        command([nasm, '-f', 'win64' if os.name == 'nt' else 'elf64', *nasm_flags(nasm), '-o', obj, asm], directory, 'assemble')
        executable = directory / ('probe.exe' if os.name == 'nt' else 'probe')
        command([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-D__USE_MINGW_ANSI_STDIO=1',
                 *(['-mno-sse'] if os.name == 'nt' else ['-no-pie']), ROOT / 'tests/tablet_probe.c', obj,
                 '-o', executable], directory, 'link')
        return executable, compiled

    def test_native_dma_abs_button_failstop_and_actual_16bit_wrap(self):
        for mode in ('debug', 'release'):
            directory = self.directory / 'normal' / mode
            executable, _ = self.executable(mode, directory)
            for scenario in range(14):
                with self.subTest(mode=mode, scenario=scenario):
                    value = command([executable, str(scenario)], directory, 'scenario-' + str(scenario), success=False)
                    self.assertEqual(0, value.returncode, value.stdout + value.stderr)
                    self.assertNotIn('panic', value.stderr)
                    if scenario == 0:
                        self.assertIn('frames=4 real DMA queues=2 full-byte-guards=ok', value.stdout)
                    elif scenario == 13:
                        self.assertIn('wire=65540 polls=1025 completed=65540 used=4 avail=68', value.stdout)
                    elif scenario <= 4 or scenario == 12:
                        self.assertIn('safely retained DMA', value.stdout)
                    else:
                        self.assertIn('failure retained ownership', value.stdout)

    def test_layout_stack_and_both_object_formats(self):
        nasm = tool('nasm', 'NASM')
        if not nasm:
            self.skipTest('NASM unavailable')
        for mode in ('debug', 'release'):
            compiled = compile_file(ROOT / 'tests/tablet_probe.dg', roots=[ROOT / 'tests', ROOT / 'services'], mode=mode)
            types = {t['full_name']: t for t in compiled.layout_manifest['types']}
            for name, size in (('drivers.virtio_pci.Transport', 136), ('drivers.virtio_blk.Lease', 32),
                               ('drivers.virtio_blk.Ops', 40), ('input.events.Event', 32), ('input.events.Queue', 2064)):
                self.assertEqual(size, types[name]['size'])
            state = types['drivers.virtio_tablet.State']
            self.assertEqual(8, state['alignment'])
            self.assertLessEqual(state['size'], 4096)
            self.assertNotRegex(compiled.assembly.lower(), r'\b(?:xmm|ymm|zmm)[0-9]+\b')
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
            (directory / 'stack.json').write_text(json.dumps(dict(generated_direct_call_path_bytes=maximum,
                callbacks_external=True, state_bytes=state['size'])) + '\n', encoding='utf-8')
            asm = directory / 'probe.asm'
            asm.write_text(compiled.assembly, encoding='utf-8')
            for fmt in ('elf64', 'win64'):
                command([nasm, '-f', fmt, *nasm_flags(nasm), '-o', directory / (fmt + '.o'), asm], directory, fmt)

    def test_duplicate_id_bad_implementation_actually_rejected(self):
        source = (ROOT / 'services/drivers/virtio_tablet.dg').read_text(encoding='utf-8')
        needle = 'if id>=SIZE || length!=8 || (seen&(1<<id))!=0 { return error.Completion; }'
        self.assertEqual(1, source.count(needle))
        services = self.directory / 'control' / 'services'
        for name in ('drivers', 'input'):
            shutil.copytree(ROOT / 'services' / name, services / name)
        replacement = 'if id<SIZE && (seen&(1<<id))!=0 { negative_hit(1); }\n            if id>=SIZE || length!=8 { return error.Completion; }'
        source = source.replace(needle, replacement).replace('module drivers.virtio_tablet;',
            'module drivers.virtio_tablet;\nunsafe extern "sysv64" ("tablet_negative_hit") fn negative_hit(kind:u64) void;', 1)
        (services / 'drivers/virtio_tablet.dg').write_text(source, encoding='utf-8')
        for mode in ('debug', 'release'):
            directory = services.parent / mode
            executable, _ = self.executable(mode, directory, services)
            value = command([executable, '1'], directory, 'negative', success=False)
            self.assertEqual(1, value.returncode, value.stdout + value.stderr)
            self.assertEqual(1, value.stderr.count('TABLET_NEGATIVE_HIT 1'), value.stderr)
            self.assertIn('TABLET_MODEL_ASSERT', value.stderr)
            self.assertNotIn('panic', value.stderr)


if __name__ == '__main__':
    unittest.main()
