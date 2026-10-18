"""Export a checked Dong layout manifest as NASM struc definitions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


def identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", value):
        raise ValueError("NASM interoperability names must be ASCII identifiers")
    return value


def number(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**64:
        raise ValueError("layout sizes and offsets must be unsigned 64-bit integers")
    return value


def generate(manifest: dict, type_name: str, name: str | None = None) -> str:
    if not isinstance(manifest, dict) or manifest.get("schema") != 1 or manifest.get("target") != "x86_64-dongos-elf":
        raise ValueError("unsupported Dong layout manifest")
    types = manifest.get("types")
    if not isinstance(types, list):
        raise ValueError("layout manifest must contain a types list")
    matches = [typ for typ in types if isinstance(typ, dict) and type_name in (typ.get("name"), typ.get("full_name"))]
    if len(matches) != 1:
        raise ValueError("type must match exactly one manifest entry")
    typ = matches[0]
    symbol = identifier(name or typ.get("name"))
    if typ.get("kind") != "struct":
        raise ValueError("NASM struc export currently requires a structure")
    size, alignment = number(typ.get("size")), number(typ.get("alignment"))
    if not size or not alignment or alignment > 4096 or alignment & (alignment - 1) or size % alignment:
        raise ValueError("invalid structure size or alignment")
    fields = typ.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError("structure must have fields")
    # Escape even valid ASCII names: rax/section/etc. are NASM reserved words.
    lines = ["; Generated from Dong compiler layout; do not edit offsets by hand.", f"struc ${symbol}"]
    cursor, seen = 0, set()
    for field in fields:
        if not isinstance(field, dict):
            raise ValueError("invalid field entry")
        field_name = identifier(field.get("name"))
        offset, field_size = number(field.get("offset")), number(field.get("size"))
        if field_name in seen or not field_size or offset < cursor or offset + field_size > size:
            raise ValueError("duplicate, overlapping or out-of-range field")
        seen.add(field_name)
        if offset > cursor:
            lines.append(f"    resb {offset - cursor}")
        lines.append(f"    .{field_name}: resb {field_size}")
        cursor = offset + field_size
    if cursor < size:
        lines.append(f"    resb {size - cursor}")
    lines += ["endstruc", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--type", required=True, dest="type_name")
    parser.add_argument("--name", help="override the NASM structure name")
    args = parser.parse_args()
    if args.manifest.resolve() == args.output.resolve():
        parser.error("output cannot overwrite the layout manifest")
    try:
        contents = generate(json.loads(args.manifest.read_text(encoding="utf-8")), args.type_name, args.name)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(contents, encoding="ascii")
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"gen_offsets: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
