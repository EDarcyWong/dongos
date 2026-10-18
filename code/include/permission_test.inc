; Isolated P2 permission probe ABI. No production entry point uses these values.
%ifndef DONGOS_PERMISSION_TEST_INC
%define DONGOS_PERMISSION_TEST_INC
%define PERMISSION_USER_CODE  0x40000000
%define PERMISSION_USER_DATA  0x40001000
%define PERMISSION_USER_STACK 0x40002000
%define PERMISSION_STACK_TOP  0x40003000
%define PERMISSION_TOKEN      0x1122334455667788
%define PERMISSION_WRITE      0x55aa33cc77ee9900
%macro PERMISSION_FIELDS 1
    %1 case_id
    %1 cr0
    %1 cr3
    %1 cr4
    %1 efer
    %1 pat
    %1 rflags
    %1 ac_flags
    %1 ac_read
    %1 ac_write
    %1 code_va
    %1 data_va
    %1 stack_top
    %1 probe_rip
    %1 code_pa
    %1 data_pa
    %1 stack_pa
    %1 code_pml4
    %1 code_pdpt
    %1 code_pd
    %1 code_pte
    %1 data_pml4
    %1 data_pdpt
    %1 data_pd
    %1 data_pte
    %1 stack_pml4
    %1 stack_pdpt
    %1 stack_pd
    %1 stack_pte
    %1 gdt_base
    %1 gdt_limit
    %1 idt_base
    %1 idt_limit
    %1 ldtr
    %1 tr
    %1 msw
    %1 steps
%endmacro
%endif
