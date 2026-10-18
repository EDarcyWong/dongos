"""Raw independent oracle checks; never execute QEMU/KVM or change a guest."""
from pathlib import Path
import importlib.util,struct,sys,unittest
BASE=Path(__file__).resolve().parent
from tests import boot_trace_oracle as oracle
KVM=dict(host_os='linux',actual_guest_boots=1,query_kvm=dict(enabled=True,present=True),artifact_bound=True)
PROOF=dict(cpuid15=[1,1000,1000000],cpuid80000007_edx=256)
def pack(words):
 words=list(words);words[28]=0;words[28]=(-sum(words))&0xffffffffffffffff;return struct.pack('<512Q',*words)
class OracleTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.path=BASE/'fixtures/boot-trace-normal.bin';cls.raw=cls.path.read_bytes();cls.words=list(struct.unpack('<512Q',cls.raw))
 def test_real_native_page_decodes_and_tcg_never_passes_kvm(self):
  d=oracle.decode(self.raw,PROOF,dict(host_os='windows',actual_guest_boots=1,query_kvm=dict(enabled=False,present=True),artifact_bound=True))
  self.assertFalse(d['kvm_gate_eligible']);self.assertFalse(d['kvm_gate_passed']);self.assertTrue(d['loader_to_shell_within_500ms']);self.assertEqual(449999000,d['intervals']['loader_to_interactive_shell_upper_ns'])
  self.assertFalse(d['actual_guest_or_kvm_executed_by_this_tool']);self.assertGreater(d['header']['clients_sequence'],d['header']['desktop_sequence'])
 def test_real_kernel_adapter_page_decodes(self):
  raw=(BASE/'fixtures/boot-trace-runtime.bin').read_bytes();d=oracle.decode(raw,PROOF,dict(host_os='windows',actual_guest_boots=0))
  self.assertFalse(d['kvm_gate_passed']);self.assertEqual(18,d['header']['configuration_count']);self.assertEqual(0x3c000,d['header']['client_mask'])
 def test_environment_and_invariant_evidence_cannot_be_skipped(self):
  for key in ('host_os','actual_guest_boots','query_kvm','artifact_bound'):
   env=dict(KVM);del env[key];self.assertFalse(oracle.decode(self.raw,PROOF,env)['kvm_gate_passed'])
  w=list(self.words);w[17]=2;proof=dict(PROOF,cpuid80000007_edx=0);self.assertFalse(oracle.decode(pack(w),proof,KVM)['kvm_gate_passed'])
  for proof in (None,dict(PROOF,cpuid15=[0,1,1]),dict(PROOF,cpuid15=[1,1001,1000000]),dict(PROOF,cpuid80000007_edx=0)):
   with self.subTest(proof=proof),self.assertRaises(ValueError):oracle.decode(self.raw,proof,KVM)
 def test_strict_500ms_bound_and_both_original_endpoints(self):
  for extra,expected in ((0,True),(1,False)):
   w=list(self.words);n=w[20]-1;target=500001000+extra;delta=target-w[32+n*6+1]
   for i in range(n,w[5]):w[32+i*6+1]+=delta
   w[18]+=delta;d=oracle.decode(pack(w),PROOF,KVM)
   self.assertEqual(expected,d['kvm_gate_passed']);self.assertEqual(500000000+extra,d['intervals']['loader_to_interactive_shell_upper_ns']);self.assertIn('ebs_to_first_desktop_upper_ns',d['intervals'])
 def test_raw_corruption_failure_tail_sequence_cpu_and_phase_rejected(self):
  cases=[]
  def changed(index,value):w=list(self.words);w[index]=value;cases.append(w)
  for index,value in [(0,0),(1,2),(3,64),(4,81),(5,81),(6,7),(7,1),(9,1),(18,0),(19,1),(20,1),(21,1),(22,1),(23,17),(24,0),(25,0),(26,0),(27,0),(30,1),(31,1),(32+79*6,1)]:changed(index,value)
  changed(32+1*6+1,self.words[33]);changed(32+2*6,1);changed(32+2*6+4,1<<32);changed(32+2*6+2,99)
  # Bad dependency, duplicate READY, and old configuration generation.
  start=next(i for i in range(self.words[5]) if self.words[32+i*6+2:32+i*6+4]==[6,5]);changed(32+start*6+5,1<<6);changed(32+start*6+5,1)
  consumer=next(i for i in range(self.words[5]) if self.words[32+i*6+2:32+i*6+4]==[6,2]);changed(32+consumer*6+5,0)
  ready=next(i for i in range(self.words[5]) if self.words[32+i*6+2:32+i*6+4]==[7,5]);changed(32+ready*6+4,2)
  for w in cases:
   with self.subTest(change=[i for i,(a,b) in enumerate(zip(self.words,w)) if a!=b]),self.assertRaises(ValueError):oracle.decode(pack(w),PROOF,KVM)
  bad=bytearray(self.raw);bad[4000]^=1
  with self.assertRaises(ValueError):oracle.decode(bytes(bad),PROOF,KVM)
 def test_three_actual_reference_forms_recompute_bounds(self):
  from tests.run_clock_calibration_qemu import SAMPLE_FIELDS
  for source,reference in ((2,dict(mask=0xffffffff,period_fs=10000000,hz=0)),(3,dict(mask=0xffffff,period_fs=0,hz=3579545)),(4,dict(mask=0xffffffff,period_fs=0,hz=3579545))):
   def sample(first,second):
    rate=3410000000;origin=reference['mask']-100;ticks=lambda ns:ns*1000000//reference['period_fs'] if reference['period_fs'] else ns*reference['hz']//1000000000
    a,b,c,d=first//3,first*2//3,10000000+second//3,10000000+second*2//3
    return dict(zip(SAMPLE_FIELDS,(origin,(1<<32)-1-a*62500000//1000000000,1000000000+b*rate//1000000000,(origin+ticks(first))&reference['mask'],(origin+ticks(10000000))&reference['mask'],(1<<32)-1-c*62500000//1000000000,1000000000+d*rate//1000000000,(origin+ticks(10000000+second))&reference['mask'])))
   samples=[sample(1350000,1000),sample(1200000,1000)]+[sample(1000+i*1000,2000+i*1000) for i in range(5)];result,_=oracle.select_clock(reference,samples);w=list(self.words)
   w[12:18]=[source,result['tsc_hz'],result['tsc_lower_hz'],result['tsc_upper_hz'],result['consistent'],5]
   for i in range(w[5]):
    if w[32+i*6+2]==13:w[32+i*6+3]=source;w[32+i*6+5]=result['tsc_hz']
   proof=dict(cpuid80000007_edx=256,reference=reference,samples=samples);d=oracle.decode(pack(w),proof,KVM);self.assertEqual(source,d['header']['clock_source'])
   bad=list(w);bad[14]+=1
   with self.assertRaises(ValueError):oracle.decode(pack(bad),proof,KVM)
if __name__=='__main__':unittest.main(verbosity=2)
