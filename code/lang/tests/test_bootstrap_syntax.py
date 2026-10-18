"""Real Dong module/statement parsing, independently compared with Python AST."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import unittest
import uuid

from lang.dongc import CompileError, compile_file
from lang.dongc.frontend import Parser, lex
from lang.tests.test_dongc import tool, nasm_flags
from lang.tests.test_bootstrap_expression import HARNESS, actual_tree, host_tree, host_type

ROOT = Path(__file__).resolve().parents[2]
RESERVED = {'lang/bootstrap/bigint_div.dg', 'lang/bootstrap/bigint_bits.dg',
            'lang/bootstrap/constant_arithmetic.dg', 'lang/bootstrap/type_layout.dg',
            'lang/std/core/arena.dg', 'lang/std/core/utf8.dg', 'lang/bootstrap/source_position.dg'}


def host_block(stmts, lengths):
    return ('block', tuple(host_statement(s, lengths) for s in stmts))


def host_statement(s, lengths):
    e = lambda expr: host_tree(expr, lengths)
    body = lambda stmts: host_block(stmts, lengths)
    k = s.kind
    if k == 'binding': return (k, s.token.kind, s.value[0].value, None if s.value[1] is None else host_type(s.value[1], lengths), e(s.expr))
    if k == 'return': return (k, e(s.expr))
    if k in ('if', 'while'):
        other = None
        if s.otherwise is not None:
            other = host_statement(s.otherwise[0], lengths) if len(s.otherwise)==1 and s.otherwise[0].kind=='if' else body(s.otherwise)
        return (k, e(s.expr), body(s.body), other)
    if k in ('loop','defer','unsafe'): return (k, body(s.body))
    if k == 'block': return body(s.body)
    if k == 'for':
        iterable = ('range', e(s.expr.args[0]), e(s.expr.args[1])) if s.expr.kind=='range' else e(s.expr)
        return (k, s.value.value, iterable, body(s.body))
    if k == 'match':
        arms = tuple(((a.pattern.kind, a.pattern.value, None if a.pattern.binding is None else a.pattern.binding.value),body(a.body)) for a in s.value)
        return (k, e(s.expr), arms)
    if k == 'asm': return (k, s.value)
    if k in ('break','continue'): return (k,)
    if k == 'assign': return (k, s.value[1], e(s.value[0]), e(s.expr))
    if k == 'call': return ('call-statement', e(s.expr))
    raise AssertionError(k)


def host_module(m):
    lengths = m.type_lengths
    typ = lambda t: host_type(t, lengths)
    e = lambda value: host_tree(value, lengths)
    number = lambda value: value if value is None or isinstance(value,int) else e(value)
    decls=[]
    def add(item, value, packed=False, align=None, unsafe=False, abi='sysv64', export=None, external=False):
        decls.append(('decl',(item.public,packed,align,unsafe,abi,export,external),value))
    for f in m.functions:
        params=tuple((name.value,typ(t),f.receiver is not None and i==0) for i,(name,t) in enumerate(f.params))
        add(f,('function',f.token.value,params,typ(f.returns),None if f.external else host_block(f.body,lengths)),
            unsafe=f.unsafe,abi=f.abi,export=f.export,external=f.external)
    for s in m.structs:
        fields=tuple((name.value,typ(t),name.value in s.field_public) for name,t in s.fields)
        add(s,('struct-decl',s.token.value,fields),packed=s.packed,align=number(s.alignment))
    for s in m.enums: add(s,('enum-decl',s.token.value,tuple((name.value,None if t is None else typ(t)) for name,t in s.variants)))
    for s in m.errors: add(s,('error-decl',s.token.value,number(s.code)))
    for s in m.aliases: add(s,('alias-decl',s.token.value,typ(s.target)))
    for s in m.constants: add(s,('const',s.token.value,typ(s.typ),e(s.expr)))
    for s in m.globals: add(s,('global',s.token.value,typ(s.typ),e(s.expr)))
    return ('module',m.name,tuple(('import',i.path,i.alias) for i in m.imports),tuple(sorted(decls,key=lambda d:(d[2][0],d[2][1]))))


class BootstrapSyntaxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc: raise unittest.SkipTest('native syntax requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-syntax'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        readonly='module p;pub fn f(x:*const u8)u64{return sizeof(u64)+(*x as u64);}'
        probe='#define PROBE_SOURCE '+json.dumps(readonly)+'\n#define PROBE_MODE 2\n'
        (cls.work/'probe.c').write_text(probe+HARNESS.replace('dong_bootstrap_expression','dong_bootstrap_syntax'),encoding='utf-8')
        cls.records=[]
        cls.inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                    [ROOT/'lang/bootstrap/expression.dg',ROOT/'lang/bootstrap/syntax.dg',ROOT/'lang/bootstrap/lexer.dg',
                     ROOT/'lang/bootstrap/unicode.dg',Path(__file__),ROOT/'lang/tests/test_bootstrap_expression.py']}
        cls.executables={mode:cls.build(ROOT/'lang',mode,mode) for mode in ('debug','release')}

    @classmethod
    def command(cls,args,label):
        r=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=120)
        (cls.work/(label+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode: raise AssertionError((label,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,root,mode,label):
        compiled=compile_file(root/'bootstrap/syntax.dg',roots=[root],mode=mode)
        asm=cls.work/(label+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
        obj=cls.work/(label+'.o');exe=cls.work/(label+('.exe' if os.name=='nt' else ''))
        for fmt in ('elf64','win64'):
            target=obj if fmt==('win64' if os.name=='nt' else 'elf64') else cls.work/(label+'.'+fmt+'.o')
            cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',target,asm],label+'-'+fmt)
        cls.command([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*([] if os.name=='nt' else ['-no-pie']),cls.work/'probe.c',obj,'-o',exe],label+'-link')
        return exe

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        artifacts={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.work.rglob('*') if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,artifact_sha256=artifacts,records=cls.records,
            OS_VM_built=False,L3_selfhost_complete=False),indent=2)+'\n',encoding='utf-8')

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for source,cap,depth,mode,status in cases:
            raw=source.encode('utf-8');payload.extend(struct.pack('<5Q',len(raw),cap,depth,mode,0));payload.extend(raw)
        (self.work/(label+'.input')).write_bytes(payload)
        r=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(r.stdout);(self.work/(label+'.stderr')).write_bytes(r.stderr)
        self.assertEqual(r.returncode,0,r.stderr);at=0
        for i,(source,cap,depth,mode,expected_status) in enumerate(cases):
            status,root,used,nxt,code,error,guard,count=struct.unpack_from('<8Q',r.stdout,at);at+=64
            nodes=[] if status==1 else [struct.unpack_from('<8Q',r.stdout,at+64*j) for j in range(used)];at+=cap*64
            self.assertEqual(guard,1,(label,i,'guard/atomicity'))
            allowed = expected_status if isinstance(expected_status,tuple) else (expected_status,)
            self.assertIn(status,allowed,(label,i,'status',error,source[:160]))
            if status==1:continue
            tokens=lex(source);parser=Parser(tokens)
            if status in (0,2):
                try:
                    if mode==1:expected=host_block(parser.block(),parser.type_lengths)
                    elif mode==2:expected=host_module(parser.parse())
                    elif mode==3:expected=host_statement(parser.statement(),parser.type_lengths)
                    else:
                        wrapped=Parser(lex('module probe;'+source)).parse()
                        expected=host_module(wrapped)[3][0];parser.index=len(tokens)-1
                except CompileError as failure:
                    self.assertEqual(status,2,(label,i,failure))
                    error_index=next(j for j,token in enumerate(tokens) if token is failure.token)
                    self.assertEqual(error,error_index,(label,i,'diagnostic token',source[:160]))
                    continue
                self.assertEqual(status,0,(label,i,source[:160]))
                self.assertEqual(nxt,parser.index,(label,i,'next token'))
                self.assertEqual(actual_tree(nodes,root,tokens),expected,(label,i,'AST',source[:160]))
        self.assertEqual(at,len(r.stdout))

    def test_actual_modules_against_host_declarations_statements_and_expressions(self):
        cases=[];sources={}
        for parent in ('lang','kernel','services'):
            for p in sorted((ROOT/parent).rglob('*.dg')):
                name=p.relative_to(ROOT).as_posix()
                if name in RESERVED:continue
                text=p.read_text(encoding='utf-8-sig');Parser(lex(text)).parse()
                sources[name]=hashlib.sha256(p.read_bytes()).hexdigest()
                cases.append((text,len(lex(text))*3,256,2,0))
        self.assertGreater(len(cases),200)
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'modules-'+mode)
        (self.work/'corpus.json').write_text(json.dumps(dict(source_sha256=sources,reserved_tasks_excluded=sorted(RESERVED)),indent=2)+'\n',encoding='utf-8')
        self.records.append(dict(test='full-modules',modules=len(cases),modes=2,passed=True))

    def test_statement_forms_and_declaration_modifiers(self):
        statements=['{var x:u64;let y=1;const N:usize=3;x=y;return;}',
            '{if x {f();} else if y {g();} else {h();} while x {break;} loop {continue;}}',
            '{for i in 0..n {f(i);} for item in values {f(item);} defer f();defer {g();}}',
            '{match x {true=>{f();},false=>{g();},null=>{h();},some(v)=>{f(v);},ok(v)=>{g(v);},err(e)=>{h(e);},State.On=>{},_=>{},}}',
            '{unsafe {*p+=1;asm {pause}}try f();{g();}}',
            '{a<<=1;a>>=1;a&=1;a|=1;a^=1;a*=2;a/=2;a%=2;a-=1;}',
            '{return Point{x:f() as u64,y:sizeof([N]u64)};}']
        modules=['module example; import core.mem;import a.b as c; pub type P=?*const u8;',
            'module example;pub packed align(16) struct S{pub a:u8,b:[N+1]u64,} pub enum E{A,B(u64),C(!u64),}',
            'module example;pub error Oops=1+2;pub const N:usize=3;var state:u64=0;',
            'module example;extern "sysv64"("custom") fn f(a:u64,b:[]u8)!u64; export("go") unsafe fn g()void{}',
            'module example;struct S{x:u64} pub fn(self:*S) get()u64{return (*self).x;}',
            'module example;extern "win64" unsafe fn f(a:u64)u64{return a;}']
        modules += ['module example;export("\\x67o") fn f()void{}',
                    'module example;extern "\\x73ysv64"("\\x66") fn f()void;']
        cases=[(s,len(lex(s))*3,256,1,0) for s in statements]+[(s,len(lex(s))*3,256,2,0) for s in modules]
        cases += [(s,len(lex(s))*3,256,3,0) for s in ('let x=Point{x:1};','if x {f();} else {g();}','defer f();')]
        cases += [(s,len(lex(s))*3,256,4,0) for s in ('pub const N:usize=4;', 'unsafe fn f()void{}', 'pub struct S{pub x:u64}')]
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'forms-'+mode)
        self.records.append(dict(test='statement-declaration-forms',cases=len(cases),modes=2,passed=True))

    def test_errors_depth_capacity_and_publication(self):
        bad=['{let x;}', '{var x;}', '{return 1}', '{if x f();}', '{for i 0..n {}}', '{defer let x=1;}',
             '{match x {some=>{}}}', '{1;}', '{break value;}', '{', '{f(;}']
        bad_modules=['module a', 'module a;fn f();','module a;pub pub fn f()void{}',
                     'module a;const N=1;', 'module a;var x:u64;', 'module a;unsafe struct S{}',
                     'module a;packed fn f()void{}','module a;enum E{A(u64,u64)}',
                     'module a;export("bad-name") fn f()void{}','module a;export("") fn f()void{}',
                     'module a;extern "sysv64"("1bad") fn f()void;']
        cases=[(s,100,128,1,2) for s in bad]+[(s,100,128,2,2) for s in bad_modules]
        cases += [('{}',1,128,1,0),('{}',0,128,1,3),('module a;',2,128,2,0),('module a;',1,128,2,3),
                  ('{'*20+'}'*20,100,8,1,4),('module a;fn f()void{}',100,1,2,4),
                  ('{}',20,128,0,1),('{}',20,128,5,1)]
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'bounds-'+mode)
        self.records.append(dict(test='syntax-depth-capacity',cases=len(cases),modes=2,passed=True))

    def test_punctuation_deletions_rejected_by_independent_host_parser(self):
        originals=['module a;import b.c as d;pub type X=[N+1]*const u8;',
            'module a;pub align(16) struct S{pub x:u64,y:[]const u8,} enum E{A,B(u64),}',
            'module a;pub error Oops=1;const N:usize=4;var x:u64=0;',
            'module a;export("entry") fn f(a:u64,b:[]u8)u64{let x=Point{x:a};if a>0 {return x.x;} else {return sizeof(u64);}}',
            'module a;unsafe fn f()void{for i in 0..N{defer g();}match x {some(v)=>{g(v);},_=>{}}}']
        rejected={}
        for original in originals:
            for i,char in enumerate(original):
                if char not in ';{}()[]:=,':continue
                mutated=original[:i]+original[i+1:]
                try:tokens=lex(mutated)
                except CompileError:continue
                try:Parser(tokens).parse()
                except CompileError as failure:
                    if failure.code in ('E0101','E0601','E0602','E0301'):
                        rejected[mutated]=failure.message
        self.assertGreater(len(rejected),60)
        cases=[(s,len(lex(s))*3,256,2,(2,5)) for s in rejected]
        for mode,exe in self.executables.items():self.run_cases(exe,cases,'deleted-'+mode)
        (self.work/'deletion-oracle.json').write_text(json.dumps(rejected,indent=2)+'\n',encoding='utf-8')
        self.records.append(dict(test='host-rejected-punctuation-deletions',cases=len(cases),modes=2,passed=True))

    def test_actual_wrong_statement_binding_and_modifier_are_rejected(self):
        source=(ROOT/'lang/bootstrap/expression.dg').read_text(encoding='utf-8')
        variants=[('assignment','return node(s,ASSIGN,ot,op,left,right,NONE);','return node(s,ASSIGN,ot,op,right,left,NONE);','{a=b;}',1),
                  ('field-public','if (*s).status==0&&public_field{(*s).nodes[item].flags=1;}',
                   'if (*s).status==0&&public_field{(*s).nodes[item].flags=0;}','module a;struct S{pub x:u64}',2)]
        for name,old,new,text,entry in variants:
            self.assertEqual(source.count(old),1)
            root=self.work/('bad-'+name);(root/'bootstrap').mkdir(parents=True)
            for file in ('lexer.dg','unicode.dg','syntax.dg'):shutil.copyfile(ROOT/'lang/bootstrap'/file,root/'bootstrap'/file)
            (root/'bootstrap/expression.dg').write_text(source.replace(old,new,1),encoding='utf-8')
            for mode in ('debug','release'):
                exe=self.build(root,mode,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'AST'):self.run_cases(exe,[(text,100,128,entry,0)],'bad-'+name+'-'+mode)
                self.records.append(dict(test='actual-bad-Dong',variant=name,mode=mode,rejected_by='AST',passed=True))


if __name__=='__main__':unittest.main()
