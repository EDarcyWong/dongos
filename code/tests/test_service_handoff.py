"""Execute the real EFI service loader and independent resource ownership model."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import tool, nasm_flags
from tools.service_bundle import pack, DATA

ROOT = Path(__file__).resolve().parents[1]


class ServiceHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/p5-handoff/host' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.paths = [ROOT / p for p in ('boot/service_bundle.asm','include/service_handoff.inc',
            'kernel/boot/service_resources.dg','tests/service_boot_probe.c',
            'tests/service_resources_probe.dg','tests/service_resources_probe.c','tests/test_service_handoff.py')]
        cls.before = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
        (cls.directory / 'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
        (cls.directory / 'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
        if after != cls.before:
            raise AssertionError('service-handoff sources changed during validation')

    def run_command(self, command, directory, name, expected=0):
        started = time.monotonic()
        result = subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=45)
        (directory / (name+'.json')).write_text(json.dumps(dict(command=list(map(str,command)),
            returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,
            elapsed_seconds=time.monotonic()-started),indent=2)+'\n')
        self.assertEqual(expected,result.returncode,result.stdout+result.stderr)
        return result

    def required_tools(self):
        nasm, cc = tool('nasm','NASM'),tool('gcc','CC')
        if not nasm or not cc:
            self.skipTest('requires NASM and native SysV-capable GCC')
        return nasm, cc

    def test_actual_uefi_helper(self):
        nasm,cc = self.required_tools()
        directory = self.directory / 'uefi'
        directory.mkdir()
        obj,exe = directory/'loader.o', directory/('probe.exe' if os.name=='nt' else 'probe')
        self.run_command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),
            '-I',str(ROOT/'include')+os.sep,'-o',str(obj),str(ROOT/'boot/service_bundle.asm')],directory,'assemble')
        self.run_command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',
            '-D__USE_MINGW_ANSI_STDIO=1',str(ROOT/'tests/service_boot_probe.c'),str(obj),'-o',str(exe)],directory,'link')
        bundle = directory/'SERVICES.BIN'
        bundle.write_bytes(pack([('probe',DATA,bytes(range(256))*20)]))
        for case in range(24):
            with self.subTest(scenario=case):
                self.run_command([str(exe),str(case),str(bundle)],directory,f'scenario-{case:02d}')

    def test_actual_resource_model(self):
        nasm,cc = self.required_tools()
        for mode in ('debug','release'):
            with self.subTest(mode=mode):
                directory = self.directory/mode
                directory.mkdir()
                result = compile_file(ROOT/'tests/service_resources_probe.dg',
                    roots=[ROOT/'tests',ROOT/'kernel'],mode=mode)
                asm,obj,exe = directory/'probe.asm',directory/'probe.o',directory/('probe.exe' if os.name=='nt' else 'probe')
                asm.write_text(result.assembly)
                self.run_command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',str(obj),str(asm)],directory,'assemble')
                self.run_command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',
                    *(['-mno-sse'] if os.name=='nt' else ['-no-pie']),str(ROOT/'tests/service_resources_probe.c'),str(obj),'-o',str(exe)],directory,'link')
                self.run_command([str(exe)],directory,'actual-independent-model')
