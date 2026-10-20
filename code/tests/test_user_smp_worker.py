"""NEW synthetic current-source PIE and finite native SIMD controls, not history."""
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
from tools.elf_symbols import read_elf_symbols
from tools.build import find_tool
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tests/fixtures/current_user_smp'
C=r'''
#include <stdint.h>
#include <cpuid.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t U;
extern U __attribute__((sysv_abi)) user_smp_app_run(U*,U,U,U);
static U p[24] __attribute__((aligned(64)));
static unsigned avx_enabled(void){
 unsigned a,b,c,d,lo,hi;
 if(!__get_cpuid(1,&a,&b,&c,&d)||(c&0x1c000000)!=0x1c000000)return 0;
 __asm__ volatile("xgetbv":"=a"(lo),"=d"(hi):"c"(0));(void)hi;return (lo&6)==6;
}
static const U arguments[5]={78117,88219,99323,104729,115249};
int main(void){unsigned avx=avx_enabled();for(unsigned i=0;i<5;i++){memset(p,0,sizeof p);U result=user_smp_app_run(p,arguments[i],8+i,16384);
#ifdef BAD
 if(result!=0x060b0041||p[5]!=1||p[12]==p[14]||p[7]!=avx){fprintf(stderr,"busy-worker corrupt-xstate control failed\n");return 1;}
#else
 if(result||p[0]!=1||p[1]!=arguments[i]||p[2]!=8+i||p[3]!=16384||p[4]||p[5]||p[6]>255||p[7]!=avx||!(p[8]|p[9]|p[10]|p[11])||!p[16]||p[17]<p[16]){fprintf(stderr,"busy-worker actual register/SIMD oracle failed\n");return 1;}
#endif
 }puts("busy-worker five finite GPR XMM and gated upper-YMM native probes passed; host syscall excluded");return 0;}
'''
class Tests(unittest.TestCase):
 def test_actual_pie_and_native_busy_loop(self):
  source=BASE/'services/apps/user_smp_worker.dg';asm=BASE/'services/apps/user_smp_worker.asm';files=[source,asm,Path(__file__),ROOT/'services/lib/syscalls.asm',ROOT/'services/gfx/accelerated.asm',ROOT/'services/gfx/transform.asm',ROOT/'services/lib/service.ld',*[ROOT/p for p in ('services/lib/sys.dg','services/lib/abi.dg','services/lib/files.dg','services/fs/protocol.dg','services/fs/handles.dg')]];before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files}
  out=ROOT/'build/test/p6-user-worker-native'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);nasm,cc,ld=tool('nasm','NASM'),tool('gcc','CC'),find_tool('ld.lld','LD_LLD');self.assertTrue(nasm and cc and ld);evidence={}
  def run(args,label):
   args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60);(out/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');self.assertEqual(0,r.returncode,r.stdout+r.stderr);return r
  for mode in ('debug','release'):
   c=compile_file(source,roots=[BASE/'services',ROOT/'services',ROOT/'lang/std'],mode=mode);p=out/(mode+'.asm');p.write_text(c.assembly);objects=[]
   for name,path in [(mode,p),('syscalls',files[3]),('accelerated',files[4]),('transform',files[5]),('worker',asm)]:
    obj=out/(mode+'-'+name+'.o');run([nasm,'-f','elf64',*nasm_flags(nasm),path,'-o',obj],'elf-'+mode+'-'+name);objects.append(obj)
   elf=out/(mode+'.elf');run([ld,'-pie','--no-dynamic-linker','-z','norelro','--build-id=none','-T',files[6],'-o',elf,*objects],'link-'+mode)
   symbols=read_elf_symbols(elf);self.assertIn('user_smp_app_run',symbols);self.assertIn('_start',symbols);self.assertIn('service_main',symbols);self.assertTrue(any('50524f4245' in name for name in symbols));evidence[mode+'_elf_sha256']=hashlib.sha256(elf.read_bytes()).hexdigest();evidence[mode+'_elf_bytes']=elf.stat().st_size
  (out/'probe.c').write_text(C)
  for bad in (False,True):
   label='corrupt'if bad else'normal';obj=out/(label+'.o');exe=out/(label+('.exe'if os.name=='nt'else''));run([nasm,'-f','win64'if os.name=='nt'else'elf64',*nasm_flags(nasm),'-DUSER_APP_NATIVE=1','-DUSER_APP_CORRUPT='+str(int(bad)),asm,'-o',obj],label+'-assemble');disassembler=tool('objdump','OBJDUMP');self.assertTrue(disassembler);disassembly=run([disassembler,'-d',obj],label+'-disassemble');self.assertNotRegex(disassembly.stdout,r'\bsyscall\b');run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*(['-DBAD=1']if bad else[]),*([]if os.name=='nt'else['-no-pie']),out/'probe.c',obj,'-o',exe],label+'-link');r=run([exe],label+'-native');evidence[label]=r.stdout
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};self.assertEqual(before,after);(out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_binding='new-synthetic-current-test-workload',synthetic_test_workload=True,historical_candidate_replay=False,base_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),guest_argument_virtual=0x44000000,guest_filesystem_operations_executed=False,actual_user_pie_linked=True,finite_native_mode_has_no_host_syscall=True,actual_cpl3_executed=False,os_build_executed=False,source_sha256=after,sources_unchanged=True,evidence=evidence),indent=2)+'\n');print('USER_SMP_WORKER_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
