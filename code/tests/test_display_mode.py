"""Execute the real Win64 GOP helper against ownership-aware EFI callbacks."""
from pathlib import Path
import os,subprocess,unittest,uuid,json
from lang.tests.test_dongc import tool,nasm_flags
ROOT=Path(__file__).resolve().parents[1]
class DisplayModeTests(unittest.TestCase):
    def test_modes_cleanup_and_missing_free_control(self):
        state=ROOT/'build/test/p7-desktop/gop'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
        nasm=tool('nasm','NASM');cc=tool('gcc','CC');self.assertTrue(nasm);self.assertTrue(cc)
        for bad in (False,True):
            d=state/('bad-free' if bad else 'normal');d.mkdir();source=ROOT/'boot/display_mode.asm'
            if bad:
                raw=source.read_text();needle='    call [r12+EFI_BOOT_SERVICES.FreePool]\n';self.assertEqual(1,raw.count(needle))
                source=d/'bad.asm';source.write_text(raw.replace(needle,'    xor eax,eax ; actual missing FreePool\n'))
            obj=d/'gop.o';exe=d/('probe.exe' if os.name=='nt' else 'probe')
            commands=[[nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-I'+str(ROOT/'include')+os.sep,'-o',str(obj),str(source)],
                [cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',*([] if os.name=='nt' else ['-no-pie']),str(ROOT/'tests/display_mode_probe.c'),str(obj),'-o',str(exe)]]
            for i,cmd in enumerate(commands):
                r=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
                (d/f'build-{i}.json').write_text(json.dumps(dict(command=cmd,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2))
                self.assertEqual(0,r.returncode,r.stderr)
            r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
            (d/'actual.json').write_text(json.dumps(dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2))
            self.assertEqual(1 if bad else 0,r.returncode,r.stdout+r.stderr)
            self.assertIn('GOP oracle failed' if bad else '12 actual',r.stderr if bad else r.stdout)
