"""Independent native model of the kernel-admitted process catalog."""
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
class ProcessCatalogR6Tests(unittest.TestCase):
    def test_exact_catalog_dependencies_scope_generation_and_events(self):
        names=('kernel/user/processes.dg','services/lib/process_abi.dg','tests/process_catalog_probe.dg','tests/process_catalog_r6_probe.c','tests/test_process_catalog_r6.py')
        before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in names}
        out=ROOT/'build/test/process-catalog-r6'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);evidence={}
        def command(args,d,label):
            args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
            (d/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
        try:
            controls={
                'slot-token-revival':('(*c).incarnation[slot]+=1;let incarnation=', '(*c).incarnation[slot]=1;let incarnation='),
                'shell-control-essential':('if actor==0{if !write||((*c).configs[id].flags&abi.ORDINARY)!=0{return;}}', 'if actor==0{return;}'),
                'forged-ready-incarnation':('||(*c).incarnation[slot]!=incarnation', '||false'),
                'vacant-physical-terminal':('    if actor<SLOTS&&(*c).configuration[actor]==14&&(*c).slot[14]==actor as u64{', '    if actor==14{return;}if actor<SLOTS&&(*c).configuration[actor]==14&&(*c).slot[14]==actor as u64{'),
                'compositor-controls-drivers':('if actor==3{if !write||(id>=14&&id<=17){return;}}','if actor==3{return;}'),
                'terminal-controls-essential':('&&(!write||((*c).configs[id].flags&abi.ORDINARY)!=0){return;}','&&true{return;}'),
                'terminal-stale-token':('&&terminal.process==((incarnation<<8)|(actor as u64+1))','&&true'),
                'config16-truncation':('pub const CONFIGS:usize=18;','pub const CONFIGS:usize=16;'),
                'failure-clobbers-output':('    try dependencies(c,id);\n    if (*c).sequence', '    if out!=null{(*out).argument=0;}\n    try dependencies(c,id);\n    if (*c).sequence'),
            }
            for mode,variant in ((mode,variant) for mode in ('debug','release') for variant in ('normal',*controls)):
                d=out/(mode+'-'+variant);d.mkdir();roots=[ROOT/'tests',ROOT/'kernel',ROOT/'services']
                if variant!='normal':
                    (d/'kernel/user').mkdir(parents=True);source=(ROOT/names[0]).read_text();old,new=controls[variant]
                    self.assertEqual(1,source.count(old));(d/'kernel/user/processes.dg').write_text(source.replace(old,new))
                    roots=[ROOT/'tests',d/'kernel',ROOT/'services']
                c=compile_file(ROOT/names[2],roots=roots,mode=mode)
                layouts={v['full_name']:v for v in c.layout_manifest['types']}
                for name,size in (('lib.process_abi.Config',128),('lib.process_abi.Snapshot',64),('lib.process_abi.Event',64),('user.processes.Catalog',10776)):
                    self.assertEqual(size,layouts[name]['size'])
                self.assertNotRegex(c.assembly.lower(),r'\b(?:invlpg|invpcid|rdmsr|wrmsr|hlt|cli|sti)\b')
                asm=d/'probe.asm';asm.write_text(c.assembly);obj=d/'probe.o';fmt='win64' if os.name=='nt' else 'elf64'
                for target,format_ in ((obj,fmt),(d/'other.o','elf64' if fmt=='win64' else 'win64')):
                    r=command([nasm,'-f',format_,*nasm_flags(nasm),'-o',target,asm],d,'assemble-'+format_);self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe')
                r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),ROOT/names[3],obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                r=command([exe],d,'execute');evidence[mode+'-'+variant]=dict(stdout=r.stdout,stderr=r.stderr,returncode=r.returncode)
                if variant=='normal':self.assertEqual(0,r.returncode,r.stdout+r.stderr)
                else:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('catalog oracle failed line',r.stderr)
        finally:
            after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in names}
            passed=len(evidence)==2*(1+len(controls)) and all(v['returncode']==(0 if name.endswith('-normal') else 1) for name,v in evidence.items())
            (out/'validation-summary.json').write_text(json.dumps(dict(passed=passed,source_sha256=after,sources_unchanged=before==after,evidence=evidence),indent=2)+'\n')
        self.assertEqual(before,after);print('PROCESS_CATALOG_R6_EVIDENCE',out)
