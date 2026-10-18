"""Ordinary production fixtures execute native; root runs real kernel guests."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_input import command
from tests.test_fat32 import stack_bound
ROOT=Path(__file__).resolve().parents[1]


class AppFixtureTests(unittest.TestCase):
    def test_native_actual_fixture_main_canaries_ipc_and_readonly_file_probes(self):
        directory=ROOT/'build/test/apps'/('run-'+uuid.uuid4().hex[:12]);directory.mkdir(parents=True)
        paths=[*sorted((ROOT/'services/apps').glob('*.dg')),*(ROOT/p for p in (
            'services/lib/files.dg','services/lib/sys.dg','services/lib/abi.dg','services/fs/protocol.dg',
            'services/fs/handles.dg','tests/apps_probe.c','tests/test_apps.py'))]
        before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};results=[]
        for kind,name in enumerate(('echo','fault','waiter','ipc_peer','fs_reader'),1):
            services=directory/name/'services';(services/'apps').mkdir(parents=True)
            for source in paths:
                if source.is_relative_to(ROOT/'services') and source.parent.name!='apps':
                    target=services/source.relative_to(ROOT/'services');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
            production=ROOT/'services/apps'/f'{name}.dg';original=production.read_bytes()
            if name=='fault':suffix='\nexport("app_canary") fn app_canary()u64{return 0;}\nexport("app_reset") fn app_reset()void{return;}\n'
            else:suffix='\nexport("app_canary") fn app_canary()u64{unsafe{return CANARY;}}\nexport("app_reset") fn app_reset()void{unsafe{CANARY=0;}return;}\n'
            if name=='waiter':suffix+='\nexport("app_probe") fn app_probe()u64{unsafe{return PROBE_VALUE;}}\n'
            staged=services/'apps'/f'{name}.dg';staged.write_bytes(original+suffix.encode());self.assertEqual(original,staged.read_bytes()[:len(original)])
            for mode in ('debug','release'):
                out=directory/name/mode;out.mkdir(parents=True);compiled=compile_file(staged,roots=[services],mode=mode)
                bound=stack_bound(compiled.assembly);self.assertLessEqual(bound,4096)
                asm=out/'probe.asm';asm.write_text(compiled.assembly);nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
                for fmt in ('elf64','win64'):command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',out/(fmt+'.o'),asm],out,'assemble-'+fmt)
                exe=out/('probe.exe' if os.name=='nt' else 'probe');flags=['-mno-sse'] if os.name=='nt' else ['-no-pie','-D_GNU_SOURCE']
                command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',f'-DAPP_KIND={kind}',*flags,
                    ROOT/'tests/apps_probe.c',out/('win64.o' if os.name=='nt' else 'elf64.o'),'-o',exe],out,'link')
                result=command([exe],out,'native');self.assertIn('App production fixture kind=',result.stdout)
                results.append(dict(name=name,mode=mode,stack=bound,stdout=result.stdout))
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};self.assertEqual(before,after)
        (directory/'validation-summary.json').write_text(json.dumps(dict(source_unchanged=True,
            source_sha256=after,results=results,actual_production_main_machine_code=True,
            syscall_and_ud2_host_stubs=True,actual_kernel_or_hardware_exception=False),indent=2)+'\n')
        print('APPS_FIXTURES_EVIDENCE '+str(directory))


if __name__=='__main__':unittest.main(verbosity=2)
