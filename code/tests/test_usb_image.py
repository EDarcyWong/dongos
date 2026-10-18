"""Actual GPT/FAT32 image bytes, independent parser and corruption controls."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid
import zlib

from tools import make_usb_image as usb

ROOT = Path(__file__).resolve().parents[1]


def fixture(folder: Path) -> dict[str, bytes]:
    (folder / 'EFI/BOOT').mkdir(parents=True)
    (folder / 'EXTRA/LEVEL2').mkdir(parents=True)
    files = {'EFI/BOOT/BOOTX64.EFI': b'MZ\0\0UEFI payload fixture\n',
             'DONGOS.IMG': bytes(range(251)) * 13,
             'SERVICES.BIN': bytes(range(255, -1, -1)) * 97,
             'EMPTY.TXT': b'', 'EXTRA/LEVEL2/DEEP.DAT': b'deep data' * 100}
    # More than one directory cluster in root AND a nested directory; full
    # sectors cannot accidentally serve as an implicit end-of-directory marker.
    for index in range(24):
        files[f'ROOT{index:02d}.DAT'] = bytes([index]) * (index * 53 + 1)
        files[f'EXTRA/ITEM{index:02d}.BIN'] = bytes([index ^ 0x5a]) * (index * 67 + 1)
    for name, data in files.items():
        (folder / name).write_bytes(data)
    return files


def independent_read(path: Path) -> dict:
    """Separate test oracle: seeks disk bytes and walks every file/dir chain.

    No calls to production writer/reader/geometry/name helpers. GPT CRC and
    file byte equality are checked without interpreting a tool manifest.
    """
    with path.open('rb') as stream:
        size = path.stat().st_size
        def read(at, length):
            stream.seek(at)
            value = stream.read(length)
            if len(value) != length:
                raise AssertionError('short disk read')
            return value
        mbr = read(0, 512)
        assert mbr[510:] == b'\x55\xaa' and mbr[450] == 0xee
        assert struct.unpack_from('<II', mbr, 454) == (1, size // 512 - 1)
        copies = []
        for lba in (1, size // 512 - 1):
            header = bytearray(read(lba * 512, 512))
            assert header[:8] == b'EFI PART'
            header_length = int.from_bytes(header[12:16], 'little')
            crc = int.from_bytes(header[16:20], 'little')
            header[16:20] = bytes(4)
            assert zlib.crc32(header[:header_length]) == crc
            table_lba, count, entry_size, table_crc = struct.unpack_from('<QIII', header, 72)
            table = read(table_lba * 512, count * entry_size)
            assert zlib.crc32(table) == table_crc
            copies.append(table)
        assert copies[0] == copies[1] and copies[0][:16] == bytes.fromhex('28732ac11ff8d211ba4b00a0c93ec93b')
        first, last = struct.unpack_from('<QQ', copies[0], 32)
        assert first == 2048 and last < size // 512 - 33
        boot = read(first * 512, 512)
        assert read((first + 6) * 512, 512) == boot
        assert struct.unpack_from('<H', boot, 11)[0] == 512 and boot[13] == 1 and boot[16] == 2
        reserved = struct.unpack_from('<H', boot, 14)[0]
        fat_sectors = struct.unpack_from('<I', boot, 36)[0]
        sector_count = struct.unpack_from('<I', boot, 32)[0]
        clusters = sector_count - reserved - 2 * fat_sectors
        assert clusters >= 65525
        fat = read((first + reserved) * 512, fat_sectors * 512)
        assert read((first + reserved + fat_sectors) * 512, fat_sectors * 512) == fat
        base = (first + reserved + fat_sectors * 2) * 512
        claimed, directories, files = set(), {}, {}
        def chain(start):
            value = []
            while start < 0x0ffffff8:
                assert 2 <= start < clusters + 2 and start not in claimed
                claimed.add(start)
                value.append(start)
                start = int.from_bytes(fat[start * 4:start * 4 + 4], 'little')
            return value
        def visit(start, name):
            links = chain(start)
            directories[name] = links
            data = b''.join(read(base + (index - 2) * 512, 512) for index in links)
            for at in range(0, len(data), 32):
                item = data[at:at + 32]
                if not item[0]:
                    assert not any(data[at:])
                    return
                base_name = item[:8].decode('ascii').strip()
                extension = item[8:11].decode('ascii').strip()
                if base_name in ('.', '..'):
                    continue
                part = base_name + ('.' + extension if extension else '')
                full = name + '/' + part if name else part
                cluster = int.from_bytes(item[20:22], 'little') << 16 | int.from_bytes(item[26:28], 'little')
                if item[11] == 0x10:
                    visit(cluster, full)
                else:
                    length = int.from_bytes(item[28:32], 'little')
                    links = chain(cluster) if cluster else []
                    payload = b''.join(read(base + (index - 2) * 512, 512) for index in links)
                    assert len(links) == (length + 511) // 512 and not any(payload[length:])
                    files[full] = payload[:length]
            raise AssertionError('directory has no end marker')
        visit(struct.unpack_from('<I', boot, 44)[0], '')
        for index in range(2, clusters + 2):
            assert (index in claimed) == bool(int.from_bytes(fat[index * 4:index * 4 + 4], 'little'))
        info = read((first + 1) * 512, 512)
        assert read((first + 7) * 512, 512) == info
        assert int.from_bytes(info[488:492], 'little') == clusters - len(claimed)
        return dict(files=files, directories=directories, first=first, last=last, fat_sectors=fat_sectors,
                    fat_offset=(first + reserved) * 512, data_offset=base, used=len(claimed))


class UsbImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = ROOT / 'build/test/usb-image/host' / ('run-' + uuid.uuid4().hex[:12])
        cls.evidence.mkdir(parents=True)
        cls.sources = [ROOT / 'tools/make_usb_image.py', Path(__file__)]
        cls.before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.sources}
        cls.results = {}

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.sources}
        if after != cls.before:
            raise AssertionError('USB tool/test sources changed during verification')
        (cls.evidence / 'validation-summary.json').write_text(json.dumps(dict(
            source_sha256=after, sources_unchanged=True, evidence=cls.results), indent=2) + '\n', encoding='utf-8')

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='dongos-usb-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.esp = self.base / 'esp'
        self.original = fixture(self.esp)
        self.target = self.base / 'disk.img'

    def expected(self):
        return {p: dict(length=len(v), sha256=hashlib.sha256(v).hexdigest()) for p, v in self.original.items()}

    def test_actual_raw_gpt_fat_multicluster_and_complete_payloads(self):
        result = usb.create(self.esp, self.target, 64)
        oracle = independent_read(self.target)
        self.assertEqual(self.original, oracle['files'])
        self.assertGreater(len(oracle['directories']['']), 1)
        self.assertGreater(len(oracle['directories']['EXTRA']), 1)
        self.assertEqual(oracle['used'], result['esp']['used_clusters'])
        self.assertTrue(stat.S_ISREG(self.target.stat().st_mode))
        self.assertEqual(64 * 1024 * 1024, self.target.stat().st_size)
        self.assertEqual(hashlib.sha256(self.target.read_bytes()).hexdigest(), result['image_sha256'])
        self.assertEqual(result, json.loads(self.target.with_name('disk.img.json').read_text(encoding='utf-8')))
        self.assertTrue(result['sources_unchanged'] and result['verified_payloads'])
        usb.inspect_image(self.target, self.expected())
        self.results['raw_independent_oracle'] = dict(files=len(oracle['files']), directories=len(oracle['directories']),
            multicluster_root=len(oracle['directories']['']), multicluster_nested=len(oracle['directories']['EXTRA']),
            gpt_headers=2, fat_mirrors=2, payload_bytes=sum(map(len, self.original.values())))

    def test_crc_mirror_cycle_crosslink_and_payload_corruption_rejected(self):
        usb.create(self.esp, self.target, 64)
        info = independent_read(self.target)
        parsed = usb.inspect_image(self.target)
        mutations = [
            ('primary-header-crc', 512 + 24, b'\x02', 'GPT header'),
            ('primary-entries-crc', 1024 + 60, b'\x01', 'GPT entries CRC'),
            ('backup-header-crc', self.target.stat().st_size - 512 + 16, b'\x01', 'GPT header CRC'),
            ('fat-mirror', info['fat_offset'] + info['fat_sectors'] * 512 + 12, b'\x01', 'FAT mirrors'),
            ('backup-bpb', (info['first'] + 6) * 512 + 13, b'\x02', 'boot mirror'),
            ('fsinfo-count', (info['first'] + 1) * 512 + 488, b'\x00', 'FSInfo'),
        ]
        for label, offset, data, message in mutations:
            changed = self.base / (label + '.img')
            shutil.copyfile(self.target, changed)
            with changed.open('r+b') as stream:
                stream.seek(offset)
                stream.write(data)
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, message):
                usb.inspect_image(changed, self.expected())
            changed.unlink()
        # A self cycle is written to both FATs, so mirror comparison cannot be
        # the reason the parser rejects the invalid chain.
        changed = self.base / 'cycle.img'
        shutil.copyfile(self.target, changed)
        cluster = parsed['files']['SERVICES.BIN']['cluster']
        with changed.open('r+b') as stream:
            for index in (0, 1):
                stream.seek(info['fat_offset'] + index * info['fat_sectors'] * 512 + cluster * 4)
                stream.write(struct.pack('<I', cluster))
        with self.assertRaisesRegex(ValueError, 'cyclic/cross-linked'):
            usb.inspect_image(changed)
        # A different broken chain converges on an already-owned file. Both
        # copies agree, so it tests ownership rather than just FAT equality.
        changed = self.base / 'crosslink.img'
        shutil.copyfile(self.target, changed)
        with changed.open('r+b') as stream:
            for index in (0, 1):
                stream.seek(info['fat_offset'] + index * info['fat_sectors'] * 512 + cluster * 4)
                stream.write(struct.pack('<I', parsed['files']['DONGOS.IMG']['cluster']))
        with self.assertRaisesRegex(ValueError, 'cyclic/cross-linked'):
            usb.inspect_image(changed)
        # Recompute both table CRCs and header CRCs around an out-of-range ESP.
        # Valid CRCs are integrity checks, not sufficient range authorization.
        changed = self.base / 'partition-bounds.img'
        shutil.copyfile(self.target, changed)
        with changed.open('r+b') as stream:
            for header_lba in (1, changed.stat().st_size // 512 - 1):
                stream.seek(header_lba * 512)
                header = bytearray(stream.read(512))
                table_lba = struct.unpack_from('<Q', header, 72)[0]
                stream.seek(table_lba * 512)
                table = bytearray(stream.read(128 * 128))
                struct.pack_into('<Q', table, 40, changed.stat().st_size // 512)
                struct.pack_into('<I', header, 88, zlib.crc32(table))
                header[16:20] = bytes(4)
                struct.pack_into('<I', header, 16, zlib.crc32(header[:92]))
                stream.seek(table_lba * 512)
                stream.write(table)
                stream.seek(header_lba * 512)
                stream.write(header)
        with self.assertRaisesRegex(ValueError, 'ESP partition'):
            usb.inspect_image(changed)
        # Valid chains and all CRCs remain intact, but a real file byte changes.
        changed = self.base / 'payload.img'
        shutil.copyfile(self.target, changed)
        with changed.open('r+b') as stream:
            stream.seek(info['data_offset'] + (cluster - 2) * 512)
            stream.write(b'\x99')
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            usb.inspect_image(changed, self.expected())
        self.results['raw_corruptions_rejected'] = [x[0] for x in mutations] + ['cycle-both-FATs',
            'crosslink-both-FATs', 'out-of-range-partition-valid-CRCs', 'file-byte-SHA256']

    def test_existing_outputs_device_paths_source_links_and_unsafe_names(self):
        for path in ('/dev/sda', '/proc/self/mem', r'\\.\PhysicalDrive0', r'\\?\C:\disk.img', r'\\server\share\disk.img', 'NUL.img'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                usb.create(self.esp, path, 64)
        for child in (self.target, self.target.with_name('disk.img.json')):
            child.write_bytes(b'preserve existing object')
            with self.assertRaises(FileExistsError):
                usb.create(self.esp, self.target, 64)
            self.assertEqual(b'preserve existing object', child.read_bytes())
            child.unlink()
        with self.assertRaises(ValueError):
            usb.create(self.esp, self.esp / 'new.img', 64)
        for name in ('longfilename.txt', 'space bad', 'BAD.NAME.EXT', 'COM1', '\u4e2d\u6587.TXT'):
            child = self.esp / name
            # Windows treats COM1 as a device, so never attempt to create it.
            if name == 'COM1':
                with self.assertRaises(ValueError):
                    usb._short(name)
                continue
            child.write_bytes(b'unsafe')
            with self.subTest(name=name), self.assertRaises(ValueError):
                usb.create(self.esp, self.target, 64)
            child.unlink()
        # Exercise the platform-neutral reparse bit using an actual source
        # path stat, without requiring Windows SeCreateSymbolicLinkPrivilege.
        original = Path.lstat
        item = self.esp / 'DONGOS.IMG'
        def reparse(value, *args, **kwargs):
            actual = original(value, *args, **kwargs)
            if value == item:
                return mock.Mock(st_mode=actual.st_mode, st_file_attributes=0x400)
            return actual
        with mock.patch.object(Path, 'lstat', reparse), self.assertRaisesRegex(ValueError, 'reparse'):
            usb.create(self.esp, self.target, 64)
        self.assertFalse(self.target.exists())

    def test_bounds_missing_payload_and_insufficient_partition_space(self):
        for size in (0, 63, 65, 1024, True, 128.0):
            with self.subTest(size=size), self.assertRaises(ValueError):
                usb.create(self.esp, self.target, size)
        required = self.esp / 'SERVICES.BIN'
        required.unlink()
        with self.assertRaisesRegex(ValueError, 'nonempty'):
            usb.create(self.esp, self.target, 64)
        with required.open('wb') as stream:
            stream.truncate(usb.MAX_FILE_BYTES + 1)
        with self.assertRaisesRegex(ValueError, 'length exceeds'):
            usb.create(self.esp, self.target, 64)
        required.write_bytes(self.original['SERVICES.BIN'])
        # Bound checks use actual source objects and are performed before the
        # staging file can be published, including a too-small ESP budget.
        with mock.patch.object(usb, 'MAX_SOURCE_BYTES', 1), self.assertRaisesRegex(ValueError, 'payload exceeds'):
            usb.create(self.esp, self.target, 64)
        original = usb._fat_geometry
        def tiny(sectors):
            value = original(sectors)
            value['clusters'] = 2
            return value
        with mock.patch.object(usb, '_fat_geometry', tiny), self.assertRaisesRegex(ValueError, 'insufficient'):
            usb.create(self.esp, self.target, 64)
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.base.glob('*.tmp*')))

    def test_source_changes_after_complete_readback_are_rejected_atomically(self):
        real_reader = usb.inspect_image
        hits = []
        def change_source(*args, **kwargs):
            value = real_reader(*args, **kwargs)
            item = self.esp / 'DONGOS.IMG'
            data = bytearray(item.read_bytes())
            data[-1] ^= 0x40
            item.write_bytes(data)
            hits.append('actual source mutation after valid image readback')
            return value
        with mock.patch.object(usb, 'inspect_image', change_source), self.assertRaisesRegex(ValueError, 'source tree changed'):
            usb.create(self.esp, self.target, 64)
        self.assertEqual(1, len(hits))
        self.assertFalse(self.target.exists())
        self.assertFalse(self.target.with_name('disk.img.json').exists())
        self.results['actual_source_mutation_rejected'] = hits

    def test_actual_bad_writer_control_and_publication_race_do_not_pass(self):
        writer = usb._write_image
        hits = []
        def bad_writer(stream, source, mib):
            writer(stream, source, mib)
            stream.seek((2048 + 32) * 512)
            stream.write(b'BAD!')  # first FAT only, not a mocked parser result
            hits.append('actual first-FAT corruption')
        with mock.patch.object(usb, '_write_image', bad_writer), self.assertRaisesRegex(ValueError, 'FAT mirrors'):
            usb.create(self.esp, self.target, 64)
        self.assertEqual(1, len(hits))
        self.assertFalse(self.target.exists())
        link = os.link
        def race(source, destination):
            if Path(destination) == self.target:
                self.target.write_bytes(b'concurrent creator owns this')
            return link(source, destination)
        with mock.patch.object(usb.os, 'link', race), self.assertRaises(FileExistsError):
            usb.create(self.esp, self.target, 64)
        self.assertEqual(b'concurrent creator owns this', self.target.read_bytes())
        self.assertFalse(self.target.with_name('disk.img.json').exists())
        self.results['actual_bad_writer_rejected'] = hits
        self.results['concurrent_existing_target_preserved'] = True

    def test_cli_creates_new_file_and_verify_is_read_only(self):
        args = [sys.executable, '-m', 'tools.make_usb_image', str(self.esp), str(self.target), '--size-mib', '64']
        created = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, created.returncode, created.stderr)
        first = json.loads(created.stdout)
        before = hashlib.sha256(self.target.read_bytes()).hexdigest()
        checked = subprocess.run([sys.executable, '-m', 'tools.make_usb_image', '--verify', str(self.target)],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, checked.returncode, checked.stderr)
        self.assertEqual(before, json.loads(checked.stdout)['image_sha256'])
        self.assertEqual(before, hashlib.sha256(self.target.read_bytes()).hexdigest())
        refused = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(0, refused.returncode)
        self.assertIn('refusing overwrite', refused.stderr)
        self.results['cli'] = dict(create_exit=created.returncode, verify_exit=checked.returncode,
            overwrite_exit=refused.returncode, original_hash=first['image_sha256'], verify_preserved_hash=before)


if __name__ == '__main__':
    unittest.main()
