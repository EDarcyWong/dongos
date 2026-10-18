"""Explicit source-root module loading, visibility and namespace resolution."""
from __future__ import annotations

from pathlib import Path

from .frontend import Parser, lex
from .model import Module, Token, fail


class Resolver:
    def __init__(self, roots=()):
        self.roots = list(dict.fromkeys(Path(root).resolve() for root in roots))
        self.units = {}
        self.paths = {}
        self.sources = {}
        self.active = []

    def read(self, path: Path, display: str) -> Module:
        raw = path.read_bytes()
        try:
            source = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            prefix = raw[:exc.start].decode("utf-8-sig", errors="replace")
            token = Token("invalid", "", prefix.count("\n") + 1,
                          len(prefix.rsplit("\n", 1)[-1]) + 1, display)
            fail("E0001", token, "source is not valid UTF-8")
        self.sources[display] = source
        return Parser(lex(source, path=display)).parse()

    def locate(self, name: str, token: Token) -> Path:
        relative = Path(*name.split(".")).with_suffix(".dg")
        found = []
        for root in self.roots:
            candidate = root / relative
            if candidate.is_file():
                resolved = candidate.resolve()
                if not resolved.is_relative_to(root):
                    fail("E0202", token, f"module {name!r} resolves outside its source root")
                found.append(resolved)
        if not found:
            fail("E0202", token, f"module {name!r} not found in the specified source roots")
        if len(found) != 1:
            fail("E0202", token, f"module {name!r} is present in multiple source roots")
        return found[0]

    def load(self, entry: Path) -> Module:
        entry = entry.resolve()
        first = self.read(entry, entry.as_posix())
        if self.roots:
            expected = self.locate(first.name, first.token)
            if expected != entry:
                fail("E0202", first.token, "entry module name does not match its source-root-relative path")
            display = first.name.replace(".", "/") + ".dg"
            self.sources.pop(entry.as_posix(), None)
            first = self.read(entry, display)
        elif first.imports:
            fail("E0202", first.imports[0].token, "module imports require an explicit --root")
        self.visit(first, entry)
        result = self.merge(first.name)
        result.source_files = [str(self.paths[name]) for name in sorted(self.paths)]
        return result

    def visit(self, unit: Module, path: Path):
        if unit.name in self.active:
            fail("E0202", unit.token, "cyclic module import: " + " -> ".join(self.active + [unit.name]))
        if unit.name in self.units:
            return
        self.active.append(unit.name)
        self.units[unit.name] = unit
        self.paths[unit.name] = path
        aliases = set()
        for declaration in unit.imports:
            if declaration.alias in aliases:
                fail("E0201", declaration.token, f"duplicate import alias {declaration.alias!r}")
            aliases.add(declaration.alias)
            if declaration.path in self.active:
                fail("E0202", declaration.token, "cyclic module import: " + " -> ".join(self.active + [declaration.path]))
            target = self.locate(declaration.path, declaration.token)
            if declaration.path not in self.units:
                imported = self.read(target, declaration.path.replace(".", "/") + ".dg")
                if imported.name != declaration.path:
                    fail("E0202", imported.token, f"expected module {declaration.path!r}, found {imported.name!r}")
                self.visit(imported, target)
        self.active.pop()

    def merge(self, entry: str) -> Module:
        from .declarations import Declarations
        return Declarations(self.units, self.sources, entry).resolve()


def prepare_single(module: Module, source: str, path: str) -> Module:
    if module.imports:
        fail("E0202", module.imports[0].token, "imports require file compilation with explicit source roots")
    resolver = Resolver()
    resolver.units[module.name] = module
    resolver.sources[path] = source
    return resolver.merge(module.name)
