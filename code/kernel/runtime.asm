; BSP runtime continuation, entered after the original protected MMU/cache
; lifecycle. Firmware services and the broad bootstrap aliases are gone.
bits 64
default rel
%include "cpu.inc"
%include "control_state.inc"
%include "device_views.inc"
%include "platform_report.inc"
%include "sched.inc"
%ifndef RUNTIME_LEVEL
%define RUNTIME_LEVEL 0
%endif
%if RUNTIME_LEVEL >= 6
extern smp_invalidate_or_fail
%endif

extern memory_read_controls, dong_acpi_inventory, dong_device_prepare, dong_device_plan
extern dong_platform_init, dong_platform_arm, dong_platform_report, platform_diagnostic_word
extern dong_runtime_guard, platform_timer_stop
extern sched_start, sched_report, sched_guard_ranges, sched_guard_count
extern cpu_idt, sched_timer_entry, serial_write, serial_hex_line
extern __kernel_bss_start, __kernel_bss_end
global runtime_begin, runtime_invalidate, runtime_flush_root
global runtime_state, runtime_device_views, runtime_platform_report
global runtime_device_plan, runtime_spurious_count, runtime_view

section .text
runtime_invalidate:
    invlpg [rdi]
%if RUNTIME_LEVEL >= 6
    xor esi,esi
    jmp smp_invalidate_or_fail
%endif
    ret
runtime_flush_root:
    mov rax, cr3
    mov cr3, rax
%if RUNTIME_LEVEL >= 6
    xor edi,edi
    mov esi,1
    jmp smp_invalidate_or_fail
%endif
    ret

; SysV u64 runtime_begin(View*): success returns1, failure0, always IF=0.
runtime_begin:
    push rbp
    mov rbp, rsp
    push rbx
    push r12
    push r13
    push r14
    push r15
    sub rsp, 8
    mov [rel runtime_view], rdi
    cli
    cld
    lea rsi, [rel runtime_marker_started]
    call serial_write
    lea rdi, [rel runtime_state]
    call memory_read_controls
    lea rdi, [rel runtime_state]
    lea rsi, [rel runtime_device_views]
    call dong_device_prepare
    test rax, rax
    jnz .error
    call dong_device_plan
    test rax, rax
    jz .bad
    mov [rel runtime_device_plan], rax
    ; The immutable linked table supplies only the scheduler's four guards.
    lea rbx, [rel sched_guard_ranges]
    mov r12, [rel sched_guard_count]
    cmp r12, 2
    jne .bad
    shl r12, 1
.guard:
    mov rdi, [rbx]
    test rdi, 4095
    jnz .bad
    lea rax, [rel __kernel_bss_start]
    cmp rdi, rax
    jb .bad
    lea rax, [rel __kernel_bss_end - 4096]
    cmp rdi, rax
    ja .bad
    call dong_runtime_guard
    test rax, rax
    jnz .error
    add rbx, 8
    dec r12
    jnz .guard
    ; Resumable timer interrupts use the interrupted thread's own stack.
    ; Fatal exceptions continue to use the original dedicated IST stacks.
    lea rax, [rel sched_timer_entry]
    mov edi, SCHED_VECTOR
    call set_gate
    lea rax, [rel runtime_spurious]
    mov edi, 0xff
    call set_gate
    call dong_acpi_inventory
    mov rdi, rax
    lea rsi, [rel runtime_device_views]
    lea rdx, [rel runtime_platform_report]
    call dong_platform_init
    test rax, rax
    jnz .error
    lea rsi, [rel irq_ready]
    call serial_write
    mov edi, 10000000              ; 10ms quantum reference interval
    call dong_platform_arm
    test rax, rax
    jnz .error
    call sched_start
    cmp rax, 1
    jne .bad
    cli
    call platform_timer_stop
    test rax, rax
    jnz .error
    lea rdi, [rel runtime_platform_report]
    call dong_platform_report
    test rax, rax
    jnz .error
    call write_reports
    lea rsi, [rel threads_ready]
    call serial_write
    mov eax, 1
    jmp .return
.bad:
    mov eax, 0x03030006
