"""Run production caller/epoch grants against an independent C state model."""
from pathlib import Path
import hashlib
import json
import os
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
from tests.test_input import command
from tests.test_fat32 import stack_bound

ROOT=Path(__file__).resolve().parents[1]


class FileHandleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=ROOT/'build/test/fs-handles'/('run-'+uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.inputs=[ROOT/name for name in ('services/fs/handles.dg','tests/fs_handles_probe.dg',
            'tests/fs_handles_probe.c','tests/test_fs_handles.py')]
        cls.before=cls.hashes();cls.results=[]

    @classmethod
    def hashes(cls):
        return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}

    @classmethod
    def tearDownClass(cls):
        after=cls.hashes()
        (cls.directory/'validation-summary.json').write_text(json.dumps(dict(
            source_unchanged=after==cls.before,source_sha256=after,results=cls.results,
            actual_kernel_identity=False,actual_service_rpc=False),indent=2)+'\n')
        print('FS_HANDLES_EVIDENCE '+str(cls.directory))
        if after!=cls.before:raise AssertionError('grant sources changed during native acceptance')

    def run_native(self,mode,label='normal',replacement=None):
        out=self.directory/label/mode;out.mkdir(parents=True)
        services=ROOT/'services'
        if replacement:
            services=out/'services';(services/'fs').mkdir(parents=True)
            source=(ROOT/'services/fs/handles.dg').read_text()
            needle,changed,kind=replacement
            self.assertEqual(1,source.count(needle))
            source=source.replace(needle,changed,1).replace('module fs.handles;',
                'module fs.handles;\nunsafe extern "sysv64" ("fsh_negative_hit") fn negative_hit(kind:u64)void;',1)
            (services/'fs/handles.dg').write_text(source)
        compiled=compile_file(ROOT/'tests/fs_handles_probe.dg',roots=[ROOT/'tests',services],mode=mode)
        sizes={t['full_name']:t['size'] for t in compiled.layout_manifest['types']}
        self.assertEqual(1104,sizes['fs.handles.Entry']);self.assertEqual(35352,sizes['fs.handles.Table'])
        stack=stack_bound(compiled.assembly);self.assertLessEqual(stack,4096)
        assembly=out/'probe.asm';assembly.write_text(compiled.assembly)
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
        for fmt in ('elf64','win64'):
            command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',out/(fmt+'.o'),assembly],out,'assemble-'+fmt)
        obj=out/('win64.o' if os.name=='nt' else 'elf64.o')
        exe=out/('probe.exe' if os.name=='nt' else 'probe')
        flags=[] if os.name=='nt' else ['-no-pie']
        command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',
            *flags,ROOT/'tests/fs_handles_probe.c',obj,'-o',exe],out,'link')
        result=command([exe],out,'native',success=False)
        if replacement:
            self.assertEqual(1,result.returncode,result.stdout+result.stderr)
            self.assertIn('FSH_NEGATIVE_HIT '+str(replacement[2]),result.stderr)
            self.assertIn('FSH_MODEL_ASSERT',result.stderr);self.assertNotIn('unexpected panic',result.stderr)
        else:
            self.assertEqual(0,result.returncode,result.stdout+result.stderr)
            self.assertIn('steps=20000 guardbytes=ok',result.stdout)
        self.results.append(dict(label=label,mode=mode,returncode=result.returncode,stack=stack,
            stdout=result.stdout,stderr=result.stderr))

    def test_production_table_owner_rights_epochs_retirement_and_independent_model(self):
        for mode in ('debug','release'):self.run_native(mode)

    def test_actual_bad_owner_rights_and_epoch_implementations_rejected(self):
        controls=[('owner','if (*item).owner!=owner||(required&~(*item).rights)!=0 {return error.Denied;}',
            'if (*item).owner!=owner {negative_hit(1);}\n    if (required&~(*item).rights)!=0 {return error.Denied;}',1),
            ('rights','if (*item).owner!=owner||(required&~(*item).rights)!=0 {return error.Denied;}',
            'if (required&~(*item).rights)!=0 {negative_hit(2);}\n    if (*item).owner!=owner {return error.Denied;}',2),
            ('epoch','let slot=token&255;let generation=(token>>8)&MAX_GENERATION;',
            'if token>>32!=(*table).epoch {negative_hit(3);}\n    let slot=token&255;let generation=(token>>8)&MAX_GENERATION;',3)]
        for label,needle,changed,kind in controls:
            if label=='epoch':
                # A second literal substitution removes the actual production gate.
                original=(ROOT/'services/fs/handles.dg').read_text()
                needle='if owner==0||slot==0||slot>32||generation==0||token>>32!=(*table).epoch {return error.InvalidHandle;}'
                changed='if token>>32!=(*table).epoch {negative_hit(3);}\n    if owner==0||slot==0||slot>32||generation==0 {return error.InvalidHandle;}'
                self.assertEqual(1,original.count(needle))
            for mode in ('debug','release'):self.run_native(mode,label,(needle,changed,kind))


if __name__=='__main__':unittest.main(verbosity=2)
