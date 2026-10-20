"""Exact active shared barrier, real queue/domain, CPU/TLB boundary mocked."""
import hashlib,json,os,shutil,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT
MUTATION_POLICY="\nU ABI user_bridge_service_policy(U slot,U event,U frame){(void)slot;(void)event;(void)frame;return 0;}\n"
class Tests(unittest.TestCase):
 def test_bkl_owned_all_cpu_barrier_and_actual_bad_wait(self):
  out=ROOT/'build/test/p6-cpl3-shared-barrier-native'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
  files=[*sorted((BASE/'kernel/sched').glob('*.*')),ROOT/'tests/user_current_entry_probe.dg',ROOT/'tests/user_current_entry_probe.c',Path(__file__)];before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};evidence={}
  c=(ROOT/'tests/user_current_entry_probe.c').read_text()+MUTATION_POLICY;needle=' /* Foreign CPU cannot use another header/capture ticket to mutate state. */'
  c=c.replace('static void bridge_controls(void){','extern U ABI dong_user_smp_barrier(void);\nstatic void bridge_controls(void){')
  c=c.replace(needle,' cpu=0;C(!ue_lock(0));U sequence=d->completed;U previous[3]={flushes[0],flushes[1],flushes[2]};C(!dong_user_smp_barrier()&&d->completed==sequence+1&&!d->barrier&&d->lock==1&&d->owner==0);for(unsigned i=0;i<3;i++)C(flushes[i]==previous[i]+1&&d->cpus[i].ack==d->completed);C(!ue_unlock(0));\n'+needle)
  c=c.replace('int main(void){setup();','int main(void){C(dong_user_smp_barrier()==1);setup();')
  nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
  def run(args,d,label):
   args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60);(d/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2));return r
  for mode in('debug','release'):
   for bad in(False,True):
    d=out/(mode+('-omit-wait'if bad else'-good'));shutil.copytree(BASE/'kernel',d/'kernel');shutil.copytree(BASE/'include',d/'include');(d/'probe.c').write_text(c)
    if bad:
     p=d/'kernel/sched/user_bridge.dg';s=p.read_text();old='let sequence=try ud.barrier_begin(d,0);try ud.barrier_wait(d,0,sequence,try deadline(d,0));';self.assertEqual(1,s.count(old));p.write_text(s.replace(old,'let sequence=try ud.barrier_begin(d,0);'))
    compiled=compile_file(ROOT/'tests/user_current_entry_probe.dg',roots=[ROOT/'tests',d/'kernel'],mode=mode);(d/'probe.asm').write_text(compiled.assembly);objects=[]
    for name,source in [('dong',d/'probe.asm'),('entry',d/'kernel/sched/user_entry.asm'),('legacy',d/'kernel/sched/user_legacy.asm')]:
     obj=d/(name+'.o');r=run([nasm,'-f','win64'if os.name=='nt'else'elf64',*nasm_flags(nasm),'-I',str(d/'include')+os.sep,'-I',str(ROOT/'include')+os.sep,source,'-o',obj],d,name);self.assertEqual(0,r.returncode,r.stderr);objects.append(obj)
    exe=d/('probe.exe'if os.name=='nt'else'probe');r=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([]if os.name=='nt'else['-no-pie']),d/'probe.c',*objects,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr);r=run([exe],d,'native');self.assertEqual(1 if bad else 0,r.returncode,r.stdout+r.stderr);evidence[d.name]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};self.assertEqual(before,after);(out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),contract="tracked-current-cpl3-v1",current_source=True,historical_replay=False,actual_production_barrier=True,real_domain_queue=True,hardware_tlb_boundary_mocked=True,actual_ap_cpl3_executed=False,vm_executed=False,source_sha256=after,evidence=evidence),indent=2)+'\n');print('USER_SMP_BARRIER_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
