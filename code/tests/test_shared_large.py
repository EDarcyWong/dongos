"""Execute real active large-page transactions with a separate raw C oracle.

Both modes execute normally; actual wrong Dong sources must link and exit 1
at the specified numeric/ordering invariant. These are host tests, never VMs.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import unittest
import uuid

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool

ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent
MODES=('debug','release')


def block(source,needle):
    start=source.index(needle);opening=source.index('{',start);level=1;end=opening+1
    while level:
        if source[end]=='{':level+=1
        elif source[end]=='}':level-=1
        end+=1
    return source[start:end]


def graph(entry):
    files={'shared_large_probe.dg':entry};pending=[entry]
    while pending:
        path=pending.pop()
        for name in re.findall(r'(?m)^\s*import\s+([\w.]+)',path.read_text(encoding='utf-8')):
            relative=name.replace('.','/')+'.dg'
            if relative in files:continue
            found=[base/relative for base in (ROOT/'kernel',ROOT/'lang/std',HERE) if (base/relative).is_file()]
            if len(found)!=1:raise AssertionError('missing/ambiguous import '+name+': '+str(found))
            files[relative]=found[0];pending.append(found[0])
    return files


class SharedLargeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources=graph(HERE/'shared_large_probe.dg')
        cls.inputs=sorted(set(cls.sources.values())|{HERE/'shared_large_probe.c',Path(__file__).resolve()})
        cls.evidence=ROOT/'build/test/shared-large'/('run-'+uuid.uuid4().hex[:12]);cls.evidence.mkdir(parents=True)
        cls.before=cls.hashes()
        (cls.evidence/'source-before.json').write_text(json.dumps(cls.before,indent=2)+'\n')
        for path in cls.inputs:
            target=cls.evidence/'source-snapshot'/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())

    @classmethod
    def hashes(cls):return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}

    @classmethod
    def tearDownClass(cls):
        after=cls.hashes();(cls.evidence/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
        if after!=cls.before:raise AssertionError('active large source changed while executing')
        print('Active large native evidence:',cls.evidence)

    def command(self,args,directory,label):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        (directory/(label+'.json')).write_text(json.dumps(dict(args=args,cwd=str(ROOT),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n')
        return r

    def prepare(self,mode,mutation):
        directory=self.evidence/(mutation or 'production')/mode;stage=directory/'sources';stage.mkdir(parents=True)
        for relative,path in self.sources.items():
            target=stage/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
        active=stage/'mm/active_paging.dg';source=active.read_text(encoding='utf-8')
        if mutation=='lost-full-root-flush':
            helper=block(source,'unsafe fn flush_root_only(')
            needle='(*context).flush(FLUSH_ROOT,virtual);';self.assertEqual(helper.count(needle),1)
            changed=helper.replace(needle,'// bad source: full root flush omitted')
            source=source.replace(helper,changed)
        elif mutation=='merge-early-reclaim':
            helper=block(source,'pub unsafe fn merge_large(')
            reclaim='try paging.reclaim((*context).space,&retired);'
            flush='(*context).flush(FLUSH_ROOT,virtual);'
            self.assertEqual(helper.count(reclaim),1);self.assertEqual(helper.count(flush),1)
            changed=helper.replace(reclaim,'').replace(flush,reclaim+'\n        '+flush)
            source=source.replace(helper,changed)
        elif mutation=='range-first-page-only':
            helper=block(source,'fn inside_span(')
            needle='return count <= pages - (address - base) / 4096;';self.assertEqual(helper.count(needle),1)
            source=source.replace(helper,helper.replace(needle,'return true;'))
        elif mutation=='lost-domain-check':
            owner=stage/'mm/shared_paging.dg';text=owner.read_text(encoding='utf-8')
            helper=block(text,'unsafe fn run(')
            needle='try domain_valid((*context).domain,(*context).root,(*context).count);'
            self.assertEqual(helper.count(needle),1)
            owner.write_text(text.replace(helper,helper.replace(needle,'')),encoding='utf-8',newline='')
        # Keep the positive production candidate byte-for-byte identical to
        # its frozen source; text-mode newline translation is only for mutants.
        if mutation:active.write_text(source,encoding='utf-8',newline='')
        sources={str(p.relative_to(stage).as_posix()):hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*.dg')}
        for relative,path in self.sources.items():
            if mutation and relative in ('mm/active_paging.dg','mm/shared_paging.dg'):continue
            self.assertEqual(sources[relative],self.before[path.relative_to(ROOT).as_posix()])
        (directory/'bound-inputs.json').write_text(json.dumps(dict(mode=mode,mutation=mutation,original=self.before,compiled_sources=sources),indent=2)+'\n')
        stdout,stderr=io.StringIO(),io.StringIO();exit_code=1
        try:
            with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
                compiled=compile_file(stage/'shared_large_probe.dg',roots=[stage],mode=mode)
            exit_code=0
        except Exception as error:
            stderr.write(repr(error));raise
        finally:
            (directory/'compile.json').write_text(json.dumps(dict(args=['compile_file',str(stage/'shared_large_probe.dg'),'--mode',mode,'--roots',str(stage)],returncode=exit_code,stdout=stdout.getvalue(),stderr=stderr.getvalue()),indent=2)+'\n')
        layout={t['full_name']:t for t in compiled.layout_manifest['types']}
        self.assertEqual((128,8),(layout['mm.active_paging.Context']['size'],layout['mm.active_paging.Context']['alignment']))
        self.assertEqual((160,8),(layout['mm.shared_paging.Context']['size'],layout['mm.shared_paging.Context']['alignment']))
        self.assertEqual(0,layout['mm.shared_paging.Context']['fields'][0]['offset'])
        self.assertEqual(dict(name='totals',type='mm.active_paging.Stats',offset=104,size=24),layout['mm.active_paging.Context']['fields'][-1])
        self.assertEqual((24,8),(layout['mm.active_paging.Stats']['size'],layout['mm.active_paging.Stats']['alignment']))
        self.assertEqual([0,8,16],[f['offset'] for f in layout['mm.active_paging.Stats']['fields']])
        self.assertNotRegex(compiled.assembly.lower(),r'\b(?:xmm|ymm|zmm)[0-9]+\b')
        (directory/'layout.json').write_text(json.dumps(compiled.layout_manifest,indent=2)+'\n')
        assembly=directory/'probe.asm';assembly.write_text(compiled.assembly)
        return directory,assembly

    def test_real_transactions_and_wrong_sources_both_modes(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
        self.assertTrue(nasm and cc,'NASM and GCC required; active large evidence must not skip')
        bad_assertions={
            'lost-full-root-flush':'callbacks==before+1',
            'merge-early-reclaim':'al_used(f->space.data)==expected.tables',
            'range-first-page-only':'!forbid_callback',
            'lost-domain-check':'!forbid_callback',
        }
        for mode in MODES:
            for mutation in (None,*bad_assertions):
                with self.subTest(mode=mode,mutation=mutation):
                    directory,assembly=self.prepare(mode,mutation);obj=directory/'probe.o';exe=directory/('probe.exe' if os.name=='nt' else 'probe')
                    r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),assembly,'-o',obj],directory,'assemble')
                    self.assertEqual(r.returncode,0,r.stderr[:6000])
                    flags=['-mno-sse'] if os.name=='nt' else ['-no-pie']
                    r=self.command([cc,'-std=c11','-O2','-D__USE_MINGW_ANSI_STDIO=1','-Wall','-Wextra','-Werror',*flags,HERE/'shared_large_probe.c',obj,'-o',exe],directory,'link')
                    self.assertEqual(r.returncode,0,r.stderr[:6000])
                    r=self.command([exe],directory,'execute')
                    after=self.hashes();(directory/'source-after-execute.json').write_text(json.dumps(after,indent=2)+'\n');self.assertEqual(after,self.before)
                    if mutation:
                        self.assertEqual(r.returncode,1,r.stdout+r.stderr);self.assertIn('active large check failed',r.stderr);self.assertIn(bad_assertions[mutation],r.stderr)
                    else:
                        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('shared large native checks passed',r.stdout)


if __name__=='__main__':unittest.main()
