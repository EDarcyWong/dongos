"""Bracketed counter intervals and auditable bounded multirate consensus."""
from pathlib import Path
import hashlib
import json
import re
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
from tests.test_input import ROOT, command, native


class ClockCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=ROOT/'build/test/clock-calibration/host'/('run-'+uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs=[ROOT/p for p in ('kernel/irq/clock_calibration.dg','tests/clock_calibration_probe.dg','tests/clock_calibration_probe.c','tests/test_clock_calibration.py')]
        cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n',encoding='utf-8');cls.evidence={}

    @classmethod
    def tearDownClass(cls):
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        (cls.directory/'source-after.json').write_text(json.dumps(after,indent=2)+'\n',encoding='utf-8')
        if after!=cls.before:raise AssertionError('clock sources changed during native verification')
        (cls.directory/'validation-summary.json').write_text(json.dumps(dict(sources_unchanged=True,source_sha256=after,evidence=cls.evidence),indent=2)+'\n',encoding='utf-8')
        print('CLOCK_CALIBRATION_EVIDENCE '+str(cls.directory))

    def test_native_interval_math_consensus_wrap_and_atomic_rejection(self):
        modes={}
        for mode in ('debug','release'):
            value,compiled=native('clock_calibration_probe',self.directory/'normal'/mode,mode,[ROOT/'kernel'])
            self.assertEqual(0,value.returncode,value.stdout+value.stderr)
            self.assertIn('independent-u128+frequency-plane-grid',value.stdout);self.assertIn('masks=24/32/64 atomic+guards=ok',value.stdout)
            types={t['full_name']:t for t in compiled.layout_manifest['types']}
            for label,size in (('Reference',24),('Sample',64),('Estimate',88),('Result',192)):self.assertEqual(size,types['irq.clock_calibration.'+label]['size'])
            modes[mode]=dict(returncode=value.returncode,output=value.stdout.strip())
        self.evidence['independent_interval_math_and_consensus']=modes

    def test_elf_coff_and_bounded_generated_stack(self):
        nasm=tool('nasm','NASM')
        if not nasm:self.fail('NASM required for the clock policy gate')
        modes={}
        for mode in ('debug','release'):
            compiled=compile_file(ROOT/'tests/clock_calibration_probe.dg',roots=[ROOT/'tests',ROOT/'kernel'],mode=mode)
            functions,current={},None
            for line in compiled.assembly.splitlines():
                match=re.match(r'^\$([A-Za-z_][A-Za-z0-9_]*):$',line)
                if match:current=match.group(1);functions[current]=dict(frame=16,calls=set())
                if current:
                    match=re.search(r'\bsub rsp, (\d+)',line)
                    if match:functions[current]['frame']+=int(match.group(1))
                    match=re.search(r'\bcall \$([A-Za-z_][A-Za-z0-9_]*)\b',line)
                    if match:functions[current]['calls'].add(match.group(1))
            def stack(name,path=()):
                self.assertNotIn(name,path);item=functions[name]
                return item['frame']+max([stack(child,(*path,name)) for child in item['calls'] if child in functions] or [0])
            maximum=max(stack(name) for name in functions);self.assertLessEqual(maximum,4096)
            directory=self.directory/'formats'/mode;directory.mkdir(parents=True);asm=directory/'probe.asm';asm.write_text(compiled.assembly,encoding='utf-8')
            for fmt in ('elf64','win64'):command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',directory/(fmt+'.o'),asm],directory,fmt)
            modes[mode]=dict(generated_direct_call_path_bytes=maximum,formats=['elf64','win64'])
        self.evidence['formats_and_stack']=modes

    def test_real_old_single_sample_and_quantization_controls_are_rejected(self):
        source=(ROOT/'kernel/irq/clock_calibration.dg').read_text(encoding='utf-8')
        marker='pub unsafe fn select(reference:*const Reference,samples:[]const Sample,out:*Result)!void {'
        self.assertEqual(1,source.count(marker))
        legacy=source[:source.index(marker)]+marker+'''
    unsafe {
        negative_hit(1);let s=samples[0];var old=EMPTY_RESULT;
        let ticks=forward(s.r0_before,s.r1_before,(*reference).mask);
        let ns=try nanoseconds(reference,ticks,false);
        old.tsc_hz=try rate(s.t1-s.t0,ns,false);old.lapic_hz=try rate(s.c0-s.c1,ns,false);
        *out=old;
    }return;
}
'''
        needle='let lower=b-a-1;let upper=c+1;'
        self.assertEqual(1,source.count(needle))
        quantization=source.replace(needle,'negative_hit(2);let lower=b-a;let upper=c;',1)
        controls={}
        for label,text,kind in (('old-single-sample',legacy,1),('missing-quantization',quantization,2)):
            staging=self.directory/'controls'/label/'kernel';(staging/'irq').mkdir(parents=True)
            text=text.replace('module irq.clock_calibration;','module irq.clock_calibration;\nunsafe extern "sysv64" ("clock_negative_hit") fn negative_hit(kind:u64)void;',1)
            (staging/'irq/clock_calibration.dg').write_text(text,encoding='utf-8');modes={}
            for mode in ('debug','release'):
                value,_=native('clock_calibration_probe',staging.parent/mode,mode,[staging])
                self.assertEqual(1,value.returncode,value.stdout+value.stderr);self.assertIn('CLOCK_NEGATIVE_HIT '+str(kind),value.stderr);self.assertNotIn('panic',value.stderr)
                if kind==1:self.assertIn('distance(value.tsc_hz,UINT64_C(3410000000))<UINT64_C(10000000)',value.stderr);self.assertIn('CLOCK_OLD_SINGLE_RATE ',value.stderr)
                else:self.assertIn('memcmp(&out.value,&expected,sizeof expected)==0',value.stderr)
                modes[mode]=dict(returncode=value.returncode,stderr=value.stderr.strip())
            controls[label]=modes
        self.evidence['executed_bad_policies']=controls


if __name__=='__main__':unittest.main(verbosity=2)
