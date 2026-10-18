; Candidate CPL0 AP path. Not linked by the production build. No large BSS:
; top pointers only; Domain/queues/xstate/stacks must live in held arena RAM.
bits 64
default rel
%include "smp.inc"
%ifndef P1_TEST
%define P1_TEST 0
%endif
%ifndef P6_TEST_NO_XSTATE
%define P6_TEST_NO_XSTATE 0
%endif
%if P6_TEST_NO_XSTATE && !P1_TEST
%error AP xstate omission is test-only
%endif
extern dong_parallel_live_event
extern parallel_dispatch,parallel_request,parallel_idle_arm
extern sched_xstate_save,sched_xstate_restore,smp_send_ipi
extern sched_xstate_mask,__kernel_text_start,__kernel_text_end
global parallel_arch_if0,parallel_arch_lock,parallel_arch_unlock
global parallel_arch_on_scheduler,parallel_arch_root
global parallel_arch_save,parallel_arch_restore,parallel_arch_copy
global parallel_arch_register,parallel_arch_install,parallel_arch_timer
global parallel_arch_clock,parallel_arch_eoi,parallel_arch_kick
global sched_parallel_idle,sched_parallel_timer_entry,sched_parallel_ipi_entry
global parallel_thread_boot,parallel_thread_block,parallel_thread_yield,parallel_thread_exit
global parallel_scheduler_tops
global parallel_arch_seed,parallel_arch_entry,parallel_arch_text_begin,parallel_arch_text_end
section .text
parallel_arch_entry:
    lea rax,[rel parallel_thread_boot]
    ret
parallel_arch_text_begin:
    lea rax,[rel __kernel_text_start]
    ret
parallel_arch_text_end:
    lea rax,[rel __kernel_text_end]
    ret
parallel_arch_seed:
    push r12
    push r13
    sub rsp,8
    mov r12,rdi
    mov r13,rsi
    mov rdi,r13
    call sched_xstate_save
    fninit
    ldmxcsr [rel parallel_mxcsr]
%assign n 0
%rep 16
    pxor xmm %+ n,xmm %+ n
%assign n n+1
%endrep
    cmp qword [rel sched_xstate_mask],7
    jne .clean
    vzeroall
.clean:
    mov rdi,r12
    call sched_xstate_save
    mov rdi,r13
    call sched_xstate_restore
    add rsp,8
    pop r13
    pop r12
    ret
parallel_arch_if0:
    pushfq
    pop rax
    and eax,0x200
    xor eax,0x200
    shr eax,9
    ret
parallel_arch_lock:
    mov eax,1
.retry:
    xchg rax,[rdi]
    test rax,rax
    jz .locked
    pause
    mov eax,1
    jmp .retry
.locked:
    ret
parallel_arch_unlock:
    mov qword [rdi],0
    ret
parallel_arch_on_scheduler:
    xor eax,eax
    cmp rsp,rdi
    jb .done
    cmp rsp,rsi
    jae .done
    mov eax,1
.done:
    ret
parallel_arch_root:
    mov rax,cr3
    and rax,-4096
    ret
parallel_arch_save:
%if P6_TEST_NO_XSTATE
    ret
%else
    jmp sched_xstate_save
%endif
parallel_arch_restore:
%if P6_TEST_NO_XSTATE
    ret
%else
    jmp sched_xstate_restore
%endif
parallel_arch_copy:
    mov rcx,rdx
    cld
    rep movsb
    ret
parallel_arch_register:
    lea rax,[rel parallel_scheduler_tops]
    mov [rax+rdi*8],rsi
    mfence
    ret
parallel_arch_install:
    ; CPL0 only; all runnable threads bind this shared kernel root/tag0.
    mov [rsi+CPU_TSS_RSP0],rdx
    mov cr3,rdi
    xor eax,eax
    xor edx,edx
    mov ecx,0xc0000100
    wrmsr
    ; GS remains the current CPU's SmpContext, never a migrating thread base.
    xor eax,eax
    ret
parallel_arch_clock:
    lfence
    rdtsc
    shl rdx,32
    or rax,rdx
    ret
