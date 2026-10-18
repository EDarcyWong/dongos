"""Codex-owned independent data gate for LM7. No generated code is executed."""
import json
from pathlib import Path
import unittest

VECTORS=[('u8_zero',8,False,0),('u8_max',8,False,255),('i8_min',8,True,128),
         ('u32_max',32,False,2**32-1),('i32_min',32,True,2**31),
         ('u64_max',64,False,2**64-1),('i64_min',64,True,2**63),('i64_minus1',64,True,2**64-1)]


class DecimalVectorsTests(unittest.TestCase):
    def validate(self,data):
        self.assertIs(type(data),dict)
        self.assertEqual(set(data),{'version','cases'})
        self.assertIs(type(data['version']),int)
        self.assertEqual(data['version'],1)
        self.assertIs(type(data['cases']),list)
        self.assertEqual(len(data['cases']),len(VECTORS))
        for item,(ident,width,signed,raw) in zip(data['cases'],VECTORS):
            self.assertIs(type(item),dict)
            self.assertEqual(set(item),{'id','width','signed','raw','text'})
            self.assertEqual(item['id'],ident)
            self.assertIs(type(item['width']),int)
            self.assertEqual(item['width'],width)
            self.assertIs(type(item['signed']),bool)
            self.assertEqual(item['signed'],signed)
            self.assertIs(type(item['raw']),str)
            self.assertEqual(item['raw'],str(raw))
            self.assertIs(type(item['text']),str)
            value=raw-(1<<width) if signed and raw>=(1<<(width-1)) else raw
            self.assertEqual(item['text'],str(value))

    def test_fixed_vectors_with_independent_integer_interpretation(self):
        path=Path(__file__).resolve().parent/'fixtures/decimal-known-vectors.json'
        self.validate(json.loads(path.read_text(encoding='utf-8')))


if __name__=='__main__':unittest.main()
