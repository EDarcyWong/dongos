"""Independent host controls for the real GUI guest gate; starts no guest."""
from copy import deepcopy
import json
import struct
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tests import run_gui_clients_qemu as gate


def fixture():
    token = 0x108
    record = dict(role=1, owner=gate.owner_key(token), epoch=7, token=(7 << 32) | 257,
        lease=(7 << 32) | 257, bytes=8192, stride=256, width=64, height=32,
        serial=3, sequence=9, presented=9, copied_serial=3, copied_sequence=9)
    root = dict(rights=395, kind=3, owner=record['owner'], epoch=4, path=b'/', live=1)
    font = dict(scale=320, pixels=20, bytes=12345)
    mappings = [(0x8000000000300007 + i * 4096, 0x8000000000300007 + i * 4096,
                 [dict(effective_user=False)]) for i in range(2)]
    return record, 7, token, 1, root, font, mappings


class GuiGuestOracleControls(unittest.TestCase):
    def test_exact_caller_bound_surface_and_fs_root(self):
        result = gate.validate_surface(*fixture())
        self.assertEqual((1, 2, [0x300000, 0x301000]),
                         (result['role'], result['pages'], result['physical_pages']))

    def test_ownership_epoch_role_budget_commit_and_readonly_root_controls(self):
        fields = (('owner', (9 << 32) | 1), ('epoch', 6), ('token', (6 << 32) | 257),
                  ('lease', (6 << 32) | 257), ('role', 2), ('bytes', 9000),
                  ('stride', 255), ('height', 0), ('width', 2000), ('serial', 0),
                  ('sequence', 0), ('presented', 8), ('presented', 10),
                  ('token', (7 << 32) | 1), ('lease', (7 << 32) | 1),
                  ('copied_serial', 2), ('copied_sequence', 8))
        for name, value in fields:
            args = list(fixture())
            args[0][name] = value
            with self.subTest(field=name), self.assertRaises(ValueError):
                gate.validate_surface(*args)
        for name, value in (('rights', 1023), ('kind', 2), ('owner', 0), ('path', b'/Documents'),
                            ('live', 0), ('epoch', 0)):
            args = list(fixture())
            args[4][name] = value
            with self.subTest(root=name), self.assertRaises(ValueError):
                gate.validate_surface(*args)

    def test_alias_flags_mismatched_pa_other_client_and_repeated_page_rejected(self):
        variants = []
        args = list(fixture()); args[6][0] = (args[6][0][0], args[6][0][1] + 4096, args[6][0][2]); variants.append(args)
        for bit in (1 << 63, 2, 4, 8, 16, 128, 256):
            args = list(fixture())
            a, b, others = args[6][0]
            args[6][0] = (a ^ bit, b ^ bit, others)
            variants.append(args)
        args = list(fixture()); args[6][0][2][0]['effective_user'] = True; variants.append(args)
        args = list(fixture()); args[6][1] = args[6][0]; variants.append(args)
        args = list(fixture()); args[6].pop(); variants.append(args)
        for index, args in enumerate(variants):
            with self.subTest(case=index), self.assertRaises(ValueError):
                gate.validate_surface(*args)

    def test_font_selected_size_and_reserved_process_slot_rejected(self):
        for name, value in (('scale', 321), ('pixels', 16), ('bytes', 0)):
            args = list(fixture()); args[5][name] = value
            with self.subTest(field=name), self.assertRaises(ValueError):
                gate.validate_surface(*args)
        for token in (0, 0x101, 0x10e, 0x111, 1 << 40):
            with self.subTest(token=token), self.assertRaises(ValueError):
                gate.owner_key(token)

    def test_relaunch_requires_new_incarnation_and_three_unchanged_processes(self):
        snapshots = [dict(process=0, generation=0, state=0) for _ in range(18)]
        for config in range(14, 18):
            snapshots[config] = dict(process=0x108 + config - 14, generation=1, state=2)
        before = dict(snapshots=snapshots)
        after = deepcopy(before)
        after['snapshots'][15] = dict(process=0x209, generation=2, state=2)
        gate.validate_relaunch(before, after, 0x109, 0x209)
        for config in (14, 15, 16, 17):
            bad = deepcopy(after)
            bad['snapshots'][config]['process'] = 0x309 if config != 15 else 0x109
            with self.subTest(config=config), self.assertRaises(ValueError):
                gate.validate_relaunch(before, bad, 0x109, 0x209)
        bad = deepcopy(after); bad['snapshots'][15]['generation'] = 1
        with self.assertRaises(ValueError):
            gate.validate_relaunch(before, bad, 0x109, 0x209)

    def test_keyboard_is_physical_qcodes_and_never_silently_drops_characters(self):
        expected = {'a': ('a',), 'A': ('shift', 'a'), ' ': ('spc',), '/': ('slash',),
                    '"': ('shift', 'apostrophe'), '+': ('shift', 'equal'), '.': ('dot',)}
        for character, keys in expected.items():
            self.assertEqual(keys, gate.qcodes(character))
        for character in ('\n', '\0', '中文', '😀', ''):
            with self.assertRaises(ValueError):
                gate.qcodes(character)

    def test_layout_fields_are_bounded_and_byte_padding_cannot_shift_scalar(self):
        layouts = gate.Layouts([dict(full_name='fixture.State', size=24,
            fields=[dict(name='flag', offset=0, size=1), dict(name='value', offset=8, size=8)])])
        raw = bytes([1]) + bytes(7) + struct.pack('<Q', 0x1234) + bytes(8)
        self.assertEqual(1, layouts.number(raw, 'fixture.State', 'flag'))
        self.assertEqual(0x1234, layouts.number(raw, 'fixture.State', 'value'))
        with self.assertRaises(ValueError):
            layouts.number(raw[:-1], 'fixture.State', 'value')

    def test_actual_three_stage_pixels_cannot_be_replaced_by_ram_only_checks(self):
        gate.validate_pixels(0x00123456, 0xff123456, 0x123456, 1)
        gate.validate_pixels(0x00123456, 0xff123456, 0x563412, 0)
        for source, cache, gop, format in ((0x123456, 0xff123456, 0x563412, 1),
            (0x123456, 0xff112233, 0x123456, 1), (0x123456, 0x123456, 0x123456, 1),
            (0x123456, 0xff123456, 0x112233, 1), (0x123456, 0xff123456, 0x123456, 2)):
            with self.subTest(source=source, cache=cache, gop=gop, format=format), self.assertRaises(ValueError):
                gate.validate_pixels(source, cache, gop, format)
        self.assertIs(gate.GuiGuest.verify_elf, gate.lifecycle.ProcessGuest.verify_elf)

    def test_constructor_failure_captures_before_parent_cleanup_exactly_once(self):
        events=[]
        def initialize(instance,*args):
            instance.evidence={}
            instance.close() # Mirrors the real parent constructor failure path.
            raise ValueError('actual kernel failed before constructor returned')
        with patch.object(gate.lifecycle.ProcessGuest,'__init__',initialize), \
             patch.object(gate.lifecycle.ProcessGuest,'close',lambda instance:events.append('close')), \
             patch.object(gate.GuiGuest,'capture_failure',lambda instance:events.append('sixteen-slots')), \
             patch.object(gate.GuiGuest,'screenshot',lambda instance,name:events.append('screenshot')):
            with self.assertRaisesRegex(ValueError,'actual kernel failed'):
                gate.GuiGuest(Path('esp'),Path('disk'),Path('state'),None,None)
        self.assertEqual(['sixteen-slots','screenshot','close','close'],events)

    def test_kernel_failure_marker_is_immediate_and_cannot_become_settle_timeout(self):
        class Process:
            def poll(self):return None
        class Guest:
            process=Process()
            raw=b'DONGOS_P1_KERNEL_FAIL\r\n'
        with self.assertRaisesRegex(ValueError,'actual GUI kernel/service failure'):
            gate.GuiGuest.alive(Guest())

    def test_parent_constructor_waits_for_real_clients_before_stable_frame_gate(self):
        events=[]
        class Guest:
            _gui_constructing=True
            raw=b''
            def resume(self):events.append('resume')
            def pause(self):events.append('pause')
            def alive(self):events.append('alive')
            def wait(self,marker,timeout):
                events.append(('wait',timeout))
                self.raw=marker
            def value(self,name):events.append(name);return 0
            def field(self,name,size):events.append(name);return bytes(size)
        with patch.object(gate.time,'sleep',lambda value:None):
            gate.GuiGuest.settle(Guest())
        self.assertIn(('wait',120),events)
        self.assertLess(events.index(('wait',120)),events.index('FRAME_BUSY'))

    def test_failure_capture_retains_catalog_allocator_and_actual_startup_pool(self):
        guest=object.__new__(gate.GuiGuest)
        names=('FRAME_COUNT','EXTENDED_LIMIT','STAGE_ID','STAGE_COUNT','STAGE_FAILED',
               'UNSHARE_FAILED','UNSHARE_ACTIVE','UNSHARE_ALLOCATING','UNSHARE_COUNT','RESOURCE_FAILED')
        addresses={name:0x1000+index*16 for index,name in enumerate(names)}
        reads=[]
        guest.ksym=lambda module,name:0x8000 if (module,name)==('boot.memory_startup','WORK') else addresses[name]
        guest.catalog=lambda:dict(sequence=19,snapshots=[dict(configuration=index) for index in range(18)])
        guest.layouts=gate.Layouts([
            dict(full_name='boot.memory_startup.Workspace',size=80,
                 fields=[dict(name='space',offset=16,size=40)]),
            dict(full_name='mm.paging.Space',size=40,fields=[
                dict(name='initialized',offset=0,size=1),dict(name='pool_count',offset=8,size=8),
                dict(name='pool_physical',offset=16,size=8),dict(name='used_total',offset=24,size=8)])])
        def kernel(address,size,label):
            reads.append((address,size))
            if address==addresses['STAGE_FAILED']:raise ValueError('unavailable one field')
            if address==0x8010:
                raw=bytearray(40)
                raw[0]=1
                struct.pack_into('<3Q',raw,8,128,0x600000,103)
                self.assertEqual(40,size)
                return bytes(raw)
            name=next(name for name,value in addresses.items() if value==address)
            self.assertEqual(1 if name in ('STAGE_FAILED','UNSHARE_FAILED','UNSHARE_ACTIVE',
                'UNSHARE_ALLOCATING','RESOURCE_FAILED') else 8,size)
            return (8193 if name=='FRAME_COUNT' else 1).to_bytes(size,'little')
        guest.kernel=kernel
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(gate.lifecycle.ProcessGuest,'capture_failure',lambda instance:dict(process_slots=16)):
            guest.state=Path(directory)
            report=guest.capture_failure()
            self.assertEqual(report,json.loads((guest.state/'failure.json').read_text(encoding='utf-8')))
        self.assertEqual(16,report['process_slots'])
        self.assertEqual(18,len(report['catalog']['snapshots']))
        self.assertEqual(8193,report['allocator']['FRAME_COUNT'])
        self.assertIn('unavailable one field',report['allocator']['STAGE_FAILED_error'])
        self.assertEqual(1,report['allocator']['RESOURCE_FAILED'])
        self.assertEqual(dict(initialized=1,pool_count=128,pool_physical=0x600000,used_total=103),
                         report['startup_space'])
        self.assertEqual(11,len(reads))


if __name__ == '__main__':
    unittest.main(verbosity=2)
