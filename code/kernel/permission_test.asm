; Destructive, BSP-only permission experiments. Linked only into isolated tests.
; The test CPU profile supplies CR4.SMEP/SMAP/UMIP; this helper never changes CR4.
bits 64
default rel
%include "bootinfo.inc"
%include "runtime_view.inc"
%include "control_state.inc"
%include "permission_test.inc"
%ifndef P1_TEST
    %error "permission_test.asm requires P1_TEST"
%endif
%ifndef PERMISSION_TEST_CASE
    %error "PERMISSION_TEST_CASE must select an isolated test"
%endif
%if PERMISSION_TEST_CASE < 1 || PERMISSION_TEST_CASE > 12
    %error "PERMISSION_TEST_CASE must be 1..12"
%endif

global permission_test_inject, permission_test_expected_rip
global permission_test_mid_return, permission_test_inject_return
global permission_test_leaf_return
global permission_code_page, permission_code_page_end
global permission_data_page, permission_stack_page
global permission_pdpt, permission_pd, permission_pt
global permission_shadow_gdt, permission_shadow_gdt_end
global permission_user_call_stub, permission_user_sgdt, permission_user_sidt
global permission_user_sldt, permission_user_smsw, permission_user_str
global permission_user_exit_hlt
extern cpu_gdt, cpu_idt, memory_read_controls, serial_write, serial_hex_line
extern kernel_fail

section .text
; rdi=RuntimeView*. This entry point intentionally never returns to the kernel.
permission_test_inject:
    push rbp
    mov rbp, rsp
    cld
    cli
    call permission_prepare
    call permission_write_report
    lea rsi, [rel permission_ready_message]
    call serial_write
    lea rsi, [rel permission_inject_message]
    call serial_write
    call permission_test_mid
permission_test_inject_return:
    ud2

; Build fresh, disjoint user aliases. The low root entry has no previous owner.
permission_prepare:
    push rbp
    mov rbp, rsp
    mov rax, [rdi + RuntimeView.boot_info]
    mov rbx, [rax + BootInfo.kernel_physical]
    mov rax, cr3
    mov rdx, HHDM_BASE
    add rax, rdx
    cmp qword [rax], 0
    jne kernel_fail
    mov [rel permission_root_address], rax
    lea rdi, [rel permission_pdpt]
    xor eax, eax
    mov ecx, 3*4096/8
    rep stosq

%macro PERMISSION_PA 2
    lea rax, [rel %1]
    mov rdx, KERNEL_BASE
    sub rax, rdx
    add rax, rbx
    mov [rel %2], rax
%endmacro
    PERMISSION_PA permission_code_page, permission_report_code_pa
    PERMISSION_PA permission_data_page, permission_report_data_pa
    PERMISSION_PA permission_stack_page, permission_report_stack_pa
    PERMISSION_PA permission_pdpt, permission_pdpt_physical
    PERMISSION_PA permission_pd, permission_pd_physical
    PERMISSION_PA permission_pt, permission_pt_physical
%unmacro PERMISSION_PA 2

    mov rax, [rel permission_pd_physical]
    or rax, 7
    mov [rel permission_pdpt + 8], rax ; VA[38:30] = 1
    mov rax, [rel permission_pt_physical]
    or rax, 7
    mov [rel permission_pd], rax
    mov rax, [rel permission_report_code_pa]
    or rax, 5                       ; present, user, read/execute
%if PERMISSION_TEST_CASE = 3
    bts rax, 63                     ; NX control: SMEP is disabled by profile
