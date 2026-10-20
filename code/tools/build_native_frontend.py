#!/usr/bin/env python3
"""Build the POSIX native compiler subset; Python is only the seed builder."""
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
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from lang.dongc import compile_file, CompileError
from lang.dongc.modules import Resolver

ENTRY = '''module native_frontend_entry;
import bootstrap.frontend as frontend;
import bootstrap.frontend_diagnostics as diagnostics;
import bootstrap.compiler_driver as compiler;
'''

def tool(name, variable):
    value = os.environ.get(variable, name)
    found = shutil.which(value)
    if not found:
        raise RuntimeError(f"{variable}: executable unavailable: {value}")
    return found

def build(output: Path, mode: str = 'debug') -> dict:
    if os.name != 'posix' or platform.machine().lower() not in ('x86_64', 'amd64'):
        raise RuntimeError('native host driver currently requires POSIX x86-64')
    output = output.absolute()
    if output.is_symlink() or (output.exists() and not output.is_file()):
        raise ValueError('output must be a regular file, not a directory or symlink')
    # Build output belongs outside source trees, so successful builds cannot
    # overwrite the compiler source or host shim even accidentally.
    if output.suffix.lower() in ('.dg', '.py', '.c', '.h', '.md'):
        raise ValueError('output cannot use a source-file extension')
    resolved = output.resolve()
    if resolved.is_relative_to(ROOT) and not resolved.is_relative_to(ROOT/'build'):
        raise ValueError('repository outputs must stay inside code/build')
    nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='native-frontend-', dir=output.parent) as directory:
        work = Path(directory)
        entry = work/'native_frontend_entry.dg'
        entry.write_text(ENTRY, encoding='utf-8')
        roots = [work, ROOT/'lang', ROOT/'lang/std']
        resolver = Resolver(roots)
        resolver.load(entry)
        source_files = [p for p in resolver.paths.values() if p != entry]
        source_files += [ROOT/'lang/host/native_driver.c', Path(__file__)]
        before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
        before.update({str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted((ROOT/'lang/dongc').glob('*.py'))})
        compilation = compile_file(entry, roots=roots, mode=mode)
        asm, obj, exe = work/'frontend.asm', work/'frontend.o', work/'dong-native'
        asm.write_text(compilation.assembly, encoding='utf-8')
        help_text = subprocess.run([nasm, '-h'], check=True, text=True, capture_output=True).stdout
        flags = ['-Wall', '-Werror'] + ['-w-' + w for w in ('reloc-rel-dword', 'reloc-abs-qword')
                                       if re.search(r'(?m)^\s*' + re.escape(w) + r'\s', help_text)]
        commands = [[nasm, '-O0', '-f', 'elf64', *flags, '-o', str(obj), str(asm)],
                    [cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-no-pie',
                     str(ROOT/'lang/host/native_driver.c'), str(obj), '-o', str(exe)]]
        for command in commands:
            result = subprocess.run(command, text=True, capture_output=True, timeout=180)
            if result.returncode:
                raise RuntimeError(f"build command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}{result.stderr}")
        after = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in before}
        if after != before:
            raise RuntimeError('compiler inputs changed during native frontend build')
        receipt = {'mode': mode, 'stage': 'host-seed-built-native-compiler-subset',
                   'selfhost': False, 'source_sha256': before,
                   'assembly_sha256': hashlib.sha256(asm.read_bytes()).hexdigest(),
                   'executable_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
                   'commands': commands}
        os.replace(exe, output)
        return receipt

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'build/native/dong-native')
    parser.add_argument('--mode', choices=('debug', 'release'), default='debug')
    options = parser.parse_args(argv)
    try:
        receipt = build(options.output, options.mode)
    except (OSError, ValueError, RuntimeError, CompileError) as error:
        print(f'build-native-frontend: {error}', file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
