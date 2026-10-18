; BSP user transition ABI; every field is one u64. See docs/user-context.md.
%ifndef DONGOS_USER_CONTEXT_INC
%define DONGOS_USER_CONTEXT_INC
USER_TOP equ 0x0000008000000000
USER_MIN equ 0x10000
USER_CODE_SELECTOR equ 0x33
USER_DATA_SELECTOR equ 0x2b
USER_RFLAGS_ALLOWED equ 0x0ad7
; Trusted hardware captures may interrupt a backward REP copy. IRET restores
; DF/RF exactly; untrusted initial/SYSCALL frames retain the narrower mask.
USER_INTERRUPT_RFLAGS_ALLOWED equ 0x10ed7
USER_FMASK equ 0x77700
USER_ERR_FRAME equ 0x04050001
USER_ERR_BUSY equ 0x04050002
USER_ERR_ARGUMENT equ 0x04050003
struc UserFrame
 .r15: resq 1
 .r14: resq 1
 .r13: resq 1
 .r12: resq 1
 .r11: resq 1
 .r10: resq 1
 .r9: resq 1
 .r8: resq 1
 .rdi: resq 1
 .rsi: resq 1
 .rbp: resq 1
 .rdx: resq 1
 .rcx: resq 1
 .rbx: resq 1
 .rax: resq 1
 .rip: resq 1
 .rflags: resq 1
 .rsp: resq 1
 .cr3: resq 1
 .fs_base: resq 1
 .gs_base: resq 1
 .status: resq 1
 .syscalls: resq 1
 .exit_code: resq 1
 .reserved: resq 1
endstruc
; Shared by production SYSCALL capture and the safe native ABI exercise.
%macro USER_SAVE_GPRS 1
    mov [%1 + UserFrame.r15], r15
    mov [%1 + UserFrame.r14], r14
    mov [%1 + UserFrame.r13], r13
    mov [%1 + UserFrame.r12], r12
    mov [%1 + UserFrame.r11], r11
    mov [%1 + UserFrame.r10], r10
    mov [%1 + UserFrame.r9], r9
    mov [%1 + UserFrame.r8], r8
    mov [%1 + UserFrame.rdi], rdi
    mov [%1 + UserFrame.rsi], rsi
    mov [%1 + UserFrame.rbp], rbp
    mov [%1 + UserFrame.rdx], rdx
    mov [%1 + UserFrame.rcx], rcx
    mov [%1 + UserFrame.rbx], rbx
    mov [%1 + UserFrame.rax], rax
%endmacro
%macro USER_LOAD_GPRS 1
    mov r15, [%1 + UserFrame.r15]
    mov r14, [%1 + UserFrame.r14]
    mov r13, [%1 + UserFrame.r13]
    mov r12, [%1 + UserFrame.r12]
    mov r11, [%1 + UserFrame.r11]
    mov r10, [%1 + UserFrame.r10]
    mov r9, [%1 + UserFrame.r9]
    mov r8, [%1 + UserFrame.r8]
    mov rsi, [%1 + UserFrame.rsi]
    mov rbp, [%1 + UserFrame.rbp]
    mov rdx, [%1 + UserFrame.rdx]
    mov rcx, [%1 + UserFrame.rcx]
    mov rbx, [%1 + UserFrame.rbx]
    mov rax, [%1 + UserFrame.rax]
    mov rdi, [%1 + UserFrame.rdi]
%endmacro
struc UserCpu
 .kernel_stack: resq 1
 .user_stack: resq 1
 .continuation: resq 1
 .root_frame: resq 1
 .original_cr3: resq 1
 .syscalls: resq 1
 .busy: resq 1
 .result: resq 1
endstruc
%endif
