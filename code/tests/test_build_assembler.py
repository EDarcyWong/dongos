"""Build-driver warning capabilities, including NASM 2.x backports."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, mock
import hashlib
import json
import re
import subprocess
import tempfile
import uuid
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

    def test_grouped_help_in_production_assemble_preserves_command_contract(self):
        summary = 'Usage: nasm\n -h -opt show additional help\n'
        warnings = ' reloc-rel-dword relative\n reloc-abs-qword absolute\n'
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(build, 'find_tool', return_value='nasm'), \
             mock.patch.object(build.subprocess, 'run', side_effect=[
                 SimpleNamespace(stdout=summary), SimpleNamespace(stdout=warnings),
             ]) as run, mock.patch.object(build, 'execute') as execute:
            output = Path(tmp)
            result = build.assemble(Path('example.asm'), output, fmt='win64',
                                    test=True, stage='p1', defines={'RUNTIME_LEVEL': 7})
            self.assertEqual(result, output / 'example.obj')
            self.assertEqual([c.args[0] for c in run.call_args_list],
                             [['nasm', '-h'], ['nasm', '-h', '-w']])
            self.assertTrue(all(c.kwargs['check'] for c in run.call_args_list))
            command = execute.call_args.args[0]
            for flag in ('-Wall', '-Werror', '-DP1_TEST=1', '-DRUNTIME_LEVEL=7',
                         '-w-reloc-rel-dword', '-w-reloc-abs-qword'):
                self.assertIn(flag, command)
            self.assertEqual(command[command.index('-f') + 1], 'win64')
            self.assertEqual(command[command.index('-l') + 1], str(output / 'example.lst'))
            self.assertEqual(command[command.index('-o') + 1], str(result))
            self.assertEqual(command.count('-I'), 2)
            self.assertEqual(command[-1], 'example.asm')

    def test_legacy_help_does_not_receive_group_option(self):
        unsupported = subprocess.CalledProcessError(2, ['nasm', '-h', '-w'])
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(build, 'find_tool', return_value='nasm'), \
             mock.patch.object(build.subprocess, 'run', side_effect=[
                 SimpleNamespace(stdout=' -h print help\n reloc-abs-qword pointer\n'),
                 unsupported,
             ]) as run, mock.patch.object(build, 'execute') as execute:
            build.assemble(Path('old.asm'), Path(tmp), fmt='elf64', test=False, stage='p1')
            self.assertEqual(run.call_count, 1)
            self.assertEqual([a for a in execute.call_args.args[0] if a.startswith('-w-')],
                             ['-w-reloc-abs-qword'])

    def test_grouped_warning_names_match_exactly_and_independently(self):
        for names in ((), ('reloc-rel-dword',), ('reloc-abs-qword',)):
            with self.subTest(names=names), tempfile.TemporaryDirectory() as tmp, \
                 mock.patch.object(build, 'find_tool', return_value='nasm'), \
                 mock.patch.object(build.subprocess, 'run', side_effect=[
                     SimpleNamespace(stdout=' -h -opt additional help\n'),
                     SimpleNamespace(stdout=' reloc-rel-dword-extra wrong\n reloc-abs-qword-extra wrong\n'
                                     + ''.join(' ' + n + ' actual\n' for n in names)),
                 ]), mock.patch.object(build, 'execute') as execute:
                build.assemble(Path('exact.asm'), Path(tmp), fmt='elf64', test=False, stage='p1')
                self.assertEqual([a for a in execute.call_args.args[0] if a.startswith('-w-')],
                                 ['-w-' + n for n in names])

    def test_probe_failures_abort_before_assembly(self):
        for group in (False, True):
            failure = subprocess.CalledProcessError(3, ['nasm', '-h'])
            responses = [SimpleNamespace(stdout=' -h -opt additional help\n'), failure] if group else [failure]
            with self.subTest(group=group), tempfile.TemporaryDirectory() as tmp, \
                 mock.patch.object(build, 'find_tool', return_value='nasm'), \
                 mock.patch.object(build.subprocess, 'run', side_effect=responses), \
                 mock.patch.object(build, 'execute') as execute:
                with self.assertRaises(subprocess.CalledProcessError) as caught:
                    build.assemble(Path('bad.asm'), Path(tmp), fmt='elf64', test=False, stage='p1')
                self.assertIs(caught.exception, failure)
                execute.assert_not_called()

    def test_real_production_assembler_legal_relocations_and_other_error(self):
        nasm = build.find_tool('nasm', 'NASM')
        state = build.ROOT / 'build/test/build-assembler' / ('run-' + uuid.uuid4().hex[:12])
        state.mkdir(parents=True)
        paths = [Path(build.__file__), Path(__file__)]
        hashes = lambda: {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        before = hashes()
        help_text = subprocess.run([nasm, '-h'], capture_output=True, text=True, check=True).stdout
        if re.search(r'(?m)^\s*-h\s+-\S+', help_text):
            help_text += '\n' + subprocess.run([nasm, '-h', '-w'], capture_output=True, text=True, check=True).stdout
        records = []
        snippets = {
            'reloc-rel-dword': 'bits 64\ndefault rel\nsection .text\nprobe: lea rax,[rel data]\nret\nsection .rodata\ndata: db 0\n',
            'reloc-abs-qword': 'bits 64\nsection .text\nprobe: ret\nsection .rodata\ndata: dq probe\n',
        }
        for name, text in snippets.items():
            source = state / (name + '.asm');source.write_text(text, encoding='ascii')
            for fmt in ('elf64', 'win64'):
                with self.subTest(name=name, fmt=fmt):
                    if re.search(r'(?m)^\s*' + re.escape(name) + r'\s', help_text):
                        raw = subprocess.run([nasm, '-f', fmt, '-Wall', '-Werror', '-o',
                                              str(state / 'raw.o'), str(source)], capture_output=True, text=True)
                        self.assertNotEqual(raw.returncode, 0)
                        self.assertIn(name, raw.stderr)
                        records.append(dict(name=name, fmt=fmt, raw_returncode=raw.returncode, raw_stderr=raw.stderr))
                    with mock.patch.object(build, 'find_tool', return_value=nasm):
                        obj = build.assemble(source, state / (name + '-' + fmt), fmt=fmt, test=False, stage='p1')
                    self.assertGreater(obj.stat().st_size, 0)
                    self.assertTrue(obj.with_suffix('.lst').is_file())
                    records.append(dict(name=name, fmt=fmt, production_returncode=0,
                                        object_sha256=hashlib.sha256(obj.read_bytes()).hexdigest()))
        overflow = state / 'overflow.asm';overflow.write_text('bits 64\nsection .data\ndb 256\n', encoding='ascii')
        for fmt in ('elf64', 'win64'):
            with self.subTest(overflow=fmt), mock.patch.object(build, 'find_tool', return_value=nasm):
                with self.assertRaises(subprocess.CalledProcessError):
                    build.assemble(overflow, state / ('overflow-' + fmt), fmt=fmt, test=False, stage='p1')
                raw = subprocess.run([nasm, '-f', fmt, '-Wall', '-Werror', '-o', str(state / 'overflow.o'),
                                      str(overflow)], capture_output=True, text=True)
                self.assertNotEqual(raw.returncode, 0);self.assertIn('number-overflow', raw.stderr)
                records.append(dict(name='overflow', fmt=fmt, production_rejected=True, stderr=raw.stderr))
        self.assertEqual(hashes(), before)
        (state / 'result.json').write_text(json.dumps(dict(passed=True, source_before=before,
            source_after=hashes(), nasm=nasm, records=records), indent=2) + '\n')
        print('Production assembler evidence:', state)
