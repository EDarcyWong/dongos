"""Host-only initial-DAG controls. No QEMU, tool installation, or guest writes."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest import mock

from tests import run_p6_initial_dag_qemu as r
from tests.test_user_smp_oracle import fixture as cpu_fixture
from tests.test_p6_kvm_runner import decoded_fixture


def catalog_bytes(final=False):
    raw = bytearray(r.CATALOG_BYTES)
    order = [5, 6, 2, 4, 1, 3, 0] + ([14, 15, 16, 17] if final else [14])
    struct.pack_into('<3Q', raw, 0, 1, 18, len(order))
    slots, inc, inverse = [r.NONE] * 32, [0] * 16, [r.NONE] * 16
    for cfg in range(32):
        if cfg < 18:
            flags = 7 if cfg in (0, 1, 3, 6) else 5 if cfg < 7 else 4 if cfg == 13 else 9 if cfg in r.GUI else 8
            name = r.life.NAMES[cfg].encode()
            struct.pack_into('<8Q', raw, 24 + cfg * 128, 1, cfg, r.life.DEPS[cfg],
                             3 if cfg in (0, 1, 3, 6) else 0, 10000000000, flags, cfg + 1, len(name))
            raw[24 + cfg * 128 + 64:24 + cfg * 128 + 64 + len(name)] = name
        else:
            struct.pack_into('<Q', raw, 24 + cfg * 128, 1)
        live = cfg < 7 or cfg in ((14, 15, 16, 17) if final else (14, 15))
        if live:
            slot = cfg if cfg < 7 else cfg - 7
            slots[cfg], inc[slot], inverse[slot] = slot, 1, cfg
            token, generation, state = 256 + slot + 1, 1, 2 if cfg in order else 1
            sequence = order.index(cfg) + 1 if cfg in order else len(order)
        else:
            token = generation = state = sequence = 0
        struct.pack_into('<8Q', raw, r.SNAPSHOTS_OFFSET + cfg * 64,
                         1, cfg, token, generation, state, 0, sequence, 0)
    offset = r.SNAPSHOTS_OFFSET + 2048
    struct.pack_into('<32Q16Q16Q', raw, offset, *slots, *inc, *inverse)
    offset += 512
    for i in range(64):
        if i < len(order):
            cfg = order[i]
            struct.pack_into('<8Q', raw, offset + i * 64,
                             1, i + 1, cfg, 1, 256 + slots[cfg] + 1, 2, 0, 0)
        else:
            struct.pack_into('<Q', raw, offset + i * 64, 1)
    return raw


def partial_trace():
    raw = bytearray((Path(__file__).parent / 'fixtures/boot-trace-normal.bin').read_bytes())
    count = struct.unpack_from('<Q', raw, 40)[0]
    # The actual prefix contains GUI14 READY and GUI15 STARTING, not final GUI readiness.
    end = next(i for i in range(count)
               if struct.unpack_from('<2Q', raw, 256 + i * 48 + 16) == (7, 15))
    raw[256 + end * 48:] = bytes(4096 - 256 - end * 48)
    struct.pack_into('<Q', raw, 40, end)
    struct.pack_into('<Q', raw, 48, 5)
    records = [struct.unpack_from('<6Q', raw, 256 + i * 48) for i in range(end)]
    for index, value in ((18, records[-1][1]), (19, end), (22, 0),
                         (24, sum(1 << e[3] for e in records if e[2] == 7)),
                         (25, sum(1 << e[3] for e in records if e[2] == 6)), (27, 0)):
        struct.pack_into('<Q', raw, index * 8, value)
    struct.pack_into('<Q', raw, 224, 0)
    struct.pack_into('<Q', raw, 224, (-sum(struct.unpack('<512Q', raw))) & r.NONE)
    return bytes(raw)


def initial_fixture():
    catalog = r.decode_catalog(catalog_bytes())
    report, _, _, _, _ = cpu_fixture()
    report[7] = 0xffffffff80300000
    domain = [1, 0, 0, 16, 15, 8, 0, 0, 8, report[8], 0, 0, 0, report[5], 65536]
    processes, threads = [[0] * 7 for _ in range(16)], [[0] * 8 for _ in range(64)]
    cpus, headers, metrics, contexts, registers, addresses = [], [], [], [], [], []
    for cpu in range(4):
        _, h, m, context, _ = cpu_fixture()
        address = r.ARENA + 0x100000 + cpu * 0x10000
        addresses.append(address)
        h[0] = address + 32768
        h[2], h[4], h[8], h[9], h[10], h[11] = address, report[8], report[7] + cpu * 256, report[5], cpu, report[7]
        h[14:22] = [address + 256, address + 320, address + 512, h[0] - 16384,
                    address + 65536, address + 98304, address + 131072, address + 4608]
        m[6], m[13], m[15], m[20] = address, h[14], h[16], h[0]
        context[:4] = [h[8], cpu, cpu, 4]
        owned = [4, 0, 0, 16, 0, 0, 0, 8, 8, 1, 2, 3, 4, 0, 5]
        reg = dict(GDT=h[14], GDT_limit=55, IDT=h[16], IDT_limit=4095, TR=24,
                   TR_base=h[15], CS=8, SS=16, GS_base=address, CR3=report[8], CR4=1 << 17)
        if cpu in (1, 2):
            cfg, slot = cpu + 13, cpu + 6
            token, root = 256 + slot + 1, 0x100000 + slot * 4096
            owned[:4] = [2, token, 1, slot]
            processes[slot] = [token, 1, root, 4, 5, 0, 0]
            threads[slot] = [2, 8, 15, cpu, 64, 64, 1, 4]
            reg.update(CS=0x33, SS=0x2b, GS_base=0, CR3=root | (slot + 1))
        cpus.append(owned)
        headers.append(h)
        metrics.append(m)
        contexts.append(context)
        registers.append(reg)
    manager = bytearray(5656)
    struct.pack_into('<3Q', manager, 0, 1, 18, 100)
    manager[24:4120] = catalog_bytes()[24:4120]
    for cfg in (14, 15):
        s = catalog['snapshots'][cfg]
        struct.pack_into('<6Q', manager, 4120 + cfg * 48, 1, s['process'], 1, 1, 200, 0)
    initial = [dict(version=1, configuration=i, process=0, generation=0, state=0,
                    status=0, sequence=0, argument=0) for i in range(32)]
    initial[5].update(process=262, generation=1, state=2)
    return dict(catalog=catalog, report=report, domain=domain, cpus=cpus, headers=headers,
                metrics=metrics, contexts=contexts, registers=registers, processes=processes,
                threads=threads, header_addresses=addresses, syscall_entry=metrics[0][11],
                init_initial=initial, init_manager_hex=manager.hex(),
                init_started=[1, 15, catalog['snapshots'][15]['process'], 1, 1, 0, 7, 0],
                trace_hex=partial_trace().hex(), stopped_before=True, stopped_after=True, stop_id=3)


def observer_fixture(state):
    """Current same-stop full acquisition, with hardware/memory boundaries mocked."""
    record = initial_fixture()
    g = object.__new__(r.InitialGuest)
    g.state, g.stop_id, g.stopped, g.chunks = Path(state), 3, True, []
    g.gui_sampling_started, g.catalog_initialized = True, True
    g.evidence = {'register_prefilter': dict(
        diagnostic_only=True, samples=0, ap_cpl3_counts=[0, 0, 0, 0],
        full_candidates=0, armed_at_stop_id=2)}
    g.qmp = mock.Mock()
    g.qmp.request.side_effect = lambda command, *args: (
        {'running': False} if command == 'query-status' else 'fresh hardware registers')
    g.catalog = mock.Mock(return_value=copy.deepcopy(record['catalog']))
    g.candidate_domain = mock.Mock(return_value={
        key: record[key] for key in ('report', 'domain', 'cpus')})
    g.symbols = {'user_smp_syscall_entry': record['syscall_entry']}

    def read(va, size, role):
        values = {'sixteen process ownership records': record['processes'],
                  'bounded queue thread array': record['threads']}[role]
        return struct.pack('<' + 'Q' * sum(map(len, values)), *(x for row in values for x in row))

    def readwords(va, count, role):
        if role == 'private Header pointers':
            return record['header_addresses']
        offset = 5632 if role == 'private CPU hardware Metrics' else 0
        cpu = record['header_addresses'].index(va - offset)
        return record['metrics' if offset else 'headers'][cpu]

    g.read, g.readwords = mock.Mock(side_effect=read), mock.Mock(side_effect=readwords)
    g.kernel = mock.Mock(side_effect=lambda va, size, role: struct.pack(
        '<32Q', *record['contexts'][(va - record['report'][7]) // 256]))
    g.refresh_processes, g.validate_private_pools = mock.Mock(), mock.Mock()
    g.verify_process = mock.Mock(side_effect=lambda slot, name: dict(
        pid=slot, image=name, root=record['processes'][slot][2], executable_bytes=32))
    initial_bytes = b''.join(struct.pack('<8Q', *s.values()) for s in record['init_initial'])
    g.init_global = mock.Mock(side_effect=lambda name, size, image: {
        'SNAPSHOTS': initial_bytes, 'MANAGER': bytes.fromhex(record['init_manager_hex']),
        'STARTED': struct.pack('<8Q', *record['init_started'])}[name])
    g.trace = mock.Mock(return_value=bytes.fromhex(record['trace_hex']))
    g.verify_code = mock.Mock(return_value=256)
    return g, record


class InitialDagTests(unittest.TestCase):
    def test_dense_cadence_is_deterministic_and_records_host_boundaries(self):
        expected = [.0002, .0005, .0013, .0021] * 3
        self.assertEqual(expected, [r.sampling_delay(True, True, i) for i in range(12)])
        self.assertEqual(.02, r.sampling_delay(False, False, 0))
        self.assertEqual(.005, r.sampling_delay(True, False, 0))
        for index in (-1, .5):
            with self.assertRaises(ValueError):
                r.sampling_delay(True, True, index)
        g = object.__new__(r.InitialGuest)
        g.sampling, g.stop_id = [], 9
        g.resume, g.pause = mock.Mock(return_value=(10, 10.02)), mock.Mock(return_value=10.05)
        with mock.patch.object(r.time, 'monotonic', return_value=10.021), \
             mock.patch.object(r.time, 'sleep') as sleep:
            g.sample_after(.0002)
        sleep.assert_called_once_with(.0002)
        sample = g.sampling[0]
        self.assertEqual(.0002, sample['requested_sleep_seconds'])
        self.assertEqual(10.021, sample['stop_request_monotonic'])
        self.assertEqual(10.05, sample['stopped_monotonic'])
        self.assertEqual(9, sample['stop_id'])
        self.assertTrue(sample['diagnostic_only'])
        self.assertFalse(sample['guest_runtime_measured'])
        self.assertAlmostEqual(.02, sample['cont_wait_seconds'])
        self.assertAlmostEqual(.001, sample['cont_reply_to_stop_request_seconds'])
        self.assertAlmostEqual(.029, sample['stop_confirmation_wait_seconds'])
        self.assertAlmostEqual(.05, sample['possibly_running_seconds_upper_bound'])
        self.assertNotIn('passed', sample)

    def test_confirmed_stopped_collection_is_separate_from_possible_runtime(self):
        g = object.__new__(r.InitialGuest)
        g.qmp = mock.Mock()
        g.qmp.request.return_value = {'running': False}
        g.stop_id, g.stopped, g.observations, g.confirmed_stop = 0, False, [], None
        with mock.patch.object(r.time, 'monotonic', side_effect=[10, 12, 12.5]):
            self.assertEqual(10, g.pause())
            self.assertEqual((12, 12.5), g.resume())
        observation = g.observations[0]
        self.assertEqual(1, observation['stop_id'])
        self.assertEqual(2, observation['confirmed_stopped_collection_seconds'])
        self.assertEqual(12, observation['collection_end_monotonic'])
        self.assertTrue(observation['diagnostic_only'])
        g.finish_observation(20)
        self.assertEqual(2, observation['confirmed_stopped_collection_seconds'])
        self.assertFalse(g.stopped)

    def test_observer_accounting_failure_cannot_prevent_guest_cleanup(self):
        g = object.__new__(r.InitialGuest)
        g.qmp_path = None
        g.finish_observation = mock.Mock(side_effect=ValueError('diagnostic accounting failed'))
        with mock.patch.object(r.timing.KvmGuest, 'close') as close:
            with self.assertRaisesRegex(ValueError, 'accounting failed'):
                g.close()
        close.assert_called_once_with(g)

    def test_candidate_domain_validates_identity_before_cpu_read(self):
        g = object.__new__(r.InitialGuest)
        g.stopped = True
        pointer, domain_va, contexts = r.ARENA + 4096, r.ARENA + 8192, 0xffffffff80300000
        report = [1, 0, 1, 4, 15, domain_va, pointer + 256, contexts, 0x400000, 1000000000]
        domain = [1, 0, 1, 0, 15, 8, 8, 15, 7, 0x400000,
                  domain_va + 128, domain_va + 128 + 12992,
                  domain_va + 128 + 12992 + 1920, domain_va, 65536]
        g.kval = mock.Mock(return_value=pointer)
        g.ksym = mock.Mock(return_value=contexts)
        g.evidence = {'trusted_kernel_page_table_pool': {'root_physical': 0x400000}}
        cpus = [4, 0, 0, 16, 0, 0, 0, 8, 7, 0, 0, 0, 0, 0, 0] * 4

        def bounded_read(va, size, role):
            if va == pointer:
                return struct.pack('<10Q', *report)
            if va == domain_va:
                return struct.pack('<15Q', *domain)
            self.assertEqual((domain[11], 480), (va, size))
            return struct.pack('<60Q', *cpus)
        g.read = mock.Mock(side_effect=bounded_read)
        value = g.candidate_domain()
        # Active/incomplete barrier is diagnostic data, never silently a PASS.
        self.assertEqual(8, value['domain'][6])
        self.assertEqual(7, value['cpus'][3][8])
        original_report, original_domain = report[:], domain[:]
        for target, field, bad in ((report, 5, 0xffffffff80300000),
                                   (report, 7, contexts + 256), (report, 8, 0xdead000),
                                   (domain, 11, r.ARENA + 0xdead000),
                                   (domain, 13, domain_va + 4096), (domain, 14, 131072)):
            with self.subTest(field=field, bad=bad):
                target[field] = bad
                g.read.reset_mock()
                with self.assertRaises(ValueError):
                    g.candidate_domain()
                self.assertFalse(any(call.args[1] == 480 for call in g.read.call_args_list))
                report[:], domain[:] = original_report, original_domain
        # Exact layout alone is insufficient: real read() must reject an
        # otherwise valid CPU span outside the allocated arena before I/O.
        g._arena_limit = domain[11] + 120
        g.physical = mock.Mock()
        g.read = mock.Mock(side_effect=lambda va, size, role:
                           r.InitialGuest.read(g, va, size, role) if size == 480
                           else bounded_read(va, size, role))
        with self.assertRaisesRegex(ValueError, 'escaped allocated'):
            g.candidate_domain()
        g.physical.assert_not_called()
        g.stopped = False
        g.read.reset_mock()
        with self.assertRaisesRegex(ValueError, 'stopped'):
            g.candidate_domain()
        g.read.assert_not_called()

    def test_latched_low_cpl3_budget_is_four_register_reads_and_zero_io(self):
        for users in (0, 1):
            with self.subTest(users=users), tempfile.TemporaryDirectory() as temp:
                g, record = observer_fixture(temp)
                registers = copy.deepcopy(record['registers'])
                registers[2]['CS'] = 8
                registers[1]['CS'] = 0x33 if users else 8
                for method in ('catalog_pointer', 'read', 'readwords', 'physical',
                               'kernel', 'candidate_domain', 'capture_initial'):
                    setattr(g, method, mock.Mock(side_effect=AssertionError('forbidden low-CPL3 I/O')))
                with mock.patch.object(r.oracle, 'registers', side_effect=registers), \
                     mock.patch.object(r, 'write') as write, \
                     mock.patch.object(Path, 'write_text') as write_text, \
                     mock.patch.object(r, 'validate_initial') as validate:
                    self.assertIsNone(g.observe_initial())
                self.assertEqual([
                    mock.call('human-monitor-command', {'command-line': 'info registers', 'cpu-index': i})
                    for i in range(4)], g.qmp.request.call_args_list)
                g.catalog.assert_not_called()
                for method in ('catalog_pointer', 'read', 'readwords', 'physical',
                               'kernel', 'candidate_domain', 'capture_initial'):
                    getattr(g, method).assert_not_called()
                write.assert_not_called()
                write_text.assert_not_called()
                validate.assert_not_called()
                self.assertEqual([], list(Path(temp).iterdir()))
                stats = g.evidence['register_prefilter']
                self.assertEqual(1, stats['samples'])
                self.assertEqual(1, stats['ap_cpl3_counts'][users])
                self.assertEqual(0, stats['full_candidates'])
                self.assertNotIn('proof', stats)

    def test_gui_phase_latches_only_flow_and_does_not_repeat_memory_prefilter(self):
        with tempfile.TemporaryDirectory() as temp:
            g, _ = observer_fixture(temp)
            g.gui_sampling_started = g.catalog_initialized = False
            g.catalog_pointer = mock.Mock(return_value=r.ARENA)
            g.readwords = mock.Mock(return_value=[1, 18, 7])
            g.read = mock.Mock(return_value=bytes(catalog_bytes()[r.GUI_OFFSET:r.GUI_OFFSET + 256]))
            with mock.patch.object(r.oracle, 'registers', return_value={'CS': 8}):
                self.assertIsNone(g.observe_initial())
                self.assertTrue(g.gui_sampling_started)
                g.stop_id += 1
                self.assertIsNone(g.observe_initial())
            g.catalog_pointer.assert_called_once()
            g.readwords.assert_called_once()
            g.read.assert_called_once()
            g.catalog.assert_not_called()
            g.candidate_domain.assert_not_called()
            self.assertEqual(8, g.qmp.request.call_count)
            self.assertEqual(3, g.evidence['register_prefilter']['armed_at_stop_id'])

    def test_eligible_prefilter_reacquires_full_same_stop_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            g, record = observer_fixture(temp)
            with mock.patch.object(r.oracle, 'registers', side_effect=record['registers'] * 2):
                captured = g.observe_initial()
            self.assertEqual([14, 15], captured['proof']['ap_gui_configurations'])
            self.assertEqual(3, captured['stop_id'])
            self.assertTrue(captured['stopped_before'] and captured['stopped_after'])
            self.assertEqual(8, sum(c.args[0] == 'human-monitor-command'
                                    for c in g.qmp.request.call_args_list))
            g.catalog.assert_called_once_with()
            g.candidate_domain.assert_called_once_with()
            g.refresh_processes.assert_called_once()
            g.validate_private_pools.assert_called_once()
            g.verify_code.assert_called_once()
            self.assertEqual([mock.call(5, 'init'), mock.call(3, 'compositor'),
                              mock.call(7, 'terminal'), mock.call(8, 'files')],
                             g.verify_process.call_args_list)
            diagnostic = json.loads((Path(temp) / 'candidate-3.json').read_text())
            self.assertTrue(diagnostic['complete'] and diagnostic['diagnostic_only'])
            self.assertNotIn('proof', diagnostic)

    def test_stale_latch_and_old_catalog_cannot_supply_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            g, record = observer_fixture(temp)
            # The old prefilter would have accepted this early Catalog, but
            # current memory says all GUI clients are READY.
            g.old_catalog = record['catalog']
            g.catalog.return_value = r.decode_catalog(catalog_bytes(True))
            with mock.patch.object(r.oracle, 'registers', side_effect=record['registers'] * 2):
                with self.assertRaisesRegex(ValueError, 'STARTING'):
                    g.observe_initial()
            g.catalog.assert_called_once_with()
            g.verify_code.assert_not_called()
            # There is intentionally no API for supplying an old Catalog.
            with self.assertRaises(TypeError):
                g.capture_initial(record['catalog'])

    def test_old_or_cross_stop_registers_cannot_supply_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            g, record = observer_fixture(temp)
            fresh = copy.deepcopy(record['registers'])
            fresh[2]['CS'] = 8
            with mock.patch.object(r.oracle, 'registers', side_effect=record['registers'] + fresh):
                with self.assertRaisesRegex(ValueError, 'fewer than two APs'):
                    g.observe_initial()
            g.catalog.assert_not_called()
            g.candidate_domain.assert_not_called()
            self.assertEqual([], list(Path(temp).iterdir()))
            g.qmp.reset_mock()

            def crossed(text):
                g.stop_id += 1
                return {'CS': 0x33}
            with mock.patch.object(r.oracle, 'registers', side_effect=crossed):
                with self.assertRaisesRegex(ValueError, 'crossed a stop'):
                    g.observe_initial()
            g.catalog.assert_not_called()

    def test_full_proof_cannot_cross_stop_during_code_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            g, record = observer_fixture(temp)

            def moved():
                g.stop_id += 1
                return 256
            g.verify_code.side_effect = moved
            with mock.patch.object(r.oracle, 'registers', side_effect=record['registers'] * 2):
                with self.assertRaisesRegex(ValueError, 'initial stop'):
                    g.observe_initial()

    def test_current_catalog_and_cheap_window(self):
        raw = catalog_bytes()
        self.assertTrue(r.gui_window(raw[r.GUI_OFFSET:r.GUI_OFFSET + 256]))
        c = r.decode_catalog(raw)
        self.assertEqual(9, c['configs'][14]['flags'])
        r.life.check_boot_dag(c)
        late = catalog_bytes(True)
        self.assertFalse(r.gui_window(late[r.GUI_OFFSET:r.GUI_OFFSET + 256]))
        for offset, value in ((24 + 14 * 128 + 40, 8),
                              (r.SNAPSHOTS_OFFSET + 14 * 64 + 16, 999),
                              (16, 65)):
            bad = bytearray(raw)
            struct.pack_into('<Q', bad, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                r.decode_catalog(bad)

    def test_positive_initial_fixture_and_independent_mutations(self):
        record = initial_fixture()
        proof = r.validate_initial(record)
        self.assertEqual([14, 15], proof['ap_gui_configurations'])
        mutations = [
            lambda x: x['domain'].__setitem__(8, 0),
            lambda x: x['domain'].__setitem__(6, 8),
            lambda x: x['cpus'][3].__setitem__(8, 7),
            lambda x: x['registers'][1].__setitem__('CS', 8),
            lambda x: x['registers'][1].__setitem__('CR3', 0xdead000),
            lambda x: x['threads'][7].__setitem__(3, 2),
            lambda x: x['catalog']['snapshots'][15].__setitem__('state', 2),
            lambda x: x['catalog']['snapshots'][14].__setitem__('generation', 2),
            lambda x: x['catalog']['configurations'].__setitem__(7, 9),
            lambda x: x['catalog']['snapshots'][3].__setitem__('generation', 2),
            lambda x: x['init_initial'][14].__setitem__('generation', 1),
            lambda x: x['init_started'].__setitem__(3, 2),
            lambda x: x.__setitem__('stopped_after', False),
            lambda x: x['headers'][2].__setitem__(26, 1),
            lambda x: x['contexts'][2].__setitem__(2, 1),
        ]
        for i, mutate in enumerate(mutations):
            bad = copy.deepcopy(record)
            mutate(bad)
            with self.subTest(mutation=i), self.assertRaises(ValueError):
                r.validate_initial(bad)
        for field, value in ((0, 2), (1, 999), (2, 0), (3, 0), (4, 0), (5, 1)):
            bad = copy.deepcopy(record)
            manager = bytearray.fromhex(bad['init_manager_hex'])
            struct.pack_into('<Q', manager, 4120 + 14 * 48 + field * 8, value)
            bad['init_manager_hex'] = manager.hex()
            with self.subTest(manager_field=field), self.assertRaises(ValueError):
                r.validate_initial(bad)

    def test_same_boot_final_readiness_not_restart_or_late_only(self):
        initial = initial_fixture()
        raw = (Path(__file__).parent / 'fixtures/boot-trace-normal.bin').read_bytes()
        final = dict(catalog=r.decode_catalog(catalog_bytes(True)), trace_hex=raw.hex())
        decoded = decoded_fixture()
        self.assertTrue(r.validate_final(initial, final, decoded))
        for kind in ('boot', 'token', 'generation', 'ready', 'prefix', 'late'):
            a, b, c = copy.deepcopy(initial), copy.deepcopy(final), copy.deepcopy(decoded)
            if kind == 'boot':
                c['header']['boot_id'] += 1
            elif kind == 'token':
                b['catalog']['snapshots'][14]['process'] += 256
            elif kind == 'generation':
                b['catalog']['snapshots'][17]['generation'] = 2
            elif kind == 'ready':
                b['catalog']['snapshots'][16]['state'] = 1
            elif kind == 'prefix':
                changed = bytearray(raw)
                changed[300] ^= 1
                b['trace_hex'] = changed.hex()
            else:
                a['trace_hex'] = raw.hex()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                r.validate_final(a, b, c)

    def test_initial_trace_header_summary_and_starting_state_negative_controls(self):
        record = initial_fixture()
        r.initial_trace(bytes.fromhex(record['trace_hex']))
        for field in (18, 19, 24, 25, 20, 21, 22, 29):
            bad = bytearray.fromhex(record['trace_hex'])
            value = struct.unpack_from('<Q', bad, field * 8)[0]
            struct.pack_into('<Q', bad, field * 8, value + 1)
            struct.pack_into('<Q', bad, 224, 0)
            struct.pack_into('<Q', bad, 224, (-sum(struct.unpack('<512Q', bad))) & r.NONE)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'summary'):
                r.initial_trace(bad)
        bad = copy.deepcopy(record)
        # A STARTING Catalog owner cannot already have a READY in its same-stop trace.
        bad['catalog']['snapshots'][14]['state'] = 1
        with self.assertRaisesRegex(ValueError, 'STARTING/READY'):
            r.validate_initial(bad)

    def test_gui_executable_root_and_completion_failure_negative_controls(self):
        record = initial_fixture()
        image = dict(pid=7, image='terminal', root=record['processes'][7][2], executable_bytes=32)
        r.bind_gui_image(image, 14, record['catalog'], record['processes'])
        for field, value in (('root', 0xdead000), ('pid', 8), ('image', 'files'), ('executable_bytes', 0)):
            bad = dict(image)
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                r.bind_gui_image(bad, 14, record['catalog'], record['processes'])
        raw = b''.join(r.MARKERS)
        r.check_completion(raw)
        for tail in (b'PANIC', b'DONGOS_P1_KERNEL_FAIL', b'DONGOS_INIT_FAILURE x', r.MARKERS[0]):
            with self.subTest(tail=tail), self.assertRaises(ValueError):
                r.check_completion(raw + tail)

    def test_bundle_auxiliary_cannot_be_unbound(self):
        with tempfile.TemporaryDirectory() as temp:
            esp = Path(temp) / 'esp'
            esp.mkdir()
            names = ('init', 'compositor', 'terminal', 'files', 'editor', 'settings')
            entries = []
            for name in names:
                path = esp.parent / 'services' / name / 'program.elf'
                path.parent.mkdir(parents=True)
                path.write_bytes(('fixture-' + name).encode())
                entries.append((name, 1, path.read_bytes()))
            (esp / 'SERVICES.BIN').write_bytes(r.service_bundle.pack(entries))
            (esp.parent / 'dong_layout.json').write_text('{}')
            self.assertEqual(7, len(r.bind_auxiliary(esp)))
            (esp.parent / 'services/init/program.elf').write_bytes(b'detached')
            with self.assertRaisesRegex(ValueError, 'differs from bound bundle'):
                r.bind_auxiliary(esp)

    def test_tcg_only_command_keeps_four_cpus_and_no_guest_mutation(self):
        base = ['qemu', '-accel', 'tcg', '-smp', '4', '-serial', 'old',
                '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
        with mock.patch.object(r.clock.builder, 'qemu_command', return_value=base):
            command = r.command_for(Path('/esp'), Path('/state'), Path('/disk'), 123)
        self.assertIn('tcg', command)
        self.assertNotIn('host,migratable=off', command)
        self.assertIn('-S', command)
        self.assertEqual('unix:/state/qmp.sock,server=on,wait=off',
                         command[command.index('-qmp') + 1])
        self.assertNotIn('isa-debug-exit,iobase=0xf4,iosize=0x04', command)
        with mock.patch.object(r.clock.builder, 'qemu_command', return_value=['qemu', '-accel', 'kvm', '-smp', '4']):
            with self.assertRaisesRegex(ValueError, 'TCG'):
                r.command_for(Path('/esp'), Path('/state'), Path('/disk'), 1)

    def test_unix_qmp_owned_path_length_and_failed_connect_cleanup(self):
        # 1 leading slash + 97 bytes of parent + slash + eight-byte qmp.sock.
        self.assertEqual(107, len(r.os.fsencode(r.qmp_socket_path('/' + 'a' * 97))))
        for parent in ('/' + 'a' * 98, '/' + 'é' * 49):
            with self.subTest(parent=parent), self.assertRaisesRegex(ValueError, '107 bytes'):
                r.qmp_socket_path(parent)
        with mock.patch.object(r.clock.builder, 'qemu_command') as builder:
            with self.assertRaises(ValueError):
                r.command_for(Path('/esp'), Path('/' + 'a' * 98), Path('/disk'), 123)
        builder.assert_not_called()
        process, connection = mock.Mock(), mock.Mock()
        process.poll.return_value = 1
        connection.connect.side_effect = ConnectionRefusedError('not listening')
        with mock.patch.object(r.socket, 'socket', return_value=connection) as opened:
            with self.assertRaises(ConnectionRefusedError):
                r.UnixQMP(Path('/owned/qmp.sock'), process)
        opened.assert_called_once_with(r.socket.AF_UNIX, r.socket.SOCK_STREAM)
        connection.close.assert_called_once()
        with self.assertRaisesRegex(ValueError, 'owned state path'):
            r.UnixQMP(Path('/owned/foreign.sock'), process)

    def test_unix_qmp_real_host_handshake_events_and_fail_closed(self):
        # Host socket protocol only. This never starts QEMU or any guest code.
        for case in ('valid', 'greeting', 'capabilities'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                path = r.qmp_socket_path(temp)
                received, failures = [], []
                server = r.socket.socket(r.socket.AF_UNIX, r.socket.SOCK_STREAM)
                server.bind(str(path))
                server.listen(1)
                server.settimeout(2)

                def serve():
                    try:
                        with server.accept()[0] as peer:
                            peer.settimeout(2)
                            with peer.makefile('rwb') as stream:
                                stream.write(json.dumps({'QMP': {}} if case != 'greeting' else {}).encode() + b'\n')
                                stream.flush()
                                if case == 'greeting':
                                    received.append(stream.readline())
                                    return
                                received.append(json.loads(stream.readline()))
                                stream.write(json.dumps({'error': {'desc': 'capability refused'}}
                                                        if case == 'capabilities' else {'return': {}}).encode() + b'\n')
                                stream.flush()
                                if case == 'capabilities':
                                    received.append(stream.readline())
                                    return
                                received.append(json.loads(stream.readline()))
                                stream.write(b'{"event":"STOP"}\n{"return":{"running":false}}\n')
                                stream.flush()
                                received.append(stream.readline())
                    except Exception as exc:
                        failures.append(exc)

                worker = threading.Thread(target=serve, daemon=True)
                worker.start()
                process = mock.Mock()
                process.poll.return_value = None
                try:
                    if case == 'valid':
                        qmp = r.UnixQMP(path, process)
                        self.assertEqual({'running': False}, qmp.request('query-status'))
                        qmp.close()
                        self.assertEqual(-1, qmp.socket.fileno())
                        self.assertIs(r.UnixQMP.request, r.clock.acpi.QMP.request)
                    else:
                        with self.assertRaises(ValueError if case == 'greeting' else RuntimeError):
                            r.UnixQMP(path, process)
                    worker.join(timeout=3)
                    self.assertFalse(worker.is_alive())
                    self.assertFalse(failures)
                    self.assertEqual(b'', received[-1])
                    if case != 'greeting':
                        self.assertEqual({'execute': 'qmp_capabilities'}, received[0])
                    if case == 'valid':
                        self.assertEqual({'execute': 'query-status'}, received[1])
                finally:
                    server.close()

    def test_unix_qmp_protocol_and_cleanup_without_host_socket_permissions(self):
        for case, replies in (
                ('valid', [b'{"QMP":{}}\n', b'{"return":{}}\n',
                           b'{"event":"STOP"}\n', b'{"return":{"running":false}}\n']),
                ('greeting', [b'{}\n']),
                ('capabilities', [b'{"QMP":{}}\n', b'{"error":{"desc":"refused"}}\n'])):
            with self.subTest(case=case):
                connection, stream, process = mock.Mock(), mock.Mock(), mock.Mock()
                connection.makefile.return_value = stream
                stream.readline.side_effect = replies
                with mock.patch.object(r.socket, 'socket', return_value=connection):
                    if case == 'valid':
                        qmp = r.UnixQMP(Path('/owned/qmp.sock'), process)
                        self.assertEqual({'running': False}, qmp.request('query-status'))
                        qmp.close()
                        self.assertEqual([{'execute': 'qmp_capabilities'}, {'execute': 'query-status'}],
                                         [json.loads(c.args[0]) for c in stream.write.call_args_list])
                    else:
                        with self.assertRaises(ValueError if case == 'greeting' else RuntimeError):
                            r.UnixQMP(Path('/owned/qmp.sock'), process)
                connection.connect.assert_called_once_with('/owned/qmp.sock')
                stream.close.assert_called_once()
                connection.close.assert_called_once()

    def test_endpoint_cleanup_never_unlinks_preexisting_or_replacement(self):
        # No real socket needed: reject an existing endpoint before Popen, then
        # prove cleanup never deletes it or a later same-path replacement.
        with tempfile.TemporaryDirectory() as temp:
            g = object.__new__(r.InitialGuest)
            g.state, g.chunks, g.evidence = Path(temp), [], {}
            g.qmp_path = None
            g.qmp = g.process = g.uart = g.reader = g.stderr = None
            with mock.patch.object(r.clock, 'create'), \
                 mock.patch.object(r.storage, 'free_port', return_value=123), \
                 mock.patch.object(Path, 'exists', return_value=True), \
                 mock.patch.object(Path, 'unlink') as unlink, \
                 mock.patch.object(r.subprocess, 'Popen') as popen:
                with self.assertRaisesRegex(ValueError, 'already exists'):
                    g.start()
                g.close()
                popen.assert_not_called()
                unlink.assert_not_called()
                self.assertTrue(g.evidence['qmp_endpoint_path_present'])
                self.assertEqual('not_removed_by_observer', g.evidence['qmp_endpoint_cleanup'])
            # A socket replaced by another socket, regular file, or symlink has
            # the same no-delete policy, independent of process completion.
            g.process = mock.Mock()
            for running in (True, False):
                with self.subTest(running=running), \
                     mock.patch.object(r.timing.KvmGuest, 'close') as close, \
                     mock.patch.object(Path, 'exists', return_value=True), \
                     mock.patch.object(Path, 'unlink') as unlink:
                    g.process.poll.return_value = None if running else 0
                    g.close()
                    close.assert_called_once_with(g)
                    unlink.assert_not_called()

    def test_owned_unix_socket_cleanup_refuses_replacement(self):
        for replacement in (False, True):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as temp:
                g = object.__new__(r.InitialGuest)
                g.state, g.chunks, g.evidence = Path(temp), [], {}
                g.qmp_path = r.qmp_socket_path(g.state)
                g.qmp = g.process = g.uart = g.reader = g.stderr = None
                if replacement:
                    g.qmp_path.write_text('not our socket')
                    g.close()
                    self.assertEqual('not our socket', g.qmp_path.read_text())
                else:
                    with r.socket.socket(r.socket.AF_UNIX, r.socket.SOCK_STREAM) as server:
                        server.bind(str(g.qmp_path))
                        g.close()
                        self.assertTrue(g.qmp_path.exists())
                self.assertTrue(g.evidence['qmp_endpoint_path_present'])
                self.assertEqual('not_removed_by_observer', g.evidence['qmp_endpoint_cleanup'])

    def test_linked_and_arena_reads_do_not_share_linear_translation(self):
        g = object.__new__(r.InitialGuest)
        g.stopped = True
        g._arena_limit = r.ARENA + 8192
        g._arena_physical = 0x900000
        g._kernel_pool = (0x100000, 128)
        g.evidence = {'trusted_kernel_page_table_pool': {'root_physical': 0x100000}}
        g.tables = {}
        pages = {}
        va = r.ARENA + 32
        for i, shift in enumerate((39, 30, 21, 12)):
            table = bytearray(4096)
            entry = ((0x100000 + (i + 1) * 4096) | 3) if i < 3 else (0x900000 | 3 | 1 << 63)
            struct.pack_into('<Q', table, ((va >> shift) & 511) * 8, entry)
            pages[0x100000 + i * 4096] = bytes(table)
        g.physical = mock.Mock(side_effect=lambda pa, size, role: pages[pa] if size == 4096 else b'x' * size)
        self.assertEqual(b'x' * 8, g.read(va, 8, 'bounded test'))
        self.assertEqual(0x900020, g.physical.call_args.args[0])
        with self.assertRaisesRegex(ValueError, 'escaped allocated'):
            g.read(r.storage.KERNEL, 8, 'wrong address class')
        g.stopped = False
        with self.assertRaisesRegex(ValueError, 'size/state'):
            g.read(va, 8, 'running')

    def test_owned_cleanup_kills_after_failed_qmp_quit(self):
        with tempfile.TemporaryDirectory() as temp:
            g = object.__new__(r.InitialGuest)
            g.state, g.chunks, g.evidence = Path(temp), [], {}
            g.qmp = mock.Mock()
            g.qmp.request.side_effect = RuntimeError('QMP unavailable')
            g.uart = g.reader = g.stderr = None
            g.process = mock.Mock()
            g.process.wait.side_effect = [r.subprocess.TimeoutExpired('qemu', 10), 0]
            g.process.poll.return_value = 0
            g.close()
            g.process.kill.assert_called_once()
            self.assertTrue((g.state / 'physical-manifest.json').is_file())

    def test_private_pool_and_leaf_rejected_before_out_of_range_read(self):
        g = object.__new__(r.InitialGuest)
        g._arena_physical, g._arena_limit = 0x100000, r.ARENA + 0x200000
        g.roots, g.pool_limits = [0] * 16, [32] * 16
        g.roots[5] = 0x100000
        g.tables = {}
        va, raw_pages = 0x12345000, {}
        for i, shift in enumerate((39, 30, 21, 12)):
            page = bytearray(4096)
            entry = (0x100000 + (i + 1) * 4096 | 7) if i < 3 else (0x200000 | 7)
            struct.pack_into('<Q', page, ((va >> shift) & 511) * 8, entry)
            raw_pages[0x100000 + i * 4096] = bytes(page)
        g.physical = mock.Mock(side_effect=lambda pa, n, role: raw_pages[pa])
        self.assertEqual(0x200007, g.pte(g.roots[5], va))
        leaf = bytearray(g.tables[0x103000])
        struct.pack_into('<Q', leaf, ((va >> 12) & 511) * 8, 0x900007)
        g.tables[0x103000] = bytes(leaf)
        with self.assertRaisesRegex(ValueError, 'physical arena'):
            g.pte(g.roots[5], va)
        before = g.physical.call_count
        g.roots[5] = 0x900000
        with self.assertRaisesRegex(ValueError, 'physical arena'):
            g.pte(g.roots[5], va)
        self.assertEqual(before, g.physical.call_count)

    def test_run_retains_failure_and_never_claims_guest_pass_from_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            guest = mock.Mock()
            guest.evidence = {'actual_qemu_executed': True}
            guest.chunks = [{'stop_id': 4, 'physical': 4096, 'bytes': 8, 'role': 'bounded fixture'}]
            guest.sampling = [{'stop_id': 4, 'requested_sleep_seconds': .0002, 'diagnostic_only': True}]
            guest.observations = [{'stop_id': 4, 'confirmed_stopped_collection_seconds': 1,
                                   'diagnostic_only': True}]
            guest.candidate_rejections = [{'stop_id': 4, 'reason': 'current candidate rejected'}]
            guest.process.poll.return_value = 0
            guest.start.side_effect = ValueError('initial AP/STARTING window missed')
            guest.close.side_effect = RuntimeError('cleanup diagnostic failed')
            with mock.patch.object(r.timing, 'verify_build', return_value={'esp': '/esp'}), \
                 mock.patch.object(r, 'bind_auxiliary', return_value={'bound': 'hash'}), \
                 mock.patch.object(r.timing, 'runner_fingerprints', return_value={'observer': 'hash'}), \
                 mock.patch.object(r, 'InitialGuest', return_value=guest):
                result = r.run(Path('/esp'), Path(temp) / 'run', 5)
            guest.capture_failure.assert_called_once()
            guest.close.assert_called_once()
            self.assertFalse(result['passed'])
            self.assertFalse(result['init_cross_ap_proven'])
            self.assertFalse(result['kvm_timing_proven'])
            self.assertEqual(0, result['actual_kvm_boots'])
            self.assertIn('window missed', result['error'])
            self.assertTrue((Path(temp) / 'run/result.json').is_file())
            self.assertIn('cleanup diagnostic failed', result['cleanup_error'])
            self.assertEqual(guest.chunks, json.loads((Path(temp) / 'run/physical-manifest.json').read_text()))
            self.assertEqual(guest.sampling, json.loads((Path(temp) / 'run/sampling.json').read_text()))
            self.assertEqual(guest.observations, json.loads(
                (Path(temp) / 'run/observation-intervals.json').read_text()))
            self.assertEqual(guest.candidate_rejections, json.loads(
                (Path(temp) / 'run/candidate-rejections.json').read_text()))

    def test_actual_source_layouts_match_narrow_observer_contract(self):
        for source, expected in (
                ('kernel/sched/user_domain.dg', {'sched.user_domain.Domain': 120,
                                                 'sched.user_domain.Cpu': 120,
                                                 'sched.user_domain.Process': 56,
                                                 'sched.multicore.Engine': 12960}),
                ('services/init/main.dg', {'init.policy.Manager': 5656,
                                          'init.policy.Node': 48,
                                          'lib.process_abi.Snapshot': 64})):
            compilation = r.compile_file(r.ROOT / source,
                roots=[r.ROOT / 'kernel', r.ROOT / 'services', r.ROOT / 'lang/std'], mode='release')
            sizes = {t['full_name']: t['size'] for t in compilation.layout_manifest['types']}
            for name, size in expected.items():
                with self.subTest(type=name):
                    self.assertEqual(size, sizes[name])


if __name__ == '__main__':
    unittest.main()
