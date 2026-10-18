"""Codex-owned independent fixed-data gate for LM8; worker cannot edit this file."""
import json
from pathlib import Path
import unittest

VECTORS=[('rax_zero',0,0),('rbp_minus8',5,-8),('rsp_plus16',4,16),
         ('r8_plus1',8,1),('r15_minus1',15,-1),('rax_min',0,-2**31),
         ('r10_max',10,2**31-1),('rcx_zero',1,0)]
REGS=('rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi',*[f'r{i}' for i in range(8,16)])

class MemoryOperandVectorsTests(unittest.TestCase):
    def validate(self,data):
        self.assertIs(type(data),dict);self.assertEqual(set(data),{'version','cases'})
        self.assertIs(type(data['version']),int);self.assertEqual(data['version'],1)
        self.assertIs(type(data['cases']),list);self.assertEqual(len(data['cases']),8)
        for item,(ident,base,disp) in zip(data['cases'],VECTORS):
            self.assertIs(type(item),dict);self.assertEqual(set(item),{'id','base','disp','text'})
            self.assertEqual(item['id'],ident);self.assertIs(type(item['base']),int)
            self.assertEqual(item['base'],base);self.assertIs(type(item['disp']),str)
            self.assertEqual(item['disp'],str(disp));self.assertIs(type(item['text']),str)
            suffix='' if disp==0 else (' + ' if disp>0 else ' - ')+str(abs(disp))
            self.assertEqual(item['text'],'['+REGS[base]+suffix+']')

    def test_fixed_known_vectors(self):
        path=Path(__file__).resolve().parent/'fixtures/memory-operand-known-vectors.json'
        self.validate(json.loads(path.read_text(encoding='utf-8')))

if __name__=='__main__':unittest.main()
