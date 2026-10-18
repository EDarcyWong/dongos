"""Native HBA callback model; no syscalls, build_service, VM or hardware."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / 'tests'
SERVICES = ROOT / 'services'
OUTPUT = ROOT / 'build/test/nvme-runtime'
sys.path.insert(0, str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
from tests.test_input import command


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


class NvmeRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = OUTPUT / ('run-' + uuid.uuid4().hex[:12]);cls.directory.mkdir(parents=True)
        cls.inputs = [SERVICES / 'drivers/nvme.dg', SERVICES / 'drivers/nvme_core.dg',
                      TESTS / 'nvme_runtime_probe.dg', TESTS / 'nvme_runtime_probe.c', Path(__file__)]
        cls.inputs += [ROOT / 'services/drivers' / (n+'.dg') for n in ('virtio_blk','virtio_pci','pci')]
        cls.before = {str(p.relative_to(ROOT)): sha(p) for p in cls.inputs}
        cls.evidence = {}
        cls.stage = cls.directory / 'snapshot'
        (cls.stage / 'drivers').mkdir(parents=True)
        for source in cls.inputs:
            if source.suffix=='.dg' and source.name!='nvme_runtime_probe.dg':
                shutil.copyfile(source, cls.stage / 'drivers' / source.name)
        shutil.copyfile(TESTS / 'nvme_runtime_probe.dg', cls.stage / 'nvme_runtime_probe.dg')

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)): sha(p) for p in cls.inputs}
        if after!=cls.before: raise AssertionError('runtime model inputs changed during verification')
        summary = dict(formal_source=True, passed=len(cls.evidence)==3, hardware_io=False, qemu_boots=0, actual_kernel_enable_tested=False,
                       source_sha256=after, source_unchanged=True, evidence=cls.evidence)
        (cls.directory / 'validation-summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
        print('NVME_RUNTIME_EVIDENCE='+str(cls.directory))

    def native(self,mode,output,stage):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
        output.mkdir(parents=True)
        compiled=compile_file(stage/'nvme_runtime_probe.dg',roots=[stage],mode=mode)
        self.assertEqual(['__dong_panic'],compiled.runtime_symbols)
        asm=output/'probe.asm';asm.write_text(compiled.assembly,encoding='utf-8');obj=output/'probe.o'
        command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',obj,asm],output,'assemble')
        exe=output/('probe.exe' if os.name=='nt' else 'probe');flags=['-mno-sse'] if os.name=='nt' else ['-no-pie']
        command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',*flags,
                 TESTS/'nvme_runtime_probe.c',obj,'-o',exe],output,'link')
        return command([exe],output,'native',success=False),compiled

    def test_exact_callbacks_commands_clock_and_retention(self):
        result={}
        for mode in ('debug','release'):
            native,compiled=self.native(mode,self.directory/'native'/mode,self.stage)
            self.assertEqual(0,native.returncode,native.stdout+native.stderr)
            self.assertIn('CAP-TO-CSTS queue-order actual-SQE-PRPs CID-phase doorbells durable-flush retained-all-guards=ok',native.stdout)
            types={t['full_name']:t for t in compiled.layout_manifest['types']}
            for name,size in (('State',656),('Ops',56),('Info',56)):
                self.assertEqual((size,8),(types['drivers.nvme.'+name]['size'],types['drivers.nvme.'+name]['alignment']))
            result[mode]=native.stdout.strip()
        self.evidence['callback_hba_model']=result

    def test_real_bad_adapter_controls(self):
        source=(self.stage/'drivers/nvme.dg').read_text(encoding='utf-8')
        controls=(('enable-before-queues','try address(s,0x28,lease.physical+core.ASQ);',
                   'MUTANT_HITS+=1;let granted=(*(*s).ops).enable((*s).context);try address(s,0x28,lease.physical+core.ASQ);'),
                  ('wrong-cq-head','try write(s,doorbell((*s).limits.doorbell_stride,(*q).qid,true),result.cq_head);',
                   'MUTANT_HITS+=1;try write(s,doorbell((*s).limits.doorbell_stride,(*q).qid,true),result.cq_head^1);'),
                  ('free-faulted-lease','(*s).info.ready=0;(*s).info.faulted=1;(*s).busy=0;',
                   '(*s).info.ready=0;(*s).info.faulted=1;(*s).busy=0;if (*s).info.held!=0 {MUTANT_HITS+=1;let freed=(*(*s).ops).release((*s).context,&(*s).lease);}'),
                  ('fixed-ready-500ms','if tick-start>=(*s).limits.ready_timeout_ms {return error.Timeout;}',
                   'if tick-start>=500 {MUTANT_HITS+=1;return error.Timeout;}'))
        outcomes={}
        for name,needle,replacement in controls:
            self.assertEqual(1,source.count(needle));stage=self.directory/'controls'/name/'snapshot'
            shutil.copytree(self.stage,stage)
            (stage/'drivers/nvme.dg').write_text(source.replace(needle,replacement).replace('module drivers.nvme;',
                'module drivers.nvme;\npub var MUTANT_HITS:u64=0;',1),encoding='utf-8')
            p=stage/'nvme_runtime_probe.dg';wrapper=p.read_text(encoding='utf-8')
            self.assertEqual(1,wrapper.count('fn mutant_hits()u64 {return 0;}'))
            p.write_text(wrapper.replace('fn mutant_hits()u64 {return 0;}',
                                        'fn mutant_hits()u64 {return nv.MUTANT_HITS;}'),encoding='utf-8')
            outcomes[name]={}
            for mode in ('debug','release'):
                native,_=self.native(mode,stage.parent/mode,stage)
                self.assertEqual(1,native.returncode,native.stdout+native.stderr)
                self.assertRegex(native.stderr,r'NVME_RUNTIME_MUTANT_PATH_HIT=[1-9][0-9]*')
                self.assertIn('NVMe runtime oracle line',native.stderr)
                outcomes[name][mode]=native.stderr.strip()
        self.evidence['actually_executed_bad_adapters']=outcomes

    def test_formats_stack(self):
        nasm=tool('nasm','NASM');self.assertTrue(nasm);outcomes={}
        for mode in ('debug','release'):
            compiled=compile_file(self.stage/'nvme_runtime_probe.dg',roots=[self.stage],mode=mode)
            output=self.directory/'formats'/mode;output.mkdir(parents=True)
            asm=output/'probe.asm';asm.write_text(compiled.assembly,encoding='utf-8')
            self.assertNotRegex(compiled.assembly,r'(?m)^section \.(?:bss|data)\b')
            self.assertNotRegex(compiled.assembly,r'\b(?:xmm|ymm|zmm)[0-9]+\b')
            functions,current,text={},None,False
            for line in compiled.assembly.splitlines():
                if line.startswith('section '):text=line=='section .text';current=None
                if not text:continue
                match=re.match(r'^\$([A-Za-z_][A-Za-z0-9_]*):$',line)
                if match:current=match[1];functions[current]=dict(frame=16,calls=set())
                if current:
                    match=re.search(r'\bsub rsp, (\d+)',line)
                    if match:functions[current]['frame']+=int(match[1])
                    match=re.search(r'\bcall \$([A-Za-z_][A-Za-z0-9_]*)\b',line)
                    if match:functions[current]['calls'].add(match[1])
            def stack(name,path=()):
                self.assertNotIn(name,path)
                f=functions[name];return f['frame']+max([stack(c,(*path,name)) for c in f['calls'] if c in functions] or [0])
            maximum=max(map(stack,functions));self.assertLessEqual(maximum,8192)
            decoded={}
            for name,value in functions.items():
                match=re.fullmatch(r'__dg_m([0-9a-f]+)_f([0-9a-f]+)',name)
                label=bytes.fromhex(match[1]).decode()+'.'+bytes.fromhex(match[2]).decode() if match else name
                decoded[label]=dict(local_with_return_and_rbp=value['frame'],direct_stack=stack(name))
            for fmt in ('elf64','win64'):
                command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',output/(fmt+'.o'),asm],output,fmt)
            outcomes[mode]=dict(maximum_direct_call_stack=maximum,global_mutable_bytes=0,functions=decoded,formats=['elf64','win64'])
        self.evidence['formats_stack']=outcomes


if __name__=='__main__':unittest.main()
