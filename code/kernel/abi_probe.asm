; Independent P1 external callees. Both return sum(argument[i] * (i+1)).
bits 64
default rel
section .text
global kernel_sysv_mix
global kernel_win_mix

; 功能：验证 SysV 八标量参数，含栈上第七、八参数。
; 输入：rdi/rsi/rdx/rcx/r8/r9，[rsp+8]，[rsp+16]。
; 输出：rax=加权和。
; 破坏：rax/r10/r11/flags；保留所有非易失寄存器。
; 中断/锁：P1 探针调用，无需持锁。
kernel_sysv_mix:
    mov rax, rdi
    lea rax, [rax+rsi*2]
    lea r10, [rdx+rdx*2]
    add rax, r10
    lea rax, [rax+rcx*4]
    lea r10, [r8+r8*4]
    add rax, r10
    imul r10, r9, 6
    add rax, r10
    imul r10, [rsp+8], 7
    add rax, r10
    mov r11, [rsp+16]
    lea rax, [rax+r11*8]
    ret

; 功能：验证 Microsoft x64 八标量参数及影子空间布局。
; 输入：rcx/rdx/r8/r9，栈参数从 [rsp+40] 起。
; 输出：rax=加权和。
; 破坏：rax/r10/r11/flags；保留 Microsoft x64 所有非易失状态。
; 中断/锁：P1 探针调用，无需持锁。
kernel_win_mix:
    mov rax, rcx
    lea rax, [rax+rdx*2]
    lea r10, [r8+r8*2]
    add rax, r10
    lea rax, [rax+r9*4]
    imul r10, [rsp+40], 5
    add rax, r10
    imul r10, [rsp+48], 6
    add rax, r10
    imul r10, [rsp+56], 7
    add rax, r10
    mov r11, [rsp+64]
    lea rax, [rax+r11*8]
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
