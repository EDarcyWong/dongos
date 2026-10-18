"""Deferred compositor-reader lifetime using real USER PTEs and RAM owner."""
import hashlib,json,os,re,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT/'build/test/p7-reader-candidate/kernel/user/window_broker.dg'
class Tests(unittest.TestCase):
    def test_real_alias_retention_reused_source_and_final_reclaim(self):
        names=('kernel/user/memory.dg','kernel/mm/paging.dg','kernel/boot/memory_startup.dg','kernel/user/window_broker.dg',
          'tests/window_reader_memory.dg','tests/window_reader_startup.dg','tests/window_reader_broker.dg',
          'tests/user_unshare_resources.dg','tests/window_reader_probe.c','tests/test_window_reader.py')
        inputs=[ROOT/p for p in names]+[CANDIDATE];before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        mutations={
          'early-budget-refund':('ENTRIES[i].live=2;','USED-=item.pages*4096;ENTRIES[i].live=2;'),
          'retouch-reused-client':('if item.live==1{','if true{'),
          'forget-orphan-on-server-exit':('if ENTRIES[i].live!=0 {try revoke_index(i);}','if ENTRIES[i].live==1 {try revoke_index(i);}'),
        }
        out=ROOT/'build/test/window-reader'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);evidence={}
        def command(argv,d,label):
            argv=list(map(str,argv));r=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=60)
            (d/(label+'.json')).write_text(json.dumps(dict(argv=argv,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
        for mode in ('debug','release'):
            for variant in ('normal','old-immediate-double-withdrawal',*mutations):
                d=out/(mode+'-'+variant);(d/'kernel').mkdir(parents=True)
                for original in (ROOT/'kernel').rglob('*.dg'):
                    target=d/'kernel'/original.relative_to(ROOT/'kernel');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original.read_bytes())
                source=CANDIDATE.read_text(encoding='utf-8')
                if variant=='old-immediate-double-withdrawal':source=(ROOT/names[3]).read_text(encoding='utf-8')
                elif variant!='normal':
                    old,new=mutations[variant];self.assertEqual(1,source.count(old));source=source.replace(old,new)
                path=d/'kernel/user/window_broker.dg';path.write_text(source+'\n'+(ROOT/names[6]).read_text(encoding='utf-8'),encoding='utf-8')
                (d/'kernel/user/memory.dg').write_text((ROOT/names[0]).read_text(encoding='utf-8')+'\n'+(ROOT/names[4]).read_text(encoding='utf-8'),encoding='utf-8')
                (d/'kernel/boot/memory_startup.dg').write_text((ROOT/names[2]).read_text(encoding='utf-8')+'\n'+(ROOT/names[5]).read_text(encoding='utf-8'),encoding='utf-8')
                (d/'kernel/boot/service_memory.dg').write_text((ROOT/names[7]).read_text(encoding='utf-8'),encoding='utf-8')
                c=compile_file(path,roots=[d/'kernel',ROOT/'services',ROOT/'lang/std',ROOT/'lang/examples'],mode=mode)
                layouts={item['full_name']:item for item in c.layout_manifest['types']}
                self.assertEqual(1288,layouts['user.memory.Process']['size']);self.assertEqual(24,layouts['user.memory.Frame']['size']);self.assertEqual(56,layouts['mm.paging.Retired']['size'])
                asm=d/'probe.asm';asm.write_text(c.assembly)
                mocked={'__dong_panic','user_current_root','user_pcid_flush_all','user_pcid_unbind','user_pcid_bind','user_entropy64','runtime_invalidate','runtime_copy_bytes','user_pcid_invalidate_root'}
                externs={m.group(1).lstrip('$') for m in re.finditer(r'^extern (\$?\w+)',c.assembly,re.M)}-mocked
                stub=d/'unused.asm';stub.write_text('bits 64\nsection .text\n'+''.join('global $'+x+'\n$'+x+': ud2\n' for x in sorted(externs)))
                objects=[]
                for label,file in (('probe',asm),('unused',stub)):
                    obj=d/(label+'.o');objects.append(obj);r=command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),file,'-o',obj],d,'assemble-'+label);self.assertEqual(0,r.returncode,r.stderr)
                exe=d/('probe.exe' if os.name=='nt' else 'probe');r=command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),ROOT/names[8],*objects,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                r=command([exe],d,'execute');self.assertEqual(0 if variant=='normal' else 1,r.returncode,r.stdout+r.stderr)
                if variant!='normal':self.assertIn('window reader oracle failed line',r.stderr)
                evidence[mode+'-'+variant]=dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
        after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs};self.assertEqual(before,after)
        (out/'validation-summary.json').write_text(json.dumps(dict(passed=True,source_sha256=after,sources_unchanged=True,
          candidate_only=True,real_memory_and_paging=True,hardware_and_arena_boundaries_mocked=True,evidence=evidence),indent=2)+'\n')
        print('WINDOW_READER_EVIDENCE',out)
if __name__=='__main__':unittest.main(verbosity=2)
