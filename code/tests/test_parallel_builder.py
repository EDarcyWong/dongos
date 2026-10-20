"""Execute the current arena builder with real paging; arena/CPU mocks only."""
# Tests the tracked current implementation, not a replay of unavailable candidate sources.
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'kernel'
BASE_REVISION=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
class Tests(unittest.TestCase):
 def test_real_guard_withdrawal_and_held_failure(self):
  files=[BASE/'sched/parallel.dg',BASE/'sched/multicore.dg',BASE/'sched/parallel_boot.dg',ROOT/'kernel/mm/paging.dg',ROOT/'tests/parallel_builder_probe.dg',ROOT/'tests/parallel_builder_startup.dg',ROOT/'tests/parallel_builder_resources.dg',ROOT/'tests/parallel_builder_probe.c',Path(__file__),BASE/'mm/huge_page_plan.dg']
  before={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};out=ROOT/'build/test/p6-builder-native'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);evidence={};nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
  controls={'skip-first-guard':('try guard(block.virtual);',''),'skip-barrier':('bridge.runtime_flush_root();try paging.reclaim','try paging.reclaim'),'ignore-global-hold':('FAILED=true;scheduler.failstop();','FAILED=true;')}
  def run(args,d,label):
   args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60);(d/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
  for mode in ('debug','release'):
   for variant in ('normal',*controls):
    d=out/(mode+'-'+variant);stage=d/'source';(stage/'boot').mkdir(parents=True);(stage/'sched').mkdir();source=files[2].read_text()
    if variant!='normal':old,new=controls[variant];self.assertEqual(1,source.count(old));source=source.replace(old,new)
    (stage/'sched/parallel_boot.dg').write_text(source);(stage/'sched/parallel.dg').write_bytes(files[0].read_bytes());(stage/'sched/multicore.dg').write_bytes(files[1].read_bytes());(stage/'boot/memory_startup.dg').write_bytes(files[5].read_bytes());(stage/'boot/service_memory.dg').write_bytes(files[6].read_bytes())
    for name in ('mm/paging.dg','mm/paging_errors.dg','mm/errors.dg','mm/huge_page_plan.dg','smp/context.dg'):
     target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/'kernel'/name).read_bytes())
    (stage/'runtime_probe.dg').write_text('module runtime_probe;unsafe extern "sysv64" fn pb_barrier()void;pub unsafe fn runtime_flush_root()void{unsafe{pb_barrier();}return;}')
    entry=stage/'parallel_builder_probe.dg';entry.write_bytes(files[4].read_bytes());c=compile_file(entry,roots=[stage],mode=mode);asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o';r=run([nasm,'-f','win64'if os.name=='nt'else'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
    exe=d/('probe.exe'if os.name=='nt'else'probe');r=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([]if os.name=='nt'else['-no-pie']),files[7],obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
    for scenario in (('normal','early','late')if variant=='normal'else('normal',)):
     r=run([exe,scenario],d,scenario);self.assertEqual(0 if variant=='normal' else 1,r.returncode,r.stdout+r.stderr);evidence[mode+'-'+variant+'-'+scenario]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
  after={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};self.assertEqual(before,after);(out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_binding='tracked-current-source',historical_candidate_replay=False,base_revision=BASE_REVISION,real_paging=True,arena_and_cpu_operations_mocked=True,actual_ap_executed=False,source_sha256=after,sources_unchanged=True,evidence=evidence),indent=2)+'\n');print('PARALLEL_BUILDER_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