%endif
    mov [rel permission_pt], rax
    mov rax, [rel permission_report_data_pa]
    or rax, 7
    bts rax, 63
    mov [rel permission_pt + 8], rax
    mov rax, [rel permission_report_stack_pa]
    or rax, 7
    bts rax, 63
    mov [rel permission_pt + 16], rax
    mov rax, PERMISSION_TOKEN
    mov [rel permission_data_page], rax
    mov qword [rel permission_report_steps], 1
    mov rax, [rel permission_pdpt_physical]
    or rax, 7
    mov rdx, [rel permission_root_address]
    mov [rdx], rax                  ; single aligned publication into empty slot
    mov rax, cr3
    mov cr3, rax                    ; real local TLB/paging-cache invalidation
    or qword [rel permission_report_steps], 2

    ; Preserve the loaded, busy TSS descriptor and the original kernel selectors.
    ; Appending DPL3 segments changes neither the IDT nor the exception IST stacks.
    lea rsi, [rel cpu_gdt]
    lea rdi, [rel permission_shadow_gdt]
    mov ecx, 5
    rep movsq
    mov rax, 0x00affb000000ffff
    mov [rel permission_shadow_gdt + 40], rax
    mov rax, 0x00cff3000000ffff
    mov [rel permission_shadow_gdt + 48], rax
    mov word [rel permission_shadow_gdtr], 55
    lea rax, [rel permission_shadow_gdt]
    mov [rel permission_shadow_gdtr + 2], rax
    lgdt [rel permission_shadow_gdtr]
    sgdt [rel permission_descriptor]
    movzx eax, word [rel permission_descriptor]
    mov [rel permission_report_gdt_limit], rax
    mov rax, [rel permission_descriptor + 2]
    mov [rel permission_report_gdt_base], rax
    sidt [rel permission_descriptor]
    movzx eax, word [rel permission_descriptor]
    mov [rel permission_report_idt_limit], rax
    mov rax, [rel permission_descriptor + 2]
    mov [rel permission_report_idt_base], rax
    xor eax, eax
    sldt ax
    mov [rel permission_report_ldtr], rax ; actual baseline, no LLDT assumption
    xor eax, eax
    str ax
    mov [rel permission_report_tr], rax
    xor eax, eax
    smsw ax
    ; The report ABI is the 16-bit MSW, matching the user memory destination.
    ; Normalize explicitly even if the register encoding exposes more of CR0.
    movzx eax, ax
    mov [rel permission_report_msw], rax
    or qword [rel permission_report_steps], 4

%if PERMISSION_TEST_CASE = 4 || PERMISSION_TEST_CASE = 5
    mov rax, cr4
    bt rax, 21
    jnc kernel_fail
    mov eax, PERMISSION_USER_DATA
    stac
    pushfq
    pop rdx
    mov [rel permission_report_ac_flags], rdx
    mov rcx, [rax]
    mov [rel permission_report_ac_read], rcx
    mov rdx, PERMISSION_WRITE
    mov [rax], rdx
    mov rcx, [rax]
    mov [rel permission_report_ac_write], rcx
    clac
    ; The high alias is supervisor memory and remains usable at AC=0.
    mov rax, PERMISSION_TOKEN
    mov [rel permission_data_page], rax
    cmp [rel permission_report_ac_read], rax
    jne kernel_fail
    cmp [rel permission_report_ac_write], rdx
    jne kernel_fail
    or qword [rel permission_report_steps], 8
%elif PERMISSION_TEST_CASE = 6
    mov rax, cr4
    bt rax, 21
    jc kernel_fail
    mov eax, PERMISSION_USER_DATA
    pushfq
    pop rdx
    bt rdx, 18
    jc kernel_fail
    mov [rel permission_report_ac_flags], rdx
    mov rcx, [rax]
    mov [rel permission_report_ac_read], rcx
    mov rdx, PERMISSION_WRITE
    mov [rax], rdx
    mov rcx, [rax]
    mov [rel permission_report_ac_write], rcx
    mov rax, PERMISSION_TOKEN
    mov [rel permission_data_page], rax
    cmp [rel permission_report_ac_read], rax
    jne kernel_fail
    cmp [rel permission_report_ac_write], rdx
    jne kernel_fail
%endif

    lea rdi, [rel permission_controls]
    call memory_read_controls
%macro PERMISSION_CONTROL 1
    mov rax, [rel permission_controls + ControlState.%1]
    mov [rel permission_report_%1], rax
%endmacro
    PERMISSION_CONTROL cr0
    PERMISSION_CONTROL cr3
    PERMISSION_CONTROL cr4
    PERMISSION_CONTROL efer
    PERMISSION_CONTROL pat
    PERMISSION_CONTROL rflags
