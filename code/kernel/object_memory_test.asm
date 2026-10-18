; Test-only read of a warmed VA after the cache owner has unmapped it,
; completed local TLB retirement, and returned its real frame to buddy.
bits 64
default rel
global object_memory_test_inject
global object_memory_test_expected_rip
global object_memory_test_mid_return
global object_memory_test_inject_return
section .text
object_memory_test_inject:
    push rbp
    mov rbp, rsp
    call object_memory_test_mid
object_memory_test_inject_return:
    ud2
object_memory_test_mid:
    push rbp
    mov rbp, rsp
    call object_memory_test_leaf
object_memory_test_mid_return:
    ud2
object_memory_test_leaf:
    push rbp
    mov rbp, rsp
    mov rax, 0xffffb00000001000
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
object_memory_test_expected_rip:
    mov rbx, [rax]
    cli
.halt:
    hlt
    jmp .halt
section .note.GNU-stack noalloc noexec nowrite progbits
