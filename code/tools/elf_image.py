"""Materialize an ELF64 kernel's PT_LOAD memory image, including zero-filled BSS."""

import struct

KERNEL_BASE = 0xffffffff80000000
MAX_KERNEL_SIZE = 2 * 1024 * 1024


def materialize(data: bytes) -> bytes:
    if len(data) < 64 or data[:7] != b"\x7fELF\x02\x01\x01":
        raise ValueError("expected little-endian ELF64")
    header = struct.unpack_from("<HHIQQQIHHHHHH", data, 16)
    kind, machine, version, entry, phoff, _, _, ehsize, phentsize, phnum, *_ = header
    if (kind, machine, version, entry, ehsize, phentsize) != (2, 62, 1, KERNEL_BASE, 64, 56):
        raise ValueError("unsupported ELF64 kernel header or entry")
    if phoff + phentsize * phnum > len(data):
        raise ValueError("truncated program headers")
    segments = []
    for index in range(phnum):
        typ, flags, offset, virtual, physical, filesz, memsz, align = struct.unpack_from(
            "<IIQQQQQQ", data, phoff + index * phentsize)
        if typ != 1 or not memsz:
            continue
        if filesz > memsz or offset + filesz > len(data):
            raise ValueError("invalid load segment file range")
        if virtual < KERNEL_BASE or virtual + memsz > KERNEL_BASE + MAX_KERNEL_SIZE:
            raise ValueError("load segment outside 2 MiB kernel window")
        start = virtual - KERNEL_BASE
        if any(start < end and start + memsz > other for other, end, _ in segments):
            raise ValueError("overlapping load segments")
        segments.append((start, start + memsz, data[offset:offset + filesz]))
    if not segments or min(start for start, _, _ in segments) != 0:
        raise ValueError("kernel has no entry load segment")
    image = bytearray(max(end for _, end, _ in segments))
    for start, _, content in segments:
        image[start:start + len(content)] = content
    return bytes(image)
