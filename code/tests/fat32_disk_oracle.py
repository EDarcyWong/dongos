"""Independent raw-byte FAT32 tree oracle and deliberately fragmented fixtures.

This reader never imports the Dong FAT implementation or its LFN codec.  It
uses Python's strict UTF-16 decoder and records every allocated cluster owner.
"""
from __future__ import annotations

import struct
from pathlib import Path
from tools.make_fat32_disk import create, SEED

OFFSETS = (1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30)
ROOT_LONG = "跨簇😀独立磁盘验证文件.txt"
DIRECTORY = "文档与 Space"
NESTED = "nested 资料 😀.txt"
EDGE = "目录跨簇长文件名数据.bin"
PAYLOAD = bytes((i * 19 + 37) & 255 for i in range(1300))
NESTED_PAYLOAD = "子目录 UTF-8 / UTF-16 😀\n".encode()
EDGE_PAYLOAD = b"fragmented directory boundary\n"
CHILD_PAYLOAD = bytes((i * 11 + 5) & 255 for i in range(850))


def short(alias: bytes, cluster=0, size=0, attributes=0x20) -> bytes:
    assert len(alias) == 11
    entry = bytearray(32)
    entry[:11] = alias
    entry[11] = attributes
    struct.pack_into("<H", entry, 20, cluster >> 16)
    struct.pack_into("<H", entry, 26, cluster & 65535)
    struct.pack_into("<I", entry, 28, size)
    return bytes(entry)


def checksum(alias: bytes) -> int:
    value = 0
    for byte in alias:
        value = (((value & 1) << 7) + (value >> 1) + byte) & 255
    return value


