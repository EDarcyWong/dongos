"""Independent raw boot trace decoder. This module never starts a VM."""
from __future__ import annotations
import argparse,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tests.run_clock_calibration_qemu import select as select_clock
MAGIC=0x3145434152544244
# Trusted normal runtime7 configuration contract, bound by integration manifest.
DEPENDENCIES=(2,4,64,18,64,0,32,2,2,2,2,2,2,64,10,10,10,10)
HEADER=('magic','version','bytes','record_bytes','capacity','count','state','failure','boot_id','loader_cpu','writer_cpu','online_mask',
 'clock_source','clock_hz','clock_lower','clock_upper','clock_samples','clock_flags','last_tsc','last_sequence','shell_sequence',
 'desktop_sequence','clients_sequence','configuration_count','ready_mask','started_mask','required_client_mask','client_mask','checksum','clock_sequence','reserved0','reserved1')
def need(test,message):
 if not test:raise ValueError(message)
def clock_evidence(h,proof):
 need(isinstance(proof,dict),'missing independent raw clock proof')
 if 'invariant_sample_flags' in proof:
  need(proof['invariant_sample_flags'] in (0,1),'invalid retained hardware invariant sample');invariant=bool(proof['invariant_sample_flags'])
 else:
  need(isinstance(proof.get('cpuid80000007_edx'),int),'missing actual CPUID invariant capability');invariant=bool(proof['cpuid80000007_edx']&256)
 need(bool(h['clock_flags']&1)==invariant,'invariant TSC metadata differs from actual CPUID')
 if h['clock_source']==1:
  ratio=proof.get('cpuid15',[]);need(len(ratio)==3,'missing actual CPUID15 registers');den,num,crystal=ratio
  need(all(isinstance(v,int) and 0<v<=0xffffffff for v in ratio),'invalid CPUID15 ratio')
  hz=crystal*num//den
  need(h['clock_flags']&2 and not h['clock_flags']&4 and h['clock_samples']==0,'wrong direct ratio provenance')
  need(h['clock_hz']==h['clock_lower']==h['clock_upper']==hz,'direct frequency differs from raw ratio')
 else:
  need(h['clock_source'] in (2,3,4),'unknown reference source')
  reference=proof.get('reference');samples=proof.get('samples');need(isinstance(reference,dict) and isinstance(samples,list) and len(samples)==7,'missing seven actual reference samples')
  if h['clock_source']==2:need(reference.get('period_fs',0)>0 and reference.get('hz')==0,'HPET provenance does not use its raw period')
  else:need(reference.get('hz')==3579545 and reference.get('period_fs')==0,'PM provenance is not exact 3579545Hz')
  result,_=select_clock(reference,samples)
  need(h['clock_flags']&4 and not h['clock_flags']&2,'wrong bracketed provenance')
  need((h['clock_hz'],h['clock_lower'],h['clock_upper'],h['clock_samples'])==
       (result['tsc_hz'],result['tsc_lower_hz'],result['tsc_upper_hz'],result['consistent']),'frequency differs from independent bracketed recomputation')
 need(1_000_000<=h['clock_lower']<=h['clock_hz']<=h['clock_upper']<=16_000_000_000,'frequency bounds invalid')
 return invariant
