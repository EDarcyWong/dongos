; Optional actual-AP probe entry. Allocate one 128-byte, 64-aligned record per
; admitted thread in the arena, pass its address as argument. No cooperative
; yield is used in the loop. Root sets record.stop=1 only after observing
; actual per-CPU timer dispatches and repeated progress of both local threads.
bits 64
default rel
%include "smp.inc"
extern parallel_thread_exit
global parallel_probe_worker,parallel_probe_entry
section .text
parallel_probe_entry:
    lea rax,[rel parallel_probe_worker]
    ret
parallel_probe_worker:
    mov rbx,rdi
    xor r12d,r12d
    mov r13,0x1122334455667788
    xor r13,rbx
    mov r14,0x8877665544332211
    mov r15,0xcafebabedeadbeef
    xor r15,rbx
    movq xmm0,r13
    mov eax,1
    movq xmm1,rax
    movq xmm15,r14
    cmp qword [gs:SmpContext.xcr0],7
    jne .seeded
    movq xmm14,r15
    vinsertf128 ymm15,ymm15,xmm14,1
.seeded:
    mov qword [rbx],1
.loop:
    paddq xmm0,xmm1
    paddq xmm15,xmm1
    inc r12
    test r12d,4095
    jnz .loop
    mov rax,0x1122334455667788
    xor rax,rbx
    cmp r13,rax
    jne .bad
    add rax,r12
    movq rdx,xmm0
    cmp rdx,rax
    jne .bad
    mov rax,0x8877665544332211
    cmp r14,rax
    jne .bad
    add rax,r12
    movq rdx,xmm15
    cmp rdx,rax
    jne .bad
    mov rax,0xcafebabedeadbeef
    xor rax,rbx
    cmp r15,rax
    jne .bad
    cmp qword [gs:SmpContext.xcr0],7
    jne .cpu
    vextractf128 xmm13,ymm15,1
    movq rdx,xmm13
    cmp rdx,r15
    jne .bad
.cpu:
    mov rcx,[gs:SmpContext.logical_id]
    mov eax,1
    shl rax,cl
    or [rbx+24],rax
    mov [rbx+32],rcx
    mov [rbx+8],r12
    cmp qword [rbx+48],0
    je .loop
    mov qword [rbx+56],1
    jmp parallel_thread_exit
.bad:
    inc qword [rbx+16]
    mov qword [rbx+56],2
    jmp parallel_thread_exit
