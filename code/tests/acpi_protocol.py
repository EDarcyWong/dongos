"""Structural compatibility only; the ACPI gate owns firmware semantics."""
from __future__ import annotations

import re

FIELDS = ('rsdp', 'xsdt', 'madt', 'fadt', 'hpet', 'mcfg', 'table_count', 'cpu_count',
          'ioapic_count', 'iso_count', 'nmi_count', 'mcfg_count', 'lapic_address', 'madt_flags',
          'fadt_flags', 'boot_arch', 'pm_timer_block', 'pm_timer_length', 'pm_timer_32bit',
          'hpet_gas_info', 'hpet_address', 'pm_timer_gas_info', 'pm_timer_address', 'steps')
READY = b'DONGOS_P3_ACPI_READY'
CACHE_READY = b'DONGOS_P2_CACHE_READY'
MEMORY_READY = b'DONGOS_P2_MEMORY_READY'
LINE = re.compile(rb'acpi_([a-z0-9_]+)=0x([0-9a-f]{16})')


def project(lines):
    """Remove only an exact optional normal ACPI stage; leave errors explicit.

    This lets the older P2 gates retain their contracts and old captures.
    It does not claim to validate the new stage's firmware-derived values.
    """
    positions = [i for i, line in enumerate(lines)
                 if b'acpi_' in line.lower() or b'dongos_p3_acpi' in line.lower()]
    if not positions:
        return lines, []
    errors = []
    if lines.count(CACHE_READY) != 1 or lines.count(MEMORY_READY) != 1:
        errors.append('ACPI stage requires successful cache and normal memory completion')
    else:
        start, stop = lines.index(CACHE_READY) + 1, lines.index(MEMORY_READY)
        if positions != list(range(start, stop)):
            errors.append('ACPI stage must exclusively follow cache ready and precede memory ready')
    names = []
    for i in positions[:-1]:
        match = LINE.fullmatch(lines[i])
        names.append(match[1].decode('ascii') if match else None)
    if names != list(FIELDS) or lines[positions[-1]] != READY:
        errors.append('ACPI stage must contain exactly its ordered known fields and ready marker')
    excluded = set(positions)
    return [line for i, line in enumerate(lines) if i not in excluded], errors
