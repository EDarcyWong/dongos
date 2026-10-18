; Explicit q35-only, SysV64. All plans must be stable kernel-owned memory.
; No firmware pointer, MMIO, SMI, DMA retirement or privilege dispatch here.
; 0 = requested writes issued, 1 = rejected before any I/O, 2 = SCI_EN absent.
bits 64
default rel
global pwr_io_reset, pwr_io_shutdown
%ifdef POWER_MODEL
extern pwr_model_cpl, pwr_model_enter, pwr_model_leave
extern pwr_model_read16, pwr_model_write16, pwr_model_write8
%endif

%macro ENTER 0
%ifdef POWER_MODEL
    call pwr_model_enter
    mov rbx,rax
%else
    pushfq
    pop rbx
    cli
    push rbx
    and qword [rsp],~((1<<9)|(1<<18))
    popfq
%endif
%endmacro
%macro LEAVE 0
%ifdef POWER_MODEL
    mov rdi,rbx
    call pwr_model_leave
%else
    test rbx,1<<9
    jz %%done
    sti
%%done:
%endif
%endmacro
%macro CPL0 0
%ifdef POWER_MODEL
    call pwr_model_cpl
    test rax,rax
%else
    xor eax,eax
    mov ax,cs
    test eax,3
%endif
    jnz .denied
%endmacro
%macro PROLOGUE 0
    push rbp
    mov rbp,rsp
    push rbx
    push r12
    push r13
    push r14
%endmacro
%macro RETURN 0
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret
%endmacro
section .text

pwr_io_reset:
    PROLOGUE
    mov r14,rdi
    test r14,r14
    jz .denied
    test r14,7
    jnz .denied
    CPL0
    cmp qword [r14],1
    jne .denied
    cmp qword [r14+8],0xcf9
    jne .denied
    cmp qword [r14+16],8
    jne .denied
    mov r12,[r14+24]
    cmp r12,255
    ja .denied
    ENTER
%ifdef POWER_MODEL
    mov edi,0xcf9
    mov rsi,r12
    call pwr_model_write8
%else
    mov dx,0xcf9
    mov al,r12b
    out dx,al
%endif
    LEAVE
    xor eax,eax
    RETURN
.denied:
    mov eax,1
    RETURN

pwr_io_shutdown:
    PROLOGUE
    mov r14,rdi
    test r14,r14
    jz .denied
    test r14,7
    jnz .denied
    CPL0
    cmp qword [r14],1
    jne .denied
    cmp qword [r14+8],0x604
    jne .denied
    cmp qword [r14+16],16
    jne .denied
    mov r12,[r14+24]
    test r12,~0x1c00
    jnz .denied
    ; PM1b and every byte of its plan must be absent on this q35 path.
    mov rax,[r14+32]
    or rax,[r14+40]
    or rax,[r14+48]
    or rax,[r14+56]
    or rax,[r14+80]
    jnz .denied
    cmp qword [r14+64],0x3c00
    jne .denied
    cmp qword [r14+72],0x2000
    jne .denied
    cmp qword [r14+88],7
    ja .denied
    cmp qword [r14+96],7
    ja .denied
    cmp qword [r14+104],16
    jae .denied
    cmp qword [r14+112],36
    jb .denied
    cmp qword [r14+112],0x100000
    jae .denied
    mov rax,[r14+88]
    shl rax,10
    cmp rax,r12
    jne .denied
    ; Every possible plan rejection above precedes flags/port operations.
    ENTER
%ifdef POWER_MODEL
    mov edi,0x604
    call pwr_model_read16
%else
    mov dx,0x604
    in ax,dx
%endif
    movzx r13d,ax
    test r13,1
    jz .disabled
    and r13,~0x3c00
    or r13,r12
%ifdef POWER_MODEL
    mov edi,0x604
    mov rsi,r13
    call pwr_model_write16
%else
    mov dx,0x604
    mov ax,r13w
    out dx,ax
%endif
    or r13,0x2000
%ifdef POWER_MODEL
    mov edi,0x604
    mov rsi,r13
    call pwr_model_write16
%else
    mov dx,0x604
    mov ax,r13w
    out dx,ax
%endif
    LEAVE
    xor eax,eax
    RETURN
.disabled:
    LEAVE
    mov eax,2
    RETURN
.denied:
    mov eax,1
    RETURN

section .note.GNU-stack noalloc noexec nowrite progbits
