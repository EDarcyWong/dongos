"""Explicit read-only guest gate for the post-scheduler WB large-page owner.

Default verifies a real completed build only. --execute starts two fresh boots;
--replay rewalks archived physical bytes. No guest memory/register writes.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time
import uuid
from tests import p2_runtime_large_build as build
from tests import run_p2_pcid_qemu as pcid
from tests import p2_pcid_oracle as raw
from tools.elf_symbols import read_elf_symbols
from tools.make_fat32_disk import create
from tools.kernel_storage_profile import verify_profile

ROOT = build.ROOT
check, sha, write = build.check, build.sha, build.write
OLD, NEW, LENGTH = 0xffffa80000000000, 0xffffa80000200000, 0x200000
TAG, NX = 0x1122334400000000, 1 << 63
FIELDS = ('version attempted complete poison error_code operation steps state root physical online root_count '
          'tables_before tables_after pre_sequence post_sequence barriers retired reclaimed reader_sequence '
          'reader_round expected old_checksum final_checksum merge_error old_entry new_entry roots_pointer readers_pointer').split()
LEGACY_OBSERVATION = 'legacy-idle-v1'
KERNEL_OBSERVATION = 'current-kernel-v2'
PCID_LOCK_FREE = raw.LOCK_FREE
PCID_CURRENT_OWNER = raw.CURRENT_OWNER


def observation_profile(value=LEGACY_OBSERVATION, *, negative=False):
    check(value in (LEGACY_OBSERVATION, KERNEL_OBSERVATION), 'unknown normal observation profile')
    check(not negative or value == LEGACY_OBSERVATION, 'current-kernel-v2 is normal-only')
    return value


def require_pcid_observation_profile(value=PCID_LOCK_FREE, *, negative=False):
    """Select the later PCID contract independently of the B checkpoint."""
    return raw.require_observation_profile(value, negative=negative)


def saved_pcid_observation_profile(result, *, requested=None):
    """Reject mixed archives before consulting build inputs or physical data."""
    check(type(result) is dict and type(result.get('boots', [])) is list, 'invalid saved PCID profile envelope')
    negative = result.get('negative')
    profile = require_pcid_observation_profile(result.get('pcid_observation_profile', PCID_LOCK_FREE), negative=negative)
    if requested is not None:
        check(require_pcid_observation_profile(requested, negative=negative) == profile,
              'replay PCID observation profile differs from saved result')
    if 'seal' in result:
        seal = result['seal']
        check(type(seal) is dict and type(seal.get('boots', [])) is list, 'invalid saved PCID seal envelope')
        check(require_pcid_observation_profile(seal.get('pcid_observation_profile', PCID_LOCK_FREE), negative=negative) == profile,
              'saved seal PCID observation profile differs from result')
        for sealed_boot in seal.get('boots', []):
            check(type(sealed_boot) is dict, 'invalid saved PCID boot seal envelope')
            check(require_pcid_observation_profile(sealed_boot.get('pcid_observation_profile', PCID_LOCK_FREE), negative=negative) == profile,
                  'saved boot seal PCID observation profile differs from result')
    for boot in result.get('boots', []):
        check(type(boot) is dict, 'invalid saved PCID boot envelope')
        check(require_pcid_observation_profile(boot.get('pcid_observation_profile', PCID_LOCK_FREE), negative=negative) == profile,
              'boot PCID observation profile differs from result')
        if 'pcid_snapshot' in boot:
            check(not negative, 'negative cannot include a later PCID snapshot')
            check(type(boot['pcid_snapshot']) is dict, 'invalid saved PCID snapshot envelope')
            check(require_pcid_observation_profile(boot['pcid_snapshot'].get('observation_profile', PCID_LOCK_FREE)) == profile,
                  'snapshot PCID observation profile differs from result')
    return profile


def parse_kernel_registers(text):
    """Extend the actual archived HMP parser locally; v1 needs no RFL field."""
    matches = re.findall(r'\bRFL=([0-9a-fA-F]{8,16})(?=\s|$)', text)
    check(len(re.findall(r'\bRFL=', text)) == len(matches) == 1,
          'missing/duplicate or malformed actual register RFL')
    registers = raw.parse_registers(text)
    registers['RFL'] = int(matches[0], 16)
    return registers


def elf_bytes(esp, address, maximum=64):
    image = (Path(esp).parent / 'kernel.elf').read_bytes()
    offset = struct.unpack_from('<Q', image, 32)[0]
    stride, count = struct.unpack_from('<HH', image, 54)
    for index in range(count):
        kind, flags, start, va, _, length, _, _ = struct.unpack_from('<II6Q', image, offset + index * stride)
        if kind == 1 and flags & 1 and va <= address < va + length:
            size = min(maximum, va + length - address)
            check(size >= 3, 'reader function truncated in actual ELF')
            return image[start + address - va:start + address - va + size]
    raise ValueError('actual reader code not in an executable ELF segment')


def layout_contract(esp):
    esp = Path(esp)
    production = json.loads((esp.parent / 'build-inputs.json').read_text(encoding='utf-8'))
    static_pools = verify_profile(esp.parent, production, expected_runtime=7,
                                  source_root=esp.parent.parent / 'source')
    symbols = read_elf_symbols(esp.parent / 'kernel.elf')
    manifest = json.loads((esp.parent / 'dong_layout.json').read_text(encoding='utf-8'))
    types = {t['full_name']: t for t in manifest['types']}
    names = ['mm.runtime_large.Context', 'mm.runtime_large.Report', 'mm.runtime_large.ReaderReport',
             'user.services.LargeStorage', 'user.services.LargeTicket', 'user.memory.RootSnapshot',
             'boot.memory_startup.Workspace', 'sched.multicore.Engine', 'mm.phys_buddy.Allocator',
             'mm.phys_buddy.PageMeta', 'smp.large_memory.Report', 'sched.multicore.Cpu', 'sched.multicore.Thread',
             'boot.abi.BootInfo']
    selected = {n: types[n] for n in names}
    check(types[names[1]]['size'] == 232 and types[names[2]]['size'] == 152
          and types['sched.user_domain.Domain']['size'] == 120 and types['sched.user_domain.Cpu']['size'] == 120,
          'source-bound native ABI differs')
    offsets = {n: {f['name']: f['offset'] for f in types[n]['fields']} for n in names}
    check(offsets[names[1]] == {n: i * 8 for i, n in enumerate(FIELDS)}, 'report offsets differ')
    check(types['boot.abi.BootInfo']['size'] == 160 and all(
          offsets['boot.abi.BootInfo'].get(name) == offset for name, offset in
          (('magic', 0), ('version', 8), ('size', 16), ('kernel_physical', 120))),
          'source-bound BootInfo layout ABI differs')
    return dict(types=selected, offsets=offsets, symbols=symbols, esp=str(esp), static_pools=static_pools,
        storage_symbol=symbols[pcid.storage.symbol('user.services', 'LARGE_STORAGE')],
        context_symbol=symbols[pcid.storage.symbol('user.services', 'RUNTIME_LARGE')],
        request_symbol=symbols[pcid.storage.symbol('user.services', 'LARGE_REQUESTED')],
        kernel_space=symbols[pcid.storage.symbol('boot.memory_startup', 'WORK')] + offsets['boot.memory_startup.Workspace']['space'],
        buddy=symbols[pcid.storage.symbol('boot.memory_startup', 'WORK')] + offsets['boot.memory_startup.Workspace']['allocator'],
        buddy_meta=symbols[pcid.storage.symbol('boot.memory_startup', 'WORK')] + offsets['boot.memory_startup.Workspace']['page_meta'],
        info_symbol=symbols[pcid.storage.symbol('sched.user_boot', 'INFO')])


def digest(data):
    check(len(data) == LENGTH, 'complete held block required')
    result = 0x4c41524745313601
    for (word,) in struct.iter_unpack('<Q', data):
        result ^= word
        result = ((result << 7) | (result >> 57)) & ((1 << 64) - 1)
    return result


def decode_boot_info(data):
    """Exact shared boot.abi.BootInfo: twenty little-endian 64-bit fields."""
    check(type(data) is bytes and len(data) == 160, 'actual BootInfo ABI size differs')
    words = list(struct.unpack('<20Q', data))
    check(words[:3] == [0x544f4f42474e4f44, 1, 160], 'actual BootInfo magic/version/size differs')
    return words


def decode_readers(data):
    check(len(data) == 16 * 152, 'complete sixteen reader slots required')
    readers = []
    for cpu in range(16):
        words = list(struct.unpack_from('<19Q', data, cpu * 152))
        readers.append(dict(request=words[0], ack=words[1], count=words[2],
            **{name: dict(zip(('cpu', 'root', 'cr4', 'value'), words[3 + 4 * i:7 + 4 * i]))
               for i, name in enumerate(['warm', 'replaced', 'restored', 'merged'])}))
    return readers


def validate_readers(report, readers, metrics, *, negative=False, require_pcid=False):
    check(report['online'] == 15 and len(readers) == 16 and len(metrics) == 4, 'actual four-reader topology differs')
    for cpu in range(4):
        check(metrics[cpu][5] == 0 and (cpu == 0 or all(metrics[cpu][i] > 0 for i in (0, 2, 3))),
              'AP lacked actual user switch/timer/entry before owner')
        r = readers[cpu]
        phases = ('warm', 'replaced') if negative and cpu == 1 else ('warm', 'replaced', 'restored', 'merged')
        if negative and cpu != 1:
            continue
        for name in phases:
            s = r[name]
            check(s['cpu'] == cpu and s['root'] == report['root'] and not s['cr4'] & 128
                  and s['cr4'] == metrics[cpu][18], 'load hardware CPU/raw kernel CR3/tag/CR4 differs')
            if require_pcid:
                check(s['cr4'] & (1 << 17), 'requested real PCID; fallback is not a pass')
            expected = TAG | (6 if name == 'replaced' and not negative else 5)
            check(s['value'] == expected, 'actual load did not observe the exact expected held page')
        if negative:
            check(r['request'] == 2 and r['ack'] == r['count'] == 1
                  and r['warm']['value'] == r['replaced']['value'] == TAG | 5,
                  'bad body did not retain actual A with B mapped, or incorrectly earned ACK')
        else:
            check(r['request'] == r['ack'] == r['count'] == 4, 'reader omitted/replayed one of four requests')
    check(all(r['request'] == r['ack'] == r['count'] == 0 for r in readers[4:]), 'offline reader was used')


def kernel_forest(image, metadata, space, physical, *, negative=False):
    """Independent complete retained kernel tree and held-range alias walk."""
    initialized, pool, count, base, meta, mask, nx, used = struct.unpack('<8Q', space)
    check(initialized == nx == 1 and count == 128 and len(image) == count * 4096
          and len(metadata) == count and all(x in (0, 1) for x in metadata), 'kernel Space/metadata differs')
    check(mask >= (1 << 32) - 4096 and mask <= (1 << 52) - 4096 and not mask & 4095
          and (mask + 4096) & (mask + 4095) == 0, 'hardware address mask invalid')
    reached, aliases = set(), []

    def visit(pa, level, prefix, rw=True, user=True, denied=False):
        check(base <= pa < base + len(image) and pa % 4096 == 0, 'kernel parent outside retained pool')
        index = (pa - base) // 4096
        check(index not in reached and metadata[index] == 1, 'kernel cycle/DAG/unowned table')
        reached.add(index)
        for slot, entry in enumerate(struct.unpack_from('<512Q', image, index * 4096)):
            if not entry:
                continue
            check(entry & 1, 'kernel absent entry contains bits')
            va = prefix | slot << (39 - 9 * level)
            if level == 0 and slot >= 256:
                va |= 0xffff000000000000
            writable, accessible, noexec = rw and bool(entry & 2), user and bool(entry & 4), denied or bool(entry & NX)
            if level < 3 and not entry & 128:
                check(entry & ~(mask | NX | 39) == 0, 'reserved/high hardware PA in kernel parent')
                visit(entry & mask, level + 1, va, writable, accessible, noexec)
                continue
            size, pa_leaf, cache = 4096, entry & mask, entry & 152
            if level < 3:
                check(level == 2 and not entry & 0x1fe000 and entry & ~(mask | NX | 0x10ff) == 0, 'malformed kernel huge leaf')
                size, pa_leaf, cache = LENGTH, entry & mask & ~(LENGTH - 1), entry & 0x1018
                if cache == 0x1000:
                    cache = 128
            else:
                check(entry & ~(mask | NX | 255) == 0, 'malformed kernel page leaf')
            check(cache in (0, 24, 128) and not (writable and not noexec)
                  and not (va >> 63 and accessible), 'kernel cache/WX/USER policy differs')
            if pa_leaf < physical + LENGTH and physical < pa_leaf + size:
                check(not accessible and writable and noexec and cache == 0, 'held WB/RW/NX alias changed')
                aliases.append((va, pa_leaf, size))
    visit(base, 0, 0)
    check(len(reached) == used == sum(metadata), 'kernel reachability/accounting mismatch')
    check((OLD, physical, LENGTH) in aliases, 'old sealed large mapping lost')
    if negative:
        check(len(aliases) == 513, 'replacement forest omitted leaves/aliases')
        check((NEW + 5 * 4096, physical + 6 * 4096, 4096) in aliases, 'negative did not really map B')
        expected = [(OLD, physical, LENGTH)] + [(NEW + i * 4096, physical + (6 if i == 5 else i) * 4096, 4096) for i in range(512)]
        check(sorted(aliases) == sorted(expected), 'third-party/hidden/non-WB alias in replacement')
    else:
        check(aliases == [(OLD, physical, LENGTH)], 'temporary alias remains or hidden held alias exists')
    return dict(tables=len(reached), held_aliases=len(aliases), kernel_scans=1)


class LargeGuest(pcid.PcidGuest):
    def large_snapshot(self, label):
        # Seal the actual bounded bulk/register epoch before resuming. All
        # expensive walks below use an independent historical image, never a
        # running Guest accessor or a fabricated stopped state.
        image = self.capture_image(label)
        self.resume()
        image.initialize()
        contract = layout_contract(image.esp)
        capture, parts = pcid.Capture(image), {}

        def get(name, address, length):
            data, parts[name] = capture.part(address, length, 'runtime-large ' + name)
            return data

        storage_pointer = struct.unpack('<Q', get('storage_pointer', contract['storage_symbol'], 8))[0]
        context_pointer = struct.unpack('<Q', get('context_pointer', contract['context_symbol'], 8))[0]
        get('requested', contract['request_symbol'], 1)
        check(storage_pointer > 0 and context_pointer == storage_pointer, 'large arena/context not published')
        get('storage', storage_pointer, contract['types']['user.services.LargeStorage']['size'])
        get('kernel_space', contract['kernel_space'], 64)
        space = raw.words(raw.part_bytes(parts['kernel_space'], image.snapshot_archive(), capture.pool), 8)
        get('kernel_meta', space[4], space[2])
        allocator = get('buddy', contract['buddy'], contract['types']['mm.phys_buddy.Allocator']['size'])
        old_symbol = contract['symbols'][pcid.storage.symbol('smp.large_memory', 'REPORT')]
        old_type = json.loads((image.esp.parent / 'dong_layout.json').read_text())['types']
        old_type = next(t for t in old_type if t['full_name'] == 'smp.large_memory.Report')
        old = get('old_report', old_symbol, old_type['size'])
        physical = struct.unpack_from('<Q', old, 7 * 8)[0]
        check(physical > 0 and physical % LENGTH == 0, 'old held block absent')
        ao = contract['offsets']['mm.phys_buddy.Allocator']
        base = struct.unpack_from('<Q', allocator, ao['base'])[0]
        meta_pointer = struct.unpack_from('<Q', allocator, ao['metadata'])[0]
        check(physical >= base, 'held block precedes buddy arena')
        get('held_meta', meta_pointer + (physical - base) // 4096 * contract['types']['mm.phys_buddy.PageMeta']['size'],
            512 * contract['types']['mm.phys_buddy.PageMeta']['size'])
        _, payload = capture.physical(physical, LENGTH, 'complete unchanged old held block ' + label)
        _, kernel_pool = capture.physical(capture.pool[0], capture.pool[1] * 4096, 'complete retained kernel pool ' + label)
        info = struct.unpack('<Q', get('boot_info_pointer', contract['info_symbol'], 8))[0]
        boot = raw.words(get('boot_report', info, 80), 10)
        domain = raw.words(get('domain', boot[5], 120), 15)
        get('cpus', domain[11], 16 * 120)
        get('processes', domain[12], 16 * 56)
        get('engine', domain[10], 12960)
        bridge_pointer = struct.unpack('<Q', get('bridge_pointer', contract['symbols'][pcid.storage.symbol('sched.user_bridge', 'ACTIVE')], 8))[0]
        get('bridge', bridge_pointer, 64)
        headers = raw.words(get('header_addresses', boot[6], 32), 4)
        for cpu, header in enumerate(headers):
            get('header.' + str(cpu), header, 256)
            get('metrics.' + str(cpu), header + 5632, 192)
        code = {}
        for name in ['runtime_large_environment', 'runtime_large_load', 'runtime_large_window', 'runtime_large_digest', 'runtime_large_test_omit']:
            address = contract['symbols'][name]
            expected = elf_bytes(image.esp, address)
            _, code[name] = capture.physical(image.boot[15] + address - pcid.storage.KERNEL, len(expected), 'resident reader code ' + name)
        syms = contract['symbols']
        for name, size in [('SPACES', 16 * 64), ('META', 16 * 128), ('PROCESSES', 16 * 1288),
                           ('POOL_LIMITS', 128), ('DYNAMIC_PHYSICAL', 128), ('DYNAMIC_TABLES', 128), ('GENERATIONS', 128), ('PINNED', 16)]:
            get('memory.' + name, syms[pcid.storage.symbol('user.memory', name)], size)
        catalog_pointer = struct.unpack('<Q', get('catalog_pointer', syms[pcid.storage.symbol('user.services', 'CATALOG')], 8))[0]
        get('catalog', catalog_pointer, pcid.life.CATALOG_BYTES)
        spaces = raw.part_bytes(parts['memory.SPACES'], image.snapshot_archive(), capture.pool)
        pools = {}
        for slot in range(16):
            initialized, pointer, count, physical, *_ = struct.unpack_from('<8Q', spaces, slot * 64)
            if initialized:
                check(count in (32, 128), 'unexpected actual private pool size')
                _, pools[str(slot)] = capture.physical(physical, count * 4096, 'complete memory-owned private pool ' + str(slot))
        snapshot = dict(label=label, epoch=image.epoch, parts=parts, kernel_pool=capture.pool, kernel_pool_ref=kernel_pool,
                        user_pools=pools, payload=payload, registers=[image.register_ref(cpu) for cpu in range(4)],
                        boot_info_ref=image.boot_info_ref, code=code, serial_offset=image.serial_offset)
        profile = getattr(self, 'normal_observation_profile', LEGACY_OBSERVATION)
        if profile == LEGACY_OBSERVATION:
            return snapshot, decode(snapshot, image.archive(), contract)
        return snapshot, decode(snapshot, image.archive(), contract, normal_observation_profile=profile)


def decode(snapshot, archive, contract, *, normal_observation_profile=LEGACY_OBSERVATION):
    profile = observation_profile(normal_observation_profile)
    archive.begin_snapshot(snapshot['epoch'])
    check(type(snapshot.get('serial_offset')) is int and snapshot['serial_offset'] == archive.snapshot_serial_offset,
          'runtime-large serial boundary differs from sealed capture epoch')
    pool = snapshot['kernel_pool']
    check(pool[1] == 128 and snapshot['kernel_pool_ref']['physical'] == pool[0]
          and snapshot['kernel_pool_ref']['length'] == pool[1] * 4096, 'kernel pool provenance differs')
    image = archive.read(snapshot['kernel_pool_ref'])
    private = {int(n): archive.read(ref) for n, ref in snapshot['user_pools'].items()}
    archive.pool_images = [(pool[0], image)] + [(snapshot['user_pools'][str(n)]['physical'], data) for n, data in private.items()]
    p = snapshot['parts']
    get = lambda name: raw.part_bytes(p[name], archive, pool)
    check(p['storage_pointer']['virtual'] == contract['storage_symbol']
          and p['context_pointer']['virtual'] == contract['context_symbol'], 'owner pointer not source-bound')
    check(p['requested']['virtual'] == contract['request_symbol'] and get('requested') in (b'\0', b'\1'),
          'production request flag is not source-bound')
    pointer = raw.words(get('storage_pointer'), 1)[0]
    check(raw.words(get('context_pointer'), 1)[0] == pointer and p['storage']['virtual'] == pointer, 'large arena pointer differs')
    data = get('storage')
    sizes, offsets = contract['types'], contract['offsets']
    check(len(data) == sizes['user.services.LargeStorage']['size'], 'incomplete owner arena')
    co = offsets['mm.runtime_large.Context']
    report = dict(zip(FIELDS, struct.unpack_from('<29Q', data, co['report'])))
    readers = decode_readers(data[co['readers']:co['readers'] + 16 * 152])
    if report['attempted']:
        check(report['roots_pointer'] == pointer + co['roots'] and report['readers_pointer'] == pointer + co['readers'], 'owner root/reader pointers not in the actual arena')
    space = get('kernel_space')
    check(p['kernel_space']['virtual'] == contract['kernel_space'] and raw.words(space, 8)[3] == pool[2] == pool[0], 'kernel Space/root not bound')
    old = raw.words(get('old_report'), len(get('old_report')) // 8)
    physical = old[7]
    check(snapshot['payload']['physical'] == physical and snapshot['payload']['length'] == LENGTH, 'held bytes not tied to old owner')
    payload = archive.read(snapshot['payload'])
    check(old[1:3] == [1, 1] and old[9] == 9 and old[8] == 512, 'old large owner incomplete')
    old_fields = contract['offsets']['smp.large_memory.Report']
    for field in ['held', 'sealed', 'complete']:
        check(struct.unpack_from('<Q', get('old_report'), old_fields[field])[0] == 1, 'old owner lost seal/lease')
    check(p['buddy']['virtual'] == contract['buddy'], 'buddy allocator not source-bound')
    allocator = get('buddy');ao = contract['offsets']['mm.phys_buddy.Allocator']
    number = lambda name: struct.unpack_from('<Q', allocator, ao[name])[0]
    count, base, metadata = number('page_count'), number('base'), number('metadata')
    check(allocator[ao['initialized']] == 1 and 0 < count <= 1 << 20 and count & (count - 1) == 0
          and metadata == contract['buddy_meta'] and physical >= base and physical - base <= count * 4096 - LENGTH
          and (physical - base) % LENGTH == 0, 'held allocation is not inside its actual buddy arena')
    mo = contract['offsets']['mm.phys_buddy.PageMeta'];stride = contract['types']['mm.phys_buddy.PageMeta']['size']
    check(p['held_meta']['virtual'] == metadata + (physical - base) // 4096 * stride, 'allocated metadata head address differs')
    meta_bytes = get('held_meta')
    check(len(meta_bytes) == 512 * stride, 'allocated block tails omitted')
    for page in range(512):
        at = page * stride
        check(meta_bytes[at + mo['state']] == (2 if page == 0 else 3)
              and meta_bytes[at + mo['order']] == (9 if page == 0 else 0)
              and struct.unpack_from('<Q', meta_bytes, at + mo['next'])[0] == (1 << 64) - 1,
              'buddy allocated head/tail ownership lost')
    domain = raw.words(get('domain'), 15)
    check(p['boot_info_pointer']['virtual'] == contract['info_symbol'], 'boot pointer not source-bound')
    boot_pointer = raw.words(get('boot_info_pointer'), 1)[0]
    check(p['boot_report']['virtual'] == boot_pointer, 'boot report pointer redirected')
    boot = raw.words(get('boot_report'), 10)
    check(boot[:5] == [1, 0, 1, 4, 15] and boot[8] == pool[2] and p['domain']['virtual'] == boot[5]
          and p['cpus']['virtual'] == domain[11] and p['processes']['virtual'] == domain[12]
          and p['engine']['virtual'] == domain[10] and p['header_addresses']['virtual'] == boot[6], 'boot/Domain/pool provenance differs')
    if report['attempted']:
        check(struct.unpack_from('<Q', data, co['domain'])[0] == boot[5], 'owner domain differs from actual boot')
        check(struct.unpack_from('<Q', data, co['space'])[0] == contract['kernel_space']
              and struct.unpack_from('<Q', data, co['allocator'])[0] == contract['buddy'], 'owner Space/allocator pointers differ')
        for field, symbol in [('hardware', 'runtime_large_environment'), ('load', 'runtime_large_load'),
                              ('window', 'runtime_large_window'), ('digest', 'runtime_large_digest')]:
            check(struct.unpack_from('<Q', data, co[field])[0] == contract['symbols'][symbol], 'owner callback not bound to actual reader ASM')
        check_symbol = '__dg_m' + 'user.services'.encode().hex() + '_f' + 'large_check'.encode().hex()
        check(struct.unpack_from('<Q', data, co['check'])[0] == contract['symbols'][check_symbol]
              and struct.unpack_from('<Q', data, co['cookie'])[0] == pointer + offsets['user.services.LargeStorage']['ticket'], 'trusted recheck callback/cookie differs')
    headers = raw.words(get('header_addresses'), 4)
    cpus = [raw.words(get('cpus')[i * 120:(i + 1) * 120], 15) for i in range(16)]
    metrics = [raw.words(get('metrics.' + str(i)), 24) for i in range(4)]
    registers = []
    check([r['cpu_index'] for r in snapshot['registers']] == list(range(4)), 'CPU register set differs')
    for ref in snapshot['registers']:
        text = archive.text(ref)
        registers.append(parse_kernel_registers(text) if profile == KERNEL_OBSERVATION else raw.parse_registers(text))
    for cpu in range(4):
        check(p['header.' + str(cpu)]['virtual'] == headers[cpu]
              and p['metrics.' + str(cpu)]['virtual'] == headers[cpu] + 5632, 'Header/metrics address redirected')
        header = raw.words(get('header.' + str(cpu)), 32)
        check(header[9] == boot[5] and header[10] == cpu and header[25] == 2
              and bool(header[13]) == bool(registers[cpu]['CR4'] & 1 << 17)
              and registers[cpu]['CR4'] == metrics[cpu][18], 'actual Header/logical CPU/PCID controls differ')
    for name in ['SPACES', 'META', 'PROCESSES', 'POOL_LIMITS', 'DYNAMIC_PHYSICAL', 'DYNAMIC_TABLES', 'GENERATIONS', 'PINNED']:
        check(p['memory.' + name]['virtual'] == contract['symbols'][pcid.storage.symbol('user.memory', name)], 'memory input not source-bound: ' + name)
    check(p['catalog_pointer']['virtual'] == contract['symbols'][pcid.storage.symbol('user.services', 'CATALOG')]
          and p['catalog']['virtual'] == raw.words(get('catalog_pointer'), 1)[0], 'Catalog pointer not bound to source')
    check(p['bridge_pointer']['virtual'] == contract['symbols'][pcid.storage.symbol('sched.user_bridge', 'ACTIVE')]
          and p['bridge']['virtual'] == raw.words(get('bridge_pointer'), 1)[0], 'Bridge pointer not source-bound')
    bridge = raw.words(get('bridge'), 8)
    check(bridge[0] == 1 and bridge[2] == boot[5] and bridge[4] == boot[6], 'actual Bridge/domain/header set differs')
    boot_words = decode_boot_info(archive.read(snapshot['boot_info_ref']))
    code_names = ['runtime_large_environment', 'runtime_large_load', 'runtime_large_window', 'runtime_large_digest', 'runtime_large_test_omit']
    check(set(snapshot['code']) == set(code_names), 'resident reader code omitted')
    for name in code_names:
        address = contract['symbols'][name];expected = elf_bytes(contract['esp'], address)
        ref = snapshot['code'][name]
        check(ref['physical'] == boot_words[15] + address - pcid.storage.KERNEL and ref['length'] == len(expected)
              and archive.read(ref) == expected, 'resident kernel reader code bytes differ from the actual built ELF')
        def table(pa):
            check(pool[0] <= pa <= pool[0] + len(image) - 4096, 'resident code ancestor escaped retained pool')
            return image[pa - pool[0]:pa - pool[0] + 4096]
        remaining, virtual, consumed = len(expected), address, 0
        while remaining:
            m = pcid.life.fat.effective_mapping(pool[2], virtual, table, (pool[0], pool[1]))
            check(m['present'] and not m['effective_user'] and not m['effective_writable'] and not m['effective_nx']
                  and m['leaf_bytes'] == 4096 and m['physical'] == ref['physical'] + consumed,
                  'resident reader code is not actual supervisor RX mapping')
            size = min(remaining, 4096 - (virtual & 4095));remaining -= size;virtual += size;consumed += size
    for slot in range(16):
        space_raw = get('memory.SPACES')[slot * 64:(slot + 1) * 64]
        if space_raw[0]:
            count, root = struct.unpack_from('<2Q', space_raw, 16)
            check(slot in private and snapshot['user_pools'][str(slot)]['physical'] == root
                  and len(private[slot]) == count * 4096, 'complete private pool omitted')
            raw.audit_pool(private[slot], get('memory.META')[slot * 128:(slot + 1) * 128],
                space_raw, root, count, image, 0)
            hardware_mask = struct.unpack_from('<Q', space, 40)[0]
            for page in range(count):
                if get('memory.META')[slot * 128 + page]:
                    check(all(not (e & raw.MASK & ~hardware_mask) for e in struct.unpack_from('<512Q', private[slot], page * 4096)),
                          'private pool/parent/leaf exceeds actual hardware PA width')
        else:
            check(slot not in private and space_raw == bytes(64), 'absent private root was damaged/hidden')
    return dict(synthetic=archive.legacy_fixture, epoch=snapshot['epoch'],
        report=report, readers=readers, domain=domain, cpus=cpus, metrics=metrics,
        registers=registers, header_addresses=headers, data=data, pointer=pointer, payload=payload, physical=physical,
        kernel_image=image, kernel_meta=get('kernel_meta'), kernel_space=space, get=get,
        private=private, old_report=old, boot_info=boot_words, bridge=bridge, requested=get('requested') == b'\1',
        catalog=raw.catalog(get('catalog')))


def audit_queue(image, contract):
    """Complete raw intrusive queues, RUNNING owners and blocked membership."""
    eo = contract['offsets']['sched.multicore.Engine']
    cs = contract['types']['sched.multicore.Cpu']['size']
    ts = contract['types']['sched.multicore.Thread']['size']
    ready, online, sequence, total = struct.unpack_from('<4Q', image)
    check(ready == 1 and online == 15 and total <= 64, 'queue engine header differs')
    cpus = [raw.words(image[eo['cpus'] + i * cs:eo['cpus'] + (i + 1) * cs], cs // 8) for i in range(16)]
    threads = [raw.words(image[eo['threads'] + i * ts:eo['threads'] + (i + 1) * ts], ts // 8) for i in range(64)]
    seen = set()
    for cpu, c in enumerate(cpus):
        current, ready_count, bitmap, cursor, dispatches = c[:5]
        check(current <= 64 and cursor < 16, 'invalid queue CPU cursor/current')
        if not online & (1 << cpu):
            check(current == 64 and ready_count == bitmap == 0, 'offline CPU owns queue state')
        if current != 64:
            check(current not in seen and threads[current][0] == 2 and threads[current][3] == cpu, 'RUNNING queue owner differs')
            seen.add(current)
        count = bits = 0
        for priority in range(32):
            head, tail = c[5 + priority], c[37 + priority]
            check(head <= 64 and tail <= 64 and (head == 64) == (tail == 64), 'queue head/tail differs')
            if head != 64:
                bits |= 1 << priority
            node, previous = head, 64
            while node != 64:
                check(node < 64 and node not in seen, 'queue cycle/duplicate ownership')
                seen.add(node)
                t = threads[node]
                check(t[0] == 1 and t[1] == priority and t[3] == cpu and t[5] == previous, 'intrusive ready queue differs')
                count += 1;previous, node = node, t[4]
            check(previous == tail, 'queue tail differs')
        check(count == ready_count and bits == bitmap, 'queue counts/bitmap differ')
    active = 0
    for slot, t in enumerate(threads):
        state, priority, affinity, cpu, nxt, prev, generation, frame = t
        check(generation <= (1 << 56) - 1, 'queue generation overflow')
        if not state:
            check(slot not in seen and [priority, affinity, cpu, nxt, prev, frame] == [0, 0, 16, 64, 64, 0], 'UNUSED queue node differs')
        else:
            active += 1
            check(state <= 3 and priority < 32 and generation > 0 and frame > 0 and frame % 8 == 0
                  and affinity > 0 and not affinity & ~online and cpu < 16 and affinity & (1 << cpu), 'invalid active queue node')
            check((slot in seen) == (state != 3), 'blocked/ready/RUNNING membership differs')
            if state == 3:
                check(nxt == prev == 64, 'blocked queue node remains linked')
    check(active == total, 'queue active count differs')
    return threads


def validate_authority(decoded, contract):
    """Recompute the complete memory/Catalog/Domain ticket from raw storage."""
    d, data, get = decoded['domain'], decoded['data'], decoded['get']
    offsets = contract['offsets']
    ticket = offsets['user.services.LargeStorage']['ticket']
    to, so = offsets['user.services.LargeTicket'], offsets['user.memory.RootSnapshot']
    snapshot = ticket + to['snapshot']
    count, mask = struct.unpack_from('<2Q', data, snapshot)
    current_spaces = get('memory.SPACES')
    live = [i for i in range(16) if current_spaces[i * 64]]
    check(count == len(live) == decoded['report']['root_count'] and mask == sum(1 << i for i in live), 'complete memory roots omitted')
    context_roots = offsets['mm.runtime_large.Context']['roots']
    generations = raw.words(get('memory.GENERATIONS'), 16)
    spaces_symbol = contract['symbols'][pcid.storage.symbol('user.memory', 'SPACES')]
    limits = raw.words(get('memory.POOL_LIMITS'), 16)
    dynamic = raw.words(get('memory.DYNAMIC_PHYSICAL'), 16)
    dynamic_ptr = raw.words(get('memory.DYNAMIC_TABLES'), 16)
    static = decoded['boot_info'][15] + contract['symbols'][pcid.storage.symbol('user.memory', 'TABLES')] - pcid.storage.KERNEL
    catalog = raw.catalog(get('catalog'))
    process_raw, domains = get('memory.PROCESSES'), get('processes')
    for index, slot in enumerate(live):
        expected = (spaces_symbol + slot * 64, slot, generations[slot])
        check(struct.unpack_from('<3Q', data, snapshot + so['roots'] + index * 24) == expected
              and struct.unpack_from('<3Q', data, context_roots + index * 24) == expected, 'root identity/memory generation mismatch')
        root = struct.unpack_from('<Q', current_spaces, slot * 64 + 24)[0]
        check(struct.unpack_from('<Q', data, snapshot + so['pool'] + slot * 8)[0] == root
              and struct.unpack_from('<Q', data, snapshot + so['pages'] + slot * 8)[0] == limits[slot], 'snapshot pool identity differs')
        check(struct.unpack_from('<2Q', process_raw, slot * 1288) == (1, root)
              and struct.unpack_from('<Q', process_raw, slot * 1288 + 16 + 18 * 8)[0] == root, 'memory Frame CR3/root differs')
        validate_pool_provenance(slot, root, struct.unpack_from('<Q', current_spaces, slot * 64 + 8)[0],
                                 limits[slot], dynamic[slot], dynamic_ptr[slot], static,
                                 contract['symbols'][pcid.storage.symbol('user.memory', 'TABLES')],
                                 static_pools=contract['static_pools'])
    threads = audit_queue(get('engine'), contract)
    owners = set()
    for slot in range(16):
        ready, root = struct.unpack_from('<2Q', process_raw, slot * 1288)
        check(struct.unpack_from('<Q', data, snapshot + so['ready'] + slot * 8)[0] == ready
              and struct.unpack_from('<Q', data, snapshot + so['pinned'] + slot * 8)[0] == get('memory.PINNED')[slot]
              and struct.unpack_from('<Q', data, snapshot + so['pages'] + slot * 8)[0] == limits[slot]
              and struct.unpack_from('<Q', data, snapshot + so['pool'] + slot * 8)[0] == (root if slot in live else 0), 'snapshot readiness/pinning/pool capacity differs')
        cfg, inc = catalog['configurations'][slot], catalog['incarnations'][slot]
        array = lambda name: struct.unpack_from('<Q', data, ticket + to[name] + slot * 8)[0]
        check(array('configuration') == cfg and array('incarnation') == inc, 'Catalog config/incarnation changed')
        process = raw.words(domains[slot * 56:(slot + 1) * 56], 7)
        expected_frame = contract['symbols'][pcid.storage.symbol('user.memory', 'PROCESSES')] + slot * 1288 + 16
        check(array('frame') == expected_frame and array('root') == root, 'ticket frame/root not the actual memory.Process')
        check(array('queue_token') == process[0], 'Domain queue token changed')
        if cfg != (1 << 64) - 1:
            state = catalog['snapshots'][cfg]
            check(array('owner') == state['process'] == (inc << 8 | slot + 1)
                  and array('config_generation') == state['generation'], 'Catalog owner/restart generation differs')
        else:
            check(array('owner') == array('config_generation') == 0, 'preloaded root invented a Catalog owner')
        if process[0]:
            root = struct.unpack_from('<Q', process_raw, slot * 1288 + 8)[0]
            check(cfg != (1 << 64) - 1 and process[1:3] == [inc, root] and process[5:] == [0, 0]
                  and process[3] == expected_frame and process[2] == array('root') and threads[slot][7] == expected_frame
                  and process[4] == contract['symbols'][pcid.storage.symbol('user.services', 'XSTATES')] + slot * 1024
                  and threads[slot][6] == process[0] >> 8 and process[0] & 255 == slot + 1,
                  'Domain Process was not bound to this live memory/Catalog identity')
    for cpu, c in enumerate(decoded['cpus'][:4]):
        if c[1]:
            check(c[3] < 16 and c[3] not in owners, 'duplicate/invalid CPU process owner')
            owners.add(c[3]);p = raw.words(domains[c[3] * 56:(c[3] + 1) * 56], 7)
            check(c[1:3] == p[:2] and threads[c[3]][0] == 2 and threads[c[3]][3] == cpu, 'CPU/queue root incarnation differs')
    check({i for i in range(16) if threads[i][0] == 2} == owners, 'RUNNING token lacks exactly one CPU owner')


def validate_pool_provenance(slot, root, pointer, pages, dynamic, dynamic_pointer, static, tables, *, static_pools):
    check(type(static_pools) is int and 0 < static_pools <= 16, 'unbound static pool count')
    if slot < static_pools:
        check(pages == 32 and root == static + slot * 32 * 4096 and pointer == tables + slot * 32 * 4096
              and dynamic == dynamic_pointer == 0, 'static pool physical provenance differs')
    else:
        check(root == dynamic and root > 0 and root % 4096 == 0 and dynamic_pointer > 0
              and dynamic_pointer % 4096 == 0 and pages == (128 if slot == 3 else 32)
              and pointer == dynamic_pointer, 'dynamic pool provenance differs')


def validate_kernel_barrier_controls(decoded, *, require_pcid=False):
    """A completed owner post may precede an unrelated still-pending barrier."""
    domain, report = decoded['domain'], decoded['report']
    completed, sequence, post = domain[8], domain[5], report['post_sequence']
    maximum = (1 << 64) - 1
    check(type(completed) is int and post <= completed <= maximum and type(sequence) is int,
          'current kernel owner post is not completed')
    idle = domain[2:4] == [0, 16] and sequence == completed and domain[6] == domain[7] == 0
    pending = (completed < maximum and domain[2:4] == [1, 0]
               and sequence == domain[6] == completed + 1 and sequence > post and domain[7] == report['online'])
    check(idle or pending, 'current kernel barrier is neither idle nor one later pending sequence')
    check(domain[1] == 0 and decoded['bridge'][1] == 0, 'current kernel Domain/Bridge failed')
    headers = decoded.get('header_addresses', [])
    check(len(headers) == 4 and all(type(h) is int and 0 < h <= maximum for h in headers)
          and len(set(headers)) == 4, 'current kernel source-bound Header set missing/duplicated')
    for cpu in range(4):
        state, metric, reg = decoded['cpus'][cpu], decoded['metrics'][cpu], decoded['registers'][cpu]
        request, ack = state[7:9]
        check(type(request) is int and type(ack) is int and request in (completed, sequence)
              and ack in (completed, sequence) and completed <= ack <= request
              and (pending or request == ack == completed),
              'current kernel CPU all-tag barrier acknowledgement is stale/missing/out of order')
        check(state[0] == 5 if cpu == 0 and pending else state[0] in (1, 4),
              'current kernel CPU mode is not captured IDLE/KERNEL or CPU0 LOCKED')
        check(len(metric) == 24 and metric[5] == 0, 'current kernel CPU metrics failed')
        check(reg.get('CS') == 8 and reg.get('GS_base') == headers[cpu] and reg.get('CR3') == report['root'],
              'current kernel CPU CS/GS Header/raw kernel CR3 tag0 differs')
        check(reg.get('CR4') == metric[18] and not reg['CR4'] & (1 << 7),
              'barrier CPU raw CR4 readback/PGE policy differs')
        if require_pcid:
            check(reg['CR4'] & (1 << 17), 'requested real PCID; fallback is not a pass')
        check(type(reg.get('RFL')) is int and 0 <= reg['RFL'] <= maximum, 'current kernel actual RFL missing')
        if cpu == 0 and pending or cpu > 0 and state[0] == 4:
            check(not reg['RFL'] & (1 << 9), 'current kernel locked/kernel CPU has IF set')
    return dict(owner_post_completed=True, current_barrier_pending=bool(pending),
                current_barrier_complete=not pending, completed_sequence=completed, current_sequence=sequence)


def validate_barrier_controls(decoded, *, negative=False, require_pcid=False,
                              normal_observation_profile=LEGACY_OBSERVATION):
    """Recompute the all-tag ACK independently of the reader's load ACK."""
    profile = observation_profile(normal_observation_profile, negative=negative)
    report, domain = decoded['report'], decoded['domain']
    cpus, metrics, registers = decoded['cpus'], decoded['metrics'], decoded['registers']
    check(len(domain) == 15 and len(cpus) == 16 and all(len(c) == 15 for c in cpus)
          and len(metrics) == len(registers) == 4, 'complete raw barrier controls required')
    root, pre, post = report['root'], report['pre_sequence'], report['post_sequence']
    maximum = (1 << 64) - 1
    check(type(root) is int and 0 < root <= maximum and root % 4096 == 0
          and domain[0] == 1 and domain[4] == report['online'] == 15 and domain[9] == root,
          'barrier topology/kernel root differs from actual owner')
    check(type(pre) is int and type(post) is int and 0 < pre < maximum and post == pre + 1,
          'owner pre/post barrier sequence is not one real transaction')
    if profile == KERNEL_OBSERVATION:
        return validate_kernel_barrier_controls(decoded, require_pcid=require_pcid)
    completed = domain[8]
    check(type(completed) is int and post <= completed <= maximum and domain[5] == completed
          and domain[6] == domain[7] == 0, 'current all-tag barrier is incomplete')
    if negative:
        check(completed == post and domain[1:4] == [1, 1, 0] and cpus[0][0] == 5
              and all(cpus[cpu][0] in (1, 4) for cpu in (1, 2, 3)),
              'negative did not retain exact post-barrier CPU0-held kernel modes')
    for cpu in range(4):
        check(cpus[cpu][7] == cpus[cpu][8] == completed,
              'online CPU omitted current completed all-tag barrier acknowledgement')
        reg = registers[cpu]
        check(reg['CR4'] == metrics[cpu][18] and not reg['CR4'] & (1 << 7),
              'barrier CPU raw CR4 readback/PGE policy differs')
        if require_pcid:
            check(reg['CR4'] & (1 << 17), 'requested real PCID; fallback is not a pass')
        if negative:
            check(reg['CS'] & 3 == 0 and reg['CR3'] == root,
                  'negative CPU raw kernel CR3/tag0 or privilege differs')
        elif reg['CS'] & 3 == 0:
            check(reg['CR3'] == root, 'barrier CPL0 raw kernel CR3/tag0 differs')


