"""Pure controls for the actual CPL3 runner; no VM or privileged execution."""
import copy,hashlib,importlib.util,json,struct,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
from tests import user_smp_oracle as o
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'build/test/p6-cpl3-integration-candidate'
def runner():
 s=importlib.util.spec_from_file_location('user_smp_actual_runner',BASE/'tests/run_user_smp_qemu.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def fixture():
 a=0xffff800011000000;domain=0xffff800010000000;r=[1,0,1,4,15,domain,a-4096,a+65536,0x900000,1000000000]
 h=[0]*32;h[0]=a+32768;h[2]=a;h[4]=r[8];h[7]=o.MAGIC;h[8]=r[7]+256;h[9]=r[5];h[10]=1;h[11]=r[7];h[12]=4;h[13]=1
 h[14:22]=[a+256,a+320,a+512,h[0]-16384,a+65536,a+98304,a+131072,a+4608]
 h[25]=2;h[29:32]=[1000000000,1000000000,62500000]
 m=[2,1,1,2,64,0,a,0,0,0xd01,0x0020000800000000,0xffffffff80001111,0x77700,a+256,55,a+512,4095,24,(1<<17)|(1<<18),7,h[0],0,0,0]
 c=[0]*32;c[:4]=[h[8],1,3,4]
 entry=dict(address=a,syscall_entry=m[11],fmask=0x77700)
 return r,h,m,c,entry
class Tests(unittest.TestCase):
 def test_actual_hardware_readback_and_negative_controls(self):
  r,h,m,c,e=fixture();o.header(1,h,m,r,c,e)
  # Each mutation removes a distinct hardware/ownership requirement.
  for position,value in [(5,1),(6,0),(7,1),(8,1),(9,0),(10,0),(11,0),(12,0),(13,0),(14,4095),(15,0),(16,55),(17,0),(18,1<<7),(20,0),(21,1)]:
   bad=list(m);bad[position]=value
   with self.subTest(metric=position),self.assertRaises(ValueError):o.header(1,h,bad,r,c,e)
  for position,value in [(2,h[2]+8192),(7,0),(8,h[8]+64),(9,0),(10,0),(14,0),(15,0),(16,0),(21,0),(25,1),(26,1)]:
   bad=list(h);bad[position]=value
   with self.subTest(header=position),self.assertRaises(ValueError):o.header(1,bad,m,r,c,e)
  h[13]=0;m[18]&=~(1<<17);m[1]=0;o.header(1,h,m,r,c,e)
  m[1]=1
  with self.assertRaises(ValueError):o.header(1,h,m,r,c,e)
 def test_user_hardware_owner_and_real_register_parser(self):
  r,h,m,_,_=fixture();slot=7;token=0x108;c=[2,token,1,slot,0,0,0,2,2,1,2,3,4,0,5];p=[[0]*7 for _ in range(16)];p[slot]=[token,1,0x123000,4,5,0,0];t=[[0]*8 for _ in range(64)];t[slot]=[2,8,15,1,64,64,1,4]
  text='CR0=80010033 CR3=0000000000123008 CR4=0000000000020020 RIP=0000000010011000 RSP=0000007fff000ff0\nCS =0033 0000000000000000 00000000 00affb00 DPL=3 CS64\nSS =002b 0000000000000000 00000000 00cff300 DPL=3 DS\nGS =0000 0000000000000000 00000000 00000000\n'
  text+='GDT= %016x 00000037\nIDT= %016x 00000fff\nTR =0018 %016x 00000067 00008900\n'%(h[14],h[16],h[15])
  reg=o.registers(text);self.assertTrue(o.cpu_ownership(1,c,p,t,h,reg))
  for key,value in [('CR3',0x123009),('CR4',1<<7),('GS_base',h[2]),('CS',0x23),('SS',0x1b)]:
   bad=dict(reg);bad[key]=value
   with self.subTest(register=key),self.assertRaises(ValueError):o.cpu_ownership(1,c,p,t,h,bad)
  for offset,value in [(0,1),(1,0),(2,2),(3,8)]:
   bad=list(c);bad[offset]=value
   with self.subTest(owner=offset),self.assertRaises(ValueError):o.cpu_ownership(1,bad,p,t,h,reg)
  with self.assertRaises(ValueError):o.registers(text.replace('CR4=','MISSING='))
 def test_actual_busy_worker_xstate_fixedva_and_migration(self):
  arg,pid,cfg,inc=781624,8,9,2;v=[0]*24;v[:8]=[1,arg,pid,1048576,1,0,3,1];v[8]=(1<<1)|(1<<3);v[16:18]=[100,200];v[19:22]=[arg,cfg,inc];v[22:24]=[128,0x534d5046494c4553]
  self.assertEqual([1,3],o.worker(v,arg,pid,cfg,inc,[0,1,2,3]))
  raw=bytearray(1024)
  for at,value in [(160,0x1122334455667788^arg),(400,0x8877665544332211^pid),(816,0xcafebabedeadbeef^arg^pid)]:struct.pack_into('<Q',raw,at,value)
  o.xstate(raw,arg,pid,True)
  for at in (160,400,816):
   bad=bytearray(raw);bad[at]^=1
   with self.subTest(xsave=at),self.assertRaises(ValueError):o.xstate(bad,arg,pid,True)
  for at,value in [(5,1),(19,arg-1),(20,cfg-1),(21,inc-1),(8,1<<100),(3,0),(17,50),(6,256),(6,0xffffffff),(22,0),(23,0)]:
   bad=list(v);bad[at]=value
   with self.subTest(probe=at),self.assertRaises(ValueError):o.worker(bad,arg,pid,cfg,inc,[0,1,2,3])
  for apics in([0,1,1,3],[0,1,2,256],[0,1,2,0xffffffff]):
   with self.assertRaises(ValueError):o.worker(v,arg,pid,cfg,inc,apics)
 def test_warm_and_negative_cannot_pass_on_arbitrary_failure(self):
  a=dict(slot=7,incarnation=1,token=264,physical=0x300000,argument=17);b=dict(slot=7,incarnation=2,token=520,physical=0x301000,argument=19);o.warm_reuse(a,b,17)
  for key in ('slot','incarnation','token','physical','argument'):
   bad=dict(b);bad[key]=a[key]
   # same physical slot is mandatory; unlike other fields, mutate it away.
   if key=='slot':bad[key]=8
   with self.subTest(warm=key),self.assertRaises(ValueError):o.warm_reuse(a,bad,17)
  states=[dict(state=4,status=6)];ess=[dict(state=2)]*7;o.negative(True,states,[0,1,0,0],ess)
  for marker,s,t,e in [(False,states,[0,1,0,0],ess),(True,[dict(state=4,status=14)],[0,1,0,0],ess),(True,states,[1,0,0,0],ess),(True,states,[0,1,0,0],[dict(state=4)]*7)]:
   with self.assertRaises(ValueError):o.negative(marker,s,t,e)
 def test_actual_idle_lapic_and_per_request_cpu_index(self):
  text='dumping local APIC state for CPU 3\nLVTT\t0x00010040\nTimer\tDCR=0x3 divide=16 initial_count = 0 current_count = 0\n';self.assertEqual(0x10040,o.idle_lapic(text)['lvtt'])
  for old,new in [('00010040','00030040'),('initial_count = 0','initial_count = 1'),('current_count = 0','current_count = 1')]:
   with self.assertRaises(ValueError):o.idle_lapic(text.replace(old,new))
  module=runner();g=object.__new__(module.UserGuest);g.qmp=mock.Mock();g.qmp.request.return_value=text
  self.assertEqual(text,g.hmp(3,'info lapic'));g.qmp.request.assert_called_once_with('human-monitor-command',{'command-line':'info lapic','cpu-index':3})
 def test_default_prepare_never_starts_guest(self):
  module=runner()
  with mock.patch.object(module,'identity',return_value={'explicit':'test-only'}),mock.patch.object(module,'UserGuest',side_effect=AssertionError('unexpected VM')),mock.patch.object(sys,'argv',['runner','--reuse-esp',str(ROOT/'build/test/not-a-real-esp')]):self.assertEqual(0,module.main())
 def test_completed_test_build_binds_candidate_and_workload_sources(self):
  module=runner()
  with tempfile.TemporaryDirectory(prefix='p6-source-',dir=ROOT/'build/test')as temporary:
   base=Path(temporary)/'candidate';out=Path(temporary)/'out';esp=out/'esp';esp.mkdir(parents=True)
   for tree in('kernel','tools','include','services'):(base/tree).mkdir(parents=True)
   worker=base/'services/worker.asm';worker.write_text('actual original source');kernel=out/'source/kernel/entry.dg';kernel.parent.mkdir(parents=True);kernel.write_text('compiled kernel union')
   (out/'kernel.elf').write_bytes(b'completed-artifact');elfs={}
   for name in module.NAMES[7:12]:
    path=out/'services'/name/'program.elf';path.parent.mkdir(parents=True);path.write_bytes(b'completed '+name.encode());elfs[name]=module.sha(path)
   m=dict(built=True,source_unchanged=True,test=True,runtime_level=7,user_smp=True,user_workload=True,user_case=None,esp=str(esp.resolve()),
          actual_kernel_sha256={'kernel/entry.dg':module.sha(kernel)},candidate_sha256={'services/worker.asm':module.sha(worker)},workload_elf_sha256=elfs,production_base_sha256={})
   (base/'base-sha256.json').write_text('{}')
   (out/'p6-cpl3-source.json').write_text(json.dumps(m));(out/'build-inputs.json').write_text(json.dumps(dict(runtime_level=7,test=True,graphics_case=None,source_unchanged=True,source_sha256={},artifacts={'kernel.elf':module.sha(out/'kernel.elf')})))
   with mock.patch.object(module,'BASE',base):
    self.assertEqual(m,module.identity(esp,False))
    worker.write_text('tampered after completed build')
    with self.assertRaisesRegex(ValueError,'candidate builder/workload/include'):module.identity(esp,False)
    worker.write_text('actual original source');(out/'kernel.elf').write_bytes(b'tampered artifact')
    with self.assertRaisesRegex(ValueError,'artifact changed'):module.identity(esp,False)
    with self.assertRaisesRegex(ValueError,'explicitly selected'):module.identity(esp,True)
if __name__=='__main__':unittest.main(verbosity=2)
