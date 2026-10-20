; Standalone kernel with P2 BSP CPU tables; firmware services are gone here.
bits 64
default rel
%include "bootinfo.inc"
%include "boot_trace.inc"
%include "cpu.inc"
%include "memory_layout.inc"
%include "memory_report.inc"
%include "memory_resource.inc"
%include "runtime_display.inc"
%include "runtime_view.inc"
%include "control_state.inc"
%include "control_plan.inc"
%include "activation_report.inc"
%include "mutation_report.inc"
%include "hardening_report.inc"
%include "object_memory_report.inc"
%include "acpi_report.inc"
%ifndef RUNTIME_LEVEL
%define RUNTIME_LEVEL 0
%endif
%if RUNTIME_LEVEL
extern sched_xstate_init, runtime_begin
%endif
%if RUNTIME_LEVEL == 4
extern user_runtime_begin
%endif
%if RUNTIME_LEVEL >= 5
extern dong_service_capture,service_runtime_begin
%endif
%if RUNTIME_LEVEL >= 6
extern smp_runtime_begin
%endif
%if RUNTIME_LEVEL >= 7
extern dong_desktop_enable
extern sched_xstate_enable_avx
%endif
%ifndef OBJECT_MEMORY_TEST_UNMAP
%define OBJECT_MEMORY_TEST_UNMAP 0
%endif
%ifndef MEMORY_MUTATION_TEST_CASE
%define MEMORY_MUTATION_TEST_CASE 0
%endif
%ifndef MEMORY_ACTIVATION_TEST_CASE
%define MEMORY_ACTIVATION_TEST_CASE 0
%endif
%ifndef P1_TEST
%define P1_TEST 0
%endif
%ifndef PERMISSION_TEST_CASE
%define PERMISSION_TEST_CASE 0
%endif
%if PERMISSION_TEST_CASE && !P1_TEST
%error "User permission probes are test-only"
%endif
%if OBJECT_MEMORY_TEST_UNMAP && !P1_TEST
%error "Object memory fault injection is test-only"
%endif
%if MEMORY_MUTATION_TEST_CASE && !P1_TEST
%error "Live mapping fault injection is test-only"
%endif
%if MEMORY_ACTIVATION_TEST_CASE && !P1_TEST
%error "Activation exception injection is test-only"
%endif
%ifndef CPU_TEST_CASE
%define CPU_TEST_CASE 0
%endif
%ifndef MEMORY_TEST_BAD_LAYOUT
%define MEMORY_TEST_BAD_LAYOUT 0
%endif
%ifndef MEMORY_TEST_BAD_PAT
%define MEMORY_TEST_BAD_PAT 0
%endif
%ifndef MEMORY_TEST_BAD_IST
%define MEMORY_TEST_BAD_IST 0
%endif
%ifndef MEMORY_TEST_MAPPED_GUARD
%define MEMORY_TEST_MAPPED_GUARD 0
%endif
%ifndef MEMORY_TEST_BAD_CONTROLS
%define MEMORY_TEST_BAD_CONTROLS 0
%endif
%if CPU_TEST_CASE && !P1_TEST
%error "CPU exception injection is test-only"
%endif
%if MEMORY_TEST_BAD_LAYOUT && !P1_TEST
%error "Memory layout injection is test-only"
%endif
%if MEMORY_TEST_BAD_PAT && !P1_TEST
%error "PAT injection is test-only"
%endif
%if (MEMORY_TEST_BAD_IST || MEMORY_TEST_MAPPED_GUARD || MEMORY_TEST_BAD_CONTROLS) && !P1_TEST
%error "Preflight injection is test-only"
%endif

extern cpu_init
extern cpu_validate
extern panic_init
extern panic_binding_matches
extern panic_saved_frames
extern panic_saved_frame_count
%if CPU_TEST_CASE
extern cpu_test_inject
%endif

extern dong_add
extern dong_sum_to
extern dong_boot_info
extern dong_memory_probe
extern dong_slice_probe
extern dong_constant_probe
extern dong_alignment_probe
extern dong_global_probe
extern dong_intrinsic_probe
extern dong_function_probe
extern dong_l1_probe
extern dong_memory_startup
extern dong_memory_manifest
extern memory_read_pat, memory_read_controls, memory_stack_probe, dong_call_on_stack
extern dong_memory_display, dong_memory_runtime, dong_memory_control_plan
extern dong_memory_controls_unchanged, dong_memory_validate
extern dong_memory_validate_active, dong_memory_activation_verify
extern memory_activate, memory_active_probe
extern memory_mutation_probe
extern cpu_hardening_activate
extern dong_object_memory_run
extern dong_acpi_prepare, dong_acpi_report, dong_acpi_inventory
%if OBJECT_MEMORY_TEST_UNMAP
extern object_memory_test_inject
%endif
%if MEMORY_MUTATION_TEST_CASE
extern memory_mutation_test_inject
%endif
%if MEMORY_ACTIVATION_TEST_CASE
extern memory_activation_test_inject
%endif
extern __kernel_text_start, __kernel_text_end
extern __kernel_rodata_start, __kernel_rodata_end
extern __kernel_data_start, __kernel_data_end
extern __kernel_bss_start, __kernel_bss_end
extern cpu_gdt, cpu_gdt_end, cpu_tss, cpu_tss_end, cpu_idt, cpu_idt_end
extern cpu_df_stack_bottom, cpu_df_stack_top, cpu_nmi_stack_bottom, cpu_nmi_stack_top
extern cpu_exception_stack_bottom, cpu_exception_stack_top
extern cpu_df_guard_low
%if RUNTIME_LEVEL >= 5
extern boot_trace_sample,dong_boot_trace_capture,dong_boot_trace_prepared
global boot_trace_entry_pointer
%endif
global kernel_entry
%if RUNTIME_LEVEL
global serial_write, serial_hex_line
%endif
%if PERMISSION_TEST_CASE
global serial_write, serial_hex_line
extern permission_test_inject
%endif
global kernel_fail
global __dong_panic
global kernel_panic_screen

section .text
%if RUNTIME_LEVEL >= 5
; Owned early raw Stamp; capture copies it after CPU/BootInfo validation.
boot_trace_entry_pointer:
    lea rax,[rel trace_entry_stamp]
    ret
%endif
section .text.entry
; 功能：校验引导交接，证明高半区、HHDM、Dong 模块和帧缓冲可用。
; 输入：rdi=BootInfo*（SysV），rsp 已切换到内核栈，入口 rsp%16=8。
; 输出：串口阶段标记、内核图形画面；测试版退出码33；不返回。
; 破坏：所有通用寄存器和标志；无 SIMD。
; 中断/锁：保持中断关闭，安装自己的 GDT/TSS/IDT；无需持锁。
kernel_entry:
    endbr64
%if RUNTIME_LEVEL >= 5
    mov [rel trace_handoff_physical],rdx
    mov [rel trace_handoff_tag],rcx
    push rdi
    lea rdi,[rel trace_entry_stamp]
    call boot_trace_sample
    pop rdi
%endif
%if RUNTIME_LEVEL >= 5
    mov [rel service_handoff_physical],rsi
%endif
    push rbp
    mov rbp, rsp
    cld
    cli
    ; Establish AC=0 before any Dong call, even when SMAP is unavailable.
    pushfq
    and qword [rsp], ~(1 << 18)
    popfq
    mov r12, rdi
    call cpu_init
    call cpu_validate
    cmp rax, 1
    jne kernel_fail
%if RUNTIME_LEVEL
    call sched_xstate_init
    cmp rax, 1
    jne kernel_fail
