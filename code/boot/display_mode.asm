; Win64 EFI helper. Every QueryMode allocation is freed before continuing;
; only an exact validated 1920x1080 RGB/BGR mode is selected.
bits 64
default rel
%include "uefi.inc"
global desktop_graphics_mode
section .text
desktop_graphics_mode:
    push rbp
    mov rbp,rsp
    push rbx
    push r12
    push r14
    push rsi
    sub rsp,64
    mov rbx,rcx
    mov r12,rdx
    test rbx,rbx
    jz .bad
    test r12,r12
    jz .bad
    mov rax,[rbx+EFI_GRAPHICS_OUTPUT_PROTOCOL.Mode]
    test rax,rax
    jz .bad
    cmp dword [rax+EFI_GRAPHICS_OUTPUT_PROTOCOL_MODE.MaxMode],256
    ja .bad
    xor r14d,r14d
.next:
    mov rax,[rbx+EFI_GRAPHICS_OUTPUT_PROTOCOL.Mode]
    cmp r14d,[rax+EFI_GRAPHICS_OUTPUT_PROTOCOL_MODE.MaxMode]
    jae .bad
    mov qword [rsp+32],0
    mov qword [rsp+40],0
    mov rcx,rbx
    mov edx,r14d
    lea r8,[rsp+32]
    lea r9,[rsp+40]
    call [rbx+EFI_GRAPHICS_OUTPUT_PROTOCOL.QueryMode]
    xor esi,esi
    test rax,rax
    jnz .free
    cmp qword [rsp+32],EFI_GRAPHICS_OUTPUT_MODE_INFORMATION_size
    jb .free
    mov rax,[rsp+40]
    test rax,rax
    jz .free
    cmp dword [rax+EFI_GRAPHICS_OUTPUT_MODE_INFORMATION.Version],0
    jne .free
    cmp dword [rax+EFI_GRAPHICS_OUTPUT_MODE_INFORMATION.HorizontalResolution],1920
    jne .free
    cmp dword [rax+EFI_GRAPHICS_OUTPUT_MODE_INFORMATION.VerticalResolution],1080
    jne .free
    cmp dword [rax+EFI_GRAPHICS_OUTPUT_MODE_INFORMATION.PixelFormat],1
    ja .free
    cmp dword [rax+EFI_GRAPHICS_OUTPUT_MODE_INFORMATION.PixelsPerScanLine],1920
    jb .free
    cmp dword [rax+EFI_GRAPHICS_OUTPUT_MODE_INFORMATION.PixelsPerScanLine],2048
    ja .free
    mov esi,1
.free:
    mov rcx,[rsp+40]
    test rcx,rcx
    jz .advance
    call [r12+EFI_BOOT_SERVICES.FreePool]
    test rax,rax
    jnz .bad
.advance:
    test esi,esi
    jnz .select
    inc r14d
    jmp .next
.select:
    mov rcx,rbx
    mov edx,r14d
    call [rbx+EFI_GRAPHICS_OUTPUT_PROTOCOL.SetMode]
    test rax,rax
    jnz .bad
    xor eax,eax
    jmp .return
.bad:
    mov eax,1
.return:
    add rsp,64
    pop rsi
    pop r14
    pop r12
    pop rbx
    pop rbp
    ret
