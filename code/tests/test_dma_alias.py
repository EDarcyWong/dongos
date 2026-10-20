"""Execute the actual DMA alias guard and share_at, including partial leases."""
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_service_ipc_cancellation import block
ROOT=Path(__file__).resolve().parents[1]
NAMES=('kernel/user/memory.dg','tests/dma_alias_fixture.dg','tests/dma_alias_adapter.dg',
       'tests/dma_alias_probe.c','tests/test_dma_alias.py')
class DmaAliasTests(unittest.TestCase):
    def prepare(self,mode,mutation=None):
        d=ROOT/'build/test/dma-alias'/('run-'+uuid.uuid4().hex[:12]);d.mkdir(parents=True)
        before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in NAMES}
        (d/'source.json').write_text(json.dumps(before,indent=2)+'\n')
        source=(ROOT/NAMES[0]).read_text()
        metadata=source[source.index('pub struct DmaLease'):source.index('// One exclusive BSP loader transaction.')]
        reserved=block(source,'unsafe fn dma_reserved(')
        production=block(source,'pub unsafe fn share_at(')
        if mutation=='skip-guard':
            old='if dma_reserved(mapping.physical){return error.InvalidAccess;}'
            self.assertEqual(1,production.count(old));production=production.replace(old,'if false{return error.InvalidAccess;}')
        if mutation=='mapped-only':
            self.assertEqual(1,reserved.count('<lease.pages'));reserved=reserved.replace('<lease.pages','<lease.mapped')
        fixture=(ROOT/NAMES[1]).read_text().replace('// PRODUCTION_METADATA',metadata).replace('// PRODUCTION_RESERVED',reserved).replace('// PRODUCTION_SHARE',production)
        path=d/'dma_alias_fixture.dg';path.write_text(fixture)
        (d/'dma_alias_adapter.dg').write_bytes((ROOT/'tests/dma_alias_adapter.dg').read_bytes())
        c=compile_file(path,roots=[d,ROOT/'lang/std'],mode=mode)
        layout={x['full_name']:x for x in c.layout_manifest['types']}
        self.assertEqual(64,layout['dma_alias_fixture.DmaLease']['size'])
        asm=d/'probe.asm';asm.write_text(c.assembly)
        self.assertEqual(before,{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in NAMES})
        return d,asm
    def command(self,args,d,label):
        r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=90)
        (d/(label+'.json')).write_text(json.dumps(dict(args=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n')
        return r
    def test_frontend_actual_fragment_both_modes(self):
        for mode in ('debug','release'):
            for mutation in (None,'skip-guard','mapped-only'):
                with self.subTest(mode=mode,mutation=mutation):self.prepare(mode,mutation)
    def test_native_actual_share_and_real_mutations(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc,'NASM and C compiler required; native evidence must not be skipped')
        for mode in ('debug','release'):
            for mutation in (None,'skip-guard','mapped-only'):
                with self.subTest(mode=mode,mutation=mutation):
                    d,asm=self.prepare(mode,mutation);obj=d/'probe.o';exe=d/('probe.exe' if os.name=='nt' else 'probe')
                    r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
                    r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',* ([] if os.name=='nt' else ['-no-pie']),ROOT/'tests/dma_alias_probe.c',obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                    r=self.command([exe],d,'execute')
                    if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('DMA alias check failed line',r.stderr)
                    else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('DMA alias native checks passed',r.stdout)