%endif
    mov rax, BOOTINFO_MAGIC
    cmp [r12 + BootInfo.magic], rax
    jne kernel_fail
    cmp qword [r12 + BootInfo.version], BOOTINFO_VERSION
    jne kernel_fail
    cmp qword [r12 + BootInfo.size], BootInfo_size
    jne kernel_fail
    test qword [r12 + BootInfo.flags], BOOTINFO_EBS_EXITED
    jz kernel_fail
    lea rax, [rel kernel_entry]
    mov rdx, KERNEL_BASE
    cmp rax, rdx
    jne kernel_fail
    mov rax, cr3
    cmp rax, [r12 + BootInfo.pml4_physical]
    jne kernel_fail
    ; HHDM must be a real physical alias of the boot information.
    mov rax, HHDM_BASE
    add rax, r12
    mov rdx, BOOTINFO_MAGIC
    cmp [rax + BootInfo.magic], rdx
    jne kernel_fail
    mov rax, [r12 + BootInfo.memory_map_size]
    test rax, rax
    jz kernel_fail
    cmp qword [r12 + BootInfo.descriptor_size], 40
    jb kernel_fail
    cmp qword [r12 + BootInfo.descriptor_version], 1
    jne kernel_fail
    cmp qword [r12 + BootInfo.rsdp], 0
    je kernel_fail
    mov rsi, [r12 + BootInfo.stack_physical]
    mov rdx, rsi
    add rdx, [r12 + BootInfo.stack_size]
    jc kernel_fail
    cmp rsp, rsi
    jb kernel_fail
    cmp rsp, rdx
    jae kernel_fail
    ; Preserve the physical handoff identity as metadata; every subsequent
    ; BootInfo access uses the HHDM alias without changing v1's PA fields.
    mov [rel memory_info_physical], r12
    mov rax, HHDM_BASE
    add r12, rax
    mov rdi, r12
    lea rsi, [rel memory_display]
    call dong_memory_display
    test rax, rax
    jnz kernel_fail
%if RUNTIME_LEVEL >= 5
    mov rdi,r12
    mov rsi,[rel memory_info_physical]
    mov rdx,[rel service_handoff_physical]
    call dong_service_capture
    test rax,rax
    jnz kernel_fail
%endif
%if RUNTIME_LEVEL >= 5
    ; Copy while identity mapping is still live; diagnostic errors do not
    ; change boot authority. Owned BSS remains mapped after activation.
    mov rdi,r12
    mov rsi,[rel memory_info_physical]
    mov rdx,[rel trace_handoff_physical]
    mov rcx,[rel trace_handoff_tag]
    call dong_boot_trace_capture
%endif
    lea rdi, [rel memory_display]
    mov rsi, [r12 + BootInfo.stack_physical]
    mov rdx, rsi
    add rdx, [r12 + BootInfo.stack_size]
    call panic_init
    lea rsi, [rel entered]
    call serial_write
    lea rsi, [rel cpu_ready]
    call serial_write
%if CPU_TEST_CASE
    lea rsi, [rel cpu_inject]
    call serial_write
    call cpu_test_inject
    jmp kernel_fail
%endif
    ; This function is compiled from Dong, linked as ELF64, and called via SysV.
    mov edi, 20
    mov esi, 22
    call dong_add
    cmp rax, 42
    jne kernel_fail
    mov edi, 10
    call dong_sum_to
    cmp rax, 55
    jne kernel_fail
    lea rsi, [rel dong_ok]
    call serial_write
    mov rdi, r12
    call dong_boot_info
    mov rdx, BOOTINFO_MAGIC
    cmp rax, rdx
    jne kernel_fail
    call dong_memory_probe
    cmp rax, 373
    jne kernel_fail
    lea rsi, [rel memory_ok]
    call serial_write
    call dong_slice_probe
    cmp rax, 765
    jne kernel_fail
    lea rsi, [rel slice_ok]
    call serial_write
    call dong_constant_probe
    cmp rax, 282
    jne kernel_fail
    lea rsi, [rel constant_ok]
    call serial_write
    call dong_alignment_probe
    cmp rax, 458
    jne kernel_fail
    lea rsi, [rel alignment_ok]
    call serial_write
    call dong_global_probe
    cmp rax, 436
    jne kernel_fail
    lea rsi, [rel global_ok]
    call serial_write
    call dong_intrinsic_probe
    cmp rax, 719
    jne kernel_fail
    lea rsi, [rel intrinsic_ok]
    call serial_write
    ; Explicit Win64 bridges preserve XMM state. Enable the architectural
    ; SSE2 context required by this boundary; ordinary Dong remains integer-only.
    mov rax, cr0
    and rax, ~((1 << 2) | (1 << 3)) ; clear EM and TS
    or rax, 1 << 1                  ; MP
    mov cr0, rax
    mov rax, cr4
    or rax, (1 << 9) | (1 << 10)    ; OSFXSR and OSXMMEXCPT
    mov cr4, rax
    call dong_function_probe
    cmp rax, 761
    jne kernel_fail
    lea rsi, [rel function_ok]
    call serial_write
    call dong_l1_probe
    cmp rax,75
    jne kernel_fail
    lea rsi,[rel l1_ok]
    call serial_write
    ; Keep the P1 CR3 active. All new tables are private, ordinary RAM.
    mov r15, cr3
    lea rdi, [rel memory_report + MemoryReport.pat_value]
    call memory_read_pat
    test rax, rax
    jz .pat_supported
    mov eax, 0x02060007
    jmp .memory_failed
.pat_supported:
    lea rdi, [rel memory_controls_before]
    call memory_read_controls
%if MEMORY_TEST_BAD_CONTROLS
    or qword [rel memory_controls_before + ControlState.cr4], 1 << 12
%endif
    lea rdi, [rel memory_controls_before]
    mov rsi, r15
    lea rdx, [rel memory_control_plan]
    call dong_memory_control_plan
    test rax, rax
    jnz .memory_failed
    mov r8, [rel memory_report + MemoryReport.pat_value]
%if MEMORY_TEST_BAD_PAT
    xor r8, 1 ; corrupt WB0 in a local value, never write IA32_PAT
%endif
    mov rdi, r12
    mov rsi, [rel memory_info_physical]
    lea rdx, [rel memory_layout]
    lea rcx, [rel memory_report]
    call dong_memory_startup
    test rax, rax
    jnz .memory_failed
    call dong_memory_runtime
    mov r13, rax
%if MEMORY_TEST_MAPPED_GUARD
    mov rdi, [rel memory_report + MemoryReport.root_physical]
    lea rsi, [rel cpu_df_guard_low]
    call memory_test_map_guard
