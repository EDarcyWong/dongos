"""Same-boot device recovery and faulting-DMA reclamation on real Dong code.

user.device_recovery is a pure authority ledger. The probe compiles it in debug
and release, links it into a DLL with a C shim, and Python drives the SysV
exports through ctypes. Expected values come from an independent Python state
machine; every rejected call must leave the whole table and all output buffers
byte-for-byte unchanged. Real wrong Dong sources (compiled, linked and executed)
must be caught by the same checks.

This is an offline contract test: no PCI configuration space, MMIO, MSR, page
table, TLB instruction or kernel boot is involved.
"""
from __future__ import annotations
import ctypes
import hashlib
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent
MAX = 2 ** 64 - 1
GUARD = 0xA5A5A5A5A5A5A5A5
TABLE_WORDS = 71

OK, INVALID, DENIED, BUSY, STALE, CAPACITY, STATE, IDENTITY, RETIRED = range(9)
ACTIVE, FAULTED, SAFE, QUIESCED, RECLAIMED, RESET, DEAD = range(1, 8)
LEASE_HELD, LEASE_QUARANTINED, LEASE_RECLAIMED = 1, 2, 3
MASK_IRQ, DISABLE_BME, RETIRE_OWNER, WAIT_QUIESCE, FLUSH_MAPPINGS, ZERO_PAGES, RECLAIM, RESET_DEVICE, REBIND_DEVICE, REAUTHORIZE = range(1, 11)
BLOCK, TABLET, PS2, XHCI = 1, 2, 3, 4
MAX_ATTEMPTS, MAX_PAGES = 3, 32
MAX_GENERATION = 0x00FF_FFFF_FFFF_FFFF
DEV_FIELDS = ('token', 'generation', 'slot', 'role', 'identity', 'state', 'owner', 'incarnation', 'lease', 'attempts')
LEASE_FIELDS = ('token', 'device_token', 'device_generation', 'owner', 'physical', 'pages', 'state')

EXPORTS = ['dr_init', 'dr_register', 'dr_allocate', 'dr_fault', 'dr_confirm', 'dr_quiesce', 'dr_reclaim',
           'dr_reset', 'dr_reauthorize', 'dr_retire', 'dr_device', 'dr_lease', 'dr_lease_check']
SHIM = '#include <stdint.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#ifdef _WIN32\n#define EXPORT __declspec(dllexport)\n#else\n#define EXPORT\n#endif\n' + \
    ''.join(f'extern char {n}[];\n' for n in EXPORTS) + \
    'typedef uint64_t (__attribute__((sysv_abi)) *fn9)(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);\n' \
    'void __attribute__((sysv_abi,noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n){fprintf(stderr,"unexpected panic %u/%u\\n",k,l);(void)f;(void)n;exit(87);}\n' \
    'EXPORT void* lookup(const char*name){\n' + ''.join(f' if(!strcmp(name,"{n}"))return {n};\n' for n in EXPORTS) + ' return 0;}\n' \
    'EXPORT uint64_t call9(void*f,uint64_t a,uint64_t b,uint64_t c,uint64_t d,uint64_t e,uint64_t g,uint64_t h,uint64_t i,uint64_t j){return ((fn9)f)(a,b,c,d,e,g,h,i,j);}\n'


class Mem:
    def __init__(self, words, fill=0):
        self.n = words
        self.raw = (ctypes.c_uint64 * (words + 8))(*([GUARD] * 4 + [fill] * words + [GUARD] * 4))
        self.addr = ctypes.addressof(self.raw) + 32

    def get(self):
        return list(self.raw[4:4 + self.n])

    def guards_ok(self):
        return all(v == GUARD for v in list(self.raw[:4]) + list(self.raw[4 + self.n:]))


class Native:
    def __init__(self, dll_path):
        self.dll = ctypes.CDLL(str(dll_path))
        self.dll.lookup.restype = ctypes.c_void_p
        self.dll.lookup.argtypes = [ctypes.c_char_p]
        self.dll.call9.restype = ctypes.c_uint64
        self.dll.call9.argtypes = [ctypes.c_void_p] + [ctypes.c_uint64] * 9
        self.fns = {n: self.dll.lookup(n.encode()) for n in EXPORTS}

    def call(self, name, *args):
        assert len(args) <= 9
        return self.dll.call9(self.fns[name], *([a & MAX for a in args] + [0] * (9 - len(args))))


