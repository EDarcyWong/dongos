"""Independent fixed-data gate for LM6; no model-generated implementation is executed."""
import json,re
from pathlib import Path
import unittest


class Leb128VectorsTests(unittest.TestCase):
    def test_fixed_vectors_and_independent_integer_encoding(self):
        data=json.loads((Path(__file__).resolve().parents[1]/'fixtures/leb128-known-vectors.json').read_text(encoding='utf-8'))
        vectors=[('u0',False,0),('u127',False,127),('u128',False,128),('u624485',False,624485),
                 ('u64_max',False,2**64-1),('s0',True,0),('s_minus1',True,-1),('s63',True,63),
                 ('s64',True,64),('s_minus64',True,-64),('s_minus65',True,-65),('s_minus123456',True,-123456)]
        self.assertEqual(set(data),{'version','cases'})
        self.assertIs(type(data['version']),int);self.assertEqual(data['version'],1)
        self.assertIsInstance(data['cases'],list)
        self.assertEqual([x['id'] for x in data['cases']],[x[0] for x in vectors])
        for item,(ident,signed,value) in zip(data['cases'],vectors):
            self.assertEqual(set(item),{'id','signed','value','hex'})
            self.assertIs(type(item['signed']),bool);self.assertEqual(item['signed'],signed)
            self.assertIsInstance(item['value'],str);self.assertRegex(item['value'],r'^(0|-?[1-9][0-9]*)$')
            self.assertEqual(int(item['value']),value)
            encoded=[];remaining=value
            while True:
                part=remaining%128;remaining//=128
                done=(remaining==0 and (not signed or part<64)) or (signed and remaining==-1 and part>=64)
                encoded.append(part if done else part+128)
                if done:break
            self.assertEqual(item['hex'],bytes(encoded).hex())


if __name__=='__main__':unittest.main()
