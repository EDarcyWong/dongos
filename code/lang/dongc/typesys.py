"""The shared target layout model for Dong's x86-64 compiler."""
from __future__ import annotations

from dataclasses import dataclass, field
import re

from .model import ALIASES, INTEGER, Module, StructDecl, Token, bits, fail, function_signature, is_function_type


MAX_SIZE = (1 << 63) - 1


@dataclass(frozen=True)
class FieldLayout:
    type: str
    offset: int


@dataclass(frozen=True)
class Layout:
    size: int
    alignment: int
    fields: dict[str, FieldLayout] = field(default_factory=dict)


def is_pointer(typ: str) -> bool:
    return typ.startswith("*")


def is_array(typ: str) -> bool:
    return bool(re.match(r"^\[[0-9]+\]", typ))


def is_slice(typ: str) -> bool:
    return typ.startswith("[]")


def is_optional(typ: str) -> bool:
    return typ.startswith("?")


def is_result(typ: str) -> bool:
    return typ.startswith("!")


def payload(typ: str) -> str:
    if not (is_optional(typ) or is_result(typ)):
        raise ValueError(f"not an optional or result type: {typ}")
    return typ[1:]


def is_scalar_payload(typ: str) -> bool:
    return typ in INTEGER | {"bool"} or is_pointer(typ) or is_function_type(typ)


def readonly(typ: str) -> bool:
    return typ.startswith(("*const ", "[]const "))


def pointee(typ: str) -> str:
    if not is_pointer(typ):
        raise ValueError(f"not a pointer type: {typ}")
    return typ[7:] if readonly(typ) else typ[1:]


def element(typ: str) -> str:
    if is_slice(typ):
        return typ[8:] if readonly(typ) else typ[2:]
    if not is_array(typ):
        raise ValueError(f"not an array or slice type: {typ}")
    return typ[typ.index("]") + 1:]


def array_length(typ: str) -> int:
    if not is_array(typ):
        raise ValueError(f"not an array type: {typ}")
    return int(typ[1:typ.index("]")])


