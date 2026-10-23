; Component only. Actual PF-entry wiring is deliberately a later integration.
bits 64
default rel
%include "user_smp.inc"
global runtime_exec_hardware,runtime_exec_action,runtime_exec_probe_label
global runtime_exec_write_attempt,runtime_exec_write_after
section .text
; SysV(Environment*). Raw tag-bearing CR3 is retained, never normalized.
runtime_exec_hardware:
    mov rax,[gs:UserSmpCpu.logical_id]
    mov [rdi],rax
    mov rax,cr3
    mov [rdi+8],rax
    mov rax,cr0
    mov [rdi+16],rax
    mov rax,cr4
    mov [rdi+24],rax
    pushfq
    pop rax
    mov [rdi+32],rax
    ret
runtime_exec_probe_label:
    lea rax,[rel runtime_exec_write_attempt]
    test rdi,rdi
    jz .done
    lea rax,[rel runtime_exec_write_after]
    cmp rdi,1
    je .done
    xor eax,eax
.done:
    ret
; SysV(command,VA,value,FaultTicket*,Sample*). No CR3 write, invalidation,
; IDT mutation, allocation or invented ACK occurs here. The payload is the
; owned mov eax,imm32;ret sequence and has no SIMD/ABI side effects.
runtime_exec_action:
    push rbp
    push rbx
    push r12
    push r13
    push r14
    push r15
    sub rsp,24
    mov r13,rdi
    mov r14,rsi
    mov r15,rdx
    mov [rsp],rcx
    mov r12,r8
    mfence
    xor eax,eax
    cpuid                         ; actual per-reader instruction serialization
    cmp r13,1
    je rex_serialized
    cmp r13,2
    je rex_read
    cmp r13,3
    je rex_call
    cmp r13,4
    je rex_probe
    cmp r13,5
    je rex_warm
    cmp r13,6
    je rex_store
    mov qword [r12+48],2
    xor eax,eax
    jmp rex_value
rex_serialized:
    xor eax,eax
    jmp rex_normal
rex_read:
    mov rax,[r14]
    jmp rex_normal
rex_call:
    call r14
    jmp rex_normal
rex_warm:
    mov rax,[r14]
    mov [r14],r15                 ; actual same-value store warms writable TLB
    mfence
    mov rax,[r14]
    jmp rex_normal
rex_store:
    mov [r14],r15
    mfence
    mov rax,[r14]
    jmp rex_normal
rex_probe:
runtime_exec_write_attempt:
    mov [r14],r15                 ; ONLY this exact RIP may consume a PF ticket
runtime_exec_write_after:
    mfence
    mov rax,[rsp]
    mov rax,[rax+8]               ; consumed=1 only after exact handler match
    mov [r12+48],rax
    mov rax,[r14]                 ; retain the actual payload after the attempt
    jmp rex_value
rex_normal:
    mov qword [r12+48],0
rex_value:
    mov [r12+40],rax
    mov rax,[gs:UserSmpCpu.logical_id]
    mov [r12],rax
    mov rax,cr3
    mov [r12+8],rax
    mov rax,cr0
    mov [r12+16],rax
    mov rax,cr4
    mov [r12+24],rax
    pushfq
    pop rax
    mov [r12+32],rax
    add rsp,24
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
