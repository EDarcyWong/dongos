"""Exact USB root/selection/manager functions, real capability table, host I/O model."""
import hashlib
import json
import os
from pathlib import Path
import unittest
import uuid

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
from tests.test_input import command
from tests.test_service_ipc_cancellation import block
from tests.test_service_gui_wiring import copy_graph

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'build/test/p8-usb-root-candidate'


def overrides(kernel, manager, selection):
    names = ('install_identity', 'BOOTs_common', 'BOOTs_region', 'BOOTs_manager', 'authority', 'endpoint', 'probe_pages', 'channels')
    fragments = '\n'.join(block(kernel, 'unsafe fn ' + name + '(') for name in names)
    fixture = (ROOT / 'tests/usb_root_probe.dg.in').read_text(encoding='utf-8').replace('// EXACT_PRODUCTION_FUNCTIONS', fragments)
    manager += '''
export("ur_manager") fn probe_start()u64{unsafe{
 CHOICES=[abi.EMPTY_DEVICE;4];SELECTED=[abi.EMPTY_DEVICE;4];BINDINGS=[abi.EMPTY_BINDING;4];
 match start(0x999){ok=>{return 0;},err(e)=>{return e;},}
}}
'''
    setup = block(selection, 'unsafe fn setup()')
    prefix = setup[:setup.index('        if sys.svc_call(0x61')]
    select = '''module usb_selection_fixture;import lib.sys as sys;import fs.protocol as protocol;
import drivers.pci as pci;import drivers.usb_block_proxy as usb;
var BOOT:*const sys.Boot=null;var USB:usb.State=usb.EMPTY;var BACKEND:u64=0;var SELECTED:pci.Function=pci.EMPTY_FUNCTION;
pub error Setup=0x05060001;
unsafe fn configuration(context:u64,address:u64,out:*u32)u64{return 1;}
''' + prefix + '''        SELECTED=function;
    }return;
}
export("ur_select") fn probe_select()u64{unsafe{USB=usb.EMPTY;BACKEND=0;SELECTED=pci.EMPTY_FUNCTION;
 match setup(){ok=>{return 0;},err(e)=>{return e;},}
}}
export("ur_backend") fn backend()u64{unsafe{return BACKEND;}}
export("ur_selected") fn selected()u64{unsafe{return SELECTED.ecam;}}
'''
    pci = (ROOT / 'services/drivers/pci.dg').read_text(encoding='utf-8')
    pci = pci[:pci.index('const LIMIT:')] + '''
unsafe extern "sysv64" fn ur_pci(index:u64,out:*Function)u64;
pub unsafe fn next(reader:Read32,context:u64,regions:[]const Region,cursor:*Cursor,out:*Function)!bool{unsafe{
 let status=ur_pci((*cursor).index,out);if status==0{return false;}(*cursor).index+=1;return true;
}}
'''
    return {
        'usb_root_probe': fixture + '\nimport usb_selection_fixture as selection;import drivers.device_manager as manager;',
        'usb_selection_fixture': select,
        'drivers.device_manager': manager,
        'drivers.usb_block_proxy': (CANDIDATE / 'services/drivers/usb_block_proxy.dg').read_text(encoding='utf-8'),
        'drivers.pci': pci,
        'user.processes': '''module user.processes;import lib.process_abi as abi;
pub const CONFIGS:usize=18;pub struct Catalog{pub states:[32]abi.Snapshot,pub slot:[32]u64}
pub const EMPTY:Catalog=Catalog{states:[abi.EMPTY_SNAPSHOT;32],slot:[0;32]};''',
        'user.memory': '''module user.memory;pub error Invalid=0x09000001;
unsafe extern "sysv64" fn ur_memory(source:u64,target:u64,address:u64,write:u64)u64;
pub unsafe fn anonymous(id:usize,address:u64)!u64{return address;}
pub unsafe fn copy_out(id:usize,address:u64,input:[]const u8)!void{return;}
pub unsafe fn readonly_data(id:usize,address:u64)!void{return;}
pub unsafe fn runtime_copy_bytes(out:*u8,input:*const u8,bytes:usize)void{return;}
var WORD:u64=0;pub unsafe fn owned_alias(id:usize,address:u64,write:bool)!u64{unsafe{return &WORD as u64;}}
pub unsafe fn share(source:usize,target:usize,address:u64,write:bool)!void{unsafe{
 if ur_memory(source as u64,target as u64,address,write as u64)!=0{return error.Invalid;}}return;}
pub unsafe fn share_at(source:usize,target:usize,address:u64,dest:u64,write:bool)!void{return;}
''',
        'user.devices': '''module user.devices;pub const CONFIGURATION_OBJECT:u64=10;pub const DMA_OBJECT:u64=20;pub const CONSOLE_OBJECT:u64=30;
pub fn region_base()u64{return 0xe0000000;}pub fn region_first()u64{return 0;}pub fn region_last()u64{return 0;}''',
        'user.desktop': '''module user.desktop;pub const INPUT_QUEUE:u64=0x54000000;
pub unsafe fn map_client_font(id:usize)!void{return;}pub unsafe fn recreate(id:usize)!void{return;}''',
        'user.device_host': '''module user.device_host;pub unsafe fn xhci_attach(id:usize,owner:u64,gen:u64)!void{return;}''',
        'boot.power_startup': 'module boot.power_startup;pub const POWER_OBJECT:u64=0x08000001;',
        'input.console': 'module input.console;pub struct Queue{pub word:u64}pub const ADDRESS:u64=0x54100000;',
    }


