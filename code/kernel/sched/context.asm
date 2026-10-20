; Resumable BSP timer entry. Intel SDM vol3 7.14: SS:RSP is saved and IRETQ
; restores it even at CPL0. IST MUST be zero: suspended frames own their stacks.
; Eager x87/SSE save; no lazy #NM, supervisor xstate, AVX, red zone or heap.
bits 64
default rel
%include "sched.inc"
%ifndef P1_TEST
%define P1_TEST 0
%endif
%ifndef RUNTIME_LEVEL
%define RUNTIME_LEVEL 0
%endif
%ifndef SCHED_TEST_DROP_YMM
%define SCHED_TEST_DROP_YMM 0
%endif
%if SCHED_TEST_DROP_YMM && (!P1_TEST || RUNTIME_LEVEL != 7)
%error YMM fault injection requires the test desktop profile
%endif
extern dong_sched_init
extern dong_sched_tick
extern platform_timer_rearm
extern apic_eoi
extern __kernel_text_start
extern __kernel_text_end
global sched_xstate_init
global sched_xstate_enable_avx,sched_xstate_mask
global sched_start
global sched_timer_entry
global sched_irq_save
global sched_irq_restore
global sched_lock_irqsave
global sched_unlock_irqrestore
global sched_park
global sched_xstate_save
global sched_xstate_restore
global sched_report
global sched_report_end
global sched_engine
global sched_xstates
global sched_guard_ranges
global sched_guard_ranges_end
global sched_guard_count
global sched_stack_ranges
global sched_stack_ranges_end
global sched_worker0_stack_bottom
global sched_worker0_stack_top
global sched_worker1_stack_bottom
global sched_worker1_stack_top
global sched_worker0_guard_low
global sched_worker0_guard_high
global sched_worker1_guard_low
global sched_worker1_guard_high
global sched_worker0
global sched_worker1
global sched_bootstrap_wait
global sched_terminal

section .text
; SysV u64 init(): before the first bound MMU control snapshot, IF/AC/DF=0.
; Zero means unsupported/invalid baseline. Configure only x87/SSE XCR0=3;
; CPUID1 FXSR+SSE+SSE2 mandatory, XSAVE optional and capability gated.
sched_xstate_init:
    push rbp
    mov rbp, rsp
    push rbx
    push r12
    pushfq
    pop rax
    test eax, 0x60600
    jnz .bad
    mov eax, 1
    cpuid
    mov [rel sched_report + SchedReport.cpuid1_ecx], ecx
    mov [rel sched_report + SchedReport.cpuid1_edx], edx
    mov eax, edx
    and eax, 0x07000000
    cmp eax, 0x07000000
    jne .bad
    mov r12d, ecx
    mov rax, cr0
    and rax, ~12                  ; no EM or TS: eager save can never #NM
    or rax, 0x22                  ; MP, NE
    mov cr0, rax
    mov [rel sched_report + SchedReport.cr0], rax
    mov rax, cr4
    or rax, 0x600                 ; OSFXSR, OSXMMEXCPT
    mov cr4, rax
    mov qword [rel sched_report + SchedReport.xstate_mode], 1
    mov qword [rel sched_report + SchedReport.xstate_bytes], 512
    test r12d, 1 << 26
    jz .fallback
    xor eax, eax
    cpuid
    cmp eax, 0xd
    jb .bad
    mov eax, 0xd
    xor ecx, ecx
    cpuid
    mov [rel sched_report + SchedReport.cpuidd_eax], eax
    mov [rel sched_report + SchedReport.cpuidd_edx], edx
    and eax, 3
    cmp eax, 3
    jne .bad
    mov rax, cr4
    or rax, 1 << 18
    mov cr4, rax
    xor ecx, ecx
    xor edx, edx
    mov eax, 3
    xsetbv
    xgetbv
    test edx, edx
    jnz .bad
    cmp eax, 3
    jne .bad
    mov [rel sched_report + SchedReport.xcr0], rax
    mov eax, 0xd
    xor ecx, ecx
    cpuid
    cmp ebx, 576
    jb .bad
    cmp ebx, SCHED_XSTATE_STRIDE
    ja .bad
    mov [rel sched_report + SchedReport.xstate_bytes], ebx
    mov qword [rel sched_report + SchedReport.xstate_mode], 2
    jmp .configured
