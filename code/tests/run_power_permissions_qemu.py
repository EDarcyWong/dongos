#!/usr/bin/env python3
"""Build isolated malicious service overlays and test real power syscall denials.

The supplied normal runtime7 build, production sources/kernel/ESP, and positive
power runner are immutable inputs. --selftest never compiles or starts a guest.
The normal CLI compiles only two new service ELFs under build/ and boots them
serially; invoke it only when the host's guest/build owner is ready.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import build as builder
from tools.build_usb import verify_build
from tools.elf_symbols import read_elf_symbols
from tools.make_fat32_disk import create
from tools.service_bundle import ELF, inspect, pack
from tests import run_acpi_qemu as acpi, run_services_qemu as storage
from tests.run_desktop_settings_qemu import Guest, ROOT, check, sha
from tests.run_power_qemu import RecordedQMP, validate_capabilities, validate_plan, check_layout, POWER_MODULE

SERVICES = ('shell', 'fs', 'block', 'compositor', 'input')
MODULE = 'power_permission_probe'
PROTOCOL, INVALID_HANDLE, DENIED, INVALID_ACTION = 0x050b0002, 0x04010002, 0x04010003, 0x08030002
FOREIGN_GUESS = 261
RUNTIME_FILES = ('kernel.elf', 'kernel.bin', 'dong_layout.json')


def inventory_tree(folder):
    folder = Path(folder)
    check(folder.is_dir() and not folder.is_symlink(), 'ordinary baseline ESP required')
    result = {}
    for path in sorted(folder.rglob('*')):
        check(not path.is_symlink() and not (getattr(path.lstat(), 'st_file_attributes', 0) & 0x400), 'overlay rejects reparse/symlink entries')
        if path.is_file():
            result[path.relative_to(folder).as_posix()] = sha(path)
    return result


def case_definitions(role):
    if role == 'compositor':
        return [dict(name=name + '-' + str(action), source=source, action=action, error=PROTOCOL)
                for name, source in (('zero', '0'), ('own-device', '(*boot).console'),
                    ('own-endpoint', '(*boot).filesystem'), ('foreign-shell-token', str(FOREIGN_GUESS)))
                for action in (1, 2)]
    check(role == 'shell', 'unsupported malicious service role')
    values = [dict(name=name + '-' + str(action), source=source, action=action, error=error)
              for name, source, error in (('zero', '0', INVALID_HANDLE), ('console', '(*boot).console', DENIED),
                  ('filesystem', '(*boot).filesystem', DENIED), ('channel', '(*boot).channel', DENIED),
                  ('stale-generation', '((*boot).reserved3+256)', INVALID_HANDLE))
              for action in (1, 2)]
    return values + [dict(name='invalid-action-' + str(action), source='(*boot).reserved3', action=action, error=INVALID_ACTION)
                     for action in (0, 3, (1 << 64) - 1)]


def expected_cases(role, boots):
    check(len(boots) == 5 and all(len(b) == 128 for b in boots), 'five exact actual Boot records required')
    records = [struct.unpack('<16Q', b) for b in boots]
    own = records[SERVICES.index(role)]
    if role == 'compositor':
        check(records[0][15] == FOREIGN_GUESS, 'forged token is not equal to this actual shell power token')
        tokens = [0, own[10], own[3], FOREIGN_GUESS]
        return [(index, token, action, PROTOCOL) for index, (token, action) in
                enumerate((t, a) for t in tokens for a in (1, 2))]
    check(role == 'shell' and own[15] >> 8 == 1, 'initial shell power generation differs')
    tokens = [(0, INVALID_HANDLE), (own[10], DENIED), (own[3], DENIED), (own[5], DENIED), (own[15] + 256, INVALID_HANDLE)]
    values = [(index, token, action, error) for index, (token, action, error) in
              enumerate((t, a, e) for t, e in tokens for a in (1, 2))]
    return values + [(10 + index, own[15], action, INVALID_ACTION) for index, action in enumerate((0, 3, (1 << 64) - 1))]


def probe_source(role):
    cases = case_definitions(role)
    pid = SERVICES.index(role) + 1
    calls = '\n'.join('        probe(%d,%s,%d,%d);' % (index, case['source'], case['action'], case['error'])
                      for index, case in enumerate(cases))
    # Shell waits for one real FS READY call/reply before its first invalid cap.
    # Its probe loop then remains CURRENT0 until all calls finish, so an IPC
    # Protocol refusal cannot hide the expected specific handle/action errors.
    ready = '''        var request=sys.EMPTY_MESSAGE;var response=sys.EMPTY_MESSAGE;
        request.words[0]=1;
        let status=sys.call((*boot).filesystem,&request,&response);
        if status!=0 || response.words[0]!=0 {FAILURES+=1;}
''' if role == 'shell' else ''
    return '''// Isolated negative fixture only; generated under build/, never production.
module power_permission_probe;
import lib.sys as sys;
pub struct Result {pub index:u64,pub token:u64,pub action:u64,pub status:u64}
const EMPTY:Result=Result {index:0,token:0,action:0,status:0};
pub var RESULTS:[%d]Result=[EMPTY;%d];
pub var COMPLETED:u64=0;
pub var FAILURES:u64=0;
pub var BOOT_PROCESS:u64=0;
fn probe(index:usize,token:u64,action:u64,expected:u64)void {
    unsafe {
        let actual=sys.svc_call(0x78,token,action,0,0,0,0);
        RESULTS[index]=Result {index:index as u64,token:token,action:action,status:actual};
        if actual!=expected {FAILURES+=1;}
        compiler_fence();COMPLETED+=1;
    }return;
}
export("service_main") fn main()u64 {
    unsafe {
        let boot=sys.boot();
        if boot==null || (*boot).version!=1 || (*boot).process!=%d || (*boot).service_count!=5 {
            let failed=sys.log("DONGOS_POWER_PERMISSION_FAIL\\r\\n");
            loop {let ignored=sys.yield_now();}
        }
        BOOT_PROCESS=(*boot).process;
%s        let begin=sys.log("DONGOS_POWER_DENY_BEGIN_%s\\r\\n");
%s
        compiler_fence();
        if FAILURES==0 && COMPLETED==%d {
            let done=sys.log("DONGOS_POWER_DENIED_%s\\r\\n");
        }else {let failed=sys.log("DONGOS_POWER_PERMISSION_FAIL\\r\\n");}
        loop {let ignored=sys.yield_now();}
    }
}
''' % (len(cases), len(cases), pid, ready, role.upper(), calls, len(cases), role.upper())


def replace_one_elf(raw, role, replacement):
    check(role in ('shell', 'compositor') and replacement, 'exact permitted replacement required')
    original = inspect(raw)
    matches = [entry for entry in original['entries'] if entry['name'] == role and entry['kind'] == ELF]
    check(len(matches) == 1, 'unique original role ELF absent')
    items = [(entry['name'], entry['kind'], replacement if entry['name'] == role else
              raw[entry['offset']:entry['offset'] + entry['length']]) for entry in original['entries']]
    changed = pack(items)
    verify_bundle_delta(raw, changed, role, replacement)
    return changed


def verify_bundle_delta(original_raw, overlay_raw, role, replacement):
    original, overlay = inspect(original_raw), inspect(overlay_raw)
    before = {entry['name']: entry for entry in original['entries']}
    after = {entry['name']: entry for entry in overlay['entries']}
    check(before.keys() == after.keys(), 'overlay added/removed bundle entries')
    changed = []
    for name, entry in before.items():
        new = after[name]
        check(entry['kind'] == new['kind'], 'overlay changed bundle kind')
        old_bytes = original_raw[entry['offset']:entry['offset'] + entry['length']]
        new_bytes = overlay_raw[new['offset']:new['offset'] + new['length']]
        if old_bytes != new_bytes:
            changed.append(name)
        if name == role:
            check(new['kind'] == ELF and new_bytes == replacement, 'replacement ELF not the actual bundle payload')
        else:
            check(new_bytes == old_bytes, 'unapproved bundle payload changed: ' + name)
    check(changed == [role], 'exactly the designated ELF must change')
    return dict(original=original, overlay=overlay, changed_entries=changed)


def build_overlay(base_esp, output, role):
    # Called only by the explicit CLI; --selftest never enters this function.
    from tools import user_services
    check(not output.exists() and output.resolve().is_relative_to((ROOT / 'build').resolve()), 'fresh build/ overlay directory required')
    metadata = verify_build(base_esp)
    base = base_esp.parent
    original_tree = inventory_tree(base_esp)
    original_raw = (base_esp / 'SERVICES.BIN').read_bytes()
    original = inspect(original_raw)
    entries = {entry['name']: entry for entry in original['entries']}
    for name in SERVICES:
        entry = entries[name]
        check(entry['kind'] == ELF and (base / 'services' / name / 'program.elf').read_bytes() ==
              original_raw[entry['offset']:entry['offset'] + entry['length']], 'baseline embedded/sidecar ELF differs: ' + name)
    output.mkdir(parents=True)
    shutil.copytree(base_esp, output / 'esp')
    for name in RUNTIME_FILES:
        shutil.copyfile(base / name, output / name)
    shutil.copyfile(base / 'build-inputs.json', output / 'base-build-inputs.json')
    for name in SERVICES:
        if name != role:
            target = output / 'services' / name
            target.mkdir(parents=True)
            shutil.copyfile(base / 'services' / name / 'program.elf', target / 'program.elf')
    source = output / 'malicious' / (MODULE + '.dg')
    source.parent.mkdir()
    source.write_text(probe_source(role), encoding='utf-8')
    # The ordinary builder intentionally accepts only production source roots.
    # Extend its compile invocation for this one host call, then restore the
    # module attribute; neither the tool source nor production roots are edited.
    original_compile = user_services.compile_file
    def isolated_compile(entry, **options):
        check(Path(entry).resolve() == source.resolve(), 'unexpected overlay compiler entry')
        options['roots'] = [source.parent, *options['roots']]
        return original_compile(entry, **options)
    user_services.compile_file = isolated_compile
    try:
        executable = user_services.build_service(source, output / 'services' / role)
    finally:
        user_services.compile_file = original_compile
    replacement = executable.read_bytes()
    overlay_raw = replace_one_elf(original_raw, role, replacement)
    (output / 'esp/SERVICES.BIN').write_bytes(overlay_raw)
    manifest = dict(version=1, kind='negative-permission-service-overlay', changed_service=role,
        base_esp=str(base_esp), base_build_inputs_sha256=sha(base / 'build-inputs.json'),
        base_metadata_copy='base-build-inputs.json', base_source_sha256=metadata['source_sha256'],
        base_artifacts=metadata['artifacts'], original_esp_files=original_tree,
        original_runtime_files={name: sha(base / name) for name in RUNTIME_FILES},
        original_service_elf={name: sha(base / 'services' / name / 'program.elf') for name in SERVICES},
        original_bundle=original, overlay_bundle=inspect(overlay_raw),
        changed_entries=[role], source=source.relative_to(output).as_posix(), source_sha256=sha(source),
        malicious_elf=executable.relative_to(output).as_posix(), malicious_elf_sha256=sha(executable),
        overlay_files={p.relative_to(output).as_posix(): sha(p) for p in sorted(output.rglob('*')) if p.is_file()},
        production_kernel_changed=False, production_source_fingerprints_rewritten=False,
        case_count=len(case_definitions(role)), expected_error_contract='exact errno, never nonzero-only')
    storage.write_json(output / 'permission-overlay.json', manifest)
    verify_overlay(base_esp, output)
    return output / 'esp', manifest


def verify_overlay(base_esp, output):
    metadata = verify_build(base_esp)
    manifest = json.loads((output / 'permission-overlay.json').read_text(encoding='utf-8'))
    role = manifest['changed_service']
    check(manifest['version'] == 1 and manifest['kind'] == 'negative-permission-service-overlay' and role in ('shell', 'compositor')
          and manifest['changed_entries'] == [role] and Path(manifest['base_esp']).resolve() == base_esp.resolve()
          and manifest['production_kernel_changed'] is False and manifest['production_source_fingerprints_rewritten'] is False,
          'overlay identity/allowlist differs')
    check(manifest['base_source_sha256'] == metadata['source_sha256'] and manifest['base_artifacts'] == metadata['artifacts'], 'base source/artifact fingerprints were rewritten')
    check(sha(base_esp.parent / 'build-inputs.json') == manifest['base_build_inputs_sha256']
          == sha(output / 'base-build-inputs.json'), 'original build manifest was changed')
    check(inventory_tree(base_esp) == manifest['original_esp_files'], 'original normal ESP changed')
    tree = inventory_tree(output / 'esp')
    check(tree.keys() == manifest['original_esp_files'].keys(), 'overlay ESP added/removed files')
    for name, value in tree.items():
        if name != 'SERVICES.BIN':
            check(value == manifest['original_esp_files'][name], 'kernel/EFI/other ESP file changed')
    for name, value in manifest['original_runtime_files'].items():
        check(sha(base_esp.parent / name) == value == sha(output / name), 'kernel/ELF/layout is not byte-identical')
    for name, value in manifest['overlay_files'].items():
        check(sha(output / name) == value, 'isolated overlay output changed: ' + name)
    replacement = (output / manifest['malicious_elf']).read_bytes()
    check(manifest['malicious_elf'] == 'services/' + role + '/program.elf'
          and manifest['source'] == 'malicious/' + MODULE + '.dg'
          and manifest['case_count'] == len(case_definitions(role)), 'negative fixture path/count contract differs')
    source = output / manifest['source']
    check(sha(source) == manifest['source_sha256'] and source.read_text(encoding='utf-8') == probe_source(role),
          'negative source is not the exact generated syscall probe')
    check(hashlib.sha256(replacement).hexdigest() == manifest['malicious_elf_sha256'], 'malicious ELF changed')
    delta = verify_bundle_delta((base_esp / 'SERVICES.BIN').read_bytes(), (output / 'esp/SERVICES.BIN').read_bytes(), role, replacement)
    check(delta['original'] == manifest['original_bundle'] and delta['overlay'] == manifest['overlay_bundle'], 'bundle inventories changed')
    for name, value in manifest['original_service_elf'].items():
        check(sha(base_esp.parent / 'services' / name / 'program.elf') == value, 'baseline service sidecar changed')
        if name != role:
            check(sha(output / 'services' / name / 'program.elf') == value, 'another service sidecar changed')
    return manifest


def validate_results(role, boots, raw, completed, failures, boot_process, info):
    expected = expected_cases(role, boots)
    check(len(raw) == len(expected) * 32, 'actual RESULTS size differs')
    actual = [struct.unpack_from('<4Q', raw, index * 32) for index in range(len(expected))]
    check(actual == expected, 'actual power syscall token/action/errno differs from independent exact oracle')
    check(completed == len(expected) and failures == 0 and boot_process == SERVICES.index(role) + 1, 'probe completion/process identity differs')
    check(len(info) == 20 and info[0] == 1 and info[1] == 5 and info[5] == len(expected) and info[6] == 0
          and info[3] == info[4] and info[2] >= len(expected) and info[9] == 0,
          'actual kernel errors/call-reply/syscall counts do not prove exactly the expected denials')
    return [dict(name=case['name'], index=a[0], token=a[1], action=a[2], actual_errno=a[3], expected_errno=e[3])
            for case, a, e in zip(case_definitions(role), actual, expected)]


def assert_no_power(raw, events):
    check(bytes(raw).count(b'DONGOS_P1_START') == 1, 'negative guest reset or did not enter its single kernel boot')
    for marker in (b'PANIC', b'DONGOS_P1_KERNEL_FAIL', b'DONGOS_POWER_PERMISSION_FAIL',
                   b'DONGOS_POWER_RESET_REQUEST', b'DONGOS_POWER_S5_REQUEST', b'DONGOS_POWER_SYNCED'):
        check(marker not in raw, 'unexpected power/failure marker in negative guest: ' + repr(marker))
    check(not any(item['message'].get('event') in ('RESET', 'SHUTDOWN') and
                  item['message'].get('data', {}).get('guest') is True for item in events), 'unauthorized guest generated an actual RESET/SHUTDOWN')


def kernel_page_entry(root, va, read_page):
    """Non-leaf U bits may be set; effective USER is the AND of all levels."""
    check(0 < root < (1 << 48) - 128 * 4096 and root % 4096 == 0, 'invalid kernel table pool')
    current, effective_user = root, True
    for shift in (39, 30, 21, 12):
        check(root <= current < root + 128 * 4096, 'kernel text walk escaped its table pool')
        raw = read_page(current)
        check(len(raw) == 4096, 'incomplete kernel table page')
        entry = struct.unpack_from('<Q', raw, ((va >> shift) & 511) * 8)[0]
        check(entry & 1, 'kernel mapping absent')
        effective_user = effective_user and bool(entry & 4)
        if shift == 12:
            check(not effective_user and not entry & 4, 'kernel leaf/effective mapping became user-accessible')
            return entry
        check(not entry & 128, 'unexpected huge kernel code mapping')
        current = entry & storage.MASK


def validate_kernel_code_leaf(entry, physical):
    # Keep exact supervisor/RO/RX/WB/physical identity; only hardware A/D vary.
    check(entry & ~0x60 == physical | 1, 'actual kernel code is not exact supervisor RO/RX/WB')


def collect_actual_startups(state):
    """Count retained actual launches/entries even if __init__ never returned."""
    reports, errors = [], []
    for role in ('compositor', 'shell'):
        folder = Path(state) / (role + '-guest')
        report_path, serial_path = folder / 'guest.json', folder / 'serial.log'
        if not report_path.exists() and not serial_path.exists():
            continue
        report, serial = {}, b''
        try:
            if report_path.exists(): report = json.loads(report_path.read_text(encoding='utf-8'))
            if serial_path.exists(): serial = serial_path.read_bytes()
        except (OSError, ValueError) as error:
            errors.append(dict(role=role, error=type(error).__name__ + ': ' + str(error)))
        boots = serial.count(b'DONGOS_P1_START')
        launched = report.get('actual_qemu_executed') is True or boots > 0
        reports.append(dict(role=role, guest_report=str(report_path) if report_path.exists() else None,
            actual_qemu_executed=launched, report_actual_qemu_executed=report.get('actual_qemu_executed'),
            constructor_completed=report.get('constructor_completed'), constructor_error=report.get('constructor_error'),
            serial_file=str(serial_path) if serial_path.exists() else None,
            serial_bytes=len(serial), serial_sha256=hashlib.sha256(serial).hexdigest(), p1_start_markers=boots))
    return dict(actual_qemu_attempts=sum(report['actual_qemu_executed'] for report in reports),
                actual_qemu_boots=sum(report['p1_start_markers'] for report in reports),
                actual_startup_reports=reports, actual_startup_report_errors=errors)


class PermissionGuest(Guest):
    """Read-only inspection helpers, with independent negative startup criteria."""
    def __init__(self, esp, disk, state, role):
        self.esp, self.disk, self.state, self.role = esp, disk, state, role
        state.mkdir(parents=True)
        self.raw, self.chunks, self.tables = bytearray(), [], {}
        self.process = self.qmp = self.uart = None
        self.stopped = False
        self.evidence = dict(actual_qemu_executed=False, constructor_completed=False, role=role, negative_fixture=True, disk=str(disk))
        up, qp = storage.free_port(), storage.free_port()
        command = builder.qemu_command(esp, state / 'guest', test=True)
        i = command.index('isa-debug-exit,iobase=0xf4,iosize=0x04'); del command[i-1:i+1]
        check(command.count('-no-reboot') == 1, 'unexpected baseline reset policy')
        command.remove('-no-reboot')
        command += ['-no-shutdown']
        command[command.index('-serial') + 1] = f'tcp:127.0.0.1:{up},server=on,wait=off'
        command += ['-cpu', 'max,+smep,+smap,+umip', '-S', '-qmp', f'tcp:127.0.0.1:{qp},server=on,wait=off',
                    '-drive', 'if=none,id=data,format=raw,cache=writeback,file=' + disk.resolve().as_posix().replace(',', ',,'),
                    '-device', 'virtio-blk-pci,drive=data,disable-legacy=on', '-device', 'virtio-tablet-pci']
        self.evidence['command'] = command
        self.stderr = (state / 'stderr.log').open('wb')
        try:
            self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=self.stderr)
            self.evidence['actual_qemu_executed'] = True
            self.qmp = RecordedQMP(qp, self.process, state / 'qmp-wire.jsonl')
            self.uart = socket.create_connection(('127.0.0.1', up)); self.uart.settimeout(.2)
            def read_uart():
                with (state / 'serial.log').open('wb') as stream:
                    while self.process.poll() is None:
                        try: part = self.uart.recv(4096)
                        except socket.timeout: continue
                        except OSError: break
                        if not part: break
                        self.raw.extend(part); stream.write(part); stream.flush()
            self.reader = threading.Thread(target=read_uart, daemon=True); self.reader.start()
            self.qmp.request('cont')
            for marker in (b'DONGOS_POWER_DENIED_' + role.upper().encode(), b'DONGOS_BLK_READY', b'DONGOS_FS_READY', b'DONGOS_INPUT_VIRTIO_TABLET_READY'):
                self.wait_negative(marker)
            if role == 'compositor': self.wait_negative(b'DONGOS_SHELL_READY')
            self.pause()
            self.symbols = acpi.validation_symbols(esp.parent / 'kernel.elf')
            memory = {k.decode(): int(v, 16) for k, v in re.findall(rb'^memory_([a-z_]+)=0x([0-9a-f]{16})\r?$', self.raw, re.MULTILINE)}
            self.kernel_root = memory['root_physical']
            self.boot = struct.unpack('<20Q', self.physical(memory['runtime_boot_info'] - acpi.HHDM, 160, 'negative BootInfo'))
            self.processes = self.kernel(self.ksym('user.memory', 'PROCESSES'), 5 * 1288, 'negative five processes')
            self.roots = [struct.unpack_from('<Q', self.processes, pid * 1288 + 8)[0] for pid in range(5)]
            self.validate_private_pools()
            check(all(struct.unpack_from('<Q', self.processes, pid * 1288)[0] == 1 for pid in range(5)), 'negative private processes missing')
            self.verify_elf()
            self.verify_kernel_text()
            self.evidence['constructor_completed'] = True
        except BaseException as error:
            self.evidence['constructor_error'] = type(error).__name__ + ': ' + str(error)
            self.close()
            raise

    def wait_negative(self, marker, timeout=90):
        deadline = time.monotonic() + timeout
        while marker not in self.raw:
            check(self.process.poll() is None, 'negative guest terminated')
            if b'DONGOS_P1_START' in self.raw: assert_no_power(self.raw, self.qmp.events)
            check(time.monotonic() < deadline, 'negative marker missing: ' + repr(marker))
            time.sleep(.02)

    def kernel_pte(self, va):
        def page(physical):
            if physical not in self.tables: self.tables[physical] = self.physical(physical, 4096, 'actual kernel table')
            return self.tables[physical]
        return kernel_page_entry(self.kernel_root, va, page)

    def verify_kernel_text(self):
        raw = (self.esp.parent / 'kernel.elf').read_bytes()
        offset = struct.unpack_from('<Q', raw, 32)[0]
        stride, count = struct.unpack_from('<HH', raw, 54)
        segments = []
        for index in range(count):
            kind, flags, off, va, _, size, memory, _ = struct.unpack_from('<IIQQQQQQ', raw, offset + index * stride)
            if kind != 1 or not flags & 1: continue
            check(not flags & 2 and size > 0, 'kernel executable segment invalid')
            for address in range(va & ~4095, (va + memory + 4095) & ~4095, 4096):
                entry = self.kernel_pte(address)
                expected = self.boot[15] + address - storage.KERNEL
                validate_kernel_code_leaf(entry, expected)
            actual = self.kernel(va, size, 'all actual production kernel executable bytes')
            check(actual == raw[off:off + size], 'actual kernel text differs from original production ELF')
            segments.append(dict(virtual=va, bytes=size, sha256=hashlib.sha256(actual).hexdigest()))
        check(segments, 'no actual kernel executable segment verified')
        self.evidence['production_kernel_executable_segments'] = segments

    def snapshot(self, name):
        self.pause()
        prepared = self.kernel(self.ksym(POWER_MODULE, 'PREPARED'), 184, name + ' Prepared')
        plan = validate_plan(prepared)
        globals_ = {field: self.kval(POWER_MODULE, field) for field in ('CAPTURE_ERROR', 'REQUESTS', 'LAST_ACTION')}
        check(globals_ == dict(CAPTURE_ERROR=0, REQUESTS=0, LAST_ACTION=0), 'unauthorized request reached power state')
        identity = {field: self.kval('boot.acpi_startup', field) for field in ('PREPARED_INFO', 'PREPARED_MAP', 'PREPARED_BYTES', 'PREPARED_STRIDE')}
        check(all(value == 0 for value in identity.values()), 'retired firmware reader identity was retained')
        boots = [self.user(pid, 0x70000000, 128, name + ' actual Boot') for pid in range(5)]
        check(all(self.pte(root, 0x70000000) & 0x800000000000001f == 0x8000000000000005 for root in self.roots), 'actual Boot capability page is not RO/NX')
        states = [self.kernel(self.ksym('user.services', 'STATES') + pid * 1336, 1336, name + ' actual capability table') for pid in range(5)]
        caps = validate_capabilities(boots, states)
        info = struct.unpack('<20Q', self.kernel(self.ksym('user.services', 'INFO'), 160, name + ' actual kernel errors/calls'))
        pid = SERVICES.index(self.role)
        bias = struct.unpack_from('<Q', self.processes, pid * 1288 + 224)[0]
        symbols = read_elf_symbols(self.esp.parent / 'services' / self.role / 'program.elf')
        def variable(field, size):
            return self.user(pid, bias + symbols[storage.symbol(MODULE, field)], size, name + ' malicious ' + field)
        completed, failures, process = [struct.unpack('<Q', variable(field, 8))[0] for field in ('COMPLETED', 'FAILURES', 'BOOT_PROCESS')]
        data = variable('RESULTS', len(case_definitions(self.role)) * 32)
        cases = validate_results(self.role, boots, data, completed, failures, process, info)
        assert_no_power(self.raw, self.qmp.events)
        for marker in (b'DONGOS_POWER_DENY_BEGIN_' + self.role.upper().encode(), b'DONGOS_POWER_DENIED_' + self.role.upper().encode()):
            check(self.raw.count(marker) == 1, 'negative application marker missing/duplicated')
        value = dict(name=name, role=self.role, plan=plan, power_globals=globals_, retired_reader_identity=identity,
                     capabilities=caps, service_report=list(info), actual_cases=cases,
                     completed=completed, failures=failures, actual_boot_process=process,
                     qmp_status=self.qmp.request('query-status'), exact_errno_verified=True)
        storage.write_json(self.state / (name + '-negative.json'), value)
        self.evidence.setdefault('snapshots', []).append(value)
        return value

    def observe(self, seconds=2):
        self.resume()
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            assert_no_power(self.raw, self.qmp.events)
            check(self.process.poll() is None, 'negative guest exited in observation interval')
            time.sleep(.02)
        status = self.qmp.request('query-status')
        check(status.get('running') is True and status.get('status') == 'running', 'negative guest did not remain running')
        self.pause()
        return dict(seconds=seconds, status_before_pause=status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp', type=Path)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(PermissionRunnerTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if args.reuse_esp is None: parser.error('--reuse-esp is required; no full build is performed')
    esp = args.reuse_esp.resolve()
    state = ROOT / 'build/test/p8-power/permissions' / ('run-' + uuid.uuid4().hex[:12])
    state.mkdir(parents=True)
    result = dict(passed=False, actual_qemu_attempts=0, actual_qemu_boots=0, permission_negative_accepted=False, cases=[],
                  production_kernel_changed=False, production_source_fingerprints_rewritten=False,
                  exact_io_trace_accepted=False)
    inputs = {str(ROOT / name): sha(ROOT / name) for name in ('tests/run_power_permissions_qemu.py',
        'tests/run_power_qemu.py', 'tests/run_desktop_settings_qemu.py', 'tests/run_acpi_qemu.py',
        'tools/user_services.py', 'tools/service_bundle.py', 'tools/build_usb.py')}
    result['runner_inputs'] = inputs
    guest, base = None, None
    try:
        base = verify_build(esp)
        result['layout'] = check_layout(esp.parent)
        original_tree = inventory_tree(esp)
        result['original_esp_files'] = original_tree
        for role in ('compositor', 'shell'):
            overlay = state / (role + '-overlay')
            overlay_esp, manifest = build_overlay(esp, overlay, role)
            disk = state / (role + '-fresh-data.img'); create(disk, 64)
            disk_before = sha(disk)
            guest = PermissionGuest(overlay_esp, disk, state / (role + '-guest'), role)
            # Wait at most a few normal loops for unrelated production IPC to
            # quiesce; never accept Protocol in place of an exact cap errno.
            deadline = time.monotonic() + 8
            while True:
                guest.pause()
                info = struct.unpack('<20Q', guest.kernel(guest.ksym('user.services', 'INFO'), 160, 'negative IPC quiescence'))
                if info[3] == info[4]: break
                check(time.monotonic() < deadline, 'normal negative-fixture IPC failed to quiesce')
                guest.resume(); time.sleep(.05)
            first = guest.snapshot('denied')
            observation = guest.observe(2)
            second = guest.snapshot('after-observation')
            check(first['plan']['sha256'] == second['plan']['sha256'] and first['actual_cases'] == second['actual_cases'], 'negative results/plan changed')
            assert_no_power(guest.raw, guest.qmp.events)
            guest.close(); guest = None
            check(sha(disk) == disk_before, 'negative application changed disk bytes')
            verify_overlay(esp, overlay)
            result['cases'].append(dict(role=role, case_count=manifest['case_count'], overlay_manifest=str(overlay / 'permission-overlay.json'),
                overlay_manifest_sha256=sha(overlay / 'permission-overlay.json'), actual_errno_results=second['actual_cases'],
                observation=observation, disk_unchanged=True, disk_sha256=disk_before))
        verify_build(esp)
        check(inventory_tree(esp) == original_tree, 'original normal ESP changed during negative tests')
        result.update(passed=True, permission_negative_accepted=True, actual_denied_syscalls=21,
                      actual_five_private_elf_rx_bytes_verified=True, actual_original_kernel_text_verified=True)
    except BaseException as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        if guest is not None: guest.close()
        result.update(collect_actual_startups(state))
        if result['actual_startup_report_errors']:
            result.update(passed=False, permission_negative_accepted=False, startup_evidence_error='retained guest/serial evidence could not be read')
        if result['passed'] and (result['actual_qemu_attempts'] != 2 or result['actual_qemu_boots'] != 2):
            result.update(passed=False, permission_negative_accepted=False, startup_evidence_error='expected exactly two actual launches/kernel entries')
        result['source_unchanged'] = (base is not None and all(sha(p) == v for p, v in inputs.items())
            and all(sha(ROOT / p) == v for p, v in base['source_sha256'].items()))
        if not result['source_unchanged']: result.update(passed=False, permission_negative_accepted=False, identity_error='source/runner identity changed')
        storage.write_json(state / 'result.json', result)
    print('P8 actual power permissions', 'PASS' if result['passed'] else 'FAIL', state, result.get('error', ''), flush=True)
    return 0 if result['passed'] else 1


class PermissionRunnerTests(unittest.TestCase):
    @staticmethod
    def boots():
        records = []
        for pid in range(5):
            value = [0] * 16; value[0] = 1; value[1] = pid + 1; value[3] = 259; value[5] = 258
            value[10] = 260; value[11] = 5; value[15] = FOREIGN_GUESS if pid == 0 else 0
            records.append(struct.pack('<16Q', *value))
        return records

    def test_kernel_walk_uses_effective_user_and_keeps_exact_code_leaf(self):
        root, virtual, physical = 0x100000, storage.KERNEL, 0x200000
        addresses = [root + index * 4096 for index in range(4)]
        def tables():
            values = {address: bytearray(4096) for address in addresses}
            for index, shift in enumerate((39, 30, 21, 12)):
                entry = addresses[index + 1] | 7 if index < 3 else physical | 1
                struct.pack_into('<Q', values[addresses[index]], ((virtual >> shift) & 511) * 8, entry)
            return values
        def write(values, index, entry):
            shift = (39, 30, 21, 12)[index]
            struct.pack_into('<Q', values[addresses[index]], ((virtual >> shift) & 511) * 8, entry)
        values = tables()
        # Actual unified non-leaf policy: U/W ancestors, supervisor RO/RX leaf.
        entry = kernel_page_entry(root, virtual, values.__getitem__)
        self.assertEqual(physical | 1, entry)
        validate_kernel_code_leaf(entry, physical)
        validate_kernel_code_leaf(entry | 0x60, physical)
        for index in range(4):
            bad = tables(); write(bad, index, 0)
            with self.assertRaises(ValueError): kernel_page_entry(root, virtual, bad.__getitem__)
        for index in range(3):
            bad = tables(); write(bad, index, addresses[index + 1] | 7 | 128)
            with self.assertRaises(ValueError): kernel_page_entry(root, virtual, bad.__getitem__)
        for ancestor_supervisor in (False, True):
            bad = tables(); write(bad, 3, physical | 7)
            if ancestor_supervisor: write(bad, 0, addresses[1] | 3)
            with self.assertRaises(ValueError): kernel_page_entry(root, virtual, bad.__getitem__)
        bad = tables(); write(bad, 0, root + 128 * 4096 | 7)
        with self.assertRaises(ValueError): kernel_page_entry(root, virtual, bad.__getitem__)
        with self.assertRaises(ValueError): kernel_page_entry(root, virtual, lambda address: bytes(4095))
        for flags in (2, 4, 8, 16, 128, 1 << 63):
            with self.assertRaises(ValueError): validate_kernel_code_leaf(physical | 1 | flags, physical)
        with self.assertRaises(ValueError): validate_kernel_code_leaf((physical + 4096) | 1, physical)

    def test_constructor_failure_still_records_actual_launch_and_boot(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            failed = state / 'compositor-guest'; failed.mkdir()
            storage.write_json(failed / 'guest.json', dict(actual_qemu_executed=True, constructor_completed=False,
                constructor_error='ValueError: physical verification failed'))
            (failed / 'serial.log').write_bytes(b'DONGOS_P1_START\r\nDONGOS_POWER_DENIED_COMPOSITOR\r\n')
            counts = collect_actual_startups(state)
            self.assertEqual((1, 1), (counts['actual_qemu_attempts'], counts['actual_qemu_boots']))
            self.assertFalse(counts['actual_startup_reports'][0]['constructor_completed'])
            self.assertIn('physical verification failed', counts['actual_startup_reports'][0]['constructor_error'])
            missing = state / 'shell-guest'; missing.mkdir()
            storage.write_json(missing / 'guest.json', dict(actual_qemu_executed=False, constructor_completed=False))
            counts = collect_actual_startups(state)
            self.assertEqual((1, 1), (counts['actual_qemu_attempts'], counts['actual_qemu_boots']))
            (missing / 'serial.log').write_bytes(b'DONGOS_P1_START\r\nDONGOS_P1_START\r\n')
            counts = collect_actual_startups(state)
            self.assertEqual((2, 3), (counts['actual_qemu_attempts'], counts['actual_qemu_boots']))

    def test_probe_counts_exact_error_contract_and_generated_actual_calls(self):
        from lang.dongc.frontend import Parser, lex
        boots = self.boots()
        for role, count in (('compositor', 8), ('shell', 13)):
            cases = expected_cases(role, boots)
            self.assertEqual(count, len(cases))
            source = probe_source(role)
            # Grammar-only host model; no source-root resolution, semantic
            # compilation, assembler, linker, build_service, or guest run.
            self.assertEqual(MODULE, Parser(lex(source)).parse().name)
            self.assertIn('sys.svc_call(0x78,token,action,0,0,0,0)', source)
            self.assertEqual(count, source.count('        probe('))
            self.assertIn('if actual!=expected', source)
            self.assertNotIn('DONGOS_P7_DESKTOP_READY', source)
            raw = b''.join(struct.pack('<4Q', *case) for case in cases)
            info = [0] * 20; info[0] = 1; info[1] = 5; info[2] = count + 10; info[3] = info[4] = 1; info[5] = count
            self.assertEqual(count, len(validate_results(role, boots, raw, count, 0, SERVICES.index(role) + 1, info)))
            # A fake marker/results publisher which never issued the denials
            # leaves kernel INFO.errors0 and must fail the independent oracle.
            fake = list(info); fake[5] = 0
            with self.assertRaises(ValueError): validate_results(role, boots, raw, count, 0, SERVICES.index(role) + 1, fake)
            for field, value in ((0, 99), (1, 1), (2, 7), (3, 0), (3, 0x1234)):
                bad = bytearray(raw); struct.pack_into('<Q', bad, field * 8, value)
                with self.assertRaises(ValueError): validate_results(role, boots, bad, count, 0, SERVICES.index(role) + 1, info)

    def test_foreign_guess_is_bound_to_actual_shell_capability(self):
        boots = self.boots(); bad = list(boots); value = bytearray(bad[0]); struct.pack_into('<Q', value, 120, 262); bad[0] = value
        with self.assertRaises(ValueError): expected_cases('compositor', bad)

    def test_only_exact_one_bundle_elf_may_change(self):
        items = [(name, ELF, b'original-elf-' + name.encode()) for name in SERVICES] + [('font16', 2, b'font'), ('desktop-config', 2, b'dpi')]
        original = pack(items)
        for role in ('compositor', 'shell'):
            overlay = replace_one_elf(original, role, b'malicious-' + role.encode())
            self.assertEqual([role], verify_bundle_delta(original, overlay, role, b'malicious-' + role.encode())['changed_entries'])
            bad = pack([(n, k, b'bad' if n == 'font16' else b'malicious-' + role.encode() if n == role else b) for n, k, b in items])
            with self.assertRaises(ValueError): verify_bundle_delta(original, bad, role, b'malicious-' + role.encode())
            with self.assertRaises(ValueError): verify_bundle_delta(original, overlay, role, b'wrong-elf')
            with self.assertRaises(ValueError): replace_one_elf(original, role, b'original-elf-' + role.encode())

    def test_negative_guest_requires_single_boot_and_no_actual_power(self):
        raw = b'DONGOS_P1_START\r\nDONGOS_POWER_DENIED_SHELL\r\n'
        assert_no_power(raw, [])
        for bad in (raw + b'DONGOS_P1_START', raw + b'PANIC', raw + b'DONGOS_POWER_RESET_REQUEST', raw + b'DONGOS_POWER_PERMISSION_FAIL'):
            with self.assertRaises(ValueError): assert_no_power(bad, [])
        for name in ('RESET', 'SHUTDOWN'):
            with self.assertRaises(ValueError): assert_no_power(raw, [dict(message=dict(event=name, data=dict(guest=True)))])
        assert_no_power(raw, [dict(message=dict(event='SHUTDOWN', data=dict(guest=False, reason='host-qmp-quit')))])

    def test_tree_inventory_rejects_unapproved_file_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder); (path / 'EFI').mkdir(); (path / 'EFI/BOOT.EFI').write_bytes(b'efi')
            first = inventory_tree(path); (path / 'EFI/BOOT.EFI').write_bytes(b'changed')
            self.assertNotEqual(first, inventory_tree(path))

    def test_overlay_manifest_cannot_relabel_kernel_or_source_changes(self):
        # Tiny opaque payloads only. No ELF compiler/builder/guest is invoked.
        # Generated malicious DG and ESP models stay under build/ as required.
        parent = ROOT / 'build/test/p8-power/permission-models'; parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            directory = Path(folder)
            self.assertTrue(directory.resolve().is_relative_to((ROOT / 'build').resolve()))
            baseline, output = directory / 'base', directory / 'overlay'
            base_esp = baseline / 'esp'; (base_esp / 'EFI/BOOT').mkdir(parents=True)
            (base_esp / 'EFI/BOOT/BOOTX64.EFI').write_bytes(b'opaque-efi')
            (base_esp / 'DONGOS.IMG').write_bytes(b'opaque-boot-kernel')
            items = [(name, ELF, b'opaque-elf-' + name.encode()) for name in SERVICES] + [('font16', 2, b'font')]
            raw = pack(items); (base_esp / 'SERVICES.BIN').write_bytes(raw)
            for name in RUNTIME_FILES: (baseline / name).write_bytes(b'opaque-' + name.encode())
            for name in SERVICES:
                target = baseline / 'services' / name; target.mkdir(parents=True)
                (target / 'program.elf').write_bytes(b'opaque-elf-' + name.encode())
            metadata = dict(runtime_level=7, test=False, graphics_case=None, source_unchanged=True,
                source_sha256={'tests/run_power_permissions_qemu.py': sha(__file__)},
                artifacts={str(p.resolve()): sha(p) for p in baseline.rglob('*') if p.is_file()})
            storage.write_json(baseline / 'build-inputs.json', metadata)
            shutil.copytree(baseline, output)
            (output / 'build-inputs.json').rename(output / 'base-build-inputs.json')
            source = output / 'malicious' / (MODULE + '.dg'); source.parent.mkdir()
            source.write_text(probe_source('shell'), encoding='utf-8')
            replacement = b'opaque-malicious-elf'
            executable = output / 'services/shell/program.elf'; executable.write_bytes(replacement)
            changed = replace_one_elf(raw, 'shell', replacement); (output / 'esp/SERVICES.BIN').write_bytes(changed)
            manifest = dict(version=1, kind='negative-permission-service-overlay', changed_service='shell',
                base_esp=str(base_esp), base_build_inputs_sha256=sha(baseline / 'build-inputs.json'),
                base_source_sha256=metadata['source_sha256'], base_artifacts=metadata['artifacts'],
                original_esp_files=inventory_tree(base_esp), original_runtime_files={n: sha(baseline / n) for n in RUNTIME_FILES},
                original_service_elf={n: sha(baseline / 'services' / n / 'program.elf') for n in SERVICES},
                source='malicious/' + MODULE + '.dg', source_sha256=sha(source), case_count=13,
                malicious_elf='services/shell/program.elf', malicious_elf_sha256=sha(executable),
                original_bundle=inspect(raw), overlay_bundle=inspect(changed), changed_entries=['shell'],
                overlay_files={p.relative_to(output).as_posix(): sha(p) for p in output.rglob('*') if p.is_file()},
                production_kernel_changed=False, production_source_fingerprints_rewritten=False)
            target = output / 'permission-overlay.json'; storage.write_json(target, manifest)
            self.assertEqual('shell', verify_overlay(base_esp, output)['changed_service'])
            corrupted = dict(manifest, base_source_sha256={}); storage.write_json(target, corrupted)
            with self.assertRaises(ValueError): verify_overlay(base_esp, output)
            storage.write_json(target, manifest)
            (output / 'kernel.bin').write_bytes(b'changed-kernel')
            with self.assertRaises(ValueError): verify_overlay(base_esp, output)
            shutil.copyfile(baseline / 'kernel.bin', output / 'kernel.bin')
            source.write_text('fake marker without syscalls', encoding='utf-8')
            corrupted = dict(manifest, source_sha256=sha(source), overlay_files=dict(manifest['overlay_files']))
            corrupted['overlay_files'][manifest['source']] = sha(source)
            storage.write_json(target, corrupted)
            with self.assertRaises(ValueError): verify_overlay(base_esp, output)


if __name__ == '__main__':
    raise SystemExit(main())