%endif
    call dong_memory_validate
    test rax, rax
    jnz .memory_failed
    ; The old P1 HHDM still maps firmware RAM here. Copy only validated ACPI
    ; values into retained BSS; do not keep dereferenceable firmware pointers.
    mov rdi, r12
    call dong_acpi_prepare
    test rax, rax
    jnz .acpi_failed
    ; Bind the diagnostic view and the stack actually used by the dry run.
    mov rdi, r13
    mov rsi, [r13 + RuntimeView.stack_probe_bottom]
    mov rdx, [r13 + RuntimeView.stack_probe_top]
    call panic_init
    ; Exercise a fresh owned stack under the existing root, without changing
    ; CR3. Its isolated guarded virtual mapping is in the inactive tree only.
    mov rdi, HHDM_BASE
    add rdi, [rel memory_report + MemoryReport.stack_physical]
    lea rsi, [rdi + 65536]
    lea rdx, [rel memory_stack_probe]
    lea rcx, [rel memory_report]
    lea r8, [rel memory_report + MemoryReport.bridge_value]
    call dong_call_on_stack
    test rax, rax
    jnz kernel_fail
    mov rax, 0x535441434b
    cmp [rel memory_report + MemoryReport.bridge_value], rax
    jne kernel_fail
    ; Retire the outgoing physical RBP chain. The fixed future stack is NOT
    ; mapped by the current P1 tree, so do not register it as readable yet.
    ; The no-return handoff binds that range only after loading the new root.
    mov rdi, r13
    xor esi, esi
    xor edx, edx
    call panic_init
    call panic_binding_matches
    cmp rax, 1
    jne kernel_fail
    lea rdi, [rel memory_controls_after]
    call memory_read_controls
    lea rdi, [rel memory_controls_before]
    lea rsi, [rel memory_controls_after]
    call dong_memory_controls_unchanged
    test rax, rax
    jnz .memory_failed
    mov rax, cr3
    cmp rax, r15
    jne kernel_fail
    call memory_report_write
    lea rsi, [rel stack_ready]
    call serial_write
    lea rsi, [rel preflight_ready]
    call serial_write
    ; Recheck immediately before the irreversible root/stack commit. Preserve
    ; a real input word to prove the raw-map Runtime alias after the switch.
    mov rax, [r13 + RuntimeView.raw_map]
    mov rax, [rax]
    mov [rel memory_raw_first], rax
    call dong_memory_validate
    test rax, rax
    jnz .memory_failed
    lea rdi, [rel memory_controls_after]
    call memory_read_controls
    lea rdi, [rel memory_controls_before]
    lea rsi, [rel memory_controls_after]
    call dong_memory_controls_unchanged
    test rax, rax
    jnz .memory_failed
    mov rdi, [r13 + RuntimeView.root_physical]
    mov rsi, [r13 + RuntimeView.stack_top]
    lea rdx, [rel memory_activation_entry]
    mov rcx, r13
    mov r8, [rel memory_control_plan + ControlPlan.cr0]
    mov r9, [rel memory_control_plan + ControlPlan.efer]
    jmp memory_activate
.acpi_failed:
    mov rbx, rax
    lea rsi, [rel acpi_error]
    call serial_write
    mov rax, rbx
    call serial_hex_line
    jmp kernel_fail
.memory_failed:
    mov rbx, rax
    lea rsi, [rel memory_error]
    call serial_write
    mov rax, rbx
    call serial_hex_line
    jmp kernel_fail

section .text
; Entered by JMP only: no outgoing return address or frame chain survives.
; rdi=immutable high-half RuntimeView*, rsp=fixed top, rbp=0, r10=cache steps.
memory_activation_entry:
    mov [rel memory_activation_report + ActivationReport.entry_rsp], rsp
    mov [rel memory_activation_report + ActivationReport.entry_rbp], rbp
    mov [rel memory_activation_report + ActivationReport.cache_steps], r10
    push qword 0                  ; terminal frame's return address
    push rbp
    mov rbp, rsp                  ; normal SysV call sites now RSP%16=0
    mov r12, rdi
    mov rsi, [r12 + RuntimeView.stack_bottom]
    mov rdx, [r12 + RuntimeView.stack_top]
    call panic_init
    mov rdi, r12
    mov rsi, [r12 + RuntimeView.stack_bottom]
    mov rdx, [r12 + RuntimeView.stack_top]
    call panic_binding_matches
    cmp rax, 1
    jne kernel_fail
    lea rdi, [rel memory_controls_active]
    call memory_read_controls
%macro ACTIVE_CONTROL 2
    mov rax, [rel memory_controls_active + ControlState.%2]
    mov [rel memory_activation_report + ActivationReport.%1], rax
%endmacro
    ACTIVE_CONTROL cr3, cr3
    ACTIVE_CONTROL cr0, cr0
    ACTIVE_CONTROL cr4, cr4
    ACTIVE_CONTROL efer, efer
    ACTIVE_CONTROL pat, pat
    ACTIVE_CONTROL rflags, rflags
%unmacro ACTIVE_CONTROL 2
    lea rdi, [rel memory_activation_report]
    mov rsi, r12
    mov rdx, [rel memory_raw_first]
    call memory_active_probe
    test rax, rax
    jnz .failed
    mov rdi, cr3
    call dong_memory_validate_active
    test rax, rax
    jnz .failed
    lea rdi, [rel memory_activation_report]
    lea rsi, [rel memory_controls_before]
    lea rdx, [rel memory_control_plan]
    mov rcx, r12
    call dong_memory_activation_verify
    test rax, rax
    jnz .failed
    call memory_activation_report_write
    lea rsi, [rel activation_ready]
    call serial_write
%if MEMORY_ACTIVATION_TEST_CASE
    lea rsi, [rel activation_inject]
    call serial_write
    call memory_activation_test_inject
    jmp kernel_fail
%endif
    lea rdi, [rel cpu_hardening_report]
    call cpu_hardening_activate
    test rax, rax
    jnz .hardening_failed
    call cpu_hardening_report_write
    lea rsi, [rel hardening_ready]
    call serial_write
    mov rdi, r12
    lea rsi, [rel memory_mutation_report]
    call memory_mutation_probe
    test rax, rax
    jnz .mutation_failed
    call memory_mutation_report_write
    lea rsi, [rel mutation_ready]
    call serial_write
%if MEMORY_MUTATION_TEST_CASE
    lea rsi, [rel mutation_inject]
    call serial_write
    call memory_mutation_test_inject
    jmp kernel_fail
%endif
    lea rdi, [rel object_memory_report]
    call dong_object_memory_run
    test rax, rax
    jnz .objects_failed
    call object_memory_report_write
    lea rsi, [rel object_memory_ready]
    call serial_write
%if OBJECT_MEMORY_TEST_UNMAP
    lea rsi, [rel object_memory_inject]
    call serial_write
    call object_memory_test_inject
    jmp kernel_fail
%endif
%if PERMISSION_TEST_CASE
    mov rdi, r12
    call permission_test_inject
    jmp kernel_fail
%endif
    call dong_acpi_inventory
    test rax, rax
    jz kernel_fail
    mov [rel p3_acpi_inventory], rax
    lea rdi, [rel p3_acpi_report]
    call dong_acpi_report
    test rax, rax
    jnz kernel_fail
    call acpi_report_write
    lea rsi, [rel acpi_ready]
    call serial_write
    lea rsi, [rel memory_ready]
    call serial_write
    call screen_draw
    test eax, eax
    jz kernel_fail
%if RUNTIME_LEVEL
    call dong_memory_runtime
    mov rdi, rax
    call runtime_begin
    cmp rax, 1
    jne kernel_fail
%endif
%if RUNTIME_LEVEL >= 6
%if RUNTIME_LEVEL >= 7
    call sched_xstate_enable_avx
%endif
    call dong_boot_trace_prepared
    call smp_runtime_begin
    cmp rax,1
    jne kernel_fail
%endif
%if RUNTIME_LEVEL == 4
    call user_runtime_begin
    cmp rax, 1
    jne kernel_fail
%endif
%if RUNTIME_LEVEL >= 5
%if RUNTIME_LEVEL >= 7
    call dong_desktop_enable
%endif
    call service_runtime_begin
    cmp rax,1
    jne kernel_fail
%endif
    lea rsi, [rel passed]
    call serial_write
%if P1_TEST
    mov eax, 0x10
    out 0xf4, eax
%endif
.halt:
    hlt
    jmp .halt
.failed:
    mov rbx, rax
    lea rsi, [rel activation_error]
    call serial_write
    mov rax, rbx
    call serial_hex_line
    jmp kernel_fail
.mutation_failed:
    mov rbx, rax
    lea rsi, [rel mutation_error]
    call serial_write
    mov rax, rbx
    call serial_hex_line
    jmp kernel_fail
.hardening_failed:
    mov rbx, rax
    lea rsi, [rel hardening_error]
    call serial_write
    mov rax, rbx
    call serial_hex_line
    jmp kernel_fail
.objects_failed:
    mov rbx, rax
    lea rsi, [rel object_memory_error]
    call serial_write
    mov rax, rbx
    call serial_hex_line
    jmp kernel_fail

acpi_report_write:
    push rbx
    lea rbx, [rel p3_acpi_report]
