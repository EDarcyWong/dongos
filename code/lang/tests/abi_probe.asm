; An independent handwritten caller checks generated SysV callees, including
; all six parameter registers, callee-saved registers and the direction flag.
bits 64
default rel
section .text
global abi_probe
global __dong_panic
extern dg_six
extern panic_record
extern panic_entry_alignment

abi_probe:
    push rbx
    push rbp
    push r12
    push r13
    push r14
    push r15
    sub rsp, 8
    mov ebx, 17
    mov ebp, 23
    mov r12d, 31
    mov r13d, 47
    mov r14d, 61
    mov r15d, 79
    mov edi, 1
    mov esi, 2
    mov edx, 3
    mov ecx, 4
    mov r8d, 5
    mov r9d, 6
    call dg_six
    cmp rax, 654321
    jne .failed
    cmp rbx, 17
    jne .failed
    cmp rbp, 23
    jne .failed
    cmp r12, 31
    jne .failed
    cmp r13, 47
    jne .failed
    cmp r14, 61
    jne .failed
    cmp r15, 79
    jne .failed
    pushfq
    pop r10
    test r10, 0x400
    jnz .failed
    mov eax, 1
    jmp .return
.failed:
    xor eax, eax
.return:
    add rsp, 8
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbp
    pop rbx
    ret

; Capture the entry alignment before a C prologue can change RSP. The tail jump
; preserves the SysV panic arguments and caller's return-address placement.
__dong_panic:
    mov rax, rsp
    and eax, 15
    mov dword [rel panic_entry_alignment], eax
    jmp panic_record

%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
