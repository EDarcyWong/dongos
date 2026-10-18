"""Lazy transparent aliases, scalar constants and their layout dependencies."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace

from .checker import Checker
from .model import (ALIASES, INTEGER, WRAPPING_INTRINSICS, Expr, Function, Module, StaticData, StaticObject,
                    StaticRelocation, fail, function_signature, make_function_type)
from .l1_declarations import L1DeclarationsMixin
from .typesys import MAX_SIZE, FieldLayout, Layout, TypeSystem, is_array, element


STATIC_LIMIT = 16 * 1024 * 1024


class SemanticTypes:
    def __init__(self, resolver):
        self.resolver = resolver

    def __getattr__(self, name):
        return getattr(self.resolver.types, name)

    def layout(self, typ, token=None):
        resolver = self.resolver
        layout = resolver.types.layout(typ, token)
        if typ in resolver.by_struct:
            declaration = resolver.by_struct[typ]
            fields = {name.value: FieldLayout(resolver.type_name(raw, declaration.module, name), layout.fields[name.value].offset)
                      for name, raw in resolver.original_fields[typ]}
            return Layout(layout.size, layout.alignment, fields)
        return layout


class StaticChecker(Checker):
    def expr(self, expr, initialized, expected=None, *, read=True):
        original_types = self.types
        if expr.kind == "layout":
            self.types = self.resolver.types
        try:
            result = super().expr(expr, initialized, expected, read=read)
        finally:
            self.types = original_types
        if not self.place_depth and expr.constant is None and expr.typ in INTEGER | {"bool"} and expr.kind in {"field", "index", "orelse"}:
            data = self.resolver.static_value(expr, self.function.module)
            expr.constant = self.resolver.scalar(data)
        return result

    def unary(self, expr, initialized):
        self.place_depth += expr.value == "&"
        try:
            return super().unary(expr, initialized)
        finally:
            self.place_depth -= expr.value == "&"

    def slice(self, expr, initialized):
        self.place_depth += 1
        try:
            return super().slice(expr, initialized)
        finally:
            self.place_depth -= 1

    def binary(self, expr):
        if any(self.types.is_pointer(child.typ) or function_signature(child.typ) is not None or child.typ == "null" for child in expr.args):
            fail("E0601", expr.token, "address comparison and arithmetic are not constant expressions")
        return super().binary(expr)

    def cast(self, expr, initialized):
        self.expr(expr.args[0], initialized)
        source, target = expr.args[0].typ, expr.value
        if self.types.is_pointer(source) and target in INTEGER or source in INTEGER | {"int"} and self.types.is_pointer(target):
            fail("E0601", expr.token, "address/integer conversion is not a constant expression")
        return super().cast(expr, initialized, checked=True)


class LazyTypes(TypeSystem):
    """Use the target's layout rules while preparing dependent declarations."""
    def __init__(self, resolver, module):
        super().__init__(Module(module.name, module.token, []))
        self.resolver = resolver
        self.structs = resolver.by_struct
        self.enums = resolver.by_enum

    def layout(self, typ, token=None):
        # An indirection's size does not depend on its target. Full target
        # validation runs after constants and structure sizes have settled.
        if self.is_pointer(typ):
            return Layout(8, 8)
        if typ in self.enums:
            return Layout(16 if any(child is not None for _,child in self.enums[typ].variants) else 8,8)
        if self.is_optional(typ) or self.is_result(typ):
            return Layout(16, 8)
        if self.is_slice(typ):
            return Layout(16, 8)
        if function_signature(typ) is not None:
            return Layout(8, 8)
        if typ in self.structs:
            self.resolver.prepare_struct(typ)
        return super().layout(typ, token)

    def _validate_reference(self, typ, token, visited):
        if is_array(typ):
            self._validate_reference(element(typ), token, visited)
            self._references.setdefault(typ, token)
            return
        return super()._validate_reference(typ, token, visited)


