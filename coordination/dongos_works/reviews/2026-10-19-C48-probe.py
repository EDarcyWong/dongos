"""Read-only C48 review probe; all mutations are compiled in a review scratch tree."""
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import uuid

WORKS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('c48_under_review', WORKS/'claude-works/tests/test_nasm_u64_function.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
T = m.NasmU64FunctionTests
T.work = WORKS/'claude-works/build/C48'/('independent-'+uuid.uuid4().hex[:12])
T.work.mkdir(parents=True)
T.nasm, T.cc = m.tool('nasm', 'NASM'), m.tool('gcc', 'CC')
T.native = 'win64' if os.name == 'nt' else 'elf64'
(T.work/'probe.c').write_text(m.HARNESS, encoding='utf-8')
before = T.digests()
t = T()
official = WORKS/'.local/runs/4f30cf261b3e4a86afadf7bd8c725aa5/workspace/claude-works/build/C48/run-386485f82b43'
source = m.SOURCE.read_text(encoding='utf-8')
old = 'if ex.emit(U64_KIND,frame,0,8*(return_slot+1),0,slice_from_raw_parts(&buffer[0],CHUNK),&n)!=ex.OK{return false;}\n  at=n;'
assert source.count(old) == 1
# Only the generated function's RBX changes. RSP and the return address are intact;
# RBX+8 is still within the original bridge's 14-qword io allocation.
bad = source.replace(old, old[:-len('at=n;')]+'at=n-4;put(buffer,&at,"add rbx, 8\\nret\\n");', 1)
mutants = T.build_all('bad-rbx-plus8', bad)
v = m.VECTORS[0]

def safe_native(text, label):
    # RIP-relative snapshots capture every observed register before trusting any
    # callee-saved register or the returned RSP. The saved entry anchor restores
    # the host stack before the normal pops/return.
    regs = ['rax', 'rsp', 'rbx', 'rbp', 'r12', 'r13', 'r14', 'r15']
    a = ['bits 64', 'section .bss', 'align 8', 'anchor: resq 1', 'pointer: resq 1', 'image: resq 8',
         'section .text', 'global v0', 'v0:', 'push rbx', 'push rbp', 'push r12', 'push r13', 'push r14', 'push r15',
         'sub rsp, 8', 'mov [rel anchor], rsp', 'mov [rel pointer], rdi', 'mov rbx, rdi']
    a += ['mov %s, 0x%x' % (r, x) for r, x in m.CALLER.items()]
    a += ['mov rax, 0x%x' % m.CANARY, 'mov [rsp], rax', 'call '+m.symbol(*v[:2])]
    a += ['mov [rel image+%d], %s' % (i*8, r) for i, r in enumerate(regs)]
    a += ['mov rsp, [rel anchor]', 'mov r11, [rel pointer]']
    for target, index in [(m.RAX, 0), (m.RSP_AFTER, 1), (m.RBX_AFTER, 2), (m.RBP_AFTER, 3),
                          *[(m.R12_AFTER+j, 4+j) for j in range(4)]]:
        a += ['mov rax, [rel image+%d]' % (index*8), 'mov [r11+%d], rax' % (target*8)]
    a += ['mov [r11+%d], r11' % (m.RBX_BEFORE*8), 'mov [r11+%d], rsp' % (m.RSP_BEFORE*8),
          'mov rax, [rsp]', 'mov [r11+%d], rax' % (m.CANARY_AFTER*8),
          'add rsp, 8', 'pop r15', 'pop r14', 'pop r13', 'pop r12', 'pop rbp', 'pop rbx', 'ret']
    a += text.decode('ascii').splitlines()
    asm = T.work/(label+'.asm')
    asm.write_text('\n'.join(a)+'\n', encoding='ascii')
    obj, exe = T.work/(label+'.o'), T.work/(label+'.exe' if os.name == 'nt' else label)
    T.command([T.nasm, '-f', T.native, *m.nasm_flags(T.nasm), '-o', obj, asm], label+'-assemble')
    main = m.NATIVE_MAIN.replace('%DECLS%', '#define STATE %d\nextern void ABI v0(uint64_t*);' % m.STATE).replace('%TABLE%', 'v0')
    c = T.work/(label+'.c'); c.write_text(main, encoding='utf-8')
    T.command([T.cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', c, obj, '-o', exe], label+'-link')
    r = subprocess.run([str(exe)], capture_output=True, timeout=30)
    assert r.returncode == 0, (label, r.returncode, r.stderr)
    assert len(r.stdout) == 8*m.STATE
    got = struct.unpack('<%dQ' % m.STATE, r.stdout)
    assert got[m.RAX] == m.interpret(*v[2:])
    assert got[m.RSP_BEFORE] == got[m.RSP_AFTER]
    assert got[m.CANARY_AFTER] == m.CANARY
    assert (got[m.RBP_AFTER], *got[m.R12_AFTER:m.R12_AFTER+4]) == tuple(m.CALLER.values())
    return dict(returncode=r.returncode, rax=got[m.RAX], rbx_before=got[m.RBX_BEFORE], rbx_after=got[m.RBX_AFTER],
                rbx_delta=got[m.RBX_AFTER]-got[m.RBX_BEFORE], rsp_restored=True, host_returned=True)

records = []
for mode, bad_exe in mutants.items():
    good_exe = official/('good-'+mode+('.exe' if os.name == 'nt' else ''))
    good_text = t.generate(good_exe, [v], 'good-'+mode)[0]
    t.native_run([good_text], [v], 'original-good-'+mode)
    good = safe_native(good_text, 'safe-good-'+mode)
    assert good['rbx_delta'] == 0
    bad_text = t.emit(bad_exe, [t.case(*v[:6],16384,m.OK)], 'bad-'+mode)[0]
    try:
        t.native_run([bad_text], [v], 'original-bad-'+mode)
        raise RuntimeError('bad RBX unexpectedly accepted')
    except AssertionError as e:
        original_failure = str(e)
        assert 'caller rsp aligned before call' in original_failure, original_failure
    observed = safe_native(bad_text, 'safe-bad-'+mode)
    assert observed['rbx_delta'] == 8
    records.append(dict(mode=mode, good=good, original_failure=original_failure, safe_bad=observed))
after = T.digests()
assert before == after
report = dict(task='claude:C48', formal_job='4f30cf261b3e4a86afadf7bd8c725aa5', inputs=before, stable=True, records=records,
              observation='original observer relies on returned RBX; safe RIP observer captures numeric RBX+8 while original misreports pre-call alignment due to shifted writes')
(T.work/'review.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps(dict(work=str(T.work), stable=True, records=records), indent=2))
