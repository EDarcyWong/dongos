#!/usr/bin/env python3
"""Gate page-table activation, live TLB mutations and real permission faults."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build import ROOT, build, qemu_command
from tools.elf_symbols import read_elf_symbols
from tests.acpi_protocol import project as project_acpi

ACTIVATION_FAULTS = {"null-page": 0, "ro-write": 3, "nx-fetch": 0x11,
                     "stack-guard": 2, "ist-guard": 0}
MUTATION_FAULTS = {"tlb-ro": 3, "tlb-unmap": 0}
CASES = ("normal", "bad-layout", "no-nx", "bad-pat", "no-pat",
         "bad-ist-layout", "mapped-guard", "bad-controls", *ACTIVATION_FAULTS, *MUTATION_FAULTS)
STATE_DIR = Path("build/test/memory-mutation")
PAGE, LOW_LIMIT, KERNEL_BASE = 4096, 1 << 32, 0xffffffff80000000
HHDM, STACK_BOTTOM, STACK_PAGES = 0xffff800000000000, 0xffff900000001000, 16
STACK_BYTES, BRIDGE_VALUE, RESOURCE_COUNT = STACK_PAGES * PAGE, 0x535441434b, 21
FIELDS = ("physical_bits", "nx", "resource_count", "arena_base", "arena_pages",
          "usable_pages", "free_pages", "pool_physical", "pool_pages", "root_physical",
          "table_count", "mapped_pages", "pat_value", "stack_physical", "stack_pages",
          "stack_bottom", "stack_top", "bridge_value", "runtime_view", "runtime_boot_info",
          "runtime_raw_map", "runtime_rsdp", "runtime_framebuffer", "runtime_pool", "ist_guard_pages",
          "cr3_before", "cr3_after", "cr0_before", "cr0_after", "cr4_before", "cr4_after",
          "efer_before", "efer_after", "rflags_before", "rflags_after",
          "planned_cr0", "planned_efer", "planned_actions")
ACTIVATION_FIELDS = ("cr3", "cr0", "cr4", "efer", "pat", "rflags", "entry_rsp", "entry_rbp",
                     "rsp", "rbp", "nested_value", "display_value", "runtime_value", "cache_steps")
NESTED_VALUE, DISPLAY_VALUE, RUNTIME_VALUE, CACHE_STEPS = 0x414354495645, 0x0055aa33, 0x52554e54494d45, 31
MUTATION_FIELDS = ("root", "virtual", "physical_a", "physical_b", "read_a", "read_b",
                   "write_value", "reuse_value", "tables_before", "tables_peak", "tables_after",
                   "invlpg_count", "reload_count", "retired_tables", "first_branch",
                   "reused_branch", "cr3_after", "steps")
MUTATION_VIRTUAL = 0xffffa00000001000
MUTATION_A, MUTATION_B, MUTATION_WRITE = 0x1122334455667788, 0x8877665544332211, 0x55aa33cc77ee9900
MUTATION_STEPS = 1023
PREFIX_MARKERS = [b"DONGOS_P1_START", b"DONGOS_P1_IMAGE_OK", b"DONGOS_P1_READY",
                  b"DONGOS_P1_EBS_RETRY", b"DONGOS_P1_EBS_OK", b"DONGOS_P1_KERNEL_HIGH_OK",
                  b"DONGOS_P2_CPU_READY", b"DONGOS_L1_PROBE_OK: 42", b"DONGOS_L1_MEMORY_OK: 373",
                  b"DONGOS_L1_SLICE_ABI_OK: 765", b"DONGOS_L1_CONSTANTS_OK: 282",
                  b"DONGOS_L1_ALIGNMENT_OK: 458", b"DONGOS_L1_GLOBALS_OK: 436",
                  b"DONGOS_L1_INTRINSICS_OK: 719", b"DONGOS_L1_FUNCTIONS_OK: 761",
                  b"DONGOS_L1_FEATURES_OK: 75"]
READY, PASS, FAIL = b"DONGOS_P2_MEMORY_READY", b"DONGOS_P1_PASS", b"DONGOS_P1_KERNEL_FAIL"
STACK_READY = b"DONGOS_P2_STACK_READY"
PREFLIGHT_READY = b"DONGOS_P2_PREFLIGHT_READY"
ACTIVATION_READY = b"DONGOS_P2_ACTIVATION_READY"
ACTIVATION_INJECT = b"DONGOS_P2_ACTIVATION_INJECT"
MUTATION_READY = b"DONGOS_P2_MUTATION_READY"
MUTATION_INJECT = b"DONGOS_P2_MUTATION_INJECT"
HARDENING_READY = b"DONGOS_P2_HARDENING_READY"
HARDENING_FIELDS = ("max_basic", "leaf7_ebx", "leaf7_ecx", "supported", "cr4_before",
                    "cr4_after", "rflags_before", "rflags_after", "cr0", "cr3", "efer", "pat", "steps")
CACHE_READY = b"DONGOS_P2_CACHE_READY"
CACHE_FIELDS = ("root", "virtual", "physical", "reused_physical", "object_size", "alignment",
                "capacity", "allocated", "oom_error", "busy_error", "reused_object", "free_before",
                "free_held", "free_after", "tables_before", "tables_peak", "tables_after",
                "invlpg_count", "reload_count", "retired_tables", "checksum", "steps", "cr4", "rflags")
PANIC = b"DONGOS_P2_PANIC"
NEGATIVE_ERRORS = {"bad-layout": 0x02050005, "no-nx": 0x02060002,
                   "bad-pat": 0x02060007, "no-pat": 0x02060007,
                   "bad-ist-layout": 0x02060005, "mapped-guard": 0x02060005,
                   "bad-controls": 0x02080001}
HEX_LINE = re.compile(rb"memory_([a-z0-9_]+)=0x([0-9a-f]{16})")
ACTIVATION_LINE = re.compile(rb"activation_([a-z0-9_]+)=0x([0-9a-f]{16})")
MUTATION_LINE = re.compile(rb"mutation_([a-z0-9_]+)=0x([0-9a-f]{16})")
PANIC_LINE = re.compile(rb"panic_([a-z0-9_]+)=0x([0-9a-f]{16})")
SEED_REGISTERS = {
    "rax": 0x1111111111111111, "rbx": 0x2222222222222222,
    "rcx": 0x3333333333333333, "rdx": 0x4444444444444444,
    "rsi": 0x5555555555555555, "rdi": 0x6666666666666666,
    "r8": 0x8888888888888888, "r9": 0x9999999999999999,
    "r10": 0xaaaaaaaaaaaaaaaa, "r11": 0xbbbbbbbbbbbbbbbb,
    "r12": 0xcccccccccccccccc, "r13": 0xdddddddddddddddd,
    "r14": 0xeeeeeeeeeeeeeeee, "r15": 0xffffffffffffffff,
}
PANIC_FIELDS = ("context", "stack", "rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp",
                "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15", "vector", "error",
                "rip", "cs", "rflags", "rsp", "ss", "cr2", "frame_symbol")
FAULT_SYMBOLS = {"memory_activation_test_expected_rip", "memory_activation_test_mid_return",
                 "memory_activation_test_inject_return", "memory_activation_test_ro_target",
                 "memory_activation_test_nx_target"}
MUTATION_FAULT_SYMBOLS = {"memory_mutation_test_expected_rip", "memory_mutation_test_mid_return",
                          "memory_mutation_test_inject_return"}
MUTATION_PAGE_SYMBOLS = {"memory_live_page_a", "memory_live_page_b"}
SYMBOL_SPANS = {
    8: ("__kernel_text_start", "__kernel_text_end"),
    9: ("__kernel_rodata_start", "__kernel_rodata_end"),
    10: ("__kernel_data_start", "__kernel_data_end"),
    11: ("__kernel_bss_start", "__kernel_bss_end"),
    12: ("cpu_gdt", "cpu_gdt_end"), 13: ("cpu_tss", "cpu_tss_end"),
    14: ("cpu_idt", "cpu_idt_end"),
    15: ("cpu_df_stack_bottom", "cpu_df_stack_top"),
    16: ("cpu_nmi_stack_bottom", "cpu_nmi_stack_top"),
    17: ("cpu_exception_stack_bottom", "cpu_exception_stack_top"),
}
WORK_SIZE = "memory_workspace_size"
VIEW_SIZE = "memory_runtime_view_size"
ACTIVATION_SIZE = "memory_activation_report_size"
MUTATION_SIZE = "memory_mutation_report_size"
GUARD_SYMBOLS = {15: ("cpu_df_guard_low", "cpu_df_guard_high"),
                 16: ("cpu_nmi_guard_low", "cpu_nmi_guard_high"),
                 17: ("cpu_exception_guard_low", "cpu_exception_guard_high")}
REQUIRED_SYMBOLS = ({name for pair in SYMBOL_SPANS.values() for name in pair}
                    | {name for pair in GUARD_SYMBOLS.values() for name in pair}
                    | {WORK_SIZE, VIEW_SIZE, ACTIVATION_SIZE, MUTATION_SIZE} | MUTATION_PAGE_SYMBOLS)


def read_validation_symbols(elf: Path, *, case="normal") -> dict[str, int]:
    symbols = read_elf_symbols(elf)
    # The private object's spelling is not an ABI. Independently verify its
    # compiled size and containment within the linked data/BSS spans instead.
    layout = json.loads(elf.with_name("dong_layout.json").read_text(encoding="utf-8"))
    types = [t for t in layout["types"] if t["full_name"] == "boot.memory_startup.Workspace"]
    if len(types) != 1 or not 0 < types[0]["size"] <= 2 * 1024 * 1024:
        raise ValueError("missing valid compiled memory workspace layout")
    symbols[WORK_SIZE] = types[0]["size"]
    views = [t for t in layout["types"] if t["full_name"] == "boot.runtime_view.View"]
    if (len(views) != 1 or views[0]["size"] != 160 or views[0]["alignment"] != 8
            or [f["offset"] for f in views[0]["fields"]] != [0, *range(48, 160, 8)]):
        raise ValueError("missing valid compiled Runtime View layout")
    symbols[VIEW_SIZE] = views[0]["size"]
    reports = [t for t in layout["types"] if t["full_name"] == "boot.activation.Report"]
    if (len(reports) != 1 or reports[0]["size"] != 112 or reports[0]["alignment"] != 8
            or [f["name"] for f in reports[0]["fields"]] != list(ACTIVATION_FIELDS)
            or [f["offset"] for f in reports[0]["fields"]] != list(range(0, 112, 8))):
        raise ValueError("missing valid compiled activation Report layout")
    symbols[ACTIVATION_SIZE] = reports[0]["size"]
    reports = [t for t in layout["types"] if t["full_name"] == "boot.live_memory.Report"]
    if (len(reports) != 1 or reports[0]["size"] != 144 or reports[0]["alignment"] != 8
            or [f["name"] for f in reports[0]["fields"]] != list(MUTATION_FIELDS)
            or [f["offset"] for f in reports[0]["fields"]] != list(range(0, 144, 8))):
        raise ValueError("missing valid compiled mutation Report layout")
    symbols[MUTATION_SIZE] = reports[0]["size"]
    extra = FAULT_SYMBOLS if case in ACTIVATION_FAULTS else MUTATION_FAULT_SYMBOLS if case in MUTATION_FAULTS else set()
    missing = (REQUIRED_SYMBOLS | extra) - symbols.keys()
    if missing:
        raise ValueError("missing memory ELF symbols: " + ", ".join(sorted(missing)))
    return symbols


def expected_exit_code(case):
    return 37 if case in ACTIVATION_FAULTS or case in MUTATION_FAULTS else 33 if case == "normal" else 35


def parse_activation_panic(lines, case, symbols, errors):
    """Validate activation or live-mutation faults and usable IST/fixed-stack frames."""
    records = []
    for position, line in enumerate(lines):
        if b"panic_" not in line:
            continue
        if line == b"panic_stack=EXCEPTION":
            records.append((position, "stack", "EXCEPTION"))
            continue
        match = PANIC_LINE.fullmatch(line)
        if match is None:
            errors.append(f"malformed activation panic diagnostic: {line!r}")
        else:
            records.append((position, match[1].decode("ascii"), int(match[2], 16)))
    names = [name for _, name, _ in records]
    frame_names = [name for name in names if re.fullmatch(r"frame_[0-9]{2}", name)]
    expected_names = [*PANIC_FIELDS, *[f"frame_{i:02d}" for i in range(len(frame_names))], "frame_count"]
    if names != expected_names:
        errors.append("activation panic fields/frames must be complete, known, unique and in fixed order")
        return {}
    if PANIC in lines:
        start = lines.index(PANIC) + 1
        if [position for position, _, _ in records] != list(range(start, len(lines))):
            errors.append("activation panic diagnostics are outside or interrupted within their stage")
    values = {name: value for _, name, value in records}
    mutation = case in MUTATION_FAULTS
    fault_symbols = MUTATION_FAULT_SYMBOLS if mutation else FAULT_SYMBOLS
    prefix = "memory_mutation_test" if mutation else "memory_activation_test"
    missing = (REQUIRED_SYMBOLS | fault_symbols) - symbols.keys()
    if missing:
        errors.append("missing activation fault ELF symbols: " + ", ".join(sorted(missing)))
        return values

    def require(condition, message):
        if not condition:
            errors.append(message)

    low, high = symbols["cpu_exception_stack_bottom"], symbols["cpu_exception_stack_top"]
    require(low < high and high - low >= 16384 and low <= values["context"] <= high - 184,
            "complete activation exception context is outside the usable EXCEPTION IST")
    require(values["context"] % 16 == 8, "activation exception context has incorrect normalized alignment")
    if mutation:
        target = MUTATION_VIRTUAL
    else:
        target = {"null-page": 0, "ro-write": symbols["memory_activation_test_ro_target"],
                  "nx-fetch": symbols["memory_activation_test_nx_target"], "stack-guard": STACK_BOTTOM - 8,
                  "ist-guard": symbols["cpu_exception_guard_low"]}[case]
        require(symbols["__kernel_rodata_start"] <= symbols["memory_activation_test_ro_target"] < symbols["__kernel_rodata_end"],
                "read-only fault target is outside linked rodata")
        require(symbols["__kernel_data_start"] <= symbols["memory_activation_test_nx_target"] < symbols["__kernel_data_end"],
                "NX fault target is outside linked data")
    rip = symbols[prefix + "_expected_rip"]
    for name in (prefix + "_mid_return", prefix + "_inject_return"):
        require(symbols["__kernel_text_start"] <= symbols[name] < symbols["__kernel_text_end"],
                "activation probe return address is outside linked text")
    if case == "nx-fetch":
        require(rip == target, "NX fault RIP symbol does not name its fetch target")
    else:
        require(symbols["__kernel_text_start"] <= rip < symbols["__kernel_text_end"],
                "activation fault RIP symbol is outside linked text")
    expected = dict(SEED_REGISTERS)
    if case != "stack-guard":
        expected["rax"] = target
    expected.update(vector=14, error=(MUTATION_FAULTS if mutation else ACTIVATION_FAULTS)[case], rip=rip, cr2=target,
                    cs=8, ss=0x10, frame_symbol=rip)
    for name, value in expected.items():
        require(values[name] == value,
                f"activation panic_{name}=0x{values[name]:016x}, expected 0x{value:016x}")
    flags = values["rflags"]
    require(flags & ((1 << 9) | (1 << 17)) == 0 and flags & (1 << 10) != 0 and flags & 2 != 0,
            "activation saved RFLAGS must have IF/VM=0, DF=1 and bit 1 set")
    rbp, rsp = values["rbp"], values["rsp"]
    require(STACK_BOTTOM <= rbp <= STACK_BOTTOM + STACK_BYTES - 16 and rbp % 16 == 0,
            "activation interrupted RBP is outside a complete aligned fixed-stack frame")
    if case == "stack-guard":
        require(rsp == STACK_BOTTOM, "stack guard fault did not preserve the boundary RSP")
    else:
        require(rsp == rbp, "activation interrupted RSP/RBP do not identify the fixed-stack leaf frame")
    count = values["frame_count"]
    require(3 <= count <= 16 and count == len(frame_names), "activation frame count is incomplete or invalid")
    expected_frames = (rip, symbols[prefix + "_mid_return"], symbols[prefix + "_inject_return"])
    for index, address in enumerate(expected_frames):
        require(values.get(f"frame_{index:02d}") == address,
                "activation frame walk lost the fault or linked fixed-stack caller returns")
    for name in frame_names[3:]:
        require(symbols["__kernel_text_start"] <= values[name] < symbols["__kernel_text_end"],
                "activation trace continued outside linked kernel text")
    return values


def parse_memory_result(serial: bytes | str, *, case="normal", symbols=None,
                        kernel_physical=None, exit_code=None) -> dict:
    """Parse complete diagnostics; return fields/resources/errors, never trust markers alone."""
    errors, fields, resources, activation, mutation = [], {}, [], {}, {}
    answer = {"fields": fields, "resources": resources, "activation": activation,
              "mutation": mutation, "errors": errors, "passed": False}
    if case not in CASES:
        errors.append(f"unknown memory case {case!r}")
        return answer
    if isinstance(serial, str):
        serial = serial.encode("utf-8")
    if serial and not serial.endswith(b"\n"):
        errors.append("unterminated serial line")
    lines = [line[:-1] if line.endswith(b"\r") else line for line in serial.split(b"\n")[:-1]]
    lines, acpi_errors = project_acpi(lines)
    errors.extend(acpi_errors)
    # This gate retains the original memory/activation/mutation contract.
    # The dedicated hardening gate additionally validates CPUID/profile and
    # hardware readbacks; project only a structurally complete optional stage.
    hardening = [i for i, line in enumerate(lines) if b"hardening_" in line or b"HARDENING" in line]
    if hardening:
        if (case in ACTIVATION_FAULTS or case in NEGATIVE_ERRORS
                or lines.count(ACTIVATION_READY) != 1):
            errors.append("hardening stage reached before successful activation")
        else:
            start = lines.index(ACTIVATION_READY) + 1
            if hardening != list(range(start, start + len(HARDENING_FIELDS) + 1)):
                errors.append("hardening stage must immediately follow activation")
        actual = []
        for i in hardening[:-1]:
            match = re.fullmatch(rb"hardening_([a-z0-9_]+)=0x([0-9a-f]{16})", lines[i])
            actual.append(match[1].decode("ascii") if match else None)
        if actual != list(HARDENING_FIELDS) or lines[hardening[-1]] != HARDENING_READY:
            errors.append("hardening stage must contain its complete ordered fields and marker")
        excluded = set(hardening)
        lines = [line for i, line in enumerate(lines) if i not in excluded]
    # The cache gate owns lifecycle semantics. Preserve the old gate's cases
    # and fields while accepting only the complete optional normal stage.
    # activation_cache_steps belongs to the older activation namespace.
    cache = [i for i, line in enumerate(lines)
             if (b"cache_" in line.lower() and not line.lower().startswith(b"activation_"))
             or b"dongos_p2_cache" in line.lower()]
    if cache:
        if case != "normal" or lines.count(MUTATION_READY) != 1 or lines.count(READY) != 1:
            errors.append("cache stage requires successful mutation and normal completion")
        else:
            start, stop = lines.index(MUTATION_READY) + 1, lines.index(READY)
            if cache != list(range(start, stop)):
                errors.append("cache stage must immediately follow mutation and precede memory ready")
        actual = []
        for i in cache[:-1]:
            match = re.fullmatch(rb"cache_([a-z0-9_]+)=0x([0-9a-f]{16})", lines[i])
            actual.append(match[1].decode("ascii") if match else None)
        if actual != list(CACHE_FIELDS) or lines[cache[-1]] != CACHE_READY:
            errors.append("cache stage must contain its complete ordered fields and marker")
        excluded = set(cache)
        lines = [line for i, line in enumerate(lines) if i not in excluded]
    is_activation_fault = case in ACTIVATION_FAULTS
    is_mutation_fault = case in MUTATION_FAULTS
    is_fault, is_rejection = is_activation_fault or is_mutation_fault, case in NEGATIVE_ERRORS
    suffix = [FAIL] if is_rejection else [STACK_READY, PREFLIGHT_READY, ACTIVATION_READY]
    if not is_rejection:
        if not is_activation_fault:
            suffix += [MUTATION_READY]
        suffix += ([ACTIVATION_INJECT, PANIC] if is_activation_fault else
                   [MUTATION_INJECT, PANIC] if is_mutation_fault else [READY, PASS])
    expected_markers = PREFIX_MARKERS + suffix
    if [line for line in lines if line.startswith(b"DONGOS")] != expected_markers:
        errors.append("guest stage markers must occur exactly once in order")
    if ((not is_fault and b"PANIC" in serial)
            or any(b"PANIC" in line and line != PANIC for line in lines)
            or any(b"FAIL" in line and not (is_rejection and line == FAIL) for line in lines)):
        errors.append("unexpected panic or guest failure")
    records = []
    for position, line in enumerate(lines):
        if b"memory_" not in line:
            continue
        match = HEX_LINE.fullmatch(line)
        if match is None:
            errors.append(f"malformed memory diagnostic: {line!r}")
        else:
            records.append((position, match[1].decode("ascii"), int(match[2], 16)))
    keys = [key for _, key, _ in records]
    expected_keys = list(FIELDS) + [key for _ in range(RESOURCE_COUNT) for key in ("kind", "base", "length")]
    if is_rejection:
        expected_keys = ["error"]
    if keys != expected_keys:
        errors.append("memory fields/resources must be complete, known, unique and in fixed order")
    last_marker = FAIL if is_rejection else STACK_READY
    if PREFIX_MARKERS[-1] in lines and last_marker in lines:
        start, stop = lines.index(PREFIX_MARKERS[-1]) + 1, lines.index(last_marker)
        if [p for p, _, _ in records] != list(range(start, stop)):
            errors.append("memory report is outside or interrupted within its stage")
    if exit_code is not None and exit_code != expected_exit_code(case):
        errors.append("wrong guest exit code")
    if keys != expected_keys:
        return answer
    if is_rejection:
        fields["error"] = records[0][2]
        if fields["error"] != NEGATIVE_ERRORS[case]:
            errors.append("wrong deliberate-rejection error")
        if any(b"activation_" in line or b"mutation_" in line or b"panic_" in line for line in lines):
            errors.append("rejected preflight reached activation or panic diagnostics")
        answer["passed"] = not errors
        return answer
    fields.update({key: value for _, key, value in records[:len(FIELDS)]})
    for index in range(RESOURCE_COUNT):
        group = records[len(FIELDS) + index * 3:len(FIELDS) + (index + 1) * 3]
        resources.append(dict(zip(("kind", "base", "length"), (value for _, _, value in group))))
    f, r = fields, resources

    def require(condition, message):
        if not condition:
            errors.append(message)

    def contains(outer, base, length):
        return outer["base"] <= base and base + length <= outer["base"] + outer["length"]

    require(32 <= f["physical_bits"] <= 52 and f["nx"] == 1, "invalid CPU memory capabilities")
    require(f["resource_count"] == RESOURCE_COUNT and [x["kind"] for x in r] == list(range(RESOURCE_COUNT)), "invalid resource count/order")
    require((f["pat_value"] & 0xff) == 6 and ((f["pat_value"] >> 24) & 0xff) == 0,
            "PAT entry 0 must be WB and entry 3 must be UC")
    require(f["arena_pages"] == 1024 and 0 < f["arena_base"] < LOW_LIMIT and f["arena_base"] % (1024 * PAGE) == 0
            and f["arena_base"] + 1024 * PAGE <= LOW_LIMIT, "invalid 4 MiB low arena")
    require(f["pool_pages"] == 128 and f["pool_physical"] % (128 * PAGE) == 0, "invalid order-7 table pool")
    require(f["arena_base"] <= f["pool_physical"] and f["pool_physical"] + 128 * PAGE <= f["arena_base"] + 1024 * PAGE,
            "pool is outside the arena")
    require(f["stack_pages"] == STACK_PAGES and f["stack_physical"] % STACK_BYTES == 0,
            "invalid order-4 stack allocation")
    require(f["arena_base"] <= f["stack_physical"]
            and f["stack_physical"] + STACK_BYTES <= f["arena_base"] + 1024 * PAGE,
            "stack is outside the arena")
    require(f["stack_bottom"] == STACK_BOTTOM and f["stack_top"] == STACK_BOTTOM + STACK_BYTES,
            "invalid reserved stack virtual range")
    require(f["bridge_value"] == BRIDGE_VALUE, "new-stack callback bridge did not complete")
    require(f["free_pages"] + f["pool_pages"] + f["stack_pages"] == f["usable_pages"] <= 1024,
            "allocator page accounting mismatch")
    require(1 <= f["table_count"] <= 128, "invalid used table count")
    require(f["root_physical"] == f["pool_physical"] and f["root_physical"] != f["cr3_before"], "root ownership mismatch")
    require(0 < f["cr3_before"] < LOW_LIMIT and f["cr3_before"] % PAGE == 0 and f["cr3_before"] == f["cr3_after"],
            "active CR3 changed or is invalid")
    for register in ("cr0", "cr4", "efer"):
        require(f[register + "_before"] == f[register + "_after"], f"active {register.upper()} changed during preflight")
    cr0, cr4, efer = f["cr0_before"], f["cr4_before"], f["efer_before"]
    require(cr0 & 0x80000001 == 0x80000001 and cr0 & 0x60000000 == 0,
            "CR0 must retain PE/PG with CD/NW clear")
    require(cr4 & (1 << 5) != 0 and cr4 & ((1 << 7) | (1 << 12) | (1 << 17) | (1 << 23)) == 0,
            "CR4 must retain PAE with PGE/LA57/PCIDE/CET clear")
    require(efer & 0x500 == 0x500, "EFER must retain LME/LMA")
    flags_mask = (1 << 9) | (1 << 10) | (1 << 17) | (1 << 18)
    require(f["rflags_before"] & flags_mask == f["rflags_after"] & flags_mask == 0,
            "IF/DF/VM/AC must remain clear during preflight")
    require(f["rflags_before"] & 2 != 0 and f["rflags_after"] & 2 != 0,
            "architecturally fixed RFLAGS bit 1 must remain set")
    require(f["planned_cr0"] == cr0 | 0x10000 and f["planned_efer"] == efer | 0x800,
            "activation plan does not preserve current CR0/EFER while adding WP/NXE")
    actions = 4 | (0 if efer & 0x800 else 1) | (0 if cr0 & 0x10000 else 2)
    require(f["planned_actions"] == actions, "activation action mask differs from current NXE/WP state")
    require(f["ist_guard_pages"] == 6, "three ISTs require six guard pages")
    require(r[0] == {"kind": 0, "base": 0, "length": PAGE}, "physical zero page is not fully reserved")
    for item in r:
        require((item["kind"] == 0 or item["base"] > 0) and item["base"] < LOW_LIMIT
                and 0 < item["length"] <= LOW_LIMIT - item["base"], f"invalid resource span {item['kind']}")
    for index in range(1, 6):
        require(r[index]["base"] % PAGE == 0 and r[index]["length"] % PAGE == 0, f"unaligned allocation envelope {index}")
    kernel = r[8]["base"]
    require(kernel % (2 * 1024 * 1024) == 0 and contains(r[1], kernel, 2 * 1024 * 1024), "kernel allocation envelope mismatch")
    if kernel_physical is not None:
        require(kernel == kernel_physical, "kernel physical placement mismatch")
    require(r[2]["length"] >= 160 and r[3]["length"] >= 40 and r[4]["length"] >= 65536, "undersized boot resource envelope")
    require(contains(r[5], f["cr3_before"], PAGE), "old CR3 is outside its retained envelope")
    require(36 <= r[7]["length"] <= PAGE, "invalid retained RSDP length")
    require(r[19]["base"] == f["pool_physical"] and r[19]["length"] == 128 * PAGE, "manifest pool differs from allocator pool")
    require(r[20]["base"] == f["stack_physical"] and r[20]["length"] == STACK_BYTES,
            "manifest stack differs from allocator stack")
    for key, envelope, size in (("runtime_boot_info", r[2], 160), ("runtime_raw_map", r[3], 40)):
        address = f[key]
        require(HHDM < address < HHDM + LOW_LIMIT and address + size <= HHDM + LOW_LIMIT
                and contains(envelope, address - HHDM, size), f"{key} is outside its HHDM allocation envelope")
    require(f["runtime_rsdp"] == HHDM + r[7]["base"], "Runtime RSDP does not match retained physical resource")
    require(f["runtime_framebuffer"] == HHDM + r[6]["base"], "Runtime GOP does not match retained physical resource")
    require(f["runtime_pool"] == HHDM + f["pool_physical"], "Runtime pool is not the allocated pool's HHDM alias")
    for index in (19, 20):
        for item in r[:index]:
            require(not (r[index]["base"] < item["base"] + item["length"]
                         and item["base"] < r[index]["base"] + r[index]["length"]),
                    f"allocated resource {index} overlaps retained resource {item['kind']}")
    symbols = symbols or {}
    missing = REQUIRED_SYMBOLS - symbols.keys()
    require(not missing, "missing independent ELF validation symbols: " + ", ".join(sorted(missing)))
    if not missing:
        require(symbols[ACTIVATION_SIZE] == 112, "compiled activation Report size mismatch")
        require(symbols[MUTATION_SIZE] == 144, "compiled mutation Report size mismatch")
        require(symbols["__kernel_text_start"] == KERNEL_BASE, "wrong linked kernel base")
        section_ends = []
        for kind, (start, end) in SYMBOL_SPANS.items():
            low, high = symbols[start], symbols[end]
            require(KERNEL_BASE <= low < high <= symbols["__kernel_bss_end"], f"invalid ELF span {kind}")
            require(r[kind]["base"] == kernel + low - KERNEL_BASE and r[kind]["length"] == high - low,
                    f"resource {kind} does not match independent ELF symbols")
            if kind < 12:
                require(low % PAGE == 0 and high % PAGE == 0, "unaligned linked kernel section")
                section_ends.append((low, high))
        require(all(section_ends[i][1] == section_ends[i + 1][0] for i in range(3)), "noncontiguous linked kernel sections")
        require(symbols["__kernel_bss_end"] - KERNEL_BASE <= 2 * 1024 * 1024, "kernel exceeds retained 2 MiB window")
        guard_windows = []
        guard_pages = set()
        for kind, (low_name, high_name) in GUARD_SYMBOLS.items():
            bottom, top = (symbols[name] for name in SYMBOL_SPANS[kind])
            low, high = symbols[low_name], symbols[high_name]
            require(low == bottom - PAGE and high == top and bottom % PAGE == 0 and top % PAGE == 0
                    and symbols["__kernel_bss_start"] <= low < bottom < top < high + PAGE <= symbols["__kernel_bss_end"],
                    f"invalid linked IST guard window {kind}")
            guard_windows.append((low, high + PAGE))
            guard_pages.update((low, high))
        guard_windows.sort()
        require(all(guard_windows[i][1] <= guard_windows[i + 1][0] for i in range(2)),
                "linked IST guard windows overlap")
        view = f["runtime_view"]
        require(symbols[VIEW_SIZE] == 160 and any(symbols[start] <= view and view + 160 <= symbols[end]
                for start, end in (SYMBOL_SPANS[10], SYMBOL_SPANS[11]))
                and not any(view < page + PAGE and page < view + 160 for page in guard_pages),
                "Runtime View is outside mapped kernel data/BSS storage")
        # Count the union of mappings whose exact spans are independently known.
        # The raw object's full length is not reported, so only its minimum
        # descriptor span is counted; merged envelopes are never guessed.
        spans = [(KERNEL_BASE, symbols["__kernel_bss_end"] - KERNEL_BASE),
                 (STACK_BOTTOM, STACK_BYTES), (HHDM + f["stack_physical"], STACK_BYTES),
                 (HHDM + f["pool_physical"], 128 * PAGE), (HHDM + f["cr3_before"], PAGE),
                 (HHDM + r[6]["base"], r[6]["length"]), (HHDM + r[7]["base"], r[7]["length"]),
                 (f["runtime_boot_info"], 160), (f["runtime_raw_map"], 40)]
        intervals = sorted((base // PAGE, (base + length + PAGE - 1) // PAGE) for base, length in spans)
        minimum_pages, previous_end = 0, 0
        for start, end in intervals:
            minimum_pages += max(0, end - max(start, previous_end))
            previous_end = max(previous_end, end)
        minimum_pages -= 6
        require(f["mapped_pages"] >= minimum_pages, "missing kernel/stack/pool/GOP/RSDP mappings excluding IST guards")
        require(r[18]["length"] == symbols[WORK_SIZE] and any(contains(r[kind], r[18]["base"], r[18]["length"])
                for kind in (10, 11)), "workspace does not match compiled size/data/BSS placement")
        page_a, page_b = symbols["memory_live_page_a"], symbols["memory_live_page_b"]
        require(page_a % PAGE == 0 and page_b == page_a + PAGE
                and symbols["__kernel_bss_start"] <= page_a < page_b
                and page_b + PAGE <= symbols["__kernel_bss_end"]
                and not any(page_a <= page < page_b + PAGE for page in guard_pages),
                "mutation RAM pages must be consecutive aligned usable linked BSS pages")
        require(not any(page_a < symbols[end] and symbols[start] < page_b + PAGE
                        for kind, (start, end) in SYMBOL_SPANS.items() if kind >= 12)
                and not (page_a < view + symbols[VIEW_SIZE] and view < page_b + PAGE)
                and not (kernel + page_a - KERNEL_BASE < r[18]["base"] + r[18]["length"]
                         and r[18]["base"] < kernel + page_b - KERNEL_BASE + PAGE),
                "mutation RAM overlaps CPU storage, Runtime View or paging workspace")
    activation_records = []
    for position, line in enumerate(lines):
        if b"activation_" not in line:
            continue
        match = ACTIVATION_LINE.fullmatch(line)
        if match is None:
            errors.append(f"malformed activation diagnostic: {line!r}")
        else:
            activation_records.append((position, match[1].decode("ascii"), int(match[2], 16)))
    if [name for _, name, _ in activation_records] != list(ACTIVATION_FIELDS):
        errors.append("activation fields must be complete, known, unique and in fixed order")
    if PREFLIGHT_READY in lines and ACTIVATION_READY in lines:
        start, stop = lines.index(PREFLIGHT_READY) + 1, lines.index(ACTIVATION_READY)
        require([p for p, _, _ in activation_records] == list(range(start, stop)),
                "activation report is outside or interrupted within its stage")
    if [name for _, name, _ in activation_records] == list(ACTIVATION_FIELDS):
        activation.update({name: value for _, name, value in activation_records})
        a = activation
        require(a["cr3"] == f["root_physical"] != f["cr3_before"], "new CR3 was not activated")
        require(a["cr0"] == f["planned_cr0"] and a["efer"] == f["planned_efer"],
                "active WP/NXE controls differ from the preservation plan")
        require(a["cr4"] == f["cr4_before"] and a["pat"] == f["pat_value"],
                "activation changed CR4 or PAT")
        require(a["rflags"] & flags_mask == 0 and a["rflags"] & 2 != 0,
                "activation RFLAGS must retain bit 1 with IF/DF/VM/AC clear")
        require(a["entry_rsp"] == STACK_BOTTOM + STACK_BYTES and a["entry_rbp"] == 0,
                "handoff did not start at the fixed stack top with a cleared RBP")
        require(STACK_BOTTOM <= a["rsp"] < STACK_BOTTOM + STACK_BYTES and a["rsp"] % 16 == 8,
                "nested call RSP is outside the aligned fixed stack")
        require(STACK_BOTTOM <= a["rbp"] <= STACK_BOTTOM + STACK_BYTES - 16 and a["rbp"] % 16 == 0,
                "nested call RBP is outside the complete fixed-stack frame")
        require(a["nested_value"] == NESTED_VALUE, "fixed-stack nested call did not complete")
        require(a["display_value"] == DISPLAY_VALUE, "Runtime framebuffer write/readback did not complete")
        require(a["runtime_value"] == RUNTIME_VALUE, "Runtime retained-object access did not complete")
        require(a["cache_steps"] == CACHE_STEPS, "cache transition did not complete every required step")
    mutation_records = []
    for position, line in enumerate(lines):
        if b"mutation_" not in line:
            continue
        match = MUTATION_LINE.fullmatch(line)
        if match is None:
            errors.append(f"malformed mutation diagnostic: {line!r}")
        else:
            mutation_records.append((position, match[1].decode("ascii"), int(match[2], 16)))
    if is_activation_fault:
        require(not mutation_records, "early activation fault unexpectedly reached mutation diagnostics")
    else:
        require([name for _, name, _ in mutation_records] == list(MUTATION_FIELDS),
                "mutation fields must be complete, known, unique and in fixed order")
        if ACTIVATION_READY in lines and MUTATION_READY in lines:
            start, stop = lines.index(ACTIVATION_READY) + 1, lines.index(MUTATION_READY)
            require([p for p, _, _ in mutation_records] == list(range(start, stop)),
                    "mutation report is outside or interrupted within its stage")
        if [name for _, name, _ in mutation_records] == list(MUTATION_FIELDS):
            mutation.update({name: value for _, name, value in mutation_records})
            m = mutation
            require(m["root"] == m["cr3_after"] == f["root_physical"],
                    "mutation changed the active CR3 root")
            require(m["virtual"] == MUTATION_VIRTUAL, "mutation target differs from the isolated virtual window")
            if not missing:
                for suffix in ("a", "b"):
                    physical = kernel + symbols["memory_live_page_" + suffix] - KERNEL_BASE
                    require(m["physical_" + suffix] == physical,
                            "mutation physical page does not match its independent linked BSS symbol")
            require(m["physical_a"] != m["physical_b"] and m["physical_b"] == m["physical_a"] + PAGE
                    and 0 < m["physical_a"] < m["physical_b"] < LOW_LIMIT
                    and m["physical_a"] % PAGE == m["physical_b"] % PAGE == 0,
                    "mutation backing RAM pages must be distinct consecutive aligned low pages")
            require(m["read_a"] == MUTATION_A and m["read_b"] == MUTATION_B,
                    "warm mapping replacement did not return the distinct physical-page tokens")
            require(m["write_value"] == MUTATION_WRITE and m["reuse_value"] == MUTATION_A,
                    "mutation write/readback or reclaimed-branch remap did not complete")
            require(m["tables_before"] == m["tables_after"] == f["table_count"]
                    and m["tables_peak"] == f["table_count"] + 3 <= f["pool_pages"],
                    "mutation table allocation/reclamation accounting differs from the private three-table branch")
            require(m["invlpg_count"] == 5 and m["reload_count"] == 2 and m["retired_tables"] == 6,
                    "mutation did not execute every leaf invalidation and full-flush reclamation")
            branch = m["first_branch"]
            require(branch == m["reused_branch"] and branch % PAGE == 0
                    and f["pool_physical"] < branch < f["pool_physical"] + f["pool_pages"] * PAGE,
                    "reclaimed mutation branch did not reuse the same owned non-root table page")
            require(m["steps"] == MUTATION_STEPS, "mutation did not complete every required lifecycle step")
    if is_fault:
        answer["panic"] = parse_activation_panic(lines, case, symbols, errors)
    elif any(b"panic_" in line for line in lines):
        errors.append("normal completion contains panic diagnostics")
    answer["passed"] = not errors
    return answer


def check_result(returncode, serial, timed_out, case, symbols):
    parsed = parse_memory_result(serial, case=case, symbols=symbols)
    errors = list(parsed["errors"])
    if timed_out:
        errors.append("QEMU memory startup timed out")
    expected = expected_exit_code(case)
    if returncode != expected:
        errors.append(f"guest exit code {returncode}, expected {expected}")
    return errors


def write_json(path, result):
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def reap_process(process):
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


def run_case(case, timeout=60.0, *, normal_esp=None):
    if case not in CASES or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("known case and finite positive timeout required")
    state = ROOT / STATE_DIR / case
    state.mkdir(parents=True, exist_ok=True)
    serial_path, result_path = state / "serial.log", state / "result.json"
    serial_path.write_bytes(b"")
    result = {"case": case, "passed": False, "status": "building", "command": None,
              "returncode": None, "timed_out": False, "interrupted": False, "errors": []}
    write_json(result_path, result)
    process, started = None, time.monotonic()
    try:
        if case in ("no-nx", "no-pat") and normal_esp is not None:
            esp = Path(normal_esp)
        else:
            output = (ROOT / STATE_DIR / "normal/build") if case in ("no-nx", "no-pat") else state / "build"
            kwargs = {"test": True, "stage": "p1", "output": output}
            if case not in ("normal", "no-nx", "no-pat"):
                kwargs["memory_case"] = case
            esp = build(**kwargs)
        result["esp"] = str(esp)
        elf = esp.parent / "kernel.elf"
        symbols = read_validation_symbols(elf, case=case)
        result["kernel_elf"] = str(elf)
        command = qemu_command(esp, state, test=True)
        if case in ("no-nx", "no-pat"):
            command += ["-cpu", "qemu64,-nx" if case == "no-nx" else "qemu64,-pat"]
        result.update(command=command, status="running")
        write_json(result_path, result)
        with (state / "qemu.stdout.log").open("wb") as stdout, (state / "qemu.stderr.log").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
            try:
                result["returncode"] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                result["timed_out"] = True
                reap_process(process)
                result["returncode"] = process.returncode
            except BaseException:
                reap_process(process)
                result["returncode"] = process.returncode
                raise
        serial = serial_path.read_bytes()
        result["errors"] = check_result(result["returncode"], serial, result["timed_out"], case, symbols)
        result["report"] = parse_memory_result(serial, case=case, symbols=symbols)
    except KeyboardInterrupt:
        result["interrupted"] = True
        result["errors"].append("host interrupted memory startup")
    except Exception as exc:
        result["errors"].append(f"host {type(exc).__name__}: {exc}")
    finally:
        if process is not None and process.poll() is None:
            try:
                reap_process(process)
            except Exception as exc:
                result["errors"].append(f"QEMU cleanup failed: {exc}")
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["timing_scope"] = "host build plus QEMU including firmware; not a boot-performance metric"
        result["passed"] = not result["errors"]
        result["status"] = "interrupted" if result["interrupted"] else "passed" if result["passed"] else "failed"
        write_json(result_path, result)
    print(f"{'PASS' if result['passed'] else 'FAIL'} memory startup/{case}; logs: {state}", flush=True)
    for error in result["errors"]:
        print("  " + error)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    select = parser.add_mutually_exclusive_group()
    select.add_argument("--case", choices=CASES, default=None)
    select.add_argument("--all", action="store_true")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    directory = ROOT / STATE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    aggregate = directory / "result.json"
    results, normal_esp = [], None
    write_json(aggregate, {"passed": False, "status": "running", "results": results})
    try:
        for case in CASES if args.all else [args.case or "normal"]:
            result = run_case(case, args.timeout, normal_esp=normal_esp)
            results.append(result)
            if case == "normal":
                normal_esp = result.get("esp")
            write_json(aggregate, {"passed": False, "status": "running", "results": results})
            if result.get("interrupted"):
                break
    except (Exception, KeyboardInterrupt) as exc:
        write_json(aggregate, {"passed": False, "status": "failed", "error": f"{type(exc).__name__}: {exc}", "results": results})
        return 130 if isinstance(exc, KeyboardInterrupt) else 1
    interrupted = any(result["interrupted"] for result in results)
    passed = bool(results) and all(result["passed"] for result in results)
    write_json(aggregate, {"passed": passed, "status": "interrupted" if interrupted else "complete", "results": results})
    return 130 if interrupted else 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
