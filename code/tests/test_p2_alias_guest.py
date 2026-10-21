"""Independent full-root and report oracle rejection, no hardware simulation."""
import copy,struct,unittest,hashlib
from tests import run_p2_alias_qemu as q

class AliasGuestOracleTests(unittest.TestCase):
    def test_independent_actual_msr_decode_and_overlap_rejection(self):
        words=[0]*52;words[13]=2;words[14]=0x806;words[15]=36
        words[16]=0x80000006;words[17]=(((1<<36)-1)&~(0x200000-1))|0x800
        data=lambda:struct.pack('<52Q',*words)
        self.assertEqual(q.audit_mtrr(data(),0x80000000,2)['effective_mtrr_types'],[6])
        words[18]=0x80000004;words[19]=words[17]
        self.assertEqual(q.audit_mtrr(data(),0x80000000,2)['effective_mtrr_types'],[4])
        words[18]=0x80000001
        with self.assertRaisesRegex(ValueError,'undefined actual MTRR overlap'):q.audit_mtrr(data(),0x80000000,2)
        words[18]=0x80000000
        self.assertEqual(q.audit_mtrr(data(),0x80000000,2)['effective_mtrr_types'],[0])
    def test_real_profile_source_is_in_the_observed_input_inventory(self):
        key='kernel/build/storage_profile.dg'
        self.assertEqual(q.source_hashes()[key],hashlib.sha256((q.ROOT/key).read_bytes()).hexdigest())
    def fixture(self):
        base=0x400000;frame=0x10000000;fb=0x80000000;pool=bytearray(16*4096);meta=bytearray(16);meta[0]=1;next_table=1
        def map_page(va,pa,flags):
            nonlocal next_table
            table=0
            for shift in (39,30,21):
                at=table*4096+((va>>shift)&511)*8;e=struct.unpack_from('<Q',pool,at)[0]
                if not e:
                    child=next_table;next_table+=1;meta[child]=1;e=(base+child*4096)|7;struct.pack_into('<Q',pool,at,e)
                table=((e&q.MASK)-base)//4096
            struct.pack_into('<Q',pool,table*4096+((va>>12)&511)*8,pa|flags)
        map_page(q.A,frame,q.NX|1);map_page(q.B,frame,1)
        for i in range(2):map_page(q.HHDM+fb+i*4096,fb+i*4096,q.NX|131)
        return base,frame,fb,pool,meta,map_page
    def audit(self,data):
        base,frame,fb,pool,meta,_=data;return q.audit_pool(bytes(pool),bytes(meta),base,frame,fb,2)
    def test_full_tree_good_and_semantic_memory_corruptions(self):
        data=self.fixture();r=self.audit(data);self.assertEqual(len(r['exec_aliases']),2);self.assertEqual(len(r['framebuffer_aliases']),2)
        for name in ('writable-exec-alias','hidden-alias','UC-GOP','orphan','cycle','dirty-free-table'):
            with self.subTest(name=name):
                base,frame,fb,pool,meta,map_page=data=self.fixture()
                if name=='writable-exec-alias':map_page(q.A,frame,q.NX|3)
                if name=='hidden-alias':map_page(q.HHDM+frame,frame,q.NX|1)
                if name=='UC-GOP':map_page(q.HHDM+fb,fb,q.NX|27)
                if name=='orphan':meta[-1]=1
                if name=='cycle':struct.pack_into('<Q',pool,((q.A>>39)&511)*8,base|7)
                if name=='dirty-free-table':pool[-1]=1
                with self.assertRaises(ValueError):self.audit(data)
    def report(self):
        r=dict.fromkeys(q.FIELDS,0);mask=15;r.update(version=1,attempted=1,held=1,complete=1,phase=9,domain=0xffff800000010000,count=4,root=0x400000,frame=0x10000000,
          free_before=880,free_held=879,window_a=q.A,window_b=q.B,warm_write_mask=mask,exec42_mask=mask,exec43_mask=mask,write_denied_mask=mask,exec_sealed=1,wc_sealed=1,wc_complete=1,
          framebuffer=0x80000000,framebuffer_pages=2,pat_before=0x0007040600070406,pat_after=0x0007040100070406,mtrr_checks=16)
        return r
    def test_completed_readbacks_cannot_hide_missing_or_failed_cpu(self):
        good=self.report();q.validate_report(good,4)
        for key,value in [('exec42_mask',7),('exec43_mask',7),('write_denied_mask',7),('warm_write_mask',7),('pat_after',good['pat_before']),('mtrr_checks',15),('held',0),('wc_complete',0),('complete',0),('error_code',7)]:
            bad=copy.deepcopy(good);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):q.validate_report(bad,4)
    def test_semantic_negatives_require_their_exact_failure(self):
        ex=self.report();ex.update(complete=0,phase=3,error_code=0x06120003,write_denied_mask=1,exec_sealed=0,exec42_mask=0);q.validate_report(ex,4,'exec')
        for key,value in [('phase',4),('write_denied_mask',15),('error_code',1)]:
            bad=dict(ex);bad[key]=value
            with self.assertRaises(ValueError):q.validate_report(bad,4,'exec')
        pat=self.report();pat.update(complete=0,phase=8,wc_phase=4,error_code=7,wc_complete=0,wc_sealed=0);q.validate_report(pat,4,'pat')
        for key,value in [('error_code',8),('phase',4),('wc_complete',1)]:
            bad=dict(pat);bad[key]=value
            with self.assertRaises(ValueError):q.validate_report(bad,4,'pat')
if __name__=='__main__':unittest.main()
