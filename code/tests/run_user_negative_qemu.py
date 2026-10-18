#!/usr/bin/env python3
"""Compile and execute a bad CPL3 peer; distinguish it from a build failure."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import build as builder

ROOT = builder.ROOT


def main():
    directory = ROOT / 'build/test/p4-user/bad-peer'
    directory.mkdir(parents=True, exist_ok=True)
    original = builder.assemble
    source = ROOT / 'services/init/ipc_server.asm'
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    hits = []
    def assemble(path, output, **kwargs):
        if path == source:
            text = source.read_text()
            needle = '    inc qword [rel message]\n'
            if text.count(needle) != 1:
                raise ValueError('bad peer mutation did not match exactly once')
            text = text.replace(needle, needle + '    inc qword [rel message + 8] ; actual bad peer payload\n')
            path = directory / 'ipc_server.asm'
            path.write_text(text)
            hits.append(1)
        return original(path, output, **kwargs)
    result = dict(passed=False, actual_qemu_executed=False, mutation_hits=0)
    try:
        with mock.patch.object(builder, 'assemble', side_effect=assemble):
            esp = builder.build(test=True, runtime_level=4, ipc_rounds=1000, output=directory / 'build')
        if hits != [1]:
            raise ValueError('bad peer source was not compiled exactly once')
        command = builder.qemu_command(esp, directory / 'guest', test=True) + ['-cpu', 'max,+smep,+smap,+umip']
        result.update(command=command, mutation_hits=len(hits), actual_qemu_executed=True)
        guest = subprocess.run(command, capture_output=True, timeout=30)
        (directory / 'stderr.txt').write_bytes(guest.stderr)
        serial = (directory / 'guest/serial.log').read_bytes()
        fields = {key.decode(): int(value,16) for key,value in re.findall(rb'^user_([a-z_]+)=0x([0-9a-f]{16})\r?$', serial, re.MULTILINE)}
        expected = dict(roundtrips=1, calls=1, replies=1, user_errors=1, rejections=5,
                        completed=0, error_code=0x04070004, last_syscall=254)
        if guest.returncode != 35 or any(fields.get(key) != value for key,value in expected.items()):
            raise ValueError('actual bad peer was not rejected after its first completed roundtrip')
        if b'DONGOS_P4_IPC_READY' in serial or b'DONGOS_P1_PASS' in serial:
            raise ValueError('bad peer incorrectly reached a success marker')
        if hashlib.sha256(source.read_bytes()).hexdigest() != before:
            raise ValueError('bad peer control changed the original source')
        result.update(passed=True, returncode=guest.returncode, actual_fields=fields,
                      source_unchanged=True, build_succeeded=True)
    except Exception as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
    (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('P4 actual bad peer', 'PASS' if result['passed'] else 'FAIL', result.get('error',''))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