class Driver:
    """ctypes wrapper that also enforces output/table atomicity on every refusal."""

    def __init__(self, lib):
        self.lib = lib
        self.table = Mem(TABLE_WORDS)
        self._expect('dr_init', self.table.addr, table=True)

    def _expect(self, name, *args, table=False):
        before = self.table.get()
        status = self.lib.call(name, *args)
        assert self.table.guards_ok()
        if status != OK and table:
            assert self.table.get() == before, (name, status, 'table changed on refusal')
        return status

    def init_again(self):
        return self._expect('dr_init', self.table.addr, table=True)

    def register(self, generation, role, identity, owner, incarnation):
        out = Mem(1, 0x1111)
        before = self.table.get()
        status = self.lib.call('dr_register', self.table.addr, generation, role, identity, owner, incarnation, out.addr)
        assert self.table.guards_ok() and out.guards_ok()
        if status != OK:
            assert self.table.get() == before and out.get() == [0x1111]
        return status, out.get()[0] if status == OK else 0

    def allocate(self, token, generation, owner, pages, physical, zeroed):
        out = Mem(1, 0x2222)
        before = self.table.get()
        status = self.lib.call('dr_allocate', self.table.addr, token, generation, owner, pages, physical, zeroed, out.addr)
        assert self.table.guards_ok() and out.guards_ok()
        if status != OK:
            assert self.table.get() == before and out.get() == [0x2222]
        return status, out.get()[0] if status == OK else 0

    def _steps(self, name, args, capacity):
        steps = Mem(16, 0x4444)
        written = Mem(1, 0x5555)
        before = self.table.get()
        status = self.lib.call(name, *args, steps.addr, capacity, written.addr)
        assert self.table.guards_ok() and steps.guards_ok() and written.guards_ok()
        n = written.get()[0]
        if status != OK:
            assert self.table.get() == before and steps.get() == [0x4444] * 16 and n == 0x5555, (name, status)
        else:
            assert 0 <= n <= capacity and steps.get()[2 * n:] == [0x4444] * (16 - 2 * n)
        return status, [(steps.get()[2 * i], steps.get()[2 * i + 1]) for i in range(n if status == OK else 0)]

    def fault(self, token, generation, capacity=8):
        return self._steps('dr_fault', [self.table.addr, token, generation], capacity)

    def confirm(self, token, generation, irq_masked, bme_off, capacity=8):
        return self._steps('dr_confirm', [self.table.addr, token, generation, irq_masked, bme_off], capacity)

    def quiesce(self, token, generation, inflight, mappings, capacity=8):
        return self._steps('dr_quiesce', [self.table.addr, token, generation, inflight, mappings], capacity)

    def reclaim(self, token, generation, zeroed, capacity=8):
        out = Mem(1, 0x6666)
        steps = Mem(16, 0x4444)
        written = Mem(1, 0x5555)
        before = self.table.get()
        status = self.lib.call('dr_reclaim', self.table.addr, token, generation, zeroed, steps.addr, capacity, written.addr, out.addr)
        assert self.table.guards_ok() and steps.guards_ok() and written.guards_ok() and out.guards_ok()
        n = written.get()[0]
        if status != OK:
            assert self.table.get() == before and steps.get() == [0x4444] * 16 and n == 0x5555 and out.get() == [0x6666], status
        else:
            assert 0 <= n <= capacity and steps.get()[2 * n:] == [0x4444] * (16 - 2 * n)
        return status, [(steps.get()[2 * i], steps.get()[2 * i + 1]) for i in range(n if status == OK else 0)], out.get()[0] if status == OK else 0

    def reset(self, token, generation, reset_ok, identity):
        return self._expect('dr_reset', self.table.addr, token, generation, reset_ok, identity, table=True)

    def reauthorize(self, token, generation, role, owner, incarnation):
        out = Mem(1, 0x7777)
        steps = Mem(16, 0x4444)
        written = Mem(1, 0x5555)
        before = self.table.get()
        status = self.lib.call('dr_reauthorize', self.table.addr, token, generation, role, owner, incarnation, steps.addr, written.addr, out.addr)
        assert self.table.guards_ok() and steps.guards_ok() and written.guards_ok() and out.guards_ok()
        n = written.get()[0]
        if status != OK:
            assert self.table.get() == before and steps.get() == [0x4444] * 16 and n == 0x5555 and out.get() == [0x7777], status
        else:
            assert n == 2 and steps.get()[4:] == [0x4444] * 12
        return status, [(steps.get()[2 * i], steps.get()[2 * i + 1]) for i in range(n if status == OK else 0)], out.get()[0] if status == OK else 0

    def retire(self, token, generation):
        return self._expect('dr_retire', self.table.addr, token, generation, table=True)

    def device(self, index):
        out = Mem(10, 0x8888)
        before = self.table.get()
        status = self.lib.call('dr_device', self.table.addr, index, out.addr)
        assert self.table.guards_ok() and out.guards_ok()
        if status != OK:
            assert out.get() == [0x8888] * 10 and self.table.get() == before
        return status, out.get()

    def lease(self, index):
        out = Mem(7, 0x9999)
        before = self.table.get()
        status = self.lib.call('dr_lease', self.table.addr, index, out.addr)
        assert self.table.guards_ok() and out.guards_ok()
        if status != OK:
            assert out.get() == [0x9999] * 7 and self.table.get() == before
        return status, out.get()

    def lease_check(self, lease_token, device_token, generation, owner):
        before = self.table.get()
        status = self.lib.call('dr_lease_check', self.table.addr, lease_token, device_token, generation, owner)
        assert self.table.guards_ok()
        if status != OK:
            assert self.table.get() == before
        return status

    def snapshot(self):
        words = self.table.get()
        devices = [self.device(i)[1] for i in range(words[1])]
        leases = [self.lease(i)[1] for i in range(4)]
        return (words[0], words[1], words[2], devices, leases)


