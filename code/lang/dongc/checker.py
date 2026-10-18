"""Dong name, type, place and definite-initialization checks."""
from __future__ import annotations

from dataclasses import dataclass
from math import gcd
import re
from .model import *
from .typesys import TypeSystem
from .l1_semantics import L1CheckerMixin


@dataclass
class Flow:
    initialized: set[int]
    reachable: bool = True


class Checker(L1CheckerMixin):
    def __init__(self, module: Module):
        self.module = module
        self.types = TypeSystem(module)
        module.type_system = self.types
        self.functions: dict[str, Function] = {}
        self.scopes: list[dict[str, Variable]] = []
        self.loops: list[list[set[int]]] = []
        self.unsafe_depth = 0

    def check(self):
        symbols: dict[str, Token] = {"__dong_panic": self.module.token,
                                   "__dg_file_" + self.module.name.encode("utf-8").hex(): self.module.token}
        for function in self.module.functions:
            owner = function.module or self.module.name
            symbols["__dg_file_" + owner.encode("utf-8").hex()] = self.module.token
        for obj in self.module.static_objects:
            if obj.symbol in symbols:
                fail("E0602", self.module.token, f"linker symbol {obj.symbol!r} is already defined or reserved", symbols[obj.symbol])
            symbols[obj.symbol] = self.module.token
        for function in self.module.functions:
            name = function.token.value
            if name in self.types.structs:
                fail("E0201", function.token, f"duplicate declaration {name!r}", self.types.structs[name].token)
            if name in self.functions:
                fail("E0201", function.token, f"duplicate function {name!r}", self.functions[name].token)
            if function.abi not in {"sysv64", "win64"}:
                fail("E0601", function.token, f"unsupported calling convention {function.abi!r}")
            for token, typ in function.params:
                self.signature_type(typ, token, external=function.external or function.abi == "win64")
            if function.returns not in {"void", "noreturn"}:
                self.signature_type(function.returns, function.token, external=function.external or function.abi == "win64")
            owner = function.module or self.module.name
            local_name = function.local_name or name
            function.symbol = function.symbol or function.export or (local_name if function.external else
                f"__dg_m{owner.encode('utf-8').hex()}_f{local_name.encode('utf-8').hex()}")
            if re.fullmatch(r"__dg_(?:static_)?string_[0-9]+", function.symbol):
                fail("E0602", function.token, f"linker symbol {function.symbol!r} is reserved for string literals")
            if function.symbol.startswith(("__dg_bridge_", "__dg_win64_body_")):
                fail("E0602", function.token, f"linker symbol {function.symbol!r} is reserved for ABI bridges")
            if function.symbol in symbols:
                fail("E0602", function.token, f"linker symbol {function.symbol!r} is already defined or reserved", symbols[function.symbol])
            symbols[function.symbol] = function.token
            self.functions[name] = function
        for function in self.module.functions:
            if function.external:
                continue
            self.function = function
            self.scopes = [{}]
            self.loops = []
            self.unsafe_depth = 0
            self.defer_frames, self.loop_scopes, self.in_defer = [], [], False
            function.variables = []
            initialized = set()
            for token, typ in function.params:
                variable = self.declare(token, typ, False)
                initialized.add(variable.slot)
            flow = self.block(function.body, Flow(initialized), scoped=False)
            if flow.reachable and function.returns != "void":
                fail("E0402", function.token, "non-void function has a path without an explicit return")

    def signature_type(self, typ: str, token: Token, *, external=False):
        self.types.layout(typ, token)
        if external and self.types.is_pair(typ):
            fail("E0601", token, "external function signatures only support scalar and pointer types")
        if self.types.is_aggregate(typ) and not self.types.is_pair(typ):
            fail("E0601", token, "struct and array values cannot cross function boundaries; use pointers")

    def require_unsafe(self, token: Token, operation: str):
        if not self.unsafe_depth:
            fail("E0501", token, f"{operation} requires an unsafe block")

    def declare(self, token: Token, typ: str, mutable: bool) -> Variable:
        self.types.layout(typ, token)
        scope = self.scopes[-1]
        if token.value in scope:
            fail("E0201", token, f"duplicate binding {token.value!r}", scope[token.value].token)
        variable = Variable(token, typ, mutable, len(self.function.variables) + 1)
        self.function.variables.append(variable)
        scope[token.value] = variable
        return variable

    def lookup(self, token: Token) -> Variable:
        for scope in reversed(self.scopes):
            if token.value in scope:
                return scope[token.value]
        if token.value in self.functions:
            fail("E0601", token, "function values are not implemented; use a direct call")
        fail("E0201", token, f"undefined name {token.value!r}")

    def base_coerce(self, expr: Expr, expected: str):
        if expr.typ == "int" and expected in INTEGER:
            self.resolve_integer_width(expr, expected)
            if expr.constant is not None:
                lo, hi = bounds(expected)
                if not lo <= expr.constant <= hi:
                    fail("E0302", expr.token, f"integer constant is outside {expected} range")
            else:
                for index, child in enumerate(expr.args):
                    if child.typ == "int":
                        self.coerce(child, "u64" if expr.kind == "binary" and expr.value in {"<<", ">>"} and index == 1 else expected)
            expr.typ = expected
        elif expr.typ == "null" and self.types.is_pointer(expected):
            expr.typ, expr.constant = expected, 0
        elif (self.types.is_pointer(expr.typ) and self.types.is_pointer(expected)
              and not self.types.readonly(expr.typ) and self.types.readonly(expected)
              and self.types.pointee(expr.typ) == self.types.pointee(expected)):
            expr.typ = expected
        elif (self.types.is_slice(expr.typ) and self.types.is_slice(expected)
              and not self.types.readonly(expr.typ) and self.types.readonly(expected)
              and self.types.element(expr.typ) == self.types.element(expected)):
            expr.typ = expected
        if expr.typ != expected:
            fail("E0301", expr.token, f"expected {expected}, found {expr.typ}")
        return expr.typ

    def resolve_integer_width(self, expr: Expr, expected: str) -> bool:
        """Resolve width-sensitive operators without narrowing ordinary constants.

        For example, 256-1 can adapt to u8, whereas (1<<8)-256 cannot hide an
        invalid u8 shift. Re-fold parents after resolving nested shifts/~ so
        contextual and explicitly typed operands give the same bit operations.
        """
        if expr.typ != "int":
            return False
        if expr.kind == "intrinsic" and expr.value in WRAPPING_INTRINSICS:
            for child in expr.args:
                self.coerce(child, expected)
            expr.intrinsic_type = expected
            if all(child.constant is not None for child in expr.args):
                operator = {"wrapping_add": "+", "wrapping_sub": "-", "wrapping_mul": "*"}[expr.value]
                expr.constant = self.wrap(constant_op(operator, *(child.constant for child in expr.args)), expected)
            return True
        if expr.kind == "binary" and expr.value in {"<<", ">>"}:
            left, right = expr.args
            self.coerce(left, expected)
            self.check_shift(expr, expected)
            if left.constant is not None and right.constant is not None:
                expr.constant = self.wrap(constant_op(expr.value, left.constant, right.constant), expected)
            return True
        if expr.kind == "unary" and expr.value == "~":
            child = expr.args[0]
            self.coerce(child, expected)
            if child.constant is not None:
                expr.constant = self.wrap(~child.constant, expected)
            return True
        changed = False
        for child in expr.args:
            changed = self.resolve_integer_width(child, expected) or changed
        if changed and all(child.constant is not None for child in expr.args):
            if expr.kind == "binary":
                left, right = expr.args
                if expr.value in {"/", "%"}:
                    if right.constant == 0:
                        fail("E0302", right.token, "division by zero in constant operand")
                    if is_signed(expected) and left.constant == bounds(expected)[0] and right.constant == -1:
                        fail("E0302", expr.token, "signed division overflow")
                expr.constant = constant_op(expr.value, left.constant, right.constant)
            elif expr.kind == "unary":
                expr.constant = -expr.args[0].constant
        return changed

    def materialize(self, expr: Expr):
        if expr.typ == "int":
            self.coerce(expr, "i64")
        elif expr.typ == "null":
            fail("E0301", expr.token, "cannot infer a pointer type for null")

    def base_expr(self, expr: Expr, initialized: set[int], expected: str | None = None, *, read=True):
        expr.addressable = expr.writable = expr.aggregate = False
        expr.alignment = 1
        if expr.kind == "integer":
            expr.typ, expr.constant = "int", expr.value
        elif expr.kind == "constant":
            expr.typ, expr.constant = expr.value
        elif expr.kind == "global":
            expr.typ = expr.value.typ
            expr.addressable, expr.writable = True, getattr(expr.value, "mutable", False)
            expr.alignment = self.types.layout(expr.typ, expr.token).alignment
        elif expr.kind == "function":
            expr.typ = function_type(expr.value)
            self.types.layout(expr.typ, expr.token)
        elif expr.kind == "boolean":
            expr.typ, expr.constant = "bool", expr.value
        elif expr.kind == "null":
            expr.typ = "null"
        elif expr.kind == "string":
            expr.typ = "[]const u8"
            expr.array_length = len(expr.value)
            expr.known_length = len(expr.value)
            expr.alignment = 1
        elif expr.kind == "name":
            variable = self.lookup(expr.token)
            if read and variable.slot not in initialized:
                fail("E0401", expr.token, f"{variable.token.value!r} may be uninitialized", variable.token)
            expr.value, expr.typ = variable, variable.typ
            expr.addressable, expr.writable = True, variable.mutable
            expr.alignment = self.types.layout(expr.typ, expr.token).alignment
        elif expr.kind == "call":
            local_callee = isinstance(expr.value, str) and any(expr.value in scope for scope in self.scopes)
            if local_callee:
                expr.value = Expr(expr.token, "name", expr.value)
            if isinstance(expr.value, str) and expr.value == "slice_from_raw_parts" and expr.value not in self.functions:
                self.raw_slice(expr, initialized)
                if expected is not None:
                    self.coerce(expr, expected)
                expr.aggregate = True
                return expr.typ
            if isinstance(expr.value, str) and expr.value in INTRINSICS and expr.value not in self.functions:
                self.intrinsic(expr, initialized, expected)
                if expected is not None:
                    self.coerce(expr, expected)
                return expr.typ
            if isinstance(expr.value, Expr):
                self.expr(expr.value, initialized)
                signature = function_signature(expr.value.typ)
                if signature is None:
                    fail("E0601", expr.token, f"calling a value of type {expr.value.typ} is not supported")
                self.require_unsafe(expr.token, "function pointer call")
                if len(expr.args) != len(signature.params):
                    fail("E0301", expr.token, f"expected {len(signature.params)} arguments, found {len(expr.args)}")
                for arg, typ in zip(expr.args, signature.params):
                    self.expr(arg, initialized, typ)
                expr.typ, expr.call_abi = signature.returns, signature.abi
                if expected is not None:
                    self.coerce(expr, expected)
                expr.aggregate = self.types.is_aggregate(expr.typ)
                return expr.typ
            function = expr.value if isinstance(expr.value, Function) else self.functions.get(expr.value)
            if function is None:
                if isinstance(expr.value, str) and expr.value in UNSUPPORTED_BUILTINS:
                    fail("E0601", expr.token, f"builtin {expr.value!r} is not implemented")
                fail("E0201", expr.token, f"undefined function {expr.value!r}")
            if function.unsafe:
                self.require_unsafe(expr.token, "call to unsafe function")
            if len(expr.args) != len(function.params):
                fail("E0301", expr.token, f"expected {len(function.params)} arguments, found {len(expr.args)}", function.token)
            for arg, (_, typ) in zip(expr.args, function.params):
                self.expr(arg, initialized, typ)
            expr.value, expr.typ = function, function.returns
            expr.call_abi = function.abi
        elif expr.kind == "unary":
            self.unary(expr, initialized)
        elif expr.kind == "binary":
            for child in expr.args:
                self.expr(child, initialized)
            self.binary(expr)
        elif expr.kind == "field":
            base = expr.args[0]
            self.expr(base, initialized)
            if (self.types.is_array(base.typ) or self.types.is_slice(base.typ)) and expr.value == "len":
                # Keep the receiver evaluation, including bounds checks and
                # calls, even though an array's length is known statically.
                expr.typ = "u64"
                expr.array_length = self.types.array_length(base.typ) if self.types.is_array(base.typ) else None
            elif self.types.is_slice(base.typ) and expr.value == "ptr":
                expr.typ = ("*const " if self.types.readonly(base.typ) else "*") + self.types.element(base.typ)
                expr.alignment = 8
            else:
                layout = self.types.layout(base.typ, base.token)
                member = layout.fields.get(expr.value)
                if member is None:
                    fail("E0201", expr.token, f"type {base.typ} has no field {expr.value!r}")
                self.field_visibility(base.typ, expr.value, expr.token)
                expr.typ, expr.field_offset = member.type, member.offset
                expr.addressable, expr.writable = base.addressable, base.writable
                expr.alignment = gcd(base.alignment, member.offset)
        elif expr.kind == "index":
            base, index = expr.args
            self.expr(base, initialized)
            self.expr(index, initialized, "u64")
            if self.types.is_array(base.typ):
                expr.typ = self.types.element(base.typ)
                expr.array_length = self.types.array_length(base.typ)
                expr.bounds_check = True
                expr.addressable, expr.writable = base.addressable, base.writable
                if index.constant is not None and index.constant >= expr.array_length:
                    fail("E0302", index.token, "constant array index is out of bounds")
            elif self.types.is_slice(base.typ):
                expr.typ = self.types.element(base.typ)
                expr.array_length, expr.bounds_check = None, True
                expr.addressable, expr.writable = True, not self.types.readonly(base.typ)
                known_length = len(base.value) if base.kind == "string" else getattr(base, "known_length", None)
                if known_length is not None and index.constant is not None and index.constant >= known_length:
                    fail("E0302", index.token, "constant slice index is out of bounds")
            elif self.types.is_pointer(base.typ):
                self.require_unsafe(expr.token, "raw pointer indexing")
                expr.typ = self.types.pointee(base.typ)
                expr.array_length, expr.bounds_check = None, False
                expr.addressable, expr.writable = True, not self.types.readonly(base.typ)
            else:
                fail("E0301", base.token, "indexing requires an array, slice, or raw pointer")
            expr.element_size = self.types.layout(expr.typ, expr.token).size
            expr.alignment = self.types.layout(expr.typ, expr.token).alignment
            if self.types.is_array(base.typ):
                offset = expr.element_size * index.constant if index.constant is not None else expr.element_size
                expr.alignment = gcd(base.alignment, offset)
        elif expr.kind == "slice":
            self.slice(expr, initialized)
        elif expr.kind == "cast":
            self.cast(expr, initialized)
        elif expr.kind == "layout":
            builtin, typ, field_name = expr.value
            layout = self.types.layout(typ, expr.token)
            if builtin == "sizeof":
                value = layout.size
            elif builtin == "alignof":
                value = layout.alignment
            else:
                if field_name not in layout.fields:
                    fail("E0201", expr.token, f"type {typ} has no field {field_name!r}")
                self.field_visibility(typ, field_name, expr.token)
                value = layout.fields[field_name].offset
            expr.typ, expr.constant = "u64", value
        elif expr.kind == "struct":
            typ, names = expr.value
            layout = self.types.layout(typ, expr.token)
            if typ not in self.types.structs:
                fail("E0301", expr.token, "struct literal requires a struct type")
            seen = set()
            for name, child in zip(names, expr.args):
                if name in seen:
                    fail("E0201", child.token, f"duplicate field initializer {name!r}")
                seen.add(name)
                if name not in layout.fields:
                    fail("E0201", child.token, f"type {typ} has no field {name!r}")
                self.field_visibility(typ, name, child.token)
                self.expr(child, initialized, layout.fields[name].type)
            missing = set(layout.fields) - seen
            if missing:
                fail("E0301", expr.token, "missing field initializer: " + ", ".join(sorted(missing)))
            expr.typ = typ
        elif expr.kind == "array":
            self.array(expr, initialized, expected)
        else:
            raise AssertionError(expr.kind)
        if expected is not None:
            self.coerce(expr, expected)
        expr.aggregate = self.types.is_aggregate(expr.typ)
        return expr.typ

    def field_visibility(self, typ: str, name: str, token: Token):
        declaration = self.types.structs.get(typ)
        if declaration is None:
            return
        owner = self.function.module or self.module.name
        if declaration.module and declaration.module != owner:
            if not declaration.public or name not in declaration.field_public:
                fail("E0201", token, f"field {typ}.{name} is private to module {declaration.module}")

    def raw_slice(self, expr: Expr, initialized: set[int]):
        self.require_unsafe(expr.token, "slice_from_raw_parts")
        if len(expr.args) != 2:
            fail("E0301", expr.token, f"slice_from_raw_parts expects 2 arguments, found {len(expr.args)}")
        pointer, length = expr.args
        self.expr(pointer, initialized)
        if not self.types.is_pointer(pointer.typ):
            fail("E0301", pointer.token, "slice_from_raw_parts requires a typed raw pointer")
        self.expr(length, initialized, "u64")
        expr.kind = "raw_slice"
        expr.typ = ("[]const " if self.types.readonly(pointer.typ) else "[]") + self.types.pointee(pointer.typ)
        expr.element_size = self.types.layout(self.types.element(expr.typ), expr.token).size
        expr.known_length = length.constant
        expr.alignment = 8

    def intrinsic(self, expr: Expr, initialized: set[int], expected: str | None):
        name = expr.value
        arity = 0 if name == "compiler_fence" else 3 if name == "atomic_compare_exchange" else 1 if name in {"volatile_load", "read_unaligned", "atomic_load"} else 2
        if len(expr.args) != arity:
            fail("E0301", expr.token, f"{name} expects {arity} arguments, found {len(expr.args)}")
        expr.kind = "intrinsic"
        if name in WRAPPING_INTRINSICS:
            for arg in expr.args:
                self.expr(arg, initialized)
                if arg.typ not in INTEGER | {"int"}:
                    fail("E0301", arg.token, f"{name} requires integer operands")
            left, right = expr.args
            typ = left.typ if left.typ != "int" else right.typ
            if typ != "int":
                self.coerce(left, typ)
                self.coerce(right, typ)
            expr.typ = expr.intrinsic_type = typ
            if left.constant is not None and right.constant is not None:
                op = {"wrapping_add": "+", "wrapping_sub": "-", "wrapping_mul": "*"}[name]
                value = constant_op(op, left.constant, right.constant)
                expr.constant = self.wrap(value, typ) if typ != "int" else value
            return
        self.require_unsafe(expr.token, name)
        if name == "compiler_fence":
            expr.typ, expr.intrinsic_type = "void", None
            return
        pointer = expr.args[0]
        self.expr(pointer, initialized)
        if not self.types.is_pointer(pointer.typ):
            fail("E0301", pointer.token, f"{name} requires a raw pointer to an integer")
        typ = self.types.pointee(pointer.typ)
        allowed = {"u32", "u64"} if name.startswith("atomic_") else INTEGER
        if typ not in allowed:
            fail("E0301", pointer.token, f"{name} does not support pointer element type {typ}")
        writing = name in {"volatile_store", "write_unaligned", "atomic_store", "atomic_compare_exchange", "atomic_fetch_add"}
        if writing and self.types.readonly(pointer.typ):
            fail("E0402", pointer.token, f"{name} requires a writable raw pointer")
        for arg in expr.args[1:]:
            self.expr(arg, initialized, typ)
        expr.intrinsic_type = typ
        expr.typ = "void" if name in {"volatile_store", "write_unaligned", "atomic_store"} else typ

    def slice(self, expr: Expr, initialized: set[int]):
        base, low, high = expr.args
        self.expr(base, initialized)
        if self.types.is_array(base.typ):
            if not base.addressable:
                fail("E0601", base.token, "slicing an array temporary is not implemented; bind the array first")
            length = self.types.array_length(base.typ)
            readonly = not base.writable
            natural = self.types.layout(self.types.element(base.typ), expr.token).alignment
            if base.alignment < natural:
                fail("E0601", base.token, "slicing requires a naturally aligned array place")
        elif self.types.is_slice(base.typ):
            length = getattr(base, "known_length", None)
            if base.kind == "string":
                length = len(base.value)
            readonly = self.types.readonly(base.typ)
        else:
            fail("E0301", base.token, "slicing requires an array or slice")
        if low is not None:
            self.expr(low, initialized, "u64")
        if high is not None:
            self.expr(high, initialized, "u64")
        lo_value = 0 if low is None else low.constant
        hi_value = length if high is None else high.constant
        if lo_value is not None and hi_value is not None and lo_value > hi_value:
            fail("E0302", expr.token, "constant slice lower bound exceeds upper bound")
        for bound in (lo_value, hi_value):
            if length is not None and bound is not None and bound > length:
                fail("E0302", expr.token, "constant slice bound is out of bounds")
        expr.typ = ("[]const " if readonly else "[]") + self.types.element(base.typ)
        expr.array_length = self.types.array_length(base.typ) if self.types.is_array(base.typ) else None
        expr.bounds_check = True
        expr.element_size = self.types.layout(self.types.element(base.typ), expr.token).size
        expr.known_length = hi_value - lo_value if lo_value is not None and hi_value is not None else None
        expr.alignment = 8

    def unary(self, expr: Expr, initialized: set[int]):
        child = expr.args[0]
        self.expr(child, initialized)
        if expr.value == "&":
            if child.kind == "constant":
                fail("E0601", expr.token, "compile-time constants have no addressable storage")
            if not child.addressable:
                fail("E0301", expr.token, "address-of requires an initialized place")
            expr.typ = ("*" if child.writable else "*const ") + child.typ
        elif expr.value == "*":
            if not self.types.is_pointer(child.typ):
                fail("E0301", expr.token, "dereference requires a raw pointer")
            self.require_unsafe(expr.token, "raw pointer dereference")
            expr.typ = self.types.pointee(child.typ)
            expr.addressable, expr.writable = True, not self.types.readonly(child.typ)
            expr.alignment = self.types.layout(expr.typ, expr.token).alignment
        elif expr.value == "!":
            self.coerce(child, "bool")
            expr.typ = "bool"
            if child.constant is not None:
                expr.constant = not child.constant
        else:
            if child.typ not in INTEGER | {"int"}:
                fail("E0301", expr.token, "integer unary operator requires an integer")
            expr.typ = child.typ
            if child.constant is not None:
                expr.constant = -child.constant if expr.value == "-" else ~child.constant
                if expr.typ in INTEGER:
                    if expr.value == "~":
                        expr.constant = self.wrap(expr.constant, expr.typ)
                    self.check_constant(expr)

    def base_binary(self, expr: Expr):
        left, right = expr.args
        op = expr.value
        if op in {"&&", "||"}:
            self.coerce(left, "bool")
            self.coerce(right, "bool")
            expr.typ = "bool"
            if left.constant is not None and ((op == "&&" and not left.constant) or (op == "||" and left.constant)):
                expr.constant = bool(left.constant)
        elif is_function_type(left.typ) or is_function_type(right.typ):
            if op not in {"==", "!="} or left.typ != right.typ:
                fail("E0301", expr.token, "function pointers only support == and != with the same function type")
            expr.typ = "bool"
        elif self.types.is_pointer(left.typ) or self.types.is_pointer(right.typ) or left.typ == "null" or right.typ == "null":
            if self.types.is_pointer(left.typ) and op in {"+", "-"}:
                self.require_unsafe(expr.token, "raw pointer arithmetic")
                self.coerce(right, "u64")
                expr.typ = left.typ
                expr.element_size = self.types.layout(self.types.pointee(left.typ), expr.token).size
            elif op in {"==", "!="}:
                if left.typ == "null" and self.types.is_pointer(right.typ):
                    self.coerce(left, right.typ)
                elif right.typ == "null" and self.types.is_pointer(left.typ):
                    self.coerce(right, left.typ)
                elif self.types.is_pointer(left.typ) and self.types.is_pointer(right.typ):
                    if self.types.readonly(right.typ):
                        self.coerce(left, right.typ)
                    else:
                        self.coerce(right, left.typ)
                else:
                    fail("E0301", expr.token, "pointer comparison requires matching pointer types")
                expr.typ = "bool"
            else:
                fail("E0301", expr.token, "raw pointers support ==, !=, and pointer +/- usize only")
        elif op in {"<<", ">>"}:
            if left.typ not in INTEGER | {"int"}:
                fail("E0301", left.token, "shift requires an integer left operand")
            self.coerce(right, "u64")
            expr.typ = left.typ
            self.check_shift(expr, left.typ if left.typ in INTEGER else "u64")
        else:
            if left.typ == "int" and right.typ != "int":
                self.coerce(left, right.typ)
            if right.typ == "int" and left.typ != "int":
                self.coerce(right, left.typ)
            if left.typ != right.typ:
                fail("E0301", expr.token, f"operands have different types: {left.typ} and {right.typ}")
            if left.typ == "bool":
                if op not in {"==", "!="}:
                    fail("E0301", expr.token, "bool only supports ==, !=, !, && and ||")
            elif left.typ not in INTEGER | {"int"}:
                fail("E0301", expr.token, "binary operator requires integer operands")
            if op in COMPARISONS:
                self.materialize(left)
                self.materialize(right)
                expr.typ = "bool"
            else:
                expr.typ = left.typ
        if op in {"/", "%"} and right.constant == 0:
            fail("E0302", right.token, "division by zero in constant operand")
        if op in {"/", "%"} and left.typ in INTEGER and is_signed(left.typ) and left.constant == bounds(left.typ)[0] and right.constant == -1:
            fail("E0302", expr.token, "signed division overflow")
        if left.constant is not None and right.constant is not None and not self.types.is_pointer(expr.typ):
            expr.constant = constant_op(op, left.constant, right.constant)
            if op == "<<" and expr.typ in INTEGER:
                expr.constant = self.wrap(expr.constant, expr.typ)
            self.check_constant(expr)

    def check_shift(self, expr: Expr, typ: str):
        count = expr.args[1]
        if count.constant is not None and count.constant >= bits(typ):
            fail("E0302", count.token, f"shift count must be less than {bits(typ)}")

    def array(self, expr: Expr, initialized: set[int], expected: str | None):
        length = expr.value if expr.value is not None else len(expr.args)
        if not length:
            fail("E0301", expr.token, "empty array literals are not supported")
        element_type = self.types.element(expected) if expected and self.types.is_array(expected) else None
        if expected and self.types.is_array(expected) and self.types.array_length(expected) != length:
            fail("E0301", expr.token, f"expected array length {self.types.array_length(expected)}, found {length}")
        if element_type is None:
            for child in expr.args:
                self.expr(child, initialized)
            for child in expr.args:
                if child.typ not in {"int", "null"}:
                    element_type = child.typ
                    break
            if element_type is None:
                element_type = "i64"
            for child in expr.args:
                self.coerce(child, element_type)
        else:
            for child in expr.args:
                self.expr(child, initialized, element_type)
        expr.typ = f"[{length}]{element_type}"
        self.types.layout(expr.typ, expr.token)

    def cast(self, expr: Expr, initialized: set[int], *, checked=False):
        target, child = expr.value, expr.args[0]
        self.types.layout(target, expr.token)
        if not checked:
            self.expr(child, initialized)
        if child.typ == "int":
            self.materialize(child)
        source = child.typ
        if source in INTEGER | {"bool"} and target in INTEGER:
            if child.constant is not None:
                expr.constant = self.wrap(int(child.constant), target)
        elif source == "null" and self.types.is_pointer(target):
            self.coerce(child, target)
            expr.constant = 0
        elif self.types.is_pointer(source) and self.types.is_pointer(target):
            if source != target and not (self.types.pointee(source) == self.types.pointee(target) and self.types.readonly(target)):
                self.require_unsafe(expr.token, "pointer reinterpretation or removal of const")
        elif self.types.is_slice(source) and self.types.is_slice(target):
            if self.types.element(source) != self.types.element(target):
                fail("E0301", expr.token, f"slice casts require matching element types, found {source} and {target}")
            if self.types.readonly(source) and not self.types.readonly(target):
                self.require_unsafe(expr.token, "removal of slice const")
            expr.known_length = getattr(child, "known_length", None)
            expr.alignment = 8
        elif (source == "u64" and self.types.is_pointer(target)) or (self.types.is_pointer(source) and target == "u64"):
            self.require_unsafe(expr.token, "integer/pointer conversion")
        else:
            fail("E0301", expr.token, f"invalid cast from {source} to {target}")
        expr.typ = target

    @staticmethod
    def wrap(value: int, typ: str) -> int:
        width = bits(typ)
        value &= (1 << width) - 1
        return value - (1 << width) if is_signed(typ) and value >= (1 << (width - 1)) else value

    def check_constant(self, expr: Expr):
        if expr.constant is not None and expr.typ in INTEGER:
            lo, hi = bounds(expr.typ)
            if not lo <= expr.constant <= hi:
                fail("E0302", expr.token, f"constant operation overflows {expr.typ}")

    def base_block(self, statements: list[Stmt], flow: Flow, *, scoped=True) -> Flow:
        if scoped:
            self.scopes.append({})
        for statement in statements:
            prior_reachable = flow.reachable
            result = self.statement(statement, flow)
            flow = Flow(result.initialized, prior_reachable and result.reachable)
        if scoped:
            local_slots = {var.slot for var in self.scopes.pop().values()}
            flow.initialized -= local_slots
        return flow

    def base_statement(self, statement: Stmt, flow: Flow) -> Flow:
        initialized = set(flow.initialized)
        if statement.kind == "binding":
            token, typ = statement.value
            if typ is not None:
                self.types.layout(typ, token)
            if statement.expr is not None:
                self.expr(statement.expr, initialized, typ)
                self.materialize(statement.expr)
                typ = statement.expr.typ
                if typ == "void":
                    fail("E0301", statement.expr.token, "void is not a storable value")
            variable = self.declare(token, typ, statement.token.kind == "var")
            statement.value = variable
            if statement.expr is not None:
                initialized.add(variable.slot)
        elif statement.kind == "assign":
            target, op = statement.value
            # Initialization is tracked for whole variables, never per field.
            self.expr(target, initialized, read=op != "=" or target.kind != "name")
            if not target.addressable:
                fail("E0301", target.token, "assignment requires a place")
            if not target.writable:
                fail("E0402", target.token, "cannot assign an immutable place")
            if op == "=":
                self.expr(statement.expr, initialized, target.typ)
            else:
                self.expr(statement.expr, initialized)
                operation = Expr(statement.token, "binary", op[:-1], [target, statement.expr])
                self.binary(operation)
                self.coerce(operation, target.typ)
            if target.kind == "name":
                initialized.add(target.value.slot)
        elif statement.kind == "return":
            if self.function.returns == "void":
                if statement.expr is not None:
                    fail("E0301", statement.token, "void function requires return;")
            elif statement.expr is None:
                fail("E0301", statement.token, "non-void return requires a value")
            else:
                self.expr(statement.expr, initialized, self.function.returns)
            return Flow(initialized, False)
        elif statement.kind == "call":
            self.expr(statement.expr, initialized)
            self.materialize(statement.expr)
        elif statement.kind == "asm":
            self.require_unsafe(statement.token, "inline assembly")
        elif statement.kind in {"block", "unsafe"}:
            if statement.kind == "unsafe":
                self.unsafe_depth += 1
            try:
                return self.block(statement.body, Flow(initialized, flow.reachable))
            finally:
                if statement.kind == "unsafe":
                    self.unsafe_depth -= 1
        elif statement.kind == "if":
            self.expr(statement.expr, initialized, "bool")
            yes = self.block(statement.body, Flow(set(initialized), flow.reachable and statement.expr.constant is not False))
            no = self.block(statement.otherwise or [], Flow(set(initialized), flow.reachable and statement.expr.constant is not True))
            if statement.expr.constant is not None:
                return yes if statement.expr.constant else no
            if not yes.reachable:
                return no
            if not no.reachable:
                return yes
            return Flow(yes.initialized & no.initialized)
        elif statement.kind == "while":
            self.expr(statement.expr, initialized, "bool")
            breaks: list[set[int]] = []
            self.loops.append(breaks)
            self.block(statement.body, Flow(set(initialized), flow.reachable and statement.expr.constant is not False))
            self.loops.pop()
            if statement.expr.constant is True:
                return Flow(set.intersection(*breaks), True) if breaks else Flow(initialized, False)
            return Flow(initialized)
        elif statement.kind in {"break", "continue"}:
            if not self.loops:
                fail("E0101", statement.token, f"{statement.kind} requires an enclosing loop")
            if statement.kind == "break" and flow.reachable:
                self.loops[-1].append(initialized)
            return Flow(initialized, False)
        else:
            raise AssertionError(statement.kind)
        return Flow(initialized)
