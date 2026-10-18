%ifndef DONGOS_BOOT_TRACE_INC
%define DONGOS_BOOT_TRACE_INC
BOOT_TRACE_MAGIC equ 0x3145434152544244
BOOT_TRACE_VERSION equ 1
BOOT_TRACE_BYTES equ 4096
BOOT_TRACE_CAPACITY equ 80
BOOT_TRACE_MARK equ 0x89
struc BootTraceStamp
 .tsc: resq 1
 .cpu: resq 1
 .flags: resq 1
endstruc
%if BootTraceStamp_size != 24
%error Boot trace sample must be24 bytes
%endif
%endif