def validate(before, after, contract, *, negative=False, require_pcid=False,
             normal_observation_profile=LEGACY_OBSERVATION):
    profile = observation_profile(normal_observation_profile, negative=negative)
    check(before.get('synthetic') is False and after.get('synthetic') is False,
          'synthetic or unbound decoded records cannot certify actual guest loads')
    check(before['report']['attempted'] == 0, 'baseline captured after owner already ran')
    check(before['requested'] is False and after['requested'] is True, 'ordinary production request lacks a real before/after')
    check(before['physical'] == after['physical'] and before['payload'] == after['payload'], 'old held block changed byte-for-byte')
    r = after['report']
    check(r['version'] == r['attempted'] == 1 and r['physical'] == after['physical']
          and r['root'] == raw.words(after['kernel_space'], 8)[3], 'actual owner/kernel/lease identity differs')
    controls = validate_barrier_controls(after, negative=negative, require_pcid=require_pcid,
                                        normal_observation_profile=profile)
    check(r['old_checksum'] == digest(before['payload']), 'initial actual whole-window digest does not bind raw baseline')
    validate_authority(after, contract)
    forest = kernel_forest(after['kernel_image'], after['kernel_meta'], after['kernel_space'], r['physical'], negative=negative)
    validate_readers(r, after['readers'], after['metrics'], negative=negative, require_pcid=require_pcid)
    if negative:
        check(r['complete'] == 0 and r['poison'] == 1 and r['error_code'] != 0 and r['operation'] == 3
              and after['domain'][1] == 1 and after['domain'][2:4] == [1, 0], 'negative did not fail permanently held under CPU0 BKL')
        check(r['state'] == 3 and r['retired'] == r['reclaimed'] == 0, 'negative rolled back/reclaimed the replaced mapping')
        check(after['bridge'][1] == 1 and after['registers'][1]['CR3'] == r['root'], 'negative did not retain the actual poisoned Bridge/kernel root')
    else:
        check(r['complete'] == 1 and r['poison'] == r['error_code'] == r['state'] == 0 and r['steps'] == 127
              and r['barriers'] == 16 and r['retired'] == r['reclaimed'] == 2 and r['tables_before'] == r['tables_after']
              and r['final_checksum'] == r['old_checksum'], 'actual lifecycle/report incomplete')
        if profile == LEGACY_OBSERVATION:
            check(after['bridge'][1] == 0 and after['domain'][1] == after['domain'][2] == after['domain'][6] == 0
                  and after['domain'][3] == 16 and after['domain'][8] >= r['post_sequence'], 'actual all-tag barrier did not finish')
        else:
            check(controls['owner_post_completed'], 'actual owner post all-tag barrier did not finish')
    return dict(passed=True, actual_cpu_loads=True, actual_kernel_cr3_consumer=True,
        cpl3_high_half_consumer=False, old_held_bytes=LENGTH, old_held_sha256=hashlib.sha256(after['payload']).hexdigest(),
        kernel_forest=forest, negative=negative, pcid_required=require_pcid,
        normal_observation_profile=profile, observation_controls=controls)