class Model:
    """Independent implementation of the documented transition rules."""

    def __init__(self):
        self.initialized = 1
        self.count = 0
        self.serial = 0
        self.devices = [{k: 0 for k in DEV_FIELDS} for _ in range(4)]
        self.leases = [{k: 0 for k in LEASE_FIELDS} for _ in range(4)]

    def initialize_again(self):
        return INVALID

    def _find(self, token, generation):
        for i in range(self.count):
            d = self.devices[i]
            if d['token'] == token and d['generation'] == generation:
                return i
        return None

    def _find_lease(self, token):
        for i in range(4):
            lease = self.leases[i]
            if lease['token'] == token and lease['state'] != 0:
                return i
        return None

    def register(self, generation, role, identity, owner, incarnation):
        if generation == 0 or generation > MAX_GENERATION or role not in (1, 2, 3, 4) or identity == 0 or owner == 0 or incarnation == 0:
            return INVALID, 0
        if any(self.devices[i]['role'] == role for i in range(self.count)):
            return BUSY, 0
        if self.count >= 4:
            return CAPACITY, 0
        slot = self.count + 1
        token = (generation << 8) | slot
        self.devices[self.count] = dict(token=token, generation=generation, slot=slot, role=role,
                                        identity=identity, state=ACTIVE, owner=owner,
                                        incarnation=incarnation, lease=0, attempts=0)
        self.count += 1
        return OK, token

    def allocate(self, token, generation, owner, pages, physical, zeroed):
        i = self._find(token, generation)
        if i is None:
            return STALE, 0
        d = self.devices[i]
        if d['state'] == DEAD:
            return RETIRED, 0
        if d['state'] != ACTIVE:
            return STATE, 0
        if d['owner'] != owner or owner == 0:
            return DENIED, 0
        if d['role'] == PS2 or d['lease'] != 0:
            return DENIED if d['role'] == PS2 else BUSY, 0
        if zeroed != 1 or pages == 0 or pages > MAX_PAGES:
            return DENIED, 0
        size = pages * 4096
        if size // 4096 != pages or physical == 0 or physical % 4096 != 0 or physical > MAX - size:
            return INVALID, 0
        if self.serial >= MAX_GENERATION:
            return CAPACITY, 0
        slot = next((s for s in range(4) if self.leases[s]['state'] in (0, LEASE_RECLAIMED)), None)
        if slot is None:
            return CAPACITY, 0
        serial = self.serial + 1
        lease_token = (serial << 8) | (slot + 1)
        self.leases[slot] = dict(token=lease_token, device_token=token, device_generation=generation,
                                  owner=owner, physical=physical, pages=pages, state=LEASE_HELD)
        self.serial = serial
        d['lease'] = lease_token
        return OK, lease_token

    def lease_check(self, lease_token, device_token, generation, owner):
        i = self._find(device_token, generation)
        if i is None:
            return STALE
        d = self.devices[i]
        if d['state'] == DEAD:
            return RETIRED
        l = self._find_lease(lease_token)
        if l is None or d['lease'] != lease_token:
            return STALE
        lease = self.leases[l]
        if lease['device_token'] != device_token or lease['device_generation'] != generation or lease['owner'] != owner:
            return DENIED
        if lease['state'] != LEASE_HELD:
            return STATE
        return OK

    def fault(self, token, generation, capacity):
        i = self._find(token, generation)
        if i is None:
            return STALE, []
        d = self.devices[i]
        if d['state'] == DEAD:
            return RETIRED, []
        if d['state'] != ACTIVE:
            return STATE, []
        if capacity < 3:
            return CAPACITY, []
        if d['lease'] != 0:
            l = self._find_lease(d['lease'])
            if l is None:
                return INVALID, []
            self.leases[l]['state'] = LEASE_QUARANTINED
        d['state'] = FAULTED
        if d['attempts'] >= MAX_ATTEMPTS:
            d['state'] = DEAD
        return OK, [(MASK_IRQ, 0), (DISABLE_BME, 0), (RETIRE_OWNER, d['owner'])]

    def confirm(self, token, generation, irq_masked, bme_off, capacity):
        i = self._find(token, generation)
        if i is None:
            return STALE, []
        d = self.devices[i]
        if d['state'] == DEAD:
            return RETIRED, []
        if d['state'] != FAULTED:
            return STATE, []
        if irq_masked != 1 or bme_off != 1:
            return DENIED, []
        if capacity < 2:
            return CAPACITY, []
        d['state'] = SAFE
        return OK, [(WAIT_QUIESCE, 0), (FLUSH_MAPPINGS, 0)]

    def quiesce(self, token, generation, inflight, mappings, capacity):
        i = self._find(token, generation)
        if i is None:
            return STALE, []
        d = self.devices[i]
        if d['state'] == DEAD:
            return RETIRED, []
        if d['state'] != SAFE:
            return STATE, []
        if inflight != 0 or mappings != 0:
            return BUSY, []
        need = 0
        if d['lease'] != 0:
            l = self._find_lease(d['lease'])
            if l is None:
                return INVALID, []
            if self.leases[l]['state'] != LEASE_QUARANTINED:
                return STATE, []
            need = 1
        if capacity < need:
            return CAPACITY, []
        d['state'] = QUIESCED
        return OK, ([(ZERO_PAGES, 0)] if need else [])

    def reclaim(self, token, generation, zeroed, capacity):
        i = self._find(token, generation)
        if i is None:
            return STALE, [], 0
        d = self.devices[i]
        if d['state'] == DEAD:
            return RETIRED, [], 0
        if d['state'] != QUIESCED:
            return STATE, [], 0
        if generation >= MAX_GENERATION:
            return CAPACITY, [], 0
        lease_slot = None
        if d['lease'] != 0:
            lease_slot = self._find_lease(d['lease'])
            if lease_slot is None:
                return INVALID, [], 0
            if self.leases[lease_slot]['state'] != LEASE_QUARANTINED:
                return STATE, [], 0
            if zeroed != 1:
                return DENIED, [], 0
        if capacity < 1:
            return CAPACITY, [], 0
        old_lease = d['lease']
        if lease_slot is not None:
            self.leases[lease_slot]['state'] = LEASE_RECLAIMED
            d['lease'] = 0
        next_generation = generation + 1
        d['generation'] = next_generation
        d['token'] = (next_generation << 8) | d['slot']
        d['state'] = RECLAIMED
        return OK, [(RECLAIM, old_lease)], d['token']

    def reset(self, token, generation, reset_ok, identity):
        i = self._find(token, generation)
        if i is None:
            return STALE
        d = self.devices[i]
        if d['state'] == DEAD:
            return RETIRED
        if d['state'] != RECLAIMED:
            return STATE
        if reset_ok != 1:
            return DENIED
        if identity != d['identity']:
            return IDENTITY
        d['state'] = RESET
        return OK

    def reauthorize(self, token, generation, role, owner, incarnation):
        i = self._find(token, generation)
        if i is None:
            return STALE, [], 0
        d = self.devices[i]
        if d['state'] == DEAD:
            return RETIRED, [], 0
        if d['state'] != RESET:
            return STATE, [], 0
        if d['attempts'] >= MAX_ATTEMPTS:
            return RETIRED, [], 0
        if role not in (1, 2, 3, 4) or role != d['role'] or owner == 0 or incarnation == 0:
            return DENIED, [], 0
        if generation >= MAX_GENERATION:
            return CAPACITY, [], 0
        next_generation = generation + 1
        d['generation'] = next_generation
        d['token'] = (next_generation << 8) | d['slot']
        d['state'] = ACTIVE
        d['owner'] = owner
        d['incarnation'] = incarnation
        d['attempts'] += 1
        d['lease'] = 0
        return OK, [(REBIND_DEVICE, role), (REAUTHORIZE, d['token'])], d['token']

    def retire(self, token, generation):
        i = self._find(token, generation)
        if i is None:
            return STALE
        if self.devices[i]['state'] == DEAD:
            return RETIRED
        self.devices[i]['state'] = DEAD
        return OK

    def snapshot(self):
        return (self.initialized, self.count, self.serial,
                [[d[k] for k in DEV_FIELDS] for d in self.devices[:self.count]],
                [[l[k] for k in LEASE_FIELDS] for l in self.leases])


