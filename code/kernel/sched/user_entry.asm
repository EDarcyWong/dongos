; Isolated CPL3 SMP architecture candidate. Not selected by production builds.
; Every context is arena owned. No global original root, UserCpu or xstate.
bits 64
default rel
%include "user_entry.inc"
extern dong_user_smp_event
extern dong_user_smp_return
extern dong_user_smp_idle
extern sched_xstate_save,sched_xstate_restore
extern user_smp_arch_enable_pcid
global user_smp_prepare_tables,user_smp_interrupt_frame
global user_smp_activate,user_smp_syscall_entry,user_smp_irq_common
global user_smp_iret,user_smp_idle,user_smp_fail
global user_smp_entry_stubs,user_smp_entry_stubs_end
global user_smp_entry_table,user_smp_entry_table_end
global user_smp_to_kernel
section .text
; Pure native-testable table construction. Header owns disjoint, mapped buffers
; previously validated by user_entry_plan. Caller excludes active descriptors.
user_smp_prepare_tables:
    push rbx
    push r12
    mov r12,rdi
    mov rdi,[r12+UserEntryCpu.gdt]
    xor eax,eax
    mov ecx,8
    cld
    rep stosq
    mov rdi,[r12+UserEntryCpu.gdt]
    mov rax,CPU_GDT_CODE_DESCRIPTOR
    mov [rdi+8],rax
    mov rax,CPU_GDT_DATA_DESCRIPTOR
    mov [rdi+16],rax
    mov rax,0x00cff3000000ffff
    mov [rdi+0x28],rax
    mov rax,0x00affb000000ffff
    mov [rdi+0x30],rax
    mov rax,[r12+UserEntryCpu.tss]
    add rdi,CPU_TSS_SELECTOR
    mov word [rdi],CPU_TSS_SIZE-1
    mov word [rdi+2],ax
    shr rax,16
    mov byte [rdi+4],al
    mov byte [rdi+5],CPU_TSS_AVAILABLE
    mov byte [rdi+6],0
    shr rax,8
    mov byte [rdi+7],al
    shr rax,8
    mov dword [rdi+8],eax
    mov dword [rdi+12],0
    mov rdi,[r12+UserEntryCpu.tss]
    xor eax,eax
    mov ecx,CPU_TSS_SIZE
    rep stosb
    mov rdi,[r12+UserEntryCpu.tss]
    mov rax,[r12+UserCpu.kernel_stack]
    mov [rdi+CPU_TSS_RSP0],rax
    mov rax,[r12+UserEntryCpu.df_top]
    mov [rdi+CPU_TSS_IST1],rax
    mov rax,[r12+UserEntryCpu.nmi_top]
    mov [rdi+CPU_TSS_IST2],rax
    mov rax,[r12+UserEntryCpu.exception_top]
    mov [rdi+CPU_TSS_IST3],rax
    mov word [rdi+CPU_TSS_IOMAP_BASE],CPU_TSS_SIZE
    mov rdi,[r12+UserEntryCpu.idt]
    lea rsi,[rel user_smp_entry_table]
    xor ebx,ebx
.gate:
    lodsq
    mov word [rdi],ax
    mov word [rdi+2],CPU_KERNEL_CODE_SELECTOR
    ; Normal IRQs use RSP0, not a shared IST that a suspended reader could reuse.
    xor edx,edx
    cmp ebx,8
    jne .not_df
    mov edx,CPU_IST_DF
.not_df:
    cmp ebx,2
    jne .not_nmi
    mov edx,CPU_IST_NMI
.not_nmi:
    mov byte [rdi+4],dl
    mov byte [rdi+5],CPU_IDT_INTERRUPT_GATE
    shr rax,16
    mov word [rdi+6],ax
    shr rax,16
    mov dword [rdi+8],eax
    mov dword [rdi+12],0
    add rdi,16
    inc ebx
    cmp ebx,256
    jb .gate
    xor eax,eax
    pop r12
    pop rbx
    ret

