"""Image contract tests and native execution of the actual boot crypto/decoder."""

from __future__ import annotations

import ctypes
import hashlib
import importlib.util
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


image = import_file("mkimage", ROOT / "tools/mkimage.py")
build = import_file("image_build_helpers", ROOT / "tools/build.py")


def corrupted_headers(original):
    """Mutations cover every field, integer limits, and exact file bounds."""
    for offset, value in [(0, b"BADMAGIC"), (8, struct.pack("<I", 2)),
                          (12, struct.pack("<I", 79)), (16, struct.pack("<Q", 0)),
                          (16, struct.pack("<Q", 2**64 - 1)),
                          (24, struct.pack("<Q", 0)),
                          (24, struct.pack("<Q", image.MAX_RAW_SIZE + 1)),
                          (32, struct.pack("<Q", 0x80000000)),
                          (40, struct.pack("<Q", 1)),
                          (48, struct.pack("<Q", 0)), (56, b"\x01"),
                          (64, b"\x01"), (79, b"\x01")]:
        changed = bytearray(original)
        changed[offset:offset + len(value)] = value
        yield bytes(changed)
    yield original[:79]
    yield original[:-1]
    yield original + b"\x00"


def invalid_blocks():
    return [
        (b"", 0),                         # no final token
        (b"\xf0", 15),                   # missing literal extension
        (b"\xf0\xff", 300),             # truncated continuation
        (b"\x20x", 2),                   # truncated literals
        (b"\x10x", 2),                   # wrong output length
        (b"\x10x\x01", 16),             # truncated offset
        (b"\x10x\x00\x00\x50abcde", 16),  # offset zero
        (b"\x10x\x02\x00\x50abcde", 16),  # offset before output start
        (b"\x1fx\x01\x00", 40),         # missing match extension
        (b"\x1fx\x01\x00\xff", 400),    # truncated match continuation
        (b"\x1fx\x01\x00\x40\x50abcde", 24),  # match beyond output
        (b"\x10x\x01\x00\x10y", 6),    # last match too close to end
        (b"\x1fx\x01\x00\x10\x00", 36),  # final literals shorter than five
        (b"\x1fx\x01\x00\x10", 36),     # no final literal sequence
    ]


class ImageFormatTests(unittest.TestCase):
    def test_roundtrip_and_literal_length_boundaries(self):
        for size in [1, 4, 5, 14, 15, 16, 269, 270, 271, 4096, image.MAX_RAW_SIZE]:
            with self.subTest(size=size):
                raw = bytes(index % 251 for index in range(size))
                packed = image.pack_image(raw)
                self.assertEqual(image.unpack_image(packed, hashlib.sha256(packed).digest()), raw)
                self.assertGreater(len(packed), len(raw))

    def test_invalid_kernel_sizes(self):
        for raw in [b"", bytes(image.MAX_RAW_SIZE + 1)]:
            with self.assertRaises(ValueError):
                image.pack_image(raw)

    def test_every_header_field_and_size_is_validated(self):
        for changed in corrupted_headers(image.pack_image(b"kernel")):
            with self.subTest(header=changed[:80]):
                with self.assertRaises(ValueError):
                    image.unpack_image(changed)

    def test_payload_corruption_rejected_by_hash(self):
        packed = image.pack_image(b"kernel code")
        changed = packed[:-1] + bytes([packed[-1] ^ 0x80])
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            image.unpack_image(changed, hashlib.sha256(packed).digest())

    def test_manifest_binds_whole_file(self):
        packed = image.pack_image(b"kernel code")
        manifest = image.manifest_text(packed)
        expected = ", ".join(f"0x{byte:02x}" for byte in hashlib.sha256(packed).digest())
        self.assertIn("%define IMAGE_EXPECTED_HASH_BYTES " + expected, manifest)
        self.assertIn(f"%define IMAGE_FILE_SIZE {len(packed)}", manifest)
        self.assertIn("%define IMAGE_RAW_SIZE 11", manifest)

    def test_overlapping_match_and_both_length_extensions(self):
        # One literal + 299 repeated bytes + five final literals. Match offset 1
        # intentionally rereads output that was just written by the same match.
        block = b"\x1fa\x01\x00\xff\x19\x50bcdef"
        self.assertEqual(image.lz4_decode(block, 305), b"a" * 300 + b"bcdef")
        literal = bytes(range(256)) + b"a" * 44
        block = b"\xff\xff\x1e" + literal + b"\x2c\x01\xff\x0a\x50vwxyz"
        self.assertEqual(image.lz4_decode(block, 589), literal + literal[:284] + b"vwxyz")

    def test_malformed_lz4_is_rejected(self):
        for block, size in invalid_blocks():
            with self.subTest(block=block, size=size):
                with self.assertRaises(ValueError):
                    image.lz4_decode(block, size)


