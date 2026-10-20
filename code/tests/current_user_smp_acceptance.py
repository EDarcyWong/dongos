"""New current-source, read-only evidence validators. Not historical acceptance.

Successful validation establishes consistency of supplied records, not that a
host fixture executed a guest. All public seal results explicitly retain that
limitation. File receipts bind bytes but do not authenticate their producer.
"""
import hashlib
import json
from pathlib import Path
from tests import user_smp_oracle as oracle

ARGS = {7: 78117, 8: 88219, 9: 99323, 10: 104729, 11: 115249}
check = oracle.check


def uint(value):
    return type(value) is int and 0 <= value < 1 << 64


def words(value, size, label):
    check(isinstance(value, (list, tuple)) and len(value) == size and
          all(uint(v) for v in value), 'malformed ' + label)
    return value


def avx(snapshot):
    metrics = snapshot.get('metrics', [])
    check(len(metrics) == 4, 'four actual CPU metrics required')
    for metric in metrics:
        words(metric, 24, 'CPU metrics')
        check(metric[18] & (1 << 18) and metric[19] & 7 == 7,
              'actual XCR0/OSXSAVE does not enable upper-YMM')


def workers(snapshot, values, arguments):
    avx(snapshot)
    check(arguments == ARGS and len(values) == 5 and
          {v['cfg'] for v in values} == set(ARGS), 'five distinct worker configurations required')
    check(len({v['slot'] for v in values}) == 5, 'workers must own distinct slots')
    processes = snapshot['processes']
    check(len(processes) == 16, 'sixteen process records required')
    for value in values:
        cfg, slot, inc = value['cfg'], value['slot'], value['incarnation']
        check(uint(slot) and slot < 16 and uint(inc) and 0 < inc <= 0x0fffffff, 'worker identity invalid')
        p = words(processes[slot], 7, 'process')
        v = words(value['probe'], 24, 'worker probe')
        check(value['token'] == (inc << 8) | (slot + 1) and
              p[:3] == [value['token'], inc, value['root']] and p[2] > 0 and p[2] % 4096 == 0,
              'worker token/root/incarnation differs')
        check(value['argument'] == ARGS[cfg] and v[:3] == [1, ARGS[cfg], slot + 1] and
              v[19:22] == [ARGS[cfg], cfg, inc], 'worker argument/configuration/incarnation differs')
        check(v[7] == 1, 'worker AVX evidence missing')
        check(v[3] >= 4096 and v[4] > 0 and v[5] == 0 and
              33 <= v[22] <= 4096 and v[23] == 0x534d5046494c4553,
              'worker progress/syscalls/file evidence missing')
    return True


def launched(records, concurrent=True):
    check(isinstance(records, dict) and set(records) == set(ARGS), 'five launched workers required')
    tokens = []
    for cfg, record in records.items():
        token = record['token']
        check(uint(token) and 1 <= token & 255 <= 16 and 0 < token >> 8 <= 0x0fffffff
              and uint(record['generation']) and record['generation'] > 0
              and record['state'] in (1, 2) and record['status'] == 0, 'invalid launch receipt')
        tokens.append(token)
    check(len(set(tokens)) == 5, 'distinct full tokens required')
    if concurrent:
        check(len({token & 255 for token in tokens}) == 5, 'concurrent workers reuse a slot')
    return True


def negative_binding(catalog, records, start_sequence):
    launched(records, concurrent=False)
    check(uint(start_sequence) and uint(catalog['sequence']) and catalog['sequence'] > start_sequence,
          'fresh catalog sequence required')
    states = catalog['snapshots']
    check(len(states) == 32 and all(s['state'] == 2 for s in states[:7]), 'essential service failed')
    for cfg, argument in ARGS.items():
        state = states[cfg]
        check(state['argument'] == argument and state['generation'] == records[cfg]['generation'],
              'worker generation/argument differs')
    matches = []
    for event in catalog['events']:
        check(uint(event['sequence']) and start_sequence < event['sequence'] <= catalog['sequence'],
              'stale negative event')
        cfg = event['configuration']
        if cfg in ARGS and event['state'] == 4:
            check(event['process'] == records[cfg]['token'] and
                  event['generation'] == records[cfg]['generation'] and event['status'] == 6,
                  'negative event token/generation/status differs')
            check(states[cfg]['state'] == 4 and states[cfg]['status'] == 6,
                  'negative snapshot status differs')
            matches.append(event)
    check(matches, 'missing exact fresh worker #UD event')
    return matches


