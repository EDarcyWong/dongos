"""Pure IST guard policy and independently assembled BSS symbol boundaries."""
from pathlib import Path
import os
import struct
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
from tools.elf_symbols import read_elf_symbols

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent


def compile_probe(mode):
    return compile_file(FIXTURES / "ist_layout_probe.dg",
                        roots=[FIXTURES, ROOT / "kernel", ROOT / "lang/examples", ROOT / "lang/std"], mode=mode)


def coff_symbols(path):
    data = path.read_bytes()
    machine, _, _, offset, count, _, _ = struct.unpack_from("<HHIIIHH", data)
    if machine != 0x8664 or offset + count * 18 + 4 > len(data):
        raise ValueError("invalid x86-64 COFF symbol table")
    strings = data[offset + count * 18:]
    length, = struct.unpack_from("<I", strings)
    if not 4 <= length <= len(strings):
        raise ValueError("invalid COFF string table")
    strings = strings[:length]
    result, index = {}, 0
    while index < count:
        name, value, section, _, _, auxiliary = struct.unpack_from("<8sIhHBB", data, offset + index * 18)
        if name[:4] == bytes(4):
            start, = struct.unpack_from("<I", name, 4)
            if not 4 <= start < len(strings):
                raise ValueError("invalid COFF string offset")
            name = strings[start:strings.index(0, start)]
        else:
            name = name.rstrip(b"\0")
        if section > 0:
            result[name.decode("ascii")] = value
        index += 1 + auxiliary
    return result


class IstLayoutTests(unittest.TestCase):
    def assemble(self, nasm, source, obj, fmt, include=False):
        command = [nasm, "-f", fmt, *nasm_flags(nasm)]
        if include:
            command += ["-I", str(ROOT / "include") + os.sep]
        result = subprocess.run(command + ["-o", str(obj), str(source)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_public_layout_abi_debug_release_elf64_coff(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("ELF/COFF assembly requires NASM")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in ("debug", "release"):
                compiled = compile_probe(mode)
                self.assertIn("boot.ist_layout", compiled.manifest()["modules"])
                layout = next(t for t in compiled.layout_manifest["types"]
                              if t["full_name"] == "boot.memory_resources.Layout")
                self.assertEqual((184, 8), (layout["size"], layout["alignment"]))
                self.assertEqual(list(range(0, 176, 16)) + [176], [f["offset"] for f in layout["fields"]])
                source = directory / (mode + ".asm")
                source.write_text(compiled.assembly, encoding="utf-8")
                for fmt in ("elf64", "win64"):
                    with self.subTest(mode=mode, format=fmt):
                        self.assemble(nasm, source, directory / (mode + fmt + ".o"), fmt)

    def test_cpu_objects_reserve_six_distinct_pages_and_keep_usable_stack_symbols(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("CPU BSS object boundaries require NASM")
        with tempfile.TemporaryDirectory() as temporary:
            for fmt in ("elf64", "win64"):
                with self.subTest(format=fmt):
                    obj = Path(temporary) / (fmt + ".o")
                    self.assemble(nasm, ROOT / "kernel/cpu.asm", obj, fmt, include=True)
                    symbols = read_elf_symbols(obj) if fmt == "elf64" else coff_symbols(obj)
                    guards, previous_end = set(), 0
                    for name in ("df", "nmi", "exception"):
                        low, high = (symbols[f"cpu_{name}_guard_{side}"] for side in ("low", "high"))
                        bottom, top = (symbols[f"cpu_{name}_stack_{side}"] for side in ("bottom", "top"))
                        self.assertEqual(0, low % 4096)
                        self.assertEqual(low + 4096, bottom)
                        self.assertEqual(bottom + 16384, top)
                        self.assertEqual(top, high)
                        self.assertGreaterEqual(low, previous_end)
                        previous_end = high + 4096
                        guards.update((low, high))
                    self.assertEqual(6, len(guards))
                    self.assertEqual(48, symbols["cpu_exception_stack_ranges_end"] - symbols["cpu_exception_stack_ranges"])

    def test_native_bss_skip_sets_invalid_layouts_and_full_input_snapshots(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native IST policy requires NASM and SysV-capable GCC")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    source, obj = directory / (mode + ".asm"), directory / (mode + ".o")
                    executable = directory / (mode + (".exe" if os.name == "nt" else ""))
                    source.write_text(compile_probe(mode).assembly, encoding="utf-8")
                    self.assemble(nasm, source, obj, "win64" if os.name == "nt" else "elf64")
                    command = [cc, "-std=c11", "-O0" if mode == "debug" else "-O2", "-fno-omit-frame-pointer",
                               "-D__USE_MINGW_ANSI_STDIO=1", "-Wall", "-Wextra", "-Werror"]
                    if os.name != "nt":
                        command += ["-no-pie"]
                    result = subprocess.run(command + [str(FIXTURES / "ist_layout_probe.c"), str(obj), "-o", str(executable)],
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("IST layout probe ok:", result.stdout)
                    self.assertIn("six guards and 16KiB stacks", result.stdout)


if __name__ == "__main__":
    unittest.main()
