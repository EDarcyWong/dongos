; CPU snapshots, dry-run stack callback and the non-returning P2 handoff.
bits 64
default rel
%include "bootinfo.inc"
%include "memory_report.inc"
%include "control_state.inc"
%include "activation_report.inc"
%include "runtime_view.inc"
%include "runtime_display.inc"

section .text
global memory_read_pat
global memory_stack_probe
global memory_read_controls
global memory_activate
global memory_active_probe

; rdi=new root PA, rsi=fixed stack top, rdx=continuation VA, rcx=RuntimeView*,
; r8=validated planned CR0, r9=validated planned EFER. Never returns.
; Caller proved IF/DF=0, PCIDE/PGE/LA57/CET=0, CD/NW=0, and all shared
; kernel/IST mappings. Keep every input outside WRMSR's EAX/EDX/ECX clobbers.
; PAT/MTRRs and old root/stack ownership remain unchanged.
memory_activate:
    mov r12, rdi
    mov r13, rsi
    mov r14, rdx
    mov r15, rcx
    mov rbx, r8
    mov rbp, r9
    xor r10d, r10d
    mov rax, rbp
    mov rdx, rbp
    shr rdx, 32
    mov ecx, 0xc0000080
    wrmsr                         ; NXE before fetching NX-bearing new tables
    or r10d, 1
    mov cr0, rbx                  ; supervisor write protection
    or r10d, 2
    mov rax, rbx
    or rax, 1 << 30               ; CD=1/NW=0: no-fill, not global UC
    mov cr0, rax
    wbinvd
    or r10d, 4
    mov cr3, r12                  ; no PCID/global translations survive
    mov rsp, r13                  ; adjacent: no old-stack access after CR3
    xor ebp, ebp                  ; retire outgoing frame chain
    or r10d, 8
    wbinvd
    mov cr0, rbx                  ; restore validated CD=NW=0, retain WP
    or r10d, 16
    mov rdi, r15
    jmp r14                       ; entry RSP%16=0, RBP=0, r10=executed steps

; SysV rdi=ActivationReport*, rsi=RuntimeView*, rdx=pre-switch raw-map word.
; Real fixed-stack nested calls, immutable Runtime reads and reversible UC GOP
; pixel access. Only publish success tokens after the corresponding accesses.
memory_active_probe:
    push rbp
    mov rbp, rsp
    sub rsp, 32
    mov qword [rsp], 17
    mov qword [rsp + 8], 25
    call .nested
    cmp rax, 42
    jne .failed
    mov rax, 0x414354495645
    mov [rdi + ActivationReport.nested_value], rax
    mov r8, [rsi + RuntimeView.boot_info]
    mov rax, BOOTINFO_MAGIC
    cmp [r8 + BootInfo.magic], rax
    jne .failed
    mov rax, [r8 + BootInfo.memory_map]
    mov r9, HHDM_BASE
    add rax, r9
    cmp rax, [rsi + RuntimeView.raw_map]
    jne .failed
    cmp [rax], rdx
    jne .failed
    mov rax, [r8 + BootInfo.memory_map_size]
    cmp rax, [rsi + RuntimeView.raw_size]
    jne .failed
    mov r8, [rsi + RuntimeView.rsdp]
    mov rax, 0x2052545020445352 ; "RSD PTR "
    cmp [r8], rax
    jne .failed
    mov rax, 0x52554e54494d45
    mov [rdi + ActivationReport.runtime_value], rax
    mov r8, [rsi + RuntimeView.display + RuntimeDisplay.framebuffer_base]
    mov r9d, [r8]
    mov dword [r8], 0x0055aa33
    mov eax, [r8]
    mov [r8], r9d
    mov [rdi + ActivationReport.display_value], rax
    cmp eax, 0x0055aa33
    jne .failed
    xor eax, eax
    leave
    ret
.nested:
    mov [rdi + ActivationReport.rsp], rsp
    mov [rdi + ActivationReport.rbp], rbp
    mov rax, [rsp + 8]
    add rax, [rsp + 16]
    ret
.failed:
    mov eax, 0x02090001
    leave
    ret

; rdi=ControlState*. CPL0, CPUID.PAT already checked. Read-only snapshot;
; capture caller flags before arithmetic. Does not change IF/DF or controls.
memory_read_controls:
    pushfq
    pop rax
    mov [rdi + ControlState.rflags], rax
    mov rax, cr0
    mov [rdi + ControlState.cr0], rax
    mov rax, cr3
    mov [rdi + ControlState.cr3], rax
    mov rax, cr4
    mov [rdi + ControlState.cr4], rax
    mov ecx, 0xc0000080
    rdmsr
    shl rdx, 32
    or rax, rdx
    mov [rdi + ControlState.efer], rax
    mov ecx, 0x277
    rdmsr
    shl rdx, 32
    or rax, rdx
    mov [rdi + ControlState.pat], rax
    ret

; rdi=u64* out. Returns 0 if PAT exists, 1 otherwise (out unchanged).
; CPL0, interrupts already disabled. No control register or MSR writes.
memory_read_pat:
    push rbx
    mov r9, rdi
    xor eax, eax
    cpuid
    cmp eax, 1
    jb .unsupported
    mov eax, 1
    cpuid
    test edx, 1 << 16
    jz .unsupported
    mov ecx, 0x277
    rdmsr
    shl rdx, 32
    or rax, rdx
    mov [r9], rax
    xor eax, eax
    pop rbx
    ret
.unsupported:
    mov eax, 1
    pop rbx
    ret

; Callback on the newly owned stack's P1 HHDM alias; rdi=MemoryReport*.
; Check actual callback entry RSP and execute another normal SysV call with a
; materialized local frame. The future guarded VA is verified in the new tree,
; but remains unmapped under the current P1 root.
memory_stack_probe:
    mov rax, rsp
    and eax, 15
    cmp eax, 8
    jne .failed
    mov rax, HHDM_BASE
    add rax, [rdi + MemoryReport.stack_physical]
    cmp rsp, rax
    jb .failed
    add rax, 65536
    cmp rsp, rax
    jae .failed
    push rbp
    mov rbp, rsp
    sub rsp, 32
    mov qword [rsp], 17
    mov qword [rsp + 8], 25
    call .nested
    cmp rax, 42
    jne .frame_failed
    mov rax, 0x535441434b
    leave
    ret
.nested:
    mov rax, rsp
    and eax, 15
    cmp eax, 8
    jne .failed
    mov rax, [rsp + 8]
    add rax, [rsp + 16]
    ret
.frame_failed:
    leave
.failed:
    xor eax, eax
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
