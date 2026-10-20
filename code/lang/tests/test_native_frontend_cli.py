"""Filesystem-to-Dong compiler CLI: no host compiler fallback at run time."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch
from tools.build_native_frontend import ROOT, build
from lang.tests.test_dongc import tool


class NativeFrontendCLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != 'posix' or platform.machine().lower() not in ('x86_64', 'amd64'):
            raise unittest.SkipTest('native filesystem driver requires POSIX x86-64')
        if not tool('nasm', 'NASM') or not tool('gcc', 'CC'):
            raise unittest.SkipTest('native frontend CLI requires NASM/GCC')
        cls.work = ROOT/'build/test/native-frontend-cli'/('run-'+uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        cls.executables = {}
        cls.receipts = {}
        for mode in ('debug', 'release'):
            exe = cls.work/('dong-native-'+mode)
            cls.receipts[mode] = build(exe, mode)
            cls.executables[mode] = exe
        cls.records = []

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'work'):
            (cls.work/'summary.json').write_text(json.dumps(dict(
                builds=cls.receipts, executions=cls.records,
                selfhost=False, OS_VM_built=False), indent=2)+'\n')

    def run_cli(self, args, expected, *, mode='debug'):
        # An empty PATH proves the final executable does not launch Python or
        # the seed compiler. PATH is not needed by the C/Dong executable.
        env = dict(os.environ, PATH='')
        completed = subprocess.run([str(self.executables[mode]), *map(str, args)],
                                   env=env, capture_output=True, timeout=60)
        self.records.append(dict(mode=mode, args=list(map(str, args)),
                                 returncode=completed.returncode,
                                 stdout=completed.stdout.decode('utf-8', 'replace'),
                                 stderr=completed.stderr.decode('utf-8', 'replace')))
        self.assertEqual(completed.returncode, expected, completed.stderr)
        return completed

    def test_native_source_check_and_real_semantic_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'a.dg'
            for mode in self.executables:
                source.write_text('module a;fn f(x:u64)u64{return x+1;}')
                before = source.read_bytes()
                accepted = self.run_cli(['--check', '--stats', source], 0, mode=mode)
                stats = json.loads(accepted.stdout)
                self.assertEqual((stats['status'], stats['units']), (0, 1))
                self.assertGreater(stats['nodes'], 0)
                self.assertGreater(stats['used_bytes'], 0)
                self.assertEqual(accepted.stderr, b'')
                self.assertEqual(source.read_bytes(), before)
                source.write_text('module a;fn f()u64{return true;}')
                failed = self.run_cli(['--check', '--stats', source], 1, mode=mode)
                self.assertIn(b'E0301', failed.stderr)
                stats = json.loads(failed.stdout)
                self.assertEqual((stats['status'], stats['stage'], stats['units']), (3, 4, 0))
                self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ['a.dg'])

    def test_explicit_roots_imports_dedup_order_and_ambiguity(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); one = base/'one'; two = base/'two'; one.mkdir(); two.mkdir()
            source = one/'a.dg'; dep = two/'dep.dg'
            source.write_text('module a;import dep;fn f()u64{return dep.g();}')
            dep.write_text('module dep;pub fn g()u64{return 7;}')
            root_alias = base/'alias'; root_alias.symlink_to(one, target_is_directory=True)
            args = ['--check', '--stats', '--root', one, '--root', two, '--root', root_alias, source]
            first = self.run_cli(args, 0); second = self.run_cli(args, 0)
            self.assertEqual(first.stdout, second.stdout)
            self.assertEqual(json.loads(first.stdout)['units'], 2)
            self.assertEqual(json.loads(first.stdout)['catalog_files'], 2)
            self.assertIn(b'E0202', self.run_cli(['--check', source], 1).stderr)
            (one/'dep.dg').write_bytes(dep.read_bytes())
            ambiguous = self.run_cli(args, 1)
            self.assertIn(b'E0202', ambiguous.stderr)
            self.assertEqual(json.loads(ambiguous.stdout)['units'], 0)

    def test_bom_crlf_unicode_and_malformed_utf8_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'a.dg'
            source.write_bytes(b'\xef\xbb\xbfmodule a;\r\nfn f()u64{return true;}')
            failed = self.run_cli(['--check', source], 1)
            self.assertIn(b'a.dg:2:', failed.stderr)
            self.assertIn(b'E0301', failed.stderr)
            source.write_bytes('module a;\n// 中\n'.encode()+b'\xff')
            failed = self.run_cli(['--check', source], 1)
            self.assertIn(b'a.dg:3:1:', failed.stderr)
            self.assertIn(b'E0001', failed.stderr)
            source.write_text('module a;fn 中文()u64{return 1;}')
            self.run_cli(['--check', source], 0)

    def test_bounded_memory_and_source_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); source = base/'a.dg'
            source.write_text('module a;fn f()u64{return 1;}')
            failed = self.run_cli(['--check', '--stats', '--memory-mib', '1', source], 2)
            self.assertEqual(json.loads(failed.stdout)['status'], 2)
            self.assertEqual(json.loads(failed.stdout)['units'], 0)
            failed = self.run_cli(['--check', '--stats', '--tokens', '1', source], 2)
            self.assertEqual(json.loads(failed.stdout)['status'], 2)
            for options in (['--max-depth', '0'], ['--nodes', '-1'], ['--memory-mib', '1025'],
                            ['--tokens', '18446744073709551616']):
                self.run_cli(['--check', *options, source], 2)
            self.run_cli(['--check', base/'missing.dg'], 2)
            fifo = base/'pipe.dg'; os.mkfifo(fifo)
            self.run_cli(['--check', fifo], 2)
            rejected = self.run_cli(['--check', '--root', base, source], 2)
            self.assertIn(b'source must be a regular file', rejected.stderr)
            fifo.unlink()
            huge = base/'large.dg'
            with huge.open('wb') as stream:
                stream.truncate(4*1024*1024+1)
            self.run_cli(['--check', '--root', base, source], 2)

    def test_no_symlink_escape_or_overlapping_entry_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); root = base/'root'; root.mkdir(); outside = base/'outside'; outside.mkdir()
            source = root/'a.dg'; source.write_text('module a;fn f()u64{return 1;}')
            secret = outside/'secret.dg'; secret.write_text('module secret;const SECRET:u64=123;')
            linked = root/'leak.dg'; linked.symlink_to(secret)
            self.assertIn(b'symlinked', self.run_cli(['--check', '--root', root, source], 2).stderr)
            linked.unlink(); linked.symlink_to(outside, target_is_directory=True)
            self.run_cli(['--check', '--root', root, source], 2)
            linked.unlink(); linked.symlink_to(source)
            self.run_cli(['--check', linked], 2)
            linked.unlink()
            self.run_cli(['--check', '--root', root, secret], 2)
            self.run_cli(['--check', '--root', base, '--root', root, source], 2)
            self.assertEqual(secret.read_text(), 'module secret;const SECRET:u64=123;')

    def test_actual_semantic_source_closure(self):
        for mode in self.executables:
            result = self.run_cli(['--check', '--stats', '--root', ROOT/'lang',
                                   ROOT/'lang/bootstrap/semantic_types.dg'], 0, mode=mode)
            stats = json.loads(result.stdout)
            self.assertEqual(stats['units'], 13)
            self.assertGreater(stats['tokens'], 80000)
            self.assertGreater(stats['nodes'], 50000)
            self.assertLess(stats['used_bytes'], stats['arena_bytes'])

    def test_host_catalog_total_budget_before_allocation(self):
        # Call the production C traversal with an already-exhausted total
        # budget; this avoids creating 131073 files just to reach the guard.
        source = self.work/'catalog-budget.c'
        include = json.dumps(str(ROOT/'lang/host/native_driver.c'))
        source.write_text('#define main production_main\n#include '+include+'\n#undef main\n'+r'''
uint64_t ABI dong_frontend_check(const Options*a,const Source*b,uint64_t c,const Limits*d,
 uint8_t*e,uint64_t f,Result*g){(void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;abort();}
uint64_t ABI dong_frontend_diagnostic(const Source*a,uint64_t b,const Result*c,uint8_t*d,
 uint64_t e,uint64_t*f){(void)a;(void)b;(void)c;(void)d;(void)e;(void)f;abort();}
uint64_t ABI dong_native_emit(const Graph*a,const EmitLimits*b,uint64_t c,uint8_t*d,
 uint64_t e,uint8_t*f,uint64_t g,EmitResult*h){
 (void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;(void)h;abort();}
int main(int argc,char**argv){
 if(argc!=2)return 3;
 Catalog c={.entry_index=UINT64_MAX,.entries=MAX_CATALOG_ENTRIES};
 int fd=open(argv[1],O_RDONLY|O_DIRECTORY);if(fd<0)return 4;
 int ok=walk(&c,fd,argv[1],"",0,0);close(fd);
 return ok||c.count||c.total||c.entries!=MAX_CATALOG_ENTRIES;
}
''')
        exe = self.work/'catalog-budget'
        command = [tool('gcc', 'CC'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(exe)]
        subprocess.run(command, check=True, capture_output=True)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'a.dg').write_text('module a;')
            result = subprocess.run([str(exe), directory], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(b'directory entry limit', result.stderr)

    def test_native_emit_assemble_execute_and_atomic_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); source = base/'a.dg'; assembly = base/'a.asm'
            source.write_text('module a;fn helper(x:u64)u64{return x*2;}'
                              'pub fn f(x:u64)u64{var n:u64=0;var i:u64=0;'
                              'while i<x{if i==3{i+=1;continue;}n+=helper(i);i+=1;}return n;}')
            before = source.read_bytes()
            c = base/'oracle.c'
            c.write_text('#include <stdint.h>\n'
                         'extern uint64_t f(uint64_t) __asm__("__dong_m61_n66");\n'
                         'int main(void){for(uint64_t n=0;n<1000;n++){uint64_t expected=0;'
                         'for(uint64_t i=0;i<n;i++)if(i!=3)expected+=2*i;'
                         'if(f(n)!=expected)return 1;}return 0;}\n')
            for mode in self.executables:
                assembly.write_bytes(b'previous assembly')
                result = self.run_cli(['--emit-asm', assembly, '--mode', mode,
                                       '--stats', source], 0, mode=mode)
                stats = json.loads(result.stdout)
                self.assertEqual((stats['backend_run'], stats['backend_status']), (1, 0))
                self.assertEqual(stats['assembly_bytes'], assembly.stat().st_size)
                self.assertIn(b'global __dong_m61_n66', assembly.read_bytes())
                obj = base/(mode+'.o'); exe = base/(mode+'.exe')
                commands = [[tool('nasm', 'NASM'), '-f', 'elf64', '-o', str(obj), str(assembly)],
                            [tool('gcc', 'CC'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                             '-no-pie', str(c), str(obj), '-o', str(exe)], [str(exe)]]
                for command in commands:
                    observed = subprocess.run(command, capture_output=True, timeout=30)
                    self.assertEqual(observed.returncode, 0, (command, observed.stderr))
                self.assertEqual(source.read_bytes(), before)
                previous = assembly.read_bytes()
                capacity = self.run_cli(['--emit-asm', assembly, '--stats',
                                         '--code-memory-mib', '1', source], 2, mode=mode)
                self.assertEqual(json.loads(capacity.stdout)['backend_status'], 2)
                self.assertEqual(assembly.read_bytes(), previous)
                self.run_cli(['--emit-asm', source, source], 2, mode=mode)
                self.assertEqual(source.read_bytes(), before)
                self.assertFalse(list(base.glob('.dong-native-*.tmp')))
            old = assembly.read_bytes()
            source.write_text('module a;fn f()u64{return true;}')
            self.run_cli(['--emit-asm', assembly, source], 1)
            self.assertEqual(assembly.read_bytes(), old)
            source.write_text('module a;var state:u64=7;fn f()u64{return state;}')
            rejected = self.run_cli(['--emit-asm', assembly, '--stats', source], 1)
            self.assertEqual(json.loads(rejected.stdout)['backend_status'], 3)
            self.assertEqual(assembly.read_bytes(), old)
            source.write_bytes(before)
            hard = base/'hard.asm'; os.link(source, hard)
            self.run_cli(['--emit-asm', hard, source], 2)
            self.assertEqual(hard.read_bytes(), before)
            link = base/'link.asm'; link.symlink_to(assembly)
            self.run_cli(['--emit-asm', link, source], 2)
            self.assertEqual(assembly.read_bytes(), old)
            self.run_cli(['--emit-asm', base, source], 2)
            self.run_cli(['--check', '--emit-asm', assembly, source], 2)
            self.assertFalse(list(base.glob('.dong-native-*.tmp')))

    def test_existing_artifact_compare_module_and_build_rollback(self):
        source = ROOT/'lang/bootstrap/artifact_compare.dg'
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        for mode in self.executables:
            result = self.run_cli(['--check', '--stats', '--root', ROOT/'lang', source], 0, mode=mode)
            self.assertEqual(json.loads(result.stdout)['units'], 1)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        old = self.work/'preserved-native'; old.write_bytes(b'previous build')
        with patch.dict(os.environ, NASM='/unavailable/nasm'):
            with self.assertRaises(RuntimeError):
                build(old)
        self.assertEqual(old.read_bytes(), b'previous build')
        with self.assertRaises(ValueError):
            build(ROOT/'lang/host/native_driver.c')
        link = self.work/'link'; link.symlink_to(old)
        with self.assertRaises(ValueError):
            build(link)
        self.assertEqual(old.read_bytes(), b'previous build')


if __name__ == '__main__':
    unittest.main()
