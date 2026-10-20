"""Current-source CPL3 manager regression, not a historical candidate replay."""
from __future__ import annotations
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_xhci_kernel import dependencies,ROOT
class XhciManagerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.out=ROOT/'build/test/p8-xhci-manager'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
  cls.inputs=[ROOT/'services/drivers/device_manager.dg',ROOT/'tests/device_manager_probe.dg',ROOT/'tests/device_manager_probe.c',ROOT/'tests/xhci_manager_probe.c',Path(__file__)]
  cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
 @classmethod
 def tearDownClass(cls):
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs};(cls.out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
  if after!=cls.before:raise AssertionError('xHCI manager changed during verification')
 def command(self,args,d,name):
  r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90);(d/(name+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
 def native(self,mutation=None):
  for mode in ('debug','release'):
   d=self.out/((mutation+'-' if mutation else '')+mode);d.mkdir();stage=d/'source';overrides={}
   if mutation:
    s=(ROOT/'services/drivers/device_manager.dg').read_text()
    old,new={
     'bare-pid-contract':('(state.process&255)!=14||(state.process>>8)==0\n                    ||(state.process>>8)>0x0fff_ffff','state.process!=14'),
     'accept-zero-incarnation':('||(state.process>>8)==0',''),
    }[mutation];self.assertEqual(1,s.count(old));overrides['drivers.device_manager']=s.replace(old,new)
   dependencies(stage,['user.device_manager','drivers.device_manager'],overrides)
   c=compile_file(ROOT/'tests/device_manager_probe.dg',roots=[ROOT/'tests',stage],mode=mode);(d/'probe.asm').write_text(c.assembly);obj=d/'probe.o';nasm=tool('nasm','NASM');cc=tool('gcc','CC');self.assertTrue(nasm and cc)
   r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',str(obj),str(d/'probe.asm')],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
   exe=d/('probe.exe' if os.name=='nt' else 'probe');r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),str(ROOT/'tests/xhci_manager_probe.c'),str(obj),'-o',str(exe)],d,'link');self.assertEqual(0,r.returncode,r.stderr)
   scenarios=('absent','normal','spawn-failure','bad-config','bad-binding','catalog-failure','bare-pid','wrong-pid','incarnation-overflow','later-incarnation')
   if mutation:scenarios=({'bare-pid-contract':'normal','accept-zero-incarnation':'bare-pid'}[mutation],)
   for scenario in scenarios:
    r=self.command([str(exe),scenario],d,scenario)
    if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('device manager check failed line',r.stderr)
    else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('checks passed',r.stdout)
 def test_actual_launcher_and_legacy_regression(self):self.native()
 def test_real_catalog_tokens_reject_bad_manager_sources(self):
  for mutation in ('bare-pid-contract','accept-zero-incarnation'):self.native(mutation)
