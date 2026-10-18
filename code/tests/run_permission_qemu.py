#!/usr/bin/env python3
"""Gate real SMEP/SMAP user mappings and CPL3 UMIP instructions."""
from __future__ import annotations

import argparse
import importlib.util
import math
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build import ROOT, build, qemu_command
from tools.elf_image import materialize

_spec = importlib.util.spec_from_file_location("permission_cache_gate", Path(__file__).with_name("run_cache_qemu.py"))
cache = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cache)
hardening, memory = cache.hardening, cache.memory

FIELDS = ("case_id", "cr0", "cr3", "cr4", "efer", "pat", "rflags", "ac_flags", "ac_read", "ac_write",
          "code_va", "data_va", "stack_top", "probe_rip", "code_pa", "data_pa", "stack_pa",
          "code_pml4", "code_pdpt", "code_pd", "code_pte", "data_pml4", "data_pdpt", "data_pd", "data_pte",
          "stack_pml4", "stack_pdpt", "stack_pd", "stack_pte", "gdt_base", "gdt_limit", "idt_base",
          "idt_limit", "ldtr", "tr", "msw", "steps")
READY = b"DONGOS_P2_PERMISSION_READY"
INJECT = b"DONGOS_P2_PERMISSION_INJECT"
PASS = b"DONGOS_P2_PERMISSION_PASS"
LINE = re.compile(rb"permission_([a-z0-9_]+)=0x([0-9a-f]{16})")
STATE_DIR = Path("build/test/permissions/qemu")
CASES = ("smep", "smep-off", "nx-control", "smap-read", "smap-write", "smap-off",
         "umip-sgdt", "umip-sidt", "umip-sldt", "umip-smsw", "umip-str", "umip-off")
PROFILE = {case: {"smep-off": "no-smep", "nx-control": "no-smep", "smap-off": "no-smap",
                  "umip-off": "no-umip"}.get(case, "all-features") for case in CASES}
SUCCESS = {"smep-off", "smap-off"}
USER_CODE, USER_DATA, USER_STACK_TOP = 0x40000000, 0x40001000, 0x40003000
TOKEN, WRITE = 0x1122334455667788, 0x55aa33cc77ee9900
NX, ACCESSED_DIRTY = 1 << 63, 0x60
REPORT_SIZE, OPCODES_VERIFIED = "permission_report_size", "permission_opcodes_verified"
# These are independently bound to linked text/BSS, never trusted serial addresses.
BACKING = {"code": "permission_code_page", "data": "permission_data_page", "stack": "permission_stack_page"}
TABLES = ("permission_pdpt", "permission_pd", "permission_pt")
GDT = "permission_shadow_gdt"
PROBE = {"smep": "permission_user_call_stub", "smep-off": "permission_user_call_stub", "nx-control": "permission_user_call_stub",
         "smap-read": "permission_test_expected_rip", "smap-write": "permission_test_expected_rip", "smap-off": "permission_test_expected_rip",
         **{"umip-" + name: "permission_user_" + name for name in ("sgdt", "sidt", "sldt", "smsw", "str")},
         "umip-off": "permission_user_exit_hlt"}
RETURN_SYMBOLS = ("permission_test_mid_return", "permission_test_inject_return")
OPCODES = {"permission_user_call_stub": bytes.fromhex("48b88877665544332211c3"),
           "permission_user_sgdt": bytes.fromhex("0f0107"),
           "permission_user_sidt": bytes.fromhex("0f014f10"),
           "permission_user_sldt": bytes.fromhex("0f004720"),
           "permission_user_smsw": bytes.fromhex("0f016722"),
           "permission_user_str": bytes.fromhex("0f004f24"),
           "permission_user_exit_hlt": b"\xf4"}
UMIP_ORDER = tuple("permission_user_" + name for name in ("sgdt", "sidt", "sldt", "smsw", "str"))
write_json = hardening.write_json


def opcode_contract(case):
    if case.startswith("smap-"):
        return {PROBE[case]: bytes.fromhex("c6005a" if case == "smap-write" else "488b18")}
    return dict(OPCODES) if case == "umip-off" else {PROBE[case]: OPCODES[PROBE[case]]}


def required_symbols():
    return ({"permission_report", "permission_report_end", GDT, GDT + "_end", *BACKING.values(), *TABLES, *RETURN_SYMBOLS}
            | set(PROBE.values()) | {"permission_report_" + name for name in FIELDS})


