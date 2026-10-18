#!/usr/bin/env python3
"""Real BSP preemption gate layered on the physical ACPI/old lifecycle gate."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import build as builder
from tests import run_acpi_qemu as acpi
from lang.dongc.modules import Resolver

ROOT = builder.ROOT
STATE = Path('build/test/p3-runtime/qemu')
CASES = ('normal', 'no-hpet', 'fxsave', 'production')
PLATFORM = ('lapic_pa', 'lapic_va', 'lapic_id', 'lapic_version', 'ioapic_count', 'redirection_count',
            'pic_master', 'pic_slave', 'reference_source', 'tsc_hz', 'lapic_hz', 'timer_mode', 'interval_ns',
            'last_tsc', 'last_deadline', 'arm_count', 'stop_count', 'spurious_vector', 'timer_vector', 'cr4',
            'rflags', 'ref_period_fs', 'ref_delta', 'steps')
SCHED = ('version', 'vector', 'ticks', 'switches', 'worker0_count', 'worker1_count', 'worker0_ticks',
         'worker1_ticks', 'worker0_fail', 'worker1_fail', 'gpr_checks', 'xstate_mode', 'xstate_bytes', 'xcr0',
         'cpuid1_ecx', 'cpuid1_edx', 'cpuidd_eax', 'cpuidd_edx', 'cr0', 'cr4', 'bootstrap_rsp', 'worker0_rsp',
         'worker1_rsp', 'worker0_stack_bottom', 'worker0_stack_top', 'worker1_stack_bottom', 'worker1_stack_top',
         'restore_checks', 'guard_count', 'steps')
BASE = 0xffffc00000000000


def project_runtime(serial):
    if not serial.endswith(b'\n'):
        raise ValueError('truncated runtime serial')
    lines = [line.removesuffix(b'\r') for line in serial.split(b'\n')[:-1]]
    start, stop = b'DONGOS_P3_RUNTIME_START', b'DONGOS_P3_THREADS_READY'
    if lines.count(start) != 1 or lines.count(stop) != 1:
        raise ValueError('exact runtime start and completion required')
    a, b = lines.index(start), lines.index(stop)
    if a < 1 or lines[a - 1] != b'DONGOS_P2_MEMORY_READY' or lines[b + 1:] != [b'DONGOS_P1_PASS']:
        raise ValueError('runtime must exclusively follow memory completion and precede actual PASS')
    names = ['platform_' + name for name in PLATFORM] + ['sched_' + name for name in SCHED]
    names += ['runtime_device_plan', 'runtime_spurious_count']
    if lines[a + 1] != b'DONGOS_P3_IRQ_READY' or b - a != len(names) + 2:
        raise ValueError('runtime IRQ stage or field count differs')
    values = {}
    for name, line in zip(names, lines[a + 2:b]):
        match = re.fullmatch(name.encode() + rb'=0x([0-9a-f]{16})', line)
        if match is None:
            raise ValueError('missing, reordered, duplicated or malformed ' + name)
        values[name] = int(match[1], 16)
    return b'\r\n'.join(lines[:a] + lines[b + 1:]) + b'\r\n', values


def validate_fields(values, case):
    p = {name: values['platform_' + name] for name in PLATFORM}
    s = {name: values['sched_' + name] for name in SCHED}
    if not (p['lapic_pa'] == 0xfee00000 and p['lapic_va'] == BASE and p['lapic_id'] == 0
            and p['ioapic_count'] == 1 and p['redirection_count'] == 24
            and p['pic_master'] == p['pic_slave'] == 255 and p['timer_vector'] == 0x40
            and p['spurious_vector'] == 255 and p['interval_ns'] == 10000000
            and p['arm_count'] == 130 and p['stop_count'] == 1 and p['steps'] == 127
            and 1000000 <= p['tsc_hz'] <= 16000000000 and p['timer_mode'] in (1, 2)
            and p['last_deadline'] > p['last_tsc'] and p['rflags'] & 0x60600 == 0):
        raise ValueError('controller/timer proof differs from actual q35 contract')
    if p['timer_mode'] == 2 and p['lapic_hz'] == 0:
        raise ValueError('one-shot fallback has no calibrated LAPIC frequency')
    if p['reference_source'] != (3 if case == 'no-hpet' else 2):
        raise ValueError('reference clock differs from configured hardware')
    if not (s['version'] == 1 and s['vector'] == 0x40 and s['ticks'] == 129 and s['switches'] == 65
            and s['worker0_ticks'] == s['worker1_ticks'] == 64 and s['worker0_count'] > 0
            and s['worker1_count'] > 0 and s['worker0_fail'] == s['worker1_fail'] == 0
            and s['gpr_checks'] == s['worker0_count'] + s['worker1_count']
            and s['restore_checks'] == 129 and s['guard_count'] == 2 and s['steps'] == 7):
        raise ValueError('real preemption/state preservation proof failed')
    if case == 'fxsave':
        if (s['xstate_mode'], s['xstate_bytes'], s['xcr0']) != (1, 512, 0):
            raise ValueError('XSAVE-disabled guest did not use actual FXSAVE path')
    elif (s['xstate_mode'], s['xstate_bytes'], s['xcr0']) != (2, 576, 3):
        raise ValueError('q35 max guest did not enable/save real x87/SSE XSAVE state')
    for index in (0, 1):
        lo, hi, sp = (s[f'worker{index}_{key}'] for key in ('stack_bottom', 'stack_top', 'rsp'))
        if hi - lo != 16384 or lo % 4096 or hi % 4096 or not lo <= sp < hi:
            raise ValueError('worker stack ownership is invalid')
    if values['runtime_spurious_count'] != 0:
        raise ValueError('unexpected spurious event in isolated proof')
    return p, s


def validate_controllers(lapic, pic):
    lvts = {name: int(value, 16) for name, value in re.findall(r'^(LVT\w*)\s+0x([0-9a-fA-F]+)', lapic, re.MULTILINE)}
    if set(lvts) != {'LVT0', 'LVT1', 'LVTPC', 'LVTERR', 'LVTTHMR', 'LVTT'} or any(not value & 0x10000 for value in lvts.values()):
        raise ValueError('actual local APIC LVT entries are not all masked after stop')
    if lvts['LVTT'] & 255 != 64 or not re.search(r'Timer\s+DCR=0x3 .*initial_count = 0 current_count = 0', lapic):
        raise ValueError('actual stopped LAPIC timer differs from its report')
    if not re.search(r'SPIV\s+0x000001ff APIC enabled', lapic) or not re.search(r'ESR\s+0x00000000', lapic):
        raise ValueError('actual LAPIC enable/spurious/error state is invalid')
    if not re.search(r'ISR\s+\(none\)', lapic) or not re.search(r'IRR\s+\(none\)', lapic):
        raise ValueError('EOI did not retire every actual timer interrupt')
    pins = [(int(pin), int(value, 16)) for pin, value in re.findall(r'pin\s+(\d+)\s+0x([0-9a-fA-F]+)', pic)]
    if [pin for pin, _ in pins] != list(range(24)) or any(not value & 0x10000 for _, value in pins):
        raise ValueError('actual IOAPIC redirection table is not fully masked')
    legacy = re.findall(r'pic([01]):[^\r\n]*imr=([0-9a-fA-F]+)', pic)
    if sorted(legacy) != [('0', 'ff'), ('1', 'ff')]:
        raise ValueError('both actual 8259 mask registers must equal ff')


def run_case(case, timeout=60):
    if case not in CASES:
        raise ValueError('unknown runtime case')
    old_case = {'normal': 'q35', 'fxsave': 'q35'}.get(case, case)
    directory = ROOT / STATE / case
    snapshot = {}
    original_qmp = acpi.QMP
    original_parse = acpi.parse_report

    def parse(serial, symbols, *, production=False):
        projected, values = project_runtime(serial)
        p, s = validate_fields(values, case)
        snapshot.update(fields=values, platform=p, scheduler=s)
        return original_parse(projected, symbols, production=production)

    class Observer(original_qmp):
        def request(self, command, arguments=None):
            answer = super().request(command, arguments)
            if command == 'query-cpus-fast' and not snapshot.get('hardware_verified'):
                self.verify_hardware()
            return answer

        def verify_hardware(self):
            state = directory / old_case
            symbols = acpi.validation_symbols(state / 'build/kernel.elf')
            chunks = json.loads((state / 'physical-manifest.json').read_text())
            boot = next(item for item in chunks if item['role'] == 'BootInfo')
            info = struct.unpack('<20Q', (state / boot['file']).read_bytes())
            runtime_reads = []

            def physical(pa, size, role):
                if not 0 < pa < 1 << 32 or not 0 < size <= 65536 or pa + size > 1 << 32:
                    raise ValueError('unsafe runtime physical snapshot request')
                path = state / f'runtime-physical-{len(runtime_reads):03d}.bin'
                super(Observer, self).request('pmemsave', {'val': pa, 'size': size, 'filename': str(path.resolve())})
                data = path.read_bytes()
                if len(data) != size:
                    raise ValueError('incomplete runtime physical dump')
                runtime_reads.append({'physical': pa, 'length': size, 'role': role, 'file': path.name,
                                      'sha256': hashlib.sha256(data).hexdigest()})
                return data

            def kernel(va, size, role):
                if not symbols['__kernel_text_start'] <= va <= symbols['__kernel_bss_end'] - size:
                    raise ValueError('runtime pointer outside retained kernel')
                return physical(info[15] + va - acpi.KERNEL, size, role)

            values, p, s = snapshot['fields'], snapshot['platform'], snapshot['scheduler']
            actual_p = kernel(symbols['runtime_platform_report'], 192, 'platform report')
            actual_s = kernel(symbols['sched_report'], 240, 'scheduler report')
            if actual_p != struct.pack('<24Q', *(p[name] for name in PLATFORM)) or actual_s != struct.pack('<30Q', *(s[name] for name in SCHED)):
                raise ValueError('runtime serial differs from actual linked BSS reports')
            plan_ptr = struct.unpack('<Q', kernel(symbols['runtime_device_plan'], 8, 'plan pointer'))[0]
            if plan_ptr != values['runtime_device_plan']:
                raise ValueError('runtime plan pointer differs from actual storage')
            plan = struct.unpack('<23Q', kernel(plan_ptr, 184, 'device plan'))
            expected_pages = [0xfee00000, 0xfec00000] + [0] * 7 + [0 if case == 'no-hpet' else 0xfed00000, 0]
            if list(plan[11:22]) != expected_pages or plan[22] != (2 if case == 'no-hpet' else 3):
                raise ValueError('device plan differs from independent q35 topology')
            registers = super().request('human-monitor-command', {'command-line': 'info registers'})
            root = int(re.search(r'CR3=([0-9a-fA-F]+)', registers)[1], 16)
            pool = root

            def pte(va):
                table = root
                for shift in (39, 30, 21, 12):
                    if not pool <= table < pool + 128 * 4096 or table % 4096:
                        raise ValueError('page walk escaped independently retained table pool')
                    entry = struct.unpack('<Q', physical(table + ((va >> shift) & 511) * 8, 8, 'PTE'))[0]
                    if not entry & 1:
                        return entry
                    if shift == 12:
                        return entry
                    if entry & 0x80:
                        raise ValueError('runtime mappings unexpectedly use a huge page')
                    table = entry & 0x000ffffffffff000

            for slot, pa in enumerate(expected_pages):
                value = pte(BASE + slot * 4096)
                if pa:
                    if value & ~0x60 != (pa | 0x800000000000001b):
                        raise ValueError('device alias lost exact UC/RW/NX/supervisor/raw PA policy')
                elif value != 0:
                    raise ValueError('unused device alias is present')
            guards = struct.unpack('<4Q', kernel(symbols['sched_guard_ranges'], 32, 'guard metadata'))
            for va in guards:
                if pte(va) != 0:
                    raise ValueError('scheduler guard page remains mapped')
            for index in (0, 1):
                for va in range(s[f'worker{index}_stack_bottom'], s[f'worker{index}_stack_top'], 4096):
                    if pte(va) & ~0x60 != ((info[15] + va - acpi.KERNEL) | 0x8000000000000003):
                        raise ValueError('scheduler stack lost exact WB/RW/NX/supervisor backing')
            engine = struct.unpack('<56Q', kernel(symbols['sched_engine'], 448, 'scheduler engine'))
            if engine[:4] != (0, 129, 65, 2) or engine[8 + 2] != 1 or engine[8 + 6 + 2] != 64 or engine[8 + 12 + 2] != 64:
                raise ValueError('actual scheduler engine does not prove all three interrupt owners')
            lapic = super().request('human-monitor-command', {'command-line': 'info lapic'})
            pic = super().request('human-monitor-command', {'command-line': 'info pic'})
            (state / 'lapic.txt').write_text(lapic, encoding='utf-8')
            (state / 'pic.txt').write_text(pic, encoding='utf-8')
            validate_controllers(lapic, pic)
            (state / 'runtime-physical-manifest.json').write_text(json.dumps(runtime_reads, indent=2) + '\n')
            snapshot.update(hardware_verified=True, raw_runtime_reads=len(runtime_reads), device_pages=plan[22], guard_pages=len(guards))

    def runtime_build(**kwargs):
        return builder.build(runtime_level=3, **kwargs)

    original_popen = acpi.subprocess.Popen

    def popen(command, *args, **kwargs):
        if case == 'fxsave' and '-cpu' in command:
            command = list(command)
            command[command.index('-cpu') + 1] += ',-xsave'
        return original_popen(command, *args, **kwargs)

    with mock.patch.object(acpi, 'STATE_DIR', STATE / case), mock.patch.object(acpi, 'build', side_effect=runtime_build), \
         mock.patch.object(acpi, 'parse_report', side_effect=parse), mock.patch.object(acpi, 'QMP', Observer), \
         mock.patch.object(acpi.subprocess, 'Popen', side_effect=popen):
        result = acpi.run_case(old_case, timeout)
    result['runtime_case'] = case
    result['runtime'] = snapshot
    if result['passed'] and not snapshot.get('hardware_verified'):
        result['passed'] = False
        result['errors'].append('independent runtime snapshot never executed')
    (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES, default='normal')
    parser.add_argument('--all', action='store_true')
    args = parser.parse_args()
    module = Resolver([ROOT / 'kernel', ROOT / 'lang/examples', ROOT / 'lang/std']).load(ROOT / 'kernel/runtime_probe.dg')
    paths = [Path(name) for name in module.source_files]
    paths += [ROOT / name for name in ('kernel/entry.asm', 'kernel/abi_probe.asm', 'kernel/cpu.asm', 'kernel/panic.asm',
              'kernel/memory_runtime.asm', 'kernel/stack_bridge.asm', 'kernel/memory_mutation.asm', 'kernel/cpu_hardening.asm',
              'kernel/runtime.asm', 'kernel/irq/hardware.asm', 'kernel/sched/context.asm', 'kernel/linker.ld',
              'lang/std/arch/x86_64.asm', 'boot/efi_main.asm', 'boot/image.asm', 'tools/build.py',
              'tests/run_runtime_qemu.py', 'tests/run_acpi_qemu.py', 'tests/acpi_reference.py')]
    # Track the headers actually referenced by this runtime, including nested
    # static includes. Independently developed P4 headers are not inputs here.
    seen = set(paths)
    pending = [path for path in paths if path.suffix == '.asm']
    while pending:
        path = pending.pop()
        for name in re.findall(r'%include\s+"([^"]+)"', path.read_text(encoding='utf-8')):
            header = ROOT / 'include' / name
            if header.is_file() and header not in seen:
                seen.add(header)
                paths.append(header)
                pending.append(header)
    def hashes():
        return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(set(paths))}
    before = hashes()
    (ROOT / STATE).mkdir(parents=True, exist_ok=True)
    (ROOT / STATE / 'source-before.json').write_text(json.dumps(before, indent=2) + '\n')
    results = [run_case(case) for case in CASES if args.all or case == args.case]
    after = hashes()
    (ROOT / STATE / 'source-after.json').write_text(json.dumps(after, indent=2) + '\n')
    passed = before == after and all(row['passed'] for row in results)
    (ROOT / STATE / 'result.json').write_text(json.dumps({'passed': passed, 'source_unchanged': before == after, 'results': results}, indent=2) + '\n')
    print([(row['runtime_case'], row['passed'], row['errors']) for row in results])
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
