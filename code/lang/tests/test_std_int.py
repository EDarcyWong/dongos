"""Independent C reference checks for core.int checked arithmetic."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[2]
STD = ROOT / "lang" / "std"


def wrapper_source():
    return """module probe;
import core.int as int;
export("int_is_pow2") fn is_pow2(v:usize)bool{return int.is_power_of_two(v);}
export("int_add_checked") fn add_checked(a:usize,b:usize,o:*usize)bool{unsafe{return int.add_checked(a,b,o);}}
export("int_sub_checked") fn sub_checked(a:usize,b:usize,o:*usize)bool{unsafe{return int.sub_checked(a,b,o);}}
export("int_mul_checked") fn mul_checked(a:usize,b:usize,o:*usize)bool{unsafe{return int.mul_checked(a,b,o);}}
export("int_align_up") fn align_up(v:usize,a:usize,o:*usize)bool{unsafe{return int.align_up(v,a,o);}}
export("int_align_down") fn align_down(v:usize,a:usize,o:*usize)bool{unsafe{return int.align_down(v,a,o);}}
"""


C_SOURCE = r"""
#define _GNU_SOURCE
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define DG __attribute__((sysv_abi))
#define CHECK(X) do{if(!(X)){fprintf(stderr,"core.int check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
extern uint8_t DG int_is_pow2(uint64_t);
extern uint8_t DG int_add_checked(uint64_t,uint64_t,uint64_t *);
extern uint8_t DG int_sub_checked(uint64_t,uint64_t,uint64_t *);
extern uint8_t DG int_mul_checked(uint64_t,uint64_t,uint64_t *);
extern uint8_t DG int_align_up(uint64_t,uint64_t,uint64_t *);
extern uint8_t DG int_align_down(uint64_t,uint64_t,uint64_t *);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    fprintf(stderr,"unexpected core.int panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char *)file);exit(99);
}
static int is_pow2(uint64_t v){return v!=0 && (v&(v-1))==0;}
static uint64_t rng(uint64_t *s){*s^=*s<<13;*s^=*s>>7;*s^=*s<<17;return *s;}
int main(void){
    uint64_t out;
    {uint64_t samples[]={0,1,2,3,4,5,7,8,16,32,63,64,65,1024,1023,(UINT64_C(1)<<63),(UINT64_C(1)<<63)+1,UINT64_MAX};
     for(size_t i=0;i<sizeof(samples)/sizeof(samples[0]);++i)CHECK(int_is_pow2(samples[i])==(uint8_t)is_pow2(samples[i]));}
    CHECK(int_add_checked(0,0,&out) && out==0);
    CHECK(int_add_checked(UINT64_MAX,0,&out) && out==UINT64_MAX);
    CHECK(int_add_checked(0,UINT64_MAX,&out) && out==UINT64_MAX);
    CHECK(int_add_checked(UINT64_MAX-1,1,&out) && out==UINT64_MAX);
    out=0xdeadbeefcafebabeULL;CHECK(!int_add_checked(UINT64_MAX,1,&out) && out==0xdeadbeefcafebabeULL);
    out=0xdeadbeefcafebabeULL;CHECK(!int_add_checked(UINT64_MAX-1,2,&out) && out==0xdeadbeefcafebabeULL);
    CHECK(int_sub_checked(5,3,&out) && out==2);
    CHECK(int_sub_checked(0,0,&out) && out==0);
    CHECK(int_sub_checked(UINT64_MAX,UINT64_MAX,&out) && out==0);
    out=0xdeadbeefcafebabeULL;CHECK(!int_sub_checked(0,1,&out) && out==0xdeadbeefcafebabeULL);
    out=0xdeadbeefcafebabeULL;CHECK(!int_sub_checked(3,5,&out) && out==0xdeadbeefcafebabeULL);
    CHECK(int_mul_checked(0,0,&out) && out==0);
    CHECK(int_mul_checked(0,UINT64_MAX,&out) && out==0);
    CHECK(int_mul_checked(UINT64_MAX,0,&out) && out==0);
    CHECK(int_mul_checked(1,UINT64_MAX,&out) && out==UINT64_MAX);
    CHECK(int_mul_checked(UINT64_MAX,1,&out) && out==UINT64_MAX);
    out=0xdeadbeefcafebabeULL;CHECK(!int_mul_checked(UINT64_C(0x100000000),UINT64_C(0x100000000),&out) && out==0xdeadbeefcafebabeULL);
    out=0xdeadbeefcafebabeULL;CHECK(!int_mul_checked(UINT64_MAX,UINT64_MAX,&out) && out==0xdeadbeefcafebabeULL);
    CHECK(int_align_up(0,1,&out) && out==0);
    CHECK(int_align_down(0,1,&out) && out==0);
    CHECK(int_align_up(1,1,&out) && out==1);
    CHECK(int_align_up(3,8,&out) && out==8);
    CHECK(int_align_up(8,8,&out) && out==8);
    CHECK(int_align_up(9,8,&out) && out==16);
    CHECK(int_align_down(9,8,&out) && out==8);
    CHECK(int_align_down(8,8,&out) && out==8);
    CHECK(int_align_down(0,8,&out) && out==0);
    CHECK(int_align_up(UINT64_MAX,1,&out) && out==UINT64_MAX);
    CHECK(int_align_up(UINT64_MAX-7,8,&out) && out==UINT64_MAX-7);
    out=0xdeadbeefcafebabeULL;CHECK(!int_align_up(UINT64_MAX,8,&out) && out==0xdeadbeefcafebabeULL);
    out=0xdeadbeefcafebabeULL;CHECK(!int_align_up(UINT64_MAX-3,8,&out) && out==0xdeadbeefcafebabeULL);
    out=0xdeadbeefcafebabeULL;CHECK(!int_align_up(5,0,&out) && out==0xdeadbeefcafebabeULL);
    out=0xdeadbeefcafebabeULL;CHECK(!int_align_up(5,3,&out) && out==0xdeadbeefcafebabeULL);
    out=0xdeadbeefcafebabeULL;CHECK(!int_align_up(5,5,&out) && out==0xdeadbeefcafebabeULL);
    out=0xdeadbeefcafebabeULL;CHECK(!int_align_down(5,6,&out) && out==0xdeadbeefcafebabeULL);
    {uint64_t seed=UINT64_C(0x9e3779b97f4a7c15);
     for(int trial=0;trial<2000;++trial){
        uint64_t a=rng(&seed),b=rng(&seed);
        int ok_add=(a<=UINT64_MAX-b);
        out=0xdeadbeefcafebabeULL;CHECK(int_add_checked(a,b,&out)==(uint8_t)ok_add);CHECK(out==(ok_add?a+b:0xdeadbeefcafebabeULL));
        int ok_sub=(a>=b);
        out=0xdeadbeefcafebabeULL;CHECK(int_sub_checked(a,b,&out)==(uint8_t)ok_sub);CHECK(out==(ok_sub?a-b:0xdeadbeefcafebabeULL));
        int ok_mul=(b==0)||(a<=UINT64_MAX/b);
        out=0xdeadbeefcafebabeULL;CHECK(int_mul_checked(a,b,&out)==(uint8_t)ok_mul);CHECK(out==(ok_mul?a*b:0xdeadbeefcafebabeULL));
        uint64_t al=rng(&seed);if((trial&3)==0){al=UINT64_C(1)<<(rng(&seed)&63);}
        int ok_align=is_pow2(al);uint64_t mask=ok_align?(al-1):0;
        int ok_up=ok_align && (a<=UINT64_MAX-mask);
        out=0xdeadbeefcafebabeULL;CHECK(int_align_up(a,al,&out)==(uint8_t)ok_up);CHECK(out==(ok_up?((a+mask)&~mask):0xdeadbeefcafebabeULL));
        out=0xdeadbeefcafebabeULL;CHECK(int_align_down(a,al,&out)==(uint8_t)ok_align);CHECK(out==(ok_align?(a&~mask):0xdeadbeefcafebabeULL));
     }}
    puts("native core.int probes passed");return 0;
}
"""


class StdIntTests(unittest.TestCase):
    def test_module_compiles_and_assembles(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("assembly checks require NASM")
        compiled = compile_file(STD / "core" / "int.dg", roots=[STD])
        self.assertEqual(["core.int"], compiled.manifest()["modules"])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asm = directory / "int.asm"
            asm.write_text(compiled.assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(directory / (object_format + ".o")), str(asm)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)

    def test_native_int(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native core.int checks require NASM and a SysV-capable GCC host compiler")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            c_path = directory / "probe.c"
            c_path.write_text(C_SOURCE, encoding="utf-8")
            object_format = "win64" if os.name == "nt" else "elf64"
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    asm, obj = directory / (mode + ".asm"), directory / (mode + ".o")
                    exe = directory / (mode + (".exe" if os.name == "nt" else ""))
                    with tempfile.TemporaryDirectory() as roots:
                        entry = Path(roots) / "probe.dg"
                        entry.write_text(wrapper_source(), encoding="utf-8")
                        compiled = compile_file(entry, roots=[Path(roots), STD], mode=mode)
                    asm.write_text(compiled.assembly, encoding="utf-8")
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(obj), str(asm)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror", str(c_path), str(obj), "-o", str(exe)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("native core.int probes passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
