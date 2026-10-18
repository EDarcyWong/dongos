"""Names and static data for L1 nominal types, errors and lexical constants."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import replace
from .model import *


class L1DeclarationsMixin:
    def extract_methods(self, units):
        self.raw_methods = []
        for owner, unit in units.items():
            self.raw_methods.extend((owner, item) for item in unit.functions if item.receiver is not None)
            unit.functions = [item for item in unit.functions if item.receiver is None]

    def setup_l1(self):
        self.enums, self.errors, self.by_enum = {}, {}, {}
        self.error_values, self.error_codes, self.methods = {}, {}, {}
        self.local_constants, self.local_const_count = {}, 0
        for owner, unit in self.units.items():
            namespace = {item.alias: item for item in unit.imports}
            for table in [self.functions, self.structures, self.aliases, self.constants, self.globals]:
                namespace.update(table[owner])
            for attribute, tables in [('enums', self.enums), ('errors', self.errors)]:
                tables[owner] = {}
                for declaration in getattr(unit, attribute):
                    name = declaration.token.value
                    if name in namespace:
                        fail('E0201', declaration.token, f'duplicate declaration {name!r}', namespace[name].token)
                    if name in INTEGER | {'bool','void','noreturn','usize','isize'}:
                        fail('E0201', declaration.token, f'cannot redefine built-in name {name!r}')
                    namespace[name] = declaration
                    declaration.module, declaration.local_name = owner, name
                    declaration.token = replace(declaration.token, value=self.symbol(owner,name))
                    tables[owner][name] = declaration
                    if attribute == 'enums':
                        self.by_enum[declaration.token.value] = declaration
        self.module.enums = list(self.by_enum.values())
        self.module.errors = [item for table in self.errors.values() for item in table.values()]
        self.module.methods = self.methods

    def type_name(self, typ, owner, token, locals_=frozenset()):
        if typ.startswith(('?','!')):
            return typ[0] + self.type_name(typ[1:], owner, token, locals_)
        if typ == 'noreturn' or typ in self.by_enum or typ in self.by_struct:
            return typ
        if typ in self.enums[owner] or '.' in typ and typ.partition('.')[0] in self.imports[owner] and typ.partition('.')[2] in self.enums[self.imports[owner][typ.partition('.')[0]]]:
            target, local, declaration = self.declaration(typ, owner, self.enums, token, 'enum')
            return self.symbol(target, local)
        return self.base_type_name(typ, owner, token, locals_)

    def layout_type(self, typ, owner, token, locals_=frozenset()):
        if typ.startswith(('?','!')):
            # The storage shape is fixed; validate payload references after
            # lazy dimensions and declaration dependencies have settled.
            return typ
        if typ == 'noreturn' or typ in self.by_enum:
            return typ
        if typ in self.enums[owner] or '.' in typ and typ.partition('.')[0] in self.imports[owner] and typ.partition('.')[2] in self.enums[self.imports[owner][typ.partition('.')[0]]]:
            return self.type_name(typ, owner, token, locals_)
        return self.base_layout_type(typ, owner, token, locals_)

    def error_code(self, owner, local):
        key = owner, local
        if key not in self.error_values:
            declaration = self.errors[owner][local]
            with self.dependency(('error',owner,local), declaration.token):
                code = self.integer(declaration.code, owner, 'error code') if isinstance(declaration.code,Expr) else declaration.code
                if not 1 <= code <= 0xffffffff:
                    fail('E0302',declaration.token,'error code must be in 1..4294967295')
                if code in self.error_codes:
                    fail('E0602',declaration.token,f'duplicate error code {code}',self.error_codes[code])
                self.error_codes[code] = declaration.token
                declaration.code = self.error_values[key] = code
        return self.error_values[key]

    def setup_methods(self):
        for owner,function in self.raw_methods:
            name = function.token.value
            token, raw_type = function.receiver
            receiver = self.type_name(raw_type,owner,token)
            if not self.types.is_pointer(receiver):
                fail('E0301',token,'method receiver must be a raw pointer to a nominal type')
            target = self.types.pointee(receiver)
            declaration = self.by_struct.get(target) or self.by_enum.get(target)
            if declaration is None or declaration.module != owner:
                fail('E0201',token,'methods must be declared in their receiver type module')
            if (target,name) in self.methods:
                fail('E0201',function.token,f'duplicate method {name!r}',self.methods[target,name].token)
            if target in self.by_struct and any(item.value == name for item,_ in declaration.fields):
                fail('E0201',function.token,f'method conflicts with field {name!r}')
            local = declaration.local_name+'.'+name
            function.module,function.local_name = owner,local
            function.token = replace(function.token,value=self.symbol(owner,local))
            function.receiver = token,receiver
            function.params[0] = token,receiver
            function.method_name,function.method_type = name,target
            self.functions[owner][local] = function
            self.methods[target,name] = function

    def prepare_function(self,function):
        result = self.base_prepare_function(function)
        if hasattr(function,'method_type') and not function.export:
            declaration = self.by_struct.get(function.method_type) or self.by_enum[function.method_type]
            function.symbol = (f'__dg_m{function.module.encode("utf-8").hex()}_t{declaration.local_name.encode("utf-8").hex()}'
                               f'_f{function.method_name.encode("utf-8").hex()}')
        return result

    def variant(self,expr,owner,locals_):
        parts = self.member(expr)
        if not parts or len(parts) < 2 or parts[0] in locals_:
            return None
        raw = '.'.join(parts[:-1])
        # Only a known type namespace can form an enum constructor. Ordinary
        # object member expressions keep their receiver evaluation untouched.
        first = raw.partition('.')[0]
        if first not in self.enums[owner] and first not in self.aliases[owner] and first not in self.imports[owner]:
            return None
        if first in self.imports[owner]:
            target = self.imports[owner][first]
            if len(parts) != 3 or parts[1] not in dict(self.enums[target],**self.aliases[target]):
                return None
        typ = self.type_name(raw,owner,expr.token,locals_)
        declaration = self.by_enum.get(typ)
        if declaration is None:
            return None
        name = parts[-1]
        for tag,(token,payload) in enumerate(declaration.variants):
            if token.value == name:
                return typ,tag,payload
        fail('E0201',expr.token,f'unknown enum variant {name!r}')

    def expression(self,expr,owner,locals_,*,constant=False,place=False):
        if expr is None:
            return
        if expr.kind == 'name' and isinstance(expr.value,str) and expr.value in locals_ and self.local_constants.get(expr.value) is not None:
            declaration = self.local_constants[expr.value]
            if not place and declaration.typ in INTEGER | {'bool'}:
                expr.kind,expr.value,expr.args = 'constant',(declaration.typ,self.scalar(declaration.initializer)),[]
            else:
                expr.kind,expr.value,expr.args = 'global',declaration,[]
            return
        if expr.kind == 'error':
            target,local,declaration = self.declaration(expr.value,owner,self.errors,expr.token,'error')
            if declaration is None:
                fail('E0201',expr.token,f'unknown error {expr.value!r}')
            expr.value = self.error_code(target,local)
            return
        if expr.kind == 'field':
            constructor = self.variant(expr,owner,locals_)
            if constructor is not None:
                expr.kind,expr.value,expr.args = 'enum_constructor',constructor,[]
                return
        if expr.kind == 'call':
            target,name = owner,expr.value if isinstance(expr.value,str) else None
            if isinstance(expr.value,Expr):
                parts = self.member(expr.value)
                if parts and len(parts) == 2 and parts[0] in self.imports[owner] and parts[0] not in locals_:
                    target,name = self.imports[owner][parts[0]],parts[1]
            occupied = name in self.functions[target] or name in self.constants[target] or name in self.globals[target]
            if name is not None and name not in locals_ and not occupied and name not in INTRINSICS | {'slice_from_raw_parts'}:
                candidates = [method for method in self.methods.values() if method.module == target and method.method_name == name]
                if candidates:
                    if constant:
                        fail('E0601',expr.token,'runtime calls are not allowed in constant expressions')
                    expr.method_candidates = candidates
                    for arg in expr.args:
                        self.expression(arg,owner,locals_)
                    return
        if expr.kind == 'call' and isinstance(expr.value,str) and expr.value not in locals_ and expr.value in dict(self.enums[owner],**self.errors[owner]):
            fail('E0601',expr.token,'types and error declarations cannot be called')
        if expr.kind == 'call' and isinstance(expr.value,Expr):
            constructor = self.variant(expr.value,owner,locals_)
            if constructor is not None:
                expr.kind,expr.value = 'enum_constructor',constructor
                for arg in expr.args:
                    self.expression(arg,owner,locals_,constant=constant)
                return
        if expr.kind in {'pair','enum_constructor'}:
            for arg in expr.args:
                self.expression(arg,owner,locals_,constant=constant)
            return
        if expr.kind in {'try','orelse','exit','range'}:
            if constant and expr.kind == 'try':
                fail('E0501',expr.token,'try is not allowed in a compile-time initializer')
            if constant and expr.kind != 'orelse':
                fail('E0601',expr.token,'control transfer is not a constant expression')
            for arg in expr.args:
                self.expression(arg,owner,locals_,constant=constant)
            return
        return self.base_expression(expr,owner,locals_,constant=constant,place=place)

    def local_constant(self,statement,owner,locals_):
        token,raw_type = statement.value
        typ = self.type_name(raw_type,owner,token,locals_) if raw_type is not None else None
        value = deepcopy(statement.expr)
        self.expression(value,owner,locals_,constant=True)
        checker = self.checker(owner)
        checker.expr(value,set(),typ)
        checker.materialize(value)
        self.validate_reads(value)
        typ = value.typ
        layout = self.types.layout(typ,token)
        self.check_size(layout.size,token)
        data = self.static_value(value,owner)
        self.local_const_count += 1
        symbol = f'__dg_m{owner.encode("utf-8").hex()}_lc{self.local_const_count}'
        declaration = ConstDecl(token,typ,value,module=owner,local_name=token.value,symbol=symbol,initializer=data)
        self.add_object(StaticObject(symbol,typ,data.data,layout.alignment,False,list(data.relocations)),token)
        return declaration

    def block(self,statements,owner,outer,*,top=False):
        saved = self.local_constants
        self.local_constants = dict(saved)
        locals_,declared = set(outer),set(outer) if top else set()
        try:
            for statement in statements:
                if statement.kind == 'binding':
                    token,typ = statement.value
                    if token.value in declared:
                        fail('E0201',token,f'duplicate binding {token.value!r}')
                    if statement.token.kind == 'const':
                        declaration = self.local_constant(statement,owner,locals_)
                        self.local_constants[token.value] = declaration
                        statement.kind,statement.expr = 'local_const',None
                    else:
                        if typ is not None:
                            statement.value = token,self.type_name(typ,owner,token,locals_)
                        self.expression(statement.expr,owner,locals_)
                        self.local_constants[token.value] = None
                    locals_.add(token.value)
                    declared.add(token.value)
                    continue
                if statement.kind == 'assign':
                    target = statement.value[0]
                    self.expression(target,owner,locals_)
                    if target.kind == 'constant' or target.kind == 'global' and not getattr(target.value,'mutable',False):
                        fail('E0402',target.token,'cannot assign a compile-time constant')
                self.expression(statement.expr,owner,locals_)
                if statement.kind == 'for':
                    inner = locals_ | {statement.value.value}
                    old = self.local_constants.get(statement.value.value)
                    self.local_constants[statement.value.value] = None
                    self.block(statement.body,owner,inner)
                    self.local_constants[statement.value.value] = old
                elif statement.kind == 'match':
                    for arm in statement.value:
                        pattern = arm.pattern
                        if pattern.kind == 'enum':
                            prefix,_,name = pattern.value.rpartition('.')
                            pattern.value = self.type_name(prefix,owner,pattern.token,locals_)+'.'+name
                        inner = set(locals_)
                        if pattern.binding is not None:
                            inner.add(pattern.binding.value)
                        old_constants = self.local_constants
                        self.local_constants = dict(old_constants)
                        if pattern.binding is not None:
                            self.local_constants[pattern.binding.value] = None
                        self.block(arm.body,owner,inner)
                        self.local_constants = old_constants
                else:
                    self.block(statement.body,owner,locals_)
                    self.block(statement.otherwise or [],owner,locals_)
        finally:
            self.local_constants = saved

    def static_value(self,expr,owner):
        if expr.kind == 'pair':
            tag,child = expr.value
            contents,relocations = bytearray(16),[]
            contents[:8] = tag.to_bytes(8,'little')
            if child is not None:
                value = self.static_value(expr.args[0],owner)
                contents[8:8+len(value.data)] = value.data
                relocations = [StaticRelocation(item.offset+8,item.symbol,item.addend) for item in value.relocations]
            return StaticData(expr.typ,bytes(contents),relocations)
        if expr.kind == 'orelse':
            data = self.static_value(expr.args[0],owner)
            return self.segment(data,8,expr.typ,expr.token) if int.from_bytes(data.data[:8],'little') else self.static_value(expr.args[1],owner)
        return self.base_static_value(expr,owner)

    def public_type(self,typ,token):
        for prefix in ('*const ','*','[]const ','[]'):
            if typ.startswith(prefix):
                return self.public_type(typ[len(prefix):],token)
        if self.types.is_array(typ):
            return self.public_type(self.types.element(typ),token)
        if typ.startswith(('?','!')):
            return self.public_type(typ[1:],token)
        if typ in self.by_enum:
            if not self.by_enum[typ].public:
                fail('E0201',token,f'public signature exposes private type {typ!r}')
            return
        return self.base_public_type(typ,token)

    def resolve(self):
        for declaration in self.by_enum.values():
            declaration.variants = [(token,self.type_name(typ,declaration.module,token) if typ is not None else None)
                                    for token,typ in declaration.variants]
        for declaration in self.by_enum.values():
            if declaration.public:
                for token,typ in declaration.variants:
                    if typ is not None:
                        self.public_type(typ,token)
        self.setup_methods()
        for owner,table in self.errors.items():
            for local in table:
                self.error_code(owner,local)
        result = self.base_resolve()
        result.enums,result.errors,result.methods = self.module.enums,self.module.errors,self.methods
        return result