def read_validation_symbols(elf, *, case="smep"):
    if case not in CASES:
        raise ValueError("unknown permission case")
    elf = Path(elf)
    symbols = cache.read_validation_symbols(elf)
    missing = required_symbols() - symbols.keys()
    if missing:
        raise ValueError("missing permission ELF symbols: " + ", ".join(sorted(missing)))
    report = symbols["permission_report"]
    if report % 8 or symbols["permission_report_end"] - report != 296 or any(
            symbols["permission_report_" + name] != report + index * 8 for index, name in enumerate(FIELDS)):
        raise ValueError("permission report must have the exact 296-byte thirty-seven-field ELF ABI")
    if not (symbols["__kernel_bss_start"] <= report < report + 296 <= symbols["__kernel_bss_end"]):
        raise ValueError("permission report is outside linked BSS")
    for kind, symbol in BACKING.items():
        address = symbols[symbol]
        low, high = (symbols["__kernel_text_start"], symbols["__kernel_text_end"]) if kind == "code" else (
            symbols["__kernel_bss_start"], symbols["__kernel_bss_end"])
        if address % 4096 or not low <= address < address + 4096 <= high:
            raise ValueError("permission backing must occupy an aligned complete linked " + kind + " page")
    if len({symbols[name] for name in BACKING.values()}) != 3:
        raise ValueError("permission backing pages overlap")
    pages = [symbols[name] for name in (*BACKING.values(), *TABLES)]
    if len(set(pages)) != len(pages) or any(symbols[name] % 4096 or not (
            symbols["__kernel_bss_start"] <= symbols[name] <= symbols["__kernel_bss_end"] - 4096) for name in TABLES):
        raise ValueError("permission private table pages must occupy distinct aligned complete BSS pages")
    if not (symbols["__kernel_data_start"] <= symbols[GDT] <= symbols["__kernel_bss_end"] - 56):
        raise ValueError("permission shadow GDT is outside retained writable kernel storage")
    if symbols[GDT + "_end"] - symbols[GDT] != 56:
        raise ValueError("permission shadow GDT must preserve original 40 bytes plus two user descriptors")
    image = materialize(elf.read_bytes())
    if case == "umip-off" and any(symbols[right] != symbols[left] + len(OPCODES[left])
                                  for left, right in zip(UMIP_ORDER, UMIP_ORDER[1:])):
        raise ValueError("permission UMIP-off instructions must be consecutive in their exact execution order")
    for name, opcode in opcode_contract(case).items():
        address = symbols[name]
        if name.startswith("permission_user_"):
            if not symbols[BACKING["code"]] <= address < symbols[BACKING["code"]] + 4096:
                raise ValueError("permission user instruction is outside its isolated executable backing page")
        elif not symbols["__kernel_text_start"] <= address < symbols["__kernel_text_end"]:
            raise ValueError("permission supervisor instruction is outside linked text")
        offset = address - memory.KERNEL_BASE
        if image[offset:offset + len(opcode)] != opcode:
            raise ValueError("permission target opcode differs from independent instruction contract: " + name)
    symbols[REPORT_SIZE], symbols[OPCODES_VERIFIED] = 296, 1
    return symbols


def expected_rip(case, symbols):
    address = symbols[PROBE[case]]
    return USER_CODE + address - symbols[BACKING["code"]] if case.startswith("umip-") or case in (
        "smep", "smep-off", "nx-control") else address


