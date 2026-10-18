; BSP-only SYSCALL/SYSRET boundary. IF0 kernel, no SIMD or user-memory access.
; Intel SDM SYSRET/SWAPGS: validate RCX before changing RSP; SWAPGS precedes GS.
bits 64
default rel
%include "cpu.inc"
%include "user_context.inc"
extern dong_user_dispatch
global user_run
global user_syscall_entry
global user_validate_frame
global user_validate_interrupt_frame
global user_frame_size
global user_context_cpu
global user_context_gdt
global user_context_gdt_end
global user_context_last_error
global user_sysret_instruction
global user_iret_instruction
global user_copy_from
global user_copy_to
global user_copy_begin
global user_copy_end
global user_copy_fault
global user_copy_resume
global user_copy_active
global user_copy_source
global user_copy_destination
global user_copy_length
global user_copy_direction
global user_entropy64
global user_current_root
global user_pcid_bind, user_pcid_unbind, user_pcid_operand
global user_pcid_flush_all, user_pcid_invalidate_root
global user_pcid_enabled, user_pcid_bindings, user_pcid_switches, user_pcid_retained
global user_enter_kernel, user_resume_frame

%define MSR_EFER 0xc0000080
%define MSR_STAR 0xc0000081
%define MSR_LSTAR 0xc0000082
%define MSR_FMASK 0xc0000084
%define MSR_FS_BASE 0xc0000100
%define MSR_GS_BASE 0xc0000101
%define MSR_KERNEL_GS_BASE 0xc0000102

section .text
; Pure SysV u64 validator(Frame*). The pointer denotes 200 readable bytes;
; no fields are modified. General GPRs are unrestricted data. RCX/R11 are
; architectural SYSCALL clobbers; return uses the explicit RIP/RFLAGS slots.
user_validate_frame:
    mov r8d, USER_RFLAGS_ALLOWED
    jmp user_validate_common
user_validate_interrupt_frame:
    mov r8d, USER_INTERRUPT_RFLAGS_ALLOWED
user_validate_common:
    xor eax, eax
    test rdi, rdi
    jz .bad
    test rdi, 7
    jnz .bad
    mov rcx, USER_TOP
    mov rdx, [rdi + UserFrame.rip]
    cmp rdx, USER_MIN
    jb .bad
    cmp rdx, rcx
    jae .bad
    mov rdx, [rdi + UserFrame.rsp]
    cmp rdx, USER_MIN
    jb .bad
    cmp rdx, rcx
    jae .bad
    mov rdx, [rdi + UserFrame.rflags]
    test edx, 2
    jz .bad
    mov r9, r8
    not r9
    and rdx, r9
    jnz .bad
    mov rdx, [rdi + UserFrame.cr3]
    test rdx, rdx
    jz .bad
    test rdx, 4095
    jnz .bad
    shr rdx, 32
    jnz .bad
    cmp qword [rdi + UserFrame.fs_base], 0
    jne .bad
    cmp qword [rdi + UserFrame.gs_base], 0
    jne .bad
    cmp qword [rdi + UserFrame.reserved], 0
    jne .bad
    mov eax, 1
.bad:
    ret
user_frame_size:
    mov eax, UserFrame_size
    ret

; Hardware DRNG: SysV bool entropy64(out,source). Outputs remain unchanged
; on unsupported/exhausted CPUs. CPUID gates both instructions independently.
; RDSEED has no bounded-success guarantee; after 32 attempts try RDRAND's
; recommended ten-attempt bounded loop. Never substitute RDTSC or zero.
user_entropy64:
    push rbx
    mov r8, rdi
    mov r9, rsi
    test r8, r8
    jz .failed
    test r9, r9
    jz .failed
    xor eax, eax
    cpuid
    mov r10d, eax
    cmp r10d, 7
    jb .rdrand_caps
    mov eax, 7
    xor ecx, ecx
    cpuid
    test ebx, 1 << 18
    jz .rdrand_caps
    mov ecx, 32
