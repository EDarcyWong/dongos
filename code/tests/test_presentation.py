"""Execute real SSE2/NT presentation on alignment/size/color pixel oracles."""
from pathlib import Path
import os,subprocess,unittest,uuid,json,hashlib,time
from lang.tests.test_dongc import tool,nasm_flags
ROOT=Path(__file__).resolve().parents[1]
class PresentationTests(unittest.TestCase):
    def test_native_pixels_guards_and_bad_color_control(self):
        state=ROOT/'build/test/p7-desktop/presentation'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
        nasm=tool('nasm','NASM');cc=tool('gcc','CC');self.assertTrue(nasm);self.assertTrue(cc)
        inputs=[ROOT/'services/lib/syscalls.asm',ROOT/'services/gfx/accelerated.asm',ROOT/'tests/presentation_probe.c',Path(__file__)]
        before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        (state/'source-before.json').write_text(json.dumps(before,indent=2))
        bridge_raw=inputs[0].read_text();graphics_raw=inputs[1].read_text()
        for kind in ('normal','bad-color','bad-alpha','bad-copy','bad-opacity'):
            negative=kind!='normal'
            d=state/kind;d.mkdir();raw_bridge=bridge_raw;raw_graphics=graphics_raw
            if kind=='bad-color':
                self.assertEqual(1,raw_bridge.count('    ror r10d,16\n'))
                raw_bridge=raw_bridge.replace('    ror r10d,16\n','    rol r10d,8 ; actual bad color\n')
            if kind=='bad-alpha':
                start=raw_graphics.index('\nsvc_composite_rows:\n')
                end=raw_graphics.index('\nglobal svc_composite_opacity_rows\n',start)
                body=raw_graphics[start:end];needle='    psrlw xmm1,8\n';self.assertEqual(1,body.count(needle))
                raw_graphics=raw_graphics[:start]+body.replace(needle,'    psrlw xmm1,7 ; actual bad alpha\n')+raw_graphics[end:]
            if kind=='bad-copy':
                needle='    movdqu [rsi+48],xmm3\n';self.assertEqual(1,raw_graphics.count(needle))
                raw_graphics=raw_graphics.replace(needle,'    movdqu [rsi+48],xmm2 ; actual wrong copied lane\n')
            if kind=='bad-opacity':
                start=raw_graphics.index('\nsvc_composite_opacity_rows:\n')
                body=raw_graphics[start:];needle='    psrlw xmm0,8\n';self.assertEqual(1,body.count(needle))
                body=body.replace(needle,'    inc qword [rel presentation_bad_opacity_hits]\n    psrlw xmm0,7 ; actual doubled opacity\n')
                raw_graphics='extern presentation_bad_opacity_hits\n'+raw_graphics[:start]+body
            # Freeze both assembly inputs per run; concurrent root work cannot
            # make different controls silently exercise different source bytes.
            source=d/'bridge.asm';source.write_text(raw_bridge)
            graphics=d/'graphics.asm';graphics.write_text(raw_graphics)
            fmt='win64' if os.name=='nt' else 'elf64';obj=d/'bridge.o';gfx=d/'graphics.o';exe=d/('probe.exe' if os.name=='nt' else 'probe')
            commands=[[nasm,'-f',fmt,*nasm_flags(nasm),'-D_start=svc_unused_start','-o',str(obj),str(source)],
                [nasm,'-f',fmt,*nasm_flags(nasm),'-o',str(gfx),str(graphics)],
                [cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),str(ROOT/'tests/presentation_probe.c'),str(obj),str(gfx),'-o',str(exe)]]
            for i,cmd in enumerate(commands):
                started=time.monotonic()
                r=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
                (d/f'build-{i}.json').write_text(json.dumps(dict(command=cmd,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr,elapsed_seconds=time.monotonic()-started),indent=2))
                self.assertEqual(0,r.returncode,r.stderr)
            started=time.monotonic()
            r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=60)
            (d/'actual.json').write_text(json.dumps(dict(command=[str(exe)],returncode=r.returncode,stdout=r.stdout,stderr=r.stderr,elapsed_seconds=time.monotonic()-started),indent=2))
            self.assertEqual(1 if negative else 0,r.returncode,r.stdout+r.stderr)
            if negative:
                self.assertIn('opacity pixel/guard failed' if kind=='bad-opacity' else 'copy pixel/guard failed' if kind=='bad-copy' else 'composition pixel/guard failed' if kind=='bad-alpha' else 'presentation pixel/guard failed',r.stderr)
                if kind=='bad-opacity':self.assertRegex(r.stderr,r'bad_hits=[1-9][0-9]*')
            else:
                self.assertRegex(r.stdout,r'(12672 cases avx2=0|25344 cases avx2=1)')
                self.assertRegex(r.stdout,r'(6336|12672) premultiplied alpha cases')
                self.assertIn('opacity oracle passed: 592128 cases alpha=0..256',r.stdout)
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        (state/'source-after.json').write_text(json.dumps(after,indent=2))
        self.assertEqual(before,after,'presentation sources changed during native validation')
