"""Actual candidate host bridge integration, not a simulated platform branch."""
import hashlib,json,os,subprocess,sys,unittest,uuid
from pathlib import Path
WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS
if not (ROOT/'lang/dongc').is_dir():
 location=Path(json.loads((WORKS/'project.json').read_text(encoding='utf-8'))['source_root'])
 ROOT=location if location.is_absolute()else(WORKS/location).resolve()
class HostBridgeTests(unittest.TestCase):
 def test_actual_candidate_bridges_run_all_compatibility_cases(self):
  state=WORKS/'codex-works/build/L3HOST13'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
  candidates=[WORKS/'codex-works/l3host'/n for n in ('test_l3a_globals.py','test_l3a_native_regression.py')]
  original=[ROOT/'lang/tests'/p.name for p in candidates]
  watched=[Path(__file__),*candidates,*original]
  before={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in watched}
  script=state/'run-candidates.py'
  script.write_text("""import importlib.util,json,sys,unittest
from pathlib import Path
root=Path(sys.argv[1]);candidate=Path(sys.argv[2]);report=Path(sys.argv[3]);sys.path.insert(0,str(root))
import lang.tests
for name in ('test_l3a_globals','test_l3a_native_regression'):
 spec=importlib.util.spec_from_file_location('lang.tests.'+name,candidate/(name+'.py'))
 module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;setattr(lang.tests,name,module);spec.loader.exec_module(module)
 module.CAND=root/'lang/bootstrap'
suite=unittest.defaultTestLoader.loadTestsFromName('lang.tests.test_l3a_mainline_compatibility')
r=unittest.TextTestRunner(verbosity=2).run(suite)
report.write_text(json.dumps(dict(passed=r.wasSuccessful(),tests=r.testsRun,skips=len(r.skipped),failures=len(r.failures),errors=len(r.errors)),indent=2)+chr(10))
raise SystemExit(not r.wasSuccessful() or bool(r.skipped))
""")
  command=[sys.executable,'-X','utf8',str(script),str(ROOT),str(candidates[0].parent),str(state/'inner-result.json')]
  process=subprocess.run(command,capture_output=True,text=True,timeout=1500,cwd=ROOT)
  (state/'process.log').write_text(process.stdout+process.stderr,encoding='utf-8')
  after={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in watched}
  (state/'summary.json').write_text(json.dumps(dict(command=command,returncode=process.returncode,source_before=before,source_after=after,source_stable=before==after),indent=2)+'\n')
  self.assertEqual(process.returncode,0,process.stdout+process.stderr)
  inner=json.loads((state/'inner-result.json').read_text());self.assertTrue(inner['passed']);self.assertEqual((inner['tests'],inner['skips']),(3,0))
  self.assertEqual(before,after)
  print('L3HOST13 actual host candidate evidence',state)
if __name__=='__main__':unittest.main()
