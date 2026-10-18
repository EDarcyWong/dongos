; std_arch_ring0 — independent EFI probe for arch.x86_64 privileged wrappers.
; efi_main is the Microsoft x64 EFI entry. The Dong probe functions and arch
; wrappers use SysV; call_sysv0/call_sysv1 bridge the boundary. ref_check cross-
; checks raw reference operations against the real dg_arch_* wrappers on the
; same hardware locations; abi_check observes the SysV ABI contract.
bits 64
default rel

section .text
global efi_main
global __dong_panic
global ring0_save_flags
global ring0_restore_flags
extern probe_io
extern probe_cr3
extern probe_msr
extern probe_io_read
extern probe_io_write
extern probe_cr3_read
extern probe_cr3_write
extern probe_msr_read
extern probe_msr_write
extern dg_arch_read_cr3
extern dg_arch_write_cr3
extern dg_arch_in8
extern dg_arch_out8
extern dg_arch_read_msr
extern dg_arch_write_msr

UART_POLL_LIMIT equ 0x100000
TEST_MSR equ 0xc0000100
TEST_VALUE equ 0x0000000100000000

efi_main:
    sub rsp, 8
    cld
    mov ax, cs
    and al, 3
    jnz fail_cpl
    call serial_init
    lea rcx, [rel msg_start]
    call serial_write
    lea rcx, [rel probe_io]
    call call_sysv0
    test rax, rax
    jnz fail_io
    lea rcx, [rel msg_io_pass]
    call serial_write
    lea rcx, [rel probe_cr3]
    call call_sysv0
    test rax, rax
    jnz fail_cr3
    lea rcx, [rel msg_cr3_pass]
    call serial_write
    lea rcx, [rel probe_msr]
    call call_sysv0
    test rax, rax
    jnz fail_msr
    lea rcx, [rel msg_msr_pass]
    call serial_write
    lea rcx, [rel ref_check]
    call call_sysv0
    test rax, rax
    jnz fail_abi
    lea rcx, [rel abi_check]
    call call_sysv0
    test rax, rax
    jnz fail_abi
    lea rcx, [rel msg_abi_pass]
    call serial_write
    lea rcx, [rel msg_pass]
    call serial_write
    mov eax, 0x10
    out 0xf4, eax
halt:
    cli
    hlt
    jmp halt

fail_cpl:
    lea rcx, [rel msg_fail_cpl]
    call serial_write
    mov eax, 0x11
    out 0xf4, eax
    jmp halt
fail_io:
    lea rcx, [rel msg_fail_io]
    call serial_write
    mov eax, 0x11
    out 0xf4, eax
    jmp halt
fail_cr3:
    lea rcx, [rel msg_fail_cr3]
    call serial_write
    mov eax, 0x11
    out 0xf4, eax
    jmp halt
fail_msr:
    lea rcx, [rel msg_fail_msr]
    call serial_write
    mov eax, 0x11
    out 0xf4, eax
    jmp halt
fail_abi:
    lea rcx, [rel msg_fail_abi]
    call serial_write
    mov eax, 0x11
    out 0xf4, eax
    jmp halt

__dong_panic:
    lea rcx, [rel msg_fail_panic]
    call serial_write
    mov eax, 0x11
    out 0xf4, eax
    jmp halt

ring0_save_flags:
    pushfq
    pop rax
    cli
    ret
ring0_restore_flags:
    push rdi
    popfq
    ret

; Call a SysV function (no args) at rcx; result in rax.
call_sysv0:
    push rbx
    push rbp
    push rdi
    push rsi
    push r12
    push r13
    push r14
    push r15
    sub rsp, 8
    call rcx
    add rsp, 8
    pop r15
    pop r14
    pop r13
    pop r12
    pop rsi
    pop rdi
    pop rbp
    pop rbx
    ret

; Call a SysV function with one arg in rdi; rcx=fn, rdx=arg; result in rax.
call_sysv1:
    push rbx
    push rbp
    push rdi
    push rsi
    push r12
    push r13
    push r14
    push r15
    sub rsp, 8
    mov rdi, rdx
    call rcx
    add rsp, 8
    pop r15
    pop r14
    pop r13
    pop r12
    pop rsi
    pop rdi
    pop rbp
    pop rbx
    ret

