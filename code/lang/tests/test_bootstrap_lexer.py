"""Run the actual Dong bootstrap lexer through an independent C/SysV boundary.

No OS image or VM is built. Inputs, native artifacts and results remain under
build/test/bootstrap-lexer so a failure never becomes a missing evidence file.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import random
import re
import struct
import subprocess
import unittest
import uuid

from lang.dongc import CompileError, compile_file
from lang.dongc.frontend import lex
from lang.dongc.model import KEYWORDS
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[2]
KEYWORD_ORDER = "module import as pub const let var type struct enum fn extern unsafe packed align export if else while loop for in match break continue return defer try error orelse true false null void noreturn asm".split()
MULTI = ["<<=", ">>=", "==", "!=", "<=", ">=", "&&", "||", "<<", ">>", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "..", "=>"]
KINDS = {"eof": 0, "identifier": 1, "integer": 2, "string": 3}
KINDS.update((word, 256 + i) for i, word in enumerate(KEYWORD_ORDER))
KINDS.update((word, 512 + i) for i, word in enumerate(MULTI))
KINDS.update((word, 1024 + ord(word)) for word in "{}()[];,:.+-*/%&|^~!<>=?")
ERRORS = {
    "unterminated block comment": 2,
    "newline in string literal": 3,
    "unterminated string literal": 4,
    "expected two hexadecimal digits after \\x": 5,
    "invalid string escape": 6,
    "invalid integer literal": 7,
}

HARNESS = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define DG __attribute__((sysv_abi))
typedef struct {uint64_t kind,start,end,line,column,value_start,value_length;} Token;
typedef struct {uint64_t count,used,error_code,error_start,error_line,error_column;} Result;
_Static_assert(sizeof(Token)==56,"Dong Token layout");
_Static_assert(sizeof(Result)==48,"Dong Result layout");
extern uint64_t DG dong_bootstrap_lex(const uint8_t*,uint64_t,Token*,uint64_t,uint8_t*,uint64_t,Result*);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
 fprintf(stderr,"unexpected Dong panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,file);exit(86);
}
static void read_exact(void *p,size_t n){if(n&&fread(p,1,n,stdin)!=n)exit(90);}
static void write_exact(const void *p,size_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(91);}
static int filled(const uint8_t *p,size_t n){size_t i;for(i=0;i<n;i++)if(p[i]!=0xa5)return 0;return 1;}
static void invalid_arguments(void){
 _Alignas(8) uint8_t storage[512],before[512];uint8_t source[3]={'a','b','c'};
 Token *tokens=(Token*)(storage+64);uint8_t *arena=storage+256;Result *out=(Result*)(storage+384);
 uint64_t code;size_t i;
 for(i=0;i<10;i++){
  memset(storage,0xa5,sizeof(storage));memcpy(before,storage,sizeof(storage));
  switch(i){
   case 0:code=dong_bootstrap_lex(NULL,1,tokens,2,arena,32,out);break;
   case 1:code=dong_bootstrap_lex(source,3,NULL,2,arena,32,out);break;
   case 2:code=dong_bootstrap_lex(source,3,tokens,2,NULL,32,out);break;
   case 3:code=dong_bootstrap_lex(source,3,tokens,2,arena,32,NULL);break;
   case 4:code=dong_bootstrap_lex(source,3,tokens,UINT64_MAX,arena,32,out);break;
   case 5:code=dong_bootstrap_lex((const uint8_t*)(uintptr_t)UINT64_MAX,1,tokens,2,arena,32,out);break;
   case 6:code=dong_bootstrap_lex(source,3,tokens,2,arena,32,(Result*)tokens);break;
   case 7:code=dong_bootstrap_lex(source,3,(Token*)((uint8_t*)tokens+1),2,arena,32,out);break;
   case 8:code=dong_bootstrap_lex(source,3,tokens,2,arena,32,(Result*)((uint8_t*)out+1));break;
   default:code=dong_bootstrap_lex(source,3,tokens,2,(uint8_t*)tokens+8,32,out);break;
  }
  if(code!=11||memcmp(before,storage,sizeof(storage))){fprintf(stderr,"invalid argument %u mutated output or returned %u\n",(unsigned)i,(unsigned)code);exit(92);}
 }
}
int main(void){
 uint64_t cases,at;
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 invalid_arguments();read_exact(&cases,8);
 for(at=0;at<cases;at++){
  uint64_t length,capacity,bytes,status,guard;uint8_t *raw,*copy,*token_mem,*string_mem,*result_mem;Token *tokens;Result *out;
  read_exact(&length,8);read_exact(&capacity,8);read_exact(&bytes,8);
  if(length>8000000||capacity>8000000||bytes>8000000)exit(93);
  raw=malloc((size_t)length+64);copy=malloc((size_t)length+1);
  token_mem=malloc((size_t)capacity*56+64);string_mem=malloc((size_t)bytes+64);result_mem=malloc(112);
  if(!raw||!copy||!token_mem||!string_mem||!result_mem)exit(94);
  memset(raw,0xa5,(size_t)length+64);memset(token_mem,0xa5,(size_t)capacity*56+64);
  memset(string_mem,0xa5,(size_t)bytes+64);memset(result_mem,0xa5,112);
  read_exact(raw+32,(size_t)length);memcpy(copy,raw+32,(size_t)length);
  tokens=(Token*)(token_mem+32);out=(Result*)(result_mem+32);
  status=dong_bootstrap_lex(raw+32,length,tokens,capacity,string_mem+32,bytes,out);
  guard=(uint64_t)(filled(raw,32)&&filled(raw+32+length,32)&&!memcmp(copy,raw+32,(size_t)length)
   &&filled(token_mem,32)&&filled(token_mem+32+capacity*56,32)
   &&filled(string_mem,32)&&filled(string_mem+32+bytes,32)&&filled(result_mem,32)&&filled(result_mem+80,32));
  if(out->count>capacity||out->used>bytes)exit(95);
  /* Unpublished tokens must never be partially written. Unpublished string
     bytes within the arena may contain a failed string's private prefix. */
  guard=guard&&(uint64_t)filled(token_mem+32+out->count*56,(size_t)(capacity-out->count)*56);
  write_exact(&status,8);write_exact(&guard,8);write_exact(out,48);
  write_exact(tokens,(size_t)out->count*56);write_exact(string_mem+32,(size_t)out->used);
  free(raw);free(copy);free(token_mem);free(string_mem);free(result_mem);
 }
 if(fgetc(stdin)!=EOF){exit(96);}
 return 0;
}
'''


def byte_position(source: str, line: int, column: int) -> int:
    actual_line, actual_column, offset = 1, 1, 0
    for char in source:
        if (actual_line, actual_column) == (line, column):
            return offset
        offset += len(char.encode("utf-8"))
        if char == "\n":
            actual_line, actual_column = actual_line + 1, 1
        else:
            actual_column += 1
    if (actual_line, actual_column) != (line, column):
        raise AssertionError((line, column, actual_line, actual_column))
    return offset


def reference(source: bytes):
    text = source.decode("utf-8")
    # Build positions once; scanning the whole source per token would turn the
    # large real-module corpus into a quadratic host-side oracle.
    positions = {}
    line, column, offset = 1, 1, 0
    for char in text:
        positions[line, column] = offset
        offset += len(char.encode("utf-8"))
        if char == "\n":
            line, column = line + 1, 1
        else:
            column += 1
    positions[line, column] = offset
    try:
        tokens = lex(text)
    except CompileError as error:
        assert error.code == "E0001", error
        code = ERRORS.get(error.message, 8 if error.message.startswith("invalid character ") else None)
        assert code is not None, error.message
        return dict(status=code, location=(positions[error.token.line, error.token.column], error.token.line, error.token.column))
    expected, strings = [], bytearray()
    for token in tokens:
        start = positions[token.line, token.column]
        value_start = value_length = 0
        if token.kind == "eof":
            end = start
        elif token.kind == "string":
            i = start + 1
            while i < len(source):
                if source[i] == 34:
                    break
                if source[i] == 92:
                    i += 1
                i += 1
            end = i + 1
            value = token.value.encode("latin-1")
            value_start, value_length = len(strings), len(value)
            strings.extend(value)
        else:
            end = start + len(token.value.encode("utf-8"))
        expected.append((KINDS[token.kind], start, end, token.line, token.column, value_start, value_length))
    return dict(status=0, tokens=expected, strings=bytes(strings))


class BootstrapLexerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest("Dong bootstrap lexer execution requires NASM and GCC")
        cls.directory = ROOT / "build/test/bootstrap-lexer" / ("run-" + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        (cls.directory / "probe.c").write_text(HARNESS, encoding="utf-8")
        cls.executables = {mode: cls.build(mode) for mode in ("debug", "release")}
        cls.records = []

    @classmethod
    def tearDownClass(cls):
        manifest = {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (ROOT / "lang/bootstrap/lexer.dg", ROOT / "lang/bootstrap/unicode.dg", ROOT / "lang/bootstrap/gen_unicode.py", Path(__file__))}
        artifacts = {str(path.relative_to(cls.directory)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in cls.directory.rglob("*") if path.is_file() and path.name != "summary.json"}
        (cls.directory / "summary.json").write_text(json.dumps(dict(kind="Dong-native-bootstrap-lexer", source_sha256=manifest, artifact_sha256=artifacts, modes=list(cls.executables), records=cls.records, OS_VM_built=False, L3_selfhost_complete=False), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def build(cls, mode, source_root=None, label=None):
        source_root = source_root or ROOT / "lang"
        label = label or mode
        compiled = compile_file(source_root / "bootstrap/lexer.dg", roots=[source_root], mode=mode)
        assembly = cls.directory / (label + ".asm")
        obj = cls.directory / (label + ".o")
        executable = cls.directory / (label + (".exe" if os.name == "nt" else ""))
        assembly.write_text(compiled.assembly, encoding="utf-8")
        cls.command([cls.nasm, "-f", "win64" if os.name == "nt" else "elf64", *nasm_flags(cls.nasm), "-o", str(obj), str(assembly)], label + "-assemble")
        cls.command([cls.cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", *([] if os.name == "nt" else ["-no-pie"]), str(cls.directory / "probe.c"), str(obj), "-o", str(executable)], label + "-link")
        return executable

    @classmethod
    def command(cls, args, label):
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
        (cls.directory / (label + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise AssertionError((args, result.returncode, result.stdout, result.stderr))

    @classmethod
    def run_cases(cls, executable, cases, label):
        payload = bytearray(struct.pack("<Q", len(cases)))
        for source, capacity, arena in cases:
            payload.extend(struct.pack("<QQQ", len(source), capacity, arena))
            payload.extend(source)
        (cls.directory / (label + ".input")).write_bytes(payload)
        process = subprocess.run([str(executable)], input=payload, capture_output=True, timeout=120)
        (cls.directory / (label + ".output")).write_bytes(process.stdout)
        (cls.directory / (label + ".stderr")).write_bytes(process.stderr)
        if process.returncode:
            raise AssertionError((label, process.returncode, process.stderr.decode(errors="replace")))
        result, at = [], 0
        for _ in cases:
            header = struct.unpack_from("<8Q", process.stdout, at)
            at += 64
            status, guard, count, used, code, start, line, column = header
            tokens = [struct.unpack_from("<7Q", process.stdout, at + i * 56) for i in range(count)]
            at += count * 56
            strings = process.stdout[at:at + used]
            at += used
            if guard != 1:
                raise AssertionError((label, "output/source guard or unpublished token modified"))
            if status != code:
                raise AssertionError((label, "status/result disagree", header))
            # Result.used publishes exactly the arena bytes owned by completed
            # STRING tokens. A merely correct byte prefix can still expose part
            # of an unfinished string after a capacity/lexical failure.
            published = 0
            for token in tokens:
                if token[0] == KINDS["string"]:
                    if token[5] != published or token[6] > used - published:
                        raise AssertionError((label, "published STRING prefix is not contiguous", header, token))
                    published += token[6]
            if published != used or len(strings) != used:
                raise AssertionError((label, "published STRING prefix disagrees with Result.used", header, published))
            result.append(dict(status=status, count=count, used=used, location=(start, line, column), tokens=tokens, strings=strings))
        if at != len(process.stdout):
            raise AssertionError((label, at, len(process.stdout)))
        return result

    def differential(self, sources, label, executable=None):
        expected = [reference(source) for source in sources]
        cases = [(source, len(source) + 1, len(source)) for source in sources]
        modes = [("mutation", executable)] if executable else self.executables.items()
        for mode, native in modes:
            results = self.run_cases(native, cases, label + "-" + mode)
            for index, (want, got) in enumerate(zip(expected, results)):
                context = (label, mode, index, sources[index][:160])
                self.assertEqual(want["status"], got["status"], context)
                if want["status"]:
                    self.assertEqual(want["location"], got["location"], context)
                else:
                    self.assertEqual(want["tokens"], got["tokens"], context)
                    self.assertEqual(want["strings"], got["strings"], context)
                    self.assertEqual((0, 0, 0), got["location"], context)
        if not executable:
            self.records.append(dict(label=label, cases=len(sources), modes=2, passed=True))

    def test_frozen_unicode_properties(self):
        import unicodedata
        self.assertEqual("15.0.0", unicodedata.unidata_version)
        result = subprocess.run([os.sys.executable, str(ROOT / "lang/bootstrap/gen_unicode.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(set(KEYWORD_ORDER), KEYWORDS)
        content = (ROOT / "lang/bootstrap/unicode.dg").read_text(encoding="utf-8")
        self.assertNotIn('extern "', content)
        self.assertNotIn("var ", content.split("fn contains", 1)[0])
        self.records.append(dict(label="frozen-unicode-all-1114112-codepoints-four-properties", passed=True))

    def test_all_production_dong_sources(self):
        paths = sorted(path for tree in ("kernel", "services", "lang") for path in (ROOT / tree).rglob("*.dg")
                       if path.relative_to(ROOT).as_posix() != 'lang/bootstrap/source_position.dg')
        self.assertGreater(len(paths), 180)
        sources = [path.read_bytes() for path in paths]
        corpus_manifest = {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(source).hexdigest() for path, source in zip(paths, sources)}
        (self.directory / "corpus-sha256.json").write_text(json.dumps(corpus_manifest, indent=2) + "\n", encoding="utf-8")
        self.differential([source.removeprefix(b"\xef\xbb\xbf") for source in sources], "all-production-Dong")

    def test_keywords_operators_comments_strings_and_positions(self):
        inputs = [
            " ".join(KEYWORD_ORDER + MULTI + list("{}()[];,:.+-*/%&|^~!<>=?")),
            '// 中文\r\nmodule 测试; /* 多\n行 */ fn 计算(输入:u64)u64{return 输入;}',
            '_ _a a0 变量 a\u0301 Ⅻ ² 0 01 0x0 0xffff_ffff 0b10_01 2_000',
            '"" "中文🌐" "a\\n\\r\\t\\0\\\\\\\"\\x00\\x7f\\x80\\xff"',
            '//tail', '/* a /* b */ c', 'a\rb\r\nc\nd\u2028e\v\ff',
            '"\\x41A" "escaped\\\"quote" "literal\u0085space"',
            'x//comment\r\n+=\n y/*next*/z',
            '1234567890' * 1000,
            '\ufeffmodule x;',
        ]
        self.differential([source.encode() for source in inputs], "syntax-and-position")

    def test_lexical_errors_match_reference_positions(self):
        bad = ['0x_1', '1_', '1__2', '0b2', '12u64', '@', '/*', '"bad\\q"', '"bad\n"', '"bad\r"', '"bad\\x0"', '"unterminated', '"trailing\\', '"\\xGG"', '"\\x０1"', '0Xff', '0b', '0x', '1²', '1中文', '\u0301', '中文\r\n  "中\\q"', '"x" /* unterminated', "a 'b'", '\x00', 'a\n\r@']
        self.differential([source.encode() for source in bad], "lexical-errors")

    def test_unicode_boundaries_and_deterministic_random_corpus(self):
        module = (ROOT / "lang/bootstrap/unicode.dg").read_text(encoding="utf-8")
        cps = {0, 9, 10, 13, 32, 127, 128, 0x7ff, 0x800, 0xffff, 0x10000, 0x10ffff}
        for encoded in re.findall(r"0x[0-9a-f]+", module.split("fn contains", 1)[0]):
            value = int(encoded, 16)
            for boundary in (value >> 21, value & 0x1fffff):
                cps.update(cp for cp in (boundary - 1, boundary, boundary + 1) if 0 <= cp <= 0x10ffff and not 0xd800 <= cp <= 0xdfff)
        randomizer = random.Random(0xD06C)
        cps.update(randomizer.randrange(0x110000) for _ in range(1200))
        cps = sorted(cp for cp in cps if not 0xd800 <= cp <= 0xdfff)
        sources = []
        for cp in cps:
            char = chr(cp)
            sources.extend((char.encode(), ("a" + char + "b").encode(), ("0" + char).encode()))
        self.differential(sources, "unicode-boundaries")

    def test_utf8_invalid_ranges_truncation_and_error_location(self):
        invalid = [b"\x80", b"\xbf", b"\xc0\x80", b"\xc1\xbf", b"\xc2", b"\xdf\x7f", b"\xe0\x80\x80", b"\xed\xa0\x80", b"\xe2\x82", b"\xf0\x80\x80\x80", b"\xf4\x90\x80\x80", b"\xf5\x80\x80\x80", b"\xff", b"\xe2A\x80"]
        sources = [prefix + source for prefix in (b"", "中\r\n  a".encode(), b"@ ") for source in invalid]
        for mode, executable in self.executables.items():
            results = self.run_cases(executable, [(source, 20, 100) for source in sources], "invalid-UTF8-" + mode)
            for source, got in zip(sources, results):
                with self.assertRaises(UnicodeDecodeError) as caught:
                    source.decode("utf-8")
                at = caught.exception.start
                prefix = source[:at].decode("utf-8")
                line = prefix.count("\n") + 1
                column = len(prefix.rsplit("\n", 1)[-1]) + 1
                self.assertEqual((1, 0, 0, (at, line, column)), (got["status"], got["count"], got["used"], got["location"]))
        self.records.append(dict(label="strict-UTF8", cases=len(sources), modes=2, passed=True))

    def test_exact_token_and_string_capacity_and_prefix_publication(self):
        sources = [b"", b"a", b"a b", b'""', b'"abc" x "z"', '"中文" "\\x00"'.encode()]
        cases, wants = [], []
        for source in sources:
            ref = reference(source)
            for token_capacity in range(len(ref["tokens"]) + 1):
                for string_capacity in range(len(ref["strings"]) + 1):
                    cases.append((source, token_capacity, string_capacity))
                    wants.append(ref)
        for mode, executable in self.executables.items():
            results = self.run_cases(executable, cases, "capacities-" + mode)
            for (source, token_capacity, string_capacity), ref, got in zip(cases, wants, results):
                context = (source, token_capacity, string_capacity, mode)
                self.assertIn(got["status"], (0, 9, 10), context)
                self.assertEqual(ref["tokens"][:got["count"]], got["tokens"], context)
                self.assertEqual(ref["strings"][:got["used"]], got["strings"], context)
                if token_capacity >= len(ref["tokens"]) and string_capacity >= len(ref["strings"]):
                    self.assertEqual(0, got["status"], context)
                else:
                    self.assertNotEqual(0, got["status"], context)
        self.records.append(dict(label="exact-capacity-guards-prefix", cases=len(cases), modes=2, invalid_argument_controls_per_native=10, passed=True))

    def test_actual_bad_implementations_are_rejected(self):
        original = (ROOT / "lang/bootstrap/lexer.dg").read_text(encoding="utf-8")
        unicode = (ROOT / "lang/bootstrap/unicode.dg").read_text(encoding="utf-8")
        controls = [
            ("integer-separator", "lexer", "return digit&&!separator;", "return digit;", b"1_"),
            ("CR-instead-LF", "lexer", "if decoded.cp==10", "if decoded.cp==13", "中\r\na".encode()),
            ("wrong-hex-byte", "lexer", "*16+hex", "*15+hex", b'"\\x41"'),
            ("overlong-UTF8", "unicode", "a>=0xc2&&a<=0xdf", "a>=0xc0&&a<=0xdf", b"\xc0\xaf"),
        ]
        for name, module, old, new, source in controls:
            staged = self.directory / name / "bootstrap"
            staged.mkdir(parents=True)
            lexer_source, unicode_source = original, unicode
            selected = lexer_source if module == "lexer" else unicode_source
            self.assertEqual(1, selected.count(old), name)
            changed = selected.replace(old, new, 1)
            if module == "lexer":
                lexer_source = changed
            else:
                unicode_source = changed
            (staged / "lexer.dg").write_text(lexer_source, encoding="utf-8")
            (staged / "unicode.dg").write_text(unicode_source, encoding="utf-8")
            executable = self.build("release", staged.parent, "bad-" + name)
            got = self.run_cases(executable, [(source, len(source) + 2, len(source))], "bad-" + name)[0]
            if name == "overlong-UTF8":
                rejected = got["status"] != 1
            else:
                want = reference(source)
                rejected = got["status"] != want["status"] or (got["location"] != want.get("location") if want["status"] else got["tokens"] != want["tokens"] or got["strings"] != want["strings"])
            self.assertTrue(rejected, "native bad implementation escaped differential oracle: " + name)
            self.records.append(dict(label="actual-bad-" + name, compiled=True, native_executed=True, rejected=True))

    def test_unfinished_string_publication_bad_source_is_rejected(self):
        original = (ROOT / "lang/bootstrap/lexer.dg").read_text(encoding="utf-8")
        unicode = (ROOT / "lang/bootstrap/unicode.dg").read_text(encoding="utf-8")
        old = "if *used>=(*s).strings.len{return reject"
        new = "if *used>=(*s).strings.len{(*s).result.used=*used;return reject"
        self.assertEqual(1, original.count(old))
        staged = self.directory / "unfinished-string-publication" / "bootstrap"
        staged.mkdir(parents=True)
        (staged / "lexer.dg").write_text(original.replace(old, new, 1), encoding="utf-8")
        (staged / "unicode.dg").write_text(unicode, encoding="utf-8")
        cases = [(b'"abc"', 4, 1), (b'"a" "bcd"', 4, 2)]
        for mode, native in self.executables.items():
            positive = self.run_cases(native, cases, "completed-string-prefix-" + mode)
            self.assertEqual([(10, 0, 0), (10, 1, 1)], [(r["status"], r["count"], r["used"]) for r in positive])
            executable = self.build(mode, staged.parent, "bad-unfinished-string-" + mode)
            for index, case in enumerate(cases):
                # run_cases first requires a successful process, valid guards
                # and status/result agreement. Only this publication invariant
                # may reject the assembled, genuinely executed bad source.
                with self.assertRaisesRegex(AssertionError, "published STRING prefix"):
                    self.run_cases(executable, [case], "bad-unfinished-string-" + mode + "-" + str(index))
            self.records.append(dict(label="actual-bad-unfinished-string-" + mode, compiled=True,
                native_executed=True, cases=len(cases), rejected_at="published STRING prefix"))


if __name__ == "__main__":
    unittest.main()
