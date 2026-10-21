; Copyable low SIPI page plus high-half AP runtime. Never run from host tests.
; BSP owns INIT/SIPI sequencing and low-page/identity-map lifetime.
bits 64
default rel
%include "smp.inc"
%ifndef P1_TEST
%define P1_TEST 0
%endif
%ifndef SMP_TEST_NO_INVALIDATE
%define SMP_TEST_NO_INVALIDATE 0
%endif
%if SMP_TEST_NO_INVALIDATE && !P1_TEST
%error SMP invalidation fault injection is test-only
%endif
extern kernel_exception_panic
extern sched_parallel_idle
extern user_smp_try_handoff,sched_parallel_timer_entry,sched_parallel_ipi_entry
%ifdef RUNTIME_LEVEL
%if RUNTIME_LEVEL >= 5
%define SMP_ALIAS_HOOK 1
extern alias_ap_command
%endif
%endif
%ifndef SMP_ALIAS_HOOK
%define SMP_ALIAS_HOOK 0
%endif
global smp_prepare_trampoline
global smp_send_ipi
global smp_ap_entry
global smp_ap_default_main
global smp_ap_idle
global smp_ping_entry
global smp_stop_entry
global smp_spurious_entry
global smp_trampoline_start
global smp_trampoline_end
global smp_trampoline_pm
global smp_trampoline_long
global smp_trampoline_context
global smp_trampoline_stage
global smp_trampoline_cr3
global smp_trampoline_pm_pointer
global smp_trampoline_lm_pointer
global smp_trampoline_gdtr
global smp_capture_mtrrs,smp_mtrr_snapshot
global smp_tlb_entry,smp_tlb_mailboxes,smp_mailboxes

section .text
; Pure unsafe SysV u64 prepare(dst4096, lowPA, CR3, Context*). No privileged
; instructions: native test can inspect the exact bytes/relocation-free patch.
smp_prepare_trampoline:
    push rbx
    push r12
    push r13
    push r14
    test rdi, rdi
    jz .bad
    cmp rsi, 4096
    jb .bad
    cmp rsi, 0xa0000
    jae .bad
    test rsi, 4095
    jnz .bad
    test rdx, rdx
    jz .bad
    test rdx, 4095
    jnz .bad
    mov rax, rdx
    shr rax, 32
    jnz .bad
    mov rax, 0xffff800000000000
    cmp rcx, rax
    jb .bad
    test rcx, 63
    jnz .bad
    mov rbx, rdi
    mov r12, rsi
    mov r13, rdx
    mov r14, rcx
    lea rsi, [rel smp_trampoline_start]
    mov ecx, 4096
    cld
    rep movsb
    mov [rbx + smp_trampoline_cr3 - smp_trampoline_start], r13d
    mov [rbx + smp_trampoline_context - smp_trampoline_start], r14
    lea rax, [rel smp_ap_entry]
    mov [rbx + trampoline_entry - smp_trampoline_start], rax
    lea eax, [r12d + smp_trampoline_pm - smp_trampoline_start]
    mov [rbx + smp_trampoline_pm_pointer - smp_trampoline_start], eax
    lea eax, [r12d + smp_trampoline_long - smp_trampoline_start]
    mov [rbx + smp_trampoline_lm_pointer - smp_trampoline_start], eax
    lea eax, [r12d + trampoline_gdt - smp_trampoline_start]
    mov [rbx + smp_trampoline_gdtr - smp_trampoline_start + 2], eax
    xor eax, eax
    jmp .done
.bad:
    mov eax, SMP_ERR_ARGUMENT
.done:
    pop r14
    pop r13
    pop r12
    pop rbx
    ret

