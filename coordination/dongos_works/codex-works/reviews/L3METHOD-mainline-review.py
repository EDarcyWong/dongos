"""Independent review probes; never edits the submitted implementation."""
from pathlib import Path
import hashlib
import json
import os
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

CACHE = Path(sys.argv[1])
BAD_CACHE = WORKS / '.local/runs/1158f00b230f4c3b96ce0c0daadf9d14/workspace/pool-works/build/L3METHOD1/run-17e3f3b90d27'
OUT = WORKS / 'codex-works/build/L3METHOD-mainline-review'
OUT.mkdir(parents=True, exist_ok=True)
candidate = WORKS / 'pool-works/l3-method/src/bootstrap'
for name in ('semantic_types.dg', 'binding.dg'):
    assert (candidate / name).read_bytes() == (CACHE / 'source/bootstrap' / name).read_bytes(), name

# Link a read-only observation harness to the existing exact-candidate object.
# The production object is unchanged; added diagnostics go to stderr only.
marker = ' wr(&code,8);wr(out,64);wr(&good,8);'
helpers = r'''
static int review_same_type(const Workspace*w,uint64_t count,uint64_t a,uint64_t b,unsigned depth){
 if(a==b)return 1;
 if(a>=count||b>=count||depth>=32)return 0;
 SType x=((SType*)w->pools[0].p)[a],y=((SType*)w->pools[0].p)[b];
 if(x.kind!=y.kind||x.flags!=y.flags)return 0;
 if(x.kind==12||x.kind==13||x.kind==14||x.kind==15)return review_same_type(w,count,x.element,y.element,depth+1);
 if(x.kind==16)return x.count==y.count&&review_same_type(w,count,x.element,y.element,depth+1);
 if(x.kind>=17)return x.unit==y.unit&&x.node==y.node;
 return 1;
}
'''
diagnostics = r'''
 #define REVIEW_CHECK(pred,label) do{if(!(pred)){fprintf(stderr,"GRAPH_ORACLE_FAIL %s unit=%llu call=%llu\n",label,(unsigned long long)j,(unsigned long long)k);exit(103);}}while(0)
 if(!code){for(uint64_t j=0;j<un;j++){for(uint64_t k=0;k<u[j].nc;k++){
  uint64_t g=u[j].ns+k;const Node*call=n+g;if(call->data[0]!=10)continue;
  uint64_t cg=u[j].ns+call->data[3];const uint64_t*ci=(uint64_t*)flow.pools[0].p+3*cg;
  const uint64_t*ri=(uint64_t*)flow.pools[0].p+3*g;
  uint64_t ct=ci[0];REVIEW_CHECK(ct<out->types,"callee-type-missing-or-out-of-range");
  SType ft=((SType*)w.pools[0].p)[ct];REVIEW_CHECK(ft.kind==19,"callee-not-FUNCTION");
  REVIEW_CHECK(ft.unit<un&&ft.node<u[ft.unit].nc,"declaration-out-of-range");
  REVIEW_CHECK(n[u[ft.unit].ns+ft.node].data[0]==100,"declaration-not-function-node");
  REVIEW_CHECK(((uint64_t*)w.pools[2].p)[u[ft.unit].ns+ft.node]==ct,"declaration-type-mismatch");
  uint64_t selected=UINT64_MAX;for(uint64_t z=0;z<nr.count;z++)if(sy[z].unit==ft.unit&&sy[z].decl==ft.node){selected=z;break;}
  REVIEW_CHECK(selected<nr.count,"selected-symbol-missing");
  Token call_name=t[u[j].ts+n[cg].data[1]],decl_name=t[u[ft.unit].ts+sy[selected].name];
  uint64_t name_length=call_name.data[2]-call_name.data[1];
  REVIEW_CHECK(name_length==decl_name.data[2]-decl_name.data[1]&&
   !memcmp(s[u[j].source].bytes.p+u[j].skip+call_name.data[1],s[u[ft.unit].source].bytes.p+u[ft.unit].skip+decl_name.data[1],name_length),"selected-method-name-mismatch");
  REVIEW_CHECK(review_same_type(&w,out->types,ft.element,ri[0],0),"call-return-info-mismatch");
  REVIEW_CHECK((ci[1]&3)==0,"callee-is-place-or-writable");
  uint64_t arg=call->data[4],parameter=0;
  if(refs[cg].kind==5||refs[cg].kind==7){
   REVIEW_CHECK(sy[selected].kind==9&&ft.length>0,"selected-symbol-not-method");
   uint64_t recv=arg;if(refs[cg].kind==5){recv=n[cg].data[3];parameter=1;}
   REVIEW_CHECK(recv<u[j].nc,"receiver-out-of-range");
   uint64_t recv_type=((uint64_t*)flow.pools[0].p)[3*(u[j].ns+recv)];
   uint64_t parameter_type=((SField*)w.pools[1].p)[ft.first].typ;
   REVIEW_CHECK(review_same_type(&w,out->types,recv_type,parameter_type,0),"selected-method-receiver-mismatch");
  }else{
   REVIEW_CHECK(refs[cg].kind==2&&refs[cg].target==selected&&sy[selected].kind==2,"free-function-target-mismatch");
  }
  uint64_t steps=0;while(arg!=UINT64_MAX){
   REVIEW_CHECK(arg<u[j].nc&&steps++<u[j].nc&&parameter<ft.length,"argument-chain-or-arity");
   uint64_t actual=((uint64_t*)flow.pools[0].p)[3*(u[j].ns+arg)];
   REVIEW_CHECK(review_same_type(&w,out->types,actual,((SField*)w.pools[1].p)[ft.first+parameter].typ,0),"argument-type-info-mismatch");
   parameter++;arg=n[u[j].ns+arg].data[6];
  }
  REVIEW_CHECK(parameter==ft.length,"argument-count-info-mismatch");
  fprintf(stderr,"CALL unit=%llu node=%llu ref=%llu target=%llu callee_type=%llu result_type=%llu selected_unit=%llu selected_node=%llu selected_kind=%llu\n",
   (unsigned long long)j,(unsigned long long)k,(unsigned long long)refs[cg].kind,
   (unsigned long long)refs[cg].target,(unsigned long long)ci[0],(unsigned long long)ri[0],
   (unsigned long long)ft.unit,(unsigned long long)ft.node,(unsigned long long)sy[selected].kind);
 }}}
 #undef REVIEW_CHECK
'''
assert runtime.HARNESS.count(marker) == 1
harness = OUT / 'probe.c'
text = runtime.HARNESS.replace('static void semantic(',helpers+'\nstatic void semantic(',1)
harness.write_text(text.replace(marker, diagnostics + marker), encoding='utf-8')

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
    ('same-name-receiver', PREFIX+'struct T{x:u64}'+METHOD+
     'fn(self:*T)get(x:bool)bool{return x;}fn f(p:*S,q:*T)bool{return q.get(true)&&p.get(1)==1;}', 0),
    ('const-receiver', PREFIX+'fn(self:*const S)get()u64{return 1;}fn f(p:*const S)u64{return p.get();}', 0),
    ('alias-receiver', PREFIX+'type Alias=S;fn(self:*Alias)get()u64{return 1;}fn f(p:*S)u64{return get(p);}', 0),
    ('unsafe-boundary', PREFIX+'unsafe fn(self:*S)get()void{}fn f(p:*S)void{unsafe{p.get();}}', 0),
    ('cross-module-overload', [(0,'a.dg','module a;import b as d;fn f(p:*d.T)bool{return d.get(p,true)&&p.get(true);}'),
     (0,'b.dg','module b;pub struct S{x:u64}pub struct T{x:u64}fn(self:*S)get(x:u64)u64{return x;}pub fn(self:*T)get(x:bool)bool{return x;}')], 0),
]

