; Independent canonical scalar-return checks and panic bridge.
bits 64
default rel
section .text
global __dong_panic
global globals_abi_probe
extern globals_panic_record
extern globals_u8
extern globals_i8
extern globals_u16
extern globals_i16
extern globals_u32
extern globals_i32
extern globals_u64
extern globals_i64
extern globals_bool

__dong_panic:
    jmp globals_panic_record

globals_abi_probe:
    push rbp
    mov rbp, rsp
    call globals_u8
    cmp rax, 255
    jne .failed
    call globals_i8
    cmp rax, -128
    jne .failed
    call globals_u16
    cmp rax, 65535
    jne .failed
    call globals_i16
    cmp rax, -32768
    jne .failed
    call globals_u32
    mov r10d, 0xffffffff
    cmp rax, r10
    jne .failed
    call globals_i32
    cmp rax, -2147483648
    jne .failed
    call globals_u64
    cmp rax, -1
    jne .failed
    call globals_i64
    mov r10, 0x8000000000000000
    cmp rax, r10
    jne .failed
    call globals_bool
    cmp rax, 1
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