def parse_panic(lines, case, fields, symbols, errors):
    records = []
    for position, line in enumerate(lines):
        if b"panic_" not in line.lower():
            continue
        if line == b"panic_stack=EXCEPTION":
            records.append((position, "stack", "EXCEPTION"))
            continue
        match = memory.PANIC_LINE.fullmatch(line)
        if match is None:
            errors.append(f"malformed permission panic diagnostic: {line!r}")
        else:
            records.append((position, match[1].decode("ascii"), int(match[2], 16)))
    names = [name for _, name, _ in records]
    frames = [name for name in names if re.fullmatch(r"frame_[0-9]{2}", name)]
    if names != [*memory.PANIC_FIELDS, *[f"frame_{i:02d}" for i in range(len(frames))], "frame_count"]:
        errors.append("permission panic fields/frames must be complete, known, unique and ordered")
        return {}
    if memory.PANIC not in lines or [p for p, _, _ in records] != list(range(lines.index(memory.PANIC) + 1, len(lines))):
        errors.append("permission panic must exclusively complete its fatal stage")
    values = {name: value for _, name, value in records}

    def require(condition, message):
        if not condition:
            errors.append(message)

    low, high = symbols["cpu_exception_stack_bottom"], symbols["cpu_exception_stack_top"]
    require(low <= values["context"] <= high - 184 and values["context"] % 16 == 8,
            "permission fault lost the complete aligned 184-byte IST context")
    user = case.startswith("umip-")
    rip = expected_rip(case, symbols)
    expected = dict(memory.SEED_REGISTERS, vector=13 if user else 14,
                    error=0 if user else 1 if case == "smap-read" else 3 if case == "smap-write" else 0x11,
                    rip=rip, cs=0x2b if user else 8, ss=0x33 if user else 0x10,
                    cr2=0 if user else USER_DATA if case.startswith("smap-") else rip,
                    frame_symbol=rip)
    if user:
        expected.update(rdi=USER_DATA, rbp=0, rsp=USER_STACK_TOP)
        if case == "umip-off":
            expected.update(rax=fields["gdt_base"], rbx=fields["idt_base"], rcx=fields["gdt_limit"],
                            rdx=fields["idt_limit"], rsi=fields["ldtr"], rdi=fields["msw"], r8=fields["tr"])
            expected.pop("r9")
            require(values["r9"] & hardening.FLAGS_MASK == 0 and values["r9"] & 2 != 0,
                    "UMIP-off must retain actual CPL3 RFLAGS with IF/DF/VM/AC clear")
        require(values["frame_count"] == len(frames) == 1,
                "CPL3 panic must retain only interrupted RIP and never traverse user RBP")
    else:
        expected.update(rax=USER_DATA)
        if case in ("smep", "nx-control"):
            expected["rax"] = rip
        require(memory.STACK_BOTTOM <= values["rbp"] <= memory.STACK_BOTTOM + memory.STACK_BYTES - 16
                and values["rbp"] % 16 == 0
                and values["rsp"] == values["rbp"] - (8 if case in ("smep", "nx-control") else 0),
                "supervisor permission fault lost its aligned fixed-stack frame")
        require(3 <= values["frame_count"] <= 16 and values["frame_count"] == len(frames),
                "supervisor permission fault lost its nested trusted trace")
        for index, name in enumerate(RETURN_SYMBOLS, 1):
            require(values.get(f"frame_{index:02d}") == symbols[name], "permission trace lost its linked return frame")
        require(all(symbols["__kernel_text_start"] <= values[name] < symbols["__kernel_text_end"] for name in frames[3:]),
                "supervisor permission trace continued outside linked kernel text")
    for name, value in expected.items():
        require(values[name] == value, f"permission panic_{name} differs from independent instruction/context contract")
    require(values.get("frame_00") == rip, "permission frame 00 differs from actual interrupted RIP")
    flags = values["rflags"]
    require(flags & ((1 << 9) | (1 << 17) | (1 << 18)) == 0 and flags & 2 != 0
            and bool(flags & (1 << 10)) == (not user),
            "permission saved RFLAGS lost original CPL-specific IF/DF/VM/AC contract")
    return values


