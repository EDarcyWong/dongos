#!/usr/bin/env python3
"""Actual published P7 zoom/DPI geometry and independent GOP pixel gate.

This runner injects QMP input and reads guest physical memory only. It never
changes guest code, memory, animation clocks, or render configuration. Kernel
builds and QEMU executions are scheduled serially by the calling root agent.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import socket
import struct
import sys
import tempfile
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests import desktop_preferences_oracle as disk_oracle
from tests import run_services_qemu as storage
from tests.run_desktop_settings_qemu import Guest, ROOT, DARK, LIGHT, check, rect, sha, theme_bytes
from tools.make_fat32_disk import create
from tools import build as builder


def rsp_packet(payload):
    data = payload.encode('ascii')
    return b'$' + data + b'#' + f'{sum(data) & 255:02x}'.encode('ascii')


def rsp_decode(data):
    out = bytearray()
    cursor = 0
    while cursor < len(data):
        value = data[cursor]
        cursor += 1
        if value == 125:
            check(cursor < len(data), 'truncated RSP escape')
            out.append(data[cursor] ^ 32)
            cursor += 1
        elif value == 42:
            check(out and cursor < len(data) and 3 <= data[cursor] - 29 <= 97, 'invalid RSP run length')
            out.extend([out[-1]] * (data[cursor] - 29))
            cursor += 1
        else:
            out.append(value)
        check(len(out) <= 65536, 'oversized RSP reply')
    return out.decode('ascii')


class HardwareRSP:
    """A deliberately restricted RSP client: Z1 only; no target writes/steps."""
    def __init__(self, connection, log):
        self.socket, self.log = connection, log
        self.continue_pending = False
        self.inbox, self.prefix = [], b''
        self.socket.settimeout(10)

    def byte(self):
        if self.prefix:
            value, self.prefix = self.prefix[:1], self.prefix[1:]
            return value
        value = self.socket.recv(1)
        if not value:
            raise EOFError('GDB stub disconnected')
        return value

    def packet(self):
        if self.inbox:
            return self.inbox.pop(0)
        return self.wire_packet()

    def wire_packet(self):
        while True:
            first = self.byte()
            if first in (b'+', b'-'):
                continue
            check(first == b'$', 'unexpected RSP framing byte')
            data = bytearray()
            while True:
                value = self.byte()
                if value == b'#':
                    break
                data.extend(value)
            checksum = self.byte() + self.byte()
            check(int(checksum, 16) == sum(data) & 255, 'RSP response checksum differs')
            self.socket.sendall(b'+')
            value = rsp_decode(data)
            if value.startswith(('T', 'S', 'W', 'X')):
                self.continue_pending = False
            self.log.append(dict(direction='reply', payload=value))
            return value

    def send(self, command):
        check(command in ('?', 'qSupported:hwbreak+;swbreak-', 'Hc-1', 'c', 'p10')
              or command.startswith(('Z1,', 'z1,')), 'RSP target write/unsupported command forbidden')
        if command == 'c':
            check(not self.continue_pending, 'duplicate pending RSP continue forbidden')
        self.log.append(dict(direction='command', payload=command))
        self.socket.sendall(rsp_packet(command))
        # In ack mode, wait until the stub actually accepted the continue
        # before sending input on the separate QMP socket. Otherwise QMP input
        # can overtake c and be rejected while the VM is still stopped.
        while True:
            value = self.byte()
            if value == b'+':
                break
            check(value == b'$', 'RSP command was not acknowledged')
            self.prefix = b'$'
            self.inbox.append(self.wire_packet())
        self.log.append(dict(direction='ack', payload='+', command=command))
        if command == 'c':
            self.continue_pending = True

    def request(self, command):
        self.send(command)
        while True:
            value = self.packet()
            # QMP stop/cont can leave asynchronous halt notifications. They
            # are acknowledged and retained in the log, never used as an OK.
            if command != '?' and value.startswith(('T', 'S', 'W', 'X')):
                continue
            return value

    def breakpoint(self, address, insert):
        value = self.request(('Z1' if insert else 'z1') + f',{address:x},1')
        check(value == 'OK', 'hardware-assisted breakpoint command rejected: ' + value)

    def close(self):
        self.socket.close()


def publication_instruction(elf, busy_symbol):
    """Fail-closed x86 decode of the compiler's unique FRAME_BUSY=0 store.

    LEA RIP+busy; spill address; MOV EAX,0; reload *same* spill; MOV [R11],RAX.
    The following LEA RAX,[RBP+disp32] is exactly seven bytes. A second Z1 at
    its successor advances past the primary breakpoint without single-step
    packets, disabled-interrupt stepping, or software breakpoints.
    """
    data = Path(elf).read_bytes()
    check(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01'
          and struct.unpack_from('<H', data, 18)[0] == 62, 'expected x86-64 ELF publication code')
    ph = struct.unpack_from('<Q', data, 32)[0]
    stride, count = struct.unpack_from('<HH', data, 54)
    check(stride >= 56 and count and ph + count * stride <= len(data), 'invalid ELF publication program table')
    matches = []
    for index in range(count):
        kind, flags, offset, address, _, size, _, _ = struct.unpack_from('<IIQQQQQQ', data, ph + index * stride)
        if kind != 1 or not flags & 1:
            continue
        check(offset + size <= len(data), 'truncated executable publication segment')
        code = data[offset:offset + size]
        for pos in range(len(code) - 39):
            if code[pos:pos + 3] != b'\x48\x8d\x05':
                continue
            if address + pos + 7 + struct.unpack_from('<i', code, pos + 3)[0] != busy_symbol:
                continue
            item = code[pos:pos + 39]
            if not (item[7:10] == b'\x48\x89\x85' and item[14:19] == b'\xb8\0\0\0\0'
                    and item[19:22] == b'\x4c\x8b\x9d' and item[10:14] == item[22:26]
                    and item[26:29] == b'\x49\x89\x03' and item[29:32] == b'\x48\x8d\x85'
                    and item[36:39] == b'\x0f\xb6\x00'):
                continue
            matches.append(dict(sequence_address=address + pos, primary=address + pos + 29,
                                secondary=address + pos + 36, code_hex=item.hex(),
                                code_sha256=hashlib.sha256(item).hexdigest()))
    check(len(matches) == 1, 'expected one strictly decoded FRAME_BUSY zero publication sequence')
    return matches[0]


def full_rect(body, target, margin):
    """The complete final texture scales with the animated body rectangle."""
    left, top, right, bottom = body
    tw, th = target[2] - target[0], target[3] - target[1]
    check(tw > 0 and th > 0 and right > left and bottom > top, 'nonpositive render geometry')
    mx, my = margin * (right - left) // tw, margin * (bottom - top) // th
    return left - mx, top - my, right + mx, bottom + my


def source_point(x, y, full, width, height):
    left, top, right, bottom = full
    if not (left <= x < right and top <= y < bottom):
        return None
    return (x - left) * width // (right - left), (y - top) * height // (bottom - top)


def over(src, dst, opacity):
    """Independent scalar Q8 opacity followed by rounded source-over /255."""
    check(0 <= opacity <= 256, 'invalid published alpha')
    alpha = ((src >> 24) * opacity + 128) // 256
    return sum(min(255, (((src >> shift) & 255) * opacity + 128) // 256
                   + (((dst >> shift) & 255) * (255 - alpha) + 127) // 255) << shift
               for shift in (0, 8, 16, 24))


def on_segment(value, start, end):
    return all(min(a, b) <= v <= max(a, b) for v, a, b in zip(value, start, end))


def interior_geometry(value, start, end, clearance=1):
    return (on_segment(value, start, end)
            and max(abs(v-a) for v, a in zip(value, start)) >= clearance
            and max(abs(v-b) for v, b in zip(value, end)) >= clearance)


class ModelTests(unittest.TestCase):
    def test_reversal_sample_has_enough_integer_geometry(self):
        start, end = (0, 0, 640, 260), (20, 8, 620, 252)
        self.assertFalse(interior_geometry((0, 0, 639, 259), start, end, 6))
        self.assertTrue(interior_geometry((8, 3, 632, 257), start, end, 6))
        self.assertFalse(interior_geometry(start, start, end))
        self.assertFalse(interior_geometry(end, start, end))
        # A one-pixel reversal has no integer position strictly between ends.
        self.assertFalse(interior_geometry((0, 0, 639, 259), (0, 0, 639, 259), start))

    def test_independent_nearest_coordinates_and_scaled_margins(self):
        self.assertEqual((-2, -1, 10, 5), full_rect((0, 0, 8, 4), (0, 0, 12, 12), 3))
        self.assertEqual([0, 0, 1, 1, 2], [source_point(x, 0, (0, 0, 5, 3), 3, 2)[0] for x in range(5)])
        self.assertEqual([0, 0, 1], [source_point(0, y, (0, 0, 5, 3), 3, 2)[1] for y in range(3)])
        self.assertIsNone(source_point(5, 0, (0, 0, 5, 3), 3, 2))

    def test_premultiplied_opacity_endpoints_and_rounding(self):
        self.assertEqual(0xff123456, over(0x80604020, 0xff123456, 0))
        self.assertEqual(0xff204080, over(0xff204080, 0xff123456, 256))
        self.assertEqual(0xff181818, over(0xff202020, 0xff101010, 128))
        self.assertEqual(0xff2d3748, over(0x80402010, 0xff123456, 128))

    def test_rsp_hardware_only_mock_and_checksums(self):
        class MockSocket:
            def __init__(self, incoming): self.incoming, self.writes = bytearray(incoming), []
            def settimeout(self, value): pass
            def recv(self, size):
                value = bytes(self.incoming[:size]);del self.incoming[:size];return value
            def sendall(self, data): self.writes.append(data)
            def close(self): pass
        wire = MockSocket(b'+' + rsp_packet('T02thread:1;') + rsp_packet('OK')
                          + b'+' + rsp_packet('OK') + b'+' + rsp_packet('T05hwbreak:;thread:1;'))
        log = []
        client = HardwareRSP(wire, log)
        client.breakpoint(0x40020e46, True)
        client.breakpoint(0x40020e46, False)
        client.send('c')
        self.assertTrue(client.packet().startswith('T05'))
        self.assertFalse(client.continue_pending)
        commands = [x['payload'] for x in log if x['direction'] == 'command']
        self.assertEqual(['Z1,40020e46,1', 'z1,40020e46,1', 'c'], commands)
        for forbidden in ('Z0,40020e46,1', 'M40020e46,1:cc', 'X40020e46,1:x', 'P10=0', 's'):
            with self.assertRaises(ValueError): client.send(forbidden)
        self.assertEqual('AAAA', rsp_decode(b'A* '))
        self.assertEqual('#', rsp_decode(b'}\x03'))
        with self.assertRaises(ValueError): HardwareRSP(MockSocket(b'$OK#00'), []).packet()
        self.assertTrue(all(not item.startswith((b'$Z0', b'$M', b'$X', b'$P', b'$s')) for item in wire.writes))

    def test_capture_actions_resume_through_rsp_not_qmp(self):
        class Recorder:
            def __init__(self): self.commands = [];self.continue_pending = False
            def send(self, value):
                self.commands.append(value)
                if value == 'c': self.continue_pending = True
            def request(self, command, arguments=None): self.commands.append((command, arguments));return {}
        class NoVmAction(TransitionGuest):
            def __init__(self):
                self.rsp, self.qmp = Recorder(), Recorder()
                self.primary, self.stopped, self.armed = 0x40020e46, True, set()
            def pause(self): self.stopped = True
            def value(self, name): return 21
            def arm(self, point): self.armed.add(point)
            def resume(self): raise AssertionError('captured action used QMP resume instead of RSP c')
        for action in ('key', 'button'):
            guest = NoVmAction()
            if action == 'key': guest.key_async('equal')
            else: guest.button_async(True)
            self.assertEqual(['c'], guest.rsp.commands)
            self.assertTrue(guest.rsp.continue_pending)
            self.assertFalse(guest.stopped)
            self.assertEqual(21, guest.action_frame)
            self.assertIn(guest.primary, guest.armed)
            self.assertEqual('send-key' if action == 'key' else 'input-send-event', guest.qmp.commands[0][0])

    def test_publication_instruction_unique_real_x86_patterns(self):
        data = bytearray(512)
        data[:7] = b'\x7fELF\x02\x01\x01'
        struct.pack_into('<H', data, 18, 62)
        struct.pack_into('<Q', data, 32, 64)
        struct.pack_into('<HH', data, 54, 56, 1)
        struct.pack_into('<IIQQQQQQ', data, 64, 1, 5, 128, 0x1000, 0, 384, 384, 4096)
        busy = 0x8000
        sequence = (bytes.fromhex('488d05') + struct.pack('<i', busy-0x1000-7)
                    + bytes.fromhex('48898500f8ffffb8000000004c8b9d00f8ffff498903488d859ffcffff0fb600'))
        self.assertEqual(39, len(sequence))
        data[128:128+39] = sequence
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'mock.elf';path.write_bytes(data)
            value = publication_instruction(path, busy)
            self.assertEqual((0x101d, 0x1024), (value['primary'], value['secondary']))
            # A different spill is not the verified reload, even if a later
            # store happens to clear some memory.
            data[128+22] ^= 1;path.write_bytes(data)
            with self.assertRaises(ValueError): publication_instruction(path, busy)
            data[128+22] ^= 1
            other = bytearray(sequence);struct.pack_into('<i', other, 3, busy-0x1040-7)
            data[192:192+39] = other;path.write_bytes(data)
            with self.assertRaises(ValueError): publication_instruction(path, busy)


class TransitionGuest(Guest):
    SIZES = {'FRAME_BUSY': 8, 'ALPHA': 32, 'PRESENTED_ALPHA': 32,
             'VISUAL_RECTS': 128, 'PRESENTED_RECTS': 128,
             'STYLE_REVISION': 8, 'PRESENTED_STYLE_REVISION': 8,
             'MOTION_ACTIVE': 8, 'CACHES_DIRTY': 1, 'CACHE_MASK': 8,
             'FRAME_COUNT': 8}

    def __init__(self, *args, **kwargs):
        self.rsp = None
        self.armed = set()
        self.gdb_log = []
        port = storage.free_port()
        original = builder.qemu_command
        def with_gdb(*command_args, **command_kwargs):
            return original(*command_args, **command_kwargs) + ['-gdb', f'tcp:127.0.0.1:{port}']
        builder.qemu_command = with_gdb
        try:
            super().__init__(*args, **kwargs)
        finally:
            builder.qemu_command = original
        try:
            self.initialize_hardware(port)
        except Exception:
            self.close()
            raise

    def initialize_hardware(self, port):
        self.evidence['hardware_gdb_log'] = self.gdb_log
        self.rsp = HardwareRSP(socket.create_connection(('127.0.0.1', port)), self.gdb_log)
        supported = self.rsp.request('qSupported:hwbreak+;swbreak-')
        check(supported and not supported.startswith('E'), 'GDB stub capabilities unavailable')
        check(self.rsp.request('Hc-1') == 'OK', 'GDB all-CPU continue selection failed')
        halt = self.rsp.request('?')
        check(halt.startswith(('T', 'S')), 'GDB stub not initially halted')
        self.breakpoint = publication_instruction(self.esp.parent / 'services/compositor/program.elf',
            self.syms[storage.symbol('desktop.service', 'FRAME_BUSY')])
        self.primary = self.bias + self.breakpoint['primary']
        self.secondary = self.bias + self.breakpoint['secondary']
        self.verify_breakpoint_code('initial')
        self.evidence['hardware_publication_breakpoint'] = dict(self.breakpoint, runtime_primary=self.primary,
            runtime_secondary=self.secondary, inserted_kind='Z1', code_or_memory_write_packets=False,
            documentation='https://www.qemu.org/docs/master/system/gdb.html#breakpoint-and-watchpoint-support')
        self.publication = {}
        for name, size in self.SIZES.items():
            address = self.bias + self.syms[storage.symbol('desktop.service', name)]
            self.publication[name] = address, size
        low = min(a for a, _ in self.publication.values())
        high = max(a + n for a, n in self.publication.values())
        check(high - low <= 131072, 'publication range unexpectedly large')
        self.progress_low, self.progress_size = low, high - low
        self.action_frame = 0
        # The private globals retain their pages through every font remap.
        # Save the translated runs while stopped, then one/two physical reads
        # can observe a real 140 ms transition without many per-symbol calls.
        self.progress_runs = self.virtual_runs(low, high - low)
        self.settle_motion()

    def verify_breakpoint_code(self, phase):
        point = self.bias + self.breakpoint['sequence_address']
        expected = bytes.fromhex(self.breakpoint['code_hex'])
        actual = self.user(3, point, len(expected), 'actual immutable hardware breakpoint code ' + phase)
        check(actual == expected, 'hardware breakpoint changed actual compositor code')
        check(self.pte(self.roots[3], point) & 0x800000000000001f == 5,
              'hardware breakpoint code lost USER/RO/RX/WB permissions')
        for pid in (0, 1, 2, 4):
            check(self.pte(self.roots[pid], self.primary) == 0
                  and self.pte(self.roots[pid], self.secondary) == 0,
                  'hardware execution breakpoint address is mapped by another service')
        self.evidence.setdefault('hardware_code_observations', []).append(dict(phase=phase,
            runtime_address=point, code_hex=actual.hex(), sha256=hashlib.sha256(actual).hexdigest(),
            actual_code_pte=self.pte(self.roots[3], point), other_service_addresses_unmapped=True))

    def arm(self, address):
        if address not in self.armed:
            self.rsp.breakpoint(address, True)
            self.armed.add(address)

    def disarm(self, address):
        if address in self.armed:
            self.rsp.breakpoint(address, False)
            self.armed.remove(address)

    def hardware_continue(self, expected):
        status = self.qmp.request('query-status')
        self.evidence.setdefault('hardware_control', []).append(dict(operation='await_publication',
            qmp_status=status, rsp_continue_pending=self.rsp.continue_pending, expected_rip=expected))
        if status.get('running'):
            # Only an RSP c establishes the stop reply that this client waits
            # for. QMP cont can run to a hardware point without sending RSP a
            # reply; relying on that implicit notification caused a real hang.
            check(self.rsp.continue_pending, 'running capture has no pending RSP continue reply')
            self.stopped = False
        elif status.get('status') == 'debug':
            registers = self.qmp.request('human-monitor-command', {'command-line': 'info registers -a'})
            bsp = re.split(r'CPU#\d+\s*', registers)[1]
            current = int(re.search(r'RIP=([0-9a-fA-F]+)', bsp)[1], 16)
            if not self.rsp.continue_pending:
                self.rsp.send('?' if current == expected else 'c')
            self.stopped = current == expected
        else:
            self.rsp.send('c')
            self.stopped = False
        while True:
            reason = self.rsp.packet()
            check(reason.startswith(('T', 'S')), 'GDB continue did not return a halt packet')
            status = self.qmp.request('query-status')
            self.evidence.setdefault('hardware_control', []).append(dict(operation='stop_reply_received',
                stop_reason=reason, qmp_status=status, expected_rip=expected))
            if status.get('running'):
                # A prior QMP-stop notification may already have been queued.
                continue
            if reason[:3] not in ('T05', 'S05') and status.get('status') == 'debug':
                # A real hardware stop can follow an earlier QMP interrupt
                # notification on the same RSP socket. Query the current halt.
                self.rsp.send('?')
                continue
            self.stopped = True
            check(status.get('status') == 'debug' and reason[:3] in ('T05', 'S05'),
                  'guest stopped outside a hardware-assisted execution breakpoint')
            registers = self.qmp.request('human-monitor-command', {'command-line': 'info registers -a'})
            cpus = re.split(r'CPU#\d+\s*', registers)[1:]
            check(len(cpus) == 4, 'hardware breakpoint lost actual four-CPU state')
            pc = int(re.search(r'RIP=([0-9a-fA-F]+)', cpus[0])[1], 16)
            root = int(re.search(r'CR3=([0-9a-fA-F]+)', cpus[0])[1], 16)
            check(pc == expected, 'hardware execution stopped at an unexpected PC')
            check(root == self.roots[3] and 'CPL=3' in cpus[0], 'hardware breakpoint did not stop the actual CPL3 compositor')
            self.evidence.setdefault('hardware_stops', []).append(dict(reason=reason,
                qmp_status=status, actual_rip=pc, expected_rip=expected,
                actual_cr3=root, expected_cr3=self.roots[3], actual_cpl=3,
                register_dump_sha256=hashlib.sha256(registers.encode()).hexdigest()))
            return

    def advance_publication(self, rearm):
        # The temporary point is the next instruction after the verified LEA.
        # Continuing executes normal guest instructions/interrupt policy only.
        self.disarm(self.primary)
        self.arm(self.secondary)
        self.hardware_continue(self.secondary)
        self.disarm(self.secondary)
        if rearm:
            self.arm(self.primary)

    def close(self):
        cleanup_error = None
        if getattr(self, 'rsp', None):
            try:
                self.pause()
                for address in tuple(self.armed):
                    self.disarm(address)
                if hasattr(self, 'breakpoint'):
                    self.verify_breakpoint_code('final')
            except Exception as exc:
                cleanup_error = exc
                self.evidence['hardware_cleanup_error'] = f'{type(exc).__name__}: {exc}'
            finally:
                self.rsp.close()
                self.rsp = None
        super().close()
        if cleanup_error:
            raise cleanup_error

    def virtual_runs(self, va, count):
        result = []
        while count:
            pte = self.pte(self.roots[3], va)
            check(pte & 1, 'missing compositor RAM')
            n = min(count, 4096 - (va & 4095))
            pa = (pte & storage.MASK) + (va & 4095)
            if result and result[-1][0] + result[-1][1] == pa:
                result[-1] = result[-1][0], result[-1][1] + n
            else:
                result.append((pa, n))
            va += n
            count -= n
        return result

    def ram(self, address, size, role):
        runs = self.virtual_runs(address, size)
        low, high = min(a for a, _ in runs), max(a + n for a, n in runs)
        if high - low <= 1 << 24:
            # WB backing pages are currently separated by 4 KiB allocator
            # holes. A bounded physical span, reassembled from verified PTEs,
            # avoids thousands of QMP commands while the guest is stopped.
            block = self.physical(low, high - low, role + ' physical span')
            result = b''.join(block[a - low:a - low + n] for a, n in runs)
            self.evidence.setdefault('ram_gathers', []).append(dict(virtual=address, bytes=size,
                physical=low, physical_span_bytes=high-low, verified_runs=len(runs)))
            return result
        return b''.join(self.physical(pa, n, role) for pa, n in runs)

    def progress(self):
        block = b''.join(self.physical(pa, n, 'live completed transition publication') for pa, n in self.progress_runs)
        values = {}
        for name, (address, n) in self.publication.items():
            data = block[address - self.progress_low:address - self.progress_low + n]
            if n == 128:
                values[name] = tuple(struct.unpack_from('<4q', data, i * 32) for i in range(4))
            elif n == 32:
                values[name] = struct.unpack('<4Q', data)
            else:
                values[name] = int.from_bytes(data, 'little')
        return values

    @staticmethod
    def coherent(value):
        return (value['FRAME_BUSY'] == 0 and value['CACHES_DIRTY'] == 0 and value['CACHE_MASK'] == 0
                and value['ALPHA'] == value['PRESENTED_ALPHA']
                and value['VISUAL_RECTS'] == value['PRESENTED_RECTS']
                and value['STYLE_REVISION'] == value['PRESENTED_STYLE_REVISION'])

    def settle_motion(self):
        self.resume()
        time.sleep(.2)
        self.pause()
        deadline = time.monotonic() + 8
        while True:
            value = self.progress()
            if self.coherent(value) and not value['MOTION_ACTIVE']:
                return value
            check(time.monotonic() < deadline, 'geometric transition did not settle')
            self.resume()
            time.sleep(.04)
            self.pause()

    def key_async(self, *keys):
        self.pause()
        self.action_frame = self.value('FRAME_COUNT')
        self.arm(self.primary)
        self.capture_input('send-key', dict(keys=[dict(type='qcode', data=k) for k in keys], **{'hold-time': 1}))

    def button_async(self, down):
        if down:
            self.pause()
        self.action_frame = self.value('FRAME_COUNT')
        if down:
            self.arm(self.primary)
            self.capture_input('input-send-event', dict(events=[dict(type='btn', data=dict(button='left', down=True))]))
        else:
            self.resume()
            self.qmp.request('input-send-event', dict(events=[dict(type='btn', data=dict(button='left', down=False))]))

    def capture_input(self, command, arguments):
        for _ in range(2):
            self.rsp.send('c')
            self.stopped = False
            try:
                self.qmp.request(command, arguments)
                return
            except RuntimeError as exc:
                status = self.qmp.request('query-status')
                if 'not running' not in str(exc).lower() or status.get('status') != 'debug':
                    raise
                # A preceding cursor frame can complete between continue and
                # QMP injection. The rejected event has not been delivered;
                # consume that real publication, pass its verified LEA, and
                # retry once from the following instruction.
                self.evidence.setdefault('hardware_control', []).append(dict(operation='input_rejected_before_delivery',
                    command=command, error=str(exc), qmp_status=status))
                self.hardware_continue(self.primary)
                self.advance_publication(True)
                self.action_frame = self.value('FRAME_COUNT')
        raise ValueError('QMP input was repeatedly rejected at a prior publication')

    def move_async(self, x, y):
        d = self.descriptor()
        coords = [(p * 32767 + n - 2) // (n - 1) for p, n in ((x, d[1]), (y, d[2]))]
        self.resume()
        self.qmp.request('input-send-event', dict(events=[dict(type='abs', data=dict(axis=a, value=v))
                                                       for a, v in zip(('x', 'y'), coords)]))

    def capture_middle(self, name, index, *, fade=False, show=None, revision=None, clearance=1):
        observations = []
        try:
            for _ in range(64):
                self.hardware_continue(self.primary)
                value = self.progress()
                observations.append(value)
                check(self.coherent(value), 'publication instruction exposed an incomplete actual frame')
                alpha = value['PRESENTED_ALPHA'][index]
                actual_visible = bool(struct.unpack_from('<Q', self.windows(), index * 144 + 136)[0] & 1)
                applied = ((revision is None or value['STYLE_REVISION'] == revision)
                           and (show is None or actual_visible == show))
                if (value['MOTION_ACTIVE'] & (1 << index) and value['FRAME_COUNT'] > self.action_frame
                        and (not fade or 0 < alpha < 256)
                        and applied):
                    track = self.field('TRANSITIONS', 320)
                    start = struct.unpack_from('<4q', track, index * 80)
                    end = struct.unpack_from('<4q', track, index * 80 + 32)
                    # Publishing the source endpoint after rebuilding a DPI
                    # cache proves remapping, but does not prove interpolation.
                    if interior_geometry(value['PRESENTED_RECTS'][index], start, end, clearance):
                        self.evidence.setdefault('capture_observations', {})[name] = observations
                        self.advance_publication(False)
                        self.verify_breakpoint_code(name)
                        return self.verify_scene(name, value)
                if (value['FRAME_COUNT'] > self.action_frame and not value['MOTION_ACTIVE'] & (1 << index)
                        and applied):
                    self.advance_publication(False)
                    break
                self.advance_publication(True)
        except Exception:
            self.capture_diagnostic(name, observations)
            raise
        self.capture_diagnostic(name, observations)
        raise ValueError('no completed actual intermediate geometric frame: ' + name)

    def capture_pointer_cancel(self, name, index):
        observations = []
        for _ in range(64):
            self.hardware_continue(self.primary)
            value = self.progress()
            observations.append(value)
            grab = struct.unpack_from('<Q', self.windows(), 2448)[0]
            if self.coherent(value) and value['FRAME_COUNT'] > self.action_frame and grab == index + 257:
                if self.coherent(value) and value['FRAME_COUNT'] > self.action_frame:
                    tracks = self.field('TRANSITIONS', 320)
                    start = struct.unpack_from('<4q', tracks, index * 80)
                    end = struct.unpack_from('<4q', tracks, index * 80 + 32)
                    duration = struct.unpack_from('<Q', tracks, index * 80 + 72)[0]
                    target = rect(self.windows(), index)
                    check(not value['MOTION_ACTIVE'] & (1 << index) and duration == 0
                          and start == end == target == value['PRESENTED_RECTS'][index],
                          'pointer press did not explicitly cancel the in-flight track')
                    self.evidence.setdefault('capture_observations', {})[name] = observations
                    self.advance_publication(False)
                    self.verify_breakpoint_code(name)
                    return self.verify_scene(name, value)
            self.advance_publication(True)
        self.capture_diagnostic(name, observations)
        raise ValueError('pointer cancellation did not publish a completed frame')

    def capture_diagnostic(self, name, observations):
        self.pause()
        value = self.progress()
        d = self.descriptor()
        durations = struct.unpack('<256Q', self.field('FRAME_TIMES', 2048))
        completed = struct.unpack('<256Q', self.field('FRAME_COMPLETED', 2048))
        first = max(0, self.action_frame - 2, value['FRAME_COUNT'] - 256)
        item = dict(name=name, action_frame=self.action_frame, final_progress=value,
                    target_rects=[rect(self.windows(), i) for i in range(4)],
                    tsc_hz=d[10], observations=observations,
                    frames=[dict(number=i, completion_tsc=completed[i % 256],
                                 composition_ticks=durations[i % 256],
                                 composition_seconds=durations[i % 256] / d[10])
                            for i in range(first, value['FRAME_COUNT'])])
        self.evidence.setdefault('capture_diagnostics', []).append(item)
        storage.write_json(self.state / (name + '-capture-diagnostic.json'), item)

    def verify_scene(self, name, value=None):
        self.pause()
        value = value or self.progress()
        check(self.coherent(value), 'snapshot includes an unpublished/incomplete frame')
        d = self.descriptor()
        width, height, stride, fmt = d[1:5]
        style = self.field('STYLE', 72)
        scale = struct.unpack_from('<Q', style, 56)[0]
        check(scale == d[14], 'descriptor and compositor source metrics disagree')
        margin = (12 * scale + 128) // 256
        win = self.windows()
        order = struct.unpack_from('<16Q', win, 2304)
        count = struct.unpack_from('<Q', win, 2432)[0]
        check(count == 4 and set(order[:count]) == {257, 258, 259, 260}, 'window identities changed')
        pointer = struct.unpack_from('<2q', win, 2464)
        targets = tuple(rect(win, i) for i in range(4))
        bodies = value['PRESENTED_RECTS']
        alphas = value['PRESENTED_ALPHA']
        check(all(0 <= q <= 256 for q in alphas), 'alpha outside bounded Q8')
        background = self.ram(d[12], d[6], 'actual final background cache')
        textures = self.ram(d[13], 8 * 1024 * 1024, 'actual final four window textures')
        gop = self.physical(self.boot[8], d[6], 'actual completed GOP pixels')
        back = self.ram(d[7], d[6], 'actual completed WB back buffer')
        full = tuple(full_rect(bodies[i], targets[i], margin) for i in range(4))
        points = {(x, y) for y in range(3, height, 37) for x in range(5, width, 43)}
        for i in range(4):
            l, t, r, b = full[i]
            # Source boundaries, AA/shadow samples, and interior texture detail.
            xs = (l - 1, l, l + 1, l + 3, l + margin, (l + r) // 2, r - margin - 1, r - 2, r - 1, r)
            ys = (t - 1, t, t + 1, t + 3, t + margin, (t + b) // 2, b - margin - 1, b - 2, b - 1, b)
            points.update((x, y) for x in xs for y in ys if 0 <= x < width and 0 <= y < height)
        for dy in (0, (4 * scale + 128) // 256, (16 * scale + 128) // 256):
            for dx in (0, dy // 2):
                x, y = pointer[0] + dx, pointer[1] + dy
                if 0 <= x < width and 0 <= y < height:
                    points.add((x, y))
        text_color = struct.unpack_from('<I', style, 8)[0]
        changed_by_alpha = changed_by_geometry = 0
        evidence = []
        for x, y in sorted(points, key=lambda p: (p[1], p[0])):
            color = struct.unpack_from('<I', background, (y * stride + x) * 4)[0]
            alpha_changed = geometry_changed = False
            for handle in order[:count]:
                i = (handle & 255) - 1
                if not alphas[i]:
                    continue
                target = targets[i]
                sw, sh = target[2] - target[0] + 2 * margin, target[3] - target[1] + 2 * margin
                uv = source_point(x, y, full[i], sw, sh)
                if uv is None:
                    continue
                sx, sy = uv
                src = struct.unpack_from('<I', textures, i * 0x200000 + (sy * sw + sx) * 4)[0]
                result = over(src, color, alphas[i])
                alpha_changed |= 0 < alphas[i] < 256 and result not in (color, src)
                geometry_changed |= bodies[i] != target and src != 0 and uv != (x - target[0] + margin, y - target[1] + margin)
                color = result
            dx, dy = x - pointer[0], y - pointer[1]
            if 0 <= dy < (17 * scale + 128) // 256 and 0 <= dx <= dy // 2:
                color = text_color
            actual_back = struct.unpack_from('<I', back, (y * stride + x) * 4)[0]
            check(actual_back == color, f'{name}: actual WB pixel differs at {(x, y)}: {actual_back:08x} != {color:08x}')
            expected_gop = color & 0xffffff
            if fmt == 0:
                expected_gop = ((expected_gop & 255) << 16) | (expected_gop & 0xff00) | (expected_gop >> 16)
            actual_gop = struct.unpack_from('<I', gop, (y * stride + x) * 4)[0] & 0xffffff
            check(actual_gop == expected_gop, f'{name}: actual GOP differs at {(x, y)}: {actual_gop:06x} != {expected_gop:06x}')
            changed_by_alpha += alpha_changed
            changed_by_geometry += geometry_changed
            evidence.append((x, y, color, actual_gop))
        tracks = self.field('TRANSITIONS', 320)
        durations = struct.unpack('<256Q', self.field('FRAME_TIMES', 2048))
        completed = struct.unpack('<256Q', self.field('FRAME_COMPLETED', 2048))
        recent = range(max(0, self.action_frame, value['FRAME_COUNT'] - 32), value['FRAME_COUNT'])
        item = dict(name=name, frame_count=value['FRAME_COUNT'], scale_q8=scale,
                    visual_rects=bodies, target_rects=targets, source_full_rects=full,
                    presented_alpha=alphas, active_mask=value['MOTION_ACTIVE'],
                    style_revision=value['STYLE_REVISION'], exact_gop_pixels=len(points),
                    actual_alpha_changed_pixels=changed_by_alpha, actual_scaled_texture_pixels=changed_by_geometry,
                    pixel_oracle_sha256=hashlib.sha256(json.dumps(evidence).encode()).hexdigest(),
                    target_state_sha256=hashlib.sha256(win).hexdigest(),
                    tsc_hz=d[10], snapshot_pauses_excluded_from_performance_acceptance=True,
                    recent_frames=[dict(number=i, completion_tsc=completed[i % 256],
                                        composition_ticks=durations[i % 256],
                                        composition_seconds=durations[i % 256] / d[10]) for i in recent],
                    transitions=[dict(from_rect=struct.unpack_from('<4q', tracks, i * 80),
                                      to_rect=struct.unpack_from('<4q', tracks, i * 80 + 32),
                                      start_ms=struct.unpack_from('<Q', tracks, i * 80 + 64)[0],
                                      duration_ms=struct.unpack_from('<Q', tracks, i * 80 + 72)[0]) for i in range(4)])
        ppm = self.state / (name + '.ppm')
        self.qmp.request('screendump', dict(filename=str(ppm.resolve())))
        from PIL import Image
        Image.open(ppm).save(self.state / (name + '.png'))
        item['screenshot'] = name + '.png'
        self.evidence.setdefault('geometric_scenes', []).append(item)
        storage.write_json(self.state / (name + '.json'), item)
        return item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp', type=Path)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ModelTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    parser.error('--reuse-esp is required') if args.reuse_esp is None else None
    esp = args.reuse_esp.resolve()
    state = ROOT / 'build/test/p7-transitions/qemu' / ('run-' + uuid.uuid4().hex[:12])
    state.mkdir(parents=True)
    inputs = {str(ROOT / p): sha(ROOT / p) for p in
              ('tests/run_desktop_transition_qemu.py', 'tests/run_desktop_settings_qemu.py',
               'tests/run_desktop_qemu.py', 'tests/desktop_preferences_oracle.py')}
    description = json.loads((esp.parent / 'build-inputs.json').read_text())
    sources = description['source_sha256']
    def unchanged():
        return all(sha(p) == v for p, v in inputs.items()) and all(sha(ROOT / p) == v for p, v in sources.items())
    result = dict(passed=False, runner_inputs=inputs, boots=[])
    guest = None
    try:
        check(description['runtime_level'] == 7 and description['source_unchanged'] and unchanged(), 'build/source identity differs')
        for p, v in description['artifacts'].items():
            check(sha(Path(p) if Path(p).is_absolute() else esp.parent / p) == v, 'build artifact changed')
        disk = state / 'durable.img'
        create(disk, 64)
        guest = TransitionGuest(esp, disk, state / 'interactive')
        result['boots'].append(str(guest.state))
        guest.verify_state('default', 256, DARK, 0)
        guest.verify_scene('initial-settled')
        guest.focus(2)
        for key in ('a', 'b', 'c'):
            guest.key(key)
        guest.key('ctrl', 's')
        guest.wait(b'DONGOS_EDITOR_SAVED', 15)
        guest.settle_motion()
        editor = rect(guest.windows(), 2)
        guest.move(editor[2] - 16, editor[1] + 12)
        guest.button_async(True)
        hidden_mid = guest.capture_middle('hide-middle', 2, fade=True, show=False, clearance=6)
        check(hidden_mid['actual_alpha_changed_pixels'] >= 8 and hidden_mid['actual_scaled_texture_pixels'] >= 8,
              'hide did not expose real geometric/alpha GOP changes')
        guest.button_async(False)
        guest.move_async(435, guest.descriptor()[2] - 40)
        guest.button_async(True)
        hide_reversed = guest.capture_middle('hide-reversed-to-restore-middle', 2, fade=True, show=True)
        check(on_segment(hide_reversed['transitions'][2]['from_rect'], hidden_mid['visual_rects'][2],
                         hidden_mid['transitions'][2]['to_rect']), 'hide reversal jumped away from its rendered path')
        check(hide_reversed['actual_alpha_changed_pixels'] >= 8 and hide_reversed['actual_scaled_texture_pixels'] >= 8,
              'visibility reversal skipped real alpha/geometry pixels')
        guest.button(False)
        guest.settle_motion()
        guest.verify_scene('reversed-restore-endpoint')
        editor = rect(guest.windows(), 2)
        guest.move(editor[2] - 16, editor[1] + 12)
        guest.button_async(True)
        guest.capture_middle('hide-final-middle', 2, fade=True, show=False)
        guest.button(False)
        guest.settle_motion()
        check(not struct.unpack_from('<Q', guest.windows(), 2 * 144 + 136)[0] & 1, 'title close did not hide editor')
        check(guest.progress()['PRESENTED_ALPHA'][2] == 0, 'hidden endpoint retained nonzero alpha')
        guest.verify_scene('hidden-endpoint')
        guest.move(435, guest.descriptor()[2] - 40)
        guest.button_async(True)
        restored = guest.capture_middle('restore-middle', 2, fade=True, show=True)
        check(restored['actual_alpha_changed_pixels'] >= 8 and restored['actual_scaled_texture_pixels'] >= 8,
              'restore did not expose real geometric/alpha GOP changes')
        guest.button(False)
        guest.settle_motion()
        guest.verify_scene('restored-endpoint')
        guest.focus(3)
        before = guest.windows()
        revision = guest.value('STYLE_REVISION')
        frames = guest.kval('user.memory', 'FRAME_COUNT')
        tables = guest.kernel(guest.ksym('user.memory', 'META'), 5 * 32, 'initial private page-table usage')
        guest.key_async('equal')
        first = guest.capture_middle('dpi-125-middle', 3, revision=revision + 1)
        check(first['actual_scaled_texture_pixels'] >= 8, 'DPI used alpha-only transition')
        guest.key_async('equal')
        second = guest.capture_middle('dpi-150-interrupted-middle', 3, revision=revision + 2)
        for i in range(4):
            check(on_segment(second['transitions'][i]['from_rect'], first['visual_rects'][i], first['transitions'][i]['to_rect']),
                  'second DPI jump restarted away from the current visual path')
        guest.key_async('minus')
        reverse = guest.capture_middle('dpi-125-reversed-middle', 3, revision=revision + 3)
        for i in range(4):
            check(on_segment(reverse['transitions'][i]['from_rect'], second['visual_rects'][i], second['transitions'][i]['to_rect']),
                  'DPI reversal restarted away from the current visual path')
        guest.settle_motion()
        after = guest.windows()
        check(before[2304:2448] == after[2304:2448], 'DPI animation changed focus/order/count')
        for i in range(4):
            check(before[i * 144:i * 144 + 40] == after[i * 144:i * 144 + 40]
                  and before[i * 144 + 136:i * 144 + 144] == after[i * 144 + 136:i * 144 + 144],
                  'DPI animation changed window ownership or visibility')
        check(guest.kval('user.memory', 'FRAME_COUNT') == frames, 'geometry animation allocated RAM')
        check(guest.kernel(guest.ksym('user.memory', 'META'), 5 * 32, 'final private page-table usage') == tables,
              'geometry animation allocated private tables')
        guest.verify_state('dpi-125-settled', 320, DARK, 0, b'abc')
        guest.verify_scene('dpi-125-settled-exact')
        # Start another transition; an actual title press must cancel motion of
        # that window and real drag must follow target-DPI title hit testing.
        guest.key_async('equal')
        interrupted = guest.capture_middle('dpi-150-before-pointer', 3, revision=revision + 4)
        scale = 384
        r = interrupted['target_rects'][3]
        # An ordinary pointer move may advance the transition normally. The
        # following press must replace the track with a zero-duration endpoint,
        # which distinguishes cancellation from simply waiting for completion.
        guest.move_async(r[0] + 90, r[1] + 40)
        guest.button_async(True)
        guest.capture_pointer_cancel('pointer-cancel-published', 3)
        guest.settle_motion()
        check(guest.progress()['PRESENTED_RECTS'][3] == rect(guest.windows(), 3), 'title press did not snap visual to target')
        check(not guest.progress()['MOTION_ACTIVE'] & 8, 'title press retained geometric capture')
        r = rect(guest.windows(), 3)
        guest.move(r[0] + 75, r[1] + 35)
        guest.button(False)
        check(rect(guest.windows(), 3) == tuple(v + delta for v, delta in zip(r, (-15, -5, -15, -5))), 'pointer interruption broke scaled title drag')
        guest.verify_state('pointer-interrupted', scale, DARK, 0, b'abc')
        guest.verify_scene('pointer-interrupted-exact')
        # A hidden window keeps its lifecycle and remains transparent while the
        # other windows transition between DPI settings.
        guest.focus(2)
        r = rect(guest.windows(), 2)
        px = lambda v: (v * scale + 128) // 256
        guest.move(r[2] - px(16), r[1] + px(12))
        guest.button(True)
        guest.button(False)
        guest.settle_motion()
        guest.focus(3)
        hidden_flags = struct.unpack_from('<Q', guest.windows(), 2 * 144 + 136)[0]
        hidden_revision = guest.value('STYLE_REVISION')
        guest.key_async('equal')
        hidden_dpi = guest.capture_middle('dpi-175-hidden-editor', 3, revision=hidden_revision + 1)
        check(hidden_dpi['presented_alpha'][2] == 0 and not hidden_flags & 1, 'hidden editor reappeared during DPI')
        guest.settle_motion()
        check(struct.unpack_from('<Q', guest.windows(), 2 * 144 + 136)[0] == hidden_flags, 'hidden window flags changed')
        guest.verify_state('dpi-175-hidden-settled', 448, DARK, 0, b'abc')
        guest.key('t')
        guest.settle_motion()
        guest.key('s')
        guest.verify_state('saved-light175', 448, LIGHT, 1, b'abc')
        guest.close()
        guest = None
        result['editor_disk'] = storage.check_disk(disk, raw_name=b'NOTE    TXT', payload=b'abc')
        saved = disk_oracle.inspect_disk(disk)
        check(saved['selection']['slot'] == 0 and saved['slots'][0]['record']['sequence'] == 1, 'final saved slot differs')
        check(bytes.fromhex(saved['slots'][0]['record_hex'])[32:104] == theme_bytes(LIGHT, 448), 'final disk theme differs')
        storage.write_json(state / 'saved-disk.json', saved)
        digest = sha(disk)
        guest = TransitionGuest(esp, disk, state / 'same-disk-reboot')
        result['boots'].append(str(guest.state))
        guest.verify_state('persisted-light175', 448, LIGHT, 1)
        guest.verify_scene('persisted-settled-exact')
        check(b'DONGOS_P7_SETTINGS_LOADED' in guest.raw, 'saved scale/theme not loaded on reboot')
        guest.close()
        guest = None
        check(sha(disk) == digest, 'transition startup rewrote configuration')
        result.update(passed=True, actual_qemu_boots=2, independent_gop_geometry_alpha_oracle=True,
                      hide_restore_zoom_verified=True, runtime_dpi_interruption_reversal_verified=True,
                      pointer_interrupt_and_scaled_drag_verified=True, hidden_dpi_window_preserved=True,
                      all_elf_executable_bytes_verified=True, theme_same_disk_reboot_verified=True,
                      focus_window_ownership_and_editor_content_preserved=True)
    except Exception as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if guest:
            guest.close()
        result['source_unchanged'] = unchanged()
        if not result['source_unchanged']:
            result.update(passed=False, error='source changed during verification')
        storage.write_json(state / 'result.json', result)
    print('P7 transitions', 'PASS' if result['passed'] else 'FAIL', state, result.get('error', ''), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
