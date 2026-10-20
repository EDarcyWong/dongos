; P2 extension acceptance probe: a CPL0 UEFI application run under QEMU TCG.
; It calls the Dong p2x_main (tests/p2_extensions_qemu.dg), which drives the
; real mm.paging large-page, alias and memory-type code against live hardware
; page tables, then reports through COM1 and isa-debug-exit:
;   0x10 -> QEMU exit 33 (pass), 0x11 -> QEMU exit 35 (fail).
bits 64
default rel

UART_POLL_LIMIT equ 0x100000

section .text
global efi_main
global __dong_panic
global p2x_read_cr3, p2x_reload_cr3, p2x_invlpg, p2x_wbinvd
global p2x_rdmsr, p2x_wrmsr, p2x_call, p2x_phys_bits, p2x_area, p2x_log
global p2x_store_root_entry, p2x_cpu_count, p2x_ap
extern p2x_main

efi_main:                       ; MS x64 ABI entry from firmware
    push rbx
    push rbp
    push rdi
    push rsi
    push r12
    push r13
    push r14
    push r15
    sub rsp, 8                  ; 8 pushes + return address: realign to 16
    cld
    mov ax, cs
    and al, 3
    jnz .fail_cpl
    mov [rel system_table], rdx ; kept for the UEFI MP Services calls
    call serial_init
    lea rcx, [rel msg_start]
    call serial_write
    call p2x_main               ; SysV, no arguments; rdi/rsi saved above
    mov rbx, rax
    lea rcx, [rel msg_result]
    call serial_write
    mov rcx, rbx
    call serial_hex
    test rbx, rbx
    jnz .fail
    lea rcx, [rel msg_pass]
    call serial_write
    mov eax, 0x10
    out 0xf4, eax
    jmp halt
.fail:
    lea rcx, [rel msg_fail]
    call serial_write
    mov eax, 0x11
    out 0xf4, eax
    jmp halt
.fail_cpl:
    mov eax, 0x11
    out 0xf4, eax
halt:
    cli
    hlt
    jmp halt

__dong_panic:
    lea rcx, [rel msg_panic]
    call serial_write
    mov eax, 0x11
    out 0xf4, eax
    jmp halt

; ---- SysV helpers called from Dong --------------------------------------
p2x_read_cr3:
    mov rax, cr3
    ret
p2x_reload_cr3:                 ; full same-root invalidation (PGE/PCID off)
    mov rax, cr3
    mov cr3, rax
    ret
p2x_invlpg:
    invlpg [rdi]
    ret
p2x_store_root_entry:           ; rdi = entry address, rsi = value
    ; OVMF maps its own page tables read-only. Lift CR0.WP for exactly this
    ; one aligned store into the firmware PML4, then restore it.
    mov rax, cr0
    mov rdx, rax
    and rax, ~(1 << 16)
    mov cr0, rax
    mov [rdi], rsi
    mov cr0, rdx
    ret
; ---- second CPU through EFI_MP_SERVICES_PROTOCOL (before ExitBootServices) --
locate_mp:                      ; -> rax = protocol or 0
    mov rax, [rel mp_services]
    test rax, rax
    jnz .done
    push rbx
    sub rsp, 0x30
    mov rax, [rel system_table]
    mov rax, [rax + 0x60]       ; BootServices
    lea rcx, [rel mp_guid]
    xor edx, edx
    lea r8, [rel mp_services]
    call [rax + 0x140]          ; LocateProtocol
    add rsp, 0x30
    pop rbx
    test rax, rax
    jz .found
    mov qword [rel mp_services], 0
.found:
    mov rax, [rel mp_services]
.done:
    ret

p2x_cpu_count:                  ; -> number of enabled processors, 0 on error
    push rbx
    sub rsp, 0x30
    call locate_mp
    test rax, rax
    jz .none
    mov rcx, rax
    lea rdx, [rsp + 0x20]
    lea r8, [rsp + 0x28]
    call [rcx + 0x00]           ; GetNumberOfProcessors(This, &All, &Enabled)
    test rax, rax
    jnz .none
    mov rax, [rsp + 0x28]
    jmp .out
