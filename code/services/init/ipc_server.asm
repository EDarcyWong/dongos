bits 64
default rel
global _start
section .text
_start:
    mov r12, rdx
    mov r13, r8
    mov ax, cs
    movzx edi, ax
    mov eax, 1
    syscall
    cmp rax, 2
    jne server_failed
    mov rdi, r13
    xor esi, esi
    mov edx, 4096
    mov r10d, 3
    mov eax, 0x40
    syscall
    cmp rax, 0x50000000
    jne server_failed
    mov r13, rax
    mov rdi, r12
    lea rsi, [rel message]
    mov eax, 0x23
    syscall
    test rax, rax
    jnz server_failed
    mov r15, rdx
.reply:
    inc qword [rel message]
    inc qword [r13]
    mov rdi, r12
    mov rsi, r15
    lea rdx, [rel message]
    lea r10, [rel message]
    mov eax, 0x26
    syscall
    test rax, rax
    jnz server_failed
    mov r15, rdx
    jmp .reply
server_failed:
    mov edi, 2
    mov eax, 0xfe
    syscall
    ud2
section .data
align 8
server_data_anchor: dq 0
section .bss
align 8, resb 1
message: resq 8
section .note.GNU-stack noalloc noexec nowrite progbits