class NativeDriver(Driver):
    """Driver plus the matching model, so fuzz compares both on every call."""

    def __init__(self, lib):
        super().__init__(lib)
        self.model = Model()

    def compare(self, label):
        native = self.snapshot()
        expected = self.model.snapshot()
        assert native[:3] == expected[:3], (label, native[:3], expected[:3])
        assert native[3] == expected[3], (label, 'devices', native[3], expected[3])
        assert native[4] == expected[4], (label, 'leases', native[4], expected[4])

    def both_init_again(self):
        got = self.init_again()
        assert got == self.model.initialize_again(), (got,)
        self.compare('init-again')
        return got

    def both_register(self, generation, role, identity, owner, incarnation):
        got, token = self.register(generation, role, identity, owner, incarnation)
        want, want_token = self.model.register(generation, role, identity, owner, incarnation)
        assert (got, token) == (want, want_token), ('register', got, token, want, want_token)
        self.compare('register')
        return got, token

    def both_allocate(self, token, generation, owner, pages, physical, zeroed):
        got, lease = self.allocate(token, generation, owner, pages, physical, zeroed)
        want, want_lease = self.model.allocate(token, generation, owner, pages, physical, zeroed)
        assert (got, lease) == (want, want_lease), ('allocate', got, lease, want, want_lease)
        self.compare('allocate')
        return got, lease

    def both_fault(self, token, generation, capacity=8):
        got, steps = self.fault(token, generation, capacity)
        want, want_steps = self.model.fault(token, generation, capacity)
        assert (got, steps) == (want, want_steps), ('fault', got, steps, want, want_steps)
        self.compare('fault')
        return got, steps

    def both_confirm(self, token, generation, irq_masked, bme_off, capacity=8):
        got, steps = self.confirm(token, generation, irq_masked, bme_off, capacity)
        want, want_steps = self.model.confirm(token, generation, irq_masked, bme_off, capacity)
        assert (got, steps) == (want, want_steps), ('confirm', got, steps, want, want_steps)
        self.compare('confirm')
        return got, steps

    def both_quiesce(self, token, generation, inflight, mappings, capacity=8):
        got, steps = self.quiesce(token, generation, inflight, mappings, capacity)
        want, want_steps = self.model.quiesce(token, generation, inflight, mappings, capacity)
        assert (got, steps) == (want, want_steps), ('quiesce', got, steps, want, want_steps)
        self.compare('quiesce')
        return got, steps

    def both_reclaim(self, token, generation, zeroed, capacity=8):
        got, steps, out = self.reclaim(token, generation, zeroed, capacity)
        want, want_steps, want_out = self.model.reclaim(token, generation, zeroed, capacity)
        assert (got, steps, out) == (want, want_steps, want_out), ('reclaim', got, steps, out, want, want_steps, want_out)
        self.compare('reclaim')
        return got, steps, out

    def both_reset(self, token, generation, reset_ok, identity):
        got = self.reset(token, generation, reset_ok, identity)
        want = self.model.reset(token, generation, reset_ok, identity)
        assert got == want, ('reset', got, want)
        self.compare('reset')
        return got

    def both_reauthorize(self, token, generation, role, owner, incarnation):
        got, steps, out = self.reauthorize(token, generation, role, owner, incarnation)
        want, want_steps, want_out = self.model.reauthorize(token, generation, role, owner, incarnation)
        assert (got, steps, out) == (want, want_steps, want_out), ('reauthorize', got, steps, out, want, want_steps, want_out)
        self.compare('reauthorize')
        return got, steps, out

    def both_retire(self, token, generation):
        got = self.retire(token, generation)
        want = self.model.retire(token, generation)
        assert got == want, ('retire', got, want)
        self.compare('retire')
        return got

    def both_lease_check(self, lease_token, device_token, generation, owner):
        got = self.lease_check(lease_token, device_token, generation, owner)
        want = self.model.lease_check(lease_token, device_token, generation, owner)
        assert got == want, ('lease_check', got, want)
        self.compare('lease-check')
        return got


