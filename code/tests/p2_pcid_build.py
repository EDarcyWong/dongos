"""Fresh, explicit P2 PCID workload build; importing/preparing never boots a VM."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import struct
import sys
from tools.kernel_storage_profile import verify_profile

ROOT = Path(__file__).resolve().parents[1]
TREES = ('kernel', 'services', 'include', 'lang', 'tools', 'boot', 'assets/fonts', 'tests')
SUFFIXES = {'.py', '.dg', '.asm', '.inc', '.ld', '.dgfont', '.txt'}
APPS = ('echo', 'fault', 'waiter', 'ipc_peer', 'fs_reader')
CASES = (None, 'wrong-tag')
CONTRACT = 'p2-pcid-current-build-v1'
SERVICES = {'block': 'drivers/block_service.dg', 'fs': 'fs/service.dg', 'shell': 'shell/main.dg',
            'compositor': 'desktop/service.dg', 'input': 'drivers/input_service.dg',
            'init': 'init/main.dg', 'devmgr': 'drivers/device_manager.dg',
            'echo': 'apps/echo.dg', 'fault': 'apps/fault.dg', 'waiter': 'apps/waiter.dg',
            'ipc-peer': 'apps/ipc_peer.dg', 'fs-reader': 'apps/fs_reader.dg',
            'xhci': 'drivers/xhci_service.dg', 'terminal': 'apps/gui_terminal.dg',
            'files': 'apps/gui_files.dg', 'editor': 'apps/gui_editor.dg', 'settings': 'apps/gui_settings.dg'}
ARTIFACT_SUFFIXES = {'.elf', '.bin', '.BIN', '.IMG', '.EFI', '.json', '.asm', '.inc', '.o', '.dg'}
PRODUCTION_ARTIFACTS = ('kernel.bin', 'kernel.elf', 'esp/DONGOS.IMG', 'esp/EFI/BOOT/BOOTX64.EFI',
                        'esp/SERVICES.BIN', 'kernel-optimization.json', 'kernel-profile-src/build/storage_profile.dg')
TOOL_VARIABLES = {'nasm': 'NASM', 'ld.lld': 'LD_LLD', 'lld-link': 'LLD_LINK'}


def required_artifacts():
    return set(PRODUCTION_ARTIFACTS) | {'dong_layout.json', 'build-inputs.json', 'dong_probe.asm',
                                      'source-before.json', 'source-after.json'} | {
        'services/' + name + '/' + leaf for name in SERVICES for leaf in ('program.elf', 'program.asm', 'build.json')}


def artifacts(target):
    return {p.relative_to(target).as_posix(): sha(p) for p in sorted(Path(target).rglob('*'))
            if p.is_file() and p.suffix in ARTIFACT_SUFFIXES}


def resolve_tools():
    from tools.build import find_tool
    paths = {'python': sys.executable}
    paths.update({name: find_tool(name, variable) for name, variable in TOOL_VARIABLES.items()})
    return {role: dict(path=str(Path(path).resolve()), sha256=sha(path)) for role, path in paths.items()}


def command_spec(output, roles):
    output = Path(output).resolve()
    script = ('from pathlib import Path; from tools.build import build; '
              'build(stage="p1",runtime_level=7,test=True,output=Path(' + repr(str(output / 'image')) + '))')
    overrides = {variable: roles[name]['path'] for name, variable in TOOL_VARIABLES.items()}
    overrides.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
    return dict(argv=[roles['python']['path'], '-B', '-c', script], cwd=str(output / 'source'),
                environment_overrides=overrides,
                environment_removed=['PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONINSPECT'])


def verify_command(output, record):
    path = file_at(output, 'build-command.json')
    check(sha(path) == record.get('build_command_sha256'), 'build command hash changed')
    spec = json.loads(path.read_text(encoding='utf-8'))
    check(spec == command_spec(output, record['build_tool_roles']), 'actual build command/cwd/environment differs')
    check(record.get('build_returncode') == 0, 'actual build exit status missing')
    log = file_at(output, 'build.log')
    check(log.stat().st_size > 0 and sha(log) == record.get('build_log_sha256'), 'build log changed/empty')


def verify_tools(record):
    roles = record.get('build_tool_roles')
    check(isinstance(roles, dict) and set(roles) == {'python', *TOOL_VARIABLES}, 'exact four compiler tool roles required')
    check(all(isinstance(item, dict) and set(item) == {'path', 'sha256'} for item in roles.values()),
          'compiler tool role shape differs')
    check(roles == resolve_tools(), 'actual compiler tool identity changed')
    check(record.get('build_tools_sha256') == {item['path']: item['sha256'] for item in roles.values()},
          'compiler tool hash set differs')


def verify_artifacts(target, record):
    bound = record.get('artifacts_sha256')
    check(isinstance(bound, dict) and required_artifacts() <= set(bound), 'required real build artifacts missing from receipt')
    verify_files(target, bound)
    check(artifacts(target) == bound, 'complete actual build artifact set differs')


def verify_production(output, record):
    output = Path(output).resolve()
    target, stage = output / 'image', output / 'source'
    path = file_at(target, 'build-inputs.json')
    check(sha(path) == record.get('production_manifest_sha256'), 'production manifest hash changed')
    production = json.loads(path.read_text(encoding='utf-8'))
    trees = ('kernel', 'services', 'boot', 'include', 'lang/dongc', 'lang/std', 'lang/examples', 'tools', 'assets/fonts')
    expected_source = {n: h for n, h in record['staged_sha256'].items()
                       if any(n.startswith(tree + '/') for tree in trees)}
    check(verify_profile(target, production, expected_runtime=7, source_root=stage) == 1,
          'current runtime7 requires exactly one static pool')
    profile = production['kernel_storage_profile']
    expected = dict(desktop_scale=100, runtime_level=7, kernel_mode='release', test=True,
                    graphics_case=None, smp_case=None, compiler_job=False, kernel_function_sections=True,
                    kernel_gc_sections=True, kernel_optimization=1, kernel_storage_profile=profile,
                    source_unchanged=True, source_sha256=expected_source,
                    artifacts={str((target / name).resolve()): sha(file_at(target, name)) for name in PRODUCTION_ARTIFACTS})
    check(production == expected, 'complete production manifest/profile/source/artifact mapping differs')
    for name in ('source-before.json', 'source-after.json'):
        check(json.loads(file_at(target, name).read_text(encoding='utf-8')) == expected_source,
              'actual production source boundary differs')
    from tools.elf_image import materialize
    from tools.mkimage import pack_image
    from tools.service_bundle import pack, inspect, ELF, DATA
    raw = materialize(file_at(target, 'kernel.elf').read_bytes())
    check(raw == file_at(target, 'kernel.bin').read_bytes(), 'actual kernel ELF/raw image differs')
    check(pack_image(raw) == file_at(target, 'esp/DONGOS.IMG').read_bytes(), 'actual packed kernel image differs')
    items = []
    for name, source in SERVICES.items():
        elf = file_at(target, 'services/' + name + '/program.elf')
        data = elf.read_bytes()
        check(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01'
              and struct.unpack_from('<HHI', data, 16) == (3, 62, 1), 'actual service PIE missing: ' + name)
        service = json.loads(file_at(target, 'services/' + name + '/build.json').read_text(encoding='utf-8'))
        check(service == dict(source=str(stage / 'services' / source), mode='release', elf=str(elf), byte_length=len(data)),
              'actual service source/ELF mapping differs: ' + name)
        items.append((name, ELF, data))
    items += [('font' + str(size), DATA, file_at(stage, 'assets/fonts/dong-cjk-sc-' + str(size) + '.dgfont').read_bytes())
              for size in (16, 20, 24, 28, 32)]
    items.append(('desktop-config', DATA, (256).to_bytes(8, 'little')))
    bundle = file_at(target, 'esp/SERVICES.BIN').read_bytes()
    inspect(bundle)
    check(pack(items) == bundle, 'actual bundle does not contain the exact seventeen linked services/assets')


def verify_completed(output, record):
    output = Path(output).resolve()
    check(record.get('built') is True and record.get('os_link_executed') is True
          and record.get('source_unchanged') is True and record.get('esp') == str(output / 'image/esp'),
          'completed real PCID build required')
    verify_artifacts(output / 'image', record)
    verify_tools(record)
    verify_command(output, record)
    verify_production(output, record)
    return record


def check(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def inputs(root=ROOT):
    root = Path(root)
    return {p.relative_to(root).as_posix(): sha(p)
            for tree in TREES for p in sorted((root / tree).rglob('*'))
            if p.is_file() and p.suffix in SUFFIXES and '__pycache__' not in p.parts}


def file_at(root, name):
    check(isinstance(name, str) and name and not Path(name).is_absolute()
          and '..' not in Path(name).parts, 'unsafe relative input')
    path = Path(root) / name
    check(path.resolve().is_relative_to(Path(root).resolve()) and path.is_file()
          and not path.is_symlink(), 'missing/escaped ordinary input: ' + name)
    return path


def verify_files(root, hashes):
    check(isinstance(hashes, dict) and bool(hashes), 'empty source/artifact manifest')
    for name, expected in hashes.items():
        check(sha(file_at(root, name)) == expected, 'input changed: ' + name)


def wrong_tag_source(data):
    old = b'    or rdi,rsi\n' if b'    or rdi,rsi\n' in data else b'    or rdi,rsi\r\n'
    check(data.count(old) == 1, 'actual PCID tag mutation anchor changed')
    nl = b'\r\n' if old.endswith(b'\r\n') else b'\n'
    # Slot11/tag12 is unused by the four initial GUI clients in this controlled
    # scenario. The runner must prove its actual current workload owner before
    # accepting this late, precisely observable hardware negative.
    lines = [b'    cmp rsi,12', b'    jne .p2_normal_tag', b'    or rdi,17',
             b'    jmp .p2_tag_ready', b'.p2_normal_tag:', b'    or rdi,rsi', b'.p2_tag_ready:']
    return data.replace(old, nl.join(lines) + nl)


def prepare(output, *, source_root=ROOT, case=None):
    """Copy real inputs and make an enumerated private test overlay, no tools."""
    check(case in CASES, 'unknown PCID mutation')
    output, source_root = Path(output).resolve(), Path(source_root).resolve()
    check(not output.exists(), 'fresh output directory required')
    before = inputs(source_root)
    check(bool(before), 'source graph missing')
    stage = output / 'source'
    stage.mkdir(parents=True)
    for name in before:
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source_root / name).read_bytes())
    check(inputs(source_root) == before and inputs(stage) == before, 'copy was not source-stable')
    worker = file_at(stage, 'tests/fixtures/current_user_smp/services/apps/user_smp_worker.dg').read_bytes()
    assembly = file_at(stage, 'tests/fixtures/current_user_smp/services/apps/user_smp_worker.asm').read_bytes()
    # Each independent PIE gets the same actual worker symbol. Appending its
    # real ASM to the private common bridge lets the unchanged production
    # build_service link it; other PIEs simply contain an unused worker body.
    changed = []
    check(worker.count(b'module apps.user_smp_worker;') == 1, 'worker module anchor changed')
    for name in APPS:
        relative = 'services/apps/' + name + '.dg'
        # The resolver requires the entry module to match its actual path.
        file_at(stage, relative).write_bytes(worker.replace(b'module apps.user_smp_worker;',
                                                           ('module apps.' + name + ';').encode()))
        changed.append(relative)
    bridge = file_at(stage, 'services/lib/syscalls.asm')
    bridge.write_bytes(bridge.read_bytes() + b'\n; P2 explicit synthetic workload body\n' + assembly)
    changed.append('services/lib/syscalls.asm')
    if case == 'wrong-tag':
        path = file_at(stage, 'kernel/sched/user_arch.asm')
        path.write_bytes(wrong_tag_source(path.read_bytes()))
        changed.append('kernel/sched/user_arch.asm')
    staged = inputs(stage)
    check(sorted(n for n in before if before[n] != staged[n]) == sorted(changed), 'unexpected overlay changes')
    record = dict(schema=1, contract=CONTRACT, case=case, source_root=str(source_root),
                  output=str(output), source_sha256=before, staged_sha256=staged,
                  overlay_paths=sorted(changed), synthetic_workload=True,
                  built=False, os_link_executed=False, guest_executed=False,
                  actual_qemu_executed=False)
    write(output / 'p2-pcid-source.json', record)
    return record


def verify_prepared(output, *, source_root=ROOT):
    output = Path(output).resolve()
    record = json.loads((output / 'p2-pcid-source.json').read_text(encoding='utf-8'))
    check(record['contract'] == CONTRACT and record['schema'] == 1, 'wrong PCID build contract')
    check(record['source_root'] == str(Path(source_root).resolve())
          and record['output'] == str(output), 'source/output redirection')
    verify_files(source_root, record['source_sha256'])
    check(inputs(source_root) == record['source_sha256'], 'source input set changed')
    verify_files(output / 'source', record['staged_sha256'])
    check(inputs(output / 'source') == record['staged_sha256'], 'staged input set changed')
    check(record['case'] in CASES and record['synthetic_workload'] is True, 'workload/case missing')
    source_root = Path(source_root)
    expected = dict(record['source_sha256'])
    changed = []
    worker = (source_root / 'tests/fixtures/current_user_smp/services/apps/user_smp_worker.dg').read_bytes()
    assembly = (source_root / 'tests/fixtures/current_user_smp/services/apps/user_smp_worker.asm').read_bytes()
    for app in APPS:
        name = 'services/apps/' + app + '.dg'
        check(worker.count(b'module apps.user_smp_worker;') == 1, 'worker module anchor changed')
        data = worker.replace(b'module apps.user_smp_worker;', ('module apps.' + app + ';').encode())
        expected[name] = hashlib.sha256(data).hexdigest()
        changed.append(name)
    name = 'services/lib/syscalls.asm'
    bridge = (source_root / name).read_bytes() + b'\n; P2 explicit synthetic workload body\n' + assembly
    expected[name] = hashlib.sha256(bridge).hexdigest()
    changed.append(name)
    if record['case'] == 'wrong-tag':
        name = 'kernel/sched/user_arch.asm'
        raw = (source_root / name).read_bytes()
        expected[name] = hashlib.sha256(wrong_tag_source(raw)).hexdigest()
        changed.append(name)
    check(record['staged_sha256'] == expected and record['overlay_paths'] == sorted(changed),
          'overlay is not the exact source-derived workload/mutation')
    return record


def build(output, *, source_root=ROOT, case=None):
    """Run the real frozen production builder in a fresh Python process."""
    record = prepare(output, source_root=source_root, case=case)
    output = Path(output).resolve()
    stage, target = output / 'source', output / 'image'
    env = os.environ.copy()
    try:
        roles = resolve_tools()
        spec = command_spec(output, roles)
        record['build_tool_roles'] = roles
        record['build_tools_sha256'] = {item['path']: item['sha256'] for item in roles.values()}
        for name in spec['environment_removed']:
            env.pop(name, None)
        env.update(spec['environment_overrides'])
        write(output / 'build-command.json', spec)
        record['build_command_sha256'] = sha(output / 'build-command.json')
        with (output / 'build.log').open('wb') as log:
            completed = subprocess.run(spec['argv'], cwd=stage, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, timeout=1800)
        record['build_returncode'] = completed.returncode
        record['build_log_sha256'] = sha(output / 'build.log')
        check(completed.returncode == 0, 'actual production build failed; see build.log')
        verify_prepared(output, source_root=source_root)
        record.update(built=True, os_link_executed=True, source_unchanged=True,
                      esp=str(target / 'esp'), artifacts_sha256=artifacts(target),
                      production_manifest_sha256=sha(target / 'build-inputs.json'))
        verify_completed(output, record)
    except BaseException as exc:
        record['built'] = False
        record['build_error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        if (output / 'build.log').is_file():
            record['build_log_sha256'] = sha(output / 'build.log')
        write(output / 'p2-pcid-source.json', record)
    return record


def identity(esp, *, source_root=ROOT):
    esp = Path(esp).resolve()
    output = esp.parent.parent
    record = verify_prepared(output, source_root=source_root)
    check(esp == output / 'image/esp', 'PCID ESP path differs')
    return verify_completed(output, record)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--build', action='store_true')
    p.add_argument('--case', choices=['wrong-tag'])
    a = p.parse_args(argv)
    result = build(a.output, case=a.case) if a.build else prepare(a.output, case=a.case)
    print(json.dumps(dict(output=result['output'], built=result['built'], guest_executed=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
