"""Independent host gate tests; no QEMU or kernel build is launched here."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("run_memory_qemu", Path(__file__).with_name("run_memory_qemu.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
K = runner.KERNEL_BASE
SYMBOLS = {
    "__kernel_text_start": K, "__kernel_text_end": K + 0x2000,
    "__kernel_rodata_start": K + 0x2000, "__kernel_rodata_end": K + 0x3000,
    "__kernel_data_start": K + 0x3000, "__kernel_data_end": K + 0x10000,
    "__kernel_bss_start": K + 0x10000, "__kernel_bss_end": K + 0x27000,
    "cpu_gdt": K + 0x3000, "cpu_gdt_end": K + 0x3028,
    "cpu_tss": K + 0x10000, "cpu_tss_end": K + 0x10068,
    "cpu_idt": K + 0x11000, "cpu_idt_end": K + 0x12000,
    "cpu_df_stack_bottom": K + 0x13000, "cpu_df_stack_top": K + 0x17000,
    "cpu_nmi_stack_bottom": K + 0x19000, "cpu_nmi_stack_top": K + 0x1d000,
    "cpu_exception_stack_bottom": K + 0x1f000, "cpu_exception_stack_top": K + 0x23000,
    "cpu_df_guard_low": K + 0x12000, "cpu_df_guard_high": K + 0x17000,
    "cpu_nmi_guard_low": K + 0x18000, "cpu_nmi_guard_high": K + 0x1d000,
    "cpu_exception_guard_low": K + 0x1e000, "cpu_exception_guard_high": K + 0x23000,
    "memory_activation_test_expected_rip": K + 0x1234,
    "memory_activation_test_mid_return": K + 0x1120,
    "memory_activation_test_inject_return": K + 0x1100,
    "memory_activation_test_ro_target": K + 0x2080,
    "memory_activation_test_nx_target": K + 0x3080,
    "memory_mutation_test_expected_rip": K + 0x1280,
    "memory_mutation_test_mid_return": K + 0x1180,
    "memory_mutation_test_inject_return": K + 0x1140,
    "memory_live_page_a": K + 0x24000, "memory_live_page_b": K + 0x25000,
    runner.WORK_SIZE: 0x2000, runner.VIEW_SIZE: 160, runner.ACTIVATION_SIZE: 112,
    runner.MUTATION_SIZE: 144,
}


def resources():
    result = [{"kind": 0, "base": 0, "length": 4096},
              {"kind": 1, "base": 0x200000, "length": 0x200000}]
    result += [{"kind": i, "base": 0x500000, "length": 0x40000} for i in range(2, 6)]
    result += [{"kind": 6, "base": 0xe0000000, "length": 0x100000},
               {"kind": 7, "base": 0x700000, "length": 36}]
    for kind, (start, end) in runner.SYMBOL_SPANS.items():
        result.append({"kind": kind, "base": 0x200000 + SYMBOLS[start] - K,
                       "length": SYMBOLS[end] - SYMBOLS[start]})
    result += [{"kind": 18, "base": 0x204000, "length": SYMBOLS[runner.WORK_SIZE]},
               {"kind": 19, "base": 0x800000, "length": 128 * 4096},
               {"kind": 20, "base": 0x880000, "length": 16 * 4096}]
    return result


def validation_symbols(case="normal"):
    symbols = dict(SYMBOLS)
    if case == "nx-fetch":
        symbols["memory_activation_test_expected_rip"] = symbols["memory_activation_test_nx_target"]
    return symbols


def activation_panic(case, symbols):
    mutation = case in runner.MUTATION_FAULTS
    symbol_prefix = "memory_mutation_test" if mutation else "memory_activation_test"
    target = runner.MUTATION_VIRTUAL if mutation else {
        "null-page": 0, "ro-write": symbols["memory_activation_test_ro_target"],
        "nx-fetch": symbols["memory_activation_test_nx_target"], "stack-guard": 0xffff900000000ff8,
        "ist-guard": symbols["cpu_exception_guard_low"]}[case]
    fields = {
        "context": K + 0x23000 - 184, "stack": "EXCEPTION",
        "rax": 0x1111111111111111, "rbx": 0x2222222222222222,
        "rcx": 0x3333333333333333, "rdx": 0x4444444444444444,
        "rsi": 0x5555555555555555, "rdi": 0x6666666666666666,
        "rbp": 0xffff900000010f00,
        "r8": 0x8888888888888888, "r9": 0x9999999999999999,
        "r10": 0xaaaaaaaaaaaaaaaa, "r11": 0xbbbbbbbbbbbbbbbb,
        "r12": 0xcccccccccccccccc, "r13": 0xdddddddddddddddd,
        "r14": 0xeeeeeeeeeeeeeeee, "r15": 0xffffffffffffffff,
        "vector": 14, "error": (runner.MUTATION_FAULTS if mutation else runner.ACTIVATION_FAULTS)[case],
        "rip": symbols[symbol_prefix + "_expected_rip"], "cs": 8, "rflags": 0x402,
        "rsp": 0xffff900000010f00, "ss": 0x10,
        "cr2": target,
        "frame_symbol": symbols[symbol_prefix + "_expected_rip"],
    }
    if case == "stack-guard":
        fields["rsp"] = 0xffff900000001000
    else:
        fields["rax"] = fields["cr2"]
    fields.update(frame_00=fields["rip"], frame_01=symbols[symbol_prefix + "_mid_return"],
                  frame_02=symbols[symbol_prefix + "_inject_return"], frame_count=3)
    return [(f"panic_{name}={value}" if name == "stack" else f"panic_{name}=0x{value:016x}").encode()
            for name, value in fields.items()]


def capture(case="normal", *, values=None, manifest=None, activation=None, mutation=None):
    manifest = resources() if manifest is None else manifest
    fields = dict(zip(runner.FIELDS, (36, 1, 21, 0x800000, 1024, 1024, 880,
                                     0x800000, 128, 0x800000, 12, 454,
                                     0x0007040600070406, 0x880000, 16,
                                     0xffff900000001000, 0xffff900000011000,
                                     0x535441434b, K + 0x4080,
                                     runner.HHDM + 0x500000, runner.HHDM + 0x500100,
                                     runner.HHDM + 0x700000, runner.HHDM + 0xe0000000,
                                     runner.HHDM + 0x800000, 6, 0x510000, 0x510000,
                                     0x80000011, 0x80000011, 0x620, 0x620,
                                     0x500, 0x500, 2, 2, 0x80010011, 0xd00, 7)))
    # Alias fixtures follow deliberately relocated valid physical resources;
    # a values override can still corrupt each alias independently.
    if len(manifest) > 7:
        fields.update(runtime_rsdp=runner.HHDM + manifest[7]["base"],
                      runtime_framebuffer=runner.HHDM + manifest[6]["base"])
    fields.update(values or {})
    lines = [b"UEFI firmware log", *runner.PREFIX_MARKERS]
    if case == "normal" or case in runner.ACTIVATION_FAULTS or case in runner.MUTATION_FAULTS:
        lines += [f"memory_{key}=0x{fields[key]:016x}".encode() for key in runner.FIELDS]
        for item in manifest:
            lines += [f"memory_{key}=0x{item[key]:016x}".encode() for key in ("kind", "base", "length")]
        lines += [runner.STACK_READY, runner.PREFLIGHT_READY]
        active = dict(zip(runner.ACTIVATION_FIELDS,
                          (fields["root_physical"], fields["planned_cr0"], fields["cr4_before"],
                           fields["planned_efer"], fields["pat_value"], 2,
                           0xffff900000011000, 0, 0xffff900000010f88, 0xffff900000010fa0,
                           0x414354495645, 0x0055aa33, 0x52554e54494d45, 31)))
        active.update(activation or {})
        lines += [f"activation_{key}=0x{active[key]:016x}".encode() for key in runner.ACTIVATION_FIELDS]
        lines += [runner.ACTIVATION_READY]
        if case in runner.ACTIVATION_FAULTS:
            lines += [runner.ACTIVATION_INJECT, runner.PANIC, *activation_panic(case, validation_symbols(case))]
        else:
            live = dict(zip(runner.MUTATION_FIELDS,
                            (fields["root_physical"], runner.MUTATION_VIRTUAL,
                             manifest[8]["base"] + SYMBOLS["memory_live_page_a"] - K,
                             manifest[8]["base"] + SYMBOLS["memory_live_page_b"] - K,
                             runner.MUTATION_A, runner.MUTATION_B, runner.MUTATION_WRITE, runner.MUTATION_A,
                             fields["table_count"], fields["table_count"] + 3, fields["table_count"],
                             5, 2, 6, fields["pool_physical"] + 0x11000, fields["pool_physical"] + 0x11000,
                             fields["root_physical"], runner.MUTATION_STEPS)))
            live.update(mutation or {})
            lines += [f"mutation_{key}=0x{live[key]:016x}".encode() for key in runner.MUTATION_FIELDS]
            lines += [runner.MUTATION_READY]
            if case in runner.MUTATION_FAULTS:
                lines += [runner.MUTATION_INJECT, runner.PANIC, *activation_panic(case, validation_symbols(case))]
            else:
                lines += [runner.READY, runner.PASS]
    else:
        lines += [f"memory_error=0x{runner.NEGATIVE_ERRORS[case]:016x}".encode(), runner.FAIL]
    return b"\r\n".join(lines) + b"\r\n"


def symbol_elf(symbols=SYMBOLS):
    strings, entries = bytearray(b"\0"), [bytes(24)]
    for name, value in symbols.items():
        offset = len(strings)
        strings += name.encode() + b"\0"
        entries.append(struct.pack("<IBBHQQ", offset, 0x10, 0, 1, value, 0))
    table = b"".join(entries)
    header = bytearray(64)
    header[:16] = b"\x7fELF\x02\x01\x01" + bytes(9)
    struct.pack_into("<HHIQQQIHHHHHH", header, 16, 2, 62, 1, K, 0, 64, 0, 64, 0, 0, 64, 3, 0)
    sections = bytes(64) + struct.pack("<IIQQQQIIQQ", 0, 2, 0, 0, 256, len(table), 2, 0, 8, 24)
    sections += struct.pack("<IIQQQQIIQQ", 0, 3, 0, 0, 256 + len(table), len(strings), 0, 0, 1, 0)
    return bytes(header) + sections + table + strings


def layout_manifest():
    return {"types": [{"full_name": "boot.memory_startup.Workspace", "size": 8192},
                      {"full_name": "boot.runtime_view.View", "size": 160, "alignment": 8,
                       "fields": [{"offset": offset} for offset in [0, *range(48, 160, 8)]]},
                      {"full_name": "boot.activation.Report", "size": 112, "alignment": 8,
                       "fields": [{"name": name, "offset": index * 8}
                                  for index, name in enumerate(("cr3", "cr0", "cr4", "efer", "pat", "rflags",
                                                                "entry_rsp", "entry_rbp", "rsp", "rbp", "nested_value",
                                                                "display_value", "runtime_value", "cache_steps"))]},
                      {"full_name": "boot.live_memory.Report", "size": 144, "alignment": 8,
                       "fields": [{"name": name, "offset": index * 8}
                                  for index, name in enumerate(runner.MUTATION_FIELDS)]}]}


def replace_diagnostic(serial, prefix, name, value):
    key = f"{prefix}_{name}=".encode()
    return b"\r\n".join(f"{prefix}_{name}=0x{value:016x}".encode() if line.startswith(key) else line
                           for line in serial.split(b"\r\n"))


class MemoryGateTests(unittest.TestCase):
    def check(self, serial=None, *, case="normal", code=None, timeout=False, symbols=None):
        if code is None:
            code = 37 if case in runner.ACTIVATION_FAULTS or case in runner.MUTATION_FAULTS else 33 if case == "normal" else 35
        if symbols is None:
            symbols = validation_symbols(case)
        return runner.check_result(code, capture(case) if serial is None else serial, timeout, case, symbols)

    def test_complete_independent_capture_and_merged_loader_envelopes(self):
        self.assertEqual([], self.check())
        parsed = runner.parse_memory_result(capture(), symbols=SYMBOLS)
        self.assertTrue(parsed["passed"])
        self.assertEqual(21, len(parsed["resources"]))

    def test_report_layout_is_fixed_thirty_eight_fields(self):
        self.assertEqual(("physical_bits", "nx", "resource_count", "arena_base", "arena_pages",
                          "usable_pages", "free_pages", "pool_physical", "pool_pages", "root_physical",
                          "table_count", "mapped_pages", "pat_value", "stack_physical", "stack_pages",
                          "stack_bottom", "stack_top", "bridge_value", "runtime_view", "runtime_boot_info",
                          "runtime_raw_map", "runtime_rsdp", "runtime_framebuffer", "runtime_pool", "ist_guard_pages",
                          "cr3_before", "cr3_after", "cr0_before", "cr0_after", "cr4_before", "cr4_after",
                          "efer_before", "efer_after", "rflags_before", "rflags_after",
                          "planned_cr0", "planned_efer", "planned_actions"), runner.FIELDS)
        self.assertEqual(38, len(runner.FIELDS))
        self.assertEqual(21, runner.RESOURCE_COUNT)

    def test_activation_report_is_fixed_fourteen_fields_and_new_state_directory(self):
        self.assertEqual(("cr3", "cr0", "cr4", "efer", "pat", "rflags", "entry_rsp", "entry_rbp",
                          "rsp", "rbp", "nested_value", "display_value", "runtime_value", "cache_steps"),
                         runner.ACTIVATION_FIELDS)
        self.assertEqual(Path("build/test/memory-mutation"), runner.STATE_DIR)
        parsed = runner.parse_memory_result(capture(), symbols=SYMBOLS)
        self.assertEqual(14, len(parsed["activation"]))
        self.assertEqual(0x800000, parsed["activation"]["cr3"])
        self.assertEqual(0x510000, parsed["fields"]["cr3_after"])

    def test_mutation_report_has_fixed_eighteen_field_abi(self):
        self.assertEqual(("root", "virtual", "physical_a", "physical_b", "read_a", "read_b",
                          "write_value", "reuse_value", "tables_before", "tables_peak", "tables_after",
                          "invlpg_count", "reload_count", "retired_tables", "first_branch", "reused_branch",
                          "cr3_after", "steps"), runner.MUTATION_FIELDS)
        parsed = runner.parse_memory_result(capture(), symbols=SYMBOLS)
        self.assertTrue(parsed["passed"])
        self.assertEqual(18, len(parsed["mutation"]))
        self.assertEqual(0xffffa00000001000, parsed["mutation"]["virtual"])
        self.assertEqual(12, parsed["mutation"]["tables_after"])

    def test_mutation_report_rejects_stale_success_and_partial_or_displaced_records(self):
        serial = capture()
        line = b"mutation_root=0x0000000000800000\r\n"
        next_line = b"mutation_virtual=0xffffa00000001000\r\n"
        old = b"\r\n".join(item for item in serial.split(b"\r\n")
                               if not item.startswith(b"mutation_") and item != runner.MUTATION_READY)
        for bad in (old, serial.replace(line, b""), serial + line,
                    serial.replace(line, b"mutation_root=0x800000\r\n"),
                    serial.replace(next_line, b"mutation_virtual=0xFFFFA00000001000\r\n"),
                    serial.replace(line, b"mutation_unknown=0x0000000000800000\r\n"),
                    serial.replace(line, b"prefix:" + line), line + serial.replace(line, b""),
                    serial.replace(line + next_line, next_line + line),
                    serial.replace(line, line + b"unexpected line\r\n"),
                    serial.replace(runner.MUTATION_READY + b"\r\n", b""),
                    serial + runner.MUTATION_READY + b"\r\n",
                    serial.replace(runner.ACTIVATION_READY + b"\r\n" + line,
                                   line + runner.ACTIVATION_READY + b"\r\n")):
            self.assertTrue(self.check(bad))

    def test_mutation_backing_addresses_are_bound_to_live_linked_ram(self):
        for name, values in (("root", (0, 0x510000, 0x801000)),
                             ("cr3_after", (0, 0x510000, 0x801000)),
                             ("virtual", (0, runner.HHDM + 0x224000, 0xffffa00000001001,
                                          0x0000a00000001000)),
                             ("physical_a", (0, 0x224001, 0x225000, 0x800000, 0xe0000000)),
                             ("physical_b", (0x224000, 0x225001, 0x226000, runner.LOW_LIMIT))):
            for value in values:
                with self.subTest(field=name, value=hex(value)):
                    self.assertTrue(self.check(capture(mutation={name: value})))
        for name, value in (("memory_live_page_a", K + 0x24001),
                            ("memory_live_page_a", K + 0x23000),
                            ("memory_live_page_b", K + 0x24000),
                            ("memory_live_page_b", K + 0x27000)):
            symbols = dict(SYMBOLS)
            symbols[name] = value
            self.assertTrue(self.check(symbols=symbols))
        for name in runner.MUTATION_PAGE_SYMBOLS | {runner.MUTATION_SIZE}:
            symbols = dict(SYMBOLS)
            del symbols[name]
            self.assertTrue(self.check(symbols=symbols))

    def test_mutation_requires_distinct_readback_write_reuse_tokens_and_all_steps(self):
        for name in ("read_a", "read_b", "write_value", "reuse_value", "steps"):
            current = runner.parse_memory_result(capture(), symbols=SYMBOLS)["mutation"][name]
            for value in (0, current ^ 1):
                self.assertTrue(self.check(capture(mutation={name: value})))
        self.assertTrue(self.check(capture(mutation={"read_b": runner.MUTATION_A})))
        self.assertTrue(self.check(capture(mutation={"reuse_value": runner.MUTATION_WRITE})))
        self.assertTrue(self.check(capture(mutation={"steps": 2047})))

    def test_mutation_ram_cannot_alias_live_cpu_view_or_workspace_storage(self):
        symbols = dict(SYMBOLS, memory_live_page_a=K + 0x10000, memory_live_page_b=K + 0x11000)
        serial = capture(mutation={"physical_a": 0x210000, "physical_b": 0x211000})
        self.assertIn("mutation RAM overlaps CPU storage, Runtime View or paging workspace",
                      self.check(serial, symbols=symbols))
        self.assertIn("mutation RAM overlaps CPU storage, Runtime View or paging workspace",
                      self.check(capture(values={"runtime_view": K + 0x24000})))
        manifest = resources()
        manifest[18]["base"] = 0x224000
        self.assertIn("mutation RAM overlaps CPU storage, Runtime View or paging workspace",
                      self.check(capture(manifest=manifest)))

    def test_mutation_reclamation_counts_and_reused_branch_are_checked_independently(self):
        for name, values in (("tables_before", (0, 11, 13)), ("tables_peak", (12, 14, 16, 65)),
                             ("tables_after", (0, 11, 13, 15)), ("invlpg_count", (0, 4, 6)),
                             ("reload_count", (0, 1, 3)), ("retired_tables", (0, 3, 5, 7)),
                             ("first_branch", (0, 0x800000, 0x811001, 0x880000)),
                             ("reused_branch", (0, 0x812000, 0x811001))):
            for value in values:
                with self.subTest(field=name, value=value):
                    self.assertTrue(self.check(capture(mutation={name: value})))
        for branch in (0x800000, 0x7ff000, 0x880000, 0x811001):
            self.assertTrue(self.check(capture(mutation={"first_branch": branch, "reused_branch": branch})))

    def test_both_mutation_hardware_faults_require_lifecycle_and_fatal_exit(self):
        self.assertEqual({"tlb-ro": 3, "tlb-unmap": 0}, runner.MUTATION_FAULTS)
        for case in runner.MUTATION_FAULTS:
            self.assertEqual([], self.check(case=case))
            serial = capture(case)
            for code in (0, 33, 35, -9):
                self.assertTrue(self.check(case=case, code=code))
            self.assertTrue(self.check(case=case, timeout=True))
            for bad in (serial.replace(runner.MUTATION_READY + b"\r\n", b""),
                        serial.replace(runner.MUTATION_INJECT + b"\r\n", b""),
                        serial.replace(runner.MUTATION_INJECT, runner.ACTIVATION_INJECT),
                        serial.replace(b"mutation_read_b=", b"mutation_unknown="),
                        serial + runner.READY + b"\r\n", serial + runner.PASS + b"\r\n",
                        serial.replace(runner.PANIC + b"\r\n", b"")):
                self.assertTrue(self.check(bad, case=case))

    def test_mutation_fault_registers_context_and_frame_symbols_are_hardware_specific(self):
        for case in runner.MUTATION_FAULTS:
            serial = capture(case)
            for name in ("vector", "error", "rip", "cr2", "cs", "ss", "frame_symbol", *runner.SEED_REGISTERS,
                         "frame_00", "frame_01", "frame_02", "frame_count"):
                line = next(item for item in serial.split(b"\r\n") if item.startswith(f"panic_{name}=".encode()))
                bad_value = int(line.partition(b"=0x")[2], 16) ^ 1
                self.assertTrue(self.check(replace_diagnostic(serial, "panic", name, bad_value), case=case))
            for name, value in (("context", SYMBOLS["cpu_exception_stack_top"] - 8),
                                ("context", SYMBOLS["cpu_exception_guard_low"]),
                                ("rbp", 0x100ff00), ("rsp", 0x100ff00),
                                ("rflags", 2), ("rflags", 0x602), ("rflags", 0x20402)):
                self.assertTrue(self.check(replace_diagnostic(serial, "panic", name, value), case=case))
            for name in runner.MUTATION_FAULT_SYMBOLS:
                symbols = dict(SYMBOLS)
                del symbols[name]
                self.assertTrue(self.check(serial, case=case, symbols=symbols))
                symbols = dict(SYMBOLS)
                symbols[name] = K + 0x3080
                self.assertTrue(self.check(serial, case=case, symbols=symbols))

    def test_early_activation_faults_cannot_claim_late_mutation_progress(self):
        report = b"mutation_root=0x0000000000800000\r\n"
        for case in runner.ACTIVATION_FAULTS:
            serial = capture(case)
            self.assertTrue(self.check(serial.replace(runner.ACTIVATION_INJECT, report + runner.ACTIVATION_INJECT), case=case))
            self.assertTrue(self.check(serial.replace(runner.ACTIVATION_INJECT, runner.MUTATION_READY + b"\r\n" +
                                                     runner.ACTIVATION_INJECT), case=case))

    def test_activation_fields_require_full_known_unique_ordered_lowercase_lines(self):
        serial = capture()
        line = b"activation_cr3=0x0000000000800000\r\n"
        next_line = b"activation_cr0=0x0000000080010011\r\n"
        for bad in (serial.replace(line, b""), serial + line,
                    serial.replace(line, b"activation_cr3=0x800000\r\n"),
                    serial.replace(line, b"activation_cr3=0x000000000080000A\r\n"),
                    serial.replace(line, b"activation_unknown=0x0000000000800000\r\n"),
                    serial.replace(line, b"prefix:" + line),
                    line + serial.replace(line, b""),
                    serial.replace(line, line + b"unexpected line\r\n"),
                    serial.replace(line + next_line, next_line + line),
                    serial.replace(runner.ACTIVATION_READY + b"\r\n", b""),
                    serial + runner.ACTIVATION_READY + b"\r\n"):
            with self.subTest(tail=bad[-150:]):
                self.assertTrue(self.check(bad))
        # An old preflight-only success transcript must never pass activation.
        old = b"\r\n".join(line for line in serial.split(b"\r\n")
                               if not line.startswith(b"activation_") and line != runner.ACTIVATION_READY)
        self.assertTrue(self.check(old))

    def test_activation_controls_must_match_new_root_and_preserved_plan(self):
        for name, value in (("cr3", 0), ("cr3", 0x510000), ("cr3", 0x801000),
                            ("cr3", 0x100000000), ("cr0", 0x80000011), ("cr0", 0x80010010),
                            ("cr4", 0x621), ("efer", 0x500), ("efer", 0xd01),
                            ("pat", 0x0007040600070407)):
            with self.subTest(name=name, value=value):
                self.assertTrue(self.check(capture(activation={name: value})))
        for flags in (0, 2 | 1 << 9, 2 | 1 << 10, 2 | 1 << 17, 2 | 1 << 18):
            self.assertTrue(self.check(capture(activation={"rflags": flags})))
        self.assertEqual([], self.check(capture(activation={"rflags": 0x8d7})))

    def test_optional_hardening_stage_projects_only_complete_ordered_records(self):
        # The dedicated hardening gate checks values and CPU profiles; this
        # adapter must still reject malformed or misplaced stage records.
        stage = [f"hardening_{name}=0x{value:016x}".encode()
                 for name, value in zip(runner.HARDENING_FIELDS,
                     (13, 0x100080, 4, 0x300800, 0x620, 0x300e20,
                      2, 2, 0x80010011, 0x800000, 0xd00,
                      0x0007040600070406, 7))] + [runner.HARDENING_READY]
        lines = capture().splitlines()
        at = lines.index(runner.ACTIVATION_READY) + 1
        def log(records, position=at):
            return b"\r\n".join(lines[:position] + records + lines[position:]) + b"\r\n"
        self.assertEqual([], self.check(log(stage)))
        for bad in (stage[1:], stage[:-1], stage + stage, stage[::-1],
                    [b"prefix " + stage[0], *stage[1:]],
                    [stage[0].replace(b"=0x", b"=0x0x"), *stage[1:]]):
            self.assertTrue(self.check(log(bad)))
        self.assertTrue(self.check(log(stage, 0)))

    def test_activation_handoff_stack_full_frames_and_result_tokens(self):
        bottom, top = 0xffff900000001000, 0xffff900000011000
        for name, values in (("entry_rsp", (top - 8, top + 8, 0)),
                             ("entry_rbp", (1, top - 16)),
                             ("rsp", (bottom - 8, bottom, top, top + 8, runner.HHDM + 0x84f008)),
                             ("rbp", (bottom - 16, bottom + 8, top - 8, top, runner.HHDM + 0x84f000)),
                             ("nested_value", (0, 0x414354495644)),
                             ("display_value", (0, 0x55aa32)),
                             ("runtime_value", (0, 0x52554e54494d44)),
                             ("cache_steps", (0, 15, 30, 63))):
            for value in values:
                with self.subTest(name=name, value=value):
                    self.assertTrue(self.check(capture(activation={name: value})))
        for rsp in (bottom + 8, top - 8):
            for rbp in (bottom, top - 16):
                self.assertEqual([], self.check(capture(activation={"rsp": rsp, "rbp": rbp})))

    def test_all_five_hardware_faults_require_full_activation_and_fatal_exit(self):
        self.assertEqual({"null-page": 0, "ro-write": 3, "nx-fetch": 17,
                          "stack-guard": 2, "ist-guard": 0}, runner.ACTIVATION_FAULTS)
        for case in runner.ACTIVATION_FAULTS:
            with self.subTest(case=case):
                self.assertEqual([], self.check(case=case))
                for code in (0, 33, 35, -9):
                    self.assertTrue(self.check(case=case, code=code))
                self.assertTrue(self.check(case=case, timeout=True))
                serial = capture(case)
                for bad in (serial[:-1], serial.replace(runner.ACTIVATION_READY + b"\r\n", b""),
                            serial.replace(runner.ACTIVATION_INJECT + b"\r\n", b""),
                            serial.replace(runner.PANIC + b"\r\n", b""),
                            serial + runner.PASS + b"\r\n", serial + runner.READY + b"\r\n",
                            serial + b"DONGOS_P2_PANIC_REENTERED\r\n", serial + b"PANIC partial\r\n"):
                    self.assertTrue(self.check(bad, case=case))

    def test_fault_vector_error_cr2_rip_and_each_seeded_register(self):
        for case in runner.ACTIVATION_FAULTS:
            serial = capture(case)
            for name in ("vector", "error", "rip", "cr2", "cs", "ss", "frame_symbol", *runner.SEED_REGISTERS):
                line = next(line for line in serial.split(b"\r\n") if line.startswith(f"panic_{name}=".encode()))
                bad_value = int(line.partition(b"=0x")[2], 16) ^ 1
                with self.subTest(case=case, name=name):
                    self.assertTrue(self.check(replace_diagnostic(serial, "panic", name, bad_value), case=case))

    def test_fault_context_and_interrupted_stack_must_use_live_fixed_ranges(self):
        for case in runner.ACTIVATION_FAULTS:
            serial = capture(case)
            for name, value in (("context", 0), ("context", SYMBOLS["cpu_exception_guard_low"]),
                                ("context", SYMBOLS["cpu_exception_stack_top"] - 8),
                                ("context", SYMBOLS["cpu_df_stack_top"] - 184),
                                ("context", SYMBOLS["cpu_exception_stack_top"] - 183),
                                ("rbp", 0x100ff00), ("rbp", 0xffff900000010ff8),
                                ("rbp", 0xffff900000010f08), ("rsp", 0x100ff00),
                                ("rflags", 2), ("rflags", 0x602), ("rflags", 0x400), ("rflags", 0x20402)):
                with self.subTest(case=case, name=name, value=value):
                    self.assertTrue(self.check(replace_diagnostic(serial, "panic", name, value), case=case))
            self.assertTrue(self.check(serial.replace(b"panic_stack=EXCEPTION", b"panic_stack=DF"), case=case))
        serial = capture("stack-guard")
        self.assertTrue(self.check(replace_diagnostic(serial, "panic", "rsp", 0xffff900000010f00), case="stack-guard"))

    def test_fault_fields_frames_complete_ordered_and_linked_to_independent_symbols(self):
        serial = capture("ro-write")
        line = b"panic_vector=0x000000000000000e\r\n"
        for bad in (serial.replace(line, b""), serial + line,
                    serial.replace(line, b"panic_vector=0xe\r\n"),
                    serial.replace(line, b"prefix:" + line), line + serial.replace(line, b""),
                    serial.replace(line, line + b"interrupted\r\n"),
                    serial + b"panic_unknown=0x0000000000000000\r\n",
                    serial.replace(b"panic_frame_01=", b"panic_frame_03="),
                    serial.replace(b"panic_frame_01=", b"panic_frame_16="),
                    serial + b"panic_stack=EXCEPTION\r\n"):
            self.assertTrue(self.check(bad, case="ro-write"))
        for name, value in (("frame_count", 0), ("frame_count", 2), ("frame_count", 4),
                            ("frame_count", 17), ("frame_00", 0), ("frame_01", 0), ("frame_02", 0)):
            self.assertTrue(self.check(replace_diagnostic(serial, "panic", name, value), case="ro-write"))
        for name in runner.FAULT_SYMBOLS:
            symbols = validation_symbols("ro-write")
            del symbols[name]
            self.assertTrue(self.check(serial, case="ro-write", symbols=symbols))
        for name, value in (("memory_activation_test_ro_target", K + 0x3080),
                            ("memory_activation_test_nx_target", K + 0x2080),
                            ("memory_activation_test_expected_rip", K + 0x3080),
                            ("memory_activation_test_mid_return", K + 0x3080)):
            symbols = validation_symbols("ro-write")
            symbols[name] = value
            self.assertTrue(self.check(serial, case="ro-write", symbols=symbols))

    def test_process_exit_timeout_and_truncation_never_pass(self):
        for code in (None, 0, 1, 35, 37, -9):
            self.assertTrue(runner.check_result(code, capture(), False, "normal", SYMBOLS))
        self.assertTrue(self.check(timeout=True))
        self.assertTrue(self.check(capture()[:-1]))

    def test_stage_marker_missing_duplicate_out_of_order_unknown_embedded(self):
        original = capture()
        for serial in (original.replace(runner.READY + b"\r\n", b""),
                       original.replace(runner.STACK_READY + b"\r\n", b""),
                       original.replace(runner.PREFLIGHT_READY + b"\r\n", b""),
                       original.replace(runner.PREFLIGHT_READY, runner.PREFLIGHT_READY + b"\r\n" + runner.PREFLIGHT_READY),
                       original.replace(runner.STACK_READY, runner.STACK_READY + b"\r\n" + runner.STACK_READY),
                       original.replace(runner.STACK_READY + b"\r\n" + runner.PREFLIGHT_READY,
                                        runner.PREFLIGHT_READY + b"\r\n" + runner.STACK_READY),
                       original.replace(runner.STACK_READY + b"\r\n", b"").replace(
                           b"memory_physical_bits=", runner.STACK_READY + b"\r\n" + b"memory_physical_bits="),
                       original + runner.PASS + b"\r\n",
                       original.replace(runner.READY, runner.PASS, 1),
                       original + b"DONGOS_OTHER\r\n",
                       original.replace(runner.READY, b"prefix:" + runner.READY),
                       original + b"PANIC partial", original + b"DONGOS_FAIL\r\n"):
            with self.subTest(serial=serial[-100:]):
                self.assertTrue(self.check(serial))

    def test_fields_exact_order_width_lowercase_and_whole_lines(self):
        original = capture()
        line = b"memory_nx=0x0000000000000001\r\n"
        for serial in (original.replace(line, b""), original + line,
                       original.replace(line, b"memory_nx=0x1\r\n"),
                       original.replace(line, b"memory_nx=0x000000000000000A\r\n"),
                       original.replace(line, b"memory_unknown=0x0000000000000001\r\n"),
                       original.replace(line, b"x" + line),
                       line + original.replace(line, b""),
                       original.replace(line, line + b"unexpected line\r\n")):
            self.assertTrue(self.check(serial))

    def test_bad_scalar_counts_alignment_width_and_cr3(self):
        changes = ({"physical_bits": 31}, {"physical_bits": 53}, {"nx": 0},
                   {"resource_count": 19}, {"resource_count": 20}, {"arena_pages": 512}, {"arena_base": 0x801000},
                   {"pool_pages": 32}, {"pool_physical": 0x801000},
                   {"free_pages": 960}, {"usable_pages": 1025}, {"table_count": 0},
                   {"table_count": 129}, {"mapped_pages": 111},
                   {"root_physical": 0x880000}, {"cr3_after": 0x520000},
                   {"cr3_before": 0x800000, "cr3_after": 0x800000})
        for values in changes:
            with self.subTest(values=values):
                self.assertTrue(self.check(capture(values=values)))

    def test_pat_checks_full_slot_bytes_and_allows_other_slots(self):
        # This is the reset PAT value used by this fixture; only entries 0/3 are frozen.
        pat = 0x0007040600070406
        for value in (pat & ~0xff, pat | 0x1000000, (pat & ~0xff) | 0x86, pat | 0x80000000):
            with self.subTest(pat=hex(value)):
                self.assertIn("PAT entry 0 must be WB and entry 3 must be UC",
                              self.check(capture(values={"pat_value": value})))
        for value in (6, 0x0606060600060606):
            self.assertEqual([], self.check(capture(values={"pat_value": value})))

    def test_stack_fixed_virtual_range_bridge_and_allocator_accounting(self):
        for changes in ({"stack_pages": 15}, {"stack_pages": 32},
                        {"stack_bottom": 0xffff900000000000}, {"stack_top": 0xffff900000010000},
                        {"bridge_value": 0}, {"bridge_value": 0x535441434a},
                        {"free_pages": 881}, {"free_pages": 960, "stack_pages": 0}):
            with self.subTest(changes=changes):
                self.assertTrue(self.check(capture(values=changes)))
        # Change both report and manifest so that range/alignment checks are independent.
        for base in (0x881000, 0x7f0000, 0xc00000, 0xffff0000, 0xffffffffffff0000):
            manifest = resources()
            manifest[20]["base"] = base
            self.assertTrue(self.check(capture(values={"stack_physical": base}, manifest=manifest)))
        for changes in ({"base": 0x890000}, {"length": 15 * 4096}, {"kind": 19}):
            manifest = resources()
            manifest[20].update(changes)
            self.assertTrue(self.check(capture(manifest=manifest)))

    def test_stack_disjoint_from_every_retained_span_including_pool(self):
        for index in range(20):
            manifest = resources()
            manifest[index]["base"] = 0x880000
            with self.subTest(kind=index):
                self.assertIn(f"allocated resource 20 overlaps retained resource {index}",
                              self.check(capture(manifest=manifest)))
        # A separately consistent pool/stack overlap must fail even with valid accounting.
        manifest = resources()
        manifest[20]["base"] = 0x830000
        self.assertIn("allocated resource 20 overlaps retained resource 19",
                      self.check(capture(values={"stack_physical": 0x830000}, manifest=manifest)))

    def test_mapped_page_floor_counts_known_alias_union_and_unaligned_rsdp(self):
        self.assertEqual([], self.check(capture(values={"mapped_pages": 452})))
        self.assertTrue(self.check(capture(values={"mapped_pages": 451})))
        manifest = resources()
        manifest[7].update(base=0x700ff0, length=36)
        self.assertTrue(self.check(capture(values={"mapped_pages": 452}, manifest=manifest)))
        self.assertEqual([], self.check(capture(values={"mapped_pages": 453}, manifest=manifest)))
        # A byte range can cover the same page envelope as the aligned GOP fixture.
        manifest = resources()
        manifest[6].update(base=0xe0000100, length=0xfff00)
        self.assertEqual([], self.check(capture(values={"mapped_pages": 452}, manifest=manifest)))
        self.assertTrue(self.check(capture(values={"mapped_pages": 451}, manifest=manifest)))

    def test_runtime_aliases_are_independently_bound_to_physical_resources(self):
        for key, value in (("runtime_boot_info", 0x500000),
                           ("runtime_boot_info", runner.HHDM + 0x500000 - 1),
                           ("runtime_boot_info", runner.HHDM + 0x540000 - 159),
                           ("runtime_raw_map", runner.HHDM + 0x540000 - 39),
                           ("runtime_raw_map", runner.HHDM + runner.LOW_LIMIT),
                           ("runtime_rsdp", runner.HHDM + 0x700001),
                           ("runtime_framebuffer", runner.HHDM + 0xe0001000),
                           ("runtime_pool", runner.HHDM + 0x801000),
                           ("runtime_view", 0x204080),
                           ("runtime_view", K + 0x2000),
                           ("runtime_view", SYMBOLS["__kernel_bss_end"] - 159),
                           ("runtime_view", SYMBOLS["cpu_df_guard_low"]),
                           ("runtime_view", SYMBOLS["cpu_df_guard_high"] - 80)):
            with self.subTest(key=key, value=hex(value)):
                self.assertTrue(self.check(capture(values={key: value})))
        for values in ({"runtime_boot_info": runner.HHDM + 0x540000 - 160},
                       {"runtime_raw_map": runner.HHDM + 0x540000 - 40},
                       {"runtime_view": SYMBOLS["__kernel_bss_end"] - 160}):
            self.assertEqual([], self.check(capture(values=values)))

    def test_guard_symbols_are_required_and_windows_cannot_overlap(self):
        for names in runner.GUARD_SYMBOLS.values():
            for name in names:
                symbols = dict(SYMBOLS)
                del symbols[name]
                self.assertTrue(self.check(symbols=symbols))
                symbols = dict(SYMBOLS)
                symbols[name] += runner.PAGE
                self.assertTrue(self.check(symbols=symbols))
        self.assertTrue(self.check(capture(values={"ist_guard_pages": 5})))
        self.assertTrue(self.check(capture(values={"ist_guard_pages": 7})))
        # Keep each local guard equality and manifest span coherent while two
        # complete windows overlap: the independent global check must reject.
        symbols, manifest = dict(SYMBOLS), resources()
        for name in (*runner.SYMBOL_SPANS[16], *runner.GUARD_SYMBOLS[16]):
            symbols[name] -= runner.PAGE
        manifest[16]["base"] -= runner.PAGE
        self.assertIn("linked IST guard windows overlap", self.check(capture(manifest=manifest), symbols=symbols))
        symbols = dict(SYMBOLS)
        symbols[runner.VIEW_SIZE] = 159
        self.assertTrue(self.check(symbols=symbols))

    def test_controls_are_unchanged_and_required_execution_state_is_checked(self):
        for register in ("cr0", "cr4", "efer"):
            fields = runner.parse_memory_result(capture(), symbols=SYMBOLS)["fields"]
            for bit in (1, 1 << 40):
                self.assertTrue(self.check(capture(values={register + "_after": fields[register + "_before"] ^ bit})))
        for bit in (1, 1 << 31, 1 << 29, 1 << 30):
            bad = 0x80000011 ^ bit
            self.assertTrue(self.check(capture(values={"cr0_before": bad, "cr0_after": bad,
                                                      "planned_cr0": bad | 0x10000})))
        for bit in (1 << 5, 1 << 7, 1 << 12, 1 << 17, 1 << 23):
            bad = 0x620 ^ bit
            self.assertTrue(self.check(capture(values={"cr4_before": bad, "cr4_after": bad})))
        for bit in (1 << 8, 1 << 10):
            bad = 0x500 ^ bit
            self.assertTrue(self.check(capture(values={"efer_before": bad, "efer_after": bad,
                                                      "planned_efer": bad | 0x800})))
        for bit in (1 << 9, 1 << 10, 1 << 17, 1 << 18):
            for key in ("rflags_before", "rflags_after"):
                self.assertTrue(self.check(capture(values={key: 2 | bit})))
        for key in ("rflags_before", "rflags_after"):
            self.assertTrue(self.check(capture(values={key: 0})))
        # Arithmetic flags may legitimately differ after the dry-run calls.
        self.assertEqual([], self.check(capture(values={"rflags_after": 0x8d7})))

    def test_planned_actions_depend_on_actual_wp_nxe_without_enabling_them(self):
        for wp in (False, True):
            for nxe in (False, True):
                cr0, efer = 0x80000011 | (0x10000 if wp else 0), 0x500 | (0x800 if nxe else 0)
                values = {"cr0_before": cr0, "cr0_after": cr0, "efer_before": efer, "efer_after": efer,
                          "planned_cr0": cr0 | 0x10000, "planned_efer": efer | 0x800,
                          "planned_actions": 4 | (0 if nxe else 1) | (0 if wp else 2)}
                self.assertEqual([], self.check(capture(values=values)))
                for field in ("planned_cr0", "planned_efer", "planned_actions"):
                    bad = dict(values)
                    bad[field] ^= 1 << 20
                    self.assertTrue(self.check(capture(values=bad)))
        for values in ({"planned_cr0": 0x10000}, {"planned_efer": 0x800},
                       {"planned_actions": 3}, {"planned_actions": 15}):
            self.assertTrue(self.check(capture(values=values)))

    def test_resource_order_duplicates_missing_and_incomplete_triple(self):
        for manifest in (resources()[:-1], resources() + [resources()[-1]],
                         [resources()[1], resources()[0], *resources()[2:]]):
            self.assertTrue(self.check(capture(manifest=manifest)))
        serial = capture().replace(b"memory_length=0x0000000000040000\r\n", b"", 1)
        self.assertTrue(self.check(serial))

    def test_pool_disjoint_from_every_retained_span_and_inside_arena(self):
        for index in range(19):
            manifest = resources()
            manifest[index]["base"] = 0x800000
            self.assertTrue(self.check(capture(manifest=manifest)))
        self.assertTrue(self.check(capture(values={"arena_base": 0xc00000})))

    def test_resource_end_overflow_zero_and_low4g_boundary(self):
        for base, length in ((0, 1), (0xffffffff, 2), (0xfffffffffffff000, 0x2000), (1, 0)):
            manifest = resources()
            manifest[6].update(base=base, length=length)
            self.assertTrue(self.check(capture(manifest=manifest)))
        manifest = resources()
        manifest[6].update(base=0xfffff000, length=4096)
        self.assertEqual([], self.check(capture(manifest=manifest)))

    def test_kernel_whole_window_old_cr3_and_rsdp_retention(self):
        for index, changes in ((1, {"length": 0x100000}), (5, {"base": 0x600000}),
                               (7, {"length": 35}), (8, {"base": 0x201000}),
                               (19, {"length": 0x20000})):
            manifest = resources()
            manifest[index].update(changes)
            self.assertTrue(self.check(capture(manifest=manifest)))

    def test_every_public_section_and_cpu_span_matches_linked_elf(self):
        for kind in runner.SYMBOL_SPANS:
            manifest = resources()
            manifest[kind]["base"] += 16
            with self.subTest(kind=kind):
                self.assertTrue(self.check(capture(manifest=manifest)))
        symbols = dict(SYMBOLS)
        symbols["cpu_gdt"] += 8
        self.assertTrue(self.check(symbols=symbols))
        self.assertTrue(self.check(symbols={}))

    def test_workspace_compiled_size_and_data_or_bss_containment(self):
        for base, length in ((0x200000, 0x2000), (0x204000, 0x2001), (0x226000, 0x2000)):
            manifest = resources()
            manifest[18].update(base=base, length=length)
            self.assertTrue(self.check(capture(manifest=manifest)))

    def test_negative_cases_require_exact_error_failure_and_exit(self):
        for case in runner.NEGATIVE_ERRORS:
            self.assertEqual([], self.check(case=case))
            self.assertTrue(self.check(case=case, code=33))
            self.assertTrue(self.check(capture(case).replace(b"memory_error=", b"memory_nx="), case=case))
            error = f"0x{runner.NEGATIVE_ERRORS[case]:016x}".encode()
            self.assertTrue(self.check(capture(case).replace(error, b"0x0000000000000000"), case=case))
            self.assertTrue(self.check(capture(case) + runner.STACK_READY + b"\r\n", case=case))
            self.assertTrue(self.check(capture(case) + runner.PREFLIGHT_READY + b"\r\n", case=case))
            self.assertTrue(self.check(capture(case) + runner.READY + b"\r\n", case=case))
            self.assertTrue(self.check(capture(case) + b"memory_error=0x0000000002050005\r\n", case=case))


class ElfSymbolTests(unittest.TestCase):
    def test_real_symbol_table_and_manifest_workspace_without_private_mangle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kernel.elf"
            path.write_bytes(symbol_elf())
            path.with_name("dong_layout.json").write_text(json.dumps(layout_manifest()))
            self.assertEqual(SYMBOLS, runner.read_validation_symbols(path))

    def test_truncated_invalid_elf_and_missing_layout_or_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kernel.elf"
            for data in (b"", symbol_elf()[:63], symbol_elf()[:-1], b"bad ELF" + symbol_elf()[7:]):
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    runner.read_elf_symbols(path)
            path.write_bytes(symbol_elf())
            with self.assertRaises(FileNotFoundError):
                runner.read_validation_symbols(path)
            path.with_name("dong_layout.json").write_text('{"types":[]}')
            with self.assertRaises(ValueError):
                runner.read_validation_symbols(path)

    def test_each_guard_symbol_and_compiled_runtime_layout_are_mandatory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kernel.elf"
            manifest_path = path.with_name("dong_layout.json")
            manifest_path.write_text(json.dumps(layout_manifest()))
            for names in runner.GUARD_SYMBOLS.values():
                for name in names:
                    symbols = dict(SYMBOLS)
                    del symbols[name]
                    path.write_bytes(symbol_elf(symbols))
                    with self.subTest(missing=name), self.assertRaisesRegex(ValueError, name):
                        runner.read_validation_symbols(path)
            path.write_bytes(symbol_elf())
            for change in ("missing", "size", "alignment", "offsets", "duplicate"):
                manifest = layout_manifest()
                view = manifest["types"][1]
                if change == "missing":
                    manifest["types"].pop(1)
                elif change == "size":
                    view["size"] = 152
                elif change == "alignment":
                    view["alignment"] = 16
                elif change == "offsets":
                    view["fields"][1]["offset"] = 40
                else:
                    manifest["types"].append(dict(view))
                manifest_path.write_text(json.dumps(manifest))
                with self.subTest(layout=change), self.assertRaisesRegex(ValueError, "Runtime View"):
                    runner.read_validation_symbols(path)

    def test_activation_compiled_layout_names_offsets_size_and_alignment_are_mandatory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kernel.elf"
            path.write_bytes(symbol_elf())
            manifest_path = path.with_name("dong_layout.json")
            for change in ("missing", "size", "alignment", "offset", "name", "order", "duplicate"):
                manifest = layout_manifest()
                report = manifest["types"][2]
                if change == "missing":
                    manifest["types"].pop(2)
                elif change == "size":
                    report["size"] = 104
                elif change == "alignment":
                    report["alignment"] = 16
                elif change == "offset":
                    report["fields"][-1]["offset"] = 96
                elif change == "name":
                    report["fields"][-1]["name"] = "unknown"
                elif change == "order":
                    report["fields"][0], report["fields"][1] = report["fields"][1], report["fields"][0]
                else:
                    manifest["types"].append(dict(report))
                manifest_path.write_text(json.dumps(manifest))
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "activation Report"):
                    runner.read_validation_symbols(path)

    def test_fault_symbols_required_only_for_isolated_activation_fault_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kernel.elf"
            path.with_name("dong_layout.json").write_text(json.dumps(layout_manifest()))
            normal = {name: value for name, value in SYMBOLS.items() if name not in runner.FAULT_SYMBOLS}
            path.write_bytes(symbol_elf(normal))
            self.assertEqual(normal, runner.read_validation_symbols(path))
            for case in runner.ACTIVATION_FAULTS:
                with self.subTest(case=case), self.assertRaisesRegex(ValueError, "memory_activation_test"):
                    runner.read_validation_symbols(path, case=case)
            for name in runner.FAULT_SYMBOLS:
                symbols = validation_symbols("ro-write")
                del symbols[name]
                path.write_bytes(symbol_elf(symbols))
                with self.subTest(symbol=name), self.assertRaisesRegex(ValueError, name):
                    runner.read_validation_symbols(path, case="ro-write")

    def test_mutation_compiled_report_layout_is_mandatory_and_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kernel.elf"
            path.write_bytes(symbol_elf())
            manifest_path = path.with_name("dong_layout.json")
            for change in ("missing", "size", "alignment", "offset", "name", "order", "duplicate"):
                manifest = layout_manifest()
                report = manifest["types"][3]
                if change == "missing":
                    manifest["types"].pop(3)
                elif change == "size":
                    report["size"] = 136
                elif change == "alignment":
                    report["alignment"] = 16
                elif change == "offset":
                    report["fields"][-1]["offset"] = 128
                elif change == "name":
                    report["fields"][-1]["name"] = "unknown"
                elif change == "order":
                    report["fields"][0], report["fields"][1] = report["fields"][1], report["fields"][0]
                else:
                    manifest["types"].append(dict(report))
                manifest_path.write_text(json.dumps(manifest))
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "mutation Report"):
                    runner.read_validation_symbols(path)

    def test_mutation_fault_symbols_are_required_only_for_mutation_fault_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kernel.elf"
            path.with_name("dong_layout.json").write_text(json.dumps(layout_manifest()))
            normal = {name: value for name, value in SYMBOLS.items() if name not in runner.MUTATION_FAULT_SYMBOLS}
            path.write_bytes(symbol_elf(normal))
            self.assertEqual(normal, runner.read_validation_symbols(path))
            for case in runner.MUTATION_FAULTS:
                with self.subTest(case=case), self.assertRaisesRegex(ValueError, "memory_mutation_test"):
                    runner.read_validation_symbols(path, case=case)
            for name in runner.MUTATION_FAULT_SYMBOLS:
                symbols = dict(SYMBOLS)
                del symbols[name]
                path.write_bytes(symbol_elf(symbols))
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, name):
                    runner.read_validation_symbols(path, case="tlb-ro")


class RunnerLifecycleTests(unittest.TestCase):
    def prepare(self, root, case="normal"):
        state = root / runner.STATE_DIR / case
        state.mkdir(parents=True)
        (state / "serial.log").write_bytes(b"STALE_SUCCESS")
        (state / "result.json").write_text('{"passed":true}')
        esp = state / "build/esp"
        esp.mkdir(parents=True)
        (esp.parent / "kernel.elf").write_bytes(symbol_elf(validation_symbols(case)))
        (esp.parent / "dong_layout.json").write_text(json.dumps(layout_manifest()))
        return state, esp

    def run_mock(self, root, *, case="normal", mode="success", reuse=False):
        state, esp = self.prepare(root, case)
        process = mock.Mock()
        process.returncode = runner.expected_exit_code(case)
        process.poll.return_value = process.returncode
        process.wait.return_value = process.returncode
        if mode in ("timeout", "interrupt", "exception"):
            problem = subprocess.TimeoutExpired("qemu", 1) if mode == "timeout" else KeyboardInterrupt() if mode == "interrupt" else RuntimeError("host wait failure")
            process.wait.side_effect = [problem, process.returncode]
            process.poll.side_effect = [None, process.returncode]

        def build_gate(**kwargs):
            self.assertEqual(b"", (state / "serial.log").read_bytes())
            self.assertFalse(json.loads((state / "result.json").read_text())["passed"])
            self.assertEqual(kwargs["test"], True)
            self.assertEqual(kwargs["stage"], "p1")
            if mode == "build-error":
                raise RuntimeError("build deliberately failed")
            return esp

        def launch(*args, **kwargs):
            self.assertEqual(b"", (state / "serial.log").read_bytes())
            (state / "serial.log").write_bytes(capture(case))
            return process

        with mock.patch.object(runner, "ROOT", root), mock.patch.object(runner, "build", side_effect=build_gate) as builder, \
                mock.patch.object(runner, "qemu_command", return_value=["qemu", "esp", str(esp)]), \
                mock.patch.object(runner.subprocess, "Popen", side_effect=launch) as popen:
            with redirect_stdout(io.StringIO()):
                result = runner.run_case(case, 1, normal_esp=esp if reuse else None)
        self.assertEqual(result, json.loads((state / "result.json").read_text()))
        return result, process, builder, popen

    def test_success_cpu_negatives_reuse_exact_normal_esp_and_build_cases_are_isolated(self):
        for case in runner.CASES:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                result, _, builder, _ = self.run_mock(root, case=case, reuse=case in ("no-nx", "no-pat"))
                self.assertTrue(result["passed"], result)
                if case in ("no-nx", "no-pat"):
                    builder.assert_not_called()
                    self.assertEqual(["-cpu", "qemu64,-nx" if case == "no-nx" else "qemu64,-pat"], result["command"][-2:])
                else:
                    self.assertEqual(root / runner.STATE_DIR / case / "build", builder.call_args.kwargs["output"])
                    if case != "normal":
                        self.assertEqual(case, builder.call_args.kwargs["memory_case"])
        for case in ("no-nx", "no-pat"):
            with self.subTest(case=case, standalone=True), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                result, _, builder, _ = self.run_mock(root, case=case)
                self.assertTrue(result["passed"], result)
                self.assertEqual(root / runner.STATE_DIR / "normal/build", builder.call_args.kwargs["output"])
                self.assertNotIn("memory_case", builder.call_args.kwargs)

    def test_build_failure_overwrites_stale_success_without_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, _, _, popen = self.run_mock(Path(tmp), mode="build-error")
            self.assertFalse(result["passed"])
            self.assertIsNone(result["returncode"])
            popen.assert_not_called()

    def test_new_mutation_state_keeps_preflight_and_activation_evidence_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            histories = []
            for phase in ("preflight", "activation"):
                old = root / f"build/test/memory-{phase}/normal"
                old.mkdir(parents=True)
                serial, result = f"old {phase} evidence\r\n".encode(), '{"passed":true,"phase":"' + phase + '"}'
                (old / "serial.log").write_bytes(serial)
                (old / "result.json").write_text(result)
                histories.append((old, serial, result))
            tested, _, _, _ = self.run_mock(root, case="mapped-guard")
            self.assertTrue(tested["passed"])
            for old, serial, result in histories:
                self.assertEqual(serial, (old / "serial.log").read_bytes())
                self.assertEqual(result, (old / "result.json").read_text())
            self.assertTrue((root / "build/test/memory-mutation/mapped-guard/result.json").is_file())

    def test_timeout_interrupt_and_exception_always_reap_and_fail(self):
        for mode in ("timeout", "interrupt", "exception"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                result, process, _, _ = self.run_mock(Path(tmp), mode=mode)
                self.assertFalse(result["passed"])
                process.kill.assert_called_once()
                self.assertEqual(2, process.wait.call_count)
                self.assertEqual(mode == "timeout", result["timed_out"])
                self.assertEqual(mode == "interrupt", result["interrupted"])

    def test_invalid_timeout_case_and_cli_are_rejected_before_work(self):
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                runner.run_case("normal", timeout)
        with self.assertRaises(ValueError):
            runner.run_case("unknown", 1)
        with mock.patch.object(runner, "run_case") as run:
            with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                runner.main(["--timeout", "nan"])
            run.assert_not_called()

    def test_all_cases_run_in_order_and_cpu_negatives_receive_normal_esp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []

            def run(case, timeout, *, normal_esp=None):
                calls.append((case, timeout, normal_esp))
                return {"case": case, "passed": True, "interrupted": False,
                        "esp": "normal-esp" if case == "normal" else "negative-esp"}

            with mock.patch.object(runner, "ROOT", root), mock.patch.object(runner, "run_case", side_effect=run):
                self.assertEqual(0, runner.main(["--all", "--timeout", "7"]))
            self.assertEqual([(case, 7, None if case == "normal" else "normal-esp") for case in runner.CASES], calls)
            self.assertEqual(15, len(calls))
            self.assertTrue(json.loads((root / runner.STATE_DIR / "result.json").read_text())["passed"])

    def test_cli_unexpected_host_failure_overwrites_aggregate_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / runner.STATE_DIR
            state.mkdir(parents=True)
            (state / "result.json").write_text('{"passed":true}')
            with mock.patch.object(runner, "ROOT", root), mock.patch.object(runner, "run_case", side_effect=RuntimeError("host failure")):
                self.assertEqual(1, runner.main(["--all"]))
            result = json.loads((state / "result.json").read_text())
            self.assertFalse(result["passed"])
            self.assertEqual("failed", result["status"])


if __name__ == "__main__":
    unittest.main()
