#!/usr/bin/env python3
"""Strict Linux/KVM loader-to-interactive-shell timing gate.

Uses a completed, normal runtime7 build. Never builds, changes guest memory,
falls back to TCG, or proves init-owned cross-AP startup. Run separately from
startup observation: no pause is issued until shell AND clients are ready.
The 500ms limit is the conservative guest-TSC interval, not host/firmware time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests import boot_trace_capture
from tests import run_clock_calibration_qemu as clock
from tools import build as builder
from tools.elf_image import materialize
from tools.elf_symbols import read_elf_symbols
from tools.make_fat32_disk import create
from tools.mkimage import HEADER_SIZE, lz4_decode, parse_header

ROOT = builder.ROOT
TREES = ('kernel', 'services', 'boot', 'include', 'lang/dongc',
         'lang/std', 'lang/examples', 'tools', 'assets/fonts')
SUFFIXES = ('.dg', '.asm', '.inc', '.ld', '.py', '.dgfont', '.txt')
MARKERS = (b'DONGOS_SHELL_READY\r\n', b'DONGOS_P7_CLIENTS_READY\r\n')
LIMIT_NS = 500_000_000
check, write = clock.check, clock.write


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ordinary(path):
    """Reject symlink redirection in every existing component."""
    path = Path(path).absolute()
    check(not any(p.is_symlink() for p in (path, *path.parents)),
          'symlink in input path: ' + str(path))
    check(path.is_file(), 'missing ordinary file: ' + str(path))
    return path.resolve()


def source_fingerprints(root):
    root = Path(root).resolve()
    paths = []
    for tree in TREES:
        base = root / tree
        check(base.is_dir() and not base.is_symlink(), 'source tree missing: ' + tree)
        for path in base.rglob('*'):
            check(not path.is_symlink(), 'symlink in source inventory: ' + str(path))
            if path.is_file() and path.suffix in SUFFIXES:
                paths.append(path)
    check(paths, 'empty current source inventory')
    return {p.relative_to(root).as_posix(): sha(ordinary(p)) for p in sorted(paths)}


def verify_build(esp, root=None):
    """Recompute, do not trust the producer's list of files to be checked."""
    root = ROOT if root is None else Path(root)
    esp = Path(esp).absolute()
    check(esp.is_dir() and not any(p.is_symlink() for p in (esp, *esp.parents)),
          'ordinary completed ESP required')
    esp = esp.resolve()
    output = esp.parent
    receipt = ordinary(output / 'build-inputs.json')
    metadata = json.loads(receipt.read_text(encoding='utf-8'))
    wanted = dict(runtime_level=7, test=False, graphics_case=None, smp_case=None,
                  kernel_mode='release', source_unchanged=True)
    for name, value in wanted.items():
        check(type(metadata.get(name)) is type(value) and metadata.get(name) == value,
              'normal build flag differs: ' + name)
    sources = source_fingerprints(root)
    check(metadata.get('source_sha256') == sources, 'complete current source inventory differs')
    expected = {ordinary(path) for path in (
        output / 'kernel.bin', output / 'kernel.elf', esp / 'DONGOS.IMG',
        esp / 'EFI/BOOT/BOOTX64.EFI', esp / 'SERVICES.BIN')}
    artifacts = metadata.get('artifacts')
    check(isinstance(artifacts, dict) and len(artifacts) == len(expected),
          'exact five build artifacts required')
    actual = {}
    for name, digest in artifacts.items():
        check(isinstance(name, str) and isinstance(digest, str)
              and re.fullmatch('[0-9a-f]{64}', digest), 'invalid artifact receipt')
        path = Path(name)
        check('..' not in path.parts, 'artifact traversal')
        path = ordinary(path if path.is_absolute() else output / path)
        check(path in expected and path not in actual, 'artifact escaped requested ESP or duplicated')
        check(sha(path) == digest, 'build artifact changed: ' + str(path))
        actual[path] = digest
    check(set(actual) == expected, 'requested ESP artifact missing')
    kernel = (output / 'kernel.bin').read_bytes()
    check(materialize((output / 'kernel.elf').read_bytes()) == kernel,
          'kernel ELF and raw image differ')
    image = (esp / 'DONGOS.IMG').read_bytes()
    _, length = parse_header(image)
    check(lz4_decode(image[HEADER_SIZE:], length) == kernel, 'boot image and kernel differ')
    return dict(esp=str(esp), build_input_sha256=sha(receipt),
                source_sha256=sources,
                artifact_sha256={str(p): actual[p] for p in sorted(actual)})


