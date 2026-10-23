"""Source-bound, read-only GOP timing collection. VM execution is opt-in.

Every result produced here is virtual evidence, never physical WC throughput.
Replay recomputes the raw capture; it does not authenticate an external producer.
"""
from pathlib import Path
import argparse
import hashlib
import json
import statistics
import struct
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests import p2_wc_stage as stage
from tests import run_p2_alias_qemu as alias

check, sha, write = stage.check, stage.sha, stage.write
SAMPLE_FIELDS = ('version phase error_code root virtual physical bytes tsc_hz flags backup capacity pattern '
                 'restored guard_low guard_high cycles leaf_count leaves').split()


def sample(raw):
    check(type(raw) is bytes and len(raw) == 320, 'complete raw Sample ABI required')
    v = list(struct.unpack('<40Q', raw))
    check(v[:3] == [1, 2, 0] and v[12] == 7 and v[13:15] == [0x736176652d6c6f77, 0x7361766568696768],
          'actual measurement/restoration/backup guards incomplete')
    check(0 < v[6] <= 65536 and v[6] % 8 == v[4] % 8 == v[5] % 8 == 0
          and 1000 <= v[7] <= 16000000000 and v[11] == 0x9e3779b97f4a7c15
          and v[10] >= v[6] + 16 and all(v[15:22]), 'bounded identical pattern/real cycles required')
    count = ((v[4] & 4095) + v[6] + 4095) // 4096
    check(v[22] == count and count <= 17 and not any(v[23 + count:]), 'complete raw sampling-window leaves required')
    selector = 27 if v[8] == 9 else 131 if v[8] == 17 else None
    check(selector is not None, 'only UC/WC logical query flags admitted')
    for i, entry in enumerate(v[23:23 + count]):
        check(entry & ~(alias.MASK | 0x60) == (1 << 63) | selector
              and entry & alias.MASK == (v[5] & ~4095) + i * 4096,
              'raw sampled PTE is not the contiguous supervisor nonglobal UC/WC aperture')
    return dict(root=v[3], virtual=v[4], physical=v[5], bytes=v[6], tsc_hz=v[7], flags=v[8],
                backup=v[9], capacity=v[10], pattern=v[11], restored=v[12], cycles=v[15:22], leaves=v[23:23 + count])


