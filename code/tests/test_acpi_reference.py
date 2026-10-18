"""Synthetic raw-byte checks for the independent ACPI reference (no guest)."""

import struct
import unittest

from tests.acpi_reference import AcpiError, discover, discover_with_tables


def sdt(signature, payload, revision=1):
    header = struct.pack("<4sIBB6s8sI4sI", signature, 36 + len(payload), revision,
                         0, b"REFOS ", b"RAWBYTES", 1, b"TEST", 1)
    result = bytearray(header + payload)
    result[9] = -sum(result) & 255
    return bytes(result)


class PhysicalImage:
    def __init__(self):
        self.blocks = {}
        self.requests = []

    def read(self, address, length):
        self.requests.append((address, length))
        for base, block in self.blocks.items():
            offset = address - base
            if 0 <= offset and offset + length <= len(block):
                return block[offset:offset + length]
        raise ValueError("unbacked fixture physical range")


def image(*, optional=True, legacy_fadt=False):
    memory = PhysicalImage()
    # Deliberately unaligned firmware structures and XSDT u64 entries.
    rsdp, xsdt, madt, fadt = 0x10003, 0x11007, 0x12009, 0x1300b
    records = [struct.pack("<BBBBI", 0, 8, 2, 3, 1),
               struct.pack("<BBHIII", 9, 16, 0, 300, 2, 1000),
               struct.pack("<BBBBII", 1, 12, 7, 0, 0xfec00000, 24),
               struct.pack("<BBBBIH", 2, 10, 0, 9, 33, 15),
               struct.pack("<BBHI", 3, 8, 5, 40),
               struct.pack("<BBBHB", 4, 6, 255, 0, 1),
               struct.pack("<BBHIB3s", 10, 12, 15, 0xffffffff, 1, b"\0\0\0"),
               struct.pack("<BBHQ", 5, 12, 0, 0x1fee00000),
               b"\x80\x04\x12\x34"]
    memory.blocks[madt] = sdt(b"APIC", struct.pack("<II", 0xfee00000, 1) + b"".join(records), 5)
    body = bytearray(116 if legacy_fadt else 276)
    struct.pack_into("<I", body, 40, 0x12345000)
    struct.pack_into("<H", body, 46, 9)
    struct.pack_into("<I", body, 76, 0x608)
    body[91] = 4
    struct.pack_into("<H", body, 109, 3)
    struct.pack_into("<I", body, 112, (1 << 8) | (1 << 10))
    if not legacy_fadt:
        struct.pack_into("<BBBBQ", body, 116, 1, 8, 0, 1, 0xcf9)
        body[128] = 6
        struct.pack_into("<Q", body, 140, 0x10012345000)
        struct.pack_into("<BBBBQ", body, 208, 1, 32, 0, 3, 0x608)
    memory.blocks[fadt] = sdt(b"FACP", body[36:], 1 if legacy_fadt else 6)
    entries = [fadt, madt]
    if optional:
        hpet, mcfg = 0x1400d, 0x1500f
        hpet_body = struct.pack("<I", 0x8086a201)
        hpet_body += struct.pack("<BBBBQ", 0, 0, 0, 0, 0xfed00000)
        hpet_body += struct.pack("<BHB", 0, 0x80, 0xa1)
        memory.blocks[hpet] = sdt(b"HPET", hpet_body)
        mcfg_body = bytes(8) + struct.pack("<QHBBI", 0xe0000000, 0, 0, 127, 0)
        mcfg_body += struct.pack("<QHBBI", 0x100000000, 2, 128, 255, 0)
        memory.blocks[mcfg] = sdt(b"MCFG", mcfg_body)
        entries.extend([hpet, mcfg])
    unknown = 0x16011
    memory.blocks[unknown] = sdt(b"OEMX", b"unrecognized but checksummed")
    entries.append(unknown)
    memory.blocks[xsdt] = sdt(b"XSDT", b"".join(struct.pack("<Q", value) for value in entries))
    pointer = bytearray(struct.pack("<8sB6sBIIQB3s", b"RSD PTR ", 0, b"REFOS ", 2,
                                    0, 36, xsdt, 0, b"\0\0\0"))
    pointer[8] = -sum(pointer[:20]) & 255
    pointer[32] = -sum(pointer) & 255
    memory.blocks[rsdp] = bytes(pointer)
    return memory, rsdp, xsdt, madt, fadt


