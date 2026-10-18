"""Independent Python-reference checks for core.utf8."""
from __future__ import annotations

import codecs
import os
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[2]
STD = ROOT / "lang" / "std"


def wrapper_source():
    return """module probe;
import core.utf8 as utf8;
export("u8_decode_size") fn dsize()usize{return sizeof(utf8.Decode);}
export("u8_scalar_off") fn soff()usize{return offsetof(utf8.Decode,scalar);}
export("u8_width_off") fn woff()usize{return offsetof(utf8.Decode,width);}
export("u8_decode") fn dec(bytes:[]const u8,start:usize,out:*utf8.Decode)bool{unsafe{return utf8.decode(bytes,start,out);}}
export("u8_encode") fn enc(scalar:u32,output:[]u8,written:*usize)bool{unsafe{return utf8.encode(scalar,output,written);}}
export("u8_validate") fn val(bytes:[]const u8)bool{return utf8.validate(bytes);}
"""


def py_decode_one(data, start):
    """Independent strict reference: decode exactly one scalar at start."""
    if start >= len(data):
        return (0, 0, 0)
    for w in (1, 2, 3, 4):
        if start + w > len(data):
            continue
        try:
            text = data[start:start + w].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if len(text) == 1:
            return (1, w, ord(text))
    return (0, 0, 0)


def py_validate(data):
    try:
        data.decode("utf-8")
        return 1
    except UnicodeDecodeError:
        return 0


INVALID_SEQUENCES = [
    b"\x80", b"\xbf", b"\xc0", b"\xc1", b"\xf5", b"\xf8", b"\xfe", b"\xff",
    b"\xc2", b"\xdf", b"\xe0", b"\xe0\xa0", b"\xed", b"\xed\xa0",
    b"\xf0", b"\xf0\x90", b"\xf0\x90\x80", b"\xf4", b"\xf4\x8f", b"\xf4\x8f\xbf",
    b"\xc0\x80", b"\xc1\xbf", b"\xe0\x80\x80", b"\xe0\x9f\xbf",
    b"\xf0\x80\x80\x80", b"\xf0\x8f\xbf\xbf",
    b"\xed\xa0\x80", b"\xed\xbf\xbf", b"\xed\xad\xbf",
    b"\xf4\x90\x80\x80", b"\xf5\x80\x80\x80", b"\xf7\xbf\xbf\xbf",
    b"\xc2\x7f", b"\xe0\xa0\x7f", b"\xf0\x90\x80\x7f",
    b"\xe1\x41\x80", b"\xf1\x80\x41\x80",
]


def build_expected(directory):
    valid = []
    for scalar in range(0x110000):
        if 0xD800 <= scalar <= 0xDFFF:
            continue
        raw = chr(scalar).encode("utf-8")
        valid.append((scalar, len(raw), raw + b"\x00" * (4 - len(raw))))
    full = directory / "full.bin"
    full.write_bytes(b"".join(struct.pack("<IB4s", s, w, b) for s, w, b in valid))

    pairs = directory / "pairs.bin"
    out = bytearray()
    for b0 in range(256):
        for b1 in range(256):
            data = bytes([b0, b1])
            ok, width, scalar = py_decode_one(data, 0)
            out.append(ok)
            out.append(width)
            out += struct.pack("<I", scalar)
            out.append(py_validate(data))
    pairs.write_bytes(bytes(out))

    invalid = directory / "invalid.bin"
    out = bytearray()
    for seq in INVALID_SEQUENCES:
        assert len(seq) <= 8
        out.append(len(seq))
        out += seq + b"\x00" * (8 - len(seq))
    invalid.write_bytes(bytes(out))
    single = directory / "single.bin"
    out = bytearray()
    for b in range(256):
        data = bytes([b])
        ok, width, scalar = py_decode_one(data, 0)
        out.append(b)
        out.append(ok)
        out.append(width)
        out += struct.pack("<I", scalar)
        out.append(py_validate(data))
    single.write_bytes(bytes(out))

    rnd = directory / "random.bin"
    rng = random.Random(0x5EED5EED)
    out = bytearray()
    for _ in range(2500):
        length = rng.randrange(0, 17)
        data = bytes(rng.randrange(256) for _ in range(length))
        ok, width, scalar = py_decode_one(data, 0)
        out.append(length)
        out += data + b"\x00" * (16 - len(data))
        out.append(py_validate(data))
        out.append(ok)
        out.append(width)
        out += struct.pack("<I", scalar)
    rnd.write_bytes(bytes(out))

    return full, pairs, invalid, single, rnd, len(valid), len(INVALID_SEQUENCES)


