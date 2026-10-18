"""Independent target representation checks for enum/optional/result values."""
from __future__ import annotations

import unittest

from lang.dongc.frontend import Parser, lex
from lang.dongc.model import CompileError
from lang.dongc.typesys import TypeSystem


def types(source=""):
    return TypeSystem(Parser(lex("module layout; " + source)).parse())


class L1LayoutTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(CompileError) as caught:
            types(source)
        self.assertEqual(code, caught.exception.code, caught.exception.message)

    def test_plain_enum_is_u64_and_payload_enum_is_pair(self):
        system = types("enum Mode{Off,On,Busy}enum Event{Timer,Key(u8),Shutdown}")
        self.assertEqual((8, 8, False, True), (system.layout("Mode").size, system.layout("Mode").alignment, system.is_pair("Mode"), system.is_scalar("Mode")))
        self.assertEqual((16, 8, True, False), (system.layout("Event").size, system.layout("Event").alignment, system.is_pair("Event"), system.is_scalar("Event")))
        self.assertTrue(system.is_aggregate("Event"))
        self.assertFalse(system.is_aggregate("Mode"))

    def test_all_optional_and_result_scalar_payloads_have_two_eightbyte_slots(self):
        system = types()
        for payload in ("bool", "*u8", "*const u64", "fn(u8)noreturn", *(f"{sign}{width}" for sign in "iu" for width in (8, 16, 32, 64))):
            for prefix in ("?", "!"):
                typ = prefix + payload
                with self.subTest(typ=typ):
                    layout = system.layout(typ)
                    self.assertEqual((16, 8), (layout.size, layout.alignment))
                    self.assertTrue(system.is_pair(typ))
                    self.assertEqual(payload, system.payload(typ))
        self.assertEqual((16, 8), (system.layout("!void").size, system.layout("!void").alignment))

    def test_pair_fields_arrays_and_packed_offsets_use_real_layouts(self):
        system = types("enum Plain{A,B}enum Event{A,B(i16)}struct S{tag:u8,opt:?u8,result:!void,event:Event,plain:Plain}packed struct P{tag:u8,value:?u16}")
        layout = system.layout("S")
        self.assertEqual((64, 8), (layout.size, layout.alignment))
        self.assertEqual([0, 8, 24, 40, 56], [field.offset for field in layout.fields.values()])
        self.assertEqual((17, 1, 1), (system.layout("P").size, system.layout("P").alignment, system.layout("P").fields["value"].offset))
        self.assertEqual(48, system.layout("[3]?u8").size)

    def test_optional_and_result_payloads_do_not_nest_or_accept_aggregates(self):
        for typ in ("??u8", "?!u8", "!?u8", "!!u8", "?[]u8", "![2]u8", "?void", "!noreturn"):
            with self.subTest(typ=typ), self.assertRaises(CompileError) as caught:
                types().layout(typ)
            self.assertEqual("E0302", caught.exception.code)
        self.assert_error("struct S{value:u8}struct Holder{value:?S}", "E0302")
        self.assert_error("enum E{A,B}struct Holder{value:!E}", "E0302")

    def test_enum_payload_restrictions_and_duplicate_variants(self):
        for payload in ("[2]u8", "[]u8", "?u8", "!u8", "E"):
            with self.subTest(payload=payload):
                self.assert_error(f"enum E{{A({payload})}}", "E0302")
        self.assert_error("enum E{}", "E0302")
        self.assert_error("enum E{A,A(u8)}", "E0201")
        self.assert_error("struct E{x:u8}enum E{A}", "E0201")

    def test_enum_pointer_and_function_pointer_payloads_break_recursion(self):
        system = types("enum Event{Next(*Event),Handler(fn(Event)void),Stop}struct Node{event:Event,next:*Node}")
        self.assertEqual((16, 24), (system.layout("Event").size, system.layout("Node").size))

    def test_unknown_or_nonstorable_targets_remain_invalid(self):
        for typ, code in (("?*Missing", "E0301"), ("!*void", "E0302"), ("?fn(*Missing)void", "E0301")):
            with self.subTest(typ=typ), self.assertRaises(CompileError) as caught:
                types().layout(typ)
            self.assertEqual(code, caught.exception.code)
        for typ in ("void", "noreturn", "*noreturn", "[]noreturn"):
            with self.subTest(typ=typ), self.assertRaises(CompileError) as caught:
                types().layout(typ)
            self.assertEqual("E0302", caught.exception.code)

    def test_pair_function_signatures_are_sysv_and_scalar_enums_work_in_win64(self):
        system = types("enum Plain{A,B}enum Payload{A(u8),B}")
        for typ in ("fn(?u8,!void,Payload)Payload", 'extern "win64" fn(Plain)Plain', "fn()noreturn"):
            with self.subTest(typ=typ):
                self.assertEqual((8, 8), (system.layout(typ).size, system.layout(typ).alignment))
        for typ in ('extern "win64" fn(?u8)void', 'extern "win64" fn()!void', 'extern "win64" fn(Payload)void'):
            with self.subTest(typ=typ), self.assertRaises(CompileError) as caught:
                system.layout(typ)
            self.assertEqual("E0601", caught.exception.code)

    def test_enum_manifest_has_public_identity_variant_tags_and_payload_slots(self):
        system = types("pub enum Mode{Off,On}pub enum Event{Timer,Key(i8),Callback(fn()void)}")
        entries = {item["name"]: item for item in system.manifest()["types"]}
        mode, event = entries["Mode"], entries["Event"]
        self.assertEqual(("layout.Mode", "enum", "scalar"), (mode["full_name"], mode["kind"], mode["representation"]))
        self.assertEqual([(0, None), (1, None)], [(item["tag"], item["payload"]) for item in mode["variants"]])
        self.assertEqual([0, 8], [item["offset"] for item in event["fields"]])
        self.assertEqual([("Timer", 0, None), ("Key", 1, "i8"), ("Callback", 2, "fn()void")], [(item["name"], item["tag"], item["payload"]) for item in event["variants"]])


if __name__ == "__main__":
    unittest.main()
