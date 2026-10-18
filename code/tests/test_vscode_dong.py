"""Consume Dong TextMate rules and compare their output with the real lexer.

The actual pinned vscode-textmate + vscode-oniguruma/WASM runtime executes
the grammar in Node; a small independent Python subset consumer adds another
cross-check. No compiler, assembler, guest, UI or network process runs.
The file works unchanged as tests/test_vscode_dong.py after promotion.
"""
from pathlib import Path
from dataclasses import dataclass
import copy
import hashlib
import importlib.util
import json
import random
import re
import shutil
import subprocess
import sys
import unittest
import uuid
import xml.etree.ElementTree as ET
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'lang/dongc/frontend.py').is_file())
EXTENSION = HERE.parent / 'editors/vscode-dong'
sys.path.insert(0, str(ROOT))
from lang.dongc.frontend import lex
from lang.dongc.model import CompileError, KEYWORDS, TYPES


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class Region:
    start: int
    end: int
    scope: str


class TextMateSubset:
    """Earliest match wins; ends win ties, as in default TextMate rules.

    All regex syntax used here is shared by Python re and Oniguruma. The
    generated grammar uses literal Unicode classes, not Python-only escapes.
    No lexer rules are supplied by this consumer: all token rules come from
    the grammar loaded by the test.
    """
    def __init__(self, grammar):
        self.grammar = grammar
        self.compiled = {}

    def regex(self, value):
        if value not in self.compiled:
            self.compiled[value] = re.compile(value, re.MULTILINE)
        return self.compiled[value]

    def expand(self, patterns, trail=()):
        for rule in patterns:
            if 'include' in rule:
                name = rule['include']
                if not name.startswith('#') or name in trail:
                    raise AssertionError('unsupported include cycle: ' + name)
                yield from self.expand([self.grammar['repository'][name[1:]]], trail + (name,))
            elif 'match' in rule or 'begin' in rule:
                yield rule
            else:
                yield from self.expand(rule.get('patterns', []), trail)

    def consume(self, source):
        stack, spans, regions = [], [], []
        position = 0

        def ancestry():
            return ('source.dong',) + tuple(r['name'] for r, _ in stack)

        def emit(a, b, scopes, captures=None, match=None):
            if a < b:
                spans.append(Span(a, b, scopes))
            if match:
                for group, value in (captures or {}).items():
                    left, right = match.span(int(group))
                    if left >= 0 and left < right:
                        spans.append(Span(left, right, scopes + (value['name'],)))

        while position < len(source):
            frame = stack[-1][0] if stack else self.grammar
            choices = []
            if stack:
                choices.append((self.regex(frame['end']), None))
            choices.extend((self.regex(rule.get('match', rule.get('begin'))), rule)
                           for rule in self.expand(frame.get('patterns', [])))
            candidates = [(regex.match(source, position), rule) for regex, rule in choices]
            candidates = [(match, rule) for match, rule in candidates if match is not None]
            if not candidates:
                candidates = [(regex.search(source, position), rule) for regex, rule in choices]
                candidates = [(match, rule) for match, rule in candidates if match is not None]
            if not candidates:
                emit(position, len(source), ancestry())
                position = len(source)
                break
            match, rule = min(enumerate(candidates), key=lambda item: (item[1][0].start(), item[0]))[1]
            if match.end() == match.start():
                raise AssertionError('zero-length grammar rule cannot make progress')
            emit(position, match.start(), ancestry())
            if rule is None:
                emit(match.start(), match.end(), ancestry(), frame.get('endCaptures'), match)
                closed, start = stack.pop()
                if not stack:
                    regions.append(Region(start, match.end(), closed['name']))
            elif 'begin' in rule:
                stack.append((rule, match.start()))
                emit(match.start(), match.end(), ancestry(), rule.get('beginCaptures'), match)
            else:
                emit(match.start(), match.end(), ancestry() + (rule['name'],), rule.get('captures'), match)
                if not stack:
                    regions.append(Region(match.start(), match.end(), rule['name']))
            position = match.end()
        return spans, sorted(regions, key=lambda r: r.start), stack


def offset(source, line, column):
    # Only LF increments the production lexer's line counter, including CRLF.
    return sum(len(part) + 1 for part in source.split('\n')[:line - 1]) + column - 1


