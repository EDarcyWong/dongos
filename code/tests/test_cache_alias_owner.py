"""Real Dong cache migration with independent C page-table/retirement oracle."""
import hashlib,json,os,re,shutil,subprocess,unittest,uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent
OPTIONS=[HERE.parent,HERE.parents[3]/'code',HERE.parents[1],Path.cwd()]
ROOTS={p.resolve() for p in OPTIONS if (p/'kernel/mm/paging.dg').is_file() and (p/'lang/dongc').is_dir()}
if len(ROOTS)!=1:raise RuntimeError('require one actual code root in normal or isolated workspace')
ROOT=ROOTS.pop()
CANDIDATE=HERE.parent/'src' if (HERE.parent/'src/mm/cache_alias_owner.dg').is_file() else ROOT/'kernel'
DOC=CANDIDATE/'mm/cache_alias_owner.md' if (CANDIDATE/'mm/cache_alias_owner.md').is_file() else ROOT/'docs/cache-alias-owner.md'
DELIVERY=HERE.parent/'deliveries/P2WC1.md'
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ABI=r'''
section .bss
align 8
wc_saved_sp: resq 1
wc_saved_capture: resq 1
section .text
align 16
global wc_checked_execute
wc_checked_execute:
 push rbx
 push rbp
 push r12
 push r13
 push r14
 push r15
 sub rsp,8
 mov [rel wc_saved_sp],rsp
 mov [rel wc_saved_capture],rsi
 mov [rsi+56],rsp
 mov rbx,0x1122334400000000
 mov rbp,0x1122334400000001
 mov r12,0x1122334400000002
 mov r13,0x1122334400000003
 mov r14,0x1122334400000004
 mov r15,0x1122334400000005
 call wc_execute
 mov r10,[rel wc_saved_capture]
 mov [r10],rax
 mov [r10+8],rbx
 mov [r10+16],rbp
 mov [r10+24],r12
 mov [r10+32],r13
 mov [r10+40],r14
 mov [r10+48],r15
 mov [r10+64],rsp
 mov rsp,[rel wc_saved_sp]
 add rsp,8
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbp
 pop rbx
 ret
'''
def closure():
    paths={'cache_alias_owner_probe.dg':HERE/'cache_alias_owner_probe.dg'};pending=list(paths.values())
    while pending:
        source=pending.pop()
        for module in re.findall(r'(?m)^\s*import\s+([\w.]+)',source.read_text(encoding='utf-8')):
            rel=module.replace('.','/')+'.dg'
            if rel in paths:continue
            bases=(CANDIDATE,) if module=='mm.cache_alias_owner' else (ROOT/'kernel',ROOT/'lang/std')
            found=[base/rel for base in bases if (base/rel).is_file()]
            if len(found)!=1:raise AssertionError((module,found))
            paths[rel]=found[0];pending.append(found[0])
    return paths
class CacheAliasOwnerTests(unittest.TestCase):
    def test_real_transactions_failures_and_wrong_dong_both_modes(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc,'native tools required; no skip')
        sources=closure();inputs=sorted(set(sources.values())|{Path(__file__),HERE/'cache_alias_owner_probe.c',DOC})
        if DELIVERY.is_file():inputs.append(DELIVERY)
        hashes=lambda:{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs};before=hashes()
        state=HERE.parent/'build/P2WC1'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
        (state/'source-before.json').write_text(json.dumps(before,indent=2)+'\n')
        original=(CANDIDATE/'mm/cache_alias_owner.dg').read_text(encoding='utf-8')
        bad={
          'skip-cache':('let status=invoke(context,CACHE_MAINT,(*context).old_kind);','let status=OK;','normal','cache-before-PAT'),
          'keep-old-alias':('match pg.map_live(c.space,va,pa,pg.WRITE|pg.WRITE_COMBINING)', 'var flags=pg.WRITE|pg.WRITE_COMBINING;if a==c.aliases.len-1&&page==0{flags=pg.WRITE;if c.aliases[a].current_cache_type==plan.UC{flags=pg.WRITE|pg.UNCACHED;}}match pg.map_live(c.space,va,pa,flags)', 'normal','old-alias-survived-remap'),
          'early-ready':('let status=invoke(context,phase,0);','if barriers!=0{(*context).complete=1;}let status=invoke(context,phase,0);','normal','ready-before-second'),
          'noack-continue':('let status=invoke(context,phase,0);if status!=OK{return poison(context,status);}','let status=invoke(context,phase,0);if status!=OK{(*context).last_error=status;}','noack','reclaim-without-first-ACK'),
        }
        results=[]
        for mode in ('debug','release'):
            for mutation in (None,*bad):
                with self.subTest(mode=mode,mutation=mutation):
                    d=state/mode/(mutation or 'production');stage=d/'src';stage.mkdir(parents=True)
                    for rel,p in sources.items():
                        target=stage/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
                    source=original
                    if mutation:
                        old,new,scenario,label=bad[mutation];self.assertEqual(source.count(old),1);source=source.replace(old,new);(stage/'mm/cache_alias_owner.dg').write_text(source,encoding='utf-8')
                    built=compile_file(stage/'cache_alias_owner_probe.dg',roots=[stage],mode=mode)
                    (d/'layout.json').write_text(json.dumps(built.layout_manifest,indent=2)+'\n')
                    asm=d/'probe.asm';asm.write_text(built.assembly+'\n'+ABI);objects={}
                    def run(cmd,label,expected=0):
                        r=subprocess.run(list(map(str,cmd)),cwd=ROOT,capture_output=True,text=True,timeout=90)
                        (d/(label+'.json')).write_text(json.dumps(dict(command=list(map(str,cmd)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n')
                        self.assertEqual(r.returncode,expected,r.stdout+r.stderr);return r
                    for fmt in ('elf64','win64'):
                        obj=d/(fmt+'.o');run([nasm,'-f',fmt,*nasm_flags(nasm),asm,'-o',obj],fmt);objects[fmt]=obj
                    exe=d/('probe.exe' if os.name=='nt' else 'probe');run([cc,'-std=c11','-O2','-D__USE_MINGW_ANSI_STDIO=1','-Wall','-Wextra','-Werror',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),HERE/'cache_alias_owner_probe.c',objects['win64' if os.name=='nt' else 'elf64'],'-o',exe],'link')
                    if mutation:
                        r=run([exe,scenario],'execute',1);self.assertIn('wc oracle: '+label,r.stderr);self.assertIn('normally',r.stderr)
                    else:
                        for scenario in ('all','normal','noack'):
                            r=run([exe,scenario],'execute-'+scenario);self.assertIn('raw oracle checks=',r.stdout)
                    results.append(dict(mode=mode,mutation=mutation,all_executions_normal=True))
                    self.assertEqual(hashes(),before)
        (state/'result.json').write_text(json.dumps(dict(passed=len(results)==10,expected_cases=10,cases=results,source_before=before,source_after=hashes()),indent=2)+'\n');print('WC real native evidence',state)
if __name__=='__main__':unittest.main()