def verify_capture(read, layout, symbols, boot, cpus):
    owner = alias.verify_bytes(read, layout, symbols, boot, cpus)
    r = owner['report']
    raw = alias.Raw(read, layout, symbols, boot)
    raw.base = r['root']
    raw.pool = read(raw.base, 128 * 4096, 'benchmark complete trusted kernel table pool')
    pair_bytes = raw.kernel('mm.wc_benchmark', 'REPORT', 'mm.wc_benchmark.Pair')
    check(len(pair_bytes) == 712, 'real Pair ABI changed')
    typ = raw.types['mm.wc_benchmark.Sample']
    check(typ['size'] == 320 and [f['name'] for f in typ['fields']] == SAMPLE_FIELDS, 'actual Sample fields differ')
    pair = raw.record('mm.wc_benchmark.Pair', pair_bytes)
    uc = sample(raw.field('mm.wc_benchmark.Pair', pair_bytes, 'uc'))
    wc = sample(raw.field('mm.wc_benchmark.Pair', pair_bytes, 'wc'))
    expected_owner = symbols[alias.control.storage.symbol('smp.alias_memory', 'REPORT')]
    check((pair['version'], pair['phase'], pair['alias_report'], pair['domain'], pair['count'])
          == (1, 2, expected_owner, r['domain'], cpus), 'benchmark does not bind the actual complete owner/domain')
    check(pair['uc_pat'] == r['pat_before'] and pair['wc_pat'] == r['pat_after']
          and (pair['uc_pat'] >> 24) & 255 == 0 and (pair['wc_pat'] >> 32) & 255 == 1,
          'sample PAT is not the actual owner pre/post hardware readback')
    check(pair['gop_base'] >= r['framebuffer'] and pair['gop_bytes'] > 0
          and pair['gop_base'] + pair['gop_bytes'] <= r['framebuffer'] + r['framebuffer_pages'] * 4096,
          'sampling window is outside the complete admitted GOP owner')
    check(len(boot) == 20 and list(boot[:3]) == [0x544f4f42474e4f44, 1, 160]
          and (pair['gop_base'], pair['gop_bytes']) == (boot[8], boot[9])
          and r['framebuffer'] == (boot[8] & ~4095)
          and r['framebuffer_pages'] == ((boot[8] & 4095) + boot[9] + 4095) // 4096,
          'benchmark/full owner aperture differs from actual raw GOP BootInfo')
    for name in ('root', 'virtual', 'physical', 'bytes', 'tsc_hz', 'backup', 'capacity', 'pattern', 'restored'):
        check(uc[name] == wc[name], 'UC/WC sampling conditions differ: ' + name)
    check(uc['root'] == r['root'] and uc['virtual'] == alias.HHDM + pair['gop_base']
          and uc['physical'] == pair['gop_base'] and uc['bytes'] <= pair['gop_bytes']
          and (uc['flags'], wc['flags']) == (9, 17), 'actual UC/WC query/root/window mismatch')
    backup = raw.virtual(wc['backup'], wc['bytes'] + 16, 'actual arena benchmark backup and guards')
    check(struct.unpack_from('<Q', backup)[0] == 0x736176652d6c6f77
          and struct.unpack_from('<Q', backup, len(backup) - 8)[0] == 0x7361766568696768,
          'actual retained backup guards differ')
    # Re-read every final window PTE from the complete owner pool. UC leaves
    # were captured before migration by the same source-bound checked function.
    for i, entry in enumerate(wc['leaves']):
        va = (wc['virtual'] & ~4095) + i * 4096
        table = raw.base
        for shift in (39, 30, 21, 12):
            check(raw.base <= table < raw.base + len(raw.pool) and table % 4096 == 0, 'final window walk escaped owner pool')
            actual = struct.unpack_from('<Q', raw.pool, table - raw.base + ((va >> shift) & 511) * 8)[0]
            check(actual & 1, 'final window missing')
            if shift == 12:
                check(actual & ~0x60 == entry & ~0x60, 'captured WC leaf differs from actual complete final PTE tree')
            else:
                check(not actual & 128, 'unexpected large sampling mapping')
                table = actual & alias.MASK
    return dict(owner=owner, pair=pair, uc=uc, wc=wc, backup_sha256=hashlib.sha256(backup).hexdigest(),
                median_uc_cycles=statistics.median(uc['cycles']), median_wc_cycles=statistics.median(wc['cycles']),
                collection_consistent=True, physical_wc_performance=False,
                cache_effect_scope='source-bound virtual GOP observations; no physical throughput claim')