; Unsafe SysV u64 send(LAPIC_UC_VA, apicID, command, poll_limit). External IRQs
; off and same BSP serializes ICR. No CR/MSR access; safe native MMIO model.
; Accepted: INIT assert/deassert, SIPI nonzero valid low vector, fixed IPI>=32.
smp_send_ipi:
    test rdi, rdi
    jz .argument
    test rdi, 4095
    jnz .argument
    cmp rsi, 255
    ja .argument
    test rcx, rcx
    jz .argument
    cmp edx, 0xc500
    je .accepted
    cmp edx, 0x8500
    je .accepted
    mov eax, edx
    and eax, ~255
    cmp eax, 0x600
    jne .fixed
    mov eax, edx
    and eax, 255
    cmp eax, 1
    jb .argument
    cmp eax, 0x9f
    ja .argument
    jmp .accepted
.fixed:
    cmp edx, 32
    jb .argument
    cmp edx, 254
    ja .argument
.accepted:
    mov r8, rcx
.before:
    test dword [rdi + 0x300], 1 << 12
    jz .available
    pause
    dec r8
    jnz .before
    mov eax, SMP_ERR_TIMEOUT
    ret
.available:
    mov dword [rdi + 0x280], 0
    mov eax, [rdi + 0x280]
    shl esi, 24
    mov [rdi + 0x310], esi
    mov [rdi + 0x300], edx
    mfence
.after:
    test dword [rdi + 0x300], 1 << 12
    jz .delivered
    pause
    dec rcx
    jnz .after
    mov eax, SMP_ERR_TIMEOUT
    ret
.delivered:
    mov eax, [rdi + 0x280]
    and eax, 0xef
    jnz .error
    xor eax, eax
    ret
.error:
    mov eax, SMP_ERR_APIC
    ret
.argument:
    mov eax, SMP_ERR_ARGUMENT
    ret

; RDI=high Context*. First high-half instruction after the copied low page.
; Root has validated all fields, disjoint tables/stacks/guards, shared CR3, PAT
; and firmware MTRRs. Build every descriptor before enabling any AP IRQ.
smp_ap_entry:
    cli
    cld
    cmp [rdi + SmpContext.self], rdi
    jne smp_ap_halt
    mov r12, rdi
    mov rsp, [r12 + SmpContext.stack_top]
    and rsp, -16
    xor ebp, ebp
    cmp qword [r12 + SmpContext.state], SMP_STARTING
    jne smp_ap_aborted
    mov eax, 1
    cpuid
    shr ebx, 24
    cmp rbx, [r12 + SmpContext.apic_id]
    jne smp_ap_feature
    test edx, 1 << 9
    jz smp_ap_feature
    mov r13d, ecx
    mov r14d, edx
    mov eax, edx
    and eax, 0x070012c4            ; FXSR/SSE/SSE2, MTRR, APIC, PAE, MCE, DE
    cmp eax, 0x070012c4
    jne smp_ap_feature
    mov rax, [r12 + SmpContext.cr4]
    test eax, 1 << 18
    jz .leaf7
    test r13d, 1 << 26
    jz smp_ap_feature
    cmp qword [r12+SmpContext.xcr0],7
    jne .xsave_leaf
    test r13d,1<<28
    jz smp_ap_feature
.xsave_leaf:
    xor eax, eax
    cpuid
    cmp eax, 0xd
    jb smp_ap_feature
    mov eax, 0xd
    xor ecx, ecx
    cpuid
    mov rcx,[r12+SmpContext.xcr0]
    and rax,rcx
    cmp rax,rcx
    jne smp_ap_feature
.leaf7:
    mov rax, [r12 + SmpContext.cr4]
    and eax, 0x300800
    jz .controls
    mov r15, rax
    xor eax, eax
    cpuid
    cmp eax, 7
    jb smp_ap_feature
    mov eax, 7
    xor ecx, ecx
    cpuid
    cmp qword [r12+SmpContext.xcr0],7
    jne .avx_checked
    test ebx,1<<5
    jz smp_ap_feature
.avx_checked:
    test r15d, 1 << 20
    jz .not_smep
    test ebx, 1 << 7
    jz smp_ap_feature
.not_smep:
    test r15d, 1 << 21
    jz .not_smap
    test ebx, 1 << 20
    jz smp_ap_feature
