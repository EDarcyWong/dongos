bits 64
default rel
%include "parallel_live_report.inc"
extern dong_parallel_live_begin,dong_parallel_live_report,dong_parallel_live_retire
extern parallel_probe_entry,smp_pause,serial_write,serial_hex_line
global parallel_live_begin,parallel_live_rate,parallel_live_worker,parallel_live_pause,parallel_live_retire
section .text
parallel_live_worker:
    jmp parallel_probe_entry
parallel_live_pause:
    jmp smp_pause
parallel_live_retire:
    jmp dong_parallel_live_retire
parallel_live_rate:
    ; Local divide-by-16 LAPIC countdown against the established TSC rate.
    ; Measure each AP separately; mask the timer throughout calibration.
    mov r9,rsi
    mov rax,rsi
    xor edx,edx
    mov ecx,100
    div rcx
    test rax,rax
    jz .bad
    mov r11,rax
    mov dword [rdi+0x320],0x10040
    mov dword [rdi+0x3e0],3
    mov dword [rdi+0x380],0xffffffff
    mfence
    lfence
    rdtsc
    shl rdx,32
    or rax,rdx
    mov r10,rax
    mov r8d,10000000
.wait:
    lfence
    rdtsc
    shl rdx,32
    or rax,rdx
    sub rax,r10
    jc .bad
    cmp rax,r11
    jae .sample
    pause
    dec r8
    jnz .wait
    jmp .bad
.sample:
    mov rsi,rax
    mov eax,0xffffffff
    sub eax,[rdi+0x390]
    jz .bad
    cmp eax,0xffffffff
    je .bad
    mov dword [rdi+0x380],0
    mul r9
    cmp rdx,rsi
    jae .bad
    div rsi
    ret
.bad:
    mov dword [rdi+0x320],0x10040
    mov dword [rdi+0x380],0
    xor eax,eax
    ret
%macro PARALLEL_FIELDS 1
%1 version
%1 phase
%1 error_code
%1 cpus
%1 domain
%1 probes
%1 count
%1 tsc_hz
%1 quantum_ns
%1 started
%1 initial_done
%1 migrated_done
%1 idle_start
%1 idle_end
%1 wake_start
%1 wake_end
%1 completed
%1 restart_token
%1 restart_bottom
%1 restart_top
%1 restart_xstate
%1 restart_frame
%endmacro
%macro PARALLEL_FIELD 1
    lea rsi,[rel parallel_key_%1]
    call serial_write
    mov rax,[r12+ParallelLiveReport.%1]
    call serial_hex_line
%endmacro
parallel_live_begin:
    push rbp
    mov rbp,rsp
    push rbx
    push r12
    lea rsi,[rel parallel_start]
    call serial_write
    call dong_parallel_live_begin
    mov rbx,rax
    call dong_parallel_live_report
    mov r12,rax
    test r12,r12
    jz .status
    PARALLEL_FIELDS PARALLEL_FIELD
.status:
    test rbx,rbx
    jnz .failed
    lea rsi,[rel parallel_ready]
    call serial_write
    mov eax,1
    jmp .return
.failed:
    lea rsi,[rel parallel_error]
    call serial_write
    mov rax,rbx
    call serial_hex_line
    xor eax,eax
.return:
    pop r12
    pop rbx
    pop rbp
    ret
section .rodata
parallel_start: db "DONGOS_P6_PARALLEL_START",13,10,0
parallel_ready: db "DONGOS_P6_PARALLEL_READY",13,10,0
parallel_error: db "DONGOS_P6_PARALLEL_ERROR=",0
%macro PARALLEL_KEY 1
parallel_key_%1: db "parallel_",%str(%1),"=",0
%endmacro
PARALLEL_FIELDS PARALLEL_KEY
