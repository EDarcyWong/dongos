"""Independent raw-PTE walking, WB/UC cache bits and native paging model checks."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=Path(__file__).parent


class PagingTests(unittest.TestCase):
    def compile(self,mode):
        return compile_file(FIXTURES/'paging_probe.dg',roots=[FIXTURES,ROOT/'kernel',ROOT/'lang/std'],mode=mode)

    def test_public_layout_and_both_object_formats(self):
        compiled=self.compile('debug')
        layouts={item['full_name']:item for item in compiled.layout_manifest['types']}
        self.assertEqual((4096,4096),(layouts['mm.paging.Table']['size'],layouts['mm.paging.Table']['alignment']))
        self.assertEqual((16,8),(layouts['mm.paging.Mapping']['size'],layouts['mm.paging.Mapping']['alignment']))
        self.assertEqual([0,8],[item['offset'] for item in layouts['mm.paging.Mapping']['fields']])
        self.assertNotRegex(compiled.assembly.lower(),r'\b(?:xmm|ymm|zmm)[0-9]+\b')
        nasm=tool('nasm','NASM')
        if not nasm:self.skipTest('both object formats require NASM')
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            for mode in ('debug','release'):
                asm=directory/(mode+'.asm');asm.write_text(self.compile(mode).assembly,encoding='utf-8')
                for fmt in ('elf64','win64'):
                    with self.subTest(mode=mode,format=fmt):
                        result=subprocess.run([nasm,'-f',fmt,*nasm_flags(nasm),'-o',str(directory/(mode+'-'+fmt+'.o')),str(asm)],capture_output=True,text=True,timeout=30)
                        self.assertEqual(0,result.returncode,result.stderr)

    def test_native_raw_walk_cache_modes_model_atomic_failures_and_malformed_entries(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
        if not nasm or not cc:self.skipTest('native paging requires NASM and SysV-capable GCC')
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            for mode in ('debug','release'):
                with self.subTest(mode=mode):
                    asm,obj=directory/(mode+'.asm'),directory/(mode+'.o')
                    exe=directory/(mode+('.exe' if os.name=='nt' else ''))
                    asm.write_text(self.compile(mode).assembly,encoding='utf-8')
                    result=subprocess.run([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',str(obj),str(asm)],capture_output=True,text=True,timeout=30)
                    self.assertEqual(0,result.returncode,result.stderr)
                    flags=[] if os.name=='nt' else ['-no-pie']
                    result=subprocess.run([cc,'-std=c11','-O2','-D__USE_MINGW_ANSI_STDIO=1','-Wall','-Wextra','-Werror',*flags,str(FIXTURES/'paging_probe.c'),str(obj),'-o',str(exe)],capture_output=True,text=True,timeout=30)
                    self.assertEqual(0,result.returncode,result.stderr)
                    result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=45)
                    self.assertEqual(0,result.returncode,result.stdout+result.stderr)
                    self.assertIn('paging independent raw walk/model/atomicity/malformed checks passed',result.stdout)


if __name__=='__main__':unittest.main()
