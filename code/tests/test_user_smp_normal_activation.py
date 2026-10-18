"""Post-gate normal selector and pure topology policy, no OS link/VM."""
import hashlib,json,os,py_compile,subprocess,unittest,uuid
from pathlib import Path
from lang.tests.test_dongc import tool,nasm_flags
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'build/test/p6-cpl3-integration-candidate';NORMAL=BASE/'normal'
C=r'''
#include <stdint.h>
#include <stdio.h>
typedef uint64_t U;
#define ABI __attribute__((sysv_abi))
extern U ABI user_smp_normal_policy(U,U);
#define STUB(n) U ABI n(void){return 0;}
STUB(dong_user_smp_boot_prepare) STUB(dong_user_smp_boot_publish) STUB(dong_user_smp_boot_report)
STUB(dong_user_entry_mapped) STUB(dong_user_entry_guard) STUB(dong_parallel_live_report)
STUB(parallel_live_rate) STUB(dong_user_smp_project) STUB(user_smp_activate)
STUB(user_smp_idle) STUB(user_smp_fail) STUB(smp_send_ipi)
int main(void){for(U n=0;n<18;n++){U expected=n==0||n>16?UINT64_MAX:n<3?0:1;
 if(user_smp_normal_policy(n,31)!=expected||user_smp_normal_policy(n,30)!=UINT64_MAX){fprintf(stderr,"normal CPU policy rejected count=%u\n",(unsigned)n);return 1;}}
 puts("normal activation topology policy:1/2 CPU explicit BSP,3..16 full user SMP,unfinished/invalid rejected");return 0;}
'''
class Tests(unittest.TestCase):
 def test_default_desktop_selector_legacy_levels_and_topology_controls(self):
  files=[p for p in NORMAL.rglob('*')if p.is_file()and'bases'not in p.parts]+list((BASE/'include').glob('*.inc'));before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files}
  out=ROOT/'build/test/p6-cpl3-normal-native'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);incs=ROOT/'build/test/p6-cpl3-integration-native/run-7a18b68d67cc';nasm,cc=tool('nasm','NASM'),tool('gcc','CC');evidence={}
  def run(args,label):
   args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60);(out/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2));return r
  prefix=[nasm,*nasm_flags(nasm),'-I',str(BASE/'include')+os.sep,'-I',str(incs)+os.sep,'-I',str(ROOT/'include')+os.sep]
  for runtime in(4,5,6,7):
   for test in(0,1):
    for fmt in('elf64','win64'):
     name=f'services-r{runtime}-t{test}-{fmt}';obj=out/(name+'.o');r=run([*prefix,'-f',fmt,'-DP1_TEST='+str(test),'-DRUNTIME_LEVEL='+str(runtime),NORMAL/'kernel/services_run.asm','-o',obj],name);self.assertEqual(0,r.returncode,r.stderr)
     self.assertEqual(runtime==7,b'user_smp_boot_begin'in obj.read_bytes());self.assertEqual(runtime==7,b'user_smp_normal_policy'in obj.read_bytes());evidence[name]=dict(passed=True,activated_by_default=runtime==7)
  r=run([*prefix,'-f','elf64','-DP1_TEST=0','-DRUNTIME_LEVEL=6','-DP6_USER_SMP=1',NORMAL/'kernel/services_run.asm','-o',out/'wrong-level.o'],'wrong-level');self.assertNotEqual(0,r.returncode);self.assertIn('requires desktop runtime7',r.stderr)
  (out/'probe.c').write_text(C)
  for bad in(False,True):
   source=NORMAL/'kernel/sched/user_boot.asm'
   if bad:
    source=out/'bad-policy.asm';text=(NORMAL/'kernel/sched/user_boot.asm').read_text();self.assertEqual(1,text.count('cmp rdi,3'));source.write_text(text.replace('cmp rdi,3','cmp rdi,2'))
   label='bad-two-cpu-activation'if bad else'good-policy';obj=out/(label+'.o');r=run([*prefix,'-f','win64'if os.name=='nt'else'elf64',source,'-o',obj],label+'-assemble');self.assertEqual(0,r.returncode,r.stderr);exe=out/(label+('.exe'if os.name=='nt'else''));r=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([]if os.name=='nt'else['-no-pie']),out/'probe.c',obj,'-o',exe],label+'-link');self.assertEqual(0,r.returncode,r.stderr);r=run([exe],label+'-native');self.assertEqual(1 if bad else 0,r.returncode,r.stdout+r.stderr);evidence[label]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
  for fmt in('elf64','win64'):
   r=run([*prefix,'-f',fmt,'-DP1_TEST=0','-DRUNTIME_LEVEL=7',NORMAL/'kernel/smp_runtime.asm','-o',out/('smp-'+fmt+'.o')],'smp-'+fmt);self.assertEqual(0,r.returncode,r.stderr)
  py_compile.compile(str(NORMAL/'tools/build.py'),cfile=str(out/'normal-build.pyc'),doraise=True)
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};self.assertEqual(before,after);(out/'validation-summary.json').write_text(json.dumps(dict(passed=True,candidate_only=True,normal_patch_applied=False,os_build_executed=False,actual_ap_cpl3_executed=False,raw_policy_native_executed=True,production_builder_syntax_checked=True,production_builder_actual_build_still_required=True,source_sha256=after,evidence=evidence),indent=2)+'\n');print('USER_SMP_NORMAL_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
