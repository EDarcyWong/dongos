"""Read formal artifacts and retain independent review evidence, without rebuilding workers."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

WORKS=Path(__file__).resolve().parents[1]
CONFIG={'C52':('claude','nasm_u64_module','72281b9c169340bd9124bf7eb7a7e7a1',6),
        'D25':('deepseek','nasm_i64_switch_function','a54f3e5a53d845f897bf9d2a4cdae27c',3)}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(number):
    owner,stem,job,tests=CONFIG[number]
    jobroot=WORKS/'.local/runs'/job
    formal=json.loads((jobroot/'result.json').read_text(encoding='utf-8'))
    assert formal['passed'] and formal['source_stable']
    assert len(formal['checks'])==1
    check=formal['checks'][0]
    assert check['tests']==tests and check['skips']==0 and check['returncode']==0
    assert not check['cancelled'] and not check['timed_out']
    for path,expected in formal['fingerprint'].items():
        assert sha(WORKS/path)==expected,path
    runs=list((jobroot/'workspace'/(owner+'-works/build')/number).glob('run-*'))
    assert len(runs)==1
    run=runs[0]
    summary=json.loads((run/'summary.json').read_text(encoding='utf-8'))
    assert summary['stable'] and summary['source_sha256']==summary['source_sha256_after']
    for path,expected in summary['artifact_sha256'].items():
        assert sha(run/path)==expected,path
    testfile=WORKS/(owner+'-works/tests')/('test_'+stem+'.py')
    spec=importlib.util.spec_from_file_location('review_inputs_'+number,testfile)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    inputs=[module.SOURCE,module.DOC,testfile,*module.DEPENDENCIES]
    actual={p.name:sha(p) for p in inputs}
    captured={Path(p).name:value for p,value in summary['source_sha256'].items()}
    assert len(actual)==len(inputs) and actual==captured
    observations=[]

    def native(label,expected,bad_value=False,rbx_delta=0):
        path=run/(label+'.native.output');raw=path.read_bytes()
        assert len(raw)==96*len(expected),label
        mismatches=[]
        for index,(row,want) in enumerate(zip(struct.iter_unpack('<12Q',raw),expected)):
            assert row[1]==row[2],(label,index,'rsp')
            assert row[3]==module.CALLER['rbx'] and row[4]==module.CALLER['rbx']+rbx_delta
            assert row[5:10]==tuple(v for r,v in module.CALLER.items() if r!='rbx')
            assert row[10]==module.CANARY and row[11]==0
            if row[0]!=want:mismatches.append(dict(index=index,expected=want,actual=row[0]))
        assert bool(mismatches)==bad_value,(label,mismatches)
        observations.append(dict(label=label,vectors=len(expected),raw_sha256=sha(path),
                                 all_abi_guards_checked=True,rbx_delta=rbx_delta,rax_mismatches=mismatches))

    if number=='C52':
        functions=[f for group in module.MODULES for f in group]
        expected=[module.interpret(f,module.ARGS[(f['m'],f['i'])]) for f in functions]
        for mode in ('debug','release'):
            native('native-'+mode,expected)
            native('bad-slot-good-'+mode,expected)
            native('bad-slot-'+mode,expected,bad_value=True)
            native('bad-rbx-good-'+mode,expected)
            native('bad-rbx-'+mode,expected,rbx_delta=8)
        required={'bad-return-slot-swapped','bad-no-duplicate-check','bad-early-header-in-out',
                  'bad-early-work-write','bad-rbx-clobbered','bad-no-alias'}
    else:
        def expected_values(vectors):
            return [dict((value,result) for value,block,result in f[2]).get(selector,f[4])
                    for f,selector in vectors]
        fixtures=[(module.MAIN,value) for value in module.VALUES]
        for mode in ('debug','release'):
            native('native-'+mode,expected_values(module.VECTORS))
            for name in ('bad-case-label','bad-arm-result'):
                native(name+'-good-'+mode,expected_values(fixtures))
                native(name+'-'+mode,expected_values(fixtures),bad_value=True)
            native('bad-early-header-good-native-'+mode,expected_values(fixtures))
        required={'bad-case-label','bad-arm-result','bad-early-header'}
    assert required<={r.get('test') for r in summary['records']}
    report=dict(task=owner+':'+number,submission_rev=16,formal_job=job,formal=formal,run=str(run),
                input_sha256=actual,artifact_hashes_checked=len(summary['artifact_sha256']),
                native_observations=observations,test_records=summary['records'],
                source_unchanged_since_formal=True,audit_script_sha256=sha(Path(__file__)),integrated=False)
    report['review_decision']='acceptance_eligible'
    if number=='C52':
        assert 'nested-prechecks-read-no-body-bytes' in {r.get('test') for r in summary['records']}
    output=WORKS/'reviews'/('2026-10-20-'+number+'-formal-final-evidence.json')
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(task=report['task'],checks=formal['checks'],inputs=len(actual),
        artifacts=report['artifact_hashes_checked'],native_rows=sum(r['vectors'] for r in observations),
        decision=report['review_decision'],evidence=str(output)),ensure_ascii=False,indent=2))


if __name__=='__main__':audit(sys.argv[1])
