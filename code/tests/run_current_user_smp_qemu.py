#!/usr/bin/env python3
"""Current-source identity/planning and read-only observation helpers.

New implementation, not recovered historical runner. CLI never starts a guest;
there is deliberately no --execute switch. ProcessGuest adapters reuse existing
physical/ELF verification infrastructure for separately authorized future use.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import re
import struct
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests import run_process_lifecycle_qemu as life
from tests import user_smp_oracle as oracle
from tests import current_user_smp_acceptance as acceptance
from tools.elf_symbols import read_elf_symbols

ROOT = BASE = Path(__file__).resolve().parents[1]
NAMES = life.NAMES
storage, settings = life.storage, life.settings
check = oracle.check


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative_file(root, name):
    check(isinstance(name, str) and name and not Path(name).is_absolute() and
          '..' not in Path(name).parts, 'unsafe receipt path')
    path = root / name
    check(path.resolve().is_relative_to(root.resolve()) and path.is_file() and not path.is_symlink(),
          'missing or escaped receipt file: ' + name)
    return path


def verify_hashes(root, values, label):
    check(isinstance(values, dict) and bool(values), label + ' manifest empty')
    for name, expected in values.items():
        check(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'invalid SHA-256')
        check(sha(relative_file(root, name)) == expected, label + ' changed: ' + name)


def identity(esp, negative=False):
    esp = Path(esp).resolve()
    check(esp.is_dir(), 'completed ESP directory required')
    output = esp.parent
    try:
        record = json.loads((output / 'current-user-smp-source.json').read_text())
        metadata = json.loads((output / 'build-inputs.json').read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('completed current source receipt required') from exc
    check(record.get('schema') == 1 and record.get('contract') == 'current-user-smp-v1', 'unknown current receipt contract')
    check(record.get('user_case') == ('omit-xstate' if negative else None),
          'negative experiment must be explicitly selected')
    for name, value in {'built': True, 'source_unchanged': True, 'test': True,
                        'runtime_level': 7, 'user_smp': True, 'user_workload': True}.items():
        check(type(record.get(name)) is type(value) and record.get(name) == value,
              'completed source receipt flag differs: ' + name)
    check(Path(record['source_root']).is_absolute() and Path(record['source_root']).resolve() == BASE.resolve(),
          'receipt source root is not the verified source root')
    check(record.get('esp') == str(esp), 'receipt ESP differs')
    for name in ('test', 'runtime_level', 'source_unchanged'):
        check(type(metadata.get(name)) is type(record[name]) and metadata[name] == record[name], 'build receipt flags disagree')
    check(metadata.get('graphics_case') is None, 'graphics fault injection not allowed')
    check(metadata.get('source_sha256') == record['source_sha256'], 'build/source graph manifests disagree')
    verify_hashes(BASE, record['source_sha256'], 'current builder/workload/include')
    check(all(name.startswith('kernel/') for name in record['staged_kernel_sha256']), 'staged kernel path invalid')
    verify_hashes(output / 'source', record['staged_kernel_sha256'], 'staged kernel')
    artifacts = metadata.get('artifacts', {})
    verify_hashes(output, artifacts, 'artifact')
    check(artifacts.get('kernel.elf') == record.get('kernel_elf_sha256') == sha(output / 'kernel.elf'),
          'kernel artifact changed or unbound')
    workloads = record['workload_elf_sha256']
    check(set(workloads) == set(NAMES[7:12]), 'five workload ELF hashes required')
    for name, expected in workloads.items():
        path = 'services/' + name + '/program.elf'
        check(artifacts.get(path) == expected == sha(relative_file(output, path)), 'workload artifact changed or unbound')
    return record


class UserGuest(life.ProcessGuest):
    def __init__(self, *args, **kwargs):
        self._constructing = True
        self._early_failure_capture = False
        self._constructor_cleanup_attempted = False
        try:
            super().__init__(*args, **kwargs)
        except BaseException:
            # The underlying constructor normally calls our close itself. If
            # it failed before that handler, clean up only resources it owns.
            if not self._constructor_cleanup_attempted:
                try:
                    self.close()
                except Exception:
                    # Cleanup must not replace the original constructor error.
                    pass
            raise
        finally:
            self._constructing = False

    def close(self):
        constructing = getattr(self, '_constructing', False)
        if constructing:
            self._constructor_cleanup_attempted = True
        try:
            process = getattr(self, 'process', None)
            if (constructing and not getattr(self, '_early_failure_capture', False)
                    and getattr(self, 'qmp', None) is not None
                    and process is not None and process.poll() is None):
                self._early_failure_capture = True
                try:
                    self.capture_failure()
                except Exception as exc:
                    try:
                        storage.write_json(self.state / 'failure-capture-error.json',
                                           {'error': type(exc).__name__ + ': ' + str(exc)})
                    except Exception:
                        # Full disks and failed diagnostic writes cannot keep
                        # an owned guest alive or mask the boot failure.
                        pass
        finally:
            super().close()

    def capture_failure(self):
        """Capture actual read-only state even before desktop initialization.

        No source fixture supplies observations. Unpublished pointers and
        unavailable reads are individually reported, not replaced with zeros.
        physical() records the raw-file/hash receipts for successful reads.
        """
        report = {'constructor_failure': bool(getattr(self, '_constructing', False)),
                  'historical_acceptance': False, 'diagnostic_only': True}

        def observe(label, action):
            try:
                value = action()
                report[label] = value
                return value
            except Exception as exc:
                report[label] = type(exc).__name__ + ': ' + str(exc)
                return None

        observe('pause', lambda: (self.pause(), 'completed')[1])
        if not hasattr(self, 'chunks'):
            self.chunks = []
        if not hasattr(self, 'symbols'):
            symbols = observe('symbols', lambda: settings.acpi.validation_symbols(self.esp.parent / 'kernel.elf'))
            if symbols is not None:
                self.symbols = symbols
        if not hasattr(self, 'boot'):
            def bootstrap():
                values = re.findall(rb'^memory_runtime_boot_info=0x([0-9a-fA-F]{16})\r?$',
                                    bytes(getattr(self, 'raw', b'')), re.MULTILINE)
                check(bool(values) and len(set(values)) == 1,
                      'missing or conflicting actual runtime BootInfo address')
                physical = int(values[0], 16) - settings.acpi.HHDM
                check(0 < physical < 1 << 48, 'invalid early BootInfo physical address')
                return struct.unpack('<20Q', self.physical(physical, 160, 'early failure BootInfo'))
            boot = observe('boot_info', bootstrap)
            if boot is not None:
                self.boot = boot

        def smp_report():
            address = self.kval('sched.user_boot', 'INFO')
            check(address != 0, 'user SMP report not published')
            return self.readwords(address, 10)
        smp = observe('smp', smp_report)
        # Four is the existing owned QEMU command's topology. Before a valid
        # publication it is only a diagnostic request count, not proof that
        # four CPUs were online. Missing CPU responses stay explicit errors.
        count = smp[3] if isinstance(smp, list) and len(smp) == 10 and 1 <= smp[3] <= 16 else 4
        report['requested_cpu_indices'] = list(range(count))
        for cpu in range(count):
            observe('cpu_' + str(cpu) + '_registers', lambda cpu=cpu: self.hmp(cpu, 'info registers'))
            observe('cpu_' + str(cpu) + '_lapic', lambda cpu=cpu: self.hmp(cpu, 'info lapic'))
        for label, module, name, size in (
                ('processes', 'user.memory', 'PROCESSES', 16 * 1288),
                ('current', 'user.services', 'CURRENT', 8),
                ('faults', 'user.services', 'USER_FAULTS', 8),
                ('irqs', 'user.services', 'USER_IRQS', 8)):
            observe(label, lambda module=module, name=name, size=size:
                    oracle.words(self.kernel(self.ksym(module, name), size, 'failure ' + module + '.' + name), size // 8))
        for name, size in (('user_active_frame', 200), ('user_context_cpu', 64),
                           ('user_context_last_error', 8)):
            observe(name, lambda name=name, size=size:
                    oracle.words(self.kernel(self.symbols[name], size, 'failure ' + name), size // 8))
        observe('exception', lambda: oracle.words(self.kernel(
            self.symbols['cpu_exception_stack_top'] - 184, 184, 'failure hardware exception context'), 23))
        report['physical_reads'] = list(self.chunks)
        report['serial_sha256'] = hashlib.sha256(bytes(getattr(self, 'raw', b''))).hexdigest()
        storage.write_json(self.state / 'failure.json', report)
        return report

    def hmp(self, cpu, command):
        check(type(cpu) is int and 0 <= cpu < 16, 'invalid CPU index')
        return self.qmp.request('human-monitor-command', {'command-line': command, 'cpu-index': cpu})

    def read(self, address, length):
        return self.kernel(address, length, 'current SMP trusted kernel observation')

    def readwords(self, address, count):
        return oracle.words(self.read(address, count * 8), count)

    def effective(self, root, virtual):
        entry = self.pte(root, virtual)
        return dict(present=bool(entry & 1), effective_user=bool(entry & 4),
                    effective_nx=bool(entry & (1 << 63)), physical=(entry & storage.MASK) + (virtual & 4095))

    def worker(self, cfg, argument, snapshot):
        check(cfg in acceptance.ARGS and argument == acceptance.ARGS[cfg], 'unknown worker/argument')
        catalog = self.catalog()
        slot = catalog['slots'][cfg]
        check(type(slot) is int and 0 <= slot < 16, 'invalid worker slot')
        incarnation = catalog['incarnations'][slot]
        token = catalog['snapshots'][cfg]['process']
        check(token == (incarnation << 8) | (slot + 1), 'catalog worker token differs')
        process = self.verify_process(slot, NAMES[cfg])
        owned = oracle.words(struct.pack('<7Q', *snapshot['processes'][slot]), 7)
        check(owned[0] == token and owned[1] == incarnation and owned[2] == process['root'], 'worker private domain ownership differs')
        symbols = read_elf_symbols(self.esp.parent / 'services' / NAMES[cfg] / 'program.elf')
        address = process['bias'] + symbols[storage.symbol('apps.user_smp_worker', 'PROBE')]
        probe = oracle.words(self.user(slot, address, 192, 'current worker probe'), 24)
        apics = [context[2] for context in snapshot['contexts']]
        oracle.worker(probe, argument, slot + 1, cfg, incarnation, apics)
        acceptance.avx(snapshot)
        check(probe[7] == 1, 'actual upper-YMM worker path required')
        raw = self.read(owned[4], 1024)
        oracle.xstate(raw, argument, slot + 1, True)
        # Fixed-VA private page is the independent translation-isolation word.
        # Current services.channels() publishes the argument read-only here.
        mapping = self.effective(process['root'], 0x44000000)
        check(mapping['present'] and mapping['effective_user'] and mapping['effective_nx'], 'fixed-VA permissions differ')
        check(struct.unpack('<Q', self.physical(mapping['physical'], 8, 'worker fixed-VA word'))[0] == argument,
              'fixed-VA argument differs')
        return dict(cfg=cfg, slot=slot, token=token, incarnation=incarnation, probe=probe,
                    root=process['root'], argument=argument, physical=mapping['physical'],
                    actual_upper_ymm_verified=True)


GUI_CONFIGS = (14, 15, 16, 17)


def _gui_historical_catalog(guest):
    """Capture a fresh stopped epoch, then audit that history after explicit cont."""
    image = guest.capture_image('gui-catalog')
    epoch, serial_offset = image.epoch, image.serial_offset
    check(guest.stopped is True and type(epoch) is int and epoch > 0
          and guest.current_epoch == epoch, 'GUI historical image is not the current paused epoch')
    check(type(serial_offset) is int and 0 <= serial_offset <= len(guest.raw)
          and serial_offset >= guest.evidence.get('gui_last_fresh_command_end', 0),
          'GUI historical image predates the fresh UART response')
    history = guest.evidence.setdefault('gui_catalog_captures', [])
    check(isinstance(history, list) and (not history or epoch > history[-1]['epoch']
          and serial_offset >= history[-1]['serial_offset']), 'GUI historical image was reused or moved backwards')
    boot = copy.deepcopy(image.boot_info_ref)
    registers = [copy.deepcopy(image.register_ref(cpu)) for cpu in range(4)]
    check(isinstance(boot, dict) and boot.get('epoch') == epoch and boot.get('length') == 160
          and boot.get('bulk_id') == 'e%d:boot-info' % epoch and boot.get('offset') == 0,
          'GUI historical BootInfo belongs to another epoch')
    check(all(isinstance(ref, dict) and ref.get('epoch') == epoch
              and type(ref.get('cpu_index')) is int and ref['cpu_index'] == cpu
              for cpu, ref in enumerate(registers)), 'GUI historical register sources differ from captured CPUs/epoch')
    # No heavy Catalog walk or filesystem-backed validation while paused.
    guest.resume()
    check(guest.stopped is False, 'GUI historical audit requires actual successful cont')
    before = len(image.chunks)
    catalog = copy.deepcopy(image.catalog())
    refs = copy.deepcopy(image.chunks[before:])
    check(bool(refs) and all(isinstance(ref, dict) and ref.get('epoch') == epoch for ref in refs),
          'GUI Catalog lacks same-epoch historical raw references')
    receipt = dict(epoch=epoch, serial_offset=serial_offset, boot_info_ref=boot,
                   registers=registers, catalog_refs=refs, historical=True)
    check(isinstance(catalog, dict) and '_historical_capture' not in catalog,
          'invalid historical GUI Catalog')
    catalog['_historical_capture'] = receipt
    history.append(copy.deepcopy(receipt))
    return catalog


def _gui_catalog(guest):
    """Audit one explicit observation, retaining configuration/token identities."""
    historical = getattr(guest, 'historical_capture', False)
    check(type(historical) is bool, 'unsupported GUI capture profile')
    if historical:
        c = _gui_historical_catalog(guest)
    else:
        guest.pause()
        check(guest.stopped is True, 'GUI control requires a paused Catalog')
        c = copy.deepcopy(guest.catalog())
    check(isinstance(c, dict), 'invalid GUI Catalog record')
    for key, length in (('configs', 32), ('snapshots', 32), ('slots', 32),
                        ('incarnations', 16), ('configurations', 16)):
        check(isinstance(c.get(key), list) and len(c[key]) == length, 'incomplete GUI Catalog ' + key)

    def word(value):
        return type(value) is int and 0 <= value <= life.NONE

    check(word(c.get('sequence')) and all(word(v) and v <= 0x0fffffff for v in c['incarnations']),
          'invalid GUI Catalog sequence/incarnation')
    tokens = set()
    for cfg, s in enumerate(c['snapshots']):
        check(isinstance(s, dict) and all(word(s.get(k)) for k in
              ('configuration', 'process', 'generation', 'state', 'status', 'sequence', 'argument'))
              and s['configuration'] == cfg and s['state'] <= 5 and s['sequence'] <= c['sequence'],
              'invalid GUI Catalog snapshot')
        slot, token = c['slots'][cfg], s['process']
        check(word(slot), 'invalid GUI Catalog slot')
        if token:
            check(cfg < 18 and slot < 16 and (slot == 13 if cfg == 13 else slot != 13)
                  and c['configurations'][slot] == cfg and c['incarnations'][slot] > 0
                  and token == (c['incarnations'][slot] << 8) | (slot + 1)
                  and token not in tokens and s['generation'] > 0 and s['state'] in (1, 2),
                  'GUI Catalog token/slot/incarnation alias')
            tokens.add(token)
        else:
            check(slot == life.NONE and s['state'] in (0, 3, 4, 5), 'GUI stopped configuration retains ownership')
    for slot, cfg in enumerate(c['configurations']):
        check(word(cfg) and (cfg == life.NONE or cfg < 18 and c['slots'][cfg] == slot
                            and c['snapshots'][cfg]['process'] != 0), 'GUI Catalog inverse map differs')
    for cfg in range(18):
        expected = 7 if cfg in (0, 1, 3, 6) else 5 if cfg < 7 else 4 if cfg == 13 else 9 if cfg >= 14 else 8
        meta = c['configs'][cfg]
        check(isinstance(meta, dict) and all(word(meta.get(k)) for k in ('id', 'flags', 'dependencies'))
              and meta['id'] == cfg and meta['flags'] == expected
              and meta.get('dependencies') == life.DEPS[cfg], 'GUI configured role/flags/dependencies differ')
    check(c['slots'][0] == 0 and c['configurations'][0] == 0
          and all(c['snapshots'][cfg]['state'] == 2 for cfg in range(7)),
          'GUI control requires the live slot-zero shell and READY essential services')
    return c


def _gui_owner(c, cfg):
    s = c['snapshots'][cfg]
    slot = c['slots'][cfg]
    return dict(configuration=cfg, process=s['process'], generation=s['generation'], state=s['state'],
                status=s['status'], argument=s['argument'], slot=slot,
                incarnation=c['incarnations'][slot] if slot != life.NONE else None)


def _gui_stable(initial, current):
    for cfg in (*range(7), 13):
        check(_gui_owner(initial, cfg) == _gui_owner(current, cfg), 'GUI control changed an essential service')
    for cfg in GUI_CONFIGS:
        before, now = _gui_owner(initial, cfg), _gui_owner(current, cfg)
        check(now['generation'] == before['generation'], 'GUI configuration generation changed')
        if now['process']:
            check(all(now[k] == before[k] for k in ('process', 'slot', 'incarnation')),
                  'GUI current token/slot/incarnation changed')
        if before['process']:
            slot = before['slot']
            check(current['incarnations'][slot] == before['incarnation']
                  and current['configurations'][slot] == (cfg if now['process'] else life.NONE),
                  'GUI former slot was reused or retained')


def _gui_shell(guest, command, *, exact=None):
    """Bind a shell receipt back to this call's actual fresh UART bytes."""
    start = len(guest.raw)
    receipt = guest.shell(command, exact=exact)
    check(isinstance(receipt, dict) and receipt.get('command') == command
          and type(receipt.get('serial_offset')) is int and start <= receipt['serial_offset'] <= len(guest.raw)
          and receipt.get('command_utf8_sha256') == hashlib.sha256(command.encode('utf-8')).hexdigest()
          and receipt.get('complete_echo_and_new_prompt_verified') is True
          and type(receipt.get('error_code')) is int and receipt['error_code'] == 0,
          'GUI shell receipt is stale or names another command')
    segment = bytes(guest.raw[receipt['serial_offset']:])
    fresh = life.fat.fresh_response(segment, command, exact=exact)
    check(fresh is not None and all(receipt.get(k) == v for k, v in fresh.items())
          and fresh['complete_echo_and_new_prompt_verified'] is True and fresh['error_code'] == 0,
          'GUI shell receipt differs from the fresh UART response')
    if getattr(guest, 'historical_capture', False) is True:
        echo = command.encode('utf-8') + b'\r\n'
        prompt_end = segment.index(echo) + len(echo) + len(bytes.fromhex(fresh['response_hex'])) + 2
        guest.evidence['gui_last_fresh_command_end'] = receipt['serial_offset'] + prompt_end
    return dict(receipt, verified_serial_length=len(segment),
                verified_serial_sha256=hashlib.sha256(segment).hexdigest()), bytes.fromhex(fresh['response_hex'])


