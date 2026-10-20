"""Host-only KVM runner controls. No test starts QEMU or opens /dev/kvm."""
import copy
import json
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import boot_trace_oracle
from tests import run_p6_kvm_qemu as runner
from tools.mkimage import pack_image


def build_fixture(base):
    root, output = base / 'source', base / 'build'
    for tree in runner.TREES:
        (root / tree).mkdir(parents=True, exist_ok=True)
    (root / 'kernel/test.dg').write_text('module test;')
    esp = output / 'esp'
    (esp / 'EFI/BOOT').mkdir(parents=True)
    raw = b'\xc3' + bytes(31)
    elf = bytearray(4096 + len(raw))
    elf[:16] = b'\x7fELF\x02\x01\x01' + bytes(9)
    struct.pack_into('<HHIQQQIHHHHHH', elf, 16, 2, 62, 1, 0xffffffff80000000,
                     64, 0, 0, 64, 56, 1, 0, 0, 0)
    struct.pack_into('<IIQQQQQQ', elf, 64, 1, 5, 4096, 0xffffffff80000000,
                     0xffffffff80000000, len(raw), len(raw), 4096)
    elf[4096:] = raw
    files = {output / 'kernel.elf': bytes(elf), output / 'kernel.bin': raw,
             esp / 'DONGOS.IMG': pack_image(raw),
             esp / 'EFI/BOOT/BOOTX64.EFI': b'host fixture, never executed',
             esp / 'SERVICES.BIN': b'host fixture, never executed'}
    for path, data in files.items():
        path.write_bytes(data)
    metadata = dict(runtime_level=7, test=False, graphics_case=None, smp_case=None,
                    kernel_mode='release', source_unchanged=True,
                    source_sha256=runner.source_fingerprints(root),
                    artifacts={str(p): runner.sha(p) for p in files})
    runner.write(output / 'build-inputs.json', metadata)
    return root, esp, metadata


def decoded_fixture():
    raw = (Path(__file__).parent / 'fixtures/boot-trace-normal.bin').read_bytes()
    return boot_trace_oracle.decode(raw,
        dict(cpuid15=[1, 1000, 1000000], cpuid80000007_edx=256),
        dict(host_os='linux', actual_guest_boots=1,
             query_kvm=dict(enabled=True, present=True), artifact_bound=True))


