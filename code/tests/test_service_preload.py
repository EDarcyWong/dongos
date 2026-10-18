"""Real preload retirement/launch fragments, with root mappings modelled."""
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_service_ipc_cancellation import block
ROOT=Path(__file__).resolve().parents[1]
class Tests(unittest.TestCase):
    def test_failed_provider_retires_unstarted_dependents_and_rebinds(self):
        names=('kernel/user/services.dg','kernel/user/processes.dg','kernel/ipc/handles.dg','kernel/ipc/core.dg',
               'tests/service_preload_adapter.dg','tests/service_preload_fixture.dg','tests/service_preload_probe.c','tests/test_service_preload.py')
        names+=('kernel/ipc/cap_notify.dg','kernel/ipc/shared_core.dg','kernel/user/memory.dg','tests/service_lifecycle_shared.dg','tests/service_compat_trace.dg','tests/service_compat_smp.dg')
        before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in names};source=(ROOT/names[0]).read_text()
        pieces=[block(source,s) for s in ('unsafe fn managed(','unsafe fn close_table(','unsafe fn revoke_loaded(',
          'unsafe fn retire_one(','unsafe fn discard_preloaded(','unsafe fn retire(','unsafe fn abort_launch(','unsafe fn launch(','unsafe fn owner_key(','unsafe fn accept(','unsafe fn cap_departed(','unsafe fn pending_call_enqueue(','unsafe fn pending_call_finish(','unsafe fn pending_call_pump(','unsafe fn pending_calls_departed(')]
        pending_globals=source[source.index('// One trusted request snapshot'):source.index('var WAIT_AFTER:')]
        fixture=(ROOT/names[5]).read_text().replace('// PRODUCTION_FUNCTIONS',pending_globals+'\n'+'\n'.join(pieces))
        variants={
          'ignore-preloads':('if PRELOADED[slot]&&slot<','if false&&PRELOADED[slot]&&slot<'),
          'forget-transitive-preloads':('affected|=1<<slot as u64;',''),
          'fabricate-unstarted-departure':('if incarnation!=0{DEPARTED[id]=incarnation;}','DEPARTED[id]=1;'),
          'keep-old-preloaded-root':('try revoke_loaded(id,0);','PRELOADED[id]=false;'),
          'discard-unrelated-unready':('((*CATALOG).configs[slot].dependencies&affected)!=0',
            '((*CATALOG).configs[slot].dependencies&~(1<<5))!=0'),
        }
        shared_model=(ROOT/'tests/service_lifecycle_shared.dg').read_text().replace('// EXACT_PRODUCTION_OBJECT_ABORT_OWNER',block((ROOT/'kernel/user/memory.dg').read_text(),'unsafe fn object_abort_owner('))
        out=ROOT/'build/test/service-preload'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);evidence={}
        def command(argv,d,label):
            argv=list(map(str,argv));r=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=60)
            (d/(label+'.json')).write_text(json.dumps(dict(argv=argv,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
        for mode in ('debug','release'):
            for variant in ('normal',*variants):
                d=out/(mode+'-'+variant);(d/'kernel').mkdir(parents=True);text=fixture
                if variant!='normal':old,new=variants[variant];self.assertEqual(1,text.count(old));text=text.replace(old,new)
                (d/'service_preload_fixture.dg').write_text(text);(d/'service_preload_adapter.dg').write_bytes((ROOT/names[4]).read_bytes())
                for extra in ('service_compat_trace.dg','service_compat_smp.dg'):(d/extra).write_bytes((ROOT/'tests'/extra).read_bytes())
                for original in ('user/processes.dg','user/abi.dg','ipc/core.dg','ipc/handles.dg','ipc/cap_notify.dg','ipc/shared_core.dg'):
                    target=d/'kernel'/original;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/'kernel'/original).read_bytes())
                shared_target=d/'kernel/user/shared_objects.dg';shared_target.parent.mkdir(parents=True,exist_ok=True);shared_target.write_text(shared_model)
                c=compile_file(d/'service_preload_fixture.dg',roots=[d,d/'kernel',ROOT/'services',ROOT/'lang/std'],mode=mode)
                asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o';r=command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe');r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),ROOT/names[6],obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                r=command([exe],d,'execute');self.assertEqual(0 if variant=='normal' else 1,r.returncode,r.stdout+r.stderr)
                evidence[mode+'-'+variant]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
        after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in names};self.assertEqual(before,after)
        (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_sha256=after,sources_unchanged=True,
          production_retire_and_launch_fragments_executed=True,real_catalog_capabilities_ipc=True,
          hardware_and_mapped_root_lifetime_modelled=True,actual_qemu_boots=0,actual_vmware_boots=0,evidence=evidence),indent=2)+'\n')
        print('SERVICE_PRELOAD_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
