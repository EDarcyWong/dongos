"""Coordinator-only real Dong FIFO/Domain + TLS native threads; no VM."""
from pathlib import Path
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import tool

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'tests'
SCENARIOS=('bind','fair','bootstrap','cycles','returning','queued-expired-free','foreign','wrong-cpu',
           'if0','root','duplicate','duplicate-waiter','queued-timeout','head-timeout','unlock-failed',
           'already-failed','overflow','overflow-max','last-ticket')
CONTROLS={
 'bypass-fifo':('if serving==ticket{if queued{try waiting(d,cpu,limit);}break;}',
                'if true{if queued{try waiting(d,cpu,limit);}break;}','fair'),
 'skip-wait-poll':('let progress=try ud.poll(d,cpu);','let progress=false;','fair'),
 'advance-before-unlock':('try ud.unlock(d,cpu);','atomic_store(&STATE.serving,wait);try ud.unlock(d,cpu);','fair'),
 'clear-owner-before-unlock':('try ud.unlock(d,cpu);','atomic_store(&STATE.owner,NONE);try ud.unlock(d,cpu);','fair'),
 'renew-deadline':('if ud.user_smp_arch_clock()>=limit{return error.Timeout;}',
                   'if ud.user_smp_arch_clock()>=limit+1000000{return error.Timeout;}','queued-expired-free'),
 'swallow-original-acquire':('try ud.acquire(d,cpu,limit);','let ignored=ud.acquire(d,cpu,limit);','root'),
 'overflow-wrap':('if next>=MAX-1{return error.Overflow;}','if next>=MAX{return error.Overflow;}','overflow'),
 'clear-ticket-after-acquire-failure':('try ud.acquire(d,cpu,limit);',
   'let result=ud.acquire(d,cpu,limit);match result{ok=>{},err(e)=>{atomic_store(&STATE.wait[cpu],0);return result;},}','root'),
 'swallow-original-unlock':('try ud.unlock(d,cpu);','let ignored=ud.unlock(d,cpu);','unlock-failed'),
 'reject-returning':('if (*c).mode!=ud.LOCKED&&(*c).mode!=ud.RETURNING',
                     'if (*c).mode!=ud.LOCKED','returning'),
 'omit-atomic-cpu-claim':('if atomic_compare_exchange(&STATE.wait[cpu],0,MAX)!=0{return error.Held;}',
                         'atomic_store(&STATE.wait[cpu],MAX);','duplicate-waiter'),
}

def digest(path):
 return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

def source_hashes():
 paths={Path(__file__),HERE/'user_bkl_probe.dg',HERE/'user_bkl_probe.c',ROOT/'docs/p2-fair-bkl.md',ROOT/'lang/tests/test_dongc.py'}
 paths.update((ROOT/'kernel').rglob('*.dg'))
 paths.update((ROOT/'lang/dongc').glob('*.py'))
 paths.update((ROOT/'include').glob('*.inc'))
 return {p.relative_to(ROOT).as_posix():digest(p) for p in sorted(paths)}

def graph():
 paths={'user_bkl_probe':HERE/'user_bkl_probe.dg'};pending=list(paths.values())
 while pending:
  path=pending.pop()
  for name in re.findall(r'\bimport\s+([\w.]+)\s+as\s+',path.read_text(encoding='utf-8')):
   if name in paths:continue
   found=[base/(name.replace('.','/')+'.dg') for base in (HERE,ROOT/'kernel') if (base/(name.replace('.','/')+'.dg')).is_file()]
   if len(found)!=1:raise AssertionError((name,found))
   paths[name]=found[0];pending.append(found[0])
 return paths

def decode_raw(path):
 raw=path.read_bytes()
 if len(raw)!=192+120+16*120:raise AssertionError(('raw snapshot length',len(raw)))
 state=struct.unpack_from('<21Q',raw)
 domain=struct.unpack_from('<15Q',raw,192)
 cpus=[struct.unpack_from('<15Q',raw,312+i*120) for i in range(16)]
 return dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),ready=state[0],domain_pointer=state[1],
             next=state[2],serving=state[3],owner=state[4],wait=list(state[5:]),
             domain_raw=list(domain),cpu_raw=[list(cpu) for cpu in cpus])

