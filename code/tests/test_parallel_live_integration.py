"""Compile/stage the tracked-current live AP graph; no OS link or VM execution."""
import copy,hashlib,importlib.util,json,os,struct,subprocess,unittest,uuid
from pathlib import Path
from unittest import mock
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
from tools.gen_offsets import generate
from tests import parallel_live_oracle as oracle
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT
def load_builder():
 from tests import current_smp_staging
 return current_smp_staging
def sections(path):
 b=path.read_bytes();count=struct.unpack_from('<H',b,2)[0];opt=struct.unpack_from('<H',b,16)[0];result={}
 for i in range(count):
  off=20+opt+40*i;name=b[off:off+8].split(b'\0')[0].decode();result[name]=struct.unpack_from('<I',b,off+16)[0]
 return {n:result.get(n,0)for n in ('.text','.rodata','.data','.bss')}
class Tests(unittest.TestCase):
 def test_arena_effective_supervisor_permissions_and_owned_tables(self):
  root=0x400000;va=0xffffd40001200000;physical=0x30000000
  tables={root+i*4096:bytearray(4096)for i in range(4)}
  shifts=(39,30,21,12)
  for i,shift in enumerate(shifts):
   entry=root+(i+1)*4096|7 if i<3 else physical|0x8000000000000003
   struct.pack_into('<Q',tables[root+i*4096],((va>>shift)&511)*8,entry)
  read=lambda pa:bytes(tables[pa])
  self.assertEqual(physical|0x8000000000000003,oracle.supervisor_leaf(root,va,read))
  # Broad USER ancestors do not expose a supervisor leaf. Every real effective
  # permission and the trusted 128-page ownership boundary must still hold.
  for level,entry in ((3,physical|0x8000000000000007),(1,root+8192|5),
                      (3,physical|3),(2,physical|0x8000000000000083),
                      (1,root+128*4096|7),(1,root|7)):
   offset=((va>>shifts[level])&511)*8;table=tables[root+level*4096]
   old=struct.unpack_from('<Q',table,offset)[0];struct.pack_into('<Q',table,offset,entry)
   with self.subTest(level=level,entry=entry),self.assertRaises((ValueError,KeyError)):
    oracle.supervisor_leaf(root,va,read)
   struct.pack_into('<Q',table,offset,old)
  struct.pack_into('<Q',tables[root+3*4096],((va>>12)&511)*8,0)
  self.assertEqual(0,oracle.supervisor_leaf(root,va,read))

 def test_current_production_union_compiles_and_arch_assembles(self):
  b=load_builder();out=ROOT/'build/test/p6-live-native'/('run-'+uuid.uuid4().hex[:12]);stage,manifest,hashes=b.prepare(out);before=hashes();candidate_before=b.source_inputs();nasm=tool('nasm','NASM');self.assertTrue(nasm);evidence={}
  def run(args,label):
   args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=300);(out/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');self.assertEqual(0,r.returncode,r.stderr)
  for mode in ('debug','release'):
   c=compile_file(stage/'smp_probe.dg',roots=[stage,ROOT/'services',ROOT/'lang/examples',ROOT/'lang/std'],mode=mode);(out/(mode+'.asm')).write_text(c.assembly);(out/(mode+'-layout.json')).write_text(json.dumps(c.layout_manifest,indent=2)+'\n')
   layouts={v['full_name']:v for v in c.layout_manifest['types']};self.assertEqual(oracle.BYTES,layouts['sched.parallel_live.Report']['size']);self.assertEqual(160,layouts['sched.parallel.Cpu']['size']);self.assertEqual(12960,layouts['sched.multicore.Engine']['size'])
   (out/'parallel_live_report.inc').write_text(generate(c.layout_manifest,'sched.parallel_live.Report','ParallelLiveReport'),encoding='ascii');(out/'smp_report.inc').write_text(generate(c.layout_manifest,'smp.runtime.Report','SmpReport'),encoding='ascii')
   evidence[mode+'_full_graph_compiled']=True
  for name,relative in [('bootstrap','smp/bootstrap.asm'),('smp_runtime','smp_runtime.asm'),('parallel','sched/parallel.asm'),('parallel_probe','sched/parallel_probe.asm'),('parallel_live','sched/parallel_live.asm')]:
   for format_ in ('elf64','win64'):
    run([nasm,'-f',format_,*nasm_flags(nasm),'-I',str(ROOT/'include')+os.sep,'-I',str(out)+os.sep,stage/relative,'-o',out/(name+'-'+format_+'.o')],'assemble-'+name+'-'+format_)
  # Measure the added graph without assembling unrelated user-service code.
  c=compile_file(stage/'sched/parallel_live.dg',roots=[stage,ROOT/'services',ROOT/'lang/examples',ROOT/'lang/std'],mode='release');(out/'added.asm').write_text(c.assembly);run([nasm,'-f','win64',*nasm_flags(nasm),out/'added.asm','-o',out/'added.o'],'assemble-added');evidence['dong_sections']=sections(out/'added.o')
  entry=out/'parallel_size_base.dg';entry.write_text('module parallel_size_base;import smp.runtime;import irq.platform;import boot.service_memory;import arch.x86_64;')
  c=compile_file(entry,roots=[out,stage,ROOT/'services',ROOT/'lang/examples',ROOT/'lang/std'],mode='release');(out/'baseline.asm').write_text(c.assembly);run([nasm,'-f','win64',*nasm_flags(nasm),out/'baseline.asm','-o',out/'baseline.o'],'assemble-baseline');evidence['baseline_sections']=sections(out/'baseline.o');evidence['dong_delta']={n:evidence['dong_sections'][n]-evidence['baseline_sections'][n]for n in evidence['dong_sections']}
  self.assertEqual(before,hashes());self.assertEqual(candidate_before,b.source_inputs());(out/'validation-summary.json').write_text(json.dumps(dict(passed=True,current_source_only=True,historical_replay=False,actual_compiler_and_assembler=True,os_link_executed=False,vm_executed=False,source_unchanged=True,current_source_sha256=candidate_before,actual_kernel_sha256=before,evidence=evidence),indent=2)+'\n');print('PARALLEL_LIVE_NATIVE_EVIDENCE',out)
 def test_current_production_routing_is_observed_without_link_or_vm(self):
  b=load_builder();out=ROOT/'build/test/current-parallel-routing'/('run-'+uuid.uuid4().hex[:12])
  plan=b.production_plan(out,runtime_level=7,test=False)
  self.assertFalse(plan['built']);self.assertFalse(plan['os_link_executed']);self.assertFalse(plan['vm_executed'])
  names={Path(a['source']).name:a for a in plan['assemblies']}
  for name in ('bootstrap.asm','smp_runtime.asm','parallel.asm','parallel_probe.asm','parallel_live.asm'):
   self.assertIn(name,names);self.assertTrue(Path(names[name]['source']).is_relative_to(ROOT/'kernel'))
   self.assertIn(names[name]['output'],plan['commands'][-1])
  self.assertIn(str(ROOT/'kernel/smp_probe.dg'),plan['commands'][0])
  self.assertEqual(1,names['parallel_live.asm']['defines']['P6_USER_SMP'])
  self.assertFalse((out/'kernel.elf').exists())
  b.prepare(out)
  with self.assertRaises(ValueError):b.prepare(out)
 def test_report_oracle_rejects_false_idle_migration_and_partial_frames(self):
  d={n:0 for n in oracle.FIELDS};d.update(version=1,phase=6,cpus=4,count=6,tsc_hz=1000000000,quantum_ns=1000000,domain=0xffffd40000100000,probes=0xffffd40000200000,restart_token=513,restart_bottom=0xffffd40003000000,restart_top=0xffffd40003004000,restart_frame=0xffffd40003003f00,restart_xstate=0xffffd40000010000)
  for i,n in enumerate('started initial_done migrated_done idle_start idle_end wake_start wake_end completed'.split()):d[n]=1+i*100000000
  for name in oracle.ARRAYS16:d[name]=[0]*16
  for name in oracle.ARRAYS32:d[name]=[0]*32
  for c in range(1,4):
   for n in ('rates','timer_events','ipi_events','initial_ticks','initial_switches'):d[n][c]=10000000 if n=='rates' else 4
   d['idle_ticks'][c]=d['idle_end_ticks'][c]=20;d['wake_ticks'][c]=d['wake_end_ticks'][c]=21 if c==1 else 20
  for i in range(6):
   d['initial_masks'][i]=d['migrated_masks'][i]=1<<(i//2+1);d['iterations'][i]=16384;d['stack_bottom'][i]=0xffffd40001000000+i*0x10000;d['stack_top'][i]=d['stack_bottom'][i]+16384;d['final_frame'][i]=d['stack_top'][i]-256;d['xstate'][i]=0xffffd40000010000+i*1024;d['retired_token'][i]=257+i
  d['migrated_masks'][0]=10;self.assertTrue(oracle.validate(d)['cross_cpu_migration'])
  raw=struct.pack('<'+str(oracle.BYTES//8)+'Q',*[d[n]for n in oracle.FIELDS],*[v for names in (oracle.ARRAYS16,oracle.ARRAYS32)for n in names for v in d[n]]);self.assertEqual(d,oracle.decode(raw))
  serial=oracle.START+b''.join(f'parallel_{n}=0x{d[n]:016x}\r\n'.encode()for n in oracle.FIELDS)+oracle.READY;self.assertEqual({n:d[n]for n in oracle.FIELDS},oracle.parse(serial)[0])
  for label,change in [('no-timer',lambda x:x['timer_events'].__setitem__(2,0)),('idle-ticks',lambda x:x['idle_end_ticks'].__setitem__(1,21)),('single-ticks',lambda x:x['wake_end_ticks'].__setitem__(2,22)),('no-migration',lambda x:x['migrated_masks'].__setitem__(0,2)),('old-token',lambda x:x.update(restart_token=257)),('no-frame',lambda x:x['final_frame'].__setitem__(3,0)),('worker-error',lambda x:x['errors'].__setitem__(1,1))]:
   with self.subTest(label=label):bad=copy.deepcopy(d);change(bad);self.assertRaises(ValueError,oracle.validate,bad)
  for bad in (serial+oracle.READY,serial.replace(oracle.READY,b''),serial.replace(b'parallel_phase=0x0000000000000006',b'parallel_phase=0x0000000000000005')+b'DONGOS_P6_PARALLEL_ERROR=0x1\r\n'):
   with self.assertRaises(ValueError):oracle.parse(bad)
if __name__=='__main__':unittest.main(verbosity=2)
