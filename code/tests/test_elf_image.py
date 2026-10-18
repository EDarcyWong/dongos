import struct
import unittest

from tools.elf_image import KERNEL_BASE, materialize


def fixture(content=b"abc", memsz=8):
    header = b"\x7fELF\x02\x01\x01" + bytes(9)
    header += struct.pack("<HHIQQQIHHHHHH", 2, 62, 1, KERNEL_BASE, 64, 0, 0, 64, 56, 1, 0, 0, 0)
    program = struct.pack("<IIQQQQQQ", 1, 5, 120, KERNEL_BASE, KERNEL_BASE, len(content), memsz, 4096)
    return header + program + content


class ElfImageTests(unittest.TestCase):
    def test_bss_is_materialized_as_zero(self):
        self.assertEqual(materialize(fixture()), b"abc" + bytes(5))

    def test_truncated_segment_rejected(self):
        with self.assertRaises(ValueError):
            materialize(fixture()[:-1])

    def test_file_larger_than_memory_rejected(self):
        with self.assertRaises(ValueError):
            materialize(fixture(memsz=2))

    def test_unbounded_segment_rejected(self):
        with self.assertRaises(ValueError):
            materialize(fixture(memsz=0x200001))
