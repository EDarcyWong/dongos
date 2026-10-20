"""Tickless Current CPL0 AP adapter; CPU/MMIO callbacks mocked, no AP executed."""
# Tests the tracked current implementation, not a replay of unavailable candidate sources.
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
BASE_REVISION=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
BASE=ROOT
class Tests(unittest.TestCase):
    def test_adapter_context_handoff_xstate_migration_and_failstop(self):
        source=BASE/'kernel/sched/parallel.dg'
        files=[source,BASE/'kernel/sched/multicore.dg',BASE/'kernel/sched/parallel.asm',BASE/'kernel/smp/bootstrap.asm',ROOT/'kernel/smp/bootstrap.asm',ROOT/'include/cpu.inc',ROOT/'include/smp.inc',ROOT/'tests/parallel_tickless_probe.dg',ROOT/'tests/parallel_tickless_probe.c',Path(__file__),BASE/'kernel/sched/parallel_boot.dg',BASE/'kernel/sched/parallel_probe.asm']
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in files}
        out=ROOT/'build/test/p6-tickless-native'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True);evidence={}
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
        controls={
          'skip-retire-notification':('parallel_live_retire(id,previous,frame);',''),
          'skip-save':('parallel_arch_save((*((*d).threads+index)).xstate);',''),
          'skip-restore':('if xstate!=0{parallel_arch_restore(xstate);}','if false{parallel_arch_restore(xstate);}'),
          'release-in-critical':('if (*c).depth!=0{return frame;}','if false{return frame;}'),
          'no-stack-handoff-check':('parallel_arch_on_scheduler((*c).scheduler_bottom,(*c).scheduler_top)!=1','false'),
          'wrong-root-accepted':('parallel_arch_root()!=(*d).root','false'),
          'lost-wakeup-ipi':('if parallel_arch_kick((*c).lapic,(*c).apic)!=0','if false'),
          'always-arm-idle':('if (*c).timer_need!=0{try arm(d,c);}', 'if true{try arm(d,c);}'),
          'skip-stop':('if parallel_arch_timer((*c).lapic,0,0)!=0', 'if false'),
          'lost-idle-ipi':('if (mask&(1<<cpu as u64))!=0{try notify(d,cpu);}', 'if cpu==1&&(mask&(1<<cpu as u64))!=0{try notify(d,cpu);}'),
          'no-local-timer':('if parallel_arch_timer((*c).lapic,(*c).mode,value)!=0','if false'),
        }
        def command(args,d,label):
            args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
            (d/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
        asm_source=(BASE/'kernel/sched/parallel.asm').read_text()
        self.assertLess(asm_source.index('mov rsp,rax\n    and rsp,-16'),asm_source.index('call parallel_dispatch'))
        for name in ('parallel','bootstrap','parallel_probe'):
            path=BASE/('kernel/smp/bootstrap.asm'if name=='bootstrap'else'kernel/sched/'+name+'.asm')
            for fmt in ('win64','elf64'):
                r=command([nasm,'-f',fmt,*nasm_flags(nasm),'-I',str(ROOT/'include')+os.sep,path,'-o',out/(name+'-'+fmt+'.o')],out,'assemble-'+name+'-'+fmt);self.assertEqual(0,r.returncode,r.stderr)
        for mode in ('debug','release'):
            compiled=compile_file(BASE/'kernel/sched/parallel_boot.dg',roots=[BASE/'kernel',ROOT/'kernel',ROOT/'services',ROOT/'lang/std',ROOT/'lang/examples'],mode=mode)
            layouts={v['full_name']:v for v in compiled.layout_manifest['types']};self.assertEqual(128,layouts['sched.parallel_boot.Probe']['size'])
            (out/('builder-'+mode+'-layout.json')).write_text(json.dumps(compiled.layout_manifest,indent=2)+'\n')
        for mode in ('debug','release'):
            for variant in ('normal',*controls):
                d=out/(mode+'-'+variant);kernel=d/'kernel';(kernel/'sched').mkdir(parents=True)
                text=source.read_text();
                if variant!='normal':old,new=controls[variant];self.assertEqual(1,text.count(old));text=text.replace(old,new)
                (kernel/'sched/parallel.dg').write_text(text);(kernel/'sched/multicore.dg').write_bytes(files[1].read_bytes())
                c=compile_file(ROOT/'tests/parallel_tickless_probe.dg',roots=[ROOT/'tests',kernel],mode=mode)
                self.assertNotRegex(c.assembly.lower(),r'\b(?:xmm\d+|ymm\d+|zmm\d+|fxsave|xsave|xrstor|fxrstor|invlpg|wrmsr|rdmsr|cli|sti)\b')
                layouts={v['full_name']:v for v in c.layout_manifest['types']};self.assertEqual(184,layouts['sched.parallel.Frame']['size']);self.assertEqual(12960,layouts['sched.multicore.Engine']['size'])
                asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o';r=command([nasm,'-f','win64'if os.name=='nt'else'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe'if os.name=='nt'else'probe');r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([]if os.name=='nt'else['-no-pie']),ROOT/'tests/parallel_tickless_probe.c',obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                scenarios=('normal','tickless','stack-fail','root-fail','timer-fail','stop-fail','kick-fail','frame-fail')if variant=='normal'else({'no-stack-handoff-check':'stack-fail','wrong-root-accepted':'root-fail'}.get(variant,'tickless'if variant in ('always-arm-idle','skip-stop','lost-idle-ipi')else'normal'),)
                for scenario in scenarios:
                    r=command([exe,scenario],d,scenario);self.assertEqual(0 if variant=='normal'else 1,r.returncode,r.stdout+r.stderr)
                    if variant!='normal':self.assertIn('parallel adapter oracle line',r.stderr)
                    evidence[mode+'-'+variant+'-'+scenario]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
        after={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in files};self.assertEqual(before,after)
        (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_binding='tracked-current-source',historical_candidate_replay=False,base_revision=BASE_REVISION,timer_contract='tickless-competition',dispatch_event='RESCHEDULE',retire_notification_checked=True,real_runqueue_and_adapter=True,hardware_callbacks_mocked=True,actual_ap_executed=False,source_sha256=after,sources_unchanged=True,evidence=evidence),indent=2)+'\n');print('PARALLEL_TICKLESS_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