def build(directory, source_root, label, mode, cc, nasm):
    compiled = compile_file(FIXTURES / 'device_recovery_probe.dg',
                            roots=[FIXTURES, source_root / 'kernel', ROOT / 'lang/std'], mode=mode)
    layouts = {x['full_name']: x['size'] for x in compiled.layout_manifest['types']}
    assert layouts['user.device_recovery.Table'] == 568, layouts
    assert layouts['user.device_recovery.Device'] == 80, layouts
    assert layouts['user.device_recovery.Lease'] == 56, layouts
    name = f'{label}-{mode}'
    asm, obj, shim, dll = (directory / (name + s) for s in ('.asm', '.o', '.c', '.dll'))
    asm.write_text(compiled.assembly, encoding='utf-8')
    shim.write_text(SHIM, encoding='utf-8')
    subprocess.run([nasm, '-f', 'win64' if os.name == 'nt' else 'elf64', *nasm_flags(nasm), '-o', str(obj), str(asm)],
                   check=True, capture_output=True, timeout=120)
    # Dong assembly calls shim exports directly; bind local ELF definitions.
    flags = [] if os.name == 'nt' else ['-fPIC', '-Wl,-Bsymbolic']
    linked = subprocess.run([cc, '-std=gnu11', '-O2', '-shared', *flags, str(shim), str(obj), '-o', str(dll)],
                            capture_output=True, text=True, timeout=120)
    if linked.returncode:
        raise AssertionError((name, linked.returncode, linked.stdout, linked.stderr))
    return Native(dll)


def drive_cycle(d, index, owner, incarnation, identity, pages=32, physical=0x20_0000):
    """One complete recovery of device `index`; returns the new token/generation/lease."""
    token = d.snapshot()[3][index][0]
    generation = d.snapshot()[3][index][1]
    status, lease = d.both_allocate(token, generation, owner, pages, physical, 1)
    assert status == OK, (status, 4)
    assert d.both_lease_check(lease, token, generation, owner) == OK
    assert d.both_lease_check(lease, token, generation, owner + 1) == DENIED
    assert d.both_lease_check(lease, token, generation + 1, owner) == STALE
    # A second lease while one is live is refused.
    assert d.both_allocate(token, generation, owner, pages, physical, 1)[0] == BUSY
    status, steps = d.both_fault(token, generation)
    assert status == OK and steps == [(MASK_IRQ, 0), (DISABLE_BME, 0), (RETIRE_OWNER, owner)], steps
    # No new DMA work may start once the lease is quarantined.
    assert d.both_lease_check(lease, token, generation, owner) == STATE
    # Reclaiming before the hardware observation and quiescence gates is refused.
    assert d.both_reclaim(token, generation, 1)[0] == STATE
    assert d.both_confirm(token, generation, 1, 0)[0] == DENIED
    assert d.both_confirm(token, generation, 0, 1)[0] == DENIED
    status, steps = d.both_confirm(token, generation, 1, 1)
    assert status == OK and steps == [(WAIT_QUIESCE, 0), (FLUSH_MAPPINGS, 0)], steps
    assert d.both_quiesce(token, generation, 1, 0)[0] == BUSY
    assert d.both_quiesce(token, generation, 0, 1)[0] == BUSY
    status, steps = d.both_quiesce(token, generation, 0, 0)
    assert status == OK and steps == [(ZERO_PAGES, 0)], steps
    assert d.both_reclaim(token, generation, 0)[0] == DENIED
    status, steps, token = d.both_reclaim(token, generation, 1)
    assert status == OK and steps == [(RECLAIM, lease)], steps
    assert d.both_lease_check(lease, token, generation + 1, owner) == STALE
    generation += 1
    reclaimed_token = token
    assert d.both_reset(token, generation, 0, identity) == DENIED
    assert d.both_reset(token, generation, 1, identity ^ 0x1000) == IDENTITY
    assert d.both_reset(token, generation, 1, identity) == OK
    assert d.both_reauthorize(token, generation, PS2, owner, incarnation + 1)[0] == DENIED
    assert d.both_reauthorize(token, generation, d.snapshot()[3][index][3], 0, incarnation + 1)[0] == DENIED
    status, steps, token = d.both_reauthorize(token, generation, d.snapshot()[3][index][3], owner, incarnation + 1)
    assert status == OK and steps[0][0] == REBIND_DEVICE and steps[1] == (REAUTHORIZE, token), steps
    assert token != reclaimed_token, ('re-authorization did not advance the incarnation', token)
    assert d.snapshot()[3][index][5] == ACTIVE
    return token, d.snapshot()[3][index][1], lease


