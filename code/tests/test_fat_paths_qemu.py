"""Pure controls for the independent FAT tree oracle and UTF-8 UART gate."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools.make_fat32_disk import create, SEED
from tests.fat_paths_oracle import FatTree, checksum, long_name, inspect


def short(alias, cluster=0, size=0, attr=32):
    result = bytearray(32)
    if len(alias) != 11:
        raise ValueError('bad fixture alias')
    result[:11], result[11] = alias, attr
    struct.pack_into('<H', result, 20, cluster >> 16)
    struct.pack_into('<HI', result, 26, cluster & 65535, size)
    return result


def lfn_entries(name, alias):
    """Test fixture encoder, deliberately separate from production Dong code."""
    encoded = name.encode('utf-16le')
    units = list(struct.unpack('<' + str(len(encoded) // 2) + 'H', encoded))
    slots = (len(units) + 12) // 13
    if len(units) % 13:
        units.append(0)
    units += [65535] * (slots * 13 - len(units))
    entries = []
    for ordinal in range(slots, 0, -1):
        item = bytearray(32)
        item[0], item[11], item[13] = ordinal | (64 if ordinal == slots else 0), 15, checksum(alias)
        for offset, unit in zip((1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30),
                                units[(ordinal - 1) * 13:ordinal * 13]):
            struct.pack_into('<H', item, offset, unit)
        entries.append(item)
    return entries


class Fixture:
    def __init__(self, directory):
        self.path = Path(directory) / 'test.img'
        self.g = create(self.path, 64)
        self.raw = bytearray(self.path.read_bytes())
        self.fat(2, 4)
        for cluster in (4, 5, 6, 8, 9):
            self.fat(cluster, 0xfffffff)
        self.fat(7, 8)
        # Every slot preceding the crossing group is live, so a reader cannot
        # accidentally stop early at a zero/deleted fixture slot.
        for slot in range(1, 13):
            self.slot([2, 4], slot, short(('F%07d' % slot).encode() + b'TXT'))
        name, alias = 'Long \U0001f600 name over sector.txt', b'LONGNA~1TXT'
        group = lfn_entries(name, alias)
        assert len(group) == 3
        for slot, entry in enumerate(group + [short(alias, 9, 8)], 13):
            self.slot([2, 4], slot, entry)
        self.slot([2, 4], 17, short(b'SUB        ', 5, attr=16))
        self.dot(5, 0)
        self.slot([5], 2, short(b'DEEP       ', 6, attr=16))
        self.dot(6, 5)
        deepname, deepalias = '\u4e2d\u6587\U0001f600.txt', b'UNICOD~1TXT'
        self.deepname = '/SUB/DEEP/' + deepname
        group = lfn_entries(deepname, deepalias)
        for slot, entry in enumerate(group + [short(deepalias, 7, 700)], 2):
            self.slot([6], slot, entry)
        self.payload = bytes(range(250)) * 2 + bytes(range(200))
        self.raw[self.cluster_offset(7):self.cluster_offset(7) + 512] = self.payload[:512]
        self.raw[self.cluster_offset(8):self.cluster_offset(8) + 188] = self.payload[512:]
        self.raw[self.cluster_offset(9):self.cluster_offset(9) + 8] = b'rootLFN!'

    def fat(self, cluster, value, copy=None):
        for which in ((0, 1) if copy is None else (copy,)):
            struct.pack_into('<I', self.raw,
                             (self.g['reserved'] + which * self.g['fat_sectors']) * 512 + cluster * 4, value)

    def cluster_offset(self, cluster):
        return (self.g['data_start'] + cluster - 2) * 512

    def slot_offset(self, chain, index):
        return self.cluster_offset(chain[index // 16]) + index % 16 * 32

    def slot(self, chain, index, entry):
        offset = self.slot_offset(chain, index)
        self.raw[offset:offset + 32] = entry

    def dot(self, cluster, parent):
        self.slot([cluster], 0, short(b'.          ', cluster, attr=16))
        self.slot([cluster], 1, short(b'..         ', parent, attr=16))


class LfnTests(unittest.TestCase):
    def test_exact_slots_padding_and_surrogate_cross_slot(self):
        alias = b'EXAMPL~1TXT'
        for name in ('a', 'a' * 13, 'a' * 26, 'a' * 12 + '\U0001f680' + 'b',
                     '\u4e2d\u6587\U0001f600.txt', 'x' * 255):
            with self.subTest(name=name):
                self.assertEqual(long_name(lfn_entries(name, alias), alias), name)

    def test_each_lfn_contract_mutation_is_rejected(self):
        alias = b'EXAMPL~1TXT'
        positive = lfn_entries('Hello long Unicode \U0001f680 filename.txt', alias)
        cases = []
        for index in range(len(positive)):
            for offset in (0, 11, 12, 13, 26, 27):
                cases.append((index, offset, positive[index][offset] ^ 1))
        # Unpaired high surrogate in first logical name scalar, plus a FFFF
        # before terminator and non-FFFF bytes after the terminator.
        cases += [(len(positive) - 1, 1, 0), (len(positive) - 1, 2, 0xd8),
                  (0, 30, 0), (0, 31, 0)]
        for index, offset, value in cases:
            mutated = [bytearray(item) for item in positive]
            mutated[index][offset] = value
            with self.subTest(index=index, offset=offset, value=value), self.assertRaises(ValueError):
                long_name(mutated, alias)

    def test_wrong_alias_and_redundant_padding_group_rejected(self):
        alias = b'EXAMPL~1TXT'
        with self.assertRaises(ValueError):
            long_name(lfn_entries('valid name.txt', alias), b'OTHER   TXT')
        group = lfn_entries('x' * 14, alias)
        # A terminator at logical unit13 would make physical slot2 redundant.
        struct.pack_into('<H', group[0], 1, 0)
        for offset in (3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30):
            struct.pack_into('<H', group[0], offset, 65535)
        with self.assertRaises(ValueError):
            long_name(group, alias)


class TreeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='dongos-fat-tree-')
        self.addCleanup(self.directory.cleanup)
        self.fixture = Fixture(self.directory.name)

    def test_independent_tree_payload_dot_chain_and_sector_crossing(self):
        fixture = self.fixture
        fixture.path.write_bytes(fixture.raw)
        before = hashlib.sha256(fixture.raw).hexdigest()
        report = inspect(fixture.path, files={'/README.TXT': SEED, fixture.deepname: fixture.payload},
                         directories=('/SUB', '/SUB/DEEP'), require_crossing_lfn=True,
                         require_multicluster_file=fixture.deepname, absent=('/removed.txt',))
        self.assertEqual(report['image_sha256'], before)
        self.assertEqual(report['directories'][0]['clusters'], [2, 4])
        self.assertEqual(report['lfn_groups_crossing_sector_boundary'],
                         ['/Long \U0001f600 name over sector.txt'])
        self.assertEqual(hashlib.sha256(fixture.path.read_bytes()).hexdigest(), before)
        self.assertTrue(report['all_allocated_clusters_reachable'])

    def mutation_rejected(self, action):
        action()
        with self.assertRaises(ValueError):
            FatTree(self.fixture.raw)

    def test_mirror_clean_orphan_crosslink_cycle_and_dot_corruption(self):
        f = self.fixture
        original = bytes(f.raw)
        cases = [lambda: f.fat(7, 8, copy=0),  # changed below to a differing value
                 lambda: f.fat(1, 0x7ffffff),
                 lambda: f.fat(10, 0xfffffff),
                 lambda: f.fat(8, 7),
                 lambda: f.slot([2, 4], 18, short(b'OTHER   TXT', 7, 700)),
                 lambda: f.slot([5], 1, short(b'..         ', 6, attr=16)),
                 lambda: f.slot([5], 0, bytes([0xe5]) + bytes(31))]
        cases[0] = lambda: f.fat(7, 9, copy=0)
        for index, action in enumerate(cases):
            f.raw[:] = original
            with self.subTest(case=index):
                self.mutation_rejected(action)

    def test_size_duplicate_alias_namespace_and_orphan_lfn_rejected(self):
        f = self.fixture
        original = bytes(f.raw)
        cases = [lambda: f.slot([6], 3, short(b'UNICOD~1TXT', 7, 1)),
                 lambda: f.slot([2, 4], 18, short(b'README  TXT')),
                 lambda: f.slot([2, 4], 18, short(b'LONGNA~1TXT')),
                 lambda: f.slot([2, 4], 16, bytes([0xe5]) + bytes(31))]
        for index, action in enumerate(cases):
            f.raw[:] = original
            with self.subTest(case=index):
                self.mutation_rejected(action)

    def test_expected_literal_payload_absence_and_directory_checks(self):
        f = self.fixture
        f.path.write_bytes(f.raw)
        for keyword in ({'files': {f.deepname: b'wrong'}}, {'directories': ['/README.TXT']},
                        {'absent': ['/README.TXT']}, {'require_multicluster_file': '/README.TXT'},
                        {'files': {'/README.TXT': SEED}, 'exact_namespace': True}):
            with self.subTest(keyword=keyword), self.assertRaises(ValueError):
                inspect(f.path, **keyword)


class UartTests(unittest.TestCase):
    def test_utf8_quoted_command_and_exact_fresh_output(self):
        from tests.run_fat_paths_qemu import quote, fresh_response
        command = 'cat ' + quote('/\u4e2d\u6587 \U0001f600.txt')
        body = '\u4f1a\u8bae data\U0001f680\r\n'.encode()
        segment = command.encode() + b'\r\n' + body + b'> '
        result = fresh_response(segment, command, exact=body)
        self.assertTrue(result['complete_echo_and_new_prompt_verified'])
        self.assertEqual(bytes.fromhex(result['response_hex']), body)
        self.assertEqual(quote('one"two\\three'), '"one\\"two\\\\three"')

    def test_echo_never_counts_as_actual_file_output(self):
        from tests.run_fat_paths_qemu import fresh_response
        command = 'write "hello long name.txt" wanted-payload'
        segment = command.encode() + b'\r\nWRITE OK\r\n> '
        with self.assertRaises(ValueError):
            fresh_response(segment, command, expected=b'wanted-payload')
        self.assertIsNone(fresh_response(segment[:-2], command, expected=b'WRITE OK'))
        self.assertIsNone(fresh_response(b'WRITE OK\r\n> ', command, expected=b'WRITE OK'))

    def test_marked_errors_missing_errors_and_extra_bytes_rejected(self):
        from tests.run_fat_paths_qemu import fresh_response
        command = 'cd /missing'
        echo = command.encode() + b'\r\n'
        error = b'ERROR 0x0000000005040006\r\n'
        result = fresh_response(echo + error + b'> ', command, expect_error=True)
        self.assertEqual(result['error_code'], 0x5040006)
        for body, want_error in ((error, False), (b'CD OK\r\n', True),
                                 (error + b'extra\r\n', True), (error + error, True),
                                 (b'ERROR 0x0000000000000000\r\n', True),
                                 (b'unknown command\r\n', False),
                                 (b'PANIC\r\n', False)):
            with self.subTest(body=body, want_error=want_error), self.assertRaises(ValueError):
                fresh_response(echo + body + b'> ', command, expect_error=want_error)

    def test_only_bounded_utf8_lines_and_no_control_injection(self):
        from tests.run_fat_paths_qemu import command_bytes, quote
        self.assertEqual(len(command_bytes('x' * 8191)), 8191)
        for command in ('', 'x' * 8192, '\u4e2d' * 2731, 'cat a\rwrite b evil',
                        'cat a\n', 'cat\tfile', 'cat\0file', 'cat\x7ffile', '\ud800'):
            with self.subTest(command=repr(command[:30])), self.assertRaises((ValueError, UnicodeError)):
                command_bytes(command)
        for path in ('one\rpower', 'one\nexit', '\0'):
            with self.assertRaises(ValueError):
                quote(path)

    def test_generated_actual_commands_fit_line_and_lfn_data_is_not_host_injected(self):
        from tests.run_fat_paths_qemu import populate, command_bytes, BIG, CROSS, BOUNDARY, file_payloads
        class Recorder:
            def __init__(self): self.commands = []
            def shell(self, command, expected=None, **kwargs):
                command_bytes(command)
                self.commands.append((command, expected, kwargs))
                return dict(command=command)
        guest = Recorder()
        files, commands = populate(guest, 'run-pure-control')
        self.assertEqual(len(commands), len(guest.commands))
        self.assertGreater(len(files[BIG]), 2048)
        self.assertGreater(len(file_payloads('run-pure-control')[1]), 4096)
        self.assertTrue(any(command.startswith('append ') for command, _, _ in guest.commands))
        touches = [command for command, _, _ in guest.commands if command.startswith('touch "' + BOUNDARY + '/F')]
        self.assertEqual(len(touches), 13)
        crossing = next(i for i, (command, _, _) in enumerate(guest.commands)
                        if command.startswith('write "' + CROSS + '"'))
        self.assertTrue(all(i < crossing for i, (command, _, _) in enumerate(guest.commands) if command in touches))
        for name, payload in file_payloads('run-pure-control')[0].items():
            self.assertEqual(files[name], payload)

    def test_each_rejected_path_gets_whole_disk_unchanged_check(self):
        from tests.run_fat_paths_qemu import rejections
        class Recorder:
            def shell(self, command, expected=None, **kwargs):
                return dict(command=command, error_code=0x5040006 if kwargs.get('expect_error') else 0)
        with patch('tests.run_fat_paths_qemu.settings.sha', return_value='unchanged'):
            commands, checks = rejections(Recorder(), Path('not-opened.img'))
        self.assertEqual(len(checks), 9)
        self.assertEqual(len(commands), 36)
        self.assertTrue(all(item['entire_image_unchanged'] for item in checks))
        with patch('tests.run_fat_paths_qemu.settings.sha', side_effect=['before', 'after']):
            with self.assertRaisesRegex(ValueError, 'rejected path changed'):
                rejections(Recorder(), Path('not-opened.img'))


class ChannelTests(unittest.TestCase):
    class Tables:
        def __init__(self):
            self.roots = [0x100000 + i * 0x100000 for i in range(5)]
            self.pool = (0x900000, 128)
            self.pages = {root: bytearray(4096) for root in self.roots}
            self.next = {root: root + 4096 for root in self.roots}
            self.leaves = {}
            for channel, owners in ((0x50000000, (0, 1)), (0x51000000, (1, 2)), (0x52000000, (1, 3))):
                for index in range(16):
                    physical = 0x1000000 + (channel - 0x50000000) // 0x1000000 * 65536 + index * 4096
                    for pid in owners:
                        self.map(pid, channel + index * 4096, physical)

        def map(self, pid, virtual, physical, flags=0x8000000000000007):
            root, table = self.roots[pid], self.roots[pid]
            for shift in (39, 30, 21):
                offset = ((virtual >> shift) & 511) * 8
                value = struct.unpack_from('<Q', self.pages[table], offset)[0]
                if not value:
                    child = self.next[root]
                    self.next[root] += 4096
                    self.pages[child] = bytearray(4096)
                    struct.pack_into('<Q', self.pages[table], offset, child | 7)
                    value = child | 7
                table = value & 0x000ffffffffff000
            offset = ((virtual >> 12) & 511) * 8
            struct.pack_into('<Q', self.pages[table], offset, physical | flags)
            self.leaves[pid, virtual] = table, offset

        def read(self, physical):
            return self.pages[physical]

    def test_three_pairs_all_forty_eight_pages_distinct(self):
        from tests.run_fat_paths_qemu import verify_channels
        tables = self.Tables()
        result = verify_channels(tables.roots, tables.read, tables.pool)
        self.assertEqual(result['distinct_physical_pages'], 48)
        self.assertEqual([channel['authorized_processes'] for channel in result['channels']],
                         [[0, 1], [1, 2], [1, 3]])

    def test_supervisor_ancestor_is_allowed_only_for_unauthorized_process(self):
        from tests.run_fat_paths_qemu import verify_channels
        tables = self.Tables()
        # A leaf advertises USER, but a supervisor PML4 ancestor makes it
        # inaccessible. This is the inherited-kernel-alias negative case.
        tables.map(4, 0x50000000, 0x1000000)
        struct.pack_into('<Q', tables.pages[tables.roots[4]], 0,
                         struct.unpack_from('<Q', tables.pages[tables.roots[4]], 0)[0] & ~4)
        result = verify_channels(tables.roots, tables.read, tables.pool)
        mapping = result['channels'][0]['pages'][0]['process_mappings']['4']
        self.assertTrue(mapping['present'])
        self.assertFalse(mapping['effective_user'])
        struct.pack_into('<Q', tables.pages[tables.roots[0]], 0,
                         struct.unpack_from('<Q', tables.pages[tables.roots[0]], 0)[0] & ~4)
        with self.assertRaises(ValueError):
            verify_channels(tables.roots, tables.read, tables.pool)

    def test_bad_actual_channel_permissions_sharing_alias_or_unauthorized_mapping_rejected(self):
        from tests.run_fat_paths_qemu import verify_channels
        cases = [lambda t: t.map(4, 0x50000000, 0x1000000),
                 lambda t: t.map(0, 0x50000000, 0x1000000, 0x8000000000000005),
                 lambda t: t.map(0, 0x50000000, 0x1000000, 7),
                 lambda t: t.map(0, 0x50000000, 0x1000000, 0x800000000000001f),
                 lambda t: t.map(0, 0x50000000, 0x1000000, 0x8000000000000087),
                 lambda t: t.map(1, 0x50000000, 0x2000000),
                 lambda t: (t.map(1, 0x51000000, 0x1000000), t.map(2, 0x51000000, 0x1000000)),
                 lambda t: struct.pack_into('<Q', t.pages[t.roots[0]], 0, 0xf00007),
                 lambda t: struct.pack_into('<Q', t.pages[t.roots[0]], 0, t.roots[0] | 7)]
        for index, action in enumerate(cases):
            tables = self.Tables()
            action(tables)
            with self.subTest(case=index), self.assertRaises(ValueError):
                verify_channels(tables.roots, tables.read, tables.pool)


if __name__ == '__main__':
    unittest.main()