def decoded_string(text):
    """Independent literal byte oracle, without importing lexer internals."""
    result = bytearray()
    cursor = 1
    escapes = {'n': 10, 'r': 13, 't': 9, '0': 0, '\\': 92, '"': 34}
    while cursor < len(text) - 1:
        char = text[cursor]
        if char != '\\':
            result.extend(char.encode('utf-8'))
            cursor += 1
        elif text[cursor + 1] == 'x':
            result.append(int(text[cursor + 2:cursor + 4], 16))
            cursor += 4
        else:
            result.append(escapes[text[cursor + 1]])
            cursor += 2
    return result.decode('latin-1')


def verify_consistency(grammar, source):
    spans, regions, open_frames = TextMateSubset(grammar).consume(source)
    try:
        expected = lex(source)
    except CompileError as error:
        start = offset(source, error.token.line, error.token.column)
        bad = any(s.start <= start < s.end and any(x.startswith('invalid.illegal') for x in s.scopes)
                  for s in spans)
        if error.message == 'unterminated block comment':
            bad = bool(open_frames and open_frames[0][1] == start
                       and open_frames[0][0]['name'] == 'comment.block.dong')
        if not bad:
            raise AssertionError(f'grammar accepted lexer error at {start}: {error.message}: {source!r}')
        return len(spans), len(regions), error.message
    if open_frames:
        raise AssertionError('grammar retained an open frame for valid lexer input')
    if any(any(x.startswith('invalid.illegal') for x in s.scopes) for s in spans):
        raise AssertionError(f'grammar rejected valid lexer input: {source!r}')
    actual = [r for r in regions if not r.scope.startswith(('comment.', 'meta.whitespace'))]
    expected = [t for t in expected if t.kind != 'eof']
    if len(actual) != len(expected):
        raise AssertionError(f'token count mismatch {len(actual)} != {len(expected)}: {source!r}')
    for region, token in zip(actual, expected):
        raw = source[region.start:region.end]
        if region.start != offset(source, token.line, token.column):
            raise AssertionError(f'token start mismatch at {raw!r}')
        if token.kind == 'string':
            valid = region.scope == 'string.quoted.double.dong' and decoded_string(raw) == token.value
        elif token.kind == 'integer':
            valid = region.scope.startswith('constant.numeric.integer.') and raw == token.value
        elif token.value in TYPES:
            valid = region.scope == 'storage.type.dong' and raw == token.value
        elif token.kind in KEYWORDS:
            valid = region.scope == 'keyword.control.dong' and raw == token.value
        elif token.kind == 'identifier':
            valid = region.scope == 'variable.other.dong' and raw == token.value
        else:
            valid = region.scope.startswith(('keyword.operator.', 'punctuation.')) and raw == token.value
        if not valid:
            raise AssertionError(f'token mismatch: {token!r} vs {region.scope}: {raw!r}')
    return len(spans), len(regions), None


def engine_spans(source, result):
    """Decode the engine's UTF-16 boundaries; reject splits inside surrogates."""
    utf16_to_codepoint, units = {0: 0}, 0
    for index, char in enumerate(source):
        units += 2 if ord(char) > 0xFFFF else 1
        utf16_to_codepoint[units] = index + 1
    spans = []
    for token in result['tokens']:
        if token['start'] not in utf16_to_codepoint or token['end'] not in utf16_to_codepoint:
            raise AssertionError('actual TextMate token split a surrogate pair')
        spans.append(Span(utf16_to_codepoint[token['start']], utf16_to_codepoint[token['end']], tuple(token['scopes'])))
    return spans


def token_scope(token):
    if token.kind == 'string':
        return 'string.quoted.double.dong'
    if token.kind == 'integer':
        return 'constant.numeric.integer.'
    if token.value in TYPES:
        return 'storage.type.dong'
    if token.kind in KEYWORDS:
        return 'keyword.control.dong'
    if token.kind == 'identifier':
        return 'variable.other.dong'
    return 'keyword.operator.' if token.value[0] in '+-*/%&|^~!<>=?' or token.value == '..' else 'punctuation.'


def string_end(source, start):
    cursor = start + 1
    while cursor < len(source):
        if source[cursor] == '"':
            return cursor + 1
        if source[cursor] == '\\':
            cursor += 4 if source[cursor + 1] == 'x' else 2
        else:
            cursor += 1
    raise AssertionError('valid lexer string has no closing quote')


