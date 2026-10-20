"""Warning capability, including vendor backports, rather than version guesses."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import call, patch

from lang.tests.test_dongc import nasm_flags, tool


class NasmCompatibilityTests(unittest.TestCase):
    def test_backported_warning_is_disabled_without_disabling_other_errors(self):
        help_text = 'NASM version 2.16.03\n  reloc-rel-dword 32-bit relative section-crossing relocation [off]\n'
        with patch('lang.tests.test_dongc.subprocess.run', return_value=subprocess.CompletedProcess([], 0, help_text)) as run:
            self.assertEqual(nasm_flags('nasm'), ['-Wall', '-Werror', '-w-reloc-rel-dword'])
            self.assertEqual(run.call_args.args[0], ['nasm', '-h'])

    def test_unavailable_warning_does_not_get_an_unknown_option(self):
        for text in ('NASM version 2.15\n warnings:\n', 'NASM version 3.0\n  reloc-rel-dword-other unrelated\n'):
            with self.subTest(help=text), patch('lang.tests.test_dongc.subprocess.run', return_value=subprocess.CompletedProcess([], 0, text)):
                self.assertEqual(nasm_flags('nasm'), ['-Wall', '-Werror'])

    def test_failed_capability_probe_is_reported(self):
        with patch('lang.tests.test_dongc.subprocess.run', side_effect=subprocess.CalledProcessError(1, ['nasm', '-h'])):
            with self.assertRaises(subprocess.CalledProcessError):
                nasm_flags('nasm')

    def test_absolute_pointer_warning_is_detected_independently(self):
        for names in [('reloc-abs-qword',), ('reloc-rel-dword', 'reloc-abs-qword')]:
            help_text = 'NASM version 2.16.03\n' + ''.join('  ' + n + ' section-crossing relocation [off]\n' for n in names)
            with self.subTest(warnings=names), patch('lang.tests.test_dongc.subprocess.run', return_value=subprocess.CompletedProcess([], 0, help_text)):
                self.assertEqual(nasm_flags('nasm'), ['-Wall', '-Werror'] + ['-w-' + n for n in names])

    def test_grouped_warning_help_is_read_without_guessing_the_version(self):
        summary = 'Usage: nasm [options] filename\n  -h -opt show additional help for option "-opt"\n'
        warnings = '  reloc-rel-dword relative relocation\n  reloc-abs-qword absolute relocation\n'
        with patch('lang.tests.test_dongc.subprocess.run', side_effect=[
            subprocess.CompletedProcess([], 0, summary),
            subprocess.CompletedProcess([], 0, warnings),
        ]) as run:
            self.assertEqual(nasm_flags('nasm'), [
                '-Wall', '-Werror', '-w-reloc-rel-dword', '-w-reloc-abs-qword',
            ])
            self.assertEqual(run.call_args_list, [
                call(['nasm', '-h'], capture_output=True, text=True, check=True),
                call(['nasm', '-h', '-w'], capture_output=True, text=True, check=True),
            ])

    def test_legacy_help_does_not_receive_an_unsupported_group_option(self):
        help_text = 'Usage: nasm [options] filename\n  -h print help\n  reloc-abs-qword absolute relocation\n'
        unsupported = subprocess.CalledProcessError(
            1, ['nasm', '-h', '-w'], stderr='nasm: error: unrecognized option `-w`',
        )
        with patch('lang.tests.test_dongc.subprocess.run', side_effect=[
            subprocess.CompletedProcess([], 0, help_text), unsupported,
        ]) as run:
            self.assertEqual(nasm_flags('nasm'), ['-Wall', '-Werror', '-w-reloc-abs-qword'])
            self.assertEqual(run.call_count, 1)

    def test_grouped_help_matches_full_names_and_detects_each_warning(self):
        summary = '  -h -opt show additional help\n'
        for names in [(), ('reloc-rel-dword',), ('reloc-abs-qword',)]:
            warnings = ('  reloc-rel-dword-other unrelated\n'
                        '  reloc-abs-qword-extra unrelated\n'
                        '  prefix-reloc-abs-qword unrelated\n')
            warnings += ''.join('  ' + name + ' relocation\n' for name in names)
            with self.subTest(names=names), patch('lang.tests.test_dongc.subprocess.run', side_effect=[
                subprocess.CompletedProcess([], 0, summary),
                subprocess.CompletedProcess([], 0, warnings),
            ]):
                self.assertEqual(nasm_flags('nasm'), ['-Wall', '-Werror'] + ['-w-' + n for n in names])

    def test_failed_grouped_probe_is_reported(self):
        failure = subprocess.CalledProcessError(
            2, ['nasm', '-h', '-w'], stderr='cannot read warning definitions',
        )
        with patch('lang.tests.test_dongc.subprocess.run', side_effect=[
            subprocess.CompletedProcess([], 0, '  -h -opt show additional help\n'), failure,
        ]):
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                nasm_flags('nasm')
            self.assertIs(caught.exception, failure)

    def test_native_cross_section_relocations_assemble_in_both_formats(self):
        nasm = tool('nasm', 'NASM')
        self.assertIsNotNone(nasm, 'native NASM is required for the compatibility check')
        flags = nasm_flags(nasm)
        snippets = {
            'reloc-rel-dword': ('bits 64\ndefault rel\nsection .text\n'
                                'probe: lea rax, [rel data]\nret\n'
                                'section .rodata\ndata: db 0\n'),
            'reloc-abs-qword': ('bits 64\ndefault rel\nsection .text\n'
                                'probe: ret\nsection .rodata\ndata: dq probe\n'),
        }
        with tempfile.TemporaryDirectory(prefix='dongos-nasm-compatibility-') as directory:
            root = Path(directory)
            for name, assembly in snippets.items():
                source = root / (name + '.asm')
                source.write_text(assembly, encoding='ascii')
                for fmt in ('elf64', 'win64'):
                    with self.subTest(warning=name, format=fmt):
                        output = root / (name + '.' + fmt + '.o')
                        if '-w-' + name in flags:
                            baseline = subprocess.run(
                                [nasm, '-f', fmt, '-Wall', '-Werror', '-o', str(output), str(source)],
                                capture_output=True, text=True,
                            )
                            self.assertNotEqual(baseline.returncode, 0, 'relocation control must expose the warning')
                            self.assertIn(name, baseline.stderr)
                        assembled = subprocess.run(
                            [nasm, '-f', fmt, *flags, '-o', str(output), str(source)],
                            capture_output=True, text=True,
                        )
                        self.assertEqual(assembled.returncode, 0, assembled.stderr)
                        self.assertGreater(output.stat().st_size, 0)

    def test_native_other_warning_remains_an_error(self):
        nasm = tool('nasm', 'NASM')
        self.assertIsNotNone(nasm, 'native NASM is required for the compatibility check')
        flags = nasm_flags(nasm)
        with tempfile.TemporaryDirectory(prefix='dongos-nasm-compatibility-') as directory:
            root = Path(directory)
            source = root / 'overflow.asm'
            source.write_text('bits 64\nsection .data\ndb 256\n', encoding='ascii')
            for fmt in ('elf64', 'win64'):
                with self.subTest(format=fmt):
                    output = root / (fmt + '.o')
                    assembled = subprocess.run(
                        [nasm, '-f', fmt, *flags, '-o', str(output), str(source)],
                        capture_output=True, text=True,
                    )
                    self.assertNotEqual(assembled.returncode, 0)
                    self.assertIn('number-overflow', assembled.stderr)
