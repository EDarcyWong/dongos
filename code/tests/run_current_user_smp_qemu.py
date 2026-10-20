#!/usr/bin/env python3
"""Current-source identity/planning and read-only observation helpers.

New implementation, not recovered historical runner. CLI never starts a guest;
there is deliberately no --execute switch. ProcessGuest adapters reuse existing
physical/ELF verification infrastructure for separately authorized future use.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests import run_process_lifecycle_qemu as life
from tests import user_smp_oracle as oracle
from tests import current_user_smp_acceptance as acceptance
from tools.elf_symbols import read_elf_symbols

ROOT = BASE = Path(__file__).resolve().parents[1]
NAMES = life.NAMES
storage, settings = life.storage, life.settings
check = oracle.check


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative_file(root, name):
    check(isinstance(name, str) and name and not Path(name).is_absolute() and
          '..' not in Path(name).parts, 'unsafe receipt path')
    path = root / name
    check(path.resolve().is_relative_to(root.resolve()) and path.is_file() and not path.is_symlink(),
          'missing or escaped receipt file: ' + name)
    return path


def verify_hashes(root, values, label):
    check(isinstance(values, dict) and bool(values), label + ' manifest empty')
    for name, expected in values.items():
        check(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'invalid SHA-256')
        check(sha(relative_file(root, name)) == expected, label + ' changed: ' + name)


def identity(esp, negative=False):
    esp = Path(esp).resolve()
    check(esp.is_dir(), 'completed ESP directory required')
    output = esp.parent
    try:
        record = json.loads((output / 'current-user-smp-source.json').read_text())
        metadata = json.loads((output / 'build-inputs.json').read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('completed current source receipt required') from exc
    check(record.get('schema') == 1 and record.get('contract') == 'current-user-smp-v1', 'unknown current receipt contract')
    check(record.get('user_case') == ('omit-xstate' if negative else None),
          'negative experiment must be explicitly selected')
    for name, value in {'built': True, 'source_unchanged': True, 'test': True,
                        'runtime_level': 7, 'user_smp': True, 'user_workload': True}.items():
        check(type(record.get(name)) is type(value) and record.get(name) == value,
              'completed source receipt flag differs: ' + name)
    check(Path(record['source_root']).is_absolute() and Path(record['source_root']).resolve() == BASE.resolve(),
          'receipt source root is not the verified source root')
    check(record.get('esp') == str(esp), 'receipt ESP differs')
    for name in ('test', 'runtime_level', 'source_unchanged'):
        check(type(metadata.get(name)) is type(record[name]) and metadata[name] == record[name], 'build receipt flags disagree')
    check(metadata.get('graphics_case') is None, 'graphics fault injection not allowed')
    check(metadata.get('source_sha256') == record['source_sha256'], 'build/source graph manifests disagree')
    verify_hashes(BASE, record['source_sha256'], 'current builder/workload/include')
    check(all(name.startswith('kernel/') for name in record['staged_kernel_sha256']), 'staged kernel path invalid')
    verify_hashes(output / 'source', record['staged_kernel_sha256'], 'staged kernel')
    artifacts = metadata.get('artifacts', {})
    verify_hashes(output, artifacts, 'artifact')
    check(artifacts.get('kernel.elf') == record.get('kernel_elf_sha256') == sha(output / 'kernel.elf'),
          'kernel artifact changed or unbound')
    workloads = record['workload_elf_sha256']
    check(set(workloads) == set(NAMES[7:12]), 'five workload ELF hashes required')
    for name, expected in workloads.items():
        path = 'services/' + name + '/program.elf'
        check(artifacts.get(path) == expected == sha(relative_file(output, path)), 'workload artifact changed or unbound')
    return record


class UserGuest(life.ProcessGuest):
    def hmp(self, cpu, command):
        check(type(cpu) is int and 0 <= cpu < 16, 'invalid CPU index')
        return self.qmp.request('human-monitor-command', {'command-line': command, 'cpu-index': cpu})

    def read(self, address, length):
        return self.kernel(address, length, 'current SMP trusted kernel observation')

    def readwords(self, address, count):
        return oracle.words(self.read(address, count * 8), count)

    def effective(self, root, virtual):
        entry = self.pte(root, virtual)
        return dict(present=bool(entry & 1), effective_user=bool(entry & 4),
                    effective_nx=bool(entry & (1 << 63)), physical=(entry & storage.MASK) + (virtual & 4095))

    def worker(self, cfg, argument, snapshot):
        check(cfg in acceptance.ARGS and argument == acceptance.ARGS[cfg], 'unknown worker/argument')
        catalog = self.catalog()
        slot = catalog['slots'][cfg]
        check(type(slot) is int and 0 <= slot < 16, 'invalid worker slot')
        incarnation = catalog['incarnations'][slot]
        token = catalog['snapshots'][cfg]['process']
        check(token == (incarnation << 8) | (slot + 1), 'catalog worker token differs')
        process = self.verify_process(slot, NAMES[cfg])
        owned = oracle.words(struct.pack('<7Q', *snapshot['processes'][slot]), 7)
        check(owned[0] == token and owned[1] == incarnation and owned[2] == process['root'], 'worker private domain ownership differs')
        symbols = read_elf_symbols(self.esp.parent / 'services' / NAMES[cfg] / 'program.elf')
        address = process['bias'] + symbols[storage.symbol('apps.user_smp_worker', 'PROBE')]
        probe = oracle.words(self.user(slot, address, 192, 'current worker probe'), 24)
        apics = [context[2] for context in snapshot['contexts']]
        oracle.worker(probe, argument, slot + 1, cfg, incarnation, apics)
        acceptance.avx(snapshot)
        check(probe[7] == 1, 'actual upper-YMM worker path required')
        raw = self.read(owned[4], 1024)
        oracle.xstate(raw, argument, slot + 1, True)
        # Fixed-VA private page is the independent translation-isolation word.
        # Current services.channels() publishes the argument read-only here.
        mapping = self.effective(process['root'], 0x44000000)
        check(mapping['present'] and mapping['effective_user'] and mapping['effective_nx'], 'fixed-VA permissions differ')
        check(struct.unpack('<Q', self.physical(mapping['physical'], 8, 'worker fixed-VA word'))[0] == argument,
              'fixed-VA argument differs')
        return dict(cfg=cfg, slot=slot, token=token, incarnation=incarnation, probe=probe,
                    root=process['root'], argument=argument, physical=mapping['physical'],
                    actual_upper_ymm_verified=True)


def close_gui(guest):
    """Close ordinary GUI clients through the existing authenticated shell."""
    return [guest.shell('stop ' + name) for name in ('terminal', 'files', 'editor', 'settings')]


def negative(guest):
    close_gui(guest)
    initial = guest.catalog()
    life.check_boot_dag(initial)
    start = len(guest.raw)
    records = {}
    for cfg, arg in acceptance.ARGS.items():
        response = guest.shell('run ' + NAMES[cfg] + ' ' + str(arg))
        text = bytes.fromhex(response['response_hex']).decode('ascii')
        match = re.search(r'RUN OK ' + re.escape(NAMES[cfg]) + r' token=(\d+) generation=(\d+) state=(\d+) status=(\d+)', text)
        check(match is not None, 'missing actual SIMD launch receipt')
        records[cfg] = dict(zip(('token', 'generation', 'state', 'status'), map(int, match.groups())))
    deadline = time.monotonic() + 90
    while True:
        marker = bytes(guest.raw).find(b'DONGOS_P6_USER_WORKER_BAD', start)
        final = guest.catalog()
        snapshot = guest.snapshot()
        try:
            acceptance.negative_binding(final, records, initial['sequence'])
            acceptance.avx(snapshot)
            check(marker >= start and sum(v[2] for v in snapshot['metrics'][1:]) > 0,
                  'missing actual SIMD marker/AP timer')
            counts = acceptance.service_counts(guest)
            return dict(snapshot=snapshot, catalog=final, launched_workers=records,
                        catalog_start_sequence=initial['sequence'], serial_marker_offset=marker,
                        serial_start_offset=start, actual_negative_busy_simd_assertion=True,
                        actual_fault_status_6=True, actual_ap_user_timer=True, service_counts=counts)
        except ValueError as exc:
            if time.monotonic() >= deadline:
                raise ValueError('missing actual SIMD fresh token-bound #UD evidence') from exc
            time.sleep(.01)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp', type=Path, required=True)
    parser.add_argument('--negative-xstate', action='store_true')
    args = parser.parse_args()
    record = identity(args.reuse_esp, args.negative_xstate)
    print(json.dumps(dict(mode='identity-only', guest_started=False, historical_acceptance=False,
                          source_identity=record), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
