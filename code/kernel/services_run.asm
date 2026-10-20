bits 64
global services_pcid_metric
extern user_pcid_enabled,user_pcid_switches,user_pcid_retained
%ifndef P6_USER_SMP
%if RUNTIME_LEVEL == 7
%define P6_USER_SMP 1
%else
%define P6_USER_SMP 0
%endif
%endif
%if P6_USER_SMP
%if RUNTIME_LEVEL != 7
%error user SMP normal activation requires desktop runtime7
%endif
extern user_smp_boot_begin,user_smp_normal_policy,dong_smp_report
%include "smp_report.inc"
%endif
section .text
services_pcid_metric:
    test edi,edi
    jnz .switches
    mov rax,cr4
    ret
.switches:
    cmp edi,1
    jne .retained
    mov rax,[rel user_pcid_switches]
    ret
.retained:
    cmp edi,2
    jne .enabled
    mov rax,[rel user_pcid_retained]
    ret
.enabled:
    mov rax,[rel user_pcid_enabled]
    ret
default rel
%include "bootinfo.inc"
%include "runtime_view.inc"
%include "user_context.inc"
%include "service_report.inc"
extern runtime_view,dong_runtime_guard,user_run,user_context_last_error
extern dong_services_prepare,dong_services_first,dong_services_report
%ifdef L3_COMPILER
extern dong_compiler_enable
%endif
extern serial_write,serial_hex_line
global service_runtime_begin,runtime_copy_bytes,services_write_bytes,services_character
global user_active_frame,user_runtime_report,user_kernel_guard_low,user_kernel_guard_high
global user_kernel_stack,user_kernel_stack_top
section .text
runtime_copy_bytes:
    mov rcx,rdx
    cld
    rep movsb
    ret

; Trusted kernel buffer and exact length; bounded UART polling.
services_write_bytes:
    mov r8,rdi
    mov r9,rsi
.next:
    test r9,r9
    jz .ok
    mov ecx,0x100000
    mov dx,0x3fd
.wait:
    in al,dx
    test al,0x20
    jnz .send
    dec ecx
    jnz .wait
    mov eax,0x050b0004
    ret
.send:
    mov dx,0x3f8
    mov al,[r8]
    out dx,al
    inc r8
    dec r9
    jmp .next
.ok:
    xor eax,eax
    ret
services_character:
    mov dx,0x3fd
    in al,dx
    test al,1
    jz .empty
    mov dx,0x3f8
    in al,dx
    movzx eax,al
    ret
.empty:
    mov eax,256
    ret

service_runtime_begin:
    push rbp
    mov rbp,rsp
    push rbx
    push r12
    lea rsi,[rel services_marker_started]
    call serial_write
    lea rdi,[rel user_kernel_guard_low]
    call dong_runtime_guard
    test rax,rax
    jnz .error
    lea rdi,[rel user_kernel_guard_high]
    call dong_runtime_guard
    test rax,rax
    jnz .error
    mov rax,[rel runtime_view]
%ifdef L3_COMPILER
    call dong_compiler_enable
    mov rax,[rel runtime_view]
%endif
    mov rax,[rax+RuntimeView.boot_info]
    mov rdi,[rax+BootInfo.kernel_physical]
    call dong_services_prepare
    test rax,rax
    jnz .error
    lea rsi,[rel services_marker_loaded]
    call serial_write
%if P6_USER_SMP
    call dong_smp_report
    mov rdi,[rax+SmpReport.cpu_count]
    mov rsi,[rax+SmpReport.steps]
    call user_smp_normal_policy
    cmp rax,-1
    je .error
    test rax,rax
    jz .legacy_user
    call user_smp_boot_begin
    test eax,eax
    jnz .error
%endif
.legacy_user:
    call dong_services_first
    mov rsi,rax
    lea rdi,[rel user_active_frame]
    mov edx,UserFrame_size
    call runtime_copy_bytes
    lea rdi,[rel user_active_frame]
    mov rsi,[rdi+UserFrame.cr3]
    lea rdx,[rel user_kernel_stack_top]
    call user_run
    mov r12,rax
    call dong_services_report
    mov [rel user_runtime_report],rax
    mov rbx,rax
    call service_reports
    cmp r12,1
    jne .boundary
    cmp qword [rbx+ServiceReport.completed],1
    jne .bad
    cmp qword [rbx+ServiceReport.last_error],0
    jne .bad
    lea rsi,[rel services_marker_ready]
    call serial_write
    mov eax,1
    jmp .return
.boundary:
    mov rax,[rel user_context_last_error]
    jmp .error
.bad:
    mov eax,0x050b0002
.error:
    mov r12,rax
    lea rsi,[rel services_marker_error]
    call serial_write
    mov rax,r12
    call serial_hex_line
    xor eax,eax
.return:
    pop r12
    pop rbx
    pop rbp
    ret

%macro SERVICE_FIELDS 1
%1 version
%1 process_count
%1 syscalls
%1 calls
%1 replies
%1 errors
%1 last_error
%1 last_pid
%1 last_syscall
%1 completed
%1 steps
%1 shell_root
%1 fs_root
%1 block_root
%1 frames
%1 bundle_physical
%1 arena_physical
%1 start_tsc
%1 end_tsc
%1 current
%endmacro
%macro SERVICE_FIELD 1
    lea rsi,[rel service_key_%1]
    call serial_write
    mov rax,[rbx+ServiceReport.%1]
    call serial_hex_line
%endmacro
service_reports:
    push rbp
    mov rbp,rsp
    SERVICE_FIELDS SERVICE_FIELD
    pop rbp
    ret
global services_i8042_read,services_i8042_write
services_i8042_read:
    xor eax,eax
    in al,0x64
    test al,1
    jz .empty
    mov ecx,eax
    in al,0x60
    movzx eax,al
    test cl,0x20
    jz .errors
    or eax,0x100
.errors:
    test cl,0xc0
    jz .return
    or eax,0x20000
.return:
    ret
.empty:
    mov eax,0x10000
    ret
services_i8042_write:
    xor eax,eax
    in al,0x64
    test al,2
    jnz .busy
    mov edx,edi
    mov eax,esi
    out dx,al
    xor eax,eax
    ret
.busy:
    mov eax,1
    ret
section .rodata
services_marker_started: db "DONGOS_P5_SERVICES_START",13,10,0
services_marker_loaded: db "DONGOS_P5_ELF_LOADED",13,10,0
services_marker_ready: db "DONGOS_P5_SERVICES_READY",13,10,0
services_marker_error: db "services_runtime_error=",0
%macro SERVICE_KEY 1
service_key_%1: db "services_",%str(%1),"=",0
%endmacro
SERVICE_FIELDS SERVICE_KEY
section .bss
align 16, resb 1
user_active_frame: resb UserFrame_size
user_runtime_report: resq 1
align 4096, resb 1
user_kernel_guard_low: resb 4096
user_kernel_stack: resb 32768
user_kernel_stack_top:
user_kernel_guard_high: resb 4096
