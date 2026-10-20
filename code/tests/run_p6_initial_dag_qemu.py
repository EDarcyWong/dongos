#!/usr/bin/env python3
"""Initial init-owned GUI DAG / simultaneous AP CPL3 structural gate.

One completed normal runtime7 image, one four-CPU TCG boot. QMP stop/cont and
narrow physical reads only: no input commands, guest writes, breakpoints, or
post-start relaunches. This is NOT the separate unpaused Linux/KVM timing gate.
Missing the initial window is failure, never permission to substitute a restart.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests import boot_trace_capture
from tests import run_p6_kvm_qemu as timing
from tests import run_process_lifecycle_qemu as life
from tests import user_smp_oracle as oracle
from tools.elf_symbols import read_elf_symbols
from tools import service_bundle
from lang.dongc import compile_file  # Load observer-layout dependencies before fingerprints.
from lang.dongc import declarations, l1_declarations  # compile_file's lazy parser modules.

clock, storage = timing.clock, life.storage
ROOT, check, write = timing.ROOT, oracle.check, timing.write
GUI = tuple(range(14, 18))
ARENA = 0xffffd40000000000
SNAPSHOTS_OFFSET = 24 + 32 * 128
GUI_OFFSET = SNAPSHOTS_OFFSET + 14 * 64
CATALOG_BYTES = 10776
NONE = (1 << 64) - 1
THREADS_OFFSET = 32 + 16 * (5 + 32 + 32) * 8
MARKERS = (b'DONGOS_SHELL_READY\r\n', b'DONGOS_P7_CLIENTS_READY\r\n')
DENSE_DELAYS = (.0002, .0005, .0013, .0021)


def sampling_delay(initialized, have_gui, dense_index):
    """Deterministic host delays, not a claim about guest/TCG elapsed time."""
    check(isinstance(dense_index, int) and dense_index >= 0, 'invalid sampling index')
    if have_gui:
        return DENSE_DELAYS[dense_index % len(DENSE_DELAYS)]
    return .005 if initialized else .02


def qmp_socket_path(state):
    path = Path(state).resolve() / 'qmp.sock'
    # Linux sockaddr_un.sun_path is 108 bytes including the terminating NUL.
    check(b'\0' not in os.fsencode(path) and len(os.fsencode(path)) <= 107,
          'owned QMP Unix socket path exceeds 107 bytes')
    return path


class UnixQMP(clock.acpi.QMP):
    """Same QMP handshake/request/close protocol, without TCP event/reply delay."""
    def __init__(self, path, process):
        path = Path(path)
        check(path == qmp_socket_path(path.parent), 'QMP socket must be the owned state path')
        self.file = None
        deadline = time.monotonic() + 15
        while True:
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                connection.settimeout(1)
                connection.connect(str(path))
                self.socket = connection
                break
            except OSError:
                connection.close()
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise
                time.sleep(.1)
        try:
            self.socket.settimeout(10)
            self.file = self.socket.makefile('rwb')
            greeting = json.loads(self.file.readline())
            check(isinstance(greeting, dict) and 'QMP' in greeting, 'QMP greeting missing')
            self.request('qmp_capabilities')
        except BaseException:
            try:
                self.close()
            except Exception:
                pass
            raise


def words(raw, count):
    return oracle.words(raw, count)


def snapshot_record(raw):
    keys = ('version', 'configuration', 'process', 'generation',
            'state', 'status', 'sequence', 'argument')
    return dict(zip(keys, words(raw, 8)))


def gui_window(raw):
    check(len(raw) == 256, 'incomplete GUI prefilter')
    records = [snapshot_record(raw[i * 64:(i + 1) * 64]) for i in range(4)]
    for cfg, record in zip(GUI, records):
        check(record['version'] == 1 and record['configuration'] == cfg,
              'GUI prefilter ABI mismatch')
    live = [r for r in records if r['generation'] == 1 and r['process']
            and r['state'] in (1, 2) and r['status'] == 0]
    return len(live) >= 2 and any(r['state'] == 1 for r in live)


def decode_catalog(raw):
    """Current ABI, including AUTOSTART|ORDINARY (9), not the old flags8 ABI."""
    check(len(raw) == CATALOG_BYTES, 'incomplete Catalog')
    ready, count, sequence = struct.unpack_from('<3Q', raw)
    check((ready, count) == (1, 18) and sequence <= 64, 'not initial Catalog history')
    configs = []
    for i in range(32):
        offset = 24 + i * 128
        fields = struct.unpack_from('<8Q', raw, offset)
        name, reserved = raw[offset + 64:offset + 96], raw[offset + 96:offset + 128]
        version, identifier, deps, retries, timeout, flags, image, length = fields
        check(version == 1 and not any(reserved), 'Catalog config version/reserved')
        if i < 18:
            expected = 7 if i in (0, 1, 3, 6) else 5 if i < 7 else 4 if i == 13 else 9 if i in GUI else 8
            check(identifier == i and deps == life.DEPS[i] and flags == expected
                  and image == i + 1 and retries == (3 if i in (0, 1, 3, 6) else 0)
                  and timeout > 0 and length == len(life.NAMES[i])
                  and name == life.NAMES[i].encode().ljust(32, b'\0'),
                  'current admitted configuration differs')
        else:
            check(fields == (1, 0, 0, 0, 0, 0, 0, 0) and not any(name),
                  'unused configuration differs')
        configs.append(dict(id=identifier, dependencies=deps, flags=flags))
    states = [snapshot_record(raw[SNAPSHOTS_OFFSET + i * 64:SNAPSHOTS_OFFSET + (i + 1) * 64])
              for i in range(32)]
    offset = SNAPSHOTS_OFFSET + 32 * 64
    slots = words(raw[offset:offset + 256], 32)
    incarnations = words(raw[offset + 256:offset + 384], 16)
    configurations = words(raw[offset + 384:offset + 512], 16)
    for cfg, s in enumerate(states):
        check(s['version'] == 1 and s['configuration'] == cfg and s['state'] <= 5
              and s['sequence'] <= sequence, 'invalid Catalog snapshot')
        if s['process']:
            slot = slots[cfg]
            check(cfg < 18 and slot < 16 and configurations[slot] == cfg
                  and (slot == 13 if cfg == 13 else slot != 13)
                  and 0 < incarnations[slot] <= 0x0fffffff
                  and s['process'] == (incarnations[slot] << 8) | (slot + 1)
                  and s['generation'] > 0 and s['state'] in (1, 2),
                  'Catalog token/slot/incarnation mismatch')
        else:
            check(slots[cfg] == NONE and s['state'] in (0, 3, 4, 5),
                  'unowned live Catalog slot')
    for slot, cfg in enumerate(configurations):
        check(cfg == NONE or cfg < 18 and slots[cfg] == slot and states[cfg]['process'],
              'Catalog inverse slot map mismatch')
    events = []
    offset += 512
    for i in range(64):
        v, seq, cfg, generation, token, state, status, flags = struct.unpack_from('<8Q', raw, offset + i * 64)
        check(v == 1 and flags == 0, 'event ABI mismatch')
        if seq:
            check(1 <= seq <= sequence and (seq - 1) % 64 == i and cfg < 18
                  and generation == 1 and state == 2 and status == 0
                  and token == states[cfg]['process'], 'not first-generation READY-only history')
            events.append(dict(sequence=seq, configuration=cfg, generation=generation,
                               process=token, state=state, status=status))
    events.sort(key=lambda e: e['sequence'])
    check([e['sequence'] for e in events] == list(range(1, sequence + 1)),
          'Catalog event gaps')
    return dict(sequence=sequence, configs=configs, snapshots=states, slots=slots,
                incarnations=incarnations, configurations=configurations, events=events)


def init_receipts(initial, manager, started, catalog, owners):
    check(len(initial) == 32 and len(manager) == 5656 and len(started) == 8,
          'init receipt ABI mismatch')
    check(words(manager[:24], 3)[:2] == [1, 18], 'init manager not initialized')
    for cfg in GUI:
        s = initial[cfg]
        check(s['version'] == 1 and s['configuration'] == cfg and s['process'] == 0
              and s['generation'] == 0 and s['state'] == 0 and s['status'] == 0
              and s['argument'] == 0, 'GUI was adopted, restarted, or not initially stopped')
        config = words(manager[24 + cfg * 128:24 + cfg * 128 + 64], 8)
        check(config[0:3] == [1, cfg, life.DEPS[cfg]] and config[5:7] == [9, cfg + 1],
              'init manager configuration differs')
    for cfg in owners:
        node = words(manager[4120 + cfg * 48:4120 + (cfg + 1) * 48], 6)
        s = catalog['snapshots'][cfg]
        check(node[0:2] == [1, s['process']] and node[2] in (1, 2)
              and node[3] == 1 and node[4] > 0 and node[5] == 0,
              'init successful launch receipt absent')
    # STARTED is just the latest raw SPAWN reply, not an invented receipt array.
    cfg = started[1]
    check(started[0] == 1 and cfg in GUI and started[2] == catalog['snapshots'][cfg]['process']
          and started[3:6] == [1, 1, 0] and started[7] == 0,
          'init latest raw SPAWN receipt differs')
    check(initial[5]['version'] == 1 and initial[5]['configuration'] == 5
          and initial[5]['process'] == catalog['snapshots'][5]['process']
          and initial[5]['generation'] == 1 and initial[5]['state'] == 2
          and initial[5]['status'] == 0,
          'original init bootstrap adoption missing')


def trace_catalog(records, catalog):
    ready = [(e[3], e[4] & 0xffffffff) for e in records if e[2] == 7]
    check(ready == [(e['configuration'], e['generation']) for e in catalog['events']],
          'Catalog READY history differs from same-stop boot trace')
    started = {e[3] for e in records if e[2] == 6 and e[4] & 0xffffffff == 1}
    ready_ids = {cfg for cfg, generation in ready}
    check(not any(e[2] == 8 for e in records), 'boot trace records a stopped generation')
    for cfg, s in enumerate(catalog['snapshots']):
        if s['process']:
            check(cfg in started and ((s['state'] == 2) == (cfg in ready_ids)),
                  'Catalog STARTING/READY differs from actual trace')


def initial_trace(raw):
    check(len(raw) == 4096 and sum(words(raw, 512)) & NONE == 0,
          'initial trace corrupt or absent')
    h = words(raw[:256], 32)
    check(h[:5] == [0x3145434152544244, 1, 4096, 48, 80]
          and h[6:8] == [5, 0] and h[8] > 0 and h[11] == 15
          and 0 < h[5] <= 80 and h[23] == 18 and h[26] == 0x3c000
          and h[30:] == [0, 0], 'initial trace already sealed or wrong boot/profile')
    records = [words(raw[256 + i * 48:304 + i * 48], 6) for i in range(h[5])]
    check(not any(raw[256 + h[5] * 48:]), 'initial trace unpublished tail is nonzero')
    last, started, ready, marks = 0, set(), set(), {}
    for i, e in enumerate(records):
        check(e[0] == i + 1 and e[1] > last and e[4] >> 32 == h[10],
              'initial trace sequence/time/writer mismatch')
        last = e[1]
        if e[2] == 6:
            check(e[3] not in started and e[4] & 0xffffffff == 1, 'initial START repeated')
            started.add(e[3])
        elif e[2] == 7:
            check(e[3] in started and e[3] not in ready, 'initial READY lacks unique START')
            ready.add(e[3])
        elif e[2] == 8:
            raise ValueError('initial trace contains a stopped generation')
        elif e[2] in (9, 10, 12, 13):
            check(e[2] not in marks, 'initial trace mark duplicated')
            marks[e[2]] = e[0]
    check(h[18] == last and h[19] == h[5]
          and h[24] == sum(1 << cfg for cfg in ready)
          and h[25] == sum(1 << cfg for cfg in started)
          and h[20:23] == [marks.get(k, 0) for k in (9, 10, 12)]
          and h[29] == marks.get(13, 0) and h[27] == 0 and 12 not in marks,
          'initial trace header summary differs from records')
    return h, records


def validate_initial(record):
    c, r, d = record['catalog'], record['report'], record['domain']
    check(r[:5] == [1, 0, 1, 4, 15] and len(r) == 10, 'four-CPU user report missing')
    check(len(d) == 15 and d[0:2] == [1, 0] and d[4] == 15
          and d[5] == d[8] > 0 and d[6:8] == [0, 0] and d[9] == r[8],
          'nonzero completed all-CPU barrier missing')
    check(len(record['cpus']) == len(record['headers']) == len(record['metrics'])
          == len(record['contexts']) == len(record['registers']) == 4,
          'incomplete same-stop CPU evidence')
    check(len(record['processes']) == 16 and len(record['threads']) == 64,
          'incomplete ownership evidence')
    check(len({x[2] for x in record['contexts']}) == 4, 'duplicate APIC identity')
    check(all(s['generation'] == 1 and s['state'] == 2 and s['status'] == 0
              for s in c['snapshots'][:7]), 'essential initial services not READY')
    check(all(s['generation'] <= 1 for s in c['snapshots']), 'post-start restart is not initial evidence')
    life.check_boot_dag(c)
    owners = []
    for cpu in range(4):
        owned, header, metric = record['cpus'][cpu], record['headers'][cpu], record['metrics'][cpu]
        check(owned[7] == owned[8] == d[8], 'CPU did not ACK the completed epoch')
        oracle.header(cpu, header, metric, r, record['contexts'][cpu],
                      dict(address=record['header_addresses'][cpu],
                           syscall_entry=record['syscall_entry'], fmask=0x77700))
        user = oracle.cpu_ownership(cpu, owned, record['processes'],
                                    record['threads'], header, record['registers'][cpu])
        if cpu and user:
            slot = owned[3]
            cfg = c['configurations'][slot]
            process, thread = record['processes'][slot], record['threads'][slot]
            check(cfg in GUI and c['slots'][cfg] == slot
                  and c['snapshots'][cfg]['process'] == owned[1]
                  and c['snapshots'][cfg]['generation'] == 1
                  and c['incarnations'][slot] == owned[2]
                  and c['snapshots'][cfg]['state'] in (1, 2)
                  and c['snapshots'][cfg]['status'] == 0,
                  'AP CPL3 owner is not a first-generation GUI')
            check(thread[2] == 15 and thread[6] == process[0] >> 8
                  and thread[7] == process[3] and process[5:] == [0, 0],
                  'AP GUI queue/frame ownership differs')
            owners.append(cfg)
    check(len(owners) >= 2 and len(set(owners)) == len(owners)
          and any(c['snapshots'][cfg]['state'] == 1 for cfg in owners),
          'no same-stop pair of AP GUI owners including STARTING')
    init_receipts(record['init_initial'], bytes.fromhex(record['init_manager_hex']),
                  record['init_started'], c, owners)
    trace = bytes.fromhex(record['trace_hex'])
    th, records = initial_trace(trace)
    trace_catalog(records, c)
    for cfg in owners:
        check(any(e[2:5] == [6, cfg, (th[10] << 32) | 1] for e in records),
              'initial trace lacks the GUI first START')
        if c['snapshots'][cfg]['state'] == 2:
            check(any(e[2:5] == [7, cfg, (th[10] << 32) | 1] for e in records),
                  'Catalog READY lacks same-stop trace READY')
    check(record['stopped_before'] is True and record['stopped_after'] is True
          and record['stop_id'] > 0, 'not one stopped observation')
    return dict(ap_gui_configurations=owners, completed_barrier_epoch=d[8],
                initial_init_owned=True, simultaneous_ap_cpl3=True)


def validate_final(initial, final, decoded):
    h = decoded['header']
    early = bytes.fromhex(initial['trace_hex'])
    old, _ = initial_trace(early)
    check(h['boot_id'] == old[8] and h['online_mask'] == 15 and h['state'] == 6
          and h['ready_mask'] & 0x3c07f == 0x3c07f
          and h['required_client_mask'] == h['client_mask'] == 0x3c000,
          'same initial boot did not finish all essential and GUI readiness')
    sealed = bytes.fromhex(final['trace_hex'])
    check(early[64:144] == sealed[64:144], 'final boot clock/CPU identity changed')
    check(early[256:256 + old[5] * 48] == sealed[256:256 + old[5] * 48],
          'final trace does not extend the captured initial boot')
    c = final['catalog']
    life.check_boot_dag(c)
    trace_catalog([words(sealed[256 + i * 48:304 + i * 48], 6)
                   for i in range(h['count'])], c)
    for cfg in (*range(7), *GUI):
        s, before = c['snapshots'][cfg], initial['catalog']['snapshots'][cfg]
        check(s['generation'] == 1 and s['state'] == 2 and s['status'] == 0
              and s['process'] != 0 and (not before['process'] or s['process'] == before['process']),
              'final readiness used a replacement generation/token')
    check(all(r['kind'] != 8 and (r['generation'] in (0, 1)) for r in decoded['records']),
          'boot trace contains a stop or restarted generation')
    return True


def bind_auxiliary(esp):
    """The five-artifact normal receipt binds the bundle, then its ELF members."""
    esp = Path(esp)
    raw = (esp / 'SERVICES.BIN').read_bytes()
    inventory = {e['name']: e for e in service_bundle.inspect(raw)['entries']}
    hashes = {}
    for name in ('init', 'compositor', 'terminal', 'files', 'editor', 'settings'):
        path = timing.ordinary(esp.parent / 'services' / name / 'program.elf')
        entry = inventory[name]
        check(entry['kind'] == 1 and timing.sha(path) == entry['sha256'],
              'inspected service ELF differs from bound bundle: ' + name)
        hashes[str(path)] = timing.sha(path)
    layout = timing.ordinary(esp.parent / 'dong_layout.json')
    hashes[str(layout)] = timing.sha(layout)
    return hashes


def bind_gui_image(image, cfg, catalog, processes):
    slot = catalog['slots'][cfg]
    check(image['pid'] == slot and image['image'] == life.NAMES[cfg]
          and image['root'] == processes[slot][2] and image['executable_bytes'] > 0,
          'executed GUI ELF root/identity differs from AP/domain root')


def check_completion(raw):
    timing.check_startup_failure(raw)
    check(all(bytes(raw).count(marker) == 1 for marker in MARKERS),
          'initial readiness markers missing or repeated')


def command_for(esp, state, disk, uart):
    qmp = qmp_socket_path(state)
    command = clock.builder.qemu_command(esp, state / 'guest', test=True, accel='tcg')
    check(command.count('-smp') == 1 and command[command.index('-smp') + 1] == '4'
          and command.count('-accel') == 1 and command[command.index('-accel') + 1] == 'tcg',
          'exact four-CPU TCG command required')
    at = command.index('isa-debug-exit,iobase=0xf4,iosize=0x04')
    check(command[at - 1] == '-device', 'unexpected debug-exit device')
    del command[at - 1:at + 1]
    command[command.index('-serial') + 1] = f'tcp:127.0.0.1:{uart},server=on,wait=off'
    command += ['-cpu', 'max,+smep,+smap,+umip,-tsc-deadline', '-S', '-qmp',
                'unix:' + str(qmp).replace(',', ',,') + ',server=on,wait=off', '-drive',
                'if=none,id=data,format=raw,cache=writeback,file=' + str(disk.resolve()).replace(',', ',,'),
                '-device', 'virtio-blk-pci,drive=data,disable-legacy=on', '-device', 'virtio-tablet-pci']
    return command


class InitialGuest(clock.ClockGuest):
    # Reuse narrow existing page/ELF validators, never their late constructors.
    ksym = life.settings.Guest.ksym
    kval = life.settings.Guest.kval
    refresh_processes = life.ProcessGuest.refresh_processes
    private_pages = life.settings.Guest.private_pages
    user = life.settings.Guest.user
    verify_process = life.ProcessGuest.verify_process
    trusted_kernel_pool = life.nvme.NvmeGuest.trusted_kernel_pool
    capture_failure = timing.KvmGuest.capture_failure

    def __init__(self, esp, state, timeout):
        super().__init__(esp, state, False, timeout, 7)
        self.tables, self.stopped, self.stop_id = {}, True, 0
        self.evidence.update(actual_kvm_boots=0, structural_only=True,
                             kvm_timing_proven=False, initial_window_observed=False)
        self.symbols = read_elf_symbols(esp.parent / 'kernel.elf')
        self.kernel_memory_layout = life.nvme.check_kernel_memory_layout(esp)
        self.deadline = None
        self.sampling = []
        self.candidate_rejections = []
        self.observations = []
        self.confirmed_stop = None
        self.catalog_initialized = False
        self.gui_sampling_started = False
        self.evidence['register_prefilter'] = dict(
            diagnostic_only=True, samples=0, ap_cpl3_counts=[0, 0, 0, 0],
            full_candidates=0, armed_at_stop_id=None)
        self.qmp_path = None

    def close(self):
        try:
            try:
                self.finish_observation(time.monotonic())
            finally:
                # Diagnostic accounting must never prevent owned-guest cleanup.
                timing.KvmGuest.close(self)
        finally:
            # Guest termination is mandatory; endpoint deletion is not. Never
            # unlink a preexisting/replaced socket or introduce an inode race.
            path = getattr(self, 'qmp_path', None)
            if path is not None:
                self.evidence['qmp_endpoint_cleanup'] = 'not_removed_by_observer'
                try:
                    self.evidence['qmp_endpoint_path_present'] = path.exists() or path.is_symlink()
                except OSError as exc:
                    self.evidence['qmp_endpoint_stat_error'] = str(exc)

    def alive(self):
        check(self.process.poll() is None, 'guest exited during initial DAG observation')
        timing.check_startup_failure(self.raw)
        check(time.monotonic() < self.deadline, 'initial DAG observation timed out')

    def pause(self):
        self.qmp.request('stop')
        check(self.qmp.request('query-status').get('running') is False, 'QMP did not stop all CPUs')
        confirmed = time.monotonic()
        self.stopped = True
        self.stop_id += 1
        self.tables = {}
        self._arena_limit = None
        self.confirmed_stop = dict(stop_id=self.stop_id, diagnostic_only=True,
                                   confirmed_stopped_monotonic=confirmed)
        self.observations.append(self.confirmed_stop)
        return confirmed

    def finish_observation(self, end):
        observation = getattr(self, 'confirmed_stop', None)
        if observation is not None and 'collection_end_monotonic' not in observation:
            observation.update(collection_end_monotonic=end,
                               confirmed_stopped_collection_seconds=
                               end - observation['confirmed_stopped_monotonic'])

    def resume(self):
        check(self.stopped, 'unpaired observation resume')
        requested = time.monotonic()
        self.finish_observation(requested)
        self.qmp.request('cont')
        replied = time.monotonic()
        self.stopped = False
        return requested, replied

    def sample_after(self, delay):
        # These are host observer intervals, never guest/KVM timing evidence.
        sample = dict(requested_sleep_seconds=delay, diagnostic_only=True,
                      guest_runtime_measured=False)
        self.sampling.append(sample)
        requested, replied = self.resume()
        sample.update(cont_request_monotonic=requested, cont_reply_monotonic=replied,
                      cont_wait_seconds=replied - requested)
        time.sleep(delay)
        sample['stop_request_monotonic'] = time.monotonic()
        confirmed = self.pause()
        sample.update(stopped_monotonic=confirmed, stop_id=self.stop_id,
                      cont_reply_to_stop_request_seconds=
                      sample['stop_request_monotonic'] - replied,
                      stop_confirmation_wait_seconds=
                      confirmed - sample['stop_request_monotonic'],
                      possibly_running_seconds_upper_bound=confirmed - requested)

    def kernel(self, va, n, role):
        check(self.stopped, 'linked-kernel read while guest is running')
        return super().kernel(va, n, role)

    def physical(self, pa, n, role):
        check(self.stopped, 'physical observation while guest is running')
        raw = super().physical(pa, n, role)
        self.chunks[-1]['stop_id'] = self.stop_id
        return raw

    def read(self, va, size, role):
        """Owned arena only; page tables must stay inside retained kernel128."""
        check(self.stopped and 0 < size <= 65536, 'unsafe arena observation size/state')
        if self._arena_limit is None:
            plan = words(self.kernel(self.ksym('boot.service_memory', 'PLAN'), 48, 'service arena Plan'), 6)
            used = self.kval('boot.service_memory', 'NEXT_PAGE')
            check(plan[4] > 0 and plan[4] % 4096 == 0 and plan[5] == 0x8000000
                  and plan[4] + plan[5] <= 1 << 32 and 0 < used <= plan[5] // 4096,
                  'invalid allocated service arena')
            self._arena_limit = ARENA + used * 4096
            self._arena_physical = plan[4]
            self._kernel_pool = self.trusted_kernel_pool()
        check(ARENA <= va < va + size <= self._arena_limit, 'read escaped allocated service arena')
        base, pages = self._kernel_pool
        out = bytearray()
        while size:
            table = self.evidence['trusted_kernel_page_table_pool']['root_physical']
            user, nx = True, False
            for shift in (39, 30, 21, 12):
                check(base <= table < base + pages * 4096 and table % 4096 == 0,
                      'arena walk escaped kernel table pool')
                if table not in self.tables:
                    self.tables[table] = self.physical(table, 4096, 'owned kernel table for arena')
                entry = struct.unpack_from('<Q', self.tables[table], ((va >> shift) & 511) * 8)[0]
                check(entry & 1, 'arena mapping not present')
                user = user and bool(entry & 4)
                nx = nx or bool(entry & (1 << 63))
                check(shift == 12 or not entry & 128, 'unexpected large arena mapping')
                table = entry & storage.MASK
            pa = table + (va & 4095)
            check(not user and nx and pa == self._arena_physical + va - ARENA,
                  'arena mapping ownership or supervisor/NX permission differs')
            n = min(size, 4096 - (va & 4095))
            out.extend(self.physical(pa, n, role))
            va, size = va + n, size - n
        return bytes(out)

    def readwords(self, va, count, role):
        return words(self.read(va, count * 8, role), count)

    def arena_physical_span(self, pa, size):
        check(self._arena_limit is not None and 0 < size
              and self._arena_physical <= pa < pa + size
              <= self._arena_physical + self._arena_limit - ARENA,
              'user table/leaf escaped allocated physical arena')

    def validate_private_pools(self):
        life.settings.Guest.validate_private_pools(self)
        for pid, root in enumerate(self.roots):
            if root and not (pid < 4 and self.pool_limits[pid] == 32):
                self.arena_physical_span(root, self.pool_limits[pid] * 4096)

    def pte(self, root, va):
        """Bound each private table before reading, and each USER leaf before use."""
        pages = self.private_pages(root)
        pid = self.roots.index(root)
        if not (pid < 4 and pages == 32):
            self.arena_physical_span(root, pages * 4096)
        current = root
        for shift in (39, 30, 21, 12):
            check(root <= current < root + pages * 4096 and current % 4096 == 0,
                  'user walk escaped its private table pool')
            if current not in self.tables:
                self.tables[current] = self.physical(current, 4096, 'bounded private user table')
            entry = struct.unpack_from('<Q', self.tables[current], ((va >> shift) & 511) * 8)[0]
            if not entry & 1:
                return entry
            check(entry & 4, 'missing USER ancestor/leaf')
            if shift == 12:
                self.arena_physical_span(entry & storage.MASK, 4096)
                return entry
            check(not entry & 128, 'unexpected large user page')
            current = entry & storage.MASK
        raise ValueError('incomplete user translation')

    def catalog_pointer(self):
        pointer = self.kval('user.services', 'CATALOG')
        check(pointer == 0 or pointer >= ARENA and pointer % 4096 == 0, 'invalid Catalog pointer')
        return pointer

    def catalog(self):
        return decode_catalog(self.read(self.catalog_pointer(), CATALOG_BYTES, 'initial lifecycle Catalog'))

    def trace(self):
        return self.kernel(self.ksym('boot.trace_runtime', 'STORAGE'), 4096, 'owned boot trace')

    def init_global(self, name, size, image):
        symbols = read_elf_symbols(self.esp.parent / 'services/init/program.elf')
        va = symbols[storage.symbol('init.main', name)]
        elf = (self.esp.parent / 'services/init/program.elf').read_bytes()
        start = struct.unpack_from('<Q', elf, 32)[0]
        stride, count = struct.unpack_from('<HH', elf, 54)
        spans = [struct.unpack_from('<II6Q', elf, start + i * stride) for i in range(count)]
        check(any(p[0] == 1 and p[1] & 2 and p[3] <= va <= p[3] + p[6] - size for p in spans),
              'init global escaped owned writable ELF segment')
        return self.user(5, image['bias'] + va, size, 'init original ' + name)

    def candidate_domain(self):
        """688 bytes of typed identity/epoch data, never sufficient for PASS."""
        check(self.stopped, 'candidate domain read requires a stopped guest')
        pointer = self.kval('sched.user_boot', 'INFO')
        check(ARENA <= pointer <= ARENA + 0x8000000 - 80 and pointer % 4096 == 0,
              'invalid SMP Report pointer')
        report = self.readwords(pointer, 10, 'user SMP report')
        check(report[:5] == [1, 0, 1, 4, 15], 'SMP not fully published')
        check(report[6] == pointer + 256 and report[7] == self.ksym('smp.runtime', 'CPUS'),
              'report does not identify actual Header table / linked CPU contexts')
        check(ARENA <= report[5] <= ARENA + 0x8000000 - 65536 and report[5] % 4096 == 0
              and report[8] == self.evidence['trusted_kernel_page_table_pool']['root_physical'],
              'report domain/root identity differs')
        domain = self.readwords(report[5], 15, 'user domain')
        check(domain[:2] == [1, 0] and domain[4] == report[4] and domain[9] == report[8]
              and domain[13] == report[5] and domain[14] == 65536
              and domain[10] == report[5] + 128
              and domain[11] == domain[10] + 12992
              and domain[12] == domain[11] + 1920,
              'domain-owned arena layout differs')
        # read() validates the allocated arena and exact physical mapping before
        # every access. No unvalidated Domain CPU pointer is dereferenced.
        raw_cpus = self.read(domain[11], 4 * 120, 'four CPU ownership records')
        cpus = [words(raw_cpus[i * 120:(i + 1) * 120], 15) for i in range(4)]
        return dict(report=report, domain=domain, cpus=cpus)

    def hardware_registers(self):
        """Four in-memory reads; no physical access, file I/O, or PASS evidence."""
        check(self.stopped, 'register prefilter requires a stopped guest')
        stop_id = self.stop_id
        registers, texts = [], []
        for i in range(4):
            text = self.qmp.request('human-monitor-command',
                                    {'command-line': 'info registers', 'cpu-index': i})
            texts.append(text)
            registers.append(oracle.registers(text))
        check(self.stopped and self.stop_id == stop_id,
              'register observation crossed a stop boundary')
        return registers, texts

    def observe_initial(self):
        """Latch only the cheap sampling phase, never Catalog or proof state."""
        check(self.stopped, 'initial observation requires a stopped guest')
        if not self.gui_sampling_started:
            pointer = self.catalog_pointer()
            self.catalog_initialized = bool(
                pointer and self.readwords(pointer, 3, 'Catalog publication')[:2] == [1, 18])
            window = (self.read(pointer + GUI_OFFSET, 256, 'GUI startup prefilter')
                      if self.catalog_initialized else None)
            if window is None or not any(
                    struct.unpack_from('<Q', window, i * 64 + 16)[0] for i in range(4)):
                return None
            self.gui_sampling_started = True
            self.evidence['register_prefilter']['armed_at_stop_id'] = self.stop_id
        # A stale phase latch can only cause extra register reads. It cannot
        # supply Catalog, registers, ownership, or any acceptance evidence.
        registers, _ = self.hardware_registers()
        count = sum(reg['CS'] & 3 == 3 for reg in registers[1:])
        stats = self.evidence['register_prefilter']
        stats['samples'] += 1
        stats['ap_cpl3_counts'][count] += 1
        if count < 2:
            return None
        stats['full_candidates'] += 1
        # Re-read EVERYTHING in the same stop; no prefilter data is an input.
        return self.capture_initial()

    def capture_initial(self):
        stop_id = self.stop_id
        stopped_before = self.qmp.request('query-status').get('running') is False
        check(self.stopped and stopped_before, 'candidate capture requires a stopped guest')
        registers, texts = self.hardware_registers()
        check(sum(reg['CS'] & 3 == 3 for reg in registers[1:]) >= 2,
              'candidate has fewer than two APs in hardware CPL3')
        catalog = self.catalog()
        hardware_dumps = []
        for i, text in enumerate(texts):
            path = self.state / f'initial-{self.stop_id}-cpu-{i}.txt'
            path.write_text(text)
            hardware_dumps.append(dict(cpu=i, file=path.name, sha256=timing.sha(path),
                                       stop_id=self.stop_id))
        diagnostic = dict(diagnostic_only=True, stop_id=self.stop_id,
                          hardware_dumps=hardware_dumps, registers=registers, complete=False)
        try:
            ownership = self.candidate_domain()
            diagnostic.update(ownership)
            check(self.qmp.request('query-status').get('running') is False,
                  'candidate diagnostic did not remain stopped')
            diagnostic['complete'] = True
        except Exception as exc:
            diagnostic['error'] = type(exc).__name__ + ': ' + str(exc)
            raise
        finally:
            diagnostic['physical_reads'] = [chunk for chunk in self.chunks
                                            if chunk['stop_id'] == self.stop_id]
            write(self.state / f'candidate-{self.stop_id}.json', diagnostic)
        report, domain, cpus = (ownership[key] for key in ('report', 'domain', 'cpus'))
        addresses = self.readwords(report[6], 4, 'private Header pointers')
        check(len(set(addresses)) == 4 and all(a % 4096 == 0 for a in addresses),
              'private Header pages overlap or are unaligned')
        raw_processes = self.read(domain[12], 16 * 56, 'sixteen process ownership records')
        processes = [words(raw_processes[i * 56:(i + 1) * 56], 7) for i in range(16)]
        raw_threads = self.read(domain[10] + THREADS_OFFSET, 64 * 64, 'bounded queue thread array')
        threads = [words(raw_threads[i * 64:(i + 1) * 64], 8) for i in range(64)]
        headers = [self.readwords(a, 32, 'private CPU Header') for a in addresses]
        metrics = [self.readwords(a + 5632, 24, 'private CPU hardware Metrics') for a in addresses]
        contexts = [words(self.kernel(report[7] + i * 256, 256, 'linked CPU Context'), 32)
                    for i in range(4)]
        self.refresh_processes()
        self.validate_private_pools()
        init = self.verify_process(5, 'init')
        initial_bytes = self.init_global('SNAPSHOTS', 2048, init)
        record = dict(catalog=catalog, report=report, domain=domain, cpus=cpus,
                      processes=processes, threads=threads, headers=headers,
                      metrics=metrics, contexts=contexts, registers=registers,
                      header_addresses=addresses, syscall_entry=self.symbols['user_smp_syscall_entry'],
                      init_initial=[snapshot_record(initial_bytes[i * 64:(i + 1) * 64])
                                    for i in range(32)],
                      init_manager_hex=self.init_global('MANAGER', 5656, init).hex(),
                      init_started=words(self.init_global('STARTED', 64, init), 8),
                      trace_hex=self.trace().hex(), stop_id=self.stop_id,
                      hardware_dumps=hardware_dumps, stopped_before=stopped_before,
                      stopped_after=self.qmp.request('query-status').get('running') is False)
        check(self.stopped and self.stop_id == stop_id,
              'full initial capture crossed a stop boundary')
        proof = validate_initial(record)
        verified = [init, self.verify_process(3, 'compositor')]
        for cfg in proof['ap_gui_configurations']:
            slot = catalog['slots'][cfg]
            image = self.verify_process(slot, life.NAMES[cfg])
            bind_gui_image(image, cfg, catalog, processes)
            verified.append(image)
        record['verified_processes'] = verified
        record['kernel_executable_bytes_verified'] = self.verify_code()
        check(self.stopped and self.stop_id == stop_id
              and self.qmp.request('query-status').get('running') is False,
              'executable verification did not remain in the initial stop')
        record['physical_reads'] = [chunk for chunk in self.chunks if chunk['stop_id'] == self.stop_id]
        record['proof'] = proof
        return record

    def start(self):
        disk = self.state / 'disk.img'
        clock.create(disk, 64)
        up = storage.free_port()
        self.qmp_path = qmp_socket_path(self.state)
        check(not self.qmp_path.exists() and not self.qmp_path.is_symlink(),
              'owned QMP socket path already exists')
        command = command_for(self.esp, self.state, disk, up)
        self.evidence['command'] = command
        self.evidence.update(qmp_transport='unix', qmp_socket=str(self.qmp_path))
        write(self.state / 'command.json', command)
        self.stderr = (self.state / 'stderr.log').open('wb')
        self.process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=self.stderr)
        self.evidence['actual_qemu_executed'] = True
        self.qmp = UnixQMP(self.qmp_path, self.process)
        check(self.qmp.request('query-kvm').get('enabled') is False, 'structural runner unexpectedly used KVM')
        check(self.qmp.request('query-status').get('running') is False, 'guest ran before observation setup')
        self.uart = socket.create_connection(('127.0.0.1', up))
        self.uart.settimeout(.2)

        def reader():
            with (self.state / 'serial.log').open('wb') as stream:
                while self.process.poll() is None:
                    try:
                        data = self.uart.recv(4096)
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    if not data:
                        break
                    self.raw.extend(data)
                    stream.write(data)
                    stream.flush()
        self.reader = threading.Thread(target=reader, daemon=True)
        self.reader.start()
        self.deadline = time.monotonic() + self.timeout
        self.resume()
        pattern = rb'^memory_runtime_boot_info=0x([0-9a-f]{16})\r?$'
        while not re.search(pattern, self.raw, re.M):
            self.alive()
            time.sleep(.001)
        self.pause()
        matches = re.findall(pattern, self.raw, re.M)
        check(len(matches) == 1, 'one original BootInfo publication required')
        self.boot = struct.unpack('<20Q', self.physical(int(matches[0], 16) - clock.acpi.HHDM, 160, 'original BootInfo'))
        check(self.boot[1:3] == (1, 160) and self.boot[15] > 0 and self.boot[15] % 4096 == 0,
              'invalid original BootInfo')
        dense_index = 0
        while True:
            self.alive()
            try:
                initial = self.observe_initial()
            except ValueError as exc:
                self.candidate_rejections.append(dict(stop_id=self.stop_id, reason=str(exc)))
            else:
                if initial is not None:
                    write(self.state / 'initial.json', initial)
                    self.evidence['initial_window_observed'] = True
                    break
            check(MARKERS[1] not in self.raw, 'initial AP/STARTING window missed; late readiness is not proof')
            # Do not pay dense observer overhead during firmware/CPL0 setup.
            # This only adjusts sampling cadence, never the same-stop oracle.
            # Vary the dense cadence rather than repeatedly requesting the same
            # 1ms as the optional user quantum. This does not guarantee overlap.
            delay = sampling_delay(self.catalog_initialized, self.gui_sampling_started, dense_index)
            if self.gui_sampling_started:
                dense_index += 1
            self.sample_after(delay)
        self.resume()
        while not all(marker in self.raw for marker in MARKERS):
            self.alive()
            time.sleep(.01)
        self.pause()
        check_completion(self.raw)
        final = dict(catalog=self.catalog(), trace_hex=self.trace().hex())
        decoded = boot_trace_capture.capture(self, self.state / 'trace')
        check((self.state / 'trace/trace.bin').read_bytes() == bytes.fromhex(final['trace_hex']),
              'final trace changed while stopped')
        validate_final(initial, final, decoded)
        check_completion(self.raw)
        write(self.state / 'final.json', final)
        return initial, final, decoded


def run(esp, state, timeout):
    check(math.isfinite(timeout) and 1 <= timeout <= 600, 'timeout must be 1..600 seconds')
    state = Path(state)
    state.mkdir(parents=True, exist_ok=False)
    before = timing.runner_fingerprints()
    result = dict(passed=False, structural_only=True, kvm_timing_proven=False,
                  actual_kvm_boots=0, actual_qemu_executed=False, actual_qemu_boots=0,
                  init_cross_ap_proven=False, all_started_guests_stopped=True)
    guest, binding, auxiliary = None, None, None
    write(state / 'runner-source-before.json', before)
    try:
        binding = timing.verify_build(esp)
        auxiliary = bind_auxiliary(Path(binding['esp']))
        result.update(build_binding=binding, auxiliary_binding=auxiliary)
        guest = InitialGuest(Path(binding['esp']), state, timeout)
        initial, final, decoded = guest.start()
        result.update(passed=True, init_cross_ap_proven=True, initial=initial['proof'],
                      final_trace=decoded, actual_qemu_boots=1)
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
        if guest:
            try:
                guest.capture_failure()
            except Exception as diagnostic:
                result['diagnostic_error'] = str(diagnostic)
    finally:
        if guest:
            try:
                guest.close()
            except Exception as exc:
                result.update(passed=False, cleanup_error=str(exc))
            # Retain receipts independently of close()/diagnostic success.
            for name, content in (('physical-manifest.json', guest.chunks),
                                  ('sampling.json', guest.sampling),
                                  ('observation-intervals.json', guest.observations),
                                  ('candidate-rejections.json', guest.candidate_rejections)):
                try:
                    write(state / name, content)
                except Exception as exc:
                    result.update(passed=False, receipt_error=type(exc).__name__ + ': ' + str(exc))
            result['guest'] = guest.evidence
            result['actual_qemu_executed'] = guest.evidence['actual_qemu_executed']
            result['actual_qemu_boots'] = int(guest.evidence['actual_qemu_executed'])
            result['all_started_guests_stopped'] = guest.process is None or guest.process.poll() is not None
            if not result['all_started_guests_stopped']:
                result['passed'] = False
        try:
            after = timing.runner_fingerprints()
            write(state / 'runner-source-after.json', after)
            check(before == after, 'observer dependencies changed during capture')
            if binding:
                check(timing.verify_build(esp) == binding and bind_auxiliary(Path(binding['esp'])) == auxiliary,
                      'source/build/observer inputs changed during capture')
            result['inputs_unchanged'] = True
        except Exception as exc:
            result.update(passed=False, inputs_unchanged=False, input_error=str(exc))
        if not result['passed']:
            result['init_cross_ap_proven'] = False
        write(state / 'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    state = args.output or ROOT / 'build/test/p6-initial-dag' / ('run-' + uuid.uuid4().hex[:12])
    result = run(args.reuse_esp, state, args.timeout)
    print(json.dumps(dict(result=str(state / 'result.json'), passed=result['passed'],
                          error=result.get('error')), indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
