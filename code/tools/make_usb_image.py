#!/usr/bin/env python3
"""Create a NEW regular GPT/ESP image from a built ESP, without mounting it.

No physical-disk output is supported. Source names use the deliberately bounded
ASCII 8.3 profile used by DongOS boot artifacts; unsupported names fail closed.
The reader below parses raw GPT/FAT bytes independently of the image writer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import mmap
import os
from pathlib import Path
import re
import stat
import struct
import uuid
import zlib

SECTOR = 512
SIZES = (64, 128, 256, 512)
MAX_FILES = 2048
MAX_DIRECTORIES = 128
MAX_DEPTH = 8
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_BYTES = 96 * 1024 * 1024
REQUIRED = frozenset(('EFI/BOOT/BOOTX64.EFI', 'DONGOS.IMG', 'SERVICES.BIN'))
ESP_GUID = uuid.UUID('c12a7328-f81f-11d2-ba4b-00a0c93ec93b')
SHORT_NAME = re.compile(r'[A-Za-z0-9_$-]{1,8}(?:\.[A-Za-z0-9_$-]{1,3})?\Z', re.ASCII)
RESERVED_NAMES = {'CON', 'PRN', 'AUX', 'NUL', 'CLOCK$',
                  *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}


def _reject_special(path: Path | str) -> Path:
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw or '\0' in raw:
        raise ValueError('invalid ordinary-file path')
    normal = raw.replace('\\', '/')
    if normal.startswith('//') or normal.startswith(('/dev/', '/proc/', '/sys/')):
        raise ValueError('device, network and special paths are not supported')
    value = Path(os.path.abspath(raw))
    for part in value.parts[1:]:
        if part.split('.')[0].upper() in RESERVED_NAMES or ':' in part:
            raise ValueError('reserved device or stream path')
    return value


def _no_links(path: Path, *, directory: bool = False) -> os.stat_result:
    # Inspect lexical ancestors before resolve(), which would hide links.
    for item in reversed((path, *path.parents)):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('symlink/reparse-point paths are not supported')
    info = path.stat()
    wanted = stat.S_ISDIR if directory else stat.S_ISREG
    if not wanted(info.st_mode):
        raise ValueError('expected an ordinary directory' if directory else 'expected a regular file')
    return info


def _short(name: str) -> bytes:
    if not SHORT_NAME.fullmatch(name) or name.split('.')[0].upper() in RESERVED_NAMES:
        raise ValueError('source names must be safe ASCII 8.3 names: ' + repr(name))
    base, _, extension = name.upper().partition('.')
    return base.ljust(8).encode('ascii') + extension.ljust(3).encode('ascii')


def _source(esp: Path) -> dict:
    _no_links(esp, directory=True)
    result: dict[str, dict] = {}
    total = files = directories = 0

    def visit(folder: Path, relative: str, depth: int):
        nonlocal total, files, directories
        if depth > MAX_DEPTH:
            raise ValueError('source directory depth exceeds limit')
        seen = set()
        for child in sorted(folder.iterdir(), key=lambda p: p.name.upper()):
            short = _short(child.name)
            if short in seen:
                raise ValueError('case-insensitive source-name collision')
            seen.add(short)
            info = child.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('source symlinks/reparse points are not supported')
            name = relative + child.name.upper()
            signature = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]
            if stat.S_ISDIR(info.st_mode):
                directories += 1
                if directories > MAX_DIRECTORIES:
                    raise ValueError('source directory count exceeds limit')
                result[name] = dict(kind='directory', signature=signature)
                visit(child, name + '/', depth + 1)
            elif stat.S_ISREG(info.st_mode):
                files += 1
                if files > MAX_FILES or info.st_size > MAX_FILE_BYTES:
                    raise ValueError('source file count/length exceeds limit')
                total += info.st_size
                if total > MAX_SOURCE_BYTES:
                    raise ValueError('source payload exceeds limit')
                flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
                with os.fdopen(os.open(child, flags), 'rb') as stream:
                    opened = os.fstat(stream.fileno())
                    if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        raise ValueError('source file changed while opening')
                    data = stream.read(MAX_FILE_BYTES + 1)
                    closed = os.fstat(stream.fileno())
                if len(data) != info.st_size or [closed.st_dev, closed.st_ino, closed.st_size, closed.st_mtime_ns] != signature:
                    raise ValueError('source file changed while reading')
                result[name] = dict(kind='file', length=len(data), sha256=hashlib.sha256(data).hexdigest(),
                                    signature=signature, data=data)
            else:
                raise ValueError('source tree contains a non-regular object')
    visit(esp, '', 0)
    if not REQUIRED <= result.keys() or any(result[p]['kind'] != 'file' or not result[p]['length'] for p in REQUIRED):
        raise ValueError('built ESP must contain nonempty BOOTX64.EFI, DONGOS.IMG and SERVICES.BIN')
    return result


def _metadata(source: dict) -> dict:
    return {key: {k: v for k, v in value.items() if k != 'data'} for key, value in source.items()}


def _fat_geometry(sectors: int) -> dict:
    fat = 1
    while True:
        clusters = sectors - 32 - 2 * fat
        required = (clusters + 2 + 127) // 128
        if required <= fat:
            break
        fat = required
    clusters = sectors - 32 - 2 * fat
    if not 65525 <= clusters < 0x0ffffff5:
        raise ValueError('partition does not have a valid FAT32 cluster count')
    return dict(sectors=sectors, reserved=32, fat_sectors=fat, clusters=clusters, data_start=32 + 2 * fat)


def _header(current: int, backup: int, entries_lba: int, total: int, disk_guid: uuid.UUID, table: bytes) -> bytes:
    header = bytearray(SECTOR)
    struct.pack_into('<8sIIIIQQQQ16sQIII', header, 0, b'EFI PART', 0x10000, 92, 0, 0,
                     current, backup, 34, total - 34, disk_guid.bytes_le, entries_lba, 128, 128, zlib.crc32(table))
    struct.pack_into('<I', header, 16, zlib.crc32(header[:92]))
    return bytes(header)


def _write_image(stream, source: dict, mib: int) -> None:
    total = mib * 1024 * 1024 // SECTOR
    first, count = 2048, total - 4096
    geometry = _fat_geometry(count)
    digest = hashlib.sha256(json.dumps({p: (v['kind'], v.get('length'), v.get('sha256')) for p, v in source.items()},
                                     sort_keys=True).encode()).hexdigest()
    disk_guid = uuid.uuid5(uuid.NAMESPACE_URL, f'dongos-usb:{mib}:{digest}')
    table = bytearray(128 * 128)
    struct.pack_into('<16s16sQQQ72s', table, 0, ESP_GUID.bytes_le, uuid.uuid5(disk_guid, 'esp').bytes_le,
                     first, first + count - 1, 0, 'DongOS ESP'.encode('utf-16le').ljust(72, b'\0'))
    mbr = bytearray(SECTOR)
    mbr[446:462] = struct.pack('<B3sB3sII', 0, b'\0\x02\0', 0xee, b'\xff\xff\xff', 1, min(total - 1, 0xffffffff))
    mbr[510:512] = b'\x55\xaa'
    stream.truncate(total * SECTOR)
    for lba, data in ((0, mbr), (1, _header(1, total - 1, 2, total, disk_guid, table)), (2, table),
                      (total - 33, table), (total - 1, _header(total - 1, 1, total - 33, total, disk_guid, table))):
        stream.seek(lba * SECTOR)
        stream.write(data)
    boot = bytearray(SECTOR)
    boot[:11] = b'\xeb\x58\x90DONGOS  '
    struct.pack_into('<HBHBHHBHHHII', boot, 11, 512, 1, 32, 2, 0, 0, 0xf8, 0, 63, 255, first, count)
    struct.pack_into('<IHHIHH', boot, 36, geometry['fat_sectors'], 0, 0, 2, 1, 6)
    boot[64], boot[66] = 0x80, 0x29
    struct.pack_into('<I', boot, 67, int(digest[:8], 16))
    boot[71:82], boot[82:90], boot[510:512] = b'DONGOS ESP ', b'FAT32   ', b'\x55\xaa'
    fat = bytearray(geometry['fat_sectors'] * SECTOR)
    struct.pack_into('<II', fat, 0, 0x0ffffff8, 0x0fffffff)
    next_cluster = 2
    allocated: dict[str, list[int]] = {}
    directories = [''] + [p for p, v in source.items() if v['kind'] == 'directory']
    children = {p: [] for p in directories}
    for path in source:
        parent = path.rpartition('/')[0]
        children[parent].append(path)
    for path in directories + [p for p, v in source.items() if v['kind'] == 'file']:
        length = (len(children[path]) + (2 if path else 0) + 1) * 32 if path in children else source[path]['length']
        clusters = math.ceil(length / SECTOR)
        if clusters > geometry['clusters'] - (next_cluster - 2):
            raise ValueError('ESP partition has insufficient free clusters')
        allocated[path] = list(range(next_cluster, next_cluster + clusters))
        next_cluster += clusters
        for index, cluster in enumerate(allocated[path]):
            struct.pack_into('<I', fat, cluster * 4,
                             allocated[path][index + 1] if index + 1 < clusters else 0x0fffffff)

    def write_cluster(cluster: int, data: bytes):
        stream.seek((first + geometry['data_start'] + cluster - 2) * SECTOR)
        stream.write(data.ljust(SECTOR, b'\0'))

    def entry(name: bytes, directory: bool, cluster: int, length: int = 0) -> bytes:
        value = bytearray(32)
        value[:11], value[11] = name, 0x10 if directory else 0x20
        for at in (16, 18, 24):
            struct.pack_into('<H', value, at, 0x21)  # fixed 1980-01-01
        struct.pack_into('<H', value, 20, cluster >> 16)
        struct.pack_into('<HI', value, 26, cluster & 0xffff, length)
        return bytes(value)

    for path in directories:
        data = bytearray()
        if path:
            data += entry(b'.          ', True, allocated[path][0])
            parent = path.rpartition('/')[0]
            data += entry(b'..         ', True, allocated[parent][0] if parent else 0)
        for child in children[path]:
            item = source[child]
            chain = allocated[child]
            data += entry(_short(child.rsplit('/', 1)[-1]), item['kind'] == 'directory',
                          chain[0] if chain else 0, item.get('length', 0))
        data += bytes(32)  # explicit end marker, including a full directory sector
        for index, cluster in enumerate(allocated[path]):
            write_cluster(cluster, data[index * SECTOR:(index + 1) * SECTOR])
    for path, item in source.items():
        if item['kind'] == 'file':
            for index, cluster in enumerate(allocated[path]):
                write_cluster(cluster, item['data'][index * SECTOR:(index + 1) * SECTOR])
    info = bytearray(SECTOR)
    struct.pack_into('<I', info, 0, 0x41615252)
    free = geometry['clusters'] - (next_cluster - 2)
    struct.pack_into('<III', info, 484, 0x61417272, free, next_cluster if free else 0xffffffff)
    struct.pack_into('<I', info, 508, 0xaa550000)
    for relative, data in ((0, boot), (6, boot), (1, info), (7, info), (32, fat), (32 + geometry['fat_sectors'], fat)):
        stream.seek((first + relative) * SECTOR)
        stream.write(data)


def inspect_image(path: Path | str, expected_files: dict | None = None) -> dict:
    """Strict read-only parser. Never calls writer geometry/name/chain helpers.

    expected_files maps canonical slash-separated names to {length,sha256}.
    The GPT headers, both entry tables, FAT mirrors, all allocations, directory
    dot entries, padding and every exact payload are checked from raw bytes.
    """
    image = _reject_special(path)
    info = _no_links(image)
    if info.st_size not in {m * 1024 * 1024 for m in SIZES}:
        raise ValueError('unsupported raw image size')
    with image.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as raw:
        total = len(raw) // 512
        if raw[510:512] != b'\x55\xaa' or raw[446] != 0 or raw[450] != 0xee:
            raise ValueError('invalid protective MBR')
        if struct.unpack_from('<II', raw, 454) != (1, total - 1) or any(raw[462:510]):
            raise ValueError('invalid protective MBR range')
        headers = []
        tables = []
        for lba, backup, table_lba in ((1, total - 1, 2), (total - 1, 1, total - 33)):
            block = bytes(raw[lba * 512:(lba + 1) * 512])
            fields = struct.unpack_from('<8sIIIIQQQQ16sQIII', block)
            magic, revision, length, crc, reserved, current, other, start, stop, guid, entries, count, size, table_crc = fields
            if (magic, revision, length, reserved, current, other, start, stop, entries, count, size) != (
                    b'EFI PART', 0x10000, 92, 0, lba, backup, 34, total - 34, table_lba, 128, 128) or any(block[92:]):
                raise ValueError('invalid GPT header fields')
            clean = bytearray(block[:92])
            clean[16:20] = bytes(4)
            if zlib.crc32(clean) != crc:
                raise ValueError('GPT header CRC mismatch')
            table = bytes(raw[entries * 512:entries * 512 + count * size])
            if zlib.crc32(table) != table_crc:
                raise ValueError('GPT entries CRC mismatch')
            headers.append(dict(lba=lba, header_crc32=crc, entries_crc32=table_crc, disk_guid=str(uuid.UUID(bytes_le=guid))))
            tables.append(table)
        if headers[0]['disk_guid'] != headers[1]['disk_guid'] or tables[0] != tables[1] or any(tables[0][128:]):
            raise ValueError('GPT mirrors or unused entries differ')
        kind, unique, first, last, flags, encoded_name = struct.unpack_from('<16s16sQQQ72s', tables[0])
        if uuid.UUID(bytes_le=kind) != ESP_GUID or unique == bytes(16) or (first, last, flags) != (2048, total - 2049, 0):
            raise ValueError('invalid ESP partition')
        if encoded_name != 'DongOS ESP'.encode('utf-16le').ljust(72, b'\0'):
            raise ValueError('invalid ESP name')
        begin, end = first * 512, (last + 1) * 512
        boot = bytes(raw[begin:begin + 512])
        bps, spc, reserved, copies, roots, small, media, legacy_fat, spt, heads, hidden, sectors = struct.unpack_from('<HBHBHHBHHHII', boot, 11)
        fats, extended, version, root, fsinfo, backup = struct.unpack_from('<IHHIHH', boot, 36)
        if (bps, spc, reserved, copies, roots, small, media, legacy_fat, hidden, sectors, extended, version, root, fsinfo, backup) != (
                512, 1, 32, 2, 0, 0, 0xf8, 0, first, last - first + 1, 0, 0, 2, 1, 6):
            raise ValueError('invalid FAT32 BPB')
        if boot[510:] != b'\x55\xaa' or boot[82:90] != b'FAT32   ' or boot != raw[begin + 6 * 512:begin + 7 * 512]:
            raise ValueError('invalid FAT32 boot mirror/signature')
        if not 1 <= fats <= (sectors - reserved) // 2:
            raise ValueError('FAT32 table bounds')
        clusters = sectors - reserved - 2 * fats
        if not 65525 <= clusters < 0x0ffffff5 or (clusters + 2) * 4 > fats * 512:
            raise ValueError('FAT32 cluster geometry')
        fat_start = begin + reserved * 512
        fat = bytes(raw[fat_start:fat_start + fats * 512])
        if fat != raw[fat_start + fats * 512:fat_start + fats * 1024] or struct.unpack_from('<II', fat) != (0x0ffffff8, 0x0fffffff):
            raise ValueError('FAT mirrors or reserved entries differ')
        if any(fat[(clusters + 2) * 4:]):
            raise ValueError('nonzero unused FAT entries')
        data_start = begin + (reserved + 2 * fats) * 512
        used = set()
        files, directories = {}, {}

        payload_bytes = 0

        def chain(cluster: int, limit: int) -> list[int]:
            result = []
            while True:
                if not 2 <= cluster < clusters + 2 or cluster in used:
                    raise ValueError('invalid/cyclic/cross-linked cluster chain')
                used.add(cluster)
                result.append(cluster)
                if len(result) > limit:
                    raise ValueError('cluster chain exceeds bounded object length')
                value = struct.unpack_from('<I', fat, cluster * 4)[0]
                if value & 0xf0000000:
                    raise ValueError('unsupported high FAT bits')
                if value >= 0x0ffffff8:
                    return result
                cluster = value

        def contents(items: list[int]) -> bytes:
            return b''.join(raw[data_start + (c - 2) * 512:data_start + (c - 1) * 512] for c in items)

        def walk(cluster: int, parent: int, name: str, depth: int):
            nonlocal payload_bytes
            if depth > 8 or len(directories) > 128:
                raise ValueError('directory depth/count exceeds limit')
            links = chain(cluster, (MAX_FILES + MAX_DIRECTORIES + 3 + 15) // 16)
            data = contents(links)
            directories[name] = dict(cluster=cluster, clusters=links)
            seen = set()
            terminated = False
            for offset in range(0, len(data), 32):
                item = data[offset:offset + 32]
                if item[0] == 0:
                    if any(data[offset:]):
                        raise ValueError('nonzero directory tail after end marker')
                    terminated = True
                    break
                if item[0] == 0xe5 or item[11] not in (0x10, 0x20) or item[12] != 0:
                    raise ValueError('unsupported/deleted/LFN directory entry')
                target = struct.unpack_from('<H', item, 20)[0] << 16 | struct.unpack_from('<H', item, 26)[0]
                length = struct.unpack_from('<I', item, 28)[0]
                if name and offset < 64:
                    if item[:11] != (b'.          ' if offset == 0 else b'..         ') or item[11] != 0x10 or length != 0 or target != (cluster if offset == 0 else parent):
                        raise ValueError('invalid directory dot/parent entry')
                    continue
                try:
                    base, extension = item[:8].decode('ascii').rstrip(' '), item[8:11].decode('ascii').rstrip(' ')
                except UnicodeDecodeError as error:
                    raise ValueError('non-ASCII short name') from error
                part = base + ('.' + extension if extension else '')
                if not re.fullmatch(r'[A-Z0-9_$-]{1,8}(?:\.[A-Z0-9_$-]{1,3})?', part, re.ASCII) or part in seen:
                    raise ValueError('invalid/duplicate short name')
                if (base.ljust(8) + extension.ljust(3)).encode('ascii') != item[:11]:
                    raise ValueError('invalid short-name padding')
                seen.add(part)
                full = name + '/' + part if name else part
                if item[11] == 0x10:
                    if length != 0:
                        raise ValueError('directory length must be zero')
                    walk(target, cluster if name else 0, full, depth + 1)
                else:
                    if len(files) >= MAX_FILES or length > MAX_FILE_BYTES or (length == 0) != (target == 0):
                        raise ValueError('invalid file length/cluster/count')
                    payload_bytes += length
                    if payload_bytes > MAX_SOURCE_BYTES:
                        raise ValueError('total payload exceeds supported size')
                    links = chain(target, (length + 511) // 512) if target else []
                    if len(links) != (length + 511) // 512:
                        raise ValueError('file cluster chain length mismatch')
                    payload = contents(links)
                    if any(payload[length:]):
                        raise ValueError('nonzero file-cluster padding')
                    files[full] = dict(length=length, sha256=hashlib.sha256(payload[:length]).hexdigest(),
                                       cluster=target, clusters=links)
            if not terminated or (name and len(data) < 96):
                raise ValueError('missing directory end/dot entries')

        walk(root, 0, '', 0)
        if not REQUIRED <= files.keys() or any(files[p]['length'] == 0 for p in REQUIRED):
            raise ValueError('required boot payload missing')
        for cluster in range(2, clusters + 2):
            value = struct.unpack_from('<I', fat, cluster * 4)[0]
            if (cluster in used) != (value != 0):
                raise ValueError('unreachable allocation or free referenced cluster')
        free = clusters - len(used)
        information = bytes(raw[begin + 512:begin + 1024])
        if information != raw[begin + 7 * 512:begin + 8 * 512] or struct.unpack_from('<I', information)[0] != 0x41615252 or struct.unpack_from('<I', information, 484)[0] != 0x61417272 or struct.unpack_from('<I', information, 508)[0] != 0xaa550000:
            raise ValueError('FSInfo mirror/signature mismatch')
        available, hint = struct.unpack_from('<II', information, 488)
        if available != free or hint != (len(used) + 2 if free else 0xffffffff) or (free and not 2 <= hint < clusters + 2):
            raise ValueError('FSInfo free-space mismatch')
        if expected_files is not None:
            actual = {p: {k: v[k] for k in ('length', 'sha256')} for p, v in files.items()}
            expected = {p: {k: v[k] for k in ('length', 'sha256')} for p, v in expected_files.items()}
            if actual != expected:
                raise ValueError('source payload names/lengths/SHA-256 mismatch')
        digest = hashlib.sha256()
        for offset in range(0, len(raw), 1024 * 1024):
            digest.update(raw[offset:offset + 1024 * 1024])
        return dict(version=1, image=str(image), image_bytes=len(raw), image_sha256=digest.hexdigest(),
                    gpt=dict(primary=headers[0], backup=headers[1], partition_guid=str(uuid.UUID(bytes_le=unique))),
                    esp=dict(first_lba=first, last_lba=last, sectors=sectors, fat_sectors=fats,
                             clusters=clusters, used_clusters=len(used), free_clusters=free,
                             fat_mirrors_equal=True, clean=True), directories=directories, files=files,
                    verified_payloads=expected_files is not None)


def create(esp: Path | str, output: Path | str, size_mib: int = 128) -> dict:
    if type(size_mib) is not int or size_mib not in SIZES:
        raise ValueError('supported image sizes: 64, 128, 256 or 512 MiB')
    source_path, target = _reject_special(esp), _reject_special(output)
    _no_links(source_path, directory=True)
    _no_links(target.parent, directory=True)
    if target.suffix.lower() != '.img' or target == source_path or source_path in target.parents:
        raise ValueError('output must be a new .img file outside the source ESP')
    report = target.with_name(target.name + '.json')
    if target.exists() or target.is_symlink() or report.exists() or report.is_symlink():
        raise FileExistsError('image or manifest already exists; refusing overwrite')
    before = _source(source_path)
    expected = {p: v for p, v in before.items() if v['kind'] == 'file'}
    temporary = target.with_name('.' + target.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary_report = temporary.with_name(temporary.name + '.json')
    published = []
    try:
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
        with os.fdopen(os.open(temporary, flags, 0o600), 'w+b') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('output staging file is not regular')
            _write_image(stream, before, size_mib)
            stream.flush()
            os.fsync(stream.fileno())
        result = inspect_image(temporary, expected)
        after = _source(source_path)
        if _metadata(before) != _metadata(after):
            raise ValueError('source tree changed during image creation')
        result.update(image=str(target), source_esp=str(source_path), sources_unchanged=True,
                      source_files={p: dict(length=v['length'], sha256=v['sha256']) for p, v in expected.items()})
        with temporary_report.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link publication is atomic and fails if a concurrent process
        # created either name. Unlike rename/replace, it cannot overwrite it.
        for staging, destination in ((temporary, target), (temporary_report, report)):
            os.link(staging, destination)
            published.append((staging, destination))
        return result
    except BaseException:
        for staging, destination in reversed(published):
            if destination.exists() and os.path.samestat(staging.stat(), destination.stat()):
                destination.unlink()
        raise
    finally:
        temporary.unlink(missing_ok=True)
        temporary_report.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('esp', type=Path, nargs='?')
    parser.add_argument('output', type=Path, nargs='?')
    parser.add_argument('--size-mib', type=int, choices=SIZES, default=128)
    parser.add_argument('--verify', type=Path, help='read-only validation of an existing image')
    args = parser.parse_args()
    if args.verify is not None:
        if args.esp is not None or args.output is not None:
            parser.error('--verify cannot be combined with source/output')
        result = inspect_image(args.verify)
    elif args.esp is None or args.output is None:
        parser.error('creation requires a built ESP directory and NEW output.img')
    else:
        result = create(args.esp, args.output, args.size_mib)
    summary = {k: result[k] for k in ('image', 'image_bytes', 'image_sha256', 'gpt', 'esp', 'verified_payloads')}
    summary['files'] = {p: {k: v[k] for k in ('length', 'sha256')} for p, v in result['files'].items()}
    summary['directory_count'] = len(result['directories'])
    if args.verify is None:
        summary['manifest'] = result['image'] + '.json'
        summary['sources_unchanged'] = result['sources_unchanged']
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        raise SystemExit('ERROR: ' + str(error))