class NativeImageTests(unittest.TestCase):
    """Assemble the same source as the EFI loader and call it via host ABI."""

    @classmethod
    def setUpClass(cls):
        try:
            nasm = build.find_tool("nasm", "NASM")
            linker = build.find_tool("lld-link", "LLD_LINK") if os.name == "nt" else shutil.which("cc")
        except build.ToolError as exc:
            raise unittest.SkipTest(str(exc))
        if not linker:
            raise unittest.SkipTest("native assembly probe needs a host C linker")
        cls.temp = tempfile.TemporaryDirectory(prefix="dongos-image-")
        directory = Path(cls.temp.name)
        cls.raw = bytes(range(256)) * 3 + b"DongOS P1 native assembly probe"
        cls.packed = image.pack_image(cls.raw)
        (directory / "image_manifest.inc").write_text(image.manifest_text(cls.packed), encoding="ascii")
        obj = directory / ("image.obj" if os.name == "nt" else "image.o")
        command = [nasm, "-f", "win64" if os.name == "nt" else "elf64",
                   "-I", str(directory) + os.sep, "-o", str(obj), str(ROOT / "boot/image.asm")]
        subprocess.run(command, check=True, capture_output=True, text=True)
        functions = ["sha256", "lz4_decode", "image_verify", "image_unpack"]
        if os.name == "nt":
            library = directory / "image.dll"
            command = [linker, "/dll", "/noentry", "/nodefaultlib", "/machine:x64",
                       "/timestamp:0", f"/out:{library}"]
            command.extend(f"/export:{name}" for name in functions)
            command.append(str(obj))
            prefix = ""
        else:
            library = directory / "image.so"
            wrapper = directory / "sysv.asm"
            lines = ["bits 64", "default rel", "section .text"]
            for name in functions:
                lines += [f"extern {name}", f"global probe_{name}", f"probe_{name}:",
                          "sub rsp, 40", "mov r9, rcx", "mov r8, rdx", "mov rdx, rsi",
                          "mov rcx, rdi", f"call {name}", "add rsp, 40", "ret"]
            lines.append("section .note.GNU-stack noalloc noexec nowrite progbits")
            wrapper.write_text("\n".join(lines) + "\n", encoding="ascii")
            wrapper_obj = directory / "sysv.o"
            subprocess.run([nasm, "-f", "elf64", "-o", str(wrapper_obj), str(wrapper)], check=True,
                           capture_output=True, text=True)
            command = [linker, "-shared", "-Wl,-Bsymbolic,-z,noexecstack", "-o", str(library),
                       str(obj), str(wrapper_obj)]
            prefix = "probe_"
        subprocess.run(command, check=True, capture_output=True, text=True)
        cls.lib = ctypes.CDLL(str(library))
        for name in functions:
            fn = getattr(cls.lib, prefix + name)
            fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            if name == "sha256":
                fn.argtypes += [ctypes.c_void_p]
                fn.restype = None
            elif name in ("lz4_decode", "image_unpack"):
                fn.argtypes += [ctypes.c_void_p, ctypes.c_size_t]
                fn.restype = ctypes.c_int
            else:
                fn.restype = ctypes.c_int
            setattr(cls, name, staticmethod(fn))

    @classmethod
    def tearDownClass(cls):
        if os.name == "nt":
            # The DLL has no live pointers after this class; release its file lock.
            free_library = ctypes.windll.kernel32.FreeLibrary
            free_library.argtypes = [ctypes.c_void_p]
            free_library.restype = ctypes.c_int
            free_library(cls.lib._handle)
        cls.temp.cleanup()

    def decode(self, block, size):
        output = ctypes.create_string_buffer(b"\xcc" * (size + 32), size + 32)
        status = self.lz4_decode(block, len(block), ctypes.byref(output, 16), size)
        self.assertEqual(output.raw[:16], b"\xcc" * 16)
        self.assertEqual(output.raw[size + 16:], b"\xcc" * 16)
        return status, output.raw[16:size + 16]

    def test_nist_sha256_vectors_and_padding_boundaries(self):
        vectors = [(b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
                   (b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
                   (b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
                    "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"),
                   (b"a" * 1_000_000,
                    "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0")]
        for size in [1, 54, 55, 56, 57, 63, 64, 65, 119, 120, 127, 128, 129, 4097]:
            raw = bytes(index % 251 for index in range(size))
            vectors.append((raw, hashlib.sha256(raw).hexdigest()))
        for raw, digest in vectors:
            with self.subTest(size=len(raw)):
                output = ctypes.create_string_buffer(32)
                self.sha256(raw, len(raw), output)
                self.assertEqual(output.raw.hex(), digest)

    def test_literal_length_boundaries(self):
        for size in [0, 1, 14, 15, 16, 269, 270, 271, 4096, image.MAX_RAW_SIZE]:
            raw = bytes(index % 251 for index in range(size))
            self.assertEqual(self.decode(image.lz4_encode(raw), size), (0, raw))

    def test_overlapping_match_and_extensions(self):
        block = b"\x1fa\x01\x00\xff\x19\x50bcdef"
        self.assertEqual(self.decode(block, 305), (0, b"a" * 300 + b"bcdef"))
        literal = bytes(range(256)) + b"a" * 44
        block = b"\xff\xff\x1e" + literal + b"\x2c\x01\xff\x0a\x50vwxyz"
        self.assertEqual(self.decode(block, 589), (0, literal + literal[:284] + b"vwxyz"))

    def test_malformed_lz4_cannot_write_outside_destination(self):
        for block, size in invalid_blocks():
            with self.subTest(block=block, size=size):
                self.assertEqual(self.decode(block, size)[0], 1)

    def test_native_header_and_loader_bound_hash(self):
        self.assertEqual(self.image_verify(self.packed, len(self.packed)), 0)
        changed = self.packed[:-1] + bytes([self.packed[-1] ^ 0x80])
        self.assertEqual(self.image_verify(changed, len(changed)), 1)
        for changed in corrupted_headers(self.packed):
            self.assertEqual(self.image_verify(changed, len(changed)), 1)
            output = ctypes.create_string_buffer(len(self.raw))
            self.assertEqual(self.image_unpack(changed, len(changed), output, len(self.raw)), 1)
        output = ctypes.create_string_buffer(len(self.raw))
        self.assertEqual(self.image_unpack(self.packed, len(self.packed), output, len(self.raw) - 1), 1)
        self.assertEqual(self.image_unpack(self.packed, len(self.packed), output, len(self.raw)), 0)
        self.assertEqual(output.raw, self.raw)

    def test_small_random_blocks_match_host_reference_without_guard_damage(self):
        random_source = random.Random(0xD06)
        for _ in range(500):
            block = random_source.randbytes(random_source.randrange(1, 48))
            size = random_source.randrange(64)
            try:
                expected = (0, image.lz4_decode(block, size))
            except ValueError:
                expected = None
            actual = self.decode(block, size)
            if expected is None:
                self.assertEqual(actual[0], 1)
            else:
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
