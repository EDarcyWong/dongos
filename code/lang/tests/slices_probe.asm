; Independently written ABI observer, no compiler-generated layout constants.
bits 64
default rel
section .text
global __dong_panic
global slices_asm_sysv
global slices_asm_win
global slices_abi_probe
extern slices_panic_record
extern slices_panic_alignment
extern dg_slice_return
extern dg_slice_position5

__dong_panic:
    mov rax, rsp
    and eax, 15
    mov dword [rel slices_panic_alignment], eax
    jmp slices_panic_record

slices_asm_sysv:
    mov rax, rsp
    and eax, 15
    cmp eax, 8
    jne .failed
    cmp rdi, 1
    jne .failed
    cmp rsi, 2
    jne .failed
    cmp rdx, 3
    jne .failed
    cmp rcx, 4
    jne .failed
    cmp r8, 5
    jne .failed
    cmp r9, 6
    jne .failed
    cmp qword [rsp+8], 7
    jne .failed
    cmp qword [rsp+16], 8
    jne .failed
    mov eax, 204
    ret
.failed:
    xor eax, eax
    ret

slices_asm_win:
    mov rax, rsp
    and eax, 15
    cmp eax, 8
    jne .failed
    cmp rcx, 1
    jne .failed
    cmp rdx, 2
    jne .failed
    cmp r8, 3
    jne .failed
    cmp r9, 4
    jne .failed
    cmp qword [rsp+40], 5
    jne .failed
    cmp qword [rsp+48], 6
    jne .failed
    cmp qword [rsp+56], 7
    jne .failed
    cmp qword [rsp+64], 8
    jne .failed
    ; Home space belongs to this callee and may be overwritten completely.
    mov qword [rsp+8], -1
    mov qword [rsp+16], -1
    mov qword [rsp+24], -1
    mov qword [rsp+32], -1
    mov eax, 204
    ret
.failed:
    xor eax, eax
    ret

slices_abi_probe:
    push rbp
    mov rbp, rsp
    sub rsp, 16
    lea rdi, [rel slices_abi_values]
    mov esi, 4
    call dg_slice_return
    lea r10, [rel slices_abi_values+8]
    cmp rax, r10
    jne .failed
    cmp rdx, 3
    jne .failed
    lea rax, [rel slices_abi_values]
    mov qword [rsp], rax
    mov qword [rsp+8], 4
    mov edi, 1
    mov esi, 2
    mov edx, 3
    mov ecx, 4
    mov r8d, 5
    mov r9d, 9
    call dg_slice_position5
    cmp rax, 9426
    jne .failed
    pushfq
    pop rax
    test eax, 0x400
    jnz .failed
    mov eax, 1
    jmp .done
.failed:
    xor eax, eax
.done:
    mov rsp, rbp
    pop rbp
    ret

section .rodata
slices_abi_values: dq 11,22,33,44
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
