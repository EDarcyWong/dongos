"""Production native revoke with real paging receipts and owned RAM."""
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT/'kernel/user/memory.dg'
class Tests(unittest.TestCase):
    def test_complete_precheck_linear_receipts_survivors_and_failstop(self):
        names=('kernel/user/memory.dg','kernel/mm/paging.dg','kernel/boot/memory_startup.dg',
          'tests/user_unshare_fixture.dg','tests/user_unshare_startup.dg','tests/user_unshare_paging.dg',
          'tests/user_unshare_resources.dg','tests/user_unshare_probe.c','tests/test_user_unshare.py')
        inputs=[ROOT/p for p in names]+[CANDIDATE];before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        mutations={
          'skip-zero-table-receipt':('try paging.reclaim(&SPACES[id],UNSHARE_RECEIPTS+page);',
            'if paging.retired_tables(UNSHARE_RECEIPTS+page)!=0{try paging.reclaim(&SPACES[id],UNSHARE_RECEIPTS+page);}'),
          'ignore-other-root':('if *recycled(index)==4&&referenced_frame(index)',
            'if *recycled(index)==4&&false'),
          'skip-final-zero':('var word:usize=0;while word<512{*(((*record(index)).virtual as *u64)+word)=0;word+=1;}\n            *recycled(index)=1;',
            'var word:usize=512;while word<512{*(((*record(index)).virtual as *u64)+word)=0;word+=1;}\n            *recycled(index)=1;'),
          'skip-shared-journal':('*(UNSHARE_FRAMES+UNSHARE_COUNT)=index as u16;UNSHARE_COUNT+=1;return;', 'return;'),
          'skip-shared-prefix-withdrawal':('let cleanup=shared_cleanup(source,target,source_base,target_base,source_pages,target_pages);', 'let cleanup=shared_cleanup(source,target,source_base,target_base,0,0);'),
          'ignore-late-error':('match detached{ok=>{},err(code)=>{UNSHARE_FAILED=true;return detached;},}',
            'match detached{ok=>{},err(code)=>{return detached;},}'),
        }
        out=ROOT/'build/test/user-unshare'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);evidence={}
        def command(argv,d,label):
            argv=list(map(str,argv));r=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=60)
            (d/(label+'.json')).write_text(json.dumps(dict(argv=argv,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
        for mode in ('debug','release'):
            for variant in ('normal',*mutations):
                d=out/(mode+'-'+variant);(d/'kernel').mkdir(parents=True)
                for original in (ROOT/'kernel').rglob('*.dg'):
                    target=d/'kernel'/original.relative_to(ROOT/'kernel');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original.read_bytes())
                source=CANDIDATE.read_text()
                if variant!='normal':
                    old,new=mutations[variant]
                    if variant=='skip-final-zero':
                        at=source.index('unsafe fn unshare_recycle(');end=source.index('unsafe fn unshare_withdraw(',at)
                        prefix,body,suffix=source[:at],source[at:end],source[end:];self.assertEqual(1,body.count(old));source=prefix+body.replace(old,new)+suffix
                    else:self.assertEqual(1,source.count(old));source=source.replace(old,new)
                path=d/'kernel/user/memory.dg';path.write_text(source+'\n'+(ROOT/names[3]).read_text())
                (d/'kernel/boot/memory_startup.dg').write_text((ROOT/names[2]).read_text()+'\n'+(ROOT/names[4]).read_text())
                paging=(ROOT/names[1]).read_text().replace('pub unsafe fn reclaim(space: *Space, retired: *Retired) !void {','unsafe fn reclaim_impl(space: *Space, retired: *Retired) !void {')
                (d/'kernel/mm/paging.dg').write_text(paging+'\n'+(ROOT/names[5]).read_text())
                (d/'kernel/boot/service_memory.dg').write_text((ROOT/names[6]).read_text())
                c=compile_file(path,roots=[d/'kernel',ROOT/'services',ROOT/'lang/std',ROOT/'lang/examples'],mode=mode)
                layouts={item['full_name']:item for item in c.layout_manifest['types']};self.assertEqual(64,layouts['mm.paging.Retired']['size'])
                asm=d/'probe.asm';asm.write_text(c.assembly)
                mocked={'__dong_panic','user_current_root','user_pcid_flush_all','user_pcid_unbind','user_pcid_bind','user_entropy64','runtime_invalidate','runtime_copy_bytes','user_pcid_invalidate_root','unshare_reclaim_event'}
                externs={m.group(1).lstrip('$') for m in re.finditer(r'^extern (\$?\w+)',c.assembly,re.M)}-mocked
                stub=d/'unused.asm';stub.write_text('bits 64\nsection .text\n'+''.join('global $'+x+'\n$'+x+': ud2\n' for x in sorted(externs)))
                objects=[]
                for label,file in (('probe',asm),('unused',stub)):
                    obj=d/(label+'.o');objects.append(obj);r=command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),file,'-o',obj],d,'assemble-'+label);self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe');r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),ROOT/names[7],*objects,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                r=command([exe],d,'execute');self.assertEqual(0 if variant=='normal' else 1,r.returncode,r.stdout+r.stderr)
                evidence[mode+'-'+variant]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
        after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs};self.assertEqual(before,after)
        (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_sha256=after,sources_unchanged=True,
          candidate_only=True,real_paging_receipts_executed=True,hardware_and_arena_mapping_mocked=True,evidence=evidence),indent=2)+'\n')
        print('USER_UNSHARE_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