def source_tools(esp):
    return pcid.source_tools(esp)


def launch_command(cfg):
    return 'run ' + pcid.life.NAMES[cfg] + ' ' + str(raw.ARGS[cfg])


def validate_launch_receipt(receipt, serial, cfg, *, start, end):
    command = launch_command(cfg)
    check(isinstance(receipt, dict) and receipt.get('command') == command
          and type(receipt.get('serial_offset')) is int and start <= receipt['serial_offset'] < end
          and receipt.get('command_utf8_sha256') == hashlib.sha256(command.encode()).hexdigest()
          and receipt.get('complete_echo_and_new_prompt_verified') is True
          and type(receipt.get('error_code')) is int and receipt['error_code'] == 0,
          'ordinary launch receipt is stale or names another request')
    fresh = pcid.life.fat.fresh_response(serial[receipt['serial_offset']:end], command)
    check(fresh is not None and all(receipt.get(k) == v for k, v in fresh.items()), 'launch receipt differs from actual fresh UART')
    body = bytes.fromhex(fresh['response_hex'])
    record = pcid.life.parse_record(body, 'RUN OK', pcid.life.NAMES[cfg])
    expected = ('RUN OK ' + pcid.life.NAMES[cfg] + ' token=' + str(record['token'])
                + ' generation=' + str(record['generation']) + ' state=1 status=0\r\n').encode()
    check(body == expected and record['generation'] > 0, 'ordinary launch lacks one exact committed STARTING receipt')
    return record


