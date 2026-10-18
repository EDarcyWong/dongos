; BSP-only private GDT/TSS/IDT and fatal exception entry, integer registers only.
; Intel SDM vol.3A 7.14 and AMD APM vol.2 8.9 specify the long-mode frame/IST.
; https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html
; https://www.amd.com/content/dam/amd/en/documents/processor-tech-docs/programmer-references/24593.pdf
bits 64
default rel
%include "cpu.inc"
%ifndef RUNTIME_LEVEL
%define RUNTIME_LEVEL 0
%endif

extern kernel_exception_panic
%if RUNTIME_LEVEL >= 5
extern dong_user_exception_dispatch,user_enter_kernel,user_resume_frame
%endif
global cpu_init
global cpu_validate
global cpu_gdt
global cpu_gdt_end
global cpu_idt
global cpu_idt_end
global cpu_tss
global cpu_tss_end
global cpu_df_stack_bottom
global cpu_df_stack_top
global cpu_nmi_stack_bottom
global cpu_nmi_stack_top
global cpu_exception_stack_bottom
global cpu_exception_stack_top
global cpu_df_guard_low
global cpu_df_guard_high
global cpu_nmi_guard_low
global cpu_nmi_guard_high
global cpu_exception_guard_low
global cpu_exception_guard_high
global cpu_exception_stack_ranges
global cpu_exception_stack_ranges_end

section .text
; SysV void cpu_init(void). Boot BSP, CPL0, no concurrent users of these tables.
; Installs high-half tables and reloads all segment selectors. Preserves SysV
; nonvolatile GPRs; clobbers caller-saved registers and flags. IF=0 and DF=0 on
; return. Does not enable IRQs, modify interrupt controllers or use SIMD.
cpu_init:
    push rbp
    mov rbp, rsp
    cli
    cld

    lea rdi, [rel cpu_tss]
    xor eax, eax
    mov ecx, CPU_TSS_SIZE / 8
    rep stosq
    lea rax, [rel cpu_exception_stack_top]
    mov [rel cpu_tss + CPU_TSS_RSP0], rax
    mov [rel cpu_tss + CPU_TSS_IST3], rax
    lea rax, [rel cpu_df_stack_top]
    mov [rel cpu_tss + CPU_TSS_IST1], rax
    lea rax, [rel cpu_nmi_stack_top]
    mov [rel cpu_tss + CPU_TSS_IST2], rax
    ; An I/O bitmap starting one byte beyond the TSS limit denies CPL>IOPL I/O.
    mov word [rel cpu_tss + CPU_TSS_IOMAP_BASE], CPU_TSS_SIZE

    lea rdi, [rel cpu_gdt + CPU_TSS_SELECTOR]
    lea rax, [rel cpu_tss]
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

    lea rdi, [rel cpu_idt]
    lea rsi, [rel cpu_stub_table]
    xor ecx, ecx
.gate:
    lodsq
    mov word [rdi], ax
    mov word [rdi + 2], CPU_KERNEL_CODE_SELECTOR
    mov edx, CPU_IST_EXCEPTION
    cmp ecx, 8
    jne .not_df
    mov edx, CPU_IST_DF
.not_df:
    cmp ecx, 2
    jne .not_nmi
    mov edx, CPU_IST_NMI
.not_nmi:
    mov byte [rdi + 4], dl
    mov byte [rdi + 5], CPU_IDT_INTERRUPT_GATE
    shr rax, 16
    mov word [rdi + 6], ax
    shr rax, 16
    mov dword [rdi + 8], eax
    mov dword [rdi + 12], 0
    add rdi, CPU_IDT_ENTRY_SIZE
    inc ecx
    cmp ecx, CPU_IDT_ENTRY_COUNT
    jb .gate

    lgdt [rel cpu_gdtr]
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
    mov ax, CPU_TSS_SELECTOR
    ltr ax
    lidt [rel cpu_idtr]
    pop rbp
    ret

