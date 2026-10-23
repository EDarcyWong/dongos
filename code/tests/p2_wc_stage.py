"""Fresh private GOP benchmark overlay; preparation never builds or boots."""
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import os
import subprocess
import sys
from tools.kernel_storage_profile import verify_profile

ROOT = Path(__file__).resolve().parents[1]
TREES = ('kernel', 'services', 'boot', 'include', 'lang', 'tools', 'assets', 'tests', 'docs')
CONTRACT = 'p2-wc-current-overlay-v1'
PRODUCTION_TREES = ('kernel', 'services', 'boot', 'include', 'lang/dongc', 'lang/std', 'lang/examples', 'tools', 'assets/fonts')
PRODUCTION_SUFFIXES = {'.dg', '.asm', '.inc', '.ld', '.py', '.dgfont', '.txt'}
DG = 'kernel/smp/alias_memory.dg'
ASM = 'kernel/smp/alias_memory.asm'
IMPORT = 'import mm.cache_type_plan as cache;\n'
BEFORE = ''' var wb_bytes=display.framebuffer_size&~(7 as u64);if wb_bytes>bench.LIMIT{wb_bytes=bench.LIMIT;}
 if wb_bytes==0{return error.InvalidIntegration;}
 var wb_clock=bench_clock.EMPTY_REPORT;try bench_clock.describe(&wb_clock);
 let wb_backup=try allocate((wb_bytes+16) as usize);
 bench.REPORT=bench.Pair{version:1,phase:0,alias_report:(&REPORT) as u64,domain:DOMAIN as u64,
  count:(*DOMAIN).count as u64,gop_base:physical,gop_bytes:display.framebuffer_size,
  uc_pat:(*BOXES).pat,wc_pat:0,uc:bench.EMPTY,wc:bench.EMPTY};
 var wb_config=bench.Config{space:startup.space_pointer(),virtual:HHDM+physical,physical:physical,
  bytes:wb_bytes,tsc_hz:wb_clock.tsc_hz,flags:pg.WRITE|pg.UNCACHED,
  backup:wb_backup as *u8,capacity:(wb_bytes+16) as usize};
 try checked(bench.measure(&wb_config,&bench.REPORT.uc));bench.REPORT.phase=1;
'''
AFTER = ''' try all(1,0,0);bench.REPORT.wc_pat=(*BOXES).pat;
 wb_config.flags=pg.WRITE|pg.WRITE_COMBINING;
 try checked(bench.measure(&wb_config,&bench.REPORT.wc));bench.REPORT.phase=2;
'''
PRE = ' REPORT.phase=7;try checked(wc.bind(&config,CACHE));REPORT.phase=8;try checked(wc.execute_migration(CACHE));\n'
POST = ' try checked(wc.seal(CACHE));REPORT.wc_sealed=1;REPORT.pat_after=(*BOXES).pat;REPORT.phase=9;\n'