%macro ACPI_FIELD 1
    lea rsi, [rel acpi_key_%1]
    call serial_write
    mov rax, [rbx + AcpiReport.%1]
    call serial_hex_line
%endmacro
    ACPI_FIELD rsdp
    ACPI_FIELD xsdt
    ACPI_FIELD madt
    ACPI_FIELD fadt
    ACPI_FIELD hpet
    ACPI_FIELD mcfg
    ACPI_FIELD table_count
    ACPI_FIELD cpu_count
    ACPI_FIELD ioapic_count
    ACPI_FIELD iso_count
    ACPI_FIELD nmi_count
    ACPI_FIELD mcfg_count
    ACPI_FIELD lapic_address
    ACPI_FIELD madt_flags
    ACPI_FIELD fadt_flags
    ACPI_FIELD boot_arch
    ACPI_FIELD pm_timer_block
    ACPI_FIELD pm_timer_length
    ACPI_FIELD pm_timer_32bit
    ACPI_FIELD hpet_gas_info
    ACPI_FIELD hpet_address
    ACPI_FIELD pm_timer_gas_info
    ACPI_FIELD pm_timer_address
    ACPI_FIELD steps
%unmacro ACPI_FIELD 1
    pop rbx
    ret

object_memory_report_write:
    push rbx
    lea rbx, [rel object_memory_report]
%macro OBJECT_MEMORY_FIELD 1
    lea rsi, [rel object_memory_key_%1]
    call serial_write
    mov rax, [rbx + ObjectMemoryReport.%1]
    call serial_hex_line
%endmacro
    OBJECT_MEMORY_FIELD root
    OBJECT_MEMORY_FIELD virtual
    OBJECT_MEMORY_FIELD physical
    OBJECT_MEMORY_FIELD reused_physical
    OBJECT_MEMORY_FIELD object_size
    OBJECT_MEMORY_FIELD alignment
    OBJECT_MEMORY_FIELD capacity
    OBJECT_MEMORY_FIELD allocated
    OBJECT_MEMORY_FIELD oom_error
    OBJECT_MEMORY_FIELD busy_error
    OBJECT_MEMORY_FIELD reused_object
    OBJECT_MEMORY_FIELD free_before
    OBJECT_MEMORY_FIELD free_held
    OBJECT_MEMORY_FIELD free_after
    OBJECT_MEMORY_FIELD tables_before
    OBJECT_MEMORY_FIELD tables_peak
    OBJECT_MEMORY_FIELD tables_after
    OBJECT_MEMORY_FIELD invlpg_count
    OBJECT_MEMORY_FIELD reload_count
    OBJECT_MEMORY_FIELD retired_tables
    OBJECT_MEMORY_FIELD checksum
    OBJECT_MEMORY_FIELD steps
    OBJECT_MEMORY_FIELD cr4
    OBJECT_MEMORY_FIELD rflags
%unmacro OBJECT_MEMORY_FIELD 1
    pop rbx
    ret

cpu_hardening_report_write:
    push rbx
    lea rbx, [rel cpu_hardening_report]
%macro HARDENING_FIELD 1
    lea rsi, [rel hardening_key_%1]
    call serial_write
    mov rax, [rbx + HardeningReport.%1]
    call serial_hex_line
%endmacro
    HARDENING_FIELD max_basic
    HARDENING_FIELD leaf7_ebx
    HARDENING_FIELD leaf7_ecx
    HARDENING_FIELD supported
    HARDENING_FIELD cr4_before
    HARDENING_FIELD cr4_after
    HARDENING_FIELD rflags_before
    HARDENING_FIELD rflags_after
    HARDENING_FIELD cr0
    HARDENING_FIELD cr3
    HARDENING_FIELD efer
    HARDENING_FIELD pat
    HARDENING_FIELD steps
%unmacro HARDENING_FIELD 1
    pop rbx
    ret

memory_mutation_report_write:
    push rbx
    lea rbx, [rel memory_mutation_report]
%macro MUTATION_FIELD 1
    lea rsi, [rel mutation_key_%1]
    call serial_write
    mov rax, [rbx + MutationReport.%1]
    call serial_hex_line
%endmacro
    MUTATION_FIELD root
    MUTATION_FIELD virtual
    MUTATION_FIELD physical_a
    MUTATION_FIELD physical_b
    MUTATION_FIELD read_a
    MUTATION_FIELD read_b
    MUTATION_FIELD write_value
    MUTATION_FIELD reuse_value
    MUTATION_FIELD tables_before
    MUTATION_FIELD tables_peak
    MUTATION_FIELD tables_after
    MUTATION_FIELD invlpg_count
    MUTATION_FIELD reload_count
    MUTATION_FIELD retired_tables
    MUTATION_FIELD first_branch
    MUTATION_FIELD reused_branch
    MUTATION_FIELD cr3_after
    MUTATION_FIELD steps
%unmacro MUTATION_FIELD 1
    pop rbx
    ret

memory_activation_report_write:
    push rbx
    lea rbx, [rel memory_activation_report]
%macro ACTIVATION_FIELD 1
    lea rsi, [rel activation_key_%1]
    call serial_write
    mov rax, [rbx + ActivationReport.%1]
    call serial_hex_line
%endmacro
    ACTIVATION_FIELD cr3
    ACTIVATION_FIELD cr0
    ACTIVATION_FIELD cr4
    ACTIVATION_FIELD efer
    ACTIVATION_FIELD pat
    ACTIVATION_FIELD rflags
    ACTIVATION_FIELD entry_rsp
    ACTIVATION_FIELD entry_rbp
    ACTIVATION_FIELD rsp
    ACTIVATION_FIELD rbp
    ACTIVATION_FIELD nested_value
    ACTIVATION_FIELD display_value
    ACTIVATION_FIELD runtime_value
    ACTIVATION_FIELD cache_steps
%unmacro ACTIVATION_FIELD 1
    pop rbx
    ret

%if MEMORY_TEST_MAPPED_GUARD
; Test-only: corrupt a leaf in the INACTIVE pool. Its adjacent first stack
; page is present; copy that mapping one page down into the reserved DF guard.
; rdi=root PA, rsi=guard VA. No active mappings/control registers change.
memory_test_map_guard:
    mov r8, rdi
    mov r9, rsi
    mov r10d, 39
    mov r11, HHDM_BASE
.walk:
    mov rax, r9
    mov ecx, r10d
    shr rax, cl
    and eax, 511
    lea rdx, [r11 + r8]
    lea rdx, [rdx + rax * 8]
    cmp r10d, 12
    je .leaf
    mov r8, [rdx]
    mov rax, 0x000ffffffffff000
    and r8, rax
    sub r10d, 9
    jmp .walk
.leaf:
    mov rax, [rdx + 8]
    sub rax, 4096
    mov [rdx], rax
    ret
%endif
; Print fixed-width, complete numeric lines for independent host validation.
; rax=value; destroys volatile registers. Entry follows normal SysV alignment.
serial_hex_line:
    sub rsp, 40
    mov r9, rax
    mov byte [rsp], '0'
    mov byte [rsp + 1], 'x'
    mov r10d, 2
    lea r11, [rel memory_hex_digits]
.digit:
    rol r9, 4
    mov rax, r9
    and eax, 15
    mov al, [r11 + rax]
    mov [rsp + r10], al
    inc r10d
    cmp r10d, 18
    jb .digit
    mov byte [rsp + 18], 13
    mov byte [rsp + 19], 10
    mov byte [rsp + 20], 0
    mov rsi, rsp
    call serial_write
    add rsp, 40
    ret

memory_report_write:
    push rbx
    push r13
    push r14
    lea rbx, [rel memory_report]
%macro MEMORY_FIELD 1
    lea rsi, [rel memory_key_%1]
    call serial_write
    mov rax, [rbx + MemoryReport.%1]
    call serial_hex_line
