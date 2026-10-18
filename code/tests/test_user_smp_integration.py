"""Compile the complete isolated CPL3 union and every architectural object.

No full OS link, loader build or virtual machine is executed.
"""
import hashlib,importlib.util,json,os,subprocess,unittest,uuid
from pathlib import Path
from unittest import mock
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
from tools.gen_offsets import generate
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'build/test/p6-cpl3-integration-candidate'
def builder():
 spec=importlib.util.spec_from_file_location('p6_cpl3_build',BASE/'tools/build.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def native_prepare(b):
 # Explicitly pinned historical source union, never an OS-build override. The
 # parent is promoting independent P6 changes; preserve the e63/786c contract.
 snapshot=ROOT/'build/test/p6-cpl3-integration-native/run-dfe2da3bac0e'
 return lambda output:b.prepare_frozen_native(output,snapshot)
class Tests(unittest.TestCase):
 def test_complete_graph_and_privileged_architecture_objects(self):
  b=builder();out=ROOT/'build/test/p6-cpl3-integration-native'/('run-'+uuid.uuid4().hex[:12]);stage,manifest,hashes=native_prepare(b)(out);before=hashes();candidate=b.candidate_inputs();nasm=tool('nasm','NASM');self.assertTrue(nasm);evidence={}
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
  # The source selector defaults off. An explicit non-test or non-desktop
  # selector is a compile-time error, not a silently enabled production mode.
  for label,defines in [('default-off',['-DP1_TEST=0','-DRUNTIME_LEVEL=7']),('non-test',['-DP1_TEST=0','-DRUNTIME_LEVEL=7','-DP6_USER_SMP=1']),('non-desktop',['-DP1_TEST=1','-DRUNTIME_LEVEL=6','-DP6_USER_SMP=1'])]:
   r=run([nasm,'-f','elf64',*nasm_flags(nasm),'-I',str(out)+os.sep,'-I',str(ROOT/'include')+os.sep,*defines,stage/'services_run.asm','-o',out/(label+'.o')],label);self.assertEqual(0 if label=='default-off'else 1,r.returncode,r.stderr)
   if label!='default-off':self.assertIn('isolated test desktop',r.stderr)
  self.assertEqual(before,hashes());self.assertEqual(candidate,b.candidate_inputs());(out/'validation-summary.json').write_text(json.dumps(dict(passed=True,candidate_only=True,full_dg_graph_compiled=True,all_architecture_elf_and_coff_assembled=True,os_link_executed=False,vm_executed=False,native_only_frozen_snapshot=manifest['native_only_frozen_snapshot'],actual_ap_cpl3_executed=False,candidate_sha256=candidate,production_kernel_sha256=manifest['production_kernel_sha256'],evidence=evidence),indent=2)+'\n');print('USER_SMP_INTEGRATION_EVIDENCE',out)
 def test_isolated_prepare_and_explicit_user_selector_routing(self):
  b=builder();out=ROOT/'build/test/p6-cpl3-routing'/('run-'+uuid.uuid4().hex[:12]);commands=[];assembled=[]
  def execute(command):
   command=list(map(str,command));commands.append(command)
   if 'lang.dongc'in command:
    path=Path(command[command.index('--emit-layout')+1]);types=[]if command[-1].endswith('trace_loader.dg')else[dict(name='Report',full_name='sched.parallel_live.Report',kind='struct',size=8,alignment=8,fields=[dict(name='version',offset=0,size=8)])];path.write_text(json.dumps(dict(schema=1,target='x86_64-dongos-elf',types=types)))
  def assembly(source,output,**kwargs):assembled.append((str(source),kwargs));return Path(output)/(Path(source).stem+'.o')
  def build(**kwargs):
   o=kwargs['output'];b.production.execute([os.sys.executable,'-m','lang.dongc','--root',str(ROOT/'boot'),'--emit-layout',str(o/'trace-layout.json'),str(ROOT/'boot/trace_loader.dg')]);b.production.execute([os.sys.executable,'-m','lang.dongc','--root',str(ROOT/'kernel'),'--emit-layout',str(o/'layout.json'),str(ROOT/'kernel/smp_probe.dg')]);b.production.assemble(ROOT/'kernel/services_run.asm',o,fmt='elf64',test=True,stage='p1',defines={'RUNTIME_LEVEL':7});b.production.execute(['ld.lld','-nostdlib','-o',str(o/'kernel.elf'),'original.o']);return o/'esp'
  with mock.patch.object(b,'prepare',side_effect=native_prepare(b)),mock.patch.object(b.production,'execute',execute),mock.patch.object(b.production,'assemble',assembly),mock.patch.object(b.production,'build',build):
   esp=b.build(out,user_smp=True)
  self.assertEqual(out.resolve()/'esp',esp);self.assertEqual(9,len(assembled));self.assertEqual(1,assembled[0][1]['defines']['P6_USER_SMP']);self.assertTrue(all(Path(p).is_relative_to(out.resolve()/'source/kernel')for p,_ in assembled));self.assertEqual(8,len([p for p in commands[-1]if p.endswith('.o')])-1)
  self.assertIn(str(ROOT/'boot'),commands[0]);self.assertEqual(str(ROOT/'boot/trace_loader.dg'),commands[0][-1]);self.assertFalse(any('source/kernel'in s for s in commands[0]))
  for kwargs in (dict(user_smp=True,test=False),dict(user_smp=True,runtime_level=6),dict(user_workload=True),dict(user_smp=True,user_case='omit-xstate'),dict(user_smp=True,user_workload=True,user_case='other')):
   with self.assertRaises(ValueError):b.build(out,**kwargs)
 def test_workload_source_and_negative_object_routing(self):
  from tools import user_services
  b=builder();out=ROOT/'build/test/p6-cpl3-routing'/('run-'+uuid.uuid4().hex[:12]);selected=[];roots_seen=[];assembled=[]
  def execute(command):
   if '-pie'in command:
    p=Path(command[command.index('-o')+1]);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'recorded-test-elf-'+p.parent.name.encode())
  def assembly(source,output,**kwargs):assembled.append((Path(source),kwargs));return Path(output)/(Path(source).stem+'.o')
  def compile_service(source,*,roots,**kwargs):roots_seen.append((Path(source),list(roots)));return None
  def service(source,output,**kwargs):
   selected.append((Path(source),Path(output)));user_services.compile_file(source,roots=[ROOT/'services']);user_services.execute(['ld.lld','-pie','-o',str(output/'program.elf'),'program.o']);return output/'program.elf'
  def build(**kwargs):
   for name in('echo','fault','waiter','ipc_peer','fs_reader','terminal'):
    user_services.build_service(ROOT/'services/apps'/(name+'.dg'),kwargs['output']/'services'/name.replace('_','-'))
   b.production.execute(['ld.lld','-nostdlib','-o',str(kwargs['output']/'kernel.elf'),'original.o']);return kwargs['output']/'esp'
  with mock.patch.object(b,'prepare',side_effect=native_prepare(b)),mock.patch.object(b.production,'execute',execute),mock.patch.object(b.production,'assemble',assembly),mock.patch.object(b.production,'build',build),mock.patch.object(user_services,'build_service',service),mock.patch.object(user_services,'compile_file',compile_service):
   b.build(out,user_smp=True,user_workload=True,user_case='omit-xstate')
  self.assertEqual([BASE/'services/apps/user_smp_worker.dg']*5,[p for p,_ in selected[:5]]);self.assertEqual(ROOT/'services/apps/terminal.dg',selected[5][0]);self.assertTrue(all(roots[0]==BASE/'services'for _,roots in roots_seen[:5]));self.assertEqual(ROOT/'services',roots_seen[5][1][0])
  self.assertEqual(5,sum(p.name=='user_smp_worker.asm'for p,_ in assembled));arch=[kw for p,kw in assembled if p.name=='user_arch.asm'];self.assertEqual(1,len(arch));self.assertEqual(1,arch[0]['defines']['USER_SMP_TEST_NO_XSTATE']);self.assertEqual(7,arch[0]['defines']['RUNTIME_LEVEL'])
  m=json.loads((out/'p6-cpl3-source.json').read_text());self.assertEqual({'echo','fault','waiter','ipc-peer','fs-reader'},set(m['workload_elf_sha256']));self.assertEqual('omit-xstate',m['user_case'])
if __name__=='__main__':unittest.main(verbosity=2)
