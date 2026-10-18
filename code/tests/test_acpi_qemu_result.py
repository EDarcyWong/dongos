"""Independent ACPI ABI, serial projection and mocked host lifecycle gates.

No test in this module starts QEMU or compiles the kernel.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

from tests import acpi_protocol as protocol
from tests import run_acpi_qemu as runner
from tests import test_cache_qemu_result as prior


# These public contract orders and offsets are handwritten, not generated
# from the Dong manifest or the gate being tested.
REPORT_FIELDS = (
    'rsdp', 'xsdt', 'madt', 'fadt', 'hpet', 'mcfg', 'table_count', 'cpu_count',
    'ioapic_count', 'iso_count', 'nmi_count', 'mcfg_count', 'lapic_address', 'madt_flags',
    'fadt_flags', 'boot_arch', 'pm_timer_block', 'pm_timer_length', 'pm_timer_32bit',
    'hpet_gas_info', 'hpet_address', 'pm_timer_gas_info', 'pm_timer_address', 'steps')
SCALARS = (
    'rsdp', 'xsdt', 'madt', 'fadt', 'hpet', 'mcfg', 'rsdp_revision', 'table_count',
    'lapic_address', 'madt_flags', 'cpu_count', 'ioapic_count', 'iso_count', 'nmi_count',
    'mcfg_count', 'fadt_revision', 'fadt_flags', 'sci_interrupt', 'boot_arch', 'dsdt',
    'pm_timer_block', 'pm_timer_length', 'pm_timer_32bit', 'reset_value', 'hpet_id',
    'hpet_number', 'hpet_min_tick', 'hpet_page_protection')
INVENTORY_FIELDS = tuple((name, index * 8) for index, name in enumerate(SCALARS)) + (
    ('pm_timer_gas', 224), ('reset_gas', 264), ('hpet_gas', 304),
    ('cpus', 344), ('ioapics', 856), ('isos', 1048), ('nmis', 1560), ('mcfg_regions', 2200))
SYMBOLS = dict(prior.SYMBOLS)
BSS = SYMBOLS['__kernel_bss_start']
SYMBOLS.update(p3_acpi_report=BSS + 0x100, p3_acpi_report_end=BSS + 0x1c0,
               p3_acpi_inventory=BSS + 0x200,
               **{'memory_activation_entry.halt': prior.old.K + 0x1300})


def logical_inventory():
    value = dict(zip(SCALARS, range(1, 29)))
    value.update(pm_timer_gas=dict(address_space=1, bit_width=32, bit_offset=0, access_size=3, address=0x608),
                 reset_gas=dict(address_space=1, bit_width=8, bit_offset=0, access_size=1, address=0xcf9),
                 hpet_gas=dict(address_space=0, bit_width=0, bit_offset=0, access_size=0, address=0xfed00000),
                 cpus=[dict(kind=0, uid=5, apic_id=7, flags=1), dict(kind=9, uid=1000, apic_id=300, flags=2)],
                 ioapics=[dict(id=4, address=0xfec00000, gsi_base=24)],
                 isos=[dict(bus=0, source=9, gsi=33, flags=15)],
                 nmis=[dict(kind=3, processor=0, flags=5, lint=0, gsi=40),
                       dict(kind=10, processor=0xffffffff, flags=0, lint=1, gsi=0)],
                 mcfg_regions=[dict(base=0xe0000000, segment=2, start_bus=64, end_bus=127)])
    return value


def capture():
    # The complete old cache/hardening/memory fixture must still validate.
    block = [f'acpi_{name}=0x{index + 1:016x}'.encode() for index, name in enumerate(REPORT_FIELDS)]
    return prior.capture().replace(b'DONGOS_P2_MEMORY_READY\r\n',
                                   b'\r\n'.join([*block, b'DONGOS_P3_ACPI_READY', b'DONGOS_P2_MEMORY_READY']) + b'\r\n')


def layout_manifest():
    layout = prior.layout_manifest()
    layout['types'] += [
        dict(full_name='boot.acpi_startup.Report', size=192, alignment=8,
             fields=[dict(name=name, offset=index * 8) for index, name in enumerate(REPORT_FIELDS)]),
        dict(full_name='firmware.acpi.Inventory', size=2456, alignment=8,
             fields=[dict(name=name, offset=offset) for name, offset in INVENTORY_FIELDS])]
    for name, fields in (
            ('Gas', ('address_space', 'bit_width', 'bit_offset', 'access_size', 'address')),
            ('Cpu', ('kind', 'uid', 'apic_id', 'flags')),
            ('IoApic', ('id', 'address', 'gsi_base')),
            ('Iso', ('bus', 'source', 'gsi', 'flags')),
            ('Nmi', ('kind', 'processor', 'flags', 'lint', 'gsi')),
            ('McfgRegion', ('base', 'segment', 'start_bus', 'end_bus'))):
        layout['types'].append(dict(full_name='firmware.acpi.' + name, size=8 * len(fields), alignment=8,
                                    fields=[dict(name=field, offset=8 * i) for i, field in enumerate(fields)]))
    return layout


class AcpiGateTests(unittest.TestCase):
    def test_production_real_retry_prefix_is_bounded_without_altering_bytes(self):
        serial = capture().replace(b'DONGOS_P1_EBS_RETRY\r\n', b'')
        before = bytes(serial)
        values, base = runner.parse_report(serial, SYMBOLS, production=True)
        self.assertTrue(base['passed'])
        self.assertEqual(24, len(values))
        self.assertEqual(before, serial)
        with self.assertRaises(ValueError):
            runner.parse_report(serial, SYMBOLS)
        excessive = serial.replace(b'DONGOS_P1_EBS_OK\r\n', b'DONGOS_P1_EBS_RETRY\r\n' * 8 + b'DONGOS_P1_EBS_OK\r\n')
        with self.assertRaisesRegex(ValueError, 'bounded'):
            runner.parse_report(excessive, SYMBOLS, production=True)

    def test_independent_inventory_entire_2456_bytes_and_unused_slots(self):
        self.assertEqual(REPORT_FIELDS, protocol.FIELDS)
        self.assertEqual(SCALARS, runner.SCALARS)
        value = logical_inventory()
        expected = bytearray(2456)
        struct.pack_into('<28Q', expected, 0, *range(1, 29))
        struct.pack_into('<5Q', expected, 224, 1, 32, 0, 3, 0x608)
        struct.pack_into('<5Q', expected, 264, 1, 8, 0, 1, 0xcf9)
        struct.pack_into('<5Q', expected, 304, 0, 0, 0, 0, 0xfed00000)
        struct.pack_into('<8Q', expected, 344, 0, 5, 7, 1, 9, 1000, 300, 2)
        struct.pack_into('<3Q', expected, 856, 4, 0xfec00000, 24)
        struct.pack_into('<4Q', expected, 1048, 0, 9, 33, 15)
        struct.pack_into('<10Q', expected, 1560, 3, 0, 5, 0, 40, 10, 0xffffffff, 0, 1, 0)
        struct.pack_into('<4Q', expected, 2200, 0xe0000000, 2, 64, 127)
        self.assertEqual(bytes(expected), runner.inventory_bytes(value))
        self.assertEqual(2456, len(runner.inventory_bytes(value)))
        for name, count in (('cpus', 16), ('ioapics', 8), ('isos', 16), ('nmis', 16), ('mcfg_regions', 8)):
            changed = copy.deepcopy(value)
            changed[name] = [changed[name][0]] * (count + 1)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'bounded'):
                runner.inventory_bytes(changed)

    def test_independent_report_24_fields_and_packed_gas(self):
        expected = dict(zip(REPORT_FIELDS, (1, 2, 3, 4, 5, 6, 8, 11, 12, 13, 14, 15,
                                           9, 10, 17, 19, 21, 22, 23, 0, 0xfed00000,
                                           0x03002001, 0x608, 7)))
        actual = runner.expected_report(logical_inventory())
        self.assertEqual(expected, actual)
        self.assertEqual(192, len(struct.pack('<24Q', *(actual[name] for name in REPORT_FIELDS))))

    def test_serial_requires_each_field_once_and_fixed_order(self):
        values, base = runner.parse_report(capture(), SYMBOLS)
        self.assertEqual(dict(zip(REPORT_FIELDS, range(1, 25))), values)
        self.assertTrue(base['passed'])
        for index, name in enumerate(REPORT_FIELDS):
            line = f'acpi_{name}=0x{index + 1:016x}\r\n'.encode()
            for bad in (capture().replace(line, b''), capture().replace(line, line * 2)):
                with self.subTest(field=name), self.assertRaises(ValueError):
                    runner.parse_report(bad, SYMBOLS)
        first = b'acpi_rsdp=0x0000000000000001\r\n'
        second = b'acpi_xsdt=0x0000000000000002\r\n'
        with self.assertRaises(ValueError):
            runner.parse_report(capture().replace(first + second, second + first), SYMBOLS)

    def test_serial_ready_placement_malformed_unknown_and_truncation_reject(self):
        serial = capture()
        variants = [serial[:-1], serial.replace(b'DONGOS_P3_ACPI_READY\r\n', b''),
                    serial.replace(b'DONGOS_P3_ACPI_READY\r\n', b'DONGOS_P3_ACPI_READY\r\n' * 2),
                    serial.replace(b'acpi_rsdp=0x0000000000000001', b'acpi_rsdp=0x000000000000000A'),
                    serial.replace(b'acpi_rsdp=', b'acpi_unrecognized='),
                    serial.replace(b'DONGOS_P3_ACPI_READY\r\n', b'noise\r\nDONGOS_P3_ACPI_READY\r\n'),
                    serial.replace(b'DONGOS_P3_ACPI_READY\r\n', b'') + b'DONGOS_P3_ACPI_READY\r\n']
        for index, bad in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                runner.parse_report(bad, SYMBOLS)

    def test_prior_cache_semantics_remain_required(self):
        serial = capture().replace(b'cache_checksum=0x0000000000073600',
                                   b'cache_checksum=0x0000000000000000')
        self.assertNotEqual(capture(), serial)
        with self.assertRaisesRegex(ValueError, 'prior lifecycle'):
            runner.parse_report(serial, SYMBOLS)

    def validate(self, manifest=None, symbols=None):
        with tempfile.TemporaryDirectory() as directory:
            elf = Path(directory) / 'kernel.elf'
            elf.with_name('dong_layout.json').write_text(json.dumps(manifest or layout_manifest()))
            with mock.patch.object(runner.cache, 'read_validation_symbols', return_value=copy.deepcopy(symbols or SYMBOLS)):
                return runner.validation_symbols(elf)

    def test_elf_manifest_independent_report_and_inventory_offsets(self):
        self.assertEqual(SYMBOLS, self.validate())
        for type_name in ('boot.acpi_startup.Report', 'firmware.acpi.Inventory',
                          'firmware.acpi.Gas', 'firmware.acpi.Cpu', 'firmware.acpi.IoApic',
                          'firmware.acpi.Iso', 'firmware.acpi.Nmi', 'firmware.acpi.McfgRegion'):
            for field in ('size', 'alignment', 'field_order', 'field_offset'):
                manifest = layout_manifest()
                item = next(item for item in manifest['types'] if item['full_name'] == type_name)
                if field == 'size': item['size'] += 8
                elif field == 'alignment': item['alignment'] = 4
                elif field == 'field_order': item['fields'][0], item['fields'][1] = item['fields'][1], item['fields'][0]
                else: item['fields'][1]['offset'] += 1
                with self.subTest(type_name=type_name, field=field), self.assertRaises(ValueError):
                    self.validate(manifest)

    def test_elf_storage_outside_bss_wrong_span_and_unaligned_reject(self):
        for field in ('p3_acpi_report', 'p3_acpi_inventory'):
            for address in (BSS - 8, SYMBOLS['__kernel_bss_end'] - 1):
                bad = dict(SYMBOLS, **{field: address})
                if field == 'p3_acpi_report': bad['p3_acpi_report_end'] = address + 192
                with self.subTest(field=field, address=address), self.assertRaises(ValueError):
                    self.validate(symbols=bad)
        bad = dict(SYMBOLS, p3_acpi_report_end=SYMBOLS['p3_acpi_report_end'] + 8)
        with self.assertRaises(ValueError): self.validate(symbols=bad)
        for field in ('p3_acpi_report', 'p3_acpi_inventory'):
            bad = dict(SYMBOLS, **{field: SYMBOLS[field] + 1})
            if field == 'p3_acpi_report': bad['p3_acpi_report_end'] += 1
            with self.subTest(field=field), self.assertRaises(ValueError): self.validate(symbols=bad)

    def test_uefi_complete_range_accepts_adjacent_acpi_and_rejects_holes(self):
        def descriptor(kind, start, pages, attrs=0):
            return struct.pack('<IIQQQQ', kind, 0, start, 0, pages, attrs)
        raw = descriptor(9, 0x2000, 1) + descriptor(10, 0x1000, 1)
        entries = runner.read_map(raw, 40)
        self.assertTrue(runner.acpi_range(entries, 0x1ff0, 32))
        self.assertFalse(runner.acpi_range(entries, 0x2ff0, 32))
        self.assertFalse(runner.acpi_range([(0x1000, 0x3000, 9, 1 << 63)], 0x1ff0, 32))
        self.assertFalse(runner.acpi_range([(0x1000, 0x3000, 7, 0)], 0x1ff0, 32))
        with self.assertRaises(ValueError): runner.read_map(raw + raw[:40], 40)


class AcpiLifecycleTests(unittest.TestCase):
    def test_qmp_handshake_failure_closes_partial_connection(self):
        for greeting in (b'{}\n', b'not-json\n'):
            connection = mock.MagicMock()
            file = connection.makefile.return_value
            file.readline.return_value = greeting
            with self.subTest(greeting=greeting), mock.patch.object(runner.socket, 'create_connection', return_value=connection):
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    runner.QMP(1, mock.Mock())
                self.assertTrue(connection.close.called)
                self.assertTrue(file.close.called)

    def run_failed(self, directory, *, close_error=False, quit_error=False, handshake_error=False, fail_build=False):
        state = Path(directory) / runner.STATE_DIR / 'q35'
        state.mkdir(parents=True)
        (state / 'serial.log').write_bytes(b'OLD SUCCESS\n')
        (state / 'result.json').write_text('{"passed": true, "physical_inventory_verified": true}')
        process = mock.MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired('mock qemu', 10)
        process.returncode = -9
        qmp = mock.MagicMock()
        if close_error: qmp.close.side_effect = OSError('mock close failed')
        if quit_error:
            def request(command, arguments=None):
                if command == 'quit':
                    raise ValueError('mock closed QMP file')
                return {}
            qmp.request.side_effect = request
        def fake_build(**kwargs):
            if fail_build: raise RuntimeError('mock build failed')
            esp = kwargs['output'] / 'esp'
            esp.mkdir(parents=True)
            return esp
        with mock.patch.object(runner, 'ROOT', Path(directory)), \
             mock.patch.object(runner, 'build', side_effect=fake_build), \
             mock.patch.object(runner, 'validation_symbols', return_value=SYMBOLS), \
             mock.patch.object(runner, 'qemu_command', return_value=['mock-qemu', '-device', 'isa-debug-exit,iobase=0xf4', '-smp', '4']), \
             mock.patch.object(runner.subprocess, 'Popen', return_value=process) as spawn, \
             mock.patch.object(runner, 'QMP', side_effect=RuntimeError('mock handshake failed') if handshake_error else None, return_value=qmp), \
             mock.patch.object(runner.time, 'monotonic', side_effect=[0, 0, 100, 100]), \
             mock.patch.object(runner.time, 'sleep'), \
             mock.patch.object(runner.cache.memory, 'reap_process') as reap, redirect_stdout(io.StringIO()):
            result = runner.run_case('q35', 1)
        return result, json.loads((state / 'result.json').read_text()), (state / 'serial.log').read_bytes(), spawn, reap, qmp

    def test_timeout_is_failed_and_old_success_is_not_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            result, stored, serial, spawn, reap, qmp = self.run_failed(directory)
        self.assertFalse(result['passed'])
        self.assertFalse(stored['passed'])
        self.assertNotIn('physical_inventory_verified', stored)
        self.assertEqual(b'', serial)
        self.assertTrue(result['actual_qemu_executed'])
        self.assertTrue(any('TimeoutError' in error for error in result['errors']))
        spawn.assert_called_once()
        reap.assert_called_once()
        qmp.close.assert_called_once()

    def test_qmp_constructor_exception_still_reaps_the_guest(self):
        with tempfile.TemporaryDirectory() as directory:
            result, stored, _, _, reap, _ = self.run_failed(directory, handshake_error=True)
        self.assertFalse(result['passed'])
        self.assertFalse(stored['passed'])
        self.assertTrue(any('handshake' in error for error in result['errors']))
        reap.assert_called_once()

    def test_qmp_close_exception_must_not_skip_reap_or_result(self):
        with tempfile.TemporaryDirectory() as directory:
            result, stored, _, _, reap, _ = self.run_failed(directory, close_error=True)
        self.assertFalse(result['passed'])
        self.assertFalse(stored['passed'])
        reap.assert_called_once()

    def test_qmp_quit_closed_file_must_not_skip_reap_or_result(self):
        with tempfile.TemporaryDirectory() as directory:
            result, stored, _, _, reap, qmp = self.run_failed(directory, quit_error=True)
        self.assertFalse(result['passed'])
        self.assertFalse(stored['passed'])
        reap.assert_called_once()
        qmp.close.assert_called_once()

    def test_build_exception_clears_old_success_without_spawning(self):
        with tempfile.TemporaryDirectory() as directory:
            result, stored, serial, spawn, reap, _ = self.run_failed(directory, fail_build=True)
        self.assertFalse(result['passed'])
        self.assertFalse(stored['passed'])
        self.assertEqual(b'', serial)
        self.assertFalse(result['actual_qemu_executed'])
        spawn.assert_not_called()
        reap.assert_not_called()


if __name__ == '__main__':
    unittest.main()
