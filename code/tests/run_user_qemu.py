#!/usr/bin/env python3
"""Actual CPL3 IPC gate, retaining the prior physical ACPI/runtime checks."""
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
from tools.elf_symbols import read_elf_symbols
from tests import run_runtime_qemu as runtime
from lang.dongc.modules import Resolver

ROOT = builder.ROOT
FIELDS = ('version process_count expected roundtrips syscalls calls replies user_errors '
          'rejections handles_created shared_physical shared_value start_tsc end_tsc elapsed_tsc '
          'tsc_hz elapsed_ns client_bias server_bias client_root server_root client_entry server_entry '
          'client_stack server_stack notification_bits completed steps error_code last_syscall').split()
STATE = Path('build/test/p4-user/qemu')


def project_user(serial, rounds):
    lines = [line.removesuffix(b'\r') for line in serial.split(b'\n')[:-1]]
    if not serial.endswith(b'\n') or lines.count(b'DONGOS_P4_USER_START') != 1 or lines.count(b'DONGOS_P4_IPC_READY') != 1:
        raise ValueError('missing/truncated actual user execution')
    start, stop = lines.index(b'DONGOS_P4_USER_START'), lines.index(b'DONGOS_P4_IPC_READY')
    if lines[start - 1] != b'DONGOS_P3_THREADS_READY' or lines[stop + 1:] != [b'DONGOS_P1_PASS']:
        raise ValueError('user execution ordering changed')
    progress = [f'user_progress=0x{i:016x}'.encode() for i in range(100000, rounds + 1, 100000)]
    body = lines[start + 1:stop]
    if body[:len(progress)] != progress or len(body) != len(progress) + len(FIELDS):
        raise ValueError('progress/report order or field count changed')
    fields = {}
    for name, line in zip(FIELDS, body[len(progress):]):
        match = re.fullmatch(('user_' + name).encode() + rb'=0x([0-9a-f]{16})', line)
        if match is None:
            raise ValueError('malformed/reordered/duplicate user field ' + name)
        fields[name] = int(match[1], 16)
    expected = dict(version=1, process_count=2, expected=rounds, roundtrips=rounds,
                    syscalls=2 * rounds + 15, calls=rounds, replies=rounds, user_errors=0,
                    rejections=5, handles_created=7, shared_value=rounds, notification_bits=4,
                    completed=1, steps=31, error_code=0, last_syscall=255)
    if any(fields[key] != value for key, value in expected.items()):
        raise ValueError('actual user protocol/counter/authority proof failed')
    if fields['end_tsc'] <= fields['start_tsc'] or fields['elapsed_tsc'] != fields['end_tsc'] - fields['start_tsc']:
        raise ValueError('invalid actual elapsed TSC')
    if fields['elapsed_ns'] != fields['elapsed_tsc'] * 1000000000 // fields['tsc_hz']:
        raise ValueError('actual elapsed time calculation mismatch')
    if fields['client_root'] == fields['server_root'] or any(fields[name] == 0 or fields[name] % 4096 for name in ('client_root', 'server_root', 'shared_physical')):
        raise ValueError('distinct physical process roots required')
    for role, base in (('client', 0x10000000), ('server', 0x30000000)):
        if not base <= fields[role + '_bias'] <= base + 255 * 65536 or fields[role + '_bias'] % 65536:
            raise ValueError('PIE placement outside randomized bounds')
        if fields[role + '_entry'] != fields[role + '_bias'] + 4096:
            raise ValueError('actual loaded ELF entry differs')
    return b'\r\n'.join(lines[:start] + lines[stop + 1:]) + b'\r\n', fields