.seed:
    rdseed rax
    jc .seed_ok
    pause
    loop .seed
.rdrand_caps:
    cmp r10d, 1
    jb .failed
    mov eax, 1
    cpuid
    test ecx, 1 << 30
    jz .failed
    mov ecx, 10
.random:
    rdrand rax
    jc .random_ok
    pause
    loop .random
.failed:
    xor eax, eax
    pop rbx
    ret
.seed_ok:
    mov edx, 1
    jmp .publish
.random_ok:
    mov edx, 2
.publish:
    mov [r8], rax
    mov [r9], rdx
    mov eax, 1
    pop rbx
    ret

user_current_root:
    mov rax, cr3
    and rax, -4096
    ret

; Bindings: root, generation, first-use flag; PCID is slot+1 (zero is the
; kernel/unbound context). New generations can never inherit a no-flush flag.
; SysV bool bind(slot, aligned-root-below4G, nonzero-generation), BSP/IF=0.
user_pcid_bind:
    cmp rdi, 16
    jae .bad
    test rsi, rsi
    jz .bad
    test rsi, 4095
    jnz .bad
    mov rax, rsi
    shr rax, 32
    jnz .bad
    test rdx, rdx
    jz .bad
    lea r8, [rel user_pcid_bindings]
    imul r9, rdi, 24
    add r8, r9
    cmp rdx, [r8 + 8]
    jbe .bad
    ; Invalidate even when an old root used the same physical table slot.
    cmp qword [rel user_pcid_enabled], 0
    je .publish
    sub rsp, 24
    lea rax, [rdi + 1]
    mov [rsp], rax
    mov qword [rsp + 8], 0
    mov eax, 1
    invpcid rax, [rsp]
    add rsp, 24
.publish:
    mov [r8], rsi
    mov [r8 + 8], rdx
    mov qword [r8 + 16], 0
    mov eax, 1
    ret
.bad:
    xor eax, eax
    ret

user_pcid_unbind:
    cmp rdi, 16
    jae .bad
    lea r8, [rel user_pcid_bindings]
    imul r9, rdi, 24
    add r8, r9
    test rsi, rsi
    jz .bad
    cmp [r8], rsi
    jne .bad
    cmp qword [rel user_pcid_enabled], 0
    je .clear
    sub rsp, 24
    lea rax, [rdi + 1]
    mov [rsp], rax
    mov qword [rsp + 8], 0
    mov eax, 1
    invpcid rax, [rsp]
    add rsp, 24
.clear:
    mov qword [r8], 0
    mov qword [r8 + 16], 0
    mov eax, 1
    ret
.bad:
    xor eax, eax
    ret

; Pure operand selection, used by the actual switch and safe host tests.
; Caller supplies an already validated naked root. It never executes CR3.
user_pcid_operand:
    mov rax, rdi
    cmp qword [rel user_pcid_enabled], 0
    je .plain
    lea r8, [rel user_pcid_bindings]
    xor ecx, ecx
.find:
    cmp [r8], rdi
    je .found
    inc ecx
    add r8, 24
    cmp ecx, 16
    jb .find
    ret                             ; unknown root uses tag zero + flush
.found:
    lea edx, [ecx + 1]
    or rax, rdx
    cmp qword [r8 + 16], 0
    je .first
    bts rax, 63
    inc qword [rel user_pcid_retained]
    ret
.first:
    mov qword [r8 + 16], 1
.plain:
    ret

user_pcid_switch:
    sub rsp, 8
    call user_pcid_operand
    add rsp, 8
    mov cr3, rax
    inc qword [rel user_pcid_switches]
    ret

; BSP invalidation for a target root, including a currently inactive tag.
; With PCIDE disabled, every re-entry is a flushing MOV CR3. A full current
; flush remains necessary before restoring/recycling shared kernel aliases.
user_pcid_invalidate_root:
    cmp qword [rel user_pcid_enabled], 0
    je .fallback
    lea r8, [rel user_pcid_bindings]
    xor ecx, ecx