def verify_semantics(d):
    # Registration and identity rules.
    assert d.both_register(0, BLOCK, 0x8086_1234, 7, 1)[0] == INVALID
    assert d.both_register(1, 9, 0x8086_1234, 7, 1)[0] == INVALID
    assert d.both_register(1, BLOCK, 0, 7, 1)[0] == INVALID
    assert d.both_register(1, BLOCK, 0x8086_1234, 0, 1)[0] == INVALID
    status, token = d.both_register(1, BLOCK, 0x8086_1234, 7, 1)
    assert status == OK and token == (1 << 8) | 1, hex(token)
    assert d.both_register(2, BLOCK, 0x8086_1235, 8, 2)[0] == BUSY
    assert d.both_init_again() == INVALID
    # DMA allocation gates.
    gen = 1
    assert d.both_allocate(token, gen, 7, 32, 0x20_0000, 0)[0] == DENIED
    assert d.both_allocate(token, gen, 7, 0, 0x20_0000, 1)[0] == DENIED
    assert d.both_allocate(token, gen, 7, 33, 0x20_0000, 1)[0] == DENIED
    assert d.both_allocate(token, gen, 7, 32, 0x20_0001, 1)[0] == INVALID
    assert d.both_allocate(token, gen, 8, 32, 0x20_0000, 1)[0] == DENIED
    assert d.both_allocate(token, gen + 1, 7, 32, 0x20_0000, 1)[0] == STALE
    assert d.both_allocate(token, gen, 7, 32, 2 ** 64 - 4096, 1)[0] == INVALID
    # A full recovery cycle, then every step gate again on the new incarnation.
    token, gen, _ = drive_cycle(d, 0, 7, 1, 0x8086_1234)
    # Stale token/generation after each bump.
    assert d.both_fault((1 << 8) | 1, 1)[0] == STALE
    assert d.both_allocate(token, gen - 1, 8, 32, 0x20_0000, 1)[0] == STALE
    # Out-of-order transitions are refused.
    assert d.both_confirm(token, gen, 1, 1)[0] == STATE
    assert d.both_quiesce(token, gen, 0, 0)[0] == STATE
    assert d.both_reclaim(token, gen, 1)[0] == STATE
    assert d.both_reset(token, gen, 1, 0x8086_1234) == STATE
    assert d.both_reauthorize(token, gen, BLOCK, 8, 2)[0] == STATE
    assert d.both_retire(token, gen) == OK
    assert d.both_fault(token, gen)[0] == RETIRED
    assert d.both_allocate(token, gen, 8, 32, 0x20_0000, 1)[0] == RETIRED
    assert d.both_retire(token, gen) == RETIRED
    # A retired device holds its lease forever.
    status, token2 = d.both_register(1, XHCI, 0x1d6b_0003, 9, 3)
    assert status == OK
    assert d.both_allocate(token2, 1, 9, 32, 0x30_0000, 1)[0] == OK
    assert d.both_fault(token2, 1)[0] == OK
    assert d.both_retire(token2, 1) == OK
    assert d.lease(0)[1][6] == LEASE_QUARANTINED
    # PS2 has no DMA but still recovers through the same gates.
    status, ps2 = d.both_register(1, PS2, 0x1, 10, 4)
    assert status == OK
    assert d.both_allocate(ps2, 1, 10, 1, 0x40_0000, 1)[0] == DENIED
    status, steps = d.both_fault(ps2, 1)
    assert status == OK and steps == [(MASK_IRQ, 0), (DISABLE_BME, 0), (RETIRE_OWNER, 10)], steps
    assert d.both_confirm(ps2, 1, 1, 1)[0] == OK
    status, steps = d.both_quiesce(ps2, 1, 0, 0)
    assert status == OK and steps == [], steps
    status, steps, ps2 = d.both_reclaim(ps2, 1, 0)
    assert status == OK and steps == [(RECLAIM, 0)], steps
    assert d.both_reset(ps2, 2, 1, 0x1) == OK
    assert d.both_reauthorize(ps2, 2, PS2, 10, 5)[0] == OK
    # Fill the fourth role and re-check duplicate-role and retired-token rules.
    status, tablet = d.both_register(1, TABLET, 0x1af4_1052, 11, 6)
    assert status == OK
    assert d.both_register(1, BLOCK, 0x2, 12, 7)[0] == BUSY
    assert d.both_allocate((1 << 8) | 1, 1, 7, 32, 0x20_0000, 1)[0] == STALE


def verify_attempts(d):
    # Three completed recoveries are allowed; the next fault is terminal.
    status, token = d.both_register(1, BLOCK, 0x8086_9999, 20, 20)
    assert status == OK
    leases = []
    for cycle in range(MAX_ATTEMPTS):
        token, gen, lease = drive_cycle(d, 0, 20, 20 + cycle, 0x8086_9999)
        leases.append(lease)
        assert d.snapshot()[3][0][9] == cycle + 1
    assert len(set(leases)) == len(leases), leases
    assert d.both_fault(token, gen)[0] == OK
    assert d.snapshot()[3][0][5] == DEAD
    assert d.both_allocate(token, gen, 20, 32, 0x50_0000, 1)[0] == RETIRED
    assert d.both_retire(token, gen) == RETIRED