class AcpiReferenceTests(unittest.TestCase):
    def test_raw_inventory_uses_all_fields_and_record_kinds(self):
        memory, rsdp, xsdt, madt, fadt = image()
        result = discover_with_tables(memory.read, rsdp)
        inv = result["inventory"]
        self.assertEqual({key: inv[key] for key in ("rsdp", "xsdt", "madt", "fadt")},
                         dict(rsdp=rsdp, xsdt=xsdt, madt=madt, fadt=fadt))
        self.assertEqual((inv["rsdp_revision"], inv["table_count"], inv["lapic_address"], inv["madt_flags"]),
                         (2, 5, 0x1fee00000, 1))
        self.assertEqual(inv["cpus"], [dict(kind=0, uid=2, apic_id=3, flags=1),
                                      dict(kind=9, uid=1000, apic_id=300, flags=2)])
        self.assertEqual(inv["ioapics"], [dict(id=7, address=0xfec00000, gsi_base=24)])
        self.assertEqual(inv["isos"], [dict(bus=0, source=9, gsi=33, flags=15)])
        self.assertEqual(inv["nmis"], [dict(kind=3, processor=0, flags=5, lint=0, gsi=40),
                                      dict(kind=4, processor=255, flags=0, lint=1, gsi=0),
                                      dict(kind=10, processor=0xffffffff, flags=15, lint=1, gsi=0)])
        self.assertEqual((inv["cpu_count"], inv["ioapic_count"], inv["iso_count"], inv["nmi_count"], inv["mcfg_count"]),
                         (2, 1, 1, 3, 2))
        self.assertEqual(inv["mcfg_regions"], [dict(base=0xe0000000, segment=0, start_bus=0, end_bus=127),
                                              dict(base=0x100000000, segment=2, start_bus=128, end_bus=255)])
        self.assertEqual((inv["fadt_revision"], inv["fadt_flags"], inv["sci_interrupt"], inv["boot_arch"],
                          inv["dsdt"], inv["pm_timer_block"], inv["pm_timer_length"], inv["pm_timer_32bit"], inv["reset_value"]),
                         (6, 0x500, 9, 3, 0x10012345000, 0x608, 4, 1, 6))
        self.assertEqual(inv["pm_timer_gas"], dict(address_space=1, bit_width=32, bit_offset=0, access_size=3, address=0x608))
        self.assertEqual(inv["reset_gas"], dict(address_space=1, bit_width=8, bit_offset=0, access_size=1, address=0xcf9))
        self.assertEqual(inv["hpet_gas"], dict(address_space=0, bit_width=0, bit_offset=0, access_size=0, address=0xfed00000))
        self.assertEqual((inv["hpet_id"], inv["hpet_number"], inv["hpet_min_tick"], inv["hpet_page_protection"]),
                         (0x8086a201, 0, 0x80, 0xa1))
        self.assertEqual([entry["signature"] for entry in result["tables"]],
                         ["RSD PTR ", "XSDT", "FACP", "APIC", "HPET", "MCFG", "OEMX"])
        self.assertTrue(all(len(entry["sha256"]) == 64 for entry in result["tables"]))
        # Register and AML addresses are values only, never physical reads.
        self.assertTrue(all(address < 0x17000 for address, length in memory.requests))

    def test_missing_optional_tables_and_legacy_fadt_tail(self):
        memory, rsdp, *_ = image(optional=False, legacy_fadt=True)
        inv = discover(memory.read, rsdp)
        self.assertEqual((inv["table_count"], inv["hpet"], inv["mcfg"], inv["mcfg_count"]), (3, 0, 0, 0))
        self.assertEqual(inv["mcfg_regions"], [])
        self.assertEqual(inv["dsdt"], 0x12345000)
        self.assertEqual(inv["pm_timer_block"], 0x608)
        self.assertEqual(inv["pm_timer_gas"], dict(address_space=0, bit_width=0, bit_offset=0, access_size=0, address=0))
        self.assertEqual(inv["reset_gas"], inv["pm_timer_gas"])
        self.assertEqual(inv["reset_value"], 0)

    def test_unknown_table_checksum_is_not_skipped(self):
        memory, rsdp, *_ = image()
        raw = bytearray(memory.blocks[0x16011])
        raw[-1] ^= 1
        memory.blocks[0x16011] = bytes(raw)
        with self.assertRaisesRegex(AcpiError, "checksum.*OEMX"):
            discover(memory.read, rsdp)

    def test_both_rsdp_checksums_are_verified(self):
        for byte in (9, 33):
            with self.subTest(byte=byte):
                memory, rsdp, *_ = image()
                raw = bytearray(memory.blocks[rsdp])
                raw[byte] ^= 1
                memory.blocks[rsdp] = bytes(raw)
                with self.assertRaisesRegex(AcpiError, "checksum"):
                    discover(memory.read, rsdp)

    def test_partial_xsdt_pointer_is_rejected(self):
        memory, rsdp, xsdt, *_ = image()
        raw = memory.blocks[xsdt]
        memory.blocks[xsdt] = sdt(b"XSDT", raw[36:] + b"\0")
        with self.assertRaisesRegex(AcpiError, "entry span"):
            discover(memory.read, rsdp)

    def test_madt_short_known_record_and_zero_progress_are_rejected(self):
        for entry in (b"\0\x07" + bytes(5), b"\x80\0", b"\x80"):
            with self.subTest(entry=entry):
                memory, rsdp, _, madt, _ = image()
                memory.blocks[madt] = sdt(b"APIC", struct.pack("<II", 0xfee00000, 1) + entry)
                with self.assertRaisesRegex(AcpiError, "MADT"):
                    discover(memory.read, rsdp)

    def test_absent_mandatory_table_is_rejected(self):
        memory, rsdp, xsdt, madt, _ = image(optional=False)
        memory.blocks[xsdt] = sdt(b"XSDT", struct.pack("<Q", madt))
        with self.assertRaisesRegex(AcpiError, "requires MADT and FADT"):
            discover(memory.read, rsdp)

    def test_low_4g_and_length_bounds_precede_reader(self):
        calls = []
        for address in (0, -1, (1 << 32) - 10, 1 << 32):
            with self.subTest(address=address), self.assertRaises(AcpiError):
                discover(lambda pa, size: calls.append((pa, size)), address)
        self.assertEqual(calls, [])
        memory, rsdp, xsdt, *_ = image()
        header = bytearray(memory.blocks[xsdt][:36])
        struct.pack_into("<I", header, 4, (1 << 20) + 1)
        memory.blocks[xsdt] = bytes(header)
        with self.assertRaisesRegex(AcpiError, "invalid SDT length"):
            discover(memory.read, rsdp)
        self.assertEqual(memory.requests[-1], (xsdt, 36))

    def test_short_reader_result_and_unstable_header_are_rejected(self):
        memory, rsdp, xsdt, *_ = image()
        with self.assertRaisesRegex(AcpiError, "short"):
            discover(lambda pa, size: memory.read(pa, size)[:-1], rsdp)
        def changing(pa, size):
            raw = memory.read(pa, size)
            if pa == xsdt and size > 36:
                changed = bytearray(raw)
                changed[10] ^= 1
                return bytes(changed)
            return raw
        with self.assertRaisesRegex(AcpiError, "header changed"):
            discover(changing, rsdp)

    def test_extended_madt_record_and_disabled_cpu_are_preserved(self):
        memory, rsdp, _, madt, _ = image()
        entry = struct.pack("<BBBBI", 0, 10, 4, 5, 0) + b"\x12\x34"
        memory.blocks[madt] = sdt(b"APIC", struct.pack("<II", 0xfee00000, 0) + entry)
        inv = discover(memory.read, rsdp)
        self.assertEqual(inv["cpus"], [dict(kind=0, uid=4, apic_id=5, flags=0)])
        self.assertEqual(inv["cpu_count"], 1)


if __name__ == "__main__":
    unittest.main()
