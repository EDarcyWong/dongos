#!/usr/bin/env python3
"""Boot a verified raw GPT/ESP file through emulated USB into the real desktop.

This validates firmware USB boot media. The runtime filesystem/data disk remains
VirtIO; success does not claim a DongOS xHCI or USB mass-storage driver. Only an
ordinary image file is accepted. No physical disk or host USB device is opened.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import build as builder
from tools import make_usb_image as usb
from tools.build_usb import verify_build
from tools.make_fat32_disk import create as create_data_disk
from tests import run_services_qemu as storage
from tests.run_desktop_settings_qemu import Guest, ROOT, DARK, check, sha


USB_DRIVE = 'usbboot'
USB_DEVICE = 'usb-boot-device'
USB_SERIAL = 'DONGOS_RAW_USB'
USB_SLOT = 5


def replace_boot_drive(command, esp, image):
    """Remove the host-directory ESP and expose exactly one raw USB boot disk."""
    source = 'format=raw,file=fat:rw:' + Path(esp).resolve().as_posix().replace(',', ',,')
    result = []
    removed = 0
    cursor = 0
    while cursor < len(command):
        if command[cursor] == '-drive' and cursor + 1 < len(command) and command[cursor + 1] == source:
            removed += 1
            cursor += 2
        else:
            result.append(command[cursor])
            cursor += 1
    check(removed == 1, 'expected exactly one source ESP drive to replace')
    check(not any('fat:rw:' in value or 'fat:ro:' in value for value in result), 'a directory-backed boot source remains')
    check('-boot' not in result and not any('bootindex=' in value for value in result), 'unexpected existing boot order')
    raw = Path(image).resolve().as_posix().replace(',', ',,')
    result += ['-device', f'qemu-xhci,id=usbhost,addr=0x{USB_SLOT:x}',
               '-drive', f'if=none,id={USB_DRIVE},format=raw,readonly=on,file={raw}',
               '-device', f'usb-storage,id={USB_DEVICE},bus=usbhost.0,port=1,drive={USB_DRIVE},'
                          f'removable=on,bootindex=1,serial={USB_SERIAL}',
               '-boot', 'strict=on']
    return result


def firmware_usb_boot(raw):
    """Require an actual OVMF start from our fixed xHCI PCI slot/USB path."""
    text = raw.decode('utf-8', errors='replace') if isinstance(raw, (bytes, bytearray)) else raw
    lines = re.findall(r'BdsDxe: starting Boot[0-9A-Fa-f]+ [^\r\n]+', text)
    check(len(lines) == 1, 'expected one actual firmware boot-start record')
    match = re.fullmatch(r'BdsDxe: starting (Boot[0-9A-Fa-f]+) "([^"]+)" from (.+)', lines[0])
    check(match is not None, 'firmware start record has an unsupported format')
    option, label, path = match.groups()
    check(re.search(rf'/Pci\(0x{USB_SLOT:x},0x0\)/USB\(', path, re.IGNORECASE) is not None,
          'firmware did not start the designated xHCI USB device')
    check('USB' in label.upper(), 'firmware boot label is not USB storage')
    check('SATA(' not in path.upper() and 'NVME(' not in path.upper(), 'firmware started another storage transport')
    check('DONGOS_P1_START' in text and text.index(lines[0]) < text.index('DONGOS_P1_START'),
          'DongOS entry does not follow the observed USB boot start')
    return dict(option=option, label=label, device_path=path, serial_record=lines[0],
                xhci_pci_slot=USB_SLOT, transport='firmware xHCI USB bulk-only storage',
                only_bootindexed_os_media=True)


def verify_block_attachment(blocks, image):
    wanted = Path(image).resolve()
    matches = [item for item in blocks if item.get('device') == USB_DRIVE]
    check(len(matches) == 1, 'QMP did not expose the exact raw USB drive')
    item = matches[0]
    inserted = item.get('inserted', {})
    name = inserted.get('image', {}).get('filename', inserted.get('file', ''))
    check(name and Path(name).resolve() == wanted and inserted.get('drv') == 'raw' and inserted.get('ro') is True,
          'QMP USB media filename/format/read-only state differs')
    check(item.get('removable') is True, 'USB boot device is not removable media')
    return item


def verify_usb_inventory(text):
    # Firmware and QMP expose different product labels. Device identity comes
    # from the configured ID/port plus the independently checked raw drive.
    records = re.findall(r'^\s*Device (\d+\.\d+), Port (\d+), Speed (\d+) Mb/s, Product ([^,\r\n]+), ID: ([^\s,]+)\s*$', text, re.MULTILINE)
    matches = [item for item in records if item[4] == USB_DEVICE]
    check(len(matches) == 1 and matches[0][1] == '1' and int(matches[0][2]) >= 480,
          'QMP USB inventory lacks the designated boot storage device/port')
    device, port, speed, product, identity = matches[0]
    return dict(device=device, port=int(port), speed_mbps=int(speed), product=product, identity=identity)


class UsbGuest(Guest):
    def __init__(self, esp, disk, state, image):
        original = builder.qemu_command
        def command(*args, **kwargs):
            return replace_boot_drive(original(*args, **kwargs), esp, image)
        builder.qemu_command = command
        try:
            super().__init__(esp, disk, state)
        finally:
            builder.qemu_command = original


class UsbRunnerTests(unittest.TestCase):
    def test_inventory_identity_is_separate_from_product_label(self):
        valid = '  Device 0.1, Port 1, Speed 5000 Mb/s, Product QEMU USB MSD, ID: usb-boot-device\r\n'
        self.assertEqual(USB_DEVICE, verify_usb_inventory(valid)['identity'])
        self.assertEqual('QEMU USB HARDDRIVE', verify_usb_inventory(valid.replace('QEMU USB MSD', 'QEMU USB HARDDRIVE'))['product'])
        for bad in (valid.replace('usb-boot-device', 'other'), valid.replace('Port 1', 'Port 2'),
                    valid.replace('5000 Mb/s', '12 Mb/s'), valid + valid):
            with self.assertRaises(ValueError): verify_usb_inventory(bad)

    def test_boot_command_has_only_raw_usb_os_media(self):
        with tempfile.TemporaryDirectory() as directory:
            esp, image = Path(directory) / 'esp', Path(directory) / 'disk,raw.img'
            fat = 'format=raw,file=fat:rw:' + esp.resolve().as_posix()
            source = ['qemu', '-drive', 'if=pflash,file=firmware.fd', '-drive', fat, '-display', 'none']
            actual = replace_boot_drive(source, esp, image)
            self.assertEqual(['qemu', '-drive', 'if=pflash,file=firmware.fd', '-display', 'none'], actual[:5])
            self.assertFalse(any('fat:' in item for item in actual))
            self.assertTrue(any('disk,,raw.img' in item and 'readonly=on' in item for item in actual))
            self.assertEqual(1, sum('bootindex=1' in item for item in actual))
            self.assertIn('strict=on', actual)
            with self.assertRaises(ValueError): replace_boot_drive(source + ['-drive', fat], esp, image)
            with self.assertRaises(ValueError): replace_boot_drive(source + ['-boot', 'c'], esp, image)

    def test_actual_firmware_path_requires_target_usb_before_entry(self):
        valid = ('BdsDxe: starting Boot0001 "UEFI QEMU USB HARDDRIVE DONGOS_RAW_USB" from '
                 'PciRoot(0x0)/Pci(0x5,0x0)/USB(0x0,0x0)\r\nDONGOS_P1_START\r\n')
        self.assertEqual('Boot0001', firmware_usb_boot(valid)['option'])
        for bad in (valid.replace('/USB(0x0,0x0)', '/Sata(0x0,0x0,0x0)'),
                    valid.replace('/Pci(0x5,', '/Pci(0x6,'),
                    valid.replace('starting', 'loading'),
                    valid.replace('DONGOS_P1_START', 'DONGOS_P1_FAIL'),
                    valid + valid):
            with self.assertRaises(ValueError): firmware_usb_boot(bad)

    def test_qmp_attachment_is_exact_readonly_raw_file(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'usb.img'
            item = dict(device=USB_DRIVE, removable=True,
                        inserted=dict(drv='raw', ro=True, image=dict(filename=str(image.resolve()))))
            self.assertEqual(item, verify_block_attachment([item], image))
            for field, value in (('drv', 'qcow2'), ('ro', False)):
                changed = dict(item, inserted=dict(item['inserted'], **{field: value}))
                with self.assertRaises(ValueError): verify_block_attachment([changed], image)
            with self.assertRaises(ValueError): verify_block_attachment([item], image.with_name('other.img'))
            with self.assertRaises(ValueError): verify_block_attachment([item, item], image)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp', type=Path)
    parser.add_argument('--image', type=Path, help='existing verified raw image, or a NEW .img file to create')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(UsbRunnerTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if args.reuse_esp is None or args.image is None:
        parser.error('--reuse-esp and --image are required')
    esp = args.reuse_esp.resolve()
    image = usb._reject_special(args.image)
    check(image.suffix.lower() == '.img', 'USB boot source must be an ordinary .img file')
    state = ROOT / 'build/test/p8-usb-boot/qemu' / ('run-' + uuid.uuid4().hex[:12])
    state.mkdir(parents=True)
    result = dict(passed=False, actual_qemu_boots=0, validation_scope='firmware USB boot medium only',
                  dongos_usb_storage_driver_accepted=False, source_esp=str(esp), image=str(image))
    inputs = {str(ROOT / name): sha(ROOT / name) for name in
              ('tests/run_usb_image_qemu.py', 'tests/run_desktop_settings_qemu.py', 'tests/run_desktop_qemu.py',
               'tools/make_usb_image.py', 'tools/build_usb.py')}
    result['runner_inputs'] = inputs
    guest = None
    metadata = None
    initial_image = None
    def unchanged():
        return (all(sha(name) == expected for name, expected in inputs.items()) and metadata is not None
                and all(sha(ROOT / name) == expected for name, expected in metadata['source_sha256'].items()))
    try:
        metadata = verify_build(esp)
        source = usb._source(esp)
        expected = {name: dict(length=item['length'], sha256=item['sha256'])
                    for name, item in source.items() if item['kind'] == 'file'}
        if not image.exists():
            ancestor = image.parent
            while not ancestor.exists():
                ancestor = ancestor.parent
            usb._no_links(ancestor, directory=True)
            image.parent.mkdir(parents=True, exist_ok=True)
            result['image_created'] = usb.create(esp, image, 128)
        before = usb.inspect_image(image, expected)
        initial_image = before['image_sha256']
        storage.write_json(state / 'raw-usb-before.json', before)
        data_disk = state / 'virtio-user-data.img'
        create_data_disk(data_disk, 64)
        guest = UsbGuest(esp, data_disk, state / 'guest', image)
        result['actual_qemu_boots'] = 1
        result['firmware_usb_boot'] = firmware_usb_boot(guest.raw)
        check(not any('fat:rw:' in value or 'fat:ro:' in value for value in guest.evidence['command']),
              'QEMU retained a host directory boot source')
        blocks = guest.qmp.request('query-block')
        result['raw_usb_attachment'] = verify_block_attachment(blocks, image)
        storage.write_json(state / 'actual-blocks.json', blocks)
        tree = guest.qmp.request('human-monitor-command', {'command-line': 'info qtree'})
        info_usb = guest.qmp.request('human-monitor-command', {'command-line': 'info usb'})
        (state / 'actual-qtree.txt').write_text(tree, encoding='utf-8')
        (state / 'actual-usb.txt').write_text(info_usb, encoding='utf-8')
        check(USB_DEVICE in tree and 'usbhost.0' in tree and USB_SERIAL in tree and 'usb-storage' in tree,
              'actual USB device/controller/serial topology differs')
        result['actual_usb_inventory'] = verify_usb_inventory(info_usb)
        bootindex = guest.qmp.request('qom-get', {'path': '/machine/peripheral/' + USB_DEVICE, 'property': 'bootindex'})
        check(bootindex == 1, 'actual USB bootindex differs')
        result['actual_usb_bootindex'] = bootindex
        scale = guest.descriptor()[14]
        guest.verify_state('usb-boot-desktop', scale, DARK, 0)
        guest.focus(2)
        for key in ('u', 's', 'b'):
            guest.key(key)
        guest.key('ctrl', 's')
        guest.wait(b'DONGOS_EDITOR_SAVED', 15)
        guest.verify_state('usb-boot-editor-saved', scale, DARK, 0, b'usb')
        check(b'DONGOS_P1_EBS_OK' in guest.raw and b'DONGOS_FS_READY' in guest.raw
              and b'DONGOS_BLK_READY' in guest.raw and b'DONGOS_P7_AVX_CONTEXT_READY' in guest.raw,
              'USB boot did not retain the actual kernel/storage/vector service path')
        result['guest'] = dict(guest.evidence)
        guest.close()
        guest = None
        result['virtio_data_disk'] = storage.check_disk(data_disk, raw_name=b'NOTE    TXT', payload=b'usb')
        after = usb.inspect_image(image, expected)
        storage.write_json(state / 'raw-usb-after.json', after)
        check(after['image_sha256'] == initial_image, 'read-only USB boot image changed')
        verify_build(esp)
        result.update(passed=True, actual_private_processes=5, all_elf_executable_bytes_verified=True,
                      user_stack_guards_verified=10, actual_desktop_palette_and_font_verified=True,
                      actual_editor_input_verified=True, virtio_user_data_flush_verified=True,
                      raw_gpt_fat_payload_and_media_unchanged=True,
                      screenshot=str(state / 'guest/usb-boot-editor-saved.png'))
    except Exception as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if guest:
            guest.close()
        guest_report = state / 'guest/guest.json'
        if guest_report.exists():
            actual_guest = json.loads(guest_report.read_text(encoding='utf-8'))
            result['guest'] = actual_guest
            result['actual_qemu_boots'] = 1 if actual_guest.get('actual_qemu_executed') else 0
        result['source_unchanged'] = unchanged()
        if not result['source_unchanged']:
            result.update(passed=False, source_identity_error='source changed during verification or completed-build metadata unavailable')
        if initial_image is not None:
            result['final_image_sha256'] = sha(image)
            if result['final_image_sha256'] != initial_image:
                result.update(passed=False, media_identity_error='USB boot image changed')
        storage.write_json(state / 'result.json', result)
    print('P8 USB boot', 'PASS' if result['passed'] else 'FAIL', state, result.get('error', ''), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
