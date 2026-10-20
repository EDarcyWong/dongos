"""Independent host controls for strict actual P6 acceptance. No VM."""
import copy,importlib.util,json,py_compile,sys,tempfile,unittest,struct
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tests'
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def snapshot():
 m=[[0]*24 for _ in range(4)]
 for metric in m:metric[18]=1<<18;metric[19]=7
 return dict(metrics=m,processes=[[0]*7 for _ in range(16)])
def launched():return {cfg:dict(token=(1<<8)|(cfg+1),generation=1,state=1,status=0)for cfg in range(7,12)}
def catalog():
 args={7:78117,8:88219,9:99323,10:104729,11:115249};states=[dict(state=2,status=0,generation=1,argument=0)for _ in range(32)]
 for cfg,arg in args.items():states[cfg]['argument']=arg
 states[9].update(state=4,status=6)
 return dict(sequence=2,snapshots=states,events=[dict(sequence=2,configuration=9,generation=1,process=266,state=4,status=6)])
class Tests(unittest.TestCase):
 def setUp(self):self.a=load(BASE/'current_user_smp_acceptance.py','actual_acceptance')
 def test_actual_four_cpu_xcr0_and_all_five_worker_avx(self):
  s=snapshot();values=[]
  for cfg,arg in self.a.ARGS.items():
   probe=[0]*24;probe[0:8]=[1,arg,cfg+1,1048576,1,0,2,1];probe[19:24]=[arg,cfg,1,128,0x534d5046494c4553]
   s['processes'][cfg]=[cfg+257,1,0x100000+cfg*4096,4,5,0,0]
   values.append(dict(cfg=cfg,slot=cfg,token=cfg+257,incarnation=1,probe=probe,root=0x100000+cfg*4096,argument=arg))
  self.a.workers(s,values,self.a.ARGS)
  for cpu in range(4):
   bad=copy.deepcopy(s);bad['metrics'][cpu][19]=3
   with self.subTest(cpu=cpu),self.assertRaisesRegex(ValueError,'XCR0'):self.a.workers(bad,values,self.a.ARGS)
  for cfg in self.a.ARGS:
   bad=copy.deepcopy(values);next(v for v in bad if v['cfg']==cfg)['probe'][7]=0
   with self.subTest(worker=cfg),self.assertRaisesRegex(ValueError,'AVX'):self.a.workers(s,bad,self.a.ARGS)
  for key,value in [('probe_cfg',8),('probe_inc',2),('argument',17),('syscalls',0),('fs',0)]:
   bad=copy.deepcopy(values)
   if key=='probe_cfg':bad[0]['probe'][20]=value
   elif key=='probe_inc':bad[0]['probe'][21]=value
   elif key=='argument':bad[0]['argument']=value
   elif key=='syscalls':bad[0]['probe'][4]=value
   else:bad[0]['probe'][23]=value
   with self.subTest(field=key),self.assertRaises(ValueError):self.a.workers(s,bad,self.a.ARGS)
 def test_fresh_exact_token_generation_argument_ud_negative(self):
  c=catalog();r=launched();self.a.negative_binding(c,r,1)
  for field,value in [('sequence',1),('process',267),('generation',2),('status',14)]:
   bad=copy.deepcopy(c);bad['events'][0][field]=value
   with self.subTest(event=field),self.assertRaises(ValueError):self.a.negative_binding(bad,r,1)
  for field,value in [('generation',2),('argument',42),('status',14)]:
   bad=copy.deepcopy(c);bad['snapshots'][9][field]=value
   with self.subTest(snapshot=field),self.assertRaises(ValueError):self.a.negative_binding(bad,r,1)
  bad=copy.deepcopy(c);bad['snapshots'][2]['state']=4
  with self.assertRaisesRegex(ValueError,'essential'):self.a.negative_binding(bad,r,1)
  for broken in ({k:v for k,v in r.items()if k!=11},{**r,11:r[10]}):
   with self.assertRaises(ValueError):self.a.negative_binding(c,broken,1)
  reused=copy.deepcopy(r);reused[11]['token']=(2<<8)|8
  self.a.negative_binding(c,reused,1)
  self.a.launched(reused,concurrent=False)
  with self.assertRaisesRegex(ValueError,'concurrent'):self.a.launched(reused)
  reused[11]['token']=reused[7]['token']
  with self.assertRaisesRegex(ValueError,'distinct full tokens'):self.a.launched(reused,concurrent=False)
 def test_counts_exact_trusted_offset_and_no_old_sequence_ratio(self):
  address=0xffffd40012340000;g=mock.Mock();g.kval.return_value=address
  g.readwords.return_value=[8,3,1,12,4,257,0x73]
  r=self.a.service_counts(g);self.assertEqual(16*8,r['calls']);self.assertEqual(16,g.readwords.call_count)
  for slot,call in enumerate(g.readwords.call_args_list):self.assertEqual(address+576+slot*56,call.args[0]);self.assertEqual(7,call.args[1])
  # The policy counters deliberately have no domain.sequence input: clock
  # optimization changes the old approximate two-barriers-per-call relation.
  g.readwords.return_value=[8,3,1,16,0,257,0x97];self.a.service_counts(g)
  g.readwords.return_value=[8,3,1,16,4,257,0x97]
  with self.assertRaises(ValueError):self.a.service_counts(g)
 def test_retire_needs_new_epoch_exact_ack_and_no_return_refs(self):
  before=dict(domain=[0]*15,processes=[[0]*7 for _ in range(16)]);before['domain'][8]=10;before['processes'][7][0]=123
  after=dict(domain=[0]*15,processes=[[0]*7 for _ in range(16)],threads=[[0]*8 for _ in range(64)],cpus=[[0]*15 for _ in range(4)],seen=[[[0]*3 for _ in range(16)]for _ in range(4)])
  after['domain'][8]=11
  for c in after['cpus']:c[7]=c[8]=11
  self.a.retirement(before,after,7)
  stale=copy.deepcopy(after);stale['domain'][8]=10
  for c in stale['cpus']:c[7]=c[8]=10
  with self.assertRaisesRegex(ValueError,'advance'):self.a.retirement(before,stale,7)
  for field in ('owner','ack','seen'):
   bad=copy.deepcopy(after)
   if field=='owner':bad['cpus'][2][1]=123
   elif field=='ack':bad['cpus'][2][8]=10
   else:bad['seen'][2][7][2]=1
   with self.subTest(field=field),self.assertRaises(ValueError):self.a.retirement(before,bad,7)
 def test_marker_or_bad_boot_never_seals_and_negative_avx_required(self):
  a=self.a;s=snapshot();s['metrics'][1][2]=1;record=dict(snapshot=s,catalog=catalog(),launched_workers=launched(),catalog_start_sequence=1,serial_marker_offset=100,serial_start_offset=90,actual_negative_busy_simd_assertion=True,actual_fault_status_6=True,actual_ap_user_timer=True)
  # Newly generated host fixture: actual hash-bound bytes, not guest evidence.
  from tests import run_current_user_smp_qemu as runner
  temporary=tempfile.TemporaryDirectory(prefix='current-seal-',dir=ROOT/'build/test');self.addCleanup(temporary.cleanup)
  out=Path(temporary.name);esp=out/'esp';esp.mkdir();(out/'source/kernel').mkdir(parents=True)
  (out/'source/kernel/probe.dg').write_text('host-only staged fixture');(out/'kernel.elf').write_bytes(b'host-only kernel fixture')
  elfs={}
  for name in runner.NAMES[7:12]:
   path=out/'services'/name/'program.elf';path.parent.mkdir(parents=True);path.write_bytes(('host-only '+name).encode());elfs[name]=runner.sha(path)
  sources={'tests/user_smp_oracle.py':runner.sha(ROOT/'tests/user_smp_oracle.py')}
  source=dict(schema=1,contract='current-user-smp-v1',source_root=str(ROOT.resolve()),esp=str(esp.resolve()),built=True,source_unchanged=True,test=True,runtime_level=7,user_smp=True,user_workload=True,user_case='omit-xstate',source_sha256=sources,staged_kernel_sha256={'kernel/probe.dg':runner.sha(out/'source/kernel/probe.dg')},kernel_elf_sha256=runner.sha(out/'kernel.elf'),workload_elf_sha256=elfs)
  (out/'current-user-smp-source.json').write_text(json.dumps(source))
  artifacts={'kernel.elf':source['kernel_elf_sha256'],**{'services/'+n+'/program.elf':h for n,h in elfs.items()}}
  (out/'build-inputs.json').write_text(json.dumps(dict(test=True,runtime_level=7,source_unchanged=True,graphics_case=None,source_sha256=sources,artifacts=artifacts)))
  def seal(value):
   value=copy.deepcopy(value);value['esp']=str(esp);value['boot_receipts']=[]
   for i,boot in enumerate(value['boots']):
    path=out/('boot-'+str(i)+'.json');path.write_text(json.dumps(boot));value['boot_receipts'].append(dict(path=str(path.resolve()),sha256=runner.sha(path)))
   return a.seal_negative_result(value)
  result=dict(passed=True,execute=True,runner_inputs_unchanged=True,all_started_guests_stopped=True,actual_qemu_boots=2,same_disk_reboot_verified=True,source_identity=source,negative_xstate=True,boots=[record,copy.deepcopy(record)])
  self.assertTrue(seal(result)['passed']);self.assertFalse(seal(result)['guest_execution_verified'])
  for key,value in [('actual_qemu_boots',1),('runner_inputs_unchanged',False),('all_started_guests_stopped',False),('same_disk_reboot_verified',False)]:
   bad=copy.deepcopy(result);bad[key]=value
   with self.subTest(field=key),self.assertRaises(ValueError):seal(bad)
  bad=copy.deepcopy(result);bad['boots'][0]['serial_marker_offset']=89
  with self.assertRaisesRegex(ValueError,'fresh'):seal(bad)
  bad=copy.deepcopy(result);bad['boots'][0]['snapshot']['metrics'][1][19]=3
  with self.assertRaisesRegex(ValueError,'XCR0'):seal(bad)
  bad=copy.deepcopy(result);bad['boots'][0]['snapshot']['metrics'][1][2]=0
  with self.assertRaisesRegex(ValueError,'timer'):seal(bad)
  with self.assertRaises(ValueError):a.seal_result(dict(passed=True,serial=b'DONGOS_P6_USER_WORKER_BAD'.hex()))
 def test_normal_one_two_cpu_fallback_is_explicit_and_not_smp_acceptance(self):
  good=dict(normal_runtime=7,test=False,cpu_count=2,smp_steps=31,user_domain_pointer=0,services_smp_enabled=False,legacy_busy=1,essential_ready=list(range(7)),desktop_ready=True,filesystem_read_and_sync=True,actual_bsp_cpl=3,ap_online=1)
  self.assertTrue(self.a.normal_fallback(good))
  for key,value in [('cpu_count',3),('smp_steps',30),('user_domain_pointer',123),('services_smp_enabled',True),('actual_bsp_cpl',0),('ap_online',0),('test',True),('filesystem_read_and_sync',False)]:
   bad=dict(good);bad[key]=value
   with self.subTest(field=key),self.assertRaises(ValueError):self.a.normal_fallback(bad)
 def test_revised_runner_syntax_and_default_does_not_start_vm(self):
  path=BASE/'run_current_user_smp_qemu.py';m=load(path,'new_acceptance_runner')
  with tempfile.TemporaryDirectory(dir=ROOT/'build/test')as d:py_compile.compile(str(path),cfile=str(Path(d)/'runner.pyc'),doraise=True)
  with mock.patch.object(m,'identity',return_value={'explicit':'test-only'}),mock.patch.object(m,'UserGuest',side_effect=AssertionError('unexpected VM')),mock.patch.object(sys,'argv',['runner','--reuse-esp',str(ROOT/'build/test/not-an-esp')]):self.assertEqual(0,m.main())
 def test_revised_runner_actual_worker_requires_upper_ymm_not_user_flag(self):
  m=load(BASE/'run_current_user_smp_qemu.py','revised_worker');g=object.__new__(m.UserGuest);g.esp=ROOT/'build/test/no-real-esp'
  arg,slot,inc,cfg=99323,7,2,9;cat=dict(slots=[0]*32,incarnations=[0]*16,snapshots=[{}for _ in range(32)]);cat['slots'][cfg]=slot;cat['incarnations'][slot]=inc;cat['snapshots'][cfg]['process']=(inc<<8)|(slot+1)
  g.catalog=mock.Mock(return_value=cat);g.verify_process=mock.Mock(return_value=dict(root=0x123000,bias=0x10000));g.effective=mock.Mock(return_value=dict(present=True,effective_user=True,effective_nx=True,physical=0x300000));g.physical=mock.Mock(return_value=struct.pack('<Q',arg))
  p=[0]*24;p[:8]=[1,arg,slot+1,1048576,1,0,2,1];p[8]=6;p[16:18]=[100,200];p[19:24]=[arg,cfg,inc,128,0x534d5046494c4553]
  raw=bytearray(1024)
  for at,value in [(160,0x1122334455667788^arg),(400,0x8877665544332211^(slot+1)),(816,0xcafebabedeadbeef^arg^(slot+1))]:struct.pack_into('<Q',raw,at,value)
  g.read=mock.Mock(return_value=bytes(raw));g.user=mock.Mock(return_value=struct.pack('<24Q',*p));s=snapshot();s['contexts']=[[0,0,i]+[0]*29 for i in range(4)];s['processes'][slot]=[(inc<<8)|(slot+1),inc,0x123000,4,5,0,0]
  with mock.patch.object(m,'read_elf_symbols',return_value={m.storage.symbol('apps.user_smp_worker','PROBE'):0x100}):
   self.assertTrue(g.worker(cfg,arg,s)['actual_upper_ymm_verified']);g.effective.assert_called_with(0x123000,0x44000000)
   p[7]=0;g.user.return_value=struct.pack('<24Q',*p)
   with self.assertRaisesRegex(ValueError,'upper-YMM'):g.worker(cfg,arg,s)
   p[7]=1;g.user.return_value=struct.pack('<24Q',*p);raw[816]^=1;g.read.return_value=bytes(raw)
   with self.assertRaisesRegex(ValueError,'upper YMM15'):g.worker(cfg,arg,s)
 def test_revised_runner_negative_rejects_old_marker_or_stale_token_fault(self):
  m=load(BASE/'run_current_user_smp_qemu.py','revised_negative')
  for fresh,event_token,ok in [(True,266,True),(False,266,False),(True,267,False)]:
   g=mock.Mock();g.raw=bytearray(b'DONGOS_P6_USER_WORKER_BAD\r\n');before=catalog();before['sequence']=1;before['events']=[];g.catalog.return_value=before;s=snapshot();s['metrics'][1][2]=1;g.snapshot.return_value=s
   g.kval.return_value=0xffffd40012340000;g.readwords.return_value=[8,3,1,12,4,257,0x73]
   def shell(command,**kw):
    name=command.split()[1];cfg=m.NAMES.index(name)
    if cfg==11:
     final=catalog();final['events'][0]['process']=event_token;g.catalog.return_value=final
     if fresh:g.raw.extend(b'DONGOS_P6_USER_WORKER_BAD\r\n')
    return dict(command=command,response_hex=('RUN OK '+name+' token='+str(launched()[cfg]['token'])+' generation=1 state=1 status=0\r\n').encode().hex())
   g.shell.side_effect=shell
   with self.subTest(fresh=fresh,event_token=event_token),mock.patch.object(m,'close_gui',return_value=[]),mock.patch.object(m.life,'check_boot_dag'),mock.patch.object(m.time,'monotonic',side_effect=[0,100]):
    if ok:self.assertTrue(m.negative(g)['actual_fault_status_6'])
    else:
     with self.assertRaisesRegex(ValueError,'missing actual SIMD'):m.negative(g)
if __name__=='__main__':unittest.main(verbosity=2)