def parse_result(serial, *, case="smep", symbols=None):
    answer = {"permission": {}, "cache": {}, "panic": {}, "errors": [], "passed": False}
    errors, symbols = answer["errors"], symbols or {}
    if case not in CASES:
        errors.append(f"unknown permission case {case!r}")
        return answer
    if isinstance(serial, str):
        serial = serial.encode("utf-8")
    if serial and not serial.endswith(b"\n"):
        errors.append("unterminated permission serial line")
    lines = [line[:-1] if line.endswith(b"\r") else line for line in serial.split(b"\n")[:-1]]
    records = []
    for position, line in enumerate(lines):
        if any(marker in line.upper() and line != marker for marker in (READY, INJECT, PASS)):
            errors.append("permission marker must occupy its own exact line")
        if b"permission_" not in line.lower() or line in (READY, INJECT, PASS):
            continue
        match = LINE.fullmatch(line)
        if match is None:
            errors.append(f"malformed permission diagnostic: {line!r}")
        else:
            records.append((position, match[1].decode("ascii"), int(match[2], 16)))
    names = [name for _, name, _ in records]
    if names != list(FIELDS):
        errors.append("permission fields must be complete, known, unique and ordered")
    fatal = case not in SUCCESS
    tail = [READY, INJECT, memory.PANIC] if fatal else [READY, INJECT, PASS]
    expected_markers = [*memory.PREFIX_MARKERS, memory.STACK_READY, memory.PREFLIGHT_READY,
                        memory.ACTIVATION_READY, hardening.READY, memory.MUTATION_READY, cache.READY, *tail]
    if [line for line in lines if line.startswith(b"DONGOS")] != expected_markers:
        errors.append("permission guest stages must occur exactly once in fixed order")
    excluded = {p for p, _, _ in records}
    if lines.count(cache.READY) == lines.count(READY) == 1:
        start, stop = lines.index(cache.READY) + 1, lines.index(READY)
        if [p for p, _, _ in records] != list(range(start, stop)):
            errors.append("permission report must exclusively follow cache ready")
        if lines[stop:stop + 3] != tail or (not fatal and stop + 3 != len(lines)):
            errors.append("permission injection/completion markers must immediately follow report")
        # The entire new stage is validated separately. Recreate only the old
        # normal terminal markers, preserving every original diagnostic value.
        projected = lines[:start] + [memory.READY, memory.PASS]
    else:
        errors.append("permission stage requires exactly one cache and permission ready marker")
        projected = [line for p, line in enumerate(lines) if p not in excluded and line not in tail]
    base = cache.parse_result(b"\r\n".join(projected) + b"\r\n", case="all-features", symbols=symbols,
                              hardening_case=PROFILE[case])
    answer["cache"] = base
    errors.extend(base["errors"])
    missing = (required_symbols() | {REPORT_SIZE, OPCODES_VERIFIED}) - symbols.keys()
    if missing:
        errors.append("missing permission validation symbols: " + ", ".join(sorted(missing)))
    if names != list(FIELDS) or missing:
        return answer
    fields = answer["permission"] = {name: value for _, name, value in records}
    old = base.get("hardening", {}).get("memory", {})
    active, old_fields = old.get("activation", {}), old.get("fields", {})

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(symbols[REPORT_SIZE] == 296 and symbols[OPCODES_VERIFIED] == 1,
            "permission requires exact ELF ABI and independently verified target opcodes")
    require(fields["case_id"] == CASES.index(case) + 1, "permission case id differs from requested case")
    require(bool(active) and bool(old_fields), "permission requires the complete prior memory lifecycle")
    if not active or not old_fields:
        return answer
    for name in ("cr0", "cr3", "efer", "pat"):
        require(fields[name] == active[name], "permission changed " + name.upper())
    require(fields["cr4"] == base.get("hardening", {}).get("hardening", {}).get("cr4_after"),
            "permission CR4 differs from independent profile hardening")
    require(fields["rflags"] & hardening.FLAGS_MASK == 0 and fields["rflags"] & 2 != 0,
            "permission baseline RFLAGS must have bit 1 with IF/DF/VM/AC clear")
    ac = case in ("smap-read", "smap-write")
    require(fields["steps"] == (15 if ac else 7), "permission preparation/AC proof steps are incomplete")
    if case.startswith("smap-"):
        require(fields["ac_flags"] & hardening.FLAGS_MASK == (1 << 18 if ac else 0) and fields["ac_flags"] & 2 != 0
                and fields["ac_read"] == TOKEN and fields["ac_write"] == WRITE,
                "SMAP must actually read/write USER data under its expected AC policy")
    else:
        require(fields["ac_flags"] == fields["ac_read"] == fields["ac_write"] == 0,
                "non-SMAP-on cases must not claim an AC bypass proof")
    require((fields["code_va"], fields["data_va"], fields["stack_top"]) == (USER_CODE, USER_DATA, USER_STACK_TOP),
            "permission user aliases differ from isolated fixed window")
    require(fields["probe_rip"] == expected_rip(case, symbols), "permission probe RIP is not the linked requested opcode")
    text_resource = next((item for item in old.get("resources", []) if item["kind"] == 8), None)
    require(text_resource is not None, "permission requires independently retained physical kernel text")
    if text_resource:
        for kind, symbol in BACKING.items():
            require(fields[kind + "_pa"] == text_resource["base"] + symbols[symbol] - memory.KERNEL_BASE,
                    "permission " + kind + " physical backing differs from actual ELF/kernel placement")
    if not 32 <= old_fields["physical_bits"] <= 52:
        errors.append("permission requires a bounded valid physical address width")
        return answer
    physical_mask = ((1 << old_fields["physical_bits"]) - 1) & ~4095
    ancestors = []
    for kind in BACKING:
        for level in ("pml4", "pdpt", "pd"):
            entry = fields[kind + "_" + level]
            address = entry & physical_mask
            require(entry & ~0x20 == address | 7,
                    f"permission {kind} {level} must be a present writable USER non-NX 4K ancestor")
            expected_table = (text_resource["base"] + symbols[TABLES[("pml4", "pdpt", "pd").index(level)]]
                              - memory.KERNEL_BASE) if text_resource else -1
            require(address == expected_table and address != fields["cr3"],
                    "permission ancestor differs from actual linked private table backing")
            if kind == "code":
                ancestors.append(address)
            else:
                require(address == ancestors[("pml4", "pdpt", "pd").index(level)],
                        "adjacent permission aliases must share their real three ancestor tables")
        leaf = fields[kind + "_pte"]
        flags = (5 | (NX if case == "nx-control" else 0)) if kind == "code" else NX | 7
        require(leaf & ~ACCESSED_DIRTY == fields[kind + "_pa"] | flags,
                f"permission {kind} leaf lost exact physical/User/RW/NX contract")
    require(len(set(ancestors)) == 3, "permission ancestor table pages overlap")
    require(fields["ldtr"] <= 0xffff, "permission actual SLDT baseline must fit its architectural 16-bit result")
    for name, value in {"gdt_base": symbols[GDT], "gdt_limit": 55, "idt_base": symbols["cpu_idt"],
                        "idt_limit": 4095, "tr": 0x18, "msw": fields["cr0"] & 0xffff}.items():
        require(fields[name] == value, "permission privileged " + name + " reference is not the actual descriptor/control contract")
    if fatal:
        answer["panic"] = parse_panic(lines, case, fields, symbols, errors)
    elif any(b"panic_" in line.lower() for line in lines):
        errors.append("successful permission probe must not contain panic diagnostics")
    answer["passed"] = not errors
    return answer


