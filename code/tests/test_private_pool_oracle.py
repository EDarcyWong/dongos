"""Strict role-bound private pool limits and raw page-table boundary controls."""
import struct
import unittest
from tests import run_desktop_settings_qemu as settings
from tests.run_nvme_qemu import verify_no_user_dma_alias
from tests.run_fat_paths_qemu import effective_mapping


class PoolOracleTests(unittest.TestCase):
    def guest(self, extended=True):
        guest=object.__new__(settings.Guest)
        guest.boot=[0]*20;guest.boot[15]=0x200000
        guest.evidence={}
        table=0xffffffff80010000
        limits=0xffffffff80020000
        dynamic=0xffffffff80021000
        guest.symbols={settings.storage.symbol('user.memory','TABLES'):table,
                       settings.storage.symbol('user.memory','DYNAMIC_PHYSICAL'):dynamic}
        if extended:guest.symbols[settings.storage.symbol('user.memory','POOL_LIMITS')]=limits
        guest._limits=[32]*16
        if extended:guest._limits[3]=128
        guest._dynamic=[0]*16;guest._dynamic[3]=0x800000;guest._dynamic[4]=0xa00000
        guest.roots=[0x210000+i*32*4096 for i in range(4)]+[0xa00000]
        if extended:guest.roots[3]=0x800000
        guest.kernel=lambda va,n,role:struct.pack('<16Q',*(guest._limits if va==limits else guest._dynamic))
        return guest

    def test_exact_static_and_dedicated_arena_roots(self):
        for extended in (False,True):
            guest=self.guest(extended);guest.validate_private_pools()
            self.assertEqual(128 if extended else 32,guest.private_pages(guest.roots[3]))
            self.assertEqual(32,guest.private_pages(guest.roots[4]))

    def test_limit_wrong_role_root_and_overlap_rejected(self):
        for kind in ('ordinary128','compositor32','other64','wrongroot','overlap'):
            guest=self.guest()
            if kind=='ordinary128':guest._limits[4]=128
            elif kind=='compositor32':guest._limits[3]=32
            elif kind=='other64':guest._limits[3]=64
            elif kind=='wrongroot':guest.roots[3]+=4096
            else:guest._dynamic[4]=guest.roots[4]=guest.roots[3]+127*4096
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
