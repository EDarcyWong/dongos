"""Pinned local Q35/OVMF ACPI samples, captured by the clock QEMU collector.

The original capture path in manifest.json is provenance only. Loading these
fixtures never reads build artifacts, contacts the network, or starts a guest.
"""
from pathlib import Path
import hashlib
import json
import struct


DIRECTORY = Path(__file__).resolve().parent / 'fixtures/acpi-q35'
PINNED = {
    'FACP': (244, '410716dfb169eaba296ed3c336028843b3cf9fce6ca7c179bb242199cfec9d1a'),
    'DSDT': (8716, '77061a02e92a1b786f951745724f42fae77b404b3e4ed5430b8b1496d3be44b5'),
}
COLLECTOR_SHA256 = '194da79f32628f0cf75fe440a13f984bf2968d9e64b45cbc61730fdc57364aa2'
CAPTURE_MANIFEST_SHA256 = '3e759b7ff3820f4ef48761f0e73e871fbfbcfe6d26a76dbc4ed451a18888115f'
CAPTURE_RESULT_SHA256 = 'b2e3cc63734dbce62c0b0011f5470735a98daca974c8c3d2810854b76a0cca62'


def fixture_inputs():
    return [Path(__file__), DIRECTORY / 'manifest.json', DIRECTORY / 'README.md',
            *(DIRECTORY / (signature + '.bin') for signature in PINNED)]


def load_fixture(directory=DIRECTORY):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 1:
        raise ValueError('unsupported pinned ACPI fixture manifest')
    capture = manifest.get('capture', {})
    if (capture.get('actual_qemu_executed') is not True
            or capture.get('collector_passed') is not True
            or capture.get('collector_sha256') != COLLECTOR_SHA256
            or capture.get('acpi_manifest_sha256') != CAPTURE_MANIFEST_SHA256
            or capture.get('result_sha256') != CAPTURE_RESULT_SHA256):
        raise ValueError('pinned ACPI fixture capture provenance changed')
    saved = manifest.get('saved', [])
    if len(saved) != len(PINNED) or {item.get('signature') for item in saved} != set(PINNED):
        raise ValueError('pinned ACPI fixture table set changed')
    files = {}
    for item in saved:
        signature = item['signature']
        size, digest = PINNED[signature]
        name = signature + '.bin'
        if (item.get('length') != size or item.get('sha256') != digest
                or item.get('file') != name or item.get('checksum_verified') is not True):
            raise ValueError('pinned ACPI fixture metadata changed: ' + signature)
        path = directory / name
        raw = path.read_bytes()
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('pinned ACPI fixture bytes changed: ' + signature)
        if (raw[:4] != signature.encode('ascii') or struct.unpack_from('<I', raw, 4)[0] != size
                or sum(raw) & 255):
            raise ValueError('invalid pinned ACPI table structure: ' + signature)
        files[signature] = path
    return manifest, files