def service_counts(guest):
    # kernel/sched/user_bridge.dg: ACTIVE + 576 + slot * sizeof(Counts=56).
    address = guest.kval('sched.user_bridge', 'ACTIVE')
    check(uint(address) and address >= 0xffff800000000000 and address % 8 == 0,
          'invalid trusted bridge pointer')
    total = dict(calls=0, pci=0, clock=0, full=0, skipped=0)
    for slot in range(16):
        record = words(guest.readwords(address + 576 + slot * 56, 7), 7, 'service counts')
        calls, pci, clock, full, skipped, event, op = record
        check(pci <= calls and clock <= calls and full % 2 == skipped % 2 == 0 and
              full + skipped == 2 * calls, 'policy barrier counters disagree')
        for key, value in zip(total, record):
            total[key] += value
    return total


def retirement(before, after, slot):
    check(uint(slot) and slot < 16, 'invalid retired slot')
    old = words(before['domain'], 15, 'before domain')[8]
    domain = words(after['domain'], 15, 'after domain')
    check(domain[8] > old and domain[6] == 0, 'retirement epoch must advance and complete')
    token = words(before['processes'][slot], 7, 'old process')[0]
    retired = words(after['processes'][slot], 7, 'retired process')
    check(token > 0 and retired[1] >= before['processes'][slot][1] and not any(retired[:1] + retired[2:]),
          'retired process retains authority')
    check(len(after['cpus']) == 4 and len(after['seen']) == 4, 'four CPU retirement records required')
    for cpu, seen in zip(after['cpus'], after['seen']):
        words(cpu, 15, 'CPU')
        check(cpu[1] != token and not (cpu[4] == token and cpu[6] != 0) and not (cpu[0] == 6 and cpu[3] == slot) and
              cpu[7] == cpu[8] == domain[8], 'retirement owner/return/ack differs')
        check(len(seen) == 16 and words(seen[slot], 3, 'seen tag')[2] == 0,
              'retired translation remains seen')
    check(len(after['threads']) == 64 and words(after['threads'][slot], 8, 'retired thread')[0] == 0,
          'retired queue thread remains live')
    return True


def normal_fallback(record):
    check(record.get('normal_runtime') == 7 and record.get('test') is False and
          record.get('cpu_count') in (1, 2) and record.get('smp_steps') == 31 and
          record.get('user_domain_pointer') == 0 and record.get('services_smp_enabled') is False and
          record.get('legacy_busy') == 1 and record.get('essential_ready') == list(range(7)) and
          record.get('desktop_ready') is True and record.get('filesystem_read_and_sync') is True and
          record.get('actual_bsp_cpl') == 3 and record.get('ap_online') == record['cpu_count'] - 1,
          'normal fallback evidence incomplete or not explicit BSP-only topology')
    return True


def read_receipt(receipt):
    check(isinstance(receipt, dict) and set(receipt) == {'path', 'sha256'}, 'file receipt required')
    path = Path(receipt['path'])
    check(path.is_absolute() and path.is_file() and not path.is_symlink(), 'ordinary absolute receipt file required')
    raw = path.read_bytes()
    check(hashlib.sha256(raw).hexdigest() == receipt['sha256'], 'receipt artifact changed')
    return json.loads(raw)


def seal_negative_result(result):
    from tests.run_current_user_smp_qemu import identity
    check(result.get('execute') is True and result.get('negative_xstate') is True and
          result.get('runner_inputs_unchanged') is True and result.get('all_started_guests_stopped') is True and
          result.get('actual_qemu_boots') == 2 and result.get('same_disk_reboot_verified') is True,
          'two stopped source-bound same-disk negative boots required')
    source = identity(Path(result['esp']), True)
    check(result.get('source_identity') == source, 'source identity differs from completed receipt')
    boots = result.get('boots', [])
    receipts = result.get('boot_receipts', [])
    check(len(boots) == len(receipts) == 2 and len({r['path'] for r in receipts}) == 2,
          'two distinct boot receipts required')
    for record, receipt in zip(boots, receipts):
        check(read_receipt(receipt) == json.loads(json.dumps(record)), 'boot record not bound to receipt')
        avx(record['snapshot'])
        check(sum(m[2] for m in record['snapshot']['metrics'][1:]) > 0, 'actual AP user timer missing')
        check(uint(record['serial_marker_offset']) and uint(record['serial_start_offset']) and
              record['serial_marker_offset'] >= record['serial_start_offset'], 'fresh serial marker required')
        records = {int(k): v for k, v in record['launched_workers'].items()}
        negative_binding(record['catalog'], records, record['catalog_start_sequence'])
        check(record.get('actual_negative_busy_simd_assertion') is True and
              record.get('actual_fault_status_6') is True and record.get('actual_ap_user_timer') is True,
              'negative evidence incomplete')
    return dict(passed=True, evidence_consistent=True, guest_execution_verified=False,
                historical_acceptance=False, scope='supplied-current-receipts-only')


def seal_result(result):
    # Positive full-guest sealing is not implemented. Never elevate a marker or
    # a producer's passed flag into acceptance.
    raise ValueError('positive guest acceptance requires an independently reviewed complete capture contract')
