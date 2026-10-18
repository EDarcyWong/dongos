%ifndef DONGOS_SMP_INC
%define DONGOS_SMP_INC
%include "cpu.inc"
SMP_STOP_VECTOR equ 0xf0
SMP_PING_VECTOR equ 0xf1
SMP_TLB_VECTOR equ 0xf2
SMP_STARTING equ 3
SMP_ONLINE equ 4
SMP_STOPPING equ 5
SMP_STOPPED equ 6
SMP_QUARANTINED equ 8
SMP_ERR_ARGUMENT equ 0x06020001
SMP_ERR_FEATURE equ 0x06020002
SMP_ERR_ABORTED equ 0x06020003
SMP_ERR_TIMEOUT equ 0x06020004
SMP_ERR_APIC equ 0x06020005
struc SmpContext
 .self: resq 1
 .logical_id: resq 1
 .apic_id: resq 1
 .state: resq 1
 .epoch: resq 1
 .cr3: resq 1
 .cr0: resq 1
 .cr4: resq 1
 .efer: resq 1
 .pat: resq 1
 .xcr0: resq 1
 .stack_bottom: resq 1
 .stack_top: resq 1
 .gdt: resq 1
 .tss: resq 1
 .idt: resq 1
 .df_bottom: resq 1
 .df_top: resq 1
 .nmi_bottom: resq 1
 .nmi_top: resq 1
 .exception_bottom: resq 1
 .exception_top: resq 1
 .lapic_pa: resq 1
 .lapic_va: resq 1
 .main: resq 1
 .online_epoch: resq 1
 .ping_request: resq 1
 .ping_ack: resq 1
 .stop_request: resq 1
 .stop_ack: resq 1
 .irq_count: resq 1
 .last_error: resq 1
endstruc
struc SmpMailbox
 .sequence: resq 1
 .virtual: resq 1
 .scope: resq 1
 .ack: resq 1
 .expected: resq 1
 .observed: resq 1
 .fault: resq 1
 .reserved: resq 1
endstruc
struc SmpStress
 .ready: resq 1
 .iterations: resq 1
 .checksum: resq 1
 .gpr_checks: resq 1
 .xstate_checks: resq 1
 .errors: resq 1
 .start_tsc: resq 1
 .end_tsc: resq 1
endstruc
%endif
