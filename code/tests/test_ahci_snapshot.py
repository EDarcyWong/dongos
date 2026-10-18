"""Candidate-only phased publication; no VM, device or production mutation."""
import hashlib,json,os,shutil,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'build/test/ahci-snapshot-candidate'
class Tests(unittest.TestCase):
    def test_real_adapter_phased_publication_and_actual_bad_controls(self):
        files=[BASE/'services/drivers'/name for name in ('ahci.dg','ahci_core.dg','virtio_pci.dg','virtio_blk.dg','pci.dg')]
        files += [BASE/'previous-empty-only.dg',ROOT/'services/drivers/ahci_core.dg',ROOT/'tests/ahci_runtime_probe.dg',ROOT/'tests/ahci_runtime_probe.c',ROOT/'tests/ahci_snapshot_probe.c',ROOT/'tests/test_ahci_snapshot.py']
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        self.assertEqual((BASE/'services/drivers/ahci_core.dg').read_bytes(),(ROOT/'services/drivers/ahci_core.dg').read_bytes())
        out=ROOT/'build/test/ahci-snapshot'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
        source=(BASE/'services/drivers/ahci.dg').read_text()
        controls={
          'previous-production-empty-only':None,
          'ignore-status-change':('if ci==sample.ci&&sact==sample.sact&&interrupts==sample.interrupts&&tfd==sample.tfd&&serr==sample.serr {','if true {'),
          'reject-captured-busy-window':('if stable&&(sample.tfd&0x88)!=0 {','if false {'),
          'missing-marker-no-deadline':('if v.now_ms-(*s).transfer.start_ms>=(*s).transfer.timeout_ms{return error.core.Timeout;}','if false{return error.core.Timeout;}'),
          'graft-later-status':('sample=core.Sample {generation:(*s).transfer.generation,ci:ci,sact:sact,interrupts:interrupts,\n                    tfd:tfd,serr:serr,prdbc:0,now_ms:0,fis:[0;256]};','sample.interrupts=interrupts;sample.tfd=tfd;sample.serr=serr;stable=true;'),
        }
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);evidence={}
        def command(args,d,label):
            args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
            (d/(label+'.json')).write_text(json.dumps(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
        for mode in ('debug','release'):
            for variant in ('normal',*controls):
                d=out/(mode+'-'+variant);stage=d/'snapshot';(stage/'drivers').mkdir(parents=True)
                for name in ('ahci.dg','ahci_core.dg','virtio_pci.dg','virtio_blk.dg','pci.dg'):shutil.copy2(BASE/'services/drivers'/name,stage/'drivers'/name)
                shutil.copy2(ROOT/'tests/ahci_runtime_probe.dg',stage/'ahci_runtime_probe.dg')
                text=source
                if variant=='previous-production-empty-only':text=(BASE/'previous-empty-only.dg').read_text()
                elif variant!='normal':
                    old,new=controls[variant];self.assertEqual(1,text.count(old));text=text.replace(old,new)
                (stage/'drivers/ahci.dg').write_text(text)
                compiled=compile_file(stage/'ahci_runtime_probe.dg',roots=[stage],mode=mode)
                self.assertEqual(['__dong_panic'],compiled.runtime_symbols)
                asm=d/'probe.asm';asm.write_text(compiled.assembly);obj=d/'probe.o'
                r=command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe');r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),ROOT/'tests/ahci_snapshot_probe.c',obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                r=command([exe],d,'native');evidence[mode+'-'+variant]={key:getattr(r,key) for key in ('returncode','stdout','stderr')}
                self.assertEqual(0 if variant=='normal' else 1,r.returncode,r.stdout+r.stderr)
                if variant=='normal':self.assertIn('AHCI_SNAPSHOT_PHASE_PASS',r.stdout)
                else:self.assertIn('AHCI runtime oracle line',r.stderr)
        after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files};self.assertEqual(before,after)
        (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,candidate_only=True,source_unchanged=True,core_unchanged=True,hardware_io=False,source_sha256=after,evidence=evidence),indent=2)+'\n')
        print('AHCI_SNAPSHOT_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
