; Safe CPL3 host exercise of the exact production save/restore helpers.
bits 64
default rel
%include "sched.inc"
extern sched_xstate_save
extern sched_xstate_restore
extern sched_report
global sched_probe_xstate
section .text
sched_probe_xstate:
    push rbp
    mov rbp, rsp
    push rbx
    push r12
    push r13
    push r14
    mov r12, rdi
    cmp edi, 2
    jne .available
    mov eax, 1
    cpuid
    and ecx, (1 << 26) | (1 << 27)
    cmp ecx, (1 << 26) | (1 << 27)
    jne .unavailable
    xor ecx, ecx
    xgetbv
    and eax, 3
    cmp eax, 3
    jne .unavailable
.available:
    mov [rel sched_report + SchedReport.xstate_mode], r12
    lea rdi, [rel probe_initial]
    call sched_xstate_save
    mov r13d, 1
    call load_pattern
    lea rdi, [rel probe_a]
    call sched_xstate_save
    mov r13d, 2
    call load_pattern
    lea rdi, [rel probe_b]
    call sched_xstate_save
    mov r14d, 128
.alternate:
    lea rdi, [rel probe_a]
    call sched_xstate_restore
    mov r13d, 1
    call check_pattern
    test eax, eax
    jnz .failed
    lea rdi, [rel probe_b]
    call sched_xstate_restore
    mov r13d, 2
    call check_pattern
    test eax, eax
    jnz .failed
    dec r14d
    jnz .alternate
    xor r12d, r12d
    jmp .restore
.failed:
    mov r12d, 1
.restore:
    lea rdi, [rel probe_initial]
    call sched_xstate_restore
    mov rax, r12
    jmp .return
.unavailable:
    mov eax, 2
.return:
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret
load_pattern:
    fninit
    lea rdx, [rel pattern_a]
    lea rcx, [rel cw_a]
    lea rsi, [rel mxcsr_a]
    cmp r13d, 1
    je .a
    lea rdx, [rel pattern_b]
    lea rcx, [rel cw_b]
    lea rsi, [rel mxcsr_b]
.a:
    fldcw [rcx]
    ldmxcsr [rsi]
    cmp r13d, 1
    jne .zero
    fld1
    jmp .xmm
.zero:
    fldz
.xmm:
%assign i 0
%rep 16
    movdqu xmm %+ i, [rdx]
%assign i i+1
%endrep
    ret
check_pattern:
    lea rdx, [rel pattern_a]
    lea rcx, [rel cw_a]
    lea rsi, [rel mxcsr_a]
    cmp r13d, 1
    je .a
    lea rdx, [rel pattern_b]
    lea rcx, [rel cw_b]
    lea rsi, [rel mxcsr_b]
.a:
%assign i 0
%rep 16
    movdqu [rel scratch + i * 16], xmm %+ i
%assign i i+1
%endrep
%assign i 0
%rep 32
    mov rax, [rdx + (i % 2) * 8]
    cmp [rel scratch + i * 8], rax
    jne .bad
%assign i i+1
%endrep
    stmxcsr [rel scratch + 256]
    mov eax, [rsi]
    cmp [rel scratch + 256], eax
    jne .bad
    fnstcw [rel scratch + 260]
    mov ax, [rcx]
    cmp [rel scratch + 260], ax
    jne .bad
    fst qword [rel scratch + 264]
    xor eax, eax
    cmp r13d, 2
    je .value
    mov rax, 0x3ff0000000000000
.value:
    cmp [rel scratch + 264], rax
    jne .bad
    xor eax, eax
    ret
.bad:
    mov eax, 1
    ret
section .rodata
align 16
pattern_a: dq 0x1122334455667788,0x8877665544332211
pattern_b: dq 0x55aa33cc77ee9900,0x0099ee77cc33aa55
cw_a: dw 0x037f
cw_b: dw 0x077f
mxcsr_a: dd 0x1f80
mxcsr_b: dd 0x3f80
section .bss
alignb 64
probe_initial: resb 1024
probe_a: resb 1024
probe_b: resb 1024
scratch: resb 272