def check_result(returncode, serial, timed_out, case, symbols):
    errors = list(parse_result(serial, case=case, symbols=symbols)["errors"])
    if timed_out:
        errors.append("QEMU permission probe timed out")
    if returncode != (41 if case in SUCCESS else 37):
        errors.append("wrong permission guest exit code")
    return errors


def run_case(case, timeout=60.0):
    if case not in CASES or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("known case and finite positive timeout required")
    state = ROOT / STATE_DIR / case
    state.mkdir(parents=True, exist_ok=True)
    serial_path, result_path = state / "serial.log", state / "result.json"
    serial_path.write_bytes(b"")
    profile = PROFILE[case]
    result = {"case": case, "cpu_profile": hardening.PROFILES[profile][0], "passed": False, "status": "building",
              "command": None, "returncode": None, "timed_out": False, "interrupted": False, "errors": []}
    write_json(result_path, result)
    process, started = None, time.monotonic()
    try:
        esp = build(test=True, stage="p1", output=state / "build", permission_case=case)
        result["esp"] = str(esp)
        elf = esp.parent / "kernel.elf"
        symbols = read_validation_symbols(elf, case=case)
        result["kernel_elf"] = str(elf)
        command = qemu_command(esp, state, test=True) + ["-cpu", hardening.PROFILES[profile][0]]
        result.update(command=command, status="running")
        write_json(result_path, result)
        with (state / "qemu.stdout.log").open("wb") as stdout, (state / "qemu.stderr.log").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
            try:
                result["returncode"] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                result["timed_out"] = True
                memory.reap_process(process)
                result["returncode"] = process.returncode
            except BaseException:
                memory.reap_process(process)
                result["returncode"] = process.returncode
                raise
        serial = serial_path.read_bytes()
        result["errors"] = check_result(result["returncode"], serial, result["timed_out"], case, symbols)
        result["report"] = parse_result(serial, case=case, symbols=symbols)
    except KeyboardInterrupt:
        result["interrupted"] = True
        result["errors"].append("host interrupted permission probe")
    except Exception as exc:
        result["errors"].append(f"host {type(exc).__name__}: {exc}")
    finally:
        if process is not None and process.poll() is None:
            try:
                memory.reap_process(process)
            except Exception as exc:
                result["errors"].append(f"QEMU cleanup failed: {exc}")
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["timing_scope"] = "host build plus QEMU including firmware; not a boot-performance metric"
        result["passed"] = not result["errors"]
        result["status"] = "interrupted" if result["interrupted"] else "passed" if result["passed"] else "failed"
        write_json(result_path, result)
    print(f"{'PASS' if result['passed'] else 'FAIL'} CPU permissions/{case}; logs: {state}", flush=True)
    for error in result["errors"]:
        print("  " + error)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    select = parser.add_mutually_exclusive_group()
    select.add_argument("--case", choices=CASES)
    select.add_argument("--all", action="store_true")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    directory = ROOT / STATE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    aggregate, results = directory / "result.json", []
    write_json(aggregate, {"passed": False, "status": "running", "results": results})
    try:
        for case in CASES if args.all else [args.case or "smep"]:
            result = run_case(case, args.timeout)
            results.append(result)
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
