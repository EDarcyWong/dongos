"""Full self-compiler ELF fixed point under the actual bounded pure job API."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest,uuid
from tools.compiler_job import exercise,ROOT
class CompilerJobTests(unittest.TestCase):
    def test_full_fixedpoint_and_preflight(self):
        work=ROOT/'build/test/compiler-job'/('run-'+uuid.uuid4().hex[:12])
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows=list(pool.map(lambda mode:exercise(work/mode,mode),['debug','release']))
        self.assertEqual(rows[0]['sources'],rows[1]['sources'])
        self.assertEqual(rows[0]['elf_sha256'],rows[1]['elf_sha256'])
        for row in rows:
            self.assertTrue(row['exact_fixedpoint'] and row['source_stable'])
            self.assertGreater(len(row['sources']),40)
            self.assertLessEqual(row['elf_bytes'],2*1024*1024)
            self.assertIn('32 atomic preflights',row['stdout'])
            self.assertIn('native semantic rejection',row['stdout'])
            self.assertIn('native backend capacity rejection',row['stdout'])
if __name__=='__main__':unittest.main()