def replay(path):
    path = Path(path).resolve()
    state = path.parent
    result = json.loads(path.read_text())
    check(result.get('environment') == 'qemu-virtual' and result.get('physical_wc_performance') is False
          and result.get('physical_gate_complete') is False,
          'this runner cannot certify physical performance')
    check({'esp', 'source_identity', 'source_before', 'source_after', 'disk_before_sha256', 'disk_after_sha256',
           'artifacts_sha256', 'physical_manifest_sha256', 'serial_sha256', 'read_range', 'boot', 'cpus',
           'observed', 'runtime_tools'} <= set(result), 'complete raw source/artifact/physical receipts required; booleans are insufficient')
    identity = stage.identity(Path(result['esp']))
    check(result['source_identity'] == identity and result['source_before'] == result['source_after']
          == stage.inputs() and result['disk_before_sha256'] == result['disk_after_sha256'], 'source/disk capture identity changed')
    check(sha(state / 'data.img') == result['disk_after_sha256'], 'actual observed disk bytes changed')
    check(result.get('no_guest_memory_or_register_writes') is True
          and set(result.get('runtime_tools', {})) == {'qemu', 'firmware_code', 'firmware_vars'}, 'complete read-only tool provenance required')
    for name, digest in result['artifacts_sha256'].items():
        check(sha(stage.ordinary(state / 'artifacts', name)) == digest, 'archived ABI/artifact changed')
    manifest_path = state / 'guest/physical-manifest.json'
    check(sha(manifest_path) == result['physical_manifest_sha256']
          and sha(state / 'guest/serial.log') == result['serial_sha256'], 'raw manifest/UART changed')
    manifest = json.loads(manifest_path.read_text())
    serial = (state / 'guest/serial.log').read_bytes()
    import re
    addresses = re.findall(rb'^memory_runtime_boot_info=0x([0-9a-f]{16})\r?$', serial, re.M)
    check(len(addresses) == 1, 'unique raw BootInfo UART identity required')
    physical = int(addresses[0], 16) - alias.HHDM
    boot_reads = [item for item in manifest if (item.get('physical'), item.get('length'), item.get('role')) == (physical, 160, 'BootInfo')]
    check(len(boot_reads) == 1, 'raw BootInfo observation receipt required')
    boot_path = stage.ordinary(state / 'guest', boot_reads[0]['file'])
    check(sha(boot_path) == boot_reads[0]['sha256']
          and list(struct.unpack('<20Q', boot_path.read_bytes())) == result['boot'], 'raw BootInfo differs from result')
    start, end = result['read_range']
    check(type(start) is int and type(end) is int and 0 <= start < end <= len(manifest), 'exact capture range missing')
    cursor = start
    def read(pa, n, role):
        nonlocal cursor
        check(cursor < end, 'capture exhausted')
        item = manifest[cursor]
        cursor += 1
        check((item['physical'], item['length'], item['role']) == (pa, n, role), 'ordered raw read identity differs')
        data_path = stage.ordinary(state / 'guest', item['file'])
        data = data_path.read_bytes()
        check(len(data) == n and sha(data_path) == item['sha256'], 'raw physical bytes changed')
        return data
    layout = json.loads((state / 'artifacts/dong_layout.json').read_text())
    symbols = alias.control.acpi.validation_symbols(state / 'artifacts/kernel.elf')
    observed = verify_capture(read, layout, symbols, result['boot'], result['cpus'])
    check(cursor == end and observed == result['observed'], 'raw recomputation differs from reported observations')
    guest = json.loads((state / 'guest/guest.json').read_text())
    check(guest.get('actual_qemu_executed') is True and guest.get('qemu_stopped') is True
          and guest.get('cleanup_completed') is True and guest.get('process_alive') is False
          and guest.get('qemu_returncode') == 0, 'owned guest cleanup is incomplete')
    command = guest.get('command', [])
    check(isinstance(command, list) and command and Path(command[0]).resolve()
          == Path(result['runtime_tools']['qemu']['path']).resolve()
          and '-accel' in command and command[command.index('-accel') + 1] in ('tcg', 'whpx', 'kvm')
          and '-smp' in command and command[command.index('-smp') + 1] == '4', 'actual virtual command/tool/topology missing')
    for t in result['runtime_tools'].values():
        check(sha(t['path']) == t['sha256'], 'QEMU/firmware input changed')
    return dict(collection_consistent=True, raw_recomputed=True, guest_execution_authenticated=False,
                physical_wc_performance=False, physical_gate_complete=False)


