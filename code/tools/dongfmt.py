#!/usr/bin/env python3
"""Token-preserving Dong formatter using the repository's current parser."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, fields, is_dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import sys
import tempfile


def compiler_root():
    # Works both in this isolated prototype and after promotion to tools/.
    for parent in Path(__file__).resolve().parents:
        if (parent / 'lang/dongc/frontend.py').is_file():
            return parent
    raise RuntimeError('cannot find the Dong compiler beside dongfmt')


ROOT = compiler_root()
sys.path.insert(0, str(ROOT))
from lang.dongc.frontend import Parser, lex
from lang.dongc.model import CompileError, Token

VERSION = '0.1.0'


class FormatError(ValueError):
    pass


@dataclass(frozen=True)
class Piece:
    kind: str
    raw: str
    anchor: int


def _pieces(source, tokens):
    """Recover raw tokens/trivia from lexer positions without decoding literals.

    The compiler is the lexical authority, including its non-nested comments.
    The extra scanner only partitions gaps that the lexer already skipped.
    """
    lines = [0, *(m.end() for m in re.finditer('\n', source))]
    result, cursor = [], 0

    def trivia(end, anchor):
        nonlocal cursor
        while cursor < end:
            if source[cursor].isspace():
                cursor += 1
            elif source.startswith('//', cursor):
                stop = source.find('\n', cursor)
                stop = end if stop < 0 else stop
                result.append(Piece('line-comment', source[cursor:stop], anchor))
                cursor = stop
            elif source.startswith('/*', cursor):
                stop = source.find('*/', cursor + 2)
                if stop < 0 or stop + 2 > end:
                    raise FormatError('inconsistent compiler block-comment boundary')
                stop += 2
                result.append(Piece('block-comment', source[cursor:stop], anchor))
                cursor = stop
            else:
                raise FormatError('unaccounted non-whitespace input')
        if cursor != end:
            raise FormatError('overlapping compiler token positions')

    for anchor, token in enumerate(tokens[:-1]):
        start = lines[token.line - 1] + token.column - 1
        trivia(start, anchor)
        if token.kind == 'string':
            end = start + 1
            while end < len(source):
                if source[end] == '\\':
                    end += 2
                elif source[end] == '"':
                    end += 1
                    break
                else:
                    end += 1
        else:
            end = start + len(token.value)
        result.append(Piece(token.kind, source[start:end], anchor))
        cursor = end
    trivia(len(source), len(tokens) - 1)
    return result


def _ast(value):
    if isinstance(value, Token):
        return ('Token', value.kind, value.value)
    if is_dataclass(value):
        return (type(value).__name__, tuple((f.name, _ast(getattr(value, f.name))) for f in fields(value)))
    if isinstance(value, dict):
        return tuple(sorted((key, _ast(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_ast(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted(_ast(item) for item in value))
    return value


def _space(previous, current):
    if previous is None:
        return False
    a, b = previous.kind, current.kind
    if b in {';', ',', ')', ']', '.', ':'} or a in {'(', '[', '.', '?', '~'}:
        return False
    if a == '..' or b == '..':
        return False
    if b == '(' and (a in {'identifier', ')', ']'} or a in {'fn', 'align', 'export'}):
        return False
    if b == '[' and a in {'identifier', ')', ']'}:
        return False
    if a == ']' and b in {'identifier', 'const'}:
        return False
    return True


def _render(pieces):
    output, delimiters = [], []
    depth, beginning, pending, previous = 0, True, False, None

    def newline():
        nonlocal beginning
        if not beginning:
            output.append('\n')
            beginning = True

    def emit(raw, space=False):
        nonlocal beginning
        if beginning:
            output.append('    ' * depth)
        elif space:
            output.append(' ')
        output.append(raw)
        beginning = raw.endswith('\n')

    for piece in pieces:
        if piece.kind.endswith('-comment'):
            # Canonical own-line comments preserve their bytes and token anchor;
            # moving a trailing comment cannot swallow the following token.
            newline()
            emit(piece.raw)
            newline()
            continue
        kind = piece.kind
        if kind == '}':
            depth -= 1
            newline()
        elif pending and not (previous and previous.kind == '}'
                              and kind in {'else', ';', ',', ')', ']', '.', '('}):
            newline()
        pending = False
        emit(piece.raw, _space(previous, piece))
        if kind in {'{', '(', '['}:
            delimiters.append(kind)
            if kind == '{':
                depth += 1
                pending = True
        elif kind in {'}', ')', ']'}:
            expected = {'}': '{', ')': '(', ']': '['}[kind]
            if not delimiters or delimiters.pop() != expected:
                raise FormatError('inconsistent parsed delimiters')
            pending = kind == '}'
        elif kind == ';':
            pending = not delimiters or delimiters[-1] != '['
        elif kind == ',':
            pending = bool(delimiters and delimiters[-1] == '{')
        previous = piece
    newline()
    if delimiters or depth:
        raise FormatError('incomplete parsed delimiters')
    return ''.join(output)


def format_source(source: str, path='input.dg') -> str:
    bom = '\ufeff' if source.startswith('\ufeff') else ''
    body = source[len(bom):]
    tokens = lex(body, path=path)
    before = Parser(tokens).parse()  # Reject syntax before producing any output.
    pieces = _pieces(body, tokens)
    formatted = _render(pieces)
    after_tokens = lex(formatted, path=path)
    after = Parser(after_tokens).parse()
    if [(t.kind, t.value) for t in tokens] != [(t.kind, t.value) for t in after_tokens]:
        raise FormatError('formatter changed the compiler token stream')
    after_pieces = _pieces(formatted, after_tokens)
    if pieces != after_pieces:
        raise FormatError('formatter changed raw tokens, comments or comment anchors')
    if _ast(before) != _ast(after):
        raise FormatError('formatter changed the parsed syntax tree')
    return bom + formatted


def format_bytes(raw: bytes, path='input.dg') -> bytes:
    return format_source(raw.decode('utf-8', errors='strict'), path).encode('utf-8')


@dataclass(frozen=True)
class Prepared:
    path: Path
    original: bytes
    formatted: bytes
    mode: int
    identity: tuple[int, int]


def prepare(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise FormatError(f'{path}: only regular, non-symlink files may be formatted')
    info = path.stat()
    raw = path.read_bytes()
    return Prepared(path, raw, format_bytes(raw, str(path)), stat.S_IMODE(info.st_mode),
                    (info.st_dev, info.st_ino))


def _unchanged(item):
    if item.path.is_symlink():
        return False
    info = item.path.stat()
    return ((info.st_dev, info.st_ino) == item.identity
            and stat.S_IMODE(info.st_mode) == item.mode
            and hashlib.sha256(item.path.read_bytes()).digest() == hashlib.sha256(item.original).digest())


def write_files(items):
    """All syntax preflight precedes staging. Each replacement is atomic.

    A source change is checked before staging and again just before replacement.
    This is a concurrent-edit guard, not a multi-file filesystem transaction.
    """
    staged = []
    try:
        if not all(_unchanged(item) for item in items):
            raise FormatError('source changed during formatting; refusing to overwrite')
        for item in items:
            if item.original == item.formatted:
                continue
            fd, name = tempfile.mkstemp(prefix='.dongfmt-', suffix='.tmp', dir=item.path.parent)
            temporary = Path(name)
            staged.append((item, temporary))
            with os.fdopen(fd, 'wb') as stream:
                stream.write(item.formatted)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, item.mode)
        if not all(_unchanged(item) for item in items):
            raise FormatError('source changed while staging; refusing to overwrite')
        for item, temporary in staged:
            if not _unchanged(item):
                raise FormatError(f'{item.path}: source changed before replacement')
            os.replace(temporary, item.path)
    finally:
        for _, temporary in staged:
            if temporary.exists():
                temporary.unlink()


def main(argv=None):
    # Windows' locale may be GBK. Paths and diagnostics are UTF-8, just like DG
    # input/output; binary writes below also avoid CRLF translation.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', newline='\n')
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--check', action='store_true', help='0: unchanged, 1: formatting needed, 2: error')
    action.add_argument('--write', action='store_true', help='preflight all files, then atomically replace changed files')
    parser.add_argument('--version', action='version', version='dongfmt ' + VERSION)
    parser.add_argument('paths', nargs='*', help='files, or a sole - for stdin (default)')
    args = parser.parse_args(argv)
    stdin = not args.paths or args.paths == ['-']
    if '-' in args.paths and not stdin:
        parser.error('stdin cannot be mixed with paths')
    if args.write and stdin:
        parser.error('--write requires regular file paths')
    if len(args.paths) > 1 and not (args.check or args.write):
        parser.error('multiple paths require --check or --write')
    try:
        if stdin:
            original = sys.stdin.buffer.read()
            formatted = format_bytes(original, '<stdin>')
            if args.check:
                return int(formatted != original)
            sys.stdout.buffer.write(formatted)
            return 0
        resolved = [Path(path).resolve() for path in args.paths]
        if len(set(resolved)) != len(resolved):
            raise FormatError('duplicate input paths')
        items = [prepare(Path(path)) for path in args.paths]
        if args.write:
            write_files(items)
        elif args.check:
            for item in items:
                if item.original != item.formatted:
                    print(item.path)
            return int(any(item.original != item.formatted for item in items))
        else:
            sys.stdout.buffer.write(items[0].formatted)
        return 0
    except CompileError as exc:
        print(f'{exc.token.path or "input.dg"}:{exc.token.line}:{exc.token.column}: '
              f'error[{exc.code}]: {exc.message}', file=sys.stderr)
    except (OSError, UnicodeError, FormatError, RecursionError) as exc:
        print('dongfmt: ' + str(exc), file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
