"""Explicit actual AP-PCID QEMU gate. Default only verifies a completed build."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import re
import struct
import sys
import time
import uuid
from unittest import mock

from tests import p2_pcid_build as build
from tests import p2_pcid_oracle as oracle
from tests import p2_bulk_capture as bulk
from tests import run_process_lifecycle_qemu as life
from tests import run_current_user_smp_qemu as prior
from tools.elf_symbols import read_elf_symbols
from tools.make_fat32_disk import create
from tools.kernel_storage_profile import verify_profile

ROOT = build.ROOT
check, write, sha = build.check, build.write, build.sha
settings, storage = life.settings, life.storage
INITIAL_GUI_LOG = b'DONGOS_GUI_APP_READY\r\n'
INITIAL_GUI_LOG_COUNT = 4
INITIAL_CLIENTS_LOG = b'DONGOS_P7_CLIENTS_READY\r\n'
LOCK_FREE = oracle.LOCK_FREE
CURRENT_OWNER = oracle.CURRENT_OWNER


def capture_metadata(esp):
    return bulk.Metadata.from_esp(esp)


def _drive_options(value):
    """Parse QEMU key/value separators without consuming escaped file commas."""
    check(type(value) is str and bool(value), 'actual drive options missing')
    parts, start, at = [], 0, 0
    while at < len(value):
        if value[at] != ',':
            at += 1
        elif at + 1 < len(value) and value[at + 1] == ',':
            at += 2
        else:
            parts.append(value[start:at]);at += 1;start = at
    parts.append(value[start:])
    options = {}
    for part in parts:
        key, separator, data = part.partition('=')
        check(separator == '=' and re.fullmatch(r'[A-Za-z0-9_.-]+', key) is not None
              and bool(data) and key not in options, 'ambiguous/duplicate actual drive option')
        options[key] = data.replace(',,', ',')
    return options


def _whpx_vars_command(command, *, require_cache=False):
    """Only mutable VARS gains writethrough; no other backend is rewritten."""
    command = list(command)
    forbidden = {'-snapshot','-blockdev','-set','-global','-readconfig','-pflash',
                 '-hda','-hdb','-hdc','-hdd','-cdrom'}
    check(not any(arg in forbidden or arg.startswith('-snapshot=') for arg in command),
          'WHPX drive configuration has a global/alternate backend override')
    indexes = [i + 1 for i, arg in enumerate(command) if arg == '-drive']
    check(len(indexes) == 4 and all(i < len(command) for i in indexes),
          'WHPX requires exact CODE/VARS/ESP/data drives')
    drives = [(i, _drive_options(command[i])) for i in indexes]
    flash = [(i, o) for i, o in drives if o.get('if') == 'pflash']
    data = [(i, o) for i, o in drives if o.get('id') == 'data']
    esp = [(i, o) for i, o in drives if o.get('file', '').startswith('fat:rw:')]
    check(len(flash) == 2 and len(data) == len(esp) == 1
          and len({i for i, _ in flash + data + esp}) == 4,
          'WHPX CODE/VARS/ESP/data roles missing or ambiguous')
    _, code = flash[0]
    vars_index, variables = flash[1]
    base = {'if','format','file'}
    check(set(code) == base | {'readonly'} and code['readonly'] == 'on' and code['format'] == 'raw'
          and re.split(r'[/\\]', code['file'])[-1] != 'OVMF_VARS.fd',
          'WHPX CODE must remain first readonly raw pflash without cache overrides')
    check(base <= set(variables) <= base | {'readonly','cache'} and variables['format'] == 'raw'
          and variables.get('readonly', 'off') == 'off'
          and re.split(r'[/\\]', variables['file'])[-1] == 'OVMF_VARS.fd',
          'WHPX mutable OVMF_VARS.fd must remain second raw pflash')
    check(variables.get('cache') in (None, 'writethrough'), 'WHPX VARS cache differs from writethrough')
    check(not require_cache or variables.get('cache') == 'writethrough',
          'recorded WHPX VARS lacks explicit writethrough cache')
    _, disk = data[0]
    disk_keys = {'if','id','format','cache','file'}
    check(disk_keys <= set(disk) <= disk_keys | {'readonly'} and disk['if'] == 'none'
          and disk['format'] == 'raw' and disk['cache'] == 'writeback'
          and disk.get('readonly', 'off') == 'off',
          'WHPX data must remain writable raw id=data with cache=writeback')
    _, efi = esp[0]
    check(set(efi) == {'format','file'} and efi['format'] == 'raw' and len(efi['file']) > len('fat:rw:'),
          'WHPX ESP must remain the original raw fat:rw drive without cache overrides')
    check(len({o['file'] for _, o in drives}) == 4, 'WHPX backend file identities overlap')
    if variables.get('cache') is None:
        command[vars_index] += ',cache=writethrough'
    return command


def launch_command(command, *, accel, cpu, kernel_irqchip=None):
    """Keep the optional WHPX interrupt backend explicit in the real argv."""
    check(accel in ('tcg', 'whpx', 'kvm') and isinstance(cpu, str) and bool(cpu),
          'explicit supported accelerator/CPU required')
    check(kernel_irqchip is None or kernel_irqchip == 'off' and accel == 'whpx',
          'kernel-irqchip=off is an explicit WHPX-only configuration')
    command = list(command)
    check(all(command.count(flag) == 1 for flag in ('-cpu', '-accel', '-smp', '-machine')),
          'ambiguous actual QEMU command')
    check(command[command.index('-accel') + 1] == accel
          and command[command.index('-smp') + 1] == '4'
          and command[command.index('-machine') + 1] in
              (('q35', 'q35,kernel-irqchip=off') if accel == 'whpx' and kernel_irqchip == 'off' else ('q35',)),
          'actual accelerator/topology/machine differs')
    command[command.index('-cpu') + 1] = cpu
    if kernel_irqchip == 'off':
        command[command.index('-machine') + 1] = 'q35,kernel-irqchip=off'
    if accel == 'whpx':
        command = _whpx_vars_command(command)
    return command


def verify_launch_command(command, *, accel, cpu, kernel_irqchip=None):
    if accel == 'whpx':
        _whpx_vars_command(command, require_cache=True)
    expected = list(command)
    check(expected.count('-machine') == 1, 'actual machine missing/duplicated')
    expected[expected.index('-machine') + 1] = 'q35'
    expected = launch_command(expected, accel=accel, cpu=cpu, kernel_irqchip=kernel_irqchip)
    check(command == expected, 'actual command differs from recorded launch configuration')


def elf_contract(esp):
    esp = Path(esp)
    static_pools = verify_profile(esp.parent, json.loads((esp.parent / 'build-inputs.json').read_text(encoding='utf-8')),
                                  expected_runtime=7, source_root=esp.parent.parent / 'source')
    symbols = read_elf_symbols(esp.parent / 'kernel.elf')
    layout = json.loads((esp.parent / 'dong_layout.json').read_text(encoding='utf-8'))
    types = {t['full_name']: t for t in layout['types']}
    for name, size in {'sched.user_boot.Report': 80, 'sched.user_domain.Domain': 120,
                       'sched.user_domain.Cpu': 120, 'sched.user_domain.Process': 56,
                       'sched.user_entry_plan.Cpu': 256, 'sched.user_entry_plan.Metrics': 192,
                       'sched.multicore.Engine': 12960, 'user.memory.Process': 1288, 'mm.paging.Space': 64}.items():
        check(types[name]['size'] == size, 'actual compiler layout differs: ' + name)
    space_offsets = {f['name']: f['offset'] for f in types['mm.paging.Space']['fields']}
    check(all(space_offsets.get(n) == v for n, v in {'initialized': 0, 'pool': 8, 'pool_count': 16,
          'pool_physical': 24, 'metadata': 32, 'address_mask': 40, 'nx_supported': 48, 'used_total': 56}.items()),
          'actual private Space offsets differ')
    return dict(static_pools=static_pools, info_symbol=symbols[storage.symbol('sched.user_boot', 'INFO')],
                syscall_entry=symbols['user_smp_syscall_entry'],
                memory_processes=symbols[storage.symbol('user.memory', 'PROCESSES')],
                worker_elfs={cfg: str(esp.parent / 'services' / life.NAMES[cfg] / 'program.elf') for cfg in oracle.ARGS},
                global_symbols={**{n: symbols[storage.symbol('user.memory', source)] for n, source in
                    [('pool_limits', 'POOL_LIMITS'), ('dynamic_physical', 'DYNAMIC_PHYSICAL'),
                     ('dynamic_tables', 'DYNAMIC_TABLES'), ('spaces', 'SPACES'), ('meta', 'META'), ('generations','GENERATIONS'), ('static_table_anchor', 'TABLES')]},
                    'catalog_pointer': symbols[storage.symbol('user.services', 'CATALOG')],
                    'arena_plan': symbols[storage.symbol('boot.service_memory','PLAN')],
                    'arena_next': symbols[storage.symbol('boot.service_memory','NEXT_PAGE')]})


class Capture:
    """Record the exact page-table and data reads, with an immutable per-stop cache."""
    def __init__(self, guest):
        self.guest = guest
        base, pages = guest.trusted_kernel_pool()
        self.pool = [base, pages, guest.evidence['trusted_kernel_page_table_pool']['root_physical']]
        self.cache = {}

    def physical(self, address, length, role, *, table=False):
        key = (address, length)
        if table and key in self.cache:
            return self.cache[key]
        raw = self.guest.physical(address, length, role)
        result = (raw, copy.deepcopy(self.guest.chunks[-1]))
        if table:
            self.cache[key] = result
        return result

    def part(self, address, length, role, *, root=None, private_pages=None):
        root = self.pool[2] if root is None else root
        allowed = [(self.pool[0], self.pool[0] + self.pool[1] * 4096)]
        if private_pages is not None:
            allowed.append((root, root + private_pages * 4096))
        record = dict(virtual=address, length=length, root=root, pages=[])
        out, remaining = bytearray(), length
        while remaining:
            table, refs = root, []
            for shift in (39, 30, 21, 12):
                check(table % 4096 == 0 and any(a <= table <= b - 4096 for a, b in allowed), 'capture table outside owned pools')
                raw, ref = self.physical(table, 4096, role + ' ancestor', table=True)
                refs.append(ref)
                entry = struct.unpack_from('<Q', raw, ((address >> shift) & 511) * 8)[0]
                check(entry & 1, 'capture mapping absent')
                if shift == 12 or shift in (30, 21) and entry & 128:
                    physical = (entry & storage.MASK & ~((1 << shift) - 1)) + (address & ((1 << shift) - 1))
                    break
                table = entry & storage.MASK
            count = min(remaining, 4096 - (address & 4095))
            raw, ref = self.physical(physical, count, role + ' data')
            record['pages'].append(dict(steps=refs, data=ref))
            out.extend(raw)
            address += count
            remaining -= count
        return bytes(out), record


class PcidGuest(life.ProcessGuest):
    historical_capture = True

    def __init__(self, esp, disk, state, *, accel='tcg', cpu='max,+smep,+smap,+umip', kernel_irqchip=None):
        self.snapshot_number = 0
        # All source-bound ELF/layout/profile reads precede Popen and the first
        # virtual pause call made by the underlying constructor.
        self._capture_metadata = capture_metadata(esp)
        self._capture_registry = None
        self._active_epoch = None
        self._boot_info_ref = None
        self._observer_events = []
        self._initial_run_seconds = 2.0
        self._initial_gui_timeout_seconds = 90.0
        self._pause_budget_ns = bulk.PAUSE_BUDGET_NS
        self.contract = elf_contract(esp)
        self.symbols = settings.acpi.validation_symbols(Path(esp).parent / 'kernel.elf')
        self.static_pools = self.contract['static_pools']
        check(self.static_pools == 1, 'expected actual current runtime7 storage profile')
        original_command = settings.builder.qemu_command
        original_nvme = life.nvme.nvme_command

        def command(*args, **kwargs):
            kwargs['accel'] = accel
            return original_command(*args, **kwargs)

        def device(command):
            command = original_nvme(command)
            return launch_command(command, accel=accel, cpu=cpu, kernel_irqchip=kernel_irqchip)

        # Routing only: both adapters invoke the real existing command/device
        # builders, and ProcessGuest invokes the actual subprocess.Popen.
        with mock.patch.object(settings.builder, 'qemu_command', command), \
                mock.patch.object(life.nvme, 'nvme_command', device):
            super().__init__(Path(esp), Path(disk), Path(state))

    @property
    def current_epoch(self):
        check(self.stopped and self._active_epoch is not None, 'no sealed paused observation epoch')
        self._capture_registry.require_epoch(self._active_epoch)
        return self._active_epoch

    @property
    def current_boot_info_ref(self):
        check(self._boot_info_ref is not None and self._boot_info_ref['epoch'] == self.current_epoch,
              'current epoch BootInfo slice missing')
        return copy.deepcopy(self._boot_info_ref)

    def snapshot_archive(self):
        return oracle.Archive(self.state, self.chunks, registry=self._capture_registry).begin_snapshot(self.current_epoch)

    def capture_image(self, label='checkpoint'):
        check(self.historical_capture is True, 'explicit v3 historical capture required')
        self.pause()
        return CapturedImage(self._capture_registry, self.current_epoch, self.current_boot_info_ref,
                             esp=self.esp, symbols=self.symbols, contract=self.contract, label=label)

    def bootstrap_audit(self):
        image = self.capture_image('bootstrap')
        self.resume()
        fields = life.audit_initial_process_image(image)
        for name in ('boot','processes','roots','bias','symbols','syms','pool_limits','static_pools'):
            setattr(self, name, fields[name])
        self.evidence.update(fields['evidence'])
        self.evidence['bootstrap_audit'] = dict(epoch=image.epoch, serial_offset=image.serial_offset,
            completed_ns=time.monotonic_ns(), historical=True, actual_cont_before_audit=True)
        self._bootstrap_audited = True
        image.flush()

    def _flush_running_capture(self):
        registry = self._capture_registry
        if registry is None:
            return
        latest = registry.epoch(len(registry._epochs))
        if latest['resume'] is not None:
            end = latest['resume']
            registry.flush_pending(phase='resume', evidence=dict(epoch=latest['epoch'],
                confirmed_ns=end['completed_ns'], status=copy.deepcopy(end['status'])))
            registry.save()

    def _wait_initial_gui_logs(self):
        """Drain fixed runtime7 startup logs while continuously running, before stop."""
        check(self.historical_capture is True and self._capture_registry is None and not self.stopped,
              'initial GUI log drain requires the untouched running v3 bootstrap')
        timeout = getattr(self, '_initial_gui_timeout_seconds', 90.0)
        check(type(timeout) in (int, float) and 0 <= timeout <= 90, 'invalid initial GUI log deadline')
        deadline = time.monotonic() + timeout
        receipt = dict(kind='initial-gui-log-drain', expected=INITIAL_GUI_LOG_COUNT,
            expected_clients=1, received=0, bare_received=0, clients_received=0, clients_bare_received=0,
            started_ns=time.monotonic_ns(), completed_ns=None, complete=False,
            commands_sent=False, inspection_stop_sent=False)
        self.evidence['initial_gui_logs'] = receipt
        try:
            while True:
                serial = bytes(self.raw)
                offsets = [m.start() for m in re.finditer(re.escape(INITIAL_GUI_LOG), serial)]
                occurrences = serial.count(INITIAL_GUI_LOG[:-2])
                clients_offsets = [m.start() for m in re.finditer(re.escape(INITIAL_CLIENTS_LOG), serial)]
                clients_occurrences = serial.count(INITIAL_CLIENTS_LOG[:-2])
                receipt.update(received=len(offsets), bare_received=occurrences,
                    clients_received=len(clients_offsets), clients_bare_received=clients_occurrences,
                    serial_offset=len(serial))
                check(self.process.poll() is None and b'DONGOS_P1_KERNEL_FAIL' not in serial
                      and b'PANIC' not in serial, 'guest failed before initial GUI logs completed')
                check(occurrences <= INITIAL_GUI_LOG_COUNT, 'duplicate initial GUI ready log')
                check(clients_occurrences <= 1, 'duplicate initial clients-ready log')
                if time.monotonic() >= deadline:
                    raise TimeoutError('initial four complete GUI ready logs and one complete clients-ready log were not received')
                if len(offsets) == occurrences == INITIAL_GUI_LOG_COUNT and len(clients_offsets) == clients_occurrences == 1:
                    receipt.update(complete=True, completed_ns=time.monotonic_ns(),
                        marker_offsets=offsets, clients_marker_offsets=clients_offsets, serial_sha256=bulk.digest(serial))
                    self._observer_events.append(copy.deepcopy(receipt))
                    return
                # No QMP, UART command, RAM read or historical Catalog is used.
                # sys.ready_boot precedes the log syscall in gui_app.dg:169.
                # desktop.service.dg:495 emits its final aggregate separately.
                time.sleep(.02)
        except BaseException as exc:
            receipt.update(completed_ns=time.monotonic_ns(),
                error=type(exc).__name__ + ': ' + str(exc), serial_sha256=bulk.digest(bytes(self.raw)))
            self._observer_events.append(copy.deepcopy(receipt))
            raise

    def pause(self):
        if self.stopped:
            status = self.qmp.request('query-status')
            check(status.get('running') is False and status.get('status') == 'paused', 'VM left claimed stopped epoch')
            self.current_epoch
            return
        if self._capture_registry is None:
            # One continuous bootstrap window, before any inspection stop.
            # This never resumes an already paused VM or changes guest deadlines.
            start = time.monotonic_ns()
            time.sleep(self._initial_run_seconds)
            self._observer_events.append(dict(kind='initial-continuous-run', started_ns=start,
                                              completed_ns=time.monotonic_ns()))
            if self.historical_capture is True:
                self._wait_initial_gui_logs()
            profile = bulk.SCHEMA if self.historical_capture is True else bulk.PAUSED_SCHEMA
            self._capture_registry = bulk.EpochRegistry(self.state, self._capture_metadata, self.chunks, profile=profile)
        elif self.historical_capture is True:
            # Historical work is materialized during the previous true running
            # interval, before the next stop request begins.
            self._flush_running_capture()
        stages = None
        prepared = None
        if self.historical_capture is True:
            # Retiring a large old table cache can run arbitrary host allocator
            # work. Finish it, and canonical target preparation, while running.
            stages = dict(kind='capture-host-stages', started_ns=time.monotonic_ns(),
                          epoch=None, complete=False)
            stages['cache_reset_started_ns'] = time.monotonic_ns()
            self.tables = {}
            self._active_epoch = None
            stages['cache_reset_completed_ns'] = time.monotonic_ns()
            try:
                prepared = self._capture_registry.prepare_epoch()
            except BaseException as exc:
                stages.update(completed_ns=time.monotonic_ns(),
                              error=type(exc).__name__ + ': ' + str(exc))
                self._observer_events.append(stages)
                raise
            stages['preparation'] = prepared.receipt
            stages['epoch'] = stages['preparation']['epoch']
        requested = time.monotonic_ns()
        try:
            self.qmp.request('stop')
            status = self.qmp.request('query-status')
            confirmed = time.monotonic_ns()
            check(status.get('running') is False and status.get('status') == 'paused', 'actual QMP paused confirmation required')
        except BaseException as exc:
            if stages is not None:
                stages.update(stop_requested_ns=requested, completed_ns=time.monotonic_ns(),
                              error=type(exc).__name__ + ': ' + str(exc))
                self._observer_events.append(stages)
            raise
        self.stopped = True
        serial = bytes(self.raw)
        stop = dict(requested_ns=requested, confirmed_ns=confirmed, status=status,
                    serial_offset=len(serial), serial_sha256=bulk.digest(serial))
        if self.historical_capture is not True:
            self.tables = {}
            self._active_epoch = None
        else:
            stages.update(stop_requested_ns=requested, stop_confirmed_ns=confirmed,
                          serial_frozen_ns=time.monotonic_ns(), capture_started_ns=time.monotonic_ns())
        try:
            epoch = (self._capture_registry.capture_epoch(self.qmp, serial, stop, prepared=prepared)
                     if self.historical_capture is True
                     else self._capture_registry.capture_epoch(self.qmp, serial, stop))
            if stages is not None:
                stages['capture_completed_ns'] = time.monotonic_ns()
            status = self.qmp.request('query-status')
            check(status.get('running') is False and status.get('status') == 'paused', 'VM ran during bounded bulk capture')
            pa = bulk.uart_value(serial, 'runtime_boot_info') - bulk.HHDM
            _, self._boot_info_ref = self._capture_registry.slice(epoch, pa, 160, 'BootInfo')
            self._active_epoch = epoch
            if self.historical_capture is True:
                stages['boot_anchor_queued_ns'] = time.monotonic_ns()
                stages['hmp_started_ns'] = time.monotonic_ns()
                for cpu in range(4):
                    self.hmp(cpu, 'info registers')
                stages['hmp_completed_ns'] = time.monotonic_ns()
                status = self.qmp.request('query-status')
                stages['seal_started_ns'] = time.monotonic_ns()
                self._capture_registry.seal_observation(epoch, bytes(self.raw), status)
                stages.update(seal_completed_ns=time.monotonic_ns(), complete=True)
            self._observer_events.append(dict(kind='sealed-paused-epoch', epoch=epoch,
                                              completed_ns=time.monotonic_ns(), serial_offset=len(self.raw)))
            if self.historical_capture is not True:
                self._capture_registry.save()
        except BaseException as exc:
            if stages is not None:
                stages['error'] = type(exc).__name__ + ': ' + str(exc)
            raise
        finally:
            if stages is not None:
                stages['completed_ns'] = time.monotonic_ns()
                self._observer_events.append(stages)

    def resume(self):
        if not self.stopped:
            return
        epoch = self.current_epoch
        original = self._capture_registry.epoch(epoch)
        requested = time.monotonic_ns()
        elapsed = requested - original['stop']['requested_ns']
        status = self.qmp.request('query-status')
        check(status.get('running') is False and status.get('status') == 'paused', 'resume lost actual paused state')
        allowed = elapsed <= self._pause_budget_ns
        performed, error, primary = False, None, None
        try:
            if allowed:
                self._active_epoch = None
                self.qmp.request('cont')
                self.stopped = False
                status = self.qmp.request('query-status')
                check(status.get('running') is True and status.get('status') == 'running', 'actual QMP cont confirmation required')
                performed = True
        except BaseException as exc:
            primary = exc
            error = type(exc).__name__ + ': ' + str(exc)
            raise
        finally:
            completed = time.monotonic_ns()
            within_budget = completed - original['stop']['requested_ns'] <= self._pause_budget_ns
            record = dict(performed=performed, requested_ns=requested, completed_ns=completed,
                elapsed_ns=completed - original['stop']['requested_ns'], status=status,
                serial_offset=len(self.raw), budget_ns=self._pause_budget_ns, error=error,
                original_progress=original['derived']['progress'],
                observer_risk='pause may age existing absolute deadlines; no clock correction',
                reason='explicit runner resume' if performed and within_budget else 'observer-disturbed: pause budget or actual cont confirmation failed')
            try:
                self._capture_registry.mark_resume(epoch, record)
                self._observer_events.append(dict(kind='resume' if performed else 'observer-budget-rejection', epoch=epoch, **record))
                # V3 persists the complete index only after confirmed cont, or
                # after owned exit. Failed/denied cont keeps this memory-only.
                if self.historical_capture is not True:
                    self._capture_registry.save()
            except BaseException as secondary:
                message = type(secondary).__name__ + ': ' + str(secondary)
                # This memory-only record keeps the real performed/status facts
                # but makes even a completed cont unusable for history/flush.
                self._capture_registry.reject_resume_bookkeeping(epoch, record, message)
                self.evidence['resume_bookkeeping_failure'] = message
                if primary is None:
                    raise
        check(performed and within_budget, 'observer-disturbed: full stop-to-cont envelope exceeded capture budget; production verdict unavailable')
        # The saved epoch remains immutable, but ordinary files are deliberately
        # created only after the real VM has resumed and query-status confirmed it.
        try:
            if self.historical_capture is True:
                self._capture_registry.save()
            self._capture_registry.flush_pending(phase='resume', evidence=dict(epoch=epoch,
                confirmed_ns=record['completed_ns'], status=copy.deepcopy(record['status'])))
            self._capture_registry.save()
        except BaseException as secondary:
            # Even a real cont cannot authorize subsequent history if its
            # required materialization/index persistence failed.
            if self.historical_capture is True:
                message = type(secondary).__name__ + ': ' + str(secondary)
                self._capture_registry.reject_resume_bookkeeping(epoch, record, message)
                self.evidence['resume_bookkeeping_failure'] = message
            raise

    def settle(self):
        # The constructor calls this virtually after its paused ELF audits.
        # Only the runner's explicit resume()/shell()/stable_snapshot may cont.
        if self.historical_capture is True:
            check(getattr(self, '_bootstrap_audited', False) and not self.stopped,
                  'historical bootstrap audit must finish after explicit cont')
            return
        self.current_epoch
        status = self.qmp.request('query-status')
        check(status.get('running') is False and status.get('status') == 'paused', 'settle must retain stopped epoch')

    def physical(self, address, length, role):
        epoch = self.current_epoch
        raw, _ = self._capture_registry.slice(epoch, address, length, role)
        return raw

    def kernel(self, address, length, role):
        check(type(address) is int and bulk.KERNEL <= address <= bulk.KERNEL + bulk.WINDOW - length,
              'kernel read escaped actual loader window')
        # self.boot is intentionally unavailable at the first constructor pause.
        boot = bulk.boot_info(self._capture_registry.read(self.current_boot_info_ref, self.current_epoch))
        return self.physical(boot[15] + address - bulk.KERNEL, length, role)

    def register_ref(self, cpu, path):
        return self._capture_registry.register_ref(self.current_epoch, cpu, path)

    def validate_private_pools(self):
        limits = list(struct.unpack('<16Q', self.kernel(self.ksym('user.memory', 'POOL_LIMITS'), 128, 'actual pool limits')))
        check(limits == [32, 32, 32, 128] + [32] * 12, 'actual private capacities differ')
        self.pool_limits = limits
        dynamic = struct.unpack('<16Q', self.kernel(self.ksym('user.memory', 'DYNAMIC_PHYSICAL'), 128, 'actual dynamic table pools'))
        base = self.boot[15] + self.ksym('user.memory', 'TABLES') - storage.KERNEL
        ranges = []
        for slot, root in enumerate(self.roots):
            if not root:
                continue
            expected = base + slot * 32 * 4096 if slot < self.static_pools else dynamic[slot]
            check(root == expected and root > 0 and root % 4096 == 0, 'root not in its actual static/dynamic pool')
            end = root + limits[slot] * 4096
            check(all(not (root < stop and start < end) for start, stop in ranges), 'private pools overlap')
            ranges.append((root, end))
        self.evidence['trusted_private_pool_pages'] = limits

    def verify_process(self, pid, name):
        # The old ProcessGuest assumes four static slots. This variant uses
        # the source-bound STATIC_USER_POOLS=1 profile and checks complete RX
        # bytes, effective ancestors and double guards without that assumption.
        self.refresh_processes()
        self.validate_private_pools()
        root = self.roots[pid]
        check(root > 0 and root % 4096 == 0, 'process root missing')
        bias = struct.unpack_from('<Q', self.processes, pid * life.PROCESS_BYTES + 224)[0]
        check(0x10000000 <= bias <= 0x1fff0000 and bias % 65536 == 0, 'actual ASLR bias differs')
        path = self.esp.parent / 'services' / name / 'program.elf'
        raw = path.read_bytes()
        check(raw[:6] == b'\x7fELF\x02\x01', 'actual service ELF missing')
        start = struct.unpack_from('<Q', raw, 32)[0]
        stride, count = struct.unpack_from('<HH', raw, 54)
        kernel_pool = self.trusted_kernel_pool()
        tables = {}
        def read_table(pa):
            if pa not in tables:
                tables[pa] = self.physical(pa, 4096, 'complete ELF ancestor')
            return tables[pa]

        def mapping(address):
            return life.fat.effective_mapping(root, address,
                read_table, kernel_pool, self.private_pages(root))

        executable = 0
        for i in range(count):
            kind, flags, off, va, _, size, mem, _ = struct.unpack_from('<II6Q', raw, start + i * stride)
            if kind != 1:
                continue
            for page in range(va & ~4095, (va + mem + 4095) & ~4095, 4096):
                m = mapping(bias + page)
                check(m['present'] and m['effective_user'] and m['effective_nx'] == (not bool(flags & 1))
                      and m['effective_writable'] == bool(flags & 2) and m['leaf_bytes'] == 4096,
                      'actual complete ELF permissions differ')
                first, last = max(page, va), min(page + 4096, va + size)
                if flags & 1 and first < last:
                    check(self.physical(m['physical'] + first - page, last - first, 'actual executable ' + name)
                          == raw[off + first - va:off + last - va], 'actual service code differs')
                    executable += last - first
        rsp = struct.unpack_from('<Q', self.processes, pid * life.PROCESS_BYTES + 16 + 17 * 8)[0]
        top = (rsp & ~4095) + 4096
        for _ in range(4):
            if not mapping(top)['present']:
                break
            top += 4096
        check(0x7fbff01000 <= top <= 0x7ffff00000 and not mapping(top)['present']
              and not mapping(top - 5 * 4096)['present'], 'actual randomized double guard differs')
        return dict(pid=pid, image=name, root=root, bias=bias, executable_bytes=executable,
                    code_sha256=sha(path), stack_top=top, private_pool_pages=self.pool_limits[pid])

    def hmp(self, cpu, command):
        check(type(cpu) is int and 0 <= cpu < 4, 'invalid actual CPU index')
        check(command == 'info registers', 'only read-only register HMP is captured')
        epoch = self.current_epoch
        if self.historical_capture is True:
            check(self._capture_registry.epoch(epoch).get('observation') is None,
                  'four HMP sources already sealed; use CapturedImage.register_ref')
        started = time.monotonic_ns()
        text = self.qmp.request('human-monitor-command', {'command-line': command, 'cpu-index': cpu})
        status = self.qmp.request('query-status')
        check(status.get('running') is False and status.get('status') == 'paused', 'HMP ran outside stopped epoch')
        self._capture_registry.register_source(epoch, cpu, text,
            observation=dict(started_ns=started, completed_ns=time.monotonic_ns(), status=status))
        return text

    def catalog(self):
        pointer = self.kval('user.services', 'CATALOG')
        check(pointer >= 0xffff800000000000 and pointer % 8 == 0, 'actual Catalog pointer invalid')
        return oracle.catalog(self.virtual_kernel(pointer, life.CATALOG_BYTES, 'actual current R6 Catalog'))

    def snapshot(self, arguments, *, validate=True, require_pcid=True, observation_profile=LOCK_FREE):
        oracle.require_observation_profile(observation_profile)
        image = self.capture_image('pcid-' + str(self.snapshot_number))
        self.snapshot_number += 1
        self.resume()
        self._last_snapshot_image = image
        try:
            return image.snapshot(arguments, validate=validate, require_pcid=require_pcid,
                                  observation_profile=observation_profile)
        finally:
            primary = sys.exc_info()[1]
            try:
                image.flush()
            except BaseException as exc:
                self.evidence['historical_flush_failure'] = type(exc).__name__ + ': ' + str(exc)
                if primary is None:
                    raise

    def _assemble_snapshot(self, arguments, *, validate=True, require_pcid=True, observation_profile=LOCK_FREE):
        oracle.require_observation_profile(observation_profile)
        if observation_profile == CURRENT_OWNER and validate is True and arguments:
            # A necessary final worker gate, read from the already sealed HMP
            # sources before expensive historical pool/forest/ELF decoding.
            self.require_actual_ap_registers()
        self.initialize()
        capture = Capture(self)
        parts = {}

        def get(name, address, count, **kwargs):
            raw, parts[name] = capture.part(address, count, name, **kwargs)
            return raw

        pointer = struct.unpack('<Q', get('info_pointer', self.contract['info_symbol'], 8))[0]
        report = oracle.words(get('report', pointer, 80), 10)
        check(report[:5] == [1, 0, 1, 4, 15], 'four-CPU user SMP has not activated')
        domain = oracle.words(get('domain', report[5], 120), 15)
        oracle.validate_observation_domain(domain, observation_profile=observation_profile)
        headers = oracle.words(get('header_addresses', report[6], 32), 4)
        cpu_raw = get('cpus', domain[11], 4 * 120)
        domain_process_raw = get('processes', domain[12], 16 * 56)
        memory_raw = get('memory_processes', self.contract['memory_processes'], 16 * 1288)
        global_symbols = self.contract['global_symbols']
        for name, size in [('pool_limits', 128), ('dynamic_physical', 128), ('dynamic_tables', 128),
                           ('spaces', 16 * 64), ('meta', 16 * 128), ('generations',128), ('static_table_anchor', 8), ('catalog_pointer', 8),
                           ('arena_plan',48),('arena_next',8)]:
            get(name, global_symbols[name], size)
        catalog_pointer = struct.unpack('<Q', get('catalog_pointer', global_symbols['catalog_pointer'], 8))[0]
        get('catalog', catalog_pointer, life.CATALOG_BYTES)
        spaces_raw = oracle.part_bytes(parts['spaces'], self.snapshot_archive(), capture.pool)
        limits_raw = oracle.part_bytes(parts['pool_limits'], self.snapshot_archive(), capture.pool)
        pool_limits = oracle.words(limits_raw, 16)
        user_pools = {}
        for slot in range(16):
            ready, root = struct.unpack_from('<2Q', memory_raw, slot * 1288)
            if ready == 1:
                pool_virtual = struct.unpack_from('<Q', spaces_raw, slot * 64 + 8)[0]
                get('pool_anchor.' + str(slot), pool_virtual, pool_limits[slot]*4096)
                _, user_pools[str(slot)] = capture.physical(root, pool_limits[slot] * 4096, 'complete private table pool ' + str(slot))
        _, kernel_pool_ref = capture.physical(capture.pool[0], capture.pool[1] * 4096, 'complete retained kernel table pool')
        get('engine', domain[10], 12960)
        for i in range(4):
            h = oracle.words(get('header.' + str(i), headers[i], 256), 32)
            get('metrics.' + str(i), h[21] + 1024, 192)
            get('context.' + str(i), report[7] + i * 256, 256)
            c = oracle.words(cpu_raw[i * 120:(i + 1) * 120], 15)
            get('seen.' + str(i), c[14], 16 * 24)
        records = []
        catalog = self.catalog()
        self.refresh_processes()
        self.validate_private_pools()
        for cfg, argument in arguments.items():
            slot = catalog['slots'][cfg]
            check(type(slot) is int and 0 <= slot < 16, 'worker is not a live process')
            name = life.NAMES[cfg]
            image = self.verify_process(slot, name)
            symbols = read_elf_symbols(self.esp.parent / 'services' / name / 'program.elf')
            address = image['bias'] + symbols[storage.symbol('apps.' + name.replace('-', '_'), 'PROBE')]
            prefix = 'worker.' + str(cfg)
            get(prefix + '.probe', address, 192, root=image['root'], private_pages=32)
            get(prefix + '.fixed', 0x44000000, 8, root=image['root'], private_pages=32)
            process = oracle.words(domain_process_raw[slot * 56:(slot + 1) * 56], 7)
            get(prefix + '.xstate', process[4], 1024)
            elf = (self.esp.parent / 'services' / name / 'program.elf').read_bytes()
            start = struct.unpack_from('<Q', elf, 32)[0]
            stride, count = struct.unpack_from('<HH', elf, 54)
            for index in range(count):
                kind, flags, off, virtual, _, size, _, _ = struct.unpack_from('<II6Q', elf, start + index * stride)
                if kind == 1 and flags & 1 and size:
                    get(prefix + '.code.' + str(index), image['bias'] + virtual, size,
                        root=image['root'], private_pages=32)
            records.append(dict(cfg=cfg, argument=argument, slot=slot, token=catalog['snapshots'][cfg]['process'],
                                incarnation=catalog['incarnations'][slot], probe_address=address))
        regs = [self.register_ref(cpu) for cpu in range(4)]
        record = dict(epoch=self.epoch, serial_offset=self.serial_offset, observation_profile=observation_profile,
                      kernel_pool=capture.pool, kernel_pool_ref=kernel_pool_ref, user_pools=user_pools,
                      parts=parts, registers=regs, workers=records)
        decoded = oracle.decode_snapshot(record, self.snapshot_archive(), **self.contract,
                                         observation_profile=observation_profile)
        if validate:
            oracle.validate_snapshot(decoded, require_pcid=require_pcid, workers=bool(arguments),
                                     observation_profile=observation_profile)
        return record, decoded

    def close(self):
        caller_error = sys.exc_info()[1]
        failure = None

        def retain(error, stage):
            nonlocal failure
            if failure is None:
                failure = error
            self.evidence.setdefault('cleanup_failures', []).append(dict(stage=stage,
                error=type(error).__name__ + ': ' + str(error)))

        try:
            super().close()
        except BaseException as exc:
            retain(exc, 'parent-close')
        process = getattr(self, 'process', None)
        try:
            # A parent QMP/file error must not bypass terminating only our Popen.
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            check(process is None or process.poll() is not None, 'owned QEMU cleanup still alive')
        except BaseException as exc:
            retain(exc, 'owned-stop')
        if failure is not None:
            for name in ('qmp', 'uart', 'stderr'):
                handle = getattr(self, name, None)
                if handle is not None:
                    try:
                        handle.close()
                    except BaseException as exc:
                        retain(exc, name + '-close')
            reader = getattr(self, 'reader', None)
            if reader is not None:
                try:
                    reader.join(timeout=2)
                    check(not reader.is_alive(), 'owned UART reader did not stop')
                except BaseException as exc:
                    retain(exc, 'reader-join')
        if caller_error is not None:
            self.evidence['primary_failure'] = type(caller_error).__name__ + ': ' + str(caller_error)
        elif failure is not None:
            self.evidence['primary_failure'] = type(failure).__name__ + ': ' + str(failure)
        if process is not None:
            self.evidence.update(process_alive=process.poll() is None,
                cleanup_completed=process.poll() is not None, qemu_returncode=process.returncode)
        try:
            write(self.state / 'physical-manifest.json', self.chunks)
        except BaseException as exc:
            retain(exc, 'physical-manifest')
        registry = getattr(self, '_capture_registry', None)
        if registry is not None:
            index_sha = None
            try:
                index_sha = self._flush_capture_after_exit()
                registry.verify_all()
                self.evidence['bulk_capture'] = dict(schema=registry.profile, index_file=bulk.INDEX,
                    index_sha256=index_sha, final_disk_verified=True, epochs=len(registry._epochs),
                    observer_events=copy.deepcopy(self._observer_events),
                    pause_budget_ns=self._pause_budget_ns, post_resume_failures_may_be_observer_disturbed=True)
            except BaseException as exc:
                retain(exc, 'final-capture')
                index_error = None
                if index_sha is None:
                    try:
                        if self.historical_capture is True:
                            check(process is not None and process.poll() is not None,
                                  'v3 failure index requires observed owned exit')
                        index_sha = registry.save()
                    except BaseException as save_error:
                        index_error = type(save_error).__name__ + ': ' + str(save_error)
                self.evidence['bulk_capture'] = dict(schema=registry.profile, index_file=bulk.INDEX,
                    index_sha256=index_sha, final_disk_verified=False,
                    error=type(exc).__name__ + ': ' + str(exc), observer_events=copy.deepcopy(self._observer_events))
                if index_error is not None:
                    self.evidence['bulk_capture']['index_error'] = index_error
        if caller_error is None and failure is not None:
            self.evidence['primary_failure'] = type(failure).__name__ + ': ' + str(failure)
        try:
            write(self.state / 'guest.json', self.evidence)
        except BaseException as exc:
            retain(exc, 'guest-record')
        if caller_error is None and failure is not None:
            raise failure

    def _flush_capture_after_exit(self):
        process = getattr(self, 'process', None)
        result = None if process is None else process.poll()
        check(process is not None and result is not None, 'owned QEMU must exit before pending files/final disk authentication')
        reader = getattr(self, 'reader', None)
        check(reader is None or not reader.is_alive(), 'owned UART reader must stop before final capture authentication')
        if 'owned_process_exit' not in self.evidence:
            self.evidence['owned_process_exit'] = dict(pid=process.pid, returncode=result,
                process_alive=False, observed_ns=time.monotonic_ns())
        evidence = self.evidence['owned_process_exit']
        check(evidence['pid'] == process.pid and evidence['returncode'] == result and evidence['process_alive'] is False,
              'owned process exit identity changed')
        write(self.state / 'guest.json', self.evidence)
        self._capture_registry.flush_pending(phase='exit', evidence=evidence)
        return self._capture_registry.save()


class CapturedImage:
    """Explicit historical readers only; owns no Guest/controller or proxy hook."""
    historical_image = True

    def __init__(self, registry, epoch, boot_ref, *, esp, symbols, contract, label):
        check(registry.profile == bulk.SCHEMA, 'CapturedImage requires the v3 profile')
        record = registry.epoch(epoch)
        check(record.get('observation') is not None and boot_ref['epoch'] == epoch,
              'CapturedImage requires a complete same-epoch observation')
        self.__registry = registry
        self.__epoch = epoch
        self.__serial_offset = record['observation']['serial_offset']
        self.__boot_ref = copy.deepcopy(boot_ref)
        self.esp, self.state = Path(esp), registry.root
        self.symbols, self.contract = copy.deepcopy(symbols), copy.deepcopy(contract)
        self.static_pools = self.contract['static_pools']
        self.raw = bytes.fromhex(record['observation']['serial_hex'])
        self.boot = bulk.boot_info(registry.read(boot_ref, epoch))
        self.tables, self.evidence, self.roots = {}, {}, []
        self.chunks = registry.chunks
        self.label = label
        self.__initialized = False

    @property
    def epoch(self): return self.__epoch

    @property
    def serial_offset(self): return self.__serial_offset

    @property
    def boot_info_ref(self): return copy.deepcopy(self.__boot_ref)

    def initialize(self):
        self.__registry.history_authority(self.epoch)
        if not self.__initialized:
            self.refresh_processes()
            self.validate_private_pools()
            check(all(struct.unpack_from('<Q', self.processes, i * life.PROCESS_BYTES)[0] == 1 for i in range(5)),
                  'missing historical essential service')
            self.bias = struct.unpack_from('<Q', self.processes, 3 * life.PROCESS_BYTES + 224)[0]
            self.syms = read_elf_symbols(self.esp.parent / 'services/compositor/program.elf')
            self.__initialized = True
        return self

    def physical(self, address, length, role):
        return self.__registry.historical_slice(self.epoch, address, length, role)[0]

    def kernel(self, address, length, role):
        check(type(address) is int and bulk.KERNEL <= address <= bulk.KERNEL + bulk.WINDOW - length,
              'historical kernel read escaped actual loader window')
        return self.physical(self.boot[15] + address - bulk.KERNEL, length, role)

    def archive(self):
        self.__registry.history_authority(self.epoch)
        return oracle.Archive(self.state, self.chunks, registry=self.__registry).begin_snapshot(self.epoch)

    snapshot_archive = archive

    def register_ref(self, cpu):
        return self.__registry.sealed_register_ref(self.epoch, cpu)

    def require_actual_ap_registers(self):
        authority = self.__registry.history_authority(self.epoch)
        check(authority['phase'] == 'resume', 'PCID worker register precheck requires confirmed resume')
        registers = []
        for cpu in range(4):
            ref = self.register_ref(cpu)
            check(ref.get('epoch') == self.epoch and ref.get('cpu_index') == cpu,
                  'PCID worker register precheck CPU/epoch differs')
            oracle.Archive.safe_name(ref)
            text = self.__registry.text(ref, self.epoch)
            registers.append(oracle.parse_observation_registers(text, observation_profile=CURRENT_OWNER))
        # Parse every CPU first: an earlier user AP must not hide a later bad
        # source. This can only reject; the complete original oracle follows.
        check(any(reg['CS'] == 0x33 for reg in registers[1:]),
              'PCID worker checkpoint has no actual AP CPL3 register source')

    def flush(self):
        authority = self.__registry.history_authority(self.epoch)
        self.__registry.flush_pending(**authority)
        self.__registry.save()

    # A finite, reviewable set of data algorithms. None inherits or forwards
    # controller methods, and every physical read reaches historical_slice.
    ksym = settings.Guest.ksym
    kval = settings.Guest.kval
    trusted_kernel_pool = settings.Guest.trusted_kernel_pool
    uses_static_pool = settings.Guest.uses_static_pool
    private_pages = settings.Guest.private_pages
    pte = settings.Guest.pte
    user = settings.Guest.user
    refresh_processes = life.ProcessGuest.refresh_processes
    verify_elf = life.ProcessGuest.verify_elf
    virtual_kernel = life.ProcessGuest.virtual_kernel
    canary = life.ProcessGuest.canary
    fixed_probe = life.ProcessGuest.fixed_probe
    validate_private_pools = PcidGuest.validate_private_pools
    verify_process = PcidGuest.verify_process
    catalog = PcidGuest.catalog
    snapshot = PcidGuest._assemble_snapshot


def stable_snapshot(guest, arguments, *, require_pcid, negative=False, timeout=90, observation_profile=LOCK_FREE):
    oracle.require_observation_profile(observation_profile, negative=negative)
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        guest.resume()
        time.sleep(.06)
        try:
            record, decoded = guest.snapshot(arguments, validate=not negative, require_pcid=require_pcid,
                                             observation_profile=observation_profile)
            oracle.bound_observation_profile(record, observation_profile)
            oracle.bound_observation_profile(decoded, observation_profile)
            if negative:
                oracle.wrong_tag(decoded)
            return record, decoded
        except ValueError as exc:
            last = exc
            # A strict capability failure is final, never a long fallback retry.
            if 'fallback is not a PCID pass' in str(exc):
                raise
            if 'requires real per-CPU PCID' in str(exc):
                raise
    raise ValueError('no complete actual PCID checkpoint: ' + str(last))


def source_tools(esp):
    qemu = settings.builder.find_tool('qemu-system-x86_64', 'QEMU')
    firmware = settings.builder.find_firmware(qemu)
    paths = [Path(qemu), *firmware, Path(sys.executable)]
    paths += [ROOT / name for name in build.inputs() if name.startswith('tests/') and name.endswith('.py')]
    return {str(p.resolve()): sha(p) for p in paths}


def final_inputs(result, esp, identity, tools, disk):
    """Late changes invalidate an earlier seal and force the actual CLI verdict."""
    try:
        result['tools_after'] = source_tools(esp)
        result['inputs_unchanged'] = result['tools_after'] == tools and build.identity(esp) == identity
        if not result['inputs_unchanged']:
            result.update(passed=False, final_error='source/artifact/runner/tool changed at final verification')
        if result.get('final_disk_sha256') and sha(disk) != result['final_disk_sha256']:
            result.update(passed=False, final_error='disk changed at final verification')
    except BaseException as exc:
        result.update(passed=False, inputs_unchanged=False, final_error=type(exc).__name__ + ': ' + str(exc))
    if result.get('passed') is not True and 'seal' in result:
        result['invalidated_seal'] = result.pop('seal')


def execute(esp, output, *, accel='tcg', cpu='max,+smep,+smap,+umip', require_pcid=True, negative=None, kernel_irqchip=None,
            observation_profile=LOCK_FREE):
    oracle.require_observation_profile(observation_profile, negative=negative)
    esp, output = Path(esp).resolve(), Path(output).resolve()
    check(kernel_irqchip is None or kernel_irqchip == 'off' and accel == 'whpx',
          'kernel-irqchip=off is an explicit WHPX-only configuration')
    identity = build.identity(esp)
    check(identity['case'] == negative, 'explicit negative differs from actual built source')
    check(not output.exists(), 'fresh actual run directory required')
    output.mkdir(parents=True)
    tools = source_tools(esp)
    disk = output / 'data.img'
    create(disk, 64)
    result = dict(schema=1, execute=True, synthetic=False, require_pcid=require_pcid, negative=negative,
                  esp=str(esp), source_identity=identity, tools_before=tools, boots=[],
                  guest_memory_or_register_writes=False, passed=False,
                  accel=accel, cpu=cpu, kernel_irqchip=kernel_irqchip, observation_profile=observation_profile)
    try:
        for number in (1, 2):
            state = output / ('boot-' + str(number))
            boot = dict(disk_before_sha256=sha(disk), phases={}, observation_profile=observation_profile)
            result['boots'].append(boot)
            guest = None
            try:
                guest = PcidGuest(esp, disk, state, accel=accel, cpu=cpu, kernel_irqchip=kernel_irqchip)
                inventory = guest.qmp.request('query-cpus-fast')
                write(state / 'cpu-inventory.json', inventory)
                check(len(inventory) == 4 and {c['cpu-index'] for c in inventory} == set(range(4))
                      and len({c['thread-id'] for c in inventory}) == 4, 'actual QMP inventory is not four distinct CPUs')
                boot['cpu_inventory_sha256'] = sha(state / 'cpu-inventory.json')
                prior.close_gui(guest)
                for cfg, argument in oracle.ARGS.items():
                    guest.shell('run ' + life.NAMES[cfg] + ' ' + str(argument))
                if negative:
                    image = guest.capture_image('negative-target')
                    guest.resume()
                    current = image.catalog()
                    targets = [cfg for cfg in oracle.ARGS if current['slots'][cfg] == 11]
                    check(len(targets) == 1, 'exact wrong-tag slot11 not owned by one current launched workload')
                    cfg = targets[0]
                    record, _ = stable_snapshot(guest, {cfg: oracle.ARGS[cfg]}, require_pcid=True, negative=True,
                                                 observation_profile=observation_profile)
                    boot['phases']['negative'] = record
                else:
                    record, cold = stable_snapshot(guest, oracle.ARGS, require_pcid=require_pcid,
                                                    observation_profile=observation_profile)
                    boot['phases']['cold'] = record
                    guest.resume()
                    time.sleep(.3)
                    record, warm = stable_snapshot(guest, oracle.ARGS, require_pcid=require_pcid,
                                                    observation_profile=observation_profile)
                    boot['phases']['warm'] = record
                    first = next(v for v in warm['workers'] if v['cfg'] == 7)
                    guest.shell('kill ' + str(first['token']))
                    record, retired = stable_snapshot(guest, {}, require_pcid=require_pcid,
                                                       observation_profile=observation_profile)
                    oracle.ownership.retirement(warm, retired, first['slot'])
                    boot['phases']['retired'] = record
                    guest.shell('run echo ' + str(oracle.REUSE_ARGUMENT))
                    arguments = {**oracle.ARGS, 7: oracle.REUSE_ARGUMENT}
                    record, _ = stable_snapshot(guest, arguments, require_pcid=require_pcid,
                                                 observation_profile=observation_profile)
                    boot['phases']['reused'] = record
                    image = guest._last_snapshot_image
                    old = image.physical(first['physical'], 8, 'held old fixed-VA incarnation word')
                    boot['old_physical_word'] = struct.unpack('<Q', old)[0]
                    boot['old_physical_ref'] = copy.deepcopy(guest.chunks[-1])
                    boot['old_physical_epoch'] = image.epoch
            finally:
                if guest is not None:
                    guest.close()
                    boot['guest'] = copy.deepcopy(guest.evidence)
                    boot['physical_manifest_sha256'] = sha(state / 'physical-manifest.json')
                    boot['serial_sha256'] = sha(state / 'serial.log')
                else:
                    # Constructors save their owned-process cleanup/diagnostic
                    # record even when no usable object is returned.
                    if (state / 'guest.json').is_file():
                        boot['guest'] = json.loads((state / 'guest.json').read_text())
                boot['disk_after_sha256'] = sha(disk)
                write(output / 'result.json', result)
        check(build.identity(esp) == identity, 'source/artifact identity changed during guests')
        after = source_tools(esp)
        result.update(tools_after=after, inputs_unchanged=tools == after,
                      final_disk_sha256=sha(disk))
        write(output / 'result.json', result)
        result['seal'] = replay(output / 'result.json', observation_profile=observation_profile)
        result['passed'] = True
    except BaseException as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        final_inputs(result, esp, identity, tools, disk)
        write(output / 'result.json', result)
    return result


def replay(path, *, observation_profile=LOCK_FREE):
    oracle.require_observation_profile(observation_profile)
    path = Path(path).resolve()
    result = json.loads(path.read_text(encoding='utf-8'))
    oracle.bound_observation_profile(result, observation_profile)
    oracle.require_observation_profile(observation_profile, negative=result.get('negative'))
    if 'seal' in result:
        oracle.bound_observation_profile(result['seal'], observation_profile)
    identity = build.identity(Path(result['esp']))
    check(result['tools_before'] == result['tools_after']
          and all(sha(p) == h for p, h in result['tools_before'].items()), 'runner/QEMU/firmware inputs changed')
    contract = elf_contract(Path(result['esp']))
    decoded = []
    for index, boot in enumerate(result['boots'], 1):
        oracle.bound_observation_profile(boot, observation_profile)
        root = path.parent / ('boot-' + str(index))
        check(sha(root / 'physical-manifest.json') == boot['physical_manifest_sha256']
              and sha(root / 'serial.log') == boot['serial_sha256'], 'raw/serial archive changed')
        guest = json.loads((root / 'guest.json').read_text(encoding='utf-8'))
        check(guest == boot['guest'], 'saved guest cleanup record differs')
        command = guest['command']
        # Reconstruct the only permitted machine option; a rehashed command
        # cannot silently switch the accelerator, CPU or interrupt backend.
        verify_launch_command(command, accel=result['accel'], cpu=result['cpu'],
                              kernel_irqchip=result['kernel_irqchip'])
        check(sha(root / 'cpu-inventory.json') == boot['cpu_inventory_sha256'], 'actual CPU inventory changed')
        inventory = json.loads((root / 'cpu-inventory.json').read_text(encoding='utf-8'))
        check(len(inventory) == 4 and {c['cpu-index'] for c in inventory} == set(range(4))
              and len({c['thread-id'] for c in inventory}) == 4, 'actual QMP inventory omitted/duplicated a CPU')
        capture = guest.get('bulk_capture', {})
        check(capture.get('schema') == bulk.SCHEMA and capture.get('index_file') == bulk.INDEX
              and capture.get('final_disk_verified') is True
              and sha(root / bulk.INDEX) == capture.get('index_sha256'), 'actual bulk capture provenance missing/changed')
        archive = oracle.Archive(root, json.loads((root / 'physical-manifest.json').read_text()), metadata=capture_metadata(result['esp']))
        phases = {n: oracle.decode_snapshot(v, archive, **contract, observation_profile=observation_profile)
                  for n, v in boot['phases'].items()}
        if not result['negative']:
            old = boot['old_physical_ref']
            archive.begin_snapshot(boot['old_physical_epoch'])
            warm = next(v for v in phases['warm']['workers'] if v['cfg'] == 7)
            check(old['physical'] == warm['physical'] and old['length'] == 8
                  and struct.unpack('<Q', archive.read(old))[0] == boot['old_physical_word'], 'old physical word not raw-bound')
        archive.verify_all()
        decoded.append(phases)
    disk = path.parent / 'data.img'
    check(sha(disk) == result['final_disk_sha256'] == result['boots'][-1]['disk_after_sha256'], 'final actual disk changed')
    return oracle.seal(result, source_identity=identity, decoded_boots=decoded)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reuse-esp', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--require-pcid', action='store_true')
    p.add_argument('--accel', choices=['tcg', 'whpx', 'kvm'], default='tcg')
    p.add_argument('--cpu', default='max,+smep,+smap,+umip')
    p.add_argument('--kernel-irqchip', choices=['off'],
                   help='explicit WHPX-only userspace interrupt backend; all hardware gates remain required')
    p.add_argument('--negative', choices=['wrong-tag'])
    p.add_argument('--observation-profile', choices=[LOCK_FREE, CURRENT_OWNER], default=LOCK_FREE,
                   help='explicit PCID checkpoint contract; default keeps the original unlocked gate')
    p.add_argument('--replay', type=Path)
    a = p.parse_args(argv)
    try:
        oracle.require_observation_profile(a.observation_profile, negative=a.negative)
        if a.replay:
            check(not a.execute, 'replay cannot execute guests')
            result = replay(a.replay, observation_profile=a.observation_profile)
            print(json.dumps(result))
            return 0 if result.get('passed') is True else 1
        if not a.execute:
            check(a.reuse_esp is not None, '--reuse-esp required')
            print(json.dumps(dict(mode='identity-only', guest_executed=False, observation_profile=a.observation_profile,
                                  source_identity=build.identity(a.reuse_esp))))
            return 0
        check(a.reuse_esp is not None, '--reuse-esp required')
        output = a.output or ROOT / 'build/test/p2-pcid/qemu' / ('run-' + uuid.uuid4().hex[:12])
        result = execute(a.reuse_esp, output, accel=a.accel, cpu=a.cpu,
                         require_pcid=a.require_pcid, negative=a.negative,
                         kernel_irqchip=a.kernel_irqchip, observation_profile=a.observation_profile)
        print(json.dumps(result))
        return 0 if result.get('passed') is True else 1
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps(dict(passed=False, error=type(exc).__name__ + ': ' + str(exc))))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
