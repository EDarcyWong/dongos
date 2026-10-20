"""Current per-CPU queues; executes policy, never an AP or user context."""
# Tests the tracked current implementation, not a replay of unavailable candidate sources.
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
BASE_REVISION=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
CURRENT=ROOT/'kernel'

def direct_stack(assembly):
    functions={};current=None;in_text=False
    for line in assembly.splitlines():
        if line.startswith('section '):in_text=line=='section .text';current=None
        if not in_text:continue
        match=re.fullmatch(r'\$?((?:multi_|__dg_)\w+):',line)
        if match:current=match.group(1);functions[current]=[]
        elif current:functions[current].append(line.strip())
    cache={}
    def visit(name,parents=()):
        if name in cache:return cache[name]
        if name in parents:raise AssertionError('recursive runqueue path')
        body=functions[name];pushes=[line for line in body if line.startswith('push ')]
        if pushes!=['push rbp']:raise AssertionError('unmodelled stack prologue')
        frames=[int(m[1]) for line in body if (m:=re.fullmatch(r'sub rsp, (\d+)',line))]
        if len(frames)!=1:raise AssertionError('unmodelled stack allocation')
        children=[]
        for line in body:
            if line.startswith('call '):
                child=line[5:].lstrip('$')
                if child=='__dong_panic':continue
                if child not in functions:raise AssertionError('unexpected external/indirect scheduling callback '+child)
                children.append(visit(child,(*parents,name)))
        amount,path=max(children,key=lambda item:item[0]) if children else (0,[])
        cache[name]=(frames[0]+16+amount,[name,*path]);return cache[name]
    results={name:visit(name) for name in functions if name.startswith('multi_')}
    maximum,path=max(results.values(),key=lambda item:item[0])
    return dict(bytes=maximum,path=path,normal_return_paths=True,panic_path_excluded=True)

class MulticoreSchedulingTests(unittest.TestCase):
    def test_independent_priority_affinity_steal_and_failure_model(self):
        source=CURRENT/'sched/multicore.dg'
        self.assertTrue(source.is_file(),'tracked current-source scheduler must exist')
        files=[source,ROOT/'tests/multicore_sched_probe.dg',ROOT/'tests/multicore_sched_probe.c',Path(__file__)]
        before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        out=ROOT/'build/test/p6-runqueue'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);evidence={}
        controls={
            'steal-ignores-affinity':('if ((*e).threads[next as usize].affinity&(1<<cpu as u64))!=0','if true'),
            'revived-thread-token':('let generation=(*e).threads[id].generation+1;','let generation:u64=1;'),
            'fifo-head-used-as-tail':('let tail=(*q).tails[p];','let tail=(*q).heads[p];'),
        }
        def command(args,d,label):
            args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
            (d/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
        for mode in ('debug','release'):
            evidence[mode]={}
            for variant in ('normal',*controls):
                d=out/(mode+'-'+variant);d.mkdir();modules=CURRENT
                if variant!='normal':
                    modules=d/'kernel';(modules/'sched').mkdir(parents=True)
                    body=source.read_text();old,new=controls[variant];self.assertEqual(1,body.count(old));(modules/'sched/multicore.dg').write_text(body.replace(old,new))
                c=compile_file(ROOT/'tests/multicore_sched_probe.dg',roots=[ROOT/'tests',modules],mode=mode)
                layouts={v['full_name']:v for v in c.layout_manifest['types']}
                for name,size in (('Thread',64),('Cpu',552),('Engine',12960),('Dispatch',40),('Move',32)):
                    self.assertEqual(size,layouts['sched.multicore.'+name]['size'])
                self.assertNotRegex(c.assembly.lower(),r'\b(?:invlpg|invpcid|rdmsr|wrmsr|hlt|cli|sti|cpuid|xsave|fxsave)\b')
                maximum=max(map(int,re.findall(r'\bsub rsp, (\d+)',c.assembly)),default=0)
                self.assertLessEqual(maximum,512);stack=direct_stack(c.assembly);self.assertLessEqual(stack['bytes'],2048)
                asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o';fmt='win64' if os.name=='nt' else 'elf64'
                for format_ in (('win64','elf64') if variant=='normal' else (fmt,)):
                    target=obj if format_==fmt else d/(format_+'.o')
                    r=command([nasm,'-f',format_,*nasm_flags(nasm),'-o',target,asm],d,'assemble-'+format_);self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe')
                r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),ROOT/'tests/multicore_sched_probe.c',obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                r=command([exe],d,'execute')
                if variant=='normal':self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('independent checks passed',r.stdout)
                else:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('multicore oracle failed line',r.stderr)
                evidence[mode][variant]=dict(stdout=r.stdout,stderr=r.stderr,returncode=r.returncode,maximum_single_frame=maximum,direct_stack=stack)
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files};self.assertEqual(before,after)
        (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,current_source=str(source.relative_to(ROOT)),source_binding='tracked-current-source',historical_candidate_replay=False,base_revision=BASE_REVISION,source_sha256=after,sources_unchanged=True,evidence=evidence,hardware_ap_scheduling_executed=False,kernel_tree_unchanged_by_test=True),indent=2)+'\n')
        print('MULTICORE_SCHED_EVIDENCE',out)
