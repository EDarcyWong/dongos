"""Read-only CPU transition policy: native semantics and both object formats."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from lang.dongc import compile_file
from lang.tests.test_dongc import tool, nasm_flags

ROOT=Path(__file__).resolve().parents[1]

class PreflightTests(unittest.TestCase):
    def test_modes_layouts_objects_and_native(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
        self.assertTrue(nasm and cc,'configured NASM and GCC required')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            for mode in ('debug','release'):
                with self.subTest(mode=mode):
                    result=compile_file(ROOT/'tests/preflight_probe.dg',roots=[ROOT/'tests',ROOT/'kernel'],mode=mode)
                    layouts={t['full_name']:t for t in result.layout_manifest['types']}
                    for name,size in (('State',48),('Plan',24)):
                        layout=layouts['boot.preflight.'+name]
                        self.assertEqual((size,8),(layout['size'],layout['alignment']))
                        self.assertEqual(list(range(0,size,8)),[f['offset'] for f in layout['fields']])
                    asm=path/(mode+'.asm');asm.write_text(result.assembly,encoding='utf-8')
                    for fmt in ('elf64','win64'):
                        obj=path/(mode+fmt+'.o')
                        r=subprocess.run([nasm,'-f',fmt,*nasm_flags(nasm),'-o',str(obj),str(asm)],capture_output=True,text=True,timeout=30)
                        self.assertEqual(0,r.returncode,r.stderr)
                    obj=path/(mode+('win64' if os.name=='nt' else 'elf64')+'.o')
                    exe=path/(mode+('.exe' if os.name=='nt' else ''))
                    args=[cc,'-std=c11','-O0' if mode=='debug' else '-O2','-Wall','-Wextra','-Werror']
                    if os.name!='nt':args+=['-no-pie']
                    r=subprocess.run(args+[str(ROOT/'tests/preflight_probe.c'),str(obj),'-o',str(exe)],capture_output=True,text=True,timeout=30)
                    self.assertEqual(0,r.returncode,r.stderr)
                    r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
                    self.assertEqual(0,r.returncode,r.stdout+r.stderr)
                    self.assertIn('preflight native checks passed',r.stdout)

if __name__=='__main__':unittest.main()
