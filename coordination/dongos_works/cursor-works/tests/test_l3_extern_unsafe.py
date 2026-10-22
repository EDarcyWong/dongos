"""L3EXTUNSAFE1: bodyless extern declarations default to unsafe.

Builds the native declaration/runtime frontend from the 13 real bootstrap
sources with the independent candidate semantic_types overlay, and compares it
with the Python seed.  The candidate is a copy of the frozen mainline
semantic_types plus the bodyless-extern unsafe default in top_function.

Covered: free functions and methods, both call forms, default/explicit unsafe,
bodyful SysV definitions, win64 ABI, explicit link names, imports, same-name
method candidates, inferred function pointers, selected callee Info identity,
real bad-Dong negative, capacity and immutable-input/guard checks.
"""
from __future__ import annotations
import hashlib, json, re, shutil, struct, subprocess, sys, unittest, uuid
from pathlib import Path

WORKS = Path(__file__).resolve().parents[2]
ROOT = WORKS
if not (ROOT / 'lang').is_dir() and (WORKS / 'project.json').is_file():
    source = Path(json.loads((WORKS / 'project.json').read_text(encoding='utf-8'))['source_root'])
    ROOT = (WORKS / source).resolve() if not source.is_absolute() else source
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lang.dongc import compile_source, compile_file
from lang.dongc.model import CompileError
from lang.tests import test_bootstrap_semantic_types as decl
from lang.tests import test_bootstrap_semantic_runtime as runtime
from lang.tests.test_dongc import tool

CANDIDATE = WORKS / 'cursor-works/l3-extern-unsafe/src/bootstrap/semantic_types.dg'
DOC = WORKS / 'cursor-works/l3-extern-unsafe/docs/default-extern-unsafe.md'
NONE = decl.NONE
TYPE, PRIVATE, UNSUPPORTED, UNSAFE, CAPACITY = 3, 10, 8, 13, 2
FUNCTION = 19
FIX = 'if n.c==NONE{flags|=2;}'
FIX_BLOCK = (' // Bodyless declarations are external; the seed marks every external function' + chr(10) +
             ' // unsafe by default, with or without an explicit ABI. Keep the ABI bit and' + chr(10) +
             ' // enforce the same unsafe call boundary for free functions and methods.' + chr(10) +
             ' if n.c==NONE{flags|=2;}' + chr(10))
FILES = ['semantic_types.dg', 'binding.dg', 'modules.dg', 'names.dg', 'expression.dg', 'syntax.dg',
         'lexer.dg', 'unicode.dg', 'constant_arithmetic.dg', 'type_layout.dg', 'bigint.dg',
         'bigint_div.dg', 'bigint_bits.dg']

SYM_DIAG = r'''
  for(uint64_t zi=0;zi<nr.count;zi++){
   Symbol zq=sy[zi];uint64_t zg=u[zq.unit].ns+zq.decl,zt=((uint64_t*)w.pools[2].p)[zg];
   uint64_t zk=UINT64_MAX,zf=UINT64_MAX,zu=UINT64_MAX,zn=UINT64_MAX;
   if(zt<out->types){SType zst=((SType*)w.pools[0].p)[zt];zk=zst.kind;zf=zst.flags;zu=zst.unit;zn=zst.node;}
   Token ztok=t[u[zq.unit].ts+zq.name];
   fprintf(stderr,"SYM unit=%llu src=%llu start=%llu end=%llu kind=%llu typ=%llu type_kind=%llu type_flags=%llu type_unit=%llu type_node=%llu\n",
    (unsigned long long)zq.unit,(unsigned long long)u[zq.unit].source,
    (unsigned long long)ztok.data[1],(unsigned long long)ztok.data[2],
    (unsigned long long)zq.kind,(unsigned long long)zt,(unsigned long long)zk,
    (unsigned long long)zf,(unsigned long long)zu,(unsigned long long)zn);
  }
'''