def validate_launch_order(boot, serial, before, after, *, negative):
    """Bind five committed launches before the one immutable LARGE checkpoint."""
    requests, trigger = boot['requests'], boot['trigger']
    checkpoint = boot['after']['serial_offset']
    check(isinstance(requests, list) and len(requests) == 5 and requests[-1] == trigger
          and {request['configuration'] for request in requests} == set(raw.ARGS)
          and type(boot['before']['epoch']) is int and type(boot['after']['epoch']) is int
          and 1 <= boot['before']['epoch'] < boot['after']['epoch']
          and all(type(v) is int for v in (checkpoint, boot['before']['serial_offset']))
          and 0 <= boot['before']['serial_offset'] <= checkpoint <= len(serial),
          'five ordinary requests/checkpoint epoch order differs')
    # Decode each Catalog under its own stop's pool image, before replay moves
    # the shared archive to the next stop. Never rewalk an old stop as new.
    old, current = before['catalog'], after['catalog']
    for cfg in range(7, 13):
        s = old['snapshots'][cfg]
        check(s['process'] == s['generation'] == s['state'] == 0, 'baseline already contains an ordinary launch')
    inactive = current['snapshots'][12]
    check(inactive['process'] == inactive['generation'] == inactive['state'] == 0,
          'LARGE after includes an unrequested ordinary launch')
    previous, launches = boot['before']['serial_offset'], []
    for index, request in enumerate(requests):
        cfg = request['configuration']
        start, end = request['serial_start'], request['serial_end']
        check(request['argument'] == raw.ARGS[cfg] and request['command'] == launch_command(cfg)
              and type(start) is int and type(end) is int and previous <= start < end <= checkpoint,
              'ordinary request serial interval is stale or overlaps another request')
        check(serial[start:end].count(launch_command(cfg).encode() + b'\r\n') == 1,
              'ordinary request lacks one fresh actual UART echo')
        member = current['snapshots'][cfg]
        check(member['process'] > 0 and member['generation'] == old['snapshots'][cfg]['generation'] + 1
              and member['state'] in (1, 2) and member['argument'] == raw.ARGS[cfg],
              'ordinary request is not its actual committed Catalog incarnation')
        if 'receipt' in request:
            record = validate_launch_receipt(request['receipt'], serial, cfg, start=start, end=end)
            check(record['token'] == member['process'] and record['generation'] == member['generation'],
                  'ordinary UART/Catalog identity differs')
            launches.append(request['receipt'])
        else:
            check(negative and index == 4 and isinstance(request.get('error'), str) and bool(request['error']),
                  'normal request failure or unbound negative request')
        previous = end
    check(boot['launches'] == launches, 'launch receipts do not match the five actual requests')
    if negative:
        check('pcid_snapshot' not in boot, 'negative must stop at the exact final-request held checkpoint')
    else:
        check(len(launches) == 5, 'five actual PCID workload launches required')


