; Independent SysV observer. Also verifies that aggregate memmove clears DF.
bits 64
default rel
section .text
global __dong_panic
global memory_df_probe
global memory_narrow_probe
extern panic_record
extern panic_entry_alignment
extern dg_overlap
extern dg_i8_widen
extern dg_u16_widen

__dong_panic:
    mov rax, rsp
    and eax, 15
    mov dword [rel panic_entry_alignment], eax
    jmp panic_record

memory_df_probe:
    push rbp
    mov rbp, rsp
    sub rsp, 16
    mov rax, 0x0504030201
    mov qword [rbp-8], rax
    lea rdi, [rbp-8]
    call dg_overlap
    pushfq
    pop rax
    and eax, 0x400
    xor eax, 0x400
    shr eax, 10
    mov rsp, rbp
    pop rbp
    ret

memory_narrow_probe:
    push rbp
    mov rbp, rsp
    mov rdi, 0x1122334455667780
    call dg_i8_widen
    cmp rax, -128
    jne .failed
    mov rdi, 0xfedcba987654ffff
    call dg_u16_widen
    cmp rax, 65535
    jne .failed
    mov eax, 1
    jmp .return
.failed:
    xor eax, eax
.return:
    pop rbp
    ret

%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