INFO_MARKER = ' wr(&code,8);wr(out,64);wr(&good,8);'
INFO_DIAG = r'''
 if(!code){for(uint64_t j=0;j<un;j++){for(uint64_t k=0;k<u[j].nc;k++){
  uint64_t g=u[j].ns+k;const Node*call=n+g;if(call->data[0]!=10)continue;
  uint64_t cg=u[j].ns+call->data[3];const uint64_t*ci=(uint64_t*)flow.pools[0].p+3*cg;
  const uint64_t*ri=(uint64_t*)flow.pools[0].p+3*g;
  uint64_t ct=ci[0],kind=UINT64_MAX,tunit=UINT64_MAX,tnode=UINT64_MAX,tflags=UINT64_MAX;
  if(ct!=UINT64_MAX&&ct<out->types){SType st=((SType*)w.pools[0].p)[ct];kind=st.kind;tunit=st.unit;tnode=st.node;tflags=st.flags;}
  fprintf(stderr,"CALL unit=%llu node=%llu ref=%llu target=%llu callee_type=%llu result_type=%llu type_kind=%llu type_unit=%llu type_node=%llu type_flags=%llu\n",
   (unsigned long long)j,(unsigned long long)k,(unsigned long long)refs[cg].kind,
   (unsigned long long)refs[cg].target,(unsigned long long)ct,(unsigned long long)ri[0],
   (unsigned long long)kind,(unsigned long long)tunit,(unsigned long long)tnode,(unsigned long long)tflags);
 }}}
'''

# Native status == 0 iff the Python seed accepts.  Seed rejection is UNSAFE for
# every default-extern call; the native side must report the same 13 code.
ALIGNED = [
    # bodyless extern free functions: unsafe by default, both ABIs
    ('extern "sysv64" fn host()u64;pub fn f()u64{return host();}', UNSAFE),
    ('extern "sysv64" fn host()u64;pub fn f()u64{unsafe{return host();}}', 0),
    ('extern "win64" fn host()u64;pub fn f()u64{return host();}', UNSAFE),
    ('extern "win64" fn host()u64;pub fn f()u64{unsafe{return host();}}', 0),
    # explicit unsafe bodyless declaration still requires an unsafe call block
    ('unsafe extern "sysv64" fn host()u64;pub fn f()u64{return host();}', UNSAFE),
    ('unsafe extern "sysv64" fn host()u64;pub fn f()u64{unsafe{return host();}}', 0),
    # bodyless extern methods: both call forms
    ('pub struct S{pub x:u64}extern "sysv64"("host_method") fn(self:*S)get()u64;'
     'pub fn f(p:*S)u64{return p.get();}', UNSAFE),
    ('pub struct S{pub x:u64}extern "sysv64"("host_method") fn(self:*S)get()u64;'
     'pub fn f()u64{var s=S{x:7};return (&s).get();}', UNSAFE),
    ('pub struct S{pub x:u64}extern "sysv64"("host_method") fn(self:*S)get()u64;'
     'pub fn f(p:*S)u64{unsafe{return p.get();}}', 0),
    ('pub struct S{pub x:u64}extern "sysv64"("host_method") fn(self:*S)get()u64;'
     'pub fn f()u64{var s=S{x:7};unsafe{return (&s).get();}}', 0),
    ('pub struct S{pub x:u64}unsafe extern "sysv64"("host_method") fn(self:*S)get()u64;'
     'pub fn f(p:*S)u64{return p.get();}', UNSAFE),
    # bodyful SysV definitions keep the old default: safe unless explicitly unsafe
    ('pub extern "sysv64" fn host()u64{return 7;}pub fn f()u64{return host();}', 0),
    ('pub extern "win64" fn host()u64{return 7;}pub fn f()u64{return host();}', 0),
    ('pub unsafe extern "sysv64" fn host()u64{return 7;}pub fn f()u64{return host();}', UNSAFE),
    ('pub unsafe extern "sysv64" fn host()u64{return 7;}pub fn f()u64{unsafe{return host();}}', 0),
    # inferred function pointer keeps the declaration's unsafe bit
    ('extern "sysv64" fn host()u64;pub fn f()u64{let p=host;return p();}', UNSAFE),
    ('extern "sysv64" fn host()u64;pub fn f()u64{let p=host;unsafe{return p();}}', 0),
    # same-name method candidates select by receiver type, not by name alone
    ('pub struct S{pub x:u64}pub struct T{pub x:u64}extern "sysv64"("m1") fn(self:*S)get()u64;'
     'fn(self:*T)get()u64{return 1;}pub fn f(q:*T)u64{return q.get();}', 0),
    ('pub struct S{pub x:u64}pub struct T{pub x:u64}extern "sysv64"("m1") fn(self:*S)get()u64;'
     'fn(self:*T)get()u64{return 1;}pub fn f(p:*S)u64{return p.get();}', UNSAFE),
    # a same-name free function wins over method candidates for f(p)
    ('pub struct S{pub x:u64}fn get(p:*S)u64{return 1;}extern "sysv64"("m") fn(self:*S)get()u64;'
     'pub fn f(p:*S)u64{return get(p);}', 0),
    ('pub struct S{pub x:u64}fn get(p:*S)u64{return 1;}extern "sysv64"("m") fn(self:*S)get()u64;'
     'pub fn f(p:*S)u64{return p.get();}', UNSAFE),
    # receiver call on a bodyful method is unaffected by an extern sibling
    ('pub struct S{pub x:u64}pub struct T{pub x:u64}extern "sysv64"("m1") fn(self:*S)get()u64;'
     'fn(self:*T)get()u64{return 1;}pub fn f(q:*T)bool{return q.get()==1;}', 0),
]

