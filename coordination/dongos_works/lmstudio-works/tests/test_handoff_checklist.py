"""Codex-owned structural checks for the small LM2 documentation task."""
import json
from pathlib import Path
import unittest


class ChecklistTests(unittest.TestCase):
    def test_fixed_schema_and_bounded_chinese_text(self):
        source=Path(__file__).resolve().parents[1]/'docs/handoff-checklist.zh-CN.json'
        value=json.loads(source.read_text(encoding='utf-8'))
        self.assertEqual(set(value),{'version','items'})
        self.assertEqual(type(value['version']),int)
        self.assertEqual(value['version'],1)
        self.assertIsInstance(value['items'],list)
        self.assertEqual([x['id'] for x in value['items']],['scope','claim','test','delivery','review'])
        for item in value['items']:
            self.assertEqual(set(item),{'id','title','description'})
            for field,limit in [('title',12),('description',40)]:
                self.assertIsInstance(item[field],str)
                self.assertTrue(1<=len(item[field])<=limit)
                self.assertTrue(any('\u4e00'<=c<='\u9fff' for c in item[field]))


if __name__=='__main__':unittest.main()