class KvmRunnerTests(unittest.TestCase):
    def test_complete_requested_build_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root, esp, metadata = build_fixture(Path(temp))
            result = runner.verify_build(esp, root)
            self.assertEqual(str(esp), result['esp'])
            self.assertEqual(5, len(result['artifact_sha256']))
            self.assertEqual(metadata['source_sha256'], result['source_sha256'])

    def test_missing_extra_stale_and_redirected_artifacts_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root, esp, metadata = build_fixture(Path(temp))
            path = esp.parent / 'build-inputs.json'
            for name in metadata['artifacts']:
                bad = copy.deepcopy(metadata)
                del bad['artifacts'][name]
                runner.write(path, bad)
                with self.subTest(missing=name), self.assertRaises(ValueError):
                    runner.verify_build(esp, root)
            bad = copy.deepcopy(metadata)
            name = str(esp / 'DONGOS.IMG')
            other = Path(temp) / 'other.img'
            other.write_bytes((esp / 'DONGOS.IMG').read_bytes())
            bad['artifacts'][str(other)] = bad['artifacts'].pop(name)
            runner.write(path, bad)
            with self.assertRaisesRegex(ValueError, 'escaped requested ESP'):
                runner.verify_build(esp, root)
            runner.write(path, metadata)
            (esp / 'SERVICES.BIN').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'artifact changed'):
                runner.verify_build(esp, root)

    def test_empty_omitted_added_changed_source_inventory_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root, esp, metadata = build_fixture(Path(temp))
            path = esp.parent / 'build-inputs.json'
            for inventory in ({}, {'kernel/other.dg': '0' * 64}):
                bad = copy.deepcopy(metadata)
                bad['source_sha256'] = inventory
                runner.write(path, bad)
                with self.assertRaisesRegex(ValueError, 'complete current source'):
                    runner.verify_build(esp, root)
            runner.write(path, metadata)
            (root / 'kernel/new.dg').write_text('new module')
            with self.assertRaises(ValueError):
                runner.verify_build(esp, root)
            (root / 'kernel/new.dg').unlink()
            (root / 'kernel/test.dg').write_text('changed')
            with self.assertRaises(ValueError):
                runner.verify_build(esp, root)

    def test_flags_types_and_elf_image_cross_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root, esp, metadata = build_fixture(Path(temp))
            path = esp.parent / 'build-inputs.json'
            for key, value in (('test', 0), ('test', True), ('runtime_level', 6),
                               ('graphics_case', 'drop-ymm'), ('smp_case', 'bad'),
                               ('kernel_mode', 'debug'), ('source_unchanged', 1)):
                bad = copy.deepcopy(metadata)
                bad[key] = value
                runner.write(path, bad)
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'flag differs'):
                    runner.verify_build(esp, root)
            bad = copy.deepcopy(metadata)
            image = esp / 'DONGOS.IMG'
            image.write_bytes(pack_image(b'different'))
            bad['artifacts'][str(image)] = runner.sha(image)
            runner.write(path, bad)
            with self.assertRaisesRegex(ValueError, 'boot image and kernel differ'):
                runner.verify_build(esp, root)

    def test_symlinked_artifact_not_accepted_even_with_matching_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root, esp, metadata = build_fixture(Path(temp))
            target = esp / 'SERVICES.BIN'
            moved = Path(temp) / 'services-copy'
            target.rename(moved)
            target.symlink_to(moved)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                runner.verify_build(esp, root)

    def test_source_symlink_directory_cannot_hide_unbound_modules(self):
        with tempfile.TemporaryDirectory() as temp:
            root, esp, metadata = build_fixture(Path(temp))
            external = Path(temp) / 'external'
            external.mkdir()
            (external/'unbound.dg').write_text('module unbound;')
            (root/'kernel/included').symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlink in source inventory'):
                runner.verify_build(esp, root)

    def test_preflight_fails_closed_without_linux_device_or_access(self):
        with mock.patch.object(runner.sys, 'platform', 'win32'):
            with self.assertRaisesRegex(ValueError, 'Linux'):
                runner.preflight()
        with mock.patch.object(runner.sys, 'platform', 'linux'), \
             mock.patch.object(Path, 'exists', return_value=False):
            with self.assertRaisesRegex(ValueError, 'no TCG fallback'):
                runner.preflight()
        with mock.patch.object(runner.sys, 'platform', 'linux'), \
             mock.patch.object(Path, 'exists', return_value=True), \
             mock.patch.object(Path, 'stat', return_value=SimpleNamespace(st_mode=stat.S_IFCHR)), \
             mock.patch.object(runner.os, 'access', return_value=False):
            with self.assertRaisesRegex(ValueError, 'not readable and writable'):
                runner.preflight()

    def test_exact_kvm_command_no_tcg_or_host_clock_metric(self):
        base = ['qemu', '-accel', 'kvm', '-smp', '4', '-serial', 'unused',
                '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
        with mock.patch.object(runner.builder, 'qemu_command', return_value=base.copy()) as command:
            value = runner.command_for(Path('esp'), Path('state'), Path('disk'), 1000, 1001)
            self.assertEqual('kvm', command.call_args.kwargs['accel'])
        self.assertIn('-S', value)
        self.assertEqual('host,migratable=off', value[value.index('-cpu') + 1])
        self.assertNotIn('tcg', ' '.join(value))
        self.assertNotIn('isa-debug-exit', ' '.join(value))
        for bad in (base[:2] + ['tcg'] + base[3:], base + ['-accel', 'tcg']):
            with mock.patch.object(runner.builder, 'qemu_command', return_value=bad):
                with self.assertRaises(ValueError):
                    runner.command_for(Path('esp'), Path('state'), Path('disk'), 1000, 1001)

    def test_accelerator_query_must_be_actual_true_booleans(self):
        self.assertEqual(dict(enabled=True, present=True),
                         runner.require_kvm(dict(enabled=True, present=True)))
        for value in ({}, {'enabled': 1, 'present': True},
                      {'enabled': True, 'present': 1},
                      {'enabled': False, 'present': True}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                runner.require_kvm(value)

    def test_rejected_accelerator_never_continues_guest(self):
        with tempfile.TemporaryDirectory() as temp:
            guest = runner.KvmGuest(Path(temp) / 'esp', Path(temp), 1)
            qmp = mock.Mock()
            qmp.request.return_value = dict(enabled=False, present=True)
            with mock.patch.object(runner, 'create'), \
                 mock.patch.object(runner, 'command_for', return_value=['not executed']), \
                 mock.patch.object(runner.subprocess, 'Popen') as process, \
                 mock.patch.object(runner.clock.acpi, 'QMP', return_value=qmp), \
                 mock.patch.object(runner.socket, 'create_connection',
                                   side_effect=AssertionError('too early')):
                with self.assertRaisesRegex(ValueError, 'query-kvm'):
                    guest.start()
                self.assertEqual(['query-kvm'], [c.args[0] for c in qmp.request.call_args_list])
                process.assert_called_once()
            guest.stderr.close()

    def test_successful_start_queries_kvm_before_only_cont_and_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            guest = runner.KvmGuest(Path(temp) / 'esp', Path(temp), 1)
            guest.raw = bytearray(b''.join(runner.MARKERS) +
                b'memory_runtime_boot_info=0xffff800000001000\r\n')
            qmp = mock.Mock()
            qmp.request.side_effect = lambda command, *args: (
                dict(enabled=True, present=True) if command == 'query-kvm'
                else dict(running=False) if command == 'query-status' else {})
            uart = mock.Mock()
            uart.recv.return_value = b''
            boot = [0] * 20
            boot[15] = 0x200000
            with mock.patch.object(runner, 'create'), \
                 mock.patch.object(runner, 'command_for', return_value=['not executed']), \
                 mock.patch.object(runner.subprocess, 'Popen'), \
                 mock.patch.object(runner.clock.acpi, 'QMP', return_value=qmp), \
                 mock.patch.object(runner.socket, 'create_connection', return_value=uart), \
                 mock.patch.object(runner, 'read_elf_symbols', return_value={}), \
                 mock.patch.object(guest, 'physical', return_value=struct.pack('<20Q', *boot)):
                guest.start()
            self.assertEqual(['query-kvm', 'query-status', 'cont', 'stop', 'query-status'],
                             [c.args[0] for c in qmp.request.call_args_list])
            self.assertEqual(1, guest.evidence['actual_kvm_boots'])
            self.assertFalse(guest.evidence['init_cross_ap_proven'])
            guest.reader.join(timeout=2)
            guest.stderr.close()

    def test_failure_in_same_batch_as_readiness_is_rejected(self):
        ready = b''.join(runner.MARKERS)
        runner.check_startup_failure(ready)
        for failure in (b'PANIC', b'DONGOS_P1_KERNEL_FAIL', b'DONGOS_INIT_FAILURE 2'):
            with self.subTest(failure=failure), self.assertRaisesRegex(ValueError, 'startup failure'):
                runner.check_startup_failure(ready + failure)

    def test_start_rejects_failure_with_readiness_or_while_stopping(self):
        for phase in ('cont', 'stop'):
            for failure in (b'PANIC', b'DONGOS_P1_KERNEL_FAIL', b'DONGOS_INIT_FAILURE 2'):
                with self.subTest(phase=phase, failure=failure), \
                     tempfile.TemporaryDirectory() as temp:
                    guest = runner.KvmGuest(Path(temp) / 'esp', Path(temp), 1)

                    def respond(command, *args):
                        if command == 'query-kvm':
                            return dict(enabled=True, present=True)
                        if command == 'query-status':
                            return dict(running=False)
                        if command == 'cont':
                            guest.raw.extend(b''.join(runner.MARKERS))
                        if command == phase:
                            guest.raw.extend(failure + b'\r\n')
                        return {}

                    qmp = mock.Mock()
                    qmp.request.side_effect = respond
                    try:
                        with mock.patch.object(runner, 'create'), \
                             mock.patch.object(runner, 'command_for', return_value=['not executed']), \
                             mock.patch.object(runner.subprocess, 'Popen'), \
                             mock.patch.object(runner.clock.acpi, 'QMP', return_value=qmp), \
                             mock.patch.object(runner.socket, 'create_connection'), \
                             mock.patch.object(runner.threading, 'Thread'), \
                             mock.patch.object(runner, 'read_elf_symbols') as symbols, \
                             mock.patch.object(guest, 'physical') as physical:
                            with self.assertRaisesRegex(ValueError, 'startup failure'):
                                guest.start()
                            symbols.assert_not_called()
                            physical.assert_not_called()
                        expected = ['query-kvm', 'query-status', 'cont']
                        if phase == 'stop':
                            expected += ['stop', 'query-status']
                        self.assertEqual(expected, [c.args[0] for c in qmp.request.call_args_list])
                        self.assertNotIn('stopped_for_capture', guest.evidence)
                    finally:
                        if guest.stderr:
                            guest.stderr.close()

    def test_exact_500ms_boundary_and_eligibility(self):
        good = decoded_fixture()
        self.assertEqual(449999000, runner.timing_pass(good))
        for ns, valid in ((500000000, True), (500000001, False), (0, False),
                          (True, False), (500000000.0, False)):
            value = copy.deepcopy(good)
            value['intervals']['loader_to_interactive_shell_upper_ns'] = ns
            if valid:
                self.assertEqual(ns, runner.timing_pass(value))
            else:
                with self.subTest(ns=ns), self.assertRaises(ValueError):
                    runner.timing_pass(value)
        for key in ('kvm_gate_eligible', 'invariant_tsc', 'kvm_gate_passed'):
            value = copy.deepcopy(good)
            value[key] = False
            with self.subTest(key=key), self.assertRaises(ValueError):
                runner.timing_pass(value)
        good['header']['online_mask'] = 3
        with self.assertRaises(ValueError):
            runner.timing_pass(good)

    def test_cleanup_still_kills_process_after_connection_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            guest = runner.KvmGuest(Path(temp) / 'esp', Path(temp), 1)
            guest.qmp = mock.Mock()
            guest.qmp.request.side_effect = OSError('socket gone')
            guest.qmp.close.side_effect = OSError('close gone')
            guest.process = mock.Mock()
            guest.process.wait.side_effect = [subprocess.TimeoutExpired('owned', 10), 0]
            guest.process.poll.return_value = -9
            guest.close()
            guest.process.kill.assert_called_once()
            self.assertEqual(2, guest.process.wait.call_count)
            self.assertTrue((Path(temp) / 'physical-manifest.json').is_file())
            self.assertEqual(-9, guest.evidence['qemu_shutdown_returncode'])

    def test_preflight_error_retains_failure_without_starting_guest(self):
        with tempfile.TemporaryDirectory() as temp, \
             mock.patch.object(runner, 'preflight', side_effect=ValueError('no KVM')), \
             mock.patch.object(runner, 'KvmGuest', side_effect=AssertionError('must not start')):
            state = Path(temp) / 'result'
            result = runner.run(Path('unused'), state, 1)
            self.assertFalse(result['passed'])
            self.assertFalse(result['actual_qemu_executed'])
            self.assertFalse(result['init_cross_ap_proven'])
            self.assertEqual(0, result['actual_kvm_boots'])
            self.assertIn('no KVM', json.loads((state / 'result.json').read_text())['error'])

    def test_orchestration_binds_before_after_and_always_closes(self):
        for capture_fails, changed in ((False, False), (True, False), (False, True)):
            with self.subTest(capture_fails=capture_fails, changed=changed), \
                 tempfile.TemporaryDirectory() as temp:
                binding = {'esp': str(Path(temp) / 'esp'), 'build': 'exact fixture'}
                guest = mock.Mock()
                guest.evidence = dict(actual_qemu_executed=True, actual_kvm_boots=1)
                guest.raw = b''.join(runner.MARKERS)
                guest.process.poll.return_value = 0
                capture = mock.Mock(return_value=decoded_fixture())
                if capture_fails:
                    capture.side_effect = ValueError('corrupt captured trace')
                with mock.patch.object(runner, 'preflight', return_value={'host_os': 'linux'}), \
                     mock.patch.object(runner, 'verify_build',
                                       side_effect=[binding, {} if changed else binding]) as verify, \
                     mock.patch.object(runner, 'KvmGuest', return_value=guest), \
                     mock.patch.object(runner.boot_trace_capture, 'capture', capture):
                    result = runner.run(Path('unused'), Path(temp) / 'result', 1)
                self.assertEqual(2, verify.call_count)
                guest.start.assert_called_once()
                guest.close.assert_called_once()
                self.assertEqual(not (capture_fails or changed), result['passed'])
                self.assertEqual(1, result['actual_kvm_boots'])
                self.assertFalse(result['init_cross_ap_proven'])
                self.assertTrue(result['all_started_guests_stopped'])
                self.assertEqual(capture_fails, guest.capture_failure.called)

    def test_preflight_only_is_not_kvm_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            binding = {'esp': str(Path(temp) / 'esp')}
            with mock.patch.object(runner, 'preflight', return_value={'host_os': 'linux'}), \
                 mock.patch.object(runner, 'verify_build', return_value=binding), \
                 mock.patch.object(runner, 'KvmGuest', side_effect=AssertionError('must not start')):
                result = runner.run(Path('unused'), Path(temp) / 'result', 1, True)
            self.assertTrue(result['preflight_passed'])
            self.assertFalse(result['passed'])
            self.assertEqual(0, result['actual_kvm_boots'])

    def test_timeout_bounds_and_existing_evidence_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            for timeout in (0, float('nan'), float('inf'), 301):
                with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                    runner.run(Path('unused'), Path(temp) / 'new', timeout)
            with self.assertRaises(FileExistsError):
                runner.run(Path('unused'), Path(temp), 1)


if __name__ == '__main__':
    unittest.main()
