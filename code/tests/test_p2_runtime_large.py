"""Host controls and real current-source OS builds; this suite never boots VM."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest import mock
import uuid
from tests import p2_runtime_large_build as build
from tests import run_p2_runtime_large_qemu as runner

ROOT = Path(__file__).resolve().parents[1]


def qemu_launch_fixture():
    """Complete synthetic builder argv; never a process or guest receipt."""
    return ['qemu', '-machine', 'q35', '-smp', '4', '-accel', 'whpx', '-cpu', 'host',
            '-m', '2G', '-net', 'none', '-monitor', 'none', '-no-reboot', '-S',
            '-drive', 'if=pflash,format=raw,readonly=on,file=C:/fw/OVMF_CODE.fd',
            '-drive', 'if=pflash,format=raw,file=C:/state/OVMF_VARS.fd',
            '-drive', 'format=raw,file=fat:rw:C:/image/esp',
            '-drive', 'if=none,id=data,format=raw,cache=writeback,file=C:/state/data.img',
            '-device', 'nvme,drive=data,serial=DONGOS-NVME']


def reader_fixture():
    """Explicit synthetic host ABI, never a guest execution receipt."""
    report = dict(root=0x4000000, online=15)
    metrics = [[10, 5, 2, 3, 0, 0] + [0] * 12 + [0x20000] + [0] * 5 for _ in range(4)]
    readers = []
    for cpu in range(16):
        r = dict(request=4 if cpu < 4 else 0, ack=4 if cpu < 4 else 0, count=4 if cpu < 4 else 0)
        for name in ['warm', 'replaced', 'restored', 'merged']:
            r[name] = dict(cpu=cpu, root=report['root'], cr4=0x20000, value=runner.TAG | (6 if name == 'replaced' else 5))
        readers.append(r)
    return report, readers, metrics


def barrier_fixture(*, negative=False, later=0):
    """Explicit raw Domain/Cpu/HMP host data; no guest or load evidence."""
    root, post, cr4 = 0x4000000, 41, 1 << 17
    sequence = post + later
    domain = [1, int(negative), int(negative), 0 if negative else 16, 15,
              sequence, 0, 0, sequence, root, 0, 0, 0, 0, 0]
    cpus = [[1, 0, 0, 16] + [0] * 11 for _ in range(16)]
    cpus[0][0] = 5 if negative else 4
    for cpu in range(4):
        cpus[cpu][7:9] = [sequence, sequence]
    metrics = [[0] * 18 + [cr4] + [0] * 5 for _ in range(4)]
    registers = [dict(CS=8, CR3=root, CR4=cr4) for _ in range(4)]
    return dict(report=dict(root=root, online=15, pre_sequence=post - 1, post_sequence=post),
                domain=domain, cpus=cpus, metrics=metrics, registers=registers)


def kernel_barrier_fixture(*, pending=True):
    """Explicit v2 host boundary; never a raw guest observation."""
    decoded = barrier_fixture(later=7)
    completed = decoded['domain'][8]
    decoded['bridge'] = [1, 0] + [0] * 6
    decoded['header_addresses'] = [0xffffd40002000000 + cpu * 32768 for cpu in range(4)]
    if pending:
        sequence = completed + 1
        decoded['domain'][2:4] = [1, 0]
        decoded['domain'][5:8] = [sequence, sequence, 15]
        decoded['cpus'][0][0] = 5
        decoded['cpus'][1][7:9] = [sequence, sequence]
        decoded['cpus'][2][7:9] = [sequence, completed]
        decoded['cpus'][2][0] = 4
    for cpu, reg in enumerate(decoded['registers']):
        reg.update(GS_base=decoded['header_addresses'][cpu], RFL=2 if decoded['cpus'][cpu][0] in (4, 5) else 0x202)
    return decoded


def kernel_validation_fixture(*, pending=True):
    after = kernel_barrier_fixture(pending=pending)
    physical, payload, checksum = 0x10000000, b'explicit host oracle boundary', 123
    before = dict(synthetic=False, report={'attempted': 0}, requested=False, physical=physical, payload=payload)
    after.update(synthetic=False, requested=True, physical=physical, payload=payload, readers=[],
                 kernel_image=b'host boundary', kernel_meta=b'host boundary',
                 kernel_space=struct.pack('<8Q', 1, 0, 128, after['report']['root'], 0, 0, 0, 0))
    after['report'].update(version=1, attempted=1, physical=physical, old_checksum=checksum,
                          final_checksum=checksum, complete=1, poison=0, error_code=0, state=0, steps=127,
                          barriers=16, retired=2, reclaimed=2, tables_before=75, tables_after=75)
    return before, after


def kernel_fixture(negative=False):
    """Independent synthetic raw tree used only to test decoder rejection."""
    base, held = 0x400000, 0x10000000
    image, meta = bytearray(128 * 4096), bytearray(128)
    for index in range(3 + bool(negative)):
        meta[index] = 1
    put = lambda table, slot, value: struct.pack_into('<Q', image, table * 4096 + slot * 8, value)
    put(0, (runner.OLD >> 39) & 511, base + 4096 | 7)
    put(1, 0, base + 8192 | 7)
    put(2, 0, held | runner.NX | 131)
    if negative:
        put(2, 1, base + 12288 | 7)
        for page in range(512):
            put(3, page, held + (6 if page == 5 else page) * 4096 | runner.NX | 3)
    space = struct.pack('<8Q', 1, 0xffffd40000000000, 128, base, 0xffffd40001000000,
                        (1 << 48) - 4096, 1, 3 + bool(negative))
    return image, meta, space, held


class HostOracleTests(unittest.TestCase):
    def test_boot_info_is_the_exact_twenty_qword_abi(self):
        words = [0x544f4f42474e4f44, 1, 160] + [0x100000000 + i for i in range(17)]
        data = struct.pack('<20Q', *words)
        self.assertEqual(words, runner.decode_boot_info(data))
        for field, value in ((0, 160 | (1 << 32)), (0, 0), (1, 0), (1, 1 + (1 << 32)),
                             (2, 152), (2, 160 + (1 << 32))):
            bad = words.copy();bad[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                runner.decode_boot_info(struct.pack('<20Q', *bad))
        for bad in (data[:-8], data + bytes(8), struct.pack('<2I', 160, 1) + bytes(152)):
            with self.assertRaises(ValueError):
                runner.decode_boot_info(bad)

    def test_bound_profile_makes_slot_one_dynamic_and_rejects_static_aliases(self):
        static, tables, physical, virtual = 0x800000, 0xffffffff80100000, 0x2000000, 0xffff800002000000
        runner.validate_pool_provenance(0, static, tables, 32, 0, 0, static, tables, static_pools=1)
        runner.validate_pool_provenance(1, physical, virtual, 32, physical, virtual, static, tables, static_pools=1)
        runner.validate_pool_provenance(3, physical, virtual, 128, physical, virtual, static, tables, static_pools=1)
        for args in (
                (1, static + 32 * 4096, tables + 32 * 4096, 32, 0, 0),
                (1, physical, virtual, 32, physical + 4096, virtual),
                (1, physical, virtual, 32, physical, virtual + 4096),
                (1, physical, virtual, 128, physical, virtual),
                (1, physical | 1, virtual, 32, physical | 1, virtual),
                (0, static, tables, 32, physical, virtual),
                (0, static, tables + 4096, 32, 0, 0)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                runner.validate_pool_provenance(*args, static, tables, static_pools=1)

    def test_whpx_irqchip_option_is_explicit_and_real_argv_cannot_be_rehashed_away(self):
        base = qemu_launch_fixture()
        actual = runner.pcid.launch_command(base, accel='whpx', cpu='host', kernel_irqchip='off')
        self.assertIn('q35,kernel-irqchip=off', actual)
        runner.pcid.verify_launch_command(actual, accel='whpx', cpu='host', kernel_irqchip='off')
        for command, option in ((base, 'off'), (actual, None),
                                (actual + ['-machine', 'q35,kernel-irqchip=off'], 'off')):
            with self.assertRaises(ValueError):
                runner.pcid.verify_launch_command(command, accel='whpx', cpu='host', kernel_irqchip=option)
        with mock.patch.object(build, 'identity') as identity, mock.patch.object(runner, 'LargeGuest') as guest:
            with self.assertRaisesRegex(ValueError, 'WHPX-only'):
                runner.execute('unused', 'unused', accel='tcg', kernel_irqchip='off')
            identity.assert_not_called();guest.assert_not_called()
        with mock.patch.object(runner, 'execute', return_value={'passed': True}) as execute:
            self.assertEqual(0, runner.main(['--execute', '--reuse-esp', 'host-control', '--accel', 'whpx',
                                            '--kernel-irqchip', 'off']))
            self.assertEqual('off', execute.call_args.kwargs['kernel_irqchip'])

    def test_b_execute_uses_real_strict_whpx_drive_gate_before_inventory_or_collection(self):
        """Explicit host IO adapters stop before collection; no VM/pass evidence."""
        actual = runner.pcid.launch_command(qemu_launch_fixture(), accel='whpx', cpu='host', kernel_irqchip='off')
        variables = next(value for value in actual if 'file=C:/state/OVMF_VARS.fd' in value)
        variants = {'valid': actual,
                    'missing-vars-cache': [value.replace(',cache=writethrough', '') for value in actual],
                    'unsafe-vars-cache': [value.replace('cache=writethrough', 'cache=unsafe') for value in actual],
                    'changed-data-cache': [value.replace('cache=writeback', 'cache=writethrough') for value in actual],
                    'duplicate-vars': actual + ['-drive', variables]}
        class ReachedCollection(ValueError):pass
        for name, command in variants.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / 'fresh';instances = []
                identity = {'case': None, 'synthetic_host_boundary': True}
                def create(disk, size):disk.write_bytes(b'explicit host disk adapter')
                class Guest:
                    def __init__(self, esp, disk, state, **kwargs):
                        state.mkdir()
                        (state / 'physical-manifest.json').write_text('[]\n')
                        (state / 'serial.log').write_bytes(b'explicit host UART adapter')
                        self.evidence = dict(command=copy.deepcopy(command), synthetic_host_boundary=True)
                        self.qmp = mock.Mock();self.qmp.request.return_value = []
                        self.closed = False;instances.append(self)
                    def close(self):self.closed = True
                with mock.patch.object(build, 'identity', return_value=identity), \
                     mock.patch.object(runner, 'create', side_effect=create), \
                     mock.patch.object(runner, 'source_tools', return_value={}), \
                     mock.patch.object(runner, 'LargeGuest', Guest), \
                     mock.patch.object(runner.pcid, 'verify_launch_command', wraps=runner.pcid.verify_launch_command) as verify, \
                     mock.patch.object(runner, 'collect_boot', side_effect=ReachedCollection('next independent boundary')) as collect, \
                     mock.patch.object(runner, 'replay') as replay, \
                     mock.patch('subprocess.Popen', side_effect=AssertionError('host adapter cannot start VM')) as popen:
                    with self.assertRaises(ReachedCollection if name == 'valid' else ValueError):
                        runner.execute('host-only', output, accel='whpx', cpu='host', kernel_irqchip='off')
                    verify.assert_called_once_with(command, accel='whpx', cpu='host', kernel_irqchip='off')
                    self.assertEqual(1, len(instances));self.assertTrue(instances[0].closed)
                    if name == 'valid':
                        instances[0].qmp.request.assert_called_once_with('query-cpus-fast')
                        collect.assert_called_once()
                        self.assertEqual(runner.LEGACY_OBSERVATION, collect.call_args.kwargs['normal_observation_profile'])
                        self.assertEqual(runner.PCID_LOCK_FREE, collect.call_args.kwargs['pcid_observation_profile'])
                    else:
                        instances[0].qmp.request.assert_not_called();collect.assert_not_called()
                    replay.assert_not_called();popen.assert_not_called()
                saved = json.loads((output / 'result.json').read_text())
                self.assertFalse(saved['passed']);self.assertNotIn('seal', saved)
                self.assertTrue(saved['inputs_unchanged'])

    def test_b_replay_uses_real_strict_whpx_drive_gate_even_when_guest_json_matches(self):
        """Self-consistent synthetic archives cannot rehash away the argv gate."""
        actual = runner.pcid.launch_command(qemu_launch_fixture(), accel='whpx', cpu='host', kernel_irqchip='off')
        variables = next(value for value in actual if 'file=C:/state/OVMF_VARS.fd' in value)
        variants = {'valid': actual,
                    'missing-vars-cache': [value.replace(',cache=writethrough', '') for value in actual],
                    'no-flush-vars': [value + ',cache.no-flush=on' if value == variables else value for value in actual],
                    'writable-code': [value.replace(',readonly=on', '') for value in actual],
                    'changed-data-cache': [value.replace('cache=writeback', 'cache=writethrough') for value in actual]}
        class ReachedCapture(ValueError):pass
        for name, command in variants.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary);path = directory / 'result.json'
                identity = {'case': None, 'synthetic_host_boundary': True}
                serial = b'memory_runtime_boot_info=0xffff800000001000\r\n'
                result = dict(esp='synthetic-host-esp', source_identity=identity, execute=True,
                              actual_guest_executed=True, synthetic=False, guest_memory_or_register_writes=False,
                              negative=None, require_pcid=True, accel='whpx', cpu='host', kernel_irqchip='off',
                              tools_before={}, tools_after={}, boots=[])
                for index in (1, 2):
                    state = directory / ('boot-' + str(index));state.mkdir()
                    (state / 'physical-manifest.json').write_text('[]\n')
                    (state / 'serial.log').write_bytes(serial)
                    guest = dict(actual_qemu_executed=True, process_alive=False, cleanup_completed=True,
                                 command=copy.deepcopy(command), synthetic_host_boundary=True)
                    (state / 'guest.json').write_text(json.dumps(guest))
                    inventory = [{'cpu-index': cpu, 'thread-id': cpu + 10} for cpu in range(4)]
                    (state / 'cpu-inventory.json').write_text(json.dumps(inventory))
                    result['boots'].append(dict(before={'boot_info_ref': {'physical': 4096}},
                        after={'boot_info_ref': {'physical': 4096}}, guest=guest,
                        physical_manifest_sha256=build.sha(state / 'physical-manifest.json'),
                        serial_sha256=build.sha(state / 'serial.log'),
                        cpu_inventory_sha256=build.sha(state / 'cpu-inventory.json')))
                path.write_text(json.dumps(result))
                saved_bytes = path.read_bytes()
                with mock.patch.object(build, 'identity', return_value=identity), \
                     mock.patch.object(runner, 'layout_contract', return_value={}), \
                     mock.patch.object(runner.pcid, 'verify_launch_command', wraps=runner.pcid.verify_launch_command) as verify, \
                     mock.patch.object(runner, 'verify_capture_record', side_effect=ReachedCapture('next independent boundary')) as capture, \
                     mock.patch.object(runner, 'decode') as decode, \
                     mock.patch.object(runner.raw, 'Archive') as archive, \
                     mock.patch.object(runner, 'LargeGuest') as guest_call, \
                     mock.patch('subprocess.Popen', side_effect=AssertionError('replay cannot start VM')) as popen:
                    with self.assertRaises(ReachedCapture if name == 'valid' else ValueError):
                        runner.replay(path)
                    verify.assert_called_once_with(command, accel='whpx', cpu='host', kernel_irqchip='off')
                    if name == 'valid':capture.assert_called_once()
                    else:capture.assert_not_called()
                    decode.assert_not_called();archive.assert_not_called()
                    guest_call.assert_not_called();popen.assert_not_called()
                self.assertEqual(saved_bytes, path.read_bytes())

    def test_production_pipeline_commits_five_roots_before_large_after(self):
        events, boot, guest, before, after = self.pipeline()
        self.assertEqual(['gui', 'snapshot-before', *[runner.launch_command(cfg) for cfg in (7, 8, 9, 10, 11)],
                          'snapshot-after', 'validate-large', 'pcid'], events)
        self.assertEqual('after', boot['after']['label'])
        self.assertEqual(11, boot['trigger']['configuration'])
        self.assertEqual(boot['requests'][-1], boot['trigger'])
        # A sixth root or a missing member cannot replace the sealed graph.
        later = copy.deepcopy(after)
        later['catalog']['snapshots'][12].update(process=521, generation=1, state=1)
        later['get'] = lambda name: later['catalog']
        with mock.patch.object(runner.raw, 'catalog', side_effect=lambda data: data):
            with self.assertRaisesRegex(ValueError, 'unrequested ordinary'):
                runner.validate_launch_order(boot, bytes(guest.raw), before, later, negative=False)
            missing = copy.deepcopy(after)
            missing['catalog']['snapshots'][8]['process'] = 0
            with self.assertRaisesRegex(ValueError, 'committed Catalog'):
                runner.validate_launch_order(boot, bytes(guest.raw), before, missing, negative=False)
            changed = copy.deepcopy(boot)
            changed['requests'][0]['serial_start'] = changed['trigger']['serial_start']
            with self.assertRaisesRegex(ValueError, 'stale'):
                runner.validate_launch_order(changed, bytes(guest.raw), before, after, negative=False)
            changed = copy.deepcopy(boot)
            changed['after']['epoch'] = changed['before']['epoch']
            with self.assertRaisesRegex(ValueError, 'epoch order'):
                runner.validate_launch_order(changed, bytes(guest.raw), before, after, negative=False)

    def test_final_request_error_still_requires_the_precise_raw_negative_oracle(self):
        events, boot, _, _, after = self.pipeline(negative=True, launch_error=True)
        self.assertEqual(['gui', 'snapshot-before', *[runner.launch_command(cfg) for cfg in (7, 8, 9, 10, 11)],
                          'snapshot-after', 'validate-large'], events)
        self.assertIn('error', boot['trigger'])
        self.assertEqual(4, len(boot['launches']))
        self.assertTrue(all('receipt' in request for request in boot['requests'][:4]))
        self.assertNotIn('pcid_snapshot', boot)
        self.assertEqual((1, 1, 1), (after['domain'][1], after['bridge'][1], after['report']['poison']))
        self.assertNotIn('first_failed_checkpoint', boot)
        with self.assertRaisesRegex(ValueError, 'exact A/PTE-B missing'):
            self.pipeline(negative=True, launch_error=True, oracle_failure=True)

    def test_permanent_domain_or_bridge_failure_stops_at_first_checkpoint_without_resume(self):
        """Run production collect_boot with explicit raw-decode boundary data."""
        for failed in ('domain', 'bridge', 'both'):
            capture = {}
            with self.subTest(failed=failed), self.assertRaisesRegex(ValueError, 'actual owner/kernel/lease identity differs') as caught:
                self.pipeline(terminal_failure=failed, capture=capture)
            boot, after = capture['boot'], capture['after']
            self.assertIs(caught.exception, capture['validation_error'])
            self.assertEqual(0, after['report']['poison'])
            self.assertEqual(0, after['report']['attempted'])
            self.assertEqual(1, capture['events'].count('snapshot-after'))
            self.assertNotIn('resume', capture['events'])
            self.assertNotIn('pcid', capture['events'])
            first = boot['first_failed_checkpoint']
            self.assertEqual(2, first['epoch'])
            self.assertEqual(boot['after'], first['checkpoint'])
            self.assertIsNot(boot['after'], first['checkpoint'])
            self.assertEqual('ValueError', first['error_type'])
            self.assertEqual(str(caught.exception), first['error'])
            self.assertEqual('undetermined', first['cause'])
            self.assertEqual('terminal-validation-failure', first['classification'])
            self.assertEqual(dict(owner_poison=False, domain_failed=failed in ('domain', 'both'),
                                  bridge_failed=failed in ('bridge', 'both')), first['terminal'])

    def test_observer_disturbed_error_remains_distinct_without_resume(self):
        for failed in (None, 'domain'):
            capture = {}
            with self.subTest(failed=failed), self.assertRaisesRegex(ValueError, 'observer-disturbed') as caught:
                self.pipeline(terminal_failure=failed, capture=capture,
                              observed_error='observer-disturbed: capture envelope invalid')
            self.assertIs(caught.exception, capture['validation_error'])
            first = capture['boot']['first_failed_checkpoint']
            self.assertEqual('observer-disturbed', first['classification'])
            self.assertEqual('undetermined', first['cause'])
            self.assertEqual(str(caught.exception), first['error'])
            self.assertEqual(failed == 'domain', first['terminal']['domain_failed'])
            self.assertNotIn('resume', capture['events'])
            self.assertNotIn('pcid', capture['events'])

    def test_pending_historical_checkpoint_retries_without_an_extra_resume(self):
        events, boot, _, _, _ = self.pipeline(pending_checkpoints=1)
        self.assertEqual(2, events.count('snapshot-after'))
        self.assertEqual(2, events.count('validate-large'))
        self.assertNotIn('resume', events)
        self.assertNotIn('first_failed_checkpoint', boot)
        self.assertEqual(3, boot['after']['epoch'])
        self.assertEqual('pcid', events[-1])

    def test_large_snapshot_uses_current_epoch_refs_and_shared_live_archive(self):
        """The production method must cont before any historical assembly."""
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / 'dong_layout.json').write_text(json.dumps({'types': [
                {'full_name': 'smp.large_memory.Report', 'size': 64}]}), encoding='utf-8')
            names = ['runtime_large_environment', 'runtime_large_load', 'runtime_large_window',
                     'runtime_large_digest', 'runtime_large_test_omit']
            symbols = {name: 0xffffffff80001000 + i * 64 for i, name in enumerate(names)}
            for module, name in [('smp.large_memory', 'REPORT'), ('sched.user_bridge', 'ACTIVE'),
                                  ('user.services', 'CATALOG')]:
                symbols[runner.pcid.storage.symbol(module, name)] = 0x9000
            for name in ['SPACES', 'META', 'PROCESSES', 'POOL_LIMITS', 'DYNAMIC_PHYSICAL',
                         'DYNAMIC_TABLES', 'GENERATIONS', 'PINNED']:
                symbols[runner.pcid.storage.symbol('user.memory', name)] = 0x9000
            contract = dict(storage_symbol=1, context_symbol=2, request_symbol=3, kernel_space=4,
                            buddy=5, info_symbol=6, symbols=symbols,
                            types={'user.services.LargeStorage': {'size': 8},
                                   'mm.phys_buddy.Allocator': {'size': 16}, 'mm.phys_buddy.PageMeta': {'size': 8}},
                            offsets={'mm.phys_buddy.Allocator': {'base': 0, 'metadata': 8}})
            data = {'storage_pointer': struct.pack('<Q', 0x8000), 'context_pointer': struct.pack('<Q', 0x8000),
                    'kernel_space': struct.pack('<8Q', 1, 0x100000, 128, 0x200000, 0x300000, 0, 1, 3),
                    'buddy': struct.pack('<2Q', 0x10000000, 0xa000),
                    'old_report': struct.pack('<8Q', *([0] * 7 + [0x10000000])),
                    'boot_info_pointer': struct.pack('<Q', 0xb000),
                    'boot_report': struct.pack('<10Q', *([0] * 5 + [0xc000, 0xd000, 0, 0, 0])),
                    'domain': struct.pack('<15Q', *([0] * 10 + [0xe000, 0xf000, 0x10000, 0, 0])),
                    'bridge_pointer': struct.pack('<Q', 0x11000),
                    'header_addresses': struct.pack('<4Q', 0x12000, 0x14000, 0x16000, 0x18000),
                    'catalog_pointer': struct.pack('<Q', 0x19000), 'memory.SPACES': bytes(16 * 64)}
            archive, events, decoded = object(), [], object()
            class Guest:
                # A previous stop exists first: selecting the first role is wrong.
                chunks = [dict(file='epoch1-boot.bin', epoch=1, role='BootInfo')]
                raw = bytearray(b'sealed uart')
                running = False
                def capture_image(self, label):
                    self_case.assertEqual('after', label)
                    self_case.assertFalse(self.running)
                    events.append('seal-six-bulk-four-hmp')
                    image.serial_offset = len(self.raw)
                    return image
                def resume(self):
                    events.append('explicit-cont')
                    self.running = True
                    self.raw.extend(b' post-cont uart must not move the sealed boundary')
                @property
                def current_epoch(self):
                    raise AssertionError('historical assembly consulted running current_epoch')
                @property
                def current_boot_info_ref(self):
                    raise AssertionError('historical assembly consulted running BootInfo')
                def physical(self, *args):
                    raise AssertionError('historical assembly consulted running physical')
                def snapshot_archive(self):
                    raise AssertionError('historical assembly consulted running archive')
                def hmp(self, *args):
                    raise AssertionError('historical assembly consulted running HMP')
            class Image:
                epoch = 7
                boot_info_ref = dict(file='epoch7-boot.bin', epoch=7, role='BootInfo')
                boot = [0] * 15 + [0x400000]
                initialized = False
                def initialize(self):
                    self_case.assertTrue(guest.running)
                    events.append('historical-initialize')
                    self.initialized = True
                def snapshot_archive(self):
                    self_case.assertTrue(guest.running and self.initialized)
                    return archive
                def archive(self):
                    return self.snapshot_archive()
                def register_ref(self, cpu):
                    self_case.assertTrue(guest.running)
                    text = ('epoch7 cpu' + str(cpu) + ' info registers\r\n').encode('utf-8')
                    return dict(cpu_index=cpu, file='source-e7-cpu' + str(cpu) + '.txt',
                                sha256=hashlib.sha256(text).hexdigest(), epoch=7, source_id='cpu' + str(cpu))
            class Capture:
                pool = [0x200000, 128, 0x200000]
                def __init__(self, source):
                    self_case.assertIs(image, source)
                    self_case.assertTrue(guest.running and source.initialized)
                    events.append('historical-capture')
                    self.image = source
                def part(self, address, length, role):
                    content = data.get(role.removeprefix('runtime-large '), bytes(length))
                    return content, dict(synthetic_bytes=content, epoch=self.image.epoch)
                def physical(self, address, length, role):
                    return b'', dict(physical=address, length=length, epoch=self.image.epoch)
            self_case = self
            guest, image = Guest(), Image()
            image.state = state;image.esp = state / 'esp'
            def contract_after_cont(esp):
                self.assertTrue(guest.running and image.initialized)
                self.assertEqual(image.esp, esp)
                events.append('historical-layout')
                return contract
            def part(ref, actual_archive, pool):
                self.assertIs(archive, actual_archive)
                return ref['synthetic_bytes']
            def decode(snapshot, actual_archive, actual_contract):
                self.assertTrue(guest.running and image.initialized)
                self.assertIs(archive, actual_archive)
                self.assertIs(contract, actual_contract)
                self.assertEqual(image.serial_offset, snapshot['serial_offset'])
                self.assertLess(snapshot['serial_offset'], len(guest.raw))
                events.append('historical-decode')
                return decoded
            with mock.patch.object(runner, 'layout_contract', side_effect=contract_after_cont), \
                 mock.patch.object(runner.pcid, 'Capture', Capture), \
                 mock.patch.object(runner, 'elf_bytes', return_value=bytes(64)), \
                 mock.patch.object(runner.raw, 'part_bytes', side_effect=part), \
                  mock.patch.object(runner, 'decode', side_effect=decode), \
                 mock.patch.object(runner.raw, 'Archive', side_effect=AssertionError('live capture must share registry')), \
                 mock.patch('subprocess.Popen', side_effect=AssertionError('host boundary cannot boot guest')):
                snapshot, actual_decoded = runner.LargeGuest.large_snapshot(guest, 'after')
            self.assertIs(decoded, actual_decoded)
            self.assertEqual(['seal-six-bulk-four-hmp', 'explicit-cont', 'historical-initialize',
                              'historical-layout', 'historical-capture', 'historical-decode'], events)
            self.assertEqual(7, snapshot['epoch'])
            self.assertEqual(image.boot_info_ref, snapshot['boot_info_ref'])
            self.assertNotEqual(guest.chunks[0], snapshot['boot_info_ref'])
            self.assertEqual([0, 1, 2, 3], [ref['cpu_index'] for ref in snapshot['registers']])
            self.assertTrue(all(ref['epoch'] == 7 and ref['source_id'] for ref in snapshot['registers']))

    def test_large_decode_binds_serial_boundary_to_the_sealed_epoch(self):
        """Changing result offsets cannot move the registry's actual boundary."""
        archive = mock.Mock()
        archive.snapshot_serial_offset = 41
        base = dict(epoch=7, serial_offset=41, kernel_pool=[0x200000, 128, 0x200000],
                    kernel_pool_ref=dict(physical=0x200000, length=128 * 4096))
        for value in (None, True, 40, 42):
            altered = dict(base, serial_offset=value)
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'sealed capture epoch'):
                runner.decode(altered, archive, {})
            archive.read.assert_not_called()
        altered = dict(base);altered.pop('serial_offset')
        with self.assertRaisesRegex(ValueError, 'sealed capture epoch'):
            runner.decode(altered, archive, {})
        archive.read.assert_not_called()
        # A matching real source boundary proceeds to the independent raw reader.
        archive.read.side_effect = LookupError('independent raw reader reached')
        with self.assertRaisesRegex(LookupError, 'independent raw reader reached'):
            runner.decode(base, archive, {})
        archive.read.assert_called_once_with(base['kernel_pool_ref'])

    def test_failed_explicit_cont_never_initializes_or_decodes_a_historical_image(self):
        image = mock.Mock()
        guest = mock.Mock()
        guest.capture_image.return_value = image
        error = ValueError('observer-disturbed: actual cont was not confirmed')
        guest.resume.side_effect = error
        with mock.patch.object(runner.pcid, 'Capture') as capture, \
             mock.patch.object(runner, 'layout_contract') as contract, \
             mock.patch.object(runner, 'decode') as decode, \
             mock.patch('subprocess.Popen', side_effect=AssertionError('host boundary cannot boot guest')):
            with self.assertRaisesRegex(ValueError, 'observer-disturbed') as caught:
                runner.LargeGuest.large_snapshot(guest, 'after')
        self.assertIs(error, caught.exception)
        guest.capture_image.assert_called_once_with('after')
        guest.resume.assert_called_once_with()
        image.initialize.assert_not_called()
        capture.assert_not_called();contract.assert_not_called();decode.assert_not_called()

    def test_large_decode_requires_explicit_epoch_before_any_raw_read(self):
        archive = mock.Mock()
        archive.begin_snapshot.side_effect = ValueError('unknown or mixed observation epoch')
        with self.assertRaisesRegex(ValueError, 'observation epoch'):
            runner.decode({'epoch': 9}, archive, {})
        archive.begin_snapshot.assert_called_once_with(9)
        archive.read.assert_not_called()
        archive.reset_mock()
        with self.assertRaises(KeyError):
            runner.decode({}, archive, {})
        archive.begin_snapshot.assert_not_called()
        archive.read.assert_not_called()

    def test_synthetic_or_unbound_records_cannot_certify_actual_guest_loads(self):
        for before, after in (({'synthetic': True}, {'synthetic': True}),
                              ({'synthetic': False}, {'synthetic': True}), ({}, {})):
            with self.assertRaisesRegex(ValueError, 'cannot certify actual guest'):
                runner.validate(before, after, {})

    def test_bulk_cleanup_record_requires_schema_final_disk_and_exact_index_hash(self):
        """Host provenance-boundary controls never produce a guest seal."""
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp);index = state / runner.pcid.bulk.INDEX
            index.write_bytes(b'{"synthetic_host_index":true}\n')
            record = dict(bulk_capture=dict(schema=runner.pcid.bulk.SCHEMA, index_file=runner.pcid.bulk.INDEX,
                          index_sha256=build.sha(index), final_disk_verified=True))
            runner.verify_capture_record(state, record)
            for key, value in (('schema', 'legacy'), ('index_file', 'another-index.json'),
                               ('final_disk_verified', False), ('index_sha256', '0' * 64)):
                changed = copy.deepcopy(record);changed['bulk_capture'][key] = value
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'bulk capture provenance'):
                    runner.verify_capture_record(state, changed)
            with self.assertRaisesRegex(ValueError, 'bulk capture provenance'):
                runner.verify_capture_record(state, {})
            index.write_bytes(index.read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'bulk capture provenance'):
                runner.verify_capture_record(state, record)

    def pipeline(self, *, negative=False, launch_error=False, oracle_failure=False,
                 terminal_failure=None, observed_error=None, pending_checkpoints=0, capture=None,
                 normal_observation_profile=runner.LEGACY_OBSERVATION,
                 pcid_observation_profile=runner.PCID_LOCK_FREE, pcid_record_profile=None):
        """Explicit host adapters test ordering, never manufacture guest proof."""
        events, boot = [], {}
        old = dict(snapshots=[dict(process=0, generation=0, state=0, argument=0) for _ in range(18)])
        current = copy.deepcopy(old)
        for cfg in runner.raw.ARGS:
            current['snapshots'][cfg].update(process=521 + cfg, generation=1, state=1, argument=runner.raw.ARGS[cfg])
        before = dict(report={'attempted': 0, 'poison': 0}, requested=False, catalog=old, domain=[1, 0], bridge=[1, 0])
        after = dict(report={'attempted': int(terminal_failure is None), 'poison': int(negative or oracle_failure)},
                     requested=True, catalog=current, domain=[1, int(negative or terminal_failure in ('domain', 'both'))],
                     bridge=[1, int(negative or terminal_failure in ('bridge', 'both'))])
        before['get'] = lambda name: before['catalog']
        after['get'] = lambda name: after['catalog']
        class Guest:
            raw = bytearray(b'desktop\r\n> ')
            epoch = 0
            after_captures = 0
            def large_snapshot(self, label):
                events.append('snapshot-' + label)
                self.epoch += 1
                record = dict(label=label, epoch=self.epoch, serial_offset=len(self.raw))
                if label == 'before':
                    return record, before
                self.after_captures += 1
                if self.after_captures <= pending_checkpoints:
                    pending = copy.deepcopy(after)
                    pending['report'] = dict(attempted=0, poison=0)
                    return record, pending
                return record, after
            def snapshot_archive(self):
                raise AssertionError('pipeline consulted running Guest archive')
            def shell(self, command):
                events.append(command)
                start = len(self.raw)
                cfg = next(cfg for cfg in runner.raw.ARGS if runner.launch_command(cfg) == command)
                body = ('RUN OK ' + runner.pcid.life.NAMES[cfg] + ' token=' + str(521 + cfg)
                        + ' generation=1 state=1 status=0\r\n').encode()
                self.raw.extend(command.encode() + b'\r\n')
                if launch_error and cfg == 11:
                    raise TimeoutError('final reply blocked')
                self.raw.extend(body + b'> ')
                segment = bytes(self.raw[start:])
                return dict(command=command, serial_offset=start,
                            command_utf8_sha256=hashlib.sha256(command.encode()).hexdigest(),
                            **runner.pcid.life.fat.fresh_response(segment, command))
            def resume(self):
                events.append('resume')
        guest = Guest()
        if capture is not None:
            capture.update(events=events, boot=boot, guest=guest, before=before, after=after)
        def verify(*args, **kwargs):
            events.append('validate-large')
            self.assertEqual(negative, kwargs['negative'])
            self.assertEqual(normal_observation_profile, kwargs['normal_observation_profile'])
            if oracle_failure:
                raise ValueError('exact A/PTE-B missing')
            if terminal_failure is not None or observed_error is not None:
                error = ValueError(observed_error or 'actual owner/kernel/lease identity differs')
                if capture is not None:
                    capture['validation_error'] = error
                raise error
            if args[1]['report']['attempted'] == 0:
                raise ValueError('owner has not completed at this sealed epoch')
        def pcid(*args, **kwargs):
            events.append('pcid')
            self.assertEqual(pcid_observation_profile, kwargs['observation_profile'])
            self.assertTrue(kwargs['require_pcid'])
            return ({'separate': True, 'observation_profile': pcid_record_profile or pcid_observation_profile}, {})
        with mock.patch.object(runner.pcid.prior, 'close_gui', side_effect=lambda g: events.append('gui')), \
             mock.patch.object(runner, 'layout_contract', return_value={'host_boundary_adapter': True}), \
             mock.patch.object(runner.raw, 'Archive', side_effect=AssertionError('pipeline must share live registry')), \
              mock.patch.object(runner, 'decode', side_effect=AssertionError('snapshot must return historical decoded data')), \
             mock.patch.object(runner, 'validate', side_effect=verify), \
             mock.patch.object(runner.pcid, 'stable_snapshot', side_effect=pcid), \
             mock.patch.object(runner.raw, 'catalog', side_effect=lambda data: data), \
             mock.patch('subprocess.Popen', side_effect=AssertionError('host pipeline started VM')):
            runner.collect_boot(guest, boot, Path('host-only'), Path('host-only/esp'),
                                negative=negative, require_pcid=True,
                                normal_observation_profile=normal_observation_profile,
                                pcid_observation_profile=pcid_observation_profile)
        return events, boot, guest, before, after

    def test_current_kernel_profile_two_shapes_and_monotonic_ack_lower_bound(self):
        for pending in (False, True):
            decoded = kernel_barrier_fixture(pending=pending)
            controls = runner.validate_barrier_controls(decoded, require_pcid=True,
                          normal_observation_profile=runner.KERNEL_OBSERVATION)
            self.assertTrue(controls['owner_post_completed'])
            self.assertEqual(pending, controls['current_barrier_pending'])
            self.assertEqual(not pending, controls['current_barrier_complete'])
            if pending:
                completed, sequence = decoded['domain'][8], decoded['domain'][5]
                for cpu in range(4):
                    for pair in ((completed, completed), (sequence, completed), (sequence, sequence)):
                        changed = copy.deepcopy(decoded);changed['cpus'][cpu][7:9] = pair
                        runner.validate_barrier_controls(changed, require_pcid=True,
                            normal_observation_profile=runner.KERNEL_OBSERVATION)
                with self.assertRaisesRegex(ValueError, 'current all-tag barrier is incomplete'):
                    runner.validate_barrier_controls(decoded)
            else:
                # V2 idle may park CPU0 with IF1, but still requires CS8/kernel root.
                decoded['cpus'][0][0] = 1;decoded['registers'][0]['RFL'] = 0x202
                runner.validate_barrier_controls(decoded, normal_observation_profile=runner.KERNEL_OBSERVATION)
                decoded['registers'][2].update(CS=0x33, CR3=0x5000011)
                runner.validate_barrier_controls(decoded)  # Exact old CPL3 allowance remains v1-only.
                with self.assertRaisesRegex(ValueError, 'CS/GS Header/raw kernel CR3'):
                    runner.validate_barrier_controls(decoded, normal_observation_profile=runner.KERNEL_OBSERVATION)

    def test_current_kernel_rejects_each_cpu_ack_mode_hardware_and_profile_corruption(self):
        for pending in (False, True):
            original = kernel_barrier_fixture(pending=pending)
            completed, sequence = original['domain'][8], original['domain'][5]
            controls = [
                ('domain-failed', lambda d: d['domain'].__setitem__(1, 1)),
                ('bridge-failed', lambda d: d['bridge'].__setitem__(1, 1)),
                ('wrong-owner', lambda d: d['domain'].__setitem__(3, 2)),
                ('wrong-lock', lambda d: d['domain'].__setitem__(2, 1 - int(pending))),
                ('bad-sequence', lambda d: d['domain'].__setitem__(5, sequence + 1)),
                ('bad-expected', lambda d: d['domain'].__setitem__(7, 7)),
                ('owner-post-incomplete', lambda d: d['domain'].__setitem__(8, d['report']['post_sequence'] - 1)),
                ('header-set-missing', lambda d: d.pop('header_addresses')),
                ('duplicate-header', lambda d: d['header_addresses'].__setitem__(2, d['header_addresses'][1])),
            ]
            for cpu in range(4):
                for field in (7, 8):
                    for value in (completed - 1, sequence + 1, True):
                        controls.append(('cpu%d-field%d-%s' % (cpu, field, value),
                            lambda d, c=cpu, f=field, v=value: d['cpus'][c].__setitem__(f, v)))
                if pending:
                    controls.append(('cpu%d-ack-before-request' % cpu,
                        lambda d, c=cpu: d['cpus'][c].__setitem__(slice(7, 9), [completed, sequence])))
                allowed = (5,) if cpu == 0 and pending else (1, 4)
                for mode in set(range(7)) - set(allowed):
                    controls.append(('cpu%d-mode%d' % (cpu, mode),
                        lambda d, c=cpu, v=mode: d['cpus'][c].__setitem__(0, v)))
                for name, value in (('CS', 0x33), ('CS', 0x10), ('GS_base', 0),
                                    ('GS_base', original['header_addresses'][(cpu + 1) % 4]),
                                    ('CR3', original['report']['root'] | 17),
                                    ('CR3', original['report']['root'] + 4096), ('RFL', None)):
                    controls.append(('cpu%d-%s-%s' % (cpu, name, value),
                        lambda d, c=cpu, k=name, v=value: d['registers'][c].__setitem__(k, v)))
                controls.extend([
                    ('cpu%d-metric-failed' % cpu, lambda d, c=cpu: d['metrics'][c].__setitem__(5, 1)),
                    ('cpu%d-cr4-readback' % cpu, lambda d, c=cpu: d['metrics'][c].__setitem__(18, 0)),
                    ('cpu%d-pge' % cpu, lambda d, c=cpu: (d['metrics'][c].__setitem__(18, 0x20080),
                        d['registers'][c].__setitem__('CR4', 0x20080))),
                    ('cpu%d-strict-fallback' % cpu, lambda d, c=cpu: (d['metrics'][c].__setitem__(18, 0),
                        d['registers'][c].__setitem__('CR4', 0))),
                ])
                if cpu == 0 and pending or cpu > 0:
                    controls.append(('cpu%d-required-IF0' % cpu, lambda d, c=cpu: (
                        d['cpus'][c].__setitem__(0, 5 if c == 0 else 4),
                        d['registers'][c].__setitem__('RFL', 0x202))))
            for name, mutate in controls:
                with self.subTest(pending=pending, control=name):
                    changed = copy.deepcopy(original);mutate(changed)
                    with self.assertRaises(ValueError):
                        runner.validate_barrier_controls(changed, require_pcid=True,
                            normal_observation_profile=runner.KERNEL_OBSERVATION)

    def test_current_kernel_actual_validate_preserves_all_owner_oracles_and_tail(self):
        for pending in (False, True):
            before, after = kernel_validation_fixture(pending=pending)
            with mock.patch.object(runner, 'digest', return_value=123) as digest, \
                 mock.patch.object(runner, 'validate_authority') as authority, \
                 mock.patch.object(runner, 'kernel_forest', return_value={'host_boundary': True}) as forest, \
                 mock.patch.object(runner, 'validate_readers') as readers:
                seal = runner.validate(before, after, {}, require_pcid=True,
                                       normal_observation_profile=runner.KERNEL_OBSERVATION)
                self.assertEqual(runner.KERNEL_OBSERVATION, seal['normal_observation_profile'])
                self.assertEqual(pending, seal['observation_controls']['current_barrier_pending'])
                self.assertEqual(not pending, seal['observation_controls']['current_barrier_complete'])
                digest.assert_called_once_with(before['payload']);authority.assert_called_once()
                forest.assert_called_once();readers.assert_called_once()
                for field, value in (('barriers', 15), ('retired', 1), ('reclaimed', 1), ('complete', 0)):
                    changed = copy.deepcopy(after);changed['report'][field] = value
                    with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'lifecycle/report incomplete'):
                        runner.validate(before, changed, {}, normal_observation_profile=runner.KERNEL_OBSERVATION)
                for cpu in range(4):
                    changed = copy.deepcopy(after);changed['cpus'][cpu][8] = after['domain'][8] - 1
                    with self.subTest(cpu=cpu), self.assertRaisesRegex(ValueError, 'all-tag barrier acknowledgement'):
                        runner.validate(before, changed, {}, normal_observation_profile=runner.KERNEL_OBSERVATION)
        for profile in (None, '', 'unknown', runner.KERNEL_OBSERVATION):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                runner.validate_barrier_controls(barrier_fixture(negative=True), negative=True,
                                                 normal_observation_profile=profile)

    def test_current_kernel_rfl_uses_one_complete_archived_hmp_register(self):
        text = ('CR0=80010033 CR3=4000000 CR4=20000 RIP=10 RSP=20 RFL=00000002 [-------] CPL=0\n'
                'CS =0008 00000000 SS =0010 00000000 GS =0000 ffffd40002000000\n'
                'GDT= 100 0037 IDT= 200 0fff TR =0018 300\n')
        self.assertEqual(2, runner.parse_kernel_registers(text)['RFL'])
        self.assertNotIn('RFL', runner.raw.parse_registers(text.replace(' RFL=00000002', '')))
        for bad in (text.replace('RFL=00000002', ''), text + 'RFL=00000202\n',
                    text + 'RFL=bad\n', text.replace('RFL=00000002', 'RFL=00000002xyz'),
                    text.replace('RFL=00000002', 'RFL=10000000000000000')):
            with self.subTest(text=bad), self.assertRaisesRegex(ValueError, 'RFL'):
                runner.parse_kernel_registers(bad)

    def test_profiles_reject_before_guest_and_bind_cli_collect_and_replay_selection(self):
        for profile, negative in ((None, None), ('unknown', None), (runner.KERNEL_OBSERVATION, 'omit-ap-flush')):
            with self.subTest(profile=profile, negative=negative), \
                 mock.patch.object(build, 'identity') as identity, \
                 mock.patch.object(runner, 'LargeGuest') as guest, \
                 mock.patch('subprocess.Popen', side_effect=AssertionError('must reject before Popen')):
                with self.assertRaises(ValueError):
                    runner.execute('unused', 'unused', negative=negative, normal_observation_profile=profile)
                identity.assert_not_called();guest.assert_not_called()
        with mock.patch.object(runner, 'execute', return_value={'passed': True}) as execute:
            self.assertEqual(0, runner.main(['--execute', '--reuse-esp', 'host-only',
                             '--normal-observation-profile', runner.KERNEL_OBSERVATION]))
            self.assertEqual(runner.KERNEL_OBSERVATION, execute.call_args.kwargs['normal_observation_profile'])
            self.assertEqual(1, runner.main(['--execute', '--reuse-esp', 'host-only',
                             '--normal-observation-profile', 'unknown']))
            self.assertEqual(1, runner.main(['--execute', '--reuse-esp', 'host-only', '--negative', 'omit-ap-flush',
                             '--normal-observation-profile', runner.KERNEL_OBSERVATION]))
            self.assertEqual(1, execute.call_count)
        events, boot, guest, _, _ = self.pipeline(normal_observation_profile=runner.KERNEL_OBSERVATION)
        self.assertEqual(runner.KERNEL_OBSERVATION, boot['normal_observation_profile'])
        self.assertEqual(runner.KERNEL_OBSERVATION, guest.normal_observation_profile)
        self.assertEqual('pcid', events[-1])
        with mock.patch.object(runner.pcid.prior, 'close_gui') as gui:
            with self.assertRaises(ValueError):
                runner.collect_boot(mock.Mock(), {}, Path('host-only'), Path('host-only'), negative=True,
                                    require_pcid=True, normal_observation_profile=runner.KERNEL_OBSERVATION)
            gui.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'result.json'
            for profile, negative in (('unknown', None), (None, None), (runner.KERNEL_OBSERVATION, 'omit-ap-flush')):
                path.write_text(json.dumps(dict(normal_observation_profile=profile, negative=negative)))
                with self.subTest(replay_profile=profile), mock.patch.object(build, 'identity') as identity:
                    with self.assertRaises(ValueError):runner.replay(path)
                    identity.assert_not_called()

    def test_pcid_profile_is_independent_and_invalid_or_negative_selection_rejects_before_guest(self):
        for profile, negative in ((None, None), ('', None), ('unknown', None),
                                  (runner.PCID_CURRENT_OWNER, 'omit-ap-flush')):
            with self.subTest(profile=profile, negative=negative), \
                 mock.patch.object(build, 'identity') as identity, \
                 mock.patch.object(runner, 'LargeGuest') as guest, \
                 mock.patch('subprocess.Popen', side_effect=AssertionError('must reject before Popen')):
                with self.assertRaises(ValueError):
                    runner.execute('unused', 'unused', negative=negative, pcid_observation_profile=profile)
                identity.assert_not_called();guest.assert_not_called()
        for normal_profile in (runner.LEGACY_OBSERVATION, runner.KERNEL_OBSERVATION):
            for pcid_profile in (runner.PCID_LOCK_FREE, runner.PCID_CURRENT_OWNER):
                events, boot, _, _, _ = self.pipeline(normal_observation_profile=normal_profile,
                                                     pcid_observation_profile=pcid_profile)
                self.assertEqual(normal_profile, boot['normal_observation_profile'])
                self.assertEqual(pcid_profile, boot['pcid_observation_profile'])
                self.assertEqual(pcid_profile, boot['pcid_snapshot']['observation_profile'])
                self.assertEqual('pcid', events[-1])
        with self.assertRaisesRegex(ValueError, 'collected PCID snapshot observation profile'):
            self.pipeline(pcid_observation_profile=runner.PCID_CURRENT_OWNER,
                          pcid_record_profile=runner.PCID_LOCK_FREE)
        with mock.patch.object(runner.pcid.prior, 'close_gui') as gui:
            with self.assertRaises(ValueError):
                runner.collect_boot(mock.Mock(), {}, Path('host-only'), Path('host-only'), negative=True,
                                    require_pcid=True, pcid_observation_profile=runner.PCID_CURRENT_OWNER)
            gui.assert_not_called()

    def test_pcid_cli_default_explicit_and_identity_only_use_the_same_independent_contract(self):
        with mock.patch.object(runner, 'execute', return_value={'passed': True}) as execute:
            self.assertEqual(0, runner.main(['--execute', '--reuse-esp', 'host-only',
                             '--normal-observation-profile', runner.KERNEL_OBSERVATION]))
            self.assertEqual(runner.PCID_LOCK_FREE, execute.call_args.kwargs['pcid_observation_profile'])
            self.assertEqual(0, runner.main(['--execute', '--reuse-esp', 'host-only',
                             '--pcid-observation-profile', runner.PCID_CURRENT_OWNER]))
            self.assertEqual(runner.LEGACY_OBSERVATION, execute.call_args.kwargs['normal_observation_profile'])
            self.assertEqual(runner.PCID_CURRENT_OWNER, execute.call_args.kwargs['pcid_observation_profile'])
            for tail in (['--pcid-observation-profile', 'unknown'],
                         ['--negative', 'omit-ap-flush', '--pcid-observation-profile', runner.PCID_CURRENT_OWNER]):
                self.assertEqual(1, runner.main(['--execute', '--reuse-esp', 'host-only', *tail]))
            self.assertEqual(2, execute.call_count)
        with mock.patch.object(build, 'identity', return_value={'case': 'omit-ap-flush'}), \
             mock.patch.object(runner, 'LargeGuest') as guest, \
             mock.patch('subprocess.Popen', side_effect=AssertionError('identity-only cannot start VM')):
            self.assertEqual(1, runner.main(['--reuse-esp', 'host-only',
                             '--pcid-observation-profile', runner.PCID_CURRENT_OWNER]))
            guest.assert_not_called()
        with mock.patch.object(runner, 'replay', return_value={'passed': True}) as replay:
            self.assertEqual(0, runner.main(['--replay', 'host-only',
                             '--pcid-observation-profile', runner.PCID_CURRENT_OWNER]))
            self.assertEqual(runner.PCID_CURRENT_OWNER, replay.call_args.kwargs['pcid_observation_profile'])

    def test_saved_pcid_profile_rejects_missing_new_fields_unknown_mixed_and_negative_before_inputs(self):
        legacy = dict(negative=None, boots=[dict(pcid_snapshot={})])
        self.assertEqual(runner.PCID_LOCK_FREE, runner.saved_pcid_observation_profile(legacy))
        current = dict(negative=None, pcid_observation_profile=runner.PCID_CURRENT_OWNER,
                       boots=[dict(pcid_observation_profile=runner.PCID_CURRENT_OWNER,
                                   pcid_snapshot=dict(observation_profile=runner.PCID_CURRENT_OWNER))],
                       seal=dict(pcid_observation_profile=runner.PCID_CURRENT_OWNER,
                                 boots=[dict(pcid_observation_profile=runner.PCID_CURRENT_OWNER)]))
        self.assertEqual(runner.PCID_CURRENT_OWNER, runner.saved_pcid_observation_profile(current))
        bad = []
        for profile in (None, '', 'unknown'):
            changed = copy.deepcopy(legacy);changed['pcid_observation_profile'] = profile;bad.append(changed)
        for layer in ('seal', 'boot-seal', 'boot', 'snapshot'):
            changed = copy.deepcopy(current)
            target = {'seal': changed['seal'], 'boot-seal': changed['seal']['boots'][0],
                      'boot': changed['boots'][0], 'snapshot': changed['boots'][0]['pcid_snapshot']}[layer]
            field = 'observation_profile' if layer == 'snapshot' else 'pcid_observation_profile'
            del target[field];bad.append(changed)
            changed = copy.deepcopy(current)
            target = {'seal': changed['seal'], 'boot-seal': changed['seal']['boots'][0],
                      'boot': changed['boots'][0], 'snapshot': changed['boots'][0]['pcid_snapshot']}[layer]
            target[field] = 'unknown';bad.append(changed)
        changed = copy.deepcopy(current);changed['negative'] = 'omit-ap-flush';bad.append(changed)
        changed = copy.deepcopy(legacy);changed['negative'] = 'omit-ap-flush';bad.append(changed)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'result.json'
            for index, changed in enumerate(bad):
                path.write_text(json.dumps(changed))
                with self.subTest(case=index), mock.patch.object(build, 'identity') as identity, \
                     mock.patch('subprocess.Popen', side_effect=AssertionError('replay cannot start VM')):
                    with self.assertRaises(ValueError):runner.replay(path)
                    identity.assert_not_called()

    def test_execute_propagates_selected_pcid_profile_through_both_boots_and_final_replay(self):
        """Production orchestration with explicit host IO adapters, no guest proof."""
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'fresh';profile = runner.PCID_CURRENT_OWNER
            identity = {'case': None, 'explicit_host_boundary': True}
            def create(disk, size):disk.write_bytes(b'host disk adapter')
            class Guest:
                def __init__(self, esp, disk, state, **kwargs):
                    state.mkdir()
                    (state / 'physical-manifest.json').write_bytes(b'[]')
                    (state / 'serial.log').write_bytes(b'host serial adapter')
                    self.evidence = {'command': ['explicit-host-boundary']}
                    self.qmp = mock.Mock()
                    self.qmp.request.return_value = []
                def close(self):pass
            def collect(guest, boot, state, esp, **kwargs):
                self.assertEqual(profile, kwargs['pcid_observation_profile'])
                self.assertEqual(profile, boot['pcid_observation_profile'])
            def replay(path, **kwargs):
                self.assertEqual(profile, kwargs['pcid_observation_profile'])
                saved = json.loads(path.read_text())
                self.assertEqual(profile, saved['pcid_observation_profile'])
                self.assertEqual(2, len(saved['boots']))
                self.assertTrue(all(b['pcid_observation_profile'] == profile for b in saved['boots']))
                return dict(passed=True, pcid_observation_profile=profile)
            with mock.patch.object(build, 'identity', return_value=identity), \
                 mock.patch.object(runner, 'create', side_effect=create), \
                 mock.patch.object(runner, 'source_tools', return_value={}), \
                 mock.patch.object(runner, 'LargeGuest', Guest), \
                 mock.patch.object(runner.pcid, 'verify_launch_command'), \
                 mock.patch.object(runner, 'collect_boot', side_effect=collect) as collect_call, \
                 mock.patch.object(runner, 'replay', side_effect=replay), \
                 mock.patch('subprocess.Popen', side_effect=AssertionError('host boundary cannot start VM')):
                result = runner.execute('host-only', output, pcid_observation_profile=profile)
            self.assertEqual(2, collect_call.call_count)
            self.assertEqual(profile, result['seal']['pcid_observation_profile'])
            self.assertTrue(result['inputs_unchanged'])

    def test_replay_actual_route_binds_missing_legacy_explicit_v2_boots_and_seal(self):
        """Explicit host adapters exercise replay routing, not guest evidence."""
        for profile, pcid_profile in ((None, None), (runner.KERNEL_OBSERVATION, None),
                                      (None, runner.PCID_CURRENT_OWNER),
                                      (runner.KERNEL_OBSERVATION, runner.PCID_CURRENT_OWNER)):
            with self.subTest(profile=profile, pcid_profile=pcid_profile), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp);path = directory / 'result.json'
                identity = {'case': None, 'synthetic_host_boundary': True}
                serial = b'memory_runtime_boot_info=0xffff800000001000\r\n'
                result = dict(esp='synthetic-host-esp', source_identity=identity, execute=True,
                              actual_guest_executed=True, synthetic=False, guest_memory_or_register_writes=False,
                              negative=None, require_pcid=True, accel='tcg', cpu='max', kernel_irqchip=None,
                              tools_before={}, tools_after={}, boots=[])
                if profile is not None:result['normal_observation_profile'] = profile
                if pcid_profile is not None:result['pcid_observation_profile'] = pcid_profile
                decoded = []
                for index in (1, 2):
                    state = directory / ('boot-' + str(index));state.mkdir()
                    (state / 'physical-manifest.json').write_text('[]\n')
                    (state / 'serial.log').write_bytes(serial)
                    guest = dict(actual_qemu_executed=True, process_alive=False, cleanup_completed=True,
                                 command=['explicit-host-command-adapter'])
                    (state / 'guest.json').write_text(json.dumps(guest))
                    inventory = [{'cpu-index': cpu, 'thread-id': cpu + 10} for cpu in range(4)]
                    (state / 'cpu-inventory.json').write_text(json.dumps(inventory))
                    boot = dict(before={'boot_info_ref': {'physical': 4096}},
                                after={'boot_info_ref': {'physical': 4096}}, guest=guest, pcid_snapshot={},
                                physical_manifest_sha256=build.sha(state / 'physical-manifest.json'),
                                serial_sha256=build.sha(state / 'serial.log'),
                                cpu_inventory_sha256=build.sha(state / 'cpu-inventory.json'))
                    if profile is not None:boot['normal_observation_profile'] = profile
                    if pcid_profile is not None:
                        boot['pcid_observation_profile'] = pcid_profile
                        boot['pcid_snapshot']['observation_profile'] = pcid_profile
                    result['boots'].append(boot)
                    decoded.extend(kernel_validation_fixture(pending=profile is not None))
                (directory / 'data.img').write_bytes(b'explicit host disk boundary')
                result['final_disk_sha256'] = build.sha(directory / 'data.img')
                path.write_text(json.dumps(result))
                archives = [mock.Mock(), mock.Mock()]
                with mock.patch.object(build, 'identity', return_value=identity), \
                     mock.patch.object(runner, 'layout_contract', return_value={}), \
                     mock.patch.object(runner.pcid, 'verify_launch_command'), \
                     mock.patch.object(runner, 'verify_capture_record') as capture, \
                     mock.patch.object(runner.raw, 'Archive', side_effect=archives), \
                     mock.patch.object(runner.pcid, 'capture_metadata', return_value={}), \
                     mock.patch.object(runner, 'decode', side_effect=decoded) as decode, \
                     mock.patch.object(runner, 'digest', return_value=123), \
                     mock.patch.object(runner, 'validate_authority') as authority, \
                     mock.patch.object(runner, 'kernel_forest', return_value={'host_boundary': True}) as forest, \
                     mock.patch.object(runner, 'validate_readers') as readers, \
                     mock.patch.object(runner, 'validate_launch_order') as launch_order, \
                     mock.patch.object(runner.raw, 'decode_snapshot', return_value={}) as pcid_decode, \
                     mock.patch.object(runner.pcid, 'elf_contract', return_value={}), \
                     mock.patch.object(runner.raw, 'validate_snapshot') as later_pcid, \
                     mock.patch('subprocess.Popen', side_effect=AssertionError('host replay cannot start VM')):
                    seal = runner.replay(path)
                    selected = profile or runner.LEGACY_OBSERVATION
                    selected_pcid = pcid_profile or runner.PCID_LOCK_FREE
                    self.assertEqual(selected, seal['normal_observation_profile'])
                    self.assertEqual(selected_pcid, seal['pcid_observation_profile'])
                    self.assertTrue(all(s['normal_observation_profile'] == selected for s in seal['boots']))
                    self.assertTrue(all(s['pcid_observation_profile'] == selected_pcid for s in seal['boots']))
                    self.assertEqual(4, decode.call_count)
                    self.assertTrue(all(c.kwargs['normal_observation_profile'] == selected for c in decode.call_args_list))
                    for oracle in (capture, authority, forest, readers, launch_order, later_pcid):
                        self.assertEqual(2, oracle.call_count)
                    self.assertEqual(2, pcid_decode.call_count)
                    self.assertTrue(all(c.kwargs['observation_profile'] == selected_pcid
                                        for c in pcid_decode.call_args_list + later_pcid.call_args_list))
                    self.assertTrue(all(c.kwargs['workers'] is True and c.kwargs['require_pcid'] is True
                                        for c in later_pcid.call_args_list))
                    for archive in archives:archive.verify_all.assert_called_once_with()
                # CLI replay can require a profile but cannot relabel an old result.
                opposite = runner.LEGACY_OBSERVATION if profile else runner.KERNEL_OBSERVATION
                with mock.patch.object(build, 'identity') as actual_identity:
                    with self.assertRaisesRegex(ValueError, 'profile differs from saved result'):
                        runner.replay(path, normal_observation_profile=opposite)
                    actual_identity.assert_not_called()
                changed = copy.deepcopy(result)
                changed['seal'] = {'normal_observation_profile': opposite,
                                   'pcid_observation_profile': selected_pcid}
                path.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, 'saved seal normal observation profile'):
                    runner.replay(path)
                changed = copy.deepcopy(result)
                changed['boots'][0]['normal_observation_profile'] = opposite
                path.write_text(json.dumps(changed))
                with mock.patch.object(build, 'identity', return_value=identity), \
                     mock.patch.object(runner, 'layout_contract', return_value={}):
                    with self.assertRaisesRegex(ValueError, 'boot normal observation profile'):
                        runner.replay(path)

                # Both old absent fields and explicit profiles bind every layer.
                opposite_pcid = runner.PCID_LOCK_FREE if pcid_profile else runner.PCID_CURRENT_OWNER
                path.write_text(json.dumps(result))
                with mock.patch.object(build, 'identity') as actual_identity:
                    with self.assertRaisesRegex(ValueError, 'replay PCID observation profile'):
                        runner.replay(path, pcid_observation_profile=opposite_pcid)
                    actual_identity.assert_not_called()
                for layer in ('seal', 'boot-seal', 'boot', 'snapshot'):
                    changed = copy.deepcopy(result)
                    if layer in ('seal', 'boot-seal'):
                        changed['seal'] = dict(pcid_observation_profile=selected_pcid)
                        if layer == 'seal':changed['seal']['pcid_observation_profile'] = opposite_pcid
                        else:changed['seal']['boots'] = [dict(pcid_observation_profile=opposite_pcid)]
                    elif layer == 'boot':changed['boots'][0]['pcid_observation_profile'] = opposite_pcid
                    else:changed['boots'][0]['pcid_snapshot']['observation_profile'] = opposite_pcid
                    path.write_text(json.dumps(changed))
                    with self.subTest(mixed_layer=layer), mock.patch.object(build, 'identity') as actual_identity:
                        with self.assertRaisesRegex(ValueError, 'PCID observation profile'):
                            runner.replay(path)
                        actual_identity.assert_not_called()

    def test_synthetic_reader_positive_and_exact_stale_negative(self):
        report, readers, metrics = reader_fixture()
        runner.validate_readers(report, readers, metrics, require_pcid=True)
        readers[1].update(request=2, ack=1, count=1)
        readers[1]['replaced']['value'] = runner.TAG | 5
        runner.validate_readers(report, readers, metrics, negative=True, require_pcid=True)

    def test_raw_barrier_current_later_and_exact_held_positive_boundaries(self):
        for negative, later in ((False, 0), (False, 7), (True, 0)):
            with self.subTest(negative=negative, later=later):
                decoded = barrier_fixture(negative=negative, later=later)
                runner.validate_barrier_controls(decoded, negative=negative, require_pcid=True)
        # A completed normal owner may be sampled after CPUs return to users.
        decoded = barrier_fixture(later=7)
        decoded['registers'][2].update(CS=0x33, CR3=0x5000011)
        runner.validate_barrier_controls(decoded, require_pcid=True)
        # The same raw policy supports explicit non-PCID operation, never strict fallback.
        decoded = barrier_fixture()
        for cpu in range(4):
            decoded['registers'][cpu]['CR4'] = decoded['metrics'][cpu][18] = 0
        runner.validate_barrier_controls(decoded, require_pcid=False)

    def test_raw_barrier_rejects_each_cpu_missing_stale_or_forged_ack_and_sequences(self):
        for negative in (False, True):
            original = barrier_fixture(negative=negative)
            controls = [
                ('not-ready', lambda d: d['domain'].__setitem__(0, 0)),
                ('online', lambda d: d['domain'].__setitem__(4, 7)),
                ('report-online', lambda d: d['report'].__setitem__('online', 7)),
                ('root', lambda d: d['domain'].__setitem__(9, d['report']['root'] + 4096)),
                ('zero-root', lambda d: (d['report'].__setitem__('root', 0), d['domain'].__setitem__(9, 0))),
                ('unaligned-root', lambda d: (d['report'].__setitem__('root', 1), d['domain'].__setitem__(9, 1))),
                ('pre-zero', lambda d: d['report'].__setitem__('pre_sequence', 0)),
                ('post-gap', lambda d: d['report'].__setitem__('post_sequence', 42)),
                ('wrapped-post', lambda d: d['report'].update(pre_sequence=(1 << 64) - 1, post_sequence=0)),
                ('overflow-post', lambda d: d['report'].update(pre_sequence=(1 << 64) - 1, post_sequence=1 << 64)),
                ('bool-pre', lambda d: d['report'].__setitem__('pre_sequence', True)),
                ('bool-post', lambda d: d['report'].__setitem__('post_sequence', True)),
                ('barrier-open', lambda d: d['domain'].__setitem__(6, 41)),
                ('expected-open', lambda d: d['domain'].__setitem__(7, 15)),
                ('sequence-not-completed', lambda d: d['domain'].__setitem__(5, 42)),
                ('completed-before-post', lambda d: d['domain'].__setitem__(8, 40)),
                ('closed-before-post', lambda d: (d['domain'].__setitem__(5, 40), d['domain'].__setitem__(8, 40),
                    [c.__setitem__(slice(7, 9), [40, 40]) for c in d['cpus'][:4]])),
                ('completed-overflow', lambda d: (d['domain'].__setitem__(5, 1 << 64),
                                                 d['domain'].__setitem__(8, 1 << 64))),
            ]
            for cpu in range(4):
                for field, value in ((7, 40), (8, 40), (8, 42)):
                    controls.append(('cpu%d-field%d-value%d' % (cpu, field, value),
                        lambda d, c=cpu, f=field, v=value: d['cpus'][c].__setitem__(f, v)))
                controls.append(('cpu%d-paired-stale' % cpu,
                    lambda d, c=cpu: d['cpus'][c].__setitem__(slice(7, 9), [40, 40])))
            for name, mutate in controls:
                with self.subTest(negative=negative, control=name):
                    changed = copy.deepcopy(original);mutate(changed)
                    with self.assertRaises(ValueError):
                        runner.validate_barrier_controls(changed, negative=negative, require_pcid=True)

    def test_raw_barrier_rejects_held_modes_and_every_cpu_hardware_control(self):
        original = barrier_fixture(negative=True)
        controls = [
            ('later-sequence', lambda d: (d['domain'].__setitem__(5, 42), d['domain'].__setitem__(8, 42),
                [c.__setitem__(slice(7, 9), [42, 42]) for c in d['cpus'][:4]])),
            ('not-failed', lambda d: d['domain'].__setitem__(1, 0)),
            ('unlocked', lambda d: d['domain'].__setitem__(2, 0)),
            ('foreign-owner', lambda d: d['domain'].__setitem__(3, 2)),
        ]
        for cpu in range(4):
            for mode in ((1, 2, 3, 4, 6) if cpu == 0 else (2, 3, 5, 6)):
                controls.append(('cpu%d-mode%d' % (cpu, mode),
                    lambda d, c=cpu, m=mode: d['cpus'][c].__setitem__(0, m)))
            controls.append(('cpu%d-user-cs' % cpu,
                lambda d, c=cpu: d['registers'][c].__setitem__('CS', 0x33)))
        for name, mutate in controls:
            with self.subTest(control=name):
                changed = copy.deepcopy(original);mutate(changed)
                with self.assertRaises(ValueError):
                    runner.validate_barrier_controls(changed, negative=True, require_pcid=True)
        for negative in (False, True):
            for cpu in range(4):
                controls = [
                    ('tag17', lambda d: d['registers'][cpu].__setitem__('CR3', original['report']['root'] | 17)),
                    ('foreign-root', lambda d: d['registers'][cpu].__setitem__('CR3', original['report']['root'] + 4096)),
                    ('pge', lambda d: (d['registers'][cpu].__setitem__('CR4', (1 << 17) | 128),
                                      d['metrics'][cpu].__setitem__(18, (1 << 17) | 128))),
                    ('readback', lambda d: d['metrics'][cpu].__setitem__(18, 0)),
                    ('fallback', lambda d: (d['registers'][cpu].__setitem__('CR4', 0),
                                           d['metrics'][cpu].__setitem__(18, 0))),
                ]
                for name, mutate in controls:
                    with self.subTest(negative=negative, cpu=cpu, control=name):
                        changed = barrier_fixture(negative=negative);mutate(changed)
                        with self.assertRaises(ValueError):
                            runner.validate_barrier_controls(changed, negative=negative, require_pcid=True)

    def test_production_validate_cannot_bypass_raw_barrier_gate(self):
        # Exercise actual validate and actual helper before adapting later raw
        # oracles. This adapter never manufactures a full guest certificate.
        for negative in (False, True):
            after = barrier_fixture(negative=negative)
            physical, payload = 0x10000000, b'explicit host payload boundary'
            before = dict(synthetic=False, report={'attempted': 0}, requested=False,
                          physical=physical, payload=payload)
            after.update(synthetic=False, requested=True, physical=physical, payload=payload,
                         kernel_space=struct.pack('<8Q', 1, 0, 128, after['report']['root'], 0, 0, 0, 0))
            after['report'].update(version=1, attempted=1, physical=physical, old_checksum=0)
            for cpu in range(4):
                changed = copy.deepcopy(after);changed['cpus'][cpu][8] -= 1
                with self.subTest(negative=negative, cpu=cpu), \
                     mock.patch.object(runner, 'digest', side_effect=AssertionError('raw ACK gate was bypassed')) as digest:
                    with self.assertRaisesRegex(ValueError, 'all-tag barrier acknowledgement'):
                        runner.validate(before, changed, {}, negative=negative, require_pcid=True)
                    digest.assert_not_called()
            with mock.patch.object(runner, 'digest', side_effect=LookupError('next independent whole-window oracle')):
                with self.assertRaisesRegex(LookupError, 'next independent whole-window oracle'):
                    runner.validate(before, after, {}, negative=negative, require_pcid=True)

    def test_synthetic_reader_rejects_omitted_ack_replay_cpu_tag_pge_and_no_timer(self):
        report, readers, metrics = reader_fixture()
        controls = [
            lambda r, m: r[1].update(ack=3),
            lambda r, m: r[1].update(count=3),
            lambda r, m: r[1]['warm'].update(cpu=2),
            lambda r, m: r[1]['warm'].update(root=report['root'] | 17),
            lambda r, m: r[1]['warm'].update(cr4=0x20080),
            lambda r, m: r[1]['replaced'].update(value=runner.TAG | 5),
            lambda r, m: r[4].update(request=1),
            lambda r, m: m[2].__setitem__(2, 0),
        ]
        for control in controls:
            with self.subTest(control=control):
                r, m = copy.deepcopy(readers), copy.deepcopy(metrics)
                control(r, m)
                with self.assertRaises(ValueError):
                    runner.validate_readers(report, r, m)

    def test_require_pcid_fails_actual_fallback_contract(self):
        report, readers, metrics = reader_fixture()
        for cpu in range(4):
            metrics[cpu][18] = 0
            for name in ['warm', 'replaced', 'restored', 'merged']:
                readers[cpu][name]['cr4'] = 0
        runner.validate_readers(report, readers, metrics, require_pcid=False)
        with self.assertRaisesRegex(ValueError, 'fallback is not a pass'):
            runner.validate_readers(report, readers, metrics, require_pcid=True)

    def test_synthetic_complete_kernel_forests_and_hardware_high_pa_rejection(self):
        for negative in [False, True]:
            image, meta, space, held = kernel_fixture(negative)
            result = runner.kernel_forest(image, meta, space, held, negative=negative)
            self.assertEqual(513 if negative else 1, result['held_aliases'])
            bad = bytearray(image)
            struct.pack_into('<Q', bad, 0, (1 << 49) | 7)
            with self.assertRaises(ValueError):
                runner.kernel_forest(bad, meta, space, held, negative=negative)

    def test_synthetic_kernel_hidden_alias_pending_and_wrong_b_leaf_rejected(self):
        for control in ['extra', 'pending', 'wrong-b', 'cache', 'wx']:
            image, meta, space, held = kernel_fixture(True)
            if control == 'extra':
                struct.pack_into('<Q', image, 2 * 4096 + 16, held | runner.NX | 131)
            elif control == 'pending':
                meta[3] = 2
            elif control == 'wrong-b':
                struct.pack_into('<Q', image, 3 * 4096 + 5 * 8, held + 5 * 4096 | runner.NX | 3)
            elif control == 'cache':
                struct.pack_into('<Q', image, 3 * 4096 + 7 * 8, held + 7 * 4096 | runner.NX | 0x1b)
            else:
                struct.pack_into('<Q', image, 3 * 4096 + 7 * 8, held + 7 * 4096 | 3)
            with self.subTest(control=control), self.assertRaises(ValueError):
                runner.kernel_forest(image, meta, space, held, negative=True)

    def test_digest_covers_interior_words_and_preserves_exact_size(self):
        data = bytes(runner.LENGTH)
        base = runner.digest(data)
        changed = bytearray(data);changed[77777] = 1
        self.assertNotEqual(base, runner.digest(changed))
        with self.assertRaises(ValueError):
            runner.digest(data[:-1])

    def test_raw_register_parser_rejects_duplicate_cr3(self):
        with self.assertRaisesRegex(ValueError, 'missing/duplicate'):
            runner.raw.parse_registers('CR0=80010033 CR3=123000 CR3=123000 CR4=20000 RIP=10 RSP=20')

    def test_default_cli_and_replay_never_construct_guest(self):
        with mock.patch.object(build, 'identity', return_value={'synthetic_host_control': True}), \
             mock.patch.object(runner, 'execute') as execute, mock.patch.object(runner, 'LargeGuest') as guest, \
             mock.patch('subprocess.Popen', side_effect=AssertionError('VM/other process forbidden')):
            self.assertEqual(0, runner.main(['--reuse-esp', str(ROOT / 'build/not-executed/esp')]))
            execute.assert_not_called();guest.assert_not_called()
        with mock.patch.object(runner, 'replay', return_value={'passed': False}), mock.patch.object(runner, 'LargeGuest') as guest:
            self.assertEqual(1, runner.main(['--replay', 'synthetic-host-control.json']))
            guest.assert_not_called()

    def test_cli_exit_status_uses_final_passed(self):
        for passed in [True, False]:
            with mock.patch.object(runner, 'execute', return_value={'passed': passed}), mock.patch.object(runner, 'LargeGuest') as guest:
                self.assertEqual(0 if passed else 1, runner.main(['--execute', '--reuse-esp', 'synthetic-esp']))
                guest.assert_not_called()

    def test_late_source_tool_disk_change_revokes_pass_and_seal(self):
        with tempfile.TemporaryDirectory() as temporary:
            disk = Path(temporary) / 'disk';disk.write_bytes(b'actual ordinary host bytes')
            identity = {'synthetic_host_control': True}
            tools = {'path': 'hash'}
            for change in ['source', 'tool', 'disk', 'exception']:
                result = dict(passed=True, seal={'passed': True}, final_disk_sha256=build.sha(disk))
                with mock.patch.object(build, 'identity', return_value=identity if change != 'source' else {'changed': True}) as binding, \
                     mock.patch.object(runner, 'source_tools', return_value=tools if change != 'tool' else {'changed': 'hash'}):
                    if change == 'disk':
                        result['final_disk_sha256'] = hashlib.sha256(b'earlier bytes').hexdigest()
                    if change == 'exception':
                        binding.side_effect = ValueError('changed source')
                    runner.final_inputs(result, 'esp', identity, tools, disk)
                self.assertFalse(result['passed'])
                self.assertFalse(result['inputs_unchanged'])
                self.assertNotIn('seal', result)
                self.assertIn('invalidated_seal', result)