.fallback:
    mov rax, cr4
    test eax, 1 << 18             ; inconsistent unsupported OSXSAVE baseline
    jnz .bad
.configured:
    mov rax, cr4
    mov [rel sched_report + SchedReport.cr4], rax
    fninit
    ldmxcsr [rel default_mxcsr]
%assign i 0
%rep 16
    pxor xmm %+ i, xmm %+ i
%assign i i+1
%endrep
    lea rdi, [rel sched_xstates]
    xor eax, eax
    mov ecx, 3 * SCHED_XSTATE_STRIDE / 8
    rep stosq
    lea rdi, [rel sched_xstates]
    call xstate_save
    lea rsi, [rel sched_xstates]
    lea rdi, [rel sched_xstates + SCHED_XSTATE_STRIDE]
    mov ecx, SCHED_XSTATE_STRIDE / 8
    rep movsq
    lea rsi, [rel sched_xstates]
    lea rdi, [rel sched_xstates + SCHED_XSTATE_STRIDE * 2]
    mov ecx, SCHED_XSTATE_STRIDE / 8
    rep movsq
    mov qword [rel xstate_ready], 1
    mov eax, 1
    jmp .return
.bad:
    xor eax, eax
.return:
    pop r12
    pop rbx
    pop rbp
    ret

sched_xstate_save:
xstate_save:
    cmp qword [rel sched_report + SchedReport.xstate_mode], 2
    jne .fx
    mov eax,[rel sched_xstate_mask]
    xor edx, edx
    xsave64 [rdi]
    ret
.fx:
    fxsave64 [rdi]
    ret
sched_xstate_restore:
xstate_restore:
    cmp qword [rel sched_report + SchedReport.xstate_mode], 2
    jne .fx
    mov eax,[rel sched_xstate_mask]
    xor edx, edx
    xrstor64 [rdi]
    ret
.fx:
    fxrstor64 [rdi]
    ret

; Optional P7 extension, after the completed P3 proof and before AP start.
; Keep the immutable historical P3 report at XCR0=3. New user saves include
; YMM_Hi128 only after CPUID validates the standard 832-byte XSAVE layout.
sched_xstate_enable_avx:
    push rbx
    push r12
    cmp qword [rel xstate_ready],1
    jne .unsupported
    cmp qword [rel sched_report+SchedReport.xstate_mode],2
    jne .unsupported
    mov eax,1
    cpuid
    and ecx,0x1c000000
    cmp ecx,0x1c000000
    jne .unsupported
    mov eax,7
    xor ecx,ecx
    cpuid
    test ebx,1<<5
    jz .unsupported
    mov eax,0xd
    xor ecx,ecx
    cpuid
    and eax,7
    cmp eax,7
    jne .unsupported
    mov eax,0xd
    mov ecx,2
    cpuid
    cmp eax,256
    jne .unsupported
    cmp ebx,576
    jne .unsupported
    xor ecx,ecx
    xgetbv
    test edx,edx
    jnz .unsupported
    cmp eax,3
    jne .unsupported
    mov eax,7
    xsetbv
    mov eax,0xd
    xor ecx,ecx
    cpuid
    cmp ebx,832
    jne .rollback
%if SCHED_TEST_DROP_YMM
    mov qword [rel sched_xstate_mask],3
%else
    mov qword [rel sched_xstate_mask],7
%endif
    vzeroall
    mov eax,1
    jmp .return
.rollback:
    xor ecx,ecx
    xor edx,edx
    mov eax,3
    xsetbv
.unsupported:
    xor eax,eax