%endmacro
    MEMORY_FIELD physical_bits
    MEMORY_FIELD nx
    MEMORY_FIELD resource_count
    MEMORY_FIELD arena_base
    MEMORY_FIELD arena_pages
    MEMORY_FIELD usable_pages
    MEMORY_FIELD free_pages
    MEMORY_FIELD pool_physical
    MEMORY_FIELD pool_pages
    MEMORY_FIELD root_physical
    MEMORY_FIELD table_count
    MEMORY_FIELD mapped_pages
    MEMORY_FIELD pat_value
    MEMORY_FIELD stack_physical
    MEMORY_FIELD stack_pages
    MEMORY_FIELD stack_bottom
    MEMORY_FIELD stack_top
    MEMORY_FIELD bridge_value
    MEMORY_FIELD runtime_view
    MEMORY_FIELD runtime_boot_info
    MEMORY_FIELD runtime_raw_map
    MEMORY_FIELD runtime_rsdp
    MEMORY_FIELD runtime_framebuffer
    MEMORY_FIELD runtime_pool
    MEMORY_FIELD ist_guard_pages
%unmacro MEMORY_FIELD 1
    lea rsi, [rel memory_key_cr3_before]
    call serial_write
    mov rax, r15
    call serial_hex_line
    lea rsi, [rel memory_key_cr3_after]
    call serial_write
    mov rax, cr3
    call serial_hex_line
%macro CONTROL_FIELD 3
    lea rsi, [rel memory_key_%1]
    call serial_write
    mov rax, [rel %2 + %3]
    call serial_hex_line
%endmacro
    CONTROL_FIELD cr0_before, memory_controls_before, ControlState.cr0
    CONTROL_FIELD cr0_after, memory_controls_after, ControlState.cr0
    CONTROL_FIELD cr4_before, memory_controls_before, ControlState.cr4
    CONTROL_FIELD cr4_after, memory_controls_after, ControlState.cr4
    CONTROL_FIELD efer_before, memory_controls_before, ControlState.efer
    CONTROL_FIELD efer_after, memory_controls_after, ControlState.efer
    CONTROL_FIELD rflags_before, memory_controls_before, ControlState.rflags
    CONTROL_FIELD rflags_after, memory_controls_after, ControlState.rflags
    CONTROL_FIELD planned_cr0, memory_control_plan, ControlPlan.cr0
    CONTROL_FIELD planned_efer, memory_control_plan, ControlPlan.efer
    CONTROL_FIELD planned_actions, memory_control_plan, ControlPlan.actions
%unmacro CONTROL_FIELD 3
    call dong_memory_manifest
    mov r14, rax
    xor r13d, r13d
.resource:
    lea rsi, [rel memory_key_kind]
    call serial_write
    mov rax, [r14 + MemoryResource.kind]
    call serial_hex_line
    lea rsi, [rel memory_key_base]
    call serial_write
    mov rax, [r14 + MemoryResource.base]
    call serial_hex_line
    lea rsi, [rel memory_key_length]
    call serial_write
    mov rax, [r14 + MemoryResource.length]
    call serial_hex_line
    add r14, MemoryResource_size
    inc r13
    cmp r13, [rbx + MemoryReport.resource_count]
    jb .resource
    pop r14
    pop r13
    pop rbx
    ret

; 功能：报告交接失败并停机。
; 输入：无。
; 输出：串口失败标记；测试版退出码35；不返回。
; 破坏：rax、rdx、rsi、r8、标志。
; 中断/锁：仅启动时调用，中断关闭，无需持锁。
kernel_fail:
    and rsp, -16
    lea rsi, [rel failed]
    call serial_write
%if P1_TEST
    mov eax, 0x11
    out 0xf4, eax
%endif
    cli
.halt:
    hlt
    jmp .halt

; 功能：为 Dong debug 检查提供不返回的 panic ABI。
; 输入：rdi=kind、rsi=line、rdx=file、rcx=file_len（SysV）。
; 输出：串口失败并停机。
; 破坏：同 kernel_fail。
; 中断/锁：仅 P1 启动探针使用，中断关闭，无需持锁。
__dong_panic:
    jmp kernel_fail

; 功能：通过引导器初始化过的 COM1 发送 NUL 结尾的串口行。
; 输入：rsi=ASCII 字符串。
; 输出：无；硬件不响应时停止发送，不永久等待。
; 破坏：rax、rdx、rsi、r8、标志。
; 中断/锁：中断关闭，独占 COM1，无需持锁。
serial_write:
.next:
    lodsb
    test al, al
    jz .drain
    mov ah, al
    mov r8d, 0x100000
    mov dx, 0x3fd
.wait:
    in al, dx
    test al, 0x20
    jnz .send
    pause
    dec r8d
    jnz .wait
    ret
.send:
    mov dx, 0x3f8
    mov al, ah
    out dx, al
    jmp .next
.drain:
    mov r8d, 0x100000
    mov dx, 0x3fd
.wait_empty:
    in al, dx
    test al, 0x40
    jnz .done
    pause
    dec r8d
    jnz .wait_empty
.done:
    ret

; 功能：直接向 GOP 帧缓冲绘制独立内核的背景和文字。
; 输入：r12=RuntimeDisplay*（高半区地址）。
; 输出：eax=1 成功，0 表示不支持/不合法的 GOP 几何。
; 破坏：调用者保存寄存器、标志；保留 r12 和 SysV 非易失寄存器。
; 中断/锁：退出固件后调用，中断关闭，独占帧缓冲，无需持锁。
screen_draw:
    push rbp
    mov rbp, rsp
    push rbx
    push r13
    push r14
    push r15
    cmp qword [r12 + RuntimeDisplay.pixel_format], 1
    ja .bad
    mov r13, [r12 + RuntimeDisplay.width]
    mov r14, [r12 + RuntimeDisplay.height]
    cmp r13, 640
    jb .bad
    cmp r13, 8192
    ja .bad
    cmp r14, 480
    jb .bad
    cmp r14, 8192
    ja .bad
    mov r15, [r12 + RuntimeDisplay.stride]
    cmp r15, r13
    jb .bad
    cmp r15, 16384
    ja .bad
    mov rax, r15
    imul rax, r14
    shl rax, 2
    cmp rax, [r12 + RuntimeDisplay.framebuffer_size]
    ja .bad
    mov rdi, [r12 + RuntimeDisplay.framebuffer_base]
    test rdi, rdi
    jz .bad
    mov ecx, 0x001b1420 ; RGB bytes 20,14,1b; dark background.
    cmp qword [r12 + RuntimeDisplay.pixel_format], 1
    jne .color
    mov ecx, 0x0020141b
.color:
    xor ebx, ebx
.row:
    mov rdx, rdi
    mov r8, r13
.pixel:
    mov [rdx], ecx
    add rdx, 4
    dec r8
    jnz .pixel
    lea rdi, [rdi + r15*4]
    inc rbx
    cmp rbx, r14
    jb .row
    lea rsi, [rel title]
    mov edi, 56
    mov edx, 48
    call text_draw
    lea rsi, [rel subtitle]
    mov edi, 56
    mov edx, 84
    call text_draw
    lea rsi, [rel mappings]
    mov edi, 56
    mov edx, 120
    call text_draw
    lea rsi, [rel compiler]
    mov edi, 56
    mov edx, 156
    call text_draw
    lea rsi, [rel memory_title]
    mov edi, 56
    mov edx, 192
    call text_draw
    lea rsi, [rel slice_title]
    mov edi, 56
    mov edx, 228
    call text_draw
    lea rsi, [rel constant_title]
    mov edi, 56
    mov edx, 264
    call text_draw
    lea rsi, [rel alignment_title]
    mov edi, 56
    mov edx, 300
    call text_draw
    lea rsi, [rel global_title]
    mov edi, 56
    mov edx, 336
    call text_draw
    lea rsi, [rel intrinsic_title]
    mov edi, 56
    mov edx, 372
    call text_draw
    lea rsi, [rel function_title]
    mov edi, 56
    mov edx, 408
    call text_draw
    lea rsi,[rel l1_title]
    mov edi,56
    mov edx,444
    call text_draw
    mov eax, 1
    jmp .done
