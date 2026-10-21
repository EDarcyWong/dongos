"""Execute the old driver capacity checks with a real zero-argument program."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests import test_bootstrap_native_compiler as original
from lang.tests.test_dongc import tool,nasm_flags

ROOT=Path(__file__).resolve().parents[2]

class ZeroArgumentCapacityTests(unittest.TestCase):
    def test_real_old_driver_zero_capacity_and_emitted_program_both_modes(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
        self.assertTrue(nasm and cc,'real NASM/CC required; no skip')
        state=ROOT/'build/test/native-zero-args'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
        watched=[Path(__file__),Path(original.__file__),*sorted((ROOT/'lang/bootstrap').glob('*.dg'))]
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in watched};records=[]
        def command(args,name):
            p=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=600)
            records.append(dict(name=name,command=list(map(str,args)),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
            (state/(name+'.log')).write_text(p.stdout+p.stderr)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            return p
        (state/'probe').mkdir();entry=state/'probe/native_compiler.dg';entry.write_text(original.WRAPPER)
        result=compile_file(entry,roots=[state,ROOT/'lang',ROOT/'lang/std'],mode='debug')
        asm=state/'wrapper.asm';asm.write_text(result.assembly);objects={}
        for fmt,suffix in [('elf64','.o'),('win64','.obj')]:
            obj=state/('wrapper'+suffix);command([nasm,'-O0','-f',fmt,*nasm_flags(nasm),asm,'-o',obj],'wrapper-'+fmt);objects[fmt]=obj
        # The old broad Linux harness uses the native SysV C default. Spell
        # the same ABI explicitly on Windows; target Dong code stays exact.
        driver_source=original.DRIVER
        for name in ('dong_frontend_check','native_lower','native_emit'):
            driver_source=driver_source.replace('extern U '+name+'(','extern U __attribute__((sysv_abi)) '+name+'(')
        driver_source=driver_source.replace('void __dong_panic(','void __attribute__((sysv_abi)) __dong_panic(')
        c=state/'driver.c';c.write_text(driver_source);driver=state/'driver.exe'
        flags=[]if os.name=='nt'else['-no-pie'];obj=objects['win64'if os.name=='nt'else'elf64']
        command([cc,'-std=c11','-D__USE_MINGW_ANSI_STDIO=1','-O2','-Wall','-Wextra','-Werror',*flags,c,obj,'-o',driver],'driver-link')
        source=state/'unsupported.dg';source.write_text('module unsupported; var x:u64=1; pub fn f()u64{return x;}')
        for mode in (0,1):
            target=state/('target-'+str(mode)+'.asm')
            report=json.loads(command([driver,source,'unsupported.dg',target,mode],'zero-args-'+str(mode)).stdout)
            self.assertEqual((report['functions'],report['arguments']),(1,0))
            targets={}
            for fmt,suffix in [('elf64','.o'),('win64','.obj')]:
                target_obj=target.with_suffix(suffix);command([nasm,'-f',fmt,*nasm_flags(nasm),target,'-o',target_obj],'target-'+str(mode)+'-'+fmt);targets[fmt]=target_obj
            observer=state/('observer-'+str(mode)+'.c')
            observer.write_text('#include <stdint.h>\nextern uint64_t __attribute__((sysv_abi)) f(void) __asm__("'+original.label('unsupported','f')+'");\nint main(void){return f()!=1;}\n')
            exe=observer.with_suffix('.exe')
            command([cc,'-std=c11','-D__USE_MINGW_ANSI_STDIO=1','-O2','-Wall','-Wextra','-Werror',*flags,observer,targets['win64'if os.name=='nt'else'elf64'],'-o',exe],'observer-link-'+str(mode))
            command([exe],'observe-'+str(mode))
        after={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in watched}
        (state/'summary.json').write_text(json.dumps(dict(passed=True,records=records,source_before=before,source_after=after,source_stable=before==after),indent=2)+'\n')
        self.assertEqual(before,after)

if __name__=='__main__':unittest.main()