.not_smap:
    test r15d, 1 << 11
    jz .controls
    test ecx, 1 << 2
    jz smp_ap_feature
.controls:
    mov rax, [r12 + SmpContext.cr0]
    or rax, 1 << 30
    and rax, ~(1 << 29)
    mov cr0, rax
    wbinvd
    ; INIT may reset an AP's MTRR default type. Synchronize the BSP snapshot
    ; and verify every register while CD=1, before enabling normal caching.
    call smp_check_mtrrs
    test eax,eax
    jnz smp_ap_feature
    mov rax, [r12 + SmpContext.cr4]
    mov cr4, rax
    test eax, 1 << 18
    jz .no_xsave
    xor ecx, ecx
    mov rax, [r12 + SmpContext.xcr0]
    mov rdx, rax
    shr rdx, 32
    xsetbv
.no_xsave:
    mov rax, [r12 + SmpContext.pat]
    mov rdx, rax
    shr rdx, 32
    mov ecx, 0x277
    wrmsr
    wbinvd
    mov rax,[r12+SmpContext.cr0]
    mov cr0,rax
    mov rax, [r12 + SmpContext.efer]
    mov rdx, rax
    shr rdx, 32
    mov ecx, 0xc0000080
    wrmsr
    xor eax, eax
    mov edx, eax
    mov ecx, 0xc0000100
    wrmsr
    mov ecx, 0xc0000102
    wrmsr
    mov rax, r12
    mov rdx, rax
    shr rdx, 32
    mov ecx, 0xc0000101
    wrmsr
    fninit
    ldmxcsr [rel smp_mxcsr]
    mov rdi, [r12 + SmpContext.tss]
    xor eax, eax
    mov ecx, CPU_TSS_SIZE
    rep stosb
    mov rdi, [r12 + SmpContext.tss]
    mov rax, [r12 + SmpContext.stack_top]
    mov [rdi + CPU_TSS_RSP0], rax
    mov rax, [r12 + SmpContext.df_top]
    mov [rdi + CPU_TSS_IST1], rax
    mov rax, [r12 + SmpContext.nmi_top]
    mov [rdi + CPU_TSS_IST2], rax
    mov rax, [r12 + SmpContext.exception_top]
    mov [rdi + CPU_TSS_IST3], rax
    mov word [rdi + CPU_TSS_IOMAP_BASE], CPU_TSS_SIZE
    mov rdi, [r12 + SmpContext.gdt]
    mov qword [rdi], 0
    mov rax, CPU_GDT_CODE_DESCRIPTOR
    mov [rdi + 8], rax
    mov rax, CPU_GDT_DATA_DESCRIPTOR
    mov [rdi + 16], rax
    mov rax, [r12 + SmpContext.tss]
    lea rdi, [rdi + CPU_TSS_SELECTOR]
    mov word [rdi], CPU_TSS_SIZE - 1
    mov word [rdi + 2], ax
    shr rax, 16
    mov byte [rdi + 4], al
    mov byte [rdi + 5], CPU_TSS_AVAILABLE
    mov byte [rdi + 6], 0
    shr rax, 8
    mov byte [rdi + 7], al
    shr rax, 8
    mov dword [rdi + 8], eax
    mov dword [rdi + 12], 0
    mov rdi, [r12 + SmpContext.idt]
    lea rsi, [rel smp_stub_table]
    xor ecx, ecx
.idt:
    lodsq
    mov edx, CPU_IST_EXCEPTION
    cmp ecx, 8
    jne .not_df
    mov edx, CPU_IST_DF
.not_df:
    cmp ecx, 2
    jne .not_nmi
    mov edx, CPU_IST_NMI
.not_nmi:
    cmp ecx, SMP_STOP_VECTOR
    jne .not_stop
    lea rax, [rel smp_stop_entry]
    xor edx, edx
.not_stop:
    cmp ecx, SMP_PING_VECTOR
    jne .not_ping
    lea rax, [rel smp_ping_entry]
    xor edx, edx
