#!/usr/bin/env python3
"""Build and run the independent arch.x86_64 ring-0 probe under QEMU TCG."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build import ROOT, ToolError, find_tool, find_firmware, execute

MARKERS = [b"DONGOS_STD_ARCH_START", b"DONGOS_STD_ARCH_IO_PASS", b"DONGOS_STD_ARCH_CR3_PASS",
           b"DONGOS_STD_ARCH_MSR_PASS", b"DONGOS_STD_ARCH_ABI_PASS", b"DONGOS_STD_ARCH_PASS"]
EXIT_CODE = (0x10 << 1) | 1  # isa-debug-exit: guest writes 0x10 -> QEMU exit 33
CPU = "max"


def nasm_flags(nasm: str) -> list[str]:
    version = subprocess.run([nasm, "-v"], capture_output=True, text=True, check=True).stdout
    major = re.search(r"NASM version (\d+)\.", version)
    return ["-Wall", "-Werror"] + (["-w-reloc-rel-dword"] if major and int(major[1]) >= 3 else [])


def output_dir(mode: str) -> Path:
    return ROOT / "build" / "test" / "std-arch-ring0" / mode


def build_probe(mode: str, arch_asm: Path | None = None, output: Path | None = None) -> Path:
    if output is None:
        output = output_dir(mode)
    esp = output / "esp"
    boot_dir = esp / "EFI" / "BOOT"
    boot_dir.mkdir(parents=True, exist_ok=True)
    linker = find_tool("lld-link", "LLD_LINK")
    nasm = find_tool("nasm", "NASM")
    probe_asm = output / "probe.asm"
    execute([sys.executable, "-m", "lang.dongc", "--mode", mode,
             "--root", str(ROOT / "lang/tests"), "--root", str(ROOT / "lang/std"),
             "--emit-asm", str(probe_asm), str(ROOT / "lang/tests/std_arch_ring0.dg")])
    objects = []
    arch_source = arch_asm if arch_asm is not None else (ROOT / "lang/std/arch/x86_64.asm")
    for src, name in [(probe_asm, "probe"),
                      (ROOT / "lang/tests/std_arch_ring0.asm", "entry"),
                      (arch_source, "arch")]:
        obj = output / (name + ".obj")
        execute([nasm, "-f", "win64", *nasm_flags(nasm), "-o", str(obj), str(src)])
        objects.append(obj)
        elf_obj = output / (name + ".o")
        execute([nasm, "-f", "elf64", *nasm_flags(nasm), "-o", str(elf_obj), str(src)])
    execute([linker, "/subsystem:efi_application", "/machine:x64", "/entry:efi_main",
             "/nodefaultlib", "/timestamp:0", "/fixed:no",
             f"/out:{boot_dir / 'BOOTX64.EFI'}", *map(str, objects)])
    print(f"Built {boot_dir / 'BOOTX64.EFI'}", flush=True)
    return esp


def qemu_command(esp: Path, state: Path) -> list[str]:
    qemu = find_tool("qemu-system-x86_64", "QEMU")
    code, variables = find_firmware(qemu)
    state.mkdir(parents=True, exist_ok=True)
    nvram = state / "OVMF_VARS.fd"
    shutil.copyfile(variables, nvram)
    def drive_path(p: Path) -> str:
        return p.resolve().as_posix().replace(",", ",,")
    return [qemu, "-machine", "q35", "-accel", "tcg", "-cpu", CPU, "-smp", "1", "-m", "512M",
            "-net", "none", "-monitor", "none", "-no-reboot",
            "-drive", f"if=pflash,format=raw,readonly=on,file={drive_path(code)}",
            "-drive", f"if=pflash,format=raw,file={drive_path(nvram)}",
            "-drive", f"format=raw,file=fat:rw:{drive_path(esp)}",
            "-display", "none", "-serial", f"file:{(state / 'serial.log').resolve().as_posix()}",
            "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]


def check_result(returncode: int | None, serial: bytes, timed_out: bool) -> list[str]:
    errors = []
    if timed_out:
        errors.append("QEMU boot timed out")
    if returncode != EXIT_CODE:
        errors.append(f"guest exit code {returncode}, expected {EXIT_CODE}")
    if serial and not serial.endswith(b"\n"):
        errors.append("serial ends without a newline (truncated output)")
    lines = [line.rstrip(b"\r\n") for line in serial.splitlines(keepends=True) if line.endswith(b"\n")]
    previous = -1
    for marker in MARKERS:
        if marker not in lines:
            errors.append(f"missing marker: {marker.decode()}")
        elif lines.count(marker) != 1:
            errors.append(f"duplicate marker: {marker.decode()}")
        elif lines.index(marker) <= previous:
            errors.append(f"marker out of order: {marker.decode()}")
        else:
            previous = lines.index(marker)
    for line in lines:
        if line.startswith(b"DONGOS_STD_ARCH_"):
            if line.startswith(b"DONGOS_STD_ARCH_FAIL") or line.startswith(b"DONGOS_STD_ARCH_PANIC"):
                errors.append(f"guest reported failure/panic: {line.decode()}")
            elif line not in MARKERS:
                errors.append(f"unknown stage marker: {line.decode()}")
    return errors


def run_probe(mode: str, timeout: float) -> dict:
    state = output_dir(mode)
    state.mkdir(parents=True, exist_ok=True)
    serial_path = state / "serial.log"
    serial_path.write_bytes(b"")
    result_path = state / "result.json"
    # Clear any stale success before building: a failed build must not retain it.
    result_path.write_text(json.dumps({"passed": False, "status": "building"}) + "\n", encoding="utf-8")
    command: list[str] = []
    started = time.monotonic()
    returncode: int | None = None
    timed_out = False
    try:
        esp = build_probe(mode)
        command = qemu_command(esp, state)
        print(f"Booting arch ring-0 probe ({mode}, TCG, {CPU}, headless)...", flush=True)
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
        errors = check_result(returncode, serial_path.read_bytes(), timed_out)
    except BaseException as exc:
        errors = [f"{type(exc).__name__}: {exc}"]
    elapsed = time.monotonic() - started
    result = {"mode": mode, "passed": not errors, "elapsed_seconds": round(elapsed, 3),
              "returncode": returncode, "timed_out": timed_out, "errors": errors,
              "cpu": CPU, "machine": "q35", "accel": "tcg",
              "command": " ".join(command)}
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{'FAIL' if errors else 'PASS'} arch-ring0/{mode} ({elapsed:.3f}s host elapsed)")
    for error in errors:
        print(f"  {error}")
    print(f"Logs: {state}")
    return result


def run_negative_control(arch_asm: Path, label: str, timeout: float = 120.0) -> dict:
    """Build with a substituted (bad) arch wrapper and run one QEMU mode.

    Returns a result dict with the same keys as run_probe (debug mode only).
    """
    state = output_dir(f"negative-{label}")
    state.mkdir(parents=True, exist_ok=True)
    serial_path = state / "serial.log"
    serial_path.write_bytes(b"")
    result_path = state / "result.json"
    result_path.write_text(json.dumps({"passed": False, "status": "building"}) + "\n", encoding="utf-8")
    command: list[str] = []
    returncode: int | None = None
    timed_out = False
    try:
        esp = build_probe("debug", arch_asm, state)
        command = qemu_command(esp, state)
        print(f"Booting negative control ({label}, debug, TCG, {CPU}, headless)...", flush=True)
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
        serial = serial_path.read_bytes()
        errors = check_result(returncode, serial, timed_out)
        serial_lines = [line.decode() for line in serial.splitlines() if line.startswith(b"DONGOS_STD_ARCH_")]
    except BaseException as exc:
        errors = [f"{type(exc).__name__}: {exc}"]
        serial_lines = []
    result = {"mode": "debug", "label": label, "passed": not errors, "returncode": returncode,
              "timed_out": timed_out, "errors": errors, "serial_lines": serial_lines,
              "cpu": CPU, "command": " ".join(command)}
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    status = "FAIL" if errors else "PASS"
    print(f"{status} negative/{label} (returncode={returncode})")
    for error in errors:
        print(f"  {error}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["debug", "release"], default="debug")
    parser.add_argument("--all-modes", action="store_true", help="run debug and release serially")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a positive finite number")
    modes = ["debug", "release"] if args.all_modes else [args.mode]
    results = [run_probe(mode, args.timeout) for mode in modes]
    return int(any(not result["passed"] for result in results))


if __name__ == "__main__":
    sys.exit(main())
