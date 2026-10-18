"""Independent C layouts and ELF/COFF relocation checks for static objects."""
from __future__ import annotations

import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool


FIXTURES = Path(__file__).parent
ENTRY = FIXTURES / "globals_probe.dg"


def static_relocation_types(path: Path, object_format: str) -> dict[str, list[int]]:
    """Read the published ELF64/AMD64 COFF formats without compiler helpers."""
    data = path.read_bytes()
    result = {}
    if object_format == "win64":
        machine, count = struct.unpack_from("<HH", data)
        if machine != 0x8664:
            raise AssertionError(f"unexpected COFF machine {machine:#x}")
        optional_header_size = struct.unpack_from("<H", data, 16)[0]
        for index in range(count):
            offset = 20 + optional_header_size + 40 * index
            name = data[offset:offset + 8].split(b"\0", 1)[0].decode("ascii")
            if name not in {".data", ".rodata"}:
                continue
            relocation_start = struct.unpack_from("<I", data, offset + 24)[0]
            relocation_count = struct.unpack_from("<H", data, offset + 32)[0]
            result[name] = [struct.unpack_from("<H", data, relocation_start + 10 * item + 8)[0]
                            for item in range(relocation_count)]
        return result
    if data[:6] != b"\x7fELF\x02\x01":
        raise AssertionError("expected little-endian ELF64")
    section_start = struct.unpack_from("<Q", data, 40)[0]
    section_size, section_count, strings_index = struct.unpack_from("<HHH", data, 58)
    sections = [section_start + index * section_size for index in range(section_count)]
    strings_start = struct.unpack_from("<Q", data, sections[strings_index] + 24)[0]

    def section_name(offset):
        start = strings_start + struct.unpack_from("<I", data, offset)[0]
        return data[start:data.index(0, start)].decode("ascii")

    for offset in sections:
        if struct.unpack_from("<I", data, offset + 4)[0] != 4:  # SHT_RELA
            continue
        target_index = struct.unpack_from("<I", data, offset + 44)[0]
        name = section_name(sections[target_index])
        if name not in {".data", ".rodata"}:
            continue
        start, size = struct.unpack_from("<QQ", data, offset + 24)
        entry_size = struct.unpack_from("<Q", data, offset + 56)[0]
        result[name] = [struct.unpack_from("<Q", data, item + 8)[0] & 0xffff_ffff
                        for item in range(start, start + size, entry_size)]
    return result


class GlobalsNativeTests(unittest.TestCase):
    def assemble(self, nasm, source, output, object_format):
        result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(output), str(source)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_static_layouts_sections_and_no_page_sized_local_frame(self):
        compiled = compile_file(ENTRY, roots=[FIXTURES])
        layouts = {item["full_name"]: item for item in compiled.layout_manifest["types"]}
        expected = {
            "Natural": (16, 4, [0, 4, 8]),
            "Packed": (7, 1, [0, 1, 5]),
            "Nested": (32, 4, [0, 4, 20, 27]),
            "Node": (16, 8, [0, 8]),
            "Page": (4096, 4096, [0]),
        }
        for name, (size, alignment, offsets) in expected.items():
            with self.subTest(name=name):
                actual = layouts["globals_defs." + name]
                self.assertEqual((actual["size"], actual["alignment"]), (size, alignment))
                self.assertEqual([field["offset"] for field in actual["fields"]], offsets)
        for section in (".bss", ".data", ".rodata"):
            self.assertIn("section " + section, compiled.assembly)
        self.assertNotIn("and rsp, -4096", compiled.assembly)
        self.assertNotIn("sub rsp, 4096", compiled.assembly)
        self.assertEqual(compiled.manifest()["modules"], ["globals_defs", "globals_probe"])

    def test_absolute_static_addresses_use_64_bit_elf_and_coff_relocations(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("static relocation inspection requires NASM")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "globals.asm"
            source.write_text(compile_file(ENTRY, roots=[FIXTURES]).assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    output = directory / (object_format + ".o")
                    self.assemble(nasm, source, output, object_format)
                    relocations = static_relocation_types(output, object_format)
                    self.assertIn(".data", relocations)
                    self.assertIn(".rodata", relocations)
                    self.assertGreaterEqual(sum(map(len, relocations.values())), 12)
                    # Both R_X86_64_64 and IMAGE_REL_AMD64_ADDR64 have value 1.
                    for section, types in relocations.items():
                        self.assertTrue(types, section)
                        self.assertEqual(set(types), {1}, f"{object_format} {section}: {types}")

    def test_native_initialized_globals_readonly_storage_and_address_cycles(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("global probes require NASM and a SysV-capable GCC host compiler")
        object_format = "win64" if os.name == "nt" else "elf64"
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    source, obj = directory / (mode + ".asm"), directory / (mode + ".o")
                    observer = directory / "observer.o"
                    executable = directory / (mode + (".exe" if os.name == "nt" else ""))
                    source.write_text(compile_file(ENTRY, roots=[FIXTURES], mode=mode).assembly, encoding="utf-8")
                    self.assemble(nasm, source, obj, object_format)
                    self.assemble(nasm, FIXTURES / "globals_probe.asm", observer, object_format)
                    command = [cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror"]
                    if os.name != "nt":
                        command.append("-no-pie")
                    result = subprocess.run(command + [str(FIXTURES / "globals_probe.c"), str(obj), str(observer),
                                                       "-o", str(executable)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("native initialized globals, readonly aggregates and 64-bit static relocations passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
