"""Real full compiler closure under the unchanged bounded pure-job contract."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import sys
import unittest
import uuid

WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS if (WORKS/'lang').is_dir() else WORKS.parents[1]/'code'
sys.path.insert(0,str(ROOT))
from tools.compiler_job import exercise
from tools import compiler_job

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class G5ClosureNativeTests(unittest.TestCase):
    def test_real_debug_release_full_elf_fixedpoint_and_preflight(self):
        candidate=WORKS/'codex-works/g5-closure/src/bootstrap/compiler_job.dg'
        full=WORKS/'codex-works/g5-full/src/bootstrap'
        if 'codex-works' not in Path(__file__).parts:
            candidate=ROOT/'lang/bootstrap/compiler_job.dg';full=ROOT/'lang/bootstrap'
        selected=[full/name for name in ('semantic_types.dg','program_ir.dg','lower_program.dg','nasm_program.dg','frontend_diagnostics.dg','native_assembler.dg')]+[candidate]
        inputs={str(p):sha(p) for p in selected+[Path(__file__),Path(compiler_job.__file__)]}
        for base in (ROOT/'lang/bootstrap',ROOT/'lang/std',ROOT/'lang/dongc'):
            inputs.update({str(p):sha(p) for p in base.rglob('*') if p.is_file() and p.suffix in ('.dg','.py')})
        work=ROOT/'build/test/G5-closure'/('run-'+uuid.uuid4().hex[:12])
        source=work/'source';(source/'lang').mkdir(parents=True)
        shutil.copytree(ROOT/'lang/bootstrap',source/'lang/bootstrap')
        shutil.copytree(ROOT/'lang/std',source/'lang/std')
        for p in selected:shutil.copyfile(p,source/'lang/bootstrap'/p.name)
        rows=[]
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                rows=list(pool.map(lambda mode:exercise(work/mode,mode,source.resolve()),('debug','release')))
            self.assertEqual(rows[0]['sources'],rows[1]['sources'])
            self.assertEqual(rows[0]['elf_sha256'],rows[1]['elf_sha256'])
            for row in rows:
                self.assertTrue(row['exact_fixedpoint'] and row['source_stable'])
                self.assertGreater(len(row['sources']),40)
                self.assertLessEqual(row['elf_bytes'],2*1024*1024)
                self.assertEqual(row['arena_bytes'],56*1024*1024)
                self.assertEqual(row['stack_bytes'],65536)
                for evidence in ('32 atomic preflights','native semantic rejection','native backend capacity rejection',
                    'native-generated startup prefix/call RCX poison and R10 arguments'):
                    self.assertIn(evidence,row['stdout'])
        finally:
            after={p:sha(p) for p in inputs}
            (work/'frozen-inputs.json').write_text(json.dumps(dict(before=inputs,after=after,source_stable=inputs==after,rows=rows),indent=2)+'\n')
            self.assertEqual(inputs,after,'compiler input changed during closure test')

if __name__=='__main__':unittest.main()
