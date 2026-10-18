"""Read-only, independent FAT32 tree/LFN oracle for actual guest disk images.

This module has no guest or filesystem implementation imports and never writes
an image. Host-created mutations belong only in the oracle's pure unit tests.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _u16(raw, offset):
    return struct.unpack_from('<H', raw, offset)[0]


def _u32(raw, offset):
    return struct.unpack_from('<I', raw, offset)[0]


def checksum(alias):
    require(len(alias) == 11, 'alias checksum requires eleven bytes')
    value = 0
    for byte in alias:
        value = (((value & 1) << 7) | (value >> 1)) + byte
        value &= 255
    return value


def ascii_key(value):
    return ''.join(chr(ord(c) - 32) if 'a' <= c <= 'z' else c for c in value)


def short_name(entry):
    require(len(entry) == 32, 'incomplete short directory entry')
    raw = bytearray(entry[:11])
    require(raw[0] not in (0, 32, 0xe5), 'invalid first short-name byte')
    if raw[0] == 5:
        raw[0] = 0xe5
    for part in (raw[:8], raw[8:]):
        trimmed = part.rstrip(b' ')
        require(b' ' not in trimmed, 'embedded short-name padding')
        require(all(b >= 32 and b not in b'"*+,./:;<=>?[\\]|' for b in trimmed),
                'illegal short-name byte')
    require(raw[:8].rstrip(b' '), 'empty short basename')
    base, ext = bytes(raw[:8]).rstrip(b' ').decode('cp437'), bytes(raw[8:]).rstrip(b' ').decode('cp437')
    require(entry[12] & ~0x18 == 0, 'reserved short-name NT bits set')
    if entry[12] & 8:
        base = base.lower()
    if entry[12] & 16:
        ext = ext.lower()
    return base + ('.' + ext if ext else '')


def long_name(entries, alias):
    """Decode one complete physical reverse-ordinal group, strictly."""
    require(1 <= len(entries) <= 20, 'LFN slot count outside 1..20')
    pieces = {}
    offsets = (1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30)
    for index, entry in enumerate(entries):
        ordinal = len(entries) - index
        require(len(entry) == 32 and entry[0] == (ordinal | (64 if index == 0 else 0)),
                'LFN ordinal/LAST order differs')
        require(entry[11] == 15 and entry[12] == 0 and entry[26:28] == b'\0\0',
                'LFN attribute/type/first-cluster differs')
        require(entry[13] == checksum(alias), 'LFN checksum differs from following alias')
        pieces[ordinal] = [_u16(entry, at) for at in offsets]
    units = [unit for ordinal in range(1, len(entries) + 1) for unit in pieces[ordinal]]
    if 0 in units:
        end = units.index(0)
        require((len(entries) - 1) * 13 < end <= 255,
                'LFN terminator in redundant/empty group or name too long')
        require(all(unit == 0xffff for unit in units[end + 1:]), 'LFN padding is not FFFF')
        units = units[:end]
    else:
        require(0 < len(units) <= 255, 'unterminated full LFN exceeds 255 UTF-16 units')
    require(0xffff not in units, 'LFN padding before terminator')
    try:
        text = struct.pack('<' + str(len(units)) + 'H', *units).decode('utf-16le', errors='strict')
    except UnicodeDecodeError as error:
        raise ValueError('unpaired LFN UTF-16 surrogate') from error
    require(text not in ('', '.', '..'), 'empty/dot LFN')
    require(all(ord(c) >= 32 and c not in '"*/:<>?\\|' for c in text), 'illegal LFN character')
    return text


class FatTree:
    def __init__(self, raw):
        self.raw = memoryview(raw)
        require(len(raw) >= 512 and len(raw) % 512 == 0, 'incomplete sector image')
        b = self.raw[:512]
        require(bytes(b[510:512]) == b'\x55\xaa', 'BPB boot signature differs')
        require(_u16(b, 11) == 512 and b[16] == 2 and _u16(b, 17) == 0
                and _u16(b, 19) == _u16(b, 22) == _u16(b, 40) == _u16(b, 42) == 0,
                'unsupported FAT32 BPB shape')
        self.spc, self.reserved, self.fatsz = b[13], _u16(b, 14), _u32(b, 36)
        self.total, self.root = _u32(b, 32), _u32(b, 44)
        require(self.spc > 0 and self.spc <= 128 and self.spc & (self.spc - 1) == 0,
                'invalid sectors per cluster')
        require(self.reserved >= 8 and self.fatsz > 0 and self.total * 512 == len(raw),
                'BPB volume size differs from exact image')
        self.data = self.reserved + self.fatsz * 2
        require(self.data < self.total, 'FAT/data geometry overflow')
        self.clusters = (self.total - self.data) // self.spc
        require(65525 <= self.clusters < 0xffffff5 and (self.clusters + 2) * 4 <= self.fatsz * 512,
                'not a bounded FAT32 volume')
        require(2 <= self.root < self.clusters + 2, 'root cluster outside data area')
        fsinfo, backup = _u16(b, 48), _u16(b, 50)
        require(0 < fsinfo < self.reserved and 0 < backup < self.reserved
                and backup + fsinfo < self.reserved, 'invalid backup/FSInfo location')
        require(bytes(b) == self.sector(backup), 'backup BPB differs')
        info = self.sector(fsinfo)
        require(info == self.sector(backup + fsinfo), 'FSInfo mirror differs')
        require((_u32(info, 0), _u32(info, 484), _u32(info, 508))
                == (0x41615252, 0x61417272, 0xaa550000), 'FSInfo signatures differ')
        for at, maximum in ((488, self.clusters), (492, self.clusters + 1)):
            hint = _u32(info, at)
            require(hint == 0xffffffff or (0 if at == 488 else 2) <= hint <= maximum,
                    'FSInfo count/next hint outside data area')
        start = self.reserved * 512
        size = self.fatsz * 512
        fat = self.raw[start:start + size]
        require(fat == self.raw[start + size:start + size * 2], 'two FAT copies differ')
        self.fat = [v[0] & 0xfffffff for v in struct.iter_unpack('<I', fat)]
        require(self.fat[0] == 0xffffff8 and self.fat[1] & 0x3ffffff == 0x3ffffff,
                'FAT reserved entries differ')
        require(self.fat[1] & 0xc000000 == 0xc000000, 'volume not clean/error-free after FLUSH')
        self.owners, self.entries, self.contents = {}, {}, {}
        self.directories, self.crossing_groups = [], []
        self._directory('/', self.root, 0, 0)
        for cluster in range(2, self.clusters + 2):
            require(cluster in self.owners or self.fat[cluster] in (0, 0xffffff7),
                    f'unreachable allocated cluster {cluster}')

    def sector(self, lba):
        require(0 <= lba < self.total, 'sector outside volume')
        return bytes(self.raw[lba * 512:(lba + 1) * 512])

    def chain(self, start, owner):
        if start == 0:
            return []
        chain, seen = [], set()
        cluster = start
        while True:
            require(2 <= cluster < self.clusters + 2, 'cluster pointer outside data area')
            require(cluster not in seen, 'cycle in FAT cluster chain')
            require(cluster not in self.owners, 'cross-linked FAT cluster chain')
            seen.add(cluster)
            self.owners[cluster] = owner
            chain.append(cluster)
            next_cluster = self.fat[cluster]
            if next_cluster >= 0xffffff8:
                return chain
            require(2 <= next_cluster < self.clusters + 2 and next_cluster < 0xffffff0,
                    'free/reserved/bad cluster in reachable chain')
            cluster = next_cluster

    def cluster_bytes(self, cluster):
        lba = self.data + (cluster - 2) * self.spc
        return bytes(self.raw[lba * 512:(lba + self.spc) * 512])

    def _directory(self, path, start, parent, depth):
        require(depth < 128, 'directory depth exceeds bounded traversal')
        chain = self.chain(start, path)
        require(chain, 'directory has no cluster')
        self.directories.append(dict(path=path, clusters=chain))
        raw = b''.join(self.cluster_bytes(cluster) for cluster in chain)
        if path != '/':
            require(raw[:11] == b'.          ' and raw[32:43] == b'..         ',
                    'directory does not begin with dot entries')
        pending, first, names, aliases = [], 0, {}, set()
        for slot in range(len(raw) // 32):
            entry = raw[slot * 32:(slot + 1) * 32]
            if entry[0] == 0:
                require(not pending, 'orphan LFN before end-of-directory marker')
                require(path == '/' or slot >= 2, 'missing dot entries')
                break
            if entry[0] == 0xe5:
                require(not pending, 'orphan LFN before deleted entry')
                continue
            if entry[11] == 15:
                if not pending:
                    first = slot
                pending.append(entry)
                require(len(pending) <= 20, 'excess LFN slots')
                continue
            attr, size = entry[11], _u32(entry, 28)
            cluster = (_u16(entry, 20) << 16) | _u16(entry, 26)
            require(attr & 0xc0 == 0 and attr & 0x18 != 0x18, 'reserved/conflicting attributes')
            if entry[:11] in (b'.          ', b'..         '):
                require(path != '/' and not pending and slot in (0, 1) and attr == 16 and size == 0,
                        'misplaced/malformed dot entry')
                require(entry[:11] == (b'.          ' if slot == 0 else b'..         '),
                        'dot entries out of order')
                expected = start if slot == 0 else parent
                require(cluster == expected or (slot == 1 and parent == self.root and cluster == 0),
                        'dot entry references wrong directory')
                continue
            require(path == '/' or slot >= 2, 'directory must begin with exact . and ..')
            if attr & 8:
                require(path == '/' and not pending and cluster == size == 0, 'invalid volume label')
                continue
            alias = short_name(entry)
            alias_key = ascii_key(alias)
            require(alias_key not in aliases, 'duplicate short aliases in directory')
            aliases.add(alias_key)
            name = long_name(pending, entry[:11]) if pending else alias
            key = ascii_key(name)
            for lookup in {key, alias_key}:
                require(lookup not in names, 'long/short lookup collision in directory')
                names[lookup] = slot
            child = path.rstrip('/') + '/' + name
            require(child not in self.entries, 'duplicate full path')
            record = dict(path=child, name=name, short_name=alias, short_alias_hex=entry[:11].hex(),
                          attributes=attr, size=size, first_cluster=cluster, directory_slot=slot,
                          lfn_slots=len(pending), first_slot=first if pending else slot)
            if pending and first // 16 != slot // 16:
                self.crossing_groups.append(child)
            pending = []
            self.entries[child] = record
            if attr & 16:
                require(size == 0 and cluster >= 2, 'invalid child-directory size/cluster')
                self._directory(child, cluster, start, depth + 1)
            else:
                chain = self.chain(cluster, child)
                needed = (size + self.spc * 512 - 1) // (self.spc * 512)
                require(len(chain) == needed, 'file size and exact allocated chain differ')
                payload = b''.join(self.cluster_bytes(c) for c in chain)[:size]
                record.update(clusters=chain, sha256=hashlib.sha256(payload).hexdigest())
                self.contents[child] = payload
        require(not pending, 'orphan LFN at end of allocated directory chain')

    def report(self):
        return dict(sector_bytes=512, sectors_per_cluster=self.spc, total_sectors=self.total,
                    clusters=self.clusters, root_cluster=self.root, fat_copies_equal=True,
                    clean_shutdown=True, hard_error_free=True,
                    all_allocated_clusters_reachable=True, allocated_clusters=len(self.owners),
                    directories=self.directories, entries=self.entries,
                    lfn_groups_crossing_sector_boundary=self.crossing_groups)


def inspect(path, *, files=None, directories=None, absent=(), require_crossing_lfn=False,
            require_multicluster_file=None, exact_namespace=False):
    """Read entire tree and compare expected names and literal file payloads."""
    path = Path(path)
    raw = path.read_bytes()
    tree = FatTree(raw)
    for name, payload in (files or {}).items():
        require(tree.contents.get(name) == payload, 'raw FAT payload differs: ' + name)
    for name in directories or ():
        require(name in tree.entries and tree.entries[name]['attributes'] & 16,
                'raw FAT directory missing: ' + name)
    for name in absent:
        require(name not in tree.entries, 'removed/rejected name still present: ' + name)
    if exact_namespace:
        require(set(tree.entries) == set(files or {}) | set(directories or ()),
                'actual complete directory tree differs from expected namespace')
    if require_crossing_lfn:
        require(tree.crossing_groups, 'no actual LFN group crossed a 512-byte directory boundary')
    if require_multicluster_file:
        require(len(tree.entries[require_multicluster_file]['clusters']) > 1,
                'actual guest file did not span multiple data clusters')
    result = tree.report()
    result.update(image=str(path.resolve()), image_sha256=hashlib.sha256(raw).hexdigest(),
                  expected_payloads_verified=len(files or {}), expected_directories_verified=len(directories or ()),
                  expected_absent_verified=len(absent), exact_namespace_verified=exact_namespace)
    return result
