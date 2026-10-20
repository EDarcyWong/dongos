; Position-independent CPL3 init/IPC client. Every roundtrip crosses two
; independent address spaces; fixed tokens are explicit startup capabilities.
bits 64
default rel
global _start
section .text
_start:
    mov r12, rdx
    mov r14, rsi
    mov r13, r8
    mov rbx, r9
    mov ax, cs
    movzx edi, ax
    mov eax, 1
    syscall
    cmp rax, 1
    jne failed
    mov rdi, r13
    xor esi, esi
    mov edx, 4096
    mov r10d, 3
    mov eax, 0x40
    syscall
    cmp rax, 0x50000000
    jne failed
    mov r13, rax
    mov rdi, rbx
    mov esi, 5
    mov eax, 0x30
    syscall
    test rax, rax
    jnz failed
    mov rdi, rbx
    mov esi, 1
    mov eax, 0x31
    syscall
    cmp rax, 1
    jne failed
    ; Rights escalation must be rejected by the real process handle table.
    mov rdi, r12
    mov esi, 64
    mov eax, 0x11
    syscall
    cmp rax, 0x04010003
    jne failed
    mov rdi, r12
    mov esi, 32
    mov eax, 0x11
    syscall
    cmp rax, 0x104
    jne failed
    mov rbp, rax
    mov rdi, rax
    mov eax, 0x10
    syscall
    test rax, rax
    jnz failed
    mov rdi, rbp
    lea rsi, [rel request]
    lea rdx, [rel response]
    mov eax, 0x22
    syscall
    cmp rax, 0x04010002
    jne failed
    ; A high/non-user input, executable output, and cross-guard input all
    ; reject before mutating the endpoint or touching user bytes.
    mov rdi, r12
    mov rsi, 0x8000000000
    lea rdx, [rel response]
    mov eax, 0x22
    syscall
    cmp rax, 0x04060003
    jne failed
    mov rdi, r12
    lea rsi, [rel request]
    lea rdx, [rel _start]
    mov eax, 0x22
    syscall
    cmp rax, 0x04060004
    jne failed
    mov rdi, r12
    lea rsi, [rsp - 24]
    lea rdx, [rel response]
    mov eax, 0x22
    syscall
    cmp rax, 0x02030002
    jne failed
    xor r15d, r15d
.loop:
    mov [rel request], r15
    mov rdi, r12
    lea rsi, [rel request]
    lea rdx, [rel response]
    mov eax, 0x22
    syscall
    test rax, rax
    jnz failed
    lea rax, [r15 + 1]
    cmp [rel response], rax
    jne failed
    cmp [r13], rax
    jne failed
    lea rdi, [rel response + 8]
    mov ecx, 7
    mov rax, 0x1122334455667788
.tail:
    cmp [rdi], rax
    jne failed
    add rdi, 8
    dec ecx
    jnz .tail
    inc r15
    cmp r15, r14
    jb .loop
    mov rdi, r15
    mov ax, cs
    movzx esi, ax
    mov eax, 0xff
    syscall
failed:
    mov edi, 1
    mov eax, 0xfe
    syscall
    ud2
section .data
align 8
request: dq 0
    times 7 dq 0x1122334455667788
section .bss
align 8, resb 1
response: resq 8
section .note.GNU-stack noalloc noexec nowrite progbits