class FairBklTests(unittest.TestCase):
 def test_actual_fifo_threads_poll_ack_and_fail_held_controls(self):
  output=ROOT/'build/test/user-bkl'/('run-'+uuid.uuid4().hex[:12]);output.mkdir(parents=True)
  before=source_hashes();tools={'python':str(Path(sys.executable).resolve()),'nasm':None,'cc':None}
  tools_before={};evidence=[];commands=[];compilations=[];passed=False;failure=None;active={}
  def tool_hashes():return {role:dict(path=path,sha256=digest(Path(path)) if path else None) for role,path in tools.items()}
  def run(argv,directory,label):
   argv=list(map(str,argv));record=dict(argv=argv,cwd=str(directory),label=label,directory=directory.relative_to(output).as_posix())
   raw=json.dumps(dict(argv=argv,cwd=str(directory)),sort_keys=True,indent=2).encode()+b'\n'
   (directory/(label+'.command.json')).write_bytes(raw);record['command_sha256']=hashlib.sha256(raw).hexdigest();stdout=stderr=b''
   try:
    result=subprocess.run(argv,cwd=directory,capture_output=True,timeout=60)
    stdout,stderr=result.stdout,result.stderr;record['returncode']=result.returncode
   except (OSError,subprocess.TimeoutExpired) as exc:
    stdout=getattr(exc,'stdout',None) or b'';stderr=getattr(exc,'stderr',None) or b''
    if isinstance(stdout,str):stdout=stdout.encode()
    if isinstance(stderr,str):stderr=stderr.encode()
    record['failure']=dict(type=type(exc).__name__,message=str(exc));raise
   finally:
    (directory/(label+'.stdout')).write_bytes(stdout);(directory/(label+'.stderr')).write_bytes(stderr)
    record.update(stdout_sha256=hashlib.sha256(stdout).hexdigest(),stderr_sha256=hashlib.sha256(stderr).hexdigest(),stdout=stdout.decode(errors='replace'),stderr=stderr.decode(errors='replace'))
    (directory/(label+'.json')).write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');commands.append(record)
   result.stdout=stdout.decode(errors='replace');result.stderr=stderr.decode(errors='replace');return result
  try:
   for role,name,override in (('nasm','nasm','NASM'),('cc','gcc','CC')):
    found=tool(name,override);self.assertTrue(found,'required native tool unavailable: '+role);tools[role]=str(Path(found).resolve())
   tools_before=tool_hashes();nasm,cc=tools['nasm'],tools['cc']
   help_result=run([nasm,'-h'],output,'nasm-help');self.assertEqual(0,help_result.returncode,help_result.stderr);help_text=help_result.stdout
   if re.search(r'(?m)^\s*-h\s+-\S+',help_text):
    help_result=run([nasm,'-h','-w'],output,'nasm-warning-help');self.assertEqual(0,help_result.returncode,help_result.stderr);help_text+='\n'+help_result.stdout
   flags=['-Wall','-Werror']+['-w-'+name for name in ('reloc-rel-dword','reloc-abs-qword') if re.search(r'(?m)^\s*'+re.escape(name)+r'\s',help_text)]
   sources=graph();c_source=(HERE/'user_bkl_probe.c').read_text(encoding='utf-8')
   for mode in ('debug','release'):
    for variant in ('normal',*CONTROLS):
     directory=output/(mode+'-'+variant);stage=directory/'source';active=dict(mode=mode,variant=variant,phase='stage')
     for name,path in sources.items():
      text=path.read_text(encoding='utf-8')
      if name=='sched.user_bkl' and variant!='normal':
       old,new,_=CONTROLS[variant];self.assertEqual(1,text.count(old),variant);text=text.replace(old,new)
      target=stage/(name.replace('.','/')+'.dg');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
     staged={p.relative_to(stage).as_posix():digest(p) for p in sorted(stage.rglob('*.dg'))}
     invocation=dict(mode=mode,variant=variant,entry=str(stage/'user_bkl_probe.dg'),roots=[str(stage)],staged_source_sha256=staged,executed=False)
     compilations.append(invocation);active['phase']='compile'
     try:
      invocation['executed']=True;compiled=compile_file(stage/'user_bkl_probe.dg',roots=[stage],mode=mode);invocation['passed']=True
     except BaseException as exc:invocation.update(passed=False,failure=dict(type=type(exc).__name__,message=str(exc)));raise
     finally:(directory/'compile.json').write_text(json.dumps(invocation,indent=2)+'\n',encoding='utf-8')
     self.assertNotRegex(compiled.assembly.lower(),r'\b(?:cli|sti|hlt|invpcid|wbinvd|wrmsr|rdmsr|cr[034])\b')
     layouts={item['full_name']:item for item in compiled.layout_manifest['types']}
     self.assertEqual(120,layouts['sched.user_domain.Domain']['size']);self.assertEqual(120,layouts['sched.user_domain.Cpu']['size'])
     layout=layouts['sched.user_bkl.State'];self.assertEqual(192,layout['size']);self.assertEqual([0,8,16,24,32,40],[item['offset'] for item in layout['fields']])
     (directory/'layout.json').write_text(json.dumps(compiled.layout_manifest,indent=2)+'\n',encoding='utf-8')
     assembly=directory/'probe.asm';assembly.write_text(compiled.assembly,encoding='utf-8');(directory/'probe.c').write_text(c_source,encoding='utf-8')
     obj=directory/'dong.o';active['phase']='assemble';result=run([nasm,'-f','win64'if os.name=='nt'else'elf64',*flags,assembly,'-o',obj],directory,'assemble');self.assertEqual(0,result.returncode,result.stdout+result.stderr)
     exe=directory/('probe.exe'if os.name=='nt'else'probe');active['phase']='link'
     result=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([]if os.name=='nt'else['-pthread','-no-pie']),directory/'probe.c',obj,'-o',exe],directory,'link');self.assertEqual(0,result.returncode,result.stdout+result.stderr)
     for scenario in SCENARIOS if variant=='normal' else (CONTROLS[variant][2],):
      active.update(phase='native',scenario=scenario);raw_path=directory/(scenario+'.raw')
      result=run([exe,scenario,raw_path],directory,'native-'+scenario)
      case=dict(mode=mode,variant=variant,scenario=scenario,returncode=result.returncode,object_sha256=digest(obj),executable_sha256=digest(exe))
      evidence.append(case)
      self.assertNotIn('USER_BKL_DONG_PANIC',result.stdout+result.stderr,'unexpected Dong panic is never an oracle rejection')
      self.assertIn(result.returncode,(0,1),'panic, signal or process crash cannot satisfy a native control')
      self.assertEqual(0 if variant=='normal'else 1,result.returncode,result.stdout+result.stderr)
      if variant!='normal':self.assertIn('BKL native oracle line',result.stderr);self.assertNotIn('USER_BKL_NATIVE_PASS',result.stdout)
      else:
       self.assertIn('USER_BKL_NATIVE_PASS scenario='+scenario,result.stdout)
       self.assertIn('synthetic_hardware=true actual_ap_cpl3_executed=false actual_qemu_executed=false',result.stdout)
       decoded=decode_raw(raw_path);case['raw_snapshot']=decoded
       self.assertEqual(1,decoded['ready']);self.assertNotEqual(0,decoded['domain_pointer'])
       if scenario=='fair':
        self.assertEqual((4,4,16),(decoded['next'],decoded['serving'],decoded['owner']));self.assertEqual([0]*16,decoded['wait'])
        self.assertEqual(0,decoded['domain_raw'][2]);self.assertEqual(16,decoded['domain_raw'][3]);self.assertEqual(1,decoded['domain_raw'][8])
        self.assertEqual([1,1,1],[cpu[8] for cpu in decoded['cpu_raw'][:3]])
       (directory/(scenario+'.decoded.json')).write_text(json.dumps(decoded,indent=2)+'\n',encoding='utf-8')
   self.assertEqual(2*(len(SCENARIOS)+len(CONTROLS)),len(evidence));self.assertEqual(before,source_hashes());self.assertEqual(tools_before,tool_hashes());passed=True
  except BaseException as exc:failure=dict(type=type(exc).__name__,message=str(exc),active=active);raise
  finally:
   after=source_hashes();tools_after=tool_hashes()
   artifacts={p.relative_to(output).as_posix():digest(p) for p in sorted(output.rglob('*')) if p.is_file() and p!=output/'validation-summary.json'}
   (output/'validation-summary.json').write_text(json.dumps(dict(passed=passed and before==after and tools_before==tools_after,failure=failure,
    source_before=before,source_after=after,sources_unchanged=before==after,tools_before=tools_before,tools_after=tools_after,tools_unchanged=tools_before==tools_after,
    artifact_sha256=artifacts,commands=commands,compilations=compilations,evidence=evidence,skipped=[],normal_scenarios_per_mode=len(SCENARIOS),mutants_per_mode=len(CONTROLS),
    actual_dong_fifo_domain_queue=bool(evidence),
    actual_native_threads=any(e['variant']=='normal' and e['scenario'] in ('fair','bootstrap','queued-expired-free','duplicate-waiter') and e['returncode']==0 for e in evidence),
    synthetic_TLS_root_IF0_atomic_lock_clock_and_TLB=True,
    bridge_integrated=False,actual_ap_cpl3_executed=False,actual_qemu_executed=False,os_build_executed=False),indent=2)+'\n',encoding='utf-8')
   print('USER_BKL_EVIDENCE',output)
  self.assertTrue(passed and before==after and tools_before==tools_after,'late source/tool mutation must fail unittest and receipt')

if __name__=='__main__':unittest.main(verbosity=2)
