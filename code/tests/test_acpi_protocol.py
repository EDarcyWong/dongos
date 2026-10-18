"""Older P2 gates may project only the exact optional normal ACPI stage."""
import unittest
from tests import acpi_protocol as protocol
from tests import test_cache_qemu_result as old


def block():
    return [*(f'acpi_{name}=0x{index:016x}'.encode() for index, name in enumerate(protocol.FIELDS)), protocol.READY]


class AcpiProtocolTests(unittest.TestCase):
    def test_absent_and_exact_normal_stage(self):
        original = [b'prefix', protocol.CACHE_READY, protocol.MEMORY_READY, b'DONGOS_P1_PASS']
        self.assertEqual((original, []), protocol.project(original))
        self.assertEqual((original, []), protocol.project(original[:2] + block() + original[2:]))

    def test_no_unknown_duplicate_missing_misplaced_or_partial_fields(self):
        original = [protocol.CACHE_READY, *block(), protocol.MEMORY_READY]
        variants = [original[1:], original[:-1], [b'prefix', *block(), protocol.CACHE_READY, protocol.MEMORY_READY]]
        for index in range(1, 1 + len(protocol.FIELDS)):
            variants.extend((original[:index] + original[index + 1:],
                             original[:index] + [original[index]] + original[index:],
                             original[:index] + [original[index] + b' '] + original[index + 1:]))
        variants.extend(([protocol.CACHE_READY, *reversed(block()), protocol.MEMORY_READY],
                         [protocol.CACHE_READY, *block(), b'acpi_fake=0x0000000000000000', protocol.MEMORY_READY],
                         [protocol.CACHE_READY, *block()[:-1], b'X' + protocol.READY, protocol.MEMORY_READY]))
        for lines in variants:
            with self.subTest(lines=lines):
                self.assertTrue(protocol.project(lines)[1])

    def test_cache_gate_retains_all_old_semantics_after_projection(self):
        serial = old.capture()
        addition = b'\r\n'.join(block()) + b'\r\n'
        serial = serial.replace(protocol.MEMORY_READY + b'\r\n', addition + protocol.MEMORY_READY + b'\r\n')
        self.assertTrue(old.runner.parse_result(serial, symbols=old.SYMBOLS)['passed'])
        self.assertFalse(old.runner.parse_result(serial.replace(b'acpi_rsdp=', b'acpi_bogus='), symbols=old.SYMBOLS)['passed'])
        broken = old.old.replace_diagnostic(serial, 'cache', 'free_after', 0)
        self.assertFalse(old.runner.parse_result(broken, symbols=old.SYMBOLS)['passed'])


if __name__ == '__main__':
    unittest.main()