.bad:
    xor eax, eax
.done:
    pop r15
    pop r14
    pop r13
    pop rbx
    pop rbp
    ret

; Fatal exception display. rdi=context, rsi=validated RuntimeDisplay or zero.
; Uses only bounded GOP geometry and the panic module's checked frame list.
kernel_panic_screen:
    test rsi, rsi
    jz .early
    push rbp
    mov rbp, rsp
    push rbx
    push r12
    push r13
    push r14
    push r15
    sub rsp, 8
    mov r12, rsi
    mov r13, rdi
    cmp qword [r12 + RuntimeDisplay.pixel_format], 1
    ja .done
    mov rbx, [r12 + RuntimeDisplay.width]
    mov r14, [r12 + RuntimeDisplay.height]
    mov r15, [r12 + RuntimeDisplay.stride]
    cmp rbx, 640
    jb .done
    cmp rbx, 8192
    ja .done
    cmp r14, 480
    jb .done
    cmp r14, 8192
    ja .done
    cmp r15, rbx
    jb .done
    cmp r15, 16384
    ja .done
    mov rax, r15
    imul rax, r14
    shl rax, 2
    cmp rax, [r12 + RuntimeDisplay.framebuffer_size]
    ja .done
    mov rdi, [r12 + RuntimeDisplay.framebuffer_base]
    test rdi, rdi
    jz .done
    mov ecx, 0x00181860
    cmp qword [r12 + RuntimeDisplay.pixel_format], 0
    je .color
    mov ecx, 0x00601818
.color:
    xor eax, eax
.row:
    mov rdx, rdi
    mov r8, rbx
.pixel:
    mov [rdx], ecx
    add rdx, 4
    dec r8
    jnz .pixel
    lea rdi, [rdi + r15*4]
    inc rax
    cmp rax, r14
    jb .row
    lea rsi, [rel panic_title]
    mov edi, 16
    mov edx, 30
    call text_draw
    lea r14, [rel panic_fields]
    mov r15d, 24
.field:
    lea rsi, [rel panic_labels]
    mov eax, [r14]
    add rsi, rax
    mov edi, [r14 + 8]
    mov edx, [r14 + 12]
    call text_draw
    mov eax, [r14 + 4]
    cmp eax, -1
    je .count
    mov rax, [r13 + rax]
    jmp .number
.count:
    mov rax, [rel panic_saved_frame_count]
.number:
    mov edi, [r14 + 8]
    add edi, 56
    mov edx, [r14 + 12]
    call screen_hex_draw
    add r14, 16
    dec r15d
    jnz .field
    lea rsi, [rel panic_trace_title]
    mov edi, 16
    mov edx, 354
    call text_draw
    xor r14d, r14d
    lea r15, [rel panic_saved_frames]
.trace:
    cmp r14, [rel panic_saved_frame_count]
    jae .footer
    cmp r14d, 4
    jae .footer
    mov rax, [r15 + r14*8]
    mov edi, 72
    imul edx, r14d, 20
    add edx, 374
    call screen_hex_draw
    inc r14d
    jmp .trace
.footer:
    lea rsi, [rel panic_footer]
    mov edi, 16
    mov edx, 456
    call text_draw
.done:
    add rsp, 8
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
.early:
    ret

; rax=value, edi=x, edx=y; fixed sixteen uppercase hex digits on the stack.
screen_hex_draw:
    push rbp
    mov rbp, rsp
    sub rsp, 32
    mov r8, rax
    lea r11, [rel screen_hex_digits]
    mov rsi, rsp
    mov ecx, 16
.digit:
    rol r8, 4
    mov eax, r8d
    and eax, 15
    mov al, [r11 + rax]
    mov [rsi], al
    inc rsi
    dec ecx
    jnz .digit
    mov byte [rsi], 0
    mov rsi, rsp
    call text_draw
    leave
    ret

; 功能：用自带5x7位图绘制两倍大小的 ASCII 大写文字。
; 输入：rsi=NUL 字符串，edi=x，edx=y；r12=RuntimeDisplay*。
; 输出：无。
; 破坏：调用者保存寄存器、标志；保留非易失寄存器。
; 中断/锁：中断关闭，调用方保证文字在帧缓冲范围内，无需持锁。
text_draw:
    push rbx
    push r13
    push r14
    push r15
    mov r13, rsi
    mov r14d, edi
    mov r15d, edx
.char:
    movzx eax, byte [r13]
    test eax, eax
    jz .done
    cmp eax, 32
    jb .skip
    cmp eax, 90
    ja .skip
    sub eax, 32
    imul eax, 7
    lea rbx, [rel glyphs]
    add rbx, rax
    xor r8d, r8d
.glyph_row:
    movzx r9d, byte [rbx+r8]
    xor r10d, r10d
.glyph_pixel:
    mov ecx, 4
    sub ecx, r10d
    bt r9d, ecx
    jnc .next_pixel
    lea eax, [r15d+r8d*2]
    imul rax, [r12 + RuntimeDisplay.stride]
    lea ecx, [r14d+r10d*2]
    add rax, rcx
    mov rdi, [r12 + RuntimeDisplay.framebuffer_base]
    lea rdi, [rdi+rax*4]
    mov dword [rdi], 0x00f4f4f4
    mov dword [rdi+4], 0x00f4f4f4
    mov rcx, [r12 + RuntimeDisplay.stride]
    lea rdi, [rdi+rcx*4]
    mov dword [rdi], 0x00f4f4f4
    mov dword [rdi+4], 0x00f4f4f4
.next_pixel:
    inc r10d
    cmp r10d, 5
    jb .glyph_pixel
    inc r8d
    cmp r8d, 7
    jb .glyph_row
.skip:
    add r14d, 14
    inc r13
    jmp .char
.done:
    pop r15
    pop r14
    pop r13
    pop rbx
    ret

section .rodata
entered: db "DONGOS_P1_KERNEL_HIGH_OK",13,10,0
cpu_ready: db "DONGOS_P2_CPU_READY",13,10,0
%if CPU_TEST_CASE
cpu_inject: db "DONGOS_P2_INJECT:"
%if CPU_TEST_CASE = 1
    db "int3"
%elif CPU_TEST_CASE = 2
    db "ud2"
%elif CPU_TEST_CASE = 3
    db "gp"
%elif CPU_TEST_CASE = 4
    db "pf"
%elif CPU_TEST_CASE = 5
    db "bad-stack"
%elif CPU_TEST_CASE = 6
    db "double-fault"
%elif CPU_TEST_CASE = 7
    db "divide"
%elif CPU_TEST_CASE = 8
    db "bad-frame"
%endif
    db 13,10,0
