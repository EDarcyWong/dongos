"""Exercise trusted-range rebinding without dereferencing synthetic frames."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from lang.tests.test_dongc import tool,nasm_flags
ROOT=Path(__file__).resolve().parents[1]
class PanicBindingTests(unittest.TestCase):
    def test_old_stack_retired_future_and_ist_ranges_bounded(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
        self.assertTrue(nasm and cc)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            for fmt in ('elf64','win64'):
                for name,source,extra in [('panic',ROOT/'kernel/panic.asm',['-DPANIC_BINDING_TEST=1']),('ranges',ROOT/'tests/panic_binding_probe.asm',[])]:
                    r=subprocess.run([nasm,'-f',fmt,*nasm_flags(nasm),'-I',str(ROOT/'include')+os.sep,*extra,'-o',str(path/(name+fmt+'.o')),str(source)],capture_output=True,text=True,timeout=30)
                    self.assertEqual(0,r.returncode,r.stderr)
            fmt='win64' if os.name=='nt' else 'elf64'
            for opt in ('-O0','-O2'):
                exe=path/(opt[1:]+('.exe' if os.name=='nt' else ''))
                args=[cc,opt,'-Wall','-Wextra','-Werror']
                if os.name!='nt':args+=['-no-pie']
                r=subprocess.run(args+[str(ROOT/'tests/panic_binding_probe.c'),str(path/('panic'+fmt+'.o')),str(path/('ranges'+fmt+'.o')),'-o',str(exe)],capture_output=True,text=True,timeout=30)
                self.assertEqual(0,r.returncode,r.stderr)
                r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
                self.assertEqual(0,r.returncode,r.stdout+r.stderr)
                self.assertIn('panic binding probes passed',r.stdout)
if __name__=='__main__':unittest.main()