def verify_mutant(d):
    """Compact sequence that every listed mutant must fail somewhere."""
    status, token = d.both_register(1, BLOCK, 0x8086_7777, 40, 40)
    assert status == OK
    seen_leases = []
    token, gen, lease = drive_cycle(d, 0, 40, 40, 0x8086_7777)
    seen_leases.append(lease)
    # The token from before reclamation must be dead, not silently accepted.
    old = (1 << 8) | 1
    assert d.both_fault(old, 1)[0] == STALE
    assert d.both_reclaim(old, 1, 1)[0] == STALE
    token, gen, lease = drive_cycle(d, 0, 40, 41, 0x8086_7777)
    seen_leases.append(lease)
    # A later cycle reuses a reclaimed lease slot; the serial must make its
    # token differ from the first cycle's token.
    token, gen, lease = drive_cycle(d, 0, 40, 42, 0x8086_7777)
    seen_leases.append(lease)
    assert len(set(seen_leases)) == len(seen_leases), seen_leases
    assert d.both_fault(token, gen)[0] == OK
    assert d.snapshot()[3][0][5] == DEAD


def verify_generation_bounds(d):
    # Reclamation cannot bump past MAX_GENERATION.
    status, token = d.both_register(MAX_GENERATION, TABLET, 0x1af4_1052, 30, 30)
    assert status == OK
    assert d.both_allocate(token, MAX_GENERATION, 30, 1, 0x60_0000, 1)[0] == OK
    assert d.both_fault(token, MAX_GENERATION)[0] == OK
    assert d.both_confirm(token, MAX_GENERATION, 1, 1)[0] == OK
    assert d.both_quiesce(token, MAX_GENERATION, 0, 0)[0] == OK
    assert d.both_reclaim(token, MAX_GENERATION, 1)[0] == CAPACITY
    assert d.both_retire(token, MAX_GENERATION) == OK
    # Re-authorization cannot bump past MAX_GENERATION either.
    status, token = d.both_register(MAX_GENERATION - 1, BLOCK, 0x8086_5555, 31, 31)
    assert status == OK
    assert d.both_allocate(token, MAX_GENERATION - 1, 31, 1, 0x61_0000, 1)[0] == OK
    assert d.both_fault(token, MAX_GENERATION - 1)[0] == OK
    assert d.both_confirm(token, MAX_GENERATION - 1, 1, 1)[0] == OK
    assert d.both_quiesce(token, MAX_GENERATION - 1, 0, 0)[0] == OK
    status, steps, token = d.both_reclaim(token, MAX_GENERATION - 1, 1)
    assert status == OK and steps[0][0] == RECLAIM
    assert d.both_reset(token, MAX_GENERATION, 1, 0x8086_5555) == OK
    assert d.both_reauthorize(token, MAX_GENERATION, BLOCK, 31, 32)[0] == CAPACITY
    assert d.both_retire(token, MAX_GENERATION) == OK


def verify_pointers(lib):
    t = Mem(TABLE_WORDS)
    assert lib.call('dr_init', 0) == INVALID
    assert lib.call('dr_init', t.addr + 4) == INVALID
    assert lib.call('dr_init', t.addr) == OK
    steps, written, word = Mem(16), Mem(1), Mem(1)
    # Output/step buffers overlapping the live table are refused.
    assert lib.call('dr_fault', t.addr, 1, 1, t.addr, 8, written.addr) == INVALID
    assert lib.call('dr_fault', t.addr, 1, 1, steps.addr, 8, t.addr) == INVALID
    assert lib.call('dr_register', t.addr, 1, BLOCK, 1, 1, 1, t.addr) == INVALID
    assert lib.call('dr_register', t.addr, 1, BLOCK, 1, 1, 1, 0) == INVALID
    assert lib.call('dr_register', t.addr, 1, BLOCK, 1, 1, 1, word.addr + 4) == INVALID
    assert lib.call('dr_device', t.addr, 0, 0) == INVALID
    assert lib.call('dr_lease', t.addr, 0, 0) == INVALID
    assert lib.call('dr_lease', 0, 0, word.addr) == INVALID
    assert lib.call('dr_lease_check', 0, 0, 0, 0, 0) == INVALID
    assert lib.call('dr_reclaim', t.addr, 1, 1, 1, steps.addr, 8, written.addr, steps.addr) == INVALID