; Pure exact hardware-frame conversion: (out, ExceptionContext*, root, count).
; The raw handler separately reads FS and user GS and fills the two zero slots.
user_smp_interrupt_frame:
    push rdi
    mov r8,rdx
    mov r9,rcx
    lea rsi,[rsi+8]
    mov ecx,15
    cld
    rep movsq
    mov rax,[rsi+16]
    mov [rdi],rax                   ; RIP
    mov rax,[rsi+32]
    mov [rdi+8],rax                 ; hardware DF/RF retained
    mov rax,[rsi+40]
    mov [rdi+16],rax                ; interrupted RSP
    mov [rdi+24],r8
    xor eax,eax
    mov [rdi+32],rax
    mov [rdi+40],rax
    mov [rdi+48],rax
    mov [rdi+56],r9
    mov [rdi+64],rax
    mov [rdi+72],rax
    pop rdi
    ret

; IF0, high-half validated header, trusted original kernel root. All tables and
; every stack must already be supervisor WB RW/NX, mapped in every live root.
; Activation is one way: an unexpected hardware inconsistency is fail-stop.
user_smp_activate:
    push rbx
    push r12
    sub rsp,24
    mov r12,rdi
    pushfq
    pop rax
    test eax,0x60600
    jnz .reject
    mov rax,0xffff800000000000
    cmp r12,rax
    jb .reject
    test r12,63
    jnz .reject
    cmp qword [r12+UserEntryCpu.ready],1
    jne .reject
    mov rax,cr3
    cmp rax,[r12+UserCpu.original_cr3]
    jne .reject
    mov rax,cr4
    test rax,(1<<7)|(1<<17)|(1<<16) ; PGE/PCIDE/FSGSBASE policy
    jnz .reject
    mov eax,0x80000000
    cpuid
    cmp eax,0x80000001
    jb .reject
    mov eax,0x80000001
    cpuid
    test edx,1<<11
    jz .reject
    mov word [rsp],55
    mov rax,[r12+UserEntryCpu.gdt]
    mov [rsp+2],rax
    lgdt [rsp]
    push qword CPU_KERNEL_CODE_SELECTOR
    lea rax,[rel .cs]
    push rax
    retfq
.cs:
    mov ax,CPU_KERNEL_DATA_SELECTOR
    mov ds,ax
    mov es,ax
    mov ss,ax
    xor eax,eax
    mov fs,ax
    mov gs,ax
    mov ax,CPU_TSS_SELECTOR
    ltr ax
    mov word [rsp],4095
    mov rax,[r12+UserEntryCpu.idt]
    mov [rsp+2],rax
    lidt [rsp]
%macro ENTRY_WRMSR 2
    mov rax,%2
    mov rdx,rax
    shr rdx,32
    mov ecx,%1
    wrmsr
%endmacro
    ENTRY_WRMSR 0xc0000100,0
    ENTRY_WRMSR 0xc0000102,0
    ENTRY_WRMSR 0xc0000101,r12
    mov ecx,0xc0000080
    rdmsr
    bts eax,0
    wrmsr
    ENTRY_WRMSR 0xc0000081,0x0020000800000000
    lea rax,[rel user_smp_syscall_entry]
    ENTRY_WRMSR 0xc0000082,rax
    ENTRY_WRMSR 0xc0000084,USER_FMASK
    mov rdi,[r12+UserEntryCpu.kernel_xstate]
    call sched_xstate_save
    call user_smp_arch_enable_pcid
    cmp rax,-1
    je user_smp_fail
    call user_smp_record_arch
    mov qword [gs:UserEntryCpu.ready],2
    mov qword [gs:UserCpu.busy],1
    xor eax,eax
    jmp .done
.reject:
    mov eax,USER_ENTRY_ERR
.done:
    add rsp,24
    pop r12
    pop rbx
    ret

; Hardware readback, not copied expected MSR values. Kept in arena for a
; read-only physical oracle on hosts whose HMP register dump omits these MSRs.
user_smp_record_arch:
    sub rsp,40
    mov r8,[gs:UserEntryCpu.kernel_xstate]
    add r8,1024
%macro ENTRY_READBACK 2
    mov ecx,%1
    rdmsr
    shl rdx,32
    or rax,rdx
    mov [r8+UserEntryMetrics.%2],rax
