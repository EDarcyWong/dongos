"""Fresh current-source runtime7 build for the actual post-scheduler WB owner.

prepare() copies sources only. build() explicitly links the real OS but never
starts a VM. The private negative omits one AP flush only in this owner's
replacement post-barrier; startup and ordinary PCID paths remain identical.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tests import p2_pcid_build as base

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = 'p2-runtime-large-current-v1'
CASES = (None, 'omit-ap-flush')
check, sha, write, inputs, file_at, verify_files = base.check, base.sha, base.write, base.inputs, base.file_at, base.verify_files


def overlays(source_root, case):
    source_root = Path(source_root)
    worker = file_at(source_root, 'tests/fixtures/current_user_smp/services/apps/user_smp_worker.dg').read_bytes()
    assembly = file_at(source_root, 'tests/fixtures/current_user_smp/services/apps/user_smp_worker.asm').read_bytes()
    check(worker.count(b'module apps.user_smp_worker;') == 1, 'worker anchor changed')
    changes = {'services/apps/' + app + '.dg': worker.replace(b'module apps.user_smp_worker;',
        ('module apps.' + app + ';').encode()) for app in base.APPS}
    changes['services/lib/syscalls.asm'] = file_at(source_root, 'services/lib/syscalls.asm').read_bytes() + b'\n; P2 explicit synthetic workload body\n' + assembly
    if case:
        check(case == 'omit-ap-flush', 'unknown runtime-large negative')
        name = 'kernel/sched/runtime_large_reader.asm'
        raw = file_at(source_root, name).read_bytes()
        old = b'    xor eax,eax\n    ret\n%ifidn __OUTPUT_FORMAT__,elf64' if b'    xor eax,eax\n    ret\n%ifidn __OUTPUT_FORMAT__,elf64' in raw else b'    xor eax,eax\r\n    ret\r\n%ifidn __OUTPUT_FORMAT__,elf64'
        check(raw.count(old) == 1, 'one actual negative gate anchor required')
        nl = b'\r\n' if b'\r\n' in old else b'\n'
        new = nl.join([b'    xor eax,eax', b'    cmp rdi,1', b'    jne .done',
            b'    cmp qword [rel runtime_large_window_active],1', b'    sete al', b'.done:', b'    ret', b'%ifidn __OUTPUT_FORMAT__,elf64'])
        changes[name] = raw.replace(old, new)
        name = 'kernel/sched/user_arch.asm'
        raw = file_at(source_root, name).read_bytes()
        old = b'user_smp_arch_flush:\n' if b'user_smp_arch_flush:\n' in raw else b'user_smp_arch_flush:\r\n'
        check(raw.count(old) == 1, 'one actual all-tag flush boundary required')
        nl = b'\r\n' if old.endswith(b'\r\n') else b'\n'
        # Preserve rdi and SysV call alignment. No startup or unrelated user
        # switch is changed. AP logical1 only, and only the new window flag.
        insertion = nl.join([b'extern runtime_large_test_omit', b'user_smp_arch_flush:', b'    push rdi',
            b'    call runtime_large_test_omit', b'    pop rdi', b'    test rax,rax', b'    jz .actual_flush',
            b'    xor eax,eax', b'    ret', b'.actual_flush:', b''])
        changes[name] = raw.replace(old, insertion)
    return changes


def prepare(output, *, source_root=ROOT, case=None):
    check(case in CASES, 'unknown negative')
    output, source_root = Path(output).resolve(), Path(source_root).resolve()
    check(not output.exists(), 'fresh output required')
    before = inputs(source_root)
    check(bool(before), 'real source graph required')
    stage = output / 'source'
    stage.mkdir(parents=True)
    for name in before:
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(file_at(source_root, name).read_bytes())
    check(inputs(source_root) == inputs(stage) == before, 'copy changed inputs')
    changes = overlays(source_root, case)
    for name, raw in changes.items():
        file_at(stage, name).write_bytes(raw)
    record = dict(schema=1, contract=CONTRACT, source_root=str(source_root), output=str(output), case=case,
        source_sha256=before, staged_sha256=inputs(stage), overlay_paths=sorted(changes),
        synthetic_workload=True, built=False, os_link_executed=False, actual_guest_executed=False)
    write(output / 'runtime-large-source.json', record)
    return record


def verify_prepared(output, *, source_root=ROOT):
    output, source_root = Path(output).resolve(), Path(source_root).resolve()
    record = json.loads((output / 'runtime-large-source.json').read_text(encoding='utf-8'))
    check(record['schema'] == 1 and record['contract'] == CONTRACT and record['case'] in CASES, 'wrong build contract')
    check(record.get('synthetic_workload') is True and record.get('actual_guest_executed') is False, 'build receipt cannot claim guest execution')
    check(record['source_root'] == str(source_root) and record['output'] == str(output), 'source/output redirection')
    check(inputs(source_root) == record['source_sha256'], 'current source graph changed')
    expected = dict(record['source_sha256'])
    changes = overlays(source_root, record['case'])
    expected.update({name: hashlib.sha256(raw).hexdigest() for name, raw in changes.items()})
    check(record['overlay_paths'] == sorted(changes) and record['staged_sha256'] == expected, 'unlisted or forged source overlay')
    check(inputs(output / 'source') == expected, 'staged input set/bytes changed')
    verify_files(source_root, record['source_sha256'])
    verify_files(output / 'source', expected)
    return record


def build(output, *, source_root=ROOT, case=None):
    record = prepare(output, source_root=source_root, case=case)
    output = Path(output).resolve()
    stage, target = output / 'source', output / 'image'
    env = os.environ.copy()
    try:
        roles = base.resolve_tools()
        spec = base.command_spec(output, roles)
        record['build_tool_roles'] = roles
        record['build_tools_sha256'] = {value['path']: value['sha256'] for value in roles.values()}
        for name in spec['environment_removed']:
            env.pop(name, None)
        env.update(spec['environment_overrides'])
        write(output / 'build-command.json', spec)
        record['build_command_sha256'] = sha(output / 'build-command.json')
        with (output / 'build.log').open('wb') as log:
            completed = subprocess.run(spec['argv'], cwd=stage, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
        record['build_returncode'] = completed.returncode
        record['build_log_sha256'] = sha(output / 'build.log')
        check(completed.returncode == 0, 'actual current-source runtime7 build failed; see build.log')
        verify_prepared(output, source_root=source_root)
        check(0 < (target / 'kernel.bin').stat().st_size <= 2 * 1024 * 1024, '2MiB loader budget exceeded')
        record.update(built=True, os_link_executed=True, source_stable=True, source_unchanged=True,
            esp=str(target / 'esp'), artifacts_sha256=base.artifacts(target),
            production_manifest_sha256=sha(target / 'build-inputs.json'), kernel_bytes=(target / 'kernel.bin').stat().st_size)
        # Shared strict current-build verifier reconstructs all 17 service
        # ELFs/profile/bundle and ELF -> raw -> IMG, plus exact command/tools.
        base.verify_completed(output, record)
    except BaseException as exc:
        record.update(built=False, error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        if (output / 'build.log').is_file():
            record['build_log_sha256'] = sha(output / 'build.log')
        write(output / 'runtime-large-source.json', record)
    return record


def identity(esp, *, source_root=ROOT):
    esp = Path(esp).resolve()
    output = esp.parent.parent
    record = verify_prepared(output, source_root=source_root)
    check(record.get('source_stable') is True and record.get('esp') == str(esp)
          and esp == output / 'image/esp', 'completed actual build required')
    base.verify_completed(output, record)
    check(0 < (esp.parent / 'kernel.bin').stat().st_size <= 2 * 1024 * 1024, 'current kernel violates loader budget')
    check(record.get('kernel_bytes') == (esp.parent / 'kernel.bin').stat().st_size, 'recorded kernel size differs')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--case', choices=['omit-ap-flush'])
    args = parser.parse_args(argv)
    result = build(args.output, case=args.case) if args.build else prepare(args.output, case=args.case)
    print(json.dumps(dict(output=result['output'], built=result['built'], guest_executed=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
