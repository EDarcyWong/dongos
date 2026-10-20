"""CI partition must preserve every test exactly once, without empty shards."""
import unittest
from tools.ci_unittest import partition

class InventoryTests(unittest.TestCase):
    def test_exact_coverage_and_module_locality(self):
        ids = ['test_a.A.test_1','test_a.A.test_2','test_b.B.test_1','test_c.C.test_1']
        shards = partition(ids,2)
        self.assertEqual(sorted(ids),sorted(x for s in shards for x in s))
        self.assertEqual(2,len(shards));self.assertTrue(all(shards))
        self.assertEqual(shards,partition(ids,2))
        self.assertTrue(all(x in shards[0] for x in ids[:2]))
    def test_invalid_inventory_is_not_a_silent_pass(self):
        for ids,count in [([],1),(['test_a.A.test_1']*2,1),(['test_a.A.test_1'],2),(['test_a.A.test_1'],0)]:
            with self.subTest(ids=ids,count=count),self.assertRaises(ValueError):partition(ids,count)
