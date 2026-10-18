; BSP scheduler/IRQ ABI. Existing fatal ExceptionContext remains untouched.
%ifndef DONGOS_SCHED_INC
%define DONGOS_SCHED_INC
%include "cpu.inc"
SCHED_VECTOR equ 0x40
SCHED_ENGINE_SIZE equ 448
SCHED_THREAD_SIZE equ 48
SCHED_THREADS equ 64
SCHED_CURRENT equ 0
SCHED_TICKS equ 8
SCHED_SWITCHES equ 16
SCHED_THREAD_TICKS equ 16
SCHED_THREAD_FRAME equ 32
SCHED_XSTATE_STRIDE equ 1024
SCHED_STACK_SIZE equ 16384
struc SchedReport
 .version: resq 1
 .vector: resq 1
 .ticks: resq 1
 .switches: resq 1
 .worker0_count: resq 1
 .worker1_count: resq 1
 .worker0_ticks: resq 1
 .worker1_ticks: resq 1
 .worker0_fail: resq 1
 .worker1_fail: resq 1
 .gpr_checks: resq 1
 .xstate_mode: resq 1
 .xstate_bytes: resq 1
 .xcr0: resq 1
 .cpuid1_ecx: resq 1
 .cpuid1_edx: resq 1
 .cpuidd_eax: resq 1
 .cpuidd_edx: resq 1
 .cr0: resq 1
 .cr4: resq 1
 .bootstrap_rsp: resq 1
 .worker0_rsp: resq 1
 .worker1_rsp: resq 1
 .worker0_stack_bottom: resq 1
 .worker0_stack_top: resq 1
 .worker1_stack_bottom: resq 1
 .worker1_stack_top: resq 1
 .restore_checks: resq 1
 .guard_count: resq 1
 .steps: resq 1
endstruc
%endif
