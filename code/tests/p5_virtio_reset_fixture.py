"""Build-only fault injection. Never modify the production checkout or a disk."""
from pathlib import Path
import argparse, hashlib, json, shutil, subprocess, sys

TARGET = 'services/drivers/block_service.dg'
ANCHOR = '        match setup() { ok => {}, err(code) => { return code; }, }'
DECL = 'unsafe extern "sysv64" fn svc_user_ud2()void;\n'
CALL = '\n        svc_user_ud2(); // disposable P5 initialized-queue fault fixture\n'

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def inject(source):
    if source.count(ANCHOR) != 1 or 'svc_user_ud2' in source:
        raise ValueError('fault insertion requires exactly one pristine setup boundary')
    module_line = next(line for line in source.splitlines(True) if line.startswith('module '))
    module_end = source.index(module_line) + len(module_line)
    return source[:module_end] + DECL + source[module_end:].replace(ANCHOR, ANCHOR + CALL)

def hashes(root):
    return {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob('*'))
            if p.is_file() and not any(x in ('build', '__pycache__', '.git') for x in p.relative_to(root).parts)
            and p.suffix != '.pyc'}

def prepare(source, destination):
    source, destination = Path(source).resolve(), Path(destination).absolute()
    if destination.exists() or destination.is_symlink() or source == destination or source in destination.parents:
        raise ValueError('require new isolated destination outside source')
    for parent in destination.parents:
        if parent.is_symlink(): raise ValueError('symlink destination ancestor')
    if not (source / TARGET).is_file(): raise ValueError('source must be code root')
    for p in source.rglob('*'):
        if 'build' not in p.relative_to(source).parts and p.is_symlink():
            raise ValueError('source symlink is not allowed: ' + str(p))
    before = hashes(source)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('build', '.git', '__pycache__', '*.pyc'))
    target = destination / TARGET
    target.write_text(inject(target.read_text()))
    after = hashes(destination)
    changed = [name for name in before if before[name] != after.get(name)]
    if changed != [TARGET] or set(before) != set(after) or before != hashes(source):
        raise ValueError('fixture changed more than the single block entry source')
    record = dict(version=1, scope='initialized-queue-crash-reset-hold-only', source=str(source),
                  destination=str(destination), production_sha256=before, fixture_sha256=after,
                  changed=[TARGET], no_production_debug_backdoor=True, outstanding_io_proven=False)
    (destination / 'p5-reset-fixture.json').write_text(json.dumps(record, indent=2)+'\n')
    return record

def verify(root):
    root = Path(root); record = json.loads((root/'p5-reset-fixture.json').read_text())
    actual = hashes(root); actual.pop('p5-reset-fixture.json', None)
    if actual != record['fixture_sha256'] or record['changed'] != [TARGET]:
        raise ValueError('fixture source manifest mismatch')
    production = Path(record['source'])
    if hashes(production) != record['production_sha256']:
        raise ValueError('production sources changed since fixture preparation')
    if (root/TARGET).read_text() != inject((production/TARGET).read_text()):
        raise ValueError('fault fixture is not the exact audited injection')
    return record

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build', action='store_true')
    args=parser.parse_args();prepare(args.source,args.output)
    if args.build:
        subprocess.run([sys.executable,'-c',
            'from pathlib import Path; from tools.build import build; print(build(stage="p1", runtime_level=7, test=False, output=Path("build/p5-reset")))'],
            cwd=args.output,check=True)
    verify(args.output)
    print(args.output/'p5-reset-fixture.json')
if __name__=='__main__': main()
