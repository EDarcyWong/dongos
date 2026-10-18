"""Independent native activation readbacks and strict/active raw-tree audits."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent
FIELDS = "cr3 cr0 cr4 efer pat rflags entry_rsp entry_rbp rsp rbp nested_value display_value runtime_value cache_steps".split()

# Host the actual production audit functions with a smaller Workspace. The
# sole address adaptation is HHDM's base: table physical addresses still use
# a bounded independent 128-page physical pool, and the real walker, masks,
# allow-list, seen/count checks and IST checks are copied without alteration.
AUDIT_PREFIX = """module activation_audit_probe;
import boot.memory_policy as policy;
const POOL_PAGES:usize=policy.POOL_PAGES;
import boot.abi as abi;
import boot.memory_resources as resources;
import boot.ist_layout as ist;
import boot.runtime_view as runtime;
import boot.startup_errors as errors;
import mm.paging as paging;
const PAGE: u64 = 4096;
const LIMIT: u64 = 0x1_0000_0000;
const KERNEL: u64 = 0xffff_ffff_8000_0000;
var HHDM: u64 = 0;
struct Workspace {
    space: paging.Space, table_meta: [128]u8, layout: resources.Layout,
    runtime: runtime.View, manifest: [9]resources.Resource,
    expected_pages: usize, ready: bool,
}
const EMPTY_SPAN: resources.Span = resources.Span { start: 0, end: 0 };
const EMPTY_LAYOUT: resources.Layout = resources.Layout {
    text: EMPTY_SPAN, rodata: EMPTY_SPAN, data: EMPTY_SPAN, bss: EMPTY_SPAN,
    gdt: EMPTY_SPAN, tss: EMPTY_SPAN, idt: EMPTY_SPAN, df: EMPTY_SPAN,
    nmi: EMPTY_SPAN, exception_stack: EMPTY_SPAN, workspace: EMPTY_SPAN, rsdp_size: 0,
};
var WORK: Workspace = Workspace {
    space: paging.EMPTY_SPACE, table_meta: [0;128], layout: EMPTY_LAYOUT,
    runtime: runtime.EMPTY_VIEW,
    manifest: [resources.Resource { kind: 0, base: 0, length: 0 };9],
    expected_pages: 0, ready: false,
};
"""
AUDIT_SUFFIX = """
export("audit_init") fn audit_init(pool: *paging.Table, physical: u64,
    layout: *const resources.Layout, view: *const runtime.View, kernel_physical: u64) u64 {
    unsafe {
        WORK.ready = false;
        WORK.space = paging.EMPTY_SPACE;
        HHDM = (pool as u64) - physical;
        WORK.layout = *layout;
        WORK.runtime = *view;
        WORK.manifest[8] = resources.Resource { kind: 0, base: kernel_physical, length: 4096 };
        WORK.expected_pages = 0;
        match paging.init(&WORK.space,slice_from_raw_parts(pool,128),physical,WORK.table_meta[..],40,true) {
            ok => { WORK.ready = true; return 0; }, err(code) => { return code; },
        }
    }
}
export("audit_map") fn audit_map(virtual: u64, physical: u64, flags: u64) u64 {
    unsafe {
        match paging.map(&WORK.space,virtual,physical,flags) {
            ok => { WORK.expected_pages += 1; return 0; }, err(code) => { return code; },
        }
    }
}
export("audit_validate") fn audit_validate(root: u64, active: u64) u64 {
    unsafe {
        if active != 0 {
            match validate_active(root) { ok => { return 0; }, err(code) => { return code; }, }
        }
        match validate_runtime() { ok => { return 0; }, err(code) => { return code; }, }
    }
}
export("audit_ready") fn audit_ready(ready: u64) void { unsafe { WORK.ready = ready != 0; } }
export("audit_bad_count") fn audit_bad_count() void { unsafe { WORK.expected_pages += 1; } }
export("audit_bad_ist") fn audit_bad_ist() void { unsafe { WORK.layout.df.start += 1; } }
"""


class ActivationTests(unittest.TestCase):
    def assemble(self, nasm, assembly, obj, fmt):
        result = subprocess.run([nasm, "-f", fmt, *nasm_flags(nasm), "-o", str(obj), str(assembly)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)

    def native(self, directory, mode, nasm, cc, obj, audit=False):
        exe = directory / (mode + ("-audit" if audit else "") + (".exe" if os.name == "nt" else ""))
        flags = ["-DDG_AUDIT=1"] if audit else []
        if os.name != "nt":
            flags += ["-no-pie"]
        result = subprocess.run([cc, "-std=c11", "-O0" if mode == "debug" else "-O2",
                                 "-D__USE_MINGW_ANSI_STDIO=1", "-Wall", "-Wextra", "-Werror", *flags,
                                 str(FIXTURES / "activation_probe.c"), str(obj), "-o", str(exe)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("activation raw audit checks passed" if audit else "activation native checks passed", result.stdout)

    def test_readback_layout_both_modes_objects_and_native_boundaries(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        self.assertTrue(nasm and cc, "configured NASM and GCC required")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    result = compile_file(FIXTURES / "activation_probe.dg",
                                          roots=[FIXTURES, ROOT / "kernel", ROOT / "lang/examples"], mode=mode)
                    layout = {t["full_name"]: t for t in result.layout_manifest["types"]}["boot.activation.Report"]
                    self.assertEqual((112, 8), (layout["size"], layout["alignment"]))
                    self.assertEqual(FIELDS, [f["name"] for f in layout["fields"]])
                    self.assertEqual(list(range(0, 112, 8)), [f["offset"] for f in layout["fields"]])
                    assembly = directory / (mode + ".asm")
                    assembly.write_text(result.assembly, encoding="utf-8")
                    for fmt in ("elf64", "win64"):
                        self.assemble(nasm, assembly, directory / (mode + fmt + ".o"), fmt)
                    obj = directory / (mode + ("win64" if os.name == "nt" else "elf64") + ".o")
                    self.native(directory, mode, nasm, cc, obj)

    def test_production_raw_audit_strict_and_active_native(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        self.assertTrue(nasm and cc, "configured NASM and GCC required")
        source = (ROOT / "kernel/boot/memory_startup.dg").read_text(encoding="utf-8")
        start = source.index("fn in_pages(")
        # The tail is production code, including the public entry points. A
        # moved/renamed helper fails compilation rather than using a stale copy.
        audit_source = AUDIT_PREFIX + source[start:] + AUDIT_SUFFIX
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            entry = directory / "activation_audit_probe.dg"
            entry.write_text(audit_source, encoding="utf-8")
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    result = compile_file(entry, roots=[directory, ROOT / "kernel", ROOT / "lang/std", ROOT / "lang/examples"], mode=mode)
                    assembly = directory / (mode + "-audit.asm")
                    assembly.write_text(result.assembly, encoding="utf-8")
                    for fmt in ("elf64", "win64"):
                        self.assemble(nasm, assembly, directory / (mode + "-audit-" + fmt + ".o"), fmt)
                    obj = directory / (mode + "-audit-" + ("win64" if os.name == "nt" else "elf64") + ".o")
                    self.native(directory, mode, nasm, cc, obj, audit=True)


if __name__ == "__main__":
    unittest.main()
