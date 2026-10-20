; BSP-only capability-gated CR4 hardening, after private-root activation and
; before the first active_paging.Context bind. No USER mappings are created.
bits 64
default rel
%include "control_state.inc"
%include "hardening_features.inc"
%include "hardening_plan.inc"
%include "hardening_report.inc"

global cpu_hardening_activate
global cpu_hardening_apply_cr4
extern dong_cpu_hardening_detect, dong_cpu_hardening_plan, dong_cpu_hardening_verify
extern memory_read_controls

section .text
; SysV: rdi points to a writable generated Report. Returns a Dong error or 0.
; The caller is CPL0 on the BSP, IF=0, with a validated supervisor-only tree.
cpu_hardening_activate:
    push rbp
    mov rbp, rsp
    push rbx
    sub rsp, 8
    mov rbx, rdi
    ; AC clearing must work even when CPUID.SMAP=0. Do not execute CLAC here.
    pushfq
    and qword [rsp], ~(1 << 18)
    popfq
    mov qword [rbx + HardeningReport.steps], 1
    lea rdi, [rel hardening_features]
    call dong_cpu_hardening_detect
    lea rdi, [rel hardening_before]
    call memory_read_controls
    lea rdi, [rel hardening_features]
    lea rsi, [rel hardening_before]
    lea rdx, [rel hardening_plan]
    call dong_cpu_hardening_plan
    test rax, rax
    jnz hardening_return
    mov rax, [rel hardening_plan + HardeningPlan.cr4]
cpu_hardening_apply_cr4:
    mov cr4, rax                   ; capability-checked OR; preserve other bits
    or qword [rbx + HardeningReport.steps], 2
    lea rdi, [rel hardening_after]
    call memory_read_controls
    or qword [rbx + HardeningReport.steps], 4
%macro FEATURE 1
    mov rax, [rel hardening_features + HardeningFeatures.%1]
    mov [rbx + HardeningReport.%1], rax
%endmacro
    FEATURE max_basic
    FEATURE leaf7_ebx
    FEATURE leaf7_ecx
%unmacro FEATURE 1
    mov rax, [rel hardening_plan + HardeningPlan.supported]
    mov [rbx + HardeningReport.supported], rax
%macro CONTROL 3
    mov rax, [rel %2 + ControlState.%3]
    mov [rbx + HardeningReport.%1], rax
%endmacro
    CONTROL cr4_before, hardening_before, cr4
    CONTROL cr4_after, hardening_after, cr4
    CONTROL rflags_before, hardening_before, rflags
    CONTROL rflags_after, hardening_after, rflags
    CONTROL cr0, hardening_after, cr0
    CONTROL cr3, hardening_after, cr3
    CONTROL efer, hardening_after, efer
    CONTROL pat, hardening_after, pat
%unmacro CONTROL 3
    lea rdi, [rel hardening_features]
    lea rsi, [rel hardening_before]
    lea rdx, [rel hardening_after]
    lea rcx, [rel hardening_plan]
    mov r8, rbx
    call dong_cpu_hardening_verify
hardening_return:
    add rsp, 8
    pop rbx
    pop rbp
    ret

section .bss
align 8, resb 1
hardening_features: resb HardeningFeatures_size
hardening_plan: resb HardeningPlan_size
hardening_before: resb ControlState_size
hardening_after: resb ControlState_size

section .note.GNU-stack noalloc noexec nowrite progbits
