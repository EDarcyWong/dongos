"""Public Dong compiler pipeline; frontend, checking and code generation."""
from .model import CompileError, Token, fail
from .frontend import lex, Parser
from .checker import Checker
from .emitter import Emitter, Compilation
from .modules import Resolver, prepare_single
from pathlib import Path


def compile_source(source: str, path: str = "input.dg", *, mode: str = "debug", target: str = "x86_64-dongos-elf", optimize: int = 0, debug_info: bool = False, function_sections: bool = False) -> Compilation:
    if mode not in {"debug", "release"}:
        raise ValueError("mode must be debug or release")
    if type(optimize) is not int or optimize not in (0, 1):
        raise ValueError("optimize must be 0 or 1")
    if type(function_sections) is not bool or (function_sections and debug_info):
        raise ValueError("function_sections must be bool and cannot be combined with debug_info")
    if target != "x86_64-dongos-elf":
        fail("E0601", Token("target", target, 1, 1), "only x86_64-dongos-elf is implemented")
    source = source.removeprefix("\ufeff")
    path = path.replace("\\", "/")
    try:
        module = prepare_single(Parser(lex(source, path=path)).parse(), source, path)
        Checker(module).check()
        return Emitter(module, path, mode, optimize=optimize, debug_info=debug_info, function_sections=function_sections).compile()
    except CompileError as exc:
        exc.sources = {path: source}
        raise


def compile_file(source, *, roots=(), mode="debug", target="x86_64-dongos-elf", optimize=0, debug_info=False, function_sections=False) -> Compilation:
    if mode not in {"debug", "release"}:
        raise ValueError("mode must be debug or release")
    if type(optimize) is not int or optimize not in (0, 1):
        raise ValueError("optimize must be 0 or 1")
    if type(function_sections) is not bool or (function_sections and debug_info):
        raise ValueError("function_sections must be bool and cannot be combined with debug_info")
    if target != "x86_64-dongos-elf":
        fail("E0601", Token("target", target, 1, 1), "only x86_64-dongos-elf is implemented")
    resolver = Resolver(roots)
    try:
        module = resolver.load(Path(source))
        Checker(module).check()
        result = Emitter(module, module.token.path or str(source), mode, optimize=optimize, debug_info=debug_info, function_sections=function_sections).compile()
        result.source_files = module.source_files
        return result
    except CompileError as exc:
        exc.sources = resolver.sources
        raise