def decode(raw,proof,environment=None,expected_configurations=18,expected_clients=0x3c000,expected_dependencies=DEPENDENCIES):
 need(len(raw)==4096,'trace is not exactly one full page');words=struct.unpack('<512Q',raw);need(sum(words)&0xffffffffffffffff==0,'incomplete or corrupt trace checksum')
 h=dict(zip(HEADER,words[:32]));need((h['magic'],h['version'],h['bytes'],h['record_bytes'],h['capacity'])==(MAGIC,1,4096,48,80),'wrong trace format')
 need(h['reserved0']==h['reserved1']==0 and h['boot_id']!=0,'reserved/header identity invalid')
 need(h['failure']==0 and h['state']==6,'failed, incomplete or unsealed trace')
 need(0<h['count']<=80 and h['last_sequence']==h['count'],'invalid publication count')
 need(h['loader_cpu']==h['writer_cpu']<=0xffffffff,'unproven cross-CPU time domain')
 need(h['configuration_count']==expected_configurations and h['required_client_mask']==expected_clients,'wrong trusted profile/configuration set')
 need(0<expected_configurations<=32 and expected_clients>>expected_configurations==0,'invalid oracle profile')
 invariant=clock_evidence(h,proof);records=[];started={};ready=set();generations={};phase=0;last=0;stamps={};online=0;clock_seq=0
 for n in range(80):
  seq,tsc,kind,subject,stamp,detail=words[32+n*6:38+n*6]
  if n>=h['count']:need(not(seq|tsc|kind|subject|stamp|detail),'nonzero unpublished record');continue
  cpu=stamp>>32;generation=stamp&0xffffffff
  need(seq==n+1 and tsc>last and cpu==h['writer_cpu'],'sequence, clock or actual CPU mismatch');last=tsc
  if kind in (1,2,3,4,5,13):
   need(subject==0 and generation==0 if kind not in (5,13) else generation==0,'phase subject/generation invalid')
   if kind==1:need(phase==0 and n==0 and detail==0,'duplicate/late loader entry');phase=1
   elif kind==2:need(phase==1 and detail==0,'EBS before loader or repeated');phase=2
   elif kind==3:need(phase==2 and detail==0,'kernel before successful EBS');phase=3
   elif kind==13:need(phase==3 and clock_seq==0 and subject==h['clock_source'] and detail==h['clock_hz'],'invalid clock bind');clock_seq=seq
   elif kind==4:need(phase==3 and clock_seq and detail==0,'kernel prepared before clock binding');phase=4
   else:need(phase==4 and subject==0 and detail&1 and detail<=0xffff,'invalid SMP online mask');online=detail;phase=5
  else:
   need(phase==5,'service/mark before SMP or after seal')
   need(0<=subject<expected_configurations and 0<generation<=0x0fffffff,'invalid service identity')
   if kind==6:
    need(subject not in started and generation>generations.get(subject,0),'reused active/stale configuration generation')
    need(expected_dependencies is not None and len(expected_dependencies)==expected_configurations and detail==expected_dependencies[subject],'START differs from trusted configuration dependencies')
    need(detail>>expected_configurations==0 and not detail&(1<<subject),'invalid dependency bitmap')
    need(all(i in ready for i in range(expected_configurations) if detail&(1<<i)),'provider not actually READY before consumer START')
    started[subject]=generation;generations[subject]=generation
   elif kind in (7,8):
    need(started.get(subject)==generation and detail==0,'READY/STOP has no matching actual START')
    if kind==7:need(subject not in ready,'duplicate READY');ready.add(subject)
    else:ready.discard(subject);del started[subject]
   elif kind==9:
    need(subject==0 and subject in ready and started[subject]==generation and 9 not in stamps and detail==0,'shell marker before actual readiness/duplicate');stamps[9]=(seq,tsc)
   elif kind==10:
    need(subject==3 and started.get(subject)==generation and 10 not in stamps and detail==0,'desktop marker before actual START/duplicate');stamps[10]=(seq,tsc)
   elif kind==12:
    need(subject==3 and subject in ready and started[subject]==generation and 10 in stamps and 12 not in stamps,'clients marker precedes compositor present')
    need(expected_clients!=0 and detail==expected_clients and all(i in ready for i in range(expected_configurations) if detail&(1<<i)),'unready/missing client surfaces');stamps[12]=(seq,tsc)
   else:raise ValueError('unknown trace event')
   if 9 in stamps and (expected_clients==0 or 12 in stamps):phase=6
  records.append(dict(sequence=seq,tsc=tsc,kind=kind,subject=subject,generation=generation,cpu=cpu,detail=detail))
 need(phase==6 and clock_seq==h['clock_sequence'] and online==h['online_mask'],'unsealed/inconsistent phase summary')
 need(last==h['last_tsc'] and sum(1<<i for i in ready)==h['ready_mask'] and sum(1<<i for i in started)==h['started_mask'],'replayed kernel summary mismatch')
 for kind,key in ((9,'shell_sequence'),(10,'desktop_sequence'),(12,'clients_sequence')):need(stamps.get(kind,(0,0))[0]==h[key],'summary endpoint differs from actual record')
 need(h['client_mask']==(expected_clients if 12 in stamps else 0),'client presentation bitmap invalid')
 first=records[0]['tsc'];ebs=next(r['tsc'] for r in records if r['kind']==2);shell=stamps[9][1]
 ceil=lambda ticks:(ticks*1_000_000_000+h['clock_lower']-1)//h['clock_lower']
 intervals=dict(loader_to_interactive_shell_upper_ns=ceil(shell-first))
 if 10 in stamps:intervals['ebs_to_first_desktop_upper_ns']=ceil(stamps[10][1]-ebs)
 env=environment or {};eligible=env.get('host_os')=='linux' and env.get('actual_guest_boots',0)>=1 and env.get('query_kvm')=={'enabled':True,'present':True} and env.get('artifact_bound') is True and invariant
 return dict(header=h,records=records,intervals=intervals,invariant_tsc=invariant,kvm_gate_eligible=bool(eligible),
  loader_to_shell_within_500ms=intervals['loader_to_interactive_shell_upper_ns']<=500_000_000,
  kvm_gate_passed=bool(eligible and intervals['loader_to_interactive_shell_upper_ns']<=500_000_000),
  actual_guest_or_kvm_executed_by_this_tool=False)
def main():
 p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('--clock-proof',type=Path,required=True);p.add_argument('--environment',type=Path);args=p.parse_args()
 result=decode(args.trace.read_bytes(),json.loads(args.clock_proof.read_text()),json.loads(args.environment.read_text()) if args.environment else None);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
