"""Source-derived frame limits, including realignment and outgoing ABI areas.

No initializer is used for the reserve objects below: these functions isolate
local storage from initializer temporaries. Ordinary frames reserve 16 bytes
for the return address and saved RBP. Realigned frames additionally save R12;
the save and worst-case alignment padding together add A bytes, making their
overhead A+16. These are explicit source/ABI calculations, not backend queries.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from lang.dongc import CompileError, compile_source
from lang.tests.test_dongc import ROOT


def reserved_frame(alignment: int, reserve: int) -> str:
    return f"""module alignment_limits;
        align({alignment}) struct Block {{ value: u8 }}
        fn budget() void {{ var head: Block; var reserve: [{reserve}]u8; }}
    """


class AlignmentLimitTests(unittest.TestCase):
    def assert_frame_error(self, source, expected_size=None, *, mode="debug"):
        with self.assertRaises(CompileError) as caught:
            compile_source(source, "alignment_limits.dg", mode=mode)
        error = caught.exception
        self.assertEqual(error.code, "E0601")
        self.assertIn("frame", error.message)
        self.assertIn("4096", error.message)
        self.assertNotIn("not implemented", error.message)
        if expected_size is not None:
            self.assertIn(str(expected_size), error.message)
        return error

    def test_exact_4096_byte_local_frames_and_next_16_bytes(self):
        # A=16: 16+4064=4080 local bytes, plus 16 overhead.
        # A>16: A+reserve locals, plus A+16 save/padding overhead.
        # All listed local payloads are already multiples of 16.
        limits = [(16, 4064), (32, 4016), (64, 3952), (256, 3568), (1024, 2032)]
        for mode in ("debug", "release"):
            for alignment, reserve in limits:
                with self.subTest(mode=mode, alignment=alignment):
                    result = compile_source(reserved_frame(alignment, reserve), mode=mode)
                    block = result.layout_manifest["types"][0]
                    self.assertEqual((block["size"], block["alignment"]), (alignment, alignment))
                    self.assert_frame_error(reserved_frame(alignment, reserve + 16), 4112, mode=mode)

    def test_win64_shadow_space_counts_even_without_arguments(self):
        # No argument snapshots. 4048 local bytes + 16 saved/return + 32 shadow.
        def source(reserve):
            return f'''module alignment_limits;
                extern "win64" fn firmware() void;
                fn budget() void {{ var reserve: [{reserve}]u8; unsafe {{ firmware(); }} }}
            '''

        compile_source(source(4048))
        self.assert_frame_error(source(4064), 4112)

    def test_sysv_stack_arguments_and_snapshots_count_together(self):
        # Eight snapshots use 64 bytes; the last two arguments use 16 outgoing.
        # 4000+64+16 outgoing+16 saved/return = 4096.
        def source(reserve):
            return f'''module alignment_limits;
                extern "sysv64" fn native(a:u64,b:u64,c:u64,d:u64,e:u64,f:u64,g:u64,h:u64) void;
                fn budget() void {{ var reserve: [{reserve}]u8; unsafe {{ native(1,2,3,4,5,6,7,8); }} }}
            '''

        compile_source(source(4000))
        self.assert_frame_error(source(4016), 4112)

    def test_win64_fifth_argument_and_tail_alignment_count(self):
        # Five scalar snapshots add 40 bytes. Their 4024-byte total payload
        # rounds to 4032; 32 shadow + fifth arg + tail padding consume 48.
        # 4032+48+16 = 4096. Sequential calls reuse the outgoing area.
        def source(reserve):
            return f'''module alignment_limits;
                extern "win64" fn firmware(a:u64,b:u64,c:u64,d:u64,e:u64) void;
                fn budget() void {{ var reserve: [{reserve}]u8;
                    unsafe {{ firmware(1,2,3,4,5); firmware(6,7,8,9,10); }}
                }}
            '''

        compile_source(source(3984))
        self.assert_frame_error(source(4000), 4112)

    def test_realignment_saves_padding_shadow_and_fifth_argument_share_budget(self):
        # 64-byte head + 3864 reserve + 40 argument snapshots = 3968 locals.
        # Return/saved RBP/R12 and maximum padding contribute 80; outgoing 48.
        # 3968+80+48 = 4096.
        def source(reserve):
            return f'''module alignment_limits;
                align(64) struct Block {{ value:u8 }}
                extern "win64" fn firmware(a:u64,b:u64,c:u64,d:u64,e:u64) void;
                fn budget() void {{ var head:Block; var reserve:[{reserve}]u8;
                    unsafe {{ firmware(1,2,3,4,5); }}
                }}
            '''

        compile_source(source(3864))
        self.assert_frame_error(source(3880), 4112)

    def test_only_temporary_storage_still_requests_realignment(self):
        def source(alignment):
            return f'''module alignment_limits;
                align({alignment}) struct Block {{ value:u64 }}
                fn temporary() u64 {{ return (Block {{ value:42 }}).value; }}
            '''

        for alignment in (16, 32, 64, 256, 1024):
            with self.subTest(alignment=alignment):
                result = compile_source(source(alignment))
                if alignment > 16:
                    self.assertIn(f"and rsp, -{alignment}", result.assembly)
        # A 2048-byte temporary and its 2064-byte overhead exceed the limit.
        self.assert_frame_error(source(2048), 4112)
        self.assert_frame_error(source(4096))

    def test_large_alignment_is_a_frame_budget_error_not_an_unsupported_type(self):
        for alignment in (2048, 4096):
            with self.subTest(alignment=alignment):
                # Merely declaring or referring to the type allocates no object.
                result = compile_source(f'''module alignment_limits;
                    align({alignment}) struct Page {{ value:u8 }}
                    fn size(p:*const Page) usize {{ return sizeof(Page); }}
                ''')
                self.assertEqual(result.layout_manifest["types"][0]["alignment"], alignment)
                self.assert_frame_error(f'''module alignment_limits;
                    align({alignment}) struct Page {{ value:u8 }}
                    fn budget() void {{ var page:Page; }}
                ''', 4112 if alignment == 2048 else None)

    def test_check_rejects_oversized_frame_and_emission_preserves_old_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source, assembly, layout = directory / "budget.dg", directory / "budget.asm", directory / "layout.json"
            source.write_text(reserved_frame(64, 3952), encoding="utf-8")

            def run(*options):
                return subprocess.run([sys.executable, "-m", "lang.dongc", *map(str, options), str(source)],
                                      cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

            accepted = run("--emit-asm", assembly, "--emit-layout", layout)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            previous = assembly.read_bytes(), layout.read_bytes()
            source.write_text(reserved_frame(64, 3968), encoding="utf-8")
            for options in [("--check",), ("--emit-asm", assembly, "--emit-layout", layout)]:
                with self.subTest(options=options):
                    rejected = run(*options)
                    self.assertEqual(rejected.returncode, 1, rejected.stderr)
                    self.assertIn("error[E0601]", rejected.stderr)
                    self.assertIn("4112", rejected.stderr)
                    self.assertNotIn("Traceback", rejected.stderr)
                    self.assertEqual((assembly.read_bytes(), layout.read_bytes()), previous)
            self.assertEqual(list(directory.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
