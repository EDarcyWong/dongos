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
global memory_live_map, memory_live_protect, memory_live_replace, memory_live_unmap
global memory_mutation_probe
global memory_live_page_a, memory_live_page_b
global memory_live_physical_a, memory_live_physical_b
extern memory_read_controls
extern dong_memory_live_init, dong_memory_live_map, dong_memory_live_protect
extern dong_memory_live_replace, dong_memory_live_unmap, dong_memory_live_counts
extern dong_memory_live_used, dong_memory_live_verify
extern dong_memory_validate_active, dong_memory_controls_unchanged
extern kernel_fail

section .text
; Unsafe callback: aligned atomic page-table commit has already happened.
; INVLPG invalidates the local leaf and paging caches. Detached empty tables
; stay quarantined through a full same-root CR3 reload, then DG reclaims them.
; PCIDE=PGE=0, IF=0; only the BSP may have used this root. No global mappings.
object_memory_flush:
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
