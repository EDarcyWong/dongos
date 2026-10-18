#!/usr/bin/env python3
"""Real AHCI CPL3 read/write/FLUSH and same-disk reboot; never builds an OS."""
from pathlib import Path
import argparse,json,struct,sys,time,unittest,uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.build_usb import verify_build
from tools.make_fat32_disk import create
from tools.elf_symbols import read_elf_symbols
from tests import run_desktop_settings_qemu as settings,run_services_qemu as storage
ROOT=settings.ROOT

def check_layout(esp):
    from lang.dongc import compile_file
    generated=compile_file(ROOT/'services/drivers/block_service.dg',roots=[ROOT/'services',ROOT/'lang/std'],mode='release')
    settings.check(generated.assembly==(esp.parent/'services/block/program.asm').read_text(encoding='utf-8'),'layout compiler output differs from the completed block ELF input')
    types={v['full_name']:v for v in generated.layout_manifest['types']}
    expected={'drivers.ahci.State':(656,{'info':0,'lease':56,'port':128,'cap':136,'pi':144,'last_sample':328,'completion_policy':648}),
              'drivers.ahci.Info':(56,{'capacity_sectors':0,'ready':24,'faulted':32,'held':40,'completed':48})}
    for name,(size,fields) in expected.items():
        t=types[name];actual={f['name']:f['offset'] for f in t['fields']}
        settings.check(t['size']==size and all(actual.get(n)==o for n,o in fields.items()),'AHCI actual ABI changed: '+name)
    return expected

def ahci_command(command):
    command=list(command)
    candidates=[i for i,v in enumerate(command) if i and command[i-1]=='-drive' and v.startswith('format=raw,file=fat:rw:')]
    settings.check(len(candidates)==1,'one exact existing EFI FAT drive is required')
    settings.check(command.count('virtio-blk-pci,drive=data,disable-legacy=on')==1,'one exact VirtIO data device is required')
    settings.check(not any(v.startswith('ide-hd,') or 'id=bootesp' in v for v in command),'boot/data drive aliases already present')
    command[candidates[0]]='if=none,id=bootesp,'+command[candidates[0]]
    command[command.index('virtio-blk-pci,drive=data,disable-legacy=on')]='ide-hd,bus=ide.0,drive=data'
    command+=['-device','ide-hd,bus=ide.1,drive=bootesp,bootindex=1']
    return command

