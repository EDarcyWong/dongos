"""Pure host negative checks for the actual desktop runner's new evidence."""
import struct
import unittest

from tests.run_desktop_qemu import validate_default_background, validate_font_aperture


class DesktopFontApertureTests(unittest.TestCase):
    def fixture(self, byte_count=2133031):
        # Independent device-table image: one contiguous font payload followed
        # by aliases of its final page, never the next manifest resource.
        root, base, physical = 0x12345000, 0x72000000, 0x50000000
        payload = list(range(physical, physical + byte_count, 4096))
        mapping = payload + [payload[-1]] * (2048 - len(payload))
        entries = {base + i * 4096: pa | 0x8000000000000005 | (0x20 if i % 2 else 0)
                   for i, pa in enumerate(mapping)}
        calls = []

        def pte(actual_root, address):
            self.assertEqual(root, actual_root)
            calls.append(address)
            return entries.get(address, 0)

        return root, base, entries, calls, pte

    def test_five_real_payload_lengths_cover_exactly_2048_pages(self):
        for length, payload_count in ((2133031, 521), (3146806, 769), (4403269, 1076),
                                      (5881701, 1436), (7577425, 1850)):
            with self.subTest(length=length):
                root, base, entries, calls, pte = self.fixture(length)
                evidence = validate_font_aperture(root, base, length, pte)
                self.assertEqual(2048, evidence['page_count'])
                self.assertEqual(payload_count, evidence['payload_pages'])
                self.assertEqual(2048 - payload_count, evidence['repeated_tail_pages'])
                self.assertEqual([entries[base + i * 4096] for i in range(2048)], evidence['raw_ptes'])
                self.assertEqual(2050, len(calls))
                self.assertEqual(set(range(base - 4096, base + 8 * 1024 * 1024 + 4096, 4096)), set(calls))

    def test_invalid_payload_leaf_and_far_tail_are_rejected(self):
        controls = ((0, 0), (17, 2), (33, 1 << 63), (519, 0x18),
                    (2047, 4096), (2046, 4), (777, 1 << 8))
        for index, mask in controls:
            with self.subTest(index=index, mask=mask):
                root, base, entries, _, pte = self.fixture()
                at = base + index * 4096
                entries[at] = entries[at] ^ mask if mask else 0
                with self.assertRaisesRegex(ValueError, 'aperture page|physical payload range'):
                    validate_font_aperture(root, base, 2133031, pte)

    def test_an_adjacent_bundle_resource_is_not_accepted_as_padding(self):
        root, base, entries, _, pte = self.fixture()
        # A mapper that simply extends the physical font span appears correct
        # throughout the old payload-only check, but exposes the next asset.
        entries[base + 521 * 4096] = 0x50209000 | 0x8000000000000005
        with self.assertRaisesRegex(ValueError, 'aperture page.*521'):
            validate_font_aperture(root, base, 2133031, pte)

    def test_guard_and_descriptor_fail_closed(self):
        for side in (-4096, 8 * 1024 * 1024):
            root, base, entries, _, pte = self.fixture()
            entries[base + side] = 0x50000000 | 0x8000000000000005
            with self.assertRaisesRegex(ValueError, 'guard mapped'):
                validate_font_aperture(root, base, 2133031, pte)
        for address, length in ((0x72001000, 2133031), (0x72000000, 47), (0x72000000, 8388609)):
            root, _, _, calls, pte = self.fixture()
            with self.assertRaisesRegex(ValueError, 'descriptor'):
                validate_font_aperture(root, address, length, pte)
            self.assertEqual([], calls)

    def test_current_panel_background_and_taskbar_palette_at_all_scales(self):
        width, height, stride = 1920, 1080, 1920
        for scale in (256, 320, 384, 448, 512):
            with self.subTest(scale=scale):
                image = bytearray(stride * height * 4)
                positions = ((5, 5, 0xff242b3b), (0, 540, 0xff151924),
                             ((175 * scale + 128) // 256, height - (45 * scale + 128) // 256, 0xff242b3b))
                for x, y, argb in positions:
                    struct.pack_into('<I', image, (y * stride + x) * 4, argb)
                result = validate_default_background(image, width, height, stride, scale)
                self.assertEqual([dict(x=x, y=y, argb=argb) for x, y, argb in positions], result)
                x, y, _ = positions[2]
                struct.pack_into('<I', image, (y * stride + x) * 4, 0xff24334a)
                with self.assertRaisesRegex(ValueError, 'palette'):
                    validate_default_background(image, width, height, stride, scale)


if __name__ == '__main__':
    unittest.main()