def verify_fuzz(d, rounds=1600):
    rnd = random.Random(0x0513)
    seen = set()
    for n in range(rounds):
        snap = d.snapshot()
        count = snap[1]
        devices = snap[3]
        seen.update(devices[i][5] for i in range(count))
        op = rnd.randrange(10)
        index = rnd.randrange(4)
        live = index < count
        token = devices[index][0] if live else rnd.getrandbits(63)
        generation = devices[index][1] if live else rnd.randrange(0, 4)
        owner = devices[index][6] if live else rnd.randrange(0, 4)
        role = devices[index][3] if live else rnd.randrange(0, 6)
        identity = devices[index][4] if live else rnd.getrandbits(32)
        if op == 0:
            d.both_register(rnd.choice([0, 1, 2, MAX_GENERATION, rnd.randrange(1, 8)]),
                            rnd.choice([0, 1, 2, 3, 4, 5, 9]), rnd.choice([0, identity, 1]), rnd.choice([0, 1, 2]),
                            rnd.choice([0, 1, 2]))
        elif op == 1:
            d.both_allocate(token, generation, rnd.choice([owner, 0, owner + 1]),
                            rnd.choice([0, 1, 32, 33, MAX_PAGES]), rnd.choice([0, 0x1000, 0x20_0000, 0x20_0001]),
                            rnd.choice([0, 1]))
        elif op == 2:
            d.both_fault(token, generation, rnd.choice([0, 3, 8]))
        elif op == 3:
            d.both_confirm(token, generation, rnd.choice([0, 1]), rnd.choice([0, 1]), rnd.choice([0, 2, 8]))
        elif op == 4:
            d.both_quiesce(token, generation, rnd.choice([0, 1]), rnd.choice([0, 1]), rnd.choice([0, 1, 8]))
        elif op == 5:
            d.both_reclaim(token, generation, rnd.choice([0, 1]), rnd.choice([0, 1, 8]))
        elif op == 6:
            d.both_reset(token, generation, rnd.choice([0, 1]), rnd.choice([identity, identity ^ 0x1000]))
        elif op == 7:
            d.both_reauthorize(token, generation, rnd.choice([role, PS2, 0]),
                               rnd.choice([0, owner, owner + 1]), rnd.choice([0, 1, 2]))
        elif op == 8:
            d.both_retire(token, generation)
        else:
            # Force a valid recovery often enough that the fuzz reaches later states.
            if live and devices[index][5] == ACTIVE and devices[index][8] == 0 and devices[index][6] != 0:
                d.both_allocate(token, generation, devices[index][6], 32, 0x20_0000, 1)
            elif live and devices[index][5] == ACTIVE:
                d.both_fault(token, generation)
            elif live and devices[index][5] == FAULTED:
                d.both_confirm(token, generation, 1, 1)
            elif live and devices[index][5] == SAFE:
                d.both_quiesce(token, generation, 0, 0)
            elif live and devices[index][5] == QUIESCED:
                d.both_reclaim(token, generation, 1)
            elif live and devices[index][5] == RECLAIMED:
                d.both_reset(token, generation, 1, identity)
            elif live and devices[index][5] == RESET:
                d.both_reauthorize(token, generation, role, owner, 9)
    assert ACTIVE in seen and DEAD in seen, seen


class DeviceRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest('native recovery checks require NASM and GCC')
        cls.dir = Path(tempfile.mkdtemp(prefix='device-recovery-'))
        cls.sources = [ROOT / 'kernel/user/device_recovery.dg', ROOT / 'tests/device_recovery_probe.dg',
                       ROOT / 'tests/test_device_recovery.py']
        cls.before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.sources}
        cls.libs = {mode: build(cls.dir, ROOT, 'good', mode, cls.cc, cls.nasm) for mode in ('debug', 'release')}

    @classmethod
    def tearDownClass(cls):
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.sources}
        assert after == cls.before, 'recovery sources changed during the test'
        shutil.rmtree(cls.dir, ignore_errors=True)

    def each_mode(self, check):
        for mode, lib in self.libs.items():
            with self.subTest(mode=mode):
                check(NativeDriver(lib))

    def test_state_machine_gates(self):
        self.each_mode(verify_semantics)
        self.each_mode(verify_attempts)

    def test_generation_and_pointer_limits(self):
        self.each_mode(verify_generation_bounds)
        for lib in self.libs.values():
            verify_pointers(lib)

    def test_random_sequences_match_independent_model(self):
        self.each_mode(verify_fuzz)

    def test_wrong_dong_implementations_are_rejected(self):
        mutants = [
            ('reclaim-before-quiesce', 'if d.state!=QUIESCED{return STATE;}', 'if d.state==DEAD{return STATE;}', verify_mutant),
            ('reclaim-without-zero', 'if (*t).leases[lease_slot].state!=LEASE_QUARANTINED{return STATE;}\n        if zeroed!=1{return DENIED;}', 'if (*t).leases[lease_slot].state!=LEASE_QUARANTINED{return STATE;}', verify_mutant),
            ('reauth-reuses-generation',
             'let next_generation=generation+1;\n    let next_token=(next_generation<<8)|d.slot;\n    (*t).devices[i].generation=next_generation;\n    (*t).devices[i].token=next_token;\n    (*t).devices[i].state=ACTIVE;',
             'let next_generation=generation;\n    let next_token=(next_generation<<8)|d.slot;\n    (*t).devices[i].generation=next_generation;\n    (*t).devices[i].token=next_token;\n    (*t).devices[i].state=ACTIVE;',
             verify_mutant),
            ('quiesce-ignores-inflight', 'if inflight!=0||mappings!=0{return BUSY;}', 'if mappings!=0{return BUSY;}', verify_mutant),
            ('confirm-skips-bme', 'if irq_masked!=1||bme_off!=1{return DENIED;}', 'if irq_masked!=1{return DENIED;}', verify_mutant),
            ('attempts-unbounded', 'if d.attempts>=MAX_ATTEMPTS{(*t).devices[i].state=DEAD;}', '', verify_attempts),
            ('lease-token-reused', 'let serial=(*t).serial+1;', 'let serial=(*t).serial;', verify_mutant),
            ('lease-gate-ignores-quarantine', 'if lease.state!=LEASE_HELD{return STATE;}', 'if lease.state==0{return STATE;}', verify_mutant),
        ]
        for name, old, new, check in mutants:
            root = self.dir / name
            shutil.copytree(ROOT / 'kernel', root / 'kernel', ignore=shutil.ignore_patterns('__pycache__'))
            target = root / 'kernel/user/device_recovery.dg'
            text = target.read_text(encoding='utf-8')
            self.assertEqual(text.count(old), 1, name)
            target.write_text(text.replace(old, new, 1), encoding='utf-8')
            for mode in ('debug', 'release'):
                lib = build(self.dir, root, name, mode, self.cc, self.nasm)
                with self.subTest(mutant=name, mode=mode):
                    with self.assertRaises(AssertionError):
                        check(NativeDriver(lib))


if __name__ == '__main__':
    unittest.main()
