"""Arena-backed user-SMP ownership protocol; raw CPU boundaries are mocked."""
# Tests the tracked current implementation, not a replay of unavailable candidate sources.
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'kernel'
BASE_REVISION=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
class Tests(unittest.TestCase):
 def test_capture_retirement_per_cpu_tags_and_if0_mailbox_progress(self):
  source=BASE/'sched/user_domain.dg';files=[source,BASE/'sched/multicore.dg',ROOT/'tests/user_domain_probe.dg',ROOT/'tests/user_domain_probe.c',Path(__file__),BASE/'sched/user_arch.asm',BASE.parent/'include/user_smp.inc',ROOT/'include/user_context.inc',ROOT/'include/smp.inc']
  before={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};out=ROOT/'build/test/p6-user-native'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);evidence={}
  # Current poll also services a legacy hardware mailbox; its mock is fault-injectable.
  controls={
   'ignore-legacy-poll-failure':('user_domain_legacy_poll()!=0','false'),
   'ack-before-capture':('if (*c).mode!=IDLE&&(*c).mode!=KERNEL&&(*c).mode!=LOCKED{return false;}','if false{return false;}'),
   'ack-without-flush':('if user_smp_arch_flush(cpu as u64)!=0','if false'),
   'skip-xstate-save':('user_smp_arch_save((*c).capture_xstate);',''),
   'foreign-cpu-authority':('user_smp_arch_cpu()!=cpu as u64||',''),
   'skip-lock-wait-poll':('let progress=try poll(d,cpu);if user_smp_arch_clock()>=deadline','if user_smp_arch_clock()>=deadline'),
   'retire-before-all-acks':('&&atomic_load(&(*((*d).cpus+id)).acknowledged)!=sequence','&&false'),
   'inherit-first-use-no-flush':('let seen=(*c).seen+(*c).slot as usize;var retain:u64=0;','let seen=(*c).seen+(*c).slot as usize;var retain:u64=1;'),
   'return-with-pending-revoke':('if atomic_load(&(*c).requested)>atomic_load(&(*c).acknowledged){return false;}','if false{return false;}'),
   'revive-slot-incarnation':('||incarnation<=(*p).incarnation',''),
   'skip-return-validation':('if user_smp_arch_validate((*c).returned,(*c).return_root)!=1','if false'),
   'IPI-loop-for-busy-peers':('atomic_load(&(*((*d).cpus+id)).mode)==IDLE','true'),
   'write-delayed-capture-to-new-slot':('(*c).captured=0;if (*c).slot>=16{return false;}let p=(*d).processes+(*c).slot as usize;\n if (*p).token!=(*c).captured_token||(*p).incarnation!=(*c).captured_incarnation||(*p).retiring!=0{return false;}\n if (*p).token!=(*c).token{fail(d);return error.Held;}', '(*c).captured=0;let p=(*d).processes+(((*c).captured_token&255)-1) as usize;'),
  }
  def run(args,d,label):
   args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=30);(d/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
  for format_ in ('win64','elf64'):
   r=run([nasm,'-f',format_,*nasm_flags(nasm),'-I',str(BASE.parent/'include')+os.sep,'-I',str(ROOT/'include')+os.sep,files[5],'-o',out/('user-arch-'+format_+'.o')],out,'assemble-arch-'+format_);self.assertEqual(0,r.returncode,r.stderr)
  for mode in ('debug','release'):
   for variant in ('normal',*controls):
    d=out/(mode+'-'+variant);stage=d/'kernel';(stage/'sched').mkdir(parents=True);text=source.read_text()
    if variant!='normal':old,new=controls[variant];self.assertEqual(1,text.count(old));text=text.replace(old,new)
    (stage/'sched/user_domain.dg').write_text(text);(stage/'sched/multicore.dg').write_bytes(files[1].read_bytes());c=compile_file(files[2],roots=[ROOT/'tests',stage],mode=mode)
    self.assertNotRegex(c.assembly.lower(),r'\b(?:xmm\d+|ymm\d+|zmm\d+|cli|sti|invpcid|wrmsr|rdmsr)\b')
    layouts={v['full_name']:v for v in c.layout_manifest['types']};self.assertEqual(12960,layouts['sched.multicore.Engine']['size']);(d/'layout.json').write_text(json.dumps(c.layout_manifest,indent=2)+'\n')
    asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o';r=run([nasm,'-f','win64'if os.name=='nt'else'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
    exe=d/('probe.exe'if os.name=='nt'else'probe');r=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([]if os.name=='nt'else['-no-pie']),files[3],obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
    scenarios=('normal','flush-fail','timeout','kick-fail','switch-fail','invalid-return','legacy-fail')if variant=='normal'else({'skip-return-validation':'invalid-return','ignore-legacy-poll-failure':'legacy-fail'}.get(variant,'normal'),)
    for scenario in scenarios:
     r=run([exe,scenario],d,scenario);self.assertEqual(0 if variant=='normal'else 1,r.returncode,r.stdout+r.stderr)
     if variant!='normal':self.assertIn('user SMP oracle line',r.stderr)
     evidence[mode+'-'+variant+'-'+scenario]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
  after={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};self.assertEqual(before,after);(out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_binding='tracked-current-source',historical_candidate_replay=False,base_revision=BASE_REVISION,legacy_mailbox_boundary_fault_injected=True,real_queue_and_user_ownership_protocol=True,hardware_callbacks_mocked=True,actual_ap_or_ring3_executed=False,source_sha256=after,sources_unchanged=True,evidence=evidence),indent=2)+'\n');print('USER_DOMAIN_EVIDENCE',out)
 def test_trusted_poll_hook_progress_without_request_and_capture_boundaries(self):
  # Keep the existing native probes and their default-null hook oracles intact.
  # This additional staged wrapper registers a real Dong callback, and the C
  # fixture drives the actual production Domain transitions around that hook.
  inputs=[BASE/'sched/user_domain.dg',BASE/'sched/multicore.dg',ROOT/'tests/user_domain_probe.dg',ROOT/'tests/user_domain_probe.c',Path(__file__),*list((ROOT/'lang/dongc').rglob('*.py'))]
  frozen=lambda:{str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in inputs}
  before=frozen();out=ROOT/'build/test/user-domain-hook'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
  nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc,'native tools required, no skip')
  bridge='''
var HOOK_CALLS:u64=0;var HOOK_ERROR:u64=0;
unsafe fn observe(domain:*p.Domain,cpu:usize)u64{unsafe{HOOK_CALLS+=1;return HOOK_ERROR;}}
export("ud_hook_install") fn install()u64{unsafe{match p.register_poll(D,observe){ok=>{return 0;},err(e)=>{return e;},}}}
export("ud_hook_raw") fn raw(h:p.PollHook)u64{unsafe{match p.register_poll(D,h){ok=>{return 0;},err(e)=>{return e;},}}}
export("ud_hook_count") fn count()u64{return HOOK_CALLS;}
export("ud_hook_error") fn set_error(value:u64)void{unsafe{HOOK_ERROR=value;}return;}
'''
  cmain='''
extern U ABI ud_hook_install(void),ud_hook_count(void);
extern void ABI ud_hook_error(U);
typedef U(ABI *RawHook)(void*,U);extern U ABI ud_hook_raw(RawHook);
int main(void){setup();cpu=1;C(ud_hook_install()!=0);lock(0);C(ud_hook_raw(0)!=0);C(!ud_hook_install());C(ud_hook_install()!=0);
 U n=ud_hook_count(),f=flushes[0];C(!ud_poll(0)&&ud_hook_count()==n+1&&flushes[0]==f&&!ud_get(13,0));
 cpu=1;n=ud_hook_count();C(!ud_poll(1)&&ud_hook_count()==n+1&&!flushes[1]);roots[1]=0x200000;n=ud_hook_count();C(!ud_poll(1)&&ud_hook_count()==n);roots[1]=0x100000;
 cpu=0;admit(0,1,0x200000,0x11);U selected=0;C(ud_select(0,&selected)==1);n=ud_hook_count();C(!ud_poll(0)&&ud_hook_count()==n);C(!ud_unlock(0));C(ud_commit(0)==1);C(!ud_poll(0)&&ud_hook_count()==n);
 C(!ud_begin(0));memcpy((void*)(uintptr_t)ud_get(8,0),&frames[0],sizeof(Frame));roots[0]=0x100000;C(!ud_poll(0)&&ud_hook_count()==n);C(!ud_complete(0));C(!ud_poll(0)&&ud_hook_count()==n+1);
 lock(0);C(ud_drain(0)==1);ud_hook_error(1);f=flushes[0];C(ud_poll(0)==0x06090003&&ud_get(0,0)&&flushes[0]==f&&!ud_get(13,0));
 puts("trusted poll hook native: no-request progress, exact CPU/IF0/root, ENTERING/RETURNING/USER guards, failure held");return 0;}
'''
  tools={str(Path(p).resolve()):hashlib.sha256(Path(p).read_bytes()).hexdigest()for p in (nasm,cc)}
  original=(BASE/'sched/user_domain.dg').read_text();controls={
   'omit-hook':('if POLL_HOOK(d,cpu)!=0','if false'),
   'ignore-hook-failure':('if POLL_HOOK(d,cpu)!=0{fail(d);return error.Hardware;}','let ignored=POLL_HOOK(d,cpu);'),
   'run-before-capture':('&&((*c).mode==IDLE||(*c).mode==KERNEL||(*c).mode==LOCKED)','&&true'),
  };commands=[];cases=[]
  try:
   for mode in ('debug','release'):
    for variant in ('normal',*controls):
     d=out/(mode+'-'+variant);stage=d/'src';(stage/'sched').mkdir(parents=True);text=original
     if variant!='normal':old,new=controls[variant];self.assertEqual(1,text.count(old));text=text.replace(old,new)
     (stage/'sched/user_domain.dg').write_text(text);(stage/'sched/multicore.dg').write_bytes((BASE/'sched/multicore.dg').read_bytes())
     (stage/'user_domain_probe.dg').write_text((ROOT/'tests/user_domain_probe.dg').read_text()+bridge)
     c=d/'oracle.c';c.write_text((ROOT/'tests/user_domain_probe.c').read_text().replace('int main(','int legacy_main(')+cmain)
     compiled=compile_file(stage/'user_domain_probe.dg',roots=[stage],mode=mode);asm=d/'probe.asm';asm.write_text(compiled.assembly)
     (d/'layout.json').write_text(json.dumps(compiled.layout_manifest,indent=2)+'\n');objects={}
     argv=[]
     for fmt in ('elf64','win64'):
      obj=d/(fmt+'.o');objects[fmt]=obj;argv.append([nasm,'-f',fmt,*nasm_flags(nasm),asm,'-o',obj])
     exe=d/('probe.exe'if os.name=='nt'else'probe');argv.append([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([]if os.name=='nt'else['-no-pie']),c,objects['win64'if os.name=='nt'else'elf64'],'-o',exe]);argv.append([exe])
     for i,command in enumerate(argv):
      command=list(map(str,command));r=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=90)
      commands.append(dict(mode=mode,variant=variant,argv=command,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr));(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
      self.assertEqual(1 if i==3 and variant!='normal'else 0,r.returncode,r.stdout+r.stderr)
     if variant=='normal':self.assertIn('no-request progress',r.stdout)
     else:self.assertIn('user SMP oracle line',r.stderr)
     cases.append(dict(mode=mode,variant=variant,elf_sha256=hashlib.sha256(objects['elf64'].read_bytes()).hexdigest(),coff_sha256=hashlib.sha256(objects['win64'].read_bytes()).hexdigest()))
  finally:
   after=frozen();tools_stable=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in tools.items());(out/'result.json').write_text(json.dumps(dict(passed=len(cases)==8 and before==after and tools_stable,cases=cases,source_before=before,source_after=after,tools_sha256=tools,tools_stable=tools_stable,hardware_callbacks_mocked=True,guest_executed=False),indent=2)+'\n')
  self.assertEqual(8,len(cases));self.assertEqual(before,after);self.assertTrue(tools_stable)
if __name__=='__main__':unittest.main(verbosity=2)