def collect_boot(guest, boot, state, esp, *, negative, require_pcid,
                 normal_observation_profile=LEGACY_OBSERVATION, pcid_observation_profile=PCID_LOCK_FREE):
    """Production pipeline, also exercised with explicit host boundary adapters."""
    profile = observation_profile(normal_observation_profile, negative=negative)
    pcid_profile = require_pcid_observation_profile(pcid_observation_profile, negative=negative)
    guest.normal_observation_profile = profile
    boot['normal_observation_profile'] = profile
    boot['pcid_observation_profile'] = pcid_profile
    boot['gui_control'] = pcid.prior.close_gui(guest)
    boot['before'], baseline = guest.large_snapshot('before')
    contract = layout_contract(esp)
    check(baseline['report']['attempted'] == 0 and baseline['requested'] is False,
          'normal desktop already requested/triggered owner; no false before image')
    boot['launches'], boot['requests'] = [], []
    for cfg in (7, 8, 9, 10, 11):
        request = dict(configuration=cfg, argument=raw.ARGS[cfg], command=launch_command(cfg), serial_start=len(guest.raw))
        boot['requests'].append(request)
        if cfg == 11:
            boot['trigger'] = request
        try:
            request['receipt'] = guest.shell(request['command'])
            boot['launches'].append(request['receipt'])
        except (ValueError, TimeoutError) as exc:
            # Only the final committed launch can request B. A generic failure
            # still earns no pass: the exact raw A/PTE-B held oracle is required.
            request['error'] = type(exc).__name__ + ': ' + str(exc)
            if cfg != 11 or not negative:
                raise
        finally:
            request['serial_end'] = len(guest.raw)
    until = time.monotonic() + 120
    last = None
    while True:
        boot['after'], observed = guest.large_snapshot('after')
        try:
            validate(baseline, observed, contract, negative=bool(negative), require_pcid=require_pcid,
                     normal_observation_profile=profile)
            break
        except ValueError as exc:
            last = exc
            terminal = dict(owner_poison=bool(observed['report']['poison']),
                            domain_failed=bool(observed['domain'][1]), bridge_failed=bool(observed['bridge'][1]))
            if any(terminal.values()) or 'fallback is not a pass' in str(exc) or 'observer-disturbed' in str(exc):
                # A verified precise negative has already broken out above.
                # Here a permanent failure cannot become healthy by resuming.
                # Retain the first checkpoint and original error, without
                # assigning the failure to production code or its observer.
                boot.setdefault('first_failed_checkpoint', dict(epoch=boot['after']['epoch'],
                    checkpoint=copy.deepcopy(boot['after']), error_type=type(exc).__name__, error=str(exc),
                    terminal=terminal, cause='undetermined',
                    classification='observer-disturbed' if 'observer-disturbed' in str(exc) else 'terminal-validation-failure'))
                raise
            if time.monotonic() >= until:
                raise ValueError('no complete actual runtime-large checkpoint: ' + str(last)) from exc
            # large_snapshot already performed the one explicit cont before
            # historical assembly/decode. No second resume belongs to retry.
            time.sleep(.04)
    # All five workload roots were committed before the immutable LARGE after.
    # The later PCID observation does not launch or replace any root.
    if not negative:
        boot['pcid_snapshot'], _ = pcid.stable_snapshot(guest, raw.ARGS, require_pcid=require_pcid,
                                                     observation_profile=pcid_profile)
        check(require_pcid_observation_profile(boot['pcid_snapshot'].get('observation_profile', PCID_LOCK_FREE))
              == pcid_profile, 'collected PCID snapshot observation profile differs from requested profile')
    validate_launch_order(boot, bytes(guest.raw), baseline, observed, negative=bool(negative))