.return:
    pop r12
    pop rbx
    ret

; SysV u64 start(): root has installed vector40 IST0, armed LAPIC and unmapped
; exported guards. Returns on the original bootstrap stack, IF0; root disarms.
; This proof is one-shot, but the generic core/IRQ frame ABI is reusable by P4.
sched_start:
    push rbp
    mov rbp, rsp
    push rbx
    push r12
    push r13
    push r14
    push r15
    sub rsp, 8
    cmp qword [rel xstate_ready], 1
    jne sched_start_bad
    cmp qword [rel started], 0
    jne sched_start_bad
    pushfq
    pop rax
    test eax, 0x60600
    jnz sched_start_bad
    mov qword [rel started], 1
    mov [rel bootstrap_stack_ceiling], rsp
    lea rdi, [rel sched_worker0_stack_top - CPU_CONTEXT_SIZE - 8]
    lea rsi, [rel sched_worker0]
    lea rdx, [rel sched_worker0_stack_top - 8]
    call make_frame
    lea rdi, [rel sched_worker1_stack_top - CPU_CONTEXT_SIZE - 8]
    lea rsi, [rel sched_worker1]
    lea rdx, [rel sched_worker1_stack_top - 8]
    call make_frame
    lea rdi, [rel sched_engine]
    lea rsi, [rel sched_worker0_stack_top - CPU_CONTEXT_SIZE - 8]
    lea rdx, [rel sched_worker1_stack_top - CPU_CONTEXT_SIZE - 8]
    call dong_sched_init
    test rax, rax
    jnz sched_start_bad
    mov qword [rel sched_report + SchedReport.version], 1
    mov qword [rel sched_report + SchedReport.vector], SCHED_VECTOR
    mov qword [rel sched_report + SchedReport.guard_count], 2
    lea rax, [rel sched_worker0_stack_bottom]
    mov [rel sched_report + SchedReport.worker0_stack_bottom], rax
    lea rax, [rel sched_worker0_stack_top]
    mov [rel sched_report + SchedReport.worker0_stack_top], rax
    lea rax, [rel sched_worker1_stack_bottom]
    mov [rel sched_report + SchedReport.worker1_stack_bottom], rax
    lea rax, [rel sched_worker1_stack_top]
    mov [rel sched_report + SchedReport.worker1_stack_top], rax
    sti
sched_bootstrap_wait:
    pause
    cmp qword [rel sched_engine + SCHED_TICKS], 129
    jb sched_bootstrap_wait
    cli
    mov rax, [rel sched_engine + SCHED_TICKS]
    mov [rel sched_report + SchedReport.ticks], rax
    mov rax, [rel sched_engine + SCHED_SWITCHES]
    mov [rel sched_report + SchedReport.switches], rax
    mov rax, [rel sched_engine + SCHED_THREADS + SCHED_THREAD_SIZE + SCHED_THREAD_TICKS]
    mov [rel sched_report + SchedReport.worker0_ticks], rax
    mov rax, [rel sched_engine + SCHED_THREADS + SCHED_THREAD_SIZE * 2 + SCHED_THREAD_TICKS]
    mov [rel sched_report + SchedReport.worker1_ticks], rax
    mov rax, [rel sched_engine + SCHED_THREADS + SCHED_THREAD_FRAME]
    mov rax, [rax + CPU_CONTEXT_RSP]
    mov [rel sched_report + SchedReport.bootstrap_rsp], rax
    mov rax, [rel sched_engine + SCHED_THREADS + SCHED_THREAD_SIZE + SCHED_THREAD_FRAME]
    mov rax, [rax + CPU_CONTEXT_RSP]
    mov [rel sched_report + SchedReport.worker0_rsp], rax
    mov rax, [rel sched_engine + SCHED_THREADS + SCHED_THREAD_SIZE * 2 + SCHED_THREAD_FRAME]
    mov rax, [rax + CPU_CONTEXT_RSP]
    mov [rel sched_report + SchedReport.worker1_rsp], rax
    cmp qword [rel sched_report + SchedReport.worker0_fail], 0
    jne sched_start_bad
    cmp qword [rel sched_report + SchedReport.worker1_fail], 0
    jne sched_start_bad
    cmp qword [rel sched_report + SchedReport.worker0_count], 0
    je sched_start_bad
    cmp qword [rel sched_report + SchedReport.worker1_count], 0
    je sched_start_bad
    mov qword [rel sched_report + SchedReport.steps], 7
    mov eax, 1
    jmp sched_start_return
