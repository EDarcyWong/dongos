"""Synthetic source preparation controls. No compiler link, OS, VM or fake success."""
import hashlib
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from tests import p2_pcid_build as b
from tools.kernel_storage_profile import generate, module_bytes


def synthetic_source(root):
    files = {'kernel/input.dg': 'module input;\n',
             'kernel/sched/user_arch.asm': 'bits 64\n    or rdi,rsi\n',
             'services/lib/syscalls.asm': 'bits 64\n; synthetic bridge\n',
             'tools/build.py': '# synthetic source only, never executed\n',
             'tests/fixtures/current_user_smp/services/apps/user_smp_worker.dg': 'module apps.user_smp_worker;\n',
             'tests/fixtures/current_user_smp/services/apps/user_smp_worker.asm': 'bits 64\n; synthetic workload source only\n'}
    files.update({'services/apps/' + app + '.dg': 'module apps.synthetic_' + app + ';\n' for app in b.APPS})
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return b.inputs(root)


class BuildTests(unittest.TestCase):
    def test_prepare_exact_private_workload_and_no_build_or_vm(self):
        for case in b.CASES:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / 'synthetic-source'
                before = synthetic_source(root)
                output = Path(temp) / 'prepared'
                with mock.patch.object(subprocess, 'run', side_effect=AssertionError('prepare must not run tools')):
                    record = b.prepare(output, source_root=root, case=case)
                    self.assertEqual(record, b.verify_prepared(output, source_root=root))
                self.assertEqual(before, b.inputs(root))
                self.assertFalse(record['built'])
                self.assertFalse(record['os_link_executed'])
                self.assertFalse(record['guest_executed'])
                self.assertEqual(6 + int(case is not None), len(record['overlay_paths']))
                self.assertFalse((output / 'image/kernel.elf').exists())
                if case:
                    self.assertIn(b'or rdi,17', (output / 'source/kernel/sched/user_arch.asm').read_bytes())
                with self.assertRaisesRegex(ValueError, 'fresh'):
                    b.prepare(output, source_root=root)
                with self.assertRaisesRegex(ValueError, 'completed real'):
                    b.identity(output / 'image/esp', source_root=root)

    def test_source_and_unenumerated_staged_mutation_are_rejected(self):
        for target in ('source', 'overlay', 'forged-overlay-receipt', 'missing-source'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / 'synthetic-source'
                synthetic_source(root)
                output = Path(temp) / 'prepared'
                record = b.prepare(output, source_root=root)
                name = 'kernel/sched/user_arch.asm'
                if target == 'source':
                    (root / name).write_bytes(b'changed current source')
                elif target == 'missing-source':
                    (root / name).unlink()
                else:
                    path = output / 'source' / name
                    path.write_bytes(b'changed undeclared kernel implementation')
                    if target == 'forged-overlay-receipt':
                        record['staged_sha256'][name] = b.sha(path)
                        record['overlay_paths'].append(name)
                        record['overlay_paths'].sort()
                        b.write(output / 'p2-pcid-source.json', record)
                with self.assertRaises(ValueError):
                    b.verify_prepared(output, source_root=root)

    def test_failed_real_entry_retains_failure_and_never_marks_built(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'synthetic-source'
            synthetic_source(root)
            output = Path(temp) / 'failed-build'
            # Explicit failed boundary injection; no fabricated successful ELF
            # or manifest is ever supplied to the implementation.
            with mock.patch('tools.build.find_tool', return_value=sys.executable), \
                    mock.patch.object(b.subprocess, 'run', return_value=subprocess.CompletedProcess(['synthetic-failure'], 23)) as run:
                with self.assertRaisesRegex(ValueError, 'actual production build failed'):
                    b.build(output, source_root=root)
            record = json.loads((output / 'p2-pcid-source.json').read_text())
            self.assertFalse(record['built'])
            self.assertFalse(record['os_link_executed'])
            self.assertIn('build_error', record)
            self.assertTrue((output / 'build.log').is_file())
            command = run.call_args.args[0]
            self.assertEqual([sys.executable, '-B', '-c'], command[:3])
            self.assertIn('runtime_level=7,test=True', command[3])
            self.assertEqual(output / 'source', run.call_args.kwargs['cwd'])

    def test_unknown_case_and_escaped_manifest_path_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'synthetic-source'
            synthetic_source(root)
            with self.assertRaisesRegex(ValueError, 'unknown'):
                b.prepare(Path(temp) / 'bad', source_root=root, case='fake-pcid')
            with self.assertRaisesRegex(ValueError, 'unsafe'):
                b.file_at(root, '../outside')

    def test_forged_sparse_completed_receipt_cannot_become_build_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'synthetic-source'
            synthetic_source(root)
            output = Path(temp) / 'forged-not-built'
            record = b.prepare(output, source_root=root)
            (output / 'image/esp').mkdir(parents=True)
            one = output / 'image/one.txt'
            one.write_bytes(b'synthetic forgery, no compiler ran')
            (output / 'build.log').write_bytes(b'synthetic non-build log')
            record.update(synthetic=True, built=True, os_link_executed=True, source_unchanged=True,
                          esp=str(output / 'image/esp'), artifacts_sha256={'one.txt': b.sha(one)},
                          build_tools_sha256={str(Path(sys.executable).resolve()): b.sha(sys.executable)},
                          build_log_sha256=b.sha(output / 'build.log'))
            b.write(output / 'p2-pcid-source.json', record)
            with self.assertRaisesRegex(ValueError, 'required real build artifacts'):
                b.identity(output / 'image/esp', source_root=root)

    def test_each_required_artifact_is_mandatory_even_with_forged_success_flags(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'synthetic-source'
            synthetic_source(root)
            output = Path(temp) / 'forged-not-built'
            record = b.prepare(output, source_root=root)
            target = output / 'image'
            # These labeled placeholders are rejection inputs only. No complete
            # fake build is validated or returned as a successful identity.
            for name in b.required_artifacts():
                path = target / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'synthetic invalid artifact, never linked')
            record.update(synthetic=True, built=True, os_link_executed=True, source_unchanged=True,
                          esp=str(target / 'esp'), artifacts_sha256=b.artifacts(target))
            b.write(output / 'p2-pcid-source.json', record)
            for name in sorted(b.required_artifacts()):
                path = target / name
                data = path.read_bytes()
                path.unlink()
                try:
                    with self.subTest(missing=name), self.assertRaisesRegex(ValueError, 'missing/escaped'):
                        b.identity(target / 'esp', source_root=root)
                finally:
                    path.write_bytes(data)

    def test_command_cwd_environment_and_log_are_rederived_not_just_rehashed(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            roles = {name: dict(path=str(Path(sys.executable).resolve()), sha256=b.sha(sys.executable))
                     for name in ('python', 'nasm', 'ld.lld', 'lld-link')}
            for kind in ('argv', 'cwd', 'environment', 'log'):
                spec = b.command_spec(output, roles)
                if kind == 'argv':
                    spec['argv'][-1] = 'print("synthetic substituted command")'
                elif kind == 'cwd':
                    spec['cwd'] = str(output / 'wrong-source')
                elif kind == 'environment':
                    spec['environment_overrides']['NASM'] = 'synthetic-other-nasm'
                b.write(output / 'build-command.json', spec)
                (output / 'build.log').write_bytes(b'synthetic rejection input, no build ran')
                record = dict(synthetic=True, build_tool_roles=roles, build_returncode=0,
                              build_command_sha256=b.sha(output / 'build-command.json'),
                              build_log_sha256=b.sha(output / 'build.log'))
                if kind == 'log':
                    (output / 'build.log').write_bytes(b'changed after the alleged boundary')
                with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'command/cwd/environment|log changed'):
                    b.verify_command(output, record)

    def test_compiler_tool_roles_must_be_exact_and_current(self):
        roles = {name: dict(path=str(Path(sys.executable).resolve()), sha256=b.sha(sys.executable))
                 for name in ('python', 'nasm', 'ld.lld', 'lld-link')}
        for missing in roles:
            partial = {name: value for name, value in roles.items() if name != missing}
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, 'exact four'):
                b.verify_tools(dict(synthetic=True, build_tool_roles=partial))
        changed = {name: dict(value) for name, value in roles.items()}
        changed['nasm']['sha256'] = '0' * 64
        with mock.patch.object(b, 'resolve_tools', return_value=roles):
            with self.assertRaisesRegex(ValueError, 'tool identity changed'):
                b.verify_tools(dict(synthetic=True, build_tool_roles=changed))
            with self.assertRaisesRegex(ValueError, 'tool hash set differs'):
                b.verify_tools(dict(synthetic=True, build_tool_roles=roles, build_tools_sha256={}))

    def test_production_manifest_replacement_is_rejected_after_hash_refresh(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'synthetic-source'
            synthetic_source(root)
            output = Path(temp) / 'not-built'
            record = b.prepare(output, source_root=root)
            for name in b.PRODUCTION_ARTIFACTS:
                path = output / 'image' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'explicit synthetic invalid production artifact')
            profile = output / 'image/kernel-profile-src/build/storage_profile.dg'
            profile.write_bytes(module_bytes(7))
            for bad in ({'runtime_level': 6}, {'runtime_level': 7, 'test': True, 'source_sha256': {}},
                        {'runtime_level': 7, 'source_unchanged': True, 'artifacts': {}}):
                manifest = output / 'image/build-inputs.json'
                b.write(manifest, dict(synthetic=True, **bad))
                record['production_manifest_sha256'] = b.sha(manifest)
                with self.subTest(manifest=bad), self.assertRaisesRegex(ValueError, 'kernel storage'):
                    b.verify_production(output, record)

    def test_rehashed_old_runtime7_profile_and_omitted_input_cannot_pass_production(self):
        for kind in ('old-rehashed','omitted-input'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root=Path(temp)/'synthetic-source';synthetic_source(root)
                output=Path(temp)/'not-built';record=b.prepare(output,source_root=root)
                target=output/'image';_,profile=generate(target,7,output/'source/kernel')
                production=dict(runtime_level=7,source_unchanged=True,source_sha256=record['staged_sha256'],kernel_storage_profile=profile)
                if kind=='old-rehashed':
                    path=target/profile['source'];raw=module_bytes(7).replace(b'POOLS:usize=1;',b'POOLS:usize=2;');path.write_bytes(raw)
                    production['kernel_storage_profile'].update(static_user_pools=2,sha256=hashlib.sha256(raw).hexdigest())
                else:
                    production=copy.deepcopy(production);del production['source_sha256']['kernel/input.dg'];del production['kernel_storage_profile']['kernel_sources']['input.dg']
                    (target/'kernel-profile-src/input.dg').unlink()
                b.write(target/'build-inputs.json',production);record['production_manifest_sha256']=b.sha(target/'build-inputs.json')
                with self.assertRaisesRegex(ValueError,'kernel storage'):b.verify_production(output,record)


if __name__ == '__main__':
    unittest.main()
