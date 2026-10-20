import hashlib
import json
from pathlib import Path
import sys

WORKS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(WORKS.parent))
from dongos_coordination.client import CoordinationClient

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def audit(task_id):
    t=CoordinationClient().task('dongos',task_id)
    v=t.get('verification') or {}
    assert v.get('passed') and v.get('source_stable'),(task_id,v)
    assert v.get('process_stopped') is True
    assert all(c['tests']>0 and c['skips']==0 and c['returncode']==0 for c in v['checks'])
    for rel,digest in v['fingerprint'].items():
        assert sha(WORKS/rel)==digest,(task_id,rel)
    jobroot=WORKS/'.local/runs'/v['job']
    formal=json.loads((jobroot/'result.json').read_text(encoding='utf-8'))
    assert formal['passed'] and formal['source_stable'] and formal['process_stopped'] is True
    summaries=[]
    for p in (jobroot/'workspace').glob('*-works/build/'+t['number']+'/*/summary.json'):
        s=json.loads(p.read_text(encoding='utf-8'))
        count=0
        for rel,digest in s.get('artifact_sha256',{}).items():
            assert sha(p.parent/rel)==digest,(task_id,rel)
            count+=1
        summaries.append(dict(path=str(p),artifact_hashes_checked=count,records=s.get('records',[]),summary_sha256=sha(p)))
    return dict(task=task_id,rev=t['rev'],status=t['status'],verification=v,summaries=summaries)

if __name__=='__main__':
    reports=[audit(id) for id in sys.argv[1:]]
    output=WORKS/'reviews/2026-10-20-formal-acceptance-evidence.json'
    old=json.loads(output.read_text(encoding='utf-8')) if output.exists() else {}
    old.update({r['task']:r for r in reports})
    output.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for r in reports:
        print(json.dumps(dict(task=r['task'],rev=r['rev'],tests=sum(c['tests'] for c in r['verification']['checks']),artifacts=sum(s['artifact_hashes_checked'] for s in r['summaries']),job=r['verification']['job'])))