C_SOURCE = (Path(__file__).parent / "std_utf8_probe.c").read_text(encoding="utf-8")


class StdUtf8Tests(unittest.TestCase):
    def test_module_compiles_and_assembles(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("assembly checks require NASM")
        compiled = compile_file(STD / "core" / "utf8.dg", roots=[STD])
        self.assertEqual(["core.utf8"], compiled.manifest()["modules"])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asm = directory / "utf8.asm"
            asm.write_text(compiled.assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(directory / (object_format + ".o")), str(asm)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)

    def _build_and_run(self, mode, directory, roots, tag):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        entry = Path(roots[0]) / "probe.dg"
        entry.write_text(wrapper_source(), encoding="utf-8")
        compiled = compile_file(entry, roots=roots, mode=mode)
        asm = directory / ("probe-" + tag + ".asm")
        obj = directory / ("probe-" + tag + ".o")
        exe = directory / ("probe-" + tag + (".exe" if os.name == "nt" else ""))
        asm.write_text(compiled.assembly, encoding="utf-8")
        object_format = "win64" if os.name == "nt" else "elf64"
        r = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(obj), str(asm)], capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stderr)
        r = subprocess.run([cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", str(directory / "probe.c"), str(obj), "-o", str(exe)], capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stderr)
        return subprocess.run([str(exe), str(directory / "full.bin"), str(directory / "pairs.bin"), str(directory / "invalid.bin"), str(directory / "single.bin"), str(directory / "random.bin")], capture_output=True, text=True, timeout=300)

    def test_native_utf8(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native core.utf8 checks require NASM and a SysV-capable GCC host compiler")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "probe.c").write_text(C_SOURCE, encoding="utf-8")
            full, pairs, invalid, single, rnd, nvalid, ninvalid = build_expected(directory)
            self.assertEqual(1112064, nvalid)
            self.assertTrue(ninvalid >= 30)
            self.assertEqual(256 * 8, single.stat().st_size)
            self.assertEqual(2500 * 24, rnd.stat().st_size)
            roots_dir = directory / "roots"
            roots_dir.mkdir()
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    result = self._build_and_run(mode, directory, [roots_dir, STD], mode)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("native core.utf8 probes passed", result.stdout)

    def test_negative_controls(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("negative controls require NASM and a C compiler")

        def bad_allow_surrogates(src):
            return src.replace("        if b0 == 0xed && b1 >= 0xa0 { return 0; }", "        if false { return 0; }")

        def bad_early_written(src):
            return src.replace(
                "pub unsafe fn encode(scalar: u32, output: []u8, written: *usize) bool {\n    let s: u32 = scalar;",
                "pub unsafe fn encode(scalar: u32, output: []u8, written: *usize) bool {\n    unsafe { (*written) = 4; }\n    let s: u32 = scalar;")

        cases = [("bad-allow-surrogates", bad_allow_surrogates), ("bad-early-written", bad_early_written)]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "probe.c").write_text(C_SOURCE, encoding="utf-8")
            build_expected(directory)
            for label, mutation in cases:
                source = (STD / "core" / "utf8.dg").read_text(encoding="utf-8")
                mutated = mutation(source)
                self.assertNotEqual(source, mutated, "mutation must change the module")
                for mode in ("debug", "release"):
                    with self.subTest(control=label, mode=mode):
                        root = directory / ("root-" + label + "-" + mode)
                        (root / "core").mkdir(parents=True)
                        (root / "core" / "utf8.dg").write_text(mutated, encoding="utf-8")
                        result = self._build_and_run(mode, directory, [root], label + "-" + mode)
                        self.assertEqual(1, result.returncode, "control must be rejected: " + label + "\n" + result.stdout + result.stderr)
                        self.assertIn("check failed", result.stderr)
                        self.assertNotIn("panic", result.stderr)


if __name__ == "__main__":
    unittest.main()
