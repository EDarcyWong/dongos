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
specs = {'D23': ('artifact_compare', '用户授权Codex直接完成原D23。生产描述符完整预检、别名区间、共同前缀先于长度差和256缺失标记正确，生产逻辑未改。修复测试双free/NULL负控协议/未初始化读取和对齐，隔离仅本模块并验证SHA，20个合法主向量含4096/4097及只读页保护成功检查、11独立可达预检。实际坏Dong漏末字节/提前写结果/仅查首字节别名在同输入好体先通过后分别由字段值/完整原子性/指定尾部预检拒绝。')}
ident = sys.argv[1]
name, note = specs[ident]
key = 'deepseek:'+ident
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
    src = w/'deepseek-works/src/bootstrap'/(name+'.'+ext)
    dst = code/'lang/bootstrap'/(name+'.'+ext)
    assert not dst.exists() or dst.read_bytes() == src.read_bytes(), str(dst)
    shutil.copyfile(src, dst)
    destinations.append(dst)
source_test = w/'deepseek-works/tests'/('test_'+name+'.py')
s = source_test.read_text(encoding='utf-8')
a = s.index('WORKS=Path(')
b = s.index('if str(ROOT)', a)
s = s[:a]+'ROOT=Path(__file__).resolve().parents[2]\nWORKS=ROOT\n'+s[b:]
s = s.replace("WORKS/'deepseek-works/src/bootstrap/", "ROOT/'lang/bootstrap/")
s = s.replace("WORKS/'deepseek-works/build/"+ident+"'", "ROOT/'build/test/bootstrap-"+name.replace('_','-')+"'")
dest = code/'lang/tests'/('test_bootstrap_'+name+'.py')
assert not dest.exists() or dest.read_text(encoding='utf-8') == s, str(dest)
dest.write_text(s, encoding='utf-8')
destinations.append(dest)
spec = importlib.util.spec_from_file_location('integrated_'+ident, dest)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
tracked = destinations + []
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
