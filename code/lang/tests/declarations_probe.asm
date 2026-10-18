; Canonical integer return values checked independently of a C narrow return.
bits 64
default rel
section .text
global __dong_panic
global declarations_abi_probe
extern declarations_panic_record
extern declarations_panic_alignment
extern declarations_u8
extern declarations_i8
extern declarations_u16
extern declarations_i16
extern declarations_u32
extern declarations_i32
extern declarations_u64
extern declarations_i64

__dong_panic:
    mov rax, rsp
    and eax, 15
    mov dword [rel declarations_panic_alignment], eax
    jmp declarations_panic_record

declarations_abi_probe:
    push rbp
    mov rbp, rsp
    call declarations_u8
    cmp rax, 255
    jne .failed
    call declarations_i8
    cmp rax, -128
    jne .failed
    call declarations_u16
    cmp rax, 65535
    jne .failed
    call declarations_i16
    cmp rax, -32768
    jne .failed
    call declarations_u32
    mov r10d, 0xffffffff
    cmp rax, r10
    jne .failed
    call declarations_i32
    cmp rax, -2147483648
    jne .failed
    call declarations_u64
    cmp rax, -1
    jne .failed
    call declarations_i64
    mov r10, 0x8000000000000000
    cmp rax, r10
    jne .failed
    mov eax, 1
    jmp .done
.failed:
    xor eax, eax
.done:
    mov rsp, rbp
    pop rbp
    ret

%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
