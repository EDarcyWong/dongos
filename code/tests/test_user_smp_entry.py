"""Tracked current table/frame assembly + real user-domain/queue/bridge native.

Privileged MSR/CR/IRET code is assembled, never executed by host tests.
"""
import hashlib,json,os,shutil,struct,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT
def sections(path):
 b=path.read_bytes();count=struct.unpack_from('<H',b,2)[0];opt=struct.unpack_from('<H',b,16)[0];result={}
 for i in range(count):
  o=20+opt+40*i;n=b[o:o+8].split(b'\0')[0].decode();result[n]=struct.unpack_from('<I',b,o+16)[0]
 return {n:result.get(n,0) for n in ('.text','.rodata','.data','.bss')}
MUTATION_POLICY="\nU ABI user_bridge_service_policy(U slot,U event,U frame){(void)slot;(void)event;(void)frame;return 0;}\n"
class Tests(unittest.TestCase):
 def test_per_cpu_architecture_and_bsp_deferred_policy(self):
  files=[*sorted((BASE/'kernel').rglob('*.*')),*sorted((BASE/'include').glob('*.inc')),ROOT/'tests/user_current_entry_probe.dg',ROOT/'tests/user_current_entry_probe.c',Path(__file__),ROOT/'include/user_context.inc',ROOT/'include/smp.inc',ROOT/'include/cpu.inc']
  before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
  out=ROOT/'build/test/p6-cpl3-native'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
  nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);evidence={}
  controls={
   'missing-RSP0':('kernel/sched/user_entry.asm','mov [rdi+CPU_TSS_RSP0],rax','nop'),
   'normal-IRQ-shared-IST':('kernel/sched/user_entry.asm','xor edx,edx\n    cmp ebx,8','mov edx,3\n    cmp ebx,8'),
   'kernel-only-user-code':('kernel/sched/user_entry.asm','mov rax,0x00affb000000ffff','mov rax,0x00af9b000000ffff'),
   'lose-hardware-DF-RF':('kernel/sched/user_entry.asm','mov [rdi+8],rax                 ; hardware DF/RF retained','and eax,0xad7\n    mov [rdi+8],rax'),
   'missing-guard-check':('kernel/sched/user_entry_plan.dg','||user_entry_guard(bottom-4096)!=1||user_entry_guard(top)!=1',''),
   'deferred-call-runs-on-AP':('kernel/sched/user_bridge.dg','try q.set_affinity((*d).engine,token,1);','try q.set_affinity((*d).engine,token,7);'),
   'no-kernel-xstate-restore':('kernel/sched/user_bridge.dg','user_bridge_restore((*header).kernel_xstate);',''),
   'skip-private-xstate-save':('kernel/sched/user_domain.dg','user_smp_arch_save((*c).capture_xstate);',''),
   'always-periodic-user-quantum':('kernel/sched/user_bridge.dg','let need=try q.needs_quantum((*d).engine,cpu);','let need=true;'),
   'old-IPI-GS-offset-assumption':('kernel/sched/user_legacy.asm','mov rsi,[rdi+UserSmpCpu.smp]','lea rsi,[rdi+UserSmpCpu.smp]'),
   'legacy-ACK-before-alltag-flush':('kernel/sched/user_legacy.asm','cmp rcx,1\n    jne .bad                       ; never ACK before actual all-tag invalidation','cmp rcx,rcx\n    jne .bad'),
   'missing-service-entry-quiescence':('kernel/sched/user_bridge.dg','let before=try ud.barrier_begin(d,cpu);try ud.barrier_wait(d,cpu,before,try deadline(d,cpu));',''),
   'missing-post-mutation-invalidation':('kernel/sched/user_bridge.dg','let after=try ud.barrier_begin(d,cpu);try ud.barrier_wait(d,cpu,after,try deadline(d,cpu));',''),
   'failure-misreported-as-idle':('kernel/sched/user_bridge.dg','}}return 0xffff_ffff_ffff_ffff;','}}return 0;'),
   'MSI-not-a-device-IRQ':('kernel/sched/user_bridge.dg','vector!=IDLE&&vector!=0x51&&vector!=0x5c&&vector!=0x60','vector!=IDLE&&vector!=0x51&&vector!=0x5c'),
  }
  def run(args,d,label):
   args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
   (d/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
  for fmt in ('win64','elf64'):
   for name in ('user_entry','user_arch','user_bridge_arch','user_legacy'):
    r=run([nasm,'-f',fmt,*nasm_flags(nasm),'-I',str(BASE/'include')+os.sep,'-I',str(ROOT/'include')+os.sep,BASE/'kernel/sched'/f'{name}.asm','-o',out/f'{name}-{fmt}.o'],out,f'arch-{name}-{fmt}')
    self.assertEqual(0,r.returncode,r.stderr)
  for mode in ('debug','release'):
   for variant in ('normal',*controls):
    d=out/(mode+'-'+variant);shutil.copytree(BASE/'kernel',d/'kernel');shutil.copytree(BASE/'include',d/'include')
    if variant!='normal':
     p,old,new=controls[variant];p=d/p;t=p.read_text();self.assertEqual(1,t.count(old));p.write_text(t.replace(old,new))
    (d/'probe.c').write_text((ROOT/'tests/user_current_entry_probe.c').read_text()+MUTATION_POLICY)
    c=compile_file(ROOT/'tests/user_current_entry_probe.dg',roots=[ROOT/'tests',d/'kernel'],mode=mode)
    self.assertNotRegex(c.assembly.lower(),r'\b(?:xmm\d+|ymm\d+|zmm\d+|cli|sti|invpcid|wrmsr|rdmsr)\b')
    layouts={v['full_name']:v for v in c.layout_manifest['types']}
    self.assertEqual(256,layouts['sched.user_entry_plan.Cpu']['size']);self.assertEqual(200,25*8);self.assertEqual(120,layouts['sched.user_domain.Cpu']['size']);self.assertEqual(12960,layouts['sched.multicore.Engine']['size'])
    (d/'layout.json').write_text(json.dumps(c.layout_manifest,indent=2)+'\n');(d/'probe.asm').write_text(c.assembly)
    fmt='win64' if os.name=='nt' else 'elf64';objects=[]
    for name,source in [('dong',d/'probe.asm'),('arch',d/'kernel/sched/user_entry.asm'),('legacy',d/'kernel/sched/user_legacy.asm')]:
     obj=d/(name+'.o');r=run([nasm,'-f',fmt,*nasm_flags(nasm),'-I',str(d/'include')+os.sep,'-I',str(ROOT/'include')+os.sep,source,'-o',obj],d,'assemble-'+name);self.assertEqual(0,r.returncode,r.stderr);objects.append(obj)
    exe=d/('probe.exe' if os.name=='nt' else 'probe');r=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([]if os.name=='nt'else['-no-pie']),d/'probe.c',*objects,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
    r=run([exe],d,'native');self.assertEqual(0 if variant=='normal' else 1,r.returncode,r.stdout+r.stderr)
    if variant!='normal':self.assertIn('user CPL3 current-source oracle line',r.stderr)
    evidence[mode+'-'+variant]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
  # No native fixture wrapper in the final size accounting.
  for name in ('user_domain','user_entry_plan','user_bridge'):
   c=compile_file(BASE/'kernel/sched'/f'{name}.dg',roots=[BASE/'kernel'],mode='release');a=out/(name+'-bare.asm');a.write_text(c.assembly);o=out/(name+'-bare.o');r=run([nasm,'-f','win64',*nasm_flags(nasm),a,'-o',o],out,'size-'+name);self.assertEqual(0,r.returncode,r.stderr);evidence[name+'_sections']=sections(o)
  for name in ('user_entry','user_arch','user_bridge_arch','user_legacy'):evidence[name+'_asm_sections']=sections(out/(name+'-win64.o'))
  after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files};self.assertEqual(before,after)
  (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),contract="tracked-current-cpl3-v1",current_source=True,historical_replay=False,privileged_paths_assembled_not_executed=True,real_domain_queue_bridge=True,service_and_hardware_boundaries_mocked=True,actual_ap_cpl3_executed=False,os_build_executed=False,source_sha256=after,sources_unchanged=True,evidence=evidence),indent=2)+'\n');print('USER_SMP_ENTRY_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