%unmacro PERMISSION_CONTROL 1
    test qword [rel permission_report_rflags], (1 << 18) | (1 << 9)
    jnz kernel_fail
    mov qword [rel permission_report_case_id], PERMISSION_TEST_CASE
    mov qword [rel permission_report_code_va], PERMISSION_USER_CODE
    mov qword [rel permission_report_data_va], PERMISSION_USER_DATA
    mov qword [rel permission_report_stack_top], PERMISSION_STACK_TOP
%if PERMISSION_TEST_CASE <= 3
    mov eax, PERMISSION_USER_CODE
%elif PERMISSION_TEST_CASE <= 6
    lea rax, [rel permission_test_expected_rip]
%elif PERMISSION_TEST_CASE = 7
    mov rax, PERMISSION_USER_CODE + permission_user_sgdt - permission_code_page
%elif PERMISSION_TEST_CASE = 8
    mov rax, PERMISSION_USER_CODE + permission_user_sidt - permission_code_page
%elif PERMISSION_TEST_CASE = 9
    mov rax, PERMISSION_USER_CODE + permission_user_sldt - permission_code_page
%elif PERMISSION_TEST_CASE = 10
    mov rax, PERMISSION_USER_CODE + permission_user_smsw - permission_code_page
%elif PERMISSION_TEST_CASE = 11
    mov rax, PERMISSION_USER_CODE + permission_user_str - permission_code_page
%else
    mov rax, PERMISSION_USER_CODE + permission_user_exit_hlt - permission_code_page
%endif
    mov [rel permission_report_probe_rip], rax
    mov rdx, [rel permission_root_address]
    mov rax, [rdx]
    mov [rel permission_report_code_pml4], rax
    mov [rel permission_report_data_pml4], rax
    mov [rel permission_report_stack_pml4], rax
    mov rax, [rel permission_pdpt + 8]
    mov [rel permission_report_code_pdpt], rax
    mov [rel permission_report_data_pdpt], rax
    mov [rel permission_report_stack_pdpt], rax
    mov rax, [rel permission_pd]
    mov [rel permission_report_code_pd], rax
    mov [rel permission_report_data_pd], rax
    mov [rel permission_report_stack_pd], rax
    mov rax, [rel permission_pt]
    mov [rel permission_report_code_pte], rax
    mov rax, [rel permission_pt + 8]
    mov [rel permission_report_data_pte], rax
    mov rax, [rel permission_pt + 16]
    mov [rel permission_report_stack_pte], rax
    ; #GP does not update CR2. Give the CPL3 probes a deterministic baseline.
    xor eax, eax
    mov cr2, rax
    leave
    ret

permission_write_report:
    push rbp
    mov rbp, rsp
%macro PERMISSION_PRINT_FIELD 1
    lea rsi, [rel permission_key_%1]
    call serial_write
    mov rax, [rel permission_report_%1]
    call serial_hex_line
%endmacro
    PERMISSION_FIELDS PERMISSION_PRINT_FIELD
%unmacro PERMISSION_PRINT_FIELD 1
    leave
    ret

permission_test_mid:
    push rbp
    mov rbp, rsp
    call permission_test_leaf
permission_test_mid_return:
    ud2

permission_test_leaf:
    push rbp
    mov rbp, rsp
%if PERMISSION_TEST_CASE >= 7
    ; Hardware exceptions use the existing IST. No DPL3 software interrupt gate
    ; and no untrusted user-frame walking are introduced by this test.
    push qword 0x33
    push qword PERMISSION_STACK_TOP
    push qword 2
    push qword 0x2b
%if PERMISSION_TEST_CASE = 12
    mov rax, PERMISSION_USER_CODE + permission_user_sgdt - permission_code_page
%else
    mov rax, [rel permission_report_probe_rip]
%endif
    push rax
%endif
    mov rax, 0x1111111111111111
    mov rbx, 0x2222222222222222
    mov rcx, 0x3333333333333333
    mov rdx, 0x4444444444444444
    mov rsi, 0x5555555555555555
    mov rdi, 0x6666666666666666
    mov r8,  0x8888888888888888
    mov r9,  0x9999999999999999
    mov r10, 0xaaaaaaaaaaaaaaaa
    mov r11, 0xbbbbbbbbbbbbbbbb
    mov r12, 0xcccccccccccccccc
    mov r13, 0xdddddddddddddddd
    mov r14, 0xeeeeeeeeeeeeeeee
    mov r15, 0xffffffffffffffff
