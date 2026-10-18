; P2 terminal exception diagnostics. No firmware, allocator, locks or SIMD.
; All public interfaces use SysV AMD64. A first panic owns the diagnostic
; channel permanently; an NMI/reentrant panic only emits a bounded marker.
bits 64
default rel
%include "cpu.inc"
%ifndef P1_TEST
%define P1_TEST 0
%endif

%define PANIC_SERIAL_BUDGET 0x10000
%define PANIC_FRAME_LIMIT 16
%define PANIC_RANGE_LIMIT 8

extern cpu_exception_stack_ranges
extern cpu_exception_stack_ranges_end
extern kernel_panic_screen

global panic_init
global panic_binding_matches
global kernel_exception_panic
global panic_saved_frames
global panic_saved_frame_count

section .text
; Input: RDI=validated RuntimeDisplay*, RSI=normal stack low, RDX=exclusive high.
; Output: none. Clobbers caller-saved RAX and flags; other registers survive.
; Called after validation and again at BSP stack-ownership boundaries, IF=0.
; Invalid/unaligned bounds disable walking that range rather than weakening it.
panic_init:
    mov [rel panic_display], rdi
    mov qword [rel panic_boot_stack_low], 0
    mov qword [rel panic_boot_stack_high], 0
    mov byte [rel panic_busy], 0
    mov byte [rel panic_serial_dead], 0
    mov qword [rel panic_saved_frame_count], 0
    test rsi, 7
    jnz .done
    test rdx, 7
    jnz .done
    cmp rsi, rdx
    jae .done
    mov rax, rdx
    sub rax, rsi
    cmp rax, 16
    jb .done
    mov [rel panic_boot_stack_low], rsi
    mov [rel panic_boot_stack_high], rdx
.done:
    ret

; Read-only confirmation of the current display and trusted normal-stack
; binding. Same three arguments as panic_init; no candidate address is read.
panic_binding_matches:
    xor eax, eax
    cmp [rel panic_display], rdi
    jne .done
    cmp [rel panic_boot_stack_low], rsi
    jne .done
    cmp [rel panic_boot_stack_high], rdx
    jne .done
    mov eax, 1
.done:
    ret

%ifdef PANIC_BINDING_TEST
global panic_test_select_range
panic_test_select_range:
    push r13
    push r14
    sub rsp, 8
    mov rax, rdi
    call panic_select_range
    setc al
    movzx eax, al
    add rsp, 8
    pop r14
    pop r13
    ret
%endif

; Input: RDI=readable ExceptionContext* built by cpu.asm, including the
; interrupted RSP/SS even for same-CPL exceptions (all gates use an IST).
; Output: never returns. Clobbers all registers and flags. Interrupts remain
; disabled; nested NMIs are covered by the atomic reentry latch.
kernel_exception_panic:
    cli
    cld
    mov al, 1
    xchg al, byte [rel panic_busy]
    test al, al
    jnz panic_reentered
    and rsp, -16
    mov r12, rdi
    mov qword [rel panic_saved_frame_count], 0
    lea rsi, [rel panic_marker]
    call panic_write
    mov rax, r12
    lea rsi, [rel label_context]
    call panic_field
    call panic_stack_name
    mov rbx, rax
    lea rsi, [rel label_stack]
    call panic_write
    mov rsi, rbx
    call panic_write
    call panic_newline

%macro PANIC_REGISTER 1
    lea rsi, [rel label_%1]
    mov rax, [r12 + ExceptionContext.%1]
    call panic_field
%endmacro
    PANIC_REGISTER rax
    PANIC_REGISTER rbx
    PANIC_REGISTER rcx
    PANIC_REGISTER rdx
    PANIC_REGISTER rsi
    PANIC_REGISTER rdi
    PANIC_REGISTER rbp
    PANIC_REGISTER r8
    PANIC_REGISTER r9
    PANIC_REGISTER r10
    PANIC_REGISTER r11
    PANIC_REGISTER r12
    PANIC_REGISTER r13
    PANIC_REGISTER r14
    PANIC_REGISTER r15
    PANIC_REGISTER vector
    PANIC_REGISTER error
    PANIC_REGISTER rip
    PANIC_REGISTER cs
    PANIC_REGISTER rflags
    PANIC_REGISTER rsp
    PANIC_REGISTER ss
    PANIC_REGISTER cr2
    lea rsi, [rel label_frame_symbol]
    mov rax, [r12 + ExceptionContext.rip]
    call panic_field

    ; Frame 00 is the interrupted instruction. Every further frame requires
    ; both qwords to be within ONE trusted, exclusive-high stack interval.
    ; The walker never probes a return address or follows a cross-stack link.
    xor r15d, r15d
    mov rax, [r12 + ExceptionContext.rip]
    call panic_frame
    inc r15d
    mov rbx, [r12 + ExceptionContext.rbp]
    mov rax, rbx
    call panic_select_range
    jnc .trace_done
