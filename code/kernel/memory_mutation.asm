; BSP-local live mapping exercise. Data-only WB/NX views; no firmware/heap.
bits 64
default rel
%include "bootinfo.inc"
%include "runtime_view.inc"
%include "control_state.inc"
%include "mutation_report.inc"
%include "live_stats.inc"

%define LIVE_VA 0xffffa00000001000
%define TOKEN_A 0x1122334455667788
%define TOKEN_B 0x8877665544332211
%define TOKEN_WRITE 0x55aa33cc77ee9900

global memory_live_flush
global object_memory_flush
global large_memory_flush
global large_memory_data, large_memory_raw, large_memory_pt
global memory_live_map, memory_live_protect, memory_live_replace, memory_live_unmap
global memory_mutation_probe
global memory_live_page_a, memory_live_page_b
global memory_live_physical_a, memory_live_physical_b
extern memory_read_controls
extern dong_memory_live_init, dong_memory_live_map, dong_memory_live_protect
extern dong_memory_live_replace, dong_memory_live_unmap, dong_memory_live_counts
extern dong_memory_live_used, dong_memory_live_verify
extern dong_memory_large_run
extern dong_memory_validate_active, dong_memory_controls_unchanged
extern kernel_fail

section .text
; Unsafe callback: aligned atomic page-table commit has already happened.
; INVLPG invalidates the local leaf and paging caches. Detached empty tables
; stay quarantined through a full same-root CR3 reload, then DG reclaims them.
; PCIDE=PGE=0, IF=0; only the BSP may have used this root. No global mappings.
object_memory_flush:
large_memory_flush:
memory_live_flush:
    cmp edi, 1
    je .page
    cmp edi, 2
    jne kernel_fail
    mov rax, cr3
    mov cr3, rax
    ret
.page:
    invlpg [rsi]
    ret

; Bounded startup-only loops for boot.large_memory. Ownership, actual CR3/
; controls, publication and invalidation remain in Dong active_paging.
; These helpers never change a page table or a control register.
%define LARGE_VA 0xffffa80000000000
%define LARGE_FIRST 0x1122334400000000
%define LARGE_LAST 0x8877665500000000
%define LARGE_BAD 0x020f0001

; write=1 initializes both boundary words on every page; write=0 checks all
; 1024 words. Ordinary MOVs are the actual volatile memory accesses here.
large_memory_data:
    cmp rdi, 1
    ja .bad
    mov rsi, LARGE_VA
    xor edx, edx
.loop:
    mov r8, LARGE_FIRST
    or r8, rdx
    mov r9, LARGE_LAST
    or r9, rdx
    test edi, edi
    jz .read
    mov [rsi], r8
    mov [rsi + 4088], r9
    jmp .next
.read:
    cmp [rsi], r8
    jne .bad
    cmp [rsi + 4088], r9
    jne .bad
.next:
    add rsi, 4096
    inc edx
    cmp edx, 512
    jb .loop
    xor eax, eax
    ret
.bad:
    mov eax, LARGE_BAD
    ret

; root,pool,pages,physical,kind. Walk only the retained low-4GiB pool.
; kind0: check the complete split table; kind1: check the 2MiB leaf.
; Both return the actual nonzero PDE. kind2 requires an empty PML4 slot and
; returns1. kind3 checks a PT parent/range and returns its raw PDE without
; requiring contiguous leaves (the deliberate merge-rejection state).
; A malformed address/parent/leaf or unknown kind returns0.
large_memory_raw:
    cmp r8, 3
    ja .bad
    test rdx, rdx
    jz .bad
    cmp rdx, 128
    ja .bad
    shl rdx, 12
    test rsi, 4095
    jnz .bad
    test rsi, rsi
    jz .bad
    mov r9, 0x100000000
    cmp rsi, r9
    jae .bad
    lea r10, [rsi + rdx]
    cmp r10, r9
    ja .bad
    test rdi, 4095
    jnz .bad
    mov rax, rdi
    sub rax, rsi
    cmp rax, rdx
    jae .bad
    mov r10, HHDM_BASE
    add rdi, r10
    mov rax, [rdi + 336 * 8]
    cmp r8, 2
    jne .walk
    test rax, rax
    jnz .bad
    mov eax, 1
    ret
.walk:
%macro LARGE_PARENT 0
    mov r10, rax
    mov r11, 0xfff0000000000fdf ; only PA and hardware A may vary
    and r10, r11
    cmp r10, 7
    jne .bad
    mov r10, 0x000ffffffffff000
    and rax, r10
    mov rdi, rax
    sub rax, rsi
    cmp rax, rdx
    jae .bad
    mov r10, HHDM_BASE
    add rdi, r10
%endmacro
    LARGE_PARENT
    mov rax, [rdi]             ; PDPT slot0
    LARGE_PARENT
    mov rax, [rdi]             ; PD slot0: actual final PDE
    mov r9, rax
    cmp r8, 3
    je .parent_only
    test r8, r8
    jz .split
    and rax, ~0x60
    mov r10, rcx
    bts r10, 63
    or r10, 0x83
    cmp rax, r10
    jne .bad
    mov rax, r9
    ret