sched_start_bad:
    cli
    xor eax, eax
sched_start_return:
    add rsp, 8
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret

; rdi frame, rsi entry, rdx initialRSP. Frame and future return slot disjoint.
make_frame:
    mov r8, rdi
    xor eax, eax
    mov ecx, CPU_CONTEXT_SIZE / 8
    rep stosq
    mov [r8 + CPU_CONTEXT_RIP], rsi
    mov qword [r8 + CPU_CONTEXT_CS], CPU_KERNEL_CODE_SELECTOR
    mov qword [r8 + CPU_CONTEXT_SS], CPU_KERNEL_DATA_SELECTOR
    mov qword [r8 + CPU_CONTEXT_RFLAGS], 0x202
    mov [r8 + CPU_CONTEXT_RSP], rdx
    mov qword [r8 + CPU_CONTEXT_VECTOR], SCHED_VECTOR
    ret

sched_timer_entry:
    push qword 0
    push qword SCHED_VECTOR
    push rax
    push rbx
    push rcx
    push rdx
    push rbp
    push rsi
    push rdi
    push r8
    push r9
    push r10
    push r11
    push r12
    push r13
    push r14
    push r15
    mov rax, cr2
    push rax
    mov r12, rsp
    cld
    cli
    pushfq
    and qword [rsp], ~(1 << 18)
    popfq
    and rsp, -16
    mov r13, [rel sched_engine + SCHED_CURRENT]
    cmp r13, 3
    jae sched_terminal
    mov rdi, r13
    shl rdi, 10
    lea rax, [rel sched_xstates]
    add rdi, rax
    call xstate_save
    lea rdi, [rel sched_engine]
    mov rsi, r12
    call dong_sched_tick
    cmp rax, 3
    jae sched_terminal
    mov r13, rax
    imul rax, SCHED_THREAD_SIZE
    lea rdx, [rel sched_engine + SCHED_THREADS]
    mov r14, [rdx + rax + SCHED_THREAD_FRAME]
    test r14, 7
    jnz sched_terminal
    test r14, r14
    jz sched_terminal
    cmp qword [r14 + CPU_CONTEXT_CS], CPU_KERNEL_CODE_SELECTOR
    jne sched_terminal
    cmp qword [r14 + CPU_CONTEXT_SS], CPU_KERNEL_DATA_SELECTOR
    jne sched_terminal
    lea rax, [rel __kernel_text_start]
    cmp [r14 + CPU_CONTEXT_RIP], rax
    jb sched_terminal
    lea rax, [rel __kernel_text_end]
    cmp [r14 + CPU_CONTEXT_RIP], rax
    jae sched_terminal
    test r13, r13
    jz .bootstrap_bounds
    mov rax, r13
    dec rax
    shl rax, 4
    lea rdx, [rel sched_stack_ranges]
    mov rcx, [rdx + rax]
    cmp r14, rcx
    jb sched_terminal
    mov rdx, [rdx + rax + 8]
    lea rax, [r14 + CPU_CONTEXT_SIZE]
    cmp rax, rdx
    ja sched_terminal
    mov rax, [r14 + CPU_CONTEXT_RSP]
    cmp rax, rcx
    jb sched_terminal
    cmp rax, rdx
    ja sched_terminal
    jmp .frame_bounds_ok
