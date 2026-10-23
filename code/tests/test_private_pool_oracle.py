"""Strict role-bound private pool limits and raw page-table boundary controls."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from tests import run_desktop_settings_qemu as settings
from tests.run_nvme_qemu import verify_no_user_dma_alias
from tests.run_fat_paths_qemu import effective_mapping
from tools.kernel_storage_profile import generate


class PoolOracleTests(unittest.TestCase):
    def guest(self, extended=True, level=4):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name);source=root/'source';(source/'kernel').mkdir(parents=True)
        (source/'kernel/sample.dg').write_text('module sample;\n')
        output=root/'image';_,profile=generate(output,level,source/'kernel')
        hashes={'kernel/sample.dg':hashlib.sha256((source/'kernel/sample.dg').read_bytes()).hexdigest()}
        (output/'build-inputs.json').write_text(json.dumps(dict(runtime_level=level,source_unchanged=True,source_sha256=hashes,kernel_storage_profile=profile if level>=5 else None)))
        guest=object.__new__(settings.Guest)
        guest.esp=output/'esp';guest.esp.mkdir();guest.profile_manifest=output/'build-inputs.json'
        guest.boot=[0]*20;guest.boot[15]=0x200000
        guest.evidence={}
        table=0xffffffff80010000;limits=0xffffffff80100000;dynamic=limits+0x1000
        names=('DYNAMIC_TABLES','SPACES','META','GENERATIONS','PROCESSES')
        guest.symbols={settings.storage.symbol('user.memory','TABLES'):table,settings.storage.symbol('user.memory','DYNAMIC_PHYSICAL'):dynamic}
        guest.symbols.update({settings.storage.symbol('user.memory',name):limits+0x2000+index*0x10000 for index,name in enumerate(names)})
        guest.symbols.update({settings.storage.symbol('boot.service_memory','PLAN'):limits+0x80000,settings.storage.symbol('boot.service_memory','NEXT_PAGE'):limits+0x81000})
        if extended:guest.symbols[settings.storage.symbol('user.memory','POOL_LIMITS')]=limits
        guest._limits=[32]*16
        if extended:guest._limits[3]=128
        count=1 if level==7 else 2 if level>=5 else 3
        guest._dynamic=[0 if i<count else 0x800000+i*0x100000 for i in range(16)]
        guest._pointers=[0 if i<count else 0xffffd40000000000+guest._dynamic[i]-0x800000 for i in range(16)]
        guest.roots=[0x210000+i*32*4096 if i<count else guest._dynamic[i] for i in range(5)]
        guest.corrupt=None
        def rebuild():
            kbase=0x400000;kraw=bytearray(128*4096);next_table=1;leaves={}
            def mapping(va,pa):
                nonlocal next_table
                offset=0
                for shift in (39,30,21):
                    at=offset+((va>>shift)&511)*8;entry=struct.unpack_from('<Q',kraw,at)[0]
                    if not entry:
                        child=next_table;next_table+=1;entry=(kbase+child*4096)|3;struct.pack_into('<Q',kraw,at,entry)
                    offset=(entry&settings.storage.MASK)-kbase
                at=offset+((va>>12)&511)*8;struct.pack_into('<Q',kraw,at,pa|(1<<63)|3);leaves[va]=at
            for pid,physical in enumerate(guest.roots):
                pointer=table+pid*32*4096 if pid<count else guest._pointers[pid]
                for page in range(guest._limits[pid]):mapping(pointer+page*4096,physical+page*4096)
            if guest.corrupt=='alias':struct.pack_into('<Q',kraw,leaves[guest._pointers[1]],0x1000000|(1<<63)|3)
            spaces=bytearray(16*64);metadata=bytearray(16*128);processes=bytearray(16*1288);generations=[0]*16;images={kbase:kraw}
            for pid,physical in enumerate(guest.roots):
                pointer=table+pid*32*4096 if pid<count else guest._pointers[pid]
                struct.pack_into('<6Q',spaces,pid*64,1,pointer,guest._limits[pid],physical,guest.ksym('user.memory','META')+pid*128,(1<<48)-4096)
                spaces[pid*64+48]=1;struct.pack_into('<Q',spaces,pid*64+56,1);metadata[pid*128]=1
                struct.pack_into('<2Q',processes,pid*1288,1,physical);struct.pack_into('<Q',processes,pid*1288+160,physical)
                struct.pack_into('<Q',processes,pid*1288+224,0x10000000);generations[pid]=1
                image=bytearray(guest._limits[pid]*4096);image[:4096]=kraw[:4096];images[physical]=image
            if guest.corrupt=='metadata':metadata[128]=2
            elif guest.corrupt=='space-used':struct.pack_into('<Q',spaces,64+56,2)
            elif guest.corrupt=='frame':struct.pack_into('<Q',processes,1288+160,guest.roots[1]+4096)
            elif guest.corrupt=='generation':generations[1]=0
            elif guest.corrupt=='shared-slot':struct.pack_into('<Q',images[guest.roots[1]],8,32)
            guest._data={limits:struct.pack('<16Q',*guest._limits),dynamic:struct.pack('<16Q',*guest._dynamic),
                guest.ksym('user.memory','DYNAMIC_TABLES'):struct.pack('<16Q',*guest._pointers),guest.ksym('user.memory','SPACES'):spaces,
                guest.ksym('user.memory','META'):metadata,guest.ksym('user.memory','GENERATIONS'):struct.pack('<16Q',*generations),guest.ksym('user.memory','PROCESSES'):processes,
                guest.ksym('boot.service_memory','PLAN'):struct.pack('<6Q',0,0,0,0,0x800000,128*1024*1024),guest.ksym('boot.service_memory','NEXT_PAGE'):struct.pack('<Q',8192)}
            guest._images=images
        def physical(pa,n,role):
            for base,data in guest._images.items():
                if base<=pa and pa+n<=base+len(data):return bytes(data[pa-base:pa-base+n])
            raise AssertionError('host byte fixture escaped')
        guest.fixture_rebuild=rebuild;rebuild()
        def kernel_read(va,n,role):
            if va==limits:return struct.pack('<16Q',*guest._limits)
            if va==dynamic:return struct.pack('<16Q',*guest._dynamic)
            if va==guest.ksym('user.memory','DYNAMIC_TABLES'):return struct.pack('<16Q',*guest._pointers)
            return bytes(guest._data[va])
        guest.kernel=kernel_read
        guest.physical=physical
        def kernel_pool():
            guest.evidence['trusted_kernel_page_table_pool']=dict(root_physical=0x400000)
            return 0x400000,128
        guest.trusted_kernel_pool=kernel_pool
        return guest

    def test_exact_static_and_dedicated_arena_roots(self):
        for extended,level in ((False,4),(True,4),(True,5),(True,6),(True,7)):
            guest=self.guest(extended,level);guest.validate_private_pools()
            self.assertEqual(128 if extended else 32,guest.private_pages(guest.roots[3]))
            self.assertEqual(32,guest.private_pages(guest.roots[4]))
            self.assertEqual('arena' if level==7 else 'static','static' if guest.uses_static_pool(1) else 'arena')

    def test_limit_wrong_role_root_and_overlap_rejected(self):
        for kind in ('ordinary128','compositor32','other64','wrongroot','overlap'):
            guest=self.guest()
            if kind=='ordinary128':guest._limits[4]=128
            elif kind=='compositor32':guest._limits[3]=32
            elif kind=='other64':guest._limits[3]=64
            elif kind=='wrongroot':guest.roots[3]+=4096
            else:guest._dynamic[4]=guest.roots[4]=guest.roots[3]+127*4096
            with self.subTest(kind=kind),self.assertRaises(ValueError):guest.validate_private_pools()
    def test_slot1_dynamic_identity_and_rehashed_old_profile_rejected(self):
        for kind in ('slot1-static','slot1-wrong-dynamic','overlap','old-rehashed','missing-profile','metadata','space-used','frame','generation','shared-slot','alias'):
            guest=self.guest(True,7)
            if kind=='slot1-static':
                guest.roots[1]=guest._dynamic[1]=0x230000;guest._pointers[1]=guest.ksym('user.memory','TABLES')+32*4096;guest.fixture_rebuild()
            elif kind=='slot1-wrong-dynamic':guest._dynamic[1]+=4096
            elif kind=='overlap':guest._dynamic[1]=guest.roots[1]=guest.roots[0]+4096;guest.fixture_rebuild()
            elif kind in ('metadata','space-used','frame','generation','shared-slot','alias'):guest.corrupt=kind;guest.fixture_rebuild()
            else:
                manifest=json.loads(guest.profile_manifest.read_text())
                if kind=='missing-profile':del manifest['kernel_storage_profile']
                else:
                    profile=guest.profile_manifest.parent/'kernel-profile-src/build/storage_profile.dg'
                    raw=profile.read_bytes().replace(b'POOLS:usize=1;',b'POOLS:usize=2;');profile.write_bytes(raw)
                    manifest['kernel_storage_profile'].update(static_user_pools=2,sha256=hashlib.sha256(raw).hexdigest())
                guest.profile_manifest.write_text(json.dumps(manifest))
            with self.subTest(kind=kind),self.assertRaises(ValueError):guest.validate_private_pools()

    def tree(self, index, leaf=0x300000):
        root=0x100000
        pages={root:bytearray(4096)}
        chain=[root,root+index*4096,root+(index-1)*4096,root+(index-2)*4096]
        for pa in chain:pages.setdefault(pa,bytearray(4096))
        for parent,child in zip(chain,chain[1:]):struct.pack_into('<Q',pages[parent],0,child|7)
        struct.pack_into('<Q',pages[chain[-1]],0,leaf|7|(1<<63))
        reads=[]
        def read(pa):reads.append(pa);return bytes(pages[pa])
        return root,read,reads

    def test_last_page_allowed_only_with_exact_extended_limit(self):
        root,read,reads=self.tree(127)
        result=verify_no_user_dma_alias(root,read,0x200000,4096,private_pages=128)
        self.assertEqual(128,result['private_pool_pages'])
        self.assertEqual(4,len(reads))
        mapping=effective_mapping(root,0,read,(0x400000,128),128)
        self.assertTrue(mapping['effective_user'] and mapping['effective_nx'])
        for pages in (32,128):
            root,read,reads=self.tree(128 if pages==128 else 32)
            with self.subTest(pages=pages),self.assertRaises(ValueError):
                verify_no_user_dma_alias(root,read,0x200000,4096,private_pages=pages)
            self.assertEqual([root],reads)
            with self.assertRaises(ValueError):effective_mapping(root,0,read,(0x400000,128),pages)

    def test_extended_walk_still_rejects_actual_dma_alias_and_bad_limit(self):
        root,read,_=self.tree(127,0x200000)
        with self.assertRaisesRegex(ValueError,'aliases DMA'):
            verify_no_user_dma_alias(root,read,0x200000,4096,private_pages=128)
        for pages in (0,31,64,129):
            with self.subTest(pages=pages),self.assertRaises(ValueError):
                verify_no_user_dma_alias(root,read,0x200000,4096,private_pages=pages)


if __name__=='__main__':unittest.main(verbosity=2)