class RequestGateTests(unittest.TestCase):
    def test_actual_dong_request_gate_and_eight_wrong_implementations(self):
        from lang.dongc import compile_file
        from lang.tests.test_dongc import nasm_flags, tool
        source = (ROOT / 'kernel/user/services.dg').read_text(encoding='utf-8')
        actual = source[source.index('unsafe fn large_request()'):source.index('unsafe fn process_call(')]
        call = source[source.index('if code==proc.SPAWN||code==proc.EXEC{'):source.index('if code==proc.WAIT{')]
        self.assertEqual(1, call.count('try large_request();'))
        self.assertLess(call.index('try manager((*frame).rdi,handles.WRITE)'), call.index('try launch('))
        self.assertLess(call.index('try memory.copy_out('), call.index('try large_request();'))
        # Actual Catalog/ABI and actual production predicate. Only the trusted
        # hardware bridge and memory.Process geometry are host data adapters.
        domain = '''module sched.user_domain;import sched.multicore as q;pub const LOCKED:u64=5;
pub struct Cpu{pub mode:u64,pub slot:u64,pub token:u64,pub incarnation:u64}
pub const EMPTY_CPU:Cpu=Cpu{mode:0,slot:0,token:0,incarnation:0};
pub struct Process{pub token:u64,pub incarnation:u64,pub root:u64,pub frame:u64}
pub const EMPTY_PROCESS:Process=Process{token:0,incarnation:0,root:0,frame:0};
pub struct Domain{pub ready:u64,pub failed:u64,pub owner:u64,pub lock:u64,pub online:u64,pub cpus:*Cpu,pub processes:*Process,pub engine:*q.Engine}
pub const EMPTY_DOMAIN:Domain=Domain{ready:0,failed:0,owner:0,lock:0,online:0,cpus:null,processes:null,engine:null};
'''
        bridge = '''module sched.user_bridge;import sched.user_domain as d;import sched.multicore as q;
pub struct Bridge{pub ready:u64,pub failed:u64,pub domain:*d.Domain}
pub var B:Bridge=Bridge{ready:0,failed:0,domain:null};pub var D:d.Domain=d.EMPTY_DOMAIN;
pub var C:d.Cpu=d.EMPTY_CPU;pub var P:d.Process=d.EMPTY_PROCESS;pub var ACTIVE:*Bridge=null;
pub var E:q.Engine=q.Engine{ready:0,online:0,sequence:0,count:0,cpus:[q.EMPTY_CPU;16],threads:[q.EMPTY_THREAD;64]};
pub fn pointer()*Bridge{unsafe{return ACTIVE;}}
'''
        prefix = '''module large_request_probe;import lib.process_abi as proc;import user.processes as procs;
import sched.user_domain as smp_domain;import sched.user_bridge as smp_bridge;import sched.multicore as smp_queue;
import user.memory as memory;
pub error Protocol=0x5111;const COUNT:usize=16;var CURRENT:usize=0;var SMP_ENABLED:bool=true;
var LARGE_REQUESTED:bool=false;var LAUNCH_FAILED:bool=false;
struct Frame{cr3:u64}struct Process{ready:u64,root:u64,frame:Frame}
const EMPTY_PROCESS:Process=Process{ready:0,root:0,frame:Frame{cr3:0}};
var PROCESSES:[16]Process=[EMPTY_PROCESS;16];unsafe fn process(id:usize)*Process{unsafe{return &PROCESSES[id];}}
var SAVED:[5]proc.Snapshot=[proc.EMPTY_SNAPSHOT;5];
var CAT:procs.Catalog=procs.Catalog{ready:0,count:0,sequence:0,configs:[proc.EMPTY_CONFIG;32],
states:[proc.EMPTY_SNAPSHOT;32],slot:[0;32],incarnation:[0;16],configuration:[0;16],events:[proc.EMPTY_EVENT;64]};
var CATALOG:*procs.Catalog=null;var SNAPSHOT:proc.Snapshot=proc.EMPTY_SNAPSHOT;
unsafe fn setup(cfg:usize)void{unsafe{
 CURRENT=0;SMP_ENABLED=true;LARGE_REQUESTED=false;LAUNCH_FAILED=false;CATALOG=&CAT;
 var index:usize=0;while index<16{
  CAT.configuration[index]=procs.NONE;CAT.incarnation[index]=0;
  PROCESSES[index]=EMPTY_PROCESS;memory.GENERATIONS[index]=0;index+=1;
 }
 index=0;while index<32{
  CAT.configs[index]=proc.EMPTY_CONFIG;CAT.configs[index].id=index as u64;
  CAT.states[index]=proc.EMPTY_SNAPSHOT;CAT.states[index].configuration=index as u64;
  CAT.slot[index]=procs.NONE;index+=1;
 }
 CAT.ready=1;CAT.count=procs.CONFIGS;CAT.slot[0]=0;CAT.configuration[0]=0;CAT.incarnation[0]=9;
 CAT.states[0]=proc.Snapshot{version:1,configuration:0,process:2305,generation:17,state:proc.READY,status:0,sequence:1,argument:0};
 index=7;while index<12{
  var member=index;if index==7{member=8;}if index==8{member=9;}if index==9{member=7;}
  let epoch=member as u64-4;let root=0x200000+(member as u64-7)*0x100000;
  CAT.configs[index].flags=proc.ORDINARY;CAT.slot[index]=member as u64;
  CAT.configuration[member]=index as u64;CAT.incarnation[member]=epoch;
  CAT.states[index]=proc.Snapshot{version:1,configuration:index as u64,process:(epoch<<8)|(member as u64+1),
   generation:index as u64+2,state:proc.STARTING,status:0,sequence:index as u64,argument:index as u64*17};
  PROCESSES[member]=Process{ready:1,root:root,frame:Frame{cr3:root}};
  memory.GENERATIONS[member]=37+(member as u64-7)*2;index+=1;
 }
 if cfg==12{
  CAT.configs[12].flags=proc.ORDINARY;CAT.slot[12]=12;CAT.configuration[12]=12;CAT.incarnation[12]=8;
  CAT.states[12]=proc.Snapshot{version:1,configuration:12,process:2061,generation:19,state:proc.STARTING,status:0,sequence:20,argument:61};
  PROCESSES[12]=Process{ready:1,root:0x700000,frame:Frame{cr3:0x700000}};memory.GENERATIONS[12]=49;
 }
 SNAPSHOT=CAT.states[cfg];
 PROCESSES[0]=Process{ready:1,root:0x100000,frame:Frame{cr3:0x100000}};
 smp_bridge.ACTIVE=&smp_bridge.B;smp_bridge.B.ready=1;smp_bridge.B.failed=0;smp_bridge.B.domain=&smp_bridge.D;
 memory.GENERATIONS[0]=31;
 smp_bridge.D.ready=1;smp_bridge.D.failed=0;smp_bridge.D.owner=0;smp_bridge.D.lock=1;smp_bridge.D.online=15;
 smp_bridge.D.cpus=&smp_bridge.C;smp_bridge.D.processes=&smp_bridge.P;smp_bridge.D.engine=&smp_bridge.E;
 smp_bridge.E.ready=1;smp_bridge.E.online=15;smp_bridge.E.cpus[0].current=0;
 smp_bridge.E.threads[0]=smp_queue.Thread{state:smp_queue.RUNNING,priority:8,affinity:1,cpu:0,
 next:smp_queue.NONE,previous:smp_queue.NONE,generation:23,frame:(&PROCESSES[0].frame) as u64};
 smp_bridge.C.mode=smp_domain.LOCKED;smp_bridge.C.slot=0;smp_bridge.C.token=5889;smp_bridge.C.incarnation=9;
 smp_bridge.P.token=5889;smp_bridge.P.incarnation=9;smp_bridge.P.root=PROCESSES[0].root;
 smp_bridge.P.frame=(&PROCESSES[0].frame) as u64;
}return;}
unsafe fn missing(id:usize,state:u64)void{unsafe{
 let member=CAT.slot[id] as usize;CAT.configuration[member]=procs.NONE;
 CAT.states[id].state=state;CAT.states[id].process=0;CAT.slot[id]=procs.NONE;
 if state==proc.STOPPED{CAT.states[id].generation=0;CAT.states[id].sequence=0;CAT.states[id].argument=0;}
}return;}
'''
        changes = {
            1: 'SMP_ENABLED=false;', 2: 'CURRENT=5;', 3: 'LARGE_REQUESTED=true;',
            4: 'SNAPSHOT.configuration=14;', 5: 'SNAPSHOT.configuration=5;',
            7: 'CAT.configs[cfg].flags=0;', 8: 'CATALOG=null;', 9: 'CAT.ready=0;',
            10: 'CAT.slot[0]=1;', 11: 'CAT.configuration[0]=1;', 12: 'CAT.states[0].generation=0;',
            13: 'CAT.states[0].state=proc.STARTING;', 14: 'CAT.incarnation[0]+=1;',
            15: 'smp_bridge.ACTIVE=null;', 16: 'smp_bridge.B.failed=1;', 17: 'smp_bridge.B.domain=null;',
            18: 'smp_bridge.D.failed=1;', 19: 'smp_bridge.D.owner=1;', 20: 'smp_bridge.D.lock=0;',
            21: 'smp_bridge.C.mode=1;', 22: 'smp_bridge.C.slot=1;', 23: 'smp_bridge.C.token+=256;',
            24: 'smp_bridge.C.incarnation+=1;', 25: 'smp_bridge.P.root+=4096;',
            26: 'smp_bridge.P.frame+=8;', 27: 'smp_bridge.P.incarnation+=1;',
            28: 'PROCESSES[0].frame.cr3+=4096;', 29: 'SNAPSHOT.process=0;',
            30: 'SNAPSHOT.process=785;', 31: 'SNAPSHOT.process=782;', 32: 'CAT.incarnation[7]+=1;',
            33: 'CAT.slot[cfg]=8;', 34: 'CAT.configuration[7]=8;', 35: 'SNAPSHOT.version=0;',
            36: 'SNAPSHOT.state=proc.READY;', 37: 'SNAPSHOT.status=1;', 38: 'SNAPSHOT.generation=0;',
            39: 'CAT.states[cfg].generation+=1;', 40: 'CAT.states[cfg].argument+=1;',
            41: 'PROCESSES[7].ready=0;', 42: 'PROCESSES[7].frame.cr3+=4096;',
            43: 'smp_bridge.D.ready=0;', 44: 'CAT.count=17;', 45: 'smp_bridge.P.token+=256;',
            46: 'smp_bridge.D.engine=null;', 47: 'smp_bridge.E.ready=0;', 48: 'smp_bridge.E.online=7;',
            49: 'smp_bridge.E.cpus[0].current=1;', 50: 'smp_bridge.E.threads[0].generation+=1;',
            51: 'smp_bridge.E.threads[0].state=smp_queue.READY;', 52: 'smp_bridge.E.threads[0].cpu=1;',
            53: 'smp_bridge.E.threads[0].frame+=8;',
            54: 'smp_bridge.P.token=5890;smp_bridge.C.token=5890;',
            55: 'smp_bridge.P.token=0;smp_bridge.C.token=0;',
            56: 'smp_bridge.P.token=1;smp_bridge.C.token=1;smp_bridge.E.threads[0].generation=0;',
            57: 'missing(7,proc.STOPPED);',
            58: 'missing(8,proc.STOPPED);',
            59: 'missing(10,proc.STOPPED);',
            60: 'missing(11,proc.STOPPED);',
            61: 'missing(7,proc.STOPPED);PROCESSES[11].frame.cr3+=4096;',
            62: 'CAT.states[7].process+=256;',
            63: 'CAT.states[7].generation=0;',
            64: 'PROCESSES[8].root=0;',
            65: 'PROCESSES[8].frame.cr3+=4096;',
            66: 'PROCESSES[8].ready=0;',
            67: 'CAT.states[7].version=0;',
            68: 'CAT.configs[7].id=8;',
            69: 'CAT.configs[7].flags=0;',
            70: 'CAT.incarnation[8]=0;',
            71: 'CAT.slot[7]=9;',
            72: 'CAT.states[7].process=CAT.states[8].process;CAT.slot[7]=9;',
            73: 'memory.GENERATIONS[8]=0;',
            74: 'CAT.states[7].state=6;',
            75: 'CAT.states[7].state=proc.STOPPED;',
            76: 'missing(7,proc.EXITED);',
            77: 'CAT.states[7].state=proc.READY;',
            79: 'CAT.states[7].configuration=8;',
            80: 'CAT.states[7].status=1;',
            81: 'CAT.states[7].process=0;',
            82: 'CAT.states[7].process=0x100;',
            83: 'CAT.incarnation[8]=0x1000_0000;',
        }
        tail = '''export("large_request_case") fn test(kind:u64)u64{unsafe{
 var cfg:usize=9;if kind==6{cfg=12;}if kind==78{cfg=11;}setup(cfg);
''' + '\n'.join('if kind==' + str(n) + '{' + body + '}' for n, body in changes.items()) + '''
 var result:u64=0;match large_request(){ok=>{},err(code)=>{result=code;},}
 if LARGE_REQUESTED{result|=0x1_0000_0000;}if LAUNCH_FAILED{result|=0x2_0000_0000;}return result;
}}
export("large_request_namespaces") fn namespaces(out:*u64)void{unsafe{
 *out=smp_bridge.P.token>>8;*(out+1)=CAT.incarnation[0];*(out+2)=CAT.states[0].generation;*(out+3)=memory.GENERATIONS[0];
}return;}
export("large_request_progress") fn progress()u64{unsafe{
 setup(9);var index:usize=0;while index<5{
  let id=index+7;SAVED[index]=CAT.states[id];missing(id,proc.STOPPED);index+=1;
 }
 var armed:u64=0;index=0;while index<5{
  let id=index+7;let saved=SAVED[index];CAT.states[id]=saved;
  let member=(saved.process&255)-1;CAT.slot[id]=member;CAT.configuration[member as usize]=id as u64;SNAPSHOT=saved;
  match large_request(){ok=>{},err(code)=>{return 0xffff_ffff_ffff_ffff;},}
  if LAUNCH_FAILED{return 0xffff_ffff_ffff_ffff;}if LARGE_REQUESTED{armed|=1<<index as u64;}index+=1;
 }
 return armed;
}}
'''
        c = r'''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define ABI __attribute__((sysv_abi))
extern uint64_t ABI large_request_case(uint64_t);
extern void ABI large_request_namespaces(uint64_t*);
extern uint64_t ABI large_request_progress(void);
void ABI __dong_panic(void){fputs("unexpected Dong panic\n",stderr);exit(2);}
int main(void){
 uint64_t first=large_request_case(0),ns[4];large_request_namespaces(ns);
 if(first!=UINT64_C(0x100000000)||ns[0]!=23||ns[1]!=9||ns[2]!=17||ns[3]!=31){
  fputs("request gate mismatch: legal distinct queue/catalog/incarnation/memory generations rejected\n",stderr);return 1;}
 for(unsigned n=0;n<=83;n++){
 uint64_t expected=n==0||n==3||n==6||n==77||n==78?UINT64_C(0x100000000):
  n<=6||(n>=57&&n<=60)||n==76?0:UINT64_C(0x200005111);
 uint64_t observed=large_request_case(n);if(observed!=expected){
  fprintf(stderr,"request gate mismatch case=%u observed=%llx expected=%llx\n",n,(unsigned long long)observed,(unsigned long long)expected);return 1;
 }}if(large_request_progress()!=UINT64_C(16)){
 fputs("request gate mismatch: first four commits armed or fifth did not arm\n",stderr);return 1;
 }puts("actual request gate: queue23/catalog17/incarnation9/memory31, five independent configs, 84 cases + five commit phases");return 0;}
'''
        out = ROOT / 'build/test/runtime-large-request' / ('run-' + uuid.uuid4().hex[:12]);out.mkdir(parents=True)
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'required native tools, zero skip')
        controls = {'normal': None, 'foreign-current': ('||CURRENT!=0', ''),
                    'wrong-child-generation': ('||child.generation!=SNAPSHOT.generation', ''),
                    'wrong-bkl-owner': ('||(*d).owner!=0', ''),
                    'conflate-queue-catalog': ('(*cpu).token!=(*caller).token', '(*cpu).token!=shell.process'),
                    'incomplete-arms': ('if !complete{return;}', ''),
                    'foreign-member-frame': ('||(*process(member)).frame.cr3!=(*process(member)).root', ''),
                    'foreign-member-generation': ('||item.generation==0', ''),
                    'missing-hides-corruption': ('complete=false;', 'return;')}
        evidence = {}
        for mode in ('debug', 'release'):
            for variant, mutation in controls.items():
                d = out / (mode + '-' + variant);d.mkdir()
                body = actual
                if mutation:
                    old, new = mutation;self.assertEqual(1, body.count(old));body = body.replace(old, new)
                files = {'large_request_probe.dg': prefix + body + tail,
                         'sched/user_domain.dg': domain, 'sched/user_bridge.dg': bridge,
                         'sched/multicore.dg': (ROOT / 'kernel/sched/multicore.dg').read_text(encoding='utf-8'),
                         'user/processes.dg': (ROOT / 'kernel/user/processes.dg').read_text(encoding='utf-8'),
                         'user/memory.dg': 'module user.memory;pub var GENERATIONS:[16]u64=[0;16];pub fn generation(id:usize)u64{unsafe{return GENERATIONS[id];}}',
                         'lib/process_abi.dg': (ROOT / 'services/lib/process_abi.dg').read_text(encoding='utf-8')}
                for name, text in files.items():
                    p = d / name;p.parent.mkdir(parents=True, exist_ok=True);p.write_text(text, encoding='utf-8')
                compiled = compile_file(d / 'large_request_probe.dg', roots=[d], mode=mode)
                assembly = d / 'probe.asm';assembly.write_text(compiled.assembly, encoding='utf-8')
                (d / 'probe.c').write_text(c, encoding='utf-8')
                def run(argv, label):
                    result = subprocess.run(list(map(str, argv)), cwd=ROOT, capture_output=True, text=True, timeout=60)
                    build.write(d / (label + '.json'), dict(argv=list(map(str, argv)), returncode=result.returncode,
                                                          stdout=result.stdout, stderr=result.stderr))
                    return result
                obj = d / 'probe.o'
                result = run([nasm, '-f', 'win64' if os.name == 'nt' else 'elf64', *nasm_flags(nasm), assembly, '-o', obj], 'assemble')
                self.assertEqual(0, result.returncode, result.stderr)
                exe = d / ('probe.exe' if os.name == 'nt' else 'probe')
                result = run([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-D__USE_MINGW_ANSI_STDIO=1',
                              *([] if os.name == 'nt' else ['-no-pie']), d / 'probe.c', obj, '-o', exe], 'link')
                self.assertEqual(0, result.returncode, result.stderr)
                result = run([exe], 'native')
                self.assertEqual(0 if mutation is None else 1, result.returncode, result.stdout + result.stderr)
                if mutation:
                    self.assertIn('request gate mismatch', result.stderr)
                evidence[mode + '-' + variant] = dict(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        build.write(out / 'validation-summary.json', dict(passed=True, actual_guest_executed=False,
                    actual_dong_predicate=True, trusted_bridge_memory_geometry_adapted=True,
                    source_sha256=hashlib.sha256(source.encode()).hexdigest(), evidence=evidence))


class ActualBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = ROOT / 'build/test/p2-runtime-large-build' / ('run-' + uuid.uuid4().hex[:12])
        cls.out.mkdir(parents=True)
        cls.before = build.inputs(ROOT)
        cls.records = {}
        # Only the coordinator executes this suite. These are fresh real
        # production OS links, never mocked/stubbed artifacts or VM launches.
        with mock.patch.object(runner, 'LargeGuest', side_effect=AssertionError('host suite cannot boot guest')):
            for case in [None, 'omit-ap-flush']:
                path = cls.out / (case or 'normal')
                cls.records[case] = build.build(path, source_root=ROOT, case=case)

    @classmethod
    def tearDownClass(cls):
        after = build.inputs(ROOT)
        stable = cls.before == after
        build.write(cls.out / 'host-build-result.json', dict(passed=stable and len(cls.records) == 2,
            source_before=cls.before, source_after=after, source_stable=stable,
            actual_os_links=len(cls.records), actual_guest_executed=False))
        if not stable:
            raise AssertionError('production inputs changed during host build suite')

    def test_actual_both_source_bound_builds_and_loader_budget(self):
        for case, record in self.records.items():
            with self.subTest(case=case):
                self.assertEqual(record, build.identity(record['esp']))
                esp = Path(record['esp'])
                self.assertEqual(b'\x7fELF\x02\x01', (esp.parent / 'kernel.elf').read_bytes()[:6])
                self.assertLessEqual(record['kernel_bytes'], 2 * 1024 * 1024)
                self.assertTrue(record['built'] and record['os_link_executed'])
                self.assertFalse(record['actual_guest_executed'])
                contract = runner.layout_contract(esp)
                self.assertLess(contract['types']['mm.runtime_large.Context']['size'], 32 * 4096)
                self.assertEqual(232, contract['types']['mm.runtime_large.Report']['size'])
                self.assertEqual(1, contract['static_pools'])

    def test_private_bad_body_changes_only_owner_window_and_ap1_flush(self):
        normal, bad = self.records[None], self.records['omit-ap-flush']
        source = Path(bad['output']) / 'source'
        changes = set(bad['overlay_paths']) - set(normal['overlay_paths'])
        self.assertEqual({'kernel/sched/user_arch.asm', 'kernel/sched/runtime_large_reader.asm'}, changes)
        arch = (source / 'kernel/sched/user_arch.asm').read_text()
        self.assertEqual(1, arch.count('call runtime_large_test_omit'))
        reader = (source / 'kernel/sched/runtime_large_reader.asm').read_text()
        self.assertIn('cmp rdi,1', reader)
        self.assertIn('cmp qword [rel runtime_large_window_active],1', reader)
        self.assertIn('invpcid rax,[rsp]', arch)
        self.assertIn('mov cr3,r8', arch)

    def test_actual_staged_source_tamper_rejected_and_restored(self):
        record = self.records[None]
        path = Path(record['output']) / 'source/kernel/mm/runtime_large.dg'
        old = path.read_bytes()
        try:
            path.write_bytes(old + b'\n// actual staged byte mutation\n')
            with self.assertRaises(ValueError):
                build.identity(record['esp'])
        finally:
            path.write_bytes(old)
        self.assertEqual(record, build.identity(record['esp']))

    def test_actual_kernel_artifact_tamper_rejected_and_restored(self):
        record = self.records[None]
        path = Path(record['esp']).parent / 'kernel.bin'
        old = path.read_bytes()
        try:
            changed = bytearray(old);changed[len(changed) // 2] ^= 1;path.write_bytes(changed)
            with self.assertRaises(ValueError):
                build.identity(record['esp'])
        finally:
            path.write_bytes(old)
        self.assertEqual(record, build.identity(record['esp']))

    def test_actual_manifest_boot_info_layout_corruption_rejected_and_restored(self):
        record = self.records[None]
        path = Path(record['esp']).parent / 'dong_layout.json'
        original = path.read_bytes()
        for field in ('size', 'magic', 'version', 'size-offset', 'kernel_physical'):
            layout = json.loads(original)
            info = next(t for t in layout['types'] if t['full_name'] == 'boot.abi.BootInfo')
            if field == 'size':
                info['size'] = 152
            else:
                name = 'size' if field == 'size-offset' else field
                next(f for f in info['fields'] if f['name'] == name)['offset'] += 8
            try:
                build.write(path, layout)
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'BootInfo layout ABI'):
                    runner.layout_contract(record['esp'])
            finally:
                path.write_bytes(original)
        self.assertEqual(160, runner.layout_contract(record['esp'])['types']['boot.abi.BootInfo']['size'])

    def test_prepare_only_does_not_start_any_process(self):
        path = self.out / 'prepare-only'
        with mock.patch('subprocess.Popen', side_effect=AssertionError('prepare must not execute')):
            result = build.prepare(path, source_root=ROOT)
        self.assertFalse(result['built'])
        self.assertFalse(result['os_link_executed'])
        self.assertFalse(result['actual_guest_executed'])
        self.assertEqual(result, build.verify_prepared(path, source_root=ROOT))

    def test_sparse_or_wrong_tool_role_receipts_rejected(self):
        record = self.records[None]
        receipt = Path(record['output']) / 'runtime-large-source.json'
        original = receipt.read_bytes()
        for kind in ['artifact', 'roles-empty', 'roles-wrong', 'tool-set', 'returncode']:
            changed = copy.deepcopy(record)
            if kind == 'artifact':
                changed['artifacts_sha256'].pop('services/settings/program.elf')
            elif kind == 'roles-empty':
                changed['build_tool_roles'] = {}
            elif kind == 'roles-wrong':
                changed['build_tool_roles']['nasm'] = dict(changed['build_tool_roles']['python'])
            elif kind == 'tool-set':
                changed['build_tools_sha256'] = {}
            else:
                changed['build_returncode'] = 17
            try:
                build.write(receipt, changed)
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    build.identity(record['esp'])
            finally:
                receipt.write_bytes(original)
        self.assertEqual(record, build.identity(record['esp']))

    def test_rehashed_command_and_production_forgery_rejected(self):
        record = self.records[None]
        output = Path(record['output'])
        receipt = output / 'runtime-large-source.json'
        old_receipt = receipt.read_bytes()
        for kind in ['command', 'production']:
            target = output / ('build-command.json' if kind == 'command' else 'image/build-inputs.json')
            old = target.read_bytes()
            changed = copy.deepcopy(record)
            value = json.loads(old)
            if kind == 'command':
                value['argv'][-1] = 'pass'
            else:
                value['kernel_storage_profile']['static_user_pools'] = 3
            try:
                build.write(target, value)
                if kind == 'command':
                    changed['build_command_sha256'] = build.sha(target)
                else:
                    changed['production_manifest_sha256'] = build.sha(target)
                    changed['artifacts_sha256']['build-inputs.json'] = build.sha(target)
                build.write(receipt, changed)
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    build.identity(record['esp'])
            finally:
                target.write_bytes(old)
                receipt.write_bytes(old_receipt)
        self.assertEqual(record, build.identity(record['esp']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
