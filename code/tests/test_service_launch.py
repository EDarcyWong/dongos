"""Exact production launch/abort/SPAWN/fatal fragments, real catalog and caps."""
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_service_ipc_cancellation import block
ROOT=Path(__file__).resolve().parents[1]
class Tests(unittest.TestCase):
    def test_atomic_launch_commit_partial_cap_cleanup_and_failstop(self):
        names=('kernel/user/services.dg','kernel/user/processes.dg','kernel/ipc/handles.dg','kernel/ipc/core.dg',
               'tests/service_launch_fixture.dg','tests/service_launch_memory.dg','tests/service_launch_resources.dg',
               'tests/service_launch_probe.c','tests/test_service_launch.py','tests/service_launch_trace.dg')
        names+=('kernel/ipc/cap_notify.dg','kernel/ipc/shared_core.dg','kernel/user/memory.dg','tests/service_lifecycle_shared.dg')
        before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in names}
        source=(ROOT/names[0]).read_text();parts=[block(source,s) for s in (
          'unsafe fn authority(','unsafe fn manager(','unsafe fn close_table(','unsafe fn abort_launch(','unsafe fn launch(')]
        spawn=block(source,'if code==proc.SPAWN||code==proc.EXEC{')
        fatal=block(source,'if LAUNCH_FAILED||memory.STAGE_FAILED')
        fragment='\n'.join(parts)+'\nunsafe fn process_call(frame:*abi.Frame)!usize{unsafe{let code=(*frame).rax;'+spawn+'}return error.InvalidCall;}\n'
        fixture=(ROOT/names[4]).read_text().replace('// PRODUCTION_FUNCTIONS',fragment).replace('// PRODUCTION_FATAL',fatal)
        trace='''
import service_launch_trace as trace;
pub unsafe fn start(c:*Catalog,id:usize,slot:usize,argument:u64,out:*abi.Snapshot)!void{unsafe{
    try start_impl(c,id,slot,argument,out);
    let observed=trace.launch_adapter_event(4,slot as u64,id as u64,(*out).generation,argument);
}return;}
'''
        catalog=(ROOT/names[1]).read_text();needle='pub unsafe fn start('
        self.assertEqual(1,catalog.count(needle));catalog=catalog.replace(needle,'unsafe fn start_impl(')+trace
        mutations={
          'catalog-published-before-stage':('    let generation=(*CATALOG).incarnation[slot]+1;',
            '    let generation=(*CATALOG).incarnation[slot]+1;try procs.start(CATALOG,id,slot,argument,&SNAPSHOT);'),
          'skip-partial-cap-close':('let closed=close_table(slot);','let closed=skip_close(slot);'),
          'skip-stage-abort':('let aborted=memory.stage_abort(slot);','let aborted=memory.skip_abort(slot);'),
          'ignore-failed-cleanup':(fatal[:fatal.index('{')+1],'if false{'),
          'late-slot-incarnation-check':('if (*CATALOG).incarnation[slot]>=0x0fff_ffff{return error.proc.Exhausted;}',''),
        }
        shared_model=(ROOT/'tests/service_lifecycle_shared.dg').read_text().replace('// EXACT_PRODUCTION_OBJECT_ABORT_OWNER',block((ROOT/'kernel/user/memory.dg').read_text(),'unsafe fn object_abort_owner('))
        out=ROOT/'build/test/service-launch'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);evidence={}
        def command(argv,d,label):
            argv=list(map(str,argv));r=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=60)
            (d/(label+'.json')).write_text(json.dumps(dict(argv=argv,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
        for mode in ('debug','release'):
            for variant in ('normal',*mutations):
                d=out/(mode+'-'+variant);(d/'kernel/user').mkdir(parents=True);text=fixture
                if variant!='normal':old,new=mutations[variant];self.assertEqual(1,text.count(old));text=text.replace(old,new)
                (d/'service_launch_fixture.dg').write_text(text);(d/'kernel/user/processes.dg').write_text(catalog)
                for original in ('ipc/core.dg','ipc/handles.dg','user/abi.dg','ipc/cap_notify.dg','ipc/shared_core.dg'):
                    target=d/'kernel'/original;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/'kernel'/original).read_bytes())
                shared_target=d/'kernel/user/shared_objects.dg';shared_target.parent.mkdir(parents=True,exist_ok=True);shared_target.write_text(shared_model)
                for p in (*names[5:7],names[9]):(d/Path(p).name).write_bytes((ROOT/p).read_bytes())
                c=compile_file(d/'service_launch_fixture.dg',roots=[d,d/'kernel',ROOT/'services',ROOT/'lang/std'],mode=mode)
                asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o'
                r=command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe')
                r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),ROOT/names[7],obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                r=command([exe],d,'execute');self.assertEqual(0 if variant=='normal' else 1,r.returncode,r.stdout+r.stderr)
                evidence[mode+'-'+variant]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
        after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in names};self.assertEqual(before,after)
        (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_sha256=after,sources_unchanged=True,
          production_launch_abort_spawn_fatal_fragments_executed=True,real_catalog_and_capabilities=True,
          memory_channels_identity_resources_mocked=True,actual_qemu_boots=0,actual_vmware_boots=0,evidence=evidence),indent=2)+'\n')
        print('SERVICE_LAUNCH_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
