"""Native SMP ownership/state policy and real assembly contracts, no AP yet."""
from pathlib import Path
import hashlib,json,os,subprocess,unittest,uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
ROOT=Path(__file__).resolve().parents[1]
class SMPTests(unittest.TestCase):
    def test_native_state_trampoline_icr_and_tlb_retention(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
        if not nasm or not cc:self.skipTest('requires NASM and native GCC')
        directory=ROOT/'build/test/p6-smp/host'/('run-'+uuid.uuid4().hex[:12]);directory.mkdir(parents=True)
        inputs=[*sorted((ROOT/'kernel/smp').glob('*')),ROOT/'include/smp.inc',ROOT/'tests/smp_native_probe.dg',ROOT/'tests/smp_probe.c',Path(__file__)]
        hashes=lambda:{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        before=hashes();(directory/'source-before.json').write_text(json.dumps(before,indent=2)+'\n')
        def run(cmd,d,name):
            value=subprocess.run(list(map(str,cmd)),cwd=ROOT,capture_output=True,text=True,timeout=40)
            (d/(name+'.json')).write_text(json.dumps(dict(command=list(map(str,cmd)),returncode=value.returncode,stdout=value.stdout,stderr=value.stderr),indent=2)+'\n')
            self.assertEqual(0,value.returncode,value.stdout+value.stderr);return value
        for mode in ('debug','release'):
            d=directory/mode;d.mkdir()
            compilation=compile_file(ROOT/'tests/smp_native_probe.dg',roots=[ROOT/'tests',ROOT/'kernel',ROOT/'lang/std'],mode=mode)
            (d/'probe.asm').write_text(compilation.assembly)
            objects=[]
            for name,source in (('probe',d/'probe.asm'),('bootstrap',ROOT/'kernel/smp/bootstrap.asm')):
                obj=d/(name+'.o');objects.append(obj)
                run([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-I',str(ROOT/'include')+os.sep,'-o',obj,source],d,name+'-assemble')
            exe=d/('probe.exe' if os.name=='nt' else 'probe')
            run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),ROOT/'tests/smp_probe.c',*objects,'-o',exe],d,'link')
            run([exe],d,'actual-native-model')
        after=hashes();(directory/'source-after.json').write_text(json.dumps(after,indent=2)+'\n');self.assertEqual(before,after)
