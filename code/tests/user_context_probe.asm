bits 64
default rel
%include "user_context.inc"
global user_probe_capture
global user_probe_offsets
section .text
; Safe SysV capture using exactly the production integer save/load macros.
user_probe_capture:
    push rbp
    push rbx
    push r12
    push r13
    push r14
    push r15
    sub rsp, 224
    mov [rsp + 208], rsi
    USER_LOAD_GPRS rdi
    USER_SAVE_GPRS rsp
    mov rdi, [rsp + 208]
    mov rsi, rsp
    mov ecx, 15
    cld
    rep movsq
    add rsp, 224
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret
; Copy NASM's actual layout as data; C compares its own offsetof for all fields.
user_probe_offsets:
%assign i 0
%macro FIELD 1
    mov qword [rdi + i * 8], UserFrame.%1
%assign i i+1
%endmacro
    FIELD r15
    FIELD r14
    FIELD r13
    FIELD r12
    FIELD r11
    FIELD r10
    FIELD r9
    FIELD r8
    FIELD rdi
    FIELD rsi
    FIELD rbp
    FIELD rdx
    FIELD rcx
    FIELD rbx
    FIELD rax
    FIELD rip
    FIELD rflags
    FIELD rsp
    FIELD cr3
    FIELD fs_base
    FIELD gs_base
    FIELD status
    FIELD syscalls
    FIELD exit_code
    FIELD reserved
    mov qword [rdi + 25 * 8], UserFrame_size
    mov qword [rdi + 26 * 8], UserCpu_size
    ret