.error:
    mov r15, rax
    lea rsi, [rel error_key]
    call serial_write
    mov rax, r15
    call serial_hex_line
    cmp r15d, 0x03050003
    jne .no_diagnostic
    call write_failure_diagnostic
.no_diagnostic:
    xor eax, eax
.return:
    cli
    add rsp, 8
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret

; IF=0, rax handler, edi vector; no firmware gate or DPL3 entry retained.
set_gate:
    lea rdx, [rel cpu_idt]
    shl edi, 4
    add rdx, rdi
    mov word [rdx], ax
    mov word [rdx + 2], CPU_KERNEL_CODE_SELECTOR
    mov byte [rdx + 4], 0
    mov byte [rdx + 5], CPU_IDT_INTERRUPT_GATE
    shr rax, 16
    mov word [rdx + 6], ax
    shr rax, 16
    mov dword [rdx + 8], eax
    mov dword [rdx + 12], 0
    ret

; A LAPIC spurious vector has no in-service entry and requires no EOI.
runtime_spurious:
    inc qword [rel runtime_spurious_count]
    iretq

; Failure-only ordered scalar words, fixed version-1 schema and hard limit.
; UART writes are the only added device effect; no controller reads occur.
write_failure_diagnostic:
    push rbp
    mov rbp, rsp
    push r12
    sub rsp, 8
    lea rsi, [rel diagnostic_begin]
    call serial_write
    xor r12d, r12d
.word:
    lea rsi, [rel diagnostic_key]
    call serial_write
    mov rdi, r12
    call platform_diagnostic_word
    call serial_hex_line
    inc r12d
    cmp r12d, 56
    jb .word
    lea rsi, [rel diagnostic_end]
    call serial_write
    add rsp, 8
    pop r12
    pop rbp
    ret

%macro PLATFORM_FIELD 1
    lea rsi, [rel platform_key_%1]
    call serial_write
    mov rax, [rel runtime_platform_report + PlatformReport.%1]
    call serial_hex_line
%endmacro
%macro SCHED_FIELD 1
    lea rsi, [rel sched_key_%1]
    call serial_write
    mov rax, [rel sched_report + SchedReport.%1]
    call serial_hex_line
%endmacro
write_reports:
    push rbp
    mov rbp, rsp
    PLATFORM_FIELD lapic_pa
    PLATFORM_FIELD lapic_va
    PLATFORM_FIELD lapic_id
    PLATFORM_FIELD lapic_version
    PLATFORM_FIELD ioapic_count
    PLATFORM_FIELD redirection_count
    PLATFORM_FIELD pic_master
    PLATFORM_FIELD pic_slave
    PLATFORM_FIELD reference_source
    PLATFORM_FIELD tsc_hz
    PLATFORM_FIELD lapic_hz
    PLATFORM_FIELD timer_mode
    PLATFORM_FIELD interval_ns
    PLATFORM_FIELD last_tsc
    PLATFORM_FIELD last_deadline
    PLATFORM_FIELD arm_count
    PLATFORM_FIELD stop_count
    PLATFORM_FIELD spurious_vector
    PLATFORM_FIELD timer_vector
    PLATFORM_FIELD cr4
    PLATFORM_FIELD rflags
    PLATFORM_FIELD ref_period_fs
    PLATFORM_FIELD ref_delta
    PLATFORM_FIELD steps
    SCHED_FIELD version
    SCHED_FIELD vector
    SCHED_FIELD ticks
    SCHED_FIELD switches
    SCHED_FIELD worker0_count
    SCHED_FIELD worker1_count
    SCHED_FIELD worker0_ticks
    SCHED_FIELD worker1_ticks
    SCHED_FIELD worker0_fail
    SCHED_FIELD worker1_fail
    SCHED_FIELD gpr_checks
    SCHED_FIELD xstate_mode
    SCHED_FIELD xstate_bytes
    SCHED_FIELD xcr0
    SCHED_FIELD cpuid1_ecx
    SCHED_FIELD cpuid1_edx
    SCHED_FIELD cpuidd_eax
    SCHED_FIELD cpuidd_edx
    SCHED_FIELD cr0
    SCHED_FIELD cr4
    SCHED_FIELD bootstrap_rsp
    SCHED_FIELD worker0_rsp
    SCHED_FIELD worker1_rsp
    SCHED_FIELD worker0_stack_bottom
    SCHED_FIELD worker0_stack_top
    SCHED_FIELD worker1_stack_bottom
    SCHED_FIELD worker1_stack_top
    SCHED_FIELD restore_checks
    SCHED_FIELD guard_count
    SCHED_FIELD steps
    lea rsi, [rel plan_key]
    call serial_write
    mov rax, [rel runtime_device_plan]
    call serial_hex_line
    lea rsi, [rel spurious_key]
    call serial_write
    mov rax, [rel runtime_spurious_count]
    call serial_hex_line
    pop rbp
    ret

