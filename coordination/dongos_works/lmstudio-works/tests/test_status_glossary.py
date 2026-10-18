"""Codex-owned structural gate for the small LM3 status glossary."""
import json
from pathlib import Path
import unittest


class StatusGlossaryTests(unittest.TestCase):
    def test_schema_states_labels_and_short_chinese(self):
        value=json.loads((Path(__file__).resolve().parents[1]/'docs/task-status.zh-CN.json').read_text(encoding='utf-8'))
        self.assertEqual(set(value),{'version','items'})
        self.assertIs(type(value['version']),int)
        self.assertEqual(value['version'],1)
        expected=[('todo','待领取'),('in_progress','进行中'),('submitted','待复验'),
                  ('rework','返修'),('accepted','已验收'),('integrated','已集成'),('paused','暂停')]
        self.assertIsInstance(value['items'],list)
        self.assertEqual([(x['state'],x['label']) for x in value['items']],expected)
        for item in value['items']:
            self.assertEqual(set(item),{'state','label','description'})
            self.assertIsInstance(item['description'],str)
            self.assertTrue(1<=len(item['description'])<=30)
            self.assertTrue(any('\u4e00'<=c<='\u9fff' for c in item['description']))


if __name__=='__main__':unittest.main()
