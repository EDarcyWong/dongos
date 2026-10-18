"""Regenerate the static TextMate grammar from the local Dong lexer contract.

Only Python's standard library is used. No installation or network operation.
"""
from pathlib import Path
import hashlib
import json
import sys
import unicodedata


HERE = Path(__file__).resolve().parent


def project_root():
    return next(p for p in HERE.parents if (p / 'lang/dongc/frontend.py').is_file())


def character_class(predicate):
    """Literal Unicode ranges work in both Oniguruma and Python's re engine."""
    runs, start, previous = [], None, None
    for value in range(sys.maxunicode + 1):
        if predicate(chr(value)):
            if start is None:
                start = value
            previous = value
        elif start is not None:
            runs.append((start, previous))
            start = None
    if start is not None:
        runs.append((start, previous))

    def literal(value):
        char = chr(value)
        return '\\' + char if char in '\\[]^- ' else char

    return '[' + ''.join(literal(a) if a == b else literal(a) + '-' + literal(b)
                         for a, b in runs) + ']'


def generate():
    root = project_root()
    sys.path.insert(0, str(root))
    from lang.dongc.model import KEYWORDS, TYPES
    first = character_class(lambda c: c == '_' or c.isidentifier())
    rest = character_class(lambda c: ('a' + c).isidentifier())
    alnum = character_class(lambda c: c.isalnum() or c == '_')
    whitespace = character_class(str.isspace)
    word = lambda words: '(?:' + '|'.join(sorted(words, key=lambda x: (-len(x), x))) + ')(?!' + rest + ')'
    sources = ('lang/dongc/frontend.py', 'lang/dongc/model.py', 'lang/spec.md')
    return {
        '$schema': 'https://raw.githubusercontent.com/martinring/tmlanguage/master/tmlanguage.json',
        'name': 'Dong', 'scopeName': 'source.dong', 'fileTypes': ['dg'],
        'comment': 'Generated Unicode ranges; block comments are deliberately NOT recursive.',
        'dongContract': {
            'unicodeVersion': unicodedata.unidata_version,
            'sources': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sources},
        },
        'patterns': [{'include': '#' + name} for name in (
            'line-comment', 'block-comment', 'unterminated-string', 'string', 'numbers',
            'types', 'keywords', 'identifier', 'operators', 'punctuation', 'whitespace', 'invalid')],
        'repository': {
            'line-comment': {'name': 'comment.line.double-slash.dong', 'match': r'//[^\n]*'},
            'block-comment': {'name': 'comment.block.dong', 'begin': r'/\*', 'end': r'\*/'},
            'unterminated-string': {
                'name': 'invalid.illegal.unterminated-string.dong',
                'match': r'"(?:[^"\\\r\n]|\\[^\r\n])*\\?(?=\r?$)',
            },
            'string': {
                'name': 'string.quoted.double.dong', 'begin': '"', 'end': '"',
                'beginCaptures': {'0': {'name': 'punctuation.definition.string.begin.dong'}},
                'endCaptures': {'0': {'name': 'punctuation.definition.string.end.dong'}},
                'patterns': [
                    {'name': 'constant.character.escape.dong', 'match': r'\\(?:[nrt0\\"]|x[0-9a-fA-F]{2})'},
                    {'name': 'invalid.illegal.escape.dong', 'match': r'\\(?:x[^"\r\n]{0,2}|[^\r\n])?'},
                ],
            },
            'numbers': {'patterns': [
                {'name': 'constant.numeric.integer.hexadecimal.dong',
                 'match': r'0x[0-9a-fA-F]+(?:_[0-9a-fA-F]+)*(?!' + alnum + ')'},
                {'name': 'constant.numeric.integer.binary.dong',
                 'match': r'0b[01]+(?:_[01]+)*(?!' + alnum + ')'},
                {'name': 'constant.numeric.integer.decimal.dong',
                 'match': r'[0-9]+(?:_[0-9]+)*(?!' + alnum + ')'},
                {'name': 'invalid.illegal.integer.dong', 'match': '[0-9]' + alnum + '*'},
            ]},
            'types': {'name': 'storage.type.dong', 'match': word(TYPES)},
            'keywords': {'name': 'keyword.control.dong', 'match': word(KEYWORDS)},
            'identifier': {'name': 'variable.other.dong', 'match': first + rest + '*'},
            'operators': {
                'name': 'keyword.operator.dong',
                'match': r'<<=|>>=|==|!=|<=|>=|&&|\|\||<<|>>|\+=|-=|\*=|/=|%=|&=|\|=|\^=|\.\.|=>|[+*/%&|^~!<>=?\-]',
            },
            'punctuation': {'name': 'punctuation.separator.dong', 'match': r'[{}()\[\];,:.]'},
            'whitespace': {'name': 'meta.whitespace.dong', 'match': whitespace + '+'},
            'invalid': {'name': 'invalid.illegal.character.dong', 'match': r'[\s\S]'},
        },
    }


if __name__ == '__main__':
    path = HERE / 'syntaxes/dong.tmLanguage.json'
    path.write_text(json.dumps(generate(), indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
    print(path)
