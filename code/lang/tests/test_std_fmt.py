"""Independent C reference checks for core.fmt and core.errors."""
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

WRAPPER = """module probe;
import core.fmt as fmt;
import core.errors as errors;
error TestSinkFailed = 0x7777;
export("fmt_decimal") fn decimal(value:u64,output:[]u8)!usize{return fmt.decimal(value,output);}
export("fmt_signed_decimal") fn signed_decimal(value:i64,output:[]u8)!usize{return fmt.signed_decimal(value,output);}
export("fmt_hexadecimal") fn hexadecimal(value:u64,output:[]u8)!usize{return fmt.hexadecimal(value,output);}
export("fmt_write") fn write(bytes:[]const u8,output:[]u8)!usize{return fmt.write(bytes,output);}
export("fmt_emit") fn emit(bytes:[]const u8,sink:fn([]const u8)!void)!void{unsafe{return fmt.emit(bytes,sink);}}
"""

OBSERVER = r"""; Independent NASM callback + probe for core.fmt emit. The callback checks the
; slice args (RDI=ptr, RSI=len), the raw UTF-8/NUL bytes, increments a count and
; returns an explicit RAX/RDX {code,value}. The probe calls the exported Dong
; fmt_emit with this callback, avoiding passing a function pointer from C.
bits 64
default rel
section .text
global fmt_asm_sink
global fmt_asm_probe_ok
global fmt_asm_probe_fail
global fmt_sink_count_get
extern fmt_emit

fmt_asm_sink:
    inc qword [rel fmt_sink_count]
    cmp rsi, 7
    jne .fail
    cmp byte [rdi + 0], 0x41
    jne .fail
    cmp byte [rdi + 1], 0x00
    jne .fail
    cmp byte [rdi + 2], 0x42
    jne .fail
    cmp byte [rdi + 3], 0xe4
    jne .fail
    cmp byte [rdi + 4], 0xb8
    jne .fail
    cmp byte [rdi + 5], 0xad
    jne .fail
    cmp byte [rdi + 6], 0x43
    jne .fail
    xor eax, eax
    xor edx, edx
    ret
.fail:
    mov eax, 0x7777
    xor edx, edx
    ret

fmt_asm_probe_ok:
    sub rsp, 8
    lea rdi, [rel fmt_good_bytes]
    mov esi, 7
    lea rdx, [rel fmt_asm_sink]
    call fmt_emit
    add rsp, 8
    ret

fmt_asm_probe_fail:
    sub rsp, 8
    lea rdi, [rel fmt_bad_bytes]
    mov esi, 7
    lea rdx, [rel fmt_asm_sink]
    call fmt_emit
    add rsp, 8
    ret

fmt_sink_count_get:
    mov rax, [rel fmt_sink_count]
    ret

section .rodata
fmt_good_bytes: db 0x41, 0x00, 0x42, 0xe4, 0xb8, 0xad, 0x43
fmt_bad_bytes: db 0x41, 0x00, 0x42, 0x00, 0x00, 0x00, 0x00

section .bss
align 8
fmt_sink_count: resq 1
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
"""