def final_inputs(result, esp, identity, tools, disk):
    try:
        result['tools_after'] = source_tools(esp)
        stable = result['tools_after'] == tools and build.identity(esp) == identity
        if result.get('final_disk_sha256') and sha(disk) != result['final_disk_sha256']:
            stable = False
        result['inputs_unchanged'] = stable
        if not stable:
            result.update(passed=False, final_error='source/tool/artifact/disk changed')
    except BaseException as exc:
        result.update(passed=False, inputs_unchanged=False, final_error=type(exc).__name__ + ': ' + str(exc))
    if result.get('passed') is not True and 'seal' in result:
        result['invalidated_seal'] = result.pop('seal')


def verify_capture_record(state, guest):
    """Bind cleanup's completed OBS32 disk verification before loading epochs."""
    capture = guest.get('bulk_capture', {})
    check(capture.get('schema') == pcid.bulk.SCHEMA and capture.get('index_file') == pcid.bulk.INDEX
          and capture.get('final_disk_verified') is True
          and sha(Path(state) / pcid.bulk.INDEX) == capture.get('index_sha256'),
          'actual bulk capture provenance missing/changed')


def replay(path, *, normal_observation_profile=None, pcid_observation_profile=None):
    path = Path(path).resolve()
    result = json.loads(path.read_text(encoding='utf-8'))
    profile = observation_profile(result.get('normal_observation_profile', LEGACY_OBSERVATION),
                                  negative=result.get('negative'))
    pcid_profile = saved_pcid_observation_profile(result, requested=pcid_observation_profile)
    if normal_observation_profile is not None:
        requested = observation_profile(normal_observation_profile, negative=result.get('negative'))
        check(requested == profile, 'replay normal observation profile differs from saved result')
    if 'seal' in result:
        check(result['seal'].get('normal_observation_profile', LEGACY_OBSERVATION) == profile,
              'saved seal normal observation profile differs from result')
    identity = build.identity(result['esp'])
    check(result['source_identity'] == identity and result['execute'] is True and result['actual_guest_executed'] is True
          and result['synthetic'] is False
          and result['guest_memory_or_register_writes'] is False and len(result['boots']) == 2, 'not two actual source-bound boots')
    check(result['tools_before'] == result['tools_after']
          and all(sha(p) == h for p, h in result['tools_before'].items()), 'runner/QEMU/firmware changed')
    contract = layout_contract(result['esp']);contract['esp'] = result['esp']
    seals = []
    for index, boot in enumerate(result['boots'], 1):
        check(boot.get('normal_observation_profile', LEGACY_OBSERVATION) == profile,
              'boot normal observation profile differs from result')
        state = path.parent / ('boot-' + str(index))
        check(sha(state / 'physical-manifest.json') == boot['physical_manifest_sha256'], 'physical archive changed')
        check(sha(state / 'serial.log') == boot['serial_sha256'], 'serial archive changed')
        serial = (state / 'serial.log').read_bytes()
        matches = re.findall(rb'^memory_runtime_boot_info=0x([0-9a-f]{16})\r?$', serial, re.M)
        check(len(matches) == 1 and boot['before']['boot_info_ref']['physical'] == boot['after']['boot_info_ref']['physical']
              == int(matches[0], 16) - 0xffff800000000000, 'actual BootInfo physical address not bound to boot serial')
        guest = json.loads((state / 'guest.json').read_text())
        check(guest == boot['guest'] and guest.get('actual_qemu_executed') is True
              and guest.get('process_alive') is False and guest.get('cleanup_completed') is True, 'guest execution/cleanup incomplete')
        pcid.verify_launch_command(guest['command'], accel=result['accel'], cpu=result['cpu'],
                                   kernel_irqchip=result['kernel_irqchip'])
        inventory = json.loads((state / 'cpu-inventory.json').read_text())
        check(sha(state / 'cpu-inventory.json') == boot['cpu_inventory_sha256']
              and {c['cpu-index'] for c in inventory} == set(range(4)) and len(inventory) == 4
              and len({c['thread-id'] for c in inventory}) == 4, 'CPU inventory missing/duplicated')
        verify_capture_record(state, guest)
        archive = raw.Archive(state, json.loads((state / 'physical-manifest.json').read_text()),
                              metadata=pcid.capture_metadata(result['esp']))
        before = decode(boot['before'], archive, contract, normal_observation_profile=profile)
        after = decode(boot['after'], archive, contract, normal_observation_profile=profile)
        seal = validate(before, after, contract, negative=bool(result['negative']), require_pcid=result['require_pcid'],
                        normal_observation_profile=profile)
        seal['pcid_observation_profile'] = pcid_profile
        seals.append(seal)
        validate_launch_order(boot, serial, before, after, negative=bool(result['negative']))
        if not result['negative']:
            decoded = raw.decode_snapshot(boot['pcid_snapshot'], archive, observation_profile=pcid_profile,
                                          **pcid.elf_contract(result['esp']))
            raw.validate_snapshot(decoded, require_pcid=result['require_pcid'], workers=True,
                                  observation_profile=pcid_profile)
        archive.verify_all()
    check(sha(path.parent / 'data.img') == result['final_disk_sha256'], 'final guest disk changed')
    return dict(passed=True, boots=seals, hardware_guest_evidence=True, historical_replay=False,
                normal_observation_profile=profile, pcid_observation_profile=pcid_profile)


