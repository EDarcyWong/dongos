#!/usr/bin/env python3
"""Reproduce a host-only native compiler fixed point, without seed fallback.

Python orchestrates and builds only the seed executable. Every stage1/stage2
assembly byte must come from a PATH-isolated native Dong compiler process.
Artifacts and failure receipts are retained; this never boots a guest OS.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUDGETS = dict(memory_mib=512, tokens=250000, nodes=150000,
                       types=150032, fields=300032, limbs=4802048,
                       max_depth=128, code_memory_mib=256, assembly_mib=128)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_files(root: Path) -> list[Path]:
    paths = []
    for directory, pattern in [('lang/bootstrap', '*.dg'), ('lang/std', '*.dg'),
                               ('lang/dongc', '*.py')]:
        base = root / directory
        if not base.is_dir():
            raise ValueError(f'missing input directory: {base}')
        paths.extend(base.rglob(pattern))
    paths.extend(root / name for name in ('lang/host/native_entry.dg',
                 'lang/host/native_driver.c', 'tools/build_native_frontend.py'))
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'input must be a regular non-symlink file: {path}')
        if any((root / parent).is_symlink() for parent in path.relative_to(root).parents
               if parent != Path('.')):
            raise ValueError(f'symlinked input directory: {path}')
    return sorted(paths)


def fingerprint(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): digest(path) for path in input_files(root)}


def snapshot(root: Path, destination: Path) -> dict[str, str]:
    before = fingerprint(root)
    destination.mkdir(parents=True, exist_ok=False)
    for name in before:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    if before != fingerprint(root) or before != fingerprint(destination):
        raise RuntimeError('compiler inputs changed while taking the snapshot')
    return before


def identical(left: Path, right: Path) -> bool:
    # Compare bytes, not merely hashes, for the fixed-point assertion.
    return left.read_bytes() == right.read_bytes()


def require_fixed_point(work: Path) -> dict[str, bool]:
    result = {kind: identical(work / ('stage1.' + kind), work / ('stage2.' + kind))
              for kind in ('asm', 'o', 'exe')}
    if not all(result.values()):
        raise RuntimeError('native fixed point differs: ' + ', '.join(k for k, v in result.items() if not v))
    return result


def prepare_work(path: Path) -> Path:
    path = path.absolute()
    resolved = path.resolve()
    if resolved.is_relative_to(ROOT) and not resolved.is_relative_to(ROOT / 'build'):
        raise ValueError('repository outputs must stay inside code/build')
    # A fresh directory prevents stale artifacts or receipts being mistaken for
    # this run. No existing run, executable or user file is overwritten.
    path.mkdir(parents=True, exist_ok=False)
    return path.resolve()


def run(work: Path, mode: str, timeout: int, budgets: dict[str, int]) -> dict:
    receipt = dict(schema=1, status='running', mode=mode,
                   host_fixed_point=False, guest_booted=False, full_L3_accepted=False,
                   seed_python_used=True, target_python_used=False,
                   budgets=budgets, timeout_seconds=timeout, commands=[], artifacts={})
    source = work / 'source'
    expected = None

    def save():
        temporary = work / 'receipt.tmp'
        temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
        temporary.replace(work / 'receipt.json')

    def command(label, args, *, native=False, expected_exit=0):
        args = list(map(str, args))
        env = dict(os.environ)
        if native:
            env['PATH'] = ''
        record = dict(label=label, command=args, cwd=str(work),
                      native_path_empty=native, expected_exit=expected_exit)
        receipt['commands'].append(record)
        save()
        try:
            completed = subprocess.run(args, cwd=work, env=env, capture_output=True,
                                       timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            record['timeout'] = True
            (work / (label + '.stdout')).write_bytes(exc.stdout or b'')
            (work / (label + '.stderr')).write_bytes(exc.stderr or b'')
            raise RuntimeError(f'{label} exceeded {timeout} seconds') from exc
        (work / (label + '.stdout')).write_bytes(completed.stdout)
        (work / (label + '.stderr')).write_bytes(completed.stderr)
        record['returncode'] = completed.returncode
        record['stdout_sha256'] = digest(work / (label + '.stdout'))
        record['stderr_sha256'] = digest(work / (label + '.stderr'))
        save()
        if completed.returncode != expected_exit:
            raise RuntimeError(f'{label} exited {completed.returncode}, expected {expected_exit}; see {label}.stderr')
        return completed

    def stable():
        if expected != fingerprint(source):
            raise RuntimeError('frozen compiler inputs changed during the run')

    try:
        save()
        if os.name != 'posix' or platform.machine().lower() not in ('x86_64', 'amd64'):
            raise RuntimeError('native bootstrap requires POSIX x86-64')
        nasm = shutil.which(os.environ.get('NASM', 'nasm'))
        cc = shutil.which(os.environ.get('CC', 'gcc'))
        if not nasm or not cc:
            raise RuntimeError('NASM and C compiler are required (set NASM and CC)')
        nasm, cc = str(Path(nasm).resolve()), str(Path(cc).resolve())
        receipt['tools'] = {name: dict(path=path, sha256=digest(Path(path)))
                            for name, path in [('nasm', nasm), ('cc', cc)]}
        expected = snapshot(ROOT, source)
        receipt['source_sha256'] = expected
        receipt['runner_sha256'] = digest(Path(__file__))
        command('nasm-version', [nasm, '-v'])
        help_text = command('nasm-help', [nasm, '-h']).stdout.decode('utf-8', 'replace')
        nasm_warnings = ['-w-' + warning for warning in ('reloc-rel-dword', 'reloc-abs-qword')
                         if re.search(r'(?m)^\s*' + re.escape(warning) + r'\s', help_text)]
        command('cc-version', [cc, '--version'])
        seed = work / 'seed-native'
        built = command('seed-build', [sys.executable, source / 'tools/build_native_frontend.py',
                          '--mode', mode, '--output', seed])
        receipt['seed_build'] = json.loads(built.stdout)
        receipt['artifacts']['seed-native'] = digest(seed)
        stable()
        options = [item for key, value in budgets.items()
                   for item in ('--' + key.replace('_', '-'), str(value))]
        roots = ['--root', source / 'lang', '--root', source / 'lang/std']
        entry = source / 'lang/host/native_entry.dg'
        for stage, compiler in ((1, seed), (2, work / 'stage1.exe')):
            stable()
            output = work / f'stage{stage}.asm'
            emitted = command(f'stage{stage}-emit', [compiler, '--emit-asm', output,
                      '--stats', '--mode', mode, *options, *roots, entry], native=True)
            stats = json.loads(emitted.stdout)
            if stats.get('status') != 0 or stats.get('backend_status') != 0 or stats.get('backend_run') != 1:
                raise RuntimeError(f'stage{stage} did not report successful native emission')
            if not output.is_file() or not output.stat().st_size or stats.get('assembly_bytes') != output.stat().st_size:
                raise RuntimeError(f'stage{stage} assembly missing or reported length differs')
            receipt[f'stage{stage}_stats'] = stats
            stable()
            # NASM includes a source-file symbol. Both builds therefore use
            # exactly the same canonical input/object paths, preserving rather
            # than stripping symbols and making whole-file equality meaningful.
            shutil.copyfile(output, work / 'compiler.asm')
            command(f'stage{stage}-assemble', [nasm, '-O0', '-f', 'elf64', '-Wall', '-Werror',
                                             *nasm_warnings, '-o', 'compiler.o', 'compiler.asm'])
            shutil.copyfile(work / 'compiler.o', work / f'stage{stage}.o')
            command(f'stage{stage}-link', [cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-no-pie', '-Wl,--build-id=none', source / 'lang/host/native_driver.c',
                    'compiler.o', '-o', 'compiler.exe'])
            shutil.copyfile(work / 'compiler.exe', work / f'stage{stage}.exe')
            (work / f'stage{stage}.exe').chmod(0o700)
            for suffix in ('asm', 'o', 'exe'):
                name = f'stage{stage}.{suffix}'
                receipt['artifacts'][name] = digest(work / name)
            save()
        stable()
        receipt['equal'] = require_fixed_point(work)
        # Execute the final result, not just compare opaque outputs. The invalid
        # control must be a source diagnostic, not a capacity/internal failure.
        good = work / 'positive.dg'; bad = work / 'negative.dg'
        good.write_text('module positive;fn f(x:u64)u64{return x+1;}\n')
        bad.write_text('module negative;fn f()u64{return true;}\n')
        for label, path, status in [('positive', good, 0), ('negative', bad, 1)]:
            observed = command('stage2-' + label, [work / 'stage2.exe', '--check', '--stats', path],
                               native=True, expected_exit=status)
            stats = json.loads(observed.stdout)
            if (label == 'positive' and stats.get('status') != 0) or (label == 'negative' and stats.get('status') != 3):
                raise RuntimeError(f'stage2 {label} control returned unexpected semantic status')
        stable()
        receipt.update(status='passed', host_fixed_point=True)
        save()
        return receipt
    except (OSError, ValueError, RuntimeError) as exc:
        receipt.update(status='failed', error=str(exc), host_fixed_point=False)
        save()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path,
                        default=ROOT / 'build/test/native-fixedpoint' / ('run-' + uuid.uuid4().hex[:12]))
    parser.add_argument('--mode', choices=('debug', 'release'), default='debug')
    parser.add_argument('--timeout', type=int, default=600, help='seconds per subprocess')
    for name, default in DEFAULT_BUDGETS.items():
        parser.add_argument('--' + name.replace('_', '-'), type=int, default=default)
    options = parser.parse_args(argv)
    budgets = {name: getattr(options, name) for name in DEFAULT_BUDGETS}
    if options.timeout <= 0 or any(value <= 0 for value in budgets.values()):
        parser.error('timeout and all memory/pool budgets must be positive')
    try:
        work = prepare_work(options.work_dir)
        run(work, options.mode, options.timeout, budgets)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'native-fixedpoint: {exc}', file=sys.stderr)
        print(f'retained run: {options.work_dir}', file=sys.stderr)
        return 2
    print(json.dumps(dict(status='passed', host_fixed_point=True, guest_booted=False,
                          receipt=str(work / 'receipt.json')), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