def close_gui(guest):
    """Kill only current ordinary GUI tokens; preserve raw UART/Catalog evidence.

    shell() uses the existing authenticated slot-zero shell. No guest memory or
    register writes, stop alias, retry on stale identity, or success-on-error.
    The caller continues to own cleanup if any validation raises.
    """
    report = dict(schema=1, completed=False, stage='initial-catalog', clients=[])
    check(isinstance(guest.evidence, dict), 'GUI control requires the owned guest evidence record')
    history = guest.evidence.setdefault('gui_controls', [])
    check(isinstance(history, list), 'invalid GUI control evidence history')
    history.append(report)
    initial = _gui_catalog(guest)
    report['initial_catalog'] = initial
    report['stage'] = 'ps'
    ps, body = _gui_shell(guest, 'ps')
    report['ps'] = ps
    listed = life.parse_ps(body)
    canonical = b''.join(('PROCESS ' + row['name'] + ' id=' + str(row['id']) + ' token=' + str(row['token'])
                          + ' generation=' + str(row['generation']) + ' state=' + str(row['state'])
                          + ' status=' + str(row['status']) + '\r\n').encode('ascii') for row in listed)
    check(body == canonical, 'GUI ps response contains extra or malformed records')
    after_ps = _gui_catalog(guest)
    report['ps_catalog'] = after_ps
    _gui_stable(initial, after_ps)
    for cfg, row in enumerate(listed):
        s = after_ps['snapshots'][cfg]
        check(all(row[key] == s[field] for key, field in
                  (('token', 'process'), ('generation', 'generation'), ('state', 'state'), ('status', 'status'))),
              'GUI ps response differs from the paused Catalog')
    records = report['clients']
    for cfg in GUI_CONFIGS:
        report['stage'] = 'configuration-' + str(cfg)
        before = _gui_catalog(guest)
        _gui_stable(initial, before)
        owner = _gui_owner(before, cfg)
        record = dict(configuration=cfg, name=NAMES[cfg], before=owner)
        records.append(record)
        if owner['process'] == 0:
            record.update(action='already-stopped', after=owner)
        else:
            command = 'kill ' + str(owner['process'])
            record['requested_command'] = command
            exact = ('KILL OK token=' + str(owner['process']) + ' generation=0 state=5 status=0\r\n').encode('ascii')
            receipt, _ = _gui_shell(guest, command, exact=exact)
            record['command'] = receipt
            after = _gui_catalog(guest)
            _gui_stable(initial, after)
            stopped = _gui_owner(after, cfg)
            check(stopped['process'] == 0 and stopped['slot'] == life.NONE
                  and stopped['generation'] == owner['generation'] and stopped['state'] == 5
                  and stopped['status'] == 0 and after['configurations'][owner['slot']] == life.NONE
                  and after['incarnations'][owner['slot']] == owner['incarnation'],
                  'GUI KILL OK lacks the same-generation KILLED Catalog and released old slot')
            record.update(action='killed', after=stopped)
    report['stage'] = 'final-catalog'
    final = _gui_catalog(guest)
    report['final_catalog'] = final
    _gui_stable(initial, final)
    for record in records:
        now = _gui_owner(final, record['configuration'])
        check(now['process'] == 0 and now == record['after'], 'GUI client restarted or changed after close')
    report.update(completed=True, stage='complete', authenticated_shell_commands=True,
                  essential_identities_preserved=True)
    return report


