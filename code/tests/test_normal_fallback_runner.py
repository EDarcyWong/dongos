"""Actual fallback runner host controls; deliberately starts no VM."""
import copy,importlib.util,struct,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];PATH=ROOT/'build/test/p6-normal-fallback-candidate/run_normal_fallback_qemu.py'
def module():
 s=importlib.util.spec_from_file_location('normal_fallback_runner',PATH);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def fixture(count=2):
 r=[0]*28;r[:10]=[1,count,count,count-1,count*2097152,count*1536,count*512,0,10,20];r[20]=0xffffd40010000000;r[26]=31
 c=[];regs=[]
 for cpu in range(count):
  context=[0]*32;context[0]=r[20]+cpu*256;context[1:5]=[cpu,cpu,4,1];context[13:16]=[0xffffd40020000000+cpu*8192,0xffffd40020000040+cpu*8192,0xffffd40020001000+cpu*8192];context[25]=1;c.append(context)
  regs.append(dict(CS=0x33 if cpu==0 else 8,SS=0x2b if cpu==0 else 16,GS_base=0 if cpu==0 else context[0],CR3=0x123001 if cpu==0 else 0x500000,CR4=1<<17 if cpu==0 else 0,GDT=context[13],IDT=context[15],TR_base=context[14],TR=24))
 process=bytearray(16*1288);struct.pack_into('<2Q',process,0,1,0x123000);legacy=[0]*8;legacy[4]=0x500000;legacy[6]=1
 return r,c,legacy,process,regs
class Tests(unittest.TestCase):
 def test_one_exact_explicit_owned_qemu_smp_argument(self):
  m=module();original=['qemu','-smp','4','-m','2G'];self.assertEqual(['qemu','-smp','2','-m','2G'],m.topology_command(original,2));self.assertEqual('4',original[2]);self.assertEqual('1',m.topology_command(original,1)[2])
  for bad in ([],['qemu','-smp'],['qemu','-smp','4','-smp','2'],['qemu','-smp=4']):
   with self.subTest(args=bad),self.assertRaises(ValueError):m.topology_command(bad,2)
  with self.assertRaises(ValueError):m.topology_command(original,4)
 def test_actual_report_online_count_and_independent_mask(self):
  m=module()
  for count in(1,2):
   r,c,l,p,reg=fixture(count);m.decode_smp(struct.pack('<28Q',*r),count);s=m.fallback_state(r,c,l,0,p,reg,0,0,count);self.assertEqual(count,s['online_count']);self.assertEqual((1<<count)-1,s['online_mask'])
  r,*_=fixture()
  for offset,value in [(1,4),(2,3),(3,0),(26,30),(27,1),(7,1),(12,1)]:
   bad=list(r);bad[offset]=value
   with self.subTest(offset=offset),self.assertRaises(ValueError):m.decode_smp(struct.pack('<28Q',*bad),2)
 def test_wrong_domain_or_bsp_or_old_ap_ownership_cannot_pass(self):
  m=module();r,c,l,p,reg=fixture();m.fallback_state(r,c,l,0,p,reg,0,0,2)
  for domain,enabled in[(1,0),(0,1)]:
   with self.assertRaises(ValueError):m.fallback_state(r,c,l,0,p,reg,domain,enabled,2)
  for cpu,key,value in[(0,'CS',8),(0,'GS_base',c[0][0]),(0,'CR3',0x999001),(1,'GS_base',c[0][0]),(1,'CR3',0x888000),(1,'CR4',1<<17),(1,'GDT',c[0][13])]:
   bad=copy.deepcopy(reg);bad[cpu][key]=value
   with self.subTest(cpu=cpu,key=key),self.assertRaises(ValueError):m.fallback_state(r,c,l,0,p,bad,0,0,2)
  bad=copy.deepcopy(c);bad[1][2]=bad[0][2]
  with self.assertRaises(ValueError):m.fallback_state(r,bad,l,0,p,reg,0,0,2)
 def test_each_hmp_request_contains_selected_cpu(self):
  m=module();g=object.__new__(m.FallbackGuest);g.qmp=mock.Mock();g.hmp(1,'info registers');g.qmp.request.assert_called_once_with('human-monitor-command',{'command-line':'info registers','cpu-index':1})
 def test_constructor_only_changes_its_owned_command_then_restores_builder(self):
  m=module();got=[]
  def parent(g,*args,**kw):got.append(m.settings.builder.qemu_command('esp','state'))
  with mock.patch.object(m.settings.builder,'qemu_command',return_value=['qemu','-smp','4'])as original,mock.patch.object(m.life.ProcessGuest,'__init__',parent):
   g=m.FallbackGuest(cpus=2);self.assertEqual([['qemu','-smp','2']],got);self.assertIs(m.settings.builder.qemu_command,original);self.assertFalse(g._constructing)
 def test_constructor_failure_captures_before_owned_cleanup(self):
  m=module();events=[]
  def parent(g,*args,**kw):g.qmp=object();g.process=SimpleNamespace(poll=lambda:None);g.close();raise TimeoutError('actual failed boot')
  with mock.patch.object(m.life.ProcessGuest,'__init__',parent),mock.patch.object(m.life.ProcessGuest,'close',side_effect=lambda:events.append('close')),mock.patch.object(m.FallbackGuest,'capture_failure',side_effect=lambda:events.append('capture')):
   with self.assertRaisesRegex(TimeoutError,'actual failed'):m.FallbackGuest(cpus=2)
  self.assertEqual(['capture','close'],events)
  g=object.__new__(m.FallbackGuest);g._constructing=True;g._early_captured=False;g.qmp=object();g.process=SimpleNamespace(poll=lambda:None);g.state=Path('unused')
  with mock.patch.object(m.FallbackGuest,'capture_failure',side_effect=ValueError('capture')),mock.patch.object(m.storage,'write_json',side_effect=OSError('disk')),mock.patch.object(m.life.ProcessGuest,'close')as close:g.close();close.assert_called_once()
 def test_normal_activation_requires_actual_selector_calls_and_default_no_vm(self):
  m=module();symbols=dict(service_runtime_begin=0x1000,user_smp_normal_policy=0x3000,user_smp_boot_begin=0x4000,user_context_cpu=0x5000);code=bytearray(384)
  for at,target in[(10,0x3000),(40,0x4000)]:code[at]=0xe8;struct.pack_into('<i',code,at+1,target-(0x1000+at+5))
  with mock.patch.object(m,'verify_build',return_value={'test':False}),mock.patch.object(m,'read_elf_symbols',return_value=symbols),mock.patch.object(m,'elf_bytes',return_value=bytes(code)):self.assertEqual({'test':False},m.identity(Path('esp')))
  code[10]=0x90
  with mock.patch.object(m,'verify_build',return_value={'test':False}),mock.patch.object(m,'read_elf_symbols',return_value=symbols),mock.patch.object(m,'elf_bytes',return_value=bytes(code)),self.assertRaisesRegex(ValueError,'selector'):m.identity(Path('esp'))
  with mock.patch.object(m,'identity',return_value={'normal':'source-bound'}),mock.patch.object(m,'FallbackGuest',side_effect=AssertionError('unexpected VM')),mock.patch.object(sys,'argv',['runner','--reuse-esp',str(ROOT/'build/test/no-real-esp')]):self.assertEqual(0,m.main())
if __name__=='__main__':unittest.main(verbosity=2)
