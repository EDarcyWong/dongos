"""Direct execution of production process retirement, with private state fixtures."""
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
class UserReclaimTests(unittest.TestCase):
    def test_actual_retirement_shared_aliases_pin_zeroing_and_negative(self):
        names=('kernel/user/memory.dg','kernel/user/entropy.dg','kernel/boot/memory_startup.dg','kernel/mm/paging.dg',
               'tests/user_reclaim_fixture.dg','tests/user_reclaim_startup.dg','tests/user_reclaim_probe.c','tests/test_user_reclaim.py')
        before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in names}
        out=ROOT/'build/test/p4-reclaim'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);evidence={}
        def command(args,d,label):
            args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
            (d/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
        for mode in ('debug','release'):
            evidence[mode]={}
            for variant in ('normal','ignore-shared-reference','wrong-share-target','scan-unrelated-frames'):
                d=out/(mode+'-'+variant);(d/'kernel').mkdir(parents=True)
                for original in (ROOT/'kernel').rglob('*.dg'):
                    target=d/'kernel'/original.relative_to(ROOT/'kernel');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original.read_bytes())
                source=(ROOT/names[0]).read_text()
                if variant=='ignore-shared-reference':
                    needle='if referenced_frame(index)'
                    self.assertEqual(1,source.count(needle));source=source.replace(needle,'if false')
                elif variant=='wrong-share-target':
                    needle='&SPACES[target],target_virtual,mapping.physical,flags'
                    self.assertEqual(1,source.count(needle));source=source.replace(needle,'&SPACES[target],source_virtual,mapping.physical,flags')
                elif variant=='scan-unrelated-frames':
                    needle='if *recycled(index)==4 {'
                    self.assertEqual(1,source.count(needle));source=source.replace(needle,'if *recycled(index)==0||*recycled(index)==4 {')
                signature='unsafe fn referenced(physical:u64)bool {'
                self.assertEqual(1,source.count(signature));source=source.replace(signature,'unsafe fn referenced_impl(physical:u64)bool {')
                path=d/'kernel/user/memory.dg';path.write_text(source+'\n'+(ROOT/names[4]).read_text())
                (d/'kernel/boot/memory_startup.dg').write_text((ROOT/names[2]).read_text()+'\n'+(ROOT/names[5]).read_text())
                c=compile_file(path,roots=[d/'kernel',ROOT/'services',ROOT/'lang/std',ROOT/'lang/examples'],mode=mode)
                asm=d/'probe.asm';asm.write_text(c.assembly)
                # Unused hardware bridges trap if reached. Explicit C mocks
                # implement only the called current-root/invalidation boundary.
                mocked={'__dong_panic','user_current_root','user_pcid_flush_all','user_pcid_unbind','runtime_invalidate','runtime_copy_bytes','user_pcid_invalidate_root'}
                externs={m.group(1).lstrip('$') for m in re.finditer(r'^extern (\$?\w+)',c.assembly,re.M)}-mocked
                stub=d/'unused.asm';stub.write_text('bits 64\nsection .text\n'+''.join('global $'+x+'\n$'+x+': ud2\n' for x in sorted(externs)))
                objects=[]
                for name,source in (('probe',asm),('unused',stub)):
                    obj=d/(name+'.o');objects.append(obj)
                    r=command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',obj,source],d,'assemble-'+name);self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe')
                r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),ROOT/names[6],*objects,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                r=command([exe],d,'execute')
                if variant=='normal':self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('user reclaim checks passed',r.stdout)
                else:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('reclaim check failed line',r.stderr)
                evidence[mode][variant]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr,unused_bridges_trap=sorted(externs))
        after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in names};self.assertEqual(before,after)
        (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_sha256=after,sources_unchanged=True,evidence=evidence,hardware_invalidation_mocked=True,production_destroy_fresh_paging_executed=True),indent=2)+'\n')
        print('USER_RECLAIM_EVIDENCE',out)