def negative(guest):
    close_gui(guest)
    initial = guest.catalog()
    life.check_boot_dag(initial)
    start = len(guest.raw)
    records = {}
    for cfg, arg in acceptance.ARGS.items():
        response = guest.shell('run ' + NAMES[cfg] + ' ' + str(arg))
        text = bytes.fromhex(response['response_hex']).decode('ascii')
        match = re.search(r'RUN OK ' + re.escape(NAMES[cfg]) + r' token=(\d+) generation=(\d+) state=(\d+) status=(\d+)', text)
        check(match is not None, 'missing actual SIMD launch receipt')
        records[cfg] = dict(zip(('token', 'generation', 'state', 'status'), map(int, match.groups())))
    deadline = time.monotonic() + 90
    while True:
        marker = bytes(guest.raw).find(b'DONGOS_P6_USER_WORKER_BAD', start)
        final = guest.catalog()
        snapshot = guest.snapshot()
        try:
            acceptance.negative_binding(final, records, initial['sequence'])
            acceptance.avx(snapshot)
            check(marker >= start and sum(v[2] for v in snapshot['metrics'][1:]) > 0,
                  'missing actual SIMD marker/AP timer')
            counts = acceptance.service_counts(guest)
            return dict(snapshot=snapshot, catalog=final, launched_workers=records,
                        catalog_start_sequence=initial['sequence'], serial_marker_offset=marker,
                        serial_start_offset=start, actual_negative_busy_simd_assertion=True,
                        actual_fault_status_6=True, actual_ap_user_timer=True, service_counts=counts)
        except ValueError as exc:
            if time.monotonic() >= deadline:
                raise ValueError('missing actual SIMD fresh token-bound #UD evidence') from exc
            time.sleep(.01)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp', type=Path, required=True)
    parser.add_argument('--negative-xstate', action='store_true')
    args = parser.parse_args()
    record = identity(args.reuse_esp, args.negative_xstate)
    print(json.dumps(dict(mode='identity-only', guest_started=False, historical_acceptance=False,
                          source_identity=record), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