def execute(esp, output, *, accel='tcg', cpu='max,+smep,+smap,+umip', require_pcid=False, negative=None,
            kernel_irqchip=None, normal_observation_profile=LEGACY_OBSERVATION,
            pcid_observation_profile=PCID_LOCK_FREE):
    profile = observation_profile(normal_observation_profile, negative=negative)
    pcid_profile = require_pcid_observation_profile(pcid_observation_profile, negative=negative)
    esp, output = Path(esp).resolve(), Path(output).resolve()
    check(kernel_irqchip is None or kernel_irqchip == 'off' and accel == 'whpx',
          'kernel-irqchip=off is an explicit WHPX-only configuration')
    identity = build.identity(esp)
    check(negative == identity['case'], 'negative differs from actual built source')
    check(not output.exists(), 'fresh guest run directory required')
    output.mkdir(parents=True)
    disk = output / 'data.img';create(disk, 64)
    tools = source_tools(esp)
    result = dict(schema=1, esp=str(esp), source_identity=identity, execute=True, passed=False,
        negative=negative, require_pcid=require_pcid, tools_before=tools, boots=[], guest_memory_or_register_writes=False,
        actual_guest_executed=False, synthetic=False, accel=accel, cpu=cpu, kernel_irqchip=kernel_irqchip,
        normal_observation_profile=profile, pcid_observation_profile=pcid_profile)
    try:
        for index in (1, 2):
            state = output / ('boot-' + str(index))
            boot = dict(normal_observation_profile=profile, pcid_observation_profile=pcid_profile)
            result['boots'].append(boot);guest = None
            try:
                guest = LargeGuest(esp, disk, state, accel=accel, cpu=cpu, kernel_irqchip=kernel_irqchip)
                result['actual_guest_executed'] = True
                pcid.verify_launch_command(guest.evidence['command'], accel=accel, cpu=cpu, kernel_irqchip=kernel_irqchip)
                inventory = guest.qmp.request('query-cpus-fast');write(state / 'cpu-inventory.json', inventory)
                boot['cpu_inventory_sha256'] = sha(state / 'cpu-inventory.json')
                collect_boot(guest, boot, state, esp, negative=negative, require_pcid=require_pcid,
                             normal_observation_profile=profile, pcid_observation_profile=pcid_profile)
            finally:
                if guest is not None:
                    guest.close();boot['guest'] = copy.deepcopy(guest.evidence)
                    boot['physical_manifest_sha256'] = sha(state / 'physical-manifest.json')
                    boot['serial_sha256'] = sha(state / 'serial.log')
                write(output / 'result.json', result)
        result.update(tools_after=source_tools(esp), final_disk_sha256=sha(disk))
        write(output / 'result.json', result)
        result['seal'] = replay(output / 'result.json', normal_observation_profile=profile,
                                pcid_observation_profile=pcid_profile)
        result['passed'] = True
    except BaseException as exc:
        result.update(passed=False, error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        final_inputs(result, esp, identity, tools, disk)
        write(output / 'result.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--negative', choices=['omit-ap-flush'])
    parser.add_argument('--require-pcid', action='store_true')
    parser.add_argument('--accel', choices=['tcg', 'whpx', 'kvm'], default='tcg')
    parser.add_argument('--cpu', default='max,+smep,+smap,+umip')
    parser.add_argument('--kernel-irqchip', choices=['off'], help='explicit WHPX-only interrupt backend')
    parser.add_argument('--normal-observation-profile',
                        help='normal-only observation contract: legacy-idle-v1 (default) or current-kernel-v2')
    parser.add_argument('--pcid-observation-profile',
                        help='independent later-PCID contract: lock-free-v1 (default) or current-owner-v2')
    parser.add_argument('--replay', type=Path)
    args = parser.parse_args(argv)
    try:
        profile = observation_profile(args.normal_observation_profile if args.normal_observation_profile is not None
                                      else LEGACY_OBSERVATION, negative=args.negative)
        pcid_profile = require_pcid_observation_profile(args.pcid_observation_profile if args.pcid_observation_profile is not None
                                                else PCID_LOCK_FREE, negative=args.negative)
        check(args.kernel_irqchip is None or args.kernel_irqchip == 'off' and args.accel == 'whpx',
              'kernel-irqchip=off is an explicit WHPX-only configuration')
        if args.replay:
            check(not args.execute, 'replay cannot start guests')
            result = replay(args.replay, normal_observation_profile=args.normal_observation_profile,
                            pcid_observation_profile=args.pcid_observation_profile)
        elif not args.execute:
            check(args.reuse_esp is not None, '--reuse-esp required')
            identity = build.identity(args.reuse_esp)
            observation_profile(profile, negative=identity.get('case'))
            require_pcid_observation_profile(pcid_profile, negative=identity.get('case'))
            result = dict(passed=True, mode='identity-only', guest_executed=False, source_identity=identity,
                          normal_observation_profile=profile, pcid_observation_profile=pcid_profile)
        else:
            check(args.reuse_esp is not None, '--reuse-esp required')
            output = args.output or ROOT / 'build/test/p2-runtime-large/qemu' / ('run-' + uuid.uuid4().hex[:12])
            result = execute(args.reuse_esp, output, accel=args.accel, cpu=args.cpu,
                require_pcid=args.require_pcid, negative=args.negative, kernel_irqchip=args.kernel_irqchip,
                normal_observation_profile=profile, pcid_observation_profile=pcid_profile)
        print(json.dumps(result));return 0 if result.get('passed') is True else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps(dict(passed=False, error=type(exc).__name__ + ': ' + str(exc))));return 1


if __name__ == '__main__':
    raise SystemExit(main())