def long_group(name: str, entry: bytes) -> list[bytes]:
    raw = name.encode("utf-16le", "strict")
    words = list(struct.unpack("<" + "H" * (len(raw) // 2), raw))
    assert 1 <= len(words) <= 255
    slots = (len(words) + 12) // 13
    if len(words) % 13:
        words.append(0)
    words.extend([65535] * (slots * 13 - len(words)))
    result = []
    for ordinal in range(slots, 0, -1):
        item = bytearray(32)
        item[0] = ordinal | (0x40 if ordinal == slots else 0)
        item[11] = 15
        item[13] = checksum(entry[:11])
        for offset, unit in zip(OFFSETS, words[(ordinal - 1) * 13:ordinal * 13]):
            struct.pack_into("<H", item, offset, unit)
        result.append(bytes(item))
    return result + [entry]


def decode_group(slots: list[bytes], alias: bytes) -> str | None:
    """Return only a complete valid adjacent chain; malformed chains fall back."""
    if not slots or len(slots) > 20:
        return None
    for i, item in enumerate(slots):
        ordinal = len(slots) - i | (0x40 if i == 0 else 0)
        if (item[0] != ordinal or item[11] != 15 or item[12]
                or item[13] != checksum(alias) or item[26:28] != b"\0\0"):
            return None
    units = [struct.unpack_from("<H", item, at)[0]
             for item in reversed(slots) for at in OFFSETS]
    if 0 in units:
        end = units.index(0)
        if end <= (len(slots) - 1) * 13 or any(n != 65535 for n in units[end + 1:]):
            return None
        units = units[:end]
    if not 1 <= len(units) <= 255 or 65535 in units:
        return None
    try:
        name = struct.pack("<" + "H" * len(units), *units).decode("utf-16le", "strict")
    except UnicodeError:
        return None
    if name in (".", "..") or any(ord(c) < 32 or c in '"*/:<>?\\|' for c in name):
        return None
    return name


class RawFat:
    def __init__(self, path: Path, *, require_clean=True):
        self.path = Path(path)
        self.stream = self.path.open("rb")
        boot = self.read(0, 512)
        assert boot[510:512] == b"\x55\xaa" and struct.unpack_from("<H", boot, 11)[0] == 512
        self.spc = boot[13]
        self.reserved = struct.unpack_from("<H", boot, 14)[0]
        self.fat_sectors = struct.unpack_from("<I", boot, 36)[0]
        self.total = struct.unpack_from("<I", boot, 32)[0]
        self.root = struct.unpack_from("<I", boot, 44)[0]
        self.data = self.reserved + 2 * self.fat_sectors
        self.clusters = (self.total - self.data) // self.spc
        self.fat = self.read(self.reserved * 512, self.fat_sectors * 512)
        assert self.fat == self.read((self.reserved + self.fat_sectors) * 512, len(self.fat)), "FAT mirror differs"
        assert self.path.stat().st_size == self.total * 512
        self.clean = bool(self.link(1) & 0x08000000)
        if require_clean:
            assert self.clean, "volume is dirty"
        self.owners: dict[int, str] = {}
        self.invalid_lfn = 0
        self.entries: dict[str, dict] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stream.close()

    def read(self, offset, length):
        self.stream.seek(offset)
        data = self.stream.read(length)
        assert len(data) == length, "short raw read"
        return data

    def link(self, cluster):
        return struct.unpack_from("<I", self.fat, cluster * 4)[0] & 0x0fffffff

    def chain(self, start, owner):
        result = []
        seen = set()
        cluster = start
        while cluster:
            assert 2 <= cluster < self.clusters + 2 and cluster not in seen, "invalid or cyclic FAT chain"
            assert cluster not in self.owners, "cross-linked cluster"
            self.owners[cluster] = owner
            seen.add(cluster)
            result.append(cluster)
            following = self.link(cluster)
            if following >= 0x0ffffff8:
                break
            assert 2 <= following < min(0x0ffffff0, self.clusters + 2), "reserved or free FAT link"
            cluster = following
        return result

    def bytes(self, chain):
        return b"".join(self.read((self.data + (c - 2) * self.spc) * 512, self.spc * 512) for c in chain)

    @staticmethod
    def alias(raw):
        if raw[0] == 5:
            raw = b"\xe5" + raw[1:]
        base, extension = raw[:8].rstrip(b" "), raw[8:11].rstrip(b" ")
        return base.decode("ascii", "strict") + (("." + extension.decode("ascii", "strict")) if extension else "")

    def audit(self, *, allow_unreachable=False):
        pending = [("/", self.root, 0, 0)]
        while pending:
            path, start, parent, depth = pending.pop()
            assert depth < 128
            chain = self.chain(start, path)
            raw = self.bytes(chain)
            assert len(raw) // 32 <= 4096
            if path != "/":
                for offset, alias, expected in ((0, b".          ", start), (32, b"..         ", parent)):
                    entry = raw[offset:offset + 32]
                    actual = struct.unpack_from("<H", entry, 20)[0] << 16 | struct.unpack_from("<H", entry, 26)[0]
                    assert entry[:11] == alias and entry[11] == 0x10 and entry[28:32] == bytes(4), "bad dot entry"
                    assert actual in ({0, self.root} if offset == 32 and parent == self.root else {expected}), "wrong dot parent"
            lfn = []
            namespace = {}
            for ordinal in range(len(raw) // 32):
                entry = raw[ordinal * 32:ordinal * 32 + 32]
                if entry[0] == 0:
                    if lfn:
                        self.invalid_lfn += 1
                    break
                if entry[0] == 0xe5:
                    if lfn:
                        self.invalid_lfn += 1
                    lfn = []
                    continue
                if entry[11] & 15 == 15:
                    if entry[0] & 0x40 and lfn:
                        self.invalid_lfn += 1
                        lfn = []
                    lfn.append(entry)
                    continue
                if entry[11] & 8:
                    lfn = []
                    continue
                name = decode_group(lfn, entry[:11])
                if lfn and name is None:
                    self.invalid_lfn += 1
                lfn = []
                if entry[:11] in (b".          ", b"..         "):
                    continue
                alias = self.alias(entry[:11])
                name = name or alias
                for spelling in (alias, name):
                    folded = "".join(chr(ord(c) - 32) if "a" <= c <= "z" else c for c in spelling)
                    assert folded not in namespace or namespace[folded] == ordinal, "shared long/short namespace collision"
                    namespace[folded] = ordinal
                child = path.rstrip("/") + "/" + name
                assert child not in self.entries, "duplicate long name"
                cluster = struct.unpack_from("<H", entry, 20)[0] << 16 | struct.unpack_from("<H", entry, 26)[0]
                size = struct.unpack_from("<I", entry, 28)[0]
                item = dict(alias=alias, raw_alias=entry[:11].hex(), name=name, cluster=cluster,
                            size=size, attributes=entry[11], raw_index=ordinal, chain=[])
                self.entries[child] = item
                if entry[11] & 16:
                    assert cluster >= 2 and size == 0
                    pending.append((child, cluster, self.root if path == "/" else start, depth + 1))
                else:
                    item["chain"] = self.chain(cluster, child)
                    assert len(item["chain"]) * self.spc * 512 >= size, "file chain is too short"
                    item["content"] = self.bytes(item["chain"])[:size]
        unreachable = [c for c in range(2, self.clusters + 2)
                       if self.link(c) not in (0, 0x0ffffff7) and c not in self.owners]
        self.unreachable = unreachable
        if not allow_unreachable:
            assert not unreachable, "allocated unreachable clusters"
        return self.entries


def fixture(path: Path, variant="valid"):
    g = create(path)
    fat = bytearray(g["fat_sectors"] * 512)
    for cluster, following in {0:0x0ffffff8, 1:0x0fffffff, 2:9, 9:0x0fffffff,
            3:0x0fffffff, 4:0x0fffffff, 5:11, 11:0x0fffffff, 6:0x0fffffff,
            7:13, 13:8, 8:0x0fffffff, 10:12, 12:0x0fffffff, 14:0x0fffffff}.items():
        struct.pack_into("<I", fat, cluster * 4, following)
    deleted = bytes([0xe5]) + bytes(31)
    root = [short(b"README  TXT", 3, len(SEED))]
    root += long_group(DIRECTORY, short(b"DOCUME~1   ", 5, 0, 0x10))
    root.extend([deleted] * (15 - len(root)))
    root += long_group(ROOT_LONG, short(b"CROSSC~1TXT", 7, len(PAYLOAD)))
    docs = [short(b".          ", 5, 0, 0x10), short(b"..         ", 0, 0, 0x10)]
    docs += long_group("ChildFolder", short(b"CHILDF~1   ", 6, 0, 0x10))
    docs += long_group(NESTED, short(b"NESTED~1TXT", 4, len(NESTED_PAYLOAD)))
    docs.extend([deleted] * (15 - len(docs)))
    docs += long_group(EDGE, short(b"EDGEBO~1BIN", 14, len(EDGE_PAYLOAD)))
    child = [short(b".          ", 6, 0, 0x10), short(b"..         ", 5, 0, 0x10), short(b"SPARSE  BIN", 10, len(CHILD_PAYLOAD))]
    if variant == "dot-self":
        docs[0] = short(b".          ", 6, 0, 0x10)
    elif variant == "dot-parent":
        child[1] = short(b"..         ", 6, 0, 0x10)
    elif variant == "cross-link":
        child[2] = short(b"SPARSE  BIN", 7, len(CHILD_PAYLOAD))
    elif variant == "ancestor":
        child.append(short(b"ANCESTOR   ", 5, 0, 0x10))
    elif variant == "dir-cycle":
        struct.pack_into("<I", fat, 11 * 4, 5)
    elif variant == "unreachable":
        struct.pack_into("<I", fat, 15 * 4, 0x0fffffff)
    elif variant in ("lfn-checksum", "lfn-ordinal", "lfn-surrogate"):
        index = 15 if variant != "lfn-surrogate" else len(root) - 2
        broken = bytearray(root[index])
        if variant == "lfn-checksum":
            broken[13] ^= 1
        elif variant == "lfn-ordinal":
            broken[0] ^= 1
        else:
            struct.pack_into("<H", broken, 1, 0xdc00)
        root[index] = bytes(broken)
    elif variant == "dirty":
        struct.pack_into("<I", fat, 4, 0x07ffffff)
    elif variant != "valid":
        raise ValueError(variant)
    with path.open("r+b") as disk:
        for copy in range(2):
            disk.seek((g["reserved"] + copy * g["fat_sectors"]) * 512)
            disk.write(fat)
        def save_chain(clusters, content):
            content = content.ljust(len(clusters) * 512, b"\0")
            for i, cluster in enumerate(clusters):
                disk.seek((g["data_start"] + cluster - 2) * 512)
                disk.write(content[i * 512:(i + 1) * 512])
        save_chain([2, 9], b"".join(root))
        save_chain([5, 11], b"".join(docs))
        save_chain([6], b"".join(child))
        save_chain([7, 13, 8], PAYLOAD)
        save_chain([4], NESTED_PAYLOAD)
        save_chain([10, 12], CHILD_PAYLOAD)
        save_chain([14], EDGE_PAYLOAD)
    return g
