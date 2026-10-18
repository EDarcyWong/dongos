#!/usr/bin/env python3
"""Four real CPL3 GUI clients: QMP input, authority, pixels, durable reboot.

Uses only a completed normal ESP. Never builds an OS or writes guest RAM,
registers, or a running disk. Only root runs guests; --selftest is host-only.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests import run_process_lifecycle_qemu as lifecycle
from tests import desktop_preferences_oracle as prefs
from tests import fat_paths_oracle as fat_oracle
from tools.build_usb import verify_build
from tools.elf_symbols import read_elf_symbols
from tools.make_fat32_disk import create, SEED

ROOT, settings, storage = lifecycle.ROOT, lifecycle.settings, lifecycle.storage
NF, MASK = 1 << 63, storage.MASK
IMAGES = ('terminal', 'files', 'editor', 'settings')
DOCUMENT = '/Documents/GUI long document.txt'
PAYLOAD = b'Actual independent GUI editor saved this text.\n'
DIRECTORY = '/Documents/GUI long directory'
REMOVED = '/Documents/removed long file.txt'
check = settings.check


def owner_key(token):
    check(0 < token >> 8 <= 0x0fffffff and 8 <= token & 255 <= 16
          and token & 255 != 14, 'invalid ordinary GUI process token')
    return ((token & 255) << 32) | (token >> 8)


class Layouts:
    """Offsets come from source matching completed assembly, not guesses."""
    def __init__(self, types):
        self.types = {item['full_name']: item for item in types}

    def size(self, name):
        return self.types[name]['size']

    def field(self, name, field):
        return next(f for f in self.types[name]['fields'] if f['name'] == field)

    def offset(self, name, field):
        return self.field(name, field)['offset']

    def part(self, raw, name, field):
        item = self.field(name, field)
        check(len(raw) == self.size(name), 'incomplete actual ' + name)
        return raw[item['offset']:item['offset'] + item['size']]

    def number(self, raw, name, field):
        value = self.part(raw, name, field)
        check(len(value) in (1, 4, 8), 'not a scalar: ' + name + '.' + field)
        return int.from_bytes(value, 'little')


def checked_layouts(esp):
    from lang.dongc import compile_file
    types = {}
    verified = []
    for image, source in (('compositor', 'desktop/service.dg'),
                          ('editor', 'apps/gui_editor.dg'), ('fs', 'fs/service.dg')):
        compiled = compile_file(ROOT / 'services' / source,
                                roots=[ROOT / 'services', ROOT / 'lang/std'], mode='release')
        completed = esp.parent / 'services' / image / 'program.asm'
        check(compiled.assembly == completed.read_text(encoding='utf-8'),
              'GUI layout source differs from completed ' + image + ' assembly')
        for item in compiled.layout_manifest['types']:
            name = item['full_name']
            check(name not in types or types[name] == item, 'inconsistent shared type ' + name)
            types[name] = item
        verified.append(dict(image=image, assembly_sha256=settings.sha(completed)))
    for item in json.loads((esp.parent / 'dong_layout.json').read_text(encoding='utf-8'))['types']:
        name = item['full_name']
        check(name not in types or types[name] == item, 'kernel/service ABI differs: ' + name)
        types[name] = item
    return Layouts(types.values()), verified


def validate_surface(record, epoch, process, role, root, font, mappings):
    """Independent oracle used for actual read-only snapshots and host controls."""
    check(record['role'] == role and record['owner'] == owner_key(process), 'wrong window role/owner')
    check(record['epoch'] == epoch and record['token'] >> 32 == epoch
          and record['lease'] >> 32 == epoch and record['token'] & 255 in range(1, 17)
          and record['lease'] & 255 in range(1, 33)
          and record['token'] >> 8 & 0xffffff > 0
          and record['lease'] >> 8 & 0xffffff > 0, 'old/invalid window or lease epoch')
    check(record['bytes'] == record['stride'] * record['height']
          and record['stride'] >= record['width'] * 4 and record['stride'] % 4 == 0
          and 0 < record['width'] <= 1920 and 0 < record['height'] <= 1080
          and record['bytes'] <= 3145728, 'shared surface dimensions/budget differ')
    check(record['serial'] > 0 and record['sequence'] > 0
          and record['presented'] == record['sequence']
          and record['copied_serial'] == record['serial']
          and record['copied_sequence'] == record['sequence'], 'frame never actually copied/presented')
    check(root['rights'] == 395 and root['kind'] == 3 and root['owner'] == owner_key(process)
          and root['epoch'] > 0 and root['path'] == b'/' and root['live'] == 1,
          'GUI filesystem root is not a caller-bound read-only ROOT395')
    check(font['scale'] in (256, 320, 384, 448, 512)
          and font['pixels'] == font['scale'] // 16 and font['bytes'] >= 48,
          'font geometry differs')
    pages = (record['bytes'] + 4095) // 4096
    check(len(mappings) == pages, 'incomplete shared page inspection')
    physicals = set()
    for pair in mappings:
        client, compositor, outsiders = pair
        check(client & ~0x60 == compositor & ~0x60
              and client & (NF | 0x19f) == NF | 7 and client & MASK > 0,
              'client/server alias is not the exact WB/RW/NX non-global page')
        check(client & MASK not in physicals, 'shared surface repeats a physical page')
        physicals.add(client & MASK)
        check(all(not item['effective_user'] for item in outsiders), 'shared pixels leaked to another client')
    return dict(role=role, process=process, owner=record['owner'], window=record['token'],
                lease=record['lease'], bytes=record['bytes'], pages=pages,
                serial=record['serial'], sequence=record['sequence'], physical_pages=sorted(physicals),
                actual_root395_verified=True, dual_alias_and_other_roots_verified=True)


def validate_relaunch(before, after, retired, replacement):
    check(before['snapshots'][15]['process'] == retired and replacement != retired
          and owner_key(replacement) != owner_key(retired), 'Files process did not get a new incarnation')
    check(after['snapshots'][15]['process'] == replacement
          and after['snapshots'][15]['generation'] > before['snapshots'][15]['generation'],
          'Files relaunch generation differs')
    for config in (14, 16, 17):
        check(before['snapshots'][config]['process'] == after['snapshots'][config]['process']
              and after['snapshots'][config]['state'] == 2, 'Files restart disturbed another GUI')


def validate_pixels(source, cache, gop, pixel_format):
    source |= 0xff000000
    expected = source & 0xffffff
    check(pixel_format in (0, 1), 'unsupported real GOP pixel format')
    if pixel_format == 0:
        expected = (expected & 255) << 16 | expected & 0xff00 | expected >> 16
    check(cache == source and gop & 0xffffff == expected,
          'shared client -> private cache -> actual GOP differs')


class GuiGuest(lifecycle.ProcessGuest):
    def __init__(self, esp, disk, state, kernel_layout, layouts):
        self.layouts = layouts
        self.gui_symbols = {}
        self._gui_constructing = True
        self._gui_failure_captured = False
        try:
            super().__init__(esp, disk, state, kernel_layout)
            self.resume()
            self.wait(b'DONGOS_P7_CLIENTS_READY\r\n', timeout=120)
            self.pause()
            self.refresh_processes()
            self.settle()
        except Exception:
            self.close()
            raise
        finally:
            self._gui_constructing = False

    def close(self):
        # Parent constructors close their own partially built object. Capture
        # here, before they reap it; main() never receives that failed object.
        if getattr(self, '_gui_constructing', False) and not getattr(self, '_gui_failure_captured', False):
            self._gui_failure_captured = True
            if hasattr(self, 'evidence'):
                for name, capture in (('failure_state', self.capture_failure),
                                      ('failure_screenshot', lambda: self.screenshot('constructor-failure'))):
                    try:
                        capture()
                        self.evidence[name + '_captured'] = True
                    except Exception as error:
                        self.evidence[name + '_error'] = str(error)
        super().close()

    def alive(self):
        check(self.process.poll() is None and b'PANIC' not in self.raw
              and b'DONGOS_P1_KERNEL_FAIL' not in self.raw
              and b'DONGOS_INIT_RETRY_EXHAUSTED' not in self.raw,
              'actual GUI kernel/service failure: ' + bytes(self.raw[-1800:]).decode(errors='replace'))

    def capture_failure(self):
        report = super().capture_failure()
        try:
            report['catalog'] = self.catalog()
        except Exception as error:
            report['catalog_error'] = str(error)
        try:
            raw = self.kernel(self.ksym('user.memory', 'SPACES'), 16 * self.layouts.size('mm.paging.Space'), 'failure actual user Spaces')
            size = self.layouts.size('mm.paging.Space')
            report['user_spaces'] = [{name: self.layouts.number(raw[i*size:(i+1)*size], 'mm.paging.Space', name)
                                      for name in ('initialized', 'pool_count', 'pool_physical', 'used_total')} for i in range(16)]
            report['window_broker_used'] = self.kval('user.window_broker', 'USED')
            report['window_broker_failed'] = self.kernel(self.ksym('user.window_broker', 'FAILED'), 1, 'failure broker failstop').hex()
        except Exception as error:
            report['user_spaces_error'] = str(error)
        try:
            state = self.windows()
            report['gui_input'] = {name:self.layouts.number(state,'desktop.windows.State',name)
                                   for name in ('focus','pointer_x','pointer_y','buttons','mode','grab')}
            report['gui_client_error'] = self.value('CLIENT_ERROR')
            report['gui_scale'] = self.descriptor()[14]
            report['input_queue'] = list(struct.unpack('<2Q', self.user(4,0x54000000,16,'failure actual input queue')))
        except Exception as error:report['gui_input_error']=str(error)
        report['allocator'] = {}
        for name, size in (('FRAME_COUNT', 8), ('EXTENDED_LIMIT', 8), ('STAGE_ID', 8),
                           ('STAGE_COUNT', 8), ('STAGE_FAILED', 1), ('UNSHARE_FAILED', 1),
                           ('UNSHARE_ACTIVE', 1), ('UNSHARE_ALLOCATING', 1), ('UNSHARE_COUNT', 8),
                           ('RESOURCE_FAILED', 1)):
            try:
                raw = self.kernel(self.ksym('user.memory', name), size, 'failure allocator ' + name)
                report['allocator'][name] = int.from_bytes(raw, 'little')
            except Exception as error:
                report['allocator'][name + '_error'] = str(error)
        try:
            address = self.ksym('boot.memory_startup', 'WORK') + self.layouts.offset('boot.memory_startup.Workspace', 'space')
            raw = self.kernel(address, self.layouts.size('mm.paging.Space'), 'failure actual startup Space')
            report['startup_space'] = {name: self.layouts.number(raw, 'mm.paging.Space', name)
                                      for name in ('initialized', 'pool_count', 'pool_physical', 'used_total')}
        except Exception as error:
            report['startup_space_error'] = str(error)
        storage.write_json(self.state / 'failure.json', report)
        return report

    def settle(self):
        # Keep actual ProcessGuest.verify_process random-stack validation.
        # The old five-process settings.Guest.verify_elf guard is never used.
        # The parent constructor dynamically calls this before our own
        # __init__ wait. Initial client allocation/configuration is startup,
        # so its separate deadline precedes the stable-frame deadline.
        if getattr(self, '_gui_constructing', False) and b'DONGOS_P7_CLIENTS_READY\r\n' not in self.raw:
            self.resume()
            self.wait(b'DONGOS_P7_CLIENTS_READY\r\n', timeout=120)
            self.pause()
        self.resume()
        time.sleep(.10)
        self.pause()
        self.alive()
        deadline = time.monotonic() + 20
        while (self.value('FRAME_BUSY') or self.field('CACHES_DIRTY', 1) != b'\0'
               or self.field('BACKGROUND_DIRTY', 1) != b'\0' or self.value('CACHE_MASK')
               or self.field('ALPHA', 32) != self.field('PRESENTED_ALPHA', 32)
               or self.value('MOTION_ACTIVE')
               or self.field('VISUAL_RECTS', 128) != self.field('PRESENTED_RECTS', 128)
               or self.value('STYLE_REVISION') != self.value('PRESENTED_STYLE_REVISION')):
            check(time.monotonic() < deadline, 'real compositor did not settle')
            self.alive()
            self.resume()
            time.sleep(.08)
            self.pause()

    def screenshot(self, name):
        ppm = self.state / (name + '.ppm')
        self.qmp.request('screendump', dict(filename=str(ppm.resolve())))
        from PIL import Image
        Image.open(ppm).save(self.state / (name + '.png'))
        return name + '.png'

    def struct(self, pid, image, module, name, type_name):
        self.refresh_processes()
        symbols = self.gui_symbols.setdefault(image, read_elf_symbols(
            self.esp.parent / 'services' / image / 'program.elf'))
        bias = struct.unpack_from('<Q', self.processes, pid * lifecycle.PROCESS_BYTES + 224)[0]
        address = bias + symbols[storage.symbol(module, name)]
        return self.user(pid, address, self.layouts.size(type_name), module + '.' + name)

    def app(self, role):
        catalog = self.catalog()
        configuration = 13 + role
        snapshot = catalog['snapshots'][configuration]
        check(snapshot['state'] == 2 and snapshot['process'] != 0, 'GUI role is not actually READY')
        pid = catalog['slots'][configuration]
        check(pid >= 7 and pid != 13, 'GUI used a system/USB physical slot')
        return pid, IMAGES[role - 1], snapshot['process']

    def model(self, role):
        pid, image, _ = self.app(role)
        return self.struct(pid, image, 'lib.gui_app', 'MODEL', 'lib.widget_state.State')

    def model_value(self, role, name):
        return self.layouts.number(self.model(role), 'lib.widget_state.State', name)

    def model_text(self, role, name='text'):
        raw = self.model(role)
        length = self.layouts.number(raw, 'lib.widget_state.State', name + '_length')
        data = self.layouts.part(raw, 'lib.widget_state.State', name)
        check(length <= len(data), 'application string length exceeds its actual buffer')
        return data[:length]

    def until(self, predicate, label, timeout=30):
        deadline = time.monotonic() + timeout
        while True:
            self.settle()
            if predicate():
                return
            check(time.monotonic() < deadline, 'missing actual GUI state: ' + label)
            self.resume()
            time.sleep(.08)

    def focus(self, role):
        # QMP tablet movement/click only; no focus field writes.
        d = self.descriptor()
        scale = d[14]
        self.move((195 + (role - 1) * 100 + 40) * scale // 256,
                  d[2] - 30 * scale // 256)
        self.button(True)
        self.button(False)
        self.until(lambda: self.layouts.number(self.windows(), 'desktop.windows.State', 'focus') == 256 + role,
                   'taskbar click focus role ' + str(role))

    def windows(self):
        return self.field('WINDOWS', self.layouts.size('desktop.windows.State'))

    def text(self, text):
        for char in text:
            self.key(*qcodes(char))

    def replace_input(self, role, text):
        self.focus(role)
        # Editor starts in body; Files starts in list. Bring actual path focus.
        if self.model_value(role, 'focus') != 0:
            self.key('tab')
        self.key('ctrl', 'u')
        self.text(text)
        self.until(lambda: self.model_text(role, 'input') == text.encode(), 'literal path/command input')

    def terminal(self, command, expected):
        self.replace_input(1, command)
        self.key('ret')
        self.until(lambda: expected in self.model_text(1) and self.model_value(1, 'status') == 0,
                   'terminal command ' + command)
        body = self.model_text(1)
        self.evidence.setdefault('qmp_commands', []).append(dict(command=command, text_hex=body.hex(),
            real_keyboard_only=True, no_uart_command_injected=True))
        return body

    def mapping(self, root, virtual):
        def read(physical):
            if physical not in self.tables:
                self.tables[physical] = self.physical(physical, 4096, 'GUI full permission walk')
            return self.tables[physical]
        if not hasattr(self, '_gui_kernel_pool'):
            self._gui_kernel_pool = self.trusted_kernel_pool()
        return lifecycle.fat.effective_mapping(root, virtual, read, self._gui_kernel_pool, self.private_pages(root))

    def font(self, pid, image, scale):
        raw = self.struct(pid, image, 'lib.gui_app', 'FONT', 'gfx.atlas.Atlas')
        value = lambda name: self.layouts.number(raw, 'gfx.atlas.Atlas', name)
        data = self.layouts.part(raw, 'gfx.atlas.Atlas', 'bytes')
        address, length = struct.unpack('<2Q', data)
        check(value('pixel_size') == scale // 16, 'GUI still uses an old font size')
        from tests.run_desktop_qemu import validate_font_aperture
        aperture = validate_font_aperture(self.roots[pid], address, length, self.pte)
        actual = self.user(pid, address, length, 'actual GUI RO font content')
        check(hashlib.sha256(actual).hexdigest() == settings.sha(ROOT / f'assets/fonts/dong-cjk-sc-{scale//16}.dgfont'),
              'GUI actual read-only font differs from selected resource')
        return dict(scale=scale, pixels=scale // 16, bytes=length, sha256=hashlib.sha256(actual).hexdigest(),
                    aperture=aperture)

    def root_grant(self, pid, image, process):
        client = self.struct(pid, image, 'lib.gui_app', 'CLIENT', 'lib.app_files.Client')
        session = self.layouts.part(client, 'lib.app_files.Client', 'fs')
        token = self.layouts.number(session, 'lib.files.Session', 'root')
        check(self.layouts.number(session, 'lib.files.Session', 'root_rights') == 395, 'client requested broad root')
        grants = self.struct(1, 'fs', 'fs.service', 'GRANTS', 'fs.handles.Table')
        entries = self.layouts.part(grants, 'fs.handles.Table', 'entries')
        size = self.layouts.size('fs.handles.Entry')
        slot = token & 255
        check(1 <= slot <= 32, 'invalid FS root token slot')
        entry = entries[(slot - 1) * size:slot * size]
        get = lambda field: self.layouts.number(entry, 'fs.handles.Entry', field)
        epoch = self.layouts.number(grants, 'fs.handles.Table', 'epoch')
        check(token >> 32 == epoch and token >> 8 & 0xffffff == get('generation'), 'stale root token')
        length = get('length')
        path = self.layouts.part(entry, 'fs.handles.Entry', 'path')[:length]
        return dict(rights=get('rights'), kind=get('kind'), owner=get('owner'), live=get('live'), epoch=epoch, path=path)

    def surface(self, role, scale):
        pid, image, process = self.app(role)
        raw = self.struct(pid, image, 'lib.gui_app', 'WINDOW', 'lib.window.Session')
        get = lambda field: self.layouts.number(raw, 'lib.window.Session', field)
        server = self.field('IPC', self.layouts.size('desktop.window_server.Server'))
        check(self.layouts.number(server, 'desktop.window_server.Server', 'poisoned') == 0, 'bridge poisoned')
        windows = self.layouts.part(server, 'desktop.window_server.Server', 'windows')
        slot = (get('token') & 255) - 1
        check(slot < 16, 'window token has no bridge slot')
        size = self.layouts.size('desktop.window_server.Window')
        window = windows[slot * size:(slot + 1) * size]
        active = self.layouts.part(window, 'desktop.window_server.Window', 'active')
        lease = lambda field: self.layouts.number(active, 'lib.window_broker_abi.Lease', field)
        broker_size = self.layouts.size('user.window_broker.Entry')
        broker_entries = self.kernel(self.ksym('user.window_broker', 'ENTRIES'),
            32 * broker_size, 'trusted live shared leases')
        broker_slot = (lease('lease') & 255) - 1
        check(0 <= broker_slot < 32, 'invalid trusted broker lease slot')
        broker_entry = broker_entries[broker_slot * broker_size:(broker_slot + 1) * broker_size]
        check(self.layouts.number(broker_entry, 'user.window_broker.Entry', 'live') == 1
              and self.layouts.number(broker_entry, 'user.window_broker.Entry', 'window') == get('token')
              and self.layouts.part(broker_entry, 'user.window_broker.Entry', 'value') == active,
              'bridge surface differs from real kernel-owned broker lease')
        policy = self.layouts.part(server, 'desktop.window_server.Server', 'policy')
        slots = self.layouts.part(policy, 'desktop.window_authority.State', 'slots')
        size = self.layouts.size('desktop.window_authority.Slot')
        authority = slots[slot * size:(slot + 1) * size]
        auth = lambda field: self.layouts.number(authority, 'desktop.window_authority.Slot', field)
        check(lease('lease') == get('lease') and lease('client_address') == get('address')
              and auth('serial') == get('serial') and auth('status') == 2
              and auth('committed') == get('sequence'),
              'client/bridge/policy disagree or configuration is unfinished')
        record = {name: lease(name) for name in ('owner', 'epoch', 'lease', 'bytes', 'width', 'height', 'stride')}
        record.update(token=get('token'), role=self.layouts.number(window, 'desktop.window_server.Window', 'role'),
            serial=auth('serial'), sequence=auth('committed'), presented=auth('presented'),
            copied_serial=self.layouts.number(window, 'desktop.window_server.Window', 'copied_serial'),
            copied_sequence=self.layouts.number(window, 'desktop.window_server.Window', 'copied_sequence'))
        self.refresh_processes()
        live = [i for i, root in enumerate(self.roots) if root]
        pairs = []
        for offset in range(0, record['bytes'], 4096):
            client = self.pte(self.roots[pid], lease('client_address') + offset)
            compositor = self.pte(self.roots[3], lease('server_address') + offset)
            for owner_root, address in ((self.roots[pid], lease('client_address') + offset),
                                        (self.roots[3], lease('server_address') + offset)):
                effective = self.mapping(owner_root, address)
                check(effective['effective_user'] and effective['effective_writable']
                      and effective['effective_nx'] and effective['leaf_bytes'] == 4096,
                      'authorized alias lost effective USER/RW/NX through an ancestor')
            others = [self.mapping(self.roots[other], lease('client_address') + offset)
                      for other in live if other not in (pid, 3)]
            # A separate compositor aperture must also be unavailable to clients.
            others += [self.mapping(self.roots[other], lease('server_address') + offset)
                       for other in live if other != 3]
            pairs.append((client, compositor, others))
        font = self.font(pid, image, scale)
        epoch = self.kval('user.window_broker', 'EPOCH')
        check(self.layouts.number(server, 'desktop.window_server.Server', 'epoch') == epoch
              == self.catalog()['incarnations'][3], 'trusted compositor epoch differs from bridge')
        check(self.kval('user.window_broker', 'USED') <= 8388608, 'kernel shared total charge exceeded')
        result = validate_surface(record, epoch, process, role,
                                  self.root_grant(pid, image, process), font, pairs)
        result.update(image=self.verify_process(pid, image), font=font,
                      client_address=lease('client_address'), server_address=lease('server_address'),
                      width=record['width'], height=record['height'], stride=record['stride'])
        return result

    def sample_pixels(self, role, surface):
        self.focus(role)
        self.move(4, 4)
        self.settle()
        descriptor = self.descriptor()
        q = descriptor[14]
        px = lambda value: (value * q + 128) // 256
        win = self.windows()
        slots = self.layouts.part(win, 'desktop.windows.State', 'slots')
        size = self.layouts.size('desktop.windows.Slot')
        chrome = slots[(role - 1) * size:role * size]
        rect = struct.unpack('<4q', self.layouts.part(chrome, 'desktop.windows.Slot', 'rect'))
        left, top, right, bottom = rect
        body_width, body_height = right - left - px(24), bottom - top - px(53)
        cache_stride = right - left + px(24)
        points = []
        for x, y in ((2, 2), (max(2, body_width // 2), max(2, body_height // 2)),
                     (body_width - 3, body_height - 3)):
            sx = x * surface['width'] // body_width
            sy = y * surface['height'] // body_height
            source = struct.unpack('<I', self.user(surface['image']['pid'],
                surface['client_address'] + sy * surface['stride'] + sx * 4, 4, 'real client pixel'))[0] | 0xff000000
            cache_va = descriptor[13] + (role - 1) * 0x200000 + ((y + px(55)) * cache_stride + x + px(24)) * 4
            cache = struct.unpack('<I', self.user(3, cache_va, 4, 'actual private compositor pixel'))[0]
            gx, gy = left + px(12) + x, top + px(43) + y
            gop = struct.unpack('<I', self.physical(self.boot[8] + (gy * descriptor[3] + gx) * 4, 4,
                                                  'actual UC GOP client pixel'))[0] & 0xffffff
            validate_pixels(source, cache, gop, descriptor[4])
            points.append(dict(source_x=sx, source_y=sy, source=source, cache=cache, x=gx, y=gy, gop=gop))
        return points

    def smoke(self, label):
        self.settle()
        catalog = self.catalog()
        lifecycle.check_boot_dag(catalog)
        check(bytes(self.raw).count(b'DONGOS_P7_CLIENTS_READY\r\n') == 1, 'one real completed clients marker required')
        check(self.value('CLIENT_ERROR') == 0, 'compositor reported a real client integration error')
        scale = self.descriptor()[14]
        records = []
        for role in range(1, 5):
            record = self.surface(role, scale)
            record['gop_samples'] = self.sample_pixels(role, record)
            record['screenshot'] = self.screenshot(label + '-' + IMAGES[role - 1])
            records.append(record)
        check(len({r['image']['root'] for r in records}) == 4, 'GUI processes share a CR3')
        check(sum(r['pages'] * 4096 for r in records) <= 8388608, 'global shared budget exceeded')
        check(not any(set(a['physical_pages']) & set(b['physical_pages']) for i, a in enumerate(records)
                      for b in records[i + 1:]), 'unrelated client surfaces physically overlap')
        pcid = self.pcid_snapshot()
        self.evidence.update(actual_processes=11, user_stack_guards_verified=22,
                             actual_independent_gui_clients_verified=4)
        return dict(catalog=catalog, surfaces=records, scale=scale, pcid=pcid,
                    actual_four_distinct_gui_elfs=True, actual_gop_client_pixels=True,
                    no_inprocess_application_model=True)


def qcodes(character):
    check(len(character) == 1 and 32 <= ord(character) < 127, 'physical keyboard fixture is printable ASCII only')
    plain = {' ': 'spc', '/': 'slash', '.': 'dot', '-': 'minus', '=': 'equal', '[': 'bracket_left',
             ']': 'bracket_right', '\\': 'backslash', ';': 'semicolon', "'": 'apostrophe', ',': 'comma', '`': 'grave_accent'}
    shifted = dict(zip('!@#$%^&*()_+{}|:"<>?~', ('1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
                  'minus', 'equal', 'bracket_left', 'bracket_right', 'backslash', 'semicolon', 'apostrophe',
                  'comma', 'dot', 'slash', 'grave_accent')))
    if character in shifted:
        return 'shift', shifted[character]
    if character.isupper():
        return 'shift', character.lower()
    return (plain.get(character, character),)


def exercise(guest):
    records = {}
    ps = guest.terminal('ps', b'17 settings token=')
    check(len(re.findall(rb'^\d+ [a-z-]+ token=', ps, re.M)) == 18, 'GUI ps omitted catalog records')
    records['echo_run_hex'] = guest.terminal('run echo 17', b'RUN OK token=').hex()
    echo_wait = guest.terminal('wait', b'WAIT OK token=')
    records['echo_wait_hex'] = echo_wait.hex()
    check(b'state=3 status=17\n' in echo_wait, 'GUI echo wait status differs')
    guest.terminal('run fault', b'RUN OK token=')
    fault_wait = guest.terminal('wait', b'WAIT OK token=')
    records['fault_wait_hex'] = fault_wait.hex()
    check(b'state=4 status=6\n' in fault_wait, 'GUI did not observe actual UD2 isolation')
    # The fixed writable scope provisions Documents on its first authorized
    # mutation; a read-only directory OPEN intentionally cannot create it.
    for command in ('touch "/Documents/GUI long document.txt"', '/Documents',
                    'mkdir "GUI long directory"', 'touch "removed long file.txt"',
                    'rm "removed long file.txt"', 'sync'):
        guest.replace_input(2, command)
        guest.key('ret')
        guest.until(lambda: guest.model_value(2, 'status') == 0 and not guest.model_value(2, 'dirty'),
                    'Files namespace command ' + command)
    guest.replace_input(3, DOCUMENT)
    guest.key('ctrl', 'o')
    guest.until(lambda: guest.model_value(3, 'focus') == 1 and guest.model_value(3, 'status') == 0,
                'Editor actual open')
    guest.text(PAYLOAD[:-1].decode())
    guest.key('ret')
    check(guest.model_text(3) == PAYLOAD and guest.model_value(3, 'dirty') == 1, 'Editor typed body differs')
    guest.key('ctrl', 's')
    guest.until(lambda: guest.model_value(3, 'saved') == 1 and not guest.model_value(3, 'dirty')
                and guest.model_value(3, 'status') == 0, 'Editor durable save after FLUSH')
    guest.text('unsaved')
    before = guest.catalog()['snapshots'][16]['process']
    guest.key('ctrl', 'q')
    guest.until(lambda: guest.catalog()['snapshots'][16]['process'] == before
                and guest.model_value(3, 'dirty') == 1 and guest.model_value(3, 'discard_pending') == 1,
                'dirty Editor visible discard confirmation')
    records['dirty_editor_screenshot'] = guest.screenshot('dirty-editor-rejected-close')
    # Theme + DPI must preserve the still-dirty editor's document bytes.
    dirty = guest.model_text(3)
    guest.focus(4)
    guest.key('t')
    guest.key('equal')
    check(guest.model_value(4, 'scale') == 320, 'Settings did not select DPI320')
    guest.key('ctrl', 's')
    guest.until(lambda: guest.descriptor()[14] == 320 and guest.model_value(4, 'saved') == 1
                and guest.model_value(4, 'status') == 0, 'Settings durable theme/DPI')
    light = guest.model_value(4, 'light')
    for role in range(1, 5):
        guest.until(lambda: guest.model_value(role, 'light') == light and guest.model_value(role, 'scale') == 320,
                    'THEME and CONFIGURE propagation to role ' + str(role))
        pid, image, _ = guest.app(role)
        guest.font(pid, image, 320)
    check(guest.model_text(3) == dirty and guest.model_value(3, 'dirty') == 1, 'style change lost dirty text')
    # A second save creates the other durable slot with a strictly newer record.
    guest.key('t')
    guest.key('ctrl', 's')
    guest.until(lambda: guest.model_value(4, 'preference_sequence') == 2 and guest.model_value(4, 'saved') == 1,
                'second durable preference slot')
    light = guest.model_value(4, 'light')
    for role in range(1, 5):
        guest.until(lambda: guest.model_value(role, 'light') == light and guest.model_value(role, 'scale') == 320,
                    'second THEME propagation to role ' + str(role))
    guest.focus(3)
    before = guest.catalog()['snapshots'][16]['process']
    cursor = guest.model_value(3, 'cursor')
    check(cursor > 0 and guest.model_value(3, 'focus') == 1, 'dirty Editor document cursor is not active')
    # A previous confirmation survives theme/taskbar events. Consume one harmless
    # document navigation key, then observe its acknowledgement before closing.
    guest.key('left')
    guest.until(lambda: guest.model_value(3, 'cursor') == cursor - 1
                and guest.model_value(3, 'discard_pending') == 0,
                'Editor navigation cleared the old discard confirmation')
    check(guest.model_text(3) == dirty and guest.model_value(3, 'dirty') == 1,
          'Editor navigation changed the dirty document')
    guest.key('ctrl', 'q')
    guest.until(lambda: guest.catalog()['snapshots'][16]['process'] == before
                and guest.model_value(3, 'discard_pending') == 1,
                'Editor fresh discard confirmation before the sole confirmed close')
    guest.key('ctrl', 'q')
    guest.wait_state(16, 3)
    guest.focus(3)
    guest.wait_state(16, 2)
    guest.until(lambda: guest.model_value(3, 'status') == 0, 'new Editor READY')
    before = guest.catalog()
    retired = before['snapshots'][15]['process']
    # Only this lifecycle control uses UART shell. Document/settings writes above use QMP GUI.
    records['shell_kill_files'] = guest.shell('kill ' + str(retired), expected=b'KILL OK')
    guest.wait_state(15, 5)
    guest.focus(2)
    after = guest.wait_state(15, 2)
    replacement = after['snapshots'][15]['process']
    validate_relaunch(before, after, retired, replacement)
    records['files_relaunch'] = dict(retired=retired, replacement=replacement, other_gui_processes_unchanged=True)
    # Wait for a copied/presented new Files frame, not just a catalog READY event.
    guest.until(lambda: guest.model_value(2, 'status') == 0, 'recreated Files root')
    records['final_smoke'] = guest.smoke('after-actions')
    records['durable_settings_sequence'] = 2
    return records


def disk_evidence(disk):
    tree = fat_oracle.inspect(disk, files={'/README.TXT': SEED, DOCUMENT: PAYLOAD},
        directories=('/Documents', DIRECTORY), absent=(REMOVED,))
    preferences = prefs.inspect_disk(disk)
    choice = preferences['selection']
    check(choice['status'] == 'selected' and choice['valid'] == [True, True]
          and choice['record']['sequence'] == 2 and choice['record']['theme']['scale_q8'] == 320,
          'raw FAT DESK slots did not persist both real GUI saves')
    # Exact content/namespace comes from the independent full-tree parser.
    raw = fat_oracle.FatTree(disk.read_bytes())
    check(set(raw.entries) == {'/README.TXT', '/Documents', DIRECTORY, DOCUMENT, '/DESK0.CFG', '/DESK1.CFG'},
          'GUI actions changed an unexpected file or retained a removed name')
    return dict(tree=tree, preferences=preferences)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp', type=Path)
    parser.add_argument('--smoke-only', action='store_true', help='one boot: distinct real GUI/authority/pixels only')
    parser.add_argument('--require-pcid', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        import unittest
        from tests import test_gui_clients_qemu
        return 0 if unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromModule(test_gui_clients_qemu)).wasSuccessful() else 1
    if args.reuse_esp is None:
        parser.error('--reuse-esp is required; no build is performed')
    esp = args.reuse_esp.resolve()
    directory = ROOT / 'build/test/gui-clients/qemu' / ('run-' + uuid.uuid4().hex[:12])
    directory.mkdir(parents=True)
    result = dict(passed=False, smoke_only=args.smoke_only, boots=[], actual_qemu_boots=0,
                  full_os_build_executed=False, no_guest_memory_or_register_writes=True,
                  no_host_document_or_preference_payload_injection=True)
    names = ('tests/run_gui_clients_qemu.py', 'tests/run_process_lifecycle_qemu.py',
             'tests/run_desktop_settings_qemu.py', 'tests/run_fat_paths_qemu.py',
             'tests/run_nvme_qemu.py', 'tests/fat_paths_oracle.py', 'tests/desktop_preferences_oracle.py',
             'tools/user_services.py', 'tools/build_usb.py', 'tools/elf_symbols.py')
    fingerprints = {name: settings.sha(ROOT / name) for name in names}
    guest = None
    metadata = {}
    try:
        metadata = verify_build(esp)
        result['build_inputs_sha256'] = settings.sha(esp.parent / 'build-inputs.json')
        layout, assembly = checked_layouts(esp)
        result['completed_assembly_layout_verified'] = assembly
        kernel_layout = lifecycle.nvme.check_kernel_memory_layout(esp)
        disk = directory / 'data.img'
        result['seed_geometry'] = create(disk, 64)
        result['seed'] = fat_oracle.inspect(disk, files={'/README.TXT': SEED}, exact_namespace=True)
        for boot in range(1 if args.smoke_only else 2):
            guest = GuiGuest(esp, disk, directory / ('boot-' + str(boot + 1)), kernel_layout, layout)
            record = guest.smoke('boot-' + str(boot + 1))
            if args.require_pcid:
                check(record['pcid']['enabled'] and record['pcid']['retained'] > 0, 'actual retained PCID required')
            if not args.smoke_only and boot == 0:
                record['actions'] = exercise(guest)
            elif boot == 1:
                choice = result['disk_after_boot1']['preferences']['selection']['record']
                check(guest.field('STYLE', 72).hex() == settings.theme_bytes(
                    tuple(choice['theme'][name] for name in prefs.COLOR_NAMES), 320).hex(),
                    'compositor did not restore exact raw durable Theme')
                for role in range(1, 5):
                    check(guest.model_value(role, 'scale') == 320, 'reboot client lost durable DPI')
                guest.replace_input(3, DOCUMENT)
                guest.key('ctrl', 'o')
                guest.until(lambda: guest.model_text(3) == PAYLOAD and guest.model_value(3, 'status') == 0,
                            'Editor same-disk durable readback')
                record['actual_gui_same_disk_readback'] = True
            record['evidence'] = guest.evidence
            guest.close()
            guest = None
            result['boots'].append(record)
            if not args.smoke_only:
                result['disk_after_boot' + str(boot + 1)] = disk_evidence(disk)
                if boot == 1:
                    check(result['disk_after_boot1']['tree']['image_sha256']
                          == result['disk_after_boot2']['tree']['image_sha256'],
                          'same-disk readback reboot changed the durable disk image')
        result.update(passed=True, actual_four_distinct_cpl3_clients=True,
                      actual_qmp_application_actions=not args.smoke_only,
                      same_disk_reboot_verified=not args.smoke_only)
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
        if guest is not None:
            for label, action in (('failure_state', guest.capture_failure),
                                  ('failure_screenshot', lambda: guest.screenshot('failure'))):
                try:
                    action()
                    result[label + '_captured'] = True
                except Exception as capture:
                    result[label + '_error'] = str(capture)
    finally:
        if guest is not None:
            try:
                guest.close()
            except Exception as error:
                result.update(passed=False, cleanup_error=str(error))
        guests = [json.loads(p.read_text(encoding='utf-8')) for p in directory.glob('boot-*/guest.json')]
        result['actual_qemu_boots'] = sum(item.get('actual_qemu_executed') is True for item in guests)
        result['all_started_guests_stopped'] = all(not item.get('actual_qemu_executed') or item.get('qemu_stopped') for item in guests)
        expected = 1 if args.smoke_only else 2
        if result['passed'] and (result['actual_qemu_boots'] != expected or not result['all_started_guests_stopped']):
            result.update(passed=False, error='all required actual guests must run and stop')
        result['runner_inputs_unchanged'] = all(settings.sha(ROOT / name) == digest for name, digest in fingerprints.items())
        if not result['runner_inputs_unchanged']:
            result.update(passed=False, error='runner inputs changed')
        if metadata:
            try:
                verify_build(esp)
                check(settings.sha(esp.parent / 'build-inputs.json') == result['build_inputs_sha256'], 'build identity changed')
            except Exception as error:
                result.update(passed=False, build_unchanged_error=str(error))
        storage.write_json(directory / 'result.json', result)
    print('Actual GUI clients', 'PASS' if result['passed'] else 'FAIL', directory, result.get('error', ''), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
