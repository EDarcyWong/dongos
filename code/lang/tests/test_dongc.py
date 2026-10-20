from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from lang.dongc import CompileError, compile_file, compile_source
from lang.dongc.compiler import lex


ROOT = Path(__file__).resolve().parents[2]


def source(body: str, returns="i64"):
    return f"module test; export(\"result\") fn result() {returns} {{ {body} }}"


def tool(name: str, override: str):
    if os.environ.get(override):
        return shutil.which(os.environ[override])
    found = shutil.which(name)
    if found:
        return found
    candidates = sorted((ROOT / ".tools").glob(f"**/{name}.exe"))
    return str(candidates[0]) if candidates else None


def nasm_flags(nasm: str):
    help_text = subprocess.run([nasm, "-h"], capture_output=True, text=True, check=True).stdout
    # NASM 3 groups warning help under "-h -w". Ask for that group only when
    # the help advertises grouped "-h -opt" syntax: older assemblers can reject
    # the extra option. Both actual probes must still report process failures.
    if re.search(r'(?m)^\s*-h\s+-\S+', help_text):
        help_text += '\n' + subprocess.run(
            [nasm, "-h", "-w"], capture_output=True, text=True, check=True,
        ).stdout
    # Some 2.x builds backport these optional warnings. Detect each warning:
    # valid PC32/REL32 references and absolute 64-bit pointer data must assemble, while other warnings
    # remain errors. Old assemblers must not receive an unknown warning option.
    warnings = ('reloc-rel-dword', 'reloc-abs-qword')
    return ["-Wall", "-Werror"] + [
        '-w-' + name for name in warnings
        if re.search(r'(?m)^\s*' + re.escape(name) + r'\s', help_text)
    ]