%endif
dong_ok: db "DONGOS_L1_PROBE_OK: 42",13,10,0
memory_ok: db "DONGOS_L1_MEMORY_OK: 373",13,10,0
slice_ok: db "DONGOS_L1_SLICE_ABI_OK: 765",13,10,0
constant_ok: db "DONGOS_L1_CONSTANTS_OK: 282",13,10,0
alignment_ok: db "DONGOS_L1_ALIGNMENT_OK: 458",13,10,0
global_ok: db "DONGOS_L1_GLOBALS_OK: 436",13,10,0
intrinsic_ok: db "DONGOS_L1_INTRINSICS_OK: 719",13,10,0
function_ok: db "DONGOS_L1_FUNCTIONS_OK: 761",13,10,0
l1_ok: db "DONGOS_L1_FEATURES_OK: 75",13,10,0
memory_ready: db "DONGOS_P2_MEMORY_READY",13,10,0
acpi_ready: db "DONGOS_P3_ACPI_READY",13,10,0
acpi_error: db "acpi_error=",0
%macro ACPI_KEY 1
acpi_key_%1: db "acpi_", %str(%1), "=", 0
%endmacro
    ACPI_KEY rsdp
    ACPI_KEY xsdt
    ACPI_KEY madt
    ACPI_KEY fadt
    ACPI_KEY hpet
    ACPI_KEY mcfg
    ACPI_KEY table_count
    ACPI_KEY cpu_count
    ACPI_KEY ioapic_count
    ACPI_KEY iso_count
    ACPI_KEY nmi_count
    ACPI_KEY mcfg_count
    ACPI_KEY lapic_address
    ACPI_KEY madt_flags
    ACPI_KEY fadt_flags
    ACPI_KEY boot_arch
    ACPI_KEY pm_timer_block
    ACPI_KEY pm_timer_length
    ACPI_KEY pm_timer_32bit
    ACPI_KEY hpet_gas_info
    ACPI_KEY hpet_address
    ACPI_KEY pm_timer_gas_info
    ACPI_KEY pm_timer_address
    ACPI_KEY steps
%unmacro ACPI_KEY 1
stack_ready: db "DONGOS_P2_STACK_READY",13,10,0
preflight_ready: db "DONGOS_P2_PREFLIGHT_READY",13,10,0
memory_error: db "memory_error=",0
memory_hex_digits: db "0123456789abcdef"
%macro MEMORY_KEY 1
memory_key_%1: db "memory_",%str(%1),"=",0
%endmacro
    MEMORY_KEY physical_bits
    MEMORY_KEY nx
    MEMORY_KEY resource_count
    MEMORY_KEY arena_base
    MEMORY_KEY arena_pages
    MEMORY_KEY usable_pages
    MEMORY_KEY free_pages
    MEMORY_KEY pool_physical
    MEMORY_KEY pool_pages
    MEMORY_KEY root_physical
    MEMORY_KEY table_count
    MEMORY_KEY mapped_pages
    MEMORY_KEY pat_value
    MEMORY_KEY stack_physical
    MEMORY_KEY stack_pages
    MEMORY_KEY stack_bottom
    MEMORY_KEY stack_top
    MEMORY_KEY bridge_value
    MEMORY_KEY runtime_view
    MEMORY_KEY runtime_boot_info
    MEMORY_KEY runtime_raw_map
    MEMORY_KEY runtime_rsdp
    MEMORY_KEY runtime_framebuffer
    MEMORY_KEY runtime_pool
    MEMORY_KEY ist_guard_pages
    MEMORY_KEY cr3_before
    MEMORY_KEY cr3_after
    MEMORY_KEY cr0_before
    MEMORY_KEY cr0_after
    MEMORY_KEY cr4_before
    MEMORY_KEY cr4_after
    MEMORY_KEY efer_before
    MEMORY_KEY efer_after
    MEMORY_KEY rflags_before
    MEMORY_KEY rflags_after
    MEMORY_KEY planned_cr0
    MEMORY_KEY planned_efer
    MEMORY_KEY planned_actions
    MEMORY_KEY kind
    MEMORY_KEY base
    MEMORY_KEY length
%unmacro MEMORY_KEY 1
activation_ready: db "DONGOS_P2_ACTIVATION_READY",13,10,0
activation_inject: db "DONGOS_P2_ACTIVATION_INJECT",13,10,0
activation_error: db "activation_error=",0
mutation_ready: db "DONGOS_P2_MUTATION_READY",13,10,0
mutation_inject: db "DONGOS_P2_MUTATION_INJECT",13,10,0
hardening_ready: db "DONGOS_P2_HARDENING_READY",13,10,0
object_memory_ready: db "DONGOS_P2_CACHE_READY",13,10,0
object_memory_inject: db "DONGOS_P2_CACHE_UNMAP_INJECT",13,10,0
object_memory_error: db "cache_error=",0
%macro OBJECT_MEMORY_KEY 1
object_memory_key_%1: db "cache_",%str(%1),"=",0
%endmacro
    OBJECT_MEMORY_KEY root
    OBJECT_MEMORY_KEY virtual
    OBJECT_MEMORY_KEY physical
    OBJECT_MEMORY_KEY reused_physical
    OBJECT_MEMORY_KEY object_size
    OBJECT_MEMORY_KEY alignment
    OBJECT_MEMORY_KEY capacity
    OBJECT_MEMORY_KEY allocated
    OBJECT_MEMORY_KEY oom_error
    OBJECT_MEMORY_KEY busy_error
    OBJECT_MEMORY_KEY reused_object
    OBJECT_MEMORY_KEY free_before
    OBJECT_MEMORY_KEY free_held
    OBJECT_MEMORY_KEY free_after
    OBJECT_MEMORY_KEY tables_before
    OBJECT_MEMORY_KEY tables_peak
    OBJECT_MEMORY_KEY tables_after
    OBJECT_MEMORY_KEY invlpg_count
    OBJECT_MEMORY_KEY reload_count
    OBJECT_MEMORY_KEY retired_tables
    OBJECT_MEMORY_KEY checksum
    OBJECT_MEMORY_KEY steps
    OBJECT_MEMORY_KEY cr4
    OBJECT_MEMORY_KEY rflags
%unmacro OBJECT_MEMORY_KEY 1
hardening_error: db "hardening_error=",0
%macro HARDENING_KEY 1
hardening_key_%1: db "hardening_",%str(%1),"=",0
%endmacro
    HARDENING_KEY max_basic
    HARDENING_KEY leaf7_ebx
    HARDENING_KEY leaf7_ecx
    HARDENING_KEY supported
    HARDENING_KEY cr4_before
    HARDENING_KEY cr4_after
    HARDENING_KEY rflags_before
    HARDENING_KEY rflags_after
    HARDENING_KEY cr0
    HARDENING_KEY cr3
    HARDENING_KEY efer
    HARDENING_KEY pat
    HARDENING_KEY steps
%unmacro HARDENING_KEY 1
mutation_error: db "mutation_error=",0
%macro MUTATION_KEY 1
mutation_key_%1: db "mutation_",%str(%1),"=",0
%endmacro
    MUTATION_KEY root
    MUTATION_KEY virtual
    MUTATION_KEY physical_a
    MUTATION_KEY physical_b
    MUTATION_KEY read_a
    MUTATION_KEY read_b
    MUTATION_KEY write_value
    MUTATION_KEY reuse_value
    MUTATION_KEY tables_before
    MUTATION_KEY tables_peak
    MUTATION_KEY tables_after
    MUTATION_KEY invlpg_count
    MUTATION_KEY reload_count
    MUTATION_KEY retired_tables
    MUTATION_KEY first_branch
    MUTATION_KEY reused_branch
    MUTATION_KEY cr3_after
    MUTATION_KEY steps
%unmacro MUTATION_KEY 1
%macro ACTIVATION_KEY 1
activation_key_%1: db "activation_",%str(%1),"=",0
%endmacro
    ACTIVATION_KEY cr3
    ACTIVATION_KEY cr0
    ACTIVATION_KEY cr4
    ACTIVATION_KEY efer
    ACTIVATION_KEY pat
    ACTIVATION_KEY rflags
    ACTIVATION_KEY entry_rsp
    ACTIVATION_KEY entry_rbp
    ACTIVATION_KEY rsp
    ACTIVATION_KEY rbp
    ACTIVATION_KEY nested_value
    ACTIVATION_KEY display_value
    ACTIVATION_KEY runtime_value
    ACTIVATION_KEY cache_steps
%unmacro ACTIVATION_KEY 1
; All absolute high-half addresses use 64-bit relocations.
%if __NASM_MAJOR__ >= 3
[warning push]
[warning -reloc-abs-qword]
%endif
align 8
memory_layout:
%if MEMORY_TEST_BAD_LAYOUT
    dq __kernel_text_start + 4096, __kernel_text_end
