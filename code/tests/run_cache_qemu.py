#!/usr/bin/env python3
"""Gate fixed-cache backing-page ownership and final-unmap CPU faults."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build import ROOT, build, qemu_command
from tests.acpi_protocol import project as project_acpi

_spec = importlib.util.spec_from_file_location("cache_hardening_gate", Path(__file__).with_name("run_hardening_qemu.py"))
hardening = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hardening)
memory = hardening.memory

FIELDS = ("root", "virtual", "physical", "reused_physical", "object_size", "alignment",
          "capacity", "allocated", "oom_error", "busy_error", "reused_object", "free_before",
          "free_held", "free_after", "tables_before", "tables_peak", "tables_after",
          "invlpg_count", "reload_count", "retired_tables", "checksum", "steps", "cr4", "rflags")
READY = b"DONGOS_P2_CACHE_READY"
INJECT = b"DONGOS_P2_CACHE_UNMAP_INJECT"
LINE = re.compile(rb"cache_([a-z0-9_]+)=0x([0-9a-f]{16})")
VIRTUAL = 0xffffb00000001000
REPORT_SIZE = "object_memory_report_size"
FAULT_PREFIX = "object_memory_test"
FAULT_SYMBOLS = {FAULT_PREFIX + suffix for suffix in ("_expected_rip", "_mid_return", "_inject_return")}
CHECKSUM = sum(((i * 7 + j + 3) & 255) if j < 48 else 0x5a
               for i in range(64) for j in range(64))
STATE_DIR = Path("build/test/cache-lifecycle/qemu")
PROFILES = {name: hardening.PROFILES[name] for name in ("all-features", "no-features")}
CASES = (*PROFILES, "cache-unmap")
write_json = hardening.write_json


def read_validation_symbols(elf, *, case="all-features"):
    symbols = hardening.read_validation_symbols(Path(elf))
    layout = json.loads(Path(elf).with_name("dong_layout.json").read_text(encoding="utf-8"))
    reports = [item for item in layout.get("types", []) if item.get("full_name") == "boot.object_memory.Report"]
    if (len(reports) != 1 or reports[0].get("size") != 192 or reports[0].get("alignment") != 8
            or [(field.get("name"), field.get("offset")) for field in reports[0].get("fields", [])]
            != [(name, i * 8) for i, name in enumerate(FIELDS)]):
        raise ValueError("compiled object-memory Report must have the exact twenty-four-field ABI")
    symbols[REPORT_SIZE] = 192
    if case == "cache-unmap" and not FAULT_SYMBOLS <= symbols.keys():
        raise ValueError("missing cache fault ELF symbols: " + ", ".join(sorted(FAULT_SYMBOLS - symbols.keys())))
    return symbols


def parse_panic(lines, symbols, errors):
    """Validate the real cache-unmap context without projecting its addresses."""
    records = []
    for position, line in enumerate(lines):
        if b"panic_" not in line:
            continue
        if line == b"panic_stack=EXCEPTION":
            records.append((position, "stack", "EXCEPTION"))
            continue
        match = memory.PANIC_LINE.fullmatch(line)
        if match is None:
            errors.append(f"malformed cache panic diagnostic: {line!r}")
        else:
            records.append((position, match[1].decode("ascii"), int(match[2], 16)))
    names = [name for _, name, _ in records]
    frames = [name for name in names if re.fullmatch(r"frame_[0-9]{2}", name)]
    if names != [*memory.PANIC_FIELDS, *[f"frame_{i:02d}" for i in range(len(frames))], "frame_count"]:
        errors.append("cache panic fields/frames must be complete, known, unique and in fixed order")
        return {}
    if memory.PANIC not in lines or [p for p, _, _ in records] != list(range(lines.index(memory.PANIC) + 1, len(lines))):
        errors.append("cache panic diagnostics are outside or interrupted within their stage")
    values = {name: value for _, name, value in records}
    missing = (memory.REQUIRED_SYMBOLS | FAULT_SYMBOLS) - symbols.keys()
    if missing:
        errors.append("missing cache fault ELF symbols: " + ", ".join(sorted(missing)))
        return values

    def require(condition, message):
        if not condition:
            errors.append(message)

    low, high = symbols["cpu_exception_stack_bottom"], symbols["cpu_exception_stack_top"]
    require(high - low >= 16384 and low <= values["context"] <= high - 184
            and values["context"] % 16 == 8, "cache fault must retain a complete aligned 184-byte EXCEPTION context")
    rip = symbols[FAULT_PREFIX + "_expected_rip"]
    returns = (rip, symbols[FAULT_PREFIX + "_mid_return"], symbols[FAULT_PREFIX + "_inject_return"])
    require(all(symbols["__kernel_text_start"] <= address < symbols["__kernel_text_end"] for address in returns),
            "cache fault and return symbols must be linked kernel text")
    expected = dict(memory.SEED_REGISTERS, rax=VIRTUAL, vector=14, error=0, rip=rip, cr2=VIRTUAL,
                    cs=8, ss=0x10, frame_symbol=rip)
    for name, value in expected.items():
        require(values[name] == value, f"cache panic_{name} does not match the independent fault/seed contract")
    flags = values["rflags"]
    require(flags & ((1 << 9) | (1 << 17) | (1 << 18)) == 0 and flags & (1 << 10) != 0 and flags & 2 != 0,
            "cache saved RFLAGS must have IF/VM/AC clear, DF set and bit 1 set")
    require(memory.STACK_BOTTOM <= values["rbp"] <= memory.STACK_BOTTOM + memory.STACK_BYTES - 16
            and values["rbp"] % 16 == 0 and values["rsp"] == values["rbp"],
            "cache interrupted RSP/RBP must identify a complete aligned fixed-stack frame")
    require(3 <= values["frame_count"] <= 16 and values["frame_count"] == len(frames),
            "cache frame count is incomplete or invalid")
    for i, address in enumerate(returns):
        require(values.get(f"frame_{i:02d}") == address, "cache trace lost a linked nested return frame")
    require(all(symbols["__kernel_text_start"] <= values[name] < symbols["__kernel_text_end"] for name in frames[3:]),
            "cache trace continued outside linked kernel text")
    return values


def parse_result(serial, *, case="all-features", symbols=None, hardening_case=None):
    answer = {"cache": {}, "hardening": {}, "panic": {}, "errors": [], "passed": False}
    errors, symbols = answer["errors"], symbols or {}
    if case not in CASES:
        errors.append(f"unknown cache case {case!r}")
        return answer
    if hardening_case is not None and hardening_case not in hardening.PROFILES:
        errors.append(f"unknown explicit cache hardening case {hardening_case!r}")
        return answer
    if isinstance(serial, str):
        serial = serial.encode("utf-8")
    if serial and not serial.endswith(b"\n"):
        errors.append("unterminated cache serial line")
    lines = [line[:-1] if line.endswith(b"\r") else line for line in serial.split(b"\n")[:-1]]
    lines, acpi_errors = project_acpi(lines)
    errors.extend(acpi_errors)
    fault = case == "cache-unmap"
    records = []
    for position, line in enumerate(lines):
        lower = line.lower()
        if b"cache_" not in lower or lower.startswith(b"activation_"):
            continue
        if line in (READY, INJECT):
            continue
        match = LINE.fullmatch(line)
        if match is None:
            errors.append(f"malformed cache diagnostic: {line!r}")
        else:
            records.append((position, match[1].decode("ascii"), int(match[2], 16)))
    names = [name for _, name, _ in records]
    if names != list(FIELDS):
        errors.append("cache fields must be complete, known, unique and in fixed order")
    expected_markers = [*memory.PREFIX_MARKERS, memory.STACK_READY, memory.PREFLIGHT_READY,
                        memory.ACTIVATION_READY, hardening.READY, memory.MUTATION_READY, READY]
    expected_markers += [INJECT, memory.PANIC] if fault else [memory.READY, memory.PASS]
    if [line for line in lines if line.startswith(b"DONGOS")] != expected_markers:
        errors.append("cache guest stage markers must occur exactly once in order")
    if lines.count(READY) == lines.count(memory.MUTATION_READY) == 1:
        start, stop = lines.index(memory.MUTATION_READY) + 1, lines.index(READY)
        if [p for p, _, _ in records] != list(range(start, stop)):
            errors.append("cache report must exclusively fill its stage after mutation")
        tail = [INJECT, memory.PANIC] if fault else [memory.READY, memory.PASS]
        if lines[stop + 1:stop + 1 + len(tail)] != tail:
            errors.append("cache completion/fault markers must immediately follow its report")
        if not fault and stop + 1 + len(tail) != len(lines):
            errors.append("cache normal completion must end with memory ready and PASS")
    else:
        errors.append("cache stage requires one mutation and cache ready marker")
    # A normal prior-stage projection is safe only alongside the independent
    # strict cache stage and real panic checks above/below. No old diagnostics
    # or old stage markers are excluded.
    excluded = {p for p, _, _ in records}
    projected = [line for p, line in enumerate(lines) if p not in excluded and line != READY]
    if fault:
        answer["panic"] = parse_panic(lines, symbols, errors)
        if INJECT in projected:
            projected = projected[:projected.index(INJECT)] + [memory.READY, memory.PASS]
    profile = hardening_case if hardening_case is not None else "all-features" if fault else case
    base = hardening.parse_result(b"\r\n".join(projected) + b"\r\n", case=profile, symbols=symbols)
    answer["hardening"] = base
    errors.extend(base["errors"])
    if names != list(FIELDS):
        return answer
    fields = answer["cache"] = {name: value for _, name, value in records}
    old = base.get("memory", {}).get("fields", {})

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(symbols.get(REPORT_SIZE) == 192, "missing exact independently compiled object-memory Report ABI")
    require(bool(old), "cache requires the complete prior memory report")
    if not old:
        return answer
    require(fields["root"] == old["root_physical"], "cache lifecycle changed the active root")
    require(fields["virtual"] == VIRTUAL, "cache target differs from the isolated virtual window")
    physical = fields["physical"]
    require(physical == fields["reused_physical"] and physical % memory.PAGE == 0
            and old["arena_base"] <= physical and physical + memory.PAGE <= old["arena_base"] + old["arena_pages"] * memory.PAGE,
            "cache backing page must be aligned owned arena RAM and deterministically reused")
    for resource in base.get("memory", {}).get("resources", []):
        require(not (physical < resource["base"] + resource["length"] and resource["base"] < physical + memory.PAGE),
                f"cache backing page overlaps retained resource {resource['kind']}")
    for name, value in {"object_size": 48, "alignment": 64, "capacity": 64, "allocated": 64,
                        "oom_error": 0x02000007, "busy_error": 0x020d0001,
                        "reused_object": VIRTUAL + 17 * 64, "checksum": CHECKSUM, "steps": 1023,
                        "invlpg_count": 2, "reload_count": 2, "retired_tables": 6}.items():
        require(fields[name] == value, f"cache {name} differs from the independently expected lifecycle result")
    require(fields["free_before"] == fields["free_after"] == old["free_pages"]
            and fields["free_held"] + 1 == fields["free_before"], "cache buddy page accounting did not return to baseline")
    require(fields["tables_before"] == fields["tables_after"] == old["table_count"]
            and fields["tables_peak"] == old["table_count"] + 3 <= old["pool_pages"],
            "cache private three-table branch was not fully reclaimed")
    require(fields["cr4"] == base.get("hardening", {}).get("cr4_after"), "cache changed hardened CR4")
    require(fields["rflags"] & hardening.FLAGS_MASK == 0 and fields["rflags"] & 2 != 0,
            "cache RFLAGS must retain bit 1 with IF/DF/VM/AC clear")
    answer["passed"] = not errors
    return answer


def check_result(returncode, serial, timed_out, case, symbols):
    errors = list(parse_result(serial, case=case, symbols=symbols)["errors"])
    if timed_out:
        errors.append("QEMU cache probe timed out")
    if returncode != (37 if case == "cache-unmap" else 33):
        errors.append("wrong cache guest exit code")
    return errors


def run_case(case, timeout=60.0, *, normal_esp=None):
    if case not in CASES or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("known case and finite positive timeout required")
    state = ROOT / STATE_DIR / case
    state.mkdir(parents=True, exist_ok=True)
    serial_path, result_path = state / "serial.log", state / "result.json"
    serial_path.write_bytes(b"")
    profile = "all-features" if case == "cache-unmap" else case
    result = {"case": case, "cpu_profile": PROFILES[profile][0], "passed": False, "status": "building",
              "command": None, "returncode": None, "timed_out": False, "interrupted": False, "errors": []}
    write_json(result_path, result)
    process, started = None, time.monotonic()
    try:
        if case == "cache-unmap":
            esp = build(test=True, stage="p1", output=state / "build", memory_case=case)
        else:
            esp = Path(normal_esp) if normal_esp is not None else build(
                test=True, stage="p1", output=ROOT / STATE_DIR / "normal/build")
        result["esp"] = str(esp)
        elf = esp.parent / "kernel.elf"
        symbols = read_validation_symbols(elf, case=case)
        result["kernel_elf"] = str(elf)
        command = qemu_command(esp, state, test=True) + ["-cpu", PROFILES[profile][0]]
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
        result["errors"].append("host interrupted cache probe")
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
    print(f"{'PASS' if result['passed'] else 'FAIL'} cache lifecycle/{case}; logs: {state}", flush=True)
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
        for case in CASES if args.all else [args.case or "all-features"]:
            result = run_case(case, args.timeout, normal_esp=normal_esp)
            results.append(result)
            if case != "cache-unmap":
                normal_esp = result.get("esp", normal_esp)
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