section .rodata
runtime_marker_started: db "DONGOS_P3_RUNTIME_START", 13,10,0
irq_ready: db "DONGOS_P3_IRQ_READY",13,10,0
threads_ready: db "DONGOS_P3_THREADS_READY",13,10,0
error_key: db "runtime_error=",0
plan_key: db "runtime_device_plan=",0
spurious_key: db "runtime_spurious_count=",0
%macro PLATFORM_KEY 1
platform_key_%1: db "platform_",%str(%1),"=",0
%endmacro
%macro SCHED_KEY 1
sched_key_%1: db "sched_",%str(%1),"=",0
%endmacro
PLATFORM_KEY lapic_pa
PLATFORM_KEY lapic_va
PLATFORM_KEY lapic_id
PLATFORM_KEY lapic_version
PLATFORM_KEY ioapic_count
PLATFORM_KEY redirection_count
PLATFORM_KEY pic_master
PLATFORM_KEY pic_slave
PLATFORM_KEY reference_source
PLATFORM_KEY tsc_hz
PLATFORM_KEY lapic_hz
PLATFORM_KEY timer_mode
PLATFORM_KEY interval_ns
PLATFORM_KEY last_tsc
PLATFORM_KEY last_deadline
PLATFORM_KEY arm_count
PLATFORM_KEY stop_count
PLATFORM_KEY spurious_vector
PLATFORM_KEY timer_vector
PLATFORM_KEY cr4
PLATFORM_KEY rflags
PLATFORM_KEY ref_period_fs
PLATFORM_KEY ref_delta
PLATFORM_KEY steps
SCHED_KEY version
SCHED_KEY vector
SCHED_KEY ticks
SCHED_KEY switches
SCHED_KEY worker0_count
SCHED_KEY worker1_count
SCHED_KEY worker0_ticks
SCHED_KEY worker1_ticks
SCHED_KEY worker0_fail
SCHED_KEY worker1_fail
SCHED_KEY gpr_checks
SCHED_KEY xstate_mode
SCHED_KEY xstate_bytes
SCHED_KEY xcr0
SCHED_KEY cpuid1_ecx
SCHED_KEY cpuid1_edx
SCHED_KEY cpuidd_eax
SCHED_KEY cpuidd_edx
SCHED_KEY cr0
SCHED_KEY cr4
SCHED_KEY bootstrap_rsp
SCHED_KEY worker0_rsp
SCHED_KEY worker1_rsp
SCHED_KEY worker0_stack_bottom
SCHED_KEY worker0_stack_top
SCHED_KEY worker1_stack_bottom
SCHED_KEY worker1_stack_top
SCHED_KEY restore_checks
SCHED_KEY guard_count
SCHED_KEY steps

section .rodata
; Exactly 56 ordered words (448B), max UART payload 1966B (including CRLF).
diagnostic_begin: db 'DONGOS_IRQ_DIAGNOSTIC_V1_BEGIN',13,10,0
diagnostic_key: db 'irq_diag_word=',0
diagnostic_end: db 'DONGOS_IRQ_DIAGNOSTIC_V1_END',13,10,0

section .bss
align 8, resb 1
runtime_state: resb ControlState_size
runtime_device_views: resb DeviceViews_size
runtime_platform_report: resb PlatformReport_size
runtime_device_plan: resq 1
runtime_spurious_count: resq 1
runtime_view: resq 1