.none:
    xor eax, eax
.out:
    add rsp, 0x30
    pop rbx
    ret

; The AP is started ONCE (non-blocking StartupThisAP) into ap_loop and stays
; resident, so its TLB survives between commands; a fresh StartupThisAP per
; command would re-enter the AP through firmware and hide stale translations.
; Mailbox: [0] command (0 idle, 1 read, 2 invlpg, 3 call, 4 exit), [8] address,
; [16] result, [24] alive. Every wait is bounded.
AP_SPIN equ 0x4000000

ap_start:                       ; -> rax = 0 when the AP loop is running
    cmp qword [rel ap_block + 24], 1
    je .ok
    push rbx
    sub rsp, 0x40
    call locate_mp
    test rax, rax
    jz .failed
    mov rbx, rax
    mov rax, [rel system_table]
    mov rax, [rax + 0x60]       ; BootServices
    xor ecx, ecx                ; Type 0: a plain event for StartupThisAP
    mov edx, 8                  ; TPL_CALLBACK (no notify function)
    xor r8d, r8d
    xor r9d, r9d
    lea r10, [rel ap_event]
    mov [rsp + 0x20], r10
    call [rax + 0x50]           ; CreateEvent
    test rax, rax
    jnz .failed
    mov qword [rel ap_block], 0
    mov rcx, rbx                ; This
    lea rdx, [rel ap_loop]      ; Procedure
    mov r8d, 1                  ; ProcessorNumber
    mov r9, [rel ap_event]      ; WaitEvent: non-blocking
    mov qword [rsp + 0x20], 0
    lea rax, [rel ap_block]
    mov [rsp + 0x28], rax
    mov qword [rsp + 0x30], 0
    call [rbx + 0x18]           ; StartupThisAP
    test rax, rax
    jnz .failed
    mov ecx, AP_SPIN
.wait:
    cmp qword [rel ap_block + 24], 1
    je .started
    pause
    dec ecx
    jnz .wait
.failed:
    add rsp, 0x40
    pop rbx
    mov rax, -1
    ret
.started:
    add rsp, 0x40
    pop rbx
.ok:
    xor eax, eax
    ret

; rdi = command (1 read qword, 2 invlpg, 3 call, 4 exit), rsi = address.
; Returns the AP's result; ~0 if the AP is not running or does not answer.
p2x_ap:
    push rbx
    mov rbx, rdi
    mov [rel ap_block + 8], rsi
    call ap_start
    test rax, rax
    jnz .failed
    mov [rel ap_block + 8], rsi
    mov qword [rel ap_block + 16], 0
    mfence
    mov [rel ap_block], rbx     ; publish the command last
    mov ecx, AP_SPIN
.wait:
    cmp qword [rel ap_block], 0
    je .done
    pause
    dec ecx
    jnz .wait
.failed:
    mov rax, -1
    pop rbx
    ret
.done:
    mov rax, [rel ap_block + 16]
    pop rbx
    ret

ap_loop:                        ; MS ABI on the AP, rcx = &ap_block
    push rbx
    mov rbx, rcx
    mov ecx, 0xc0000080         ; EFER.NXE: the private tree uses NX
    rdmsr
    bts eax, 11
    wrmsr
    mov qword [rbx + 24], 1     ; alive
.poll:
    mov rax, [rbx]
    test rax, rax
    jnz .command
    pause
    jmp .poll
.command:
    mov rdx, [rbx + 8]
    cmp rax, 1
    je .read
    cmp rax, 2
    je .flush
    cmp rax, 3
    je .call
    cmp rax, 4
    je .exit
    jmp .ack
.read:
    mov rax, [rdx]
    mov [rbx + 16], rax
    jmp .ack
.flush:
    invlpg [rdx]
    mov qword [rbx + 16], 0
    jmp .ack
