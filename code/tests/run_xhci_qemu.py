#!/usr/bin/env python3
"""Actual direct-root USB2 enumeration/HID/BOT on ordinary disposable images.

No full OS build, host USB passthrough, physical device, or guest RAM write.
Only the root agent runs this serially with other hardware integrations.
"""
from pathlib import Path
import argparse,hashlib,json,re,struct,sys,time,uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests import run_gui_clients_qemu as gui
from tools import build as builder
from tools.build_usb import verify_build
from tools.make_fat32_disk import create
ROOT=gui.ROOT
check=gui.check

def add_devices(command,image):
    # Disable SuperSpeed in this bounded USB2 test; its endpoint maxBurst and
    # companion descriptor policy have a separate acceptance contract.
    return command+['-device','qemu-xhci,id=usbhost,addr=0x5,p2=4,p3=0',
      '-drive','if=none,id=usbdata,format=raw,cache=writeback,file='+image.resolve().as_posix().replace(',',',,'),
      '-device','usb-storage,id=usbdisk,bus=usbhost.0,port=1,drive=usbdata,removable=on',
      '-device','usb-kbd,id=usbkeyboard,bus=usbhost.0,port=2',
      '-device','usb-mouse,id=usbmouse,bus=usbhost.0,port=3']

def scalar(raw,types,name,field):return types.number(raw,name,field)

