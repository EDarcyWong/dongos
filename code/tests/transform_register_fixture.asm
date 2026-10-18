bits 64
default rel
extern svc_transform_rows
global transform_register_probe
section .text
transform_register_probe:
    push rbx
    push rbp
    push r12
    push r13
    push r14
    push r15
    sub rsp,8
    mov rbx,0x123456789abcdef0
    mov rbp,0x23456789abcdef01
    mov r12,0x3456789abcdef012
    mov r13,0x456789abcdef0123
    mov r14,0x56789abcdef01234
    mov r15,0x6789abcdef012345
    call svc_transform_rows
    mov rdx,0x123456789abcdef0
    cmp rbx,rdx
    jne .bad
    mov rdx,0x23456789abcdef01
    cmp rbp,rdx
    jne .bad
    mov rdx,0x3456789abcdef012
    cmp r12,rdx
    jne .bad
    mov rdx,0x456789abcdef0123
    cmp r13,rdx
    jne .bad
    mov rdx,0x56789abcdef01234
    cmp r14,rdx
    jne .bad
    mov rdx,0x6789abcdef012345
    cmp r15,rdx
    jne .bad
    xor eax,eax
    jmp .done
.bad:
    mov eax,1
.done:
    add rsp,8
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbp
    pop rbx
    ret
section .note.GNU-stack noalloc noexec nowrite progbits