C_SOURCE = r"""
#define _GNU_SOURCE
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
#define ERR_BUFFER_TOO_SMALL 0x01000001ULL
#define TEST_SINK_FAILED 0x7777ULL
struct Result {uint64_t code;uint64_t value;};
struct Bytes {const uint8_t *ptr;uint64_t len;};
extern struct Result DG fmt_decimal(uint64_t,struct Bytes);
extern struct Result DG fmt_signed_decimal(int64_t,struct Bytes);
extern struct Result DG fmt_hexadecimal(uint64_t,struct Bytes);
extern struct Result DG fmt_write(struct Bytes,struct Bytes);
extern struct Result DG fmt_asm_probe_ok(void);
extern struct Result DG fmt_asm_probe_fail(void);
extern uint64_t DG fmt_sink_count_get(void);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    fprintf(stderr,"unexpected core.fmt panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char *)file);exit(99);
}
#define CHECK(X) do{if(!(X)){fprintf(stderr,"core.fmt check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
static int check_decimal(uint64_t v){
    char ref[64];int n=snprintf(ref,sizeof(ref),"%" PRIu64,v);
    uint8_t buf[64];struct Result r=fmt_decimal(v,(struct Bytes){(const uint8_t*)buf,64});
    if(r.code!=0 || r.value!=(uint64_t)n || memcmp(buf,ref,(size_t)n)) return 0;
    memset(buf,0xa5,64);r=fmt_decimal(v,(struct Bytes){(const uint8_t*)buf,(uint64_t)n});
    if(r.code!=0 || r.value!=(uint64_t)n) return 0;
    uint8_t s[64];memset(s,0xa5,64);r=fmt_decimal(v,(struct Bytes){(const uint8_t*)s,(uint64_t)(n-1)});
    if(r.code!=ERR_BUFFER_TOO_SMALL) return 0;
    for(int i=0;i<64;++i)if(s[i]!=0xa5)return 0;
    return 1;
}
static int check_signed(int64_t v){
    char ref[64];int n=snprintf(ref,sizeof(ref),"%" PRId64,v);
    uint8_t buf[64];struct Result r=fmt_signed_decimal(v,(struct Bytes){(const uint8_t*)buf,64});
    if(r.code!=0 || r.value!=(uint64_t)n || memcmp(buf,ref,(size_t)n)) return 0;
    memset(buf,0xa5,64);r=fmt_signed_decimal(v,(struct Bytes){(const uint8_t*)buf,(uint64_t)n});
    if(r.code!=0 || r.value!=(uint64_t)n) return 0;
    uint8_t s[64];memset(s,0xa5,64);r=fmt_signed_decimal(v,(struct Bytes){(const uint8_t*)s,(uint64_t)(n-1)});
    if(r.code!=ERR_BUFFER_TOO_SMALL) return 0;
    for(int i=0;i<64;++i)if(s[i]!=0xa5)return 0;
    return 1;
}
static int check_hex(uint64_t v){
    char ref[64];int n=snprintf(ref,sizeof(ref),"%" PRIx64,v);
    uint8_t buf[64];struct Result r=fmt_hexadecimal(v,(struct Bytes){(const uint8_t*)buf,64});
    if(r.code!=0 || r.value!=(uint64_t)n || memcmp(buf,ref,(size_t)n)) return 0;
    memset(buf,0xa5,64);r=fmt_hexadecimal(v,(struct Bytes){(const uint8_t*)buf,(uint64_t)n});
    if(r.code!=0 || r.value!=(uint64_t)n) return 0;
    uint8_t s[64];memset(s,0xa5,64);r=fmt_hexadecimal(v,(struct Bytes){(const uint8_t*)s,(uint64_t)(n-1)});
    if(r.code!=ERR_BUFFER_TOO_SMALL) return 0;
    for(int i=0;i<64;++i)if(s[i]!=0xa5)return 0;
    return 1;
}
int main(void){
    {uint64_t v[]={0,1,9,10,42,255,4294967295ULL,UINT64_MAX};for(size_t i=0;i<sizeof(v)/sizeof(v[0]);++i)CHECK(check_decimal(v[i]));}
    {int64_t v[]={0,1,-1,9,-9,10,-10,INT64_MAX,INT64_MIN,-255};for(size_t i=0;i<sizeof(v)/sizeof(v[0]);++i)CHECK(check_signed(v[i]));}
    {uint64_t v[]={0,1,9,10,15,16,255,0xdeadbeefULL,UINT64_MAX};for(size_t i=0;i<sizeof(v)/sizeof(v[0]);++i)CHECK(check_hex(v[i]));}
    {uint8_t buf[16]={0x41,0x00,0x42,0x43};uint8_t out[16]={0};
     struct Result r=fmt_write((struct Bytes){(const uint8_t*)buf,4},(struct Bytes){(const uint8_t*)out,16});
     CHECK(r.code==0 && r.value==4 && out[0]==0x41 && out[1]==0x00 && out[2]==0x42 && out[3]==0x43);
     memset(out,0xa5,16);r=fmt_write((struct Bytes){(const uint8_t*)buf,4},(struct Bytes){(const uint8_t*)out,3});
     CHECK(r.code==ERR_BUFFER_TOO_SMALL && out[0]==0xa5);
     uint8_t ov[8]={0,1,2,3,4,5,6,7};r=fmt_write((struct Bytes){(const uint8_t*)ov+2,4},(struct Bytes){(const uint8_t*)ov,4});
     CHECK(r.code==0 && ov[0]==2 && ov[1]==3 && ov[2]==4 && ov[3]==5);}
    {struct Result r=fmt_asm_probe_ok();
     CHECK(r.code==0 && r.value==0 && fmt_sink_count_get()==1);
     r=fmt_asm_probe_fail();
     CHECK(r.code==TEST_SINK_FAILED && r.value==0 && fmt_sink_count_get()==2);}
    puts("native core.fmt probes passed");return 0;
}
"""


class StdFmtTests(unittest.TestCase):
    def test_module_compiles_and_assembles(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("assembly checks require NASM")
        compiled = compile_file(STD / "core" / "fmt.dg", roots=[STD])
        self.assertEqual(["core.errors", "core.fmt", "core.mem"], compiled.manifest()["modules"])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asm = directory / "fmt.asm"
            asm.write_text(compiled.assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(directory / (object_format + ".o")), str(asm)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)

    def test_native_fmt(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native core.fmt checks require NASM and a SysV-capable GCC host compiler")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            c_path = directory / "probe.c"
            c_path.write_text(C_SOURCE, encoding="utf-8")
            object_format = "win64" if os.name == "nt" else "elf64"
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    asm, obj = directory / (mode + ".asm"), directory / (mode + ".o")
                    observer = directory / "observer.o"
                    exe = directory / (mode + (".exe" if os.name == "nt" else ""))
                    with tempfile.TemporaryDirectory() as roots:
                        entry = Path(roots) / "probe.dg"
                        entry.write_text(WRAPPER, encoding="utf-8")
                        compiled = compile_file(entry, roots=[Path(roots), STD], mode=mode)
                    asm.write_text(compiled.assembly, encoding="utf-8")
                    (directory / "observer.asm").write_text(OBSERVER, encoding="utf-8")
                    for inp, out in [(asm, obj), (directory / "observer.asm", observer)]:
                        result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(out), str(inp)], capture_output=True, text=True)
                        self.assertEqual(0, result.returncode, result.stderr)
                    command = [cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror"]
                    if os.name != "nt":
                        command += ["-no-pie"]
                    result = subprocess.run(command + [str(c_path), str(obj), str(observer), "-o", str(exe)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("native core.fmt probes passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
