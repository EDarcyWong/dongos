"""Isolated path policy; independent raw UTF-8 and component-stack C model."""
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


class PathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=ROOT/'build/test/fs-path'/('run-'+uuid.uuid4().hex[:12]);cls.directory.mkdir(parents=True)
        cls.inputs=[HERE/name for name in ('services/fs/path.dg','tests/path_probe.dg','tests/path_probe.c','tests/test_fs_path.py','docs/fat-path-lfn.md')]
        cls.inputs += [ROOT/name for name in ('lang/dongc/frontend.py','lang/dongc/model.py','services/fs/fat32.dg','services/fs/protocol.dg','services/fs/service.dg')]
        cls.before={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        cls.evidence={};cls.compiled={}

    @classmethod
    def tearDownClass(cls):
        after={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        if after!=cls.before:raise AssertionError('path component or formal read-only inputs changed')
        (cls.directory/'validation-summary.json').write_text(json.dumps(dict(prototype_only=False,
            source_unchanged=True,source_sha256=after,filesystem_integrated=False,
            required_evidence_complete={'independent_native','formats_and_stack','actual_bad_implementations'}.issubset(cls.evidence),
            disk_or_guest_executed=False,full_build_executed=False,evidence=cls.evidence),indent=2)+'\n',encoding='utf-8')
        print('PATH_EVIDENCE '+str(cls.directory))

    def compile(self,mode,services=None):
        key=(mode,str(services))
        if key not in self.compiled:
            self.compiled[key]=compile_file(HERE/'tests/path_probe.dg',roots=[HERE/'tests',services or HERE/'services'],mode=mode)
        return self.compiled[key]

    def native(self,mode,label,services=None):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc,'NASM/GCC required for native path gate')
        output=self.directory/label/mode;output.mkdir(parents=True)
        compiled=self.compile(mode,services);source=output/'probe.asm';source.write_text(compiled.assembly,encoding='utf-8')
        obj=output/'probe.o'
        command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),'-o',obj,source],output,'assemble')
        exe=output/('probe.exe' if os.name=='nt' else 'probe');flags=['-mno-sse'] if os.name=='nt' else ['-no-pie','-D_DEFAULT_SOURCE']
        command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',*flags,HERE/'tests/path_probe.c',obj,'-o',exe],output,'link')
        result=command([exe],output,'native',success=False)
        return result,compiled

    def test_independent_utf8_table_stack_oracle_bounds_alias_and_guardpages(self):
        modes={}
        for mode in ('debug','release'):
            value,compiled=self.native(mode,'normal')
            self.assertEqual(0,value.returncode,value.stdout+value.stderr)
            self.assertIn('table3-7+component-stack atomic+guards+real-guardpages=ok',value.stdout)
            sizes={t['full_name']:t['size'] for t in compiled.layout_manifest['types']}
            self.assertEqual(1048,sizes['fs.path.Path'])
            modes[mode]=dict(returncode=0,output=value.stdout.strip())
        self.evidence['independent_native']=modes

    def test_elf_coff_single_function_and_all_reachable_direct_stack(self):
        nasm=tool('nasm','NASM');self.assertTrue(nasm,'NASM required')
        modes={}
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

    def test_actual_root_escape_and_surrogate_bad_implementations_rejected(self):
        original=(HERE/'services/fs/path.dg').read_text(encoding='utf-8')
        controls=[('root-escape','if (*path).components==0 {return error.RootEscape;}',
            'if (*path).components==0 {negative_hit(1);return;}',1),
            ('utf8-surrogate','if value<minimum||value>0x10ffff||(value>=0xd800&&value<=0xdfff) {return error.InvalidUtf8;}',
             'if value>=0xd800&&value<=0xdfff {negative_hit(2);}\n    if value<minimum||value>0x10ffff {return error.InvalidUtf8;}',2)]
        outcomes={}
        for label,needle,replacement,kind in controls:
            self.assertEqual(1,original.count(needle))
            services=self.directory/'controls'/label/'services';(services/'fs').mkdir(parents=True)
            changed=original.replace(needle,replacement,1).replace('module fs.path;',
                'module fs.path;\nunsafe extern "sysv64" ("path_negative_hit") fn negative_hit(kind:u64)void;',1)
            (services/'fs/path.dg').write_text(changed,encoding='utf-8');modes={}
            for mode in ('debug','release'):
                value,_=self.native(mode,label,services)
                self.assertEqual(1,value.returncode,value.stdout+value.stderr)
                self.assertEqual(1,value.stderr.count('PATH_NEGATIVE_HIT '+str(kind)),value.stderr)
                self.assertIn('PATH_MODEL_ASSERT',value.stderr);self.assertNotIn('panic',value.stderr)
                modes[mode]=dict(returncode=1,actual_marked_path_hit=1,stderr=value.stderr.strip())
            outcomes[label]=modes
        self.evidence['actual_bad_implementations']=outcomes


if __name__=='__main__':unittest.main(verbosity=2)
