"""Execute the exact Win64 UEFI bundle-envelope assembly on the native host."""
import hashlib
import json
import os
from pathlib import Path
import re
import unittest
import uuid
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_input import command
ROOT=Path(__file__).resolve().parents[1]


class ServiceBundleHeaderTests(unittest.TestCase):
    def test_actual_win64_header_capacity_padding_reserved_and_bad_32_manifest_gate(self):
        directory=ROOT/'build/test/boot-bundle-header'/('run-'+uuid.uuid4().hex[:12]);directory.mkdir(parents=True)
        paths=[ROOT/p for p in ('boot/service_bundle.asm','include/service_handoff.inc',
            'tests/service_bundle_header_probe.c','tests/test_service_bundle_header.py')]
        before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        text=(ROOT/'boot/service_bundle.asm').read_text();start=text.index('sb_bundle_header:\n');end=text.index('service_handoff_validate:\n',start)
        # Copy through the final .bad return, excluding the next helper's comment.
        body=text[start:end];last=body.rfind('    ret\n');self.assertGreaterEqual(last,0);body=body[:last+len('    ret\n')]
        error=re.search(r'^SB_LOAD_ERROR equ [^\n]+$',text,re.MULTILINE);self.assertIsNotNone(error)
        prefix='bits 64\ndefault rel\n'+error.group(0)+'\nsection .text\nglobal sb_bundle_header\n'
        results=[]
        for label,actual in (('normal',body),('bad-cap32',body.replace('cmp r8d, 30','cmp r8d, 31',1))):
            if label!='normal':self.assertEqual(1,body.count('cmp r8d, 30'));self.assertNotEqual(body,actual)
            out=directory/label;out.mkdir();asm=out/'header.asm';asm.write_text(prefix+actual)
            self.assertEqual(actual,asm.read_text()[len(prefix):])
            nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
            for fmt in ('elf64','win64'):command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',out/(fmt+'.o'),asm],out,'assemble-'+fmt)
            exe=out/('probe.exe' if os.name=='nt' else 'probe');flags=['-mno-sse'] if os.name=='nt' else ['-no-pie']
            command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',*flags,ROOT/'tests/service_bundle_header_probe.c',
                out/('win64.o' if os.name=='nt' else 'elf64.o'),'-o',exe],out,'link')
            result=command([exe],out,'native',success=False)
            if label=='normal':self.assertEqual(0,result.returncode,result.stdout+result.stderr);self.assertIn('payload31=nonzero',result.stdout)
            else:self.assertEqual(1,result.returncode,result.stdout+result.stderr);self.assertIn('BUNDLE_HEADER_MODEL_ASSERT',result.stderr)
            results.append(dict(label=label,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,
                actual_body_unchanged=label=='normal',body_sha256=hashlib.sha256(actual.encode()).hexdigest()))
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};self.assertEqual(before,after)
        (directory/'validation-summary.json').write_text(json.dumps(dict(source_unchanged=True,source_sha256=after,
            results=results,actual_uefi_header_machine_code=True,actual_firmware_file_io=False),indent=2)+'\n')
        print('BOOT_BUNDLE_HEADER_EVIDENCE '+str(directory))


if __name__=='__main__':unittest.main(verbosity=2)
