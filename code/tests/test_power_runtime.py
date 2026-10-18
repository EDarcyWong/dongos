"""Formal ACPI capture and exact Q35 I/O model; production I/O is never run.

The ACPI inputs are pinned local fixtures, not live or downloaded firmware data.
"""
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
from tests.power_acpi_fixture import fixture_inputs, load_fixture


class PowerRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/power-runtime/host' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [ROOT / name for name in ('kernel/firmware/power_runtime.dg',
            'kernel/firmware/power_io.asm', 'kernel/firmware/power.dg',
            'kernel/firmware/acpi.dg', 'kernel/firmware/acpi_errors.dg',
            'tests/p8_power_runtime_probe.dg', 'tests/power_runtime_probe.c',
            'tests/test_input.py')]
        cls.inputs += [Path(__file__), *fixture_inputs()]
        cls.before = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-before.json').write_text(json.dumps(cls.before, indent=2)+'\n', encoding='utf-8')
        cls.evidence = {}

    @classmethod
    def tearDownClass(cls):
        after = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory / 'source-after.json').write_text(json.dumps(after, indent=2)+'\n', encoding='utf-8')
        if after != cls.before:
            raise AssertionError('formal power runtime inputs changed during verification')
        complete = {'actual_reader_and_hardware_model', 'formats_and_stack'}.issubset(cls.evidence)
        (cls.directory / 'validation-summary.json').write_text(json.dumps(dict(formal_kernel_sources=True,
            actual_hardware_io_executed=False, guest_executed=False, full_build_executed=False,
            source_unchanged=True, source_sha256=after, required_evidence_complete=complete,
            evidence=cls.evidence), indent=2)+'\n', encoding='utf-8')
        print('POWER_RUNTIME_EVIDENCE ' + str(cls.directory))

    def compile(self, mode):
        return compile_file(ROOT / 'tests/p8_power_runtime_probe.dg', mode=mode,
                            roots=[ROOT / 'tests', ROOT / 'kernel'])

    def test_native_capture_and_exact_hardware_model(self):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'NASM and GCC are required')
        manifest, files = load_fixture()
        outcomes = {}
        for mode in ('debug', 'release'):
            output = self.directory / 'native' / mode;output.mkdir(parents=True)
            compiled = self.compile(mode);assembly = output / 'probe.asm';assembly.write_text(compiled.assembly, encoding='utf-8')
            fmt = 'win64' if os.name == 'nt' else 'elf64'
            objects = []
            for source, name, defines in ((assembly, 'probe.o', []), (ROOT / 'kernel/firmware/power_io.asm', 'io-model.o', ['-DPOWER_MODEL=1'])):
                obj = output / name;objects.append(obj)
                command([nasm, '-f', fmt, *nasm_flags(nasm), *defines, '-o', obj, source], output, name)
            binary = output / ('probe.exe' if os.name == 'nt' else 'probe')
            flags = ['-mno-sse'] if os.name == 'nt' else ['-no-pie']
            command([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-D__USE_MINGW_ANSI_STDIO=1', *flags,
                     ROOT / 'tests/power_runtime_probe.c', *objects, '-o', binary], output, 'link')
            value = command([binary, files['FACP'], files['DSDT']], output, 'native', success=False)
            self.assertEqual(0, value.returncode, value.stdout+value.stderr)
            self.assertIn('exact-I/O-order IF-restore AC-clear no-retained-borrows no-SMI no-MMIO', value.stdout)
            sizes = {t['full_name']: t['size'] for t in compiled.layout_manifest['types']}
            self.assertEqual(184, sizes['firmware.power_runtime.Prepared'])
            outcomes[mode] = value.stdout.strip()
        self.evidence['actual_reader_and_hardware_model'] = dict(source=manifest['saved'], outcomes=outcomes)

    def test_production_assembly_formats_and_direct_call_stack(self):
        nasm = tool('nasm', 'NASM');self.assertTrue(nasm, 'NASM is required')
        outcomes = {}
        for mode in ('debug', 'release'):
            output = self.directory / 'formats' / mode;output.mkdir(parents=True)
            compiled = self.compile(mode);assembly = output / 'probe.asm';assembly.write_text(compiled.assembly, encoding='utf-8')
            functions, current = {}, None
            for line in compiled.assembly.splitlines():
                match = re.match(r'^\$([A-Za-z_][A-Za-z0-9_]*):$', line)
                if match: current = match[1];functions[current] = dict(frame=16, calls=set())
                if current:
                    match = re.search(r'\bsub rsp, (\d+)', line)
                    if match: functions[current]['frame'] += int(match[1])
                    match = re.search(r'\bcall \$([A-Za-z_][A-Za-z0-9_]*)\b', line)
                    if match: functions[current]['calls'].add(match[1])
            def stack(name, path=()):
                self.assertNotIn(name, path)
                value = functions[name]
                return value['frame'] + max([stack(c, (*path, name)) for c in value['calls'] if c in functions] or [0])
            maximum = max(map(stack, functions));self.assertLessEqual(maximum, 8192)
            for fmt in ('elf64', 'win64'):
                for source, name in ((assembly, 'collector'), (ROOT / 'kernel/firmware/power_io.asm', 'production-io')):
                    command([nasm, '-f', fmt, *nasm_flags(nasm), '-o', output / (name+'-'+fmt+'.o'), source], output, name+'-'+fmt)
            outcomes[mode] = dict(generated_direct_call_stack_bytes=maximum,
                                  external_reader_and_panic_stack_included=False,
                                  production_io_assembled_not_executed=True,
                                  formats=['elf64', 'win64'])
        self.evidence['formats_and_stack'] = outcomes


if __name__ == '__main__': unittest.main()
