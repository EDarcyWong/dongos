"""Formal P8 power policy: independent host models and pinned local ACPI data.

No guest is started and no host port/MMIO operation is executed.
"""
from pathlib import Path
import hashlib
import importlib.util
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
from tests.power_acpi_fixture import DIRECTORY, fixture_inputs, load_fixture


class PowerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/power/host' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.sources = [ROOT / name for name in ('kernel/firmware/power.dg',
            'tests/power_probe.dg', 'tests/power_probe.c', 'tests/power_actual_probe.c',
            'tests/aml_reference.py', 'tests/test_input.py')]
        cls.sources += [Path(__file__), *fixture_inputs()]
        cls.before = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.sources}
        (cls.directory / 'source-before.json').write_text(json.dumps(cls.before, indent=2)+'\n', encoding='utf-8')
        cls.results = {}

    @classmethod
    def tearDownClass(cls):
        after = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.sources}
        (cls.directory / 'source-after.json').write_text(json.dumps(after, indent=2)+'\n', encoding='utf-8')
        if after != cls.before:
            raise AssertionError('formal power inputs changed during verification')
        complete = {'actual_ovmf', 'independent_native', 'formats_and_stack',
                    'actual_bad_implementations', 'fixture_pins'}.issubset(cls.results)
        (cls.directory / 'validation-summary.json').write_text(json.dumps(dict(
            source_sha256=after, source_unchanged=True, formal_kernel_sources=True,
            actual_hardware_io_executed=False, guest_executed=False, full_build_executed=False,
            required_evidence_complete=complete, evidence=cls.results), indent=2)+'\n', encoding='utf-8')
        print('POWER_EVIDENCE ' + str(cls.directory))

    def compile(self, mode, source=None):
        return compile_file(ROOT / 'tests/power_probe.dg', mode=mode, roots=[ROOT / 'tests', source or ROOT / 'kernel'])

    def native(self, mode, label, source=None, c_source=None, arguments=()):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not nasm or not cc:
            self.fail('formal power gate requires NASM and SysV-capable GCC')
        directory = self.directory / label / mode
        directory.mkdir(parents=True)
        compiled = self.compile(mode, source)
        assembly = directory / 'probe.asm'
        assembly.write_text(compiled.assembly, encoding='utf-8')
        obj = directory / 'probe.o'
        command([nasm, '-f', 'win64' if os.name == 'nt' else 'elf64', *nasm_flags(nasm), '-o', obj, assembly], directory, 'assemble')
        binary = directory / ('probe.exe' if os.name == 'nt' else 'probe')
        flags = ['-mno-sse'] if os.name == 'nt' else ['-no-pie']
        command([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-D__USE_MINGW_ANSI_STDIO=1', *flags,
                 c_source or ROOT / 'tests/power_probe.c', obj, '-o', binary], directory, 'link')
        return command([binary, *arguments], directory, 'native', success=False), compiled

    def test_pinned_fixture_detects_valid_checksum_tampering_and_metadata_changes(self):
        manifest, files = load_fixture()
        altered = self.directory / 'fixture-control'
        altered.mkdir()
        for path in files.values():
            (altered / path.name).write_bytes(path.read_bytes())
        manifest_path = altered / 'manifest.json'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        self.assertEqual(set(files), set(load_fixture(altered)[1]))
        # Preserve ACPI checksum while changing an OEM byte: the pinned hash,
        # independently of the mutable manifest, must still reject the table.
        path = altered / 'DSDT.bin'
        raw = bytearray(path.read_bytes())
        raw[10] ^= 1
        raw[9] = 0
        raw[9] = (-sum(raw)) & 255
        self.assertEqual(0, sum(raw) & 255)
        path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'fixture bytes changed: DSDT'):
            load_fixture(altered)
        path.write_bytes(files['DSDT'].read_bytes())
        manifest['saved'][0]['sha256'] = '0' * 64
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'fixture metadata changed'):
            load_fixture(altered)
        manifest, _ = load_fixture()
        manifest['capture']['collector_sha256'] = '0' * 64
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'capture provenance changed'):
            load_fixture(altered)
        self.results['fixture_pins'] = dict(valid_checksum_byte_change_rejected=True,
            altered_manifest_hash_rejected=True, altered_collector_provenance_rejected=True,
            fixture_directory=DIRECTORY.relative_to(ROOT).as_posix())

    def test_actual_ovmf_tables_and_injected_namespace_dynamic_rejections(self):
        manifest, files = load_fixture()
        spec = importlib.util.spec_from_file_location('power_aml_reference', ROOT / 'tests/aml_reference.py')
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        parsed = module.StaticAml(files['DSDT'].read_bytes()).parse()
        self.assertEqual(dict(type_a=0, type_b=0, aml_offset=8159), parsed['s5'])
        (self.directory / 'actual-ovmf-structure.json').write_text(json.dumps(parsed, indent=2)+'\n', encoding='utf-8')
        outcomes = {}
        for mode in ('debug', 'release'):
            value, _ = self.native(mode, 'actual-ovmf', c_source=ROOT / 'tests/power_actual_probe.c',
                                   arguments=(files['FACP'], files['DSDT']))
            self.assertEqual(0, value.returncode, value.stdout+value.stderr)
            self.assertIn('actual-root-field-region-dynamic-rejections=5', value.stdout)
            outcomes[mode] = value.stdout.strip()
        self.results['actual_ovmf'] = dict(source=manifest['saved'], independent_structure=parsed['s5'], native=outcomes)

    def test_independent_gas_model_aml_boundaries_and_atomic_output(self):
        outcomes = {}
        for mode in ('debug', 'release'):
            value, compiled = self.native(mode, 'normal')
            self.assertEqual(0, value.returncode, value.stdout + value.stderr)
            self.assertIn('all-guards=ok', value.stdout)
            sizes = {t['full_name']: t['size'] for t in compiled.layout_manifest['types']}
            self.assertEqual(120, sizes['firmware.power.Shutdown'])
            outcomes[mode] = value.stdout.strip()
        self.results['independent_native'] = outcomes

    def test_elf_coff_and_direct_call_stack(self):
        nasm = tool('nasm', 'NASM')
        if not nasm:
            self.fail('NASM required for the formal power format gate')
        outcomes = {}
        for mode in ('debug', 'release'):
            compiled = self.compile(mode)
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
                value = functions[name]
                return value['frame'] + max([stack(c, (*path, name)) for c in value['calls'] if c in functions] or [0])
            maximum = max(map(stack, functions))
            self.assertLessEqual(maximum, 4096)
            for fmt in ('elf64', 'win64'):
                command([nasm, '-f', fmt, *nasm_flags(nasm), '-o', directory / (fmt + '.o'), assembly], directory, fmt)
            outcomes[mode] = dict(generated_direct_call_stack_bytes=maximum,
                external_panic_stack_included=False, formats=['elf64', 'win64'])
        self.results['formats_and_stack'] = outcomes

    def test_actual_nested_namespace_and_unauthorized_gas_bad_implementations(self):
        original = (ROOT / 'kernel/firmware/power.dg').read_text(encoding='utf-8')
        controls = [('namespace', 'if path.root_s5 {\n                    if *seen',
            'if path.root_s5 || path.depth==2 {\n                    if !path.root_s5 {negative_hit(1);}\n                    if *seen', 1),
            ('gas-boundary', 'if address<low || address>=high || bytes>high-address {return error.Denied;}',
             'if address<low || address>=high {negative_hit(2);}\n        if false {return error.Denied;}', 2)]
        outcomes = {}
        for label, needle, replacement, kind in controls:
            self.assertEqual(1, original.count(needle))
            source = self.directory / 'controls' / label / 'src'
            (source / 'firmware').mkdir(parents=True)
            changed = original.replace(needle, replacement).replace('module firmware.power;',
                'module firmware.power;\nunsafe extern "sysv64" ("power_negative_hit") fn negative_hit(kind:u64)void;', 1)
            (source / 'firmware/power.dg').write_text(changed, encoding='utf-8')
            modes = {}
            for mode in ('debug', 'release'):
                value, _ = self.native(mode, label, source)
                self.assertEqual(1, value.returncode, value.stdout + value.stderr)
                self.assertEqual(1, value.stderr.count('POWER_NEGATIVE_HIT ' + str(kind)), value.stderr)
                self.assertIn('POWER_MODEL_ASSERT', value.stderr)
                self.assertNotIn('panic', value.stderr)
                modes[mode] = dict(exit=1, actual_marked_path_hit=1, stderr=value.stderr.strip())
            outcomes[label] = modes
        self.results['actual_bad_implementations'] = outcomes


if __name__ == '__main__':
    unittest.main()
