"""Native transaction oracle around the unmodified formal grant function body."""
from pathlib import Path
import hashlib
import json
import os
import re
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/ahci_broker_fixtures'
sys.path.insert(0, str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
from tests.test_input import command


def sha(data):
    return hashlib.sha256(data).hexdigest()


class AhciBrokerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/ahci-broker' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.formal = ROOT / 'kernel/user/devices.dg'
        cls.raw = cls.formal.read_bytes()
        start = cls.raw.index(b'pub unsafe fn grant(')
        end = cls.raw.index(b'pub fn granted_bars(', start)
        cls.body = cls.raw[start:end]
        cls.before = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in
                      [cls.formal, FIXTURES / 'harness-prefix.dg.in', FIXTURES / 'harness-suffix.dg.in',
                       ROOT / 'tests/ahci_broker_probe.c', Path(__file__), *sorted((FIXTURES / 'stubs').rglob('*.dg')),
                       *sorted((ROOT / 'lang/dongc').glob('*.py'))]}
        (cls.directory / 'grant.original.dg').write_bytes(cls.body)
        cls.extraction = dict(path='kernel/user/devices.dg', full_source_sha256=sha(cls.raw),
                              byte_start=start, byte_end=end, body_bytes=len(cls.body),
                              body_sha256=sha(cls.body), original_bytes_preserved=True,
                              prefix_source='tests/ahci_broker_fixtures/harness-prefix.dg.in',
                              suffix_source='tests/ahci_broker_fixtures/harness-suffix.dg.in')
        (cls.directory / 'extraction.json').write_text(json.dumps(cls.extraction, indent=2) + '\n', encoding='utf-8')
        cls.evidence = {}

    @classmethod
    def tearDownClass(cls):
        after = {name: sha((ROOT / name).read_bytes()) for name in cls.before}
        if after != cls.before:
            raise AssertionError('formal grant input/envelope/compiler changed during broker verification')
        (cls.directory / 'validation-summary.json').write_text(json.dumps(dict(
            passed=bool(cls.evidence), sources_unchanged=True, source_sha256=after, extracted_function=cls.extraction,
            actual_scratch_window_executed=False, actual_pagetables_executed=False,
            actual_device_executed=False, minimal_typed_stub_contracts=True,
            evidence=cls.evidence), indent=2) + '\n', encoding='utf-8')

    def compile(self, mode, where, bad=False):
        body = self.body
        if bad:
            needle = b'if ((try read32(ecam+4))&65535)!=((old_command&~7) as u32) {return error.Invalid;}'
            self.assertEqual(1, body.count(needle))
            body = body.replace(needle, b'negative_hit(1); // deliberately omitted initial readback')
        prefix = (FIXTURES / 'harness-prefix.dg.in').read_bytes()
        capwalk = self.raw[self.raw.index(b'unsafe fn interrupt_caps('):self.raw.index(b'pub unsafe fn grant(')]
        stub = b'unsafe fn interrupt_caps(ecam:u64,disable:bool)!u64 {return error.Invalid;}'
        self.assertEqual(1, prefix.count(stub))
        # Execute the real capability walk. This independent AHCI model has no
        # MSI capability; any attempted capability write must fail closed.
        prefix = prefix.replace(stub, b'unsafe fn configuration_write16(address:u64,value:u16)!void {return error.Invalid;}\n' + capwalk)
        harness = prefix + body + (FIXTURES / 'harness-suffix.dg.in').read_bytes()
        path = where / 'broker_probe.dg'
        path.write_bytes(harness)
        if not bad:
            self.assertEqual(1, harness.count(self.body))
        compiled = compile_file(path, mode=mode, roots=[where, FIXTURES / 'stubs'])
        (where / 'layout.json').write_text(json.dumps(compiled.layout_manifest, indent=2) + '\n', encoding='utf-8')
        return compiled

    def test_original_body_and_actual_bad_readback_control(self):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'broker native model needs NASM and GCC')
        evidence = {}
        for bad in (False, True):
            modes = {}
            for mode in ('debug', 'release'):
                where = self.directory / ('bad' if bad else 'normal') / mode
                where.mkdir(parents=True)
                compiled = self.compile(mode, where, bad)
                assembly = where / 'probe.asm'
                assembly.write_text(compiled.assembly, encoding='utf-8')
                self.assertNotRegex(compiled.assembly.lower(), r'\b(?:invlpg|rdmsr|wrmsr|cr[0348]|xmm[0-9]+|ymm[0-9]+)\b')
                maximum = max(map(int, re.findall(r'\bsub rsp, (\d+)', compiled.assembly)), default=0)
                self.assertLessEqual(maximum, 4096)
                native_fmt = 'win64' if os.name == 'nt' else 'elf64'
                obj = where / 'probe.o'
                for fmt in (native_fmt,) if bad else ('elf64', 'win64'):
                    target = obj if fmt == native_fmt else where / (fmt + '.o')
                    command([nasm, '-f', fmt, *nasm_flags(nasm), '-o', target, assembly], where, 'assemble-' + fmt)
                binary = where / ('probe.exe' if os.name == 'nt' else 'probe')
                flags = ['-mno-sse'] if os.name == 'nt' else ['-no-pie']
                command([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-D__USE_MINGW_ANSI_STDIO=1',
                         *flags, ROOT / 'tests/ahci_broker_probe.c', obj, '-o', binary], where, 'link')
                trace = where / 'events.jsonl'
                result = command([binary, trace], where, 'execute', success=False)
                if bad:
                    self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                    self.assertEqual(1, result.stderr.count('BROKER_NEGATIVE_HIT 1'), result.stderr)
                    self.assertIn('BROKER_MODEL_ASSERT', result.stderr)
                    self.assertIn('(p->command&7)==0', result.stderr)
                    self.assertNotIn('panic', result.stderr.lower())
                else:
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn('AHCI_BROKER_MODEL_OK', result.stdout)
                events = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
                # First actual transaction is the ignored command-clear case.
                first = [e for e in events if e['case'] == 1]
                destructive = [e for e in first if e['event'] in ('BAR_WRITE', 'MAP_ATTEMPT', 'HANDLE_ATTEMPT', 'BME_ENABLE_REQUEST')]
                self.assertEqual(1 if bad else 0, len(destructive))
                self.assertEqual([e['a'] for e in first if e['event'] == 'PCI_COMMAND'], [0x400])
                modes[mode] = dict(returncode=result.returncode, stdout=result.stdout.strip(), stderr=result.stderr.strip(),
                                   maximum_single_generated_stack_reservation=maximum,
                                   raw_event_records=len(events), events_sha256=sha(trace.read_bytes()),
                                   first_ignored_clear_destructive_events=len(destructive),
                                   actual_mutated_path_executed=bad)
            evidence['actual_bad_readback_omission' if bad else 'original_formal_body'] = modes
        self.evidence['native_transactions'] = evidence
        print('AHCI_BROKER_EVIDENCE', self.directory / 'validation-summary.json')


if __name__ == '__main__':
    unittest.main()
