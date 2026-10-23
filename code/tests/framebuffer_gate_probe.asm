; Host-only wrappers around source-extracted production renderers and Gate.
; The generated includes contain unchanged entry.asm fragments and unchanged
; runtime_cache_reader.asm Gate functions. No privileged entry is executed.
bits 64
default rel

%include "cpu.inc"
%include "runtime_display.inc"
extern panic_saved_frames,panic_saved_frame_count
global runtime_cache_gate_enter,runtime_cache_gate_leave,runtime_cache_gate_close
global runtime_cache_gate_drain,runtime_cache_gate_open
%include "framebuffer-production.inc"
%include "framebuffer-cache-gate.inc"

section .text
global probe_screen_draw,probe_panic_screen,probe_gate_get
global probe_gate_enter,probe_gate_leave,probe_gate_storage,probe_gate_storage_size
global probe_abi_failures

; SysV wrappers also work when called from MinGW C via sysv_abi. Six saved
; nonvolatile registers plus 40 bytes keep RSP 16-byte aligned before CALL.
; Locals: arg1,arg2,result,expected RSP,stack sentinel.
%macro WRAP 3
%1:
    push rbp
    push rbx
    push r12
    push r13
    push r14
    push r15
    sub rsp,40
    mov [rsp],rdi
    mov [rsp+8],rsi
    mov [rsp+24],rsp
    mov rax,0x5b6c7d8e9fa0b1c2
    mov [rsp+32],rax
    test rsp,15
    jz %%aligned
    or qword [rel probe_abi_failures],128
%%aligned:
    mov rbp,0x123456789abcdef0
    mov rbx,0x23456789abcdef01
%if %3 = 1
    mov r12,[rsp]
%else
    mov r12,0x3456789abcdef012
%endif
    mov r13,0x456789abcdef0123
    mov r14,0x56789abcdef01234
    mov r15,0x6789abcdef012345
    mov rdi,[rsp]
    mov rsi,[rsp+8]
    call %2
    mov [rsp+16],rax
    cmp rsp,[rsp+24]
    je %%stack_ok
    or qword [rel probe_abi_failures],256
%%stack_ok:
    mov rax,0x5b6c7d8e9fa0b1c2
    cmp [rsp+32],rax
    je %%sentinel_ok
    or qword [rel probe_abi_failures],512
%%sentinel_ok:
    mov rax,0x123456789abcdef0
    cmp rbp,rax
    je %%rbp_ok
    or qword [rel probe_abi_failures],1
%%rbp_ok:
    mov rax,0x23456789abcdef01
    cmp rbx,rax
    je %%rbx_ok
    or qword [rel probe_abi_failures],2
%%rbx_ok:
%if %3 = 1
    mov rax,[rsp]
%else
    mov rax,0x3456789abcdef012
%endif
    cmp r12,rax
    je %%r12_ok
    or qword [rel probe_abi_failures],4
%%r12_ok:
    mov rax,0x456789abcdef0123
    cmp r13,rax
    je %%r13_ok
    or qword [rel probe_abi_failures],8
%%r13_ok:
    mov rax,0x56789abcdef01234
    cmp r14,rax
    je %%r14_ok
    or qword [rel probe_abi_failures],16
%%r14_ok:
    mov rax,0x6789abcdef012345
    cmp r15,rax
    je %%r15_ok
    or qword [rel probe_abi_failures],32
%%r15_ok:
    mov rax,[rsp+16]
    add rsp,40
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret
%endmacro

WRAP probe_screen_draw,screen_draw,1
WRAP probe_panic_screen,kernel_panic_screen,0
WRAP probe_gate_get,kernel_framebuffer_gate_get,0
WRAP probe_gate_enter,framebuffer_gate_enter,0
WRAP probe_gate_leave,framebuffer_gate_leave,0
%unmacro WRAP 3

; These refer to the storage labels independently of the production getter.
probe_gate_storage:
    lea rax,[rel framebuffer_gate]
    ret
probe_gate_storage_size:
    mov eax,framebuffer_gate_end-framebuffer_gate
    ret

section .bss
align 8, resb 1
probe_abi_failures: resq 1

%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
