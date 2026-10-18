; Independent ABI observer. Every generated callee receives a legal SysV stack;
; the 64 possible 16-byte-aligned residues modulo 1024 are tested explicitly.
bits 64
default rel
section .text
global alignment_abi_probe
global alignment_temp_frame
global alignment_asm_sysv
global alignment_asm_win
global __dong_panic
extern dg_align1024
extern dg_align_stack
extern dg_align_slice_stack
extern dg_align_return
extern dg_align_calls
extern alignment_panic_record
extern alignment_panic_entry
extern alignment_panic_df

alignment_temp_frame:
    mov rax, rsp
    and eax, 15
    cmp eax, 8
    jne .failed
    lea r10, [rdi-1]
    test r12, r10
    jnz .failed
    ; The fixture has no locals and exactly one aggregate temporary. Before
    ; its field initializer runs, that full object's storage has been zeroed.
    mov r11, r12
    sub r11, rdi
    test r11, r10
    jnz .failed
    mov rcx, rdi
    shr rcx, 3
.zeroed:
    cmp qword [r11], 0
    jne .failed
    add r11, 8
    dec rcx
    jnz .zeroed
    pushfq
    pop r10
    test r10d, 0x400
    jnz .failed
    mov rax, rdi
    ret
.failed:
    xor eax, eax
    ret

alignment_asm_sysv:
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

alignment_asm_win:
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
    mov qword [rsp+8], -1
    mov qword [rsp+16], -1
    mov qword [rsp+24], -1
    mov qword [rsp+32], -1
    mov eax, 204
    ret
.failed:
    xor eax, eax
    ret

%macro VERIFY_FRAME 0
    mov r10, r13
    shl r10, 4
    add r10, r14
    cmp rsp, r10
    jne .failed
    cmp r12, 0x22334455
    jne .failed
    cmp rbp, 0x11223344
    jne .failed
    cmp rbx, 0x33445566
    jne .failed
    pushfq
    pop r10
    test r10d, 0x400
    jnz .failed
%endmacro

alignment_abi_probe:
    push rbp
    push rbx
    push r12
    push r13
    push r14
    push r15
    sub rsp, 8
    mov r15, rsp
    sub rsp, 2048
    and rsp, -1024
    mov r14, rsp
    xor r13d, r13d
    mov ebp, 0x11223344
    mov r12d, 0x22334455
    mov ebx, 0x33445566
.residue:
    mov r10, r13
    shl r10, 4
    lea rsp, [r14+r10]
    call dg_align1024
    cmp rax, 100044
    jne .failed
    VERIFY_FRAME
    mov edi, 1
    mov esi, 2
    mov edx, 3
    mov ecx, 4
    mov r8d, 5
    mov r9d, 6
    mov qword [rsp], 7
    mov qword [rsp+8], 8
    call dg_align_stack
    cmp rax, 100221
    jne .failed
    VERIFY_FRAME
    mov edi, 1
    mov esi, 2
    mov edx, 3
    mov ecx, 4
    mov r8d, 5
    mov r9d, 9
    lea rax, [rel alignment_values]
    mov qword [rsp], rax
    mov qword [rsp+8], 4
    call dg_align_slice_stack
    cmp rax, 109490
    jne .failed
    VERIFY_FRAME
    lea rdi, [rel alignment_values]
    mov esi, 4
    mov edx, 1
    call dg_align_return
    lea r10, [rel alignment_values+8]
    cmp rax, r10
    jne .failed
    cmp rdx, 3
    jne .failed
    VERIFY_FRAME
    lea rdi, [rel alignment_values]
    mov esi, 4
    xor edx, edx
    call dg_align_return
    lea r10, [rel alignment_values]
    cmp rax, r10
    jne .failed
    cmp rdx, 2
    jne .failed
    VERIFY_FRAME
    call dg_align_calls
    cmp rax, 200655
    jne .failed
    VERIFY_FRAME
    inc r13
    cmp r13, 64
    jb .residue
    mov eax, 1
    jmp .done
.failed:
    xor eax, eax
.done:
    cld
    mov rsp, r15
    add rsp, 8
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret

__dong_panic:
    mov rax, rsp
    and eax, 15
    mov dword [rel alignment_panic_entry], eax
    pushfq
    pop rax
    and eax, 0x400
    mov dword [rel alignment_panic_df], eax
    jmp alignment_panic_record

section .rodata
alignment_values: dq 11,22,33,44
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