%if PERMISSION_TEST_CASE >= 7
    mov ebp, 0
    mov edi, PERMISSION_USER_DATA
permission_test_expected_rip:
    iretq
%elif PERMISSION_TEST_CASE <= 3
    mov eax, PERMISSION_USER_CODE
    std
permission_test_expected_rip:
    call rax
permission_test_leaf_return:
%if PERMISSION_TEST_CASE = 2
    cld
    mov rdx, PERMISSION_TOKEN
    cmp rax, rdx
    jne kernel_fail
    jmp permission_pass
%else
    jmp kernel_fail
%endif
%else
    mov eax, PERMISSION_USER_DATA
    std
permission_test_expected_rip:
%if PERMISSION_TEST_CASE = 5
    mov byte [rax], 0x5a
%else
    mov rbx, [rax]
%endif
permission_test_leaf_return:
%if PERMISSION_TEST_CASE = 6
    cld
    mov rdx, PERMISSION_TOKEN
    cmp rbx, rdx
    jne kernel_fail
    mov rdx, PERMISSION_WRITE
    mov [rax], rdx
    cmp [rax], rdx
    jne kernel_fail
    jmp permission_pass
%else
    jmp kernel_fail
%endif
%endif
%if PERMISSION_TEST_CASE >= 7
permission_test_leaf_return:
    ud2
%endif

permission_pass:
    cld
    lea rsi, [rel permission_pass_message]
    call serial_write
    mov eax, 0x14                    ; isa-debug-exit reports (0x14 << 1) | 1
    out 0xf4, eax
    cli
.halt:
    hlt
    jmp .halt

; One entire physical code page: the aliases expose no adjacent kernel code.
align 4096, db 0x90
permission_code_page:
permission_user_call_stub:
    mov rax, PERMISSION_TOKEN
    ret
    times 16-($-permission_code_page) db 0x90
permission_user_sgdt:
    sgdt [rdi]
permission_user_sidt:
    sidt [rdi + 16]
permission_user_sldt:
    sldt word [rdi + 32]
permission_user_smsw:
    smsw word [rdi + 34]
permission_user_str:
    str word [rdi + 36]
    mov rax, [rdi + 2]
    mov rbx, [rdi + 18]
    movzx ecx, word [rdi]
    movzx edx, word [rdi + 16]
    movzx esi, word [rdi + 32]
    movzx r8d, word [rdi + 36]
    movzx edi, word [rdi + 34]
    pushfq
    pop r9
permission_user_exit_hlt:
    hlt
    ud2
    times 4096-($-permission_code_page) db 0x90
permission_code_page_end:

section .rodata
%macro PERMISSION_KEY 1
permission_key_%1: db "permission_", %str(%1), "=", 0
%endmacro
    PERMISSION_FIELDS PERMISSION_KEY
%unmacro PERMISSION_KEY 1
permission_ready_message: db "DONGOS_P2_PERMISSION_READY", 13, 10, 0
permission_inject_message: db "DONGOS_P2_PERMISSION_INJECT", 13, 10, 0
permission_pass_message: db "DONGOS_P2_PERMISSION_PASS", 13, 10, 0

section .bss
align 8, resb 1
global permission_report, permission_report_end
permission_report:
%macro PERMISSION_FIELD 1
global permission_report_%1
permission_report_%1: resq 1
%endmacro
    PERMISSION_FIELDS PERMISSION_FIELD
%unmacro PERMISSION_FIELD 1
permission_report_end:
permission_controls: resb ControlState_size
permission_root_address: resq 1
permission_pdpt_physical: resq 1
permission_pd_physical: resq 1
permission_pt_physical: resq 1
align 16, resb 1
permission_descriptor: resb 16
permission_shadow_gdtr: resb 16
permission_shadow_gdt: resb 56
permission_shadow_gdt_end:
align 4096, resb 1
permission_pdpt: resb 4096
permission_pd: resb 4096
permission_pt: resb 4096
permission_data_page: resb 4096
permission_stack_page: resb 4096

section .note.GNU-stack noalloc noexec nowrite progbits
