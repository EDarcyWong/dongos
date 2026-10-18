"""Independent parse/trivia and real CLI tests; never rewrite repository DG."""
from __future__ import annotations

from bisect import bisect_left
from contextlib import redirect_stderr
from dataclasses import asdict
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid


PACKAGE = Path(__file__).resolve().parents[1]
for candidate in PACKAGE.parents:
    if (candidate / 'lang/dongc/frontend.py').is_file():
        ROOT = candidate
        break
else:
    ROOT = PACKAGE
sys.path.insert(0, str(ROOT))
from lang.dongc.frontend import Parser, lex
from lang.dongc.model import CompileError

TOOL = PACKAGE / 'tools/dongfmt.py'
spec = importlib.util.spec_from_file_location('dongfmt_under_test', TOOL)
fmt = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fmt
spec.loader.exec_module(fmt)


def ast_model(text):
    # dataclass dict conversion is independent of the formatter's AST walker.
    # Recognize only Token's complete field set; do not strip ImportDecl.path.
    def tokenless(items):
        data = dict(items)
        if set(data) == {'kind', 'value', 'line', 'column', 'path'}:
            return {key: data[key] for key in ('kind', 'value')}
        return data
    tree = Parser(lex(text.removeprefix('\ufeff'), path='oracle.dg')).parse()
    return json.dumps(asdict(tree, dict_factory=tokenless), default=sorted, sort_keys=True, ensure_ascii=False)


def trivia_model(text):
    # A separate regex selects literals/comments. Compiler token offsets anchor
    # them to the original program without using the formatter's Piece scanner.
    text = text.removeprefix('\ufeff')
    lines = [0, *(m.end() for m in re.finditer('\n', text))]
    starts = [lines[t.line - 1] + t.column - 1 for t in lex(text)[:-1]]
    patterns = r'"(?:\\[^\r\n]|[^"\\\r\n])*"|//[^\n]*|/\*[\s\S]*?\*/'
    return [('string' if m.group().startswith('"') else 'comment',
             m.group(), bisect_left(starts, m.start())) for m in re.finditer(patterns, text)]


def repo_dg():
    result = []
    for directory, names, files in os.walk(ROOT):
        names[:] = [n for n in names if n not in {'build', '.git', '.tools', 'node_modules',
                                                 '.venv', '__pycache__'}]
        result += [Path(directory) / name for name in files if name.endswith('.dg')]
    return sorted(result)


FULL_SYNTAX = r'''// Unicode identifiers and literal bytes must survive: 中 é
module 测试.格式;
import core.int as ci;
pub align(8) packed struct 数据 {pub 值:u64,pub 指针:*const u8}
pub enum 候选 {空,数(u64),指(*const u8)}
pub error 错误=0x08_00;
type Callback=unsafe extern "win64" fn(x:u64)u64;
pub const 数量:usize=4;
pub var 存储:[数量]u8=[0;数量];
unsafe extern "sysv64" ("foreign_fn") fn 外部(p:*const u8,n:usize)u64;
fn (self:*数据) 读取(x:u64)u64 {return x;}
fn 清理()void{return;}
export("entry") fn 主体(选:?u64,结果:!u64,数组:[]const u8)!u64 {
defer 清理();defer {清理();}
const N:usize=2;var 局部:[N]u8=[1,2];
let 文本="中文\x00\x41\n\r\t\0\\\" /* not comment */";
let i=选 orelse return error.错误;
let v=try 结果;
var 计数:u64=0;for j in 0..N {计数+=j;}for b in 数组 {计数+=b as u64;}
while 计数<2 {计数+=1;if 计数==1 {continue;}else{break;}}
loop {break;}
match 选 {some(x)=>{计数=x;},null=>{计数=0;},}
match 结果 {ok(x)=>{计数=x;},err(code)=>{return code;},}
let 实体=数据 {值:1,指针:null};let 备选=候选.数(2);
unsafe {asm {pause}let p=局部.ptr;let x=read_unaligned(p);write_unaligned(p,x);}
/* block: whitespace and Unicode are literal bytes
  第二行  */
return (i+v*2)<<1;
}
'''


class DongfmtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'build/test/dongfmt/host' / ('run-' + uuid.uuid4().hex[:12])
        cls.directory.mkdir(parents=True)
        cls.dg = repo_dg()
        cls.inputs = [TOOL, Path(__file__), ROOT / 'lang/dongc/frontend.py', ROOT / 'lang/dongc/model.py',
                      ROOT / 'lang/spec.md', *cls.dg]
        cls.before = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        cls.evidence = {}

    @classmethod
    def tearDownClass(cls):
        after = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.inputs}
        if after != cls.before:
            raise AssertionError('formatter/compiler/repository source changed during verification')
        (cls.directory / 'validation-summary.json').write_text(json.dumps(dict(
            source_unchanged=True, source_sha256=after, repository_files_rewritten=False,
            guest_executed=False, full_build_executed=False, evidence=cls.evidence), indent=2)+'\n', encoding='utf-8')
        print('DONGFMT_EVIDENCE ' + str(cls.directory))

    def cli(self, args=(), data=None):
        return subprocess.run([sys.executable, str(TOOL), *map(str, args)], input=data,
                              cwd=self.directory, capture_output=True, timeout=30)

    def equivalent(self, original, formatted):
        self.assertEqual(ast_model(original), ast_model(formatted))
        before = [(t.kind, t.value) for t in lex(original.removeprefix('\ufeff'))]
        after = [(t.kind, t.value) for t in lex(formatted.removeprefix('\ufeff'))]
        self.assertEqual(before, after)
        self.assertEqual(trivia_model(original), trivia_model(formatted))
        self.assertEqual(original.startswith('\ufeff'), formatted.startswith('\ufeff'))
        self.assertEqual(formatted, fmt.format_source(formatted))

    def test_full_syntax_unicode_literals_comments_bom_and_crlf(self):
        cases = [FULL_SYNTAX, '\ufeff'+FULL_SYNTAX.replace('\n', '\r\n'),
                 'module x;fn f()u64{let é=1;/* a */return é;}// trailing  ',
                 'module x;fn f(p:*u64)u64{unsafe{return 2 / /* divide by deref */ *p;}}',
                 'module x;fn f()void{let x="\\xff\\x00";// retain CR\r\nreturn;}']
        outputs = []
        for index, text in enumerate(cases):
            with self.subTest(index=index):
                value = fmt.format_source(text)
                self.equivalent(text, value)
                self.assertTrue(value.endswith('\n'))
                path = self.directory / ('syntax-'+str(index)+'.dg')
                path.write_bytes(value.encode('utf-8'))
                outputs.append(dict(index=index, bytes=len(value.encode('utf-8'))))
        self.evidence['full_syntax'] = outputs

    def test_complete_repository_valid_syntax_and_idempotence_without_writes(self):
        outcomes, invalid = [], []
        self.assertGreaterEqual(len(self.dg), 150)
        for path in self.dg:
            original = path.read_bytes()
            text = original.decode('utf-8')
            try:
                Parser(lex(text.removeprefix('\ufeff'), path=str(path))).parse()
            except CompileError as exc:
                invalid.append(dict(path=path.relative_to(ROOT).as_posix(), code=exc.code, message=exc.message))
                with self.assertRaises(CompileError):
                    fmt.format_bytes(original, str(path))
                continue
            value = fmt.format_bytes(original, str(path))
            self.equivalent(text, value.decode('utf-8'))
            self.assertEqual(original, path.read_bytes())
            outcomes.append(dict(path=path.relative_to(ROOT).as_posix(),
                input_sha256=hashlib.sha256(original).hexdigest(), output_sha256=hashlib.sha256(value).hexdigest(),
                input_bytes=len(original), formatted_bytes=len(value)))
        self.assertGreaterEqual(len(outcomes), 150)
        self.evidence['repository'] = dict(valid_files=len(outcomes), invalid_files=invalid, files=outcomes)

    def test_cli_stdout_stdin_check_paths_and_utf8_diagnostics(self):
        raw = 'module 中文;fn f()u64{return 0x12_34;}'.encode('utf-8')
        expected = fmt.format_bytes(raw)
        for args in ((), ('-',)):
            value = self.cli(args, raw)
            self.assertEqual((0, expected, b''), (value.returncode, value.stdout, value.stderr))
        value = self.cli(('--check',), raw)
        self.assertEqual((1, b'', b''), (value.returncode, value.stdout, value.stderr))
        value = self.cli(('--check',), expected)
        self.assertEqual((0, b'', b''), (value.returncode, value.stdout, value.stderr))
        path = self.directory / '命令-e\u0301-\U0001f9ea.dg'
        path.write_bytes(raw)
        self.assertEqual(expected, self.cli((path,)).stdout)
        value = self.cli(('--check', path))
        self.assertEqual(1, value.returncode)
        self.assertEqual(str(path)+'\n', value.stdout.decode('utf-8'))
        for data in (b'module broken; fn f()void{', b'module x; const s:[]const u8="bad\\q";', b'\xff'):
            value = self.cli((), data)
            self.assertEqual((2, b''), (value.returncode, value.stdout))
            self.assertTrue(value.stderr)
        for args in (('--write',), ('-', path), (path, path), ('--write', path, path), ('--check', '--write', path)):
            value = self.cli(args)
            self.assertEqual(2, value.returncode)
        self.assertEqual(raw, path.read_bytes())
        self.evidence['cli_contract'] = dict(stdin=True, stdout=True, check_exit_0_1_2=True,
            invalid_utf8_refused=True, invalid_combinations_refused=True)

    def test_write_batch_preflight_bom_mode_and_idempotent_atomic_replace(self):
        good = self.directory / 'write-good.dg'
        bad = self.directory / 'write-bad.dg'
        raw = b'\xef\xbb\xbfmodule good;\r\nfn f()void{return;}'
        invalid = b'module bad;fn f()void{'
        good.write_bytes(raw)
        bad.write_bytes(invalid)
        os.chmod(good, stat.S_IRUSR | stat.S_IWUSR)
        mode = stat.S_IMODE(good.stat().st_mode)
        value = self.cli(('--write', good, bad))
        self.assertEqual(2, value.returncode)
        self.assertEqual(raw, good.read_bytes())
        self.assertEqual(invalid, bad.read_bytes())
        bad.write_bytes(b'module bad;fn f()void{return;}')
        value = self.cli(('--write', good, bad))
        self.assertEqual((0, b'', b''), (value.returncode, value.stdout, value.stderr))
        self.assertEqual(fmt.format_bytes(raw), good.read_bytes())
        self.assertEqual(mode, stat.S_IMODE(good.stat().st_mode))
        self.assertEqual(0, self.cli(('--check', good, bad)).returncode)
        self.assertEqual([], list(self.directory.glob('.dongfmt-*.tmp')))
        self.evidence['atomic_write'] = dict(batch_syntax_preflight=True, bom_preserved=True, mode_preserved=True)

    def test_concurrent_source_changes_and_replace_errors_never_clobber(self):
        path = self.directory / 'concurrent.dg'
        raw = b'module x;fn f()void{return;}'
        edited = b'module changed;fn f()void{return;}'
        path.write_bytes(raw)
        item = fmt.prepare(path)
        path.write_bytes(edited)
        with self.assertRaisesRegex(fmt.FormatError, 'source changed'):
            fmt.write_files([item])
        self.assertEqual(edited, path.read_bytes())
        path.write_bytes(raw)
        item = fmt.prepare(path)
        real_fsync = fmt.os.fsync
        def raced(fd):
            real_fsync(fd)
            path.write_bytes(edited)
        with patch.object(fmt.os, 'fsync', side_effect=raced):
            with self.assertRaisesRegex(fmt.FormatError, 'source changed'):
                fmt.write_files([item])
        self.assertEqual(edited, path.read_bytes())
        path.write_bytes(raw)
        item = fmt.prepare(path)
        with patch.object(fmt.os, 'replace', side_effect=OSError('injected replacement refusal')):
            with self.assertRaisesRegex(OSError, 'replacement refusal'):
                fmt.write_files([item])
        self.assertEqual(raw, path.read_bytes())
        self.assertEqual([], list(self.directory.glob('.dongfmt-*.tmp')))
        self.evidence['write_failure_controls'] = dict(before_staging_change=True,
            during_staging_change=True, failed_replace=True, temporary_cleanup=True)

    def test_actual_bad_renderers_are_rejected_before_write(self):
        text = 'module x;fn f(a:u64)u64{/* preserve me */let s="\\x41";return a+1;}'
        normal = fmt._render
        outcomes = {}
        mutations = {'drop-comment': lambda s:s.replace('/* preserve me */', ''),
                     'reencode-string': lambda s:s.replace('"\\x41"', '"A"'),
                     'change-operator': lambda s:s.replace('a + 1', 'a - 1')}
        for label, mutate in mutations.items():
            hit = []
            def bad(pieces):
                hit.append(True)
                return mutate(normal(pieces))
            with self.subTest(label=label):
                path = self.directory / ('bad-'+label+'.dg')
                path.write_bytes(text.encode('utf-8'))
                with patch.object(fmt, '_render', side_effect=bad), redirect_stderr(io.StringIO()):
                    self.assertEqual(2, fmt.main(['--write', str(path)]))
                self.assertEqual([True], hit)
                self.assertEqual(text.encode('utf-8'), path.read_bytes())
                changed = mutate(normal(fmt._pieces(text, lex(text))))
                # Independent oracle proves the selected mutation is material,
                # including string spelling whose parsed bytes stay equivalent.
                if label == 'change-operator':
                    self.assertNotEqual(ast_model(text), ast_model(changed))
                else:
                    self.assertEqual(ast_model(text), ast_model(changed))
                    self.assertNotEqual(trivia_model(text), trivia_model(changed))
                outcomes[label] = dict(actual_renderer_path_hit=1, rejected_exit=2, original_unchanged=True)
        self.evidence['actual_bad_renderers'] = outcomes

    def test_non_nested_comment_contract_and_invalid_syntax_never_render(self):
        invalid = ['/* outer /* inner */ tail */ module x;', 'module x; fn f()void{return}',
                   'module x; fn f()void{let n=0b2;}', 'module x; /*',
                   'module x; fn f()void{let x="bad\n";}', 'module x; fn f()void{let x="\\q";}']
        for text in invalid:
            with self.subTest(text=text), patch.object(fmt, '_render') as renderer:
                with self.assertRaises(CompileError):
                    fmt.format_source(text)
                renderer.assert_not_called()
        self.evidence['invalid_input'] = dict(samples=len(invalid), no_render_or_write=True,
            block_comments='non-nested, matching the current compiler/spec')


if __name__ == '__main__':
    unittest.main(verbosity=2)