%endmacro
    ENTRY_READBACK 0xc0000101,gs_base
    ENTRY_READBACK 0xc0000102,kernel_gs_base
    ENTRY_READBACK 0xc0000100,fs_base
    ENTRY_READBACK 0xc0000080,efer
    ENTRY_READBACK 0xc0000081,star
    ENTRY_READBACK 0xc0000082,lstar
    ENTRY_READBACK 0xc0000084,fmask
    sgdt [rsp]
    sidt [rsp+16]
    mov rax,[rsp+2]
    mov [r8+UserEntryMetrics.gdtr_base],rax
    movzx eax,word [rsp]
    mov [r8+UserEntryMetrics.gdtr_limit],rax
    mov rax,[rsp+18]
    mov [r8+UserEntryMetrics.idtr_base],rax
    movzx eax,word [rsp+16]
    mov [r8+UserEntryMetrics.idtr_limit],rax
    str ax
    movzx eax,ax
    mov [r8+UserEntryMetrics.tr],rax
    mov rax,cr4
    mov [r8+UserEntryMetrics.cr4],rax
    test rax,1<<18
    jz .no_xsave
    xor ecx,ecx
    xgetbv
    shl rdx,32
    or rax,rdx
    jmp .xcr
.no_xsave:
    xor eax,eax
.xcr:
    mov [r8+UserEntryMetrics.xcr0],rax
    mov rax,[gs:UserEntryCpu.tss]
    mov rax,[rax+CPU_TSS_RSP0]
    mov [r8+UserEntryMetrics.rsp0],rax
    add rsp,40
    ret

; The root must remain tag zero without changing other local PCID bindings.
user_smp_to_kernel:
    mov rax,[gs:UserCpu.original_cr3]
    mov cr3,rax
    ret

user_smp_syscall_entry:
    swapgs
    lfence
    mov [gs:UserCpu.user_stack],rsp
    mov rsp,[gs:UserCpu.kernel_stack]
    sub rsp,208
    USER_SAVE_GPRS rsp
    mov [rsp+UserFrame.rip],rcx
    mov [rsp+UserFrame.rflags],r11
    mov rax,[gs:UserCpu.user_stack]
    mov [rsp+UserFrame.rsp],rax
    mov rax,cr3
    and rax,-4096
    mov [rsp+UserFrame.cr3],rax
    mov qword [rsp+UserFrame.status],0
    mov qword [rsp+UserFrame.exit_code],0
    mov qword [rsp+UserFrame.reserved],0
    inc qword [gs:UserCpu.syscalls]
    mov rax,[gs:UserCpu.syscalls]
    mov [rsp+UserFrame.syscalls],rax
    mov r12,rsp
    mov r13d,USER_ENTRY_SYSCALL
    jmp user_smp_captured

user_smp_irq_common:
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
    ; Paranoid GS selection handles NMI in either SWAPGS window. User GS is
    ; constrained to zero; no untrusted base can resemble the high-half header.
    mov ecx,0xc0000101
    rdmsr
    test edx,edx
    js .kernel_gs
    swapgs
    lfence
.kernel_gs:
    mov ecx,0xc0000101
    rdmsr
    test edx,edx
    jns user_smp_fail_untrusted
    shl rdx,32
    or rax,rdx
    mov r8,USER_ENTRY_MAGIC
    cmp [rax+UserCpu.result],r8
    jne user_smp_fail_untrusted
    cmp qword [rax+UserEntryCpu.ready],2
    jne user_smp_fail_untrusted
    cld
    pushfq
    and qword [rsp],~(1<<18)
    popfq
    cmp qword [rsp+ExceptionContext.vector],2
    je user_smp_fail
    cmp qword [rsp+ExceptionContext.vector],8
    je user_smp_fail
    test qword [rsp+ExceptionContext.cs],3
    jz .kernel_irq
    mov r14,rsp
    mov r13,[r14+ExceptionContext.vector]
    mov rsp,[gs:UserCpu.kernel_stack]
    sub rsp,208
    mov r12,rsp
    mov rdi,rsp
    mov rsi,r14
    mov rdx,cr3
    and rdx,-4096
    mov rcx,[gs:UserCpu.syscalls]
    call user_smp_interrupt_frame
    jmp user_smp_captured
.kernel_irq:
    ; Maskable kernel IRQs are legal only in STI/HLT idle, never with BKL held.
    mov r13,[rsp+ExceptionContext.vector]
    cmp r13,0x40
    je .idle
    cmp r13,USER_SMP_RESCHEDULE_VECTOR
    je .idle
    cmp r13,SMP_PING_VECTOR
    je .idle
    cmp r13,SMP_TLB_VECTOR
    je .idle
    cmp r13,0xf3                   ; drained CPL0 reschedule IPI tail
    je .idle
    cmp r13,0x51
    je .idle
    cmp r13,0x5c
    je .idle
    cmp r13,0x60
    je .idle
    cmp r13,0xff
    jne user_smp_fail
