; Private arena header. The first 112 bytes retain user_smp.inc exactly.
%ifndef DONGOS_USER_ENTRY_INC
%define DONGOS_USER_ENTRY_INC
%include "user_smp.inc"
%include "cpu.inc"
struc UserEntryCpu
 .prefix: resb UserSmpCpu_size
 .gdt: resq 1
 .tss: resq 1
 .idt: resq 1
 .stack_bottom: resq 1
 .df_top: resq 1
 .nmi_top: resq 1
 .exception_top: resq 1
 .kernel_xstate: resq 1
 .capture: resq 1
 .returned: resq 1
 .return_xstate: resq 1
 .ready: resq 1
 .last_error: resq 1
 .event: resq 1
 .raw_frame: resq 1
 .deadline_ticks: resq 1
 .tsc_hz: resq 1
 .timer_hz: resq 1
endstruc
USER_ENTRY_SYSCALL equ 256
USER_ENTRY_IDLE equ 257
USER_ENTRY_ERR equ 0x060b0001
USER_ENTRY_MAGIC equ 0x55534552534d5036
struc UserEntryMetrics
 .switches:resq 1
 .retained:resq 1
 .user_timers:resq 1
 .user_entries:resq 1
 .last_vector:resq 1
 .failed:resq 1
 .gs_base:resq 1
 .kernel_gs_base:resq 1
 .fs_base:resq 1
 .efer:resq 1
 .star:resq 1
 .lstar:resq 1
 .fmask:resq 1
 .gdtr_base:resq 1
 .gdtr_limit:resq 1
 .idtr_base:resq 1
 .idtr_limit:resq 1
 .tr:resq 1
 .cr4:resq 1
 .xcr0:resq 1
 .rsp0:resq 1
 .reserved:resq 3
endstruc
%endif
