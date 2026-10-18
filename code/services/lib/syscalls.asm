bits 64
default rel
global svc_call, svc_receive, svc_reply_wait
global svc_fence
global svc_ticks
global __dong_panic
global _start
extern service_main
section .text
svc_ticks:
    lfence
    rdtsc
    shl rdx,32
    or rax,rdx
    ret
_start:
    and rsp, -16
    call svc_graphics_features
    call service_main
    mov rdi, rax
    mov eax, 0xff
.exit:
    syscall
    ud2
global svc_user_ud2
svc_user_ud2:
    ud2

; SysV(number,A,B,C,D,E,F) -> RAX. SYSCALL destroys RCX/R11.
svc_call:
    mov rax, rdi
    mov rdi, rsi
    mov rsi, rdx
    mov rdx, rcx
    mov r10, r8
    mov r8, r9
    mov r9, [rsp + 8]
    syscall
    ret

svc_receive:
    push r12
    mov r12, rdx
    mov eax, 0x23
    syscall
    mov [r12], rdx
    pop r12
    ret

; SysV(endpoint,ticket,response,next,next_ticket*) -> RAX
svc_reply_wait:
    push r12
    mov r12, r8
    mov r10, rcx
    mov eax, 0x26
    syscall
    mov [r12], rdx
    pop r12
    ret
svc_fence:
    mfence
    ret
; Bounded by compositor preflight. Source is WB RAM, destination is the
; exclusive GOP mapping. SSE2 keeps this valid for the FXSAVE fallback.
global svc_present_rows
global svc_graphics_features,svc_vector_probe,svc_vector_clobber
global svc_gather_vendor_fast
svc_graphics_features:
    push rbx
    mov qword [rel svc_avx2],0
    mov qword [rel svc_gather_fast],0
    mov eax,1
    cpuid
    and ecx,0x1c000000
    cmp ecx,0x1c000000
    jne .none
    xor ecx,ecx
    xgetbv
    and eax,7
    cmp eax,7
    jne .none
    mov eax,7
    xor ecx,ecx
    cpuid
    test ebx,1<<5
    jz .none
    mov qword [rel svc_avx2],1
    ; Select once at process entry. TCG's per-lane gather helpers are slower
    ; than scalar loads; other hypervisors and native CPUs keep the AVX2 path.
    mov eax,0x40000000
    xor ecx,ecx
    cpuid
    mov edi,ebx
    mov esi,ecx
    call svc_gather_vendor_fast
    mov [rel svc_gather_fast],rax
    mov eax,1
    pop rbx
    ret
.none:
    xor eax,eax
    pop rbx
    ret
; SysV (CPUID.40000000 EBX, ECX, EDX) -> 0 for exactly TCGTCGTCGTCG,
; otherwise 1. This predicate alone does not authorize AVX instructions.
svc_gather_vendor_fast:
    mov eax,1
    cmp edi,0x54474354
    jne .return
    cmp esi,0x43544743
    jne .return
    cmp edx,0x47435447
    jne .return
    xor eax,eax
.return:
    ret
svc_vector_clobber:
    cmp qword [rel svc_avx2],1
    jne .return
    vpcmpeqd ymm15,ymm15,ymm15
    vzeroupper
.return:
    ret
; Input's separate ELF deliberately clobbers YMM15 before yielding. A probe
; which survives 128 real round-robin dispatches therefore requires YMM save.
svc_vector_probe:
    cmp qword [rel svc_avx2],1
    jne .unsupported
    push r12
    mov r12d,128
    vmovdqu ymm15,[rel svc_vector_canary]
.round:
    mov eax,3
    syscall
    vpcmpeqb ymm0,ymm15,[rel svc_vector_canary]
    vpmovmskb eax,ymm0
    cmp eax,-1
    jne .failed
    dec r12d
    jnz .round
    vzeroupper
    mov eax,1
    pop r12
    ret
.failed:
    vzeroupper
    mov eax,2
    pop r12
    ret
.unsupported:
    xor eax,eax
    ret
svc_present_rows:
    push rbx
    push r12
    push r13
    mov r12,rdi
    mov r13,rsi
    mov rbx,rdx
    shl rbx,2
.row:
    test r8,r8
    jz .done
    mov rdi,r13
    mov rsi,r12
    mov rdx,rcx
    test r9,r9
    jz .rgb
    cmp qword [rel svc_avx2],1
    je .avx_prefix
.prefix:
    test rdx,rdx
    jz .next
    test rdi,15
    jz .vector
    mov eax,[rsi]
    mov [rdi],eax
    add rsi,4
    add rdi,4
    dec rdx
    jmp .prefix
.vector:
    cmp rdx,4
    jb .tail
    movdqu xmm0,[rsi]
    movntdq [rdi],xmm0
    add rsi,16
    add rdi,16
    sub rdx,4
    jmp .vector
.avx_prefix:
    test rdx,rdx
    jz .next
    test rdi,31
    jz .avx_vector
    mov eax,[rsi]
    mov [rdi],eax
    add rsi,4
    add rdi,4
    dec rdx
    jmp .avx_prefix
.avx_vector:
    cmp rdx,32
    jb .avx_short
    vmovdqu ymm0,[rsi]
    vmovdqu ymm1,[rsi+32]
    vmovdqu ymm2,[rsi+64]
    vmovdqu ymm3,[rsi+96]
    vmovntdq [rdi],ymm0
    vmovntdq [rdi+32],ymm1
    vmovntdq [rdi+64],ymm2
    vmovntdq [rdi+96],ymm3
    add rsi,128
    add rdi,128
    sub rdx,32
    jmp .avx_vector
.avx_short:
    cmp rdx,8
    jb .tail
    vmovdqu ymm0,[rsi]
    vmovntdq [rdi],ymm0
    add rsi,32
    add rdi,32
    sub rdx,8
    jmp .avx_vector
.tail:
    test rdx,rdx
    jz .next
    mov eax,[rsi]
    mov [rdi],eax
    add rsi,4
    add rdi,4
    dec rdx
    jmp .tail
.rgb:
    test rdx,rdx
    jz .next
    mov eax,[rsi]
    mov r10d,eax
    and eax,0xff00ff00
    and r10d,0x00ff00ff
    ror r10d,16
    or eax,r10d
    mov [rdi],eax
    add rsi,4
    add rdi,4
    dec rdx
    jmp .rgb
.next:
    add r12,rbx
    add r13,rbx
    dec r8
    jmp .row
.done:
    sfence
    cmp qword [rel svc_avx2],1
    jne .return
    vzeroupper
.return:
    pop r13
    pop r12
    pop rbx
    ret
__dong_panic:
    mov eax, 0xfe
    syscall
    ud2
section .rodata
align 32
svc_vector_canary: dq 0x1122334455667788,0x8877665544332211,0xcafef00dbaad1234,0xd00d001122334455
section .data
align 8
global svc_avx2,svc_gather_fast
svc_avx2: dq 0
svc_gather_fast: dq 0
section .note.GNU-stack noalloc noexec nowrite progbits
