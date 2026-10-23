bits 64
default rel
%include "user_smp.inc"
global runtime_large_environment,runtime_large_load,runtime_large_window,runtime_large_digest
global runtime_large_test_omit,runtime_large_window_active
section .data
align 8
runtime_large_window_active: dq 0
section .text
; These readers neither switch CR3 nor invalidate any translation. A warm AP
; stays on its already captured kernel root while CPU0 holds the global BKL.
runtime_large_environment:
    mov rax,[gs:UserSmpCpu.logical_id]
    mov [rdi],rax
    pushfq
    pop rax
    shr rax,9
    and eax,1
    xor eax,1
    mov [rdi+8],rax
    mov rax,cr3
    mov [rdi+16],rax
    mov rax,cr4
    mov [rdi+24],rax
    ret
runtime_large_load:
    mov rax,[gs:UserSmpCpu.logical_id]
    mov [rsi],rax
    mov rax,cr3
    mov [rsi+8],rax
    mov rax,cr4
    mov [rsi+16],rax
    lfence
    mov rax,[rdi]                   ; actual volatile alias load
    lfence
    mov [rsi+24],rax
    ret
runtime_large_window:
    mov [rel runtime_large_window_active],rdi
    ret
runtime_large_digest:
    ; Full old-window byte coverage only before/after the lifecycle, in this
    ; compact real reader loop. No writes, allocation, flush or CR3 switch.
    mov rax,0x4c41524745313601
    xor ecx,ecx
.word:
    xor rax,[rdi+rcx]
    rol rax,7
    add rcx,8
    cmp rcx,rsi
    jb .word
    ret
runtime_large_test_omit:
    ; Private guest bad build replaces only this literal. The unchanged
    ; production user_arch never calls this function.
    xor eax,eax
    ret
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
