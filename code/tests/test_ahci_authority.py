"""Execute the DMA-enable policy with independent C register snapshots."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
ROOT=Path(__file__).resolve().parents[1]

class AhciAuthorityTests(unittest.TestCase):
    def test_native_policy_bad_other_port_control_and_object_formats(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
        self.assertTrue(nasm and cc,'NASM and SysV-capable GCC are required')
        directory=ROOT/'build/test/ahci-authority'/('run-'+uuid.uuid4().hex[:12]);directory.mkdir(parents=True)
        names=('services/drivers/ahci_authority.dg','tests/ahci_authority_probe.dg','tests/ahci_authority_probe.c','tests/test_ahci_authority.py')
        before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in names}
        evidence={}
        def command(args,where,label):
            result=subprocess.run([str(x) for x in args],cwd=ROOT,capture_output=True,text=True,timeout=50)
            (where/(label+'.json')).write_text(json.dumps(dict(command=[str(x) for x in args],returncode=result.returncode,stdout=result.stdout,stderr=result.stderr),indent=2)+'\n',encoding='utf-8')
            return result
        for mode in ('debug','release'):
            evidence[mode]={}
            for bad in (False,True):
                where=directory/(mode+('-bad' if bad else ''));where.mkdir()
                source=ROOT/'services'
                if bad:
                    source=where/'services';(source/'drivers').mkdir(parents=True)
                    text=(ROOT/names[0]).read_text(encoding='utf-8')
                    self.assertEqual(1,text.count('while i<count as usize'))
                    (source/'drivers/ahci_authority.dg').write_text(text.replace('while i<count as usize','while i<1'),encoding='utf-8')
                compiled=compile_file(ROOT/names[1],roots=[ROOT/'tests',source],mode=mode)
                layouts={v['full_name']:v for v in compiled.layout_manifest['types']}
                self.assertEqual(88,layouts['drivers.ahci_authority.Header']['size'])
                self.assertEqual(64,layouts['drivers.ahci_authority.Port']['size'])
                maximum=max(map(int,re.findall(r'\bsub rsp, (\d+)',compiled.assembly)),default=0)
                self.assertLessEqual(maximum,4096)
                asm=where/'probe.asm';asm.write_text(compiled.assembly,encoding='utf-8')
                obj=where/'probe.o';exe=where/('probe.exe' if os.name=='nt' else 'probe')
                for fmt in ('win64','elf64') if not bad else ('win64' if os.name=='nt' else 'elf64',):
                    target=obj if fmt==('win64' if os.name=='nt' else 'elf64') else where/(fmt+'.o')
                    r=command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',target,asm],where,'assemble-'+fmt)
                    self.assertEqual(0,r.returncode,r.stderr)
                r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),ROOT/names[2],obj,'-o',exe],where,'link')
                self.assertEqual(0,r.returncode,r.stderr)
                r=command([exe,*(['bad'] if bad else [])],where,'execute')
                if bad:
                    self.assertEqual(99,r.returncode,r.stdout+r.stderr)
                    self.assertIn('UNSAFE_OTHER_PORT_ACCEPTED',r.stdout)
                else:
                    self.assertEqual(0,r.returncode,r.stdout+r.stderr)
                    self.assertRegex(r.stdout,r'AHCI authority checks=66[0-9]{3} ')
                evidence[mode]['bad' if bad else 'normal']=dict(stdout=r.stdout,max_single_frame=maximum)
        after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in names}
        self.assertEqual(before,after)
        (directory/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_sha256=after,sources_unchanged=True,actual_device_executed=False,evidence=evidence),indent=2)+'\n',encoding='utf-8')
        print('AHCI_AUTHORITY_EVIDENCE',directory)
