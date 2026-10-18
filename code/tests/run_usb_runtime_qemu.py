#!/usr/bin/env python3
"""Real USB primary FAT, HID consumption and same-image reboot; never builds.

Only root runs guests. All data files are created by the actual shell, and
raw FAT inspection occurs only after QEMU has stopped. No USB passthrough.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests import run_gui_clients_qemu as gui
from tests import fat_paths_oracle as oracle
from tests import boot_trace_capture
from tests.run_clock_calibration_qemu import ClockGuest
from tools import build as builder
from tools.build_usb import verify_build
from tools.make_fat32_disk import create, SEED

ROOT, check, settings, storage = gui.ROOT, gui.check, gui.settings, gui.storage
DIRECTORY = '/USB runtime long directory'
DOCUMENT = DIRECTORY + '/USB durable long document.txt'
REMOVED = DIRECTORY + '/removed USB long file.txt'
FIRST = b'DongOS real USB primary storage ' + b'0123456789abcdef' * 96
TAIL = b'USB same disk durable tail'
PAYLOAD = FIRST + TAIL


def usb_console_response(segment):
    """Keep the actual echo, excluding only complete bounded HID telemetry.

    Each log syscall is atomic, but another process can echo a shell character
    between the six syscalls in one HID record. Preserve every intervening byte
    and reject reordered, partial or inconsistent diagnostic records.
    """
    fields = ('source', 'kind', 'bytes', 'generation', 'raw', 'end')
    token = re.compile(rb'usb_hid_(source|kind|bytes|generation|raw)=0x([0-9a-f]{16})\r\n'
                       rb'|DONGOS_XHCI_HID_REPORT\r\n')
    kept, records, record, position = [], [], {}, 0
    for match in token.finditer(segment):
        kept.append(segment[position:match.start()]); position = match.end()
        name = match[1].decode() if match[1] else 'end'
        check(name == fields[len(record)], 'interleaved HID diagnostic field order differs')
        if name != 'end':
            record[name] = int(match[2], 16)
        else:
            check(record['source'] in (2, 3) and record['kind'] == record['source'] - 1
                  and 1 <= record['generation'] <= 16 and 3 <= record['bytes'] <= 8
                  and (record['kind'] != 1 or record['bytes'] == 8),
                  'interleaved HID diagnostic identity or bound differs')
            records.append(record); record = {}
            check(len(records) <= 32, 'too many bounded HID diagnostic records')
    if record:
        return None
    kept.append(segment[position:])
    response = gui.lifecycle.fat.fresh_response(b''.join(kept), 'pwd', exact=b'/\r\n')
    if response is not None:
        response['excluded_complete_hid_records'] = records
        response['raw_segment_sha256'] = hashlib.sha256(segment).hexdigest()
    return response


def usb_command(command, image, usb_only):
    """Convert only the base EFI volume; never hide an existing PCI failure."""
    command = list(command)
    check(command.count('-machine') == 1 and command[command.index('-machine') + 1] == 'q35',
          'one unmodified q35 machine required')
    check(not any(v.startswith(('nvme,', 'nvme-ns,', 'virtio-blk', 'ich9-ahci',
                                'qemu-xhci', 'usb-host', 'usb-storage')) for v in command),
          'preexisting storage/controller/passthrough must not be replaced or hidden')
    efi = [i for i, value in enumerate(command) if i and command[i-1] == '-drive'
           and value.startswith('format=raw,file=fat:rw:')]
    check(len(efi) == 1, 'one exact original EFI volume required')
    ordinary = [value for i, value in enumerate(command) if i and command[i-1] == '-drive'
                and not value.startswith('if=pflash,')]
    check(len(ordinary) == 1, 'unexpected ordinary drive must not be silently removed')
    command[command.index('-machine') + 1] = 'q35,sata=off' + (',i8042=off' if usb_only else '')
    command[efi[0]] = 'if=none,id=usbefi,' + command[efi[0]]
    image = Path(image).resolve().as_posix().replace(',', ',,')
    command += ['-device', 'qemu-xhci,id=usbhost,addr=0x5,p2=4,p3=0',
                '-drive', 'if=none,id=usbdata,format=raw,cache=writeback,file=' + image,
                '-device', 'usb-storage,id=usbdisk,bus=usbhost.0,port=1,drive=usbdata,removable=on',
                '-device', 'usb-kbd,id=usbkeyboard,bus=usbhost.0,port=2',
                '-device', 'usb-mouse,id=usbmouse,bus=usbhost.0,port=3',
                '-device', 'usb-storage,id=usbefi,bus=usbhost.0,port=4,drive=usbefi,bootindex=1']
    return command


def checked_layouts(esp):
    layouts, identity = gui.checked_layouts(esp)
    from lang.dongc import compile_file
    for image, path in (('input', 'drivers/input_service.dg'),
                        ('block', 'drivers/block_service.dg'), ('xhci', 'drivers/xhci_service.dg')):
        generated = compile_file(ROOT/'services'/path, roots=[ROOT/'services', ROOT/'lang/std'], mode='release')
        completed = esp.parent/'services'/image/'program.asm'
        check(generated.assembly == completed.read_text(encoding='utf-8'),
              'USB source differs from completed actual ' + image)
        for item in generated.layout_manifest['types']:
            name = item['full_name']
            check(name not in layouts.types or layouts.types[name] == item, 'USB shared ABI differs: ' + name)
            layouts.types[name] = item
        identity.append(dict(image=image, assembly_sha256=settings.sha(completed)))
    check(layouts.size('usb.enumerate.State') == 223*8, 'driver enumeration storage stride changed')
    check(layouts.size('usb.bot.State') <= 64*8, 'driver BOT storage too small')
    return layouts, identity


def validate_flush(cbw, csw, tag, actual, residue, status):
    check(len(cbw) == 31 and len(csw) == 13 and 0 < tag <= 0xffffffff,
          'incomplete actual BOT command/status or invalid tag')
    expected = bytearray(31)
    struct.pack_into('<II', expected, 0, 0x43425355, tag)
    expected[14], expected[15] = 10, 0x35
    check(cbw == expected, 'actual DMA CBW is not exact reserved-zero SYNCHRONIZE CACHE10')
    check(csw == struct.pack('<IIIB', 0x53425355, tag, 0, 0)
          and (actual, residue, status) == (0, 0, 0), 'actual DMA CSW is not matching successful FLUSH')
    return dict(tag=tag, cbw_hex=cbw.hex(), csw_hex=csw.hex(),
                actual_dma_command_and_success_status_verified=True)


def validate_primary(block, proxy, controller, epoch, capacity, selected_kind):
    check(block['backend'] == 4 and selected_kind == 0, 'actual block service did not select USB without PCI storage')
    check(block['ready'] == proxy['ready'] == 1 and block['readonly'] == 0
          and block['capacity'] == capacity and block['completed'] == proxy['completed']
          and proxy['busy'] == 0 and proxy['epoch'] == epoch, 'USB proxy medium/lifetime/completion mismatch')
    check(controller['ready'] == controller['held'] == 1 and controller['fault'] == 0
          and controller['phase'] == 8 and controller['epoch'] == epoch,
          'actual xHCI controller is not healthy/current')


def validate_keyboard(before, after, text, usb_only):
    check(after['self_epoch'] == before['self_epoch'] and after['peer_epoch'] == before['peer_epoch'] > 0,
          'HID driver/input incarnation changed')
    check(after['keyboard_sequence'] >= before['keyboard_sequence'] + 2
          and after['keyboard_kind'] == 1 and not after['usb_a'] and not after['aggregate_a'],
          'actual USB make/release was not decoded through input sources')
    check(text == b'a' if usb_only else text in (b'a', b'aa'),
          'real GUI did not consume the QMP character through the aggregate input queue')


def validate_mouse(before, pressed, released, window_pressed, window_released):
    check(released['mouse_sequence']>pressed['mouse_sequence']>before['mouse_sequence']
          and pressed['usb_left'] and pressed['aggregate_left']
          and not released['usb_left'] and not released['aggregate_left']
          and pressed['mouse_kind']==released['mouse_kind']==2
          and released['queue'][1]==0 and window_pressed&1 and window_released&1==0,
          'real USB mouse make/release did not pass through input and compositor consumption')


def validate_enumeration(devices, ports, protocols, dcbaa):
    check(ports==4 and list(protocols)==[2]*4+[0]*28 and len(dcbaa)>=4
          and [(d['port'],d['kind']) for d in devices]==[(1,3),(2,1),(3,2)],
          'USB2 data/keyboard/mouse direct-root ordering differs')
    expected={d['slot']:d['physical']+4096 for d in devices}
    check(len(expected)==3 and all(0<slot<len(dcbaa) for slot in expected)
          and all(value==expected.get(slot,0) for slot,value in enumerate(dcbaa)),
          'actual DCBAA contains a missing/shared/unexpected EFI device context')


def disk_evidence(disk):
    tree = oracle.FatTree(Path(disk).read_bytes())
    files = {'/README.TXT': SEED, DOCUMENT: PAYLOAD}
    directories = [DIRECTORY]
    for name in ('/DESK0.CFG', '/DESK1.CFG'):
        if name in tree.entries: files[name] = b''
    if '/Documents' in tree.entries: directories.append('/Documents')
    return oracle.inspect(disk, files=files, directories=directories, absent=(REMOVED,),
                          exact_namespace=True, require_multicluster_file=DOCUMENT)


def validate_boots(manifests, expected):
    count=sum(item.get('actual_qemu_executed') is True for item in manifests)
    stopped=all(not item.get('actual_qemu_executed') or item.get('qemu_stopped') for item in manifests)
    check(expected>0 and len(manifests)==count==expected and stopped,
          'all required actual USB boots must execute and stop')
    return dict(actual_qemu_boots=count,all_started_guests_stopped=stopped)


def select_usb_mouse(mice):
    # QEMU's USB HID input handler is named "QEMU HID Mouse"; the USB device
    # product string must not be mistaken for query-mice's handler name.
    candidates=[item for item in mice if item.get('absolute') is False
                and item.get('name','').lower() in ('qemu hid mouse','qemu usb mouse')]
    check(len(candidates)==1 and isinstance(candidates[0].get('index'),int)
          and candidates[0]['index']>=0,'one actual QEMU USB HID relative mouse required')
    return candidates[0]


class UsbGuest(gui.GuiGuest):
    """Own USB constructor. Never invokes NvmeGuest.__init__/block_snapshot."""
    def __init__(self, esp, disk, state, kernel_layout, layouts, usb_only=False, startup_timeout=180):
        self.esp, self.disk, self.state = Path(esp), Path(disk), Path(state)
        self.layouts, self.kernel_memory_layout = layouts, kernel_layout
        self.usb_only, self.startup_timeout = usb_only, startup_timeout
        self.gui_symbols, self.tables, self.chunks, self.raw = {}, {}, [], bytearray()
        self.process = self.qmp = self.uart = None
        self.stopped, self._usb_closed, self._gui_constructing = False, False, True
        self._gui_failure_captured = False
        self.state.mkdir(parents=True)
        self.evidence = dict(actual_qemu_executed=False, disk=str(disk), backend='usb',
                             usb_only=usb_only, no_nvme_constructor_or_backend_assumptions=True)
        try:
            self.launch()
            self.bootstrap()
        except Exception:
            self.close()
            raise
        finally:
            self._gui_constructing = False

    def launch(self):
        up, qp = storage.free_port(), storage.free_port()
        command = usb_command(builder.qemu_command(self.esp, self.state/'guest', test=True), self.disk, self.usb_only)
        index = command.index('isa-debug-exit,iobase=0xf4,iosize=0x04')
        del command[index-1:index+1]
        command[command.index('-serial')+1] = f'tcp:127.0.0.1:{up},server=on,wait=off'
        command += ['-cpu', 'max,+smep,+smap,+umip', '-S', '-qmp', f'tcp:127.0.0.1:{qp},server=on,wait=off']
        self.evidence['command'] = command
        self.stderr = (self.state/'stderr.log').open('wb')
        self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=self.stderr)
        self.evidence['actual_qemu_executed'] = True
        self.qmp = gui.lifecycle.settings.acpi.QMP(qp, self.process)
        self.uart = socket.create_connection(('127.0.0.1', up)); self.uart.settimeout(.2)
        def reader():
            with (self.state/'serial.log').open('wb') as stream:
                while self.process.poll() is None:
                    try: data = self.uart.recv(4096)
                    except socket.timeout: continue
                    except OSError: break
                    if not data: break
                    self.raw.extend(data); stream.write(data); stream.flush()
        self.reader = threading.Thread(target=reader, daemon=True); self.reader.start()
        self.qmp.request('cont')

    def bootstrap(self):
        # Capture kernel evidence even when USB/FS fails before GUI readiness.
        self.symbols = settings.acpi.validation_symbols(self.esp.parent/'kernel.elf')
        deadline=time.monotonic()+self.startup_timeout
        pattern=rb'^memory_runtime_boot_info=0x([0-9a-f]{16})\r?\n'
        while not re.search(pattern,self.raw,re.M):
            self.alive();check(time.monotonic()<deadline,'actual runtime BootInfo not published');time.sleep(.02)
        addresses=re.findall(pattern,self.raw,re.M)
        check(len(addresses)==1,'duplicate actual BootInfo publication')
        self.pause()
        self.boot=struct.unpack('<20Q',self.physical(int(addresses[0],16)-settings.acpi.HHDM,160,'BootInfo'))
        self.resume()
        for marker in (b'DONGOS_XHCI_HID_BLOCK_RPC_READY\r\n', b'DONGOS_USB_BLOCK_READY\r\n',
                       b'DONGOS_SHELL_READY\r\n', b'DONGOS_P7_CLIENTS_READY\r\n'):
            self.wait(marker, self.startup_timeout)
        self.pause()
        self.refresh_processes(); self.validate_private_pools()
        self.bias = struct.unpack_from('<Q', self.processes, 3*gui.lifecycle.PROCESS_BYTES+224)[0]
        self.syms = gui.read_elf_symbols(self.esp.parent/'services/compositor/program.elf')
        self.verify_elf()
        self.evidence['actual_xhci_elf'] = self.verify_process(13, 'xhci')
        self.settle()

    def alive(self):
        super().alive()
        check(re.search(rb'(?:xhci_error|usb_hid_error|usb_proxy_error)=0x[0-9a-f]{16}', self.raw) is None,
              'actual USB service failed: ' + bytes(self.raw[-1600:]).decode(errors='replace'))

    def verify_code(self):
        return ClockGuest.verify_code(self)

    def trace_snapshot(self, label):
        self.pause()
        decoded = boot_trace_capture.capture(self, self.state / ('trace-' + label))
        check(decoded['header']['online_mask'] == 15, 'trace did not record all four online CPUs')
        return decoded

    def trusted_kernel_mapping(self, virtual):
        pool = self.trusted_kernel_pool()
        # The kernel root is owned by kernel128, outside every user private
        # pool. Use that same authenticated pool for all four walk levels.
        return gui.lifecycle.fat.effective_mapping(pool[0], virtual,
            lambda pa: self.physical(pa, 4096, 'trusted snapshot kernel page table'), pool, 128)

    def wait(self, marker, timeout=180):
        deadline = time.monotonic()+timeout
        while marker not in self.raw:
            self.alive(); check(time.monotonic()<deadline, 'missing actual USB marker '+repr(marker)); time.sleep(.02)

    def capture_failure(self):
        report = super().capture_failure()
        try:
            # A controller failure can precede bootstrap's normal pool audit.
            self.refresh_processes()
            self.validate_private_pools()
            state = self.struct(13, 'xhci', 'drivers.xhci_service', 'STATE', 'usb.xhci_controller.State')
            info = self.layouts.part(state, 'usb.xhci_controller.State', 'info')
            caps = self.layouts.part(state, 'usb.xhci_controller.State', 'caps')
            setup = self.layouts.part(state, 'usb.xhci_controller.State', 'setup')
            driver = dict(info={n:self.number(info,'usb.xhci_controller.Info',n)
                                for n in ('ready','held','fault','phase','last_status')},
                          setup={n:self.number(setup,'usb.xhci_controller.Setup',n)
                                 for n in ('physical','bytes','physical_bits','epoch','lease_token')},
                          caps={n:self.number(caps,'usb.xhci_controller.Caps',n)
                                for n in ('operational','runtime','doorbells','ports','enabled_slots')})
            virtual = self.scalar(13,'xhci','drivers.xhci_service','VIRTUAL')
            capabilities = self.user(13,virtual,64,'failure actual USB capabilities')
            driver['capability_bytes'] = capabilities.hex()
            driver['caps']['interrupters'] = (int.from_bytes(capabilities[4:8],'little')>>8)&2047
            report['usb_driver'] = driver
            report['usb_authority'] = {n:self.kval('user.devices',n) for n in
                ('XHCI_ADMITTED','XHCI_SELECTED','XHCI_OWNER','XHCI_INCARNATION',
                 'XHCI_BINDING_TOKEN','XHCI_BINDING_GENERATION')}
            snapshot = self.authority_snapshot_storage()
            report['usb_authority']['snapshot_storage'] = snapshot
            for name, count, typename in (() if snapshot is None else (('XHCI_INTERRUPTS',driver['caps']['interrupters'],'drivers.xhci_authority.Interrupter'),
                                            ('XHCI_EXTENSIONS',64,'drivers.xhci_authority.Extension'))):
                check(0 < count <= 1024,'invalid failure snapshot array length')
                raw = self.authority_snapshot_bytes(snapshot,name,count*self.layouts.size(typename))
                (self.state/(name+'.bin')).write_bytes(raw)
                report['usb_authority'][name] = dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            if snapshot is not None:
                raw = self.authority_snapshot_bytes(snapshot,'XHCI_DMA_SNAPSHOT',131072)
                (self.state/'XHCI_DMA_SNAPSHOT.bin').write_bytes(raw)
                report['usb_authority']['dma_snapshot_sha256'] = hashlib.sha256(raw).hexdigest()
            bots = self.global_data(13,'xhci','drivers.xhci_service','BOT_STORAGE',3*64*8)
            report['usb_bot'] = []
            for index in range(3):
                raw = bots[index*512:index*512+self.layouts.size('usb.bot.State')]
                if self.number(raw,'usb.bot.State','held') != 1:continue
                record = {n:self.number(raw,'usb.bot.State',n) for n in
                          ('held','ready','fault','busy','recoverable','tag','blocks','block_bytes','actual','residue','status')}
                setup = self.layouts.part(raw,'usb.bot.State','setup')
                scratch = self.layouts.part(setup,'usb.bot.Setup','scratch')
                pointer = self.number(scratch,'usb.transport.Buffer','pointer')
                data = self.user(13,pointer,512,'failure actual completed BOT scratch')
                (self.state/('bot'+str(index)+'-scratch.bin')).write_bytes(data)
                record.update(index=index,scratch_sha256=hashlib.sha256(data).hexdigest(),
                              cbw_hex=data[:31].hex(),csw_hex=data[64:77].hex(),data_prefix_hex=data[128:160].hex())
                report['usb_bot'].append(record)
        except Exception as error:
            report['usb_snapshot_error'] = str(error)
        storage.write_json(self.state/'failure.json',report)
        return report

    def close(self):
        if self._usb_closed:return
        if self._gui_constructing and self.process is not None and not self._gui_failure_captured:
            self._gui_failure_captured = True
            for label, capture in (('failure_state', self.capture_failure),
                                   ('failure_screenshot', lambda:self.screenshot('constructor-failure'))):
                try:capture();self.evidence[label]=True
                except Exception as error:self.evidence[label+'_error']=str(error)
        try:
            settings.Guest.close(self)
        finally:
            if self.process is not None and self.process.poll() is None:
                self.process.kill(); self.process.wait(timeout=5)
            stopped = self.process is None or self.process.poll() is not None
            self.evidence.update(qemu_stopped=stopped, qemu_returncode=None if self.process is None else self.process.returncode)
            storage.write_json(self.state/'guest.json', self.evidence)
            self._usb_closed = stopped
            check(stopped, 'USB guest did not stop')

    def global_data(self, pid, image, module, name, size):
        self.refresh_processes()
        symbols = self.gui_symbols.setdefault(image, gui.read_elf_symbols(self.esp.parent/'services'/image/'program.elf'))
        bias = struct.unpack_from('<Q', self.processes, pid*gui.lifecycle.PROCESS_BYTES+224)[0]
        return self.user(pid, bias+symbols[storage.symbol(module,name)], size, module+'.'+name)

    def authority_snapshot_storage(self):
        symbol = storage.symbol('user.devices','XHCI_SNAPSHOT_BLOCK')
        if symbol not in self.symbols:
            return dict(dynamic=False)
        physical,virtual,pages = struct.unpack('<3Q',self.kernel(self.symbols[symbol],24,'held xHCI snapshot block'))
        pointers = {name:self.kval('user.devices',name) for name in
                    ('XHCI_INTERRUPTS','XHCI_EXTENSIONS','XHCI_DMA_SNAPSHOT')}
        if (physical,virtual,pages)==(0,0,0):
            check(not any(pointers.values()),'partially published xHCI snapshot pointers')
            return None
        plan = struct.unpack('<6Q',self.kernel(self.ksym('boot.service_memory','PLAN'),48,'owned service arena'))
        check(pages==43 and physical%4096==virtual%4096==0 and plan[4]<=physical
              and physical-plan[4]<=plan[5] and 43*4096<=plan[5]-(physical-plan[4])
              and virtual==0xffffd40000000000+physical-plan[4], 'xHCI snapshot escaped owned arena')
        offsets = dict(XHCI_INTERRUPTS=0,XHCI_EXTENSIONS=10*4096,XHCI_DMA_SNAPSHOT=11*4096)
        check(all(pointers[name]==virtual+offset for name,offset in offsets.items()),
              'xHCI trusted snapshot views overlap or escaped allocation')
        return dict(dynamic=True,physical=physical,virtual=virtual,pages=pages,offsets=offsets)

    def authority_snapshot_bytes(self, snapshot, name, size):
        if not snapshot['dynamic']:
            return self.kernel(self.ksym('user.devices',name),size,'trusted '+name)
        offset = snapshot['offsets'][name]
        check(0<size<=dict(XHCI_INTERRUPTS=10*4096,XHCI_EXTENSIONS=64*48,XHCI_DMA_SNAPSHOT=32*4096)[name],
              'xHCI snapshot read exceeds its own view')
        return self.physical(snapshot['physical']+offset,size,'trusted arena '+name)

    def scalar(self, pid, image, module, name):
        return int.from_bytes(self.global_data(pid,image,module,name,8),'little')

    def at(self, pid, address, type_name):
        return self.user(pid, address, self.layouts.size(type_name), 'actual '+type_name)

    def number(self, raw, type_name, name):return self.layouts.number(raw, type_name, name)

    def input_snapshot(self):
        self.pause()
        rpc = self.struct(4, 'input', 'drivers.input_service', 'USB_RPC', 'input.usb_rpc.State')
        sources = self.struct(4, 'input', 'drivers.input_service', 'SOURCES', 'input.sources.State')
        sequence = struct.unpack('<3Q', self.layouts.part(rpc, 'input.usb_rpc.State', 'sequence'))
        kind = struct.unpack('<3Q', self.layouts.part(rpc, 'input.usb_rpc.State', 'kind'))
        keysize = self.layouts.size('input.events.Keys')
        keys = self.layouts.part(sources, 'input.sources.State', 'keys')
        combined = self.layouts.part(sources, 'input.sources.State', 'combined')
        def held(raw,code):return bool(struct.unpack_from('<Q',raw,(code//64)*8)[0]&(1<<(code%64)))
        queue = struct.unpack('<2Q',self.user(4,0x54000000,16,'actual sole-writer GUI event queue'))
        check(queue[0]<64 and queue[1]<=64, 'actual GUI event ring is invalid')
        return dict(self_epoch=self.number(rpc,'input.usb_rpc.State','self_epoch'),
            peer_epoch=self.number(rpc,'input.usb_rpc.State','peer_epoch'),
            keyboard_sequence=sequence[1],keyboard_kind=kind[1],mouse_sequence=sequence[2],mouse_kind=kind[2],
            usb_a=held(keys[2*keysize:3*keysize],30),aggregate_a=held(combined,30),
            usb_keyboard_down=any(struct.unpack_from('<4Q',keys,2*keysize)),
            aggregate_keyboard_down=any(struct.unpack_from('<4Q',combined)),
            usb_left=held(keys[3*keysize:4*keysize],272),aggregate_left=held(combined,272),queue=list(queue))

    def await_keyboard(self, before, predicate, label):
        # A stable compositor frame does not acknowledge a key. Observe the
        # make/release sequence, both source states, queue drain and consumer.
        def delivered():
            current=self.input_snapshot()
            return (current['self_epoch']==before['self_epoch']
                    and current['keyboard_sequence']>=before['keyboard_sequence']+2
                    and not current['usb_keyboard_down'] and not current['aggregate_keyboard_down']
                    and current['queue'][1]==0 and predicate())
        self.until(delivered,label)
        return self.input_snapshot()

    def await_mouse(self, down, after_sequence):
        received={}
        def delivered():
            current=self.input_snapshot()
            buttons=self.number(self.windows(),'desktop.windows.State','buttons')
            received.update(source=current,buttons=buttons)
            return (current['mouse_sequence']>after_sequence and current['mouse_kind']==2
                    and current['usb_left']==down and current['aggregate_left']==down
                    and bool(buttons&1)==down and current['queue'][1]==0)
        self.until(delivered,'USB button '+('make' if down else 'release')+' and compositor consumption')
        return received['source'],received['buttons']

    def move(self,x,y):
        for _ in range(100):
            raw=self.windows();current=[self.number(raw,'desktop.windows.State',name) for name in ('pointer_x','pointer_y')]
            delta=[x-current[0],y-current[1]]
            if max(map(abs,delta))<=4:return
            self.resume();self.qmp.request('input-send-event',dict(events=[dict(type='rel',data=dict(axis=a,value=max(-32,min(32,v)))) for a,v in zip(('x','y'),delta) if v]))
            self.settle()
        raise ValueError('actual USB relative pointer failed to reach target')

    def hid(self):
        mice=self.qmp.request('query-mice')
        selected=select_usb_mouse(mice)
        self.qmp.request('human-monitor-command',dict(**{'command-line':'mouse_set '+str(selected['index'])}))
        activated=self.qmp.request('query-mice');active=select_usb_mouse(activated)
        check(active['index']==selected['index'] and active['current'] is True,'QMP did not activate the USB relative mouse')
        self.focus(1); cleared=self.input_snapshot();self.key('ctrl','u')
        self.await_keyboard(cleared,lambda:self.model_text(1,'input')==b'', 'cleared real terminal input and control release')
        before=self.input_snapshot(); self.key('a')
        self.await_keyboard(before,lambda:self.model_text(1,'input') in (b'a',b'aa'), 'USB keyboard character and release')
        after=self.input_snapshot(); text=self.model_text(1,'input');validate_keyboard(before,after,text,self.usb_only)
        cleared=self.input_snapshot();self.key('ctrl','u')
        self.await_keyboard(cleared,lambda:self.model_text(1,'input')==b'', 'cleared physical character and control release')
        mouse_before=self.input_snapshot();self.button(True)
        pressed,window_pressed=self.await_mouse(True,mouse_before['mouse_sequence']);self.button(False)
        released,window_released=self.await_mouse(False,pressed['mouse_sequence'])
        validate_mouse(mouse_before,pressed,released,window_pressed,window_released)
        record=dict(before=before,after=after,character=text.decode(),mouse_before=mouse_before,
                    mouse_pressed=pressed,mouse_released=released,real_gui_character_consumption=True,
                    actual_compositor_buttons=[window_pressed,window_released],
                    qmp_mouse_inventory=mice,qmp_mouse_activated=activated,no_uart_input_for_hid=True)
        if self.usb_only:record['console']=self.usb_console()
        return record

    def usb_console(self):
        ring=lambda:struct.unpack('<3Q',self.user(4,0x54100000,24,'actual input console ring'))
        initial=ring();before=self.input_snapshot();start=len(self.raw);self.key('f12')
        self.await_keyboard(before,lambda:b'DONGOS_INPUT_CONSOLE_ON\r\n' in self.raw[start:], 'fresh USB console ON and F12 release')
        command_start=len(self.raw)
        for index,code in enumerate(('p','w','d','ret'),1):
            before=self.input_snapshot();self.key(code)
            def consumed():
                current=ring()
                check(current[2]==initial[2]==0,'USB console dropped a character')
                check(current[1]<=initial[1]+index,'USB console received duplicate characters')
                return current[0]==current[1]==initial[1]+index
            self.await_keyboard(before,consumed,'USB console consumed key '+code)
        self.until(lambda:usb_console_response(bytes(self.raw[command_start:])) is not None,
                   'fresh USB-only physical pwd response')
        response=usb_console_response(bytes(self.raw[command_start:]))
        check(response is not None,'USB-only physical characters did not execute pwd')
        before=self.input_snapshot();start=len(self.raw);self.key('f12')
        self.await_keyboard(before,lambda:b'DONGOS_INPUT_CONSOLE_OFF\r\n' in self.raw[start:], 'fresh USB console OFF and F12 release')
        final=ring();check(final[0]==final[1] and final[0]-initial[0]==4 and final[2]==initial[2]==0,
                          'USB-only console did not consume exactly four QMP characters')
        return dict(ring_before=initial,ring_after=final,response=response,exact_qmp_character_consumption=True)

    def block_snapshot(self, capacity, flush=False):
        catalog=self.catalog();epoch=catalog['incarnations'][13]
        check(catalog['slots'][13]==13 and catalog['snapshots'][13]['state']==2,'reserved xHCI is not READY')
        block_raw=self.struct(2,'block','drivers.block_service','USB','drivers.usb_block_proxy.State')
        block={name:self.number(block_raw,'drivers.usb_block_proxy.State',name) for name in ('ready','capacity','readonly','completed')}
        block['backend']=self.scalar(2,'block','drivers.block_service','BACKEND')
        proxy_raw=self.struct(13,'xhci','drivers.xhci_service','PROXY','usb.block_proxy.State')
        proxy={name:self.number(proxy_raw,'usb.block_proxy.State',name) for name in ('ready','busy','epoch','completed','storage','channel')}
        state=self.struct(13,'xhci','drivers.xhci_service','STATE','usb.xhci_controller.State')
        info=self.layouts.part(state,'usb.xhci_controller.State','info');setup=self.layouts.part(state,'usb.xhci_controller.State','setup')
        controller={name:self.number(info,'usb.xhci_controller.Info',name) for name in ('ready','held','fault','phase')}
        controller['epoch']=self.number(setup,'usb.xhci_controller.Setup','epoch')
        validate_primary(block,proxy,controller,epoch,capacity,self.kval('user.devices','SELECTED_KIND'))
        check(proxy['channel']==0x51000000 and self.scalar(13,'xhci','drivers.xhci_service','ATTEMPTED')==3
              and self.scalar(13,'xhci','drivers.xhci_service','ENUMERATED')==3,'wrong direct-root device count/channel')
        enumerations=self.global_data(13,'xhci','drivers.xhci_service','ENUMERATIONS',3*223*8)
        devices=[]
        for index,kind in enumerate((3,1,2)):
            item=enumerations[index*223*8:(index+1)*223*8]
            itemsetup=self.layouts.part(item,'usb.enumerate.State','setup')
            configuration=self.layouts.part(item,'usb.enumerate.State','configuration')
            binding=self.layouts.part(configuration,'usb.descriptor.Configuration','bindings')[:self.layouts.size('usb.descriptor.Binding')]
            check(self.number(item,'usb.enumerate.State','held')==self.number(item,'usb.enumerate.State','ready')==1
                  and self.number(item,'usb.enumerate.State','fault')==0
                  and self.number(itemsetup,'usb.enumerate.Setup','port')==index+1
                  and self.number(configuration,'usb.descriptor.Configuration','count')==1
                  and self.number(binding,'usb.descriptor.Binding','kind')==kind,'driver enumerated wrong direct-root port/interface')
            devices.append(dict(port=index+1,kind=kind,slot=self.number(item,'usb.enumerate.State','slot'),
                                physical=self.number(itemsetup,'usb.enumerate.Setup','physical')))
        check(len({item['slot'] for item in devices})==3,'enumerated USB devices share one hardware slot')
        check(self.kval('user.devices','XHCI_OWNER')==(14<<32)|epoch
              and self.kval('user.devices','XHCI_INCARNATION')==epoch,'kernel xHCI owner/incarnation differs')
        input_state=self.input_snapshot()
        check(input_state['self_epoch']==catalog['incarnations'][4] and input_state['peer_epoch'] in (0,epoch),
              'input accepted another driver/input incarnation')
        token,physical,pointer,length=struct.unpack('<4Q',self.kernel(self.ksym('user.devices','XHCI_LEASE'),32,'actual xHCI private DMA grant'))
        check((physical,pointer,length)==tuple(self.number(setup,'usb.xhci_controller.Setup',n) for n in ('physical','pointer','bytes'))
              and token==self.number(setup,'usb.xhci_controller.Setup','lease_token') and length==131072,'actual kernel/user xHCI DMA lease differs')
        caps=self.layouts.part(state,'usb.xhci_controller.State','caps')
        enabled=self.number(caps,'usb.xhci_controller.Caps','enabled_slots')
        check(3<=enabled<=8,'actual enabled USB slot count differs')
        dcbaa=struct.unpack('<'+str(enabled+1)+'Q',self.physical(physical,(enabled+1)*8,'actual DMA DCBAA'))
        validate_enumeration(devices,self.number(caps,'usb.xhci_controller.Caps','ports'),
            struct.unpack('<32Q',self.layouts.part(caps,'usb.xhci_controller.Caps','protocols')),dcbaa)
        isolation=[]
        for pid,root in enumerate(self.roots):
            if not root or pid==13:continue
            isolation.append(gui.lifecycle.nvme.verify_no_user_dma_alias(root,
                lambda pa:self.physical(pa,4096,'USB full DMA isolation walk'),physical,length,
                self.trusted_kernel_pool(),self.private_pages(root)))
        for offset in range(0,length,4096):
            entry=self.pte(self.roots[13],pointer+offset)
            check(entry&gui.MASK==physical+offset and entry&(gui.NF|0x19f)==gui.NF|7,'USB DMA lost private RW/NX/WB')
        boot_input=int.from_bytes(self.global_data(4,'input','drivers.input_service','PS2_ACTIVE',1),'little')
        interrupts=int.from_bytes(self.global_data(4,'input','drivers.input_service','INTERRUPTS',1),'little')
        check(boot_input==int(not self.usb_only) and (not self.usb_only or interrupts==0),'actual PS2/USB-only mode differs')
        # The persistent FS/block channel has exactly these three owners.
        for offset in range(0,65536,4096):
            pair=[self.mapping(root,0x51000000+offset) if root else dict(effective_user=False) for root in self.roots]
            check(all(pair[pid]['effective_user'] and pair[pid]['effective_writable'] and pair[pid]['effective_nx']
                      and pair[pid]['leaf_bytes']==4096 for pid in (1,2,13))
                  and len({pair[pid]['physical'] for pid in (1,2,13)})==1
                  and all(not item['effective_user'] for pid,item in enumerate(pair) if pid not in (1,2,13)),
                  'actual USB block channel is not limited to FS/block/xHCI')
        result=dict(block=block,proxy=proxy,controller=controller,lease=[token,physical,pointer,length],devices=devices,dcbaa=dcbaa,
                    complete_dma_isolation=isolation,actual_ps2_active=bool(boot_input),actual_input_interrupts=bool(interrupts))
        snapshot=self.authority_snapshot_storage()
        if storage.symbol('user.devices','XHCI_SNAPSHOT_BLOCK') in self.symbols:
            check(snapshot is not None and snapshot['dynamic'],'enabled xHCI has no trusted held snapshot')
            check(snapshot['physical']+43*4096<=physical or physical+length<=snapshot['physical'],
                  'trusted xHCI snapshot overlaps driver DMA lease')
            for offset in range(0,43*4096,4096):
                mapping=self.trusted_kernel_mapping(snapshot['virtual']+offset)
                check(mapping['physical']==snapshot['physical']+offset and mapping['leaf_bytes']==4096
                      and not mapping['effective_user'] and mapping['effective_writable'] and mapping['effective_nx']
                      and mapping['leaf_entry']&0x198==0,
                      'trusted xHCI snapshot lacks private supervisor RW/NX mapping')
            for root in self.roots:
                if root:
                    gui.lifecycle.nvme.verify_no_user_dma_alias(root,
                        lambda pa:self.physical(pa,4096,'trusted snapshot complete USER isolation'),
                        snapshot['physical'],43*4096,self.trusted_kernel_pool(),self.private_pages(root))
            result['trusted_snapshot']=dict(**snapshot,all_user_roots_excluded=True)
        if flush:
            bot=self.at(13,proxy['storage'],'usb.bot.State');botsetup=self.layouts.part(bot,'usb.bot.State','setup')
            scratch=self.layouts.part(botsetup,'usb.bot.Setup','scratch');address=self.number(scratch,'usb.transport.Buffer','pointer')
            check(self.number(bot,'usb.bot.State','ready')==self.number(bot,'usb.bot.State','held')==1
                  and self.number(bot,'usb.bot.State','fault')==self.number(bot,'usb.bot.State','busy')==0
                  and self.number(bot,'usb.bot.State','blocks')==capacity and self.number(bot,'usb.bot.State','block_bytes')==512
                  and self.number(botsetup,'usb.bot.Setup','slot')==devices[0]['slot'],'BOT flush medium/fault/pending state differs')
            check(pointer<=address<=pointer+length-77 and self.number(scratch,'usb.transport.Buffer','bytes')>=77
                  and self.number(scratch,'usb.transport.Buffer','physical')==physical+address-pointer,
                  'BOT CBW/CSW are not in the independently verified private DMA lease')
            result['flush']=validate_flush(self.user(13,address,31,'actual DMA CBW'),self.user(13,address+64,13,'actual DMA CSW'),
                *(self.number(bot,'usb.bot.State',n) for n in ('tag','actual','residue','status')))
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp',type=Path)
    parser.add_argument('--case',choices=('coexist','usb-only','both'),default='both')
    parser.add_argument('--require-pcid',action='store_true')
    parser.add_argument('--startup-timeout',type=int,default=180)
    parser.add_argument('--selftest',action='store_true')
    args=parser.parse_args()
    if args.selftest:
        import unittest
        from tests import test_usb_runtime_qemu
        return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_usb_runtime_qemu)).wasSuccessful() else 1
    if args.reuse_esp is None:parser.error('--reuse-esp required; no build is performed')
    check(1<=args.startup_timeout<=600,'invalid startup deadline')
    esp=args.reuse_esp.resolve();out=ROOT/'build/test/usb-runtime/qemu'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
    cases=('coexist','usb-only') if args.case=='both' else (args.case,)
    result=dict(passed=False,cases=[],actual_qemu_boots=0,full_os_build_executed=False,
                no_guest_memory_or_register_writes=True,no_physical_devices=True,no_host_payload_injection=True)
    guest=None
    names=('tests/run_usb_runtime_qemu.py','tests/run_gui_clients_qemu.py','tests/run_process_lifecycle_qemu.py',
           'tests/run_desktop_settings_qemu.py','tests/run_fat_paths_qemu.py','tests/fat_paths_oracle.py','tools/build.py',
           'tests/boot_trace_capture.py','tests/boot_trace_oracle.py','tests/run_clock_calibration_qemu.py')
    fingerprints={n:settings.sha(ROOT/n) for n in names}
    try:
        verify_build(esp);build_sha=settings.sha(esp.parent/'build-inputs.json')
        layouts,identity=checked_layouts(esp);result['completed_source_identity']=identity
        kernel_layout=gui.lifecycle.nvme.check_kernel_memory_layout(esp)
        for case in cases:
            directory=out/case;directory.mkdir();disk=directory/'usb-data.img';geometry=create(disk,64)
            record=dict(case=case,geometry=geometry,initial=oracle.inspect(disk,files={'/README.TXT':SEED},exact_namespace=True),boots=[])
            result['cases'].append(record)
            for boot in range(2):
                guest=UsbGuest(esp,disk,directory/('boot-'+str(boot+1)),kernel_layout,layouts,case=='usb-only',args.startup_timeout)
                evidence=dict(gui=guest.smoke(case+'-'+str(boot+1)),before=guest.block_snapshot(geometry['total']),hid=guest.hid())
                evidence['boot_trace'] = guest.trace_snapshot('before-storage')
                if args.require_pcid:check(evidence['gui']['pcid']['enabled'] and evidence['gui']['pcid']['retained']>0,'actual PCID retention required')
                commands=[]
                if boot==0:
                    for command,expected in [('mkdir '+gui.lifecycle.fat.quote(DIRECTORY),b'MKDIR OK\r\n'),
                        ('write '+gui.lifecycle.fat.quote(DOCUMENT)+' '+FIRST.decode(),b'WRITE OK\r\n'),
                        ('append '+gui.lifecycle.fat.quote(DOCUMENT)+' '+TAIL.decode(),b'APPEND OK\r\n'),
                        ('write '+gui.lifecycle.fat.quote(REMOVED)+' remove-me',b'WRITE OK\r\n'),
                        ('rm '+gui.lifecycle.fat.quote(REMOVED),b'RM OK\r\n')]:
                        commands.append(guest.shell(command,exact=expected))
                    commands.append(guest.shell('sync',exact=b'SYNC OK\r\n'))
                    evidence['durable_flush']=guest.block_snapshot(geometry['total'],flush=True)
                    check(evidence['durable_flush']['block']['completed']>evidence['before']['block']['completed'],'guest write/FLUSH caused no actual USB RPC completions')
                commands.append(guest.shell('cat '+gui.lifecycle.fat.quote(DOCUMENT),exact=PAYLOAD+b'\r\n'))
                evidence.update(commands=commands,actual_shell_same_disk_readback=True,evidence=guest.evidence)
                evidence['boot_trace_after_storage'] = guest.trace_snapshot('after-storage')
                check((guest.state/'trace-before-storage/trace.bin').read_bytes()
                      == (guest.state/'trace-after-storage/trace.bin').read_bytes(),
                      'sealed boot trace changed during actual storage/HID service activity')
                guest.screenshot('usb-runtime-final');guest.close();guest=None
                evidence['raw_disk']=disk_evidence(disk);record['boots'].append(evidence)
                if boot:check(record['boots'][0]['raw_disk']['image_sha256']==evidence['raw_disk']['image_sha256'],'read-only second boot changed durable USB disk')
        verify_build(esp);check(settings.sha(esp.parent/'build-inputs.json')==build_sha,'completed build identity changed')
        result['passed']=True
    except Exception as error:
        result['error']=type(error).__name__+': '+str(error)
        if guest is not None:
            for label,action in (('failure_state',guest.capture_failure),('failure_screenshot',lambda:guest.screenshot('failure'))):
                try:action();result[label]=True
                except Exception as nested:result[label+'_error']=str(nested)
    finally:
        if guest is not None:
            try:guest.close()
            except Exception as error:result.update(passed=False,cleanup_error=str(error))
        manifests=[json.loads(p.read_text()) for p in out.glob('*/boot-*/guest.json')]
        result['actual_qemu_boots']=sum(r.get('actual_qemu_executed') is True for r in manifests)
        result['all_started_guests_stopped']=all(not r.get('actual_qemu_executed') or r.get('qemu_stopped') for r in manifests)
        result['runner_inputs_unchanged']=all(settings.sha(ROOT/n)==h for n,h in fingerprints.items())
        if result['passed'] and (result['actual_qemu_boots']!=2*len(cases) or not result['all_started_guests_stopped'] or not result['runner_inputs_unchanged']):
            result.update(passed=False,error='actual boots, cleanup or runner fingerprints differ')
        if result['passed']:
            try:result.update(validate_boots(manifests,2*len(cases)))
            except ValueError as error:result.update(passed=False,error=str(error))
        storage.write_json(out/'result.json',result)
    print('Actual USB runtime','PASS' if result['passed'] else 'FAIL',out,result.get('error',''),flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