parallel_arch_timer:
    mov r10,rdi
    test esi,esi
    jz .stop
    cmp esi,1
    je .deadline
    cmp esi,2
    jne .bad
    test rdx,rdx
    jz .bad
    mov rax,rdx
    shr rax,32
    jnz .bad
    mov dword [r10+0x3e0],3
    mov dword [r10+0x320],0x40
    mov [r10+0x380],edx
    xor eax,eax
    ret
.stop:
    ; No runnable competition: mask the LVT, cancel one-shot and, only on
    ; CPUs advertising TSC-deadline, cancel any deadline MSR as well.
    mov dword [r10+0x320],0x10040
    mov dword [r10+0x380],0
    mfence
    push rbx
    mov eax,1
    cpuid
    test ecx,1<<24
    jz .stopped
    xor eax,eax
    xor edx,edx
    mov ecx,0x6e0
    wrmsr
.stopped:
    pop rbx
    xor eax,eax
    ret
.deadline:
    push rbx
    mov r9,rdx
    mov eax,1
    cpuid
    test ecx,1<<24
    jz .unsupported
    mov dword [r10+0x320],0x40040
    mfence
    mov rax,r9
    mov rdx,r9
    shr rdx,32
    mov ecx,0x6e0
    wrmsr
    xor eax,eax
    pop rbx
    ret
.unsupported:
    pop rbx
.bad:
    mov eax,1
    ret
parallel_arch_eoi:
    mov dword [rdi+0xb0],0
    ret
parallel_arch_kick:
    mov edx,0xf3
    mov ecx,1000000
    jmp smp_send_ipi
sched_parallel_idle:
    sub rsp,8
    mov rdi,[gs:SmpContext.logical_id]
    call parallel_idle_arm
    add rsp,8
    ret

; IST0: hardware and saved GPR frame stays on the interrupted thread's own
; stack. No queue release occurs until RSP changes to the per-CPU scheduler
; stack. A remote CPU can then resume the old stack without racing this code.
sched_parallel_timer_entry:
    push qword 0
    push qword 0x40
    jmp parallel_interrupt
sched_parallel_ipi_entry:
    push qword 0
    push qword 0xf3
parallel_interrupt:
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
    mov rax,cr2
    push rax
    cmp qword [rsp+CPU_CONTEXT_CS],CPU_KERNEL_CODE_SELECTOR
    jne parallel_fatal
    cld
    cli
    pushfq
    and qword [rsp],~(1<<18)
    popfq
    mov r12,rsp
    mov rdi,[gs:SmpContext.logical_id]
    cmp rdi,16
    jae parallel_fatal
    lea rax,[rel parallel_scheduler_tops]
    mov rax,[rax+rdi*8]
    test rax,rax
    jz .early
    mov rsp,rax
    and rsp,-16
    mov rsi,[r12+CPU_CONTEXT_VECTOR]
    call dong_parallel_live_event
    test rax,rax
    jnz parallel_fatal
    mov rdi,[gs:SmpContext.logical_id]
    mov rsi,r12
    mov edx,1
    cmp qword [r12+CPU_CONTEXT_VECTOR],0xf3
    jne .dispatch
    mov edx,2
.dispatch:
    call parallel_dispatch
    test rax,rax
    jz parallel_fatal
    mov rsp,rax
    jmp parallel_restore
.early:
    mov rax,[gs:SmpContext.lapic_va]
    mov dword [rax+0xb0],0
    mov rsp,r12
parallel_restore:
    pop rax
    mov cr2,rax
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
    add rsp,16
    iretq
parallel_thread_boot:
    sub rsp,8
    call r12
    add rsp,8
    jmp parallel_thread_exit
parallel_thread_block:
    mov esi,1
    jmp parallel_thread_request
parallel_thread_yield:
    xor esi,esi
parallel_thread_request:
    pushfq
    cli
    mov rdi,[gs:SmpContext.logical_id]
    call parallel_request
    test rax,rax
    jnz .done
    int 0xf3
.done:
    popfq
    ret
parallel_thread_exit:
    pushfq
    cli
    mov rdi,[gs:SmpContext.logical_id]
    mov esi,2
    call parallel_request
    test rax,rax
    jnz parallel_fatal
    int 0xf3
parallel_fatal:
    cli
.halt:
    hlt
    jmp .halt
section .bss
align 64
parallel_scheduler_tops: resq 16
section .rodata
align 4
parallel_mxcsr: dd 0x1f80