MODULE_OK = [
    ([(0, 'a.dg', 'module a;import dep as d;pub fn f()u64{return d.host();}'),
      (0, 'dep.dg', 'module dep;pub extern "sysv64" fn host()u64;')], UNSAFE),
    ([(0, 'a.dg', 'module a;import dep as d;pub fn f()u64{unsafe{return d.host();}}'),
      (0, 'dep.dg', 'module dep;pub extern "sysv64" fn host()u64;')], 0),
    ([(0, 'a.dg', 'module a;import dep as d;pub fn f(p:*d.S)u64{return p.get();}'),
      (0, 'dep.dg', 'module dep;pub struct S{pub x:u64}'
                   'pub extern "sysv64"("m") fn(self:*S)get()u64;')], UNSAFE),
    ([(0, 'a.dg', 'module a;import dep as d;pub fn f(p:*d.S)u64{unsafe{return p.get();}}'),
      (0, 'dep.dg', 'module dep;pub struct S{pub x:u64}'
                   'pub extern "sysv64"("m") fn(self:*S)get()u64;')], 0),
]

FLAGS = [
    ('free-default', 'module a;extern "sysv64" fn host()u64;', {'host': [2]}),
    ('free-explicit-unsafe', 'module a;unsafe extern "sysv64" fn host()u64;', {'host': [2]}),
    ('free-win64-link-name', 'module a;extern "win64"("link_host") fn host()u64;', {'host': [3]}),
    ('method-default-link-name', 'module a;pub struct S{pub x:u64}'
     'extern "sysv64"("host_method") fn(self:*S)get()u64;', {'get': [2]}),
    ('method-explicit-unsafe', 'module a;pub struct S{pub x:u64}'
     'unsafe extern "sysv64"("host_method") fn(self:*S)get()u64;', {'get': [2]}),
    ('bodyful-sysv', 'module a;pub extern "sysv64" fn host()u64{return 7;}', {'host': [0]}),
    ('bodyful-win64-link-name', 'module a;pub extern "win64"("link_host") fn host()u64{return 7;}',
     {'host': [1]}),
    ('bodyful-plain', 'module a;pub fn host()u64{return 7;}', {'host': [0]}),
    ('bodyful-unsafe', 'module a;pub unsafe fn host()u64{return 7;}', {'host': [2]}),
    ('bodyful-method', 'module a;pub struct S{pub x:u64}fn(self:*S)get()u64{return 1;}', {'get': [0]}),
    ('same-name-methods', 'module a;pub struct S{pub x:u64}pub struct T{pub x:u64}'
     'extern "sysv64"("m1") fn(self:*S)get()u64;fn(self:*T)get()u64{return 1;}',
     {'get': [0, 2]}),
    ('inferred-pointer', 'module a;extern "sysv64" fn host()u64;'
     'pub fn f()u64{let p=host;unsafe{return p();}}', {'host': [2], 'f': [0]}),
]