.find:
    cmp [r8], rdi
    je .found
    inc ecx
    add r8, 24
    cmp ecx, 16
    jb .find
    ret
.found:
    sub rsp, 24
    lea eax, [ecx + 1]
    mov [rsp], rax
    mov qword [rsp + 8], 0
    mov eax, 1
    invpcid rax, [rsp]
    add rsp, 24
    mov qword [r8 + 16], 0
    ret
.fallback:
    mov rax, cr3
    mov cr3, rax
    ret

user_pcid_flush_all:
    cmp qword [rel user_pcid_enabled], 0
    je .fallback
    sub rsp, 24
    mov qword [rsp], 0
    mov qword [rsp + 8], 0
    mov eax, 2                       ; includes global entries and all tags
    invpcid rax, [rsp]
    add rsp, 24
    ret
.fallback:
    mov rax, cr3
    mov cr3, rax
    ret

; Optional optimization only. Require both PCID and INVPCID so inactive
; contexts can be explicitly retired. The runtime's PGE=0 contract remains.
user_pcid_enable:
    push rbx
    mov rax, cr4
    mov [rel original_cr4], rax
    test eax, (1 << 17) | (1 << 7)
    jnz .done
    mov rax, cr3
    test eax, 4095
    jnz .done
    xor eax, eax
    cpuid
    cmp eax, 7
    jb .done
    mov eax, 1
    cpuid
    test ecx, 1 << 17
    jz .done
    mov eax, 7
    xor ecx, ecx
    cpuid
    test ebx, 1 << 10
    jz .done
    mov rax, cr4
    bts rax, 17
    mov cr4, rax
    mov qword [rel user_pcid_enabled], 1
.done:
    pop rbx
    ret

; Services dispatch calls this before lifecycle mutation. The original
; trusted kernel root uses tag zero; all user tags remain independently live.
user_enter_kernel:
    cmp qword [rel user_context_cpu + UserCpu.busy], 1
    jne .done
    mov rdi, [rel user_context_cpu + UserCpu.original_cr3]
    and rdi, -4096
    sub rsp, 8
    call user_pcid_switch
    add rsp, 8
.done:
    ret

; Trusted fault continuation only. Root has already SWAPGS'ed from a CPL3
; trap and selected a validated owned Frame. Abandon the IST/caller stack;
; resume through IRET on the normal guarded kernel stack. Never return to the
; offender's exception frame. Fatal validation failure uses controlled exit.
user_resume_frame:
    cli
    cld
    mov r12, rdi
    mov rsp, [gs:UserCpu.kernel_stack]
    call user_validate_interrupt_frame
    test eax, eax
    jz user_invalid_exit
    mov rsi, r12
    mov rdi, [gs:UserCpu.root_frame]
    mov ecx, UserFrame_size / 8
    rep movsq
    mov rdi, [r12 + UserFrame.cr3]
    call user_pcid_switch
    mov rdi, r12
    jmp initial_iret

