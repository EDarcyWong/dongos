"""Independent C harness checks for core.mem byte-memory primitives."""
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
import core.mem as m;
export("mem_copy") fn copy(d:*u8,s:*const u8,n:usize)void{unsafe{m.copy(d,s,n);}}
export("mem_move") fn move(d:*u8,s:*const u8,n:usize)void{unsafe{m.move(d,s,n);}}
export("mem_zero") fn zero(d:*u8,n:usize)void{unsafe{m.zero(d,n);}}
export("mem_compare") fn compare(a:*const u8,b:*const u8,n:usize)i32{unsafe{return m.compare(a,b,n);}}
"""


C_SOURCE = r"""
#define _GNU_SOURCE
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define CHECK(X) do{if(!(X)){fprintf(stderr,"core.mem check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
extern void DG mem_copy(uint8_t *,const uint8_t *,uint64_t);
extern void DG mem_move(uint8_t *,const uint8_t *,uint64_t);
extern void DG mem_zero(uint8_t *,uint64_t);
extern int32_t DG mem_compare(const uint8_t *,const uint8_t *,uint64_t);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    fprintf(stderr,"unexpected core.mem panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char *)file);exit(99);
}
int main(void){
    mem_copy(NULL,NULL,0);mem_move(NULL,NULL,0);mem_zero(NULL,0);
    CHECK(mem_compare(NULL,NULL,0)==0);
    {uint8_t src[64],dst[64];for(size_t i=0;i<sizeof(src);++i)src[i]=(uint8_t)(i*7+3);
     for(size_t n=0;n<=64;++n){memset(dst,0x5a,sizeof(dst));mem_copy(dst,src,n);
      for(size_t i=0;i<n;++i)CHECK(dst[i]==src[i]);
      for(size_t i=n;i<64;++i)CHECK(dst[i]==0x5a);}}
    {uint8_t in[64],out[64],before[64];for(size_t i=0;i<64;++i){in[i]=(uint8_t)(255-i);before[i]=in[i];}
     memset(out,0xa5,sizeof(out));mem_copy(out+1,in+3,33);
     CHECK(out[0]==0xa5);CHECK(out[34]==0xa5);
     for(size_t i=0;i<33;++i)CHECK(out[1+i]==in[3+i]);
     for(size_t i=0;i<64;++i)CHECK(in[i]==before[i]);}
    {uint8_t buf[48];memset(buf,0xa5,sizeof(buf));mem_zero(buf+1,17);
     CHECK(buf[0]==0xa5);for(size_t i=1;i<18;++i)CHECK(buf[i]==0);CHECK(buf[18]==0xa5);}
    {uint8_t a[16],b[16];for(size_t i=0;i<16;++i){a[i]=(uint8_t)i;b[i]=(uint8_t)i;}
     CHECK(mem_compare(a,b,16)==0);CHECK(mem_compare(a,b,0)==0);
     b[3]=200;CHECK(mem_compare(a,b,16)==-1);CHECK(mem_compare(b,a,16)==1);}
    {uint8_t a[8]={1,2,3,4,5,6,7,8},b[8]={1,2,3,4,9,9,9,9};
     CHECK(mem_compare(a,b,4)==0);CHECK(mem_compare(a,b,5)==-1);CHECK(mem_compare(b,a,5)==1);}
    {uint8_t buf[10]={0,1,2,3,4,5,6,7,8,9};mem_move(buf,buf+3,5);
     uint8_t expect[10]={3,4,5,6,7,5,6,7,8,9};CHECK(!memcmp(buf,expect,10));}
    {uint8_t buf[10]={0,1,2,3,4,5,6,7,8,9};mem_move(buf+3,buf,5);
     uint8_t expect[10]={0,1,2,0,1,2,3,4,8,9};CHECK(!memcmp(buf,expect,10));}
    {uint8_t buf[10]={9,8,7,6,5,4,3,2,1,0};uint8_t copy[10];memcpy(copy,buf,10);
     mem_move(buf,buf,10);CHECK(!memcmp(buf,copy,10));}
    {uint8_t src[32],dst[32];for(size_t i=0;i<32;++i)src[i]=(uint8_t)(i*5+2);
     memset(dst,0xcc,sizeof(dst));mem_move(dst,src,32);CHECK(!memcmp(dst,src,32));}
    puts("native core.mem probes passed");return 0;
}
"""


class StdMemTests(unittest.TestCase):
    def test_module_compiles_and_assembles(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("assembly checks require NASM")
        compiled = compile_file(STD / "core" / "mem.dg", roots=[STD])
        self.assertEqual(["core.mem"], compiled.manifest()["modules"])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asm = directory / "mem.asm"
            asm.write_text(compiled.assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(directory / (object_format + ".o")), str(asm)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)

    def test_native_mem(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native core.mem checks require NASM and a SysV-capable GCC host compiler")
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
                    self.assertIn("native core.mem probes passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
