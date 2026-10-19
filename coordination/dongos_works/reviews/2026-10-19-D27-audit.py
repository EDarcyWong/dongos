"""Independently inspect formal D27 Pair, whole-memory and ABI observations."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

WORKS=Path(__file__).resolve().parents[1]
JOB='5830ef22792f4e57ab60d920f30bb0ec'
MASK=(1<<64)-1


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    jobroot=WORKS/'.local/runs'/JOB
    formal=json.loads((jobroot/'result.json').read_text(encoding='utf-8'))
    assert formal['passed'] and formal['source_stable']
    assert len(formal['checks'])==1
    check=formal['checks'][0]
    assert check['tests']==3 and check['skips']==0 and check['returncode']==0
    assert not check['timed_out'] and not check['cancelled']
    for path,value in formal['fingerprint'].items():assert sha(WORKS/path)==value,path
    runs=list((jobroot/'workspace/deepseek-works/build/D27').glob('run-*'))
    assert len(runs)==1
    run=runs[0];summary=json.loads((run/'summary.json').read_text(encoding='utf-8'))
    assert summary['stable'] and summary['source_sha256']==summary['source_sha256_after']
    for path,value in summary['artifact_sha256'].items():assert sha(run/path)==value,path
    test=WORKS/'deepseek-works/tests/test_nasm_indexed_memory_function.py'
    spec=importlib.util.spec_from_file_location('review_d27_inputs',test)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    files=[module.SOURCE,module.DOC,test,*module.DEPENDENCIES]
    inputs={p.name:sha(p) for p in files}
    assert len(inputs)==len(files)
    assert inputs=={Path(p).name:value for p,value in summary['source_sha256'].items()}
    initial=bytes([0xa5]*32)+bytes((i*73+0x81)&255 for i in range(256))+bytes([0x5a]*32)
    assert initial==module.INITIAL

    def oracle(vector,mutant=None):
        f,length,index,value,null,readonly=vector
        operation,width,signed=f[2:5];memory=bytearray(initial)
        if index>=length and mutant!='bounds':return (0,1),bytes(memory)
        assert not null
        scale=width//8
        if mutant=='scale':scale=8//scale
        at=32+index*scale;n=width//8
        assert 32<=at and at+n<=288
        if operation==0:
            result=int.from_bytes(memory[at:at+n],'little',signed=bool(signed))&MASK
        else:
            result=value&((1<<width)-1);memory[at:at+n]=result.to_bytes(n,'little')
        return (result,0),bytes(memory)

    observations=[]

    def native(label,vectors,mutant=None):
        path=run/(label+'.native.output');raw=path.read_bytes();size=432
        assert len(raw)==size*len(vectors)
        records=[]
        for k,vector in enumerate(vectors):
            protected,=struct.unpack_from('<Q',raw,k*size)
            row=struct.unpack_from('<13Q',raw,k*size+8)
            memory=raw[k*size+112:(k+1)*size]
            assert protected==1
            assert row[2]==row[3] and row[4]==row[5]==module.CALLER['rbx']
            assert row[6:11]==tuple(value for reg,value in module.CALLER.items() if reg!='rbx')
            assert row[11]==module.CANARY and row[12]==0
            assert memory[:32]==initial[:32] and memory[-32:]==initial[-32:]
            want,want_memory=oracle(vector,mutant)
            good,good_memory=oracle(vector)
            assert row[:2]==want,(label,k,'pair',row[:2],want)
            assert memory==want_memory,(label,k,'whole memory')
            pair_wrong=want!=good;memory_wrong=want_memory!=good_memory
            if mutant=='scale':
                assert (pair_wrong,memory_wrong)==((True,False) if vector[0][2]==0 else (False,True))
            elif mutant=='bounds':
                assert pair_wrong and want[1]==0 and good==(0,1)
                assert memory_wrong==(vector[0][2]==1)
            else:assert not pair_wrong and not memory_wrong
            records.append(dict(index=k,actual_pair=list(row[:2]),good_pair=list(good),
                pair_differs_from_good=pair_wrong,memory_differs_from_good=memory_wrong,
                changed_offsets_vs_good=[i for i,(a,b) in enumerate(zip(memory,good_memory)) if a!=b],
                memory_sha256=hashlib.sha256(memory).hexdigest()))
        observations.append(dict(label=label,vectors=len(vectors),mutant=mutant,
            all_abi_and_guards_checked=True,raw_sha256=sha(path),records=records))

    scale=[(module.FUNCTIONS[2],4,3,MASK,False,True),
           (module.FUNCTIONS[9],4,3,0xfedcba9876543281,False,False)]
    gate=[(module.FUNCTIONS[2],2,2,MASK,False,False),
          (module.FUNCTIONS[10],2,2,MASK,False,False)]
    for mode in ('debug','release'):
        native('native-'+mode,module.VECTORS)
        for name,fixtures,mutant in [('bad-scale',scale,'scale'),('bad-bounds-index',gate,'bounds')]:
            for k,v in enumerate(fixtures):
                native(name+'-good-'+mode+'-fixture%d'%k,[v])
                native(name+'-'+mode+'-fixture%d'%k,[v],mutant)
        native('bad-early-header-good-'+mode,[(module.FUNCTIONS[0],4,0,MASK,False,True)])
    required={'bad-scale','bad-bounds-index','bad-early-header'}
    assert required<={r.get('test') for r in summary['records']}
    report=dict(task='deepseek:D27',submission_rev=3,formal_job=JOB,formal=formal,run=str(run),
        input_sha256=inputs,artifact_hashes_checked=len(summary['artifact_sha256']),
        native_observations=observations,test_records=summary['records'],source_unchanged_since_formal=True,
        audit_script_sha256=sha(Path(__file__)),integrated=False,review_decision='acceptance_eligible')
    output=WORKS/'reviews/2026-10-19-D27-evidence.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(task=report['task'],checks=formal['checks'],inputs=len(inputs),
        artifacts=report['artifact_hashes_checked'],native_rows=sum(r['vectors'] for r in observations),
        decision=report['review_decision'],evidence=str(output)),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
