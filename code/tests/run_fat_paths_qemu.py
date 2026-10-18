#!/usr/bin/env python3
"""Actual UTF-8 FAT32 paths/LFN writes, FLUSH and same-image two-boot gate.

Only root runs this against an already completed normal runtime7 ESP. The
runner creates a fresh seed-only ordinary data image. Every probe file is made
by actual shell commands; physical guest inspection is read-only.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build_usb import verify_build
from tools.make_fat32_disk import create, SEED
from tests import fat_paths_oracle as oracle
from tests import run_nvme_qemu as nvme

ROOT, settings, storage = nvme.ROOT, nvme.settings, nvme.storage
WORK = '/\u5de5\u4f5c \u6587\u4ef6'
SUB = WORK + '/\u5b50\u76ee\u5f55\U0001f600'
DEEP = SUB + '/Deep Space'
BOUNDARY = '/Boundary Cases'
BIG = SUB + '/\u4f1a\u8bae \u8bb0\u5f55\U0001f600.txt'
CROSS = BOUNDARY + '/\u8de8\u8d8a \u6247\u533a\u8fb9\u754c\u7684\u957f\u6587\u4ef6\u540d\U0001f600.txt'
REPLACED = SUB + '/replace long name.txt'
EMPTY = DEEP + '/empty long name.txt'
REMOVED = SUB + '/delete long name.txt'
REMOVED_DIR = SUB + '/remove empty directory'
COLLISIONS = [BOUNDARY + '/Collision common prefix ' + word + '.txt' for word in ('one', 'two')]
DIRECTORIES = [WORK, SUB, DEEP, BOUNDARY]


def quote(path):
    settings.check(isinstance(path, str) and '\r' not in path and '\n' not in path
                   and '\0' not in path, 'unsafe shell path')
    return '"' + path.replace('\\', '\\\\').replace('"', '\\"') + '"'


def command_bytes(command):
    settings.check(isinstance(command, str) and command and '\r' not in command and '\n' not in command
                   and all(ord(c) >= 32 and ord(c) != 127 for c in command), 'invalid UART command')
    encoded = command.encode('utf-8', errors='strict')
    settings.check(len(encoded) <= 8191, 'UART command exceeds actual 8191-byte line capacity')
    return encoded


def fresh_response(segment, command, *, expected=None, expect_error=False, exact=None):
    """Only bytes after the fresh complete echo and before the new prompt count."""
    encoded = command_bytes(command)
    echo = encoded + b'\r\n'
    at = segment.find(echo)
    if at < 0:
        return None
    body_start = at + len(echo)
    prompt = segment.find(b'> ', body_start)
    if prompt < 0:
        return None
    settings.check(segment.find(echo, body_start) < 0, 'duplicate fresh command echo')
    body = segment[body_start:prompt]
    settings.check(b'PANIC' not in segment and b'DONGOS_P1_KERNEL_FAIL' not in segment,
                   'actual guest failed during command')
    errors = re.findall(rb'^ERROR 0x([0-9a-f]{16})\r\n', body, re.MULTILINE)
    if expect_error:
        settings.check(len(errors) == 1 and body == b'ERROR 0x' + errors[0] + b'\r\n',
                       'rejected command did not return one exact filesystem error')
        settings.check(int(errors[0], 16) != 0, 'error status was zero')
    else:
        settings.check(b'ERROR ' not in body and b'unknown command' not in body
                       and b'filename required' not in body, 'fresh UART command failed')
    if expected is not None:
        settings.check(expected in body, 'expected bytes occur only in echo or are missing from fresh response')
    if exact is not None:
        settings.check(body == exact, 'fresh command returned unexpected literal bytes')
    return dict(response_hex=body.hex(), error_code=int(errors[0], 16) if errors else 0,
                complete_echo_and_new_prompt_verified=True)


def effective_mapping(root, virtual, read_table, kernel_pool, private_pages=32):
    """Walk full ancestor permissions, including inherited supervisor mappings."""
    kernel_base, kernel_pages = kernel_pool
    settings.check(private_pages in (32,128) and kernel_pages == 128 and root % 4096 == kernel_base % 4096 == 0,
                   'invalid trusted/private page table pools')
    allowed = ((root, root + private_pages * 4096), (kernel_base, kernel_base + kernel_pages * 4096))
    table, user, writable, nx = root, True, True, False
    visited, path = set(), []
    for shift in (39, 30, 21, 12):
        settings.check(table not in visited and table % 4096 == 0
                       and any(first <= table < last for first, last in allowed),
                       'IPC page table outside trusted private/trusted kernel128 pools or cycle')
        visited.add(table)
        raw = read_table(table)
        settings.check(len(raw) == 4096, 'incomplete IPC page table')
        entry = struct_unpack_entry(raw, virtual, shift)
        path.append(dict(table=table, shift=shift, entry=entry))
        if not entry & 1:
            return dict(present=False, effective_user=False, path=path)
        user = user and bool(entry & 4)
        writable = writable and bool(entry & 2)
        nx = nx or bool(entry & (1 << 63))
        if shift == 12 or (shift in (30, 21) and entry & 128):
            if shift != 12:
                reserved = ((1 << shift) - 1) & ~((1 << 13) - 1)
                settings.check(entry & reserved == 0, 'reserved large IPC mapping alignment bits')
            physical = (entry & storage.MASK & ~((1 << shift) - 1)) + (virtual & ((1 << shift) - 1))
            return dict(present=True, effective_user=user, effective_writable=writable,
                        effective_nx=nx, leaf_bytes=1 << shift, physical=physical,
                        leaf_entry=entry, path=path)
        settings.check(not (shift == 39 and entry & 128), 'invalid large PML4 mapping')
        table = entry & storage.MASK
    raise ValueError('IPC page-table walk did not reach a leaf')


def struct_unpack_entry(raw, virtual, shift):
    # Deliberately independent of inherited Guest.pte(), which requires USER
    # on every ancestor and therefore cannot prove supervisor-only absence.
    import struct
    return struct.unpack_from('<Q', raw, ((virtual >> shift) & 511) * 8)[0]


def verify_channels(roots, read_table, kernel_pool, pool_pages=None):
    pool_pages=[32]*5 if pool_pages is None else pool_pages
    settings.check(pool_pages in ([32]*5,[32,32,32,128,32]),'invalid channel pool capacities')
    settings.check(len(roots) == 5 and len(set(roots)) == 5, 'five distinct private roots required')
    descriptions = ((0x50000000, (0, 1), 'shell-fs'),
                    (0x51000000, (1, 2), 'fs-block'),
                    (0x52000000, (1, 3), 'compositor-fs'))
    records, all_physical = [], set()
    for virtual, owners, name in descriptions:
        pages = []
        for index in range(16):
            address = virtual + index * 4096
            mappings = [effective_mapping(root, address, read_table, kernel_pool, pool_pages[pid]) for pid,root in enumerate(roots)]
            for pid, mapping in enumerate(mappings):
                if pid in owners:
                    settings.check(mapping['present'] and mapping['effective_user']
                                   and mapping['effective_writable'] and mapping['effective_nx']
                                   and mapping['leaf_bytes'] == 4096 and mapping['leaf_entry'] & 0x198 == 0,
                                   'IPC owner page is not private non-global WB/RW/NX/effectively USER')
                else:
                    settings.check(not mapping['effective_user'],
                                   f'IPC {name} visible to unauthorized process {pid}')
            pa = mappings[owners[0]]['physical']
            settings.check(pa == mappings[owners[1]]['physical'] and pa % 4096 == 0 and pa > 0,
                           'authorized IPC peers do not map the exact same physical page')
            settings.check(pa not in all_physical, 'distinct IPC channel pages physically alias')
            all_physical.add(pa)
            pages.append(dict(index=index, virtual=address, physical=pa,
                              process_mappings={str(pid): mapping for pid, mapping in enumerate(mappings)}))
        records.append(dict(name=name, virtual=virtual, pages=pages, authorized_processes=list(owners),
                            page_count=16, all_effective_user_rw_nx_wb=True,
                            unauthorized_processes_have_no_effective_user_mapping=True))
    return dict(channels=records, distinct_physical_pages=len(all_physical),
                channels_physically_distinct=True, effective_ancestor_permissions_verified=True)


class FatGuest(nvme.NvmeGuest):
    def shell(self, command, expected=None, *, expect_error=False, exact=None):
        encoded = command_bytes(command)
        before = len(self.raw)
        self.resume()
        self.uart.sendall(encoded + b'\r')
        deadline = time.monotonic() + 90
        while True:
            segment = bytes(self.raw[before:])
            response = fresh_response(segment, command, expected=expected,
                                      expect_error=expect_error, exact=exact)
            if response is not None:
                break
            settings.check(self.process.poll() is None and b'PANIC' not in self.raw
                           and b'DONGOS_P1_KERNEL_FAIL' not in self.raw, 'actual guest failure')
            settings.check(time.monotonic() < deadline, 'UTF-8 UART response timeout')
            time.sleep(.01)
        self.pause()
        return dict(command=command, command_utf8_sha256=hashlib.sha256(encoded).hexdigest(),
                    serial_offset=before, serial_segment_sha256=hashlib.sha256(segment).hexdigest(), **response)

    def channel_snapshot(self):
        kernel_pool = self.trusted_kernel_pool()
        tables = {}
        def read_table(physical):
            if physical not in tables:
                tables[physical] = self.physical(physical, 4096, 'actual IPC channel page table')
            return tables[physical]
        result = verify_channels(self.roots, read_table, kernel_pool, self.pool_limits[:len(self.roots)])
        result['unique_tables_read'] = len(tables)
        self.evidence['private_ipc_channels_verified'] = True
        return result


def file_payloads(run_name):
    first = ('\u8de8\u7c07 \u6570\u636e\U0001f600 ' + run_name + ' ORIGINAL ' + '0123456789abcdefghijklmno' * 190).encode()
    tail = ('APPENDED ' + run_name + ' ' + 'ZYXWVUTSRQPONMLKJIHGFEDCBA9876543210' * 31).encode()
    files = {'/README.TXT': SEED, BIG: first + tail, CROSS: ('sector-crossing ' + run_name).encode(),
             REPLACED: ('AFTER ' + run_name).encode(), EMPTY: b'',
             COLLISIONS[0]: ('alias first ' + run_name).encode(),
             COLLISIONS[1]: ('alias second ' + run_name).encode()}
    for index in range(13):
        files[BOUNDARY + '/F%02d.TXT' % index] = b''
    return files, first, tail


def populate(guest, run_name):
    files, first, tail = file_payloads(run_name)
    commands = []
    call = lambda command, expected=None, **kw: commands.append(guest.shell(command, expected, **kw))
    call('pwd', exact=b'/\r\n')
    for directory in DIRECTORIES:
        call('mkdir ' + quote(directory), b'MKDIR OK\r\n')
    call('cd ' + quote(SUB), b'CD OK\r\n')
    call('pwd', exact=SUB.encode() + b'\r\n')
    call('write ' + quote(BIG.rsplit('/', 1)[1]) + ' ' + first.decode(), b'WRITE OK\r\n')
    call('append ' + quote(BIG.rsplit('/', 1)[1]) + ' ' + tail.decode(), b'APPEND OK\r\n')
    call('cat ' + quote(BIG), exact=files[BIG] + b'\r\n')
    call('write ' + quote(REPLACED) + ' BEFORE ' + 'old-content-' * 100, b'WRITE OK\r\n')
    call('write ' + quote(REPLACED) + ' ' + files[REPLACED].decode(), b'WRITE OK\r\n')
    call('touch ' + quote(EMPTY), b'WRITE OK\r\n')
    call('write ' + quote(REMOVED) + ' must-be-deleted ' + run_name, b'WRITE OK\r\n')
    call('rm ' + quote(REMOVED), b'RM OK\r\n')
    call('mkdir ' + quote(REMOVED_DIR), b'MKDIR OK\r\n')
    call('rm ' + quote(REMOVED_DIR), b'RM OK\r\n')
    for index in range(13):
        call('touch ' + quote(BOUNDARY + '/F%02d.TXT' % index), b'WRITE OK\r\n')
    for name in (CROSS, *COLLISIONS):
        call('write ' + quote(name) + ' ' + files[name].decode(), b'WRITE OK\r\n')
    call('cd ' + quote(DEEP), b'CD OK\r\n')
    call('pwd', exact=DEEP.encode() + b'\r\n')
    call('cd ..', b'CD OK\r\n')
    call('pwd', exact=SUB.encode() + b'\r\n')
    call('cat ' + quote(WORK + '/./' + SUB.rsplit('/', 1)[1] + '/../' + SUB.rsplit('/', 1)[1]
                        + '/' + BIG.rsplit('/', 1)[1]), exact=files[BIG] + b'\r\n')
    call('ls ' + quote(BOUNDARY), CROSS.rsplit('/', 1)[1].encode())
    call('ls /', WORK[1:].encode())
    return files, commands


def rejections(guest, disk):
    """Stop/FLUSH/hash before and after each rejected operation, not just at end."""
    commands, checks = [], []
    cases = [
        'write "/../escaped long name.txt" must-not-exist',
        'cd ' + quote(BIG),
        'mkdir ' + quote(BIG + '/child directory'),
        'cat ' + quote(BIG + '/../' + REPLACED.rsplit('/', 1)[1]),
        'write ' + quote(BIG + '/') + ' must-not-truncate',
        'rm ' + quote(WORK),
        'cat ' + quote(REMOVED),
        'touch "/missing parent/file.txt"',
        'cd ../../../..',
    ]
    for command in cases:
        commands.append(guest.shell('sync', b'SYNC OK\r\n'))
        before = settings.sha(disk)
        rejected = guest.shell(command, expect_error=True)
        commands.append(rejected)
        commands.append(guest.shell('sync', b'SYNC OK\r\n'))
        after = settings.sha(disk)
        settings.check(before == after, 'rejected path changed the entire guest data image: ' + command)
        checks.append(dict(command=command, before_sha256=before, after_sha256=after,
                           error_code=rejected['error_code'], entire_image_unchanged=True))
        commands.append(guest.shell('pwd', exact=SUB.encode() + b'\r\n'))
    return commands, checks


def readback(guest, files):
    commands = []
    for name, payload in files.items():
        commands.append(guest.shell('cat ' + quote(name), exact=payload + b'\r\n'))
    for directory in DIRECTORIES:
        commands.append(guest.shell('cd ' + quote(directory), b'CD OK\r\n'))
        commands.append(guest.shell('pwd', exact=directory.encode() + b'\r\n'))
    commands.append(guest.shell('ls ' + quote(BOUNDARY), CROSS.rsplit('/', 1)[1].encode()))
    commands.append(guest.shell('cat ' + quote(REMOVED), expect_error=True))
    commands.append(guest.shell('cd ' + quote(SUB), b'CD OK\r\n'))
    return commands


def raw_disk_check(disk, files):
    return oracle.inspect(disk, files=files, directories=DIRECTORIES,
                          absent=(REMOVED, REMOVED_DIR, '/escaped long name.txt', '/missing parent'),
                          require_crossing_lfn=True, require_multicluster_file=BIG, exact_namespace=True)


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp', type=Path)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        from tests import test_fat_paths_qemu
        suite = unittest.defaultTestLoader.loadTestsFromModule(test_fat_paths_qemu)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if args.reuse_esp is None:
        parser.error('--reuse-esp is required; this runner never builds an OS')
    esp = args.reuse_esp.resolve()
    state = ROOT / 'build/test/fat-paths/qemu' / ('run-' + uuid.uuid4().hex[:12])
    state.mkdir(parents=True)
    print('FAT paths actual state:', state, flush=True)
    result = dict(passed=False, backend='nvme', boot_attempts=0, actual_qemu_boots=0, boots=[],
                  full_os_build_executed=False, host_probe_payload_injection=False,
                  no_guest_memory_or_register_writes=True, no_qmp_storage_or_power_injection=True)
    names = ['tests/run_fat_paths_qemu.py', 'tests/fat_paths_oracle.py', 'tests/run_nvme_qemu.py',
             'tests/run_desktop_settings_qemu.py', 'tests/run_services_qemu.py', 'tests/run_acpi_qemu.py',
             'tools/build_usb.py', 'tools/make_fat32_disk.py', 'tools/elf_symbols.py', 'tools/build.py']
    inputs = {name: settings.sha(ROOT / name) for name in names}
    result['runner_inputs'] = inputs
    metadata, guest = {}, None
    try:
        metadata = verify_build(esp)
        result.update(build_inputs_verified=True,
                      build_inputs_sha256=settings.sha(esp.parent / 'build-inputs.json'))
        result['block_layout'] = nvme.check_layout(esp)
        result['kernel_memory_layout'] = nvme.check_kernel_memory_layout(esp)
        result['qemu_capability_probe'] = nvme.probe_qemu(state)
        disk = state / 'data.img'
        result['seed_geometry'] = create(disk, 64)
        seed = oracle.inspect(disk, files={'/README.TXT': SEED}, exact_namespace=True)
        storage.write_json(state / 'seed-disk.json', seed)
        result['seed_image_sha256'] = seed['image_sha256']
        first_hash = None
        files = None
        for boot in range(2):
            result['boot_attempts'] += 1
            guest = FatGuest(esp, disk, state / ('boot-' + str(boot + 1)), result['kernel_memory_layout'])
            if boot == 0:
                files, commands = populate(guest, state.name)
                rejected_commands, rejected = rejections(guest, disk)
                commands += rejected_commands
                result['rejected_operations'] = rejected
            else:
                commands = readback(guest, files)
            commands.append(guest.shell('sync', b'SYNC OK\r\n'))
            block = guest.block_snapshot()
            channels = guest.channel_snapshot()
            guest.close()
            result['boots'].append(dict(evidence=guest.evidence, commands=commands, block=block, channels=channels))
            guest = None
            raw = raw_disk_check(disk, files)
            storage.write_json(state / ('disk-after-boot-' + str(boot + 1) + '.json'), raw)
            if boot == 0:
                first_hash = raw['image_sha256']
                result['disk_sha256_after_first_sync'] = first_hash
            else:
                result['disk_sha256_after_second_sync'] = raw['image_sha256']
                settings.check(raw['image_sha256'] == first_hash,
                               'same image changed during second-boot read-only operations and FLUSH')
        result.update(passed=True, actual_utf8_uart_commands=True, actual_subdirectory_and_lfn_writes=True,
                      actual_multicluster_read_write=True, actual_lfn_group_crossed_directory_sector=True,
                      actual_guest_requested_nvme_flush=True, same_disk_reboot_verified=True,
                      original_readme_seed_preserved=True, independent_complete_fat_tree_verified=True)
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    finally:
        if guest is not None:
            try:
                guest.close()
            except Exception as error:
                result.update(passed=False, cleanup_error=f'{type(error).__name__}: {error}')
        records = [json.loads(path.read_text()) for path in state.glob('boot-*/guest.json')]
        result['actual_qemu_boots'] = sum(record.get('actual_qemu_executed') is True for record in records)
        result['all_started_guests_stopped'] = all(not record.get('actual_qemu_executed')
                                                  or record.get('qemu_stopped') is True for record in records)
        if any(record.get('cleanup_error') for record in records) or not result['all_started_guests_stopped']:
            result.update(passed=False, cleanup_error='started guest cleanup failed; see guest.json')
        if result['passed'] and result['actual_qemu_boots'] != 2:
            result.update(passed=False, error='successful run requires exactly two recorded actual boots')
        result['runner_inputs_unchanged'] = all(settings.sha(ROOT / name) == digest
                                               for name, digest in inputs.items())
        if not result['runner_inputs_unchanged']:
            result.update(passed=False, error='runner inputs changed during FAT verification')
        if metadata:
            try:
                verify_build(esp)
                settings.check(settings.sha(esp.parent / 'build-inputs.json') == result['build_inputs_sha256'],
                               'build metadata changed')
                settings.check(settings.sha(esp.parent / 'dong_layout.json')
                               == result['kernel_memory_layout']['layout_file_sha256'], 'kernel layout changed')
                result['build_source_and_artifacts_unchanged'] = True
            except Exception as error:
                result.update(passed=False, build_source_and_artifacts_unchanged=False,
                              unchanged_error=f'{type(error).__name__}: {error}')
        storage.write_json(state / 'result.json', result)
    print('FAT paths actual', 'PASS' if result['passed'] else 'FAIL', state, result.get('error', ''), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