; SysV u64 cpu_validate(void): 1 only when the loaded tables and every gate
; match this module, including LTR's busy bit and the absent I/O bitmap.
; CPL0; IF must still be clear. No writes to the installed tables or SIMD.
; Preserves all SysV nonvolatile registers. Returns 0 for a detected mismatch.
cpu_validate:
    sub rsp, 40
    sgdt [rsp]
    sidt [rsp + 16]
    str word [rsp + 12]
    cmp word [rsp], CPU_GDT_SIZE - 1
    jne .bad
    lea rax, [rel cpu_gdt]
    cmp [rsp + 2], rax
    jne .bad
    mov rdx, 0xffff800000000000
    cmp rax, rdx
    jb .bad
    cmp word [rsp + 16], CPU_IDT_SIZE - 1
    jne .bad
    lea rax, [rel cpu_idt]
    cmp [rsp + 18], rax
    jne .bad
    cmp rax, rdx
    jb .bad
    cmp word [rsp + 12], CPU_TSS_SELECTOR
    jne .bad
    mov ax, cs
    cmp ax, CPU_KERNEL_CODE_SELECTOR
    jne .bad
    mov ax, ds
    cmp ax, CPU_KERNEL_DATA_SELECTOR
    jne .bad
    mov ax, es
    cmp ax, CPU_KERNEL_DATA_SELECTOR
    jne .bad
    mov ax, ss
    cmp ax, CPU_KERNEL_DATA_SELECTOR
    jne .bad
    pushfq
    pop rax
    test eax, (1 << 9) | (1 << 10)
    jnz .bad

    cmp qword [rel cpu_gdt], 0
    jne .bad
    mov rax, CPU_GDT_CODE_DESCRIPTOR
    cmp [rel cpu_gdt + CPU_KERNEL_CODE_SELECTOR], rax
    jne .bad
    mov rax, CPU_GDT_DATA_DESCRIPTOR
    cmp [rel cpu_gdt + CPU_KERNEL_DATA_SELECTOR], rax
    jne .bad
    lea rsi, [rel cpu_gdt + CPU_TSS_SELECTOR]
    cmp word [rsi], CPU_TSS_SIZE - 1
    jne .bad
    cmp byte [rsi + 5], CPU_TSS_BUSY
    jne .bad
    cmp byte [rsi + 6], 0
    jne .bad
    cmp dword [rsi + 12], 0
    jne .bad
    movzx eax, word [rsi + 2]
    movzx edx, byte [rsi + 4]
    shl rdx, 16
    or rax, rdx
    movzx edx, byte [rsi + 7]
    shl rdx, 24
    or rax, rdx
    mov edx, [rsi + 8]
    shl rdx, 32
    or rax, rdx
    lea rsi, [rel cpu_tss]
    cmp rax, rsi
    jne .bad
    cmp dword [rsi], 0
    jne .bad
    cmp qword [rsi + 28], 0
    jne .bad
    cmp qword [rsi + 92], 0
    jne .bad
    cmp word [rsi + 100], 0
    jne .bad
    cmp word [rsi + CPU_TSS_IOMAP_BASE], CPU_TSS_SIZE
    jne .bad
    lea rax, [rel cpu_exception_stack_top]
    cmp [rsi + CPU_TSS_RSP0], rax
    jne .bad
    cmp [rsi + CPU_TSS_IST3], rax
    jne .bad
    lea rax, [rel cpu_df_stack_top]
    cmp [rsi + CPU_TSS_IST1], rax
    jne .bad
    lea rax, [rel cpu_nmi_stack_top]
    cmp [rsi + CPU_TSS_IST2], rax
    jne .bad
    cmp qword [rsi + CPU_TSS_RSP1], 0
    jne .bad
    cmp qword [rsi + CPU_TSS_RSP2], 0
    jne .bad
    lea rdi, [rsi + CPU_TSS_IST4]
    mov ecx, 4
.unused_ist:
    cmp qword [rdi], 0
    jne .bad
    add rdi, 8
    loop .unused_ist

    lea rdi, [rel cpu_idt]
    lea rsi, [rel cpu_stub_table]
    xor ecx, ecx
.gate:
    lodsq
    cmp word [rdi], ax
    jne .bad
    shr rax, 16
    cmp word [rdi + 6], ax
    jne .bad
    shr rax, 16
    cmp dword [rdi + 8], eax
    jne .bad
    cmp word [rdi + 2], CPU_KERNEL_CODE_SELECTOR
    jne .bad
    mov edx, CPU_IST_EXCEPTION
    cmp ecx, 8
    jne .not_df
    mov edx, CPU_IST_DF
.not_df:
    cmp ecx, 2
    jne .not_nmi
    mov edx, CPU_IST_NMI
.not_nmi:
    cmp byte [rdi + 4], dl
    jne .bad
    cmp byte [rdi + 5], CPU_IDT_INTERRUPT_GATE
    jne .bad
    cmp dword [rdi + 12], 0
    jne .bad
    add rdi, CPU_IDT_ENTRY_SIZE
    inc ecx
    cmp ecx, CPU_IDT_ENTRY_COUNT
    jb .gate
    mov eax, 1
    add rsp, 40
    ret
.bad:
    xor eax, eax
    add rsp, 40
    ret