; Cross-verify raw reference ops against the real dg_arch_* wrappers. Saves and
; restores COM1 scratch, FS_BASE MSR and RFLAGS on every exit. 0=pass, 1=fail.
ref_check:
    push rbp
    mov rbp, rsp
    push rbx
    sub rsp, 56
    pushfq
    pop rax
    mov [rbp-16], rax
    cli
    mov dx, 0x3ff
    in al, dx
    mov [rbp-24], al
    mov ecx, TEST_MSR
    rdmsr
    shl rdx, 32
    or rax, rdx
    mov [rbp-40], rax
    mov rax, TEST_VALUE
    mov [rbp-48], rax
    mov rax, 0x0000000200000000
    mov [rbp-56], rax
    ; reference write -> wrapper read (IO)
    mov dx, 0x3ff
    mov al, 0x5a
    out dx, al
    lea rcx, [rel probe_io_read]
    call call_sysv0
    cmp al, 0x5a
    jne .fail
    ; wrapper write -> reference read (IO)
    lea rcx, [rel probe_io_write]
    mov rdx, 0xa5
    call call_sysv1
    mov dx, 0x3ff
    in al, dx
    cmp al, 0xa5
    jne .fail
    ; CR3: confirm legal original via independent MOV read, then wrapper read matches
    mov rax, cr3
    mov [rbp-32], rax
    lea rcx, [rel probe_cr3_read]
    call call_sysv0
    cmp rax, [rbp-32]
    jne .fail
    ; CR3 write-back: wrapper write of confirmed original -> independent read-back
    lea rcx, [rel probe_cr3_write]
    mov rdx, [rbp-32]
    call call_sysv1
    mov rax, cr3
    cmp rax, [rbp-32]
    jne .fail
    ; MSR: wrapper write -> reference read
    lea rcx, [rel probe_msr_write]
    mov rdx, [rbp-48]
    call call_sysv1
    mov ecx, TEST_MSR
    rdmsr
    shl rdx, 32
    or rax, rdx
    cmp rax, [rbp-48]
    jne .fail
    ; MSR: raw write -> wrapper read (independent direction)
    mov ecx, TEST_MSR
    mov rax, [rbp-56]
    mov rdx, [rbp-56]
    shr rdx, 32
    wrmsr
    lea rcx, [rel probe_msr_read]
    call call_sysv0
    cmp rax, [rbp-56]
    jne .fail
    xor ebx, ebx
    jmp .done
.fail:
    mov ebx, 1
.done:
    mov ecx, TEST_MSR
    mov rax, [rbp-40]
    mov rdx, [rbp-40]
    shr rdx, 32
    wrmsr
    mov dx, 0x3ff
    mov al, [rbp-24]
    out dx, al
    ; independent read-back verification of restore
    mov ecx, TEST_MSR
    rdmsr
    shl rdx, 32
    or rax, rdx
    cmp rax, [rbp-40]
    jne .set_fail
    mov dx, 0x3ff
    in al, dx
    cmp al, [rbp-24]
    jne .set_fail
    jmp .finish
.set_fail:
    mov ebx, 1
.finish:
    push qword [rbp-16]
    popfq
    mov eax, ebx
    add rsp, 56
    pop rbx
    leave
    ret

; SysV ABI observer: per-call DF, all non-volatile GPRs, and balanced RSP.
abi_check:
    mov rax, rsp
    and eax, 15
    cmp eax, 8
    jne .fail_early
    pushfq
    pop rax
    test eax, 0x400
    jnz .fail_early
    mov [rel abi_saved_rbp], rbp
    sub rsp, 8
    mov [rel abi_saved_rsp], rsp
    mov rbx, 0x0b0b0b0b0b0b0b0b
    mov rbp, 0x0d0d0d0d0d0d0d0d
    mov r12, 0x1212121212121212
    mov r13, 0x1313131313131313
    mov r14, 0x1414141414141414
    mov r15, 0x1515151515151515
    ; Every real wrapper (read AND write) is called directly and checked for
    ; exact RSP balance, non-volatile GPRs and DF immediately on return, before
    ; any Dong frame restoration can hide an unbalanced return such as ret 8.
    mov [rel abi_saved_rsp2], rsp
    call dg_arch_read_cr3
    mov [rel abi_wcr3], rax
    call .check
    test eax, eax
    jnz .fail
    mov r8, [rel abi_saved_rsp2]
    cmp r8, rsp
    jne .fail
    mov rdi, [rel abi_wcr3]
    mov [rel abi_saved_rsp2], rsp
    call dg_arch_write_cr3
    call .check
    test eax, eax
    jnz .fail
    mov r8, [rel abi_saved_rsp2]
    cmp r8, rsp
    jne .fail
    mov edi, 0x3ff
    mov [rel abi_saved_rsp2], rsp
    call dg_arch_in8
    mov [rel abi_port], al
    call .check
    test eax, eax
    jnz .fail
    mov r8, [rel abi_saved_rsp2]
    cmp r8, rsp
    jne .fail
    mov edi, 0x3ff
    movzx esi, byte [rel abi_port]
    mov [rel abi_saved_rsp2], rsp
    call dg_arch_out8
    call .check
    test eax, eax
    jnz .fail
    mov r8, [rel abi_saved_rsp2]
    cmp r8, rsp
    jne .fail
    mov edi, 0xc0000100
    mov [rel abi_saved_rsp2], rsp
    call dg_arch_read_msr
    mov [rel abi_msr], rax
    call .check
    test eax, eax
    jnz .fail
    mov r8, [rel abi_saved_rsp2]
    cmp r8, rsp
    jne .fail
    mov edi, 0xc0000100
    mov rsi, [rel abi_msr]
    mov [rel abi_saved_rsp2], rsp
    call dg_arch_write_msr
    call .check
    test eax, eax
    jnz .fail
    mov r8, [rel abi_saved_rsp2]
    cmp r8, rsp
    jne .fail
    call probe_io
    call .check
    test eax, eax
    jnz .fail
    mov rax, [rel abi_saved_rsp]
    cmp rax, rsp
    jne .fail
    call probe_cr3
    call .check
    test eax, eax
    jnz .fail
    mov rax, [rel abi_saved_rsp]
    cmp rax, rsp
    jne .fail
    call probe_msr
    call .check
    test eax, eax
    jnz .fail
    mov rax, [rel abi_saved_rsp]
    cmp rax, rsp
    jne .fail
    add rsp, 8
    mov rbp, [rel abi_saved_rbp]
    xor eax, eax
    ret
