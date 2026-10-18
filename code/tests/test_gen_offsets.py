import copy
import unittest

from tools.gen_offsets import generate


class OffsetExportTests(unittest.TestCase):
    manifest = {"schema": 1, "target": "x86_64-dongos-elf", "types": [
        {"name": "Record", "full_name": "test.Record", "kind": "struct", "size": 16, "alignment": 8,
         "fields": [{"name": "tag", "type": "u8", "offset": 0, "size": 1},
                    {"name": "value", "type": "u64", "offset": 8, "size": 8}]}]}

    def test_padding_comes_from_layout(self):
        result = generate(self.manifest, "test.Record")
        self.assertIn(".tag: resb 1\n    resb 7\n    .value: resb 8", result)

    def test_overlapping_field_rejected(self):
        data = copy.deepcopy(self.manifest)
        data["types"][0]["fields"][1]["offset"] = 0
        with self.assertRaises(ValueError):
            generate(data, "Record")

    def test_injected_identifier_rejected(self):
        data = copy.deepcopy(self.manifest)
        data["types"][0]["fields"][0]["name"] = "x\nsection .text"
        with self.assertRaises(ValueError):
            generate(data, "Record")

    def test_duplicate_type_rejected(self):
        data = copy.deepcopy(self.manifest)
        data["types"].append(data["types"][0])
        with self.assertRaises(ValueError):
            generate(data, "Record")
