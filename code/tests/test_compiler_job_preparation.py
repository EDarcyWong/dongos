"""Fresh host compiler/profile/FAT preparation; this gate never boots a guest."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time
import traceback
import unittest
from unittest.mock import patch
import uuid

from tools import build as builder
from tools import compiler_job, user_services
from tests import run_compiler_job_qemu as runner

ROOT = builder.ROOT
MIB = 1024 * 1024


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def elf_layout(image, *, compiler=True):
    """Decode actual PT_LOAD mappings; enforce the compiler's narrower API."""
    if len(image) < 64 or image[:7] != b'\x7fELF\x02\x01\x01':
        raise ValueError('compiler image is not little-endian ELF64')
    kind, machine, version, entry, phoff, _, _, size, stride, count, *_ = struct.unpack_from(
        '<HHIQQQIHHHHHH', image, 16)
    if (machine, version, size, stride) != (62, 1, 64, 56) or kind not in (2, 3):
        raise ValueError('compiler ELF header differs')
    if compiler and kind != 2:
        raise ValueError('compiler ELF must be static ET_EXEC')
    if count == 0 or phoff + count * stride > len(image):
        raise ValueError('compiler ELF program table is truncated')
    rows = []
    for index in range(count):
        typ, flags, offset, virtual, _, filesz, memsz, alignment = struct.unpack_from(
            '<IIQQQQQQ', image, phoff + index * stride)
        if typ != 1:
            continue
        if (flags not in (5, 6) or not memsz or filesz > memsz
                or offset + filesz > len(image) or alignment != 4096):
            raise ValueError('ELF load-segment bounds differ')
        if compiler and (filesz != memsz or virtual < 0x400000 or virtual + memsz > 0x800000):
            raise ValueError('compiler ELF escaped the kernel static-image contract')
        start, end = virtual & ~4095, (virtual + memsz + 4095) & ~4095
        if any(start < row['map_end'] and row['map_start'] < end for row in rows):
            raise ValueError('compiler ELF load pages overlap')
        rows.append(dict(flags=flags, file_offset=offset, virtual_address=virtual,
                         file_bytes=filesz, memory_bytes=memsz, map_start=start,
                         map_end=end, pages=(end - start) // 4096))
    if not rows or (compiler and len(rows) > 2) or not any(
            row['flags'] == 5 and row['virtual_address'] <= entry
            < row['virtual_address'] + row['memory_bytes'] for row in rows):
        raise ValueError('compiler ELF has no bounded executable entry')
    return dict(elf_type=kind, entry=entry, segments=rows, pages=sum(row['pages'] for row in rows))


def empty_stage_entry(path, raw_name):
    """Check the actual empty FAT entry; p5.check_disk requires a data chain."""
    with path.open('rb') as disk:
        boot = disk.read(512)
        bps, reserved = struct.unpack_from('<H', boot, 11)[0], struct.unpack_from('<H', boot, 14)[0]
        spc, fats = boot[13], boot[16]
        sectors, root = struct.unpack_from('<I', boot, 36)[0], struct.unpack_from('<I', boot, 44)[0]
        if (bps, spc, fats, boot[510:512]) != (512, 1, 2, b'\x55\xaa'):
            raise ValueError('empty-stage FAT geometry differs')
        disk.seek(reserved * 512)
        fat = disk.read(sectors * 512)
        if len(fat) != sectors * 512 or disk.read(len(fat)) != fat:
            raise ValueError('empty-stage FAT mirrors differ')
        directory, seen, cluster = bytearray(), set(), root
        while cluster < 0xffffff8:
            if cluster < 2 or cluster in seen or cluster * 4 + 4 > len(fat):
                raise ValueError('empty-stage root chain is invalid')
            seen.add(cluster)
            disk.seek((reserved + fats * sectors + cluster - 2) * 512)
            part = disk.read(512)
            if len(part) != 512:
                raise ValueError('empty-stage root is truncated')
            directory.extend(part)
            cluster = struct.unpack_from('<I', fat, cluster * 4)[0] & 0xfffffff
        matches = []
        for offset in range(0, len(directory), 32):
            record = directory[offset:offset + 32]
            if record[0] == 0:
                break
            if record[:11] == raw_name:
                matches.append(record)
        if len(matches) != 1:
            raise ValueError('empty-stage directory entry missing or duplicated')
        record = matches[0]
        first = (struct.unpack_from('<H', record, 20)[0] << 16) | struct.unpack_from('<H', record, 26)[0]
        size = struct.unpack_from('<I', record, 28)[0]
        if record[11] != 0x20 or first != 0 or size != 0:
            raise ValueError('stage file is not an empty unallocated regular file')
        return dict(raw_name=raw_name.decode(), size=size, first_cluster=first,
                    directory_entry_hex=record.hex(), verified=True)


class CompilerJobPreparationTests(unittest.TestCase):
    def test_fresh_fixedpoint_profile_binding_and_seed_disk(self):
        work = ROOT / 'build/test/g6-preparation' / ('run-' + uuid.uuid4().hex[:12])
        work.mkdir(parents=True)
        commands = work / 'commands'
        commands.mkdir()
        started = time.monotonic()
        tracked = [Path(__file__), Path(compiler_job.__file__), Path(builder.__file__),
                   Path(user_services.__file__), Path(runner.__file__), Path(runner.p5.__file__),
                   ROOT / 'kernel/user/compiler_job.dg', ROOT / 'kernel/user/compiler_stack.dg',
                   ROOT / 'services/compiler/controller.dg']
        before = {str(path): sha(path) for path in tracked}
        result = dict(passed=False, guest_executed=False, actual_qemu_executed=False,
                      source_before=before, commands=[], negative_controls=[],
                      dynamic_managed_frames_verified=False)
        groups = {}

        def execute(command):
            # Execute the actual command with the same cwd/error contract as
            # build.execute, retaining output even when a tool fails.
            index = len(result['commands'])
            log = commands / f'{index:04d}.log'
            row = dict(command=list(map(str, command)), cwd=str(ROOT), log=str(log))
            result['commands'].append(row)
            print('+ ' + subprocess.list2cmdline(row['command']), flush=True)
            with log.open('wb') as output:
                process = subprocess.run(row['command'], cwd=ROOT, stdout=output,
                                         stderr=subprocess.STDOUT)
            row['returncode'] = process.returncode
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, row['command'])

        def reject_changed(path, expected, esp, fixture):
            original = path.read_bytes()
            self.assertTrue(original, str(path))
            changed = bytearray(original)
            changed[-1] ^= 1
            row = dict(path=str(path), before_sha256=sha(path), restored=False,
                       expected_rejection=expected)
            result['negative_controls'].append(row)
            try:
                path.write_bytes(changed)
                row['mutated_sha256'] = sha(path)
                with self.assertRaisesRegex(ValueError, expected) as caught:
                    runner.load_inputs(ROOT, esp, fixture)
                row.update(rejected=True, reason=str(caught.exception))
            finally:
                path.write_bytes(original)
                row['restored_sha256'] = sha(path)
                row['restored'] = path.read_bytes() == original
                self.assertTrue(row['restored'], 'negative control did not restore original bytes')
            runner.verify_frozen(groups)

        with patch.object(runner, 'boot', side_effect=AssertionError('host preparation must not boot')) as boot:
            try:
                fixture = work / 'fixture'
                with (work / 'fixture-console.log').open('w', encoding='utf-8') as output:
                    with redirect_stdout(output), redirect_stderr(output):
                        receipt = compiler_job.exercise(fixture, 'release', ROOT)
                result['fixture_receipt'] = str(fixture / 'receipt.json')
                self.assertTrue(receipt['source_stable'] and receipt['exact_fixedpoint'])
                self.assertTrue(receipt['host_only'])
                self.assertFalse(receipt['guest_executed'])
                self.assertEqual((receipt['arena_bytes'], receipt['stack_bytes']), (56 * MIB, 65536))

                with (work / 'build-console.log').open('w', encoding='utf-8') as output:
                    with redirect_stdout(output), redirect_stderr(output):
                        with patch.object(builder, 'execute', side_effect=execute), \
                                patch.object(user_services, 'execute', side_effect=execute):
                            esp = builder.build(stage='p1', runtime_level=5, compiler_job=True,
                                                test=False, output=work / 'kernel')
                blob, image, sources, groups = runner.load_inputs(ROOT, esp, fixture)
                runner.verify_frozen(groups)
                self.assertEqual(image, (fixture / 'stage2.elf').read_bytes())
                self.assertEqual(hashlib.sha256(image).hexdigest(), receipt['elf_sha256'])
                self.assertEqual(hashlib.sha256(blob).hexdigest(), receipt['blob_sha256'])
                count, entry = struct.unpack_from('<2Q', blob)
                self.assertEqual(count, len(receipt['sources']))
                self.assertTrue(0 < count <= 64 and entry < count)
                self.assertLessEqual(len(blob), 512 * 1024)
                self.assertLessEqual(len(image), 2 * MIB)
                layout = elf_layout(image)
                services = {}
                for name in ('shell', 'fs', 'block'):
                    path = esp.parent / 'services' / name / 'program.elf'
                    content = path.read_bytes()
                    services[name] = dict(path=str(path), bytes=len(content), sha256=sha(path),
                                          **elf_layout(content, compiler=False))
                result.update(binding_verified=True, source_groups={name: {str(p): value for p, value in rows.items()}
                              for name, rows in groups.items()}, build_sources=sources,
                              compiler_elf=dict(path=str(fixture / 'stage1.elf'), bytes=len(image),
                                                sha256=sha(fixture / 'stage1.elf'), **layout),
                              service_elf=services,
                              source_blob=dict(bytes=len(blob), modules=count, entry=entry,
                                               sha256=sha(fixture / 'sources.bin')),
                              budgets=dict(elf_limit=2 * MIB, elf_remaining=2 * MIB - len(image),
                                           source_limit=512 * 1024, source_remaining=512 * 1024 - len(blob),
                                           arena_bytes=56 * MIB, arena_pages=14336,
                                           stack_bytes=65536, stack_pages=16, metadata_pages=1,
                                           managed_user_frame_limit=16384,
                                           dynamic_peak_not_established=True))

                reject_changed(fixture / 'stage1.elf', 'host fixture changed or fixed point unproven', esp, fixture)
                reject_changed(esp / 'SERVICES.BIN', 'artifact differs from build manifest', esp, fixture)
                runner.load_inputs(ROOT, esp, fixture)
                runner.verify_frozen(groups)

                disk = work / 'disk.img'
                runner.seed_disk(disk, blob, image)
                disk_rows = [runner.p5.check_disk(disk, raw_name=name, payload=data)
                             for name, data in ((b'SOURCES BIN', blob), (b'SEED    ELF', image))]
                disk_rows += [empty_stage_entry(disk, name) for name in (b'STAGE1  ELF', b'STAGE2  ELF')]
                result['seed_disk'] = dict(path=str(disk), bytes=disk.stat().st_size,
                                           sha256=sha(disk), files=disk_rows)
                runner.verify_frozen(groups)
                boot.assert_not_called()
                result['passed'] = True
            except BaseException as error:
                result['failure'] = dict(type=type(error).__name__, message=str(error),
                                         traceback=traceback.format_exc())
                raise
            finally:
                result['elapsed_seconds'] = time.monotonic() - started
                result['source_after'] = {str(path): sha(path) for path in tracked}
                result['source_stable'] = result['source_after'] == before
                result['boot_calls'] = boot.call_count
                if not result['source_stable'] or boot.call_count:
                    result['passed'] = False
                    result['finalization_failure'] = 'source changed or forbidden boot was called'
                result['artifact_sha256'] = {p.relative_to(work).as_posix(): sha(p)
                                            for p in work.rglob('*') if p.is_file()}
                (work / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
                print('G6_PREPARATION_EVIDENCE', work, flush=True)
                boot.assert_not_called()
                self.assertTrue(result['source_stable'], 'host preparation inputs changed')


if __name__ == '__main__':
    unittest.main()
