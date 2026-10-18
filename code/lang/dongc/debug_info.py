"""DWARF 4 for the direct x86-64 backend, independent of NASM's ASM debug mode.

The backend supplies its actual stack slots and final instruction stream.  Only
labels and non-allocated debug sections are added; no machine instruction is
changed.  Unknown/uninitialised locations are deliberately omitted.  DW_LANG_C99
selects GDB's compatible scalar/aggregate expression reader, not a C ABI: the
actual Dong layout and AMD64 register numbers are emitted below.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
import re
import struct

from .model import INTEGER, bits, is_signed, function_signature, is_function_type
from .typesys import is_pointer, pointee, is_array, array_length, element, is_slice, is_optional, is_result


def uleb(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative ULEB128")
    result = bytearray()
    while True:
        byte, value = value & 127, value >> 7
        result.append(byte | (128 if value else 0))
        if not value:
            return bytes(result)


def sleb(value: int) -> bytes:
    result = bytearray()
    while True:
        byte, value = value & 127, value >> 7
        done = (value == 0 and not byte & 64) or (value == -1 and byte & 64)
        result.append(byte | (0 if done else 128))
        if done:
            return bytes(result)


def data(value: bytes) -> str:
    return "    db " + ", ".join(str(byte) for byte in value) if value else ""


def string(value: str) -> str:
    return data(value.encode("utf-8") + b"\0")


def logical_path(path: str) -> str:
    """Root-relative module paths stay relative; standalone paths lose host root.

    For standalone input the debugger's directory/substitute-path command locates
    the source.  Explicit module roots already provide reproducible logical paths.
    Never embed a build machine's current working directory in the debug unit.
    """
    path = path.replace("\\", "/")
    if path.startswith("/") or re.match(r"^[A-Za-z]:/", path):
        return PurePosixPath(path).name
    return str(PurePosixPath(path))


def adapt_coff_debug(blob: bytes) -> bytes:
    """Convert NASM's debug-section references to COFF SECREL relocations.

    NASM win64 exposes image-relative and absolute relocations, but no SECREL
    operand for hand-authored DWARF.  Unlike ELF non-ALLOC debug sections, PE
    debug section VMAs are not zero.  A host builder must explicitly apply this
    adapter after NASM and before the MinGW linker.  Text/data/symbol bytes and
    every relocation outside a debug-to-debug ADDR32 reference are untouched.
    The DongOS ELF64 path does not use this adapter.
    """
    result = bytearray(blob)
    if len(blob) < 20:
        raise ValueError("truncated COFF header")
    machine,count,_,symbols,symbol_count,optional,_ = struct.unpack_from("<HHIIIHH",blob)
    if machine != 0x8664 or optional or count == 0:
        raise ValueError("expected an AMD64 COFF object")
    if 20+40*count > len(blob) or symbols+18*symbol_count+4 > len(blob):
        raise ValueError("truncated COFF sections or symbols")
    strings = symbols+18*symbol_count
    string_size = struct.unpack_from("<I",blob,strings)[0]
    if string_size < 4 or strings+string_size > len(blob):
        raise ValueError("truncated COFF strings")
    def name(raw):
        if raw.startswith(b"/"):
            try: index=int(raw[1:].rstrip(b"\0"))
            except ValueError as exc: raise ValueError("invalid COFF long section name") from exc
            if not 4 <= index < string_size:
                raise ValueError("COFF section name outside string table")
            end=blob.find(b"\0",strings+index,strings+string_size)
            if end < 0: raise ValueError("unterminated COFF name")
            return blob[strings+index:end].decode("ascii")
        return raw.rstrip(b"\0").decode("ascii")
    sections=[]
    for index in range(count):
        offset=20+40*index
        section_name=name(blob[offset:offset+8])
        reloc,count_reloc=struct.unpack_from("<I",blob,offset+24)[0],struct.unpack_from("<H",blob,offset+32)[0]
        if reloc+10*count_reloc > len(blob):
            raise ValueError("truncated COFF relocation table")
        sections.append((section_name,offset,reloc,count_reloc))
    for section_name,offset,reloc,count_reloc in sections:
        if not section_name.startswith(".debug_"): continue
        # Same read-only/discardable non-runtime flags emitted by MinGW GAS.
        struct.pack_into("<I",result,offset+36,0x42100040)
        for index in range(count_reloc):
            position=reloc+10*index
            symbol_index=struct.unpack_from("<I",blob,position+4)[0]
            kind=struct.unpack_from("<H",blob,position+8)[0]
            if symbol_index >= symbol_count:
                raise ValueError("COFF relocation references invalid symbol")
            target=struct.unpack_from("<h",blob,symbols+18*symbol_index+12)[0]
            if kind == 2 and 1 <= target <= count and sections[target-1][0].startswith(".debug_"):
                struct.pack_into("<H",result,position+8,0x000b)
    return bytes(result)


@dataclass
class Scope:
    start: str
    end: str = ""
    children: list = field(default_factory=list)
    variables: list = field(default_factory=list)
    tail: object = None
    declarations: list = field(default_factory=list)


@dataclass
class Frame:
    start: str
    end: str
    cfi: list


class DebugInfo:
    """Emitter hook protocol: scope_begin/end, binding, instrument, sections."""
    def __init__(self, module, path: str):
        self.module, self.path, self.types = module, logical_path(path), module.type_system
        self.serial = 0
        self.scopes = []
        self.functions = []
        self.frames = []
        self.files = {}
        self.type_ids = {}
        self._file(path)

    def _label(self, purpose="pc"):
        self.serial += 1
        return f"..@dg_debug_{purpose}_{self.serial}"

    def _file(self, path):
        path = logical_path(path or self.path)
        if path not in self.files:
            self.files[path] = len(self.files) + 1
        return self.files[path]

    def scope_begin(self):
        label = self._label("scope")
        self.scopes.append(label)
        return "; dg.scope.begin " + label

    def scope_end(self):
        if not self.scopes:
            raise ValueError("debug lexical scope underflow")
        return "; dg.scope.end " + self.scopes.pop()

    def binding(self, slot):
        return "; dg.local.live " + str(slot)

    def declaration(self, slot):
        return "; dg.local.declare " + str(slot)

    @staticmethod
    def _initialised_slots(function):
        # Initialisation in a conditional does not make a previously uninitialised
        # outer binding unconditionally live at the merge.  Such bindings remain
        # unavailable; showing stale stack bytes would be false debug information.
        slots = set()
        def visit(statements):
            for statement in statements:
                if statement.kind == "binding" and statement.expr is not None:
                    slots.add(statement.value.slot)
                if statement.kind == "for":
                    slots.add(statement.variable.slot)
                visit(statement.body or [])
                visit(statement.otherwise or [])
                if statement.kind == "match":
                    for arm in statement.value:
                        if getattr(arm,"binding",None) is not None:
                            slots.add(arm.binding.slot)
                        visit(arm.body)
        visit(function.body)
        return slots

    @staticmethod
    def _implicit_slots(function):
        slots=set()
        def visit(statements):
            for statement in statements:
                if statement.kind == "for": slots.add(statement.variable.slot)
                visit(statement.body or [])
                visit(statement.otherwise or [])
                if statement.kind == "match":
                    for arm in statement.value:
                        if getattr(arm,"binding",None) is not None: slots.add(arm.binding.slot)
                        visit(arm.body)
        visit(function.body)
        return slots

    def instrument_function(self, function, lines, variable_offsets, frame_base="rbp"):
        """Add labels to final code, preserving every original instruction.

        Scope/live comments originate in the emitter, so lexical ranges describe
        code addresses, including duplicated cleanup bodies, rather than guessing
        block ends from source line numbers.  Declaration markers put unavailable
        bindings in their real lexical scope, preserving uninitialised shadowing.
        """
        if frame_base not in {"rbp", "r12"}:
            raise ValueError("unknown debug frame base")
        output, rows, frames, stack = [], [], [], []
        by_slot = {variable.slot: variable for variable in function.variables}
        allowed = self._initialised_slots(function)
        implicit = self._implicit_slots(function)
        pending = []
        active_declarations = {}
        live_slots = set()
        root = Scope(self._label("scope_root"))
        stack.append(root)
        body_symbol = "__dg_bridge_" + function.symbol.encode("utf-8").hex() if function.abi == "win64" else function.symbol
        body_start = body_end = None
        current_frame = None
        wrapper = False
        prologue = False
        params_start = None
        file_id = self._file(function.source_path or self.path)
        for line_index,line in enumerate(lines):
            stripped = line.strip()
            if stripped in {"$" + function.symbol + ":", "$" + body_symbol + ":"}:
                if current_frame:
                    end = self._label("frame_end")
                    output.append(end + ":")
                    current_frame.end = end
                    frames.append(current_frame)
                output.append(line)
                start = self._label("function")
                output.append(start + ":")
                current_frame = Frame(start, "", [])
                wrapper = function.abi == "win64" and stripped != "$" + body_symbol + ":"
                prologue = True
                if stripped == "$" + body_symbol + ":":
                    body_start = start
                    rows.append((start, file_id, function.token.line, function.token.column))
                continue
            if stripped.startswith("; dg.scope.begin "):
                name = stripped.split()[-1]
                scope = Scope(name)
                parent = stack[-1].tail or stack[-1]
                parent.children.append(scope)
                stack.append(scope)
                output.append(name + ":")
                for variable_,offset in pending:
                    scope.variables.append((variable_,name,offset))
                pending.clear()
                if params_start is None:
                    params_start = name
                continue
            if stripped.startswith("; dg.scope.end "):
                if len(stack) <= 1 or stack[-1].start != stripped.split()[-1]:
                    raise ValueError("unbalanced debug lexical scope")
                scope = stack.pop()
                scope.end = self._label("scope_end")
                for declaration_scope in scope.declarations:
                    declaration_scope.end = scope.end
                    for entry in declaration_scope.variables:
                        active_declarations[entry[0].slot].pop()
                output.append(scope.end + ":")
                continue
            if stripped.startswith("; dg.local.live "):
                slot = int(stripped.split()[-1])
                declaration = active_declarations.get(slot,[])
                declaration = declaration[-1] if declaration else None
                if slot in allowed and ((declaration is None and slot not in live_slots) or (declaration is not None and declaration[1] is None)):
                    label = self._label("live")
                    output.append(label + ":")
                    if declaration is not None:
                        declaration[1] = label
                    elif slot in implicit:
                        # for/match store the implicit binding just before their
                        # body scope opens; it is not visible after that body.
                        pending.append((by_slot[slot],variable_offsets[slot]))
                    else:
                        stack[-1].variables.append([by_slot[slot], label, variable_offsets[slot]])
                    live_slots.add(slot)
                continue
            if stripped.startswith("; dg.local.declare "):
                slot=int(stripped.split()[-1])
                # C99/Dong names start at their declaration, not block entry.
                # Nest successive declaration tails so earlier names remain
                # visible, rather than overlapping sibling lexical ranges.
                name=self._label("declaration")
                output.append(name+":")
                scope=Scope(name)
                parent=stack[-1].tail or stack[-1]
                parent.children.append(scope)
                stack[-1].tail=scope
                stack[-1].declarations.append(scope)
                entry=[by_slot[slot],None,variable_offsets[slot]]
                scope.variables.append(entry)
                active_declarations.setdefault(slot,[]).append(entry)
                continue
            match = re.fullmatch(r"; line (\d+)", stripped)
            if match:
                label = self._label("line")
                output.extend([line, label + ":"])
                rows.append((label, file_id, int(match[1]), 1))
                prologue = False
                continue
            output.append(line)
            if re.match(r"\.L_panic_\d+:$",stripped):
                panic_line = next((re.fullmatch(r"mov esi, (\d+)",item.strip())
                    for item in lines[line_index+1:line_index+4] if re.fullmatch(r"mov esi, (\d+)",item.strip())),None)
                if panic_line:
                    label=self._label("panic_line")
                    output.append(label+":")
                    rows.append((label,file_id,int(panic_line[1]),1))
            if current_frame:
                cfi = None
                if stripped == "push rbp" and prologue:
                    cfi = bytes([0x0e, 16, 0x86, 2])  # CFA rsp+16; saved rbp CFA-16
                elif stripped == "mov rbp, rsp" and prologue:
                    cfi = bytes([0x0d, 6])
                elif stripped == "push r12" and prologue:
                    cfi = bytes([0x8c, 3])
                elif stripped == "mov r12, qword [rbp-8]":
                    cfi = bytes([0xcc])
                elif stripped == "pop rbp":
                    cfi = bytes([0x0c, 7, 8, 0xc6])
                elif re.match(r"\.L_panic_\d+:$", stripped):
                    cfi = bytes([0x0c, 6, 16, 0x86, 2]) + (bytes([0x8c, 3]) if frame_base == "r12" else b"")
                else:
                    saved = re.fullmatch(r"mov qword \[rbp-(8|16)\], (rdi|rsi)", stripped)
                    if saved and prologue and wrapper:
                        cfi = bytes([0x80 + {"rdi": 5, "rsi": 4}[saved[2]], (int(saved[1]) + 16) // 8])
                    restored = re.fullmatch(r"mov (rdi|rsi), qword \[rbp-(8|16)\]", stripped)
                    if restored and wrapper:
                        cfi = bytes([0xc0 + {"rdi": 5, "rsi": 4}[restored[1]]])
                    saved_xmm=re.fullmatch(r"movdqu \[rbp-(\d+)\], xmm(\d+)",stripped)
                    if saved_xmm and wrapper:
                        cfi=bytes([0x80+17+int(saved_xmm[2])])+uleb((int(saved_xmm[1])+16)//8)
                    restored_xmm=re.fullmatch(r"movdqu xmm(\d+), \[rbp-\d+\]",stripped)
                    if restored_xmm and wrapper:
                        cfi=bytes([0xc0+17+int(restored_xmm[1])])
                if cfi:
                    label = self._label("cfi")
                    output.append(label + ":")
                    current_frame.cfi.append((label, cfi))
        if len(stack) != 1 or pending or not body_start or not current_frame:
            raise ValueError("incomplete debug function")
        body_end = self._label("function_end")
        output.append(body_end + ":")
        current_frame.end = body_end
        frames.append(current_frame)
        root.end = body_end
        root.start = body_start
        self.frames.extend(frames)
        self.functions.append(dict(function=function, start=body_start, end=body_end, rows=rows,
            scope=root, base=12 if frame_base == "r12" else 6, offsets=dict(variable_offsets),
            params_start=params_start or body_start, file=file_id))
        return output

    @staticmethod
    def _section(name):
        # ELF non-ALLOC sections and COFF IMAGE_SCN_LNK_REMOVE/DEBUG sections.
        return ["%ifidn __OUTPUT_FORMAT__,elf64", f"section {name} noalloc noexec nowrite progbits align=1",
                "%else", f"section {name} info align=1", "%endif"]

    @staticmethod
    def _offset(label):
        # ELF links these at VMA zero.  COFF builders must run adapt_coff_debug
        # so NASM's ADDR32 relocations become section-relative SECREL instead.
        return [f"    dd {label}"]

    def _type(self, typ):
        if typ not in self.type_ids:
            self.type_ids[typ] = self._label("type")
        return self.type_ids[typ]

    def _ref(self, typ):
        return f"    dd {self._type(typ)} - ..@dg_debug_cu"

    def _types(self):
        output, done = [], set()
        while len(done) != len(self.type_ids):
            typ = next(typ for typ in self.type_ids if typ not in done)
            done.add(typ)
            output.append(self.type_ids[typ] + ":")
            if typ in {"void", "noreturn"}:
                output += [data(uleb(5)), string(typ)]
            elif typ in INTEGER or typ == "bool":
                output += [data(uleb(4)), string(typ), data(bytes([1 if typ == "bool" else bits(typ)//8,
                    2 if typ == "bool" else 5 if is_signed(typ) else 7]))]
            elif is_pointer(typ):
                output += [data(uleb(6)), self._ref(pointee(typ)), "    db 8"]
            elif is_function_type(typ):
                # Typed function pointers are pointer-to-subroutine DIEs, not integers.
                signature = function_signature(typ)
                child = self._label("subroutine")
                output += [data(uleb(6)), f"    dd {child} - ..@dg_debug_cu", "    db 8", child + ":",
                    data(uleb(12)), self._ref(signature.returns)]
                for param in signature.params:
                    output += [data(uleb(13)), self._ref(param)]
                output.append("    db 0")
            elif is_array(typ):
                output += [data(uleb(9)), self._ref(element(typ)), f"    dq {self.types.layout(typ).size}",
                    data(uleb(10)), f"    dq {array_length(typ)}", "    db 0"]
            else:
                layout = self.types.layout(typ)
                fields = [(name, field.type, field.offset) for name, field in layout.fields.items()]
                if is_slice(typ):
                    fields = [("data", "*" + element(typ), 0), ("len", "u64", 8)]
                elif is_optional(typ) or is_result(typ):
                    fields = [("tag", "u64", 0)]
                    if typ[1:] != "void":
                        fields.append(("payload", typ[1:], 8))
                elif typ in self.types.enums:
                    if not self.types.is_pair(typ):
                        output += [data(uleb(14)), string(typ), "    db 8"]
                        for index, (variant, _) in enumerate(self.types.enums[typ].variants):
                            output += [data(uleb(15)), string(variant.value), data(uleb(index))]
                        output.append("    db 0")
                        continue
                    # Payload variants can have different scalar types.  Expose
                    # the physical pair honestly, rather than assert one variant.
                    fields = [("tag", "u64", 0), ("payload_bits", "u64", 8)]
                output += [data(uleb(7)), string(typ), f"    dq {layout.size}"]
                for name, child, offset in fields:
                    output += [data(uleb(8)), string(name), self._ref(child), data(uleb(offset))]
                output.append("    db 0")
        return output

    @staticmethod
    def _abbreviations():
        # code, tag, children, [(attribute, form)]; all DWARF4 standard values.
        entries = [
            (1,0x11,1,[(0x25,8),(0x13,5),(3,8),(0x1b,8),(0x10,0x17),(0x11,1),(0x12,1)]),
            (2,0x2e,1,[(3,8),(0x3a,0x0f),(0x3b,0x0f),(0x49,0x13),(0x11,1),(0x12,1),(0x40,0x18)]),
            (3,0x0b,1,[(0x11,1),(0x12,1)]),
            (4,0x24,0,[(3,8),(0x0b,0x0b),(0x3e,0x0b)]), (5,0x3b,0,[(3,8)]),
            (6,0x0f,0,[(0x49,0x13),(0x0b,0x0b)]),
            (7,0x13,1,[(3,8),(0x0b,7)]), (8,0x0d,0,[(3,8),(0x49,0x13),(0x38,0x0f)]),
            (9,1,1,[(0x49,0x13),(0x0b,7)]), (10,0x21,0,[(0x37,7)]),
            (11,0x34,0,[(3,8),(0x49,0x13),(0x3a,0x0f),(0x3b,0x0f),(2,0x17)]),
            (12,0x15,1,[(0x49,0x13)]), (13,5,0,[(0x49,0x13)]),
            (14,4,1,[(3,8),(0x0b,0x0b)]), (15,0x28,0,[(3,8),(0x1c,0x0f)]),
            (16,5,0,[(3,8),(0x49,0x13),(0x3a,0x0f),(0x3b,0x0f),(2,0x17)]),
            (17,0x34,0,[(3,8),(0x49,0x13),(0x3a,0x0f),(0x3b,0x0f)]),
            (18,0x34,0,[(3,8),(0x49,0x13),(0x3a,0x0f),(0x3b,0x0f),(2,0x18)]),
        ]
        result = []
        for code, tag, children, attributes in entries:
            result += [data(uleb(code)+uleb(tag)+bytes([children]))]
            result.extend(data(uleb(attr)+uleb(form)) for attr,form in attributes)
            result.append("    db 0,0")
        return result + ["    db 0"]

    def sections(self):
        if self.scopes:
            raise ValueError("unfinished debug scope")
        info = self._section(".debug_info") + ["..@dg_debug_cu:", "    dd ..@dg_debug_cu_end - ..@dg_debug_cu - 4", "    dw 4"]
        info += self._offset("..@dg_debug_abbrev") + ["    db 8", "    db 1", string("Dong direct backend DWARF4"),
            "    dw 0x000c", string(self.path), string(".")]
        info += self._offset("..@dg_debug_line")
        info += [f"    dq {self.frames[0].start}, {self.frames[-1].end}" if self.frames else "    dq 0,0"]
        locations = self._section(".debug_loc")
        def variable(variable, begin, end, offset, base, parameter=False):
            name = variable.token.value
            loc = self._label("location")
            file_id = self._file(variable.token.path or self.path)
            die = [data(uleb(16 if parameter else 11)), string(name), self._ref(variable.typ), data(uleb(file_id)), data(uleb(variable.token.line))]
            die += self._offset(loc)
            expression = bytes([0x70+base]) + sleb(-offset)
            locations.extend([loc+":", "    dq 0xffffffffffffffff,0", f"    dq {begin}, {end}",
                f"    dw {len(expression)}", data(expression), "    dq 0,0"])
            return die
        def scope_die(scope, record):
            result = ["    db 3", f"    dq {scope.start}, {scope.end}"]
            for var,begin,offset in scope.variables:
                if begin is None:
                    result += ["    db 17",string(var.token.value),self._ref(var.typ),
                        data(uleb(self._file(var.token.path or self.path))),data(uleb(var.token.line))]
                else:
                    result += variable(var,begin,scope.end,offset,record["base"])
            for child in scope.children:
                result += scope_die(child,record)
            return result+["    db 0"]
        for record in self.functions:
            function = record["function"]
            info += ["    db 2", string(function.local_name or function.token.value),
                data(uleb(record["file"])), data(uleb(function.token.line)), self._ref(function.returns),
                f"    dq {record['start']}, {record['end']}", "    db 1, 0x56"]  # frame base rbp register value
            for variable_ in function.variables[:len(function.params)]:
                parameter_end=record["scope"].children[0].end if record["scope"].children else record["scope"].end
                info += variable(variable_,record["params_start"],parameter_end,record["offsets"][variable_.slot],record["base"],True)
            info += scope_die(record["scope"],record)
            info.append("    db 0")
        emitted={obj.symbol for obj in self.module.static_objects}
        for declaration in self.module.globals:
            if declaration.symbol not in emitted: continue
            info += ["    db 18",string(declaration.local_name or declaration.token.value),self._ref(declaration.typ),
                data(uleb(self._file(declaration.token.path or self.path))),data(uleb(declaration.token.line)),
                "    db 9,3",f"    dq ${declaration.symbol}"]  # exprloc: DW_OP_addr
        info += self._types() + ["    db 0", "..@dg_debug_cu_end:"]
        abbrev = self._section(".debug_abbrev") + ["..@dg_debug_abbrev:"] + self._abbreviations()
        line = self._section(".debug_line") + ["..@dg_debug_line:","    dd ..@dg_debug_line_end - ..@dg_debug_line - 4", "    dw 4",
            "    dd ..@dg_debug_line_program - ..@dg_debug_line_header", "..@dg_debug_line_header:",
            "    db 1,1,1,251,14,13", "    db 0,1,1,1,1,0,0,0,1,0,0,1", "    db 0"]
        for path in self.files:
            line += [string(path), "    db 0,0,0"]
        line += ["    db 0", "..@dg_debug_line_program:"]
        for record in self.functions:
            previous_line = 1
            for address,file_id,line_no,column in record["rows"]:
                line += ["    db 0,9,2", f"    dq {address}",data(bytes([4])+uleb(file_id)),
                    data(bytes([3])+sleb(line_no-previous_line)),data(bytes([5])+uleb(column)),"    db 1"]
                previous_line = line_no
            line += ["    db 0,9,2", f"    dq {record['end']}", "    db 0,1,1"]
        line.append("..@dg_debug_line_end:")
        frames = self._section(".debug_frame") + ["..@dg_debug_cie:",
            "    dd ..@dg_debug_cie_end - ..@dg_debug_cie - 4", "    dd 0xffffffff", "    db 1,0,1,0x78,16,0x0c,7,8,0x90,1",
            "..@dg_debug_cie_end:"]
        for frame in self.frames:
            start,end = self._label("fde"),self._label("fde_end")
            frames += [start+":", f"    dd {end} - {start} - 4"] + self._offset("..@dg_debug_cie")
            frames += [f"    dq {frame.start}, {frame.end} - {frame.start}"]
            for address,instructions in frame.cfi:
                frames += ["    db 1",f"    dq {address}",data(instructions)]  # DW_CFA_set_loc
            frames.append(end+":")
        return info + abbrev + locations + line + frames
