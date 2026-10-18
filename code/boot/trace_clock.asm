; Ordered real CPU/TSC sample, SysV RDI=*{TSC, xAPIC ID, invariant flag}.
; No allocation, port/MMIO, firmware or user-controlled timestamp.
bits 64
default rel
section .text
global boot_trace_sample,boot_trace_cpuid15
boot_trace_sample:
    push rbx
    lfence
    rdtsc
    lfence
    shl rdx,32
    or rax,rdx
    mov [rdi],rax
    mov eax,1
    xor ecx,ecx
    cpuid
    shr ebx,24
    mov [rdi+8],rbx
    xor r8d,r8d
    mov eax,0x80000000
    cpuid
    cmp eax,0x80000007
    jb .store
    mov eax,0x80000007
    xor ecx,ecx
    cpuid
    shr edx,8
    and edx,1
    mov r8d,edx
.store:
    mov [rdi+16],r8
    pop rbx
    ret
; SysV RDI=*three u64. Preserve raw denominator/numerator/crystal for oracle.
boot_trace_cpuid15:
    push rbx
    mov qword [rdi],0
    mov qword [rdi+8],0
    mov qword [rdi+16],0
    xor eax,eax
    cpuid
    cmp eax,0x15
    jb .done
    mov eax,0x15
    xor ecx,ecx
    cpuid
    mov [rdi],rax
    mov [rdi+8],rbx
    mov [rdi+16],rcx
.done:
    pop rbx
    ret
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
