"""Execute the production startup text, including a normally returning bad bridge.

This fast NASM oracle complements the full native-assembler ELF execution in
test_bootstrap_compiler_job; it does not imply guest execution.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import unittest
import uuid

from lang.tests.test_dongc import nasm_flags, tool
from tools.compiler_job import BRIDGE, HOST_UTILS, ROOT, STARTUP_CHECK


MAIN = r'''
int main(int argc,char**argv){
 check(argc==3,"usage");FILE*f=fopen(argv[1],"rb");check(f!=NULL,"bridge open");
 unsigned char entry[28];check(fread(entry,1,sizeof entry,f)==sizeof entry,"bridge size");
 check(fgetc(f)==EOF&&!fclose(f),"bridge EOF");check(entry[27]==0xc3,"oracle target return");
 check(!memcmp(entry,entry_prefix,7)&&entry[10]==0xe8,"production stack/call encoding");
 check(!memcmp(entry+15,entry_suffix,sizeof entry_suffix),"production guest exit tail");
 if(!strcmp(argv[2],"normal"))check(!memcmp(entry,entry_prefix,sizeof entry_prefix),"production R10 restore encoding");
 else check(entry[7]==0x90&&entry[8]==0x90&&entry[9]==0x90,"actual omitted-restore mutant");
 check_startup_bridge(entry);check(startup_checks==2,"startup vector coverage");
 puts("PASS production startup prefix/call: six arguments, RCX poison, R10 restore, stack alignment and guards");return 0;
}
'''


class StartupBridgeTests(unittest.TestCase):
    def test_actual_startup_registers_and_missing_restore_mutant(self):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'NASM and GCC are required; no skipped machine execution')
        source = ROOT / 'lang/bootstrap/compiler_job.dg'
        dependencies = [source, ROOT / 'tools/compiler_job.py', Path(__file__)]
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies}
        match = re.search(r'let bridge=("(?:[^"\\]|\\.)*");', source.read_text(encoding='utf-8'))
        self.assertIsNotNone(match)
        bridge = json.loads(match.group(1))
        self.assertEqual(bridge.count('mov rcx, r10\n'), 1)
        work = ROOT / 'build/test/compiler-startup-bridge' / ('run-' + uuid.uuid4().hex[:12])
        work.mkdir(parents=True)
        records = []

        def command(args, label, expected=0, needle=None):
            result = subprocess.run(list(map(str, args)), capture_output=True, timeout=60)
            row = dict(command=list(map(str, args)), returncode=result.returncode,
                       expected_exit=expected, stdout=result.stdout.decode(errors='replace'),
                       stderr=result.stderr.decode(errors='replace'))
            records.append(row)
            (work / (label + '.json')).write_text(json.dumps(row, indent=2) + '\n', encoding='utf-8')
            self.assertEqual(result.returncode, expected, row)
            if needle:
                self.assertIn(needle, row['stderr'], row)
            return result

        (work / 'invoke.asm').write_text(BRIDGE, encoding='ascii')
        (work / 'probe.c').write_text(HOST_UTILS + STARTUP_CHECK + MAIN, encoding='ascii')
        fmt = 'win64' if os.name == 'nt' else 'elf64'
        command([nasm, '-O0', '-f', fmt, *nasm_flags(nasm), '-o', work / 'invoke.o',
                 work / 'invoke.asm'], 'invoke-assemble')
        other = 'elf64' if fmt == 'win64' else 'win64'
        command([nasm, '-O0', '-f', other, *nasm_flags(nasm), '-o', work / 'invoke-other.o',
                 work / 'invoke.asm'], 'invoke-other-format')
        executable = work / ('probe.exe' if os.name == 'nt' else 'probe')
        command([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                 work / 'probe.c', work / 'invoke.o', '-o', executable], 'link')
        for variant in ('normal', 'missing-restore'):
            text = bridge if variant == 'normal' else bridge.replace('mov rcx, r10\n', 'nop\nnop\nnop\n')
            assembly, binary = work / (variant + '.asm'), work / (variant + '.bin')
            assembly.write_text('bits 64\n' + text + '\ndong_compile_job:\nret\n', encoding='ascii')
            command([nasm, '-O0', '-f', 'bin', '-o', binary, assembly], variant + '-assemble')
            self.assertEqual(binary.stat().st_size, 28)
            result = command([executable, binary, variant], variant + '-execute',
                             0 if variant == 'normal' else 90,
                             None if variant == 'normal' else 'FAIL startup argument 4 differs')
            if variant == 'normal':
                self.assertIn('PASS production startup prefix/call', result.stdout.decode())
        self.assertEqual(before, {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies})
        (work / 'summary.json').write_text(json.dumps(dict(
            passed=True, guest_executed=False, source_stable=True, source_sha256=before,
            actual_startup_prefix_call=True, negative_control='missing restore: argument 4 oracle, exit 90',
            records=records), indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
