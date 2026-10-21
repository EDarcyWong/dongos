"""Independent raw-ledger and report rejection tests; actual guests run separately."""
import copy,struct,unittest
from pathlib import Path
from lang.dongc import compile_file
from tests import run_p2_shared_large_qemu as gate
ROOT=Path(__file__).resolve().parents[1]
def report(count=4):
    r=dict.fromkeys(gate.FIELDS,0)
    r.update(version=1,attempted=1,complete=1,phase=11,steps=2047,held=1,sealed=1,seal_error=0x060e0002,
        window=gate.WINDOW,root=0x400000,cr3=0x400000,physical=0x600000,pages=512,order=9,
        free_before=880,free_held=368,free_after=368,tables_before=1,tables_mapped=3,tables_split=4,tables_merged=3,
        cleanup_tables=1,tables_after=3,invlpg=2,full_flush=517,retired_tables=4,merge_error=0x02030007,
        domain_pointer=0xffffffff80100000,count=count,reader_checks=5*(count-1),cr0=0x80010033,cr4=0x340668,efer=0xd00,
        rflags=0x46,pat=0x7040600070406,split_entry=0x403007)
    tag=lambda i:0x1122334400000000|i
    for name,i in [('sample_first',0),('sample_last',511),('split_value',5),('replacement_value',6),('restored_value',5),('merge_value',5),('reader_value',5)]:r[name]=tag(i)
    for n in ('large_entry','merged_entry','final_entry'):r[n]=0x8000000000600083
    for n,diff in dict(epoch=524,broadcasts=524,sent=524*(count-1),acks=524*(count-1),invalid=2,full=517,probes=5).items():
        r[n+'_before']=0;r[n+'_after']=diff
    return r
class SharedGuestOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout=compile_file(ROOT/'kernel/smp/runtime.dg',roots=[ROOT/'kernel',ROOT/'lang/std',ROOT/'lang/examples'],mode='release').layout_manifest
        cls.types={t['full_name']:t for t in cls.layout['types']}
    def test_exact_abi_and_report_rejects_missing_ack_or_returned_lease(self):
        for count in (1,4):
            r=report(count);self.assertEqual(gate.validate_report(r),r)
            self.assertEqual(gate.decode_report(struct.pack('<63Q',*(r[n] for n in gate.FIELDS)),self.layout),r)
        for name in ('held','sealed','acks_after','full_flush','free_after','reader_value','cleanup_tables','domain_pending'):
            r=report();r[name]^=1
            with self.subTest(name=name),self.assertRaises(ValueError):gate.validate_report(r)
        layout=copy.deepcopy(self.layout);t=next(t for t in layout['types'] if t['full_name']=='smp.large_memory.Report');t['fields'][-1]['offset']-=8
        with self.assertRaises(ValueError):gate.decode_report(bytes(504),layout)
        with self.assertRaises(ValueError):gate.decode_report(bytes(496),self.layout)
    def test_complete_table_pool_rejects_alias_unreachable_and_unzeroed_tables(self):
        r=report();pool=bytearray(128*4096);meta=bytearray(128);meta[:3]=b'\1'*3
        struct.pack_into('<Q',pool,336*8,r['root']+4096|7);struct.pack_into('<Q',pool,4096,r['root']+8192|7)
        struct.pack_into('<Q',pool,8192,r['final_entry']);space=bytearray(self.types['mm.paging.Space']['size'])
        f=next(f for f in self.types['mm.paging.Space']['fields'] if f['name']=='used_total');struct.pack_into('<Q',space,f['offset'],3)
        self.assertEqual(gate.audit_pool(pool,meta,space,self.types,r)['large_pages'],1)
        for kind in ('alias','cycle','unreachable','unzeroed','wrong_cache'):
            p=bytearray(pool);m=bytearray(meta);s=bytearray(space)
            if kind=='alias':
                m[3]=1;struct.pack_into('<Q',p,8192+8,r['root']+12288|7);struct.pack_into('<Q',p,12288,r['physical']|0x8000000000000003);struct.pack_into('<Q',s,f['offset'],4)
            elif kind=='cycle':struct.pack_into('<Q',p,336*8,r['root']|7)
            elif kind=='unreachable':m[3]=1;struct.pack_into('<Q',s,f['offset'],4)
            elif kind=='unzeroed':p[12288]=1
            else:struct.pack_into('<Q',p,8192,r['final_entry']|0x18)
            with self.subTest(kind=kind),self.assertRaises(ValueError):gate.audit_pool(p,m,s,self.types,r)
    def test_exact_buddy_lease_rejects_free_overlap_and_metadata_forgery(self):
        r=report();a=bytearray(128);m=bytearray(16384);none=(1<<64)-1
        struct.pack_into('<B7xQQQ',a,0,1,0x400000,1024,0xffffffff80120000)
        heads=[none]*11
        for i in range(1024):struct.pack_into('<BB6xQ',m,i*16,3,0,none)
        for i,order in ((0,7),(128,4),(512,9)):struct.pack_into('<BB6xQ',m,i*16,2,order,none)
        for i,order in ((144,4),(160,5),(192,6),(256,8)):heads[order]=i;struct.pack_into('<BB6xQ',m,i*16,1,order,none)
        struct.pack_into('<11Q',a,32,*heads);struct.pack_into('<Q',a,120,368)
        self.assertEqual(gate.audit_buddy(a,m,r),368)
        for kind in ('freed_lease','wrong_order','free_cycle','counter'):
            x=bytearray(a);y=bytearray(m)
            if kind=='freed_lease':y[512*16]=1
            elif kind=='wrong_order':y[512*16+1]=8
            elif kind=='free_cycle':struct.pack_into('<Q',y,144*16+8,144)
            else:struct.pack_into('<Q',x,120,880)
            with self.subTest(kind=kind),self.assertRaises(ValueError):gate.audit_buddy(x,y,r)
if __name__=='__main__':unittest.main()
