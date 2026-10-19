"""Reviewer-only cases against the already-built formal isolated CX2 executables."""
import hashlib
import json
import argparse
from pathlib import Path
import sys
import unittest

WORKSPACE = Path(__file__).resolve().parents[3]
SOURCE = WORKSPACE / 'code'
sys.path.insert(0, str(SOURCE))
from lang.dongc import compile_source
from lang.dongc.model import CompileError
from lang.tests import test_bootstrap_semantic_runtime as runtime
from lang.tests import test_bootstrap_semantic_types as decl

FORMAL = WORKSPACE / 'coordination/dongos_works/.local/runs/323f94f151404be3982303a0b57421e5/workspace'
BINARIES = FORMAL / 'build/test/bootstrap-semantic-runtime/run-a4eacec43d23'
OUTPUT = WORKSPACE / 'coordination/dongos_works/.local/reviews/CX2-independent-20261019'


class ReviewProbe(unittest.TestCase):
    run_cases = decl.BootstrapSemanticTypesTests.run_cases


def main():
    global FORMAL, BINARIES, OUTPUT
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', help='Optional newer formal job; preserves the original review evidence')
    args = parser.parse_args()
    if args.job:
        if len(args.job) != 32 or any(c not in '0123456789abcdef' for c in args.job):
            parser.error('--job must be a 32-character hexadecimal job id')
        FORMAL = WORKSPACE / ('coordination/dongos_works/.local/runs/' + args.job + '/workspace')
        BINARIES = max((FORMAL / 'build/test/bootstrap-semantic-runtime').glob('run-*'), key=lambda p:p.stat().st_mtime)
        OUTPUT = WORKSPACE / ('coordination/dongos_works/.local/reviews/CX2-independent-20261019/' + args.job)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    samples = []
    for typ in ('u16', 'i8', 'bool', '*u8'):
        samples += [
            f'fn f(x:?{typ})void{{match x{{null=>{{}},some(v)=>{{let y:{typ}=v;}}}}}}',
            f'fn f(x:!{typ})void{{match x{{ok(v)=>{{let y:{typ}=v;}},err(e)=>{{let z:u64=e;}}}}}}',
        ]
    samples += [
        'fn f(x:?u8)u8{var y:u8;match x{null=>{return 0;},some(v)=>{y=v;}}return y;}',
        'fn f(x:?u8)u8{var y:u8;match x{null=>{},some(v)=>{return v;}}return y;}',
        'fn f(x:!u8)u8{var y:u8;match x{ok(v)=>{y=v;},err(e)=>{return 0;}}return y;}',
        'fn f(x:?u8,b:bool)u8{var y:u8;match x{null=>{y=0;},some(v)=>{if b{y=v;}}}return y;}',
        'fn f(x:?u8)void{match x{some(_)=>{},null=>{}}}',
        'fn f(x:!u8)void{match x{ok(_)=>{},err(_)=>{}}}',
        'const O:?bool=false;fn f()bool{var y:bool;match O{null=>{},some(v)=>{y=v;}}return y;}',
        'const R:!u8=1;fn f()u8{var y:u8;match R{ok(v)=>{y=v;},err(e)=>{}}return y;}',
        'fn f(x:?u8,y:?u8)void{match x{some(v)=>{match y{some(v)=>{let a:u8=v;},null=>{}}},null=>{}}}',
        'fn f(x:!u8)void{match x{ok(v)=>{},err(e)=>{let y:bool=e;}}}',
        'fn f(x:?u8)void{match x{null=>{}}}',
    ]
    cases, records = [], []
    for body in samples:
        source = 'module a;' + body
        try:
            compile_source(source)
            status = 0
        except CompileError as error:
            # Exact nonzero status is established explicitly for supported
            # type/flow/name errors, not silently treated as any rejection.
            code = error.code
            status = {'E0301': 3, 'E0403': 15, 'E0401': 11, 'E0201': 9}.get(code)
            if status is None:
                records.append(dict(source=source, host_error=code, untested=True))
                continue
        cases.append(decl.case(source, status))
        records.append(dict(source=source, expected=status))
    probe = ReviewProbe()
    probe.work = OUTPUT
    inputs = ['lang/bootstrap/semantic_types.dg', 'lang/bootstrap/semantic_types.md',
              'lang/tests/test_bootstrap_semantic_runtime.py']
    hashes = {p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in inputs}
    for path in inputs:
        assert hashes[path] == hashlib.sha256((FORMAL / path).read_bytes()).hexdigest(), path
    failures = []
    for mode in ('debug', 'release'):
        exe = BINARIES / (mode + '.exe')
        for index, case in enumerate(cases):
            try:
                probe.run_cases(exe, [case], f'{mode}-{index:02d}')
            except AssertionError as error:
                failures.append(dict(mode=mode, index=index, failure=str(error)))
    after = {p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in inputs}
    result = dict(cases=records, tested_cases=len(cases), failures=failures,
                  source_sha256=hashes, source_stable=hashes == after,
                  binaries=str(BINARIES), note='Reused already-built formal isolated binaries; no recompile or source edits')
    (OUTPUT / 'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return bool(failures) or hashes != after


if __name__ == '__main__':
    raise SystemExit(main())
