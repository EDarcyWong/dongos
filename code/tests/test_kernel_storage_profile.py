"""Measure real default/service kernel pool storage in assembled objects."""
from pathlib import Path
import copy,hashlib,json,os,struct,subprocess,tempfile,unittest,uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
from tools.kernel_storage_profile import generate, module_bytes, static_user_pools, verify_profile, verify_definition
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

def coff_bss_symbol_span(path,name):
    data=Path(path).read_bytes();machine,count,_,offset,number,optional,_=struct.unpack_from('<HHIIIHH',data)
    assert machine==0x8664 and optional==0 and offset+number*18+4<=len(data)
    sections=[struct.unpack_from('<8sIIIIIIHHI',data,20+i*40) for i in range(count)]
    strings=data[offset+number*18:];string_bytes=struct.unpack_from('<I',strings)[0]
    assert 4<=string_bytes<=len(strings)
    symbols=[];index=0
    while index<number:
        raw,value,section,_,_,aux=struct.unpack_from('<8sIhHBB',data,offset+index*18)
        if raw[:4]==bytes(4):
            at=struct.unpack_from('<I',raw,4)[0];assert 4<=at<string_bytes
            text=strings[at:strings.index(0,at,string_bytes)].decode()
        else:text=raw.split(b'\0',1)[0].decode()
        if 1<=section<=count:symbols.append((text,section,value))
        index+=1+aux
    found=[s for s in symbols if s[0]==name];assert len(found)==1
    _,section,start=found[0];header=sections[section-1]
    assert header[9]&0x80 and header[9]&0xc0000000==0xc0000000
    end=header[3]
    ends=[value for _,si,value in symbols if si==section and value>start]
    return min(ends+[end])-start

class KernelStorageProfileTests(unittest.TestCase):
    def test_actual_compiler_objects_and_unchanged_abi(self):
        nasm=tool('nasm','NASM');self.assertTrue(nasm,'native NASM required, no skip')
        state=ROOT/'build/test/kernel-storage-profile'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
        watched=[Path(__file__),ROOT/'tools/kernel_storage_profile.py',ROOT/'kernel/build/storage_profile.dg',ROOT/'kernel/user/memory.dg']
        hashes=lambda:{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in watched};before=hashes();records=[];abis=[]
        for level,count in [(4,3),(5,2),(6,2),(7,1)]:
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
            coff_measured=coff_bss_symbol_span(out/'win64.o',name);self.assertEqual(coff_measured,count*32*4096)
            types={t['full_name']:t for t in result.layout_manifest['types']};shape={n:types[n] for n in ('user.memory.Process','user.memory.Frame','mm.paging.Space','mm.phys_buddy.Allocator')};abis.append(shape)
            self.assertEqual(types['mm.paging.Space']['size'],64)
            records.append(dict(level=level,profile=profile,measured_static_bytes=measured,coff_static_bytes=coff_measured,commands=commands,layout=shape))
            self.assertEqual(hashes(),before)
        for shape in abis[1:]:self.assertEqual(abis[0],shape)
        self.assertEqual([r['measured_static_bytes'] for r in records],[393216,262144,262144,131072])
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
    def test_readonly_exact_definition_and_actual_source_graph(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source';kernel=source/'kernel';kernel.mkdir(parents=True)
            (kernel/'sample.dg').write_text('module sample;pub const X:u64=7;\n')
            (kernel/'build').mkdir();(kernel/'build/storage_profile.dg').write_text('module build.storage_profile;pub const STATIC_USER_POOLS:usize=3;\n')
            source_hashes={'kernel/'+p.relative_to(kernel).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in kernel.rglob('*.dg')}
            for level,count in [(4,3),(5,2),(6,2),(7,1)]:
                out=Path(temp)/str(level);_,profile=generate(out,level,kernel)
                manifest=dict(runtime_level=level,source_unchanged=True,source_sha256=source_hashes,kernel_storage_profile=profile if level>=5 else None)
                before={str(p):p.read_bytes() for p in Path(temp).rglob('*') if p.is_file()}
                self.assertEqual(count,verify_profile(out,manifest,source_root=source))
                self.assertEqual(count,verify_definition(manifest,module_bytes(level) if level>=5 else None,source_root=source))
                self.assertEqual(before,{str(p):p.read_bytes() for p in Path(temp).rglob('*') if p.is_file()})
            for bad in (-1,8,True,None,'7'):
                with self.assertRaises(ValueError):static_user_pools(bad)
            out=Path(temp)/'7';_,profile=generate(out,7,kernel)
            good=dict(runtime_level=7,source_unchanged=True,source_sha256=source_hashes,kernel_storage_profile=profile)
            for kind in ('old-rehashed','boolean-count','missing-profile','omitted-source','changed-snapshot'):
                bad=copy.deepcopy(good);path=out/'kernel-profile-src/build/storage_profile.dg';original=path.read_bytes()
                sample=out/'kernel-profile-src/sample.dg';sample_original=sample.read_bytes()
                try:
                    if kind=='old-rehashed':
                        raw=module_bytes(7).replace(b'POOLS:usize=1;',b'POOLS:usize=2;');path.write_bytes(raw)
                        bad['kernel_storage_profile'].update(static_user_pools=2,sha256=hashlib.sha256(raw).hexdigest())
                    elif kind=='boolean-count':bad['kernel_storage_profile']['static_user_pools']=True
                    elif kind=='missing-profile':del bad['kernel_storage_profile']
                    elif kind=='omitted-source':
                        del bad['source_sha256']['kernel/sample.dg'];del bad['kernel_storage_profile']['kernel_sources']['sample.dg'];sample.unlink()
                    else:sample.write_bytes(b'module sample;pub const X:u64=8;\n')
                    with self.subTest(kind=kind),self.assertRaises(ValueError):verify_profile(out,bad,source_root=source)
                finally:path.write_bytes(original);sample.write_bytes(sample_original)
if __name__=='__main__':unittest.main()
