; Fatal page-permission probes, linked only into isolated activation test builds.
bits 64
default rel
%ifndef MEMORY_ACTIVATION_TEST_CASE
%error "MEMORY_ACTIVATION_TEST_CASE must select an isolated page fault"
%endif

global memory_activation_test_inject
global memory_activation_test_expected_rip
global memory_activation_test_mid_return
global memory_activation_test_inject_return
global memory_activation_test_ro_target
global memory_activation_test_nx_target
extern cpu_exception_guard_low

section .text
; SysV, no arguments, never returns. Two materialized callers let the host
; independently verify the permanent fixed stack's trusted frame chain.
memory_activation_test_inject:
    push rbp
    mov rbp, rsp
    call memory_activation_test_mid
memory_activation_test_inject_return:
    ud2

memory_activation_test_mid:
    push rbp
    mov rbp, rsp
    call memory_activation_test_leaf
memory_activation_test_mid_return:
    ud2

memory_activation_test_leaf:
    push rbp
    mov rbp, rsp
    mov rax, 0x1111111111111111
    mov rbx, 0x2222222222222222
    mov rcx, 0x3333333333333333
    mov rdx, 0x4444444444444444
    mov rsi, 0x5555555555555555
    mov rdi, 0x6666666666666666
    mov r8,  0x8888888888888888
    mov r9,  0x9999999999999999
    mov r10, 0xaaaaaaaaaaaaaaaa
    mov r11, 0xbbbbbbbbbbbbbbbb
    mov r12, 0xcccccccccccccccc
    mov r13, 0xdddddddddddddddd
    mov r14, 0xeeeeeeeeeeeeeeee
    mov r15, 0xffffffffffffffff
    ; The exception entry must clear DF while preserving it in saved RFLAGS.
    std
%if MEMORY_ACTIVATION_TEST_CASE = 1
    mov eax, 0
memory_activation_test_expected_rip:
    mov rbx, [rax]
%elif MEMORY_ACTIVATION_TEST_CASE = 2
    lea rax, [rel memory_activation_test_ro_target]
memory_activation_test_expected_rip:
    mov byte [rax], 0x5a
%elif MEMORY_ACTIVATION_TEST_CASE = 3
    lea rax, [rel memory_activation_test_nx_target]
    jmp rax
%elif MEMORY_ACTIVATION_TEST_CASE = 4
    ; The faulting PUSH really crosses the lower ordinary stack guard. Its
    ; valid RBP chain remains on the fixed stack for the IST-based handler.
    mov rsp, 0xffff900000001000
memory_activation_test_expected_rip:
    push rax
%elif MEMORY_ACTIVATION_TEST_CASE = 5
    lea rax, [rel cpu_exception_guard_low]
memory_activation_test_expected_rip:
    mov rbx, [rax]
%else
%error "Unknown MEMORY_ACTIVATION_TEST_CASE"
%endif
    ; An absent fault must time out, never reach a normal completion marker.
    cli
.halt:
    hlt
    jmp .halt

section .rodata
memory_activation_test_ro_target: db 0xa5

section .data
%if MEMORY_ACTIVATION_TEST_CASE = 3
memory_activation_test_expected_rip:
%endif
memory_activation_test_nx_target: db 0xc3

section .note.GNU-stack noalloc noexec nowrite progbits