class FrontendTests(unittest.TestCase):
    def assert_error(self, text, code, *, mode="debug"):
        with self.assertRaises(CompileError) as caught:
            compile_source(text, mode=mode)
        self.assertEqual(code, caught.exception.code, caught.exception.message)
        return caught.exception

    def test_utf8_locations_and_comments(self):
        tokens = lex("// 中文\r\nmodule 测试; /* 多\n行 */ fn 计算(输入:u64)u64{return 输入;}")
        module = tokens[0]
        self.assertEqual(("module", 2, 1), (module.kind, module.line, module.column))
        function = next(token for token in tokens if token.value == "计算")
        self.assertEqual((3, 9), (function.line, function.column))
        compiled = compile_source("\ufeffmodule 测试; fn 计算(输入:u64)u64{return 输入;}")
        self.assertIn("__dg_m" + "测试".encode().hex() + "_f" + "计算".encode().hex(), compiled.assembly)

    def test_invalid_lexemes(self):
        for text in ["0x_1", "1_", "1__2", "0b2", "12u64", "@", "/*", '"bad\\q"', '"bad\n"', '"bad\\x0"', '"unterminated']:
            with self.subTest(text=text):
                with self.assertRaises(CompileError) as caught:
                    lex(text)
                self.assertEqual("E0001", caught.exception.code)

    def test_scalar_control_flow_and_forward_calls(self):
        compiled = compile_source("""module test;
            export("result") fn result(n: u64) u64 {
                var result: u64;
                if n == 0 { result = 1; } else { result = helper(n); }
                var i: u64 = 0;
                while i < n { i += 1; if i == 2 { continue; } if i == 5 { break; } result += i; }
                return result;
            }
            fn helper(n:u64) u64 { return n * 2; }
        """)
        self.assertEqual(["result"], compiled.exports)
        self.assertEqual(["__dong_panic"], compiled.runtime_symbols)
        self.assertIn("default rel", compiled.assembly)
        self.assertIn("push rbp", compiled.assembly)
        self.assertNotIn("[rsp-", compiled.assembly)

    def test_scope_shadow_initializer(self):
        compile_source(source("let x = 3; { let x = x + 1; } return x;"))
        self.assert_error(source("let x = 3; let x = x + 1; return x;"), "E0201")
        self.assert_error(source("{ let x = 1; } return x;"), "E0201")
        self.assert_error("module test; fn f(x:i64) i64 { let x = 1; return x; }", "E0201")
        self.assert_error("module test; fn f() i64 { let f = 1; return f(); }", "E0601")

    def test_flow_initialization(self):
        compile_source("module test; fn f(a:bool)i64 { var x:i64; if a {x=1;} else {x=2;} return x; }")
        compile_source("module test; fn f(a:bool)i64 { var x:i64; if a {return 1;} else {x=2;} return x; }")
        compile_source("module test; fn f()i64 { while true {if false {break;}} }")
        compile_source("module test; fn f()i64 { var x:i64; while true {x=1;break;} return x; }")
        cases = [
            "var x:i64; return x;",
            "var x:i64; while false {x=1;} return x;",
            "var x:i64; x+=1; return x;",
            "var x:i64; if false {x=1;} return x;",
        ]
        for body in cases:
            with self.subTest(body=body):
                self.assert_error(source(body), "E0401")
        self.assert_error("module test; fn f(a:bool)i64 {var x:i64;if a{x=1;}return x;}", "E0401")

    def test_type_and_control_errors(self):
        cases = [
            (source("let x = 1; x=2; return x;"), "E0402"),
            (source("if true {let x=1;}"), "E0402"),
            (source("return;"), "E0301"),
            (source("return 1;", "void"), "E0301"),
            (source("if 1 {return 1;} return 2;"), "E0301"),
            (source("return missing;"), "E0201"),
            (source("return missing();"), "E0201"),
            (source("let x = true + false; return 0;"), "E0301"),
            (source("let x = true < false; return 0;"), "E0301"),
            (source("break; return 0;"), "E0101"),
            (source("let x = 1 < 2 < 3; return 0;"), "E0101"),
            ("module test; fn f(a:u64,b:i64) bool {return a==b;}", "E0301"),
            ("module test; fn f(a:u64,b:i64) u64 {return a<<b;}", "E0301"),
            ("module test; fn f()void{} fn g()void{let x=f();}", "E0301"),
            ("module test; fn f(a:u64)u64{return a;} fn g()u64{return f();}", "E0301"),
        ]
        for text, code in cases:
            with self.subTest(text=text):
                self.assert_error(text, code)
        compile_source(source("let x = (1 < 2) == true; if x {return 1;} else {return 2;}"))

    def test_constants_and_literals(self):
        compile_source(source("return -9223372036854775808;"))
        compile_source(source("return 18_446_744_073_709_551_615;", "u64"))
        compiled = compile_source(source("return 0xF_F + 0b1_0;"))
        self.assertIn("mov rax, 257", compiled.assembly)
        for body in ["return 9223372036854775808;", "return 1/0;", "return 1<<64;", "return " + "9"*5000 + ";"]:
            for mode in ["debug", "release"]:
                self.assert_error(source(body), "E0302", mode=mode)
        # Locals are runtime values; constants in their initializers remain checked.
        self.assert_error(source("let x:u64 = -1; return 0;"), "E0302")

    def test_dynamic_shift_with_literal_left(self):
        compile_source("module test; fn f(n:usize)u64{return 1<<n;}")
        compile_source("module test; fn f(n:usize)i64{return -1>>n;}")
        compile_source("module test; fn f(n:usize)i64{let x=1<<n;return x;}")

    def test_unsupported_features_are_explicit(self):
        cases = [
            "let x:u64=1;",
            "extern \"unknown\" fn f()u64;",
        ]
        for body in cases:
            with self.subTest(body=body):
                self.assert_error("module test; " + body, "E0601")
        self.assert_error("module test; import core.mem;", "E0202")
        with self.assertRaises(CompileError) as caught:
            compile_source(source("return 1;"), target="x86_64-uefi-coff")
        self.assertEqual("E0601", caught.exception.code)

    def test_exports_and_frame_limit(self):
        self.assert_error('module test; export("x") fn a()void{} export("x") fn b()void{}', "E0602")
        self.assert_error('module test; export("__dong_panic") fn a()void{}', "E0602")
        self.assert_error('module test; export("__dg_file_74657374") fn a()void{}', "E0602")
        self.assert_error('module test; export("1bad") fn a()void{}', "E0602")
        self.assert_error(source(" ".join(f"let v{i}={i};" for i in range(520)) + "return 0;"), "E0601")

    def test_modes_and_runtime_manifest(self):
        text = "module test; export(\"add\") fn add(a:u64,b:u64)u64{return a+b;}"
        debug, release = compile_source(text), compile_source(text, mode="release")
        self.assertEqual(["__dong_panic"], debug.runtime_symbols)
        self.assertEqual([], release.runtime_symbols)
        self.assertEqual("l1-language", debug.manifest()["compiler_subset"])
        for mode in ["debug", "release"]:
            compiled = compile_source("module test; fn f(a:i64,b:i64)i64{return a/b;}", mode=mode)
            self.assertIn("mov edi, 3", compiled.assembly)
            self.assertIn("mov edi, 5", compiled.assembly)
        # Logical short-circuit constant folding must not emit a dead division.
        compiled = compile_source("module test; fn f(d:u64)bool{return false && (1/d==0);}")
        self.assertEqual([], compiled.runtime_symbols)


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "lang.dongc", *map(str, args)], cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8")

    def test_cli_outputs_diagnostics_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            path, asm, manifest = directory / "test.dg", directory / "test.asm", directory / "manifest.json"
            path.write_text(source("return 1;"), encoding="utf-8-sig")
            result = self.run_cli("--root", directory, "--emit-asm", asm, "--emit-manifest", manifest, path)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("l1-language", json.loads(manifest.read_text())["compiler_subset"])
            before = asm.read_bytes()
            path.write_text(source("return 未定义;"), encoding="utf-8")
            result = self.run_cli("--emit-asm", asm, path)
            self.assertEqual(1, result.returncode, result.stderr)
            self.assertIn("error[E0201]", result.stderr)
            self.assertIn("未定义", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(before, asm.read_bytes())
            self.assertEqual([], list(directory.glob("*.tmp")))
            self.assertEqual(2, self.run_cli("--check", directory / "missing.dg").returncode)
            path.write_bytes(b"module test;\n\xff")
            result = self.run_cli("--check", path)
            self.assertEqual(1, result.returncode, result.stderr)
            self.assertIn(":2:1: error[E0001]", result.stderr)

    def test_root_validation_and_check_no_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            path = directory / "wrong.dg"
            path.write_text(source("return 1;"), encoding="utf-8")
            result = self.run_cli("--check", "--root", directory, path)
            self.assertEqual(1, result.returncode, result.stderr)
            self.assertIn("E0202", result.stderr)
            self.assertEqual(0, self.run_cli("--check", path).returncode)
            self.assertEqual([path], list(directory.iterdir()))


class AssemblyTests(unittest.TestCase):
    def test_nasm_elf64_object(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("NASM is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            asm, obj = directory / "probe.asm", directory / "probe.o"
            asm.write_text(compile_file(ROOT / "lang/examples/boot_probe.dg", roots=[ROOT / "lang/examples"]).assembly, encoding="utf-8")
            result = subprocess.run([nasm, "-f", "elf64", *nasm_flags(nasm), "-o", str(obj), str(asm)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(b"\x7fELF\x02", obj.read_bytes()[:5])

    def test_nasm_reserved_export_names(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("NASM is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            asm, obj = directory / "reserved.asm", directory / "reserved.o"
            text = 'module t; export("rax") fn f()i64{return 1;} export("section") fn g()i64{return f();}'
            asm.write_text(compile_source(text).assembly, encoding="utf-8")
            result = subprocess.run([nasm, "-f", "elf64", *nasm_flags(nasm), "-o", str(obj), str(asm)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)

    def test_native_values_panic_and_assembly_abi_probe(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native execution requires NASM and a SysV-capable GCC host compiler")
        fixtures = Path(__file__).parent
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for mode in ["debug", "release"]:
                with self.subTest(mode=mode):
                    asm = directory / f"{mode}.asm"
                    obj, abi = directory / f"{mode}.o", directory / "abi.o"
                    exe = directory / (f"{mode}.exe" if os.name == "nt" else mode)
                    compiled = compile_source((fixtures / "scalar_probe.dg").read_text(encoding="utf-8"), "scalar_probe.dg", mode=mode)
                    asm.write_text(compiled.assembly, encoding="utf-8")
                    for inp, out in [(asm, obj), (fixtures / "abi_probe.asm", abi)]:
                        result = subprocess.run([nasm, "-f", "win64" if os.name == "nt" else "elf64", *nasm_flags(nasm), "-o", str(out), str(inp)], capture_output=True, text=True)
                        self.assertEqual(0, result.returncode, result.stderr)
                    command = [cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror",
                               "-DDEBUG_MODE=" + ("1" if mode == "debug" else "0"), str(fixtures / "native_probe.c"), str(obj), str(abi), "-o", str(exe)]
                    result = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("native scalar and SysV probe passed", result.stdout)
                    cases = {"divzero": 3, "modzero": 3, "idivzero": 3, "andzero": 3,
                             "divoverflow": 5, "modoverflow": 5, "shift": 4, "signedshift": 4,
                             "order": 2 if mode == "debug" else 3}
                    if mode == "debug":
                        cases.update({name: 2 for name in ["add", "sub", "mul", "uneg", "iadd", "isub", "imul", "ineg"]})
                    for case, kind in cases.items():
                        with self.subTest(mode=mode, panic=case):
                            result = subprocess.run([str(exe), case], capture_output=True, text=True, timeout=10)
                            self.assertEqual(64 + kind, result.returncode, result.stdout + result.stderr)
                            self.assertIn(f"observed panic {kind}", result.stdout)


if __name__ == "__main__":
    unittest.main()
