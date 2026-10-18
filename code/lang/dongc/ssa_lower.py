"""Checked scalar/pointer AST to SSA and an ordered-memory x86-64 backend.

This optional release backend deliberately rejects a whole function before
emitting code when it contains unsupported calls, checks, or cleanup. Volatile,
atomic and barrier operations retain L1. Ordinary memory stays ordered; no alias,
trap or ABI assumption is guessed.
"""
from __future__ import annotations

from dataclasses import asdict
from . import ssa
from .model import COMPARISONS
from .typesys import is_pointer, pointee


class Unsupported(Exception):
    pass


SCALARS = {"u64", "i64", "bool"}
OPS = {"+": "add", "-": "sub", "*": "mul", "&": "and", "|": "or", "^": "xor"}


def ir_type(typ):
    if is_pointer(typ):return 'u64'
    if typ in SCALARS|{'void'}:return typ
    raise Unsupported('non-64-bit scalar or pointer value')


class Lower:
    def __init__(self, function):
        self.function = function
        if function.abi != "sysv64":
            raise Unsupported("non-scalar or non-SysV signature")
        ir_type(function.returns)
        self.types, self.blocks, self.counter = {}, [], 0
        self.slot_types = {v.slot: ir_type(v.typ) for v in function.variables}
        self.next_slot = max(self.slot_types, default=-1) + 1
        self.current = self.block("entry")
        self.params = tuple(self.value(ir_type(v.typ)) for v in function.variables[:len(function.params)])
        self.param_env = {v.slot: p for v, p in zip(function.variables, self.params)}
        self.loops = []
        self.inline_env = None
        self.inline_stack = [function.symbol]
        self.inline_count = 0

    def value(self, typ):
        result = len(self.types)
        self.types[result] = typ
        return result

    def block(self, prefix):
        name = prefix if not self.blocks else f"{prefix}_{len(self.blocks)}"
        block = ssa.Block(name, [], None)
        self.blocks.append(block)
        return block

    def emit(self, op, typ, args=(), imm=None, token=None):
        typ=ir_type(typ)
        value = self.value(typ)
        self.current.instructions.append(ssa.Instruction(value, op, typ, tuple(args), imm, token))
        return value

    def terminate(self, op, args=(), targets=(), token=None):
        assert self.current.terminator is None
        self.current.terminator = ssa.Terminator(op, tuple(args), tuple(targets), token)

    def get(self, slot, token=None):
        return self.emit("get", self.slot_types[slot], imm=slot, token=token)

    def set(self, slot, value):
        self.current.instructions.append((slot, value))

    def temporary(self, typ):
        slot = self.next_slot
        self.next_slot += 1
        self.slot_types[slot] = typ
        return slot

    def expression(self, expr):
        ir_type(expr.typ)
        if expr.constant is not None:
            return self.emit("const", expr.typ, imm=int(expr.constant), token=expr.token)
        if expr.kind == "name":
            if self.inline_env is not None:
                if expr.value.slot not in self.inline_env:
                    raise Unsupported("inline helper has a non-parameter local")
                return self.inline_env[expr.value.slot]
            return self.get(expr.value.slot, expr.token)
        if expr.kind == "cast":
            child = expr.args[0]
            if ir_type(expr.typ) not in {"u64", "i64"} or ir_type(child.typ) not in {"u64", "i64"}:
                raise Unsupported("narrow or boolean cast")
            return self.emit("cast", expr.typ, (self.expression(child),), token=expr.token)
        if expr.kind == "unary" and expr.value in {"-", "~", "!"}:
            child = self.expression(expr.args[0])
            if expr.value == "!":
                zero = self.emit("const", "bool", imm=0)
                return self.emit("cmp", "bool", (child, zero), "==", expr.token)
            return self.emit("neg" if expr.value == "-" else "not", expr.typ, (child,), token=expr.token)
        if expr.kind=='unary'and expr.value=='*':
            return self.emit('load',expr.typ,(self.expression(expr.args[0]),),token=expr.token)
        if expr.kind=='index'and is_pointer(expr.args[0].typ):
            return self.emit('load',expr.typ,(self.address(expr),),token=expr.token)
        if expr.kind == "binary":
            op = expr.value
            left = self.expression(expr.args[0])
            if op in {"&&", "||"}:
                right_block, shortcut, join = self.block("rhs"), self.block("short"), self.block("join")
                result = self.temporary("bool")
                targets = (right_block.name, shortcut.name) if op == "&&" else (shortcut.name, right_block.name)
                self.terminate("branch", (left,), targets, expr.token)
                self.current = shortcut
                self.set(result, self.emit("const", "bool", imm=int(op == "||")))
                self.terminate("jump", targets=(join.name,))
                self.current = right_block
                self.set(result, self.expression(expr.args[1]))
                self.terminate("jump", targets=(join.name,))
                self.current = join
                return self.get(result, expr.token)
            if op not in OPS and op not in COMPARISONS:
                raise Unsupported("checked division or shift")
            right = self.expression(expr.args[1])
            if is_pointer(expr.typ) and op in {'+','-'}:
                return self.emit('addr','u64',(left,right),(expr.element_size,1 if op=='+'else -1),expr.token)
            return self.emit("cmp" if op in COMPARISONS else OPS[op], expr.typ,
                             (left, right), op if op in COMPARISONS else None, expr.token)
        if expr.kind == "intrinsic" and expr.value in {"wrapping_add", "wrapping_sub", "wrapping_mul"}:
            args = [self.expression(arg) for arg in expr.args]
            return self.emit(expr.value[9:], expr.typ, args, token=expr.token)
        if expr.kind == "call":
            callee = expr.value
            if (not hasattr(callee, "body") or callee.external or callee.abi != "sysv64" or
                    callee.returns not in SCALARS or any(t not in SCALARS for _, t in callee.params)):
                raise Unsupported("non-inlineable call")
            body = [s for s in callee.body if s.kind in {"return", "local_const"}]
            def pure(node):
                return not(node.kind in {'global','index'}or(node.kind=='unary'and node.value in {'*','&'}))and all(pure(c)for c in node.args if c is not None)
            if (len(body) != len(callee.body) or sum(s.kind == "return" for s in body) != 1 or
                    any(getattr(s, "cleanups", []) for s in body) or
                    callee.symbol in self.inline_stack or len(self.inline_stack) >= 5 or self.inline_count >= 32 or
                    any(s.expr is not None and not pure(s.expr)for s in body)):
                raise Unsupported("call requires L1 ABI or exceeds inline budget")
            # Arguments are snapshotted in caller context, once, left to right.
            args = [self.expression(arg) for arg in expr.args]
            prior = self.inline_env
            self.inline_env = {v.slot: value for v, value in zip(callee.variables, args)}
            self.inline_stack.append(callee.symbol)
            self.inline_count += 1
            try:
                return self.expression(next(s.expr for s in body if s.kind == "return"))
            finally:
                self.inline_stack.pop()
                self.inline_env = prior
        raise Unsupported(f"expression {expr.kind} requires L1 effects/checks")

    def address(self,expr):
        if expr.kind=='unary'and expr.value=='*':return self.expression(expr.args[0])
        if expr.kind=='index'and is_pointer(expr.args[0].typ):
            base=self.expression(expr.args[0]);index=self.expression(expr.args[1])
            return self.emit('addr','u64',(base,index),(expr.element_size,1),expr.token)
        raise Unsupported('addressable aggregate/local requires L1 storage')

    def statements(self, statements):
        for statement in statements:
            if self.current.terminator is not None:
                break
            if getattr(statement, "cleanups", []):
                raise Unsupported("deferred cleanup")
            kind = statement.kind
            if kind == "binding":
                if statement.expr is not None:
                    self.set(statement.value.slot, self.expression(statement.expr))
            elif kind == "assign":
                target, op = statement.value
                address=self.address(target)if target.kind!='name'else None
                left = (self.get(target.value.slot,target.token)if address is None else
                        self.emit('load',target.typ,(address,),token=target.token)) if op!='='else None
                right = self.expression(statement.expr)
                if op != "=":
                    if op[:-1] not in OPS:
                        raise Unsupported("checked compound operation")
                    if is_pointer(target.typ):
                        element=ir_type(pointee(target.typ))
                        right=self.emit('addr','u64',(left,right),(1 if element=='bool'else 8,1 if op=='+='else -1),statement.token)
                    else:right = self.emit(OPS[op[:-1]], target.typ, (left, right), token=statement.token)
                if address is None:self.set(target.value.slot,right)
                else:self.emit('store',target.typ,(address,right),token=statement.token)
            elif kind == "return":
                args = () if statement.expr is None else (self.expression(statement.expr),)
                self.terminate("return", args, token=statement.token)
            elif kind in {"block", "unsafe"}:
                self.statements(statement.body)
            elif kind in {"local_const", "const"}:
                pass
            elif kind == "if":
                condition = self.expression(statement.expr)
                yes, no, join = self.block("yes"), self.block("no"), self.block("join")
                self.terminate("branch", (condition,), (yes.name, no.name), statement.token)
                for block, body in ((yes, statement.body), (no, statement.otherwise or [])):
                    self.current = block
                    self.statements(body)
                    if self.current.terminator is None:
                        self.terminate("jump", targets=(join.name,))
                self.current = join
            elif kind in {"while", "loop", "for"}:
                self.loop(statement)
            elif kind in {"break", "continue"}:
                start, end = self.loops[-1]
                self.terminate("jump", targets=(end if kind == "break" else start,), token=statement.token)
            else:
                raise Unsupported(f"statement {kind} requires L1 effects/checks")

    def loop(self, statement):
        is_for = statement.kind == "for"
        if is_for:
            if statement.for_kind != "range":
                raise Unsupported("array/slice iteration")
            cursor, limit = statement.variable.slot, self.temporary("u64")
            self.set(cursor, self.expression(statement.expr.args[0]))
            self.set(limit, self.expression(statement.expr.args[1]))
        test, body, end = self.block("test"), self.block("body"), self.block("end")
        advance = self.block("advance") if is_for else test
        self.terminate("jump", targets=(test.name,))
        self.current = test
        if is_for:
            condition = self.emit("cmp", "bool", (self.get(cursor), self.get(limit)), "<")
        elif statement.kind == "while":
            condition = self.expression(statement.expr)
        else:
            condition = self.emit("const", "bool", imm=1)
        self.terminate("branch", (condition,), (body.name, end.name), statement.token)
        self.current = body
        self.loops.append((advance.name, end.name))
        self.statements(statement.body)
        self.loops.pop()
        if self.current.terminator is None:
            self.terminate("jump", targets=(advance.name,))
        if is_for:
            self.current = advance
            one = self.emit("const", "u64", imm=1)
            self.set(cursor, self.emit("add", "u64", (self.get(cursor), one)))
            self.terminate("jump", targets=(test.name,))
        self.current = end

    def finish(self):
        self.statements(self.function.body)
        if self.current.terminator is None:
            if self.function.returns != "void":
                # A checker-proven unreachable merge may have no predecessor.
                self.terminate("return", (self.emit("const", self.function.returns, imm=0),))
            else:
                self.terminate("return")
        by_name = {b.name: b for b in self.blocks}
        reachable, todo = set(), ["entry"]
        while todo:
            name = todo.pop()
            if name not in reachable:
                reachable.add(name)
                block = by_name[name]
                if block.terminator is None:
                    raise Unsupported("unterminated reachable block")
                todo.extend(block.terminator.targets)
        self.blocks = [b for b in self.blocks if b.name in reachable]
        predecessors = {b.name: set() for b in self.blocks}
        uses, defs = {}, {}
        for block in self.blocks:
            used, defined = set(), set()
            for ins in block.instructions:
                if isinstance(ins, tuple):
                    defined.add(ins[0])
                elif ins.op == "get" and ins.imm not in defined:
                    used.add(ins.imm)
            uses[block.name], defs[block.name] = used, defined
            for name in block.terminator.targets:
                predecessors[name].add(block.name)
        live = {b.name: set() for b in self.blocks}
        changed = True
        while changed:
            changed = False
            for block in reversed(self.blocks):
                out = set().union(*(live[t] for t in block.terminator.targets))
                value = uses[block.name] | (out - defs[block.name])
                if value != live[block.name]:
                    live[block.name], changed = value, True
        incoming, outgoing = {}, {}
        for block in self.blocks:
            incoming[block.name] = (dict(self.param_env) if block.name == "entry" else
                                    {slot: self.value(self.slot_types[slot]) for slot in sorted(live[block.name])})
            env, instructions = dict(incoming[block.name]), []
            for ins in block.instructions:
                if isinstance(ins, tuple):
                    env[ins[0]] = ins[1]
                elif ins.op == "get":
                    if ins.imm not in env:
                        raise Unsupported("uninitialized value on a syntactically reachable edge")
                    instructions.append(ssa.Instruction(ins.result, "copy", ins.typ, (env[ins.imm],), token=ins.token))
                else:
                    instructions.append(ins)
            outgoing[block.name] = env
            block.instructions = instructions
        for block in self.blocks:
            if block.name == "entry":
                continue
            phis = []
            for slot, value in incoming[block.name].items():
                try:
                    edges = tuple((p, outgoing[p][slot]) for p in sorted(predecessors[block.name]))
                except KeyError:
                    raise Unsupported("uninitialized value on a syntactically reachable edge") from None
                phis.append(ssa.Instruction(value, "phi", self.slot_types[slot], imm=edges))
            block.instructions = phis + block.instructions
        used_ids = set(self.params)
        used_ids.update(i.result for b in self.blocks for i in b.instructions)
        result = ssa.Function(self.function.symbol, self.params, {v: self.types[v] for v in used_ids},
                              self.blocks, "entry", ir_type(self.function.returns))
        ssa.verify(result)
        return result


from .ssa_x86 import assembly


def compile_function(function):
    lower = Lower(function)
    lowered = lower.finish()
    optimized = ssa.optimize(lowered)
    ssa.verify(optimized)
    lines, allocation = assembly(optimized)
    def dump(ir):
        return {"name": ir.name, "params": list(ir.params), "value_types": ir.value_types,
                "entry": ir.entry, "return_type": ir.return_type,
                "blocks": [{"name": b.name, "instructions": [
                    {k: v for k, v in asdict(i).items() if k != "token"} for i in b.instructions],
                    "terminator": {k: v for k, v in asdict(b.terminator).items() if k != "token"}}
                    for b in ir.blocks]}
    return lines, {"symbol": function.symbol, "backend": "ssa", "before": dump(lowered),
                   "after": dump(optimized), "allocation": allocation, "inlined_calls": lower.inline_count}
