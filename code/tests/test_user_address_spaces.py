"""Production DRNG layout and PCID operand lifetime, without privileged execution."""
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
class UserAddressTests(unittest.TestCase):
    def test_actual_layout_and_pcid_lifetimes(self):
        paths=('kernel/user/context.asm','kernel/user/memory.dg','kernel/user/entropy.dg',
               'tests/user_address_probe.dg','tests/user_address_probe.c','tests/user_pcid_probe.c',
               'tests/user_drng_probe.asm','tests/user_drng_probe.c','tests/test_user_address_spaces.py')
        before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
        out=ROOT/'build/test/p4-address'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
        evidence={}
        def command(args,d,label):
            args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
            (d/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n')
            return r
        def asm(src,obj,fmt,d,label):
            r=command([nasm,'-f',fmt,*nasm_flags(nasm),'-I'+str(ROOT/'include')+os.sep,'-o',obj,src],d,label)
            self.assertEqual(0,r.returncode,r.stderr)
        for mode in ('debug','release'):
            d=out/mode;d.mkdir();c=compile_file(ROOT/'tests/user_address_probe.dg',roots=[ROOT/'tests',ROOT/'kernel'],mode=mode)
            self.assertNotIn('rdtsc',c.assembly.lower());self.assertLessEqual(max(int(x.split(', ')[-1]) for x in c.assembly.splitlines() if x.strip().startswith('sub rsp, ')),256)
            source=d/'layout.asm';source.write_text(c.assembly);obj=d/'layout.o';fmt='win64' if os.name=='nt' else 'elf64'
            asm(source,obj,fmt,d,'assemble-layout')
            asm(source,d/'layout-other.o','elf64' if fmt=='win64' else 'win64',d,'assemble-layout-other')
            exe=d/('layout.exe' if os.name=='nt' else 'layout')
            r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),ROOT/'tests/user_address_probe.c',obj,'-o',exe],d,'link-layout');self.assertEqual(0,r.returncode,r.stderr)
            r=command([exe],d,'layout');self.assertEqual(0,r.returncode,r.stdout+r.stderr)
            evidence[mode]=dict(stdout=r.stdout)
            # Compile the complete memory module to verify preserved public ABI.
            memory=compile_file(ROOT/'kernel/user/memory.dg',roots=[ROOT/'kernel',ROOT/'services',ROOT/'lang/std',ROOT/'lang/examples'],mode=mode)
            layouts={v['full_name']:v for v in memory.layout_manifest['types']}
            self.assertEqual(1288,layouts['user.memory.Process']['size']);self.assertEqual(24,layouts['user.memory.Frame']['size'])
        d=out/'context';d.mkdir()
        for variant in ('normal','missing-first-use-reset'):
            path=ROOT/'kernel/user/context.asm'
            if variant!='normal':
                source=path.read_text();needle='    mov qword [r8 + 16], 0\n    mov eax, 1\n    ret\n.bad:'
                self.assertGreaterEqual(source.count(needle),1)
                path=d/'bad-context.asm';path.write_text(source.replace(needle,'    nop ; actual bad implementation retains previous generation\n    mov eax, 1\n    ret\n.bad:',1))
            obj=d/(variant+'.o');asm(path,obj,'win64' if os.name=='nt' else 'elf64',d,'assemble-'+variant)
            exe=d/(variant+('.exe' if os.name=='nt' else ''))
            r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),ROOT/'tests/user_pcid_probe.c',obj,'-o',exe],d,'link-'+variant);self.assertEqual(0,r.returncode,r.stderr)
            r=command([exe],d,'execute-'+variant)
            if variant=='normal':self.assertEqual(0,r.returncode,r.stdout+r.stderr)
            else:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('PCID operand failed line',r.stderr)
            evidence[variant]=dict(stdout=r.stdout,stderr=r.stderr,returncode=r.returncode)
        d=out/'drng';d.mkdir()
        for variant in ('normal','wrong-rdrand-retry-bound'):
            source=(ROOT/'kernel/user/context.asm').read_text()
            source=source.replace('    cpuid\n','    call user_test_cpuid\n').replace('    rdseed rax\n','    call user_test_seed\n').replace('    rdrand rax\n','    call user_test_random\n')
            if variant!='normal':
                self.assertEqual(1,source.count('    mov ecx, 10\n'));source=source.replace('    mov ecx, 10\n','    mov ecx, 11\n')
            source+='\nextern user_test_cpuid,user_test_seed,user_test_random\n'
            path=d/(variant+'.asm');path.write_text(source);obj=d/(variant+'.o');stub=d/'hardware.o';fmt='win64' if os.name=='nt' else 'elf64'
            asm(path,obj,fmt,d,'assemble-'+variant);asm(ROOT/'tests/user_drng_probe.asm',stub,fmt,d,'assemble-hardware-'+variant)
            exe=d/(variant+('.exe' if os.name=='nt' else ''))
            r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),ROOT/'tests/user_drng_probe.c',obj,stub,'-o',exe],d,'link-'+variant);self.assertEqual(0,r.returncode,r.stderr)
            r=command([exe],d,'execute-'+variant)
            if variant=='normal':self.assertEqual(0,r.returncode,r.stdout+r.stderr)
            else:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('DRNG retry failed line',r.stderr)
            evidence['drng-'+variant]=dict(stdout=r.stdout,stderr=r.stderr,returncode=r.returncode)
        after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths};self.assertEqual(before,after)
        (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_sha256=after,sources_unchanged=True,evidence=evidence,privileged_pcid_executed=False),indent=2)+'\n')
        print('USER_ADDRESS_EVIDENCE',out)
