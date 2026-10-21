"""Measure real default/service kernel pool storage in assembled objects."""
from pathlib import Path
import hashlib,json,os,struct,subprocess,unittest,uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
from tools.kernel_storage_profile import generate
ROOT=Path(__file__).resolve().parents[1]

def bss_symbol_span(path,name):
    b=Path(path).read_bytes();assert b[:7]==b'\x7fELF\x02\x01\x01'
    off=struct.unpack_from('<Q',b,40)[0];stride,n=struct.unpack_from('<HH',b,58)
    sections=[struct.unpack_from('<IIQQQQIIQQ',b,off+i*stride)for i in range(n)]
    symbols=[]
    for sec in sections:
        if sec[1]!=2:continue
        strings=b[sections[sec[6]][4]:sections[sec[6]][4]+sections[sec[6]][5]]
        for p in range(sec[4],sec[4]+sec[5],sec[9]):
            at,info,other,index,value,size=struct.unpack_from('<IBBHQQ',b,p)
            if at and index and index<len(sections):symbols.append((strings[at:strings.index(0,at)].decode(),index,value))
    found=[s for s in symbols if s[0]==name];assert len(found)==1
    _,index,start=found[0];sec=sections[index];assert sec[1]==8 and sec[2]&7==3
    ends=[value for text,si,value in symbols if si==index and value>start]
    return min(ends+[sec[5]])-start

class KernelStorageProfileTests(unittest.TestCase):
    def test_actual_compiler_objects_and_unchanged_abi(self):
        nasm=tool('nasm','NASM');self.assertTrue(nasm,'native NASM required, no skip')
        state=ROOT/'build/test/kernel-storage-profile'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
        watched=[Path(__file__),ROOT/'tools/kernel_storage_profile.py',ROOT/'kernel/build/storage_profile.dg',ROOT/'kernel/user/memory.dg']
        hashes=lambda:{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in watched};before=hashes();records=[];abis=[]
        for level,count in [(4,3),(7,2)]:
            out=state/str(level);root,profile=generate(out,level)
            self.assertEqual(profile['static_user_pools'],count)
            for rel,digest in profile['kernel_sources'].items():self.assertEqual(hashlib.sha256((root/rel).read_bytes()).hexdigest(),digest)
            # Only one explicit kernel root; the resolver's duplicate-module
            # rejection remains enabled, and the original source is untouched.
            result=compile_file(root/'user/memory.dg',roots=[root,ROOT/'lang/examples',ROOT/'lang/std',ROOT/'services'],mode='release',function_sections=True)
            asm=out/'memory.asm';asm.write_text(result.assembly);commands=[]
            for fmt in ('elf64','win64'):
                obj=out/(fmt+'.o');cmd=[nasm,'-f',fmt,*nasm_flags(nasm),asm,'-o',obj]
                run=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=90);self.assertEqual(run.returncode,0,run.stdout+run.stderr);commands.append(dict(command=list(map(str,cmd)),returncode=run.returncode,stdout=run.stdout,stderr=run.stderr))
            name='__dg_m'+b'user.memory'.hex()+'_g'+b'TABLES'.hex()
            measured=bss_symbol_span(out/'elf64.o',name);self.assertEqual(measured,count*32*4096)
            types={t['full_name']:t for t in result.layout_manifest['types']};shape={n:types[n] for n in ('user.memory.Process','user.memory.Frame','mm.paging.Space','mm.phys_buddy.Allocator')};abis.append(shape)
            self.assertEqual(types['mm.paging.Space']['size'],64)
            records.append(dict(level=level,profile=profile,measured_static_bytes=measured,commands=commands,layout=shape))
            self.assertEqual(hashes(),before)
        self.assertEqual(abis[0],abis[1]);self.assertEqual(records[0]['measured_static_bytes']-records[1]['measured_static_bytes'],131072)
        (state/'result.json').write_text(json.dumps(dict(passed=True,records=records,source_before=before,source_after=hashes()),indent=2)+'\n');print('actual kernel storage object evidence',state)
    def test_invalid_or_conflicting_profile_preserves_existing_output(self):
        import tempfile
        with tempfile.TemporaryDirectory()as temp:
            output=Path(temp)/'out'
            for bad in (-1,8,True,None,'7'):
                with self.assertRaises(ValueError):generate(output,bad)
                self.assertFalse(output.exists())
            root,profile=generate(output,4);before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with self.assertRaises(ValueError):generate(output,7)
            self.assertEqual(before,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})
            root2,again=generate(output,4);self.assertEqual((root,profile),(root2,again))
if __name__=='__main__':unittest.main()