class Declarations(L1DeclarationsMixin):
    def __init__(self, units, sources, entry):
        self.extract_methods(units)
        self.units, self.sources, self.entry = units, sources, entry
        self.qualified = len(units) > 1
        self.functions, self.structures, self.aliases, self.constants, self.globals = {}, {}, {}, {}, {}
        self.imports = {}
        self.active = []
        self.alias_values, self.constant_values, self.length_values = {}, {}, {}
        self.layout_requests = []
        self.prepared_structs = set()
        self.original_fields = {}
        self.by_struct = {}
        self.static_objects, self.static_bytes, self.by_symbol = [], 0, {}
        self.declared_types = {}
        self.prepared_functions = set()
        for owner, unit in units.items():
            self.imports[owner] = {item.alias: item.path for item in unit.imports}
            namespace = {item.alias: item for item in unit.imports}
            for attribute, table in (("functions", self.functions), ("structs", self.structures),
                                     ("aliases", self.aliases), ("constants", self.constants), ("globals", self.globals)):
                table[owner] = {}
                for declaration in getattr(unit, attribute):
                    name = declaration.token.value
                    if name in namespace:
                        fail("E0201", declaration.token, f"duplicate declaration {name!r}", namespace[name].token)
                    if attribute in {"structs", "aliases"} and name in INTEGER | {"bool", "void", "usize", "isize"}:
                        fail("E0201", declaration.token, f"cannot redefine built-in type {name!r}")
                    namespace[name] = declaration
                    table[owner][name] = declaration
                    declaration.module, declaration.local_name = owner, name
                    declaration.token = replace(declaration.token, value=self.symbol(owner, name))
                    if attribute in {"constants", "globals"}:
                        suffix = "c" if attribute == "constants" else "g"
                        declaration.symbol = f"__dg_m{owner.encode('utf-8').hex()}_{suffix}{name.encode('utf-8').hex()}"
                        self.by_symbol[declaration.symbol] = declaration
                    if attribute == "structs":
                        self.by_struct[declaration.token.value] = declaration
                        self.original_fields[declaration.token.value] = list(declaration.fields)
        self.module = Module(entry, units[entry].token, [], list(self.by_struct.values()))
        self.setup_l1()
        self.types = LazyTypes(self, self.module)

    def symbol(self, owner, local):
        return owner + "." + local if self.qualified else local

    @contextmanager
    def dependency(self, key, token):
        if key in self.active:
            names = [str(item[-1]) for item in self.active[self.active.index(key):] + [key]]
            fail("E0302", token, "cyclic constant, alias or layout dependency: " + " -> ".join(names))
        self.active.append(key)
        try:
            yield
        finally:
            self.active.pop()

    def declaration(self, name, owner, tables, token, kind):
        if "." in name:
            alias, _, local = name.partition(".")
            target = self.imports[owner].get(alias)
            declaration = tables.get(target, {}).get(local)
            if declaration is None or not declaration.public:
                fail("E0201", token, f"{kind} {name!r} is missing or private")
            return target, local, declaration
        declaration = tables[owner].get(name)
        return owner, name, declaration

    def base_type_name(self, typ, owner, token, locals_=frozenset()):
        signature = function_signature(typ)
        if signature is not None:
            return make_function_type([self.type_name(param, owner, token, locals_) for param in signature.params],
                                      self.type_name(signature.returns, owner, token, locals_),
                                      signature.abi, signature.unsafe)
        for prefix in ("*const ", "*", "[]const ", "[]"):
            if typ.startswith(prefix):
                return prefix + self.type_name(typ[len(prefix):], owner, token, locals_)
        if typ.startswith("["):
            end = typ.index("]")
            count = typ[1:end]
            if count.startswith("@"):
                key = (owner, count)
                if key not in self.length_values:
                    expression = self.units[owner].type_lengths[count]
                    with self.dependency(("length", owner, count), expression.token):
                        self.length_values[key] = self.integer(expression, owner, "array length", positive=True, locals_=locals_)
                count = self.length_values[key]
            return f"[{count}]" + self.type_name(typ[end + 1:], owner, token, locals_)
        if typ in INTEGER | {"bool", "void", "usize", "isize"}:
            return ALIASES.get(typ, typ)
        # Resolve aliases and structures through the same import visibility rule.
        combined = {name: dict(self.structures[name], **self.aliases[name]) for name in self.units}
        target, local, declaration = self.declaration(typ, owner, combined, token, "type")
        if declaration is None:
            return typ  # TypeSystem supplies the unknown-type diagnostic.
        if local in self.aliases[target]:
            return self.alias(target, local)
        return self.symbol(target, local)

    def alias(self, owner, local):
        key = owner, local
        if key not in self.alias_values:
            declaration = self.aliases[owner][local]
            with self.dependency(("alias", owner, local), declaration.token):
                self.alias_values[key] = self.type_name(declaration.target, owner, declaration.token)
        return self.alias_values[key]

    def prepare_struct(self, name):
        if name in self.prepared_structs:
            return
        declaration = self.by_struct[name]
        with self.dependency(("struct", name), declaration.token):
            declaration.fields = [(token, self.layout_type(typ, declaration.module, token)) for token, typ in self.original_fields[name]]
            if isinstance(declaration.alignment, Expr):
                declaration.alignment = self.integer(declaration.alignment, declaration.module, "alignment", positive=True)
            self.prepared_structs.add(name)

    def base_layout_type(self, typ, owner, token, locals_=frozenset()):
        """Expand by-value dependencies, stopping at pointer/slice boundaries."""
        if function_signature(typ) is not None:
            return typ
        if typ.startswith("*") or typ.startswith("[]"):
            return typ
        if typ.startswith("["):
            end = typ.index("]")
            count = typ[1:end]
            if count.startswith("@"):
                count = self.integer(self.units[owner].type_lengths[count], owner, "array length", positive=True, locals_=locals_)
            return f"[{count}]" + self.layout_type(typ[end + 1:], owner, token, locals_)
        if typ in INTEGER | {"bool", "void", "usize", "isize"}:
            return ALIASES.get(typ, typ)
        combined = {name: dict(self.structures[name], **self.aliases[name]) for name in self.units}
        target, local, declaration = self.declaration(typ, owner, combined, token, "type")
        if declaration is None:
            return typ
        if local in self.aliases[target]:
            with self.dependency(("layout-alias", target, local), declaration.token):
                return self.layout_type(declaration.target, target, declaration.token)
        return self.symbol(target, local)

    def checker(self, owner):
        # Avoid eager TypeSystem construction; all expression rules remain the
        # ordinary checker rules, including contextual shifts and typed overflow.
        checker = object.__new__(StaticChecker)
        checker.module, checker.types = self.module, SemanticTypes(self)
        checker.resolver, checker.place_depth = self, 0
        checker.functions, checker.scopes, checker.loops = {}, [{}], []
        checker.unsafe_depth = 0
        checker.function = Function(self.units[owner].token, [], "void", [], None, module=owner)
        return checker

    def base_prepare_function(self, function):
        key = function.module, function.local_name
        if key not in self.prepared_functions:
            with self.dependency(("function-signature", *key), function.token):
                function.params = [(token, self.type_name(typ, function.module, token)) for token, typ in function.params]
                function.returns = self.type_name(function.returns, function.module, function.token)
                function.symbol = function.export or (function.local_name if function.external else
                    f"__dg_m{function.module.encode('utf-8').hex()}_f{function.local_name.encode('utf-8').hex()}")
                self.prepared_functions.add(key)
        return function

    def lower_function(self, expr, function):
        expr.kind, expr.value, expr.args = "function", self.prepare_function(function), []

    def constant(self, owner, local):
        key = owner, local
        if key not in self.constant_values:
            declaration = self.constants[owner][local]
            data = self.initialize(declaration)
            value = self.scalar(data) if data.typ in INTEGER | {"bool"} else data
            self.constant_values[key] = data.typ, value
        return self.constant_values[key]

    def object_type(self, declaration):
        if declaration.symbol not in self.declared_types:
            with self.dependency(("object-type", declaration.symbol), declaration.token):
                typ = self.type_name(declaration.typ, declaration.module, declaration.token)
                self.declared_types[declaration.symbol] = typ
                declaration.typ = typ
        return self.declared_types[declaration.symbol]

    def check_size(self, size, token):
        if size > STATIC_LIMIT:
            fail("E0601", token, "static object exceeds the 16 MiB materialization budget")

    def add_object(self, obj, token):
        if self.static_bytes + len(obj.data) > STATIC_LIMIT:
            fail("E0601", token, "static objects exceed the 16 MiB materialization budget")
        self.static_bytes += len(obj.data)
        self.static_objects.append(obj)
        self.by_symbol[obj.symbol] = self.by_symbol.get(obj.symbol, obj)

    def initialize(self, declaration):
        if declaration.initializer is not None:
            return declaration.initializer
        with self.dependency(("constant-value", declaration.symbol), declaration.token):
            typ = self.object_type(declaration)
            layout = SemanticTypes(self).layout(typ, declaration.token)
            self.check_size(layout.size, declaration.token)
            expression = deepcopy(declaration.expr)
            self.expression(expression, declaration.module, set(), constant=True)
            self.checker(declaration.module).expr(expression, set(), typ)
            self.validate_reads(expression)
            data = self.static_value(expression, declaration.module)
            declaration.initializer = StaticData(typ, data.data, list(data.relocations))
            self.add_object(StaticObject(declaration.symbol, typ, data.data, layout.alignment,
                                         getattr(declaration, "mutable", False), list(data.relocations)), declaration.token)
        return declaration.initializer

    @staticmethod
    def scalar(data):
        if data.relocations:
            raise AssertionError("symbolic address used as scalar")
        value = int.from_bytes(data.data, "little", signed=data.typ.startswith("i"))
        return bool(value) if data.typ == "bool" else value

    def validate_reads(self, expr, *, place=False):
        if expr is None:
            return
        if expr.kind == "global" and getattr(expr.value, "mutable", False) and not place:
            fail("E0601", expr.token, "mutable global values cannot be read in a constant expression")
        for index, child in enumerate(expr.args):
            base_place = index == 0 and (place or expr.kind == "unary" and expr.value == "&"
                or expr.kind == "slice" and self.types.is_array(child.typ)
                or expr.kind == "field" and expr.value == "len" and self.types.is_array(child.typ))
            self.validate_reads(child, place=base_place)

    def segment(self, data, offset, typ, token):
        size = self.types.layout(typ, token).size
        if offset < 0 or offset + size > len(data.data):
            fail("E0302", token, "constant access is outside its backing object")
        relocs = [StaticRelocation(item.offset - offset, item.symbol, item.addend)
                  for item in data.relocations if offset <= item.offset and item.offset + 8 <= offset + size]
        return StaticData(typ, data.data[offset:offset + size], relocs)

    def pointer(self, data, offset=0):
        relocation = next((item for item in data.relocations if item.offset == offset), None)
        return (relocation.symbol, relocation.addend) if relocation else (None, int.from_bytes(data.data[offset:offset + 8], "little"))

    def address_data(self, typ, address):
        symbol, addend = address
        return StaticData(typ, bytes(8) if symbol else addend.to_bytes(8, "little"),
                          [StaticRelocation(0, symbol, addend)] if symbol else [])

    def place(self, expr, owner):
        if expr.kind == "global":
            return expr.value.symbol, 0
        if expr.kind == "field":
            symbol, offset = self.place(expr.args[0], owner)
            return symbol, offset + expr.field_offset
        if expr.kind == "index":
            base, index = expr.args
            position = self.scalar(self.static_value(index, owner))
            if self.types.is_array(base.typ):
                address = self.place(base, owner)
            elif self.types.is_slice(base.typ):
                backing = self.static_value(base, owner)
                if position >= int.from_bytes(backing.data[8:16], "little"):
                    fail("E0302", index.token, "constant slice index is out of bounds")
                address = self.pointer(backing)
            else:
                fail("E0601", expr.token, "constant addresses require a global array place")
            return address[0], address[1] + position * expr.element_size
        fail("E0601", expr.token, "constant address requires a named global place")

    def read_address(self, address, typ, token):
        symbol, offset = address
        obj = self.by_symbol.get(symbol)
        if obj is None or getattr(obj, "mutable", False):
            fail("E0601", token, "mutable global values cannot be read in a constant expression")
        data = self.initialize(obj) if hasattr(obj, "initializer") else StaticData(obj.typ, obj.data, obj.relocations)
        return self.segment(data, offset, typ, token)

    def base_static_value(self, expr, owner):
        if hasattr(expr, "static_data"):
            data = expr.static_data
            return StaticData(expr.typ, data.data, list(data.relocations))
        layout = self.types.layout(expr.typ, expr.token)
        self.check_size(layout.size, expr.token)
        if expr.constant is not None:
            value = int(expr.constant) & ((1 << (layout.size * 8)) - 1)
            data = StaticData(expr.typ, value.to_bytes(layout.size, "little"), [])
        elif expr.kind == "global":
            if getattr(expr.value, "mutable", False):
                fail("E0601", expr.token, "mutable global values cannot be read in a constant expression")
            original = self.initialize(expr.value)
            data = StaticData(expr.typ, original.data, list(original.relocations))
        elif expr.kind == "function":
            data = self.address_data(expr.typ, (expr.value.symbol, 0))
        elif expr.kind == "unary" and expr.value == "&":
            data = self.address_data(expr.typ, self.place(expr.args[0], owner))
        elif expr.kind == "cast":
            original = self.static_value(expr.args[0], owner)
            data = StaticData(expr.typ, original.data, list(original.relocations))
        elif expr.kind in {"struct", "array"}:
            contents, relocations = bytearray(layout.size), []
            if expr.kind == "struct":
                fields = SemanticTypes(self).layout(expr.typ, expr.token).fields
                children = [(fields[name].offset, child) for name, child in zip(expr.value[1], expr.args)]
            else:
                stride = self.types.layout(self.types.element(expr.typ)).size
                if expr.value is not None:
                    value = self.static_value(expr.args[0], owner)
                    contents[:] = value.data * expr.value
                    relocations = [StaticRelocation(i * stride + item.offset, item.symbol, item.addend)
                                   for i in range(expr.value) for item in value.relocations]
                    data = StaticData(expr.typ, bytes(contents), relocations)
                    expr.static_data = data
                    return data
                children = ((i * stride, child) for i, child in enumerate(expr.args))
            for offset, child in children:
                value = self.static_value(child, owner)
                contents[offset:offset + len(value.data)] = value.data
                relocations.extend(StaticRelocation(offset + item.offset, item.symbol, item.addend) for item in value.relocations)
            data = StaticData(expr.typ, bytes(contents), relocations)
        elif expr.kind == "string":
            symbol = "__dg_static_string_" + str(len(self.static_objects))
            self.add_object(StaticObject(symbol, f"[{len(expr.value)}]u8", expr.value, 1), expr.token)
            data = StaticData(expr.typ, bytes(8) + len(expr.value).to_bytes(8, "little"), [StaticRelocation(0, symbol)])
        elif expr.kind == "field":
            base = expr.args[0]
            if self.types.is_array(base.typ) and expr.value == "len":
                data = StaticData("u64", self.types.array_length(base.typ).to_bytes(8, "little"), [])
            elif self.types.is_slice(base.typ):
                data = self.segment(self.static_value(base, owner), 8 if expr.value == "len" else 0, expr.typ, expr.token)
            else:
                data = self.segment(self.static_value(base, owner), expr.field_offset, expr.typ, expr.token)
        elif expr.kind == "index":
            base, index = expr.args
            position = self.scalar(self.static_value(index, owner))
            if self.types.is_array(base.typ):
                data = self.segment(self.static_value(base, owner), position * expr.element_size, expr.typ, expr.token)
            else:
                backing = self.static_value(base, owner)
                length = int.from_bytes(backing.data[8:16], "little")
                if position >= length:
                    fail("E0302", index.token, "constant slice index is out of bounds")
                symbol, offset = self.pointer(backing)
                data = self.read_address((symbol, offset + position * expr.element_size), expr.typ, expr.token)
        elif expr.kind == "slice":
            base, lower, upper = expr.args
            if self.types.is_array(base.typ):
                pointer, length = self.place(base, owner), self.types.array_length(base.typ)
            else:
                backing = self.static_value(base, owner)
                pointer, length = self.pointer(backing), int.from_bytes(backing.data[8:16], "little")
            lo = self.scalar(self.static_value(lower, owner)) if lower else 0
            hi = self.scalar(self.static_value(upper, owner)) if upper else length
            if not 0 <= lo <= hi <= length:
                fail("E0302", expr.token, "constant slice range is out of bounds")
            pointer = pointer[0], pointer[1] + lo * expr.element_size
            address = self.address_data("*u8", pointer)
            data = StaticData(expr.typ, address.data + (hi - lo).to_bytes(8, "little"), address.relocations)
        else:
            fail("E0601", expr.token, "initializer is not a supported constant expression")
        expr.static_data = data
        return data

    def integer(self, expression, owner, purpose, *, positive=False, locals_=frozenset()):
        expression = deepcopy(expression)
        self.expression(expression, owner, locals_, constant=True)
        checker = self.checker(owner)
        checker.expr(expression, set())
        def untyped_wrapping(node):
            return node is not None and ((node.kind == "intrinsic" and node.value in WRAPPING_INTRINSICS and node.typ == "int")
                                         or any(untyped_wrapping(child) for child in node.args))
        if expression.typ == "int" and untyped_wrapping(expression):
            # Shapes accept any integer width. A wrapping operation still needs
            # its ordinary default width when no typed operand supplied one;
            # unrelated pure arithmetic retains arbitrary-precision folding.
            checker.materialize(expression)
        self.validate_reads(expression)
        if expression.typ not in INTEGER | {"int"} or expression.constant is None:
            fail("E0301", expression.token, f"{purpose} requires a compile-time integer")
        value = expression.constant
        if positive and value <= 0:
            fail("E0302", expression.token, f"{purpose} must be positive")
        if value > MAX_SIZE:
            fail("E0302", expression.token, f"{purpose} exceeds the x86-64 object size limit")
        return value

    @staticmethod
    def member(expr):
        if expr.kind == "name":
            return [expr.value]
        if expr.kind == "field":
            base = Declarations.member(expr.args[0])
            if base:
                return base + [expr.value]
        return None

    def lower_object(self, expr, declaration, *, place=False):
        typ = self.object_type(declaration)
        if not place and not getattr(declaration, "mutable", False) and typ in INTEGER | {"bool"}:
            expr.kind, expr.value, expr.args = "constant", self.constant(declaration.module, declaration.local_name), []
        else:
            expr.kind, expr.value, expr.args = "global", declaration, []

    def base_expression(self, expr, owner, locals_, *, constant=False, place=False):
        if expr is None:
            return
        if constant and expr.kind == "name" and expr.value in locals_:
            fail("E0601", expr.token, "local values cannot be used in compile-time expressions")
        if expr.kind == "name" and expr.value not in locals_:
            if expr.value in self.constants[owner]:
                self.lower_object(expr, self.constants[owner][expr.value], place=place)
                return
            if expr.value in self.globals[owner]:
                self.lower_object(expr, self.globals[owner][expr.value], place=True)
                return
            if expr.value in self.functions[owner]:
                self.lower_function(expr, self.functions[owner][expr.value])
                return
        if expr.kind == "field":
            parts = self.member(expr)
            if parts and len(parts) == 2 and parts[0] in self.imports[owner] and parts[0] not in locals_:
                tables = {name: dict(self.functions[name], **self.constants[name], **self.globals[name]) for name in self.units}
                target, local, declaration = self.declaration(".".join(parts), owner, tables, expr.token, "global")
                if isinstance(declaration, Function):
                    self.lower_function(expr, declaration)
                else:
                    self.lower_object(expr, declaration, place=place)
                return
        if expr.kind == "call":
            if isinstance(expr.value, str) and expr.value not in locals_ and (expr.value in self.aliases[owner] or expr.value in self.structures[owner] or expr.value in self.imports[owner]):
                fail("E0601", expr.token, "types and module namespaces cannot be called")
            pure_builtin = isinstance(expr.value, str) and expr.value in WRAPPING_INTRINSICS and expr.value not in locals_ and expr.value not in self.functions[owner] and expr.value not in self.constants[owner] and expr.value not in self.globals[owner]
            if constant and not pure_builtin:
                fail("E0601", expr.token, "runtime calls are not allowed in constant expressions")
            if isinstance(expr.value, Expr):
                parts = self.member(expr.value)
                if parts and len(parts) == 2 and parts[0] in self.imports[owner] and parts[0] not in locals_ and parts[1] in self.functions[self.imports[owner][parts[0]]]:
                    target, local, function = self.declaration(".".join(parts), owner, self.functions, expr.token, "function")
                    expr.value = self.symbol(target, local)
                else:
                    self.expression(expr.value, owner, locals_)
            elif expr.value not in locals_ and expr.value in self.functions[owner]:
                expr.value = self.symbol(owner, expr.value)
            elif expr.value in locals_ or expr.value in self.constants[owner] or expr.value in self.globals[owner]:
                callee = Expr(expr.token, "name", expr.value)
                self.expression(callee, owner, locals_)
                expr.value = callee
        if constant and (expr.kind not in {"integer", "boolean", "null", "constant", "global", "function", "string", "array", "struct", "field", "index", "slice", "name", "unary", "binary", "cast", "layout", "call"}
                         or expr.kind == "unary" and expr.value == "*"):
            fail("E0601", expr.token, "this expression is not supported in a scalar constant")
        if expr.kind == "struct":
            name, fields = expr.value
            expr.value = self.type_name(name, owner, expr.token, locals_), fields
        elif expr.kind == "cast":
            expr.value = self.type_name(expr.value, owner, expr.token, locals_)
        elif expr.kind == "layout":
            builtin, name, field = expr.value
            # Computing an indirection's size must not evaluate dimensions in
            # its target. Keep the original request for strict validation after
            # all constant sizes have settled.
            normalized = self.layout_type(name, owner, expr.token, locals_) if constant else self.type_name(name, owner, expr.token, locals_)
            expr.value = builtin, normalized, field
            self.layout_requests.append((owner, name, expr.token, frozenset(locals_)))
        elif expr.kind == "array" and isinstance(expr.value, Expr):
            expr.value = self.integer(expr.value, owner, "array repeat count", positive=True, locals_=locals_)
        for index, argument in enumerate(expr.args):
            child_place = index == 0 and (place or expr.kind == "slice" or expr.kind == "unary" and expr.value == "&")
            self.expression(argument, owner, locals_, constant=constant, place=child_place)

    def base_block(self, statements, owner, outer):
        locals_ = set(outer)
        for statement in statements:
            if statement.kind == "binding":
                token, typ = statement.value
                if typ is not None:
                    statement.value = token, self.type_name(typ, owner, token, locals_)
                self.expression(statement.expr, owner, locals_)
                locals_.add(token.value)
            else:
                if statement.kind == "assign":
                    target = statement.value[0]
                    self.expression(target, owner, locals_)
                    if target.kind == "constant":
                        fail("E0402", target.token, "cannot assign a compile-time constant")
                self.expression(statement.expr, owner, locals_)
                self.block(statement.body, owner, locals_)
                self.block(statement.otherwise or [], owner, locals_)

    def base_public_type(self, typ, token):
        while typ.startswith("*") or typ.startswith("["):
            if typ.startswith("*const "):
                typ = typ[7:]
            elif typ.startswith("*"):
                typ = typ[1:]
            elif typ.startswith("[]const "):
                typ = typ[8:]
            elif typ.startswith("[]"):
                typ = typ[2:]
            else:
                typ = typ[typ.index("]") + 1:]
        signature = function_signature(typ)
        if signature is not None:
            for param in signature.params:
                self.public_type(param, token)
            self.public_type(signature.returns, token)
            return
        declaration = self.by_struct.get(typ)
        if declaration and not declaration.public:
            fail("E0201", token, f"public signature exposes private type {typ!r}")

    def base_resolve(self):
        for owner in sorted(self.units):
            for local in self.constants[owner]:
                self.constant(owner, local)
            for declaration in self.globals[owner].values():
                self.initialize(declaration)
        for owner in sorted(self.units):
            for local, declaration in self.aliases[owner].items():
                typ = self.alias(owner, local)
                self.types.validate(typ, declaration.token)
                if declaration.public:
                    self.public_type(typ, declaration.token)
        for name, declaration in self.by_struct.items():
            self.types.layout(name, declaration.token)
        # Provisional layouts intentionally retained raw pointer/slice targets.
        # Resolve every target now, then the ordinary TypeSystem validates all
        # referenced objects, including arrays hidden behind indirections.
        for name, declaration in self.by_struct.items():
            declaration.fields = [(token, self.type_name(typ, declaration.module, token)) for token, typ in self.original_fields[name]]
            if declaration.public:
                for token, typ in declaration.fields:
                    if token.value in declaration.field_public:
                        self.public_type(typ, token)
        final_types = TypeSystem(self.module)
        for (owner, local), typ in self.alias_values.items():
            final_types.validate(typ, self.aliases[owner][local].token)
        for declaration in self.by_symbol.values():
            if hasattr(declaration, "initializer"):
                final_types.layout(declaration.typ, declaration.token)
                if declaration.public:
                    self.public_type(declaration.typ, declaration.token)
        merged_functions = []
        for owner in sorted(self.units):
            for function in self.functions[owner].values():
                function.source_path = function.token.path or owner.replace(".", "/") + ".dg"
                self.prepare_function(function)
                self.block(function.body, owner, {token.value for token, _ in function.params}, top=True)
                if function.public:
                    for token, typ in function.params:
                        self.public_type(typ, token)
                    self.public_type(function.returns, function.token)
                merged_functions.append(function)
        for owner, raw_type, token, locals_ in self.layout_requests:
            final_types.layout(self.type_name(raw_type, owner, token, locals_), token)
        result = Module(self.entry, self.units[self.entry].token, merged_functions, list(self.by_struct.values()))
        result.globals = [item for owner in sorted(self.units) for item in self.globals[owner].values()]
        result.constants = [item for owner in sorted(self.units) for item in self.constants[owner].values()]
        result.static_objects = list(self.static_objects)
        result.sources, result.modules = dict(self.sources), sorted(self.units)
        return result
