#!/usr/bin/env python3
"""Rebuild and boot isolated, fatal P2 CPU probes under headless QEMU."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build import ROOT, CPU_TEST_CASES, build, qemu_command

PANIC_EXIT_CODE = 37
CONTEXT_SIZE = 184
UNMAPPED_ADDRESS = 0x100000000
CASE_VECTORS = {"int3": 3, "ud2": 6, "gp": 13, "pf": 14,
                "bad-stack": 6, "double-fault": 8, "divide": 0, "bad-frame": 6}
PREFIX_MARKERS = [b"DONGOS_P1_START", b"DONGOS_P1_IMAGE_OK", b"DONGOS_P1_READY",
                  b"DONGOS_P1_EBS_RETRY", b"DONGOS_P1_EBS_OK",
                  b"DONGOS_P1_KERNEL_HIGH_OK", b"DONGOS_P2_CPU_READY"]
PANIC_MARKER = b"DONGOS_P2_PANIC"
SEED_REGISTERS = {
    "rax": 0x1111111111111111, "rbx": 0x2222222222222222,
    "rcx": 0x3333333333333333, "rdx": 0x4444444444444444,
    "rsi": 0x5555555555555555, "rdi": 0x6666666666666666,
    "r8": 0x8888888888888888, "r9": 0x9999999999999999,
    "r10": 0xaaaaaaaaaaaaaaaa, "r11": 0xbbbbbbbbbbbbbbbb,
    "r12": 0xcccccccccccccccc, "r13": 0xdddddddddddddddd,
    "r14": 0xeeeeeeeeeeeeeeee, "r15": 0xffffffffffffffff,
}
REQUIRED_FIELDS = set(SEED_REGISTERS) | {
    "context", "rbp", "vector", "error", "rip", "cs", "rflags", "rsp",
    "ss", "cr2", "frame_symbol", "frame_count",
}
REQUIRED_SYMBOLS = {
    "cpu_df_stack_bottom", "cpu_df_stack_top", "cpu_exception_stack_bottom",
    "cpu_exception_stack_top", "cpu_test_expected_rip", "cpu_test_mid_return",
    "cpu_test_inject_return",
}
HEX_FIELD = re.compile(rb"panic_([a-z0-9_]+)=0x([0-9a-fA-F]{16})")
FRAME_NAME = re.compile(r"frame_([0-9]{2})")


def read_elf_symbols(path: Path) -> dict[str, int]:
    """Read defined symbols from a little-endian x86-64 ELF SHT_SYMTAB."""
    data = Path(path).read_bytes()

    def span(offset, size):
        if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
            raise ValueError("truncated or invalid ELF table")
        return data[offset:offset + size]

    span(0, 64)
    if data[:7] != b"\x7fELF\x02\x01\x01" or struct.unpack_from("<H", data, 18)[0] != 62:
        raise ValueError("CPU probe needs a little-endian x86-64 ELF")
    shoff = struct.unpack_from("<Q", data, 40)[0]
    shsize, count = struct.unpack_from("<HH", data, 58)
    if shsize < 64 or not count:
        raise ValueError("ELF has no supported section table")
    span(shoff, shsize * count)
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * shsize) for i in range(count)]
    symbols = {}
    for section in sections:
        if section[1] != 2:  # SHT_SYMTAB, not the dynamic loader's symbol table.
            continue
        _, _, _, _, offset, size, link, _, _, stride = section
        if link >= count or stride < 24 or size % stride or sections[link][1] != 3:
            raise ValueError("invalid ELF symbol/string table")
        span(offset, size)
        strings = span(sections[link][4], sections[link][5])
        for cursor in range(offset, offset + size, stride):
            name, _, _, index, value, _ = struct.unpack_from("<IBBHQQ", data, cursor)
            if not name or not index:
                continue
            if name >= len(strings) or b"\0" not in strings[name:]:
                raise ValueError("invalid ELF symbol name")
            text = strings[name:strings.index(0, name)].decode("utf-8")
            if text in symbols and symbols[text] != value:
                raise ValueError(f"ambiguous ELF symbol {text!r}")
            symbols[text] = value
    missing = REQUIRED_SYMBOLS - symbols.keys()
    if missing:
        raise ValueError("missing CPU ELF symbols: " + ", ".join(sorted(missing)))
    return symbols


def check_result(returncode: int | None, serial: bytes, timed_out: bool,
                 case: str, symbols: dict[str, int]) -> list[str]:
    """Fail closed: panic text alone cannot turn a crash or stale boot into a pass."""
    errors = []
    if case not in CASE_VECTORS:
        return [f"unknown CPU case {case!r}"]
    if timed_out:
        errors.append("QEMU CPU probe timed out")
    if returncode != PANIC_EXIT_CODE:
        errors.append(f"guest exit code {returncode}, expected {PANIC_EXIT_CODE}")
    if serial and not serial.endswith(b"\n"):
        errors.append("unterminated serial line")
    lines = [line[:-1] if line.endswith(b"\r") else line for line in serial.split(b"\n")[:-1]]
    markers = PREFIX_MARKERS + [f"DONGOS_P2_INJECT:{case}".encode(), PANIC_MARKER]
    observed = [line for line in lines if line.startswith(b"DONGOS")]
    if observed != markers:
        errors.append("CPU stage markers must occur exactly once and in order, with no other guest stage")
    if any(word in serial for word in (b"P1_PASS", b"L1_PROBE", b"FAIL", b"PANIC_REENTERED")):
        errors.append("guest reported failure, reentry or normal completion")
    panic_index = lines.index(PANIC_MARKER) if PANIC_MARKER in lines else len(lines)
    fields, positions, frames, frame_positions = {}, {}, {}, []
    stack = None
    for index, line in enumerate(lines):
        if not line.startswith(b"panic_"):
            continue
        if index <= panic_index:
            errors.append("panic field precedes the panic marker")
        if line.startswith(b"panic_stack="):
            if stack is not None:
                errors.append("duplicate panic_stack")
            stack = line.partition(b"=")[2]
            if stack not in {b"DF", b"EXCEPTION"}:
                errors.append("invalid panic_stack")
            continue
        match = HEX_FIELD.fullmatch(line)
        if match is None:
            errors.append(f"malformed panic field: {line!r}")
            continue
        name = match[1].decode("ascii")
        value = int(match[2], 16)
        frame = FRAME_NAME.fullmatch(name)
        if frame:
            number = int(frame[1])
            if number in frames or number >= 16:
                errors.append("duplicate or invalid panic frame index")
            frames[number] = value
            frame_positions.append((index, number))
        elif name in REQUIRED_FIELDS:
            if name in fields:
                errors.append(f"duplicate panic_{name}")
            fields[name], positions[name] = value, index
        else:
            errors.append(f"unknown panic field {name!r}")
    missing = REQUIRED_FIELDS - fields.keys()
    if missing:
        errors.append("missing panic fields: " + ", ".join(sorted(missing)))
    expected_stack = b"DF" if case == "double-fault" else b"EXCEPTION"
    if stack != expected_stack:
        errors.append(f"panic stack {stack!r}, expected {expected_stack.decode()}")
    missing_symbols = REQUIRED_SYMBOLS - symbols.keys()
    if missing_symbols:
        errors.append("missing validation symbols: " + ", ".join(sorted(missing_symbols)))
    if missing or missing_symbols:
        return errors

    expected = dict(SEED_REGISTERS)
    if case in {"gp", "double-fault"}:
        expected["rax"] = 0x28
    elif case == "pf":
        expected["rax"] = UNMAPPED_ADDRESS
    elif case == "divide":
        expected.update(rax=1, rcx=0, rdx=0)
    expected.update(vector=CASE_VECTORS[case], error=0x28 if case == "gp" else 0,
                    cs=8, ss=0x10)
    if case != "double-fault":
        expected["rip"] = symbols["cpu_test_expected_rip"]
    if case == "pf":
        expected["cr2"] = UNMAPPED_ADDRESS
    for field, value in expected.items():
        if fields[field] != value:
            errors.append(f"panic_{field}=0x{fields[field]:016x}, expected 0x{value:016x}")
    if fields["rflags"] & (1 << 9) or not fields["rflags"] & (1 << 10) or not fields["rflags"] & 2:
        errors.append("saved RFLAGS must have IF=0, DF=1 and reserved bit 1 set")
    prefix = "cpu_df_stack_" if case == "double-fault" else "cpu_exception_stack_"
    low, high = symbols[prefix + "bottom"], symbols[prefix + "top"]
    context = fields["context"]
    if not (low < high and high - low >= 16384 and low <= context <= high - CONTEXT_SIZE):
        errors.append("complete exception context is outside the selected IST stack")
    if context & 15 != 8:
        errors.append("exception context has the wrong normalized stack alignment")
    if case == "bad-stack":
        if fields["rsp"] != UNMAPPED_ADDRESS:
            errors.append("bad-stack did not preserve the unmapped interrupted RSP")
    elif not (0 < fields["rsp"] < UNMAPPED_ADDRESS and fields["rsp"] % 16 == 0):
        errors.append("interrupted RSP is not on the aligned low bootstrap stack")
    if case == "bad-frame":
        if fields["rbp"] != UNMAPPED_ADDRESS:
            errors.append("bad-frame did not preserve the invalid RBP")
    elif not (0 < fields["rbp"] < UNMAPPED_ADDRESS and fields["rbp"] % 16 == 0):
        errors.append("interrupted RBP is not an aligned low bootstrap frame")
    if case not in {"bad-stack", "bad-frame"} and fields["rbp"] != fields["rsp"]:
        errors.append("leaf RBP and interrupted RSP differ")
    count = fields["frame_count"]
    if not 1 <= count <= 16 or set(frames) != set(range(count)):
        errors.append("frame count and complete contiguous frame indices disagree")
    if [number for _, number in frame_positions] != list(range(len(frame_positions))):
        errors.append("panic frames are out of order")
    if frame_positions and positions["frame_count"] <= frame_positions[-1][0]:
        errors.append("frame_count precedes the final frame")
    if frames.get(0) != fields["rip"] or fields["frame_symbol"] != fields["rip"]:
        errors.append("frame 00 / frame symbol must equal the interrupted RIP")
    if case == "bad-frame":
        if count != 1:
            errors.append("invalid RBP was followed beyond frame 00")
    else:
        if count < 3 or frames.get(1) != symbols["cpu_test_mid_return"] or frames.get(2) != symbols["cpu_test_inject_return"]:
            errors.append("frame walk lost the two independently linked caller return addresses")
    return errors


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def reap_process(process) -> None:
    """Bounded cleanup on timeout, interruption and exceptional host paths."""
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


def run_case(case: str, timeout: float) -> dict:
    if case not in CPU_TEST_CASES or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("a known CPU case and a finite positive timeout are required")
    state = ROOT / "build/test/cpu" / case
    state.mkdir(parents=True, exist_ok=True)
    serial_path, result_path = state / "serial.log", state / "result.json"
    serial_path.write_bytes(b"")
    result = {"case": case, "passed": False, "status": "building", "command": None,
              "build_request": {"test": True, "stage": "p1", "cpu_case": case},
              "returncode": None, "timed_out": False, "interrupted": False, "errors": [],
              "elapsed_seconds": 0.0, "build_elapsed_seconds": 0.0,
              "timing_scope": "elapsed_seconds is host QEMU start to exit (firmware included), not a boot-performance metric"}
    write_json(result_path, result)
    total_start, build_start = time.monotonic(), time.monotonic()
    process, qemu_start = None, None
    try:
        print(f"Rebuilding P2 CPU/{case}...", flush=True)
        esp = build(test=True, stage="p1", cpu_case=case)
        result["build_elapsed_seconds"] = round(time.monotonic() - build_start, 3)
        elf = esp.parent / "kernel.elf"
        result["kernel_elf"] = str(elf)
        symbols = read_elf_symbols(elf)
        result["command"] = qemu_command(esp, state, test=True)
        result["status"] = "running"
        write_json(result_path, result)
        print(f"Booting P2 CPU/{case} (TCG, isolated NVRAM, panic exit {PANIC_EXIT_CODE})...", flush=True)
        with (state / "qemu.stdout.log").open("wb") as stdout, (state / "qemu.stderr.log").open("wb") as stderr:
            qemu_start = time.monotonic()
            process = subprocess.Popen(result["command"], cwd=ROOT, stdout=stdout, stderr=stderr)
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
        result["errors"] = check_result(result["returncode"], serial_path.read_bytes(),
                                        result["timed_out"], case, symbols)
    except KeyboardInterrupt:
        result["interrupted"] = True
        result["errors"].append("host interrupted the CPU probe")
    except Exception as exc:
        result["errors"].append(f"host {type(exc).__name__}: {exc}")
    finally:
        if process is not None and process.poll() is None:
            try:
                reap_process(process)
            except Exception as exc:
                result["errors"].append(f"QEMU cleanup failed: {exc}")
        if qemu_start is not None:
            result["elapsed_seconds"] = round(time.monotonic() - qemu_start, 3)
        if not result["build_elapsed_seconds"]:
            result["build_elapsed_seconds"] = round(time.monotonic() - build_start, 3)
        result["total_elapsed_seconds"] = round(time.monotonic() - total_start, 3)
        result["passed"] = not result["errors"]
        result["status"] = "interrupted" if result["interrupted"] else "passed" if result["passed"] else "failed"
        write_json(result_path, result)
    print(f"{'PASS' if result['passed'] else 'FAIL'} P2 CPU/{case}; logs: {state}", flush=True)
    for error in result["errors"]:
        print("  " + error)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--case", choices=list(CPU_TEST_CASES), help="one isolated CPU fault (default: int3)")
    selection.add_argument("--all", action="store_true", help="rebuild and run all eight cases serially")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    directory = ROOT / "build/test/cpu"
    directory.mkdir(parents=True, exist_ok=True)
    result_path = directory / "result.json"
    results = []
    write_json(result_path, {"passed": False, "status": "running", "results": results})
    try:
        for case in list(CPU_TEST_CASES) if args.all else [args.case or "int3"]:
            result = run_case(case, args.timeout)
            results.append(result)
            write_json(result_path, {"passed": False, "status": "running", "results": results})
            if result.get("interrupted"):
                break
    except (Exception, KeyboardInterrupt) as exc:
        write_json(result_path, {"passed": False, "status": "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                                 "error": f"{type(exc).__name__}: {exc}", "results": results})
        return 130 if isinstance(exc, KeyboardInterrupt) else 1
    interrupted = any(result.get("interrupted") for result in results)
    passed = bool(results) and all(result["passed"] for result in results)
    write_json(result_path, {"passed": passed, "status": "interrupted" if interrupted else "complete", "results": results})
    return 130 if interrupted else 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