.parent_only:
    LARGE_PARENT
    mov rax, r9
    ret
.split:
    LARGE_PARENT
    bts rcx, 63
    or rcx, 3
    xor r11d, r11d
.entry:
    mov rax, [rdi + r11 * 8]
    and rax, ~0x60
    cmp rax, rcx
    jne .bad
    add rcx, 4096
    inc r11d
    cmp r11d, 512
    jb .entry
    mov rax, r9
    ret
.bad:
    xor eax, eax
    ret
%unmacro LARGE_PARENT 0

; copy=1 snapshots all512 raw entries into the already held/warmed page509.
; copy=0 compares all512 exactly, then restores that page's boundary words.
; The caller obtained pt from the checked raw walker and retains the lease.
large_memory_pt:
    cmp rdi, 1
    ja .bad
    test rsi, 4095
    jnz .bad
    mov r10, HHDM_BASE
    mov rax, rsi
    sub rax, r10
    shr rax, 32
    jnz .bad
    mov r8, LARGE_VA + 509 * 4096
    xor ecx, ecx
.loop:
    mov rax, [rsi + rcx * 8]
    test edi, edi
    jz .compare
    mov [r8 + rcx * 8], rax
    jmp .next
.compare:
    cmp rax, [r8 + rcx * 8]
    jne .bad
.next:
    inc ecx
    cmp ecx, 512
    jb .loop
    test edi, edi
    jnz .done
    mov rax, LARGE_FIRST | 509
    mov [r8], rax
    mov rax, LARGE_LAST | 509
    mov [r8 + 4088], rax
.done:
    xor eax, eax
    ret
.bad:
    mov eax, LARGE_BAD
    ret

; Public SysV wrappers capture ACTUAL controls immediately before each DG
; operation. Arguments are VA/PA/flags or VA/flags, without a forged snapshot.
%macro LIVE_WRAPPER 2
%1:
    push rbp
    mov rbp, rsp
    sub rsp, 80
    mov [rsp + 48], rdi
    mov [rsp + 56], rsi
    mov [rsp + 64], rdx
    lea rdi, [rsp]
    call memory_read_controls
    lea rdi, [rsp]
    mov rsi, [rsp + 48]
    mov rdx, [rsp + 56]
    mov rcx, [rsp + 64]
    call %2
    leave
    ret
%endmacro
LIVE_WRAPPER memory_live_map, dong_memory_live_map
LIVE_WRAPPER memory_live_protect, dong_memory_live_protect
LIVE_WRAPPER memory_live_replace, dong_memory_live_replace
LIVE_WRAPPER memory_live_unmap, dong_memory_live_unmap
%unmacro LIVE_WRAPPER 2

