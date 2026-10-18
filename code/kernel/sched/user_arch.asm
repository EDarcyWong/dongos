; Raw per-CPU user-domain operations. Called with IF=0 and trusted kernel GS.
; No global BSP UserCpu, original-root or PCID first-use state is accessed.
; Entry/IRET, GDT/MSR activation, service glue and SMP handler conversion remain
; separate integration work; merely linking this object does not enable SMP.
bits 64
default rel
%include "user_entry.inc"
%ifndef P1_TEST
%define P1_TEST 0
%endif
%ifndef RUNTIME_LEVEL
%define RUNTIME_LEVEL 0
%endif
%ifndef USER_SMP_TEST_NO_XSTATE
%define USER_SMP_TEST_NO_XSTATE 0
%endif
%if USER_SMP_TEST_NO_XSTATE && (!P1_TEST || RUNTIME_LEVEL != 7)
%error user xstate omission is isolated test desktop only
%endif
%if USER_SMP_TEST_NO_XSTATE
extern __dg_m757365722e7365727669636573_g534d505f544553545f534c4f5453
%endif
extern sched_xstate_save
extern smp_send_ipi
extern user_validate_interrupt_frame
global user_smp_arch_if0,user_smp_arch_cpu,user_smp_arch_root
global user_smp_arch_try_lock,user_smp_arch_unlock,user_smp_arch_pause
global user_smp_arch_clock,user_smp_arch_copy,user_smp_arch_save
global user_smp_arch_flush,user_smp_arch_kick,user_smp_arch_switch
global user_smp_arch_validate,user_smp_arch_enable_pcid
section .text
user_smp_arch_if0:
    pushfq
    pop rax
    and eax,0x200
    xor eax,0x200
    shr eax,9
    ret
user_smp_arch_cpu:
    mov rax,[gs:UserSmpCpu.logical_id]
    ret
user_smp_arch_root:
    mov rax,cr3
    and rax,-4096
    ret
user_smp_arch_try_lock:
    mov eax,1
    xchg rax,[rdi]
    test rax,rax
    setz al
    movzx eax,al
    ret
user_smp_arch_unlock:
    mov qword [rdi],0
    ret
user_smp_arch_pause:
    pause
    ret
user_smp_arch_clock:
    lfence
    rdtsc
    shl rdx,32
    or rax,rdx
    ret
user_smp_arch_copy:
    mov rcx,rdx
    cld
    rep movsb
    ret
user_smp_arch_save:
%if USER_SMP_TEST_NO_XSTATE
    ; Preserve essential AND ordinary GUI startup. The trusted BSP role mask
    ; selects only cfg7..11; physical >=7 alone is unsafe with GUI slot reuse.
    mov rax,[gs:UserSmpCpu.domain]
    mov rax,[rax+88]                ; Domain.cpus; native layout asserted
    mov rcx,[gs:UserSmpCpu.logical_id]
    imul rcx,120                    ; Cpu_size; native layout asserted
    mov rax,[rax+rcx+24]            ; Cpu.slot
    bt qword [rel __dg_m757365722e7365727669636573_g534d505f544553545f534c4f5453],rax
    jnc .ordinary_excluded
    ret
.ordinary_excluded:
    jmp sched_xstate_save
%else
    jmp sched_xstate_save
%endif
user_smp_arch_validate:
    ; The root is bound by the selected slot/incarnation, never caller data.
    cmp [rdi+UserFrame.cr3],rsi
    jne .bad
    test qword [rdi+UserFrame.rflags],0x200
    jz .bad
    jmp user_validate_interrupt_frame
.bad:
    xor eax,eax
    ret
user_smp_arch_kick:
    cmp rdi,[gs:UserSmpCpu.context_count]
    jae .bad
    cmp rdi,16
    jae .bad
    mov rax,[gs:UserSmpCpu.contexts]
    shl rdi,8
    add rax,rdi
    mov rsi,[rax+SmpContext.apic_id]
    mov rax,[gs:UserSmpCpu.smp]
    mov rdi,[rax+SmpContext.lapic_va]
    mov edx,USER_SMP_RESCHEDULE_VECTOR
    mov ecx,1000000
    jmp smp_send_ipi
.bad:
    mov eax,1
    ret
user_smp_arch_enable_pcid:
    ; Call once before domain admission on each CPU after installing this GS.
    ; Stable PCID/INVPCID policy thereafter; PGE is excluded by the root policy.
    push rbx
    mov qword [gs:UserSmpCpu.pcid_enabled],0
    mov r8,cr4
    test r8,1<<7
    jnz .bad
    mov rax,cr3
    test rax,4095
    jnz .bad
    mov eax,1
    cpuid
    test ecx,1<<17
    jz .fallback
    xor eax,eax
    cpuid
    cmp eax,7
    jb .fallback
    mov eax,7
    xor ecx,ecx
    cpuid
    test ebx,1<<10
    jz .fallback
    bts r8,17
    mov cr4,r8
    mov qword [gs:UserSmpCpu.pcid_enabled],1
    mov eax,1
    pop rbx
    ret
.fallback:
    test r8,1<<17
    jnz .bad
    xor eax,eax
    pop rbx
    ret
.bad:
    mov rax,-1
    pop rbx
    ret
user_smp_arch_flush:
    cmp rdi,[gs:UserSmpCpu.logical_id]
    jne .bad
    mov r8,cr3
    and r8,-4096
    cmp r8,[gs:UserCpu.original_cr3]
    jne .bad
    mov r9,cr4
    test r9,1<<7
    jnz .bad
    test r9,1<<17
    jz .untagged
    cmp qword [gs:UserSmpCpu.pcid_enabled],1
    jne .bad
    sub rsp,24
    mov qword [rsp],0
    mov qword [rsp+8],0
    mov eax,2
    invpcid rax,[rsp]
    add rsp,24
    xor eax,eax
    ret
.untagged:
    cmp qword [gs:UserSmpCpu.pcid_enabled],0
    jne .bad
    mov cr3,r8
    xor eax,eax
    ret
.bad:
    mov eax,1
    ret
user_smp_arch_switch:
    test rdi,rdi
    jz .bad
    test rdi,4095
    jnz .bad
    mov rax,rdi
    shr rax,32
    jnz .bad
    cmp rsi,1
    jb .bad
    cmp rsi,16
    ja .bad
    cmp rdx,1
    ja .bad
    mov rax,cr3
    and rax,-4096
    cmp rax,[gs:UserCpu.original_cr3]
    jne .bad
    mov r8,cr4
    test r8,1<<7
    jnz .bad
    test r8,1<<17
    jz .fallback
    cmp qword [gs:UserSmpCpu.pcid_enabled],1
    jne .bad
    or rdi,rsi
    test rdx,rdx
    jz .install
    bts rdi,63
    jmp .install
.fallback:
    cmp qword [gs:UserSmpCpu.pcid_enabled],0
    jne .bad
.install:
    mov cr3,rdi
    mov r8,[gs:UserEntryCpu.kernel_xstate]
    inc qword [r8+1024+UserEntryMetrics.switches]
    cmp qword [gs:UserSmpCpu.pcid_enabled],1
    jne .counted
    test rdx,rdx
    jz .counted
    inc qword [r8+1024+UserEntryMetrics.retained]
.counted:
    xor eax,eax
    ret
.bad:
    mov eax,1
    ret
