"""Independent, bounded static AML fixture inspector; no AML evaluation or I/O."""
from pathlib import Path
import hashlib
import json
import struct
import sys


class StaticAml:
    def __init__(self, raw):
        if len(raw) < 36 or len(raw) > 1048576 or raw[:4] not in (b'DSDT', b'SSDT'):
            raise ValueError('invalid AML table identity/length')
        if struct.unpack_from('<I', raw, 4)[0] != len(raw) or sum(raw) & 255:
            raise ValueError('invalid AML table checksum/declared length')
        self.raw, self.trace, self.candidate = raw, [], None
        self.steps = 0

    def step(self):
        self.steps += 1
        if self.steps > 65536:
            raise ValueError('static AML object budget exhausted')

    def fail(self, at, description):
        raise ValueError(f'{description} at 0x{at:x}')

    def length(self, at, end):
        if at >= end:
            self.fail(at, 'truncated PkgLength')
        lead = self.raw[at]
        count = lead >> 6
        if at + 1 + count > end or count and lead & 0x30:
            self.fail(at, 'invalid PkgLength')
        value = lead & (15 if count else 63)
        for i in range(count):
            value |= self.raw[at+1+i] << (4+8*i)
        return value, at+1+count

    def package(self, at, end):
        length, payload = self.length(at, end)
        if payload > at+length or at+length > end:
            self.fail(at, 'invalid package extent')
        return payload, at+length

    def name(self, at, end, scope):
        raw = self.raw
        if at >= end:
            self.fail(at, 'truncated NameString')
        if raw[at] == 92:
            scope, at = (), at+1
        else:
            while at < end and raw[at] == 94:
                if not scope:
                    self.fail(at, 'parent prefix above root')
                scope, at = scope[:-1], at+1
        if at >= end:
            self.fail(at, 'truncated NamePath')
        count = 1
        if raw[at] == 0:
            count, at = 0, at+1
        elif raw[at] == 46:
            count, at = 2, at+1
        elif raw[at] == 47:
            if at+1 >= end:
                self.fail(at, 'truncated MultiName')
            count, at = raw[at+1], at+2
            if not count:
                self.fail(at, 'empty MultiName')
        if count > 16 or len(scope)+count > 16 or at+count*4 > end:
            self.fail(at, 'unsupported NameString extent')
        result = []
        for i in range(count):
            segment = raw[at+i*4:at+(i+1)*4]
            if not self.segment(segment):
                self.fail(at+i*4, 'invalid NameSeg')
            result.append(segment.decode('ascii'))
        return at+count*4, scope+tuple(result), count

    @staticmethod
    def segment(value):
        return len(value) == 4 and (value[0] == 95 or 65 <= value[0] <= 90) and all(
            x == 95 or 65 <= x <= 90 or 48 <= x <= 57 for x in value[1:])

    def integer(self, at, end):
        if at >= end:
            self.fail(at, 'truncated integer')
        op = self.raw[at]
        if op in (0, 1, 255):
            return at+1, (0xffffffffffffffff if op == 255 else op)
        size = {10: 1, 11: 2, 12: 4, 14: 8}.get(op)
        if size is None:
            self.fail(at, 'dynamic/nonliteral integer unsupported')
        if at+1+size > end:
            self.fail(at, 'truncated integer payload')
        return at+1+size, int.from_bytes(self.raw[at+1:at+1+size], 'little')

    def data(self, at, end, scope, level=0, element=False):
        self.step()
        if at >= end or level > 16:
            self.fail(at, 'data extent/depth')
        op = self.raw[at]
        if op == 13:
            stop = at+1
            while stop < end and self.raw[stop]:
                if self.raw[stop] > 127:
                    self.fail(stop, 'non-ASCII string')
                stop += 1
            if stop == end:
                self.fail(at, 'unterminated string')
            return stop+1, ('string', self.raw[at+1:stop].decode('ascii'))
        if op == 17:
            payload, stop = self.package(at+1, end)
            first, size = self.integer(payload, stop)
            if size > 65536 or size < stop-first:
                self.fail(at, 'unsupported Buffer size')
            return stop, ('buffer', self.raw[first:stop].hex())
        if op == 18:
            first, stop = self.package(at+1, end)
            if first == stop:
                self.fail(at, 'missing package count')
            count, first = self.raw[first], first+1
            values = []
            for _ in range(count):
                first, value = self.data(first, stop, scope, level+1, True)
                values.append(value)
            if first != stop:
                self.fail(at, 'package element count/extent mismatch')
            return stop, ('package', values)
        if element and (op in (92, 94, 46, 47) or op == 95 or 65 <= op <= 90):
            stop, path, count = self.name(at, end, scope)
            if not count:
                self.fail(at, 'empty package name reference')
            return stop, ('reference', path)
        stop, value = self.integer(at, end)
        return stop, ('integer', value)

    def named(self, at, end, scope):
        stop, target, count = self.name(at, end, scope)
        if not count or target == ('_S5_',):
            self.fail(at, 'non-package named object occupies root S5')
        return stop, target

    def field(self, at, end, scope, code):
        first, stop = self.package(at+2, end)
        first, _, count = self.name(first, stop, scope)
        if not count:
            self.fail(first, 'empty Field region')
        if code in (134, 135):
            first, _, count = self.name(first, stop, scope)
            if not count:
                self.fail(first, 'empty field index/bank')
        if code == 135:
            first, _ = self.integer(first, stop)
        if first >= stop or self.raw[first] & 128 or self.raw[first] & 15 > 5 or (self.raw[first] >> 5) & 3 > 2:
            self.fail(first, 'invalid field flags')
        first += 1
        while first < stop:
            self.step()
            op = self.raw[first]
            if op == 0:
                _, first = self.length(first+1, stop)
            elif op in (1, 3):
                size = 3 if op == 1 else 4
                if first+size > stop or self.raw[first+1] > 5:
                    self.fail(first, 'invalid access field')
                first += size
            elif op == 2:
                if first+1 >= stop:
                    self.fail(first, 'truncated connect field')
                if self.raw[first+1] == 17:
                    first, _ = self.data(first+1, stop, scope)
                else:
                    first, _, count = self.name(first+1, stop, scope)
                    if not count:
                        self.fail(first, 'empty connect reference')
            else:
                segment = self.raw[first:first+4]
                if not self.segment(segment) or first+4 > stop:
                    self.fail(first, 'invalid NamedField')
                if not scope and segment == b'_S5_':
                    self.fail(first, 'Field defines root S5')
                _, first = self.length(first+4, stop)
        return stop

    def walk(self, at, end, scope=(), nesting=0):
        if nesting > 16:
            self.fail(at, 'namespace depth')
        while at < end:
            self.step()
            start, op, target = at, self.raw[at], scope
            if op == 8:
                first, target, count = self.name(at+1, end, scope)
                if not count:
                    self.fail(at, 'empty Name target')
                at, value = self.data(first, end, scope)
                kind = 'Name'
                if target == ('_S5_',):
                    if self.candidate is not None:
                        self.fail(start, 'duplicate static root S5')
                    if value[0] != 'package' or not 2 <= len(value[1]) <= 32 or any(v[0] != 'integer' for v in value[1]) or any(v[1] > 7 for v in value[1][:2]):
                        self.fail(start, 'root S5 is not an integer-only sleep package')
                    self.candidate = dict(type_a=value[1][0][1], type_b=value[1][1][1], aml_offset=start)
            elif op in (16, 20) or op == 91 and at+1 < end and self.raw[at+1] in (130, 131, 132, 133):
                ext = self.raw[at+1] if op == 91 else op
                first, stop = self.package(at+(2 if op == 91 else 1), end)
                if op == 16:
                    first, target, _ = self.name(first, stop, scope)
                else:
                    first, target = self.named(first, stop, scope)
                if target == ('_S5_',):
                    self.fail(start, 'namespace object occupies root S5')
                if op == 20:
                    if first >= stop:
                        self.fail(first, 'missing method flags')
                    kind = 'Method'
                else:
                    first += 6 if ext == 131 else 3 if ext == 132 else 0
                    if first > stop:
                        self.fail(start, 'truncated named scope header')
                    kind = {16: 'Scope', 130: 'Device', 131: 'Processor', 132: 'PowerResource', 133: 'ThermalZone'}[ext]
                    self.trace.append(dict(offset=start, end=stop, kind=kind, path=target))
                    self.walk(first, stop, target, nesting+1)
                    at = stop
                    continue
                at = stop
            elif op == 91 and at+1 < end:
                ext = self.raw[at+1]
                kind = f'Ext{ext:02x}'
                if ext == 128:
                    first, target = self.named(at+2, end, scope)
                    if first >= end or self.raw[first] > 10 and self.raw[first] < 128:
                        self.fail(first, 'invalid OperationRegion address space')
                    first, _ = self.integer(first+1, end)
                    at, _ = self.integer(first, end)
                elif ext in (129, 134, 135):
                    at = self.field(at, end, scope, ext)
                elif ext in (1, 2):
                    at, target = self.named(at+2, end, scope)
                    if ext == 1:
                        if at >= end or self.raw[at] & 240:
                            self.fail(at, 'invalid Mutex flags')
                        at += 1
                else:
                    self.fail(at, f'unsupported module ext opcode {ext:02x}')
            elif op == 163:
                at, kind = at+1, 'NoOp'
            else:
                self.fail(at, f'unsupported module opcode {op:02x}')
            self.trace.append(dict(offset=start, end=at, kind=kind, path=target))
        if at != end:
            self.fail(at, 'TermList extent')

    def parse(self):
        self.walk(36, len(self.raw))
        if self.candidate is None:
            raise ValueError('missing static root S5')
        return dict(s5=self.candidate, module_terms=len(self.trace), bounded_objects=self.steps,
                    source_sha256=hashlib.sha256(self.raw).hexdigest(), trace=self.trace)


if __name__ == '__main__':
    value = StaticAml(Path(sys.argv[1]).read_bytes()).parse()
    print(json.dumps(value, indent=2))
