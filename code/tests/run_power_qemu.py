#!/usr/bin/env python3
"""Actual q35 ACPI S5/reset and durable shell data; reuse a normal runtime7 ESP.

No automatic build, guest memory writes, debug-exit, QMP powerdown/reset, or
permission-negative acceptance. --selftest uses only host models/loopback QMP.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
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
from tools.make_fat32_disk import create
from tools.elf_symbols import read_elf_symbols
from tests import run_acpi_qemu as acpi, run_services_qemu as storage
from tests.run_desktop_settings_qemu import Guest, DARK, ROOT, check, sha

POWER_OBJECT = 0x08000001
POWER_MODULE = 'boot.power_startup'
FORBIDDEN_QMP = {'system_reset', 'system_powerdown', 'system_wakeup', 'inject-nmi', 'set-action'}
TRACE_EVENT = 'qemu_system_shutdown_request'


class RecordedQMP:
    """Keep asynchronous events even while idle or waiting for another reply."""
    def __init__(self, port, process, journal):
        self.condition = threading.Condition()
        self.send_lock = threading.Lock()
        self.log_lock = threading.Lock()
        self.records, self.events, self.replies = [], [], {}
        self.number, self.failure, self.closed, self.buffer = 0, None, False, b''
        self.log = Path(journal).open('w', encoding='utf-8')
        deadline = time.monotonic() + 15
        while True:
            try:
                self.socket = socket.create_connection(('127.0.0.1', port), timeout=1)
                break
            except OSError:
                if process.poll() is not None or time.monotonic() >= deadline:
                    self.log.close()
                    raise
                time.sleep(.05)
        self.socket.settimeout(10)
        greeting = self.line()
        self.record('rx', greeting)
        check('QMP' in json.loads(greeting), 'QMP greeting absent')
        self.socket.settimeout(None)
        self.reader = threading.Thread(target=self.read_messages, daemon=True)
        self.reader.start()
        self.request('qmp_capabilities')

    def line(self):
        while b'\n' not in self.buffer:
            part = self.socket.recv(65536)
            if not part:
                raise EOFError('QMP closed')
            self.buffer += part
        line, self.buffer = self.buffer.split(b'\n', 1)
        return line + b'\n'

    def record(self, direction, raw):
        item = dict(direction=direction, monotonic_ns=time.monotonic_ns(),
                    wire=raw.decode('utf-8'), message=json.loads(raw))
        with self.log_lock:
            self.records.append(item)
            self.log.write(json.dumps(item) + '\n')
            self.log.flush()
        return item

    def read_messages(self):
        try:
            while not self.closed:
                raw = self.line()
                item = self.record('rx', raw)
                message = item['message']
                with self.condition:
                    if 'event' in message:
                        self.events.append(item)
                    elif 'id' in message:
                        self.replies[message['id']] = message
                    else:
                        raise ValueError('unmatched QMP packet')
                    self.condition.notify_all()
        except BaseException as error:
            with self.condition:
                self.failure = error
                self.condition.notify_all()

    def request(self, command, arguments=None):
        check(command not in FORBIDDEN_QMP, 'host power/reset injection is forbidden')
        if command == 'human-monitor-command':
            check(arguments and arguments.get('command-line', '').startswith('info '), 'mutating HMP forbidden')
        with self.send_lock:
            self.number += 1
            identity = self.number
            packet = dict(execute=command, id=identity)
            if arguments is not None:
                packet['arguments'] = arguments
            raw = json.dumps(packet).encode() + b'\n'
            self.record('tx', raw)
            self.socket.sendall(raw)
        deadline = time.monotonic() + 15
        with self.condition:
            while identity not in self.replies:
                if self.failure:
                    raise self.failure
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('QMP reply missing: ' + command)
                self.condition.wait(remaining)
            value = self.replies.pop(identity)
        if 'error' in value:
            raise RuntimeError(value['error'])
        check('return' in value, 'QMP response has no return')
        return value['return']

    def wait_event(self, name, after, timeout=30):
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                matches = [item for item in self.events[after:] if item['message']['event'] == name]
                if matches:
                    return matches[0]
                if self.failure:
                    raise self.failure
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('actual QMP event missing: ' + name)
                self.condition.wait(remaining)

    def close(self):
        self.closed = True
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.socket.close()
        self.reader.join(timeout=2)
        self.log.close()


def power_command(command, trace_file):
    check(command.count('-no-reboot') == 1, 'unexpected initial reboot policy')
    check('-no-shutdown' not in command and '-action' not in command, 'unexpected initial power policy')
    command = [part for part in command if part != '-no-reboot']
    command += ['-no-shutdown', '-trace', 'enable=' + TRACE_EVENT + ',file=' +
                str(Path(trace_file).resolve()).replace('\\', '/').replace(',', ',,')]
    return command


def validate_power_event(item, action):
    value = item['message']
    expected = ('RESET', 'guest-reset') if action == 1 else ('SHUTDOWN', 'guest-shutdown')
    check(value.get('event') == expected[0] and value.get('data', {}).get('guest') is True
          and value['data'].get('reason') == expected[1], 'event was not the required actual guest power request')
    check(isinstance(value.get('timestamp', {}).get('seconds'), int)
          and isinstance(value['timestamp'].get('microseconds'), int), 'QMP power event timestamp absent')
    return item


def validate_serial_power(raw, command_offset, action):
    suffix = bytes(raw[command_offset:])
    request = b'DONGOS_POWER_RESET_REQUEST' if action == 1 else b'DONGOS_POWER_S5_REQUEST'
    check(suffix.count(b'DONGOS_POWER_SYNCED') == 1 and suffix.count(request) == 1,
          'missing/duplicate FLUSH-completed or kernel power request record')
    check(suffix.index(b'DONGOS_POWER_SYNCED') < suffix.index(request), 'request preceded filesystem sync')
    for bad in (b'PANIC', b'DONGOS_P1_KERNEL_FAIL', b'ExecutionReturned', b'POWER_RETURNED', b'ERROR '):
        check(bad not in suffix, 'guest reported failure: ' + repr(bad))
    return dict(synced_offset=command_offset + suffix.index(b'DONGOS_POWER_SYNCED'),
                request_offset=command_offset + suffix.index(request), action=action)


def check_layout(build):
    path = build / 'dong_layout.json'
    types = {item['full_name']: item for item in json.loads(path.read_text(encoding='utf-8'))['types']}
    expected = {'ipc.handles.Entry': (40, {'generation': 0, 'kind': 8, 'object': 16, 'rights': 24, 'live': 32}),
                'ipc.handles.Table': (1296, {'ready': 0, 'used': 8, 'entries': 16}),
                'user.services.State': (1336, {'table': 0}),
                'lib.abi.Boot': (128, {'reserved3': 120}),
                'drivers.virtio_blk.Info': (72, {'ready': 24, 'faulted': 32, 'completed': 48}),
                'drivers.virtio_blk.State': (None, {'info': 0, 'busy': 72, 'published': 80})}
    for name, (size, fields) in expected.items():
        actual = types[name]
        offsets = {f['name']: f['offset'] for f in actual['fields']}
        check((actual['size'] == size if size is not None else actual['size'] >= 88)
              and all(offsets.get(k) == v for k, v in fields.items()), 'power ABI layout differs: ' + name)
    return dict(file=str(path), sha256=sha(path), validated=expected)


def validate_plan(raw):
    check(len(raw) == 184, 'Prepared must be exactly184 bytes')
    values = struct.unpack('<23Q', raw)
    check(values[0] == 1 and 1 <= values[1] <= 16 and values[2:4] == (0, 0), 'early capture did not prepare both operations')
    check(values[4:8] == (1, 0xcf9, 8, 15), 'reset escaped explicit q35 IO/width/value')
    check(values[8:11] == (1, 0x604, 16) and values[11] == values[19] << 10
          and values[12:16] == (0, 0, 0, 0) and values[16:19] == (0x3c00, 0x2000, 0), 'shutdown plan escaped PM1a-only q35 policy')
    check(values[19:21] == (0, 0) and values[21] < values[1] and 36 <= values[22] < 1048576,
          'current OVMF S5 provenance/type differs')
    return dict(version=values[0], aml_tables=values[1], reset_error=values[2], shutdown_error=values[3],
                reset=dict(space=values[4], port=values[5], width=values[6], value=values[7]),
                shutdown=dict(port=values[9], width=values[10], type_value=values[11], clear_mask=values[16],
                              enable_mask=values[17], type_a=values[19], type_b=values[20],
                              table_index=values[21], aml_offset=values[22]), raw_hex=raw.hex(), sha256=hashlib.sha256(raw).hexdigest())


def validate_capabilities(boots, states):
    check(len(boots) == 5 and len(states) == 5, 'five actual capability/boot records required')
    evidence, found = [], []
    for pid, (boot, state) in enumerate(zip(boots, states)):
        check(len(boot) == 128 and len(state) == 1336, 'capability state record size differs')
        b = struct.unpack('<16Q', boot)
        ready, used = struct.unpack_from('<2Q', state)
        check(b[0] == 1 and b[1] == pid + 1 and b[11] == 5 and ready == 1, 'service Boot/Table identity differs')
        entries = [struct.unpack_from('<5Q', state, 16 + i * 40) for i in range(32)]
        check(sum(e[4] == 1 for e in entries) == used and all(e[4] in (0, 1) for e in entries), 'capability occupancy corrupt')
        powers = [(i, entry) for i, entry in enumerate(entries) if entry[4] == 1 and entry[2] == POWER_OBJECT]
        for slot, entry in powers:
            check(pid == 0 and entry[1] == 5 and entry[3] == 2 and entry[0] > 0, 'power capability leaked or gained extra rights')
            check(b[15] == (entry[0] << 8) | (slot + 1), 'shell reserved3 token does not name its exact power entry')
            found.append(pid)
        evidence.append(dict(pid=pid, boot=list(b), entries=[list(e) for e in entries], used=used))
    check(found == [0], 'exactly one shell DEVICE/WRITE POWER_OBJECT capability required')
    return evidence


def validate_completed_flush(lease, state, header, status):
    token, physical, virtual, length = struct.unpack('<4Q', lease)
    info = struct.unpack('<11Q', state)
    check(token == 1 and physical != 0 and physical % 4096 == 0 and virtual == 0x68000000
          and length == 131072, 'actual persistent block DMA lease differs')
    check(info[3] == 1 and info[4] == 0 and info[6] > 0 and info[9:11] == (0, 0), 'block operation not complete/healthy')
    check(struct.unpack('<IIQ', header) == (4, 0, 0) and status == b'\0', 'last actual VirtIO FLUSH command did not complete')
    return dict(physical=physical, virtual=virtual, bytes=length, completed=info[6],
                header_hex=header.hex(), status_hex=status.hex(), actual_flush_completion=True)


class PowerGuest(Guest):
    def __init__(self, esp, disk, state):
        self.commands = []
        original_command, original_qmp = builder.qemu_command, acpi.QMP
        builder.qemu_command = lambda *a, **kw: power_command(original_command(*a, **kw), state / 'qemu-trace.log')
        acpi.QMP = lambda port, process: RecordedQMP(port, process, state / 'qmp-wire.jsonl')
        try:
            super().__init__(esp, disk, state)
        finally:
            builder.qemu_command, acpi.QMP = original_command, original_qmp
        check(not any('isa-debug-exit' in p for p in self.evidence['command']), 'debug-exit device present')
        check('-no-reboot' not in self.evidence['command'] and '-no-shutdown' in self.evidence['command'], 'real power policy differs')
        self.evidence.update(power_host_injection=False, actual_negative_permission_probe=False)

    def wait_from(self, marker, offset, timeout=90):
        deadline = time.monotonic() + timeout
        while marker not in self.raw[offset:]:
            check(self.process.poll() is None and b'PANIC' not in self.raw and b'DONGOS_P1_KERNEL_FAIL' not in self.raw, 'actual guest failed')
            if time.monotonic() >= deadline:
                raise TimeoutError('missing new serial marker: ' + repr(marker))
            time.sleep(.01)

    def shell(self, command, expected=None):
        check(command.isascii() and '\r' not in command and '\n' not in command and len(command) < 255, 'unsafe shell command')
        before = len(self.raw)
        self.resume()
        item = dict(command=command, serial_offset=before, monotonic_ns=time.monotonic_ns())
        self.commands.append(item)
        storage.write_json(self.state / 'shell-commands.json', self.commands)
        self.uart.sendall(command.encode() + b'\r')
        if expected is not None:
            self.wait_from(expected, before, 30)
            self.wait_from(b'> ', before, 30)
            check(b'ERROR ' not in self.raw[before:] and b'unknown command' not in self.raw[before:], 'actual shell command failed')
            self.pause()
        return before

    def snapshot_power(self, name, requests, last_action):
        self.pause()
        raw = self.kernel(self.ksym(POWER_MODULE, 'PREPARED'), 184, name + ' Prepared')
        plan = validate_plan(raw)
        actual = {field: self.kval(POWER_MODULE, field) for field in ('CAPTURE_ERROR', 'REQUESTS', 'LAST_ACTION')}
        check(actual == dict(CAPTURE_ERROR=0, REQUESTS=requests, LAST_ACTION=last_action), 'early capture/request counters differ')
        boots = [self.user(pid, 0x70000000, 128, name + ' readonly Boot') for pid in range(5)]
        check(all(self.pte(root, 0x70000000) & 0x800000000000001f == 0x8000000000000005 for root in self.roots), 'Boot page is not RO/NX')
        base = self.ksym('user.services', 'STATES')
        states = [self.kernel(base + pid * 1336, 1336, name + ' capability table') for pid in range(5)]
        capabilities = validate_capabilities(boots, states)
        info = struct.unpack('<20Q', self.kernel(self.ksym('user.services', 'INFO'), 160, name + ' actual service report'))
        check(info[1] == 5 and info[3] == info[4] and info[5:7] == (0, 0), 'service call/reply/error state differs')
        value = dict(name=name, plan=plan, globals=actual, capabilities=capabilities, service_report=list(info),
                     capability_negative_test_accepted=False)
        storage.write_json(self.state / (name + '-power.json'), value)
        self.evidence.setdefault('power_states', []).append(value)
        return value

    def completed_flush(self, name):
        self.pause()
        lease = self.kernel(self.ksym('user.devices', 'DMA_LEASE'), 32, name + ' actual block DMA lease')
        _, physical, virtual, _ = struct.unpack('<4Q', lease)
        check(self.pte(self.roots[2], virtual) & ~0x60 == physical | 0x8000000000000007,
              'FLUSH DMA command is not the actual block service mapped lease')
        symbols = read_elf_symbols(self.esp.parent / 'services/block/program.elf')
        bias = struct.unpack_from('<Q', self.processes, 2 * 1288 + 224)[0]
        state = self.user(2, bias + symbols[storage.symbol('drivers.block_service', 'STATE')], 88, name + ' actual block completion state')
        value = validate_completed_flush(lease, state,
            self.physical(physical + 256, 16, name + ' actual VirtIO command header'),
            self.physical(physical + 272, 1, name + ' actual VirtIO completion status'))
        storage.write_json(self.state / (name + '-flush.json'), value)
        return value

    def refresh_after_reset(self, offset):
        for marker in (b'DONGOS_P1_START', b'DONGOS_P7_DESKTOP_READY', b'DONGOS_INPUT_VIRTIO_TABLET_READY',
                       b'DONGOS_P7_AVX_CONTEXT_READY', b'DONGOS_SHELL_READY'):
            self.wait_from(marker, offset)
        self.pause()
        memory = {k.decode(): int(v, 16) for k, v in re.findall(rb'^memory_([a-z_]+)=0x([0-9a-f]{16})\r?$', self.raw[offset:], re.MULTILINE)}
        self.boot = struct.unpack('<20Q', self.physical(memory['runtime_boot_info'] - acpi.HHDM, 160, 'second firmware BootInfo'))
        self.processes = self.kernel(self.ksym('user.memory', 'PROCESSES'), 5 * 1288, 'second five private processes')
        self.roots = [struct.unpack_from('<Q', self.processes, i * 1288 + 8)[0] for i in range(5)]
        self.validate_private_pools()
        check(all(struct.unpack_from('<Q', self.processes, i * 1288)[0] == 1 for i in range(5)), 'second private services missing')
        self.bias = struct.unpack_from('<Q', self.processes, 3 * 1288 + 224)[0]
        self.verify_elf()
        self.settle()


def collect_trace_help(state):
    qemu = builder.find_tool('qemu-system-x86_64', 'QEMU')
    command = [qemu, '-trace', 'help']
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    text = result.stdout + result.stderr
    (state / 'qemu-trace-help.txt').write_text(text, encoding='utf-8')
    available = set(text.splitlines())
    check(result.returncode == 0 and TRACE_EVENT in available, 'QEMU actual shutdown-request trace is unavailable')
    # This QEMU build exposes no PM1_CNT/CF9 I/O write trace. A shutdown-request
    # trace proves the device-model request, not the precise port/value order.
    ports = sorted(event for event in available if re.search(r'(pm1|cf9|ich9.*reset|acpi.*pm.*write)', event, re.I))
    return dict(command=command, exit_code=result.returncode, help_sha256=sha(state / 'qemu-trace-help.txt'),
                enabled=[TRACE_EVENT], possible_port_trace_events=ports, exact_io_trace_accepted=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp', type=Path)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(PowerRunnerTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if args.reuse_esp is None:
        parser.error('--reuse-esp is required; this runner never builds')
    esp = args.reuse_esp.resolve()
    state = ROOT / 'build/test/p8-power/qemu' / ('run-' + uuid.uuid4().hex[:12])
    state.mkdir(parents=True)
    result = dict(passed=False, actual_qemu_boots=0, action_results=[], permission_negative_accepted=False,
                  exact_io_trace_accepted=False, no_qmp_power_reset_injection=True)
    inputs = {str(ROOT / p): sha(ROOT / p) for p in ('tests/run_power_qemu.py', 'tests/run_desktop_settings_qemu.py',
        'tests/run_desktop_qemu.py', 'tests/run_acpi_qemu.py', 'tests/run_services_qemu.py', 'tools/build_usb.py')}
    result['runner_inputs'] = inputs
    guest, metadata = None, None
    try:
        metadata = verify_build(esp)
        result['layout'] = check_layout(esp.parent)
        result['trace_capability'] = collect_trace_help(state)
        for action, word in ((2, 'shutdown'), (1, 'reboot')):
            disk = state / (word + '-data.img')
            create(disk, 64)
            payload = ('DongOS P8 durable ' + word + ' ' + state.name).encode()
            guest = PowerGuest(esp, disk, state / word)
            result['actual_qemu_boots'] += 1
            guest.wait(b'DONGOS_SHELL_READY')
            guest.verify_state('before-' + word, guest.descriptor()[14], DARK, 0)
            first = guest.snapshot_power('before', 0, 0)
            guest.shell('write NOTE.TXT ' + payload.decode(), b'WRITE OK\r\n')
            guest.shell('cat NOTE.TXT', b'cat NOTE.TXT\r\n' + payload + b'\r\n')
            guest.shell('sync', b'SYNC OK\r\n')
            flush_before = guest.completed_flush('before-power')
            events_before = len(guest.qmp.events)
            offset = guest.shell(word)
            event = validate_power_event(guest.qmp.wait_event('RESET' if action == 1 else 'SHUTDOWN', events_before), action)
            guest.wait_from(b'DONGOS_POWER_RESET_REQUEST' if action == 1 else b'DONGOS_POWER_S5_REQUEST', offset, 15)
            serial_order = validate_serial_power(guest.raw, offset, action)
            action_result = dict(action=word, qmp_event=event, serial_order=serial_order,
                                 prepared_sha256=first['plan']['sha256'], payload=payload.decode(), flush_before=flush_before)
            if action == 2:
                status = guest.qmp.request('query-status')
                check(status.get('status') == 'shutdown' and status.get('running') is False, 'actual ACPI S5 did not stop the VM')
                guest.stopped = True
                action_result['qmp_status'] = status
                after = guest.snapshot_power('after-s5', 1, 2)
                check(first['plan']['sha256'] == after['plan']['sha256'], 'persistent plan changed during shutdown')
                flush_after = guest.completed_flush('after-s5')
                check(flush_after['physical'] == flush_before['physical']
                      and flush_after['completed'] >= flush_before['completed'] + 2, 'S5 path did not complete the additional FAT FLUSH requests')
                action_result['flush_after'] = flush_after
            else:
                guest.refresh_after_reset(offset)
                result['actual_qemu_boots'] += 1
                check(bytes(guest.raw).count(b'DONGOS_P1_START') == 2, 'reset did not produce exactly two actual kernel entries')
                guest.snapshot_power('second-reset-boot', 0, 0)
                guest.verify_state('after-reboot', guest.descriptor()[14], DARK, 0)
                guest.shell('cat NOTE.TXT', b'cat NOTE.TXT\r\n' + payload + b'\r\n')
                guest.shell('sync', b'SYNC OK\r\n')
            check(b'PANIC' not in guest.raw and b'DONGOS_P1_KERNEL_FAIL' not in guest.raw, 'PANIC in actual power run')
            action_result['serial_sha256'] = hashlib.sha256(guest.raw).hexdigest()
            guest.close()
            guest = None
            action_result['disk_after_power'] = storage.check_disk(disk, raw_name=b'NOTE    TXT', payload=payload)
            action_result['disk_sha256_after_power'] = sha(disk)
            if action == 2:
                guest = PowerGuest(esp, disk, state / 'after-shutdown')
                result['actual_qemu_boots'] += 1
                guest.wait(b'DONGOS_SHELL_READY')
                guest.snapshot_power('second-shutdown-boot', 0, 0)
                guest.verify_state('after-cold-start', guest.descriptor()[14], DARK, 0)
                guest.shell('cat NOTE.TXT', b'cat NOTE.TXT\r\n' + payload + b'\r\n')
                guest.shell('sync', b'SYNC OK\r\n')
                guest.close()
                guest = None
                action_result['disk_after_cold_start'] = storage.check_disk(disk, raw_name=b'NOTE    TXT', payload=payload)
                check(sha(disk) == action_result['disk_sha256_after_power'], 'read/sync second boot changed original disk bytes')
            result['action_results'].append(action_result)
        verify_build(esp)
        result.update(passed=True, actual_actions=2, durable_original_note_verified=True,
                      all_five_private_elf_code_and_rx_verified=True, all_capability_tables_recorded=True)
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        if guest is not None:
            guest.close()
        result['source_unchanged'] = (metadata is not None and all(sha(p) == v for p, v in inputs.items())
            and all(sha(ROOT / p) == v for p, v in metadata['source_sha256'].items()))
        if not result['source_unchanged']:
            result.update(passed=False, identity_error='runner/source changed or completed build metadata absent')
        storage.write_json(state / 'result.json', result)
    print('P8 actual power', 'PASS' if result['passed'] else 'FAIL', state, result.get('error', ''), flush=True)
    return 0 if result['passed'] else 1


class PowerRunnerTests(unittest.TestCase):
    def test_command_allows_real_reset_and_preserves_shutdown_evidence(self):
        actual = power_command(['qemu', '-machine', 'q35', '-no-reboot'], Path('trace.log'))
        self.assertNotIn('-no-reboot', actual)
        self.assertIn('-no-shutdown', actual)
        self.assertTrue(any(TRACE_EVENT in part for part in actual))
        for command in (['qemu'], ['qemu', '-no-reboot', '-no-reboot'], ['qemu', '-no-reboot', '-no-shutdown']):
            with self.assertRaises(ValueError): power_command(command, Path('trace.log'))

    def test_events_and_uart_order_fail_closed(self):
        for action, name, reason in ((1, 'RESET', 'guest-reset'), (2, 'SHUTDOWN', 'guest-shutdown')):
            item = dict(message=dict(event=name, data=dict(guest=True, reason=reason), timestamp=dict(seconds=1, microseconds=2)))
            self.assertEqual(item, validate_power_event(item, action))
            for bad in (dict(item['message'], data=dict(guest=False, reason=reason)),
                        dict(item['message'], data=dict(guest=True, reason='host-qmp-quit')),
                        dict(item['message'], event='STOP'), dict(item['message'], timestamp={})):
                with self.assertRaises(ValueError): validate_power_event(dict(message=bad), action)
            request = b'DONGOS_POWER_RESET_REQUEST' if action == 1 else b'DONGOS_POWER_S5_REQUEST'
            good = b'old\r\nDONGOS_POWER_SYNCED\r\n' + request + b'\r\n'
            self.assertLess(validate_serial_power(good, 5, action)['synced_offset'], validate_serial_power(good, 5, action)['request_offset'])
            for bad in (request + b'\r\nDONGOS_POWER_SYNCED', good + request, good + b'PANIC'):
                with self.assertRaises(ValueError): validate_serial_power(bad, 0, action)

    def test_exact_plan_and_only_shell_capability(self):
        p = [1, 1, 0, 0, 1, 0xcf9, 8, 15, 1, 0x604, 16, 0, 0, 0, 0, 0, 0x3c00, 0x2000, 0, 0, 0, 0, 8159]
        self.assertEqual(0xcf9, validate_plan(struct.pack('<23Q', *p))['reset']['port'])
        for i, value in ((0, 0), (1, 17), (2, 1), (5, 0x604), (6, 16), (9, 0x608), (11, 1), (12, 1), (18, 1), (19, 1), (21, 1), (22, 0)):
            bad = list(p); bad[i] = value
            with self.assertRaises(ValueError): validate_plan(struct.pack('<23Q', *bad))
        boots, states = [], []
        for pid in range(5):
            boot, state = bytearray(128), bytearray(1336)
            struct.pack_into('<Q', boot, 0, 1); struct.pack_into('<Q', boot, 8, pid + 1); struct.pack_into('<Q', boot, 88, 5)
            struct.pack_into('<Q', state, 0, 1)
            if pid == 0:
                struct.pack_into('<Q', boot, 120, 257); struct.pack_into('<Q', state, 8, 1)
                struct.pack_into('<5Q', state, 16, 1, 5, POWER_OBJECT, 2, 1)
            boots.append(bytes(boot)); states.append(bytes(state))
        self.assertEqual(5, len(validate_capabilities(boots, states)))
        for pid, field, value in ((0, 24, 130), (1, 16, 1)):
            bad = list(states); data = bytearray(bad[pid])
            if pid == 1:
                struct.pack_into('<Q', data, 8, 1); struct.pack_into('<5Q', data, 16, 1, 5, POWER_OBJECT, 2, 1)
            else: struct.pack_into('<Q', data, 16 + field, value)
            bad[pid] = bytes(data)
            with self.assertRaises(ValueError): validate_capabilities(boots, bad)

    def test_idle_and_interleaved_qmp_events_are_preserved(self):
        server = socket.socket(); server.bind(('127.0.0.1', 0)); server.listen(1)
        port = server.getsockname()[1]
        failures = []
        def serve():
            try:
                with server.accept()[0] as conn:
                    stream = conn.makefile('rwb')
                    stream.write(b'{"QMP":{"version":{},"capabilities":[]}}\n'); stream.flush()
                    for name in ('qmp_capabilities', 'query-status'):
                        request = json.loads(stream.readline())
                        self.assertEqual(name, request['execute'])
                        if name == 'query-status':
                            event = dict(event='SHUTDOWN', data=dict(guest=True, reason='guest-shutdown'), timestamp=dict(seconds=5, microseconds=6))
                            stream.write(json.dumps(event).encode() + b'\n')
                        stream.write(json.dumps(dict(id=request['id'], **{'return': {}})).encode() + b'\n'); stream.flush()
                    event = dict(event='RESET', data=dict(guest=True, reason='guest-reset'), timestamp=dict(seconds=7, microseconds=8))
                    stream.write(json.dumps(event).encode() + b'\n'); stream.flush()
                    while conn.recv(4096): pass
            except BaseException as error:
                failures.append(error)
            finally:
                server.close()
        thread = threading.Thread(target=serve, daemon=True); thread.start()
        class Process:
            @staticmethod
            def poll(): return None
        with tempfile.TemporaryDirectory() as directory:
            qmp = RecordedQMP(port, Process(), Path(directory) / 'wire.jsonl')
            try:
                qmp.request('query-status')
                self.assertEqual('SHUTDOWN', qmp.wait_event('SHUTDOWN', 0, 2)['message']['event'])
                self.assertEqual('RESET', qmp.wait_event('RESET', 0, 2)['message']['event'])
                for forbidden in FORBIDDEN_QMP:
                    with self.assertRaises(ValueError): qmp.request(forbidden)
                with self.assertRaises(ValueError): qmp.request('human-monitor-command', {'command-line': 'system_reset'})
            finally:
                qmp.close()
            records = [json.loads(line) for line in (Path(directory) / 'wire.jsonl').read_text().splitlines()]
            self.assertEqual(2, sum('event' in item['message'] for item in records))
            self.assertTrue(all(json.loads(item['wire']) == item['message'] for item in records))
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertFalse(failures, failures)

    def test_actual_dma_flush_requires_complete_type4_status_zero(self):
        lease = struct.pack('<4Q', 1, 0x100000, 0x68000000, 131072)
        state = struct.pack('<11Q', 131072, 128, 0, 1, 0, 1, 42, 42, 42, 0, 0)
        header = struct.pack('<IIQ', 4, 0, 0)
        self.assertEqual(42, validate_completed_flush(lease, state, header, b'\0')['completed'])
        for h, s in ((struct.pack('<IIQ', 0, 0, 0), b'\0'), (header, b'\1')):
            with self.assertRaises(ValueError): validate_completed_flush(lease, state, h, s)
        for offset, value in ((24, 0), (32, 1), (72, 1), (80, 1)):
            bad = bytearray(state); struct.pack_into('<Q', bad, offset, value)
            with self.assertRaises(ValueError): validate_completed_flush(lease, bad, header, b'\0')


if __name__ == '__main__':
    raise SystemExit(main())