.check:
    mov r8, 0x0b0b0b0b0b0b0b0b
    cmp rbx, r8
    jne .check_fail
    mov r8, 0x0d0d0d0d0d0d0d0d
    cmp rbp, r8
    jne .check_fail
    mov r8, 0x1212121212121212
    cmp r12, r8
    jne .check_fail
    mov r8, 0x1313131313131313
    cmp r13, r8
    jne .check_fail
    mov r8, 0x1414141414141414
    cmp r14, r8
    jne .check_fail
    mov r8, 0x1515151515151515
    cmp r15, r8
    jne .check_fail
    pushfq
    pop rax
    test eax, 0x400
    jnz .check_fail
    xor eax, eax
    ret
.check_fail:
    mov eax, 1
    ret
.fail_early:
    mov eax, 1
    ret
.fail:
    mov rsp, [rel abi_saved_rsp]
    add rsp, 8
    mov rbp, [rel abi_saved_rbp]
    mov eax, 1
    ret

serial_init:
    mov dx, 0x3fb
    mov al, 3
    out dx, al
    mov dx, 0x3f9
    xor eax, eax
    out dx, al
    mov dx, 0x3fb
    mov al, 0x80
    out dx, al
    mov dx, 0x3f8
    mov al, 1
    out dx, al
    mov dx, 0x3f9
    xor eax, eax
    out dx, al
    mov dx, 0x3fb
    mov al, 3
    out dx, al
    mov dx, 0x3fa
    mov al, 0xc7
    out dx, al
    mov dx, 0x3fc
    mov al, 0x0b
    out dx, al
    ret

serial_write:
.next:
    mov r9b, [rcx]
    test r9b, r9b
    jz .drain
    mov r8d, UART_POLL_LIMIT
    mov dx, 0x3fd
.wait:
    in al, dx
    test al, 0x20
    jnz .send
    pause
    dec r8d
    jnz .wait
    ret
.send:
    mov dx, 0x3f8
    mov al, r9b
    out dx, al
    inc rcx
    jmp .next
.drain:
    mov r8d, UART_POLL_LIMIT
    mov dx, 0x3fd
.wait_empty:
    in al, dx
    test al, 0x40
    jnz .done
    pause
    dec r8d
    jnz .wait_empty
.done:
    ret

section .bss
align 8
abi_saved_rsp: resq 1
abi_saved_rbp: resq 1
abi_saved_rsp2: resq 1
abi_wcr3: resq 1
abi_msr: resq 1
align 8
abi_port: resb 1

section .rdata
msg_start:     db "DONGOS_STD_ARCH_START", 10, 0
msg_io_pass:   db "DONGOS_STD_ARCH_IO_PASS", 10, 0
msg_cr3_pass:  db "DONGOS_STD_ARCH_CR3_PASS", 10, 0
msg_msr_pass:  db "DONGOS_STD_ARCH_MSR_PASS", 10, 0
msg_abi_pass:  db "DONGOS_STD_ARCH_ABI_PASS", 10, 0
msg_pass:      db "DONGOS_STD_ARCH_PASS", 10, 0
msg_fail_cpl:  db "DONGOS_STD_ARCH_FAIL:CPL", 10, 0
msg_fail_io:   db "DONGOS_STD_ARCH_FAIL:IO", 10, 0
msg_fail_cr3:  db "DONGOS_STD_ARCH_FAIL:CR3", 10, 0
msg_fail_msr:  db "DONGOS_STD_ARCH_FAIL:MSR", 10, 0
msg_fail_abi:  db "DONGOS_STD_ARCH_FAIL:ABI", 10, 0
msg_fail_panic: db "DONGOS_STD_ARCH_FAIL:PANIC", 10, 0
