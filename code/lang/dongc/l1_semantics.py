"""Structured control flow and tagged-value semantics for the complete L1 layer."""
from __future__ import annotations
from copy import copy
from .model import *


class L1CheckerMixin:
    @staticmethod
    def flow(initialized, reachable=True):
        from .checker import Flow
        return Flow(set(initialized), reachable)

    def cleanup_lists(self, loop_only=False):
        frames = getattr(self, "defer_frames", [])
        start = self.loop_scopes[-1] if loop_only and getattr(self, "loop_scopes", []) else 0
        return [body for frame in reversed(frames[start:]) for body in reversed(frame)]

    @staticmethod
    def terminates(expr):
        if expr is None:
            return False
        if expr.typ == "noreturn" or getattr(expr,"never_returns",False):
            return True
        if expr.kind == "binary" and expr.value in {"&&","||"}:
            left,right = expr.args
            return L1CheckerMixin.terminates(left) or ((left.constant is True if expr.value == "&&" else left.constant is False) and L1CheckerMixin.terminates(right))
        if expr.kind == "orelse":
            return L1CheckerMixin.terminates(expr.args[0]) or (L1CheckerMixin.known_tag(expr.args[0]) == 0 and L1CheckerMixin.terminates(expr.args[1]))
        if expr.kind == "try":
            known = L1CheckerMixin.known_tag(expr.args[0])
            return L1CheckerMixin.terminates(expr.args[0]) or known is not None and known != 0
        callee = expr.value if expr.kind == "call" and isinstance(expr.value,Expr) else None
        return L1CheckerMixin.terminates(callee) or any(L1CheckerMixin.terminates(child) for child in expr.args if child is not None)

    @staticmethod
    def known_tag(expr):
        if expr.kind == "pair":
            return expr.value[0]
        if expr.kind == "global" and not getattr(expr.value,"mutable",False) and expr.value.initializer is not None:
            return int.from_bytes(expr.value.initializer.data[:8],"little")
        return expr.constant

    def coerce(self, expr, expected):
        if expr.typ == "noreturn":
            expr.never_returns = True
            expr.typ = expected
            return expected
        if expr.typ == expected:
            return expected
        if self.types.is_optional(expected) or self.types.is_result(expected):
            payload = self.types.payload(expected)
            if expr.typ == "error":
                if not self.types.is_result(expected):
                    fail("E0301", expr.token, "errors require an error-result context")
                expr.kind, expr.value, expr.args = "pair", (int(expr.constant), None), []
            elif expr.typ == "null" and self.types.is_optional(expected):
                expr.kind, expr.value, expr.args = "pair", (0, None), []
            else:
                if payload == "void":
                    fail("E0301", expr.token, "!void success requires return;")
                self.base_coerce(expr, payload)
                value = copy(expr)
                expr.kind, expr.value, expr.args = "pair", (1 if self.types.is_optional(expected) else 0, payload), [value]
            expr.typ, expr.constant = expected, None
            expr.aggregate, expr.addressable, expr.writable = True, False, False
            return expected
        return self.base_coerce(expr, expected)

    def enum_constructor(self, expr, initialized):
        typ, tag, child = expr.value
        if child is None:
            if expr.args:
                fail("E0301", expr.token, "this enum variant has no payload")
        elif len(expr.args) != 1:
            fail("E0301", expr.token, "this enum variant requires exactly one payload")
        else:
            self.expr(expr.args[0], initialized, child)
        expr.typ = typ
        if self.types.is_pair(typ):
            expr.kind, expr.value = "pair", (tag, child)
            expr.aggregate = True
        else:
            expr.kind, expr.constant, expr.value = "constant", tag, (typ, tag)
        expr.addressable = expr.writable = False
        expr.alignment = 8

    def expr(self, expr, initialized, expected=None, *, read=True):
        # Type-check dead children as usual, but do not let their control
        # transfers create loop exits. A previous argument may never return,
        # and a short-circuit RHS may never execute at all.
        if not hasattr(self,"expression_frames"):
            self.expression_frames = []
        parent = self.expression_frames[-1] if self.expression_frames else None
        live = getattr(self,"current_reachable",True) and (parent is None or parent[1])
        if parent is not None:
            enclosing = parent[0]
            if enclosing.kind == "binary" and enclosing.value in {"&&","||"} and expr is enclosing.args[1]:
                skip = enclosing.args[0].constant is (False if enclosing.value == "&&" else True)
                live = live and not skip
        frame = [expr,live]
        self.expression_frames.append(frame)
        try:
            result = self.checked_expr(expr,initialized,expected,read=read)
        finally:
            self.expression_frames.pop()
        if parent is not None and live and self.terminates(expr):
            parent[1] = False
        return result

    def checked_expr(self, expr, initialized, expected=None, *, read=True):
        if getattr(self,"in_defer",False) and expr.kind == "name":
            variable = expr.value if isinstance(expr.value,Variable) else self.lookup(expr.token)
            if variable.slot in self.defer_captured_slots:
                read = True
        if getattr(expr, "_l1_checked", False):
            if expr.kind == "name" and read and expr.value.slot not in initialized:
                fail("E0401", expr.token, "binding may be uninitialized", expr.value.token)
            if expected is not None:
                self.coerce(expr, expected)
            return expr.typ
        if expr.kind == "enum_constructor":
            self.enum_constructor(expr, initialized)
        elif expr.kind == "error":
            expr.typ, expr.constant = "error", int(expr.value)
            expr.addressable = expr.writable = expr.aggregate = False
            expr.alignment = 8
        elif expr.kind == "try":
            if getattr(self, "in_defer", False):
                fail("E0501", expr.token, "try is not allowed in defer")
            if not self.types.is_result(self.function.returns):
                fail("E0501", expr.token, "try requires an error-returning function")
            self.expr(expr.args[0], initialized)
            if not self.types.is_result(expr.args[0].typ):
                fail("E0301", expr.token, "try requires an error result")
            expr.typ = expr.payload_type = self.types.payload(expr.args[0].typ)
            expr.cleanups = self.cleanup_lists()
            expr.addressable = expr.writable = expr.aggregate = False
            expr.alignment = 8
        elif expr.kind == "orelse":
            self.expr(expr.args[0], initialized)
            if not self.types.is_optional(expr.args[0].typ):
                fail("E0301", expr.token, "orelse requires an optional value")
            expr.typ = expr.payload_type = self.types.payload(expr.args[0].typ)
            right = expr.args[1]
            if right.kind == "exit":
                saved_reachable = getattr(self,"current_reachable",True)
                self.current_reachable = saved_reachable and self.known_tag(expr.args[0]) != 1
                try:
                    self.check_exit(right, initialized)
                finally:
                    self.current_reachable = saved_reachable
            else:
                self.expr(right, initialized, expr.typ)
            expr.addressable = expr.writable = expr.aggregate = False
            expr.alignment = 8
        elif expr.kind == "exit":
            fail("E0101", expr.token, "control transfer is only valid as an orelse fallback")
        else:
            if expr.kind == "call" and hasattr(expr,"method_candidates"):
                if not expr.args:
                    fail("E0301",expr.token,"method call requires an explicit receiver")
                self.expr(expr.args[0],initialized)
                matches = [method for method in expr.method_candidates if method.params[0][1] == expr.args[0].typ]
                if not matches:
                    fail("E0301",expr.token,"method receiver pointer type must match exactly")
                method = matches[0]
                if method.module != self.function.module and not method.public:
                    fail("E0201",expr.token,"method is private to its declaring module")
                expr.value = method
            # Resolve methods by the actual receiver pointer type, without
            # implicit address-taking, dereferencing or field-name rewriting.
            if expr.kind == "call" and isinstance(expr.value, Expr) and expr.value.kind == "field":
                member = expr.value
                receiver = member.args[0]
                self.expr(receiver, initialized)
                if self.types.is_pointer(receiver.typ):
                    target = self.types.pointee(receiver.typ)
                    method = getattr(self.module, "methods", {}).get((target, member.value))
                    if method is not None:
                        if method.module != self.function.module and not method.public:
                            fail("E0201", member.token, "method is private to its declaring module")
                        if receiver.typ != method.params[0][1]:
                            fail("E0301",member.token,"method receiver pointer type must match exactly")
                        expr.value, expr.args = method, [receiver] + expr.args
            result = self.base_expr(expr, initialized, expected, read=read)
            expr._l1_checked = True
            return result
        if expected is not None:
            self.coerce(expr, expected)
        expr._l1_checked = True
        return expr.typ

    def binary(self, expr):
        left, right = expr.args
        if left.typ == "noreturn" or right.typ == "noreturn":
            other = right if left.typ == "noreturn" else left
            typ = "i64" if other.typ in {"int","noreturn"} else other.typ
            for child in expr.args:
                if child.typ == "noreturn":
                    self.coerce(child,typ)
        if self.types.is_enum(left.typ) or self.types.is_enum(right.typ):
            if expr.value not in {"==", "!="} or left.typ != right.typ or self.types.is_pair(left.typ):
                fail("E0301", expr.token, "only scalar enum values of the same type may be compared")
            expr.typ = "bool"
            if left.constant is not None and right.constant is not None:
                expr.constant = left.constant == right.constant if expr.value == "==" else left.constant != right.constant
            return
        return self.base_binary(expr)

    def check_exit(self, expr, initialized):
        if getattr(self, "in_defer", False):
            fail("E0501", expr.token, "control transfer is not allowed in defer")
        if expr.value == "return":
            if self.function.returns == "noreturn":
                fail("E0402", expr.token, "noreturn functions cannot contain return")
            if not expr.args:
                if self.function.returns not in {"void", "!void"}:
                    fail("E0301", expr.token, "return requires a value")
                if self.function.returns == "!void":
                    expr.args = [self.void_success(expr.token)]
            else:
                if self.function.returns == "void":
                    fail("E0301", expr.token, "void functions require return;")
                self.expr(expr.args[0], initialized, self.function.returns)
            expr.cleanups = self.cleanup_lists()
        else:
            if not self.loops:
                fail("E0101", expr.token, "break/continue requires a loop")
            expr.cleanups = self.cleanup_lists(True)
            cleanup_stops = any(getattr(self,"defer_termination",{}).get(id(body),False) for body in expr.cleanups)
            expression_live = not getattr(self,"expression_frames",[]) or self.expression_frames[-1][1]
            if expr.value == "break" and getattr(self,"current_reachable",True) and expression_live and not cleanup_stops:
                self.loops[-1].append(set(initialized))
        expr.typ = "noreturn"

    @staticmethod
    def void_success(token):
        value = Expr(token, "pair", (0, None), [], typ="!void")
        value.aggregate, value.addressable, value.writable = True, False, False
        value._l1_checked = True
        return value

    def block(self, statements, flow, *, scoped=True):
        if not hasattr(self, "defer_frames"):
            self.defer_frames, self.loop_scopes, self.in_defer = [], [], False
        if scoped:
            self.scopes.append({})
        frame = []
        self.defer_frames.append(frame)
        original = list(statements)
        for statement in original:
            prior = flow.reachable
            saved_reachable = getattr(self,"current_reachable",True)
            self.current_reachable = flow.reachable
            try:
                result = self.statement(statement, flow)
            finally:
                self.current_reachable = saved_reachable
            flow = self.flow(result.initialized, prior and result.reachable)
        if frame:
            if any(getattr(self,"defer_termination",{}).get(id(body),False) for body in frame):
                flow.reachable = False
            statements.append(Stmt(original[-1].token if original else self.function.token,
                                   "cleanup", body=[statement for body in reversed(frame) for statement in body]))
        self.defer_frames.pop()
        if scoped:
            flow.initialized -= {variable.slot for variable in self.scopes.pop().values()}
        return flow

    def statement(self, statement, flow):
        initialized = set(flow.initialized)
        kind = statement.kind
        if kind == "local_const":
            return self.flow(initialized)
        if kind == "defer":
            if getattr(self, "in_defer", False):
                fail("E0501", statement.token, "nested defer is not allowed")
            saved = self.in_defer
            self.in_defer = True
            self.defer_captured_slots = {variable.slot for scope in self.scopes for variable in scope.values()}
            try:
                cleanup_flow = self.block(statement.body, self.flow(initialized))
            finally:
                self.in_defer = saved
            if not hasattr(self,"defer_termination"):
                self.defer_termination = {}
            self.defer_termination[id(statement.body)] = not cleanup_flow.reachable
            self.defer_frames[-1].append(statement.body)
            return self.flow(initialized)
        if kind == "return":
            exit = Expr(statement.token, "exit", "return", [statement.expr] if statement.expr is not None else [])
            self.check_exit(exit, initialized)
            statement.expr = exit.args[0] if exit.args else None
            statement.cleanups = exit.cleanups
            return self.flow(initialized, False)
        if kind in {"break", "continue"}:
            exit = Expr(statement.token, "exit", kind)
            self.check_exit(exit, initialized)
            statement.cleanups = exit.cleanups
            return self.flow(initialized, False)
        if kind in {"while", "loop", "for"}:
            if kind == "while":
                self.expr(statement.expr, initialized, "bool")
            if kind == "for":
                source = statement.expr
                if source.kind == "range":
                    saved_reachable = getattr(self,"current_reachable",True)
                    bound_live = saved_reachable
                    try:
                        for bound in source.args:
                            self.current_reachable = bound_live
                            self.expr(bound, initialized, "u64")
                            bound_live = bound_live and not self.terminates(bound)
                    finally:
                        self.current_reachable = saved_reachable
                    element, form = "u64", "range"
                else:
                    self.expr(source, initialized)
                    if not (self.types.is_array(source.typ) or self.types.is_slice(source.typ)):
                        fail("E0301", source.token, "for requires a range, array or slice")
                    element = self.types.element(source.typ)
                    form = "array" if self.types.is_array(source.typ) else "slice"
                self.scopes.append({})
                variable = self.declare(statement.value, element, False)
                statement.variable, statement.element_type, statement.for_kind = variable, element, form
                initialized.add(variable.slot)
            breaks = []
            self.loops.append(breaks)
            self.loop_scopes.append(len(self.defer_frames))
            self.block(statement.body, self.flow(initialized, flow.reachable and not (kind == "while" and statement.expr.constant is False)))
            self.loop_scopes.pop()
            self.loops.pop()
            if kind == "for":
                initialized -= {var.slot for var in self.scopes.pop().values()}
            if kind != "loop" and self.terminates(statement.expr):
                return self.flow(initialized,False)
            infinite = kind == "loop" or kind == "while" and statement.expr.constant is True
            if infinite:
                return self.flow(set.intersection(*breaks) if breaks else initialized, bool(breaks))
            return self.flow(initialized)
        if kind == "if":
            result = self.base_statement(statement,flow)
            if self.terminates(statement.expr):
                result.reachable = False
            return result
        if kind == "match":
            return self.match_statement(statement, flow)
        if kind == "call":
            self.expr(statement.expr, initialized)
            self.materialize(statement.expr)
            if self.types.is_result(statement.expr.typ):
                fail("E0301", statement.token, "error results cannot be discarded; use try or match")
            return self.flow(initialized, not self.terminates(statement.expr))
        if kind == "cleanup":
            return self.flow(initialized)
        result = self.base_statement(statement, flow)
        if statement.expr is not None and self.terminates(statement.expr):
            result.reachable = False
        return result

    def match_statement(self, statement, flow):
        self.expr(statement.expr, flow.initialized)
        typ = statement.expr.typ
        optional, result = self.types.is_optional(typ), self.types.is_result(typ)
        enum = self.types.enums.get(typ)
        known = self.known_tag(statement.expr)
        if result and known is not None:
            known = int(known != 0)
        if typ == "bool" or optional or result:
            possibilities = {0, 1}
        elif enum is not None:
            possibilities = set(range(len(enum.variants)))
        else:
            fail("E0301", statement.expr.token, "match requires bool, enum, optional or error result")
        seen, flows, wildcard = set(), [], False
        for arm in statement.value:
            pattern = arm.pattern
            child, source = None, "payload"
            if wildcard:
                fail("E0403", pattern.token, "unreachable match arm after wildcard")
            if pattern.kind == "wildcard":
                if seen == possibilities:
                    fail("E0403", pattern.token, "unreachable wildcard after exhaustive patterns")
                wildcard, key, tag = True, None, None
            elif typ == "bool" and pattern.kind == "bool":
                key = tag = int(pattern.value)
            elif optional and pattern.kind in {"null", "some"}:
                key = tag = int(pattern.kind == "some")
                child = self.types.payload(typ) if key else None
            elif result and pattern.kind in {"ok", "err"}:
                key = int(pattern.kind == "err")
                tag = 0 if not key else "nonzero"
                child = "u64" if key else self.types.payload(typ)
                source = "tag" if key else "payload"
                if child == "void":
                    child = None
            elif enum is not None and pattern.kind == "enum":
                owner, _, name = pattern.value.rpartition(".")
                if owner != typ:
                    fail("E0301", pattern.token, "pattern belongs to a different enum")
                found = [(i, payload) for i, (variant, payload) in enumerate(enum.variants) if variant.value == name]
                if not found:
                    fail("E0201", pattern.token, "unknown enum variant")
                key, child = found[0]
                tag = key
            else:
                fail("E0301", pattern.token, "pattern does not match the subject type")
            if key is not None:
                if key in seen:
                    fail("E0403", pattern.token, "duplicate match pattern")
                seen.add(key)
            binding = pattern.binding
            if child is None and binding is not None:
                fail("E0301", pattern.token, "this pattern has no payload")
            if child is not None and binding is None:
                fail("E0301", pattern.token, "this pattern requires a payload binding")
            self.scopes.append({})
            initialized = set(flow.initialized)
            arm.binding = None
            if binding is not None and binding.value != "_":
                arm.binding = self.declare(binding, child, False)
                initialized.add(arm.binding.slot)
            arm.tag_value, arm.payload_type, arm.binding_source = tag, child, source
            branch_live = flow.reachable and not self.terminates(statement.expr) and (known is None or key == known or key is None and known not in seen)
            branch = self.block(arm.body, self.flow(initialized, branch_live))
            branch.initialized -= {var.slot for var in self.scopes.pop().values()}
            if branch.reachable:
                flows.append(branch.initialized)
        if not wildcard and seen != possibilities:
            fail("E0403", statement.token, "match is not exhaustive")
        return self.flow(set.intersection(*flows) if flows else flow.initialized, bool(flows))
