"""Independent raw FAT32 / DONGPREF oracle for the actual desktop reboot gate.

No Dong, runner, filesystem, preferences, or disk-generator code is imported.
The image is the bounded FAT32 superfloppy used by the real service test (not
an MBR/GPT partition wrapper). Every referenced root/file cluster is checked.

Suggested actual-QEMU sequence (the runner owns QEMU and its shutdown):
1. Boot one disk, exercise all five runtime scales and complete light/dark
   themes; inspect real service state, atlas/resource mapping and GOP pixels.
2. Save two *different* settings with S, stop/quit/reap QEMU, inspect_disk().
   Require two valid records, increasing sequences, and the intended latest
   theme/scale in the raw newest slot, not merely a serial 'saved' message.
3. Reboot the same disk with a different build-time default. Before any R/S
   input compare actual startup state/pixels to the oracle's selected record;
   R must also restore that record after a volatile +/-/T change.
4. Quit/reap, copy the saved disk for evidence, corrupt_cfg_byte(newest slot),
   and reboot that same corrupted copy. Require actual service state/pixels
   equal the older valid slot. This helper never labels a guest run as passed.

Layout agreed with the preferences owner: 128-byte LE DONGPREF v1, 72-byte
logical Theme at offset32 (including zero padding68), checksum104..111 zeroed
for bidirectional Adler32, and reserved112..127 zero. A valid theme has opaque
background AND surface, premultiplied colors, five exact Q8 scales, bounded
radius/shadow/duration. Sequence comparison is unsigned, never modular.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import time
import unittest
import uuid
import zlib

RECORD_SIZE = 128
CFG_NAMES = (b'DESK0   CFG', b'DESK1   CFG')
SCALES_Q8 = (256, 320, 384, 448, 512)
COLOR_NAMES = ('background', 'surface', 'text', 'muted', 'accent', 'border', 'shadow', 'selection', 'danger')
METRIC_NAMES = ('radius', 'shadow_size', 'scale_q8', 'duration_ms')
MAX_FILE_BYTES = 1 << 20
MAX_FAT_BYTES = 64 << 20
MAX_IMAGE_BYTES = 4 << 30


class DiskError(ValueError):
    """Disk structure is ambiguous, inconsistent, or outside test bounds."""


class RecordError(ValueError):
    """One preference record is not valid; its peer can still be selected."""


def checksum(data: bytes) -> int:
    """Independent zlib implementation of the owner's two Adler32 streams."""
    if len(data) != RECORD_SIZE:
        raise RecordError('record length must be exactly 128')
    work = bytearray(data)
    work[104:112] = b'\0' * 8
    return ((zlib.adler32(work[::-1]) & 0xffffffff) << 32) | (zlib.adler32(work) & 0xffffffff)


def decode_record(data: bytes) -> dict:
    """Decode and validate actual record bytes, without guest/theme imports."""
    data = bytes(data)
    if len(data) != RECORD_SIZE:
        raise RecordError('record length must be exactly 128')
    if data[:8] != b'DONGPREF':
        raise RecordError('record magic differs')
    version, length = struct.unpack_from('<II', data, 8)
    if (version, length) != (1, RECORD_SIZE):
        raise RecordError('record version/length differs')
    sequence, flags = struct.unpack_from('<QQ', data, 16)
    if sequence == 0 or flags != 0:
        raise RecordError('sequence zero or unknown flags')
    if data[68:72] != b'\0' * 4 or data[112:128] != b'\0' * 16:
        raise RecordError('theme padding or reserved bytes are nonzero')
    stored = struct.unpack_from('<Q', data, 104)[0]
    calculated = checksum(data)
    if stored != calculated:
        raise RecordError('bidirectional Adler32 mismatch')
    colors = dict(zip(COLOR_NAMES, struct.unpack_from('<9I', data, 32)))
    metrics = dict(zip(METRIC_NAMES, struct.unpack_from('<4Q', data, 72)))
    for name, color in colors.items():
        alpha = color >> 24
        if any(((color >> shift) & 255) > alpha for shift in (0, 8, 16)):
            raise RecordError('non-premultiplied ' + name)
    if colors['background'] >> 24 != 255 or colors['surface'] >> 24 != 255:
        raise RecordError('background/surface must be opaque')
    if metrics['radius'] > 32 or metrics['shadow_size'] > 32 or metrics['duration_ms'] > 1000:
        raise RecordError('theme metric out of range')
    if metrics['scale_q8'] not in SCALES_Q8:
        raise RecordError('scale is not one of the five runtime levels')
    return dict(version=version, length=length, sequence=sequence, flags=flags,
                theme={**colors, **metrics}, checksum=stored, checksum_hex=f'{stored:016x}',
                sha256=hashlib.sha256(data).hexdigest())


