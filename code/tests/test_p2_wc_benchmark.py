"""Coordinator-only native/source gates. These tests never boot an OS/VM."""
from pathlib import Path
import ast
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest import mock

from lang.dongc import compile_file
from lang.tests.test_dongc import tool
from tests import p2_wc_stage as stage
from tests import run_p2_wc_benchmark as runner

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'tests'


def closure():
    paths = {'wc_benchmark_probe.dg': HERE / 'wc_benchmark_probe.dg'}
    pending = list(paths.values())
    while pending:
        source = pending.pop()
        for module in re.findall(r'(?m)^\s*import\s+([\w.]+)', source.read_text()):
            relative = module.replace('.', '/') + '.dg'
            if relative in paths:
                continue
            choices = [root / relative for root in (ROOT / 'kernel', ROOT / 'lang/std') if (root / relative).is_file()]
            if len(choices) != 1:
                raise AssertionError((module, choices))
            paths[relative] = choices[0]
            pending.append(choices[0])
    return paths


class WcBenchmarkTests(unittest.TestCase):
    def test_fresh_actual_runtime7_build_and_identity_no_guest(self):
        # This is a real current-source build, never a manufactured ELF or
        # manifest fixture. Only the coordinator executes this host gate.
        output = ROOT / 'build/test/p2-wc-fresh-build' / ('run-' + uuid.uuid4().hex[:12])
        output.parent.mkdir(parents=True, exist_ok=True)
        passed, failure = False, None
        evidence = dict(guest_executed=False, physical_wc_performance=False)
        try:
            record = stage.build(output)
            esp = Path(record['esp'])
            self.assertEqual(0, record['build_returncode'])
            self.assertTrue(record['built'] and record['os_link_executed']
                            and record['source_unchanged'] and record['tools_unchanged'])
            self.assertEqual({'build-command.json', 'build.stdout', 'build.stderr'}, set(record['log_sha256']))
            self.assertEqual(record, stage.identity(esp))
            manifest_path=esp.parent/'build-inputs.json'
            manifest_before=manifest_path.read_bytes();manifest=json.loads(manifest_before)
            profile_path=esp.parent/manifest['kernel_storage_profile']['source'];profile_before=profile_path.read_bytes()
            receipt_path=output/'wc-source.json';receipt_before=receipt_path.read_bytes()
            try:
                old=profile_before.replace(b'POOLS:usize=1;',b'POOLS:usize=2;');self.assertNotEqual(profile_before,old)
                profile_path.write_bytes(old);manifest['kernel_storage_profile'].update(static_user_pools=2,sha256=stage.sha(profile_path))
                manifest['artifacts'][str(profile_path.resolve())]=stage.sha(profile_path);stage.write(manifest_path,manifest)
                changed=copy.deepcopy(record)
                changed['artifacts_sha256'][profile_path.relative_to(esp.parent).as_posix()]=stage.sha(profile_path)
                changed['artifacts_sha256']['build-inputs.json']=stage.sha(manifest_path);stage.write(receipt_path,changed)
                with self.assertRaisesRegex(ValueError,'kernel storage'):stage.identity(esp)
                evidence['rehashed_historical_two_pool_profile_rejected']=True
            finally:
                profile_path.write_bytes(profile_before);manifest_path.write_bytes(manifest_before);receipt_path.write_bytes(receipt_before)
            self.assertEqual(record, stage.identity(esp))
            # Exercise the real CLI identity branch too. It cannot enter the
            # explicit --execute branch, and does not discover/start QEMU.
            command = [sys.executable, '-B', '-m', 'tests.run_p2_wc_benchmark', '--reuse-esp', str(esp)]
            try:
                result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=120)
            except subprocess.TimeoutExpired as exc:
                (output / 'identity.stdout').write_bytes(exc.stdout or b'')
                (output / 'identity.stderr').write_bytes(exc.stderr or b'')
                stage.write(output / 'identity-command.json', dict(argv=command, cwd=str(ROOT), returncode=None, timed_out=True))
                raise
            (output / 'identity.stdout').write_bytes(result.stdout)
            (output / 'identity.stderr').write_bytes(result.stderr)
            stage.write(output / 'identity-command.json', dict(argv=command, cwd=str(ROOT), returncode=result.returncode))
            self.assertEqual(0, result.returncode, result.stderr.decode('utf-8', 'replace'))
            reply = json.loads(result.stdout)
            self.assertEqual('identity-only', reply['mode'])
            self.assertIs(reply['guest_started'], False)
            self.assertIs(reply['physical_wc_performance'], False)
            self.assertEqual(record, reply['source_identity'])
            command_path = output / 'build-command.json'
            original = command_path.read_bytes()
            try:
                command_path.write_bytes(b'{"forged_command":true}\n')
                with self.assertRaisesRegex(ValueError, 'build command/log changed'):
                    stage.identity(esp)
                evidence['actual_command_tampering_rejected'] = True
            finally:
                command_path.write_bytes(original)
            self.assertEqual(record, stage.identity(esp))
            evidence.update(kernel_bytes=(esp.parent / 'kernel.bin').stat().st_size,
                            source_sha256=record['source_sha256'], staged_sha256=record['staged_sha256'],
                            artifacts_sha256=record['artifacts_sha256'], logs=record['log_sha256'],
                            tools=record['tools'], actual_identity_returncode=result.returncode)
            passed = True
        except BaseException as exc:
            failure = dict(type=type(exc).__name__, message=str(exc))
            raise
        finally:
            output.mkdir(parents=True, exist_ok=True)
            stage.write(output / 'fresh-build-test.json', dict(passed=passed, failure=failure, skipped=[], evidence=evidence))
            print('P2_WC_FRESH_BUILD_EVIDENCE', output)

    def test_real_paging_and_timing_asm_restore_guards_and_semantic_mutants(self):
        out = ROOT / 'build/test/p2-wc-native' / ('run-' + uuid.uuid4().hex[:12])
        out.mkdir(parents=True)
        sources = closure()
        files = set(sources.values()) | set((ROOT / 'lang/dongc').rglob('*.py')) | {
            ROOT / 'kernel/mm/wc_benchmark.asm', Path(__file__).resolve(), HERE / 'wc_benchmark_probe.c',
            HERE / 'p2_wc_stage.py', HERE / 'run_p2_wc_benchmark.py', ROOT / 'docs/p2-wc-benchmark.md'}
        hashes = lambda: {str(p.relative_to(ROOT)): stage.sha(p) for p in sorted(files)}
        before = hashes()
        stage.write(out / 'source-before.json', before)
        records, evidence, tools = [], [], {}
        passed, failure = False, None

        def command(argv, directory, label):
            argv = list(map(str, argv))
            row = dict(argv=argv, cwd=str(ROOT), label=label, timeout=False)
            start = time.monotonic()
            try:
                value = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=90)
                row.update(returncode=value.returncode)
                (directory / (label + '.stdout')).write_bytes(value.stdout)
                (directory / (label + '.stderr')).write_bytes(value.stderr)
                row.update(stdout=value.stdout.decode('utf-8', 'replace'), stderr=value.stderr.decode('utf-8', 'replace'))
                return value
            except subprocess.TimeoutExpired as exc:
                row.update(returncode=None, timeout=True)
                (directory / (label + '.stdout')).write_bytes(exc.stdout or b'')
                (directory / (label + '.stderr')).write_bytes(exc.stderr or b'')
                raise
            finally:
                row['elapsed_seconds'] = time.monotonic() - start
                records.append(row)
                stage.write(directory / (label + '.json'), row)
                stage.write(out / 'commands.json', records)
        try:
            nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
            self.assertTrue(nasm and cc, 'required native tools unavailable; gate never skips')
            tools = {n: dict(path=str(Path(p).resolve()), sha256=stage.sha(p)) for n, p in (('nasm', nasm), ('cc', cc))}
            help_result = command([nasm, '-h'], out, 'nasm-help')
            self.assertEqual(0, help_result.returncode)
            help_text = help_result.stdout.decode('utf-8', 'replace')
            if re.search(r'(?m)^\s*-h\s+-\S+', help_text):
                help_result = command([nasm, '-h', '-w'], out, 'nasm-warning-help')
                self.assertEqual(0, help_result.returncode)
                help_text += help_result.stdout.decode('utf-8', 'replace')
            flags = ['-Wall', '-Werror'] + ['-w-' + name for name in ('reloc-rel-dword', 'reloc-abs-qword')
                                         if re.search(r'(?m)^\s*' + re.escape(name) + r'\s', help_text)]
            original = (ROOT / 'kernel/mm/wc_benchmark.asm').read_text()
            variants = ((None, None, None), ('skip-restore', (' rep movsb', ' nop'), 'window-restored'),
                        ('write-overrun', (' jb .write', ' jbe .write'), 'write-window-guard'))
            for mode in ('debug', 'release'):
                for name, mutation, rejection in variants:
                    directory = out / mode / (name or 'production')
                    source_root = directory / 'src'
                    source_root.mkdir(parents=True)
                    for relative, path in sources.items():
                        destination = source_root / relative
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(path.read_bytes())
                    compiled = compile_file(source_root / 'wc_benchmark_probe.dg', roots=[source_root], mode=mode)
                    stage.write(directory / 'layout.json', compiled.layout_manifest)
                    source = directory / 'probe.asm'
                    source.write_text(compiled.assembly, encoding='utf-8')
                    body = original
                    if mutation:
                        self.assertEqual(1, body.count(mutation[0]))
                        body = body.replace(*mutation)
                    helper = directory / 'timing.asm'
                    helper.write_text(body, encoding='ascii')
                    objects = {}
                    for fmt in ('elf64', 'win64'):
                        objects[fmt] = []
                        for label, path in (('dong', source), ('timing', helper)):
                            target = directory / (label + '-' + fmt + '.o')
                            result = command([nasm, '-f', fmt, *flags, path, '-o', target], directory, label + '-' + fmt)
                            self.assertEqual(0, result.returncode, result.stderr.decode('utf-8', 'replace'))
                            objects[fmt].append(target)
                    executable = directory / ('probe.exe' if os.name == 'nt' else 'probe')
                    result = command([cc, '-std=c11', '-O2', '-D__USE_MINGW_ANSI_STDIO=1', '-Wall', '-Wextra', '-Werror',
                                      *(['-mno-sse'] if os.name == 'nt' else ['-no-pie']), HERE / 'wc_benchmark_probe.c',
                                      *objects['win64' if os.name == 'nt' else 'elf64'], '-o', executable], directory, 'link')
                    self.assertEqual(0, result.returncode, result.stderr.decode('utf-8', 'replace'))
                    result = command([executable], directory, 'native')
                    stdout, stderr = result.stdout.decode('utf-8', 'replace'), result.stderr.decode('utf-8', 'replace')
                    self.assertEqual(1 if rejection else 0, result.returncode, stdout + stderr)
                    if rejection:
                        self.assertIn('WC_ORACLE ' + rejection + ' normally', stderr)
                        self.assertNotIn('WC_BENCH_NATIVE_PASS', stdout)
                    else:
                        self.assertIn('WC_BENCH_NATIVE_PASS', stdout)
                        self.assertIn('hardware_cache=unknown physical_wc_performance=false', stdout)
                    evidence.append(dict(mode=mode, mutation=name, rejected_by=rejection,
                                         executable_sha256=stage.sha(executable), actual_returncode=result.returncode))
            self.assertEqual(before, hashes())
            passed = True
        except BaseException as exc:
            failure = dict(type=type(exc).__name__, message=str(exc))
            raise
        finally:
            after = hashes()
            stage.write(out / 'source-after.json', after)
            stage.write(out / 'validation-summary.json', dict(passed=passed and before == after, failure=failure,
                source_before=before, source_after=after, sources_unchanged=before == after,
                artifact_sha256={p.relative_to(out).as_posix(): stage.sha(p) for p in out.rglob('*') if p.is_file()
                                 and p.name != 'validation-summary.json'}, tools=tools, commands=records, evidence=evidence,
                skipped=[], actual_dong_paging=True, actual_timing_asm=True, hardware_cache='unknown',
                physical_wc_performance=False, guest_executed=False))
            print('P2_WC_NATIVE_EVIDENCE', out)

    def test_actual_source_prepare_exact_overlay_and_tampering(self):
        base = ROOT / 'build/test/p2-wc-prepare'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temporary:
            output = Path(temporary) / 'fresh'
            record = stage.prepare(output)
            self.assertFalse(record['built'])
            self.assertFalse(record['os_link_executed'])
            self.assertFalse(record['guest_executed'])
            self.assertEqual(sorted((stage.DG, stage.ASM)), record['overlay_paths'])
            self.assertEqual(record, stage.verify_prepared(output))
            self.assertFalse(any((output / 'source').rglob('*.elf')))
            with self.assertRaises(ValueError):
                stage.identity(output / 'image/esp')
            forged = copy.deepcopy(record)
            forged.update(built=True, os_link_executed=True, source_unchanged=True, tools_unchanged=True,
                          esp=str((output / 'image/esp').resolve()))
            stage.write(output / 'wc-source.json', forged)
            with self.assertRaisesRegex(ValueError, 'complete actual artifacts'):
                stage.identity(output / 'image/esp')
            stage.write(output / 'wc-source.json', record)
            path = output / 'source/kernel/mm/wc_benchmark.dg'
            path.write_bytes(path.read_bytes() + b'\n// unauthorized private edit\n')
            # Rehashing the staged manifest cannot legitimize an unapproved edit.
            record['staged_sha256']['kernel/mm/wc_benchmark.dg'] = stage.sha(path)
            stage.write(output / 'wc-source.json', record)
            with self.assertRaisesRegex(ValueError, 'noncanonical'):
                stage.verify_prepared(output)

    def test_raw_sample_cache_guards_and_receipt_cannot_be_self_certified(self):
        # A component-only host byte fixture, never a physical/guest receipt.
        v = [1, 2, 0, 0x400000, 0xffff800080000000, 0x80000000, 65536, 1000000000, 9,
             0xffffd40000100000, 65552, 0x9e3779b97f4a7c15, 7, 0x736176652d6c6f77, 0x7361766568696768]
        v += [100, 110, 120, 130, 140, 150, 160, 16]
        v += [(0x80000000 + i * 4096) | (1 << 63) | 27 for i in range(16)] + [0]
        self.assertEqual(9, runner.sample(struct_pack(v))['flags'])
        for index, value in ((1, 1), (2, 1), (6, 65544), (7, 0), (8, 17), (12, 6), (13, 0),
                             (15, 0), (22, 15), (23, v[23] | 4), (24, v[23])):
            bad = list(v)
            bad[index] = value
            with self.subTest(field=index), self.assertRaises(ValueError):
                runner.sample(struct_pack(bad))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'result.json'
            for record in ({'passed': True}, {'passed': True, 'environment': 'physical', 'physical_wc_performance': True},
                           {'passed': True, 'environment': 'qemu-virtual', 'physical_wc_performance': False, 'physical_gate_complete': False}):
                stage.write(path, record)
                with self.assertRaises(ValueError):
                    runner.replay(path)

    def test_default_prepare_and_identity_never_execute_guest(self):
        with mock.patch.object(stage, 'prepare', return_value={'built': False}) as prepare, \
                mock.patch.object(runner, 'execute', side_effect=AssertionError('VM forbidden')):
            self.assertEqual(0, runner.main(['--output', 'unused-host-only']))
            prepare.assert_called_once()
        with mock.patch.object(stage, 'identity', return_value={'host_fixture_only': True}), \
                mock.patch.object(runner, 'execute', side_effect=AssertionError('VM forbidden')):
            self.assertEqual(0, runner.main(['--reuse-esp', 'unused-host-only']))
        # Merely importing/parsing the entry point cannot invoke Popen/execute.
        tree = ast.parse((HERE / 'run_p2_wc_benchmark.py').read_text())
        self.assertTrue(any(isinstance(n, ast.FunctionDef) and n.name == 'execute' for n in tree.body))


def struct_pack(values):
    import struct
    return struct.pack('<40Q', *values)


if __name__ == '__main__':
    unittest.main(verbosity=2)