%else
    dq __kernel_text_start, __kernel_text_end
%endif
    dq __kernel_rodata_start, __kernel_rodata_end
    dq __kernel_data_start, __kernel_data_end
    dq __kernel_bss_start, __kernel_bss_end
    dq cpu_gdt, cpu_gdt_end, cpu_tss, cpu_tss_end, cpu_idt, cpu_idt_end
%if MEMORY_TEST_BAD_IST
    dq cpu_df_stack_bottom + 4096, cpu_df_stack_top
%else
    dq cpu_df_stack_bottom, cpu_df_stack_top
%endif
    dq cpu_nmi_stack_bottom, cpu_nmi_stack_top
    dq cpu_exception_stack_bottom, cpu_exception_stack_top
    dq 0, 0, 0 ; workspace and RSDP size filled from actual runtime storage
%if __NASM_MAJOR__ >= 3
[warning pop]
%endif
passed: db "DONGOS_P1_PASS",13,10,0
failed: db "DONGOS_P1_KERNEL_FAIL",13,10,0
title: db "DONGOS P3 ACPI READY",0
subtitle: db "UEFI OFF GDT TSS IDT OK",0
mappings: db "HIGH HALF AND HHDM OK",0
compiler: db "DONGC RESULT 42",0
memory_title: db "MEMORY TYPES 373",0
slice_title: db "SLICE AND ABI 765",0
constant_title: db "ALIASES AND CONSTANTS 282",0
alignment_title: db "ALIGNED STACK 458",0
global_title: db "GLOBAL STORAGE 436",0
intrinsic_title: db "MEMORY INTRINSICS 719",0
function_title: db "FUNCTIONS AND WIN64 761",0
l1_title: db "L1 LANGUAGE FEATURES 75",0
panic_title: db "DONGOS KERNEL PANIC",0
panic_trace_title: db "CALL TRACE",0
panic_footer: db "HALTED RESET REQUIRED",0
screen_hex_digits: db "0123456789ABCDEF"
panic_labels:
.vec: db "VEC",0
.err: db "ERR",0
.rip: db "RIP",0
.rsp: db "RSP",0
.cr2: db "CR2",0
.flg: db "FLG",0
.cs: db "CS",0
.bt: db "BT",0
.rax: db "RAX",0
.rbx: db "RBX",0
.rcx: db "RCX",0
.rdx: db "RDX",0
.rsi: db "RSI",0
.rdi: db "RDI",0
.rbp: db "RBP",0
.r8: db "R8",0
.r9: db "R9",0
.r10: db "R10",0
.r11: db "R11",0
.r12: db "R12",0
.r13: db "R13",0
.r14: db "R14",0
.r15: db "R15",0
.ss: db "SS",0
; Relative label offsets avoid any narrow absolute relocation in the high half.
panic_fields:
%macro PANIC_FIELD 4
    dd panic_labels.%1 - panic_labels, %2, %3, %4
%endmacro
    PANIC_FIELD vec, ExceptionContext.vector, 16, 70
    PANIC_FIELD err, ExceptionContext.error, 336, 70
    PANIC_FIELD rip, ExceptionContext.rip, 16, 94
    PANIC_FIELD rsp, ExceptionContext.rsp, 336, 94
    PANIC_FIELD cr2, ExceptionContext.cr2, 16, 118
    PANIC_FIELD flg, ExceptionContext.rflags, 336, 118
    PANIC_FIELD cs, ExceptionContext.cs, 16, 142
    PANIC_FIELD bt, -1, 336, 142
    PANIC_FIELD rax, ExceptionContext.rax, 16, 166
    PANIC_FIELD rbx, ExceptionContext.rbx, 336, 166
    PANIC_FIELD rcx, ExceptionContext.rcx, 16, 190
    PANIC_FIELD rdx, ExceptionContext.rdx, 336, 190
    PANIC_FIELD rsi, ExceptionContext.rsi, 16, 214
    PANIC_FIELD rdi, ExceptionContext.rdi, 336, 214
    PANIC_FIELD rbp, ExceptionContext.rbp, 16, 238
    PANIC_FIELD r8, ExceptionContext.r8, 336, 238
    PANIC_FIELD r9, ExceptionContext.r9, 16, 262
    PANIC_FIELD r10, ExceptionContext.r10, 336, 262
    PANIC_FIELD r11, ExceptionContext.r11, 16, 286
    PANIC_FIELD r12, ExceptionContext.r12, 336, 286
    PANIC_FIELD r13, ExceptionContext.r13, 16, 310
    PANIC_FIELD r14, ExceptionContext.r14, 336, 310
    PANIC_FIELD r15, ExceptionContext.r15, 16, 334
    PANIC_FIELD ss, ExceptionContext.ss, 336, 334
%unmacro PANIC_FIELD 4
; Original minimal 5x7 glyphs. ASCII32..90; unused punctuation is blank.
glyphs:
    times (48-32)*7 db 0
    db 14,17,19,21,25,17,14 ; 0
    db 4,12,4,4,4,4,14 ; 1
    db 14,17,1,2,4,8,31 ; 2
    db 30,1,1,14,1,1,30 ; 3
    db 2,6,10,18,31,2,2 ; 4
    db 31,16,16,30,1,1,30 ; 5
    db 14,16,16,30,17,17,14 ; 6
    db 31,1,2,4,8,8,8 ; 7
    db 14,17,17,14,17,17,14 ; 8
    db 14,17,17,15,1,1,14 ; 9
    times (65-58)*7 db 0
    db 14,17,17,31,17,17,17 ; A
    db 30,17,17,30,17,17,30 ; B
    db 14,17,16,16,16,17,14 ; C
    db 30,17,17,17,17,17,30 ; D
    db 31,16,16,30,16,16,31 ; E
    db 31,16,16,30,16,16,16 ; F
    db 14,17,16,23,17,17,15 ; G
    db 17,17,17,31,17,17,17 ; H
    db 14,4,4,4,4,4,14 ; I
    db 7,2,2,2,2,18,12 ; J
    db 17,18,20,24,20,18,17 ; K
    db 16,16,16,16,16,16,31 ; L
    db 17,27,21,21,17,17,17 ; M
    db 17,25,21,19,17,17,17 ; N
    db 14,17,17,17,17,17,14 ; O
    db 30,17,17,30,16,16,16 ; P
    db 14,17,17,17,21,18,13 ; Q
    db 30,17,17,30,20,18,17 ; R
    db 15,16,16,14,1,1,30 ; S
    db 31,4,4,4,4,4,4 ; T
    db 17,17,17,17,17,17,14 ; U
    db 17,17,17,17,17,10,4 ; V
    db 17,17,17,21,21,21,10 ; W
    db 17,17,10,4,10,17,17 ; X
    db 17,17,10,4,4,4,4 ; Y
    db 31,1,2,4,8,16,31 ; Z

section .bss
align 8, resb 1
memory_report: resb MemoryReport_size
memory_info_physical: resq 1
memory_display: resb RuntimeDisplay_size
memory_controls_before: resb ControlState_size
memory_controls_after: resb ControlState_size
memory_control_plan: resb ControlPlan_size
memory_controls_active: resb ControlState_size
cpu_hardening_report: resb HardeningReport_size
memory_activation_report: resb ActivationReport_size
memory_mutation_report: resb MutationReport_size
object_memory_report: resb ObjectMemoryReport_size
global p3_acpi_report, p3_acpi_report_end, p3_acpi_inventory
p3_acpi_report: resb AcpiReport_size
p3_acpi_report_end:
p3_acpi_inventory: resq 1
memory_raw_first: resq 1
%if RUNTIME_LEVEL >= 5
service_handoff_physical: resq 1
trace_handoff_physical: resq 1
trace_handoff_tag: resq 1
trace_entry_stamp: resq 3
%endif
