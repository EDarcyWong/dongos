"""Execute production shared-flush ASM control flow; privileged body is mocked.

The coordinator runs this native gate. It never starts an OS/VM and never
executes CR access or INVPCID. Both original and instrumented ASM are assembled.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import unittest
import uuid

from lang.tests.test_dongc import tool

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'kernel/user/shared_barrier.asm'
PROBE = ROOT / 'tests/user_shared_flush_probe.c'
LOCAL_MOCK = '''extern user_shared_mock_local_flush
 sub rsp,8
 call user_shared_mock_local_flush
 add rsp,8
 ret
'''
BRIDGE = '''bits 64
default rel
section .text
extern user_shared_barrier
extern user_shared_mock_active,user_shared_mock_local,user_shared_mock_broadcast
global user_shared_abi_call,dong_user_smp_barrier,smp_invalidate_all
global user_shared_mock_local_flush
; Tail thunks expose actual call-entry RSP alignment to the independent C oracle.
dong_user_smp_barrier:
 mov rdi,rsp
 and edi,15
 jmp user_shared_mock_active
user_shared_mock_local_flush:
 mov rdi,rsp
 and edi,15
 jmp user_shared_mock_local
smp_invalidate_all:
 mov rdx,rsp
 and edx,15
 jmp user_shared_mock_broadcast
; Preserve our own caller, then inspect all SysV callee-saved GPRs and RSP.
user_shared_abi_call:
 push rbp
 push rbx
 push r12
 push r13
 push r14
 push r15
 sub rsp,40
 mov [rsp],rdi
 mov [rsp+8],rsp
 mov rbp,0x1020304050607080
 mov rbx,0x2131415161718191
 mov r12,0x32425262728292a2
 mov r13,0x435363738393a3b3
 mov r14,0x5464748494a4b4c4
 mov r15,0x65758595a5b5c5d5
 call user_shared_barrier
 mov r10,[rsp]
 mov [r10],rax
 mov rax,[rsp+8]
 mov [r10+8],rax
 mov [r10+16],rsp
 mov [r10+24],rbp
 mov [r10+32],rbx
 mov [r10+40],r12
 mov [r10+48],r13
 mov [r10+56],r14
 mov [r10+64],r15
 add rsp,40
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbx
 pop rbp
 ret
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


class UserSharedFlushTests(unittest.TestCase):
    def test_real_selector_orchestration_abi_and_three_semantic_mutants(self):
        output = ROOT / 'build/test/p2-user-shared-flush' / ('run-' + uuid.uuid4().hex[:12])
        output.mkdir(parents=True)
        inputs = [SOURCE, PROBE, Path(__file__).resolve(), ROOT / 'lang/tests/test_dongc.py',
                  ROOT / 'docs/user-address-spaces.md']
        before = {str(p.relative_to(ROOT)): sha(p) if p.is_file() else None for p in inputs}
        write_json(output / 'source-before.json', before)
        records, evidence, tool_info = [], [], {}
        passed, failure = False, None

        def command(args, directory, label):
            args = list(map(str, args))
            started = time.monotonic()
            row = dict(name=label, command=args, cwd=str(ROOT), timed_out=False)
            try:
                result = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=60)
                row.update(returncode=result.returncode, stdout=result.stdout.decode('utf-8', 'replace'),
                           stderr=result.stderr.decode('utf-8', 'replace'))
                (directory / (label + '.stdout')).write_bytes(result.stdout)
                (directory / (label + '.stderr')).write_bytes(result.stderr)
            except subprocess.TimeoutExpired as exc:
                row.update(returncode=None, timed_out=True, stdout=str(exc.stdout), stderr=str(exc.stderr))
                (directory / (label + '.stdout')).write_bytes(exc.stdout or b'')
                (directory / (label + '.stderr')).write_bytes(exc.stderr or b'')
                raise
            finally:
                row['elapsed_seconds'] = time.monotonic() - started
                records.append(row)
                write_json(directory / (label + '.json'), row)
                write_json(output / 'commands.json', records)
            return result

        try:
            self.assertNotIn(None, before.values(), 'every frozen source input must exist')
            nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
            self.assertTrue(nasm and cc, 'configured NASM/GCC are required; this gate never skips')
            tool_info = {name: dict(path=str(Path(path).resolve()), sha256=sha(path))
                         for name, path in (('nasm', nasm), ('cc', cc))}
            for path, label in ((nasm, 'nasm-version'), (cc, 'cc-version')):
                result = command([path, '-v' if path == nasm else '--version'], output, label)
                self.assertEqual(0, result.returncode, result.stderr.decode('utf-8', 'replace'))
            # Keep warning capability probes in the same raw command ledger as
            # compilation; do not let the shared helper run hidden subprocesses.
            result = command([nasm, '-h'], output, 'nasm-help')
            self.assertEqual(0, result.returncode, result.stderr.decode('utf-8', 'replace'))
            help_text = result.stdout.decode('utf-8', 'replace')
            if re.search(r'(?m)^\s*-h\s+-\S+', help_text):
                result = command([nasm, '-h', '-w'], output, 'nasm-warning-help')
                self.assertEqual(0, result.returncode, result.stderr.decode('utf-8', 'replace'))
                help_text += '\n' + result.stdout.decode('utf-8', 'replace')
            flags = ['-Wall', '-Werror'] + [
                '-w-' + name for name in ('reloc-rel-dword', 'reloc-abs-qword')
                if re.search(r'(?m)^\s*' + re.escape(name) + r'\s', help_text)
            ]
            raw = SOURCE.read_bytes()
            marker = b'user_shared_local_flush:'
            self.assertEqual(1, raw.count(marker))
            begin = raw.index(b'\n', raw.index(marker)) + 1
            end = raw.index(b'%ifidn __OUTPUT_FORMAT__,elf64', begin)
            body, prefix, suffix = raw[begin:end], raw[:begin], raw[end:]
            self.assertIn(b'mov rdi,cr4', body)
            self.assertIn(b'invpcid rax,[rsp]', body)
            newline = b'\r\n' if b'\r\n' in raw else b'\n'
            mock = LOCAL_MOCK.encode().replace(b'\n', newline)
            instrumented = prefix + mock + suffix
            self.assertEqual(prefix, instrumented[:begin])
            self.assertEqual(suffix, instrumented[begin + len(mock):])
            write_json(output / 'instrumentation.json', dict(
                source_sha256=sha(SOURCE), production_prefix_sha256=hashlib.sha256(prefix).hexdigest(),
                production_hardware_body_sha256=hashlib.sha256(body).hexdigest(),
                production_suffix_sha256=hashlib.sha256(suffix).hexdigest(),
                boundary='only user_shared_local_flush hardware body replaced in private copies',
                orchestration_and_selector_preserved_byte_for_byte=True,
                actual_cr4_and_tlb_instructions_executed=False))
            native = 'win64' if os.name == 'nt' else 'elf64'

            def assemble(source, target, fmt, runtime, directory, label):
                result = command([nasm, '-f', fmt, *flags,
                                  '-DRUNTIME_LEVEL=' + str(runtime), source, '-o', target], directory, label)
                self.assertEqual(0, result.returncode, result.stderr.decode('utf-8', 'replace'))

            # The actual privileged production body is only assembled, in all
            # three runtime configurations and both object containers.
            for runtime in (4, 6, 7):
                for fmt in ('elf64', 'win64'):
                    assemble(SOURCE, output / f'production-r{runtime}-{fmt}.o', fmt, runtime,
                             output, f'production-r{runtime}-{fmt}')

            variants = [
                ('good', 4, None, None, 'all', None),
                ('good', 6, None, None, 'all', None),
                ('good', 7, None, None, 'all', None),
                ('missing-broadcast', 7, b' call smp_invalidate_all', b' xor eax,eax',
                 'broadcast', 'broadcast-required/callback-order'),
                ('active-error-fallback', 7, b' jne .failed', b' nop',
                 'active-error', 'active-error-no-fallback/result'),
                ('accept-PGE', 7, b' jnz .global_unsupported', b' nop',
                 'selector', 'PGE-rejection/selector'),
            ]
            for name, runtime, old, new, scenario, rejection in variants:
                directory = output / (name + '-r' + str(runtime))
                directory.mkdir()
                selected = instrumented
                if old is not None:
                    self.assertEqual(1, prefix.count(old), name)
                    selected = prefix.replace(old, new, 1) + mock + suffix
                source = directory / 'shared_barrier.asm'
                source.write_bytes(selected)
                bridge = directory / 'bridge.asm'
                bridge.write_text(BRIDGE, encoding='ascii')
                for fmt in ('elf64', 'win64'):
                    assemble(source, directory / ('shared-' + fmt + '.o'), fmt, runtime,
                             directory, 'shared-' + fmt)
                    assemble(bridge, directory / ('bridge-' + fmt + '.o'), fmt, runtime,
                             directory, 'bridge-' + fmt)
                executable = directory / ('probe.exe' if os.name == 'nt' else 'probe')
                result = command([cc, '-std=c11', '-D__USE_MINGW_ANSI_STDIO=1',
                                  '-DTEST_RUNTIME_LEVEL=' + str(runtime), '-O2', '-Wall', '-Wextra', '-Werror',
                                  *([] if os.name == 'nt' else ['-no-pie']), PROBE,
                                  directory / ('shared-' + native + '.o'),
                                  directory / ('bridge-' + native + '.o'), '-o', executable], directory, 'link')
                self.assertEqual(0, result.returncode, result.stderr.decode('utf-8', 'replace'))
                result = command([executable, scenario], directory, 'native')
                stderr, stdout = result.stderr.decode('utf-8', 'replace'), result.stdout.decode('utf-8', 'replace')
                self.assertEqual(1 if rejection else 0, result.returncode, stdout + stderr)
                if rejection:
                    self.assertIn('P2_FLUSH_ORACLE ' + rejection, stderr)
                    self.assertNotIn('P2_FLUSH_PASS', stdout)
                else:
                    self.assertIn('P2_FLUSH_PASS runtime=' + str(runtime), stdout)
                    self.assertIn('hardware=mock', stdout)
                evidence.append(dict(variant=name, runtime_level=runtime, scenario=scenario,
                                     source_sha256=sha(source), executable_sha256=sha(executable),
                                     object_sha256={p.name: sha(p) for p in directory.glob('*.o')},
                                     actual_native_returncode=result.returncode, rejected_by=rejection))
            self.assertEqual(before, {str(p.relative_to(ROOT)): sha(p) for p in inputs})
            passed = True
        except BaseException as exc:
            failure = dict(type=type(exc).__name__, message=str(exc))
            raise
        finally:
            after = {str(p.relative_to(ROOT)): sha(p) if p.is_file() else None for p in inputs}
            write_json(output / 'source-after.json', after)
            artifacts = {p.relative_to(output).as_posix(): sha(p)
                         for p in output.rglob('*') if p.is_file() and p.name != 'validation-summary.json'}
            write_json(output / 'validation-summary.json', dict(
                passed=passed and before == after, failure=failure, sources_unchanged=before == after,
                source_before=before, source_after=after, tools=tool_info, artifact_sha256=artifacts,
                records=records, evidence=evidence, skipped=[],
                runtime_levels=[4, 6, 7], real_production_selector=True,
                real_production_orchestration=True, hardware_local_flush_body_mocked=True,
                actual_cr4_read_executed=False, actual_invpcid_executed=False,
                actual_ap_or_user_cr3_execution=False, os_or_vm_started=False))
            print('P2_USER_SHARED_FLUSH_EVIDENCE', output)


if __name__ == '__main__':
    unittest.main(verbosity=2)