.trace:
    test rbx, 7
    jnz .trace_done
    cmp rbx, r13
    jb .trace_done
    mov rax, rbx
    add rax, 16
    jc .trace_done
    cmp rax, r14
    ja .trace_done
    mov rax, [rbx + 8]
    test rax, rax
    jz .trace_done
    call panic_frame
    inc r15d
    cmp r15d, PANIC_FRAME_LIMIT
    jae .trace_done
    mov rax, [rbx]
    cmp rax, rbx
    jbe .trace_done
    mov rbx, rax
    jmp .trace
.trace_done:
    lea rsi, [rel label_frame_count]
    mov rax, r15
    call panic_field
    call panic_drain
    mov rdi, r12
    mov rsi, [rel panic_display]
    call kernel_panic_screen
panic_stop:
    cli
%if P1_TEST
    mov eax, 0x12
    out 0xf4, eax
%endif
.halt:
    hlt
    jmp .halt

; A reentrant fault must not dereference its context, inspect stack chains or
; call the renderer. It uses no CALL/PUSH/POP and has a finite UART poll count.
panic_reentered:
    lea rsi, [rel panic_reentry_marker]
.next:
    lodsb
    test al, al
    jz panic_stop
    mov r9b, al
    mov ecx, PANIC_SERIAL_BUDGET
    mov dx, 0x3fd
.wait:
    in al, dx
    test al, 0x20
    jnz .send
    pause
    dec ecx
    jnz .wait
    jmp panic_stop
.send:
    mov al, r9b
    mov dx, 0x3f8
    out dx, al
    jmp .next

; RAX=frame address. CF=1 and R13/R14=low/high on success, CF=0 on
; failure. Only table entries and saved bounds are read here, never RAX.
panic_select_range:
    test rax, 7
    jnz .missing
    mov r13, [rel panic_boot_stack_low]
    mov r14, [rel panic_boot_stack_high]
    cmp r13, r14
    jae .ist
    cmp rax, r13
    jb .ist
    mov rdx, rax
    add rdx, 16
    jc .missing
    cmp rdx, r14
    jbe .found
.ist:
    lea r8, [rel cpu_exception_stack_ranges]
    lea r9, [rel cpu_exception_stack_ranges_end]
    mov ecx, PANIC_RANGE_LIMIT
.next:
    cmp r8, r9
    jae .missing
    mov r13, [r8]
    mov r14, [r8 + 8]
    add r8, 16
    cmp r13, r14
    jae .advance
    cmp rax, r13
    jb .advance
    mov rdx, rax
    add rdx, 16
    jc .missing
    cmp rdx, r14
    jbe .found
.advance:
    dec ecx
    jnz .next
.missing:
    clc
    ret
.found:
    stc
    ret

; Classify the CONTEXT's IST, not the interrupted RSP/RBP. cpu.asm's table
; is ordered DF, NMI, EXCEPTION. Unknown addresses are reported honestly.
; Returns RAX=static name; does not read through the context pointer.
panic_stack_name:
    lea r8, [rel cpu_exception_stack_ranges]
    lea r9, [rel cpu_exception_stack_ranges_end]
    xor ecx, ecx
.next:
    cmp r8, r9
    jae .unknown
    cmp ecx, 3
    jae .unknown
    mov rdx, [r8]
    cmp r12, rdx
    jb .advance
    mov rdx, r12
    add rdx, ExceptionContext_size
    jc .unknown
    cmp rdx, [r8 + 8]
    jbe .found
.advance:
    add r8, 16
    inc ecx
    jmp .next
.found:
    lea rax, [rel panic_stack_names]
    movsxd rdx, dword [rax + rcx*4]
    add rax, rdx
    ret
.unknown:
    lea rax, [rel name_unknown]
    ret

; Internal text helpers preserve RBX/RBP/R12..R15. Every internal CALL has
; 16-byte aligned RSP; no red zone is used. All text inputs are static rodata.
; panic_putc: AL=byte; clobbers RAX/RCX/RDX/R9/flags. One timeout disables
; subsequent polling, bounding the total stall even for the complete dump.
panic_putc:
    cmp byte [rel panic_serial_dead], 0
    jne .done
    mov r9b, al
    mov ecx, PANIC_SERIAL_BUDGET
    mov dx, 0x3fd
.wait:
    in al, dx
    test al, 0x20
    jnz .send
    pause
    dec ecx
    jnz .wait
    mov byte [rel panic_serial_dead], 1
    ret
.send:
    mov al, r9b
    mov dx, 0x3f8
    out dx, al
.done:
    ret

; RSI=static NUL-terminated string, capped at 96 bytes per call.
; Clobbers RAX/RCX/RDX/RSI/R9/R11/flags.
panic_write:
    sub rsp, 8
    mov r11d, 96
.next:
    lodsb
    test al, al
    jz .done
    call panic_putc
    dec r11d
    jnz .next
.done:
    add rsp, 8
    ret

