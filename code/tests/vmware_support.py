#!/usr/bin/env python3
"""Shared VMware image, UART observation and own-VM command helpers.

No build, VM launch or device access occurs at import. The storage entry point
provides ownership, dual-disk preparation, serial I/O and bounded cleanup.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import unittest
import uuid

HERE = Path(__file__).absolute().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from tools import make_usb_image as usb

DEFAULT_VMRUN = Path('D:/ProgramFiles/VMware/VMware Workstation/vmrun.exe')
REQUIRED = ('EFI/BOOT/BOOTX64.EFI', 'DONGOS.IMG', 'SERVICES.BIN')
IRQ_DIAG_BEGIN = b'DONGOS_IRQ_DIAGNOSTIC_V1_BEGIN'
IRQ_DIAG_END = b'DONGOS_IRQ_DIAGNOSTIC_V1_END'
IRQ_DIAG_WORDS = 56
IRQ_DIAG_GRACE = 2.0
IRQ_DIAG_FIELDS = ('version', 'stage', 'error_code', 'valid', 'apic_base', 'madt_lapic',
    'lapic_id_raw', 'lapic_version', 'cpu_count', 'cpu_match', 'ioapic_count', 'io_index',
    'madt_io_id', 'madt_io_address', 'gsi_base', 'io_id_raw', 'io_version', 'pins',
    'gsi_kind', 'prior_base', 'prior_pins', 'cpuid1_ecx', 'cpuid1_edx', 'reserved')
MARKERS = {
    'DONGOS_P1_START': 'UEFI loader entry',
    'DONGOS_P1_EBS_OK': 'UEFI ExitBootServices complete',
    'DONGOS_P1_KERNEL_HIGH_OK': 'kernel high-half entry',
    'DONGOS_P2_CPU_READY': 'CPU capabilities',
    'DONGOS_P2_MEMORY_READY': 'memory initialization',
    'DONGOS_P2_CACHE_READY': 'object cache initialization',
    'DONGOS_P3_ACPI_READY': 'ACPI initialization',
    'DONGOS_P3_RUNTIME_START': 'interrupt/runtime initialization started',
    'DONGOS_P3_IRQ_READY': 'interrupt platform ready',
    'DONGOS_P6_SMP_START': 'SMP initialization started',
    'DONGOS_P6_SMP_READY': 'SMP initialization ready',
    'DONGOS_P5_SERVICES_START': 'user service initialization started',
    'DONGOS_P5_ELF_LOADED': 'service ELF loading complete',
    'DONGOS_BLK_READY': 'VirtIO block service ready marker',
    'DONGOS_FS_READY': 'filesystem service ready marker',
    'DONGOS_INPUT_PS2_READY': 'PS/2 input service ready marker',
    'DONGOS_INPUT_VIRTIO_TABLET_READY': 'VirtIO tablet ready marker',
    'DONGOS_SHELL_READY': 'shell ready marker',
    'DONGOS_P7_AVX_CONTEXT_READY': 'AVX context ready marker',
    'DONGOS_P7_DESKTOP_READY': 'desktop ready marker only',
}


def check(condition, message):
    if not condition:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    with Path(path).open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write('\n')


def ordinary(path, *, directory=False):
    path = usb._reject_special(path)
    usb._no_links(path, directory=directory)
    return path


def within(path, parent):
    try:
        Path(path).relative_to(parent)
        return True
    except ValueError:
        return False


def identity(path):
    item = Path(path).stat()
    return [item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns]


def verify_build(esp):
    """Read-only normal runtime7 verification; deliberately imports no builder."""
    esp = ordinary(esp, directory=True)
    metadata_file = ordinary(esp.parent / 'build-inputs.json')
    metadata = json.loads(metadata_file.read_text(encoding='utf-8'))
    check(metadata.get('runtime_level') == 7 and metadata.get('test') is False
          and metadata.get('graphics_case') is None and metadata.get('smp_case') is None
          and metadata.get('source_unchanged') is True,
          'a completed normal runtime7 build is required')
    check(isinstance(metadata.get('source_sha256'), dict) and metadata['source_sha256']
          and isinstance(metadata.get('artifacts'), dict) and metadata['artifacts'],
          'incomplete completed-build fingerprints')
    for name, expected in metadata['source_sha256'].items():
        relative = Path(name)
        check(not relative.is_absolute() and '..' not in relative.parts,
              'source fingerprint escapes the repository')
        source = ordinary(ROOT / relative)
        check(sha(source) == expected, 'source changed since completed build: ' + name)
    artifacts = set()
    for name, expected in metadata['artifacts'].items():
        artifact = Path(name)
        artifact = ordinary(artifact if artifact.is_absolute() else esp.parent / artifact)
        check(within(artifact, esp.parent), 'artifact escapes the selected completed build')
        check(sha(artifact) == expected, 'completed build artifact changed: ' + str(artifact))
        artifacts.add(artifact)
    check(all(esp / name in artifacts for name in REQUIRED),
          'completed-build metadata does not authenticate all boot payloads')
    return metadata, sha(metadata_file)


def copy_verified_image(source, destination, expected_sha256):
    source = ordinary(source)
    ordinary(destination.parent, directory=True)
    before = identity(source)
    digest = hashlib.sha256()
    size = 0
    with source.open('rb') as src, destination.open('xb') as dst:
        check(identity(source) == before, 'source identity changed before copy')
        check([os.fstat(src.fileno()).st_dev, os.fstat(src.fileno()).st_ino,
               os.fstat(src.fileno()).st_size, os.fstat(src.fileno()).st_mtime_ns] == before,
              'source file changed while opening')
        for chunk in iter(lambda: src.read(1024 * 1024), b''):
            dst.write(chunk)
            digest.update(chunk)
            size += len(chunk)
        dst.flush()
        os.fsync(dst.fileno())
    check(identity(source) == before and size == before[2], 'source changed while copying')
    check(digest.hexdigest() == expected_sha256 and sha(destination) == expected_sha256,
          'source/copy hash differs from verified GPT image')
    check(not os.path.samestat(source.stat(), destination.stat())
          and destination.stat().st_nlink == 1, 'boot disk copy aliases another file')
    return dict(bytes=size, sha256=expected_sha256, source_identity=before,
                destination_identity=identity(destination), independently_allocated_file=True)


def descriptor(image_bytes, cid):
    check(type(image_bytes) is int and image_bytes > 0 and image_bytes % 512 == 0,
          'flat disk must have an exact positive sector count')
    check(re.fullmatch('[0-9a-f]{8}', cid) is not None, 'invalid descriptor CID')
    sectors = image_bytes // 512
    # The extent is an ordinary private copy, never a raw-device/partition map.
    return (f'# Disk DescriptorFile\nversion=1\nencoding="UTF-8"\nCID={cid}\n'
            'parentCID=ffffffff\ncreateType="monolithicFlat"\n\n'
            f'RW {sectors} FLAT "boot-flat.vmdk" 0\n\n'
            '# The Disk Data Base\n'
            'ddb.adapterType = "lsilogic"\n'
            f'ddb.geometry.cylinders = "{max(1, (sectors + 16064) // 16065)}"\n'
            'ddb.geometry.heads = "255"\nddb.geometry.sectors = "63"\n')


def configuration(run_id, controller):
    check(re.fullmatch('[0-9a-f]{16}', run_id) is not None, 'invalid run ID')
    check(controller in ('sata', 'nvme'), 'unsupported boot controller')
    fields = {
        '.encoding': 'UTF-8', 'config.version': '8', 'virtualHW.version': '18',
        'displayName': 'DongOS bootstrap ' + run_id, 'guestOS': 'other-64',
        'firmware': 'efi', 'uefi.secureBoot.enabled': 'FALSE',
        'numvcpus': '4', 'cpuid.coresPerSocket': '1', 'memsize': '2048',
        'nvram': 'dongos.nvram', 'extendedConfigFile': 'dongos.vmxf', 'workingDir': '.',
        'uuid.action': 'create', 'msg.autoAnswer': 'TRUE',
        'logging': 'TRUE', 'log.fileName': 'vmware.log', 'log.keepOld': '4',
        'bios.bootOrder': 'hdd', 'pciBridge0.present': 'TRUE',
        'pciBridge4.present': 'TRUE', 'pciBridge4.virtualDev': 'pcieRootPort',
        'pciBridge4.functions': '8',
        'sata0.present': 'TRUE' if controller == 'sata' else 'FALSE',
        'nvme0.present': 'TRUE' if controller == 'nvme' else 'FALSE',
        controller + '0:0.present': 'TRUE', controller + '0:0.fileName': 'disk.vmdk',
        controller + '0:0.deviceType': 'disk', controller + '0:0.mode': 'persistent',
        controller + '0:0.startConnected': 'TRUE',
        'scsi0.present': 'FALSE', 'ide0:0.present': 'FALSE', 'ide0:1.present': 'FALSE',
        'ide1:0.present': 'FALSE', 'ide1:1.present': 'FALSE',
        'serial0.present': 'TRUE', 'serial0.fileType': 'file',
        'serial0.fileName': 'serial.log', 'serial0.startConnected': 'TRUE',
        'serial0.yieldOnMsrRead': 'TRUE',
        'serial1.present': 'FALSE', 'parallel0.present': 'FALSE', 'floppy0.present': 'FALSE',
        'usb.present': 'FALSE', 'ehci.present': 'FALSE', 'usb_xhci.present': 'FALSE',
        'sound.present': 'FALSE', 'vmci0.present': 'FALSE', 'mks.enable3d': 'FALSE',
        'svga.present': 'TRUE', 'svga.vramSize': '67108864',
        'svga.maxWidth': '1920', 'svga.maxHeight': '1080',
        'sharedFolder.maxNum': '0', 'sharedFolder0.present': 'FALSE',
        'isolation.tools.hgfs.disable': 'TRUE', 'isolation.tools.hgfsServerSet.disable': 'TRUE',
        'isolation.tools.copy.disable': 'TRUE', 'isolation.tools.paste.disable': 'TRUE',
        'isolation.tools.dnd.disable': 'TRUE', 'tools.syncTime': 'FALSE',
        'tools.remindInstall': 'FALSE', 'tools.upgrade.policy': 'manual',
        'vhv.enable': 'FALSE',
    }
    for i in range(10):
        fields[f'ethernet{i}.present'] = 'FALSE'
    return ''.join(f'{key} = "{value}"\n' for key, value in fields.items())


def parse_running(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    check(lines, 'empty vmrun list response')
    matched = re.fullmatch(r'Total running VMs: (0|[1-9][0-9]*)', lines[0])
    check(matched is not None, 'unrecognized vmrun list response; refusing VM control')
    count = int(matched.group(1))
    check(len(lines) == count + 1, 'vmrun list count differs from returned paths')
    paths = []
    for line in lines[1:]:
        path = Path(line)
        check(path.is_absolute() and path.suffix.lower() == '.vmx', 'invalid running VM path')
        paths.append(os.path.normcase(os.path.abspath(path)))
    check(len(set(paths)) == count, 'duplicate paths in vmrun list response')
    return paths


def decode_irq_diagnostic(words):
    """Decode only a complete version-1 report, never infer missing fields."""
    check(len(words) == IRQ_DIAG_WORDS, 'diagnostic requires exactly 56 words')
    fields = dict(zip(IRQ_DIAG_FIELDS, words[:24]))
    check(fields['version'] == 1, 'unsupported diagnostic version')
    check(fields['stage'] in (1, 2, 3, 4), 'invalid failure stage')
    check(fields['error_code'] == 0x03050003, 'diagnostic error differs from InvalidTopology')
    check(fields['valid'] in {1: (1,), 2: (7,), 3: (7, 15), 4: (15,)}[fields['stage']], 'stage/valid mask inconsistent')
    check(1 <= fields['cpu_count'] <= 16 and 1 <= fields['ioapic_count'] <= 8, 'diagnostic topology count out of bounds')
    check(fields['reserved'] == 0 and fields['cpu_match'] == int(fields['stage'] >= 3), 'reserved/CPU-match schema differs')
    check(fields['gsi_kind'] in ((1, 2) if fields['stage'] == 4 else (0,)), 'invalid GSI failure subtype')
    if fields['stage'] >= 3:
        check(fields['io_index'] < fields['ioapic_count'], 'diagnostic IOAPIC index out of bounds')
    if fields['stage'] == 3 and fields['valid'] == 7:
        check(fields['io_id_raw'] == fields['io_version'] == fields['pins'] == 0,
              'static IOAPIC rejection must not claim unobserved MMIO data')
    cpus = [dict(index=i, apic_id=words[24 + 2*i], flags=words[25 + 2*i]) for i in range(16)]
    for cpu in cpus:
        if not fields['valid'] & 4 or cpu['index'] >= fields['cpu_count']:
            check(cpu['apic_id'] == cpu['flags'] == 0, 'unobserved CPU record contains data')
    return dict(fields=fields, cpu_records=cpus, cpu_records_observed=bool(fields['valid'] & 4),
                msr_observed=bool(fields['valid'] & 1), lapic_identity_observed=bool(fields['valid'] & 2),
                ioapic_identity_observed=bool(fields['valid'] & 8))


def irq_diagnostic_observations(raw):
    """Exact newline framing, bounded parsed prefixes; serial.log keeps all bytes."""
    blocks, active = [], None
    begin_count = end_count = orphan_words = 0
    offset = 0
    def finish(block, stop, ended):
        block['end_observed'] = ended
        block['raw_bytes'] = stop - block['byte_start']
        block['raw_sha256'] = hashlib.sha256(raw[block['byte_start']:stop]).hexdigest()
        if ended and block['word_line_count'] != IRQ_DIAG_WORDS:
            block['errors'].append('expected exactly 56 diagnostic word lines')
        if ended and not block['errors']:
            try:
                block['decoded'] = decode_irq_diagnostic(block['words'])
            except ValueError as exc:
                block['errors'].append(str(exc))
        block['status'] = 'invalid' if block['errors'] else 'complete' if ended else 'partial'
        block['complete'] = block['status'] == 'complete'
        blocks.append(block)
    pieces = raw.split(b'\n')
    for index, piece in enumerate(pieces):
        terminated = index + 1 < len(pieces)
        stop = offset + len(piece) + int(terminated)
        line = piece.removesuffix(b'\r')
        if terminated and line == IRQ_DIAG_BEGIN:
            begin_count += 1
            if active is not None:
                active['errors'].append('nested diagnostic BEGIN')
                finish(active, offset, False)
            active = dict(byte_start=offset, line_start=index+1, words=[], word_line_count=0, errors=[],
                          malformed_lines=[], parsed_words_truncated=False)
        elif terminated and line == IRQ_DIAG_END:
            end_count += 1
            if active is None:
                active = dict(byte_start=offset, line_start=index+1, words=[], word_line_count=0,
                              errors=['orphan diagnostic END'], malformed_lines=[], parsed_words_truncated=False)
            finish(active, stop, True)
            active = None
        elif active is not None and (terminated or piece):
            match = re.fullmatch(rb'irq_diag_word=0x([0-9a-fA-F]{16})', line) if terminated else None
            if match:
                active['word_line_count'] += 1
                if len(active['words']) < IRQ_DIAG_WORDS + 1:
                    active['words'].append(int(match[1], 16))
                else:
                    active['parsed_words_truncated'] = True
            elif not terminated:
                # A final incomplete hex/END line can still arrive on the next
                # read. Preserve its prefix without calling the block complete.
                active['trailing_partial_line_hex'] = piece[:256].hex()
            else:
                if len(active['malformed_lines']) < 8:
                    active['malformed_lines'].append(dict(line=index+1, prefix_hex=line[:256].hex()))
                if 'noncanonical line inside diagnostic block' not in active['errors']:
                    active['errors'].append('noncanonical line inside diagnostic block')
        elif line.startswith(b'irq_diag_word='):
            orphan_words += 1
        offset = stop
    if active is not None:
        finish(active, len(raw), False)
    ambiguous = begin_count > 1 or end_count > 1 or orphan_words > 0
    status = ('invalid' if ambiguous or any(block['status'] == 'invalid' for block in blocks)
              else blocks[0]['status'] if len(blocks) == 1 else 'absent')
    return dict(status=status, complete=status == 'complete' and len(blocks) == 1,
                begin_count=begin_count, end_count=end_count, end_marker_observed=end_count > 0,
                orphan_word_count=orphan_words, multiple_blocks=begin_count > 1 or len(blocks) > 1, blocks=blocks)


def serial_observations(raw):
    check(len(raw) <= 32 * 1024 * 1024, 'serial output exceeds observation bound')
    events = []
    values = {}
    failures = []
    for line in raw.splitlines():
        match = re.fullmatch(rb'(DONGOS_[A-Z0-9_]+)(?::[^\r\n]*)?', line)
        if match:
            name = match.group(1).decode('ascii')
            events.append(name)
            if 'PANIC' in name or name.endswith('_FAIL') or name.endswith('_FAILED'):
                failures.append(name)
        key = re.fullmatch(rb'([a-z][a-z0-9_]+)=0x([0-9a-fA-F]{16})', line)
        if key:
            name = key.group(1).decode('ascii')
            value = int(key.group(2), 16)
            values[name] = value
            if name in ('services_runtime_error', 'runtime_error', 'smp_runtime_error') and value:
                failures.append(name + '=0x' + key.group(2).decode('ascii'))
    known = [name for name in events if name in MARKERS]
    bootstrap = ('DONGOS_P1_START', 'DONGOS_P1_EBS_OK', 'DONGOS_P1_KERNEL_HIGH_OK')
    indices = [events.index(name) if name in events else -1 for name in bootstrap]
    valid_bootstrap = all(index >= 0 for index in indices) and indices == sorted(indices)
    observations = dict(markers=events, marker_counts={name: events.count(name) for name in sorted(set(events))},
        last_marker=events[-1] if events else None, last_known_marker=known[-1] if known else None,
        last_stage=MARKERS[known[-1]] if known else 'no recognized DongOS marker',
        bootstrap_markers_observed_in_order=valid_bootstrap,
        desktop_marker_observed='DONGOS_P7_DESKTOP_READY' in events,
        fatal_markers=failures, guest_failure_observed=bool(failures), hex_fields=values,
        irq_diagnostic=irq_diagnostic_observations(raw),
        serial_bytes=len(raw), serial_sha256=hashlib.sha256(raw).hexdigest(),
        last_serial_lines=[line.decode('utf-8', errors='replace') for line in raw.splitlines()[-30:]])
    if (values.get('services_last_error') == 0x05060001
            and values.get('services_last_pid') == 2):
        observations['failure_hint'] = ('block service pid 2 reported drivers.block_service.Setup; '
            'this driver searches modern VirtIO PCI 1af4:1042, not VMware SATA/NVMe')
    return observations


class Commands:
    """The only subprocess boundary; no shell and four narrowly allowed forms."""
    def __init__(self, state, vmrun, vmx, invoke=None):
        self.state, self.vmrun, self.vmx = state, vmrun, vmx
        self.invoke = subprocess.run if invoke is None else invoke
        self.records = []

    def allowed(self, args):
        return args in ([], ['-T', 'ws', 'list'],
            ['-T', 'ws', 'start', str(self.vmx), 'nogui'],
            ['-T', 'ws', 'stop', str(self.vmx), 'hard'])

    def run(self, args, timeout=45):
        check(self.allowed(args), 'refusing a command outside the own-VM allowlist')
        index = len(self.records)
        prefix = f'command-{index:03d}'
        command = [str(self.vmrun), *args]
        record = dict(index=index, argv=command, shell=False, cwd=str(self.state),
                      started_utc=utc(), timeout_seconds=timeout,
                      stdout=prefix + '.stdout', stderr=prefix + '.stderr')
        self.records.append(record)
        write_json(self.state / 'commands.json', self.records)
        output = error = b''
        try:
            finished = self.invoke(command, cwd=str(self.state), shell=False,
                capture_output=True, timeout=timeout,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            output, error = finished.stdout, finished.stderr
            record['returncode'] = finished.returncode
        except subprocess.TimeoutExpired as exc:
            output, error = exc.stdout or b'', exc.stderr or b''
            record.update(timed_out=True, error=str(exc))
            raise
        except BaseException as exc:
            record['error'] = f'{type(exc).__name__}: {exc}'
            raise
        finally:
            (self.state / record['stdout']).write_bytes(output)
            (self.state / record['stderr']).write_bytes(error)
            record['finished_utc'] = utc()
            write_json(self.state / 'commands.json', self.records)
        return record['returncode'], output.decode('utf-8', errors='replace'), error.decode('utf-8', errors='replace')

    def running(self):
        code, output, error = self.run(['-T', 'ws', 'list'])
        check(code == 0 and not error.strip(), 'vmrun list failed; refusing VM control')
        return parse_running(output)