def run_case(case, rounds, timeout=300):
    snapshot = {}
    original_project = runtime.project_runtime
    original_qmp = runtime.acpi.QMP
    actual_build = builder.build
    old_case = {'normal': 'q35', 'fxsave': 'q35'}.get(case, case)
    state = ROOT / STATE / case / old_case

    def project(serial):
        projected, fields = project_user(serial, rounds)
        snapshot['fields'] = fields
        return original_project(projected)

    def build(**kwargs):
        kwargs.update(runtime_level=4, ipc_rounds=rounds)
        return actual_build(**kwargs)

    class Observer(original_qmp):
        def request(self, command, arguments=None):
            answer = super().request(command, arguments)
            if command == 'query-cpus-fast' and not snapshot.get('physical_verified'):
                self.verify_user()
            return answer

        def verify_user(self):
            symbols = read_elf_symbols(state / 'build/kernel.elf')
            chunks = json.loads((state / 'physical-manifest.json').read_text())
            boot = next(item for item in chunks if item['role'] == 'BootInfo')
            info = struct.unpack('<20Q', (state / boot['file']).read_bytes())
            fields, reads = snapshot['fields'], []

            def physical(pa, count, role):
                if not 0 < pa < 1 << 32 or not 0 < count <= 65536 or pa + count > 1 << 32:
                    raise ValueError('unsafe physical user snapshot')
                path = state / f'user-physical-{len(reads):03d}.bin'
                super(Observer, self).request('pmemsave', {'val': pa, 'size': count, 'filename': str(path.resolve())})
                data = path.read_bytes()
                if len(data) != count:
                    raise ValueError('incomplete user snapshot')
                reads.append(dict(physical=pa, length=count, role=role, file=path.name, sha256=hashlib.sha256(data).hexdigest()))
                return data

            def kernel(va, count, role):
                if not symbols['__kernel_text_start'] <= va <= symbols['__kernel_bss_end'] - count:
                    raise ValueError('user report escaped retained kernel')
                return physical(info[15] + va - 0xffffffff80000000, count, role)

            pointer = struct.unpack('<Q', kernel(symbols['user_runtime_report'], 8, 'report pointer'))[0]
            if kernel(pointer, 240, 'user report') != struct.pack('<30Q', *(fields[key] for key in FIELDS)):
                raise ValueError('serial user report differs from independently dumped BSS')
            if struct.unpack('<Q', physical(fields['shared_physical'], 8, 'actual shared counter'))[0] != rounds:
                raise ValueError('actual shared physical counter differs')

            def pte(root, va):
                table = root
                for shift in (39, 30, 21, 12):
                    if not root <= table < root + 32 * 4096 or table % 4096:
                        raise ValueError('user page walk escaped exclusive pool')
                    value = struct.unpack('<Q', physical(table + ((va >> shift) & 511) * 8, 8, 'user PTE'))[0]
                    if not value & 1:
                        return value
                    if not value & 4:
                        raise ValueError('user ancestor lost USER access')
                    if shift == 12:
                        return value
                    if value & 128:
                        raise ValueError('unexpected user huge page')
                    table = value & 0x000ffffffffff000

            for role in ('client', 'server'):
                root, bias = fields[role + '_root'], fields[role + '_bias']
                image = (state / f'build/ipc_{role}.elf').read_bytes()
                phoff = struct.unpack_from('<Q', image, 32)[0]
                stride, count = struct.unpack_from('<HH', image, 54)
                for index in range(count):
                    kind, flags, offset, virtual, _, filesz, memsz, _ = struct.unpack_from('<IIQQQQQQ', image, phoff + stride * index)
                    if kind != 1:
                        continue
                    for page in range(virtual & ~4095, (virtual + memsz + 4095) & ~4095, 4096):
                        value = pte(root, page + bias)
                        if value & 0x800000000000001f != (5 | (2 if flags & 2 else 0) | (0 if flags & 1 else 1 << 63)):
                            raise ValueError('user segment lost exact USER/W^X/WB policy')
                        # Writable data changes during execution; immutable code must
                        # exactly match independently read bytes of the linked ELF.
                        first, last = max(page, virtual), min(page + 4096, virtual + filesz)
                        if flags & 1 and first < last:
                            pa = (value & 0x000ffffffffff000) + first - page
                            if physical(pa, last - first, 'actual user executable') != image[offset + first - virtual:offset + last - virtual]:
                                raise ValueError('loaded executable differs from its independent ELF')
                top = fields[role + '_stack']
                for guard in (top - 5 * 4096, top):
                    if pte(root, guard) != 0:
                        raise ValueError('user stack guard mapped')
                for va in range(top - 4 * 4096, top, 4096):
                    if pte(root, va) & 0x800000000000001f != 0x8000000000000007:
                        raise ValueError('user stack lost WB/RW/NX protection')
                if pte(root, 0x50000000) & ~0x60 != fields['shared_physical'] | 0x8000000000000007:
                    raise ValueError('shared mappings do not resolve to the same owned physical page')
            (state / 'user-physical-manifest.json').write_text(json.dumps(reads, indent=2) + '\n')
            snapshot.update(physical_verified=True, raw_physical_reads=len(reads), executable_bytes_verified=True,
                            private_roots_verified=True, guard_pages_verified=4, shared_physical_verified=True)

    with mock.patch.object(runtime, 'STATE', STATE), mock.patch.object(runtime, 'project_runtime', side_effect=project), \
         mock.patch.object(runtime.acpi, 'QMP', Observer), mock.patch.object(builder, 'build', side_effect=build):
        result = runtime.run_case(case, timeout)
    result['user'] = snapshot
    result['passed'] = result['passed'] and snapshot.get('physical_verified', False)
    (ROOT / STATE / case / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=runtime.CASES, default='normal')
    parser.add_argument('--rounds', type=int, default=1000000)
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    module = Resolver([ROOT / 'kernel', ROOT / 'lang/examples', ROOT / 'lang/std']).load(ROOT / 'kernel/user_probe.dg')
    paths = {Path(name) for name in module.source_files}
    # The bundle loader is developed independently behind SERVICE_BUNDLE=0;
    # retain the exact compiled assembly/listings/ELFs and all actual root inputs.
    paths.update(ROOT / name for name in ('tools/build.py', 'kernel/entry.asm', 'kernel/user/context.asm',
        'kernel/user_run.asm', 'kernel/runtime.asm', 'kernel/sched/context.asm', 'kernel/irq/hardware.asm',
        'services/lib/user.ld', 'services/init/ipc_client.asm', 'services/init/ipc_server.asm',
        'include/user_context.inc', 'tests/run_user_qemu.py'))
    hashes = lambda: {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    before = hashes()
    directory = ROOT / STATE
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f'{args.case}-source-before.json').write_text(json.dumps(before, indent=2) + '\n')
    result = run_case(args.case, args.rounds, args.timeout)
    after = hashes()
    result['source_unchanged'] = before == after
    result['passed'] = result['passed'] and before == after
    (directory / f'{args.case}-source-after.json').write_text(json.dumps(after, indent=2) + '\n')
    (directory / f'{args.case}-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('P4', args.case, 'PASS' if result['passed'] else 'FAIL', result.get('errors'))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
