"""Shared syntax tree and scalar definitions for the Dong v0.1 compiler.

The executable compiler never evaluates user code. Constant arithmetic here is
implemented directly; unsupported language features have explicit diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import re


KEYWORDS = set("module import as pub const let var type struct enum fn extern unsafe packed align export if else while loop for in match break continue return defer try error orelse true false null void noreturn asm".split())
INTEGER = {f"{sign}{width}" for sign in "iu" for width in (8, 16, 32, 64)}
TYPES = INTEGER | {"bool", "void", "noreturn", "usize", "isize"}
ALIASES = {"usize": "u64", "isize": "i64"}
COMPARISONS = {"==", "!=", "<", "<=", ">", ">="}
ASSIGNMENTS = {"=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>="}
PRECEDENCE = {"orelse": 0, "||": 1, "&&": 2, "==": 3, "!=": 3, "<": 3, "<=": 3, ">": 3, ">=": 3,
              "|": 4, "^": 5, "&": 6, "<<": 7, ">>": 7, "+": 8, "-": 8, "*": 9, "/": 9, "%": 9}
UNSUPPORTED = {"type"}  # Top-level aliases have their own parser branch.
WRAPPING_INTRINSICS = {"wrapping_add", "wrapping_sub", "wrapping_mul"}
MEMORY_INTRINSICS = {"volatile_load", "volatile_store", "read_unaligned", "write_unaligned",
                     "atomic_load", "atomic_store", "atomic_compare_exchange", "atomic_fetch_add", "compiler_fence"}
INTRINSICS = WRAPPING_INTRINSICS | MEMORY_INTRINSICS
UNSUPPORTED_BUILTINS = set()
ASM_INSTRUCTIONS = {"cli", "sti", "hlt", "pause", "int3", "lfence", "sfence", "mfence"}


@dataclass(frozen=True)
class FunctionSignature:
    params: tuple[str, ...]
    returns: str
    abi: str = "sysv64"
    unsafe: bool = False


def make_function_type(params, returns: str, abi="sysv64", unsafe=False) -> str:
    if abi not in {"sysv64", "win64"}:
        raise ValueError(f"unsupported function ABI {abi!r}")
    prefix = ("unsafe " if unsafe else "") + ('extern "win64" ' if abi == "win64" else "")
    return prefix + "fn(" + ",".join(params) + ")" + returns


@lru_cache(maxsize=4096)
def function_signature(typ: str) -> FunctionSignature | None:
    rest, unsafe, abi = typ, False, "sysv64"
    if rest.startswith("unsafe "):
        unsafe, rest = True, rest[7:]
    for name in ("sysv64", "win64"):
        prefix = f'extern "{name}" '
        if rest.startswith(prefix):
            abi, rest = name, rest[len(prefix):]
            break
    if not rest.startswith("fn("):
        return None
    depth, start, params = 0, 3, []
    for index in range(3, len(rest)):
        char = rest[index]
        if char in "([":
            depth += 1
        elif char == ")" and depth == 0:
            if index > start:
                params.append(rest[start:index])
            elif params:
                raise ValueError("empty function parameter type")
            returns = rest[index + 1:]
            if not returns:
                raise ValueError("missing function return type")
            return FunctionSignature(tuple(params), returns, abi, unsafe)
        elif char in ")]":
            depth -= 1
        elif char == "," and depth == 0:
            if index == start:
                raise ValueError("empty function parameter type")
            params.append(rest[start:index])
            start = index + 1
    raise ValueError("unterminated function type")


def is_function_type(typ: str) -> bool:
    return function_signature(typ) is not None


def function_type(function) -> str:
    return make_function_type((typ for _, typ in function.params), function.returns, function.abi, function.unsafe)


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    column: int
    path: str | None = None


class CompileError(Exception):
    def __init__(self, code: str, token: Token, message: str, related: Token | None = None):
        super().__init__(message)
        self.code, self.token, self.message, self.related = code, token, message, related
        self.sources: dict[str, str] = {}

    def format(self, path: str, source: str) -> str:
        t = self.token
        diagnostic_path = t.path or path
        result = f"{diagnostic_path}:{t.line}:{t.column}: error[{self.code}]: {self.message}"
        lines = self.sources.get(diagnostic_path, source).splitlines()
        if 0 < t.line <= len(lines):
            result += "\n    " + lines[t.line - 1] + "\n    " + " " * (t.column - 1) + "^"
        if self.related:
            result += f"\n{self.related.path or path}:{self.related.line}:{self.related.column}: note: previous declaration"
        return result


def fail(code: str, token: Token, message: str, related: Token | None = None):
    raise CompileError(code, token, message, related)


@dataclass
class Expr:
    token: Token
    kind: str
    value: object = None
    args: list[Expr | None] = field(default_factory=list)
    typ: str | None = None
    constant: int | bool | None = None
    parenthesized: bool = False


@dataclass
class Stmt:
    token: Token
    kind: str
    value: object = None
    expr: Expr | None = None
    body: list[Stmt] = field(default_factory=list)
    otherwise: list[Stmt] | None = None


@dataclass
class Pattern:
    token: Token
    kind: str
    value: object = None
    binding: Token | None = None


@dataclass
class MatchArm:
    token: Token
    pattern: Pattern
    body: list[Stmt]


@dataclass
class Variable:
    token: Token
    typ: str
    mutable: bool
    slot: int


@dataclass
class Function:
    token: Token
    params: list[tuple[Token, str]]
    returns: str
    body: list[Stmt]
    export: str | None
    symbol: str = ""
    variables: list[Variable] = field(default_factory=list)
    public: bool = False
    abi: str = "sysv64"
    external: bool = False
    unsafe: bool = False
    module: str = ""
    local_name: str = ""
    source_path: str = ""
    receiver: tuple[Token, str] | None = None


@dataclass
class StructDecl:
    token: Token
    fields: list[tuple[Token, str]]
    packed: bool = False
    alignment: int | Expr | None = None
    public: bool = False
    module: str = ""
    local_name: str = ""
    field_public: set[str] = field(default_factory=set)


@dataclass
class EnumDecl:
    token: Token
    variants: list[tuple[Token, str | None]]
    public: bool = False
    module: str = ""
    local_name: str = ""


@dataclass
class ErrorDecl:
    token: Token
    code: int | Expr
    public: bool = False
    module: str = ""
    local_name: str = ""


@dataclass
class ImportDecl:
    token: Token
    path: str
    alias: str


@dataclass
class AliasDecl:
    token: Token
    target: str
    public: bool = False
    module: str = ""
    local_name: str = ""


@dataclass
class StaticRelocation:
    offset: int
    symbol: str
    addend: int = 0


@dataclass
class StaticData:
    typ: str
    data: bytes
    relocations: list[StaticRelocation] = field(default_factory=list)


@dataclass
class StaticObject:
    symbol: str
    typ: str
    data: bytes
    alignment: int
    mutable: bool = False
    relocations: list[StaticRelocation] = field(default_factory=list)


@dataclass
class ConstDecl:
    token: Token
    typ: str
    expr: Expr
    public: bool = False
    module: str = ""
    local_name: str = ""
    symbol: str = ""
    initializer: StaticData | None = None


@dataclass
class GlobalDecl:
    token: Token
    typ: str
    expr: Expr
    public: bool = False
    module: str = ""
    local_name: str = ""
    symbol: str = ""
    mutable: bool = True
    initializer: StaticData | None = None


@dataclass
class Module:
    name: str
    token: Token
    functions: list[Function]
    structs: list[StructDecl] = field(default_factory=list)
    imports: list[ImportDecl] = field(default_factory=list)
    aliases: list[AliasDecl] = field(default_factory=list)
    constants: list[ConstDecl] = field(default_factory=list)
    type_lengths: dict[str, Expr] = field(default_factory=dict)
    globals: list[GlobalDecl] = field(default_factory=list)
    static_objects: list[StaticObject] = field(default_factory=list)
    enums: list[EnumDecl] = field(default_factory=list)
    errors: list[ErrorDecl] = field(default_factory=list)


def bits(typ: str) -> int:
    typ = ALIASES.get(typ, typ)
    if typ not in INTEGER:
        raise ValueError(f"not an integer type: {typ}")
    return int(typ[1:])


def is_signed(typ: str) -> bool:
    return ALIASES.get(typ, typ) in INTEGER and ALIASES.get(typ, typ).startswith("i")


def bounds(typ: str) -> tuple[int, int]:
    width = bits(typ)
    return (-(1 << (width - 1)), (1 << (width - 1)) - 1) if is_signed(typ) else (0, (1 << width) - 1)


def integer_div(a: int, b: int) -> int:
    return (abs(a) // abs(b)) * (-1 if (a < 0) != (b < 0) else 1)


def constant_op(op: str, a: int, b: int):
    if op == "+": return a + b
    if op == "-": return a - b
    if op == "*": return a * b
    if op == "/": return integer_div(a, b)
    if op == "%": return a - integer_div(a, b) * b
    if op == "&": return a & b
    if op == "|": return a | b
    if op == "^": return a ^ b
    if op == "<<": return a << b
    if op == ">>": return a >> b
    if op == "==": return a == b
    if op == "!=": return a != b
    if op == "<": return a < b
    if op == "<=": return a <= b
    if op == ">": return a > b
    if op == ">=": return a >= b
    if op == "&&": return bool(a and b)
    if op == "||": return bool(a or b)
    raise AssertionError(op)


