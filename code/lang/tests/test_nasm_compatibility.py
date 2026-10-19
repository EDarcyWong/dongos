"""Warning capability, including vendor backports, rather than version guesses."""
import subprocess
import unittest
from unittest.mock import patch

from lang.tests.test_dongc import nasm_flags


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