def payload(source, **limits):
    c, _, _ = decl.case('', files=source, **limits) if isinstance(source,list) else decl.case(source, **limits)
    out = bytearray(struct.pack('<Q', 1))
    out.extend(struct.pack('<14Q', c['roots'], c['entry'], len(c['files']),
                           *[c[k] for k in ('units','tokens','strings','nodes','edges','states','depth')],
                           c['semantic_depth'], c['pool'], c['cap'], 0))
    for root, path, data in c['files']:
        out.extend(struct.pack('<3Q', root, len(path), len(data)))
        out.extend(path); out.extend(data)
    return out

records = []
negative_controls = []
for mode in ('debug', 'release'):
    exe = OUT / (mode + '.exe')
    command = [tool('gcc','CC'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', *([] if os.name=='nt' else ['-no-pie']),
               str(harness), str(CACHE / (mode+'.o')), '-o', str(exe)]
    subprocess.run(command, check=True, capture_output=True)
    for name, source, expected in cases:
        try:
            if isinstance(source,list):
                host=OUT/('seed-'+mode+'-'+name);host.mkdir(exist_ok=True)
                for _,path,text in source:(host/path).write_text(text,encoding='utf-8')
                decl.compile_file(host/'a.dg',roots=[host])
            else:
                compile_source(source)
            seed_ok = True
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
            assert struct.unpack_from('<Q',run.stdout,len(run.stdout)-8)==(1,), row
        else:
            raise AssertionError(row)
        observed = [int(v) for v in re.findall(r'callee_type=(\d+)', row['diagnostics'])]
        if expected==0:assert len(observed)==(2 if 'same-name' in name or name=='cross-module-overload' else 1), row
        row['callee_info_complete'] = all(v != decl.NONE for v in observed)
        records.append(row)
    boundary_source=PREFIX+METHOD+'fn f(p:*S)u64{return get(p,1);}'
    for pool in range(24,29):
        run=subprocess.run([str(exe)],input=payload(boundary_source,pool=pool,cap=decl.NONE,semantic_depth=32),capture_output=True,timeout=120)
        assert run.returncode==0,(pool,run.stderr)
        values=struct.unpack_from('<10Q',run.stdout)
        assert values[0]==values[1]==2 and values[2:5]==(0,0,0) and values[-1]==1,(pool,values)
        assert struct.unpack_from('<Q',run.stdout,len(run.stdout)-8)==(1,)
        records.append(dict(mode=mode,name='one-short-'+str(pool),status=2,guards=1,callee_info_complete=True))
    bad_exe=OUT/(mode+'-R0-negative.exe')
    bad_command=[*command]
    bad_command[bad_command.index(str(CACHE/(mode+'.o')))]=str(BAD_CACHE/(mode+'.o'))
    bad_command[-1]=str(bad_exe)
    subprocess.run(bad_command,check=True,capture_output=True)
    bad=subprocess.run([str(bad_exe)],input=payload(PREFIX+METHOD+'fn f(p:*S)u64{return p.get(1);}'),capture_output=True,timeout=120)
    assert bad.returncode==103 and b'callee-type-missing-or-out-of-range' in bad.stderr,(mode,bad.returncode,bad.stderr)
    negative_controls.append(dict(mode=mode,real_R0_object=str(BAD_CACHE/(mode+'.o')),returncode=bad.returncode,diagnostics=bad.stderr.decode()))
missing = [dict(mode=r['mode'], name=r['name']) for r in records if not r['callee_info_complete']]
summary = dict(native_artifact_root=str(CACHE),
               native_object_sha256={m:hashlib.sha256((CACHE/(m+'.o')).read_bytes()).hexdigest()
                                     for m in ('debug','release')},
               candidate_sha256={n:hashlib.sha256((candidate/n).read_bytes()).hexdigest()
                                for n in ('semantic_types.dg','binding.dg')},
               checks_passed=len(records), graph_oracle_passed=not missing,negative_controls=negative_controls,
               missing_callee_info=missing, records=records)
(OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
for row in records:
    print(row['mode'],row['name'],'status='+str(row.get('status')),row.get('diagnostics','').strip())
print('real R0 negative controls rejected:',len(negative_controls))
if missing:
    print('GRAPH ORACLE FAILED:', len(missing), 'records have no selected callee type')
    raise SystemExit(1)
