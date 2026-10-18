"""Permanent negative controls: a bad arch wrapper must be rejected by the gate."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.build import ROOT, ToolError, find_firmware, find_tool
import tests.run_std_arch_qemu as runner

BAD_CR3_ARCH = "bits 64\ndefault rel\nsection .text\nglobal dg_arch_in8\ndg_arch_in8:\n    mov dx, di\n    in al, dx\n    ret\nglobal dg_arch_out8\ndg_arch_out8:\n    mov dx, di\n    mov al, sil\n    out dx, al\n    ret\nglobal dg_arch_read_cr3\ndg_arch_read_cr3:\n    xor eax, eax\n    xor edx, edx\n    ret\nglobal dg_arch_write_cr3\ndg_arch_write_cr3:\n    ret\nglobal dg_arch_read_msr\ndg_arch_read_msr:\n    mov ecx, edi\n    rdmsr\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_write_msr\ndg_arch_write_msr:\n    mov ecx, edi\n    mov eax, esi\n    mov rdx, rsi\n    shr rdx, 32\n    wrmsr\n    ret\nglobal dg_arch_read_tsc\ndg_arch_read_tsc:\n    rdtsc\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_cpuid\ndg_arch_cpuid:\n    push rbx\n    push r12\n    mov r12, rdx\n    mov eax, edi\n    mov ecx, esi\n    cpuid\n    mov [r12 + 0], eax\n    mov [r12 + 4], ebx\n    mov [r12 + 8], ecx\n    mov [r12 + 12], edx\n    pop r12\n    pop rbx\n    ret\nglobal dg_arch_lfence\ndg_arch_lfence:\n    lfence\n    ret\nglobal dg_arch_sfence\ndg_arch_sfence:\n    sfence\n    ret\nglobal dg_arch_mfence\ndg_arch_mfence:\n    mfence\n    ret\n%ifidn __OUTPUT_FORMAT__,elf64\nsection .note.GNU-stack noalloc noexec nowrite progbits\n%endif"
BAD_MSR_ARCH = "bits 64\ndefault rel\nsection .text\nglobal dg_arch_in8\ndg_arch_in8:\n    mov dx, di\n    in al, dx\n    ret\nglobal dg_arch_out8\ndg_arch_out8:\n    mov dx, di\n    mov al, sil\n    out dx, al\n    ret\nglobal dg_arch_read_cr3\ndg_arch_read_cr3:\n    mov rax, cr3\n    ret\nglobal dg_arch_write_cr3\ndg_arch_write_cr3:\n    mov cr3, rdi\n    ret\nglobal dg_arch_read_msr\ndg_arch_read_msr:\n    mov ecx, 0xc0000101\n    rdmsr\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_write_msr\ndg_arch_write_msr:\n    mov ecx, 0xc0000101\n    mov eax, esi\n    mov rdx, rsi\n    shr rdx, 32\n    wrmsr\n    ret\nglobal dg_arch_read_tsc\ndg_arch_read_tsc:\n    rdtsc\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_cpuid\ndg_arch_cpuid:\n    push rbx\n    push r12\n    mov r12, rdx\n    mov eax, edi\n    mov ecx, esi\n    cpuid\n    mov [r12 + 0], eax\n    mov [r12 + 4], ebx\n    mov [r12 + 8], ecx\n    mov [r12 + 12], edx\n    pop r12\n    pop rbx\n    ret\nglobal dg_arch_lfence\ndg_arch_lfence:\n    lfence\n    ret\nglobal dg_arch_sfence\ndg_arch_sfence:\n    sfence\n    ret\nglobal dg_arch_mfence\ndg_arch_mfence:\n    mfence\n    ret\n%ifidn __OUTPUT_FORMAT__,elf64\nsection .note.GNU-stack noalloc noexec nowrite progbits\n%endif"
BAD_MSR_HIGH_ARCH = "bits 64\ndefault rel\nsection .text\nglobal dg_arch_in8\ndg_arch_in8:\n    mov dx, di\n    in al, dx\n    ret\nglobal dg_arch_out8\ndg_arch_out8:\n    mov dx, di\n    mov al, sil\n    out dx, al\n    ret\nglobal dg_arch_read_cr3\ndg_arch_read_cr3:\n    mov rax, cr3\n    ret\nglobal dg_arch_write_cr3\ndg_arch_write_cr3:\n    mov cr3, rdi\n    ret\nglobal dg_arch_read_msr\ndg_arch_read_msr:\n    mov ecx, edi\n    rdmsr\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_write_msr\ndg_arch_write_msr:\n    mov ecx, edi\n    mov eax, esi\n    xor edx, edx\n    wrmsr\n    ret\nglobal dg_arch_read_tsc\ndg_arch_read_tsc:\n    rdtsc\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_cpuid\ndg_arch_cpuid:\n    push rbx\n    push r12\n    mov r12, rdx\n    mov eax, edi\n    mov ecx, esi\n    cpuid\n    mov [r12 + 0], eax\n    mov [r12 + 4], ebx\n    mov [r12 + 8], ecx\n    mov [r12 + 12], edx\n    pop r12\n    pop rbx\n    ret\nglobal dg_arch_lfence\ndg_arch_lfence:\n    lfence\n    ret\nglobal dg_arch_sfence\ndg_arch_sfence:\n    sfence\n    ret\nglobal dg_arch_mfence\ndg_arch_mfence:\n    mfence\n    ret\n%ifidn __OUTPUT_FORMAT__,elf64\nsection .note.GNU-stack noalloc noexec nowrite progbits\n%endif"
BAD_ABI_ARCH = "bits 64\ndefault rel\nsection .text\nglobal dg_arch_in8\ndg_arch_in8:\n    mov dx, di\n    in al, dx\n    mov rbx, 0xdeadbeefdeadbeef\n    ret\nglobal dg_arch_out8\ndg_arch_out8:\n    mov dx, di\n    mov al, sil\n    out dx, al\n    ret\nglobal dg_arch_read_cr3\ndg_arch_read_cr3:\n    mov rax, cr3\n    ret\nglobal dg_arch_write_cr3\ndg_arch_write_cr3:\n    mov cr3, rdi\n    ret\nglobal dg_arch_read_msr\ndg_arch_read_msr:\n    mov ecx, edi\n    rdmsr\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_write_msr\ndg_arch_write_msr:\n    mov ecx, edi\n    mov eax, esi\n    mov rdx, rsi\n    shr rdx, 32\n    wrmsr\n    ret\nglobal dg_arch_read_tsc\ndg_arch_read_tsc:\n    rdtsc\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_cpuid\ndg_arch_cpuid:\n    push rbx\n    push r12\n    mov r12, rdx\n    mov eax, edi\n    mov ecx, esi\n    cpuid\n    mov [r12 + 0], eax\n    mov [r12 + 4], ebx\n    mov [r12 + 8], ecx\n    mov [r12 + 12], edx\n    pop r12\n    pop rbx\n    ret\nglobal dg_arch_lfence\ndg_arch_lfence:\n    lfence\n    ret\nglobal dg_arch_sfence\ndg_arch_sfence:\n    sfence\n    ret\nglobal dg_arch_mfence\ndg_arch_mfence:\n    mfence\n    ret\n%ifidn __OUTPUT_FORMAT__,elf64\nsection .note.GNU-stack noalloc noexec nowrite progbits\n%endif"
BAD_PORT_ARCH = "bits 64\ndefault rel\nsection .text\nglobal dg_arch_in8\ndg_arch_in8:\n    mov dx, 0x3fe\n    in al, dx\n    ret\nglobal dg_arch_out8\ndg_arch_out8:\n    mov dx, 0x3fe\n    mov al, sil\n    out dx, al\n    ret\nglobal dg_arch_read_cr3\ndg_arch_read_cr3:\n    mov rax, cr3\n    ret\nglobal dg_arch_write_cr3\ndg_arch_write_cr3:\n    mov cr3, rdi\n    ret\nglobal dg_arch_read_msr\ndg_arch_read_msr:\n    mov ecx, edi\n    rdmsr\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_write_msr\ndg_arch_write_msr:\n    mov ecx, edi\n    mov eax, esi\n    mov rdx, rsi\n    shr rdx, 32\n    wrmsr\n    ret\nglobal dg_arch_read_tsc\ndg_arch_read_tsc:\n    rdtsc\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_cpuid\ndg_arch_cpuid:\n    push rbx\n    push r12\n    mov r12, rdx\n    mov eax, edi\n    mov ecx, esi\n    cpuid\n    mov [r12 + 0], eax\n    mov [r12 + 4], ebx\n    mov [r12 + 8], ecx\n    mov [r12 + 12], edx\n    pop r12\n    pop rbx\n    ret\nglobal dg_arch_lfence\ndg_arch_lfence:\n    lfence\n    ret\nglobal dg_arch_sfence\ndg_arch_sfence:\n    sfence\n    ret\nglobal dg_arch_mfence\ndg_arch_mfence:\n    mfence\n    ret\n%ifidn __OUTPUT_FORMAT__,elf64\nsection .note.GNU-stack noalloc noexec nowrite progbits\n%endif"
BAD_CR3_RET8_ARCH = "bits 64\ndefault rel\nsection .text\nglobal dg_arch_in8\ndg_arch_in8:\n    mov dx, di\n    in al, dx\n    ret\nglobal dg_arch_out8\ndg_arch_out8:\n    mov dx, di\n    mov al, sil\n    out dx, al\n    ret\nglobal dg_arch_read_cr3\ndg_arch_read_cr3:\n    mov rax, cr3\n    ret 8\nglobal dg_arch_write_cr3\ndg_arch_write_cr3:\n    mov cr3, rdi\n    ret\nglobal dg_arch_read_msr\ndg_arch_read_msr:\n    mov ecx, edi\n    rdmsr\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_write_msr\ndg_arch_write_msr:\n    mov ecx, edi\n    mov eax, esi\n    mov rdx, rsi\n    shr rdx, 32\n    wrmsr\n    ret\nglobal dg_arch_read_tsc\ndg_arch_read_tsc:\n    rdtsc\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_cpuid\ndg_arch_cpuid:\n    push rbx\n    push r12\n    mov r12, rdx\n    mov eax, edi\n    mov ecx, esi\n    cpuid\n    mov [r12 + 0], eax\n    mov [r12 + 4], ebx\n    mov [r12 + 8], ecx\n    mov [r12 + 12], edx\n    pop r12\n    pop rbx\n    ret\nglobal dg_arch_lfence\ndg_arch_lfence:\n    lfence\n    ret\nglobal dg_arch_sfence\ndg_arch_sfence:\n    sfence\n    ret\nglobal dg_arch_mfence\ndg_arch_mfence:\n    mfence\n    ret\n%ifidn __OUTPUT_FORMAT__,elf64\nsection .note.GNU-stack noalloc noexec nowrite progbits\n%endif"
BAD_WCR3_RET8_ARCH = "bits 64\ndefault rel\nsection .text\nglobal dg_arch_in8\ndg_arch_in8:\n    mov dx, di\n    in al, dx\n    ret\nglobal dg_arch_out8\ndg_arch_out8:\n    mov dx, di\n    mov al, sil\n    out dx, al\n    ret\nglobal dg_arch_read_cr3\ndg_arch_read_cr3:\n    mov rax, cr3\n    ret\nglobal dg_arch_write_cr3\ndg_arch_write_cr3:\n    mov cr3, rdi\n    ret 8\nglobal dg_arch_read_msr\ndg_arch_read_msr:\n    mov ecx, edi\n    rdmsr\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_write_msr\ndg_arch_write_msr:\n    mov ecx, edi\n    mov eax, esi\n    mov rdx, rsi\n    shr rdx, 32\n    wrmsr\n    ret\nglobal dg_arch_read_tsc\ndg_arch_read_tsc:\n    rdtsc\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_cpuid\ndg_arch_cpuid:\n    push rbx\n    push r12\n    mov r12, rdx\n    mov eax, edi\n    mov ecx, esi\n    cpuid\n    mov [r12 + 0], eax\n    mov [r12 + 4], ebx\n    mov [r12 + 8], ecx\n    mov [r12 + 12], edx\n    pop r12\n    pop rbx\n    ret\nglobal dg_arch_lfence\ndg_arch_lfence:\n    lfence\n    ret\nglobal dg_arch_sfence\ndg_arch_sfence:\n    sfence\n    ret\nglobal dg_arch_mfence\ndg_arch_mfence:\n    mfence\n    ret\n%ifidn __OUTPUT_FORMAT__,elf64\nsection .note.GNU-stack noalloc noexec nowrite progbits\n%endif"
BAD_RET8_ARCH = "bits 64\ndefault rel\nsection .text\nglobal dg_arch_in8\ndg_arch_in8:\n    mov dx, di\n    in al, dx\n    ret\nglobal dg_arch_out8\ndg_arch_out8:\n    mov dx, di\n    mov al, sil\n    out dx, al\n    ret 8\nglobal dg_arch_read_cr3\ndg_arch_read_cr3:\n    mov rax, cr3\n    ret\nglobal dg_arch_write_cr3\ndg_arch_write_cr3:\n    mov cr3, rdi\n    ret\nglobal dg_arch_read_msr\ndg_arch_read_msr:\n    mov ecx, edi\n    rdmsr\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_write_msr\ndg_arch_write_msr:\n    mov ecx, edi\n    mov eax, esi\n    mov rdx, rsi\n    shr rdx, 32\n    wrmsr\n    ret\nglobal dg_arch_read_tsc\ndg_arch_read_tsc:\n    rdtsc\n    shl rdx, 32\n    or rax, rdx\n    ret\nglobal dg_arch_cpuid\ndg_arch_cpuid:\n    push rbx\n    push r12\n    mov r12, rdx\n    mov eax, edi\n    mov ecx, esi\n    cpuid\n    mov [r12 + 0], eax\n    mov [r12 + 4], ebx\n    mov [r12 + 8], ecx\n    mov [r12 + 12], edx\n    pop r12\n    pop rbx\n    ret\nglobal dg_arch_lfence\ndg_arch_lfence:\n    lfence\n    ret\nglobal dg_arch_sfence\ndg_arch_sfence:\n    sfence\n    ret\nglobal dg_arch_mfence\ndg_arch_mfence:\n    mfence\n    ret\n%ifidn __OUTPUT_FORMAT__,elf64\nsection .note.GNU-stack noalloc noexec nowrite progbits\n%endif"


def _run(label, arch_text):
    with tempfile.TemporaryDirectory() as temporary:
        arch = Path(temporary) / "bad_arch.asm"
        arch.write_text(arch_text, encoding="utf-8")
        return runner.run_negative_control(arch, label)


class StdArchQemuNegativeTests(unittest.TestCase):
    def _require_tools(self):
        try:
            qemu = find_tool("qemu-system-x86_64", "QEMU")
            find_tool("nasm", "NASM")
            find_tool("lld-link", "LLD_LINK")
            find_firmware(qemu)
        except ToolError:
            self.skipTest("negative control requires QEMU, NASM, LLD-LINK and OVMF")

    def _assert_rejected(self, result, stage):
        self.assertFalse(result["passed"])
        self.assertEqual(35, result["returncode"])
        self.assertTrue(result["command"])
        self.assertFalse(result["timed_out"])
        self.assertTrue(any(f"guest reported failure/panic: DONGOS_STD_ARCH_{stage}" in e for e in result["errors"]))
        self.assertFalse(any("PANIC" in e for e in result["errors"]))
        lines = result["serial_lines"]
        self.assertTrue(lines)
        self.assertEqual("DONGOS_STD_ARCH_START", lines[0])
        self.assertEqual(f"DONGOS_STD_ARCH_{stage}", lines[-1])
        self.assertEqual(1, sum(1 for ln in lines if ln.startswith("DONGOS_STD_ARCH_FAIL")))
        self.assertEqual(len(lines), len(set(lines)))
        allowed = {"DONGOS_STD_ARCH_START", "DONGOS_STD_ARCH_IO_PASS", "DONGOS_STD_ARCH_CR3_PASS",
                   "DONGOS_STD_ARCH_MSR_PASS", "DONGOS_STD_ARCH_ABI_PASS", f"DONGOS_STD_ARCH_{stage}"}
        for line in lines:
            self.assertIn(line, allowed)

    def test_bad_cr3_wrapper_rejected(self):
        self._require_tools()
        self._assert_rejected(_run("bad-cr3", BAD_CR3_ARCH), "FAIL:ABI")

    def test_bad_msr_wrapper_rejected(self):
        self._require_tools()
        self._assert_rejected(_run("bad-msr", BAD_MSR_ARCH), "FAIL:ABI")

    def test_bad_msr_high_bits_rejected(self):
        self._require_tools()
        self._assert_rejected(_run("bad-msr-high", BAD_MSR_HIGH_ARCH), "FAIL:MSR")

    def test_bad_abi_wrapper_rejected(self):
        self._require_tools()
        self._assert_rejected(_run("bad-abi", BAD_ABI_ARCH), "FAIL:ABI")

    def test_bad_port_wrapper_rejected(self):
        self._require_tools()
        self._assert_rejected(_run("bad-port", BAD_PORT_ARCH), "FAIL:IO")

    def test_bad_ret8_wrapper_rejected(self):
        self._require_tools()
        self._assert_rejected(_run("bad-ret8", BAD_RET8_ARCH), "FAIL:IO")

    def test_correct_value_ret8_wrapper_rejected(self):
        self._require_tools()
        self._assert_rejected(_run("bad-cr3-ret8", BAD_CR3_RET8_ARCH), "FAIL:ABI")

    def test_correct_write_cr3_ret8_wrapper_rejected(self):
        self._require_tools()
        self._assert_rejected(_run("bad-wcr3-ret8", BAD_WCR3_RET8_ARCH), "FAIL:ABI")

    def test_normal_wrapper_passes(self):
        self._require_tools()
        result = runner.run_negative_control(ROOT / "lang/std/arch/x86_64.asm", "normal")
        self.assertTrue(result["passed"])
        self.assertEqual(33, result["returncode"])
        self.assertTrue(result["command"])


if __name__ == "__main__":
    unittest.main()
