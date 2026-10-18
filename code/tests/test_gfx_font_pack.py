"""License-free synthetic coverage of the atlas format and GB2312 repertoire."""
import struct
import unittest
from tools.font_atlas_pack import codepoints, encode_atlas


class FontPackTests(unittest.TestCase):
    def test_complete_repertoire_and_independent_binary_layout(self):
        points = codepoints()
        self.assertEqual(7541, len(points))
        self.assertEqual(7445, sum(cp not in range(0x20, 0x7f) and cp != 0xfffd for cp in points))
        self.assertTrue({0x4e2d, 0x56fd, 0xfffd, ord('A')} <= set(points))
        glyphs = [dict(codepoint=32, width=0, height=0, bearing_x=0, bearing_y=0, advance_q6=192, bitmap=b''),
                  dict(codepoint=65, width=2, height=2, bearing_x=-1, bearing_y=2, advance_q6=160, bitmap=bytes((0, 128, 255, 64)))]
        data = encode_atlas(glyphs, pixel_size=14, ascent=11, descent=3)
        header = struct.pack('<8s7IiiI', b'DGFONT01', 1, 48, 2, 14, 48, 112, 4, 11, 3, 0)
        space = struct.pack('<IHHhhiIHHQ', 32, 0, 0, 0, 0, 192, 0, 0, 0, 0)
        letter = struct.pack('<IHHhhiIHHQ', 65, 2, 2, -1, 2, 160, 0, 2, 0, 0)
        self.assertEqual(header + space + letter + bytes((0, 128, 255, 64)), data)

    def test_invalid_glyph_records_are_rejected(self):
        good = dict(codepoint=65, width=1, height=1, bearing_x=0, bearing_y=1, advance_q6=64, bitmap=b'\xff')
        for changes in (dict(codepoint=0xd800), dict(width=257), dict(height=0), dict(bitmap=b''), dict(advance_q6=65537)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                encode_atlas([dict(good, **changes)], pixel_size=14, ascent=11, descent=3)
        with self.assertRaises(ValueError):
            encode_atlas([good, good], pixel_size=14, ascent=11, descent=3)


if __name__ == '__main__':
    unittest.main()
