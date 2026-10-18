from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from lang.dongc import CompileError, compile_file, compile_source
from lang.tests.test_dongc import ROOT, nasm_flags, tool


class ModuleTests(unittest.TestCase):
    def prepare(self, root, files):
        for name, source in files.items():
            path = root / (name.replace(".", "/") + ".dg")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        return root / "main.dg"

    def test_qualified_types_public_calls_and_stable_symbols(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entry = self.prepare(root, {
                "main": 'module main; import math.geom as g; export("result") fn result()u64 { let p=g.Point{x:42}; return g.read(&p); }',
                "math.geom": 'module math.geom; pub struct Point{pub x:u64} pub fn read(p:*const Point)u64{unsafe{return (*p).x;}}',
            })
            result = compile_file(entry, roots=[root])
            self.assertIn("__dg_m" + b"math.geom".hex() + "_f" + b"read".hex(), result.assembly)
            typ = result.layout_manifest["types"][0]
            self.assertEqual((typ["name"], typ["full_name"]), ("Point", "math.geom.Point"))
            self.assertEqual(len(result.source_files), 2)
            self.assertEqual(result.assembly, compile_file(entry, roots=[root]).assembly)

    def test_cycles_and_missing_modules(self):
        cases = [
            ({"main": "module main; import absent;"}, "E0202"),
            ({"main": "module main; import dep;", "dep": "module dep; import main;"}, "E0202"),
            ({"main": "module main; import dep;", "dep": "module wrong;"}, "E0202"),
            ({"main": "module main; import dep as d; import dep as d;", "dep": "module dep;"}, "E0201"),
        ]
        for files, code in cases:
            with self.subTest(files=files), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                entry = self.prepare(root, files)
                with self.assertRaises(CompileError) as caught:
                    compile_file(entry, roots=[root])
                self.assertEqual(caught.exception.code, code)

    def test_ambiguous_source_roots_and_no_implicit_lookup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = root / "one", root / "two"
            entry = self.prepare(first, {"main": "module main; import dep;", "dep": "module dep;"})
            self.prepare(second, {"dep": "module dep;"})
            for roots in [[], [first, second]]:
                with self.subTest(roots=roots), self.assertRaises(CompileError) as caught:
                    compile_file(entry, roots=roots)
                self.assertEqual(caught.exception.code, "E0202")
            self.assertIsNotNone(compile_file(entry, roots=[first]))

    def test_private_functions_types_fields_and_public_leaks(self):
        cases = [
            ('fn hidden()u64{return 1;}', 'return d.hidden();'),
            ('struct Hidden{x:u64}', 'return sizeof(d.Hidden);'),
            ('pub struct S{x:u64} pub fn accept(p:*const S)u64{unsafe{return (*p).x;}}', 'let v=d.S{x:1};return d.accept(&v);'),
            ('pub struct S{x:u64} pub fn make() *const S {return null;}', 'let p=d.make();unsafe{return (*p).x;}'),
        ]
        for declaration, body in cases:
            with self.subTest(declaration=declaration), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                entry = self.prepare(root, {"main": f'module main; import dep as d; fn f()u64{{{body}}}',
                                            "dep": "module dep; " + declaration})
                with self.assertRaises(CompileError) as caught:
                    compile_file(entry, roots=[root])
                self.assertEqual(caught.exception.code, "E0201")
        with self.assertRaises(CompileError) as caught:
            compile_source("module test; struct Hidden{x:u64} pub fn expose(p:*Hidden)void{}")
        self.assertEqual(caught.exception.code, "E0201")

    def test_dependency_diagnostics_use_its_path_and_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entry = self.prepare(root, {"main": "module main; import dep;",
                                        "dep": "module dep;\npub fn f()u64 { return 未定义; }"})
            result = subprocess.run([sys.executable, "-m", "lang.dongc", "--root", str(root), "--check", str(entry)],
                                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("dep.dg:2:", result.stderr)
            self.assertIn("return 未定义;", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_output_cannot_overwrite_dependency(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entry = self.prepare(root, {"main": "module main; import dep;", "dep": "module dep;"})
            dependency = root / "dep.dg"
            before = dependency.read_bytes()
            result = subprocess.run([sys.executable, "-m", "lang.dongc", "--root", str(root), "--emit-asm", str(dependency), str(entry)],
                                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(dependency.read_bytes(), before)

    def test_native_dependency_panic_preserves_source_path(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("dependency panic probe requires NASM and GCC")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entry = self.prepare(root, {
                "main": 'module main; import dep; export("probe") fn f(i:usize)u64{return dep.read(i);}',
                "dep": 'module dep;\npub fn read(i:usize)u64{\nlet a:[1]u64=[42]; return a[i];\n}',
            })
            observer = root / "observer.c"
            observer.write_text('''#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
extern uint64_t DG probe(uint64_t);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const unsigned char *file,uint64_t size){
    exit(kind==1 && line==3 && size==6 && !memcmp(file,"dep.dg",6) ? 65 : 99);
}
int main(int argc,char **argv){(void)argv; return probe(argc>1 ? 1 : 0)==42 ? 0 : 98;}
''', encoding="ascii")
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    asm, obj = root / f"{mode}.asm", root / f"{mode}.o"
                    exe = root / (mode + ".exe" if os.name == "nt" else mode)
                    asm.write_text(compile_file(entry, roots=[root], mode=mode).assembly, encoding="utf-8")
                    commands = [
                        [nasm, "-f", "win64" if os.name == "nt" else "elf64", *nasm_flags(nasm), "-o", str(obj), str(asm)],
                        [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(observer), str(obj), "-o", str(exe)],
                    ]
                    for command in commands:
                        result = subprocess.run(command, capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(subprocess.run([str(exe)], timeout=10).returncode, 0)
                    self.assertEqual(subprocess.run([str(exe), "panic"], timeout=10).returncode, 65)

    def test_import_alias_shadow_and_local_function_shadow(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entry = self.prepare(root, {"main": "module main; import dep as d; fn f()u64{let d=0;return d.value();}",
                                        "dep": "module dep; pub fn value()u64{return 42;}"})
            with self.assertRaises(CompileError) as caught:
                compile_file(entry, roots=[root])
            self.assertEqual(caught.exception.code, "E0201")
            self.assertIn("type i64 has no field", caught.exception.message)
