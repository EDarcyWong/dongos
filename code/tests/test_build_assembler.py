"""Build-driver warning capabilities, including NASM 2.x backports."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, mock
import tempfile
from tools import build

class AssemblerCapabilities(TestCase):
    def test_supported_relocation_diagnostics_only(self):
        for help_text, expected in (
            ('NASM old\n', []),
            ('NASM 2 backport\n reloc-rel-dword optional\n', ['-w-reloc-rel-dword']),
            ('NASM 3\n reloc-rel-dword optional\n reloc-abs-qword optional\n',
             ['-w-reloc-rel-dword', '-w-reloc-abs-qword']),
        ):
            with self.subTest(help=help_text), tempfile.TemporaryDirectory() as tmp:
                with mock.patch.object(build, 'find_tool', return_value='nasm'), \
                     mock.patch.object(build.subprocess, 'run', return_value=SimpleNamespace(stdout=help_text)) as run, \
                     mock.patch.object(build, 'execute') as execute:
                    build.assemble(Path('source.asm'), Path(tmp), fmt='elf64', test=True, stage='p1')
                command = execute.call_args.args[0]
                self.assertIn('-Wall', command); self.assertIn('-Werror', command)
                self.assertIn('-DP1_TEST=1', command)
                self.assertEqual(expected, [x for x in command if x.startswith('-w-')])
                self.assertEqual(['nasm', '-h'], run.call_args.args[0])