; Hardware error-code vectors: #DF/#TS/#NP/#SS/#GP/#PF/#AC/#CP/#VC/#SX.
; Intel SDM 7.13/7.15 and AMD APM 8.2, 15.35. INT n must not be used to
; simulate those faults: software INT never supplies their hardware error code.
%macro CPU_VECTOR 1
cpu_vector_%1:
%if %1 = 8 || %1 = 10 || %1 = 11 || %1 = 12 || %1 = 13 || %1 = 14 || %1 = 17 || %1 = 21 || %1 = 29 || %1 = 30
%else
    push qword 0
%endif
    push qword %1
    jmp cpu_exception_common
%endmacro

%assign vector 0
%rep CPU_IDT_ENTRY_COUNT
    CPU_VECTOR vector
%assign vector vector + 1
%endrep

; Fatal-only entry. The interrupt gate already cleared IF and selected an IST
; even if the interrupted RSP was unmapped. Capture CR2 before other accesses;
; RAX's original value was saved before using it. Keep the context untouched
; above the call frame; panic may inspect it but must never attempt IRET.
cpu_exception_common:
    push rax
    mov rax, cr2
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
    push rax
    mov rdi, rsp
    and rsp, -16
    cld
    cli
    ; Preserve the interrupted AC in ExceptionContext, then close any future
    ; user-copy window before entering Dong/panic. Valid without CPUID.SMAP;
    ; unconditional CLAC would #UD on older CPUs.
    pushfq
    and qword [rsp], ~(1 << 18)
    popfq
%if RUNTIME_LEVEL >= 5
    ; A user exception retires that process; supervisor faults retain the
    ; original fatal path. IRQs reach the same capture with DPL0 gates.
    test qword [rdi + ExceptionContext.cs], 3
    jz .fatal
    mov rbx, rdi
    swapgs
    lfence
    call user_enter_kernel
    mov rdi, rbx
    call dong_user_exception_dispatch
    test rax, rax
    jz .unhandled
    mov rdi, rax
    jmp user_resume_frame
.unhandled:
    swapgs
    mov rdi, rbx
.fatal:
%endif
    call kernel_exception_panic
    ; Defensive only: panic's ABI is noreturn. Never resume a faulting task.
    cli
.halt:
    hlt
    jmp .halt

section .rodata
; These table entries deliberately need full R_X86_64_64/ADDR64 relocations;
; the fixed high-half kernel link resolves them, without 32-bit truncation.
%if __NASM_MAJOR__ >= 3
[warning push]
[warning -reloc-abs-qword]
%endif
align 8
cpu_gdtr:
    dw CPU_GDT_SIZE - 1
    dq cpu_gdt
cpu_idtr:
    dw CPU_IDT_SIZE - 1
    dq cpu_idt
align 8
cpu_stub_table:
%assign vector 0
%rep CPU_IDT_ENTRY_COUNT
    dq cpu_vector_%+vector
%assign vector vector + 1
%endrep
align 8
cpu_exception_stack_ranges:
    dq cpu_df_stack_bottom, cpu_df_stack_top
    dq cpu_nmi_stack_bottom, cpu_nmi_stack_top
    dq cpu_exception_stack_bottom, cpu_exception_stack_top
cpu_exception_stack_ranges_end:
%if __NASM_MAJOR__ >= 3
[warning pop]
%endif

section .data
align 16
cpu_gdt:
    dq 0
    dq CPU_GDT_CODE_DESCRIPTOR
    dq CPU_GDT_DATA_DESCRIPTOR
    times 16 db 0
cpu_gdt_end:

section .bss
alignb 16
cpu_tss: resb CPU_TSS_SIZE
cpu_tss_end:
alignb 16
cpu_idt: resb CPU_IDT_SIZE
cpu_idt_end:
alignb 4096
; Each guard owns a distinct reserved page. The inactive memory tree skips
; these six pages; P1's current bootstrap mapping still includes them.
cpu_df_guard_low: resb 4096
cpu_df_stack_bottom: resb CPU_IST_STACK_SIZE
cpu_df_stack_top:
cpu_df_guard_high: resb 4096
alignb 4096
cpu_nmi_guard_low: resb 4096
cpu_nmi_stack_bottom: resb CPU_IST_STACK_SIZE
cpu_nmi_stack_top:
cpu_nmi_guard_high: resb 4096
alignb 4096
cpu_exception_guard_low: resb 4096
cpu_exception_stack_bottom: resb CPU_IST_STACK_SIZE
cpu_exception_stack_top:
cpu_exception_guard_high: resb 4096

section .note.GNU-stack noalloc noexec nowrite progbits