class TypeSystem:
    is_pointer = staticmethod(is_pointer)
    is_array = staticmethod(is_array)
    is_slice = staticmethod(is_slice)
    is_optional = staticmethod(is_optional)
    is_result = staticmethod(is_result)
    payload = staticmethod(payload)
    is_scalar_payload = staticmethod(is_scalar_payload)
    readonly = staticmethod(readonly)
    pointee = staticmethod(pointee)
    element = staticmethod(element)
    array_length = staticmethod(array_length)
    is_function_type = staticmethod(is_function_type)
    is_function = staticmethod(is_function_type)
    function_signature = staticmethod(function_signature)

    def __init__(self, module: Module):
        self.module = module
        self.structs: dict[str, StructDecl] = {}
        self.enums = {}
        self._layouts: dict[str, Layout] = {}
        self._active: set[str] = set()
        self._references: dict[str, Token] = {}
        for declaration in module.structs:
            name = declaration.token.value
            if name in self.structs:
                fail("E0201", declaration.token, f"duplicate type {name!r}", self.structs[name].token)
            if name in INTEGER | {"bool", "void", "noreturn", "usize", "isize"}:
                fail("E0201", declaration.token, f"cannot redefine built-in type {name!r}")
            self.structs[name] = declaration
        for declaration in module.enums:
            name = declaration.token.value
            if name in self.structs or name in self.enums:
                prior = self.structs.get(name) or self.enums[name]
                fail("E0201", declaration.token, f"duplicate type {name!r}", prior.token)
            if name in INTEGER | {"bool", "void", "noreturn", "usize", "isize"}:
                fail("E0201", declaration.token, f"cannot redefine built-in type {name!r}")
            self.enums[name] = declaration
        # Validate all declarations, including ones never referenced by a function.
        for name, declaration in self.structs.items():
            self.layout(name, declaration.token)
        for name, declaration in self.enums.items():
            self.layout(name, declaration.token)
        for typ, token in sorted(self._references.items()):
            self.layout(typ, token)

    def is_aggregate(self, typ: str) -> bool:
        return is_array(typ) or self.is_pair(typ) or typ in self.structs

    def is_enum(self, typ: str) -> bool:
        return typ in self.enums

    def is_pair(self, typ: str) -> bool:
        return is_slice(typ) or is_optional(typ) or is_result(typ) or (typ in self.enums and any(value is not None for _, value in self.enums[typ].variants))

    def is_scalar(self, typ: str) -> bool:
        return is_scalar_payload(typ) or typ in self.enums and not self.is_pair(typ)

    def _token(self, token: Token | None) -> Token:
        return token if token is not None else self.module.token

    def validate(self, typ: str, token: Token | None = None):
        token = self._token(token)
        typ = ALIASES.get(typ, typ)
        if typ in INTEGER | {"bool", "void", "noreturn"}:
            return
        if is_function_type(typ):
            self.validate_function(typ, token)
            return
        if is_pointer(typ) or is_slice(typ):
            target = pointee(typ) if is_pointer(typ) else element(typ)
            if target in {"void", "noreturn"}:
                fail("E0302", token, "pointers and slices to void/noreturn are not allowed; use u8 elements")
            self._validate_reference(target, token, set())
            return
        self.layout(typ, token)

    def _validate_reference(self, typ: str, token: Token, visited: set[str]):
        """Check pointer targets without following by-value recursive layouts."""
        if typ in INTEGER | {"bool"} or typ in self.structs or typ in self.enums:
            return
        if is_function_type(typ):
            self.validate_function(typ, token)
            return
        if typ in {"void", "noreturn"}:
            fail("E0302", token, "void/noreturn cannot be used as a pointer, array or slice element type")
        if is_pointer(typ):
            self._validate_reference(pointee(typ), token, visited)
        elif is_slice(typ):
            self._validate_reference(element(typ), token, visited)
        elif is_optional(typ) or is_result(typ):
            self.validate_pair(typ, token)
        elif is_array(typ):
            if array_length(typ) <= 0:
                fail("E0302", token, "array length must be positive")
            self._validate_reference(element(typ), token, visited)
            # Recursive pointer targets do not contribute to their containing
            # object's size. Validate their arrays after the containing layout.
            if self._active:
                self._references.setdefault(typ, token)
            else:
                self.layout(typ, token)
        else:
            fail("E0301", token, f"unknown or non-storable type {typ!r}")

    def layout(self, typ: str, token: Token | None = None) -> Layout:
        token = self._token(token)
        typ = ALIASES.get(typ, typ)
        if typ in self._layouts:
            return self._layouts[typ]
        if typ in INTEGER:
            size = bits(typ) // 8
            result = Layout(size, size)
        elif typ == "bool":
            result = Layout(1, 1)
        elif typ in {"void", "noreturn"}:
            fail("E0302", token, f"{typ} has no object layout")
        elif is_function_type(typ):
            self.validate_function(typ, token)
            result = Layout(8, 8)
        elif is_pointer(typ):
            self.validate(typ, token)
            result = Layout(8, 8)
        elif is_slice(typ):
            self.validate(typ, token)
            result = Layout(16, 8)
        elif is_optional(typ) or is_result(typ):
            self.validate_pair(typ, token)
            result = Layout(16, 8)
        elif typ in self.enums:
            declaration = self.enums[typ]
            # A function-pointer payload may mention this enum in its own
            # signature. The enum's representation is known from its variants,
            # and the code pointer does not recursively embed that signature.
            if typ in self._active:
                return Layout(16 if self.is_pair(typ) else 8, 8)
            self._active.add(typ)
            try:
                if not declaration.variants:
                    fail("E0302", declaration.token, "empty enums are not allowed")
                seen = {}
                for variant, child in declaration.variants:
                    if variant.value in seen:
                        fail("E0201", variant, f"duplicate enum variant {variant.value!r}", seen[variant.value])
                    seen[variant.value] = variant
                    if child is not None:
                        if not is_scalar_payload(child):
                            fail("E0302", variant, "enum payloads must be an integer, bool, raw pointer or function pointer")
                        self.layout(child, variant)
                result = Layout(16 if self.is_pair(typ) else 8, 8)
            finally:
                self._active.remove(typ)
        elif is_array(typ):
            count = array_length(typ)
            if count <= 0:
                fail("E0302", token, "array length must be positive")
            child = self.layout(element(typ), token)
            if count > MAX_SIZE // child.size:
                fail("E0302", token, "array layout exceeds the x86-64 object size limit")
            result = Layout(count * child.size, child.alignment)
        elif typ in self.structs:
            if typ in self._active:
                fail("E0302", token, f"recursive by-value layout for {typ!r}")
            declaration = self.structs[typ]
            if not declaration.fields:
                fail("E0302", declaration.token, "empty structures are not allowed")
            explicit = declaration.alignment
            if declaration.packed and explicit is not None:
                fail("E0302", declaration.token, "packed and align cannot be combined")
            if explicit is not None and (explicit < 1 or explicit > 4096 or explicit & (explicit - 1)):
                fail("E0302", declaration.token, "alignment must be a power of two between 1 and 4096")
            self._active.add(typ)
            try:
                fields, seen = {}, {}
                offset, alignment = 0, 1
                for name, field_type in declaration.fields:
                    if name.value in seen:
                        fail("E0201", name, f"duplicate field {name.value!r}", seen[name.value])
                    seen[name.value] = name
                    child = self.layout(field_type, name)
                    field_alignment = 1 if declaration.packed else child.alignment
                    offset = self._round_up(offset, field_alignment, name)
                    fields[name.value] = FieldLayout(field_type, offset)
                    offset += child.size
                    if offset > MAX_SIZE:
                        fail("E0302", name, "structure layout exceeds the x86-64 object size limit")
                    alignment = max(alignment, field_alignment)
                if explicit is not None:
                    if explicit < alignment:
                        fail("E0302", declaration.token, "explicit alignment cannot lower natural alignment")
                    alignment = explicit
                result = Layout(self._round_up(offset, alignment, declaration.token), alignment, fields)
            finally:
                self._active.remove(typ)
        else:
            fail("E0301", token, f"unknown type {typ!r}")
        self._layouts[typ] = result
        return result

    def validate_function(self, typ: str, token: Token):
        signature = function_signature(typ)
        for child in signature.params + (() if signature.returns in {"void", "noreturn"} else (signature.returns,)):
            if self.is_aggregate(child) and (signature.abi == "win64" or not self.is_pair(child)):
                fail("E0601", token, "function signatures only support scalars and SysV pairs")
            self.layout(child, token)

    def validate_pair(self, typ: str, token: Token):
        child = payload(typ)
        if is_result(typ) and child == "void":
            return
        if not is_scalar_payload(child):
            fail("E0302", token, "optional/result payloads must be an integer, bool, raw pointer or function pointer")
        self.layout(child, token)

    @staticmethod
    def _round_up(size: int, alignment: int, token: Token) -> int:
        result = (size + alignment - 1) & -alignment
        if result > MAX_SIZE:
            fail("E0302", token, "layout exceeds the x86-64 object size limit")
        return result

    def manifest(self) -> dict:
        """Stable machine-readable target layouts, including declared structures."""
        entries = []
        for name in sorted(self.structs):
            declaration = self.structs[name]
            layout = self.layout(name)
            entries.append({
                "name": declaration.local_name or name.rsplit(".", 1)[-1],
                "full_name": name if "." in name else f"{declaration.module or self.module.name}.{name}",
                "kind": "struct",
                "size": layout.size, "alignment": layout.alignment,
                "fields": [{"name": field, "type": info.type, "offset": info.offset,
                            "size": self.layout(info.type).size}
                           for field, info in layout.fields.items()],
            })
        for name in sorted(self.enums):
            declaration = self.enums[name]
            layout = self.layout(name)
            entries.append({"name": declaration.local_name or name.rsplit(".", 1)[-1],
                            "full_name": name if "." in name else f"{declaration.module or self.module.name}.{name}",
                            "kind": "enum", "size": layout.size, "alignment": layout.alignment,
                            "representation": "pair" if self.is_pair(name) else "scalar",
                            "fields": [{"name": "tag", "type": "u64", "offset": 0, "size": 8}] +
                                      ([{"name": "value_slot", "type": "u64", "offset": 8, "size": 8}] if self.is_pair(name) else []),
                            "variants": [{"name": variant.value, "tag": index, "payload": child}
                                         for index, (variant, child) in enumerate(declaration.variants)]})
        return {"schema": 1, "target": "x86_64-dongos-elf", "spec_version": "0.1",
                "module": self.module.name, "types": entries}
