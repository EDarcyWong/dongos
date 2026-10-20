"""Execute Dong lexer -> expression AST, compare the independent host parser."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import unittest
import uuid

from lang.dongc import compile_file, CompileError
from lang.dongc.frontend import Parser, lex
from lang.dongc.model import constant_op, function_signature, ALIASES
from lang.tests.test_dongc import tool, nasm_flags
from lang.tests.test_bootstrap_lexer import KINDS

ROOT = Path(__file__).resolve().parents[2]
NONE = 2**64-1
HARNESS = r'''
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <sys/mman.h>
#endif
#ifndef PROBE_SOURCE
#define PROBE_SOURCE "sizeof(u64)+((1 as u64)*2)"
#define PROBE_MODE 1
#endif
#define ABI __attribute__((sysv_abi))
typedef struct {uint64_t kind,start,end,line,column,value_start,value_length;} Token;
typedef struct {uint64_t count,used,code,start,line,column;} LexResult;
typedef struct {uint64_t kind,token,op,a,b,c,next,flags;} Node;
typedef struct {uint64_t root,used,next,code,error;} Result;
_Static_assert(sizeof(Token)==56 && sizeof(Node)==64 && sizeof(Result)==40,"Dong layout");
extern uint64_t ABI dong_bootstrap_lex(const uint8_t*,uint64_t,Token*,uint64_t,uint8_t*,uint64_t,LexResult*);
extern uint64_t ABI dong_bootstrap_expression(const uint8_t*,uint64_t,const Token*,uint64_t,uint64_t,Node*,uint64_t,uint64_t,uint8_t,Result*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n){
 fprintf(stderr,"panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);
}
static void rd(void*p,size_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void wr(const void*p,size_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static int filled(const void*p,size_t n){const uint8_t*b=p;for(size_t i=0;i<n;i++)if(b[i]!=0xa5)return 0;return 1;}
static void readonly_inputs(void){
 const char text[]=PROBE_SOURCE;uint8_t*s;Token*t;
#ifdef _WIN32
 s=VirtualAlloc(NULL,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
 t=VirtualAlloc(NULL,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
#else
 s=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 t=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 if(s==MAP_FAILED||t==MAP_FAILED)exit(97);
#endif
 if(!s||!t)exit(97);
 memcpy(s,text,sizeof(text)-1);uint8_t strings[256];LexResult lr;Node nodes[256];Result result;
 if(dong_bootstrap_lex(s,sizeof(text)-1,t,64,strings,sizeof(strings),&lr))exit(97);
#ifdef _WIN32
 DWORD old;
 if(!VirtualProtect(s,4096,PAGE_READONLY,&old)||!VirtualProtect(t,4096,PAGE_READONLY,&old))exit(97);
#else
 if(mprotect(s,4096,PROT_READ)||mprotect(t,4096,PROT_READ))exit(97);
#endif
 if(dong_bootstrap_expression(s,sizeof(text)-1,t,lr.count,0,nodes,256,128,PROBE_MODE,&result))exit(98);
#ifdef _WIN32
 VirtualFree(s,0,MEM_RELEASE);VirtualFree(t,0,MEM_RELEASE);
#else
 munmap(s,4096);munmap(t,4096);
#endif
}
static void invalid(void){
 uint64_t memory[128],saved[128];Token*t=(Token*)(memory+8);Node*n=(Node*)(memory+40);Result*r=(Result*)(memory+96);
 const uint8_t *s=(uint8_t*)memory;
 for(unsigned i=0;i<15;i++){
  memset(memory,0xa5,sizeof(memory));((uint8_t*)memory)[0]='a';
  t[0]=(Token){1,0,1,1,1,0,0};t[1]=(Token){0,1,1,1,2,0,0};
  if(i==12){t[0].kind=0;}
  if(i==13){t[1].end=2;}
  if(i==14){t[1].start=0;}
  memcpy(saved,memory,sizeof(memory));uint64_t code;
  switch(i){
   case 0:code=dong_bootstrap_expression(s,1,t,2,0,n,2,64,1,NULL);break;
   case 1:code=dong_bootstrap_expression(NULL,1,t,2,0,n,2,64,1,r);break;
   case 2:code=dong_bootstrap_expression(s,1,NULL,2,0,n,2,64,1,r);break;
   case 3:code=dong_bootstrap_expression(s,1,t,UINT64_MAX,0,n,2,64,1,r);break;
   case 4:code=dong_bootstrap_expression(s,1,t,2,0,n,UINT64_MAX,64,1,r);break;
   case 5:code=dong_bootstrap_expression(s,1,t,2,2,n,2,64,1,r);break;
   case 6:code=dong_bootstrap_expression(s,1,t,2,0,n,2,0,1,r);break;
   case 7:code=dong_bootstrap_expression(s,1,t,2,0,n,2,257,1,r);break;
   case 8:code=dong_bootstrap_expression(s,1,t,2,0,(Node*)((uint8_t*)n+1),2,64,1,r);break;
   case 9:code=dong_bootstrap_expression(s,1,t,2,0,(Node*)t,2,64,1,r);break;
   case 10:code=dong_bootstrap_expression(s,1,t,2,0,n,2,64,1,(Result*)n);break;
   case 11:code=dong_bootstrap_expression((void*)(uintptr_t)UINT64_MAX,1,t,2,0,n,2,64,1,r);break;
   default:code=dong_bootstrap_expression(s,1,t,2,0,n,2,64,1,r);break;
  }
  if(code!=1||memcmp(saved,memory,sizeof(memory))){fprintf(stderr,"invalid preflight %u\n",i);exit(93);}
 }
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 invalid();readonly_inputs();uint64_t count;rd(&count,8);
 while(count--){
  uint64_t h[5];rd(h,sizeof(h));uint64_t len=h[0],cap=h[1];
  if(len>100000||cap>200064)exit(94); /* 2 * maximum source bytes + 64 nodes */
  uint8_t *s=malloc(len+32),*strings=malloc(len+1),*scopy=malloc(len+1);
  uint64_t tc=len+1;uint8_t*tb=malloc(tc*56+32);Token*t=(Token*)(tb+16);
  uint8_t*nb=malloc(cap*64+32);Node*n=(Node*)(nb+16);
  if(!s||!strings||!scopy||!tb||!nb)exit(95);
  memset(s,0xa5,len+32);memset(tb,0xa5,tc*56+32);memset(nb,0xa5,cap*64+32);
  rd(s+16,len);memcpy(scopy,s+16,len);LexResult lr;
  if(dong_bootstrap_lex(s+16,len,t,tc,strings,len,&lr)){fprintf(stderr,"fixture lexer failed\n");exit(96);}
  uint8_t*tcopy=malloc(tc*56);if(!tcopy)exit(95);memcpy(tcopy,t,tc*56);
  uint64_t meta[9];memset(meta,0xa5,sizeof(meta));Result*r=(Result*)(meta+2);
  uint64_t status=dong_bootstrap_expression(s+16,len,t,lr.count,h[4],n,cap,h[2],(uint8_t)h[3],r);
  uint64_t guard=filled(s,16)&&filled(s+16+len,16)&&!memcmp(scopy,s+16,len)&&
   filled(tb,16)&&filled(tb+16+tc*56,16)&&!memcmp(tcopy,t,tc*56)&&
   filled(nb,16)&&filled(nb+16+cap*64,16)&&filled(meta,16)&&filled(meta+7,16);
  if(status==1)guard=guard&&filled(r,40)&&filled(n,cap*64);
  else guard=guard&&status==r->code&&r->used<=cap&&r->next<lr.count&&r->error<lr.count&&
    filled(n+r->used,(cap-r->used)*64)&&(status?r->root==UINT64_MAX:r->root<r->used);
  uint64_t response[8]={status,r->root,r->used,r->next,r->code,r->error,guard,lr.count};
  wr(response,sizeof(response));wr(n,cap*64);
  free(s);free(strings);free(scopy);free(tb);free(nb);free(tcopy);
 }return 0;
}
'''


def host_type(typ, lengths):
    sig = function_signature(typ)
    if sig:
        return ('fn', sig.unsafe, sig.abi, tuple(host_type(p, lengths) for p in sig.params), host_type(sig.returns, lengths))
    if typ.startswith(('?', '!')):
        return (typ[0], host_type(typ[1:], lengths))
    if typ.startswith('*'):
        readonly = typ.startswith('*const ')
        return ('ptr', readonly, host_type(typ[7:] if readonly else typ[1:], lengths))
    if typ.startswith('[]'):
        readonly = typ.startswith('[]const ')
        return ('slice', readonly, host_type(typ[8:] if readonly else typ[2:], lengths))
    if typ.startswith('['):
        at = typ.index(']');count = typ[1:at]
        count = host_tree(lengths[count], lengths) if count.startswith('@') else int(count)
        return ('array-type', count, host_type(typ[at+1:], lengths))
    return ('type', typ)


def host_tree(e, lengths=None):
    lengths = lengths or {}
    convert = lambda child: host_tree(child, lengths)
    if e is None:
        return None
    k = e.kind
    if k in ('integer', 'boolean', 'string', 'name', 'error'):
        return (k, e.value)
    if k == 'null':
        return (k,)
    if k == 'call':
        callee = ('name', e.value) if isinstance(e.value, str) else convert(e.value)
        return (k, callee, tuple(convert(a) for a in e.args))
    if k == 'array':
        count = e.value if isinstance(e.value, int) else convert(e.value)
        return (k, count, tuple(convert(a) for a in e.args))
    if k == 'cast':
        return (k, host_type(e.value, lengths), tuple(convert(a) for a in e.args))
    if k == 'layout':
        name, typ, field = e.value
        return (k, (name, host_type(typ, lengths), field), ())
    if k == 'struct':
        return (k, (e.value[0], tuple(e.value[1])), tuple(convert(a) for a in e.args))
    return (k, e.value, tuple(convert(a) for a in e.args))


def actual_tree(nodes, root, tokens, require_all=True):
    seen = set()

    def dotted(v):
        return v[1] if v[0]=='name' else dotted(v[2][0])+'.'+v[1]

    def numeric(v):
        if v[0] == 'integer': return v[1]
        if v[0] == 'unary' and v[1] in ('-', '~'):
            x = numeric(v[2][0]);return -x if v[1]=='-' else ~x
        if v[0] == 'binary': return constant_op(v[1], numeric(v[2][0]), numeric(v[2][1]))
        raise ValueError('deferred constant')

    def count_value(v):
        try: return numeric(v)
        except ValueError: return v

    def children(first):
        result, visited = [], set()
        while first != NONE:
            assert first not in visited, 'cyclic argument list'
            visited.add(first)
            result.append(visit(first))
            first = nodes[first][6]
        return tuple(result)

    def visit(index):
        if index == NONE:
            return None
        assert 0 <= index < len(nodes), 'AST child index'
        assert index not in seen, 'AST cycle or shared mutable node'
        seen.add(index)
        k, t, op, a, b, c, nxt, flags = nodes[index]
        assert 0 <= t < len(tokens) and flags in (0, 1), 'AST token/flags'
        token = tokens[t]
        if k == 1:
            v = token.value.replace('_', '')
            return ('integer', int(v, 16 if v.startswith('0x') else 2 if v.startswith('0b') else 10))
        if k == 2:
            return ('boolean', token.kind == 'true')
        if k == 3:
            return ('null',)
        if k == 4:
            return ('string', token.value.encode('latin-1'))
        if k == 5:
            return ('name', token.value)
        if k in (6, 7, 8, 9, 16):
            assert op == KINDS[token.kind], 'operator token mismatch'
            kinds = {6:'unary', 7:'try', 8:'binary', 9:'orelse', 16:'exit'}
            value = None if k in (7, 9) else token.kind
            args = (visit(a), visit(b)) if k in (8, 9) else (() if a == NONE else (visit(a),))
            return (kinds[k], value, args)
        if k == 10:
            return ('call', visit(a), children(b))
        if k == 11:
            return ('field', token.value, (visit(a),))
        if k == 12:
            return ('index', None, (visit(a), visit(b)))
        if k == 13:
            return ('slice', None, (visit(a), visit(b), visit(c)))
        if k == 14:
            return ('array', None, children(a))
        if k == 15:
            return ('array', count_value(visit(b)), (visit(a),))
        if k == 17:
            path = visit(a)
            return ('error', dotted(path))
        if k == 18:
            return ('cast', visit(b), (visit(a),))
        if k == 19:
            name = dotted(visit(a));fields = children(b)
            return ('struct', (name, tuple(f[0] for f in fields)), tuple(f[1] for f in fields))
        if k == 20:
            return ('layout', (token.value, visit(a), None if op==NONE else tokens[op].value), ())
        if k == 21:
            return (token.value, visit(a))
        if k == 32:
            name = dotted(visit(a));return ('type', ALIASES.get(name, name))
        if k in (33, 34):
            return ('ptr' if k==33 else 'slice', bool(flags), visit(a))
        if k == 35:
            element = visit(a);return ('array-type', count_value(visit(b)), element)
        if k in (36, 37): return ('?' if k==36 else '!', visit(a))
        if k == 38:
            return ('fn', bool(flags), 'win64' if op else 'sysv64', children(a), visit(b))
        if k == 39: return visit(a)
        if k == 64: return ('block', children(a))
        if k == 65: return ('binding', {260:'const',261:'let',262:'var'}[op], token.value, visit(a), visit(b))
        if k == 66: return ('return', visit(a))
        if k in (67, 68):
            condition, body, other = visit(a), visit(b), visit(c)
            if other is not None and other[0]=='block' and len(other[1])==1 and other[1][0][0]=='if':
                other = other[1][0]
            return ('if' if k==67 else 'while', condition, body, other)
        if k == 69: return ('loop', visit(a))
        if k == 70: return ('for', visit(a)[1], visit(b), visit(c))
        if k == 71: return ('range', visit(a), visit(b))
        if k == 72: return ('defer', visit(a))
        if k == 73: return ('match', visit(a), children(b))
        if k == 74: return (visit(a), visit(b))
        if k == 75:
            if op in (286, 287): return ('bool', op==286, None)
            if op == 288: return ('null', None, None)
            name = dotted(visit(a));binding = visit(b)
            special = name in ('_', 'some', 'ok', 'err')
            return ('wildcard' if name=='_' else name if special else 'enum', None if special else name,
                    None if binding is None else binding[1])
        if k == 76: return ('unsafe', visit(a))
        if k == 77: return ('asm', token.value)
        if k in (78, 79): return ('break' if k==78 else 'continue',)
        if k == 80: return ('assign', token.kind, visit(a), visit(b))
        if k == 81: return ('call-statement', visit(a))
        if k == 96:
            name = dotted(visit(a));items = children(b)
            imports = tuple(i for i in items if i[0]=='import')
            decls = tuple(sorted((i for i in items if i[0]=='decl'), key=lambda d:(d[2][0],d[2][1])))
            return ('module', name, imports, decls)
        if k == 97:
            name = dotted(visit(a));alias = visit(b)
            return ('import', name, name.split('.')[-1] if alias is None else alias[1])
        if k == 98: return (op, visit(a), visit(b))
        if k == 99:
            decl = visit(a);attrs = children(b);table = {i[0]:(i[1],i[2]) for i in attrs}
            public = 259 in table;packed = 269 in table
            align = count_value(table[270][0]) if 270 in table else None
            external = decl[0]=='function' and decl[-1] is None
            unsafe = 268 in table or external
            abi = table[267][0][1].decode('ascii') if 267 in table else 'sysv64'
            export = table[271][0][1].decode('ascii') if 271 in table else None
            if 267 in table and table[267][1] is not None: export = table[267][1][1].decode('ascii')
            if external and export is None: export = decl[1]
            return ('decl', (public,packed,align,unsafe,abi,export,external), decl)
        if k == 100: return ('function', token.value, children(a), visit(b), visit(c))
        if k == 101: return ('struct-decl', token.value, children(a))
        if k == 102: return (token.value, visit(a), bool(flags))
        if k == 103: return ('enum-decl', token.value, children(a))
        if k == 104: return (token.value, visit(a))
        if k == 105: return ('error-decl', token.value, count_value(visit(b)))
        if k == 106: return ('alias-decl', token.value, visit(a))
        if k == 107: return ('const' if op==260 else 'global', token.value, visit(a), visit(b))
        if k == 108: return (token.value, visit(a), bool(flags))
        raise AssertionError(('unknown AST kind', k))

    tree = visit(root)
    if require_all: assert len(seen) == len(nodes), 'unreachable allocated AST node'
    return tree


class BootstrapExpressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest('native expression parser requires NASM/GCC')
        cls.work = ROOT/'build/test/bootstrap-expression'/('run-'+uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS, encoding='utf-8')
        cls.records = []
        cls.inputs = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in [ROOT/'lang/bootstrap/expression.dg', ROOT/'lang/bootstrap/lexer.dg',
                                ROOT/'lang/bootstrap/unicode.dg', Path(__file__)]}
        cls.executables = {mode:cls.build(ROOT/'lang', mode, mode) for mode in ('debug', 'release')}

    @classmethod
    def command(cls, args, label):
        r = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=120)
        (cls.work/(label+'.log')).write_text(r.stdout+r.stderr, encoding='utf-8')
        if r.returncode: raise AssertionError((label, r.returncode, r.stdout, r.stderr))

    @classmethod
    def build(cls, root, mode, label):
        result = compile_file(root/'bootstrap/expression.dg', roots=[root], mode=mode)
        asm = cls.work/(label+'.asm');asm.write_text(result.assembly, encoding='utf-8')
        obj = cls.work/(label+'.o');exe = cls.work/(label+('.exe' if os.name=='nt' else ''))
        for fmt in ('elf64', 'win64'):
            target = obj if fmt==('win64' if os.name=='nt' else 'elf64') else cls.work/(label+'.'+fmt+'.o')
            cls.command([cls.nasm, '-f', fmt, *nasm_flags(cls.nasm), '-o', target, asm], label+'-'+fmt)
        cls.command([cls.cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                     *([] if os.name=='nt' else ['-no-pie']), cls.work/'probe.c', obj, '-o', exe], label+'-link')
        return exe

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls, 'work'): return
        files = {p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in cls.work.rglob('*') if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs, artifact_sha256=files,
            records=cls.records, L3_selfhost_complete=False, OS_VM_built=False), indent=2)+'\n', encoding='utf-8')

    def run_cases(self, exe, cases, label):
        payload = bytearray(struct.pack('<Q', len(cases)))
        for source, cap, depth, allow, start, expected_status in cases:
            raw = source.encode('utf-8');payload.extend(struct.pack('<5Q', len(raw), cap, depth, allow, start));payload.extend(raw)
        (self.work/(label+'.input')).write_bytes(payload)
        r = subprocess.run([str(exe)], input=payload, capture_output=True, timeout=120)
        (self.work/(label+'.output')).write_bytes(r.stdout)
        (self.work/(label+'.stderr')).write_bytes(r.stderr)
        self.assertEqual(r.returncode, 0, r.stderr)
        at = 0
        for i, (source, cap, depth, allow, start, expected_status) in enumerate(cases):
            status, root, used, nxt, code, error, guard, count = struct.unpack_from('<8Q', r.stdout, at);at+=64
            nodes = [struct.unpack_from('<8Q', r.stdout, at+64*j) for j in range(used)]
            at += cap*64
            self.assertEqual(guard, 1, (label, i, 'guard/atomicity'))
            self.assertEqual(status, expected_status, (label, i, source, 'status', error))
            if status == 1: continue
            tokens = lex(source);self.assertEqual(count, len(tokens))
            self.assertEqual(code, status)
            if status in (0, 2):
                parser = Parser(tokens);parser.index=start
                try: expected = parser.expression(allow_struct=bool(allow))
                except CompileError as failure:
                    self.assertEqual(status, 2, (label, i, failure))
                    error_index = next(j for j, token in enumerate(tokens) if token is failure.token)
                    self.assertEqual(error, error_index, (label, i, source, 'error position'))
                    continue
                self.assertEqual(status, 0, (label, i, source))
                self.assertEqual(nxt, parser.index, (label, i, 'next token'))
                self.assertEqual(actual_tree(nodes, root, tokens), host_tree(expected, parser.type_lengths), (label, i, source, 'AST'))
        self.assertEqual(at, len(r.stdout))

    def test_precedence_postfix_literals_and_generated_trees(self):
        sources = ['1+2*3', '(1+2)*3', 'a-b-c', 'a orelse b orelse c', 'a||b&&c==d|e^f&g<<h+i*j',
                   'try f(x)+1', '-*p', '&a[2]', '!true', '~0xffff_ffff_ffff_ffff_ffff', 'null',
                   '"你好\\0\\xff"', 'α.β[1..n](x,y,).field', 'f()()', 'f((g))(h(1,2),3)',
                   'a[..]', 'a[..n]', 'a[1..]', 'a[1..n]', '[1,2,3,]', '[x;N+1]', '[0;2+3]',
                   'error.pkg.name', 'a orelse return 42;', 'a orelse break;', 'a orelse continue {',
                   'a orelse return;', '(a<b)==c', 'a==(b<c)', 'a < b {', 'x;1+2', 'f(a orelse return, 2)']
        rng = random.Random(0xE871)
        def generate(depth):
            if not depth: return rng.choice(['0', '1', 'foo', 'α', 'null', 'true', '0x1234'])
            choice = rng.randrange(6)
            if choice == 0: return '('+generate(depth-1)+' '+rng.choice(['+', '-', '*', '<<', '&', '||', 'orelse'])+' '+generate(depth-1)+')'
            if choice == 1: return rng.choice(['-', '~', '!', 'try '])+'('+generate(depth-1)+')'
            if choice == 2: return 'f('+generate(depth-1)+','+generate(depth-1)+',)'
            if choice == 3: return '('+generate(depth-1)+').field[1..n]'
            if choice == 4: return '['+generate(depth-1)+','+generate(depth-1)+']'
            return generate(0)
        sources += [generate(rng.randrange(1, 5)) for _ in range(700)]
        cases = [(s, len(lex(s))*2, 128, int(s!='a < b {'), 2 if s=='x;1+2' else 0, 0) for s in sources]
        operators = ['orelse', '||', '&&', '==', '!=', '<', '<=', '>', '>=', '|', '^', '&', '<<', '>>', '+', '-', '*', '/', '%']
        comparisons = {'==', '!=', '<', '<=', '>', '>='}
        for first in operators:
            for second in operators:
                s = f'a {first} b {second} c'
                cases.append((s, 20, 128, 1, 0, 2 if first in comparisons and second in comparisons else 0))
        for mode, exe in self.executables.items(): self.run_cases(exe, cases, 'syntax-'+mode)
        self.records.append(dict(test='host-parser-AST-differential', cases=len(cases), modes=2, passed=True))

    def test_errors_capacity_depth_and_explicit_unsupported(self):
        bad = ['', 'a+', 'f(', 'f(,)', 'f(a,,b)', 'a[]', 'a[1', '(1', '[]', '[1,', '[1;]',
               'a.', 'error.', 'error.foo.', 'a<b<c', 'a==b!=c', 'a orelse break value;', '[1 2]']
        cases = [(s, max(10, len(lex(s))*2), 128, 1, 0, 2) for s in bad]
        cases += [(s, 100, 128, 1, 0, 5) for s in ('a as extern "unknown" fn()void',)]
        cases += [('a+b', 3, 128, 1, 0, 0), ('a+b', 2, 128, 1, 0, 3), ('a', 0, 128, 1, 0, 3),
                  ('a', 1, 1, 1, 0, 0), ('-a', 3, 1, 1, 0, 4), ('((a))', 3, 2, 1, 0, 4),
                  ('('+('('*125)+'a'+(')'*125)+')', 1, 128, 1, 0, 0),
                  ('('*130+'a'+')'*130, 1, 128, 1, 0, 4)]
        cases += [(s,cap,128,1,0,status) for s,cap,status in
                  [('x as u64',4,0),('x as u64',3,3),('P{x:1}',4,0),('P{x:1}',3,3),
                   ('sizeof(u64)',3,0),('sizeof(u64)',2,3)]]
        for mode, exe in self.executables.items(): self.run_cases(exe, cases, 'bounds-'+mode)
        self.records.append(dict(test='syntax-capacity-depth-unsupported', cases=len(cases), modes=2,
                                 invalid_preflights_per_process=15, passed=True))

    def test_expressions_extracted_from_actual_dong_modules(self):
        class RecordingParser(Parser):
            def __init__(self, tokens):
                super().__init__(tokens);self.expressions = []

            def expression(self, minimum=0, *, allow_struct=True):
                start = self.index
                result = super().expression(minimum, allow_struct=allow_struct)
                if minimum == 0:
                    self.expressions.append((start, self.index, allow_struct, result))
                return result

        corpus, scanned, excluded = {}, {}, {}
        reserved = {'lang/bootstrap/bigint_div.dg', 'lang/bootstrap/bigint_bits.dg',
                    'lang/bootstrap/constant_arithmetic.dg', 'lang/bootstrap/type_layout.dg',
                    'lang/std/core/arena.dg', 'lang/std/core/utf8.dg', 'lang/bootstrap/source_position.dg'}
        for parent in ('lang', 'kernel', 'services'):
            for path in sorted((ROOT/parent).rglob('*.dg')):
                if path.relative_to(ROOT).as_posix() in reserved: continue
                text = path.read_text(encoding='utf-8-sig')
                try:
                    tokens = lex(text);parser = RecordingParser(tokens);parser.parse()
                except CompileError as failure:
                    excluded[path.relative_to(ROOT).as_posix()] = failure.message
                    continue
                scanned[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
                positions = {};line, column = 1, 1
                for i, ch in enumerate(text):
                    positions[line, column] = i
                    if ch=='\n': line, column = line+1, 1
                    else: column += 1
                positions[line, column] = len(text)
                for start, end, allow, tree in parser.expressions:
                    first, last = tokens[start], tokens[end]
                    snippet = text[positions[first.line, first.column]:positions[last.line, last.column]].strip()
                    if snippet and len(snippet)<=2000:
                        # Preserve an expression boundary for orelse control
                        # exits; EOF itself is not a break/continue delimiter.
                        corpus.setdefault((snippet+';', allow), None)
        self.assertGreater(len(scanned), 200)
        self.assertGreater(len(corpus), 1000)
        cases = [(s, len(lex(s))*2, 128, int(allow), 0, 0) for s, allow in corpus]
        for mode, exe in self.executables.items(): self.run_cases(exe, cases, 'corpus-'+mode)
        (self.work/'corpus.json').write_text(json.dumps(dict(scanned_sha256=scanned,
            excluded_unparseable_modules=excluded, unique_expressions=len(cases),
            typed_expressions_excluded=False, reserved_tasks_excluded=sorted(reserved),
            maximum_snippet_characters=2000), indent=2)+'\n', encoding='utf-8')
        self.records.append(dict(test='real-module-expressions', modules=len(scanned),
                                 cases=len(cases), modes=2, passed=True))

    def test_cast_structure_layout_and_full_type_syntax(self):
        types = ['u64', 'usize', 'isize', 'pkg.Type', '*const u8', '**u64', '[]const u8',
                 '[2+3]u64', '[N+1]*const u8', '?*u64', '!void', '!?[]u8',
                 'fn()void', 'unsafe fn(x:u64, y:[]const u8,)!u64',
                 'extern "win64" fn(u64,[]u8)u64', 'extern "\\x73ysv64" unsafe fn()noreturn',
                 '[sizeof(u32)]fn(a:*const u8)[]u64']
        sources = ['x as '+t for t in types] + ['sizeof('+t+')' for t in types]
        sources += ['Point{}', 'pkg.Point{x:1,y:f(2),}', 'Outer{inner:Inner{x:1},values:[2,3]}',
                    'offsetof(Point,field)', 'alignof([N]Point)', '-x as u64 + 1',
                    '(Point{x:1}).x', 'a as *u64 as usize', 'sizeof([N+1]u64)+sizeof([M]u8)',
                    'f(x as u64, Point{x:2}, offsetof(A,b))', 'ifname {']
        cases = [(s, len(lex(s))*3, 128, int(s!='ifname {'), 0, 0) for s in sources]
        for mode, exe in self.executables.items(): self.run_cases(exe, cases, 'typed-'+mode)
        self.records.append(dict(test='typed-expressions', cases=len(cases), modes=2, passed=True))

    def test_actual_bad_precedence_and_chained_comparison_are_rejected(self):
        source = (ROOT/'lang/bootstrap/expression.dg').read_text(encoding='utf-8')
        variants = [('precedence', 'if k==1066||k==1071||k==1061{return 9;}',
                     'if k==1066||k==1071||k==1061{return 8;}', '1+2*3', 0, 'AST'),
                    ('comparison', 'if p==3&&(*s).nodes[left].kind==BINARY',
                     'if p==99&&(*s).nodes[left].kind==BINARY', 'a<b<c', 2, 'status'),
                    ('publication', 'if s.status!=0{root=NONE;}',
                     'if s.status!=0{root=0;}', 'a+', 2, 'guard/atomicity'),
                    ('readonly-type', 'let id=node(s,tag,t,0,child,NONE,NONE);if (*s).status==0&&readonly{(*s).nodes[id].flags=1;}',
                     'let id=node(s,tag,t,0,child,NONE,NONE);if (*s).status==0&&readonly{(*s).nodes[id].flags=0;}',
                     'x as *const u8',0,'AST'),
                    ('layout-field', '(*s).nodes[left].op=field;', '(*s).nodes[left].op=NONE;',
                     'offsetof(Point,field)',0,'AST')]
        for label, old, new, text, status, reason in variants:
            self.assertEqual(source.count(old), 1)
            root = self.work/('bad-'+label);(root/'bootstrap').mkdir(parents=True)
            for name in ('lexer.dg', 'unicode.dg'): shutil.copyfile(ROOT/'lang/bootstrap'/name, root/'bootstrap'/name)
            (root/'bootstrap/expression.dg').write_text(source.replace(old, new, 1), encoding='utf-8')
            for mode in ('debug', 'release'):
                exe = self.build(root, mode, label+'-'+mode)
                with self.assertRaisesRegex(AssertionError, reason):
                    self.run_cases(exe, [(text, 20, 128, 1, 0, status)], 'bad-'+label+'-'+mode)
                self.records.append(dict(test='actual-wrong-Dong-source', variant=label, mode=mode,
                                         rejected_by=reason, passed=True))


if __name__ == '__main__': unittest.main()
