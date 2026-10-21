"""python -m lang.dongc --check file.dg / --emit-asm file.asm file.dg."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

from .compiler import CompileError, compile_file


def atomic_write_many(outputs: list[tuple[Path, str]]):
    """Stage the complete artifact set, restoring previous files on failure."""
    temporaries, prepared, committed = [], [], []
    recovery_files = set()
    try:
        # Check every target before staging or replacing any artifact. In
        # particular, a later directory target must not leave an earlier .asm.
        for path, _ in outputs:
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(mode):
                raise OSError(f"output target is not a regular file: {path}")
        for path, text in outputs:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent,
                                             prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
                staged = Path(stream.name)
                temporaries.append(staged)
                stream.write(text)
            backup = None
            if path.exists():
                with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=path.name + ".rollback.",
                                                 suffix=".tmp", delete=False) as stream:
                    backup = Path(stream.name)
                    temporaries.append(backup)
                shutil.copyfile(path, backup)
            prepared.append((path, staged, backup))
        for path, staged, backup in prepared:
            os.replace(staged, path)
            committed.append((path, backup))
    except BaseException as error:
        failures = []
        for path, backup in reversed(committed):
            try:
                if backup is None:
                    path.unlink(missing_ok=True)
                else:
                    os.replace(backup, path)
            except OSError as rollback_error:
                if backup is not None:
                    recovery_files.add(backup)
                failures.append(f"{path}: {rollback_error}" +
                                (f" (previous output saved at {backup})" if backup is not None else ""))
        if failures:
            raise OSError(f"output write failed: {error}; rollback failed: " + "; ".join(failures)) from error
        raise
    finally:
        for temporary in temporaries:
            if temporary in recovery_files:
                continue
            temporary.unlink(missing_ok=True)


def atomic_write(path: Path, text: str):
    atomic_write_many([(path, text)])


def main(argv: list[str] | None = None) -> int:
    # Redirected Windows Python streams otherwise use the machine code page,
    # which loses identifiers and makes automated diagnostics non-reproducible.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Dong v0.1 L1 language compiler")
    parser.add_argument("source", type=Path)
    parser.add_argument("--check", action="store_true", help="check only; do not write artifacts")
    parser.add_argument("--emit-asm", type=Path)
    parser.add_argument("--emit-manifest", type=Path)
    parser.add_argument("--emit-layout", type=Path, help="export checked type sizes, alignments and field offsets")
    parser.add_argument("--emit-ir", type=Path, help="export the optional SSA backend and per-function fallback record")
    parser.add_argument("--target", default="x86_64-dongos-elf")
    parser.add_argument("--mode", choices=["debug", "release"], default="debug")
    parser.add_argument("-O", "--optimize", type=int, choices=(0, 1), default=0,
                        help="optional scalar SSA optimization; other functions use L1")
    parser.add_argument("-g", "--debug-info", action="store_true", help="emit source-level DWARF information")
    parser.add_argument("--function-sections", action="store_true", help="emit separate code sections for linker garbage collection; incompatible with -g")
    parser.add_argument("--root", type=Path, action="append", help="explicit module source root (repeatable)")
    options = parser.parse_args(argv)
    if options.check and (options.emit_asm or options.emit_manifest or options.emit_layout or options.emit_ir):
        parser.error("--check cannot be combined with output options")
    if not options.check and not (options.emit_asm or options.emit_layout or options.emit_ir):
        parser.error("provide --check, --emit-asm or --emit-layout")
    if options.emit_ir and not options.optimize:
        parser.error("--emit-ir requires --optimize 1")
    if options.function_sections and options.debug_info:
        parser.error("--function-sections cannot be combined with --debug-info")
    outputs = [path.resolve() for path in (options.emit_asm, options.emit_manifest, options.emit_layout, options.emit_ir) if path]
    if len(outputs) != len(set(outputs)) or options.source.resolve() in outputs:
        parser.error("output paths must be distinct and cannot overwrite the source")
    source, display_path = "", options.source.as_posix()
    try:
        compilation = compile_file(options.source, roots=options.root or [], mode=options.mode, target=options.target,
                                   optimize=options.optimize, debug_info=options.debug_info, function_sections=options.function_sections)
        if any(output in {Path(path).resolve() for path in compilation.source_files} for output in outputs):
            parser.error("output cannot overwrite an imported source file")
        if not options.check:
            artifacts = []
            if options.emit_asm:
                artifacts.append((options.emit_asm, compilation.assembly))
            if options.emit_manifest:
                artifacts.append((options.emit_manifest, json.dumps(compilation.manifest(), ensure_ascii=False, indent=2) + "\n"))
            if options.emit_layout:
                artifacts.append((options.emit_layout, json.dumps(compilation.layout_manifest, ensure_ascii=False, indent=2) + "\n"))
            if options.emit_ir:
                artifacts.append((options.emit_ir, json.dumps(compilation.optimization, ensure_ascii=False, indent=2) + "\n"))
            atomic_write_many(artifacts)
        return 0
    except CompileError as error:
        print(error.format(display_path, source), file=sys.stderr)
        return 1
    except OSError as error:
        print(f"dongc: IO error: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"dongc: internal error for {options.source}: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
