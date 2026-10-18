bits 64
default rel
%include "smp.inc"
%include "smp_report.inc"
%ifndef P1_TEST
%define P1_TEST 0
%endif
extern dong_smp_begin,dong_smp_report,smp_invalidate_all,parallel_live_begin
extern dong_boot_trace_online
extern serial_write,serial_hex_line,sched_xstate_save,sched_xstate_restore
global smp_runtime_begin,smp_invalidate_or_fail,smp_context_main,smp_pause
global smp_stress_begin,smp_stress_bsp,smp_stress_restore,smp_stress_reports,smp_bsp_tables
global smp_stress_go,smp_stress_data,smp_saved_xstate
global smp_current_xcr0
%define STRESS_ITERATIONS 2097152
section .text
smp_current_xcr0:
    xor ecx,ecx
    xgetbv
    shl rdx,32
    or rax,rdx
    ret
smp_pause:
    pause
    ret
smp_context_main:
    lea rax,[rel smp_stress_ap]
    ret
smp_stress_reports:
    lea rax,[rel smp_stress_data]
    ret
smp_stress_begin:
    sub rsp,8
    lea rdi,[rel smp_saved_xstate]
    call sched_xstate_save
    add rsp,8
    mov qword [rel smp_stress_go],0
    lea rdi,[rel smp_stress_data]
    mov ecx,16*SmpStress_size/8
    xor eax,eax
    cld
    rep stosq
    ret
smp_stress_restore:
    lea rdi,[rel smp_saved_xstate]
    jmp sched_xstate_restore
smp_stress_ap:
    sti
    jmp smp_stress_common
smp_stress_bsp:
    cli
    mov qword [rel smp_stress_go],1
smp_stress_common:
    push rbp
    mov rbp,rsp
    push rbx
    push r12
    push r13
    push r14
    push r15
    mov rax,[rdi+SmpContext.logical_id]
    shl rax,6
    lea r12,[rel smp_stress_data]
    add r12,rax
    mov qword [r12+SmpStress.ready],1
.wait:
    cmp qword [rel smp_stress_go],1
    je .start
    pause
    jmp .wait
.start:
    lfence
    rdtsc
    shl rdx,32
    or rax,rdx
    mov [r12+SmpStress.start_tsc],rax
    mov r9,[rdi+SmpContext.logical_id]
    mov rbx,0x1122334455667788
    add rbx,r9
    mov r13,0xcafebabedead4321
    xor r13,r9
    mov r14,0xd15ea5e5b00b1234
    mov r15,0x0102030405060708
    add r15,r9
    inc r9
    movq xmm0,rbx
    movq xmm1,r9
    xor r8d,r8d
.loop:
    paddq xmm0,xmm1
    inc r8
    test r8d,4095
    jnz .next
    mov rax,r8
    imul rax,r9
    add rax,rbx
    movq rdx,xmm0
    cmp rax,rdx
    je .xstate_ok
    inc qword [r12+SmpStress.errors]
.xstate_ok:
    inc qword [r12+SmpStress.xstate_checks]
    mov rax,0xcafebabedead4321
    xor rax,[rdi+SmpContext.logical_id]
    cmp rax,r13
    je .gpr1
    inc qword [r12+SmpStress.errors]
.gpr1:
    mov rax,0xd15ea5e5b00b1234
    cmp rax,r14
    je .gpr2
    inc qword [r12+SmpStress.errors]
.gpr2:
    mov rax,0x0102030405060708
    add rax,[rdi+SmpContext.logical_id]
    cmp rax,r15
    je .gpr3
    inc qword [r12+SmpStress.errors]
.gpr3:
    add qword [r12+SmpStress.gpr_checks],3
.next:
    cmp r8d,STRESS_ITERATIONS
    jb .loop
    movq rax,xmm0
    mov [r12+SmpStress.checksum],rax
    mov [r12+SmpStress.iterations],r8
    mfence
    lfence
    rdtsc
    shl rdx,32
    or rax,rdx
    mov [r12+SmpStress.end_tsc],rax
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret

smp_bsp_tables:
    sub rsp,32
    sgdt [rsp]
    sidt [rsp+16]
    mov rax,[rsp+2]
    mov [rdi+SmpContext.gdt],rax
    mov rdx,[rsp+18]
    mov [rdi+SmpContext.idt],rdx
    movzx edx,word [rax+CPU_TSS_SELECTOR+2]
    movzx ecx,byte [rax+CPU_TSS_SELECTOR+4]
    shl rcx,16
    or rdx,rcx
    movzx ecx,byte [rax+CPU_TSS_SELECTOR+7]
    shl rcx,24
    or rdx,rcx
    mov ecx,[rax+CPU_TSS_SELECTOR+8]
    shl rcx,32
    or rdx,rcx
    mov [rdi+SmpContext.tss],rdx
    mov rax,[rdx+CPU_TSS_IST1]
    mov [rdi+SmpContext.df_top],rax
    sub rax,CPU_IST_STACK_SIZE
    mov [rdi+SmpContext.df_bottom],rax
    mov rax,[rdx+CPU_TSS_IST2]
    mov [rdi+SmpContext.nmi_top],rax
    sub rax,CPU_IST_STACK_SIZE
    mov [rdi+SmpContext.nmi_bottom],rax
    mov rax,[rdx+CPU_TSS_IST3]
    mov [rdi+SmpContext.exception_top],rax
    sub rax,CPU_IST_STACK_SIZE
    mov [rdi+SmpContext.exception_bottom],rax
    add rsp,32
    ret

; Runtime wrappers tail-jump here with SysV entry alignment. No caller can
; continue to reclaim memory when an AP fails to acknowledge invalidation.
smp_invalidate_or_fail:
    sub rsp,8
    call smp_invalidate_all
    add rsp,8
    test rax,rax
    jnz smp_tlb_fatal
    ret
smp_tlb_fatal:
    cli
    cld
    mov rbx,rax
    lea rsi,[rel smp_marker_tlb_error]
    call serial_write
    mov rax,rbx
    call serial_hex_line
%if P1_TEST
    mov eax,0x11
    out 0xf4,eax
%endif
.halt:
    hlt
    jmp .halt

smp_runtime_begin:
    push rbp
    mov rbp,rsp
    push rbx
    push r12
    lea rsi,[rel smp_marker_start]
    call serial_write
    call dong_smp_begin
    mov rbx,rax
    call dong_smp_report
    mov r12,rax
    call smp_write_report
    test rbx,rbx
    jnz .bad
    ; Successful report already proved every logical CPU ONLINE. Derive mask
    ; from actual report, never a user log or assumed four-CPU constant.
    mov rcx,[r12+SmpReport.cpu_count]
    cmp rcx,1
    jb .trace_online_done
    cmp rcx,16
    ja .trace_online_done
    mov rdi,1
    shl rdi,cl
    dec rdi
    call dong_boot_trace_online
.trace_online_done:
    lea rsi,[rel smp_marker_ready]
    call serial_write
    cmp qword [r12+SmpReport.cpu_count],3
    jae .parallel
    mov eax,1
    jmp .return
.parallel:
    call parallel_live_begin
    test eax,eax
    jz .return
    mov eax,1
    jmp .return
.bad:
    lea rsi,[rel smp_marker_error]
    call serial_write
    mov rax,rbx
    call serial_hex_line
    xor eax,eax
.return:
    pop r12
    pop rbx
    pop rbp
    ret
%macro SMP_FIELDS 1
%1 version
%1 cpu_count
%1 online
%1 ping_acks
%1 iterations
%1 gpr_checks
%1 xstate_checks
%1 stress_errors
%1 overlap_start
%1 overlap_end
%1 tlb_broadcasts
%1 tlb_sent
%1 tlb_acks
%1 tlb_invalidations
%1 tlb_full
%1 tlb_probes
%1 reclaimed
%1 tables_before
%1 tables_after
%1 low_pages
%1 context_pointer
%1 stress_pointer
%1 domain_pointer
%1 mailbox_pointer
%1 marker_a
%1 marker_b
%1 steps
%1 error_code
%endmacro
%macro SMP_FIELD 1
    lea rsi,[rel smp_key_%1]
    call serial_write
    mov rax,[r12+SmpReport.%1]
    call serial_hex_line
%endmacro
smp_write_report:
    push rbp
    mov rbp,rsp
    SMP_FIELDS SMP_FIELD
    pop rbp
    ret
section .rodata
smp_marker_start: db "DONGOS_P6_SMP_START",13,10,0
smp_marker_ready: db "DONGOS_P6_SMP_READY",13,10,0
smp_marker_error: db "smp_runtime_error=",0
smp_marker_tlb_error: db "DONGOS_P6_TLB_FATAL=",0
%macro SMP_KEY 1
smp_key_%1: db "smp_",%str(%1),"=",0
%endmacro
SMP_FIELDS SMP_KEY
section .bss
alignb 64
smp_saved_xstate: resb 1024
smp_stress_data: resb 16*SmpStress_size
smp_stress_go: resq 1
