"""Independent C harness checks for core.slice byte-slice helpers."""
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
import core.slice as slice;
export("slice_equal") fn equal(a:[]const u8,b:[]const u8)bool{return slice.equal(a,b);}
export("slice_compare") fn compare(a:[]const u8,b:[]const u8)i32{return slice.compare(a,b);}
export("slice_find_byte") fn find_byte(b:[]const u8,v:u8,start:usize)usize{return slice.find_byte(b,v,start);}
export("slice_range_valid") fn range_valid(l:usize,lo:usize,hi:usize)bool{return slice.range_valid(l,lo,hi);}
"""


C_SOURCE = r"""
#define _GNU_SOURCE
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define CHECK(X) do{if(!(X)){fprintf(stderr,"core.slice check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
struct Bytes {const uint8_t *ptr;uint64_t len;};
extern uint8_t DG slice_equal(struct Bytes,struct Bytes);
extern int32_t DG slice_compare(struct Bytes,struct Bytes);
extern uint64_t DG slice_find_byte(struct Bytes,uint8_t,uint64_t);
extern uint8_t DG slice_range_valid(uint64_t,uint64_t,uint64_t);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    fprintf(stderr,"unexpected core.slice panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char *)file);exit(99);
}
int main(void){
    struct Bytes empty={NULL,0};
    CHECK(slice_equal(empty,empty));
    {uint8_t data[]={1,2,3};struct Bytes A={data,3};
     struct Bytes B={data,3};CHECK(slice_equal(A,B));
     uint8_t other[]={1,2,4};struct Bytes C={other,3};CHECK(!slice_equal(A,C));
     struct Bytes short_a={data,2};CHECK(!slice_equal(A,short_a));
     struct Bytes shifted={data+1,2};CHECK(!slice_equal(A,shifted));
     CHECK(!slice_equal(empty,A));CHECK(!slice_equal(A,empty));}
    {uint8_t a[]={0,1,2,255};struct Bytes A={a,4};
     uint8_t b[]={0,1,2,3};struct Bytes B={b,4};
     CHECK(slice_compare(A,B)==1);CHECK(slice_compare(B,A)==-1);CHECK(slice_compare(A,A)==0);
     struct Bytes prefix={a,3};CHECK(slice_compare(prefix,A)==-1);CHECK(slice_compare(A,prefix)==1);
     CHECK(slice_compare(empty,empty)==0);CHECK(slice_compare(empty,A)==-1);CHECK(slice_compare(A,empty)==1);}
    {uint8_t data[]={5,10,5,20,5,30};struct Bytes D={data,6};
     CHECK(slice_find_byte(D,5,0)==0);
     CHECK(slice_find_byte(D,5,1)==2);
     CHECK(slice_find_byte(D,20,0)==3);
     CHECK(slice_find_byte(D,30,0)==5);
     CHECK(slice_find_byte(D,99,0)==6);
     CHECK(slice_find_byte(D,5,6)==6);
     CHECK(slice_find_byte(D,5,7)==6);
     CHECK(slice_find_byte(D,0,0)==6);
     CHECK(slice_find_byte(empty,5,0)==0);
     CHECK(slice_find_byte(empty,5,1)==0);}
    CHECK(slice_range_valid(0,0,0));
    CHECK(slice_range_valid(10,0,10));
    CHECK(slice_range_valid(10,10,10));
    CHECK(slice_range_valid(10,3,7));
    CHECK(slice_range_valid(10,0,0));
    CHECK(!slice_range_valid(10,3,2));
    CHECK(!slice_range_valid(10,0,11));
    CHECK(!slice_range_valid(10,11,11));
    CHECK(slice_range_valid(UINT64_MAX,UINT64_MAX,UINT64_MAX));
    CHECK(!slice_range_valid(UINT64_MAX-1,UINT64_MAX,UINT64_MAX));
    puts("native core.slice probes passed");return 0;
}
"""


class StdSliceTests(unittest.TestCase):
    def test_module_compiles_and_assembles(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("assembly checks require NASM")
        compiled = compile_file(STD / "core" / "slice.dg", roots=[STD])
        self.assertEqual(["core.slice"], compiled.manifest()["modules"])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asm = directory / "slice.asm"
            asm.write_text(compiled.assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(directory / (object_format + ".o")), str(asm)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)

    def test_native_slice(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native core.slice checks require NASM and a SysV-capable GCC host compiler")
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
                    self.assertIn("native core.slice probes passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