def preflight():
    check(sys.platform.startswith('linux'), 'P6 performance acceptance requires Linux')
    device = Path('/dev/kvm')
    check(device.exists() and stat.S_ISCHR(device.stat().st_mode),
          'Linux /dev/kvm character device is unavailable; no TCG fallback')
    check(os.access(device, os.R_OK | os.W_OK),
          'Linux /dev/kvm is not readable and writable; no TCG fallback')
    return dict(host_os='linux', kvm_device=str(device), device_accessible=True)


def require_kvm(value):
    check(isinstance(value, dict) and value.get('enabled') is True
          and value.get('present') is True,
          'actual QMP query-kvm must confirm enabled=true and present=true')
    return dict(enabled=True, present=True)


def command_for(esp, state, disk, uart_port, qmp_port):
    command = builder.qemu_command(esp, state / 'guest', test=True, accel='kvm')
    check(command.count('-accel') == 1 and command[command.index('-accel') + 1] == 'kvm'
          and command.count('-smp') == 1 and command[command.index('-smp') + 1] == '4',
          'owned command must use only KVM and exactly four CPUs')
    at = command.index('isa-debug-exit,iobase=0xf4,iosize=0x04')
    check(command[at - 1] == '-device', 'unexpected debug-exit command')
    del command[at - 1:at + 1]
    command[command.index('-serial') + 1] = f'tcp:127.0.0.1:{uart_port},server=on,wait=off'
    # Expose host-supported nonmigratable features, including invariant TSC
    # where available. Never invent a CPUID frequency or use a synthetic TSC.
    command += ['-cpu', 'host,migratable=off', '-S', '-qmp',
                f'tcp:127.0.0.1:{qmp_port},server=on,wait=off',
                '-drive', 'if=none,id=data,format=raw,cache=writeback,file='
                + disk.resolve().as_posix().replace(',', ',,'),
                '-device', 'virtio-blk-pci,drive=data,disable-legacy=on',
                '-device', 'virtio-tablet-pci']
    return command


def check_startup_failure(raw):
    check(b'PANIC' not in raw and b'DONGOS_P1_KERNEL_FAIL' not in raw
          and b'DONGOS_INIT_FAILURE ' not in raw,
          'guest startup failure; retain the failed run')


def timing_pass(decoded):
    check(decoded.get('kvm_gate_eligible') is True and decoded.get('invariant_tsc') is True,
          'captured trace is not eligible Linux/KVM invariant-TSC evidence')
    check(decoded.get('header', {}).get('online_mask') == 15, 'four online CPUs required')
    value = decoded.get('intervals', {}).get('loader_to_interactive_shell_upper_ns')
    check(type(value) is int and 0 < value <= LIMIT_NS,
          'loader-to-interactive-shell conservative bound exceeds 500ms')
    check(decoded.get('kvm_gate_passed') is True, 'independent trace decoder rejected timing')
    return value