.bootstrap_bounds:
    mov rdx, [rel bootstrap_stack_ceiling]
    lea rcx, [rdx - 4096]
    cmp r14, rcx
    jb sched_terminal
    lea rax, [r14 + CPU_CONTEXT_SIZE]
    cmp rax, rdx
    ja sched_terminal
    mov rax, [r14 + CPU_CONTEXT_RSP]
    cmp rax, rcx
    jb sched_terminal
    cmp rax, rdx
    ja sched_terminal
.frame_bounds_ok:
    mov rax, [r14 + CPU_CONTEXT_RFLAGS]
    test eax, 0x67400             ; DF/IOPL/NT/VM/AC must be zero
    jnz sched_terminal
    and eax, 0x202
    cmp eax, 0x202
    jne sched_terminal
    call platform_timer_rearm
    test rax, rax
    jnz sched_terminal
    call apic_eoi
    mov rdi, r13
    shl rdi, 10
    lea rax, [rel sched_xstates]
    add rdi, rax
    call xstate_restore
    inc qword [rel sched_report + SchedReport.restore_checks]
    mov rsp, r14
    pop rax
    mov cr2, rax
    pop r15
    pop r14
    pop r13
    pop r12
    pop r11
    pop r10
    pop r9
    pop r8
    pop rdi
    pop rsi
    pop rbp
    pop rdx
    pop rcx
    pop rbx
    pop rax
    add rsp, 16
    iretq

sched_terminal:
    cli
    mov qword [rel sched_report + SchedReport.steps], 0xbad
.halt:
    hlt
    jmp .halt

; Both workers are independent live loops, with no call, yield, HLT or INT.
; Every iteration checks all GPR seeds, all 16 complete XMM registers, x87
; control+ST0 and MXCSR after asynchronous preemption. Separate scratch slots.
%macro WORKER 2
sched_worker%1:
    fldcw [rel worker%1_cw]
    ldmxcsr [rel worker%1_mxcsr]
%if %1 == 0
    fld1
%else
    fldz
%endif
%assign i 0
%rep 16
    movdqu xmm %+ i, [rel worker%1_pattern]
%assign i i+1
%endrep
    mov eax, %2 + 1
    mov ebx, %2 + 2
    mov ecx, %2 + 3
    mov edx, %2 + 4
    mov esi, %2 + 5
    mov edi, %2 + 6
    xor ebp, ebp
    mov r8d, %2 + 8
    mov r9d, %2 + 9
    mov r10d, %2 + 10
    mov r11d, %2 + 11
    mov r12d, %2 + 12
    mov r13d, %2 + 13
    mov r14d, %2 + 14
    mov r15d, %2 + 15
.loop:
    cmp rax, %2 + 1
    jne .fail
    cmp rbx, %2 + 2
    jne .fail
    cmp rcx, %2 + 3
    jne .fail
    cmp rdx, %2 + 4
    jne .fail
    cmp rsi, %2 + 5
    jne .fail
    cmp rdi, %2 + 6
    jne .fail
    test rbp, rbp
    jnz .fail
%assign i 8
%rep 8
    cmp r %+ i, %2 + i
    jne .fail
%assign i i+1
%endrep
    stmxcsr [rel worker%1_scratch + 256]
    fnstcw [rel worker%1_scratch + 260]
    fst qword [rel worker%1_scratch + 264]
%assign i 0
%rep 16
    movdqu [rel worker%1_scratch + i * 16], xmm %+ i
%assign i i+1
%endrep
%assign i 0
%rep 32
    mov rax, [rel worker%1_pattern + (i % 2) * 8]
    cmp [rel worker%1_scratch + i * 8], rax
    jne .fail
%assign i i+1
%endrep
    mov eax, [rel worker%1_mxcsr]
    cmp [rel worker%1_scratch + 256], eax
    jne .fail
    mov ax, [rel worker%1_cw]
    cmp [rel worker%1_scratch + 260], ax
    jne .fail
%if %1 == 0
    mov rax, 0x3ff0000000000000