.not_ping:
    cmp ecx,SMP_TLB_VECTOR
    jne .not_tlb
    lea rax,[rel smp_tlb_entry]
    xor edx,edx
.not_tlb:
    cmp ecx,0x40
    jne .not_parallel_timer
    lea rax,[rel sched_parallel_timer_entry]
    xor edx,edx
.not_parallel_timer:
    cmp ecx,0xf3
    jne .not_parallel_ipi
    lea rax,[rel sched_parallel_ipi_entry]
    xor edx,edx
.not_parallel_ipi:
    cmp ecx, 255
    jne .gate
    lea rax, [rel smp_spurious_entry]
    xor edx, edx
.gate:
    mov word [rdi], ax
    mov word [rdi + 2], CPU_KERNEL_CODE_SELECTOR
    mov byte [rdi + 4], dl
    mov byte [rdi + 5], CPU_IDT_INTERRUPT_GATE
    shr rax, 16
    mov word [rdi + 6], ax
    shr rax, 16
    mov dword [rdi + 8], eax
    mov dword [rdi + 12], 0
    add rdi, 16
    inc ecx
    cmp ecx, 256
    jb .idt
    sub rsp, 32
    mov word [rsp], CPU_GDT_SIZE - 1
    mov rax, [r12 + SmpContext.gdt]
    mov [rsp + 2], rax
    lgdt [rsp]
    push qword CPU_KERNEL_CODE_SELECTOR
    lea rax, [rel .private_cs]
    push rax
    retfq
.private_cs:
    mov ax, CPU_KERNEL_DATA_SELECTOR
    mov ds, ax
    mov es, ax
    mov ss, ax
    xor eax, eax
    mov fs, ax
    mov gs, ax
    ; Loading the null GS selector may clear its base: restore AFTER selectors.
    mov rax, r12
    mov rdx, rax
    shr rdx, 32
    mov ecx, 0xc0000101
    wrmsr
    mov ax, CPU_TSS_SELECTOR
    ltr ax
    mov word [rsp], CPU_IDT_SIZE - 1
    mov rax, [r12 + SmpContext.idt]
    mov [rsp + 2], rax
    lidt [rsp]
    add rsp, 32
    mov ecx, 0x1b
    rdmsr
    test edx, edx
    jnz smp_ap_feature
    test eax, 1 << 8
    jnz smp_ap_feature
    test eax, 1 << 10
    jnz smp_ap_feature
    mov ebx, eax
    and ebx, 0xfffff000
    cmp rbx, [r12 + SmpContext.lapic_pa]
    jne smp_ap_feature
    or eax, 1 << 11
    wrmsr
    mov rbx, [r12 + SmpContext.lapic_va]
    mov eax, [rbx + 0x30]
    cmp al, 0x10
    jb smp_ap_feature
    shr eax, 16
    and eax, 255
    cmp eax, 3
    jb smp_ap_feature
    cmp eax, 6
    ja smp_ap_feature
    mov dword [rbx + 0x320], 0x100ff
    mov dword [rbx + 0x350], 0x100ff
    mov dword [rbx + 0x360], 0x100ff
    mov dword [rbx + 0x370], 0x100ff
    cmp eax, 4
    jb .no_perf
    mov dword [rbx + 0x340], 0x100ff
.no_perf:
    cmp eax, 5
    jb .no_thermal
    mov dword [rbx + 0x330], 0x100ff
.no_thermal:
    cmp eax, 6
    jb .no_cmci
    mov dword [rbx + 0x2f0], 0x100ff
