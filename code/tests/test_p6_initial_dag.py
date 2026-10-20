"""Host-only initial-DAG controls. No QEMU, tool installation, or guest writes."""
import copy
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
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


class InitialDagTests(unittest.TestCase):
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
            command = r.command_for(Path('/esp'), Path('/state'), Path('/disk'), 123, 456)
        self.assertIn('tcg', command)
        self.assertNotIn('host,migratable=off', command)
        self.assertIn('-S', command)
        self.assertNotIn('isa-debug-exit,iobase=0xf4,iosize=0x04', command)
        with mock.patch.object(r.clock.builder, 'qemu_command', return_value=['qemu', '-accel', 'kvm', '-smp', '4']):
            with self.assertRaisesRegex(ValueError, 'TCG'):
                r.command_for(Path('/esp'), Path('/state'), Path('/disk'), 1, 2)

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
            guest.process.poll.return_value = 0
            guest.start.side_effect = ValueError('initial AP/STARTING window missed')
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
