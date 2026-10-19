"""Independently audit every good/bad native record from the formal R1 runs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

w=Path(__file__).resolve().parents[1]
n=sys.argv[1];assert n in ('C49','C50')
stem='nasm_u64_select_function'if n=='C49'else'nasm_u64_forward_function'
job={'C49':'e60916643e6247918773e0f6206d8cd7','C50':'563c3a6bab364e49b5d794a4511832d6'}[n]
jobroot=w/'.local/runs'/job
formal=json.loads((jobroot/'result.json').read_text(encoding='utf-8'))
assert formal['passed']and formal['source_stable']
assert len(formal['checks'])==1 and formal['checks'][0]['tests']==4 and formal['checks'][0]['skips']==0
for p,sha in formal['fingerprint'].items():assert hashlib.sha256((w/p).read_bytes()).hexdigest()==sha,p
runs=list((jobroot/'workspace/claude-works/build'/n).glob('run-*'));assert len(runs)==1
run=runs[0];summary=json.loads((run/'summary.json').read_text(encoding='utf-8'))
assert summary['stable']and summary['source_sha256']==summary['source_sha256_after']
assert any(x['test']=='bad-rbx-clobbered'for x in summary['records'])
spec=importlib.util.spec_from_file_location('r1_inputs',w/('claude-works/tests/test_'+stem+'.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
planted=0x0bbb0bbb0bbb0bbb;canary=0x5ca1ab1e0ddba11c
others=(0x0b0b0b0b0b0b0b0b,0x1212121212121212,0x1313131313131313,0x1414141414141414,0x1515151515151515)
expected_count=20 if n=='C49'else 16
width=12 if n=='C49'else 22
assert len(m.VECTORS)==expected_count
records=[];artifact_sha={}
for mode in ('debug','release'):
    observations=[]
    for prefix in ('bad-rbx-good-','bad-rbx-'):
        p=run/(prefix+mode+'.native.output');data=p.read_bytes()
        assert len(data)==expected_count*width*8
        observations.append(list(struct.iter_unpack('<%dQ'%width,data)))
        artifact_sha[p.name]=hashlib.sha256(data).hexdigest()
    routes={True:0,False:0}
    for i,(good,bad,v)in enumerate(zip(*observations,m.VECTORS)):
        assert good[0]==bad[0]
        assert good[1]==good[2]and bad[1]==bad[2]
        assert good[3]==good[4]==bad[3]==planted and bad[4]==planted+8
        assert good[5:10]==bad[5:10]==others
        assert good[10]==bad[10]==canary and good[11]==bad[11]==0
        if n=='C49':
            condition,a,b=v[2],v[5],v[6]
            sa=a-(1<<64)if a&(1<<63)else a;sb=b-(1<<64)if b&(1<<63)else b
            yes=(a==b,a!=b,a<b,a<=b,a>b,a>=b,sa<sb,sa<=sb,sa>sb,sa>=sb)[condition]
            assert good[0]==(v[7]if yes else v[8]);routes[yes]+=1
        else:
            args=[v[6][a]for a in v[5]]
            for x in (good,bad):
                assert x[12:16]==(1,i,8,len(args))
                assert list(x[16:16+len(args)])==args
            h=0xc0ffee0000000000|len(args);mask=(1<<64)-1
            for j,x in enumerate(args):h=((h*0x100000001b3)&mask)^((x+(j+1)*0x9e3779b97f4a7c15)&mask)
            assert good[0]==h|(1<<63)
    if n=='C49':assert routes=={True:10,False:10}
    records.append(dict(mode=mode,vectors=expected_count,rax_correct=True,rsp_balanced=True,other_callee_saved_preserved=True,
                        canary_intact=True,alignment_correct=True,rbx_good=planted,rbx_bad=planted+8,rbx_delta=8,
                        routes=routes if n=='C49'else None,callee_records_correct=True if n=='C50'else None))
report=dict(task='claude:'+n,submission_rev=8,formal_job=job,formal=formal,run=str(run),input_sha256=summary['source_sha256'],
            records=records,raw_sha256=artifact_sha,source_unchanged_since_formal=True,
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
out=w/'reviews'/('2026-10-19-'+n+'-R1-evidence.json')
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(task=n,evidence=str(out),checks=formal['checks'],records=records),indent=2))
