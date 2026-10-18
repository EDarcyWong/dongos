"""Independent host controls for USB runtime gate. Starts no virtual machine."""
from copy import deepcopy
from pathlib import Path
import json
import struct
import tempfile
import unittest
from unittest.mock import patch

from tests import run_usb_runtime_qemu as gate
from tests.test_fat_paths_qemu import short, lfn_entries


def base_command():
    return ['qemu','-machine','q35','-drive','if=pflash,readonly=on,file=code.fd',
            '-drive','if=pflash,file=vars.fd','-drive','format=raw,file=fat:rw:esp',
            '-serial','file:log','-device','isa-debug-exit,iobase=0xf4,iosize=0x04']


def primary():
    return (dict(backend=4,ready=1,readonly=0,capacity=131072,completed=19),
            dict(ready=1,busy=0,epoch=3,completed=19),
            dict(ready=1,held=1,fault=0,phase=8,epoch=3),3,131072,0)


def keyboard():
    before=dict(self_epoch=1,peer_epoch=3,keyboard_sequence=7)
    after=dict(self_epoch=1,peer_epoch=3,keyboard_sequence=9,keyboard_kind=1,usb_a=False,aggregate_a=False)
    return before,after


def mouse():
    before=dict(mouse_sequence=3)
    pressed=dict(mouse_sequence=4,mouse_kind=2,usb_left=True,aggregate_left=True)
    released=dict(mouse_sequence=5,mouse_kind=2,usb_left=False,aggregate_left=False,queue=[0,0])
    return before,pressed,released,1,0


