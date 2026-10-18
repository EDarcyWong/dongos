; arch.x86_64 — NASM implementations for lang/std/arch/x86_64.dg.
; All functions follow the SysV AMD64 convention regardless of output format:
;   integer/pointer args in rdi rsi rdx rcx r8 r9, scalar return in rax (or al).
; They are declared extern "sysv64" in Dong and called the same way from C.
; Clobbers are limited to caller-saved registers plus the stated outputs;
; cpuid saves and restores RBX (and uses R12 for the out pointer).

bits 64
default rel

section .text

; u8 in8(u16 port)  [rdi=port -> al]
; Privileged (IN). Clobbers: rax (result), rdx (port) are caller-saved.
global dg_arch_in8
dg_arch_in8:
    mov dx, di
    in al, dx
    ret

; void out8(u16 port, u8 value)  [rdi=port, rsi=value]
; Privileged (OUT). Clobbers: rax, rdx (caller-saved).
global dg_arch_out8
dg_arch_out8:
    mov dx, di
    mov al, sil
    out dx, al
    ret

; u64 read_cr3(void)  [-> rax]
; Privileged (MOV from CR3). Clobbers: rax.
global dg_arch_read_cr3
dg_arch_read_cr3:
    mov rax, cr3
    ret

; void write_cr3(u64 value)  [rdi=value]
; Privileged (MOV to CR3). Clobbers: none beyond the instruction's effect.
global dg_arch_write_cr3
dg_arch_write_cr3:
    mov cr3, rdi
    ret

; u64 read_msr(u32 msr)  [rdi=msr -> rax = EDX:EAX combined]
; Privileged (RDMSR). Clobbers: rax, rdx, rcx (caller-saved).
global dg_arch_read_msr
dg_arch_read_msr:
    mov ecx, edi
    rdmsr
    shl rdx, 32
    or rax, rdx
    ret

; void write_msr(u32 msr, u64 value)  [rdi=msr, rsi=value]
; Privileged (WRMSR). Clobbers: rax, rdx, rcx (caller-saved).
global dg_arch_write_msr
dg_arch_write_msr:
    mov ecx, edi
    mov eax, esi
    mov rdx, rsi
    shr rdx, 32
    wrmsr
    ret

; u64 read_tsc(void)  [-> rax = EDX:EAX combined]
; RDTSC is not a serializing barrier. Clobbers: rax, rdx (caller-saved).
global dg_arch_read_tsc
dg_arch_read_tsc:
    rdtsc
    shl rdx, 32
    or rax, rdx
    ret

; void cpuid(u32 leaf, u32 subleaf, *CpuId out)  [rdi=leaf, rsi=subleaf, rdx=out]
; Writes eax/ebx/ecx/edx to out+0/4/8/12. Preserves RBX and R12 (callee-saved).
; Clobbers: rax, rcx, rdx (caller-saved).
global dg_arch_cpuid
dg_arch_cpuid:
    push rbx
    push r12
    mov r12, rdx
    mov eax, edi
    mov ecx, esi
    cpuid
    mov [r12 + 0], eax
    mov [r12 + 4], ebx
    mov [r12 + 8], ecx
    mov [r12 + 12], edx
    pop r12
    pop rbx
    ret

; void lfence(void) / sfence(void) / mfence(void)
; Ordering fences. Clobbers: none.
global dg_arch_lfence
dg_arch_lfence:
    lfence
    ret
global dg_arch_sfence
dg_arch_sfence:
    sfence
    ret
global dg_arch_mfence
dg_arch_mfence:
    mfence
    ret

%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
