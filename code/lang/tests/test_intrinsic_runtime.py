"""Independent C/NASM checks for wrapping and hardware-memory intrinsics."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from lang.dongc import compile_source
from lang.tests.test_dongc import nasm_flags, tool


INTEGER_TYPES = [(sign + str(width), sign == "i", width) for width in (8, 16, 32, 64) for sign in "ui"]


def dong_source():
    declarations = ["module intrinsic_runtime;"]
    for typ, signed, width in INTEGER_TYPES:
        minimum, maximum = (-(1 << (width - 1)), (1 << (width - 1)) - 1) if signed else (0, (1 << width) - 1)
        operands = {"add": (maximum, 1), "sub": (minimum, 1), "mul": (minimum, -1)} if signed else {
            "add": (maximum, 1), "sub": (0, 1), "mul": (maximum, 2)}
        for op in ("add", "sub", "mul"):
            a, b = operands[op]
            declarations += [
                f'export("intr_wrap_{typ}_{op}") fn wrap_{typ}_{op}(a:{typ},b:{typ}){typ}{{return wrapping_{op}(a,b);}}',
                f'const A_{typ}_{op}:{typ}={a}; const B_{typ}_{op}:{typ}={b};',
                f'const C_{typ}_{op}:{typ}=wrapping_{op}(A_{typ}_{op},B_{typ}_{op});',
                f'export("intr_const_{typ}_{op}") fn constant_{typ}_{op}(){typ}{{return C_{typ}_{op};}}',
            ]
        for prefix, load, store in (("u", "read_unaligned", "write_unaligned"), ("v", "volatile_load", "volatile_store")):
            declarations += [
                f'export("intr_{prefix}read_{typ}") fn {prefix}read_{typ}(p:*const {typ}){typ}{{unsafe{{return {load}(p);}}}}',
                f'export("intr_{prefix}write_{typ}") fn {prefix}write_{typ}(p:*{typ},v:{typ})void{{unsafe{{{store}(p,v);}}}}',
            ]
    for width in (32, 64):
        typ = "u" + str(width)
        declarations += [
            f'export("intr_atomic_load{width}") fn load{width}(p:*const {typ}){typ}{{unsafe{{return atomic_load(p);}}}}',
            f'export("intr_atomic_store{width}") fn store{width}(p:*{typ},v:{typ})void{{unsafe{{atomic_store(p,v);}}}}',
            f'export("intr_cas{width}") fn cas{width}(p:*{typ},e:{typ},d:{typ}){typ}{{unsafe{{return atomic_compare_exchange(p,e,d);}}}}',
            f'export("intr_fetch{width}") fn fetch{width}(p:*{typ},d:{typ}){typ}{{unsafe{{return atomic_fetch_add(p,d);}}}}',
        ]
    declarations.append('''
        extern "sysv64" fn intr_mark_pointer(p:*u32,tag:u64)*u32;
        extern "sysv64" fn intr_mark_value(value:u64,tag:u64)u64;
        extern "sysv64" fn intr_observe(p:*u32,next:u32)u32;
        export("intr_order_store") fn order_store(p:*u32)void{
            unsafe{volatile_store(intr_mark_pointer(p,1),intr_mark_value(42,2) as u32);}
        }
        export("intr_order_load") fn order_load(p:*u32)u32{
            unsafe{return volatile_load(intr_mark_pointer(p,1));}
        }
        export("intr_order_cas") fn order_cas(p:*u32)u32{
            unsafe{return atomic_compare_exchange(intr_mark_pointer(p,1),intr_mark_value(17,2) as u32,intr_mark_value(23,3) as u32);}
        }
        export("intr_order_fetch") fn order_fetch(p:*u32)u32{
            unsafe{return atomic_fetch_add(intr_mark_pointer(p,1),intr_mark_value(3,2) as u32);}
        }
        export("intr_order_unaligned") fn order_unaligned(p:*u32)u32{
            unsafe{write_unaligned(intr_mark_pointer(p,1),intr_mark_value(0xaabbccdd,2) as u32);return read_unaligned(p);}
        }
        export("intr_order_wrapping") fn order_wrapping()u8{
            unsafe{return wrapping_add(intr_mark_value(255,1) as u8,intr_mark_value(2,2) as u8);}
        }
        export("intr_volatile_sequence") fn volatile_sequence(p:*u32)u32{
            unsafe{
                volatile_store(p,1);
                let before=intr_observe(p,2);
                let after=volatile_load(p);
                compiler_fence();
                volatile_store(p,before+after);
                return volatile_load(p);
            }
        }
        export("intr_fence") fn fence()void{unsafe{compiler_fence();}}
    ''')
    return "\n".join(declarations)


OBSERVER = r'''
bits 64
default rel
section .text
global __dong_panic
global intr_mark_value
extern intr_panic_record
extern intr_record_token
__dong_panic:
    jmp intr_panic_record
intr_mark_value:
    push rbp
    mov rbp,rsp
    sub rsp,16
    mov qword [rbp-8],rdi
    mov rdi,rsi
    call intr_record_token
    mov rax,qword [rbp-8]
    mov rdi,0x1111111122222222
    mov rsi,0x3333333344444444
    mov rdx,0x5555555566666666
    mov rcx,0x7777777788888888
    mov r8,0x99999999aaaaaaaa
    mov r9,0xbbbbbbbbcccccccc
    mov r10,0xddddddddeeeeeeee
    mov r11,0xffffffffffffffff
    mov rsp,rbp
    pop rbp
    ret
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
'''


def c_source():
    source = [r'''
#define _GNU_SOURCE
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#include <sys/mman.h>
#include <unistd.h>
#endif
#define DG __attribute__((sysv_abi))
#define CHECK(X) do{if(!(X)){fprintf(stderr,"intrinsic check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
static uint64_t sequence;
void DG intr_record_token(uint64_t token){sequence=sequence*10+token;}
uint32_t *DG intr_mark_pointer(uint32_t *p,uint64_t token){intr_record_token(token);return p;}
uint32_t DG intr_observe(uint32_t *p,uint32_t next){uint32_t old=*(volatile uint32_t *)p;*(volatile uint32_t *)p=next;return old;}
void DG __attribute__((noreturn)) intr_panic_record(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    fprintf(stderr,"unexpected intrinsic panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char *)file);exit(99);
}
static uint64_t random_bits(uint64_t *state){*state^=*state<<13;*state^=*state>>7;*state^=*state<<17;return *state;}
extern void DG intr_order_store(uint32_t *),intr_fence(void);
extern uint32_t DG intr_order_load(uint32_t *),intr_order_cas(uint32_t *),intr_order_fetch(uint32_t *),intr_order_unaligned(uint32_t *),intr_volatile_sequence(uint32_t *);
extern uint8_t DG intr_order_wrapping(void);
''']
    for width in (8, 16, 32, 64):
        source.append(f"static int{width}_t signed{width}(uint{width}_t bits){{int{width}_t value;memcpy(&value,&bits,sizeof(value));return value;}}")
    for typ, signed, width in INTEGER_TYPES:
        ctyp = ("int" if signed else "uint") + str(width) + "_t"
        for op in ("add", "sub", "mul"):
            source += [f"extern {ctyp} DG intr_wrap_{typ}_{op}({ctyp},{ctyp});", f"extern {ctyp} DG intr_const_{typ}_{op}(void);"]
        for prefix in ("u", "v"):
            source += [f"extern {ctyp} DG intr_{prefix}read_{typ}(const {ctyp} *);",
                       f"extern void DG intr_{prefix}write_{typ}({ctyp} *,{ctyp});"]
    source.append(r'''
extern uint32_t DG intr_atomic_load32(const uint32_t *),intr_cas32(uint32_t *,uint32_t,uint32_t),intr_fetch32(uint32_t *,uint32_t);
extern uint64_t DG intr_atomic_load64(const uint64_t *),intr_cas64(uint64_t *,uint64_t,uint64_t),intr_fetch64(uint64_t *,uint64_t);
extern void DG intr_atomic_store32(uint32_t *,uint32_t),intr_atomic_store64(uint64_t *,uint64_t);
static uint32_t counter32;
static uint64_t counter64;
struct Worker { unsigned mode; };
static void increment_counters(unsigned mode){
    for(unsigned i=0;i<4000;++i){
        if(mode&1){
            uint32_t expected32,old32;
            do{expected32=intr_atomic_load32(&counter32);old32=intr_cas32(&counter32,expected32,expected32+1);}while(old32!=expected32);
            uint64_t expected64,old64;
            do{expected64=intr_atomic_load64(&counter64);old64=intr_cas64(&counter64,expected64,expected64+1);}while(old64!=expected64);
        }else{(void)intr_fetch32(&counter32,1);(void)intr_fetch64(&counter64,1);}
    }
}
#ifdef _WIN32
static DWORD WINAPI worker(LPVOID context){increment_counters(((struct Worker *)context)->mode);return 0;}
#else
static void *worker(void *context){increment_counters(((struct Worker *)context)->mode);return NULL;}
#endif
int main(void){
    size_t page_size;
    uint8_t *guard;
#ifdef _WIN32
    SYSTEM_INFO system_info;GetSystemInfo(&system_info);page_size=system_info.dwPageSize;
    guard=VirtualAlloc(NULL,page_size*2,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);CHECK(guard!=NULL);
    DWORD previous;CHECK(VirtualProtect(guard+page_size,page_size,PAGE_NOACCESS,&previous)!=0);
#else
    page_size=(size_t)sysconf(_SC_PAGESIZE);
    guard=mmap(NULL,page_size*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);CHECK(guard!=MAP_FAILED);
    CHECK(mprotect(guard+page_size,page_size,PROT_NONE)==0);
#endif
    uint64_t seed=UINT64_C(0x46ad39be7c821105);
''')
    for typ, signed, width in INTEGER_TYPES:
        ctyp, utyp = ("int" if signed else "uint") + str(width) + "_t", f"uint{width}_t"
        as_typed = lambda value: f"signed{width}(({utyp})({value}))" if signed else f"({utyp})({value})"
        minimum, maximum = f"INT{width}_MIN", f"INT{width}_MAX" if signed else f"UINT{width}_MAX"
        value = f"({ctyp})({minimum}+5)" if signed else f"({ctyp})({maximum}-5)"
        constants = {"add": minimum, "sub": maximum, "mul": minimum} if signed else {
            "add": "0", "sub": maximum, "mul": f"({ctyp})({maximum}-1)"}
        source.append("{")
        for op, operator in (("add", "+"), ("sub", "-"), ("mul", "*")):
            source.append(f"CHECK(intr_const_{typ}_{op}()=={constants[op]});")
        source.append(f"for(unsigned trial=0;trial<96;++trial){{{utyp} ua=({utyp})random_bits(&seed),ub=({utyp})random_bits(&seed);{ctyp} a={as_typed('ua')},b={as_typed('ub')};")
        for op, operator in (("add", "+"), ("sub", "-"), ("mul", "*")):
            source.append(f"CHECK(intr_wrap_{typ}_{op}(a,b)=={as_typed(f'(uint64_t)ua {operator} (uint64_t)ub')});")
        source.append("}")
        source.append(f"uint8_t buffer[64],expected[64];{ctyp} value={value};memset(buffer,0xa5,sizeof(buffer));memset(expected,0xa5,sizeof(expected));memcpy(expected+3,&value,sizeof(value));")
        source.append(f"intr_uwrite_{typ}(({ctyp} *)(void *)(buffer+3),value);CHECK(!memcmp(buffer,expected,sizeof(buffer)));CHECK(intr_uread_{typ}((const {ctyp} *)(const void *)(buffer+3))==value);")
        source.append(f"memset(guard,0xa5,page_size);uint8_t *edge=guard+page_size-sizeof(value);intr_vwrite_{typ}(({ctyp} *)(void *)edge,value);CHECK(!memcmp(edge,&value,sizeof(value)));CHECK(edge[-1]==0xa5);CHECK(intr_vread_{typ}((const {ctyp} *)(const void *)edge)==value);")
        source.append("}")
    source.append(r'''
    uint32_t ordered=0;
    sequence=0;intr_order_store(&ordered);CHECK(sequence==12 && ordered==42);
    sequence=0;CHECK(intr_order_load(&ordered)==42 && sequence==1);
    sequence=0;ordered=17;CHECK(intr_order_cas(&ordered)==17 && ordered==23 && sequence==123);
    sequence=0;ordered=11;CHECK(intr_order_cas(&ordered)==11 && ordered==11 && sequence==123);
    sequence=0;ordered=UINT32_MAX;CHECK(intr_order_fetch(&ordered)==UINT32_MAX && ordered==2 && sequence==12);
    sequence=0;CHECK(intr_order_wrapping()==1 && sequence==12);
    uint8_t unaligned[8];memset(unaligned,0xa5,sizeof(unaligned));sequence=0;
    CHECK(intr_order_unaligned((uint32_t *)(void *)(unaligned+1))==UINT32_C(0xaabbccdd) && sequence==12);
    CHECK(unaligned[0]==0xa5 && unaligned[5]==0xa5 && unaligned[6]==0xa5 && unaligned[7]==0xa5);
    CHECK(intr_volatile_sequence(&ordered)==3 && ordered==3);intr_fence();
    struct {uint32_t left,value,right;} cell32={0xabcdef01,0,0x12345678};
    struct {uint64_t left,value,right;} cell64={UINT64_C(0xabcdef0123456789),0,UINT64_C(0x123456789abcdef0)};
    intr_atomic_store32(&cell32.value,UINT32_MAX);CHECK(intr_atomic_load32(&cell32.value)==UINT32_MAX);
    CHECK(intr_fetch32(&cell32.value,3)==UINT32_MAX && intr_atomic_load32(&cell32.value)==2);
    CHECK(intr_cas32(&cell32.value,2,19)==2 && intr_atomic_load32(&cell32.value)==19);
    CHECK(intr_cas32(&cell32.value,2,99)==19 && intr_atomic_load32(&cell32.value)==19);
    CHECK(cell32.left==UINT32_C(0xabcdef01) && cell32.right==UINT32_C(0x12345678));
    intr_atomic_store64(&cell64.value,UINT64_MAX);CHECK(intr_atomic_load64(&cell64.value)==UINT64_MAX);
    CHECK(intr_fetch64(&cell64.value,9)==UINT64_MAX && intr_atomic_load64(&cell64.value)==8);
    CHECK(intr_cas64(&cell64.value,8,29)==8 && intr_atomic_load64(&cell64.value)==29);
    CHECK(intr_cas64(&cell64.value,8,99)==29 && intr_atomic_load64(&cell64.value)==29);
    CHECK(cell64.left==UINT64_C(0xabcdef0123456789) && cell64.right==UINT64_C(0x123456789abcdef0));
    intr_atomic_store32(&counter32,0);intr_atomic_store64(&counter64,0);
    struct Worker contexts[4]={{0},{1},{0},{1}};
#ifdef _WIN32
    HANDLE threads[4];
    for(unsigned i=0;i<4;++i){threads[i]=CreateThread(NULL,0,worker,&contexts[i],0,NULL);CHECK(threads[i]!=NULL);}
    CHECK(WaitForMultipleObjects(4,threads,TRUE,INFINITE)==WAIT_OBJECT_0);
    for(unsigned i=0;i<4;++i)CHECK(CloseHandle(threads[i])!=0);
    CHECK(VirtualFree(guard,0,MEM_RELEASE)!=0);
#else
    pthread_t threads[4];
    for(unsigned i=0;i<4;++i)CHECK(pthread_create(&threads[i],NULL,worker,&contexts[i])==0);
    for(unsigned i=0;i<4;++i)CHECK(pthread_join(threads[i],NULL)==0);
    CHECK(munmap(guard,page_size*2)==0);
#endif
    CHECK(intr_atomic_load32(&counter32)==16000 && intr_atomic_load64(&counter64)==16000);
    puts("native wrapping, exact-width memory and contended atomic intrinsic probes passed");return 0;
}
''')
    return "\n".join(source)


class IntrinsicRuntimeTests(unittest.TestCase):
    def assemble(self, nasm, source, output, object_format):
        result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(output), str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_elf_and_coff_encoding_and_compiler_fence(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("intrinsic encoding checks require NASM")
        compiled = compile_source(dong_source(), "intrinsic_runtime.dg")
        fence = compiled.assembly.split("$intr_fence:", 1)[1].split("\nalign 16", 1)[0].split("section .rodata", 1)[0]
        self.assertNotRegex(fence, r"\b(?:mfence|sfence|lfence|lock)\b")
        self.assertNotRegex(compiled.assembly, r"\b(?:xmm|ymm|zmm)[0-9]+\b")
        for typ, _, width in INTEGER_TYPES:
            for operation, intrinsic in (("read", "volatile_load"), ("write", "volatile_store")):
                with self.subTest(type=typ, operation=operation):
                    body = compiled.assembly.split(f"$intr_v{operation}_{typ}:", 1)[1].split("\nalign 16", 1)[0]
                    access = body.split("; intrinsic " + intrinsic, 1)[1]
                    # Argument snapshots precede the intrinsic barrier. Ignore
                    # stack-slot reads afterwards, and count only target memory.
                    widths = re.findall(r"\b(byte|word|dword|qword)\s+\[(?!rbp\b|rsp\b|r12\b)[^\]]+\]", access)
                    self.assertEqual(widths, [{8: "byte", 16: "word", 32: "dword", 64: "qword"}[width]])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "intrinsics.asm"
            source.write_text(compiled.assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    self.assemble(nasm, source, directory / (object_format + ".o"), object_format)

    def test_native_intrinsics_and_four_thread_xadd_cas_competition(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native intrinsic probes require NASM and a SysV-capable GCC host compiler")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            c, observer = directory / "probe.c", directory / "observer.asm"
            c.write_text(c_source(), encoding="utf-8")
            observer.write_text(OBSERVER, encoding="utf-8")
            object_format = "win64" if os.name == "nt" else "elf64"
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    source, obj, abi = directory / (mode + ".asm"), directory / (mode + ".o"), directory / "observer.o"
                    executable = directory / (mode + (".exe" if os.name == "nt" else ""))
                    source.write_text(compile_source(dong_source(), "intrinsic_runtime.dg", mode=mode).assembly, encoding="utf-8")
                    self.assemble(nasm, source, obj, object_format)
                    self.assemble(nasm, observer, abi, object_format)
                    command = [cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror"]
                    if os.name != "nt":
                        command += ["-no-pie", "-pthread"]
                    result = subprocess.run(command + [str(c), str(obj), str(abi), "-o", str(executable)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("native wrapping, exact-width memory and contended atomic intrinsic probes passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