.no_cmci:
    mov dword [rbx + 0x80], 0
    mov dword [rbx + 0x380], 0
    mov eax, [rbx + 0xf0]
    and eax, ~0x11ff
    or eax, 0x1ff
    mov [rbx + 0xf0], eax
    mfence
    mov eax, [rbx + 0xf0]
    and eax, 0x11ff
    cmp eax, 0x1ff
    jne smp_ap_feature
    cmp dword [rbx + 0x80], 0
    jne smp_ap_feature
    mov rax, cr3
    cmp rax, [r12 + SmpContext.cr3]
    jne smp_ap_feature
    mov rax, cr0
    cmp rax, [r12 + SmpContext.cr0]
    jne smp_ap_feature
    mov rax, cr4
    cmp rax, [r12 + SmpContext.cr4]
    jne smp_ap_feature
    test eax,1<<18
    jz .xcr_checked
    xor ecx,ecx
    xgetbv
    shl rdx,32
    or rax,rdx
    cmp rax,[r12+SmpContext.xcr0]
    jne smp_ap_feature
.xcr_checked:
%macro SMP_CHECK_MSR 2
    mov ecx, %1
    rdmsr
    shl rdx, 32
    or rax, rdx
    cmp rax, [r12 + SmpContext.%2]
    jne smp_ap_feature
%endmacro
    SMP_CHECK_MSR 0x277, pat
    SMP_CHECK_MSR 0xc0000080, efer
    SMP_CHECK_MSR 0xc0000101, self
    sub rsp, 32
    sgdt [rsp]
    sidt [rsp + 16]
    mov rax, [r12 + SmpContext.gdt]
    cmp word [rsp], 39
    jne smp_ap_feature
    cmp [rsp + 2], rax
    jne smp_ap_feature
    mov rax, [r12 + SmpContext.idt]
    cmp word [rsp + 16], 4095
    jne smp_ap_feature
    cmp [rsp + 18], rax
    jne smp_ap_feature
    str ax
    cmp ax, CPU_TSS_SELECTOR
    jne smp_ap_feature
    add rsp, 32
    pushfq
    pop rax
    test eax, 0x60600
    jnz smp_ap_feature
    mov rax, [r12 + SmpContext.epoch]
    mov [r12 + SmpContext.online_epoch], rax
    mov eax, SMP_STARTING
    mov edx, SMP_ONLINE
    lock cmpxchg [r12 + SmpContext.state], rdx
    jne smp_ap_aborted
    mov rdi, r12
    call [r12 + SmpContext.main]
global smp_ap_idle_after_hlt
smp_ap_idle:
    call user_smp_try_handoff
    call sched_parallel_idle
    sti
    hlt
smp_ap_idle_after_hlt:
    cli
    jmp smp_ap_idle
smp_ap_feature:
    mov qword [r12 + SmpContext.last_error], SMP_ERR_FEATURE
    jmp smp_ap_halt
smp_ap_aborted:
    mov qword [r12 + SmpContext.last_error], SMP_ERR_ABORTED
smp_ap_halt:
    cli
.halt:
    hlt
    jmp .halt
smp_ap_default_main:
    ret

; BSP-only, IF0. No MTRR is changed. All APs validate this immutable snapshot
; while CD=1, so differing firmware cache configuration fails closed.
smp_capture_mtrrs:
    push rbx
    mov eax,1
    cpuid
    test edx,1<<12
    jz .bad
    mov eax,0x80000000
    cpuid
    cmp eax,0x80000008
    jb .bad
    mov eax,0x80000008
    cpuid
    movzx eax,al
    cmp eax,32
    jb .bad
    cmp eax,52
    ja .bad
    mov [rel smp_mtrr_snapshot+376],rax
    cmp qword [rel smp_mtrr_snapshot],0
    jne .bad
    mov ecx,0xfe
    rdmsr
    shl rdx,32
    or rax,rdx
    mov [rel smp_mtrr_snapshot+8],rax
    movzx r8d,al
    cmp r8d,16
    ja .bad
    mov [rel smp_mtrr_snapshot+24],r8
    mov ecx,0x2ff
    rdmsr
    shl rdx,32
    or rax,rdx
    mov [rel smp_mtrr_snapshot+16],rax
    shl r8d,1
    xor r9d,r9d
    lea r10,[rel smp_mtrr_snapshot+32]
.variable:
    cmp r9d,r8d
    jae .fixed_begin
    lea ecx,[r9d+0x200]
    rdmsr
    shl rdx,32
    or rax,rdx
    mov [r10+r9*8],rax
    inc r9d
    jmp .variable
