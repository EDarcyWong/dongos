; SysV: (bottom, top, callback, arg, out_value) -> 0 success / 1 invalid.
; Caller owns mapped writable stack/out storage and executable callback code.
bits 64
default rel
section .text
global dong_call_on_stack

%macro BRIDGE_CANONICAL 1
    mov rax, %1
    shl rax, 16
    sar rax, 16
    cmp rax, %1
    jne dong_call_on_stack.invalid
%endmacro

dong_call_on_stack:
    ; Capture flags before comparisons, and restore the scratch word as well.
    ; This uses only the existing call stack, never the proposed new stack.
    mov rax, [rsp - 8]
    pushfq
    pop r11
    mov [rsp - 8], rax

    test rdi, rdi
    jz .invalid
    test rdi, 15
    jnz .invalid
    test rsi, 15
    jnz .invalid
    cmp rsi, rdi
    jbe .invalid
    mov rax, rsi
    sub rax, rdi
    cmp rax, 4096
    jb .invalid
    BRIDGE_CANONICAL rdi
    BRIDGE_CANONICAL rsi
    mov rax, rdi
    xor rax, rsi
    shr rax, 47
    test al, 1
    jnz .invalid                  ; no range spanning the canonical hole

    test rdx, rdx
    jz .invalid
    BRIDGE_CANONICAL rdx
    cmp rdx, rdi
    jb .callback_outside
    cmp rdx, rsi
    jb .invalid                  ; new frames must not overwrite callback code
.callback_outside:
    test r8, r8
    jz .invalid
    test r8, 7
    jnz .invalid
    BRIDGE_CANONICAL r8
    mov r9, r8
    add r9, 8
    jc .invalid                  ; out's complete eight-byte span must not wrap
    lea r10, [r9 - 1]
    BRIDGE_CANONICAL r10
    cmp r8, rsi
    jae .out_outside
    cmp r9, rdi
    ja .invalid
.out_outside:
    ; Protect the old save area, eight bytes of slack, and incoming return slot.
    cmp rsp, 64
    jb .invalid
    mov r10, rsp
    add r10, 8
    jc .invalid
    lea r9, [rsp - 64]
    cmp rdi, r10
    jae .new_stack_outside
    cmp rsi, r9
    ja .invalid
.new_stack_outside:
    cmp r8, r10
    jae .old_out_outside
    lea rax, [r8 + 8]
    cmp rax, r9
    ja .invalid
.old_out_outside:
    mov rax, rsp
    and eax, 15
    cmp eax, 8
    jne .invalid

    push r11                     ; complete original RFLAGS
    push rbx
    push rbp
    push r12
    push r13
    push r14
    push r15
    mov r9, rsp                  ; address of old saved nonvolatile registers
    lea rsp, [rsi - 64]           ; 16-byte aligned immediately before CALL
    mov [rsp], r9
    mov [rsp + 8], rdx
    mov [rsp + 16], rcx
    mov [rsp + 24], r8
    mov rbp, rsp                 ; callback preserves this SysV register
    mov rdi, [rbp + 16]
    cld
    call qword [rbp + 8]
    ; All volatile registers may have changed. Recover solely from our frame.
    mov rdx, [rbp + 24]
    mov [rdx], rax
    mov rsp, [rbp]
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbp
    pop rbx
    popfq
    mov eax, 0                   ; MOV/RET do not disturb restored flags or DF
    ret
.invalid:
    ; No callback/new-stack/output writes. Restore the current scratch slot.
    mov r9, [rsp - 8]
    push r11
    popfq
    mov [rsp - 8], r9
    mov eax, 1
    ret

%unmacro BRIDGE_CANONICAL 1

%ifdef STACK_BRIDGE_TEST
; Test-only ABI probes. No test symbols/references occur in ordinary builds.
extern stack_bridge_c_callback
global stack_bridge_test_callback
global stack_bridge_test_probe
global stack_bridge_test_current_overlap
global stack_bridge_test_out_overlap

stack_bridge_test_callback:
    mov [rdi], rsp
    pushfq
    pop rax
    mov [rdi + 8], rax
    sub rsp, 8
    call stack_bridge_c_callback
    add rsp, 8
    mov rcx, 0x1111222233334444
    mov rdx, 0x2222333344445555
    mov rsi, 0x3333444455556666
    mov rdi, 0x4444555566667777
    mov r8, 0x5555666677778888
    mov r9, 0x6666777788889999
    mov r10, 0x777788889999aaaa
    mov r11, 0x88889999aaaabbbb
    ret

; Sixth argument selects DF=0/1. Return zero iff result/NV/full flags survive.
stack_bridge_test_probe:
    push rbp
    push rbx
    push r12
    push r13
    push r14
    push r15
    sub rsp, 8
    mov rbx, 0x1234567812345678
    mov rbp, 0x2345678923456789
    mov r12, 0x3456789a3456789a
    mov r13, 0x456789ab456789ab
    mov r14, 0x56789abc56789abc
    mov r15, 0x6789abcd6789abcd
    test r9, r9
    jz .clear
    std
    jmp .flags
.clear:
    cld
.flags:
    pushfq
    pop r10
    mov [rsp], r10
    call dong_call_on_stack
    pushfq
    pop r10
    cmp r10, [rsp]
    jne .bad_flags
    test rax, rax
    jnz .bad_call
%macro PROBE_NV 2
    mov r10, %2
    cmp %1, r10
    jne stack_bridge_test_probe.bad_nv
%endmacro
    PROBE_NV rbx, 0x1234567812345678
    PROBE_NV rbp, 0x2345678923456789
    PROBE_NV r12, 0x3456789a3456789a
    PROBE_NV r13, 0x456789ab456789ab
    PROBE_NV r14, 0x56789abc56789abc
    PROBE_NV r15, 0x6789abcd6789abcd
%unmacro PROBE_NV 2
    xor eax, eax
    jmp .done
.bad_flags:
    mov eax, 2
    jmp .done
.bad_call:
    mov eax, 3
    jmp .done
.bad_nv:
    mov eax, 4
.done:
    cld                          ; this helper returns to an ordinary C caller
    add rsp, 8
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret

stack_bridge_test_current_overlap:
    sub rsp, 8
    lea rdi, [rsp - 2048]
    and rdi, -16
    lea rsi, [rdi + 4096]
    call dong_call_on_stack
    add rsp, 8
    ret

; Sixth argument chooses the return slot or the bridge's future save region.
stack_bridge_test_out_overlap:
    sub rsp, 8
    lea r8, [rsp - 8]
    test r9, r9
    jz .call
    lea r8, [rsp - 40]
.call:
    call dong_call_on_stack
    add rsp, 8
    ret
%endif

%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