INFO_CASES = [
    ('free-extern', 'module a;extern "sysv64" fn host()u64;'
     'pub fn f()u64{unsafe{return host();}}', 1),
    ('method-extern', 'module a;pub struct S{pub x:u64}extern "sysv64"("m") fn(self:*S)get()u64;'
     'pub fn f(p:*S)u64{unsafe{return p.get();}}', 1),
    ('same-name-methods', 'module a;pub struct S{pub x:u64}pub struct T{pub x:u64}'
     'extern "sysv64"("m1") fn(self:*S)get()u64;fn(self:*T)get()u64{return 1;}'
     'pub fn f(p:*S,q:*T)u64{let a=q.get();unsafe{return p.get()+a;}}', 2),
    ('inferred-pointer', 'module a;extern "sysv64" fn host()u64;'
     'pub fn f()u64{let p=host;unsafe{return p();}}', 1),
]


class L3ExternUnsafeTests(unittest.TestCase):
    wrapper = runtime.WRAPPER
    build = classmethod(runtime.BootstrapSemanticRuntimeTests.build.__func__)

    @classmethod
    def setUpClass(cls):
        cls.nasm, cls.cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest('native extern-unsafe semantics require NASM/GCC')
        cls.work = WORKS / 'cursor-works/build/L3EXTUNSAFE1' / ('run-' + uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        (cls.work / 'probe.c').write_text(runtime.HARNESS, encoding='utf-8')
        sym_harness = runtime.HARNESS.replace(' if(!code){', ' if(!code){' + SYM_DIAG, 1)
        assert sym_harness != runtime.HARNESS
        (cls.work / 'probe-sym.c').write_text(sym_harness, encoding='utf-8')
        info_harness = runtime.HARNESS.replace(INFO_MARKER, INFO_DIAG + INFO_MARKER, 1)
        assert info_harness != runtime.HARNESS
        (cls.work / 'probe-info.c').write_text(info_harness, encoding='utf-8')
        cls.files = FILES
        cls.candidate_paths = [CANDIDATE, DOC, Path(__file__)]
        cls.mainline = {p: hashlib.sha256((ROOT / 'lang/bootstrap' / p).read_bytes()).hexdigest()
                        for p in cls.files}
        cls.candidate_sha = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in cls.candidate_paths}
        cls.records = []
        cls.snapshot = cls.work / 'source'
        (cls.snapshot / 'bootstrap').mkdir(parents=True)
        for p in cls.files:
            shutil.copyfile(ROOT / 'lang/bootstrap' / p, cls.snapshot / 'bootstrap' / p)
        shutil.copyfile(CANDIDATE, cls.snapshot / 'bootstrap/semantic_types.dg')
        cls.executables = {m: cls.build(cls.snapshot, m, m) for m in ('debug', 'release')}
        cls.diag_executables = {}
        for label, cfile in (('sym', 'probe-sym.c'), ('info', 'probe-info.c')):
            cls.diag_executables[label] = {}
            for mode in ('debug', 'release'):
                exe = cls.work / (label + '-' + mode + '.exe')
                subprocess.run([cls.cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                                str(cls.work / cfile), str(cls.work / (mode + '.o')), '-o', str(exe)],
                               check=True, capture_output=True)
                cls.diag_executables[label][mode] = exe

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls, 'work'):
            return
        after_main = {p: hashlib.sha256((ROOT / 'lang/bootstrap' / p).read_bytes()).hexdigest()
                      for p in cls.files}
        after_cand = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in cls.candidate_paths}
        (cls.work / 'summary.json').write_text(json.dumps(dict(
            mainline_sha256=cls.mainline, mainline_stable=cls.mainline == after_main,
            candidate_sha256=cls.candidate_sha, candidate_stable=cls.candidate_sha == after_cand,
            records=cls.records, modes=['debug', 'release'], skips=0,
            L3G5_complete=False, OS_VM_built=False), indent=2) + chr(10), encoding='utf-8')

    # ---- payload / execution helpers -------------------------------------
    def payload(self, cases):
        out = bytearray(struct.pack('<Q', len(cases)))
        for c, _status, _expected in cases:
            out.extend(struct.pack('<14Q', c['roots'], c['entry'], len(c['files']),
                                   *[c[k] for k in ('units', 'tokens', 'strings', 'nodes',
                                                    'edges', 'states', 'depth')],
                                   c['semantic_depth'], c['pool'], c['cap'], 0))
            for root, path, data in c['files']:
                out.extend(struct.pack('<3Q', root, len(path), len(data)))
                out.extend(path)
                out.extend(data)
        return bytes(out)

    def parse_case(self, result, at):
        returned, code, nt, nf, nl, unchecked, u, t, detail, good = \
            struct.unpack_from('<10Q', result.stdout, at)
        at += 80
        self.assertEqual(good, 1, 'guards/immutable input/publication')
        self.assertEqual(returned, code, ('returned/publication', u, t, detail))
        self.assertEqual(unchecked, 0, ('unchecked initializers', u, t))
        if not code:
            sycount, = struct.unpack_from('<Q', result.stdout, at)
            at += 8
            for _ in range(sycount):
                row = struct.unpack_from('<11Q', result.stdout, at)
                at += 88
                at += row[9] * 4 + row[10] * 8
        intact, = struct.unpack_from('<Q', result.stdout, at)
        at += 8
        self.assertEqual(intact, 1, 'graph integrity')
        return code, at

    def run_cases(self, exe, cases, label):
        result = subprocess.run([str(exe)], input=self.payload(cases), capture_output=True, timeout=600)
        (self.work / (label + '.output')).write_bytes(result.stdout)
        (self.work / (label + '.stderr')).write_bytes(result.stderr)
        self.assertEqual(result.returncode, 0, result.stderr)
        at = 0
        for c, status, _expected in cases:
            code, at = self.parse_case(result, at)
            self.assertEqual(code, status, ('status', c['files'], result.stderr[-400:]))
        self.assertEqual(at, len(result.stdout), 'no trailing output')

    def host_ok(self, source):
        try:
            compile_source(source)
            return True
        except CompileError:
            return False

    def aligned_cases(self, items):
        cases = []
        for body, status in items:
            source = 'module a;' + body
            self.assertEqual(self.host_ok(source), status == 0,
                             ('host acceptance', source, status))
            cases.append(decl.case(source, status))
        return cases

    def run_single(self, exe, case):
        result = subprocess.run([str(exe)], input=self.payload([case]), capture_output=True, timeout=600)
        self.assertEqual(result.returncode, 0, result.stderr)
        code, at = self.parse_case(result, 0)
        self.assertEqual(at, len(result.stdout))
        return result, code

    def symbol_rows(self, source, files=None):
        case = decl.case(source, 0, files=files)
        result, code = self.run_single(self.diag_executables['sym']['debug'], case)
        self.assertEqual(code, 0)
        c = case[0]
        rows = []
        for line in result.stderr.decode(errors='replace').splitlines():
            m = re.search(r'SYM unit=(\d+) src=(\d+) start=(\d+) end=(\d+) kind=(\d+) typ=(\d+) '
                          r'type_kind=(\d+) type_flags=(\d+) type_unit=(\d+) type_node=(\d+)', line)
            if not m:
                continue
            unit, src, start, end, kind, typ, tkind, flags, tunit, tnode = (int(x) for x in m.groups())
            data = c['files'][src][2]
            name = data[start:end].decode('utf-8', 'replace')
            rows.append(dict(unit=unit, src=src, name=name, kind=kind, typ=typ,
                             type_kind=tkind, type_flags=flags,
                             type_unit=tunit, type_node=tnode))
        return rows, c

    def call_rows(self, source):
        case = decl.case(source, 0)
        result, code = self.run_single(self.diag_executables['info']['debug'], case)
        self.assertEqual(code, 0)
        rows = []
        for line in result.stderr.decode(errors='replace').splitlines():
            m = re.search(r'CALL unit=(\d+) node=(\d+) ref=(\d+) target=(\d+) callee_type=(\d+) '
                          r'result_type=(\d+) type_kind=(\d+) type_unit=(\d+) type_node=(\d+) '
                          r'type_flags=(\d+)', line)
            if m:
                rows.append(dict(zip(('unit', 'node', 'ref', 'target', 'callee_type', 'result_type',
                                      'type_kind', 'type_unit', 'type_node', 'type_flags'),
                                     (int(x) for x in m.groups()))))
        return rows

    # ---- tests ------------------------------------------------------------
    def test_default_extern_calls_match_seed(self):
        cases = self.aligned_cases(ALIGNED)
        for mode, exe in self.executables.items():
            self.run_cases(exe, cases, 'aligned-' + mode)
        self.records.append(dict(test='aligned-default-extern', cases=len(cases), modes=2,
                                 statuses=sorted({s for _, s in ALIGNED}), passed=True))

    def test_imported_extern_calls_match_seed(self):
        cases = []
        for files, status in MODULE_OK:
            host = self.work / ('mod-' + uuid.uuid4().hex[:8])
            host.mkdir()
            for _, path, text in files:
                (host / path).write_text(text, encoding='utf-8')
            accepted = True
            try:
                compile_file(host / 'a.dg', roots=[host])
            except CompileError:
                accepted = False
            self.assertEqual(accepted, status == 0, ('seed import acceptance', files, status))
            cases.append(decl.case('', status, files=files))
        for mode, exe in self.executables.items():
            self.run_cases(exe, cases, 'modules-' + mode)
        self.records.append(dict(test='imported-extern', cases=len(cases), modes=2, passed=True))

    def test_declared_flags_keep_abi_and_unsafe_bits(self):
        observed = {}
        for name, source, expected in FLAGS:
            self.assertTrue(self.host_ok(source), (name, source))
            rows, _ = self.symbol_rows(source)
            for symbol, flags in expected.items():
                matched = [r for r in rows if r['name'] == symbol]
                self.assertEqual(len(matched), len(flags), (name, symbol, rows))
                self.assertEqual(sorted(r['type_flags'] for r in matched), sorted(flags),
                                 (name, symbol, matched))
                for row in matched:
                    self.assertEqual(row['type_kind'], FUNCTION, (name, symbol, row))
                    self.assertNotEqual(row['type_node'], NONE, (name, symbol, row))
                    self.assertEqual(row['type_unit'], row['unit'], (name, symbol, row))
            observed[name] = [{k: r[k] for k in ('name', 'type_flags', 'type_unit', 'type_node')}
                              for r in rows if r['name'] in expected]
        # Before integration the candidate must be the frozen mainline plus the
        # declared hunk only; after integration that identity no longer applies.
        candidate = CANDIDATE.read_text(encoding='utf-8')
        mainline = (ROOT / 'lang/bootstrap/semantic_types.dg').read_text(encoding='utf-8')
        self.assertEqual(candidate.count(FIX_BLOCK), 1)
        if FIX_BLOCK not in mainline:
            self.assertEqual(candidate.replace(FIX_BLOCK, '', 1), mainline)
        self.records.append(dict(test='declared-flags', cases=len(FLAGS), observed=observed, passed=True))

    def test_selected_callee_info_identity(self):
        observed = []
        for name, source, count in INFO_CASES:
            calls = self.call_rows(source)
            self.assertEqual(len(calls), count, (name, calls))
            syms, _ = self.symbol_rows(source)
            for call in calls:
                self.assertEqual(call['type_kind'], FUNCTION, (name, call))
                self.assertNotEqual(call['type_node'], NONE, (name, call))
                self.assertNotEqual(call['callee_type'], NONE, (name, call))
                self.assertIn((call['type_unit'], call['type_node']),
                              {(r['type_unit'], r['type_node']) for r in syms
                               if r['type_kind'] == FUNCTION and r['name'] in ('host', 'get')},
                              (name, call, syms))
                if name != 'same-name-methods':
                    self.assertEqual(call['type_flags'], 2, (name, call))
            if 'same-name' in name:
                targets = {(r['type_unit'], r['type_node']) for r in syms
                           if r['type_kind'] == FUNCTION and r['name'] == 'get'}
                self.assertEqual(len({(c['type_unit'], c['type_node']) for c in calls}), 2,
                                 (name, calls))
                self.assertEqual({(c['type_unit'], c['type_node']) for c in calls}, targets,
                                 (name, calls, targets))
                self.assertEqual({c['type_flags'] for c in calls}, {0, 2}, (name, calls))
            observed.append(dict(case=name, calls=calls))
        self.records.append(dict(test='callee-info-identity', cases=len(INFO_CASES),
                                 observed=observed, passed=True))

    def test_capacity_and_zero_skip(self):
        source = ('module a;pub struct S{pub x:u64}extern "sysv64"("host_method") '
                  'fn(self:*S)get()u64;pub fn f(p:*S)u64{unsafe{return p.get();}}')
        self.assertTrue(self.host_ok(source))
        cases = [decl.case(source, CAPACITY, pool=24, cap=0)]
        for mode, exe in self.executables.items():
            self.run_cases(exe, cases, 'capacity-' + mode)
        self.records.append(dict(test='capacity-zero', cases=len(cases), modes=2, passed=True))

    def test_bad_candidate_without_default_unsafe_is_rejected(self):
        candidate = CANDIDATE.read_text(encoding='utf-8')
        self.assertEqual(candidate.count(FIX_BLOCK), 1)
        bad_source = candidate.replace(FIX_BLOCK, '', 1)
        mainline = (ROOT / 'lang/bootstrap/semantic_types.dg').read_text(encoding='utf-8')
        if FIX_BLOCK not in mainline:
            self.assertEqual(bad_source, mainline)
        bad_root = self.work / 'bad-no-default-unsafe'
        (bad_root / 'bootstrap').mkdir(parents=True)
        for p in self.files:
            if p != 'semantic_types.dg':
                shutil.copyfile(self.snapshot / 'bootstrap' / p, bad_root / 'bootstrap' / p)
        (bad_root / 'bootstrap/semantic_types.dg').write_text(bad_source, encoding='utf-8')
        probes = [
            'module a;extern "sysv64" fn host()u64;pub fn f()u64{return host();}',
            'module a;pub struct S{pub x:u64}extern "sysv64"("m") fn(self:*S)get()u64;'
            'pub fn f(p:*S)u64{return p.get();}',
        ]
        cases = []
        for source in probes:
            with self.assertRaises(CompileError):
                compile_source(source)
            cases.append(decl.case(source, UNSAFE))
        for mode in ('debug', 'release'):
            exe = self.build(bad_root, mode, 'bad-' + mode)
            for case in cases:
                with self.assertRaisesRegex(AssertionError, 'status'):
                    self.run_cases(exe, [case], 'bad-' + mode)
        self.records.append(dict(test='bad-Dong-no-default-unsafe', cases=len(cases), modes=2,
                                 rejected_by='native status vs seed oracle', passed=True))

    def test_inputs_and_candidate_are_stable(self):
        after_main = {p: hashlib.sha256((ROOT / 'lang/bootstrap' / p).read_bytes()).hexdigest()
                      for p in self.files}
        after_cand = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in self.candidate_paths}
        self.assertEqual(self.mainline, after_main)
        self.assertEqual(self.candidate_sha, after_cand)
        self.records.append(dict(test='source-immutable', files=len(self.files),
                                 candidate_files=len(self.candidate_paths), passed=True))


if __name__ == '__main__':
    unittest.main()

