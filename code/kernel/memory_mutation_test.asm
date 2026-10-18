; Warm translations before supervisor write revocation or final unmapping.
; Linked only into the corresponding isolated fatal test image.
bits 64
default rel
%ifndef MEMORY_MUTATION_TEST_CASE
%error "MEMORY_MUTATION_TEST_CASE must select an isolated mutation fault"
%endif

global memory_mutation_test_inject
global memory_mutation_test_expected_rip
global memory_mutation_test_mid_return
global memory_mutation_test_inject_return
extern memory_live_map, memory_live_protect, memory_live_unmap
extern memory_live_physical_a
extern kernel_fail

%define LIVE_VIRTUAL 0xffffa00000001000

section .text
; Root has completed and reported the common map/protect/replace/reclaim
; lifecycle. This private setup warms the exact target before its revocation.
memory_mutation_test_inject:
    push rbp
    mov rbp, rsp
    mov rdi, LIVE_VIRTUAL
    mov rsi, [rel memory_live_physical_a]
    mov edx, 1                   ; supervisor WB writable, NX
    call memory_live_map
    test rax, rax
    jnz kernel_fail
    mov rdi, LIVE_VIRTUAL
%if MEMORY_MUTATION_TEST_CASE = 1
    mov rax, 0x1122334455667788
    mov [rdi], rax               ; populate a writable translation
    xor esi, esi                ; same physical page, now read-only/NX
    call memory_live_protect
%elif MEMORY_MUTATION_TEST_CASE = 2
    mov rax, [rdi]               ; populate a readable translation
    call memory_live_unmap
%else
%error "Unknown MEMORY_MUTATION_TEST_CASE"
%endif
    test rax, rax
    jnz kernel_fail
    call memory_mutation_test_mid
memory_mutation_test_inject_return:
    ud2

memory_mutation_test_mid:
    push rbp
    mov rbp, rsp
    call memory_mutation_test_leaf
memory_mutation_test_mid_return:
    ud2

memory_mutation_test_leaf:
    push rbp
    mov rbp, rsp
    mov rax, LIVE_VIRTUAL
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
    std
memory_mutation_test_expected_rip:
%if MEMORY_MUTATION_TEST_CASE = 1
    mov byte [rax], 0x5a
%else
    mov rbx, [rax]
%endif
    ; Missing invalidation/permission enforcement cannot reach PASS.
    cli
.halt:
    hlt
    jmp .halt

section .note.GNU-stack noalloc noexec nowrite progbits
