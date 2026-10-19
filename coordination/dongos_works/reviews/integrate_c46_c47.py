"""Review-gated, path-only integration of C46/C47 with real mainline tests."""
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

w = Path(__file__).resolve().parents[1]
workspace = w.parents[1]
code = workspace/'code'
sys.path.insert(0, str(workspace/'coordination'))
from dongos_coordination.client import CoordinationClient
from dongos_coordination.mcp_server import TaskMCP
c = CoordinationClient()
m = TaskMCP(c, 'codex', 'codex-native-review-integration', 'coordinator')
specs = {
    'C46': ('nasm_checked_variable_shift', '已实际审查完整继承任务书/返修、生产与说明、全部永久测试及依赖。完整RCX宽64门禁在CL移位前；scratch64/16上界与一次发布正确。R1已关闭：同输入正式Dong好侧实际执行，全部15个非rsp GPR加rsp捕获，坏宽/漏guard按路由拒绝、坏rbx按保持数值拒绝，容量负控拒绝提前written。'),
    'C47': ('nasm_guarded_integer_divide', '已实际审查完整任务书/交付、生产与说明、全部永久测试及依赖。真实C31 guard→CR18 success标签→CR19除法顺序、标签互异、scratch224/32/64上界及一次发布正确。24原生向量检查商余/安全异常路由、15个GPR及rsp保持，实际坏Dong余数取反/安全异常路由互换/坏rbx及容量提前written均有同输入正式好侧和正常返回后的数值/路由/原子性拒绝。'),
}
ident = sys.argv[1]
name, note = specs[ident]
key = 'claude:'+ident
t = c.task('dongos', key)
v = t.get('verification')
assert v and v['passed'] and v['source_stable']
assert all(x['tests'] == 3 and x['skips'] == 0 for x in v['checks'])
assert t['status'] in ('submitted', 'accepted'), t['status']
original = {p: hashlib.sha256((w/p).read_bytes()).hexdigest() for p in t['write_paths']}
assert original == v['fingerprint']
if t['status'] == 'submitted':
    m.invoke('change_task', dict(project='dongos', task_id=key, rev=t['rev'], action='accept', note=note+'正式独立复验3项零skip且来源稳定；主线实际集成另做。'))
destinations = []
for ext in ('dg', 'md'):
    src = w/'claude-works/src/bootstrap'/(name+'.'+ext)
    dst = code/'lang/bootstrap'/(name+'.'+ext)
    assert not dst.exists() or dst.read_bytes() == src.read_bytes(), str(dst)
    shutil.copyfile(src, dst)
    destinations.append(dst)
source_test = w/'claude-works/tests'/('test_'+name+'.py')
s = source_test.read_text(encoding='utf-8')
a = s.index('WORKS=Path(')
b = s.index('if str(ROOT)', a)
s = s[:a]+'ROOT=Path(__file__).resolve().parents[2]\nWORKS=ROOT\n'+s[b:]
s = s.replace("WORKS/'claude-works/src/bootstrap/", "ROOT/'lang/bootstrap/")
s = s.replace("WORKS/'claude-works/build/"+ident+"'", "ROOT/'build/test/bootstrap-"+name.replace('_','-')+"'")
dest = code/'lang/tests'/('test_bootstrap_'+name+'.py')
assert not dest.exists() or dest.read_text(encoding='utf-8') == s, str(dest)
dest.write_text(s, encoding='utf-8')
destinations.append(dest)
spec = importlib.util.spec_from_file_location('integrated_'+ident, dest)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
tracked = destinations + list(mod.DEPS)
before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
start = time.monotonic()
r = subprocess.run([sys.executable, '-m', 'unittest', '-v', 'lang.tests.test_bootstrap_'+name], cwd=code, capture_output=True, text=True, timeout=600)
elapsed = time.monotonic()-start
out = w/'reviews'/('2026-10-19-'+ident+'-integration.log')
out.write_text(r.stdout+r.stderr, encoding='utf-8')
assert r.returncode == 0, r.stderr
assert re.search(r'Ran 3 tests in ', r.stderr) and '\nOK\n' in r.stderr and 'skipped=' not in r.stderr, r.stderr
assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
assert original == {p: hashlib.sha256((w/p).read_bytes()).hexdigest() for p in t['write_paths']}
t = c.task('dongos', key)
assert t['status'] == 'accepted'
note += f'主线实际复制.dg/.md及仅路径适配的永久测试；主线3项零skip{elapsed:.3f}秒，生产字节与正式输入相同，源码/依赖/主线文件SHA前后稳定。未运行OS/VM，不宣称完整L3。'
m.invoke('change_task', dict(project='dongos', task_id=key, rev=t['rev'], action='integrate', note=note))
report = dict(task=key, verification=v, mainline_tests=3, mainline_skips=0, elapsed=elapsed, fingerprints=before, review=note, status=c.task('dongos',key)['status'])
(w/'reviews'/('2026-10-19-'+ident+'-integration.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(key, report['status'], 'mainline 3 tests 0 skips', round(elapsed,3))