class UsbRuntimeHostControls(unittest.TestCase):
    def test_snapshot_kernel_walk_accepts_kernel_root_without_private_root_lookup(self):
        guest=object.__new__(gate.UsbGuest);root=0x200000;va=0xffffd40000020000;physical=0x30020000
        tables={root+i*4096:bytearray(4096) for i in range(4)}
        for i,shift in enumerate((39,30,21,12)):
            entry=(root+(i+1)*4096)|7 if i<3 else physical|3|(1<<63)
            struct.pack_into('<Q',tables[root+i*4096],((va>>shift)&511)*8,entry)
        guest.trusted_kernel_pool=lambda:(root,128)
        guest.private_pages=lambda value:(_ for _ in ()).throw(AssertionError('kernel root queried as private'))
        guest.physical=lambda pa,n,role:bytes(tables[pa])
        result=guest.trusted_kernel_mapping(va)
        self.assertEqual(physical,result['physical']);self.assertEqual(4096,result['leaf_bytes'])
        self.assertFalse(result['effective_user']);self.assertTrue(result['effective_writable']);self.assertTrue(result['effective_nx'])
        # The walk must still reject a child table escaping the owned kernel pool.
        struct.pack_into('<Q',tables[root],((va>>39)&511)*8,0x900000|7)
        with self.assertRaises(ValueError):guest.trusted_kernel_mapping(va)

    def test_trusted_snapshot_uses_only_complete_owned_arena_block_and_exact_views(self):
        guest=object.__new__(gate.UsbGuest)
        guest.symbols={gate.storage.symbol('user.devices','XHCI_SNAPSHOT_BLOCK'):11,
                       gate.storage.symbol('boot.service_memory','PLAN'):22}
        arena_pa=0x20000000;physical=arena_pa+0x20000;virtual=0xffffd40000020000
        block=[physical,virtual,43];plan=[0,0,0,0,arena_pa,0x100000]
        pointers=dict(XHCI_INTERRUPTS=virtual,XHCI_EXTENSIONS=virtual+40960,XHCI_DMA_SNAPSHOT=virtual+45056)
        guest.kernel=lambda va,n,role:struct.pack('<3Q',*block) if va==11 else struct.pack('<6Q',*plan)
        guest.kval=lambda module,name:pointers[name]
        reads=[]
        guest.physical=lambda pa,n,role:(reads.append((pa,n)) or b'x'*n)
        result=guest.authority_snapshot_storage()
        self.assertEqual(physical,result['physical']);self.assertEqual(43,result['pages'])
        self.assertEqual(b'x'*131072,guest.authority_snapshot_bytes(result,'XHCI_DMA_SNAPSHOT',131072))
        self.assertEqual([(physical+45056,131072)],reads)
        with self.assertRaises(ValueError):guest.authority_snapshot_bytes(result,'XHCI_DMA_SNAPSHOT',131073)
        for index,value in ((0,arena_pa-4096),(0,arena_pa+0x100000),(0,physical+1),(1,virtual+4096),(1,virtual+8),(2,42)):
            saved=block[index];block[index]=value
            with self.subTest(index=index,value=value),self.assertRaises(ValueError):guest.authority_snapshot_storage()
            block[index]=saved
        for name in pointers:
            saved=pointers[name];pointers[name]+=8
            with self.subTest(name=name),self.assertRaises(ValueError):guest.authority_snapshot_storage()
            pointers[name]=saved
        block[:]=[0,0,0]
        with self.assertRaises(ValueError):guest.authority_snapshot_storage()
        pointers={key:0 for key in pointers}
        self.assertIsNone(guest.authority_snapshot_storage())
        guest.symbols={}
        self.assertEqual(dict(dynamic=False),guest.authority_snapshot_storage())

    def test_console_echo_survives_atomic_hid_logs_between_characters(self):
        lines = [b'usb_hid_source=0x0000000000000002\r\n',
                 b'usb_hid_kind=0x0000000000000001\r\n',
                 b'usb_hid_bytes=0x0000000000000008\r\n',
                 b'usb_hid_generation=0x000000000000000e\r\n',
                 b'usb_hid_raw=0x0000000000000000\r\n',
                 b'DONGOS_XHCI_HID_REPORT\r\n']
        for split in range(7):
            segment = b'p' + b''.join(lines[:split]) + b'w' + b''.join(lines[split:]) + b'd\r\n/\r\n> '
            with self.subTest(split=split):
                result = gate.usb_console_response(segment)
                self.assertEqual('2f0d0a', result['response_hex'])
                self.assertTrue(result['complete_echo_and_new_prompt_verified'])
                self.assertEqual([dict(source=2, kind=1, bytes=8, generation=14, raw=0)],
                                 result['excluded_complete_hid_records'])
        for end in range(1,6):
            self.assertIsNone(gate.usb_console_response(b'p'+b''.join(lines[:end])))
        # Removing the required echo/output is never repaired by telemetry.
        self.assertIsNone(gate.usb_console_response(b''.join(lines)+b'd\r\n/\r\n> '))
        self.assertIsNone(gate.usb_console_response(b'pwd\r\n'+b''.join(lines)+b'/\r\n'))
        for bad in (b'wrong\r\n', b'ERROR 0x0000000000000001\r\n', b'PANIC\r\n',
                    b'usb_hid_raw=0xINVALID\r\n'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                gate.usb_console_response(b'pwd\r\n'+b''.join(lines)+bad+b'/\r\n> ')
        for old,new in ((b'kind=0x0000000000000001',b'kind=0x0000000000000002'),
                        (b'generation=0x000000000000000e',b'generation=0x0000000000000011'),
                        (b'bytes=0x0000000000000008',b'bytes=0x0000000000000003')):
            with self.subTest(new=new), self.assertRaises(ValueError):
                gate.usb_console_response((b'pwd\r\n'+b''.join(lines)+b'/\r\n> ').replace(old,new))
        with self.assertRaises(ValueError):
            gate.usb_console_response(b'pwd\r\n'+lines[1]+lines[0]+b''.join(lines[2:])+b'/\r\n> ')
        with self.assertRaises(ValueError):
            gate.usb_console_response(b'pwd\r\n'+b''.join(lines)+b'/\r\npwd\r\n/\r\n> ')

    def test_key_receipt_waits_for_release_queue_and_real_consumer(self):
        guest=object.__new__(gate.UsbGuest);guest.phase=0;sent=[]
        before=dict(self_epoch=1,keyboard_sequence=10)
        states=[dict(self_epoch=1,keyboard_sequence=10,usb_keyboard_down=True,aggregate_keyboard_down=True,queue=[0,2]),
                dict(self_epoch=1,keyboard_sequence=12,usb_keyboard_down=True,aggregate_keyboard_down=True,queue=[0,0]),
                dict(self_epoch=1,keyboard_sequence=12,usb_keyboard_down=False,aggregate_keyboard_down=True,queue=[0,0]),
                dict(self_epoch=1,keyboard_sequence=12,usb_keyboard_down=False,aggregate_keyboard_down=False,queue=[0,1]),
                dict(self_epoch=1,keyboard_sequence=12,usb_keyboard_down=False,aggregate_keyboard_down=False,queue=[0,0])]
        guest.input_snapshot=lambda:states[min(guest.phase,4)]
        def until(predicate,label):
            for stage in range(6):
                guest.phase=stage
                if predicate():return
            raise ValueError('missing receipt '+label)
        guest.until=until;guest.key=lambda *keys:sent.append(keys)
        guest.key('a')
        guest.await_keyboard(before,lambda:guest.phase==5,'one physical key')
        self.assertEqual(5,guest.phase);self.assertEqual([('a',)],sent)
        states[4]['aggregate_keyboard_down']=True
        with self.assertRaises(ValueError):guest.await_keyboard(before,lambda:True,'missing release')
        self.assertEqual([('a',)],sent)

    def test_mouse_receipt_waits_for_window_and_shared_ring_without_reinjecting(self):
        guest=object.__new__(gate.UsbGuest);guest.phase=0;sent=[]
        guest.number=lambda state,typename,name:state
        guest.windows=lambda:0 if guest.phase<2 else 1
        guest.input_snapshot=lambda:dict(mouse_sequence=4,mouse_kind=2,usb_left=True,
            aggregate_left=True,queue=[0,int(guest.phase<3)])
        def until(predicate,label):
            for stage in range(5):
                guest.phase=stage
                if predicate():return
            raise ValueError(label)
        guest.until=until;guest.button=lambda down:sent.append(down)
        guest.button(True);source,buttons=guest.await_mouse(True,3)
        self.assertEqual(3,guest.phase);self.assertEqual(0,source['queue'][1]);self.assertEqual(1,buttons)
        self.assertEqual([True],sent)
        guest.windows=lambda:0
        with self.assertRaises(ValueError):guest.await_mouse(True,3)
        self.assertEqual([True],sent)

    def test_usb_console_delayed_real_receipts_once_and_missing_ack_fail_closed(self):
        class Console(gate.UsbGuest):
            def __init__(self,stall=None):
                # Old markers must never count as acknowledgement of a new key.
                self.raw=bytearray(b'DONGOS_INPUT_CONSOLE_ON\r\nDONGOS_INPUT_CONSOLE_OFF\r\n')
                self.sent=[];self.phase=4;self.sequence=10;self.head=self.tail=0
                self.stall=stall;self.waits=[];self.pending=None;self.toggles=0
            def key(self,*keys):
                self.sent.append(keys);self.pending=keys[0];self.phase=0
                if self.pending=='f12':self.toggles+=1
            def input_snapshot(self):
                return dict(self_epoch=1,keyboard_sequence=self.sequence,
                    usb_keyboard_down=self.phase<2 or self.stall=='release',
                    aggregate_keyboard_down=self.phase<2,queue=[0,0])
            def user(self,*args):return struct.pack('<3Q',self.head,self.tail,0)
            def until(self,predicate,label,timeout=30):
                for _ in range(7):
                    self.phase+=1
                    if self.phase==1:self.sequence+=2
                    if self.phase==2 and self.pending in ('p','w','d','ret') and self.stall!='ring':
                        self.head+=1;self.tail+=1
                    if self.phase==3 and self.pending=='f12':
                        name='ON' if self.toggles==1 else 'OFF'
                        if self.stall!=name:self.raw.extend(('DONGOS_INPUT_CONSOLE_'+name+'\r\n').encode())
                    if self.phase==4 and self.pending=='ret' and self.stall!='response':
                        self.raw.extend(b'pwd\r\n/\r\n> ')
                    if predicate():self.waits.append((label,self.phase));return
                raise ValueError('missing actual receipt '+label)
        guest=Console();record=guest.usb_console()
        self.assertEqual([('f12',),('p',),('w',),('d',),('ret',),('f12',)],guest.sent)
        self.assertEqual([4,4,0],list(record['ring_after']))
        self.assertTrue(record['response']['complete_echo_and_new_prompt_verified'])
        self.assertEqual(3,guest.waits[0][1]);self.assertEqual(3,guest.waits[-1][1])
        for stall in ('ON','OFF','release','ring','response'):
            guest=Console(stall)
            with self.subTest(stall=stall),self.assertRaisesRegex(ValueError,'missing actual receipt'):
                guest.usb_console()
            self.assertLessEqual(guest.sent.count(('f12',)),2)
            for key in ('p','w','d','ret'):self.assertLessEqual(guest.sent.count((key,)),1)

    def test_exact_usb_ports_no_sata_and_both_input_modes(self):
        original=base_command()
        for usb_only in (False,True):
            command=gate.usb_command(original,Path('ordinary,64MiB.img'),usb_only)
            self.assertEqual('q35,sata=off'+(',i8042=off' if usb_only else ''),command[command.index('-machine')+1])
            self.assertIn('qemu-xhci,id=usbhost,addr=0x5,p2=4,p3=0',command)
            devices=[v for i,v in enumerate(command) if i and command[i-1]=='-device']
            self.assertEqual(4,len([v for v in devices if v.startswith(('usb-storage,','usb-kbd,','usb-mouse,'))]))
            for port,name in ((1,'usbdisk'),(2,'usbkeyboard'),(3,'usbmouse'),(4,'usbefi')):
                matches=[v for v in devices if 'id='+name+',' in v]
                self.assertEqual(1,len(matches));self.assertIn('port='+str(port),matches[0])
            self.assertIn('if=none,id=usbefi,format=raw,file=fat:rw:esp',command)
            self.assertIn('ordinary,,64MiB.img',' '.join(command))
            self.assertFalse(any(v.startswith(('virtio-blk','nvme,')) for v in devices))
        self.assertEqual(base_command(),original)

    def test_existing_pci_storage_or_duplicate_drive_cannot_be_hidden_as_usb(self):
        variants=[]
        for device in ('nvme,drive=data','virtio-blk-pci,drive=data','ich9-ahci,id=sata',
                       'qemu-xhci,id=other','usb-host,hostbus=1','usb-storage,drive=data'):
            variants.append(base_command()+['-device',device])
        variants.extend((base_command()+['-drive','if=none,id=data,file=data.img'],
                         base_command()+['-drive','format=raw,file=fat:rw:extra']))
        wrong=base_command();wrong[2]='q35,sata=off';variants.append(wrong)
        wrong=base_command();del wrong[7:9];variants.append(wrong)
        for command in variants:
            with self.subTest(command=command),self.assertRaises(ValueError):gate.usb_command(command,Path('image'),True)

    def test_actual_usb_primary_requires_healthy_matching_medium_and_epoch(self):
        gate.validate_primary(*primary())
        for index,field,value in ((0,'backend',3),(0,'ready',0),(0,'readonly',1),(0,'capacity',65536),
                (0,'completed',18),(1,'ready',0),(1,'busy',1),(1,'epoch',2),(1,'completed',20),
                (2,'ready',0),(2,'held',0),(2,'fault',1),(2,'phase',7),(2,'epoch',2)):
            args=list(primary());args[index][field]=value
            with self.subTest(index=index,field=field),self.assertRaises(ValueError):gate.validate_primary(*args)
        args=list(primary());args[-1]=3
        with self.assertRaises(ValueError):gate.validate_primary(*args)

    def test_flush_requires_raw_dma_cbw_csw_not_software_success_alone(self):
        cbw=bytearray(31);struct.pack_into('<II',cbw,0,0x43425355,19);cbw[14:16]=bytes([10,0x35])
        csw=struct.pack('<IIIB',0x53425355,19,0,0)
        gate.validate_flush(cbw,csw,19,0,0,0)
        for offset in range(31):
            bad=bytearray(cbw);bad[offset]^=1
            with self.subTest(cbw=offset),self.assertRaises(ValueError):gate.validate_flush(bad,csw,19,0,0,0)
        for offset in range(13):
            bad=bytearray(csw);bad[offset]^=1
            with self.subTest(csw=offset),self.assertRaises(ValueError):gate.validate_flush(cbw,bad,19,0,0,0)
        for tag,actual,residue,status in ((0,0,0,0),(20,0,0,0),(19,1,0,0),(19,0,1,0),(19,0,0,1)):
            with self.assertRaises(ValueError):gate.validate_flush(cbw,csw,tag,actual,residue,status)

    def test_keyboard_must_reach_real_gui_and_release_usb_source(self):
        before,after=keyboard();gate.validate_keyboard(before,after,b'a',True)
        gate.validate_keyboard(before,after,b'aa',False)
        for usb_only,text in ((True,b'aa'),(True,b''),(False,b''),(False,b'aaa')):
            with self.assertRaises(ValueError):gate.validate_keyboard(before,after,text,usb_only)
        for field,value in (('self_epoch',2),('peer_epoch',2),('keyboard_sequence',8),('keyboard_kind',2),('usb_a',True),('aggregate_a',True)):
            bad=deepcopy(after);bad[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):gate.validate_keyboard(before,bad,b'a',True)

    def test_mouse_usb_state_without_compositor_consumption_cannot_pass(self):
        gate.validate_mouse(*mouse())
        for index,field,value in ((1,'mouse_sequence',3),(1,'usb_left',False),(1,'aggregate_left',False),
                                  (2,'mouse_sequence',4),(2,'usb_left',True),(2,'aggregate_left',True),
                                  (2,'mouse_kind',1),(2,'queue',[0,1])):
            args=list(mouse());args[index][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):gate.validate_mouse(*args)
        for pressed,released in ((0,0),(1,1)):
            args=list(mouse());args[-2:]=[pressed,released]
            with self.assertRaises(ValueError):gate.validate_mouse(*args)

    def test_actual_dcbaa_proves_only_first_three_ports_not_efi_four(self):
        devices=[dict(port=i+1,kind=kind,slot=i+1,physical=0x204000+i*32768) for i,kind in enumerate((3,1,2))]
        dcbaa=[0]+[d['physical']+4096 for d in devices]+[0]*5
        protocols=[2]*4+[0]*28
        gate.validate_enumeration(devices,4,protocols,dcbaa)
        for slot,value in ((0,0x200000),(1,0),(4,0x300000),(8,0x400000)):
            bad=list(dcbaa);bad[slot]=value
            with self.subTest(slot=slot),self.assertRaises(ValueError):gate.validate_enumeration(devices,4,protocols,bad)
        for index,field,value in ((0,'port',4),(1,'kind',3),(2,'slot',2),(0,'physical',0x205000)):
            bad=deepcopy(devices);bad[index][field]=value
            with self.assertRaises(ValueError):gate.validate_enumeration(bad,4,protocols,dcbaa)
        wrong=list(protocols);wrong[4]=3
        with self.assertRaises(ValueError):gate.validate_enumeration(devices,4,wrong,dcbaa)

    def test_usb_constructor_has_explicit_transport_and_never_calls_nvme_init(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(gate.gui.lifecycle.nvme.NvmeGuest,'__init__',side_effect=AssertionError('NVMe constructor forbidden')), \
             patch.object(gate.UsbGuest,'launch',lambda self:None), \
             patch.object(gate.UsbGuest,'bootstrap',lambda self:self.evidence.update(usb_bootstrap=True)):
            guest=gate.UsbGuest(Path('esp'),Path('disk'),Path(folder)/'boot',{},None,True)
            self.assertEqual('usb',guest.evidence['backend'])
            self.assertTrue(guest.evidence['usb_bootstrap'])
            guest.close()
            record=json.loads((Path(folder)/'boot/guest.json').read_text())
            self.assertFalse(record['actual_qemu_executed']);self.assertTrue(record['qemu_stopped'])

    def test_usb_constructor_failure_captures_before_own_transport_cleanup(self):
        events=[]
        class Process:
            returncode=0
            stopped=False
            def poll(self):return 0 if self.stopped else None
        def launch(guest):guest.process=Process()
        def bootstrap(guest):raise ValueError('actual USB startup failed')
        def close(guest):events.append('close');guest.process.stopped=True
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(gate.UsbGuest,'launch',launch),patch.object(gate.UsbGuest,'bootstrap',bootstrap), \
             patch.object(gate.UsbGuest,'capture_failure',lambda self:events.append('capture')), \
             patch.object(gate.UsbGuest,'screenshot',lambda self,name:events.append('screenshot')), \
             patch.object(gate.settings.Guest,'close',close):
            with self.assertRaisesRegex(ValueError,'actual USB startup failed'):
                gate.UsbGuest(Path('esp'),Path('disk'),Path(folder)/'boot',{},None)
        self.assertEqual(['capture','screenshot','close'],events)

    def test_bootstrap_uses_early_kernel_evidence_and_usb_markers_without_tablet_nvme(self):
        guest=object.__new__(gate.UsbGuest);events=[]
        guest.esp=Path('esp');guest.startup_timeout=180
        guest.raw=b'memory_runtime_boot_info=0xffff800000001000\r\n'
        guest.pause=lambda:events.append('pause')
        guest.resume=lambda:events.append('resume')
        guest.physical=lambda address,size,role:(events.append(('physical',address,size)) or bytes(160))
        guest.wait=lambda marker,timeout:events.append(('wait',marker))
        guest.refresh_processes=lambda:setattr(guest,'processes',bytes(16*gate.gui.lifecycle.PROCESS_BYTES))
        guest.validate_private_pools=lambda:events.append('pools')
        guest.verify_elf=lambda:events.append('actual-seven-elfs')
        guest.verify_process=lambda pid,name:dict(pid=pid,image=name)
        guest.settle=lambda:events.append('settle');guest.evidence={}
        with patch.object(gate.settings.acpi,'validation_symbols',lambda path:{}), \
             patch.object(gate.gui,'read_elf_symbols',lambda path:{}):
            guest.bootstrap()
        waits=[event[1] for event in events if isinstance(event,tuple) and event[0]=='wait']
        self.assertIn(b'DONGOS_XHCI_HID_BLOCK_RPC_READY\r\n',waits)
        self.assertIn(b'DONGOS_USB_BLOCK_READY\r\n',waits)
        self.assertFalse(any(b'NVME' in value or b'VIRTIO_TABLET' in value for value in waits))
        self.assertLess(events.index(('physical',4096,160)),events.index(('wait',waits[0])))
        self.assertEqual(dict(pid=13,image='xhci'),guest.evidence['actual_xhci_elf'])

    def test_success_requires_all_real_boots_and_cleanup_not_empty_mock_manifests(self):
        good=[dict(actual_qemu_executed=True,qemu_stopped=True) for _ in range(4)]
        self.assertEqual(4,gate.validate_boots(good,4)['actual_qemu_boots'])
        for bad in ([],good[:2],good+[good[0]],
                    [dict(actual_qemu_executed=False,qemu_stopped=True)]*4,
                    [*good[:3],dict(actual_qemu_executed=True,qemu_stopped=False)]):
            with self.assertRaises(ValueError):gate.validate_boots(bad,4)

    def test_actual_qemu_hid_handler_name_selects_relative_usb_not_ps2_or_tablet(self):
        usb=dict(index=2,name='QEMU HID Mouse',absolute=False,current=False)
        ps2=dict(index=0,name='QEMU PS/2 Mouse',absolute=False,current=True)
        tablet=dict(index=1,name='QEMU HID Tablet',absolute=True,current=False)
        self.assertEqual(usb,gate.select_usb_mouse([ps2,tablet,usb]))
        for mice in ([],[ps2],[tablet],[usb,dict(usb,index=3)],
                     [dict(usb,absolute=True)],[dict(usb,index=-1)]):
            with self.assertRaises(ValueError):gate.select_usb_mouse(mice)

    def test_independent_raw_fat_gate_rejects_seed_only_and_wrong_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixture.img';g=gate.create(path,64)
            with self.assertRaises(ValueError):gate.disk_evidence(path)
            raw=bytearray(path.read_bytes())
            def offset(cluster):return (g['data_start']+cluster-2)*512
            def fat(cluster,value):
                for copy in range(2):struct.pack_into('<I',raw,(g['reserved']+copy*g['fat_sectors'])*512+cluster*4,value)
            fat(4,0xfffffff)
            clusters=(len(gate.PAYLOAD)+511)//512
            for i in range(clusters):fat(5+i,0xfffffff if i==clusters-1 else 6+i)
            root=offset(2);alias=b'USBRUN~1   '
            entries=lfn_entries(gate.DIRECTORY[1:],alias)+[short(alias,4,attr=16)]
            for index,item in enumerate(entries,1):raw[root+index*32:root+(index+1)*32]=item
            first=offset(4);raw[first:first+32]=short(b'.          ',4,attr=16);raw[first+32:first+64]=short(b'..         ',0,attr=16)
            alias=b'USBDOC~1TXT';entries=lfn_entries(gate.DOCUMENT.rsplit('/',1)[1],alias)+[short(alias,5,len(gate.PAYLOAD))]
            for index,item in enumerate(entries,2):raw[first+index*32:first+(index+1)*32]=item
            raw[offset(5):offset(5)+len(gate.PAYLOAD)]=gate.PAYLOAD;path.write_bytes(raw)
            result=gate.disk_evidence(path);self.assertTrue(result['exact_namespace_verified'])
            raw[offset(5)]^=1;path.write_bytes(raw)
            with self.assertRaises(ValueError):gate.disk_evidence(path)


if __name__=='__main__':unittest.main(verbosity=2)
