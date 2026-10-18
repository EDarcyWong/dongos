#!/usr/bin/env python3
"""Pack an explicitly supplied OFL Noto CJK SC font into DGFONT01 atlases.

No fonts are downloaded or discovered in system directories. The source font,
matching OFL license and source URL must be supplied by the caller. Commercial
Windows fonts are deliberately outside this redistributable asset pipeline.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct


def codepoints() -> list[int]:
    """ASCII printable, every valid GB2312 double-byte character, and U+FFFD."""
    chinese = set()
    for lead in range(0xA1, 0xF8):
        for tail in range(0xA1, 0xFF):
            try:
                chinese.add(ord(bytes((lead, tail)).decode('gb2312')))
            except UnicodeDecodeError:
                pass
    if len(chinese) != 7445:
        raise ValueError('host GB2312 codec does not contain the required 7445 characters')
    return sorted(chinese | set(range(0x20, 0x7F)) | {0xFFFD})


def encode_atlas(glyphs: list[dict], *, pixel_size: int, ascent: int, descent: int) -> bytes:
    """Deterministic format encoder, independently readable by gfx.atlas."""
    if not 1 <= len(glyphs) <= 65536 or not 1 <= pixel_size <= 128:
        raise ValueError('bounded nonempty glyph list and pixel size required')
    if not (0 <= ascent <= 512 and 0 <= descent <= 512 and ascent + descent):
        raise ValueError('invalid font vertical metrics')
    records, bitmaps = bytearray(), bytearray()
    previous = -1
    for glyph in glyphs:
        cp, width, height = glyph['codepoint'], glyph['width'], glyph['height']
        bx, by, advance = glyph['bearing_x'], glyph['bearing_y'], glyph['advance_q6']
        bitmap = bytes(glyph['bitmap'])
        if not (previous < cp <= 0x10FFFF and not 0xD800 <= cp <= 0xDFFF):
            raise ValueError('glyph codepoints must be unique, sorted Unicode scalars')
        if not (0 <= width <= 256 and 0 <= height <= 256 and len(bitmap) == width * height):
            raise ValueError('glyph bitmap dimensions or byte count invalid')
        if (width == 0) != (height == 0) or not (-32768 <= bx <= 32767 and -32768 <= by <= 32767 and -65536 <= advance <= 65536):
            raise ValueError('invalid empty glyph or metrics')
        records += struct.pack('<IHHhhiIHHQ', cp, width, height, bx, by, advance, len(bitmaps), width, 0, 0)
        bitmaps += bitmap
        previous = cp
    bitmap_start = 48 + len(records)
    if bitmap_start + len(bitmaps) > 64 << 20:
        raise ValueError('atlas exceeds 64MiB format bound')
    header = struct.pack('<8s7IiiI', b'DGFONT01', 1, 48, len(glyphs), pixel_size,
                         48, bitmap_start, len(bitmaps), ascent, descent, 0)
    return header + records + bitmaps


def pack(font_path: Path, license_path: Path, output: Path, *, sizes=(14, 16, 20, 24, 28, 32), source_url: str):
    from PIL import Image, ImageDraw, ImageFont, features
    from fontTools.ttLib import TTFont
    if not features.check('freetype2'):
        raise ValueError('Pillow must include FreeType support')
    font_bytes, license_bytes = font_path.read_bytes(), license_path.read_bytes()
    license_text = license_bytes.decode('utf-8-sig')
    if 'SIL OPEN FONT LICENSE' not in license_text or 'Version 1.1' not in license_text:
        raise ValueError('provide the upstream SIL OFL 1.1 license text')
    if not source_url.startswith(('https://github.com/notofonts/', 'https://raw.githubusercontent.com/notofonts/')):
        raise ValueError('explicit official Noto source URL required')
    with TTFont(font_path) as font:
        names = {record.toUnicode() for record in font['name'].names if record.nameID in (1, 4, 6)}
        copyrights = sorted({record.toUnicode() for record in font['name'].names if record.nameID == 0})
        trademarks = sorted({record.toUnicode() for record in font['name'].names if record.nameID == 7})
        if not any('Noto' in name and ('CJK SC' in name or 'CJKsc' in name) for name in names):
            raise ValueError('only explicit Noto CJK SC source fonts are accepted')
        cmap = font.getBestCmap()
        points = codepoints()
        # The upstream CJK font can omit U+FFFD while covering every planned
        # character. Supply our own explicit box glyph in that case; never
        # silently claim that a missing GB2312 character was rasterized.
        generated_replacement = 0xFFFD not in cmap
        missing = [cp for cp in points if cp not in cmap and cp != 0xFFFD]
        if missing:
            raise ValueError(f'source font lacks {len(missing)} required glyphs, first U+{missing[0]:04X}')
    sizes = tuple(sizes)
    if not sizes or len(set(sizes)) != len(sizes) or any(size not in (14, 16, 20, 24, 28, 32) for size in sizes):
        raise ValueError('choose unique planned sizes 14,16,20,24,28,32')
    # Validate provenance before creating output assets. Never overwrite a pack.
    output.mkdir(parents=True, exist_ok=False)
    (output / 'OFL.txt').write_bytes(license_bytes)
    # The upstream license can be generic; keep the actual font's embedded
    # copyright/trademark notices alongside every derived atlas pack as well.
    notices = '\n'.join(copyrights + trademarks) + '\n\nDerived Dong CJK SC bitmap atlases; licensed under SIL OFL 1.1.\n'
    (output / 'COPYRIGHT.txt').write_text(notices, encoding='utf-8')
    assets = []
    for size in sizes:
        font = ImageFont.truetype(str(font_path), size)
        ascent, descent = font.getmetrics()
        glyphs = []
        for cp in points:
            if cp == 0xFFFD and generated_replacement:
                width, height = max(3, (size + 1) // 2), max(5, size)
                bitmap = bytes(255 if x in (0, width - 1) or y in (0, height - 1) else 0
                               for y in range(height) for x in range(width))
                glyphs.append(dict(codepoint=cp, width=width, height=height, bearing_x=0,
                                   bearing_y=height, advance_q6=(width + 1) * 64, bitmap=bitmap))
                continue
            text = chr(cp)
            left, top, right, bottom = font.getbbox(text, anchor='ls')
            width, height = right - left, bottom - top
            if width == 0 or height == 0:
                width = height = 0
                left = top = 0
                bitmap = b''
            else:
                image = Image.new('L', (width, height))
                ImageDraw.Draw(image).text((-left, -top), text, font=font, fill=255, anchor='ls')
                bitmap = image.tobytes()
            glyphs.append(dict(codepoint=cp, width=width, height=height, bearing_x=left,
                               bearing_y=-top, advance_q6=math.floor(font.getlength(text) * 64 + .5), bitmap=bitmap))
        data = encode_atlas(glyphs, pixel_size=size, ascent=ascent, descent=descent)
        name = f'dong-cjk-sc-{size}.dgfont'
        (output / name).write_bytes(data)
        assets.append(dict(file=name, pixel_size=size, glyphs=len(glyphs), bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    manifest = dict(format='DGFONT01', source_url=source_url, source_file=font_path.name,
                    source_sha256=hashlib.sha256(font_bytes).hexdigest(), license='SIL-OFL-1.1',
                    license_sha256=hashlib.sha256(license_bytes).hexdigest(), family_names=sorted(names),
                    copyrights=copyrights, trademarks=trademarks, derived_family='Dong CJK SC',
                    glyph_repertoire='ASCII-printable + all 7445 GB2312 characters + U+FFFD', assets=assets,
                    replacement_glyph='program-generated box' if generated_replacement else 'upstream U+FFFD',
                    source_font_copied=False, windows_system_fonts_used=False)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', type=Path, required=True)
    parser.add_argument('--license', type=Path, required=True)
    parser.add_argument('--source-url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sizes', default='14,16,20,28')
    args = parser.parse_args(argv)
    result = pack(args.font, args.license, args.output, source_url=args.source_url,
                  sizes=tuple(int(value) for value in args.sizes.split(',')))
    # Keep the CLI usable in a Windows legacy console even when upstream
    # copyright notices contain characters outside its active code page.
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