; Unsafe SysV u64 run(Frame*, CR3, kernel_stack_top). Both roots map this code,
; all context BSS and the full trusted kernel stack supervisor RW/NX. Initial
; Frame.cr3 must match CR3. Caller ensures actual physical/root ownership.
; Returns 1 on controlled dispatch-null exit, 0 on rejected frame/busy/config.
; Caller nonvolatiles, GDTR, all changed MSRs, CR3 and kernel stack restored.
user_run:
    pushfq
    pop r11
    push rbp
    mov rbp, rsp
    push rbx
    push r12
    push r13
    push r14
    push r15
    sub rsp, 8
    cmp qword [rel user_context_cpu + UserCpu.busy], 0
    jne .busy
    test rdi, rdi
    jz .argument
    test rdi, 7
    jnz .argument
    test r11d, USER_FMASK
    jnz .argument
    test rdx, 15
    jnz .argument
    mov rax, 0xffff800000000000
    cmp rdx, rax
    jb .argument
    cmp rsi, [rdi + UserFrame.cr3]
    jne .argument
    mov r12, rdi
    mov r13, rsi
    mov r14, rdx
    call user_validate_frame
    test eax, eax
    jz .frame
    mov eax, 0x80000000
    cpuid
    cmp eax, 0x80000001
    jb .argument
    mov eax, 0x80000001
    cpuid
    test edx, 1 << 11              ; SYSCALL/SYSRET enumerated before MSR use
    jz .argument
    mov rax, cr4
    test eax, (1 << 17) | (1 << 7) ; exclusive runtime starts PCIDE=PGE=0
    jnz .argument
    sgdt [rel original_gdtr]
    cmp word [rel original_gdtr], CPU_GDT_SIZE - 1
    jb .argument
    mov rsi, [rel original_gdtr + 2]
    cmp byte [rsi + CPU_TSS_SELECTOR + 5], CPU_TSS_BUSY
    jne .argument
    lea rdi, [rel user_context_gdt]
    mov ecx, CPU_GDT_SIZE / 8
    cld
    rep movsq
    mov rax, 0x00cff3000000ffff
    mov [rel user_context_gdt + 0x28], rax
    mov rax, 0x00affb000000ffff
    mov [rel user_context_gdt + 0x30], rax
    mov [rel user_context_cpu + UserCpu.kernel_stack], r14
    mov [rel user_context_cpu + UserCpu.continuation], rsp
    mov [rel user_context_cpu + UserCpu.root_frame], r12
    mov [rel original_flags], r11
    mov ax, ds
    mov [rel original_ds], ax
    mov ax, es
    mov [rel original_es], ax
    mov ax, fs
    mov [rel original_fs_selector], ax
    mov ax, gs
    mov [rel original_gs_selector], ax
    mov rax, cr3
    mov [rel user_context_cpu + UserCpu.original_cr3], rax
    mov qword [rel user_context_cpu + UserCpu.syscalls], 0
    mov qword [rel user_context_cpu + UserCpu.busy], 1
    mov qword [rel user_context_cpu + UserCpu.result], 1
    mov qword [rel user_context_last_error], 0
%macro SAVE_MSR 2
    mov ecx, %1
    rdmsr
    shl rdx, 32
    or rax, rdx
    mov [rel %2], rax
%endmacro
    SAVE_MSR MSR_EFER, original_efer
    SAVE_MSR MSR_STAR, original_star
    SAVE_MSR MSR_LSTAR, original_lstar
    SAVE_MSR MSR_FMASK, original_fmask
    SAVE_MSR MSR_FS_BASE, original_fs
    SAVE_MSR MSR_GS_BASE, original_gs
    SAVE_MSR MSR_KERNEL_GS_BASE, original_kernel_gs
%macro WRITE_MSR 2
    mov rax, %2
    mov rdx, rax
    shr rdx, 32
    mov ecx, %1
    wrmsr
%endmacro
    mov rax, [rel original_efer]
    or rax, 1
    WRITE_MSR MSR_EFER, rax
    mov rax, 0x0020000800000000
    WRITE_MSR MSR_STAR, rax
    lea rax, [rel user_syscall_entry]
    WRITE_MSR MSR_LSTAR, rax
    WRITE_MSR MSR_FMASK, USER_FMASK
    WRITE_MSR MSR_FS_BASE, 0
    lea rax, [rel user_context_cpu]
    WRITE_MSR MSR_GS_BASE, rax
    WRITE_MSR MSR_KERNEL_GS_BASE, 0
    lgdt [rel user_gdtr]
    call user_pcid_enable
    mov rdi, r13
    call user_pcid_switch
    mov rdi, r12
    call initial_iret
    ud2
.busy:
    mov qword [rel user_context_last_error], USER_ERR_BUSY
    jmp .reject