def verify_engine(source, result):
    spans = engine_spans(source, result)
    try:
        tokens = lex(source)
    except CompileError as error:
        start = offset(source, error.token.line, error.token.column)
        if error.message == 'unterminated block comment':
            valid = not result['root'] and any(
                span.start <= start < span.end and 'comment.block.dong' in span.scopes for span in spans)
        else:
            valid = any(span.start <= start < span.end
                        and any(scope.startswith('invalid.illegal') for scope in span.scopes) for span in spans)
        if not valid:
            raise AssertionError(f'actual engine accepted lexer error at {start}: {error.message}: {source!r}')
        return 'invalid'
    if not result['root']:
        raise AssertionError('actual engine retained an open rule for valid lexer input')
    if any(any(scope.startswith('invalid.illegal') for scope in span.scopes) for span in spans):
        raise AssertionError(f'actual engine rejected valid lexer input: {source!r}')
    for token in tokens:
        if token.kind == 'eof':
            continue
        start = offset(source, token.line, token.column)
        end = string_end(source, start) if token.kind == 'string' else start + len(token.value)
        prefix = token_scope(token)
        cursor = start
        for span in spans:
            if span.end <= cursor or span.start >= end:
                continue
            if span.start > cursor or not any(scope.startswith(prefix) for scope in span.scopes):
                raise AssertionError(f'actual engine scope mismatch at {cursor}: {token!r}, {span!r}')
            cursor = max(cursor, min(span.end, end))
        if cursor != end:
            raise AssertionError(f'actual engine omitted token interval {start}:{end}')
    return 'valid'


class DongLanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grammar = json.loads((EXTENSION / 'syntaxes/dong.tmLanguage.json').read_text(encoding='utf-8'))
        cls.output = EXTENSION / '.validation' / ('run-' + uuid.uuid4().hex[:12])
        cls.output.mkdir(parents=True)
        cls.sources = [p for p in EXTENSION.rglob('*') if p.is_file()
                       and '.validation' not in p.parts and 'dist' not in p.parts and '__pycache__' not in p.parts]
        cls.sources += [Path(__file__), ROOT / 'lang/dongc/frontend.py', ROOT / 'lang/dongc/model.py', ROOT / 'lang/spec.md']
        cls.before = {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in cls.sources}
        cls.evidence = {}

    @classmethod
    def tearDownClass(cls):
        after = {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in cls.sources}
        if after != cls.before:
            raise AssertionError('syntax package or compiler inputs changed during verification')
        (cls.output / 'validation-summary.json').write_text(json.dumps({
            'source_hashes': cls.before, 'unchanged': after == cls.before,
            'compiler_or_native_build_executed': False, 'guest_executed': False,
            'network_or_install_executed': False, 'evidence': cls.evidence,
            'runtime': 'Actual bundled vscode-textmate and vscode-oniguruma/WASM plus an independent Python subset and lexer oracle.',
        }, indent=2) + '\n', encoding='utf-8')
        print('\nVS Code language evidence: ' + str(cls.output / 'validation-summary.json'))

    def verify(self, source):
        return verify_consistency(self.grammar, source)

    def test_package_contract_and_exact_generated_tables(self):
        package = json.loads((EXTENSION / 'package.json').read_text(encoding='utf-8'))
        language, = package['contributes']['languages']
        grammar, = package['contributes']['grammars']
        self.assertEqual(['.dg'], language['extensions'])
        self.assertEqual('dong', grammar['language'])
        self.assertEqual(self.grammar['scopeName'], grammar['scopeName'])
        configuration = json.loads((EXTENSION / language['configuration']).read_text(encoding='utf-8'))
        self.assertEqual(['/*', '*/'], configuration['comments']['blockComment'])
        self.assertNotIn('activationEvents', package)
        self.assertNotIn('main', package)
        spec = importlib.util.spec_from_file_location('dong_grammar_generator', EXTENSION / 'generate_grammar.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.generate(), self.grammar)
        for source, digest in self.grammar['dongContract']['sources'].items():
            self.assertEqual(digest, hashlib.sha256((ROOT / source).read_bytes()).hexdigest())
        self.evidence['contract'] = {'unicode': self.grammar['dongContract']['unicodeVersion'],
                                    'keywords': len(KEYWORDS), 'scalar_types': len(TYPES)}

    def test_real_repository_samples_and_every_keyword_type_operator(self):
        files = sorted((ROOT / 'lang/examples').rglob('*.dg')) + [
            ROOT / 'kernel/firmware/power.dg', ROOT / 'kernel/firmware/power_runtime.dg',
            ROOT / 'services/desktop/theme.dg', ROOT / 'services/desktop/preferences.dg']
        token_count = 0
        for path in files:
            with self.subTest(path=str(path.relative_to(ROOT))):
                _, count, error = self.verify(path.read_text(encoding='utf-8-sig'))
                self.assertIsNone(error)
                token_count += count
        words = sorted(KEYWORDS | TYPES)
        for word in words:
            for suffix in ('', '_', 'é', '值', '\u0301', '9'):
                self.verify(word + suffix)
        operators = '<<= >>= == != <= >= && || << >> += -= *= /= %= &= |= ^= .. => {}()[];,:.+-*/%&|^~!<>=?'
        self.verify(operators)
        self.evidence['real_sources'] = {'files': len(files), 'grammar_regions': token_count,
                                         'word_boundary_cases': len(words) * 6}

    def test_unicode_identifier_boundaries_and_numeric_continuations(self):
        rng = random.Random(0xD06)
        values = {0, 9, 10, 13, 28, 32, 127, 0x85, 0xA0, 0xAD, 0xB2, 0xB7, 0x300, 0x301,
                  0x345, 0x5D0, 0x660, 0x200C, 0x200D, 0x2028, 0x2029, 0x2118, 0x212E,
                  0x309B, 0x4E00, 0xFF10, 0x10000, 0x10400, 0x1D7CE, 0x1F600, 0x10FFFF}
        values.update(rng.randrange(0x110000) for _ in range(2048))
        # Surrogate code points cannot occur in a UTF-8 Dong source file.
        values = sorted(v for v in values if not 0xD800 <= v <= 0xDFFF)
        for value in values:
            char = chr(value)
            if char in '"\\/*':
                continue
            with self.subTest(codepoint=hex(value)):
                self.verify(char)
                self.verify('a' + char)
                self.verify('0' + char)
        for source in ('值', 'π变量', '_δ9', 'a\u0301', 'return\u0301', 'u64变量', '变量\u0301', '𐐀9'):
            self.verify(source)
        self.evidence['unicode'] = {'sampled_codepoints': len(values), 'contexts_per_codepoint': 3,
                                    'random_seed': 0xD06}

    def test_literals_invalid_digits_escapes_and_string_comment_masking(self):
        valid_numbers = ('0', '00', '1_000', '0x0', '0xA_f_09', '0b0', '0b10_01', '999999999999999999999999')
        invalid_numbers = ('0x', '0b', '0X12', '0B01', '0x_1', '0b_1', '0x1_', '0b1_', '1_',
                           '1__2', '0xGG', '0b102', '9abc', '1值', '0١', '7²')
        for value in valid_numbers + invalid_numbers:
            _, _, error = self.verify('let n = ' + value + ';')
            self.assertEqual(value in invalid_numbers, error is not None, value)
        escapes = [r'\n', r'\r', r'\t', r'\0', r'\\', r'\"'] + ['\\x' + f'{n:02X}' for n in range(256)]
        for value in escapes:
            self.assertIsNone(self.verify('"值' + value + '// /* fn u64 0xZZ"')[2])
        invalid_escapes = (r'\q', r'\u1234', r'\XFF', r'\x', r'\x0', r'\xGG', r'\x1Z', r'\a')
        for value in invalid_escapes:
            self.assertIsNotNone(self.verify('"abc' + value + '"')[2])
        for source in ('"unclosed', '"a\nlet next:u8=1;', '"a\r\nlet next:u8=1;', '/* unclosed\n fn u64'):
            self.assertIsNotNone(self.verify(source)[2])
        masked = '/* "\\q" fn u8 0b9 */ let 值:u64=7; // "\\q" 0xZZ\r\n"// /* */ fn 0xZZ";'
        self.assertIsNone(self.verify(masked)[2])
        spans, _, _ = TextMateSubset(self.grammar).consume(masked)
        q = masked.index('\\q')
        self.assertTrue(any(s.start <= q < s.end and 'comment.block.dong' in s.scopes for s in spans))
        self.assertFalse(any(s.start <= q < s.end and 'invalid.illegal.escape.dong' in s.scopes for s in spans))
        self.evidence['literals'] = {'valid_numbers': len(valid_numbers), 'invalid_numbers': len(invalid_numbers),
                                     'valid_escapes': len(escapes), 'invalid_escapes': len(invalid_escapes),
                                     'masking': 'strings and comments shield their contents'}

    def test_non_nested_comment_ends_at_first_delimiter(self):
        sources = ('/* outer /* inner */ let 值:u8=1; */',
                   '/* outer\n /* inner */\r\nreturn 0; */',
                   '/* /* */ "suffix" // */\nfn f()void{}')
        for source in sources:
            self.verify(source)
            _, regions, stack = TextMateSubset(self.grammar).consume(source)
            self.assertFalse(stack)
            comments = [r for r in regions if r.scope == 'comment.block.dong']
            self.assertEqual(1, len(comments))
            self.assertEqual(source.index('*/') + 2, comments[0].end)
            self.assertTrue(any(t.kind in {'let', 'return', 'string'} for t in lex(source)))
        self.evidence['non_nested'] = {'samples': len(sources), 'suffix_is_lexed': True}

    def test_actual_bad_grammar_controls_are_rejected(self):
        controls = []
        recursive = copy.deepcopy(self.grammar)
        recursive['repository']['block-comment']['patterns'] = [{'include': '#block-comment'}]
        controls.append(('recursive-block-comment', recursive, '/* outer /* inner */ let 值:u8=1; */'))
        permissive = copy.deepcopy(self.grammar)
        permissive['repository']['numbers']['patterns'][0]['match'] = r'0[xX][0-9a-fA-F_]+'
        controls.append(('permissive-hex-number', permissive, 'let n=0x1_;'))
        escape = copy.deepcopy(self.grammar)
        escape['repository']['string']['patterns'][0]['match'] = r'\\(?:[nrtq0\\"]|x[0-9a-fA-F]{2})'
        controls.append(('unknown-escape-accepted', escape, '"\\q"'))
        rejected = []
        for name, bad, source in controls:
            with self.subTest(control=name):
                # The mutated JSON is consumed. Failure is from output mismatch,
                # not a JSON hash, field equality, or a mocked token stream.
                with self.assertRaises(AssertionError) as error:
                    verify_consistency(bad, source)
                rejected.append({'control': name, 'reason': str(error.exception)})
        self.evidence['actual_bad_grammar_controls'] = rejected

    def test_offline_vsix_bytes_manifest_payloads_and_allowlist(self):
        spec = importlib.util.spec_from_file_location('dong_vsix_package', EXTENSION / 'package.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        first, second = (self.output / name for name in ('one.vsix', 'two.vsix'))
        digest = module.build(first)
        self.assertEqual(digest, module.build(second))
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(first) as archive:
            expected = {'[Content_Types].xml', 'extension.vsixmanifest'} | {'extension/' + p for p in module.FILES}
            self.assertEqual(expected, set(archive.namelist()))
            self.assertEqual(sorted(expected), archive.namelist())
            for name, data in module.payloads().items():
                self.assertEqual(data, archive.read(name))
            for info in archive.infolist():
                self.assertEqual((1980, 1, 1, 0, 0, 0), info.date_time)
                self.assertEqual(zipfile.ZIP_STORED, info.compress_type)
                self.assertEqual(0o100644, info.external_attr >> 16)
            manifest = ET.fromstring(archive.read('extension.vsixmanifest'))
            namespace = {'v': 'http://schemas.microsoft.com/developer/vsx-schema/2011'}
            identity = manifest.find('v:Metadata/v:Identity', namespace)
            self.assertEqual('dong-language', identity.attrib['Id'])
            self.assertEqual('dongos', identity.attrib['Publisher'])
            types = ET.fromstring(archive.read('[Content_Types].xml'))
            self.assertEqual({'json', 'md', 'vsixmanifest'}, {v.attrib['Extension'] for v in types})
            package = json.loads(archive.read('extension/package.json'))
            for entry in package['contributes']['grammars']:
                self.assertIn('extension/' + entry['path'].removeprefix('./'), expected)
        self.evidence['vsix'] = {'sha256': digest, 'bytes': first.stat().st_size,
                                 'same_input_same_bytes': True, 'payloads': sorted(expected),
                                 'installed': False}

    def test_real_textmate_oniguruma_scopes_state_utf16_and_bad_grammar(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node.js is required for the actual TextMate/Oniguruma engine gate')
        samples = []

        def sample(name, source):
            samples.append({'id': name, 'text': source})

        for path in sorted((ROOT / 'lang/examples').rglob('*.dg')) + [
                ROOT / 'kernel/firmware/power.dg', ROOT / 'kernel/firmware/power_runtime.dg',
                ROOT / 'services/desktop/theme.dg', ROOT / 'services/desktop/preferences.dg']:
            sample('repository-' + path.relative_to(ROOT).as_posix(), path.read_text(encoding='utf-8-sig'))
        for word in sorted(KEYWORDS | TYPES):
            for suffix in ('', '_', 'é', '值', '\u0301', '9', '𐐀'):
                sample('word-' + word + '-' + str(len(samples)), word + suffix)
        rng = random.Random(0xD06)
        values = {0, 9, 10, 13, 28, 32, 127, 0x85, 0xA0, 0xAD, 0xB2, 0xB7, 0x300, 0x301,
                  0x345, 0x5D0, 0x660, 0x200C, 0x200D, 0x2028, 0x2029, 0x2118, 0x212E,
                  0x309B, 0x4E00, 0xFF10, 0x10000, 0x10400, 0x1D7CE, 0x1F600, 0x10FFFF}
        values.update(rng.randrange(0x110000) for _ in range(2048))
        for value in sorted(values):
            if 0xD800 <= value <= 0xDFFF or chr(value) in '"\\/*':
                continue
            for prefix in ('', 'a', '0'):
                sample(f'unicode-{value:x}-{prefix}', prefix + chr(value))
        for number in ('0', '00', '1_000', '0x0', '0xA_f_09', '0b0', '0b10_01',
                       '0x', '0b', '0X12', '0B01', '0x_1', '0b_1', '0x1_', '0b1_', '1_',
                       '1__2', '0xGG', '0b102', '9abc', '1值', '0١', '7²'):
            sample('number-' + number, 'let n=' + number + ';')
        escapes = [r'\n', r'\r', r'\t', r'\0', r'\\', r'\"'] + ['\\x' + f'{n:02X}' for n in range(256)]
        for index, escape in enumerate(escapes):
            sample('escape-' + str(index), '"值' + escape + '// /* fn u64 0xZZ"')
        for index, escape in enumerate((r'\q', r'\u1234', r'\XFF', r'\x', r'\x0', r'\xGG', r'\x1Z', r'\a')):
            sample('invalid-escape-' + str(index), '"abc' + escape + '"')
        for index, source in enumerate(('"unclosed', '"a\nlet next:u8=1;', '"a\r\nlet next:u8=1;',
                                        '/* unclosed\n fn u64')):
            sample('unterminated-' + str(index), source)
        sample('multiline-first-close', '/* 外层\r\n/* 内层 */let 值:u8=1;\r\nreturn 0; */')
        sample('captures-and-utf16', 'const 𐐀值:u64=1; let a\u0301:u8=2; "𐐀值\\xFF\\n\\\"";')
        sample('comment-mask', '/* "\\q" fn u8 0b9 */ let 值:u64=7; // "\\q" 0xZZ\r\n"// /* */ fn 0xZZ";')
        sample('operators', '<<= >>= == != <= >= && || << >> += -= *= /= %= &= |= ^= .. => {}()[];,:.+-*/%&|^~!<>=?')
        recursive = copy.deepcopy(self.grammar)
        recursive['repository']['block-comment']['patterns'] = [{'include': '#block-comment'}]
        number = copy.deepcopy(self.grammar)
        number['repository']['numbers']['patterns'][0]['match'] = r'0[xX][0-9a-fA-F_]+'
        escape = copy.deepcopy(self.grammar)
        escape['repository']['string']['patterns'][0]['match'] = r'\\(?:[nrtq0\\"]|x[0-9a-fA-F]{2})'
        controls = [('recursive-comment', recursive, '/* outer /* inner */ let 值:u8=1; */'),
                    ('permissive-number', number, 'let n=0x1_;'), ('unknown-escape', escape, '"\\q"')]
        request = {'groups': [{'id': 'normal', 'grammar': self.grammar, 'samples': samples}] + [
            {'id': name, 'grammar': grammar, 'samples': [{'id': name, 'text': source}]}
            for name, grammar, source in controls]}
        raw_input = json.dumps(request, ensure_ascii=True)
        (self.output / 'actual-engine-input.json').write_text(raw_input + '\n', encoding='utf-8')
        process = subprocess.run([node, str(EXTENSION / 'test-deps/run_textmate.cjs')], input=raw_input,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 encoding='utf-8', timeout=45, cwd=EXTENSION)
        self.assertEqual(0, process.returncode, process.stderr)
        response = json.loads(process.stdout)
        (self.output / 'actual-engine-output.json').write_text(json.dumps(response, ensure_ascii=True) + '\n', encoding='utf-8')
        self.assertTrue(response['engine']['wasm'])
        self.assertTrue(response['engine']['dependencyHashesVerified'])
        actual = {item['id']: item for item in response['groups']['normal']}
        self.assertEqual({item['id'] for item in samples}, set(actual))
        outcomes = {'valid': 0, 'invalid': 0}
        for entry in samples:
            with self.subTest(actual_engine_sample=entry['id']):
                outcome = verify_engine(entry['text'], actual[entry['id']])
                outcomes[outcome] += 1
        multiline = actual['multiline-first-close']
        self.assertEqual([2, 1, 1], [line['depth'] for line in multiline['lineStates']])
        value = next(item['text'] for item in samples if item['id'] == 'captures-and-utf16')
        spans = engine_spans(value, actual['captures-and-utf16'])
        for name in ('punctuation.definition.string.begin.dong', 'punctuation.definition.string.end.dong',
                     'constant.character.escape.dong'):
            self.assertTrue(any(name in span.scopes for span in spans), name)
        for index, escape_text in enumerate(escapes):
            source = next(item['text'] for item in samples if item['id'] == 'escape-' + str(index))
            escape_spans = engine_spans(source, actual['escape-' + str(index)])
            start, end = 2, 2 + len(escape_text)
            cursor = start
            for span in escape_spans:
                if span.end <= cursor or span.start >= end:
                    continue
                self.assertIn('constant.character.escape.dong', span.scopes, escape_text)
                self.assertLessEqual(span.start, cursor)
                cursor = min(span.end, end)
            self.assertEqual(end, cursor, escape_text)
            for scope, boundary in (('punctuation.definition.string.begin.dong', 0),
                                    ('punctuation.definition.string.end.dong', len(source) - 1)):
                self.assertTrue(any(span.start <= boundary < span.end and scope in span.scopes for span in escape_spans),
                                (escape_text, scope))
        first_astral = value.index('𐐀')
        self.assertTrue(any(span.start == first_astral and 'variable.other.dong' in span.scopes for span in spans))
        self.assertTrue(any(token['start'] != span.start for token, span in zip(actual['captures-and-utf16']['tokens'], spans)),
                        'sample must actually exercise UTF-16/code-point offset differences')
        rejected = []
        for name, _, source in controls:
            result, = response['groups'][name]
            with self.assertRaises(AssertionError) as error:
                verify_engine(source, result)
            rejected.append({'name': name, 'reason': str(error.exception)})
        self.evidence['actual_textmate_oniguruma'] = {
            **response['engine'], 'samples': len(samples), 'outcomes': outcomes,
            'raw_token_count': sum(len(value['tokens']) for value in actual.values()),
            'multiline_depths': [line['depth'] for line in multiline['lineStates']],
            'captures_and_utf16': True, 'exact_escape_capture_intervals': len(escapes),
            'actual_bad_grammar_controls': rejected,
            'input_sha256': hashlib.sha256((self.output / 'actual-engine-input.json').read_bytes()).hexdigest(),
            'output_sha256': hashlib.sha256((self.output / 'actual-engine-output.json').read_bytes()).hexdigest(),
        }


if __name__ == '__main__':
    unittest.main(verbosity=2)
