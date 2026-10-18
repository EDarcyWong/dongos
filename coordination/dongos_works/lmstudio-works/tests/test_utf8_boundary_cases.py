"""Codex-owned UTF-8 fixture validation using the host's strict decoder."""
import json
from pathlib import Path
import unittest


class Utf8BoundaryCasesTests(unittest.TestCase):
    def test_small_fixed_corpus_against_strict_decoder(self):
        data=json.loads((Path(__file__).resolve().parents[1]/'fixtures/utf8-boundary-cases.json').read_text(encoding='utf-8'))
        self.assertEqual(set(data),{'version','cases'})
        self.assertIs(type(data['version']),int)
        self.assertEqual(data['version'],1)
        expected=[('empty',''),('nul','00'),('ascii','41'),('han','e6b189'),('emoji','f09f9880'),('max','f48fbfbf'),
                  ('overlong','c0af'),('continuation','80'),('surrogate','eda080'),('too_high','f4908080'),
                  ('truncated','e282'),('bad_continuation','e228a1')]
        self.assertIsInstance(data['cases'],list)
        self.assertEqual([(x['id'],x['hex']) for x in data['cases']],expected)
        for item in data['cases']:
            self.assertEqual(set(item),{'id','hex','valid','scalar_count'})
            self.assertIs(type(item['valid']),bool)
            try:decoded=bytes.fromhex(item['hex']).decode('utf-8',errors='strict')
            except UnicodeDecodeError:
                self.assertFalse(item['valid'])
                self.assertIsNone(item['scalar_count'])
            else:
                self.assertTrue(item['valid'])
                self.assertIs(type(item['scalar_count']),int)
                self.assertEqual(item['scalar_count'],len(decoded))


if __name__=='__main__':unittest.main()