class AhciGuest(settings.Guest):
    def __init__(self,esp,disk,state):
        super().__init__(esp,disk,state,block_backend='ahci')
        self.wait(b'DONGOS_AHCI_READY')
    def shell(self,command,expected):
        settings.check(command.isascii() and '\n' not in command and '\r' not in command and len(command)<255,'invalid UART command')
        before=len(self.raw);self.resume();self.uart.sendall(command.encode()+b'\r')
        end=time.monotonic()+30
        while expected not in self.raw[before:] or b'> ' not in self.raw[before:]:
            settings.check(self.process.poll() is None and b'PANIC' not in self.raw and b'DONGOS_P1_KERNEL_FAIL' not in self.raw,'actual guest failure')
            settings.check(time.monotonic()<end,'UART response timeout')
            time.sleep(.01)
        self.pause();segment=bytes(self.raw[before:])
        settings.check(b'ERROR ' not in segment and b'unknown command' not in segment,'UART command failed')
        return dict(command=command,serial_offset=before,response_hex=segment.hex())
    def block_snapshot(self):
        pid=2;bias=struct.unpack_from('<Q',self.processes,pid*1288+224)[0]
        symbols=read_elf_symbols(self.esp.parent/'services/block/program.elf')
        def global_bytes(module,name,n):
            return self.user(pid,bias+symbols[storage.symbol(module,name)],n,module+'.'+name)
        backend=struct.unpack('<Q',global_bytes('drivers.block_service','BACKEND',8))[0]
        settings.check(backend==2 and self.kval('user.devices','SELECTED_KIND')==2,'actual block backend is not AHCI')
        settings.check(self.kernel(self.ksym('user.devices','AHCI_DMA_ENABLED'),1,'actual enable attempt')==b'\1','kernel did not enable selected AHCI')
        state=global_bytes('drivers.block_service','AHCI',656)
        identity=struct.unpack('<Q',global_bytes('drivers.block_service','AHCI_PCI_IDENTITY',8))[0]
        policy=struct.unpack('<Q',global_bytes('drivers.block_service','AHCI_COMPLETION_POLICY',8))[0]
        settings.check(policy==struct.unpack_from('<Q',state,648)[0]==0,'QEMU AHCI must use the default strict completion policy')
        settings.check(identity&0xffffffff!=0x07e015ad and (identity>>32)&0xffffff==0x010601 and identity>>56 in (0,128),'QEMU AHCI trusted PCI identity differs')
        info=struct.unpack_from('<7Q',state)
        settings.check(info[0]==131072 and info[1]==128 and info[2:6]==(0,1,0,1) and info[6]>0,'AHCI state/capacity/completion differs')
        token,physical,pointer,length=struct.unpack_from('<4Q',state,56)
        kernel_lease=struct.unpack('<4Q',self.kernel(self.ksym('user.devices','DMA_LEASE'),32,'trusted lease'))
        settings.check((token,physical,pointer,length)==kernel_lease and token==1 and pointer==0x68000000 and length==131072 and physical%131072==0,'AHCI lease mismatch')
        settings.check(0<physical<=0x100000000-length,'AHCI DMA exceeds supported 32bit range')
        for offset in range(0,length,4096):
            settings.check(self.pte(self.roots[2],pointer+offset)&~0x60==(physical+offset)|0x8000000000000007,'DMA must be exact private WB/RW/NX')
        bars=self.kernel(self.ksym('user.devices','BARS'),144,'trusted BAR grants')
        granted=[struct.unpack_from('<3Q',bars,i*24) for i in range(6)]
        settings.check(all(b==(0,0,0) for b in granted[:5]) and granted[5][1]>0 and granted[5][2]!=0,'AHCI must grant only BAR5')
        for offset in range(0,granted[5][1],4096):
            settings.check(self.pte(self.roots[2],0x65000000+offset)&~0x60==(granted[5][0]+offset)|0x800000000000001f,'BAR5 lost UC/RW/NX/USER')
        snapshot=self.kernel(self.ksym('user.devices','AHCI_PORTS'),32*64,'pre-enable trusted all-port snapshots')
        port,cap,pi=struct.unpack_from('<3Q',state,128)
        settings.check(port==0,'data must be first live ATA port')
        for i in range((cap&31)+1):
            if pi&(1<<i):
                cmd,ci,sact,ie,clb,fb,_,_=struct.unpack_from('<8Q',snapshot,i*64)
                settings.check(cmd&0xc011==0 and ci==sact==ie==0,'kernel enabled BME before every engine stopped')
                if i==port:settings.check((clb,fb)==(physical,physical+0x400),'kernel bases differ from trusted lease')
        # Last command was a guest-requested FLUSH, not a host reset/flush
        # injected through QMP. Read actual DMA descriptors and completion FIS.
        header=self.physical(physical,32,'actual AHCI slot0 header')
        table=self.physical(physical+0x800,144,'actual AHCI command table')
        fis=self.physical(physical+0x400,256,'actual AHCI received FIS')
        settings.check(struct.unpack_from('<II',header)==(5,0) and struct.unpack_from('<Q',header,8)[0]==physical+0x800,'last command header is not FLUSH EXT')
        settings.check(table[:3]==bytes.fromhex('2780ea') and not any(table[3:]) and fis[0x40]==0x34 and fis[0x42]&0xa9==0,'actual FLUSH command/completion invalid')
        self.evidence.update(actual_ahci=True,actual_guest_flush_ext=True,only_bar5_granted=True,all_implemented_ports_quiescent_before_enable=True,dma_lease_verified=True,strict_completion_policy=True)
        return dict(info=list(info),lease=list(kernel_lease),bar5=list(granted[5]),port=port,pi=pi,cap=cap,pci_identity=identity,completion_policy=policy)

