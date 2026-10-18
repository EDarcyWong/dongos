#!/usr/bin/env python3
"""Gate BSP feature-dependent CR4 hardening and the existing memory lifecycle."""
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

_spec = importlib.util.spec_from_file_location("hardening_memory_gate", Path(__file__).with_name("run_memory_qemu.py"))
memory = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(memory)

MASK = 0x300800
FLAGS_MASK = 0x60600  # IF, DF, VM and AC; arithmetic flags may vary.
FIELDS = ("max_basic", "leaf7_ebx", "leaf7_ecx", "supported", "cr4_before", "cr4_after",
          "rflags_before", "rflags_after", "cr0", "cr3", "efer", "pat", "steps")
READY = b"DONGOS_P2_HARDENING_READY"
LINE = re.compile(rb"hardening_([a-z0-9_]+)=0x([0-9a-f]{16})")
STATE_DIR = Path("build/test/cpu-hardening")
PROFILES = {
    "all-features": ("max,+smep,+smap,+umip", MASK),
    "no-smep": ("max,-smep,+smap,+umip", 0x200800),
    "no-smap": ("max,+smep,-smap,+umip", 0x100800),
    "no-umip": ("max,+smep,+smap,-umip", 0x300000),
    "no-features": ("max,-smep,-smap,-umip", 0),
}
CASES = tuple(PROFILES)


def read_validation_symbols(elf):
    """Retain the old ELF/layout gates and independently fix the new ABI."""
    symbols = memory.read_validation_symbols(elf)
    layout = json.loads(Path(elf).with_name("dong_layout.json").read_text(encoding="utf-8"))
    reports = [item for item in layout.get("types", []) if item.get("full_name") == "cpu.hardening.Report"]
    if (len(reports) != 1 or reports[0].get("size") != 104 or reports[0].get("alignment") != 8
            or [(field.get("name"), field.get("offset")) for field in reports[0].get("fields", [])]
            != [(name, index * 8) for index, name in enumerate(FIELDS)]):
        raise ValueError("compiled hardening Report must have the exact thirteen-field ABI")
    return symbols


def parse_result(serial, *, case="all-features", symbols=None):
    """Check raw CPUID, actual readback and an unmodified old memory report."""
    answer = {"hardening": {}, "memory": {}, "errors": [], "passed": False}
    errors = answer["errors"]
    if case not in PROFILES:
        errors.append(f"unknown hardening case {case!r}")
        return answer
    if isinstance(serial, str):
        serial = serial.encode("utf-8")
    if serial and not serial.endswith(b"\n"):
        errors.append("unterminated hardening serial line")
    lines = [line[:-1] if line.endswith(b"\r") else line for line in serial.split(b"\n")[:-1]]
    records = []
    for position, line in enumerate(lines):
        if READY in line and line != READY:
            errors.append("hardening ready marker must occupy its own line")
        if b"hardening_" not in line:
            continue
        match = LINE.fullmatch(line)
        if match is None:
            errors.append(f"malformed hardening diagnostic: {line!r}")
        else:
            records.append((position, match[1].decode("ascii"), int(match[2], 16)))
    names = [name for _, name, _ in records]
    if names != list(FIELDS):
        errors.append("hardening fields must be complete, known, unique and in fixed order")
    if lines.count(READY) != 1 or lines.count(memory.ACTIVATION_READY) != 1:
        errors.append("hardening/activation ready markers must occur exactly once")
    else:
        start, stop = lines.index(memory.ACTIVATION_READY) + 1, lines.index(READY)
        if stop <= start or [position for position, _, _ in records] != list(range(start, stop)):
            errors.append("hardening report is outside or interrupted within its stage")
    # Validate the original reports through their existing complete gate. Only
    # the new records and exact marker are projected out; errors above remain
    # fatal, so this cannot hide malformed or misplaced new diagnostics.
    excluded = {position for position, _, _ in records}
    projected = b"\r\n".join(line for position, line in enumerate(lines)
                                 if position not in excluded and line != READY) + b"\r\n"
    base = memory.parse_memory_result(projected, case="normal", symbols=symbols)
    answer["memory"] = base
    errors.extend(base["errors"])
    if names != list(FIELDS):
        return answer
    fields = {name: value for _, name, value in records}
    answer["hardening"] = fields

    def require(condition, message):
        if not condition:
            errors.append(message)

    maximum, ebx, ecx = (fields[name] for name in ("max_basic", "leaf7_ebx", "leaf7_ecx"))
    require(maximum <= 0xffffffff and ebx <= 0xffffffff and ecx <= 0xffffffff,
            "raw CPUID values must fit u32")
    require(maximum >= 7 or ebx == ecx == 0, "missing basic leaf 7 must have zero raw results")
    supported = ((1 << 20) if ebx & (1 << 7) else 0) | ((1 << 21) if ebx & (1 << 20) else 0)
    supported |= (1 << 11) if ecx & (1 << 2) else 0
    expected = PROFILES[case][1]
    require(fields["supported"] == supported == expected,
            "raw CPUID and supported mask differ from the independent CPU profile")
    before, after = fields["cr4_before"], fields["cr4_after"]
    require(before & MASK & ~expected == 0, "unsupported hardening control was already set")
    require(after == before | expected, "actual CR4 readback differs from supported-bit enable plan")
    for name in ("rflags_before", "rflags_after"):
        require(fields[name] & FLAGS_MASK == 0 and fields[name] & 2 != 0,
                "hardening RFLAGS must retain bit 1 with IF/DF/VM/AC clear")
    active = base.get("activation", {})
    require(bool(active), "hardening requires the complete independently validated activation report")
    if active:
        require(before == active["cr4"], "hardening baseline CR4 differs from activation readback")
        for register in ("cr0", "cr3", "efer", "pat"):
            require(fields[register] == active[register], f"hardening changed {register.upper()}")
    require(fields["steps"] == 7, "hardening did not complete plan, write and actual verification")
    answer["passed"] = not errors
    return answer


def check_result(returncode, serial, timed_out, case, symbols):
    errors = list(parse_result(serial, case=case, symbols=symbols)["errors"])
    if timed_out:
        errors.append("QEMU hardening probe timed out")
    if returncode != 33:
        errors.append("wrong hardening guest exit code")
    return errors


def write_json(path, result):
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def run_case(case, timeout=60.0, *, normal_esp=None):
    if case not in PROFILES or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("known case and finite positive timeout required")
    state = ROOT / STATE_DIR / case
    state.mkdir(parents=True, exist_ok=True)
    serial_path, result_path = state / "serial.log", state / "result.json"
    serial_path.write_bytes(b"")
    result = {"case": case, "cpu_profile": PROFILES[case][0], "expected_mask": PROFILES[case][1],
              "passed": False, "status": "building", "command": None, "returncode": None,
              "timed_out": False, "interrupted": False, "errors": []}
    write_json(result_path, result)
    process, started = None, time.monotonic()
    try:
        esp = Path(normal_esp) if normal_esp is not None else build(
            test=True, stage="p1", output=ROOT / STATE_DIR / "normal/build")
        result["esp"] = str(esp)
        elf = esp.parent / "kernel.elf"
        symbols = read_validation_symbols(elf)
        result["kernel_elf"] = str(elf)
        command = qemu_command(esp, state, test=True) + ["-cpu", PROFILES[case][0]]
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
        result["errors"].append("host interrupted hardening probe")
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
    print(f"{'PASS' if result['passed'] else 'FAIL'} CPU hardening/{case}; logs: {state}", flush=True)
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
