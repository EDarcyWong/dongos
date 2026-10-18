#!/usr/bin/env python3
"""Validate copied ACPI topology against independent physical firmware bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import time
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build import ROOT, build, qemu_command
from tools.elf_symbols import read_elf_symbols
from tests import run_cache_qemu as cache
from tests import acpi_protocol as protocol, acpi_reference as reference

STATE_DIR = Path('build/test/p3-acpi/qemu')
CASES = ('q35', 'no-hpet', 'one-cpu', 'production')
SCALARS = ('rsdp', 'xsdt', 'madt', 'fadt', 'hpet', 'mcfg', 'rsdp_revision', 'table_count',
           'lapic_address', 'madt_flags', 'cpu_count', 'ioapic_count', 'iso_count', 'nmi_count', 'mcfg_count',
           'fadt_revision', 'fadt_flags', 'sci_interrupt', 'boot_arch', 'dsdt', 'pm_timer_block', 'pm_timer_length',
           'pm_timer_32bit', 'reset_value', 'hpet_id', 'hpet_number', 'hpet_min_tick', 'hpet_page_protection')
GAS_FIELDS = ('address_space', 'bit_width', 'bit_offset', 'access_size', 'address')
GASES = ('pm_timer_gas', 'reset_gas', 'hpet_gas')
ARRAYS = {'cpus': (16, ('kind', 'uid', 'apic_id', 'flags')), 'ioapics': (8, ('id', 'address', 'gsi_base')),
          'isos': (16, ('bus', 'source', 'gsi', 'flags')), 'nmis': (16, ('kind', 'processor', 'flags', 'lint', 'gsi')),
          'mcfg_regions': (8, ('base', 'segment', 'start_bus', 'end_bus'))}
KERNEL, HHDM, LIMIT = 0xffffffff80000000, 0xffff800000000000, 1 << 32


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


class QMP:
    def __init__(self, port, process):
        deadline = time.monotonic() + 15
        while True:
            try:
                self.socket = socket.create_connection(('127.0.0.1', port), timeout=1)
                break
            except OSError:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise
                time.sleep(.1)
        self.file = None
        try:
            self.socket.settimeout(10)
            self.file = self.socket.makefile('rwb')
            if 'QMP' not in json.loads(self.file.readline()):
                raise ValueError('QMP greeting missing')
            self.request('qmp_capabilities')
        except BaseException:
            try:
                self.close()
            except Exception:
                pass
            raise

    def request(self, command, arguments=None):
        self.file.write(json.dumps({'execute': command, **({'arguments': arguments} if arguments is not None else {})}).encode() + b'\n')
        self.file.flush()
        while True:
            item = json.loads(self.file.readline())
            if 'error' in item:
                raise RuntimeError(item['error'])
            if 'return' in item:
                return item['return']

    def close(self):
        try:
            if self.file is not None:
                self.file.close()
        finally:
            self.socket.close()


def inventory_bytes(value):
    values = [value[name] for name in SCALARS]
    for name in GASES:
        values += [value[name][field] for field in GAS_FIELDS]
    for name, (capacity, fields) in ARRAYS.items():
        if len(value[name]) > capacity:
            raise ValueError('firmware inventory exceeds bounded ' + name)
        for index in range(capacity):
            values += [value[name][index][field] if index < len(value[name]) else 0 for field in fields]
    data = struct.pack('<' + 'Q' * len(values), *values)
    assert len(data) == 2456
    return data


def expected_report(value):
    answer = {name: value[name] for name in protocol.FIELDS if name in value}
    def gas_info(gas):
        return sum(gas[name] << (i * 8) for i, name in enumerate(GAS_FIELDS[:4]))
    answer.update(hpet_gas_info=gas_info(value['hpet_gas']), hpet_address=value['hpet_gas']['address'],
                  pm_timer_gas_info=gas_info(value['pm_timer_gas']), pm_timer_address=value['pm_timer_gas']['address'], steps=7)
    assert set(answer) == set(protocol.FIELDS)
    return answer


def validation_symbols(elf):
    symbols = cache.read_validation_symbols(elf)
    for name in ('p3_acpi_report', 'p3_acpi_report_end', 'p3_acpi_inventory', 'memory_activation_entry.halt'):
        if name not in symbols:
            raise ValueError('missing ACPI ELF symbol ' + name)
    if symbols['p3_acpi_report_end'] - symbols['p3_acpi_report'] != 192:
        raise ValueError('ACPI report ELF span must be 192 bytes')
    manifest = json.loads(Path(elf).with_name('dong_layout.json').read_text())
    types = {item['full_name']: item for item in manifest['types']}
    report = types['boot.acpi_startup.Report']
    if report['size'] != 192 or report['alignment'] != 8 or [(item['name'], item['offset']) for item in report['fields']] != [(name, i * 8) for i, name in enumerate(protocol.FIELDS)]:
        raise ValueError('ACPI Report does not match independent 24-field ABI')
    spans = []
    offset = 0
    for name in SCALARS:
        spans.append((name, offset)); offset += 8
    for name in GASES:
        spans.append((name, offset)); offset += 40
    for name, (capacity, fields) in ARRAYS.items():
        spans.append((name, offset)); offset += capacity * len(fields) * 8
    inventory = types['firmware.acpi.Inventory']
    if inventory['size'] != 2456 or inventory['alignment'] != 8 or [(item['name'], item['offset']) for item in inventory['fields']] != spans:
        raise ValueError('ACPI Inventory does not match independent 2456-byte ABI')
    children = {'Gas': GAS_FIELDS, 'Cpu': ARRAYS['cpus'][1], 'IoApic': ARRAYS['ioapics'][1],
                'Iso': ARRAYS['isos'][1], 'Nmi': ARRAYS['nmis'][1], 'McfgRegion': ARRAYS['mcfg_regions'][1]}
    for name, fields in children.items():
        child = types['firmware.acpi.' + name]
        if child['size'] != len(fields) * 8 or child['alignment'] != 8 or [(item['name'], item['offset']) for item in child['fields']] != [(field, i * 8) for i, field in enumerate(fields)]:
            raise ValueError('ACPI nested record ABI differs: ' + name)
    for name in ('p3_acpi_report', 'p3_acpi_inventory'):
        if symbols[name] % 8 or not symbols['__kernel_bss_start'] <= symbols[name] <= symbols['__kernel_bss_end'] - (192 if name.endswith('report') else 8):
            raise ValueError('ACPI exported storage must reside in retained BSS')
    return symbols


def parse_report(serial, symbols, *, production=False):
    if isinstance(serial, str):
        serial = serial.encode()
    if not serial.endswith(b'\n'):
        raise ValueError('truncated ACPI serial')
    lines = [line.removesuffix(b'\r') for line in serial.split(b'\n')[:-1]]
    _, errors = protocol.project(lines)
    if errors or lines.count(protocol.READY) != 1:
        raise ValueError('invalid ACPI stage: ' + repr(errors))
    pairs = [protocol.LINE.fullmatch(line) for line in lines if line.startswith(b'acpi_')]
    if any(pair is None for pair in pairs):
        raise ValueError('malformed ACPI field')
    values = {pair[1].decode(): int(pair[2], 16) for pair in pairs}
    if production:
        retries = lines.count(b'DONGOS_P1_EBS_RETRY')
        if retries > 7:
            raise ValueError('production firmware exceeded bounded EBS retry count')
        prefix = list(cache.memory.PREFIX_MARKERS)
        index = prefix.index(b'DONGOS_P1_EBS_RETRY')
        prefix[index:index + 1] = [b'DONGOS_P1_EBS_RETRY'] * retries
        with mock.patch.object(cache.memory, 'PREFIX_MARKERS', prefix):
            base = cache.parse_result(serial, case='all-features', symbols=symbols)
    else:
        base = cache.parse_result(serial, case='all-features', symbols=symbols)
    if not base['passed']:
        raise ValueError('prior lifecycle failed: ' + repr(base['errors']))
    return values, base


def read_map(raw, stride):
    if stride < 40 or stride % 8 or not raw or len(raw) > 65536 or len(raw) % stride:
        raise ValueError('invalid original UEFI map shape')
    entries = []
    for offset in range(0, len(raw), stride):
        kind = struct.unpack_from('<I', raw, offset)[0]
        start, pages, attributes = (struct.unpack_from('<Q', raw, offset + i)[0] for i in (8, 24, 32))
        end = start + pages * 4096
        if start % 4096 or pages == 0 or end > (1 << 64) - 1 or any(start < stop and begin < end for begin, stop, _, _ in entries):
            raise ValueError('invalid original UEFI descriptor range')
        entries.append((start, end, kind, attributes))
    return entries


def acpi_range(entries, pa, size):
    if pa <= 0 or size <= 0 or pa + size > LIMIT:
        return False
    cursor = pa
    while cursor < pa + size:
        found = [(end, kind, attrs) for start, end, kind, attrs in entries if start <= cursor < end]
        if len(found) != 1 or found[0][1] not in (9, 10) or found[0][2] & (1 << 63):
            return False
        cursor = found[0][0]
    return True


def run_case(case, timeout=60.0):
    if case not in CASES or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('known ACPI case and finite positive timeout required')
    state = ROOT / STATE_DIR / case
    state.mkdir(parents=True, exist_ok=True)
    serial_path = state / 'serial.log'
    serial_path.write_bytes(b'')
    result = {'case': case, 'passed': False, 'status': 'building', 'actual_qemu_executed': False, 'errors': []}
    write_json(state / 'result.json', result)
    process, qmp = None, None
    started = time.monotonic()
    try:
        esp = build(test=case != 'production', output=state / 'build')
        elf = esp.parent / 'kernel.elf'
        symbols = validation_symbols(elf)
        if case == 'production' and any(name.startswith(('permission_', 'cpu_test_', 'memory_test_',
                  'memory_activation_test_', 'memory_mutation_test_', 'object_memory_test_')) for name in symbols):
            raise ValueError('production image contains a test fault helper')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
        command = qemu_command(esp, state, test=True)
        index = command.index('-device')
        assert command[index + 1].startswith('isa-debug-exit,')
        del command[index:index + 2]
        command += ['-vga', 'std', '-cpu', 'max,+smep,+smap,+umip', '-S', '-qmp', f'tcp:127.0.0.1:{port},server=on,wait=off']
        if case == 'one-cpu':
            command[command.index('-smp') + 1] = '1'
        if case == 'no-hpet':
            command[command.index('-machine') + 1] += ',hpet=off'
        result.update(command=command, kernel_elf=str(elf), status='running')
        write_json(state / 'result.json', result)
        with (state / 'qemu.stdout.log').open('wb') as stdout, (state / 'qemu.stderr.log').open('wb') as stderr:
            process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
            result['actual_qemu_executed'] = True
            qmp = QMP(port, process)
            qmp.request('cont')
            deadline = time.monotonic() + timeout
            halt = symbols['memory_activation_entry.halt']
            while True:
                serial = serial_path.read_bytes()
                if b'FAIL' in serial or b'PANIC' in serial:
                    raise ValueError('guest failed before ACPI normal completion')
                if b'DONGOS_P1_PASS\r\n' in serial:
                    registers = qmp.request('human-monitor-command', {'command-line': 'info registers'})
                    match = re.search(r'RIP=([0-9a-fA-F]+)', registers)
                    if match and int(match[1], 16) in (halt, halt + 1) and 'HLT=1' in registers:
                        break
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise TimeoutError('ACPI guest did not reach linked normal HLT')
                time.sleep(.1)
            qmp.request('stop')
            registers = qmp.request('human-monitor-command', {'command-line': 'info registers'})
            (state / 'registers.txt').write_text(registers)
            if 'HLT=1' not in registers or 'CPL=0' not in registers or int(re.search(r'RIP=([0-9a-fA-F]+)', registers)[1], 16) not in (halt, halt + 1):
                raise ValueError('stopped ACPI guest lost its linked CPL0 HLT')
            fields, base = parse_report(serial, symbols, production=case == 'production')
            result.update(acpi=fields, prior=base)
            chunks = []
            def physical(pa, size, role='firmware'):
                if pa <= 0 or size <= 0 or size > 1 << 20 or pa + size > LIMIT:
                    raise ValueError('bounded physical dump range required')
                path = state / f'physical-{len(chunks):03d}.bin'
                qmp.request('pmemsave', {'val': pa, 'size': size, 'filename': str(path.resolve())})
                data = path.read_bytes()
                if len(data) != size:
                    raise ValueError('incomplete physical dump')
                chunks.append({'physical': pa, 'length': size, 'file': path.name, 'role': role, 'sha256': hashlib.sha256(data).hexdigest()})
                write_json(state / 'physical-manifest.json', chunks)
                return data
            old = base['hardening']['memory']['fields']
            info = struct.unpack('<20Q', physical(old['runtime_boot_info'] - HHDM, 160, 'BootInfo'))
            if info[:3] != (0x544f4f42474e4f44, 1, 160) or info[7] != 1 or not info[3] & 1:
                raise ValueError('physical BootInfo differs from original v1 contract')
            entries = read_map(physical(info[4], info[5], 'UEFI map'), info[6])
            def read(pa, size):
                if not acpi_range(entries, pa, size):
                    raise ValueError('firmware table is outside retained non-runtime ACPI RAM')
                return physical(pa, size)
            expected = reference.discover(read, info[14])
            write_json(state / 'independent-inventory.json', expected)
            if fields != expected_report(expected):
                raise ValueError('ACPI serial differs from independent physical table interpretation')
            kernel_physical = info[15]
            pointer = struct.unpack('<Q', physical(kernel_physical + symbols['p3_acpi_inventory'] - KERNEL, 8, 'inventory pointer'))[0]
            if pointer % 8 or not symbols['__kernel_bss_start'] <= pointer <= symbols['__kernel_bss_end'] - 2456:
                raise ValueError('published inventory is outside retained aligned BSS')
            actual = physical(kernel_physical + pointer - KERNEL, 2456, 'inventory')
            if actual != inventory_bytes(expected):
                raise ValueError('entire copied Inventory (including unused slots) differs from independent firmware')
            raw_report = physical(kernel_physical + symbols['p3_acpi_report'] - KERNEL, 192, 'report')
            if raw_report != struct.pack('<24Q', *(fields[name] for name in protocol.FIELDS)):
                raise ValueError('serial differs from actual BSS report')
            if fields['cpu_count'] != len(qmp.request('query-cpus-fast')) or fields['cpu_count'] != (1 if case == 'one-cpu' else 4):
                raise ValueError('MADT CPU topology differs from configured processors')
            if (case == 'no-hpet') != (fields['hpet'] == 0):
                raise ValueError('HPET presence differs from explicit VM configuration')
            controls = {name: int(value, 16) for name, value in re.findall(r'\b(CR0|CR3|CR4|EFER)=([0-9a-fA-F]+)', registers)}
            if controls['CR4'] != base['hardening']['hardening']['cr4_after'] or controls['CR3'] != base['cache']['root']:
                raise ValueError('ACPI changed the hardened active controls')
            for name in ('cr0', 'efer'):
                if controls[name.upper()] != base['hardening']['hardening'][name]:
                    raise ValueError('ACPI changed ' + name.upper())
            flags = int(re.search(r'RFL=([0-9a-fA-F]+)', registers)[1], 16)
            if flags & 0x60600 or not flags & 2:
                raise ValueError('ACPI completion lost IF/DF/VM/AC policy')
            write_json(state / 'physical-manifest.json', chunks)
            result.update(passed=True, status='passed', physical_inventory_verified=True, inventory_virtual=pointer,
                          raw_physical_reads=len(chunks), current_controls=controls,
                          termination='Host QMP quit after linked HLT, original lifecycle and independent physical inventory validation; no guest exit code synthesized.')
    except (Exception, KeyboardInterrupt) as exc:
        result['errors'].append(f'{type(exc).__name__}: {exc}')
        result['status'] = 'failed'
        result['interrupted'] = isinstance(exc, KeyboardInterrupt)
    finally:
        if qmp is not None:
            try:
                qmp.request('quit')
            except Exception as exc:
                if not isinstance(exc, (OSError, json.JSONDecodeError)):
                    result['errors'].append(f'QMP quit failed: {exc}')
            try:
                qmp.close()
            except Exception as exc:
                result['errors'].append(f'QMP close failed: {exc}')
        if process is not None:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                result['errors'].append('QEMU did not quit after host observation completed')
                try:
                    cache.memory.reap_process(process)
                except Exception as exc:
                    result['errors'].append(f'QEMU cleanup failed: {exc}')
            except Exception as exc:
                result['errors'].append(f'QEMU wait failed: {exc}')
                try:
                    cache.memory.reap_process(process)
                except Exception as cleanup:
                    result['errors'].append(f'QEMU cleanup failed: {cleanup}')
            result['qemu_shutdown_returncode'] = process.returncode
        if result['errors']:
            result.update(passed=False, status='failed')
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        write_json(state / 'result.json', result)
    print(('PASS' if result['passed'] else 'FAIL') + ' P3 ACPI/' + case, flush=True)
    for error in result['errors']:
        print('  ' + error, flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--case', choices=CASES)
    selection.add_argument('--all', action='store_true')
    parser.add_argument('--timeout', type=float, default=60)
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('timeout must be finite and positive')
    directory = ROOT / STATE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    results = []
    write_json(directory / 'result.json', {'passed': False, 'status': 'running', 'results': results})
    for case in CASES if args.all else (args.case or 'q35',):
        results.append(run_case(case, args.timeout))
        write_json(directory / 'result.json', {'passed': False, 'status': 'running', 'results': results})
        if results[-1].get('interrupted'):
            break
    passed = bool(results) and all(row['passed'] for row in results)
    write_json(directory / 'result.json', {'passed': passed, 'status': 'complete', 'results': results})
    return 130 if any(row.get('interrupted') for row in results) else 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
