bits 64
default rel
%include "user_entry.inc"
extern dong_user_smp_boot_prepare,dong_user_smp_boot_publish,dong_user_smp_boot_report
extern dong_user_entry_mapped,dong_user_entry_guard
extern dong_parallel_live_report,parallel_live_rate,dong_user_smp_project
extern user_smp_activate,user_smp_idle,user_smp_fail
extern smp_send_ipi
global user_smp_boot_begin,user_smp_try_handoff
global user_entry_mapped,user_entry_guard
global user_boot_live_report,user_boot_rate,user_boot_publish,user_boot_pause,user_boot_project
global user_smp_handoff_headers,user_smp_handoff_count
section .text
user_entry_mapped: jmp dong_user_entry_mapped
user_entry_guard: jmp dong_user_entry_guard
user_boot_live_report: jmp dong_parallel_live_report
user_boot_rate: jmp parallel_live_rate
user_boot_project: jmp dong_user_smp_project
user_boot_pause:
    pause
    ret
; Shared BSP preparation precedes this publication. Wake the old AP idle loop
; with its old ping gate; no old handler ever sees Header GS during handoff.
user_boot_publish:
    push rbx
    push r12
    push r13
    mov r12,rdi
    mov r13,rsi
    mov [rel user_smp_handoff_count],rsi
    mfence
    mov [rel user_smp_handoff_headers],rdi
    mov ebx,1
.loop:
    cmp rbx,r13
    jae .done
    mov rax,[r12+rbx*8]
    mov rax,[rax+UserSmpCpu.smp]
    mov rsi,[rax+SmpContext.apic_id]
    mov rax,[r12]
    mov rax,[rax+UserSmpCpu.smp]
    mov rdi,[rax+SmpContext.lapic_va]
    mov edx,SMP_PING_VECTOR
    mov ecx,1000000
    call smp_send_ipi
    test eax,eax
    jnz .return
    inc rbx
    jmp .loop
.done:
    xor eax,eax
.return:
    pop r13
    pop r12
    pop rbx
    ret
; Called only at original AP idle (IF0, GS still old SmpContext). The prior
; parallel engine is drained and all local timers stopped before publication.
user_smp_try_handoff:
    mov rax,[rel user_smp_handoff_headers]
    test rax,rax
    jz .return
    mov rcx,[gs:SmpContext.logical_id]
    test rcx,rcx
    jz .fatal
    cmp rcx,[rel user_smp_handoff_count]
    jae .fatal
    mov rdi,[rax+rcx*8]
    mov rax,[gs:SmpContext.self]
    cmp [rdi+UserSmpCpu.smp],rax
    jne .fatal
    sub rsp,8
    call user_smp_activate
    add rsp,8
    test eax,eax
    jnz .fatal
    jmp user_smp_idle
.return:
    ret
.fatal:
    cli
.halt:
    hlt
    jmp .halt
; BSP success is noreturn; the default-off services_run selector alone calls it.
user_smp_boot_begin:
    sub rsp,8
    call dong_user_smp_boot_prepare
    test eax,eax
    jnz .error
    call dong_user_smp_boot_report
    mov rax,[rax+48]               ; checked Report.headers layout
    mov rdi,[rax]
    call user_smp_activate
    test eax,eax
    jnz .error
    call dong_user_smp_boot_publish
    test eax,eax
    jnz user_smp_fail
    jmp user_smp_idle
.error:
    add rsp,8
    ret
section .bss
alignb 8
user_smp_handoff_headers:resq 1
user_smp_handoff_count:resq 1

; Normal runtime policy is pure and independently native-testable. A 1/2-CPU
; machine keeps BSP userspace; >=3 uses the already validated phase6 handoff.
; Corrupt/unfinished topology is an error, never a permissive legacy fallback.
global user_smp_normal_policy
section .text
user_smp_normal_policy:
    mov rax,-1
    cmp rsi,31
    jne .done
    cmp rdi,1
    jb .done
    cmp rdi,16
    ja .done
    xor eax,eax
    cmp rdi,3
    setae al
.done:
    ret