.fixed_begin:
    test qword [rel smp_mtrr_snapshot+8],1<<8
    jz .ready
    xor r9d,r9d
    lea r10,[rel smp_fixed_msr_indices]
    lea r11,[rel smp_mtrr_snapshot+288]
.fixed:
    mov ecx,[r10+r9*4]
    rdmsr
    shl rdx,32
    or rax,rdx
    mov [r11+r9*8],rax
    inc r9d
    cmp r9d,11
    jb .fixed
.ready:
    mov qword [rel smp_mtrr_snapshot],1
    xor eax,eax
    pop rbx
    ret
.bad:
    mov eax,SMP_ERR_FEATURE
    pop rbx
    ret

smp_check_mtrrs:
    push rbx
    cmp qword [rel smp_mtrr_snapshot],1
    jne .bad
    mov ecx,0xfe
    rdmsr
    shl rdx,32
    or rax,rdx
    cmp rax,[rel smp_mtrr_snapshot+8]
    jne .bad
    mov eax,0x80000008
    cpuid
    movzx eax,al
    cmp rax,[rel smp_mtrr_snapshot+376]
    jne .bad
    ; Intel SDM MTRR initialization sequence: caches disabled, WBINVD,
    ; disable MTRRs, load variable/fixed registers, restore default/E/FE.
    mov ecx,0x2ff
    rdmsr
    and eax,~0xc00
    wrmsr
    mov r8,[rel smp_mtrr_snapshot+24]
    shl r8d,1
    xor r9d,r9d
    lea r10,[rel smp_mtrr_snapshot+32]
.copy_variable:
    cmp r9d,r8d
    jae .copy_fixed_begin
    mov rax,[r10+r9*8]
    mov rdx,rax
    shr rdx,32
    lea ecx,[r9d+0x200]
    wrmsr
    inc r9d
    jmp .copy_variable
.copy_fixed_begin:
    test qword [rel smp_mtrr_snapshot+8],1<<8
    jz .copy_default
    xor r9d,r9d
    lea r10,[rel smp_fixed_msr_indices]
    lea r11,[rel smp_mtrr_snapshot+288]
.copy_fixed:
    mov rax,[r11+r9*8]
    mov rdx,rax
    shr rdx,32
    mov ecx,[r10+r9*4]
    wrmsr
    inc r9d
    cmp r9d,11
    jb .copy_fixed
.copy_default:
    mov rax,[rel smp_mtrr_snapshot+16]
    mov rdx,rax
    shr rdx,32
    mov ecx,0x2ff
    wrmsr
    wbinvd
    mov ecx,0x2ff
    rdmsr
    shl rdx,32
    or rax,rdx
    cmp rax,[rel smp_mtrr_snapshot+16]
    jne .bad
    mov r8,[rel smp_mtrr_snapshot+24]
    shl r8d,1
    xor r9d,r9d
    lea r10,[rel smp_mtrr_snapshot+32]
.variable:
    cmp r9d,r8d
    jae .fixed_begin
    lea ecx,[r9d+0x200]
    rdmsr
    shl rdx,32
    or rax,rdx
    cmp rax,[r10+r9*8]
    jne .bad
    inc r9d
    jmp .variable
.fixed_begin:
    test qword [rel smp_mtrr_snapshot+8],1<<8
    jz .ok
    xor r9d,r9d
    lea r10,[rel smp_fixed_msr_indices]
    lea r11,[rel smp_mtrr_snapshot+288]
.fixed:
    mov ecx,[r10+r9*4]
    rdmsr
    shl rdx,32
    or rax,rdx
    cmp rax,[r11+r9*8]
    jne .bad
    inc r9d
    cmp r9d,11
    jb .fixed
.ok:
    xor eax,eax
    pop rbx
    ret
.bad:
    mov eax,SMP_ERR_FEATURE
    pop rbx
    ret