def select_records(first: bytes | None, second: bytes | None) -> dict:
    """Return selected/no_valid_record/conflict; never invent a default theme."""
    raw = (first, second)
    records, errors = [], []
    for item in raw:
        try:
            if item is None:
                raise RecordError('file absent')
            records.append(decode_record(item))
            errors.append(None)
        except RecordError as exc:
            records.append(None)
            errors.append(str(exc))
    valid = [index for index, record in enumerate(records) if record is not None]
    base = dict(valid=[record is not None for record in records], errors=errors)
    if not valid:
        return dict(status='no_valid_record', **base)
    if len(valid) == 1:
        slot = valid[0]
    else:
        a, b = records
        if a['sequence'] == b['sequence']:
            if raw[0] != raw[1]:
                return dict(status='conflict', sequence=a['sequence'], **base)
            slot = 0
        else:
            slot = 0 if a['sequence'] > b['sequence'] else 1
    return dict(status='selected', slot=slot, record=records[slot], **base)


class Fat32Image:
    """Bounded independent FAT32 reader. Use as a context manager."""

    def __init__(self, path: Path | str, *, require_clean: bool = True):
        self.path = Path(path).resolve()
        self.stream = self.path.open('rb')
        try:
            self.image_bytes = os.fstat(self.stream.fileno()).st_size
            if not 512 <= self.image_bytes <= MAX_IMAGE_BYTES:
                raise DiskError('image exceeds supported superfloppy bounds')
            boot = self._read(0, 512)
            if boot[510:512] != b'\x55\xaa':
                raise DiskError('boot signature absent')
            bps = struct.unpack_from('<H', boot, 11)[0]
            spc = boot[13]
            reserved = struct.unpack_from('<H', boot, 14)[0]
            nfats = boot[16]
            root_entries, total16, fat16 = (struct.unpack_from('<H', boot, off)[0] for off in (17, 19, 22))
            total = struct.unpack_from('<I', boot, 32)[0]
            fat_sectors = struct.unpack_from('<I', boot, 36)[0]
            flags, version = struct.unpack_from('<HH', boot, 40)
            root = struct.unpack_from('<I', boot, 44)[0] & 0x0fffffff
            if bps != 512 or not spc or spc & (spc - 1) or spc > 128 or reserved < 1 or nfats != 2:
                raise DiskError('expected bounded 512-byte, mirrored FAT32 geometry')
            if root_entries or total16 or fat16 or version or flags & 0x80 or flags & ~0x008f:
                raise DiskError('not supported mirrored FAT32 BPB')
            first_data = reserved + nfats * fat_sectors
            if not fat_sectors or first_data >= total or total * bps != self.image_bytes:
                raise DiskError('volume length/metadata bounds differ from image')
            clusters = (total - first_data) // spc
            if not 65525 <= clusters < 0x0ffffff5 or (clusters + 2) * 4 > fat_sectors * bps:
                raise DiskError('cluster count/FAT capacity is not FAT32')
            if not 2 <= root < clusters + 2 or fat_sectors * bps > MAX_FAT_BYTES:
                raise DiskError('root/FAT exceeds bounds')
            self.geometry = dict(bytes_per_sector=bps, sectors_per_cluster=spc, reserved_sectors=reserved,
                                 fat_count=nfats, fat_sectors=fat_sectors, total_sectors=total,
                                 first_data_sector=first_data, cluster_count=clusters, root_cluster=root)
            self.cluster_bytes = bps * spc
            self.fat_offset = reserved * bps
            self.fat = self._read(self.fat_offset, fat_sectors * bps)
            mirror = self._read(self.fat_offset + len(self.fat), len(self.fat))
            if self.fat != mirror:
                raise DiskError('raw FAT mirrors differ')
            first, second = struct.unpack_from('<II', self.fat)
            if (first & 0x0fffff00) != 0x0fffff00 or (first & 255) != boot[21] or (second & 0x03ffffff) != 0x03ffffff:
                raise DiskError('FAT reserved entries/media byte differ')
            self.clean = bool(second & 0x08000000)
            self.no_io_error = bool(second & 0x04000000)
            if require_clean and not (self.clean and self.no_io_error):
                raise DiskError('disk lacks clean/no-I/O-error status after shutdown')
            self.root_chain = self.chain(root, max_bytes=MAX_FILE_BYTES)
            directory = b''.join(self.cluster(cluster) for cluster in self.root_chain)
            self.directory = directory
            self.entries = []
            ended = False
            for offset in range(0, len(directory), 32):
                entry = directory[offset:offset + 32]
                if entry[0] == 0:
                    ended = True
                    break
                if entry[0] == 0xe5 or entry[11] & 15 == 15 or entry[11] & 8:
                    continue
                raw_name = entry[:11]
                if raw_name[0] == 5:
                    raw_name = b'\xe5' + raw_name[1:]
                cluster = ((struct.unpack_from('<H', entry, 20)[0] << 16)
                           | struct.unpack_from('<H', entry, 26)[0]) & 0x0fffffff
                physical = self.cluster_offset(self.root_chain[offset // self.cluster_bytes]) + offset % self.cluster_bytes
                self.entries.append(dict(raw_name=raw_name, attributes=entry[11], first_cluster=cluster,
                                         size=struct.unpack_from('<I', entry, 28)[0], directory_offset=physical,
                                         raw_entry=entry))
            self.directory_end_marker = ended
        except Exception:
            self.stream.close()
            raise

    def _read(self, offset: int, count: int) -> bytes:
        if offset < 0 or count < 0 or offset > self.image_bytes - count:
            raise DiskError('read escaped raw image')
        self.stream.seek(offset)
        data = self.stream.read(count)
        if len(data) != count:
            raise DiskError('short raw image read')
        return data

    def cluster_offset(self, cluster: int) -> int:
        if not 2 <= cluster < self.geometry['cluster_count'] + 2:
            raise DiskError('cluster number outside data area')
        return (self.geometry['first_data_sector'] + (cluster - 2) * self.geometry['sectors_per_cluster']) * 512

    def cluster(self, cluster: int) -> bytes:
        return self._read(self.cluster_offset(cluster), self.cluster_bytes)

    def chain(self, cluster: int, *, max_bytes: int = MAX_FILE_BYTES) -> list[int]:
        result, seen = [], set()
        limit = min(self.geometry['cluster_count'], max_bytes // self.cluster_bytes)
        while True:
            if not 2 <= cluster < self.geometry['cluster_count'] + 2 or cluster in seen:
                raise DiskError('cluster chain is free/reserved/cyclic/out of range')
            if len(result) >= limit:
                raise DiskError('cluster chain exceeds bounded oracle budget')
            seen.add(cluster)
            result.append(cluster)
            following = struct.unpack_from('<I', self.fat, cluster * 4)[0] & 0x0fffffff
            if following >= 0x0ffffff8:
                return result
            if following < 2 or following >= 0x0ffffff0:
                raise DiskError('cluster chain reached free/reserved/bad marker')
            cluster = following

    def entry(self, raw_name: bytes) -> dict | None:
        if len(raw_name) != 11:
            raise ValueError('exact 11-byte short name required')
        matches = [entry for entry in self.entries if entry['raw_name'] == raw_name]
        if len(matches) > 1:
            raise DiskError('ambiguous duplicate short directory name')
        return matches[0] if matches else None

    def file(self, raw_name: bytes, *, max_bytes: int = MAX_FILE_BYTES) -> tuple[bytes, dict]:
        entry = self.entry(raw_name)
        if entry is None:
            raise FileNotFoundError(raw_name.decode('ascii', 'backslashreplace'))
        if entry['attributes'] & 0xd8:
            raise DiskError('target short name is not a regular file')
        if entry['size'] > max_bytes:
            raise DiskError('file exceeds bounded oracle budget')
        if entry['size'] == 0 and entry['first_cluster'] == 0:
            chain = []
        else:
            chain = self.chain(entry['first_cluster'], max_bytes=max_bytes + self.cluster_bytes)
        if len(chain) * self.cluster_bytes < entry['size']:
            raise DiskError('file chain shorter than directory size')
        if set(chain) & set(self.root_chain):
            raise DiskError('file is cross-linked with root directory')
        data = b''.join(self.cluster(cluster) for cluster in chain)[:entry['size']]
        metadata = {key: value for key, value in entry.items() if key not in ('raw_name', 'raw_entry')}
        metadata.update(name=raw_name[:8].decode('ascii', 'backslashreplace').rstrip() + '.'
                        + raw_name[8:].decode('ascii', 'backslashreplace').rstrip(),
                        raw_name_hex=raw_name.hex(), clusters=chain,
                        cluster_offsets=[self.cluster_offset(cluster) for cluster in chain],
                        directory_entry_hex=entry['raw_entry'].hex())
        return data, metadata

    def close(self):
        self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def inspect_disk(path: Path | str, *, require_clean: bool = True) -> dict:
    """JSON-safe raw evidence, both mirrors, both CFGs, and independent choice."""
    slots, records = [], []
    with Fat32Image(path, require_clean=require_clean) as disk:
        for index, name in enumerate(CFG_NAMES):
            entry = disk.entry(name)
            if entry is None:
                records.append(None)
                slots.append(dict(slot=index, present=False, valid=False, error='file absent'))
                continue
            data, metadata = disk.file(name)
            item = dict(slot=index, present=True, **metadata, content_sha256=hashlib.sha256(data).hexdigest(),
                        record_hex=data.hex() if len(data) <= RECORD_SIZE else None)
            records.append(data)
            try:
                item.update(valid=True, record=decode_record(data), error=None)
            except RecordError as exc:
                item.update(valid=False, record=None, error=str(exc))
            slots.append(item)
        if all(item['present'] for item in slots) and set(slots[0]['clusters']) & set(slots[1]['clusters']):
            raise DiskError('preference files share allocated clusters')
        result = dict(path=str(disk.path), image_bytes=disk.image_bytes, geometry=disk.geometry,
                      both_fats_equal=True, fat_sha256=hashlib.sha256(disk.fat).hexdigest(),
                      clean=disk.clean, no_io_error=disk.no_io_error,
                      root_clusters=disk.root_chain, root_sha256=hashlib.sha256(disk.directory).hexdigest(),
                      root_end_marker=disk.directory_end_marker, slots=slots,
                      selection=select_records(*records))
    return result


def _sha256(path: Path, *, mask_offset: int | None = None) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        offset = 0
        for block in iter(lambda: stream.read(1 << 20), b''):
            if mask_offset is not None and offset <= mask_offset < offset + len(block):
                block = bytearray(block)
                block[mask_offset - offset] = 0
            digest.update(block)
            offset += len(block)
    return digest.hexdigest()


def corrupt_cfg_byte(path: Path | str, slot: int, record_offset: int = 104, xor: int = 1,
                     *, destination: Path | str | None = None) -> dict:
    """Flip one real CFG byte on a stopped/reaped guest disk and fsync it.

    Caller owns guest quiescence. Supplying destination preserves the original;
    an existing destination is rejected. No FAT, directory, or peer CFG byte is
    changed. The target must initially be a valid exact 128-byte record.
    """
    if slot not in (0, 1) or not 0 <= record_offset < RECORD_SIZE or not 1 <= xor <= 255:
        raise ValueError('slot/record byte offset/xor mask out of range')
    source = Path(path).resolve()
    before = inspect_disk(source)
    target = before['slots'][slot]
    if not target['present'] or not target['valid']:
        raise RecordError('corruption witness requires an initially valid target record')
    # Reject aliases to any other root entry before touching the disk. Real
    # directory/file lifetime corruption is not a preference-record fallback.
    with Fat32Image(source) as disk:
        own = set(target['clusters'])
        for entry in disk.entries:
            if entry['raw_name'] == CFG_NAMES[slot] or entry['first_cluster'] == 0:
                continue
            other = disk.chain(entry['first_cluster'])
            if own & set(other):
                raise DiskError('target preference file aliases another root entry')
    selected_path = source
    if destination is not None:
        selected_path = Path(destination).resolve()
        if selected_path == source or selected_path.exists():
            raise FileExistsError('destination must be a distinct new evidence image')
        selected_path.parent.mkdir(parents=True, exist_ok=True)
        # Use exclusive creation, not an exists()+overwrite copy race.
        with source.open('rb') as original, selected_path.open('xb') as copied:
            shutil.copyfileobj(original, copied, 1 << 20)
    old_sha = _sha256(selected_path)
    cluster_bytes = before['geometry']['sectors_per_cluster'] * 512
    physical = target['cluster_offsets'][record_offset // cluster_bytes] + record_offset % cluster_bytes
    outside_before = _sha256(selected_path, mask_offset=physical)
    with selected_path.open('r+b') as stream:
        stream.seek(physical)
        old = stream.read(1)
        if len(old) != 1:
            raise DiskError('target byte disappeared')
        stream.seek(physical)
        stream.write(bytes((old[0] ^ xor,)))
        stream.flush()
        os.fsync(stream.fileno())
    after = inspect_disk(selected_path)
    outside_after = _sha256(selected_path, mask_offset=physical)
    if outside_before != outside_after:
        raise DiskError('some byte outside the requested mutation also changed')
    if after['fat_sha256'] != before['fat_sha256'] or after['root_sha256'] != before['root_sha256']:
        raise DiskError('corruption unexpectedly changed FAT/directory bytes')
    if after['slots'][1 - slot].get('content_sha256') != before['slots'][1 - slot].get('content_sha256'):
        raise DiskError('corruption unexpectedly changed the peer CFG')
    wanted = bytearray.fromhex(target['record_hex'])
    wanted[record_offset] ^= xor
    if after['slots'][slot]['record_hex'] != wanted.hex():
        raise DiskError('mutation was not exactly the requested target record byte')
    if after['slots'][slot]['valid']:
        raise DiskError('requested corruption did not invalidate the target record')
    return dict(path=str(selected_path), source_path=str(source), slot=slot, record_offset=record_offset,
                physical_offset=physical, before_byte=old[0], after_byte=old[0] ^ xor,
                sha256_before=old_sha, sha256_after=_sha256(selected_path), requested_record_byte_changes=1,
                all_other_disk_bytes_unchanged=True, all_other_bytes_sha256=outside_after,
                fat_and_directory_unchanged=True, peer_cfg_unchanged=True,
                before=before, after=after)


def _slow_checksum(data: bytes) -> int:
    """Self-test's hand-written recurrence, independent of zlib oracle."""
    fa, fb, ra, rb = 1, 0, 1, 0
    for index in range(128):
        forward = 0 if 104 <= index < 112 else data[index]
        reverse_index = 127 - index
        reverse = 0 if 104 <= reverse_index < 112 else data[reverse_index]
        fa = (fa + forward) % 65521
        fb = (fb + fa) % 65521
        ra = (ra + reverse) % 65521
        rb = (rb + ra) % 65521
    return (rb << 48) | (ra << 32) | (fb << 16) | fa


def _fixture_record(sequence: int, scale: int = 256, accent: int = 0xff224466) -> bytes:
    data = bytearray(128)
    struct.pack_into('<8sIIQQ', data, 0, b'DONGPREF', 1, 128, sequence, 0)
    struct.pack_into('<9I', data, 32, 0xff102030, 0xff203040, 0xffe0e0e0, 0xffa0a0a0,
                     accent, 0xff303030, 0x40000000, 0xff335577, 0xffff3333)
    struct.pack_into('<4Q', data, 72, 7, 8, scale, 140)
    struct.pack_into('<Q', data, 104, _slow_checksum(data))
    return bytes(data)


def _fixture_disk(path: Path) -> None:
    """Hand-authored FAT32 minimum, fragmented root; no production generator."""
    reserved, fat_sectors, clusters = 32, 512, 65525
    first = reserved + 2 * fat_sectors
    boot = bytearray(512)
    boot[:3] = b'\xeb\x58\x90'
    struct.pack_into('<HBHBHHBHHHII', boot, 11, 512, 1, reserved, 2, 0, 0, 0xf8, 0, 1, 1, 0, first + clusters)
    struct.pack_into('<IHHIHH', boot, 36, fat_sectors, 0, 0, 7, 1, 6)
    boot[510:512] = b'\x55\xaa'
    fat = bytearray(fat_sectors * 512)
    for cluster, following in ((0, 0x0ffffff8), (1, 0x0fffffff), (7, 19), (19, 0x0fffffff),
                               (11, 0x0fffffff), (23, 0x0fffffff), (31, 41), (41, 0x0fffffff)):
        struct.pack_into('<I', fat, cluster * 4, following)
    root0, root1 = bytearray(512), bytearray(512)
    for offset in range(0, 512, 32):
        root0[offset] = 0xe5
    root0[0:11] = CFG_NAMES[0]
    root0[11] = 0x0f  # LFN decoy, must not shadow the real short entry.
    root0[32:43] = CFG_NAMES[1]
    root0[43] = 8  # volume label decoy
    for data, offset, name, cluster in ((root0, 96, CFG_NAMES[0], 11), (root1, 0, CFG_NAMES[1], 23)):
        data[offset:offset + 11] = name
        data[offset + 11] = 0x20
        struct.pack_into('<H', data, offset + 26, cluster)
        struct.pack_into('<I', data, offset + 28, 128)
    root1[32:43] = b'CHAIN   BIN'
    root1[43] = 0x20
    struct.pack_into('<H', root1, 32 + 26, 31)
    struct.pack_into('<I', root1, 32 + 28, 700)
    payload = bytes((index * 37 + 11) & 255 for index in range(700))
    with path.open('wb') as stream:
        stream.truncate((first + clusters) * 512)
        for offset, data in ((0, boot), (reserved * 512, fat), ((reserved + fat_sectors) * 512, fat),
                             ((first + 7 - 2) * 512, root0), ((first + 19 - 2) * 512, root1),
                             ((first + 11 - 2) * 512, _fixture_record(1)), ((first + 23 - 2) * 512, _fixture_record(2, 384)),
                             ((first + 31 - 2) * 512, payload[:512]), ((first + 41 - 2) * 512, payload[512:])):
            stream.seek(offset)
            stream.write(data)


def _self_test() -> int:
    evidence = Path(__file__).resolve().parents[1] / 'build/test/desktop-preferences-oracle' / ('selftest-' + uuid.uuid4().hex[:12])
    evidence.mkdir(parents=True)

    class OracleTests(unittest.TestCase):
        def test_record_bytes_checksum_and_constraints(self):
            good = _fixture_record(3, 448)
            self.assertEqual(_slow_checksum(good), checksum(good))
            self.assertEqual((3, 448), (decode_record(good)['sequence'], decode_record(good)['theme']['scale_q8']))
            for offset, value in ((16, 0), (24, 1), (68, 1), (72, 33), (80, 33), (88, 300), (96, 1001), (112, 1)):
                bad = bytearray(good)
                struct.pack_into('<Q' if offset not in (68, 112) else '<I', bad, offset, value)
                struct.pack_into('<Q', bad, 104, _slow_checksum(bad))
                with self.subTest(offset=offset), self.assertRaises(RecordError):
                    decode_record(bad)
            for offset, color in ((32, 0x80102030), (36, 0x80102030), (56, 0x10203040)):
                bad = bytearray(good)
                struct.pack_into('<I', bad, offset, color)
                struct.pack_into('<Q', bad, 104, _slow_checksum(bad))
                with self.subTest(color_offset=offset), self.assertRaises(RecordError):
                    decode_record(bad)
            for offset in range(128):
                for bit in range(8):
                    bad = bytearray(good)
                    bad[offset] ^= 1 << bit
                    with self.subTest(byte=offset, bit=bit), self.assertRaises(RecordError):
                        decode_record(bad)

        def test_selection_unsigned_ties_and_invalid_fallback(self):
            a, b = _fixture_record(1), _fixture_record(2, 512)
            self.assertEqual(1, select_records(a, b)['slot'])
            self.assertEqual(0, select_records(a, None)['slot'])
            self.assertEqual(0, select_records(a, a)['slot'])
            self.assertEqual('conflict', select_records(a, _fixture_record(1, 320))['status'])
            self.assertEqual('no_valid_record', select_records(None, b'bad')['status'])
            self.assertEqual(0, select_records(_fixture_record((1 << 64) - 1), b)['slot'])

        def test_fragmented_root_raw_mirrors_and_one_byte_fallback(self):
            image = evidence / 'original.img'
            _fixture_disk(image)
            before = inspect_disk(image)
            self.assertEqual([7, 19], before['root_clusters'])
            self.assertEqual(1, before['selection']['slot'])
            self.assertEqual([11], before['slots'][0]['clusters'])
            self.assertEqual([23], before['slots'][1]['clusters'])
            with Fat32Image(image) as disk:
                payload, entry = disk.file(b'CHAIN   BIN')
                self.assertEqual([31, 41], entry['clusters'])
                self.assertEqual(bytes((index * 37 + 11) & 255 for index in range(700)), payload)
            corrupt = corrupt_cfg_byte(image, 1, destination=evidence / 'corrupted-newest.img')
            self.assertEqual(0, corrupt['after']['selection']['slot'])
            self.assertEqual(1, corrupt['after']['selection']['record']['sequence'])
            self.assertEqual(before, inspect_disk(image))
            (evidence / 'corruption.json').write_text(json.dumps(corrupt, indent=2), encoding='utf-8')
            mismatch = evidence / 'bad-mirror.img'
            shutil.copyfile(image, mismatch)
            with mismatch.open('r+b') as stream:
                stream.seek((32 + 512) * 512 + 11 * 4)
                stream.write(b'\x00')
            with self.assertRaisesRegex(DiskError, 'mirrors'):
                inspect_disk(mismatch)
            cycle = evidence / 'cyclic-root.img'
            shutil.copyfile(image, cycle)
            with cycle.open('r+b') as stream:
                for sector in (32, 32 + 512):
                    stream.seek(sector * 512 + 19 * 4)
                    stream.write(struct.pack('<I', 7))
            with self.assertRaisesRegex(DiskError, 'cyclic'):
                inspect_disk(cycle)

    start = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OracleTests))
    (evidence / 'result.json').write_text(json.dumps(dict(passed=result.wasSuccessful(), tests=result.testsRun,
        failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
        elapsed_seconds=time.monotonic() - start, module_sha256=_sha256(Path(__file__))), indent=2), encoding='utf-8')
    print('evidence:', evidence)
    return 0 if result.wasSuccessful() else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path, nargs='?')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--corrupt-slot', type=int, choices=(0, 1))
    parser.add_argument('--record-offset', type=int, default=104)
    parser.add_argument('--xor', type=lambda value: int(value, 0), default=1)
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    if args.image is None:
        parser.error('image or --self-test required')
    result = (inspect_disk(args.image) if args.corrupt_slot is None else
              corrupt_cfg_byte(args.image, args.corrupt_slot, args.record_offset, args.xor, destination=args.destination))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
