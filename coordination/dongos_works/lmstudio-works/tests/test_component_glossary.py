"""Codex-owned structural checks for the LM4 component navigation document."""
import json
from pathlib import Path
import unittest


class ComponentGlossaryTests(unittest.TestCase):
    def test_fixed_modules_source_paths_and_short_chinese(self):
        value=json.loads((Path(__file__).resolve().parents[1]/'docs/bootstrap-components.zh-CN.json').read_text(encoding='utf-8'))
        names=['cfg_reachability','sysv_integer_args','parallel_moves','stack_slots','switch_cases','cleanup_plan','nasm_bytes']
        self.assertEqual(set(value),{'version','items'})
        self.assertIs(type(value['version']),int)
        self.assertEqual(value['version'],1)
        self.assertIsInstance(value['items'],list)
        self.assertEqual([x['module'] for x in value['items']],['bootstrap.'+n for n in names])
        for name,item in zip(names,value['items']):
            self.assertEqual(set(item),{'module','title','summary','source'})
            self.assertEqual(item['source'],'lang/bootstrap/'+name+'.dg')
            for field,limit in [('title',16),('summary',48)]:
                self.assertIsInstance(item[field],str)
                self.assertTrue(1<=len(item[field])<=limit)
                self.assertTrue(any('\u4e00'<=c<='\u9fff' for c in item[field]))


if __name__=='__main__':unittest.main()
