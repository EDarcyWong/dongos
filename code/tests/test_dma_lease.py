"""Execute exact production DMA allocator fragment against an independent boundary model.

No unpin/reclaim path exists. The model injects failures after allocation,
inside own_frame (after metadata), and at every USER map of a rounded block.
"""
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_service_ipc_cancellation import block
ROOT=Path(__file__).resolve().parents[1]
NAMES=('kernel/user/memory.dg','tests/dma_lease_fixture.dg','tests/dma_lease_adapter.dg',
       'tests/dma_lease_probe.c','tests/test_dma_lease.py')
class DmaLeaseTests(unittest.TestCase):
    def prepare(self,mode,mutation=None):
        d=ROOT/'build/test/dma-lease'/('run-'+uuid.uuid4().hex[:12]);d.mkdir(parents=True)
        before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in NAMES}
        (d/'source.json').write_text(json.dumps(before,indent=2)+'\n')
        source=(ROOT/NAMES[0]).read_text()
        metadata=source[source.index('pub struct DmaLease'):source.index('// One exclusive BSP loader transaction.')]
        production=block(source,'pub unsafe fn contiguous(')
        changes={
          'lost-rounded-suffix':('virtual:virtual,pages:pages,root:PROCESSES[id].root','virtual:virtual,pages:requested,root:PROCESSES[id].root'),
          'allocation-before-pin':('PINNED[id]=true;','PINNED[id]=false;'),
          'premature-complete':('attempted:0,mapped:0,state:DMA_HELD','attempted:0,mapped:0,state:DMA_COMPLETE'),
        }
        if mutation:
            old,new=changes[mutation];self.assertEqual(1,production.count(old));production=production.replace(old,new)
        fixture=(ROOT/NAMES[1]).read_text().replace('// PRODUCTION_METADATA',metadata).replace('// PRODUCTION_CONTIGUOUS',production)
        path=d/'dma_lease_fixture.dg';path.write_text(fixture)
        (d/'dma_lease_adapter.dg').write_bytes((ROOT/'tests/dma_lease_adapter.dg').read_bytes())
        c=compile_file(path,roots=[d,ROOT/'lang/std'],mode=mode)
        layout={x['full_name']:x for x in c.layout_manifest['types']}
        self.assertEqual(64,layout['dma_lease_fixture.DmaLease']['size'])
        asm=d/'probe.asm';asm.write_text(c.assembly)
        self.assertEqual(before,{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in NAMES})
        return d,asm
    def command(self,args,d,label):
        r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=90)
        (d/(label+'.json')).write_text(json.dumps(dict(args=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n')
        return r
    def test_frontend_actual_fragment_both_modes(self):
        for mode in ('debug','release'):
            for mutation in (None,'lost-rounded-suffix','allocation-before-pin','premature-complete'):
                with self.subTest(mode=mode,mutation=mutation):self.prepare(mode,mutation)
    def test_native_partial_allocation_and_real_mutations(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc,'NASM and C compiler required; native evidence must not be skipped')
        for mode in ('debug','release'):
            for mutation in (None,'lost-rounded-suffix','allocation-before-pin','premature-complete'):
                with self.subTest(mode=mode,mutation=mutation):
                    d,asm=self.prepare(mode,mutation);obj=d/'probe.o';exe=d/('probe.exe' if os.name=='nt' else 'probe')
                    r=self.command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
                    r=self.command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',* ([] if os.name=='nt' else ['-no-pie']),ROOT/'tests/dma_lease_probe.c',obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                    r=self.command([exe],d,'execute')
                    if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('DMA lease check failed line',r.stderr)
                    else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('DMA lease native checks passed',r.stdout)
