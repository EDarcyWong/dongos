"""No-guest checks for the NVMe command transform and raw FLUSH oracle."""
import struct
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.run_nvme_qemu import (NVME_DEVICE, QUEUE_FIELDS, NvmeGuest, nvme_command,
                                 validate_flush, verify_no_user_dma_alias)


class CommandTests(unittest.TestCase):
    @staticmethod
    def command():
        return ['qemu', '-machine', 'q35', '-drive', 'format=raw,file=fat:rw:D:/esp',
                '-drive', 'if=none,id=data,format=raw,cache=writeback,file=D:/data.img',
                '-device', 'virtio-blk-pci,drive=data,disable-legacy=on',
                '-device', 'virtio-tablet-pci']

    def test_preserves_sata_efi_and_replaces_only_data_device(self):
        command = self.command()
        before = list(command)
        changed = nvme_command(command)
        self.assertEqual(command, before)
        differences = [(a, b) for a, b in zip(before, changed) if a != b]
        self.assertEqual(differences, [('virtio-blk-pci,drive=data,disable-legacy=on', NVME_DEVICE)])
        self.assertEqual(len(before), len(changed))
        self.assertIn('format=raw,file=fat:rw:D:/esp', changed)

    def test_missing_or_ambiguous_inputs_rejected(self):
        command = self.command()
        invalid = [[], command[0:5], command + ['-drive', command[4]],
                   command + ['-drive', command[6]], command + ['-device', command[8]],
                   command + ['-device', 'nvme,drive=other,serial=bad'],
                   command + ['-device', 'nvme-ns,drive=other'],
                   command + ['-drive', 'if=none,id=bootesp,format=raw,file=x']]
        for value in invalid:
            with self.subTest(command=value), self.assertRaises(ValueError):
                nvme_command(value)

    def test_second_transform_rejected(self):
        with self.assertRaises(ValueError):
            nvme_command(nvme_command(self.command()))


