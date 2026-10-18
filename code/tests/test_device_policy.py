"""Real native UC device planning, including RAM and retained-alias rejection."""
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]


class DevicePolicyTests(unittest.TestCase):
    def test_native_independent_conflicts_and_failure_atomicity(self):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'native device validation requires NASM and SysV-capable GCC')
        directory = ROOT / 'build/test/device-policy' / ('run-' + uuid.uuid4().hex[:12])
        directory.mkdir(parents=True)
        for mode in ('debug', 'release'):
            compiled = compile_file(ROOT / 'tests/device_policy_probe.dg', roots=[ROOT / 'tests', ROOT / 'kernel', ROOT / 'lang/examples', ROOT / 'lang/std'], mode=mode)
            layouts = {t['full_name']: t for t in compiled.layout_manifest['types']}
            self.assertEqual(88, layouts['boot.device_policy.Views']['size'])
            self.assertEqual(184, layouts['boot.device_policy.Plan']['size'])
            asm, obj = directory / (mode + '.asm'), directory / (mode + '.o')
            exe = directory / (mode + ('.exe' if os.name == 'nt' else ''))
            asm.write_text(compiled.assembly, encoding='utf-8')
            commands = [[nasm, '-f', 'win64' if os.name == 'nt' else 'elf64', *nasm_flags(nasm), '-o', str(obj), str(asm)],
                        [cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-D__USE_MINGW_ANSI_STDIO=1', *(['-mno-sse'] if os.name == 'nt' else ['-no-pie']),
                         str(ROOT / 'tests/device_policy_probe.c'), str(obj), '-o', str(exe)], [str(exe)]]
            for index, command in enumerate(commands):
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=40)
                (directory / f'{mode}-{index}.json').write_text(json.dumps({'command': command, 'returncode': result.returncode,
                    'stdout': result.stdout, 'stderr': result.stderr}, indent=2) + '\n', encoding='utf-8')
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertRegex(result.stdout, r'device policy native checks=10[0-9]{2} complete Plan and input guards verified')