class KvmGuest(clock.ClockGuest):
    def __init__(self, esp, state, timeout):
        super().__init__(esp, state, False, timeout, 7)
        self.evidence.update(init_cross_ap_proven=False, no_tcg_fallback=True,
                             pause_before_completion=False)

    def start(self):
        disk = self.state / 'disk.img'
        create(disk, 64)
        up, qp = clock.storage.free_port(), clock.storage.free_port()
        command = command_for(self.esp, self.state, disk, up, qp)
        self.evidence['command'] = command
        write(self.state / 'command.json', command)
        self.stderr = (self.state / 'stderr.log').open('wb')
        self.process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL,
                                        stderr=self.stderr)
        self.evidence['actual_qemu_executed'] = True
        self.evidence['pid'] = self.process.pid
        self.qmp = clock.acpi.QMP(qp, self.process)
        # This happens before the first cont, not after an already-run guest.
        query = self.qmp.request('query-kvm')
        write(self.state / 'query-kvm-before-cont.json', query)
        self.evidence['query_kvm_before_cont'] = require_kvm(query)
        check(self.qmp.request('query-status').get('running') is False,
              'guest ran before accelerator verification')
        self.uart = socket.create_connection(('127.0.0.1', up))
        self.uart.settimeout(.2)

        def read_uart():
            with (self.state / 'serial.log').open('wb') as stream:
                while self.process.poll() is None:
                    try:
                        data = self.uart.recv(4096)
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    if not data:
                        break
                    self.raw.extend(data)
                    stream.write(data)
                    stream.flush()
        self.reader = threading.Thread(target=read_uart, daemon=True)
        self.reader.start()
        self.qmp.request('cont')
        self.evidence['cont_issued_after_kvm_check'] = True
        self.evidence['actual_kvm_boots'] = 1
        deadline = time.monotonic() + self.timeout
        while not all(marker in self.raw for marker in MARKERS):
            check(self.process.poll() is None, 'KVM guest exited before readiness')
            check_startup_failure(self.raw)
            if time.monotonic() >= deadline:
                raise TimeoutError('shell and clients did not both become ready')
            time.sleep(.01)
        check_startup_failure(self.raw)
        check(all(bytes(self.raw).count(marker) == 1 for marker in MARKERS),
              'initial boot readiness markers must be unique')
        self.qmp.request('stop')
        check(self.qmp.request('query-status').get('running') is False,
              'guest did not stop for read-only trace capture')
        check_startup_failure(self.raw)
        self.evidence['stopped_for_capture'] = True
        self.symbols = read_elf_symbols(self.esp.parent / 'kernel.elf')
        matches = re.findall(rb'^memory_runtime_boot_info=0x([0-9a-f]{16})\r?$',
                             self.raw, re.MULTILINE)
        check(len(matches) == 1, 'one actual BootInfo publication required')
        address = int(matches[0], 16) - clock.acpi.HHDM
        self.boot = struct.unpack('<20Q', self.physical(address, 160, 'actual BootInfo'))
        check(self.boot[15] > 0 and self.boot[15] % 4096 == 0, 'invalid kernel physical base')

    def capture_failure(self):
        """Best-effort raw diagnostic capture; cannot turn failure into PASS."""
        diagnostic = {}
        if self.qmp is None or self.process is None or self.process.poll() is not None:
            return diagnostic
        for name, command, args in (
                ('stop', 'stop', None), ('status', 'query-status', None),
                ('kvm', 'query-kvm', None),
                *((f'cpu-{cpu}', 'human-monitor-command',
                   {'command-line': 'info registers', 'cpu-index': cpu}) for cpu in range(4))):
            try:
                diagnostic[name] = self.qmp.request(command, args) if args else self.qmp.request(command)
            except Exception as exc:
                diagnostic[name] = type(exc).__name__ + ': ' + str(exc)
        write(self.state / 'failure-diagnostics.json', diagnostic)
        return diagnostic

    def close(self):
        """A failed diagnostic/connection close must not leak our QEMU."""
        errors = []

        def attempt(label, action):
            try:
                action()
            except Exception as exc:
                errors.append(label + ': ' + type(exc).__name__ + ': ' + str(exc))
        if self.qmp:
            # A process which already exited can legitimately reject quit.
            attempt('quit', lambda: self.qmp.request('quit'))
            attempt('qmp close', self.qmp.close)
        if self.uart:
            attempt('uart close', self.uart.close)
        if self.process:
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                attempt('kill', self.process.kill)
                attempt('wait after kill', lambda: self.process.wait(timeout=5))
            except Exception as exc:
                errors.append('wait: ' + str(exc))
                if self.process.poll() is None:
                    attempt('kill', self.process.kill)
                    attempt('wait after kill', lambda: self.process.wait(timeout=5))
            self.evidence['qemu_shutdown_returncode'] = self.process.poll()
        if self.reader:
            attempt('reader join', lambda: self.reader.join(timeout=2))
        if self.stderr:
            attempt('stderr close', self.stderr.close)
        self.evidence['cleanup_diagnostics'] = errors
        write(self.state / 'physical-manifest.json', self.chunks)
        check(self.process is None or self.process.poll() is not None,
              'owned QEMU is still running after cleanup')


