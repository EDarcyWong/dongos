#!/usr/bin/env python3
"""Boot P0/P1 under headless TCG; P1 also rejects damaged or missing images."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build import ROOT, ToolError, build, output_directory, qemu_command

HELLO = b"DongOS: hello, x86-64 UEFI!"
PASS = b"DONGOS_P0_PASS"
EXIT_CODE = (0x10 << 1) | 1
P1_MARKERS = [b"DONGOS_P1_START", b"DONGOS_P1_IMAGE_OK", b"DONGOS_P1_READY",
              b"DONGOS_P1_EBS_RETRY", b"DONGOS_P1_EBS_OK", b"DONGOS_P1_KERNEL_HIGH_OK", b"DONGOS_P2_CPU_READY", b"DONGOS_L1_PROBE_OK: 42",
              b"DONGOS_L1_MEMORY_OK: 373", b"DONGOS_L1_SLICE_ABI_OK: 765",
              b"DONGOS_L1_CONSTANTS_OK: 282", b"DONGOS_L1_ALIGNMENT_OK: 458",
              b"DONGOS_L1_GLOBALS_OK: 436", b"DONGOS_L1_INTRINSICS_OK: 719",
              b"DONGOS_L1_FUNCTIONS_OK: 761", b"DONGOS_L1_FEATURES_OK: 75",
              b"DONGOS_P2_STACK_READY", b"DONGOS_P2_PREFLIGHT_READY",
              b"DONGOS_P2_ACTIVATION_READY", b"DONGOS_P2_MUTATION_READY",
              b"DONGOS_P2_MEMORY_READY", b"DONGOS_P1_PASS"]
FAILURE_CASES = {"tamper": b"DONGOS_P1_FAIL:E08_IMAGE_HASH",
                 "truncated": b"DONGOS_P1_FAIL:E05_IMAGE_SIZE",
                 "missing": b"DONGOS_P1_FAIL:E04_IMAGE_OPEN"}


def check_result(returncode: int | None, serial: bytes, timed_out: bool,
                 stage: str = "p0", expected_failure: bytes | None = None) -> list[str]:
    errors = []
    if timed_out:
        errors.append("QEMU boot timed out")
    expected_code = 35 if expected_failure else EXIT_CODE
    if returncode != expected_code:
        errors.append(f"guest exit code {returncode}, expected {expected_code}")
    # Markers must be complete serial lines, not firmware text or partial writes.
    lines = [line.rstrip(b"\r\n") for line in serial.splitlines(keepends=True) if line.endswith(b"\n")]
    if stage == "p1":
        if expected_failure:
            if lines.count(P1_MARKERS[0]) != 1 or lines.count(expected_failure) != 1:
                errors.append("expected one loader start and one rejection")
            elif lines.index(P1_MARKERS[0]) >= lines.index(expected_failure):
                errors.append("loader rejection precedes start")
            if expected_failure not in lines:
                errors.append("expected loader rejection missing")
            if [line for line in lines if line.startswith(b"DONGOS") and b"FAIL" in line] != [expected_failure]:
                errors.append("unexpected or duplicate guest failure")
            if any(marker in lines for marker in P1_MARKERS[1:]):
                errors.append("rejected image reached verified-image or kernel stage")
        else:
            previous = -1
            for marker in P1_MARKERS:
                if marker not in lines:
                    errors.append(f"missing stage marker: {marker.decode()}")
                elif lines.count(marker) != 1:
                    errors.append(f"duplicate stage marker: {marker.decode()}")
                elif lines.index(marker) <= previous:
                    errors.append(f"stage marker out of order: {marker.decode()}")
                else:
                    previous = lines.index(marker)
            if any(b"FAIL" in line for line in lines):
                errors.append("guest reported failure")
        return errors
    if HELLO not in lines:
        errors.append("serial hello missing")
    if PASS not in lines:
        errors.append("guest completion marker missing")
    if HELLO in lines and PASS in lines and lines.index(PASS) <= lines.index(HELLO):
        errors.append("completion marker precedes hello")
    return errors


def run_case(esp: Path, stage: str, case: str, timeout: float) -> dict:
    state = output_directory(stage, True) / case
    state.mkdir(parents=True, exist_ok=True)
    if case != "normal":
        clone = state / "esp"
        shutil.copytree(esp, clone, dirs_exist_ok=True)
        image = clone / "DONGOS.IMG"
        if case == "missing":
            image.unlink()
        else:
            data = bytearray(image.read_bytes())
            if case == "tamper":
                data[-1] ^= 0x80
            elif case == "truncated":
                del data[-1]
            image.write_bytes(data)
        esp = clone
    serial_path = state / "serial.log"
    serial_path.write_bytes(b"")  # A stale success log must never pass a new boot.
    started = time.monotonic()
    returncode = None
    timed_out = False
    try:
        command = qemu_command(esp, state, test=True)
        started = time.monotonic()
        print(f"Booting {stage.upper()}/{case} (TCG, 4 CPUs, 2 GiB, headless)...", flush=True)
        with (state / "qemu.stdout.log").open("wb") as stdout, (state / "qemu.stderr.log").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                returncode = process.wait()
            except BaseException:
                process.kill()
                process.wait()
                raise
        errors = check_result(returncode, serial_path.read_bytes(), timed_out, stage, FAILURE_CASES.get(case))
    except (ToolError, OSError, subprocess.CalledProcessError) as exc:
        errors = [str(exc)]
    elapsed = time.monotonic() - started
    result = {"stage": stage.upper(), "case": case, "passed": not errors, "elapsed_seconds": round(elapsed, 3),
              "timing_scope": "host QEMU process start to exit; includes firmware; not P6 boot metric",
              "returncode": returncode, "timed_out": timed_out, "errors": errors}
    (state / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{'FAIL' if errors else 'PASS'} {stage.upper()}/{case} ({elapsed:.3f}s host elapsed)")
    for error in errors:
        print(f"  {error}")
    print(f"Logs: {state}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["p0", "p1"], default="p1")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--all", action="store_true", help="P1 success and three image rejection cases")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        output_directory(args.stage, True).mkdir(parents=True, exist_ok=True)
        result_path = output_directory(args.stage, True) / "result.json"
        result_path.write_text(json.dumps({"passed": False, "status": "building"}) + "\n", encoding="utf-8")
        esp = build(test=True, stage=args.stage)
        cases = ["normal", *FAILURE_CASES] if args.all and args.stage == "p1" else ["normal"]
        results = [run_case(esp, args.stage, case, args.timeout) for case in cases]
        result_path.write_text(
            json.dumps(results, indent=2) + "\n", encoding="utf-8")
        return int(any(not result["passed"] for result in results))
    except (ToolError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        if "result_path" in locals():
            result_path.write_text(json.dumps({"passed": False, "error": str(exc)}) + "\n", encoding="utf-8")
        print(f"FAIL {args.stage.upper()} build: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