%else
    xor eax, eax
%endif
    cmp [rel worker%1_scratch + 264], rax
    jne .fail
    mov eax, %2 + 1
    inc qword [rel sched_report + SchedReport.worker%1_count]
    inc qword [rel sched_report + SchedReport.gpr_checks]
    jmp .loop
.fail:
    inc qword [rel sched_report + SchedReport.worker%1_fail]
    jmp .loop
%endmacro
WORKER 0, 0x100
WORKER 1, 0x200

; BSP IRQ-safe locks: acquire before any shared mutation, never sleep holding
; one. Saved flags is an opaque token from this CPU and this nesting level.
sched_irq_save:
    pushfq
    pop rax
    cli
    ret
sched_irq_restore:
    test edi, 1 << 9
    jz .off
    sti
.off:
    ret
sched_lock_irqsave:
    pushfq
    pop r8
    cli
.retry:
    xor eax, eax
    mov edx, 1
    lock cmpxchg [rdi], edx
    je .locked
    pause
    jmp .retry
.locked:
    mov rax, r8
    ret
sched_unlock_irqrestore:
    mov dword [rdi], 0
    test esi, 1 << 9
    jz .off
    sti
.off:
    ret

; SysV void park(Engine*): after core.wait succeeded, IF0. Return IF0 only
; after wake_one made this thread runnable and a real IRQ selected it again.
; No other locks may be held. STI/HLT is adjacent; no lost local wake window.
sched_park:
    push r12
    push r13
    mov r12, rdi
    mov r13, [r12 + SCHED_CURRENT]
    cmp r13, 8
    jae sched_terminal
    imul r13, SCHED_THREAD_SIZE
.wait:
    cmp qword [r12 + r13 + SCHED_THREADS], 3
    jne .awake
    sti
    hlt
    cli
    jmp .wait
.awake:
    pop r13
    pop r12
    ret

section .rodata
align 16
default_mxcsr: dd 0x1f80
worker0_mxcsr: dd 0x1f80
worker1_mxcsr: dd 0x3f80
worker0_cw: dw 0x037f
worker1_cw: dw 0x077f
align 16
worker0_pattern: dq 0x1122334455667788, 0x8877665544332211
worker1_pattern: dq 0x55aa33cc77ee9900, 0x0099ee77cc33aa55
align 8
sched_guard_count: dq 2
; These are intentional absolute kernel VA metadata, resolved by the linker.
%if __NASM_MAJOR__ >= 3
[warning push]
[warning -reloc-abs-qword]
%endif
sched_guard_ranges:
    dq sched_worker0_guard_low, sched_worker0_guard_high
    dq sched_worker1_guard_low, sched_worker1_guard_high
sched_guard_ranges_end:
sched_stack_ranges:
    dq sched_worker0_stack_bottom, sched_worker0_stack_top
    dq sched_worker1_stack_bottom, sched_worker1_stack_top
sched_stack_ranges_end:
%if __NASM_MAJOR__ >= 3
[warning pop]
%endif

section .data
align 8
sched_xstate_mask: dq 3
section .bss
align 64, resb 1
sched_report: resb SchedReport_size
sched_report_end:
align 64, resb 1
sched_engine: resb SCHED_ENGINE_SIZE
align 64, resb 1
sched_xstates: resb SCHED_XSTATE_STRIDE * 3
worker0_scratch: resb 272
worker1_scratch: resb 272
xstate_ready: resq 1
started: resq 1
bootstrap_stack_ceiling: resq 1
align 4096, resb 1
sched_worker0_guard_low: resb 4096
sched_worker0_stack_bottom: resb SCHED_STACK_SIZE
sched_worker0_stack_top:
sched_worker0_guard_high: resb 4096
sched_worker1_guard_low: resb 4096
sched_worker1_stack_bottom: resb SCHED_STACK_SIZE
sched_worker1_stack_top:
sched_worker1_guard_high: resb 4096