.call:
    sub rsp, 0x20
    call rdx
    add rsp, 0x20
    mov [rbx + 16], rax
.ack:
    mfence
    mov qword [rbx], 0
    jmp .poll
.exit:
    mov qword [rbx + 24], 0
    mfence
    mov qword [rbx], 0
    pop rbx
    ret

p2x_wbinvd:
    wbinvd
    ret
p2x_rdmsr:
    mov ecx, edi
    rdmsr
    shl rdx, 32
    or rax, rdx
    ret
p2x_wrmsr:
    mov ecx, edi
    mov eax, esi
    mov rdx, rsi
    shr rdx, 32
    wrmsr
    ret
p2x_call:                       ; executes code at rdi, returns its RAX
    sub rsp, 8
    call rdi
    add rsp, 8
    ret
p2x_phys_bits:
    push rbx
    mov eax, 0x80000008
    cpuid
    and eax, 0xff
    pop rbx
    ret
p2x_area:                       ; rdi = area index -> address (VA == PA in UEFI)
    lea rax, [rel area_pool]
    cmp rdi, 0
    je .done
    lea rax, [rel area_meta]
    cmp rdi, 1
    je .done
    lea rax, [rel area_chunk]
    cmp rdi, 2
    je .done
    lea rax, [rel area_frame_b]
    cmp rdi, 3
    je .done
    lea rax, [rel area_exec]
    cmp rdi, 4
    je .done
    lea rax, [rel area_wc]
    cmp rdi, 5
    je .done
    lea rax, [rel area_exec2]
    cmp rdi, 6
    je .done
    xor eax, eax
.done:
    ret
p2x_log:                        ; rdi = value: prints "P2X <hex>"
    push rbx
    mov rbx, rdi
    lea rcx, [rel msg_log]
    call serial_write
    mov rcx, rbx
    call serial_hex
    pop rbx
    ret

; ---- COM1 ---------------------------------------------------------------
serial_init:
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

serial_byte:                    ; r9b = byte
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
    ret

serial_write:                   ; rcx = NUL-terminated string
.next:
    mov r9b, [rcx]
    test r9b, r9b
    jz .done
    call serial_byte
    inc rcx
    jmp .next
.done:
    ret

serial_hex:                     ; rcx = value; 16 hex digits and LF
    mov r10, rcx
    mov r11d, 16
.digit:
    rol r10, 4
    mov r9, r10
    and r9d, 15
    cmp r9b, 10
    jb .num
    add r9b, 'a' - 10
    jmp .out
.num:
    add r9b, '0'
.out:
    call serial_byte
    dec r11d
    jnz .digit
    mov r9b, 10
    call serial_byte
    ret

section .rdata
msg_start:  db "DONGOS_P2X_START", 10, 0
msg_result: db "DONGOS_P2X_RESULT ", 0
msg_log:    db "P2X ", 0
msg_pass:   db "DONGOS_P2X_PASS", 10, 0
msg_fail:   db "DONGOS_P2X_FAIL", 10, 0
msg_panic:  db "DONGOS_P2X_FAIL:PANIC", 10, 0
mp_guid:    dd 0x3fdda605
            dw 0xa76e, 0x4f46
            db 0xad, 0x29, 0x12, 0xf4, 0x53, 0x1b, 0x3d, 0x08

section .bss
align 4096, resb 1
area_pool:    resb 4096 * 32    ; mm.paging table pool (identity: PA == VA)
area_frame_b: resb 4096         ; replacement frame for the split check
area_exec:    resb 4096         ; dynamically executable frame
area_wc:      resb 4096         ; write-combining frame
area_exec2:   resb 4096         ; executable frame for the two-CPU transition
area_chunk:   resb 4 * 1024 * 1024  ; contains one 2 MiB aligned 2 MiB frame
area_meta:    resb 64
system_table: resq 1
mp_services:  resq 1
ap_block:     resq 4
ap_event:     resq 1
