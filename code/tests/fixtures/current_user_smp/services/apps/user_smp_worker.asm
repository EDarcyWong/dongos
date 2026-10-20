; NEW SYNTHETIC current-source workload, not recovered historical evidence.
; SysV ABI in both ELF64 and Win64 containers:
;   u64 user_smp_app_run(u64 probe[24], u64 argument, u64 pid, u64 limit)
; This finite native test does not establish guest CPL3/preemption behavior.
; Guest limit=0 runs continuously without yielding. Native limit=0 defaults
; to 16384, and USER_APP_NATIVE removes the guest syscall instruction entirely.
; p[20..23] belong to the Dong wrapper and are never modified here. Native
; also preserves p[19]; guest p[19] records the actual fixed-VA argument word.
bits 64
default rel
%ifndef USER_APP_NATIVE
%define USER_APP_NATIVE 0
%endif
%ifndef USER_APP_CORRUPT
%define USER_APP_CORRUPT 0
%endif

global user_smp_app_run
section .text
user_smp_app_run:
    push rbx
    push rbp
    push r12
    push r13
    push r14
    push r15
    sub rsp,48
    mov r12,rdi
    mov r13,rsi
    mov r14,rdx
    mov r15,rcx
%if USER_APP_NATIVE
    test r15,r15
    jnz .limit_ready
    mov r15d,16384
.limit_ready:
%endif
    ; Only assembly-owned output words are reset.
    xor eax,eax
    mov ecx,19
    rep stosq
    mov [r12+8],r13
    mov [r12+16],r14

    ; CPUID.1 EBX[31:24] is the actual initial local APIC ID (8 bits).
    mov eax,1
    cpuid
    shr ebx,24
    mov [r12+48],rbx
    bts qword [r12+64],rbx
    ; XGETBV is executed only after XSAVE, OSXSAVE and AVX are present.
    and ecx,0x1c000000
    cmp ecx,0x1c000000
    jne .features_ready
    xor ecx,ecx
    xgetbv
    and eax,6
    cmp eax,6
    jne .features_ready
    mov qword [r12+56],1
.features_ready:
    ; Independent memory expectations are retained throughout the busy loop.
    mov rbp,0xa55aa55a11223344
    xor rbp,r13
    xor rbp,r14
    mov [rsp],rbp
    mov r8,0x13579bdf2468ace0
    xor r8,r13
    mov [rsp+8],r8
    mov r9,0xfedcba9876543210
    xor r9,r14
    mov [rsp+16],r9
    mov rax,0x1122334455667788
    xor rax,r13
    mov [rsp+24],rax
    movq xmm0,rax
    mov rax,0x8877665544332211
    xor rax,r14
    mov [rsp+32],rax
    movq xmm15,rax
    mov rax,0xcafebabedeadbeef
    xor rax,r13
    xor rax,r14
    mov [rsp+40],rax
    cmp qword [r12+56],1
    jne .registers_ready
    vmovq xmm1,rax
    vinsertf128 ymm15,ymm15,xmm1,1
.registers_ready:
    lfence
    rdtsc
    shl rdx,32
    or rax,rdx
    mov [r12+128],rax
    mov [r12+136],rax
    mov qword [r12],1
%if USER_APP_CORRUPT
    ; Corrupt the LIVE register, not the oracle or result. The same comparison
    ; below must detect it, including when argument makes the low lane zero.
    pcmpeqd xmm1,xmm1
    pxor xmm0,xmm1
%endif
.loop:
    inc qword [r12+24]
    cmp rbp,[rsp]
    jne .bad_rbp
    cmp r8,[rsp+8]
    jne .bad_r8
    cmp r9,[rsp+16]
    jne .bad_r9
    movq rax,xmm0
    cmp rax,[rsp+24]
    jne .bad_xmm0
    movq rax,xmm15
    cmp rax,[rsp+32]
    jne .bad_xmm15
    cmp qword [r12+56],1
    jne .registers_checked
    vextractf128 xmm1,ymm15,1
    movq rax,xmm1
    cmp rax,[rsp+40]
    jne .bad_ymm15
.registers_checked:
%if !USER_APP_NATIVE
    ; Existing guest channels() mapping: read-only per-incarnation argument.
    ; No native branch can dereference this guest virtual address.
    mov eax,0x44000000
    mov rax,[rax]
    mov [r12+152],rax
    cmp rax,r13
    jne .bad_argument
    test qword [r12+24],0xfffff
    jnz .no_getpid
    inc qword [r12+32]
    mov edi,0x33
    mov eax,1
    syscall
    cmp rax,r14
    jne .bad_pid
.no_getpid:
%endif
    ; Sample migration without resetting any invariant register. CPUID only
    ; overwrites RAX/RBX/RCX/RDX; R8/R9/RBP and the SIMD canaries stay live.
    test qword [r12+24],4095
    jnz .sample_done
    mov eax,1
    cpuid
    shr ebx,24
    mov [r12+48],rbx
    bts qword [r12+64],rbx
    lfence
    rdtsc
    shl rdx,32
    or rax,rdx
    mov [r12+136],rax
.sample_done:
    test r15,r15
    jz .loop
    cmp [r12+24],r15
    jb .loop
    xor r10d,r10d
    jmp .finish

.bad_rbp:
    mov rax,rbp
    mov rdx,[rsp]
    mov ecx,1
    jmp .mismatch
.bad_r8:
    mov rax,r8
    mov rdx,[rsp+8]
    mov ecx,2
    jmp .mismatch
.bad_r9:
    mov rax,r9
    mov rdx,[rsp+16]
    mov ecx,3
    jmp .mismatch
.bad_xmm0:
    mov rdx,[rsp+24]
    mov ecx,4
    jmp .mismatch
.bad_xmm15:
    mov rdx,[rsp+32]
    mov ecx,5
    jmp .mismatch
.bad_ymm15:
    mov rdx,[rsp+40]
    mov ecx,6
    jmp .mismatch
%if !USER_APP_NATIVE
.bad_pid:
    mov rdx,r14
    mov ecx,7
    jmp .mismatch
.bad_argument:
    mov rdx,r13
    mov ecx,8
%endif
.mismatch:
    mov qword [r12+40],1
    mov [r12+96],rdx
    mov [r12+104],rcx
    mov [r12+112],rax
    mov r10d,0x060b0041
    mov [r12+120],r10
.finish:
    lfence
    rdtsc
    shl rdx,32
    or rax,rdx
    mov [r12+136],rax
    cmp qword [r12+56],1
    jne .return
    vzeroupper
.return:
    mov rax,r10
    add rsp,48
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbp
    pop rbx
    ret

%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
