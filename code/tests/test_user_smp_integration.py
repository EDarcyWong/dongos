"""Compile the complete tracked-current CPL3 graph and every architectural object.

No full OS link, loader build or virtual machine is executed.
"""
import hashlib,importlib.util,json,os,subprocess,unittest,uuid
from pathlib import Path
from unittest import mock
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
from tools.gen_offsets import generate
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT
def builder():
 from tests import current_smp_staging
 return current_smp_staging
def native_prepare(b):
 # Current source only. The unavailable e63/786c historical replay is retired.
 return b.prepare
class Tests(unittest.TestCase):
 def test_complete_graph_and_privileged_architecture_objects(self):
  b=builder();out=ROOT/'build/test/p6-cpl3-integration-native'/('run-'+uuid.uuid4().hex[:12]);stage,manifest,hashes=native_prepare(b)(out);before=hashes();candidate=b.source_inputs();nasm=tool('nasm','NASM');self.assertTrue(nasm);evidence={}
  for inc in (BASE/'include').glob('*.inc'):(out/inc.name).write_bytes(inc.read_bytes())
  for mode in ('debug','release'):
   c=compile_file(stage/'smp_probe.dg',roots=[stage,ROOT/'services',ROOT/'lang/examples',ROOT/'lang/std'],mode=mode);(out/(mode+'.asm')).write_text(c.assembly);(out/(mode+'-layout.json')).write_text(json.dumps(c.layout_manifest,indent=2)+'\n')
   layouts={v['full_name']:v for v in c.layout_manifest['types']};self.assertEqual(256,layouts['sched.user_entry_plan.Cpu']['size']);self.assertEqual(80,layouts['sched.user_boot.Report']['size']);self.assertEqual(200,layouts['user.abi.Frame']['size']);self.assertEqual(1288,layouts['user.memory.Process']['size']);self.assertEqual(192,layouts['sched.user_entry_plan.Metrics']['size']);self.assertEqual(120,layouts['sched.user_domain.Cpu']['size'])
   self.assertEqual(88,next(f['offset']for f in layouts['sched.user_domain.Domain']['fields']if f['name']=='cpus'));self.assertEqual(24,next(f['offset']for f in layouts['sched.user_domain.Cpu']['fields']if f['name']=='slot'))
   for filename,typename,alias in [('bootinfo_layout.inc','boot.abi.BootInfo','BootInfo'),('parallel_live_report.inc','sched.parallel_live.Report','ParallelLiveReport'),('smp_report.inc','smp.runtime.Report','SmpReport'),('runtime_view.inc','boot.runtime_view.View','RuntimeView'),('service_report.inc','user.services.Report','ServiceReport')]:
    (out/filename).write_text(generate(c.layout_manifest,typename,alias),encoding='ascii')
   evidence[mode+'_complete_graph_compiled']=True
  sources=['smp/bootstrap.asm','smp_runtime.asm','services_run.asm',*['sched/'+n+'.asm' for n in ('parallel','parallel_probe','parallel_live','user_entry','user_arch','user_bridge_arch','user_legacy','user_boot')]]
  def run(args,label):
   args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60);(out/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
  for relative in sources:
   for fmt in ('win64','elf64'):
    label=Path(relative).stem+'-'+fmt;args=[nasm,'-f',fmt,*nasm_flags(nasm),'-I',str(out)+os.sep,'-I',str(ROOT/'include')+os.sep,'-DP1_TEST=1','-DRUNTIME_LEVEL=7','-DP6_USER_SMP=1',stage/relative,'-o',out/(label+'.o')];r=run(args,label);self.assertEqual(0,r.returncode,r.stderr)
  for fmt in('win64','elf64'):
   r=run([nasm,'-f',fmt,*nasm_flags(nasm),'-I',str(out)+os.sep,'-I',str(ROOT/'include')+os.sep,'-DP1_TEST=1','-DRUNTIME_LEVEL=7','-DUSER_SMP_TEST_NO_XSTATE=1',stage/'sched/user_arch.asm','-o',out/('user-negative-'+fmt+'.o')],'user-negative-'+fmt);self.assertEqual(0,r.returncode,r.stderr)
  # Current production intentionally enables SMP at runtime7, including normal
  # builds; only an explicit non-desktop selection must be rejected.
  for label,defines in [('default-runtime7',['-DP1_TEST=0','-DRUNTIME_LEVEL=7']),('explicit-normal',['-DP1_TEST=0','-DRUNTIME_LEVEL=7','-DP6_USER_SMP=1']),('non-desktop',['-DP1_TEST=1','-DRUNTIME_LEVEL=6','-DP6_USER_SMP=1'])]:
   r=run([nasm,'-f','elf64',*nasm_flags(nasm),'-I',str(out)+os.sep,'-I',str(ROOT/'include')+os.sep,*defines,stage/'services_run.asm','-o',out/(label+'.o')],label);self.assertEqual(1 if label=='non-desktop'else 0,r.returncode,r.stderr)
   if label=='non-desktop':self.assertIn('requires desktop runtime7',r.stderr)
  self.assertEqual(before,hashes());self.assertEqual(candidate,b.source_inputs());(out/'validation-summary.json').write_text(json.dumps(dict(passed=True,current_source_only=True,historical_replay=False,full_dg_graph_compiled=True,all_architecture_elf_and_coff_assembled=True,os_link_executed=False,vm_executed=False,source_contract=manifest['contract'],actual_ap_cpl3_executed=False,current_source_sha256=candidate,staged_sha256=manifest['staged_sha256'],evidence=evidence),indent=2)+'\n');print('USER_SMP_INTEGRATION_EVIDENCE',out)
 def test_current_production_selector_and_architecture_routing(self):
  b=builder()
  for level in (6,7):
   out=ROOT/'build/test/current-cpl3-routing'/('run-'+uuid.uuid4().hex[:12]);plan=b.production_plan(out,runtime_level=level,test=False)
   names={Path(a['source']).name:a for a in plan['assemblies']}
   for name in ('services_run','user_entry','user_arch','user_bridge_arch','user_legacy','user_boot'):
    record=names[name+'.asm'];self.assertEqual(int(level==7),record['defines']['P6_USER_SMP']);self.assertIn(record['output'],plan['commands'][-1])
   self.assertIn(str(ROOT/'kernel/smp_probe.dg'),plan['commands'][0]);self.assertFalse(plan['built']);self.assertFalse((out/'kernel.elf').exists())
 def test_workload_source_and_negative_object_routing(self):
  from tests import current_user_smp_workload as workload
  expected={7:78117,8:88219,9:99323,10:104729,11:115249}
  for case in (None,'omit-xstate'):
   out=ROOT/'build/test/current-cpl3-workload-routing'/('run-'+uuid.uuid4().hex[:12])
   plan=workload.workload_plan(out,test=True,runtime_level=7,user_smp=True,user_case=case)
   routes=plan['workloads'];self.assertEqual(expected,{r['configuration']:r['argument']for r in routes})
   self.assertEqual({'echo','fault','waiter','ipc-peer','fs-reader'},{r['name']for r in routes})
   for route in routes:
    self.assertEqual(workload.FIXTURE/'services/apps/user_smp_worker.dg',Path(route['source']))
    self.assertEqual(workload.FIXTURE/'services/apps/user_smp_worker.asm',Path(route['assembly']))
    self.assertEqual(str(workload.FIXTURE/'services'),route['roots'][0]);self.assertFalse(Path(route['output']).exists())
   self.assertEqual(str(ROOT/'services/apps/gui_terminal.dg'),plan['unchanged_terminal']['source'])
   arch=plan['architecture'];self.assertEqual(str(ROOT/'kernel/sched/user_arch.asm'),arch['source'])
   self.assertEqual(dict(P1_TEST=1,RUNTIME_LEVEL=7,P6_USER_SMP=1,USER_SMP_TEST_NO_XSTATE=int(case=='omit-xstate')),arch['defines'])
   self.assertTrue(plan['synthetic_test_workload']);self.assertFalse(plan['historical_replay']);self.assertFalse(plan['built'])
   self.assertFalse(plan['os_link_executed']);self.assertFalse(plan['vm_executed']);self.assertFalse((out/'kernel.elf').exists())
   self.assertNotIn('workload_elf_sha256',plan) # A routing plan is not a built ELF receipt.
   for name,digest in plan['source_sha256'].items():self.assertEqual(digest,hashlib.sha256((ROOT/name).read_bytes()).hexdigest())
   self.assertEqual(plan,json.loads((out/'current-user-workload-plan.json').read_text()))
  for changes in ({'test':False},{'runtime_level':6},{'user_smp':False},{'user_case':'unknown'}):
   options=dict(test=True,runtime_level=7,user_smp=True);options.update(changes)
   with self.assertRaises(ValueError):workload.workload_plan(out,**options)
if __name__=='__main__':unittest.main(verbosity=2)
