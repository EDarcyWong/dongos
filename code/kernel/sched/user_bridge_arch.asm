bits 64
default rel
%include "user_entry.inc"
extern user_smp_arch_cpu,user_smp_arch_clock,user_smp_arch_copy,user_smp_arch_kick
extern sched_xstate_restore
extern dong_user_smp_service,dong_user_smp_project
extern dong_user_smp_interrupt,dong_user_smp_service_policy
extern user_smp_arch_legacy
global user_bridge_cpu,user_bridge_clock,user_bridge_copy,user_bridge_restore
global user_bridge_kick,user_bridge_eoi,user_bridge_timer
global user_bridge_service,user_bridge_project
global user_domain_legacy_poll
global user_bridge_interrupt,user_bridge_service_policy
global services_smp_pcid_metric
section .text
user_bridge_cpu: jmp user_smp_arch_cpu
user_bridge_clock: jmp user_smp_arch_clock
user_bridge_copy: jmp user_smp_arch_copy
user_bridge_restore: jmp sched_xstate_restore
user_bridge_kick: jmp user_smp_arch_kick
user_bridge_service_policy: jmp dong_user_smp_service_policy
user_bridge_service: jmp dong_user_smp_service
user_bridge_project: jmp dong_user_smp_project
user_domain_legacy_poll: jmp user_smp_arch_legacy
user_bridge_interrupt: jmp dong_user_smp_interrupt
services_smp_pcid_metric:
    test rdi,rdi
    jnz .metric
    mov rax,cr4
    ret
.metric:
    mov rax,[gs:UserEntryCpu.kernel_xstate]
    cmp rdi,1
    jne .retain
    mov rax,[rax+1024+UserEntryMetrics.switches]
    ret
.retain:
    cmp rdi,2
    jne .enabled
    mov rax,[rax+1024+UserEntryMetrics.retained]
    ret
.enabled:
    mov rax,[gs:UserSmpCpu.pcid_enabled]
    ret
user_bridge_eoi:
    cmp rdi,[gs:UserSmpCpu.logical_id]
    jne .bad
    cmp rsi,0xff
    je .done
    cmp rsi,0x40
    je .eoi
    cmp rsi,USER_SMP_RESCHEDULE_VECTOR
    je .eoi
    cmp rsi,SMP_PING_VECTOR
    je .eoi
    cmp rsi,SMP_TLB_VECTOR
    je .eoi
    cmp rsi,0xf3                   ; harmless old scheduler wake after handoff
    je .eoi
    cmp rdi,0
    jne .bad
    cmp rsi,0x51
    je .eoi
    cmp rsi,0x5c
    jne .bad
.eoi:
    mov rax,[gs:UserSmpCpu.smp]
    mov rax,[rax+SmpContext.lapic_va]
    mov dword [rax+0xb0],0
.done:
    xor eax,eax
    ret
.bad:
    mov eax,1
    ret
; One-shot local timer. Independent rate comes from the live AP calibration,
; not mutable BSP platform state. Empty/single runnable domain masks the LVT.
user_bridge_timer:
    cmp rdi,[gs:UserSmpCpu.logical_id]
    jne .bad
    cmp rsi,1
    ja .bad
    mov r8,[gs:UserSmpCpu.smp]
    mov r8,[r8+SmpContext.lapic_va]
    test rsi,rsi
    jnz .arm
    mov dword [r8+0x320],0x10040
    mov dword [r8+0x380],0
    push rbx
    mov eax,1
    cpuid
    test ecx,1<<24
    jz .no_deadline
    mov ecx,0x6e0
    xor eax,eax
    xor edx,edx
    wrmsr
.no_deadline:
    pop rbx
    xor eax,eax
    ret
.arm:
    mov rax,[gs:UserEntryCpu.timer_hz]
    xor edx,edx
    mov ecx,1000
    div rcx
    test rax,rax
    jz .bad
    mov rdx,rax
    shr rdx,32
    jnz .bad
    mov dword [r8+0x3e0],3
    mov dword [r8+0x320],0x40
    mov [r8+0x380],eax
    xor eax,eax
    ret
.bad:
    mov eax,1
    ret
