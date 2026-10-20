#!/usr/bin/env python3
"""Build and boot the P2 extension acceptance probe (large pages, alias W^X, PAT WC).

The probe is a CPL0 UEFI application (tests/p2_extensions_qemu.asm + .dg) that
links the real kernel mm modules. It passes only if QEMU exits with 33 and the
serial log contains every step marker. Wrong Dong mm sources (``--mutant``) are
built from a copied kernel tree and must make the same probe fail.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build import ROOT, execute, find_firmware, find_tool
from lang.tests.test_dongc import nasm_flags

PASS_EXIT, FAIL_EXIT = 33, 35
STEPS = [f"P2X 0000000050320{n:03x}" for n in range(1, 9)] + ["P2X 0000000050328001"]
MUTANTS = {
    # The split builds the page table but never links it: the CPU keeps using
    # the 2 MiB leaf, so replacing one 4 KiB entry has no visible effect.
    "split-not-linked": ("mm/paging.dg",
        "        atomic_store(&(*directory).entries[path.slots[2]], ((*space).pool_physical + (child as u64) * 4096) | PARENT_BITS);\r\n",
        ""),
    # The alias planner forgets to revoke the writable alias before granting
    # execute, so W^X is violated in the middle of the transition.
    "transition-without-revoke": ("mm/alias_policy.dg",
        "  if aliases[i].frame==frame&&(aliases[i].perms&conflict)!=0{steps[n]=Step{kind:REVOKE,index:i as u64};n+=1;}\n",
        ""),
    # 2 MiB leaves keep the PAT selector in bit 12; a split that copies it
    # raw (instead of moving it to bit 7) changes nothing for WB pages but a
    # large page mapped with PS set must also be recognised: dropping the
    # walker's large-leaf branch makes every 2 MiB mapping look malformed.
    # Two-CPU plan without SHOOTDOWN: the other CPU would keep a stale writable
    # translation of the frame that is about to become executable.
    "plan-without-shootdown": ("mm/alias_policy.dg",
        " if cpus>1{steps[n]=Step{kind:SHOOTDOWN,index:0};n+=1;}\n", ""),
    "walker-without-large-leaf": ("mm/paging.dg", "            if level == 2 && (entry & LARGE) != 0 {", "            if false {"),
}


def build(output: Path, kernel_root: Path, mode: str) -> Path:
    esp = output / "esp"
    boot = esp / "EFI" / "BOOT"
    boot.mkdir(parents=True, exist_ok=True)
    nasm, linker = find_tool("nasm", "NASM"), find_tool("lld-link", "LLD_LINK")
    probe_asm = output / "probe.asm"
    execute([sys.executable, "-m", "lang.dongc", "--mode", mode, "--root", str(ROOT / "tests"),
             "--root", str(kernel_root), "--root", str(ROOT / "lang/std"),
             "--emit-asm", str(probe_asm), str(ROOT / "tests/p2_extensions_qemu.dg")])
    objects = []
    for source, name in [(probe_asm, "probe"), (ROOT / "tests/p2_extensions_qemu.asm", "entry")]:
        obj = output / (name + ".obj")
        execute([nasm, "-f", "win64", *nasm_flags(nasm), "-o", str(obj), str(source)])
        execute([nasm, "-f", "elf64", *nasm_flags(nasm), "-o", str(output / (name + ".o")), str(source)])
        objects.append(obj)
    execute([linker, "/subsystem:efi_application", "/machine:x64", "/entry:efi_main", "/nodefaultlib",
             "/timestamp:0", "/fixed:no", f"/out:{boot / 'BOOTX64.EFI'}", *map(str, objects)])
    return esp


def boot(esp: Path, state: Path, timeout: float) -> tuple[int | None, str, float]:
    qemu = find_tool("qemu-system-x86_64", "QEMU")
    code, variables = find_firmware(qemu)
    state.mkdir(parents=True, exist_ok=True)
    nvram = state / "OVMF_VARS.fd"
    shutil.copyfile(variables, nvram)
    serial = state / "serial.log"
    serial.unlink(missing_ok=True)
    quote = lambda p: p.resolve().as_posix().replace(",", ",,")
    command = [qemu, "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-smp", "2", "-m", "512M",
               "-net", "none", "-monitor", "none", "-no-reboot", "-display", "none",
               "-drive", f"if=pflash,format=raw,readonly=on,file={quote(code)}",
               "-drive", f"if=pflash,format=raw,file={quote(nvram)}",
               "-drive", f"format=raw,file=fat:rw:{quote(esp)}",
               "-serial", f"file:{serial.resolve().as_posix()}",
               "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
    (state / "command.json").write_text(json.dumps(command, indent=1), encoding="utf-8")
    start = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout)
        exit_code = result.returncode
    except subprocess.TimeoutExpired:
        exit_code = None
    elapsed = time.monotonic() - start
    text = serial.read_text(encoding="latin-1") if serial.is_file() else ""
    return exit_code, text, elapsed


def run(label: str, kernel_root: Path, mode: str, timeout: float) -> dict:
    output = ROOT / "build" / "test" / "p2-extensions-qemu" / label / mode
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True)
    esp = build(output, kernel_root, mode)
    exit_code, text, elapsed = boot(esp, output / "state", timeout)
    markers = {step: step in text for step in STEPS}
    passed = exit_code == PASS_EXIT and "DONGOS_P2X_PASS" in text and all(markers.values()) \
        and "DONGOS_P2X_RESULT 0000000000000000" in text
    record = dict(label=label, mode=mode, exit_code=exit_code, passed=passed, elapsed=round(elapsed, 3),
                  markers=markers, serial_tail=text[-600:])
    (output / "result.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    return record


def mutant_root(name: str) -> Path:
    relative, old, new = MUTANTS[name]
    root = ROOT / "build" / "test" / "p2-extensions-qemu" / ("src-" + name)
    shutil.rmtree(root, ignore_errors=True)
    shutil.copytree(ROOT / "kernel", root, ignore=shutil.ignore_patterns("__pycache__"))
    target = root / relative
    text = target.read_bytes().decode("utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"mutant {name}: anchor matched {text.count(old)} times")
    target.write_bytes(text.replace(old, new, 1).encode("utf-8"))
    return root


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("debug", "release", "both"), default="both")
    parser.add_argument("--mutant", choices=sorted(MUTANTS) + ["all"], default=None)
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args(argv)
    modes = ("debug", "release") if args.mode == "both" else (args.mode,)
    failures = 0
    for mode in modes:
        record = run("good", ROOT / "kernel", mode, args.timeout)
        print(("PASS" if record["passed"] else "FAIL"), "p2-extensions", mode, "exit", record["exit_code"],
              f"{record['elapsed']}s", flush=True)
        failures += not record["passed"]
        names = sorted(MUTANTS) if args.mutant == "all" else ([args.mutant] if args.mutant else [])
        for name in names:
            bad = run(name, mutant_root(name), mode, args.timeout)
            rejected = bad["exit_code"] == FAIL_EXIT and not bad["passed"]
            print(("PASS" if rejected else "FAIL"), "mutant", name, mode, "exit", bad["exit_code"],
                  bad["serial_tail"].strip().splitlines()[-2:] if bad["serial_tail"] else "", flush=True)
            failures += not rejected
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