def check(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def inputs(root=ROOT):
    root = Path(root).resolve()
    return {p.relative_to(root).as_posix(): sha(p)
            for tree in TREES for p in sorted((root / tree).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'
            and ('build' not in p.relative_to(root).parts or p.relative_to(root).parts[:2] == ('kernel', 'build'))}


def ordinary(root, name):
    check(isinstance(name, str) and name and not Path(name).is_absolute()
          and '..' not in Path(name).parts, 'unsafe relative input')
    path = Path(root) / name
    check(path.is_file() and not path.is_symlink()
          and path.resolve().is_relative_to(Path(root).resolve()), 'missing/escaped input: ' + name)
    return path


def overlay(root):
    """Deterministic, reviewed edits to exactly two existing private files."""
    source = ordinary(root, DG).read_bytes()
    newline = b'\r\n' if b'\r\n' in source else b'\n'
    encode = lambda s: s.encode('utf-8').replace(b'\n', newline)
    replacement = source
    for anchor, added in ((IMPORT, IMPORT + 'import mm.wc_benchmark as bench;\nimport irq.platform as bench_clock;\n'),
                          (PRE, BEFORE + PRE), (POST, AFTER + POST)):
        check(replacement.count(encode(anchor)) == 1, 'unique WC sampling boundary required')
        replacement = replacement.replace(encode(anchor), encode(added), 1)
    hardware = ordinary(root, ASM).read_bytes()
    helper = ordinary(root, 'kernel/mm/wc_benchmark.asm').read_bytes()
    return {DG: replacement, ASM: hardware + b'\n; Explicit private WC benchmark helper\n' + helper}


def prepare(output, *, source_root=ROOT):
    output, source_root = Path(output).resolve(), Path(source_root).resolve()
    check(not output.exists() and all(not output.is_relative_to(source_root / tree) for tree in TREES),
          'fresh output outside all source input trees required')
    before = inputs(source_root)
    for required in (DG, ASM, 'kernel/mm/wc_benchmark.dg', 'kernel/mm/wc_benchmark.asm', 'tools/build.py'):
        check(required in before, 'complete actual source tree required: ' + required)
    stage = output / 'source'
    stage.mkdir(parents=True)
    for name in before:
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(ordinary(source_root, name).read_bytes())
    check(inputs(source_root) == before and inputs(stage) == before, 'copy not source-stable')
    edits = overlay(source_root)
    differences = []
    for name, data in edits.items():
        original = ordinary(stage, name).read_bytes()
        ordinary(stage, name).write_bytes(data)
        differences.extend(difflib.unified_diff(original.decode().splitlines(keepends=True),
                                              data.decode().splitlines(keepends=True), name, name + '.private'))
    (output / 'overlay.diff').write_text(''.join(differences), encoding='utf-8', newline='')
    staged = inputs(stage)
    check(set(staged) == set(before) and {n for n in before if before[n] != staged[n]} == set(edits), 'unexpected private edits')
    record = dict(schema=1, contract=CONTRACT, source_root=str(source_root), output=str(output),
                  source_sha256=before, staged_sha256=staged, overlay_paths=sorted(edits),
                  overlay_diff_sha256=sha(output / 'overlay.diff'), built=False,
                  os_link_executed=False, guest_executed=False, physical_wc_performance=False)
    write(output / 'wc-source.json', record)
    return record


def verify_prepared(output, *, source_root=ROOT):
    output, source_root = Path(output).resolve(), Path(source_root).resolve()
    record = json.loads((output / 'wc-source.json').read_text(encoding='utf-8'))
    check(record.get('schema') == 1 and record.get('contract') == CONTRACT
          and record.get('source_root') == str(source_root) and record.get('output') == str(output), 'source identity/redirection')
    current = inputs(source_root)
    check(current == record['source_sha256'], 'current source graph changed')
    expected = dict(current)
    differences = []
    for name, data in overlay(source_root).items():
        expected[name] = hashlib.sha256(data).hexdigest()
        differences.extend(difflib.unified_diff(ordinary(source_root, name).read_text().splitlines(keepends=True),
                                              data.decode().replace('\r\n', '\n').splitlines(keepends=True), name, name + '.private'))
    check(record['overlay_paths'] == sorted((DG, ASM)) and record['staged_sha256'] == expected
          and inputs(output / 'source') == expected, 'noncanonical or changed private source')
    check(sha(output / 'overlay.diff') == record['overlay_diff_sha256'], 'overlay diff changed')
    # Hash equality alone is insufficient: retain an exact, canonical diff.
    actual_diff = (output / 'overlay.diff').read_text(encoding='utf-8')
    check(actual_diff == ''.join(differences), 'overlay diff does not describe the exact transformation')
    return record


def tools_before():
    from tools.build import find_tool
    paths = dict(python=sys.executable, nasm=find_tool('nasm', 'NASM'),
                 ld_lld=find_tool('ld.lld', 'LD_LLD'), lld_link=find_tool('lld-link', 'LLD_LINK'))
    return {name: dict(path=str(Path(path).resolve()), sha256=sha(path)) for name, path in paths.items()}


def production_sources(staged):
    return {n: h for n, h in staged.items() if Path(n).suffix in PRODUCTION_SUFFIXES
            and any(n.startswith(t + '/') for t in PRODUCTION_TREES)}


def build(output, *, source_root=ROOT):
    record = prepare(output, source_root=source_root)
    output = Path(output).resolve()
    try:
        record['tools'] = tools_before()
        env = os.environ.copy()
        for key, variable in (('nasm', 'NASM'), ('ld_lld', 'LD_LLD'), ('lld_link', 'LLD_LINK')):
            env[variable] = record['tools'][key]['path']
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        target = output / 'image'
        script = ('from pathlib import Path; from tools.build import build; '
                  'build(stage="p1",runtime_level=7,test=True,output=Path(' + repr(str(target)) + '))')
        command = [sys.executable, '-B', '-c', script]
        write(output / 'build-command.json', dict(argv=command, cwd=str(output / 'source')))
        with (output / 'build.stdout').open('wb') as stdout, (output / 'build.stderr').open('wb') as stderr:
            completed = subprocess.run(command, cwd=output / 'source', env=env, stdout=stdout, stderr=stderr, timeout=1800)
        record['build_returncode'] = completed.returncode
        check(completed.returncode == 0, 'real runtime7 build failed')
        verify_prepared(output, source_root=source_root)
        manifest = json.loads((target / 'build-inputs.json').read_text())
        check(manifest['runtime_level'] == 7 and manifest['test'] is True and manifest['source_unchanged'] is True,
              'actual production build profile differs')
        check(manifest['source_sha256'] == production_sources(record['staged_sha256']), 'production compiler source graph is incomplete/different')
        check(verify_profile(target, manifest, expected_runtime=7, source_root=output / 'source') == 1,
              'current WC runtime7 storage profile differs')
        for name, digest in manifest['artifacts'].items():
            path = Path(name)
            check(path.is_absolute() and path.resolve().is_relative_to(target) and sha(path) == digest, 'production artifact binding')
        record['artifacts_sha256'] = {p.relative_to(target).as_posix(): sha(p) for p in sorted(target.rglob('*')) if p.is_file()}
        check({'kernel.elf', 'kernel.bin', 'dong_layout.json', 'esp/DONGOS.IMG', 'esp/SERVICES.BIN',
               'esp/EFI/BOOT/BOOTX64.EFI', 'build-inputs.json'} <= set(record['artifacts_sha256']), 'missing real boot artifacts')
        record.update(built=True, os_link_executed=True, esp=str(target / 'esp'))
    except BaseException as exc:
        record['build_error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        record['tools_unchanged'] = all(Path(t['path']).is_file() and sha(t['path']) == t['sha256'] for t in record.get('tools', {}).values())
        record['source_unchanged'] = inputs(source_root) == record['source_sha256']
        # The command uses a hyphen, so glob('build.*') silently loses its
        # receipt despite a successful real link. Enumerate the contract.
        record['log_sha256'] = {name: sha(output / name)
                                for name in ('build-command.json', 'build.stdout', 'build.stderr')
                                if (output / name).is_file()}
        if not record['tools_unchanged'] or not record['source_unchanged']:
            record['built'] = False
        write(output / 'wc-source.json', record)
    check(record['built'], 'unstable build inputs/tools')
    return record


def identity(esp, *, source_root=ROOT):
    esp = Path(esp).resolve()
    record = verify_prepared(esp.parent.parent, source_root=source_root)
    check(record.get('built') is True and record.get('os_link_executed') is True
          and record.get('source_unchanged') is True and record.get('tools_unchanged') is True
          and record.get('esp') == str(esp), 'completed real WC benchmark build required')
    required = {'kernel.elf', 'kernel.bin', 'dong_layout.json', 'build-inputs.json',
                'esp/DONGOS.IMG', 'esp/SERVICES.BIN', 'esp/EFI/BOOT/BOOTX64.EFI'}
    check(isinstance(record.get('artifacts_sha256'), dict) and required <= set(record['artifacts_sha256'])
          and set(record.get('tools', {})) == {'python', 'nasm', 'ld_lld', 'lld_link'}
          and {'build-command.json', 'build.stdout', 'build.stderr'} <= set(record.get('log_sha256', {})),
          'complete actual artifacts/tools/raw build logs required; flags alone are insufficient')
    for name, digest in record['artifacts_sha256'].items():
        check(sha(ordinary(esp.parent, name)) == digest, 'artifact changed: ' + name)
    for t in record['tools'].values():
        check(sha(t['path']) == t['sha256'], 'build tool changed')
    for name, digest in record['log_sha256'].items():
        check(sha(ordinary(esp.parent.parent, name)) == digest, 'build command/log changed')
    manifest = json.loads((esp.parent / 'build-inputs.json').read_text(encoding='utf-8'))
    check(manifest.get('runtime_level') == 7 and manifest.get('test') is True
          and manifest.get('source_unchanged') is True and manifest.get('graphics_case') is None
          and manifest.get('smp_case') is None, 'actual production manifest profile differs')
    check(manifest.get('source_sha256') == production_sources(record['staged_sha256']),
          'actual production compiler input graph is incomplete/different')
    check(verify_profile(esp.parent, manifest, expected_runtime=7, source_root=esp.parent.parent / 'source') == 1,
          'current WC runtime7 storage profile differs')
    for name, digest in manifest['artifacts'].items():
        path = Path(name)
        check(path.is_absolute() and path.resolve().is_relative_to(esp.parent)
              and sha(path) == digest, 'production artifact manifest differs')
    from tools.elf_symbols import read_elf_symbols
    symbols = read_elf_symbols(esp.parent / 'kernel.elf')
    report = '__dg_m' + b'mm.wc_benchmark'.hex() + '_g' + b'REPORT'.hex()
    check({'wc_benchmark_trial', 'wc_benchmark_restore', report} <= set(symbols), 'actual linked benchmark functions/report missing')
    return record


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--build', action='store_true')
    a = p.parse_args(argv)
    result = build(a.output) if a.build else prepare(a.output)
    print(json.dumps(dict(output=result['output'], built=result['built'], guest_executed=False, physical_wc_performance=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
