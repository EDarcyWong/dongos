"""NASM ELF64 code generation for the Dong v0.1 language.

Scalar expression results are canonical 64-bit values in RAX. Aggregate results
are addresses of temporary storage. Locals use RBP, or an aligned R12 base;
no generated instruction uses the red zone or an implicit C runtime. Ordinary
Dong bodies use no SIMD; Win64 ABI bridges save the required XMM registers.
"""
from __future__ import annotations

from dataclasses import dataclass
from .model import *


@dataclass
class Compilation:
    assembly: str
    module: str
    mode: str
    runtime_symbols: list[str]
    exports: list[str]
    layout_manifest: dict | None = None
    modules: list[str] | None = None
    sources: list[str] | None = None
    optimization: dict | None = None
    debug_information: dict | None = None
    function_sections: bool = False

    def manifest(self):
        result = {"schema": 1, "spec_version": "0.1", "compiler_subset": "l1-language",
                "target": "x86_64-dongos-elf", "mode": self.mode, "module": self.module,
                "exports": self.exports, "runtime_symbols": self.runtime_symbols}
        if self.modules is not None:
            result["modules"] = self.modules
        if self.sources is not None:
            result["sources"] = self.sources
        if self.optimization is not None:
            result["optimization"] = self.optimization
        if self.debug_information is not None:
            result["debug_information"] = self.debug_information
        if self.function_sections:
            result["function_sections"] = True
        return result