class CompletionTests(unittest.TestCase):
    @staticmethod
    def fixture(cid):
        state = bytearray(656)
        queue = dict.fromkeys(QUEUE_FIELDS, 0)
        queue.update(ready=1, held=1, epoch=1, qid=1, depth=2,
                     lease_physical=0x200000, lease_bytes=131072,
                     sq_tail=cid % 2, cq_head=cid % 2, phase=1 ^ ((cid // 2) & 1),
                     next_cid=cid, generation=cid, last_ms=25)
        struct.pack_into('<21Q', state, 408, *(queue[name] for name in QUEUE_FIELDS))
        struct.pack_into('<7Q', state, 576, 0, 1, 1, 25, 11, 0, 1)
        struct.pack_into('<Q', state, 648, 5)
        sqe = bytearray(64)
        struct.pack_into('<HI', sqe, 2, cid, 1)
        phase = queue['phase'] ^ (1 if queue['cq_head'] == 0 else 0)
        cqe = struct.pack('<IIHHHH', 0, 0, queue['sq_tail'], 1, cid, phase)
        state[632:648] = cqe
        return state, sqe, cqe

    def test_phase_wraps_and_last_issued_cid(self):
        for cid in (1, 2, 3, 4, 17, 18, 65533, 65534):
            with self.subTest(cid=cid):
                result = validate_flush(*self.fixture(cid))
                self.assertEqual(result['cid'], cid)
                self.assertEqual(result['consumed_phase'], 1 ^ (((cid - 1) // 2) & 1))
                self.assertFalse(result['hardware_transferred_byte_count_available'])

    def test_every_sqe_byte_and_cqe_byte_is_checked(self):
        for field, length in ((1, 64), (2, 16)):
            for offset in range(length):
                with self.subTest(field=field, offset=offset):
                    values = list(self.fixture(18))
                    changed = bytearray(values[field])
                    changed[offset] ^= 1
                    values[field] = changed
                    with self.assertRaises(ValueError):
                        validate_flush(*values)

    def test_stale_cid_error_status_wrong_phase_and_reserved_words_rejected(self):
        for offset, value in ((0, 1), (4, 1), (8, 1), (10, 0), (12, 17), (14, 2), (14, 0x8001)):
            with self.subTest(offset=offset, value=value):
                state, sqe, cqe = self.fixture(18)
                changed = bytearray(cqe)
                struct.pack_into('<H', changed, offset, value)
                state[632:648] = changed
                with self.assertRaises(ValueError):
                    validate_flush(state, sqe, changed)

    def test_saved_cqe_is_compared_to_raw_dma(self):
        state, sqe, cqe = self.fixture(18)
        state[632] ^= 1
        with self.assertRaises(ValueError):
            validate_flush(state, sqe, cqe)

    def test_pending_fault_or_invalid_queue_history_rejected(self):
        cases = [(name, 1) for name in ('fault', 'pending', 'pending_cid', 'pending_kind',
                 'pending_bytes', 'pending_generation', 'started_ms', 'timeout_ms')]
        cases += [('ready', 0), ('held', 0), ('epoch', 2), ('qid', 0), ('depth', 3),
                  ('next_cid', 17), ('generation', 17), ('sq_tail', 1), ('cq_head', 1), ('phase', 1)]
        for name, value in cases:
            with self.subTest(name=name, value=value):
                state, sqe, cqe = self.fixture(18)
                struct.pack_into('<Q', state, 408 + QUEUE_FIELDS.index(name) * 8, value)
                with self.assertRaises(ValueError):
                    validate_flush(state, sqe, cqe)

    def test_runtime_pending_unhealthy_or_nonflush_state_rejected(self):
        for offset, value in ((576, 1), (584, 0), (592, 0), (608, 10), (616, 1),
                              (624, 0), (624, 3), (624, 9), (648, 3)):
            with self.subTest(offset=offset, value=value):
                state, sqe, cqe = self.fixture(18)
                struct.pack_into('<Q', state, offset, value)
                with self.assertRaises(ValueError):
                    validate_flush(state, sqe, cqe)

    def test_truncated_snapshot_rejected(self):
        for field in range(3):
            values = list(self.fixture(18))
            values[field] = values[field][:-1]
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_flush(*values)


class CleanupTests(unittest.TestCase):
    def test_qmp_cleanup_exception_still_stops_own_process_and_preserves_failure(self):
        class FakeProcess:
            returncode = None
            killed = False
            def poll(self): return self.returncode
            def kill(self): self.killed = True
            def wait(self, timeout):
                self.returncode = -1
                return self.returncode

        with tempfile.TemporaryDirectory(prefix='dongos-nvme-cleanup-') as folder:
            guest = NvmeGuest.__new__(NvmeGuest)
            guest._nvme_closed = False
            guest.process = FakeProcess()
            guest.state = Path(folder)
            guest.evidence = dict(actual_qemu_executed=True)
            with patch('tests.run_nvme_qemu.settings.Guest.close', side_effect=OSError('marked QMP failure')):
                with self.assertRaisesRegex(OSError, 'marked QMP failure'):
                    guest.close()
            record = json.loads((Path(folder) / 'guest.json').read_text())
            self.assertTrue(guest.process.killed)
            self.assertTrue(record['qemu_stopped'])
            self.assertIn('marked QMP failure', record['cleanup_error'])


class IsolationTests(unittest.TestCase):
    class Tables:
        def __init__(self):
            self.root = 0x100000
            self.pages = {self.root: bytearray(4096)}
            self.reads = []

        def allocate(self):
            pa = self.root + len(self.pages) * 4096
            self.pages[pa] = bytearray(4096)
            return pa

        def entry(self, table, index, value):
            struct.pack_into('<Q', self.pages[table], index * 8, value)

        def map(self, va, pa, shift=12, flags=7):
            table = self.root
            for level in (39, 30, 21, 12):
                index = (va >> level) & 511
                if level == shift:
                    self.entry(table, index, pa | flags | (128 if shift > 12 else 0))
                    return
                entry = struct.unpack_from('<Q', self.pages[table], index * 8)[0]
                if not entry:
                    child = self.allocate()
                    self.entry(table, index, child | 7)
                else:
                    child = entry & 0x000ffffffffff000
                table = child

        def read(self, pa):
            self.reads.append(pa)
            return bytes(self.pages[pa])

        def verify(self, physical=0x200000, length=131072, kernel_pool=None):
            return verify_no_user_dma_alias(self.root, self.read, physical, length, kernel_pool)

    def test_same_virtual_address_distinct_physical_lease_is_allowed(self):
        tables = self.Tables()
        tables.map(0x68000000, 0x220000)
        result = tables.verify()
        self.assertTrue(result['no_effective_user_physical_alias'])
        self.assertEqual(result['user_leaf_counts']['4096'], 1)

    def test_same_and_different_virtual_address_physical_aliases_are_rejected(self):
        for va in (0x68000000, 0x400000, 0x72000000, 0x7fffffc000):
            for pa in (0x200000, 0x21f000):
                with self.subTest(va=hex(va), pa=hex(pa)):
                    tables = self.Tables()
                    tables.map(va, pa)
                    with self.assertRaisesRegex(ValueError, 'aliases DMA'):
                        tables.verify()

    def test_adjacent_intervals_pass_and_partial_overlap_fails(self):
        for pa in (0x1ff000, 0x220000):
            tables = self.Tables()
            tables.map(0x400000, pa)
            self.assertTrue(tables.verify()['no_effective_user_physical_alias'])
        tables = self.Tables()
        tables.map(0x400000, 0x200000)
        with self.assertRaisesRegex(ValueError, 'aliases DMA'):
            tables.verify(0x200fff, 1)

    def test_user_permission_must_survive_every_level(self):
        for blocked_shift in (39, 30, 21, 12):
            with self.subTest(blocked_shift=blocked_shift):
                tables = self.Tables()
                tables.map(0x68000000, 0x200000)
                table = tables.root
                for shift in (39, 30, 21, 12):
                    index = (0x68000000 >> shift) & 511
                    entry = struct.unpack_from('<Q', tables.pages[table], index * 8)[0]
                    if shift == blocked_shift:
                        tables.entry(table, index, entry & ~4)
                        break
                    table = entry & 0x000ffffffffff000
                result = tables.verify()
                self.assertEqual(sum(result['user_leaf_counts'].values()), 0)
                self.assertEqual(len(tables.reads), (39 - blocked_shift) // 9 + 1)

    def test_large_user_leaves_check_their_entire_physical_interval(self):
        for shift in (21, 30):
            with self.subTest(shift=shift):
                tables = self.Tables()
                tables.map(0x80000000, 0, shift=shift)
                with self.assertRaisesRegex(ValueError, 'aliases DMA'):
                    tables.verify((1 << shift) - 4096, 4096)
                tables = self.Tables()
                tables.map(0x80000000, 2 << shift, shift=shift)
                result = tables.verify()
                self.assertEqual(result['user_leaf_counts'][str(1 << shift)], 1)

    def test_large_leaf_pat_bit_allowed_but_reserved_alignment_bits_rejected(self):
        for shift in (21, 30):
            tables = self.Tables()
            tables.map(0x80000000, (2 << shift) | 4096, shift=shift)
            self.assertTrue(tables.verify()['no_effective_user_physical_alias'])
            tables = self.Tables()
            tables.map(0x80000000, (2 << shift) | 8192, shift=shift)
            with self.assertRaisesRegex(ValueError, 'misaligned/reserved'):
                tables.verify()

    def test_top_level_large_flag_rejected_and_pt_pat_is_not_large(self):
        tables = self.Tables()
        tables.entry(tables.root, 0, 0x400087)
        with self.assertRaisesRegex(ValueError, 'invalid at PML4'):
            tables.verify()
        tables = self.Tables()
        tables.map(0x68000000, 0x220000, flags=0x87)
        self.assertEqual(tables.verify()['user_leaf_counts']['4096'], 1)

    def test_cycle_and_user_table_outside_private_pool_fail_closed(self):
        tables = self.Tables()
        tables.entry(tables.root, 0, tables.root | 7)
        with self.assertRaisesRegex(ValueError, 'cycle'):
            tables.verify()
        for pa in (0, 0x0ff000, 0x120000, 0x200000):
            with self.subTest(pa=hex(pa)):
                tables = self.Tables()
                tables.entry(tables.root, 0, pa | 7)
                with self.assertRaisesRegex(ValueError, 'outside allowlisted'):
                    tables.verify()
                self.assertEqual(tables.reads, [tables.root])

    def test_supervisor_and_absent_branches_do_not_dereference_external_tables(self):
        tables = self.Tables()
        tables.entry(tables.root, 0, 0x300003)
        tables.entry(tables.root, 1, 0x400006)
        self.assertTrue(tables.verify()['no_effective_user_physical_alias'])
        self.assertEqual(tables.reads, [tables.root])

    def test_repeated_table_dag_is_bounded_and_still_checks_aliases(self):
        tables = self.Tables()
        tables.map(0x400000, 0x220000)
        first = struct.unpack_from('<Q', tables.pages[tables.root], 0)[0]
        tables.entry(tables.root, 1, first)
        result = tables.verify()
        self.assertEqual(result['unique_tables_read'], 4)
        self.assertEqual(len(tables.reads), 4)
        self.assertEqual(result['user_leaf_counts']['4096'], 1)

    def test_incomplete_table_and_invalid_intervals_rejected(self):
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            verify_no_user_dma_alias(0x100000, lambda pa: bytes(4095), 0x200000, 131072)
        for root, pa, length in ((0, 0x200000, 4096), (0x100001, 0x200000, 4096),
                                  (0x100000, 0, 4096), (0x100000, 0x200000, 0),
                                  (0x100000, (1 << 52) - 4096, 8192)):
            with self.subTest(root=root, pa=pa, length=length), self.assertRaises(ValueError):
                verify_no_user_dma_alias(root, lambda table: bytes(4096), pa, length)


class InheritedPoolTests(unittest.TestCase):
    @staticmethod
    def fixture(user_leaf=False):
        tables = IsolationTests.Tables()
        pool = 0x400000
        for offset in (4096, 8192, 12288):
            tables.pages[pool + offset] = bytearray(4096)
        tables.entry(tables.root, 511, (pool + 4096) | 7)
        tables.entry(pool + 4096, 510, (pool + 8192) | 7)
        tables.entry(pool + 8192, 0, (pool + 12288) | 7)
        tables.entry(pool + 12288, 0, 0x200000 | (7 if user_leaf else 3))
        return tables, (pool, 128)

    def test_inherited_user_parents_and_supervisor_leaf_pass(self):
        tables, pool = self.fixture()
        result = tables.verify(kernel_pool=pool)
        self.assertEqual(result['unique_tables_read'], 4)
        self.assertEqual(result['trusted_kernel_pool'], [0x400000, 128])
        self.assertEqual(sum(result['user_leaf_counts'].values()), 0)
        self.assertEqual(result['supervisor_branches_skipped'], 1)

    def test_inherited_high_user_alias_leaf_is_rejected(self):
        tables, pool = self.fixture(user_leaf=True)
        with self.assertRaisesRegex(ValueError, 'aliases DMA'):
            tables.verify(kernel_pool=pool)

    def test_untrusted_external_pool_is_not_dereferenced(self):
        tables, pool = self.fixture()
        with self.assertRaisesRegex(ValueError, 'outside allowlisted'):
            tables.verify()
        self.assertEqual(tables.reads, [tables.root])
        tables, pool = self.fixture()
        tables.entry(tables.root, 511, 0x480007)
        with self.assertRaisesRegex(ValueError, 'outside allowlisted'):
            tables.verify(kernel_pool=pool)
        self.assertEqual(tables.reads, [tables.root])

    def test_overlapping_or_malformed_pool_parameters_rejected(self):
        for pool in ((0x100000, 128), (0x101000, 128), (0x0ff000, 128),
                     (0, 128), (0x400001, 128), (0x400000, 127), (0x400000, 129),
                     ((1 << 52) - 4096, 128)):
            with self.subTest(pool=pool):
                tables = IsolationTests.Tables()
                with self.assertRaises(ValueError):
                    tables.verify(kernel_pool=pool)
                self.assertEqual(tables.reads, [])

    def test_last_kernel_pool_page_allowed_and_shared_cycle_rejected(self):
        tables = IsolationTests.Tables()
        last = 0x400000 + 127 * 4096
        tables.pages[last] = bytearray(4096)
        tables.entry(tables.root, 511, last | 7)
        self.assertEqual(tables.verify(kernel_pool=(0x400000, 128))['unique_tables_read'], 2)
        tables, pool = self.fixture()
        tables.entry(0x401000, 510, 0x401007)
        with self.assertRaisesRegex(ValueError, 'cycle'):
            tables.verify(kernel_pool=pool)

    @staticmethod
    def guest_view():
        guest = NvmeGuest.__new__(NvmeGuest)
        guest.evidence = {}
        guest.kernel_memory_layout = dict(runtime_offset=35536, view_size=160,
            view_fields=dict(pool=96, pool_physical=104, pool_pages=112, root_physical=152))
        guest.ksym = lambda module, name: 0xffffffff800ad088
        view = bytearray(160)
        struct.pack_into('<3Q', view, 96, 0xffff800000400000, 0x400000, 128)
        struct.pack_into('<Q', view, 152, 0x400000)
        guest.kernel = lambda va, n, role: bytes(view) if (va, n) == (0xffffffff800b5b58, 160) else None
        guest.raw = bytearray(b'memory_pool_physical=0x0000000000400000\r\n'
            b'memory_pool_pages=0x0000000000000080\r\n'
            b'memory_root_physical=0x0000000000400000\r\n'
            b'memory_runtime_view=0xffffffff800b5b58\r\n')
        return guest, view

    def test_kernel_view_and_uart_must_independently_match(self):
        guest, _ = self.guest_view()
        self.assertEqual(guest.trusted_kernel_pool(), (0x400000, 128))
        self.assertTrue(guest.evidence['trusted_kernel_page_table_pool'][
            'independently_read_from_kernel_and_matched_to_uart'])
        for offset, value in ((96, 0), (104, 0x500000), (112, 127), (152, 0x500000)):
            with self.subTest(offset=offset):
                guest, view = self.guest_view()
                struct.pack_into('<Q', view, offset, value)
                with self.assertRaises(ValueError):
                    guest.trusted_kernel_pool()
        for raw in (b'', b'memory_pool_pages=0x0000000000000080\r\n'):
            guest, _ = self.guest_view()
            if raw:
                guest.raw.extend(raw)
            else:
                guest.raw = bytearray()
            with self.assertRaises(ValueError):
                guest.trusted_kernel_pool()


if __name__ == '__main__':
    unittest.main()
