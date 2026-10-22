"""Native assembler symbol escaping, linked ELF bytes and actual host execution."""
from __future__ import annotations
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest
import uuid

from lang.dongc import compile_file
from lang.tests.test_dongc import tool, nasm_flags

ROOT = Path(__file__).resolve().parents[2]
U = C.c_uint64


class Slice(C.Structure):
    _fields_ = [('p', C.c_void_p), ('n', U)]


class Workspace(C.Structure):
    _fields_ = [(name, Slice) for name in ('labels', 'table', 'text', 'data')]


class Result(C.Structure):
    _fields_ = [(name, U) for name in ('status', 'line', 'detail', 'text', 'data', 'labels', 'written')]


WRAPPER = '''module probe;
import bootstrap.native_assembler as a;
export("native_assemble") pub unsafe fn f(src:*const u8,n:usize,entry:*const u8,en:usize,w:*const a.Workspace,out:*u8,cap:usize,r:*a.Result)u64{unsafe{
 return a.assemble(slice_from_raw_parts(src,n),slice_from_raw_parts(entry,en),w,slice_from_raw_parts(out,cap),r);
}}
'''
SHIM = '''#include <stdint.h>
#include <stdlib.h>
typedef uint64_t U;
extern U __attribute__((sysv_abi)) native_assemble(const void*,U,const void*,U,const void*,void*,U,void*);
void __attribute__((sysv_abi)) __dong_panic(uint32_t k,uint32_t l,const void*p,U n){(void)k;(void)l;(void)p;(void)n;abort();}
U bridge_assemble(const void*s,U n,const void*e,U en,const void*w,void*out,U cap,void*r){return native_assemble(s,n,e,en,w,out,cap,r);}
'''
PROGRAM = '''bits 64
default rel
section .text
global $_start
$_start:
call $rax
add rax, 35
ret
$rax:
mov rax, 7
ret
section .data
$pointer: dq $rax
'''


class EscapedSymbolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not cls.nasm or not cls.cc:
            raise RuntimeError('NASM and GCC are required')
        cls.work = ROOT / 'build/test/l3-escaped-symbols' / ('run-' + uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        cls.hashes, cls.records, cls.libs = {}, [], {}
        snapshot = cls.work / 'snapshot'
        (snapshot / 'bootstrap').mkdir(parents=True)
        for name in ('native_assembler', 'x86_encode', 'elf64_image'):
            path = ROOT / 'lang/bootstrap' / (name + '.dg')
            data = path.read_bytes()
            cls.hashes[str(path)] = hashlib.sha256(data).hexdigest()
            (snapshot / 'bootstrap' / path.name).write_bytes(data)
        (snapshot / 'probe.dg').write_text(WRAPPER)
        shim = cls.work / 'bridge.c'
        shim.write_text(SHIM)
        for mode in ('debug', 'release'):
            asm = cls.work / (mode + '.asm')
            asm.write_text(compile_file(snapshot / 'probe.dg', roots=[snapshot], mode=mode).assembly)
            for fmt in ('elf64', 'win64'):
                cls.command([cls.nasm, '-O0', '-f', fmt, *nasm_flags(cls.nasm), asm, '-o', cls.work / (mode + '-' + fmt + '.o')])
            fmt = 'win64' if os.name == 'nt' else 'elf64'
            lib = cls.work / (mode + ('.dll' if os.name == 'nt' else '.so'))
            cls.command([cls.cc, '-shared', '-O2', '-Wall', '-Wextra', '-Werror', *(['-Wl,--export-all-symbols'] if os.name == 'nt' else ['-fPIC']), shim, cls.work / (mode + '-' + fmt + '.o'), '-o', lib])
            dll = C.CDLL(str(lib))
            fn = dll.bridge_assemble
            fn.argtypes = [C.c_void_p, U, C.c_void_p, U, C.POINTER(Workspace), C.c_void_p, U, C.POINTER(Result)]
            fn.restype = U
            cls.libs[mode] = dll, fn

    @classmethod
    def command(cls, command):
        p = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=600)
        cls.records.append(dict(command=list(map(str, command)), returncode=p.returncode, stdout=p.stdout, stderr=p.stderr))
        if p.returncode:
            raise AssertionError(p.stderr)
        return p

    @classmethod
    def tearDownClass(cls):
        after = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in cls.hashes}
        (cls.work / 'summary.json').write_text(json.dumps(dict(before=cls.hashes, after=after, source_stable=after == cls.hashes, records=cls.records), indent=2))
        if after != cls.hashes:
            raise AssertionError('assembler sources changed during test')

    def assemble(self, mode, source, entry='_start', capacity=131072):
        raw, entry_raw = source.encode(), entry.encode()
        src, ent = C.create_string_buffer(raw), C.create_string_buffer(entry_raw)
        sizes = [128 * 32, 257 * 8, 65536, 65536, 131072]
        pools = [(U * ((n + 32) // 8))() for n in sizes]
        for pool, n in zip(pools, sizes):
            C.memset(C.addressof(pool), 0xa5, n + 32)
        addresses = [C.addressof(p) + 16 for p in pools]
        workspace = Workspace(*[Slice(p, n) for p, n in zip(addresses, (128, 257, 65536, 65536))])
        result = Result()
        status = self.libs[mode][1](src, len(raw), ent, len(entry_raw), C.byref(workspace), addresses[4], capacity, C.byref(result))
        self.assertEqual(status, result.status)
        self.assertEqual(bytes(src)[:len(raw)], raw)
        self.assertEqual(bytes(ent)[:len(entry_raw)], entry_raw)
        for p, n in zip(pools, sizes):
            self.assertEqual(C.string_at(C.addressof(p), 16), b'\xa5' * 16)
            self.assertEqual(C.string_at(C.addressof(p) + 16 + n, 16), b'\xa5' * 16)
        used = result.written if status == 0 else 0
        self.assertEqual(C.string_at(addresses[4] + used, sizes[4] - used), b'\xa5' * (sizes[4] - used))
        self.records.append(dict(mode=mode, source=source, entry=entry, status=status, detail=result.detail, capacity=capacity))
        return status, C.string_at(addresses[4], used), result

    @staticmethod
    def headers(image):
        entry, phoff = struct.unpack_from('<QQ', image, 24)
        phentsize, phnum = struct.unpack_from('<HH', image, 54)
        return entry, [struct.unpack_from('<IIQQQQQQ', image, phoff + phentsize * i) for i in range(phnum)]

    def execute(self, image):
        entry, headers = self.headers(image)
        loads = [h for h in headers if h[0] == 1 and h[6]]
        base = min(h[3] & ~4095 for h in loads)
        size = max((h[3] + h[6] + 4095) & ~4095 for h in loads) - base
        if os.name == 'nt':
            api = C.WinDLL('kernel32', use_last_error=True)
            api.VirtualAlloc.argtypes = [C.c_void_p, C.c_size_t, U, U]
            api.VirtualAlloc.restype = C.c_void_p
            api.VirtualFree.argtypes = [C.c_void_p, C.c_size_t, U]
            api.VirtualProtect.argtypes = [C.c_void_p, C.c_size_t, U, C.POINTER(C.c_ulong)]
            api.FlushInstructionCache.argtypes = [C.c_void_p, C.c_void_p, C.c_size_t]
            mapped = api.VirtualAlloc(base, size, 0x3000, 4)
            self.assertEqual(mapped, base)
            def protect(address, length, executable):
                old = C.c_ulong()
                self.assertTrue(api.VirtualProtect(address, length, 0x20 if executable else 4, C.byref(old)))
            def release():
                self.assertTrue(api.VirtualFree(base, 0, 0x8000))
        else:
            api = C.CDLL(None, use_errno=True)
            api.mmap.argtypes = [C.c_void_p, C.c_size_t, C.c_int, C.c_int, C.c_int, C.c_long]
            api.mmap.restype = C.c_void_p
            api.mprotect.argtypes = [C.c_void_p, C.c_size_t, C.c_int]
            api.munmap.argtypes = [C.c_void_p, C.c_size_t]
            mapped = api.mmap(base, size, 3, 0x100022, -1, 0)
            self.assertEqual(mapped, base)
            def protect(address, length, executable):
                self.assertEqual(api.mprotect(address, length, 5 if executable else 3), 0)
            def release():
                self.assertEqual(api.munmap(base, size), 0)
        try:
            for h in loads:
                C.memmove(h[3], image[h[2]:h[2] + h[5]], h[5])
                protect(h[3], (h[6] + 4095) & ~4095, bool(h[1] & 1))
            if os.name == 'nt':
                self.assertTrue(api.FlushInstructionCache(C.c_void_p(-1), base, size))
            return C.CFUNCTYPE(U)(entry)()
        finally:
            release()

    def test_escaped_labels_calls_relocations_and_real_execution(self):
        images = []
        for mode in self.libs:
            status, image, result = self.assemble(mode, PROGRAM)
            self.assertEqual(status, 0, (result.line, result.detail))
            self.assertEqual(self.execute(image), 42)
            _, headers = self.headers(image)
            data = [h for h in headers if h[0] == 1 and h[1] & 2][0]
            text = [h for h in headers if h[0] == 1 and h[1] & 1][0]
            ptr = struct.unpack_from('<Q', image, data[2])[0]
            code = image[text[2]:text[2] + text[5]]
            self.assertEqual(ptr, text[3] + code.index(b'\x48\xb8' + struct.pack('<Q', 7) + b'\xc3'))
            images.append(image)
            self.records.append(dict(mode=mode, executed_return=42, pointer=ptr, elf_sha256=hashlib.sha256(image).hexdigest()))
        self.assertEqual(images[0], images[1])

    def test_plain_and_escaped_spellings_share_identity_and_rip_references(self):
        source = PROGRAM.replace('global $_start', 'global _start').replace('$_start:', '_start:').replace('call $rax', 'call helper').replace('$rax:', '$helper:').replace('dq $rax', 'dq helper')
        source = source.replace('mov rax, 7', 'lea rcx, [rel $helper]\nlea rax, [rel $pointer]\nmov rax, qword [rax]\nsub rax, rcx\nadd rax, 7')
        for mode in self.libs:
            status, image, result = self.assemble(mode, source)
            self.assertEqual(status, 0, (result.line, result.detail))
            self.assertEqual(self.execute(image), 42)

    def test_duplicate_undefined_and_malformed_escapes_fail_atomically(self):
        for mode in self.libs:
            for body in (PROGRAM + 'pointer: dq 0\n', PROGRAM.replace('call $rax', 'call $missing'), PROGRAM.replace('global $_start', 'global $'), PROGRAM.replace('$rax:', '$$rax:')):
                status, image, result = self.assemble(mode, body)
                self.assertIn(status, (3, 4))
                self.assertEqual(image, b'')
                self.assertEqual(result.written, 0)

    def test_exact_and_short_final_output(self):
        for mode in self.libs:
            status, image, result = self.assemble(mode, PROGRAM)
            self.assertEqual(status, 0)
            self.assertEqual(self.assemble(mode, PROGRAM, capacity=len(image))[1], image)
            status, image, result = self.assemble(mode, PROGRAM, capacity=len(image) - 1)
            self.assertEqual(status, 2)
            self.assertEqual(image, b'')


if __name__ == '__main__':
    unittest.main()
