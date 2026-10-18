"""Pure LFN byte codec: independent native C oracle, no disks or guests."""
from pathlib import Path
import hashlib
import json
import os
import re
import sys
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT
sys.path.insert(0,str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_input import command


class LfnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=ROOT/'build/test/fs-lfn'/('run-'+uuid.uuid4().hex[:12]);cls.directory.mkdir(parents=True)
        cls.inputs=[HERE/name for name in ('services/fs/lfn.dg','tests/lfn_probe.dg','tests/lfn_probe.c','tests/test_fs_lfn.py','docs/fat-path-lfn.md')]
        cls.inputs += [ROOT/'services/fs/path.dg']
        cls.inputs += [ROOT/name for name in ('lang/dongc/frontend.py','lang/dongc/model.py','services/fs/fat32.dg','services/fs/protocol.dg','services/fs/service.dg')]
        cls.before={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        cls.evidence={};cls.compiled={}

    @classmethod
    def tearDownClass(cls):
        after={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        if after!=cls.before:raise AssertionError('LFN component or read-only dependencies changed')
        (cls.directory/'validation-summary.json').write_text(json.dumps(dict(prototype_only=False,
            source_unchanged=True,source_sha256=after,filesystem_integrated=False,
            required_evidence_complete={'independent_native','formats_and_stack','actual_bad_implementations'}.issubset(cls.evidence),
            disk_or_guest_executed=False,full_build_executed=False,evidence=cls.evidence),indent=2)+'\n',encoding='utf-8')
        print('LFN_EVIDENCE '+str(cls.directory))

    def compile(self,mode,services=None):
        key=(mode,str(services))
        if key not in self.compiled:
            roots=[ROOT/'tests',services or ROOT/'services']
            self.compiled[key]=compile_file(ROOT/'tests/lfn_probe.dg',roots=roots,mode=mode)
        return self.compiled[key]

    def native(self,mode,label,services=None):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc,'NASM/GCC required')
        output=self.directory/label/mode;output.mkdir(parents=True)
        compiled=self.compile(mode,services);source=output/'probe.asm';source.write_text(compiled.assembly,encoding='utf-8')
        obj=output/'probe.o'
        command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',obj,source],output,'assemble')
        exe=output/('probe.exe' if os.name=='nt' else 'probe');flags=['-mno-sse'] if os.name=='nt' else ['-no-pie','-D_DEFAULT_SOURCE']
        command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',*flags,HERE/'tests/lfn_probe.c',obj,'-o',exe],output,'link')
        return command([exe],output,'native',success=False),compiled

    def test_independent_raw_bytes_utf16_random_atomic_alias_and_guardpages(self):
        modes={}
        for mode in ('debug','release'):
            value,compiled=self.native(mode,'normal');self.assertEqual(0,value.returncode,value.stdout+value.stderr)
            self.assertIn('raw32+utf16+atomic+real-guardpages=ok',value.stdout)
            sizes={t['full_name']:t['size'] for t in compiled.layout_manifest['types']}
            self.assertEqual(680,sizes['fs.lfn.Group']);self.assertEqual(1040,sizes['fs.lfn.Name'])
            modes[mode]=dict(returncode=0,output=value.stdout.strip())
        self.evidence['independent_native']=modes

    def test_elf_coff_single_function_and_all_reachable_direct_stack(self):
        nasm=tool('nasm','NASM');self.assertTrue(nasm,'NASM required');modes={}
        for mode in ('debug','release'):
            compiled=self.compile(mode);functions={};current=None
            for line in compiled.assembly.splitlines():
                match=re.match(r'^\$([A-Za-z_][A-Za-z0-9_]*):$',line)
                if match:current=match[1];functions[current]=dict(frame=16,calls=set())
                if current:
                    match=re.search(r'\bsub rsp, (\d+)',line)
                    if match:functions[current]['frame']+=int(match[1])
                    match=re.search(r'\bcall \$([A-Za-z_][A-Za-z0-9_]*)\b',line)
                    if match:functions[current]['calls'].add(match[1])
            def stack(name,active=()):
                self.assertNotIn(name,active);value=functions[name]
                return value['frame']+max([stack(child,(*active,name)) for child in value['calls'] if child in functions] or [0])
            maximum=max(map(stack,functions));single=max(v['frame'] for v in functions.values())
            self.assertLessEqual(single,4096);self.assertLessEqual(maximum,4096)
            output=self.directory/'formats'/mode;output.mkdir(parents=True);source=output/'probe.asm';source.write_text(compiled.assembly,encoding='utf-8')
            for fmt in ('elf64','win64'):command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',output/(fmt+'.o'),source],output,fmt)
            modes[mode]=dict(single_function_bytes=single,generated_reachable_stack_bytes=maximum,
                external_host_panic_stack_included=False,recursive=False,formats=['elf64','win64'])
        self.evidence['formats_and_stack']=modes

    def test_actual_checksum_ordinal_padding_and_surrogate_mutants_rejected(self):
        original=(HERE/'services/fs/lfn.dg').read_text(encoding='utf-8')
        controls=[
            ('checksum','if entries[base+13]!=sum {return error.Corrupt;}',
             'if entries[base+13]!=sum {negative_hit(1);}',1),
            ('ordinal','if entries[base]!=ordinal||entries[base+11]!=15||entries[base+12]!=0',
             'if entries[base]!=ordinal {negative_hit(2);}\n        if entries[base+11]!=15||entries[base+12]!=0',2),
            ('padding','if ended {if unit!=0xffff {return error.Corrupt;}}',
             'if ended {if unit!=0xffff {negative_hit(3);}}',3),
            ('surrogate','else if unit>=0xdc00&&unit<=0xdfff {return error.InvalidUnicode;}',
             'else if unit>=0xdc00&&unit<=0xdfff {negative_hit(4);try emit(&candidate,unit);}',4),
        ]
        outcomes={}
        for label,needle,replacement,kind in controls:
            self.assertEqual(1,original.count(needle))
            services=self.directory/'controls'/label/'services';(services/'fs').mkdir(parents=True)
            changed=original.replace(needle,replacement,1).replace('module fs.lfn;',
                'module fs.lfn;\nunsafe extern "sysv64" ("lfn_negative_hit") fn negative_hit(kind:u64)void;',1)
            (services/'fs/lfn.dg').write_text(changed,encoding='utf-8');modes={}
            # The resolver rejects shadowing across roots. Each isolated mutant
            # root gets the exact current formal path dependency, not a fallback
            # root containing another fs.lfn and not any build prototype input.
            (services/'fs/path.dg').write_bytes((ROOT/'services/fs/path.dg').read_bytes())
            for mode in ('debug','release'):
                value,_=self.native(mode,label,services)
                self.assertEqual(1,value.returncode,value.stdout+value.stderr)
                self.assertIn('LFN_NEGATIVE_HIT '+str(kind),value.stderr)
                self.assertIn('LFN_MODEL_ASSERT',value.stderr);self.assertNotIn('panic',value.stderr)
                modes[mode]=dict(returncode=1,actual_marked_path_hit=True,stderr=value.stderr.strip())
            outcomes[label]=modes
        self.evidence['actual_bad_implementations']=outcomes


if __name__=='__main__':unittest.main(verbosity=2)
