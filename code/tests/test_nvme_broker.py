"""Native transaction oracle for exact formal NVMe capwalk and grant bodies."""
from pathlib import Path
import hashlib
import json
import os
import re
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
from tests.test_input import command
ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'tests/ahci_broker_fixtures'
def sha(raw):return hashlib.sha256(raw).hexdigest()

class NvmeBrokerTests(unittest.TestCase):
    def test_formal_capwalk_grant_and_actual_bad_controls(self):
        directory=ROOT/'build/test/nvme-broker'/('run-'+uuid.uuid4().hex[:12]);directory.mkdir(parents=True)
        formal=ROOT/'kernel/user/devices.dg';raw=formal.read_bytes()
        first=raw.index(b'unsafe fn interrupt_caps(');middle=raw.index(b'pub unsafe fn grant(',first)
        end=raw.index(b'pub fn granted_bars(',middle)
        capwalk,grant=raw[first:middle],raw[middle:end]
        names=[formal,FIXTURES/'harness-prefix.dg.in',FIXTURES/'harness-suffix.dg.in',ROOT/'tests/nvme_broker_probe.c',
               Path(__file__),*sorted((FIXTURES/'stubs').rglob('*.dg')),*sorted((ROOT/'lang/dongc').glob('*.py'))]
        before={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in names}
        extraction=dict(source_sha256=sha(raw),capwalk_start=first,capwalk_end=middle,grant_end=end,
                        capwalk_sha256=sha(capwalk),grant_sha256=sha(grant),capwalk_bytes=len(capwalk),grant_bytes=len(grant),original_bytes_preserved=True)
        (directory/'capwalk.original.dg.in').write_bytes(capwalk);(directory/'grant.original.dg.in').write_bytes(grant)
        prefix=(FIXTURES/'harness-prefix.dg.in').read_bytes()
        stub=b'unsafe fn interrupt_caps(ecam:u64,disable:bool)!u64 {return error.Invalid;}'
        self.assertEqual(1,prefix.count(stub))
        prefix=prefix.replace(stub,b'''unsafe extern "sysv64" ("broker_control16") fn host_control16(address:u64,value:u16)u64;
unsafe fn configuration_write16(address:u64,value:u16)!void {unsafe {if host_control16(address,value)!=0 {return error.Invalid;}}return;}
''')
        suffix=(FIXTURES/'harness-suffix.dg.in').read_bytes()+b'''
export("broker_caps") fn caps(ecam:u64,disable:u64,out:*u64)u64 {unsafe {
    match interrupt_caps(ecam,disable!=0) {ok(value)=>{*out=value;return 0;},err(code)=>{return code;},}
}}
'''
        controls={
            'no-capwalk':(b'if (try interrupt_caps(ecam,true))!=3 {return error.Invalid;}',
                          b'if nvm {negative_hit(1);}', 'interrupt_disabled()'),
            'no-cap-readback':(b'if ((try read32(ecam+offset))>>16)!=(planned as u32) {return error.Invalid;}',
                               b'negative_hit(2);', 'interrupt_disabled()'),
            'wrong-control-width':(b'try configuration_write16(ecam+offset+2,planned);',
                                    b'negative_hit(3);try write32(ecam+offset,(planned as u32)<<16);', 'off==16 || off==20'),
            'no-initial-readback':(b'if ((try read32(ecam+4))&65535)!=((old_command&~7) as u32) {return error.Invalid;}',
                                    b'negative_hit(4);', '(cfg[1]&7)==0'),
        }
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
        evidence={}
        for kind in ('normal',*controls):
            evidence[kind]={}
            for mode in ('debug','release'):
                where=directory/kind/mode;where.mkdir(parents=True)
                body=capwalk+grant
                if kind!='normal':
                    old,new,_=controls[kind];self.assertEqual(2 if kind in ('no-cap-readback','wrong-control-width') else 1,body.count(old));body=body.replace(old,new)
                else:self.assertEqual(1,body.count(capwalk));self.assertEqual(1,body.count(grant))
                source=where/'broker_probe.dg';source.write_bytes(prefix+body+suffix)
                compiled=compile_file(source,roots=[where,FIXTURES/'stubs'],mode=mode)
                maximum=max(map(int,re.findall(r'\bsub rsp, (\d+)',compiled.assembly)),default=0);self.assertLessEqual(maximum,4096)
                self.assertNotRegex(compiled.assembly.lower(),r'\b(?:invlpg|rdmsr|wrmsr|cr[0348]|xmm[0-9]+|ymm[0-9]+)\b')
                asm=where/'probe.asm';asm.write_text(compiled.assembly,encoding='utf-8');obj=where/'probe.o';native='win64' if os.name=='nt' else 'elf64'
                for fmt in ('win64','elf64') if kind=='normal' else (native,):
                    command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',obj if fmt==native else where/(fmt+'.o'),asm],where,'assemble-'+fmt)
                binary=where/('probe.exe' if os.name=='nt' else 'probe')
                command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-D__USE_MINGW_ANSI_STDIO=1',
                    *(['-mno-sse'] if os.name=='nt' else ['-no-pie']),ROOT/'tests/nvme_broker_probe.c',obj,'-o',binary],where,'link')
                trace=where/'events.jsonl';result=command([binary,trace],where,'execute',success=False)
                if kind=='normal':self.assertEqual(0,result.returncode,result.stdout+result.stderr);self.assertIn('NVME_BROKER_MODEL_OK',result.stdout)
                else:
                    self.assertEqual(1,result.returncode,result.stdout+result.stderr);self.assertIn('NVME_BROKER_NEGATIVE_HIT',result.stderr)
                    self.assertIn('NVME_BROKER_ASSERT',result.stderr);self.assertIn(controls[kind][2],result.stderr);self.assertNotIn('panic',result.stderr)
                first=[json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines() if '"case":1,' in line]
                destructive=[e for e in first if e['event'] in ('CONTROL16','BAR32','MAP','INSTALL')]
                self.assertEqual(1 if kind=='no-initial-readback' else 0,len(destructive))
                evidence[kind][mode]=dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,max_single_frame=maximum,
                    events_sha256=sha(trace.read_bytes()),event_bytes=trace.stat().st_size,first_failed_clear_destructive_events=len(destructive),actual_mutated_path_executed=kind!='normal')
        after={name:sha((ROOT/name).read_bytes()) for name in before};self.assertEqual(before,after)
        (directory/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_sha256=after,sources_unchanged=True,
            extracted_functions=extraction,actual_device_executed=False,actual_scratch_window_executed=False,
            actual_pagetables_executed=False,minimal_typed_stub_contracts=True,evidence=evidence),indent=2)+'\n',encoding='utf-8')
        print('NVME_BROKER_EVIDENCE',directory/'validation-summary.json')