; AP kernel-only GS ABI. No allocations, callbacks, SIMD or shared runqueue.
smp_ping_entry:
    push rax
    push rdx
%if SMP_ALIAS_HOOK
    push rcx
    push rsi
    push rdi
    push r8
    push r9
    push r10
    push r11
    push rbp
    mov rbp,rsp
    and rsp,-16
    cld
    call alias_ap_command
    mov rsp,rbp
    pop rbp
    pop r11
    pop r10
    pop r9
    pop r8
    pop rdi
    pop rsi
    pop rcx
%endif
    cld
    pushfq
    and qword [rsp], ~(1 << 18)
    popfq
    inc qword [gs:SmpContext.irq_count]
    cmp qword [gs:SmpContext.state], SMP_ONLINE
    jne .eoi
    mov rax, [gs:SmpContext.ping_request]
    cmp rax, [gs:SmpContext.ping_ack]
    jbe .eoi
    mov [gs:SmpContext.ping_ack], rax
.eoi:
    mov rdx, [gs:SmpContext.lapic_va]
    mov dword [rdx + 0xb0], 0
    pop rdx
    pop rax
    iretq
smp_stop_entry:
    cli
    push rax
    push rdx
    mov rax, [gs:SmpContext.lapic_va]
    mov dword [rax + 0xb0], 0
    inc qword [gs:SmpContext.irq_count]
    cmp qword [gs:SmpContext.state], SMP_STOPPING
    jne .stale
    mov rax, [gs:SmpContext.stop_request]
    cmp rax, [gs:SmpContext.stop_ack]
    jbe .stale
    mov [gs:SmpContext.stop_ack], rax
    mfence
    mov eax, SMP_STOPPING
    mov edx, SMP_STOPPED
    lock cmpxchg [gs:SmpContext.state], rdx
    jmp smp_ap_halt
.stale:
    pop rdx
    pop rax
    iretq
smp_spurious_entry:
    iretq

smp_mailboxes:
    lea rax,[rel smp_tlb_mailboxes]
    ret
; BSP publishes payload before sequence. ACK is released only after INVLPG/
; CR3 reload finishes. Context policy excludes PCID/PGE, so full reload also
; invalidates every paging-structure cache used by this AP's shared root.
smp_tlb_entry:
    push rax
    push rdx
    push rcx
    push r8
    push r9
    cld
    mov rax,[gs:SmpContext.logical_id]
    cmp rax,16
    jae .eoi
    shl rax,6
    lea rdx,[rel smp_tlb_mailboxes]
    add rdx,rax
    mov r8,[rdx+SmpMailbox.sequence]
    cmp r8,[rdx+SmpMailbox.ack]
    jbe .eoi
    mov rcx,[rdx+SmpMailbox.scope]
    mov rax,[rdx+SmpMailbox.virtual]
    cmp rcx,1
    je .full
    cmp rcx,2
    je .probe
    test rcx,rcx
    jnz .bad
%if SMP_TEST_NO_INVALIDATE
    inc qword [rdx+SmpMailbox.reserved]
%else
    invlpg [rax]
%endif
    jmp .ack
.full:
    mov rax,cr3
    mov cr3,rax
    jmp .ack
.probe:
    mov r9,[rax]
    mov [rdx+SmpMailbox.observed],r9
    jmp .ack
.bad:
    mov qword [rdx+SmpMailbox.fault],SMP_ERR_ARGUMENT
.ack:
    mfence
    mov [rdx+SmpMailbox.ack],r8
    inc qword [gs:SmpContext.irq_count]
.eoi:
    mov rax,[gs:SmpContext.lapic_va]
    mov dword [rax+0xb0],0
    pop r9
    pop r8
    pop rcx
    pop rdx
    pop rax
    iretq

; Dedicated fatal stubs preserve the existing 184B panic contract. AP stacks
; are NOT silently added to the BSP's trusted unwind ranges.
%assign vector 0
%rep 256
smp_fatal_%+vector:
%if vector != 8 && vector != 10 && vector != 11 && vector != 12 && vector != 13 && vector != 14 && vector != 17 && vector != 21 && vector != 29 && vector != 30
    push qword 0
