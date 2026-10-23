#!/usr/bin/env python3
"""DongOS P0/P1 build and QEMU entry points; Python standard library only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CPU_TEST_CASES = {"int3": 1, "ud2": 2, "gp": 3, "pf": 4,
                  "bad-stack": 5, "double-fault": 6, "divide": 7, "bad-frame": 8}
MEMORY_ACTIVATION_CASES = {"null-page": 1, "ro-write": 2, "nx-fetch": 3,
                           "stack-guard": 4, "ist-guard": 5}
MEMORY_MUTATION_CASES = {"tlb-ro": 1, "tlb-unmap": 2}
PERMISSION_TEST_CASES = {"smep": 1, "smep-off": 2, "nx-control": 3,
                         "smap-read": 4, "smap-write": 5, "smap-off": 6,
                         "umip-sgdt": 7, "umip-sidt": 8, "umip-sldt": 9,
                         "umip-smsw": 10, "umip-str": 11, "umip-off": 12}


class ToolError(RuntimeError):
    pass


def find_tool(name: str, env_name: str) -> str:
    override = os.environ.get(env_name)
    if override:
        found = shutil.which(override)
        if found:
            return found
        raise ToolError(f"{env_name} points to an unavailable executable: {override}")
    found = shutil.which(name)
    if found:
        return found
    candidates = sorted((ROOT / ".tools").glob(f"**/{name}.exe"))
    if os.name == "nt" and name in ("lld-link", "ld.lld"):
        programs = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        candidates.append(programs / f"LLVM/bin/{name}.exe")
        vs = programs / "Microsoft Visual Studio"
        candidates += sorted(vs.glob(f"*/**/VC/Tools/Llvm/x64/bin/{name}.exe"), reverse=True)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise ToolError(f"Missing {name}; install it or set {env_name} to its executable path.")


def find_firmware(qemu: str) -> tuple[Path, Path]:
    code, variables = os.environ.get("OVMF_CODE"), os.environ.get("OVMF_VARS")
    if code or variables:
        if not code or not variables:
            raise ToolError("Set both OVMF_CODE and OVMF_VARS to a matching firmware pair.")
        pair = (Path(code).resolve(), Path(variables).resolve())
        if not all(p.is_file() for p in pair):
            raise ToolError(f"Firmware file not found: {pair}")
        return pair
    qemu_dir = Path(qemu).resolve().parent
    directories = [Path(os.environ["OVMF_DIR"])] if "OVMF_DIR" in os.environ else [
        Path("/usr/share/OVMF"), Path("/usr/share/edk2/ovmf"),
        Path("/usr/share/edk2/x64"), qemu_dir / "share", qemu_dir / "share/qemu",
        qemu_dir, ROOT / ".tools/ovmf",
    ]
    for directory in directories:
        for code_name, vars_name in [
            ("OVMF_CODE_4M.fd", "OVMF_VARS_4M.fd"),
            ("OVMF_CODE.fd", "OVMF_VARS.fd"),
            ("edk2-x86_64-code.fd", "edk2-i386-vars.fd"),
        ]:
            pair = directory / code_name, directory / vars_name
            if all(p.is_file() for p in pair):
                return tuple(p.resolve() for p in pair)
    raise ToolError("Missing UEFI firmware; install ovmf or set OVMF_CODE and OVMF_VARS.")


def execute(command: list[str]) -> None:
    print("+ " + subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def output_directory(stage: str, test: bool) -> Path:
    return ROOT / "build" / "test" / stage if test else ROOT / "build" / stage


def assemble(source: Path, output: Path, *, fmt: str, test: bool, stage: str,
             defines: dict[str, int] | None = None) -> Path:
    nasm = find_tool("nasm", "NASM")
    output.mkdir(parents=True, exist_ok=True)
    obj = output / (source.stem + (".obj" if fmt == "win64" else ".o"))
    command = [nasm, "-f", fmt, "-Wall", "-Werror", "-I", str(ROOT / "include") + os.sep,
               "-I", str(output) + os.sep, "-l", str(output / (source.stem + ".lst")), "-o", str(obj)]
    # Valid PC32/REL32 references and 64-bit pointer data are intentional.
    # Some NASM 2.x distributions backport these optional diagnostics; detect
    # capabilities rather than guessing from the major version. Every other
    # warning remains an error, including unsupported relocation widths.
    help_text = subprocess.run([nasm, "-h"], check=True, capture_output=True, text=True).stdout
    if re.search(r'(?m)^\s*-h\s+-\S+', help_text):
        help_text += '\n' + subprocess.run(
            [nasm, "-h", "-w"], check=True, capture_output=True, text=True,
        ).stdout
    for warning in ("reloc-rel-dword", "reloc-abs-qword"):
        if re.search(r"(?m)^\s*" + re.escape(warning) + r"\s", help_text):
            command.append("-w-" + warning)
    if test:
        command.append(f"-D{stage.upper()}_TEST=1")
    for name, value in (defines or {}).items():
        command.append(f"-D{name}={value}")
    execute(command + [str(source)])
    return obj


def build(*, test: bool = False, stage: str = "p1", cpu_case: str | None = None,
          output: Path | None = None, memory_case: str | None = None,
          permission_case: str | None = None, runtime_level: int = 0,
          ipc_rounds: int = 1_000_000, smp_case: str | None = None,
          graphics_case: str | None = None, desktop_scale: int = 100,
          compiler_job: bool = False) -> Path:
    if compiler_job and (runtime_level!=5 or stage!='p1' or cpu_case or memory_case or permission_case):
        raise ToolError('compiler job profile requires isolated P5')
    if desktop_scale not in (100,125,150,175,200) or (desktop_scale!=100 and runtime_level!=7):
        raise ToolError("desktop scale must be 100,125,150,175,200 and requires runtime7")
    if stage not in ("p0", "p1"):
        raise ToolError(f"Unknown stage: {stage}")
    if runtime_level not in (0, 3, 4, 5, 6, 7) or runtime_level and (stage != "p1" or cpu_case or memory_case or permission_case):
        raise ToolError("Runtime levels 3/4/5/6 require an isolated P1 build without fault injection")
    if not 1 <= ipc_rounds <= 1_000_000:
        raise ToolError("IPC rounds must be between 1 and 1,000,000")
    if smp_case is not None and (not test or runtime_level != 6 or smp_case != "no-invalidate"):
        raise ToolError("SMP invalidation injection requires a runtime6 test build")
    if graphics_case is not None and (not test or runtime_level != 7 or graphics_case != "drop-ymm"):
        raise ToolError("graphics fault injection requires a runtime7 test build")
    if cpu_case is not None and (not test or stage != "p1" or cpu_case not in CPU_TEST_CASES):
        raise ToolError("CPU fault injection requires a known case and a P1 test build")
    if permission_case is not None and (not test or stage != "p1"
            or permission_case not in PERMISSION_TEST_CASES or cpu_case is not None or memory_case is not None):
        raise ToolError("Permission probes require an isolated P1 test build and a known case")
    if memory_case is not None and (not test or stage != "p1" or memory_case not in
        ("bad-layout", "bad-pat", "bad-ist-layout", "mapped-guard", "bad-controls",
         "cache-unmap", *MEMORY_ACTIVATION_CASES, *MEMORY_MUTATION_CASES) or cpu_case):
        raise ToolError("Memory fault injection requires an isolated P1 test build and a known case")
    linker = find_tool("lld-link", "LLD_LINK")
    explicit_output = output is not None
    output = Path(output) if explicit_output else output_directory(stage, test)
    if cpu_case is not None and not explicit_output:
        output = ROOT / "build/test/cpu" / cpu_case / "build"
    esp = output / "esp" if test or stage == "p0" or explicit_output else ROOT / "build/esp"
    boot_dir = esp / "EFI/BOOT"
    boot_dir.mkdir(parents=True, exist_ok=True)
    input_paths=[]
    if runtime_level>=4:
        input_paths=sorted(p for tree in ('kernel','services','boot','include','lang/dongc','lang/std','lang/examples','tools','assets/fonts')
            for p in (ROOT/tree).rglob('*') if p.is_file() and p.suffix in ('.dg','.asm','.inc','.ld','.py','.dgfont','.txt'))
        if compiler_job:
            input_paths+=sorted((ROOT/'lang/bootstrap').glob('*.dg'))
    fingerprints=lambda:{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in input_paths}
    inputs_before=fingerprints()
    if input_paths:(output/'source-before.json').write_text(json.dumps(inputs_before,indent=2)+'\n')
    objects = []
    if stage == "p1":
        # Import only when building P1, so the P0 baseline remains independent.
        sys.path.insert(0, str(ROOT))
        from tools.elf_image import materialize
        from tools.mkimage import pack_image, manifest_text
        from tools.gen_offsets import generate
        elf_linker = find_tool("ld.lld", "LD_LLD")
        generated = output / "dong_probe.asm"
        layout_path = output / "dong_layout.json"
        service_roots = ["--root", str(ROOT / "services")] if runtime_level >= 4 else []
        # Production service kernels use the checked release backend to keep
        # the existing 2MiB image envelope. Isolated diagnostic probes retain
        # debug instrumentation; both modes remain native-tested.
        kernel_mode = "release" if runtime_level >= 5 else "debug"
        from tools.kernel_budget import kernel_flags
        kernel_sections = kernel_flags(runtime_level)
        kernel_profile = None
        profile_flags = []
        kernel_source_root = ROOT / "kernel"
        if runtime_level >= 5:
            from tools.kernel_storage_profile import generate as kernel_storage_profile
            profile_root, kernel_profile = kernel_storage_profile(output, runtime_level)
            kernel_source_root = profile_root
            profile_flags = ["--emit-ir", str(output / "kernel-optimization.json")]
        execute([sys.executable, "-m", "lang.dongc", "--mode", kernel_mode, *kernel_sections, *profile_flags, "--root", str(ROOT / "lang/examples"),
                 "--root", str(kernel_source_root), "--root", str(ROOT / "lang/std"), *service_roots, "--emit-asm", str(generated),
                 "--emit-layout", str(layout_path),
                 str(kernel_source_root / "smp_probe.dg" if runtime_level >= 5 else ROOT / ("kernel/user_probe.dg" if runtime_level == 4 else
                             "kernel/runtime_probe.dg" if runtime_level else "kernel/memory_probe.dg"))])
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
        (output / "bootinfo_layout.inc").write_text(generate(layout, "boot.abi.BootInfo"), encoding="ascii")
        (output / "memory_layout.inc").write_text(generate(layout, "boot.memory_resources.Layout", "MemoryLayout"), encoding="ascii")
        (output / "memory_report.inc").write_text(generate(layout, "boot.memory_startup.Report", "MemoryReport"), encoding="ascii")
        (output / "memory_resource.inc").write_text(generate(layout, "boot.memory_resources.Resource", "MemoryResource"), encoding="ascii")
        (output / "runtime_display.inc").write_text(generate(layout, "boot.runtime_view.Display", "RuntimeDisplay"), encoding="ascii")
        (output / "runtime_view.inc").write_text(generate(layout, "boot.runtime_view.View", "RuntimeView"), encoding="ascii")
        (output / "control_state.inc").write_text(generate(layout, "boot.preflight.State", "ControlState"), encoding="ascii")
        (output / "control_plan.inc").write_text(generate(layout, "boot.preflight.Plan", "ControlPlan"), encoding="ascii")
        (output / "activation_report.inc").write_text(generate(layout, "boot.activation.Report", "ActivationReport"), encoding="ascii")
        (output / "mutation_report.inc").write_text(generate(layout, "boot.live_memory.Report", "MutationReport"), encoding="ascii")
        (output / "live_stats.inc").write_text(generate(layout, "mm.active_paging.Stats", "LiveStats"), encoding="ascii")
        (output / "hardening_features.inc").write_text(generate(layout, "cpu.hardening.Features", "HardeningFeatures"), encoding="ascii")
        (output / "hardening_plan.inc").write_text(generate(layout, "cpu.hardening.Plan", "HardeningPlan"), encoding="ascii")
        (output / "hardening_report.inc").write_text(generate(layout, "cpu.hardening.Report", "HardeningReport"), encoding="ascii")
        (output / "object_memory_report.inc").write_text(generate(layout, "boot.object_memory.Report", "ObjectMemoryReport"), encoding="ascii")
        (output / "acpi_report.inc").write_text(generate(layout, "boot.acpi_startup.Report", "AcpiReport"), encoding="ascii")
        if runtime_level:
            for filename, typename, alias in (("device_views.inc", "boot.device_policy.Views", "DeviceViews"),
                                              ("platform_report.inc", "irq.platform.Report", "PlatformReport"),
                                              ("acpi_inventory.inc", "firmware.acpi.Inventory", "AcpiInventory")):
                (output / filename).write_text(generate(layout, typename, alias), encoding="ascii")
        if runtime_level == 4:
            (output / "user_report.inc").write_text(generate(layout, "user.runtime.Report", "UserReport"), encoding="ascii")
        if runtime_level >= 5:
            (output / "service_report.inc").write_text(generate(layout, "user.services.Report", "ServiceReport"), encoding="ascii")
            from tools.user_services import build_service
            from tools.service_bundle import pack, ELF, DATA
            programs = []
            for name, path in (("block", "services/drivers/block_service.dg"),
                               ("fs", "services/fs/service.dg"), ("shell", "services/shell/main.dg")):
                if compiler_job and name=='shell':
                    from lang.dongc import compile_file
                    target=output/'services'/name;target.mkdir(parents=True,exist_ok=True)
                    result=compile_file(ROOT/'services/compiler/controller.dg',roots=[ROOT/'services',ROOT/'lang',ROOT/'lang/std'],mode='release')
                    source=target/'program.asm';source.write_text(result.assembly,encoding='utf-8')
                    items=[assemble(source,target,fmt='elf64',test=False,stage=stage)]
                    for part in ['services/lib/syscalls.asm','services/gfx/accelerated.asm','services/gfx/transform.asm']:
                        items.append(assemble(ROOT/part,target,fmt='elf64',test=False,stage=stage))
                    executable=target/'program.elf'
                    execute([elf_linker,'-pie','--no-dynamic-linker','-z','norelro','--build-id=none','-T',str(ROOT/'services/lib/service.ld'),'-o',str(executable),*map(str,items)])
                else:
                    executable = build_service(ROOT / path, output / "services" / name)
                programs.append((name, ELF, executable.read_bytes()))
            if runtime_level >= 7:
                for name,path in (("compositor","services/desktop/service.dg"),("input","services/drivers/input_service.dg"),
                                  ("init","services/init/main.dg"),("devmgr","services/drivers/device_manager.dg"),
                                  ("echo","services/apps/echo.dg"),("fault","services/apps/fault.dg"),
                                  ("waiter","services/apps/waiter.dg"),("ipc-peer","services/apps/ipc_peer.dg"),
                                  ("fs-reader","services/apps/fs_reader.dg"),("xhci","services/drivers/xhci_service.dg"),
                                  ("terminal","services/apps/gui_terminal.dg"),("files","services/apps/gui_files.dg"),
                                  ("editor","services/apps/gui_editor.dg"),("settings","services/apps/gui_settings.dg")):
                    executable=build_service(ROOT/path,output/"services"/name)
                    programs.append((name,ELF,executable.read_bytes()))
                for font_pixels in (16,20,24,28,32):
                    programs.append((f"font{font_pixels}",DATA,(ROOT/f"assets/fonts/dong-cjk-sc-{font_pixels}.dgfont").read_bytes()))
                programs.append(("desktop-config",DATA,(desktop_scale*256//100).to_bytes(8,"little")))
            (esp / "SERVICES.BIN").write_bytes(pack(programs))
        if runtime_level >= 5:
            (output / "smp_report.inc").write_text(generate(layout,"smp.runtime.Report","SmpReport"),encoding="ascii")
            (output / "parallel_live_report.inc").write_text(generate(layout,"sched.parallel_live.Report","ParallelLiveReport"),encoding="ascii")
        probe = assemble(generated, output, fmt="elf64", test=test, stage=stage)
        defines = {"CPU_TEST_CASE": CPU_TEST_CASES[cpu_case]} if cpu_case else {}
        if runtime_level:
            defines["RUNTIME_LEVEL"] = runtime_level
            defines["P6_USER_SMP"] = int(runtime_level == 7)
        if compiler_job:
            defines['L3_COMPILER']=1
        if smp_case == "no-invalidate":
            defines["SMP_TEST_NO_INVALIDATE"] = 1
        if graphics_case == "drop-ymm":
            defines["SCHED_TEST_DROP_YMM"] = 1
        if runtime_level == 4:
            defines["IPC_ROUNDS"] = ipc_rounds
            for name in ("ipc_client", "ipc_server"):
                obj = assemble(ROOT / f"services/init/{name}.asm", output, fmt="elf64", test=False, stage=stage)
                execute([elf_linker, "-pie", "--no-dynamic-linker", "-z", "norelro", "--build-id=none",
                         "-T", str(ROOT / "services/lib/user.ld"), "-o", str(output / f"{name}.elf"), str(obj)])
        if permission_case is not None:
            defines["PERMISSION_TEST_CASE"] = PERMISSION_TEST_CASES[permission_case]
        if memory_case == "cache-unmap":
            defines["OBJECT_MEMORY_TEST_UNMAP"] = 1
        if memory_case in MEMORY_ACTIVATION_CASES:
            defines["MEMORY_ACTIVATION_TEST_CASE"] = MEMORY_ACTIVATION_CASES[memory_case]
        if memory_case in MEMORY_MUTATION_CASES:
            defines["MEMORY_MUTATION_TEST_CASE"] = MEMORY_MUTATION_CASES[memory_case]
        if memory_case == "bad-layout":
            defines["MEMORY_TEST_BAD_LAYOUT"] = 1
        if memory_case == "bad-pat":
            defines["MEMORY_TEST_BAD_PAT"] = 1
        if memory_case == "bad-ist-layout":
            defines["MEMORY_TEST_BAD_IST"] = 1
        if memory_case == "mapped-guard":
            defines["MEMORY_TEST_MAPPED_GUARD"] = 1
        if memory_case == "bad-controls":
            defines["MEMORY_TEST_BAD_CONTROLS"] = 1
        entry = assemble(ROOT / "kernel/entry.asm", output, fmt="elf64", test=test, stage=stage,
                         defines=defines)
        abi_probe = assemble(ROOT / "kernel/abi_probe.asm", output, fmt="elf64", test=test, stage=stage)
        cpu = assemble(ROOT / "kernel/cpu.asm", output, fmt="elf64", test=test, stage=stage, defines=defines)
        panic = assemble(ROOT / "kernel/panic.asm", output, fmt="elf64", test=test, stage=stage)
        arch = assemble(ROOT / "lang/std/arch/x86_64.asm", output, fmt="elf64", test=test, stage=stage)
        runtime = assemble(ROOT / "kernel/memory_runtime.asm", output, fmt="elf64", test=test, stage=stage)
        stack_bridge = assemble(ROOT / "kernel/stack_bridge.asm", output, fmt="elf64", test=test, stage=stage)
        kernel_objects = [entry, probe, abi_probe, cpu, panic, arch, runtime, stack_bridge]
        # memory_probe imports optional power capture for every P1 image; Dong
        # currently emits all reachable module functions without link-time DCE.
        kernel_objects.append(assemble(ROOT / "kernel/firmware/power_io.asm", output,
                                       fmt="elf64", test=test, stage=stage))
        kernel_objects.append(assemble(ROOT / "kernel/memory_mutation.asm", output,
                                       fmt="elf64", test=test, stage=stage))
        kernel_objects.append(assemble(ROOT / "kernel/cpu_hardening.asm", output,
                                       fmt="elf64", test=test, stage=stage))
        if runtime_level:
            for source in ("kernel/runtime.asm", "kernel/irq/hardware.asm", "kernel/sched/context.asm"):
                kernel_objects.append(assemble(ROOT / source, output, fmt="elf64", test=test, stage=stage, defines=defines))
        if runtime_level == 4:
            kernel_objects.append(assemble(ROOT / "kernel/user/context.asm", output / "user", fmt="elf64", test=test, stage=stage))
            kernel_objects.append(assemble(ROOT / "kernel/user_run.asm", output, fmt="elf64", test=test, stage=stage, defines=defines))
        if runtime_level >= 5:
            kernel_objects.append(assemble(ROOT / "kernel/user/context.asm", output / "user", fmt="elf64", test=test, stage=stage))
            kernel_objects.append(assemble(ROOT / "kernel/services_run.asm", output, fmt="elf64", test=test, stage=stage, defines=defines))
        if runtime_level >= 5:
            for source in ("kernel/smp/bootstrap.asm","kernel/smp_runtime.asm","kernel/smp/large_memory.asm","kernel/smp/alias_memory.asm"):
                kernel_objects.append(assemble(ROOT/source,output,fmt="elf64",test=test,stage=stage,defines=defines))
        if runtime_level >= 4:
            kernel_objects.append(assemble(ROOT / "kernel/user/shared_barrier.asm", output,
                                           fmt="elf64", test=test, stage=stage, defines=defines))
        if runtime_level >= 5:
            for source in ("parallel", "parallel_probe", "parallel_live", "user_entry", "user_arch",
                           "user_bridge_arch", "user_legacy", "user_boot", "runtime_large_reader"):
                kernel_objects.append(assemble(ROOT / ("kernel/sched/" + source + ".asm"), output,
                                               fmt="elf64", test=test, stage=stage, defines=defines))
        if memory_case == "cache-unmap":
            kernel_objects.append(assemble(ROOT / "kernel/object_memory_test.asm", output,
                                           fmt="elf64", test=test, stage=stage))
        if permission_case is not None:
            kernel_objects.append(assemble(ROOT / "kernel/permission_test.asm", output,
                                           fmt="elf64", test=test, stage=stage, defines=defines))
        if cpu_case:
            kernel_objects.append(assemble(ROOT / "kernel/cpu_test.asm", output, fmt="elf64",
                                           test=test, stage=stage, defines=defines))
        if memory_case in MEMORY_ACTIVATION_CASES:
            kernel_objects.append(assemble(ROOT / "kernel/memory_activation_test.asm", output,
                                           fmt="elf64", test=test, stage=stage, defines=defines))
        if memory_case in MEMORY_MUTATION_CASES:
            kernel_objects.append(assemble(ROOT / "kernel/memory_mutation_test.asm", output,
                                           fmt="elf64", test=test, stage=stage, defines=defines))
        if runtime_level >= 5:
            kernel_objects.append(assemble(ROOT / "boot/trace_clock.asm", output / "kernel-trace",
                                           fmt="elf64", test=test, stage=stage))
        kernel_elf = output / "kernel.elf"
        kernel_gc = ["--gc-sections"] if runtime_level >= 5 else []
        execute([elf_linker, "-nostdlib", *kernel_gc, "-z", "max-page-size=0x1000", "-T", str(ROOT / "kernel/linker.ld"),
                 "-o", str(kernel_elf), *map(str, kernel_objects)])
        raw = materialize(kernel_elf.read_bytes())
        (output / "kernel.bin").write_bytes(raw)
        image = pack_image(raw)
        (esp / "DONGOS.IMG").write_bytes(image)
        (output / "image_manifest.inc").write_text(manifest_text(image), encoding="utf-8")
        objects.append(assemble(ROOT / "boot/image.asm", output, fmt="win64", test=test, stage=stage))
    source = ROOT / ("p0/efi_main.asm" if stage == "p0" else "boot/efi_main.asm")
    loader_defines = {"SERVICE_BUNDLE": 1} if runtime_level >= 5 else None
    if runtime_level >= 7:
        loader_defines["DESKTOP_MODE"] = 1
    objects.append(assemble(source, output, fmt="win64", test=test, stage=stage, defines=loader_defines))
    if runtime_level >= 5:
        objects.append(assemble(ROOT / "boot/service_bundle.asm", output, fmt="win64", test=test, stage=stage))
    if runtime_level >= 7:
        objects.append(assemble(ROOT / "boot/display_mode.asm", output, fmt="win64", test=test, stage=stage))
    if runtime_level >= 5:
        trace_output = output / "loader-trace"
        trace_output.mkdir(parents=True, exist_ok=True)
        # boot.trace_loader is rooted at the repository, whereas boot.trace is
        # rooted at kernel/. This separate small graph is never a kernel probe.
        trace_assembly = trace_output / "trace_loader.asm"
        execute([sys.executable, "-m", "lang.dongc", "--mode", "release",
                 "--root", str(ROOT), "--root", str(ROOT / "kernel"),
                 "--root", str(ROOT / "lang/std"), "--root", str(ROOT / "lang/examples"),
                 "--emit-asm", str(trace_assembly), "--emit-layout", str(trace_output / "layout.json"),
                 str(ROOT / "boot/trace_loader.dg")])
        objects.append(assemble(trace_assembly, trace_output, fmt="win64", test=test, stage=stage))
        objects.append(assemble(ROOT / "boot/trace_clock.asm", trace_output, fmt="win64", test=test, stage=stage))
        objects.append(assemble(ROOT / "boot/trace_loader_panic.asm", trace_output, fmt="win64", test=test, stage=stage))
    execute([linker, "/subsystem:efi_application", "/machine:x64", "/entry:efi_main",
             "/nodefaultlib", "/timestamp:0", "/fixed:no",
             f"/map:{output / 'efi_main.map'}", f"/out:{boot_dir / 'BOOTX64.EFI'}", *map(str, objects)])
    if input_paths:
        after=fingerprints();(output/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
        manifest=dict(desktop_scale=desktop_scale,runtime_level=runtime_level,kernel_mode=kernel_mode,test=test,graphics_case=graphics_case,smp_case=smp_case,compiler_job=compiler_job,
            kernel_function_sections=runtime_level>=5,kernel_gc_sections=runtime_level>=5,
            kernel_optimization=1 if runtime_level>=5 else 0,kernel_storage_profile=kernel_profile,
            source_unchanged=inputs_before==after,source_sha256=after,
            artifacts={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                (output/'kernel.bin',output/'kernel.elf',esp/'DONGOS.IMG',esp/'EFI/BOOT/BOOTX64.EFI',*((esp/'SERVICES.BIN',output/'kernel-optimization.json',profile_root/'build/storage_profile.dg') if runtime_level>=5 else ()))})
        (output/'build-inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
        if inputs_before!=after:raise ToolError('Build inputs changed during compilation; retained artifacts are not accepted')
    print(f"Built {boot_dir / 'BOOTX64.EFI'}", flush=True)
    return esp


def qemu_command(esp: Path, state: Path, *, test: bool = False,
                 debug: bool = False, headless: bool = False,
                 accel: str = "tcg") -> list[str]:
    qemu = find_tool("qemu-system-x86_64", "QEMU")
    code, variables = find_firmware(qemu)
    state.mkdir(parents=True, exist_ok=True)
    # Start with fresh NVRAM for reproducible boots; never modify the vendor template.
    nvram = state / "OVMF_VARS.fd"
    shutil.copyfile(variables, nvram)
    def drive_path(path: Path) -> str:
        # Commas delimit QEMU key/value options; doubling quotes the literal comma.
        return path.resolve().as_posix().replace(",", ",,")
    command = [qemu, "-machine", "q35", "-accel", accel, "-smp", "4", "-m", "2G",
               "-net", "none", "-monitor", "none", "-no-reboot",
               "-drive", f"if=pflash,format=raw,readonly=on,file={drive_path(code)}",
               "-drive", f"if=pflash,format=raw,file={drive_path(nvram)}",
               "-drive", f"format=raw,file=fat:rw:{drive_path(esp)}"]
    if test:
        command += ["-display", "none", "-serial", f"file:{(state / 'serial.log').resolve().as_posix()}",
                    "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
    else:
        command += ["-serial", "stdio"]
        if headless:
            command += ["-display", "none"]
    if debug:
        command += ["-s", "-S", "-d", "int", "-D", str(state / "qemu.log")]
    return command


def doctor() -> int:
    failed = False
    qemu = None
    for name, variable in [("nasm", "NASM"), ("lld-link", "LLD_LINK"), ("ld.lld", "LD_LLD"),
                           ("qemu-system-x86_64", "QEMU")]:
        try:
            path = find_tool(name, variable)
            result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
            lines = (result.stdout + result.stderr).strip().splitlines()
            if result.returncode:
                raise ToolError(f"{name} could not run: {' '.join(lines)}")
            print(f"OK {name}: {path}\n   {lines[0] if lines else 'version unavailable'}")
            if name == "qemu-system-x86_64":
                qemu = path
        except (ToolError, OSError, subprocess.TimeoutExpired) as exc:
            print(f"FAIL {exc}")
            failed = True
    if qemu:
        try:
            code, variables = find_firmware(qemu)
            print(f"OK firmware: {code}\n             {variables}")
        except ToolError as exc:
            print(f"FAIL {exc}")
            failed = True
    return int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "run", "debug", "test", "doctor"])
    parser.add_argument("--stage", choices=["p0", "p1"], default="p1")
    parser.add_argument("--runtime-level", type=int, choices=[0, 3, 4, 5, 6, 7], default=0,
                        help="0: diagnostic; 3: threads; 4: IPC; 5: storage shell; 6: APs and TLB domain; 7: desktop integration")
    parser.add_argument("--ipc-rounds", type=int, default=1_000_000)
    parser.add_argument('--compiler-job',action='store_true',help='P5 isolated pure compiler/controller profile')
    parser.add_argument("--headless", action="store_true", help="hide the QEMU display")
    parser.add_argument("--accel", choices=["tcg", "kvm", "whpx"], default="tcg")
    args = parser.parse_args()
    try:
        if args.action == "doctor":
            return doctor()
        if args.action == "test":
            execute([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"])
            execute([sys.executable, "-m", "unittest", "discover", "-s", "lang/tests", "-p", "test_*.py"])
            execute([sys.executable, str(ROOT / "tests/run_qemu.py"), "--stage", "p0"])
            if args.stage == "p1":
                execute([sys.executable, str(ROOT / "tests/run_qemu.py"), "--stage", "p1", "--all"])
                execute([sys.executable, str(ROOT / "tests/run_cpu_qemu.py"), "--all"])
                execute([sys.executable, str(ROOT / "tests/run_memory_qemu.py"), "--all"])
                execute([sys.executable, str(ROOT / "tests/run_hardening_qemu.py"), "--all"])
                execute([sys.executable, str(ROOT / "tests/run_cache_qemu.py"), "--all"])
                execute([sys.executable, str(ROOT / "tests/run_permission_qemu.py"), "--all"])
                execute([sys.executable, str(ROOT / "tests/run_acpi_qemu.py"), "--all"])
                execute([sys.executable, str(ROOT / "tests/run_runtime_qemu.py"), "--all"])
            return 0
        esp = build(stage=args.stage, runtime_level=args.runtime_level, ipc_rounds=args.ipc_rounds,compiler_job=args.compiler_job)
        if args.action in ("run", "debug"):
            if args.action == "debug":
                print("QEMU paused; connect GDB with: target remote localhost:1234", flush=True)
            execute(qemu_command(esp, ROOT / "build/run" / args.stage, debug=args.action == "debug",
                                 headless=args.headless, accel=args.accel))
        return 0
    except (ToolError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
