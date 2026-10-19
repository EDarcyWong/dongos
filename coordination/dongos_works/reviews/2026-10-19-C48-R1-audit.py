"""Independently inspect all raw RBX good/bad observations from the formal R1 run."""
import hashlib
import json
from pathlib import Path
import struct

WORKS=Path(__file__).resolve().parents[1]
JOB='ac548cd8d9db4152bfa2059c2d4cf58e'
jobroot=WORKS/'.local/runs'/JOB
formal=json.loads((jobroot/'result.json').read_text(encoding='utf-8'))
assert formal['passed'] and formal['source_stable']
assert len(formal['checks'])==1 and formal['checks'][0]['tests']==4 and formal['checks'][0]['skips']==0
for name,sha in formal['fingerprint'].items():
    assert hashlib.sha256((WORKS/name).read_bytes()).hexdigest()==sha,name
runs=list((jobroot/'workspace/claude-works/build/C48').glob('run-*'))
assert len(runs)==1,runs
run=runs[0]
summary=json.loads((run/'summary.json').read_text(encoding='utf-8'))
assert summary['stable'] and summary['source_sha256']==summary['source_sha256_after']
assert any(x['test']=='bad-rbx-clobbered'for x in summary['records'])
planted=0x0bbb0bbb0bbb0bbb
others=(0x0b0b0b0b0b0b0b0b,0x1212121212121212,0x1313131313131313,0x1414141414141414,0x1515151515151515)
records=[]
artifacts={}
for mode in ('debug','release'):
    raw=[]
    for prefix in ('bad-rbx-good-','bad-rbx-'):
        p=run/(prefix+mode+'.native.output')
        data=p.read_bytes();assert len(data)==16*12*8
        raw.append(list(struct.iter_unpack('<12Q',data)))
        artifacts[p.name]=hashlib.sha256(data).hexdigest()
    for index,(good,bad)in enumerate(zip(*raw)):
        assert good[0]==bad[0],(mode,index,'RAX differs')
        assert good[1]==good[2] and bad[1]==bad[2],(mode,index,'RSP imbalance')
        assert good[3]==good[4]==bad[3]==planted
        assert bad[4]==planted+8,(mode,index,'wrong RBX witness')
        assert good[5:10]==bad[5:10]==others
        assert good[10]==bad[10]==0x5ca1ab1e0ddba11c
        assert good[11]==bad[11]==0
    records.append(dict(mode=mode,vectors=16,rax_equal=True,rsp_balanced=True,other_callee_saved_preserved=True,
                        canary_intact=True,alignment_zero=True,good_rbx=planted,bad_rbx=planted+8,rbx_delta=8))
report=dict(task='claude:C48',submission_rev=10,formal_job=JOB,formal=formal,run=str(run),
            input_sha256=summary['source_sha256'],records=records,raw_sha256=artifacts,
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            source_unchanged_since_formal=True,acceptance_performed_by_audit=False,integration_performed_by_audit=False)
output=WORKS/'reviews/2026-10-19-C48-R1-evidence.json'
output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(evidence=str(output),checks=formal['checks'],stable=True,records=records),indent=2))