.argument:
    mov qword [rel user_context_last_error], USER_ERR_ARGUMENT
    jmp .reject
.frame:
    mov qword [rel user_context_last_error], USER_ERR_FRAME
.reject:
    xor eax, eax
    jmp user_run_return

; RDI selects a trusted validated frame. Initial entry uses IRETQ so all GPRs,
; including RCX and R11, can carry their chosen initial values.
initial_iret:
    mov rax, [rdi + UserFrame.rsp]
    mov [gs:UserCpu.user_stack], rax
    push qword USER_DATA_SELECTOR
    push qword [rdi + UserFrame.rsp]
    push qword [rdi + UserFrame.rflags]
    push qword USER_CODE_SELECTOR
    push qword [rdi + UserFrame.rip]
    USER_LOAD_GPRS rdi
    swapgs
user_iret_instruction:
    iretq

user_syscall_entry:
    swapgs
    lfence                          ; serialize use of the selected kernel GS
    mov [gs:UserCpu.user_stack], rsp
    mov rsp, [gs:UserCpu.kernel_stack]
    sub rsp, 208                     ; 200B frame plus 8B alignment padding
    USER_SAVE_GPRS rsp
    mov [rsp + UserFrame.rip], rcx
    mov [rsp + UserFrame.rflags], r11
    mov rax, [gs:UserCpu.user_stack]
    mov [rsp + UserFrame.rsp], rax
    mov rax, cr3
    and rax, -4096                  ; Frame ABI always stores the naked root
    mov [rsp + UserFrame.cr3], rax
    mov qword [rsp + UserFrame.status], 0
    mov qword [rsp + UserFrame.exit_code], 0
    mov qword [rsp + UserFrame.reserved], 0
    inc qword [gs:UserCpu.syscalls]
    mov rax, [gs:UserCpu.syscalls]
    mov [rsp + UserFrame.syscalls], rax
    cld
    mov ecx, MSR_FS_BASE
    rdmsr
    shl rdx, 32
    or rax, rdx
    mov [rsp + UserFrame.fs_base], rax
    mov ecx, MSR_KERNEL_GS_BASE
    rdmsr
    shl rdx, 32
    or rax, rdx
    mov [rsp + UserFrame.gs_base], rax
    mov r12, rsp
    mov rdi, r12
    call dong_user_dispatch
    cli
    cld
    pushfq
    and qword [rsp], ~(1 << 18)
    popfq
    test rax, rax
    jz user_controlled_exit
    mov r12, rax
    mov rdi, r12
    call user_validate_frame
    test eax, eax
    jz user_invalid_exit
    mov rsi, r12
    mov rdi, [gs:UserCpu.root_frame]
    mov ecx, UserFrame_size / 8
    rep movsq
    mov rdi, [r12 + UserFrame.cr3]
    call user_pcid_switch
    mov rax, [r12 + UserFrame.rsp]
    mov [gs:UserCpu.user_stack], rax
    mov rdi, r12
    USER_LOAD_GPRS rdi
    ; RCX/R11 are the architecturally defined return slots, never arbitrary
    ; frame.rcx/r11. Re-fetch from the copied stable caller-owned frame.
    mov rcx, [gs:UserCpu.root_frame]
    mov r11, [rcx + UserFrame.rflags]
    mov rcx, [rcx + UserFrame.rip]
    mov rsp, [gs:UserCpu.user_stack]
    swapgs
user_sysret_instruction:
    o64 sysret

user_invalid_exit:
    mov qword [rel user_context_last_error], USER_ERR_FRAME
    mov qword [gs:UserCpu.result], 0
user_controlled_exit:
    cli
    cld
    mov rsi, r12
    mov rdi, [gs:UserCpu.root_frame]
    mov ecx, UserFrame_size / 8
    rep movsq
    mov rax, [gs:UserCpu.original_cr3]
    mov cr3, rax
    mov rax, [rel original_cr4]
    mov cr4, rax                     ; clearing PCIDE invalidates old tags
    mov qword [rel user_pcid_enabled], 0
    lea rdi, [rel user_pcid_bindings]
    mov ecx, 16