def execute(esp):
    """Only called by the explicit CLI --execute branch, never by host tests."""
    esp = Path(esp).resolve()
    identity = stage.identity(esp)
    state = ROOT / 'build/test/p2-wc-guest' / ('run-' + uuid.uuid4().hex[:12])
    state.mkdir(parents=True)
    art = state / 'artifacts'
    art.mkdir()
    for name in ('kernel.elf', 'dong_layout.json', 'build-inputs.json'):
        (art / name).write_bytes((esp.parent / name).read_bytes())
    disk = state / 'data.img'
    alias.create(disk, 64)
    qemu = alias.builder.find_tool('qemu-system-x86_64', 'QEMU')
    code, variables = alias.builder.find_firmware(qemu)
    tools = {name: dict(path=str(Path(p).resolve()), sha256=sha(p))
             for name, p in (('qemu', qemu), ('firmware_code', code), ('firmware_vars', variables))}
    result = dict(passed=False, environment='qemu-virtual', physical_wc_performance=False,
                  physical_gate_complete=False, esp=str(esp), source_identity=identity,
                  source_before=stage.inputs(), disk_before_sha256=sha(disk), runtime_tools=tools,
                  artifacts_sha256={p.name: sha(p) for p in art.iterdir()}, no_guest_memory_or_register_writes=True)
    guest = None
    try:
        guest = alias.control.ResetGuest(esp, disk, state / 'guest', control=True)
        guest.resume()
        guest.wait(b'DONGOS_P7_DESKTOP_READY', timeout=180)
        guest.pause()
        cpus = len(guest.qmp.request('query-cpus-fast'))
        check(cpus == 4, 'actual four-reader hardware topology required')
        (state / 'registers.txt').write_text(guest.qmp.request('human-monitor-command', {'command-line': 'info registers -a'}))
        start = len(guest.chunks)
        observed = verify_capture(guest.physical, guest.layout, guest.symbols, guest.boot, cpus)
        result.update(observed=observed, read_range=[start, len(guest.chunks)], boot=list(guest.boot), cpus=cpus)
        result['passed'] = True
    except BaseException as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if guest is not None:
            try:
                guest.close()
            except Exception as exc:
                result.update(passed=False, cleanup_error=str(exc))
        guest_receipt = state / 'guest/guest.json'
        result['all_started_guests_stopped'] = False
        if guest_receipt.is_file():
            receipt = json.loads(guest_receipt.read_text())
            result['all_started_guests_stopped'] = (receipt.get('qemu_stopped') is True
                                                   and receipt.get('process_alive') is False)
        if not result['all_started_guests_stopped']:
            result.update(passed=False, cleanup_error=result.get('cleanup_error', 'missing confirmed child-process termination'))
        result.update(source_after=stage.inputs(), disk_after_sha256=sha(disk))
        for name, rel in (('serial_sha256', 'guest/serial.log'), ('physical_manifest_sha256', 'guest/physical-manifest.json')):
            p = state / rel
            if p.is_file():
                result[name] = sha(p)
        try:
            stage.identity(esp)
            check(result['source_before'] == result['source_after'] and result['disk_before_sha256'] == result['disk_after_sha256'], 'source/disk changed during collection')
        except Exception as exc:
            result.update(passed=False, integrity_error=str(exc))
        write(state / 'result.json', result)
    if result['passed']:
        try:
            write(state / 'replay.json', replay(state / 'result.json'))
        except Exception as exc:
            result.update(passed=False, replay_error=str(exc))
            write(state / 'result.json', result)
    return state / 'result.json', result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reuse-esp', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--build', action='store_true')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--replay', type=Path)
    a = p.parse_args(argv)
    if a.replay:
        check(not a.execute and not a.build and not a.output and not a.reuse_esp, 'replay must stand alone')
        print(json.dumps(replay(a.replay)))
        return 0
    if not a.reuse_esp:
        check(a.output is not None and not a.execute, 'prepare requires --output; execution requires an already reviewed --reuse-esp')
        result = stage.build(a.output) if a.build else stage.prepare(a.output)
        print(json.dumps(dict(mode='build' if a.build else 'prepare', built=result['built'], guest_started=False, physical_wc_performance=False)))
        return 0
    check(not a.build and not a.output, 'reuse is separate from preparation/build')
    if not a.execute:
        identity = stage.identity(a.reuse_esp)
        print(json.dumps(dict(mode='identity-only', guest_started=False, physical_wc_performance=False, source_identity=identity)))
        return 0
    path, result = execute(a.reuse_esp)
    print(json.dumps(dict(result=str(path), passed=result['passed'], physical_wc_performance=False)))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
