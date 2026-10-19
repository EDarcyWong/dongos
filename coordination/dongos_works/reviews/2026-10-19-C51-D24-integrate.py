"""Install accepted files and run only their integrated mainline test modules."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time

WORKS = Path(__file__).resolve().parents[1]
ROOT = (WORKS / '../../code').resolve()
REVIEW = WORKS / 'reviews'
CONFIG = {'C51': ('claude', 'u64_expression_ir', 6),
          'D24': ('deepseek', 'nasm_u64_loop_function', 3)}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted(number):
    owner, stem, count = CONFIG[number]
    data = json.loads((REVIEW / '2026-10-19-C51-D24-acceptance.json').read_text(encoding='utf-8'))
    task = next(t for t in data['tasks'] if t['id'] == owner + ':' + number)
    assert task['status'] == 'accepted' and task['rev'] == 5
    assert task['verification']['passed'] and task['verification']['source_stable']
    for path, expected in task['verification']['fingerprint'].items():
        assert digest(WORKS / path) == expected, path
    return task


def adaptations(number):
    if number == 'C51':
        return {
            "WORKS=Path(__file__).resolve().parents[2]\nROOT=WORKS\nif not (ROOT/'lang').is_dir() and (WORKS/'project.json').is_file():\n    source=Path(json.loads((WORKS/'project.json').read_text(encoding='utf-8'))['source_root'])\n    ROOT=(WORKS/source).resolve() if not source.is_absolute() else source\n":
                'ROOT=Path(__file__).resolve().parents[2]\nWORKS=ROOT\n',
            "SOURCE=WORKS/'claude-works/src/bootstrap/u64_expression_ir.dg'":
                "SOURCE=ROOT/'lang/bootstrap/u64_expression_ir.dg'",
            "DOC=WORKS/'claude-works/src/bootstrap/u64_expression_ir.md'":
                "DOC=ROOT/'lang/bootstrap/u64_expression_ir.md'",
            "WORKS/'claude-works/build/C51'": "ROOT/'build/bootstrap_u64_expression_ir'",
        }
    return {
        "WORKS = Path(__file__).resolve().parents[2]\nROOT = WORKS\nif not (ROOT / 'lang').is_dir() and (WORKS / 'project.json').is_file():\n    source = Path(json.loads((WORKS / 'project.json').read_text(encoding='utf-8'))['source_root'])\n    ROOT = source if source.is_absolute() else (WORKS / source).resolve()\n":
            'ROOT = Path(__file__).resolve().parents[2]\nWORKS = ROOT\n',
        "SOURCE = WORKS / 'deepseek-works/src/bootstrap/nasm_u64_loop_function.dg'":
            "SOURCE = ROOT / 'lang/bootstrap/nasm_u64_loop_function.dg'",
        "WORKS/'deepseek-works/build/D24'": "ROOT/'build/bootstrap_nasm_u64_loop_function'",
    }


def metadata(number):
    return REVIEW / ('2026-10-19-' + number + '-integration.json')


def prepare():
    plans = []
    for number, (owner, stem, count) in CONFIG.items():
        task = accepted(number)
        files = []
        for suffix in ('.dg', '.md'):
            source = WORKS / (owner + '-works/src/bootstrap') / (stem + suffix)
            target = ROOT / 'lang/bootstrap' / (stem + suffix)
            files.append((source, target, source.read_bytes()))
        source = WORKS / (owner + '-works/tests') / ('test_' + stem + '.py')
        target = ROOT / 'lang/tests' / ('test_bootstrap_' + stem + '.py')
        text = source.read_text(encoding='utf-8')
        for old, new in adaptations(number).items():
            assert text.count(old) == 1, (number, old)
            text = text.replace(old, new, 1)
        files.append((source, target, text.encode('utf-8')))
        assert all(not target.exists() for source, target, content in files), number
        assert not metadata(number).exists(), metadata(number)
        plans.append((number, task, files))
    for number, task, files in plans:
        for source, target, content in files:
            with target.open('xb') as handle:
                handle.write(content)
        report = dict(task=task['id'], accepted_rev=5,
                      accepted_fingerprint=task['verification']['fingerprint'],
                      formal_job=task['verification']['job'],
                      path_only_test_adaptations=adaptations(number),
                      files=[dict(source=str(source), target=str(target), source_sha256=digest(source),
                                  target_sha256=digest(target)) for source, target, content in files],
                      registered_integrated=False)
        metadata(number).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(dict(task=task['id'], installed=[str(target) for source, target, content in files])))


def run(number):
    task = accepted(number)
    owner, stem, count = CONFIG[number]
    record_path = metadata(number)
    record = json.loads(record_path.read_text(encoding='utf-8'))
    target = ROOT / 'lang/tests' / ('test_bootstrap_' + stem + '.py')
    spec = importlib.util.spec_from_file_location('integrated_inputs_' + number, target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    paths = [module.SOURCE, module.DOC, target, *module.DEPENDENCIES,
             *sorted((ROOT / 'lang/dongc').rglob('*.py')), ROOT / 'lang/tests/test_dongc.py']
    before = {p.relative_to(ROOT).as_posix(): digest(p) for p in paths}
    build = ROOT / 'build' / ('bootstrap_' + stem)
    previous = set(build.glob('run-*'))
    command = [sys.executable, '-m', 'unittest', 'lang.tests.test_bootstrap_' + stem, '-v']
    log = REVIEW / ('2026-10-19-' + number + '-main-test.log')
    started = time.monotonic()
    with log.open('wb') as output:
        result = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, timeout=1200)
    elapsed = round(time.monotonic() - started, 3)
    after = {p.relative_to(ROOT).as_posix(): digest(p) for p in paths}
    text = log.read_text(encoding='utf-8')
    matches = re.findall(r'^Ran (\d+) tests? in ([0-9.]+)s$', text, re.M)
    ok = re.search(r'^OK(?: \(skipped=(\d+)\))?$', text, re.M)
    passed = result.returncode == 0 and bool(ok) and bool(matches)
    tests = int(matches[-1][0]) if matches else 0
    skips = int(ok.group(1) or 0) if ok else 0
    stable = before == after
    new_runs = set(build.glob('run-*')) - previous
    record.update(main_test_command=command, main_test_cwd=str(ROOT), main_test_log=str(log),
                  main_inputs_before=before, main_inputs_after=after,
                  main_test=dict(passed=passed, returncode=result.returncode, tests=tests, skips=skips,
                                 elapsed_seconds=elapsed, source_stable=stable),
                  main_runs=[str(p) for p in sorted(new_runs)])
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    assert passed and tests == count and skips == 0 and stable, record['main_test']
    assert len(new_runs) == 1, new_runs
    summary = json.loads((next(iter(new_runs)) / 'summary.json').read_text(encoding='utf-8'))
    assert summary['stable'] and summary['source_sha256'] == summary['source_sha256_after']
    for path, value in summary['artifact_sha256'].items():
        assert digest(next(iter(new_runs)) / path) == value, path
    accepted(number)
    for item in record['files']:
        assert digest(Path(item['target'])) == item['target_sha256']
        if Path(item['target']).suffix in ('.dg', '.md'):
            assert Path(item['target']).read_bytes() == Path(item['source']).read_bytes()
    record['main_artifact_hashes_checked'] = len(summary['artifact_sha256'])
    record['accepted_files_unchanged_after_main_test'] = True
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(task=task['id'], main_test=record['main_test'],
                         inputs=len(before), artifacts=record['main_artifact_hashes_checked'],
                         evidence=str(record_path)), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    if sys.argv[1] == 'prepare':
        prepare()
    else:
        run(sys.argv[1])
