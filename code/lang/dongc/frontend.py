"""Dong lexer and parser."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from .model import *


def lex(source: str, path: str | None = None) -> list[Token]:
    """Positions count Unicode code points; CRLF counts as one line break."""
    result: list[Token] = []
    index, line, column = 0, 1, 1

    def advance(text: str):
        nonlocal index, line, column
        index += len(text)
        for char in text:
            if char == "\n":
                line, column = line + 1, 1
            else:
                column += 1

    while index < len(source):
        c = source[index]
        token = Token(c, c, line, column, path)
        if c.isspace():
            advance(c)
            continue
        if source.startswith("//", index):
            end = source.find("\n", index)
            advance(source[index:len(source) if end < 0 else end])
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end < 0:
                fail("E0001", token, "unterminated block comment")
            advance(source[index:end + 2])
            continue
        if c == '"':
            start = index
            advance(c)
            value = bytearray()
            while index < len(source) and source[index] != '"':
                c = source[index]
                if c in "\r\n":
                    fail("E0001", token, "newline in string literal")
                if c != "\\":
                    value.extend(c.encode("utf-8"))
                    advance(c)
                    continue
                escape_token = Token("string", "", line, column, path)
                advance(c)
                if index >= len(source):
                    fail("E0001", token, "unterminated string literal")
                c = source[index]
                escapes = {"n": b"\n", "r": b"\r", "t": b"\t", "0": b"\0", "\\": b"\\", '"': b'"'}
                if c in escapes:
                    value.extend(escapes[c])
                    advance(c)
                elif c == "x":
                    text = source[index + 1:index + 3]
                    if not re.fullmatch("[0-9a-fA-F]{2}", text):
                        fail("E0001", escape_token, "expected two hexadecimal digits after \\x")
                    value.append(int(text, 16))
                    advance("x" + text)
                else:
                    fail("E0001", escape_token, "invalid string escape")
            if index >= len(source):
                fail("E0001", token, "unterminated string literal")
            advance('"')
            # Export names must be ASCII. Latin-1 preserves arbitrary escaped bytes
            # until the parser can reject them with the correct source position.
            result.append(Token("string", value.decode("latin-1"), token.line, token.column, path))
            continue
        if c.isascii() and c.isdigit():
            end = index + 1
            while end < len(source) and (source[end].isalnum() or source[end] == "_"):
                end += 1
            text = source[index:end]
            pattern = (r"0x[0-9a-fA-F]+(?:_[0-9a-fA-F]+)*" if text.startswith("0x") else
                       r"0b[01]+(?:_[01]+)*" if text.startswith("0b") else r"[0-9]+(?:_[0-9]+)*")
            if not re.fullmatch(pattern, text):
                fail("E0001", token, "invalid integer literal")
            result.append(Token("integer", text, line, column, path))
            advance(text)
            continue
        if c == "_" or c.isidentifier():
            end = index + 1
            while end < len(source) and ("a" + source[end]).isidentifier():
                end += 1
            text = source[index:end]
            result.append(Token(text if text in KEYWORDS else "identifier", text, line, column, path))
            advance(text)
            continue
        operator = next((op for op in ("<<=", ">>=", "==", "!=", "<=", ">=", "&&", "||", "<<", ">>", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "..", "=>") if source.startswith(op, index)), None)
        if operator:
            result.append(Token(operator, operator, line, column, path))
            advance(operator)
        elif c in "{}()[];,:.+-*/%&|^~!<>=?":
            result.append(token)
            advance(c)
        else:
            fail("E0001", token, f"invalid character {c!r}")
    result.append(Token("eof", "", line, column, path))
    return result


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens, self.index = tokens, 0
        self.type_lengths: dict[str, Expr] = {}

    @property
    def token(self):
        return self.tokens[self.index]

    def take(self, kind: str) -> Token | None:
        if self.token.kind == kind:
            token = self.token
            self.index += 1
            return token
        return None

    def expect(self, kind: str) -> Token:
        token = self.take(kind)
        if token is None:
            self.unsupported()
            fail("E0101", self.token, f"expected {kind!r}, found {self.token.value or 'end of file'!r}")
        return token

    def unsupported(self):
        if self.token.kind in UNSUPPORTED:
            fail("E0601", self.token, f"{self.token.value!r} declarations are not supported in this context")

    def typ(self, *, allow_void=False) -> str:
        token = self.token
        if self.take("?"):
            return "?" + self.typ()
        if self.take("!"):
            return "!" + self.typ(allow_void=True)
        if self.take("*"):
            readonly = bool(self.take("const"))
            return ("*const " if readonly else "*") + self.typ()
        if self.take("["):
            if self.take("]"):
                readonly = bool(self.take("const"))
                return ("[]const " if readonly else "[]") + self.typ()
            count = self.integer_or_expression(self.expression(), "array length")
            self.expect("]")
            if isinstance(count, Expr):
                key = f"@{len(self.type_lengths)}"
                self.type_lengths[key] = count
                return f"[{key}]" + self.typ()
            self.positive_count(count, token, "array length")
            return f"[{count}]" + self.typ()
        if token.kind in {"fn", "unsafe", "extern"}:
            return self.function_typ()
        if token.kind in {"void", "noreturn"} and not allow_void:
            fail("E0302", token, f"{token.kind} is only allowed as a function return type")
        if token.kind != "identifier" and not (allow_void and token.kind in {"void", "noreturn"}):
            fail("E0301", token, "expected an object type" + (" or void" if allow_void else ""))
        self.index += 1
        name = token.value
        while self.take("."):
            name += "." + self.expect("identifier").value
        return ALIASES.get(name, name)

    def function_typ(self) -> str:
        unsafe, abi, seen = False, "sysv64", set()
        while self.token.kind in {"unsafe", "extern"}:
            modifier = self.token
            self.index += 1
            if modifier.kind in seen:
                fail("E0101", modifier, f"duplicate {modifier.kind} modifier")
            seen.add(modifier.kind)
            if modifier.kind == "unsafe":
                unsafe = True
            else:
                token = self.expect("string")
                if token.value not in {"sysv64", "win64"}:
                    fail("E0601", token, "ABI must be 'sysv64' or 'win64'")
                abi = token.value
        self.expect("fn")
        self.expect("(")
        params, names = [], set()
        while self.token.kind != ")":
            if self.token.kind == "identifier" and self.tokens[self.index + 1].kind == ":":
                name = self.expect("identifier")
                self.expect(":")
                if name.value in names:
                    fail("E0201", name, f"duplicate parameter {name.value!r}")
                names.add(name.value)
            params.append(self.typ())
            if not self.take(","):
                break
        self.expect(")")
        returns = self.typ(allow_void=True)
        return make_function_type(params, returns, abi, unsafe)

    def static_integer(self, expr: Expr, what: str) -> int:
        if expr.kind == "integer":
            return expr.value
        if expr.kind == "unary" and expr.value in {"-", "~"}:
            value = self.static_integer(expr.args[0], what)
            return -value if expr.value == "-" else ~value
        if expr.kind == "binary" and expr.value not in COMPARISONS | {"&&", "||"}:
            a = self.static_integer(expr.args[0], what)
            b = self.static_integer(expr.args[1], what)
            if expr.value in {"/", "%"} and b == 0:
                fail("E0302", expr.token, f"division by zero in {what}")
            if expr.value in {"<<", ">>"} and (b < 0 or b > 4096):
                fail("E0302", expr.token, f"invalid shift in {what}")
            return constant_op(expr.value, a, b)
        fail("E0601", expr.token, f"{what} currently requires an integer constant expression")

    def integer_or_expression(self, expr: Expr, what: str) -> int | Expr:
        """Fold the existing numeric subset; named/layout expressions wait."""
        def numeric(value):
            if value.kind == "integer":
                return True
            if value.kind == "unary" and value.value in {"-", "~"}:
                return numeric(value.args[0])
            return (value.kind == "binary" and value.value not in COMPARISONS | {"&&", "||"}
                    and all(numeric(child) for child in value.args))

        return self.static_integer(expr, what) if numeric(expr) else expr

    @staticmethod
    def positive_count(count: int, token: Token, what: str):
        if count <= 0:
            fail("E0302", token, f"{what} must be positive")
        if count > (1 << 63) - 1:
            fail("E0302", token, f"{what} exceeds the x86-64 object size limit")

    @staticmethod
    def dotted_name(expr: Expr) -> str | None:
        if expr.kind == "name":
            return expr.value
        if expr.kind == "field":
            prefix = Parser.dotted_name(expr.args[0])
            if prefix is not None:
                return prefix + "." + expr.value
        return None

    def parse(self) -> Module:
        self.expect("module")
        first = self.expect("identifier")
        parts = [first.value]
        while self.take("."):
            parts.append(self.expect("identifier").value)
        self.expect(";")
        module_name = ".".join(parts)
        functions, structs, imports, aliases, constants, globals_, enums, errors = [], [], [], [], [], [], [], []
        while self.token.kind != "eof":
            if self.take("import"):
                imported = self.expect("identifier")
                imported_parts = [imported.value]
                while self.take("."):
                    imported_parts.append(self.expect("identifier").value)
                alias = self.expect("identifier").value if self.take("as") else imported_parts[-1]
                self.expect(";")
                imports.append(ImportDecl(imported, ".".join(imported_parts), alias))
                continue
            export, public, packed, alignment = None, False, False, None
            abi, explicit_abi, unsafe = "sysv64", False, False
            while self.token.kind in {"pub", "export", "packed", "align", "extern", "unsafe"}:
                modifier = self.token
                self.index += 1
                if modifier.kind == "pub":
                    if public:
                        fail("E0101", modifier, "duplicate pub modifier")
                    public = True
                elif modifier.kind == "export":
                    if export is not None:
                        fail("E0101", modifier, "duplicate export modifier")
                    self.expect("(")
                    name = self.expect("string")
                    self.expect(")")
                    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name.value):
                        fail("E0602", name, "export name must be an ASCII linker identifier")
                    export = name.value
                elif modifier.kind == "packed":
                    if packed:
                        fail("E0101", modifier, "duplicate packed modifier")
                    packed = True
                elif modifier.kind == "unsafe":
                    if unsafe:
                        fail("E0101", modifier, "duplicate unsafe modifier")
                    unsafe = True
                elif modifier.kind == "extern":
                    if explicit_abi:
                        fail("E0101", modifier, "duplicate extern modifier")
                    explicit_abi = True
                    abi_token = self.expect("string")
                    if abi_token.value not in {"sysv64", "win64"}:
                        fail("E0601", abi_token, "ABI must be 'sysv64' or 'win64'")
                    abi = abi_token.value
                    if self.take("("):
                        name = self.expect("string")
                        self.expect(")")
                        if export is not None:
                            fail("E0101", name, "linker name is already specified")
                        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name.value):
                            fail("E0602", name, "external name must be an ASCII linker identifier")
                        export = name.value
                else:
                    if alignment is not None:
                        fail("E0101", modifier, "duplicate align modifier")
                    self.expect("(")
                    alignment = self.integer_or_expression(self.expression(), "alignment")
                    self.expect(")")
            if self.take("enum"):
                name = self.expect("identifier")
                if export is not None or explicit_abi or unsafe or packed or alignment is not None:
                    fail("E0101", name, "only pub may modify an enum declaration")
                self.expect("{")
                variants = []
                while self.token.kind not in {"}", "eof"}:
                    variant = self.expect("identifier")
                    payload = None
                    if self.take("("):
                        payload = self.typ()
                        if self.token.kind == ",":
                            fail("E0601", self.token, "enum variants accept at most one payload")
                        self.expect(")")
                    if self.token.kind == "=":
                        fail("E0601", self.token, "explicit enum tags are not supported")
                    variants.append((variant, payload))
                    if not self.take(","):
                        break
                self.expect("}")
                enums.append(EnumDecl(name, variants, public, module_name, name.value))
                continue
            if self.take("error"):
                name = self.expect("identifier")
                if export is not None or explicit_abi or unsafe or packed or alignment is not None:
                    fail("E0101", name, "only pub may modify an error declaration")
                self.expect("=")
                code = self.integer_or_expression(self.expression(), "error number")
                self.expect(";")
                errors.append(ErrorDecl(name, code, public, module_name, name.value))
                continue
            if self.take("struct"):
                name = self.expect("identifier")
                if export is not None or explicit_abi or unsafe:
                    fail("E0101", name, "export, extern and unsafe apply only to functions")
                self.expect("{")
                fields, field_public = [], set()
                while self.token.kind not in {"}", "eof"}:
                    public_field = bool(self.take("pub"))
                    field = self.expect("identifier")
                    if public_field:
                        field_public.add(field.value)
                    self.expect(":")
                    fields.append((field, self.typ()))
                    if not self.take(","):
                        break
                self.expect("}")
                structs.append(StructDecl(name, fields, packed, alignment, public, module_name, name.value, field_public))
                continue
            if packed or alignment is not None:
                fail("E0101", self.token, "packed and align apply only to structures")
            if self.take("type"):
                name = self.expect("identifier")
                if export is not None or explicit_abi or unsafe:
                    fail("E0101", name, "export, extern and unsafe apply only to functions")
                self.expect("=")
                target = self.typ(allow_void=True)
                self.expect(";")
                aliases.append(AliasDecl(name, target, public, module_name, name.value))
                continue
            if self.take("const"):
                name = self.expect("identifier")
                if export is not None or explicit_abi or unsafe:
                    fail("E0101", name, "export, extern and unsafe apply only to functions")
                if not self.take(":"):
                    fail("E0301", name, "top-level const requires an explicit type")
                typ = self.typ()
                self.expect("=")
                expr = self.expression()
                self.expect(";")
                constants.append(ConstDecl(name, typ, expr, public, module_name, name.value))
                continue
            if self.take("var"):
                name = self.expect("identifier")
                if export is not None or explicit_abi or unsafe:
                    fail("E0101", name, "export, extern and unsafe apply only to functions")
                if not self.take(":"):
                    fail("E0301", name, "top-level var requires an explicit type")
                typ = self.typ()
                if not self.take("="):
                    fail("E0301", name, "top-level var requires an explicit initializer")
                expr = self.expression()
                self.expect(";")
                globals_.append(GlobalDecl(name, typ, expr, public, module_name, name.value))
                continue
            if self.token.kind == "let":
                fail("E0601", self.token, "top-level let is not implemented; use const or explicitly initialized var")
            self.expect("fn")
            receiver = None
            if self.token.kind == "(":
                self.index += 1
                receiver_name = self.expect("identifier")
                self.expect(":")
                receiver = receiver_name, self.typ()
                self.expect(")")
            name = self.expect("identifier")
            self.expect("(")
            params = [receiver] if receiver is not None else []
            if self.token.kind != ")":
                while True:
                    param = self.expect("identifier")
                    self.expect(":")
                    params.append((param, self.typ()))
                    if not self.take(",") or self.token.kind == ")":
                        break
            self.expect(")")
            returns = self.typ(allow_void=True)
            external = bool(self.take(";"))
            if external and not explicit_abi:
                fail("E0101", name, "a function declaration without a body requires extern")
            body = [] if external else self.block()
            functions.append(Function(name, params, returns, body, export or (name.value if external else None),
                                      public=public, abi=abi, external=external, unsafe=unsafe or external,
                                      module=module_name, local_name=name.value, source_path=name.path or "", receiver=receiver))
        return Module(module_name, first, functions, structs, imports, aliases, constants, self.type_lengths, globals_,
                      enums=enums, errors=errors)

    def block(self) -> list[Stmt]:
        self.expect("{")
        statements = []
        while self.token.kind not in {"}", "eof"}:
            statements.append(self.statement())
        self.expect("}")
        return statements

    def statement(self) -> Stmt:
        token = self.token
        if self.take("let") or self.take("var") or self.take("const"):
            name = self.expect("identifier")
            typ = self.typ() if self.take(":") else None
            expr = self.expression() if self.take("=") else None
            if token.kind in {"let", "const"} and expr is None:
                fail("E0101", name, f"{token.kind} requires an initializer")
            if expr is None and typ is None:
                fail("E0301", name, "uninitialized var requires an explicit type")
            self.expect(";")
            return Stmt(token, "binding", (name, typ), expr)
        if self.take("return"):
            expr = None if self.token.kind == ";" else self.expression()
            self.expect(";")
            return Stmt(token, "return", expr=expr)
        if self.take("if"):
            expr = self.expression(allow_struct=False)
            body = self.block()
            otherwise = None
            if self.take("else"):
                otherwise = [self.statement()] if self.token.kind == "if" else self.block()
            return Stmt(token, "if", expr=expr, body=body, otherwise=otherwise)
        if self.take("while"):
            expr = self.expression(allow_struct=False)
            return Stmt(token, "while", expr=expr, body=self.block())
        if self.take("loop"):
            return Stmt(token, "loop", body=self.block())
        if self.take("for"):
            binding = self.expect("identifier")
            self.expect("in")
            iterable = self.expression(allow_struct=False)
            if self.take(".."):
                upper = self.expression(allow_struct=False)
                iterable = Expr(iterable.token, "range", args=[iterable, upper])
            return Stmt(token, "for", binding, iterable, self.block())
        if self.take("defer"):
            if self.token.kind == "{":
                return Stmt(token, "defer", body=self.block())
            statement = self.statement()
            if statement.kind != "call":
                fail("E0101", statement.token, "defer requires a call or a block")
            return Stmt(token, "defer", body=[statement])
        if self.take("match"):
            expr = self.expression(allow_struct=False)
            self.expect("{")
            arms = []
            while self.token.kind not in {"}", "eof"}:
                pattern = self.pattern()
                if self.token.kind == "if":
                    fail("E0601", self.token, "match guards are not supported")
                self.expect("=>")
                arms.append(MatchArm(pattern.token, pattern, self.block()))
                if not self.take(","):
                    break
            self.expect("}")
            return Stmt(token, "match", arms, expr)
        if self.take("unsafe"):
            return Stmt(token, "unsafe", body=self.block())
        if self.take("asm"):
            self.expect("{")
            instruction = self.token
            if instruction.kind != "identifier" or instruction.value not in ASM_INSTRUCTIONS:
                fail("E0601", instruction, "asm requires one instruction from the v1 whitelist")
            self.index += 1
            if self.token.kind != "}":
                fail("E0601", self.token, "asm accepts exactly one instruction without operands")
            self.expect("}")
            return Stmt(token, "asm", instruction.value)
        if self.token.kind == "{":
            return Stmt(token, "block", body=self.block())
        if self.take("break") or self.take("continue"):
            if self.token.kind != ";":
                fail("E0601", self.token, "break/continue values and labels are not supported")
            self.expect(";")
            return Stmt(token, token.kind)
        self.unsupported()
        expr = self.expression()
        if self.token.kind in ASSIGNMENTS:
            assignment = self.token
            self.index += 1
            value = self.expression()
            self.expect(";")
            return Stmt(assignment, "assign", (expr, assignment.kind), value)
        self.expect(";")
        if expr.kind != "call" and not (expr.kind == "try" and expr.args[0].kind == "call"):
            fail("E0101", token, "only calls can be standalone expression statements")
        return Stmt(token, "call", expr=expr)

    def pattern(self) -> Pattern:
        token = self.token
        if self.take("true") or self.take("false"):
            return Pattern(token, "bool", token.kind == "true")
        if self.take("null"):
            return Pattern(token, "null")
        name = self.expect("identifier")
        if name.value == "_":
            return Pattern(name, "wildcard")
        parts = [name.value]
        while self.take("."):
            parts.append(self.expect("identifier").value)
        kind = parts[0] if len(parts) == 1 and parts[0] in {"some", "ok", "err"} else "enum"
        binding = None
        if self.take("("):
            binding = self.expect("identifier")
            self.expect(")")
        elif kind in {"some", "err"}:
            fail("E0101", name, f"{kind} pattern requires a binding")
        return Pattern(name, kind, ".".join(parts) if kind == "enum" else None, binding)

    def expression(self, minimum=0, *, allow_struct=True) -> Expr:
        token = self.token
        if self.take("try"):
            left = Expr(token, "try", args=[self.expression(11, allow_struct=allow_struct)])
        elif self.take("error"):
            self.expect(".")
            parts = [self.expect("identifier").value]
            while self.take("."):
                parts.append(self.expect("identifier").value)
            left = Expr(token, "error", ".".join(parts))
        elif self.token.kind in {"!", "~", "-", "&", "*"}:
            self.index += 1
            left = Expr(token, "unary", token.kind, [self.expression(11, allow_struct=allow_struct)])
        elif self.take("integer"):
            text = token.value.replace("_", "")
            if text.startswith(("0x", "0b")):
                value = int(text, 16 if text.startswith("0x") else 2)
            else:
                # Avoid Python's decimal-string limit while preserving the
                # specification's arbitrary-precision untyped constants.
                value = 0
                for start in range(0, len(text), 1000):
                    chunk = text[start:start + 1000]
                    value = value * (10 ** len(chunk)) + int(chunk)
            left = Expr(token, "integer", value)
        elif self.take("true") or self.take("false"):
            left = Expr(token, "boolean", token.kind == "true")
        elif self.take("null"):
            left = Expr(token, "null")
        elif self.take("string"):
            left = Expr(token, "string", token.value.encode("latin-1"))
        elif self.take("identifier"):
            if token.value in {"sizeof", "alignof", "offsetof"} and self.take("("):
                typ = self.typ()
                field = None
                if token.value == "offsetof":
                    self.expect(",")
                    field = self.expect("identifier").value
                self.expect(")")
                left = Expr(token, "layout", (token.value, typ, field))
            else:
                left = Expr(token, "name", token.value)
        elif self.take("["):
            if self.token.kind == "]":
                fail("E0302", token, "empty array literals are not allowed")
            first = self.expression()
            if self.take(";"):
                count = self.integer_or_expression(self.expression(), "array repeat count")
                if not isinstance(count, Expr):
                    self.positive_count(count, token, "array repeat count")
                left = Expr(token, "array", count, [first])
            else:
                args = [first]
                while self.take(",") and self.token.kind != "]":
                    args.append(self.expression())
                left = Expr(token, "array", None, args)
            self.expect("]")
        elif self.take("("):
            left = self.expression()
            self.expect(")")
            left.parenthesized = True
        else:
            self.unsupported()
            fail("E0101", token, "expected an expression")
        while True:
            if self.take("("):
                args = []
                if self.token.kind != ")":
                    while True:
                        args.append(self.expression())
                        if not self.take(",") or self.token.kind == ")":
                            break
                self.expect(")")
                left = Expr(left.token, "call", left.value if left.kind == "name" else left, args)
            elif self.take("."):
                field = self.expect("identifier")
                left = Expr(field, "field", field.value, [left])
            elif self.take("["):
                index = None if self.token.kind == ".." else self.expression()
                if self.take(".."):
                    end = None if self.token.kind == "]" else self.expression()
                    self.expect("]")
                    left = Expr(left.token, "slice", args=[left, index, end])
                    continue
                self.expect("]")
                left = Expr(left.token, "index", args=[left, index])
            elif self.token.kind == "as" and minimum <= 10:
                cast = self.expect("as")
                left = Expr(cast, "cast", self.typ(), [left])
            elif self.token.kind == "{" and self.dotted_name(left) is not None and allow_struct:
                self.index += 1
                names, args = [], []
                while self.token.kind not in {"}", "eof"}:
                    name = self.expect("identifier")
                    self.expect(":")
                    names.append(name.value)
                    args.append(self.expression())
                    if not self.take(","):
                        break
                self.expect("}")
                left = Expr(left.token, "struct", (self.dotted_name(left), names), args)
            else:
                break
        while self.token.kind in PRECEDENCE and PRECEDENCE[self.token.kind] >= minimum:
            operator = self.token
            self.index += 1
            if operator.kind in COMPARISONS and left.kind == "binary" and left.value in COMPARISONS and not left.parenthesized:
                fail("E0101", operator, "chained comparisons are not allowed")
            if operator.kind == "orelse" and self.token.kind in {"return", "break", "continue"}:
                control = self.token
                self.index += 1
                if control.kind in {"break", "continue"} and self.token.kind not in {";", ",", ")", "]", "}", "{"}:
                    fail("E0601", self.token, "break/continue values and labels are not supported")
                value = self.expression(allow_struct=allow_struct) if control.kind == "return" and self.token.kind not in {";", ",", ")", "]", "}"} else None
                right = Expr(control, "exit", control.kind, [value] if value is not None else [])
            else:
                right = self.expression(PRECEDENCE[operator.kind] + (operator.kind != "orelse"), allow_struct=allow_struct)
            left = Expr(operator, "orelse" if operator.kind == "orelse" else "binary", None if operator.kind == "orelse" else operator.kind, [left, right])
        return left


