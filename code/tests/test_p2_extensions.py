"""P2 extension planners (huge pages, cross-alias W^X, memory types) on real Dong code.

mm.huge_page_plan, mm.alias_policy and mm.cache_type_plan are compiled in debug and
release, linked into a small DLL together with a C shim that calls the SysV exports,
and driven from Python through ctypes. Expected values come from independent Python
models; every call is wrapped in guard words so a rejected call must leave all caller
storage unchanged. Real wrong Dong sources (compiled and executed) must be rejected by
the same checks. These are offline contract tests: nothing here boots a kernel, loads a
page table or touches an MSR.
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
MODULES = ['huge_page_plan', 'alias_policy', 'cache_type_plan']
MAX = 2 ** 64 - 1
GUARD = 0xA5A5A5A5A5A5A5A5
EXPORTS = ['p2_hp_split', 'p2_hp_merge', 'p2_ap_check', 'p2_ap_plan', 'p2_ct_page_type',
           'p2_ct_pat_valid', 'p2_ct_mtrr', 'p2_ct_aliases', 'p2_ct_migrate', 'p2_ct_effective']
SHIM = '#include <stdint.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#ifdef _WIN32\n#define EXPORT __declspec(dllexport)\n#else\n#define EXPORT\n#endif\n' + \
    ''.join(f'extern char {n}[];\n' for n in EXPORTS) + \
    'typedef uint64_t (__attribute__((sysv_abi)) *fn9)(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);\n' \
    'void __attribute__((sysv_abi,noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n){fprintf(stderr,"unexpected panic %u/%u\\n",k,l);(void)f;(void)n;exit(87);}\n' \
    'EXPORT void* lookup(const char*name){\n' + ''.join(f' if(!strcmp(name,"{n}"))return {n};\n' for n in EXPORTS) + ' return 0;}\n' \
    'EXPORT uint64_t call9(void*f,uint64_t a,uint64_t b,uint64_t c,uint64_t d,uint64_t e,uint64_t g,uint64_t h,uint64_t i,uint64_t j){return ((fn9)f)(a,b,c,d,e,g,h,i,j);}\n'


class Mem:
    """Word buffer with guard words on both sides; address is 8-aligned."""
    def __init__(self, words, fill=0):
        self.n = words
        self.raw = (ctypes.c_uint64 * (words + 8))(*([GUARD] * 4 + [fill] * words + [GUARD] * 4))
        self.addr = ctypes.addressof(self.raw) + 32

    def get(self):
        return list(self.raw[4:4 + self.n])

    def set(self, values):
        for i, v in enumerate(values):
            self.raw[4 + i] = v

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
        padded = [a & MAX for a in args] + [0] * (9 - len(args))
        return self.dll.call9(self.fns[name], *padded)


def build(directory, source_root, label, mode, cc, nasm):
    """Compile the probe against source_root/kernel and link a DLL."""
    compiled = compile_file(FIXTURES / 'p2_extensions_probe.dg',
                            roots=[FIXTURES, source_root / 'kernel', ROOT / 'lang/std'], mode=mode)
    name = f'{label}-{mode}'
    asm, obj, shim, dll = (directory / (name + s) for s in ('.asm', '.o', '.c', '.dll'))
    asm.write_text(compiled.assembly, encoding='utf-8')
    shim.write_text(SHIM, encoding='utf-8')
    subprocess.run([nasm, '-f', 'win64' if os.name == 'nt' else 'elf64', *nasm_flags(nasm), '-o', str(obj), str(asm)],
                   check=True, capture_output=True, timeout=120)
    flags = [] if os.name == 'nt' else ['-fPIC']
    subprocess.run([cc, '-std=gnu11', '-O2', '-shared', *flags, str(shim), str(obj), '-o', str(dll)],
                   check=True, capture_output=True, timeout=120)
    return Native(dll)


# ---------------------------------------------------------------- huge pages
P, RW, US, PWT, PCD, A, D, PS, G = 1, 2, 4, 8, 0x10, 0x20, 0x40, 0x80, 0x100
PDE_PAT, PTE_PAT, NX = 1 << 12, 1 << 7, 1 << 63
SOFT = (0x7 << 9) | (0x7FF << 52)
HP_OK, HP_INVALID, NOT_HUGE, NOT_PRESENT, RESERVED, MISALIGNED, NOT_CONTIGUOUS, ATTR_MISMATCH = range(8)
CLEAR_AD = 1


def attrs(rnd):
    bits = rnd.choice([0, RW, US, PWT, PCD, G, NX, RW | US, PWT | PCD, RW | NX | G]) | (rnd.getrandbits(3) << 9)
    if rnd.random() < .5:
        bits |= rnd.getrandbits(11) << 52
    return bits | P | (A if rnd.random() < .5 else 0) | (D if rnd.random() < .5 else 0)


def model_split(pde, clear_ad):
    base = pde & 0x000F_FFFF_FFE0_0000
    common = pde & ~(0x000F_FFFF_FFE0_0000 | PS | PDE_PAT)
    if pde & PDE_PAT:
        common |= PTE_PAT
    if clear_ad:
        common &= ~(A | D)
    return [common | (base + i * 4096) for i in range(512)]


def hp_split(lib, pde, flags, table_words=512, valid=True):
    table, plan = Mem(table_words, 0x1111), Mem(3, 0x2222)
    status = lib.call('p2_hp_split', pde, flags, table.addr, table_words, plan.addr)
    assert table.guards_ok() and plan.guards_ok(), 'guard words damaged'
    return status, table.get(), plan.get()


def hp_merge(lib, entries, pde0=0x3333):
    table, pde, plan = Mem(len(entries)), Mem(1, pde0), Mem(3, 0x2222)
    table.set(entries)
    status = lib.call('p2_hp_merge', table.addr, len(entries), pde.addr, plan.addr)
    assert table.guards_ok() and pde.guards_ok() and plan.guards_ok(), 'guard words damaged'
    assert table.get() == list(entries), 'merge modified its input table'
    return status, pde.get()[0], plan.get()


def verify_huge(lib):
    rnd = random.Random(0x2025)
    for n in range(300):
        pde = (rnd.randrange(1 << 31) << 21) | attrs(rnd) | PS | (PDE_PAT if rnd.random() < .5 else 0)
        for clear in (0, CLEAR_AD):
            status, table, plan = hp_split(lib, pde, clear)
            assert status == HP_OK, (hex(pde), status)
            assert table == model_split(pde, clear), ('split', hex(pde), clear)
            assert plan == [512, 1, 0], plan
        # round trip: split without clearing A/D then merge restores the PDE exactly
        status, table, _ = hp_split(lib, pde, 0)
        status, merged, plan = hp_merge(lib, table)
        assert status == HP_OK and merged == pde and plan == [512, 1, 1], (hex(pde), status, hex(merged))
    # split failures leave the table and the plan untouched
    good = (7 << 21) | P | PS | RW
    for pde, flags, expect in [(0, 0, NOT_PRESENT), (good & ~P, 0, NOT_PRESENT), (good & ~PS, 0, NOT_HUGE),
                               (good | (1 << 13), 0, RESERVED), (good | (0xFF << 13), 0, RESERVED),
                               (good, 2, HP_INVALID), (good, CLEAR_AD | 4, HP_INVALID)]:
        status, table, plan = hp_split(lib, pde, flags)
        assert status == expect, (hex(pde), flags, status, expect)
        assert table == [0x1111] * 512 and plan == [0x2222] * 3, ('split not atomic', expect)
    assert hp_split(lib, good, 0, table_words=511)[0] == HP_INVALID
    assert hp_split(lib, good, 0, table_words=513)[0] == HP_INVALID
    # merge failures: reason order present -> alignment -> contiguity -> attributes
    base = 0x40_0000
    ok = [base + i * 4096 | P | RW | NX for i in range(512)]
    cases = []
    broken = list(ok); broken[300] &= ~P; cases.append((broken, NOT_PRESENT))
    cases.append(([e + 4096 for e in ok], MISALIGNED))
    broken = list(ok); broken[10], broken[11] = broken[11], broken[10]; cases.append((broken, NOT_CONTIGUOUS))
    broken = list(ok); broken[511] += 4096; cases.append((broken, NOT_CONTIGUOUS))
    for flag in (RW, US, PWT, PCD, G, NX, PTE_PAT, 1 << 10, 1 << 53):
        broken = list(ok); broken[200] ^= flag; cases.append((broken, ATTR_MISMATCH))
    broken = list(ok); broken[5] &= ~P; broken[6] = (broken[6] & ~0xFFFFF000) | 0x1000; cases.append((broken, NOT_PRESENT))
    for entries, expect in cases:
        status, pde, plan = hp_merge(lib, entries)
        assert status == expect, (status, expect)
        assert pde == 0x3333 and plan == [0x2222] * 3, ('merge not atomic', expect)
    # A/D are OR-ed, PAT folds from bit 7 to bit 12 and back
    mixed = list(ok); mixed[3] |= A; mixed[500] |= D | A
    status, pde, _ = hp_merge(lib, [e | PTE_PAT for e in mixed])
    assert status == HP_OK and pde == (base | P | RW | NX | PS | A | D | PDE_PAT), hex(pde)
    status, table, _ = hp_split(lib, pde, 0)
    assert all(e & PTE_PAT for e in table) and not table[0] & PDE_PAT   # bit 12 of entry 0 is address, stays clear
    # descriptor errors
    t, pdev, pl = Mem(512), Mem(1), Mem(3)
    t.set(ok)
    for args in [(t.addr, 512, 0, pl.addr), (t.addr, 512, pdev.addr, 0), (0, 512, pdev.addr, pl.addr),
                 (t.addr + 4, 512, pdev.addr, pl.addr), (t.addr, 511, pdev.addr, pl.addr),
                 (t.addr, 512, pdev.addr + 4, pl.addr), (t.addr, 512, pdev.addr, pl.addr + 4),
                 (t.addr, 512, t.addr + 8, pl.addr), (t.addr, 512, pdev.addr, t.addr + 16),
                 (t.addr, 512, pdev.addr, pdev.addr), (MAX - 7, 512, pdev.addr, pl.addr)]:
        assert lib.call('p2_hp_merge', *args) == HP_INVALID, args
    assert t.get() == ok and t.guards_ok()


# ----------------------------------------------------------------- alias W^X
R_, W_, X_, U_ = 1, 2, 4, 8
AP_OK, AP_INVALID, AP_CAPACITY, VIOLATION, DUPLICATE, NOT_FOUND = range(6)
REVOKE, FLUSH_LOCAL, SHOOTDOWN, GRANT = 1, 2, 3, 4


def alias_words(aliases):
    return [w for a in aliases for w in a]   # (frame, space, virt, perms, cache)


def model_check(aliases):
    for i, a in enumerate(aliases):
        if a[3] & W_ and a[3] & X_:
            return VIOLATION, (i, i)
        for j in range(i + 1, len(aliases)):
            b = aliases[j]
            if a[1] == b[1] and a[2] == b[2]:
                return DUPLICATE, (i, j)
            if a[0] == b[0] and ((a[3] & W_ and b[3] & X_) or (a[3] & X_ and b[3] & W_)):
                return VIOLATION, (i, j)
    return AP_OK, None


def ap_check(lib, aliases):
    mem, found = Mem(max(1, 5 * len(aliases))), Mem(2, 0x7777)
    mem.set(alias_words(aliases))
    status = lib.call('p2_ap_check', mem.addr, len(aliases), found.addr)
    assert mem.guards_ok() and found.guards_ok() and mem.get()[:5 * len(aliases)] == alias_words(aliases)
    return status, found.get()


def ap_plan(lib, aliases, frame, target, grantee, cpus, capacity):
    mem, steps, count = Mem(max(1, 5 * len(aliases))), Mem(max(1, 2 * capacity), 0x4444), Mem(1, 0x5555)
    mem.set(alias_words(aliases))
    status = lib.call('p2_ap_plan', mem.addr, len(aliases), frame, target, grantee, cpus, steps.addr, capacity, count.addr)
    assert mem.guards_ok() and steps.guards_ok() and count.guards_ok()
    return status, steps.get(), count.get()[0]


def random_aliases(rnd, n, frames):
    out, used = [], set()
    while len(out) < n:
        space, virt = rnd.randrange(3), rnd.randrange(20)
        if (space, virt) in used and rnd.random() < .9:
            continue
        used.add((space, virt))
        out.append((rnd.randrange(frames), space, virt, rnd.choice([1, 1, 3, 5, 9, 13, 2, 4, 7, 15]), rnd.choice([6, 1])))
    return out


def verify_alias(lib):
    rnd = random.Random(7)
    seen = set()
    for n in range(500):
        aliases = random_aliases(rnd, rnd.randrange(0, 8), 3)
        status, pair = model_check(aliases)
        got, found = ap_check(lib, aliases)
        assert got == status, (aliases, got, status)
        assert found == (list(pair) if pair else [0x7777] * 2), ('found', found, pair)
        seen.add(status)
    assert seen == {AP_OK, VIOLATION, DUPLICATE}, seen
    # invalid tables
    assert ap_check(lib, [(1, 0, 0, 0, 6)])[0] == AP_INVALID
    assert ap_check(lib, [(1, 0, 0, 16, 6)])[0] == AP_INVALID
    assert lib.call('p2_ap_check', 0, 0, 0) == AP_INVALID
    big = Mem(5 * 257)
    assert lib.call('p2_ap_check', big.addr, 257, Mem(2).addr) == AP_INVALID
    # transitions: simulate each step and require the invariant after EVERY step
    rnd = random.Random(11)
    done = 0
    for n in range(800):
        aliases = random_aliases(rnd, rnd.randrange(1, 7), 2)
        if model_check(aliases)[0] != AP_OK:
            continue
        frame, target = rnd.randrange(2), rnd.choice([1, 2])
        grantee = rnd.randrange(len(aliases))
        cpus = rnd.choice([1, 2, 8])
        conflict = X_ if target == 1 else W_
        revoked = [i for i, a in enumerate(aliases) if a[0] == frame and a[3] & conflict]
        expect = [(REVOKE, i) for i in revoked] + ([(FLUSH_LOCAL, 0)] + ([(SHOOTDOWN, 0)] if cpus > 1 else []) if revoked else []) + [(GRANT, grantee)]
        status, steps, count = ap_plan(lib, aliases, frame, target, grantee, cpus, len(expect))
        if aliases[grantee][0] != frame:
            assert status == NOT_FOUND and count == 0x5555, status
            continue
        assert status == AP_OK, (status, aliases, frame, target, grantee)
        got = [(steps[2 * i], steps[2 * i + 1]) for i in range(count)]
        assert got == expect, (got, expect)
        # exact capacity succeeds, one short fails atomically
        status, steps, count = ap_plan(lib, aliases, frame, target, grantee, cpus, len(expect) - 1)
        assert status == AP_CAPACITY and count == 0x5555 and steps[:2 * (len(expect) - 1)] == [0x4444] * (2 * (len(expect) - 1))
        # independent replay: W^X must hold at every instant, and shootdown precedes grant
        table = [list(a) for a in aliases]
        flushed = not revoked
        for kind, index in got:
            if kind == REVOKE:
                table[index][3] &= ~conflict
                flushed = False
            elif kind in (FLUSH_LOCAL, SHOOTDOWN):
                flushed = True
            else:
                assert flushed and (cpus == 1 or not revoked or (SHOOTDOWN, 0) in got), 'grant before flush/shootdown'
                table[index][3] |= W_ if target == 1 else X_
            assert model_check([tuple(a) for a in table])[0] in (AP_OK, VIOLATION)
            if kind != GRANT:
                assert model_check([tuple(a) for a in table])[0] == AP_OK, ('violation before grant', table)
        assert model_check([tuple(a) for a in table])[0] != DUPLICATE
        done += 1
    assert done > 100, done
    # an inconsistent starting table is refused before any step is written
    bad = [(1, 0, 0, W_, 6), (1, 1, 5, X_, 6)]
    status, steps, count = ap_plan(lib, bad, 1, 1, 0, 2, 10)
    assert status == VIOLATION and count == 0x5555 and steps == [0x4444] * 20
    assert ap_plan(lib, [(1, 0, 0, 1, 6)], 1, 3, 0, 1, 4)[0] == AP_INVALID
    assert ap_plan(lib, [(1, 0, 0, 1, 6)], 1, 1, 0, 0, 4)[0] == AP_INVALID
    assert ap_plan(lib, [(1, 0, 0, 1, 6)], 2, 1, 0, 1, 4)[0] == NOT_FOUND
    assert ap_plan(lib, [(1, 0, 0, 1, 6)], 1, 1, 1, 1, 4)[0] == NOT_FOUND


# ------------------------------------------------------------- memory types
UC_, WC_, WT_, WP_, WB_, UCM_ = 0, 1, 4, 5, 6, 7
CT_OK, CT_INVALID, CT_CAPACITY, CONFLICT = range(4)
DEFAULT_PAT = 0x0007_0406_0007_0406   # WB, WT, UC-, UC, WB, WT, UC-, UC


def model_range_type(ranges, default, phys):
    kinds = {r[2] for r in ranges if r[0] <= phys < r[0] + r[1]}
    if not kinds:
        return CT_OK, default
    if UC_ in kinds:
        return CT_OK, UC_
    if len(kinds) == 1:
        return CT_OK, next(iter(kinds))
    if kinds == {WT_, WB_}:
        return CT_OK, WT_
    return CONFLICT, None


# Intel SDM Vol. 3A Table 14-7 (order 325384-093), transcribed row by row:
# (MTRR type, PAT entry value) -> effective type.
SDM_14_7 = {
    (UC_, UC_): UC_, (UC_, UCM_): UC_, (UC_, WC_): WC_, (UC_, WT_): UC_, (UC_, WB_): UC_, (UC_, WP_): UC_,
    (WC_, UC_): UC_, (WC_, UCM_): WC_, (WC_, WC_): WC_, (WC_, WT_): UC_, (WC_, WB_): WC_, (WC_, WP_): UC_,
    (WT_, UC_): UC_, (WT_, UCM_): UC_, (WT_, WC_): WC_, (WT_, WT_): WT_, (WT_, WB_): WT_, (WT_, WP_): WP_,
    (WB_, UC_): UC_, (WB_, UCM_): UC_, (WB_, WC_): WC_, (WB_, WT_): WT_, (WB_, WB_): WB_, (WB_, WP_): WP_,
    (WP_, UC_): UC_, (WP_, UCM_): WC_, (WP_, WC_): WC_, (WP_, WT_): WT_, (WP_, WB_): WP_, (WP_, WP_): WP_,
}
# Xen xen/arch/x86/hvm/mtrr.c mm_type_tbl, transcribed separately as a cross-check
# (row = MTRR, column = PAT index 0..7, None = reserved encoding).
XEN = {UC_: [UC_, WC_, None, None, UC_, UC_, UC_, UC_],
       WC_: [UC_, WC_, None, None, UC_, UC_, WC_, WC_],
       WT_: [UC_, WC_, None, None, WT_, WP_, WT_, UC_],
       WP_: [UC_, WC_, None, None, WT_, WP_, WP_, WC_],
       WB_: [UC_, WC_, None, None, WT_, WP_, WB_, UC_]}


def ct_call(lib, name, words, *args, out_words=1):
    mem, out = Mem(max(1, len(words))), Mem(out_words, 0x6666)
    mem.set(words)
    status = lib.call(name, *[mem.addr if a == 'in' else out.addr if a == 'out' else a for a in args])
    assert mem.guards_ok() and out.guards_ok() and mem.get()[:len(words)] == list(words)
    return status, out.get()


def verify_types(lib):
    rnd = random.Random(3)
    kinds = [UC_, WC_, WT_, WP_, WB_, UCM_]
    for n in range(400):
        pat = sum(rnd.choice(kinds) << (8 * i) for i in range(8))
        for bits in range(8):
            status, out = ct_call(lib, 'p2_ct_page_type', [], pat, bits, 'out')
            index = ((bits >> 2) & 1) * 4 + ((bits >> 1) & 1) * 2 + (bits & 1)
            assert status == CT_OK and out == [(pat >> (8 * index)) & 255], (hex(pat), bits, out)
    status, out = ct_call(lib, 'p2_ct_page_type', [], DEFAULT_PAT, 6, 'out')
    assert status == CT_OK and out == [(DEFAULT_PAT >> 48) & 255]
    for bad in (DEFAULT_PAT | (2 << 16), DEFAULT_PAT | (3 << 40), DEFAULT_PAT | (8 << 56), DEFAULT_PAT ^ (0xFF << 8)):
        valid = all(((bad >> (8 * i)) & 255) in kinds for i in range(8))
        assert lib.call('p2_ct_pat_valid', bad) == int(valid), hex(bad)
        status, out = ct_call(lib, 'p2_ct_page_type', [], bad, 0, 'out')
        assert (status == CT_OK) == valid and (valid or out == [0x6666]), hex(bad)
    assert ct_call(lib, 'p2_ct_page_type', [], DEFAULT_PAT, 8, 'out') == (CT_INVALID, [0x6666])
    # MTRR resolution against the model, including conflicts
    seen = set()
    for n in range(1500):
        ranges = []
        for _ in range(rnd.randrange(0, 5)):
            size = 1 << rnd.randrange(12, 16)
            ranges.append((rnd.randrange(0, 8) * size, size, rnd.choice([UC_, WC_, WT_, WP_, WB_])))
        default = rnd.choice([UC_, WC_, WT_, WP_, WB_])
        phys = rnd.randrange(0, 1 << 17)
        words = [w for r in ranges for w in r]
        status, out = ct_call(lib, 'p2_ct_mtrr', words, 'in', len(ranges), default, phys, 'out')
        expect, kind = model_range_type(ranges, default, phys)
        assert status == expect, (ranges, default, phys, status, expect)
        assert out == ([kind] if expect == CT_OK else [0x6666]), (out, kind)
        seen.add((expect, kind))
    assert (CONFLICT, None) in seen and (CT_OK, WT_) in seen and (CT_OK, UC_) in seen, seen
    for words, default in [([0x1000, 0x1000, UCM_], WB_), ([0, 0, WB_], WB_), ([0, 0x3000, WB_], WB_),
                           ([0x1000, 0x2000, WB_], WB_), ([0x800, 0x1000, WB_], WB_), ([0, 0x1000, WB_], UCM_),
                           ([MAX - 0xFFF, 1 << 12, WB_], WB_)]:
        assert ct_call(lib, 'p2_ct_mtrr', words, 'in', 1, default, 0, 'out') == (CT_INVALID, [0x6666]), words
    # one type per frame
    status, out = ct_call(lib, 'p2_ct_aliases', [WB_, WB_, WB_], 'in', 3, 'out')
    assert (status, out) == (CT_OK, [0x6666])
    status, out = ct_call(lib, 'p2_ct_aliases', [WB_, WB_, WC_, UC_], 'in', 4, 'out')
    assert (status, out) == (CONFLICT, [2])
    assert ct_call(lib, 'p2_ct_aliases', [WB_, WT_], 'in', 2, 'out')[0] == CONFLICT
    assert ct_call(lib, 'p2_ct_aliases', [WB_, 9], 'in', 2, 'out')[0] == CT_INVALID
    assert ct_call(lib, 'p2_ct_aliases', [], 'in', 0, 'out') == (CT_OK, [0x6666])
    # PAT x MTRR effective type: all 30 cells of SDM Table 14-7
    assert len(SDM_14_7) == 30
    for (mtrr, pat), expect in SDM_14_7.items():
        assert XEN[mtrr][pat] == expect, ('transcriptions disagree', mtrr, pat)
        status, out = ct_call(lib, 'p2_ct_effective', [], mtrr, pat, 'out')
        assert (status, out) == (CT_OK, [expect]), (mtrr, pat, status, out, expect)
    for mtrr, pat in [(UCM_, WB_), (2, WB_), (WB_, 2), (WB_, 3), (8, 0), (WB_, 8)]:
        assert ct_call(lib, 'p2_ct_effective', [], mtrr, pat, 'out') == (CT_INVALID, [0x6666]), (mtrr, pat)
    assert lib.call('p2_ct_effective', WB_, WB_, 0) == CT_INVALID
    # migration order
    for old in kinds:
        for new in kinds:
            steps, count = Mem(10, 0x4444), Mem(1, 0x5555)
            status = lib.call('p2_ct_migrate', old, new, steps.addr, 5, count.addr)
            assert steps.guards_ok() and count.guards_ok()
            if old == new:
                assert (status, count.get(), steps.get()) == (CT_OK, [0], [0x4444] * 10)
            else:
                assert status == CT_OK and count.get() == [5]
                assert steps.get() == [1, 0, 2, 0, 3, old, 4, new, 2, 0], steps.get()
            short, count = Mem(8, 0x4444), Mem(1, 0x5555)
            status = lib.call('p2_ct_migrate', old, new, short.addr, 4, count.addr)
            assert (status == CT_CAPACITY) == (old != new) and count.get() == ([0x5555] if old != new else [0])
            assert old == new or short.get() == [0x4444] * 8
    assert lib.call('p2_ct_migrate', 3, WB_, Mem(10).addr, 5, Mem(1).addr) == CT_INVALID


class P2ExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest('native P2 extension checks require NASM and GCC')
        cls.dir = Path(tempfile.mkdtemp(prefix='p2-ext-'))
        cls.sources = {m: hashlib.sha256((ROOT / 'kernel/mm' / (m + '.dg')).read_bytes()).hexdigest() for m in MODULES}
        cls.libs = {mode: build(cls.dir, ROOT, 'good', mode, cls.cc, cls.nasm) for mode in ('debug', 'release')}

    @classmethod
    def tearDownClass(cls):
        after = {m: hashlib.sha256((ROOT / 'kernel/mm' / (m + '.dg')).read_bytes()).hexdigest() for m in MODULES}
        assert after == cls.sources, 'sources changed during the test'
        shutil.rmtree(cls.dir, ignore_errors=True)   # loaded DLLs cannot be removed on Windows

    def each_mode(self, check):
        for mode, lib in self.libs.items():
            with self.subTest(mode=mode):
                check(lib)

    def test_huge_page_split_merge(self):
        self.each_mode(verify_huge)

    def test_cross_alias_wx_and_revoke_order(self):
        self.each_mode(verify_alias)

    def test_memory_types_mtrr_aliases_and_migration(self):
        self.each_mode(verify_types)

    def test_wrong_dong_implementations_are_rejected(self):
        """Each mutant compiles, links and runs normally; only the checks may catch it."""
        mutants = [
            ('raw-pat-bit', 'huge_page_plan', ' if (pde&PDE_PAT)!=0{template=template|PTE_PAT;}\n', '', verify_huge),
            ('merge-no-contiguity', 'huge_page_plan', '(table[i]&PTE_ADDRESS)!=start+(i as u64)*4096', 'false', verify_huge),
            ('merge-drops-dirty', 'huge_page_plan', 'touched=touched|(table[i]&(ACCESSED|DIRTY));', 'touched=touched|(table[i]&ACCESSED);', verify_huge),
            ('alias-ignores-cross-alias',
             'alias_policy', 'if a.frame==b.frame{', 'if a.frame==b.frame&&a.space==b.space{', verify_alias),
            ('alias-no-shootdown', 'alias_policy', 'if cpus>1{steps[n]=Step{kind:SHOOTDOWN,index:0};n+=1;}', '', verify_alias),
            ('mtrr-no-uc-priority', 'cache_type_plan', 'if (seen&(1<<UC))!=0{result=UC;}\n  else if', 'if false{result=UC;}\n  else if', verify_types),
            ('effective-wt-wp-takes-minimum', 'cache_type_plan', ' else{result=pat;}', ' else if mtrr<pat{result=mtrr;}else{result=pat;}', verify_types),
            ('effective-uc-minus-ignores-wp', 'cache_type_plan', 'if mtrr==WC||mtrr==WP{result=WC;}', 'if mtrr==WC{result=WC;}', verify_types),
            ('migrate-no-cache-flush', 'cache_type_plan', 'steps[2]=Step{kind:FLUSH_CACHE,arg:old_kind};', 'steps[2]=Step{kind:FLUSH_TLB,arg:0};', verify_types),
        ]
        for name, module, old, new, check in mutants:
            root = self.dir / name
            shutil_tree(ROOT / 'kernel', root / 'kernel')
            target = root / 'kernel/mm' / (module + '.dg')
            text = target.read_text(encoding='utf-8')
            self.assertEqual(text.count(old), 1, name)
            target.write_text(text.replace(old, new, 1), encoding='utf-8')
            for mode in ('debug', 'release'):
                lib = build(self.dir, root, name, mode, self.cc, self.nasm)
                with self.subTest(mutant=name, mode=mode):
                    with self.assertRaises(AssertionError):
                        check(lib)


def shutil_tree(src, dst):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__'))


if __name__ == '__main__':
    unittest.main()
