"""Independent C/assembly checks for arch.x86_64 hardware wrappers."""
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

# The Dong wrapper imports arch.x86_64 and re-exports the user-mode-safe calls
# plus layout checks. The privileged wrappers are emitted so their extern link
# names resolve against the NASM implementation, but are never called on a host.
WRAPPER = """module probe;
import arch.x86_64 as arch;

export("arch_layout_ok") fn layout_ok() u64 {
    if sizeof(arch.CpuId) != 16 { return 0; }
    if alignof(arch.CpuId) != 4 { return 0; }
    if offsetof(arch.CpuId, eax) != 0 { return 0; }
    if offsetof(arch.CpuId, ebx) != 4 { return 0; }
    if offsetof(arch.CpuId, ecx) != 8 { return 0; }
    if offsetof(arch.CpuId, edx) != 12 { return 0; }
    return 1;
}
export("arch_tsc") fn tsc() u64 { unsafe { return arch.read_tsc(); } }
export("arch_cpuid") fn cpuid(leaf:u32, subleaf:u32, out:*arch.CpuId) void { unsafe { arch.cpuid(leaf, subleaf, out); } }
export("arch_fences") fn fences() void { unsafe { arch.lfence(); arch.sfence(); arch.mfence(); } }
export("arch_in8") fn in8(port:u16) u8 { unsafe { return arch.in8(port); } }
export("arch_out8") fn out8(port:u16, value:u8) void { unsafe { arch.out8(port, value); } }
export("arch_read_cr3") fn read_cr3() u64 { unsafe { return arch.read_cr3(); } }
export("arch_write_cr3") fn write_cr3(v:u64) void { unsafe { arch.write_cr3(v); } }
export("arch_read_msr") fn read_msr(m:u32) u64 { unsafe { return arch.read_msr(m); } }
export("arch_write_msr") fn write_msr(m:u32, v:u64) void { unsafe { arch.write_msr(m, v); } }
"""

# Register-preservation observer. Calls dg_arch_cpuid directly and verifies the
# callee-saved RBX (which CPUID clobbers) and R12 (the out-pointer temp) survive.
OBSERVER = r"""
bits 64
default rel
section .text
global arch_regcheck
extern dg_arch_cpuid

arch_regcheck:
    push rbp
    mov rbp, rsp
    push rbx
    push r12
    mov rbx, 0x0b0b0b0b0b0b0b0b
    mov r12, 0x1212121212121212
    lea rdx, [rel arch_cpuid_out]
    xor edi, edi
    xor esi, esi
    call dg_arch_cpuid
    mov rax, 0x0b0b0b0b0b0b0b0b
    cmp rbx, rax
    jne .fail
    mov rax, 0x1212121212121212
    cmp r12, rax
    jne .fail
    mov eax, dword [rel arch_cpuid_out + 4]
    test eax, eax
    jz .fail
    mov eax, dword [rel arch_cpuid_out + 12]
    test eax, eax
    jz .fail
    mov eax, 1
    jmp .done
.fail:
    xor eax, eax
.done:
    pop r12
    pop rbx
    leave
    ret

section .bss
align 16
arch_cpuid_out: resb 16
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
#define CHECK(X) do{if(!(X)){fprintf(stderr,"arch.x86_64 check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
struct CpuId {uint32_t eax,ebx,ecx,edx;};
extern uint64_t DG arch_layout_ok(void);
extern uint64_t DG arch_tsc(void);
extern void DG arch_cpuid(uint32_t,uint32_t,struct CpuId *);
extern void DG arch_fences(void);
extern int DG arch_regcheck(void);
void DG __attribute__((noreturn)) __dong_panic(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    fprintf(stderr,"unexpected arch panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char *)file);exit(99);
}
int main(void){
    CHECK(arch_layout_ok()==1);
    uint64_t t0=arch_tsc();
    uint64_t t1=arch_tsc();
    CHECK(t1>=t0);
    struct CpuId id;
    arch_cpuid(0,0,&id);
    char vendor[13];
    memcpy(vendor+0,&id.ebx,4);
    memcpy(vendor+4,&id.edx,4);
    memcpy(vendor+8,&id.ecx,4);
    vendor[12]=0;
    int known = !strcmp(vendor,"GenuineIntel") || !strcmp(vendor,"AuthenticAMD")
             || !strcmp(vendor,"HygonGenuine") || !strcmp(vendor,"CentaurHauls");
    int printable=1;
    for(int i=0;i<12;++i)if(vendor[i]<0x20||vendor[i]>0x7e)printable=0;
    CHECK(known || printable);
    arch_cpuid(1,0,&id);
    CHECK(id.eax!=0);
    arch_fences();
    CHECK(arch_regcheck()==1);
    puts("native arch.x86_64 host probes passed");return 0;
}
"""


class StdArchTests(unittest.TestCase):
    def test_module_compiles_and_assembles(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("assembly checks require NASM")
        compiled = compile_file(STD / "arch" / "x86_64.dg", roots=[STD])
        self.assertEqual(["arch.x86_64"], compiled.manifest()["modules"])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            decl = directory / "decl.asm"
            decl.write_text(compiled.assembly, encoding="utf-8")
            impl = directory / "impl.asm"
            impl.write_text((STD / "arch" / "x86_64.asm").read_text(encoding="utf-8"), encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(directory / ("decl_" + object_format + ".o")), str(decl)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(directory / ("impl_" + object_format + ".o")), str(impl)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)

    def test_native_arch(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native arch checks require NASM and a SysV-capable GCC host compiler")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            c_path = directory / "probe.c"
            c_path.write_text(C_SOURCE, encoding="utf-8")
            object_format = "win64" if os.name == "nt" else "elf64"
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    asm, obj = directory / (mode + ".asm"), directory / (mode + ".o")
                    arch_obj, observer = directory / "arch.o", directory / "observer.o"
                    exe = directory / (mode + (".exe" if os.name == "nt" else ""))
                    with tempfile.TemporaryDirectory() as roots:
                        entry = Path(roots) / "probe.dg"
                        entry.write_text(WRAPPER, encoding="utf-8")
                        compiled = compile_file(entry, roots=[Path(roots), STD], mode=mode)
                    asm.write_text(compiled.assembly, encoding="utf-8")
                    for inp, out in [(asm, obj), (STD / "arch" / "x86_64.asm", arch_obj), (directory / "observer.asm", observer)]:
                        if inp == directory / "observer.asm":
                            inp.write_text(OBSERVER, encoding="utf-8")
                        result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(out), str(inp)], capture_output=True, text=True)
                        self.assertEqual(0, result.returncode, result.stderr)
                    command = [cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror"]
                    if os.name != "nt":
                        command += ["-no-pie"]
                    result = subprocess.run(command + [str(c_path), str(obj), str(arch_obj), str(observer), "-o", str(exe)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertIn("native arch.x86_64 host probes passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