; rdi=RuntimeView*, rsi=MutationReport*. Returns0 or explicit error; only used
; once on the fixed stack after activation. The scratch pages remain held BSS.
memory_mutation_probe:
    push rbp
    mov rbp, rsp
    push rbx
    push r12
    push r13
    push r14
    push r15
    sub rsp, 8
    mov r12, rdi
    mov r13, rsi
    mov r14, LIVE_VA
    mov r15, cr3
    mov [r13 + MutationReport.root], r15
    mov [r13 + MutationReport.virtual], r14
    mov rax, TOKEN_A
    mov [rel memory_live_page_a], rax
    mov rax, TOKEN_B
    mov [rel memory_live_page_b], rax
    mov rax, [r12 + RuntimeView.boot_info]
    mov rbx, [rax + BootInfo.kernel_physical]
    lea rsi, [rel memory_live_page_a]
    mov rax, KERNEL_BASE
    sub rsi, rax
    add rsi, rbx
    lea rdx, [rsi + 4096]
    mov [rel memory_live_physical_a], rsi
    mov [rel memory_live_physical_b], rdx
    mov [r13 + MutationReport.physical_a], rsi
    mov [r13 + MutationReport.physical_b], rdx
    lea rdi, [rel memory_live_before]
    call memory_read_controls
    mov rsi, [rel memory_live_physical_a]
    mov rdx, [rel memory_live_physical_b]
    lea rdi, [rel memory_live_before]
    call dong_memory_live_init
    test rax, rax
    jnz .return
    or qword [r13 + MutationReport.steps], 1
    lea rdi, [r13 + MutationReport.tables_before]
    call dong_memory_live_used
    test rax, rax
    jnz .return
    mov rdi, r14
    mov rsi, [rel memory_live_physical_a]
    mov edx, 1
    call memory_live_map
    test rax, rax
    jnz .return
    mov rax, [r14]                  ; populate a real cached A translation
    mov [r13 + MutationReport.read_a], rax
    mov rdx, TOKEN_A
    cmp rax, rdx
    jne .bad
    or qword [r13 + MutationReport.steps], 2
    lea rdi, [r13 + MutationReport.tables_peak]
    call dong_memory_live_used
    test rax, rax
    jnz .return
    mov rax, HHDM_BASE
    add rax, r15
    mov rax, [rax + 320 * 8]
    mov rdx, 0x000ffffffffff000
    and rax, rdx
    mov [r13 + MutationReport.first_branch], rax
    mov rdi, r14
    xor esi, esi
    call memory_live_protect
    test rax, rax
    jnz .return
    mov rax, [r14]
    mov rdx, TOKEN_A
    cmp rax, rdx
    jne .bad
    or qword [r13 + MutationReport.steps], 4
    mov rdi, r14
    mov esi, 1
    call memory_live_protect
    test rax, rax
    jnz .return
    mov rax, TOKEN_A
    mov [r14], rax                  ; RO -> RW must permit the first write
    or qword [r13 + MutationReport.steps], 8
    mov rdi, r14
    mov rsi, [rel memory_live_physical_b]
    mov edx, 1
    call memory_live_replace
    test rax, rax
    jnz .return
    mov rax, [r14]                  ; first load must now resolve to B
    mov [r13 + MutationReport.read_b], rax
    mov rdx, TOKEN_B
    cmp rax, rdx
    jne .bad
    or qword [r13 + MutationReport.steps], 16
    mov rax, TOKEN_WRITE
    mov [r14], rax
    mov rax, [r14]
    mov [r13 + MutationReport.write_value], rax
    mov rdx, TOKEN_WRITE
    cmp rax, rdx
    jne .bad
    cmp [rel memory_live_page_b], rax
    jne .bad
    mov rax, TOKEN_A
    cmp [rel memory_live_page_a], rax
    jne .bad
    or qword [r13 + MutationReport.steps], 32
    mov rdi, r14
    call memory_live_unmap
    test rax, rax
    jnz .return
    lea rdi, [rel memory_live_used_count]
    call dong_memory_live_used
    test rax, rax
    jnz .return
    mov rax, [rel memory_live_used_count]
    cmp rax, [r13 + MutationReport.tables_before]
    jne .bad
    or qword [r13 + MutationReport.steps], 64
    mov rdi, r14
    mov rsi, [rel memory_live_physical_a]
    mov edx, 1
    call memory_live_map
    test rax, rax
    jnz .return
    mov rax, [r14]
    mov [r13 + MutationReport.reuse_value], rax
    mov rdx, TOKEN_A
    cmp rax, rdx
    jne .bad
    mov rax, HHDM_BASE
    add rax, r15
    mov rax, [rax + 320 * 8]
    mov rdx, 0x000ffffffffff000
    and rax, rdx
    mov [r13 + MutationReport.reused_branch], rax
    cmp rax, [r13 + MutationReport.first_branch]
    jne .bad
    or qword [r13 + MutationReport.steps], 128
    mov rdi, r14
    call memory_live_unmap
    test rax, rax
    jnz .return
    lea rdi, [r13 + MutationReport.tables_after]
    call dong_memory_live_used
    test rax, rax
    jnz .return
    or qword [r13 + MutationReport.steps], 256
    lea rdi, [rel memory_live_stats]
    call dong_memory_live_counts
    test rax, rax
    jnz .return
%macro COPY_STATS 2
    mov rax, [rel memory_live_stats + LiveStats.%2]
    mov [r13 + MutationReport.%1], rax
%endmacro
    COPY_STATS invlpg_count, invlpg
    COPY_STATS reload_count, full_flush
    COPY_STATS retired_tables, retired_tables
%unmacro COPY_STATS 2
    lea rdi, [rel memory_live_after]
    call memory_read_controls
    mov rax, [rel memory_live_after + ControlState.cr3]
    mov [r13 + MutationReport.cr3_after], rax
    lea rdi, [rel memory_live_before]
    lea rsi, [rel memory_live_after]
    call dong_memory_controls_unchanged
    test rax, rax
    jnz .return
    mov rdi, cr3
    call dong_memory_validate_active ; only held startup mappings remain
    test rax, rax
    jnz .return
    or qword [r13 + MutationReport.steps], 512
    mov rdi, r13
    call dong_memory_live_verify
    test rax, rax
    jnz .return
    ; Run the buddy-owned large-page lifecycle on this actual private root,
    ; with hardening active and before any AP/user process can use the root.
    call dong_memory_large_run
    jmp .return
.bad:
    mov eax, 0x020b0001
.return:
    add rsp, 8
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret

section .bss
align 8, resb 1
memory_live_before: resb ControlState_size
memory_live_after: resb ControlState_size
memory_live_stats: resb LiveStats_size
memory_live_used_count: resq 1
memory_live_physical_a: resq 1
memory_live_physical_b: resq 1
align 4096, resb 1
memory_live_page_a: resb 4096
memory_live_page_b: resb 4096

section .note.GNU-stack noalloc noexec nowrite progbits
