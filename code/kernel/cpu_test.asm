; Deliberate P2 exception injection, linked only into an isolated P1 test build.
bits 64
default rel
%include "cpu.inc"
%ifndef CPU_TEST_CASE
%error "CPU_TEST_CASE must select an isolated fault test"
%endif

global cpu_test_inject
global cpu_test_expected_rip
global cpu_test_mid_return
global cpu_test_inject_return
extern cpu_idt

section .text
cpu_test_inject:
    push rbp
    mov rbp, rsp
    call cpu_test_mid
cpu_test_inject_return:
    ud2

cpu_test_mid:
    push rbp
    mov rbp, rsp
    call cpu_test_leaf
cpu_test_mid_return:
    ud2

cpu_test_leaf:
    push rbp
    mov rbp, rsp
%if CPU_TEST_CASE = 6
    ; A genuine #GP while delivering another contributory #GP causes #DF.
    ; Selector 0x28 lies just past the five GDT slots (null/code/data/TSS*2).
    mov word [rel cpu_idt + 13*16 + 2], 0x28
%endif
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
    ; Verify that the entry stub clears DF while preserving the saved RFLAGS.
    std
%if CPU_TEST_CASE = 1
    int3
cpu_test_expected_rip:
%elif CPU_TEST_CASE = 3 || CPU_TEST_CASE = 6
    mov eax, 0x28
cpu_test_expected_rip:
    mov ds, ax
%elif CPU_TEST_CASE = 4
    mov rax, 0x0000000100000000 ; first address beyond the P1 4 GiB mappings
cpu_test_expected_rip:
    mov rbx, [rax]
%elif CPU_TEST_CASE = 5
    mov rsp, 0x0000000100000000
cpu_test_expected_rip:
    ud2
%elif CPU_TEST_CASE = 7
    mov eax, 1
    xor ecx, ecx
    xor edx, edx
cpu_test_expected_rip:
    div rcx
%elif CPU_TEST_CASE = 8
    mov rbp, 0x0000000100000000
cpu_test_expected_rip:
    ud2
%elif CPU_TEST_CASE = 2
cpu_test_expected_rip:
    ud2
%else
%error "Unknown CPU_TEST_CASE"
%endif
    ; No case can return to the normal P1 completion path.
    cli
.halt:
    hlt
    jmp .halt

section .note.GNU-stack noalloc noexec nowrite progbits