.clear_loaded:
    mov qword [rdi + 16], 0
    add rdi, 24
    loop .clear_loaded
    mov rsp, [gs:UserCpu.continuation]
    lgdt [rel original_gdtr]
    mov ax, [rel original_ds]
    mov ds, ax
    mov ax, [rel original_es]
    mov es, ax
    mov ax, [rel original_fs_selector]
    mov fs, ax
    mov ax, [rel original_gs_selector]
    mov gs, ax
%macro RESTORE_MSR 2
    mov rax, [rel %2]
    WRITE_MSR %1, rax
%endmacro
    RESTORE_MSR MSR_STAR, original_star
    RESTORE_MSR MSR_LSTAR, original_lstar
    RESTORE_MSR MSR_FMASK, original_fmask
    RESTORE_MSR MSR_EFER, original_efer
    RESTORE_MSR MSR_FS_BASE, original_fs
    ; No GS-relative references after restoring GS_BASE. We arrived here with
    ; kernel GS active, and restore BOTH MSRs directly rather than swapping.
    RESTORE_MSR MSR_KERNEL_GS_BASE, original_kernel_gs
    RESTORE_MSR MSR_GS_BASE, original_gs
    push qword [rel original_flags]
    popfq
    mov qword [rel user_context_cpu + UserCpu.busy], 0
    mov rax, [rel user_context_cpu + UserCpu.result]
user_run_return:
    lea rsp, [rsp + 8]
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret

; Optional root fault-fixup hook. Unsafe copy(dst,src,count): predicates and
; AC control belong to root. This helper never enables AC, probes mappings or
; reads a user pointer before root validates it. Bounds labels cover only MOVSB.
; A validated PF fixup sets saved RIP=user_copy_fault. No other fault is caught.
user_copy_from:
    mov r8d, 1
    jmp user_copy_common
user_copy_to:
    mov r8d, 2
user_copy_common:
    cmp qword [rel user_copy_active], 0
    jne .busy
    mov [rel user_copy_source], rsi
    mov [rel user_copy_destination], rdi
    mov [rel user_copy_length], rdx
    mov [rel user_copy_direction], r8
    mov qword [rel user_copy_active], 1
    mov rcx, rdx
user_copy_begin:
    rep movsb
user_copy_end:
    xor eax, eax
    jmp user_copy_resume
user_copy_fault:
    mov eax, USER_ERR_ARGUMENT
user_copy_resume:
    mov qword [rel user_copy_active], 0
    ret
user_copy_common.busy:
    mov eax, USER_ERR_BUSY
    ret

section .rodata
%if __NASM_MAJOR__ >= 3
[warning push]
[warning -reloc-abs-qword]
%endif
user_gdtr: dw 55
    dq user_context_gdt
%if __NASM_MAJOR__ >= 3
[warning pop]
%endif
section .bss
alignb 16
user_context_cpu: resb UserCpu_size
user_context_gdt: resb 56
user_context_gdt_end:
original_gdtr: resb 16
original_efer: resq 1
original_star: resq 1
original_lstar: resq 1
original_fmask: resq 1
original_fs: resq 1
original_gs: resq 1
original_kernel_gs: resq 1
original_flags: resq 1
original_ds: resw 1
original_es: resw 1
original_fs_selector: resw 1
original_gs_selector: resw 1
user_context_last_error: resq 1
user_copy_active: resq 1
user_copy_source: resq 1
user_copy_destination: resq 1
user_copy_length: resq 1
user_copy_direction: resq 1
original_cr4: resq 1
user_pcid_enabled: resq 1
user_pcid_switches: resq 1
user_pcid_retained: resq 1
user_pcid_bindings: resq 48