%endif
    push qword vector
    jmp smp_fatal_common
%assign vector vector+1
%endrep
smp_fatal_common:
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
    mov rdi, rsp
    and rsp, -16
    cli
    cld
    pushfq
    and qword [rsp], ~(1 << 18)
    popfq
    call kernel_exception_panic
    ud2

section .rodata
align 16
smp_mxcsr: dd 0x1f80
smp_fixed_msr_indices: dd 0x250,0x258,0x259,0x268,0x269,0x26a,0x26b,0x26c,0x26d,0x26e,0x26f
%if __NASM_MAJOR__ >= 3
[warning push]
[warning -reloc-abs-qword]
%endif
smp_stub_table:
%assign vector 0
%rep 256
    dq smp_fatal_%+vector
%assign vector vector+1
%endrep
%if __NASM_MAJOR__ >= 3
[warning pop]
%endif

; Fully self-contained 4096-byte page: no external relocations in this region.
; Before paging, writes only its stage word; after PG=1 it performs NO writes
; to the low page, so root can map the identity page supervisor RX (not RWX).
align 4096
bits 16
smp_trampoline_start:
    cli
    cld
    mov ax, cs
    mov ds, ax
    mov es, ax
    xor ebx, ebx
    mov bx, ax
    shl ebx, 4
    mov dword [smp_trampoline_stage-smp_trampoline_start], 1
    o32 lgdt [smp_trampoline_gdtr-smp_trampoline_start]
    mov eax, cr0
    or eax, 1
    mov cr0, eax
    jmp dword far [smp_trampoline_pm_pointer-smp_trampoline_start]
bits 32
smp_trampoline_pm:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov dword [ebx+smp_trampoline_stage-smp_trampoline_start], 2
    mov esi, ebx
    mov eax, 0x80000000
    cpuid
    cmp eax, 0x80000001
    jb trampoline_failed
    mov eax, 0x80000001
    cpuid
    and edx, (1 << 20) | (1 << 29)
    cmp edx, (1 << 20) | (1 << 29)
    jne trampoline_failed
    mov eax, 0x20
    mov cr4, eax
    mov ecx, 0xc0000080
    rdmsr
    or eax, (1 << 8) | (1 << 11)
    wrmsr
    ; CPUID overwrites EBX; ESI retains the real-mode-computed physical base.
    ; No CALL/PUSH is permitted before the trusted long-mode stack is loaded.
    mov ebx, esi
    mov eax, [ebx+smp_trampoline_cr3-smp_trampoline_start]
    mov cr3, eax
    mov eax, cr0
    or eax, 0x80000000
    mov cr0, eax
    jmp far [ebx+smp_trampoline_lm_pointer-smp_trampoline_start]
trampoline_failed:
    cli
.halt:
    hlt
    jmp .halt
bits 64
smp_trampoline_long:
    mov edi, ebx
    mov rax, [rdi+trampoline_entry-smp_trampoline_start]
    mov rdi, [rdi+smp_trampoline_context-smp_trampoline_start]
    jmp rax
    times 0x300-($-smp_trampoline_start) db 0
trampoline_gdt:
    dq 0,0x00cf9b000000ffff,0x00cf93000000ffff,0x00af9b000000ffff
smp_trampoline_gdtr:
    dw 31
    dd 0
smp_trampoline_pm_pointer:
    dd 0
    dw 8
smp_trampoline_lm_pointer:
    dd 0
    dw 0x18
smp_trampoline_cr3: dd 0
smp_trampoline_context: dq 0
trampoline_entry: dq 0
smp_trampoline_stage: dd 0
    times 4096-($-smp_trampoline_start) db 0
smp_trampoline_end:
bits 64

section .bss
align 8, resb 1
smp_mtrr_snapshot: resq 48
align 64, resb 1
smp_tlb_mailboxes: resb 16*SmpMailbox_size
