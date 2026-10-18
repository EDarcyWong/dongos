"""Actual production compositor graph must link under unchanged PIE policy."""
from pathlib import Path
import struct
import unittest
import uuid

from tools.user_services import ROOT, build_service


def dynamic_tags(raw):
    if raw[:7] != b'\x7fELF\x02\x01\x01':
        raise ValueError('not an actual ELF64 little-endian file')
    if struct.unpack_from('<HH', raw, 16) != (3, 62):
        raise ValueError('service is not an x86-64 PIE')
    offset = struct.unpack_from('<Q', raw, 32)[0]
    stride, count = struct.unpack_from('<HH', raw, 54)
    if stride != 56 or count == 0 or offset + count * stride > len(raw):
        raise ValueError('invalid actual ELF program headers')
    tags = []
    for index in range(count):
        kind, _, at, _, _, size, _, _ = struct.unpack_from('<IIQQQQQQ', raw, offset + index * stride)
        if kind == 2:
            if size % 16 or at + size > len(raw):
                raise ValueError('invalid dynamic table range')
            for tag, value in struct.iter_unpack('<QQ', raw[at:at + size]):
                if tag == 0:
                    break
                tags.append((tag, value))
    if not tags or any(tag == 22 or tag == 30 and value & 4 for tag, value in tags):
        raise ValueError('missing dynamic metadata or forbidden text relocations')
    return tags


class CompositorPieTests(unittest.TestCase):
    def test_actual_service_links_without_readonly_function_relocations(self):
        # One service graph only, no kernel, image, or virtual machine build.
        directory = ROOT / 'build/test/compositor-pie' / ('run-' + uuid.uuid4().hex[:12])
        executable = build_service(ROOT / 'services/desktop/service.dg', directory)
        tags = dynamic_tags(executable.read_bytes())
        self.assertNotIn(22, [tag for tag, _ in tags])
        print('ACTUAL_COMPOSITOR_PIE_LINK ' + str(executable))


if __name__ == '__main__':
    unittest.main(verbosity=2)
