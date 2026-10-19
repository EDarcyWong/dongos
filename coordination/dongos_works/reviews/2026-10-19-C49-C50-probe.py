"""Independent, bounded register-observer checks; no submitted files are changed."""
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import uuid

WORKS=Path(__file__).resolve().parents[1]
NUMBER=sys.argv[1]
assert NUMBER in ('C49','C50')
stem='nasm_u64_select_function' if NUMBER=='C49' else 'nasm_u64_forward_function'
job={'C49':'922a95d14f8247fd8616080fb93ff321','C50':'5f149631ee114d7ba816b16610f4d902'}[NUMBER]
spec=importlib.util.spec_from_file_location('under_review',WORKS/('claude-works/tests/test_'+stem+'.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
T=m.NasmU64SelectFunctionTests if NUMBER=='C49' else m.NasmU64ForwardFunctionTests
T.work=WORKS/'claude-works/build'/NUMBER/('independent-'+uuid.uuid4().hex[:12]);T.work.mkdir(parents=True)
T.nasm,T.cc=m.tool('nasm','NASM'),m.tool('gcc','CC');T.native='win64' if os.name=='nt' else 'elf64'
(T.work/'probe.c').write_text(m.HARNESS,encoding='utf-8')
before=T.digests();t=T()
formalroot=WORKS/'.local/runs'/job/'workspace/claude-works/build'/NUMBER
formalruns=list(formalroot.glob('run-*'))
assert len(formalruns)==1,formalruns
official=formalruns[0]
source=m.SOURCE.read_text(encoding='utf-8')
needle='!=ex.OK{return INVALID;}\n at+=n;'
assert source.count(needle)==(2 if NUMBER=='C49' else 1)
mutated=source.replace(needle,'!=ex.OK{return INVALID;}\n at+=n-4;put(text,&at,"add rbx, 8\\nret\\n");')
bad_exes=T.build_all('bad-rbx-plus8',mutated)

def safe_native(text,v,label):
    regs=['rax','rsp','rbx','rbp','r12','r13','r14','r15']
    externs=[] if NUMBER=='C49' else ['extern callee_target','extern callee_align','extern callee_id','extern callee_arity']
    a=['bits 64',*externs,'section .bss','align 8','anchor: resq 1','pointer: resq 1','image: resq 8',
       'section .text','global v0','v0:','push rbx','push rbp','push r12','push r13','push r14','push r15',
       'sub rsp, 8','mov [rel anchor], rsp','mov [rel pointer], rdi','mov rbx, rdi']
    a+=['mov %s, 0x%x'%(r,x) for r,x in m.CALLER.items()]
    args=v[5:9] if NUMBER=='C49' else v[6]
    a+=['mov %s, 0x%x'%(r,x) for r,x in zip(['rdi','rsi','rdx','rcx','r8','r9'],args)]
    a+=['mov rax, 0x%x'%m.CANARY,'mov [rsp], rax','call '+m.symbol(*v[:2])]
    a+=['mov [rel image+%d], %s'%(i*8,r) for i,r in enumerate(regs)]
    a+=['mov rsp, [rel anchor]','mov r11, [rel pointer]']
    for target,index in [(m.RAX,0),(m.RSP_AFTER,1),(m.RBX_AFTER,2),(m.RBP_AFTER,3),*[(m.R12_AFTER+j,4+j)for j in range(4)]]:
        a+=['mov rax, [rel image+%d]'%(index*8),'mov [r11+%d], rax'%(target*8)]
    a+=['mov [r11+%d], r11'%(m.RBX_BEFORE*8),'mov [r11+%d], rsp'%(m.RSP_BEFORE*8),
        'mov rax, [rsp]','mov [r11+%d], rax'%(m.CANARY_AFTER*8),
        'add rsp, 8','pop r15','pop r14','pop r13','pop r12','pop rbp','pop rbx','ret']
    if NUMBER=='C50':
        a+=[m.symbol(*v[2:4])+':','mov r11, rsp','and r11, 15','mov [rel callee_align], r11',
            'mov qword [rel callee_id], 0','mov qword [rel callee_arity], %d'%len(v[5]),'jmp callee_target']
    a+=text.decode('ascii').splitlines()
    asm=T.work/(label+'.asm');asm.write_text('\n'.join(a)+'\n',encoding='ascii')
    for fmt in ('elf64','win64'):
        T.command([T.nasm,'-f',fmt,*m.nasm_flags(T.nasm),'-o',T.work/(label+'.'+fmt+'.o'),asm],label+'-'+fmt)
    c=T.work/(label+'.c')
    c.write_text(m.NATIVE_MAIN.replace('%DECLS%','#define STATE %d\nextern void ABI v0(uint64_t*);'%m.STATE).replace('%TABLE%','v0'),encoding='utf-8')
    extra=[]
    if NUMBER=='C50':
        callee=T.work/'callee.c';callee.write_text(m.CALLEE,encoding='utf-8');extra=[callee]
    exe=T.work/(label+('.exe'if os.name=='nt'else''))
    T.command([T.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',c,*extra,T.work/(label+'.'+T.native+'.o'),'-o',exe],label+'-link')
    r=subprocess.run([str(exe)],capture_output=True,timeout=30)
    (T.work/(label+'.output')).write_bytes(r.stdout)
    assert r.returncode==0,(label,r.returncode,r.stderr)
    assert len(r.stdout)==8*(m.STATE+(10 if NUMBER=='C50' else 0))
    got=struct.unpack('<%dQ'%(len(r.stdout)//8),r.stdout)
    want=(v[7]if m.holds(v[2],v[5],v[6])else v[8])if NUMBER=='C49' else m.callee_hash([v[6][i]for i in v[5]])
    assert got[m.RAX]==want
    assert got[m.RSP_BEFORE]==got[m.RSP_AFTER] and got[m.CANARY_AFTER]==m.CANARY
    assert (got[m.RBP_AFTER],*got[m.R12_AFTER:m.R12_AFTER+4])==tuple(m.CALLER.values())
    if NUMBER=='C50':
        assert got[m.STATE:m.STATE+4]==(1,0,8,len(v[5]))
        assert list(got[m.STATE+4:m.STATE+4+len(v[5])])==[v[6][i]for i in v[5]]
    return dict(returncode=r.returncode,rax=got[m.RAX],rbx_before=got[m.RBX_BEFORE],rbx_after=got[m.RBX_AFTER],
                rbx_delta=got[m.RBX_AFTER]-got[m.RBX_BEFORE],rsp_balanced=True,host_returned=True)

records=[]
vectors=m.VECTORS[:2] if NUMBER=='C49' else [m.VECTORS[5]]
for mode,bad_exe in bad_exes.items():
    good_exe=official/('good-'+mode+('.exe'if os.name=='nt'else''))
    for index,v in enumerate(vectors):
        tag=mode+'-'+str(index)
        goodtext=t.generate(good_exe,[v],'good-'+tag)[0]
        t.native_run([goodtext],[v],'original-good-'+tag)
        good=safe_native(goodtext,v,'safe-good-'+tag);assert good['rbx_delta']==0
        case=(*v[:5],1024,0,0,m.OK)if NUMBER=='C49' else t.case(v[:4],v[5],v[4],4096,m.OK)
        badtext=t.emit(bad_exe,[case],'bad-'+tag)[0]
        try:
            t.native_run([badtext],[v],'original-bad-'+tag)
            raise RuntimeError('bad RBX unexpectedly accepted')
        except AssertionError as e:
            failure=str(e);assert 'caller rsp aligned before call'in failure,failure
        bad=safe_native(badtext,v,'safe-bad-'+tag);assert bad['rbx_delta']==8
        records.append(dict(mode=mode,vector_index=index,good=good,original_failure=failure,safe_bad=bad))
after=T.digests();assert before==after
report=dict(task='claude:'+NUMBER,formal_job=job,official=str(official),inputs=before,stable=True,records=records)
(T.work/'review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(work=str(T.work),stable=True,records=records),indent=2),flush=True)
