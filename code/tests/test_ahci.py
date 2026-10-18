"""AHCI byte/state model, with an explicitly bounded VMware snapshot quirk.

Primary sources: Intel AHCI 1.3.1 sections 4.2.1, 5.3.9, 5.4.1 and 5.5.3
https://www.intel.com/content/dam/www/public/us/en/documents/technical-specifications/serial-ata-ahci-spec-rev1-3-1.pdf
SATA-IO Revision 3.4 section 11.8 (DPIOI1)
https://sata-io.org/sites/default/files/specifications/SerialATA_Revision_3_4_Gold_0.pdf
VMware's own PCI identity constants
https://github.com/vmware/open-vm-tools/blob/master/open-vm-tools/lib/include/vm_device_version.h

SATA requires initial DRQ=1. AHCI copies that original FIS to PSFIS; the
E_Status-to-PxTFD update does not specify rewriting PSFIS.Status. The saved
VMware Status40/E_Status0 is empirical compatibility, not wire conformance.
Default poll stays strict. No build_service, guest, or device I/O is executed.
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
PROTO = ROOT
sys.path.insert(0, str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
from tests.test_input import command


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AhciCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/ahci-core' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs = [PROTO / n for n in ('services/drivers/ahci_core.dg', 'tests/ahci_probe.dg',
                                         'tests/ahci_probe.c', 'tests/test_ahci.py')]
        cls.before = {str(p.relative_to(ROOT)): digest(p) for p in cls.inputs}
        cls.evidence = {}

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): digest(p) for p in cls.inputs}
        if after != cls.before:
            raise AssertionError('core inputs changed during model verification')
        summary = dict(prototype_only=False, qemu_boots=0, hardware_io=False,
                       source_unchanged=True, source_sha256=after, evidence=cls.evidence)
        (cls.directory / 'validation-summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
        print('AHCI_EVIDENCE=' + str(cls.directory))

    def native(self, mode, output, core=None, probe=None):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'NASM and SysV-capable GCC are required')
        output.mkdir(parents=True)
        compiled = compile_file(probe or PROTO / 'tests/ahci_probe.dg', mode=mode,
                                roots=[(probe.parent if probe else PROTO / 'tests'), core or ROOT / 'services'])
        self.assertEqual(['__dong_panic'], compiled.runtime_symbols)
        asm = output / 'probe.asm';asm.write_text(compiled.assembly, encoding='utf-8')
        obj = output / 'probe.o'
        command([nasm, '-f', 'win64' if os.name == 'nt' else 'elf64', *nasm_flags(nasm), '-o', obj, asm], output, 'assemble')
        binary = output / ('probe.exe' if os.name == 'nt' else 'probe')
        flags = ['-mno-sse'] if os.name == 'nt' else ['-no-pie']
        command([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                 '-D__USE_MINGW_ANSI_STDIO=1', *flags,
                 PROTO / 'tests/ahci_probe.c', obj, '-o', binary], output, 'link')
        return command([binary], output, 'native', success=False), compiled

    def test_native_all_bytes_and_lifetime_state(self):
        outcomes = {}
        for mode in ('debug', 'release'):
            result, compiled = self.native(mode, self.directory / 'native' / mode)
            self.assertEqual(0, result.returncode, result.stdout+result.stderr)
            self.assertIn('all-bytes=240 all-guards=ok no-hardware-io', result.stdout)
            self.assertIn('vmware-snapshot-quirk-replay=ok', result.stdout)
            layout = {t['full_name']: t for t in compiled.layout_manifest['types']}
            sizes = {'Lease':24, 'Caps':16, 'Info':40, 'Request':24, 'Command':240,
                     'State':80, 'Sample':320, 'EngineInput':56, 'Action':40}
            for name, size in sizes.items():
                self.assertEqual((size, 8), (layout['drivers.ahci_core.'+name]['size'],
                                             layout['drivers.ahci_core.'+name]['alignment']))
            outcomes[mode] = result.stdout.strip()
        self.evidence['native_byte_and_state_oracle'] = outcomes

    def test_bad_builders_execute_and_are_rejected(self):
        original = (ROOT / 'services/drivers/ahci_core.dg').read_text(encoding='utf-8')
        wrapper = (PROTO / 'tests/ahci_probe.dg').read_text(encoding='utf-8')
        controls = (
            ('prdt-dbc-off-by-one', 'put32(candidate.table[..],140,bytes-1);',
             'MUTANT_HITS+=1;put32(candidate.table[..],140,bytes);'),
            ('lba-high-byte-duplicated', 'candidate.table[10]=((r.lba>>40)&255) as u8;',
             'MUTANT_HITS+=1;candidate.table[10]=((r.lba>>32)&255) as u8;'),
        )
        outcomes = {}
        for label, needle, replacement in controls:
            self.assertEqual(1, original.count(needle))
            staging = self.directory / 'controls' / label
            core = staging / 'src/drivers/ahci_core.dg';core.parent.mkdir(parents=True)
            source = original.replace(needle, replacement).replace('module drivers.ahci_core;',
                      'module drivers.ahci_core;\npub var MUTANT_HITS:u64=0;', 1)
            core.write_text(source, encoding='utf-8')
            probe = staging / 'tests/ahci_probe.dg';probe.parent.mkdir()
            self.assertEqual(1, wrapper.count('fn mutant_hits()u64 {return 0;}'))
            probe.write_text(wrapper.replace('fn mutant_hits()u64 {return 0;}',
                                             'fn mutant_hits()u64 {return core.MUTANT_HITS;}'), encoding='utf-8')
            outcomes[label] = {}
            for mode in ('debug', 'release'):
                result, _ = self.native(mode, staging / mode, staging / 'src', probe)
                self.assertEqual(1, result.returncode, 'compiled bad builder must fail its byte oracle')
                self.assertRegex(result.stderr, r'AHCI_BUILDER_MUTANT_PATH_HIT=[1-9][0-9]*')
                self.assertIn('AHCI oracle line', result.stderr)
                outcomes[label][mode] = dict(code=result.returncode, stderr=result.stderr.strip())
        self.evidence['actually_executed_bad_builders'] = outcomes

    def test_bad_completion_quirks_execute_and_are_rejected(self):
        original=(ROOT/'services/drivers/ahci_core.dg').read_text(encoding='utf-8')
        wrapper=(PROTO/'tests/ahci_probe.dg').read_text(encoding='utf-8')
        controls=(
            ('ending-status-errors',
             'var initial=s.fis[0x22]&0xa9;',
             'var initial=s.fis[0x22]&0xa9;\n            var ending=s.fis[0x2f]&0xa9;\n            if policy==IDENTIFY_DRQ0 && ending!=0 {MUTANT_HITS+=1;ending=0;}',
             '(s.fis[0x2f]&0xa9)!=0','ending!=0'),
            ('current-tfd-drq',
             'if (s.tfd&0x88)!=0 || s.prdbc!=(*state).expected',
             'var current=s.tfd&0x88;\n        if policy==IDENTIFY_DRQ0 && current==8 {MUTANT_HITS+=1;current=0;}\n        if current!=0 || s.prdbc!=(*state).expected',
             None,None),
            ('short-dma',
             'if (s.tfd&0x88)!=0 || s.prdbc!=(*state).expected',
             'var bytes=s.prdbc;\n        if policy==IDENTIFY_DRQ0 && bytes<(*state).expected {MUTANT_HITS+=1;bytes=(*state).expected;}\n        if (s.tfd&0x88)!=0 || bytes!=(*state).expected',
             None,None),
        )
        outcomes={}
        for label,needle,replacement,second,changed in controls:
            self.assertEqual(1,original.count(needle));source=original.replace(needle,replacement,1)
            if second:
                self.assertEqual(1,source.count(second));source=source.replace(second,changed,1)
            source=source.replace('module drivers.ahci_core;','module drivers.ahci_core;\npub var MUTANT_HITS:u64=0;',1)
            staging=self.directory/'completion-controls'/label;core=staging/'src/drivers/ahci_core.dg';core.parent.mkdir(parents=True)
            core.write_text(source,encoding='utf-8');probe=staging/'tests/ahci_probe.dg';probe.parent.mkdir()
            needle='fn completion_mutant_hits()u64 {return 0;}'
            self.assertEqual(1,wrapper.count(needle));probe.write_text(wrapper.replace(needle,'fn completion_mutant_hits()u64 {return core.MUTANT_HITS;}',1),encoding='utf-8')
            outcomes[label]={}
            for mode in ('debug','release'):
                result,_=self.native(mode,staging/mode,staging/'src',probe)
                self.assertEqual(1,result.returncode,'actual bad completion policy must fail its independent state oracle')
                self.assertRegex(result.stderr,r'AHCI_COMPLETION_MUTANT_PATH_HIT=[1-9][0-9]*')
                self.assertIn('AHCI oracle line',result.stderr);self.assertNotIn('panic',result.stderr)
                outcomes[label][mode]=dict(code=result.returncode,stderr=result.stderr.strip())
        self.evidence['actually_executed_bad_completion_quirks']=outcomes

    def test_elf_coff_stack_and_no_device_symbols(self):
        nasm = tool('nasm', 'NASM');self.assertTrue(nasm, 'NASM is required')
        outcomes = {}
        for mode in ('debug', 'release'):
            output = self.directory / 'formats' / mode;output.mkdir(parents=True)
            compiled = compile_file(PROTO / 'tests/ahci_probe.dg', mode=mode,
                                    roots=[ROOT / 'tests', ROOT / 'services'])
            asm = output / 'probe.asm';asm.write_text(compiled.assembly, encoding='utf-8')
            self.assertEqual(['__dong_panic'], compiled.runtime_symbols)
            self.assertNotRegex(compiled.assembly, re.compile(r'^section \.(?:bss|data)\b', re.MULTILINE))
            self.assertNotRegex(compiled.assembly, r'\b(?:xmm|ymm|zmm)[0-9]+\b|^\s*(?:in|out|syscall|cli|sti)\s',
                                'pure integer core must not issue device or SIMD instructions')
            functions, current, text = {}, None, False
            for line in compiled.assembly.splitlines():
                if line.startswith('section '):
                    text = line == 'section .text'
                    current = None
                if not text: continue
                match = re.match(r'^\$([A-Za-z_][A-Za-z0-9_]*):$', line)
                if match:
                    current = match[1];functions[current] = dict(frame=16, calls=set())
                if current:
                    match = re.search(r'\bsub rsp, (\d+)', line)
                    if match: functions[current]['frame'] += int(match[1])
                    match = re.search(r'\bcall \$([A-Za-z_][A-Za-z0-9_]*)\b', line)
                    if match: functions[current]['calls'].add(match[1])
            self.assertTrue(functions)
            def stack(name, path=()):
                self.assertNotIn(name, path, 'recursive direct call invalidates the bound')
                f = functions[name]
                return f['frame'] + max([stack(c, (*path, name)) for c in f['calls'] if c in functions] or [0])
            maximum = max(map(stack, functions));self.assertLessEqual(maximum, 8192)
            decoded = {}
            for name, value in functions.items():
                parts = re.fullmatch(r'__dg_m([0-9a-f]+)_f([0-9a-f]+)', name)
                label = (bytes.fromhex(parts[1]).decode()+'.'+bytes.fromhex(parts[2]).decode()) if parts else name
                decoded[label] = dict(local_with_return_and_rbp=value['frame'], direct_call_stack=stack(name))
            for fmt in ('elf64', 'win64'):
                command([nasm, '-f', fmt, *nasm_flags(nasm), '-o', output / ('core-'+fmt+'.o'), asm], output, fmt)
            (output / 'stack.json').write_text(json.dumps(decoded, indent=2)+'\n', encoding='utf-8')
            outcomes[mode] = dict(maximum_direct_call_stack=maximum, functions=decoded,
                                  formats=['elf64', 'win64'], device_symbols=[], global_mutable_storage=0)
        self.evidence['formats_stack_and_purity'] = outcomes


if __name__ == '__main__':
    unittest.main()
