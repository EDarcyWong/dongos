"""Native actual ELF/paging/loader transactions; hardware boundaries mocked."""
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_service_ipc_cancellation import block
ROOT=Path(__file__).resolve().parents[1]
class Tests(unittest.TestCase):
    def test_sparse_elf_orphan_shared_pin_and_abort_order(self):
        names=('kernel/user/memory.dg','kernel/exec/elf.dg','kernel/mm/paging.dg',
               'tests/user_stage_fixture.dg','tests/user_stage_startup.dg','tests/user_stage_resources.dg',
               'tests/user_stage_probe.c','tests/test_user_stage.py')
        before={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
        out=ROOT/'build/test/user-stage'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);evidence={}
        def command(argv,d,label):
            argv=list(map(str,argv));r=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=60)
            (d/(label+'.json')).write_text(json.dumps(dict(argv=argv,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
        mutations={
          'omit-new-orphan-journal':('FRAME_COUNT+=1;try journal(index);','FRAME_COUNT+=1;'),
          'ignore-shared-survivor':('*recycled(index)==2||referenced_frame(index)','*recycled(index)==2||false'),
          'skip-abort-zero':('var word:usize=0;while word<512{*(((*record(index)).virtual as *u64)+word)=0;word+=1;}',
                             'var word:usize=512;while word<512{*(((*record(index)).virtual as *u64)+word)=0;word+=1;}'),
        }
        for mode in ('debug','release'):
            for variant in ('normal',*mutations):
                d=out/(mode+'-'+variant);(d/'kernel').mkdir(parents=True)
                for original in (ROOT/'kernel').rglob('*.dg'):
                    target=d/'kernel'/original.relative_to(ROOT/'kernel');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original.read_bytes())
                source=(ROOT/names[0]).read_text()
                if variant!='normal':
                    old,new=mutations[variant]
                    if variant=='skip-abort-zero':
                        # The final zero loop also exists in unshare_recycle.
                        # This negative control must alter only loader abort.
                        body=block(source,'unsafe fn abort_candidate(')
                        self.assertEqual(1,body.count(old));source=source.replace(body,body.replace(old,new))
                    else:self.assertEqual(1,source.count(old));source=source.replace(old,new)
                source=source.replace('pub const ALIASES: u64 = 0xffff_d000_0000_0000;','pub var ALIASES: u64 = 0;')
                # The fixture uses an extended frame table to reach reserve(),
                # while each owned alias is backed by a normal host allocation.
                path=d/'kernel/user/memory.dg';path.write_text(source+'\n'+(ROOT/names[3]).read_text())
                (d/'kernel/boot/memory_startup.dg').write_text((ROOT/'kernel/boot/memory_startup.dg').read_text()+'\n'+(ROOT/names[4]).read_text())
                (d/'kernel/boot/service_memory.dg').write_text((ROOT/names[5]).read_text())
                c=compile_file(path,roots=[d/'kernel',ROOT/'services',ROOT/'lang/std',ROOT/'lang/examples'],mode=mode)
                asm=d/'probe.asm';asm.write_text(c.assembly)
                mocked={'__dong_panic','user_current_root','user_pcid_flush_all','user_pcid_unbind','user_pcid_bind','user_entropy64','runtime_invalidate','runtime_copy_bytes','user_pcid_invalidate_root'}
                externs={m.group(1).lstrip('$') for m in re.finditer(r'^extern (\$?\w+)',c.assembly,re.M)}-mocked
                stub=d/'unused.asm';stub.write_text('bits 64\nsection .text\n'+''.join('global $'+x+'\n$'+x+': ud2\n' for x in sorted(externs)))
                objects=[]
                for label,file in (('probe',asm),('unused',stub)):
                    obj=d/(label+'.o');objects.append(obj)
                    r=command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),file,'-o',obj],d,'assemble-'+label);self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe')
                r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),ROOT/names[6],*objects,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                r=command([exe],d,'execute');self.assertEqual(0 if variant=='normal' else 1,r.returncode,r.stdout+r.stderr)
                evidence[mode+'-'+variant]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr,unused_bridges_trap=sorted(externs))
        after={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names};self.assertEqual(before,after)
        (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_sha256=after,sources_unchanged=True,
          production_load_abort_paging_elf_executed=True,hardware_and_physical_reservation_mocked=True,evidence=evidence),indent=2)+'\n')
        print('USER_STAGE_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