class Emitter:
    REGISTERS = ["rdi", "rsi", "rdx", "rcx", "r8", "r9"]
    LOW_REGISTERS = {
        1: ["dil", "sil", "dl", "cl", "r8b", "r9b"],
        2: ["di", "si", "dx", "cx", "r8w", "r9w"],
        4: ["edi", "esi", "edx", "ecx", "r8d", "r9d"],
        8: REGISTERS,
    }
    WIDTH = {1: "byte", 2: "word", 4: "dword", 8: "qword"}
    ACC = {1: "al", 2: "ax", 4: "eax", 8: "rax"}

    def __init__(self, module: Module, path: str, mode: str, *, optimize=0, debug_info=False, function_sections=False):
        self.module, self.path, self.mode = module, path, mode
        self.types = module.type_system
        self.runtime = set()
        self.file_labels = {}
        self.strings = []
        self.external_symbols = set()
        self.serial = 0
        self.optimize = optimize
        self.function_sections = function_sections
        self.optimization = []
        self.debug = None
        if debug_info:
            from .debug_info import DebugInfo
            self.debug = DebugInfo(module, path)

    def emit(self, *lines):
        self.lines.extend(lines)

    def is_pair(self, typ):
        return getattr(self.types, "is_pair", self.types.is_slice)(typ)

    def label(self, name):
        self.serial += 1
        return f".L_{name}_{self.serial}"

    @staticmethod
    def slot(offset: int):
        # The function's greatest alignment may first appear in a late
        # temporary. Resolve this memory-only placeholder after its whole body.
        return f"[__DG_FRAME_BASE__-{offset}]"

    def allocate(self, size=8, alignment=8):
        # The eventual frame base meets the greatest requested alignment.
        self.max_alignment = max(self.max_alignment, alignment)
        self.next_temp = (self.next_temp + size + alignment - 1) & -alignment
        self.max_size = max(self.max_size, self.next_temp)
        return self.next_temp

    def storage(self, typ, token):
        layout = self.types.layout(typ)
        if layout.size > 4080:
            minimum_frame = 16 + ((layout.size + 15) & ~15) + (layout.alignment if layout.alignment > 16 else 0)
            fail("E0601", token, f"worst-case frame at least {minimum_frame} bytes exceeds 4096 bytes")
        return self.allocate(layout.size, layout.alignment)

    def check(self, condition: str, kind: int, token: Token):
        label = self.label("panic")
        self.panic_sites.append((label, kind, token.line))
        self.runtime.add("__dong_panic")
        self.emit(f"    {condition} {label}")

    def compile(self) -> Compilation:
        pieces = []
        for function in self.module.functions:
            if not getattr(function, "external", False):
                if self.function_sections:
                    section = ".text.dg_" + function.symbol.encode("utf-8").hex()
                    pieces.extend(["%ifidn __OUTPUT_FORMAT__,elf64",
                                   "section " + section + " progbits alloc exec nowrite align=16",
                                   "%else", "section " + section + " code align=16", "%endif"])
                if self.optimize and self.mode == "release" and self.debug is None:
                    from .ssa_lower import compile_function, Unsupported
                    try:
                        lines, record = compile_function(function)
                    except Unsupported as error:
                        lines = self.function(function)
                        record = {"symbol": function.symbol, "backend": "l1", "reason": str(error)}
                    pieces.extend(lines)
                    self.optimization.append(record)
                else:
                    pieces.extend(self.function(function))
                    if self.optimize:
                        self.optimization.append({"symbol": function.symbol, "backend": "l1",
                                                  "reason": "debug checks or source debugging requested"})
        external = {function.symbol for function in self.module.functions if function.external}
        self.external_symbols.update(relocation.symbol for obj in self.module.static_objects
                                     for relocation in obj.relocations if relocation.symbol in external)
        # Collect every payload before rendering byte operands. Runtime string
        # literals and diagnostic file names share the declared-object budget.
        static_size = sum(len(obj.data) for obj in self.module.static_objects)
        static_size += sum(len(data) for _, data in self.strings)
        static_size += sum(len(path.encode("utf-8")) for _, path in self.file_labels.values())
        if static_size > 16 * 1024 * 1024:
            fail("E0601", self.module.token, "static storage exceeds the 16 MiB bootstrap materialization budget")
        header = ["; Dong v0.1 L1 language; generated, do not edit.",
                  f"; mode: {self.mode}; target: x86_64-dongos-elf",
                  "; required-runtime: " + (", ".join(sorted(self.runtime)) or "none"),
                  "bits 64", "default rel", "section .text"]
        header += ["extern $" + symbol for symbol in sorted(self.runtime | self.external_symbols)]
        header += ["global $" + function.symbol for function in self.module.functions
                   if function.export and not getattr(function, "external", False)]
        if self.file_labels or self.strings:
            pieces.append("section .rodata")
            for label, path in self.file_labels.values():
                data = path.encode("utf-8")
                pieces += [label + ":", "    db " + (", ".join(str(byte) for byte in data) or "0")]
            for label, data in self.strings:
                pieces += [label + ":", "    db " + (", ".join(str(byte) for byte in data) or "0")]
        pieces.extend(self.static_sections())
        if self.debug is not None:
            pieces.extend(self.debug.sections())
        pieces += ["%ifidn __OUTPUT_FORMAT__,elf64", "section .note.GNU-stack noalloc noexec nowrite progbits", "%endif", ""]
        manifest = self.types.manifest()
        module_names = getattr(self.module, "modules", None)
        source_map = getattr(self.module, "sources", None)
        modules = sorted(module_names) if module_names is not None else sorted(
            {self.module.name} | {(getattr(function, "module", "") or self.module.name)
                                  for function in self.module.functions})
        sources = sorted(source_map) if source_map is not None else sorted(
            {self.path} | {(getattr(function, "source_path", "") or self.path)
                           for function in self.module.functions})
        return Compilation("\n".join(header + pieces), self.module.name, self.mode, sorted(self.runtime),
                           [function.export for function in self.module.functions if function.export and not getattr(function, "external", False)], manifest, modules, sources,
                           {"level": self.optimize, "functions": self.optimization} if self.optimize else None,
                           {"format": "DWARF", "backend": "l1"} if self.debug is not None else None,
                           self.function_sections)

    @staticmethod
    def static_bytes(data):
        if not data:
            return []
        # Uniform initializers and padding should not produce millions of
        # textual byte operands at the bootstrap static-storage limit.
        if data.count(data[:1]) == len(data):
            return [f"    times {len(data)} db {data[0]}"]
        return ["    db " + ", ".join(str(byte) for byte in data[offset:offset + 32])
                for offset in range(0, len(data), 32)]

    def static_sections(self):
        objects = getattr(self.module, "static_objects", [])
        if sum(len(obj.data) for obj in objects) > 16 * 1024 * 1024:
            fail("E0601", self.module.token, "static storage exceeds the 16 MiB bootstrap limit")
        sections = {".rodata": [], ".data": [], ".bss": []}
        bss_alignment = 4  # NASM's default .bss alignment, raised by each object.
        for obj in objects:
            name = ".rodata" if not obj.mutable else ".bss" if not obj.relocations and not any(obj.data) else ".data"
            lines = sections[name]
            if name == ".bss":
                bss_alignment = max(bss_alignment, obj.alignment)
            # Some vendor NASM 2.x alignb macros expand warning-stack directives
            # the assembler itself does not support. Reserve section-relative
            # padding directly; the section header below also aligns its base.
            lines += [f"    resb ({obj.alignment} - ($-$$) % {obj.alignment}) % {obj.alignment}" if name == ".bss" else f"align {obj.alignment}, db 0",
                      "$" + obj.symbol + ":"]
            if name == ".bss":
                lines.append(f"    resb {len(obj.data)}")
                continue
            cursor = 0
            for relocation in sorted(obj.relocations, key=lambda item: item.offset):
                if relocation.offset < cursor or relocation.offset + 8 > len(obj.data):
                    fail("E0601", self.module.token, "invalid or overlapping 64-bit static relocation")
                lines.extend(self.static_bytes(obj.data[cursor:relocation.offset]))
                addend = f" + {relocation.addend}" if relocation.addend > 0 else f" - {-relocation.addend}" if relocation.addend < 0 else ""
                lines.append(f"    dq ${relocation.symbol}{addend}")
                cursor = relocation.offset + 8
            lines.extend(self.static_bytes(obj.data[cursor:]))
            if not obj.data:
                lines.append("    db 0")
        # Static pointers deliberately need ELF absolute 64-bit relocations.
        # NASM 3 diagnoses those as optional portability warnings by default.
        result = ["%if __NASM_MAJOR__ >= 3", "[warning push]", "[warning -reloc-abs-qword]", "%endif"] if objects else []
        for name, lines in sections.items():
            if lines:
                suffix = f" align={bss_alignment}" if name == ".bss" else ""
                result += ["section " + name + suffix] + lines
        if objects:
            result += ["%if __NASM_MAJOR__ >= 3", "[warning pop]", "%endif"]
        return result

    def parameter_locations(self, types, abi="sysv"):
        """Assign whole INTEGER-class values before applying stack alignment.

        A pair consumes two registers together, or goes wholly on the stack.
        A failed pair allocation leaves a spare register available to scalars.
        """
        registers = ["rcx", "rdx", "r8", "r9"] if abi == "win64" else self.REGISTERS
        register_index, stack_offset = 0, 32 if abi == "win64" else 0
        locations = []
        for typ in types:
            words = 2 if self.is_pair(typ) else 1
            if register_index + words <= len(registers):
                locations.append((registers[register_index:register_index + words], None))
                register_index += words
            else:
                locations.append((None, stack_offset))
                stack_offset += 8 * words
        return locations, (stack_offset + 15) & ~15

    def function(self, function: Function):
        self.lines = []
        self.function_returns = function.returns
        owner = (getattr(function, "module", "") or self.module.name)
        self.file_label = "__dg_file_" + owner.encode("utf-8").hex()
        self.function_path = (getattr(function, "source_path", "") or self.path)
        self.next_temp = self.max_size = self.max_outgoing = 0
        self.max_alignment = 16
        self.variables = {}
        self.panic_sites = []
        self.loop_labels = []
        self.return_label = self.label("return")
        for variable in function.variables:
            self.variables[variable.slot] = self.storage(variable.typ, variable.token)
        locations, _ = self.parameter_locations([typ for _, typ in function.params])
        for index, (registers, stack_offset) in enumerate(locations):
            variable = function.variables[index]
            destination = self.variables[variable.slot]
            size = self.types.layout(variable.typ).size
            if registers:
                if self.is_pair(variable.typ):
                    for word, register in enumerate(registers):
                        self.emit(f"    mov qword {self.slot(destination - 8 * word)}, {register}")
                else:
                    register_index = self.REGISTERS.index(registers[0])
                    self.emit(f"    mov {self.WIDTH[size]} {self.slot(destination)}, {self.LOW_REGISTERS[size][register_index]}")
            else:
                if self.is_pair(variable.typ):
                    for word in range(2):
                        self.emit(f"    mov rax, qword [rbp+{16 + stack_offset + 8 * word}]",
                                  f"    mov qword {self.slot(destination - 8 * word)}, rax")
                else:
                    self.emit(f"    mov rax, qword [rbp+{16 + stack_offset}]",
                              f"    mov {self.WIDTH[size]} {self.slot(destination)}, {self.ACC[size]}")
        self.block(function.body)
        if function.returns == "void":
            self.emit("    xor eax, eax")
        realigned = self.max_alignment > 16
        self.emit(self.return_label + ":", "    cld")
        if function.returns == "noreturn":
            self.emit("    ud2")
        else:
            if realigned:
                self.emit("    mov r12, qword [rbp-8]")
            self.emit("    mov rsp, rbp", "    pop rbp", "    ret")
        if self.panic_sites:
            self.file_labels[owner] = (self.file_label, self.function_path)
        for label, kind, line in self.panic_sites:
            self.emit(label + ":", f"    mov edi, {kind}", f"    mov esi, {line}",
                      f"    lea rdx, [rel {self.file_label}]", f"    mov ecx, {len(self.function_path.encode('utf-8'))}",
                      "    call __dong_panic", "    ud2")
        size = (self.max_size + 15) & ~15
        # With realignment, RBP anchors incoming stack arguments and R12 is
        # saved at [rbp-8]. After both pushes RSP is 8 modulo 16, so rounding
        # down to A >= 32 can cost at most A-8 bytes. Counting the return slot,
        # both saved registers, payload and outgoing arguments gives 16+A+S+O.
        worst_case = size + 16 + self.max_outgoing + (self.max_alignment if realigned else 0)
        win64 = function.abi == "win64"
        wrapper_size = 0
        if win64:
            # The Win64 entry and its private SysV body coexist on the stack.
            # Count both return slots/prologues, bridge saves and marshalled
            # stack parameters, then the body's complete worst-case frame.
            _, wrapper_outgoing = self.parameter_locations([typ for _, typ in function.params])
            wrapper_size = (176 + wrapper_outgoing + 15) & ~15
            worst_case += 16 + wrapper_size
        if worst_case > 4096:
            fail("E0601", function.token, f"worst-case frame {worst_case} bytes exceeds 4096 bytes")
        body_symbol = "__dg_bridge_" + function.symbol.encode("utf-8").hex() if win64 else function.symbol
        prefix = ["", "align 16", "$" + body_symbol + ":", "    push rbp", "    mov rbp, rsp", "    cld"]
        if realigned:
            prefix += ["    push r12", f"    and rsp, -{self.max_alignment}", "    mov r12, rsp"]
        if size:
            prefix.append(f"    sub rsp, {size}")
        frame_base = "r12" if realigned else "rbp"
        bridge = self.win64_wrapper(function, body_symbol, wrapper_size) if win64 else []
        lines = bridge + prefix + [line.replace("[__DG_FRAME_BASE__-", f"[{frame_base}-") for line in self.lines]
        if self.debug is not None:
            lines = self.debug.instrument_function(function, lines, variable_offsets=self.variables,
                                                   frame_base=frame_base)
        return lines

    def win64_wrapper(self, function, body_symbol, size):
        """Preserve Microsoft's larger nonvolatile set around a SysV body."""
        lines = ["", "align 16", "$" + function.symbol + ":", "    push rbp", "    mov rbp, rsp",
                 f"    sub rsp, {size}", "    cld", "    mov qword [rbp-8], rdi", "    mov qword [rbp-16], rsi"]
        for index in range(10):
            lines.append(f"    movdqu [rbp-{32 + 16 * index}], xmm{6 + index}")
        # Copy stack parameters first using RAX. Save the four register values
        # through this dependency-safe ordering before reusing RCX/RDX/R8/R9.
        for index in range(6, len(function.params)):
            lines += [f"    mov rax, qword [rbp+{48 + 8 * (index - 4)}]",
                      f"    mov qword [rsp+{8 * (index - 6)}], rax"]
        for index, source in enumerate(("rcx", "rdx", "r8", "r9")):
            if index < len(function.params):
                lines.append(f"    mov {self.REGISTERS[index]}, {source}")
        for index in range(4, min(6, len(function.params))):
            lines.append(f"    mov {self.REGISTERS[index]}, qword [rbp+{48 + 8 * (index - 4)}]")
        lines.append(f"    call ${body_symbol}")
        if function.returns == "noreturn":
            return lines + ["    ud2"]
        for index in range(10):
            lines.append(f"    movdqu xmm{6 + index}, [rbp-{32 + 16 * index}]")
        lines += ["    mov rdi, qword [rbp-8]", "    mov rsi, qword [rbp-16]", "    cld",
                  "    mov rsp, rbp", "    pop rbp", "    ret"]
        return lines

    def block(self, statements: list[Stmt]):
        if self.debug is not None:
            self.emit(self.debug.scope_begin())
        for statement in statements:
            saved = self.next_temp
            self.statement(statement)
            self.next_temp = saved
        if self.debug is not None:
            self.emit(self.debug.scope_end())

    def statement(self, statement: Stmt):
        self.emit(f"    ; line {statement.token.line}")
        if statement.kind == "binding":
            if self.debug is not None:
                self.emit(self.debug.declaration(statement.value.slot))
            if statement.expr is not None:
                variable = statement.value
                self.expr(statement.expr)
                self.emit(f"    lea r11, {self.slot(self.variables[variable.slot])}")
                self.store(variable.typ)
                if self.debug is not None:
                    self.emit(self.debug.binding(variable.slot))
        elif statement.kind == "assign":
            target, op = statement.value
            address = self.allocate()
            self.address(target)
            self.emit(f"    mov qword {self.slot(address)}, rax")
            if op == "=":
                self.expr(statement.expr)
            else:
                value = self.allocate()
                self.load(target.typ)
                self.emit(f"    mov qword {self.slot(value)}, rax")
                self.expr(statement.expr)
                self.emit("    mov r10, rax", f"    mov rax, qword {self.slot(value)}")
                self.binary(op[:-1], target.typ, statement.expr.typ, target.typ, statement.token)
            self.emit(f"    mov r11, qword {self.slot(address)}")
            self.store(target.typ)
            if self.debug is not None and target.kind == "name":
                self.emit(self.debug.binding(target.value.slot))
        elif statement.kind == "return":
            self.return_statement(statement)
        elif statement.kind == "cleanup":
            self.block(statement.body)
        elif statement.kind in {"defer", "local_const", "const"}:
            pass  # Checked exits and normal block tails own the cleanup lists.
        elif statement.kind == "call":
            self.expr(statement.expr)
        elif statement.kind == "asm":
            self.emit("    ; compiler barrier: inline asm begin", f"    {statement.value}",
                      "    ; compiler barrier: inline asm end")
        elif statement.kind in {"block", "unsafe"}:
            self.block(statement.body)
        elif statement.kind == "if":
            otherwise, end = self.label("else"), self.label("endif")
            self.expr(statement.expr)
            self.emit("    test rax, rax", f"    jz {otherwise}")
            self.block(statement.body)
            self.emit(f"    jmp {end}", otherwise + ":")
            self.block(statement.otherwise or [])
            self.emit(end + ":")
        elif statement.kind in {"while", "loop"}:
            start, end = self.label("while"), self.label("endwhile")
            self.loop_labels.append((start, end))
            self.emit(start + ":")
            if statement.kind == "while":
                self.expr(statement.expr)
                self.emit("    test rax, rax", f"    jz {end}")
            self.block(statement.body)
            self.emit(f"    jmp {start}", end + ":")
            self.loop_labels.pop()
        elif statement.kind == "for":
            self.for_statement(statement)
        elif statement.kind == "match":
            self.match_statement(statement)
        elif statement.kind in {"break", "continue"}:
            self.cleanups(statement)
            start, end = self.loop_labels[-1]
            self.emit(f"    jmp {end if statement.kind == 'break' else start}")
        else:
            raise AssertionError(statement.kind)

    def cleanups(self, node):
        for body in getattr(node, "cleanups", []):
            self.block(body)

    def return_statement(self, statement):
        saved = None
        if statement.expr is not None:
            if getattr(statement, "cleanups", []):
                saved = self.storage(self.function_returns, statement.token)
            self.expr(statement.expr)
            if saved is not None:
                self.emit(f"    lea r11, {self.slot(saved)}")
                self.store(self.function_returns)
        self.cleanups(statement)
        if saved is not None:
            self.emit(f"    lea rax, {self.slot(saved)}")
            self.load(self.function_returns)
        if self.is_pair(self.function_returns):
            if statement.expr is None:
                self.emit("    xor eax, eax", "    xor edx, edx")
            else:
                self.emit("    mov rdx, qword [rax+8]", "    mov rax, qword [rax]")
        self.emit(f"    jmp {self.return_label}")

    def for_statement(self, statement):
        if self.debug is not None:
            self.emit(self.debug.scope_begin(), self.debug.declaration(statement.variable.slot))
        cursor, limit = self.allocate(), self.allocate()
        pointer = None
        if statement.for_kind == "range":
            self.expr(statement.expr.args[0])
            self.emit(f"    mov qword {self.slot(cursor)}, rax")
            self.expr(statement.expr.args[1])
            self.emit(f"    mov qword {self.slot(limit)}, rax")
        else:
            pointer = self.allocate()
            receiver = statement.expr
            if statement.for_kind == "array":
                self.address(receiver) if receiver.addressable else self.expression(receiver)
                self.emit(f"    mov qword {self.slot(pointer)}, rax",
                          f"    mov rax, {self.types.array_length(receiver.typ)}")
            else:
                self.expression(receiver)
                self.emit("    mov r10, qword [rax]", f"    mov qword {self.slot(pointer)}, r10",
                          "    mov rax, qword [rax+8]")
            self.emit(f"    mov qword {self.slot(limit)}, rax", f"    mov qword {self.slot(cursor)}, 0")
        start, advance, end = self.label("for"), self.label("fornext"), self.label("endfor")
        self.emit(start + ":", f"    mov rax, qword {self.slot(cursor)}",
                  f"    cmp rax, qword {self.slot(limit)}", f"    jae {end}")
        if pointer is not None:
            size = self.types.layout(statement.element_type).size
            if size != 1:
                self.emit(f"    mov r10, {size}", "    imul rax, r10")
            self.emit(f"    add rax, qword {self.slot(pointer)}")
            self.load(statement.element_type)
        self.emit(f"    lea r11, {self.slot(self.variables[statement.variable.slot])}")
        self.store(statement.variable.typ)
        if self.debug is not None:
            self.emit(self.debug.binding(statement.variable.slot))
        self.loop_labels.append((advance, end))
        self.block(statement.body)
        self.loop_labels.pop()
        self.emit(advance + ":", f"    add qword {self.slot(cursor)}, 1", f"    jmp {start}", end + ":")
        if self.debug is not None:
            self.emit(self.debug.scope_end())

    def match_statement(self, statement):
        snapshot = self.storage(statement.expr.typ, statement.token)
        self.expr(statement.expr)
        self.emit(f"    lea r11, {self.slot(snapshot)}")
        self.store(statement.expr.typ)
        self.emit(f"    lea rax, {self.slot(snapshot)}")
        if self.is_pair(statement.expr.typ):
            self.emit("    mov rax, qword [rax]")
        else:
            self.load(statement.expr.typ)
        end = self.label("endmatch")
        labels = [self.label("arm") for _ in statement.value]
        for arm, label in zip(statement.value, labels):
            kind = arm.pattern.kind
            if kind == "wildcard":
                self.emit(f"    jmp {label}")
            elif kind == "err":
                self.emit("    test rax, rax", f"    jnz {label}")
            else:
                tag = getattr(arm, "tag_value", None)
                if tag is None:
                    tag = {"null": 0, "some": 1, "ok": 0}.get(kind, arm.pattern.value)
                self.emit(f"    mov r10, {int(tag)}", "    cmp rax, r10", f"    je {label}")
        self.emit(f"    jmp {end}")
        for arm, label in zip(statement.value, labels):
            self.emit(label + ":")
            if self.debug is not None:
                self.emit(self.debug.scope_begin())
            binding = getattr(arm, "binding", None)
            if binding is not None:
                if self.debug is not None:
                    self.emit(self.debug.declaration(binding.slot))
                offset = snapshot if arm.pattern.kind == "err" else snapshot - 8
                self.emit(f"    lea rax, {self.slot(offset)}")
                self.load(binding.typ)
                self.emit(f"    lea r11, {self.slot(self.variables[binding.slot])}")
                self.store(binding.typ)
                if self.debug is not None:
                    self.emit(self.debug.binding(binding.slot))
            self.block(arm.body)
            self.emit(f"    jmp {end}")
            if self.debug is not None:
                self.emit(self.debug.scope_end())
        self.emit(end + ":")

    def normalize(self, typ):
        if typ == "bool" or typ == "u8":
            self.emit("    movzx eax, al")
        elif typ == "i8":
            self.emit("    movsx rax, al")
        elif typ == "u16":
            self.emit("    movzx eax, ax")
        elif typ == "i16":
            self.emit("    movsx rax, ax")
        elif typ == "u32":
            self.emit("    mov eax, eax")
        elif typ == "i32":
            self.emit("    movsxd rax, eax")

    def load(self, typ, register="rax"):
        """Load a scalar from register, or retain an aggregate address in RAX."""
        if self.types.is_aggregate(typ) or self.is_pair(typ):
            return
        size = self.types.layout(typ).size
        if size == 8:
            self.emit(f"    mov rax, qword [{register}]")
        elif typ in {"i8", "i16"}:
            self.emit(f"    movsx rax, {self.WIDTH[size]} [{register}]")
        elif typ == "i32":
            self.emit(f"    movsxd rax, dword [{register}]")
        elif size == 4:
            self.emit(f"    mov eax, dword [{register}]")
        else:
            self.emit(f"    movzx eax, {self.WIDTH[size]} [{register}]")

    def store(self, typ):
        """Store RAX's value at R11. Aggregate copies have memmove semantics."""
        size = self.types.layout(typ).size
        if not (self.types.is_aggregate(typ) or self.is_pair(typ)):
            self.emit(f"    mov {self.WIDTH[size]} [r11], {self.ACC[size]}")
            return
        forward, end = self.label("copyforward"), self.label("copyend")
        self.emit("    mov r10, r11", "    mov rsi, rax", "    mov rdi, r11", f"    mov rcx, {size}",
                  "    cmp rdi, rsi", f"    jbe {forward}",
                  "    add rsi, rcx", "    dec rsi", "    add rdi, rcx", "    dec rdi", "    std",
                  "    rep movsb", "    cld", f"    jmp {end}", forward + ":", "    cld", "    rep movsb",
                  end + ":", "    mov rax, r10")

    def address(self, expr: Expr):
        if expr.kind == "global":
            self.emit(f"    lea rax, [rel ${expr.value.symbol}]")
        elif expr.kind == "name":
            self.emit(f"    lea rax, {self.slot(self.variables[expr.value.slot])}")
        elif expr.kind == "unary" and expr.value == "*":
            self.expr(expr.args[0])
        elif expr.kind == "field":
            base = expr.args[0]
            if self.types.is_pointer(base.typ):
                self.expr(base)
                base_type = self.types.pointee(base.typ)
            else:
                # A temporary aggregate must remain live until any enclosing
                # index expression has finished evaluating its index operand.
                self.address(base) if base.addressable else self.expression(base)
                base_type = base.typ
            offset = (8 if expr.value == "len" else 0) if self.types.is_slice(base_type) else self.types.layout(base_type).fields[expr.value].offset
            if offset:
                if offset <= 0x7fff_ffff:
                    self.emit(f"    add rax, {offset}")
                else:
                    self.emit(f"    mov r10, {offset}", "    add rax, r10")
        elif expr.kind == "index":
            base, index = expr.args
            temp = self.allocate()
            length_temp = self.allocate() if self.types.is_slice(base.typ) else None
            if self.types.is_pointer(base.typ):
                self.expr(base)
                element, length = self.types.pointee(base.typ), None
            else:
                self.address(base) if base.addressable else self.expression(base)
                element = self.types.element(base.typ)
                if self.types.is_slice(base.typ):
                    # Snapshot both words before evaluating an index that can
                    # mutate the receiver descriptor through an alias.
                    self.emit("    mov r10, qword [rax+8]", f"    mov qword {self.slot(length_temp)}, r10",
                              "    mov rax, qword [rax]")
                    length = None
                else:
                    length = self.types.array_length(base.typ)
            self.emit(f"    mov qword {self.slot(temp)}, rax")
            self.expr(index)
            if length_temp is not None:
                self.emit(f"    cmp rax, qword {self.slot(length_temp)}")
                self.check("jae", 1, expr.token)
            elif length is not None:
                self.emit(f"    mov r10, {length}", "    cmp rax, r10")
                self.check("jae", 1, expr.token)
            size = self.types.layout(element).size
            if size != 1:
                self.emit(f"    mov r10, {size}", "    imul rax, r10")
            self.emit(f"    add rax, qword {self.slot(temp)}")
        else:
            raise AssertionError("not an lvalue: " + expr.kind)

    def expr(self, expr: Expr):
        saved = self.next_temp
        self.expression(expr)
        self.next_temp = saved

    def expression(self, expr: Expr):
        if expr.kind == "field" and expr.value == "len" and self.types.is_array(expr.args[0].typ):
            self.expr(expr.args[0])
            self.emit(f"    mov rax, {self.types.array_length(expr.args[0].typ)}")
        elif expr.constant is not None:
            self.emit(f"    mov rax, {int(expr.constant) & ((1 << 64) - 1)}")
        elif expr.kind == "null":
            self.emit("    xor eax, eax")
        elif expr.kind == "function":
            if expr.value.external:
                self.external_symbols.add(expr.value.symbol)
            self.emit(f"    lea rax, [rel ${expr.value.symbol}]")
        elif expr.kind in {"name", "global", "field", "index"}:
            self.address(expr)
            self.load(expr.typ)
        elif expr.kind == "cast":
            self.expr(expr.args[0])
            self.normalize(expr.typ)
        elif expr.kind == "call":
            self.call(expr)
        elif expr.kind == "intrinsic":
            self.intrinsic(expr)
        elif expr.kind == "pair":
            self.pair(expr)
        elif expr.kind in {"try", "orelse"}:
            self.unwrap(expr)
        elif expr.kind == "exit":
            self.exit_expression(expr)
        elif expr.kind in {"slice", "raw_slice", "string"}:
            self.slice(expr)
        elif expr.kind in {"array", "struct"}:
            destination = self.storage(expr.typ, expr.token)
            layout = self.types.layout(expr.typ)
            self.emit(f"    lea rdi, {self.slot(destination)}", f"    mov ecx, {layout.size}", "    xor eax, eax", "    rep stosb")
            if expr.kind == "struct":
                names = expr.value[1]
                for name, arg in zip(names, expr.args):
                    self.expr(arg)
                    field = layout.fields[name]
                    self.emit(f"    lea r11, {self.slot(destination - field.offset)}")
                    self.store(field.type)
            else:
                element = self.types.element(expr.typ)
                stride = self.types.layout(element).size
                if expr.value is None:
                    for index, arg in enumerate(expr.args):
                        self.expr(arg)
                        self.emit(f"    lea r11, {self.slot(destination - index * stride)}")
                        self.store(element)
                else:
                    # Evaluate a repeat initializer exactly once, then copy it.
                    value = self.storage(element, expr.token)
                    self.expr(expr.args[0])
                    self.emit(f"    lea r11, {self.slot(value)}")
                    self.store(element)
                    for index in range(expr.value if stride else 0):
                        self.emit(f"    lea rax, {self.slot(value)}")
                        self.load(element)
                        self.emit(f"    lea r11, {self.slot(destination - index * stride)}")
                        self.store(element)
            self.emit(f"    lea rax, {self.slot(destination)}")
        elif expr.kind == "unary":
            if expr.value == "&":
                self.address(expr.args[0])
                return
            self.expr(expr.args[0])
            if expr.value == "*":
                self.load(expr.typ)
            elif expr.value == "!":
                self.emit("    test rax, rax", "    sete al", "    movzx eax, al")
            elif expr.value == "~":
                self.emit("    not rax")
                self.normalize(expr.typ)
            else:
                self.emit("    neg rax")
                if self.mode == "debug":
                    self.check("jo" if is_signed(expr.typ) else "jc", 2, expr.token)
                    self.check_range(expr.typ, expr.token)
                self.normalize(expr.typ)
        elif expr.kind == "binary":
            op = expr.value
            left, right = expr.args
            if op in {"&&", "||"}:
                end = self.label("shortcircuit")
                self.expr(left)
                self.emit("    test rax, rax", f"    {'jz' if op == '&&' else 'jnz'} {end}")
                self.expr(right)
                self.emit(end + ":")
                return
            offset = self.allocate()
            self.expr(left)
            self.emit(f"    mov qword {self.slot(offset)}, rax")
            self.expr(right)
            self.emit("    mov r10, rax", f"    mov rax, qword {self.slot(offset)}")
            self.binary(op, left.typ, right.typ, expr.typ, expr.token)
        else:
            raise AssertionError(expr.kind)

    def pair(self, expr):
        tag, payload_type = expr.value
        if not self.is_pair(expr.typ):
            self.emit(f"    mov rax, {tag}")
            return
        destination = self.storage(expr.typ, expr.token)
        self.emit(f"    mov r10, {tag}", f"    mov qword {self.slot(destination)}, r10",
                  f"    mov qword {self.slot(destination - 8)}, 0")
        if expr.args:
            self.expr(expr.args[0])
            size = self.types.layout(payload_type).size
            self.emit(f"    mov {self.WIDTH[size]} {self.slot(destination - 8)}, {self.ACC[size]}")
        self.emit(f"    lea rax, {self.slot(destination)}")

    def unwrap(self, expr):
        failure, end = self.label("unwrapfail"), self.label("unwrapend")
        failure_slot = self.storage(self.function_returns, expr.token) if expr.kind == "try" else None
        self.expr(expr.args[0])
        self.emit("    cmp qword [rax], 0", f"    {'jne' if expr.kind == 'try' else 'je'} {failure}")
        if expr.payload_type == "void":
            self.emit("    xor eax, eax")
        else:
            self.emit("    add rax, 8")
            self.load(expr.payload_type)
        self.emit(f"    jmp {end}", failure + ":")
        if expr.kind == "try":
            self.emit("    mov r10, qword [rax]", f"    mov qword {self.slot(failure_slot)}, r10",
                      f"    mov qword {self.slot(failure_slot - 8)}, 0")
            self.cleanups(expr)
            self.emit(f"    mov rax, qword {self.slot(failure_slot)}", "    xor edx, edx", f"    jmp {self.return_label}")
        else:
            self.expr(expr.args[1])
        self.emit(end + ":")

    def exit_expression(self, expr):
        if expr.value == "return":
            statement = Stmt(expr.token, "return", expr=expr.args[0] if expr.args else None)
            statement.cleanups = getattr(expr, "cleanups", [])
            self.return_statement(statement)
        else:
            self.cleanups(expr)
            start, end = self.loop_labels[-1]
            self.emit(f"    jmp {start if expr.value == 'continue' else end}")

    def intrinsic(self, expr):
        name, typ = expr.value, expr.intrinsic_type
        slots = []
        # Finish and snapshot each argument before evaluating the next one.
        # In particular a value-producing call can modify the original pointer.
        for argument in expr.args:
            offset = self.allocate()
            self.expr(argument)
            self.emit(f"    mov qword {self.slot(offset)}, rax")
            slots.append(offset)
        if name == "compiler_fence":
            self.emit("    ; compiler barrier: compiler_fence (no CPU instruction)")
            return
        self.emit(f"    ; intrinsic {name}")
        if name.startswith("wrapping_"):
            instruction = {"wrapping_add": "add", "wrapping_sub": "sub", "wrapping_mul": "imul"}[name]
            self.emit(f"    mov rax, qword {self.slot(slots[0])}",
                      f"    mov r10, qword {self.slot(slots[1])}", f"    {instruction} rax, r10")
            self.normalize(typ)
            return
        self.emit(f"    mov r11, qword {self.slot(slots[0])}")
        if name in {"read_unaligned", "volatile_load", "atomic_load"}:
            # x86 scalar MOV permits unaligned integer accesses; volatile uses
            # precisely one target access. Seq-cst atomics consistently use the
            # MOV-load / locked-XCHG-store mapping for ordinary cached memory.
            self.load(typ, "r11")
            return
        size = self.types.layout(typ).size
        if name in {"write_unaligned", "volatile_store"}:
            self.emit(f"    mov rax, qword {self.slot(slots[1])}")
            self.store(typ)
        elif name == "atomic_store":
            self.emit(f"    mov rax, qword {self.slot(slots[1])}",
                      f"    xchg {self.WIDTH[size]} [r11], {self.ACC[size]}")
        elif name == "atomic_compare_exchange":
            self.emit(f"    mov rax, qword {self.slot(slots[1])}",
                      f"    mov r10, qword {self.slot(slots[2])}",
                      f"    lock cmpxchg {self.WIDTH[size]} [r11], {'r10d' if size == 4 else 'r10'}")
            self.normalize(typ)
        elif name == "atomic_fetch_add":
            self.emit(f"    mov rax, qword {self.slot(slots[1])}",
                      f"    lock xadd {self.WIDTH[size]} [r11], {self.ACC[size]}")
            self.normalize(typ)
        else:
            raise AssertionError("unknown intrinsic: " + name)

    def call(self, expr):
        function = expr.value
        indirect = isinstance(function, Expr)
        callee = None
        if indirect:
            # A field/index/call receiver can have effects, and argument
            # evaluation can replace its original function pointer storage.
            callee = self.allocate()
            self.expr(function)
            self.emit(f"    mov qword {self.slot(callee)}, rax")
            signature = self.types.function_signature(function.typ)
            abi = signature.abi
            never_returns = signature.returns == "noreturn"
        else:
            abi = function.abi
            never_returns = function.returns == "noreturn"
        never_returns = never_returns or getattr(expr, "never_returns", False)
        abi = getattr(expr, "call_abi", abi)
        locations, outgoing = self.parameter_locations([arg.typ for arg in expr.args], abi)
        slots = []
        # Every argument owns a snapshot, including descriptor values. Later
        # arguments may modify the original slice or allocate nested temporaries.
        for arg in expr.args:
            offset = self.storage(arg.typ, arg.token) if self.is_pair(arg.typ) else self.allocate()
            slots.append(offset)
            self.expr(arg)
            if self.is_pair(arg.typ):
                self.emit("    mov r10, qword [rax]", f"    mov qword {self.slot(offset)}, r10",
                          "    mov r10, qword [rax+8]", f"    mov qword {self.slot(offset - 8)}, r10")
            else:
                self.emit(f"    mov qword {self.slot(offset)}, rax")
        result = self.storage(expr.typ, expr.token) if self.is_pair(expr.typ) and not never_returns else None
        self.max_outgoing = max(self.max_outgoing, outgoing)
        if outgoing:
            self.emit(f"    sub rsp, {outgoing}")
        # Copy stack words first: RAX is scratch and cannot disturb assigned
        # argument registers. Padding belongs after the final stack argument.
        for arg, offset, (registers, stack_offset) in zip(expr.args, slots, locations):
            if registers is None:
                for word in range(2 if self.is_pair(arg.typ) else 1):
                    self.emit(f"    mov rax, qword {self.slot(offset - 8 * word)}",
                              f"    mov qword [rsp+{stack_offset + 8 * word}], rax")
        for arg, offset, (registers, _) in zip(expr.args, slots, locations):
            if registers:
                for word, register in enumerate(registers):
                    self.emit(f"    mov {register}, qword {self.slot(offset - 8 * word)}")
        if indirect:
            self.emit(f"    mov r11, qword {self.slot(callee)}", "    call r11")
        else:
            if function.external:
                self.external_symbols.add(function.symbol)
            self.emit(f"    call ${function.symbol}")
        if never_returns:
            self.emit("    ud2")
            return
        if outgoing:
            self.emit(f"    add rsp, {outgoing}")
        if result is not None:
            self.emit(f"    mov qword {self.slot(result)}, rax", f"    mov qword {self.slot(result - 8)}, rdx",
                      f"    lea rax, {self.slot(result)}")
        else:
            self.normalize(expr.typ)

    def slice(self, expr):
        destination = self.storage(expr.typ, expr.token)
        if expr.kind == "string":
            label = "__dg_string_" + str(len(self.strings))
            data = expr.value if isinstance(expr.value, bytes) else expr.value.encode("utf-8")
            self.strings.append((label, data))
            self.emit(f"    lea rax, [rel {label}]", f"    mov qword {self.slot(destination)}, rax",
                      f"    mov rax, {len(data)}", f"    mov qword {self.slot(destination - 8)}, rax")
        elif expr.kind == "raw_slice":
            self.expr(expr.args[0])
            self.emit(f"    mov qword {self.slot(destination)}, rax")
            self.expr(expr.args[1])
            self.emit(f"    mov qword {self.slot(destination - 8)}, rax")
        else:
            base, lower, upper = expr.args
            pointer, length, lo, hi = [self.allocate() for _ in range(4)]
            if self.types.is_array(base.typ):
                self.address(base)
                self.emit(f"    mov qword {self.slot(pointer)}, rax", f"    mov rax, {self.types.array_length(base.typ)}",
                          f"    mov qword {self.slot(length)}, rax")
            else:
                self.expression(base)
                self.emit("    mov r10, qword [rax]", f"    mov qword {self.slot(pointer)}, r10",
                          "    mov r10, qword [rax+8]", f"    mov qword {self.slot(length)}, r10")
            if lower is None:
                self.emit("    xor eax, eax")
            else:
                self.expr(lower)
            self.emit(f"    mov qword {self.slot(lo)}, rax")
            if upper is None:
                self.emit(f"    mov rax, qword {self.slot(length)}")
            else:
                self.expr(upper)
            self.emit(f"    mov qword {self.slot(hi)}, rax", f"    cmp rax, qword {self.slot(length)}")
            self.check("ja", 1, expr.token)
            self.emit(f"    mov rax, qword {self.slot(lo)}", f"    cmp rax, qword {self.slot(hi)}")
            self.check("ja", 1, expr.token)
            size = self.types.layout(self.types.element(expr.typ)).size
            if size != 1:
                self.emit(f"    mov r10, {size}", "    imul rax, r10")
            self.emit(f"    add rax, qword {self.slot(pointer)}", f"    mov qword {self.slot(destination)}, rax",
                      f"    mov rax, qword {self.slot(hi)}", f"    sub rax, qword {self.slot(lo)}",
                      f"    mov qword {self.slot(destination - 8)}, rax")
        self.emit(f"    lea rax, {self.slot(destination)}")

    def check_range(self, typ, token):
        if typ not in INTEGER or bits(typ) == 64:
            return
        lo, hi = bounds(typ)
        if is_signed(typ):
            self.emit(f"    cmp rax, {lo}")
            self.check("jl", 2, token)
        # u32's maximum is not encodable as a sign-extended imm32.
        self.emit(f"    mov r11, {hi}", "    cmp rax, r11")
        self.check("jg" if is_signed(typ) else "ja", 2, token)

    def binary(self, op, left_type, right_type, typ, token):
        """RAX is the left scalar and R10 the right scalar."""
        if self.types.is_pointer(left_type) and op in {"+", "-"}:
            size = self.types.layout(self.types.pointee(left_type)).size
            self.emit(f"    mov r11, {size}", "    imul r10, r11", f"    {'add' if op == '+' else 'sub'} rax, r10")
            return
        signed = is_signed(left_type)
        if op in {"+", "-"}:
            self.emit(f"    {'add' if op == '+' else 'sub'} rax, r10")
            if self.mode == "debug":
                self.check("jo" if signed else "jc", 2, token)
                self.check_range(typ, token)
        elif op == "*":
            if not signed and bits(typ) == 64 and self.mode == "debug":
                self.emit("    mul r10", "    test rdx, rdx")
                self.check("jnz", 2, token)
            else:
                self.emit("    imul rax, r10")
                if self.mode == "debug":
                    self.check("jo", 2, token)
                    self.check_range(typ, token)
        elif op in {"/", "%"}:
            self.emit("    test r10, r10")
            self.check("jz", 3, token)
            if signed:
                safe = self.label("divsafe")
                minimum = bounds(typ)[0]
                self.emit(f"    mov r11, {minimum}", "    cmp rax, r11", f"    jne {safe}", "    cmp r10, -1")
                self.check("je", 5, token)
                self.emit(safe + ":", "    cqo", "    idiv r10")
            else:
                self.emit("    xor edx, edx", "    div r10")
            if op == "%":
                self.emit("    mov rax, rdx")
        elif op in {"<<", ">>"}:
            self.emit(f"    cmp r10, {bits(typ)}")
            self.check("jae", 4, token)
            self.emit("    mov rcx, r10", f"    {'shl' if op == '<<' else 'sar' if signed else 'shr'} rax, cl")
        elif op in {"&", "|", "^"}:
            self.emit(f"    { {'&': 'and', '|': 'or', '^': 'xor'}[op]} rax, r10")
        else:
            condition = {"==": "e", "!=": "ne", "<": "l" if signed else "b", "<=": "le" if signed else "be", ">": "g" if signed else "a", ">=": "ge" if signed else "ae"}[op]
            self.emit("    cmp rax, r10", f"    set{condition} al", "    movzx eax, al")
            return
        self.normalize(typ)
