"""Read defined symbols from an ELF64 little-endian x86-64 symbol table."""
from pathlib import Path
import struct


def read_elf_symbols(path: Path) -> dict[str, int]:
    data = Path(path).read_bytes()

    def span(offset, size):
        if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
            raise ValueError("truncated or invalid ELF table")
        return data[offset:offset + size]

    span(0, 64)
    if data[:7] != b"\x7fELF\x02\x01\x01" or struct.unpack_from("<H", data, 18)[0] != 62:
        raise ValueError("expected little-endian x86-64 ELF64")
    shoff = struct.unpack_from("<Q", data, 40)[0]
    stride, count = struct.unpack_from("<HH", data, 58)
    if stride < 64 or not count:
        raise ValueError("ELF has no supported section table")
    span(shoff, stride * count)
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * stride) for i in range(count)]
    result = {}
    for section in sections:
        if section[1] != 2:
            continue
        offset, size, link, entry_size = section[4], section[5], section[6], section[9]
        if link >= count or entry_size < 24 or size % entry_size or sections[link][1] != 3:
            raise ValueError("invalid ELF symbol/string table")
        span(offset, size)
        strings = span(sections[link][4], sections[link][5])
        for cursor in range(offset, offset + size, entry_size):
            name, _, _, index, value, _ = struct.unpack_from("<IBBHQQ", data, cursor)
            if not name or not index:
                continue
            if name >= len(strings) or b"\0" not in strings[name:]:
                raise ValueError("invalid ELF symbol name")
            text = strings[name:strings.index(0, name)].decode("utf-8")
            if text in result and result[text] != value:
                raise ValueError(f"ambiguous ELF symbol {text!r}")
            result[text] = value
    if not result:
        raise ValueError("ELF has no defined symbols")
    return result