def runner_fingerprints():
    # All currently imported local Python dependencies, including this runner.
    paths = {Path(__file__).resolve()}
    for module in list(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.suffix == '.py' and path.is_relative_to(ROOT.resolve()):
                paths.add(path)
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths)}


def run(esp, state, timeout, preflight_only=False):
    check(math.isfinite(timeout) and 1 <= timeout <= 300, 'timeout must be 1..300 seconds')
    state = Path(state)
    state.mkdir(parents=True, exist_ok=False)
    result = dict(passed=False, actual_qemu_executed=False, actual_kvm_boots=0,
                  init_cross_ap_proven=False, full_build_executed=False,
                  timing_limit_ns=LIMIT_NS, preflight_only=preflight_only,
                  all_started_guests_stopped=True)
    guest, binding = None, None
    before = runner_fingerprints()
    write(state / 'runner-source-before.json', before)
    try:
        result['preflight'] = preflight()
        binding = verify_build(esp)
        result['build_binding'] = binding
        if preflight_only:
            result['preflight_passed'] = True
        else:
            guest = KvmGuest(Path(binding['esp']), state, timeout)
            guest.start()
            result['trace'] = boot_trace_capture.capture(guest, state / 'trace')
            check_startup_failure(guest.raw)
            result['loader_to_shell_upper_ns'] = timing_pass(result['trace'])
            result['actual_kvm_boots'] = 1
            result['passed'] = True
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
        if guest:
            try:
                guest.capture_failure()
            except Exception as diagnostic_error:
                result['diagnostic_error'] = str(diagnostic_error)
    finally:
        if guest:
            try:
                guest.close()
            except Exception as exc:
                result.update(passed=False, cleanup_error=type(exc).__name__ + ': ' + str(exc))
            result['guest'] = guest.evidence
            result['actual_qemu_executed'] = guest.evidence['actual_qemu_executed']
            result['actual_kvm_boots'] = guest.evidence.get('actual_kvm_boots', 0)
            result['all_started_guests_stopped'] = guest.process is None or guest.process.poll() is not None
            if not result['all_started_guests_stopped']:
                result['passed'] = False
        try:
            after = runner_fingerprints()
            write(state / 'runner-source-after.json', after)
            check(before == after, 'runner dependency inputs changed')
            if binding is not None:
                check(verify_build(esp) == binding, 'source or requested build changed during KVM run')
            result['inputs_unchanged'] = True
        except Exception as exc:
            result.update(passed=False, inputs_unchanged=False,
                          input_error=type(exc).__name__ + ': ' + str(exc))
        write(state / 'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    state = args.output or ROOT / 'build/test/p6-kvm/qemu' / ('run-' + uuid.uuid4().hex[:12])
    result = run(args.reuse_esp, state, args.timeout, args.preflight_only)
    print(json.dumps(dict(result=str(state / 'result.json'), passed=result['passed'],
                          preflight_passed=result.get('preflight_passed', False),
                          error=result.get('error')), indent=2))
    return 0 if (result['passed'] or
                 args.preflight_only and result.get('preflight_passed')
                 and result.get('inputs_unchanged')) else 1


if __name__ == '__main__':
    raise SystemExit(main())