class CommandTests(unittest.TestCase):
    def test_data_port0_and_efi_port1(self):
        original=['qemu','-machine','q35','-drive','format=raw,file=fat:rw:D:/esp','-drive','if=none,id=data,format=raw,file=D:/data.img','-device','virtio-blk-pci,drive=data,disable-legacy=on']
        result=ahci_command(original)
        self.assertEqual('virtio-blk-pci,drive=data,disable-legacy=on',original[-1])
        self.assertIn('if=none,id=bootesp,format=raw,file=fat:rw:D:/esp',result)
        self.assertIn('ide-hd,bus=ide.0,drive=data',result)
        self.assertEqual(['-device','ide-hd,bus=ide.1,drive=bootesp,bootindex=1'],result[-2:])
    def test_ambiguous_or_missing_drives_rejected(self):
        for command in ([],['-drive','format=raw,file=fat:rw:x'],['-drive','format=raw,file=fat:rw:x','-device','virtio-blk-pci,drive=data,disable-legacy=on','-device','ide-hd,bus=ide.0,drive=data']):
            with self.assertRaises(ValueError):ahci_command(command)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reuse-esp',type=Path);p.add_argument('--selftest',action='store_true');a=p.parse_args()
    if a.selftest:return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CommandTests)).wasSuccessful() else 1
    if not a.reuse_esp:p.error('--reuse-esp required; this runner never builds')
    state=ROOT/'build/test/ahci/qemu'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
    result=dict(passed=False,actual_qemu_boots=0,boot_attempts=0,boots=[],backend='ahci',full_os_build_executed=False);guest=None;metadata={}
    inputs={str(Path(__file__).relative_to(ROOT)):settings.sha(__file__),'tests/run_desktop_settings_qemu.py':settings.sha(ROOT/'tests/run_desktop_settings_qemu.py')}
    try:
        esp=a.reuse_esp.resolve();metadata=verify_build(esp);result['build_inputs_verified']=True
        result['layout']=check_layout(esp)
        result['build_inputs_sha256']=settings.sha(esp.parent/'build-inputs.json')
        result['runner_inputs']=inputs
        disk=state/'data.img';create(disk,64)
        payload=('DongOS AHCI persistent '+state.name).encode()
        for i in range(2):
            result['boot_attempts']+=1
            guest=AhciGuest(esp,disk,state/('boot-'+str(i+1)))
            commands=[]
            if i==0:commands.append(guest.shell('write PROBE.TXT '+payload.decode(),b'WRITE OK'))
            commands.append(guest.shell('cat PROBE.TXT',payload))
            commands.append(guest.shell('ls',b'PROBE.TXT'))
            commands.append(guest.shell('sync',b'SYNC OK'))
            block=guest.block_snapshot();guest.close()
            result['boots'].append(dict(evidence=guest.evidence,commands=commands,block=block));guest=None
            result['disk']=storage.check_disk(disk,raw_name=b'PROBE   TXT',payload=payload)
        result.update(passed=True,same_disk_reboot_verified=True,actual_cpl3_ahci=True,no_qmp_storage_or_power_injection=True)
    except Exception as e:result['error']=f'{type(e).__name__}: {e}'
    finally:
        if guest:
            try:guest.close()
            except Exception as e:result.update(passed=False,cleanup_error=f'{type(e).__name__}: {e}')
        result['actual_qemu_boots']=sum(json.loads(p.read_text())['actual_qemu_executed'] is True for p in state.glob('boot-*/guest.json'))
        result['source_unchanged']=all(settings.sha(ROOT/n)==s for n,s in inputs.items()) and all(settings.sha(ROOT/n)==s for n,s in metadata.get('source_sha256',{}).items())
        if not result['source_unchanged']:result.update(passed=False,error='source changed during AHCI verification')
        storage.write_json(state/'result.json',result)
    print('AHCI actual','PASS' if result['passed'] else 'FAIL',state,result.get('error',''),flush=True)
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
