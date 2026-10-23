"""Bounded read-only P2 capture. No guest memory, register or clock writes.

Live readers share one privately owned immutable byte registry. Replay has its
own cache and must rehash every disk file again before issuing a final seal.
"""
from pathlib import Path
import copy
import hashlib
import json
import os
import re
import stat
import struct
import time

KERNEL = 0xffffffff80000000
HHDM = 0xffff800000000000
LIMIT = 1 << 32
WINDOW = 2 * 1024 * 1024
BUDDY = 4 * 1024 * 1024
ARENA = 128 * 1024 * 1024
MAX_SLICE = 1 << 24
INDEX = 'physical-bulk-manifest.json'
PAUSED_SCHEMA = 'p2-paused-bulk-v2'
SCHEMA = 'p2-historical-bulk-v3'
PAUSE_BUDGET_NS = 10_000_000_000
BULK_KINDS = ('boot-info', 'map', 'kernel', 'buddy', 'service', 'rsdp')
HOST_STAGE_FIELDS = ('dispatch_guard_started_ns', 'dispatch_guard_completed_ns',
    'qmp_started_ns', 'qmp_completed_ns', 'initial_read_started_ns',
    'initial_read_completed_ns', 'initial_hash_completed_ns')


def check(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def symbol(module, name):
    return '__dg_m' + module.encode().hex() + '_g' + name.encode().hex()


def extent(pa, length, *, alignment=1):
    check(type(pa) is int and type(length) is int and 0 < pa < LIMIT
          and 0 < length <= LIMIT - pa and pa % alignment == 0, 'invalid bounded physical extent')
    return pa, length


def ordinary(root, name):
    check(isinstance(name, str) and name and Path(name).name == name
          and '/' not in name and '\\' not in name and name not in ('.', '..'), 'escaped capture file')
    path = Path(root) / name
    check(path.resolve().parent == Path(root).resolve() and path.is_file() and not path.is_symlink(),
          'missing or escaped capture file')
    return path


def uart_value(serial, name):
    found = re.findall(rb'^memory_' + name.encode() + rb'=0x([0-9a-f]{16})\r?$', serial, re.M)
    check(len(found) == 1, 'missing/duplicate memory UART field: ' + name)
    return int(found[0], 16)


def boot_info(data):
    check(type(data) is bytes and len(data) == 160, 'BootInfo must be twenty qwords')
    b = struct.unpack('<20Q', data)
    check(b[:3] == (0x544f4f42474e4f44, 1, 160) and b[3] & 1 and b[7] == 1,
          'BootInfo magic/version/size/flags/descriptor ABI differs')
    extent(b[15], WINDOW, alignment=WINDOW)
    check(0 < b[16] <= WINDOW and b[19] == 65536, 'BootInfo kernel/stack size differs')
    extent(b[4], b[5]);check(b[5] <= 65536 and b[6] >= 40 and b[6] % 8 == 0 and b[5] % b[6] == 0,
                             'BootInfo memory map ABI differs')
    return b


def memory_map(raw, stride):
    check(type(stride) is int and stride >= 40 and stride % 8 == 0 and raw
          and len(raw) <= 65536 and len(raw) % stride == 0, 'invalid UEFI map shape')
    entries = []
    for at in range(0, len(raw), stride):
        kind = struct.unpack_from('<I', raw, at)[0]
        pa, pages, attrs = (struct.unpack_from('<Q', raw, at + off)[0] for off in (8, 24, 32))
        end = pa + pages * 4096
        check(kind <= 15 and pa % 4096 == 0 and pages > 0 and end < 1 << 64
              and all(not (pa < stop and start < end) for start, stop, _, _ in entries),
              'invalid UEFI descriptor or overlapping map')
        entries.append((pa, end, kind, attrs))
    return entries


def covered(entries, pa, length, kinds):
    extent(pa, length)
    cursor, end = pa, pa + length
    while cursor < end:
        found = [(stop, kind, attrs) for start, stop, kind, attrs in entries if start <= cursor < stop]
        check(len(found) == 1 and found[0][1] in kinds and not found[0][2] & (1 << 63),
              'capture range escaped original UEFI ownership')
        cursor = min(end, found[0][0])


class Metadata:
    """Host-prepared compiled offsets/symbols; never loaded from an archive's choice."""
    def __init__(self, symbols, types, binding, immutable=()):
        self._symbols = copy.deepcopy(symbols)
        self._types = copy.deepcopy(types)
        self._binding = canonical(binding)
        self._immutable = tuple((int(va), bytes(data)) for va, data in immutable)
        self._validate()

    @property
    def binding(self):
        return json.loads(self._binding)

    def address(self, module, name):
        address = self._symbols[symbol(module, name)]
        check(type(address) is int and KERNEL <= address < KERNEL + WINDOW, 'source symbol escaped loader window')
        return address

    def field(self, name, member):
        typ = self._types[name]
        fields = [f for f in typ['fields'] if f['name'] == member]
        check(len(fields) == 1, 'missing/duplicate compiled field: ' + name + '.' + member)
        f = fields[0]
        check(type(f['offset']) is int and type(f['size']) is int and f['offset'] >= 0
              and f['size'] > 0 and f['offset'] + f['size'] <= typ['size'], 'compiled field escaped structure')
        return f['offset'], f['size']

    def scalar(self, image, va, name, member):
        off, size = self.field(name, member)
        check(size in (1, 8), 'non-scalar compiled field')
        at = va - KERNEL + off
        check(0 <= at <= len(image) - size, 'compiled object escaped kernel dump')
        return int.from_bytes(image[at:at + size], 'little')

    def _validate(self):
        for name, size in [('boot.abi.BootInfo', 160), ('boot.runtime_view.View', 160),
                           ('mm.paging.Space', 64), ('boot.service_resources.Plan', 48),
                           ('sched.user_bridge.Progress', 48), ('sched.user_bridge.Failure', 224)]:
            check(self._types[name]['size'] == size, 'source-bound capture layout differs: ' + name)
        for member, off in [('magic', 0), ('version', 8), ('size', 16), ('kernel_physical', 120)]:
            check(self.field('boot.abi.BootInfo', member) == (off, 8), 'BootInfo compiled ABI differs')
        for member, off in [('pool', 96), ('pool_physical', 104), ('pool_pages', 112), ('root_physical', 152)]:
            check(self.field('boot.runtime_view.View', member) == (off, 8), 'runtime View compiled ABI differs')
        for module, name in [('boot.memory_startup', 'WORK'), ('boot.service_memory', 'PLAN'),
                             ('boot.service_memory', 'NEXT_PAGE'), ('boot.service_memory', 'HANDOFF'),
                             ('sched.user_bridge', 'PROGRESS')]:
            self.address(module, name)
        work = self.address('boot.memory_startup', 'WORK')
        check(work + self._types['boot.memory_startup.Workspace']['size'] <= KERNEL + WINDOW,
              'compiled WORK escaped retained image')

    @classmethod
    def from_esp(cls, esp):
        from tools.elf_symbols import read_elf_symbols
        from tools.kernel_storage_profile import verify_profile
        esp = Path(esp).resolve();output = esp.parent
        manifest_path, layout_path, elf_path = (output / n for n in ('build-inputs.json', 'dong_layout.json', 'kernel.elf'))
        production = json.loads(manifest_path.read_text(encoding='utf-8'))
        check(verify_profile(output, production, expected_runtime=7, source_root=output.parent / 'source') == 1,
              'capture requires source-bound current runtime7 profile')
        layout = json.loads(layout_path.read_text(encoding='utf-8'))
        check(layout['schema'] == 1 and layout['target'] == 'x86_64-dongos-elf', 'capture layout target differs')
        types = {t['full_name']: t for t in layout['types']}
        check(len(types) == len(layout['types']), 'duplicate capture layout type')
        image = elf_path.read_bytes();immutable = []
        phoff, stride, count = struct.unpack_from('<Q', image, 32)[0], *struct.unpack_from('<HH', image, 54)
        check(stride >= 56 and phoff + stride * count <= len(image), 'invalid kernel ELF program headers')
        for i in range(count):
            kind, flags, off, va, _, size, mem, _ = struct.unpack_from('<II6Q', image, phoff + i * stride)
            if kind != 1:
                continue
            check(KERNEL <= va and va + mem <= KERNEL + WINDOW and size <= mem and off + size <= len(image),
                  'ELF load segment escaped kernel capture')
            if not flags & 2 and size:
                immutable.append((va, image[off:off + size]))
        check(bool(immutable), 'kernel ELF immutable segments missing')
        binding = dict(schema=SCHEMA, synthetic=False, runtime=7,
            kernel_elf_sha256=digest(image), layout_sha256=digest(layout_path.read_bytes()),
            production_manifest_sha256=digest(manifest_path.read_bytes()), static_pools=1)
        return cls(read_elf_symbols(elf_path), types, binding, immutable)

    def derive(self, boot, kernel, rawmap, serial):
        b = boot_info(boot)
        check(len(kernel) == WINDOW and len(rawmap) == b[5], 'incomplete bootstrap dumps')
        entries = memory_map(rawmap, b[6])
        for va, expected in self._immutable:
            at = va - KERNEL
            check(kernel[at:at + len(expected)] == expected, 'resident immutable kernel differs from actual ELF')
        work = self.address('boot.memory_startup', 'WORK')
        workspace = 'boot.memory_startup.Workspace'
        check(self.scalar(kernel, work, workspace, 'ready') == 1, 'startup WORK not published')
        allocator = work + self.field(workspace, 'allocator')[0]
        a = lambda n: self.scalar(kernel, allocator, 'mm.phys_buddy.Allocator', n)
        buddy, count = a('base'), a('page_count')
        check(a('initialized') == 1 and count == 1024 and buddy % BUDDY == 0
              and a('metadata') == work + self.field(workspace, 'page_meta')[0], 'actual startup buddy identity differs')
        extent(buddy, count * 4096, alignment=BUDDY)
        view = work + self.field(workspace, 'runtime')[0]
        v = lambda n: self.scalar(kernel, view, 'boot.runtime_view.View', n)
        space = work + self.field(workspace, 'space')[0]
        s = lambda n: self.scalar(kernel, space, 'mm.paging.Space', n)
        pool, pages, root = v('pool_physical'), v('pool_pages'), v('root_physical')
        check(pages == 128 and root == pool and pool % (128 * 4096) == 0
              and buddy <= pool and pool + pages * 4096 <= buddy + BUDDY
              and v('pool') == HHDM + pool and s('initialized') == 1 and s('pool') == HHDM + pool
              and s('pool_count') == 128 and s('pool_physical') == pool and 0 < s('used_total') <= 128,
              'kernel Space/View pool identity differs')
        check(v('boot_info') == uart_value(serial, 'runtime_boot_info')
              and v('raw_map') == HHDM + b[4] and v('raw_size') == b[5]
              and v('descriptor_size') == b[6] and v('rsdp') == HHDM + b[14], 'BootInfo/runtime View differs')
        boot_pa = uart_value(serial, 'runtime_boot_info') - HHDM
        extent(boot_pa, 160, alignment=8)
        for name, wanted in [('arena_base', buddy), ('arena_pages', count), ('pool_physical', pool),
                             ('pool_pages', pages), ('root_physical', root), ('runtime_view', view),
                             ('runtime_raw_map', HHDM + b[4]), ('runtime_rsdp', HHDM + b[14])]:
            check(uart_value(serial, name) == wanted, 'kernel/UART capture identity differs: ' + name)
        rsdp_size = v('rsdp_size')
        layout_va = work + self.field(workspace, 'layout')[0]
        check(36 <= rsdp_size <= 4096 and self.scalar(kernel, layout_va, 'boot.memory_resources.Layout', 'rsdp_size') == rsdp_size,
              'source-bound RSDP extent differs')
        plan_va = self.address('boot.service_memory', 'PLAN')
        plan = struct.unpack_from('<6Q', kernel, plan_va - KERNEL)
        handoff, hand_bytes, bundle, bundle_bytes, arena, arena_bytes = plan
        next_va = self.address('boot.service_memory', 'NEXT_PAGE')
        next_page = struct.unpack_from('<Q', kernel, next_va - KERNEL)[0]
        check(hand_bytes == 4096 and arena_bytes == ARENA and 0 < next_page <= ARENA // 4096
              and 8192 <= bundle_bytes <= 64 * 1024 * 1024, 'held service PLAN/NEXT_PAGE bounds differ')
        for pa, length in ((handoff, hand_bytes), (bundle, bundle_bytes), (arena, arena_bytes)):
            extent(pa, length, alignment=4096);check(length % 4096 == 0, 'unaligned service PLAN extent')
        h = struct.unpack_from('<12Q', kernel, self.address('boot.service_memory', 'HANDOFF') - KERNEL)
        check(h[:4] == (0x31444e4148565344, 1, 96, 1) and sum(h) & ((1 << 64) - 1) == 0
              and h[4:7] == (bundle, bundle_bytes, bundle_bytes // 4096)
              and h[7:11] == (arena, ARENA, ARENA // 4096, handoff), 'source-captured handoff/PLAN differs')
        for pa, length, kinds in ((boot_pa, 160, (2,)), (b[15], WINDOW, (1,)), (buddy, BUDDY, (7,)),
                                  (handoff, hand_bytes, (2,)), (bundle, bundle_bytes, (2,)),
                                  (arena, ARENA, (2,)), (b[4], b[5], (2,)), (b[14], rsdp_size, (9, 10))):
            covered(entries, pa, length, kinds)
        extent(b[17], 8 * 4096, alignment=4096);extent(b[18], b[19], alignment=4096)
        spans = [('kernel', b[15], WINDOW), ('buddy', buddy, BUDDY), ('service', arena, ARENA),
                 ('handoff', handoff, hand_bytes), ('bundle', bundle, bundle_bytes),
                 ('map', b[4], b[5]), ('rsdp', b[14], rsdp_size),
                 ('boot-info', boot_pa, 160), ('bootstrap-root', b[17], 8 * 4096),
                 ('bootstrap-stack', b[18], b[19])]
        if b[9]:
            extent(b[8], b[9]);spans.append(('framebuffer', b[8], b[9]))
        for i, (_, pa, length) in enumerate(spans):
            for _, other, size in spans[:i]:
                check(not (pa < other + size and other < pa + length), 'derived capture ownership overlaps')
        progress_at = self.address('sched.user_bridge', 'PROGRESS') - KERNEL
        check(progress_at + 16 * 48 <= WINDOW, 'bridge Progress escaped kernel image')
        progress = [list(struct.unpack_from('<6Q', kernel, progress_at + i * 48)) for i in range(16)]
        return dict(ranges={'boot-info': [boot_pa, 160],
                    'kernel': [b[15], WINDOW], 'map': [b[4], b[5]], 'buddy': [buddy, BUDDY],
                    'service': [arena, next_page * 4096], 'rsdp': [b[14], rsdp_size]},
                    kernel_pool=[pool, pages, root], next_page=next_page, progress=progress)


class PreparedEpoch:
    """Opaque live capability; its diagnostic receipt grants no capture authority."""
    __slots__ = ('__receipt',)

    def __init__(self, receipt):
        self.__receipt = canonical(receipt)

    @property
    def receipt(self):
        return json.loads(self.__receipt)


class EpochRegistry:
    def __init__(self, root, metadata, chunks=None, *, profile=PAUSED_SCHEMA):
        check(profile in (PAUSED_SCHEMA, SCHEMA), 'unsupported explicit capture profile')
        self.profile = profile
        self._owned_exit = None
        check(isinstance(metadata, Metadata), 'explicit trusted capture metadata required')
        self.root = Path(root).resolve();self.metadata = metadata
        self.chunks = [] if chunks is None else chunks
        check(isinstance(self.chunks, list) and not self.chunks, 'fresh live physical manifest required')
        self._epochs = {};self._blobs = {};self._refs = {};self._texts = {};self._files = {}
        self._pending = {};self._writes = {};self._batches = []
        self._next_slice = 0;self.disk_reads = 0
        self._prepared = None;self._capture_active = None;self._capture_failed = False

    @staticmethod
    def _directory_identity(path):
        value = os.lstat(path)
        check(stat.S_ISDIR(value.st_mode) and not stat.S_ISLNK(value.st_mode)
              and not getattr(value, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
              and type(value.st_dev) is int and type(value.st_ino) is int and value.st_ino > 0,
              'capture root is not an ordinary directory')
        return value.st_dev, value.st_ino

    @staticmethod
    def _absent_target(path):
        # lstat also rejects dangling links, which Path.exists would miss.
        try:
            os.lstat(path)
        except FileNotFoundError:
            return
        raise ValueError('bulk file overwrite or unsafe target refused')

    def prepare_epoch(self):
        """Preflight all six canonical names during the runner's running interval.

        This does not allocate an epoch or create a placeholder file. QMP has no
        exclusive-create option: the small dispatch lstat guard and the ordinary
        post-read checks remain necessary, without claiming an atomic OS lock.
        """
        check(self.profile == SCHEMA, 'prepared epochs require the explicit v3 profile')
        check(self._capture_active is None and not self._capture_failed and self._owned_exit is None,
              'capture preparation after an active or failed capture/owned exit')
        self._prepared = None
        started = time.monotonic_ns();epoch = len(self._epochs) + 1
        if self._epochs:
            end = self._epochs[epoch - 1]['resume']
            check(end is not None and end['performed'] is True and end.get('error') is None
                  and end['elapsed_ns'] <= PAUSE_BUDGET_NS
                  and end['status'].get('running') is True and end['status'].get('status') == 'running',
                  'capture preparation requires the actual prior cont')
        check(self.root.resolve(strict=True) == self.root, 'capture root is no longer canonical')
        root_identity = None
        for directory in (*reversed(self.root.parents), self.root):
            root_identity = self._directory_identity(directory)
        paths = []
        for kind in BULK_KINDS:
            name = 'bulk-e%04d-%s.bin' % (epoch, kind)
            check(name not in self._files, 'bulk file identity reused')
            path = self.root / name;self._absent_target(path)
            canonical_path = path.resolve()
            check(canonical_path.parent == self.root and canonical_path.name == name,
                  'prepared bulk target escaped capture root')
            paths.append((kind, name, path, str(canonical_path)))
        check(len({p[3] for p in paths}) == 6, 'prepared bulk targets are not unique')
        completed = time.monotonic_ns()
        ticket = PreparedEpoch(dict(epoch=epoch, started_ns=started, completed_ns=completed,
                                    kinds=list(BULK_KINDS)))
        self._prepared = (ticket, epoch, self.root, root_identity, tuple(paths), completed)
        return ticket

    def _queue_file(self, name, raw, *, epoch, kind, authority=None):
        # No stat/open/write per ordinary slice while the VM is stopped.
        # The exclusive create in flush_pending detects even pre-existing files.
        check(type(raw) is bytes and name not in self._files, 'capture file overwrite refused')
        wanted = digest(raw)
        self._files[name] = (len(raw), wanted);self._pending[name] = raw
        self._writes[name] = dict(file=name, epoch=epoch, kind=kind, length=len(raw), sha256=wanted,
            queued_ns=time.monotonic_ns(), materialized_ns=None, batch=None)
        if self.profile == SCHEMA:
            record = self._writes[name]
            observed = self._epochs[epoch].get('observation')
            record['derivation'] = dict(kind='historical' if authority is not None else 'paused',
                source_epoch=epoch, observed_sealed_ns=(observed['sealed_ns'] if authority is not None
                    else self._epochs[epoch]['sealed_ns']), derived_ns=record['queued_ns'],
                authority=copy.deepcopy(authority))

    def history_authority(self, epoch):
        """Only a confirmed running interval or observed owned exit permits derivation."""
        self.require_epoch(epoch)
        check(self.profile == SCHEMA and self._epochs[epoch].get('observation') is not None,
              'historical derivation requires a sealed v3 observation')
        if self._owned_exit is not None:
            return dict(phase='exit', evidence=copy.deepcopy(self._owned_exit))
        latest = len(self._epochs);end = self._epochs[latest]['resume']
        check(end is not None, 'historical image cannot read while the VM is paused')
        evidence = dict(epoch=latest, confirmed_ns=end['completed_ns'], status=copy.deepcopy(end['status']))
        self._authorize_flush('resume', evidence)
        return dict(phase='resume', evidence=evidence)

    def _validate_derivation(self, record, epoch):
        if self.profile == PAUSED_SCHEMA:
            check('derivation' not in record
                  and (epoch['resume'] is None or record['queued_ns'] <= epoch['resume']['requested_ns']),
                  'v2 queued file was not captured before its epoch resume')
            return
        d = record['derivation']
        check(set(d) == {'kind','source_epoch','observed_sealed_ns','derived_ns','authority'}
              and type(d['source_epoch']) is int and type(d['observed_sealed_ns']) is int
              and d['source_epoch'] == record['epoch'] and d['derived_ns'] == record['queued_ns'],
              'historical derivation identity/time differs')
        if d['kind'] == 'paused':
            check(d['authority'] is None and d['observed_sealed_ns'] == epoch['sealed_ns']
                  and (epoch['resume'] is None or record['queued_ns'] <= epoch['resume']['requested_ns']),
                  'paused source queued after cont')
        else:
            check(d['kind'] == 'historical' and epoch.get('observation') is not None
                  and d['observed_sealed_ns'] == epoch['observation']['sealed_ns'],
                  'historical source observation differs')
            auth = d['authority']
            check(isinstance(auth, dict) and set(auth) == {'phase','evidence'}, 'historical authority missing')
            boundary = self._authorize_flush(auth['phase'], auth['evidence'], latest=False)
            check(boundary <= d['derived_ns'], 'historical derivation predates actual cont/exit')
            if auth['phase'] == 'exit':
                check(auth['evidence'] == self._owned_exit, 'historical derivation exit differs from owned cleanup')
            if auth['phase'] == 'resume':
                current = auth['evidence']['epoch']
                check(current >= record['epoch'], 'historical derivation used an earlier running epoch')
                if current < len(self._epochs):
                    check(d['derived_ns'] <= self._epochs[current + 1]['stop']['requested_ns'],
                          'historical derivation occurred in a later paused interval')

    def _authorize_flush(self, phase, evidence, *, latest=True):
        check(isinstance(evidence, dict) and phase in ('resume', 'exit'), 'explicit resume/exit materialization required')
        if phase == 'resume':
            check(set(evidence) == {'epoch', 'confirmed_ns', 'status'} and type(evidence['confirmed_ns']) is int,
                  'invalid resume materialization receipt')
            epoch = evidence['epoch'];self.require_epoch(epoch)
            end = self._epochs[epoch]['resume']
            check((not latest or epoch == len(self._epochs)) and end is not None and end['performed'] is True
                  and end.get('error') is None and end['elapsed_ns'] <= PAUSE_BUDGET_NS
                  and end['status'].get('running') is True and end['status'].get('status') == 'running'
                  and evidence['confirmed_ns'] == end['completed_ns'] and evidence['status'] == end['status'],
                  'pending files require actual successful current-epoch cont confirmation')
            return evidence['confirmed_ns']
        check(set(evidence) == {'pid', 'returncode', 'process_alive', 'observed_ns'}
              and type(evidence['pid']) is int and evidence['pid'] > 0
              and type(evidence['returncode']) is int and evidence['process_alive'] is False
              and type(evidence['observed_ns']) is int and evidence['observed_ns'] > 0,
              'pending files require observed owned-process exit')
        check(all(evidence['observed_ns'] >= (r['resume']['completed_ns'] if r['resume'] is not None
                    else (r.get('observation') or {}).get('sealed_ns', r['sealed_ns']))
                  for r in self._epochs.values()), 'exit receipt predates captured epoch')
        return evidence['observed_ns']

    def flush_pending(self, *, phase, evidence):
        boundary = self._authorize_flush(phase, evidence)
        if phase == 'exit':
            check(self._owned_exit is None or self._owned_exit == evidence, 'owned exit receipt changed')
            self._owned_exit = copy.deepcopy(evidence)
        if not self._pending:
            return 0
        batch = dict(id=len(self._batches) + 1, phase=phase, evidence=copy.deepcopy(evidence),
                     started_ns=time.monotonic_ns(), completed_ns=None, count=0, error=None)
        check(boundary <= batch['started_ns'], 'materialization predates actual resume/exit')
        self._batches.append(batch)
        try:
            for name, raw in list(self._pending.items()):
                record = self._writes[name];epoch = self._epochs[record['epoch']]
                check(record['queued_ns'] <= batch['started_ns'], 'file queued after materialization began')
                self._validate_derivation(record, epoch)
                # Never truncate/rewrite an already materialized or foreign file.
                # Failed partial writes remain evidence and cannot be retried over.
                with (self.root / name).open('xb') as stream:
                    check(stream.write(raw) == len(raw), 'short pending capture write')
                record['materialized_ns'] = time.monotonic_ns();record['batch'] = batch['id']
                del self._pending[name];batch['count'] += 1
        except BaseException as exc:
            batch['error'] = type(exc).__name__ + ': ' + str(exc)
            raise
        finally:
            batch['completed_ns'] = time.monotonic_ns()
        return batch['count']

    def _dump(self, qmp, epoch, kind, pa, length, *, prepared=None):
        extent(pa, length);check(length <= ARENA, 'bulk capture exceeds actual arena bound')
        if self.profile == SCHEMA:
            started = time.monotonic_ns()
            check(prepared is not None and self._capture_active is not None
                  and self._capture_active[0] is prepared and prepared[1] == epoch
                  and prepared[2] == self.root, 'invalid prepared bulk dispatch')
            position = self._capture_active[1]
            check(position < len(BULK_KINDS) and prepared[4][position][0] == kind,
                  'prepared bulk kind reused or reordered')
            self._capture_active[1] += 1
            _, name, path, filename = prepared[4][position]
            # Two safety checks only. Canonicalization and the six-path plan
            # were prepared before stop; never overwrite an injected target.
            check(self._directory_identity(self.root) == prepared[3], 'prepared capture root identity changed')
            self._absent_target(path)
            stages = dict(dispatch_guard_started_ns=started, dispatch_guard_completed_ns=time.monotonic_ns())
        else:
            check(prepared is None, 'v2 cannot consume a prepared epoch')
            name = 'bulk-e%04d-%s.bin' % (epoch, kind)
            check(not (self.root / name).exists(), 'bulk file overwrite refused')
            started = time.monotonic_ns();filename = str((self.root / name).resolve())
        arguments = dict(val=pa, size=length, filename=filename)
        if prepared is not None: stages['qmp_started_ns'] = time.monotonic_ns()
        response = qmp.request('pmemsave', arguments)
        if prepared is not None:
            stages['qmp_completed_ns'] = time.monotonic_ns()
            stages['initial_read_started_ns'] = time.monotonic_ns()
        raw = ordinary(self.root, name).read_bytes();self.disk_reads += 1
        if prepared is not None: stages['initial_read_completed_ns'] = time.monotonic_ns()
        check(len(raw) == length, 'short actual bulk dump')
        wanted = digest(raw)
        if prepared is not None: stages['initial_hash_completed_ns'] = time.monotonic_ns()
        record = dict(id='e%d:%s' % (epoch, kind), epoch=epoch, kind=kind, physical=pa, length=length,
                      file=name, sha256=wanted, started_ns=started, completed_ns=time.monotonic_ns(),
                      request=dict(command='pmemsave', arguments=arguments), response=response)
        if prepared is not None: record['host_stages'] = stages
        self._files[name] = (length, record['sha256']);self._blobs[record['id']] = (canonical(record), raw)
        return record, raw

    def capture_epoch(self, qmp, serial, stop, *, prepared=None):
        if self.profile == PAUSED_SCHEMA:
            check(prepared is None, 'v2 cannot consume a prepared epoch')
            return self._capture_epoch(qmp, serial, stop)
        state = self._prepared
        check(state is not None and prepared is state[0] and type(prepared) is PreparedEpoch
              and state[1] == len(self._epochs) + 1 and self._capture_active is None
              and not self._capture_failed, 'missing, foreign, stale or consumed prepared epoch')
        # Consume before any validation/read/request. Failure never revives a
        # ticket or retries over a partial dump from this same epoch.
        self._prepared = None;self._capture_active = [state, 0]
        try:
            check(type(stop.get('requested_ns')) is int and type(stop.get('confirmed_ns')) is int
                  and state[5] <= stop['requested_ns'] <= stop['confirmed_ns']
                  and stop['status'].get('running') is False and stop['status'].get('status') == 'paused',
                  'prepared epoch was not completed before the actual stop')
            epoch = self._capture_epoch(qmp, serial, stop, prepared=state)
            check(self._capture_active[1] == 6, 'prepared epoch did not consume all six kinds')
            return epoch
        except BaseException:
            self._capture_failed = True
            raise
        finally:
            self._capture_active = None

    def _capture_epoch(self, qmp, serial, stop, *, prepared=None):
        epoch = len(self._epochs) + 1
        pa = uart_value(serial, 'runtime_boot_info') - HHDM;extent(pa, 160, alignment=8)
        boot_ref, boot = self._dump(qmp, epoch, 'boot-info', pa, 160, prepared=prepared);b = boot_info(boot)
        check(uart_value(serial, 'runtime_raw_map') == HHDM + b[4], 'BootInfo map differs from trusted UART')
        map_ref, rawmap = self._dump(qmp, epoch, 'map', b[4], b[5], prepared=prepared)
        entries = memory_map(rawmap, b[6]);covered(entries, pa, 160, (2,));covered(entries, b[15], WINDOW, (1,))
        kernel_ref, kernel = self._dump(qmp, epoch, 'kernel', b[15], WINDOW, prepared=prepared)
        derived = self.metadata.derive(boot, kernel, rawmap, serial)
        refs = [boot_ref, map_ref, kernel_ref]
        for kind in ('buddy', 'service', 'rsdp'):
            ref, raw = self._dump(qmp, epoch, kind, *derived['ranges'][kind], prepared=prepared);refs.append(ref)
            if kind == 'rsdp':
                check(raw[:8] == b'RSD PTR ' and sum(raw[:20]) & 255 == 0 and raw[15] >= 2
                      and struct.unpack_from('<I', raw, 20)[0] == len(raw) and sum(raw) & 255 == 0,
                      'actual RSDP checksum/length differs')
        if self._epochs:
            first = self._epochs[1]
            check(boot == self._blobs[first['bulks'][0]['id']][1], 'immutable BootInfo changed across epochs')
        record = dict(epoch=epoch, serial_hex=serial.hex(), stop=copy.deepcopy(stop), bulks=refs,
                      sealed_ns=time.monotonic_ns(),
                      derived=derived, registers=[], aliases=[], resume=None)
        if self.profile == SCHEMA:
            record['observation'] = None
        self._epochs[epoch] = record
        return epoch

    def require_epoch(self, epoch):
        check(type(epoch) is int and epoch > 0 and epoch in self._epochs, 'unknown/unsealed capture epoch')

    def check_manifest(self, root, manifest):
        check(Path(root).resolve() == self.root and isinstance(manifest, list)
              and len(manifest) == len(self._refs), 'registry root/manifest differs')
        if manifest is not self.chunks:
            check(manifest == self.chunks, 'registry exact physical manifest differs')

    def slice(self, epoch, pa, length, role):
        """Original paused derivation: its real queue time must precede cont."""
        self.require_epoch(epoch)
        check(self._epochs[epoch]['resume'] is None, 'paused slice requested after cont')
        return self._slice(epoch, pa, length, role)

    def historical_slice(self, epoch, pa, length, role):
        authority = self.history_authority(epoch)
        return self._slice(epoch, pa, length, role, authority=authority)

    def _slice(self, epoch, pa, length, role, *, authority=None):
        self.require_epoch(epoch);extent(pa, length);check(length <= MAX_SLICE, 'ordinary slice exceeds 16MiB')
        hits = [r for r in self._epochs[epoch]['bulks'] if r['physical'] <= pa
                and pa + length <= r['physical'] + r['length']]
        check(len(hits) == 1, 'physical request missing from current immutable bulk coverage')
        source = hits[0];off = pa - source['physical'];raw = self._blobs[source['id']][1][off:off + length]
        name = 'physical-e%04d-%06d.bin' % (epoch, self._next_slice);self._next_slice += 1
        ref = dict(physical=pa, length=length, role=role, file=name, sha256=digest(raw),
                   epoch=epoch, bulk_id=source['id'], offset=off)
        self._queue_file(name, raw, epoch=epoch, kind='slice', authority=authority)
        self._refs[name] = canonical(ref);self.chunks.append(ref)
        return raw, copy.deepcopy(ref)

    def read(self, ref, epoch):
        self.require_epoch(epoch)
        check(isinstance(ref, dict) and self._refs.get(ref.get('file')) == canonical(ref), 'slice not in exact registry')
        check(ref['epoch'] == epoch, 'mixed capture epoch')
        source = next((r for r in self._epochs[epoch]['bulks'] if r['id'] == ref['bulk_id']), None)
        check(source is not None and type(ref['offset']) is int and ref['offset'] >= 0
              and 0 < ref['length'] <= MAX_SLICE and ref['offset'] + ref['length'] <= source['length']
              and ref['physical'] == source['physical'] + ref['offset'], 'slice PA/offset/source differs')
        raw = self._blobs[source['id']][1][ref['offset']:ref['offset'] + ref['length']]
        check(digest(raw) == ref['sha256'], 'slice differs from immutable bulk bytes')
        return raw

    def register_source(self, epoch, cpu, text, *, observation):
        self.require_epoch(epoch);check(type(cpu) is int and 0 <= cpu < 4 and isinstance(text, str), 'invalid actual HMP source')
        sources = self._epochs[epoch]['registers'];index = len(sources)
        if self.profile == SCHEMA:
            check(self._epochs[epoch]['observation'] is None
                  and not any(s['cpu_index'] == cpu for s in sources), 'HMP repeated after observation seal')
        raw = text.encode('utf-8');name = 'register-source-e%04d-c%d-%04d.txt' % (epoch, cpu, index)
        self._queue_file(name, raw, epoch=epoch, kind='register-source')
        source = dict(source_id='e%d:r%d' % (epoch, index), epoch=epoch, cpu_index=cpu,
                      command='info registers', file=name, sha256=digest(raw), length=len(raw),
                      observation=copy.deepcopy(observation))
        sources.append(source);self._texts[source['source_id']] = (canonical(source), text)
        return source['source_id']

    def seal_observation(self, epoch, serial, status):
        self.require_epoch(epoch);record = self._epochs[epoch]
        check(self.profile == SCHEMA and record['observation'] is None and record['resume'] is None,
              'observation already sealed or wrong capture profile')
        check(type(serial) is bytes and status.get('running') is False and status.get('status') == 'paused'
              and serial.startswith(bytes.fromhex(record['serial_hex']))
              and len(record['registers']) == 4 and {s['cpu_index'] for s in record['registers']} == set(range(4)),
              'observation requires six bulk/four actual paused HMP and fixed UART')
        record['aliases'] = [dict(cpu_index=s['cpu_index'], file=s['file'], sha256=s['sha256'],
            epoch=epoch, source_id=s['source_id']) for s in record['registers']]
        record['observation'] = dict(sealed_ns=time.monotonic_ns(), serial_offset=len(serial),
            serial_sha256=digest(serial), serial_hex=serial.hex(), status=copy.deepcopy(status))

    def sealed_register_ref(self, epoch, cpu):
        self.require_epoch(epoch);record = self._epochs[epoch]
        check(self.profile == SCHEMA and record.get('observation') is not None, 'register observation not sealed')
        refs = [r for r in record['aliases'] if r['cpu_index'] == cpu]
        check(type(cpu) is int and len(refs) == 1, 'sealed CPU register ref missing')
        return copy.deepcopy(refs[0])

    def register_ref(self, epoch, cpu, path):
        check(self.profile == PAUSED_SCHEMA, 'v3 register refs must use the four sealed sources')
        self.require_epoch(epoch);path = Path(path)
        check(path.resolve().parent == self.root, 'register alias escaped state directory')
        raw = ordinary(self.root, path.name).read_bytes()
        sources = [s for s in self._epochs[epoch]['registers'] if s['cpu_index'] == cpu]
        check(bool(sources), 'register ref missing actual same-epoch HMP source')
        source = sources[-1]
        check(raw == self._texts[source['source_id']][1].encode('utf-8'), 'register alias differs from actual HMP source')
        ref = dict(cpu_index=cpu, file=path.name, sha256=digest(raw), epoch=epoch, source_id=source['source_id'])
        check(path.name not in self._files, 'register alias file reused')
        self._files[path.name] = (len(raw), ref['sha256']);self._epochs[epoch]['aliases'].append(ref)
        return copy.deepcopy(ref)

    def text(self, ref, epoch):
        self.require_epoch(epoch)
        check(ref in self._epochs[epoch]['aliases'] and ref.get('epoch') == epoch, 'mixed/unregistered register epoch')
        found = self._texts.get(ref.get('source_id'));check(found is not None, 'register source missing')
        source = json.loads(found[0])
        check(source['epoch'] == epoch and source['cpu_index'] == ref['cpu_index']
              and source['command'] == 'info registers' and digest(found[1].encode('utf-8')) == ref['sha256'],
              'register source CPU/epoch/bytes differs')
        return found[1]

    def mark_resume(self, epoch, record):
        self.require_epoch(epoch);check(self._epochs[epoch]['resume'] is None, 'epoch resumed twice')
        self._epochs[epoch]['resume'] = copy.deepcopy(record)

    def reject_resume_bookkeeping(self, epoch, record, secondary):
        """No I/O: retain actual cont facts while revoking all running authority."""
        self.require_epoch(epoch)
        failed = copy.deepcopy(record)
        failed['bookkeeping_error'] = secondary
        if failed['error'] is None:
            failed['error'] = 'resume bookkeeping failed: ' + secondary
        self._epochs[epoch]['resume'] = failed

    def epoch(self, epoch):
        self.require_epoch(epoch);return copy.deepcopy(self._epochs[epoch])

    def save(self):
        index = dict(schema=self.profile, metadata=self.metadata.binding, epochs=list(self._epochs.values()),
                     slices=self.chunks, materializations=self.materializations())
        write(self.root / INDEX, index)
        return digest((self.root / INDEX).read_bytes())

    def materializations(self):
        return copy.deepcopy(dict(files=list(self._writes.values()), batches=self._batches))

    def _verify_materializations(self):
        expected = {ref['file']: (ref['epoch'], 'slice', ref['length'], ref['sha256']) for ref in self.chunks}
        for epoch in self._epochs.values():
            for source in epoch['registers']:
                expected[source['file']] = (source['epoch'], 'register-source', source['length'], source['sha256'])
        check(not self._pending and set(self._writes) == set(expected), 'pending/unregistered capture files remain unmaterialized')
        previous = 0
        exit_receipt = None
        for position, batch in enumerate(self._batches, 1):
            check(type(batch['id']) is int and batch['id'] == position and batch['error'] is None
                  and type(batch['count']) is int
                  and type(batch['started_ns']) is int and type(batch['completed_ns']) is int
                  and previous <= batch['started_ns'] <= batch['completed_ns'], 'materialization batch failed/unordered')
            boundary = self._authorize_flush(batch['phase'], batch['evidence'], latest=False)
            if batch['phase'] == 'resume' and batch['evidence']['epoch'] < len(self._epochs):
                following = self._epochs[batch['evidence']['epoch'] + 1]
                check(batch['completed_ns'] <= following['stop']['requested_ns'],
                      'resumed materialization crossed the next paused epoch')
            if batch['phase'] == 'exit':
                if exit_receipt is None:
                    exit_receipt = json.loads(ordinary(self.root, 'guest.json').read_bytes())['owned_process_exit']
                check(batch['evidence'] == exit_receipt, 'materialization exit differs from owned guest cleanup receipt')
            check(boundary <= batch['started_ns'], 'materialization preceded resume/exit confirmation')
            files = [r for r in self._writes.values() if r['batch'] == position]
            check(len(files) == batch['count'] and bool(files), 'materialization batch count differs')
            for record in files:
                fields = {'file', 'epoch', 'kind', 'length', 'sha256', 'queued_ns', 'materialized_ns', 'batch'}
                if self.profile == SCHEMA: fields.add('derivation')
                check(set(record) == fields,
                      'invalid materialization file record')
                epoch = self._epochs[record['epoch']]
                check(type(record['queued_ns']) is int and type(record['materialized_ns']) is int
                      and epoch['sealed_ns'] <= record['queued_ns'] <= batch['started_ns']
                      <= record['materialized_ns'] <= batch['completed_ns'],
                      'file queued/materialized outside its actual capture/flush phases')
                self._validate_derivation(record, epoch)
                wanted = expected[record['file']]
                check((record['epoch'], record['kind'], record['length'], record['sha256']) == wanted,
                      'materialized file source/length/hash differs')
                if record['kind'] == 'register-source':
                    source = next(s for s in epoch['registers'] if s['file'] == record['file'])
                    check(source['observation']['completed_ns'] <= record['queued_ns'], 'HMP queued before actual observation')
            previous = batch['completed_ns']
        check({r['file'] for r in self._writes.values() if type(r['batch']) is int and 0 < r['batch'] <= len(self._batches)}
              == set(expected), 'capture file missing exact materialization batch')

    def verify_all(self):
        # Deliberately ignores caches for final disk authentication.
        check(bool(self._epochs), 'no sealed capture epoch to authenticate')
        check(len(self.chunks) == len(self._refs)
              and {ref['file']: canonical(ref) for ref in self.chunks} == self._refs,
              'registered slice manifest was changed/removed')
        self._verify_materializations()
        for name, (length, wanted) in self._files.items():
            raw = ordinary(self.root, name).read_bytes();self.disk_reads += 1
            check(len(raw) == length and digest(raw) == wanted, 'final disk capture bytes/hash changed: ' + name)
        serial = ordinary(self.root, 'serial.log').read_bytes()
        first_boot = None;previous = None
        for epoch, record in self._epochs.items():
            self._validate_timeline(record)
            boundary = record['stop']['serial_offset']
            check(serial[:boundary] == bytes.fromhex(record['serial_hex'])
                  and boundary <= len(serial), 'epoch UART boundary differs from actual serial log')
            if self.profile == SCHEMA:
                observed = record['observation'];end = observed['serial_offset']
                check(serial[:end] == bytes.fromhex(observed['serial_hex']) and end <= len(serial),
                      'sealed observation UART differs from actual serial log')
            if previous is not None:
                end = previous['resume']
                check(end is not None and end['performed'] is True
                      and end['completed_ns'] <= record['stop']['requested_ns'], 'new epoch lacks explicit prior cont')
            previous = record
            blobs = {r['kind']: ordinary(self.root, r['file']).read_bytes() for r in record['bulks']}
            if first_boot is None:
                first_boot = blobs['boot-info']
            check(first_boot == blobs['boot-info'], 'immutable BootInfo changed between capture epochs')
            rsdp = blobs['rsdp']
            check(rsdp[:8] == b'RSD PTR ' and len(rsdp) >= 36 and sum(rsdp[:20]) & 255 == 0
                  and rsdp[15] >= 2 and struct.unpack_from('<I', rsdp, 20)[0] == len(rsdp)
                  and sum(rsdp) & 255 == 0, 'final RSDP checksum/length differs')
            derived = self.metadata.derive(blobs['boot-info'], blobs['kernel'], blobs['map'], bytes.fromhex(record['serial_hex']))
            check(derived == record['derived'], 'final disk derived range contract differs')
            for ref in record['bulks']:
                check(derived['ranges'][ref['kind']] == [ref['physical'], ref['length']], 'bulk PA/extent not source-derived')
            for ref in self.chunks:
                if ref['epoch'] == epoch:
                    check(ordinary(self.root, ref['file']).read_bytes() == self.read(ref, epoch), 'final slice differs from parent bulk')
            for ref in record['aliases']:
                check(ordinary(self.root, ref['file']).read_bytes().decode('utf-8') == self.text(ref, epoch), 'final register alias changed')
        index = ordinary(self.root, INDEX)
        expected = dict(schema=self.profile, metadata=self.metadata.binding, epochs=list(self._epochs.values()),
                        slices=self.chunks, materializations=self.materializations())
        check(json.loads(index.read_text(encoding='utf-8')) == expected, 'bulk index changed after capture')

    @staticmethod
    def _validate_timeline(record):
        stop = record['stop'];serial = bytes.fromhex(record['serial_hex'])
        check(stop['status'].get('running') is False and stop['status'].get('status') == 'paused'
              and type(stop['requested_ns']) is int and stop['requested_ns'] <= stop['confirmed_ns'] <= record['sealed_ns']
              and stop['serial_offset'] == len(serial) and stop['serial_sha256'] == digest(serial),
              'epoch lacks an actual paused confirmation/serial boundary')
        previous = stop['confirmed_ns']
        for ref in record['bulks']:
            check(previous <= ref['started_ns'] <= ref['completed_ns'] <= record['sealed_ns'], 'bulk not within paused epoch')
            if 'host_stages' in ref:
                stages = ref['host_stages']
                check('observation' in record and isinstance(stages, dict) and set(stages) == set(HOST_STAGE_FIELDS)
                      and all(type(stages[k]) is int for k in HOST_STAGE_FIELDS), 'invalid bulk host stages')
                ordered = [stages[k] for k in HOST_STAGE_FIELDS]
                check(ref['started_ns'] == ordered[0] and ordered == sorted(ordered)
                      and ordered[-1] <= ref['completed_ns'], 'bulk host stages are not within the actual dump')
            request = ref['request']
            check(request['command'] == 'pmemsave' and request['arguments']['val'] == ref['physical']
                  and request['arguments']['size'] == ref['length']
                  and Path(request['arguments']['filename']).name == ref['file']
                  and ref['response'] == {}, 'actual bounded pmemsave receipt differs')
            previous = ref['completed_ns']
        end = record['resume']
        if end is not None:
            check(record['sealed_ns'] <= end['requested_ns'] <= end['completed_ns']
                  and end['elapsed_ns'] == end['completed_ns'] - stop['requested_ns'], 'invalid full pause envelope')
            check(type(end['performed']) is bool and end['budget_ns'] == PAUSE_BUDGET_NS
                  and end['original_progress'] == record['derived']['progress'] and end.get('error') is None,
                  'resume budget/progress/actual confirmation differs')
            check(end['performed'] is True, 'observer-disturbed: explicit resume was rejected')
            check(not end['performed'] or end['elapsed_ns'] <= PAUSE_BUDGET_NS,
                  'observer-disturbed: actual stop-to-cont envelope exceeded budget')
            check(end['status'].get('running') is end['performed']
                  and end['status'].get('status') == ('running' if end['performed'] else 'paused'), 'resume status differs')
        for source in record['registers']:
            o = source['observation']
            check(record['sealed_ns'] <= o['started_ns'] <= o['completed_ns']
                  and (end is None or o['completed_ns'] <= end['requested_ns'])
                  and o['status'].get('running') is False and o['status'].get('status') == 'paused',
                  'HMP register source outside stopped epoch')
        if 'observation' in record:
            observed = record['observation']
            check(isinstance(observed, dict) and set(observed) == {'sealed_ns','serial_offset','serial_sha256','serial_hex','status'}
                  and len(record['registers']) == len(record['aliases']) == 4
                  and record['aliases'] == [dict(cpu_index=s['cpu_index'], file=s['file'], sha256=s['sha256'],
                      epoch=record['epoch'], source_id=s['source_id']) for s in record['registers']]
                  and {r['cpu_index'] for r in record['registers']} == set(range(4))
                  and all(s['observation']['completed_ns'] <= observed['sealed_ns'] for s in record['registers'])
                  and record['sealed_ns'] <= observed['sealed_ns']
                  and (end is None or observed['sealed_ns'] <= end['requested_ns'])
                  and observed['status'].get('running') is False and observed['status'].get('status') == 'paused'
                  and observed['serial_offset'] == len(bytes.fromhex(observed['serial_hex']))
                  and observed['serial_sha256'] == digest(bytes.fromhex(observed['serial_hex']))
                  and bytes.fromhex(observed['serial_hex']).startswith(serial),
                  'incomplete/mixed paused observation seal')

    @classmethod
    def from_disk(cls, root, manifest, metadata, *, profile=PAUSED_SCHEMA):
        check(isinstance(metadata, Metadata), 'explicit trusted replay metadata required')
        root = Path(root).resolve();index = json.loads(ordinary(root, INDEX).read_text(encoding='utf-8'))
        check(set(index) == {'schema', 'metadata', 'epochs', 'slices', 'materializations'} and index['schema'] == profile
              and index['metadata'] == metadata.binding and index['slices'] == manifest
              and isinstance(index['epochs'], list) and bool(index['epochs']), 'bulk manifest/metadata differs')
        result = cls(root, metadata, profile=profile)
        writes = index['materializations']
        check(set(writes) == {'files', 'batches'} and isinstance(writes['files'], list)
              and isinstance(writes['batches'], list), 'materialization manifest missing')
        result._writes = {r['file']: copy.deepcopy(r) for r in writes['files']}
        check(len(result._writes) == len(writes['files']), 'duplicate materialized file record')
        result._batches = copy.deepcopy(writes['batches'])
        for record in index['epochs']:
            epoch = record['epoch'];check(type(epoch) is int and epoch == len(result._epochs) + 1, 'invalid epoch sequence')
            check(len(record['bulks']) == 6 and {r['kind'] for r in record['bulks']} == {'boot-info','kernel','map','buddy','service','rsdp'},
                  'bounded bulk set missing/duplicated')
            result._epochs[epoch] = copy.deepcopy(record)
            check(('observation' in record) == (profile == SCHEMA), 'epoch profile/observation mismatch')
            for ref in record['bulks']:
                extent(ref['physical'], ref['length']);check(ref['length'] <= ARENA and ref['epoch'] == epoch
                    and ref['id'] == 'e%d:%s' % (epoch, ref['kind']) and ref['id'] not in result._blobs, 'bulk source identity differs')
                raw = ordinary(root, ref['file']).read_bytes();result.disk_reads += 1
                check(len(raw) == ref['length'] and digest(raw) == ref['sha256'] and ref['file'] not in result._files,
                      'bulk file/hash differs')
                result._blobs[ref['id']] = (canonical(ref), raw);result._files[ref['file']] = (len(raw), ref['sha256'])
            for source_index, source in enumerate(record['registers']):
                raw = ordinary(root, source['file']).read_bytes();result.disk_reads += 1
                check(type(source['epoch']) is int and source['epoch'] == epoch
                      and source['source_id'] == 'e%d:r%d' % (epoch, source_index)
                      and source['command'] == 'info registers' and type(source['cpu_index']) is int and 0 <= source['cpu_index'] < 4
                      and source['source_id'] not in result._texts and source['file'] not in result._files
                      and len(raw) == source['length'] and digest(raw) == source['sha256'], 'register source differs')
                result._texts[source['source_id']] = (canonical(source), raw.decode('utf-8'))
                result._files[source['file']] = (len(raw), source['sha256'])
            for ref in record['aliases']:
                shared = profile == SCHEMA and any(s['file'] == ref['file'] and s['source_id'] == ref['source_id']
                                                   for s in record['registers'])
                check(shared or ref['file'] not in result._files, 'duplicate register alias file')
                raw = ordinary(root, ref['file']).read_bytes();result.disk_reads += 1
                result._files[ref['file']] = (len(raw), ref['sha256'])
                check(raw.decode('utf-8') == result.text(ref, epoch), 'register alias/source differs')
        exits = [v['evidence'] for v in result._batches if v['phase'] == 'exit']
        if exits:
            result._owned_exit = copy.deepcopy(exits[0])
        for ref in manifest:
            check(ref['file'] not in result._files, 'duplicate slice file')
            result._refs[ref['file']] = canonical(ref);result.chunks.append(copy.deepcopy(ref))
            raw = ordinary(root, ref['file']).read_bytes();result.disk_reads += 1
            check(raw == result.read(ref, ref['epoch']), 'slice/bulk bytes differ')
            result._files[ref['file']] = (len(raw), digest(raw))
        result.verify_all()
        return result
