"""Backend contracts for pair ABI, cleanup snapshots and loop storage."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import CompileError, compile_source
from lang.tests.test_dongc import nasm_flags, tool


def body(assembly, symbol):
    return assembly.split("$" + symbol + ":", 1)[1].split("\nalign 16", 1)[0].split("section .rodata", 1)[0]


class L1CodegenTests(unittest.TestCase):
    def test_pairs_spill_wholly_and_leave_the_last_register_for_a_scalar(self):
        compiled = compile_source('''module pair_abi;
            export("echo") fn echo(a:u64,b:u64,c:u64,d:u64,e:u64,p:?i16,z:u64)?i16{return p;}
        ''')
        assembly = body(compiled.assembly, "echo")
        self.assertIn("qword [rbp+16]", assembly)
        self.assertIn("qword [rbp+24]", assembly)
        self.assertRegex(assembly, r"mov qword \[rbp-[0-9]+\], r9")
        self.assertIn("mov rdx, qword [rax+8]", assembly)

    def test_for_a_large_array_place_does_not_copy_its_entire_backing_object(self):
        compiled = compile_source('''module large_view;
            var DATA:[8192]u8=[0;8192];
            export("sum") fn sum()u64{var result:u64=0;for value in DATA{result+=value as u64;}return result;}
        ''')
        assembly = body(compiled.assembly, "sum")
        self.assertNotIn("rep movsb", assembly)
        self.assertNotIn("rep stosb", assembly)
        self.assertNotIn("8192", "\n".join(line for line in assembly.splitlines() if "sub rsp" in line))
        self.assertRegex(assembly, r"movzx eax, byte \[rax\]")

    def test_pair_constructor_temporary_counts_at_exact_frame_boundary(self):
        def source(reserve, win64=False):
            modifier = 'extern "win64" ' if win64 else ""
            return f'''module frame;
                export("budget") {modifier}fn budget()void{{var padding:[{reserve}]u8;let value:?u64=null;}}
            '''

        # SysV: padding + local descriptor16 + constructor temporary16 + frame16.
        # Win64 adds wrapper RBP/return16 + 176 bytes of nonvolatile saves.
        for win64, reserve in ((False, 4048), (True, 3856)):
            with self.subTest(win64=win64):
                compile_source(source(reserve, win64))
                with self.assertRaises(CompileError) as caught:
                    compile_source(source(reserve + 16, win64))
                self.assertEqual(caught.exception.code, "E0601")
                self.assertIn("4112", caught.exception.message)

    def test_noreturn_has_no_ordinary_return_path(self):
        compiled = compile_source('''module never;
            extern "sysv64" fn halt()noreturn;
            export("never") fn never()noreturn{unsafe{halt();}}
            export("scalar_bottom") fn scalar_bottom()u32{unsafe{return halt();}}
            export("pair_bottom") fn pair_bottom()!u32{unsafe{return halt();}}
            export("indirect_bottom") fn indirect_bottom()u8{let stop=halt;unsafe{return stop();}}
        ''')
        assembly = body(compiled.assembly, "never")
        self.assertRegex(assembly, r"call \$halt\s+ud2")
        self.assertNotRegex(assembly, r"\bret\b")
        for symbol in ("scalar_bottom", "pair_bottom"):
            self.assertRegex(body(compiled.assembly, symbol), r"call \$halt\s+ud2")
        self.assertRegex(body(compiled.assembly, "indirect_bottom"), r"call r11\s+ud2")

    def test_native_pair_bits_and_return_snapshot_survive_cleanup(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("pair cleanup execution requires NASM and GCC")
        source = '''module pair_bits;
            error Maximum=4294967295;
            enum Event{Number(i8),Empty}
            var TRACE:u64=0;
            var EVENTS:[2]Event=[Event.Number(-1),Event.Number(5)];
            var BYTES:[3]u8=[1,2,3];
            var OTHER:[1]u8=[9];
            var VIEW:[]u8=BYTES[..];
            fn cleanup()void{TRACE=TRACE*10+7;}
            fn selected()Event{TRACE=TRACE*10+2;return EVENTS[0];}
            export("failure") fn failure()!u8{defer cleanup();return error.Maximum;}
            export("signed_pair") fn signed_pair()?i16{defer cleanup();return -123;}
            export("empty_pair") fn empty_pair()?i16{defer cleanup();return null;}
            export("event") fn event()Event{return Event.Number(-1);}
            export("score") fn score(value:?i16)i64{match value{some(n)=>{return n as i64;},null=>{return -999;},}}
            export("trace") fn trace()u64{return TRACE;}
            export("loop_pairs") fn loop_pairs()i64{
                var total:i64=0;
                for item in EVENTS{match item{Event.Number(n)=>{EVENTS[1]=Event.Number(7);total+=n as i64;},Event.Empty=>{},}}
                return total;
            }
            export("match_once") fn match_once()i64{
                match selected(){Event.Number(n)=>{EVENTS[0]=Event.Empty;return n as i64;},Event.Empty=>{return 0;},}
            }
            export("loop_temporary") fn loop_temporary(value:i8)i64{
                var total:i64=0;
                for item in [Event.Number(value),Event.Number(3)]{match item{Event.Number(n)=>{cleanup();total+=n as i64;},Event.Empty=>{},}}
                return total;
            }
            export("loop_view") fn loop_view()u64{
                var total:u64=0;
                for item in VIEW{VIEW=OTHER[..];total+=item as u64;}
                return total;
            }
        '''
        harness = r'''
            #include <stdint.h>
            #include <stdio.h>
            #include <stdlib.h>
            #define DG __attribute__((sysv_abi))
            struct Pair{uint64_t tag,value;};
            extern struct Pair DG failure(void),signed_pair(void),empty_pair(void),event(void);
            extern int64_t DG score(struct Pair);
            extern int64_t DG loop_pairs(void),match_once(void),loop_temporary(int8_t);
            extern uint64_t DG loop_view(void);
            extern uint64_t DG trace(void);
            void DG __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const uint8_t*f,uint64_t n){(void)k;(void)l;(void)f;(void)n;abort();}
            int main(void){
                struct Pair a=failure(),b=signed_pair(),c=empty_pair(),d=event();
                if(a.tag!=UINT64_C(4294967295)||a.value||b.tag!=1||b.value!=UINT64_C(0xff85)||c.tag||c.value||d.tag||d.value!=255||score(b)!=-123||score(c)!=-999||trace()!=777)return 1;
                if(loop_pairs()!=6||match_once()!=-1||trace()!=7772||loop_temporary(-9)!=-6||loop_view()!=6)return 2;
                puts("pair low bits, maximum error tag and cleanup return snapshots passed");return 0;
            }
        '''
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            c = directory / "probe.c"
            c.write_text(harness, encoding="utf-8")
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    assembly, obj = directory / (mode + ".asm"), directory / (mode + ".o")
                    executable = directory / (mode + (".exe" if os.name == "nt" else ""))
                    compiled = compile_source(source, mode=mode)
                    assembly.write_text(compiled.assembly, encoding="utf-8")
                    result = subprocess.run([nasm, "-f", "win64" if os.name == "nt" else "elf64", *nasm_flags(nasm),
                                             "-o", str(obj), str(assembly)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    flags = [] if os.name == "nt" else ["-no-pie"]
                    result = subprocess.run([cc, "-std=c11", "-O0", "-Wall", "-Wextra", "-Werror", *flags,
                                             str(c), str(obj), "-o", str(executable)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
