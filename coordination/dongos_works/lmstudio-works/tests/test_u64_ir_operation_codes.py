"""Coordinator-owned independent fixed-data gate for LM9; worker cannot edit this file."""
import json
from pathlib import Path
import unittest

CODES=[('CONST',0),('COPY',1),('ADD',2),('SUB',3),('AND',4),('OR',5),('XOR',6),('IMUL',7)]

class U64IrOperationCodesTests(unittest.TestCase):
    def validate(self,data):
        self.assertIs(type(data),dict);self.assertEqual(list(data),['version','operations'])
        self.assertIs(type(data['version']),int);self.assertEqual(data['version'],1)
        self.assertIs(type(data['operations']),list);self.assertEqual(len(data['operations']),8)
        for item,(name,code) in zip(data['operations'],CODES):
            self.assertIs(type(item),dict);self.assertEqual(list(item),['name','code'])
            self.assertIs(type(item['name']),str);self.assertEqual(item['name'],name)
            self.assertIs(type(item['code']),int);self.assertEqual(item['code'],code)

    def test_fixed_operation_codes(self):
        path=Path(__file__).resolve().parents[1]/'fixtures/u64-ir-operation-codes.json'
        self.validate(json.loads(path.read_text(encoding='utf-8')))

    def test_gate_rejects_wrong_shapes(self):
        good={'version':1,'operations':[{'name':n,'code':c} for n,c in CODES]}
        self.validate(good)
        bad=[{'version':'1','operations':good['operations']},
             {'version':1,'operations':good['operations'][:7]},
             {'version':1,'operations':[{'name':n,'code':str(c)} for n,c in CODES]},
             {'version':1,'operations':[{'code':c,'name':n} for n,c in CODES]},
             {'version':1,'operations':list(reversed(good['operations']))},
             {'version':1,'operations':good['operations'],'extra':0}]
        for item in bad:
            with self.subTest(item=item):
                with self.assertRaises(AssertionError):self.validate(item)

if __name__=='__main__':unittest.main()
