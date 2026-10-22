"""Independent review probes; never edits the submitted implementation."""
from pathlib import Path
import hashlib
import json
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
CODE = ROOT / 'code'
WORKS = ROOT / 'coordination/dongos_works'
sys.path.insert(0, str(CODE))
from lang.dongc import compile_source
from lang.dongc.model import CompileError
from lang.tests import test_bootstrap_semantic_types as decl
from lang.tests import test_bootstrap_semantic_runtime as runtime
from lang.tests.test_dongc import tool

CACHE = (Path(sys.argv[1]) if len(sys.argv) > 1 else
         WORKS / 'pool-works/build/L3METHOD1/run-e8a06e62008e')
OUT = WORKS / 'codex-works/build/L3METHOD1-review'
OUT.mkdir(parents=True, exist_ok=True)
candidate = WORKS / 'pool-works/l3-method/src/bootstrap'
for name in ('semantic_types.dg', 'binding.dg'):
    assert (candidate / name).read_bytes() == (CACHE / 'source/bootstrap' / name).read_bytes(), name

# Link a read-only observation harness to the existing exact-candidate object.
# The production object is unchanged; added diagnostics go to stderr only.
marker = ' wr(&code,8);wr(out,64);wr(&good,8);'
diagnostics = r'''
 if(!code){for(uint64_t j=0;j<un;j++){for(uint64_t k=0;k<u[j].nc;k++){
  uint64_t g=u[j].ns+k;const Node*call=n+g;if(call->data[0]!=10)continue;
  uint64_t cg=u[j].ns+call->data[3];const uint64_t*ci=(uint64_t*)flow.pools[0].p+3*cg;
  const uint64_t*ri=(uint64_t*)flow.pools[0].p+3*g;
  fprintf(stderr,"CALL unit=%llu node=%llu ref=%llu target=%llu callee_type=%llu result_type=%llu\n",
   (unsigned long long)j,(unsigned long long)k,(unsigned long long)refs[cg].kind,
   (unsigned long long)refs[cg].target,(unsigned long long)ci[0],(unsigned long long)ri[0]);
 }}}
'''
assert runtime.HARNESS.count(marker) == 1
harness = OUT / 'probe.c'
harness.write_text(runtime.HARNESS.replace(marker, diagnostics + marker), encoding='utf-8')

PREFIX = 'module a;struct S{x:u64}'
METHOD = 'fn(self:*S)get(x:u64)u64{return x;}'
cases = [
    ('free-function-baseline', 'module a;fn get(x:u64)u64{return x;}fn f()u64{return get(1);}', 0),
    ('receiver-info', PREFIX+METHOD+'fn f(p:*S)u64{return p.get(1);}', 0),
    ('functional-info', PREFIX+METHOD+'fn f(p:*S)u64{return get(p,1);}', 0),
    ('receiver-missing-arg', PREFIX+METHOD+'fn f(p:*S)u64{return p.get();}', 3),
    ('receiver-extra-arg', PREFIX+METHOD+'fn f(p:*S)u64{return p.get(1,2);}', 3),
    ('functional-missing-receiver', PREFIX+METHOD+'fn f()u64{return get();}', 3),
    ('functional-missing-arg', PREFIX+METHOD+'fn f(p:*S)u64{return get(p);}', 3),
    ('functional-extra-arg', PREFIX+METHOD+'fn f(p:*S)u64{return get(p,1,2);}', 3),
    ('receiver-wrong-arg-type', PREFIX+METHOD+'fn f(p:*S)u64{return p.get(true);}', 3),
    ('functional-wrong-arg-type', PREFIX+METHOD+'fn f(p:*S)u64{return get(p,true);}', 3),
    ('wrong-return-type', PREFIX+METHOD+'fn f(p:*S)bool{return p.get(1);}', 3),
    ('wrong-method-body-return', PREFIX+'fn(self:*S)get()u64{return true;}', 3),
    ('same-name-different-receiver', PREFIX+'struct T{x:u64}'+METHOD+
     'fn(self:*T)get(x:bool)bool{return x;}fn f(p:*S,q:*T)bool{return get(q,true)&&get(p,1)==1;}', 0),
    ('pointer-result', PREFIX+'fn(self:*S)get()*S{return self;}fn f(p:*S)*S{return p.get();}', 0),
    ('slice-arg-result', PREFIX+'fn(self:*S)get(x:[]u64)[]u64{return x;}fn f(p:*S,x:[]u64)[]u64{return p.get(x);}', 0),
    ('function-shadow', PREFIX+'fn get(x:bool)bool{return x;}'+METHOD+'fn f()bool{return get(true);}', 0),
]

def payload(source):
    c, _, _ = decl.case(source)
    out = bytearray(struct.pack('<Q', 1))
    out.extend(struct.pack('<14Q', c['roots'], c['entry'], len(c['files']),
                           *[c[k] for k in ('units','tokens','strings','nodes','edges','states','depth')],
                           c['semantic_depth'], c['pool'], c['cap'], 0))
    for root, path, data in c['files']:
        out.extend(struct.pack('<3Q', root, len(path), len(data)))
        out.extend(path); out.extend(data)
    return out

records = []
for mode in ('debug', 'release'):
    exe = OUT / (mode + '.exe')
    command = [tool('gcc','CC'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
               str(harness), str(CACHE / (mode+'.o')), '-o', str(exe)]
    subprocess.run(command, check=True, capture_output=True)
    for name, source, expected in cases:
        try:
            compile_source(source); seed_ok = True
        except CompileError:
            seed_ok = False
        run = subprocess.run([str(exe)], input=payload(source), capture_output=True, timeout=120)
        row = dict(mode=mode,name=name,source=source,seed_ok=seed_ok,expected_status=expected,
                   process_exit=run.returncode,diagnostics=run.stderr.decode(errors='replace'))
        if run.returncode == 0:
            returned,status,nt,nf,nl,unchecked,u,t,detail,good=struct.unpack_from('<10Q',run.stdout)
            row.update(status=status,guards=good,published_types=nt,published_fields=nf)
            assert returned==status and good==1, row
            assert status==expected and seed_ok==(expected==0), row
        else:
            raise AssertionError(row)
        observed = [int(v) for v in re.findall(r'callee_type=(\d+)', row['diagnostics'])]
        row['callee_info_complete'] = all(v != decl.NONE for v in observed)
        records.append(row)
missing = [dict(mode=r['mode'], name=r['name']) for r in records if not r['callee_info_complete']]
summary = dict(native_artifact_root=str(CACHE),
               native_object_sha256={m:hashlib.sha256((CACHE/(m+'.o')).read_bytes()).hexdigest()
                                     for m in ('debug','release')},
               candidate_sha256={n:hashlib.sha256((candidate/n).read_bytes()).hexdigest()
                                for n in ('semantic_types.dg','binding.dg')},
               acceptance_checks_passed=len(records), graph_oracle_passed=not missing,
               missing_callee_info=missing, records=records)
(OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
for row in records:
    print(row['mode'],row['name'],'seed='+str(row['seed_ok']),'status='+str(row.get('status')),
          row['diagnostics'].strip())
if missing:
    print('GRAPH ORACLE FAILED:', len(missing), 'records have no selected callee type')
    raise SystemExit(1)
