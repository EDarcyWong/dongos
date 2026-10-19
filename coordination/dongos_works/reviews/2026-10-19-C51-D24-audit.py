"""Inspect formal verification artifacts without recompiling or executing workers."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

WORKS = Path(__file__).resolve().parents[1]
CONFIG = {
    'C51': ('claude', 'u64_expression_ir', 'f7289623842e4deba12e58db53c293a3', 6),
    'D24': ('deepseek', 'nasm_u64_loop_function', '9c0c6514f96c47bdb0df53afeac76677', 3),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(number):
    owner, stem, job, tests = CONFIG[number]
    jobroot = WORKS / '.local/runs' / job
    formal = json.loads((jobroot / 'result.json').read_text(encoding='utf-8'))
    assert formal['passed'] and formal['source_stable'], formal
    assert len(formal['checks']) == 1
    check = formal['checks'][0]
    assert check['tests'] == tests and check['skips'] == 0 and check['returncode'] == 0
    assert not check['cancelled'] and not check['timed_out']
    for path, expected in formal['fingerprint'].items():
        assert sha(WORKS / path) == expected, path
    runs = list((jobroot / 'workspace' / (owner + '-works/build') / number).glob('run-*'))
    assert len(runs) == 1, runs
    run = runs[0]
    summary = json.loads((run / 'summary.json').read_text(encoding='utf-8'))
    assert summary['stable'] and summary['source_sha256'] == summary['source_sha256_after']
    for path, expected in summary['artifact_sha256'].items():
        assert sha(run / path) == expected, path
    testfile = WORKS / (owner + '-works/tests') / ('test_' + stem + '.py')
    spec = importlib.util.spec_from_file_location('review_inputs_' + number, testfile)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    inputs = [module.SOURCE, module.DOC, testfile, *module.DEPENDENCIES]
    actual = {p.name: sha(p) for p in inputs}
    captured = {Path(p).name: value for p, value in summary['source_sha256'].items()}
    assert len(actual) == len(inputs) and actual == captured, (actual, captured)
    observations = []

    def native(label, expected, bad_value=False, rbx_delta=0):
        path = run / (label + '.native.output')
        raw = path.read_bytes()
        assert len(raw) == 12 * 8 * len(expected), label
        mismatches = []
        for index, (row, want) in enumerate(zip(struct.iter_unpack('<12Q', raw), expected)):
            assert row[1] == row[2], (label, index, 'rsp')
            assert row[3] == module.CALLER['rbx'], (label, index, 'planted rbx')
            assert row[4] == module.CALLER['rbx'] + rbx_delta, (label, index, 'returned rbx')
            assert row[5:10] == tuple(value for reg, value in module.CALLER.items() if reg != 'rbx')
            assert row[10] == module.CANARY and row[11] == 0, (label, index, 'canary/alignment')
            if row[0] != want:
                mismatches.append(dict(index=index, expected=want, actual=row[0]))
        assert bool(mismatches) == bad_value, (label, mismatches)
        observations.append(dict(label=label, vectors=len(expected), raw_sha256=sha(path),
                                 all_abi_guards_checked=True, rbx_delta=rbx_delta,
                                 rax_mismatches=mismatches))

    if number == 'C51':
        fixtures = module.FIXTURES
        expected = [module.py_eval(module.py_parse(module.py_tokens(expr)), dict(zip(params, args)))
                    for params, expr, args in fixtures]
        sub_indexes = [k for k, (params, expr, args) in enumerate(fixtures)
                       if '-' in expr and params and any(ins[0] == module.SUB and ins[2] != ins[3]
                           for ins in module.py_ir(module.py_parse(module.py_tokens(expr)), params)[0])]
        for mode in ('debug', 'release'):
            native('native-' + mode, expected)
            native('bad-sub-good-' + mode, [expected[k] for k in sub_indexes])
            native('bad-sub-' + mode, [expected[k] for k in sub_indexes], bad_value=True)
            native('bad-rbx-good-' + mode, expected)
            native('bad-rbx-' + mode, expected, rbx_delta=8)
        required = {'bad-sub-swapped', 'bad-unknown-name-mapped', 'bad-early-ir',
                    'bad-early-result', 'bad-rbx-clobbered', 'bad-no-alias'}
    else:
        def interpret(vector):
            acc, factor, increment = vector[6]
            for _ in range(vector[2]):
                acc = (acc * factor + increment) & ((1 << 64) - 1)
            return acc
        vectors = module.VECTORS
        for mode in ('debug', 'release'):
            native('native-' + mode, [interpret(v) for v in vectors])
            for name in ('bad-imul-add', 'bad-backedge-exit'):
                expected = [interpret(vectors[k]) for k in (3, 4)]
                native(name + '-good-' + mode, expected)
                native(name + '-' + mode, expected, bad_value=True)
            native('bad-early-header-good-native-' + mode, [interpret(vectors[4])])
        required = {'bad-imul-add', 'bad-backedge-exit', 'bad-early-header'}
    assert required <= {r.get('test') for r in summary['records']}
    report = dict(task=owner + ':' + number, submission_rev=3, formal_job=job,
                  formal=formal, run=str(run), source_unchanged_since_formal=True,
                  input_sha256=actual, artifact_hashes_checked=len(summary['artifact_sha256']),
                  native_observations=observations, test_records=summary['records'],
                  audit_script_sha256=sha(Path(__file__)), integrated=False)
    output = WORKS / 'reviews' / ('2026-10-19-' + number + '-evidence.json')
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(task=report['task'], evidence=str(output), checks=formal['checks'],
                         inputs=len(actual), artifacts=report['artifact_hashes_checked'],
                         native_rows=sum(x['vectors'] for x in observations),
                         observations=observations), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    audit(sys.argv[1])
