#!/usr/bin/env python3
"""Real runtime7 FXSAVE/SSE2 desktop and zoom/DPI pixel verification.

Only the caller schedules a guest, using --reuse-esp. No build, performance
threshold, AVX canary, clock patch or guest-memory write is performed here.
Intermediate frames use the existing immutable-code Z1 publication protocol;
these deliberately stopped functional observations cannot establish FPS.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct
import sys
import unittest
import uuid
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests import run_desktop_settings_qemu as settings
from tests.run_desktop_settings_qemu import Guest, ROOT, DARK, check, rect, sha
from tests.run_desktop_transition_qemu import TransitionGuest
from tests.run_runtime_qemu import SCHED
from tools.elf_symbols import read_elf_symbols
from tools.make_fat32_disk import create
from tools.service_bundle import inspect as inspect_bundle

storage = settings.storage
CPU = 'max,-avx,-avx2,-xsave,+smep,+smap,+umip'
ORIGINAL_CPU = 'max,+smep,+smap,+umip'
AVX_READY = b'DONGOS_P7_AVX_CONTEXT_READY'
SSE2_READY = b'DONGOS_P7_SSE2_CONTEXT_READY'
ROLES = ('shell', 'fs', 'block', 'compositor', 'input')


def sse2_command(command):
    """Change exactly one explicit CPU option; preserve the complete command."""
    result = list(command)
    check(result.count('-cpu') == 1, 'expected exactly one explicit Guest CPU option')
    index = result.index('-cpu') + 1
    check(index < len(result) and result[index] == ORIGINAL_CPU, 'unexpected original Guest CPU model')
    result[index] = CPU
    return result


def serial_safe(raw, completed=False):
    for forbidden in (b'PANIC', b'DONGOS_P1_KERNEL_FAIL', b'DONGOS_P7_AVX_FAILED',
                      AVX_READY, b'panic_vector=', b'Invalid Opcode'):
        check(forbidden not in raw, 'SSE2 guest fault or incompatible AVX success: ' + repr(forbidden))
    if completed:
        lines = raw.replace(b'\r\n', b'\n').split(b'\n')
        check(lines.count(SSE2_READY) == 1, 'one exact SSE2 context completion marker required')


def validate_xstate(report, mask):
    check(len(report) == 8 * len(SCHED), 'actual scheduler report byte size differs')
    fields = dict(zip(SCHED, struct.unpack('<' + 'Q' * len(SCHED), report)))
    check(fields['version'] == 1 and (fields['xstate_mode'], fields['xstate_bytes'], fields['xcr0']) == (1, 512, 0),
          'actual scheduler must use FXSAVE 512 bytes with no XCR0')
    check(fields['cpuid1_ecx'] & 0x1c000000 == 0, 'actual CPUID still advertises XSAVE/OSXSAVE/AVX')
    check(fields['cpuid1_edx'] & 0x07000000 == 0x07000000, 'actual CPUID lacks FXSR/SSE/SSE2')
    check(fields['cr4'] & (1 << 18) == 0 and fields['cr4'] & 0x600 == 0x600, 'actual scheduler CR4 not FXSAVE/SSE')
    check(fields['cr0'] & 12 == 0, 'actual scheduler uses EM/TS instead of eager state')
    check(mask == 3, 'actual scheduler retained a YMM save mask')
    return fields


def validate_registers(text):
    blocks = re.split(r'CPU#\d+\s*', text)[1:]
    check(len(blocks) == 4, 'four actual CPU register sets required')
    values = []
    for block in blocks:
        match = re.search(r'\bCR4=([0-9a-fA-F]+)', block)
        check(match is not None, 'actual CPU CR4 absent')
        cr4 = int(match[1], 16)
        check(cr4 & (1 << 18) == 0, 'actual CPU still enables OSXSAVE')
        check(cr4 & 0x600 == 0x600, 'actual CPU lost OSFXSR/OSXMMEXCPT')
        check(cr4 & ((1 << 20) | (1 << 21) | (1 << 11)) == ((1 << 20) | (1 << 21) | (1 << 11)),
              'actual CPU lost SMEP/SMAP/UMIP')
        values.append(cr4)
    return values


def validate_flags(flags):
    check(set(flags) == set(ROLES), 'exactly five actual service flags required')
    for role, fields in flags.items():
        check(set(fields) == {'svc_avx2', 'svc_gather_fast'} and all(value == 0 for value in fields.values()),
              'actual service retained an AVX/gather backend: ' + role)


class Sse2Guest(TransitionGuest):
    def __init__(self, *args, **kwargs):
        # Guest appends its CPU after builder.qemu_command. Adapt the completed
        # command at launch, restoring Popen immediately after construction.
        # The actual command is retained in Guest's existing evidence record.
        original = settings.subprocess.Popen
        def launch(command, *popen_args, **popen_kwargs):
            actual = sse2_command(command)
            self.evidence['command'] = actual
            self.evidence['required_cpu'] = CPU
            return original(actual, *popen_args, **popen_kwargs)
        with mock.patch.object(settings.subprocess, 'Popen', launch):
            super().__init__(*args, **kwargs)

    def wait(self, marker, timeout=90):
        actual = SSE2_READY if marker == AVX_READY else marker
        self.evidence.setdefault('required_waits', []).append(dict(requested=marker.decode('ascii'), actual=actual.decode('ascii')))
        # This is a real required wait, not a skipped AVX assertion. Timeout
        # and all original Guest failure checks propagate without alteration.
        result = Guest.wait(self, actual, timeout)
        serial_safe(bytes(self.raw))
        return result

    def verify_sse2(self, phase):
        self.pause()
        serial_safe(bytes(self.raw), completed=True)
        report = self.kernel(self.symbols['sched_report'], len(SCHED) * 8, 'actual FXSAVE scheduler report ' + phase)
        mask = struct.unpack('<Q', self.kernel(self.symbols['sched_xstate_mask'], 8, 'actual FXSAVE mask ' + phase))[0]
        fields = validate_xstate(report, mask)
        flags = {}
        for pid, role in enumerate(ROLES):
            symbols = read_elf_symbols(self.esp.parent / 'services' / role / 'program.elf')
            bias = struct.unpack_from('<Q', self.processes, pid * 1288 + 224)[0]
            flags[role] = {}
            for name in ('svc_avx2', 'svc_gather_fast'):
                check(name in symbols, 'service backend symbol missing: ' + role + '.' + name)
                address = bias + symbols[name]
                check(self.pte(self.roots[pid], address) & 0x800000000000001f == 0x8000000000000007,
                      'actual service flag lost USER/RW/NX/WB mapping')
                flags[role][name] = struct.unpack('<Q', self.user(pid, address, 8, role + ' actual ' + name + ' ' + phase))[0]
        validate_flags(flags)
        registers = self.qmp.request('human-monitor-command', {'command-line': 'info registers -a'})
        cr4 = validate_registers(registers)
        path = self.state / (phase + '-actual-registers.txt')
        path.write_text(registers, encoding='utf-8')
        item = dict(phase=phase, scheduler=fields, sched_xstate_mask=mask, actual_service_flags=flags,
                    actual_cpu_cr4=cr4, register_dump=path.name, register_dump_sha256=sha(path),
                    cpu_configuration=CPU, avx_canary_required=False, performance_acceptance=False)
        self.evidence.setdefault('fxsave_observations', []).append(item)
        storage.write_json(self.state / (phase + '-fxsave.json'), item)
        return item


def pin_build(esp):
    description_path = esp.parent / 'build-inputs.json'
    description = json.loads(description_path.read_text(encoding='utf-8'))
    check(description['runtime_level'] == 7 and description['source_unchanged'] and not description.get('derived')
          and not description['test'] and description['graphics_case'] is None and description['smp_case'] is None,
          'fresh normal complete runtime7 build required')
    inputs = {str(ROOT / name): sha(ROOT / name) for name in (
        'tests/run_desktop_sse2_qemu.py', 'tests/run_desktop_transition_qemu.py', 'tests/run_desktop_settings_qemu.py',
        'tests/run_runtime_qemu.py', 'tests/run_services_qemu.py', 'tests/run_acpi_qemu.py',
        'tests/run_desktop_qemu.py', 'tests/desktop_preferences_oracle.py',
        'tools/build.py', 'tools/make_fat32_disk.py', 'tools/elf_symbols.py', 'tools/service_bundle.py')}
    inputs[str(description_path)] = sha(description_path)
    for name, digest in description['source_sha256'].items():
        path = ROOT / name
        check(sha(path) == digest, 'build source identity differs: ' + name)
        inputs[str(path)] = digest
    for name, digest in description['artifacts'].items():
        path = Path(name) if Path(name).is_absolute() else esp.parent / name
        check(sha(path) == digest, 'build artifact changed: ' + str(path))
        inputs[str(path)] = digest
    bundle = (esp / 'SERVICES.BIN').read_bytes()
    entries = {entry['name']: entry for entry in inspect_bundle(bundle)['entries']}
    for role in ROLES:
        path = esp.parent / 'services' / role / 'program.elf'
        data = path.read_bytes()
        entry = entries[role]
        check(bundle[entry['offset']:entry['offset'] + entry['length']] == data and entry['sha256'] == sha(path),
              'external ELF differs from verified bundle: ' + role)
        inputs[str(path)] = sha(path)
    check(SSE2_READY in (esp.parent / 'services/compositor/program.elf').read_bytes(),
          'normal compositor has no mandatory SSE2 context marker; rebuild with the explicit fallback log')
    return inputs


class ModelTests(unittest.TestCase):
    def test_exact_cpu_replacement_keeps_other_arguments_and_rejects_ambiguity(self):
        original = ['qemu', '-gdb', 'tcp:127.0.0.1:1234', '-cpu', ORIGINAL_CPU, '-S', '-smp', '4']
        changed = sse2_command(original)
        self.assertEqual(CPU, changed[4])
        self.assertEqual(original[:4] + [ORIGINAL_CPU] + original[5:], original)
        self.assertEqual(original[:4] + [CPU] + original[5:], changed)
        for value in (['qemu'], ['qemu', '-cpu'], ['qemu', '-cpu', 'host'], original + ['-cpu', ORIGINAL_CPU]):
            with self.assertRaises(ValueError):
                sse2_command(value)

    def test_required_wait_substitution_is_exact_and_missing_marker_cannot_pass(self):
        guest = object.__new__(Sse2Guest)
        guest.evidence, guest.raw = {}, bytearray(SSE2_READY + b'\r\n')
        with mock.patch.object(Guest, 'wait', return_value=17) as wait:
            self.assertEqual(17, guest.wait(AVX_READY, 3))
            wait.assert_called_once_with(guest, SSE2_READY, 3)
        with mock.patch.object(Guest, 'wait', side_effect=TimeoutError('missing SSE2')) as wait:
            with self.assertRaises(TimeoutError):
                guest.wait(AVX_READY, 2)
            wait.assert_called_once_with(guest, SSE2_READY, 2)
        with mock.patch.object(Guest, 'wait') as wait:
            guest.wait(b'DONGOS_EDITOR_SAVED', 8)
            wait.assert_called_once_with(guest, b'DONGOS_EDITOR_SAVED', 8)

    def test_launch_adapter_changes_the_actual_process_command_and_restores_popen(self):
        original = ['qemu', '-cpu', ORIGINAL_CPU, '-S']
        def parent(guest, *args, **kwargs):
            guest.evidence = {}
            settings.subprocess.Popen(original, stdout='unchanged')
        with mock.patch.object(settings.subprocess, 'Popen') as launch:
            with mock.patch.object(TransitionGuest, '__init__', parent):
                guest = Sse2Guest('unused', 'unused', 'unused')
            launch.assert_called_once_with(['qemu', '-cpu', CPU, '-S'], stdout='unchanged')
            self.assertIs(settings.subprocess.Popen, launch)
            self.assertEqual(['qemu', '-cpu', CPU, '-S'], guest.evidence['command'])
        self.assertEqual(ORIGINAL_CPU, original[2])

    def test_serial_requires_exact_marker_and_rejects_faults_or_avx_success(self):
        serial_safe(SSE2_READY + b'\r\n', completed=True)
        for value in (b'', b'prefix' + SSE2_READY + b'\n', SSE2_READY + b'\n' + SSE2_READY + b'\n',
                      SSE2_READY + b'\nPANIC', SSE2_READY + b'\n' + AVX_READY, b'DONGOS_P7_AVX_FAILED'):
            with self.assertRaises(ValueError):
                serial_safe(value, completed=True)

    def report(self, **changes):
        fields = dict.fromkeys(SCHED, 0)
        fields.update(version=1, xstate_mode=1, xstate_bytes=512, cpuid1_edx=0x07000000, cr4=0x600)
        fields.update(changes)
        return struct.pack('<' + 'Q' * len(SCHED), *(fields[name] for name in SCHED))

    def test_actual_state_contract_rejects_xsave_avx_missing_sse_and_ymm_mask(self):
        self.assertEqual(1, validate_xstate(self.report(), 3)['xstate_mode'])
        for changes in ({'xstate_mode': 2}, {'xstate_bytes': 832}, {'xcr0': 7}, {'cpuid1_ecx': 1 << 26},
                        {'cpuid1_ecx': 1 << 27}, {'cpuid1_ecx': 1 << 28}, {'cpuid1_edx': 0x03000000},
                        {'cr4': 0x40600}, {'cr4': 0}, {'cr0': 4}, {'cr0': 8}):
            with self.assertRaises(ValueError):
                validate_xstate(self.report(**changes), 3)
        for raw, mask in ((self.report()[:-1], 3), (self.report(), 7), (self.report(), 0)):
            with self.assertRaises(ValueError):
                validate_xstate(raw, mask)

    def test_actual_five_service_flags_and_all_cpu_cr4_are_checked(self):
        flags = {role: dict(svc_avx2=0, svc_gather_fast=0) for role in ROLES}
        validate_flags(flags)
        for role in ROLES:
            for name in flags[role]:
                flags[role][name] = 1
                with self.assertRaises(ValueError):
                    validate_flags(flags)
                flags[role][name] = 0
        good = 0x600 | (1 << 20) | (1 << 21) | (1 << 11)
        text = ''.join(f'CPU#{i}\nCR4={good:x}\n' for i in range(4))
        self.assertEqual([good] * 4, validate_registers(text))
        for bad in (text.replace(f'CR4={good:x}', 'CR4=0', 1), text + 'CPU#4\nCR4=0\n',
                    text.replace(f'CR4={good:x}', f'CR4={good | (1 << 18):x}', 1)):
            with self.assertRaises(ValueError):
                validate_registers(bad)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp', type=Path)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ModelTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if args.reuse_esp is None:
        parser.error('--reuse-esp is required; this runner never builds')
    esp = args.reuse_esp.resolve()
    state = ROOT / 'build/test/p7-sse2/qemu' / ('run-' + uuid.uuid4().hex[:12])
    state.mkdir(parents=True)
    inputs, guest = {}, None
    result = dict(passed=False, actual_qemu_executed=False, cpu=CPU, runner_sha256=sha(__file__),
                  actual_qemu_boots=0, performance_acceptance=False, animation_fps=None, avx_canary_required=False)
    def unchanged():
        try:
            return bool(inputs) and all(sha(path) == digest for path, digest in inputs.items())
        except OSError:
            return False
    try:
        inputs = pin_build(esp)
        result['pinned_inputs'] = inputs
        disk = state / 'data.img'
        create(disk, 64)
        guest = Sse2Guest(esp, disk, state / 'interactive')
        result.update(actual_qemu_executed=True, actual_qemu_boots=1, guest_state=str(guest.state))
        guest.verify_sse2('initial')
        guest.verify_state('default100', 256, DARK, 0)
        guest.verify_scene('initial-pixels')
        guest.focus(2)
        editor = rect(guest.windows(), 2)
        guest.move(editor[2] - 16, editor[1] + 12)
        guest.button_async(True)
        hidden = guest.capture_middle('sse2-hide-middle', 2, fade=True, show=False)
        check(hidden['actual_alpha_changed_pixels'] >= 8 and hidden['actual_scaled_texture_pixels'] >= 8,
              'SSE2 hide lacks actual intermediate alpha and scaled pixels')
        guest.button(False)
        guest.settle_motion()
        check(guest.progress()['PRESENTED_ALPHA'][2] == 0, 'hidden endpoint retained opacity')
        guest.verify_scene('sse2-hidden-endpoint')
        guest.move(435, guest.descriptor()[2] - 40)
        guest.button_async(True)
        shown = guest.capture_middle('sse2-show-middle', 2, fade=True, show=True)
        check(shown['actual_alpha_changed_pixels'] >= 8 and shown['actual_scaled_texture_pixels'] >= 8,
              'SSE2 show lacks actual intermediate alpha and scaled pixels')
        guest.button(False)
        guest.settle_motion()
        guest.verify_scene('sse2-shown-endpoint')
        guest.focus(3)
        owner = guest.windows()
        frames = guest.kval('user.memory', 'FRAME_COUNT')
        metadata = guest.kernel(guest.ksym('user.memory', 'META'), 5 * 32, 'SSE2 initial page metadata')
        for scale in (320, 384, 448, 512, 256):
            revision = guest.value('STYLE_REVISION')
            guest.key_async('equal')
            middle = guest.capture_middle(f'sse2-dpi{scale}-middle', 3, revision=revision + 1)
            check(middle['scale_q8'] == scale and middle['actual_scaled_texture_pixels'] >= 8,
                  'SSE2 DPI has no genuine intermediate scaled GOP pixels')
            guest.settle_motion()
            guest.verify_state(f'sse2-dpi{scale}-endpoint', scale, DARK, 0)
            guest.verify_scene(f'sse2-dpi{scale}-exact')
            current = guest.windows()
            check(owner[2304:2448] == current[2304:2448], 'SSE2 DPI changed focus/order/count')
            for index in range(4):
                check(owner[index * 144:index * 144 + 40] == current[index * 144:index * 144 + 40]
                      and owner[index * 144 + 136:index * 144 + 144] == current[index * 144 + 136:index * 144 + 144],
                      'SSE2 DPI changed window ownership/visibility')
            guest.verify_sse2('dpi' + str(scale))
        check(guest.kval('user.memory', 'FRAME_COUNT') == frames, 'SSE2 DPI allocated physical frames')
        check(guest.kernel(guest.ksym('user.memory', 'META'), 5 * 32, 'SSE2 final page metadata') == metadata,
              'SSE2 DPI allocated private page tables')
        guest.verify_elf()
        guest.verify_sse2('final')
        guest.close()
        guest = None
        result.update(passed=True, real_fxsave_512_mask3_verified=True, actual_all_five_service_avx_flags_zero=True,
                      five_dpi_scales_verified=True, actual_hide_show_intermediate_geometry_alpha=True,
                      immutable_code_and_z1_publication_verified=True, independent_gop_pixel_oracle=True,
                      no_guest_clock_code_or_memory_write_operations=True)
    except Exception as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if guest:
            result['actual_qemu_executed'] = guest.evidence.get('actual_qemu_executed', False)
            try:
                guest.close()
            except Exception as exc:
                result['cleanup_error'] = f'{type(exc).__name__}: {exc}'
                result['passed'] = False
        # Construction can fail after launching QEMU, before Python assigns
        # guest. Preserve the actual launch evidence written by Guest.close.
        guest_record = state / 'interactive/guest.json'
        if guest_record.exists():
            record = json.loads(guest_record.read_text(encoding='utf-8'))
            result['actual_qemu_executed'] = bool(record.get('actual_qemu_executed'))
            result['actual_qemu_boots'] = int(result['actual_qemu_executed'])
        result['source_unchanged'] = unchanged()
        if not result['source_unchanged']:
            result.update(passed=False, source_identity_failure=True)
        storage.write_json(state / 'result.json', result)
    print('P7 SSE2/FXSAVE', 'PASS' if result['passed'] else 'FAIL', state, result.get('error', ''), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