class EnumerationGuest(gui.GuiGuest):
    """Bring-up evidence can precede independent GUI acceptance."""
    def __init__(self,esp,disk,state,kernel_layout,layouts):
        self.layouts=layouts;self.gui_symbols={};self._gui_constructing=False
        gui.lifecycle.ProcessGuest.__init__(self,esp,disk,state,kernel_layout)
    def settle(self):
        self.pause()
    def wait(self,marker,timeout=90):
        if not marker.startswith(b'DONGOS_XHCI_'):
            return super().wait(marker,timeout)
        deadline=time.monotonic()+timeout
        while marker not in self.raw:
            error=re.search(rb'xhci_error=0x([0-9a-f]{16})',bytes(self.raw))
            check(error is None,'actual xHCI entry error: '+(error[1].decode() if error else ''))
            check(self.process.poll() is None and time.monotonic()<deadline,'USB startup timeout')
            time.sleep(.02)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reuse-esp',type=Path,required=True)
    p.add_argument('--enumeration-only',action='store_true',help='USB bring-up only; no GUI completion claim')
    args=p.parse_args();esp=args.reuse_esp.resolve()
    out=ROOT/'build/test/p8-xhci/qemu'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
    result=dict(passed=False,actual_qemu_boots=0,no_physical_device=True,no_guest_memory_writes=True,
                runtime_usb_primary_filesystem=False,actual_usb_write_verified=False)
    guest=None;original=builder.qemu_command
    try:
        verify_build(esp);layouts,identity=gui.checked_layouts(esp)
        from lang.dongc import compile_file
        compiled=compile_file(ROOT/'services/drivers/xhci_service.dg',roots=[ROOT/'services',ROOT/'lang/std'],mode='release')
        completed=esp.parent/'services/xhci/program.asm'
        check(compiled.assembly==completed.read_text(encoding='utf-8'),'actual USB service source/build differ')
        for item in compiled.layout_manifest['types']:
            name=item['full_name'];check(name not in layouts.types or layouts.types[name]==item,'USB ABI differs');layouts.types[name]=item
        result['assembly_identity']=identity+[dict(image='xhci',assembly_sha256=gui.settings.sha(completed))]
        disk=out/'pci-data.img';usb=out/'usb-data.img';create(disk,64);geometry=create(usb,64)
        initial=gui.settings.sha(usb)
        def command(*a,**kw):return add_devices(original(*a,**kw),usb)
        builder.qemu_command=command
        guest_type=EnumerationGuest if args.enumeration_only else gui.GuiGuest
        guest=guest_type(esp,disk,out/'boot-1',gui.lifecycle.nvme.check_kernel_memory_layout(esp),layouts)
        builder.qemu_command=original
        guest.resume();guest.wait(b'DONGOS_XHCI_ASYNC_HID_BOT_READY\r\n',timeout=90);guest.pause()
        catalog=guest.catalog();snap=catalog['snapshots'][13]
        check(snap['state']==2 and snap['process']&255==14 and catalog['slots'][13]==13,'actual reserved USB process missing')
        result['gui']=None if args.enumeration_only else guest.smoke('usb')
        result['independent_gui_acceptance_executed']=not args.enumeration_only
        guest.refresh_processes()
        state=guest.struct(13,'xhci','drivers.xhci_service','STATE','usb.xhci_controller.State')
        setup=layouts.part(state,'usb.xhci_controller.State','setup')
        address=scalar(setup,layouts,'usb.xhci_controller.Setup','pointer')
        pa=scalar(setup,layouts,'usb.xhci_controller.Setup','physical')
        length=scalar(setup,layouts,'usb.xhci_controller.Setup','bytes')
        check(length==131072 and address%4096==0 and pa%4096==0,'USB private DMA lease differs')
        mappings=[]
        for offset in range(0,length,4096):
            entry=guest.pte(guest.roots[13],address+offset)
            check(entry&gui.MASK==pa+offset and entry&(gui.NF|0x19f)==gui.NF|7,'USB DMA leaf is not private WB/RW/NX')
            for pid,root in enumerate(guest.roots):
                if not root or pid==13:continue
                other=guest.pte(root,address+offset)
                check(not other&1 or other&gui.MASK!=pa+offset,'USB DMA appears in another USER root')
            mappings.append(entry)
        raw=bytes(guest.raw)
        for marker in (b'DONGOS_XHCI_BOT_ENUMERATED',b'DONGOS_XHCI_HID_KEYBOARD_ENUMERATED',
                       b'DONGOS_XHCI_HID_MOUSE_ENUMERATED',b'DONGOS_XHCI_BOT_READ_SYNC_READY'):
            check(marker in raw,'actual USB marker missing: '+repr(marker))
        def last_hex(name):
            matches=re.findall(name.encode()+rb'=0x([0-9a-f]{16})',bytes(guest.raw));check(bool(matches),'missing '+name)
            return int(matches[-1],16)
        check(last_hex('usb_bot_blocks')==geometry['total'] and last_hex('usb_bot_block_bytes')==512,'actual READ CAPACITY differs from image')
        with usb.open('rb') as stream:head=int.from_bytes(stream.read(8),'little')
        check(last_hex('usb_bot_lba0_head')==head,'actual USB READ10 LBA0 differs')
        before=len(guest.raw)
        guest.resume();guest.qmp.request('send-key',{'keys':[{'type':'qcode','data':'a'}],'hold-time':100})
        deadline=time.monotonic()+10
        def keys():
            return re.findall(rb'usb_hid_source=0x([0-9a-f]{16})\r\nusb_hid_kind=0x0000000000000001\r\nusb_hid_bytes=0x0000000000000008\r\nusb_hid_generation=0x([0-9a-f]{16})\r\nusb_hid_raw=0x([0-9a-f]{16})\r\nDONGOS_XHCI_HID_REPORT\r\n',bytes(guest.raw[before:]))
        while len(keys())<2:
            check(time.monotonic()<deadline and guest.process.poll() is None,'USB keyboard did not complete make/release TDs');time.sleep(.02)
        guest.pause()
        reports=keys();check(int(reports[0][2],16)==0x40000 and int(reports[-1][2],16)==0
          and reports[0][0]==reports[-1][0] and int(reports[-1][1],16)>int(reports[0][1],16),
          'actual USB keyboard bytes/generation did not match QMP a make/release')
        result.update(actual_private_dma=mappings,actual_reserved_process=snap,actual_read_capacity=True,
                      actual_read10_lba0=True,actual_sync=True,actual_hid_report_make_release=True,
                      actual_hid_reports=[[x.decode() for x in row] for row in reports],
                      qmp_usb=guest.qmp.request('human-monitor-command',{'command-line':'info usb'}))
        guest.screenshot('usb-final');guest.close();guest=None
        check(gui.settings.sha(usb)==initial,'read/SYNC/HID smoke changed USB image')
        result.update(passed=True,usb_image_sha256=initial)
    except Exception as e:
        result['error']=type(e).__name__+': '+str(e)
        if guest:
            try:
                guest.pause();guest.refresh_processes()
                symbols=gui.read_elf_symbols(esp.parent/'services/xhci/program.elf')
                bias=struct.unpack_from('<Q',guest.processes,13*gui.lifecycle.PROCESS_BYTES+224)[0]
                address=struct.unpack('<Q',guest.user(13,bias+symbols[gui.storage.symbol('drivers.xhci_service','VIRTUAL')],8,'actual USB BAR virtual'))[0]
                check(0x60000000<=address<0x68000000,'USB BAR was not mapped')
                physical=guest.pte(guest.roots[13],address)&gui.MASK
                caps=guest.physical(physical,64,'actual xHCI capability MMIO')
                op=caps[0]
                page=guest.physical(physical+op+8,4,'actual xHCI PAGESIZE MMIO')
                gui.storage.write_json(out/'failure-capabilities.json',dict(physical=physical,raw_hex=caps.hex(),
                    words=list(struct.unpack('<16I',caps)),pagesize=int.from_bytes(page,'little')))
                result['actual_capabilities_captured']=True
            except Exception as nested:result['capabilities_error']=str(nested)
            for name,action in (('failure_state',guest.capture_failure),('failure_screen',lambda:guest.screenshot('failure'))):
                try:action();result[name]=True
                except Exception as nested:result[name+'_error']=str(nested)
    finally:
        builder.qemu_command=original
        if guest:
            try:guest.close()
            except Exception as e:result.update(passed=False,cleanup_error=str(e))
        records=[json.loads(p.read_text(encoding='utf-8')) for p in out.glob('boot-*/guest.json')]
        result['actual_qemu_boots']=sum(r.get('actual_qemu_executed') is True for r in records)
        result['all_started_guests_stopped']=all(not r.get('actual_qemu_executed') or r.get('qemu_stopped') for r in records)
        if result['passed'] and (result['actual_qemu_boots']!=1 or not result['all_started_guests_stopped']):result.update(passed=False,error='actual guest/cleanup count differs')
        gui.storage.write_json(out/'result.json',result)
    print('Actual xHCI', 'PASS' if result['passed'] else 'FAIL',out,result.get('error',''),flush=True)
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
