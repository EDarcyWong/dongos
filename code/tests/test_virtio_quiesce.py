"""Trusted modern VirtIO reset protocol, with no DMA release/reuse authority."""
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from tests.test_service_ipc_cancellation import block
from lang.tests.test_dongc import nasm_flags,tool
ROOT=Path(__file__).resolve().parents[1]
NAMES=('kernel/user/virtio_quiesce.dg','kernel/user/device_host.dg','kernel/user/devices.dg',
       'services/drivers/pci.dg','services/drivers/virtio_pci.dg','tests/virtio_quiesce_probe.dg',
       'tests/virtio_quiesce_probe.c','tests/test_virtio_quiesce.py','tests/virtio_quiesce_fixture.dg')
class VirtioQuiesceTests(unittest.TestCase):
    def compile(self,mode,mutation=None):
        d=ROOT/'build/test/virtio-quiesce'/('run-'+uuid.uuid4().hex[:12]);d.mkdir(parents=True)
        hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in NAMES}
        (d/'source.json').write_text(json.dumps(hashes,indent=2)+'\n')
        for n in (NAMES[0],NAMES[3],NAMES[4],NAMES[5]):
            target=d/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/n).read_bytes())
        if mutation and mutation!='skip-wrapper-hold':
            p=d/NAMES[0];s=p.read_text()
            changes={
                'skip-status-read':('if (try vp.read((*ops).read,context,&transport.common,20,1))==0','if true'),
                'wide-status-write':('&transport.common,20,1,0)','&transport.common,20,4,0)'),
                'skip-initial-fence':('if (*ops).fence(context,3)!=0{return error.Io;}','if false{return error.Io;}'),
            }
            old,new=changes[mutation];self.assertGreaterEqual(s.count(old),1);s=s.replace(old,new,1);p.write_text(s)
        wrapper=block((ROOT/'kernel/user/devices.dg').read_text(),'pub unsafe fn quiesce_stopped_block(')
        if mutation=='skip-wrapper-hold':
            self.assertEqual(wrapper.count('BLOCK_RESET_STATE=1;'),1)
            wrapper=wrapper.replace('BLOCK_RESET_STATE=1;','BLOCK_RESET_STATE=0;')
        fixture=(ROOT/'tests/virtio_quiesce_fixture.dg').read_text().replace('// PRODUCTION_WRAPPER',wrapper)
        (d/'tests/virtio_quiesce_fixture.dg').write_text(fixture)
        c=compile_file(d/NAMES[5],roots=[d/'tests',d/'kernel',d/'services'],mode=mode)
        asm=d/'probe.asm';asm.write_text(c.assembly)
        self.assertEqual(hashes,{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in NAMES})
        return d,asm
    def run_command(self,args,d,label):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        (d/(label+'.json')).write_text(json.dumps(dict(args=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
    def test_frontend_and_production_connection(self):
        for mode in ('debug','release'):
            for mutation in (None,'skip-status-read','wide-status-write','skip-initial-fence','skip-wrapper-hold'):self.compile(mode,mutation)
            c=compile_file(ROOT/'kernel/user/device_host.dg',roots=[ROOT/'kernel',ROOT/'services',ROOT/'lang/std',ROOT/'lang/examples'],mode=mode)
            self.assertTrue(('__dg_m'+'user.devices'.encode().hex()+'_f'+'quiesce_stopped_block'.encode().hex()) in c.assembly, 'production reset hook missing')
    def test_native_reset_and_actual_mutations(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc,'native verification requires NASM/GCC')
        for mode in ('debug','release'):
            for mutation in (None,'skip-status-read','wide-status-write','skip-initial-fence','skip-wrapper-hold'):
                with self.subTest(mode=mode,mutation=mutation):
                    d,asm=self.compile(mode,mutation);obj=d/'probe.o';exe=d/('probe.exe' if os.name=='nt' else 'probe')
                    r=self.run_command([nasm,'-f','win64' if os.name=='nt' else 'elf64',*nasm_flags(nasm),asm,'-o',obj],d,'assemble');self.assertEqual(0,r.returncode,r.stderr)
                    r=self.run_command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',* ([] if os.name=='nt' else ['-no-pie']),ROOT/'tests/virtio_quiesce_probe.c',obj,'-o',exe],d,'link');self.assertEqual(0,r.returncode,r.stderr)
                    r=self.run_command([exe],d,'execute')
                    if mutation:self.assertEqual(1,r.returncode,r.stdout+r.stderr);self.assertIn('VirtIO quiesce check failed',r.stderr)
                    else:self.assertEqual(0,r.returncode,r.stdout+r.stderr);self.assertIn('VirtIO quiesce native checks passed',r.stdout)
