"""Run a deterministic whole-module shard; record the complete test inventory."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item

def partition(ids, count):
    if type(count) is not int or count < 1:
        raise ValueError('positive shard count required')
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('empty or duplicate test inventory')
    modules = sorted({name.split('.')[0] for name in ids})
    if count > len(modules):
        raise ValueError('shard count exceeds module count')
    assignment = {module: i % count for i, module in enumerate(modules)}
    shards = [[name for name in ids if assignment[name.split('.')[0]] == i] for i in range(count)]
    if any(not shard for shard in shards) or sorted(name for shard in shards for name in shard) != sorted(ids):
        raise ValueError('incomplete shard coverage')
    return shards

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('host', 'language'), required=True)
    parser.add_argument('--index', type=int, required=True)
    parser.add_argument('--count', type=int, required=True)
    parser.add_argument('--inventory-only', action='store_true')
    args = parser.parse_args()
    if not 0 <= args.index < args.count:
        parser.error('shard index outside count')
    start = ROOT / ('tests' if args.suite == 'host' else 'lang/tests')
    cases = list(flatten(unittest.defaultTestLoader.discover(str(start), pattern='test_*.py')))
    if any(type(case).__name__ == '_FailedTest' for case in cases):
        unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(case for case in cases if type(case).__name__ == '_FailedTest'))
        raise SystemExit('test discovery failed; shard cannot omit failed imports')
    ids = [case.id() for case in cases]
    shards = partition(ids, args.count)
    selected = set(shards[args.index])
    record = dict(suite=args.suite, index=args.index, count=args.count,
                  inventory=ids, assignments=shards, selected=shards[args.index],
                  inventory_sha256=hashlib.sha256('\n'.join(ids).encode()).hexdigest())
    output = ROOT/'build/test/ci-inventory'; output.mkdir(parents=True, exist_ok=True)
    (output/f'{args.suite}-{args.index}.json').write_text(json.dumps(record, indent=2)+'\n')
    print(f'{args.suite}: {len(ids)} total, {len(selected)} selected, shard {args.index}/{args.count}', flush=True)
    if args.inventory_only:
        return 0
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(case for case in cases if case.id() in selected))
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
