"""Execute the live candidate's exact idle/drain/time/error fragments."""
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'build/test/p6-live-integration-candidate/kernel'
def block(text,marker):
 a=text.index(marker);b=text.index('{',a);depth=1;i=b+1
 while depth:
  depth+=int(text[i]=='{')-int(text[i]=='}');i+=1
 return text[a:i]
class Tests(unittest.TestCase):
 def test_real_idle_fragment_late_ipi_periodic_timeout_error_and_rollback(self):
  source=BASE/'sched/parallel_live.dg';files=[source,BASE/'sched/parallel.dg',BASE/'sched/multicore.dg',BASE/'sched/parallel_boot.dg',ROOT/'tests/parallel_idle_probe.c',Path(__file__)];before={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};out=ROOT/'build/test/p6-idle-drain-native'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);evidence={}
  text=source.read_text();fragment='\n'.join([*re.findall(r'pub error \w+=0x[0-9a-f_]+;',text),block(text,'pub struct Report{'),*(block(text,'unsafe fn '+n+'(')for n in('timed','healthy','delay','settle_idle'))]);probe=block(files[3].read_text(),'pub struct Probe{')
  entry='module parallel_idle_probe;import sched.parallel as p;import sched.parallel_boot as boot;import arch.x86_64 as arch;var INFO:*Report=null;unsafe extern "sysv64" fn parallel_live_pause()void;\n'+fragment+'''
export("gip_required") fn required()u64{return p.required_bytes();}
export("gip_init") fn initialize(arena:u64,bytes:u64,report:u64,template:u64)u64{unsafe{INFO=report as *Report;(*INFO).tsc_hz=1000000;match p.initialize(arena,bytes,14,0x100000,0x80000000,0x80010000,0x80000010,template){ok=>{return 0;},err(e)=>{return e;},}}}
export("gip_run") fn run()u64{unsafe{match settle_idle(p.pointer(),4,1000000){ok=>{return 0;},err(e)=>{return e;},}}}
export("gip_ticks") fn ticks(id:usize)u64{unsafe{return &(*((*p.pointer()).cpus+id)).ticks as u64;}}
export("gip_error") fn errors()u64{unsafe{return &(*boot.probe_records()).errors as u64;}}
export("gip_fail") fn fail()void{unsafe{p.failstop();}return;}
export("gip_get") fn get(which:u64,id:usize)u64{unsafe{if which==0{return (*INFO).idle_start;}if which==1{return (*INFO).idle_end;}if which==2{return (*INFO).idle_ticks[id];}return (*INFO).idle_end_ticks[id];}}
'''
  controls={
   'skip-global-drain-deadline':('try timed(draining);','', 'periodic'),
   'accept-transient-as-quiet':('if value!=(*INFO).idle_ticks[cpu]{complete=false;}','if false{complete=false;}','transient'),
   'skip-worker-error':('try healthy();try timed(started);','try timed(started);','worker'),
   'clock-rollback-short-circuit':('if now<started{return error.Deadline;}','', 'rollback'),
   'ignore-failed-domain':('if boot.FAILED||p.pointer()==null||atomic_load(&(*p.pointer()).failed)!=0','if false','failed-domain'),
  }
  def command(args,d,label):
   args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=30);(d/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
  for mode in('debug','release'):
   for variant in('normal',*controls):
    d=out/(mode+'-'+variant);stage=d/'source';(stage/'sched').mkdir(parents=True);body=entry
    if variant!='normal':old,new,_=controls[variant];self.assertEqual(1,body.count(old));body=body.replace(old,new)
    (stage/'parallel_idle_probe.dg').write_text(body);(stage/'sched/parallel.dg').write_bytes(files[1].read_bytes());(stage/'sched/multicore.dg').write_bytes(files[2].read_bytes());(stage/'sched/parallel_boot.dg').write_text('module sched.parallel_boot;pub var FAILED:bool=false;'+probe+'const ZERO:Probe=Probe{ready:0,iterations:0,errors:0,cpu_mask:0,last_cpu:0,reserved:0,stop:0,done:0,scratch:[0;8]};var PROBES:[2]Probe=[ZERO;2];pub fn probe_records()*Probe{unsafe{return &PROBES[0];}}pub fn probe_count()usize{return 2;}')
    c=compile_file(stage/'parallel_idle_probe.dg',roots=[stage,ROOT/'lang/std'],mode=mode);asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o';r=command([nasm,'-f','win64'if os.name=='nt'else'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
    exe=d/('probe.exe'if os.name=='nt'else'probe');r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([]if os.name=='nt'else['-no-pie']),files[4],obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
    for scenario in(('quiet','transient','periodic','worker','rollback','failed-domain')if variant=='normal'else(controls[variant][2],)):
     r=command([exe,scenario],d,scenario);self.assertEqual(0 if variant=='normal'else 1,r.returncode,r.stdout+r.stderr)
     if variant!='normal':self.assertIn('parallel idle oracle line',r.stderr)
     evidence[mode+'-'+variant+'-'+scenario]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
  after={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};self.assertEqual(before,after);(out/'validation-summary.json').write_text(json.dumps(dict(passed=True,candidate_only=True,exact_live_idle_and_deadline_fragments=True,real_parallel_domain=True,clock_and_async_ticks_and_worker_read_boundary_mocked=True,actual_ap_or_vm_executed=False,source_sha256=after,sources_unchanged=True,evidence=evidence),indent=2)+'\n');print('PARALLEL_IDLE_DRAIN_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