; RAX=value; always prints exactly 16 lowercase hexadecimal digits.
; Clobbers RAX/RCX/RDX/R8/R9/R10/R11/flags.
panic_hex64:
    sub rsp, 8
    mov r8, rax
    mov r10d, 16
    lea r11, [rel panic_digits]
.next:
    rol r8, 4
    mov rax, r8
    and eax, 15
    mov al, [r11 + rax]
    call panic_putc
    dec r10d
    jnz .next
    add rsp, 8
    ret

panic_newline:
    sub rsp, 8
    mov al, 13
    call panic_putc
    mov al, 10
    call panic_putc
    add rsp, 8
    ret

; RSI=label including =0x, RAX=value.
panic_field:
    sub rsp, 24
    mov [rsp], rax
    call panic_write
    mov rax, [rsp]
    call panic_hex64
    call panic_newline
    add rsp, 24
    ret

; R15=frame index 0..15, RAX=instruction/return address.
panic_frame:
    lea rsi, [rel panic_saved_frames]
    mov [rsi + r15*8], rax
    lea rdx, [r15 + 1]
    mov [rel panic_saved_frame_count], rdx
    lea rsi, [rel panic_frame_labels]
    movsxd rdx, dword [rsi + r15*4]
    add rsi, rdx
    jmp panic_field

panic_drain:
    cmp byte [rel panic_serial_dead], 0
    jne .done
    mov ecx, PANIC_SERIAL_BUDGET
    mov dx, 0x3fd
.wait:
    in al, dx
    test al, 0x40
    jnz .done
    pause
    dec ecx
    jnz .wait
.done:
    ret

section .rodata
panic_marker: db 'DONGOS_P2_PANIC',13,10,0
panic_reentry_marker: db 'DONGOS_P2_PANIC_REENTERED',13,10,0
panic_digits: db '0123456789abcdef'
label_context: db 'panic_context=0x',0
label_stack: db 'panic_stack=',0
label_frame_symbol: db 'panic_frame_symbol=0x',0
label_frame_count: db 'panic_frame_count=0x',0
%macro PANIC_LABEL 1
label_%1: db 'panic_',%str(%1),'=0x',0
%endmacro
    PANIC_LABEL rax
    PANIC_LABEL rbx
    PANIC_LABEL rcx
    PANIC_LABEL rdx
    PANIC_LABEL rsi
    PANIC_LABEL rdi
    PANIC_LABEL rbp
    PANIC_LABEL r8
    PANIC_LABEL r9
    PANIC_LABEL r10
    PANIC_LABEL r11
    PANIC_LABEL r12
    PANIC_LABEL r13
    PANIC_LABEL r14
    PANIC_LABEL r15
    PANIC_LABEL vector
    PANIC_LABEL error
    PANIC_LABEL rip
    PANIC_LABEL cs
    PANIC_LABEL rflags
    PANIC_LABEL rsp
    PANIC_LABEL ss
    PANIC_LABEL cr2
name_df: db 'DF',0
name_nmi: db 'NMI',0
name_exception: db 'EXCEPTION',0
name_unknown: db 'UNKNOWN',0
align 8
panic_stack_names: dd name_df-panic_stack_names,name_nmi-panic_stack_names,name_exception-panic_stack_names
panic_frame_labels:
    dd frame00-panic_frame_labels,frame01-panic_frame_labels,frame02-panic_frame_labels,frame03-panic_frame_labels
    dd frame04-panic_frame_labels,frame05-panic_frame_labels,frame06-panic_frame_labels,frame07-panic_frame_labels
    dd frame08-panic_frame_labels,frame09-panic_frame_labels,frame10-panic_frame_labels,frame11-panic_frame_labels
    dd frame12-panic_frame_labels,frame13-panic_frame_labels,frame14-panic_frame_labels,frame15-panic_frame_labels
frame00: db 'panic_frame_00=0x',0
frame01: db 'panic_frame_01=0x',0
frame02: db 'panic_frame_02=0x',0
frame03: db 'panic_frame_03=0x',0
frame04: db 'panic_frame_04=0x',0
frame05: db 'panic_frame_05=0x',0
frame06: db 'panic_frame_06=0x',0
frame07: db 'panic_frame_07=0x',0
frame08: db 'panic_frame_08=0x',0
frame09: db 'panic_frame_09=0x',0
frame10: db 'panic_frame_10=0x',0
frame11: db 'panic_frame_11=0x',0
frame12: db 'panic_frame_12=0x',0
frame13: db 'panic_frame_13=0x',0
frame14: db 'panic_frame_14=0x',0
frame15: db 'panic_frame_15=0x',0

section .bss
align 8
panic_saved_frames: resq PANIC_FRAME_LIMIT
panic_saved_frame_count: resq 1
panic_display: resq 1
panic_boot_stack_low: resq 1
panic_boot_stack_high: resq 1
panic_busy: resb 1
panic_serial_dead: resb 1

section .note.GNU-stack noalloc noexec nowrite progbits