class UsbRootGlueTests(unittest.TestCase):
    def test_exact_root_caps_channel_selection_and_xhci_only_manager(self):
        paths = [CANDIDATE / 'kernel/user/services.dg', CANDIDATE / 'services/drivers/device_manager.dg',
                 CANDIDATE / 'services/drivers/block_service.dg', CANDIDATE / 'services/drivers/usb_block_proxy.dg',
                 ROOT / 'tests/usb_root_probe.dg.in', ROOT / 'tests/usb_root_probe.c', Path(__file__)]
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        kernel, manager, selection = [p.read_text(encoding='utf-8') for p in paths[:3]]
        variants = [
            ('normal', None, None, None),
            ('ordinary-usb-endpoint', 'kernel', 'if id==2&&GRAPHICS{', 'if (id==2||id==7)&&GRAPHICS{'),
            ('wrong-channel-owner', 'kernel', 'memory.share(2,13,0x5100_0000', 'memory.share(1,13,0x5100_0000'),
            ('fifteen-channel-pages', 'kernel', 'while i<16{try memory.share(2,13,', 'while i<15{try memory.share(2,13,'),
            ('requires-internal-block', 'manager', 'if CHOICES[0].token==0&&CHOICES[3].token==0', 'if CHOICES[0].token==0'),
            ('admits-no-storage-controller', 'manager', 'if CHOICES[0].token==0&&CHOICES[3].token==0', 'if false'),
            ('ahci-over-nvme', 'selection', 'if nvm.ecam!=0 {function=nvm;BACKEND=3;}', 'if nvm.ecam!=0&&sata.ecam==0 {function=nvm;BACKEND=3;}'),
        ]
        directory = ROOT / 'build/test/usb-root-glue' / ('run-' + uuid.uuid4().hex[:12])
        directory.mkdir(parents=True)
        results = []
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc)
        for label, name, old, new in variants:
            texts = dict(kernel=kernel, manager=manager, selection=selection)
            if name:
                self.assertEqual(1, texts[name].count(old))
                texts[name] = texts[name].replace(old, new, 1)
            for mode in ('debug', 'release'):
                d = directory / (label + '-' + mode)
                stage = d / 'source'
                copy_graph(stage, ['usb_root_probe'], overrides(**texts))
                compiled = compile_file(stage / 'usb_root_probe.dg', roots=[stage], mode=mode)
                asm = d / 'probe.asm'
                asm.write_text(compiled.assembly, encoding='utf-8')
                objects = {}
                for fmt in ('win64', 'elf64'):
                    objects[fmt] = d / (fmt + '.o')
                    command([nasm, '-f', fmt, *nasm_flags(nasm), '-o', objects[fmt], asm], d, 'assemble-' + fmt)
                exe = d / ('probe.exe' if os.name == 'nt' else 'probe')
                command([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-D__USE_MINGW_ANSI_STDIO=1',
                         *(['-mno-sse'] if os.name == 'nt' else ['-no-pie']),
                         ROOT / 'tests/usb_root_probe.c', objects['win64' if os.name == 'nt' else 'elf64'], '-o', exe], d, 'link')
                result = command([exe], d, 'native', success=False)
                self.assertEqual(0 if name is None else 1, result.returncode, result.stdout + result.stderr)
                self.assertIn('USB_ROOT_NATIVE_PASS' if name is None else 'USB_ROOT_ASSERT', result.stdout + result.stderr)
                results.append(dict(variant=label, mode=mode, stdout=result.stdout, stderr=result.stderr, returncode=result.returncode))
        self.assertEqual(before, {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
        (directory / 'validation-summary.json').write_text(json.dumps(dict(passed=True, source_unchanged=True,
            source_sha256=before, actual_production_fragments=True, actual_capability_table=True,
            memory_pci_and_rpc_boundaries_mocked=True, hardware_io=False, results=results), indent=2) + '\n', encoding='utf-8')
        print('USB_ROOT_GLUE_EVIDENCE', directory)


if __name__ == '__main__':
    unittest.main(verbosity=2)
