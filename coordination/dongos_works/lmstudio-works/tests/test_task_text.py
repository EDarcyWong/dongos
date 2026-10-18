"""Independent LM1 contract checks, owned by Codex. LM Studio cannot edit this."""
import importlib.util
from pathlib import Path
import random
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'src/task_text.py'


class TaskTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('lm_task_text',SOURCE)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_empty_normal_and_unicode(self):
        for value,expected in [('', ''),('  ',''),('abc','abc'),('  任务\t标签\r\n 完成  ','任务 标签 完成'),('\u3000a\u00a0b\u2003','a b')]:
            with self.subTest(value=value):self.assertEqual(self.module.collapse_whitespace(value),expected)

    def test_preserves_non_whitespace(self):
        for value in ['a-b_c:1','中文🙂é','a\x00b','a\u200bb']:
            self.assertEqual(self.module.collapse_whitespace(value),value)

    def test_non_string_rejected(self):
        for value in (None,1,[],b'abc'):
            with self.subTest(value=value),self.assertRaises(TypeError):self.module.collapse_whitespace(value)

    def test_seeded_whitespace_and_idempotence(self):
        rng=random.Random(20261018)
        for _ in range(200):
            words=[rng.choice(['abc','任务','🙂','x-y']) for _ in range(rng.randrange(1,12))]
            value=rng.choice(['',' ','\t'])+''.join(word+rng.choice([' ','\t','\r\n','\u3000']) for word in words)
            actual=self.module.collapse_whitespace(value)
            self.assertEqual(actual,' '.join(words))
            self.assertEqual(self.module.collapse_whitespace(actual),actual)


if __name__=='__main__':unittest.main()
