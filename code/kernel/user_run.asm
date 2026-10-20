; Actual CPL3 ELF/IPC integration; the user programs are independent ET_DYNs.
bits 64
default rel
%include "bootinfo.inc"
%include "runtime_view.inc"
%include "platform_report.inc"
%include "user_context.inc"
%include "user_report.inc"
extern runtime_view, runtime_platform_report
extern dong_user_prepare, dong_user_first, dong_user_report, user_run
extern user_context_last_error, serial_write, serial_hex_line
extern dong_runtime_guard
global user_runtime_begin, runtime_copy_bytes, user_progress
global user_active_frame, user_runtime_report, user_kernel_stack, user_kernel_stack_top
global user_kernel_guard_low, user_kernel_guard_high

section .text
runtime_copy_bytes:
    mov rcx, rdx
    cld
    rep movsb
    ret

user_progress:
    push rbx
    mov rbx, rdi
    lea rsi, [rel user_marker_progress]
    call serial_write
    mov rax, rbx
    call serial_hex_line
    pop rbx
    ret

user_runtime_begin:
    push rbp
    mov rbp, rsp
    push rbx
    push r12
    sub rsp, 16                    ; seventh SysV argument
    lea rsi, [rel user_marker_started]
    call serial_write
    lea rdi, [rel user_kernel_guard_low]
    call dong_runtime_guard
    test rax, rax
    jnz .error
    lea rdi, [rel user_kernel_guard_high]
    call dong_runtime_guard
    test rax, rax
    jnz .error
    mov rax, [rel runtime_view]
    mov rax, [rax + RuntimeView.boot_info]
    mov rdi, [rax + BootInfo.kernel_physical]
    lea rsi, [rel client_image]
    mov edx, client_image_end - client_image
    lea rcx, [rel server_image]
    mov r8d, server_image_end - server_image
    mov r9d, IPC_ROUNDS
    mov rax, [rel runtime_platform_report + PlatformReport.tsc_hz]
    mov [rsp], rax
    call dong_user_prepare
    test rax, rax
    jnz .error
    call dong_user_first
    mov rsi, rax
    lea rdi, [rel user_active_frame]
    mov edx, UserFrame_size
    call runtime_copy_bytes
    lea rdi, [rel user_active_frame]
    mov rsi, [rdi + UserFrame.cr3]
    lea rdx, [rel user_kernel_stack_top]
    call user_run
    mov r12, rax
    call dong_user_report
    mov [rel user_runtime_report], rax
    mov rbx, rax
    call write_report
    cmp r12, 1
    jne .boundary
    cmp qword [rbx + UserReport.completed], 1
    jne .bad
    cmp qword [rbx + UserReport.error_code], 0
    jne .bad
    cmp qword [rbx + UserReport.user_errors], 0
    jne .bad
    cmp qword [rbx + UserReport.rejections], 5
    jne .bad
    cmp qword [rbx + UserReport.notification_bits], 4
    jne .bad
    lea rsi, [rel user_marker_ready]
    call serial_write
    mov eax, 1
    jmp .return
.boundary:
    mov rax, [rel user_context_last_error]
    jmp .error
.bad:
    mov eax, 0x04070003
.error:
    mov r12, rax
    lea rsi, [rel user_marker_error]
    call serial_write
    mov rax, r12
    call serial_hex_line
    xor eax, eax
.return:
    add rsp, 16
    pop r12
    pop rbx
    pop rbp
    ret

%macro REPORT_FIELDS 1
%1 version
%1 process_count
%1 expected
%1 roundtrips
%1 syscalls
%1 calls
%1 replies
%1 user_errors
%1 rejections
%1 handles_created
%1 shared_physical
%1 shared_value
%1 start_tsc
%1 end_tsc
%1 elapsed_tsc
%1 tsc_hz
%1 elapsed_ns
%1 client_bias
%1 server_bias
%1 client_root
%1 server_root
%1 client_entry
%1 server_entry
%1 client_stack
%1 server_stack
%1 notification_bits
%1 completed
%1 steps
%1 error_code
%1 last_syscall
%endmacro
%macro REPORT_FIELD 1
    lea rsi, [rel key_%1]
    call serial_write
    mov rax, [rbx + UserReport.%1]
    call serial_hex_line
%endmacro
write_report:
    push rbp
    mov rbp, rsp
    REPORT_FIELDS REPORT_FIELD
    pop rbp
    ret

section .rodata
user_marker_started: db "DONGOS_P4_USER_START",13,10,0
user_marker_ready: db "DONGOS_P4_IPC_READY",13,10,0
user_marker_progress: db "user_progress=",0
user_marker_error: db "user_runtime_error=",0
%macro REPORT_KEY 1
key_%1: db "user_",%str(%1),"=",0
%endmacro
REPORT_FIELDS REPORT_KEY
align 16
client_image: incbin "ipc_client.elf"
client_image_end:
align 16
server_image: incbin "ipc_server.elf"
server_image_end:

section .bss
align 16, resb 1
user_active_frame: resb UserFrame_size
user_runtime_report: resq 1
align 4096, resb 1
user_kernel_guard_low: resb 4096
user_kernel_stack: resb 32768
user_kernel_stack_top:
user_kernel_guard_high: resb 4096
