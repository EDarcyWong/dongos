#!/usr/bin/env python3
"""Real NVMe CPL3 write/read/FLUSH and same-disk reboot; never builds an OS."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build_usb import verify_build
from tools.make_fat32_disk import create
from tools.elf_symbols import read_elf_symbols
from tests import run_desktop_settings_qemu as settings, run_services_qemu as storage

ROOT = settings.ROOT
NVME_DEVICE = 'nvme,drive=data,serial=DongOSNVMe'
QUEUE_FIELDS = ('ready held fault epoch qid depth lease_physical lease_bytes sq_tail cq_head phase '
                'next_cid generation pending pending_cid pending_kind pending_bytes pending_generation '
                'started_ms last_ms timeout_ms').split()
EXPECTED_LAYOUT = {
    'drivers.nvme.State': (656, dict(info=0, lease=56, bar=88, ops=112, context=120,
        caps=128, limits=152, controller=176, namespace=208, admin=240, io=408,
        busy=576, enabled=584, clock_seen=592, last_ms=600, phase=608, published=616,
        last_csts=624, last_cqe=632, last_kind=648)),
    'drivers.nvme.Info': (56, dict(capacity_sectors=0, max_transfer_sectors=8, readonly=16,
        ready=24, faulted=32, held=40, completed=48)),
    'drivers.nvme.Ops': (56, dict(read=0, write=8, fence=16, acquire=24, release=32, enable=40, now=48)),
    'drivers.nvme_core.Queue': (168, {name: i * 8 for i, name in enumerate(QUEUE_FIELDS)}),
}


def check_layout(esp):
    from lang.dongc import compile_file
    generated = compile_file(ROOT / 'services/drivers/block_service.dg',
        roots=[ROOT / 'services', ROOT / 'lang/std'], mode='release')
    settings.check(generated.assembly == (esp.parent / 'services/block/program.asm').read_text(encoding='utf-8'),
                   'layout compiler output differs from the completed block ELF input')
    types = {t['full_name']: t for t in generated.layout_manifest['types']}
    for name, (size, fields) in EXPECTED_LAYOUT.items():
        actual = types[name]
        offsets = {f['name']: f['offset'] for f in actual['fields']}
        settings.check(actual['size'] == size and all(offsets.get(n) == o for n, o in fields.items()),
                       'NVMe actual ABI changed: ' + name)
    return EXPECTED_LAYOUT


def check_kernel_memory_layout(esp):
    from lang.dongc import compile_file
    path = esp.parent / 'dong_layout.json'
    completed = {t['full_name']: t for t in json.loads(path.read_text(encoding='utf-8'))['types']}
    compiled = compile_file(ROOT / 'kernel/boot/memory_startup.dg',
        roots=[ROOT / 'lang/examples', ROOT / 'kernel', ROOT / 'services', ROOT / 'lang/std'], mode='debug')
    current = {t['full_name']: t for t in compiled.layout_manifest['types']}
    for name in ('boot.memory_startup.Workspace', 'boot.runtime_view.View'):
        settings.check(current[name] == completed[name], 'kernel runtime-view layout differs from completed build')
    workspace = current['boot.memory_startup.Workspace']
    view = current['boot.runtime_view.View']
    fields = {f['name']: f['offset'] for f in view['fields']}
    runtime = next(f for f in workspace['fields'] if f['name'] == 'runtime')
    settings.check(runtime['size'] == view['size'] == 160
                   and all(fields.get(n) == o for n, o in dict(pool=96, pool_physical=104,
                            pool_pages=112, root_physical=152).items()), 'kernel View ABI changed')
    return dict(layout_file_sha256=settings.sha(path), workspace_size=workspace['size'],
                runtime_offset=runtime['offset'], view_size=160, view_fields=fields)


def nvme_command(command):
    """Keep the existing SATA EFI drive; replace only the exact data device."""
    command = list(command)
    efi = [i for i, v in enumerate(command) if i and command[i - 1] == '-drive'
           and v.startswith('format=raw,file=fat:rw:')]
    data = [i for i, v in enumerate(command) if i and command[i - 1] == '-drive'
            and v.startswith('if=none,id=data,format=raw,')]
    virtio = [i for i, v in enumerate(command) if i and command[i - 1] == '-device'
              and v == 'virtio-blk-pci,drive=data,disable-legacy=on']
    settings.check(len(efi) == len(data) == len(virtio) == 1,
                   'one exact existing EFI drive and VirtIO data device are required')
    settings.check(not any(v.startswith(('nvme,', 'nvme-ns,')) or 'id=bootesp' in v for v in command),
                   'NVMe or boot alias already present')
    command[virtio[0]] = NVME_DEVICE
    return command


def queue_fields(raw):
    settings.check(len(raw) == 168, 'NVMe queue snapshot must be 168 bytes')
    return dict(zip(QUEUE_FIELDS, struct.unpack('<21Q', raw)))


def verify_no_user_dma_alias(root, read_table, physical, length, kernel_pool=None, private_pages=32):
    """Walk every effectively USER leaf and reject physical DMA aliases.

    USER ancestor paths may enter the inherited retained kernel128-page pool
    before lower supervisor-only entries remove effective USER permission.
    Only the exact private32/128 pages and independently verified kernel128 pages may
    be dereferenced; high mappings are never skipped by their virtual address.
    Address-space DAGs are memoized by (table,level); cycles fail closed.
    Valid1GiB/2MiB leaves are checked as complete physical intervals.
    """
    ceiling = 1 << 52
    settings.check(0 < root < ceiling and root % 4096 == 0
                   and private_pages in (32,128) and root + private_pages * 4096 <= ceiling, 'invalid private page-table pool')
    settings.check(0 < physical < ceiling and 0 < length <= ceiling - physical,
                   'invalid forbidden DMA interval')
    pool_end = root + private_pages * 4096
    allowed = [(root, pool_end)]
    if kernel_pool is not None:
        kernel_base, kernel_pages = kernel_pool
        settings.check(0 < kernel_base < ceiling and kernel_base % 4096 == 0
                       and kernel_pages == 128 and 128 * 4096 <= ceiling - kernel_base,
                       'invalid trusted kernel128-page pool')
        kernel_end = kernel_base + 128 * 4096
        settings.check(not (root < kernel_end and kernel_base < pool_end),
                       'private and trusted kernel page-table pools overlap')
        allowed.append((kernel_base, kernel_end))
    active, complete, cache = set(), set(), {}
    leaf_counts = {4096: 0, 2097152: 0, 1073741824: 0}
    supervisor_branches = 0

    def walk(table, shift, virtual):
        nonlocal supervisor_branches
        settings.check(table % 4096 == 0 and any(start <= table < stop for start, stop in allowed),
                       'USER page table outside allowlisted trusted private/kernel128 pools')
        settings.check(table not in active, 'cycle in USER page tables')
        if (table, shift) in complete:
            return
        if table not in cache:
            page = read_table(table)
            settings.check(len(page) == 4096, 'incomplete USER page-table read')
            cache[table] = page
        active.add(table)
        for index, entry in enumerate(struct.unpack('<512Q', cache[table])):
            if not entry & 1:
                continue
            if not entry & 4:
                supervisor_branches += 1
                continue
            at = virtual | (index << shift)
            if at & (1 << 47):
                at |= 0xffff000000000000
            if shift == 12 or (shift in (30, 21) and entry & 128):
                span = 1 << shift
                if shift != 12:
                    # Bit12 is the large-page PAT selector. Bits13..(shift-1)
                    # are reserved; treating them as a base could hide aliases.
                    reserved = ((1 << shift) - 1) & ~((1 << 13) - 1)
                    settings.check(entry & reserved == 0, 'misaligned/reserved large USER leaf')
                base = entry & storage.MASK & ~(span - 1)
                settings.check(not (base < physical + length and physical < base + span),
                    f'USER leaf VA0x{at:x} physical[0x{base:x},0x{base+span:x}) aliases DMA')
                leaf_counts[span] += 1
            else:
                settings.check(shift != 39 or not entry & 128, 'large USER leaf invalid at PML4')
                walk(entry & storage.MASK, shift - 9, at)
        active.remove(table)
        complete.add((table, shift))

    walk(root, 39, 0)
    return dict(root=root, forbidden_physical=physical, forbidden_bytes=length,
                private_pool_pages=private_pages, unique_tables_read=len(cache),
                trusted_kernel_pool=None if kernel_pool is None else list(kernel_pool),
                table_level_interpretations=len(complete), supervisor_branches_skipped=supervisor_branches,
                user_leaf_counts={str(size): count for size, count in leaf_counts.items()},
                no_effective_user_physical_alias=True)


def validate_flush(state, sqe, cqe):
    """Independently check raw hardware SQ/CQ bytes, including the consumed phase.

    NVMe CQEs contain no transferred-byte count. No software expected-byte field
    is treated as a DMA receipt; successful file readback supplies the data check.
    """
    settings.check(len(state) == 656 and len(sqe) == 64 and len(cqe) == 16,
                   'invalid NVMe completion snapshot sizes')
    q = queue_fields(state[408:576])
    settings.check((q['ready'], q['held'], q['fault'], q['epoch'], q['qid'], q['depth'])
                   == (1, 1, 0, 1, 1, 2), 'I/O queue identity/lifetime differs')
    settings.check(q['pending'] == q['pending_cid'] == q['pending_kind'] == q['pending_bytes']
                   == q['pending_generation'] == q['started_ms'] == q['timeout_ms'] == 0,
                   'last I/O completion still pending')
    cid = q['next_cid']
    settings.check(0 < cid < 65535 and q['generation'] == cid,
                   'last-issued CID/generation differs')
    settings.check(q['sq_tail'] == q['cq_head'] == cid % q['depth']
                   and q['phase'] == (1 ^ ((cid // q['depth']) & 1)),
                   'I/O queue head/tail/phase history differs')
    expected_sqe = bytearray(64)
    struct.pack_into('<HI', expected_sqe, 2, cid, 1)
    settings.check(sqe == expected_sqe, 'actual last SQE is not a reserved-zero NSID1 FLUSH')
    consumed_phase = q['phase'] ^ (1 if q['cq_head'] == 0 else 0)
    expected_cqe = struct.pack('<IIHHHH', 0, 0, q['sq_tail'], 1, cid, consumed_phase)
    settings.check(cqe == expected_cqe, 'actual FLUSH CQE CID/SQHD/SQID/status/phase differs')
    settings.check(cqe == state[632:648], 'saved CQE differs from the actual DMA completion slot')
    busy, enabled, seen, _, phase, published, csts = struct.unpack_from('<7Q', state, 576)
    settings.check((busy, enabled, seen, phase, published) == (0, 1, 1, 11, 0)
                   and csts & 0x2f == 1 and struct.unpack_from('<Q', state, 648)[0] == 5,
                   'runtime did not finish healthy guest-requested FLUSH')
    return dict(cid=cid, generation=q['generation'], sq_slot=(q['sq_tail'] + 1) % 2,
                cq_slot=(q['cq_head'] + 1) % 2, consumed_phase=consumed_phase,
                queue=q, sqe_hex=sqe.hex(), cqe_hex=cqe.hex(),
                hardware_transferred_byte_count_available=False)


class NvmeGuest(settings.Guest):
    def __init__(self, esp, disk, state, kernel_memory_layout=None):
        self._nvme_closed = False
        self.kernel_memory_layout = kernel_memory_layout or check_kernel_memory_layout(esp)
        super().__init__(esp, disk, state, block_backend='nvme')
        try:
            self.wait(b'DONGOS_NVME_READY')
        except Exception:
            self.close()
            raise

    def shell(self, command, expected):
        settings.check(command.isascii() and '\n' not in command and '\r' not in command
                       and len(command) < 255, 'invalid UART command')
        before = len(self.raw)
        self.resume()
        self.uart.sendall(command.encode() + b'\r')
        deadline = time.monotonic() + 40
        while True:
            segment = bytes(self.raw[before:])
            found = segment.find(expected)
            if found >= 0 and b'> ' in segment[found + len(expected):]:
                break
            settings.check(self.process.poll() is None and b'PANIC' not in self.raw
                           and b'DONGOS_P1_KERNEL_FAIL' not in self.raw, 'actual guest failure')
            settings.check(time.monotonic() < deadline, 'UART response timeout')
            time.sleep(.01)
        self.pause()
        segment = bytes(self.raw[before:])
        settings.check(command.encode() in segment and b'ERROR ' not in segment
                       and b'unknown command' not in segment, 'fresh UART command failed or echo missing')
        return dict(command=command, serial_offset=before, response_hex=segment.hex())

    def block_snapshot(self):
        pid = 2
        bias = struct.unpack_from('<Q', self.processes, pid * 1288 + 224)[0]
        symbols = read_elf_symbols(self.esp.parent / 'services/block/program.elf')

        def global_bytes(module, name, size):
            return self.user(pid, bias + symbols[storage.symbol(module, name)], size, module + '.' + name)

        backend = struct.unpack('<Q', global_bytes('drivers.block_service', 'BACKEND', 8))[0]
        settings.check(backend == self.kval('user.devices', 'SELECTED_KIND') == 3,
                       'actual block backend is not NVMe; EFI AHCI must not win selection')
        settings.check(self.kernel(self.ksym('user.devices', 'NVME_DMA_ENABLED'), 1,
                                  'actual NVMe enable attempt') == b'\1', 'kernel did not enable NVMe')
        state = global_bytes('drivers.block_service', 'NVME', 656)
        identity = struct.unpack('<Q', global_bytes('drivers.block_service', 'NVME_PCI_IDENTITY', 8))[0]
        settings.check(identity & 0xffff not in (0, 0xffff)
                       and (identity >> 32) & 0xffffff == 0x020801 and identity >> 56 in (0, 128),
                       'trusted PCI identity is not the selected NVMe controller')
        info = struct.unpack_from('<7Q', state)
        settings.check(info[:6] == (131072, 128, 0, 1, 0, 1) and info[6] > 0,
                       'NVMe state/capacity/completion differs')
        token, physical, pointer, length = struct.unpack_from('<4Q', state, 56)
        lease = struct.unpack('<4Q', self.kernel(self.ksym('user.devices', 'DMA_LEASE'), 32, 'trusted lease'))
        settings.check((token, physical, pointer, length) == lease and token == 1
                       and pointer == 0x68000000 and length == 131072 and physical % 131072 == 0,
                       'NVMe lease mismatch')
        settings.check(0 < physical <= 0x100000000 - length, 'NVMe DMA exceeds supported 32bit range')
        for offset in range(0, length, 4096):
            settings.check(self.pte(self.roots[pid], pointer + offset) & ~0x60
                           == (physical + offset) | 0x8000000000000007,
                           'DMA must be exact private WB/RW/NX')
        table_cache = {}
        def table_read(pa):
            if pa not in table_cache:
                table_cache[pa] = self.physical(pa, 4096, 'complete USER DMA isolation page table')
            return table_cache[pa]
        kernel_pool = self.trusted_kernel_pool()
        isolation = {str(other): verify_no_user_dma_alias(self.roots[other], table_read, physical, length, kernel_pool, self.private_pages(self.roots[other]))
                     for other in (0, 1, 3, 4)}
        # Input has an independent16KiB lease at the same user VA. Verify its
        # own mapping and physical isolation instead of requiring that VA absent.
        input_lease = struct.unpack('<4Q', self.kernel(self.ksym('user.devices', 'INPUT_LEASE'),
                                                       32, 'trusted input DMA lease'))
        input_token, input_pa, input_va, input_bytes = input_lease
        settings.check(input_token == 2 and input_va == 0x68000000 and input_bytes == 16384
                       and 0 < input_pa <= 0x100000000 - input_bytes and input_pa % 4096 == 0
                       and not (input_pa < physical + length and physical < input_pa + input_bytes),
                       'input and block DMA leases overlap or differ from trusted bounds')
        for offset in range(0, input_bytes, 4096):
            settings.check(self.pte(self.roots[4], input_va + offset) & ~0x60
                           == (input_pa + offset) | 0x8000000000000007,
                           'input DMA must remain exact private WB/RW/NX')
        input_isolation = {str(other): verify_no_user_dma_alias(self.roots[other], table_read, input_pa, input_bytes, kernel_pool, self.private_pages(self.roots[other]))
                           for other in (0, 1, 2, 3)}
        bars = self.kernel(self.ksym('user.devices', 'BARS'), 144, 'trusted BAR grants')
        granted = [struct.unpack_from('<3Q', bars, i * 24) for i in range(6)]
        settings.check(granted[0][0] > 0 and granted[0][1] >= 0x1010 and granted[0][2] != 0
                       and all(b == (0, 0, 0) for b in granted[1:]), 'NVMe must grant only BAR0')
        settings.check(tuple(struct.unpack_from('<3Q', state, 88)) == granted[0],
                       'NVMe runtime BAR differs from the trusted grant')
        for offset in range(0, granted[0][1], 4096):
            settings.check(self.pte(self.roots[pid], 0x60000000 + offset) & ~0x60
                           == (granted[0][0] + offset) | 0x800000000000001f,
                           'BAR0 lost UC/RW/NX/USER')
        header = struct.unpack('<16Q', self.kernel(self.ksym('user.devices', 'NVME_HEADER'),
                                                  128, 'pre-enable trusted NVMe snapshot'))
        cap, version, bits, bar_size, lease_pa, lease_bytes, pci_command, cc, csts, intms, aqa, asq, acq, msi, msix, exclusive = header
        settings.check((cap, version) == struct.unpack_from('<2Q', state, 128)
                       and 36 <= bits <= 48 and bar_size == granted[0][1]
                       and (lease_pa, lease_bytes) == (physical, length), 'trusted NVMe bounds/capabilities differ')
        settings.check(pci_command <= 65535 and pci_command & 0x407 == 0x402
                       and cc == 0x460000 and csts == 0 and intms == 0xffffffff
                       and aqa == 0x10001 and (asq, acq) == (physical, physical + 0x1000)
                       and (msi, msix, exclusive) == (1, 1, 1),
                       'BME was enabled before disabled/masked controller and trusted Admin queues')
        io = queue_fields(state[408:576])
        admin = queue_fields(state[240:408])
        settings.check((admin['qid'], admin['next_cid'], admin['pending'], admin['fault']) == (0, 5, 0, 0)
                       and io['next_cid'] == info[6]
                       and (io['lease_physical'], io['lease_bytes']) == (physical, length),
                       'actual Admin initialization or I/O completion count differs')
        sq_slot = (io['sq_tail'] + io['depth'] - 1) % io['depth']
        cq_slot = (io['cq_head'] + io['depth'] - 1) % io['depth']
        sqe = self.physical(physical + 0x2000 + sq_slot * 64, 64, 'actual NVMe I/O SQ FLUSH command')
        cqe = self.physical(physical + 0x3000 + cq_slot * 16, 16, 'actual NVMe I/O CQ completion')
        flush = validate_flush(state, sqe, cqe)
        self.evidence.update(actual_nvme=True, actual_guest_flush=True, only_bar0_granted=True,
            controller_disabled_and_admin_bases_verified_before_enable=True, msi_msix_disabled_before_enable=True,
            dma_lease_verified=True, dma_lease_private_to_block=True,
            hardware_transferred_byte_count_available=False)
        return dict(info=list(info), lease=list(lease), bar0=list(granted[0]), pci_identity=identity,
                    trusted_pre_enable_header=list(header), caps=list(struct.unpack_from('<3Q', state, 128)),
                    raw_state_sha256=hashlib.sha256(state).hexdigest(), flush=flush,
                    complete_block_dma_user_isolation=isolation, input_lease=list(input_lease),
                    complete_input_dma_user_isolation=input_isolation)

    def trusted_kernel_pool(self):
        layout = self.kernel_memory_layout
        view_va = self.ksym('boot.memory_startup', 'WORK') + layout['runtime_offset']
        raw = self.kernel(view_va, layout['view_size'], 'trusted retained kernel runtime View')
        def field(name):
            return struct.unpack_from('<Q', raw, layout['view_fields'][name])[0]
        observed = {}
        for name in ('pool_physical', 'pool_pages', 'root_physical', 'runtime_view'):
            values = re.findall(rb'^memory_' + name.encode() + rb'=0x([0-9a-f]{16})\r?$',
                                bytes(self.raw), re.MULTILINE)
            settings.check(len(values) == 1, 'missing/duplicate trusted kernel memory UART field: ' + name)
            observed[name] = int(values[0], 16)
        base, pages, root = field('pool_physical'), field('pool_pages'), field('root_physical')
        settings.check(observed == dict(pool_physical=base, pool_pages=pages,
                                       root_physical=root, runtime_view=view_va),
                       'kernel View/UART pool or root mismatch')
        settings.check(0 < base < 0x100000000 and base % 4096 == 0 and pages == 128
                       and pages * 4096 <= 0x100000000 - base
                       and base <= root < base + pages * 4096 and root % 4096 == 0
                       and field('pool') == 0xffff800000000000 + base,
                       'retained kernel table pool bounds/alias differ')
        self.evidence['trusted_kernel_page_table_pool'] = dict(physical=base, pages=pages,
            root_physical=root, runtime_view_virtual=view_va, layout=layout,
            independently_read_from_kernel_and_matched_to_uart=True)
        return base, pages

    def close(self):
        if self._nvme_closed:
            return
        try:
            super().close()
            stopped = self.process is None or self.process.poll() is not None
            self.evidence.update(qemu_stopped=stopped,
                                 qemu_returncode=None if self.process is None else self.process.returncode)
            storage.write_json(self.state / 'guest.json', self.evidence)
            settings.check(stopped, 'QEMU cleanup did not confirm process stopped')
            self._nvme_closed = True
        except Exception as error:
            self.evidence['cleanup_error'] = f'{type(error).__name__}: {error}'
            # Constructor failures never return a Guest to main(). Ensure an
            # earlier QMP/manifest error cannot bypass stopping our own process.
            try:
                if self.process is not None and self.process.poll() is None:
                    self.process.kill()
                    self.process.wait(timeout=5)
            except Exception as stop_error:
                self.evidence['emergency_stop_error'] = f'{type(stop_error).__name__}: {stop_error}'
            self.evidence['qemu_stopped'] = self.process is None or self.process.poll() is not None
            storage.write_json(self.state / 'guest.json', self.evidence)
            raise


def probe_qemu(state):
    qemu = settings.builder.find_tool('qemu-system-x86_64', 'QEMU')
    result = subprocess.run([qemu, '-device', 'nvme,help'], capture_output=True, timeout=20)
    raw = result.stdout + result.stderr
    (state / 'nvme-help.txt').write_bytes(raw)
    settings.check(result.returncode == 0 and b'drive=<str>' in raw and b'serial=<str>' in raw,
                   'local QEMU does not expose the required NVMe drive/serial properties')
    return dict(executable=str(qemu), sha256=settings.sha(qemu), arguments=['-device', 'nvme,help'],
                returncode=result.returncode, help_sha256=hashlib.sha256(raw).hexdigest(),
                configured_properties=['drive=data', 'serial=DongOSNVMe'], actual_guest_executed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp', type=Path)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        from tests.test_nvme_qemu import (CommandTests, CompletionTests, CleanupTests,
                                          IsolationTests, InheritedPoolTests)
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c)
                                   for c in (CommandTests, CompletionTests, CleanupTests,
                                             IsolationTests, InheritedPoolTests))
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if not args.reuse_esp:
        parser.error('--reuse-esp required; this runner never builds')
    state = ROOT / 'build/test/nvme/qemu' / ('run-' + uuid.uuid4().hex[:12])
    state.mkdir(parents=True)
    result = dict(passed=False, actual_qemu_boots=0, boot_attempts=0, boots=[], backend='nvme',
                  full_os_build_executed=False, actual_128_sector_rpc_verified=False)
    guest = None
    esp = args.reuse_esp.resolve()
    metadata = {}
    names = ['tests/run_nvme_qemu.py', 'tests/run_desktop_settings_qemu.py', 'tests/run_services_qemu.py',
             'tests/run_acpi_qemu.py', 'tools/build_usb.py', 'tools/make_fat32_disk.py',
             'tools/elf_symbols.py', 'tools/build.py']
    inputs = {n: settings.sha(ROOT / n) for n in names}
    result['runner_inputs'] = inputs
    try:
        metadata = verify_build(esp)
        result['build_inputs_verified'] = True
        result['build_inputs_sha256'] = settings.sha(esp.parent / 'build-inputs.json')
        result['layout'] = check_layout(esp)
        result['kernel_memory_layout'] = check_kernel_memory_layout(esp)
        result['qemu_capability_probe'] = probe_qemu(state)
        disk = state / 'data.img'
        create(disk, 64)
        payload = ('DongOS NVMe persistent ' + state.name).encode()
        first_hash = None
        for i in range(2):
            result['boot_attempts'] += 1
            guest = NvmeGuest(esp, disk, state / ('boot-' + str(i + 1)), result['kernel_memory_layout'])
            commands = []
            if i == 0:
                commands.append(guest.shell('write PROBE.TXT ' + payload.decode(), b'WRITE OK'))
            commands.append(guest.shell('cat PROBE.TXT', payload))
            commands.append(guest.shell('ls', b'PROBE.TXT'))
            commands.append(guest.shell('sync', b'SYNC OK'))
            block = guest.block_snapshot()
            guest.close()
            result['boots'].append(dict(evidence=guest.evidence, commands=commands, block=block))
            guest = None
            result['disk'] = storage.check_disk(disk, raw_name=b'PROBE   TXT', payload=payload)
            current_hash = settings.sha(disk)
            if first_hash is None:
                first_hash = current_hash
                result['disk_sha256_after_first_sync'] = first_hash
            else:
                result['disk_sha256_after_second_sync'] = current_hash
                settings.check(current_hash == first_hash, 'same disk changed during read-only second-boot operations')
        result.update(passed=True, same_disk_reboot_verified=True, actual_cpl3_nvme=True,
                      no_qmp_storage_or_power_injection=True, no_guest_memory_or_register_writes=True)
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    finally:
        if guest:
            try:
                guest.close()
            except Exception as error:
                result.update(passed=False, cleanup_error=f'{type(error).__name__}: {error}')
        records = [json.loads(p.read_text()) for p in state.glob('boot-*/guest.json')]
        result['actual_qemu_boots'] = sum(r.get('actual_qemu_executed') is True for r in records)
        result['all_started_guests_stopped'] = all(not r.get('actual_qemu_executed')
                                                  or r.get('qemu_stopped') is True for r in records)
        if any(r.get('cleanup_error') for r in records):
            result.update(passed=False, cleanup_error='guest cleanup reported an error; see guest.json')
        if not result['all_started_guests_stopped']:
            result.update(passed=False, cleanup_error='a started QEMU process was not confirmed stopped')
        if result['passed'] and result['actual_qemu_boots'] != 2:
            result.update(passed=False, error='successful run requires exactly two recorded actual boots')
        result['source_unchanged'] = all(settings.sha(ROOT / n) == digest for n, digest in inputs.items())
        if metadata:
            try:
                verify_build(esp)
                settings.check(settings.sha(esp.parent / 'build-inputs.json') == result['build_inputs_sha256'],
                               'build metadata changed')
                if 'kernel_memory_layout' in result:
                    settings.check(settings.sha(esp.parent / 'dong_layout.json')
                                   == result['kernel_memory_layout']['layout_file_sha256'],
                                   'kernel runtime layout manifest changed')
                result['build_source_and_artifacts_unchanged'] = True
            except Exception as error:
                result.update(passed=False, build_source_and_artifacts_unchanged=False,
                              unchanged_error=f'{type(error).__name__}: {error}')
        if not result['source_unchanged']:
            result.update(passed=False, error='runner inputs changed during NVMe verification')
        storage.write_json(state / 'result.json', result)
    print('NVMe actual', 'PASS' if result['passed'] else 'FAIL', state, result.get('error', ''), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