.idle:
    mov rsp,[gs:UserCpu.kernel_stack]
    mov rdi,[gs:UserSmpCpu.logical_id]
    mov rsi,r13
    call dong_user_smp_idle
    cmp rax,-1
    je user_smp_fail
    test rax,rax
    jnz user_smp_return
    jmp user_smp_idle

user_smp_captured:
    cld
    mov [gs:UserEntryCpu.event],r13
    mov [gs:UserEntryCpu.raw_frame],r12
    mov rax,[gs:UserEntryCpu.kernel_xstate]
    inc qword [rax+1024+UserEntryMetrics.user_entries]
    mov [rax+1024+UserEntryMetrics.last_vector],r13
    cmp r13,0x40
    jne .not_timer
    inc qword [rax+1024+UserEntryMetrics.user_timers]
.not_timer:
    mov ecx,0xc0000100
    rdmsr
    shl rdx,32
    or rax,rdx
    mov [r12+UserFrame.fs_base],rax
    mov ecx,0xc0000102
    rdmsr
    shl rdx,32
    or rax,rdx
    mov [r12+UserFrame.gs_base],rax
    ; GPRs are safe on the private RSP0 stack; switch to tag0 before DG/XSAVE.
    call user_smp_to_kernel
    mov rdi,[gs:UserSmpCpu.logical_id]
    mov rsi,r12
    mov rdx,r13
    call dong_user_smp_event
    cmp rax,-1
    je user_smp_fail
    test rax,rax
    jz user_smp_idle
user_smp_return:
    ; This DG callback performs final revocation test/CR3 switch. It returns
    ; false to re-enter the kernel-side selection loop. No DG runs after XRSTOR.
    mov rdi,[gs:UserSmpCpu.logical_id]
    call dong_user_smp_return
    cmp rax,-1
    je user_smp_fail
    test rax,rax
    jz user_smp_idle
    mov rdi,[gs:UserEntryCpu.return_xstate]
    call sched_xstate_restore
    mov rsp,[gs:UserCpu.kernel_stack]
    mov rdi,[gs:UserEntryCpu.returned]
    push qword USER_DATA_SELECTOR
    push qword [rdi+UserFrame.rsp]
    push qword [rdi+UserFrame.rflags]
    push qword USER_CODE_SELECTOR
    push qword [rdi+UserFrame.rip]
    USER_LOAD_GPRS rdi
    swapgs
user_smp_iret:
    iretq
user_smp_idle:
    mov rsp,[gs:UserCpu.kernel_stack]
    mov rdi,[gs:UserSmpCpu.logical_id]
    mov esi,USER_ENTRY_IDLE
    call dong_user_smp_idle
    cmp rax,-1
    je user_smp_fail
    test rax,rax
    jnz user_smp_return
    sti
    hlt
    cli
    jmp user_smp_idle
user_smp_fail:
    cli
    cld
    mov qword [gs:UserEntryCpu.last_error],USER_ENTRY_ERR
    mov rax,[gs:UserEntryCpu.kernel_xstate]
    mov qword [rax+1024+UserEntryMetrics.failed],1
user_smp_fail_untrusted:
    cli
.halt:
    hlt
    jmp .halt

align 16
user_smp_entry_stubs:
%assign V 0
%rep 256
entry_%+V:
%if V != 8 && V != 10 && V != 11 && V != 12 && V != 13 && V != 14 && V != 17 && V != 21 && V != 29 && V != 30
    push qword 0
%endif
    push qword V
    jmp user_smp_irq_common
%assign V V+1
%endrep
user_smp_entry_stubs_end:
section .rodata
%if __NASM_MAJOR__ >= 3
[warning push]
[warning -reloc-abs-qword]
%endif
align 8
user_smp_entry_table:
%assign V 0
%rep 256
    dq entry_%+V
%assign V V+1
%endrep
user_smp_entry_table_end:
%if __NASM_MAJOR__ >= 3
[warning pop]
%endif
